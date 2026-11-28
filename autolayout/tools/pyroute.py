"""pyroute.py - router Python 2 lop theo quyet dinh cua agent (INV-3).
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" pyroute.py IN.kicad_pcb OUT.kicad_pcb [--strip]

Y tuong
- Luoi RES mm, A* 8 huong + via. Moi net duoc route theo thu tu uu tien trong PLAN (P1 -> P3).
- Vat can cua net N = moi dong dong cua net KHAC, nua bang clearance = max(clr_N, clr_khac) + w/2 (hoac via/2).
- B.Cu la plane GND: dat chi phi cao (D-2L), chi nhay ngan. Pad GND SMD noi xuong plane bang via + stub ngan.
- K1: F.Cu khong di duoi than linh kien (F.Fab bbox); connector chi cam phia duoi hang pad.
- Ket qua ghi vao board bang pcbnew; DRC/audit chay RIENG (khong tu cham dat).
"""
import heapq
import math
import sys
import time

import pcbnew
from pcbnew import FromMM, VECTOR2I

import os as _os
RES = float(_os.environ.get("PYROUTE_RES", "0.05"))      # 0.1 = che do route NHANH (luoi tho) de loc hang loat phuong an; 0.05 = route that
EDGE_CLR = 0.5          # D-FAB copper_to_edge
HOLE_CLR = 0.25
SKEW_REVIEW = 5.0        # mm; D-DIFF usb_fs_ls: target 2.0, review 5.0. USB FS 12 Mbps: lech vai mm = vai chuc ps << 83 ns bit time
SKEW_TARGET = None       # None = chi chinh khi vuot REVIEW; --match-skew X de ep chinh ve <= X (vd USB HS)
MAX_EXP = int(_os.environ.get("PYROUTE_MAXEXP", "2500000"))      # tran so buoc A* moi lan tim (benchmark dung nho hon de khong ket)
COUPLE_R = 0.55          # vung "bam sat" quanh net doi tac (mm, tinh tu tim track)
BRIDGE_MAX = 8.0         # 2 pad cung net cung linh kien cach <= 8 mm -> noi bang cua so hep truoc
BRIDGE_MARGIN = 3.0
FINE_PAD = 0.45          # pad hep hon 0.45 mm (TSSOP, hang pad connector) = pitch min
NECK_W = 0.25            # nhanh vao pad pitch min: thu hep xuong 0.25 mm (owner: >= 0.1 mm la duoc)
GRID_SAFETY = 0.02      # mm: bu sai so lam tron luoi 0.05 (pad khong nam tren luoi)
GND_VIA_B_EXTRA = 0.45  # mm: track B.Cu khong sat via GND (de thermal relief noi duoc voi plane)
VIA_EXTRA = 0.15        # track/via cua net khac khong duoc sat via: clearance + 0.15 mm (yeu cau owner)
HUG_GAP = 0.45      # mm: mep track cach mep pad SMD khac net <= gia tri nay = "sat hang chan" (owner 2026-11-27: trace qua roi)
VIA_PAD_GAP = 0.25   # Eurocircuits: >=0.25 mm mep pad SMD -> mep via (L52)
GND_NEAR = 1.5          # mm: via GND cua tu decoupling cach pad GND <= 1.5 (D-DECAP)
KEEP_LOOP_DEPTH = 1.5     # mm: vung duoc phep vong quanh dau pad connector (cau D+/D-, cau VBUS) tren F.Cu
BRIDGE_VIA = (0.5, 0.3)  # via nho nhat (min_via_diameter) cho cau noi pad o hang pad 0.5 mm
KEEP_SKIP_PREFIX = ("U",)   # IC: vung xam K1 (kenh giua hai hang chan) - khong chan
# ---- chi phi (mm tuong duong) - cho phep tinh chinh -------------------------------------------
COST = {
    "bend45": 0.25,      # phat doi huong 45 do
    "bend90": 1.0,       # phat doi huong >= 90 do
    "via": 2.0,          # moi via
    "via_in_pad": 3.0,   # via nam trong pad
    "bcu_mult": 2.0,
    "bcu_p12": 3.5,     # B.Cu cho net P1/P2 dat hon (D-2L: khong cat plane GND)
    "via_p12": 14.0,    # via tren net P1/P2: dat ngang ~14 mm duong di, tuc la chi khi het cach khac
    "hug": 3.0,          # he so nhan chieu dai khi di sat (<= HUG_GAP) pad SMD cua net khac: chong chay doc hang chan IC (L57)
    "couple_out": 1.35,  # he so nhan chieu dai khi KHONG di song song voi net doi tac (cap vi sai)     # he so nhan chieu dai tren B.Cu (plane GND, D-2L)
}

# ---- net class: doc tu <board>.kicad_pro (clearance, track_width, via_diameter, via_drill) -------------
CLASSES = {"Default": (0.2, 0.2, 0.6, 0.3)}
PATTERNS = []          # [(fnmatch pattern, class name)]
_NC_CACHE = {}


def load_config(board_path, pro_override=None):
    """Doc netclass + rule tu file .kicad_pro cung ten voi board. Khong co file -> gia tri mac dinh D-FAB."""
    global EDGE_CLR, HOLE_CLR
    import json, os
    pro = pro_override or os.path.splitext(board_path)[0] + ".kicad_pro"
    if not os.path.exists(pro):
        print("WARN: khong thay", pro, "-> dung mac dinh D-FAB")
        return
    d = json.load(open(pro, encoding="utf-8"))
    ns = d.get("net_settings", {})
    for c in ns.get("classes", []):
        CLASSES[c["name"]] = (c.get("clearance", 0.2), c.get("track_width", 0.2), c.get("via_diameter", 0.6), c.get("via_drill", 0.3))
    for p in ns.get("netclass_patterns", []) or []:
        PATTERNS.append((p["pattern"], p["netclass"]))
    r = d.get("board", {}).get("design_settings", {}).get("rules", {}) or d.get("board_design_settings", {}).get("rules", {})
    EDGE_CLR = r.get("min_copper_edge_clearance", EDGE_CLR) or EDGE_CLR
    HOLE_CLR = r.get("min_hole_clearance", HOLE_CLR) or HOLE_CLR
    print(f"config: classes={ {k: v for k, v in CLASSES.items()} } patterns={len(PATTERNS)} edge={EDGE_CLR} hole={HOLE_CLR}")


def nc(net):
    if net in _NC_CACHE:
        return _NC_CACHE[net]
    import fnmatch
    best = CLASSES["Default"]
    for pat, cls in PATTERNS:
        if fnmatch.fnmatchcase(net, pat) and cls in CLASSES:
            best = CLASSES[cls]
            break
    _NC_CACHE[net] = best
    return best


DECAP_NAMES = ("V3", "VCAP", "+3V3", "3V3", "VDD", "VCC", "+3.3V")   # rail cuc bo sau tu decoupling
POWER_NAMES = ("VBUS", "+5V", "5V", "+3V3", "3V3", "V3", "VCAP", "VDD", "VCC", "+3.3V")


