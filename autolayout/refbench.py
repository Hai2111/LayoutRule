"""refbench.py - KHAI THAC REF DESIGN: xoa track/via cua cac board ref (nguoi da route), cho autolayout route lai, SO VOI BAN CUA NGUOI.
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" refbench.py OUT_DIR [workers=4]
Do duoc: ti le net route, DRC, via/100mm va ti le B.Cu so voi chinh ban ref goc (ground truth). Thieu GND plane B.Cu -> them zone GND B.Cu (router gia dinh plane o B.Cu).
"""
import glob, json, os, re, shutil, subprocess, sys, time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
KP = r"C:\Program Files\KiCad\10.0\bin\python.exe"
TOOLS = os.path.join(HERE, "tools")
REF = os.path.join(HERE, "..", "ref", "Kicad")
BOARDS = ["1908_Lora_Externder/Lora_Externder/LoraExt.kicad_pcb", "Bike Track/Bike Track.kicad_pcb", "LTE Network card/BLE2LTE.kicad_pcb",
          "RA01_SCH_PCB/RA-01SCH_SMOKE.kicad_pcb", "SR01/0722_SR01.kicad_pcb", "DaLogg/BUTTON.kicad_pcb"]
DEFPRO = os.path.join(HERE, "default.kicad_pro")


def prep(rel, out):
    name = rel.split("/")[0].replace(" ", "_")
    d = os.path.join(out, name); os.makedirs(d, exist_ok=True)
    src = os.path.join(REF, rel)
    subprocess.run(["python", os.path.join(TOOLS, "strip_tracks.py"), src, os.path.join(d, "stripped.kicad_pcb")], capture_output=True)
    pro = os.path.splitext(src)[0] + ".kicad_pro"
    return name, d, src, pro


def addzone(d):
    import pcbnew
    from pcbnew import FromMM
    b = pcbnew.LoadBoard(os.path.join(d, "stripped.kicad_pcb"))
    has = any("GND" in z.GetNetname().upper() and z.IsOnLayer(pcbnew.B_Cu) for z in b.Zones())
    if not has:
        gnd = next((n for n in {p.GetNetname() for f in b.GetFootprints() for p in f.Pads()} if "GND" in n.upper()), None)
        if gnd:
            bb = b.GetBoardEdgesBoundingBox(); z = pcbnew.ZONE(b); z.SetLayer(pcbnew.B_Cu); z.SetNet(b.FindNet(gnd)); z.SetMinThickness(FromMM(0.2))
            ol = z.Outline(); ol.NewOutline(); m = FromMM(0.3)
            for x, y in ((bb.GetLeft() + m, bb.GetTop() + m), (bb.GetRight() - m, bb.GetTop() + m), (bb.GetRight() - m, bb.GetBottom() - m), (bb.GetLeft() + m, bb.GetBottom() - m)):
                ol.Append(x, y)
            b.Add(z)
    b.Save(os.path.join(d, "placed.kicad_pcb"))


def work(rel_out):
    rel, out = rel_out
    name, d, src, pro = prep(rel, out)
    addzone(d)
    shutil.copy(pro if os.path.exists(pro) else DEFPRO, os.path.join(d, "placed.kicad_pro"))
    t0 = time.time()
    env = dict(os.environ, PYROUTE_MAXEXP="500000", MSYS_NO_PATHCONV="1")
    try:
        subprocess.run([KP, os.path.join(HERE, "autolayout.py"), os.path.join(d, "placed.kicad_pcb"), os.path.join(d, "placed.kicad_pro"), os.path.join(d, "run")],
                       capture_output=True, text=True, env=env, timeout=40 * 60)
    except subprocess.TimeoutExpired:
        pass
    return name, src, d, round(time.time() - t0)


def analyse(name, src, d, secs):
    sys.path.insert(0, TOOLS)
    import importlib.util
    spec = importlib.util.spec_from_file_location("rp", os.path.join(TOOLS, "ref_profile.py"))
    src_txt = open(os.path.join(TOOLS, "ref_profile.py"), encoding="utf-8").read().replace("\nmain()", "\n").replace('if __name__ == "__main__":', "if False:")
    g = {"__name__": "rp"}; exec(compile(src_txt, "rp", "exec"), g)
    rep = os.path.join(d, "run", "report.md")
    row = {"board": name, "secs": secs}
    if not os.path.exists(rep):
        row.update(done=False); return row
    t = open(rep, encoding="utf-8").read()
    ok = len(re.findall(r"^OK\s", t, re.M)); fail = len(re.findall(r"^FAIL\s", t, re.M))
    drc = re.search(r"KiCad DRC: (\d+) vi pham, (\d+) chua noi", t)
    final = os.path.join(d, "run", "final.kicad_pcb")
    try:
        hm = g["metrics"](src); fm = g["metrics"](final)
    except Exception as e:
        hm = fm = None
    row.update(done=True, nets_ok=ok, nets_fail=fail, completion=round(ok / max(1, ok + fail), 2), drc=int(drc.group(1)) if drc else -1,
               unconnected=int(drc.group(2)) if drc else -1,
               human_via=hm and hm["via_per_100mm"], auto_via=fm and fm["via_per_100mm"], human_bcu=hm and hm["bcu_share"], auto_bcu=fm and fm["bcu_share"],
               failed=[l.split()[1] + " " + (re.search(r"unrouted=(.*)", l).group(1)[:60] if re.search(r"unrouted=(.*)", l) else "") for l in t.splitlines() if l.startswith("FAIL")][:12])
    return row


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    out = os.path.abspath(sys.argv[1]); W = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    os.makedirs(out, exist_ok=True)
    with Pool(W) as p:
        res = p.map(work, [(b, out) for b in BOARDS], chunksize=1)
    rows = [analyse(*r) for r in res]
    json.dump(rows, open(os.path.join(out, "refbench.json"), "w"), indent=1, ensure_ascii=False)
    with open(os.path.join(HERE, "learn", "exercises.jsonl"), "a", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(dict(r, exercise="refbench", ts=time.strftime("%Y-%m-%d %H:%M")), ensure_ascii=False) + "\n")
    print("board              net_ok net_loi hoan_thanh DRC chua_noi  via/100mm(nguoi->auto)  B.Cu(nguoi->auto)  phut")
    for r in rows:
        if not r.get("done"): print(f'{r["board"]:18s} KHONG CHAY XONG'); continue
        print(f'{r["board"]:18s} {r["nets_ok"]:6d} {r["nets_fail"]:7d} {r["completion"]:9.2f} {r["drc"]:4d} {r["unconnected"]:8d}  {r["human_via"]}->{r["auto_via"]}   {r["human_bcu"]}->{r["auto_bcu"]}   {r["secs"]//60}')
