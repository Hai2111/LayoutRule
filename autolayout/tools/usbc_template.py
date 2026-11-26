"""usbc_template.py - trich LOGIC BO TRI quanh connector USB-C tu ref design (khong phai con so do dac).
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" usbc_template.py BOARD:CONN_REF [BOARD:CONN_REF ...]

Khung toa do cua connector: goc = tam hang pad tin hieu, x sang phai, y = HUONG THOAT (len) khi than connector o duoi.
Moi linh kien lan can duoc gan VAI TRO theo noi no noi toi (net cua pad connector), khong theo ten:
  CC_R (tro keo CC), ESD (IC co chan tren D+/D-), TVS (D noi VBUS-GND), VBUS_C (tu noi VBUS-GND), D_R (tro noi tiep D+/D-).
In vi tri (dx, dy) va huong xoay tuong doi -> de ap thanh MAU bo tri cho board dich.
"""
import math
import sys

import pcbnew


def pt(p):
    return (p.x / 1e6, p.y / 1e6)


def analyse(path, cref):
    b = pcbnew.LoadBoard(path)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    conn = fps[cref]
    rot = int(round(conn.GetOrientationDegrees())) % 360
    s = -1 if rot == 180 else 1
    pads = {p.GetNumber(): p for p in conn.Pads()}
    sig = [p for p in conn.Pads() if p.GetNetname() and not p.GetNumber().startswith("SH")]
    cx = sum(pt(p.GetPosition())[0] for p in sig) / len(sig)
    cy = sum(pt(p.GetPosition())[1] for p in sig) / len(sig)

    def net_of(*names):
        return {pads[n].GetNetname() for n in names if n in pads and pads[n].GetNetname()}
    cc = net_of("A5", "B5")
    dn = net_of("A6", "B6", "A7", "B7")
    vb = net_of("A4_B9", "B4_A9", "A4", "A9", "B4", "B9")
    out = []
    for ref, f in fps.items():
        if ref == cref:
            continue
        x, y = pt(f.GetPosition())
        xf, yf = s * (x - cx), -s * (y - cy)
        if abs(xf) > 12 or yf < -6 or yf > 14:
            continue
        nets = {p.GetNetname() for p in f.Pads() if p.GetNetname()}
        np_ = len(list(f.Pads()))
        role = None
        pre = ref.rstrip("0123456789")
        if pre.startswith("R") and nets & cc and np_ == 2:
            role = "CC_R"
        elif np_ >= 3 and nets & dn and pre.startswith(("U", "IC", "D")):
            role = "ESD"
        elif np_ == 2 and nets & vb and any("GND" in n.upper() for n in nets):
            role = "TVS" if pre.startswith("D") else ("VBUS_C" if pre.startswith("C") else None)
        elif pre.startswith("R") and nets & dn and np_ == 2:
            role = "D_R"
        if role:
            r_rel = (int(round(f.GetOrientationDegrees())) - rot) % 180
            out.append((role, ref, round(xf, 1), round(yf, 1), r_rel))
    return rot, out


def main():
    allr = {}
    for a in sys.argv[1:]:
        path, cref = a.rsplit(":", 1)
        name = path.replace("\\", "/").split("/")[-2] + "/" + cref
        rot, items = analyse(path, cref)
        allr[name] = items
        print(f"== {name} (rot {rot})")
        for role, ref, dx, dy, rr in sorted(items):
            print(f"   {role:7s} {ref:6s} dx={dx:5.1f} dy={dy:5.1f} xoay_tuong_doi={rr}")


main()
