"""autolayout.py - INPUT (board da dat linh kien + .kicad_pro co netclass) -> tu route + kiem tra + bao cao cuoi phien.
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" autolayout.py PLACED.kicad_pcb PROJECT.kicad_pro OUT_DIR

Khong can pre-route tay, khong can khai bao intent: tu SUY RA tu netlist + vai tro linh kien
  - cap USB (pad A6/B6, A7/B7 cua connector), CC (A5/B5), VBUS (A4/A9...), GND
  - chuoi cap nguon:  chan VBUS -> TVS (D 2 chan VBUS-GND) -> bulk (C lon nhat) -> tai (connector) ; moi IC: tu decoupling TRUOC chan
  - tu decoupling (C 2 chan: 1 chan cung net chan IC nguon <=4 mm, 1 chan GND), via GND sat tu, noi them GND chan IC <-> tu ke ben
Thu tu uu tien = quy tac owner: USB -> nguon thong suot -> CC -> tu/GND -> gate -> tin hieu cham (ngan truoc).
Dung cac bai hoc trong learn/lessons.jsonl da o trang thai IMPLEMENTED (nam trong pyroute/chuoi nay).
"""
import json, math, os, re, subprocess, sys, shutil, hashlib, time
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "tools")); from kenv import KP, CLI, FP  # KiCad tim tu dong (tools/kenv.py)
T = os.path.join(HERE, "tools")
sys.path.insert(0, T)
import sch_check


def val(s):
    m = re.match(r"([\d.]+)\s*([pnuµm]?)", s.lower())
    if not m: return 0.0
    return float(m.group(1)) * {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1}[m.group(2)]


