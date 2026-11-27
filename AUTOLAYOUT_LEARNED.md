# Autolayout: dữ liệu đã học (2026-11-26)

**Trạng thái:** PROPOSED. Tổng hợp các phiên làm việc Claude 2026-11-22 → 26 trên board STM8 RGB USB-C 30×30 mm 2 lớp
và đối chiếu với Vector (heyvector.co). Mã và kho bài học nằm trong [autolayout/](autolayout/).
Owner duyệt trước khi bất kỳ mục nào trở thành rule chính thức.

## 1. Kết luận chính

**Khác biệt nằm ở cách ra quyết định, không ở thông số.** Router chạy mù (luật cứng + A*) không biết dời linh kiện
và không biết dây nào đang chắn dây nào. Một tác tử **nhìn ảnh board → sửa đúng một chỗ → DRC → giữ hoặc hoàn tác**
làm tốt hơn hẳn trên cùng placement đầu vào:

| STM8, cùng placement | Via tín hiệu | DRC | Lỗi vị trí tương đối |
|---|---|---|---|
| autolayout.py (bản nháp tự động) | 13 | 0 lỗi | UART_RX kẹp giữa C2/C4 |
| Gỡ dây đi lại tự động, ~1 giờ (`tools/improve.py`) | 12 | 0 lỗi | +5V bị đẩy xuống B.Cu (2 via) |
| **Tác tử quan sát, ~30 bước** (`tools/agent_edit.py`) | **9** | **0 lỗi, 0 hở** | **không** |
| Vector | 7 | 0 lỗi | USB_DM kẹp C6/R2; +5V dưới mép thân U1 |

Ảnh: [autolayout/learn/stm8_agent_vs_vector.png](autolayout/learn/stm8_agent_vs_vector.png).
2 via chênh với Vector đều ở PWM_R; Vector bỏ được nhờ đoạn +5V dưới mép thân U1, việc mà owner từng đánh giá là lỗi.
**Chờ owner quyết:** có cho phép đoạn nguồn ngắn dưới mép thân IC hay không.

## 2. Quy trình đề xuất (ghép với SESSION_PIPELINE.md trên main)

Tác tử quan sát chạy **bên trong** các cổng đã có của repo, không thay chúng:

1. **Rà schematic** (`autolayout/tools/sch_check.py`): chỉ cảnh báo (tụ reset, giá trị tụ theo datasheet, mã TVS chung chung). Người quyết sửa.
2. **Bản nháp tự động** (`autolayout/autolayout.py`): suy ý đồ từ netlist, hoán vị cụm linh kiện giống nhau và route thật từng hoán vị,
   đi dây theo tầng USB → nguồn → CC → tụ/GND → gate → tín hiệu chậm.
3. **Cổng bắt buộc** (`agent_edit.py WORK start`):
   - **Bước 0** = `tools/session_start.py review` của repo trên bản nháp. Tác tử mở từng ảnh và thay hết `TODO` trong `SESSION_START.md`.
   - **Cổng reference** = `tools/session_gate.py preflight session.json`. Thiếu reference → BLOCKED toàn board (đúng `reference_missing_behavior: GLOBAL_STOP`).
     `--training` bỏ qua cổng này **chỉ cho bài luyện tập**, ghi vào nhật ký; không dùng cho dự án thật.
   - Mọi lệnh sửa (`move/swap/nudge/rip/ripnear/route/pour/padconn/cleanvias`) tự gọi `gate` và thoát mã 3 khi một trong hai cổng chưa qua.
4. **Tác tử quan sát** (`agent_edit.py`): `show` (ảnh có tên net, crop 60 px/mm) → nhận xét theo vị trí tương đối →
   sửa một chỗ → `check` (DRC + via + self_review R1/R2/R3) → `undo` nếu xấu hơn. Mỗi bước là `stepNN_*.kicad_pcb` + một dòng `log.jsonl`.
5. **Chất lượng GND** (`agent_edit.py pour`): đổ đồng GND mặt trên (SMD nối đặc, THT thermal), via khâu lưới 3 mm ở chỗ trống cả 2 lớp.
6. Báo cáo cuối theo REVIEW_LEARNING_LOOP.md: 1 ảnh + ≤5 dòng, owner chỉ chọn ĐẠT / KHÔNG ĐẠT.

**Tiêu chí giữ hay bỏ một bản sửa (thứ tự ưu tiên):** DRC không xấu hơn → không thêm lỗi vị trí tương đối (dây dưới thân, dây kẹp giữa pad,
sai thứ tự nguồn) → nguồn không bị đẩy xuống lớp dưới → **sau cùng** mới xét số via / chiều dài.

## 2b. Khác biệt với pipeline Freerouting trên main (cần owner chọn)

| | `FREEROUTING_VISUAL_LOOP.md` (main) | Đề xuất này |
|---|---|---|
| Ai đi dây | Freerouting; tác tử chỉ đề xuất MOVE/ROTATE/REROUTE_NET | `pyroute` do tác tử điều khiển từng net |
| Giữ/bỏ bản sửa | "Không có cải thiện kỹ thuật thì giảm via hoặc chiều dài là được nhận" | Theo thứ tự ở trên; via là tiêu chí cuối |
| Ảnh | KiCad SVG → PNG (cần CairoSVG hoặc Inkscape) | pcbnew + PIL, có tên net; ảnh render KiCad lấy từ bước 0 |
| Số phương án | REF + OPT | Một bản, hoàn tác theo bước |

