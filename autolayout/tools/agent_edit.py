"""agent_edit.py - cong cu cho TAC TU QUAN SAT: moi lenh tao 1 buoc moi (stepNN.kicad_pcb) + ghi nhat ky, hoan tac duoc.
  KP agent_edit.py WORK init BOARD.kicad_pcb PROJECT.kicad_pro INTENT.json [SCHEMATIC.kicad_sch]
  KP agent_edit.py WORK start [layout_intent.json] [session.json | --training]
        CONG BAT BUOC truoc moi lenh sua (LayoutRule SESSION_PIPELINE):
        (1) buoc 0 session_start.py review -> WORK/session_start/SESSION_START.md; tac tu mo tung anh, thay het TODO
        (2) cong reference session_gate.py preflight session.json; thieu reference = BLOCKED toan board.
            --training: bo qua cong (2) cho bai luyen tap, ghi ro vao nhat ky; khong dung cho du an that.
  KP agent_edit.py WORK gate                        kiem lai 2 cong (lenh sua tu goi)
  KP agent_edit.py WORK move REF X Y [ROT]          dat linh kien (mm, do)
  KP agent_edit.py WORK nudge REF DX DY [DROT]      dich tuong doi
  KP agent_edit.py WORK rip NET[,NET...]            go day + via cua net
  KP agent_edit.py WORK route NET[,NET...]          di net (pyroute, theo thu tu, dung intent)
  KP agent_edit.py WORK check                       DRC + via tin hieu + net ho cua buoc hien tai
  KP agent_edit.py WORK undo                        quay ve buoc truoc
  KP agent_edit.py WORK show OUT.png [x0,y0,x1,y1]  anh (co ten net) toan board hoac vung (mm, toa do board)
Giu hay bo mot ban sua (thu tu uu tien): DRC khong xau hon -> khong them loi vi tri tuong doi (self_review R1 duoi than,
R2 kep giua pad, R3 thu tu nguon) -> nguon khong bi day xuong lop duoi -> SAU CUNG moi xet via/chieu dai.
Buoc hien tai = WORK/cur.txt. Nhat ky = WORK/log.jsonl. Loi route (FAIL) van luu buoc nhung bao ro.
"""
import json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); from kenv import KP, CLI, FP  # KiCad tim tu dong (kenv.py)
W = os.path.abspath(sys.argv[1]); CMD = sys.argv[2]; A = sys.argv[3:]
ENV = dict(os.environ, PYROUTE_RES="0.05", MSYS_NO_PATHCONV="1")


def cur():
    return os.path.join(W, open(os.path.join(W, "cur.txt")).read().strip())


def new_step(tag):
    """so buoc = lon nhat da tung dung + 1 (khong dem file: file buoc bi huy da bi xoa)"""
    import re as _re
    nums = [int(m.group(1)) for f in os.listdir(W) for m in [_re.match(r"step(\d+)_", f)] if m]
    lp = os.path.join(W, "log.jsonl")
    if os.path.exists(lp):
        for l in open(lp, encoding="utf-8"):
            m = _re.match(r"step(\d+)_", json.loads(l).get("step", ""))
            if m:
                nums.append(int(m.group(1)))
    n = max(nums) + 1 if nums else 0
    return os.path.join(W, f"step{n:02d}_{tag}.kicad_pcb")


def drop_step(name):
    """xoa moi file cua 1 buoc (pcb/pro/prl/dru): buoc bi hoan tac la rac"""
    base = os.path.join(W, name[:-10])
    for ext in (".kicad_pcb", ".kicad_pro", ".kicad_prl", ".kicad_dru"):
        if os.path.exists(base + ext):
            os.remove(base + ext)


