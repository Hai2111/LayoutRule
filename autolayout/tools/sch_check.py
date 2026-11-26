"""sch_check.py - RA schematic truoc khi layout (chi CANH BAO, khong tu sua mach). Bai hoc tu ban Vector 2026-11-26.
  sch_check.py BOARD.kicad_pcb       Moi dong la mot diem CAN KIEM voi datasheet.
"""
import re, sys
import pcbnew


def check(path):
    b = pcbnew.LoadBoard(path)
    fps = {f.GetReference(): str(f.GetValue()) for f in b.GetFootprints()}
    nets = {}
    for f in b.GetFootprints():
        for p in f.Pads():
            nets.setdefault(p.GetNetname(), []).append(f.GetReference())
    out = []
    for n, rs in nets.items():
        short = n.lstrip("/").upper()
        ic = any(r.startswith("U") for r in rs)
        if ic and re.search(r"(NRST|RESET|^RST|^EN$)", short) and not any(r.startswith("C") for r in rs):
            out.append(f"CAN KIEM: net {n} (reset/enable cua IC) khong co tu loc xuong GND")
        if short == "V3" and any("CH340" in fps[r].upper() for r in rs):
            out += [f"CAN KIEM: tu {r}={fps[r]} tren chan V3 cua CH340; datasheet thuong ghi 100n"
                    for r in rs if r.startswith("C") and not re.match(r"(100n|0\.1u)", fps[r].lower())]
    out += [f"CAN KIEM: {r}={v} la ten chung, chua chon ma linh kien that" for r, v in fps.items() if r.startswith("D") and v.upper().startswith("TVS_")]
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(check(sys.argv[1])) or "khong co canh bao")
