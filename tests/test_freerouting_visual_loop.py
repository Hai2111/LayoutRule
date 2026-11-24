#!/usr/bin/env python3
"""Freerouting/vision loop tests with injected fake router, images and DRC.

Tests the orchestrator only. A real KiCad10 + JAR smoke test remains required.
"""
import hashlib
import json
import shutil
import struct
import zlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from freerouting_prepare import validate_actions
from freerouting_visual_decider import select_context
from freerouting_visual_loop import visual_loop


def valid_png():
    def chunk(tag, blob):
        return (struct.pack(">I",len(blob))+tag+blob+
                struct.pack(">I",zlib.crc32(tag+blob) & 0xffffffff))
    raw=b"\x00"+b"\x70\x98\x20"
    return (b"\x89PNG\r\n\x1a\n"+
            chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,2,0,0,0))+
            chunk(b"IDAT",zlib.compress(raw))+
            chunk(b"IEND",b""))


def finding():
    return {"layer":"F.Cu","roi":[0.1,0.1,0.9,0.9],
            "ref":"R1","problem":"pad escape detour near R1",
            "reason":"confirmed ref exists; image diagnosis still hypothesis",
            "expected_change":"reduce unconnected / shorten route"}


class ValidatedActions(unittest.TestCase):
    def test_high_level_placement_and_net_ripup(self):
        self.assertEqual(len(validate_actions({
            "rationale":"U1 escape blocks R1",
            "actions":[{"op":"move","ref":"R1","x_mm":10.0,"y_mm":12.0},
                       {"op":"reroute_net","net":"USB_DP"}]})["actions"]),2)

    def test_reject_low_level_made_up_copper(self):
        with self.assertRaises(ValueError):
            validate_actions({"rationale":"try","actions":[
                {"op":"add_trace","points_mm":[[1,2],[3,4]]}]})

    def test_reject_large_batch(self):
        with self.assertRaises(ValueError):
            validate_actions({"rationale":"try","actions":[
                {"op":"reroute_net","net":f"N{i}"} for i in range(13)]})

    def test_vision_context_includes_geometry_and_short_history(self):
        result=select_context({"iteration":2,"source_board":"board.kicad_pcb",
                               "mechanical_anchors":["J1"],
                               "observation":{"drc_errors":1,"unconnected":0,
                                              "images":{"F.Cu":"f.png","B.Cu":"b.png"},
                                              "footprints":{"R1":{"x":4,"y":5}},
                                              "issues":[{"type":"short"}]},
                               "previous_attempts":[{"state":"ROLLBACK"}]})
        self.assertEqual(result["footprints"]["R1"]["x"],4)
        self.assertEqual(result["previous_attempts"][0]["state"],"ROLLBACK")


