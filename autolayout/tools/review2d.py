"""review2d.py - anh review 2D kieu "iteration N": luoi mm, net mau, pad theo bbox that, refdes, legend.
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" review2d.py BOARD.kicad_pcb OUT.svg [title]
Xuat SVG (co chu). Mo bang trinh duyet; lop B.Cu ve nhat + net dut net (stroke-dasharray) de phan biet voi F.Cu.
"""
import sys
import pcbnew

PALETTE = ["#1f77b4", "#aec7e8", "#ff7f0e", "#ffbb78", "#2ca02c", "#98df8a", "#7f7f7f", "#d62728",
           "#9467bd", "#c5b0d5", "#8c564b", "#c49c94", "#e377c2", "#f7b6d2", "#bcbd22", "#dbdb8d",
           "#17becf", "#9edae5", "#393b79", "#637939"]
S = 40  # px per mm
M = 60  # margin px


def main():
    path, out = sys.argv[1], sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else path
    b = pcbnew.LoadBoard(path)
    bb = b.GetBoardEdgesBoundingBox()
    x0, y0 = bb.GetLeft(), bb.GetTop()
    W, H = bb.GetWidth() / 1e6, bb.GetHeight() / 1e6

    def X(v): return M + (v - x0) / 1e6 * S
    def Y(v): return M + (v - y0) / 1e6 * S

    nets = sorted({t.GetNetname() for t in b.GetTracks() if t.GetNetname()} |
                  {p.GetNetname() for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()})
    col = {n: ("#888888" if n == "GND" else PALETTE[i % len(PALETTE)]) for i, n in enumerate(nets)}
    col[""] = "#bbbbbb"

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{M*2+W*S+170:.0f}" height="{M*2+H*S:.0f}" '
               f'font-family="Segoe UI,Arial" font-size="12">')
    svg.append('<rect width="100%" height="100%" fill="#fff"/>')
    svg.append(f'<text x="{M+W*S/2:.0f}" y="24" text-anchor="middle" font-size="16">{title}</text>')
    # grid 1 mm + labels every 1 mm
    for i in range(int(W) + 1):
        svg.append(f'<line x1="{M+i*S}" y1="{M}" x2="{M+i*S}" y2="{M+H*S}" stroke="#eee"/>')
        svg.append(f'<text x="{M+i*S}" y="{M-8}" text-anchor="middle" fill="#555">{i}</text>')
    for j in range(int(H) + 1):
        svg.append(f'<line x1="{M}" y1="{M+j*S}" x2="{M+W*S}" y2="{M+j*S}" stroke="#eee"/>')
        svg.append(f'<text x="{M-8}" y="{M+j*S+4}" text-anchor="end" fill="#555">{j}</text>')
    svg.append(f'<rect x="{M}" y="{M}" width="{W*S}" height="{H*S}" fill="none" stroke="#222" stroke-width="3"/>')

    # courtyards (dashed purple)
    for f in b.GetFootprints():
        c = f.GetBoundingBox(False)
        svg.append(f'<rect x="{X(c.GetLeft()):.1f}" y="{Y(c.GetTop()):.1f}" width="{c.GetWidth()/1e6*S:.1f}" '
                   f'height="{c.GetHeight()/1e6*S:.1f}" fill="none" stroke="#a0c" stroke-width="0.6" stroke-dasharray="3,3"/>')
    # pads
    for f in b.GetFootprints():
        for p in f.Pads():
            r = p.GetBoundingBox()
            c = col.get(p.GetNetname(), "#bbb")
            if p.GetShape() in (pcbnew.PAD_SHAPE_CIRCLE, pcbnew.PAD_SHAPE_OVAL):
                svg.append(f'<ellipse cx="{X(r.GetCenter().x):.1f}" cy="{Y(r.GetCenter().y):.1f}" rx="{r.GetWidth()/2e6*S:.1f}" '
                           f'ry="{r.GetHeight()/2e6*S:.1f}" fill="{c}" fill-opacity="0.55" stroke="{c}"/>')
            else:
                svg.append(f'<rect x="{X(r.GetLeft()):.1f}" y="{Y(r.GetTop()):.1f}" width="{r.GetWidth()/1e6*S:.1f}" '
                           f'height="{r.GetHeight()/1e6*S:.1f}" fill="{c}" fill-opacity="0.55" stroke="{c}"/>')
    # tracks: B.Cu first (lighter, dashed), then F.Cu
    for layer, op, dash in ((pcbnew.B_Cu, 0.55, ' stroke-dasharray="10,5"'), (pcbnew.F_Cu, 0.85, '')):
        for t in b.GetTracks():
            if t.GetClass() == "PCB_TRACK" and t.GetLayer() == layer:
                svg.append(f'<line x1="{X(t.GetStart().x):.1f}" y1="{Y(t.GetStart().y):.1f}" x2="{X(t.GetEnd().x):.1f}" '
                           f'y2="{Y(t.GetEnd().y):.1f}" stroke="{col.get(t.GetNetname(), "#999")}" stroke-width="{t.GetWidth()/1e6*S:.1f}" '
                           f'stroke-linecap="round" stroke-opacity="{op}"{dash}/>')
    # vias
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            r = t.GetWidth(pcbnew.F_Cu) / 2e6 * S
            svg.append(f'<circle cx="{X(t.GetPosition().x):.1f}" cy="{Y(t.GetPosition().y):.1f}" r="{r:.1f}" fill="#fff" '
                       f'stroke="{col.get(t.GetNetname(), "#333")}" stroke-width="2"/>')
    # refdes
    for f in b.GetFootprints():
        c = f.GetBoundingBox(False)
        svg.append(f'<text x="{X(c.GetCenter().x):.1f}" y="{Y(c.GetCenter().y):.1f}" text-anchor="middle" font-weight="600">{f.GetReference()}</text>')
    # legend (right), mark nets with unconnected via/track count
    lx = M * 2 + W * S - M + 20
    for i, n in enumerate(nets):
        yy = M + 18 * i
        svg.append(f'<rect x="{lx}" y="{yy-10}" width="12" height="12" fill="{col[n]}"/>')
        svg.append(f'<text x="{lx+18}" y="{yy}" fill="#444">/{n}</text>')
    svg.append(f'<text x="{lx}" y="{M+18*len(nets)+18}" fill="#777">F.Cu: dac | B.Cu: net dut</text>')
    svg.append('</svg>')
    open(out, "w", encoding="utf-8").write("\n".join(svg))
    print("svg", out)


main()
