# CODEX ROUTING GUIDE — Hướng dẫn tổng hợp cho agent layout KiCad

**Trạng thái:** PROPOSED 2026-11-18. Chưa được owner duyệt; chờ merge vào main.  
**Nguồn:** tổng hợp từ LAYOUT_RULES.md, AGENT_LAYOUT_PLAYBOOK.md, LESSONS_LEARNED.md,  
rules/layout_defaults.json, và kinh nghiệm thực tế session STM8 RGB USB-C V8 (2026-11-17).  
**Dùng thay cho:** không — đây là index tổng hợp; các file gốc vẫn là nguồn chính.

---

## Phần 0 — Tư duy nền tảng (đọc trước khi làm bất cứ gì)

### 0.1 Layout là thực thi ý đồ điện, không phải nối cho hết airwire

DRC = 0 lỗi **không** có nghĩa là mạch chạy được.  
Trước khi đặt linh kiện đầu tiên, phải viết `layout_intent.json`:
- Netclass của mỗi net (kèm dòng thực tế)
- Vòng nóng (hot loop) và vòng nhạy (sensitive loop)
- Map decoupling: chân nào của IC nào cần tụ nào
- Danh sách ưu tiên P1/P2/P3 (xem Phần 2)

### 0.2 "Nối được" ≠ "hoạt động được"

Ba điều kiện hoàn thành thực sự:
1. **Đúng thứ tự ưu tiên** — P1 xong và sạch trước khi route P2
2. **Không vi phạm body-keepout** — K1 (xem Phần 1)
3. **Return path hợp lệ** — dòng GND có đường về ngắn tương ứng với mỗi nhánh nguồn

### 0.3 Thất bại do placement sai thì phải đặt lại, không được patch routing

Nếu sau khi route P1 mà drc_body_keepout.py báo lỗi → **loại candidate, đặt lại từ đầu**.  
Patch routing trên nền placement sai chỉ dịch vi phạm từ chỗ này sang chỗ khác.  
(Kiểm chứng thực tế: V7 patch V6 → 49 vi phạm, V8 đặt lại → 0 vi phạm.)

---

## Phần 1 — Ba luật cứng K1/K2/K3 (cấm tuyệt đối)

### K1 — Không trace dưới bụng linh kiện

| Cấm | Giải thích |
|---|---|
| Dưới thân R, C, L, D dạng SMD | Body bbox từ F.Fab layer |
| Giữa hai pad của bất kỳ linh kiện nào | Kể cả pad cùng net |
| Dưới thân SOT-23 | Vùng giữa hai hàng pad |
| Dưới vỏ kim loại connector | USB shell, RJ45 shell, v.v. |

**Vùng xám (không cấm, cần ghi chú):** trace trong *kênh* giữa hai hàng chân SOIC/TSSOP (không phải dưới thân IC) — phải ghi vào REVIEW.md nếu dùng.

**Ngoại lệ có cơ sở:** nếu topology bắt buộc (ví dụ cầu D+/D− USB-C do pin-out xen kẽ 16 chân) → khai báo trong `--exempt` của checker và giải thích trong REVIEW.md.

**Kiểm tra:** `python tools/drc_body_keepout.py board.kicad_pcb [--exempt REF,NET]`  
→ Phải 0 vi phạm trước khi route P2.

### K2 — Cấm "route in order, done when connected"

Không được route tuần tự net 1 → net N rồi xác nhận xong khi tất cả node đã nối.  
Nếu làm vậy: P1 bị hi sinh cho P3, return path không được thiết kế, kết quả "chạy được nhưng không hoạt động được".

### K3 — Thứ tự bắt buộc: Place → P1 → check → P2 → P3

```
place_all()           # J1–Jn cố định; đặt lại tất cả còn lại
  → route_P1()        # USB/vi sai, decoupling, connector cluster, vòng nóng
  → drc_body_keepout.py → phải 0 vi phạm
  → if FAIL: ghi số vòng + lý do vào REVIEW.md, adjust_placement(), goto route_P1
  → route_P2()        # trunk nguồn, tải dòng lớn, gate MOSFET
  → route_P3()        # UART, debug, control, PWM — tối đa 1 B.Cu hop ngắn/net
  → final_check()
```