def commit(path, what, extra=None):
    shutil.copy(os.path.join(W, "project.kicad_pro"), path[:-10] + ".kicad_pro")
    if os.path.exists(os.path.join(W, "project.kicad_dru")):   # luat rieng (vd ngoai le land pattern) di theo moi buoc
        shutil.copy(os.path.join(W, "project.kicad_dru"), path[:-10] + ".kicad_dru")
    prev = open(os.path.join(W, "cur.txt")).read().strip() if os.path.exists(os.path.join(W, "cur.txt")) else ""
    open(os.path.join(W, "cur.txt"), "w").write(os.path.basename(path))
    with open(os.path.join(W, "log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(ts=time.strftime("%H:%M:%S"), step=os.path.basename(path), prev=prev, what=what, **(extra or {})), ensure_ascii=False) + "\n")
    print("buoc moi:", os.path.basename(path))


def layoutrule_tools():
    """thu muc tools/ cua LayoutRule: trong repo (autolayout/ nam trong repo) hoac ban clone o ../rule"""
    for c in (os.environ.get("LAYOUTRULE_TOOLS", ""), os.path.join(HERE, "..", "..", "tools"), os.path.join(HERE, "..", "..", "rule", "tools")):
        if c and os.path.isfile(os.path.join(c, "session_start.py")):
            return os.path.abspath(c)
    sys.exit("khong tim thay LayoutRule tools/session_start.py (dat LAYOUTRULE_TOOLS)")


def gate():
    """True khi ca 2 cong da qua; in ly do neu chua"""
    st = os.path.join(W, "gate.json")
    if not os.path.exists(st):
        print("BLOCKED: chua chay 'start' (buoc 0 + cong reference)"); return False
    g = json.load(open(st, encoding="utf-8"))
    r = subprocess.run([sys.executable, os.path.join(layoutrule_tools(), "session_start.py"), "check", os.path.join(W, "session_start", "SESSION_START.md")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("BLOCKED buoc 0:", (r.stdout + r.stderr).strip().splitlines()[-1]); return False
    if g["reference"] not in ("READY", "TRAINING_SKIP"):
        print("BLOCKED cong reference:", g["reference"]); return False
    return True


def stats(path):
    import pcbnew
    t = list(pcbnew.LoadBoard(path).GetTracks()); v = {}
    for x in t:
        if x.GetClass() == "PCB_VIA" and "GND" not in x.GetNetname():
            v[x.GetNetname()] = v.get(x.GetNetname(), 0) + 1
    return v, round(sum(x.GetLength() for x in t if x.GetClass() != "PCB_VIA") / 1e6, 1)


if CMD == "init":
    os.makedirs(W, exist_ok=True)
    def _cp(s, d):                      # file da nam san trong WORK (vd intent.json) -> khong copy chinh no (L76)
        if not (os.path.exists(d) and os.path.samefile(s, d)):
            shutil.copy(s, d)
    _cp(A[1], os.path.join(W, "project.kicad_pro")); _cp(A[2], os.path.join(W, "intent.json"))
    if len(A) > 3:
        _cp(A[3], os.path.join(W, "schematic.kicad_sch"))
    p = new_step("init"); shutil.copy(A[0], p); commit(p, f"init tu {A[0]}")

elif CMD == "start":
    lt = layoutrule_tools(); out = os.path.join(W, "session_start"); os.makedirs(out, exist_ok=True)
    rb = os.path.join(out, "review_board.kicad_pcb"); shutil.copy(cur(), rb)
    shutil.copy(os.path.join(W, "project.kicad_pro"), rb[:-10] + ".kicad_pro")
    if os.path.exists(os.path.join(W, "schematic.kicad_sch")):
        shutil.copy(os.path.join(W, "schematic.kicad_sch"), rb[:-10] + ".kicad_sch")
        for f in os.listdir(W):            # schematic phan cap: sheet con + bang thu vien phai nam canh, neu khong parity bao gia (L76)
            if (f.endswith(".kicad_sch") and f != "schematic.kicad_sch") or f in ("sym-lib-table", "fp-lib-table"):
                shutil.copy(os.path.join(W, f), os.path.join(out, f))
        if os.path.isdir(os.path.join(W, "lib")):
            shutil.copytree(os.path.join(W, "lib"), os.path.join(out, "lib"), dirs_exist_ok=True)
    li = A[0] if A and A[0].endswith(".json") and "session" not in os.path.basename(A[0]) else None
    if not li:
        li = os.path.join(out, "layout_intent.json")
        json.dump({"nets": {}, "hot_loops": [], "note": "ASSUMED: chua co layout_intent cua du an"}, open(li, "w"))
    r = subprocess.run([KP, os.path.join(lt, "session_start.py"), "review", rb, li, "--out", out], capture_output=True, text=True)
    print((r.stdout + r.stderr).strip()[-600:])
    man = next((a for a in A if os.path.basename(a).startswith("session") and a.endswith(".json")), None)
    if "--training" in A:
        ref = "TRAINING_SKIP"
    elif man:
        rr = subprocess.run([sys.executable, os.path.join(lt, "session_gate.py"), "preflight", man, "--output-dir", os.path.join(W, "session_review")], capture_output=True, text=True)
        ref = "READY" if rr.returncode == 0 else "BLOCKED"
        print((rr.stdout + rr.stderr).strip()[-600:])
    else:
        ref = "BLOCKED (khong co session.json reference manifest)"
    json.dump({"board": os.path.basename(cur()), "reference": ref}, open(os.path.join(W, "gate.json"), "w"))
    with open(os.path.join(W, "log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(ts=time.strftime("%H:%M:%S"), step=os.path.basename(cur()), prev=os.path.basename(cur()), what=f"start: buoc 0 + reference={ref}"), ensure_ascii=False) + "\n")
    print("reference:", ref, "| mo tung anh trong", out, "va thay het TODO trong SESSION_START.md, roi chay 'gate'")

elif CMD == "gate":
    print("GATE OK" if gate() else "")

elif CMD in ("move", "nudge", "swap", "rip", "ripnear", "route", "cleanvias", "pour", "padconn", "track", "via", "delat", "setnet", "reftext", "dogbone", "tidy", "oct45", "gndsolid", "silkrefs", "placesmall", "chamfer") and not gate():
    sys.exit(3)

elif CMD in ("move", "nudge"):
    import pcbnew
    from pcbnew import FromMM, VECTOR2I
    b = pcbnew.LoadBoard(cur()); f = b.FindFootprintByReference(A[0])
    x, y, r = f.GetPosition().x / 1e6, f.GetPosition().y / 1e6, f.GetOrientationDegrees()
    if CMD == "move":
        x, y = float(A[1]), float(A[2]); r = float(A[3]) if len(A) > 3 else r
    else:
        x, y = x + float(A[1]), y + float(A[2]); r = r + (float(A[3]) if len(A) > 3 else 0)
    f.SetOrientationDegrees(r); f.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
    p = new_step(f"{CMD}_{A[0]}"); b.Save(p); commit(p, f"{CMD} {A[0]} -> ({x:.2f},{y:.2f}) {r:.0f}deg")

elif CMD == "rip":
    import pcbnew
    b = pcbnew.LoadBoard(cur()); ns = set(A[0].split(",")); k = 0
    for t in list(b.GetTracks()):
        if t.GetNetname() in ns:
            b.Remove(t); k += 1
    p = new_step("rip"); b.Save(p); commit(p, f"rip {A[0]} ({k} doan)")

elif CMD == "ripnear":     # ripnear REF[,REF] NET : go doan/via cua NET cham pad cua cac linh kien nay (vd GND sau khi doi cho)
    import pcbnew
    b = pcbnew.LoadBoard(cur()); refs = A[0].split(","); net = A[1]
    pts = [(p.GetPosition().x, p.GetPosition().y) for r in refs for p in b.FindFootprintByReference(r).Pads() if p.GetNetname() == net]
    near = lambda q: any(abs(q.x - x) < 1.2e6 and abs(q.y - y) < 1.2e6 for x, y in pts)
    k = 0
    for t in list(b.GetTracks()):
        if t.GetNetname() == net and (near(t.GetStart()) or near(t.GetEnd())):
            b.Remove(t); k += 1
    p = new_step("ripnear"); b.Save(p); commit(p, f"ripnear {A[0]} {net} ({k} doan)")

elif CMD == "swap":      # swap A B : doi cho + huong 2 linh kien
    import pcbnew
    b = pcbnew.LoadBoard(cur()); fa, fb = b.FindFootprintByReference(A[0]), b.FindFootprintByReference(A[1])
    pa, ra = pcbnew.VECTOR2I(fa.GetPosition().x, fa.GetPosition().y), fa.GetOrientationDegrees()
    pb, rb = pcbnew.VECTOR2I(fb.GetPosition().x, fb.GetPosition().y), fb.GetOrientationDegrees()
    fa.SetOrientationDegrees(rb); fa.SetPosition(pb); fb.SetOrientationDegrees(ra); fb.SetPosition(pa)
    p = new_step(f"swap_{A[0]}_{A[1]}"); b.Save(p); commit(p, f"swap {A[0]} <-> {A[1]}")

elif CMD == "cleanvias":   # cleanvias NET : bo via mo coi (khong cham pad, khong cham doan day nao) - thuong sot lai sau khi doi cho
    import pcbnew
    b = pcbnew.LoadBoard(cur()); net = A[0]
    segs = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() == net]
    pads = [p for f in b.GetFootprints() for p in f.Pads() if p.GetNetname() == net]
    k = 0
    for v in [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == net]:
        q = v.GetPosition()
        touch = any((s.GetStart().x, s.GetStart().y) == (q.x, q.y) or (s.GetEnd().x, s.GetEnd().y) == (q.x, q.y) for s in segs) or any(p.HitTest(q) for p in pads)
        if not touch:
            b.Remove(v); k += 1
    seen, dup = set(), 0   # doan day trung lap (router di lai len doan cu)
    for t in list(b.GetTracks()):
        if t.GetClass() != "PCB_TRACK": continue
        e = tuple(sorted([(t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)]))
        key = (t.GetNetname(), t.GetLayer(), t.GetWidth(), e)
        if key in seen:
            b.Remove(t); dup += 1
        seen.add(key)
    p = new_step("cleanvias"); b.Save(p); commit(p, f"cleanvias {net} ({k} via mo coi, {dup} doan trung)")

elif CMD == "pour":        # pour NET [pitch_mm=3] : do dong NET mat tren (F.Cu) + via khau luoi o cho trong tren CA 2 lop
    import pcbnew, math
    from pcbnew import FromMM, VECTOR2I
    b = pcbnew.LoadBoard(cur()); net = A[0]; pitch = float(A[1]) if len(A) > 1 else 3.0
    ni = b.FindNet(net); e = b.GetBoardEdgesBoundingBox()
    if not any(z.GetNetname() == net and z.GetFirstLayer() == pcbnew.F_Cu for z in b.Zones()):
        z = pcbnew.ZONE(b); z.SetLayer(pcbnew.F_Cu); z.SetNet(ni); z.SetMinThickness(FromMM(0.2))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)   # SMD noi dac, THT co thermal (de han tay)
        ol = z.Outline(); ol.NewOutline(); m = FromMM(0.3)
        for x, y in ((e.GetLeft() + m, e.GetTop() + m), (e.GetRight() - m, e.GetTop() + m), (e.GetRight() - m, e.GetBottom() - m), (e.GetLeft() + m, e.GetBottom() - m)):
            ol.Append(x, y)
        b.Add(z)
    obst = []   # (loai, hinh) cua dong khac net, tren bat ky lop nao
    for t in b.GetTracks():
        if t.GetNetname() != net:
            obst.append((t.GetStart().x / 1e6, t.GetStart().y / 1e6, t.GetEnd().x / 1e6, t.GetEnd().y / 1e6, t.GetWidth() / 2e6 if t.GetClass() != "PCB_VIA" else t.GetWidth(pcbnew.F_Cu) / 2e6))
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.GetNetname() != net or p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:   # via khau cung khong duoc sat pad SMD cung net (V1)
                r = p.GetBoundingBox(); obst.append((r.GetLeft() / 1e6, r.GetTop() / 1e6, r.GetRight() / 1e6, r.GetBottom() / 1e6, -1))
        c = f.GetBoundingBox(False, False)   # khong khau via duoi than linh kien
        obst.append((c.GetLeft() / 1e6, c.GetTop() / 1e6, c.GetRight() / 1e6, c.GetBottom() / 1e6, -2))
    own = [(t.GetPosition().x / 1e6, t.GetPosition().y / 1e6) for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    def dseg(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay; L = dx * dx + dy * dy
        u = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
        return math.hypot(px - ax - u * dx, py - ay - u * dy)
    VR, CL = 0.3, 0.35   # ban kinh via 0.6 + khe ho
    add = 0; x0, y0, x1, y1 = e.GetLeft() / 1e6 + 1.2, e.GetTop() / 1e6 + 1.2, e.GetRight() / 1e6 - 1.2, e.GetBottom() / 1e6 - 1.2
    y = y0
    while y <= y1:
        x = x0
        while x <= x1:
            ok = all(math.hypot(x - a, y - c) > 1.5 for a, c in own)
            for o in obst if ok else []:
                if o[4] >= 0:
                    if dseg(x, y, *o[:4]) < VR + CL + o[4]: ok = False; break
                else:
                    pad = VR + CL if o[4] == -1 else 0.1
                    if o[0] - pad < x < o[2] + pad and o[1] - pad < y < o[3] + pad: ok = False; break
            if ok:
                v = pcbnew.PCB_VIA(b); v.SetPosition(VECTOR2I(FromMM(x), FromMM(y))); v.SetWidth(FromMM(0.6)); v.SetDrill(FromMM(0.3)); v.SetNet(ni)
                b.Add(v); own.append((x, y)); add += 1
            x += pitch
        y += pitch
    p = new_step("pour"); b.Save(p); commit(p, f"pour {net} F.Cu + {add} via khau (luoi {pitch} mm)")

elif CMD == "placesmall":  # placesmall REF [R_mm=5] [apply] : do vi tri + huong cho linh kien nho (khong co dinh theo mau), chon diem tot nhat (L67)
    import pcbnew, math
    from pcbnew import FromMM, VECTOR2I
    b = pcbnew.LoadBoard(cur()); f = b.FindFootprintByReference(A[0])
    R = float(A[1]) if len(A) > 1 and A[1] != "apply" else 5.0; do_apply = "apply" in A
    zn = {z.GetNetname() for z in b.Zones()}                       # net do dong (GND): khong can noi day
    own = {p.GetNetname() for p in f.Pads() if p.GetNetname() and p.GetNetname() not in zn}
    x0, y0, r0 = f.GetPosition().x, f.GetPosition().y, f.GetOrientationDegrees()
    others = [g for g in b.GetFootprints() if g.GetReference() != A[0]]      # SWIG: "is not" luon dung (proxy moi), so theo ten
    def crt(g):
        if hasattr(g, "BuildCourtyardCaches"): g.BuildCourtyardCaches()
        cy = g.GetCourtyard(pcbnew.F_CrtYd); return cy.BBox() if cy.OutlineCount() else g.GetBoundingBox(False)
    ocrt = [crt(g) for g in others]
    eb = b.GetBoardEdgesBoundingBox(); eb.Inflate(-FromMM(0.5))
    segs = [(t.GetStart(), t.GetEnd(), t.GetWidth(), t.GetNetname()) for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetLayer() == pcbnew.F_Cu and t.GetNetname() not in own]
    vias = [(v.GetPosition(), v.GetWidth(pcbnew.F_Cu), v.GetNetname()) for v in b.GetTracks() if v.GetClass() == "PCB_VIA" and v.GetNetname() not in own]
    tgt = {n: [p for g in others for p in g.Pads() if p.GetNetname() == n] for n in own}
    def sd(a, c, p):
        dx, dy = c.x - a.x, c.y - a.y; L = dx * dx + dy * dy; u = 0 if L == 0 else max(0, min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L))
        return math.hypot(p.x - a.x - u * dx, p.y - a.y - u * dy)
    def cross(a, c, s, e):
        o = lambda p, q, r: (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x)
        return o(a, c, s) * o(a, c, e) < 0 and o(s, e, a) * o(s, e, c) < 0
    cands = []; cur_sc = None
    st = FromMM(0.25); n = int(FromMM(R) / st)
    for ix in range(-n, n + 1):
        for iy in range(-n, n + 1):
            x, y = x0 + ix * st, y0 + iy * st
            for rot in (0, 90, 180, 270):
                f.SetPosition(VECTOR2I(int(x), int(y))); f.SetOrientationDegrees(rot); c = crt(f)
                if not eb.Contains(c) or any(c.Intersects(o) for o in ocrt): continue
                bad = False
                for p in f.Pads():          # dong cua net khac khong duoc cham pad (clearance 0.25)
                    q = p.GetPosition(); hw = max(p.GetBoundingBox().GetWidth(), p.GetBoundingBox().GetHeight()) / 2
                    if any(sd(s, e, q) < w / 2 + hw + FromMM(0.25) for s, e, w, nn in segs if nn != p.GetNetname()) or any((q - vp).EuclideanNorm() < vw / 2 + hw + FromMM(0.25) for vp, vw, nn in vias):
                        bad = True; break
                if bad: continue
                sc = 0.0
                for p in f.Pads():
                    nn = p.GetNetname()
                    if nn not in own or not tgt[nn]: continue
                    q = p.GetPosition(); best = min(tgt[nn], key=lambda t_: (t_.GetPosition() - q).EuclideanNorm()); tq = best.GetPosition()
                    sc += (tq - q).EuclideanNorm() + FromMM(3.0) * sum(1 for s, e, w, n2 in segs if cross(q, tq, s, e))
                cands.append((sc, x, y, rot))
                if ix == 0 and iy == 0 and rot == int(r0) % 360: cur_sc = sc
    f.SetPosition(VECTOR2I(int(x0), int(y0))); f.SetOrientationDegrees(r0)
    cands.sort()
    print(f"{A[0]}: hien tai ({x0 / 1e6:.2f},{y0 / 1e6:.2f}) {r0:.0f} do diem {cur_sc / 1e6 if cur_sc is not None else float('nan'):.2f}; {len(cands)} vi tri hop le; tot nhat:")
    for sc, x, y, rot in cands[:5]:
        print(f"   ({x / 1e6:.2f},{y / 1e6:.2f}) {rot} do  diem {sc / 1e6:.2f}")
    if do_apply and cands:
        sc, x, y, rot = cands[0]
        f.SetPosition(VECTOR2I(int(x), int(y))); f.SetOrientationDegrees(rot)
        for t in list(b.GetTracks()):        # go day cua cac net tin hieu cua no de route lai
            if t.GetNetname() in own: b.Remove(t)
        p = new_step(f"placesmall_{A[0]}"); b.Save(p); commit(p, f"placesmall {A[0]} -> ({x / 1e6:.2f},{y / 1e6:.2f}) {rot}; go day {sorted(own)}")
        print("da dat, can route lai:", ",".join(sorted(own)))

elif CMD == "gndsolid":    # gndsolid NET [CLR=0.25] : zone NET noi pad SOLID, clearance CLR; bo moi track NET (pad noi thang vao mat dong), giu via khau (L59)
    import pcbnew
    b = pcbnew.LoadBoard(cur()); net = A[0]; clr = float(A[1]) if len(A) > 1 else 0.25
    nz = 0
    for z in b.Zones():
        if z.GetNetname() == net:
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL); z.SetLocalClearance(pcbnew.FromMM(clr)); nz += 1
    for f in b.GetFootprints():          # pad tu dat kieu noi rieng (padconn) -> ve theo zone
        for p in f.Pads():
            if p.GetNetname() == net:
                p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_INHERITED)
    dead = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() == net]
    for t in dead:
        b.Remove(t)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    p = new_step("gndsolid"); b.Save(p); commit(p, f"gndsolid {net}: {nz} zone noi pad solid, clearance {clr}; bo {len(dead)} doan day {net}")
    print(f"{nz} zone solid, bo {len(dead)} doan {net}")

elif CMD == "padconn":     # padconn REF.PAD full|thermal : kieu noi pad voi zone (vd chan header bi starved thermal)
    import pcbnew
    b = pcbnew.LoadBoard(cur()); ref, num = A[0].split(".")
    pad = next(p for p in b.FindFootprintByReference(ref).Pads() if p.GetNumber() == num)
    pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL if A[1] == "full" else pcbnew.ZONE_CONNECTION_THERMAL)
    p = new_step(f"padconn_{ref}{num}"); b.Save(p); commit(p, f"padconn {A[0]} {A[1]}")

elif CMD == "track":       # track NET F.Cu|B.Cu WIDTH x1,y1 x2,y2 ... : ve doan day thu cong (quyet dinh hinh hoc cua tac tu)
    import pcbnew
    from pcbnew import FromMM, VECTOR2I
    b = pcbnew.LoadBoard(cur()); ni = b.FindNet(A[0]); lay = pcbnew.F_Cu if A[1] == "F.Cu" else pcbnew.B_Cu; w = float(A[2])
    if ni is None or not A[0]:      # Git Bash doi "/03_x/NET" thanh duong dan Windows -> net khong ton tai -> dong khong net (L80)
        sys.exit(f"TU CHOI: khong co net '{A[0]}' (Git Bash: dat MSYS_NO_PATHCONV=1 cho ten net bat dau bang /)")
    pts = [tuple(float(v) for v in q.split(",")) for q in A[3:]]
    import math   # chot chan: KiCad tu doi net cua via bi day de len -> DRC khong bao, phai chan o day
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):    # L61: chi ve doan 0/45/90 do (tru doan < 0.15 mm de can tam pad)
        a = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 45
        if min(a, 45 - a) >= 1.0 and math.hypot(x2 - x1, y2 - y1) >= 0.15:
            sys.exit(f"TU CHOI: doan ({x1},{y1})-({x2},{y2}) lech goc 45 do {min(a, 45 - a):.1f} do; them diem gap khuc")
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        for v in b.GetTracks():
            if v.GetClass() != "PCB_VIA" or v.GetNetname() == A[0]: continue
            px, py = v.GetPosition().x / 1e6, v.GetPosition().y / 1e6; dx, dy = x2 - x1, y2 - y1; L = dx * dx + dy * dy
            u = 0 if L == 0 else max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / L))
            if math.hypot(px - x1 - u * dx, py - y1 - u * dy) < w / 2 + v.GetWidth(pcbnew.F_Cu) / 2e6 + 0.2:
                sys.exit(f"TU CHOI: doan ({x1},{y1})-({x2},{y2}) de/sat via {v.GetNetname()} tai ({px:.2f},{py:.2f}); xoa/doi via truoc")
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(b); t.SetStart(VECTOR2I(FromMM(x1), FromMM(y1))); t.SetEnd(VECTOR2I(FromMM(x2), FromMM(y2)))
        t.SetWidth(FromMM(w)); t.SetLayer(lay); t.SetNet(ni); b.Add(t)
    p = new_step("track"); b.Save(p); commit(p, f"track {A[0]} {A[1]} w{w} {' '.join(A[3:])}")

