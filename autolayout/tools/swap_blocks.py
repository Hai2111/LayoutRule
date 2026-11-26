"""swap_blocks.py - HOAN VI vi tri cac cum linh kien GIONG HET nhau (vd 3 kenh LED: Q + R gate + R keo xuong) de go day cheo.
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" swap_blocks.py IN.kicad_pcb OUT.kicad_pcb [k]
Netlist KHONG doi, chi doi cho (bai hoc tu ban Vector 2026-11-26). Cum = cac linh kien nho noi nhau qua net RIENG (khong cham IC/connector).
Liet ke moi hoan vi; autolayout route THAT tung cai roi chon (ratsnest khong du doan duoc ket qua route).
"""
import itertools, sys
import pcbnew

FIXED = ("U", "J", "H", "SW", "Y")   # linh kien khong dua vao cum


def isg(n):
    return "GND" in n.upper()


def mst(pts):
    done, todo, edges = [pts[0]], pts[1:], []
    while todo:
        d, a, b = min(((abs(p[0] - q[0]) + abs(p[1] - q[1]), p, q) for p in done for q in todo), key=lambda t: t[0])
        edges.append((a, b)); done.append(b); todo.remove(b)
    return edges


def crosses(a, b, c, d):
    o = lambda p, q, r: (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def main():
    inp, outp = sys.argv[1], sys.argv[2]
    b = pcbnew.LoadBoard(inp)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    pads, nets = {}, {}
    for r, f in fps.items():
        for p in f.Pads():
            n = p.GetNetname()
            pos = p.GetPosition()
            pads[(r, p.GetNumber())] = (n, (pos.x / 1e6, pos.y / 1e6))
            if n and not n.startswith("unconnected"):
                nets.setdefault(n, []).append((r, p.GetNumber()))
    small = {r for r in fps if not r.startswith(FIXED)}
    rail = {n for n, v in nets.items() if isg(n) or len(v) > 5 or n.lstrip("/").startswith(("+", "V"))}
    private = {n for n, v in nets.items() if n not in rail and all(r in small for r, _ in v) and len({r for r, _ in v}) > 1}
    parent = {r: r for r in small}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x
    for n in private:
        rs = [r for r, _ in nets[n]]
        for r in rs[1:]:
            parent[find(r)] = find(rs[0])
    clusters = {}
    for r in sorted(small):
        clusters.setdefault(find(r), []).append(r)

    def role(r):
        kinds = []
        for (pr, num), (n, _) in pads.items():
            if pr == r:
                kinds.append((num, "G" if isg(n) else "PWR" if n in rail else "PRIV" if n in private else "EXT" if n in nets else "NC"))
        return (fps[r].GetFPIDAsString(), str(fps[r].GetValue()), tuple(sorted(kinds)))
    groups = {}
    for members in clusters.values():
        if len(members) > 1:
            ms = sorted(members, key=role)
            if len({role(r) for r in ms}) == len(ms):          # vai tro trong cum phai phan biet duoc
                groups.setdefault(tuple(role(r) for r in ms), []).append(ms)

    def score(where):   # where: ref -> ref cua cho dang dung
        edges = []
        for n, v in nets.items():
            if n in rail:
                continue
            pts = [pads[(where.get(r, r), num)][1] for r, num in v]
            edges += [(n, a, c) for a, c in mst(pts)]
        x = sum(1 for i, e in enumerate(edges) for g in edges[i + 1:] if e[0] != g[0] and crosses(e[1], e[2], g[1], g[2]))
        return x, round(sum(((a[0] - c[0]) ** 2 + (a[1] - c[1]) ** 2) ** 0.5 for _, a, c in edges), 1)

    cands = [{}]
    for grp in groups.values():
        if len(grp) < 2 or len(grp) > 4:                      # toi da 4 cum (24 hoan vi) de con route het duoc
            continue
        print("cum giong nhau", ["+".join(c) for c in grp])
        new = []
        for w0 in cands:
            for perm in itertools.permutations(range(len(grp))):
                w = dict(w0)
                for i, j in enumerate(perm):
                    w.update(zip(grp[i], grp[j]))
                new.append(w)
        cands = new[:24]
    cands.sort(key=score)                                     # 0 = it giao cat nhat theo ratsnest (chi de xep thu tu, KHONG de quyet dinh)
    pick = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    where = cands[pick]
    print("candidates", len(cands), "pick", pick, "ratsnest", score(where))
    pose = {r: (pcbnew.VECTOR2I(f.GetPosition().x, f.GetPosition().y), f.GetOrientationDegrees()) for r, f in fps.items()}
    moved = {r: s for r, s in where.items() if r != s}
    for r, s in moved.items():
        fps[r].SetOrientationDegrees(pose[s][1])
        fps[r].SetPosition(pose[s][0])
    b.Save(outp)
    print("doi cho:", ", ".join(f"{r}->cho cua {s}" for r, s in sorted(moved.items())) or "khong")


main()
