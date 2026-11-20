# ITERATIVE ROUTING PLAYBOOK — vòng lặp placement ↔ routing theo phân vùng

**Trạng thái:** `PROPOSED` (2026-11-20). Chưa được owner duyệt. Xem [GOVERNANCE.md](GOVERNANCE.md).
**Dùng cùng:** [AGENT_LAYOUT_PLAYBOOK.md](AGENT_LAYOUT_PLAYBOOK.md) (phases + intent), [LAYOUT_RULES.md](LAYOUT_RULES.md) (A/P/R/G), [rules/topology_digests.json](rules/topology_digests.json) (digest input nhỏ cho ref design).

Chênh lệch so với playbook phẳng hiện có: **không** làm 1 lần "placement xong → routing xong". Thay vào đó, chia board thành **phân vùng (region)** và chạy **vòng lặp** trong mỗi vùng, chỉ mở rộng vùng khi vùng hiện tại **đạt cổng**. Mỗi vòng lặp:

```
placement(vùng) → routing(vùng) → xử lý ảnh → xử lý logic
       ↑                                        │
       └── chưa đạt: thử placement lại ──────────┤
              (routing giữ nguyên vị trí đã đặt, chỉ re-route phần chưa đạt)
                                            đạt → khóa vùng, sang vùng kế
```

Sau khi các vùng cấp 1 hoàn thành, chạy lại cổng **xử lý ảnh + xử lý logic ở cấp 2** (các vùng ghép nhau), rồi cấp 3, cuối cùng **cấp 4 = toàn mạch**.

---

## 1. Ba bất biến (invariants) — bắt buộc mọi vòng lặp

Đây là phần "mấu chốt" — nếu một bước trong vòng lặp phá bất biến nào, agent phải quay lại bước trước trong cùng vùng.

| ID | Bất biến | Ý nghĩa cụ thể | Kiểm tra |
|---|---|---|---|
| **INV-1** | **Mọi net luôn ở trạng thái "routable-ready"** | Không net nào bị kẹt: còn ít nhất 1 đường đi hình học khả thi (bề rộng + via + lớp) đến pad đích với clearance hiện hành. Không để airwire "cắt ngang" vùng chưa route. | Mỗi vòng: liệt kê net chưa hoàn thành trong vùng; với mỗi net, agent ghi 1 câu "đường đi khả thi: từ pad X qua lớp Y, qua via Z". Không viết được câu đó → INV-1 vi phạm → quay lại placement |
| **INV-2** | **Mọi component luôn ở trạng thái "relocatable"** | Placement trong vùng chưa khóa là **tạm (tentative)**: agent phải có thể di chuyển/rotate mà không phá INV-1. Chỉ đặt flag `locked` khi cả 4 bước vùng đã đạt. Không "vẽ xong rồi mới phát hiện phải dời IC" ở trạng thái không thể quay lại. | Ledger `region_ledger.json` mỗi vùng: `component | vị trí hiện | vị trí dự phòng (fallback) | locked?`. Fallback = vị trí thay thế đã tính, không phải "sẽ nghĩ sau" |
| **INV-3** | **Routing = quyết định của agent + tool thực thi, không phải tool tự chạy** | Agent ra quyết định (thứ tự net, lớp, vị trí via, topology vòng dòng, khi nào re-route), tool (Freerouting/DSN/KiCad) **chỉ thực thi** quyết định đó. Không có bước "chạy tool rồi xem được gì". | Mỗi net được route phải có entry trong ledger: `net | quyết định (lớp/via/vòng) | lý do (rule ID) | tool chạy | kết quả`. Net nào không có entry = chưa được route theo nghĩa của playbook này |

> INV-3 là khác biệt lớn nhất so với dùng routing engine trần: engine có thể DRC-pass nhưng không giải thích được *vì sao* via đặt ở đó, vòng SW đi theo hình học nào. Ledger bắt buộc việc giải trình; đó là bằng chứng để owner review.

---

## 2. Phân vùng (region) — cách chia board

| Cấp | Là gì | Ví dụ (board MCU + RF + nguồn) | Cổng |
|---|---|---|---|
| **R1 (cấp 1)** | Khối chức năng nhỏ, khép kín được: 1 nguồn con, 1 front-end, crystal+load, connector+ESD | buck converter, RF matching, USB-C+ESD | 4 bước vòng lặp đạt |
| **R2 (cấp 2)** | Nhóm các R1 cùng miền điện | "miền nguồn" = buck + LDO + bulk caps | cổng R2 = ảnh + logic **ranh giới các R1** |
| **R3 (cấp 3)** | Nửa board / trục mạch | "trục MCU" = MCU + clock + flash + debug | cổng R3 = ảnh + logic **ranh giới R2** |
| **R4 (toàn mạch)** | Board đầy đủ | — | ảnh + logic **toàn bộ** + DRC/ERC + checklist G05 |

