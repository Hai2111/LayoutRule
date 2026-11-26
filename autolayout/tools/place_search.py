"""place_search.py - tim kiem bo tri (xoay + dich) bang tinh toan, TRUOC khi route that.
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" place_search.py BASE.kicad_pcb OUT_DIR [iters=30000] [seeds=8] [topk=5]

Y tuong: nguoi thiet ke 'nhin' duoc chuyen cac net CAT NHAU, chan nao doi dien chan nao, tu nam ben nao. Do la tinh duoc nhanh:
  chi phi = so lan cat nhau giua cac ratsnest (cay khung MST moi net, bo GND vi co plane)  [trong so cao cho USB, nguon]
          + chieu dai tong (HPWL nho) + tu decoupling xa chan IC + chan loi thoat chan IC bi linh kien chan.
Rang buoc cung: courtyard khong de len nhau, trong board, khong dung vung than connector/neo co khi.
SA (simulated annealing) chay song song nhieu seed; xuat top-k bo tri khac nhau -> route that + DRC + xem anh.
Linh kien duoc phep dich: MOVABLE (nhom U2+C1+C2 dich cung nhau; con lai di chuyen rieng le). Neo (J1..J4, U1, C5, D1) co dinh.
"""
import itertools
import json
import math
import multiprocessing as mp
import os
import random
import sys

import pcbnew
from pcbnew import FromMM, VECTOR2I

FIXED = {"J1", "J2", "J3", "J4", "U1", "C5", "D1"}
GROUPS = [["U2", "C1", "C2"]]            # dich cung nhau (tu decoupling di theo chan cua no)
SKIP_NETS = ("GND",)                       # plane
W_CROSS = {"usb": 3.0, "pwr": 1.5, "sig": 1.0}


def box(bb):
    return (bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6)


def load(path):
    b = pcbnew.LoadBoard(path)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    bb = box(b.GetBoardEdgesBoundingBox())
    data = {}
    for ref, f in fps.items():
        p0 = f.GetPosition(); rot0 = f.GetOrientationDegrees()
        info = {"pos": (p0.x / 1e6, p0.y / 1e6), "rot": int(round(rot0)) % 360, "off": {}}
        for r in (0, 90, 180, 270):
            f.SetOrientationDegrees(r)
            pads = []
            for pd in f.Pads():
                pp = pd.GetPosition(); bx = box(pd.GetBoundingBox())
                pads.append((pd.GetNetname(), pp.x / 1e6 - p0.x / 1e6, pp.y / 1e6 - p0.y / 1e6, (bx[2] - bx[0]) / 2, (bx[3] - bx[1]) / 2, pd.GetNumber()))
            try:
                poly = f.GetCourtyard(pcbnew.F_CrtYd)
                cy = box(poly.BBox()) if poly.OutlineCount() > 0 else None
            except Exception:
                cy = None
            if cy is None:
                xs = [(q[1] - q[3] - .25, q[2] - q[4] - .25, q[1] + q[3] + .25, q[2] + q[4] + .25) for q in pads]
                cy = (min(x[0] for x in xs) + p0.x / 1e6, min(x[1] for x in xs) + p0.y / 1e6, max(x[2] for x in xs) + p0.x / 1e6, max(x[3] for x in xs) + p0.y / 1e6)
            info["off"][r] = {"pads": pads, "cy": (cy[0] - p0.x / 1e6, cy[1] - p0.y / 1e6, cy[2] - p0.x / 1e6, cy[3] - p0.y / 1e6)}
        f.SetOrientationDegrees(rot0)
        data[ref] = info
    return b, fps, data, bb


def netclass(n):
    u = n.upper().split("/")[-1]
    if any(k in u for k in ("USB", "DP", "DM", "DN")) and "UP" not in u:
        return "usb"
    if u in ("+5V", "VBUS", "+3V3", "V3", "VCAP") or u.startswith(("LED",)):
        return "pwr"
    return "sig"


