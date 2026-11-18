"""Independent geometric checks (NOT a replacement for KiCad DRC): clearance, hole, edge, connectivity,
dangling ends, K1 body keep-out, courtyard overlap. Zones are ignored: nets joined only by a zone show as split.

    python -m pcbkit check board.kicad_pcb --exempt J1,/USB_DM
"""
import itertools, math
from .sexpr import parse, kids, kid
from .board import Board, F, B


# ---------- geometry ----------
def pt_seg(p, a, b):
    ax, ay = a; bx, by = b; px, py = p; dx, dy = bx - ax, by - ay; L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _cross(a, b, c, d):
    def o(p, q, r): return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def seg_seg(a, b, c, d):
    if _cross(a, b, c, d):
        return 0.0
    return min(pt_seg(a, c, d), pt_seg(b, c, d), pt_seg(c, a, b), pt_seg(d, a, b))


def seg_rect(a, b, x0, y0, x1, y1):
    inside = lambda p: x0 <= p[0] <= x1 and y0 <= p[1] <= y1
    if inside(a) or inside(b):
        return 0.0
    c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return min(seg_seg(a, b, c[i], c[(i + 1) % 4]) for i in range(4))


def sdist(s, t):
    """Edge-to-edge distance. Shapes: ('cap', a, b, r) capsule/circle, ('rr', x0, y0, x1, y1, r) rounded rect."""
    if s[0] == 'cap' and t[0] == 'cap':
        return seg_seg(s[1], s[2], t[1], t[2]) - s[3] - t[3]
    if s[0] == 'rr' and t[0] == 'cap':
        s, t = t, s
    if s[0] == 'cap' and t[0] == 'rr':
        return seg_rect(s[1], s[2], *t[1:5]) - s[3] - t[5]
    dx = max(t[1] - s[3], s[1] - t[3], 0); dy = max(t[2] - s[4], s[2] - t[4], 0)
    return math.hypot(dx, dy) - s[5] - t[5]


def pad_shape(p):
    w, h = p['aw'], p['ah']
    rr = p['rr'] * min(w, h) if p['shape'] == 'roundrect' else (min(w, h) / 2 if p['shape'] in ('circle', 'oval') else 0)
    return ('rr', p['ax'] - w / 2 + rr, p['ay'] - h / 2 + rr, p['ax'] + w / 2 - rr, p['ay'] + h / 2 - rr, rr)


def hole_shape(p, b):
    kind, dw, dh = p['drill']
    if kind == 'oval' and round(p['la'] + b.fp[p['ref']]['pos'][2]) % 180 == 90:
        dw, dh = dh, dw
    r = min(dw, dh) / 2
    return ('cap', (p['ax'] - (dw / 2 - r), p['ay'] - (dh / 2 - r)), (p['ax'] + (dw / 2 - r), p['ay'] + (dh / 2 - r)), r)


