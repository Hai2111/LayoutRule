#!/usr/bin/env python3
"""Prepare an isolated KiCad placement/rip-up candidate for a Freerouting pass.

The operation is intentionally limited to placement and entire-net rip-up:
Freerouting reconstructs the copper.  This prevents stale pad-attached tracks
when moving a footprint.  No edits to the source board.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

OPS = {"move", "rotate", "reroute_net"}


def validate_actions(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("rationale"), str):
        raise ValueError("agent plan must contain a rationale")
    actions = plan.get("actions")
    if not isinstance(actions, list) or not 0 <= len(actions) <= 12:
        raise ValueError("agent plan must contain 0..12 actions")
    seen = set()
    for action in actions:
        if not isinstance(action, dict) or action.get("op") not in OPS:
            raise ValueError("only move, rotate and reroute_net are permitted")
        op = action["op"]
        if op in ("move", "rotate"):
            ref = action.get("ref")
            if not isinstance(ref, str) or not ref.strip():
                raise ValueError("move/rotate needs a nonempty footprint ref")
            key = (op, ref)
            if key in seen:
                raise ValueError("duplicate placement action")
            seen.add(key)
            fields = ("x_mm", "y_mm") if op == "move" else ("degrees",)
            for k in fields:
                v = action.get(k)
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                    raise ValueError(f"invalid {k}")
        else:
            name = action.get("net")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("reroute_net requires an existing net name")
    return plan


def apply(board_path, output, plan, *, mechanical_anchors, protected_nets=(),
          max_ripup_items=300):
    import pcbnew as pcb
    validate_actions(plan)
    board_path, output = Path(board_path).resolve(), Path(output).resolve()
    if board_path == output:
        raise ValueError("never overwrite the source board")
    if not board_path.is_file() or board_path.suffix != ".kicad_pcb" or output.suffix != ".kicad_pcb":
        raise ValueError("must use existing source and distinct target .kicad_pcb")
    if not isinstance(mechanical_anchors, list) or any(
            not isinstance(v, str) for v in mechanical_anchors):
        raise ValueError("mechanical anchors must be an explicit array")
    fixed = set(mechanical_anchors)
    protected = set(protected_nets)
    source_hash = hashlib.sha256(board_path.read_bytes()).hexdigest()
    board = pcb.LoadBoard(str(board_path))
    if board is None:
        raise RuntimeError("pcbnew failed to load source")
    refs = {fp.GetReference(): fp for fp in board.GetFootprints()}
    existing_nets = {t.GetNetname() for t in board.GetTracks()}
    for fp in board.GetFootprints():
        existing_nets.update(pad.GetNetname() for pad in fp.Pads())
    reroute = set()
    edits = []
    for action in plan["actions"]:
        op = action["op"]
        if op in ("move", "rotate"):
            ref = action["ref"]
            if ref in fixed:
                raise ValueError(f"cannot move mechanical anchor {ref}")
            if ref not in refs:
                raise ValueError(f"unknown footprint {ref}")
            footprint = refs[ref]
            reroute.update(p.GetNetname() for p in footprint.Pads() if p.GetNetname())
            if op == "move":
                footprint.SetPosition(pcb.VECTOR2I(pcb.FromMM(action["x_mm"]),
                                                   pcb.FromMM(action["y_mm"])))
            else:
                footprint.SetOrientationDegrees(action["degrees"])
            edits.append(f"{op}:{ref}")
        else:
            net = action["net"]
            if net not in existing_nets:
                raise ValueError(f"unknown net {net}")
            reroute.add(net)
            edits.append(f"reroute:{net}")
    reroute.discard("")
    if reroute & protected:
        raise ValueError(f"attempt to rip-up protected nets: {sorted(reroute & protected)}")
    if len(reroute) > 12:
        raise ValueError("too many nets affected by one agent decision")
    removal = [t for t in list(board.GetTracks()) if t.GetNetname() in reroute]
    if len(removal) > max_ripup_items:
        raise ValueError("large rip-up refused; split the optimization into regions")
    for track in removal:
        board.Remove(track)
    # pcbnew zone refill, rather than assuming previous filled polygons stay valid.
    if len(plan["actions"]) and hasattr(pcb, "ZONE_FILLER"):
        pcb.ZONE_FILLER(board).Fill(board.Zones())
    output.parent.mkdir(parents=True, exist_ok=True)
    pcb.SaveBoard(str(output), board)
    if hashlib.sha256(board_path.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError("source PCB was altered")
    if not output.is_file():
        raise RuntimeError("prepared board not written")
    return {"actions":edits, "ripup_nets":sorted(reroute),
            "ripup_items":len(removal), "source_sha256":source_hash}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--board", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--mechanical", type=Path, required=True)
    p.add_argument("--protected", type=Path)
    args = p.parse_args()
    protected = json.loads(args.protected.read_text(encoding="utf-8")) if args.protected else []
    result = apply(args.board,args.output,json.loads(args.plan.read_text(encoding="utf-8")),
                   mechanical_anchors=json.loads(args.mechanical.read_text(encoding="utf-8")),
                   protected_nets=protected)
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":
    main()
