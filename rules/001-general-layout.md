# 001 — General layout & clearance starter (PROPOSED, DRAFT parameters)

**Status:** PROPOSED (parameters still DRAFT — not validated against any fab; do not treat as pass/fail gate)
**Tier:** HEURISTIC (starting values only, per `rules/layout_defaults.json` precedence: project > fab > vendor > these)
**Owner:** Hai · **Proposed:** 2026-11-20 · **Base commit:** 071417f

## Scope / Applies to

- Prototype FR-4 boards, 2–4 layers, no extreme fab constraints (no fine-line/buried-via fab).
- Default starting point when project constraints, fab capability and vendor docs are silent.
- **Not applicable:** RF boards (use P07/R11 + antenna keepout rules), high-current power stages (use R04 + D-WIDTH/D-VDROP), high-speed signals (use R02/R07 + stackup-controlled impedance).

## Proposed parameters

> Values below are DRAFT and intentionally mirror `fab_profile_fallback` (D-FAB) in `rules/layout_defaults.json` so both stay in one place; this file only adds the assembly-side items D-FAB does not cover.

| Parameter | Draft value | Unit | Basis | Note |
|---|---|---|---|---|
| Clearance net-to-net / net-to-copper | 0.2 | mm | PRACTICE | mirrors D-FAB `clearance_min_mm` |
| Track width, signal (min) | 0.2 | mm | PRACTICE | mirrors D-FAB `track_min_mm` |
| Track width, power | by current | mm | CALC | use D-WIDTH table, never a flat "min width" (A02/R04) |
| Via, signal | drill 0.3 / dia 0.6 | mm | PRACTICE | mirrors D-FAB `via_signal` |
| Via, power | drill 0.4 / dia 0.8 | mm | PRACTICE | mirrors D-FAB `via_power` |
| Component keepout to board edge | 1.0 | mm | PRACTICE | mirrors D-FAB `component_to_edge_mm` |
| **Silkscreen to pad** | **0.1** | mm | PRACTICE | *new* — keeps silkscreen off solder pad, avoids mask bridging |
| **Component-to-component (body/courtyard)** | **0.25** | mm | PRACTICE | *new* — DFM/rework access; allows tighter where verified |
| **Testpoint / rework access** | **2.0** | mm | PRACTICE | *new* — keep clear zone around at least one access point per net class of interest |

## Why

Owner requested a starter rule so agents doing generic prototype boards have explicit, reviewable numbers instead of inventing them per run. Every value above is PRACTICE-level, not verified: the rule is a floor for *starting* a layout, not a gate; each value the agent actually uses must still be logged in `layout_intent.json` assumptions (per `layout_defaults.json` how_to_use).

## Exceptions & counterexamples

- Fine-pitch fab (e.g. 4/6 layer, 0.1 mm/0.1 mm capability) → fab numbers replace all DRAFT values (A02).
- Board with mechanical/connector envelope (e.g. `ref/Kicad/BLE2LTE`, `LTE Network card`) → edge/mount rules from P01 override edge keepout.
- Anything vendor-specified (antenna matching network, crystal per P05) overrides this file.

## Risk of misapplication

- An agent reading this as HARD could reject valid fine-pitch designs; hence tier HEURISTIC + PROPOSED status.
- `silkscreen_to_pad` and the two DFM items are not checked by any current tool in `tools/`; they are review-checklist items only.

## Provenance & evidence (per GOVERNANCE.md)

- Downstream source: local ref design `D:/Data/hai/app/Kicad/Rule&Ref/ref/Kicad/RA01_SCH_PCB/RA-01SCH_SMOKE.kicad_pcb` — SHA256 `d7e9819d1744dd8a2c6c79930547ce4cb26aa5ef3d7371ab1dd6e93cb2f08ebb` (used only to confirm a 2-layer FR-4 prototype as the applicability example, no rule derived from its geometry).
- Rulebook base commit: `071417f` (main).
- No measurement taken from the ref board; values are PRACTICE, consistent with existing D-FAB fallback profile.

## Validation plan (before owner can move to VALIDATED/APPROVED)

1. Pick two of the 10 converted ref projects, run `tools/drc_body_keepout.py` + KiCad DRC with these DRAFT values as board-setup constraints, record violations.
2. Compare each violation against fab capability sheet (JLCPCB standard: min 0.12 mm/0.12 mm, min drill 0.3 mm) — expect 0.2 mm clearances to pass; document which do not.
3. Owner adjudicates per GOVERNANCE: scope (2-layer prototypes only?), then promote/adjust in `LAYOUT_RULES.md` and, if machine-enforced, add a matching entry in `rules/technical_checks.json` (next free TC ID).

## Rollback

Delete this file and revert any `technical_checks.json` entry added on approval; D-FAB in `layout_defaults.json` is untouched by this proposal.
