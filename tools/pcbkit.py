"""pcbkit.py — scripted KiCad 10 placement, priority routing and review for 2-layer boards (single file).

Use as a library (from the folder containing this file, or with it on sys.path):
    from pcbkit import Board, F, B, Router, write, check, render
    b = Board('board.kicad_pcb')                 # needs <board>.kicad_pro next to it for netclass clearances
    b.place('U1', 21.9, 17.2, 0)                 # placement in Python
    b.poly([b.P('J1.B6'), (20.25, 8.85), b.P('U2.5')], 0.2, '/USB_DP')   # P1/P2 drawn by hand
    Router(b).route('/UART_TX', 'U1.2', 'U2.3', 0.2, layers=(F, B), allow_via=True)   # A* assist for P3
    write(b, 'candidate.kicad_pcb'); check('candidate.kicad_pcb'); render(b, 'candidate.png')
or from the command line:
    python pcbkit.py check   BOARD [--exempt REF,NET ...]
    python pcbkit.py render  BOARD OUT.png [--region x0,y0,x1,y1] [--title T]
    python pcbkit.py diff    OLD NEW [--offset dx,dy]
    python pcbkit.py stitch  BOARD OUT [--fence /+5V,/USB_DP,/USB_DM] [--cover 3.5] [--pitch 2.5]
    python pcbkit.py center  BOARD OUT [--origin bottom-left|top-left|center]
    python pcbkit.py origin  BOARD OUT X Y
    python pcbkit.py rename  FOLDER OLD NEW [--title T --date D --rev R --comment C]
Requires: pip install numpy opencv-python matplotlib
Reference layout script: singleRgbCtrl/layout_v8.py (rebuilds the V8 candidate exactly).
Sections: SEXPR · BOARD · CHECK · ROUTER · WRITER · STITCH · TRANSFORM · DIFF · RENDER · CLI
"""
import argparse, collections, fnmatch, heapq, itertools, json, math, os, re, sys, uuid
import numpy as np
import cv2



