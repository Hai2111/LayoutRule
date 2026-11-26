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

## 2. Quy trình đề xuất

1. **Rà schematic** (`tools/sch_check.py`): chỉ cảnh báo (tụ reset, giá trị tụ theo datasheet, mã TVS chung chung). Người quyết sửa.
2. **Bản nháp tự động** (`autolayout.py`): suy ý đồ từ netlist, hoán vị cụm linh kiện giống nhau và route thật từng hoán vị
   (`tools/swap_blocks.py`), đi dây theo tầng USB → nguồn → CC → tụ/GND → gate → tín hiệu chậm.
3. **Tác tử quan sát** (`tools/agent_edit.py`): `show` (ảnh có tên net, crop 60 px/mm) → nhận xét theo vị trí tương đối →
   `move/swap/nudge` linh kiện, `rip/ripnear` + `route` vài net → `check` (DRC + via) → `undo` nếu xấu hơn.
   Mỗi bước là một file `stepNN_*.kicad_pcb` + dòng nhật ký `log.jsonl`.
4. **Chất lượng GND** (`agent_edit.py pour`): đổ đồng GND mặt trên (SMD nối đặc, THT thermal), via khâu lưới 3 mm ở chỗ trống cả 2 lớp.
5. **Tự kiểm quan hệ** (`tools/self_review.py`): R1 dây dưới thân, R2 dây kẹp giữa pad 2 linh kiện, R3 thứ tự cấp nguồn.
6. Báo cáo cuối: 1 ảnh + ĐẠT/KHÔNG ĐẠT.

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