elif CMD == "delat":       # delat X Y [R=0.3] [via|F.Cu|B.Cu|all] : xoa via / doan day co dau mut trong ban kinh R quanh diem
    import pcbnew
    b = pcbnew.LoadBoard(cur()); x, y = float(A[0]) * 1e6, float(A[1]) * 1e6
    r = (float(A[2]) if len(A) > 2 else 0.3) * 1e6; kind = A[3] if len(A) > 3 else "all"
    near = lambda q: (q.x - x) ** 2 + (q.y - y) ** 2 <= r * r
    gone = []
    for t in list(b.GetTracks()):
        isv = t.GetClass() == "PCB_VIA"
        if kind == "via" and not isv: continue
        if kind in ("F.Cu", "B.Cu") and (isv or b.GetLayerName(t.GetLayer()) != kind): continue
        if (isv and near(t.GetPosition())) or (not isv and (near(t.GetStart()) or near(t.GetEnd()))):
            gone.append(f"{t.GetClass()}:{t.GetNetname()}"); b.Remove(t)
    p = new_step("delat"); b.Save(p); commit(p, f"delat {' '.join(A)} -> {gone}")

elif CMD == "setnet":      # setnet REF.PAD NET [REF.PAD NET ...] : DOI NETLIST tren board (vd hoan vi chan tuong duong) -> PHAI sua schematic theo
    import pcbnew
    b = pcbnew.LoadBoard(cur()); done = []
    for k in range(0, len(A), 2):
        ref, num = A[k].split(".")
        for pd in b.FindFootprintByReference(ref).Pads():
            if pd.GetNumber() == num:
                done.append(f"{A[k]}:{pd.GetNetname()}->{A[k + 1]}"); pd.SetNet(b.FindNet(A[k + 1]))
    p = new_step("setnet"); b.Save(p); commit(p, "setnet (CAN SUA SCHEMATIC) " + ", ".join(done))
    with open(os.path.join(W, "SCHEMATIC_CHANGES.md"), "a", encoding="utf-8") as f:
        f.write(f"- {time.strftime('%Y-%m-%d %H:%M')}: " + ", ".join(done) + "\n")