def infer(board_path):
    b = pcbnew.LoadBoard(board_path)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    pad = {}
    for ref, f in fps.items():
        for p in f.Pads():
            pad[(ref, p.GetNumber())] = (p.GetNetname(), (p.GetPosition().x / 1e6, p.GetPosition().y / 1e6))
    isg = lambda n: "GND" in n.upper()
    conn = next((r for r, f in fps.items() if any(k[0] == r and k[1] in ("A5", "A6", "A7") for k in pad)), None)
    nets = {}
    for (r, n), (net, pos) in pad.items():
        if net and not net.startswith("unconnected"):
            nets.setdefault(net, []).append((r, n, pos))
    def cn(*names):
        return sorted({pad[(conn, n)][0] for n in names if (conn, n) in pad and pad[(conn, n)][0]})
    usb = cn("A6", "B6", "A7", "B7"); cc = cn("A5", "B5"); vbus = cn("A4_B9", "B4_A9", "A4", "A9", "B4", "B9")
    usb_dp = [n for n in usb if re.search(r"(DP|D\+|_P)$", n.upper())]; usb_dm = [n for n in usb if n not in usb_dp]
    # tu decoupling
    caps = {}
    for ref, f in fps.items():
        ps = list(f.Pads())
        if ref.startswith("C") and len(ps) == 2:
            g = [p for p in ps if isg(p.GetNetname())]; v = [p for p in ps if p.GetNetname() and not isg(p.GetNetname())]
            if len(g) == 1 and len(v) == 1:
                caps[ref] = (v[0].GetNetname(), v[0].GetNumber(), g[0].GetNumber(), val(f.GetValue()),
                             (v[0].GetPosition().x / 1e6, v[0].GetPosition().y / 1e6))
    decap, ics = [], {r for r in fps if r.startswith("U")}
    for cref, (net, vn, gn, cv, cp) in caps.items():
        best = None
        for (r, n), (pnet, pos) in pad.items():
            if r in ics and pnet == net:
                d = math.hypot(pos[0] - cp[0], pos[1] - cp[1])
                if d < 4.0 and (best is None or d < best[0]): best = (d, r, n)
        if best: decap.append({"cap": cref, "pin": f"{best[1]}.{best[2]}", "capnet": net, "gnd_pad": gn, "val": cv})
    # chuoi cap nguon cho moi net VBUS
    chains = {}
    for vb in vbus:
        srcs = sorted([f"{r}.{n}" for r, n, _ in nets[vb] if r == conn])
        tvs = [f"{r}.{n}" for r, n, _ in nets[vb] if r.startswith("D") and len([1 for k in pad if k[0] == r]) == 2]
        bulk = sorted([(caps[r][3], f"{r}.{n}") for r, n, _ in nets[vb] if r in caps and r not in {d["cap"] for d in decap}], reverse=True)
        loads = [f"{r}.{n}" for r, n, _ in nets[vb] if r.startswith("J") and r != conn]
        path = tvs + [bulk[0][1]] if bulk else tvs
        path += loads
        chs = []
        if srcs and path:
            chs.append({"from": srcs[0], "path": path, "width": None})
        done = {srcs[0]} | set(path) if srcs else set(path)
        for d in decap:
            if d["capnet"] == vb:
                cp_ = caps[d["cap"]][4]
                near_src = min(srcs, key=lambda sp: math.hypot(pad[(conn, sp.split(".")[1])][1][0] - cp_[0], pad[(conn, sp.split(".")[1])][1][1] - cp_[1]))
                tp_ = [pad[(r_, n_)][1] for r_, n_, _ in nets[vb] if f"{r_}.{n_}" in path]
                d_src = math.hypot(pad[(conn, near_src.split(".")[1])][1][0] - cp_[0], pad[(conn, near_src.split(".")[1])][1][1] - cp_[1])
                d_trunk = min((math.hypot(q[0] - cp_[0], q[1] - cp_[1]) for q in tp_), default=1e9)
                # co TVS thi MOI nhanh phai lay SAU TVS/tu bulk; khong co TVS moi duoc lay tu pad nguon gan nhat
                strict = tvs and not os.environ.get("AUTOLAYOUT_LOOSE_TVS")   # bien chi de thu A/B
                frm = near_src if not strict and d_src <= 1.25 * d_trunk else "trunk"
                chs.append({"from": frm, "path": [f'{d["cap"]}.{caps[d["cap"]][1]}', d["pin"]], "width": 0.3}); done |= {f'{d["cap"]}.{caps[d["cap"]][1]}', d["pin"]}
        for r, n, _ in nets[vb]:
            if f"{r}.{n}" not in done and r != conn and not r.startswith("C"):
                chs.append({"from": "trunk", "path": [f"{r}.{n}"], "width": 0.25})
        chains[vb] = chs
    # ties GND: chan GND IC <-> pad GND tu decoupling ke ben (<=4 mm)
    ties = []
    for (r, n), (pnet, pos) in pad.items():
        if r in ics and isg(pnet):
            for d in decap:
                gp = next((p for p in fps[d["cap"]].Pads() if p.GetNumber() == d["gnd_pad"]), None)
                q = (gp.GetPosition().x / 1e6, gp.GetPosition().y / 1e6)
                if math.hypot(q[0] - pos[0], q[1] - pos[1]) < 4.0 and d["pin"].split(".")[0] == r:
                    ties.append([f"{r}.{n}", f'{d["cap"]}.{d["gnd_pad"]}'])
    # thu tu net
    rails = {d["capnet"] for d in decap} - set(vbus)
    allnets = {n for n in nets if not isg(n) and len(nets[n]) >= 2}
    hp = lambda n: (lambda xs, ys: (max(xs) - min(xs)) + (max(ys) - min(ys)))([p[2][0] for p in nets[n]], [p[2][1] for p in nets[n]])
    pro_cls = set()
    rest = sorted(allnets - set(usb) - set(cc) - set(vbus) - rails, key=hp)
    loads = [n for n in rest if re.search(r"LED|LOAD|MOTOR", n.upper())]; gates = [n for n in rest if "GATE" in n.upper()]
    slow = [n for n in rest if n not in loads and n not in gates]
    order = {"usb": usb_dp + usb_dm, "power": list(vbus) + loads, "cc": cc, "decap": sorted(rails), "gnd": ["GND"], "gates": gates, "slow": slow}
    return order, chains, [d for d in decap], ties, conn


