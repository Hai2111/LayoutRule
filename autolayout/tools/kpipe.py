"""kpipe.py STEPS.json [--from NAME] [--only NAME] : chay chuoi buoc layout co the tiep tuc khi bi ngat (L76).

STEPS.json: {"steps": [{"name": "v5a", "tool": "apply_place.py", "args": ["v4.kicad_pcb", "place_v5.json", "v5a.kicad_pcb"],
                         "in": ["v4.kicad_pcb", "place_v5.json"], "out": "v5a.kicad_pcb", "timeout": 600}, ...]}
- duong dan tuong doi tinh tu thu muc chua STEPS.json; tool tim trong thu muc tools (cung cho voi file nay).
- "out" khong co -> buoc chi in (vd place_score): stdout luu vao .kpipe/NAME.log va van co dau .done.
Moi buoc:
  1. .kpipe/NAME.lock co PID con song -> DUNG (dang co tien trinh khac chay buoc nay, khong chay chong).
     PID da chet -> buoc truoc bi ngat: xoa file tam __tmp__, chay lai tu dau buoc nay.
  2. .kpipe/NAME.done khop (hash input + tool + args) va out ton tai -> BO QUA.
  3. Chay; log day du vao .kpipe/NAME.log; ma loi != 0 hoac out khong co -> DUNG ca chuoi, in 20 dong cuoi log.
Tool phai ghi file bang ksave (nguyen tu) nen out khong bao gio dang do.
"""
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); from kenv import KP, CLI, FP  # KiCad tim tu dong (kenv.py)
TOOLS = os.path.dirname(os.path.abspath(__file__))
NOISE = ("assert", "image handler")


def alive(pid):
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong(); k.GetExitCodeProcess(h, ctypes.byref(code)); k.CloseHandle(h)
    return code.value == 259                       # STILL_ACTIVE


def digest(st, wd):
    h = hashlib.sha1(json.dumps([st["tool"], st["args"]]).encode())
    for f in st.get("in", []):
        with open(os.path.join(wd, f), "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def run(path, frm=None, only=None):
    wd = os.path.dirname(os.path.abspath(path)); kd = os.path.join(wd, ".kpipe"); os.makedirs(kd, exist_ok=True)
    steps = json.load(open(path, encoding="utf-8"))["steps"]
    started = frm is None
    for st in steps:
        n = st["name"]; started = started or n == frm
        if not started or (only and n != only):
            continue
        lock, done, log = (os.path.join(kd, n + e) for e in (".lock", ".done", ".log"))
        if os.path.exists(lock):
            pid = int(open(lock).read().strip() or 0)
            if pid and alive(pid):
                sys.exit(f"[{n}] DANG CHAY o PID {pid} - doi xong roi chay lai kpipe (khong chay chong)")
            print(f"[{n}] phat hien lan chay truoc bi ngat (PID {pid} da dung) -> don file tam, chay lai buoc nay")
            for f in os.listdir(wd):
                if "__tmp__" in f:
                    os.remove(os.path.join(wd, f))
            os.remove(lock)
            if os.path.exists(done):
                os.remove(done)
        missing = [f for f in st.get("in", []) if not os.path.exists(os.path.join(wd, f))]
        if missing:
            sys.exit(f"[{n}] thieu input {missing}")
        dg = digest(st, wd); out = st.get("out")
        if os.path.exists(done) and open(done).read().strip() == dg and (not out or os.path.exists(os.path.join(wd, out))):
            print(f"[{n}] da xong (input khong doi) - bo qua")
            continue
        t0 = time.time()
        with open(log, "w", encoding="utf-8") as lf:
            p = subprocess.Popen([KP, os.path.join(TOOLS, st["tool"])] + st["args"], cwd=wd, stdout=lf, stderr=subprocess.STDOUT,
                                 env={**os.environ, **st.get("env", {})})
            open(lock, "w").write(str(p.pid))
            try:
                rc = p.wait(timeout=st.get("timeout", 1800))
            except subprocess.TimeoutExpired:
                p.kill(); rc = "timeout"
        os.remove(lock)
        lines = [l.rstrip() for l in open(log, encoding="utf-8", errors="replace") if l.strip() and not any(z in l.lower() for z in NOISE)]
        if rc != 0 or (out and not os.path.exists(os.path.join(wd, out))):
            print(f"[{n}] LOI (rc={rc}) - dung chuoi. Cuoi log {log}:"); print("\n".join(lines[-20:]))
            sys.exit(1)
        open(done, "w").write(dg)
        print(f"[{n}] xong {time.time() - t0:.0f}s"); print("   " + "\n   ".join(lines[-8:]))


if __name__ == "__main__":
    a = sys.argv[1:]
    get = lambda k: a[a.index(k) + 1] if k in a else None
    run(a[0], get("--from"), get("--only"))