elif CMD == "reftext":     # reftext REF X Y [SIZE_MM] : dat chu ky hieu (silkscreen) cua linh kien
    import pcbnew
    from pcbnew import FromMM, VECTOR2I
    b = pcbnew.LoadBoard(cur()); t = b.FindFootprintByReference(A[0]).Reference()
    t.SetPosition(VECTOR2I(FromMM(float(A[1])), FromMM(float(A[2]))))
    if len(A) > 3:
        _mh = json.load(open(os.path.join(W, "project.kicad_pro"), encoding="utf-8"))["board"]["design_settings"]["rules"].get("min_text_height", 0.8)
        if float(A[3]) < _mh and not (len(A) > 5 and A[5] == "fab"):
            sys.exit(f"TU CHOI: co chu {A[3]} < min_text_height {_mh} cua luat du an")
        sz = FromMM(float(A[3])); t.SetTextSize(VECTOR2I(sz, sz)); t.SetTextThickness(int(sz * 0.15))
    t.SetTextAngleDegrees(float(A[4]) if len(A) > 4 else 0)
    t.SetLayer(pcbnew.F_Fab if (len(A) > 5 and A[5] == "fab") else pcbnew.F_SilkS)   # fab: khong con cho, chi o ban ve lap rap
    p = new_step(f"reftext_{A[0]}"); b.Save(p); commit(p, f"reftext {' '.join(A)}")

elif CMD == "silkrefs":    # silkrefs [SIZE=0.8] : dua ky hieu len silkscreen, tu dat quanh courtyard, tranh pad/via/chu khac/mep board (Q17, L64)
    import pcbnew
    from pcbnew import FromMM, VECTOR2I
    b = pcbnew.LoadBoard(cur())
    _mh = json.load(open(os.path.join(W, "project.kicad_pro"), encoding="utf-8"))["board"]["design_settings"]["rules"].get("min_text_height", 0.8)
    sz = FromMM(max(float(A[0]) if A else 0.8, _mh))       # khong bao gio nho hon min_text_height cua luat du an (DRC text_height)
    eb = b.GetBoardEdgesBoundingBox(); eb.Inflate(-FromMM(0.3))
    obst = [p.GetBoundingBox() for f in b.GetFootprints() for p in f.Pads()] + [v.GetBoundingBox() for v in b.GetTracks() if v.GetClass() == "PCB_VIA" and not v.IsTented(pcbnew.F_Mask)]   # via tented (phu mask): chu in de len duoc
    for bb_ in obst: bb_.Inflate(FromMM(0.1))
    placed, fail = [], []
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
    crts_of = {f.GetReference(): _body(f) for f in b.GetFootprints()}; crts = list(crts_of.values())
    fps = sorted(b.GetFootprints(), key=lambda f: f.GetBoundingBox(False).GetArea())     # linh kien nho truoc (it cho dat nhat)
    for f in fps:
        t = f.Reference(); bot = f.IsFlipped()
        t.SetLayer(pcbnew.B_SilkS if bot else pcbnew.F_SilkS); t.SetVisible(True)
        cy = f.GetCourtyard(pcbnew.B_CrtYd if bot else pcbnew.F_CrtYd)
        c = cy.BBox() if cy.OutlineCount() else f.GetBoundingBox(False)
        cx_, cy_ = c.GetCenter().x, c.GetCenter().y
        # do luoi 0.2 mm quanh courtyard (toi 2.6 mm), co chu 0.8/0.6/0.5, ngang/doc; chon cho GAN linh kien cua minh nhat
        # ma khong de pad/via/chu khac, nam trong board, va khong gan linh kien khac hon (Q18)
        best = None
        for s_ in (sz,):     # khong thu nho chu duoi luat; khong co cho -> F.Fab
            if best: break
            for ang in (0, 90):
                t.SetTextSize(VECTOR2I(s_, s_)); t.SetTextThickness(int(s_ * 0.15)); t.SetTextAngleDegrees(ang)
                R = FromMM(2.6); st = FromMM(0.2)
                for ix in range(-int(R / st), int(R / st) + 1):
                    for iy in range(-int(R / st), int(R / st) + 1):
                        x = (c.GetLeft() + c.GetRight()) // 2 + ix * st + (ix > 0) * (c.GetWidth() // 2) - (ix < 0) * (c.GetWidth() // 2)
                        y = (c.GetTop() + c.GetBottom()) // 2 + iy * st + (iy > 0) * (c.GetHeight() // 2) - (iy < 0) * (c.GetHeight() // 2)
                        t.SetPosition(VECTOR2I(int(x), int(y))); tb = t.GetBoundingBox()
                        if not eb.Contains(tb) or tb.Intersects(c): continue
                        if any(tb.Intersects(o) for o in obst) or any(tb.Intersects(o) for o in placed): continue
                        tc = tb.GetCenter()
                        dist = lambda q: ((max(q.GetLeft() - tc.x, 0, tc.x - q.GetRight())) ** 2 + (max(q.GetTop() - tc.y, 0, tc.y - q.GetBottom())) ** 2) ** 0.5
                        own = dist(crts_of[f.GetReference()]); oth = min((dist(o) for o in crts if o is not crts_of[f.GetReference()]), default=1e12)
                        if oth < own + FromMM(0.3): continue
                        sc = own - 0.3 * min(oth - own, FromMM(1.0)) + (s_ < sz) * FromMM(0.5)
                        if best is None or sc < best[0]:
                            best = (sc, x, y, s_, ang)
        if best:
            _, x, y, s_, ang = best
            t.SetTextSize(VECTOR2I(s_, s_)); t.SetTextThickness(int(s_ * 0.15)); t.SetTextAngleDegrees(ang); t.SetPosition(VECTOR2I(int(x), int(y)))
        else:     # khong con cho tren silkscreen o co chu hop le: ky hieu chi o ban ve lap rap
            fail.append(f.GetReference()); t.SetTextSize(VECTOR2I(sz, sz)); t.SetTextThickness(int(sz * 0.15)); t.SetTextAngleDegrees(0)
            t.SetPosition(VECTOR2I(int(cx_), int(cy_))); t.SetLayer(pcbnew.B_Fab if bot else pcbnew.F_Fab)
        placed.append(t.GetBoundingBox())
    p = new_step("silkrefs"); b.Save(p); commit(p, f"silkrefs: {len(fps)} ky hieu len silkscreen; khong cho dat: {fail}")
    print(f"{len(fps)} ky hieu len silkscreen" + (f"; KHONG tim duoc cho trong: {fail}" if fail else ""))

