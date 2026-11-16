# CAD evidence extraction — batch 01 (2026-11-16)

**Status: PROPOSED / NOT APPROVED.** This document is an evidence-backed proposal under [GOVERNANCE.md](../GOVERNANCE.md). Do not modify canonical PT/TC rules or permit agents to enforce these checks as HARD merely because this draft exists. Explicit owner approval is required for exact changes.

## Scope and method

Directly inspected three *original KiCad PCB source texts* through the GitHub connection, **not** screenshots or READMEs. Recorded source blob SHA, component XY, pad-net association, routed track-segment length sum, layer per segment, via count and zone-object count. No native KiCad schematic ERC/PCB DRC, zone refill, copper continuity, electrical simulation or EMI/thermal validation was run. These are static observations and **cannot prove an optimal layout**.

1. **RD30 — STM32F4 reference PCB**, 4-layer KiCad 5.1.6, [source](https://github.com/pms67/STM32F4-Reference-PCB/blob/master/STM32F4_REV2.kicad_pcb), source blob SHA \`abc62424db5875d85692611bf2f9ad2ec33f148d\`. Source: 54 modules, 245 segment objects, 67 vias, 2 zone objects. Positive *topological example*, not manufacturer-certified.
2. **RD36 — STM32F401RE development board**, 2-layer KiCad 9, [source](https://github.com/colonelblacc/STM32F401RE-Dev-Board-Design/blob/main/STM32.kicad_pcb), source blob SHA \`f7bb50a89902d141d892ef504622c5b49928fb6b\`. Source: 39 footprints, **0 track segments, 0 vias, 0 zone objects**. Its README claims a finished board with DRC/ERC checks, but the checked-in board file itself is **not a routed PCB**; other exported files may represent a separate completed layout. Therefore, cannot use this particular source file as a positive routing reference. Its R3/R6 also carry footprint value \`22k\` in series between USB D+/- connector nets and MCU nets: **schematic/electrical validation required** before using as any reference (not yet classified definitely incorrect).
3. **Training — STM8 RGB USB-C**, 2-layer KiCad 10, [source](https://github.com/Hai2111/Training/blob/main/stm8_rgb_usb_c_v2/stm8_rgb_usb_c_v2.kicad_pcb), source blob SHA \`9872eabddd9b3852fbf3be43290a31557d9d7bbd\`. Source: 24 footprints, 237 track segments, 18 vias, 1 zone object. **Downstream case study only**; it does NOT independently change upstream rules.

### RD30: ESD chain and power-stage geometry (observations)

- \`J5\` USB Micro-B center **(84.5, 52.25) mm**, \`U3\` USBLC6-2SC6 center **(75.975, 52.575) mm**, \`U2\` STM32F405 center **(50, 62.75) mm**. Straight-line center gaps: J5–U3 **8.531 mm**, U3–U2 **27.897 mm**.
- On the connector side, \`USB_CONN_D-\` and \`USB_CONN_D+\` each have 5 track segments, **5.161 mm summed copper segments**, 0 via, F.Cu only. On the MCU side, \`USB_D-\` and \`USB_D+\` each have 6 segments, **22.891 mm summed copper segments**, 0 via, F.Cu only. The separation between connector-side and MCU-side net names is visible in U3 pad assignments.
- **Interpretation:** the protector is a connector-facing satellite and both polarities exhibit the same *reported copper length sum*. This illustrates *topological staging* and route planning, **not** a universal center-distance or USB impedance target. There is no evidence of USB eye/EMC pass, and summed segments are not a simulation of propagation delay or return quality.
- \`U1\` MP2359 buck center **(70.5,72.25)**, \`L1\` 10 µH center **(63.5,72.25)**, \`C1\` 10 µF on BUCK_IN/GND at **(71.9,68.0)**, \`R3\` 47k BUCK_FB/+3V3 at **(73.5,74.2875)**. \`BUCK_IN\` **8.783 mm**, \`BUCK_SW\` **9.652 mm**, \`BUCK_FB\` **3.862 mm** of *summed segment length*, all F.Cu, 0 via. **Do not** infer hot-loop area or EMI performance from these 1D lengths or footprints.

### Training: actual UART/RESET placement tradeoff (observations)

- \`U2\` CH340C center **(10,15) mm**, \`U1\` STM8S003F3P6 center **(21,18) mm**; \`R3\` 10k RESET pull-up **(15.5,17)** is between them and its pads connect \`/+5V\`–\`/NRST\`, **not UART**.
- \`/UART_RX\`: **8 segments, 19.17 mm segment length sum, 2 vias, F.Cu + B.Cu**; \`/UART_TX\`: **19 segments, 17.83 mm segment length sum, 0 vias, F.Cu**. The net totals also include the UART debug-header branches, so **they are not precise CH340C-to-MCU point-to-point lengths**.
- The UART chip-side pad rows are on the facing sides of U2/U1. The R3 pad copper lies approximately \`x=14.275..16.725 mm, y=16.525..17.475 mm\` (using R3 footprint pad nominal dimensions), inside the coarse intervening routing region. **This is a congestion candidate, not proof** that moving R3 removes both RX vias; NRST trace/pad escape may still obstruct.
- \`C2\` 1 µF at **(15.5,15.25)** belongs to CH340C \`/V3\`–\`/GND\`; \`C4\` 1 µF at **(15.5,19.75)** belongs to STM8 \`/VCAP\`–\`/GND\`. Treating both as freely movable obstacle passives would **risk their local power loops**. Evaluate them separately from R3. **No placement/route candidate has been executed** on this source.

## Six candidate rules (testable rather than slogans)

### ER01 — Qualify CAD before treating it as a routing reference
**Maps:** PT09, PT16, TC10. **Priority:** hard *data-ingestion gate*, not an electronic design rule.

**Applies:** when labeling a third-party layout “routed”, “DRC-clean” or “reference geometry”.

- **Inputs:** exact \`.kicad_pcb\` SHA; counts of segments/vias/zones/unrouted pads; provided schematic/provenance; native KiCad DRC if claiming electrical release.
- **Check:** distinguish \`HAS_ROUTING_GEOMETRY\` from \`ROUTING_COMPLETE\`. If 0 saved tracks, do **not** label the CAD a positive routing example, regardless of README/checklist claims. Native DRC/ERC parity is necessary for \`DRC_VALIDATED\`.
- **Counterexample:** intentionally un-routed placement-only samples are valid for placement studies; do not reject them from all research.
- **Evidence:** RD36 source contains 0 segment/via/zone, while README makes broader completion claims.

### ER02 — Detect critical-net corridors obstructed by movable unrelated footprints
**Maps:** PT07, PT08, PT17. **Priority:** heuristic (routing effort); no automatic DRC failure.

**Applies:** when a critical or route-constrained pair of pads must escape through a shared small corridor, particularly on 2-layer boards.

- **Inputs:** source and destination *pad* positions/orientations, footprint pad/courtyard geometry, priority nets and their branching, fixed anchors, layer/zone and actual route status.
- **Candidate detection:** construct a *coarse* bounding corridor around the desired pad fanout. Flag **unrelated movable footprints intersecting that corridor** as \`POTENTIAL_CONGESTION\`; inspect existing traces and pin ordering before blaming those footprints.
- **Experiment:** clone PCB, move only legitimate obstacle group(s), reroute affected nets, refill zones, run native ERC/DRC as applicable; compare completion, via count, summed copper length per relevant tree/branch, reference continuity and effects on other nets. Accept only **measurable improvement without hard violations**.
- **Counterexample:** one via can be preferable to a longer same-layer detour with broken return plane; physical corridor intersection alone does not demand relocation.
- **Evidence:** Training R3 located inside the STM8↔CH340C UART region, with RX 2 vias and TX 0 vias; causal impact still **UNTESTED**.

### ER03 — Reposition support components only while protecting their actual electrical loops
**Maps:** PT03, PT08, PT17. **Priority:** conditional, vendor override.

**Applies:** when “freeing a corridor” proposes moving RESET resistors, VCAP/V3 bypass capacitors, FB/clock/RF support components.

- **Inputs:** pad-net topology, local supply/reference pin, GND return topology, relevant vendor layout guide, candidate pad-path and zone data.
- **Check:** class by *function and net* instead of R/C package. RESET pull-up may be moved if RESET net/control constraints remain met; decoupling/VCAP must retain required low-impedance pin-to-cap-to-GND return. Reject a candidate whose required local loop worsens beyond vendor constraints or lacks measurements.
- **Counterexample:** moving \`C2\` /\`C4\` with R3 as a uniform group may free visual space but harm CH340 V3 / STM8 VCAP.
- **Evidence:** Training R3 +5V/NRST vs C2 V3/GND and C4 VCAP/GND **explicit net map**.

### ER04 — Verify connector → ESD → PHY chain and stage routing before other nets
**Maps:** PT05, PT07, TC05. **Priority:** conditional electrical/ESD layout.

**Applies:** external USB data lines with PCB ESD protection and known device topology.

- **Inputs:** netlist path connector↔protector↔PHY, protection pad topology, near-port placement and low-impedance surge-GND path, stackup/pair constraints, trace and via data.
- **Check:** identify protector-facing and MCU-facing nets; require no unprotected branch reaching vulnerable IC first, if topology specifies that; compare protector location relative to port and IC and measured surge return, then test D+/D− pair against *PHY-specific*, not USB-C-connector-generic impedance/skew limits.
- **Counterexample:** ESD part “nearest connector by centroid” with a long GND discharge path or high-capacitance load can be worse; protection parts with through/shunt topology differ.
- **Evidence:** RD30 J5–U3–U2 and paired 5.161/22.891 mm copper-segment sums. These values **are measurements, NOT thresholds**.

### ER05 — Distinguish switching loop placement from copper length/centroid proximity
**Maps:** PT02, TC03, TC04. **Priority:** conditional vendor electrical.

**Applies:** buck/boost with identified high-di/dt loops, SW node, input bypass, feedback return and current profile.

- **Inputs:** exact regulator MPN/topology, VIN+GND input capacitor pads, switching return copper polygon, SW and FB nets, layer stack, vendor app note, current/EMI constraints.
- **Check:** evaluate **enclosed high-di/dt loop area + return continuity** and FB exposure. Compute multiple candidate placements if possible; do not certify from a short net-length sum or nearest IC center.
- **Counterexample:** rearranging L1 closer while expanding CIN→power-ground loop can worsen EMI. Synchronous vs asynchronous buck topology changes hot-loop shape.
- **Evidence:** RD30 U1/L1/C1/R3 net association (static); official RD01 TPS62933 and TS02 SNVA054C source guidance. **No area calculation performed here.**

### ER06 — Accept a placement optimization only after reproducible constrained rerouting
**Maps:** PT08, PT17, TC10. **Priority:** hard release workflow; not a claim about EMI.

**Applies:** an agent proposes local placement changes to fix congestion or remove vias.

- **Inputs:** baseline board SHA and manual-lock record; candidate cloned PCB, schematic/netlist SHA, routing versions, router output, native post-zone DRC and per-net metrics.
- **Check:** ensure no lost nets, moved locked footprints, unrelated route corruption, new hard DRC, worse critical loop/return; produce before/after via+length+unrouted with explicit rollback. A cost decrease on one UART net **cannot offset** violating VCAP bypass and power routing constraints.
- **Counterexample:** optimizing only net-via count with no DRC/source parity is not an accepted result.
- **Evidence:** Training existing UART candidate opportunity and source-governed process; **actual optimization not yet executed**.

## What is still NOT established

- Neither RD30 nor RD36 nor Training was electrically qualified or had native DRC/ERC run during this extraction.
- No route optimizer was executed; no test establishes that changing R3 removes two RX vias or that RD30 is globally optimal.
- Footprint center distances and copper *segment-length sums* are **not pad-to-pad true electrical loop length** on branches.
- RD36 requires sourcing the exact claimed complete layout if it exists in a separate release/zip; source \`main/STM32.kicad_pcb\` is insufficient.

## Owner approval checklist

Approve, amend or reject **ER01–ER06 individually**. Upon approval, merge exact selected rules into canonical \`PLACEMENT_PATTERNS.md\`, \`rules/placement_patterns.json\`, \`rules/technical_checks.json\`/workflow as appropriate; add tests and cross-links. Approval is not inferred from this draft PR or from downstream CAD results.
