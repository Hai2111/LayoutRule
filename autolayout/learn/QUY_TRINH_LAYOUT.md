# Quy trình layout chung (rút từ 75 bài học, 2026-11-27)

Áp dụng cho mọi board, không gắn với một dự án. Nguồn gốc: `lessons.jsonl` (L01–L75), lời owner, dấu vết
và lời khuyên của Vector, `rule/LAYOUT_RULES.md`.

Ký hiệu trạng thái: **[có]** đã có công cụ tự động · **[tay]** tác tử làm tay bằng `agent_edit.py` ·
**[chưa]** mới là bài học, chưa có công cụ.

## Nguyên tắc xuyên suốt

1. **Thứ tự ưu tiên khi xung đột** (L45): điện (vòng dòng nhỏ, đường hồi liền) → làm được ở luật chuẩn của fab →
   vừa vỏ/connector → nhỏ/rẻ. Cấp trên luôn thắng.
2. **Nghĩ theo vòng dòng, không theo sợi dây.** Mỗi net quan trọng: dòng đi đâu, hồi về đâu, làm vòng nhỏ nhất
   (rule P04, R05, R06).
3. **Placement quyết định phần lớn kết quả.** Linh kiện được dời, xoay, hoán vị; chỉ neo cơ khí là cố định (L02, L10, L19).
4. **Nhìn toàn khối, không sửa từng điểm** (L29). Sửa một linh kiện thì đánh giá lại cả khối và cả board.
5. **Ref trước, sửa sau** (L09, L30). Lệch ref phải có lý do ghi lại.
6. **Dữ liệu trước, ảnh để kiểm** (L06, L46, L49). Quan hệ vị trí (giữa, trước/sau, bên nào) tính từ tọa độ;
   số dùng để xếp hạng phương án; ảnh bắt cái số bỏ sót. Ảnh nhỏ mâu thuẫn với tọa độ thì tin tọa độ.
7. **Sửa tăng dần, kiểm sau mỗi bước, xấu hơn thì hoàn tác** (L17).
8. **Agent tự quyết đánh đổi kỹ thuật; biết chưa tối ưu thì sửa xong mới báo** (L28, L32). Chỉ hỏi owner khi
   chạm neo cơ khí, giao tiếp ngoài, khả năng fab, việc không đảo ngược.
9. **Quy trình phải chịu được bị ngắt** (L76). Chuỗi bước chạy qua `kpipe.py STEPS.json` (lock PID, dấu .done theo
   hash input, log trong `.kpipe/`); tool ghi file qua `ksave` (nguyên tử, không sinh .kicad_pro/.kicad_prl rác).
   Bị ngắt thì: tìm tiến trình mồ côi → kiểm toàn vẹn output → chạy lại `kpipe` (tự bỏ bước đã xong, làm lại bước dở).

## Các tầng và cổng kiểm

Mỗi cổng là tự kiểm của agent. Owner chỉ duyệt một lần cuối: ĐẠT / KHÔNG ĐẠT (L07).

### Tầng 0 — Đầu vào
- Đọc `intake.txt` (rule/PROJECT_INTAKE.md). Thiếu câu nào thì lấy mặc định và ghi vào `assumptions`, không dừng hỏi. **[có]**
- Chốt fab + IPC class (mặc định Class 2) (L41). **[chưa]**
- Nạp file luật `.kicad_dru` mẫu theo fab + stackup; luật riêng của board phải kèm lý do (L42). **[chưa]**
- Gate LayoutRule step 0 (`session_start.py`) + reference preflight (`session_gate.py`). **[có]**

- Biến mọi con số thành luật (L51): mỗi số có **nguồn** (fab / tính toán / datasheet / chuẩn), **phạm vi**
  (toàn board / nhóm net / vùng / cặp đối tượng) và **loại** (min / max / target). Đặt đúng chỗ:

  | Loại luật | Chỗ đặt | Ví dụ |
  |---|---|---|
  | Min của fab, toàn board | Board Setup → Constraints | clearance 0.2, drill 0.3 |
  | Theo nhóm net | Net Class + pattern tên net | `Power` track ≥ bề rộng tính theo dòng; `USB` |
  | Có điều kiện | Custom Rules (`.kicad_dru`) | J1 hole_clearance 0.19 chỉ trong footprint J1 |
  | Theo vùng | Rule Area (keepout) | dưới anten module RF |
  | KiCad không biểu diễn được | script trong `check` | decap trước chân, thứ tự nguồn, vòng dòng, W1, V1 |

  Cái gì DRC giữ được thì để DRC giữ; script chỉ cho phần còn lại. **[chưa]** (board USB-C mới có net class Default)

