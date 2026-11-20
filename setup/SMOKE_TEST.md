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
| KiCad → DSN export (fixture) | PASS | `pcbnew.ExportSpecctraDSN(board, output)` wrote a valid DSN for `tests/fixtures/demo_good.kicad_pcb` and `demo_bad.kicad_pcb` |
| KiCad → DSN export (RA01 converted ref) | **BLOCKED** | Same API returned `False` and wrote no file for RA01 (KiCad file version `20260206`, vs fixtures `20241229`). Removing the 4 empty-ref footprints did not fix it. Needs KiCad-native resave / project context or converter cleanup. |
| Freerouting CLI startup | PASS | Freerouting 2.5.0 starts and reads the DSN |
| Freerouting route on fixture | **BLOCKED** | v2.5.0 Windows native image crashed with `UnsupportedFeatureError: SerializationConstructorAccessor ... ObstacleArea`; no `.ses` produced. Freerouting runtime defect, not a board DRC result. |
| Freerouting → SES → KiCad | **NOT READY** | Requires both a valid DSN for converted boards and a Freerouting build that completes without the native-image serialization crash. Do not claim end-to-end routing. |

## Exact smoke commands

```powershell
& "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe" pcb drc BOARD.kicad_pcb -o drc.json --format json --severity-all
& "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe" pcb render BOARD.kicad_pcb -o board.png --floor --width 1600 --height 1200 --quality high
& "C:\Program Files\KiCad\10.0\bin\python.exe" tools\export_dsn.py BOARD.kicad_pcb board.dsn
& "<repo>\setup\freerouting\cli\freerouting-cli.exe" -de board.dsn -do board.ses
```

## Interpretation

The installed toolchain is reproducible, and the DRC/render path works. DSN export works on the repository's clean fixture boards but returns `False` for the converted RA01 board (KiCad file version `20260206`; fixtures use `20241229`). Removing four empty-reference footprints did not resolve it; the next fix is KiCad-native resave/project context or converter cleanup.

Freerouting CLI 2.5.0 starts but the Windows native image crashed while routing the fixture with `UnsupportedFeatureError: SerializationConstructorAccessor ... ObstacleArea`, so no `.ses` was produced. The routing pipeline is therefore **not yet end-to-end**. A later fix must produce a real DSN for the converted board, use a Freerouting build that completes, import `.ses`, and run native DRC again. Until then an agent must not report a completed routed result solely from this setup.