Bằng chứng cho dòng "giữ/bỏ": tối ưu theo số via (`tools/improve.py`, 1 giờ) đẩy +5V xuống B.Cu qua 2 via; tác tử theo vị trí tương đối không mắc lỗi đó.
Trên máy owner hiện **không có CairoSVG lẫn Inkscape**, nên vòng Freerouting chưa chạy được ở bước ảnh.

**Lỗi công cụ repo phát hiện khi chạy bước 0 thật (2026-11-27):** `session_start.py` cắt zoom lệch trên board vuong 30×30 mm vì render 2000×2600
không giữ tỉ lệ và khung ảnh được coi là viền board (zoom_J3 thực tế hiện U1, J4 nằm ngoài khung); `drc_body_keepout.py` vẫn crash trên KiCad 10.

## 2c. Phạm vi — owner cần quyết

`rules/owner_decisions.json` ghi: chưa giao board chuẩn (`OVR-NO-ASSIGNED-BOARD`), không tự chọn board Training, demo USB-C không đưa vào
LayoutRule (`OVR-USB-C-OUT-OF-SCOPE`). Bằng chứng chính ở đây là board STM8 RGB USB-C, do owner giao trong chat ngày 2026-11-22
("Thử board STM8 trước"). Đề xuất: coi STM8 là **bài luyện tập**, chỉ đưa vào repo phần quy trình và công cụ; owner quyết có giữ số liệu STM8 trong file này không.

## 3. Bài học (20 mục, đầy đủ trong `autolayout/learn/lessons.jsonl`)

| ID | Trạng thái | Luật |
|---|---|---|
| L01 | IMPLEMENTED | Chỉ đổi lớp sau khi đã thử cùng lớp với nới lỏng cho phép (rộng ≥0.1, clearance 0.15) |
| L02 | PARTIAL | Net ưu tiên cao bị kẹp giữa pad 2 linh kiện → dời/xoay linh kiện, không luồn |
| L03 | IMPLEMENTED | Nguồn: connector → TVS → bulk → tải; tụ decoupling trước chân IC |
| L04 | IMPLEMENTED | VBUS ưu tiên hơn CC; điện trở CC kéo ra ngoài hàng pad |
| L05 | TRIED | Hai IC nối bus: dịch IC cho hàng chân thẳng hàng trước khi route |
| L06 | IMPLEMENTED | Review bằng ảnh và vị trí tương đối; số chỉ dùng cho giới hạn cứng |
| L07 | IMPLEMENTED | Một review cuối phiên |
| L08 | IMPLEMENTED | Được đi dưới thân header/JST xuyên lỗ; giữ khoảng cách quanh via |
| L09 | IMPLEMENTED | Trích mẫu bố trí quan hệ từ ref design (khối USB-C, tụ decoupling) |
| L10 | PARTIAL | Xoay linh kiện là nước đi hạng nhất |
| L11 | IMPLEMENTED | Via 0.6/0.3 mặc định; nhỏ hơn chỉ ở hàng pad connector |
| L12 | IMPLEMENTED | USB FS không chỉnh độ dài |
| L13 | TRIED | Hoán vị cụm linh kiện giống nhau; **phải route thật để chọn**: ratsnest xếp hạng sai |
| L14 | IMPLEMENTED | Rà schematic trước layout, chỉ cảnh báo |
| L15 | TRIED | Ép mọi nhánh nguồn đi sau TVS làm đường +5V cắt giữa board (15 via so với 11). Pad VBUS thứ hai đã nối cầu tại connector thì nhánh từ pad đó được chấp nhận — **chờ owner xác nhận** |
| L16 | CANDIDATE | Khai báo ý đồ từng khối (như Vector vẽ lại schematic thành khối có tiêu đề) trước khi layout |
| L17 | CANDIDATE | Sửa tăng dần, chỉ đi lại net bị ảnh hưởng, kiểm sau mỗi bước |
| L18 | CANDIDATE | Tầng cuối: đổ đồng GND mặt trên + via khâu |
| L19 | CANDIDATE | Tụ lọc sát chân nguồn; được dời/xoay để đạt |
| L20 | TRIED | Quy trình chính = tác tử quan sát; script chỉ tạo bản nháp |

Quy trình của Vector dựng lại từ dấu vết file (Vector từ chối mô tả): [autolayout/learn/vector_inferred_pipeline.md](autolayout/learn/vector_inferred_pipeline.md).

## 4. Lỗi đã gặp và sửa (để không lặp lại)

- **Chân NC bị nối với nhau:** tầng không có net vẫn gọi router với `--order ""`, router nối mọi pad net rỗng → ~90 đoạn dây vô chủ,
  chặn bus; DRC vẫn báo "0 chưa nối". Đã sửa ở `autolayout.py` và `pyroute.py`. Bài luyện bus2ic và benchmark ref chạy trước đó **không dùng được**.
- **Git Bash đổi `/NET` thành đường dẫn:** luôn đặt `MSYS_NO_PATHCONV=1`.
- **Thước đo rẻ đánh lừa:** giao cắt ratsnest xếp bản tốt nhất ở cuối; số via tối ưu mù đẩy nguồn xuống lớp dưới.

## 5. Còn mở

- Bài luyện bus2ic và benchmark ref cần chạy lại sau bản sửa chân NC.
- `PASS_CRITERIA.md` mục A chưa đạt (via so với ref); mục B, C chưa có kết quả hợp lệ.
- Tác tử quan sát hiện chạy trong phiên chat; muốn chạy độc lập cần gọi mô hình qua API.
