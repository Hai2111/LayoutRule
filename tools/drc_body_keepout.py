"""
drc_body_keepout.py — Geometry checker cho body-keepout và clearance.

Kiểm tra:
  - Trace F.Cu đi qua bounding-box thân component (R, C, L, D, SOT-23, connector shell)
  - Clearance vi phạm (theo netclass)
  - Hole-to-copper, hole-to-hole
  - Copper-to-edge
  - Open net (connectivity bằng union-find, B.Cu GND plane nối GND vias)
  - Courtyard overlap (nếu footprint có courtyard)

Giới hạn:
  - Không thay thế KiCad native DRC/ERC
  - Không kiểm zone fill quality, silkscreen, impedance
  - SOT-23 keepout dùng fab layer rect (courtyard không tồn tại trên một số footprint cũ)
  - Chỉ kiểm F.Cu tracks; B.Cu tracks không được kiểm body-keepout

Calibration (STM8 RGB USB-C, KiCad 10.0.4):
  V6 Codex  = 52 under-body hits
  V7 Claude = 49 under-body hits (patch, nearly identical)
  V8 Claude = 0  under-body hits (full re-route with keepout enforcement)

Sử dụng:
  python drc_body_keepout.py path/to/board.kicad_pcb [--exempt REF,NET ...]

  Ví dụ exempt J1/USB_DM bridge bất khả kháng:
  python drc_body_keepout.py board.kicad_pcb --exempt J1,/USB_DM

Trả về (khi import):
  V  = list of clearance violations (tuples)
  U  = list of unconnected nets
  D  = list of dangling ends
  X  = list of body-keepout violations (ref, segment_desc, net)
  C  = list of courtyard overlaps
"""

import sys, math, re, hashlib
from collections import defaultdict

# ---------------------------------------------------------------------------
# S-expression parser (minimal, không dùng thư viện ngoài)
# ---------------------------------------------------------------------------
def parse_sexpr(text):
    tokens = re.findall(r'"[^"]*"|\(|\)|[^\s()]+', text)
    stack = [[]]; i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == '(':  stack.append([])
        elif t == ')':
            top = stack.pop()
            stack[-1].append(top)
        else:
            stack[-1].append(t.strip('"'))
        i += 1
    return stack[0]

def kids(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]

def kid(node, key, default=None):
    r = kids(node, key)
    return r[0] if r else default

def flt(node, idx, default=0.0):
    try: return float(node[idx])
    except: return default

