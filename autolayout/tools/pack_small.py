"""pack_small.py IN.kicad_pcb OUT.kicad_pcb [REF ... | @small] [--r 6] [--gap 0.2] [--pass 2]

Dat lai hang loat linh kien nho (R/C/Q/D/TP...) sat chan ma chung noi toi (L67 mo rong cho ca board, L76).
- Linh kien KHONG co trong danh sach = co dinh (IC, connector da dat tay theo floorplan).
- Moi linh kien: tim luoi 0.25 mm trong ban kinh --r quanh vi tri hien tai (vi tri tay = y do), 4 huong.
- Hop le: courtyard (bbox xoay) khong cham courtyard khac + gap, nam trong board (inset 0.5), khong cham rule area.
  Courtyard co dinh dung da giac that (U1 hinh chu T co canh anten), khong chi bbox.
- Diem = tong khoang cach moi pad (net khac GND) toi pad cung net gan nhat tren linh kien khac
        + 2 mm cho moi doan do cat ratsnest net tin hieu khac (moi lan cat ~ 1 via).
- Thu tu: tu dien truoc (decap sat chan), roi R, roi cac loai khac; lap --pass lan.
"""
import math
import sys

import pcbnew
from pcbnew import FromMM, VECTOR2I

args = sys.argv[1:]
opt = {"--r": 6.0, "--gap": 0.2, "--pass": 2, "--fix": ""}   # --fix A,B,C : giu co dinh (vd cum da dat tay theo hanh lang)
for k in list(opt):
    if k in args:
        i = args.index(k); opt[k] = type(opt[k])(args[i + 1]); del args[i:i + 2]
src, dst, refs = args[0], args[1], args[2:]
b = pcbnew.LoadBoard(src)
fps = {f.GetReference(): f for f in b.GetFootprints()}
if refs == ["@small"] or not refs:
    refs = [r for r, f in fps.items() if r[0] in "RCQDL" and not r.startswith("D") or (r.startswith("D") and len(f.Pads()) <= 3)]
    refs = [r for r in refs if len(fps[r].Pads()) <= 4]
fixed = {r for r in opt["--fix"].split(",") if r}
bad = fixed - set(fps)
if bad:
    sys.exit(f"--fix co ref khong ton tai: {sorted(bad)}")
refs = [r for r in refs if r not in fixed]
order = lambda r: (0 if r.startswith("C") else 1 if r.startswith("R") else 2, r)
refs = sorted(refs, key=order)
S = 1e6
GND = lambda n: "GND" in n.upper()


def local(f):
    """courtyard bbox va pad offset (mm) cua f o goc 0, tinh tu vi tri/goc hien tai."""
    o = f.GetPosition(); a = math.radians(f.GetOrientationDegrees())
    unrot = lambda x, y: (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))
    # KiCad: diem cuc bo (x,y) o goc a -> (x cos a + y sin a, -x sin a + y cos a); nghich dao nhu tren
    cy = f.GetCourtyard(pcbnew.F_CrtYd)
    pts = []
    if cy.OutlineCount():
        ol = cy.Outline(0)
        pts = [((ol.CPoint(i).x - o.x) / S, (ol.CPoint(i).y - o.y) / S) for i in range(ol.PointCount())]
    else:
        bb = f.GetBoundingBox(False)
        pts = [((bb.GetLeft() - o.x) / S, (bb.GetTop() - o.y) / S), ((bb.GetRight() - o.x) / S, (bb.GetBottom() - o.y) / S)]
    pl = [unrot(x, y) for x, y in pts]
    box = (min(p[0] for p in pl), min(p[1] for p in pl), max(p[0] for p in pl), max(p[1] for p in pl))
    pads = [(p.GetNetname(), unrot((p.GetPosition().x - o.x) / S, (p.GetPosition().y - o.y) / S)) for p in f.Pads()]
    return box, pads


def at(lbox, lpads, x, y, rot):
    a = math.radians(rot)
    rt = lambda px, py: (x + px * math.cos(a) + py * math.sin(a), y - px * math.sin(a) + py * math.cos(a))
    c = [rt(lbox[0], lbox[1]), rt(lbox[2], lbox[1]), rt(lbox[0], lbox[3]), rt(lbox[2], lbox[3])]
    box = (min(p[0] for p in c), min(p[1] for p in c), max(p[0] for p in c), max(p[1] for p in c))
    return box, [(n, rt(*q)) for n, q in lpads]


def polys(f):
    cy = f.GetCourtyard(pcbnew.F_CrtYd)
    out = []
    for k in range(cy.OutlineCount()):
        ol = cy.Outline(k); out.append([(ol.CPoint(i).x / S, ol.CPoint(i).y / S) for i in range(ol.PointCount())])
    if not out:
        bb = f.GetBoundingBox(False); l, t, r, bt = bb.GetLeft() / S, bb.GetTop() / S, bb.GetRight() / S, bb.GetBottom() / S
        out = [[(l, t), (r, t), (r, bt), (l, bt)]]
    return out


