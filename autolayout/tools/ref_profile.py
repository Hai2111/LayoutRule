"""ref_profile.py - tu dong quet ref design va so layout ung vien voi dai so lieu cua ref.
  python: "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe"
  scan:    ref_profile.py scan  <ref/Kicad folder>  <profile.json>
  compare: ref_profile.py compare <candidate.kicad_pcb> <profile.json> [--md out.md]

Chi so (cung ham cho ref va ung vien -> so sanh cong bang), CHI board 2 lop:
  bcu_share      : B.Cu non-GND / tong track non-GND (muc cat plane GND, D-2L)
  via_per_100mm  : so via moi 100 mm track
  signal_w_p50   : be rong track tin hieu trung vi (mm);  power_w_p50: be rong track nguon trung vi
  via_dia_mode   : duong kinh via pho bien nhat
  decap_p50/p90  : khoang cach pad nguon tu -> pad IC cung net (mm)
  decap_gnd_p50  : khoang cach pad GND tu -> via GND gan nhat (mm)
  under_ic_share : ti le chieu dai track nam trong bbox pad cua IC (U*) (xap xi 'duoi than IC')
Neu khong co ref nao hop le -> in GLOBAL STOP (owner_decisions: reference_missing_behavior).
Khong thay the owner review; chi bao ung vien nam NGOAI dai ref o chi so nao.
"""
import collections
import hashlib
import json
import math
import os
import statistics
import sys

import pcbnew

PWR = ("VBUS", "VCC", "VDD", "VIN", "VBAT", "+5V", "5V", "+3V3", "3V3", "+3.3V", "V3", "+12V", "12V", "VOUT")


def pt(p):
    return (p.x / 1e6, p.y / 1e6)


def box(bb):
    return (bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6)


def is_gnd(n):
    u = n.upper()
    return "GND" in u or u in ("0V", "VSS")


def is_pwr(n):
    u = n.upper().split("/")[-1]
    return (not is_gnd(n)) and (u in PWR or any(u.startswith(p) for p in PWR) or u.endswith(("V3", "V5", "5V", "3V3")))


def pct(vals, p):
    if not vals:
        return None
    v = sorted(vals)
    return v[min(len(v) - 1, int(round((len(v) - 1) * p)))]


def metrics(path):
    b = pcbnew.LoadBoard(path)
    if b.GetCopperLayerCount() != 2:
        return None
    fps = list(b.GetFootprints())
    if len(fps) < 15:
        return None
    L = {"F": 0.0, "B": 0.0}
    widths_sig, widths_pwr = [], []
    segs = []
    for t in b.GetTracks():
        if t.GetClass() != "PCB_TRACK":
            continue
        n = t.GetNetname()
        ln = t.GetLength() / 1e6
        a, c = pt(t.GetStart()), pt(t.GetEnd())
        if not is_gnd(n):
            L["F" if t.GetLayer() == pcbnew.F_Cu else "B"] += ln
            (widths_pwr if is_pwr(n) else widths_sig).extend([t.GetWidth() / 1e6] * max(1, int(ln / 0.5)))
        segs.append((n, t.GetLayer() == pcbnew.F_Cu, a, c))
    vias = []
    vdia = collections.Counter()
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            vias.append((t.GetNetname(), pt(t.GetPosition())))
            vdia[round(t.GetWidth(pcbnew.F_Cu) / 1e6, 2)] += 1
    total = L["F"] + L["B"]
    if total < 20:
        return None
    # pad tables
    pads = []
    for f in fps:
        for p in f.Pads():
            pads.append((f.GetReference(), p.GetNumber(), p.GetNetname(), pt(p.GetPosition()), box(p.GetBoundingBox())))
    # decap
    dec, decg = [], []
    gvias = [v[1] for v in vias if is_gnd(v[0])]
    for f in fps:
        r = f.GetReference()
        ps = list(f.Pads())
        if not (r.startswith("C") and len(ps) == 2):
            continue
        nets = [p.GetNetname() for p in ps]
        pw = [p for p in ps if is_pwr(p.GetNetname())]
        gn = [p for p in ps if is_gnd(p.GetNetname())]
        if len(pw) == 1 and len(gn) == 1:
            pp = pt(pw[0].GetPosition())
            best = min((math.hypot(pp[0] - q[3][0], pp[1] - q[3][1]) for q in pads if q[0].startswith("U") and q[2] == pw[0].GetNetname()), default=None)
            if best is not None:
                dec.append(best)
            gp = pt(gn[0].GetPosition())
            gv = min((math.hypot(gp[0] - v[0], gp[1] - v[1]) for v in gvias), default=None)
            if gv is not None:
                decg.append(gv)
    # under IC (pad bbox union) - cung ham cho moi board
    icb = []
    for f in fps:
        if f.GetReference().startswith("U"):
            bs = [box(p.GetBoundingBox()) for p in f.Pads()]
            if len(bs) >= 8:
                icb.append((f.GetReference(), min(x[0] for x in bs), min(x[1] for x in bs), max(x[2] for x in bs), max(x[3] for x in bs)))
    under = 0.0
    sigL = 0.0
    for n, top, a, c in segs:
        if is_gnd(n):
            continue
        ln = math.hypot(c[0] - a[0], c[1] - a[1])
        sigL += ln
        if not top:
            continue
        mx, my = (a[0] + c[0]) / 2, (a[1] + c[1]) / 2
        for ref, x0, y0, x1, y1 in icb:
            own = any(q[0] == ref and q[2] == n for q in pads)
            if not own and x0 + 0.3 < mx < x1 - 0.3 and y0 + 0.3 < my < y1 - 0.3:
                under += ln
                break
    return {
        "footprints": len(fps), "track_mm": round(total, 1),
        "bcu_share": round(L["B"] / total, 3),
        "via_per_100mm": round(100.0 * len(vias) / total, 2),
        "signal_w_p50": pct(widths_sig, 0.5), "power_w_p50": pct(widths_pwr, 0.5),
        "via_dia_mode": (vdia.most_common(1)[0][0] if vdia else None),
        "decap_p50": pct(dec, 0.5), "decap_p90": pct(dec, 0.9), "decap_n": len(dec),
        "decap_gnd_p50": pct(decg, 0.5), "decap_gnd_n": len(decg),
        "under_ic_share": round(under / sigL, 3) if sigL else None,
    }


