"""Write a Board back to .kicad_pcb by editing the original text (everything not touched is kept byte-for-byte).

write(b, out)                       moved footprints + replace ALL tracks/vias with b.segs/b.vias, drop zone fills
write(b, out, copper='append')      keep existing tracks/vias, append only b.segs/b.vias (use for stitching vias)
Zone fills are removed (KiCad refills with B or `kicad-cli pcb drc --refill-zones`).
"""
import re, uuid
from .sexpr import blocks, fnum
from .board import F


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
