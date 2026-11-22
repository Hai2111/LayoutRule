#!/usr/bin/env python3
"""Fail-closed reference preflight and single-session visual review for KiCad candidates.

Stdlib only. Reads input boards/images/reports; never modifies PCB or merges Git.
Reference images must be actual board/datasheet screenshots, not synthesized art.
Use a separate candidate branch for REF and OPT and obtain owner approval to merge.
"""
import argparse
import base64
import hashlib
import json
import struct
import sys
from pathlib import Path
from xml.sax.saxutils import escape


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(base, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected non-empty file path")
    return (base / value).resolve()


def png_info(path):
    raw = path.read_bytes()
    if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise ValueError("image is not a PNG (export a real PCB/reference screenshot)")
    width, height = struct.unpack(">II", raw[16:24])
    if not 0 < width <= 100000 or not 0 < height <= 100000:
        raise ValueError("invalid PNG dimensions")
    return width, height


def panel(base, evidence, errors, tag):
    if not isinstance(evidence, dict):
        errors.append(f"{tag}: image record missing")
        return None
    try:
        path = resolve(base, evidence.get("path"))
        if not path.is_file():
            raise ValueError("image not found")
        width, height = png_info(path)
        roi = evidence.get("roi")
        if not (isinstance(roi, list) and len(roi) == 4
                and all(isinstance(v, (float, int)) and not isinstance(v, bool) for v in roi)
                and 0 <= roi[0] < roi[2] <= 1 and 0 <= roi[1] < roi[3] <= 1):
            raise ValueError("roi must be normalized [x0,y0,x1,y1] enclosing the traced region")
        return {"path": str(path), "sha256": sha(path), "size": [width, height], "roi": roi}
    except (OSError, ValueError) as exc:
        errors.append(f"{tag}: {exc}")
        return None


def preflight(manifest, base):
    errors, regions = [], []
    if manifest.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not isinstance(manifest.get("session_id"), str) or not manifest["session_id"].strip():
        errors.append("session_id required")
    try:
        board = resolve(base, manifest.get("board"))
        if not board.is_file() or board.suffix != ".kicad_pcb":
            raise ValueError("input .kicad_pcb not found")
        board_sha = sha(board)
    except (OSError, ValueError) as exc:
        errors.append(f"board: {exc}")
        board_sha = None
    items = manifest.get("regions")
    if not isinstance(items, list) or not items:
        errors.append("regions must be a non-empty list")
        items = []
    seen = set()
    for index, region in enumerate(items):
        if not isinstance(region, dict):
            errors.append(f"regions[{index}]: expected object")
            continue
        rid = region.get("id")
        if not isinstance(rid, str) or not rid.strip() or rid in seen:
            errors.append(f"regions[{index}]: unique non-empty id required")
            continue
        seen.add(rid)
        required = region.get("required_layers")
        if not isinstance(required, list) or not required or any(
                not isinstance(x, str) or not x for x in required) or len(required) != len(set(required)):
            errors.append(f"{rid}: required_layers must be distinct names")
            required = []
        source = region.get("reference")
        if not isinstance(source, dict):
            errors.append(f"{rid}: reference record required")
            source = {}
        for field in ("id", "source_url", "source_region", "applicability"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                errors.append(f"{rid}: reference.{field} required")
        observed = source.get("observed_features")
        if not isinstance(observed, list) or not observed or not all(
                isinstance(v, str) and v.strip() for v in observed):
            errors.append(f"{rid}: reference.observed_features required")
        visual = source.get("evidence")
        if not isinstance(visual, dict):
            errors.append(f"{rid}: reference.evidence must map layer to annotated PNG evidence")
            visual = {}
        images = {}
        for layer in required:
            images[layer] = panel(base, visual.get(layer), errors, f"{rid}: reference {layer}")
        review_layer = region.get("review_layer")
        if review_layer not in required:
            errors.append(f"{rid}: review_layer must be one of required_layers")
        regions.append({"id": rid, "required_layers": required,
                        "review_layer": review_layer, "reference": images})
    return {"status": "BLOCKED" if errors else "READY", "board_sha256": board_sha,
            "issues": errors, "regions": regions}


def candidate_check(base, candidate, required, rid, label):
    problems, images = [], {}
    if not isinstance(candidate, dict):
        return {"status": "NEEDS_REVIEW", "issues": ["candidate record missing"], "images": {}}
    branch = candidate.get("branch")
    if not isinstance(branch, str) or not branch.strip():
        problems.append("branch missing")
    try:
        board = resolve(base, candidate.get("board"))
        if not board.is_file() or board.suffix != ".kicad_pcb":
            raise ValueError("candidate .kicad_pcb missing")
        board_sha = sha(board)
    except (OSError, ValueError) as exc:
        problems.append(f"board: {exc}")
        board_sha = None
    for layer in required:
        images[layer] = panel(base, (candidate.get("images") or {}).get(layer),
                              problems, f"{rid}/{label} {layer}")
    counts = {}
    try:
        drc = read_json(resolve(base, candidate.get("drc")))
        for key in ("violations", "unconnected_items"):
            if not isinstance(drc.get(key), list):
                raise ValueError(f"KiCad DRC missing list {key}")
            counts[key] = len(drc[key])
        if any(counts.values()):
            problems.append(f"native KiCad DRC findings: {counts}")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        problems.append(f"native DRC unavailable/invalid: {exc}")
    try:
        audit = read_json(resolve(base, candidate.get("audit")))
        if not isinstance(audit.get("results"), list) or not audit["results"]:
            raise ValueError("layout audit results missing")
        acounts = audit.get("summary", {}).get("counts", {})
        if not isinstance(acounts, dict):
            raise ValueError("audit counts missing")
        counts["audit"] = acounts
        if acounts.get("FAIL", 0) or acounts.get("NEEDS_REVIEW", 0):
            problems.append(f"layout audit findings: {acounts}")
        if audit.get("summary", {}).get("board_sha256") != board_sha:
            problems.append("layout audit board SHA256 mismatch")
    except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        problems.append(f"layout audit unavailable/invalid: {exc}")
    try:
        ledger = read_json(resolve(base, candidate.get("routing_ledger")))
        nets = ledger.get("nets_ledger")
        if not isinstance(nets, list) or not nets:
            raise ValueError("nets_ledger missing/empty")
        if ledger.get("board_sha256") != board_sha:
            problems.append("routing ledger board SHA256 mismatch")
        for net in nets:
            if not isinstance(net, dict) or not all(net.get(k) for k in ("net", "layer", "reason", "tool", "outcome")):
                problems.append("routing ledger has unexplained net")
                break
    except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        problems.append(f"routing ledger unavailable/invalid: {exc}")
    return {"status": "NEEDS_REVIEW" if problems else "ELIGIBLE",
            "issues": problems, "branch": branch, "board_sha256": board_sha,
            "drc": counts, "images": images}


def image_markup(record, x, y, w, h):
    path = Path(record["path"])
    iw, ih = record["size"]
    fitted = min(w / iw, h / ih)
    fw, fh = iw * fitted, ih * fitted
    px, py = x + (w - fw) / 2, y + (h - fh) / 2
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    a, b, c, d = record["roi"]
    return (f'<image x="{px:.2f}" y="{py:.2f}" width="{fw:.2f}" height="{fh:.2f}" '
            f'href="data:image/png;base64,{b64}"/>'
            f'<rect x="{px+a*fw:.2f}" y="{py+b*fh:.2f}" '
            f'width="{(c-a)*fw:.2f}" height="{(d-b)*fh:.2f}" '
            f'fill="none" stroke="#ff9b30" stroke-width="4"/>')


def svg_review(rows, output):
    pane_w, pane_h, gap, top, row_h = 575, 390, 15, 90, 430
    height = top + len(rows) * row_h + 25
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="{height}" viewBox="0 0 1800 {height}">',
             '<rect width="100%" height="100%" fill="#15202b"/>',
             '<text x="20" y="37" font-size="23" font-family="Arial" fill="#ffffff">PCB session review — actual source images</text>']
    for col, head in enumerate(("REFERENCE", "CANDIDATE REF", "CANDIDATE OPT")):
        parts.append(f'<text x="{20+col*(pane_w+gap)}" y="67" font-size="18" '
                     f'font-family="Arial" fill="#ffffff">{head}</text>')
    for i, row in enumerate(rows):
        y = top + i * row_h
        parts.append(f'<text x="20" y="{y+18}" font-size="18" font-family="Arial" '
                     f'fill="#ffffff">{escape(row["id"])} — {escape(row["layer"])}</text>')
        for col, record in enumerate(row["panels"]):
            x = 20 + col * (pane_w + gap)
            parts.append(f'<rect x="{x}" y="{y+28}" width="{pane_w}" height="{pane_h}" '
                         'fill="#263543" stroke="#56677b" stroke-width="2"/>')
            parts.append(image_markup(record, x + 5, y + 33, pane_w - 10, pane_h - 10))
    parts.append('</svg>')
    output.write_text("\n".join(parts), encoding="utf-8")


def review(manifest, base, result, output):
    evidence, pictures, issues = {}, [], list(result["issues"])
    refs = {r["id"]: r for r in result["regions"]}
    for region in manifest.get("regions", []):
        rid = region.get("id")
        if rid not in refs:
            continue
        layer = refs[rid]["review_layer"]
        candidates = region.get("candidates") or {}
        r = candidate_check(base, candidates.get("ref"), refs[rid]["required_layers"], rid, "REF")
        o = candidate_check(base, candidates.get("opt"), refs[rid]["required_layers"], rid, "OPT")
        if r.get("branch") and r.get("branch") == o.get("branch"):
            issues.append(f"{rid}: REF and OPT must be separate Git branches")
        evidence[rid] = {"reference_id": region.get("reference", {}).get("id"),
                         "source_region": region.get("reference", {}).get("source_region"),
                         "ref": r, "opt": o}
        for label, value in (("REF", r), ("OPT", o)):
            if value["status"] != "ELIGIBLE":
                issues.extend(f"{rid}/{label}: {problem}" for problem in value["issues"])
        if (layer and refs[rid]["reference"].get(layer) and r["images"].get(layer)
                and o["images"].get(layer)):
            pictures.append({"id": rid, "layer": layer,
                             "panels": [refs[rid]["reference"][layer],
                                        r["images"][layer], o["images"][layer]]})
    if result["status"] == "BLOCKED":
        status = "BLOCKED"
    elif issues:
        status = "NEEDS_REVIEW"
    else:
        status = "READY_FOR_OWNER"  # no automatic acceptance or merge
    output.mkdir(parents=True, exist_ok=True)
    montage = output / "session_comparison.svg"
    if pictures:
        svg_review(pictures, montage)
    report = {"session_id": manifest.get("session_id"), "status": status,
              "board_sha256": result["board_sha256"], "preflight": result,
              "candidates": evidence, "issues": issues, "montage": str(montage) if pictures else None,
              "owner_approval": "PENDING"}
    (output / "technical_evidence.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = [
        f"# {manifest.get('session_id', 'Session')} — {status}",
        f"Reference: {len(refs)} vùng; đối chiếu có ảnh: {len(pictures)} vùng.",
        "Candidate: " + (", ".join("{} REF={} OPT={}".format(k, v["ref"]["status"], v["opt"]["status"]) for k, v in evidence.items()) or "chưa có") + ".",
        f"Chặn/cần xem: {len(issues)} mục (chi tiết trong technical_evidence.json).",
        "Quyết định: chờ owner duyệt một lần; KHÔNG merge/sửa PCB chính thức."
    ]
    (output / "OWNER_REVIEW.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    return status


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("preflight", "review"))
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--output-dir", type=Path, default=Path("session_review"))
    args = ap.parse_args()
    try:
        mfile = args.manifest.resolve()
        manifest = read_json(mfile)
        if not isinstance(manifest, dict):
            raise ValueError("manifest root must be object")
        result = preflight(manifest, mfile.parent)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"BLOCKED: invalid session manifest: {exc}", file=sys.stderr)
        return 3
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.command == "preflight":
        (output / "preflight.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{result['status']}: {len(result['issues'])} reference preflight issue(s)")
        for item in result["issues"]:
            print(f"- {item}")
        return 0 if result["status"] == "READY" else 3
    status = review(manifest, mfile.parent, result, output)
    print(f"{status}: {output / 'OWNER_REVIEW.md'}")
    return 0 if status == "READY_FOR_OWNER" else 3 if status == "BLOCKED" else 4


if __name__ == "__main__":
    sys.exit(main())
