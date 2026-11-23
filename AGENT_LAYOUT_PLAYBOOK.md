# AGENT LAYOUT PLAYBOOK — từ schematic tốt đến board hoạt động được

**Trạng thái:** `APPROVED` as foundation (owner Hai, 2026-11-20). Production work follows [ITERATIVE_ROUTING_PLAYBOOK.md](ITERATIVE_ROUTING_PLAYBOOK.md); this file supplies intent and phase gates. Tool-specific limitations remain tracked in `setup/SMOKE_TEST.md`. Xem [GOVERNANCE.md](GOVERNANCE.md).
**Dùng cùng:** [LAYOUT_RULES.md](LAYOUT_RULES.md) (luật A/P/R/G), [PLACEMENT_PATTERNS.md](PLACEMENT_PATTERNS.md) (PTnn), [rules/layout_defaults.json](rules/layout_defaults.json) (giá trị khởi điểm D-…), [tools/layout_audit.py](tools/layout_audit.py) (đo hình học).

> **Cách thực thi theo vùng (PROPOSED 2026-11-20):** thay vì chạy G2→G3/G4/G5 một lượt phẳng, xem [ITERATIVE_ROUTING_PLAYBOOK.md](ITERATIVE_ROUTING_PLAYBOOK.md): chia board thành phân vùng R1 (khối chức năng), chạy vòng lặp *placement → routing (agent quyết định, tool thực thi) → xử lý ảnh → xử lý logic* trong từng vùng, đạt thì ghi checkpoint/snapshot **không khóa vùng**; sau đó kiểm liên vùng R2, R3 và toàn mạch. Ba bất biến: mọi net luôn routable-ready, mọi component luôn relocatable, mọi quyết định routing có giải trình trong ledger.

**Cập nhật quy trình review (đề xuất 2026-11-23):** G1/G3/G5 là checkpoint nội bộ, không gửi owner duyệt; chỉ bản cuối phiên sau báo cáo mới được review. Ngoài neo phải khớp cơ khí không khóa placement/copper/vùng, kể cả sau owner review. Bài demo USB-C không phải project đưa vào repo. Xem [REVIEW_LEARNING_LOOP.md](REVIEW_LEARNING_LOOP.md).

Các tài liệu khác trong repo trả lời câu hỏi "điều gì không được coi là luật". Tài liệu này trả lời câu hỏi còn thiếu: **agent làm gì, theo thứ tự nào, đo cái gì, đạt bao nhiêu thì được đi tiếp, và khi nào phải quay lại.**

## 0. Ba nguyên tắc vận hành

**N1 — Layout là thực thi ý đồ điện, không phải nối cho hết airwire.** Trước khi đặt linh kiện đầu tiên, agent phải viết ra ý đồ đó thành file `layout_intent.json` (Pha 0). Mọi cổng kiểm tra về sau đều đo board so với file này. Không có intent thì không có gì để kiểm ngoài DRC, và DRC = 0 không chứng minh mạch chạy (G07).

**N2 — Thiếu số liệu thì dùng giá trị khởi điểm và ghi lại, không dừng, không bịa.** Thứ tự ưu tiên: ràng buộc dự án > năng lực nhà máy > hướng dẫn của đúng IC > `rules/layout_defaults.json`. Mỗi giá trị D-… đã dùng phải nằm trong `assumptions` của intent. Giá trị khởi điểm có hai mốc: `target` (nhắm tới) và `review` (vượt qua thì phải sửa hoặc viết lý do). Chỉ dừng hỏi người ở các trường hợp trong mục 7.

**N3 — Đi theo pha, mỗi pha có cổng.** Không qua cổng thì không sang pha sau; cổng sau hỏng do pha trước thì quay về pha trước (mục 6). Thứ tự: `G0 intent → G1 floorplan → G2 placement → G3 critical routing → G4 routing xong → G5 kiểm chức năng`.

---

## Pha 0 — Viết layout intent từ schematic

Đầu vào: schematic/netlist đã qua ERC, datasheet các IC chính, outline và ràng buộc cơ khí, năng lực nhà máy (nếu có).

**0.1 Chọn số lớp và vai trò từng lớp.** Quyết định này đi trước mọi thứ (A03).

