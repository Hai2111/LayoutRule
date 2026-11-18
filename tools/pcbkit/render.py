"""Matplotlib render of a Board for self-review and before/after comparison (not a KiCad screenshot).
Pads coloured by net, F.Cu tracks solid / B.Cu dotted, vias (highlighted ones green), non-GND zones, courtyards, refs, mm grid.
For the real copper (zone fills) use `kicad-cli pcb export svg` / `pcb render` (see CLAUDE.md 9A).

    python -m pcbkit render board.kicad_pcb out.png [--region x0,y0,x1,y1]
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Polygon
from .board import F


def render(b, out, title='', highlight=(), region=None, copper=True, size=17):
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
