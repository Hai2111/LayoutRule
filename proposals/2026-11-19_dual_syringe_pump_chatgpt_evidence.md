# PROPOSAL SP-2026-11-19 — Dual Syringe Pump: topology-first placement/routing and validation gates

> **Status:** PROPOSED / NEEDS_OWNER_REVIEW. **Prepared and independently inspected by:** ChatGPT (OpenAI GPT-6), 2026-11-19.
> This is evidence for an unmerged rule proposal, **not** an APPROVED universal design rule or a KiCad release sign-off.
> Review target: [LayoutRule GOVERNANCE.md](../GOVERNANCE.md); base commit `071417f97627be75038025cb625b223387dbd552`.

## 1. Sources and precise artifact identity

- Source Drive folder: https://drive.google.com/drive/folders/1KL6GbNLy4wTjIYiVeUMPEXMwSKvqhyfx
- Original source repository: https://github.com/nguyentron2909/dual-syringe-pump-pcb ; source handoff says work branch `layout/playbook-pass1`, but the attached WIP file has **no independently verified Git commit association**.
- Drive `NguyenTron_snapshot_2026-11-19.zip` contains the older baseline source and KiCad project; source PCB SHA256: `851f6d88716dd59b66e68466136b94add67f6a315b63444f3aa16b760e8e4490`.
- Drive `handoff/current_layout_wip.kicad_pcb` SHA256: `813e974274a98d3cc2f6f15f84d8b52e4dbb910487753c938cc419abc71db35b`.
- Snapshot top-level schematic `dual_syringe_pump.kicad_sch` SHA256: `5523b8a3f36f574e2d33857dd741a4f557796b87274c46d1367e03888e2b63e7`. The exact schematic→WIP synchronization is **not independently verified**.
- Data package: `handoff/pyflow_source_and_state.zip` (routing scripts, plan/state, evaluator), `AGENT_HANDOFF.md`, `experiment.txt`, `handoff_placement.png`, `handoff_routing.png`, `handoff_pour.png`.
- The attached `AGENT_HANDOFF.md` and `experiment.txt` are **project-authored reports**, not independently certified measurements.

## 2. What was checked

Independent parse of the supplied WIP KiCad PCB using the supplied `pyflow/model.py`, with `geom.part_pads`, `evalr.Evaluator.angles` and `vip.vip` applied to its native geometry:

| Check | Observed on supplied WIP | Evidence boundary |
|---|---:|---|
| Board outline | 70 × 100 mm, 2 copper layers | Extracted board geometry |
| Footprints / track segments / vias | 125 / 831 / 170 | Extracted board geometry |
| GND vias | 47 of 170 | Extracted board geometry |
| F.Cu / B.Cu route length | ~1695.3 / 1021.7 mm | Summed centerlines; no electrical interpretation |
| 90° bends / acute bends | 9 / 3 | `evalr.angles()` geometry-only check |
| Non-EP via-in-pad hits / EP thermal-via hits | 0 / 18 | Supplied `vip.py` algorithm; EP fabrication constraints remain to be checked |
| Filled copper polygon records | 127 | This is not a validated count of connected GND regions |

**Reported, not independently rerun here:** The Drive handoff lists **2 copper-clearance**, **10 courtyard**, and **28 GND unconnected** errors in a KiCad-native exported-and-poured stage; those errors must be rechecked against the exact board revision before release. There was no KiCad CLI DRC execution in this independent review.

**Important checker limitation confirmed in source:** `pyflow/evalr.py` `connectivity()` contains `if n == 'GND' or len(pl) < 2: continue`. Thus its reported `unconnected = 0` **does not certify GND continuity**, and cannot supersede native KiCad DRC/zone-refill output.

**Important intent-model error confirmed against WIP pads:** `layout_work/layout_intent.json` labels `U4.17` and `U5.17` as ground references for decoupling. The native PCB identifies both pin 17s as `Net-(U4-VREF)` and `Net-(U5-VREF)`, respectively. The relevant GND pins/pads must be derived from the actual datasheet and netlist before any loop/decoupling audit. An intent file is not a source of electrical truth.

## 3. Comparison results — interpretation, not overclaim

`experiment.txt` reports:
- Freerouting on original placement: 40 unconnected, 17 starved thermals.
- Freerouting staged on a different simulated-annealing placement: as many as 77 unconnected.
- Human-defined functional placement, power and signal topology, followed by editable guided A*/manual routes: 831 segments, 170 vias and `0` non-GND unconnected in the Python check.

These are **different placement/topology/test conditions**. They illustrate the need for engineering constraints, but **do not establish a controlled performance win** over a baseline autorouter. Comparison must fix the same starting schematic/board, tool versions, DRC settings, netclasses, time budgets, and metrics; include KiCad-native DRC after refilling copper.

## 4. Candidate changes for owner decision

The following IDs are **proposal-local** and do not override canonical A/P/R/G/K rules until reviewed. The words below are the exact proposed change, not a claim of approval.