Mỗi vòng lặp placement bị loại phải ghi số thứ tự và lý do vào REVIEW.md.  
4 vòng lặp là bình thường; đừng vội xác nhận vòng đầu tiên.

---

## Phần 2 — Phân cấp ưu tiên routing

### P1 — Route trước tiên, không được vi phạm sau khi xong

| Net/nhóm | Width | Via | Yêu cầu đặc biệt |
|---|---|---|---|
| USB / vi sai | 0.2 mm | 0 | Song song từ đầu đến cuối, skew ≤ 1 mm, không trace nào cắt ngang |
| Decoupling cap | ≥ pad width | Via GND riêng mỗi tụ | Nguồn vào pad tụ trước, rồi mới tới chân IC |
| CC pull-down (USB-C) | 0.2 mm | — | Sát connector |
| GND shield/connector | 0.4 mm | Via gần chân | Trước khi route bất kỳ P2 nào |
| VBUS, TVS, bulk cap | 0.5 mm | ≥ 2 via/chỗ đổi lớp | Nối đầy đủ trước P2 |

**Luật decoupling bắt buộc (board 2 lớp):**  
Nguồn → pad tụ → (rồi mới) → chân IC. Không được đấu ngược.  
Via GND của tụ đặt sát pad GND của tụ, trong vòng 1 mm.  
Mỗi tụ một via GND riêng, không dùng chung.

### P2 — Route sau khi P1 đã sạch

| Net/nhóm | Width | Ghi chú |
|---|---|---|
| Trunk nguồn chính → connector tải | 0.8 mm min | 0 via preferred; sụt áp < 2% rail |
| Nhánh nguồn MCU | 0.3–0.5 mm | Vào tụ trước, rồi tới chân |
| Tải LED / motor | 0.3–0.5 mm theo dòng | Trở gate ≤ 3 mm từ chân gate MOSFET |
| Nguồn các IC phụ | 0.3 mm | Như MCU |

**Quy tắc sụt áp:**  
Mục tiêu ≤ 2% rail; phải xem xét lại nếu > 5%.  
Công thức: `V = I × (ρ × L) / (w × t)`, trong đó t = 35 µm (1 oz), ρ = 1.72×10⁻⁸ Ω·m.  
Ví dụ: 0.5 A, 30 mm, 0.8 mm, 1 oz ≈ 13 mV trên rail 5V = 0.26% ✓

**Quy tắc via khi đổi lớp trên net nguồn:**  
- Số via: `n = max(2, ceil(I / dòng_mỗi_via))` (via 0.3 mm drill: 0.8 A; via 0.4 mm drill: 1.0 A)
- Dàn via ngang bề rộng trace, không xếp một hàng dọc theo chiều dòng
- Đổi lớp trên đoạn thẳng, không ở góc cua
- GND return của tải cũng phải có số via tương đương

### P3 — Route cuối, được phép 1 B.Cu hop ngắn mỗi net

| Net | B.Cu hop tối đa | Điều cấm |
|---|---|---|
| UART TX/RX | Không cần nếu placement tốt | Không đi dưới USB pair, trunk nguồn |
| SWIM, NRST | 1 hop ≤ 4 mm | Không cắt GND plane tạo slot |
| PWM, debug | 1 hop ≤ 4 mm | Không đi dưới P2 load path |

**Luật B.Cu hop (2-layer board):**  
- Chỉ là jumper: ngắn, thẳng, vuông góc hướng dòng GND hồi nếu được
- Không nhảy bên dưới vòng nóng, cặp vi sai, decoupling, cuộn cảm
- Hai jumper song song phải cách đủ để GND chảy giữa chúng
- Sau fill: B.Cu GND phải là **một** vùng liền

---

## Phần 3 — Placement: quy tắc và tư duy

### 3.1 Thứ tự đặt

