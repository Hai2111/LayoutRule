# LayoutRule — PCB Layout Knowledge Base

> Cơ sở tri thức phục vụ **KiCadAutoLayout / Codex / Claude**: placement, routing, PCB review, DRC, DFM.

**Đọc trước tiên:** [START_HERE.md](START_HERE.md) — 1 trang quy trình cho cả owner và agent. Đề bài board mới: [PROJECT_INTAKE.md](PROJECT_INTAKE.md) — 10 câu hỏi giao bài; thông tin thiếu được ghi thành giả định, không dừng flow.

**Cập nhật:** 2026-11-23 (đang đề xuất PR #5) · **Trạng thái:** core approved — quy tắc A/P/R/G (LAYOUT_RULES), playbook vòng lặp theo vùng (ITERATIVE_ROUTING_PLAYBOOK, H1/H2 + visual scan 3 tầng), rule 001 starter (tham số DRAFT, fab cross-checked, DRC chưa chạy) và topology digest format (class boundaries đã chốt). Phần catalog video/reference vẫn là research v0.3: metadata/chapters, chưa xác minh toàn văn.

## Quy trình cho agent tự làm layout (approved 2026-11-20, owner Hai)
- [ITERATIVE_ROUTING_PLAYBOOK.md](ITERATIVE_ROUTING_PLAYBOOK.md) — **cách làm chính hiện hành**: chia vùng R1→R4, vòng lặp *đặt → route (agent quyết định, tool thực thi) → ảnh 3 tầng → logic*, 3 bất biến INV-1/2/3, 2 hành vi chuẩn H1 (route ⇄ xê linh kiện xuyên suốt) + H2 (ảnh ratsnest là bản đồ đầu vào), báo cáo vùng = **1 ảnh + ≤5 dòng** cho owner.
- [AGENT_LAYOUT_PLAYBOOK.md](AGENT_LAYOUT_PLAYBOOK.md) — quy trình 5 pha có cổng kiểm (intent → floorplan → placement → routing → kiểm chức năng), giữ làm nền cho các cổng.
- [rules/layout_defaults.json](rules/layout_defaults.json) — giá trị khởi điểm (bề rộng theo dòng, số via đổi lớp, khoảng cách decoupling, vòng nóng…); mỗi giá trị ghi rõ `VENDOR` / `CALC` / `PRACTICE`.
- [rules/001-general-layout.md](rules/001-general-layout.md) — rule starter "general layout & clearance" cho board prototype FR-4 2–4 lớp; tham số DRAFT (đã cross-check fab, DRC validation PENDING).
- [rules/topology_digests.json](rules/topology_digests.json) — digest "input nhỏ" để 1 session đọc/hiểu ref design không cần parse cả file CAD; class boundaries light/medium/heavy đã chốt.
- [tools/layout_audit.py](tools/layout_audit.py) — đo hình học `.kicad_pcb` so với `layout_intent.json`; mới thử trên board tổng hợp trong `tests/fixtures/`, chưa thử trên board KiCad 10 thật.
- [FREEROUTING_VISUAL_LOOP.md](FREEROUTING_VISUAL_LOOP.md) — **Freerouting + ảnh PCB 2D + agent local** + `STAGE_REPORT.html`/`stage_results.json` minh bạch từng bước (ảnh gốc KiCad SVG→PNG, ROI, giả thuyết lỗi, KEEP/ROLLBACK có SHA): tự thử đổi placement/rip-up net, reroute, đo DRC và rollback. Thử nghiệm: chưa chạy end-to-end trên KiCad local.
- [CLOSED_LOOP_RUNBOOK.md](CLOSED_LOOP_RUNBOOK.md) — **vòng lặp local thật**: Codex/Claude quyết định → Python `pcbnew` sửa candidate → KiCad DRC + ảnh F.Cu/B.Cu → KEEP/ROLLBACK; chưa xác minh end-to-end bằng KiCad host.
- [tools/layout_controller.py](tools/layout_controller.py) — điều phối vòng lặp; `layout_observer.py`, `kicad_executor.py`, `candidate_evaluator.py` thực thi/kiểm chứng, không khóa board.
- [rules/owner_decisions.json](rules/owner_decisions.json) — **dữ liệu gốc Q01–Q35**: 32 lựa chọn A/B/C, Q22 xác nhận bằng lời, Q14/Q35 chưa chọn; các quyết định mới thay thế được đánh dấu rõ để agent không áp dụng rule cũ.
- [REVIEW_LEARNING_LOOP.md](REVIEW_LEARNING_LOOP.md) — **owner chỉ review bản cuối sau báo cáo**, agent giữ nguyên văn góp ý, đọc lại ở phiên sau; không khóa vùng/linh kiện trừ neo cơ khí và không tự công nhận rule.\n- [SESSION_PIPELINE.md](SESSION_PIPELINE.md) — **ONE SESSION = ONE OWNER REVIEW**: reference phải đủ bằng chứng trước routing, thiếu là GLOBAL STOP; hai candidate trên branch riêng; 1 ảnh tổng hợp và tối đa 5 dòng để chủ duyệt cuối phiên.

## Autolayout đã học (PROPOSED 2026-11-26)
- [AUTOLAYOUT_LEARNED.md](AUTOLAYOUT_LEARNED.md) — tổng hợp 20 bài học, quy trình tác tử quan sát (nhìn ảnh → sửa đúng chỗ → DRC), so sánh với Vector; mã trong [autolayout/](autolayout/).

## Routing engine (bổ sung 2026-11-15)
- [ROUTING_ENGINE_INTEGRATION.md](ROUTING_ENGINE_INTEGRATION.md) — so sánh Freerouting DSN/SES và PCBWorld/CADET, luật routing + cách kiểm tra native DRC. Code thử nghiệm đã commit trong [Hai2111/Training/routing](https://github.com/Hai2111/Training/tree/main/routing).
- [tools/route_pipeline.ps1](tools/route_pipeline.ps1) — cổng reference bắt buộc; nhận CandidateBoard do agent tạo hoặc FreeroutingProposal thử nghiệm; native KiCad DRC + geometry audit. Xem [setup/SMOKE_TEST.md](setup/SMOKE_TEST.md) cho giới hạn đã xác minh.

## Tư liệu tham khảo (CHỈ agent cần đào sâu đọc — không thuộc quy trình mặc định, xem START_HERE.md)
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
13. [TECHNICAL_SOURCES.md](TECHNICAL_SOURCES.md) — 17 nguồn tiêu chuẩn/tài liệu hãng/KiCad (TS14–TS17 là đề xuất mới) có mức bằng chứng rõ ràng.
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
