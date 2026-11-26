"""place_caps.py - dat lai tu decoupling sat chan IC (giai doan 'sap dat tu', sau khi nguon da thong).
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" place_caps.py PLACE.kicad_pcb INTENT.json OUT.kicad_pcb [OBSTACLE_ROUTED.kicad_pcb]

Voi moi muc intent["decoupling"] = {pin: "U1.9", cap: "C3", gnd_pin: "U1.7"}:
  - thu cac vi tri luoi 0.25 mm quanh chan IC (ban kinh R) x 4 huong xoay;
  - loai vi tri: de len linh kien khac (bbox pad + khe), ra sat mep board, de len track USB/via da route (OBSTACLE_ROUTED);
  - diem = khoang cach pad nguon cua tu -> chan nguon IC  +  0.3 * khoang cach pad GND cua tu -> chan GND IC
  - chi doi vi tri khi diem tot hon ro ret (>= 0.3 mm). Tu doi khong tu cham 'dat': ket qua van phai route + DRC.
Luat tham chieu: D-DECAP (target <= 2.0 mm pad-to-pin, review 4.0; GND pad toi via/chan GND <= 1.5).
"""
import json
import math
import sys

import pcbnew
from pcbnew import FromMM, VECTOR2I

STEP = 0.25
RADIUS = 4.5
GAP = 0.1             # khe toi thieu giua COURTYARD cac linh kien (courtyard da gom bien an toan)
VIA_SITE_DIST = 0.9   # via GND cua tu phai co cho trong trong ban kinh nay quanh pad GND
EDGE = 0.8            # cach mep board toi thieu
TRACK_CLR = 0.35      # khoang cach pad tu -> track/via da co (clearance 0.15..0.2 + nua be rong + du)
MIN_GAIN = 0.3


def box(bb):
    v = (bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6)
    if any(abs(x) > 1e4 for x in v):
        raise RuntimeError("swig rac")
    return v


def pt(p):
    return (p.x / 1e6, p.y / 1e6)


def court(f):
    """bbox courtyard that (F.CrtYd); khong co thi dung bbox pad + 0.25."""
    try:
        poly = f.GetCourtyard(pcbnew.F_CrtYd)
        if poly.OutlineCount() > 0:
            return box(poly.BBox())
    except Exception:
        pass
    u = union([box(p.GetBoundingBox()) for p in f.Pads()])
    return (u[0] - 0.25, u[1] - 0.25, u[2] + 0.25, u[3] + 0.25)


def pad_boxes(f):
    return [box(p.GetBoundingBox()) for p in f.Pads()]


def union(bs):
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))


def overlap(a, b, gap):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def seg_rect_dist(a, c, r):
    """khoang cach nho nhat tu doan a-c toi hinh chu nhat r (lay mau)."""
    L = math.hypot(c[0] - a[0], c[1] - a[1])
    n = max(1, int(L / 0.1))
    best = 1e9
    for i in range(n + 1):
        x = a[0] + (c[0] - a[0]) * i / n
        y = a[1] + (c[1] - a[1]) * i / n
        dx = max(r[0] - x, 0, x - r[2])
        dy = max(r[1] - y, 0, y - r[3])
        best = min(best, math.hypot(dx, dy))
    return best


