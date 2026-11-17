#!/usr/bin/env python3
"""Functional geometry audit of a .kicad_pcb against a layout_intent.json.

Standard library only; reads the board file as text, never writes it.
It measures what KiCad DRC does not: decoupling distance, hot-loop geometry,
power track width, via count where power changes layer, vias/length on
no-via nets, differential-pair skew, slots cut into the reference layer.

STATUS: PROPOSED tool. A PASS here is a geometry statement, not proof that
the board works electrically; ERC/DRC and engineering review are still needed.
Thresholds come from the intent file first, then rules/layout_defaults.json.

usage: layout_audit.py BOARD.kicad_pcb INTENT.json [--defaults FILE] [--json OUT]
exit code: 0 no FAIL, 1 at least one FAIL, 2 input error
"""
import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ---------- s-expression ----------
def parse_sexpr(text):
    stack, cur, i, n = [], [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '(':
            stack.append(cur); cur = []; i += 1
        elif c == ')':
            done = cur; cur = stack.pop(); cur.append(done); i += 1
        elif c == '"':
            j, buf = i + 1, []
            while text[j] != '"':
                if text[j] == '\\':
                    j += 1
                buf.append(text[j]); j += 1
            cur.append(''.join(buf)); i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()':
                j += 1
            cur.append(text[i:j]); i = j
    return cur[0]


def kids(node, name):
    return [x for x in node if isinstance(x, list) and x and x[0] == name]


def kid(node, name):
    r = kids(node, name)
    return r[0] if r else None


def num(x):
    return float(x)


# ---------- board model ----------
class Board:
    def __init__(self, path):
        raw = Path(path).read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        root = parse_sexpr(raw.decode('utf-8'))
        if not root or root[0] != 'kicad_pcb':
            raise ValueError('not a kicad_pcb file')
        self.version = (kid(root, 'version') or [None, None])[1]
        codes = {}
        for nnode in kids(root, 'net'):                 # (net 3 "GND") in KiCad <= 9
            if len(nnode) >= 3:
                codes[nnode[1]] = nnode[2]

        def netname(node):
            nn = kid(node, 'net')
            if nn is None:
                return ''
            if len(nn) >= 3:
                return nn[2]
            return codes.get(nn[1], nn[1])              # code, or bare name in newer files

        self.pads = {}                                   # "U1.3" -> dict
        self.refs = {}                                   # ref -> dict(x,y,layer,pads)
        for fp in kids(root, 'footprint') + kids(root, 'module'):
            ref = None
            for p in kids(fp, 'property'):
                if len(p) > 2 and p[1] == 'Reference':
                    ref = p[2]
            for t in kids(fp, 'fp_text'):
                if len(t) > 2 and t[1] == 'reference':
                    ref = ref or t[2]
            if not ref:
                continue
            at = kid(fp, 'at')
            fx, fy = num(at[1]), num(at[2])
            rot = math.radians(num(at[3])) if len(at) > 3 else 0.0
            layer = (kid(fp, 'layer') or [None, 'F.Cu'])[1]
            self.refs[ref] = {'x': fx, 'y': fy, 'layer': layer, 'pads': []}
            for pad in kids(fp, 'pad'):
                pat = kid(pad, 'at')
                dx, dy = num(pat[1]), num(pat[2])
                x = fx + dx * math.cos(rot) + dy * math.sin(rot)
                y = fy - dx * math.sin(rot) + dy * math.cos(rot)
                size = kid(pad, 'size')
                layers = (kid(pad, 'layers') or [None])[1:]
                key = f'{ref}.{pad[1]}'
                rec = {'key': key, 'ref': ref, 'x': x, 'y': y, 'net': netname(pad),
                       'thru': pad[2] == 'thru_hole' or '*.Cu' in layers,
                       'layer': layer, 'r': max(num(size[1]), num(size[2])) / 2 if size else 0.3}
                self.pads.setdefault(key, rec)           # first pad wins for duplicate numbers
                self.refs[ref]['pads'].append(rec)

        self.segments = []
        for s in kids(root, 'segment') + kids(root, 'arc'):
            a, b, m = kid(s, 'start'), kid(s, 'end'), kid(s, 'mid')
            rec = {'x1': num(a[1]), 'y1': num(a[2]), 'x2': num(b[1]), 'y2': num(b[2]),
                   'w': num(kid(s, 'width')[1]), 'layer': kid(s, 'layer')[1], 'net': netname(s)}
            if m is not None:
                rec['len'] = arc_length((rec['x1'], rec['y1']), (num(m[1]), num(m[2])), (rec['x2'], rec['y2']))
            self.segments.append(rec)
        self.vias = []
        for v in kids(root, 'via'):
            at = kid(v, 'at')
            self.vias.append({'x': num(at[1]), 'y': num(at[2]), 'drill': num(kid(v, 'drill')[1]),
                              'net': netname(v)})
        self.zones = []
        for z in kids(root, 'zone'):
            nm = kid(z, 'net_name')
            name = nm[1] if nm and len(nm) > 1 else netname(z)
            fills = defaultdict(int)
            for fpoly in kids(z, 'filled_polygon'):
                fills[(kid(fpoly, 'layer') or [None, '?'])[1]] += 1
            zl = kid(z, 'layer') or kid(z, 'layers')
            self.zones.append({'net': name, 'layers': zl[1:] if zl else [], 'fills': dict(fills)})


def dist(a, b):
    return math.hypot(a['x'] - b['x'], a['y'] - b['y'])


def seg_len(s):
    return s['len'] if 'len' in s else math.hypot(s['x2'] - s['x1'], s['y2'] - s['y1'])


def arc_length(a, m, b):
    """length of the circular arc from a to b passing through m"""
    d = 2 * (a[0] * (m[1] - b[1]) + m[0] * (b[1] - a[1]) + b[0] * (a[1] - m[1]))
    if abs(d) < 1e-12:                                   # collinear: treat as two straight pieces
        return math.hypot(m[0] - a[0], m[1] - a[1]) + math.hypot(b[0] - m[0], b[1] - m[1])
    sq = lambda p: p[0] * p[0] + p[1] * p[1]
    cx = (sq(a) * (m[1] - b[1]) + sq(m) * (b[1] - a[1]) + sq(b) * (a[1] - m[1])) / d
    cy = (sq(a) * (b[0] - m[0]) + sq(m) * (a[0] - b[0]) + sq(b) * (m[0] - a[0])) / d
    r = math.hypot(a[0] - cx, a[1] - cy)
    ang = lambda p: math.atan2(p[1] - cy, p[0] - cx)
    two_pi = 2 * math.pi
    am, ab = (ang(m) - ang(a)) % two_pi, (ang(b) - ang(a)) % two_pi
    sweep = ab if am <= ab else two_pi - ab             # go the way that passes through m
    return r * sweep


def clusters(points, link):
    """single-link clustering of dicts with x,y"""
    left, out = list(points), []
    while left:
        grp, queue = [], [left.pop()]
        while queue:
            p = queue.pop(); grp.append(p)
            near = [q for q in left if dist(p, q) <= link]
            for q in near:
                left.remove(q)
            queue.extend(near)
        out.append(grp)
    return out


def chains(segs, tol=0.01):
    """group segments that touch end to end; returns list of (total_len, segs)"""
    left, out = list(segs), []
    while left:
        grp, queue = [], [left.pop()]
        while queue:
            s = queue.pop(); grp.append(s)
            ends = [(s['x1'], s['y1']), (s['x2'], s['y2'])]
            near = [t for t in left if any(math.hypot(ex - tx, ey - ty) <= tol for ex, ey in ends
                                           for tx, ty in ((t['x1'], t['y1']), (t['x2'], t['y2'])))]
            for t in near:
                left.remove(t)
            queue.extend(near)
        out.append((sum(seg_len(s) for s in grp), grp))
    return out


# ---------- audit ----------
class Audit:
    def __init__(self, board, intent, defaults):
        self.b, self.i, self.d = board, intent, defaults
        self.rows = []

    def add(self, check, rule, status, obj, measured, limit, note=''):
        self.rows.append({'check': check, 'rule_ids': rule, 'status': status, 'object': obj,
                          'measured': measured, 'limit': limit, 'note': note})

    def grade(self, value, target, review, lower_is_better=True):
        if lower_is_better:
            return 'PASS' if value <= target else ('NEEDS_REVIEW' if value <= review else 'FAIL')
        return 'PASS' if value >= target else ('NEEDS_REVIEW' if value >= review else 'FAIL')

    def pad(self, key, check):
        p = self.b.pads.get(key)
        if p is None:
            self.add(check, '', 'FAIL', key, None, None, 'pad named in intent not found on board')
        return p

    def width_for(self, amps):
        for row in self.d['track_width_by_current']['table']:
            if amps <= row['current_a_max']:
                return row['use_mm']
        return None

    def run(self):
        nets = self.i.get('nets', {})
        board_nets = {p['net'] for p in self.b.pads.values()}
        for name in nets:
            if name not in board_nets:
                self.add('INTENT', 'A01', 'FAIL', name, None, None, 'net in intent not present on board')
        self.check_widths(nets)
        self.check_vias(nets)
        self.check_net_limits(nets)
        self.check_decoupling()
        self.check_hot_loops()
        self.check_proximity()
        self.check_diff_pairs()
        self.check_reference_layer(nets)
        return self.rows

    def check_widths(self, nets):
        for name, spec in nets.items():
            amps = spec.get('current_a')
            need = spec.get('min_width_mm') or (self.width_for(amps) if amps else None)
            if amps and need is None:
                self.add('W-POWER', 'R04', 'NEEDS_REVIEW', name, None, None,
                         f'{amps} A is above the default table: needs zone + project calculation')
                continue
            if need is None:
                continue
            segs = [s for s in self.b.segments if s['net'] == name]
            if not segs:
                zoned = any(z['net'] == name for z in self.b.zones)
                self.add('W-POWER', 'R04', 'NEEDS_REVIEW' if zoned else 'FAIL', name, None, need,
                         'no tracks: carried by zone only, check zone neck width by eye' if zoned
                         else 'net has neither tracks nor zone')
                continue
            narrow = [s for s in segs if s['w'] < need - 1e-6]
            wmin = min(s['w'] for s in segs)
            if narrow:
                s = min(narrow, key=lambda q: q['w'])
                self.add('W-POWER', 'R04,R12', 'FAIL', name, wmin, need,
                         f"{len(narrow)} segment(s) below required width, e.g. at ({s['x1']:.2f},{s['y1']:.2f}) on {s['layer']}")
            else:
                self.add('W-POWER', 'R04', 'PASS', name, wmin, need)

    def check_vias(self, nets):
        dv = self.d['vias_at_layer_change']
        for name, spec in nets.items():
            amps = spec.get('current_a')
            if not amps or spec.get('class') == 'gnd':
                continue
            vias = [v for v in self.b.vias if v['net'] == name]
            for grp in clusters(vias, 2.5):
                per = dv['current_per_via_a']['drill_0.4mm' if min(v['drill'] for v in grp) >= 0.4 else 'drill_0.3mm']
                need = max(dv['min_vias_power_net'], math.ceil(amps / per - 1e-9))
                cx = sum(v['x'] for v in grp) / len(grp); cy = sum(v['y'] for v in grp) / len(grp)
                status, note = ('PASS', '') if len(grp) >= need else ('FAIL', 'too few vias where this power net changes layer')
                if status == 'PASS' and self.maybe_serial(name, grp):
                    status = 'NEEDS_REVIEW'
                    note = ('vias in this group are joined by a track on one layer only: they may be in series '
                            '(down and back up), not in parallel; check each transition by eye')
                self.add('VIA-POWER', 'R04,R08,PT12', status, f'{name} @({cx:.2f},{cy:.2f})', len(grp), need, note)

    def maybe_serial(self, name, grp):
        """True if two vias of the group are linked by a track run on exactly one layer.
        Parallel vias share copper on both layers (tracks or zones); a down-and-up jumper
        is linked on one layer only. Proximity alone cannot tell these apart."""
        by_layer = defaultdict(list)
        for s in self.b.segments:
            if s['net'] == name:
                by_layer[s['layer']].append(s)
        linked = defaultdict(set)                         # (i, j) -> layers with a direct run
        for layer, segs in by_layer.items():
            for _, run in chains(segs):
                ends = [(x, y) for s in run for x, y in ((s['x1'], s['y1']), (s['x2'], s['y2']))]
                hit = [i for i, v in enumerate(grp)
                       if any(math.hypot(v['x'] - x, v['y'] - y) <= 0.05 for x, y in ends)]
                for i in hit:
                    for j in hit:
                        if i < j:
                            linked[(i, j)].add(layer)
        return any(len(layers) == 1 for layers in linked.values())

    def check_net_limits(self, nets):
        for name, spec in nets.items():
            if 'max_vias' in spec:
                n = sum(1 for v in self.b.vias if v['net'] == name)
                self.add('NET-VIAS', 'R08,PT04', 'PASS' if n <= spec['max_vias'] else 'FAIL', name, n, spec['max_vias'])
            if 'max_length_mm' in spec:
                length = sum(seg_len(s) for s in self.b.segments if s['net'] == name)
                lim = spec['max_length_mm']
                if length == 0:
                    self.add('NET-LENGTH', 'R01', 'NEEDS_REVIEW', name, 0, lim, 'net has no tracks yet')
                else:
                    self.add('NET-LENGTH', 'R08', 'PASS' if length <= lim else 'FAIL', name, round(length, 2), lim)

    def check_decoupling(self):
        d = self.d['decoupling']
        a, g = d['smallest_cap_power_pad_to_pin_mm'], d['cap_gnd_pad_to_gnd_via_or_pin_mm']
        gnd_names = {n for n, s in self.i.get('nets', {}).items() if s.get('class') == 'gnd'}
        for item in self.i.get('decoupling', []):
            pin = self.pad(item['pin'], 'DECAP')
            cap = self.b.refs.get(item['cap'])
            if pin is None:
                continue
            if cap is None:
                self.add('DECAP', 'P04', 'FAIL', item['cap'], None, None, 'capacitor not found on board'); continue
            hot = [p for p in cap['pads'] if p['net'] == pin['net']]
            cold = [p for p in cap['pads'] if p['net'] in gnd_names]
            if not hot or not cold:
                self.add('DECAP', 'P04,A01', 'FAIL', f"{item['pin']}<-{item['cap']}", None, None,
                         'capacitor is not between this supply net and GND'); continue
            dd = min(dist(pin, p) for p in hot)
            st = self.grade(dd, item.get('target_mm', a['target']), item.get('review_mm', a['review']))
            side = '' if cap['layer'] == pin['layer'] else ' ; capacitor on the opposite side from the IC'
            if side and st == 'PASS':
                st = 'NEEDS_REVIEW'
            self.add('DECAP', 'P04,PT03', st, f"{item['pin']}<-{item['cap']}", round(dd, 2),
                     item.get('target_mm', a['target']), 'supply pad to capacitor pad' + side)
            cold_nets = {c['net'] for c in cold}
            targets = [v for v in self.b.vias if v['net'] in cold_nets]
            gp = self.b.pads.get(item.get('gnd_pin', ''))
            if gp is not None:
                if gp['net'] in cold_nets:
                    targets = targets + [gp]
                else:
                    self.add('DECAP-GND', 'P04,G01', 'FAIL', item['cap'], None, None,
                             f"gnd_pin {gp['key']} is on {gp['net']}, not the capacitor's ground net")
            pairs = [(c, t) for c in cold for t in targets if c['net'] == t['net']]
            if pairs:
                gd = min(dist(c, t) for c, t in pairs)
                self.add('DECAP-GND', 'P04,PT03', self.grade(gd, g['target'], g['review']),
                         item['cap'], round(gd, 2), g['target'], 'capacitor GND pad to nearest GND via / IC GND pin')
            else:
                self.add('DECAP-GND', 'P04', 'NEEDS_REVIEW', item['cap'], None, g['target'], 'no GND via or gnd_pin to measure to')

    def check_hot_loops(self):
        d = self.d['switching_converter']
        seg = d['hot_loop_pad_to_pad_segment_mm']
        for loop in self.i.get('hot_loops', []):
            pads = [self.pad(k, 'HOT-LOOP') for k in loop['pads']]
            if any(p is None for p in pads):
                continue
            name = loop['name']
            # consecutive pads on the same footprint are "inside the part" and are not copper
            longest, where = 0.0, ''
            for p, q in zip(pads, pads[1:] + pads[:1]):
                if p['ref'] == q['ref']:
                    continue
                dd = dist(p, q)
                if dd > longest:
                    longest, where = dd, f"{p['key']}-{q['key']}"
            tgt, rev = loop.get('target_mm', seg['target']), loop.get('review_mm', seg['review'])
            self.add('HOT-LOOP-SEG', 'P03,R03,PT02', self.grade(longest, tgt, rev), name, round(longest, 2), tgt,
                     f'longest pad-to-pad copper span is {where}')
            area = abs(sum(p['x'] * q['y'] - q['x'] * p['y'] for p, q in zip(pads, pads[1:] + pads[:1]))) / 2
            limit = loop.get('max_area_mm2')
            self.add('HOT-LOOP-AREA', 'P03,PT02', 'NA' if limit is None else ('PASS' if area <= limit else 'FAIL'),
                     name, round(area, 2), limit, 'pad-centre polygon area; compare candidates, smaller is better')
            layers = {p['layer'] for p in pads if not p['thru']}
            self.add('HOT-LOOP-LAYER', 'P03,PT02', 'PASS' if len(layers) <= 1 else 'FAIL', name, sorted(layers), 'one layer',
                     '' if len(layers) <= 1 else 'hot-loop parts are split between board sides')
            xs, ys = [p['x'] for p in pads], [p['y'] for p in pads]
            loop_nets = {p['net'] for p in pads}
            gnd_names = {n for n, s in self.i.get('nets', {}).items() if s.get('class') == 'gnd'}
            inside = [v for v in self.b.vias if v['net'] in loop_nets - gnd_names
                      and min(xs) <= v['x'] <= max(xs) and min(ys) <= v['y'] <= max(ys)]
            self.add('HOT-LOOP-VIA', 'R03,PT02', 'PASS' if not inside else 'FAIL', name, len(inside),
                     d['hot_loop_vias_allowed'], 'vias on the loop nets (GND excluded) inside the loop bounding box')
            others = [r for r, f in self.b.refs.items() if r not in {p['ref'] for p in pads}
                      and min(xs) < f['x'] < max(xs) and min(ys) < f['y'] < max(ys)]
            self.add('HOT-LOOP-CLEAR', 'PT02', 'PASS' if not others else 'NEEDS_REVIEW', name, others, [],
                     'footprints whose origin lies inside the loop bounding box')

    def check_proximity(self):
        for item in self.i.get('proximity', []):
            a, b = self.pad(item['a'], 'PROXIMITY'), self.pad(item['b'], 'PROXIMITY')
            if a is None or b is None:
                continue
            dd = dist(a, b)
            if item.get('relation', 'max') == 'min':
                st = self.grade(dd, item['target_mm'], item.get('review_mm', item['target_mm']), lower_is_better=False)
            else:
                st = self.grade(dd, item['target_mm'], item.get('review_mm', item['target_mm']))
            self.add('PROXIMITY', item.get('rule_ids', ''), st, f"{item['a']}~{item['b']}", round(dd, 2),
                     item['target_mm'], item.get('why', ''))

    def check_diff_pairs(self):
        dd = self.d['differential_pair']
        for pair in self.i.get('diff_pairs', []):
            spec = dd.get(pair.get('type', ''))
            if not isinstance(spec, dict) or 'skew_mm' not in spec:
                if all(k in pair for k in ('skew_target_mm', 'skew_review_mm', 'max_vias_per_line')):
                    spec = {'skew_mm': {'target': pair['skew_target_mm'], 'review': pair['skew_review_mm']},
                            'max_vias_per_line': pair['max_vias_per_line'],
                            'max_length_mm_review': pair.get('max_length_mm', float('inf'))}
                else:
                    self.add('DIFF-SKEW', 'R07', 'NEEDS_REVIEW', pair['name'], None, None,
                             f"no limits for pair type '{pair.get('type')}': give skew_target_mm, skew_review_mm and "
                             'max_vias_per_line in the intent from the interface/PHY specification')
                    continue
            lp = sum(seg_len(s) for s in self.b.segments if s['net'] == pair['p'])
            ln = sum(seg_len(s) for s in self.b.segments if s['net'] == pair['n'])
            vp = sum(1 for v in self.b.vias if v['net'] == pair['p'])
            vn = sum(1 for v in self.b.vias if v['net'] == pair['n'])
            if lp == 0 or ln == 0:
                self.add('DIFF-SKEW', 'R07', 'NEEDS_REVIEW', pair['name'], None, None, 'pair not routed yet'); continue
            skew = abs(lp - ln)
            self.add('DIFF-SKEW', 'R07', self.grade(skew, spec['skew_mm']['target'], spec['skew_mm']['review']),
                     pair['name'], round(skew, 2), spec['skew_mm']['target'], f'lengths {lp:.2f} / {ln:.2f} mm')
            ok = vp == vn and vp <= spec['max_vias_per_line']
            self.add('DIFF-VIAS', 'R07,R08', 'PASS' if ok else 'FAIL', pair['name'], [vp, vn],
                     spec['max_vias_per_line'], 'via count per line; both lines must match')
            self.add('DIFF-LENGTH', 'R07', 'PASS' if max(lp, ln) <= spec['max_length_mm_review'] else 'NEEDS_REVIEW',
                     pair['name'], round(max(lp, ln), 2), spec['max_length_mm_review'])

    def check_reference_layer(self, nets):
        board = self.i.get('board', {})
        ref = board.get('reference_layer')
        if not ref:
            self.add('REF-LAYER', 'R06', 'NA', 'board', None, None, 'no reference_layer declared in intent'); return
        gnd_names = {n for n, s in nets.items() if s.get('class') == 'gnd'}
        zones = [z for z in self.b.zones if z['net'] in gnd_names and ref in z['layers']]
        if not zones:
            self.add('REF-ZONE', 'R06,G02', 'FAIL', ref, 0, 1, 'no GND zone on the reference layer'); return
        islands = sum(z['fills'].get(ref, 0) for z in zones)
        lim = self.d['two_layer_reference_plane']['gnd_zone_islands_on_reference_layer']
        if islands == 0:
            self.add('REF-ZONE', 'G02,G05', 'NEEDS_REVIEW', ref, 0, 1, 'zone exists but is not filled in the file: refill and save')
        else:
            self.add('REF-ZONE', 'R06,G02', self.grade(islands, lim['target'], lim['review']), ref, islands, lim['target'],
                     'separate filled GND areas on the reference layer (1 = continuous)')
        j = self.d['two_layer_reference_plane']['jumper_length_on_reference_layer_mm']
        foreign = [s for s in self.b.segments if s['layer'] == ref and s['net'] not in gnd_names]
        worst = 'PASS'
        for length, grp in sorted(chains(foreign), key=lambda t: -t[0]):
            st = self.grade(length, j['target'], j['review'])
            if st != 'PASS':
                s = grp[0]
                self.add('REF-SLOT', 'R05,R06,PT06', st, f"{s['net']} @({s['x1']:.2f},{s['y1']:.2f})", round(length, 2),
                         j['target'], f'track run on {ref} cuts the GND reference')
                worst = st
        total = sum(seg_len(s) for s in foreign)
        self.add('REF-SLOT-TOTAL', 'R06,PT06', 'PASS' if worst == 'PASS' else 'NEEDS_REVIEW', ref, round(total, 2), None,
                 f'total non-GND track length on {ref}, in {len(chains(foreign))} run(s); lower is better')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('board', type=Path)
    ap.add_argument('intent', type=Path)
    ap.add_argument('--defaults', type=Path, default=ROOT / 'rules' / 'layout_defaults.json')
    ap.add_argument('--json', type=Path, help='write full report here')
    a = ap.parse_args()
    try:
        board = Board(a.board)
        intent = json.loads(a.intent.read_text(encoding='utf-8'))
        defaults = json.loads(a.defaults.read_text(encoding='utf-8'))
    except (OSError, ValueError, IndexError, TypeError) as e:
        print(f'input error: {e}', file=sys.stderr)
        raise SystemExit(2)
    rows = Audit(board, intent, defaults).run()
    counts = defaultdict(int)
    for r in rows:
        counts[r['status']] += 1
    order = {'FAIL': 0, 'NEEDS_REVIEW': 1, 'PASS': 2, 'NA': 3}
    for r in sorted(rows, key=lambda r: order[r['status']]):
        print(f"{r['status']:<12} {r['check']:<15} {str(r['object']):<34} measured={r['measured']} limit={r['limit']}  {r['note']}")
    summary = {'board': str(a.board), 'board_sha256': board.sha256, 'kicad_file_version': board.version,
               'intent_sha256': hashlib.sha256(a.intent.read_bytes()).hexdigest(),
               'defaults_sha256': hashlib.sha256(a.defaults.read_bytes()).hexdigest(),
               'counts': dict(counts),
               'disclaimer': 'Geometry audit only. Not a substitute for KiCad ERC/DRC or electrical review.'}
    print(json.dumps(summary, indent=2))
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps({'summary': summary, 'results': rows}, indent=2, ensure_ascii=False), encoding='utf-8')
    raise SystemExit(1 if counts['FAIL'] else 0)


if __name__ == '__main__':
    main()
