"""h1_variants.py - H1 tu dong: sinh nhieu phuong an XOAY / DICH linh kien de mo loi di, moi phuong an 1 thu muc.
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" h1_variants.py BASE_PLACE.kicad_pcb PRO INTENT OUT_DIR N "C2,C3,C4"
Rang buoc (de phuong an hop le): courtyard khong de len nhau, trong board, tranh hanh lang USB (intent avoid),
khong chan loi thoat (stub 1.2 mm) cua chan IC khac, pad nguon cua tu <= 3.0 mm toi chan IC (review).
v0 = phuong an goc (de so sanh). Khong tu cham 'dat': moi phuong an phai route + DRC + xem anh.
"""
import json
import math
import os
import random
import shutil
import sys

import pcbnew
from pcbnew import FromMM, VECTOR2I


def box(bb):
    return (bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6)


def pt(p):
    return (p.x / 1e6, p.y / 1e6)


def court(f):
    try:
        poly = f.GetCourtyard(pcbnew.F_CrtYd)
        if poly.OutlineCount() > 0:
            return box(poly.BBox())
    except Exception:
        pass
    bs = [box(p.GetBoundingBox()) for p in f.Pads()]
    return (min(b[0] for b in bs) - .25, min(b[1] for b in bs) - .25, max(b[2] for b in bs) + .25, max(b[3] for b in bs) + .25)


def overlap(a, b, gap=0.0):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def main():
    base, pro, intent_p, out, n, refs = sys.argv[1:7]
    n = int(n); refs = refs.split(",")
    intent = json.load(open(intent_p, encoding="utf-8"))
    dec = {d["cap"]: d for d in intent["decoupling"]}
    avoid = [tuple(a) for d in intent["decoupling"] for a in d.get("avoid", [])]
    random.seed(7)
    os.makedirs(out, exist_ok=True)
    made, tries = 0, 0
    sigs = set()
    while made <= n and tries < 4000:
        tries += 1
        b = pcbnew.LoadBoard(base)
        fps = {f.GetReference(): f for f in b.GetFootprints()}
        bb = box(b.GetBoardEdgesBoundingBox())
        if made > 0:
            for r in refs:
                f = fps[r]
                x, y = pt(f.GetPosition())
                rot = f.GetOrientationDegrees()
                dx = random.choice([-1.0, -0.5, 0, 0, 0.5, 1.0]); dy = random.choice([-1.0, -0.5, 0, 0, 0.5, 1.0])
                nr = random.choice([0, 90, 180, 270])
                f.SetPosition(VECTOR2I(FromMM(x + dx), FromMM(y + dy)))
                f.SetOrientationDegrees(nr)
        sig = tuple((r, round(pt(fps[r].GetPosition())[0], 2), round(pt(fps[r].GetPosition())[1], 2), round(fps[r].GetOrientationDegrees())) for r in refs)
        if sig in sigs:
            continue
        ok = True
        cb = {r: court(f) for r, f in fps.items()}
        for r in refs:
            c = cb[r]
            if c[0] < bb[0] + 0.8 or c[1] < bb[1] + 0.8 or c[2] > bb[2] - 0.8 or c[3] > bb[3] - 0.8:
                ok = False; break
            if any(overlap(c, cb[o], 0.1) for o in cb if o != r):
                ok = False; break
            if any(overlap(c, a_, 0.0) for a_ in avoid):
                ok = False; break
            # pad nguon -> chan IC
            if r in dec:
                ic_ref, ic_pin = dec[r]["pin"].split(".")
                P = [p for p in fps[ic_ref].Pads() if p.GetNumber() == ic_pin][0]
                net = P.GetNetname()
                cp = [p for p in fps[r].Pads() if p.GetNetname() == net]
                if not cp:
                    ok = False; break
                d = math.hypot(pt(cp[0].GetPosition())[0] - pt(P.GetPosition())[0], pt(cp[0].GetPosition())[1] - pt(P.GetPosition())[1])
                if d > 3.0:
                    ok = False; break
            # khong chan loi thoat chan IC khac net
            nets = {p.GetNetname() for p in fps[r].Pads()}
            for o, fo in fps.items():
                if o in refs or not o.startswith("U"):
                    continue
                for q in fo.Pads():
                    if not q.GetNetname() or q.GetNetname() in nets:
                        continue
                    qb = box(q.GetBoundingBox()); w, h = qb[2] - qb[0], qb[3] - qb[1]
                    cx, cy = (qb[0] + qb[2]) / 2, (qb[1] + qb[3]) / 2
                    fx, fy = pt(fo.GetPosition())
                    if w >= 1.6 * h:
                        sg = 1 if cx > fx else -1
                        st = (min(cx, cx + sg * 1.2), cy - .2, max(cx, cx + sg * 1.2), cy + .2)
                    elif h >= 1.6 * w:
                        sg = 1 if cy > fy else -1
                        st = (cx - .2, min(cy, cy + sg * 1.2), cx + .2, max(cy, cy + sg * 1.2))
                    else:
                        continue
                    if overlap(box(fps[r].GetBoundingBox(False)), st, 0.15):
                        ok = False; break
                if not ok:
                    break
            if not ok:
                break
        if not ok:
            continue
        sigs.add(sig)
        d = os.path.join(out, f"v{made}")
        os.makedirs(d, exist_ok=True)
        b.Save(os.path.join(d, "place.kicad_pcb"))
        shutil.copy(pro, os.path.join(d, "place.kicad_pro"))
        shutil.copy(intent_p, os.path.join(d, "intent.json"))
        json.dump({r: [s[1], s[2], s[3]] for r, s in zip(refs, sig)}, open(os.path.join(d, "variant.json"), "w"))
        print(f"v{made}", sig)
        made += 1
    print("tao", made, "phuong an")


main()