# ====================================================================================================
# SEXPR
# ====================================================================================================
# Minimal KiCad s-expression reader: parse() -> nested lists of strings; kids()/kid() helpers; blocks() for text edits.
_TOK = re.compile(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+')


def parse(text):
    """Parse an s-expression into nested lists. Quoted strings are unquoted."""
    stack, cur = [], []
    for m in _TOK.finditer(text):
        t = m.group()
        if t == '(':
            stack.append(cur); cur = []
        elif t == ')':
            done = cur; cur = stack.pop(); cur.append(done)
        else:
            cur.append(t[1:-1].replace('\\"', '"') if t[0] == '"' else t)
    return cur[0] if cur else []


def kids(node, tag):
    """Direct children lists whose head is `tag`."""
    return [c for c in node if isinstance(c, list) and c and c[0] == tag]


def kid(node, tag):
    """First direct child with head `tag`, or None."""
    for c in node:
        if isinstance(c, list) and c and c[0] == tag:
            return c
    return None


def blocks(text, head):
    """(start, end) spans of every top-level block starting with `head` (e.g. '\\t(segment\\n'), end includes newline."""
    out, i = [], 0
    while True:
        i = text.find(head, i)
        if i < 0:
            return out
        d, j = 0, i + head.index('(')
        while True:
            c = text[j]
            if c == '"':
                j = text.index('"', j + 1)
                while text[j - 1] == '\\':
                    j = text.index('"', j + 1)
            elif c == '(':
                d += 1
            elif c == ')':
                d -= 1
                if d == 0:
                    break
            j += 1
        end = j + 1
        if text[end:end + 1] == '\n':
            end += 1
        out.append((i, end)); i = end


def fnum(v):
    """Format a float the way KiCad does (no trailing zeros)."""
    s = '%.6f' % v
    s = s.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


# ====================================================================================================
# BOARD
# ====================================================================================================
# Board model: footprints (absolute pads, F.Fab body, courtyard), tracks, vias, zones, outline, netclasses.
#
# Coordinates are KiCad mm, Y down. Pad positions are made absolute with the footprint transform.
# Placement and routing are authored in Python: b.place(), b.seg()/b.poly(), b.via(); write with pcbkit.writer.
F, B = 'F.Cu', 'B.Cu'
_SHAPES = ('fp_rect', 'fp_line', 'fp_poly', 'fp_circle', 'fp_arc')


def _shape_pts(g):
    pts = []
    for k in ('start', 'end', 'mid', 'center'):
        q = kid(g, k)
        if q:
            pts.append((float(q[1]), float(q[2])))
    q = kid(g, 'pts')
    if q:
        pts += [(float(a[1]), float(a[2])) for a in q[1:] if a[0] == 'xy']
    if g[0] == 'fp_circle' and kid(g, 'center') and kid(g, 'end'):
        c, e = kid(g, 'center'), kid(g, 'end')
        r = math.hypot(float(e[1]) - float(c[1]), float(e[2]) - float(c[2]))
        cx, cy = float(c[1]), float(c[2])
        pts += [(cx - r, cy - r), (cx + r, cy + r)]
    return pts


def _bbox(pts):
    if not pts:
        return None
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


class Board:
    def __init__(self, path, pro=None):
        self.path = path
        raw = open(path, encoding='utf-8', newline='').read()
        self.nl = '\r\n' if '\r\n' in raw else '\n'
        self.txt = raw.replace('\r\n', '\n')
        t = parse(self.txt)
        self.tree = t
        self.fp = {}
        for fp in kids(t, 'footprint'):
            at = kid(fp, 'at')
            ref = [p for p in kids(fp, 'property') if p[1] == 'Reference'][0][2]
            rot = float(at[3]) if len(at) > 3 else 0.0
            side = kid(fp, 'layer')[1]
            pads = []
            for p in kids(fp, 'pad'):
                pa, sz, n, dr = kid(p, 'at'), kid(p, 'size'), kid(p, 'net'), kid(p, 'drill')
                rr = kid(p, 'roundrect_rratio')
                drill = None
                if dr:
                    v = [x for x in dr[1:] if not isinstance(x, list)]
                    drill = ('oval', float(v[1]), float(v[2])) if v and v[0] == 'oval' else ('circle', float(v[0]), float(v[0]))
                pads.append(dict(num=p[1], type=p[2], shape=p[3], x=float(pa[1]), y=float(pa[2]),
                                 la=(float(pa[3]) if len(pa) > 3 else 0.0) - rot,
                                 w=float(sz[1]), h=float(sz[2]), rr=float(rr[1]) if rr else 0.0,
                                 net=n[-1] if n else '', drill=drill,
                                 layers=[x for x in (kid(p, 'layers') or [])[1:]]))
            fab = [q for g in fp if isinstance(g, list) and g and g[0] in _SHAPES and kid(g, 'layer')
                   and kid(g, 'layer')[1] in ('F.Fab', 'B.Fab') for q in _shape_pts(g)]
            crt = [q for g in fp if isinstance(g, list) and g and g[0] in _SHAPES and kid(g, 'layer')
                   and kid(g, 'layer')[1] in ('F.CrtYd', 'B.CrtYd') for q in _shape_pts(g)]
            props = {p[1]: p[2] for p in kids(fp, 'property')}
            padbox = _bbox([(q['x'], q['y']) for q in pads]) or (0, 0, 0, 0)
            self.fp[ref] = dict(side=side, value=props.get('Value', ''), lib=fp[1],
                                fab=_bbox(fab) or _bbox(crt) or padbox, crt=_bbox(crt) or _bbox(fab) or padbox,
                                orig=(float(at[1]), float(at[2]), rot), pos=(float(at[1]), float(at[2]), rot), pads=pads)
        # existing copper (read-only view; authored copper goes to self.segs/self.vias)
        self.old_segs = []
        for s in kids(t, 'segment'):
            a, b2 = kid(s, 'start'), kid(s, 'end')
            self.old_segs.append(dict(a=(float(a[1]), float(a[2])), b=(float(b2[1]), float(b2[2])),
                                      w=float(kid(s, 'width')[1]), layer=kid(s, 'layer')[1], net=kid(s, 'net')[-1]))
        self.old_vias = [dict(c=(float(kid(v, 'at')[1]), float(kid(v, 'at')[2])), net=kid(v, 'net')[-1],
                              size=float(kid(v, 'size')[1]), drill=float(kid(v, 'drill')[1])) for v in kids(t, 'via')]
        self.zones = []
        for z in kids(t, 'zone'):
            L = kid(z, 'layer') or kid(z, 'layers')
            pol = kid(z, 'polygon')
            pts = [(float(a[1]), float(a[2])) for a in kid(pol, 'pts')[1:]] if pol else []
            pr = kid(z, 'priority')
            self.zones.append(dict(net=(kid(z, 'net') or [''])[-1], layers=list(L[1:]) if L else [],
                                   name=(kid(z, 'name') or ['', ''])[1], priority=int(pr[1]) if pr else 0, pts=pts,
                                   keepout=kid(z, 'keepout') is not None))
        edge = []
        for g in t:
            if isinstance(g, list) and g and g[0] in ('gr_line', 'gr_rect', 'gr_arc', 'gr_poly', 'gr_circle') \
                    and kid(g, 'layer') and kid(g, 'layer')[1] == 'Edge.Cuts':
                edge += _shape_pts([('fp' + g[0][2:])] + g[1:])
        self.outline = _bbox(edge) or (0.0, 0.0, 100.0, 100.0)
        setup = kid(t, 'setup') or []
        o = kid(setup, 'aux_axis_origin')
        self.aux_origin = (float(o[1]), float(o[2])) if o else None
        self._load_netclasses(pro or os.path.splitext(path)[0] + '.kicad_pro')
        self.segs, self.vias = [], []

    # ---------- netclasses ----------
    def _load_netclasses(self, pro):
        self.classes = {'Default': dict(clearance=0.2, track_width=0.2)}
        self.patterns = []
        self.pro = pro if os.path.exists(pro) else None
        if self.pro:
            j = json.load(open(pro, encoding='utf-8'))
            ns = j.get('net_settings', {})
            for c in ns.get('classes', []):
                self.classes[c['name']] = dict(clearance=c.get('clearance', 0.2), track_width=c.get('track_width', 0.2))
            self.patterns = [(p['pattern'], p['netclass']) for p in ns.get('netclass_patterns', [])]
            for net, cl in (ns.get('netclass_assignments') or {}).items():
                self.patterns.append((net, cl if isinstance(cl, str) else cl[0]))

    def netclass(self, net):
        for pat, cl in self.patterns:
            if fnmatch.fnmatchcase(net, pat) and cl in self.classes:
                return cl
        return 'Default'

    def clearance(self, net):
        return self.classes[self.netclass(net)]['clearance']

    # ---------- placement ----------
    def place(self, ref, x, y, rot):
        self.fp[ref]['pos'] = (x, y, rot)

    def xf(self, ref, px, py):
        x, y, rot = self.fp[ref]['pos']; r = math.radians(rot)
        return (x + px * math.cos(r) + py * math.sin(r), y - px * math.sin(r) + py * math.cos(r))

    def _box(self, ref, key):
        x0, y0, x1, y1 = self.fp[ref][key]
        c = [self.xf(ref, a, b) for a in (x0, x1) for b in (y0, y1)]
        return (min(p[0] for p in c), min(p[1] for p in c), max(p[0] for p in c), max(p[1] for p in c))

    def crt(self, ref):
        """Absolute courtyard bbox."""
        return self._box(ref, 'crt')

    def body(self, ref):
        """Absolute F.Fab body bbox (K1 keep-out)."""
        return self._box(ref, 'fab')

    def pads(self):
        out = []
        for ref, f in self.fp.items():
            for p in f['pads']:
                ax, ay = self.xf(ref, p['x'], p['y'])
                w, h = p['w'], p['h']
                if round(p['la'] + f['pos'][2]) % 180 == 90:
                    w, h = h, w
                d = dict(p); d.update(ref=ref, ax=ax, ay=ay, aw=w, ah=h, name='%s.%s' % (ref, p['num']))
                out.append(d)
        return out

    def pad(self, name):
        r = [p for p in self.pads() if p['name'] == name]
        assert r, 'no pad ' + name
        return r[0]

    def P(self, name):
        """Absolute centre of pad 'REF.NUM'."""
        p = self.pad(name); return (p['ax'], p['ay'])

    def place_check(self, edge_margin=0.2, skip_edge=()):
        """Courtyard overlaps and courtyards crossing the outline (connectors may be listed in skip_edge)."""
        bad, refs = [], list(self.fp)
        X0, Y0, X1, Y1 = self.outline
        for i, a in enumerate(refs):
            A = self.crt(a)
            if a not in skip_edge and (A[0] < X0 + edge_margin or A[1] < Y0 + edge_margin or A[2] > X1 - edge_margin or A[3] > Y1 - edge_margin):
                bad.append((a, 'edge', A))
            for b in refs[i + 1:]:
                Bb = self.crt(b)
                if A[0] < Bb[2] - 1e-6 and Bb[0] < A[2] - 1e-6 and A[1] < Bb[3] - 1e-6 and Bb[1] < A[3] - 1e-6:
                    bad.append((a, b))
        return bad

    # ---------- authoring copper ----------
    def seg(self, a, b, w, net, layer=F):
        if math.hypot(a[0] - b[0], a[1] - b[1]) > 1e-6:
            self.segs.append(dict(a=(round(a[0], 4), round(a[1], 4)), b=(round(b[0], 4), round(b[1], 4)), w=w, layer=layer, net=net))

    def poly(self, pts, w, net, layer=F):
        """Polyline through points (pad centres from b.P('U1.3') or (x, y))."""
        for a, b in zip(pts, pts[1:]):
            self.seg(a, b, w, net, layer)

    def via(self, c, net, size=0.6, drill=0.3):
        self.vias.append(dict(c=(round(c[0], 4), round(c[1], 4)), net=net, size=size, drill=drill))

    def keep_existing_copper(self):
        """Start from the board's current tracks/vias (edit mode) instead of an empty route."""
        self.segs = [dict(s) for s in self.old_segs]
        self.vias = [dict(v) for v in self.old_vias]


# ====================================================================================================
# CHECK
# ====================================================================================================
# Independent geometric checks (NOT a replacement for KiCad DRC): clearance, hole, edge, connectivity,
# dangling ends, K1 body keep-out, courtyard overlap. Zones are ignored: nets joined only by a zone show as split.
#
#     python -m pcbkit check board.kicad_pcb --exempt J1,/USB_DM
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


# ====================================================================================================
# ROUTER
# ====================================================================================================
# Grid A* router for 2-layer boards, used to *assist* scripted priority routing (not a full autorouter).
#
# - 8-direction grid (default 0.05 mm), obstacles rasterised at 4x supersampling with OpenCV
# - respects netclass clearance, hole clearance, board edge, K1 keep-outs (pcbkit.check.keepouts)
# - costs: B.Cu x b_cost, via via_cost, inside IC pad area x ic_cost, turn penalty
#     r = Router(b); r.route('/UART_TX', 'U1.2', 'U2.3', w=0.2, layers=(F, B), allow_via=True)
# `src` may be a pad name, a list of pad names, or 'tree' (= existing copper of the net). Output goes to b.segs/b.vias.
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


class Grid:
    def __init__(self, b, g=0.05, ss=4):
        self.b, self.g, self.ss = b, g, ss
        X0, Y0, X1, Y1 = b.outline
        self.x0, self.y0 = X0, Y0
        self.nx, self.ny = int(round((X1 - X0) / g)) + 1, int(round((Y1 - Y0) / g)) + 1
        self.hx, self.hy = (self.nx - 1) * ss + 1, (self.ny - 1) * ss + 1

    def hp(self, x, y):           # mm -> hi-res pixel
        return (int(round((x - self.x0) / self.g * self.ss)), int(round((y - self.y0) / self.g * self.ss)))

    def hl(self, v):              # mm length -> hi-res pixels
        return int(round(v / self.g * self.ss))

    def cell(self, x, y):
        return (int(round((x - self.x0) / self.g)), int(round((y - self.y0) / self.g)))

    def xy(self, ix, iy):
        return (self.x0 + ix * self.g, self.y0 + iy * self.g)


def blocked(gr, net, layer, hw, extra_cl=0.0, for_via=False, extra_keepouts=None):
    """bool[ny, nx]: True where a track centre (half-width hw) of `net` may not go on `layer`."""
    b = gr.b; m = np.zeros((gr.hy, gr.hx), np.uint8); mg = 0.02
    infl = lambda other: hw + max(b.clearance(net), b.clearance(other)) + extra_cl + mg
    for p in b.pads():
        if p['drill'] and (p['net'] != net or p['type'] == 'np_thru_hole' or for_via):
            kind, dw, dh = p['drill']
            if kind == 'oval' and round(p['la'] + b.fp[p['ref']]['pos'][2]) % 180 == 90:
                dw, dh = dh, dw
            r = min(dw, dh) / 2; d = r + 0.25 + hw + mg
            cv2.line(m, gr.hp(p['ax'] - (dw / 2 - r), p['ay'] - (dh / 2 - r)), gr.hp(p['ax'] + (dw / 2 - r), p['ay'] + (dh / 2 - r)), 1, max(1, 2 * gr.hl(d)))
        if p['type'] == 'np_thru_hole' or p['net'] == net:
            continue
        if p['type'] == 'smd' and layer != F:
            continue
        d = infl(p['net'] or '?')
        cv2.rectangle(m, gr.hp(p['ax'] - p['aw'] / 2 - d, p['ay'] - p['ah'] / 2 - d), gr.hp(p['ax'] + p['aw'] / 2 + d, p['ay'] + p['ah'] / 2 + d), 1, -1)
    for s in b.segs:
        if s['net'] != net and s['layer'] == layer:
            cv2.line(m, gr.hp(*s['a']), gr.hp(*s['b']), 1, max(1, 2 * gr.hl(infl(s['net']) + s['w'] / 2)))
    for v in b.vias:
        if v['net'] != net:
            cv2.circle(m, gr.hp(*v['c']), gr.hl(v.get('size', 0.6) / 2 + infl(v['net'])), 1, -1)
        elif for_via:
            cv2.circle(m, gr.hp(*v['c']), gr.hl(0.15 + 0.25 + 0.15 + mg), 1, -1)
    for z in b.zones:
        if z['net'] != net and layer in z['layers'] and z['pts'] and not z['net'] == '/GND':
            pts = np.array([gr.hp(*q) for q in z['pts']], np.int32)
            cv2.fillPoly(m, [pts], 1); cv2.polylines(m, [pts], True, 1, max(1, 2 * gr.hl(infl(z['net']))))
    e = gr.hl(0.3 + hw + mg + 0.1); m[:e, :] = 1; m[-e:, :] = 1; m[:, :e] = 1; m[:, -e:] = 1
    if layer == F:
        own = np.zeros_like(m)
        for p in b.pads():
            if p['net'] == net and p['type'] == 'smd':
                cv2.rectangle(own, gr.hp(p['ax'] - p['aw'] / 2, p['ay'] - p['ah'] / 2), gr.hp(p['ax'] + p['aw'] / 2, p['ay'] + p['ah'] / 2), 1, -1)
        ko = np.zeros_like(m)
        for ref, (x0, y0, x1, y1), inf in keepouts(b, extra_keepouts):
            d = hw if inf else 0
            cv2.rectangle(ko, gr.hp(x0 - d, y0 - d), gr.hp(x1 + d, y1 + d), 1, -1)
        m |= ko if for_via else (ko & (1 - own))
    return m[::gr.ss, ::gr.ss].astype(bool)


class Router:
    def __init__(self, b, grid=0.05, b_cost=3.0, via_cost=10.0, ic_cost=4.0, turn=0.25, b_forbid=None, extra_keepouts=None):
        self.b, self.gr = b, Grid(b, grid)
        self.b_cost, self.via_cost, self.ic_cost, self.turn = b_cost, via_cost, ic_cost, turn
        self.bf, self.xk = b_forbid, extra_keepouts

    def _tree(self, net, layer):
        gr, c = self.gr, set()
        for s in self.b.segs:
            if s['net'] == net and s['layer'] == layer:
                n = max(1, int(math.dist(s['a'], s['b']) / gr.g * 2))
                for k in range(n + 1):
                    x = s['a'][0] + (s['b'][0] - s['a'][0]) * k / n; y = s['a'][1] + (s['b'][1] - s['a'][1]) * k / n
                    c.add(gr.cell(x, y))
        for v in self.b.vias:
            if v['net'] == net:
                c.add(gr.cell(*v['c']))
        return c

    def route(self, net, src, dst, w, layers=(F,), extra_cl=0.05, allow_via=False, max_exp=3_000_000):
        b, gr = self.b, self.gr; hw = w / 2
        blk = {L: blocked(gr, net, L, hw, extra_cl, extra_keepouts=self.xk) for L in (F, B)}
        if self.bf is not None:
            blk[B] |= self.bf
        vb = (blocked(gr, net, F, 0.3, 0, True, self.xk) | blocked(gr, net, B, 0.3, 0, True, self.xk)) if allow_via else None
        icz = np.zeros((gr.ny, gr.nx), bool)
        for ref in b.fp:
            if ref[0] == 'U':
                ps = [p for p in b.pads() if p['ref'] == ref]
                (i0, j0), (i1, j1) = gr.cell(min(p['ax'] for p in ps), min(p['ay'] for p in ps)), gr.cell(max(p['ax'] for p in ps), max(p['ay'] for p in ps))
                icz[j0:j1 + 1, i0:i1 + 1] = True
        def padcell(nm):
            p = b.pad(nm); return gr.cell(p['ax'], p['ay']), (p['ax'], p['ay']), p
        starts = {}
        if src == 'tree':
            for L in (F, B):
                for c in self._tree(net, L):
                    starts[(L,) + c] = None
        else:
            for nm in ([src] if isinstance(src, str) else src):
                c, ex, p = padcell(nm); starts[(F,) + c] = ex
                if p['drill']:
                    starts[(B,) + c] = ex
        gc, gex, gp = padcell(dst); goals = {(F,) + gc}
        if gp['drill']:
            goals.add((B,) + gc)
        for (L, x, y) in list(starts) + list(goals):
            blk[L][y, x] = False
        gx, gy = gc
        h = lambda x, y: (max(abs(x - gx), abs(y - gy)) + 0.4142 * min(abs(x - gx), abs(y - gy))) * gr.g
        pq, best, par = [], {}, {}
        for st in starts:
            k = st + (8,); best[k] = 0.0; heapq.heappush(pq, (h(st[1], st[2]), 0.0, k))
        exp, end = 0, None
        while pq:
            f, g, k = heapq.heappop(pq)
            if g > best.get(k, 1e18) + 1e-9:
                continue
            L, x, y, d = k
            if (L, x, y) in goals:
                end = k; break
            exp += 1
            if exp > max_exp:
                break
            for nd, (dx, dy) in enumerate(DIRS):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < gr.nx and 0 <= ny < gr.ny) or blk[L][ny, nx] or L not in layers:
                    continue
                if dx and dy and (blk[L][y, nx] or blk[L][ny, x]):
                    continue
                c = (1.4142 if dx and dy else 1.0) * gr.g
                c *= self.b_cost if L == B else (self.ic_cost if icz[ny, nx] else 1.0)
                if d != 8 and nd != d:
                    t = min((nd - d) % 8, (d - nd) % 8); c += self.turn * (1 if t == 1 else 3 if t == 2 else 20)
                nk, ng = (L, nx, ny, nd), g + c
                if ng < best.get(nk, 1e18) - 1e-9:
                    best[nk] = ng; par[nk] = k; heapq.heappush(pq, (ng + h(nx, ny), ng, nk))
            oL = B if L == F else F
            if allow_via and not vb[y, x] and oL in layers:
                nk, ng = (oL, x, y, 8), g + self.via_cost
                if ng < best.get(nk, 1e18) - 1e-9:
                    best[nk] = ng; par[nk] = k; heapq.heappush(pq, (ng + h(x, y), ng, nk))
        if end is None:
            return False
        path = [end]
        while path[-1] in par:
            path.append(par[path[-1]])
        path.reverse()
        pts = [(k[0],) + gr.xy(k[1], k[2]) for k in path]
        s0 = starts.get(path[0][:3])
        if s0:
            pts.insert(0, (pts[0][0],) + tuple(s0))
        pts.append((pts[-1][0],) + tuple(gex))
        run = [pts[0]]
        for p in pts[1:]:
            if p[0] != run[-1][0]:
                self._emit(run, w, net); b.via((p[1], p[2]), net); run = [p]; continue
            run.append(p)
        self._emit(run, w, net); self.last_cost = best[end]
        return True

    def _emit(self, run, w, net):
        if len(run) < 2:
            return
        L, out = run[0][0], [run[0]]
        for i in range(1, len(run) - 1):
            a, p, c = out[-1], run[i], run[i + 1]
            if abs((p[1] - a[1]) * (c[2] - p[2]) - (p[2] - a[2]) * (c[1] - p[1])) > 1e-9:
                out.append(p)
        out.append(run[-1])
        for a, c in zip(out, out[1:]):
            self.b.seg((a[1], a[2]), (c[1], c[2]), w, net, L)