| Điều kiện | Chọn |
|---|---|
| MCU/logic chậm, USB FS, nguồn ≤ ~3 A, không BGA, không RF tự làm | 2 lớp: `F.Cu` = linh kiện + tín hiệu + nguồn; `B.Cu` = GND liền, chỉ cho jumper ngắn (D-2L) |
| USB HS, RF chip-down, BGA/QFN pitch nhỏ khó fanout, nhiều rail, dòng lớn, ADC nhạy cạnh nguồn switching | 4 lớp: `F.Cu` tín hiệu + linh kiện / `In1` GND liền / `In2` nguồn (và tín hiệu chậm) / `B.Cu` tín hiệu + GND |

Nếu dự án đã chốt số lớp thì giữ, nhưng ghi rủi ro vào report khi điều kiện ở hàng dưới xuất hiện trên board 2 lớp.

**0.2 Phân loại mọi net.** Không net nào được để trống class.

| Class | Nhận biết từ schematic | Thuộc tính phải điền |
|---|---|---|
| `gnd` | GND, AGND, PGND… | có tách miền không (chỉ khi schematic có linh kiện cách ly, G01) |
| `power` | rail nguồn, VBUS, VBAT, đầu ra regulator | `current_a`, `rail_v` |
| `switch_node` | chân SW/LX, nút giữa FET và cuộn cảm | `current_a`, `max_vias: 0` |
| `feedback` | FB, sense, COMP, Kelvin của shunt | nguồn nhiễu phải tránh |
| `crystal` | XI/XO, OSC_IN/OUT | `max_vias: 0`, `max_length_mm` |
| `diff_pair` | USB D+/D−, CAN, RS-485, LVDS | loại giao tiếp, cặp P/N |
| `analog_sensitive` | đầu vào ADC, cảm biến, tham chiếu, trở kháng cao | aggressor phải tránh |
| `fast_digital` | clock, SPI flash, SDIO, tín hiệu cạnh nhanh | nguồn phát (đặt R nối tiếp ở đâu) |
| `signal` | phần còn lại | — |

**Cách lấy `current_a` cho rail nguồn** (theo thứ tự, lấy cái đầu tiên có): (1) yêu cầu dự án; (2) tổng dòng max các tải trên rail theo datasheet, cộng 30%; (3) dòng ra định mức của regulator cấp cho rail; (4) định mức của cầu chì/connector đầu vào. Ghi rõ đã dùng cách nào. Dòng của nhánh con (ví dụ nhánh cấp cho một cảm biến) được tính riêng, không phải nhánh nào cũng mang dòng của cả rail.

**0.3 Lập bảng net class → hình học.** Từ `current_a` tra D-WIDTH ra bề rộng, tra D-VIA ra số via mỗi lần đổi lớp. Ghi vào netclass của KiCad trước khi route để router không dùng bề rộng tín hiệu cho nguồn.

**0.4 Liệt kê vòng dòng nóng của từng bộ nguồn switching** (P03, PT02). Đọc hình layout trong datasheet của đúng IC trước. Viết vòng thành dãy pad theo thứ tự dòng chạy:

| Topology | Vòng nóng (di/dt cao) | Dãy pad ghi vào intent |
|---|---|---|
| Buck | tụ vào ↔ công tắc trên/dưới | `CIN.+ → IC.VIN → IC.GND (hoặc diode.A) → CIN.−` |
| Boost | công tắc ↔ diode/FET đồng bộ ↔ tụ ra | `IC.SW → D.A, D.K → COUT.+, COUT.− → IC.GND` |
| Buck-boost/SEPIC/flyback | theo datasheet | nếu không xác định được: mục 7 |
| LDO | không có vòng nóng | chỉ cần `proximity`: CIN và COUT tới chân IC |

Kèm theo cho mỗi converter: cuộn cảm ↔ chân SW, tụ bootstrap ↔ BOOT/SW, cầu phân áp FB ↔ chân FB (mục `proximity`, D-SMPS).

**0.5 Lập bản đồ decoupling** (P04, PT03). Mỗi chân nguồn (hoặc nhóm chân kề nhau) của mỗi IC được gán đúng một tụ nhỏ nhất, kèm chân GND gần nó nhất: `{"pin": "U1.4", "cap": "C3", "gnd_pin": "U1.5"}`. Tụ bulk gán theo IC hoặc theo rail. Schematic có ít tụ hơn số chân nguồn thì ghi nhận và báo, không tự thêm linh kiện.

