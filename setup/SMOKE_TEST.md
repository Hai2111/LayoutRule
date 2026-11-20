# Toolchain smoke test — 2026-11-20

## Result

| Stage | Result | Evidence |
|---|---|---|
| Python audit runtime | PASS | Python 3.12.10; repo tools use stdlib only |
| KiCad CLI | PASS | KiCad CLI 10.0.4 found at `C:\Program Files\KiCad\10.0\bin\kicad-cli.exe` |
| KiCad DRC | PASS on command path | RA01 DRC command completed and wrote JSON; output reported `Found 0 unconnected items` |
| KiCad 3D render | PASS | `pcb render` created a 1600×1200 PNG in 15.043 s |
| Java runtime | PASS | OpenJDK 25.0.5 |
| Freerouting CLI | PASS | Freerouting CLI 2.5.0 starts; 8 cores / ~13 GB detected |
| KiCad 10 Python board load | PASS | `pcbnew.LoadBoard`: RA01 loaded, 47 footprints, 788 tracks |
| KiCad → DSN export | **BLOCKED** | `pcbnew.ExportSpecctraDSN(board, output)` returned `False` and wrote no file in the smoke run |
| Freerouting → SES → KiCad | **NOT RUN** | Requires a valid DSN; do not claim end-to-end routing is ready yet |

## Exact smoke commands

```powershell
& "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe" pcb drc BOARD.kicad_pcb -o drc.json --format json --severity-all
& "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe" pcb render BOARD.kicad_pcb -o board.png --floor --width 1600 --height 1200 --quality high
& "C:\Program Files\KiCad\10.0\bin\python.exe" tools\export_dsn.py BOARD.kicad_pcb board.dsn
& "<repo>\setup\freerouting\cli\freerouting-cli.exe" -de board.dsn -do board.ses
```

## Interpretation

The installed toolchain is reproducible, and the DRC/render path works. The routing pipeline is **not yet end-to-end**: the remaining integration defect is the KiCad 10 Python DSN export returning `False` for this RA01 board. A later fix must first produce a real `.dsn`, then run Freerouting, import `.ses`, and run native DRC again. Until then an agent must not report a completed routed result solely from this setup.