# ---------- K1 keep-out regions ----------
def keepouts(b, extra=None):
    """[(ref, (x0,y0,x1,y1), inflate)] where F.Cu tracks may not go.
    inflate=True: the whole track (incl. width) must stay out; False: only between-pin gaps.
      * 2-pad parts (R/C/L/D/F/FB...): the gap between the two pads (any net, also the part's own net)
      * transistors / SOT / diodes with >2 pads (ref Q*, D*, or lib contains SOT/TO-): F.Fab body
      * connectors J*/P*: gaps between adjacent pins; with metal shell (THT shell + SMD pins, e.g. USB-C): shell area
      * ICs (U*): none (channel between pin rows is a grey zone, route cost only)
    `extra`: {ref: [(x0,y0,x1,y1), ...]} project-specific additions."""
    out = []
    allp = b.pads()
    for ref, f in b.fp.items():
        ps = [p for p in allp if p['ref'] == ref and p['type'] != 'np_thru_hole']
        lib = f['lib'].upper()
        if len(ps) == 2 and ref[0] not in 'JPU':
            a, c = ps
            if abs(a['ax'] - c['ax']) > abs(a['ay'] - c['ay']):
                lo, hi = sorted(ps, key=lambda p: p['ax'])
                out.append((ref, (lo['ax'] + lo['aw'] / 2, min(p['ay'] - p['ah'] / 2 for p in ps),
                                  hi['ax'] - hi['aw'] / 2, max(p['ay'] + p['ah'] / 2 for p in ps)), True))
            else:
                lo, hi = sorted(ps, key=lambda p: p['ay'])
                out.append((ref, (min(p['ax'] - p['aw'] / 2 for p in ps), lo['ay'] + lo['ah'] / 2,
                                  max(p['ax'] + p['aw'] / 2 for p in ps), hi['ay'] - hi['ah'] / 2), True))
        elif ref[0] == 'Q' or 'SOT' in lib or 'TO_' in lib or (ref[0] == 'D' and len(ps) > 2):
            out.append((ref, b.body(ref), True))
        elif ref[0] in 'JP':
            smd = [p for p in ps if p['type'] == 'smd']; tht = [p for p in ps if p['type'] == 'thru_hole']
            if smd and tht:   # shell connector: area between shell legs, from body edge to the SMD pin row
                X0, Y0, X1, Y1 = b.body(ref)
                sx0, sx1 = min(p['ax'] - p['aw'] / 2 for p in tht), max(p['ax'] + p['aw'] / 2 for p in tht)
                ty0, ty1 = min(p['ay'] - p['ah'] / 2 for p in smd), max(p['ay'] + p['ah'] / 2 for p in smd)
                if (ty0 + ty1) / 2 > (Y0 + Y1) / 2:
                    out.append((ref, (sx0, Y0, sx1, ty0), True))
                else:
                    out.append((ref, (sx0, ty1, sx1, Y1), True))
            uniq = {}
            for p in ps:                               # stacked pads (USB-C A12/B1, A9/B4) count once
                if p['type'] != 'np_thru_hole' and not (smd and tht and p['type'] == 'thru_hole'):
                    uniq.setdefault((round(p['ax'], 2), round(p['ay'], 2)), p)
            q = [uniq[k] for k in sorted(uniq)]
            for a, c in zip(q, q[1:]):
                if abs(a['ay'] - c['ay']) < 0.1:      # same row: horizontal gap
                    r = (a['ax'] + a['aw'] / 2, max(a['ay'] - a['ah'] / 2, c['ay'] - c['ah'] / 2),
                         c['ax'] - c['aw'] / 2, min(a['ay'] + a['ah'] / 2, c['ay'] + c['ah'] / 2))
                elif abs(a['ax'] - c['ax']) < 0.1:    # same column: vertical gap
                    r = (max(a['ax'] - a['aw'] / 2, c['ax'] - c['aw'] / 2), a['ay'] + a['ah'] / 2,
                         min(a['ax'] + a['aw'] / 2, c['ax'] + c['aw'] / 2), c['ay'] - c['ah'] / 2)
                else:
                    continue
                if r[2] > r[0] + 1e-6 and r[3] > r[1] + 1e-6:
                    out.append((ref, r, False))
    for ref, rects in (extra or {}).items():
        out += [(ref, r, True) for r in rects]
    return out


# ---------- item list ----------
def items_of(b):
    items, holes = [], []
    for p in b.pads():
        sh = pad_shape(p)
        L = [F, B] if p['type'] == 'thru_hole' else ([F] if (p['type'] == 'smd' and 'F.Cu' in p['layers']) else ([B] if p['type'] == 'smd' else []))
        net = p['net'] or '<none:%s>' % p['name']
        for l in L:
            items.append(dict(kind='pad', name=p['name'], net=net, layer=l, sh=sh, ref=p['ref']))
        if p['drill']:
            holes.append(dict(name=p['name'] + '.hole', net=net, sh=hole_shape(p, b), npth=p['type'] == 'np_thru_hole'))
    for g in b.segs:
        items.append(dict(kind='seg', name='seg %s (%.3f,%.3f)-(%.3f,%.3f) w%.2f' % (g['layer'], g['a'][0], g['a'][1], g['b'][0], g['b'][1], g['w']),
                          net=g['net'], layer=g['layer'], sh=('cap', g['a'], g['b'], g['w'] / 2), a=g['a'], b=g['b']))
    for v in b.vias:
        nm = 'via (%.3f,%.3f)' % v['c']
        for l in (F, B):
            items.append(dict(kind='via', name=nm, net=v['net'], layer=l, sh=('cap', v['c'], v['c'], v.get('size', 0.6) / 2), c=v['c']))
        holes.append(dict(name=nm + '.hole', net=v['net'], sh=('cap', v['c'], v['c'], v.get('drill', 0.3) / 2), npth=False))
    return items, holes