**0.6 Chia khối và vẽ dòng tín hiệu** (A05, PT01). Mỗi linh kiện thuộc đúng một khối. Mỗi khối ghi: IC chính, linh kiện đi kèm, khối nó nhận tín hiệu/nguồn từ đâu và đưa đi đâu. Chuỗi cổng vào luôn viết theo thứ tự vật lý: `connector → bảo vệ (TVS/cầu chì) → lọc → IC` (P06, PT05).

**0.7 Liệt kê neo cơ khí** (P01, A04): connector (cạnh nào, hướng cắm), lỗ bắt vít, nút, LED chỉ thị, anten (keepout theo datasheet module), linh kiện người dùng đã khóa (G06).

**0.8 Tra hướng dẫn riêng của IC** cho thạch anh, RF, converter, USB PHY. Số của hãng ghi đè giá trị khởi điểm (ví dụ ESP32-S3: thạch anh cách chân clock ≥ 2,0 mm, PT04).

### Cổng G0
- [ ] Mọi net có class; mọi net `power`/`switch_node` có `current_a` và nguồn gốc con số.
- [ ] Mọi converter có `hot_loops` + `proximity`; mọi chân nguồn IC có mục `decoupling`.
- [ ] Mọi linh kiện thuộc một khối; mọi connector/neo có cạnh hoặc tọa độ.
- [ ] `assumptions` liệt kê mọi D-… đã dùng. `layout_audit.py` chạy được trên board chưa đặt và không báo `INTENT FAIL`.

Mẫu file: [tests/fixtures/demo_intent.json](tests/fixtures/demo_intent.json).

---

## Pha 1 — Floorplan (đặt khối, chưa đặt linh kiện nhỏ)

**1.1 Đặt và cố định chỉ neo bắt buộc theo khớp cơ khí.** Connector quay đúng hướng cắm, đúng cạnh. Không dời neo để rút ngắn dây (PT01).

**1.2 Ước lượng diện tích khối:** tổng courtyard × hệ số D-PLACE (2,0 cho 2 lớp; 1,5 cho 4 lớp). Tổng diện tích khối vượt diện tích board thì báo ngay, đừng cố nén.

**1.3 Xếp khối theo dòng năng lượng và dòng tín hiệu:**
1. Khối cổng nguồn + bảo vệ nằm ngay tại connector nguồn.
2. Converter nằm giữa cổng nguồn và tải của nó; cuộn cảm và nút SW quay ra xa khối analog, thạch anh, anten.
3. IC trung tâm (MCU) nằm gần trọng tâm các khối nó nối tới.
4. Khối giao tiếp nằm giữa MCU và connector của nó, trên đường thẳng nối hai bên.
5. Analog nhạy nằm xa converter và xa đường dòng lớn; đường đi từ cảm biến/connector vào ADC không băng qua khối số ồn.
6. Anten/RF ở mép board theo keepout của hãng (P07, PT10).

**1.4 Chọn hướng xoay IC chính.** Thử cả 4 góc (và mặt còn lại nếu được phép). Với mỗi góc tính: tổng chiều dài airwire có trọng số (crystal/diff/analog/switching ×3, nguồn ×2, còn lại ×1) và số cặp airwire cắt nhau. Chọn góc có số giao cắt nhỏ nhất, hòa thì lấy chiều dài nhỏ hơn. Mục tiêu: mỗi nhóm chân quay mặt về khối mà nó nối tới (P10).

**1.5 Vạch hành lang:** đường nguồn chính từ cổng vào tới từng khối; hành lang cho cặp vi sai; vùng cấm quanh cuộn cảm/SW/thạch anh/anten; kênh fanout cạnh IC pitch nhỏ (D-PLACE, PT17).

### Cổng G1
- [ ] Không khối nào chồng nhau hoặc lấn keepout; **chỉ neo cơ khí** đúng vị trí và được cố định.
- [ ] Đường nguồn chính và mỗi net critical liên khối đi được mà không băng qua khối khác.
- [ ] Converter không kề khối analog/thạch anh/anten; nếu buộc phải kề thì có lý do và có khoảng cách ghi rõ.
- [ ] Đã so ít nhất 2 phương án floorplan khi board có từ 3 khối trở lên; ghi lý do chọn.

---

## Pha 2 — Đặt linh kiện trong từng khối

Luôn đặt theo thứ tự dưới đây, vì linh kiện ở trên bị ràng buộc chặt hơn linh kiện ở dưới. Đo mọi khoảng cách từ **pad tới pad**, không từ tâm linh kiện (PT03).