# ====================================================================================================
# WRITER
# ====================================================================================================
# Write a Board back to .kicad_pcb by editing the original text (everything not touched is kept byte-for-byte).
#
# write(b, out)                       moved footprints + replace ALL tracks/vias with b.segs/b.vias, drop zone fills
# write(b, out, copper='append')      keep existing tracks/vias, append only b.segs/b.vias (use for stitching vias)
# Zone fills are removed (KiCad refills with B or `kicad-cli pcb drc --refill-zones`).
def _norm(a):
    a = ((a + 180) % 360) - 180
    return 180 if a == -180 else a


def _move_footprints(b, txt):
    out, last = [], 0
    for i, j in blocks(txt, '\t(footprint '):
        blk = txt[i:j]
        ref = re.search(r'\(property "Reference" "([^"]+)"', blk)[1]
        ox, oy, orot = b.fp[ref]['orig']; x, y, rot = b.fp[ref]['pos']
        if (ox, oy, orot) != (x, y, rot):
            d, cnt = rot - orot, [0]
            def rep(m):
                cnt[0] += 1
                if cnt[0] == 1:                       # the footprint's own (at x y rot)
                    return '(at %s %s%s)' % (fnum(x), fnum(y), '' if _norm(rot) == 0 else ' ' + fnum(_norm(rot)))
                if d == 0:
                    return m[0]
                na = _norm((float(m[3]) if m[3] else 0.0) + d)   # pad/property angles are absolute in the file
                return '(at %s %s%s)' % (m[1], m[2], '' if na == 0 else ' ' + fnum(na))
            blk = re.sub(r'\(at ([\d.\-]+) ([\d.\-]+)(?: ([\d.\-]+))?\)', rep, blk)
        out += [txt[last:i], blk]; last = j
    out.append(txt[last:])
    return ''.join(out)


