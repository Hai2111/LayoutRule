# PLACEMENT PATTERNS — mô hình ra quyết định cho agent

Updated 2026-11-15. Nguồn đối chiếu: [REFERENCE_DESIGN_CATALOG.md](REFERENCE_DESIGN_CATALOG.md) (RDxx), [VIDEO_REVIEWS_EXTERNAL.md](VIDEO_REVIEWS_EXTERNAL.md) (EXxx), [VIDEO_CATALOG.md](VIDEO_CATALOG.md) (PLxx, AAxx).

**Nguyên tắc:** Đánh giá vị trí dựa trên **pad-to-pad path, electrical topology, return current và thứ tự ưu tiên**, không chỉ khoảng cách tâm linh kiện hay số airwire. `HARD` chỉ khi ràng buộc datasheet/board/fab yêu cầu; các quy tắc khác là `CONDITIONAL` hoặc `HEURISTIC`.

## PT01 — Placement theo anchor và functional flow
- **Khi nào:** mọi board có connector/hole/switch/antenna/locked parts.
- **Thứ tự:** (1) board/mechanical constraints; (2) connector, antenna, mount, externally operated parts; (3) IC theo khối; (4) companion parts theo pin/topology; (5) test/assembly.
- **Kiểm tra:** locked part, connector orientation + keepout + mating, board edge, courtyard và các route feasibility region.
- **Chỉ tối ưu:** minimizing weighted airwires sau hard mechanical constraints; tuyệt đối không di chuyển connector chỉ để rút trace.
- **Evidence:** EX08 [0:39–13:49], EX14 [3:34–11:15], EX15 [53:57]; RD08.
- **Không áp:** board có MCU package + mechanical được nhà cung cấp khóa chung một footprint module.

## PT02 — Buck/boost: tìm hot loop trước khi đặt cuộn cảm
- **Khi nào:** switching converter.
- **Ràng buộc topology:** xác định **hot loop** theo transistor switching + input cap power GND; ưu tiên `CIN⇄VIN/GND⇄switch` ngắn và thấp inductance; đặt inductor bên SW, COUT theo đường load current, FB sense xa nút SW.
- **Kiểm tra:** cùng layer cho các parts critical **khi vendor đề nghị**; đo route/loop area trên pad/net, polygon path, cách biệt FB-SW và FB sensing; có GND return thực.
- **Không đặt ngưỡng vòng mm² tùy tiện:** ngưỡng theo EVM + tần số switching, di/dt và EMI target.
- **Nguồn mạnh:** RD01 TI TPS62933 §12.1–12.2 (hình top & bottom đã kiểm tra); EX02/EX10 tham khảo ví dụ khác.
- **Phản ví dụ:** cuộn cảm đặt sát IC nhất nhưng chặn đường CIN–power GND sẽ làm loop tệ hơn; IC flyback/SEPIC có loop topology khác.
- **Auto-check:** critical net path + polygon loop region + relative clearance FB vs SW; `NEEDS_REVIEW` nếu chỉ có component centers.

## PT03 — Decoupling: tối ưu power/ground loop, không phải gần tâm nhất
- **Khi nào:** mọi IC có supply bypass.
- **Quan hệ:** `power_pin→capacitor_pad→capacitor_GND_pad→return` phải có loop nhỏ/inductance thấp; phân biệt local high-frequency cap với bulk cap.
- **Kiểm tra:** cùng layer khi phù hợp, via-to-plane gần power/GND pin theo topology, không để via/copper khó nối bị trace khác chắn; so sánh route path qua pad, không chỉ tâm.
- **Nguồn:** RD01, RD03 (Espressif supply), EX20, PL09, AA03/AA04 (metadata).
- **Ngoại lệ:** via-in-pad/plane embedded, package BGA, shared capacitors; không tự đặt ngưỡng 1mm/2mm cho mọi chip.