**2.1 Converter (P03, PT02, D-SMPS).** Công thức cho buck, áp dụng tương tự theo vòng nóng đã ghi ở 0.4:
1. Đặt IC. Xoay sao cho chân VIN và GND công suất quay về phía tụ vào, chân SW quay ra phía cuộn cảm.
2. Đặt **tụ vào trước mọi thứ khác**: cùng mặt với IC, pad + sát VIN, pad − sát GND công suất. Không via, không linh kiện nào nằm trong vòng.
3. Đặt cuộn cảm sát chân SW. Vùng đồng SW chỉ lớn vừa đủ dòng.
4. Đặt tụ ra sao cho GND của nó về cùng vùng GND với tụ vào, đầu + trên đường ra tải.
5. Tụ bootstrap sát hai chân BOOT–SW. Diode ngoài (nếu có) sát SW và GND tụ vào.
6. Cầu phân áp FB sát chân FB, ở phía xa cuộn cảm. Điểm lấy mẫu là ở tụ ra, không ở chân cuộn cảm.

**2.2 Tụ decoupling (P04, PT03, D-DECAP).** Mỗi tụ đặt cùng mặt với IC, pad nguồn của tụ quay về chân nguồn nó phục vụ, pad GND có chỗ đặt via GND ngay cạnh (board 4 lớp) hoặc nối thẳng về chân GND của IC (board 2 lớp). Tụ nhỏ nhất gần chân nhất, tụ lớn hơn xếp ra ngoài. Không gom tất cả tụ về một góc IC. Chừa kênh fanout cho các chân tín hiệu trước khi chốt vị trí tụ.

**2.3 Thạch anh (P05, PT04, D-XTAL).** Theo hướng dẫn của hãng trước. Mặc định: thạch anh cùng mặt với MCU, phía các chân OSC, hai trace ngắn và gần bằng nhau, tụ tải sát thạch anh, GND tụ tải về GND của MCU. Không đặt cạnh cuộn cảm, connector, đường nguồn switching.

**2.4 Bảo vệ cổng (P06, PT05, D-ESD).** TVS/ESD đặt sát chân connector, nằm **trên đường đi** từ connector vào mạch, GND của TVS có đường ngắn về GND/chassis. Cầu chì, hạt ferrite, lọc theo đúng thứ tự schematic.

**2.5 Linh kiện có vị trí theo vai trò:**

| Linh kiện | Đặt ở đâu |
|---|---|
| R nối tiếp trên đường tín hiệu nhanh | sát chân phát |
| R gate MOSFET | sát chân gate (RE05) |
| R kéo lên/kéo xuống, R cấu hình | sát chân IC cần nó; kéo lên bus (I2C) đặt ở đâu trên bus cũng được |
| Shunt đo dòng | trên đường dòng chính; hai dây sense lấy từ mép trong của pad, đi thành cặp |
| Tụ lọc/tham chiếu ADC | sát chân ADC/VREF, GND về GND analog của IC |
| R/C của mạch reset, boot, enable | sát chân IC |
| LED, nút, testpoint | sau cùng, không chặn kênh route |

**2.6 Hình học chung (P11, D-PLACE):** lưới 0,5 mm (0,1 mm cho tinh chỉnh), góc xoay bội của 90°, linh kiện thụ động cùng nhóm xếp thẳng hàng cùng hướng, khe pad–pad ≥ 0,5 mm, mọi SMD ở một mặt trừ khi có lý do, cách mép board theo D-FAB.

**2.7 Vòng lặp route thử (PT17).** Trên bản sao board, route thử: vòng nóng, tụ decoupling, thạch anh, cặp vi sai, fanout IC pitch nhỏ. Net nào không đi được, phải vòng (> 1,5 lần khoảng cách Manhattan) hoặc cần thêm via thì dịch/xoay nhóm linh kiện gây cản rồi thử lại. Tối đa 5 vòng cho mỗi khối (D-LOOP); hết vòng mà chưa đạt thì quay lại Pha 1.

