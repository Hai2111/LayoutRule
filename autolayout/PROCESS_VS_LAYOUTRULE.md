# Quy trình hiện tại của agent so với LayoutRule `main` (PROPOSED)

Cập nhật 2026-11-28. Tác giả: Claude.
Nguồn: dự án OTA Rev1 (ESP32-S3 + W5500 + USB-C + RS485 + microSD, 2 lớp, 100 × 75 mm) và hai bài luyện STM8 / USB-C.
Theo `GOVERNANCE.md`, mọi thứ trong file này là **đề xuất**, chưa phải luật. Owner duyệt một lần, kết quả ĐẠT hoặc KHÔNG ĐẠT.

Quy trình đầy đủ: [learn/QUY_TRINH_LAYOUT.md](learn/QUY_TRINH_LAYOUT.md).
Bài học gốc: [learn/lessons.jsonl](learn/lessons.jsonl), từ L01 tới L80, chỉ thêm, không xoá.

## 1. Quy trình agent đang chạy (tóm tắt)

| # | Bước | Cách làm thực tế | Công cụ |
|---|---|---|---|
| 0 | Mở phiên | Chạy step 0 xem toàn board, rồi cổng reference: mỗi vùng phải có ảnh board thật làm ref. Thiếu ref thì tìm nguồn có sẵn, ví dụ board mã nguồn mở; tải file phải hỏi owner. | `session_start.py`, `session_gate.py`, `agent_edit.py start` |
| 1 | Đầu vào | Đọc stackup thật và luật fab trước. Số trở kháng lấy từ calculator của fab, ví dụ JLCPCB, rồi kiểm chéo bằng bộ giải của mình. | `diffz.py` (chỉ kiểm chéo) |
| 2 | Floorplan | Connector đặt theo thứ tự chân MCU. Chừa hành lang có đo kích thước cho từng luồng tín hiệu. Đảo Ethernet/RF tách khỏi luồng header. | `apply_place.py` |
| 3 | Chấm placement trước khi route | Đo chiều dài ratsnest MST, số điểm cắt nhau, courtyard chồng (dùng đa giác thật, không dùng bbox), kiểm tra keepout. | `place_score.py` |
| 4 | Linh kiện nhỏ | Đặt hàng loạt sát chân. Nhóm đã đặt tay giữ cố định bằng `--fix`. | `pack_small.py` |
| 5 | Hoán vị chân | Hoán vị GPIO hoặc linh kiện tương đương để bỏ điểm cắt, ví dụ SDIO, ETH SPI, hai điện trở kéo lên giống nhau. Agent tự quyết, ghi ảnh hưởng firmware. | sửa label schematic + pad net, parity = 0 |
| 6 | Route vùng khó bằng tay trước | USB-C 16P, cặp MDI Ethernet, fan-out chân QFN/LQFP, trục nguồn. Toạ độ tính sẵn, khe hở kiểm trước khi vẽ. Chỉ vẽ đoạn 0/45/90°. | `agent_edit.py track/via/move/delat` |
| 7 | Router cho phần còn lại | Router nhận ra pad đã nối bằng đồng có sẵn (union-find), nên không đi thêm đường thừa. Nếu thất bại thì đọc ảnh, tìm nguyên nhân (thứ tự chân, bức tường B.Cu), sửa placement hoặc tự route tay. | `pyroute.py` |
| 8 | Kiểm sau mỗi khối | DRC, số đường chưa nối, R1–R3 (dây dưới thân linh kiện, dây bị kẹp, thứ tự nguồn), W1, C90, V1, đếm dây không net. Xem ảnh vùng. | `agent_edit.py check`, `shot.py` |
| 9 | GND | GND đổ zone đặc hai lớp, không route GND. Khâu via dày. Zone GND dưới thân IC không có EP. | `agent_edit.py gndsolid/pour` |
| 10 | Review | Bộ câu hỏi gắn với rule, có cổng theo giai đoạn. Silkscreen chỉ làm khi mọi câu về đặt và route đã đạt. | `review_run.py`, `route_audit.py` |
| 11 | Chạy không sợ ngắt | Mỗi bước có lock theo PID, dấu `.done` theo hash input, ghi file nguyên tử, không để file rác. | `kpipe.py`, `ksave.py` |

## 2. So với LayoutRule `main`: chỗ giống nhau

- Step 0 xem toàn board và cổng reference trước khi sửa board: agent đã dùng (`agent_edit.py start`).
- Owner chỉ duyệt một lần ở bản cuối, kết quả ĐẠT hoặc KHÔNG ĐẠT, không hỏi duyệt lẻ: agent đã theo (memory "agent-owns-technical-decisions").
- INV-2, linh kiện luôn dời được: agent đã dời R1, R14/R15, R22, R25/R26, C22, R63/R64, R21 ngay trong lúc route.
- INV-3, agent quyết, tool chỉ thực thi: phần khó vẽ tay có toạ độ và lý do; router chỉ dùng cho net thường. Mọi bước được ghi vào `log.jsonl`.

## 3. Chỗ khác nhau: thứ agent đang làm mà LayoutRule chưa có

