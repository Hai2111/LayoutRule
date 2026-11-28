"""apply_place.py IN.kicad_pcb PLACE.json OUT.kicad_pcb : dat linh kien theo bang {REF: [x, y, goc]} (mm, do).
Bang co the chua muc "_outline": [x0, y0, x1, y1] de doi vien board (chi khi da chung minh). Khong dong vao net/pad/day."""
import json
import sys

import pcbnew
from pcbnew import FromMM, VECTOR2I

b = pcbnew.LoadBoard(sys.argv[1])
tab = json.load(open(sys.argv[2], encoding="utf-8"))
moved = []
for ref, v in tab.items():
    if ref.startswith("_"):
        continue
    f = b.FindFootprintByReference(ref)
    if f is None:
        sys.exit(f"khong co {ref}")
    x, y = v[0], v[1]
    if len(v) > 2:
        f.SetOrientationDegrees(v[2])
    f.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
    moved.append(ref)
if "_outline" in tab:
    x0, y0, x1, y1 = tab["_outline"]
    for d in list(b.GetDrawings()):
        if d.GetLayer() == pcbnew.Edge_Cuts:
            b.Remove(d)
    r = pcbnew.PCB_SHAPE(b); r.SetShape(pcbnew.SHAPE_T_RECT); r.SetLayer(pcbnew.Edge_Cuts); r.SetWidth(FromMM(0.1))
    r.SetStart(VECTOR2I(FromMM(x0), FromMM(y0))); r.SetEnd(VECTOR2I(FromMM(x1), FromMM(y1))); b.Add(r)
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from ksave import save_board; save_board(b, sys.argv[3])
print(f"dat {len(moved)} linh kien -> {sys.argv[3]}")
