import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parent.parent / 'tools' / 'pcb_ref_extract.py'
spec = importlib.util.spec_from_file_location('pcb_ref_extract', MODULE_PATH)
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)


class ExtractorTests(unittest.TestCase):
    def check_board(self, src, names, refs=()):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'board.kicad_pcb'
            path.write_text(src, encoding='utf-8')
            return extractor.report(str(path), refs, names)

    def test_kicad10_named_nets(self):
        src = '''(kicad_pcb (version 20260206)
            (footprint "R" (at 15.5 17)
              (property "Reference" "R3") (property "Value" "10k")
              (pad "1" smd rect (at 0 0) (size 0.8 0.95) (net "/NRST")))
            (segment (start 0 0) (end 3 4) (width 0.2) (layer "F.Cu") (net "/NRST"))
            (via (at 3 4) (size 0.6) (drill 0.3) (net "/NRST"))
            (zone (net "/GND") (layer "B.Cu"))
        )'''
        d = self.check_board(src, ['/NRST'], ['R3'])
        self.assertEqual((d['footprints'], d['track_segments'], d['via_count'], d['zone_objects']), (1, 1, 1, 1))
        self.assertEqual(d['selected_footprints']['R3']['pads'][0]['net'], '/NRST')
        self.assertEqual(d['net_statistics']['/NRST']['total_copper_segment_length_mm'], 5.0)

    def test_kicad5_legacy_numeric_nets(self):
        src = '''(kicad_pcb (version 20171130)
            (net 5 "BUCK_IN")
            (module "R" (layer F.Cu) (at 7 8 90)
              (fp_text reference R1 (at 0 0)) (fp_text value 10k (at 0 0))
              (pad 1 smd rect (at 0 0) (size 0.5 0.8) (net 5 "BUCK_IN")))
            (segment (start 0 0) (end 3 4) (width 0.25) (layer F.Cu) (net 5))
        )'''
        d = self.check_board(src, ['BUCK_IN'], ['R1'])
        self.assertEqual(d['net_statistics']['BUCK_IN']['segment_count'], 1)
        self.assertEqual(d['net_statistics']['BUCK_IN']['min_segment_width_mm'], 0.25)
        self.assertEqual(d['selected_footprints']['R1']['value'], '10k')

    def test_placement_only_not_routing_reference(self):
        src = '''(kicad_pcb (version 20241229)
           (footprint "U" (at 10 10) (property "Reference" "U1") (property "Value" "MCU"))
        )'''
        d = self.check_board(src, [])
        self.assertFalse(d['has_saved_tracks'])
        self.assertEqual(d['track_segments'], 0)
        self.assertEqual(d['footprints'], 1)

    def test_fail_closed_on_truncated_board(self):
        with self.assertRaises(ValueError):
            extractor.parse_board('(kicad_pcb (segment (start 1 2)')


if __name__ == '__main__':
    unittest.main()
