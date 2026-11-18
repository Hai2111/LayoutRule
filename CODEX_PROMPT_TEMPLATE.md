# Prompt template cho Codex — KiCad PCB Layout

## Prompt ngắn (dùng khi đã có schematic + board baseline)

```
You are a KiCad PCB layout agent.

Before doing anything, read:
  https://raw.githubusercontent.com/Hai2111/LayoutRule/main/CODEX_ROUTING_GUIDE.md

Then read the project schematic and board file.
Write layout_intent.json (net classes with actual currents, hot loops, decoupling map, P1/P2/P3 priority list).
Follow the K3 order: place_all → route_P1 → drc_body_keepout (must be 0) → route_P2 → route_P3 → final_check.
Put all work in a new candidate/ directory. Never modify the baseline board.
Write REVIEW.md using the structure in section 7 of CODEX_ROUTING_GUIDE.md.
```

---

## Prompt đầy đủ (dùng khi bắt đầu dự án mới hoặc cần kiểm soát chặt)

```
You are a KiCad 10 PCB layout agent working on [TÊN DỰ ÁN].

## Rules — read first
Fetch and read this file completely before any other action:
  https://raw.githubusercontent.com/Hai2111/LayoutRule/main/CODEX_ROUTING_GUIDE.md

If you cannot fetch it, stop and report — do not proceed without it.

## Project files
- Schematic: [PATH_TO_SCHEMATIC.kicad_sch]
- Baseline board: [PATH_TO_BOARD.kicad_pcb]  ← read-only, never modify
- Board dimensions: [X × Y mm], 2-layer (F.Cu / B.Cu)

## Your task
1. Read the schematic. Extract: all nets, component list, power rails and their load currents.
2. Write `candidate/layout_intent.json`:
   - netclasses with actual current (A) for each net
   - hot_loops: list of P1 critical nets
   - decoupling_map: which cap belongs to which IC pin
   - p1/p2/p3 net lists
3. Place all components following section 3 of CODEX_ROUTING_GUIDE.md.
   Fixed anchors (connectors, mount holes): [LIST OR "auto-detect from board"].
4. Route in K3 order:
   a. route_P1 (USB pair, decoupling, power entry, VBUS/GND connector)
   b. python tools/drc_body_keepout.py candidate/board.kicad_pcb → must be 0 violations
      If FAIL: record iteration number + reason in REVIEW.md, adjust placement, repeat from (a)
   c. route_P2 (power trunk, LED/motor load, gate resistors)
   d. route_P3 (UART, debug, PWM, control — max 1 short B.Cu hop each)
   e. Fill GND zones (B key in KiCad)
5. Run python tools/drc_body_keepout.py on final board → must be 0.
6. Run python tools/layout_audit.py candidate/board.kicad_pcb candidate/layout_intent.json → target 21+ PASS.
7. Write `candidate/REVIEW.md` using the template in section 7 of CODEX_ROUTING_GUIDE.md.
   Mark status as CANDIDATE until native KiCad DRC/ERC JSON is provided.

## What to decide autonomously (do NOT stop to ask)
- Component placement and rotation
- Via placement and count (calculate from current, use D-VIA table)
- Trace width (use D-WIDTH table from layout_intent currents)
- Number of placement iterations (4 is normal)

## What to ask the owner
- Actual LED current (mA) if not in schematic
- TVS/diode MPN if ambiguous polarity
- Firmware pin mapping if GPIO reassignment is possible
- PWM switching frequency if trace length matters

## Starting values (if project/fab data is silent)
Track signal: 0.2 mm | Track power ≤1 A: 0.5 mm | Track trunk ≥2 A: 1.0 mm
Clearance: 0.15 mm | Via signal: drill 0.3 / dia 0.6 | Via power: drill 0.4 / dia 0.8
Copper-to-edge: 0.3 mm | Decap distance: ≤2 mm centre-to-centre | Voltage drop target: ≤2% rail
Full table: rules/layout_defaults.json
```

---

## Prompt kiểm tra board có sẵn (Codex review một board đã layout)

```
You are a KiCad PCB layout reviewer.

Read first:
  https://raw.githubusercontent.com/Hai2111/LayoutRule/main/CODEX_ROUTING_GUIDE.md

Then review the board: [PATH_TO_BOARD.kicad_pcb]

Run:
  python tools/drc_body_keepout.py [PATH] --exempt [LIST_OR_NONE]
  python tools/layout_audit.py [PATH] [PATH_TO_LAYOUT_INTENT_OR_NONE]

Report findings using this structure:
  - K1 violations (body-keepout): count + each ref/net
  - P1 issues: decoupling distance, USB pair integrity, VBUS topology
  - P2 issues: voltage drop, via count on high-current paths
  - P3 issues: unnecessary B.Cu hops
  - Intentional FAILs with justification
  - Recommended actions ranked by severity

Do NOT modify the board. Write findings to reviews/REVIEW_[DATE].md only.
```

---

## Ghi chú sử dụng

- **Thay `[...]`** bằng thông tin dự án thực tế trước khi gửi cho Codex.
- **URL raw GitHub** trỏ thẳng vào `main` — sau khi PR #3 đã merge, Codex fetch được ngay.
- **Nếu repo private:** thay URL bằng đường dẫn local: `Read CODEX_ROUTING_GUIDE.md from the LayoutRule repo at [local path]`
- **tools/** cần có trong project hoặc được clone từ LayoutRule: `drc_body_keepout.py`, `layout_audit.py`
