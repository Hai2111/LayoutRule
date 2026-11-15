# PCB AUTO-PLACEMENT / ROUTING RESEARCH & BENCHMARKS

Date: 2026-11-15. **Purpose:** connect layout engineering rules to practical source-backed agent evaluation. These papers are research hypotheses, not validated rules automatically applicable to hardware.

## Evidence policy
- `ABSTRACT_READ`: authors' online abstract and reported results reviewed, **full experimental protocol not independently verified**.
- `REPO_README_READ`: authors' repository/docs source present and implementation described; **no installation, test execution or benchmarking by us**.
- Peer-reviewed results and engineering vendor reference designs have different evidence roles. Never turn a paper metric into an electrical PCB specification.

| ID | Source | Evidence | Key idea | Relevance/limitations |
|---|---|---|---|---|
| PR01 | [CADET: Construction of PCB Routing Instances with Executable Demonstrations](https://arxiv.org/abs/2611.16913) (2026-11-12); [source BSD-3](https://github.com/LGAI-Research/CADET) | **ABSTRACT_READ + REPO_README_READ** | Authors generate 100,000 synthetic routing instances and engine-executable route demonstrations; BC+RL routing under KiCad-based engine. Their D3-B test clean-pass result is 67.2% at one rollout in README table, versus 65.6% Freerouting in authors' tested setting. | Important for **replayable agent action trajectories and reproducible DRC**. Numbers are **authors' reported**, not comparable to user boards without same dataset, engine, budgets or setup. |
| PR02 | [PCBWorld: KiCad push-and-shove routing environment](https://github.com/LGAI-Research/PCBWorld) | **REPO_README_READ** | Provides Gymnasium agent step environment built on KiCad router, real board benchmark splits, LLM tool-calling policies and shared evaluation pipeline. States engine submodule pinned to KiCad 9.0.8 and GPLv3, wrapper BSD-3. | **Potential test bench**, but platform lists Linux x86_64 primary, macOS ARM experimental; Windows setup is **not declared supported**. No integration with KicadAutoLayout or repo user computer was executed. |
| PR03 | [Component Centric Placement Using Deep Reinforcement Learning](https://arxiv.org/abs/2602.23540) (2026-02) | **ABSTRACT_READ** | Paper models passives placed around a central IC in discretized candidate sites; optimizes wirelength/feasibility via RL and simulated annealing on >9 boards. | Suggests predefine feasible site generator per pin before optimizing. **Not a universal law to put the main IC at board center**; mechanical connectors, RF and hot-loop constrain placement. |
| PR04 | [Microstrip Impedance Management Through Multilayer PCB Stack-up](https://www.mdpi.com/2073-8994/13/10/1771) (2021) | **ABSTRACT_READ** | Footprint pads cause impedance discontinuities; research examines reference-plane cutouts/compensation with measurements from S-parameters and TDR. | **Counterexample to 'never use plane void'**: a deliberately computed local void can compensate controlled-impedance pad loading. Requires EM model/measurement; should not auto-cut ground beneath every pad. |
| PR05 | [Analysis and measurement of small inductance of loops and vias on PCB](https://ieeexplore.ieee.org/abstract/document/1280307) (IEEE IECON 2003) | **ABSTRACT_READ** | Examines loop/via parasitic inductance and its dependence on geometry; experimental test circuit compared with analytical estimates. | Guide loop inductance scoring; do not equate via count with total L without return path geometry. |
| PR06 | [Embedded decoupling capacitor placement for GaN buck](https://ieeexplore.ieee.org/abstract/document/11403647) (IEEE PEAS 2025, indexed Feb 2026) | **ABSTRACT_READ** | Researchers report an embedded-cap PCB, reduced loop inductance and switch overshoot on a tested GaN converter. | Geometry-specific demonstration; **not a recommendation for through-hole via-in-pad on normal 2-layer low-cost PCBs**. |
| PR07 | [PCB layout-based EMI filter mutual coupling optimization](https://ieeexplore.ieee.org/abstract/document/11659068) (IEEE TIE 2026) | **ABSTRACT_READ** | Reports 11kW onboard-charger test/measurement: EMI-filter performance changes due to spatial mutual inductance, not just schematic values. | Caution that compact filter placement may cause undesirable coupling. Values are authors' experiment and device-specific. |

## Lessons useful for KiCadAutoLayout now
1. **Do not score route quality with net completion alone.** Report: clean-pass under KiCad DRC, net routability/completion, length/via count, electrical risk annotations and runtime separately (PR01/PR02).
2. **Agent actions must be replayable** in deterministic versions of the router with reproducible start board, rule-set, action list and tool version (PR01/PR02).
3. **Candidate placement should respect electrical placement constraints before optimization**. Passive pins, mechanical anchors, current loops, RF keepouts, user locks must feed candidate feasible site search; centroid-only placement cost is not safe (PR03 + TS02/TS06).
4. **No universal ground plane absolutes.** Preserve signal return under normal critical traces, but designed impedance structures can use intentional compensated voids (PR04). Such changes need field solver validation.
5. **Electrical metric ≠ routing DRC.** PR01's clean pass is correctly scoped to DRC and connection completion, not measured EMI/thermal or signal eye.

## Suggested benchmark design
- **Dataset:** 10–20 fixed-revision KiCad PCB boards with source URL/blob SHA, schematic, stackup, fab rules; include a mixture of small 2-layer MCU USB, buck/boost, RF, isolated RS485, 4-layer mixed-signal, BGA/DDR.
- **Per board outputs:** `source_sha`, `kicad_version`, `rule_set_sha`, `agent version`, `action_trace.jsonl`, `final.kicad_pcb`, `drc.json`, `clean_pass`, `net_completion`, `runtime_s`, `length_by_priority_net`, `vias_by_class`, `critical_violations`, `manual_edits_preserved`.
- **Hard gates:** zero actual shorts/opens; no unexplained missing footprints; no altered netlist or project/fab limits; no unapproved manual edits.
- **Review-only scores:** hot loop topology/area, return path continuity, ADC noise, impedance, temperature, RF matching, assembler access. These require sources, simulation or hardware measurements before PASS.
- **Baselines:** original PCB layout, Freerouting/PCBWorld if installed/verified, KiCad native routing agent, constrained random/place heuristic. Compare using equal time/rollout budgets and same DRC configuration.
- **Safety/legal:** check project licenses (MIT, CERN-OHL-W, CC BY-SA), respect third-party restrictions; ensure PCBWorld separate engine GPLv3 implications when embedding/distributing. Do not copy external board source into LayoutRule simply to build a benchmark.

## Practical next steps (not yet performed)
- Investigate whether PR02 engine API / Windows environment can be used with the existing project toolchain.
- Run *one* board all the way through: zone refill, KiCad DRC, trial route, replay action trace, compare per-net metrics to manual baseline.
- Run CAD geometry extraction with KiCad pcbnew and validate parser output on RD30 board: the existing `RD30_kicad_placement_sample.json` has only partial component metadata.
