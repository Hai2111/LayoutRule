"""CLI:
  python -m pcbkit check   BOARD [--exempt REF,NET ...]
  python -m pcbkit render  BOARD OUT.png [--region x0,y0,x1,y1] [--title T]
  python -m pcbkit diff    OLD NEW [--offset dx,dy]
  python -m pcbkit stitch  BOARD OUT [--fence /+5V,/USB_DP,/USB_DM] [--cover 3.5] [--pitch 2.5]
  python -m pcbkit center  BOARD OUT [--origin bottom-left|top-left|center]
  python -m pcbkit origin  BOARD OUT X Y
  python -m pcbkit rename  FOLDER OLD NEW [--title T --date D --rev R --comment C]
"""
import argparse, json, sys
from . import Board, check, render, diff, transform
from .stitch import apply as stitch_apply


def main(argv=None):
    ap = argparse.ArgumentParser(prog='pcbkit'); sp = ap.add_subparsers(dest='cmd', required=True)
    c = sp.add_parser('check'); c.add_argument('board'); c.add_argument('--exempt', nargs='*', default=[]); c.add_argument('--json')
    r = sp.add_parser('render'); r.add_argument('board'); r.add_argument('out'); r.add_argument('--region'); r.add_argument('--title', default='')
    d = sp.add_parser('diff'); d.add_argument('old'); d.add_argument('new'); d.add_argument('--offset', default='0,0')
    s = sp.add_parser('stitch'); s.add_argument('board'); s.add_argument('out'); s.add_argument('--fence', default='/+5V')
    s.add_argument('--cover', type=float, default=3.5); s.add_argument('--pitch', type=float, default=2.5); s.add_argument('--net', default='/GND')
    ce = sp.add_parser('center'); ce.add_argument('board'); ce.add_argument('out'); ce.add_argument('--origin', default='bottom-left')
    o = sp.add_parser('origin'); o.add_argument('board'); o.add_argument('out'); o.add_argument('x', type=float); o.add_argument('y', type=float)
    rn = sp.add_parser('rename'); rn.add_argument('folder'); rn.add_argument('old'); rn.add_argument('new')
    for k in ('title', 'date', 'rev', 'comment'):
        rn.add_argument('--' + k)
    a = ap.parse_args(argv)
    if a.cmd == 'check':
        res = check(a.board, exempt=[tuple(x.split(',', 1)) for x in a.exempt])
        if a.json:
            json.dump(res, open(a.json, 'w'), indent=1, default=str)
        return 1 if (res['violations'] or res['under_body'] or res['courtyard'] or res['dangling']) else 0
    if a.cmd == 'render':
        b = Board(a.board); b.keep_existing_copper()
        render(b, a.out, a.title, region=tuple(map(float, a.region.split(','))) if a.region else None)
    elif a.cmd == 'diff':
        diff(a.old, a.new, offset=tuple(map(float, a.offset.split(','))))
    elif a.cmd == 'stitch':
        r = stitch_apply(a.board, a.out, net=a.net, fence_nets=tuple(a.fence.split(',')), cover_r=a.cover, fence_pitch=a.pitch)
        print(r['counts'], 'skipped islands:', r['skipped_islands'])
    elif a.cmd == 'center':
        print('shift, origin:', transform.center_on_sheet(a.board, a.out, a.origin))
    elif a.cmd == 'origin':
        transform.set_origin(a.board, a.out, a.x, a.y)
    elif a.cmd == 'rename':
        transform.rename_project(a.folder, a.old, a.new, a.title, a.date, a.rev, a.comment)
    return 0


if __name__ == '__main__':
    sys.exit(main())
