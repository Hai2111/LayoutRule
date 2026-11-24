# AGENTS.md — instructions for Claude / Codex / KiCadAutoLayout

This repository is the **canonical PCB layout reference**, NOT an automatically validated standards database. Owner-controlled update rules: [GOVERNANCE.md](GOVERNANCE.md). Downstream repos may submit evidence and proposals, but do not modify the upstream rulebook automatically.

## Read order
-0. **`START_HERE.md`** — 1 trang duy nhất: quy trình 3 bước + "chủ chỉ cần xem ảnh". Đọc file này trước khi đọc bất cứ file nào khác.
0. **`rules/owner_decisions.json`** — 35 owner confirmations + explicit later overrides (Q14/Q35 unconfirmed; do not infer), followed by `GOVERNANCE.md` for owner approvals and one-way dependency.
1. `README.md`
2. `LAYOUT_RULES.md`
3. `TECHNICAL_SOURCES.md` (official CAD docs, vendors, IPC standard scope and contradictory advice)
4. `REFERENCE_DESIGN_CATALOG.md`, `references/index.json`, `PLACEMENT_PATTERNS.md` (vendor-specific overrides)
5. `PLACEMENT_ROUTING_WORKFLOW.md`
5a. **`CLOSED_LOOP_RUNBOOK.md`** — local observe → decide → pcbnew action → KiCad DRC/2D images → keep/rollback, with no owner prompts mid-session.
5b. **`ITERATIVE_ROUTING_PLAYBOOK.md` — phương pháp làm theo vùng**: vòng lặp INV-1/2/3 + H1/H2 + visual scan 3 tầng; checkpoint nội bộ, owner chỉ xem bản cuối
5c. `AGENT_LAYOUT_PLAYBOOK.md` + `rules/layout_defaults.json` — nền 5 pha + giá trị khởi điểm D-…
5d. `rules/001-general-layout.md` (starter, tham số DRAFT) + `rules/topology_digests.json` (digest đọc ref design, class boundaries đã chốt)
6. `REVIEW_CHECKLIST.md`
7. `VIDEO_CATALOG.md` + `VIDEO_REVIEWS_EXTERNAL.md` for video chapter, URLs and evidence status
8. `AI_LAYOUT_RESEARCH.md` for experimental routing benchmarks and new academic results (not automatic quality standards)
9. `ROUTING_ENGINE_INTEGRATION.md` for safe Claude routing controller/decision rules and Freerouting KiCad10 tool contracts

**Alternative Freerouting + visual route optimization (EXPERIMENTAL):** use `FREEROUTING_VISUAL_LOOP.md` and `tools/freerouting_visual_loop.py`. This is not a substitute for the canonical owner review contract. Agent inspects actual KiCad F.Cu/B.Cu exports, changes mechanical-safe placements / targeted reroute nets, reruns pinned Freerouting JAR, rejects DRC regressions and retains best isolated candidate. Do not mark as validated until real KiCad benchmark evidence exists.

## Doing placement and routing (foundation approved; closed-loop executor is experimental)
**Local execution:** start `tools/layout_controller.py` from `CLOSED_LOOP_RUNBOOK.md`, not by routing every net manually. Model emits JSON geometry actions; KiCad executor edits only a copy. Native DRC, image exports and geometric checks feed the next model iteration. Keep only independently measured improvements, rollback on regressions, and never replace board master or approve without owner.
**Decision precedence:** Load `rules/owner_decisions.json` before old playbook prose. Explicit `overrides` supersede earlier selected options; `UNCONFIRMED` entries are not permissions. Mechanical-only anchors and final-only owner review take precedence over old region-lock/gate-review text.
When the task is to **produce** a layout rather than review one, follow **`ITERATIVE_ROUTING_PLAYBOOK.md`** (region loop: place → route (agent decides, tool executes) → 3-layer visual scan → logic check; H1 route⇄move continuously, H2 ratsnest map as loop input; internal region evidence; ONE owner review at end of session). Its foundation phases and gates:
1. Write `layout_intent.json` from the schematic before placing anything (net classes with currents, hot loops, decoupling map, blocks, anchors) — see `AGENT_LAYOUT_PLAYBOOK.md`.
2. Floorplan → place inside blocks → route by risk order → functional check. Each phase has a gate; do not pass a gate with an open `FAIL`.
3. When project/fab/vendor data is silent, use the starting value from `rules/layout_defaults.json`, record its id under `assumptions`, and continue. On any hard stop, end the session with one BLOCKED batch report; never interrupt the owner for individual approvals.
4. Run `python tools/layout_audit.py BOARD.kicad_pcb layout_intent.json` at gates G2–G5 in addition to KiCad ERC/DRC. Its PASS is a geometry statement, not electrical proof.
4a. Also run `python tools/drc_body_keepout.py BOARD.kicad_pcb [--exempt REF,NET ...]` to enforce K1 (no trace under component body). Must return 0 violations (excluding declared exemptions) before any P2 routing begins. Calibration: same checker on STM8 V6 Codex = 52 hits, V8 Claude full re-route = 0 hits. See `LESSONS_LEARNED.md` for K1/K2/K3 rules derived from that session.
5. If a net will not route cleanly, change placement; do not route around a bad placement.

**Before each new session**, execute `python tools/review_feedback.py context --history PROJECT/reviews/owner_feedback.jsonl` (or read the ledger directly) and explicitly translate unresolved owner feedback into candidate experiments. **After each owner review**, store verbatim feedback using `review_feedback.py record`; do not promote a global rule just because owner accepted a layout. See REVIEW_LEARNING_LOOP.md.