elif CMD == "dogbone":     # dogbone NET [GAP=0.25] : via cua NET lan/sat pad SMD -> doi ra ngoai pad (canh via cach pad GAP), noi bang doan ngan
    import pcbnew, math
    from pcbnew import FromMM, VECTOR2I
    b = pcbnew.LoadBoard(cur()); net = A[0]; gap = float(A[1]) if len(A) > 1 else 0.25; CL = 0.2
    pads = [p for f in b.GetFootprints() for p in f.Pads()]
    pname = {id(p): f"{f.GetReference()}.{p.GetNumber()}" for f in b.GetFootprints() for p in f.Pads()}
    pname = {id(p): n for p, n in zip(pads, pname.values())}
    def edge_d(p, x, y):
        bb = p.GetBoundingBox(); dx = max(bb.GetLeft() / 1e6 - x, 0, x - bb.GetRight() / 1e6); dy = max(bb.GetTop() / 1e6 - y, 0, y - bb.GetBottom() / 1e6)
        return math.hypot(dx, dy)
    def seg_d(t, x, y):
        ax, ay, bx, by = t.GetStart().x / 1e6, t.GetStart().y / 1e6, t.GetEnd().x / 1e6, t.GetEnd().y / 1e6
        dx, dy = bx - ax, by - ay; L = dx * dx + dy * dy; u = 0 if L == 0 else max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / L))
        return math.hypot(x - ax - u * dx, y - ay - u * dy) - t.GetWidth() / 2e6
    moved = []
    _eb = b.GetBoardEdgesBoundingBox(); EB = (_eb.GetLeft() / 1e6, _eb.GetTop() / 1e6, _eb.GetRight() / 1e6, _eb.GetBottom() / 1e6)
    pname = {id(p): f"{p.GetParentFootprint().GetReference()}.{p.GetNumber()}" for p in pads}
    targets = [(t.GetPosition().x / 1e6, t.GetPosition().y / 1e6) for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == net]
    for vx, vy in targets:    # tim lai via moi vong (doi tuong SWIG cu mat hieu luc sau khi Remove)
        v = next(t for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and abs(t.GetPosition().x / 1e6 - vx) < 1e-4 and abs(t.GetPosition().y / 1e6 - vy) < 1e-4)
        r = v.GetWidth(pcbnew.F_Cu) / 2e6
        hit = [p for p in pads if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and edge_d(p, vx, vy) - r < gap]
        if not hit: continue
        own = next((p for p in hit if p.GetNetname() == net), hit[0])
        cx, cy = own.GetPosition().x / 1e6, own.GetPosition().y / 1e6
        base = math.atan2(vy - cy, vx - cx) if (vx, vy) != (cx, cy) else 0.0
        best = None
        for k in range(16):                                  # thu 16 huong, uu tien huong gan huong cu
            a = base + (k + 1) // 2 * (math.pi / 8) * (1 if k % 2 else -1)
            for dist in [x / 20 for x in range(4, 40)]:
                x, y = cx + dist * math.cos(a), cy + dist * math.sin(a)
                if edge_d(own, x, y) - r < gap: continue
                if not (EB[0] + r + 0.5 <= x <= EB[2] - r - 0.5 and EB[1] + r + 0.5 <= y <= EB[3] - r - 0.5): continue   # cach mep board 0.5 (copper_to_edge)
                ok = all(edge_d(p, x, y) - r >= (gap if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD else CL) for p in pads if p is not own) and \
                     all(seg_d(t, x, y) - r >= CL for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() != net) and \
                     all(math.hypot(x - t.GetPosition().x / 1e6, y - t.GetPosition().y / 1e6) >= 2 * r + 0.25 for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and t is not v)
                if ok:   # doan noi pad -> via cung phai sach (khong cat / sat dong khac net)
                    for i in range(1, 11):
                        sx, sy = cx + (x - cx) * i / 10, cy + (y - cy) * i / 10
                        if any(seg_d(t, sx, sy) - 0.15 < CL for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() != net) or                            any(edge_d(p, sx, sy) - 0.15 < CL for p in pads if p.GetNetname() != net):
                            ok = False; break
                if ok:
                    best = (dist, k, x, y); break
            if best: break
        if not best:
            moved.append(f"KHONG DOI DUOC via {net} ({vx:.2f},{vy:.2f})"); continue
        _, _, x, y = best
        for t in list(b.GetTracks()):          # bo doan cut cu noi toi vi tri via cu
            if t.GetClass() == "PCB_TRACK" and t.GetNetname() == net and (abs(t.GetStart().x / 1e6 - vx) < 1e-3 and abs(t.GetStart().y / 1e6 - vy) < 1e-3 or abs(t.GetEnd().x / 1e6 - vx) < 1e-3 and abs(t.GetEnd().y / 1e6 - vy) < 1e-3):
                b.Remove(t)
        v.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
        t = pcbnew.PCB_TRACK(b); t.SetStart(VECTOR2I(FromMM(cx), FromMM(cy))); t.SetEnd(VECTOR2I(FromMM(x), FromMM(y)))
        t.SetWidth(FromMM(0.3)); t.SetLayer(pcbnew.F_Cu); t.SetNet(v.GetNet()); b.Add(t)
        moved.append(f"{pname.get(id(own), '?')}: ({vx:.2f},{vy:.2f})->({x:.2f},{y:.2f})")
        break   # SWIG KiCad 10: doi tuong board hong sau Add/Remove trong vong lap -> moi lan goi chi xu ly 1 via, goi lai den khi het
    p = new_step("dogbone"); b.Save(p); commit(p, f"dogbone {net}: " + "; ".join(moved)); print("\n".join(moved))

