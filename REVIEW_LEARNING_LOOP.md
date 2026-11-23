# REVIEW LEARNING LOOP — một lần review bản cuối, học từ mọi phản hồi

**Đề xuất cập nhật 2026-11-23.** Đây là quy trình agent áp dụng cho các **dự án được giao sau này**. Bài demo USB-C độc lập không phải một project của LayoutRule và không tự động trở thành training data/rule.

## Nguyên tắc bất biến của phiên

1. Owner giao đề bài cụ thể khi sẵn sàng. **Không tự chọn board Training, không tự đưa demo USB-C vào repo.**
2. Agent local (Codex/Claude CLI) tự chạy placement ↔ routing ↔ ảnh ↔ DRC/geometry; cổng G1/G3/G5 và các vùng R1–R4 là **checkpoint nội bộ**, không phải điểm hỏi owner.
3. **Owner chỉ review bản cuối của một phiên, sau khi agent đã gửi báo cáo.** Không gửi candidate từng vòng để duyệt; không xin duyệt từng linh kiện, via, net hay cổng. Chỉ gửi một ảnh 2D từ PCB thực theo template + tối đa 5 dòng kết quả/các quyết định cần owner.
4. **Không khóa vị trí/copper/vùng sau khi review hoặc khi qua checkpoint nội bộ.** Mọi placement và routing không thuộc neo cơ khí đều có thể được xét lại nếu toàn board tốt hơn. Những neo có ràng buộc cơ khí thực tế (connector mating, lỗ vít, kích thước/vỏ, vị trí khớp cơ khí chủ đã cung cấp) không được tự di chuyển.
5. Nếu chưa có stackup/fab numbers, dùng giá trị khởi điểm có căn cứ trong layout_intent.json và gắn `ASSUMED`; không yêu cầu owner chốt sớm. Không tự điền số giả thành yêu cầu bắt buộc. Khi điều kiện an toàn/điện thực sự cần thông số còn thiếu, ghi `NEEDS_REVIEW`, không bịa PASS.
6. Reference coverage vẫn tuân theo quy tắc GLOBAL STOP đã chốt; khi bị chặn, agent nghiên cứu đến khi hết khả năng, đóng phiên bằng **một** báo cáo `BLOCKED`. GLOBAL STOP không phải "khóa vùng" hay "đóng băng placement" sau review.

## Mỗi lần owner review bản cuối — phải học, không chỉ ghi "đã sửa"

```text
Agent tự làm trọn phiên -> ảnh PCB thực + báo cáo ngắn -> OWNER REVIEW (một lần)
                                                |
                           ghi nguyên văn góp ý + marker/vùng/net liên quan
                                                |
                   tách nhận xét (quan sát) khỏi giả thuyết (nguyên nhân)
                                                |
                 đề xuất một cách sửa kiểm chứng được + phản ví dụ/rủi ro
                                                |
           lưu candidate/branch + ảnh before/after + DRC + audit + board SHA
                                                |
                         phiên sau agent thử lại, kiểm tra hồi quy toàn vùng
                                                |
                     chỉ nâng thành rule sau khi owner duyệt rule đó
```

Feedback cần phân biệt:
- `ACCEPT`: owner nói **"được/đạt"**. Đây mới là quyết định chấp nhận layout; DRC PASS chỉ là điều kiện kỹ thuật cần thiết, không thay cho owner.
- `REVISE`: owner thấy chưa đạt, chỉ ra marker/vùng hoặc tiêu chí. Agent ghi lại, tự sửa ở phiên **tiếp theo**, không yêu cầu xác nhận từng bước.
- `REJECT`: phương án không được dùng làm thiết kế cuối, vẫn có thể lưu lỗi có giá trị học tập.
- `DEFER`: owner chưa quyết định; giữ candidate ở nhánh riêng, không merge.

**Không được suy diễn câu "được" thành chấp thuận một rule mới**. Sửa layout và đổi rule chuẩn là hai hành động riêng; việc đổi rule vẫn phải theo GOVERNANCE.md.

