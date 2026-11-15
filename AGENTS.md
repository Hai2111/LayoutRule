# AGENTS.md — instructions for Claude / Codex / KiCadAutoLayout

This repository is a **PCB layout reference**, NOT an automatically validated standards database.

## Read order
1. `README.md`
2. `LAYOUT_RULES.md`
3. `REFERENCE_DESIGN_CATALOG.md` and `PLACEMENT_PATTERNS.md` (vendor-specific overrides)
4. `PLACEMENT_ROUTING_WORKFLOW.md`
5. `REVIEW_CHECKLIST.md`
6. `VIDEO_CATALOG.md` + `VIDEO_REVIEWS_EXTERNAL.md` for video chapter, URLs and evidence status

## Before acting on a PCB
- Read current schematic/board, datasheets, manufacturability, stackup and **project-local** constraints.
- Detect and respect manually edited placements and tracks; diff before applying any change.
- Classify each candidate action with `rule_id`, net/refdes, known facts, confidence, evidence, expected tradeoff, rollback path.
- Never substitute these generic rules for component vendor design requirements.
- Before treating a reference as a geometry template, check `references/index.json` and mark it NOT REVIEWED unless `cad_geometry_parsed=true` with revision/hash traceability. Use the `tools/reference_status.py` validator to detect stale entries. **Vendor override first**, especially crystal: ESP32-S3 RD03 recommends >=2.0 mm from clock pin, unlike generic near-IC heuristics.
- **Do not claim a video was watched in full** when only metadata or chapter description is available. In the current catalog all `M` entries need transcript/visual verification.
- Do not treat 90-degree corners as universal release blocker; prefer clean 45-degree/rounded paths for consistency unless a justified exception exists.
- Do not use DRC=0 as proof of electrical layout correctness.
- If sources conflict, report both viewpoints; evaluate stackup, pin/package, frequency/edge rate, loop area, and datasheet before deciding.
- Follow placement-first/critical-path routing, not arbitrary autoroute.
- Do not silently change another repository's gate meanings. To integrate into host KicadAutoLayout, **explicitly map** rule IDs to its existing check phases.
- Evidence reports must include a link/path to source PCB and revision hash.

## Status reporting
Use `PASS`, `FAIL`, `NEEDS_REVIEW`, `NA` per rule. Output terse actionable review, prioritize blocked risks. A tool failure or unavailable data is NOT a PASS.

## Updating research
When discovering new reference PCBs, update both `REFERENCE_DESIGN_CATALOG.md` and `references/index.json` (source URL, exact revision, published files, evidence status, group, potential PT patterns). Do NOT call Gerber/CAD files parsed until coordinates, nets and polygons were actually extracted. Maintain strict license boundaries.

When discovering new Phil's Lab/Altium Academy videos:
1. Check URL, author/channel, chapters and duplication.
2. Add to its matching catalog with unique PLnn/AAnn/EXnn and `M`.
3. Summarize scope and source-supported takeaways; do not fabricate detailed quotes or numerical requirements.
4. Upgrade to `T` or `V` only after obtaining/examining full transcript or video, with timestamped evidence and review note.
5. Add or revise rules only after explaining scope, testability, priority and exception.
6. Update catalog totals and relevant backlinks. Never silently rewrite prior reviewed cases.
