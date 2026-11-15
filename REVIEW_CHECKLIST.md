# PCB REVIEW CHECKLIST (agent + human)

Mỗi check: `rule_id, status(PASS|FAIL|NEEDS_REVIEW|NA), evidence, file_hash, net/refdes/xy, rationale, fix`. Không tự đổi `NEEDS_REVIEW` thành `PASS`.

| Phase | Questions | Expected evidence |
|---|---|---|
| 1. Input integrity | Netlist vs PCB có đồng nhất? Footprint đúng MPN pin1/polarity? Constraints có nguồn? | ERC, netlist compare, fab stackup |
| 2. Mechanical | Connectors, holes, keepouts, 3D heights, antenna clearance đúng? User-moved components có được giữ? | board outline, 3D exports, diff |
| 2b. Vendor-specific exceptions | Crystal/clock rule, RF matching, layout current loop, USB/SDIO rules có đúng theo **đúng IC+revision**? | RDxx source + PTxx checks + measured footprint/pad distances |
| 2c. Isolation + multi-channel | Domains and creepage defined? Repeated analog channels have comparable routing/return where gain/phase matching requires it? | PT13/PT14 pattern+fab standard+channel map |
| 3. Functional placement | Đã chia block? Có sự giao cắt/đường dài bất thường giữa các khối? Buck/boost loop và decouplers đúng topology? | block annotation + loop sketches |
| 4. Critical routing | Clocks, RF, USB/diff, AFE, clock buses có return path hợp lệ? Trace width/spacing/impedance được tính? | net-class & route report |
| 5. Power & ground | Di/dt loops đủ nhỏ? Vdrop/trace thermal đủ? GND không bị ngắt/đảo? Via transfer hợp lý? | loop map, plane map, current analysis |
| 6. Manufacturing | DRC = 0 hard errors; fab holes, mask slivers, silk/polarity, land patterns, test points, footprints hợp lý? | DRC, 3D, Gerber viewer, fab notes |
| 7. Independent review | Có vấn đề dù DRC=0? Mỗi ngoại lệ đã nêu risk/owner? | review summary / exception log |

### Block release immediately
- Short, missing net, wrong pin/polarity, unsafe current/voltage/clearance, invalid footprint, manufacturing infeasibility.
- Critical route/ground-path violation with no mitigation.
- Deleting/undoing user changes without explicit evidence and authorization when it affects committed decisions.

### Non-blocking by default
- 90° trace corner **in isolation**, generic visual aesthetic, via count when no evidence it harms result, subjective “too far” cap without loop analysis.

### Review feedback / anti-regression
- On each changed PCB file: snapshot hash and diff; rerun only dependency-relevant checks plus full DRC.
- When a user fixes an item, append `resolved_by_user` and do not repeat it without a new regression.
- When candidate improves metrics but breaks an earlier validated critical loop, reject it or seek approval.
- Report actionable findings first: **severity, net/component, coordinates, explanation, evidence, proposed patch**, not generic PCB advice.
