#!/usr/bin/env python3
"""Owner decision register integrity checks (no KiCad runtime needed)."""
import json
import unittest
from pathlib import Path

REGISTER = Path(__file__).resolve().parents[1] / "rules" / "owner_decisions.json"


class OwnerDecisionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(REGISTER.read_text(encoding="utf-8"))

    def test_all_numbered_questions_present_once(self):
        q = self.data["questions"]
        self.assertEqual(len(q), 35)
        self.assertEqual([x["id"] for x in q],
                         [f"Q{i:02d}" for i in range(1, 36)])
        self.assertEqual(
            {s: sum(x["state"] == s for x in q) for s in
             ("SELECTED", "FREEFORM_CONFIRMED", "UNCONFIRMED")},
            {"SELECTED": 32, "FREEFORM_CONFIRMED": 1, "UNCONFIRMED": 2})
        self.assertEqual(
            [x["id"] for x in q if x["state"] == "UNCONFIRMED"],
            ["Q14", "Q35"])
        self.assertEqual([x["id"] for x in q if x["state"] == "FREEFORM_CONFIRMED"],
                         ["Q22"])

    def test_no_invented_option_or_implicit_approval(self):
        for q in self.data["questions"]:
            if q["state"] == "SELECTED":
                self.assertIn(q["selected_option"], {"A", "B", "C"})
            else:
                self.assertNotIn("selected_option", q)
        self.assertEqual(self.data["authority"], "PROPOSED_IN_PR_NOT_MERGED_TO_MAIN")
        self.assertTrue(self.data["owner_workflow"]["owner_acceptance_required"])

    def test_overrides_are_explicit_and_traceable(self):
        qids = {q["id"] for q in self.data["questions"]}
        overrides = self.data["overrides"]
        ids = {x["id"] for x in overrides}
        self.assertEqual(len(ids), len(overrides))
        self.assertEqual(len(overrides), self.data["stats"]["post_question_overrides"])
        for override in overrides:
            self.assertTrue(override["from"])
            self.assertTrue(override["decision"])
            self.assertTrue(set(override.get("supersedes", [])).issubset(qids))
        by_q = {q["id"]: q for q in self.data["questions"]}
        for q in by_q.values():
            self.assertTrue(set(q.get("superseded_by", [])).issubset(ids))
        self.assertEqual(by_q["Q02"]["superseded_by"], ["OVR-REVIEW-FINAL-ONLY"])
        self.assertEqual(by_q["Q06"]["superseded_by"], ["OVR-NO-LAYOUT-LOCK"])

    def test_final_review_and_only_mechanical_anchors(self):
        workflow = self.data["owner_workflow"]
        self.assertEqual(workflow["review_frequency"], "ONE_REVIEW_AFTER_FINAL_SESSION_REPORT")
        self.assertEqual(workflow["owner_review_outcomes"], ["PASS", "FAIL"])
        self.assertEqual(workflow["owner_review_labels"], {"PASS":"ĐẠT","FAIL":"KHÔNG ĐẠT"})
        self.assertTrue(workflow["mechanical_anchors_only"])
        self.assertFalse(workflow["freeze_layout_after_review"])
        self.assertEqual(workflow["reference_missing_behavior"], "GLOBAL_STOP")
        self.assertFalse(workflow["usb_c_demo_in_scope"])
        self.assertEqual(workflow["benchmark_board"], "NOT_ASSIGNED")


if __name__ == "__main__":
    unittest.main()