def check(b, exempt=(), hole_cl=0.25, edge_cl=0.3, plane_nets=('/GND',), extra_keepouts=None, verbose=True):
    """b: Board (with b.segs/b.vias filled) or a path. Returns dict of lists."""
    if isinstance(b, str):
        b = Board(b); b.keep_existing_copper()
    items, holes = items_of(b)
    V = []
    for a, c in itertools.combinations(items, 2):
        if a['layer'] != c['layer'] or a['net'] == c['net']:
            continue
        need = max(b.clearance(a['net']), b.clearance(c['net']))
        d = sdist(a['sh'], c['sh'])
        if d < need - 1e-4:
            V.append(('clearance %.3f<%.2f' % (d, need), a['layer'], '%s [%s]' % (a['name'], a['net']), '%s [%s]' % (c['name'], c['net'])))
    for h in holes:
        for a in items:
            if a['net'] == h['net'] or a['name'] + '.hole' == h['name']:
                continue
            d = sdist(h['sh'], a['sh'])
            if d < hole_cl - 1e-4:
                V.append(('hole_clearance %.3f<%.2f' % (d, hole_cl), a['layer'], h['name'], '%s [%s]' % (a['name'], a['net'])))
    for h, g in itertools.combinations(holes, 2):
        if h['name'] != g['name'] and h['name'].split('.hole')[0] != g['name'].split('.hole')[0]:
            d = sdist(h['sh'], g['sh'])
            if d < hole_cl - 1e-4:
                V.append(('hole_to_hole %.3f' % d, '', h['name'], g['name']))
    X0, Y0, X1, Y1 = b.outline
    for a in items:
        if a['kind'] == 'pad':
            continue
        s = a['sh']; r = s[3]
        e = min(min(s[1][0], s[2][0]) - r - X0, min(s[1][1], s[2][1]) - r - Y0, X1 - max(s[1][0], s[2][0]) - r, Y1 - max(s[1][1], s[2][1]) - r)
        if e < edge_cl - 1e-4:
            V.append(('edge %.3f<%.2f' % (e, edge_cl), a['layer'], a['name'], ''))
    # connectivity (union-find); copper planes join their vias / THT pads
    par = list(range(len(items)))
    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]; i = par[i]
        return i
    def u(i, j): par[f(i)] = f(j)
    first = {}
    for i, a in enumerate(items):
        if a['kind'] in ('via', 'pad'):
            k = (a['kind'], a['name'])
            if k in first:
                u(i, first[k])
            first[k] = i
    for net in plane_nets:
        anchor = None
        for i, a in enumerate(items):
            if a['net'] == net and a['layer'] == B and a['kind'] in ('via', 'pad'):
                anchor = i if anchor is None else anchor; u(i, anchor)
    for i, j in itertools.combinations(range(len(items)), 2):
        a, c = items[i], items[j]
        if a['layer'] == c['layer'] and a['net'] == c['net'] and sdist(a['sh'], c['sh']) <= 1e-6:
            u(i, j)
    nets = {}
    for i, a in enumerate(items):
        if a['kind'] == 'pad' and not a['net'].startswith(('<none', 'unconnected')):
            nets.setdefault(a['net'], {}).setdefault(f(i), set()).add(a['name'])
    U = [(n, [sorted(v) for v in g.values()]) for n, g in nets.items() if len(g) > 1]
    D = []
    for i, a in enumerate(items):
        if a['kind'] == 'seg':
            for e in (a['a'], a['b']):
                if not any(j != i and c['layer'] == a['layer'] and c['net'] == a['net'] and sdist(('cap', e, e, 0.0), c['sh']) <= 1e-6
                           for j, c in enumerate(items)):
                    D.append((a['name'], e))
    # K1
    ex = {tuple(x) for x in exempt}
    K = []
    for ref, (x0, y0, x1, y1), infl in keepouts(b, extra_keepouts):
        own = {p['net'] for p in b.fp[ref]['pads']}
        for a in items:
            if a['kind'] == 'seg' and a['layer'] == F and (ref, a['net']) not in ex:
                d = sdist(a['sh'], ('rr', x0, y0, x1, y1, 0.0))
                lim = -a['sh'][3] + 1e-3 if (a['net'] in own or not infl) else -1e-3
                if d < lim:
                    K.append((ref, a['name'], a['net']))
    C = b.place_check(skip_edge=[r for r in b.fp if r[0] in 'JP'])
    res = dict(violations=V, unconnected=U, dangling=D, under_body=K, courtyard=C)
    if verbose:
        if not b.pro:
            print('WARNING: no .kicad_pro next to the board -> netclass clearances unknown, using Default 0.2 mm')
        print('clearance/hole/edge: %d | unconnected nets: %d | dangling: %d | under body (K1): %d | courtyard: %d'
              % (len(V), len(U), len(D), len(K), len(C)))
        for k, lst in res.items():
            for x in lst[:40]:
                print('  %-12s %s' % (k, x))
    return res
