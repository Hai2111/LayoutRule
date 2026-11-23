#!/usr/bin/env python3
"""Closed-loop KiCad: observe -> local AI decides -> edit -> DRC -> keep/rollback.

Source PCB remains unchanged. Never merge a branch or claim owner approval.
The loop is internal; only a final session report may reach the owner.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from candidate_evaluator import compare
from kicad_executor import validate_plan
from layout_decider import ask
from layout_observer import observe
from review_feedback import load as read_feedback
from session_gate import preflight

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def anchors_from_intent(intent):
    """Require explicit mechanical-fit anchors, including [] if none."""
    data = json.loads(Path(intent).read_text(encoding="utf-8"))
    if "mechanical_anchor_refs" not in data or not isinstance(data["mechanical_anchor_refs"], list):
        raise ValueError("intent must declare mechanical_anchor_refs, even [] if none")
    refs = data["mechanical_anchor_refs"]
    if any(not isinstance(r,str) or not r for r in refs) or len(set(refs)) != len(refs):
        raise ValueError("invalid mechanical_anchor_refs")
    return refs


def brief(obs):
    return {k:v for k,v in obs.items()
            if k not in ("tracks","track_items","footprints","vias","issues",
                         "audit_findings","keepout_log")}


def loop(board, manifest, intent, work_dir, *, provider="codex", iterations=8,
         kicad_python=sys.executable, kicad_cli="kicad-cli", timeout=240,
         decision_fn=None, execution_fn=None, observation_fn=None):
    board = Path(board).resolve()
    manifest = Path(manifest).resolve()
    intent = Path(intent).resolve()
    work_dir = Path(work_dir).resolve()
    if not board.is_file() or board.suffix != ".kicad_pcb":
        raise ValueError("existing source .kicad_pcb required")
    if board == work_dir or work_dir in board.parents:
        raise ValueError("work dir cannot be parent of source board")
    work_dir.mkdir(parents=True, exist_ok=True)
    if not 1 <= iterations <= 100:
        raise ValueError("iterations must be 1..100")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if (manifest.parent / data.get("board","")).resolve() != board:
        raise ValueError("manifest board must match source board")
    if data.get("submission_stage") == "FINAL":
        raise ValueError("loop must run as internal stage; FINAL only after work finished")
    pf = preflight(data, manifest.parent)
    if pf["status"] != "READY":
        (work_dir / "blocked.json").write_text(json.dumps(pf, indent=2), encoding="utf-8")
        return {"status":"BLOCKED","issues":pf["issues"],"history":[]}
    fixed = anchors_from_intent(intent)
    fixed_path = work_dir / "mechanical_anchors.json"
    fixed_path.write_text(json.dumps(fixed), encoding="utf-8")
    baseline_sha = sha(board)
    best = work_dir / "best_candidate.kicad_pcb"
    if best.resolve() == board:
        raise ValueError("source cannot be best candidate")
    shutil.copy2(board, best)
    project = board.with_suffix(".kicad_pro")
    if project.is_file():
        shutil.copy2(project, best.with_suffix(".kicad_pro"))

    obser = observation_fn or (lambda src,out: observe(src,out,kicad_cli=kicad_cli,intent=intent))
    decide = decision_fn or (lambda ctx: ask(ctx,provider,timeout=timeout,work_dir=work_dir))

    def execute(src,target,plan,path):
        if execution_fn:
            return execution_fn(src,target,plan,path)
        proc = subprocess.run([str(kicad_python),str(ROOT/"tools"/"kicad_executor.py"),
             "--source",str(src),"--output",str(target),"--actions",str(path),
             "--mechanical",str(fixed_path)],text=True,capture_output=True,timeout=180)
        if proc.returncode != 0 or not target.is_file():
            raise RuntimeError("KiCad executor failed: " + (proc.stderr+proc.stdout)[-3000:])
        return json.loads(proc.stdout)

    obs = obser(best,work_dir/"baseline")
    history = []
    fails = 0
    feedback_path = board.parent/"reviews"/"owner_feedback.jsonl"
    if not feedback_path.is_file():
        feedback_path = work_dir/"reviews"/"owner_feedback.jsonl"
    previous_feedback = read_feedback(feedback_path)
    for i in range(1,iterations+1):
        dest = work_dir/f"iteration_{i:02d}"
        dest.mkdir(parents=True,exist_ok=True)
        ctx = {"iteration":i,"current_board":str(best),"observation":obs,
               "previous_feedback":previous_feedback,"mechanical_anchors":fixed,
               "previous_attempts":history[-3:],
               "owner_decisions_file":str(ROOT/"rules"/"owner_decisions.json"),
               "layout_rules_file":str(ROOT/"LAYOUT_RULES.md"),
               "intent_file":str(intent),"reference_preflight":pf,
               "review_png":list(obs.get("images",{}).values())}
        (dest/"decision_context.json").write_text(
            json.dumps(ctx,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
        row = {"iteration":i,"status":"PENDING"}
        try:
            plan = decide(ctx)
            if not isinstance(plan,dict) or not isinstance(plan.get("rationale"),str):
                raise ValueError("agent decision missing rationale")
            if plan.get("actions") == []:
                row.update(status="STOP_BY_AGENT",reason=plan["rationale"])
                history.append(row)
                break
            validate_plan(plan)
            plan_path = dest/"actions.json"
            plan_path.write_text(json.dumps(plan,indent=2,ensure_ascii=False),encoding="utf-8")
            proposal = dest/"candidate.kicad_pcb"
            if best.with_suffix(".kicad_pro").is_file():
                shutil.copy2(best.with_suffix(".kicad_pro"),proposal.with_suffix(".kicad_pro"))
            execute(best,proposal,plan,plan_path)
            candidate_obs = obser(proposal,dest/"inspection")
            accepted,reason = compare(obs,candidate_obs)
            row.update(status="KEEP" if accepted else "ROLLBACK",reason=reason,
                       candidate_sha256=candidate_obs.get("board_sha256"),
                       before=brief(obs),after=brief(candidate_obs),
                       actions=len(plan["actions"]),agent_rationale=plan["rationale"])
            if accepted:
                shutil.copy2(proposal,best)
                obs = candidate_obs
                fails = 0
            else:
                fails += 1
        except (ValueError,RuntimeError,subprocess.TimeoutExpired,OSError) as exc:
            row.update(status="ERROR_ROLLBACK",reason=str(exc)[:1500])
            fails += 1
        history.append(row)
        (work_dir/"iterations.json").write_text(
            json.dumps(history,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
        if fails >= 2:
            break
    if sha(board) != baseline_sha:
        raise RuntimeError("FATAL: source PCB modified")
    status = ("CANDIDATE_READY_FOR_INTERNAL_REVIEW"
              if any(x["status"]=="KEEP" for x in history)
              else "NO_MEASURED_IMPROVEMENT")
    result = {"status":status,"owner_approved":False,"best_candidate":str(best),
              "best_sha256":sha(best),"input_sha256":baseline_sha,
              "iterations":len(history),
              "accepted_iterations":sum(x["status"]=="KEEP" for x in history),
              "metrics":brief(obs),"history":history,
              "note":"No production claim: needs KiCad validation and owner final-only review."}
    (work_dir/"session_progress.json").write_text(
        json.dumps(result,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("board","manifest","intent","work-dir"):
        p.add_argument("--"+arg,required=True,type=Path)
    p.add_argument("--provider",choices=("codex","claude"),default="codex")
    p.add_argument("--iterations",type=int,default=8)
    p.add_argument("--kicad-python",default=sys.executable)
    p.add_argument("--kicad-cli",default="kicad-cli")
    args = p.parse_args()
    result = loop(args.board,args.manifest,args.intent,args.work_dir,
                  provider=args.provider,iterations=args.iterations,
                  kicad_python=args.kicad_python,kicad_cli=args.kicad_cli)
    print(json.dumps({k:v for k,v in result.items() if k!="history"},
                     ensure_ascii=False,indent=2))
    return 3 if result["status"]=="BLOCKED" else 0


if __name__=="__main__":
    raise SystemExit(main())