## PT04 — Crystal placement theo IC cụ thể (QUY TẮC XUNG ĐỘT)
- **Khi nào:** external crystal/oscillator.
- **Vendor override:** nguồn RD03 ESP32-S3 **khuyến nghị crystal cách clock pin ít nhất 2.0 mm**, không via trên clock traces, tránh route dưới crystal, series component sát chip, matching cap dọc hai bên crystal. Đây là trường hợp chống lại khẩu hiệu `crystal càng sát MCU càng tốt`.
- **Kiểm tra:** `crystal_to_clock_pin_gap >= vendor_min` khi chip/guide áp dụng; net trace via-count, adjacent aggressor, GND shielding theo vendor; lấy pin/pad clearance thích hợp để đo.
- **Ngoại lệ:** với nRF/ST/IC khác **phải** dùng layout guide của chúng, không mang con số 2.0 mm sang; nếu chưa có guide `NEEDS_REVIEW`.
- **Nguồn:** RD03; EX08 [25:00] là ví dụ placement RP2040, không phải tiêu chuẩn.

## PT05 — ESD/protection đặt theo cửa xâm nhập
- **Khi nào:** connector với TVS/ESD/clamp/filter.
- **Quan hệ:** protector tại điểm entry, đường xung về chassis/GND như topology vendor; đặt TVS trước khu vực IC nhạy cảm và tránh để surge chạy qua GND nhạy cảm.
- **Kiểm tra:** connector–TVS vs connector–IC order qua net + ground return; ESD component-to-port region.
- **Nguồn:** RD03 power entry ESD; PL04, PL32.
- **Ngoại lệ:** bảo vệ USB HS cần kiểm tra loading/capacitance; bố trí nearest center không thay tính toán đường xung.

## PT06 — Return-path corridor cho board hai lớp
- **Khi nào:** 2-layer board, fast edge, noisy power, sensitive analog/RF.
- **Quan hệ:** placement/routing phải bảo toàn GND region dưới critical traces, không tạo split kéo dài qua line khác; nếu crossing thì return jump/stitching có kiểm chứng.
- **Kiểm tra:** raster/polygon connectivity trên B.Cu, shortest return via/ground path, discontinuity length, clearance, island count. Xem pre-pour và post-pour.
- **Nguồn:** RD03 2-layer guidance, EX11 [14:01,54:46], EX12, EX13, PL03.
- **Ngoại lệ:** intentional isolation/creepage/safety boundary; không short isolated grounds để thỏa metric.

## PT07 — Memory / USB / diff placement và fanout
- **Khi nào:** flash/PSRAM/SPI tốc độ cao, USB, diff pairs, QFN/BGA.
- **Quan hệ:** component trong chuỗi tương tác đặt cùng routing corridor; có khoảng không để fanout chân; resistor series sát source nếu vendor yêu cầu; USB entry→protection→IC theo topology.
- **Kiểm tra:** wire crossing estimate, pin escape, pair contiguous ground reference, designed impedance theo stackup, length/skew theo interface; **không** giả định tất cả SPI cần 50Ω.
- **Nguồn:** RD03 SPI+USB, EX08 [27:00,30:40], EX09 [07:13,35:28,1:21:56], EX16.

## PT08 — Placement là bài toán có vòng phản hồi, không phải 1 lượt
- **Khi nào:** sau rough placement hoặc candidate route xuất hiện blockages.
- **Thuật toán:** anchor freeze → block floorplan → critical parts → preliminary fanout/route → congestion / return map → rotate/swap legitimate → full route → inspect/rework.
- **Metric:** DRC, critical length, current loop, user-lock conflict, via count và routing congestion; lưu before/after.
- **Nguồn:** EX08/09/10, EX14, EX15. Tối ưu `length only` không đủ.
- **Ngoại lệ:** không auto-rollback thay đổi user; mọi move cần log lý do.