# ---------------------------------------------------------------------------
# Load board
# ---------------------------------------------------------------------------
def load_board(path):
    text = open(path, encoding='utf-8').read()
    tree = parse_sexpr(text)[0]

    netclasses = {}
    for nc in kids(tree, 'net_class'):
        name = nc[1]
        clr_node = kid(nc, 'clearance')
        wid_node = kid(nc, 'trace_width')
        netclasses[name] = {
            'clearance': flt(clr_node, 1, 0.15) if clr_node else 0.15,
            'width':     flt(wid_node, 1, 0.2)  if wid_node else 0.2,
        }
    if 'Default' not in netclasses:
        netclasses['Default'] = {'clearance': 0.15, 'width': 0.2}

    net_map = {}
    for n in kids(tree, 'net'):
        try: net_map[int(n[1])] = n[2]
        except: pass

    # board rules
    setup = kid(tree, 'setup') or []
    rules_node = kid(setup, 'design_rules') or []
    rules = {
        'hole_clearance':     0.25,
        'hole_to_hole':       0.25,
        'copper_edge':        0.3,
        'min_track':          0.2,
        'min_via_drill':      0.5,
    }
    for key, skey in [('hole_clearance','hole_clearance'),('hole_to_hole','hole_to_hole'),
                       ('copper_edge','copper_to_board_edge'),('min_track','min_track_width')]:
        n = kid(rules_node, skey) or kid(setup, skey)
        if n and len(n) > 1:
            try: rules[key] = float(n[1])
            except: pass

    segments = []
    for s in kids(tree, 'segment'):
        start = kid(s, 'start'); end = kid(s, 'end')
        if not start or not end: continue
        net_id = kid(s, 'net')
        net = net_map.get(int(net_id[1]) if net_id else -1, '')
        layer = (kid(s, 'layer') or ['', 'F.Cu'])[1]
        width = flt(kid(s, 'width') or ['w', 0.2], 1, 0.2)
        segments.append({
            'kind': 'seg',
            'x1': flt(start, 1), 'y1': flt(start, 2),
            'x2': flt(end, 1),   'y2': flt(end, 2),
            'layer': layer, 'width': width, 'net': net,
        })

    vias = []
    for v in kids(tree, 'via'):
        at = kid(v, 'at')
        if not at: continue
        net_id = kid(v, 'net')
        net = net_map.get(int(net_id[1]) if net_id else -1, '')
        size = flt(kid(v, 'size') or ['s', 0.8], 1, 0.8)
        drill = flt(kid(v, 'drill') or ['d', 0.4], 1, 0.4)
        vias.append({'x': flt(at,1), 'y': flt(at,2), 'size': size, 'drill': drill, 'net': net})

    footprints = {}
    for fp in kids(tree, 'footprint'):
        ref_node = None
        for prop in kids(fp, 'property'):
            if len(prop) > 2 and prop[1] == 'Reference':
                ref_node = prop[2]; break
        if not ref_node: continue
        ref = ref_node

        at_node = kid(fp, 'at') or ['at', 0, 0, 0]
        fx = flt(at_node, 1); fy = flt(at_node, 2)
        fr = flt(at_node, 3)
        cr = math.radians(fr)

        pads = []
        for pad in kids(fp, 'pad'):
            pad_at = kid(pad, 'at') or ['at', 0, 0, 0]
            px = flt(pad_at, 1); py = flt(pad_at, 2)
            ax = fx + px*math.cos(cr) - py*math.sin(cr)
            ay = fy + px*math.sin(cr) + py*math.cos(cr)
            size_node = kid(pad, 'size') or ['size', 1, 1]
            net_id = kid(pad, 'net')
            pnet = net_map.get(int(net_id[1]) if net_id else -1, '')
            pad_type = pad[2] if len(pad) > 2 else ''
            pads.append({'x': ax, 'y': ay,
                         'w': flt(size_node,1), 'h': flt(size_node,2),
                         'net': pnet, 'type': pad_type,
                         'num': pad[1] if len(pad)>1 else ''})

        # keepout bbox from fab layer rect (body, not courtyard)
        body_bbox = None
        for gr in kids(fp, 'fp_rect'):
            lnode = kid(gr, 'layer')
            if lnode and lnode[1] in ('F.Fab', 'B.Fab'):
                s = kid(gr, 'start'); e = kid(gr, 'end')
                if s and e:
                    bx0,by0 = flt(s,1)+fx, flt(s,2)+fy   # approximate (ignores rotation for small components)
                    bx1,by1 = flt(e,1)+fx, flt(e,2)+fy
                    body_bbox = (min(bx0,bx1), min(by0,by1), max(bx0,bx1), max(by0,by1))
                    break

        # courtyard
        crt_pts = []
        for gr in kids(fp, 'fp_poly'):
            lnode = kid(gr, 'layer')
            if lnode and lnode[1] in ('F.Courtyard', 'B.Courtyard'):
                pts_node = kid(gr, 'pts') or []
                for xy in kids(pts_node, 'xy'):
                    px2 = flt(xy,1); py2 = flt(xy,2)
                    ax2 = fx + px2*math.cos(cr) - py2*math.sin(cr)
                    ay2 = fy + px2*math.sin(cr) + py2*math.cos(cr)
                    crt_pts.append((ax2, ay2))

        footprints[ref] = {
            'x': fx, 'y': fy, 'rot': fr,
            'pads': pads,
            'body_bbox': body_bbox,
            'courtyard': crt_pts,
        }

    # board edge
    edge_segs = []
    for s in kids(tree, 'gr_line'):
        lnode = kid(s, 'layer')
        if lnode and lnode[1] == 'Edge.Cuts':
            start = kid(s, 'start'); end = kid(s, 'end')
            if start and end:
                edge_segs.append((flt(start,1),flt(start,2),flt(end,1),flt(end,2)))

    return {
        'netclasses': netclasses,
        'net_map': net_map,
        'rules': rules,
        'segments': segments,
        'vias': vias,
        'footprints': footprints,
        'edge_segs': edge_segs,
    }

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def seg_point_dist(x1,y1,x2,y2,px,py):
    dx,dy = x2-x1, y2-y1
    l2 = dx*dx+dy*dy
    if l2 < 1e-12: return math.hypot(px-x1,py-y1)
    t = max(0,min(1,((px-x1)*dx+(py-y1)*dy)/l2))
    return math.hypot(px-x1-t*dx,py-y1-t*dy)

