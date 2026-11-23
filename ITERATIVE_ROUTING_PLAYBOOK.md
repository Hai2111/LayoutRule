# ITERATIVE ROUTING PLAYBOOK — vòng lặp placement ↔ routing theo phân vùng

**Trạng thái:** `APPROVED` (owner Hai, 2026-11-20, merge `b08e9d5`) — scope: phương pháp thực thi theo vùng + 3 bất biến INV-1/2/3, không phải thay đổi nội dung luật A/P/R/G. Các ngưỡng class trong `rules/topology_digests.json` vẫn PROPOSED. Xem [GOVERNANCE.md](GOVERNANCE.md).
**Dùng cùng:** [AGENT_LAYOUT_PLAYBOOK.md](AGENT_LAYOUT_PLAYBOOK.md) (phases + intent), [LAYOUT_RULES.md](LAYOUT_RULES.md) (A/P/R/G), [rules/topology_digests.json](rules/topology_digests.json) (digest input nhỏ cho ref design).

Chênh lệch so với playbook phẳng hiện có: **không** làm 1 lần "placement xong → routing xong". Thay vào đó, chia board thành **phân vùng (region)** và chạy **vòng lặp** trong mỗi vùng, chỉ mở rộng vùng khi vùng hiện tại **đạt cổng**. Mỗi vòng lặp:

```
placement(vùng) → routing(vùng) → xử lý ảnh → xử lý logic
       ↑                                        │
       └── chưa đạt: thử placement lại ──────────┤
              (routing giữ nguyên vị trí đã đặt, chỉ re-route phần chưa đạt)
                                            đạt → ghi snapshot/ledger, sang vùng kế (KHÔNG khóa)
```

Sau khi các vùng cấp 1 hoàn thành, chạy lại cổng **xử lý ảnh + xử lý logic ở cấp 2** (các vùng ghép nhau), rồi cấp 3, cuối cùng **cấp 4 = toàn mạch**.

---

## 1. Ba bất biến (invariants) — bắt buộc mọi vòng lặp

Đây là phần "mấu chốt" — nếu một bước trong vòng lặp phá bất biến nào, agent phải quay lại bước trước trong cùng vùng.

| ID | Bất biến | Ý nghĩa cụ thể | Kiểm tra |
|---|---|---|---|
| **INV-1** | **Mọi net luôn ở trạng thái "routable-ready"** | Không net nào bị kẹt: còn ít nhất 1 đường đi hình học khả thi (bề rộng + via + lớp) đến pad đích với clearance hiện hành. Không để airwire "cắt ngang" vùng chưa route. | Mỗi vòng: liệt kê net chưa hoàn thành trong vùng; với mỗi net, agent ghi 1 câu "đường đi khả thi: từ pad X qua lớp Y, qua via Z". Không viết được câu đó → INV-1 vi phạm → quay lại placement |
| **INV-2** | **Mọi component luôn ở trạng thái "relocatable"** | Placement/routing là **tạm (tentative)** kể cả sau khi checkpoint đạt và sau khi owner review. Agent có thể di chuyển/rotate hoặc rip-up/re-route khi đánh giá toàn board tốt hơn. **Chỉ neo đã xác nhận phải khớp cơ khí mới bất động.** | Ledger `region_ledger.json`: `component | vị trí hiện | fallback | mechanical_anchor?`; mọi thay đổi lưu hash/snapshot để rollback |
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
- **Thứ tự đặt "cứng → mềm" (chuẩn kỹ sư):**
  1. Neo cơ khí: chỉ connector, lỗ bắt vít, anten/vỏ và linh kiện có vị trí **bắt buộc theo khớp cơ khí thực** được bất động; không tự khóa battery hay SMD to nếu không có ràng buộc cơ khí.
  2. **Vòng nóng**: đặt IC nguồn trước, rồi `C-in → L → C-out` *bao quanh IC* thành vòng khép nhỏ nhất (P03). Decap nằm giữa pin nguồn và IC, không phải "gần theo thước" (P04).
  3. IC chủ (MCU/RF FE): đặt sao net quan trọng ngắn; **nhìn ratsnest xuyên ngang board = dấu hiệu phải dời cả khối**, không chỉnh từng linh kiện.
  4. Passive còn lại: lấp theo từng net/khối.
- Áp INV-2: **mọi component trong vùng được đặt cùng vị trí dự phòng (fallback)** trước khi sang bước routing. Fallback = vị trí khác hợp lệ đã kiểm (không overlap, còn đường đi cho net, giữ neo cơ khí bắt buộc). Neo không có fallback.

