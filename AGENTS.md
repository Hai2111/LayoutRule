# AGENTS.md — instructions for Claude / Codex / KiCadAutoLayout

This repository is a **PCB layout reference**, NOT an automatically validated standards database.

## Read order
1. `README.md`
2. `LAYOUT_RULES.md`
3. `PLACEMENT_ROUTING_WORKFLOW.md`
4. `REVIEW_CHECKLIST.md`
5. `VIDEO_CATALOG.md` for source chapter and evidence status

## Before acting on a PCB
- Read current schematic/board, datasheets, manufacturability, stackup and **project-local** constraints.
- Detect and respect manually edited placements and tracks; diff before applying any change.
- Classify each candidate action with `rule_id`, net/refdes, known facts, confidence, evidence, expected tradeoff, rollback path.
- Never substitute these generic rules for component vendor design requirements.
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
When discovering new Phil's Lab/Altium Academy videos:
1. Check URL, author/channel, chapters and duplication.
2. Add to `VIDEO_CATALOG.md` with unique PLnn/AAnn and `M`.
3. Summarize scope and source-supported takeaways; do not fabricate detailed quotes or numerical requirements.
4. Upgrade to `T` or `V` only after obtaining/examining full transcript or video, with timestamped evidence and review note.
5. Add or revise rules only after explaining scope, testability, priority and exception.
6. Update catalog totals and relevant backlinks. Never silently rewrite prior reviewed cases.