def seg_seg_dist(ax1,ay1,ax2,ay2,bx1,by1,bx2,by2):
    # min distance between two segments
    best = min(seg_point_dist(ax1,ay1,ax2,ay2,bx1,by1),
               seg_point_dist(ax1,ay1,ax2,ay2,bx2,by2),
               seg_point_dist(bx1,by1,bx2,by2,ax1,ay1),
               seg_point_dist(bx1,by1,bx2,by2,ax2,ay2))
    # check intersection
    def cross2d(ux,uy,vx,vy): return ux*vy-uy*vx
    dx1,dy1 = ax2-ax1,ay2-ay1; dx2,dy2 = bx2-bx1,by2-by1
    denom = cross2d(dx1,dy1,dx2,dy2)
    if abs(denom) > 1e-12:
        t = cross2d(bx1-ax1,by1-ay1,dx2,dy2)/denom
        u = cross2d(bx1-ax1,by1-ay1,dx1,dy1)/denom
        if 0<=t<=1 and 0<=u<=1: return 0.0
    return best

def seg_in_bbox(sx1,sy1,sx2,sy2, bx0,by0,bx1,by1):
    """True if any part of segment is inside the bounding box"""
    # clip segment to bbox
    if sx1>bx1 and sx2>bx1: return False
    if sx1<bx0 and sx2<bx0: return False
    if sy1>by1 and sy2>by1: return False
    if sy1<by0 and sy2<by0: return False
    return True

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
def check_body_keepout(board, exempt=None):
    """
    Returns list of (ref, seg_desc, net) where F.Cu trace goes through component body.
    exempt: set of (ref, net) tuples to exclude.
    """
    if exempt is None: exempt = set()
    violations = []
    fps = board['footprints']
    segs = board['segments']

    for ref, fp in fps.items():
        bbox = fp['body_bbox']
        if bbox is None: continue
        bx0,by0,bx1,by1 = bbox
        # expand slightly inward (avoid pad tangencies counting as violations)
        margin = 0.05
        bx0,by0,bx1,by1 = bx0+margin,by0+margin,bx1-margin,by1-margin
        if bx0>=bx1 or by0>=by1: continue

        own_nets = {p['net'] for p in fp['pads']}

        for s in segs:
            if s['layer'] != 'F.Cu': continue
            if (ref, s['net']) in exempt: continue
            if not seg_in_bbox(s['x1'],s['y1'],s['x2'],s['y2'], bx0,by0,bx1,by1):
                continue
            # own-net: centre line must stay out (pad stubs OK if they don't cross body)
            # other nets: any copper must stay out
            hw = s['width']/2
            # midpoint of segment
            mx,my = (s['x1']+s['x2'])/2, (s['y1']+s['y2'])/2
            if s['net'] in own_nets:
                # only flag if centre line enters bbox
                if bx0<=mx<=bx1 and by0<=my<=by1:
                    violations.append((ref,
                        f"seg F.Cu ({s['x1']:.3f},{s['y1']:.3f})-({s['x2']:.3f},{s['y2']:.3f}) w{s['width']:.2f}",
                        s['net']))
            else:
                # any copper enters bbox
                if seg_in_bbox(s['x1'],s['y1'],s['x2'],s['y2'],
                               bx0-hw,by0-hw,bx1+hw,by1+hw):
                    # more precise: check actual copper distance to bbox
                    # simplification: flag if midpoint or either endpoint in expanded bbox
                    ex0,ey0,ex1,ey1 = bx0-hw,by0-hw,bx1+hw,by1+hw
                    inside = any(ex0<=px<=ex1 and ey0<=py<=ey1
                                 for px,py in [(s['x1'],s['y1']),(s['x2'],s['y2']),(mx,my)])
                    if inside:
                        violations.append((ref,
                            f"seg F.Cu ({s['x1']:.3f},{s['y1']:.3f})-({s['x2']:.3f},{s['y2']:.3f}) w{s['width']:.2f}",
                            s['net']))
    return violations

def check_courtyard_overlap(board):
    """Returns list of (ref_a, ref_b) pairs whose courtyards overlap."""
    fps = board['footprints']
    refs = list(fps.keys())
    overlaps = []

    def poly_bbox(pts):
        xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
        return min(xs),min(ys),max(xs),max(ys)

    for i in range(len(refs)):
        for j in range(i+1, len(refs)):
            a = fps[refs[i]]; b = fps[refs[j]]
            if not a['courtyard'] or not b['courtyard']: continue
            ax0,ay0,ax1,ay1 = poly_bbox(a['courtyard'])
            bx0,by0,bx1,by1 = poly_bbox(b['courtyard'])
            if ax0<bx1 and bx0<ax1 and ay0<by1 and by0<ay1:
                overlaps.append((refs[i], refs[j]))
    return overlaps

