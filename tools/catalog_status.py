#!/usr/bin/env python3
"""Summarize videos in VIDEO_CATALOG.md (source of truth). Standard library only."""
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

PATTERN = re.compile(r'^\|\s*(PL\d\d|AA\d\d)\s*\|\s*\[([^]]+)\]\((https?://[^)]+)\)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*(M|T|V)\s*\|$')

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--catalog', type=Path, default=Path(__file__).resolve().parents[1] / 'VIDEO_CATALOG.md')
    p.add_argument('--json-output', type=Path)
    p.add_argument('--csv-output', type=Path)
    a = p.parse_args()
    rows = []
    for line_no, line in enumerate(a.catalog.read_text(encoding='utf-8').splitlines(), 1):
        m = PATTERN.match(line)
        if m:
            vid, title, url, chapter, summary, rules, status = m.groups()
            rows.append({'id': vid, 'title': title, 'url': url, 'chapters': chapter.strip(), 'summary': summary.strip(), 'rule_ids': rules.strip(), 'status': status, 'line': line_no})
    ids = [r['id'] for r in rows]
    duplicates = [k for k, c in Counter(ids).items() if c > 1]
    if duplicates:
        raise SystemExit('Duplicate IDs: ' + ', '.join(duplicates))
    counts = Counter(r['status'] for r in rows)
    channels = Counter('Phil Lab' if r['id'].startswith('PL') else 'Altium Academy' for r in rows)
    report = {'unique_videos': len(rows), 'by_channel': dict(channels), 'by_status': {s: counts[s] for s in ('M','T','V')}, 'records': rows}
    print(json.dumps({k:v for k,v in report.items() if k != 'records'}, indent=2, ensure_ascii=False))
    if a.json_output:
        a.json_output.parent.mkdir(parents=True, exist_ok=True)
        a.json_output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    if a.csv_output:
        a.csv_output.parent.mkdir(parents=True, exist_ok=True)
        with a.csv_output.open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=['id','title','url','chapters','summary','rule_ids','status','line'])
            writer.writeheader()
            writer.writerows(rows)

if __name__ == '__main__':
    main()
