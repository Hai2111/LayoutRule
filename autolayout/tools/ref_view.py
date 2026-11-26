"""ref_view.py - ve vung quanh 1 linh kien (connector) tren 1 board, CUNG huong de so sanh bang mat voi ref design.
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" ref_view.py BOARD.kicad_pcb REF OUT.svg TITLE [RADIUS_MM]
Tu dong xoay 180 do neu linh kien quay 180 -> than connector luon o DUOI, duong thoat huong LEN tren moi board.
Net mau theo ten; pad theo bbox that; track F.Cu net lien, B.Cu nhat; via tron trang. Khong in so lieu.
"""
import sys
import pcbnew

PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#17becf", "#bcbd22", "#393b79", "#637939", "#a55194"]
S = 40


def main():
    path, ref, out, title = sys.argv[1:5]
    R = float(sys.argv[5]) if len(sys.argv) > 5 else 13.0
    b = pcbnew.LoadBoard(path)
    fp = [f for f in b.GetFootprints() if f.GetReference() == ref][0]
    flip = abs(round(fp.GetOrientationDegrees()) % 360) == 180
    sig = [p for p in fp.Pads() if p.GetNetname() and not p.GetNumber().startswith("SH")]
    cx = sum(p.GetPosition().x for p in sig) / len(sig) / 1e6
    cy = sum(p.GetPosition().y for p in sig) / len(sig) / 1e6

    def tx(x):           # mm -> px (co lat 180 quanh tam)
        d = (x - cx) * (-1 if flip else 1)
        return (d + R) * S

    def ty(y):
        d = (y - cy) * (-1 if flip else 1)
        # dua hang pad len gan 40% chieu cao, than connector xuong duoi
        return (d + R * 1.05) * S

    W = int(2 * R * S); H = int(1.6 * R * S)
    nets = {}
    def col(n):
        if not n:
            return "#999"
        if "GND" in n.upper():
            return "#777"
        if n not in nets:
            nets[n] = PALETTE[len(nets) % len(PALETTE)]
        return nets[n]

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H + 26}" font-family="Segoe UI,Arial" font-size="11">',
         '<rect width="100%" height="100%" fill="#fff"/>', f'<text x="6" y="16" font-size="13" font-weight="600">{title}</text>',
         f'<g transform="translate(0,22)"><rect width="{W}" height="{H}" fill="#fafafa" stroke="#ccc"/>']
    # courtyards + refdes
    for f in b.GetFootprints():
        c = f.GetBoundingBox(False)
        l, t, r_, bt = c.GetLeft() / 1e6, c.GetTop() / 1e6, c.GetRight() / 1e6, c.GetBottom() / 1e6
        if abs((l + r_) / 2 - cx) > R + 4 or abs((t + bt) / 2 - cy) > R + 4:
            continue
        xa, xb = sorted((tx(l), tx(r_))); ya, yb = sorted((ty(t), ty(bt)))
        o.append(f'<rect x="{xa:.0f}" y="{ya:.0f}" width="{xb-xa:.0f}" height="{yb-ya:.0f}" fill="none" stroke="#b0b" stroke-width="0.6" stroke-dasharray="3,3"/>')
    # tracks
    for layer, op, dash in ((pcbnew.B_Cu, 0.45, ' stroke-dasharray="7,4"'), (pcbnew.F_Cu, 0.85, "")):
        for t in b.GetTracks():
            if t.GetClass() == "PCB_TRACK" and t.GetLayer() == layer:
                a, e = t.GetStart(), t.GetEnd()
                x1, y1, x2, y2 = tx(a.x / 1e6), ty(a.y / 1e6), tx(e.x / 1e6), ty(e.y / 1e6)
                if max(x1, x2) < -20 or min(x1, x2) > W + 20 or max(y1, y2) < -20 or min(y1, y2) > H + 20:
                    continue
                o.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{col(t.GetNetname())}" '
                         f'stroke-width="{max(1.2, t.GetWidth()/1e6*S):.1f}" stroke-linecap="round" stroke-opacity="{op}"{dash}/>')
    # pads
    for f in b.GetFootprints():
        for p in f.Pads():
            bb = p.GetBoundingBox()
            l, t, r_, bt = bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6
            xa, xb = sorted((tx(l), tx(r_))); ya, yb = sorted((ty(t), ty(bt)))
            if xb < -10 or xa > W + 10 or yb < -10 or ya > H + 10:
                continue
            c = col(p.GetNetname())
            if p.GetShape() in (pcbnew.PAD_SHAPE_CIRCLE, pcbnew.PAD_SHAPE_OVAL):
                o.append(f'<ellipse cx="{(xa+xb)/2:.1f}" cy="{(ya+yb)/2:.1f}" rx="{(xb-xa)/2:.1f}" ry="{(yb-ya)/2:.1f}" fill="{c}" fill-opacity="0.5" stroke="{c}"/>')
            else:
                o.append(f'<rect x="{xa:.1f}" y="{ya:.1f}" width="{xb-xa:.1f}" height="{yb-ya:.1f}" fill="{c}" fill-opacity="0.5" stroke="{c}" stroke-width="0.8"/>')
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            x, y = tx(t.GetPosition().x / 1e6), ty(t.GetPosition().y / 1e6)
            if 0 <= x <= W and 0 <= y <= H:
                o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{t.GetWidth(pcbnew.F_Cu)/2e6*S:.1f}" fill="#fff" stroke="{col(t.GetNetname())}" stroke-width="1.6"/>')
    for f in b.GetFootprints():
        c = f.GetBoundingBox(False)
        x, y = tx((c.GetLeft() + c.GetRight()) / 2e6), ty((c.GetTop() + c.GetBottom()) / 2e6)
        if 0 <= x <= W and 0 <= y <= H:
            o.append(f'<text x="{x:.0f}" y="{y:.0f}" text-anchor="middle" font-weight="600" fill="#222">{f.GetReference()}</text>')
    o.append("</g></svg>")
    open(out, "w", encoding="utf-8").write("\n".join(o))
    print("ok", out, "flip" if flip else "")


main()