## Before acting on a PCB
- Read current schematic/board, datasheets, manufacturability, stackup and **project-local** constraints.
- **Reference-gated candidate:** see SESSION_PIPELINE.md and REVIEW_LEARNING_LOOP.md. Before ANY placement/routing mutation, run session_gate.py preflight for ALL reference regions/layers; missing reference = GLOBAL STOP. Validate an independently generated agent candidate by running route_pipeline.ps1 with -Board, -SessionManifest, -CandidateBoard and -IntentPath. The script runs KiCad native DRC plus geometry/keepout audits and never approves or merges anything. -FreeroutingProposal is an explicit experiment, NOT evidence of INV-3 agent-owned routing. Generate one Reference / Candidate REF / Candidate OPT montage and ≤5-line summary **only when the final candidate of the session is ready**. Owner reviews once after the report, not at G1/G3/G5. Capture owner feedback verbatim with board hash and region markers; next session must read it, attempt an evidence-backed repair, and log lessons and counterexamples.

- **Toolchain:** run `powershell -NoProfile -ExecutionPolicy Bypass -File setup\setup.ps1` (or equivalent check on non-Windows) before first use of kicad-cli, Freerouting or the Python audit tools. Pinned versions: [setup/MANIFEST.json](setup/MANIFEST.json).
- Preserve mechanical fit anchors (connector mating, mounting holes, enclosure constraints) as the only immutable placements. Nonmechanical placement, copper and regions remain movable **even after review**; save diffs/hashes and rollback candidates. Detect manually edited placements/tracks; inspect diffs rather than silently replacing them.
- Classify each candidate action with `rule_id`, net/refdes, known facts, confidence, evidence, expected tradeoff, rollback path.
- Never substitute these generic rules for component vendor design requirements.
- Compare agent performance using same source PCB hashes, router/DRC versions, time budgets and reproducible action traces; see `AI_LAYOUT_RESEARCH.md`.
- Check `rules/technical_checks.json` for required inputs and evidence. **These checks are proposals, not executable or validated.** Do not mark them PASS without a board-specific test and project constraints.
- TI TS03 USB 90 ohm +/-15 percent and other source numerical examples are conditional by protocol/PHY; never make them blanket settings for USB-C devices.
- When implementing routing, use explicit source file hashes and scoped candidate runs; prefer agent-controlled KiCad router/API for geometry, with native KiCad DRC and independent reference inspection. Freerouting whole-board route is experimental, not autonomous agent geometry. See the Training repository controller and linked limitations.
- Before treating a reference as a geometry template, check `references/index.json` and mark it PARTIAL when `cad_placement_parsed=true`, NOT REVIEWED unless `cad_geometry_parsed=true` with revision/hash traceability. Use the `tools/reference_status.py` validator to detect stale entries. **Vendor override first**, especially crystal: ESP32-S3 RD03 recommends >=2.0 mm from clock pin, unlike generic near-IC heuristics.
- **Do not claim a video was watched in full** when only metadata or chapter description is available. In the current catalog all `M` entries need transcript/visual verification.
- Do not treat 90-degree corners as universal release blocker; prefer clean 45-degree/rounded paths for consistency unless a justified exception exists.
- Do not use DRC=0 as proof of electrical layout correctness.
- If sources conflict, report both viewpoints; evaluate stackup, pin/package, frequency/edge rate, loop area, and datasheet before deciding.
- Follow placement-first/critical-path routing, not arbitrary autoroute.
- Do not silently change another repository's gate meanings. To integrate into host KicadAutoLayout, **explicitly map** rule IDs to its existing check phases.
- Evidence reports must include a link/path to source PCB and revision hash.

**User-specified scope:** No benchmark PCB assigned yet. The USB-C escape demo from chat is **not** a LayoutRule project/reference. If fab/stackup numbers have not been provided, do not force premature decisions: record conservative assumptions, perform checks, mark genuinely unverifiable risks NEEDS_REVIEW.

## Status reporting
Use `PASS`, `FAIL`, `NEEDS_REVIEW`, `NA` per rule. Output terse actionable review, prioritize blocked risks. A tool failure or unavailable data is NOT a PASS.

## Updating research
**Governance:** These are instructions for drafting change proposals, not for changing canonical `main` without the owner's explicit approval of the exact revision. See `GOVERNANCE.md`; do not infer approval from successful tests or downstream project outcomes. Record provenance and exceptions.

When discovering official standards/technical papers, propose a source ID TSnn in `TECHNICAL_SOURCES.md` with exact accessible edition and provenance. **Do not claim to possess the full paid IPC standards from their free sample/TOC PDFs.**

When discovering new reference PCBs, propose coordinated updates to both `REFERENCE_DESIGN_CATALOG.md` and `references/index.json` (source URL, exact revision, published files, evidence status, group, potential PT patterns). Do NOT call Gerber/CAD files parsed until coordinates, nets and polygons were actually extracted. Maintain strict license boundaries.

When discovering new Phil's Lab/Altium Academy videos:
1. Check URL, author/channel, chapters and duplication.
2. Add to its matching catalog with unique PLnn/AAnn/EXnn and `M`.
3. Summarize scope and source-supported takeaways; do not fabricate detailed quotes or numerical requirements.
4. Upgrade to `T` or `V` only after obtaining/examining full transcript or video, with timestamped evidence and review note.
5. Propose added or revised rules only after explaining scope, testability, priority and exception.
6. Update catalog totals and relevant backlinks. Never silently rewrite prior reviewed cases.
