# Bài học thực tế — STM8 RGB USB-C V8 (2026-11-17)

**Nguồn:** session Training `D:\Data\hai\app\Kicad\Auto\Training` — Claude Sonnet 4.6  
**Board:** 30×30 mm, 2-layer, STM8S103F3P6 + CH340C, USB-C Type-C connector 16-pin  
**Trạng thái:** candidate V8, kiểm hình học độc lập PASS, chưa native KiCad DRC

---

## L1 — Lỗi nghiêm trọng: patch thay vì làm lại

**V7** chỉ patch V6 (Codex): đếm được 49 vi phạm under-body, so với 52 của V6. Kết quả
gần như không đổi vì layout gốc đã vi phạm luật cơ bản từ placement.

**Bài học:** khi vi phạm xuất phát từ placement sai thì patch routing không giải quyết được.
Phải làm lại từ đầu với luật cứng được thực thi từ bước placement.

---

## L2 — Luật cứng được xác nhận là cần thiết (đã kiểm chứng)

Những luật sau đây đã được đưa vào checker hình học và kiểm thực tế trên board:

### K1 — Không trace dưới bụng linh kiện thụ động

Cấm trace đi qua bounding-box thân của R, C, L, D dạng SMD (không phải vùng pad).  
Cấm trace giữa hai pad của bất kỳ linh kiện nào (xuyên qua khe linh kiện).  
Cấm trace dưới thân SOT-23 (3-pin, khe giữa 2 hàng pad).  
Cấm trace dưới vỏ kim loại connector (USB shell, RJ45 shell).

**Ngoại lệ duy nhất có cơ sở:** cầu D−/D+ buộc phải đi vòng qua đầu pad J1 USB-C do pin-out
16-chân xen kẽ — đây là bất khả kháng topology, không phải lựa chọn routing. Ghi rõ trong
REVIEW.md và EXEMPT list của checker.

Trace trong *kênh* giữa hai hàng chân SOIC/TSSOP (không dưới thân IC) là vùng xám — cần
quyết định của owner. Session này chọn cho phép với lý do IC body không che phủ kênh đó.

### K2 — Cấm "route in order, done when connected"

Không được route tuần tự từ net 1 đến net N rồi xác nhận hoàn thành khi tất cả node đã nối.  
Tiêu chí hoàn thành là: (a) đúng độ ưu tiên, (b) không vi phạm luật body-keepout, (c) return
path hợp lệ — không phải chỉ "nối được".

### K3 — Thứ tự bắt buộc: Place → P1 → check → đặt lại → P2 → P3

```
place_all()
  → route_P1()          # USB pair, decoupling, connector cluster
  → check_violations()
  → if fail: adjust_placement(), goto route_P1
  → route_P2()          # power trunk, LED load, gate nets
  → route_P3()          # UART, SWIM, NRST, PWM — may hop B.Cu, short
  → final_check()
```

P3 được phép nhảy lớp (1 via ngắn mỗi đường) nhưng **không được đi dưới** P1/P2 load path.

---

## L3 — Vòng lặp placement: 4 vòng là bình thường

V8 cần 4 vòng placement:
- Vòng 1: 11 courtyard chồng nhau → loại
- Vòng 2: router tự động tạo 9 mm trace diagonal dưới U1 → loại (vi phạm K1)
- Vòng 3: via NRST quá gần MCU supply branch (clearance lỗi) → loại
- Vòng 4: PASS tất cả gate

**Bài học:** đừng expect placement đầu tiên là đúng. Gate kiểm tra giữa các pha là để
phát hiện sớm, không phải để confirm. Số vòng lặp cần ghi vào REVIEW.md.

---

## L4 — Phân cấp ưu tiên routing (đã kiểm chứng trên board thật)

