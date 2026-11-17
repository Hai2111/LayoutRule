#!/usr/bin/env python3
"""Regression test for tools/layout_audit.py on synthetic fixtures (stdlib only).
The fixtures are hand-made boards, not real designs: they prove the tool reads
geometry and grades it as intended, not that any threshold is electrically right.
run: python tests/test_layout_audit.py
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"


def audit(board):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "r.json"
        p = subprocess.run([sys.executable, str(ROOT / "tools" / "layout_audit.py"),
                            str(FIX / board), str(FIX / "demo_intent.json"), "--json", str(out)],
                           capture_output=True, text=True)
        return p.returncode, json.loads(out.read_text(encoding="utf-8"))


class LayoutAuditTest(unittest.TestCase):
    def test_good_board_has_no_findings(self):
        for board in ("demo_good.kicad_pcb", "demo_good_named_nets.kicad_pcb"):
            code, rep = audit(board)
            self.assertEqual(code, 0, board)
            self.assertNotIn("FAIL", rep["summary"]["counts"], board)
            self.assertNotIn("NEEDS_REVIEW", rep["summary"]["counts"], board)

    def test_bad_board_is_caught(self):
        code, rep = audit("demo_bad.kicad_pcb")
        self.assertEqual(code, 1)
        failed = {r["check"] for r in rep["results"] if r["status"] == "FAIL"}
        self.assertEqual(failed, {"W-POWER", "VIA-POWER", "NET-VIAS", "DECAP", "DECAP-GND",
                                  "HOT-LOOP-SEG", "DIFF-SKEW", "REF-SLOT"})
        review = {r["check"] for r in rep["results"] if r["status"] == "NEEDS_REVIEW"}
        self.assertEqual(review, {"HOT-LOOP-CLEAR", "REF-ZONE", "REF-SLOT-TOTAL"})

    def test_rotated_footprint_pad_position(self):
        _, rep = audit("demo_good.kicad_pcb")
        seg = next(r for r in rep["results"] if r["check"] == "HOT-LOOP-SEG")
        self.assertAlmostEqual(seg["measured"], 1.53, places=2)


if __name__ == "__main__":
    unittest.main()
