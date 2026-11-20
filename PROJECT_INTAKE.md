# PROJECT INTAKE — 10 câu hỏi khi giao bài "thiết kế 1 board hoàn thiện"

Mục đích: chủ (owner) trả lời **một lần khi giao bài**, agent có đủ dữ kiện để làm tới cùng.
Trống câu nào thì agent **không dừng hỏi lại** — dùng giá trị khởi điểm từ `rules/layout_defaults.json`,
ghi vào mục `assumptions` của intent (nguyên tắc N2), và hiện rõ giả định đó trong ảnh + danh sách vấn đề.

## A. Đầu vào thiết kế (bắt buộc có ít nhất 1)
1. **Schematic/Netlist có sẵn chưa?** File gì (KiCad `.kicad_sch`, Altium, PDF)? Đã chạy ERC sạch chưa?
   *(Không có → mô tả chức năng để agent tự thiết kế, agent phải gửi lại ảnh schematic trước khi layout.)*
2. **BOM/datasheet đầy đủ chưa?** IC chính (MCU, RF module, nguồn) có datasheet + layout guide không?
3. **Board này làm gì, đầu vào/ra là gì?** 1–2 câu (ví dụ: "đọc cảm biến khói, báo qua LoRa, nguồn 5V USB").

## B. Cơ khí
4. **Kích thước/envelope có giới hạn không?** Connector, lỗ bắt vít, antenna, battery có vị trí cố định?
5. **Số lớp: chốt 2/4 hay để agent chọn?** (agent chọn theo bảng §0.1 của AGENT_LAYOUT_PLAYBOOK nếu bỏ trống).

## C. Điện
6. **Nguồn vào gì, dòng từng rail bao nhiêu?** (USB-C 5V, pin Li-ion, AC…; dòng max rail lớn nhất).
7. **Giao tiếp nào có ràng buộc tốc độ/tín hiệu?** USB HS? RF 433/LoRa/GPS? BLE/LTE module? → có cần controlled impedance không.

## D. Sản xuất
8. **Fab nào (JLCPCB standard/HD, hay khác)?** → quyết định min track/clearance (0.2 hay 0.1 mm).
9. **Tầng lớp PCB + ngân sách/lead time** (nếu ảnh hưởng chọn 2/4 lớp, vật liệu FR-4/EPDM).

## E. Chốt "hoàn thiện"
10. **"Hoàn thiện" = gì?** Tối thiểu: ảnh + danh sách vấn đề từng vùng đạt, DRC/ERC = 0, Gerber + position file xuất được.
    Cần thêm gì: testpoint, silkscreen, tài liệu assembly, firmware constraints?

---
**Cách dùng:** dán 10 câu trả lời này (hoặc "chưa có") vào thư mục project, đặt tên `intake.txt`.
Agent đọc trước `layout_intent.json`; câu nào trả "chưa có" → giả định ghi trong `assumptions`, hiện trong báo cáo ảnh.
