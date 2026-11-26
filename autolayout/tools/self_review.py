"""self_review.py - ba phep kiem LOGIC ma DRC khong lam duoc (bai hoc: tu review phai doc lap voi bo route).
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" self_review.py BOARD.kicad_pcb INTENT.json

R1  track duoi than linh kien (F.Fab bbox), KE CA IC. Pad cua chinh net duoc phep.
R2  track bi KEP giua pad cua >= 2 linh kien khac nhau (khoang trong <= SQUEEZE mm moi ben) -> dich linh kien thay vi luon.
R3  THU TU cap nguon: voi power_chains trong intent, tim duong dong dien ngan nhat tu pad nguon toi tung chan IC
    tren chinh dong dong da route; kiem pad tu (cap) nam TRUOC chan IC, TVS truoc bulk.
Khong thay the DRC/ERC. In ra danh sach tung vi pham de nguoi xem doi chieu voi anh.
"""
import heapq
import json
import math
import sys

import pcbnew

SQUEEZE = 0.9


def pt(p):
    return (p.x / 1e6, p.y / 1e6)


def box(bb):
    return (bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6)


def dist_pt_rect(x, y, r):
    return math.hypot(max(r[0] - x, 0, x - r[2]), max(r[1] - y, 0, y - r[3]))


def samples(a, c, step=0.4):
    L = math.hypot(c[0] - a[0], c[1] - a[1])
    n = max(1, int(L / step))
    return [(a[0] + (c[0] - a[0]) * i / n, a[1] + (c[1] - a[1]) * i / n) for i in range(n + 1)]


