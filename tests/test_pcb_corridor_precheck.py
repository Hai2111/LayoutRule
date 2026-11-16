import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
from pcb_corridor_precheck import precheck


def board_at(reset_y):
    return f'''(kicad_pcb (version 20260206)
      (footprint "IC" (layer "F.Cu") (at 10 15 180)
        (property "Reference" "U2") (property "Value" "CH340C")
        (pad "2" smd rect (at -2.475 -3.175) (size 1.95 0.6) (net "/UART_RX")))
      (footprint "IC" (layer "F.Cu") (at 21 18)
        (property "Reference" "U1") (property "Value" "STM8")
        (pad "3" smd rect (at -2.8625 -1.625) (size 1.475 0.4) (net "/UART_RX")))
      (footprint "R" (layer "F.Cu") (at 15.5 {reset_y})
        (property "Reference" "R3") (property "Value" "10k")
        (pad "1" smd rect (at -0.825 0) (size 0.8 0.95) (net "/+5V"))
        (pad "2" smd rect (at 0.825 0) (size 0.8 0.95) (net "/NRST")))
    )'''


class CorridorTests(unittest.TestCase):
    def test_reset_between_uart_blocked(self):
        d = precheck(board_at(17), 'U2','2','U1','3', 0.2, 0.15)
        self.assertEqual(d['status'], 'POTENTIAL_CONGESTION')
        self.assertAlmostEqual(d['direct_pad_center_distance_mm'], 5.9417)
        self.assertEqual([(i['ref'],i['pad']) for i in d['intersected_unrelated_pad_envelopes']],
                         [('R3','1'),('R3','2')])

    def test_move_reset_clears_direct_line_hypothesis(self):
        d = precheck(board_at(12), 'U2','2','U1','3', 0.2, 0.15)
        self.assertEqual(d['status'], 'NO_PAD_ENVELOPE_HIT')
        self.assertFalse(d['intersected_unrelated_pad_envelopes'])

    def test_reject_negative_constraints(self):
        with self.assertRaises(ValueError):
            precheck(board_at(17), 'U2','2','U1','3', 0.2, -0.1)


if __name__ == '__main__':
    unittest.main()
