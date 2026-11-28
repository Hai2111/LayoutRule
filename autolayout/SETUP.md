# autolayout: setup on a new machine and quickstart

## 1. What you need

| Item | Where | Note |
|---|---|---|
| KiCad 10 | kicad.org | The tools use KiCad's bundled Python (`pcbnew`, numpy, Pillow) and `kicad-cli`. |
| This repo | `git clone https://github.com/Hai2111/LayoutRule` then `git checkout proposal/autolayout-learned-20261126` | The `autolayout/` tools live on this proposal branch until the owner merges it. |
| Reference boards (owner's own designs, about 2 GB) | Copy the `ref/` folder from the original machine by hand. It is **not** in this public repo. | Default path is `<repo>/../ref/Kicad`, or set `LAYOUTRULE_REF`. |
| Git Bash (Windows) | Git for Windows | Always `export MSYS_NO_PATHCONV=1` (L80). |

## 2. Environment variables (all optional)

| Variable | Default | Used for |
|---|---|---|
| `KICAD_PY` | auto: the running Python if it can import `pcbnew`, otherwise `C:\Program Files\KiCad\<newest>\bin\python.exe` (macOS and Linux paths also searched) | Every tool that starts KiCad Python |
| `KICAD_CLI` | auto, same search | DRC, ERC, render |
| `LAYOUTRULE_TOOLS` | `<repo>/tools` | `session_start.py`, `session_gate.py` (step 0 and the reference gate) |
| `LAYOUTRULE_REF` | `<repo>/../ref/Kicad` | Reference boards for `learn.py`, `refbench.py`, and the reference images |
| `PYROUTE_RES` / `PYROUTE_MAXEXP` | 0.05 / 2500000 | Router grid size and search limit |

Check the setup:

```
"<KiCad>/bin/python.exe" autolayout/tools/kenv.py
"<KiCad>/bin/python.exe" -m unittest discover -s tests
```

## 3. Workflow (what the agent actually runs)

The full procedure is in [learn/QUY_TRINH_LAYOUT.md](learn/QUY_TRINH_LAYOUT.md). Read [OWNER_WORKING_RULES.md](OWNER_WORKING_RULES.md) first. The difference from LayoutRule main is in [PROCESS_VS_LAYOUTRULE.md](PROCESS_VS_LAYOUTRULE.md).

```
KP="<KiCad>/bin/python.exe"; T=autolayout/tools; W=<work dir>
export MSYS_NO_PATHCONV=1

# Placement (before routing)
$KP $T/place_score.py BOARD.kicad_pcb --detail            # ratsnest MST length, crossings, courtyard polygons, keepout
$KP $T/apply_place.py IN.kicad_pcb PLACE.json OUT.kicad_pcb # {REF:[x,y,rot]} plus an optional "_outline"
$KP $T/pack_small.py IN OUT @small --fix A,B --r 4        # small parts placed next to their pins; fixed groups stay
$KP $T/kpipe.py steps.json                                # chain the above safely (resumes after an interrupt)
RATS=1 S=14 $KP $T/shot.py out.png BOARD.kicad_pcb        # image with ratsnest for review

# Session with step history (undo, log)
$KP $T/agent_edit.py $W init BOARD.kicad_pcb PROJECT.kicad_pro intent.json ROOT.kicad_sch
#   copy the hierarchical sub-sheets, lib/, sym-lib-table and fp-lib-table into $W first (needed for parity)
$KP $T/agent_edit.py $W start session.json                # step 0 + reference gate (READY needed)
#   open every image in $W/session_start, replace every TODO in SESSION_START.md
$KP $T/agent_edit.py $W gate
$KP $T/agent_edit.py $W track NET F.Cu 0.2 x1,y1 x2,y2 ...    # hand route (0/45/90 degrees only)
$KP $T/agent_edit.py $W via NET X Y [size drill]
$KP $T/agent_edit.py $W route "NET1,NET2"                 # router for normal nets (respects existing copper)
$KP $T/agent_edit.py $W check                             # DRC + relational self-review + W1/C90/V1
$KP $T/agent_edit.py $W undo | move | rip | delat | gndsolid | pour | chamfer | silkrefs ...

# Review (question bank; silkscreen stage only after every place/route question passes)
$KP $T/review_run.py $W
$KP $T/route_audit.py BOARD.kicad_pcb

# Impedance: take numbers from the fab calculator; diffz only cross-checks
$KP $T/diffz.py z --w 0.22 --s 0.152 --g 0.203 --h 1.43
```

## 4. Files a session needs

These are not in the repo; they are created for each project.

- **`intent.json`:**
  - `decoupling`: list of {pin, cap, gnd_pin}.
  - `power_chains`: per net, an ordered {from, path[], width}.
  - `gnd_ties`.
- **`session.json`** (LayoutRule `SESSION_PIPELINE.md` schema):
  - One region per block.
  - Each region has a reference record: id, source_url, source_region, applicability, observed_features[].
  - Each region has a PNG made from a real reference board (`shot.py` with `CROP`).
  - A downloaded reference needs the owner's approval first.
- **`project.kicad_pro` net classes:**
  - Differential and impedance classes, for example `ETH_MDI` 0.22 / 0.152.
  - The `Power` class.

## 5. Known limits

- **`pyroute`:** fails on pins boxed in by neighbouring routes. When it does, read the image, find the cause (pin order, a B.Cu wall, a part in the way), and fix placement or route by hand.
- **`session_start.py` (LayoutRule):** zoom images are offset by about 10 mm on boards with an overhanging antenna. Check edge connectors in your own render.
- **`learn/runs.jsonl`:** history only. Absolute paths there refer to the original machine.
