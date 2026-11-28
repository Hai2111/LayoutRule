"""route_audit.py BOARD [BOARD...] : do do "gon" cua dong da route, de so board cua ta voi ref (L58).

Chi so (tren tin hieu = moi net tru GND/nguon), moi board 1 dong:
  sig_mm     tong chieu dai track tin hieu
  hug%       % chieu dai track tin hieu chay sat (<= 0.45 mm) >= 4 chan SMD cua CUNG 1 linh kien khac net
  underIC%   % chieu dai track tin hieu nam duoi than IC (U*, >= 8 pad) tren lop co pad
  inner      so lan track vao chan IC tu PHIA THAN (huong vao tam IC) / tong so chan IC co track
  via/net    via trung binh moi net tin hieu co route
  bend/10mm  so lan doi huong (> 10 do) moi 10 mm track tin hieu
Khong phai luat cung: dung de thay board cua ta lech khoi cach nguoi thiet ke ref lam bao xa.
"""
import math
import re
import sys

import pcbnew

POWER = re.compile(r"(GND|VCC|VDD|VBUS|VBAT|VIN|\+\d|V\d+V\d*|3V3|5V|12V|VSYS|VREF)", re.I)


def seg_d(ax, ay, bx, by, x, y):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    u = 0 if L == 0 else max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / L))
    return math.hypot(x - ax - u * dx, y - ay - u * dy)


