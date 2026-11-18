"""Whole-board text transforms.

translate(src, out, dx, dy)          move every absolute coordinate (footprint `at`, tracks, vias, zones, gr_*, dimensions);
                                     footprint-internal geometry is relative and is left alone
set_origin(src, out, x, y)           aux (drill/place) origin + grid origin
center_on_sheet(src, out)            translate so the outline centre = sheet centre, origin = board bottom-left
rename_project(folder, old, new)     rename .kicad_pro/.kicad_sch/.kicad_pcb/.kicad_prl and the name inside them
"""
import os, re
from .sexpr import fnum, parse, kid
from .board import Board

SHIFT = {'at', 'start', 'end', 'mid', 'center', 'xy'}
SHEETS = {'A4': (297, 210), 'A3': (420, 297), 'A5': (210, 148), 'USLetter': (279.4, 215.9)}
_TOK = re.compile(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+')


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
