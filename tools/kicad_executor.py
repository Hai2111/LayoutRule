#!/usr/bin/env python3
"""Apply a constrained local KiCad PCB action plan to a COPY, never source board.

Requires KiCad's Python exposing pcbnew. Not a push-and-shove routing engine.
Candidates MUST pass native KiCad DRC before reuse.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

ALLOWED = {"move", "rotate", "remove_track", "add_trace", "add_via"}
LAYERS = {"F.Cu": "F_Cu", "B.Cu": "B_Cu"}


def positive_number(value, name, zero=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if not zero and value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def validate_plan(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("actions"), list):
        raise ValueError("plan needs actions list")
    if not 0 < len(plan["actions"]) <= 50:
        raise ValueError("plan must contain 1..50 actions")
    for action in plan["actions"]:
        if not isinstance(action, dict) or action.get("op") not in ALLOWED:
            raise ValueError("unsupported action operation")
        op = action["op"]
        if op in ("move", "rotate"):
            if not isinstance(action.get("ref"), str) or not action["ref"]:
                raise ValueError("missing footprint reference")
            if op == "move":
                for k in ("x_mm", "y_mm"):
                    positive_number(action.get(k), k, zero=True)
            else:
                positive_number(action.get("degrees"), "degrees", zero=True)
        if op == "remove_track":
            if not isinstance(action.get("uuid"), str) or not action["uuid"]:
                raise ValueError("track removal requires exact UUID")
            if not isinstance(action.get("net"), str) or not action["net"]:
                raise ValueError("track removal requires net name")
        if op in ("add_trace", "add_via"):
            if not isinstance(action.get("net"), str) or not action["net"]:
                raise ValueError("new copper requires non-empty existing net")
            positive_number(action.get("width_mm"), "width_mm")
            if op == "add_trace":
                if action.get("layer") not in LAYERS:
                    raise ValueError("only F.Cu and B.Cu track supported")
                points = action.get("points_mm")
                if not isinstance(points, list) or not (2 <= len(points) <= 100):
                    raise ValueError("points_mm needs 2..100 points")
                for p in points:
                    if not isinstance(p, list) or len(p) != 2:
                        raise ValueError("invalid trace coordinate")
                    for v in p:
                        positive_number(v, "coordinate", zero=True)
                for a, b in zip(points, points[1:]):
                    if a == b:
                        raise ValueError("zero length segment")
            else:
                for key in ("x_mm", "y_mm", "drill_mm"):
                    positive_number(action.get(key), key, zero=key != "drill_mm")
                if action["drill_mm"] >= action["width_mm"]:
                    raise ValueError("via drill must be smaller than diameter")
    return plan


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply(source, target, plan, mechanical_anchors):
    import pcbnew as pcb
    validate_plan(plan)
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        raise ValueError("never edit source board in-place")
    if not source.is_file() or source.suffix != ".kicad_pcb" or target.suffix != ".kicad_pcb":
        raise ValueError("source/output must be .kicad_pcb files")
    original_sha = sha(source)
    board = pcb.LoadBoard(str(source))
    if board is None:
        raise ValueError("pcbnew failed to load board")
    refs = {fp.GetReference(): fp for fp in board.GetFootprints()}
    anchors = set(mechanical_anchors)
    if not all(isinstance(x, str) for x in anchors):
        raise ValueError("invalid mechanical anchor list")

    def point(coords):
        return pcb.VECTOR2I(pcb.FromMM(coords[0]), pcb.FromMM(coords[1]))

    for action in plan["actions"]:
        op, net = action["op"], action.get("net")
        if op in ("move", "rotate"):
            ref = action["ref"]
            if ref in anchors:
                raise ValueError(f"mechanical anchor immutable: {ref}")
            if ref not in refs:
                raise ValueError(f"unknown footprint: {ref}")
            if op == "move":
                refs[ref].SetPosition(point([action["x_mm"], action["y_mm"]]))
            else:
                refs[ref].SetOrientationDegrees(action["degrees"])
            continue
        if op == "remove_track":
            found = [t for t in list(board.GetTracks())
                     if str(t.GetUuid().AsString()) == action["uuid"]]
            if len(found) != 1 or found[0].GetNetname() != net:
                raise ValueError("track UUID/net mismatch; refuse rip-up")
            board.Remove(found[0])
            continue
        netcode = board.GetNetcodeFromNetname(net)
        if not isinstance(netcode, int) or netcode <= 0:
            raise ValueError(f"net not defined in PCB: {net}")
        if op == "add_trace":
            layer_id = getattr(pcb, LAYERS[action["layer"]])
            for p0, p1 in zip(action["points_mm"], action["points_mm"][1:]):
                t = pcb.PCB_TRACK(board)
                t.SetStart(point(p0))
                t.SetEnd(point(p1))
                t.SetWidth(pcb.FromMM(action["width_mm"]))
                t.SetLayer(layer_id)
                t.SetNetCode(netcode)
                board.Add(t)
        elif op == "add_via":
            via = pcb.PCB_VIA(board)
            via.SetPosition(point([action["x_mm"], action["y_mm"]]))
            try:
                via.SetWidth(pcb.FromMM(action["width_mm"]))
            except TypeError:
                via.SetWidth(pcb.F_Cu, pcb.FromMM(action["width_mm"]))
            via.SetDrill(pcb.FromMM(action["drill_mm"]))
            via.SetViaType(pcb.VIATYPE_THROUGH)
            via.SetLayerPair(pcb.F_Cu, pcb.B_Cu)
            via.SetNetCode(netcode)
            board.Add(via)
    target.parent.mkdir(parents=True, exist_ok=True)
    pcb.SaveBoard(str(target), board)
    if not target.is_file() or sha(source) != original_sha:
        raise RuntimeError("failed to save candidate or source board changed")
    return {"source_sha256": original_sha, "candidate_sha256": sha(target),
            "actions": len(plan["actions"]), "mechanical_anchors": sorted(anchors)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--actions", type=Path, required=True)
    parser.add_argument("--mechanical", type=Path, required=True,
                        help="JSON array of fixed mechanical refs from project intent")
    args = parser.parse_args()
    plan = json.loads(args.actions.read_text(encoding="utf-8"))
    mechanical = json.loads(args.mechanical.read_text(encoding="utf-8"))
    if not isinstance(mechanical, list):
        parser.error("mechanical anchor file must be JSON list")
    print(json.dumps(apply(args.source, args.output, plan, mechanical), indent=2))


if __name__ == "__main__":
    main()