### Cổng G2
- [ ] `layout_audit.py`: `DECAP`, `DECAP-GND`, `HOT-LOOP-*`, `PROXIMITY` không còn `FAIL`; mỗi `NEEDS_REVIEW` có lý do viết ra.
- [ ] Courtyard và keepout sạch trong DRC của KiCad.
- [ ] Route thử 100% net critical thành công, không via trên net `max_vias: 0`.
- [ ] Số giao cắt airwire không tăng so với floorplan; không neo cơ khí nào bị dời (G06); linh kiện khác được phép điều chỉnh có kiểm chứng.
- [ ] Ảnh chụp/tọa độ placement được lưu để so sánh khi phải quay lại.

---

## Pha 3 — Routing theo thứ tự rủi ro

Thứ tự dưới đây là mặc định; đổi thứ tự hai bước kề nhau được phép khi có xung đột chỗ, nhưng phải ghi lý do (R02, R03). **Không route theo thứ tự net ID. Không chạy autorouter toàn board.**

### Luật cứng bắt buộc trước khi route bất kỳ trace nào (K1–K3)

Những luật này được rút ra từ kiểm chứng thực tế (xem `LESSONS_LEARNED.md`). Vi phạm bất kỳ luật nào → loại candidate, quay lại Pha 2.

**K1 — Cấm trace dưới bụng linh kiện thụ động và dưới vỏ connector.**
- Không có trace nào (kể cả lớp `F.Cu` và `B.Cu`) đi qua bounding-box thân của R, C, L, D dạng SMD.
- Không trace đi giữa hai pad của bất kỳ linh kiện nào (xuyên qua khe linh kiện).
- Không trace dưới thân SOT-23 (vùng giữa hai hàng pad).
- Không trace dưới vỏ kim loại connector (USB shell, RJ45 shell, v.v.).
- Trace trong *kênh* giữa hai hàng chân SOIC/TSSOP (không dưới thân IC) là vùng xám — cần chủ ý nhưng không cấm hoàn toàn; phải ghi rõ trong REVIEW nếu dùng.
- Ngoại lệ có cơ sở: nếu topology bắt buộc (ví dụ cầu nối D+/D− USB-C do pin-out xen kẽ) thì phải ghi vào EXEMPT list của checker và giải thích trong REVIEW.md.
- **Kiểm tra:** `python tools/drc_body_keepout.py board.kicad_pcb` — phải trả về 0 violation (trừ EXEMPT đã khai báo).

**K2 — Cấm "route in order, done when connected".**
- Không được route tuần tự từ net 1 đến net N rồi xác nhận hoàn thành khi tất cả node đã nối.
- Tiêu chí hoàn thành là: (a) đúng thứ tự ưu tiên K3, (b) không vi phạm K1, (c) return path hợp lệ — không phải chỉ "nối được".

**K3 — Thứ tự bắt buộc: Placement → P1 → check → đặt lại nếu thất bại → P2 → P3.**
```
place_all()
  → route_P1()      # USB/cặp vi sai, decoupling, connector cluster, vòng nóng
  → check_K1()      # drc_body_keepout.py — phải 0 violation
  → if fail: adjust_placement(), goto route_P1   # loại candidate, không patch
  → route_P2()      # trunk nguồn, tải LED/motor, gate MOSFET
  → route_P3()      # UART, debug, control — được 1 via ngắn mỗi đường, không đi dưới P1/P2
  → final_check()
```
Mỗi vòng lặp placement phải được ghi số thứ tự và lý do loại vào REVIEW.md.

**3.1 Dựng GND trước.** Vẽ outline zone GND trên lớp tham chiếu (và các lớp khác nếu có) ngay từ đầu để mọi quyết định sau nhìn thấy nó. Board 2 lớp: mỗi pad GND trên `F.Cu` có via xuống `B.Cu` ngay cạnh pad, hoặc nối vào vùng GND `F.Cu` có via gần đó (R06, PT06).

**3.2 Vòng nóng của converter.** Dùng polygon/track rộng, một lớp, không via. Nối CIN–IC trước, rồi SW–L, rồi L–COUT, rồi GND chung. Sau đó ghi snapshot các net này; không khóa trace, được re-route nếu cần tối ưu toàn board.

**3.3 Decoupling.** Nối chân nguồn ↔ tụ bằng track ngắn và rộng nhất mà pad cho phép. Board 2 lớp: nguồn đi **qua pad tụ rồi mới tới chân IC**. Via GND/nguồn của tụ đặt sát pad tụ, không dùng chung một via cho nhiều tụ.

