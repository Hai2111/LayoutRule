import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import session_start as s  # noqa: E402


class SessionStartTest(unittest.TestCase):
    def test_ipc_widths(self):
        self.assertAlmostEqual(s.ipc_width_mm(3), 1.37, places=2)
        self.assertAlmostEqual(s.ipc_width_mm(2), 0.78, places=2)
        self.assertAlmostEqual(s.ipc_width_mm(1), 0.30, places=2)

    def test_polygon_area(self):
        self.assertEqual(s.polygon_area([(0, 0), (4, 0), (4, 3), (0, 3)]), 12)

    def test_gate_blocks_until_every_todo_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            report = Path(d) / "SESSION_START.md"
            report.write_text("- board_top.png: TODO\n- fix order and reason: TODO\n", encoding="utf-8")
            self.assertEqual(s.main(["check", str(report)]), 3)
            report.write_text("- board_top.png: buck loop is large\n- fix order and reason: placement first\n", encoding="utf-8")
            self.assertEqual(s.main(["check", str(report)]), 0)


if __name__ == "__main__":
    unittest.main()
