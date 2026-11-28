"""learn.py - kho hoc cua quy trinh layout (khong tu nang bai hoc thanh rule da duyet: owner quyet).
  python learn.py seed                        nap bai hoc tu learn/seed_lessons.json -> learn/lessons.jsonl
  python learn.py feedback "<nguyen van>" --board X.kicad_pcb --cause "..." --rule "..."   ghi phan hoi owner moi (kem SHA)
  python learn.py edits OLD.kicad_pcb NEW.kicad_pcb     (KiCad python) tu chinh sua cua owner -> ung vien bai hoc
  python learn.py refs                        (KiCad python) trich mau bo tri tu ref -> learn/patterns.json
  python learn.py show                        tom tat bai hoc theo trang thai
Trang thai: CANDIDATE -> TRIED (da thu tren 1 board) -> IMPLEMENTED (co trong cong cu) -> CONFIRMED (owner xac nhan tren >=2 board).
"""
import hashlib, json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); L = os.path.join(HERE, "learn")
TOOLS = os.path.join(HERE, "tools"); sys.path.insert(0, TOOLS); from kenv import KP  # KiCad tim tu dong (tools/kenv.py)
REFROOT = os.environ.get("LAYOUTRULE_REF") or os.path.join(HERE, "..", "ref", "Kicad")   # ref board cua owner, khong nam trong repo

def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]

def load():
    p = os.path.join(L, "lessons.jsonl")
    return [json.loads(x) for x in open(p, encoding="utf-8")] if os.path.exists(p) else []

def save(ls):
    with open(os.path.join(L, "lessons.jsonl"), "w", encoding="utf-8") as f:
        for x in ls: f.write(json.dumps(x, ensure_ascii=False) + "\n")

sys.stdout.reconfigure(encoding="utf-8")

def main():
    c = sys.argv[1] if len(sys.argv) > 1 else "show"
    if c == "seed":
        seed = json.load(open(os.path.join(L, "seed_lessons.json"), encoding="utf-8")); have = {x["id"] for x in load()}
        ls = load() + [dict(s, ts=time.strftime("%Y-%m-%d"), source="owner_feedback") for s in seed if s["id"] not in have]
        save(ls); print(len(ls), "bai hoc")
    elif c == "feedback":
        a = sys.argv; txt = a[2]; g = lambda k: a[a.index(k) + 1] if k in a else ""
        ls = load(); nid = "L%02d" % (len(ls) + 1)
        ls.append({"id": nid, "verbatim": txt, "board_sha": sha(g("--board")) if g("--board") else "", "cause": g("--cause"), "rule": g("--rule"), "status": "CANDIDATE", "ts": time.strftime("%Y-%m-%d"), "source": "owner_feedback"})
        save(ls); print("ghi", nid)
    elif c == "refs":
        out = subprocess.run([KP, os.path.join(TOOLS, "usbc_template.py")] + sys.argv[2:], capture_output=True, text=True).stdout
        d = subprocess.run([KP, os.path.join(TOOLS, "decap_template.py"), REFROOT], capture_output=True, text=True).stdout
        json.dump({"decap": [x for x in d.splitlines() if x.strip()][:8], "ts": time.strftime("%Y-%m-%d")}, open(os.path.join(L, "patterns.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("patterns.json cap nhat"); print(d[:400])
    elif c == "edits":
        import pcbnew
        def snap(p):
            b = pcbnew.LoadBoard(p); return {f.GetReference(): (round(f.GetPosition().x / 1e6, 2), round(f.GetPosition().y / 1e6, 2), int(round(f.GetOrientationDegrees())) % 360) for f in b.GetFootprints()}
        a, n = snap(sys.argv[2]), snap(sys.argv[3]); ls = load(); k = 0
        for r in sorted(a):
            if a[r] != n.get(r):
                nid = "L%02d" % (len(ls) + 1); k += 1
                ls.append({"id": nid, "verbatim": f"[chinh sua cua owner] {r}: {a[r]} -> {n.get(r)}", "board_sha": sha(sys.argv[3]), "cause": "(chua phan tich)", "rule": "(rut ra quan he vi tri tuong doi tu chinh sua nay)", "status": "CANDIDATE", "ts": time.strftime("%Y-%m-%d"), "source": "owner_edit"})
        save(ls); print(k, "chinh sua moi duoc ghi")
    else:
        ls = load(); import collections
        print(collections.Counter(x["status"] for x in ls))
        for x in ls: print(f'{x["id"]} [{x["status"]:11s}] {x["verbatim"][:70]}')

main()
