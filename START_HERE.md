# START HERE — đọc 1 trang này là đủ (các file khác là tư liệu)

## Repo này là gì
"Quy tắc xếp bảng mạch" cho agent (Claude/Codex). Agent đọc rồi layout/routing; **owner (Hai) không cần hiểu kỹ thuật — owner chỉ cần xem ảnh.**

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

## Chủ (owner) chỉ duyệt 2 loại
1. **Ảnh layout + danh sách vấn đề** của từng vùng → "sửa chỗ X" / "được, khóa".
2. **Rule mới/sửa** (hiếm): agent đưa bằng chứng, chủ gật hay lắc.

## Map nhanh các file

| File | Ai đọc |
|---|---|
| `START_HERE.md` (file này) | chủ + agent |
| `LAYOUT_RULES.md` | agent (bộ quy tắc) |
| `ITERATIVE_ROUTING_PLAYBOOK.md` | agent (cách làm theo vùng) |
| `rules/*.json` | agent (số liệu) |
| `tools/*.py` | agent chạy, **chủ không đọc** |
| `VIDEO_CATALOG` / `TECHNICAL_SOURCES` / `AI_LAYOUT_RESEARCH` | tư liệu nghiên cứu, **không thuộc quy trình** |
| `GOVERNANCE.md` | khi cần tranh luận "ai được quyền đổi gì" |
