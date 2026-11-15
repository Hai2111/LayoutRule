# ROUTING ENGINE INTEGRATION — Claude / KiCad 10

Updated 2026-11-15. **Primary executable candidate**: [Freerouting](https://github.com/freerouting/freerouting) + KiCad10 `pcbnew` Specctra DSN/SES bridge. Reference integration prototype and Claude instructions are in [Hai2111/Training/routing](https://github.com/Hai2111/Training/tree/main/routing), [Training ROUTING_RULES.md](https://github.com/Hai2111/Training/blob/main/ROUTING_RULES.md), and [Training CLAUDE.md](https://github.com/Hai2111/Training/blob/main/CLAUDE.md).

**Source quality and maturity:**
- [Official KiCad10 pcbnew namespace](https://docs.kicad.org/doxygen-python-10.0/namespacepcbnew.html): `ExportSpecctraDSN`/`ImportSpecctraSES` are explicit Python 10 API functions, using a BOARD object. **API contract checked; not executed here.**
- [Freerouting CLI docs](https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md): `-de .dsn[+.kicad_pro][+.kicad_dru]`, `-do .ses`, headless and routing settings. DSN does not transmit KiCad min track width/custom DRC rules on its own. **Docs checked; not installed or executed here.**
- [Freerouting KiCad plugin](https://github.com/freerouting/freerouting/blob/master/integrations/KiCad/README.md): production-default DSN/SES route and GUI plugin; alternative experimental JSON/API mode. **Source/README checked.**
- [PCBWorld](https://github.com/LGAI-Research/PCBWorld/blob/main/docs/ENVIRONMENT.md): route-step environment with KiCad push-and-shove. Its `env.reset()` *strips preexisting routing* from the board being evaluated; it must **not** be handed an owner-only baseline. Linux x86_64 primary, Python 3.12+, and GPLv3 engine submodule are integration constraints.
- [CADET](https://github.com/LGAI-Research/CADET): research into routing traces/executable demonstrations, not an immediate production router.

## General rule layers for an LLM router
1. **Hard invariants:** current file hash; pad→net identity, board layers, outline, component XY/rotation locked by owner, clearance and minimum widths, protection of all unselected nets.
2. **Physical constraints:** current loops, GND return reference/plane, actual load/temperature/voltage, impedance according to PHY and stackup, safety/isolation barriers.
3. **Route objective:** achieve connectivity on permitted nets without DRC errors; minimize avoidable vias, route length, congested crossovers and noise coupling **only after** previous conditions.
4. **Placement feedback:** repeated detours indicate poor floorplanning. Return to placement optimizer; route engine alone cannot fix an inconvenient connector or a gate resistor on the opposite side of the board.
5. **Audit:** original board hash + original DRC + candidate DRC + source integrity + track/via diffs + return path assessment. **KiCad native DRC PASS is necessary but insufficient for EMI/power.**

## Route strategies by net class

| ID | Use when | Preferred routing action | Anti-rule |
|---|---|---|---|
| RE01 | Dense 2-layer | Protect coherent GND reference layer, use B.Cu signal escapes when necessary plus return transfer | GND vias every fixed X mm for all boards |
| RE02 | MCU power, bypass | Short cap-to-pin/return loop, avoid slicing GND plane with tracks | Nearest capacitor center = best loop |
| RE03 | Switching buck/boost | Route hot loop / CIN power-current paths before unrelated nets can obstruct them | All switch rails must be shortest centroid line |
| RE04 | USB FS / HS | Separate PHY constraints, route D+/D− together with controlled reference path; limit avoidable via transitions | Copy HS 90Ω rules blindly to every USB-C board |
| RE05 | Gate drive | Put damping R as topology requires (MOSFET gate resistor near gate), route R→gate short | Always put every series resistor near MCU driver |
| RE06 | RGB/industrial load | Actual current, Vdrop, pad/via copper bottlenecks; optimize load loop in coordination with connector pin mapping | 0.2mm minimum DRC means 0.2mm safe for any current |
| RE07 | Analog ADC, CT, EIS | Route low-level signal/reference away from noisy switch aggressors; model returns/guard based on actual AFE | Unconditionally split AGND/DGND |
| RE08 | Via/route angles | Favor efficient bends, low via counts only if GND return still good; 45° often tidy | Blanket 90° prohibition or zero via dogma |
| RE09 | Iterative agent | Rip up selected nets only; inspect results; if poor, re-evaluate placement/stackup | Re-route 100% of board repeatedly without evidence |

## Critical KiCad→Freerouting rule transfer caveat
The current [Freerouting CLI docs](https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md) expressly note that the DSN file does not carry every KiCad custom DRU, nor `board.design_settings.rules.min_track_width`. Use `-de board.dsn+board.kicad_pro[+board.kicad_dru]`, plus the configured minimum neck width where supported. **Still run native KiCad CLI DRC after import**, because not all application-specific rules are represented by DSN.

## Limitations and next integration validation
- Training has committed a prototype `routing/route_controller.py` + `routing/kicad_worker.py` + `routing/audit_pcb.py`. Pure Python syntax and plan-only mode were tested; **no KiCad10 pcbnew/Java routing run has been executed here**.
- Must validate Freerouting integration with an installed matching KiCad10 Python interpreter and Java runtime before claiming automatic routing is operational. Keep input file immutable, test on copy, inspect DRC.
- Current example source mismatch in Training: uploaded board has all 237 track widths at 0.2mm; GitHub board still includes 32 under 0.2mm. Do not falsely claim an old repo version was fixed until file is committed and re-reviewed.