def copper_text(segs, vias):
    s = ''
    for g in segs:
        s += ('\t(segment\n\t\t(start %s %s)\n\t\t(end %s %s)\n\t\t(width %s)\n\t\t(layer "%s")\n\t\t(net "%s")\n\t\t(uuid "%s")\n\t)\n'
              % (fnum(g['a'][0]), fnum(g['a'][1]), fnum(g['b'][0]), fnum(g['b'][1]), fnum(g['w']), g['layer'], g['net'], uuid.uuid4()))
    for v in vias:
        s += ('\t(via\n\t\t(at %s %s)\n\t\t(size %s)\n\t\t(drill %s)\n\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "%s")\n\t\t(uuid "%s")\n\t)\n'
              % (fnum(v['c'][0]), fnum(v['c'][1]), fnum(v.get('size', 0.6)), fnum(v.get('drill', 0.3)), v['net'], uuid.uuid4()))
    return s


def insert_before_zones(txt, block):
    z = txt.find('\t(zone\n')
    if z < 0:
        z = txt.rfind(')')
    return txt[:z] + block + txt[z:]


def drop_fills(txt):
    for i, j in reversed(blocks(txt, '\t\t(filled_polygon\n')):
        txt = txt[:i] + txt[j:]
    return txt


def write(b, out, copper='replace', keep_fills=False, extra_text=''):
    txt = _move_footprints(b, b.txt)
    if copper == 'replace':
        for head in ('\t(segment\n', '\t(arc\n', '\t(via\n'):
            for i, j in reversed(blocks(txt, head)):
                txt = txt[:i] + txt[j:]
    txt = insert_before_zones(txt, copper_text(b.segs, b.vias) + extra_text)
    if not keep_fills:
        txt = drop_fills(txt)
    open(out, 'w', encoding='utf-8', newline='').write(txt.replace('\n', b.nl))
    return out


