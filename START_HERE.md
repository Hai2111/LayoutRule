# START HERE — đọc 1 trang này là đủ (các file khác là tư liệu)

## Repo này là gì
"Quy tắc xếp bảng mạch" cho agent (Claude/Codex). Agent đọc rồi layout/routing; **owner (Hai) không cần hiểu kỹ thuật — owner chỉ cần xem ảnh.**

**Giao bài "thiết kế 1 board hoàn thiện"?** → trả lời 10 câu hỏi trong [PROJECT_INTAKE.md](PROJECT_INTAKE.md) (trống câu nào agent tự dùng giá trị khởi điểm + ghi giả định, không dừng hỏi lại).

## Quy trình (3 bước)

```
1. Agent đọc: LAYOUT_RULES.md + ITERATIVE_ROUTING_PLAYBOOK.md
   + digest của ref design (rules/topology_digests.json)
2. Agent làm theo vùng: đặt → route → xem ảnh → kiểm logic
   (chỉ khi nào vùng đạt mới khóa vùng, sang vùng kế)
3. CHỦ nhận đúng 1 thứ: BỨC ẢNH + DANH SÁCH VẤN ĐỀ (≤ 5 dòng)
   → chỉ vào chỗ nào trong ảnh cần sửa → agent sửa → gửi lại ảnh
   DRC log, ledger, json... là của agent, chủ KHÔNG phải đọc
```

## Owner review (batch, một lần sau mỗi phiên)
1. Agent tự nghiên cứu reference, tự thử Candidate REF/OPT, kiểm tra và ghi ledger từng vùng; **không hỏi duyệt lẻ**.
2. Agent kết thúc phiên tại cổng G1/G3/G5 hoặc GLOBAL STOP khi thiếu reference bắt buộc; chỉ xuất **1 ảnh tổng hợp + tối đa 5 dòng** để owner duyệt một lần.
3. Rule mới/sửa vẫn là **đề xuất** chờ owner duyệt theo GOVERNANCE.md, không tự merge vào main. Xem SESSION_PIPELINE.md.

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
| `ITERATIVE_ROUTING_PLAYBOOK.md` | agent (cách làm theo vùng) |
| `rules/*.json` | agent (số liệu) |
| `tools/*.py` | agent chạy, **chủ không đọc** |
| `VIDEO_CATALOG` / `TECHNICAL_SOURCES` / `AI_LAYOUT_RESEARCH` | tư liệu nghiên cứu, **không thuộc quy trình** |
| `GOVERNANCE.md` | khi cần tranh luận "ai được quyền đổi gì" |
