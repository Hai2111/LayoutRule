#!/usr/bin/env python3
"""Closed-loop orchestration regression; real KiCad smoke test is still separate."""
import hashlib
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
la = types.ModuleType("layout_audit")
la.Board = object
la.seg_len = lambda s: 1
la.parse_sexpr = lambda s: []
la.kids = lambda a,b: []
la.kid = lambda a,b: None
sys.modules["layout_audit"] = la
sg = types.ModuleType("session_gate")
sg.preflight = lambda data,base: {"status":"READY","issues":[]}
sys.modules["session_gate"] = sg
rf = types.ModuleType("review_feedback")
rf.load = lambda path: []
sys.modules["review_feedback"] = rf
from candidate_evaluator import compare
from kicad_executor import validate_plan
import layout_controller as ctrl


class CandidateComparison(unittest.TestCase):
    def setUp(self):
        self.start = {"board_sha256":"A","drc_errors":0,"unconnected":4,
                      "audit_fail":0,"keepout_fail":0,"via_count":3,"trace_mm":20}

    def test_better_connectivity_is_accepted(self):
        self.assertTrue(compare(self.start,{**self.start,"board_sha256":"B","unconnected":3})[0])

    def test_drc_regression_forces_rollback(self):
        self.assertFalse(compare(self.start,{**self.start,"board_sha256":"B","unconnected":1,"drc_errors":1})[0])

    def test_extra_via_without_electrical_gain_is_rejected(self):
        self.assertFalse(compare(self.start,{**self.start,"board_sha256":"B","via_count":4,"trace_mm":18})[0])

    def test_same_board_is_not_improvement(self):
        self.assertFalse(compare(self.start,self.start)[0])


class StrictExecutorValidation(unittest.TestCase):
    def test_valid_local_route(self):
        validate_plan({"actions":[{"op":"add_trace","net":"VDD","layer":"F.Cu",
                                    "width_mm":0.2,"points_mm":[[1,1],[2,2]]}]})

    def test_reject_unknown_command_and_zero_segment(self):
        for action in ({"op":"shell","command":"rm -rf ."},
                       {"op":"add_trace","net":"VDD","layer":"F.Cu",
                        "width_mm":0.2,"points_mm":[[1,1],[1,1]]}):
            with self.assertRaises(ValueError):
                validate_plan({"actions":[action]})


class ClosedLoop(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.board = self.root / "source.kicad_pcb"
        self.board.write_text("(kicad_pcb (version 20241229))")
        self.sha = hashlib.sha256(self.board.read_bytes()).hexdigest()
        self.manifest = self.root / "session.json"
        self.manifest.write_text(json.dumps({"board":"source.kicad_pcb","submission_stage":"G3"}))
        self.intent = self.root / "intent.json"
        self.intent.write_text(json.dumps({"mechanical_anchor_refs":["J1"]}))
        self.work = self.root / "work"

    def mock_observe(self, src, out):
        data = Path(src).read_text()
        return {"board_sha256":hashlib.sha256(Path(src).read_bytes()).hexdigest(),
                "drc_errors":1 if "BAD" in data else 0,
                "unconnected":4 if "BETTER" not in data else 3,
                "audit_fail":0,"keepout_fail":0,"via_count":3,
                "trace_mm":20.0,"images":{},"footprints":{},"tracks":[],"vias":[]}

    def mock_executor(self, src, dest, plan, path):
        shutil.copy2(src, dest)
        with open(dest,"a") as file:
            file.write("\n"+plan["rationale"])
        return {"candidate_sha256":hashlib.sha256(dest.read_bytes()).hexdigest()}

    def test_one_accepted_then_rejected_drc_worsening(self):
        plans = iter(["BETTER","BAD"])

        def decide(ctx):
            rationale = next(plans)
            return {"actions":[{"op":"move","ref":"R1","x_mm":2,"y_mm":4}],
                    "rationale":rationale}

        result = ctrl.loop(self.board,self.manifest,self.intent,self.work,iterations=2,
                           decision_fn=decide,execution_fn=self.mock_executor,
                           observation_fn=self.mock_observe)
        self.assertEqual([x["status"] for x in result["history"]],["KEEP","ROLLBACK"])
        self.assertIn("BETTER",(self.work/"best_candidate.kicad_pcb").read_text())
        self.assertNotIn("BAD",(self.work/"best_candidate.kicad_pcb").read_text())
        self.assertEqual(hashlib.sha256(self.board.read_bytes()).hexdigest(),self.sha)
        self.assertFalse((self.work/"OWNER_REVIEW.md").exists())
        self.assertFalse(result["owner_approved"])

    def test_no_anchor_list_fails_closed(self):
        self.intent.write_text("{}")
        with self.assertRaisesRegex(ValueError,"mechanical_anchor_refs"):
            ctrl.loop(self.board,self.manifest,self.intent,self.work,iterations=1,
                      decision_fn=lambda x:None,execution_fn=self.mock_executor,
                      observation_fn=self.mock_observe)

    def test_explicit_global_stop_prevents_edit(self):
        original = ctrl.preflight
        try:
            ctrl.preflight = lambda manifest,base: {"status":"BLOCKED","issues":["no reference"]}
            result = ctrl.loop(self.board,self.manifest,self.intent,self.work,iterations=1,
                               decision_fn=lambda x:None,execution_fn=self.mock_executor,
                               observation_fn=self.mock_observe)
            self.assertEqual(result["status"],"BLOCKED")
            self.assertFalse((self.work/"best_candidate.kicad_pcb").exists())
        finally:
            ctrl.preflight = original


if __name__=="__main__":
    unittest.main()
