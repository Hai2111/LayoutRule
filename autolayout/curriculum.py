"""curriculum.py - chuong trinh LUYEN TAP: topology don gian tu sinh -> autolayout -> cham diem -> tich luy vao learn/.
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" curriculum.py gen  bus2ic  OUT_ROOT
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" curriculum.py run  OUT_ROOT [workers=8]
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" curriculum.py report OUT_ROOT

Bai 'bus2ic': 2 IC SOIC-16 doi dien nhau, 4 net bus song song (A.pin16..13 <-> B.pin1..4), GND/VCC.
Bien the: do lech doc dy (mm) giua 2 IC x huong xoay B (0 / 180). Cau hoi luyen tap: khi nao bus di thang, 0 via?
Ket qua (via, chieu dai, B.Cu, net that bai, DRC) ghi vao learn/exercises.jsonl va sinh ung vien bai hoc co SO LIEU di kem.
"""
import glob, json, os, re, shutil, subprocess, sys, time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
KP = r"C:\Program Files\KiCad\10.0\bin\python.exe"
FP = r"C:\Program Files\KiCad\10.0\share\kicad\footprints"
PRO = os.path.join(HERE, "default.kicad_pro")


def gen_bus2ic(root):
    import pcbnew
    from pcbnew import FromMM, VECTOR2I
    os.makedirs(root, exist_ok=True)
    n = 0
    for rot in (0, 180):
        for dy in (0.0, 1.0, 2.0, 3.0, 4.0, 6.0):
            d = os.path.join(root, f"bus2ic_rot{rot}_dy{int(dy * 10):02d}")
            os.makedirs(d, exist_ok=True)
            b = pcbnew.BOARD(); nets = {}
            def net(nm):
                if nm not in nets:
                    ni = pcbnew.NETINFO_ITEM(b, nm); b.Add(ni); nets[nm] = ni
                return nets[nm]
            def add(ref, lib, name, x, y, r, padnets):
                f = pcbnew.FootprintLoad(os.path.join(FP, lib + ".pretty"), name)
                f.SetReference(ref); f.SetPosition(VECTOR2I(FromMM(x), FromMM(y))); f.SetOrientationDegrees(r)
                for p in f.Pads():
                    nm = padnets.get(p.GetNumber())
                    if nm: p.SetNet(net(nm))
                b.Add(f)
            soic = ("Package_SO", "SOIC-16_3.9x9.9mm_P1.27mm")
            A = {str(16 - i): f"BUS{i}" for i in range(4)}; A.update({"8": "GND", "9": "VCC", "1": "GND"})
            B = {str(1 + i): f"BUS{i}" for i in range(4)}; B.update({"16": "VCC", "9": "GND", "8": "GND"})
            if rot == 180:   # B quay 180: pin i <-> pin 17-i
                B = {str(16 - i): f"BUS{i}" for i in range(4)}; B.update({"1": "VCC", "8": "GND", "9": "GND"})
            add("U1", *soic, 12.0, 15.0, 0, A)
            add("U2", *soic, 32.0, 15.0 + dy, rot, B)
            add("C1", "Capacitor_SMD", "C_0603_1608Metric", 12.0, 7.0, 90, {"1": "VCC", "2": "GND"})
            add("C2", "Capacitor_SMD", "C_0603_1608Metric", 32.0, 7.0, 90, {"1": "VCC", "2": "GND"})
            for (x1, y1, x2, y2) in ((0, 0, 44, 0), (44, 0, 44, 30), (44, 30, 0, 30), (0, 30, 0, 0)):
                s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(FromMM(0.1))
                s.SetStart(VECTOR2I(FromMM(x1), FromMM(y1))); s.SetEnd(VECTOR2I(FromMM(x2), FromMM(y2))); b.Add(s)
            z = pcbnew.ZONE(b); z.SetLayer(pcbnew.B_Cu); z.SetNet(net("GND")); z.SetMinThickness(FromMM(0.2))
            ol = z.Outline(); ol.NewOutline()
            for px, py in ((0.3, 0.3), (43.7, 0.3), (43.7, 29.7), (0.3, 29.7)): ol.Append(FromMM(px), FromMM(py))
            b.Add(z)
            b.Save(os.path.join(d, "placed.kicad_pcb")); shutil.copy(PRO, os.path.join(d, "placed.kicad_pro"))
            json.dump({"exercise": "bus2ic", "rot": rot, "dy": dy}, open(os.path.join(d, "meta.json"), "w")); n += 1
    print("tao", n, "bai")


def run_one(d):
    t0 = time.time()
    out = os.path.join(d, "run")
    r = subprocess.run([KP, os.path.join(HERE, "autolayout.py"), os.path.join(d, "placed.kicad_pcb"), os.path.join(d, "placed.kicad_pro"), out], capture_output=True, text=True)
    meta = json.load(open(os.path.join(d, "meta.json")))
    rep = open(os.path.join(out, "report.md"), encoding="utf-8").read() if os.path.exists(os.path.join(out, "report.md")) else ""
    vias = 0; length = 0.0; fails = 0
    for m in re.finditer(r"^(OK|FAIL)\s+(\S+)\s+pads=\s*\d+ len=\s*([\d.]+) mm vias=(\d+)", rep, re.M):
        if "GND" in m.group(2): continue
        if m.group(1) == "FAIL": fails += 1
        length += float(m.group(3)); vias += int(m.group(4))
    drc = re.search(r"KiCad DRC: (\d+) vi pham, (\d+) chua noi", rep)
    return dict(meta, vias=vias, length=round(length, 1), fail=fails, drc=int(drc.group(1)) if drc else -1,
                unconnected=int(drc.group(2)) if drc else -1, secs=round(time.time() - t0), dir=d)


def run(root, w):
    dirs = sorted(glob.glob(os.path.join(root, "*", "placed.kicad_pcb")))
    dirs = [os.path.dirname(x) for x in dirs]
    with Pool(w) as p:
        res = p.map(run_one, dirs, chunksize=1)
    with open(os.path.join(HERE, "learn", "exercises.jsonl"), "a", encoding="utf-8") as f:
        for r in res: f.write(json.dumps(dict(r, ts=time.strftime("%Y-%m-%d %H:%M")), ensure_ascii=False) + "\n")
    json.dump(res, open(os.path.join(root, "results.json"), "w"), indent=1)
    report(root)


def report(root):
    res = json.load(open(os.path.join(root, "results.json")))
    print("rot   dy(mm)  net_loi  via  dai(mm)  DRC  chua_noi  giay")
    for r in sorted(res, key=lambda r: (r["rot"], r["dy"])):
        print(f'{r["rot"]:3d}  {r["dy"]:6.1f}  {r["fail"]:7d}  {r["vias"]:3d}  {r["length"]:7.1f}  {r["drc"]:3d}  {r["unconnected"]:8d}  {r["secs"]:4d}')


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    c = sys.argv[1]
    if c == "gen": gen_bus2ic(sys.argv[3])
    elif c == "run": run(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 8)
    else: report(sys.argv[2])
