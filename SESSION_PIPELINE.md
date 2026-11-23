# Session-safe candidate pipeline (proposed; pending owner review)

**Hard contract:** ONE SESSION = ONE OWNER REVIEW OF THE FINAL CANDIDATE, AFTER REPORT. No region-level/G1/G3/G5 approval prompts and no layout locking beyond required mechanical anchors. The owner decides acceptance. See REVIEW_LEARNING_LOOP.md.
This implementation does not edit canonical rules or merge a branch.

## Work flow

1. Agent writes session.json before changing PCB, with references for every region
   and every required copper layer. Visual references are accepted (CAD not required).
   Each reference identifies its source URL, exact region, applicability, observed
   features, PNG screenshot and normalized ROI rectangle.
2. Run GLOBAL preflight. Missing source region, visible layer, ROI or screenshot
   means BLOCKED for the **entire PCB**. Agent may continue searching documentation
   without touching placement/routing. Report one batch at session end.
3. Generate Candidate REF and Candidate OPT on separate branches, preserving
   the main PCB until owner approval. Route decisions and net outcomes belong
   in a board-SHA-bound region ledger.
4. Run native KiCad DRC, geometry audit and supplemental body-keepout audit.
   A clean DRC does not prove correct return paths, topology or EMC.
5. G1/G3/G5 are **internal checkpoints only**. End after the full final candidate has been checked and the report is ready (or end with one BLOCKED report); review is one SVG image containing original
   reference / REF / OPT panels (one row per region) plus 5-line OWNER_REVIEW.md.
   Full details go to technical_evidence.json. Owner approval is ALWAYS pending.

## Required JSON schema (abbreviated)

~~~json
{
  "schema_version": 1,
  "session_id": "example-r1",
  "board": "board.kicad_pcb",
  "regions": [{
    "id": "R1-buck",
    "required_layers": ["F.Cu", "B.Cu"],
    "review_layer": "F.Cu",
    "reference": {
      "id": "RD01",
      "source_url": "https://vendor.example/reference",
      "source_region": "input capacitor/controller/inductor area",
      "applicability": "same topology, comparable pinout and stackup",
      "observed_features": ["VIN bypass loop", "SW path"],
      "evidence": {
        "F.Cu": {"path": "images/source-f.png", "roi": [0.1, 0.1, 0.9, 0.9]},
        "B.Cu": {"path": "images/source-b.png", "roi": [0.1, 0.1, 0.9, 0.9]}
      }
    },
    "candidates": {
      "ref": {
        "branch": "candidate/ref", "board": "ref/board.kicad_pcb",
        "images": {
          "F.Cu": {"path": "images/ref-f.png", "roi": [0.1, 0.1, 0.9, 0.9]},
          "B.Cu": {"path": "images/ref-b.png", "roi": [0.1, 0.1, 0.9, 0.9]}
        },
        "drc": "ref/drc.json", "audit": "ref/audit.json",
        "routing_ledger": "ref/region_ledger.json"
      },
      "opt": {
        "branch": "candidate/opt", "board": "opt/board.kicad_pcb",
        "images": {
          "F.Cu": {"path": "images/opt-f.png", "roi": [0.1, 0.1, 0.9, 0.9]},
          "B.Cu": {"path": "images/opt-b.png", "roi": [0.1, 0.1, 0.9, 0.9]}
        },
        "drc": "opt/drc.json", "audit": "opt/audit.json",
        "routing_ledger": "opt/region_ledger.json"
      }
    }
  }]
}
~~~

The paths and vendor URL above are **placeholders** and MUST be replaced with
real PCB and actual KiCad/datasheet screenshot evidence before routing.
Each image is a PNG, each ROI is normalized [left,top,right,bottom].
Same-layer comparison is enforced; source truth and identical visual scale
still need independent human/agent verification.

## Commands

~~~powershell
# Global reference preflight (3 means BLOCKED; no board modifications)
python tools\session_gate.py preflight project\session.json --output-dir project\session_review

# Agent creates a routed PCB independently; validate in an isolated candidate
powershell -NoProfile -ExecutionPolicy Bypass -File tools\route_pipeline.ps1 -Board project\board.kicad_pcb -SessionManifest project\session.json -CandidateBoard work\agent_candidate.kicad_pcb -IntentPath project\layout_intent.json

# When both candidates are ready: one composite image and owner report
python tools\session_gate.py review project\session.json --output-dir project\session_review

# Regression tests (stdlib-only)
python -m unittest discover -s tests -p "test_session_gate.py"
~~~

Session gate preflight exit: 0 READY, 3 BLOCKED.
Session gate review exit: 0 READY_FOR_OWNER (not approved), 3 BLOCKED,
4 NEEDS_REVIEW (DRC/audit/ledger/image problems or not marked FINAL). No automatic merge.

**Known limitations:** The Freerouting mode must be explicitly requested with
-FreeroutingProposal and is only an experimental whole-board proposal, not
agent-guided placement/routing (INV-3). The wrapper does not implement KiCad
push-and-shove geometry or generate real copper screenshots itself. The RA01
DSN-export issue and existing fixture DRC findings also remain unresolved.
This pipeline must not be described as a complete autonomous router.

## Sau khi owner xem bản cuối

Owner chỉ nhận báo cáo **sau** khi agent đã kiểm tra candidate cuối. Owner có thể trả lời ACCEPT/REVISE/REJECT/DEFER bằng ngôn ngữ tự nhiên; agent lưu **nguyên văn** nhận xét cùng ảnh/vùng, board SHA, giả thuyết nguyên nhân, cách thử sửa và kiểm chứng ở phiên sau. Không bắt owner chấm điểm từng net. Không khóa placement/copper/vùng khi owner ACCEPT hoặc khi qua checkpoint nội bộ; vẫn giữ bản đã review để đối chiếu/rollback. Một câu ACCEPT cho layout **không** tự cấp phép đổi rule chung. Xem [REVIEW_LEARNING_LOOP.md](REVIEW_LEARNING_LOOP.md).

**Project scope:** chưa có benchmark board do owner chỉ định; demo USB-C trong chat chỉ là bài thử, không đưa vào LayoutRule. Thiếu nhà sản xuất/stackup cụ thể: dùng giả định có nguồn và ghi trong intent; chỉ báo NEEDS_REVIEW nếu thực sự ảnh hưởng kiểm chứng.
