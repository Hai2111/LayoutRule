#!/usr/bin/env python3
"""Inspect real KiCad PCB: native DRC, geometry, and 2D F.Cu/B.Cu PNG.

Read-only: no image synthesis or changes to the source PCB.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from layout_audit import Board, seg_len, parse_sexpr, kids, kid
from visual_stage_report import png_metadata


def call(args, *, timeout=180):
    return subprocess.run(list(map(str, args)), text=True, capture_output=True, timeout=timeout)


def observe(board, output, *, kicad_cli="kicad-cli", intent=None, export=True):
    board, output = Path(board).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    geom = Board(board)
    drc_path = output / "drc.json"
    r = call([kicad_cli, "pcb", "drc", "--format", "json", "--severity-all",
              "-o", drc_path, board])
    if not drc_path.is_file():
        raise RuntimeError(f"KiCad native DRC output missing: {r.stderr.strip()}")
    drc = json.loads(drc_path.read_text(encoding="utf-8-sig"))
    if not isinstance(drc.get("violations"), list) or not isinstance(drc.get("unconnected_items"), list):
        raise RuntimeError("invalid native KiCad DRC JSON")
    root = parse_sexpr(board.read_text(encoding="utf-8"))
    tracks = [{"uuid": (kid(t, "uuid") or [None, ""])[1],
               "net_code": (kid(t, "net") or [None, ""])[1],
               "start": (kid(t, "start") or [None])[1:],
               "end": (kid(t, "end") or [None])[1:]}
              for t in kids(root, "segment") + kids(root, "arc")]
    counts = {"drc_errors": len(drc["violations"]), "unconnected": len(drc["unconnected_items"]),
              "audit_fail": 0, "keepout_fail": 0, "via_count": len(geom.vias),
              "trace_mm": round(sum(seg_len(s) for s in geom.segments), 4),
              "board_sha256": geom.sha256, "footprints": geom.refs,
              "tracks": geom.segments, "track_items": tracks, "vias": geom.vias,
              "issues": drc["violations"][:30] + drc["unconnected_items"][:30], "images": {}}
    if intent:
        audit_path = output / "audit.json"
        ar = call([sys.executable, str(Path(__file__).with_name("layout_audit.py")),
                   board, Path(intent).resolve(), "--json", audit_path])
        if audit_path.is_file():
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            statuses = audit.get("summary", {}).get("counts", {})
            counts["audit_fail"] = statuses.get("FAIL", 0) + statuses.get("NEEDS_REVIEW", 0)
            counts["audit_findings"] = [x for x in audit.get("results", [])
                                        if x.get("status") in ("FAIL", "NEEDS_REVIEW")][:30]
        else:
            raise RuntimeError(f"geometry audit missing: {ar.stderr}")
    ko = call([sys.executable, str(Path(__file__).with_name("drc_body_keepout.py")), board])
    counts["keepout_fail"] = 0 if ko.returncode == 0 else 1
    counts["keepout_log"] = (ko.stdout + ko.stderr)[-6000:]
    if export:
        counts["image_evidence"] = {}
        for layer in ("F.Cu", "B.Cu"):
            image_dir = output / layer.replace(".", "_")
            image_dir.mkdir(exist_ok=True)
            # Stale exports are not evidence of the current PCB.
            for old_png in image_dir.glob("*.png"):
                old_png.unlink()
            common = f"{layer[0]}.SilkS,{layer[0]}.CrtYd,Edge.Cuts"
            command = [str(kicad_cli), "pcb", "export", "png",
                       "--exclude-drawing-sheet", "--layers", layer,
                       "--common-layers", common, "--output", str(image_dir), str(board)]
            image_result = call(command)
            images = sorted(image_dir.glob("*.png"))
            if image_result.returncode != 0 or len(images) != 1:
                raise RuntimeError(f"KiCad 2D {layer} export failed or ambiguous: {image_result.stderr}")
            meta = png_metadata(images[0])
            counts["images"][layer] = str(images[0])
            counts["image_evidence"][layer] = {
                "layer": layer, "board_sha256": geom.sha256,
                "png_sha256": meta["sha256"], "dimensions_px": [meta["width"],meta["height"]],
                "export_command": command, "export_exit_code": image_result.returncode
            }
        if Board(board).sha256 != geom.sha256:
            raise RuntimeError("board changed during copper image capture")
    (output / "observation.json").write_text(
        json.dumps(counts, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return counts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--board", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--kicad-cli", default="kicad-cli")
    p.add_argument("--intent", type=Path)
    args = p.parse_args()
    result = observe(args.board, args.output, kicad_cli=args.kicad_cli, intent=args.intent)
    print(json.dumps({k:v for k,v in result.items()
                      if k not in ("footprints","tracks","track_items","vias","issues")},
                     indent=2))


if __name__ == "__main__":
    main()
