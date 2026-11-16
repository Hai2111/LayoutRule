"""Contract tests for the proposed 36-source planner (no KiCad dependency)."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "plan_reference_workflow.py"
spec = importlib.util.spec_from_file_location("plan_reference_workflow", SCRIPT)
planner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planner)


class WorkflowContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = planner.load_json(planner.DEFAULT_MATRIX)
        cls.workflow = planner.load_json(planner.DEFAULT_WORKFLOW)

    def test_all_36_references_and_13_phases(self):
        result = planner.validate(self.matrix, self.workflow)
        self.assertEqual(result["reference_count"], 36)
        self.assertEqual(result["workflow_stage_count"], 13)
        self.assertEqual(result["source_cad_text_read"], 10)

    def test_all_profile_requires_owner_approval(self):
        plan = planner.choose(self.matrix, self.workflow, "all")
        self.assertEqual(plan["selected_reference_count"], 36)
        self.assertEqual(plan["status"], "PLAN_ONLY_NOT_EXECUTED")
        self.assertEqual(plan["rulebook_status"], "DRAFT_AWAITING_OWNER_REVIEW")
        self.assertTrue(plan["operator_contract"]["original_pcb"] == "READ_ONLY")

    def test_focused_profiles(self):
        for profile, expected in [
            ("mcu-usb", 17), ("battery-power", 14),
            ("analog-metering", 21), ("industrial-fieldbus", 16),
            ("rf-module", 10),
        ]:
            with self.subTest(profile=profile):
                plan = planner.choose(self.matrix, self.workflow, profile)
                self.assertEqual(plan["selected_reference_count"], expected)
                self.assertEqual(len(plan["workflow"]), 13)
                self.assertEqual(len(plan["selected_reference_ids"]),
                                 len(set(plan["selected_reference_ids"])))

    def test_negative_routing_reference_is_not_accepted(self):
        case = next(v for v in self.matrix["records"] if v["id"] == "RD36")
        self.assertEqual(case["source_cad"]["segments"], 0)
        self.assertEqual(case["result_status"], "NEGATIVE_ROUTING_REFERENCE")
        self.assertFalse(any(v["rule_maturity"] == "APPROVED"
                             for v in self.matrix["records"]))

    def test_invalid_rule_reference_detected(self):
        import copy
        bad = copy.deepcopy(self.matrix)
        bad["records"][0]["workflow_checks"] = ["WF99"]
        with self.assertRaises(planner.MatrixError):
            planner.validate(bad, self.workflow)

    def test_bad_missing_approval_state_detected(self):
        import copy
        bad = copy.deepcopy(self.workflow)
        bad["status"] = "APPROVED"
        with self.assertRaises(planner.MatrixError):
            planner.validate(self.matrix, bad)


if __name__ == "__main__":
    unittest.main()