elif CMD in ("tidy", "oct45", "chamfer"):   # tidy [JOG=0.35]: gop doan thang hang, bo khuc gap nho (L58) | oct45: doi moi doan lech goc 45 thanh 2 doan 0/45/90 (L61)
    import pcbnew, math
    from pcbnew import FromMM, VECTOR2I
    jog = float(A[0]) if (A and CMD == "tidy") else 0.35; CL = 0.2
    b = pcbnew.LoadBoard(cur())
    objs = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]
    S = [dict(i=i, net=t.GetNetname(), lay=t.GetLayer(), w=t.GetWidth() / 1e6, a=(t.GetStart().x / 1e6, t.GetStart().y / 1e6),
              b=(t.GetEnd().x / 1e6, t.GetEnd().y / 1e6), dead=False) for i, t in enumerate(objs)]
    vias = [(v.GetPosition().x / 1e6, v.GetPosition().y / 1e6, v.GetWidth(pcbnew.F_Cu) / 2e6, v.GetNetname()) for v in b.GetTracks() if v.GetClass() == "PCB_VIA"]
    pads = [(p, p.GetNetname()) for f in b.GetFootprints() for p in f.Pads()]
    def pd(P, Q, X):
        dx, dy = Q[0] - P[0], Q[1] - P[1]; LL = dx * dx + dy * dy; u = 0 if LL == 0 else max(0, min(1, ((X[0] - P[0]) * dx + (X[1] - P[1]) * dy) / LL))
        return math.hypot(X[0] - P[0] - u * dx, X[1] - P[1] - u * dy)
    def cross(P, Q, R, T):
        o = lambda a, b_, c: (b_[0] - a[0]) * (c[1] - a[1]) - (b_[1] - a[1]) * (c[0] - a[0])
        return o(P, Q, R) * o(P, Q, T) < 0 and o(R, T, P) * o(R, T, Q) < 0
    def ss(P, Q, R, T):
        return 0.0 if cross(P, Q, R, T) else min(pd(P, Q, R), pd(P, Q, T), pd(R, T, P), pd(R, T, Q))
    def key(p): return (round(p[0], 3), round(p[1], 3))
    def anchored(net, lay, X):
        if any(abs(X[0] - vx) < 1e-3 and abs(X[1] - vy) < 1e-3 for vx, vy, _, vn in vias if vn == net): return True
        return any(n == net and p.IsOnLayer(lay) and p.HitTest(VECTOR2I(FromMM(X[0]), FromMM(X[1]))) for p, n in pads)
    def clear(net, lay, w, P, Q, skip):
        for s in S:
            if s["dead"] or s["i"] in skip or s["lay"] != lay or s["net"] == net: continue
            if ss(P, Q, s["a"], s["b"]) - w / 2 - s["w"] / 2 < CL: return False
        for vx, vy, r, vn in vias:
            if vn != net and pd(P, Q, (vx, vy)) - w / 2 - r < CL: return False
        for p, n in pads:
            if n == net or not p.IsOnLayer(lay): continue
            q = p.GetBoundingBox(); x0, y0, x1, y1 = q.GetLeft() / 1e6, q.GetTop() / 1e6, q.GetRight() / 1e6, q.GetBottom() / 1e6
            edges = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
            inside = x0 <= P[0] <= x1 and y0 <= P[1] <= y1
            if inside or min(ss(P, Q, e0, e1) for e0, e1 in edges) - w / 2 < CL: return False
        return True
    def is45(P, Q):
        a = math.degrees(math.atan2(Q[1] - P[1], Q[0] - P[0])) % 45
        return min(a, 45 - a) < 1.0
    def inpad(net, lay, P, Q):    # doan nam tron trong 1 pad cung net: khong nhin thay, khong tinh goc
        return any(n == net and p.IsOnLayer(lay) and p.HitTest(VECTOR2I(FromMM(P[0]), FromMM(P[1]))) and p.HitTest(VECTOR2I(FromMM(Q[0]), FromMM(Q[1]))) for p, n in pads)
    if CMD == "chamfer":     # vat moi goc gap > 45 do (vd 90 do) giua 2 doan cung net thanh 2 goc 45 do (owner: "sao lai be vuong goc")
        cmax = float(A[0]) if A else 0.6
        done, fail = 0, []
        # buoc 1: doan vat ngan (< 0.3 mm) giua 2 doan dai -> bo, keo 2 doan dai toi giao diem (thanh goc that) de buoc 2 vat dung 45 do
        def _ix(P1, P2, P3, P4):
            d = (P2[0] - P1[0]) * (P4[1] - P3[1]) - (P2[1] - P1[1]) * (P4[0] - P3[0])
            if abs(d) < 1e-9: return None
            u = ((P3[0] - P1[0]) * (P4[1] - P3[1]) - (P3[1] - P1[1]) * (P4[0] - P3[0])) / d
            return (P1[0] + u * (P2[0] - P1[0]), P1[1] + u * (P2[1] - P1[1]))
        again = True
        while again:
            again = False
            adj = {}
            for s in S:
                if not s["dead"]:
                    for end in ("a", "b"): adj.setdefault((s["net"], s["lay"], key(s[end])), []).append((s, end))
            for sm in S:
                if sm["dead"] or math.hypot(sm["b"][0] - sm["a"][0], sm["b"][1] - sm["a"][1]) >= 0.3: continue
                la = [x for x in adj.get((sm["net"], sm["lay"], key(sm["a"])), []) if x[0] is not sm]
                lb = [x for x in adj.get((sm["net"], sm["lay"], key(sm["b"])), []) if x[0] is not sm]
                if len(la) != 1 or len(lb) != 1: continue
                (s1, e1), (s2, e2) = la[0], lb[0]
                F1 = s1["b" if e1 == "a" else "a"]; F2 = s2["b" if e2 == "a" else "a"]
                if math.hypot(F1[0] - s1[e1][0], F1[1] - s1[e1][1]) < 0.3 or math.hypot(F2[0] - s2[e2][0], F2[1] - s2[e2][1]) < 0.3: continue
                X = _ix(F1, s1[e1], s2[e2], F2)
                if X is None or math.hypot(X[0] - sm["a"][0], X[1] - sm["a"][1]) > 0.4: continue
                if inpad(sm["net"], sm["lay"], sm["a"], sm["b"]) or inpad(sm["net"], sm["lay"], X, X): continue
                s1[e1] = X; s2[e2] = X; sm["dead"] = True; again = True; break
        changed = True
        while changed:
            changed = False
            adj = {}
            for s in S:
                if not s["dead"]:
                    for end in ("a", "b"): adj.setdefault((s["net"], s["lay"], key(s[end])), []).append((s, end))
            for (net, lay, k), lst in adj.items():
                if len(lst) != 2: continue
                (s1, e1), (s2, e2) = lst
                N = s1[e1]; P_ = s1["b" if e1 == "a" else "a"]; Q_ = s2["b" if e2 == "a" else "a"]
                v1 = (N[0] - P_[0], N[1] - P_[1]); v2 = (Q_[0] - N[0], Q_[1] - N[1]); n1, n2 = math.hypot(*v1), math.hypot(*v2)
                if n1 < 1e-4 or n2 < 1e-4: continue
                turn = math.degrees(math.acos(max(-1, min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))))
                if turn < 46 or turn > 95: continue          # chi xu ly goc 90 do (135 do de bao cao)
                if inpad(net, lay, N, N): continue            # gap trong pad: khong nhin thay
                w = min(s1["w"], s2["w"]); ok_ = None
                for c in (cmax, 0.4, 0.25, 0.15):           # vat lon nhat con du khe ho
                    c = min(c, n1 * 0.5, n2 * 0.5)
                    if c < 0.12: break
                    Ap = (N[0] - v1[0] / n1 * c, N[1] - v1[1] / n1 * c); Bp = (N[0] + v2[0] / n2 * c, N[1] + v2[1] / n2 * c)
                    if clear(net, lay, w, Ap, Bp, {s1["i"], s2["i"]}):
                        ok_ = (Ap, Bp); break
                if ok_ is None:
                    if f"{net} ({N[0]:.2f},{N[1]:.2f})" not in fail: fail.append(f"{net} ({N[0]:.2f},{N[1]:.2f})")
                    continue
                Ap, Bp = ok_
                s1[e1] = Ap; s2[e2] = Bp
                S.append(dict(i=-1, net=net, lay=lay, w=w, a=Ap, b=Bp, dead=False, _new=True))
                done += 1; changed = True; break
        for s in S:
            if s["i"] >= 0:
                t = objs[s["i"]]; t.SetStart(VECTOR2I(FromMM(s["a"][0]), FromMM(s["a"][1]))); t.SetEnd(VECTOR2I(FromMM(s["b"][0]), FromMM(s["b"][1])))
            elif s.get("_new") and not s["dead"]:
                t = pcbnew.PCB_TRACK(b); t.SetStart(VECTOR2I(FromMM(s["a"][0]), FromMM(s["a"][1]))); t.SetEnd(VECTOR2I(FromMM(s["b"][0]), FromMM(s["b"][1])))
                t.SetWidth(FromMM(s["w"])); t.SetLayer(s["lay"]); t.SetNet(b.FindNet(s["net"])); b.Add(t)
        for t in [objs[s["i"]] for s in S if s["dead"] and s["i"] >= 0]:
            b.Remove(t)
        p = new_step("chamfer"); b.Save(p); commit(p, f"chamfer: vat {done} goc 90 do; khong vat duoc {len(fail)}")
        print(f"vat {done} goc 90 do" + ("; KHONG vat duoc (thieu khe ho): " + "; ".join(fail) if fail else ""))
        sys.exit(0)
    if CMD == "oct45":
        done, fail = 0, []
        for s in list(S):
            P, Q = s["a"], s["b"]; dx, dy = Q[0] - P[0], Q[1] - P[1]
            if math.hypot(dx, dy) < 1e-4 or is45(P, Q) or inpad(s["net"], s["lay"], P, Q): continue
            m = min(abs(dx), abs(dy)); sx, sy = math.copysign(1, dx), math.copysign(1, dy)
            ok = None
            for K in ((P[0] + sx * m, P[1] + sy * m), (Q[0] - sx * m, Q[1] - sy * m)):     # cheo truoc / thang truoc
                if clear(s["net"], s["lay"], s["w"], P, K, {s["i"]}) and clear(s["net"], s["lay"], s["w"], K, Q, {s["i"]}):
                    ok = K; break
            if ok is None:
                fail.append(f"{s['net']} ({P[0]:.2f},{P[1]:.2f})->({Q[0]:.2f},{Q[1]:.2f})"); continue
            s["b"] = ok
            t = pcbnew.PCB_TRACK(b); t.SetStart(VECTOR2I(FromMM(ok[0]), FromMM(ok[1]))); t.SetEnd(VECTOR2I(FromMM(Q[0]), FromMM(Q[1])))
            t.SetWidth(FromMM(s["w"])); t.SetLayer(s["lay"]); t.SetNet(objs[s["i"]].GetNet()); b.Add(t)
            S.append(dict(i=-1, net=s["net"], lay=s["lay"], w=s["w"], a=ok, b=Q, dead=False)); done += 1
        for s in S:
            if s["i"] >= 0:
                t = objs[s["i"]]; t.SetStart(VECTOR2I(FromMM(s["a"][0]), FromMM(s["a"][1]))); t.SetEnd(VECTOR2I(FromMM(s["b"][0]), FromMM(s["b"][1])))
        p = new_step("oct45"); b.Save(p); commit(p, f"oct45: {done} doan doi ve 0/45/90; khong doi duoc {len(fail)}")
        print(f"doi {done} doan" + ("; KHONG doi duoc: " + "; ".join(fail) if fail else ""))
        sys.exit(0)
    merged = jogs = 0
    changed = True
    while changed:
        changed = False
        adj = {}
        for s in S:
            if not s["dead"]:
                for end in ("a", "b"): adj.setdefault((s["net"], s["lay"], key(s[end])), []).append((s, end))
        for (net, lay, k), lst in adj.items():
            if len(lst) != 2: continue
            (s1, e1), (s2, e2) = lst
            if s1["dead"] or s2["dead"] or abs(s1["w"] - s2["w"]) > 1e-6: continue
            N = s1[e1]
            if anchored(net, lay, N): continue
            P = s1["b" if e1 == "a" else "a"]; Q = s2["b" if e2 == "a" else "a"]
            v1 = (N[0] - P[0], N[1] - P[1]); v2 = (Q[0] - N[0], Q[1] - N[1])
            n1, n2 = math.hypot(*v1), math.hypot(*v2)
            col = n1 > 0 and n2 > 0 and abs(v1[0] * v2[1] - v1[1] * v2[0]) / (n1 * n2) < 0.035 and v1[0] * v2[0] + v1[1] * v2[1] > 0
            if not col and min(n1, n2) >= jog: continue
            if not col and not (is45(P, Q) or inpad(net, lay, P, Q)): continue      # chi nan khi doan moi van dung goc 0/45/90 (L61)
            if not col and not clear(net, lay, s1["w"], P, Q, {s1["i"], s2["i"]}): continue
            s1["a"], s1["b"] = P, Q; s2["dead"] = True
            merged += col; jogs += (not col); changed = True
            break
    dead = [objs[s["i"]] for s in S if s["dead"]]
    for s in S:
        if not s["dead"]:
            t = objs[s["i"]]; t.SetStart(VECTOR2I(FromMM(s["a"][0]), FromMM(s["a"][1]))); t.SetEnd(VECTOR2I(FromMM(s["b"][0]), FromMM(s["b"][1])))
    for t in dead: b.Remove(t)
    p = new_step("tidy"); b.Save(p); commit(p, f"tidy: gop {merged} doan thang hang, bo {jogs} khuc gap nho"); print(f"gop {merged}, bo khuc gap {jogs}")

