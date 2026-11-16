# Proposed PT18 — Multi-net criticality and coupled routing regression control

**Status: PROPOSED, awaiting owner's explicit rule-level approval.** Source: [Training Trial A](https://github.com/Hai2111/Training/pull/1), KiCad10/Freerouting reproducible run [43805350779](https://github.com/Hai2111/Training/actions/runs/43805350779). No change to canonical `LAYOUT_RULES.md`, placement patterns, JSON checks or project PCB.

## Failure motivating this rule

Training USB Full-Speed from CH340C was treated as two independent nets. Agent optimized single UART_RX objective after moving RESET pull-up R3:

- UART_RX: 19.167 mm / 2 vias → 16.777 mm / 0 vias.
- USB_DM: 14.653 mm → 23.872 mm; USB_DP: 12.921 mm → 13.175 mm.
- Pair *summed-copper* length difference: 1.732 mm → 10.697 mm.
- NRST: 11.763 mm → 24.077 mm.
- Native DRC errors: 51 → 38, but 38 remain, with new/changed narrow traces and a starved thermal.

The local improvement was real, but the candidate **must not be accepted as a global improvement**. No exact USB timing or impedance has been established by this observation.

## Candidate rule

**Whenever rerouting or moving any footprint, evaluate the entire electrically coupled net-group graph and all affected other nets before accepting a placement. Hard constraints for every net always outrank all ranking metrics.** Group membership, current requirements and applicability are derived from schematic, exact MPN, board stackup and project evidence, *not only a net name or token matching*.

### Step A — Global non-negotiable invariants

- Preserve schematic pad-to-net mapping, source revision and manually locked footprints.
- DRC/Electrical clearance/width/current requirements, exposed connector safety and isolated creepage boundaries are non-tradeable. An unresolved error is NOT accepted merely because overall error counts decrease.
- Source PCB immutable; compare cloned candidates with exact same input and rulebook revisions.

### Step B — Build functional net groups by dependency, not flat net order

- **Coupled transmission:** USB D+/D−, Ethernet diff pairs, controlled-impedance RF segments and relevant high-speed buses. Route/check **as pairs/groups**; assess topology, same-layer adjacency, return path, physical pair integrity, via transitions and interface-specific requirements. USB Full-Speed does not universally require an arbitrary matched length threshold: protocol and edge-rate guide importance.
- **Supply/return loops:** VBUS, battery, buck switching loops, GND returns, charger bypass and IC VCAP/V3. Check geometry, voltage drop, hot-loop paths, capacitance and parasitics jointly.
- **Switching/control stages:** PWM source→gate resistor→MOSFET and associated current return and load paths. Avoid optimizing PWM trace while lengthening gate/control loops.
- **Operational/service:** reset, SWIM/SWD, UART, CC pins and user connectors. Some can move, but must remain electrically valid and not obstruct higher critical routing corridors.
- **Unknown:** NEEDS_EVIDENCE with bounded local trial, never silently categorized as safe.

### Step C — Compare candidates simultaneously using lexicographic constraints and Pareto fronts

1. Reject a **candidate** (not the entire search) on any new hard violation, lost connectivity, owner-lock change or protected-net corruption.
2. Test all P1 coupled groups for unacceptable degradation. A router cannot trade a USB differential pair's route for UART_RX improvements.
3. Test all P2/P3 groups and global DFM/return, preserving length/via/thermal/signal-integrity comparisons.
4. Allow explicit measured tradeoffs *within a tier*, but surface these to engineer; never substitute an arbitrary single weighted sum or absolute minimizing-vias objective.
5. Preserve best-so-far legal solution; propose localized placement move and scoped reroute if trial worsens other groups; bounded retry.
6. Native KiCad DRC/ERC and electrical signoff remain necessary before manufacturing.

### Counterexamples and calibration

- For USB Full-Speed (CH340C), geometrically parallel close D+/D− is a strong layout preference but *neither 0-mm skew nor strict same-layer routing is a universal must-pass physical standard*. Accept justified escape transitions if routing and returns are better and interface spec passes.
- A power path may need a via to maintain copper width/return path; scoring via count alone gives the wrong answer.
- Existing baseline DRC=51 errors and candidate=38 errors is **not** a manufacturing pass. A new `starved_thermal` or `track_width` error cannot be hidden by fixing more unrelated clearances.
- Board-specific code may use experimental thresholds to **reject obvious regressions**, clearly labeled heuristics, but these thresholds must not be copied into generic LayoutRule as USB timing or IPC standards.

## Testable acceptance protocol

Inputs: source/candidate PCB and schematic SHA, ERC/DRC JSON, footprint and net diffs, group map from actual netlist and vendor docs, physical pad/trace coordinates, GND return and stackup.

Outputs: per-group before/after route metrics, pair geometry report, hard DRC delta by *type*, violations with net/refdes, selected candidate disposition, next local repair proposal, rollback.

Pass semantics: `REJECT_TRIAL` / `KEEP_PROVISIONAL` / `NEEDS_EVIDENCE`; **no automatic promotion to LayoutRule canonical rules without owner signoff**.

## Implementation evidence

Experimental [Training net classification](https://github.com/Hai2111/Training/blob/experiment/training-layout-replay-20261116/routing/net_priority_policy.json) and [multi-net evaluator](https://github.com/Hai2111/Training/blob/experiment/training-layout-replay-20261116/routing/evaluate_candidate.py). Repro tests in `routing/test_evaluate_candidate.py`. Evaluation pending CI proof when first drafted; update only with actual run IDs.

**Proposed category:** CONDITIONAL workflow constraint, backed by this failed real KiCad candidate. No universal new electrical threshold is proposed.