def auto_plan(pads):
    """Thu tu uu tien tu dong: vi sai/USB -> CC -> nguon/tai (net class khac Default) -> tin hieu (HPWL ngan truoc) -> GND."""
    by = {}
    for p in pads:
        if p["net"] and not p["net"].startswith("unconnected"):
            by.setdefault(p["net"], []).append(p)
    nets = {n: ps for n, ps in by.items() if len({(round(q["x"], 2), round(q["y"], 2)) for q in ps}) >= 2}

    def base(n):
        return n.split("/")[-1].upper()

    def hpwl(ps):
        xs = [q["x"] for q in ps]; ys = [q["y"] for q in ps]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

    A, B, C, D, E, F, G = [], [], [], [], [], [], []
    for n, ps in nets.items():
        b = base(n)
        if b in ("GND", "AGND", "DGND", "PGND"):
            G.append(n)
        elif any(k in b for k in ("USB", "DP", "DM", "DN", "D+", "D-")) and "UP" not in b:
            A.append(n)
        elif b.startswith("CC"):
            B.append(n)
        elif b in DECAP_NAMES:
            E.append(n)
        elif nc(n) != CLASSES["Default"] or b in POWER_NAMES:
            C.append(n)
        elif "GATE" in b:
            F.append(n)
        else:
            D.append(n)
    A.sort(key=lambda n: (not base(n).endswith(("DP", "D+")), n))
    B.sort()
    C.sort(key=lambda n: (-nc(n)[1], -len(nets[n]), n))
    D.sort(key=lambda n: hpwl(nets[n]))
    E.sort(key=lambda n: hpwl(nets[n]))
    F.sort(key=lambda n: hpwl(nets[n]))
    # thu tu theo yeu cau owner: cap USB -> (CC cung hang pad) -> nguon thong suot -> tu decoupling -> gate -> tin hieu cham -> GND
    return A + B + C + E + F + D + G


class Grid:
    def __init__(self, bbv):
        L, T, R, B = bbv
        self.ox, self.oy = L, T
        self.nx = int((R - L) / RES) + 1
        self.ny = int((B - T) / RES) + 1
        self.n = self.nx * self.ny

    def cell(self, x, y):
        return int(round((x - self.ox) / RES)), int(round((y - self.oy) / RES))

    def xy(self, ix, iy):
        return self.ox + ix * RES, self.oy + iy * RES

    # ---- painting (toa do mm, ghi vao bytearray) ------------------------------------------
    def rect(self, m, x0, y0, x1, y1):
        # chi chan cac o NAM TRONG vung (bien chinh xac = du clearance, KiCad cho phep gap == clearance)
        i0 = max(0, math.floor((x0 - self.ox) / RES + 1e-6) + 1); i1 = min(self.nx - 1, math.ceil((x1 - self.ox) / RES - 1e-6) - 1)
        j0 = max(0, math.floor((y0 - self.oy) / RES + 1e-6) + 1); j1 = min(self.ny - 1, math.ceil((y1 - self.oy) / RES - 1e-6) - 1)
        if i1 < i0:
            return
        fill = b"\x01" * (i1 - i0 + 1)
        for j in range(j0, j1 + 1):
            s = j * self.nx
            m[s + i0:s + i1 + 1] = fill

    def circle(self, m, cx, cy, r):
        j0 = max(0, math.ceil((cy - r - self.oy) / RES)); j1 = min(self.ny - 1, math.floor((cy + r - self.oy) / RES))
        for j in range(j0, j1 + 1):
            dy = self.oy + j * RES - cy
            d = r * r - dy * dy
            if d < 0:
                continue
            dx = math.sqrt(d)
            i0 = max(0, math.ceil((cx - dx - self.ox) / RES)); i1 = min(self.nx - 1, math.floor((cx + dx - self.ox) / RES))
            if i1 >= i0:
                s = j * self.nx
                m[s + i0:s + i1 + 1] = b"\x01" * (i1 - i0 + 1)

    def seg(self, m, x1, y1, x2, y2, r):
        L = math.hypot(x2 - x1, y2 - y1)
        k = max(1, int(L / (RES * 0.8)))
        for t in range(k + 1):
            self.circle(m, x1 + (x2 - x1) * t / k, y1 + (y2 - y1) * t / k, r)


class Item:
    """dong (mm). kind: rect(x0,y0,x1,y1) | seg(x1,y1,x2,y2,hw) | circ(cx,cy,r). layers: {0,1}."""
    def __init__(self, kind, data, layers, net, margin=0.0, margin_b=0.0):
        self.kind, self.data, self.layers, self.net, self.margin, self.margin_b = kind, data, layers, net, margin, margin_b   # margin: khoang cach them (mm) ngoai clearance


def box_mm(bb):
    """BOX2I -> (x0,y0,x1,y1) mm. Doc ngay vao bien cuc bo (swig temp co the bi giai phong) va kiem tra gia tri rac."""
    v = (bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6)
    if any(abs(x) > 1e4 for x in v):
        raise RuntimeError(f"swig tra gia tri rac: {v}")
    return v


def pt_mm(p):
    v = (p.x / 1e6, p.y / 1e6)
    if any(abs(x) > 1e4 for x in v):
        raise RuntimeError(f"swig tra gia tri rac: {v}")
    return v


def pad_items(b):
    items, pads = [], []
    for f in b.GetFootprints():
        for p in f.Pads():
            rb = p.GetBoundingBox()
            x0, y0, x1, y1 = box_mm(rb)
            ppos = pt_mm(p.GetPosition())
            fpos = pt_mm(f.GetPosition())
            net = p.GetNetname()
            tht = p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
            layers = {0, 1} if tht else ({0} if f.GetLayer() == pcbnew.F_Cu else {1})
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                items.append(Item("circ", (ppos[0], ppos[1], p.GetDrillSize().x / 2e6 + HOLE_CLR), {0, 1}, "#HOLE"))
                continue
            items.append(Item("rect", (x0, y0, x1, y1), layers, net))
            pads.append({"ref": f.GetReference(), "num": p.GetNumber(), "net": net, "x": ppos[0],
                         "y": ppos[1], "rect": (x0, y0, x1, y1), "tht": tht, "layers": layers, "fc": fpos})
    return items, pads