def inside(pt, poly):
    x, y = pt; c = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def segx(a, c, d, e):
    o = lambda p, q, r: (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, c, d) * o(a, c, e) < 0 and o(d, e, a) * o(d, e, c) < 0


def rect_hits_poly(bx, poly):
    l, t, r, btm = bx
    if max(p[0] for p in poly) < l or min(p[0] for p in poly) > r or max(p[1] for p in poly) < t or min(p[1] for p in poly) > btm:
        return False
    corners = [(l, t), (r, t), (r, btm), (l, btm)]
    if any(inside(c, poly) for c in corners) or any(l < p[0] < r and t < p[1] < btm for p in poly):
        return True
    for i in range(4):
        for j in range(len(poly)):
            if segx(corners[i], corners[i - 1], poly[j], poly[j - 1]):
                return True
    return False


eb = b.GetBoardEdgesBoundingBox()
BL, BT, BR, BB = eb.GetLeft() / S + 0.5, eb.GetTop() / S + 0.5, eb.GetRight() / S - 0.5, eb.GetBottom() / S - 0.5
rule = [[(z.Outline().Outline(0).CPoint(i).x / S, z.Outline().Outline(0).CPoint(i).y / S) for i in range(z.Outline().Outline(0).PointCount())]
        for z in b.Zones() if z.GetIsRuleArea()]
loc = {r: local(fps[r]) for r in refs}
G = opt["--gap"]


def world_pads(r):
    f = fps[r]
    return [(p.GetNetname(), (p.GetPosition().x / S, p.GetPosition().y / S)) for p in f.Pads()]


def power(n):
    return any(k in n.upper() for k in ("VBUS", "+5V", "3V3", "VDD", "AVDD"))


def place(r):
    f = fps[r]; lbox, lpads = loc[r]
    x0, y0 = f.GetPosition().x / S, f.GetPosition().y / S
    obst = [g for k, g in fps.items() if k != r]
    opoly = [(k, polys(g)) for k, g in fps.items() if k != r]
    tgt = {}
    for k, g in fps.items():
        if k == r:
            continue
        for n, q in world_pads(k):
            if n and not n.startswith("unconnected") and not GND(n):
                tgt.setdefault(n, []).append(q)
    # ratsnest tin hieu cua net khac (de phat cat)
    rats = []
    for n, pts in tgt.items():
        if power(n) or len(pts) < 2:
            continue
        used = [pts[0]]; rest = pts[1:]
        while rest:
            d, i, u = min((math.dist(u, q), i, u) for i, q in enumerate(rest) for u in used)
            rats.append((n, u, rest[i])); used.append(rest.pop(i))
    best = None
    st = 0.25; n = int(opt["--r"] / st)
    for ix in range(-n, n + 1):
        for iy in range(-n, n + 1):
            x, y = x0 + ix * st, y0 + iy * st
            for rot in (0, 90, 180, 270):
                bx, pads = at(lbox, lpads, x, y, rot)
                if bx[0] < BL or bx[1] < BT or bx[2] > BR or bx[3] > BB:
                    continue
                gb = (bx[0] - G, bx[1] - G, bx[2] + G, bx[3] + G)
                if any(rect_hits_poly(gb, p) for _, ps in opoly for p in ps) or any(rect_hits_poly(bx, p) for p in rule):
                    continue
                sc = 0.0
                for nn, q in pads:
                    if not nn or nn.startswith("unconnected") or GND(nn) or nn not in tgt:
                        continue
                    tq = min(tgt[nn], key=lambda t_: math.dist(t_, q))
                    sc += math.dist(tq, q)
                    if not power(nn):
                        sc += 2.0 * sum(1 for m, a, c in rats if m != nn and segx(q, tq, a, c))
                sc += 0.02 * math.hypot(x - x0, y - y0)          # hoa: giu y do tay
                if best is None or sc < best[0]:
                    best = (sc, x, y, rot)
    if best:
        f.SetOrientationDegrees(best[3]); f.SetPosition(VECTOR2I(FromMM(best[1]), FromMM(best[2])))
        loc[r] = local(f)
    return best


for ps in range(opt["--pass"]):
    moved = 0
    for r in refs:
        x0, y0, a0 = fps[r].GetPosition().x, fps[r].GetPosition().y, fps[r].GetOrientationDegrees()
        bst = place(r)
        if bst is None:
            print(f"  {r}: KHONG co vi tri hop le trong r={opt['--r']} (giu nguyen, chong?)")
        elif (fps[r].GetPosition().x, fps[r].GetPosition().y, fps[r].GetOrientationDegrees()) != (x0, y0, a0):
            moved += 1
    print(f"pass {ps + 1}: doi {moved}/{len(refs)}")
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from ksave import save_board; save_board(b, dst)
print("->", dst)
