#!/usr/bin/env python3
"""Static metadata extractor for KiCad 5/9/10 .kicad_pcb files.

Evidence only: does not run ERC/DRC, trace continuity, zone fill, impedance,
return-current, thermal or EMI analysis. Input may be a work-in-progress board.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

NET_RE = re.compile(r'\(net\s+(?:(\d+)\s+)?(?:"([^"]+)"|([^\s()]+))\)')
AT_RE = re.compile(r'\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)')
XY_RE = lambda key: re.compile(r'\(' + key + r'\s+([-\d.]+)\s+([-\d.]+)\)')


def forms(src, allowed=None):
    """Return direct children of an S-expression, respecting quoted strings."""
    depth = 0
    quoted = escaped = False
    start = -1
    kind = ''
    for i, ch in enumerate(src):
        if quoted:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                quoted = False
            continue
        if ch == '"':
            quoted = True
        elif ch == '(':
            if depth == 1:
                m = re.match(r'[^\s()]+', src[i + 1:i + 80])
                kind = m.group(0) if m else ''
                start = i if allowed is None or kind in allowed else -1
            depth += 1
        elif ch == ')':
            if depth == 2 and start >= 0:
                yield kind, src[start:i + 1]
                start = -1
            depth -= 1
            if depth < 0:
                raise ValueError('Unbalanced KiCad S-expression')
    if depth != 0 or quoted:
        raise ValueError('Truncated KiCad S-expression')


def net_of(s, net_ids):
    m = NET_RE.search(s)
    if not m:
        numeric_only = re.search(r'\(net\s+(\d+)\)', s)
        return net_ids.get(numeric_only.group(1)) if numeric_only else None
    if m.group(1):
        return m.group(2) or m.group(3) or net_ids.get(m.group(1))
    if m.group(3) in net_ids:
        return net_ids[m.group(3)]
    return m.group(2) or m.group(3)


def parse_board(src):
    top = list(forms(src, {'net', 'footprint', 'module', 'segment', 'via', 'zone'}))
    net_ids = {}
    for typ, item in top:
        if typ == 'net':
            m = NET_RE.search(item)
            if m and m.group(1):
                net_ids[m.group(1)] = m.group(2) or m.group(3)
    fps, tracks, vias, zones = {}, [], [], 0
    for typ, item in top:
        if typ in ('footprint', 'module'):
            m = AT_RE.search(item)
            ref = (re.search(r'\(property\s+"Reference"\s+"([^"]+)"', item) or
                   re.search(r'\(fp_text\s+reference\s+(?:"([^"]+)"|([^\s()]+))', item))
            val = (re.search(r'\(property\s+"Value"\s+"([^"]+)"', item) or
                   re.search(r'\(fp_text\s+value\s+(?:"([^"]+)"|([^\s()]+))', item))
            if not (m and ref):
                continue
            rid = next((v for v in ref.groups() if v is not None), None)
            fp_layer = re.search(r'\(layer\s+"?([^\s")]+)', item)
            pads = []
            for ptype, pad in forms(item, {'pad'}):
                pad_no = re.match(r'\(pad\s+(?:"([^"]+)"|([^\s()]+))', pad)
                loc = AT_RE.search(pad)
                size = re.search(r'\(size\s+([-\d.]+)\s+([-\d.]+)\)', pad)
                pads.append({'number': (pad_no.group(1) or pad_no.group(2)) if pad_no else None,
                             'net': net_of(pad, net_ids),
                             'local_xy_mm': [float(loc.group(1)), float(loc.group(2))] if loc else None,
                             'local_rotation_deg': float(loc.group(3) or 0) if loc else 0,
                             'size_mm': [float(size.group(1)), float(size.group(2))] if size else None})
            fps[rid] = {'value': next((v for v in val.groups() if v is not None), None) if val else None,
                        'layer': fp_layer.group(1) if fp_layer else None,
                        'xy_mm': [float(m.group(1)), float(m.group(2))],
                        'rotation_deg': float(m.group(3) or 0),
                        'pad_count': len(pads), 'pads': pads}
        elif typ == 'segment':
            a = XY_RE('start').search(item)
            b = XY_RE('end').search(item)
            layer = re.search(r'\(layer\s+"?([^\s")]+)', item)
            width = re.search(r'\(width\s+([-\d.]+)\)', item)
            if not a or not b:
                continue
            tracks.append({'net': net_of(item, net_ids),
                           'layer': layer.group(1) if layer else None,
                           'width_mm': float(width.group(1)) if width else None,
                           'length_mm': math.hypot(float(a.group(1))-float(b.group(1)),
                                                   float(a.group(2))-float(b.group(2)))})
        elif typ == 'via':
            vias.append({'net': net_of(item, net_ids)})
        elif typ == 'zone':
            zones += 1
    return fps, tracks, vias, zones


def report(pcb, requested_refs, requested_nets):
    raw = Path(pcb).read_bytes()
    fps, tracks, vias, zones = parse_board(raw.decode('utf-8-sig'))
    nets = sorted(requested_nets or {t['net'] for t in tracks if t['net']})
    stats = {}
    for net in nets:
        items = [t for t in tracks if t['net'] == net]
        stats[net] = {'segment_count': len(items),
                      'total_copper_segment_length_mm': round(sum(t['length_mm'] for t in items), 3),
                      'via_count': sum(v['net'] == net for v in vias),
                      'layers': sorted({t['layer'] for t in items if t['layer']}),
                      'min_segment_width_mm': min((t['width_mm'] for t in items if t['width_mm'] is not None), default=None)}
    return {'source_path': str(pcb), 'sha256': hashlib.sha256(raw).hexdigest(),
            'footprints': len(fps), 'track_segments': len(tracks),
            'via_count': len(vias), 'zone_objects': zones,
            'has_saved_tracks': bool(tracks),
            'selected_footprints': {r: fps.get(r) for r in requested_refs},
            'net_statistics': stats,
            'evidence_limitations': ['No KiCad ERC/DRC executed', 'No zone-fill/electrical continuity evaluated',
                                    'Summed segment length is NOT endpoint-to-endpoint length when nets branch',
                                    'No proof of layout electrical quality or manufacturing readiness']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('pcb', help='KiCad .kicad_pcb input file')
    p.add_argument('--ref', action='append', default=[], help='Reference designator to include (repeatable)')
    p.add_argument('--net', action='append', default=[], help='Named net to measure (repeatable)')
    p.add_argument('--output', help='Optional JSON file path')
    args = p.parse_args()
    data = json.dumps(report(args.pcb, args.ref, args.net), ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(data + '\n', encoding='utf-8')
    else:
        print(data)


if __name__ == '__main__':
    main()
