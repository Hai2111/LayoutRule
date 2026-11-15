# LayoutRule — PCB Layout Knowledge Base

> Cơ sở tri thức phục vụ **KiCadAutoLayout / Codex / Claude**: placement, routing, PCB review, DRC, DFM.

**Cập nhật:** 2026-11-15 · **Trạng thái:** research v0.3, có metadata/video chapters và một số reference PDF visual-inspected; **chưa xác minh video toàn văn; đã đọc một phần tọa độ linh kiện/net trong 1 tệp CAD, chưa parse hình học/DRC đầy đủ**.

## Routing engine (bổ sung 2026-11-15)
- [ROUTING_ENGINE_INTEGRATION.md](ROUTING_ENGINE_INTEGRATION.md) — so sánh Freerouting DSN/SES và PCBWorld/CADET, luật routing + cách kiểm tra native DRC. Code thử nghiệm đã commit trong [Hai2111/Training/routing](https://github.com/Hai2111/Training/tree/main/routing).
- KiCad 10 export/import Specctra DSN/SES được xác minh trong API chính thức. Adapter Python mới **chưa thực thi với KiCad/Java thật trên máy người dùng**, chỉ compile và plan-only test.

## Bắt đầu
1. [VIDEO_CATALOG.md](VIDEO_CATALOG.md) — **43 video** Phil's Lab / Altium Academy.
2. [VIDEO_REVIEWS_EXTERNAL.md](VIDEO_REVIEWS_EXTERNAL.md) — **25 video review** ngoài hai kênh: Robert Feranec/FEDEVEL, EEVblog, element14.
3. [REFERENCE_DESIGN_CATALOG.md](REFERENCE_DESIGN_CATALOG.md) — **36 nguồn reference PCB/hãng**, mức xác minh khác nhau.
4. [PLACEMENT_PATTERNS.md](PLACEMENT_PATTERNS.md) — **16 pattern có điều kiện**, từ mechanical freeze tới source-specific crystal placement.
5. [LAYOUT_RULES.md](LAYOUT_RULES.md) — bộ quy tắc có ID, điều kiện áp dụng, ngoại lệ và cách kiểm tra.
6. [PLACEMENT_ROUTING_WORKFLOW.md](PLACEMENT_ROUTING_WORKFLOW.md) — thứ tự placement / routing dành cho agent.
7. [REVIEW_CHECKLIST.md](REVIEW_CHECKLIST.md) — tiêu chí PASS/FAIL và yêu cầu bằng chứng.
8. [AGENTS.md](AGENTS.md) — yêu cầu Codex/Claude kế thừa và kiểm chứng quy tắc.
9. [tools/catalog_status.py](tools/catalog_status.py) — tạo thống kê video CSV/JSON.
10. [rules/placement_patterns.json](rules/placement_patterns.json) — dữ liệu machine-readable **16 placement patterns**, chưa gắn engine kiểm tra tự động.
11. [references/index.json](references/index.json) — danh mục có cấu trúc cho **36 reference design**, xác minh theo cấp độ.
12. [tools/reference_status.py](tools/reference_status.py) — kiểm tra index/MD đồng nhất và xuất CSV.
13. [TECHNICAL_SOURCES.md](TECHNICAL_SOURCES.md) — 13 nguồn tiêu chuẩn/tài liệu hãng/KiCad có mức bằng chứng rõ ràng.
14. [rules/technical_checks.json](rules/technical_checks.json) — 10 đề xuất kiểm tra layout có inputs và điều kiện, **chưa thực thi**.
15. [references/RD30_kicad_placement_sample.json](references/RD30_kicad_placement_sample.json) — 1 bộ dữ liệu vị trí + net được trích trực tiếp từ KiCad source, có SHA.
16. [AI_LAYOUT_RESEARCH.md](AI_LAYOUT_RESEARCH.md) — 7 paper/repo khoa học, bao gồm CADET + PCBWorld và thiết kế benchmark KiCadAutoLayout.

## Nguyên tắc quan trọng
- **Không coi link / chapter / description là bằng chứng đã xem toàn bộ video.** Trạng thái mặc định là `SOURCE_METADATA_REVIEWED`; khi có transcript hoặc phân tích trực tiếp mới nâng cấp và ghi URL + timestamp/đoạn hỗ trợ.
- **Không dùng luật tuyệt đối thiếu cơ sở**, ví dụ “cấm góc 90° ở mọi trace”, “mọi tụ phải gần nhất về hình học”, hoặc “đi tất cả power trước mọi signal”.
- **Prioritize device-specific source:** Espressif ESP32-S3 crystal guide đề nghị gap >=2.0 mm tới clock pin; không suy ra đó là ngưỡng chung cho MCU khác. Xem RD03/PT04.
- **DRC=0 là điều kiện cần, không đủ**; agent còn phải kiểm tra topology, return path, vòng dòng chuyển mạch, nhiệt, khả năng sản xuất và rủi ro EMI/SI.
- Các giới hạn chiều rộng, clearance, via, impedance **lấy từ nhà sản xuất, stackup và từng dự án**, không khóa cứng thành một cấu hình cho mọi board.

**Tổng catalog video: 68 video = 37 Phil's Lab + 6 Altium Academy + 25 nguồn ngoài; trạng thái metadata/chapter M=68, transcript/video full T/V=0.** Không tuyên bố đã xem hết.

**Kiểm tra reference:** chạy `python tools/reference_status.py --csv-output report/references.csv` tại root repo. Hiện **1/36** reference đã được đọc một phần placement/net từ CAD (RD30), **0/36** đã parse/verify toàn bộ geometry + DRC/electrical performance; các luật hình học khác còn là candidates.

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

**Nguồn chính:** [Phil's Lab](https://www.phils-lab.net/videos), [Altium Academy](https://www.youtube.com/@AltiumAcademy), tài liệu [Altium Component Placement & Routing](https://www.altium.com/documentation/altium-designer/tutorial/component-placement-routing-board). Nội dung trong repo là bản tóm tắt và đề xuất kiểm tra kỹ thuật, không sao chép transcript có bản quyền.
