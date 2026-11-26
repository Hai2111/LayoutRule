"""render2d.py - ve anh 2D (F.Cu do, B.Cu xanh) + metrics net, khong can PIL/numpy.
Chay bang python KiCad:  python render2d.py BOARD.kicad_pcb OUT.png [--metrics]
Mau: F.Cu = do, B.Cu = xanh duong, via = vang, pad = cam, outline = trang. Zone GND khong ve.
"""
import math
import struct
import sys
import zlib
import pcbnew

S = 36  # px per mm
PAD = 2.0


def main():
    path, out = sys.argv[1], sys.argv[2]
    b = pcbnew.LoadBoard(path)
    bb = b.GetBoardEdgesBoundingBox()
    x0, y0 = bb.GetLeft() / 1e6 - PAD, bb.GetTop() / 1e6 - PAD
    W = int((bb.GetWidth() / 1e6 + 2 * PAD) * S)
    H = int((bb.GetHeight() / 1e6 + 2 * PAD) * S)
    img = bytearray([24, 24, 28] * (W * H))

    def px(x, y, c, a=1.0):
        if 0 <= x < W and 0 <= y < H:
            i = (y * W + x) * 3
            for k in range(3):
                img[i + k] = int(img[i + k] * (1 - a) + c[k] * a)

    def mm2px(x, y):
        return (x / 1e6 - x0) * S, (y / 1e6 - y0) * S

    def seg(ax, ay, bx, by, w, c, a=0.85):
        ax, ay = mm2px(ax, ay)
        bx, by = mm2px(bx, by)
        r = w * S / 2
        for y in range(int(min(ay, by) - r) - 1, int(max(ay, by) + r) + 2):
            for x in range(int(min(ax, bx) - r) - 1, int(max(ax, bx) + r) + 2):
                dx, dy = bx - ax, by - ay
                L = dx * dx + dy * dy
                t = 0 if L == 0 else max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / L))
                d = math.hypot(x - (ax + t * dx), y - (ay + t * dy))
                if d <= r:
                    px(x, y, c, a)

    def rect(cx, cy, w, h, c, a=0.9):
        cx, cy = mm2px(cx, cy)
        for y in range(int(cy - h * S / 2), int(cy + h * S / 2) + 1):
            for x in range(int(cx - w * S / 2), int(cx + w * S / 2) + 1):
                px(x, y, c, a)

    def disc(cx, cy, d, c, a=1.0):
        cx, cy = mm2px(cx, cy)
        r = d * S / 2
        for y in range(int(cy - r) - 1, int(cy + r) + 2):
            for x in range(int(cx - r) - 1, int(cx + r) + 2):
                if math.hypot(x - cx, y - cy) <= r:
                    px(x, y, c, a)

    RED, BLUE, YEL, ORG, WHT = (230, 70, 70), (70, 130, 240), (240, 220, 60), (240, 150, 40), (240, 240, 240)
    # B.Cu first then F.Cu on top
    for layer, col in ((pcbnew.B_Cu, BLUE), (pcbnew.F_Cu, RED)):
        for t in b.GetTracks():
            if t.GetClass() == "PCB_TRACK" and t.GetLayer() == layer:
                seg(t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y, t.GetWidth() / 1e6, col)
    for fp in b.GetFootprints():
        for p in fp.Pads():
            pos = p.GetPosition()
            sz = p.GetSize()
            ang = round(p.GetOrientationDegrees()) % 180
            w, h = (sz.x, sz.y) if ang == 0 else (sz.y, sz.x)
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                disc(pos.x, pos.y, max(sz.x, sz.y) / 1e6, ORG, 0.9)
            else:
                rect(pos.x / 1e6 * 1e6, pos.y / 1e6 * 1e6, 0, 0, ORG, 0) if False else None
                cx, cy = mm2px(pos.x, pos.y)
                for y in range(int(cy - h / 1e6 * S / 2), int(cy + h / 1e6 * S / 2) + 1):
                    for x in range(int(cx - w / 1e6 * S / 2), int(cx + w / 1e6 * S / 2) + 1):
                        px(x, y, ORG, 0.55)
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            disc(t.GetPosition().x, t.GetPosition().y, t.GetWidth(pcbnew.F_Cu) / 1e6, YEL, 1.0)
            disc(t.GetPosition().x, t.GetPosition().y, t.GetDrillValue() / 1e6, (20, 20, 20), 1.0)
    for d in b.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts:
            seg(d.GetStart().x, d.GetStart().y, d.GetEnd().x, d.GetEnd().y, 0.12, WHT, 1.0)
    # labels not drawn (no font); refs listed on stdout
    # write png
    raw = b"".join(b"\x00" + bytes(img[y * W * 3:(y + 1) * W * 3]) for y in range(H))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    open(out, "wb").write(png)
    print("png", out, W, H, "origin_mm", x0, y0, "scale px/mm", S)

    # own K1 check (repo drc_body_keepout.py cannot parse KiCad 10 files): F.Cu tracks inside the connector body
    j1 = [f for f in b.GetFootprints() if f.GetReference() == "J1"][0]
    jx, jy = j1.GetPosition().x / 1e6, j1.GetPosition().y / 1e6
    hits = []
    for t in b.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetLayer() == pcbnew.F_Cu:
            for pt in (t.GetStart(), t.GetEnd()):
                x, y = pt.x / 1e6, pt.y / 1e6
                if abs(x - jx) <= 5.3 and y > jy - 3.68 + 0.6 and y < jy + 4.3:
                    hits.append((t.GetNetname(), round(x, 2), round(y, 2)))
                    break
    print("K1-own (F.Cu tracks under connector body, y>pad row):", len(hits), hits[:6])

    if "--metrics" in sys.argv:
        stats = {}
        for t in b.GetTracks():
            n = t.GetNetname()
            s = stats.setdefault(n, {"len": 0.0, "vias": 0, "F": 0.0, "B": 0.0, "wmin": 9, "wmax": 0})
            if t.GetClass() == "PCB_VIA":
                s["vias"] += 1
            else:
                L = t.GetLength() / 1e6
                s["len"] += L
                s["F" if t.GetLayer() == pcbnew.F_Cu else "B"] += L
                w = t.GetWidth() / 1e6
                s["wmin"] = min(s["wmin"], w)
                s["wmax"] = max(s["wmax"], w)
        print("net      len_mm  F_mm  B_mm  vias  w_min-w_max")
        for n in sorted(stats):
            s = stats[n]
            print(f"{n:8s} {s['len']:6.1f} {s['F']:5.1f} {s['B']:5.1f}  {s['vias']:3d}  {s['wmin']:.2f}-{s['wmax']:.2f}")


main()
