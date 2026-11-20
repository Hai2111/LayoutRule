#!/usr/bin/env python
"""export_dsn.py — export Specctra DSN (Freerouting input) from a KiCad 10 board.

Usage (run with the KiCad-bundled Python so pcbnew is available):
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" export_dsn.py BOARD.kicad_pcb [OUT.dsn]

Writes OUT.dsn (default: <board basename>.dsn) plus the .kicad_pro/.kicad_dru
companion files Freerouting can consume via -de board.dsn+board.kicad_pro.
Returns 0 on success, nonzero on failure.
"""
import os
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    board_path = os.path.abspath(sys.argv[1])
    out_dsn = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.splitext(board_path)[0] + ".dsn"

    import pcbnew  # bundled with KiCad 10

    board = pcbnew.LoadBoard(board_path)
    if board is None:
        print(f"FAIL: cannot load {board_path}")
        return 1

    # Module-level API in KiCad 10: pcbnew.ExportSpecctraDSN(board, filename).
    ok = pcbnew.ExportSpecctraDSN(board, out_dsn)
    if not ok:
        print(f"FAIL: ExportSpecctraDSN -> {out_dsn}")
        return 1
    print(f"OK: DSN written to {out_dsn}")
    print("Next: freerouting-cli.exe -de <out.dsn> -do out.ses, then "
          "pcbnew.ImportSpecctraSES(board, out.ses) + kicad-cli pcb drc (see ROUTING_ENGINE_INTEGRATION.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
