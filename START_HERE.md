# START HERE — đọc 1 trang này là đủ (các file khác là tư liệu)

## Repo này là gì
"Quy tắc xếp bảng mạch" cho agent (Claude/Codex). Agent đọc rồi layout/routing; **owner (Hai) không cần hiểu kỹ thuật — owner chỉ cần xem ảnh.**

**Giao bài "thiết kế 1 board hoàn thiện"?** → trả lời 10 câu hỏi trong [PROJECT_INTAKE.md](PROJECT_INTAKE.md) (trống câu nào agent tự dùng giá trị khởi điểm + ghi giả định, không dừng hỏi lại).

## Quy trình (3 bước)

```
1. Agent đọc: rules/owner_decisions.json (quyết định mới ghi đè cũ)
   + LAYOUT_RULES.md + ITERATIVE_ROUTING_PLAYBOOK.md
   + digest của ref design (rules/topology_digests.json)
2. Agent làm theo vùng: đặt → route → xem ảnh → kiểm logic
   (qua checkpoint thì ghi snapshot, không khóa vùng/copper; chỉ giữ neo cơ khí)
3. Agent hoàn thiện bản cuối phiên + báo cáo trước; CHỦ chỉ review 1 lần
   qua 1 ẢNH PCB THẬT + KẾT LUẬN ≤ 5 dòng, hoặc báo cáo BLOCKED.
   Feedback được ghi nguyên văn, đưa vào vòng học ở phiên sau.
   DRC log/ledger/JSON của agent; không có lệnh khóa layout sau review.
```

## Owner review (batch, một lần sau mỗi phiên)
1. Agent tự nghiên cứu reference, tự thử Candidate REF/OPT, kiểm tra và ghi ledger từng vùng; **không hỏi duyệt lẻ**.
2. G1/G3/G5 là **checkpoint nội bộ**; chỉ sau khi agent hoàn thiện bản cuối và báo cáo (hoặc GLOBAL STOP) mới gửi **1 ảnh tổng hợp + tối đa 5 dòng** để owner duyệt một lần.
3. Owner quyết định layout đạt hay chưa; sau mỗi review agent lưu feedback và tự học cho phiên sau theo [REVIEW_LEARNING_LOOP.md](REVIEW_LEARNING_LOOP.md). **Không khóa layout**, trừ neo phải khớp cơ khí. Rule mới/sửa vẫn chỉ là đề xuất theo GOVERNANCE.md.

**Scope:** chưa có PCB benchmark được owner giao; demo USB-C ở chat là thử nghiệm riêng, **không** phải project đưa vào LayoutRule. Thiếu số liệu fab/stackup thì dùng giả định có ghi nguồn, không xin owner quyết định sớm.

## Trạng thái nhanh (cái nào đã chốt, cái nào chưa)

| Hạng mục | Trạng thái | Ý nghĩa với chủ |
|---|---|---|
| Quy tắc A/P/R/G (`LAYOUT_RULES.md`) | ✅ APPROVED | luật đã chốt |
| Vòng lặp theo vùng + INV + H1/H2 + báo cáo 1 ảnh (`ITERATIVE_ROUTING_PLAYBOOK.md`) | ✅ APPROVED | cách làm đã chốt |
| Rule 001 starter (số clearance/track) | ⚠️ APPROVED nhưng **tham số DRAFT** | số dùng tạm; DRC thật chưa chạy |
| Ngưỡng class digest light/medium/heavy | ✅ APPROVED | đã chốt |
| Catalog video / reference / research | ⚠️ research, chưa xác minh toàn văn | tư liệu, chưa phải chuẩn |

## Map nhanh các file

| File | Ai đọc |
|---|---|
| `START_HERE.md` (file này) | chủ + agent |
| `PROJECT_INTAKE.md` | chủ trả lời khi giao project mới |
| `LAYOUT_RULES.md` | agent (bộ quy tắc) |
| `rules/owner_decisions.json` | agent (35 xác nhận và các ngoại lệ sau này) |
| `ITERATIVE_ROUTING_PLAYBOOK.md` | agent (cách làm theo vùng) |
| `REVIEW_LEARNING_LOOP.md` | agent (học sau mỗi phản hồi bản cuối) |
| `rules/*.json` | agent (số liệu) |
| `tools/*.py` | agent chạy, **chủ không đọc** |
| `VIDEO_CATALOG` / `TECHNICAL_SOURCES` / `AI_LAYOUT_RESEARCH` | tư liệu nghiên cứu, **không thuộc quy trình** |
| `GOVERNANCE.md` | khi cần tranh luận "ai được quyền đổi gì" |
