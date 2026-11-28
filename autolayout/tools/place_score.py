"""place_score.py BOARD [--detail] : cham placement TRUOC khi route (L46).

- ratsnest: cay MST (khoang cach Euclid giua tam pad) cho moi net, tru net do dong (GND).
- cat: so cap doan ratsnest cua 2 net TIN HIEU khac nhau cat nhau (moi lan cat ~ 1 via sau nay).
- overlap: cap courtyard chong nhau; ngoai: courtyard ra ngoai vien board (tru linh kien co chu dich lo ra: antenna/connector, liet ke rieng).
- keepout: pad/courtyard nam trong rule area (keepout) cua board.
In tong + top net dai nhat + top cap cat nhau.
"""
import math
import sys

import pcbnew

POWER_HINT = ("GND",)


def mst(points):
    if len(points) < 2:
        return []
    used = [points[0]]; rest = points[1:]; edges = []
    while rest:
        best = None
        for i, q in enumerate(rest):
            for u in used:
                d = math.dist(u, q)
                if best is None or d < best[0]:
                    best = (d, i, u)
        d, i, u = best
        edges.append((u, rest[i])); used.append(rest.pop(i))
    return edges


def cross(a, b, c, d):
    o = lambda p, q, r: (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    if a in (c, d) or b in (c, d):
        return False
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def score(path, detail=False):
    b = pcbnew.LoadBoard(path)
    zone_nets = {z.GetNetname() for z in b.Zones() if not z.GetIsRuleArea()}
    nets = {}
    for f in b.GetFootprints():
        for p in f.Pads():
            n = p.GetNetname()
            if not n or n.startswith("unconnected") or any(h in n.upper() for h in POWER_HINT) or n in zone_nets:
                continue
            nets.setdefault(n, []).append((round(p.GetPosition().x / 1e6, 3), round(p.GetPosition().y / 1e6, 3)))
    edges = {n: mst(sorted(set(v))) for n, v in nets.items()}
    length = {n: sum(math.dist(a, c) for a, c in e) for n, e in edges.items()}
    pw = lambda n: any(k in n.upper() for k in ("VBUS", "+5V", "3V3", "VDD", "AVDD"))
    sig = [(n, e) for n, es in edges.items() if not pw(n) for e in es]
    crosses = []
    for i in range(len(sig)):
        for j in range(i + 1, len(sig)):
            if sig[i][0] != sig[j][0] and cross(*sig[i][1], *sig[j][1]):
                crosses.append((sig[i][0], sig[j][0]))
    eb = b.GetBoardEdgesBoundingBox()
    crt, poly = {}, {}
    for f in b.GetFootprints():
        c = f.GetCourtyard(pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd)
        crt[f.GetReference()] = c.BBox() if c.OutlineCount() else f.GetBoundingBox(False)
        poly[f.GetReference()] = pcbnew.SHAPE_POLY_SET(c) if c.OutlineCount() else None
    refs = sorted(crt)
    def hit(a, c):          # courtyard that la da giac (vd U1 hinh chu T vung anten), khong chi bbox
        if not crt[a].Intersects(crt[c]):
            return False
        if poly[a] is None or poly[c] is None:
            return True
        x = pcbnew.SHAPE_POLY_SET(poly[a])
        try:
            x.BooleanIntersection(poly[c])
        except TypeError:
            x.BooleanIntersection(poly[c], pcbnew.SHAPE_POLY_SET.PM_FAST)
        return x.Area() > 1e9          # > 0.001 mm2
    overl = [(a, c) for i, a in enumerate(refs) for c in refs[i + 1:] if hit(a, c)]
    outside = [r for r in refs if not eb.Contains(crt[r])]
    keep = []
    for z in b.Zones():
        if not z.GetIsRuleArea():
            continue
        for f in b.GetFootprints():
            for p in f.Pads():
                if z.Outline().Contains(p.GetPosition()):
                    keep.append(f"{f.GetReference()}.{p.GetNumber()}")
    tot = sum(length.values())
    print(f"{path.split('/')[-1]}: ratsnest {tot:.0f} mm | cat {len(crosses)} | courtyard chong {len(overl)} | ra ngoai {len(outside)} {outside} | keepout {len(set(keep))}")
    if detail:
        print("  net dai nhat:", ", ".join(f"{n} {length[n]:.0f}" for n in sorted(length, key=length.get, reverse=True)[:12]))
        from collections import Counter
        print("  cap cat nhieu nhat:", Counter(tuple(sorted(c)) for c in crosses).most_common(12))
        if overl:
            print("  chong:", overl[:20])
        if keep:
            print("  pad trong keepout:", sorted(set(keep))[:20])
    return dict(len=tot, cross=len(crosses), overlap=len(overl), outside=outside, keepout=len(set(keep)))


if __name__ == "__main__":
    score(sys.argv[1], "--detail" in sys.argv)
