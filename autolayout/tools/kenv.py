"""kenv.py - tim KiCad tren may hien tai (dung cho moi tool, de chay duoc tren may khac).

Thu tu uu tien:
  1. bien moi truong KICAD_PY / KICAD_CLI / KICAD_FP
  2. python dang chay neu import duoc pcbnew (vd dang chay bang python cua KiCad)
  3. duong dan cai dat chuan: Windows C:\\Program Files\\KiCad\\<ver>\\bin, macOS /Applications/KiCad, Linux /usr/bin
Dung:  from kenv import KP, CLI, FP
"""
import glob
import os
import shutil
import sys


def _win_candidates():
    roots = [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramW6432", r"C:\Program Files")]
    out = []
    for r in roots:
        for d in sorted(glob.glob(os.path.join(r, "KiCad", "*")), reverse=True):     # ban moi nhat truoc
            out.append(os.path.join(d, "bin"))
    return out


def _find():
    py = os.environ.get("KICAD_PY"); cli = os.environ.get("KICAD_CLI"); fp = os.environ.get("KICAD_FP")
    bins = []
    if sys.platform == "win32":
        bins = _win_candidates()
    elif sys.platform == "darwin":
        bins = ["/Applications/KiCad/KiCad.app/Contents/MacOS"]
    else:
        bins = ["/usr/bin", "/usr/local/bin"]
    if not py:
        try:
            import pcbnew  # noqa: F401
            py = sys.executable
        except ImportError:
            for b in bins:
                c = os.path.join(b, "python.exe" if sys.platform == "win32" else "python3")
                if os.path.isfile(c):
                    py = c; break
    if not cli:
        for b in bins:
            c = os.path.join(b, "kicad-cli.exe" if sys.platform == "win32" else "kicad-cli")
            if os.path.isfile(c):
                cli = c; break
        cli = cli or shutil.which("kicad-cli")
    if not fp and cli:
        base = os.path.dirname(os.path.dirname(cli))
        for c in (os.path.join(base, "share", "kicad", "footprints"), "/usr/share/kicad/footprints"):
            if os.path.isdir(c):
                fp = c; break
    return py, cli, fp


KP, CLI, FP = _find()

if __name__ == "__main__":
    print("KICAD_PY :", KP)
    print("KICAD_CLI:", CLI)
    print("KICAD_FP :", FP)
    if not KP or not CLI:
        sys.exit("thieu KiCad: cai KiCad 10 hoac dat KICAD_PY / KICAD_CLI")
