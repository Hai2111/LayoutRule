#!/usr/bin/env python3
"""Visual reasoning for Freerouting iterations. JSON decisions only; no PCB edits."""
import json
import subprocess
import tempfile
from pathlib import Path

from freerouting_prepare import validate_actions

INSTRUCTIONS = """Act as an independent PCB design reviewer, not a net-completion bot.
You are looking at ACTUAL KiCad F.Cu and B.Cu exports of a Freerouting candidate.
Study placement, pad escape, trace turns, via burden, congestion, return path,
decoupling, net constraints, and interactions between adjacent nets.
The copper picture is evidence, not proof of SI/EMI; use board geometry and
native KiCad DRC to ground each recommendation.

Freerouting will reroute the result after you modify the PRE-ROUTE board.
You may propose ONLY:
 {"op":"move","ref":"R1","x_mm":12.5,"y_mm":8.0}
 {"op":"rotate","ref":"U1","degrees":90}
 {"op":"reroute_net","net":"/EXACT_NET_NAME"}
The executor automatically removes existing copper of nets connected to any
moved footprint and of explicitly rerouted nets; do not edit raw trace points.
No moving mechanical anchors and no moving a net's connector for convenience.
Prefer a targeted local alteration affecting 1 or 2 footprints/nets; evaluate
neighboring connections globally. Do NOT simply route one net to completion.
If the design is already as good as the evidence supports, return no actions.
Return strict JSON: {"actions":[],"rationale":"specific visual/geometry finding",
"expected_improvement":"testable hypothesis"}. No markdown or explanation outside JSON.
"""


def select_context(context):
    """Keep vision prompts within reasonable size on medium/large PCBs."""
    obs = context["observation"]
    return {
        "iteration": context["iteration"],
        "source_board": context["source_board"],
        "mechanical_anchors": context["mechanical_anchors"],
        "protected_nets": context.get("protected_nets", []),
        "drc_errors": obs.get("drc_errors"),
        "unconnected": obs.get("unconnected"),
        "audit_fail": obs.get("audit_fail"),
        "keepout_fail": obs.get("keepout_fail"),
        "via_count": obs.get("via_count"),
        "trace_mm": obs.get("trace_mm"),
        "footprints": obs.get("footprints", {}),
        "issues": obs.get("issues", [])[:35],
        "audit_findings": obs.get("audit_findings", [])[:30],
        "track_items": obs.get("track_items", [])[:150],
        "previous_attempts": context.get("previous_attempts", [])[-4:],
        "previous_owner_feedback": context.get("owner_feedback", [])[-6:],
        "rulebook_path": context.get("rulebook_path"),
        "intent_path": context.get("intent_path"),
        "image_layers": list(obs.get("images", {}).keys())
    }


def ask(context, *, provider="codex", timeout=300, codex_bin="codex",
        claude_bin="claude"):
    images = context["observation"].get("images", {})
    if not all(layer in images and Path(images[layer]).is_file()
               for layer in ("F.Cu", "B.Cu")):
        raise RuntimeError("both real KiCad copper images are required before AI decision")
    prompt = INSTRUCTIONS + "\nContext:\n" + json.dumps(select_context(context),ensure_ascii=False,default=str)
    with tempfile.TemporaryDirectory(prefix="pcb_visual_") as temp:
        out = Path(temp)/"response.json"
        if provider == "codex":
            cmd = [codex_bin,"exec","--sandbox","read-only",
                   "--image",str(images["F.Cu"]),"--image",str(images["B.Cu"]),
                   "--output-last-message",str(out),"-"]
            result = subprocess.run(cmd,input=prompt,text=True,capture_output=True,
                                    timeout=timeout)
            if result.returncode != 0 or not out.is_file():
                raise RuntimeError(f"Codex vision failed: {result.stderr[-1000:]}")
            raw = out.read_text(encoding="utf-8")
        elif provider == "claude":
            # Claude Code reads local image bytes through Read, not through stdin.
            prompt += ("\nMUST use Read tool on both local image files before deciding: "
                       +str(images["F.Cu"])+" ; "+str(images["B.Cu"]))
            cmd=[claude_bin,"-p","--allowedTools","Read","--output-format","text"]
            result=subprocess.run(cmd,input=prompt,text=True,capture_output=True,timeout=timeout)
            if result.returncode:
                raise RuntimeError(f"Claude visual decision failed: {result.stderr[-1000:]}")
            raw=result.stdout
        else:
            raise ValueError("provider must be codex or claude")
    try:
        plan=json.loads(raw.strip())
    except json.JSONDecodeError as exc:
        raise ValueError("visual agent must return a single strict JSON object") from exc
    validate_actions(plan)
    return plan