def main():
    path, intent_p = sys.argv[1], sys.argv[2]
    intent = json.load(open(intent_p, encoding="utf-8"))
    b = pcbnew.LoadBoard(path)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    pads = []   # (ref, num, net, rect, layers, center)
    fab = {}
    for ref, f in fps.items():
        xs0 = ys0 = 1e9; xs1 = ys1 = -1e9
        for g in f.GraphicalItems():
            if g.GetLayer() == pcbnew.F_Fab:
                gb = box(g.GetBoundingBox())
                xs0, ys0, xs1, ys1 = min(xs0, gb[0]), min(ys0, gb[1]), max(xs1, gb[2]), max(ys1, gb[3])
        if xs0 < 1e8:
            fab[ref] = (xs0, ys0, xs1, ys1)
        for p in f.Pads():
            pads.append((ref, p.GetNumber(), p.GetNetname(), box(p.GetBoundingBox()),
                         p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH, pt(p.GetPosition())))
    segs = []
    vias = []
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            vias.append((t.GetNetname(), pt(t.GetPosition())))
        else:
            segs.append((t.GetNetname(), 0 if t.GetLayer() == pcbnew.F_Cu else 1, pt(t.GetStart()), pt(t.GetEnd()), t.GetWidth() / 1e6))

    # ---------------- R1: duoi than ----------------
    print("R1  track dau/giua duoi THAN linh kien (F.Fab bbox, ke ca IC) tren F.Cu")
    r1 = {}
    for net, l, a, c, w in segs:
        if l != 0:
            continue
        for ref, bb in fab.items():
            own = {p[2] for p in pads if p[0] == ref}
            if net in own and ref != "J1":
                continue                       # track cung net voi linh kien (noi vao pad cua no)
            inside = sum(1 for x, y in samples(a, c, 0.2) if bb[0] + 0.05 < x < bb[2] - 0.05 and bb[1] + 0.05 < y < bb[3] - 0.05)
            if inside:
                r1.setdefault((ref, net), 0.0)
                r1[(ref, net)] += inside * 0.2
    for (ref, net), L in sorted(r1.items(), key=lambda kv: -kv[1]):
        print(f"    [{ref}] {net}: ~{L:.1f} mm duoi than")
    if not r1:
        print("    (khong co)")

    # ---------------- R2: bi kep giua pad ----------------
    print("R2  track bi KEP giua pad cua >=2 linh kien khac nhau (khoang <= %.1f mm moi ben)" % SQUEEZE)
    r2 = {}
    for net, l, a, c, w in segs:
        if l != 0:
            continue
        hits_all = set()
        for x, y in samples(a, c, 0.4):
            near = {}
            for ref, num, pnet, rect, tht, cen in pads:
                if pnet == net or not pnet:
                    continue
                if any(p_[0] == ref and p_[2] == net for p_ in pads):      # linh kien co pad thuoc net nay: day la duong noi chu y, khong phai bi kep
                    continue
                d = dist_pt_rect(x, y, rect) - w / 2
                if d <= SQUEEZE:
                    near[ref] = min(near.get(ref, 9), d)
            if len(near) >= 2:
                hits_all.add(tuple(sorted(near)))
        for refs in hits_all:
            r2.setdefault(net, set()).add(refs)
    for net, s in sorted(r2.items()):
        print(f"    {net}: " + "; ".join("/".join(x) for x in sorted(s)))
    if not r2:
        print("    (khong co)")

    # ---------------- R3: thu tu cap nguon ----------------
    print("R3  thu tu cap nguon (duong dong dien that tren dong da route)")
    chains = intent.get("power_chains", {})
    for net, chs in chains.items():
        # do thi: dinh = (x,y,layer) lam tron 0.02; pad noi voi dinh nam trong pad rect cung lop
        def key(p, l): return (round(p[0], 2), round(p[1], 2), l)
        adj = {}
        def add(u, v, w):
            adj.setdefault(u, []).append((v, w)); adj.setdefault(v, []).append((u, w))
        for n_, l, a, c, w in segs:
            if n_ != net:
                continue
            add(key(a, l), key(c, l), math.hypot(c[0] - a[0], c[1] - a[1]))
        for n_, p in vias:
            if n_ == net:
                add(key(p, 0), key(p, 1), 0.01)
        segl = [(a, c) for n_, l, a, c, w in segs if n_ == net for _l in [l]]
        segl2 = [(key(a, l), key(c, l), a, c) for n_, l, a, c, w in segs if n_ == net]
        ends = {u for u in list(adj) if u[0] != "PAD"}
        for u in ends:
            for ka, kc, a, c in segl2:
                if u in (ka, kc) or u[2] != ka[2]:
                    continue
                dx, dy = c[0] - a[0], c[1] - a[1]; L2 = dx * dx + dy * dy
                if L2 == 0:
                    continue
                t = ((u[0] - a[0]) * dx + (u[1] - a[1]) * dy) / L2
                if 0 < t < 1 and math.hypot(u[0] - (a[0] + t * dx), u[1] - (a[1] + t * dy)) < 0.03:
                    add(u, ka, math.hypot(u[0] - a[0], u[1] - a[1])); add(u, kc, math.hypot(c[0] - u[0], c[1] - u[1]))
        padnode = {}
        for ref, num, pnet, rect, tht, cen in pads:
            if pnet != net:
                continue
            pid = f"{ref}.{num}"
            for u in [u_ for u_ in list(adj) if u_[0] != "PAD"]:
                if (u[2] == 0 or tht) and rect[0] - 0.02 <= u[0] <= rect[2] + 0.02 and rect[1] - 0.02 <= u[1] <= rect[3] + 0.02:
                    add(("PAD", pid), u, 0.0)
                    padnode[pid] = ("PAD", pid)
        src = chs[0]["from"]
        if ("PAD", src) not in adj:
            print(f"    {net}: pad nguon {src} chua co dong nao ({'chua route' })")
            continue
        dist = {("PAD", src): 0.0}; prev = {}
        import itertools
        cnt = itertools.count()
        pq = [(0.0, next(cnt), ("PAD", src))]
        while pq:
            d, _c, u = heapq.heappop(pq)
            if d > dist.get(u, 1e9):
                continue
            for v, w in adj.get(u, []):
                if d + w < dist.get(v, 1e9):
                    dist[v] = d + w; prev[v] = u; heapq.heappush(pq, (d + w, next(cnt), v))
        def pads_on_path(pid):
            u = ("PAD", pid)
            if u not in dist:
                return None
            seq = []
            while u in prev or u == ("PAD", src):
                if u[0] == "PAD":
                    seq.append(u[1])
                if u == ("PAD", src):
                    break
                u = prev[u]
            return list(reversed(seq)), dist[("PAD", pid)]
        wanted = {}
        for ch in chs:
            for i, name in enumerate(ch["path"]):
                wanted[name] = [m_ for m_ in ch["path"][:i] if not m_.startswith("J")]      # tai (connector) khong bat buoc thu tu
        for tgt, must in wanted.items():
            res = pads_on_path(tgt)
            if res is None:
                print(f"    {net}: {tgt} KHONG noi voi {src}")
                continue
            seq, L = res
            miss = [m for m in must if m not in seq]
            status = "DUNG THU TU" if not miss else "SAI: khong di qua " + ",".join(miss)
            print(f"    {net}: {src} -> {tgt} ({L:.1f} mm) qua {' > '.join(seq)}  [{status}]")
    if not chains:
        print("    (intent khong co power_chains)")


main()
