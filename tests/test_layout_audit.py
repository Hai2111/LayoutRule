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


def audit(board, intent=None):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "r.json"
        p = subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "layout_audit.py"),
                            str(board if Path(board).is_absolute() else FIX / board),
                            str(intent or FIX / "demo_intent.json"), "--json", str(out)],
                           capture_output=True, text=True)
        return p.returncode, json.loads(out.read_text(encoding="utf-8"))


def audit_text(pcb_body, intent):
    """run the audit on a minimal board given as s-expression text"""
    with tempfile.TemporaryDirectory() as tmp:
        b, i = Path(tmp) / "t.kicad_pcb", Path(tmp) / "t.json"
        b.write_text('(kicad_pcb (version 20260206)\n' + pcb_body + ')\n', encoding="utf-8")
        i.write_text(json.dumps(intent), encoding="utf-8")
        return audit(b, i)[1]["results"]


def fp(ref, x, y, pads):
    body = "".join(f'(pad "{n}" smd rect (at {dx} {dy}) (size 0.6 0.6) (layers "F.Cu") (net "{net}"))'
                   for n, dx, dy, net in pads)
    return f'(footprint "t:{ref}" (layer "F.Cu") (at {x} {y}) (property "Reference" "{ref}") {body})\n'


def seg(a, b, layer, net, w=0.5):
    return f'(segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width {w}) (layer "{layer}") (net "{net}"))\n'


def via(x, y, net, drill=0.4):
    return f'(via (at {x} {y}) (size 0.8) (drill {drill}) (layers "F.Cu" "B.Cu") (net "{net}"))\n'


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

    # --- regressions for the Codex review findings on PR #3 ---
    def test_arc_is_measured_along_the_curve(self):
        pcb = fp("U1", 0, 0, [("1", 0, 0, "N")]) + \
            '(arc (start 0 0) (mid 5 5) (end 10 0) (width 0.2) (layer "F.Cu") (net "N"))\n'
        res = audit_text(pcb, {"nets": {"N": {"class": "signal", "max_length_mm": 12}}})
        row = next(r for r in res if r["check"] == "NET-LENGTH")
        self.assertAlmostEqual(row["measured"], 15.71, places=2)
        self.assertEqual(row["status"], "FAIL")

    def test_serial_vias_are_not_passed_as_parallel(self):
        pads = fp("U1", 0, 0, [("1", 0, 0, "P")])
        intent = {"nets": {"P": {"class": "power", "current_a": 1.0}}}
        serial = pads + via(10, 10, "P") + via(12, 10, "P") + seg((10, 10), (12, 10), "B.Cu", "P") + \
            seg((5, 10), (10, 10), "F.Cu", "P") + seg((12, 10), (17, 10), "F.Cu", "P")
        row = next(r for r in audit_text(serial, intent) if r["check"] == "VIA-POWER")
        self.assertEqual(row["status"], "NEEDS_REVIEW")
        parallel = pads + via(10, 10, "P") + via(10, 11, "P") + \
            seg((10, 10), (10, 11), "F.Cu", "P") + seg((10, 10), (10, 11), "B.Cu", "P")
        row = next(r for r in audit_text(parallel, intent) if r["check"] == "VIA-POWER")
        self.assertEqual(row["status"], "PASS")

    def test_decap_return_uses_the_capacitors_own_ground(self):
        pcb = fp("U1", 0, 0, [("1", 0, 0, "VDD"), ("2", 0, 1, "GND")]) + \
            fp("C1", 1.5, 0, [("1", -0.5, 0, "VDD"), ("2", 0.5, 0, "GND")]) + \
            via(2.0, 0, "GND_ISO") + via(9, 9, "GND")
        intent = {"nets": {"GND": {"class": "gnd"}, "GND_ISO": {"class": "gnd"}, "VDD": {"class": "power"}},
                  "decoupling": [{"pin": "U1.1", "cap": "C1"}]}
        row = next(r for r in audit_text(pcb, intent) if r["check"] == "DECAP-GND")
        self.assertGreater(row["measured"], 5)            # the isolated-ground via at the pad is ignored
        self.assertEqual(row["status"], "FAIL")

    def test_unknown_diff_pair_type_is_not_graded_as_usb(self):
        pcb = fp("U1", 0, 0, [("1", 0, 0, "TXP"), ("2", 0, 1, "TXN")]) + \
            seg((0, 0), (10, 0), "F.Cu", "TXP", 0.2) + seg((0, 1), (10, 1), "F.Cu", "TXN", 0.2)
        pair = {"name": "ETH_TX", "p": "TXP", "n": "TXN", "type": "ethernet_100base_tx"}
        rows = [r for r in audit_text(pcb, {"nets": {}, "diff_pairs": [pair]}) if r["check"].startswith("DIFF")]
        self.assertEqual([r["status"] for r in rows], ["NEEDS_REVIEW"])
        pair.update(skew_target_mm=0.5, skew_review_mm=1.0, max_vias_per_line=2)
        rows = [r for r in audit_text(pcb, {"nets": {}, "diff_pairs": [pair]}) if r["check"] == "DIFF-SKEW"]
        self.assertEqual(rows[0]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