## PT09 — Review nhiều lớp bằng chứng / không lấy DRC=0 làm điểm cuối
- **Khi nào:** từng phase và trước fab release.
- **Kiểm tra:** electrical topology, mechanical, placement, hot loops, reference plane, traces, antipads/vias, thermals, EMI/DFM, full DRC, Gerber/3D.
- **Nguồn:** EX01, EX03, EX10; RD08.
- **Cảnh báo:** DRC pass nhưng không chứng minh signal integrity hoặc EMI. `manual_change` phải được nhận ra và tôn trọng.

## PT10 — RF/antenna vùng keepout theo module/stackup
- **Khi nào:** PCB antenna, chip antenna, coax/IPEX RF feed.
- **Quan hệ:** module antenna ưu tiên edge/ngoài baseboard; RF matching theo datasheet và vendor; isolation RF vs USB/UART/clock.
- **Kiểm tra:** layer keepout, housing clearance, pad/trace impedance, microstrip/CPWG reference, CLC orientation per vendor, RF path no via khi vendor yêu cầu.
- **Nguồn:** RD03; RD04 catalog chưa parse; PL10, PL33.
- **Ngoại lệ:** ESP32-S3 chip-down RF 0201 zigzag và 15-mil stub (nếu dùng) không chuyển nguyên sang WROOM module.