### 3.2 Routing (vùng) — agent quyết định, tool thực thi (INV-3)
**2 hành vi chuẩn, bắt buộc trong mọi vòng lặp:**
- **H1 — Route ⇄ xê linh kiện xuyên suốt (không đợi route xong mới đặt lại):** kỹ sư route được vài net là đã xê 1 IC. Quy tắc: net nào đi không lọt (kẹt, vòng quá to, cắt plane) → **xê linh kiện gần đó, route lại đúng chỗ đó, ngay trong vòng lặp hiện tại**. Chỉ dừng lại để visual pass khi không còn net "không lọt" nào. Ghi mỗi lần xê vào ledger (`placement_changes`).
- **H2 — Ảnh ratsnest/congestion là bản đồ đầu vào của mỗi vòng lặp:** trước khi route (và trước mỗi visual pass), render **1 ảnh ratsnest của vùng** (sợi chằng chịt + mật độ). Ảnh này là "bản đồ" quyết định: chỗ nào sợi đặc nhất → linh kiện/khối nào cần xê trước; chỗ nào đã trống → route được ngay. Không có ảnh bản đồ → chưa được bắt đầu vòng lặp.

Thứ tự net trong vùng (mở rộng R02/R03 cho phạm vi vùng):
1. `switch_node`/hot loop và decoupling liên quan (P03/P04) — route cùng lúc, không tách.
2. Net bị ràng buộc: crystal, RF, differential, clock, ADC input (R02).
3. Power rail còn lại, theo D-WIDTH/D-VDROP.
4. Net thông thường.

Với **mỗi** net: agent ghi entry ledger (lớp, vị trí via, lý do + rule ID) → gọi tool thực thi → tool trả kết quả → agent **đọc kết quả bằng mắt (ảnh) trước khi route net kế**; kẹt thì áp H1 ngay. Không gom "chạy hết rồi mới xem".

**Cách gọi tool thực thi (recipe, 1 lệnh):** `powershell -NoProfile -ExecutionPolicy Bypass -File tools\route_pipeline.ps1 -Board BOARD.kicad_pcb -SessionManifest session.json -CandidateBoard AGENT_BOARD.kicad_pcb -IntentPath layout_intent.json` — nhận **candidate agent tự tạo**, sao chép vào thư mục tạm, chạy DRC native + audit + render ảnh; **Freerouting toàn board chỉ khi được gọi với `-FreeroutingProposal` như thử nghiệm, không chứng minh INV-3**. Pipeline xong ≠ vùng đạt: agent vẫn phải chạy 3.3/3.4 (ảnh + logic), ghi ledger và snapshot; **không khóa vùng**. Limitations: xem `setup/SMOKE_TEST.md` (board convert Altium chưa export được DSN).

### 3.3 Xử lý ảnh (visual pass) — scan 3 tầng, từ xa đến gần (chuẩn kỹ sư review)
Render chuẩn: **1 ảnh F.Cu + 1 ảnh B.Cu** (cùng zoom), bật copper + silkscreen + courtyard; zoom vừa đủ thấy cả vùng + ranh giới. Scan theo 3 tầng, KHÔNG liệt kê ngang nhau:

**Tầng 1 — board-level (zoom xa nhất, ~30 giây):** bố cục khối đúng đường (nguồn→MCU→RF), các neo đúng chỗ (antenna rìa board, connector, mount), mật độ bất thường (đặc = nút nghẽn).

**Tầng 2 — scan khối theo thứ tự RỦI RO ĐIỆN (không theo tên net):**
| Ưu tiên | Vùng/rủi ro | Dấu hiệu thị giác | Hành động sửa |
|---|---|---|---|
| 1 | Vòng nóng (buck/boost) | diện tích vòng VIN→SW→L→out lớn; decap không nằm giữa pin–IC | xê C-in/L/C-out vào sát IC (P03), thu vòng |
| 2 | RF/antenna | trace/via chui vào keepout; matching xa đầu antenna | mở rộng keepout, dời matching sát antenna (P07) |
| 3 | Clock/crystal | đường dài, có via, song song dài với net khác | rút ngắn, bỏ via, tách song song (P05/R10) |
| 4 | Return path (mặt B.Cu) | plane bị xẻ/khe hở dưới net tốc độ cao, via đổi lớp không có stitching | bổ sung stitching, dời via (R05/R06/G03) |

**Tầng 3 — chi tiết (zoom sát):** via mọc thành đám (nhiễu/dòng), trace dưới thân component, silkscreen trên pad, testpoint không chạm được (DFM).

**Kết quả:** danh sách vấn đề theo đúng thứ tự trên (rủi ro cao đứng trước), mỗi item: `vị trí | vấn đề | ảnh hưởng (rule ID) | sửa thế nào`.

### 3.4 Xử lý logic (logical pass)
Kiểm trên netlist/hình học (không cần ảnh):
- **INV-1 check**: với mọi net chưa hoàn thành trong + ngoài vùng, xác nhận còn đường đi khả thi (đặc biệt các net xuyên vùng — xem §4)
- **INV-2 check**: mọi component không phải neo cơ khí vẫn có phương án dịch/rotate/rollback; không gắn cờ `locked` khi chỉ vì một vùng đã đạt
- **INV-3 check**: ledger đầy đủ cho 100% net đã route trong vùng
- DRC scoped (clearance, hole/copper, unconnected): chạy `tools/drc_body_keepout.py` + KiCad DRC scoped theo vùng
- ERC/net-to-pad: không net nào đổi tính chất sau routing