elif CMD == "via":         # via NET X Y [SIZE DRILL]
    import pcbnew
    from pcbnew import FromMM, VECTOR2I
    b = pcbnew.LoadBoard(cur())
    if b.FindNet(A[0]) is None:     # L80: khong tao via khong net
        sys.exit(f"TU CHOI: khong co net '{A[0]}' (Git Bash: dat MSYS_NO_PATHCONV=1 cho ten net bat dau bang /)")
    v = pcbnew.PCB_VIA(b); v.SetPosition(VECTOR2I(FromMM(float(A[1])), FromMM(float(A[2]))))
    v.SetWidth(FromMM(float(A[3]) if len(A) > 3 else 0.6)); v.SetDrill(FromMM(float(A[4]) if len(A) > 4 else 0.3)); v.SetNet(b.FindNet(A[0])); b.Add(v)
    p = new_step("via"); b.Save(p); commit(p, f"via {' '.join(A)}")

elif CMD == "route":
    p = new_step("route")
    r = subprocess.run([KP, os.path.join(HERE, "pyroute.py"), cur(), p, "--pro", os.path.join(W, "project.kicad_pro"),
                        "--intent", os.path.join(W, "intent.json"), "--order", A[0]], capture_output=True, text=True, env=ENV)
    lines = [l for l in r.stdout.splitlines() if l.startswith(("OK", "FAIL"))]
    print("\n".join(lines) or r.stdout[-800:] + r.stderr[-800:])
    if os.path.exists(p):
        commit(p, f"route {A[0]}", {"result": lines})