def run(args, cwd, inp, outp, extra):
    env = dict(os.environ, PYROUTE_RES="0.05", MSYS_NO_PATHCONV="1")
    r = subprocess.run([KP, "-u", os.path.join(T, "pyroute.py"), inp, outp] + extra, capture_output=True, text=True, cwd=cwd, env=env)
    return r.stdout


def result(d):
    """diem cua 1 ung vien da route (nho hon = tot hon): net hong, chua noi, via tin hieu, chieu dai"""
    rep = open(os.path.join(d, "report.md"), encoding="utf-8").read()
    m = re.search(r"DRC: (\d+) vi pham, (\d+) chua noi; net route that bai: (\d+)", rep)
    tr = list(pcbnew.LoadBoard(os.path.join(d, "final.kicad_pcb")).GetTracks())
    vias = sum(t.GetClass() == "PCB_VIA" and "GND" not in t.GetNetname() for t in tr)
    length = sum(t.GetLength() for t in tr if t.GetClass() != "PCB_VIA") / 1e6
    return (int(m.group(3)), int(m.group(2)), int(m.group(1)), vias, round(length, 1))


def choose(pcb, pro, out, n):
    """route THAT moi hoan vi cum (song song) roi chep ban tot nhat ra out"""
    procs = []
    for k in range(n):
        d = os.path.join(out, f"cand_{k:02d}"); os.makedirs(d, exist_ok=True)
        while sum(p.poll() is None for p, _ in procs) >= max(2, (os.cpu_count() or 4) // 2):
            time.sleep(5)
        procs.append((subprocess.Popen([KP, os.path.abspath(__file__), pcb, pro, d], env=dict(os.environ, AUTOLAYOUT_PICK=str(k)),
                                       stdout=open(os.path.join(d, "log.txt"), "w"), stderr=subprocess.STDOUT), d))
    for p, _ in procs:
        p.wait()
    scored = sorted((result(d), d) for _, d in procs if os.path.exists(os.path.join(d, "report.md")))
    best = scored[0][1]
    for f in os.listdir(best):
        if os.path.isfile(os.path.join(best, f)):
            shutil.copy(os.path.join(best, f), os.path.join(out, f))
    table = ["", "## Chon hoan vi (net hong, chua noi, DRC, via tin hieu, dai mm)"] + [f"{os.path.basename(d)} {r}" for r, d in scored]
    with open(os.path.join(out, "report.md"), "a", encoding="utf-8") as f:
        f.write("\n".join(table))
    print("\n".join(table))


def main():
    pcb, pro, out = [os.path.abspath(a) for a in sys.argv[1:4]]
    os.makedirs(out, exist_ok=True)
    placed = os.path.join(out, "placed.kicad_pcb")
    shutil.copy(pcb, placed)
    # hoan vi cum linh kien giong nhau (netlist khong doi) truoc khi di day; luu pro SAU vi pcbnew ghi de .kicad_pro
    pick = os.environ.get("AUTOLAYOUT_PICK")
    sw = subprocess.run([KP, os.path.join(T, "swap_blocks.py"), pcb, placed, pick or "0"], capture_output=True, text=True)
    swaps = [l for l in sw.stdout.splitlines() if l.startswith(("cum ", "doi cho", "candidates"))]
    n = next((int(l.split()[1]) for l in swaps if l.startswith("candidates")), 1)
    if pick is None and n > 1:
        return choose(pcb, pro, out, n)
    shutil.copy(pro, os.path.join(out, "placed.kicad_pro"))
    pcb = placed
    order, chains, decap, ties, conn = infer(pcb)
    for v_ in chains.values():
        for c_ in v_:
            if c_.get("width") is None: c_.pop("width", None)
    intent = {"decoupling": [{"pin": d["pin"], "cap": d["cap"], "gnd_pin": ""} for d in decap], "power_chains": chains, "gnd_ties": ties}
    json.dump({"order": order, "intent": intent}, open(os.path.join(out, "plan.json"), "w"), indent=1, ensure_ascii=False)
    I = os.path.join(out, "intent_auto.json"); json.dump(intent, open(I, "w"), indent=1)
    gname = next((n for n in order["gnd"]), "GND")
    # ten GND that
    b = pcbnew.LoadBoard(pcb); gnd = next((p.GetNetname() for f in b.GetFootprints() for p in f.Pads() if "GND" in p.GetNetname().upper()), "GND")
    P = ["--pro", os.path.join(out, "placed.kicad_pro")]
    cc = ",".join(order["cc"])
    # tang khong co net phai BO QUA: --order "" tung lam router noi tat ca chan NC (net rong) voi nhau
    stages = [("usb", (["--order", ",".join(order["usb"])] + (["--lowprio", cc] if cc else [])) if order["usb"] else None),
              ("power", (["--intent", I, "--order", ",".join(order["power"])] + (["--lowprio", cc] if cc else [])) if order["power"] else None),
              ("cc", ["--order", cc] if cc else None),
              ("decap", ["--intent", I, "--order", ",".join(order["decap"] + [gnd + "@caps"])]),
              ("gnd", ["--order", gnd]),
              ("ties", ["--intent", I, "--order", gnd + "@ties"] if ties else None),
              ("gates", ["--order", ",".join(order["gates"] + order["slow"])] if (order["gates"] or order["slow"]) else None)]
    cur = "placed.kicad_pcb"; log = []; t0 = time.time()
    for i, (name, args) in enumerate(stages):
        if not args: continue
        nxt = f"s{i}_{name}.kicad_pcb"
        o = run(None, out, cur, nxt, P + args); log.append(f"== {name}\n" + "\n".join(l for l in o.splitlines() if re.match(r"(OK|FAIL)", l)))
        if os.path.exists(os.path.join(out, nxt)): cur = nxt
        print("xong", name, round(time.time() - t0), "s", flush=True)
    final = os.path.join(out, "final.kicad_pcb"); shutil.copy(os.path.join(out, cur), final); shutil.copy(os.path.join(out, "placed.kicad_pro"), os.path.join(out, "final.kicad_pro"))
    subprocess.run([CLI, "pcb", "drc", final, "-o", os.path.join(out, "drc.json"), "--format", "json", "--severity-all", "--refill-zones"], capture_output=True)
    d = json.load(open(os.path.join(out, "drc.json")))
    fails = sum(l.startswith("FAIL") for x in log for l in x.splitlines())
    vias = sum(int(m.group(1)) for x in log for m in re.finditer(r"vias=(\d+)", x) if "GND" not in x.splitlines()[0])
    subprocess.run([KP, os.path.join(T, "review2d.py"), final, os.path.join(out, "review.svg"), "autolayout - ban cuoi"], capture_output=True)
    if conn:
        subprocess.run([KP, os.path.join(T, "ref_view.py"), final, conn, os.path.join(out, "connector.svg"), f"{conn}", "8.5"], capture_output=True)
    sha = hashlib.sha256(open(final, "rb").read()).hexdigest()[:16]
    rep = [f"# autolayout - bao cao cuoi phien", f"PCB `final.kicad_pcb` SHA256 {sha}...", f"KiCad DRC: {len(d['violations'])} vi pham, {len(d['unconnected_items'])} chua noi; net route that bai: {fails}",
           "Anh: review.svg (toan board), connector.svg (vung connector, cung huong voi ref).", "",
           "## Hoan vi cum", *(swaps or ["khong"]), "", "## Schematic can kiem", *(sch_check.check(pcb) or ["khong"]), "", "## Ledger", *log]
    open(os.path.join(out, "report.md"), "w", encoding="utf-8").write("\n".join(rep))
    with open(os.path.join(HERE, "learn", "runs.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M"), "board_sha": sha, "drc": len(d["violations"]), "unconnected": len(d["unconnected_items"]), "route_fail": fails, "dir": out}) + "\n")
    print("DRC", len(d["violations"]), "| chua noi", len(d["unconnected_items"]), "| net that bai", fails, "| ->", os.path.join(out, "report.md"))


main()
