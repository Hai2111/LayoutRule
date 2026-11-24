# Freerouting + Vision Agent Loop (experimental)

**Purpose:** use Freerouting to route copper, then let a local Codex/Claude
agent inspect **real KiCad 2D F.Cu/B.Cu images** and propose placement/rip-up
changes, automatically rerouting and keeping only measured improvements.

## Flow

~~~text
Original KiCad board + intent + references + previous owner feedback
 -> reference preflight (missing evidence => global STOP)
 -> KiCad DSN -> Freerouting JAR -> SES -> routed KiCad board
 -> KiCad DRC + audit + actual F.Cu & B.Cu PNG
 -> local vision agent reviews pads, vias, net congestion, return paths
 -> proposal: MOVE / ROTATE / REROUTE_NET
 -> pcbnew moves parts and rips up affected existing copper on a COPY
 -> Freerouting reroutes -> DRC + PNG + audit -> KEEP or ROLLBACK
 -> repeat, then write best_routed.kicad_pcb + evidence
 -> owner reviews only a final candidate after independent checks
~~~

The model does not guess track geometries from a picture. It decides
placement and affected nets. Freerouting solves the copper routes.

## One local Windows command

Requirements: KiCad 10 pcbnew Python + kicad-cli, Java, the pinned
Freerouting JAR installed by setup/setup.ps1, authenticated Codex CLI.

~~~powershell
& "C:\Program Files\KiCad\10.0\bin\python.exe" tools\freerouting_visual_loop.py --board "D:\PCB\project\board.kicad_pcb" --manifest "D:\PCB\project\session.json" --intent "D:\PCB\project\layout_intent.json" --output "D:\PCB\project\visual_fr" --kicad-python "C:\Program Files\KiCad\10.0\bin\python.exe" --kicad-cli "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe" --provider codex --iterations 8 --passes 8
~~~

The paths are examples; no test design has been assigned. The script
requires a real input PCB and appropriate references. You can choose
--provider claude: Claude Code is prompted to read images with its Read
tool; that image-ingestion path is not yet verified on the owner's PC.

## Required inputs

- session.json: existing SESSION_PIPELINE.md manifest, with all real
  reference images and ROI records. Set submission_stage to G3 (internal),
  not FINAL.
- layout_intent.json: existing intent, plus an explicit
  "mechanical_anchor_refs": ["J1", "H1"] or [] when truly none.
  Optionally set "protected_net_names": ["GND"] for circuits whose existing
  copper should never be stripped automatically.
- Previous feedback: PROJECT/reviews/owner_feedback.jsonl (optional).

## Kiểm chứng ảnh và giám sát từng công đoạn

**KiCad 10 không còn lệnh `pcb export png` cho 2D copper**. Script
`tools/kicad_2d_export.py` dùng **KiCad native `pcb export svg`**
cho từng layer F.Cu/B.Cu, rồi chuyển các SVG gốc thành PNG bằng **CairoSVG**
hoặc **Inkscape**. Trên Windows phải cài một trong hai: nếu không, pipeline
báo lỗi rõ ràng, không tự vẽ ảnh thay thế hoặc tái sử dụng ảnh cũ.

Mở file `<output>/STAGE_REPORT.html` trên máy sau mỗi phiên để xem:

| Công đoạn | Thứ phải xuất ra | Mức chứng minh |
|---|---|---|
| Reference preflight | Mọi vùng + layer reference, status | Thiếu → GLOBAL STOP |
| DSN → JAR → SES | File kèm SHA và command/exit | Đã chạy đúng chuỗi thao tác |
| KiCad capture | SVG gốc, PNG, layer, kích thước, SHA board, lệnh export | Chứng minh nguồn ảnh, **không** chứng minh agent nhìn đúng |
| Agent nhìn & khoanh lỗi | Layer, ROI chuẩn hóa, ref/net hiện hữu, `finding_X_F.svg`, lý do sửa | **Giả thuyết**, chưa tự xác minh đúng lỗi |
| Sửa placement/rip-up | `decision.json`, candidate board, SHA | Thực thi/kiểm soát cơ khí |
| Route lại | DSN/SES, candidate mới, SHA | Có board mới thực tế |
| Đối chiếu | F.Cu/B.Cu trước/sau, DRC, unconnected, via, chiều dài, geometry | Bằng chứng số; cần xem lại vùng đã sửa |
| KEEP/ROLLBACK | Đường dẫn bản thắng/bản bị loại, SHA và lý do | Bản gốc bất biến, best kiểm chứng SHA |
| Final | Kết luận nội bộ + bản cuối | **Không** đồng nghĩa owner ACCEPT |

