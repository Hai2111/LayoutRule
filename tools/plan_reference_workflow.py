#!/usr/bin/env python3
"""Plan an auditable KiCad placement/routing study from LayoutRule's 36-source matrix.

This script selects *reference hypotheses*, not validated designs. It NEVER
modifies a KiCad board, runs autorouting, runs DRC, or promotes upstream rules.

Usage:
  python tools/plan_reference_workflow.py --validate
  python tools/plan_reference_workflow.py --profile mcu-usb --output work_plan.json
  python tools/plan_reference_workflow.py --profile all --output all_reference_work_plan.json
  python tools/plan_reference_workflow.py --profile industrial-fieldbus
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MATRIX = ROOT / "proposals" / "2026-11-16_ALL_36_REFERENCE_MATRIX.json"
DEFAULT_WORKFLOW = ROOT / "proposals" / "2026-11-16_PLACEMENT_ROUTING_WORKFLOW.json"

# Profiles group *research hypotheses*. Actual rules require matching schematic
# topology, exact device-specific datasheets and electrical constraints.
PROFILES = {
    "all": ["POWER", "MIXED_SIGNAL", "INTERFACE", "RF_MCU", "BOARD_REVISIONS", "TRAINING_REFERENCE"],
    "mcu-usb": ["RF_MCU", "INTERFACE", "TRAINING_REFERENCE"],
    "battery-power": ["POWER", "BOARD_REVISIONS", "TRAINING_REFERENCE"],
    "analog-metering": ["MIXED_SIGNAL", "POWER", "TRAINING_REFERENCE"],
    "industrial-fieldbus": ["INTERFACE", "MIXED_SIGNAL", "BOARD_REVISIONS"],
    "rf-module": ["RF_MCU", "BOARD_REVISIONS"],
}


class MatrixError(ValueError):
    pass


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise MatrixError("Missing data: " + str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def validate(matrix: dict, workflow: dict) -> dict:
    items = matrix.get("records", [])
    stages = workflow.get("stages", [])
    ids = [r.get("id") for r in items]
    stage_ids = [s.get("id") for s in stages]
    errors = []
    if len(items) != 36:
        errors.append(f"Expected 36 references, found {len(items)}")
    if len(set(ids)) != len(ids):
        errors.append("Duplicate reference IDs")
    if set(ids) != {f"RD{i:02d}" for i in range(1, 37)}:
        errors.append("Reference IDs are not exactly RD01..RD36")
    if len(set(stage_ids)) != len(stage_ids):
        errors.append("Duplicate WF stage IDs")
    if len(stages) != 13 or set(stage_ids) != {f"WF{i:02d}" for i in range(13)}:
        errors.append("Expected WF00..WF12")
    sid = set(stage_ids)
    for ref in items:
        for key in ["processing_category", "original_catalog_evidence", "result_status", "rule_maturity", "source_urls"]:
            if not ref.get(key):
                errors.append(f"{ref.get('id')} missing {key}")
        if ref.get("processing_category") not in PROFILES["all"]:
            errors.append(f"{ref.get('id')} unknown category")
        if not ref.get("workflow_checks"):
            errors.append(f"{ref.get('id')} has no workflow checks")
        for wf in ref.get("workflow_checks", []):
            if wf not in sid:
                errors.append(f"{ref.get('id')} references unknown stage {wf}")
        if ref.get("rule_maturity") != "DRAFT_HYPOTHESIS_NOT_APPROVED":
            errors.append(f"{ref.get('id')} cannot be automatically approved")
    for stage in stages:
        for dep in stage.get("dependencies", []):
            if dep not in sid:
                errors.append(f"{stage.get('id')} unknown dependency {dep}")
        if not stage.get("soft_failure") or not stage.get("hard_invariants"):
            errors.append(f"{stage.get('id')} missing recovery or invariants")
    if workflow.get("status") != "RESEARCH_PROPOSAL_OWNER_APPROVAL_REQUIRED":
        errors.append("Workflow cannot be interpreted as approved")
    if errors:
        raise MatrixError("\n".join(errors))
    counts = Counter(r["result_status"] for r in items)
    return {"valid": True, "reference_count": len(items), "workflow_stage_count": len(stages),
            "evidence_class_counts": dict(sorted(counts.items())),
            "source_cad_text_read": sum(bool(r["independent_cad_text_read_current_turn"]) for r in items)}


def choose(matrix: dict, workflow: dict, profile: str) -> dict:
    validate(matrix, workflow)
    groups = set(PROFILES[profile])
    refs = [r for r in matrix["records"] if r["processing_category"] in groups]
    wf_by_id = {s["id"]: s for s in workflow["stages"]}
    applied = set(w for r in refs for w in r["workflow_checks"])
    # Mandatory workflow invariants are included even if not explicitly
    # mapped by a selected catalog entry.
    applied.update({"WF00", "WF01", "WF02", "WF03", "WF04", "WF05",
                    "WF06", "WF07", "WF08", "WF09", "WF10", "WF11", "WF12"})
    selected = [wf_by_id[f"WF{i:02d}"] for i in range(13) if f"WF{i:02d}" in applied]
    return {
        "kind": "RESEARCH_EXECUTION_PLAN",
        "status": "PLAN_ONLY_NOT_EXECUTED",
        "profile": profile,
        "used_groups": sorted(groups),
        "source_matrix": "2026-11-16_ALL_36_REFERENCE_MATRIX.json",
        "rulebook_status": "DRAFT_AWAITING_OWNER_REVIEW",
        "selected_reference_count": len(refs),
        "selected_reference_ids": [r["id"] for r in refs],
        "reference_lessons": [
            {"id": r["id"], "title": r["title"],
             "hypothesis": r["relationship_hypothesis"],
             "scope": r["constraints_and_counterexamples"],
             "rule_ids": r["pattern_ids"], "source_urls": r["source_urls"],
             "source_evidence": r["result_status"],
             "cad_blob_sha": r["source_cad"]["blob_sha"] if r["source_cad"] else None}
            for r in refs
        ],
        "workflow": selected,
        "acceptance_policy": workflow["selection_policy"],
        "trial_budget": workflow["resource_budget"],
        "operator_contract": {
            "do_not_stop_on_one_bad_candidate": True,
            "preserve_best_valid_candidate": True,
            "do_not_weaken_actual_ERC_DRC_or_safety_requirements": True,
            "missing_native_tools_means": "NOT_RUN_AND_ACTIONABLE_NEXT_STEPS",
            "rule_promotion": "OWNER_APPROVAL_REQUIRED",
            "original_pcb": "READ_ONLY"
        }
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    ap.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW)
    ap.add_argument("--profile", choices=sorted(PROFILES), default="all")
    ap.add_argument("--validate", action="store_true", help="Validate all 36 rows and stage dependencies")
    ap.add_argument("--output", type=Path, help="Write JSON plan to path; otherwise stdout")
    args = ap.parse_args()
    try:
        matrix = load_json(args.matrix)
        workflow = load_json(args.workflow)
        data = validate(matrix, workflow) if args.validate else choose(matrix, workflow, args.profile)
        content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
        else:
            sys.stdout.write(content)
        return 0
    except (MatrixError, json.JSONDecodeError, OSError) as exc:
        print(f"PLAN_DATA_INVALID: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
