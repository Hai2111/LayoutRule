"""review_run.py WORKDIR : chay ngan hang cau hoi review (learn/review_questions.json) tren board hien tai cua WORKDIR.

- Cau 'auto': may tra loi PASS / FAIL / NEEDS_REVIEW kem bang chung.
- Cau 'image': sinh anh close-up tung khoi (review_img/*.png) va de trong o tra loi; agent PHAI mo anh va dien.
Ket qua: WORKDIR/REVIEW.md. Chay bang KiCad python.
"""
import json
import math
import os
import re
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
KP = sys.executable
sys.path.insert(0, HERE)
import route_audit  # noqa: E402

REF_RANGE = dict(hug=(0, 6.1), under=(0, 19.3), innerp=(24, 40), via=(0, 1.07), bend=(1.18, 2.22))   # 8 board ref (L58)
USB = re.compile(r"(USB|D\+|D-|^/?DP$|^/?DN$|^/?USB_D)", re.I)


def run_check(W):
    r = subprocess.run([KP, os.path.join(HERE, "agent_edit.py"), W, "check"], capture_output=True, text=True)
    return r.stdout


def main(W):
    bq = json.load(open(os.path.join(HERE, "..", "learn", "review_questions.json"), encoding="utf-8"))
    cur = os.path.join(W, open(os.path.join(W, "cur.txt")).read().strip())
    intent = json.load(open(os.path.join(W, "intent.json"), encoding="utf-8"))
    b = pcbnew.LoadBoard(cur)
    out = run_check(W)
    ans = {}

    m = re.search(r"DRC loi (\d+) \| canh bao (\d+) \| net ho (\d+)", out)
    e, wn, uc = (int(x) for x in m.groups()) if m else (-1, -1, -1)
    ans["drc_errors"] = ("PASS" if e == 0 else "FAIL", f"{e} loi, {wn} canh bao")
    ans["unconnected"] = ("PASS" if uc == 0 else "FAIL", f"{uc} net ho")
    bad = [l.strip() for l in out.splitlines() if "[SAI" in l]
    ans["power_order"] = ("PASS" if not bad else "FAIL", "; ".join(bad) or "moi tai dung thu tu")
    for key, tag in (("power_width", "W1"), ("via_pad", "V1"), ("hug", "R4"), ("angle45", "A45"), ("corner45", "C90")):
        ls = [l for l in out.splitlines() if l.startswith(tag)]
        sai = [l for l in ls if " SAI" in l]
        xem = [l for l in ls if "can xem" in l]
        ans[key] = ("FAIL" if sai else ("NEEDS_REVIEW" if xem else "PASS"), " | ".join((sai + xem) or ls)[:400])

    pads = {(f.GetReference(), p.GetNumber()): p for f in b.GetFootprints() for p in f.Pads()}
    def bbox(p):
        q = p.GetBoundingBox(); return q.GetLeft() / 1e6, q.GetTop() / 1e6, q.GetRight() / 1e6, q.GetBottom() / 1e6
    def gap(a, c):
        ax0, ay0, ax1, ay1 = bbox(a); cx0, cy0, cx1, cy1 = bbox(c)
        return math.hypot(max(cx0 - ax1, ax0 - cx1, 0), max(cy0 - ay1, ay0 - cy1, 0))
    # Q04 decap
    rows, worst = [], "PASS"
    for d in intent.get("decoupling", []):
        ref, num = d["pin"].split("."); pin = pads.get((ref, num))
        if pin is None: continue
        cps = [p for (r_, n_), p in pads.items() if r_ == d["cap"] and p.GetNetname() == pin.GetNetname()]
        if not cps: continue
        g = min(gap(pin, c) for c in cps)
        st = "PASS" if g <= 2.0 else ("NEEDS_REVIEW" if g <= 4.0 else "FAIL")
        if st != "PASS" and worst != "FAIL": worst = st
        rows.append(f"{d['cap']}->{d['pin']} {g:.2f} mm")
    ans["decap_distance"] = (worst, "; ".join(rows) or "intent khong co decoupling")
    # Q09 nguon duoi than IC
    pnets = set(intent.get("power_chains", {}).keys())
    hits = []
    for f in b.GetFootprints():
        if not f.GetReference().startswith("U") or len(f.Pads()) < 5: continue
        xs, ys = [], []
        for it in f.GraphicalItems():
            if it.GetLayer() == pcbnew.F_Fab and it.GetClass() != "PCB_TEXT":
                q = it.GetBoundingBox(); xs += [q.GetLeft() / 1e6, q.GetRight() / 1e6]; ys += [q.GetTop() / 1e6, q.GetBottom() / 1e6]
        if not xs: continue
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        for t in b.GetTracks():
            if t.GetClass() != "PCB_TRACK" or t.GetNetname() not in pnets or t.GetLayer() != pcbnew.F_Cu: continue
            a, c = t.GetStart(), t.GetEnd(); L = t.GetLength() / 1e6
            inside = sum(1 for i in range(11) if x0 < (a.x + (c.x - a.x) * i / 10) / 1e6 < x1 and y0 < (a.y + (c.y - a.y) * i / 10) / 1e6 < y1) / 11
            if L * inside > 0.4:
                hits.append(f"{t.GetNetname()} {L * inside:.1f} mm duoi {f.GetReference()}")
    ans["power_under_ic"] = ("FAIL" if hits else "PASS", "; ".join(hits) or "khong co")
    # Q10 GND
    gtr = sum(1 for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and "GND" in t.GetNetname())
    zs = [z for z in b.Zones() if "GND" in z.GetNetname()]
    lays = {b.GetLayerName(l) for z in zs for l in z.GetLayerSet().Seq()}
    solid = all(z.GetPadConnection() == pcbnew.ZONE_CONNECTION_FULL for z in zs)
    ok = gtr == 0 and solid and {"F.Cu", "B.Cu"} <= lays
    ans["gnd_solid"] = ("PASS" if ok else "FAIL", f"{gtr} doan GND, zone {sorted(lays)}, solid={solid}")
    # Q11 USB vias, Q14 signal vias, Q12 power transitions
    vias = [v for v in b.GetTracks() if v.GetClass() == "PCB_VIA"]
    usbv = {}
    sigv = {}
    for v in vias:
        n = v.GetNetname()
        if USB.search(n) and "VBUS" not in n.upper(): usbv[n] = usbv.get(n, 0) + 1
        if n not in pnets and "GND" not in n: sigv[n] = sigv.get(n, 0) + 1
    ans["usb_vias"] = ("PASS" if not usbv else "NEEDS_REVIEW", str(usbv) + (" (can chung minh bat buoc, L63)" if usbv else ""))
    over = {n: c for n, c in sigv.items() if c > 2}
    ans["signal_vias"] = ("FAIL" if over else "PASS", f"> 2 via: {over}" if over else f"via tin hieu: {sigv}")
    single = []
    for v in vias:
        if v.GetNetname() not in pnets: continue
        q = v.GetPosition(); near = [u for u in vias if u is not v and u.GetNetname() == v.GetNetname() and (u.GetPosition() - q).EuclideanNorm() < 1.5e6]
        if not near:
            pn = min(pads.items(), key=lambda kv: (kv[1].GetPosition() - q).EuclideanNorm() if kv[1].GetNetname() == v.GetNetname() else 1e18)
            single.append(f"{v.GetNetname()} ({q.x / 1e6:.2f},{q.y / 1e6:.2f}) gan {pn[0][0]}.{pn[0][1]}")
    ans["power_transition_vias"] = ("PASS" if not single else "NEEDS_REVIEW", ("via don: " + "; ".join(single)) if single else "khong co cho doi lop don via")
    # Q13 route audit
    ra = route_audit.audit(cur)
    if ra:
        offs = [f"{k}={ra[k]:.2f} ngoai {lo}-{hi}" for k, (lo, hi) in REF_RANGE.items() if k != "bend" and not (lo <= ra[k] <= hi) and not (k == "innerp" and ra[k] == 0)]   # bend chi de tham khao: ban owner sua (cap vi sai doi xung, bus deu) co bend cao hon (L72)
        ans["route_audit"] = ("FAIL" if offs else "PASS", "; ".join(offs) or "trong khoang ref: " + ", ".join(f"{k}={ra[k]:.2f}" for k in REF_RANGE))
    else:
        ans["route_audit"] = ("NEEDS_REVIEW", "khong co track tin hieu")
    # Q15 schematic changes
    log = [json.loads(l) for l in open(os.path.join(W, "log.jsonl"), encoding="utf-8")] if os.path.exists(os.path.join(W, "log.jsonl")) else []
    sn = [x for x in log if str(x.get("what", "")).startswith("setnet")]
    scf = os.path.join(W, "SCHEMATIC_CHANGES.md")
    if not sn:
        ans["sch_changes"] = ("PASS", "khong doi netlist tren board")
    else:
        ans["sch_changes"] = ("NEEDS_REVIEW" if os.path.exists(scf) else "FAIL",
                              f"{len(sn)} lan setnet; " + ("da ghi SCHEMATIC_CHANGES.md, schematic chua sua theo" if os.path.exists(scf) else "CHUA ghi SCHEMATIC_CHANGES.md"))
    # Q16 mep board
    EDGE = json.load(open(os.path.join(W, os.path.splitext(os.path.basename(cur))[0] + '.kicad_pro'), encoding='utf-8'))['board']['design_settings']['rules'].get('min_copper_edge_clearance', 0.5) if os.path.exists(os.path.join(W, os.path.splitext(os.path.basename(cur))[0] + '.kicad_pro')) else 0.5   # luat du an, khong tu dat (owner de trunk 0.32 mm voi luat 0.3)
    eb = b.GetBoardEdgesBoundingBox(); L0, T0, R0, B0 = eb.GetLeft() / 1e6, eb.GetTop() / 1e6, eb.GetRight() / 1e6, eb.GetBottom() / 1e6
    near_e = []
    for t in b.GetTracks():
        w = (t.GetWidth(pcbnew.F_Cu) if t.GetClass() == "PCB_VIA" else t.GetWidth()) / 2e6
        for q in (t.GetStart(), t.GetEnd()):
            x, y = q.x / 1e6, q.y / 1e6
            d = min(x - L0, R0 - x, y - T0, B0 - y) - w
            if d < EDGE - 1e-3: near_e.append(f"{t.GetNetname()} ({x:.2f},{y:.2f}) {d:.2f} mm")
    ans["edge_clear"] = ("PASS" if not near_e else "FAIL", "; ".join(sorted(set(near_e))[:6]) or "dat")

    # Q22: moi tu decap co via GND trong 1.5 mm quanh pad GND cua no (owner rai via khau co chu dich, L71)
    gv = [v.GetPosition() for v in b.GetTracks() if v.GetClass() == "PCB_VIA" and "GND" in v.GetNetname()]
    miss = []
    for dd in intent.get("decoupling", []):
        for (r_, n_), p_ in pads.items():
            if r_ == dd["cap"] and "GND" in p_.GetNetname():
                dmin = min(((q - p_.GetPosition()).EuclideanNorm() / 1e6 for q in gv), default=99)
                if dmin > 1.5: miss.append(f"{dd['cap']}.{n_} via GND gan nhat {dmin:.1f} mm")
    ans["decap_gnd_via"] = ("PASS" if not miss else "FAIL", "; ".join(miss) or "moi tu decap co via GND trong 1.5 mm")
    # Q17 ky hieu silkscreen
    vb = [v.GetBoundingBox() for v in b.GetTracks() if v.GetClass() == "PCB_VIA" and not v.IsTented(pcbnew.F_Mask)]   # via tented: chu de len duoc
    pbs = [(f.GetReference(), p.GetNumber(), p.GetBoundingBox()) for f in b.GetFootprints() for p in f.Pads()]
    tbs, probs = [], []
    for f in b.GetFootprints():
        r = f.Reference()
        if not r.IsVisible() or b.GetLayerName(r.GetLayer()) not in ("F.Silkscreen", "B.Silkscreen"):
            probs.append(f"{f.GetReference()} khong in ({b.GetLayerName(r.GetLayer())})"); continue
        tb = r.GetBoundingBox()
        hp = [f"{a}.{n}" for a, n, q in pbs if tb.Intersects(q)]
        hv = sum(1 for q in vb if tb.Intersects(q))
        ht = [x for x, q in tbs if tb.Intersects(q)]
        if hp or hv or ht or not eb.Contains(tb):
            probs.append(f"{f.GetReference()}: de pad {hp[:2]} via {hv} chu {ht} ngoai_board {not eb.Contains(tb)}")
        tbs.append((f.GetReference(), tb))
    def _crt(f):
        cy = f.GetCourtyard(pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd)
        return cy.BBox() if cy.OutlineCount() else f.GetBoundingBox(False)
    def _body(f):      # than nhin thay duoc = pad + F.Fab (nguoi doc gan chu theo than/pad, khong theo courtyard)
            import pcbnew as _p
            xs, ys = [], []
            for p in f.Pads():
                q = p.GetBoundingBox(); xs += [q.GetLeft(), q.GetRight()]; ys += [q.GetTop(), q.GetBottom()]
            for it in f.GraphicalItems():
                if it.GetLayer() in (_p.F_Fab, _p.B_Fab) and it.GetClass() != "PCB_TEXT":
                    q = it.GetBoundingBox(); xs += [q.GetLeft(), q.GetRight()]; ys += [q.GetTop(), q.GetBottom()]
            return _p.BOX2I(_p.VECTOR2I(min(xs), min(ys)), _p.VECTOR2L(max(xs) - min(xs), max(ys) - min(ys))) if xs else f.GetBoundingBox(False)
    cr = {f.GetReference(): _body(f) for f in b.GetFootprints()}
    amb = []
    for f in b.GetFootprints():
        tc = f.Reference().GetBoundingBox().GetCenter()
        dd = lambda q: math.hypot(max(q.GetLeft() - tc.x, 0, tc.x - q.GetRight()), max(q.GetTop() - tc.y, 0, tc.y - q.GetBottom())) / 1e6
        own = dd(cr[f.GetReference()]); oth = min(((dd(q), r) for r, q in cr.items() if r != f.GetReference()), default=(99, ""))
        if oth[0] < own - 0.05:
            amb.append(f"{f.GetReference()} gan {oth[1]} ({oth[0]:.1f} mm) hon chinh no ({own:.1f} mm)")
    ans["silk_near_own"] = ("PASS" if not amb else "FAIL", "; ".join(amb) or "moi ky hieu gan linh kien cua no nhat")
    fabonly = probs and all("khong in (F.Fab)" in x for x in probs)
    ans["silk_refs"] = ("PASS" if not probs else ("NEEDS_REVIEW" if fabonly else "FAIL"), "; ".join(probs[:8]) or "moi ky hieu in tren silkscreen, khong de pad/via/chu khac")

    # anh close-up cho cau image: moi IC/connector 1 anh
    img = os.path.join(W, "review_img"); os.makedirs(img, exist_ok=True)
    shots = []
    for f in b.GetFootprints():
        r = f.GetReference()
        if r[0] in "UJQ":
            q = f.GetBoundingBox(False); m_ = 3.0
            crop = f"{q.GetLeft() / 1e6 - m_:.1f},{q.GetTop() / 1e6 - m_:.1f},{q.GetRight() / 1e6 + m_:.1f},{q.GetBottom() / 1e6 + m_:.1f}"
            pth = os.path.join(img, f"{r}.png")
            subprocess.run([KP, os.path.join(HERE, "shot.py"), pth, cur], env=dict(os.environ, CROP=crop, S="60", LABELS="1"), capture_output=True)
            shots.append(pth)
    full = os.path.join(img, "_board.png")
    subprocess.run([KP, os.path.join(HERE, "shot.py"), full, cur], env=dict(os.environ, LABELS="1"), capture_output=True)

    lines = [f"# REVIEW {os.path.basename(cur)}", "", "| ID | Cau hoi | Luat | Ket qua | Bang chung |", "|---|---|---|---|---|"]
    cnt = {}
    # cau tra loi anh + ly do cho NEEDS_REVIEW do agent ghi: WORKDIR/review_answers.json {ID: {status, evidence}}
    af = os.path.join(W, "review_answers.json")
    given = json.load(open(af, encoding="utf-8")) if os.path.exists(af) else {}
    def state(q):
        if q["mode"] == "auto":
            st, ev = ans.get(q["check"], ("NEEDS_REVIEW", "chua co checker"))
            if st == "NEEDS_REVIEW" and q["id"] in given and given[q["id"]].get("status") == "JUSTIFIED":
                return "JUSTIFIED", ev + " | ly do: " + given[q["id"]]["evidence"]
            return st, ev
        g = given.get(q["id"])
        return (g["status"], g["evidence"]) if g else ("IMAGE", "agent chua tra loi (mo anh roi ghi vao review_answers.json)")
    pr_fail = [q["id"] for q in bq["questions"] if q.get("stage") != "finish" and state(q)[0] not in ("PASS", "JUSTIFIED")]
    for q in bq["questions"]:
        if q.get("stage") == "finish" and pr_fail:
            st, ev = "DEFERRED", "chi xet sau khi place/route dat het (chua dat: " + ",".join(pr_fail) + ")"
        else:
            st, ev = state(q)
        cnt[st] = cnt.get(st, 0) + 1
        lines.append(f"| {q['id']} | {q['q']} | {', '.join(q['rules'])} | {st} | {ev.replace('|', '/')} |")
    lines += ["", "Anh close-up: " + ", ".join(os.path.basename(s) for s in [full] + shots)]
    open(os.path.join(W, "REVIEW.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(json.dumps(cnt), "->", os.path.join(W, "REVIEW.md"))
    for q in bq["questions"]:
        if not (q.get("stage") == "finish" and pr_fail):
            st, ev = state(q)
            if st not in ("PASS", "JUSTIFIED"): print(f"  {q['id']} [{q.get('stage')}] {st}: {ev[:220]}")
    print("  cong sang giai doan finish (silkscreen):", "MO" if not pr_fail else "DONG, con " + ",".join(pr_fail))


if __name__ == "__main__":
    main(sys.argv[1])