def seg_cross(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    d1, d2, d3, d4 = o(a, b, c), o(a, b, d), o(c, d, a), o(c, d, b)
    return d1 * d2 < -1e-9 and d3 * d4 < -1e-9


def mst(pts):
    n = len(pts)
    if n < 2:
        return []
    inT = [False] * n; best = [1e9] * n; par = [-1] * n; best[0] = 0; edges = []
    for _ in range(n):
        u = min((i for i in range(n) if not inT[i]), key=lambda i: best[i]); inT[u] = True
        if par[u] >= 0:
            edges.append((pts[par[u]], pts[u]))
        for v in range(n):
            if not inT[v]:
                d = math.hypot(pts[u][0] - pts[v][0], pts[u][1] - pts[v][1])
                if d < best[v]:
                    best[v], par[v] = d, u
    return edges


class Model:
    def __init__(self, data, bb, decap, prox=()):
        self.data, self.bb, self.decap, self.prox = data, bb, decap, prox
        self.refs = list(data)
        self.movable = [r for r in self.refs if r not in FIXED]

    def placed(self, st):
        out = {}
        for r in self.refs:
            x, y, rot = st[r]
            o = self.data[r]["off"][rot]
            cy = o["cy"]
            out[r] = (x, y, rot, [(n, x + dx, y + dy, hw, hh, num) for (n, dx, dy, hw, hh, num) in o["pads"]], (x + cy[0], y + cy[1], x + cy[2], y + cy[3]))
        return out

    def legal(self, pl):
        bb = self.bb
        cs = [(r, pl[r][4]) for r in self.refs]
        for r, c in cs:
            if r in FIXED:
                continue
            if c[0] < bb[0] + 0.5 or c[1] < bb[1] + 0.5 or c[2] > bb[2] - 0.5 or c[3] > bb[3] - 0.5:
                return False
        for (r1, a), (r2, b) in itertools.combinations(cs, 2):
            if r1 in FIXED and r2 in FIXED:
                continue
            ox = min(a[2], b[2]) - max(a[0], b[0]); oy = min(a[3], b[3]) - max(a[1], b[1])
            if ox > 0.12 and oy > 0.12:          # courtyard cham nhau < 0.12 mm van duoc (v8 goc cung vay; DRC KiCad xac nhan sau)
                return False
        return True

    def cost(self, st):
        pl = self.placed(st)
        if not self.legal(pl):
            return None
        nets = {}
        for r, (x, y, rot, pads, cy) in pl.items():
            for (n, px, py, hw, hh, num) in pads:
                if n and n not in SKIP_NETS and not n.startswith("unconnected"):
                    nets.setdefault(n, []).append((px, py))
        edges = []
        hp = 0.0
        for n, pts in nets.items():
            if len(pts) < 2:
                continue
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            hp += (max(xs) - min(xs)) + (max(ys) - min(ys))
            for a, b in mst(pts):
                edges.append((n, a, b))
        cross = 0.0
        for (n1, a, b), (n2, c, d) in itertools.combinations(edges, 2):
            if n1 == n2:
                continue
            if seg_cross(a, b, c, d):
                k1, k2 = netclass(n1), netclass(n2)
                cross += max(W_CROSS[k1], W_CROSS[k2])
        dec = 0.0
        for cap, (ic, pin) in self.decap.items():
            cp = [p for p in pl[cap][3] if p[0] == pl[ic][3][0][0] or True]
            # pad nguon cua tu = pad co net trung net chan IC
            icp = next(p for p in pl[ic][3] if p[5] == pin)
            capp = [p for p in pl[cap][3] if p[0] == icp[0]]
            if capp:
                d = math.hypot(capp[0][1] - icp[1], capp[0][2] - icp[2])
                dec += max(0.0, d - 2.0) * 3
        pr = 0.0
        for (a_, b_, tgt) in self.prox:       # cap pad can o gan nhau (CC<->connector, TVS, cong gate...): intent 'proximity'
            try:
                pa = next(q for q in pl[a_.split('.')[0]][3] if q[5] == a_.split('.')[1]); pb = next(q for q in pl[b_.split('.')[0]][3] if q[5] == b_.split('.')[1])
            except StopIteration:
                continue
            pr += max(0.0, math.hypot(pa[1] - pb[1], pa[2] - pb[2]) - tgt) * 2.0
        # loi thoat: stub 1.2 mm cua chan IC (pad dai) khong bi linh kien khac chan
        esc = 0.0
        for r in ("U1", "U2"):
            x, y, rot, pads, cy = pl[r]
            for (n, px, py, hw, hh, num) in pads:
                if not n or n in SKIP_NETS and False:
                    continue
                if hw >= 1.6 * hh:
                    sg = 1 if px > x else -1; st_ = (min(px, px + sg * 1.2), py - .2, max(px, px + sg * 1.2), py + .2)
                elif hh >= 1.6 * hw:
                    sg = 1 if py > y else -1; st_ = (px - .2, min(py, py + sg * 1.2), px + .2, max(py, py + sg * 1.2))
                else:
                    continue
                for r2, (x2, y2, rot2, pads2, cy2) in pl.items():
                    if r2 == r or any(q[0] == n for q in pads2):
                        continue
                    if not (st_[2] <= cy2[0] or cy2[2] <= st_[0] or st_[3] <= cy2[1] or cy2[3] <= st_[1]):
                        esc += 1.0
        return cross * 3.0 + 0.05 * hp + dec + esc * 2.0 + pr


def run_seed(args):
    seed, path, iters = args
    random.seed(seed)
    b, fps, data, bb = load(path)
    _ip = os.path.join(os.path.dirname(path), "intent_500mA.json")
    intent = json.load(open(_ip, encoding="utf-8")) if os.path.exists(_ip) else {"decoupling": []}
    decap = {d["cap"]: tuple(d["pin"].split(".")) for d in intent.get("decoupling", [])}
    prox = [(d["a"], d["b"], d.get("target_mm", 5.0)) for d in intent.get("proximity", [])]
    m = Model(data, bb, decap, prox)
    st = {r: (data[r]["pos"][0], data[r]["pos"][1], data[r]["rot"]) for r in m.refs}
    cur = m.cost(st)
    if cur is None:
        return (1e9, st)
    best, bst = cur, dict(st)
    T0, T1 = 3.0, 0.05
    for it in range(iters):
        T = T0 * (T1 / T0) ** (it / iters)
        new = dict(st)
        grp = random.random() < 0.25
        if grp:
            g = GROUPS[0]
            dx, dy = random.choice([-3, -2, -1, -0.5, 0.5, 1, 2, 3]) * random.random(), random.choice([-3, -2, -1, -0.5, 0.5, 1, 2, 3]) * random.random()
            for r in g:
                x, y, rot = st[r]; new[r] = (x + dx, y + dy, rot)
        else:
            r = random.choice(m.movable)
            x, y, rot = st[r]
            if random.random() < 0.3:
                rot = random.choice([0, 90, 180, 270])
            else:
                x += random.uniform(-2.5, 2.5); y += random.uniform(-2.5, 2.5)
            new[r] = (round(x * 4) / 4, round(y * 4) / 4, rot)
        c = m.cost(new)
        if c is None:
            continue
        if c < cur or random.random() < math.exp((cur - c) / T):
            st, cur = new, c
            if cur < best:
                best, bst = cur, dict(st)
    return (best, bst)


def main():
    base, out = sys.argv[1], sys.argv[2]
    iters = int(sys.argv[3]) if len(sys.argv) > 3 else 30000
    seeds = int(sys.argv[4]) if len(sys.argv) > 4 else 8
    topk = int(sys.argv[5]) if len(sys.argv) > 5 else 5
    os.makedirs(out, exist_ok=True)
    # chi phi goc
    b, fps, data, bb = load(base)
    intent_p = os.path.join(os.path.dirname(os.path.abspath(base)), "intent_500mA.json")
    intent = json.load(open(intent_p, encoding="utf-8")) if os.path.exists(intent_p) else {"decoupling": []}
    decap = {d["cap"]: tuple(d["pin"].split(".")) for d in intent.get("decoupling", [])}
    prox = [(d["a"], d["b"], d.get("target_mm", 5.0)) for d in intent.get("proximity", [])]
    m = Model(data, bb, decap, prox)
    st0 = {r: (data[r]["pos"][0], data[r]["pos"][1], data[r]["rot"]) for r in m.refs}
    c0 = m.cost(st0)
    print("chi phi bo tri hien tai:", None if c0 is None else round(c0, 2))
    with mp.Pool(min(seeds, mp.cpu_count())) as pool:
        res = pool.map(run_seed, [(s, os.path.abspath(base), iters) for s in range(seeds)])
    res.sort(key=lambda t: t[0])
    chosen, sigs = [], set()
    for c, st in res:
        sig = tuple((r, round(st[r][0], 1), round(st[r][1], 1), st[r][2]) for r in m.movable)
        if sig in sigs:
            continue
        sigs.add(sig); chosen.append((c, st))
        if len(chosen) >= topk:
            break
    for i, (c, st) in enumerate(chosen):
        d = os.path.join(out, f"s{i+1}"); os.makedirs(d, exist_ok=True)
        bb2 = pcbnew.LoadBoard(base)
        for f in bb2.GetFootprints():
            r = f.GetReference()
            if r in st and r not in FIXED:
                x, y, rot = st[r]
                f.SetOrientationDegrees(rot); f.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
        bb2.Save(os.path.join(d, "place.kicad_pcb"))
        os.system(f'copy /Y "{os.path.join(os.path.dirname(os.path.abspath(base)), "stm8_place.kicad_pro")}" "{os.path.join(d, "place.kicad_pro")}" >nul')
        moved = {r: (round(st[r][0], 2), round(st[r][1], 2), st[r][2]) for r in m.movable if (round(st[r][0], 2), round(st[r][1], 2), st[r][2]) != (round(st0[r][0], 2), round(st0[r][1], 2), st0[r][2])}
        print(f"s{i+1} chi phi {c:.2f}  doi: {moved}")
        json.dump({r: list(v) for r, v in moved.items()}, open(os.path.join(d, "moved.json"), "w"))


if __name__ == "__main__":
    main()