def zone_text(net, layer, pts, name='', priority=0, clearance=0.25, min_thickness=0.2, thermal_gap=0.5, thermal_bridge=0.5):
    """A zone block without fill data (KiCad fills it)."""
    xy = ' '.join('(xy %s %s)' % (fnum(x), fnum(y)) for x, y in pts)
    return ('\t(zone\n\t\t(net "%s")\n\t\t(layer "%s")\n\t\t(uuid "%s")\n%s\t\t(hatch edge 0.5)\n\t\t(priority %d)\n'
            '\t\t(connect_pads\n\t\t\t(clearance %s)\n\t\t)\n\t\t(min_thickness %s)\n'
            '\t\t(fill yes\n\t\t\t(thermal_gap %s)\n\t\t\t(thermal_bridge_width %s)\n\t\t\t(island_removal_mode 0)\n\t\t)\n'
            '\t\t(polygon\n\t\t\t(pts\n\t\t\t\t%s\n\t\t\t)\n\t\t)\n\t)\n'
            % (net, layer, uuid.uuid4(), ('\t\t(name "%s")\n' % name) if name else '', priority, fnum(clearance), fnum(min_thickness),
               fnum(thermal_gap), fnum(thermal_bridge), xy))


# ====================================================================================================
# STITCH
# ====================================================================================================
# GND pour on F.Cu + purposeful GND stitching vias (owner rules, singleRgbCtrl 2026-11-18):
#   1. fence   : along `fence_nets` (power, USB pair) both sides, ~fence_pitch mm
#   2. island  : every F.Cu pour island >= island_min mm^2 without a GND via / GND THT pad gets one via (may sit under a body)
#   3. coverage: until every pour point is <= cover_r mm from a GND via (outside bodies)
# Never on pads (>= pad_gap from ANY pad), never in another net's zone, >= 0.65 mm from the edge, >= 1.0 mm between GND vias.
#
#     python -m pcbkit stitch board.kicad_pcb out.kicad_pcb --fence /+5V,/USB_DP,/USB_DM
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


