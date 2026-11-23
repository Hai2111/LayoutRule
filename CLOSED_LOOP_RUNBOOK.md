# Local closed-loop controller — experimental

**Purpose:** make locally installed Codex/Claude iterate PCB placement and routing, using real KiCad board geometry.

```text
reference preflight -> observe native KiCad PCB & DRC -> local AI decisions
 -> pcbnew edits isolated candidate -> native DRC & actual F/B copper image
 -> candidate evaluator KEEP or ROLLBACK -> repeat -> final-only owner report
```

## Components
- `layout_controller.py`: repeat bounded iteration; preserve source PCB/hash and candidate isolation.
- `layout_decider.py`: invoke existing local Codex/Claude CLI for JSON action proposal (not new AI).
- `kicad_executor.py`: move/rotate footprints; remove UUID track; add segments/vias with pcbnew.
- `layout_observer.py`: **real** KiCad DRC, geometry/body-keepout and F.Cu/B.Cu PNG exports.
- `candidate_evaluator.py`: block DRC/connectivity/audit regressions; require measurable improvement.
- `review_feedback.py`: read prior owner feedback before next session.

## Run on Windows with KiCad 10 and Codex CLI available

```powershell
& "C:\Program Files\KiCad\10.0\bin\python.exe" tools\layout_controller.py --board "D:\project\board.kicad_pcb" --manifest "D:\project\session.json" --intent "D:\project\layout_intent.json" --work-dir "D:\project\agent_loop" --provider codex --iterations 8 --kicad-python "C:\Program Files\KiCad\10.0\bin\python.exe" --kicad-cli "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
```

Replace paths with **the PCB owner provides later**. Use `--provider claude` for Claude Code. The CLI should be authenticated locally.

- `session.json` follows `SESSION_PIPELINE.md`; `submission_stage` is an **internal stage** such as `G3` while iterating. All reference evidence required by global preflight must be present; otherwise **GLOBAL STOP**.
- `layout_intent.json` must explicitly include `"mechanical_anchor_refs": ["J1", "H1"]` or `[]` if there truly are none. Do not infer anchored positions from refdes. Only genuine mechanical-fit anchors are immutable. Placement and copper are not locked by review.
- The script retains a matching `.kicad_pro` beside candidate copies when present, never overwrites source PCB, and writes `best_candidate.kicad_pcb`, `iterations.json`, `session_progress.json`, native DRC JSON and KiCad-exported 2D images.
- Only `FINAL` in session gate generates owner review. Continue G1/G3/G5 internally. When two candidate branches and verified images are ready, run `session_gate.py review` with `submission_stage: FINAL` for one end-of-session owner review.

## Boundaries

**Not yet a mature intelligent autorouter.** `pcbnew` edits straight tracks and vias, **not** KiCad GUI push-and-shove. Validation of real pad escape, image cognition, zone refill, electronics/return-path quality and native on-host KiCad execution is **PENDING** until a real board is supplied. A `KEEP` means improvement by implemented checks; not electrical validation or owner acceptance. No automatic merge to `main`.
