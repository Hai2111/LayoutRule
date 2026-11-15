#!/usr/bin/env python3
"""Count and export source-indexed PCB layout videos. Standard library only."""
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(
    r'^\|\s*(PL\d\d|AA\d\d|EX\d\d)\s*\|\s*\[([^]]+)\]\((https?://[^)]+)\)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*(M|T|V)\s*\|$'
)

def collect(catalog: Path) -> list:
    records = []
    for line_num, line in enumerate(catalog.read_text(encoding="utf-8").splitlines(), 1):
        match = PATTERN.match(line)
        if match:
            vid, title, url, chapters, summary, rules, status = match.groups()
            records.append({
                "id": vid, "title": title, "url": url,
                "chapters": chapters.strip(), "summary": summary.strip(),
                "rule_ids": rules.strip(), "status": status,
                "source_catalog": str(catalog.name), "line": line_num
            })
    return records

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", action="append", type=Path,
                   help="Override defaults; use multiple times to include more catalogs.")
    p.add_argument("--json-output", type=Path)
    p.add_argument("--csv-output", type=Path)
    a = p.parse_args()
    sources = a.catalog or [
        ROOT / "VIDEO_CATALOG.md", ROOT / "VIDEO_REVIEWS_EXTERNAL.md"
    ]
    rows = [record for file in sources for record in collect(file)]
    ids = Counter(r["id"] for r in rows)
    duplicated_ids = sorted(k for k, v in ids.items() if v > 1)
    urls = Counter(r["url"] for r in rows)
    duplicated_urls = sorted(k for k, v in urls.items() if v > 1)
    if duplicated_ids or duplicated_urls:
        raise SystemExit(f"duplicate video ids: {duplicated_ids}; duplicate URLs: {duplicated_urls}")
    status_counts = Counter(r["status"] for r in rows)
    channel_counts = Counter(
        ("Phil's Lab" if r["id"].startswith("PL") else
         "Altium Academy" if r["id"].startswith("AA") else
         "External review") for r in rows
    )
    report = {
        "unique_videos": len(rows),
        "by_channel": dict(channel_counts),
        "by_status": {k: status_counts[k] for k in ("M", "T", "V")},
        "catalog_files": [str(x) for x in sources],
        "records": rows
    }
    print(json.dumps({k: v for k, v in report.items() if k != "records"},
                     indent=2, ensure_ascii=False))
    if a.json_output:
        a.json_output.parent.mkdir(parents=True, exist_ok=True)
        a.json_output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if a.csv_output:
        a.csv_output.parent.mkdir(parents=True, exist_ok=True)
        with a.csv_output.open("w", newline="", encoding="utf-8-sig") as out:
            fields = ["id", "title", "url", "chapters", "summary",
                      "rule_ids", "status", "source_catalog", "line"]
            writer = csv.DictWriter(out, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

if __name__ == "__main__":
    main()
