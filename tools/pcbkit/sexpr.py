"""Minimal KiCad s-expression reader: parse() -> nested lists of strings; kids()/kid() helpers; blocks() for text edits."""
import re

_TOK = re.compile(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+')


def parse(text):
    """Parse an s-expression into nested lists. Quoted strings are unquoted."""
    stack, cur = [], []
    for m in _TOK.finditer(text):
        t = m.group()
        if t == '(':
            stack.append(cur); cur = []
        elif t == ')':
            done = cur; cur = stack.pop(); cur.append(done)
        else:
            cur.append(t[1:-1].replace('\\"', '"') if t[0] == '"' else t)
    return cur[0] if cur else []


def kids(node, tag):
    """Direct children lists whose head is `tag`."""
    return [c for c in node if isinstance(c, list) and c and c[0] == tag]


def kid(node, tag):
    """First direct child with head `tag`, or None."""
    for c in node:
        if isinstance(c, list) and c and c[0] == tag:
            return c
    return None


def blocks(text, head):
    """(start, end) spans of every top-level block starting with `head` (e.g. '\\t(segment\\n'), end includes newline."""
    out, i = [], 0
    while True:
        i = text.find(head, i)
        if i < 0:
            return out
        d, j = 0, i + head.index('(')
        while True:
            c = text[j]
            if c == '"':
                j = text.index('"', j + 1)
                while text[j - 1] == '\\':
                    j = text.index('"', j + 1)
            elif c == '(':
                d += 1
            elif c == ')':
                d -= 1
                if d == 0:
                    break
            j += 1
        end = j + 1
        if text[end:end + 1] == '\n':
            end += 1
        out.append((i, end)); i = end


def fnum(v):
    """Format a float the way KiCad does (no trailing zeros)."""
    s = '%.6f' % v
    s = s.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s