def main():
    place, intent_p, out = sys.argv[1], sys.argv[2], sys.argv[3]
    routed = sys.argv[4] if len(sys.argv) > 4 else None
    intent = json.load(open(intent_p, encoding="utf-8"))
    b = pcbnew.LoadBoard(place)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    bb = box(b.GetBoardEdgesBoundingBox())

    # vat can da route (chi nhung net se KHONG bi route lai: truyen file da route chi chua USB)
    obs_seg, obs_via = [], []
    if routed:
        br = pcbnew.LoadBoard(routed)
        for t in br.GetTracks():
            if t.GetClass() == "PCB_VIA":
                obs_via.append((pt(t.GetPosition()), t.GetWidth(pcbnew.F_Cu) / 2e6))
            else:
                obs_seg.append((pt(t.GetStart()), pt(t.GetEnd()), t.GetWidth() / 2e6))

    def pad_of(f, net_or_num, by_net=True):
        for p in f.Pads():
            if (by_net and p.GetNetname() == net_or_num) or (not by_net and p.GetNumber() == net_or_num):
                return p
        return None

    report = []
    for d in intent.get("decoupling", []):
        if d.get("fixed"):
            continue                 # owner/intent: giu nguyen vi tri (vd tu da toi uu bang tay o v8)
        avoid = [tuple(r_) for r_ in d.get("avoid", [])]   # vung can bo trong (vd hanh lang USB vao chan IC)
        ic_ref, ic_pin = d["pin"].split(".")
        cap_ref = d["cap"]
        gnd_ref, gnd_pin = d["gnd_pin"].split(".")
        ic, cap = fps[ic_ref], fps[cap_ref]
        P = pad_of(ic, ic_pin, by_net=False)
        G = pad_of(fps[gnd_ref], gnd_pin, by_net=False)
        net_p = P.GetNetname()
        pp = pt(P.GetPosition()); gp = pt(G.GetPosition())
        cx0, cy0 = pt(cap.GetPosition()); rot0 = cap.GetOrientationDegrees()

        def metrics():
            cp = pad_of(cap, net_p); cg = [p for p in cap.Pads() if p is not cp][0]
            a = pt(cp.GetPosition()); g_ = pt(cg.GetPosition())
            return math.hypot(a[0] - pp[0], a[1] - pp[1]), math.hypot(g_[0] - gp[0], g_[1] - gp[1])

        d0 = metrics()
        s0 = d0[0] + 0.3 * d0[1]
        cb0 = court(cap)
        must_move = any(overlap(cb0, a_, 0.0) for a_ in avoid)
        # loi thoat (stub 1.2 mm) cua cac chan IC KHAC net voi tu: tu khong duoc chan (bai hoc U1.7)
        cap_nets = {pp_.GetNetname() for pp_ in cap.Pads()}
        stubs = []
        for r_, f_ in fps.items():
            if r_ == cap_ref:
                continue
            for q_ in f_.Pads():
                if not q_.GetNetname() or q_.GetNetname() in cap_nets:
                    continue
                bq = box(q_.GetBoundingBox()); wq, hq = bq[2] - bq[0], bq[3] - bq[1]
                cxq, cyq = (bq[0] + bq[2]) / 2, (bq[1] + bq[3]) / 2
                fx_, fy_ = pt(f_.GetPosition())
                if hq >= 1.6 * wq:
                    sg = 1 if cyq > fy_ else -1; stubs.append((cxq - 0.2, min(cyq, cyq + sg * 1.2), cxq + 0.2, max(cyq, cyq + sg * 1.2)))
                elif wq >= 1.6 * hq:
                    sg = 1 if cxq > fx_ else -1; stubs.append((min(cxq, cxq + sg * 1.2), cyq - 0.2, max(cxq, cxq + sg * 1.2), cyq + 0.2))
        others = [(r, court(f)) for r, f in fps.items() if r != cap_ref]
        other_pads = [(r, union(pad_boxes(f))) for r, f in fps.items() if r != cap_ref]
        best = (s0, cx0, cy0, rot0, d0)
        if must_move:
            best = (1e9, cx0, cy0, rot0, d0)     # vi tri hien tai vi pham vung can tranh: bat buoc chon vi tri hop le khac
        nx = int(RADIUS / STEP)
        for ix in range(-nx, nx + 1):
            for iy in range(-nx, nx + 1):
                x, y = pp[0] + ix * STEP, pp[1] + iy * STEP
                if math.hypot(x - pp[0], y - pp[1]) > RADIUS:
                    continue
                for rot in (0, 90, 180, 270):
                    cap.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
                    cap.SetOrientationDegrees(rot)
                    ub = union(pad_boxes(cap))
                    cb = court(cap)
                    if ub[0] < bb[0] + EDGE or ub[1] < bb[1] + EDGE or ub[2] > bb[2] - EDGE or ub[3] > bb[3] - EDGE:
                        continue
                    if any(overlap(cb, ob, GAP) for r, ob in others):
                        continue
                    if any(overlap(cb, a_, 0.0) for a_ in avoid):
                        continue
                    if any(overlap(ub, st_, 0.25) for st_ in stubs):
                        continue
                    # con cho cho via GND canh pad GND cua tu (>= 1 trong 8 huong khong nam trong courtyard linh kien khac)
                    cgp = [p for p in cap.Pads() if p.GetNetname() != net_p][0]
                    gx, gy = pt(cgp.GetPosition())
                    free = False
                    for k in range(8):
                        vx = gx + VIA_SITE_DIST * math.cos(k * math.pi / 4); vy = gy + VIA_SITE_DIST * math.sin(k * math.pi / 4)
                        if cb[0] <= vx <= cb[2] and cb[1] <= vy <= cb[3] and False:
                            continue
                        if any(ob[0] - 0.15 <= vx <= ob[2] + 0.15 and ob[1] - 0.15 <= vy <= ob[3] + 0.15 for r, ob in others):
                            continue
                        if any(pb_[0] - 0.4 <= vx <= pb_[2] + 0.4 and pb_[1] - 0.4 <= vy <= pb_[3] + 0.4 for r, pb_ in other_pads):
                            continue
                        if not (bb[0] + EDGE <= vx <= bb[2] - EDGE and bb[1] + EDGE <= vy <= bb[3] - EDGE):
                            continue
                        free = True
                        break
                    if not free:
                        continue
                    if any(seg_rect_dist(a, c, ub) < TRACK_CLR + w for a, c, w in obs_seg):
                        continue
                    if any(max(0, ub[0] - v[0][0], v[0][0] - ub[2]) ** 2 + max(0, ub[1] - v[0][1], v[0][1] - ub[3]) ** 2 < (TRACK_CLR + v[1]) ** 2 for v in obs_via):
                        continue
                    dd = metrics()
                    sc = dd[0] + 0.3 * dd[1]
                    if sc < best[0] - 1e-9:
                        best = (sc, x, y, rot, dd)
        if (best[0] < s0 - MIN_GAIN and not must_move) or (must_move and best[1:4] != (cx0, cy0, rot0)):
            sc, x, y, rot, dd = best
            cap.SetPosition(VECTOR2I(FromMM(x), FromMM(y))); cap.SetOrientationDegrees(rot)
            moved = True
        else:
            cap.SetPosition(VECTOR2I(FromMM(cx0), FromMM(cy0))); cap.SetOrientationDegrees(rot0)
            dd, moved = d0, False
        fps_box = union(pad_boxes(cap))
        report.append((cap_ref, f"{ic_ref}.{ic_pin}", d0, dd, moved, (round(cx0, 2), round(cy0, 2), rot0), (round(pt(cap.GetPosition())[0], 2), round(pt(cap.GetPosition())[1], 2), cap.GetOrientationDegrees())))

    print("cap  chan     truoc(pad-chan, GND-chan)   sau(pad-chan, GND-chan)   vi tri")
    for cap_ref, pin, d0, dd, moved, p0, p1 in report:
        print(f"{cap_ref:4s} {pin:7s} ({d0[0]:.2f}, {d0[1]:.2f})              ({dd[0]:.2f}, {dd[1]:.2f})      {'DOI' if moved else 'giu'} {p0} -> {p1}")
    b.Save(out)
    print("saved", out)


main()
