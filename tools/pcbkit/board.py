"""Board model: footprints (absolute pads, F.Fab body, courtyard), tracks, vias, zones, outline, netclasses.

Coordinates are KiCad mm, Y down. Pad positions are made absolute with the footprint transform.
Placement and routing are authored in Python: b.place(), b.seg()/b.poly(), b.via(); write with pcbkit.writer.
"""
import fnmatch, json, math, os
from .sexpr import parse, kids, kid

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
