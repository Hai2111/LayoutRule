"""pcbkit — scripted KiCad 10 placement, priority routing and review for 2-layer boards.

Typical layout script (see examples/singleRgbCtrl_v8.py):
    from pcbkit import Board, F, B, Router, write, check, render
    b = Board('board.kicad_pcb')
    b.place('U1', 21.9, 17.2, 0)                      # placement in Python
    b.poly([b.P('J1.B6'), (20.25, 8.85), b.P('U2.5')], 0.2, '/USB_DP')   # P1 by hand
    Router(b).route('/UART_TX', 'U1.2', 'U2.3', 0.2)  # A* assist for P3
    write(b, 'candidate.kicad_pcb'); check('candidate.kicad_pcb'); render(b, 'candidate.png')
"""
from .board import Board, F, B
from .router import Router
from .writer import write
from .check import check, keepouts
from .render import render
from .stitch import stitch, apply as stitch_apply
from .diff import diff
from . import transform

__all__ = ['Board', 'F', 'B', 'Router', 'write', 'check', 'keepouts', 'render', 'stitch', 'stitch_apply', 'diff', 'transform']