def stitch_apply(path, out, **kw):
    """Add stitching vias (+ GND_TOP zone if missing) to an existing board without touching anything else."""
    b = Board(path); b.keep_existing_copper()
    r = stitch(b, **kw)
    txt = insert_before_zones(b.txt, copper_text([], r['vias']) + r['zone_text'])
    open(out, 'w', encoding='utf-8', newline='').write(drop_fills(txt).replace('\n', b.nl))
    return r


# ====================================================================================================
# TRANSFORM
# ====================================================================================================
# Whole-board text transforms.
#
# translate(src, out, dx, dy)          move every absolute coordinate (footprint `at`, tracks, vias, zones, gr_*, dimensions);
#                                      footprint-internal geometry is relative and is left alone
# set_origin(src, out, x, y)           aux (drill/place) origin + grid origin
# center_on_sheet(src, out)            translate so the outline centre = sheet centre, origin = board bottom-left
# rename_project(folder, old, new)     rename .kicad_pro/.kicad_sch/.kicad_pcb/.kicad_prl and the name inside them
SHIFT = {'at', 'start', 'end', 'mid', 'center', 'xy'}
SHEETS = {'A4': (297, 210), 'A3': (420, 297), 'A5': (210, 148), 'USLetter': (279.4, 215.9)}
# (_TOK shared with SEXPR)


def _translate_text(s, dx, dy):
    out, last, stack, pending, opened = [], 0, [], None, False
    for m in _TOK.finditer(s):
        t = m.group()
        if t == '(':
            opened = True; continue
        if opened:
            opened = False; stack.append(t)
            parent = stack[-2] if len(stack) > 1 else None
            infp = 'footprint' in stack[:-1]
            ok = t in SHIFT and ((t == 'at' and parent == 'footprint') if infp else parent not in ('setup', 'pcbplotparams'))
            pending = [0] if ok else None
            continue
        if t == ')':
            stack.pop(); pending = None; continue
        if pending is not None and pending[0] < 2:
            try:
                v = float(t)
            except ValueError:
                pending = None; continue
            out += [s[last:m.start()], fnum(v + (dx if pending[0] == 0 else dy))]; last = m.end(); pending[0] += 1
    out.append(s[last:])
    return ''.join(out)


def _rw(src, out, fn):
    raw = open(src, encoding='utf-8', newline='').read(); nl = '\r\n' if '\r\n' in raw else '\n'
    open(out, 'w', encoding='utf-8', newline='').write(fn(raw.replace('\r\n', '\n')).replace('\n', nl))


def _origin(s, x, y):
    s = re.sub(r'\n\t\t\((aux_axis_origin|grid_origin) [^)]*\)', '', s)
    i = s.index('(pcbplotparams'); j = s.rfind('\n', 0, i) + 1
    return s[:j] + '\t\t(aux_axis_origin %s %s)\n\t\t(grid_origin %s %s)\n' % (fnum(x), fnum(y), fnum(x), fnum(y)) + s[j:]


def translate(src, out, dx, dy):
    _rw(src, out, lambda s: _translate_text(s, dx, dy))


def set_origin(src, out, x, y):
    _rw(src, out, lambda s: _origin(s, x, y))


def center_on_sheet(src, out, origin='bottom-left'):
    b = Board(src)
    paper = kid(b.tree, 'paper')[1]
    sw, sh = SHEETS.get(paper, SHEETS['A4'])
    if len(kid(b.tree, 'paper')) > 2 and kid(b.tree, 'paper')[2] == 'portrait':
        sw, sh = sh, sw
    X0, Y0, X1, Y1 = b.outline
    dx = round(sw / 2 - (X0 + X1) / 2, 4); dy = round(sh / 2 - (Y0 + Y1) / 2, 4)
    ox, oy = {'bottom-left': (X0, Y1), 'top-left': (X0, Y0), 'center': ((X0 + X1) / 2, (Y0 + Y1) / 2)}[origin]
    _rw(src, out, lambda s: _origin(_translate_text(s, dx, dy), ox + dx, oy + dy))
    # self-check: translating back must give the original text (origin lines aside)
    back = _translate_text(re.sub(r'\n\t\t\((aux_axis_origin|grid_origin) [^)]*\)', '',
                                  open(out, encoding='utf-8', newline='').read().replace('\r\n', '\n')), -dx, -dy)
    orig = re.sub(r'\n\t\t\((aux_axis_origin|grid_origin) [^)]*\)', '', b.txt)
    num = re.compile(r'-?\d+\.?\d*(?:e-?\d+)?')
    assert num.split(back) == num.split(orig) and all(a == c or abs(float(a) - float(c)) < 1e-6 for a, c in zip(num.findall(back), num.findall(orig))), 'round-trip failed'
    return dx, dy, (ox + dx, oy + dy)


