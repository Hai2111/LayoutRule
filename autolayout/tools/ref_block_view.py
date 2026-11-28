"""ref_block_view.py - ANH DOI CHIEU khoi USB-C: moi board (ref + board cua ta) ve trong CUNG KHUNG cua connector
(connector o duoi, huong thoat day len), chi ve khoi lien quan: linh kien noi toi net cua connector (tru GND) va tang ke tiep.
  KP ref_block_view.py OUT.png BOARD[:CONNREF] [BOARD[:CONNREF] ...]
Nhan vai tro theo KET NOI (khong theo ten): CC_R, ESD, TVS, C_VBUS, LDO, R_D, HDR, IC. In bang vai tro + vi tri tuong doi ra stdout.
"""
import math, os, sys
import pcbnew
from PIL import Image, ImageDraw, ImageFont

S, W, H = 34, 30.0, 30.0         # px/mm, khung mm (rong, cao) quanh connector
PAL = {"VBUS": "#ff6b6b", "CC": "#ffb000", "DP": "#4aa3ff", "DN": "#2ec27e", "OTHER": "#b57bff", "GND": "#666670"}


def kind(n):
    u = n.upper().lstrip("/")
    if "GND" in u: return "GND"
    if "VBUS" in u or u in ("+5V", "5V", "VUSB", "USB_5V", "VIN"): return "VBUS"
    if "CC" in u: return "CC"
    if any(k in u for k in ("D+", "DP", "_P", "USB_P")) and "PWM" not in u: return "DP"
    if any(k in u for k in ("D-", "DN", "DM", "_N", "USB_N")): return "DN"
    return "OTHER"


def find_conn(b, ref):
    for f in b.GetFootprints():
        nums = {p.GetNumber() for p in f.Pads()}
        if (ref and f.GetReference() == ref) or (not ref and {"A5", "B5"} <= nums):
            return f


