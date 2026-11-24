#!/usr/bin/env python3
"""Tests for provenance, ROI claims and stage-by-stage human-readable evidence."""
import hashlib
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from visual_stage_report import (StageReport, png_metadata, validate_capture,
                                  validate_findings, roi_svg)


def png():
    def chunk(tag, data):
        return (struct.pack(">I", len(data))+tag+data+
                struct.pack(">I", zlib.crc32(tag+data) & 0xffffffff))
    raw=b"\x00\x10\x20\x30"
    return (b"\x89PNG\r\n\x1a\n"+
            chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,2,0,0,0))+
            chunk(b"IDAT",zlib.compress(raw))+
            chunk(b"IEND",b""))


class EvidenceContract(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.board=self.root/"board.kicad_pcb"
        self.board.write_text("(kicad_pcb (version 20241229))")
        self.sha=hashlib.sha256(self.board.read_bytes()).hexdigest()
        self.obs={"board_sha256":self.sha,"images":{},"image_evidence":{},
                  "footprints":{"R1":{"x":3,"y":4,"pads":[]}},"tracks":[]}
        for layer in ("F.Cu","B.Cu"):
            file=self.root/(layer+".png")
            file.write_bytes(png())
            self.obs["images"][layer]=str(file)
            self.obs["image_evidence"][layer]={
                "layer":layer,"board_sha256":self.sha,
                "png_sha256":hashlib.sha256(file.read_bytes()).hexdigest(),
                "export_exit_code":0,
                "export_command":["kicad-cli","pcb","export","png","--layers",layer]}
        self.plan={"actions":[{"op":"move","ref":"R1","x_mm":1,"y_mm":2}],
                   "rationale":"R1 blocks escape",
                   "findings":[{"layer":"F.Cu","roi":[0.1,0.1,0.9,0.9],
                                 "ref":"R1","problem":"escape detour",
                                 "reason":"near R1", "expected_change":"reduce via count"}]}

    def test_provenance_pass_and_is_exact_board_layer(self):
        result=validate_capture(self.board,self.obs)
        self.assertEqual(result["F.Cu"]["board_sha256"],self.sha)
        self.assertEqual(result["B.Cu"]["width"],1)
        self.assertEqual(result["F.Cu"]["provenance_status"],"CHECKED")

    def test_corrupt_png_does_not_pass(self):
        file=Path(self.obs["images"]["F.Cu"])
        file.write_bytes(file.read_bytes()[:-4])
        with self.assertRaises(ValueError):
            validate_capture(self.board,self.obs)

    def test_wrong_layer_or_board_provenance_does_not_pass(self):
        self.obs["image_evidence"]["B.Cu"]["layer"]="F.Cu"
        with self.assertRaisesRegex(ValueError,"provenance"):
            validate_capture(self.board,self.obs)
        self.obs["image_evidence"]["B.Cu"]["layer"]="B.Cu"
        self.board.write_text("another version")
        with self.assertRaisesRegex(ValueError,"PCB SHA"):
            validate_capture(self.board,self.obs)

    def test_valid_and_incorrect_findings(self):
        self.assertEqual(len(validate_findings(self.plan,self.obs)),1)
        self.plan["findings"][0]["ref"]="UNLISTED"
        with self.assertRaisesRegex(ValueError,"unknown footprint"):
            validate_findings(self.plan,self.obs)
        self.plan["findings"][0]["ref"]="R1"
        self.plan["findings"][0]["roi"]=[0.3,0.2,0.1,0.4]
        with self.assertRaisesRegex(ValueError,"ROI"):
            validate_findings(self.plan,self.obs)

    def test_real_pixel_roi_and_html_stage_outputs(self):
        crop=roi_svg(self.obs["images"]["F.Cu"],[0,0,1,1],self.root/"finding.svg")
        self.assertTrue(Path(crop["path"]).is_file())
        self.assertIn("data:image/png;base64,",Path(crop["path"]).read_text())
        report=StageReport(self.root)
        report.add("BASELINE_IMAGE_AND_DRC","PROVENANCE_PASS",
                   inputs={"board_sha256":self.sha},
                   screenshots=validate_capture(self.board,self.obs))
        report.add("AGENT_VISUAL_DIAGNOSIS","HYPOTHESIS",
                   iteration=1,findings=self.plan["findings"],
                   screenshots={"Crop":crop["path"]})
        report.add("ROLLBACK","RESTORED_BY_NO_COMMIT",iteration=1,
                   reason="unconnected grew",outputs={"best_sha":self.sha})
        self.assertEqual([x["stage"] for x in
                          json.loads((self.root/"stage_results.json").read_text())["events"]],
                         ["BASELINE_IMAGE_AND_DRC","AGENT_VISUAL_DIAGNOSIS","ROLLBACK"])
        page=(self.root/"STAGE_REPORT.html").read_text()
        self.assertIn("ROLLBACK",page)
        self.assertIn("HYPOTHESIS",page)
        self.assertIn('finding.svg',page)


if __name__ == "__main__":
    unittest.main()