## Gói bằng chứng agent lưu, owner không cần đọc

Mỗi phản hồi có một record như sau (có thể nằm ở repo dự án tương ứng, **không** ghi đè LayoutRule):

```json
{
  "session_id": "example-session",
  "board_sha256": "<sha256 của PCB được review>",
  "owner_feedback_verbatim": "<nguyên văn owner nhận xét>",
  "owner_verdict": "REVISE",
  "markers": ["R1-P03"],
  "observations": ["Trace đi vòng do vị trí R1"],
  "hypotheses": ["R1 đang chặn kênh escape của U1"],
  "proposed_experiments": ["Dời R1, re-route nhóm net, so sánh với candidate ban đầu"],
  "reference_region": "<source URL + vị trí trên ảnh>",
  "checks_required": ["KiCad DRC", "geometry audit", "visual comparison"],
  "reusable_lesson": "PROPOSED",
  "scope_and_exceptions": "Chỉ áp dụng khi pinout/keepout và cơ khí cho phép",
  "next_session": "PENDING"
}
```

Owner chỉ cần cho biết điều **chưa ưng** và/hoặc nói đã **đạt**; agent tự phân tích, phân loại, thử sửa, ghi học và báo kết quả. Không buộc owner phải giải thích kỹ thuật.

## Cách nhận biết agent thực sự học được

- Ở **phiên sau**, agent **phải đọc các feedback trước** và nêu được quyết định nào khác đi do review đó. Không chỉ lặp lại nguyên văn hoặc sao chép tọa độ.
- Khi lỗi tương tự tái diễn ở board/region khác, agent phải tự phát hiện và thử cách sửa đã học, **nhưng kiểm tra điều kiện áp dụng** trước.
- Nếu một bài học không hiệu quả, ghi counterexample, rollback candidate; không âm thầm nâng lên rule.
- **Không tự khóa** candidate thắng, copper tốt, vùng đạt hoặc thiết kế được owner chấp nhận. Giữ revision/branch để rollback và tránh ghi đè bản owner đã review.

## Kết thúc một phiên

- `TECHNICAL_READY`: các check cần thiết hợp lệ, nhưng **chưa phải owner ACCEPT**.
- `READY_FOR_OWNER`: agent đã hoàn thiện candidate cuối của phiên và đã tạo báo cáo cuối.
- `OWNER_ACCEPTED`: owner xác nhận phương án cụ thể; không đồng nghĩa rule chung được duyệt.
- `BLOCKED`: agent không được sửa PCB thêm; chỉ báo cáo một lần với lý do và bằng chứng.

Bảo vệ ràng buộc điện/cơ khí, làm việc trên nhánh/copy; không commit/merge main tự động. **Mỗi vòng lặp nội bộ được tự làm, chỉ bản cuối mỗi phiên mới đưa owner xem.**

## Agent local — dùng được ngay

Agent tự ghi file `owner_words.txt` chứa **đúng nguyên văn** góp ý của chủ (không yêu cầu chủ chạy script). Sau đó gọi:

~~~bash
python tools/review_feedback.py record --history PROJECT/reviews/owner_feedback.jsonl --session-id SESSION_ID --board PROJECT/final_candidate.kicad_pcb --feedback-file PROJECT/owner_words.txt --verdict REVISE --marker R1-P03
# Trước phiên sau, bắt buộc đọc lại toàn bộ lịch sử
python tools/review_feedback.py context --history PROJECT/reviews/owner_feedback.jsonl --json
~~~

Verdict `ACCEPT` chỉ được nhập khi owner **thực sự xác nhận**; không suy từ DRC hoặc im lặng. Công cụ lưu nguyên văn + SHA của PCB được review + marker + trạng thái chưa có rule được công nhận. Agent tự diễn giải kỹ thuật, tạo thử nghiệm và xác nhận hồi quy ở phiên sau. Ledger thuộc repo dự án, không tự đồng bộ vào rulebook chung.
