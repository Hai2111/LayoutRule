#!/usr/bin/env python3
"""Review-feedback ledger regression (stdlib only; no KiCad dependency)."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "review_feedback.py"


class ReviewFeedbackTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.board = self.root / "board.kicad_pcb"
        self.board.write_text("(kicad_pcb (version 20241229))\n", encoding="utf-8")
        self.feedback = self.root / "owner.txt"
        self.feedback.write_text("Chân thoát U1 quá rối, cần dời R1.\n", encoding="utf-8")
        self.history = self.root / "reviews" / "owner_feedback.jsonl"

    def command(self, *args):
        return subprocess.run([sys.executable, str(TOOL), *map(str, args)],
                              text=True, capture_output=True)

    def save(self, verdict="FAIL"):
        return self.command("record", "--history", self.history,
                            "--session-id", "s1", "--board", self.board,
                            "--feedback-file", self.feedback, "--verdict", verdict,
                            "--marker", "R1-P03")

    def test_record_verbatim_with_sha_and_no_layout_lock(self):
        result = self.save()
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = [json.loads(s) for s in self.history.read_text().splitlines()]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["owner_feedback_verbatim"], "Chân thoát U1 quá rối, cần dời R1.")
        self.assertEqual(saved[0]["owner_verdict"], "FAIL")
        self.assertEqual(saved[0]["markers"], ["R1-P03"])
        self.assertEqual(saved[0]["board_sha256"], hashlib.sha256(self.board.read_bytes()).hexdigest())
        self.assertFalse(saved[0]["layout_locked"])
        self.assertEqual(saved[0]["reusable_rule_status"], "NOT_PROMOTED")

    def test_append_and_next_session_context(self):
        self.assertEqual(self.save("FAIL").returncode, 0)
        self.feedback.write_text("Được, bản cuối đạt.", encoding="utf-8")
        self.assertEqual(self.save("PASS").returncode, 0)
        p = self.command("context", "--history", self.history, "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = json.loads(p.stdout)
        self.assertEqual([x["owner_verdict"] for x in rows], ["FAIL", "PASS"])
        self.assertEqual(rows[1]["owner_feedback_verbatim"], "Được, bản cuối đạt.")

    def test_reject_empty_feedback_without_writing(self):
        self.feedback.write_text("    ", encoding="utf-8")
        self.assertNotEqual(self.save().returncode, 0)
        self.assertFalse(self.history.exists())

    def test_only_two_owner_outcomes_allowed(self):
        for legacy in ("ACCEPT", "REVISE", "REJECT", "DEFER"):
            self.assertNotEqual(self.save(legacy).returncode, 0)
            self.assertFalse(self.history.exists())

    def test_reject_missing_board(self):
        self.board.unlink()
        self.assertNotEqual(self.save().returncode, 0)
        self.assertFalse(self.history.exists())


if __name__ == "__main__":
    unittest.main()
