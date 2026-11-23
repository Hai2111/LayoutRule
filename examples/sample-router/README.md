# sample-router — dự án mẫu 1-lệnh cho agent

**Mục đích:** dự án nhỏ, **KiCad-native sạch** (không phải board convert Altium) để 1 session agent chạy được **cả chuỗi routing + kiểm tra** từ repo, làm bước kiểm thử cho pipeline. Board convert Altium (RA01) chưa export được DSN (xem `setup/SMOKE_TEST.md`) nên demo phải dùng board native.

## Nó có gì
- `sample-router.kicad_pcb` — 2 lớp, **6 component, 10 net, 14 segment + 3 via đã có sẵn**, GND plane lớp B.Cu, một phần routing (chưa hoàn chỉnh — có net chưa nối).
- `layout_intent.json` — intent mẫu (net class, decoupling, hot loop, diff pair USB) đúng schema `AGENT_LAYOUT_PLAYBOOK.md`.
- `sample-router.kicad_pro` — design rules min 0.2 mm, class mặc định.

## Agent chạy thế nào (theo đúng ITERATIVE_ROUTING_PLAYBOOK)
```powershell
# 0) toolchain
powershell -NoProfile -ExecutionPolicy Bypass -File setup\setup.ps1
# 1) routing candidate (1 lệnh, không ghi đè board gốc)
powershell -NoProfile -ExecutionPolicy Bypass -File tools\route_pipeline.ps1 -Board examples\sample-router\sample-router.kicad_pcb
```
Pipeline ra (trong `examples/sample-router/routing_candidate/`):
`sample-router.dsn` → Freerouting JAR → `sample-router.ses` → import vào **candidate riêng** `sample-router-routed.kicad_pcb` → DRC json → **ảnh 3D PNG**.

Sau đó agent làm đúng vòng lặp §3: visual pass 3 tầng + logic pass (INV-1/2/3) trên candidate, rồi báo cáo theo §3.5 = **1 ảnh + ≤5 dòng** cho owner. Board gốc `sample-router.kicad_pcb` không bao giờ bị ghi đè.

## Chờ mong đợi khi owner xem
- Ảnh 3D + 5 dòng vấn đề (đúng format §3.5).
- DRC candidate có thể còn vi phạm/via không nối — điều này **cố ý**: pipeline chỉ tạo *candidate*, agent phải iter (H1: xê linh kiện → route lại) rồi mới giao. Freerouting "0 unrouted" không đồng nghĩa đạt chuẩn (rule R13/G05).

## Kết quả hiện tại (baseline, 2026-11-23)
- Board nguồn `sample-router.kicad_pcb` ở trạng thái **0 unconnected** (đã dọn các tự-xung-đột cũ của fixture).
- Pipeline (MaxPasses 8) → candidate: **0 unconnected**, Freerouting score 1000 (0 unrouted / 0 router violation).
- Ảnh `routing_candidate/sample-router-routed.png` được pipeline **tự sinh lại** mỗi lần chạy (không vẽ tay).
- Vẫn còn (giữ làm **bài H1 cho agent**): ~3–4 góc vuông 90° ở cụm nguồn U2/L1/C1 (F.Cu) + ~4 trace 0.15 mm dưới min DRC 0.2 mm + 1 orphan via. **Cách xử lý đúng** = H1 trong playbook (xê linh kiện → route lại 45°), không phải chỉnh ảnh.
- Lưu ý: mỗi lần xê linh kiện có thể sinh lỗi mới (đã kiểm chứng xê C1 → GND U2 mất nối), nên giữ baseline 0-unconnected; agent phải cân bằng.