1. Cố định cơ khí: connector, mount hole, switch, antenna (không di chuyển)
2. Phân khối chức năng: power, MCU, USB bridge, tải (LED/motor), debug
3. Đặt IC chính trong mỗi khối
4. Đặt decoupling **ngay cạnh chân nguồn** của IC (không phải "gần" chung chung)
5. Đặt TVS/ESD cạnh connector
6. Đặt linh kiện phụ theo signal flow
7. Kiểm courtyard overlap trước khi route

### 3.2 Tiêu chí placement tốt

- Tụ decoupling: khoảng cách tâm–tâm đến chân IC ≤ 3 mm (target ≤ 2 mm)
- Trở gate MOSFET: ≤ 3 mm từ chân gate
- Nguồn → tụ → IC, không đảo ngược
- USB pair có thể ra thẳng từ connector mà không cần vòng
- P2 trunk có đường đi thẳng mà không bị P1 chắn

### 3.3 Dấu hiệu placement cần đặt lại

- Route P1 xong mà drc_body_keepout.py báo lỗi (K1)
- USB pair phải vòng > 1.5× đường thẳng
- Tụ decoupling phải thêm via để nối với chân IC
- Trunk nguồn phải đi qua nhiều via
- P3 cần > 1 via B.Cu hop mỗi net

---

## Phần 4 — Các tình huống đặc biệt đã kiểm chứng

### 4.1 USB-C VBUS hai chân (Type-C 16-pin)

Hai chân VBUS (A4/B9 và A9/B4) nằm hai bên cặp D+/D−.  
**Nối hai chân VBUS mà không cắt USB pair** → chỉ có 2 cách:
- F.Cu dưới vỏ connector → vi phạm K1 (cấm)
- B.Cu U-shape vòng sau đầu pad → chấp nhận được, ghi FAIL có chủ ý vào REVIEW.md

Chọn B.Cu. Checker tự động báo FAIL (REF-SLOT) nhưng đây là FAIL có giải thích.

### 4.2 Cầu D+/D− USB-C (Type-C 16-pin xen kẽ)

Connector 16-pin có D+/D− ở hai vị trí (A6/B6 và A7/B7).  
Nối A6↔B6 buộc phải vòng qua đầu pad → khai báo EXEMPT trong checker.  
Ghi vào REVIEW.md: "ngoại lệ topology, không phải lựa chọn routing".

### 4.3 Trace trong kênh giữa hàng chân SOIC/TSSOP

Không bị K1 cấm vì trace không nằm dưới thân IC (thân IC không che kênh giữa hai hàng).  
Nhưng phải ghi rõ trong REVIEW.md và hỏi owner nếu chưa rõ chính sách dự án.

### 4.4 PWM/signal dài do topology

Nếu PWM_G phải đi 32 mm vì chân MCU ở góc trên-phải còn tải ở góc trên-trái:  
→ Chấp nhận được nếu là P3 và không vi phạm K1  
→ Ghi vào REVIEW.md với lý do (topology, không phải lười routing)  
→ Chỉ cần lo nếu có yêu cầu switching speed cụ thể (hỏi owner)

---

## Phần 5 — Quy trình kiểm tra tại mỗi cổng

### Gate sau P1 (trước khi bắt đầu P2)

```bash
python tools/drc_body_keepout.py board.kicad_pcb --exempt <list>
```
→ Phải 0 vi phạm (trừ EXEMPT đã khai báo).  
→ Nếu có: ghi số vòng và lý do, adjust_placement(), route_P1() lại.

### Gate sau P3 (trước khi giao)

```bash
python tools/layout_audit.py board.kicad_pcb layout_intent.json
python tools/drc_body_keepout.py board.kicad_pcb --exempt <list>
```
→ layout_audit: target là 21+ PASS, 0 FAIL (trừ FAIL có giải thích)  
→ drc_body_keepout: 0 vi phạm

### Gate KiCad native (bắt buộc, không thể bỏ qua)

Mở KiCad 10.0.4 → nhấn **B** (refill zone) → **DRC** → **ERC** → lưu JSON vào thư mục candidate.  
Chỉ sau bước này mới được viết trạng thái khác "CANDIDATE" trong REVIEW.md.

---

## Phần 6 — Những gì phải hỏi owner, những gì không