## PT11 — AD5940/AD5941 AFE và giao diện điện cực
- **Khi nào:** điện cực đo trở kháng, high-impedance sense/force.
- **Quan hệ:** connector electrode, AFE inputs, RCAL/RTIA, power references lập thành signal flow với sự chú ý đến ký sinh đường đo và nhiễu switching.
- **Kiểm tra:** danh sách net force/sense, guard/return model **theo topology chính xác**, chiều dài/độ đối xứng và clearance phù hợp độ nhạy; không tự cài guard ring vô căn cứ.
- **Nguồn:** RD05 (đã xem artwork trang 1,2), RD06 (file listed), [ADI AD5940 product docs](https://www.analog.com/en/products/ad5940.html).
- **Cảnh báo:** dữ liệu hình PCB chưa đủ suy ra giá trị guard spacing hay độ chính xác EIS; board có cable parasitics đáng kể.

## PT12 — Định giá via theo return/escape, không theo số lượng thuần
- **Khi nào:** switching layer / ground stitching / narrow pitch fanout.
- **Quan hệ:** via không chỉ tăng length/L, mà còn phá vùng ground reference hay bảo đảm current return; phải xét cả vị trí lỗ và soldermask/fab.
- **Nguồn:** EX11/12/20, PL09/31.
- **Kiểm tra:** per critical signal via transition với adjacent return, resulting GND polygon neck, current/thermal rating; QFN pad via-in-pad nếu fab cho phép.

## PT13 — Repeated analog channels: cấu trúc lặp và quản lý matching
- **Khi nào:** board có 2+ channel CT, Rogowski coil, đồng pha đa kênh, multi-phase driver; yêu cầu matching channel nếu accuracy/signal integrity thực sự đòi hỏi.
- **Reference:** RD11 TI TIDA-010986 (đã mở assembly SLURB45 trang 1): U1/U4/U6 lặp cấu trúc R/C theo pha; RD10/RD12/RD13/ RD20 là candidates **chưa phân tích geometry**.
- **Placement:** tạo một channel template với input connector, protection/RC, gain stage, ADC path; đặt các channel cạnh nhau hoặc theo đối xứng nếu cơ khí/EMI cho phép; tách khỏi high-di/dt source.
- **Routing:** map pairing `input_i → filter_i → amplifier_i → ADC_i`; so sánh branch lengths/vias/reference only when relevant, không bắt mọi channel có length chính xác như nhau.
- **Check:** channel component-count, relative group order, per-channel net topology, return overlap, crosstalk aggressor.
- **Exception:** pha/chức năng với scaling/gain khác nhau không nên ép identical geometry; assembly artwork không tự xác nhận điện trở/giá trị/timing.
- **Status:** CONDITIONAL / evidence RD11 partial-visual.

## PT14 — Isolation barrier / creepage floorplanning
- **Khi nào:** ISO35T, isolated AFE, PoE, high-voltage input, medical/safety isolation.
- **Reference:** RD14 (TI TIDA-010065), RD18 (TI TIDA-00057), RD10 (isolated interfaces), RD25 (PoE revision).
- **Placement:** xác định primary vs secondary domains, boundary và nơi tín hiệu đi qua isolation component; **chừa đủ hành lang trước khi bố trí transceiver, connector, DC/DC và testpoint**.
- **Check:** clearance, creepage along board surface, slots/cuts, copper/mask/connector and any copper crossing barrier; use applicable insulation standard, voltage, CTI, pollution degree, fab data.
- **Safety:** không tự copy spacing từ EVM; không tự chèn GND stitching nối qua barrier; cần electrical isolation sign-off.
- **Status:** HARD **nếu có spec cách ly xác định**, nếu chưa rõ `NEEDS_REVIEW`.

## PT15 — Field bus connector/protection/transceiver chain
- **Khi nào:** RS485 field interface, industrial external cable, optional isolated domains.
- **Reference:** RD16 TIDA-00862, RD17 TIDA-00060, RD18 TIDA-00057 (Gerber listed only); PL32 protection tutorial.
- **Placement:** chọn topology và hardware requirements trước: connector ↔ surge/ESD + common-mode filter nếu dùng ↔ transceiver ↔ MCU; bố trí TVS GND return ngắn và tránh surge through MCU analog ground.
- **Check:** branch topology, stub, term/bias location, return, shield/chassis ground decision, isolated vs unisolated barrier.
- **Caution:** 'TVS nearest connector' là heuristic về surge path, không phải min-center-distance; RS485 half/full duplex, bus bias và termination không trộn lẫn.
- **Status:** CONDITIONAL / requires schematic + board review.

## PT16 — Learn from revision diffs before encoding a rule
- **Khi nào:** reference repository có released PCB history + ghi chú lỗi sản xuất/thermal/SI.
- **Reference:** RD25 OLIMEX ESP32-POE revision log: I chuyển 2→4 layers để tăng cooling DCDC; H1 sửa Ethernet connection khi có tải; RD26 ESP32-GATEWAY change log về noise Ethernet clock/GPIO17.
- **Method:** pin exact revision SHA and source state → derive before/after refdes+net+layer+board outline → link stated motivation → validate if geometry or electrical topology actually changed.
- **Check:** source version, observed delta, claimed failure, whether fix is trace/placement/topology, evidence/test. Record outcomes rather than falsely saying 'this placement alone solved the problem'.
- **Status:** HEURISTIC / design lessons until independent measurements and layout diff.

## Heuristic priority graph (không phải 1 luật cứng)
```text
Mechanical constraints
  ├─→ connectors, antennas, mounting holes [freeze]
  └─→ block floorplan
         ├─→ power hot loops + feedback isolation
         ├─→ MCU + decoupling + crystal/memory [vendor overlay]
         ├─→ RF + keepout/matching
         └─→ analog/sense + isolation
                  ↓
         fanout feasibility + critical routing
                  ↓
         iterated placement + ordinary routing
                  ↓
         ground/pour/review/DFM
```

### Anti-rule: crystal always close
Original `LAYOUT_RULES.md:P05` contained a broad “crystal near pin” suggestion. ESP32-S3 vendor rule RD03 expressly states a **minimum 2.0 mm gap**; updated v0.2 rulebook must replace that broad guidance by `vendor-specific crystal rules take precedence`. This is a concrete example of why unverified tutorial generalizations cannot become HARD rules.

### Minimal placement report per check
```json
{
  "pattern_id": "PT04",
  "applicability": {"device": "ESP32-S3", "vendor_guide": "RD03"},
  "objects": ["U1", "Y1", "clock_pads"],
  "geometry": {"distance_metric": "pad-to-pad", "measured_mm": null},
  "expected": {"relation": "min_clearance", "threshold_mm": 2.0},
  "status": "NEEDS_REVIEW",
  "evidence": "RD03 crystal section; full PCB geometry not supplied",
  "override_reason": null
}
```