def audit(path):
    b = pcbnew.LoadBoard(path)
    fps = list(b.GetFootprints())
    smd = [(f, p) for f in fps for p in f.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    ics = []
    for f in fps:
        if f.GetReference().startswith("U") and len(f.Pads()) >= 8:
            xs, ys = [], []
            for it in f.GraphicalItems():
                if it.GetLayer() in (pcbnew.F_Fab, pcbnew.B_Fab) and it.GetClass() != "PCB_TEXT":
                    q = it.GetBoundingBox(); xs += [q.GetLeft() / 1e6, q.GetRight() / 1e6]; ys += [q.GetTop() / 1e6, q.GetBottom() / 1e6]
            if not xs:   # khong co F.Fab: lay than = vung giua cac pad
                q = f.GetBoundingBox(False); xs = [q.GetLeft() / 1e6, q.GetRight() / 1e6]; ys = [q.GetTop() / 1e6, q.GetBottom() / 1e6]
            # than IC = bbox Fab nhung bo phan chan: thu nho ve phia tam theo chieu dai pad
            ics.append((f, min(xs), min(ys), max(xs), max(ys)))
    tr = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and not POWER.search(t.GetNetname() or "GND") and t.GetNetname()]
    vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and not POWER.search(t.GetNetname() or "GND") and t.GetNetname()]
    sig = sum(t.GetLength() for t in tr) / 1e6
    if sig < 1:
        return None
    hug = under = 0.0
    for t in tr:
        ax, ay, bx, by = t.GetStart().x / 1e6, t.GetStart().y / 1e6, t.GetEnd().x / 1e6, t.GetEnd().y / 1e6
        L = t.GetLength() / 1e6
        per = {}
        for f, p in smd:
            if p.GetNetname() == t.GetNetname() or not p.GetLayerSet().Contains(t.GetLayer()):
                continue
            q = p.GetBoundingBox()
            xs = (q.GetLeft() / 1e6, q.GetRight() / 1e6, (q.GetLeft() + q.GetRight()) / 2e6)
            ys = (q.GetTop() / 1e6, q.GetBottom() / 1e6, (q.GetTop() + q.GetBottom()) / 2e6)
            if min(seg_d(ax, ay, bx, by, x, y) for x in xs for y in ys) - t.GetWidth() / 2e6 <= 0.45:
                per[f.GetReference()] = per.get(f.GetReference(), 0) + 1
        if L >= 1.0 and any(v >= 4 for v in per.values()):
            hug += L
        for f, x0, y0, x1, y1 in ics:
            if not any(p.GetLayerSet().Contains(t.GetLayer()) for p in f.Pads()):
                continue
            n = 10   # lay mau 10 diem tren doan
            inside = sum(1 for i in range(n + 1) if x0 < ax + (bx - ax) * i / n < x1 and y0 < ay + (by - ay) * i / n < y1)
            under += L * inside / (n + 1)
    # vao chan tu phia than
    inner = tot = 0
    for f, x0, y0, x1, y1 in ics:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        for p in f.Pads():
            if POWER.search(p.GetNetname() or "GND") or not p.GetNetname():
                continue
            px, py = p.GetPosition().x / 1e6, p.GetPosition().y / 1e6
            for t in tr:
                for (sx, sy), (ox, oy) in (((t.GetStart().x / 1e6, t.GetStart().y / 1e6), (t.GetEnd().x / 1e6, t.GetEnd().y / 1e6)),
                                           ((t.GetEnd().x / 1e6, t.GetEnd().y / 1e6), (t.GetStart().x / 1e6, t.GetStart().y / 1e6))):
                    if t.GetNetname() == p.GetNetname() and p.HitTest(pcbnew.VECTOR2I(int(sx * 1e6), int(sy * 1e6))):
                        # bo qua doan ngan nam trong pad, tim huong ra khoi pad
                        if math.hypot(ox - sx, oy - sy) < 0.05:
                            continue
                        tot += 1
                        vx, vy = ox - sx, oy - sy
                        wx, wy = cx - px, cy - py
                        nv, nw = math.hypot(vx, vy), math.hypot(wx, wy)
                        if nv and nw and (vx * wx + vy * wy) / (nv * nw) > 0.5:
                            inner += 1
    # doi huong
    bends = 0; bendpts = set()
    ends = {}
    for t in tr:
        for q, o in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
            ends.setdefault((t.GetNetname(), round(q.x / 1e4), round(q.y / 1e4)), []).append((q, o))
    allpads = [p for f in fps for p in f.Pads()]
    for k, lst in ends.items():
        if len(lst) == 2:
            (q1, o1), (q2, o2) = lst
            if any(p.HitTest(q1) for p in allpads):      # gap khuc nam trong pad: khong nhin thay, khong tinh
                continue
            a1 = math.atan2(o1.y - q1.y, o1.x - q1.x)
            a2 = math.atan2(o2.y - q2.y, o2.x - q2.x)
            turn = abs((a1 - a2 + math.pi) % (2 * math.pi) - math.pi)
            if abs(math.pi - turn) > math.radians(10):
                bends += 1
                bendpts.add(k)
    # goc da vat (2 lan gap noi bang doan < 1 mm) la MOT goc voi nguoi nhin: tru bot 1 cho moi doan vat
    for t in tr:
        if t.GetLength() / 1e6 < 1.0:
            ka = (t.GetNetname(), round(t.GetStart().x / 1e4), round(t.GetStart().y / 1e4))
            kb = (t.GetNetname(), round(t.GetEnd().x / 1e4), round(t.GetEnd().y / 1e4))
            if ka in bendpts and kb in bendpts:
                bends -= 1
    nets = {t.GetNetname() for t in tr}
    return dict(sig_mm=sig, hug=100 * hug / sig, under=100 * under / sig, inner=f"{inner}/{tot}",
                innerp=100 * inner / max(tot, 1), via=len(vias) / max(len(nets), 1), bend=10 * bends / sig)


if __name__ == "__main__":
    print(f"{'board':28s} {'sig_mm':>7s} {'hug%':>5s} {'undIC%':>6s} {'inner':>7s} {'via/net':>7s} {'bend/10':>7s}")
    for pth in sys.argv[1:]:
        r = audit(pth)
        name = pth.replace("\\", "/").split("/")[-1][:28]
        if r is None:
            print(f"{name:28s} (khong co track tin hieu)")
            continue
        print(f"{name:28s} {r['sig_mm']:7.0f} {r['hug']:5.1f} {r['under']:6.1f} {r['inner']:>7s} {r['via']:7.2f} {r['bend']:7.2f}")
