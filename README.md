# LayoutRule — PCB Layout Knowledge Base

> Cơ sở tri thức phục vụ **KiCadAutoLayout / Codex / Claude**: placement, routing, PCB review, DRC, DFM.

**Cập nhật:** 2026-11-15 · **Trạng thái:** v0.1, tổng hợp nguồn mở (chưa xem/nghe toàn văn tất cả video).

## Bắt đầu
1. [VIDEO_CATALOG.md](VIDEO_CATALOG.md) — thống kê **từng video đã kiểm tra nguồn**, link, chương có liên quan và bài học rút ra; phân loại rõ mức xác minh.
2. [LAYOUT_RULES.md](LAYOUT_RULES.md) — bộ quy tắc có ID, điều kiện áp dụng, ngoại lệ và cách kiểm tra.
3. [PLACEMENT_ROUTING_WORKFLOW.md](PLACEMENT_ROUTING_WORKFLOW.md) — thứ tự placement / routing dành cho agent.
4. [REVIEW_CHECKLIST.md](REVIEW_CHECKLIST.md) — tiêu chí PASS/FAIL và yêu cầu bằng chứng.

## Nguyên tắc quan trọng
- **Không coi link / chapter / description là bằng chứng đã xem toàn bộ video.** Trạng thái mặc định là `SOURCE_METADATA_REVIEWED`; khi có transcript hoặc phân tích trực tiếp mới nâng cấp và ghi URL + timestamp/đoạn hỗ trợ.
- **Không dùng luật tuyệt đối thiếu cơ sở**, ví dụ “cấm góc 90° ở mọi trace”, “mọi tụ phải gần nhất về hình học”, hoặc “đi tất cả power trước mọi signal”.
- **DRC=0 là điều kiện cần, không đủ**; agent còn phải kiểm tra topology, return path, vòng dòng chuyển mạch, nhiệt, khả năng sản xuất và rủi ro EMI/SI.
- Các giới hạn chiều rộng, clearance, via, impedance **lấy từ nhà sản xuất, stackup và từng dự án**, không khóa cứng thành một cấu hình cho mọi board.

**Kiểm tra số video:** chạy `python tools/catalog_status.py --json-output report/videos.json --csv-output report/videos.csv` tại root repo. Không chứa transcript có bản quyền.

## Áp dụng vào KiCadAutoLayout
1. Đọc netlist/schematic, footprint, datasheet, stackup và PCB constraints.
2. Lập placement constraints, gán functional blocks và critical nets.
3. Placement theo các phase trong workflow; chạy kiểm tra sau từng phase.
4. Route theo độ ưu tiên kỹ thuật, không theo thứ tự tên net.
5. Chạy DRC/ERC, đối soát net connectivity + checklist độc lập, xuất báo cáo `rule_id | evidence | result | proposed_change`.
6. Mỗi lần người dùng sửa PCB: so sánh thay đổi và tránh ghi đè chỉnh sửa thủ công không có lý do kỹ thuật và bằng chứng.

## Quy định cập nhật
Mỗi video mới phải thêm một bản ghi trong `VIDEO_CATALOG.md` với: source, ngày, mức xác minh, mốc thời gian, tóm tắt, rule IDs, điểm cần xác minh tiếp. Rule mới chỉ được gắn `HARD` khi có điều kiện kỹ thuật/tiêu chuẩn hoặc thông số nhà sản xuất để kiểm tra.

**Nguồn:** [Phil's Lab](https://www.phils-lab.net/videos), [Altium Academy](https://www.youtube.com/@AltiumAcademy), tài liệu [Altium Component Placement & Routing](https://www.altium.com/documentation/altium-designer/tutorial/component-placement-routing-board). Nội dung trong repo là bản tóm tắt và đề xuất kiểm tra kỹ thuật, không sao chép transcript có bản quyền.
