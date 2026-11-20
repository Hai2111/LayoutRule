#!/usr/bin/env python
"""import_ses.py — import a Freerouting Specctra SES (routed result) into a KiCad 10 board.

Usage (run with the KiCad-bundled Python so pcbnew is available):
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" import_ses.py BOARD.kicad_pcb ROUTE.ses [OUT.kicad_pcb]

Loads BOARD, imports the Freerouting-routed tracks/vias from ROUTE.ses onto it,
and saves the result to OUT (default: <board basename>_routed.kicad_pcb).
The input BOARD file is NOT modified. Returns 0 on success, nonzero on failure.

Pair with tools/export_dsn.py and setup/freerouting jar; see tools/route_pipeline.ps1
for the whole DSN -> route -> import -> DRC chain in one command.
"""
import os
import sys


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    board_path = os.path.abspath(sys.argv[1])
    ses_path = os.path.abspath(sys.argv[2])
    out_path = os.path.abspath(sys.argv[3]) if len(sys.argv) > 3 else os.path.splitext(board_path)[0] + "_routed.kicad_pcb"

    if not os.path.exists(board_path):
        print(f"FAIL: board not found {board_path}")
        return 1
    if not os.path.exists(ses_path):
        print(f"FAIL: SES not found {ses_path} (run Freerouting first)")
        return 1

    import pcbnew  # bundled with KiCad 10

    board = pcbnew.LoadBoard(board_path)
    if board is None:
        print(f"FAIL: cannot load {board_path}")
        return 1

    # Module-level API in KiCad 10: pcbnew.ImportSpecctraSES(board, filename).
    ok = pcbnew.ImportSpecctraSES(board, ses_path)
    if not ok:
        print(f"FAIL: ImportSpecctraSES -> {ses_path}")
        return 1

    board.Save(out_path)
    print(f"OK: routed board written to {out_path}")
    print("Next: kicad-cli pcb drc " + out_path + " -o drc.json --format json --severity-all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