| Proposal | Existing related rule | Tier proposed | Exact candidate rule / scope and exception | Verification / rejection test |
|---|---|---|---|---|
| **SP01** | A01, N01, P04, G07 | HARD process gate | Before trusting `layout_intent.json`, verify every named power/return/decap pad against the project-native pad→net map and component vendor pinout. A mismatch = FAIL. Exception: documented deliberate alternative pad/net mapping with matching schematic revision. | Cross-check `U4.17/U5.17` VREF error; regression test should reject the current false GND mapping. |
| **SP02** | R01, R05–R06, G02, G05 | HARD release gate | A custom connectivity PASS is only a provisional geometric result. After final zone refill, run native KiCad DRC and evaluate **all nets including GND, pours and islands**. No PASS/ready-for-fab while native unconnected or clearance errors remain. Exception: recorded, reviewed and safety-justified accepted exceptions, never silence or missing DRC. | Detect Python `GND` exclusion; test a GND island/disconnected pad despite non-GND nets connected. |
| **SP03** | P03–P04, R03–R04, G04 | CONDITIONAL | For high-current multi-load systems, define source→bulk capacitor→branch destinations and the **real return paths** before trace completion. Check each branch's current, voltage drop, width, via transitions, loop geometry and decoupler return; source-to-load topology may use parallel branches when shared upstream series segments would cause unacceptable drop, coupling or thermal stress. **Do not mandate parallel branches for all systems**. | Compare TMC2209 VSYS branches from bulk C29 against alternate topology with current assumptions varied; evaluate loop area, `I*R`, copper temperature and GND return. |
| **SP04** | K2/K3, R02–R08, workflow | HEURISTIC | Use topology-first and congestion-aware routing: reserve current/return/critical corridors, fan out constrained pads, and permit short controlled layer hops; interleave placement adjustments and partial routing. The router may implement geometry **inside** human/project constraints; do not force global net-by-net completion. Alternative automated placements/routing are acceptable if they satisfy identical verified constraints. | Compare fixed-time controlled candidates and failure modes; keep editable route plan and repour/DRC artifacts. |
| **SP05** | G03–G04, P09 | CONDITIONAL | Distinguish intentional thermal vias in exposed pads from accidental via-in-pad. Thermal via count, drill, fill/tent/cap method, solder wicking and assembly suitability must follow the IC/package plus fabricator/assembler specification. General default: no unapproved via-in-SMD-pad. | `vip.py` 0 non-EP / 18 EP is geometry only; review EP solder mask/paste drill and assembled performance with manufacturer. |
| **SP06** | G06–G07, REVIEW_CHECKLIST | HARD process gate | An agent may mark an internal geometry check PASS while separately logging **native DRC FAIL** and **electrical NEEDS_REVIEW**. Never collapse into one `0 violations` status; retain board SHA256, tool version, report output, unresolved coordinates and owner edits. | Compare handoff 0 non-GND connectivity from Python against native-reported 2 clearance/10 courtyard/28 GND unconnected. |
| **SP07** | A02, R04, workflow | CONDITIONAL | All power/current budgets and USB/differential impedance targets must be classified `VENDOR`, `PROJECT`, `CALCULATED` or `ASSUMED`. Reject promotion of assumed example values (e.g. motor 1 A/coil, VSYS 3 A, `USB 90 Ω`) to universal defaults or PASS thresholds. | Recalculate with actual copper stackup, motor current, battery/adapter ratings and PHY requirements; compare with design intent. |
| **SP08** | REVIEW_CHECKLIST, K1 | HEURISTIC review process | Publish placement, routing, and poured-board PNG views at checkpoints (with critical hotspots/coordinate annotations). Images aid owner review but **must not replace** native DRC, manufacturing checks or source-hash traceability. | Pair every visual candidate with exact board hash, region list and DRC/log provenance. |

### Conflicts or claims **not** promoted

1. **"Absolutely no 90° corners"**: the handoff calls it mandatory; canonical [LAYOUT_RULES.md](../LAYOUT_RULES.md) **R09** explicitly treats isolated 90° corners as a heuristic/style warning, not universal electrical failure. Retain R09. Nine observed bends are a polish issue unless justified risk exists.
2. **"Every power path must literally pass through the decoupling capacitor first"**: treat this as a way to reason about **small supply–return loop inductance and source topology**, not a universal pad ordering rule.
3. **"No traces under any passive body"**: project-specific K1 may be conservative for manufacturability, visual review and clearance; broader use must evaluate part body, copper layers, routing requirements, fabrication and vendor exceptions. Do not claim copper on a valid PCB layer underneath a passive is electrically forbidden in all designs.
4. **"18 vias under EP are always acceptable"**: no; thermal geometry must be reviewed against assembly process.
5. **"Guided routing is proven superior"**: not established until controlled, same-source benchmarks including DRC and plane quality.

## 5. Proposed validation steps before promotion

1. Reproduce checks on the exact WIP SHA above, correct the pin 17/VREF `layout_intent.json` mapping, then rerun evaluator.
2. Run zone refill + KiCad-native DRC on the exact candidate, save JSON/RTF outputs; resolve GND, 2 reported clearance and 10 reported courtyard issues, not just non-GND connectivity.
3. Review the attached layout images, B.Cu reference-plane cuts, TP5100/XL4015 hot loops, TMC2209 EP solderability, connector/mechanical courtyard and antenna keepout.
4. Run one controlled tool-only vs topology-guided experiment from the same placement and netclass/DRC constraints, same total budget, with same evaluator and native DRC.
5. Run regression tests on at least one separate board for the candidate rule's generality and negative counterexamples.
6. Owner explicitly approves or rejects **each SPnn** with intended scope; only then promote accepted wording into canonical LAYOUT_RULES / playbook / checker tests.

## 6. Author/reviewer and status

- **Analysis/document author:** ChatGPT (OpenAI GPT-6), 2026-11-19. Linked GitHub account performing the write may be the repository owner; Git commit metadata is not a substitute for the author declaration here.
- **Native KiCad DRC:** NOT RERUN in this review.
- **Review/merge:** HUMAN OWNER DECISION REQUIRED; **no main-branch rule changes made**.
- Rollback: close proposal PR/delete proposal branch; canonical rules are unchanged.