def keepouts(b):
    """K1: F.Cu bi cam duoi than linh kien (F.Fab bbox). J1: chi duoi hang pad."""
    out = []
    for f in b.GetFootprints():
        ref = f.GetReference()
        npth = sum(1 for p in f.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH)
        if ref.startswith(KEEP_SKIP_PREFIX) or (ref != "J1" and npth >= 2):
            continue   # IC (vung xam) va header/JST xuyen lo: owner cho phep di duoi bung (chi giu khoang cach voi via)
        xs0 = ys0 = 1e9
        xs1 = ys1 = -1e9
        for g in f.GraphicalItems():
            if g.GetLayer() == pcbnew.F_Fab:
                gb = box_mm(g.GetBoundingBox())
                xs0, ys0, xs1, ys1 = min(xs0, gb[0]), min(ys0, gb[1]), max(xs1, gb[2]), max(ys1, gb[3])
        if xs0 > 1e8:
            continue
        y0, y1 = ys0, ys1
        if ref == "J1":
            # connector hang pad nam o mot dau: chi cam phia THAN (khac phia hang pad), dung voi moi huong quay 0/180
            sm = [box_mm(p.GetBoundingBox()) for p in f.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
            pcy = sum((q[1] + q[3]) / 2 for q in sm) / len(sm)
            # ngoai le "vong quanh dau pad" (owner: theo ref): KEEP_LOOP_DEPTH mm ngay sau hang pad van duoc di tren F.Cu
            if pcy < (ys0 + ys1) / 2:        # hang pad o phia tren (y nho) -> than o phia duoi
                y0 = max(q[3] for q in sm) + KEEP_LOOP_DEPTH
            else:                            # hang pad o phia duoi -> than o phia tren
                y1 = min(q[1] for q in sm) - KEEP_LOOP_DEPTH
        out.append((xs0, y0, xs1, y1))
    return out


def _pt_seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def ic_keepouts(b):
    """Than IC (F.Fab bbox cua U*): net P1/P2 khong duoc di duoi than (owner: v8 tranh, circle 2-4 trong anh review)."""
    out = []
    for f in b.GetFootprints():
        if not f.GetReference().startswith(KEEP_SKIP_PREFIX):
            continue
        xs0 = ys0 = 1e9
        xs1 = ys1 = -1e9
        for g in f.GraphicalItems():
            if g.GetLayer() == pcbnew.F_Fab:
                gb = box_mm(g.GetBoundingBox())
                xs0, ys0, xs1, ys1 = min(xs0, gb[0]), min(ys0, gb[1]), max(xs1, gb[2]), max(ys1, gb[3])
        if xs0 < 1e8:
            out.append((xs0, ys0, xs1, ys1))
    return out


class Router:
    def __init__(self, b):
        self.b = b
        _bb = b.GetBoardEdgesBoundingBox()
        self.bbv = box_mm(_bb)
        self.g = Grid(self.bbv)
        self.items, self.pads = pad_items(b)
        self.keep = keepouts(b)
        self.ic_keep = ic_keepouts(b)
        self.block_ic = set()       # net P1/P2: cam di duoi than IC
        self.log = []
        self.partner = {}
        self.gnd_ties = []
        self.src_pad = {}         # net -> 'J1.B6': ep pad thoat (thu cac to hop pad thoat de tranh via cheo cap)
        self.chains = {}          # net -> [{from, path[], width}] cay nguon co thu tu
        self.out_vias = []
        self.via_cost_of = {}       # net -> chi phi via (P1/P2 cao: chi dung khi bat buoc)
        self.cur_via_cost = COST["via"]
        self.cur_bcu = COST["bcu_mult"]
        self.segs = {}      # net -> [(layer, (x1,y1), (x2,y2), w)]  de ghep cap + do do dai
        self.preconn = self._existing_clusters(b)     # (ref,num) -> id cum: pad DA noi san bang dong co san (L79)
        self.virt = {}
        self._make_virtual()
        # dong da co (khi khong --strip)
        for t in b.GetTracks():
            if t.GetClass() == "PCB_VIA":
                c = pt_mm(t.GetPosition())
                self.items.append(Item("circ", (c[0], c[1], t.GetWidth(pcbnew.F_Cu) / 2e6), {0, 1}, t.GetNetname(), VIA_EXTRA))
            else:
                a_, c_ = pt_mm(t.GetStart()), pt_mm(t.GetEnd())
                self.items.append(Item("seg", (a_[0], a_[1], c_[0], c_[1], t.GetWidth() / 2e6),
                                       {0 if t.GetLayer() == pcbnew.F_Cu else 1}, t.GetNetname()))

    @staticmethod
    def _existing_clusters(b):
        """Union-find hinh hoc: pad + doan + via cung net cham nhau -> cung cum. Tra ve {(ref,num): (net, id)}.
        Khong co buoc nay, route lai net da co day tay se coi moi pad la mot nhom va di THEM duong moi (L79)."""
        tr = [t for t in b.GetTracks() if t.GetNetname()]
        if not tr:
            return {}
        pads = [p for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()]
        nodes = [("pad", p) for p in pads] + [("trk", t) for t in tr]
        par = list(range(len(nodes)))
        def find(i):
            while par[i] != i:
                par[i] = par[par[i]]; i = par[i]
            return i
        def uni(i, j):
            par[find(i)] = find(j)
        bynet = {}
        for i, (k, o) in enumerate(nodes):
            bynet.setdefault(o.GetNetname(), []).append(i)
        TOL = 2000                                    # 2 um
        def ends(t):
            return [t.GetPosition()] if t.GetClass() == "PCB_VIA" else [t.GetStart(), t.GetEnd()]
        def layers(t):
            return {pcbnew.F_Cu, pcbnew.B_Cu} if t.GetClass() == "PCB_VIA" else {t.GetLayer()}
        for net, idx in bynet.items():
            ts = [i for i in idx if nodes[i][0] == "trk"]
            ps = [i for i in idx if nodes[i][0] == "pad"]
            if not ts:
                continue
            for a in range(len(ts)):
                ta = nodes[ts[a]][1]
                for c in range(a + 1, len(ts)):
                    tc = nodes[ts[c]][1]
                    if not (layers(ta) & layers(tc)):
                        continue
                    if any((e1 - e2).EuclideanNorm() <= TOL for e1 in ends(ta) for e2 in ends(tc)) or \
                       any(ta.HitTest(e, 0) for e in ends(tc)) or any(tc.HitTest(e, 0) for e in ends(ta)):   # ca noi chu T (dau doan nam giua doan kia)
                        uni(ts[a], ts[c])
                for pi in ps:
                    p = nodes[pi][1]
                    pl = {pcbnew.F_Cu, pcbnew.B_Cu} if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else {pcbnew.B_Cu if p.IsOnLayer(pcbnew.B_Cu) and not p.IsOnLayer(pcbnew.F_Cu) else pcbnew.F_Cu}
                    if (layers(ta) & pl) and (any(p.HitTest(e) for e in ends(ta)) or
                                              (ta.GetClass() != "PCB_VIA" and ta.HitTest(p.GetPosition(), 0))):   # doan chay XUYEN qua pad (vd U2 3->4)
                        uni(ts[a], pi)
        out = {}
        for i, (k, o) in enumerate(nodes):
            if k == "pad":
                out[(o.GetParentFootprint().GetReference(), o.GetNumber())] = (o.GetNetname(), find(i))
        return out

    ESC_LEN = 1.2
    ESC_LEN_FINE = 2.6
    def _make_virtual(self):
        """Giu san loi thoat cho pad chua route: pad dai (>=1.6:1) -> doan thang ra ngoai theo truc dai.
        Net khac khong duoc chan loi thoat nay (tranh 'bac cau' che mat pad ke ben o connector pitch 0.5)."""
        for p in self.pads:
            if p["tht"] or not p["net"]:
                continue
            x0, y0, x1, y1 = p["rect"]
            w, h = x1 - x0, y1 - y0
            fx, fy = p["fc"]
            if h >= 1.6 * w:
                d = (0, -1 if p["y"] < fy else 1)
            elif w >= 1.6 * h:
                d = (-1 if p["x"] < fx else 1, 0)
            else:
                continue
            hw = nc(p["net"])[1] / 2
            esc = self.ESC_LEN_FINE if min(w, h) <= 0.35 else self.ESC_LEN   # pad pitch 0.5: chua cho cho via + cau cua cap doi
            self.virt.setdefault(p["net"], []).append(
                Item("seg", (p["x"], p["y"], p["x"] + d[0] * esc, p["y"] + d[1] * esc, hw), p["layers"], p["net"]))

    # ---- mat na vat can cho net -------------------------------------------------------------
    def masks(self, net, vd_override=None, w_override=None, clr_override=None):
        g = self.g
        clr, w, vd, _ = nc(net)
        if clr_override is not None:
            clr = clr_override
        if w_override:
            w = w_override
        if vd_override:
            vd = vd_override
        mt = [bytearray(g.n), bytearray(g.n)]      # track
        mv = [bytearray(g.n), bytearray(g.n)]      # via
        hug = [bytearray(g.n), bytearray(g.n)]     # vung "sat pad khac net": khong cam, chi dat hon (COST hug)
        virt = [v for n, vs in self.virt.items() if n != net for v in vs]
        for it in self.items + virt:
            if it.net != net and it.net != "#HOLE" and it.kind == "rect" and len(it.layers) == 1:
                x0, y0, x1, y1 = it.data; e = max(clr, nc(it.net)[0]) + w / 2 + HUG_GAP
                for l in it.layers:
                    g.rect(hug[l], x0 - e, y0 - e, x1 + e, y1 + e)
            if it.net == net:
                # V1: via KHONG duoc nam trong / sat pad SMD, ke ca pad cua chinh net (thiec chay xuong lo khi reflow)
                if it.kind == "rect" and len(it.layers) == 1:
                    x0, y0, x1, y1 = it.data; e = VIA_PAD_GAP + vd / 2
                    for l in (0, 1):
                        g.rect(mv[l], x0 - e, y0 - e, x1 + e, y1 + e)
                continue
            c0 = 0.0 if it.net == "#HOLE" else max(clr, nc(it.net)[0]) + it.margin + GRID_SAFETY
            for m, half in ((mt, w / 2), (mv, vd / 2)):
                for l in it.layers:
                    c = c0 + (it.margin_b if l == 1 else 0.0)     # margin_b: via GND can cho thermal relief tren B.Cu (plane)
                    if it.kind == "rect":
                        x0, y0, x1, y1 = it.data
                        e = c + half
                        g.rect(m[l], x0 - e, y0 - e, x1 + e, y1 + e)
                    elif it.kind == "circ":
                        cx, cy, r = it.data
                        g.circle(m[l], cx, cy, r + c + half)
                    else:
                        x1, y1, x2, y2, hw = it.data
                        g.seg(m[l], x1, y1, x2, y2, hw + c + half)
        # mep board
        L, T, R, B_ = self.bbv
        for m, half in ((mt, w / 2), (mv, vd / 2)):
            for l in (0, 1):
                e = EDGE_CLR + half
                g.rect(m[l], L - 5, T - 5, R + 5, T + e)
                g.rect(m[l], L - 5, B_ - e, R + 5, B_ + 5)
                g.rect(m[l], L - 5, T - 5, L + e, B_ + 5)
                g.rect(m[l], R - e, T - 5, R + 5, B_ + 5)
        # K1 keepout tren F.Cu (tru pad cung net)
        kp0 = bytearray(g.n)       # keepout than linh kien tren F.Cu: rieng, de pad cua CHINH net co loi vao (keepout khong chan pad cua minh)
        for x0, y0, x1, y1 in self.keep:
            g.rect(kp0, x0 - w / 2, y0 - w / 2, x1 + w / 2, y1 + w / 2)
            g.rect(mv[0], x0 - vd / 2, y0 - vd / 2, x1 + vd / 2, y1 + vd / 2)
        if net in self.block_ic:
            for x0, y0, x1, y1 in self.ic_keep:
                g.rect(kp0, x0 - w / 2, y0 - w / 2, x1 + w / 2, y1 + w / 2)
                g.rect(mv[0], x0 - vd / 2, y0 - vd / 2, x1 + vd / 2, y1 + vd / 2)
        # cho phep o pad cua chinh net (keepout/lan can)
        for p in self.pads:
            if p["net"] == net:
                x0, y0, x1, y1 = p["rect"]
                for l in p["layers"]:
                    self._clear_rect(mt[l], x0, y0, x1, y1, net)
                e_ = w / 2 + 0.06
                self._clear_rect(kp0, x0 - e_, y0 - e_, x1 + e_, y1 + e_, net)     # loi vao pad cua chinh net xuyen qua vung dem keepout
        mt[0] = bytearray((int.from_bytes(mt[0], "little") | int.from_bytes(kp0, "little")).to_bytes(g.n, "little"))
        if clr_override is None and w_override is None:
            self.cur_hug = hug
        return mt, mv

    def _clear_rect(self, m, x0, y0, x1, y1, net):
        # chi xoa nhung o khong thuoc dong cua net khac (da duoc sơn rieng) -> don gian: xoa het vung pad
        g = self.g
        i0 = max(0, math.ceil((x0 - g.ox) / RES)); i1 = min(g.nx - 1, math.floor((x1 - g.ox) / RES))
        j0 = max(0, math.ceil((y0 - g.oy) / RES)); j1 = min(g.ny - 1, math.floor((y1 - g.oy) / RES))
        for j in range(j0, j1 + 1):
            s = j * g.nx
            for i in range(i0, i1 + 1):
                m[s + i] = 0

    # ---- A* ---------------------------------------------------------------------------------
    DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]

    def astar(self, sources, goals, mt, mv, via_ok, padcells, max_exp=MAX_EXP, goal_fn=None, window=None, near=None):
        g = self.g
        nx, N = g.nx, g.n
        hugm = getattr(self, "cur_hug", None)
        goals = set(goals)
        gl = [(k % N) % nx for k in goals], [(k % N) // nx for k in goals]
        gcoords = [((k % N) % nx, (k % N) // nx) for k in goals]

        def h(ix, iy):
            if goal_fn is not None:
                return 0.0
            best = 1e9
            for gx, gy in gcoords:
                dx, dy = abs(ix - gx), abs(iy - gy)
                d = (max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)) * RES
                if d < best:
                    best = d
            return best

        pq, gs = [], {}
        for s in sources:
            l, idx = divmod(s, N)
            key = (s, 8)
            gs[key] = 0.0
            heapq.heappush(pq, (h(idx % nx, idx // nx), 0.0, s, 8))
        par = {}
        exp = 0
        step = {d: math.hypot(*d) * RES for d in self.DIRS}
        while pq:
            f, gc, s, d = heapq.heappop(pq)
            if gs.get((s, d), 1e18) < gc - 1e-12:
                continue
            l, idx = divmod(s, N)
            ix, iy = idx % nx, idx // nx
            if (goal_fn(l, idx) if goal_fn else s in goals):
                path = [s]
                cur = (s, d)
                while cur in par:
                    cur = par[cur]
                    path.append(cur[0])
                return path[::-1], exp
            exp += 1
            if exp > max_exp:
                return None, exp
            m = mt[l]
            for di, (dx, dy) in enumerate(self.DIRS):
                jx, jy = ix + dx, iy + dy
                if jx < 0 or jy < 0 or jx >= nx or jy >= g.ny:
                    continue
                if window is not None and not (window[0] <= jx <= window[2] and window[1] <= jy <= window[3]):
                    continue
                jdx = jy * nx + jx
                if m[jdx]:
                    continue
                if dx and dy and (m[iy * nx + jx] or m[jy * nx + ix]):
                    continue
                c = step[(dx, dy)] * (self.cur_bcu if l == 1 else 1.0)
                if hugm is not None and hugm[l][jdx]:
                    c *= COST["hug"]
                if near is not None and not near[l][jdx]:
                    c *= COST["couple_out"]      # ghep cap: ra ngoai vung bam sat net doi tac thi dat hon
                if d != 8:
                    pd = self.DIRS[d]
                    dot = pd[0] * dx + pd[1] * dy
                    if (pd[0], pd[1]) != (dx, dy):
                        nrm = math.hypot(*pd) * math.hypot(dx, dy)
                        cosang = dot / nrm
                        c += COST["bend45"] if cosang > 0.5 else COST["bend90"]
                ns = l * N + jdx
                ng = gc + c
                k2 = (ns, di)
                if ng < gs.get(k2, 1e18) - 1e-12:
                    gs[k2] = ng
                    par[k2] = (s, d)
                    heapq.heappush(pq, (ng + h(jx, jy), ng, ns, di))
            # via
            if via_ok(l, idx, mv):
                ns = (1 - l) * N + idx
                ng = gc + self.cur_via_cost + (COST["via_in_pad"] if idx in padcells else 0.0)
                k2 = (ns, 8)
                if ng < gs.get(k2, 1e18) - 1e-12:
                    gs[k2] = ng
                    par[k2] = (s, d)
                    heapq.heappush(pq, (ng + h(ix, iy), ng, ns, 8))
        return None, exp

    # ---- route 1 net ------------------------------------------------------------------------
    def route(self, net, only_refs=None):
        g = self.g
        N = g.n
        clr, w, vd, vdr = nc(net)
        t0 = time.time()
        mt, mv = self.masks(net)
        self.cur_via_cost = self.via_cost_of.get(net, COST["via"])
        self.cur_bcu = COST["bcu_p12"] if net in self.via_cost_of else COST["bcu_mult"]
        pads = [p for p in self.pads if p["net"] == net]
        # gop pad trung vi tri (A4/B9...)
        uniq = {}
        for p in pads:
            uniq.setdefault((round(p["x"], 2), round(p["y"], 2)), p)
        pads = list(uniq.values())
        padcells = set()
        for p in self.pads:
            x0, y0, x1, y1 = p["rect"]
            ia, ja = g.cell(x0, y0); ib, jb = g.cell(x1, y1)
            for j in range(ja, jb + 1):
                for i in range(ia, ib + 1):
                    padcells.add(j * g.nx + i)

        def via_ok(l, idx, mv_):
            return not mv_[0][idx] and not mv_[1][idx]

        def pcells(p):
            ix, iy = g.cell(p["x"], p["y"])
            idx = iy * g.nx + ix
            return [l * N + idx for l in p["layers"]]

        res = {"net": net, "pads": len(pads), "tracks": 0, "vias": 0, "len": 0.0, "fail": []}
        new_items = []
        if net.endswith("GND"):
            # moi pad SMD GND -> via gan nhat (plane B.Cu). Pad THT cham plane truc tiep.
            todo = [p for p in pads if not p["tht"]]
            if only_refs is not None:                       # giai doan tu: chi pad GND cua tu decoupling, via <= GND_NEAR
                todo = [p for p in todo if p["ref"] in only_refs or f'{p["ref"]}.{p["num"]}' in only_refs]
            gvias = [it.data for it in self.items if it.kind == "circ" and it.net == net]
            for p in todo:
                if only_refs is None and any(math.hypot(v[0] - p["x"], v[1] - p["y"]) <= GND_NEAR + 0.2 for v in gvias):
                    continue                                 # da co via GND sat pad nay (tu giai doan tu)
                src = pcells(p)
                for s_ in src:
                    mt[s_ // N][s_ % N] = 0
                # dich phu: via GND co san (chi via: pad GND khac chua chac da xuong plane) -> chan IC khong co cho dat via van noi duoc vao tu ke ben
                ext = set()
                for v_ in gvias:
                    ix_, iy_ = g.cell(v_[0], v_[1]); ext.add(iy_ * g.nx + ix_)
                px_, py_ = p["x"], p["y"]
                near_ok = lambda l, idx: math.hypot(g.ox + (idx % g.nx) * RES - px_, g.oy + (idx // g.nx) * RES - py_) <= GND_NEAR
                # V1: via GND khong lan/sat pad (thiec chay xuong lo khi reflow). Canh via cach MOI pad SMD >= VIA_PAD_GAP
                def off_pads(idx, _r=self.cfg_via_r(net) if hasattr(self, "cfg_via_r") else 0.3):
                    cx_, cy_ = g.ox + (idx % g.nx) * RES, g.oy + (idx // g.nx) * RES
                    for q_ in self.pads:
                        if q_["tht"]: continue
                        x0_, y0_, x1_, y1_ = q_["rect"]
                        if math.hypot(max(x0_ - cx_, 0, cx_ - x1_), max(y0_ - cy_, 0, cy_ - y1_)) < _r + VIA_PAD_GAP:
                            return False
                    return True
                path, ex = self.astar(src, [], mt, mv, via_ok, padcells,
                                      goal_fn=lambda l, idx: l == 0 and ((via_ok(l, idx, mv) and idx not in padcells and near_ok(l, idx) and off_pads(idx)) or (idx in ext and off_pads(idx))))
                if not path:                                 # khong co cho trong <= GND_NEAR: cho phep xa hon
                    path, ex = self.astar(src, [], mt, mv, via_ok, padcells,
                                          goal_fn=lambda l, idx: l == 0 and via_ok(l, idx, mv) and idx not in padcells and off_pads(idx))
                if not path:
                    res["fail"].append(f'{p["ref"]}.{p["num"]}')
                    continue
                last = path[-1] % N
                ends_on_gnd = last in ext
                exy = None
                if ends_on_gnd and gvias:
                    lx_, ly_ = g.xy(last % g.nx, last // g.nx)
                    exy = min(((v_[0], v_[1]) for v_ in gvias), key=lambda q_: math.hypot(q_[0] - lx_, q_[1] - ly_))
                self._commit(path, net, w, vd, vdr, p, None, res, new_items, force_via_end=not ends_on_gnd, end_xy=exy)
                gvias.append((path and g.xy((path[-1] % N) % g.nx, (path[-1] % N) // g.nx)) + (0,))
            res["time"] = round(time.time() - t0, 1)
            if only_refs is None:
                self.virt.pop(net, None)
            return res
        # --- cap vi sai: net thu hai bam sat net thu nhat -----------------------------------------
        near = None
        partner = self.partner.get(net)
        if partner and self.segs.get(partner):
            near = [bytearray(g.n), bytearray(g.n)]
            for l, p1, p2, pw, _it in self.segs[partner]:
                g.seg(near[l], p1[0], p1[1], p2[0], p2[1], COUPLE_R)
        for p in pads:                                   # o cua chinh net: duoc phep di vao
            for s_ in pcells(p):
                mt[s_ // N][s_ % N] = 0
        groups = [{"pads": [p], "cells": set(pcells(p)), "pcells": set(pcells(p))} for p in pads]
        # pad da noi san bang dong co san (ve tay / buoc truoc) -> gop thanh 1 nhom, khong di them duong (L79)
        _cid = {}
        for i_ in range(len(groups)):
            k_ = self.preconn.get((groups[i_]["pads"][0]["ref"], groups[i_]["pads"][0]["num"]))
            if k_ is None:
                continue
            if k_ in _cid:
                ga_ = groups[_cid[k_]]
                if ga_ is not groups[i_]:
                    ga_["pads"] += groups[i_]["pads"]; ga_["cells"] |= groups[i_]["cells"]; ga_["pcells"] |= groups[i_]["pcells"]
                    groups[i_] = ga_
            else:
                _cid[k_] = i_
        bridge_mv = None
        # --- cau noi pad cung linh kien (vd 2 pad VBUS cua USB-C): tim kiem trong cua so hep ------
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                ga, gb = groups[i], groups[j]
                if ga is gb or not ga["cells"] or not gb["cells"]:
                    continue
                pa, pb = ga["pads"][0], gb["pads"][0]
                if pa["ref"] != pb["ref"] or math.hypot(pa["x"] - pb["x"], pa["y"] - pb["y"]) > BRIDGE_MAX:
                    continue
                cxs = [pa["x"], pb["x"]]; cys = [pa["y"], pb["y"]]
                i0, j0 = g.cell(min(cxs) - BRIDGE_MARGIN, min(cys) - BRIDGE_MARGIN)
                i1, j1 = g.cell(max(cxs) + BRIDGE_MARGIN, max(cys) + BRIDGE_MARGIN)
                if bridge_mv is None:
                    bmt, bridge_mv = self.masks(net, vd_override=BRIDGE_VIA[0])      # cau noi pad dung via nho nhat cho phep (pitch 0.5)
                    for p_ in pads:
                        for s_ in pcells(p_):
                            bmt[s_ // N][s_ % N] = 0
                # (a) thu truoc vong F.Cu quanh dau pad, KHONG via, rong 0.3 (ban ve cua owner); (b) khong duoc moi dung cau via
                mt_f, mv_f = masks_loop = self.masks(net, w_override=min(w, 0.2), clr_override=0.15)     # cau ngan: 0.2 mm / 0.15 mm (>=0.1 owner cho phep)
                for p_ in pads:
                    for s_ in pcells(p_):
                        mt_f[s_ // N][s_ % N] = 0
                path_f, _ex = self.astar(list(ga["cells"]), list(gb["cells"]), mt_f, mv_f, lambda l_, i_, m_: False, padcells,
                                         window=(max(0, i0), max(0, j0), min(g.nx - 1, i1), min(g.ny - 1, j1)), max_exp=400000)
                if path_f:
                    end_pad_f = pb if path_f[-1] in pcells(pb) else None
                    self._commit(path_f, net, min(w, 0.2), vd, vdr, None, end_pad_f, res, new_items, force_via_end=False)
                    res.setdefault("bridges", []).append(f'{pa["ref"]}.{pa["num"]}~{pb["ref"]}.{pb["num"]} (F.Cu, 0 via)')
                    ga["pads"] += gb["pads"]; ga["cells"] |= set(path_f) | gb["cells"]; ga["pcells"] |= gb["pcells"]
                    groups[j] = ga
                    continue
                keep_vc, self.cur_via_cost = self.cur_via_cost, COST["via"]      # cau noi pad: via la bat buoc, chi phi thuong
                path, ex = self.astar(list(ga["cells"]), list(gb["cells"]), bmt, bridge_mv, via_ok, padcells,
                                      window=(max(0, i0), max(0, j0), min(g.nx - 1, i1), min(g.ny - 1, j1)), max_exp=400000)
                self.cur_via_cost = keep_vc
                if not path:
                    continue
                end_pad = pb if path[-1] in pcells(pb) else None
                self._commit(path, net, w, BRIDGE_VIA[0], BRIDGE_VIA[1], None, end_pad, res, new_items, force_via_end=False)
                res.setdefault("bridges", []).append(f'{pa["ref"]}.{pa["num"]}~{pb["ref"]}.{pb["num"]}')
                ga["pads"] += gb["pads"]; ga["cells"] |= set(path) | gb["cells"]; ga["pcells"] |= gb["pcells"]   # pcells: chi pad -> loi ra PHAI xuat phat tu pad (khong tu doan vong cau F.Cu)
                if len({s_ // N for s_ in path}) > 1:
                    ga["pcells"] |= set(path)      # cau co via (B.Cu): via-in-pad la loi ra duy nhat (chot dinh vi chan loi F.Cu o pad VBUS)
                groups[j] = ga                                # gop nhom
        uniq_groups = []
        for gr in groups:
            if not any(gr is u for u in uniq_groups):
                uniq_groups.append(gr)
        # --- nhanh vao chan IC pitch min (TSSOP...): thu hep track (neck-down) xuong NECK_W, nhu v8 ("nhanh rieng 0.3 mm") ----
        def is_fine(gr):
            return any((not q["tht"]) and min(q["rect"][2] - q["rect"][0], q["rect"][3] - q["rect"][1]) <= FINE_PAD for q in gr["pads"])
        def pos_key(q):
            return (round(q["x"], 2), round(q["y"], 2))

        def group_of(q):
            return next((gr for gr in uniq_groups if any(pos_key(x) == pos_key(q) for x in gr["pads"])), None)

        chains = self.chains.get(net)
        mcache = {}

        def masks_wc(wd, clr_o=None):
            key = (wd, clr_o)
            if key not in mcache:
                if clr_o is None and wd == w:
                    mcache[key] = (mt, mv)
                else:
                    m1, m2 = self.masks(net, w_override=wd, clr_override=clr_o)
                    for p_ in pads:
                        for s_ in pcells(p_):
                            m1[s_ // N][s_ % N] = 0
                    mcache[key] = (m1, m2)
            return mcache[key]

        def masks_w(wd):
            return masks_wc(wd, None)

        def ladder(src_, goals_, wd, near_=None):
            """THANG NOI LONG (nguyen tac chung): chi chuyen lop khi da thu CUNG LOP voi cac noi long duoc phep.
            B1 cung lop, thong so lop net | B2 cung lop, rong<=0.2 & clearance 0.15 (owner: >=0.1 duoc) | B3 cho phep via."""
            steps = [(wd, None, True), (min(wd, 0.2), 0.15, True), (wd, None, False)]      # moi net (ke ca tin hieu cham): cung lop truoc, via sau cung
            for wsel, csel, novia in steps:
                m1, m2 = masks_wc(wsel, csel)
                for s_ in list(src_) + list(goals_):
                    m1[s_ // N][s_ % N] = 0
                pth, _e = self.astar(list(src_), list(goals_), m1, m2, (lambda l_, i_, m_: False) if novia else via_ok, padcells,
                                     near=near_, max_exp=250000 if novia else 2500000)
                if pth:
                    return pth, wsel
            return None, wd

        covered = set()
        if chains:
            # --- cay nguon CO THU TU (owner): chuoi pad theo luong dien, vd J1 -> TVS -> bulk -> tai; tu truoc, chan IC sau ----
            padmap = {f'{q["ref"]}.{q["num"]}': q for q in pads}
            padmap.update({f'{q["ref"]}.{q["num"]}': q for q in self.pads if q["net"] == net})
            g0 = group_of(padmap[chains[0]["from"]])
            tree = set(g0["pcells"])
            covered |= {pos_key(x) for x in g0["pads"]}
            trunk_cells = None
            for ch in chains:
                wc = ch.get("width", w)
                if ch["from"] == "tree":
                    src = list(tree)
                elif ch["from"] == "trunk":
                    src = list(trunk_cells) if trunk_cells else list(tree)      # nhanh chi re tu TRUNK (chuoi dau), khong tu pad tu/IC cua nhanh khac
                else:
                    gs_ = group_of(padmap[ch["from"]])
                    src = list(gs_["pcells"])
                    tree |= gs_["pcells"]
                    covered |= {pos_key(x) for x in gs_["pads"]}
                for name in ch["path"]:
                    tp = padmap[name]
                    tg = group_of(tp)
                    wd = min(wc, NECK_W) if is_fine(tg) else wc
                    goals = list(tg["pcells"])
                    path, wd = ladder(src, goals, wd)
                    if not path:
                        res["fail"].append(f'chuoi {ch["from"]}->{name}')
                        break
                    self._commit(path, net, wd, vd, vdr, None, tp, res, new_items, force_via_end=False)
                    tree |= set(path) | tg["pcells"]
                    covered |= {pos_key(x) for x in tg["pads"]}
                    src = list(tg["pcells"])             # hop tiep theo di TU pad nay (cau noi qua tu truoc khi toi chan IC)
                res.setdefault("chains", []).append(f'{ch["from"]}->' + "->".join(ch["path"]))
                if trunk_cells is None:
                    trunk_cells = set(tree)
            rest = [gr for gr in uniq_groups if not any(pos_key(x) in covered for x in gr["pads"])]
            normal = [gr for gr in rest if not is_fine(gr)]
            fine = [gr for gr in rest if is_fine(gr)]
            todo = [(gr, False) for gr in normal] + [(gr, True) for gr in fine]
        else:
            normal = [gr for gr in uniq_groups if not is_fine(gr)]
            fine = [gr for gr in uniq_groups if is_fine(gr)]
            start = normal[0] if normal else fine[0]
            tree = set(start["pcells"])
            if net in self.src_pad:
                sp_ = next((q for q in pads if f'{q["ref"]}.{q["num"]}' == self.src_pad[net]), None)
                if sp_ is not None:
                    start = group_of(sp_) or start        # bat dau tu nhom chua pad thoat da chon
                    tree = set(pcells(sp_))
            todo = [(gr, False) for gr in normal if gr is not start] + [(gr, True) for gr in fine if gr is not start]
        mt_n = mv_n = None
        w_n = min(w, NECK_W)
        pending = [t for t in todo if not t[1]]
        pending_fine = [t for t in todo if t[1]]
        for phase_fine, rem in ((False, pending), (True, pending_fine)):
            remaining = [gr for gr, _f in rem]
            if phase_fine and remaining and w_n < w and mt_n is None:
                mt_n, mv_n = self.masks(net, w_override=w_n)
                for p in pads:
                    for s_ in pcells(p):
                        mt_n[s_ // N][s_ % N] = 0
            mt_use, mv_use, w_use = (mt_n, mv_n, w_n) if (phase_fine and mt_n is not None) else (mt, mv, w)
            while remaining:
                goals = [c for gr in remaining for c in gr["pcells"]]
                for s_ in list(tree) + goals:
                    mt_use[s_ // N][s_ % N] = 0
                path, w_use = ladder(list(tree), goals, w_use, near)
                if not path:
                    res["fail"].append(",".join(f'{q["ref"]}.{q["num"]}' for gr in remaining for q in gr["pads"]))
                    break
                end = path[-1]
                hit = next(gr for gr in remaining if end in gr["pcells"])
                end_pad = next((q for q in hit["pads"] if end in pcells(q)), None)
                self._commit(path, net, w_use, vd, vdr, None, end_pad, res, new_items, force_via_end=False)
                tree |= set(path) | hit["pcells"]
                remaining = [gr for gr in remaining if gr is not hit]
        res["time"] = round(time.time() - t0, 1)
        self.virt.pop(net, None)
        return res

    def route_ties(self, net, ties):
        """Noi them tren F.Cu cac cap pad cung net (vd GND chan IC <-> pad GND tu ke ben): khong phu thuoc plane khi plane bi cat thanh dao."""
        g = self.g; N = g.n
        clr, w, vd, vdr = nc(net)
        mt, mv = self.masks(net)
        res = {"net": net, "pads": 0, "tracks": 0, "vias": 0, "len": 0.0, "fail": [], "time": 0.0}
        padmap = {f'{q["ref"]}.{q["num"]}': q for q in self.pads if q["net"] == net}
        for a_, b_ in ties:
            pa, pb = padmap[a_], padmap[b_]
            ca = [g.cell(pa["x"], pa["y"])]; cb = [g.cell(pb["x"], pb["y"])]
            sa = [c[1] * g.nx + c[0] for c in ca]; sb = [c[1] * g.nx + c[0] for c in cb]
            for s_ in sa + sb:
                mt[0][s_] = 0
            path, ex = self.astar(sa, sb, mt, mv, lambda l_, i_, m_: False, set(), max_exp=300000)
            if not path:
                res["fail"].append(f"{a_}~{b_}")
                continue
            self._commit(path, net, w, vd, vdr, pa, pb, res, [], force_via_end=False)
        return res

    def finalize(self):
        """Ghi tat ca track/via da route vao board (goi 1 lan, sau khi tune)."""
        b = self.b
        for net, lst in self.segs.items():
            ni = b.FindNet(net)
            for l, a, c, w, _it in lst:
                t = pcbnew.PCB_TRACK(b)
                t.SetLayer(pcbnew.F_Cu if l == 0 else pcbnew.B_Cu)
                t.SetStart(VECTOR2I(FromMM(a[0]), FromMM(a[1])))
                t.SetEnd(VECTOR2I(FromMM(c[0]), FromMM(c[1])))
                t.SetWidth(FromMM(w))
                t.SetNet(ni)
                b.Add(t)
        for net, p, vd, vdr in self.out_vias:
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(VECTOR2I(FromMM(p[0]), FromMM(p[1])))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetDrill(FromMM(vdr)); v.SetWidth(FromMM(vd)); v.SetNet(b.FindNet(net))
            b.Add(v)

    def net_len(self, net):
        return sum(math.hypot(c[0] - a[0], c[1] - a[1]) for _l, a, c, _w, _it in self.segs.get(net, []))

    def tune_length(self, net, delta, tol=0.3):
        """Them `delta` mm vao net bang khuc uon chu nhat (bump) tren cac doan thang F.Cu dai nhat.
        Moi bump: chieu cao h -> them 2h. Chi nhan neu moi o doc theo bump con trong (mat na vat can cua net)."""
        g = self.g
        mt, _mv = self.masks(net)
        for p in self.pads:
            if p["net"] == net:
                for l in p["layers"]:
                    self._clear_rect(mt[l], *p["rect"], net)
        w = nc(net)[1]
        BW = 0.6                                 # khoang cach 2 chan bump (>= clr + 2*w)
        added = 0.0
        tried = set()
        while delta - added > tol:
            cands = sorted([e for e in self.segs[net] if e[0] == 0 and id(e[4]) not in tried],
                           key=lambda e: -math.hypot(e[2][0] - e[1][0], e[2][1] - e[1][1]))
            if not cands:
                break
            e = cands[0]
            tried.add(id(e[4]))
            l, A, B, ew, it = e
            L = math.hypot(B[0] - A[0], B[1] - A[1])
            if L < BW + 1.0:
                continue
            ux, uy = (B[0] - A[0]) / L, (B[1] - A[1]) / L
            nx_, ny_ = -uy, ux
            rem = delta - added
            done = False
            for side in (1, -1):
                h = min(rem / 2, 3.0)
                while h >= 0.4 and not done:
                    c0 = L / 2 - BW / 2
                    P = [A, (A[0] + ux * c0, A[1] + uy * c0),
                         (A[0] + ux * c0 + side * nx_ * h, A[1] + uy * c0 + side * ny_ * h),
                         (A[0] + ux * (c0 + BW) + side * nx_ * h, A[1] + uy * (c0 + BW) + side * ny_ * h),
                         (A[0] + ux * (c0 + BW), A[1] + uy * (c0 + BW)), B]
                    ok = True
                    for k in range(len(P) - 1):
                        d = math.hypot(P[k + 1][0] - P[k][0], P[k + 1][1] - P[k][1])
                        n = max(1, int(d / (RES * 0.5)))
                        for t_ in range(n + 1):
                            x = P[k][0] + (P[k + 1][0] - P[k][0]) * t_ / n
                            y = P[k][1] + (P[k + 1][1] - P[k][1]) * t_ / n
                            ix, iy = g.cell(x, y)
                            if not (0 <= ix < g.nx and 0 <= iy < g.ny) or mt[0][iy * g.nx + ix]:
                                ok = False
                                break
                        if not ok:
                            break
                    if ok:
                        # khong sat qua cac doan khac cua chinh net (tru doan bi thay)
                        for e2 in self.segs[net]:
                            if e2 is e or e2[0] != 0:
                                continue
                            for q in P[2:4]:
                                if _pt_seg_dist(q, e2[1], e2[2]) < 0.45 and not (math.hypot(q[0]-A[0], q[1]-A[1]) < 0.5 or math.hypot(q[0]-B[0], q[1]-B[1]) < 0.5):
                                    ok = False
                    if ok:
                        self.segs[net].remove(e)
                        self.items.remove(it)
                        for k in range(len(P) - 1):
                            it2 = Item("seg", (P[k][0], P[k][1], P[k + 1][0], P[k + 1][1], w / 2), {0}, net)
                            self.items.append(it2)
                            self.segs[net].append((0, P[k], P[k + 1], w, it2))
                        added += 2 * h
                        done = True
                        break
                    h -= 0.2
                if done:
                    break
        return added

    def _commit(self, path, net, w, vd, vdr, start_pad, end_pad, res, new_items, force_via_end, end_xy=None):
        g, b, N = self.g, self.b, self.g.n

        def pos(s):
            l, idx = divmod(s, N)
            return l, g.xy(idx % g.nx, idx // g.nx)
        pts = [pos(s) for s in path]
        # tach thanh run cung lop, cung huong
        i = 0
        net_item = self.b.FindNet(net)
        def add_track(l, a, c):
            if math.hypot(c[0] - a[0], c[1] - a[1]) < 1e-6:
                return
            it = Item("seg", (a[0], a[1], c[0], c[1], w / 2), {l}, net)
            self.items.append(it)
            self.segs.setdefault(net, []).append((l, a, c, w, it))     # tao PCB_TRACK luc finalize() de con sua (tune do dai)
            res["tracks"] += 1
            res["len"] += math.hypot(c[0] - a[0], c[1] - a[1])
        def add_via(p):
            self.out_vias.append((net, p, vd, vdr))
            self.items.append(Item("circ", (p[0], p[1], vd / 2), {0, 1}, net, VIA_EXTRA, GND_VIA_B_EXTRA if net.endswith("GND") else 0.0))
            res["vias"] += 1
        # pad -> diem dau chinh xac
        if start_pad is not None:
            pts[0] = (pts[0][0], (start_pad["x"], start_pad["y"]))
            seg_start = (pts[0][0], pts[0][1])
        if end_pad is not None:
            pts[-1] = (pts[-1][0], (end_pad["x"], end_pad["y"]))
        if end_xy is not None:                      # ket thuc tren via co san: bam dung tam via (khong de ho 0.0x mm do lam tron luoi)
            pts[-1] = (pts[-1][0], end_xy)
        run_l, run_pts = pts[0][0], [pts[0][1]]
        def flush(l, rp):
            if len(rp) < 2:
                return
            a, prev_dir = rp[0], None
            for k in range(1, len(rp)):
                dx, dy = rp[k][0] - rp[k - 1][0], rp[k][1] - rp[k - 1][1]
                dirk = (round(math.copysign(1, dx)) if abs(dx) > 1e-6 else 0, round(math.copysign(1, dy)) if abs(dy) > 1e-6 else 0)
                if prev_dir is not None and dirk != prev_dir:
                    add_track(l, a, rp[k - 1])
                    a = rp[k - 1]
                prev_dir = dirk
            add_track(l, a, rp[-1])
        for (l, p) in pts[1:]:
            if l != run_l:
                flush(run_l, run_pts)
                add_via(run_pts[-1])
                run_l, run_pts = l, [run_pts[-1]]
            else:
                run_pts.append(p)
        flush(run_l, run_pts)
        if force_via_end:
            # GND: ket thuc la mot via tren F.Cu noi voi plane B.Cu
            add_via(run_pts[-1])


def main():
    inp, outp = sys.argv[1], sys.argv[2]
    load_config(inp, sys.argv[sys.argv.index("--pro") + 1] if "--pro" in sys.argv else None)
    global SKEW_TARGET
    if "--match-skew" in sys.argv:
        SKEW_TARGET = float(sys.argv[sys.argv.index("--match-skew") + 1])
    b = pcbnew.LoadBoard(inp)
    r = Router(b)
    t0 = time.time()
    if "--order" in sys.argv:
        plan = [n for n in sys.argv[sys.argv.index("--order") + 1].split(",") if n]   # bo ten rong = pad NC
        known = {p_["net"] for p_ in r.pads}
        bad = [n for n in plan if n.replace("@caps", "").replace("@ties", "") not in known]
        if bad:
            sys.exit(f"net khong ton tai: {bad}. Luu y: Git Bash doi '/NET' thanh duong dan -> dat MSYS_NO_PATHCONV=1. Net co: {sorted(known)[:12]}...")
    else:
        plan = auto_plan(r.pads)
    for n in plan:
        bn = n.split("/")[-1].upper()
        for neg, pos in (("DM", "DP"), ("DN", "DP"), ("D-", "D+")):
            if bn.endswith(neg):
                cand = n[: len(n) - len(neg)] + pos if n.upper().endswith(neg) else None
                for q in plan:
                    if cand and q.upper() == cand.upper():
                        r.partner[n] = q
    if "--src-pad" in sys.argv:
        for kv in sys.argv[sys.argv.index("--src-pad") + 1].split(","):
            k_, v_ = kv.split("=")
            r.src_pad[k_] = v_
    print("PLAN:", plan, "| cap vi sai:", r.partner, "| pad thoat:", r.src_pad)
    if "--lowprio" in sys.argv:       # net uu tien thap (vd CC): khong giu loi thoat; route SAU net quan trong hon
        for n_ in sys.argv[sys.argv.index("--lowprio") + 1].split(","):
            r.virt.pop(n_, None)
    # P1/P2 (USB, CC, nguon, LED, decap, gate): via la phuong an cuoi cung; tin hieu cham (P3) duoc nhay B.Cu ngan
    slow = {n for n in plan if n.split("/")[-1].upper() in ("SWIM", "NRST") or "PWM" in n.upper() or "UART" in n.upper()}
    for n in plan:
        if n != "GND" and not n.endswith("GND") and n not in slow:
            r.via_cost_of[n] = COST["via_p12"]
            r.block_ic.add(n)
    sys.stdout.flush()
    allres = []
    intent_caps = None
    if "--intent" in sys.argv:
        import json as _j
        _intent = _j.load(open(sys.argv[sys.argv.index("--intent") + 1], encoding="utf-8"))
        r.chains = _intent.get("power_chains", {})
        r.gnd_ties = _intent.get("gnd_ties", [])
        _dec = _intent.get("decoupling", [])
        intent_caps = {d_["cap"] for d_ in _dec} | {d_["gnd_pin"] for d_ in _dec}      # tu + chan GND cua IC duoc decouple (U1.7, U2.1)
    for net in plan:
        if net.endswith("@ties"):
            res = r.route_ties(net[:-5], r.gnd_ties)
            net = net[:-5] + "@ties"
        elif net.endswith("@caps"):
            res = r.route(net[:-5], only_refs=intent_caps)
            net = net[:-5] + "@caps"
        else:
            res = r.route(net)
        allres.append(res)
        status = "OK " if not res["fail"] else "FAIL"
        print(f'{status} {net:9s} pads={res["pads"]:2d} len={res["len"]:6.1f} mm vias={res["vias"]} t={res["time"]}s' +
              (f' unrouted={res["fail"]}' if res["fail"] else ""))
        if net in r.partner:
            la, lb = r.net_len(net), r.net_len(r.partner[net])
            print(f"     CAP {r.partner[net]} / {net}: {lb:.2f} / {la:.2f} mm  -> LECH {abs(la - lb):.2f} mm")
            if SKEW_TARGET is not None and abs(la - lb) > SKEW_TARGET and not res["fail"]:     # USB FS: khong chinh do dai (chi bao); --match-skew X cho USB HS
                short = net if la < lb else r.partner[net]
                got = r.tune_length(short, abs(la - lb) - 0.2)
                la, lb = r.net_len(net), r.net_len(r.partner[net])
                print(f"     TUNE {short}: them {got:.2f} mm -> {r.partner[net]} {lb:.2f} / {net} {la:.2f} mm  -> LECH {abs(la - lb):.2f} mm")
        if res.get("bridges"):
            print("     cau noi pad:", res["bridges"])
        sys.stdout.flush()
    r.finalize()
    b.Save(outp)
    print("saved", outp, "total", round(time.time() - t0, 1), "s")


main()