**Cổng 0:** có fab, class, số lớp, luật nạp xong.

### Tầng 1 — Schematic
- Rà schematic, chỉ cảnh báo (`sch_check.py`) (L14). **[có]**
- Khai báo ý đồ từng khối thành `intent.json` người đọc được: khối nào, chuỗi nguồn nào, vòng nào nhạy (L16). **[tay]**
- Chuỗi nguồn: nguồn → TVS/ESD → bulk → tải; mỗi IC có tụ decap trước chân; mọi nhánh lấy sau TVS (L03, L15, L25). Connector có 2 chân nguồn: nối 2 chân bằng cầu ngắn, rộng nhất vừa khe; nhánh nào không lấy sau TVS được phải ghi lý do (L56). **[có]** một phần
- Đối chiếu footprint với datasheet hoặc ghi "chưa kiểm" (L44). **[chưa]**

**Cổng 1:** ERC sạch, mọi khối có ý đồ, mọi footprint đã kiểm hoặc được đánh dấu.

### Tầng 2 — Floorplan
- Khoá neo cơ khí: viền board, lỗ bắt vít, connector, nút bấm, pin, anten.
- Chia board thành các khối theo `intent.json`; khối đi theo dòng tín hiệu và dòng nguồn, chạy một chiều qua board.
- Mở ảnh khối của ref cùng khung connector (`ref_block_view.py`) và so vai trò + vị trí tương đối (L30). **[có]**

### Tầng 3 — Placement theo độ nhạy (L35)
Thứ tự: module RF + vùng cấm anten → vòng xung DC/DC → thạch anh → tụ decap → bảo vệ cổng (ESD/TVS) →
chuỗi nguồn theo chiều dòng → IC còn lại → cảm biến → trở kéo, LED lấp chỗ trống.

Xem mẫu khối ở bảng cuối tài liệu. Dùng xoay như một nước đi chính (L10). Mẫu ref chỉ là điểm khởi đầu: mọi linh kiện nhỏ 2 chân chạy `placesmall` để chọn vị trí + hướng tốt nhất (L67). Hai IC nối bằng bus thì dóng thẳng hàng chân (L05).
Có cụm giống hệt nhau thì thử hoán vị (L13, `swap_blocks.py`). **[có]** một phần

**Cổng 3 — kiểm placement, quan trọng nhất** (L43, L46). **[chưa]**
- Tạo 2–3 phương án cho vùng khó; chấm từng phương án bằng: tổng chiều dài ratsnest, số giao cắt ratsnest,
  diện tích vòng xung/decap, mặt GND có liền không.
- Phương án tốt nhất phải qua kiểm bằng ảnh: so ref, tụ trước chân, thạch anh và vòng xung sát chân, không dây nguồn dưới thân IC.
- Không qua thì không được route.

### Tầng 4 — Routing
Thứ tự: GND là zone solid cả hai lớp, không route GND, pad nối thẳng vào đồng, via chỉ để khâu (L59) → trunk nguồn vẽ thẳng trước, TVS/tụ đặt lên trunk (L60) → net ngắn quan trọng (vòng xung, thạch anh, decap xuống via GND) →
USB/vi sai/RF → nguồn → tín hiệu thường (R02).