elif CMD == "check":
    c = cur(); chk = os.path.join(W, "_chk.kicad_pcb"); shutil.copy(c, chk); shutil.copy(os.path.join(W, "project.kicad_pro"), os.path.join(W, "_chk.kicad_pro"))
    if os.path.exists(os.path.join(W, "project.kicad_dru")): shutil.copy(os.path.join(W, "project.kicad_dru"), os.path.join(W, "_chk.kicad_dru"))
    subprocess.run([CLI, "pcb", "drc", chk, "-o", os.path.join(W, "_drc.json"), "--format", "json", "--severity-all", "--refill-zones"], capture_output=True)
    j = json.load(open(os.path.join(W, "_drc.json"), encoding="utf-8"))
    errs = [v for v in j["violations"] if v["severity"] == "error"]
    print("buoc", os.path.basename(c))
    print("DRC loi", len(errs), "| canh bao", len(j["violations"]) - len(errs), "| net ho", len(j["unconnected_items"]))
    for v in errs[:8]:
        print("  loi", v["type"], "|", " / ".join(i["description"][:60] for i in v["items"]))
    for u in j["unconnected_items"][:8]:
        print("  ho", " / ".join(i["description"][:60] for i in u["items"]))
    v, L = stats(c); print("via tin hieu", sum(v.values()), v, "| dai", L, "mm")
    sr = subprocess.run([KP, os.path.join(HERE, "self_review.py"), c, os.path.join(W, "intent.json")], capture_output=True, text=True).stdout
    blk = [l for l in sr.splitlines() if l.startswith(("R1", "R2", "R3")) or l.startswith("    ")]
    print("tu kiem vi tri tuong doi:"); print("\n".join(blk[:16]))
    # V1: khong via trong / sat pad SMD (thiec chay xuong lo khi reflow). Ref USB-C: via gan nhat cach pad >= 0.21 mm
    import math as _m
    import pcbnew
    bv = pcbnew.LoadBoard(c); smd = [p for f in bv.GetFootprints() for p in f.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    bad, warn = [], []
    for v in bv.GetTracks():
        if v.GetClass() != "PCB_VIA": continue
        q = v.GetPosition(); r = v.GetWidth(pcbnew.F_Cu) / 2
        for p in smd:
            bbx = p.GetBoundingBox(); dx = max(bbx.GetLeft() - q.x, 0, q.x - bbx.GetRight()); dy = max(bbx.GetTop() - q.y, 0, q.y - bbx.GetBottom())
            d = (_m.hypot(dx, dy) - r) / 1e6
            if d < 0.25:   # Eurocircuits: >= 0.25 mm mep pad -> mep via, con dai solder mask (L52)
                (bad if d < 0.2 else warn).append(f"{v.GetNetname()} ({q.x / 1e6:.2f},{q.y / 1e6:.2f}) cach pad {p.GetParentFootprint().GetReference()}.{p.GetNumber()} {d:.2f} mm")
    print("V1 SAI: via trong/sat pad SMD: " + "; ".join(bad) if bad else "V1 dung: khong via nao trong/sat pad SMD (< 0.2 mm)")
    if warn:
        print("V1 can xem (0.2-0.25 mm, kiem dai solder mask): " + "; ".join(warn))
    # R4: track chay DOC hang chan cua linh kien khac (owner 2026-11-27 "trace qua roi"): doan >= 1.5 mm, mep track cach mep
    # >= 4 pad SMD khac net CUNG 1 linh kien <= 0.45 mm. Di vao chan cua chinh no thi chi cat qua 1-2 pad ke ben, khong tinh.
    def _sd(t, x, y):
        ax, ay, bx2, by2 = t.GetStart().x / 1e6, t.GetStart().y / 1e6, t.GetEnd().x / 1e6, t.GetEnd().y / 1e6
        dx, dy = bx2 - ax, by2 - ay; LL = dx * dx + dy * dy; u = 0 if LL == 0 else max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / LL))
        return _m.hypot(x - ax - u * dx, y - ay - u * dy)
    # A45: moi doan nhin thay duoc (khong nam tron trong pad cung net) phai 0/45/90 do (owner 2026-11-27)
    allp = [p for f in bv.GetFootprints() for p in f.Pads()]
    off45 = []
    for t in bv.GetTracks():
        if t.GetClass() != "PCB_TRACK": continue
        s_, e_ = t.GetStart(), t.GetEnd(); dx_, dy_ = (e_.x - s_.x) / 1e6, (e_.y - s_.y) / 1e6
        if _m.hypot(dx_, dy_) < 0.15: continue
        a_ = _m.degrees(_m.atan2(dy_, dx_)) % 45
        if min(a_, 45 - a_) < 1.0: continue
        if any(p.GetNetname() == t.GetNetname() and p.HitTest(s_) and p.HitTest(e_) for p in allp): continue
        off45.append(f"{t.GetNetname()} ({s_.x / 1e6:.2f},{s_.y / 1e6:.2f})->({e_.x / 1e6:.2f},{e_.y / 1e6:.2f}) lech {min(a_, 45 - a_):.0f} do")
    print("A45 SAI: " + "; ".join(off45) if off45 else "A45 dung: moi doan 0/45/90 do")
    # C90: goc GAP giua 2 doan lien nhau cua cung net phai <= 45 do (khong be vuong goc), tru diem gap nam trong pad
    ends_ = {}
    for t in bv.GetTracks():
        if t.GetClass() != "PCB_TRACK": continue
        for q, o in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
            ends_.setdefault((t.GetNetname(), t.GetLayer(), round(q.x / 1e4), round(q.y / 1e4)), []).append((q, o))
    sharp = []
    # ngoai le: vong cau D+/D- sat hang pad connector buoc 0.5 mm (khong du cho doan cheo 45 do + clearance; ref SR01 cung de chu U)
    fine = []
    for fp_ in bv.GetFootprints():
        if fp_.GetReference().startswith("J") and any(min(p.GetSize().x, p.GetSize().y) <= 350000 for p in fp_.Pads()):
            cy_ = fp_.GetCourtyard(pcbnew.F_CrtYd); fine.append(cy_.BBox() if cy_.OutlineCount() else fp_.GetBoundingBox(False))
    infine = lambda q: any(bb.Contains(q) for bb in fine)
    for (nn, ll, _x, _y), lst in ends_.items():
        if len(lst) != 2: continue
        (q1, o1), (q2, o2) = lst
        v1 = (q1.x - o1.x, q1.y - o1.y); v2 = (o2.x - q2.x, o2.y - q2.y); m1, m2 = _m.hypot(*v1), _m.hypot(*v2)
        if m1 == 0 or m2 == 0: continue
        turn = _m.degrees(_m.acos(max(-1, min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / (m1 * m2)))))
        if turn > 46 and not infine(q1) and not any(p.GetNetname() == nn and p.HitTest(q1) for p in allp):
            sharp.append(f"{nn} ({q1.x / 1e6:.2f},{q1.y / 1e6:.2f}) gap {turn:.0f} do")
    # goc "an" sau doan vat ngan (< 0.3 mm): mat nhin van la goc vuong -> do goc giua 2 doan dai hai ben doan ngan
    for t in bv.GetTracks():
        if t.GetClass() != "PCB_TRACK" or t.GetLength() / 1e6 >= 0.3: continue
        a_, c_ = t.GetStart(), t.GetEnd(); nn, ll = t.GetNetname(), t.GetLayer()
        la = [x for x in ends_.get((nn, ll, round(a_.x / 1e4), round(a_.y / 1e4)), []) if not (x[1].x == c_.x and x[1].y == c_.y)]
        lc = [x for x in ends_.get((nn, ll, round(c_.x / 1e4), round(c_.y / 1e4)), []) if not (x[1].x == a_.x and x[1].y == a_.y)]
        if len(la) != 1 or len(lc) != 1: continue
        (qa, oa), (qc, oc) = la[0], lc[0]
        if _m.hypot(qa.x - oa.x, qa.y - oa.y) < 3e5 or _m.hypot(oc.x - qc.x, oc.y - qc.y) < 3e5: continue
        v1 = (qa.x - oa.x, qa.y - oa.y); v2 = (oc.x - qc.x, oc.y - qc.y); m1, m2 = _m.hypot(*v1), _m.hypot(*v2)
        turn = _m.degrees(_m.acos(max(-1, min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / (m1 * m2)))))
        if turn > 46 and not infine(a_) and not any(p.GetNetname() == nn and (p.HitTest(a_) or p.HitTest(c_)) for p in allp):
            sharp.append(f"{nn} ({a_.x / 1e6:.2f},{a_.y / 1e6:.2f}) gap {turn:.0f} do (sau doan vat ngan)")
    print("C90 SAI: " + "; ".join(sharp) if sharp else "C90 dung: khong goc gap nao > 45 do")
    hugs = []
    for t in bv.GetTracks():
        if t.GetClass() != "PCB_TRACK" or t.GetLength() / 1e6 < 1.5:
            continue
        per = {}
        for p in smd:
            if p.GetNetname() == t.GetNetname() or p.GetLayerSet().Contains(t.GetLayer()) is False:
                continue
            bbp = p.GetBoundingBox(); xs = (bbp.GetLeft() / 1e6, bbp.GetRight() / 1e6, (bbp.GetLeft() + bbp.GetRight()) / 2e6)
            ys = (bbp.GetTop() / 1e6, bbp.GetBottom() / 1e6, (bbp.GetTop() + bbp.GetBottom()) / 2e6)
            if min(_sd(t, x, y) for x in xs for y in ys) - t.GetWidth() / 2e6 <= 0.45:
                per.setdefault(p.GetParentFootprint().GetReference(), []).append(p.GetNumber())
        for ref_, nums in per.items():
            if len(nums) >= 4:
                hugs.append(f"{t.GetNetname()} {t.GetLength() / 1e6:.1f} mm doc chan {ref_}.{','.join(nums)}")
    print("R4 SAI: track chay sat hang chan: " + "; ".join(hugs) if hugs else "R4 dung: khong track nao chay doc hang chan linh kien khac")
    # W1: be rong nguon GIAM DAN theo chieu dong: doan o pad nguon chiu toan bo dong, khong duoc hep hon doan phia sau
    import pcbnew
    bb = pcbnew.LoadBoard(c); intent = json.load(open(os.path.join(W, "intent.json"), encoding="utf-8"))
    for net, chains in intent.get("power_chains", {}).items():
        segs = [t for t in bb.GetTracks() if t.GetNetname() == net and t.GetClass() != "PCB_VIA"]
        if not segs:
            continue
        srcs = {ch["from"] for ch in chains if "." in ch["from"]}
        def _pads(s):
            ref, num = s.split("."); return [p for p in bb.FindFootprintByReference(ref).Pads() if p.GetNumber() == num]
        segs = [t for t in segs if t.GetClass() == "PCB_TRACK"]
        for src in srcs:
            pads = _pads(src); others = [p for s in srcs if s != src for p in _pads(s)]
            # chi so voi doan PHIA SAU nguon nay: lan theo dau mut, dung lai o pad nguon khac (cau noi 2 pad VBUS khong tinh)
            key = lambda q: (round(q.x / 1e4), round(q.y / 1e4))
            ends = {}
            for t in segs:
                for q in (t.GetStart(), t.GetEnd()): ends.setdefault(key(q), []).append(t)
            seen, todo = set(), [t for t in segs for p in pads if p.HitTest(t.GetStart()) or p.HitTest(t.GetEnd())]
            while todo:
                t = todo.pop()
                if id(t) in seen: continue
                seen.add(id(t))
                for q in (t.GetStart(), t.GetEnd()):
                    if any(p.HitTest(q) for p in others): continue
                    todo += [u for u in ends.get(key(q), []) if id(u) not in seen]
            down = [t for t in segs if id(t) in seen]
            if not down: continue
            wmax = max(t.GetWidth() for t in down) / 1e6
            touch = [t.GetWidth() / 1e6 for t in segs for p in pads if p.HitTest(t.GetStart()) or p.HitTest(t.GetEnd())]
            if touch and max(touch) + 1e-6 < wmax:
                print(f"W1 SAI: {net} ra khoi nguon {src} rong {max(touch):.2f} mm < doan phia sau {wmax:.2f} mm")
            elif touch:
                print(f"W1 dung: {net} tai nguon {src} rong {max(touch):.2f} mm >= phia sau ({wmax:.2f})")

elif CMD == "undo":
    log = [json.loads(l) for l in open(os.path.join(W, "log.jsonl"), encoding="utf-8")]
    undone = os.path.basename(cur())
    prev = next(x["prev"] for x in log if x["step"] == undone and not str(x["what"]).startswith("undo"))
    open(os.path.join(W, "cur.txt"), "w").write(prev)
    with open(os.path.join(W, "log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(ts=time.strftime("%H:%M:%S"), step=prev, prev=undone, what="undo (xoa file buoc bi huy)")) + "\n")
    drop_step(undone)
    print("ve", prev, "| da xoa", undone)

elif CMD == "prune":       # prune : xoa moi file buoc KHONG nam tren chuoi tu step00 toi buoc hien tai (rac do thu / hoan tac)
    import re as _re
    log = [json.loads(l) for l in open(os.path.join(W, "log.jsonl"), encoding="utf-8")]
    made = {x["step"]: x["prev"] for x in log if not str(x.get("what", "")).startswith("undo")}
    keep, s_ = set(), os.path.basename(cur())
    while s_ and s_ not in keep:
        keep.add(s_); s_ = made.get(s_, "")
    allsteps = {_re.sub(r"\.kicad_(pcb|pro|prl|dru)$", "", f) for f in os.listdir(W) if _re.match(r"step\d+_", f)}
    gone = sorted(allsteps - {k[:-10] for k in keep})
    for g in gone:
        drop_step(g + ".kicad_pcb")
    print(f"giu {len(keep)} buoc tren chuoi hien tai, xoa {len(gone)} buoc rac")

elif CMD == "show":
    env = dict(os.environ, LABELS="1")
    if len(A) > 1:
        env["CROP"] = A[1]; env.setdefault("S", "60")
    r = subprocess.run([KP, os.path.join(HERE, "shot.py"), A[0], cur()], capture_output=True, text=True, env=env)
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-500:])