Quy tắc chia:
- R1 được xác định **từ schematic** (khối chức năng + net class), không phải cắt hình học trước. Hình học vùng là kết quả của placement, không phải input.
- R1 nào chứa **RF / antenna / crystal / switching loop** được ưu tiên làm trước (chúng giữ "vùng cấm" lớn nhất, ảnh hưởng mọi vùng sau).
- Ranh giới vùng là đường **logic theo net**, không phải đường thẳng trên board: 1 R1 có thể là 2 mảng hình học (vd decoupling bulk ở xa regulator) — ghi rõ trong ledger.

---

## 3. Bốn bước trong vòng lặp của một vùng

### 3.1 Placement (vùng)
Theo P01–P11, thu hẹp vào phạm vi vùng. Đầu vào: `layout_intent.json` (phases 0–1 của AGENT_LAYOUT_PLAYBOOK) + digest của vùng nếu board khớp một topology trong `rules/topology_digests.json`.
- Áp INV-2: **mọi component trong vùng được đặt cùng vị trí dự phòng (fallback)** trước khi sang bước routing. Fallback = vị trí khác hợp lệ đã kiểm (không overlap, còn đường đi cho net, giữ locked items).
- Locked items (P01, mechanical, connector, antenna) không có fallback — chúng là neo.

### 3.2 Routing (vùng) — agent quyết định, tool thực thi (INV-3)
Thứ tự net trong vùng (mở rộng R02/R03 cho phạm vi vùng):
1. `switch_node`/hot loop và decoupling liên quan (P03/P04) — route cùng lúc, không tách.
2. Net bị ràng buộc: crystal, RF, differential, clock, ADC input (R02).
3. Power rail còn lại, theo D-WIDTH/D-VDROP.
4. Net thông thường.

Với **mỗi** net: agent ghi entry ledger (lớp, vị trí via, lý do + rule ID) → gọi tool thực thi → tool trả kết quả → agent **đọc kết quả bằng mắt (ảnh) trước khi route net kế**. Không gom "chạy hết rồi mới xem".

### 3.3 Xử lý ảnh (visual pass)
Render 2–3 view của vùng (KiCad 2D F.Cu/B.Cu, zoom vùng) và kiểm:
- Trace chạy dưới thân component (body keepout — P04, D-SMPS)
- Vòng dòng có nhỏ/đúng hình học không (di/dt loop, decoupling path)
- Plane GND có bị xẻ/khe hở dưới các net (R05/R06, D-VIA "không khoét khe")
- Courtyard/courtyard overlap, silkscreen trên pad
- Congestion: vùng nào còn "chặt" — đây là tín hiệu để quay lại placement
**Kết quả:** danh sách tìm kiếm, mỗi item ghi `vị trí | vấn đề | ảnh hưởng (rule ID)`.

### 3.4 Xử lý logic (logical pass)
Kiểm trên netlist/hình học (không cần ảnh):
- **INV-1 check**: với mọi net chưa hoàn thành trong + ngoài vùng, xác nhận còn đường đi khả thi (đặc biệt các net xuyên vùng — xem §4)
- **INV-2 check**: mọi component chưa locked trong vùng có fallback hợp lệ (fallback chưa bị bước 3.2/3.3 chiếm chỗ)
- **INV-3 check**: ledger đầy đủ cho 100% net đã route trong vùng
- DRC scoped (clearance, hole/copper, unconnected): chạy `tools/drc_body_keepout.py` + KiCad DRC scoped theo vùng
- ERC/net-to-pad: không net nào đổi tính chất sau routing

**Cổng vùng:** 3.3 + 3.4 không có item FAIL nào thuộc scope vùng (item ngoài vùng được ghi nhận, không chặn) → **khóa vùng**: component `locked=yes`, vùng ghi vào `region_ledger.json` với hash board file.

Chưa đạt → **quay lại 3.1** nhưng theo quy tắc: **giữ nguyên vị trí đã route tốt, chỉ thử placement lại những component liên quan đến net chưa đạt** (re-route tại vị trí cũ = không làm lại toàn bộ, chỉ re-route phần còn nợ). Lặp.

> Giới hạn lặp: nếu 2 vòng liên tiếp cùng vùng không tiến bộ (cùng item FAIL), dừng trong vùng đó và ghi `NEEDS_REVIEW` kèm 2 phương án placement thay thế cho owner — không tự bịa vòng thứ 3.

---

## 4. Cổng liên vùng (R2 → R3 → R4)

Khi các R1 con của một R2 đều đã khóa:

