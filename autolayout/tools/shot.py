"""shot.py OUT.png BOARD [BOARD...] - anh PNG de NHIN (tac tu quan sat).
F.Cu = net mau dac, B.Cu = net dut, via tron trang, pad vien mau net, GND xam. Zone F.Cu ve nen xanh toi (mat dong GND).
env: S=px/mm (30) | COLS | CROP=x0,y0,x1,y1 (mm, toa do board) | LABELS=1 ghi ten net canh doan dai nhat cua moi net.
"""
import sys, os, math
import pcbnew
from PIL import Image, ImageDraw, ImageFont

PAL = ["#4aa3ff", "#ff9f1c", "#2ec27e", "#e5484d", "#b57bff", "#d9a441", "#ff77c8", "#c9d11f", "#19c9d6", "#8fb8ff", "#7ee08a", "#ffb3a1"]
GAP = 20


def box(o):
    r = o.GetBoundingBox()
    return r.GetLeft() / 1e6, r.GetTop() / 1e6, r.GetRight() / 1e6, r.GetBottom() / 1e6


def draw(path, S, crop, labels):
    b = pcbnew.LoadBoard(path)
    e = b.GetBoardEdgesBoundingBox()
    if crop:
        x0, y0, x1, y1 = crop
    else:
        x0, y0, x1, y1 = e.GetLeft() / 1e6, e.GetTop() / 1e6, e.GetRight() / 1e6, e.GetBottom() / 1e6
    W, H = x1 - x0, y1 - y0
    im = Image.new("RGB", (int(W * S) + 2, int(H * S) + 30), "#14141a")
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype("arial.ttf", max(11, int(S * 0.45)))
    fs = ImageFont.truetype("arial.ttf", max(10, int(S * 0.3)))
    P = lambda x, y: ((x - x0) * S, (y - y0) * S + 28)
    if crop:   # luoi 1 mm de doc toa do
        for i in range(int(x0), int(x1) + 1):
            d.line([P(i, y0), P(i, y1)], fill="#24242c"); d.text(P(i, y0), str(i), font=fs, fill="#777")
        for j in range(int(y0), int(y1) + 1):
            d.line([P(x0, j), P(x1, j)], fill="#24242c"); d.text(P(x0, j), str(j), font=fs, fill="#777")
    names = sorted({p.GetNetname() for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname()})
    col = {n: PAL[i % len(PAL)] for i, n in enumerate(names)}
    for n in names:
        if "GND" in n.upper(): col[n] = "#77777f"
    # zone F.Cu (GND solid) ve mo phia duoi de thay pad GND noi vao mat dong (owner hoi "pour zone cho net nao")
    try:
        b.BuildConnectivity()     # khong co buoc nay, filler coi moi dao la co lap va xoa (khac voi DRC)
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        for z in b.Zones():
            if not z.IsOnLayer(pcbnew.F_Cu): continue
            ps = pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(pcbnew.F_Cu))
            try: ps.Unfracture()          # fill luu o dang 'fractured' (khe noi lo) -> tach lai vien ngoai + lo moi ve dung
            except TypeError: ps.Unfracture(pcbnew.SHAPE_POLY_SET.PM_FAST)
            from PIL import ImageChops
            tot = Image.new("L", im.size, 0)
            for i in range(ps.OutlineCount()):      # moi manh dong: to vien ngoai roi khoet lo CUA CHINH NO, gop bang OR
                mk = Image.new("L", im.size, 0); dm = ImageDraw.Draw(mk)
                o = ps.Outline(i); pts = [P(o.CPoint(k).x / 1e6, o.CPoint(k).y / 1e6) for k in range(o.PointCount())]
                if len(pts) > 2: dm.polygon(pts, fill=255)
                for j in range(ps.HoleCount(i)):
                    h = ps.Hole(i, j); hp = [P(h.CPoint(k).x / 1e6, h.CPoint(k).y / 1e6) for k in range(h.PointCount())]
                    if len(hp) > 2: dm.polygon(hp, fill=0)
                tot = ImageChops.lighter(tot, mk)
            im.paste("#1f3326", (0, 0), tot)
    except Exception as ex:
        print("khong ve duoc zone:", ex)
    for fp in b.GetFootprints():
        for p in fp.Pads():
            l, t, r, bt = box(p)
            c = col.get(p.GetNetname(), "#555560")
            fn = d.ellipse if p.GetShape() in (pcbnew.PAD_SHAPE_CIRCLE, pcbnew.PAD_SHAPE_OVAL) else d.rectangle
            fn([P(l, t), P(r, bt)], outline=c, fill=None, width=2)
    tracks = list(b.GetTracks()); longest = {}
    for layer, dashed in ((pcbnew.B_Cu, True), (pcbnew.F_Cu, False)):
        for t in tracks:
            if t.GetClass() != "PCB_TRACK" or t.GetLayer() != layer: continue
            s, en = t.GetStart(), t.GetEnd()
            a, z = P(s.x / 1e6, s.y / 1e6), P(en.x / 1e6, en.y / 1e6)
            w = max(2, int(t.GetWidth() / 1e6 * S))
            c = col.get(t.GetNetname(), "#999999")
            L = math.dist(a, z)
            if L > longest.get(t.GetNetname(), (0,))[0]: longest[t.GetNetname()] = (L, a, z, c)
            if not dashed:
                d.line([a, z], fill=c, width=w)
                for q in (a, z): d.ellipse([q[0] - w / 2, q[1] - w / 2, q[0] + w / 2, q[1] + w / 2], fill=c)
            else:
                n = max(1, int(L / 10))
                for i in range(n):
                    u, v = i / n, (i + 0.55) / n
                    d.line([(a[0] + (z[0] - a[0]) * u, a[1] + (z[1] - a[1]) * u), (a[0] + (z[0] - a[0]) * v, a[1] + (z[1] - a[1]) * v)], fill=c, width=w)
    for t in tracks:
        if t.GetClass() == "PCB_VIA":
            q = t.GetPosition(); c = P(q.x / 1e6, q.y / 1e6); r = t.GetWidth(pcbnew.F_Cu) / 2e6 * S
            d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill="#ffffff", outline=col.get(t.GetNetname(), "#999999"), width=3)
    if os.environ.get("RATS") == "1":      # placement review: courtyard + ratsnest MST (tru GND) de thay cat nhau
        for fp in b.GetFootprints():
            cy = fp.GetCourtyard(pcbnew.F_CrtYd)
            for k in range(cy.OutlineCount()):
                o = cy.Outline(k); pts = [P(o.CPoint(i).x / 1e6, o.CPoint(i).y / 1e6) for i in range(o.PointCount())]
                if len(pts) > 2: d.polygon(pts, outline="#4a4a66")
        nets = {}
        for fp in b.GetFootprints():
            for p in fp.Pads():
                n = p.GetNetname()
                if n and not n.startswith("unconnected") and "GND" not in n.upper():
                    nets.setdefault(n, set()).add((p.GetPosition().x / 1e6, p.GetPosition().y / 1e6))
        for n, pts in nets.items():
            pts = sorted(pts); used = [pts[0]]; rest = pts[1:]
            pw = any(k in n.upper() for k in ("VBUS", "+5V", "3V3", "VDD", "AVDD"))
            while rest:
                dd, i, u = min((math.dist(u, q), i, u) for i, q in enumerate(rest) for u in used)
                d.line([P(*u), P(*rest[i])], fill=col[n], width=1 if pw else 2); used.append(rest.pop(i))
    for fp in b.GetFootprints():
        q = fp.GetPosition()
        d.text(P(q.x / 1e6, q.y / 1e6), fp.GetReference(), font=f, fill="#ffffff", anchor="mm", stroke_width=2, stroke_fill="#000000")
    if labels:
        for n, (L, a, z, c) in longest.items():
            if "GND" in n.upper() or L < 20: continue
            d.text(((a[0] + z[0]) / 2, (a[1] + z[1]) / 2), n.lstrip("/"), font=fs, fill=c, anchor="mm", stroke_width=3, stroke_fill="#000000")
    d.text((4, 4), os.path.basename(path) + (f"  crop {crop}" if crop else ""), font=ImageFont.truetype("arial.ttf", 16), fill="#ffff88")
    return im


out, paths = sys.argv[1], sys.argv[2:]
COLS = int(os.environ.get("COLS", len(paths)))
S = float(os.environ.get("S", 30))
crop = tuple(float(v) for v in os.environ["CROP"].split(",")) if os.environ.get("CROP") else None
ims = [draw(p, S, crop, os.environ.get("LABELS") == "1") for p in paths]
cw, ch = max(i.width for i in ims), max(i.height for i in ims)
rows = (len(ims) + COLS - 1) // COLS
sheet = Image.new("RGB", (COLS * cw + (COLS - 1) * GAP, rows * ch + (rows - 1) * GAP), "#ffffff")
for k, i in enumerate(ims):
    sheet.paste(i, ((k % COLS) * (cw + GAP), (k // COLS) * (ch + GAP)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from ksave import save_image; save_image(sheet, out)
print(out, sheet.size)
