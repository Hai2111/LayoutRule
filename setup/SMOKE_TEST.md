# Toolchain smoke test — 2026-11-20

## Result

| Stage | Result | Evidence |
|---|---|---|
| Python audit runtime | PASS | Python 3.12.10; repo tools use stdlib only |
| KiCad CLI | PASS | KiCad CLI 10.0.4 at `C:\Program Files\KiCad\10.0\bin\kicad-cli.exe` |
| KiCad DRC | PASS on command path | RA01 command completed and wrote JSON; output reported `Found 0 unconnected items` |
| KiCad 3D render | PASS | `pcb render` created 1600×1200 PNG in 15.043 s |
| Java runtime | PASS | OpenJDK 25.0.5 |
| Freerouting native CLI | **FAIL** | v2.5.0 Windows native image crashes during routing with `UnsupportedFeatureError: SerializationConstructorAccessor ... ObstacleArea` |
| Freerouting JAR | PASS | `java -jar freerouting-2.5.0.jar -de demo_good.dsn -do demo_good.ses -mp 2` exits 0 and writes SES (4.2 KB); route summary: 0 unrouted, 2 Freerouting violations |
| KiCad 10 Python board load | PASS | `pcbnew.LoadBoard`: RA01 loaded, 47 footprints, 788 tracks |
| KiCad → DSN export (fixture) | PASS | `pcbnew.ExportSpecctraDSN(board, output)` writes valid DSN for `tests/fixtures/demo_good.kicad_pcb` and `demo_bad.kicad_pcb` |
| KiCad → DSN export (RA01 converted ref) | **BLOCKED** | Same API returns `False` and writes no file for RA01 (version `20260206`; fixtures `20241229`). Removing 4 empty-ref footprints did not fix it. Needs KiCad-native resave/project context or converter cleanup. |
| SES → KiCad import (fixture) | PASS | `pcbnew.ImportSpecctraSES` returns true and saves routed board copy |
| One-command pipeline (fixture) | PASS | `tools\route_pipeline.ps1 -Board tests\fixtures\demo_good.kicad_pcb` completed all 5 steps (DSN → JAR route → import candidate → native DRC → 3D image) with `-AllowDrcViolations`; input board untouched |
| Native DRC after SES import (fixture) | **FAIL (expected test result)** | DRC runs and reports 23 violations + 1 unconnected item. Freerouting itself flagged the 2 **pre-existing** fixed-item clearance violations (FixedVia#32/33 on net +3V3) that cannot be fixed by routing — board author must fix in EDA. This proves the return path works, not that the fixture route is acceptable. |
| Full converted-board routing | **NOT READY** | RA01 cannot export DSN; do not claim end-to-end routing for converted refs until that is fixed. |

## Exact smoke commands

```powershell
& "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe" pcb drc BOARD.kicad_pcb -o drc.json --format json --severity-all
& "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe" pcb render BOARD.kicad_pcb -o board.png --floor --width 1600 --height 1200 --quality high
& "C:\Program Files\KiCad\10.0\bin\python.exe" tools\export_dsn.py BOARD.kicad_pcb board.dsn
& "<repo>\setup\freerouting\freerouting-2.5.0.jar"  # run with: java -jar ... -de board.dsn -do board.ses
```

## Interpretation

The toolchain path is now partially proven: **KiCad fixture → DSN → Freerouting JAR → SES → KiCad import → native DRC** all execute. The native Freerouting executable is unusable for routing in this environment; use the pinned JAR instead. The route still requires native DRC and visual review; a Freerouting success/0-unrouted message is not a release result.

The remaining converted-ref blocker is RA01's DSN export returning false. It is isolated from the router: export works on the clean fixtures and the JAR works on a valid DSN. Fix the converter output / KiCad-native normalization before claiming an end-to-end result on Altium-converted projects.