**Checkpoint vùng (nội bộ):** 3.3 + 3.4 không có item FAIL thuộc scope vùng → **ghi snapshot + board hash + ledger**, cho phép mở rộng sang vùng kế. **Không khóa component, copper hay region**; quay lại sửa nếu phát hiện tối ưu toàn board tốt hơn.

### 3.5 Evidence theo vùng (NỘI BỘ; không hỏi owner giữa phiên)

Agent lưu ảnh PCB 2D KiCad, findings tối đa 5 dòng, reference ID + vùng nguồn đã học,
hai candidate REF/OPT và ledger cho từng R1/R2/R3/R4. **Không gửi yêu cầu duyệt
từng vùng.** Khi thiếu ảnh/lớp reference bắt buộc: GLOBAL STOP toàn PCB,
chỉ được tìm kiếm tài liệu và chuẩn bị báo cáo BLOCKED.

**ONE SESSION = ONE OWNER REVIEW:** G1/G3/G5 chỉ là checkpoint nội bộ; owner **chỉ review bản cuối** của phiên sau khi agent đã hoàn tất báo cáo (hoặc một báo cáo BLOCKED khi thiếu bằng chứng);
xuất một ảnh tổng hợp Reference / Candidate REF / Candidate OPT
và tối đa 5 dòng tổng kết cho owner. Log DRC/geometry/history để agent lưu riêng.
Bắt buộc owner duyệt batch trước khi thay thế PCB chính thức hay merge rule. **Sau khi owner review cũng không tự khóa layout**: agent ghi nguyên văn feedback, nguyên nhân giả thuyết và kiểm thử trong phiên sau theo REVIEW_LEARNING_LOOP.md.
Cách chạy và schema: SESSION_PIPELINE.md.

Chưa đạt → **quay lại 3.1** nhưng theo quy tắc: **giữ nguyên vị trí đã route tốt, chỉ thử placement lại những component liên quan đến net chưa đạt** (re-route tại vị trí cũ = không làm lại toàn bộ, chỉ re-route phần còn nợ). Lặp.

> Giới hạn lặp: nếu 2 vòng liên tiếp cùng vùng không tiến bộ, ghi `NEEDS_REVIEW`, thử phương án vùng/placement thay thế hoặc kết thúc phiên bằng **một báo cáo cuối** với các lựa chọn; không hỏi owner lẻ.

---

## 4. Cổng liên vùng (R2 → R3 → R4)

Khi các R1 con của một R2 đạt checkpoint nội bộ:

1. **Xử lý ảnh ở ranh giới:** render các R1 con nằm cạnh nhau (1 ảnh tổng, zoom đường ranh giới). Kiểm: trace xuyên ranh giới có chạy gọn không, có "căng" (cong vòng qua vùng con) không, net xuyên R1 có giữ đường ngắn/đúng lớp không, via xuyên vùng có vi phạm D-VIA (khe plane) không.
2. **Xử lý logic ở ranh giới:** mọi net thuộc ≥2 R1 đã hoàn thành phải khớp (cùng net class, không conflict via/plane). Chạy liên thông net (tool `layout_audit.py` union-find) cho tập R2.
3. R2 đạt → ghi checkpoint, lên R3 (không khóa vùng), lặp lại với ranh giới R2. R4 = ảnh + logic toàn board + DRC/ERC đầy đủ + checklist REVIEW_CHECKLIST.md.

Ranh giới nào FAIL → thử trước **re-route các net xuyên ranh giới** với placement giữ nguyên để giảm chi phí. Nếu không cải thiện, được phép dịch lại R1/R2 liên quan (giữ snapshot/hash để rollback); không cần cơ chế mở khóa.

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
  "checkpoint_iteration": 2,
  "mechanical_anchors": ["J1: mating position fixed"],
  "nets_ledger": [
    {"net": "SW", "layer": "F.Cu", "vias": 0, "reason": "switch_node, max_vias:0 (A02/class)", "tool": "agent+freerouting", "outcome": "PASS"}
  ],
  "open_items": []
}
```

Agent lưu ledger để tự kiểm; owner chỉ cần xem ảnh tổng hợp và các quyết định cuối phiên.

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

## 7. Khi nào dừng phiên / báo owner một lần (mở rộng mục 7 của AGENT_LAYOUT_PLAYBOOK)

Agent **chỉ trình bản cuối** sau khi đã tự xử lý các checkpoint G1/G3/G5, đánh giá toàn mạch và viết xong báo cáo. Nếu bế tắc hoặc thiếu bằng chứng reference bắt buộc (GLOBAL STOP) thì đóng phiên bằng **một báo cáo BLOCKED**, không gửi bản dở dang để duyệt. Sau feedback owner, agent ghi bài học cho phiên sau; không khóa placement/routing.

---

**Rollback:** xóa file này + `rules/topology_digests.json`, revert index pointer trong LAYOUT_RULES.md / AGENT_LAYOUT_PLAYBOOK.md. Không file nào khác của repo bị chạm.