- **Nguồn:** VBUS trước CC (L04). Bề rộng tính theo dòng (IPC-2221/2152) và giảm dần theo chiều dòng, đoạn ra khỏi pad nguồn rộng nhất (L31, W1). **[có]**
- **Lớp:** thử cùng lớp với nới lỏng cho phép trước khi đổi lớp (L01). Board 2 lớp không có mặt phẳng: một lớp ngang, một lớp dọc (L48). **[có]** / **[chưa]**
- **Via:** 0.6/0.3, nhỏ hơn chỉ ở hàng pad connector (L11). Không via trong hoặc sát pad SMD: < 0.2 mm là sai, mục tiêu ≥ 0.25 mm và còn dải solder mask (L34, L52, V1, nguồn Eurocircuits). Mọi via tự đặt cách mép board ≥ 0.5 mm (L53). Xoá via GND thì kiểm lại đảo đồng (L55). Đổi lớp cuối dây thì vào thẳng pad xuyên lỗ (L27). **[có]**
- **Thân linh kiện:** được đi dưới header/JST, giữ cách via (L08). Không đi nguồn dưới thân IC. **[có]**
- **USB FS:** không chỉnh độ dài (L12). **[có]**
- **Trở kháng / stackup (L77):** đọc stackup thật (số lớp, điện môi, er, đồng) từ board trước khi đặt khối có cặp vi sai.
  Con số bề rộng/khe lấy từ nguồn có sẵn: design guide hãng IC + calculator của fab (vd JLCPCB "coplanar
  differential pair"), tự giải (`diffz.py`) chỉ để kiểm chéo. Board 2 lớp 1.6 mm không làm microstrip 100 Ω nổi
  (cần dây ~1 mm) → dùng coplanar có GND cùng lớp + GND đặc lớp dưới. Số đã tra (L78, JLCPCB JLC0216A 2 lớp
  1.6 mm 1oz, 100 Ω coplanar vi sai): rộng 0.22 mm / khe cặp 0.152 mm / khe tới GND pour 0.203 mm. Đọc calculator
  web: bấm, chờ, đọc 2 lần, chỉ nhận khi trùng (kết quả có thể trễ 1 lần bấm).
- **Ethernet MDI (WIZnet HW Design Guide, L77):** 100 Ω vi sai; dây 6–12 mil, khe trong cặp ≤ 10 mil, TX–RX ≥ 20 mil,
  cách dây khác ≥ 20 mil có GND chen; dài < 25 mm, cùng độ dài, 45°/cong, **không via/đổi lớp**; điện trở 49.9 Ω + tụ
  trung điểm sát MagJack; không plane nguồn/GND dưới MagJack; không dây số giữa PHY và RJ45 (LED đi vòng ngoài);
  tinh thể sát chip. Kiểm thứ tự P/N hai đầu cặp khi đặt; đảo thì vòng dây N quanh chân P của connector THT.
- **Điểm dừng** (L47): một net cần > 2 via hoặc vòng xa thì dừng, quay lại tầng 3 dời/xoay linh kiện, không ép đường. **[tay]**
- Chỉ đi lại các net bị ảnh hưởng, giữ phần tốt (L17). **[tay]**

- **Theo cách owner sửa (L69–L74):** cặp vi sai đi thành cặp song song đối xứng; nhóm dây cùng chức năng đi thành bus đều; nhánh nguồn vòng ra mép để nhường chỗ chân IC; biên mép theo luật dự án; cầu VBUS có thể là zone. **[chưa]** (mới là bài học)

### Tầng 5 — Chất lượng GND
- Đổ đồng GND mặt trên, via khâu không sát pad SMD (L18, `pour`). **[tay]**
- Xem riêng lớp GND: không có đảo, không bị dây xẻ dưới vùng nhạy (L40, R06). **[chưa]**

### Tầng 6 — Kiểm tra
`agent_edit.py check`:
- DRC 0 lỗi, 0 cảnh báo, 0 net hở. **[có]**
- Tự kiểm quan hệ R1–R3. **[có]**
- V1: không via sát pad. **[có]**
- A45: mọi đoạn nhìn thấy được phải 0/45/90 độ; `track` từ chối đoạn lệch, `oct45` nắn lại (L61). **[có]**
- C90: không góc gấp > 45° giữa hai đoạn liền nhau (kể cả góc ẩn sau đoạn vát ngắn); `chamfer` vát lại (L68). **[có]**
- R4: không track nào chạy dọc hàng chân linh kiện khác (≥ 1.5 mm, ≥ 4 chân trong 0.45 mm); router phạt vùng sát chân (L57). **[có]**
- Nhìn ảnh theo câu hỏi cụ thể, không theo cảm giác: trunk có thẳng không, tải có lấy bằng nhánh ngắn không, mỗi via vượt có lý do bắt buộc không (L57).
- W1: bề rộng nguồn không nở dọc đường, so theo từng nhánh của từng pad nguồn (L31, L54). **[có]**
- So netlist board với schematic: khác biệt chỉ được là các mục trong `SCHEMATIC_CHANGES.md`, và schematic phải được sửa theo trước khi release (L50). **[chưa]**

Sau đó chạy `tools/route_audit.py` trên board ta cùng các ref: chỉ số nào nằm ngoài khoảng của ref là lỗi cần sửa, kể cả khi mọi kiểm tra khác đạt (L58). Chạy `tidy` để bỏ khúc gấp nhỏ. Mọi câu "bắt buộc phải như vậy" cần một thí nghiệm chứng minh. Sau đó đối chiếu ref lần cuối bằng ảnh. Thứ tự giữ/hoàn tác một thay đổi: DRC → lỗi quan hệ → nguồn không bị đẩy xuống B.Cu → via/chiều dài.

**Tự soát độc lập sau mỗi lượt sửa (L62):** xem ảnh close-up từng vùng như một người review khác, không chỉ chỗ vừa được phê: decap sát chân chưa, đường nào khép quanh chân khác, via nào bỏ được, chỉ số route_audit còn trong khoảng ref không. Ý tưởng sửa lớn phải qua kiểm khả thi hình học trước (L63).

**Review bằng ngân hàng câu hỏi (L64):** chạy `tools/review_run.py WORKDIR`; trả lời mọi câu ảnh vào `review_answers.json` kèm bằng chứng; NEEDS_REVIEW phải có lý do. Câu hỏi mới phát hiện được thì thêm vào `learn/review_questions.json`. Chỉ khi mọi câu place/route đạt thì mới sang tầng 7 (silkscreen, nhãn).

### Tầng 7 — Hoàn thiện và release
- Silkscreen: nhãn chân header theo thứ tự dây tự nhiên nếu header do ta định nghĩa (L33). **[tay]**
- Mọi sửa schematic ghi vào `SCHEMATIC_CHANGES.md`. **[có]**
- **Chỉ xuất file sản xuất khi layout đã hoàn chỉnh.**
- Báo cáo một lần: 1 ảnh + ≤ 5 dòng (L07). **[có]**

## Mẫu khối

| Khối | Mẫu đặt và đi dây | Nguồn |
|---|---|---|
| USB-C 16P | Trở CC cách hàng pad ≥ 1.5 mm. ESD đặt ngay trên tâm connector, chân VBUS quay về connector, gán chân theo cặp xuyên thông để D± không cắt nhau. Cầu 2 pad VBUS là vòng F.Cu dưới thân connector. Pad GND nối sang chân vỏ. Trunk nguồn vòng ra ngoài trở CC. | L04, L21–L23, L26, L34; ref SR01, ColdChain |
| Tụ decap | Sát chân, nằm giữa nguồn và chân IC; via GND ngay cạnh tụ, không trong pad. | L03, L19, P04 |
| LDO | Tụ vào trước, tụ ra sau; cụm đặt gần tải, không ở mép xa. | L29 |
| Module RF có anten | Mép board, anten hướng ra; cấm đồng và linh kiện trên mọi lớp dưới anten; mặt GND đủ dài theo datasheet. | L36 |
| DC/DC | Cuộn L và tụ sát chân SW; vòng nhỏ nhất; route trước mọi net khác; GND dưới vòng liền. | L37 |
| Thạch anh | Sát chân hoặc đúng khoảng cách trong layout guide của IC; không dây dưới thân. | L38, P05 |
| Cảm biến môi trường | Góc mát, xa LDO, IC sạc, MCU; rãnh phay nếu hãng yêu cầu. | L39 |
| Header/breakout tự định nghĩa | Gán nhãn chân theo thứ tự dây, in nhãn lên silkscreen. | L33 |

## Việc còn thiếu để quy trình chạy trọn

Các mục **[chưa]** theo thứ tự đáng làm:
1. Cổng 3 (L43 + L46): chấm phương án placement bằng ratsnest rồi chặn `route` cho tới khi qua.
2. Ghi các con số trong `layout_defaults.json` vào net class / custom rule của project khi `init` (L51).
3. So netlist board ↔ schematic (L50). Board USB-C hiện lệch schematic ở U1 và J2 (đã ghi, chưa sửa schematic).
4. Điểm dừng ở tầng 4 (L47): router báo net > 2 via để tác tử quay về placement.
5. Kiểm đảo GND (L40).
6. File luật mẫu theo fab và class (L41, L42).
7. Luật khối RF/DC/DC/thạch anh/cảm biến (L36–L39). Số liệu phải kiểm datasheet trước khi viết thành luật.
8. Thư viện footprint đã kiểm (L44).