def rename_project(folder, old, new, title=None, date=None, rev=None, comment=None):
    for ext in ('kicad_pro', 'kicad_prl', 'kicad_sch', 'kicad_pcb'):
        src = os.path.join(folder, '%s.%s' % (old, ext))
        if not os.path.exists(src):
            continue
        raw = open(src, encoding='utf-8', newline='').read(); nl = '\r\n' if '\r\n' in raw else '\n'
        # only whole-name occurrences: "old", old.kicad_*, old.<ext> (never a substring of other text)
        s = re.sub(r'(?<![\w.-])' + re.escape(old) + r'(?=["./])', new, raw.replace('\r\n', '\n'))
        if ext in ('kicad_pcb', 'kicad_sch') and title and '(title_block' not in s:
            tb = '\t(title_block\n\t\t(title "%s")\n' % title
            tb += ('\t\t(date "%s")\n' % date if date else '') + ('\t\t(rev "%s")\n' % rev if rev else '')
            tb += ('\t\t(comment 1 "%s")\n' % comment if comment else '') + '\t)\n'
            i = s.find('(paper')
            if i >= 0:
                j = s.index('\n', i) + 1; s = s[:j] + tb + s[j:]
        open(os.path.join(folder, '%s.%s' % (new, ext)), 'w', encoding='utf-8', newline='').write(s.replace('\n', nl))


# ====================================================================================================
# DIFF
# ====================================================================================================
# What changed between two boards (use every time the owner saved the board):
# footprints moved/rotated, tracks added/removed per net+layer (count, mm), vias added/removed, zones, origin.
# Coordinates of `b` can be shifted back with offset=(dx, dy) when one board was translated.
#
#     python -m pcbkit diff old.kicad_pcb new.kicad_pcb
def diff(a_path, b_path, offset=(0.0, 0.0), verbose=True):
    A, Bb = Board(a_path), Board(b_path)
    ox, oy = offset
    q = lambda v: round(v + 1e-7, 3)
    sh = lambda p: (q(p[0] - ox), q(p[1] - oy))
    moved = []
    for r in sorted(set(A.fp) | set(Bb.fp)):
        pa, pb = A.fp.get(r, {}).get('pos'), Bb.fp.get(r, {}).get('pos')
        pb = (pb[0] - ox, pb[1] - oy, pb[2]) if pb else None
        if pa is None or pb is None or any(abs(x - y) > 1e-3 for x, y in zip(pa, pb)):
            moved.append((r, pa, pb))
    norm = lambda s, f=lambda p: (q(p[0]), q(p[1])): (s['net'], s['layer'], s['w']) + tuple(sorted([f(s['a']), f(s['b'])]))
    sa = collections.Counter(norm(s) for s in A.old_segs)
    sb = collections.Counter(norm(s, sh) for s in Bb.old_segs)
    rem, add = sa - sb, sb - sa
    per = collections.defaultdict(lambda: [0, 0.0, 0, 0.0])
    for s, c in rem.items():
        per[s[:2]][0] += c; per[s[:2]][1] += c * math.dist(s[3], s[4])
    for s, c in add.items():
        per[s[:2]][2] += c; per[s[:2]][3] += c * math.dist(s[3], s[4])
    va = collections.Counter((v['net'], q(v['c'][0]), q(v['c'][1])) for v in A.old_vias)
    vb = collections.Counter((v['net'],) + sh(v['c']) for v in Bb.old_vias)
    res = dict(moved=moved, tracks=dict(per), tracks_removed=list(rem.elements()), tracks_added=list(add.elements()),
               vias_removed=list((va - vb).elements()), vias_added=list((vb - va).elements()),
               zones=([(z['net'], z['layers'], z['priority'], z['name']) for z in A.zones], [(z['net'], z['layers'], z['priority'], z['name']) for z in Bb.zones]),
               origin=(A.aux_origin, Bb.aux_origin), counts=((len(A.old_segs), len(A.old_vias)), (len(Bb.old_segs), len(Bb.old_vias))))
    if verbose:
        print('segments %d -> %d, vias %d -> %d, origin %s -> %s' % (res['counts'][0][0], res['counts'][1][0], res['counts'][0][1], res['counts'][1][1], *res['origin']))
        for r, pa, pb in moved:
            print('  moved %-5s %s -> %s' % (r, pa, pb))
        for (net, layer), (nr, lr, na, la) in sorted(per.items()):
            print('  tracks %-10s %-5s -%d (%.2f mm)  +%d (%.2f mm)' % (net, layer, nr, lr, na, la))
        print('  vias removed:', res['vias_removed']); print('  vias added:', res['vias_added'])
        if res['zones'][0] != res['zones'][1]:
            print('  zones:', res['zones'][0], '->', res['zones'][1])
    return res


# ====================================================================================================
# RENDER
# ====================================================================================================
# Matplotlib render of a Board for self-review and before/after comparison (not a KiCad screenshot).
# Pads coloured by net, F.Cu tracks solid / B.Cu dotted, vias (highlighted ones green), non-GND zones, courtyards, refs, mm grid.
# For the real copper (zone fills) use `kicad-cli pcb export svg` / `pcb render` (see CLAUDE.md 9A).
#
#     python -m pcbkit render board.kicad_pcb out.png [--region x0,y0,x1,y1]