**3.4 Net nhạy và net có ràng buộc** (R02), theo thứ tự: thạch anh (0 via, không net nào chạy bên dưới) → cặp vi sai (đi cặp, đối xứng, số via hai dây bằng nhau, D-DIFF) → analog nhạy và FB (tránh SW/cuộn cảm/clock, R10) → clock và bus nhanh. Net đổi lớp tham chiếu trên board ≥ 4 lớp thì có via GND kèm (D-RETURN, G03).

**3.5 Phân phối nguồn** (R04). Bề rộng theo D-WIDTH cho đúng dòng của **từng nhánh**. Topology: thân chính rộng rồi rẽ nhánh, hoặc hình sao từ tụ ra của regulator; không nối chuỗi tải nặng qua pad của tải nhẹ. Không thắt cổ (R12). Kiểm sụt áp theo D-VDROP cho nhánh dài nhất.

**3.6 Mỗi lần đường tải dòng đổi lớp** (D-VIA; đề xuất mới, nguồn ở mục 9):
- Số via: `n = max(2, ceil(I / dòng_mỗi_via))`; mặc định 0,8 A cho via lỗ 0,3 mm, 1,0 A cho lỗ 0,4 mm.
- Dàn via **ngang bề rộng** đường đồng, tối đa 2–3 hàng so le. Không xếp một hàng dọc theo chiều dòng: via đầu và cuối sẽ gánh phần lớn.
- Đổi lớp ở đoạn thẳng, không ở góc cua: ở góc chỉ các via phía góc trong dẫn dòng.
- Đặt sát chân linh kiện nơi dòng vào/ra; đồng từ pad tới cụm via không hẹp hơn track; nối đặc, không thermal relief (G04).
- Không để cụm via khoét thành khe trên plane GND; chừa đồng giữa các antipad.
- Đường GND hồi về của tải đó cũng phải có số via tương đương.

**3.7 Tín hiệu thường.** Lúc này mới được dùng autorouter (Freerouting, xem [ROUTING_ENGINE_INTEGRATION.md](ROUTING_ENGINE_INTEGRATION.md)), với điều kiện các net ở 3.2–3.6 đã đạt checkpoint nội bộ và netclass có bề rộng đúng; không tự khóa net. Sau khi import: xóa mọi đoạn autorouter đặt lên lớp tham chiếu dài quá mốc D-2L, route lại tay.

**3.8 Luật riêng cho lớp tham chiếu trên board 2 lớp** (R05, R06, D-2L):
- Track trên `B.Cu` chỉ là jumper: ngắn, thẳng, vuông góc với hướng dòng hồi chính nếu được.
- Không jumper bên dưới vòng nóng, thạch anh, cặp vi sai, đầu vào analog, cuộn cảm.
- Hai jumper song song phải cách nhau đủ để GND chảy giữa chúng; không xếp thành hàng rào cắt đôi plane.
- Sau khi fill: GND trên `B.Cu` là **một** vùng liền.

**3.9 Đổ đồng và hoàn thiện** (G02, G03, G05): refill zone; xóa đảo đồng cô lập; thêm via khâu GND ở nơi vùng GND `F.Cu` chỉ nối với plane qua cổ hẹp; kiểm thermal relief (tắt cho pad dòng lớn, giữ cho pad hàn tay); xóa stub, via treo, đoạn thừa; chạy lại DRC.

**Khi một net không đi được** (D-LOOP): thử tối đa 3 đường khác nhau. Vẫn phải vòng > 1,5 lần hoặc thêm > 2 via thì **không cố route**: quay lại Pha 2 dịch nhóm linh kiện liên quan (RE09, PT08). Chỉ gỡ và route lại các net bị ảnh hưởng.

### Cổng G3 (sau bước 3.6) và G4 (sau bước 3.9)
- [ ] G3: `HOT-LOOP-VIA`, `NET-VIAS`, `NET-LENGTH`, `DIFF-*`, `W-POWER`, `VIA-POWER` không còn `FAIL`.
- [ ] G4: DRC KiCad 0 lỗi, 0 net chưa nối, zone đã refill; `REF-ZONE`, `REF-SLOT` không còn `FAIL`.
- [ ] G4: mọi track nguồn đúng netclass; không có thay đổi ngoài ý đồ trên net critical đã qua checkpoint; kiểm lại nếu re-route.

---

## Pha 4 — Kiểm chức năng (G5)

DRC sạch mới là điều kiện vào cổng này. Trả lời từng câu bằng số đo hoặc ảnh, kèm hash file board (G07).