Mỗi bước lưu ngay vào `stage_results.json` và cập nhật `STAGE_REPORT.html`.
Nhật ký nằm trong thư mục output của project, không cần owner đọc từng file.
Nếu xảy ra ROLLBACK thông thường, best không bị ghi đè; khi lỗi ghi file
dở dang xảy ra, công cụ thử khôi phục bằng bản snapshot SHA đã xác minh.
Nếu không khôi phục được, công cụ phải dừng với lỗi **FATAL**.

**Không thể kết luận đã khoanh đúng lỗi chỉ bằng ROI hợp lệ.**
ROI hợp lệ chứng minh crop trùng các pixel ảnh KiCad; mức chính xác của chẩn
đoán phải dựa vào DRC/hình học/net/thiết kế điện, hoặc đánh giá bản cuối.
Ảnh crop before/after có thể lệch khi KiCad thay đổi phạm vi plot tự động,
nên được gắn `NEEDS_INDEPENDENT_VALIDATION` chứ không coi là kết quả PASS.

## Owner-facing output — chỉ cần mở một file

**Chỉ mở `STAGE_REPORT.html`** để xem một trang ngắn: kết quả, ảnh PCB
F.Cu trước/sau (B.Cu có thể mở thêm), tối đa 3 lỗi agent nghi ngờ,
và mỗi lượt thử được KEEP hay ROLLBACK. Mọi chi tiết DSN/SES/SHA/lệnh/ảnh
vẫn lưu trong `stage_results.json` và chỉ xuất hiện khi mở phần kỹ thuật.
File PCB để review là `best_routed.kicad_pcb`.

**Lưu ý:** Báo cáo ngắn không đồng nghĩa QA bị rút gọn; agent vẫn phải
chạy đủ toàn bộ bước kiểm chứng. Kết quả kỹ thuật chưa phải owner ACCEPT.

## Outputs

- best_pre_route.kicad_pcb: preserved candidate placement.
- best_routed.kicad_pcb: best Freerouting routed output.
- baseline_route/ and baseline_observation/: real KiCad initial evidence.
- iteration_NN/: decision JSON, Freerouting data, real copper images, audit.
- iterations.json, session_progress.json, FINAL_CANDIDATE_SUMMARY.md.
- **STAGE_REPORT.html** (mở bằng trình duyệt: bảng tổng công đoạn, ảnh,
  crop, lỗi, quyết định KEEP/ROLLBACK), **stage_results.json** (dữ liệu đầy đủ),
  và command_steps.json trong mỗi folder Freerouting.

Two consecutive failed/no-improvement proposals stop the loop. DRC errors,
unconnected items, audit and keepout are regression blockers. Without a
technical improvement, reducing via count or total copper length is accepted.
The source PCB is SHA checked and never overwritten. No automatic merge.

## Limitations (must be verified before claiming functional quality)

1. Freerouting reroutes the entire board after each targeted rip-up;
   this is not KiCad's native interactive push-and-shove.
2. Whole-net rip-up can affect other regions; cap at 12 nets or 300 copper
   items per iteration. Protect sensitive net copper via intent.
3. DRC PASS does not prove electrical return path quality, signal/power
   integrity, thermals or EMI. The agent's visual hypotheses must be
   checked against copper geometry and device-specific vendor constraints.
4. Unit tests use fake router, vision and observer. Actual KiCad 10 on-host
   end-to-end execution is PENDING (no board has been assigned yet).
5. No automatic owner approval or final report generation. Only send
   the final PCB after a separate end-of-session validation/review process.

Sources: KiCad 10 official kicad-cli export png documentation and the
Freerouting CLI DSN/SES command contract. See the existing technical
sources and setup/SMOKE_TEST.md for evidence levels.
