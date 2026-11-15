# LAYOUT RULES v0.1 — Evidence-based

**Date** 2026-11-15. Mục tiêu: quy tắc cho PCB do con người hoặc agent bố trí và đi dây; không đồng nhất thông số thiết kế cho mọi board.

- `HARD`: vi phạm yêu cầu dự án/datasheet/DRC hoặc rủi ro đã được xác định; fail khi có bằng chứng.
- `CONDITIONAL`: áp dụng khi điều kiện (stackup, tín hiệu, tốc độ cạnh, dòng, môi trường, fab) đúng.
- `HEURISTIC`: mục tiêu tối ưu, được phép đánh đổi có giải trình.
- Mỗi check báo `PASS/FAIL/NEEDS_REVIEW/NOT_APPLICABLE`, ghi bằng chứng. Không tự động gán PASS nếu thiếu dữ liệu.

## A — Constraints & planning
| ID | Level | Rule | Kiểm tra |
|---|---|---|---|
| A01 | HARD | Xác minh schematic/netlist, pinout, footprint và hướng pin trước placement. | Đối chiếu net-to-pad; ERC/footprint map. |
| A02 | HARD | DRC parameters (width, gap, via, mask, drill, edge, creepage) lấy theo nhà sản xuất + dự án; không bịa số. | Constraint provenance + DRC. |
| A03 | CONDITIONAL | Stack-up phải phù hợp high-speed/current/EMI/chi phí; trace impedance tính theo stack-up thực. | Board setup và fab stackup. |
| A04 | HARD | Không phá keepout, board outline, mechanical clearance, antenna keepout, connector envelope. | Bounding boxes, 3D, courtyard. |
| A05 | HEURISTIC | Phân nhóm chức năng: power, MCU, clock, analog, RF, USB, IO/connector; xác định critical nets trước placement. | Functional group map. |

## P — Placement (ưu tiên)
| ID | Level | Rule | Kiểm tra |
|---|---|---|---|
| P01 | HARD | Các vị trí bị khóa cơ khí (connector, mount hole, board-to-board, switch, antenna) đặt trước. | Mechanical constraint/locked. |
| P02 | HEURISTIC | Đặt IC chủ chốt và khối critical trước linh kiện phụ, theo signal/power flow; tối thiểu giao cắt ratsnest sau khi bảo toàn ràng buộc. | Block map, ratsnest cost. |
| P03 | CONDITIONAL | Với buck/boost: VIN bypass, IC, diode/FET, inductor và output tụ được đặt theo dòng vòng switching; giảm diện tích vòng có di/dt cao, nút SW nhỏ. | Visual current loop topology; area. |
| P04 | CONDITIONAL | Decoupling: tối thiểu **loop inductance** từ power pin tới GND, không chỉ khoảng cách đo bằng thước. Cách đặt phụ thuộc loại IC, pin, stackup. | Path geometry/return path, planes, pin adjacency. |
| P05 | CONDITIONAL | Crystal + load caps gần pin clock, bảo vệ vùng nhạy, tránh SW/power noisy xuyên qua. | Gán critical route và proximity. |
| P06 | CONDITIONAL | ESD/TVS gần cổng vào; giữ đường dòng xung về chassis/GND ngắn và đúng topology, tránh dòng xung đi qua IC được bảo vệ. | Connector→TVS→IC path / return. |
| P07 | CONDITIONAL | Antenna RF: tuân thủ ground/keepout/matching/network theo datasheet/module; ưu tiên vị trí rìa theo cấu hình phù hợp. | Vendor app note và clearance. |
| P08 | CONDITIONAL | Analog front-end: nhóm linh kiện theo signal flow, tách nguồn nhiễu, bảo vệ đường vào high-Z/low-level; không áp dụng cấm phân vùng GND tuyệt đối. | Sensitive-to-noisy spacing, return topology. |
| P09 | CONDITIONAL | BGA/QFN: bảo đảm khả năng fanout, vias phù hợp công nghệ lỗ và hàn; không tự cho phép via-in-pad không được nhà máy hỗ trợ. | Pitch, solder mask/assembly constraints. |
| P10 | HEURISTIC | Dùng rotation/flip/MCU pin reassignment hợp lệ để giảm cắt nhau và chiều dài critical net; tuyệt đối không đổi chức năng pin mà chưa xác minh. | Connectivity and firmware constraints. |
| P11 | HEURISTIC | Tránh bố trí quá dày không cần thiết; chừa không gian cho testpoint, assembly, rework, mounting. | Assembly keepout / service access. |

