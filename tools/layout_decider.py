#!/usr/bin/env python3
"""Ask local Codex/Claude CLI for JSON PCB actions; the model never edits PCB directly."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

RULES = """You are a PCB placement/routing engineer. Read the observation and recent
review feedback; examine real KiCad copper exports when image access is available.
Optimize a REGION and adjacent nets, not one net to completion at a time.
May move components except fixed mechanical anchors. Never assume DRC PASS proves
electrical validity. If no safe improvement is justified, return
{"actions":[],"rationale":"why"}. Return ONE JSON object and no markdown.
Allowed actions:
move: {"op":"move","ref":"R1","x_mm":12.3,"y_mm":8.1}
rotate: {"op":"rotate","ref":"R1","degrees":90}
remove_track: {"op":"remove_track","uuid":"...","net":"/NET"}
add_trace: {"op":"add_trace","net":"/NET","layer":"F.Cu","width_mm":0.2,"points_mm":[[1,2],[3,4]]}
add_via: {"op":"add_via","net":"/NET","x_mm":1,"y_mm":2,"width_mm":0.6,"drill_mm":0.3}
All coordinates must come from board geometry, nets must exist. Review return
paths, plane cuts, decoupling and adjacent nets; do not invent routing facts.
Output fields: actions (list), rationale (short string)."""


def parse_json_only(text):
    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise ValueError("agent must return exactly one JSON object, not prose") from exc
    if not isinstance(result, dict):
        raise ValueError("agent result must be object")
    return result


def ask(context, provider, *, timeout=240, work_dir=None,
        codex_executable="codex", claude_executable="claude"):
    prompt = RULES + "\n\nCONTEXT JSON:\n" + json.dumps(context, ensure_ascii=False, default=str)
    if provider not in ("codex", "claude"):
        raise ValueError("provider must be codex or claude")
    with tempfile.TemporaryDirectory(prefix="pcb_agent_") as td:
        if provider == "codex":
            output = Path(td) / "answer.json"
            cmd = [codex_executable, "exec", "--sandbox", "read-only",
                   "--output-last-message", str(output)]
            for image in context.get("review_png", []):
                if Path(image).is_file():
                    cmd.extend(["--image", str(image)])
            cmd.append("-")
            result = subprocess.run(cmd, input=prompt, text=True, capture_output=True,
                                    cwd=str(work_dir) if work_dir else None, timeout=timeout)
            if result.returncode != 0 or not output.is_file():
                raise RuntimeError(f"Codex decision failed: {(result.stderr+result.stdout)[-2000:]}")
            return parse_json_only(output.read_text(encoding="utf-8"))
        result = subprocess.run([claude_executable, "-p", "--output-format", "text"],
                                input=prompt, text=True, capture_output=True,
                                cwd=str(work_dir) if work_dir else None, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(f"Claude decision failed: {result.stderr[-2000:]}")
        return parse_json_only(result.stdout)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--context", required=True, type=Path)
    p.add_argument("--provider", choices=("codex","claude"), default="codex")
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    context = json.loads(args.context.read_text(encoding="utf-8"))
    plan = ask(context, args.provider, work_dir=args.context.parent)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