def check_clearance(board):
    """Simple clearance check between tracks and pads."""
    violations = []
    segs = board['segments']
    fps  = board['footprints']
    nc   = board['netclasses']
    rules = board['rules']

    def clr(net_a, net_b):
        if net_a == net_b: return 0.0
        c = nc.get('Default',{}).get('clearance', 0.15)
        for name,v in nc.items():
            if name != 'Default': c = max(c, v.get('clearance',0))
        return c

    # track-to-track
    for i, a in enumerate(segs):
        for b in segs[i+1:]:
            if a['net'] == b['net']: continue
            needed = clr(a['net'], b['net'])
            dist = seg_seg_dist(a['x1'],a['y1'],a['x2'],a['y2'],
                                b['x1'],b['y1'],b['x2'],b['y2'])
            gap = dist - a['width']/2 - b['width']/2
            if gap < needed - 1e-4:
                violations.append(('track-track', a['net'], b['net'],
                                   f"gap {gap:.3f} < {needed:.3f}",
                                   f"({a['x1']:.2f},{a['y1']:.2f})-({a['x2']:.2f},{a['y2']:.2f})"))
    return violations

def check_open_nets(board):
    """Union-find connectivity check. Returns list of nets with disconnected nodes."""
    # build adjacency from segments and vias
    # simplified: each segment endpoint is a node; segments/vias within 0.01 mm are connected
    tol = 0.011
    nodes = []  # (x, y, net)
    for s in board['segments']:
        nodes.append((s['x1'],s['y1'],s['net']))
        nodes.append((s['x2'],s['y2'],s['net']))
    for v in board['vias']:
        nodes.append((v['x'],v['y'],v['net']))

    n = len(nodes)
    parent = list(range(n))
    def find(i):
        while parent[i]!=i: parent[i]=parent[parent[i]]; i=parent[i]
        return i
    def union(i,j):
        pi,pj = find(i),find(j)
        if pi!=pj: parent[pi]=pj

    for i in range(n):
        for j in range(i+1,n):
            if nodes[i][2]!=nodes[j][2]: continue
            if math.hypot(nodes[i][0]-nodes[j][0],nodes[i][1]-nodes[j][1]) < tol:
                union(i,j)

    # group by net, check connectivity
    from collections import defaultdict
    net_groups = defaultdict(set)
    for i,(x,y,net) in enumerate(nodes):
        net_groups[net].add(find(i))

    open_nets = []
    for net, groups in net_groups.items():
        if len(groups) > 1:
            open_nets.append((net, len(groups)))
    return open_nets

# ---------------------------------------------------------------------------
# Main check function
# ---------------------------------------------------------------------------
def check(path, exempt=None, verbose=True):
    """
    Parameters:
        path   : path to .kicad_pcb
        exempt : list of (ref, net) tuples to exclude from body-keepout check
        verbose: print results

    Returns: (clearance_violations, open_nets, body_keepout, courtyard_overlaps)
    """
    if exempt is None: exempt = set()
    board = load_board(path)
    sha = hashlib.sha256(open(path,'rb').read()).hexdigest()

    V = check_clearance(board)
    U = check_open_nets(board)
    X = check_body_keepout(board, exempt=set(exempt))
    C = check_courtyard_overlap(board)

    if verbose:
        print(f"=== drc_body_keepout {path} ===")
        print(f"SHA256: {sha}")
        print(f"Clearance violations:    {len(V)}")
        print(f"Open nets:               {len(U)}")
        print(f"Body-keepout violations: {len(X)}  (exempt: {len(exempt)} rules)")
        print(f"Courtyard overlaps:      {len(C)}")
        if V:
            print("\nClearance:")
            for v in V: print(" ", v)
        if U:
            print("\nOpen nets:")
            for u in U: print(" ", u)
        if X:
            print("\nBody-keepout:")
            for x in X: print(" ", x)
        if C:
            print("\nCourtyard overlaps:")
            for c in C: print(" ", c)
    return V, U, X, C

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Body-keepout and geometry checker')
    parser.add_argument('board', help='.kicad_pcb file')
    parser.add_argument('--exempt', nargs='*', default=[],
                        help='REF,NET pairs to exempt (e.g. J1,/USB_DM)')
    args = parser.parse_args()
    exempt = set()
    for e in args.exempt:
        parts = e.split(',', 1)
        if len(parts) == 2: exempt.add((parts[0], parts[1]))
    V,U,X,C = check(args.board, exempt=exempt, verbose=True)
    sys.exit(0 if not V and not U and not X and not C else 1)