## R — Routing (không tuyến tính theo net ID)
| ID | Level | Rule | Kiểm tra |
|---|---|---|---|
| R01 | HARD | Mỗi copper segment phải kết nối đúng net, không ngắn mạch, không bỏ airwire ở trạng thái release. | Connectivity + DRC + board inspection. |
| R02 | CONDITIONAL | Route signal có ràng buộc **trước** net thường: clocks, RF, USB, differential pairs, high-speed, ADC input/low-level. | Priority map with exceptions. |
| R03 | CONDITIONAL | Route switching power loops và decoupling liên quan ngay sau khi placement khối, trước khi net khác chắn đường; thứ tự tương đối với signals theo risk. | Loop integrity and congestion. |
| R04 | CONDITIONAL | Trace có dòng lớn phải đáp ứng I, ΔT, độ sụt áp, đồng, chiều dài, copper pour và thermal (không lấy dòng chỉ từ 'min width'). | I²R, IPC-2152/thermal validation, fab copper. |
| R05 | CONDITIONAL | Khi có return plane tham chiếu, không vô cớ route qua split/void; nếu phải đổi plane/layer, bố trí return transfer/stitching path thích hợp. | Reference plane continuity under signal. |
| R06 | CONDITIONAL | Board 2 lớp: cố gắng giữ vùng GND liên tục, tránh xẻ nền bởi hàng loạt trace; thiết kế GND jumps/stitching khi cần. | Polygon connectivity / return path assessment. |
| R07 | CONDITIONAL | Đối với cặp vi sai, width/gap/impedance/skew theo chuẩn giao tiếp, stackup và yêu cầu chip; coupling không thay thế plane return. | Pair-specific rule + impedance calc. |
| R08 | HEURISTIC | Ưu tiên route ngắn, có mục đích; tối thiểu via/chuyển lớp **mà không** hy sinh reference plane, current capacity, EMI hay khả năng đi dây. | Routed length/via count with penalties. |
| R09 | HEURISTIC | Góc 45°/bo tròn thường dễ kiểm soát hình học; **không fail góc 90° chỉ vì là 90°** nếu không có ràng buộc cơ/điện đặc thù. | Corner-angle warning only by default. |
| R10 | CONDITIONAL | Hạn chế parallel run sát và dài giữa aggressor/victim, đặc biệt fast edge/analog sensitive; tăng spacing, return path, phân lớp hợp lý. | Spacing/parallel length/crosstalk risk. |
| R11 | CONDITIONAL | RF 50Ω/controlled impedance chỉ khi giao diện và stackup yêu cầu; tránh đổi bề rộng trace một cách tùy tiện. | Calculation + vendor/fab validation. |
| R12 | HEURISTIC | Tránh branch, stub và neck-down không cần thiết; có ngoại lệ (test point, low-speed). | Net topology/risk. |
| R13 | HARD | Route không được đặt sát edge, drill, copper zone, NPTH, thermal pad... trái DRC/fab constraints. | DRC/DFM. |

## G — Ground, polygons, manufacturability
| ID | Level | Rule | Kiểm tra |
|---|---|---|---|
| G01 | CONDITIONAL | Không tự chia AGND/DGND hoặc cắt GND plane chỉ vì tên khối; ưu tiên kiểm soát đường return và dòng nhiễu. | Ground topology review. |
| G02 | CONDITIONAL | Copper pour đúng net/priority/clearance; bỏ island gây vấn đề, kiểm tra thermals theo dòng và khả năng hàn. | Repour + DRC + thermal review. |
| G03 | CONDITIONAL | Stitching/return via đặt có mục đích tại via transitions, shield/edge/RF khi cần, không rải theo khoảng cách vô căn cứ. | Return transfer & fab clearance. |
| G04 | CONDITIONAL | Nhiệt: đảm bảo copper/thermal vias/solderability quanh linh kiện sinh nhiệt; không dùng thermal-relief yếu cho dòng lớn. | Power loss, copper area, soldering. |
| G05 | HARD | Refill copper, run DRC/ERC, đối chiếu designators, polarity, pin-1, mask, silkscreen, testpoint, 3D, Gerber & drill trước release. | Checklist + artifacts. |
| G06 | HARD | Manual edits không được bị agent ghi đè vô điều kiện; diff PCB revision và yêu cầu lý do nếu move/reroute vị trí do người dùng đã sửa. | File diff + intent log. |
| G07 | HARD | Review G1–G5: DRC không đồng nghĩa layout đúng; mỗi fail có vị trí, evidence, recommended action và file/hash nguồn. | Signed review report. |

## Quan trọng: những hiểu lầm không được biến thành luật
1. **“Không bao giờ đi trace 90°”** → sai khi biến thành lệnh tuyệt đối. Góc vuông không tự động gây hỏng tín hiệu; cân nhắc EMI/impedance, etch và hình học ở tần số cao theo ngữ cảnh.
2. **“Tụ decoupling lúc nào cũng sát IC nhất”** → metric đúng hơn là loop inductance, topology và planes, pin.
3. **“Tất cả power net route trước signal”** → sai với clock, RF, diff-pair và routing congestion; cần đồ thị ưu tiên phụ thuộc.
4. **“PCB 2-layer không cần tham chiếu GND”** → sai; return path quan trọng đặc biệt khi bottom layer bị chia cắt.

## Tham chiếu gốc (đối chiếu rule ID trong catalog)
- Phil's Lab #60 buck layout (loop / routing): https://www.youtube.com/watch?v=AmfLhT5SntE
- Phil's Lab #65 KiCad 2-layer full tutorial: https://www.youtube.com/watch?v=aVUqaB0IMh4
- Phil's Lab #137 2-layer design: https://home.fedevel.com/blog/2-layer-pcb-design-tips-phils-lab-137
- Phil's Lab #144 QFN: https://www.youtube.com/watch?v=hOamoJ15hmA
- Phil's Lab #170 design rules: https://www.youtube.com/watch?v=zeH3WbMWvdg
- Phil's Lab #176 copper: https://www.youtube.com/watch?v=Ao2HUjjhlmQ
- Altium Academy decoupling routing tradeoffs: https://www.youtube.com/watch?v=1O48JZX8j5g
- Altium Academy decoupling placement: https://www.youtube.com/watch?v=SSpyE9CP97g
- Altium Academy AI vs human layout: https://www.youtube.com/watch?v=qX29OWSYTmI

**Nguồn hiện tại được xác minh ở mức description/chapter/site article, không phải đã xem đầy đủ tất cả video. Các diễn giải kỹ thuật là tổng hợp độc lập, không phải trích dẫn nguyên văn.**
