# CAD extraction runbook — reproducible rule-candidate research

**Status: DRAFT.** Use on a copy of each original source PCB. This is a static analysis tool, not a DRC replacement.

## Inputs

1. Download the exact source .kicad_pcb in its own repo/revision and record the commit SHA and GitHub file blob SHA.
2. If electrical acceptance is claimed, obtain matching .kicad_sch and .kicad_pro for the same revision, stackup, rule settings, BOM/MPN and current design constraints.
3. Run this extractor on the local PCB:

~~~bash
python tools/pcb_ref_extract.py path/to/board.kicad_pcb \
  --ref U1 --ref U2 --ref R3 \
  --net /UART_RX --net /UART_TX \
  --output board_static_metrics.json

python -m unittest discover -s tests -p 'test_pcb_ref_extract.py' -v
~~~

For old KiCad 5 names, use the exact net name from the file. For KiCad 10, use exact strings, including initial / when the file uses it.

The tool emits footprint XY/rotation, selected **local pad** coordinates, raw pad net names, per-net counts of trace-segment objects, **sum of physical segment lengths**, per-net vias/layers and zone object count. **Local pad coordinates have not been transformed to board-global XY**: obtain global positions through KiCad API before doing genuine pad-to-pad geometry, obstruction tests or electrical loop-area analysis.


For an **F.Cu-only straight-line corridor precheck** on the Training project, using its actual Default netclass clearance (0.15 mm) and 0.2 mm trace width:

~~~bash
python tools/pcb_corridor_precheck.py path/to/stm8_rgb_usb_c_v2.kicad_pcb \
  --from-ref U2 --from-pad 2 --to-ref U1 --to-pad 3 \
  --trace-width-mm 0.2 --clearance-mm 0.15
~~~

The tool tests pad-envelope intersection for a **hypothetical direct route**, not whether a real router can eliminate vias. It does not read .kicad_pro itself; pass the correct netclass clearance after checking current project settings. It does not support B.Cu/mirrored pad mapping.

## Acceptance policy

- A README, BOM, screenshot or ZIP claim does not verify the current PCB source data.
- A source that has saved tracks does **not** prove routing is complete, even with 0 errors claimed elsewhere.
- Net segment sum is not point-to-point length on branched nets, especially UART/SWD/power/GND with test headers.
- The extractor does not inspect filled zone polygons, impedance, trace-to-footprint collision, clearance or loop areas.
- An observed reference relation becomes an **ER proposal**, not an APPROVED/HARD rule. Any numeric threshold must come from an exact vendor, topology, stackup, fab or validated optimization; do not copy coordinate gaps.
- Before/after trials require immutable baseline, native KiCad ERC/DRC, filled zones, explicit targeted-net reroute, connectivity audit, source/candidate hashes, permitted component moves and return/power-loop review.
- Unverified cases stay NEEDS_REVIEW and cannot be presented as a passing benchmark.

## Batch 01 artifacts

- [Source observations and ER01–ER06](2026-11-16_CAD_RULE_CANDIDATES.md)
- [Machine-readable case measurements](2026-11-16_CAD_EVIDENCE_BATCH01.json)
- [Python extractor](../tools/pcb_ref_extract.py)
- [F.Cu corridor precheck](../tools/pcb_corridor_precheck.py)
- [Extractor fixture unit tests](../tests/test_pcb_ref_extract.py)
- [Corridor fixture unit tests](../tests/test_pcb_corridor_precheck.py)

**Test scope:** Python extractor and corridor prechecker passed seven small **synthetic** fixture tests (KiCad 5 numeric net, KiCad 10 named net, placement-only detection, malformed board rejection). The three full-sized boards were independently inspected as CAD text with a JavaScript S-expression scanner through GitHub. The Python extractor has **not** yet been run end-to-end on these full-sized sources.

## Next benchmark

1. Run Python on pinned RD30/RD36/Training files locally; compare outputs with evidence JSON. Resolve discrepancies before marking a full CAD parse.
2. Add KiCad-native pad-global coordinates, filled copper zone connectivity, net continuity and DRC; do not mistake exported DSN/SES for native constraints.
3. Clone Training PCB and trial **R3-only placement alternatives**, preserving C2 (CH340C V3) and C4 (STM8 VCAP) until their loops are mapped. Compare UART_RX 2-via baseline with actual candidates; don't promise 0 vias.
4. Reclassify RD36 main PCB source as placement-only for routing evaluation; independently inspect any actual routed exports and USB resistor values.
5. Present ER01–ER07 to owner for individual approval; only then change canonical rulebook and machine-readable checks.

Do not replace Training or any user PCB while testing; work on a cloned candidate.
