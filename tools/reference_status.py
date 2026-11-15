#!/usr/bin/env python3
"""Validate reference index against the Markdown catalog, export review queue CSV.
No external network calls; stdlib only. Missing downloaded CAD is NOT a pass.
"""
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ID_PATTERN = re.compile(r'^\|\s*(RD\d\d)\s*\|', re.MULTILINE)

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", type=Path, default=ROOT / "REFERENCE_DESIGN_CATALOG.md")
    p.add_argument("--index", type=Path, default=ROOT / "references/index.json")
    p.add_argument("--csv-output", type=Path)
    a = p.parse_args()
    data = json.loads(a.index.read_text(encoding="utf-8"))
    records = data.get("references", [])
    indexed = [r["id"] for r in records]
    documented = ID_PATTERN.findall(a.catalog.read_text(encoding="utf-8"))
    duplicated = [i for i, n in Counter(indexed).items() if n > 1]
    missing = sorted(set(documented) - set(indexed))
    extra = sorted(set(indexed) - set(documented))
    invalid_urls = [
        r["id"] for r in records
        if not r.get("source_urls") or any(not u.startswith("https://") for u in r["source_urls"])
    ]
    count_mismatch = data.get("count") != len(records) or len(indexed) != len(documented)
    summary = {
        "references": len(records),
        "evidence": dict(Counter(r.get("evidence_status", "UNKNOWN") for r in records)),
        "cad_geometry_parsed": sum(bool(r.get("cad_geometry_parsed")) for r in records),
        "electrically_verified_by_us": sum(bool(r.get("electrically_verified_by_us")) for r in records),
        "duplicated_ids": duplicated,
        "missing_from_json": missing,
        "missing_from_markdown": extra,
        "invalid_urls": invalid_urls,
        "count_mismatch": count_mismatch,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if a.csv_output:
        a.csv_output.parent.mkdir(parents=True, exist_ok=True)
        with a.csv_output.open("w", newline="", encoding="utf-8-sig") as out:
            fields = ["id", "title", "evidence_status", "cad_geometry_parsed",
                      "electrically_verified_by_us", "source_url"]
            wr = csv.DictWriter(out, fieldnames=fields)
            wr.writeheader()
            wr.writerows({
                "id": r["id"], "title": r["title"],
                "evidence_status": r["evidence_status"],
                "cad_geometry_parsed": r["cad_geometry_parsed"],
                "electrically_verified_by_us": r["electrically_verified_by_us"],
                "source_url": r["source_urls"][0],
            } for r in records)
    if duplicated or missing or extra or invalid_urls or count_mismatch:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