def render(b, out, title='', highlight=(), region=None, copper=True, size=17):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Circle, Polygon
    nets = sorted({p['net'] for p in b.pads() if p['net'] and not p['net'].startswith('unconn')})
    cm = plt.get_cmap('tab20'); col = {n: cm(i % 20) for i, n in enumerate(nets)}; col['/GND'] = (0.45, 0.45, 0.45, 1)
    X0, Y0, X1, Y1 = region or b.outline
    fig, ax = plt.subplots(figsize=(size, size * (Y1 - Y0) / max(X1 - X0, 1e-6)))
    ax.set_xlim(X0 - 0.5, X1 + 0.5); ax.set_ylim(Y1 + 0.5, Y0 - 0.5); ax.set_aspect('equal')
    bx0, by0, bx1, by1 = b.outline
    ax.add_patch(Rectangle((bx0, by0), bx1 - bx0, by1 - by0, fill=False, ec='k', lw=2))
    for z in b.zones:
        if z['net'] != '/GND' and z['pts']:
            ax.add_patch(Polygon(z['pts'], closed=True, fc=(0.12, 0.47, 0.71, 0.3), ec='b', lw=1, zorder=4))
    for ref in b.fp:
        x0, y0, x1, y1 = b.crt(ref)
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=(0.8, 0.2, 0.8), lw=0.6, ls='--'))
        ax.text((x0 + x1) / 2, (y0 + y1) / 2, ref, fontsize=9, weight='bold', ha='center', va='center', zorder=6)
    for p in b.pads():
        if p['type'] == 'np_thru_hole':
            ax.add_patch(Circle((p['ax'], p['ay']), p['aw'] / 2, fc='w', ec='k')); continue
        ax.add_patch(Rectangle((p['ax'] - p['aw'] / 2, p['ay'] - p['ah'] / 2), p['aw'], p['ah'], fc=col.get(p['net'], (0.87, 0.87, 0.87, 1)), ec='k', lw=0.3, alpha=0.6))
        ax.text(p['ax'], p['ay'], p['num'], fontsize=4, ha='center', va='center')
    k = size * 72 / (X1 - X0 + 1)
    hl = {tuple(map(lambda v: round(v, 3), h)) for h in highlight}
    if copper:
        for g in b.segs:
            ax.plot([g['a'][0], g['b'][0]], [g['a'][1], g['b'][1]], color=col.get(g['net'], 'k'), lw=g['w'] * k, solid_capstyle='round',
                    ls='-' if g['layer'] == F else (0, (1, 1.2)), alpha=0.9 if g['layer'] == F else 0.6)
        for v in b.vias:
            new = (round(v['c'][0], 3), round(v['c'][1], 3)) in hl
            ax.add_patch(Circle(v['c'], v.get('size', 0.6) / 2, fc=(0.1, 0.8, 0.2) if new else 'w', ec='k' if new else col.get(v['net'], 'k'), lw=1.2, zorder=7 if new else 5))
    for i, n in enumerate(nets):
        ax.text(X1 + 0.7, Y0 + 1 + i * 0.9, n, color=col[n], fontsize=10)
    ax.set_xticks(range(int(X0), int(X1) + 1)); ax.set_yticks(range(int(Y0), int(Y1) + 1)); ax.grid(alpha=0.2); ax.set_title(title)
    ax.tick_params(labelsize=7)
    plt.savefig(out, dpi=100, bbox_inches='tight'); plt.close()
    return out


# ====================================================================================================
# CLI
# ====================================================================================================
# CLI:
#   python -m pcbkit check   BOARD [--exempt REF,NET ...]
#   python -m pcbkit render  BOARD OUT.png [--region x0,y0,x1,y1] [--title T]
#   python -m pcbkit diff    OLD NEW [--offset dx,dy]
#   python -m pcbkit stitch  BOARD OUT [--fence /+5V,/USB_DP,/USB_DM] [--cover 3.5] [--pitch 2.5]
#   python -m pcbkit center  BOARD OUT [--origin bottom-left|top-left|center]
#   python -m pcbkit origin  BOARD OUT X Y
#   python -m pcbkit rename  FOLDER OLD NEW [--title T --date D --rev R --comment C]
def main(argv=None):
    ap = argparse.ArgumentParser(prog='pcbkit'); sp = ap.add_subparsers(dest='cmd', required=True)
    c = sp.add_parser('check'); c.add_argument('board'); c.add_argument('--exempt', nargs='*', default=[]); c.add_argument('--json')
    r = sp.add_parser('render'); r.add_argument('board'); r.add_argument('out'); r.add_argument('--region'); r.add_argument('--title', default='')
    d = sp.add_parser('diff'); d.add_argument('old'); d.add_argument('new'); d.add_argument('--offset', default='0,0')
    s = sp.add_parser('stitch'); s.add_argument('board'); s.add_argument('out'); s.add_argument('--fence', default='/+5V')
    s.add_argument('--cover', type=float, default=3.5); s.add_argument('--pitch', type=float, default=2.5); s.add_argument('--net', default='/GND')
    ce = sp.add_parser('center'); ce.add_argument('board'); ce.add_argument('out'); ce.add_argument('--origin', default='bottom-left')
    o = sp.add_parser('origin'); o.add_argument('board'); o.add_argument('out'); o.add_argument('x', type=float); o.add_argument('y', type=float)
    rn = sp.add_parser('rename'); rn.add_argument('folder'); rn.add_argument('old'); rn.add_argument('new')
    for k in ('title', 'date', 'rev', 'comment'):
        rn.add_argument('--' + k)
    a = ap.parse_args(argv)
    if a.cmd == 'check':
        res = check(a.board, exempt=[tuple(x.split(',', 1)) for x in a.exempt])
        if a.json:
            json.dump(res, open(a.json, 'w'), indent=1, default=str)
        return 1 if (res['violations'] or res['under_body'] or res['courtyard'] or res['dangling']) else 0
    if a.cmd == 'render':
        b = Board(a.board); b.keep_existing_copper()
        render(b, a.out, a.title, region=tuple(map(float, a.region.split(','))) if a.region else None)
    elif a.cmd == 'diff':
        diff(a.old, a.new, offset=tuple(map(float, a.offset.split(','))))
    elif a.cmd == 'stitch':
        r = stitch_apply(a.board, a.out, net=a.net, fence_nets=tuple(a.fence.split(',')), cover_r=a.cover, fence_pitch=a.pitch)
        print(r['counts'], 'skipped islands:', r['skipped_islands'])
    elif a.cmd == 'center':
        print('shift, origin:', center_on_sheet(a.board, a.out, a.origin))
    elif a.cmd == 'origin':
        set_origin(a.board, a.out, a.x, a.y)
    elif a.cmd == 'rename':
        rename_project(a.folder, a.old, a.new, a.title, a.date, a.rev, a.comment)
    return 0


if __name__ == '__main__':
    sys.exit(main())
