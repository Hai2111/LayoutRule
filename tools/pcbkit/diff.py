"""What changed between two boards (use every time the owner saved the board):
footprints moved/rotated, tracks added/removed per net+layer (count, mm), vias added/removed, zones, origin.
Coordinates of `b` can be shifted back with offset=(dx, dy) when one board was translated.

    python -m pcbkit diff old.kicad_pcb new.kicad_pcb
"""
import collections, math
from .board import Board


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