1. **Xử lý ảnh ở ranh giới:** render các R1 con nằm cạnh nhau (1 ảnh tổng, zoom đường ranh giới). Kiểm: trace xuyên ranh giới có chạy gọn không, có "căng" (cong vòng qua vùng con) không, net xuyên R1 có giữ đường ngắn/đúng lớp không, via xuyên vùng có vi phạm D-VIA (khe plane) không.
2. **Xử lý logic ở ranh giới:** mọi net thuộc ≥2 R1 đã hoàn thành phải khớp (cùng net class, không conflict via/plane). Chạy liên thông net (tool `layout_audit.py` union-find) cho tập R2.
3. R2 đạt → khóa, lên R3, lặp lại với ranh giới R2. R4 (toàn mạch) = ảnh + logic toàn board + DRC/ERC đầy đủ + checklist REVIEW_CHECKLIST.md.

Ranh giới nào FAIL → không mở khóa lại các R1 con ngay: trước tiên thử **chỉ re-route các net xuyên ranh giới** (giữ placement, rẻ nhất). Chỉ khi không đạt mới mở khóa R1 con (giữ hash để rollback).

---

## 5. File ledger (bằng chứng, bắt buộc có)

Mỗi vùng sinh `region_ledger.json` (1 file/vùng, nằm cùng project, không commit vào LayoutRule):

```json
{
  "region": "R1-buck",
  "board_sha256": "...",
  "iterations": [
    {"n": 1, "placement_changes": ["U2 moved 3mm left", "L1 rotated 90"],
     "nets_routed": ["SW", "VIN", "VOUT"],
     "visual_findings": [{"at": "U2 SW pad", "issue": "trace under body", "rule": "P03/D-SMPS"}],
     "logic_findings": [{"net": "VOUT", "inv": "INV-1", "ok": true}],
     "result": "loop"}
  ],
  "locked_at_iteration": 2,
  "nets_ledger": [
    {"net": "SW", "layer": "F.Cu", "vias": 0, "reason": "switch_node, max_vias:0 (A02/class)", "tool": "agent+freerouting", "outcome": "PASS"}
  ],
  "open_items": []
}
```

Owner review đọc ledger trước, đọc board sau.

---

## 6. Đọc ref design với input nhỏ (đi cùng `rules/topology_digests.json`)

Mục tiêu: **một agent session đọc được và hiểu được 1 ref design mà không cần parse toàn bộ file .kicad_pcb** — input chỉ gồm:
- `digest` (JSON, 1 entry/board): topology class, số component/net/lớp, các khối chính, net class đặc trưng, "neo" hình học (antenna, connector, mount), lưu ý vùng nhạy.
- 2–3 ảnh render (top/bottom/vùng RF) nếu cần đối chiếu trực quan.

Quy trình:
1. Chọn digest theo class (xem `topology_digests.json` → `match_hints`). Digest `light` (≤ ~50 component, topology 1 trục) thì chỉ cần digest + ảnh top. `medium` cần thêm danh sách net class.
2. **Xác nhận khớp:** so digest với board thật (số component, refdes chính, layer) bằng 1 lệnh grep/thống kê nhanh — không parse toàn bộ.
3. Dùng digest làm seed cho `layout_intent.json` của board đích **nếu** topology trùng class; khác class thì chỉ dùng làm tham chiếu hình học (positioning blocks), không copy net topology.
4. Ghi trong intent: `reference_digest: <id> @ <sha của digest>` — đủ để truy vết.

Ngưỡng class (đề xuất, chưa owner duyệt):
| Class | Component | Net | Ví dụ digest |
|---|---|---|---|
| `light` | ≤ 50 | ≤ 70 | RA01 (smoke detector MCU board, 47 comp, 60 nets, 2 lớp) |
| `medium` | 50–300 | 70–400 | BLE2LTE, LoraGw (RF + MCU + nguồn) |
| `heavy` | > 300 hoặc BGA/multi-rail nhiều | > 400 | chưa có digest mẫu |

---

## 7. Khi nào dừng / hỏi owner (mở rộng mục 7 của AGENT_LAYOUT_PLAYBOOK)

Chỉ hỏi owner khi: (a) 2 vòng lặp bế tắc trong cùng vùng (§3), (b) INV-2 không thể thỏa cho component nào (không còn fallback hợp lệ), (c) digest không khớp class của board đích và không có ref khác. Mọi trường hợp khác: tiếp tục theo vòng lặp.

---

**Rollback:** xóa file này + `rules/topology_digests.json`, revert index pointer trong LAYOUT_RULES.md / AGENT_LAYOUT_PLAYBOOK.md. Không file nào khác của repo bị chạm.
