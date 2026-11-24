#!/usr/bin/env python3
"""Freerouting + visual AI: route -> inspect actual KiCad images -> revise -> reroute.

Candidate-only experimental controller. Does NOT touch the original PCB,
merge Git, or claim that electrical behavior/EMC is validated.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from candidate_evaluator import compare
from freerouting_prepare import validate_actions
from freerouting_visual_decider import ask as vision_ask
from layout_observer import observe
from review_feedback import load as read_feedback
from session_gate import preflight
from visual_stage_report import StageReport, validate_capture, validate_findings, roi_svg

ROOT=Path(__file__).resolve().parents[1]


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_command(cmd, *, timeout=240):
    p=subprocess.run([str(x) for x in cmd],capture_output=True,text=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(map(str,cmd[:4]))}: "+
                           (p.stderr+p.stdout)[-1300:])
    return p


def copy_project(source, target):
    for ext in (".kicad_pro",".kicad_dru"):
        src=Path(source).with_suffix(ext)
        if src.is_file():
            shutil.copy2(src,Path(target).with_suffix(ext))


def route_once(source, directory, *, kicad_python, freerouting_jar,
               java_bin="java", passes=8, cmd=run_command):
    """Isolated KiCad DSN -> pinned Freerouting JAR -> SES -> KiCad PCB."""
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=True)
    stage=directory/"pre_route.kicad_pcb"
    if Path(source).resolve()!=stage.resolve():
        shutil.copy2(source,stage)
    copy_project(source,stage)
    dsn=directory/"candidate.dsn"
    ses=directory/"candidate.ses"
    routed=directory/"candidate_routed.kicad_pcb"
    copy_project(stage,routed)
    if not Path(freerouting_jar).is_file():
        raise FileNotFoundError(f"Freerouting JAR missing: {freerouting_jar}")
    cmd([kicad_python,ROOT/"tools"/"export_dsn.py",stage,dsn],timeout=180)
    if not dsn.is_file():
        raise RuntimeError("KiCad did not write Specctra DSN")
    cmd([java_bin,"-jar",freerouting_jar,"-de",dsn,"-do",ses,"-mp",passes],timeout=900)
    if not ses.is_file():
        raise RuntimeError("Freerouting did not write SES")
    cmd([kicad_python,ROOT/"tools"/"import_ses.py",stage,ses,routed],timeout=180)
    if not routed.is_file():
        raise RuntimeError("KiCad SES import produced no PCB")
    return routed


def prepare_once(src,dst,plan,*,mechanical,protected,kicad_python,cmd=run_command):
    dst=Path(dst)
    dst.parent.mkdir(parents=True,exist_ok=True)
    plan_path=dst.parent/"agent_actions.json"
    mech_path=dst.parent/"mechanical.json"
    protected_path=dst.parent/"protected.json"
    plan_path.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding="utf-8")
    mech_path.write_text(json.dumps(mechanical,ensure_ascii=False),encoding="utf-8")
    protected_path.write_text(json.dumps(protected,ensure_ascii=False),encoding="utf-8")
    copy_project(src,dst)
    cmd([kicad_python,ROOT/"tools"/"freerouting_prepare.py",
         "--board",src,"--output",dst,"--plan",plan_path,
         "--mechanical",mech_path,"--protected",protected_path],timeout=180)
    if not dst.is_file():
        raise RuntimeError("KiCad placement preparation returned no PCB")
    return dst


def metrics(obs):
    keys=("board_sha256","drc_errors","unconnected","audit_fail",
          "keepout_fail","via_count","trace_mm","images")
    return {k:obs.get(k) for k in keys}


def visual_loop(board,manifest,intent,output,*,provider="codex",iterations=8,
                kicad_python=sys.executable,kicad_cli="kicad-cli",
                jar=None,java_bin="java",passes=8,
                router=None,observer=None,decider=None,preparer=None,preflight_fn=preflight):
    board,manifest,intent,output=map(lambda v:Path(v).resolve(),
                                      (board,manifest,intent,output))
    if board.suffix!=".kicad_pcb" or not board.is_file():
        raise ValueError("a real .kicad_pcb source is required")
    if not 1<=iterations<=60 or not 1<=passes<=200:
        raise ValueError("iteration/pass budget out of range")
    if output==board.parent or output in board.parents:
        raise ValueError("output directory must be distinct from board source")
    output.mkdir(parents=True,exist_ok=True)
    trail=StageReport(output)
    trail.add("INPUT", "PASS", inputs={"source_board":str(board), "source_sha256":file_hash(board),
                                     "manifest":str(manifest), "intent":str(intent)})
    manifest_data=json.loads(manifest.read_text(encoding="utf-8"))
    if (manifest.parent/manifest_data.get("board","")).resolve()!=board:
        raise ValueError("manifest board does not match source")
    if manifest_data.get("submission_stage")=="FINAL":
        raise ValueError("run as internal stage; FINAL is reserved for owner review")
    reference=preflight_fn(manifest_data,manifest.parent)
    trail.add("REFERENCE_PREFLIGHT", reference["status"],
              reason="; ".join(reference.get("issues",[])),
              outputs={"source_sha256":reference.get("board_sha256"),
                       "region_count":len(reference.get("regions",[]))})
    if reference["status"]!="READY":
        result={"status":"BLOCKED","reasons":reference["issues"],"iterations":[]}
        (output/"blocked.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        return result
    intent_data=json.loads(intent.read_text(encoding="utf-8"))
    anchors=intent_data.get("mechanical_anchor_refs")
    protected=intent_data.get("protected_net_names",[])
    if not isinstance(anchors,list) or not all(isinstance(x,str) and x for x in anchors):
        raise ValueError("intent must declare mechanical_anchor_refs as a JSON list")
    if not isinstance(protected,list) or not all(isinstance(x,str) for x in protected):
        raise ValueError("protected_net_names must be JSON list")
    original_hash=file_hash(board)
    trail.add("MECHANICAL_AND_NET_CONSTRAINTS", "PASS",
              outputs={"mechanical_anchors":anchors,"protected_nets":protected})
    layout=output/"best_pre_route.kicad_pcb"
    routed=output/"best_routed.kicad_pcb"
    shutil.copy2(board,layout)
    copy_project(board,layout)
    jar=Path(jar).resolve() if jar else ROOT/"setup"/"freerouting"/"freerouting-2.5.0.jar"
    runroute=router or (lambda src,out:route_once(src,out,kicad_python=kicad_python,
                                                  freerouting_jar=jar,java_bin=java_bin,passes=passes))
    look=observer or (lambda src,out:observe(src,out,kicad_cli=kicad_cli,intent=intent))
    decide=decider or (lambda ctx:vision_ask(ctx,provider=provider))
    prep=preparer or (lambda src,dst,plan:prepare_once(src,dst,plan,mechanical=anchors,
                                                        protected=protected,kicad_python=kicad_python))
    baseline=runroute(layout,output/"baseline_route")
    if not Path(baseline).is_file():
        raise RuntimeError("Freerouting baseline returned nonexistent PCB")
    trail.add("BASELINE_FREEROUTING", "PASS",
              inputs={"pre_route_sha256":file_hash(layout)},
              outputs={"routed_board":str(baseline),"routed_sha256":file_hash(baseline)})
    initial=look(baseline,output/"baseline_observation")
    initial_proof=validate_capture(baseline,initial)
    trail.add("BASELINE_IMAGE_AND_DRC", "PROVENANCE_PASS",
              outputs={"image_evidence":initial.get("image_evidence",{})},
              metrics=metrics(initial),screenshots=initial_proof,
              reason="Layer/export/board SHA checked; this does not prove visual diagnosis")
    shutil.copy2(baseline,routed)
    copy_project(baseline,routed)
    best=initial
    history=[]
    misses=0
    feedback_path=board.parent/"reviews"/"owner_feedback.jsonl"
    feedback=read_feedback(feedback_path)
    for iteration in range(1,iterations+1):
        folder=output/f"iteration_{iteration:02d}"
        folder.mkdir(parents=True,exist_ok=True)
        context={"iteration":iteration,"source_board":str(board),"observation":best,
                 "mechanical_anchors":anchors,"protected_nets":protected,
                 "previous_attempts":history[-4:],"owner_feedback":feedback,
                 "rulebook_path":str(ROOT/"LAYOUT_RULES.md"),"intent_path":str(intent)}
        entry={"iteration":iteration,"state":"STARTED"}
        before_pre_hash=file_hash(layout)
        before_routed_hash=file_hash(routed)
        trail.add("ITERATION_START","PASS",iteration=iteration,
                  inputs={"best_pre_route_sha256":before_pre_hash,
                          "best_routed_sha256":before_routed_hash},
                  metrics=metrics(best),screenshots=initial_proof)
        try:
            plan=decide(context)
            validate_actions(plan)
            findings=validate_findings(plan,best)
            (folder/"decision.json").write_text(json.dumps(plan,ensure_ascii=False,indent=2),
                                                 encoding="utf-8")
            marked=[]
            crop_artifacts={}
            for index,finding in enumerate(findings,1):
                crop=roi_svg(best["images"][finding["layer"]],finding["roi"],
                             folder/f"finding_{index}_{finding['layer'][0]}.svg")
                marked.append({**finding,"crop":crop,
                               "verification":"AGENT_VISUAL_HYPOTHESIS_NOT_INDEPENDENTLY_PROVEN"})
                crop_artifacts[f"Finding {index} — {finding['layer']}"]=crop["path"]
            trail.add("AGENT_VISUAL_DIAGNOSIS",
                      "HYPOTHESIS" if plan["actions"] else "NO_ACTION",iteration=iteration,
                      reason=plan["rationale"],
                      inputs={"board_sha256":best["board_sha256"]},
                      outputs={"decision_file":str(folder/"decision.json"),
                               "image_verification":"PROVENANCE_PASS_NOT_DIAGNOSIS_PROOF"},
                      findings=marked,screenshots=crop_artifacts)
            if not plan["actions"]:
                entry.update(state="STOP_NO_SAFE_ACTION",rationale=plan["rationale"])
                history.append(entry)
                break
            prepared=prep(layout,folder/"proposed_layout.kicad_pcb",plan)
            trail.add("PLACEMENT_AND_NET_RIPUP","PASS",iteration=iteration,
                      inputs={"best_pre_route_sha256":before_pre_hash,
                              "actions":plan["actions"]},
                      outputs={"proposed_board":str(prepared),
                               "proposed_sha256":file_hash(prepared)})
            route=runroute(prepared,folder/"freerouting")
            trail.add("FREEROUTING_REROUTE","PASS",iteration=iteration,
                      inputs={"prepared_sha256":file_hash(prepared)},
                      outputs={"routed_board":str(route),"routed_sha256":file_hash(route)})
            after=look(route,folder/"observation")
            after_proof=validate_capture(route,after)
            trail.add("IMAGE_CAPTURE_AND_DRC","PROVENANCE_PASS",iteration=iteration,
                      reason="KiCad PNG and board SHA verified; defect diagnosis remains a hypothesis",
                      outputs={"image_evidence":after.get("image_evidence",{})},
                      metrics=metrics(after),screenshots=after_proof)
            accept,reason=compare(best,after)
            trail.add("BEFORE_AFTER_EVALUATION","KEEP" if accept else "ROLLBACK",
                      iteration=iteration,reason=reason,
                      inputs={"before":metrics(best)},outputs={"after":metrics(after)},
                      screenshots={**{f"Before {k}":v for k,v in initial_proof.items()},
                                   **{f"After {k}":v for k,v in after_proof.items()}})
            entry.update(state="KEEP" if accept else "ROLLBACK",reason=reason,
                         rationale=plan["rationale"],actions=plan["actions"],
                         before=metrics(best),after=metrics(after))
            if accept:
                # Retain exact previous best as an immutable, reviewable snapshot.
                shutil.copy2(layout,folder/"before_best_pre_route.kicad_pcb")
                shutil.copy2(routed,folder/"before_best_routed.kicad_pcb")
                shutil.copy2(prepared,layout)
                copy_project(prepared,layout)
                shutil.copy2(route,routed)
                copy_project(route,routed)
                if file_hash(layout)!=file_hash(prepared) or file_hash(routed)!=file_hash(route):
                    raise RuntimeError("KEEP copy hash mismatch; prior best saved in iteration folder")
                best=after
                initial_proof=after_proof
                misses=0
                trail.add("BEST_CANDIDATE_UPDATE","KEEP",iteration=iteration,
                          outputs={"best_pre_route_sha256":file_hash(layout),
                                   "best_routed_sha256":file_hash(routed),
                                   "previous_best_snapshot":str(folder/"before_best_routed.kicad_pcb")})
            else:
                if file_hash(layout)!=before_pre_hash or file_hash(routed)!=before_routed_hash:
                    raise RuntimeError("ROLLBACK integrity failed: best candidate was overwritten")
                misses+=1
                trail.add("ROLLBACK","RESTORED_BY_NO_COMMIT",iteration=iteration,
                          reason=reason,
                          outputs={"best_pre_route_sha256":file_hash(layout),
                                   "best_routed_sha256":file_hash(routed),
                                   "rejected_candidate":str(route)})
        except (RuntimeError,ValueError,OSError,subprocess.TimeoutExpired) as exc:
            entry.update(state="ERROR_ROLLBACK",reason=str(exc)[-1600:])
            trail.add("ITERATION_FAILURE","ERROR_ROLLBACK",iteration=iteration,
                      reason=str(exc)[-1600:],
                      inputs={"previous_best_pre_sha256":before_pre_hash,
                              "previous_best_routed_sha256":before_routed_hash},
                      outputs={"current_best_pre_sha256":file_hash(layout),
                               "current_best_routed_sha256":file_hash(routed)})
            misses+=1
        history.append(entry)
        (output/"iterations.json").write_text(json.dumps(history,ensure_ascii=False,indent=2,default=str),
                                               encoding="utf-8")
        if file_hash(board)!=original_hash:
            raise RuntimeError("FATAL: source PCB changed")
        if misses>=2:
            break
    if file_hash(board)!=original_hash:
        raise RuntimeError("source board modified")
    trail.add("FINAL_INTERNAL_RESULT","NOT_OWNER_APPROVED",
              reason="Only a final owner review can accept layout; full electrical quality is not proven",
              outputs={"best_pre_route":str(layout),"best_routed":str(routed),
                       "best_pre_route_sha256":file_hash(layout),
                       "best_routed_sha256":file_hash(routed)},
              metrics=metrics(best),screenshots=initial_proof)
    result={"status":"INTERNAL_CANDIDATE_ONLY","owner_approved":False,
            "source_sha256":original_hash,"best_routed":str(routed),
            "best_pre_route":str(layout),"best_metrics":metrics(best),
            "iterations":history,"note":"KiCad native DRC/image metrics not proof of SI/EMC or owner acceptance"}
    (output/"session_progress.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    (output/"FINAL_CANDIDATE_SUMMARY.md").write_text(
        "# Internal candidate — not owner approved\n\n"
        +f"- Freerouting + real KiCad 2D-image iterations: {len(history)}\n"
        +f"- Accepted changes: {sum(x['state']=='KEEP' for x in history)}\n"
        +f"- DRC violations: {best['drc_errors']}; unconnected: {best['unconnected']}\n"
        +f"- Routed candidate: \`{routed}\`\n"
        +"- Only submit for owner review after independent layout/electrical checks\n",
        encoding="utf-8")
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("board","manifest","intent","output"):
        p.add_argument("--"+name,required=True,type=Path)
    p.add_argument("--provider",choices=("codex","claude"),default="codex")
    p.add_argument("--iterations",type=int,default=8)
    p.add_argument("--passes",type=int,default=8)
    p.add_argument("--kicad-python",default=sys.executable)
    p.add_argument("--kicad-cli",default="kicad-cli")
    p.add_argument("--jar",type=Path)
    p.add_argument("--java-bin",default="java")
    a=p.parse_args()
    result=visual_loop(a.board,a.manifest,a.intent,a.output,
                       provider=a.provider,iterations=a.iterations,
                       kicad_python=a.kicad_python,kicad_cli=a.kicad_cli,
                       jar=a.jar,java_bin=a.java_bin,passes=a.passes)
    print(json.dumps({k:v for k,v in result.items() if k!="iterations"},
                     ensure_ascii=False,indent=2,default=str))
    return 3 if result["status"]=="BLOCKED" else 0


if __name__=="__main__":
    raise SystemExit(main())