| Mức | Nội dung | Yêu cầu đặc biệt |
|---|---|---|
| P1 | USB differential pair, decoupling cap (mỗi chân nguồn IC), CC pull-down, GND shield | 0 via, song song, không dưới bất kỳ component nào |
| P1 | VBUS cluster, TVS, bulk cap | Nối trước khi route bất kỳ P2 nào |
| P2 | Trunk nguồn → connector tải | 0,8 mm min, 0 via preferred |
| P2 | Nhánh nguồn MCU + bridge | Vào tụ trước, rồi mới tới chân IC |
| P2 | LED load path, MOSFET gate | 0,3–0,4 mm, trở gate ≤ 3 mm từ chân gate |
| P3 | SWIM, UART, NRST, PWM | 1 via B.Cu ngắn (< 4 mm) là chấp nhận được |

---

## L5 — Checker hình học: giá trị và giới hạn

`tools/drc_body_keepout.py` trong repo này (xem mô tả) phát hiện:
- Trace đi qua bounding-box thân component (không phải pad bbox)
- Courtyard overlap
- Clearance vi phạm (theo netclass)
- Open net (union-find)

**Giới hạn đã biết:**
- Không thay thế được KiCad native DRC/ERC
- Không kiểm zone fill quality
- Không kiểm silkscreen
- Không kiểm impedance hoặc độ dài differential pair
- SOT-23 keepout dùng fab layer rect thay vì courtyard polygon (courtyard không tồn tại trên
  một số footprint cũ)

Calibration: cùng bộ kiểm → V6 = 52 hits, V7 = 49, V8 = 0 (trừ 3 đoạn J1/DM exempt).

---

## L6 — VBUS USB-C trên 2-layer: bài toán topology

Hai chân VBUS (A4/B9 và A9/B4) nằm hai bên cặp D+/D− trên connector 16-pin.
Nối hai chân VBUS mà không cắt ngang USB pair → chỉ có hai cách:
1. F.Cu dưới vỏ connector (vi phạm K1 — cấm dưới shell)
2. B.Cu U-shape vòng sau đầu pad (16,4 mm, chấp nhận được vì không có trace nào đi ngang)

Chọn phương án 2. Audit tự động báo FAIL (REF-SLOT) nhưng đây là FAIL có chủ ý, ghi rõ
trong REVIEW.md.

**Bài học:** một số FAIL của checker là bất khả kháng do topology. Mọi FAIL đều phải có
ghi chú giải thích trong REVIEW — không được im lặng.

---

## L7 — Những gì phải hỏi owner, những gì không

**Phải hỏi (genuine electrical constraint):**
- Dòng LED thực tế ≤ X mA? (ảnh hưởng width trace P2)
- MPN và cực tính TVS/diode? (ảnh hưởng netlist kiểm)
- Mapping chân firmware MCU? (ảnh hưởng net assignment)

**Không hỏi (ordinary candidate change):**
- Có được đặt lại component không? (yes, đó là công việc của agent)
- Có được route lại không? (yes, trong candidate dir)
- Via ở đây có ổn không? (tính toán rồi quyết định, ghi lý do vào REVIEW)

---

## L8 — Cấu trúc thư mục candidate

```
reviews/candidates/<vN>_<agent>/
  stm8_rgb_usb_c_v2.kicad_pcb   ← file PCB (SHA trong REVIEW.md)
  REVIEW.md                      ← bắt buộc: SHA trước/sau, metrics, số vòng lặp, FAIL có chủ ý
  layout_audit.json              ← output của tools/layout_audit.py
  independent_check.txt          ← output của tools/drc_body_keepout.py
  v{N}_render.png                ← ảnh board
  tools/build_v{N}.py            ← script tái sinh (chạy lại ra PCB mới)
  tools/kit.py / out8.py / ...   ← tools đi kèm
```

Không bao giờ ghi đè original baseline hoặc manually-edited PCB.  
Không claim PASS cho đến khi native KiCad DRC/ERC chạy và lưu JSON kết quả vào thư mục này.
