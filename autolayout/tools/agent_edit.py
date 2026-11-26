"""agent_edit.py - cong cu cho TAC TU QUAN SAT: moi lenh tao 1 buoc moi (stepNN.kicad_pcb) + ghi nhat ky, hoan tac duoc.
  KP agent_edit.py WORK init BOARD.kicad_pcb PROJECT.kicad_pro INTENT.json
  KP agent_edit.py WORK move REF X Y [ROT]          dat linh kien (mm, do)
  KP agent_edit.py WORK nudge REF DX DY [DROT]      dich tuong doi
  KP agent_edit.py WORK rip NET[,NET...]            go day + via cua net
  KP agent_edit.py WORK route NET[,NET...]          di net (pyroute, theo thu tu, dung intent)
  KP agent_edit.py WORK check                       DRC + via tin hieu + net ho cua buoc hien tai
  KP agent_edit.py WORK undo                        quay ve buoc truoc
  KP agent_edit.py WORK show OUT.png [x0,y0,x1,y1]  anh (co ten net) toan board hoac vung (mm, toa do board)
Buoc hien tai = WORK/cur.txt. Nhat ky = WORK/log.jsonl. Loi route (FAIL) van luu buoc nhung bao ro.
"""
import json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
KP = r"C:\Program Files\KiCad\10.0\bin\python.exe"; CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
W = os.path.abspath(sys.argv[1]); CMD = sys.argv[2]; A = sys.argv[3:]
ENV = dict(os.environ, PYROUTE_RES="0.05", MSYS_NO_PATHCONV="1")


def cur():
    return os.path.join(W, open(os.path.join(W, "cur.txt")).read().strip())


def new_step(tag):
    n = len([f for f in os.listdir(W) if f.startswith("step") and f.endswith(".kicad_pcb")])
    return os.path.join(W, f"step{n:02d}_{tag}.kicad_pcb")


def commit(path, what, extra=None):
    shutil.copy(os.path.join(W, "project.kicad_pro"), path[:-10] + ".kicad_pro")
    prev = open(os.path.join(W, "cur.txt")).read().strip() if os.path.exists(os.path.join(W, "cur.txt")) else ""
    open(os.path.join(W, "cur.txt"), "w").write(os.path.basename(path))
    with open(os.path.join(W, "log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(ts=time.strftime("%H:%M:%S"), step=os.path.basename(path), prev=prev, what=what, **(extra or {})), ensure_ascii=False) + "\n")
    print("buoc moi:", os.path.basename(path))


def stats(path):
    import pcbnew
    t = list(pcbnew.LoadBoard(path).GetTracks()); v = {}
    for x in t:
        if x.GetClass() == "PCB_VIA" and "GND" not in x.GetNetname():
            v[x.GetNetname()] = v.get(x.GetNetname(), 0) + 1
    return v, round(sum(x.GetLength() for x in t if x.GetClass() != "PCB_VIA") / 1e6, 1)


if CMD == "init":
    os.makedirs(W, exist_ok=True)
    shutil.copy(A[1], os.path.join(W, "project.kicad_pro")); shutil.copy(A[2], os.path.join(W, "intent.json"))
    p = new_step("init"); shutil.copy(A[0], p); commit(p, f"init tu {A[0]}")

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
    p = new_step("cleanvias"); b.Save(p); commit(p, f"cleanvias {net} ({k} via)")

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
            if p.GetNetname() != net:
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

elif CMD == "padconn":     # padconn REF.PAD full|thermal : kieu noi pad voi zone (vd chan header bi starved thermal)
    import pcbnew
    b = pcbnew.LoadBoard(cur()); ref, num = A[0].split(".")
    pad = next(p for p in b.FindFootprintByReference(ref).Pads() if p.GetNumber() == num)
    pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL if A[1] == "full" else pcbnew.ZONE_CONNECTION_THERMAL)
    p = new_step(f"padconn_{ref}{num}"); b.Save(p); commit(p, f"padconn {A[0]} {A[1]}")

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

elif CMD == "undo":
    log = [json.loads(l) for l in open(os.path.join(W, "log.jsonl"), encoding="utf-8")]
    prev = next(x["prev"] for x in log if x["step"] == os.path.basename(cur()) and x["what"] != "undo")
    open(os.path.join(W, "cur.txt"), "w").write(prev)
    with open(os.path.join(W, "log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(ts=time.strftime("%H:%M:%S"), step=prev, prev=os.path.basename(cur()), what="undo")) + "\n")
    print("ve", prev)

elif CMD == "show":
    env = dict(os.environ, LABELS="1")
    if len(A) > 1:
        env["CROP"] = A[1]; env.setdefault("S", "60")
    r = subprocess.run([KP, os.path.join(HERE, "shot.py"), A[0], cur()], capture_output=True, text=True, env=env)
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-500:])