class FakeLocalKiCadLoop(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.board=self.root/"source.kicad_pcb"
        self.board.write_text("(kicad_pcb)\n",encoding="utf-8")
        self.start_hash=hashlib.sha256(self.board.read_bytes()).hexdigest()
        self.manifest=self.root/"session.json"
        self.manifest.write_text(json.dumps({
            "schema_version":1,"session_id":"trial","submission_stage":"G3",
            "board":"source.kicad_pcb"}),encoding="utf-8")
        self.intent=self.root/"intent.json"
        self.intent.write_text(json.dumps({"mechanical_anchor_refs":["J1"]}))
        self.work=self.root/"experiment"
        self.record=[]

    def router(self,source,output):
        self.record.append(("router",str(source)))
        output=Path(output)
        output.mkdir(parents=True,exist_ok=True)
        dest=output/"candidate_routed.kicad_pcb"
        shutil.copy2(source,dest)
        with dest.open("a") as f:
            f.write("\nROUTED")
        return dest

    def observe(self,board,out):
        self.record.append(("observer",str(board)))
        data=Path(board).read_text()
        out=Path(out)
        out.mkdir(parents=True,exist_ok=True)
        images={}
        for layer in ("F.Cu","B.Cu"):
            png=out/(layer.replace(".","_")+".png")
            png.write_bytes(valid_png())
            images[layer]=str(png)
        board_sha=hashlib.sha256(board.read_bytes()).hexdigest()
        proof={layer: {"layer":layer,"board_sha256":board_sha,
                       "png_sha256":hashlib.sha256(Path(images[layer]).read_bytes()).hexdigest(),
                       "export_command":["kicad-cli","pcb","export","png","--layers",layer],
                       "export_exit_code":0} for layer in ("F.Cu","B.Cu")}
        return {"board_sha256":board_sha,"image_evidence":proof,
                "drc_errors":int("BAD" in data),
                "unconnected":3 if "GOOD" in data else 4,
                "audit_fail":0,"keepout_fail":0,
                "via_count":2,"trace_mm":12,"footprints":{"R1":{"x":5,"y":6}},
                "track_items":[],"issues":[],"images":images}

    def preparer(self,source,dest,plan):
        self.record.append(("preparer",str(source),plan["rationale"]))
        shutil.copy2(source,dest)
        with dest.open("a") as f:
            f.write("\n"+plan["rationale"])
        return dest

    def exercise_loop(self,decider,iterations=5,preflight=None):
        return visual_loop(self.board,self.manifest,self.intent,self.work,
            iterations=iterations,router=self.router,observer=self.observe,
            preparer=self.preparer,decider=decider,
            preflight_fn=preflight or (lambda m,b:{"status":"READY","issues":[]}))

    def test_keeps_image_driven_improvement_and_rolls_back_drc_regression(self):
        plans=iter(("GOOD","BAD"))
        contexts=[]
        def decider(ctx):
            contexts.append(ctx)
            return {"rationale":next(plans),"findings":[finding()],"actions":[
                {"op":"move","ref":"R1","x_mm":6.0,"y_mm":7.0}]}
        result=self.exercise_loop(decider,iterations=2)
        self.assertEqual([r["state"] for r in result["iterations"]],["KEEP","ROLLBACK"])
        self.assertEqual(result["best_metrics"]["unconnected"],3)
        self.assertEqual(result["best_metrics"]["drc_errors"],0)
        self.assertEqual(len(contexts),2)
        self.assertTrue(Path(contexts[0]["observation"]["images"]["F.Cu"]).is_file())
        self.assertTrue(Path(contexts[0]["observation"]["images"]["B.Cu"]).is_file())
        self.assertIn("GOOD",(self.work/"best_pre_route.kicad_pcb").read_text())
        self.assertNotIn("BAD",(self.work/"best_pre_route.kicad_pcb").read_text())
        self.assertEqual(hashlib.sha256(self.board.read_bytes()).hexdigest(),self.start_hash)
        self.assertFalse(result["owner_approved"])
        self.assertTrue((self.work/"FINAL_CANDIDATE_SUMMARY.md").is_file())

    def test_one_no_action_finishes_without_premature_review(self):
        result=self.exercise_loop(lambda ctx:{"rationale":"already acceptable for internal tests",
                                    "actions":[]},iterations=10)
        self.assertEqual(len(result["iterations"]),1)
        self.assertEqual(result["iterations"][0]["state"],"STOP_NO_SAFE_ACTION")
        self.assertFalse((self.work/"OWNER_REVIEW.md").exists())

    def test_two_nonimproving_tries_end_session(self):
        def decider(ctx):
            return {"rationale":"UNCHANGED","findings":[finding()],"actions":[
                {"op":"rotate","ref":"R1","degrees":0}]}
        result=self.exercise_loop(decider,iterations=10)
        self.assertEqual(len(result["iterations"]),2)
        self.assertEqual([x["state"] for x in result["iterations"]],["ROLLBACK","ROLLBACK"])

    def test_reference_block_cannot_route_or_request_agent(self):
        def no_decider(ctx):
            self.fail("Agent must not run if reference is blocked")
        out=self.exercise_loop(no_decider,preflight=lambda m,b:{
            "status":"BLOCKED","issues":["B.Cu reference missing"]})
        self.assertEqual(out["status"],"BLOCKED")
        self.assertEqual(self.record,[])

    def test_reject_missing_mechanical_anchor_declaration(self):
        self.intent.write_text("{}")
        with self.assertRaisesRegex(ValueError,"mechanical_anchor_refs"):
            self.exercise_loop(lambda c:None)
        self.assertEqual(self.record,[])

    def test_fails_without_final_internal_stage(self):
        data=json.loads(self.manifest.read_text())
        data["submission_stage"]="FINAL"
        self.manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,"FINAL"):
            self.exercise_loop(lambda ctx:None)
        self.assertEqual(self.record,[])


if __name__=="__main__":
    unittest.main()
