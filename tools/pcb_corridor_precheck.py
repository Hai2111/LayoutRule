#!/usr/bin/env python3
"""Candidate straight-line pad-to-pad corridor precheck for KiCad F.Cu footprints.

Output POTENTIAL_CONGESTION only: it is NOT a routing feasibility decision.
Only approximates footprint pads as axis-aligned envelopes, ignoring copper zones,
existing traces, keepouts, mounting holes and B.Cu footprint mirroring.
"""
import argparse
import json
import math
from pathlib import Path
from pcb_ref_extract import parse_board


def global_pad(fp, pad):
    dx, dy = pad['local_xy_mm']
    a = math.radians(fp['rotation_deg'])
    x, y = fp['xy_mm']
    return (x + dx * math.cos(a) + dy * math.sin(a),
            y - dx * math.sin(a) + dy * math.cos(a))


def pad_bbox(fp, pad, inflate):
    x, y = global_pad(fp, pad)
    width, height = pad['size_mm']
    theta = math.radians(fp['rotation_deg'] + pad.get('local_rotation_deg', 0))
    hw = (abs(math.cos(theta)) * width + abs(math.sin(theta)) * height)/2 + inflate
    hh = (abs(math.sin(theta)) * width + abs(math.cos(theta)) * height)/2 + inflate
    return (x-hw, y-hh, x+hw, y+hh)


def segment_intersects_aabb(start, end, bbox):
    x, y = start
    dx, dy = end[0]-x, end[1]-y
    xmin, ymin, xmax, ymax = bbox
    tmin, tmax = 0.0, 1.0
    for p, q in [(-dx, x-xmin), (dx, xmax-x), (-dy, y-ymin), (dy, ymax-y)]:
        if abs(p) < 1e-12:
            if q < 0:
                return False
        else:
            t = q/p
            if p < 0:
                tmin = max(tmin, t)
            else:
                tmax = min(tmax, t)
            if tmin > tmax:
                return False
    return True


def precheck(text, from_ref, from_pad, to_ref, to_pad, trace_width_mm, clearance_mm):
    if min(trace_width_mm, clearance_mm) < 0:
        raise ValueError('Trace width and clearance must be nonnegative')
    fps, _, _, _ = parse_board(text)
    pair = []
    for ref, number in ((from_ref, from_pad), (to_ref, to_pad)):
        fp = fps[ref]
        if fp['layer'] != 'F.Cu':
            raise ValueError('Only F.Cu footprint transform supported: '+ref)
        pad = next(p for p in fp['pads'] if p['number'] == number)
        pair.append((fp, pad, global_pad(fp, pad)))
    if not pair[0][1]['net'] or pair[0][1]['net'] != pair[1][1]['net']:
        raise ValueError('Source and destination pads must have the same named net')
    net = pair[0][1]['net']
    start, end = pair[0][2], pair[1][2]
    overlap = []
    pad_margin = trace_width_mm/2 + clearance_mm
    for ref, fp in fps.items():
        if fp['layer'] != 'F.Cu':
            continue
        for pad in fp['pads']:
            if (ref, pad['number']) in ((from_ref, from_pad), (to_ref, to_pad)):
                continue
            if pad['net'] == net or pad['size_mm'] is None or pad['local_xy_mm'] is None:
                continue
            rect = pad_bbox(fp, pad, pad_margin)
            if segment_intersects_aabb(start, end, rect):
                overlap.append({'ref':ref, 'pad':pad['number'], 'net':pad['net'],
                                'bbox_mm':[round(v,4) for v in rect]})
    return {'status': 'POTENTIAL_CONGESTION' if overlap else 'NO_PAD_ENVELOPE_HIT',
            'net': net, 'from':f'{from_ref}:{from_pad}', 'to':f'{to_ref}:{to_pad}',
            'direct_pad_center_distance_mm': round(math.dist(start,end), 4),
            'straight_line_from_mm': [round(v,4) for v in start],
            'straight_line_to_mm':[round(v,4) for v in end],
            'clearance_assumption_mm':clearance_mm,
            'trace_width_assumption_mm':trace_width_mm,
            'intersected_unrelated_pad_envelopes':overlap,
            'limitations':['Straight-line hypothesis, not actual routed path',
                           'F.Cu pad envelope only (conservative AABB for rotated pads)',
                           'No zone, keepout, existing route, DRC or continuity check',
                           'No automatic relocation decision or numeric universal threshold']}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('pcb')
    ap.add_argument('--from-ref',required=True)
    ap.add_argument('--from-pad',required=True)
    ap.add_argument('--to-ref',required=True)
    ap.add_argument('--to-pad',required=True)
    ap.add_argument('--trace-width-mm',required=True,type=float)
    ap.add_argument('--clearance-mm',required=True,type=float)
    args=ap.parse_args()
    result=precheck(Path(args.pcb).read_text(encoding='utf-8-sig'),args.from_ref,args.from_pad,
                    args.to_ref,args.to_pad,args.trace_width_mm,args.clearance_mm)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
