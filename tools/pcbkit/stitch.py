"""GND pour on F.Cu + purposeful GND stitching vias (owner rules, singleRgbCtrl 2026-11-18):
  1. fence   : along `fence_nets` (power, USB pair) both sides, ~fence_pitch mm
  2. island  : every F.Cu pour island >= island_min mm^2 without a GND via / GND THT pad gets one via (may sit under a body)
  3. coverage: until every pour point is <= cover_r mm from a GND via (outside bodies)
Never on pads (>= pad_gap from ANY pad), never in another net's zone, >= 0.65 mm from the edge, >= 1.0 mm between GND vias.

    python -m pcbkit stitch board.kicad_pcb out.kicad_pcb --fence /+5V,/USB_DP,/USB_DM
"""
import math
import numpy as np, cv2
from .board import Board, F, B
from .check import items_of
from .writer import write, zone_text, copper_text, insert_before_zones, drop_fills


def stitch(b, net='/GND', fence_nets=('/+5V',), fence_pitch=2.5, cover_r=3.5, island_min=0.5, res=0.025,
           zone_cl=0.25, min_thickness=0.2, via_size=0.6, via_drill=0.3, pad_gap=0.25, cu_gap=0.2, edge_gap=0.65,
           via_pitch=1.0, body_margin=0.15, add_top_zone=True):
    X0, Y0, X1, Y1 = b.outline
    W, H = int(round((X1 - X0) / res)) + 1, int(round((Y1 - Y0) / res)) + 1
    px = lambda x, y: (int(round((x - X0) / res)), int(round((y - Y0) / res)))
    pl = lambda v: int(round(v / res))
    VR = via_size / 2
    items, holes = items_of(b)
    def draw(img, sh, grow, val=255):
        if sh[0] == 'cap':
            r = sh[3] + grow
            cv2.line(img, px(*sh[1]), px(*sh[2]), val, max(1, 2 * pl(r)))
            cv2.circle(img, px(*sh[1]), pl(r), val, -1); cv2.circle(img, px(*sh[2]), pl(r), val, -1)
        else:
            _, x0, y0, x1, y1, r = sh; r += grow
            cv2.rectangle(img, px(x0, y0 - r), px(x1, y1 + r), val, -1); cv2.rectangle(img, px(x0 - r, y0), px(x1 + r, y1), val, -1)
            for cx in (x0, x1):
                for cy in (y0, y1):
                    cv2.circle(img, px(cx, cy), pl(r), val, -1)
    Fi = [it for it in items if it['layer'] == F]
    obst = np.zeros((H, W), np.uint8)
    for it in Fi:
        if it['net'] != net:
            draw(obst, it['sh'], zone_cl)
    for h in holes:
        if h['net'] != net:
            draw(obst, h['sh'], zone_cl)
    other_zones = [z for z in b.zones if z['net'] != net and F in z['layers'] and z['pts']]
    for z in other_zones:
        pts = np.array([px(*q) for q in z['pts']], np.int32)
        cv2.fillPoly(obst, [pts], 255); cv2.polylines(obst, [pts], True, 255, max(1, 2 * pl(zone_cl)))
    e = pl(0.3); obst[:e, :] = 255; obst[-e:, :] = 255; obst[:, :e] = 255; obst[:, -e:] = 255
    pour = (obst == 0).astype(np.uint8)
    for it in Fi:
        if it['net'] == net:
            draw(pour, it['sh'], 0, 1)
    k = 2 * pl(min_thickness / 2) + 1
    pour = cv2.morphologyEx(pour, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    forbid = np.zeros((H, W), np.uint8)
    for it in items:
        if it['kind'] == 'pad':
            draw(forbid, it['sh'], VR + pad_gap)
        elif it['net'] != net:
            draw(forbid, it['sh'], VR + cu_gap)
    for h in holes:
        draw(forbid, h['sh'], via_drill / 2 + 0.25)
    forbid |= (cv2.erode(pour, np.ones((3, 3), np.uint8)) == 0).astype(np.uint8) * 255
    eb = pl(edge_gap); forbid[:eb, :] = 255; forbid[-eb:, :] = 255; forbid[:, :eb] = 255; forbid[:, -eb:] = 255
    body = np.zeros((H, W), np.uint8)
    for r in b.fp:
        x0, y0, x1, y1 = b.body(r)
        cv2.rectangle(body, px(x0 - body_margin, y0 - body_margin), px(x1 + body_margin, y1 + body_margin), 255, -1)
    vias = [it['c'] for it in items if it['kind'] == 'via' and it['net'] == net and it['layer'] == F]
    for v in vias:
        cv2.circle(forbid, px(*v), pl(via_pitch), 255, -1)
    added = {'fence': [], 'island': [], 'cover': []}
    def place(p, kind):
        vias.append(p); added[kind].append(p); cv2.circle(forbid, px(*p), pl(via_pitch), 255, -1)
    def ok(x, y, allow_body=False):
        i, j = px(x, y)
        return 0 <= j < H and 0 <= i < W and not forbid[j, i] and (allow_body or not body[j, i])
    for it in Fi:                                            # 1) fence
        if it['kind'] != 'seg' or it['net'] not in fence_nets:
            continue
        (ax, ay), (bx, by) = it['a'], it['b']; L = math.dist(it['a'], it['b'])
        if L < 1.5:
            continue
        ux, uy = (bx - ax) / L, (by - ay) / L; nx, ny = -uy, ux; w2 = it['sh'][3]
        for kk in range(int(L // fence_pitch) + 1):
            f = min(1, (kk + 0.5) * fence_pitch / L); cx, cy = ax + ux * L * f, ay + uy * L * f
            for s in (1, -1):
                for off in np.arange(w2 + 0.5, w2 + 1.3, 0.1):
                    p = (round(cx + s * nx * off, 3), round(cy + s * ny * off, 3))
                    if ok(*p):
                        place(p, 'fence'); break
    n, lab = cv2.connectedComponents(pour, connectivity=8)    # 2) island rescue
    anchored = {lab[px(*v)[1], px(*v)[0]] for v in vias}
    for p in b.pads():
        if p['net'] == net and p['type'] == 'thru_hole':
            i, j = px(p['ax'], p['ay']); anchored.add(lab[j, i])
    skipped = []
    for L_ in range(1, n):
        if L_ in anchored:
            continue
        m = lab == L_; area = m.sum() * res * res
        if area < island_min:
            continue
        cand = m & (forbid == 0)
        if not cand.any():
            ys, xs = np.nonzero(m)
            skipped.append((round(area, 2), (round(X0 + xs.min() * res, 2), round(Y0 + ys.min() * res, 2), round(X0 + xs.max() * res, 2), round(Y0 + ys.max() * res, 2))))
            continue
        dt = cv2.distanceTransform(cand.astype(np.uint8), cv2.DIST_L2, 5)
        j, i = np.unravel_index(np.argmax(dt), dt.shape)
        place((round(X0 + i * res, 3), round(Y0 + j * res, 3)), 'island')
    while True:                                              # 3) coverage
        src = np.full((H, W), 255, np.uint8)
        for v in vias:
            cv2.circle(src, px(*v), 2, 0, -1)
        d = cv2.distanceTransform(src, cv2.DIST_L2, 5) * res
        d[pour == 0] = 0
        cand = (forbid == 0) & (body == 0) & (d > cover_r)
        if not cand.any():
            break
        j, i = np.unravel_index(np.argmax(np.where(cand, d, 0)), d.shape)
        place((round(X0 + i * res, 3), round(Y0 + j * res, 3)), 'cover')
    new = added['fence'] + added['island'] + added['cover']
    zone = ''
    if add_top_zone and not any(z['net'] == net and F in z['layers'] for z in b.zones):
        i = 0.275
        zone = zone_text(net, F, [(X0 + i, Y0 + i), (X1 - i, Y0 + i), (X1 - i, Y1 - i), (X0 + i, Y1 - i)], name='GND_TOP',
                         priority=0, clearance=zone_cl, min_thickness=min_thickness)
    return dict(new=new, counts={k: len(v) for k, v in added.items()}, skipped_islands=skipped, zone_text=zone,
                vias=[dict(c=p, net=net, size=via_size, drill=via_drill) for p in new])


def apply(path, out, **kw):
    """Add stitching vias (+ GND_TOP zone if missing) to an existing board without touching anything else."""
    b = Board(path); b.keep_existing_copper()
    r = stitch(b, **kw)
    txt = insert_before_zones(b.txt, copper_text([], r['vias']) + r['zone_text'])
    open(out, 'w', encoding='utf-8', newline='').write(drop_fills(txt).replace('\n', b.nl))
    return r
