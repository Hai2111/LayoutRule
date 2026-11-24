#!/usr/bin/env python3
"""Append-only owner feedback ledger for local agent learning across PCB sessions.

This tool records what owner actually said; it NEVER infers approval,
edits PCB, locks a region, or promotes a rule. Source project owns the ledger.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


VERDICTS = ("PASS", "FAIL")  # owner decision only; historical values remain readable


def record(history, session_id, board, feedback, verdict, markers):
    if verdict not in VERDICTS:
        raise ValueError('owner verdict must be PASS (ĐẠT) or FAIL (KHÔNG ĐẠT)')
    text = feedback.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("owner feedback is empty")
    if not board.is_file() or board.suffix != ".kicad_pcb":
        raise ValueError("board must be a real .kicad_pcb file")
    if not session_id.strip():
        raise ValueError("session id missing")
    entry = {
        "schema_version": 1,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "board_path": str(board.resolve()),
        "board_sha256": hashlib.sha256(board.read_bytes()).hexdigest(),
        "owner_feedback_verbatim": text,
        "owner_verdict": verdict,
        "markers": markers,
        "observations": [],
        "hypotheses": [],
        "proposed_experiments": [],
        "checks_required": ["KiCad DRC", "geometry audit", "visual comparison"],
        "next_session_action": "ANALYZE_FEEDBACK_BEFORE_LAYOUT",
        "reusable_rule_status": "NOT_PROMOTED",
        "layout_locked": False,
        "mechanical_anchors_only": True,
    }
    history.parent.mkdir(parents=True, exist_ok=True)
    with history.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return entry


def load(history):
    if not history.is_file():
        return []
    entries = []
    for n, line in enumerate(history.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if not isinstance(item, dict) or "owner_feedback_verbatim" not in item:
                raise ValueError("not a feedback entry")
            entries.append(item)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"corrupt history line {n}: {exc}") from exc
    return entries


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record", help="save owner words for the NEXT agent session")
    rec.add_argument("--history", required=True, type=Path)
    rec.add_argument("--session-id", required=True)
    rec.add_argument("--board", required=True, type=Path)
    rec.add_argument("--feedback-file", required=True, type=Path)
    rec.add_argument("--verdict", required=True, choices=VERDICTS)
    rec.add_argument("--marker", action="append", default=[])
    ctx = sub.add_parser("context", help="read all feedback before new placement/routing")
    ctx.add_argument("--history", required=True, type=Path)
    ctx.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        if args.command == "record":
            e = record(args.history, args.session_id, args.board,
                       args.feedback_file, args.verdict, args.marker)
            print(f"RECORDED: session={e['session_id']} verdict={e['owner_verdict']} board={e['board_sha256'][:12]}")
        else:
            items = load(args.history)
            if args.json:
                print(json.dumps(items, ensure_ascii=False, indent=2))
            else:
                if not items:
                    print("NO_FEEDBACK_HISTORY: this is not proof of a validated routing method.")
                for item in items:
                    print(f"{item['session_id']} [{item['owner_verdict']}] {item['owner_feedback_verbatim']}")
                print(f"FEEDBACK_COUNT={len(items)}; agent must derive scoped fixes and check regression.")
        return 0
    except (OSError, ValueError) as exc:
        ap.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
