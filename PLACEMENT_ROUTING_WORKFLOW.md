# PLACEMENT → ROUTING — Workflow for KiCad agents

**Use with:** `LAYOUT_RULES.md`, `PLACEMENT_PATTERNS.md`, `REFERENCE_DESIGN_CATALOG.md`, `VIDEO_CATALOG.md`, `VIDEO_REVIEWS_EXTERNAL.md`, `REVIEW_CHECKLIST.md`.

**Vendor layout guides outrank generic placement heuristics.** Do not optimize Y1 location on ESP32-S3 using an unconditional 'as-close-as-possible' constraint: see RD03/PT04.

## 0. Input contract (fail early)
Read: schematic/netlist, board outline, all footprints, Fab constraints, number of layers/stackup, expected current, fast-edge interfaces, mechanical keepouts, antenna guidance, user-fixed components, prior PCB and hashes. If missing **critical** constraints, request human review. Do not mark PASS by assumption.

**Output:** `input_manifest` (filename, SHA, mtime), `project_constraints`, `net_priority_map`, `functional_blocks`, `user_locked_footprints`.

## 1. Placement pipeline
1. **Mechanical freeze (P01/A04):** board edge, mount holes, connectors, switches, antennas, enclosure-locked components.
2. **Block placement (P02/A05):** partition MCU, PSU, interfaces, clock, RF, analog, sensors and related passives. Estimate airwire/ratsnest congestion and power/signal flow.
3. **Critical placement (P03–P09):** for each buck/boost close high-di/dt loop; place ESD at connector; group clock and decouplers around actual IC pins; antenna keepout; reserved via escapes for fine pitch.
4. **Fanout + route feasibility:** simulate pin escape on 2-layer QFN and multi-pad packages. If blocked, adjust placement *before* bulk routing.
5. **Optimize (P10/P11):** minimize routing obstruction and critical loop/path costs subject to locked placement; do not alter net/pin functions without proof.
6. **Snapshot:** position/orientation diff, DRC and image/zone evidence; never silently overwrite manual user edits.

## 2. Routing pipeline (priority depends on net criticality)
1. **Local bypass/power switching closure:** route short loops inside each power block first where necessary; if conflict with high-speed interfaces compare engineering impact, not rote order.
2. **Critical signals:** quartz/clock, sensitive analog input, RF controlled impedance, USB/differential pairs, timing-critical buses.
3. **Power distribution:** consider current, voltage drop, thermal, branch topology and copper width/pours.
4. **Ordinary signals:** shorter and cleaner routing, minimize crossovers, vias and stubs; preserve return path.
5. **Ground system and pours:** assess 2-layer GND continuity, via transitions, stitch, plane cuts, thermal relief; refill and verify no islands.
6. **Finish:** DFM, silk, mask, 3D, test access, complete DRC/ERC, export and inspect Gerber.

## 3. Route scoring (proposal, not calibrated physics)
Agent can rank candidate solutions using a weighted objective with transparent terms:

`cost = w1*critical_net_length + w2*power_loop_area + w3*return_discontinuity + w4*via_count + w5*congestion + w6*predicted_noise_coupling + w7*manual_edit_conflict`

**Hard constraints are not cost penalties** (hard violations reject solution). Don't insert numerical weights without calibration. Include engineering evidence and rule IDs for any claimed penalty improvement.

## 4. Rules specific to two-layer PCB
- Plan copper reference strategy **before** power/signal routes.
- Constrain major signals/power to layer/region that leaves the best return network; preserve GND connectivity on other side where possible.
- Detect traces that split a GND corridor, via/return-path detours and high-di/dt loops; propose relocation of signal or GND jumps where manufacturable.
- For USB/fast edge: evaluate whether stackup permits required impedance; if not, call out limitation instead of falsely certifying 90Ω differential.
- Treat `min_width=0.10 mm`, `clearance=0.127 mm`, `via 0.30/0.15 mm` as **example past project requirements**, not defaults across every design; check actual manufacturer.

## 5. Agent must challenge its own results
- Did a “shorter” trace require 2 extra vias and a broken reference plane?
- Did a geometrically closer decoupler increase loop inductance or change return topology?
- Did routing force a poor buck placement to remain? Move placement when allowed, instead of tracing around the error.
- Is SW copper unnecessarily enlarged? Are sensitive inputs near it?
- Is any user moved component reverted? If so show exact reason before mutating it.
- Are comments about 90-degree corners supported by electrical/fab evidence? If not, only stylistic warning.

## 6. Gate mapping (do not replace existing KicadAutoLayout G1–G5 semantics)
This repository defines **checks**, not the project's master gate IDs. The host project should map these to its existing gates in `config/rule_gate_map.yaml` and preserve its current gating logic.
- Pre-placement: A rules.
- Placement candidate: P rules.
- Routing candidate: R rules.
- Plane/fab: G rules.
- Release: no unresolved HARD + explicit disposition of CONDITIONAL risks.

## 7. Output files per review
```text
review/
  input_manifest.json
  placement_diff.json
  net_priority_map.json
  routing_metrics.json
  violations.json    # rule_id, severity, status, x/y/net, evidence, suggested_fix
  evidence/          # renders, DRC logs, gerber preview
  review_summary.md
```

Each review must record **UTC timestamp**, source revision, DRC version, netlist hashes, rulebook commit, unresolved exceptions, human-override decisions. Reuse previous scan data only if hashes of relevant inputs are unchanged.

## Sources / evidence status
- PL01, PL02, PL03, PL04, PL09, PL17 and AA01–AA05 in `VIDEO_CATALOG.md`.
- The *workflow and scoring function are engineering proposals* derived from themes, **not statements that video authors endorse this specific algorithm**.