| # | Câu hỏi | Cách đo | Luật |
|---|---|---|---|
| F1 | Mỗi rail có tới tải với sụt áp trong mốc không? | chiều dài × bề rộng nhánh dài nhất, D-VDROP, cộng cả đường GND về | R04 |
| F2 | Mỗi chỗ đổi lớp của net nguồn có đủ via, dàn đúng cách không? | `VIA-POWER` + xem bằng mắt cách dàn | D-VIA |
| F3 | Mỗi vòng nóng: một lớp, không via, không linh kiện lạ bên trong? | `HOT-LOOP-*` | P03 |
| F4 | Mỗi chân nguồn IC có tụ riêng trong mốc, GND tụ về ngắn? | `DECAP`, `DECAP-GND` | P04 |
| F5 | GND có liền không? Dòng hồi của mỗi net critical có đường đi ngay bên dưới không? | `REF-ZONE`, `REF-SLOT`; xem từng net critical so với lớp tham chiếu | R05, R06 |
| F6 | Thạch anh: 0 via, không net lạ bên dưới, đúng hướng dẫn hãng? | `NET-VIAS`, `NET-LENGTH`, xem bằng mắt | P05 |
| F7 | Cặp vi sai: lệch dài trong mốc, via đối xứng, không băng qua khe plane? | `DIFF-*` + F5 | R07 |
| F8 | FB/analog có chạy cạnh hoặc dưới SW, cuộn cảm, clock không? | khoảng cách tới đồng SW, `PROXIMITY` kiểu `min` | R10, P08 |
| F9 | TVS có nằm trên đường đi, trước IC được bảo vệ không? | thứ tự pad trên track từ connector | P06 |
| F10 | Linh kiện tỏa nhiệt có đồng và via nhiệt theo datasheet không? | so với land pattern khuyến nghị | G04 |
| F11 | Keepout anten, khe cách ly, khoảng cách an toàn còn nguyên? | DRC + xem bằng mắt | A04, PT14 |
| F12 | Lắp ráp và đo kiểm: pin-1, cực tính, silkscreen, testpoint cho mỗi rail và tín hiệu debug? | 3D + checklist | G05 |

Kết quả ghi theo [REVIEW_CHECKLIST.md](REVIEW_CHECKLIST.md): `PASS / FAIL / NEEDS_REVIEW / NA` cho từng dòng. `PASS` của `layout_audit.py` là phát biểu về hình học, không phải chứng nhận điện. Agent không được báo "hoàn thành" khi còn `FAIL` ở F1–F9, và phải liệt kê mọi `NEEDS_REVIEW` cùng giả định D-… đã dùng.

---

## 6. Quay lui

| Triệu chứng | Quay về | Việc làm |
|---|---|---|
| Net critical phải vòng, thêm via, hoặc chui qua lớp tham chiếu | Pha 2 | dịch/xoay nhóm linh kiện gây cản, route lại net bị ảnh hưởng |
| Hai khối tranh nhau một hành lang; nguồn chính phải băng qua khối khác | Pha 1 | đổi vị trí khối hoặc xoay IC chính |
| `REF-ZONE` > 1 đảo, hoặc `REF-SLOT` nhiều | Pha 2/3 | gom tín hiệu lên `F.Cu` bằng cách xoay linh kiện; nếu không được, đề xuất lên 4 lớp |
| Vòng nóng không đạt dù đã xoay IC | Pha 0 | kiểm lại pinout/footprint và hình layout của hãng |
| Sụt áp vượt mốc `review` | Pha 3.5 | nới rộng, dùng zone, rút ngắn; nếu hết chỗ thì về Pha 1 |
| Hết ngân sách vòng lặp | dừng | báo cáo phương án tốt nhất, các `FAIL` còn lại và nguyên nhân |

Mỗi lần quay lui: lưu hash trước/sau, danh sách refdes/net bị đổi, số đo trước/sau, và giữ phương án cũ nếu phương án mới tệ hơn (PT17).

## 7. Khi nào kết thúc phiên để báo cáo owner một lần