### Phải hỏi (genuine electrical constraint — không thể suy luận)

- Dòng tải thực tế (ảnh hưởng width P2)
- MPN và cực tính TVS/diode bảo vệ
- Mapping chân firmware (nếu có pin reassignment)
- Yêu cầu switching speed của PWM (nếu cần trace ngắn P3)

### Không hỏi (ordinary candidate decision)

- Có được đặt lại component không? → Có, đó là công việc của agent
- Via ở đây có ổn không? → Tính toán, quyết định, ghi lý do vào REVIEW.md
- Có được route lại toàn bộ không? → Có, trong candidate dir, không đụng baseline
- Trace dài X mm có chấp nhận được không? → Tính sụt áp, so với threshold, tự quyết

---

## Phần 7 — Cấu trúc REVIEW.md bắt buộc

Mỗi candidate phải có REVIEW.md với đủ các mục sau:

```markdown
## SHA
| board.kicad_pcb | <sha256> |
| baseline (V6)   | <sha256> |

## Vòng lặp placement
- Vòng 1: [lý do loại]
- Vòng 2: [lý do loại]
- Vòng N: PASS

## Kết quả kiểm hình học
clearance: X | under-body: X | courtyard: X | open nets: X

## FAIL có chủ ý
- [ref/net]: [lý do bắt buộc, không phải lựa chọn]

## Metrics
| USB D+   | X mm | X via |
| USB D−   | X mm | X via |
| Skew     | X mm |
| Trunk +5V| X mm | X via | X mV sụt áp |
| Decap CX | X mm |

## Quyết định đang chờ owner
- [câu hỏi cụ thể]

## Trạng thái
CANDIDATE — chưa có KiCad native DRC/ERC
(hoặc: PASS — DRC/ERC sạch, file JSON: drc.json, erc.json)
```

---

## Phần 8 — Giá trị khởi điểm (khi project/vendor không nói gì)

| Thông số | Target | Phải xem xét lại nếu |
|---|---|---|
| Track tín hiệu | 0.2 mm | — |
| Track nguồn ≤ 0.5 A | 0.3 mm | > 0.4 mm tốt hơn |
| Track nguồn ≤ 1 A | 0.5 mm | — |
| Track trunk ≥ 2 A | 1.0 mm | Tính sụt áp |
| Clearance | 0.15 mm | Theo fab |
| Via signal | drill 0.3, dia 0.6 | — |
| Via nguồn | drill 0.4, dia 0.8 | ≥ 2 via/chỗ đổi lớp |
| Copper-to-edge | 0.3 mm | — |
| Decap distance | ≤ 2 mm tâm–tâm | > 3 mm cần giải thích |
| Gate resistor distance | ≤ 3 mm | — |
| Sụt áp trunk | ≤ 2% rail | > 5% phải sửa |
| USB skew D+/D− | ≤ 1 mm | — |

Nguồn đầy đủ: `rules/layout_defaults.json`.

---

## Phần 9 — File cần đọc theo thứ tự (nếu cần chi tiết hơn)

1. `GOVERNANCE.md` — ai quyết định gì, luật nào cần duyệt trước khi áp dụng
2. `LAYOUT_RULES.md` — toàn bộ rules A/P/R/G với level HARD/CONDITIONAL/HEURISTIC
3. `AGENT_LAYOUT_PLAYBOOK.md` — workflow đầy đủ 6 pha với gate cụ thể
4. `rules/layout_defaults.json` — giá trị khởi điểm có nguồn gốc
5. `LESSONS_LEARNED.md` — 8 bài học thực tế từ STM8 V8 session
6. `tools/drc_body_keepout.py` — checker K1 (portable, standalone)
7. `tools/layout_audit.py` — checker đa tiêu chí (cần layout_intent.json)
8. `REVIEW_CHECKLIST.md` — checklist trước khi giao candidate

**File này (`CODEX_ROUTING_GUIDE.md`) là điểm vào tổng hợp.  
Đọc file này đủ để hiểu tư duy và thứ tự hành động.  
Đọc các file gốc khi cần chi tiết hoặc giải quyết trường hợp đặc biệt.**
