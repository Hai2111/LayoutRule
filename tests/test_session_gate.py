#!/usr/bin/env python3
"""Regression tests for reference GLOBAL STOP and one-session owner review.

Synthetic PNG/PCB fixtures validate mechanics, NOT electrical correctness.
run: python -m unittest discover -s tests -p 'test_session_gate.py'
"""
import copy
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "session_gate.py"


def tiny_png():
    """Valid 2x2 PNG with RGB pixels; no Pillow dependency."""
    def chunk(name, value):
        return (struct.pack(">I", len(value)) + name + value +
                struct.pack(">I", zlib.crc32(name + value) & 0xffffffff))
    raw = b"".join(b"\x00" + b"\x1f\x86\x20" * 2 for _ in range(2))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


class SessionGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.original = self.root / "source.kicad_pcb"
        self.original.write_text("(kicad_pcb (version 20241229))\n", encoding="utf-8")
        self.original_sha = hashlib.sha256(self.original.read_bytes()).hexdigest()
        for name in ("source_f.png", "source_b.png", "ref_f.png",
                     "ref_b.png", "opt_f.png", "opt_b.png"):
            (self.root / name).write_bytes(tiny_png())
        self.manifest = {
            "schema_version": 1,
            "session_id": "demo-session",
            "board": "source.kicad_pcb",
            "regions": [{
                "id": "R1-power",
                "required_layers": ["F.Cu", "B.Cu"],
                "review_layer": "F.Cu",
                "reference": {
                    "id": "RD01",
                    "source_url": "https://example.com/reference",
                    "source_region": "CIN-U1-L1 screenshot",
                    "applicability": "same buck control topology; check pinout",
                    "observed_features": ["input cap near VIN/GND", "switch loop"],
                    "evidence": {
                        "F.Cu": {"path": "source_f.png", "roi": [0, 0, 1, 1]},
                        "B.Cu": {"path": "source_b.png", "roi": [0, 0, 1, 1]}
                    }
                },
                "candidates": {}
            }]
        }
        for label in ("ref", "opt"):
            board = self.root / f"{label}.kicad_pcb"
            board.write_text(f"(kicad_pcb (version 20241229) (title_block (title \"{label}\")))", encoding="utf-8")
            board_sha = hashlib.sha256(board.read_bytes()).hexdigest()
            write_json(self.root / f"{label}-drc.json", {"violations": [], "unconnected_items": []})
            write_json(self.root / f"{label}-audit.json", {
                "summary": {"board_sha256": board_sha, "counts": {"PASS": 1}},
                "results": [{"status": "PASS", "check": "NET"}]})
            write_json(self.root / f"{label}-ledger.json", {
                "board_sha256": board_sha,
                "nets_ledger": [{"net": "VDD", "layer": "F.Cu",
                                 "reason": "reference and schematic", "tool": "agent",
                                 "outcome": "PASS"}]})
            self.manifest["regions"][0]["candidates"][label] = {
                "branch": f"candidate/{label}", "board": f"{label}.kicad_pcb",
                "images": {
                    "F.Cu": {"path": f"{label}_f.png", "roi": [0, 0, 1, 1]},
                    "B.Cu": {"path": f"{label}_b.png", "roi": [0, 0, 1, 1]}
                },
                "drc": f"{label}-drc.json", "audit": f"{label}-audit.json",
                "routing_ledger": f"{label}-ledger.json"
            }
        self.save()

    def save(self):
        write_json(self.root / "session.json", self.manifest)

    def run_gate(self, command):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), command,
             str(self.root / "session.json"), "--output-dir", str(self.root / "review")],
            text=True, capture_output=True)

    def test_preflight_ready_and_input_unchanged(self):
        p = self.run_gate("preflight")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertEqual(json.loads((self.root / "review" / "preflight.json").read_text())["status"], "READY")
        self.assertEqual(hashlib.sha256(self.original.read_bytes()).hexdigest(), self.original_sha)

    def test_global_stop_if_any_region_missing_bottom_layer(self):
        second = copy.deepcopy(self.manifest["regions"][0])
        second["id"] = "R1-crystal"
        second["reference"]["evidence"].pop("B.Cu")
        self.manifest["regions"].append(second)
        self.save()
        p = self.run_gate("preflight")
        self.assertEqual(p.returncode, 3)
        rep = json.loads((self.root / "review" / "preflight.json").read_text())
        self.assertEqual(rep["status"], "BLOCKED")
        self.assertTrue(any("R1-crystal" in x for x in rep["issues"]))
        self.assertEqual(hashlib.sha256(self.original.read_bytes()).hexdigest(), self.original_sha)

    def test_review_generates_single_embedded_visual_and_evidence(self):
        p = self.run_gate("review")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        summary = (self.root / "review" / "OWNER_REVIEW.md").read_text()
        self.assertEqual(len(summary.strip().splitlines()), 5)
        self.assertIn("READY_FOR_OWNER", summary)
        svg = (self.root / "review" / "session_comparison.svg").read_text()
        self.assertEqual(svg.count("data:image/png;base64,"), 3)
        self.assertIn("REFERENCE", svg)
        self.assertIn("CANDIDATE OPT", svg)
        evidence = json.loads((self.root / "review" / "technical_evidence.json").read_text())
        self.assertEqual(evidence["owner_approval"], "PENDING")
        self.assertEqual(evidence["status"], "READY_FOR_OWNER")

    def test_native_drc_findings_cannot_be_approved(self):
        write_json(self.root / "opt-drc.json", {
            "violations": [{"type": "clearance"}], "unconnected_items": []})
        p = self.run_gate("review")
        self.assertEqual(p.returncode, 4, p.stderr + p.stdout)
        self.assertIn("NEEDS_REVIEW", (self.root / "review" / "OWNER_REVIEW.md").read_text())

    def test_wrong_audit_board_sha_cannot_be_approved(self):
        obj = json.loads((self.root / "opt-audit.json").read_text())
        obj["summary"]["board_sha256"] = "wrong"
        write_json(self.root / "opt-audit.json", obj)
        self.assertEqual(self.run_gate("review").returncode, 4)

    def test_same_branch_is_not_two_candidates(self):
        self.manifest["regions"][0]["candidates"]["opt"]["branch"] = "candidate/ref"
        self.save()
        self.assertEqual(self.run_gate("review").returncode, 4)

    def test_blocked_review_reports_once_without_montage(self):
        self.manifest["regions"][0]["reference"]["evidence"].pop("B.Cu")
        self.save()
        p = self.run_gate("review")
        self.assertEqual(p.returncode, 3, p.stderr + p.stdout)
        self.assertIn("BLOCKED", (self.root / "review" / "OWNER_REVIEW.md").read_text())
        self.assertFalse((self.root / "review" / "session_comparison.svg").exists())

    def test_invalid_audit_summary_does_not_pass(self):
        obj = json.loads((self.root / "opt-audit.json").read_text())
        obj["summary"]["counts"] = {"PASS": 2}
        write_json(self.root / "opt-audit.json", obj)
        self.assertEqual(self.run_gate("review").returncode, 4)

    def test_failed_routing_ledger_does_not_pass(self):
        obj = json.loads((self.root / "ref-ledger.json").read_text())
        obj["nets_ledger"][0]["outcome"] = "FAIL"
        write_json(self.root / "ref-ledger.json", obj)
        self.assertEqual(self.run_gate("review").returncode, 4)

    def test_invalid_or_missing_roi_blocks_reference(self):
        self.manifest["regions"][0]["reference"]["evidence"]["F.Cu"]["roi"] = [0, 0, 0, 1]
        self.save()
        self.assertEqual(self.run_gate("preflight").returncode, 3)


if __name__ == "__main__":
    unittest.main()
