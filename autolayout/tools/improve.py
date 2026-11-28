"""improve.py - GO DAY DI LAI (rip-up and reroute) sau khi route xong.
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" improve.py RUN_DIR OUT_DIR [workers=4] [max_rounds=6]
RUN_DIR = thu muc ket qua autolayout (final.kicad_pcb, final.kicad_pro, intent_auto.json, plan.json).
Moi vong: voi moi net dang co via, thu (a) di lai mot minh, (b) xoa cung 1 net khac roi di net-co-via TRUOC. Nhan ban tot nhat
neu DRC khong loi, khong ho, va (via tin hieu, chieu dai) nho hon. Luat thu tu nguon giu nguyen (net nguon di lai theo intent).
"""
import json, os, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); from kenv import KP, CLI, FP  # KiCad tim tu dong (kenv.py)
RIP = "import pcbnew,sys\nb=pcbnew.LoadBoard(sys.argv[1]); ns=set(sys.argv[3].split(','))\n" \
      "[b.Remove(t) for t in list(b.GetTracks()) if t.GetNetname() in ns]\nb.Save(sys.argv[2])\n"
STAT = "import pcbnew,sys,json\nt=list(pcbnew.LoadBoard(sys.argv[1]).GetTracks()); v={}\n" \
       "for x in t:\n  if x.GetClass()=='PCB_VIA' and 'GND' not in x.GetNetname(): v[x.GetNetname()]=v.get(x.GetNetname(),0)+1\n" \
       "print(json.dumps([v, sum(x.GetLength() for x in t if x.GetClass()!='PCB_VIA')/1e6]))\n"
ENV = dict(os.environ, PYROUTE_RES="0.05", MSYS_NO_PATHCONV="1", PYROUTE_MAXEXP="1200000")


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, env=ENV, **kw).stdout


def stat(board):
    v, length = json.loads(sh([KP, "-c", STAT, board]).strip().splitlines()[-1])
    return v, (sum(v.values()), round(length, 1))


def trial(args):
    idx, cur, nets, work, pro, intent = args
    d = os.path.join(work, f"t{idx:03d}"); os.makedirs(d, exist_ok=True)
    rip, out = os.path.join(d, "rip.kicad_pcb"), os.path.join(d, "out.kicad_pcb")
    sh([KP, "-c", RIP, cur, rip, ",".join(nets)])
    shutil.copy(pro, os.path.join(d, "rip.kicad_pro"))
    try:
        log = sh([KP, os.path.join(HERE, "pyroute.py"), rip, out, "--pro", pro, "--intent", intent, "--order", ",".join(nets)], timeout=600)
    except subprocess.TimeoutExpired:
        return None
    if not os.path.exists(out) or any(l.startswith("FAIL") for l in log.splitlines()):
        return None
    return stat(out)[1], nets, out


def drc_ok(board, pro, work):
    chk = os.path.join(work, "chk.kicad_pcb")
    shutil.copy(board, chk); shutil.copy(pro, os.path.join(work, "chk.kicad_pro"))
    rep = os.path.join(work, "chk_drc.json")
    subprocess.run([CLI, "pcb", "drc", chk, "-o", rep, "--format", "json", "--severity-all", "--refill-zones"], capture_output=True)
    j = json.load(open(rep, encoding="utf-8"))
    return not j["unconnected_items"] and not any(v["severity"] == "error" for v in j["violations"])


def main():
    run, out = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
    W = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    rounds = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    os.makedirs(out, exist_ok=True)
    pro = os.path.join(out, "final.kicad_pro"); shutil.copy(os.path.join(run, "final.kicad_pro"), pro)
    intent = os.path.join(run, "intent_auto.json")
    order = json.load(open(os.path.join(run, "plan.json"), encoding="utf-8"))["order"]
    signals = order["gates"] + order["slow"]
    partners = signals + order["power"] + order["usb"]
    cur = os.path.join(out, "cur.kicad_pcb"); shutil.copy(os.path.join(run, "final.kicad_pcb"), cur)
    vias, score = stat(cur)
    print("bat dau", score, vias, flush=True)
    for r in range(rounds):
        t0 = time.time()
        bad = [n for n in vias if n in signals]
        jobs = [[a] for a in bad] + [[a, b] for a in bad for b in partners if b != a]
        work = os.path.join(out, f"round{r}"); os.makedirs(work, exist_ok=True)
        with ThreadPoolExecutor(W) as p:
            res = list(p.map(trial, [(i, cur, n, work, pro, intent) for i, n in enumerate(jobs)]))
        better = sorted((x for x in res if x and x[0] < score), key=lambda x: x[0])
        chosen = next((x for x in better if drc_ok(x[2], pro, work)), None)
        if not chosen:
            print(f"vong {r}: {len(jobs)} thu, khong con cai thien ({round(time.time() - t0)} s)", flush=True)
            break
        shutil.copy(chosen[2], cur)
        vias, score = stat(cur)
        print(f"vong {r}: {len(jobs)} thu, go {chosen[1]} -> {score} ({round(time.time() - t0)} s)", flush=True)
        shutil.copy(cur, os.path.join(out, "final.kicad_pcb"))
    shutil.copy(cur, os.path.join(out, "final.kicad_pcb"))
    print("ket qua", score, vias, "DRC_ok", drc_ok(cur, pro, out))


main()
