"""Grid A* router for 2-layer boards, used to *assist* scripted priority routing (not a full autorouter).

- 8-direction grid (default 0.05 mm), obstacles rasterised at 4x supersampling with OpenCV
- respects netclass clearance, hole clearance, board edge, K1 keep-outs (pcbkit.check.keepouts)
- costs: B.Cu x b_cost, via via_cost, inside IC pad area x ic_cost, turn penalty
    r = Router(b); r.route('/UART_TX', 'U1.2', 'U2.3', w=0.2, layers=(F, B), allow_via=True)
`src` may be a pad name, a list of pad names, or 'tree' (= existing copper of the net). Output goes to b.segs/b.vias.
"""
import heapq, math
import numpy as np, cv2
from .board import F, B
from .check import keepouts

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