| Khác biệt | Bằng chứng (OTA) | Đề xuất cho LayoutRule |
|---|---|---|
| **Chấm placement bằng số trước khi route** (L46) | ratsnest 2195 → 1701 mm, số điểm cắt 244 → 54 | Thêm bước "Placement score" vào ITERATIVE_ROUTING_PLAYBOOK §3.1. Cổng: không tăng số điểm cắt. |
| **Hoán vị GPIO/chân tương đương là quyết định của agent** | SDIO: SD×SD 6 → 0. ETH SPI: 5 net 0 via, trước đó thứ tự hai đầu đảo hoàn toàn. | Ghi vào `rules/owner_decisions.json`: được hoán vị nếu giữ đủ ràng buộc strapping/PSRAM/USB và ghi ảnh hưởng firmware. |
| **Tra nguồn có sẵn trước khi tự giải** (L77, L78) | WIZnet HW Design Guide + JLCPCB calculator: 0.22 / 0.152 / 0.203 mm cho 100 Ω coplanar | Thêm vào TECHNICAL_SOURCES và AGENT_LAYOUT_PLAYBOOK: số trở kháng phải có nguồn từ fab. |
| **Route tay vùng khó trước, router sau** (L79) | USB-C, VBUS ring qua ESD tap, MDI, fan-out W5500 | Thêm vào ITERATIVE §3.2: liệt kê loại vùng bắt buộc route tay. |
| **Router phải tôn trọng đồng có sẵn** (L79) | +5V chéo 107.9 → 51 mm sau khi gộp nhóm pad | Áp dụng cho mọi engine: trước khi route, gộp pad đã nối thành một nhóm. |
| **Quy trình chịu được bị ngắt** (L76) | Tiến trình mồ côi, mất log, 14 file `.kicad_pro`/`.kicad_prl` rác | Đưa `kpipe.py`/`ksave.py` vào `tools/`, dùng cho `route_pipeline`. |
| **Không tạo đồng không net** (L80) | Git Bash đổi `/03_Ethernet/...` thành đường dẫn, tạo 3 via không net | Mọi tool tạo track/via phải kiểm net tồn tại. Trong Git Bash đặt `MSYS_NO_PATHCONV=1`. |
| **Bức tường B.Cu** | Trục +5V dọc trên B.Cu chặn mọi đường cắt dưới vùng fan-out | Thêm câu review: "Đường dài trên B.Cu có chặn hành lang cắt lớp không?" |
| **Fan-out LQFP không EP trên 2 lớp** | Chân GND đi vào trong thân IC; AVDD nối thành bus ngoài, không bao kín chân GND | Thêm vào PLACEMENT_PATTERNS. |
| **Bộ câu hỏi review có cổng giai đoạn** | 33 câu, silkscreen ở giai đoạn finish | Ánh xạ sang REVIEW_CHECKLIST. |

## 4. Lỗi tìm thấy trong LayoutRule (sửa trong nhánh này)

1. **`tools/drc_body_keepout.py` crash với file KiCad 10.** KiCad 10 ghi net của pad là `(net "NAME")`, không còn số, nên dòng `int(net_id[1])` báo ValueError. **Đã sửa** để đọc được cả hai dạng. Đã chạy lại trên board OTA và chạy `tests/`: OK.
2. **`tools/session_start.py`: khung ảnh zoom lệch khoảng 10 mm về phía tây** với board có anten nhô ra ngoài viền. Connector ở mép board rơi ra ngoài ảnh zoom. **Chưa sửa**; agent bù bằng ảnh `shot.py` của chính mình. Đề xuất: tính khung từ `GetBoardEdgesBoundingBox()` thay vì bbox footprint.
3. **Bản clone local `main` cũ hơn `origin/main`**, thiếu `session_start.py` và `session_gate.py`. Đây là lỗi môi trường, không phải lỗi repo. Đề xuất ghi vào START_HERE: chạy `git fetch` và kiểm tra hai tool này có mặt.

## 5. Chỗ agent còn thiếu so với LayoutRule (sẽ làm)

- **Ledger theo từng net** (`routing_ledger.json` theo INV-3): hiện chỉ có `log.jsonl` theo bước. Sẽ sinh ledger cho OTA khi kết thúc phiên route.
- **Hai ứng viên REF/OPT** theo SESSION_PIPELINE: hiện chỉ có một ứng viên. Với OTA, OPT là placement v8 so với REF là placement gốc.
- **`rules/topology_digests.json`**: chưa đọc digest; ref chỉ đọc qua ảnh.
- **PROJECT_INTAKE** 10 câu: chưa trả lời chính thức cho OTA. Giá trị khởi điểm lấy từ repo OTA.

## 6. Thay đổi trong nhánh đề xuất này

- `autolayout/tools/`, mới:
  - `apply_place`, `place_score`, `pack_small` (placement)
  - `kpipe`, `ksave` (chạy không sợ ngắt)
  - `diffz` (kiểm chéo trở kháng)
  - `review_run`, `route_audit` (review)
  - `ref_block_view` (xem khối của ref)
- `autolayout/tools/`, sửa: `agent_edit` (từ chối net không tồn tại, copy sheet con, `init` không copy đè), `pyroute` (gộp pad đã nối), `shot` (`RATS=1`, ghi nguyên tử).
- `autolayout/learn/`: `lessons.jsonl` (L01–L80), `QUY_TRINH_LAYOUT.md`, `review_questions.json`, `exercises.jsonl`, `runs.jsonl`.
- `tools/drc_body_keepout.py`: sửa lỗi KiCad 10.

Không đụng `main`. Không đổi file luật đã APPROVED. Chỉ owner merge.