def scan(root, out):
    seen, prof = {}, {}
    for dp, dn, fn in os.walk(root):
        if ".history" in dp:
            continue
        for f in fn:
            if not f.endswith(".kicad_pcb"):
                continue
            p = os.path.join(dp, f)
            try:
                m = metrics(p)
            except Exception as e:
                print("loi", p, e)
                continue
            if not m:
                continue
            key = (m["footprints"], m["track_mm"])
            if key in seen:
                continue                      # trung (ban sao cung du an)
            seen[key] = p
            prof[os.path.relpath(p, root)] = m
            print("ref", os.path.relpath(p, root), m["footprints"], "fp", m["track_mm"], "mm")
    if not prof:
        print("GLOBAL STOP: khong co ref 2 lop hop le trong", root)
        sys.exit(2)
    json.dump(prof, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("profile:", len(prof), "ref ->", out)


KEYS = [
    ("bcu_share", "ti le B.Cu (non-GND)", "lower"),
    ("via_per_100mm", "via / 100 mm track", "lower"),
    ("signal_w_p50", "rong track tin hieu (mm)", None),
    ("power_w_p50", "rong track nguon (mm)", None),
    ("decap_p50", "tu: pad nguon -> chan IC trung vi (mm)", "lower"),
    ("decap_gnd_p50", "tu: pad GND -> via GND trung vi (mm)", "lower"),
    ("under_ic_share", "ti le track duoi pad-bbox IC", "lower"),
]


def compare(cand, prof_p, md=None):
    prof = json.load(open(prof_p, encoding="utf-8"))
    m = metrics(cand)
    if not m:
        print("ung vien khong hop le (can board 2 lop, >=15 linh kien, >=20 mm track)")
        sys.exit(2)
    rows, flags = [], []
    for k, label, bad in KEYS:
        rv = sorted(v[k] for v in prof.values() if v.get(k) is not None)
        cv = m.get(k)
        if not rv or cv is None:
            rows.append((label, "-", "-", cv, "")); continue
        lo, med, hi = rv[0], statistics.median(rv), rv[-1]
        status = ""
        if bad == "lower" and cv > hi:
            status = "NGOAI DAI (cao hon moi ref)"
        elif bad == "lower" and cv > med * 1.5 and cv > lo:
            status = "cao hon trung vi 1.5x"
        elif bad is None and (cv < lo or cv > hi):
            status = "ngoai dai"
        if status:
            flags.append(f"{label}: ung vien {cv} | ref {lo}..{hi} (trung vi {round(med, 3)}) -> {status}")
        rows.append((label, f"{lo}..{hi}", round(med, 3), cv, status))
    print(f"So voi {len(prof)} ref 2 lop (khong tinh ban sao):")
    for r_ in rows:
        print(f"  {r_[0]:42s} ref {str(r_[1]):14s} p50 {str(r_[2]):7s} ung vien {str(r_[3]):7s} {r_[4]}")
    print("KET LUAN:", "khong co chi so nao ngoai dai" if not flags else f"{len(flags)} chi so lech khoi ref")
    for f_ in flags:
        print("  -", f_)
    if md:
        with open(md, "w", encoding="utf-8") as fh:
            fh.write("# So voi ref design (tu dong)\n\n| Chi so | Ref (min..max) | p50 | Ung vien | |\n|---|---|---|---|---|\n")
            for r_ in rows:
                fh.write(f"| {r_[0]} | {r_[1]} | {r_[2]} | {r_[3]} | {r_[4]} |\n")
            fh.write("\n" + "\n".join("- " + f for f in flags) + "\n")


if __name__ == "__main__":
    if sys.argv[1] == "scan":
        scan(sys.argv[2], sys.argv[3])
    else:
        compare(sys.argv[2], sys.argv[3], sys.argv[sys.argv.index("--md") + 1] if "--md" in sys.argv else None)