def view(path, ref):
    b = pcbnew.LoadBoard(path)
    c = find_conn(b, ref)
    if c is None:
        return None, []
    sig = [p for p in c.Pads() if p.GetNumber()[:1] in "AB" and p.GetNetname()]
    cx = sum(p.GetPosition().x for p in sig) / len(sig) / 1e6; cy = sum(p.GetPosition().y for p in sig) / len(sig) / 1e6
    # huong thoat = tu tam than connector ve phia hang pad
    bc = c.GetPosition(); ex, ey = cx - bc.x / 1e6, cy - bc.y / 1e6
    L = math.hypot(ex, ey) or 1; ux, uy = ex / L, ey / L            # vector "len" trong toa do board
    rx, ry = -uy, ux                                                  # vector "phai"
    if any(p.GetNumber() == "A5" for p in sig):                        # giu CC1(A5) ben trai cho moi board
        a5 = next(p for p in sig if p.GetNumber() == "A5").GetPosition()
        if ((a5.x / 1e6 - cx) * rx + (a5.y / 1e6 - cy) * ry) > 0: rx, ry = -rx, -ry
    T = lambda x, y: ((x - cx) * rx + (y - cy) * ry, (x - cx) * ux + (y - cy) * uy)   # (phai, len) mm
    P = lambda x, y: (W / 2 * S + T(x, y)[0] * S, (H - 4) * S - T(x, y)[1] * S)
    cnets = {p.GetNetname() for p in c.Pads() if p.GetNetname() and kind(p.GetNetname()) != "GND"}
    parts = {f.GetReference(): f for f in b.GetFootprints() if f is not c and any(p.GetNetname() in cnets for p in f.Pads())}
    nets2 = set(cnets) | {p.GetNetname() for f in parts.values() for p in f.Pads() if p.GetNetname() and kind(p.GetNetname()) != "GND"}
    more = {f.GetReference(): f for f in b.GetFootprints() if f is not c and f.GetReference() not in parts
            and any(p.GetNetname() in nets2 for p in f.Pads()) and abs(T(f.GetPosition().x / 1e6, f.GetPosition().y / 1e6)[0]) < W / 2
            and -4 < T(f.GetPosition().x / 1e6, f.GetPosition().y / 1e6)[1] < H - 4}
    def role(f):
        ks = {kind(p.GetNetname()) for p in f.Pads() if p.GetNetname()}; r = f.GetReference(); n = len(list(f.Pads()))
        if r.startswith("R") and "CC" in ks: return "CC_R"
        if r.startswith("R") and ks & {"DP", "DN"}: return "R_D"
        if (r.startswith(("U", "D")) and {"DP", "DN"} <= ks) or (r.startswith("U") and ks & {"DP", "DN"} and n <= 6): return "ESD"
        if r.startswith("D") and ks <= {"VBUS", "GND"}: return "TVS"
        if r.startswith("C") and "VBUS" in ks: return "C_VBUS"
        if r.startswith("U") and "VBUS" in ks: return "LDO/IC_PWR"
        if r.startswith(("J", "P", "CN")): return "HDR"
        if r.startswith("U"): return "IC"
        return r.rstrip("0123456789")
    im = Image.new("RGB", (int(W * S), int(H * S) + 26), "#15151b"); d = ImageDraw.Draw(im)
    f12 = ImageFont.truetype("arial.ttf", 13); f16 = ImageFont.truetype("arial.ttf", 15)
    keep = set(nets2)
    for t in b.GetTracks():
        n = t.GetNetname()
        if n not in keep: continue
        col = PAL[kind(n)]
        if t.GetClass() == "PCB_VIA":
            q = t.GetPosition(); a = P(q.x / 1e6, q.y / 1e6); r = 0.3 * S
            d.ellipse([a[0] - r, a[1] - r, a[0] + r, a[1] + r], outline=col, fill="#ffffff", width=2); continue
        a = P(t.GetStart().x / 1e6, t.GetStart().y / 1e6); z = P(t.GetEnd().x / 1e6, t.GetEnd().y / 1e6)
        w = max(2, int(t.GetWidth() / 1e6 * S))
        if t.GetLayer() == pcbnew.F_Cu: d.line([a, z], fill=col, width=w)
        else:
            n_ = max(1, int(math.dist(a, z) / 8))
            for i in range(n_):
                u0, u1 = i / n_, (i + 0.5) / n_
                d.line([(a[0] + (z[0] - a[0]) * u0, a[1] + (z[1] - a[1]) * u0), (a[0] + (z[0] - a[0]) * u1, a[1] + (z[1] - a[1]) * u1)], fill=col, width=w)
    rows = []
    for f in [c] + list(parts.values()) + list(more.values()):
        for p in f.Pads():
            bb = p.GetBoundingBox(); pts = [P(bb.GetLeft() / 1e6, bb.GetTop() / 1e6), P(bb.GetRight() / 1e6, bb.GetBottom() / 1e6)]
            xs, ys = sorted([pts[0][0], pts[1][0]]), sorted([pts[0][1], pts[1][1]])
            d.rectangle([xs[0], ys[0], xs[1], ys[1]], outline=PAL[kind(p.GetNetname())] if p.GetNetname() else "#444", width=2)
        if f is c: continue
        q = f.GetPosition(); a = P(q.x / 1e6, q.y / 1e6); rl = role(f) if f.GetReference() in parts else role(f) + "*"
        d.text(a, f"{f.GetReference()} {rl}", font=f12, fill="#ffffff", anchor="mm", stroke_width=2, stroke_fill="#000")
        tx, ty = T(q.x / 1e6, q.y / 1e6); rows.append((rl, f.GetReference(), str(f.GetValue())[:14], round(tx, 1), round(ty, 1)))
    d.text((4, 4), f"{os.path.basename(path)}  [{c.GetReference()}]  (len = huong thoat)", font=f16, fill="#ffff88")
    return im, sorted(rows)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    out = sys.argv[1]; ims = []
    for arg in sys.argv[2:]:
        path, _, ref = arg.partition(":") if not (len(arg) > 2 and arg[1] == ":" and arg.count(":") == 1) else (arg, "", "")
        if len(arg) > 2 and arg[1] == ":" and arg.count(":") == 2:
            i = arg.rfind(":"); path, ref = arg[:i], arg[i + 1:]
        im, rows = view(path, ref or None)
        print("==", os.path.basename(path))
        for r in rows: print("  ", r)
        if im: ims.append(im)
    cols = min(3, len(ims)); rws = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * ims[0].width + (cols - 1) * 12, rws * ims[0].height + (rws - 1) * 12), "#ffffff")
    for k, im in enumerate(ims): sheet.paste(im, ((k % cols) * (im.width + 12), (k // cols) * (im.height + 12)))
    sheet.save(out); print(out, sheet.size)


main()
