"""decap_template.py - LOGIC dat tu decoupling tu ref design: tu nam o dau so voi chan IC, xoay the nao.
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" decap_template.py REF_ROOT  [CAND.kicad_pcb]
Khung cua moi chan IC: truc 'ra' = tu tam IC huong ra chan (snap 4 huong), truc 'ngang' vuong goc.
Moi tu 2 pad (1 pad cung net chan IC nguon, 1 pad GND) gan chan IC cung net trong 4 mm -> (ra, ngang, tro cung truc 'ra' hay vuong goc).
In thong ke tren cac ref 2 lop (khong ban sao) va, neu co CAND, so tung tu cua ung vien voi thong ke do.
"""
import collections
import math
import os
import statistics
import sys

import pcbnew


def pt(p):
    return (p.x / 1e6, p.y / 1e6)


def gnd(n):
    return "GND" in n.upper()


def board_caps(path):
    b = pcbnew.LoadBoard(path)
    if b.GetCopperLayerCount() != 2:
        return None
    fps = list(b.GetFootprints())
    ics = [f for f in fps if f.GetReference().startswith("U") and len(list(f.Pads())) >= 8]
    out = []
    for f in fps:
        ref = f.GetReference()
        ps = list(f.Pads())
        if not (ref.startswith("C") and len(ps) == 2):
            continue
        g = [p for p in ps if gnd(p.GetNetname())]
        v = [p for p in ps if p.GetNetname() and not gnd(p.GetNetname())]
        if len(g) != 1 or len(v) != 1:
            continue
        vp = pt(v[0].GetPosition())
        best = None
        for ic in ics:
            c = pt(ic.GetPosition())
            for q in ic.Pads():
                if q.GetNetname() == v[0].GetNetname():
                    qp = pt(q.GetPosition())
                    d = math.hypot(vp[0] - qp[0], vp[1] - qp[1])
                    if d < 4.0 and (best is None or d < best[0]):
                        best = (d, ic, q, qp, c)
        if not best:
            continue
        d, ic, q, qp, c = best
        ax, ay = qp[0] - c[0], qp[1] - c[1]
        if abs(ax) >= abs(ay):
            ox, oy = (1 if ax > 0 else -1), 0
        else:
            ox, oy = 0, (1 if ay > 0 else -1)
        cc = pt(f.GetPosition())
        rx, ry = cc[0] - qp[0], cc[1] - qp[1]
        out_d = rx * ox + ry * oy
        lat = abs(-rx * oy + ry * ox)
        gp = pt(g[0].GetPosition())
        axis_cap = (abs(gp[0] - vp[0]), abs(gp[1] - vp[1]))
        cap_along_out = (abs(axis_cap[0]) > abs(axis_cap[1])) == (ox != 0)
        out.append((ref, round(out_d, 1), round(lat, 1), "cung_truc" if cap_along_out else "vuong_goc", round(d, 1)))
    return out


def main():
    root = sys.argv[1]
    stats = []
    seen = set()
    for dp, dn, fn in os.walk(root):
        if ".history" in dp:
            continue
        for f in fn:
            if f.endswith(".kicad_pcb"):
                try:
                    caps = board_caps(os.path.join(dp, f))
                except Exception:
                    continue
                if caps and len(caps) >= 3:
                    key = len(caps), sum(c[1] for c in caps)
                    if key in seen:
                        continue
                    seen.add(key)
                    stats += caps
    outs = [c[1] for c in stats]; lats = [c[2] for c in stats]
    orient = collections.Counter(c[3] for c in stats)
    print(f"{len(stats)} tu decoupling tren cac ref 2 lop")
    print(f"  o phia CHAN (ra > 0): {sum(1 for o in outs if o > 0)}/{len(outs)}   ra trung vi {statistics.median(outs):.1f} mm (p10 {sorted(outs)[len(outs)//10]:.1f}, p90 {sorted(outs)[9*len(outs)//10]:.1f})")
    print(f"  lech ngang trung vi {statistics.median(lats):.1f} mm (p90 {sorted(lats)[9*len(lats)//10]:.1f})")
    print(f"  huong tu so voi truc ra: {dict(orient)}")
    if len(sys.argv) > 2:
        print("== ung vien", sys.argv[2])
        for ref, od, lat, ori, d in board_caps(sys.argv[2]) or []:
            print(f"   {ref:4s} ra={od:5.1f} ngang={lat:4.1f} {ori:10s} cach chan {d:.1f} mm")


main()