Chỉ các trường hợp sau; mọi trường hợp khác dùng giá trị khởi điểm và ghi giả định:
1. Không có outline board hoặc vị trí connector/lỗ vít.
2. Có cách ly an toàn, điện áp nguy hiểm, hoặc yêu cầu creepage (PT14).
3. Rail > 5 A mà không có số liệu dòng/đồng/nhiệt của dự án.
4. Anten hoặc đường RF tự thiết kế không có hướng dẫn của hãng.
5. Topology converter không xác định được vòng nóng từ datasheet.
6. Giao tiếp cần trở kháng kiểm soát (USB HS, Ethernet…) trên stackup không đạt được.
7. Phải dịch neo cơ khí đã chốt (G06); thay đổi thủ công khác được so sánh trước/sau, giữ hash và không ngầm ghi đè.
8. Schematic có lỗi cản trở layout (thiếu tụ decoupling, footprint sai, net thiếu).

Không hỏi owner lẻ trong phiên. Nếu thiếu đầu vào nghiêm trọng, agent tự nghiên cứu, ghi lại chặn và kết thúc phiên với một báo cáo BLOCKED. **Chỉ owner review bản cuối sau khi agent đã báo cáo**; feedback được ghi để học ở phiên kế tiếp theo REVIEW_LEARNING_LOOP.md.

## 8. Lỗi agent hay mắc (tra trước khi báo xong)

1. Xếp linh kiện theo lưới đều hoặc theo thứ tự refdes thay vì theo khối và dòng tín hiệu.
2. Tối ưu tổng chiều dài airwire và bỏ qua vòng nóng, đường GND về.
3. Gom tụ decoupling thành một hàng xa IC; một tụ phục vụ nhiều chân ở hai phía IC.
4. Nối GND bằng track mảnh nối chuỗi thay vì zone + via.
5. Dùng bề rộng tín hiệu cho nguồn; thắt cổ ở pad; một via cho đường nguồn đổi lớp.
6. Xếp cụm via nguồn thành một hàng dọc theo dòng, hoặc đặt ngay góc cua.
7. Rải track khắp `B.Cu` của board 2 lớp, cắt GND thành nhiều đảo.
8. Route dưới thạch anh, dưới cuộn cảm; chạy FB sát nút SW.
9. Đặt TVS trên nhánh rẽ thay vì trên đường đi.
10. Để autorouter đi net critical, hoặc chạy lại autorouter toàn board mỗi lần sửa.
11. Cố route quanh một placement sai thay vì sửa placement.
12. Báo `PASS` vì DRC = 0, hoặc vì thiếu dữ liệu để kiểm.

## 9. Nguồn gốc và mức bằng chứng

- Trình tự pha và cổng: tổng hợp từ luật A/P/R/G và PT01–PT17 hiện có; là đề xuất quy trình, chưa chạy trên board thật.
- Số liệu via (3.6): TS14 (TI SLVA959, bảng dòng via và vị trí đặt), TS15 (Brooks & Adam, nhiệt độ via), TS16 (TI TIDA-00774, lặp track trên nhiều lớp và khâu via), TS17 (phân bố dòng trong cụm via). Nhận định "dàn ngang tốt hơn xếp dọc" còn dựa trên một mô hình DC hai lớp tự chạy (đồng 1 oz, trace 4 mm, via 0,3 mm): 7 via dàn ngang chia 14–15% mỗi via; 7 via xếp dọc cho 20% ở hai đầu và 10% ở giữa. Mô hình này chưa được đối chiếu với đo đạc.
- Bề rộng track: công thức IPC-2221 (`CALC`), không phải trích từ toàn văn IPC-2152 (TS11).
- Các mốc khoảng cách ghi `PRACTICE` trong `layout_defaults.json` là kinh nghiệm phổ biến, chưa có nguồn được kiểm trong repo. Chúng là điểm khởi đầu để agent không bị kẹt, cần owner xem và chỉnh.
- `layout_audit.py` có test hồi quy trên board tổng hợp (`python tests/test_layout_audit.py`) và đã đọc được một file KiCad 10 thật (Training `stm8_rgb_usb_c_v2`, định dạng 20260206, PCB SHA256 `f60b1aa4…38ad`): số track, via và chiều dài net khớp với báo cáo độc lập của dự án đó. Một board là chưa đủ để coi công cụ đã được kiểm chứng.
- Giới hạn đã biết của công cụ: via nguồn được gom theo khoảng cách, nên cụm có track nối trên một lớp duy nhất bị trả `NEEDS_REVIEW` (có thể là nối tiếp, không song song); cặp vi sai ngoài USB cần giới hạn ghi trong intent; zone chưa lưu fill thì `REF-ZONE` trả `NEEDS_REVIEW`.
