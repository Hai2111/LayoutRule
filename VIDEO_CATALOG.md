# VIDEO CATALOG — Phil's Lab / Altium Academy

**Last review: 2026-11-15.** Trọng tâm: sắp xếp linh kiện (placement), routing, real PCB design review.

**Quy ước trạng thái:** `M` = kiểm tra **thông tin nguồn gốc, mô tả và chapter** trên YouTube/FEDEVEL/Altium, **chưa xác minh toàn bộ lời thoại/khung hình**. `T` = transcript đọc/đối chiếu đầy đủ (chưa có). `V` = video thực sự xem/kiểm tra trực tiếp đầy đủ (chưa có). **Không coi M là “đã xem hết”.**

Các “bài học” bên dưới là **tóm tắt chủ đề xác minh được + suy luận kỹ thuật vận dụng có ghi rõ**, không phải trích nguyên văn người nói. Mỗi entry có liên kết kiểm tra được, mốc chapter khi tìm thấy, rule mapping.

## Tổng quan
- **35 nguồn video/webinar được tra cứu**: **29 Phil's Lab + 6 Altium Academy/Altium**. Trạng thái: **35 M, 0 T, 0 V**.
- **Ưu tiên đọc lại:** #137 (2-layer), #60 (buck), #65 (KiCad), #41 (Altium full), #144 (QFN), Altium placement, Altium decoupling, Altium AI vs human.
- Chưa kiểm kê toàn bộ upload của 2 kênh; đây là danh sách theo chủ đề, không phải tuyên bố “toàn bộ video trên Internet”.
- Rule ID tham chiếu [LAYOUT_RULES.md](LAYOUT_RULES.md).

## A. Phil's Lab — placement/routing thực hành (ưu tiên cao)

| ID | Video / link | Chapter liên quan | Tóm tắt có thể xác minh từ nguồn | Rules | Status |
|---|---|---|---|---|---|
| PL01 | [#65 KiCad 6 STM32 PCB Design Full Tutorial](https://www.youtube.com/watch?v=aVUqaB0IMh4) | 52:11 setup; 57:03 MCU/caps/crystal; 1:03:15 USB/SWD; 1:12:11 nguồn; 1:19:54–1:32:45 route | Quy trình đầy đủ board STM32 2-layer: bố trí linh kiện theo khối trước, route decoupling/crystal/signal/power rồi DRC và xuất fab. Đây là **ví dụ một workflow**, không phải thứ tự bắt buộc mọi board. | P02,P04,P05,R02,R03,G05 | M |
| PL02 | [#60 Switching Regulator PCB Design](https://www.youtube.com/watch?v=AmfLhT5SntE) | 02:23 topology/loops; 06:12 rules; 09:57 layout; 17:32 routing | Minh họa layout/routing buck với trọng tâm vòng dòng chuyển mạch và giảm nhiễu/EMI. Quy tắc vận dụng: đánh dấu các dòng có di/dt lớn trước khi placement. | P03,R03,G02 | M |
| PL03 | [#137 2-Layer PCB Design Tips](https://home.fedevel.com/blog/2-layer-pcb-design-tips-phils-lab-137) | 11:24 placement; 14:40 power routing order; 16:49 signal/GND jumps; 23:06 RF | Đặc thù board 2 lớp: phân lớp, vị trí linh kiện, thứ tự đi power, signal và cách bảo toàn return path khi không có internal GND plane. | A03,P02,R04,R05,R06 | M |
| PL04 | [#5 KiCad STM32 + RF + USB](https://www.youtube.com/watch?v=14_jh3nLSsU) | 19:24 rough; 20:37 placement order; 21:30 ESD; 21:42 RF; 23:24 stackup; 26:43–29:40 route | Ví dụ ưu tiên linh kiện critical, tách USB/power/RF/MCU, xử lý ESD và RF routing cùng impedance. Có **correction IREF** trong description: không được bê schematic trực tiếp khi chưa đọc errata. | P02,P06,P07,R07,R11 | M |
| PL05 | [#41 STM32 PCB Design — Altium Full Walkthrough](https://www.fedevel.com/blog/stm32-pcb-design-complete-walkthrough-altium-designer-jlcpcb-phils-lab-41) | 1:20:00 rough; 1:25:36 MCU; 1:41:25 sensor; 1:45:05 USB; 1:55:19 routing; 2:16:39 planes; 2:21:15 power | Lộ trình thiết kế 4-layer có rough/fine placement, sensor, USB, route, planes và DRC. Dùng học cách phối hợp thứ tự placement và route. | P02,P04,R02,R05,G05 | M |
| PL06 | [#11 KiCad STM32 + USB + Buck Full Tutorial](https://fedevel.com/blog/kicad-stm32-usb-buck-converter-pcb-design-and-jlcpcb-assembly-update-phils-lab-11) | Video dài, chapter nguồn mô tả schematic/layout/routing/fab | Ví dụ STM32F4 4-layer có buck + USB, từ thiết kế tới sản xuất; thích hợp làm case study end-to-end. | P03,R03,G05 | M |
| PL07 | [#15 KiCad STM32 Hardware Overview](https://www.fedevel.com/blog/kicad-stm32-hardware-design-an-overview-in-20-minutes-phils-lab-15) | 12:21 layout; 13:15 power; 14:18 MCU/caps/crystal; 16:19 USB pair | Bản ngắn cho 2-layer STM32: vị trí khối nguồn, MCU, decoupling, routing USB và kiểm tra DRC. | P04,P05,R07,G05 | M |
| PL08 | [#1 Flight Control System Hardware](https://fedevel.com/blog/flight-control-system-design-hardware-and-pcb-design-with-kicad-phils-lab-1) | 11:00 layout; 12:37 routing; 20:23 sectioning; 22:25 oscillators; 24:08 current; 24:44 order/vias | Board flight controller thực tế, nhấn mạnh phân khối, oscillator, nguồn dòng lớn, thứ tự đi dây và stitching vias. | P02,P05,R04,G03 | M |
| PL09 | [#144 QFN PCB Design Tips](https://www.youtube.com/watch?v=hOamoJ15hmA) | 20:20 exposed pad vias; 23:59 fanout/caps; 31:08 examples; 35:26 vs stackup | Layout QFN gồm footprint, exposed pad, fanout, decoupling theo cấu trúc chân và stack-up; không mặc định via-in-pad hợp lệ. | P04,P09,R08 | M |
| PL10 | [#139 PCB Chip Antenna Hardware Design](https://courses.fedevel.com/blog/pcb-chip-antenna-hardware-design-phils-lab-139) | 12:33 match; 20:26 footprint; 22:31 PCB | Chip antenna: chọn loại, matching, footprint và vùng PCB liên quan. Đặc biệt kiểm tra keepout và reference theo datasheet. | P07,R11,A04 | M |
| PL11 | [#78 Mini 6-Layer Mixed-Signal Walkthrough](https://fedevel.com/blog/mini-6-layer-mixed-signal-hardware-design-walkthrough-phils-lab-78) | 05:35 PSU; 13:38 analog front end; 16:02 PCB | Case study board 6 lớp âm thanh tích hợp MCU, bộ nhớ, USB HS, RS485, ADC/codec, analog. Dùng làm ví dụ phân tách chức năng và luồng tín hiệu. | A05,P08,R02 | M |

## B. Phil's Lab — review thật, quy tắc và SI/EMI

| ID | Video / link | Chapter liên quan | Tóm tắt có thể xác minh từ nguồn | Rules | Status |
|---|---|---|---|---|---|
| PL12 | [#63 Design Review: Spartan-7](https://www.fedevel.com/blog/design-review-spartan-7-fpga-schematic-pcb-phils-lab-63) | 08:30 PCB | Review schematic/PCB KiCad FPGA, lỗi thường gặp và routing; chưa có transcript để gán lỗi cụ thể. | A01,G07 | M |
| PL13 | [#70 Design Review: Wireless Keyboard Adapter](https://fedevel.com/blog/design-review-schematic-pcb-phils-lab-70) | 09:20 PCB | Review design thực tế KiCad của bộ adapter keyboard, phân tích common errors và routing. | G07 | M |
| PL14 | [#76 RF + MCU Design Review](https://www.fedevel.com/blog/rf-mcu-pcb-design-review-phils-lab-76) | 14:03 PCB; 15:34 MCU/caps; 19:05 RF; 23:51 transfer vias; 24:36 USB pair | Review STM32WB + RF antenna + USB; đụng đến stack-up, stitching, impedance và vị trí decoupling. | P04,P07,R05,R07,G03 | M |
| PL15 | [#81 Review: Buck + STM32 + Relays](https://fedevel.com/blog/design-review-buck-stm32-peripherals-phils-lab-81) | 12:48 PCB; 17:12 buck | Review schematic/board MCU nguồn switching và relay, dành ưu tiên xem kỹ placement và routing buck. | P03,R03,G07 | M |
| PL16 | [#85 FPGA PCB Design Review](https://fedevel.com/blog/fpga-pcb-design-review-phils-lab-85) | 16:04 stack; 18:48 buck; 27:17 caps; 28:16 transfer via; 30:10 pour | Review Spartan-7 board có buck, memory, USB: đánh giá stackup, nguồn, via, decoupling, diff pairs và copper. | A03,P03,P09,R05,G02 | M |
| PL17 | [#131 PCB Design Final Touches](https://home.fedevel.com/blog/pcb-design-final-touches-tips-checklist-phils-lab-131) | 05:30 pour; 12:52 teardrop; 14:48 transfer via; 29:51 DRC; 31:49 Gerber; 33:40 footprint | Checklist pre-fab: pours, stitching, voids, mask, silk, vias, mechanical, Gerber, footprints và manufacturing notes. | G02,G03,G05 | M |
| PL18 | [#170 PCB Design Rules 101](https://www.youtube.com/watch?v=zeH3WbMWvdg) | 06:29 impedance; 13:29 clearance/width; 29:59 priorities; 32:36 net class; 38:43 DRC | Cách lập rule từ giới hạn nhà máy, constraints, priority, net class, room và DRC. | A02,A03,R01,R13 | M |
| PL19 | [#176 PCB Copper Pours 101](https://www.youtube.com/watch?v=Ao2HUjjhlmQ) | 04:02 rules; 10:52 priority; 11:49 thermal; 22:50 balance | Polygon copper, thứ tự đổ, thermal relief, copper balance và hatch; không thể mặc định solid polygon tốt cho mọi hàn/đường dòng. | G02,G04 | M |
| PL20 | [#175 PCB Via Fencing & Edge Plating](https://www.youtube.com/watch?v=fQ1BTyvXfKw) | 03:31 basics; 09:10 fencing; 22:54 edge plating | Giải pháp và đánh đổi via fencing/edge plating để kiểm soát phát xạ điện từ ở mép PCB. | G03 | M |
| PL21 | [#56 PCB Stack-Up/Build-Up](https://www.fedevel.com/blog/pcb-stack-up-and-build-up-phils-lab-56) | 12:09 golden rules; 13:58 PWR+GND; 14:34 4-layer; 17:05 transfer vias | Cách chọn stack-up theo field/return path, signal integrity, và khả năng sản xuất, không chỉ theo số lớp. | A03,R05,G03 | M |
| PL22 | [#64 PCB Design for EMI & SI](https://www.fedevel.com/blog/pcb-design-for-emi-si-phils-lab-64) | 04:08 edge speed; 09:20 stack; 12:00 tracks; 14:47 vias; 16:08 planes | EMI/SI phụ thuộc edge rate, stack-up, termination, vias, reference plane và phân cách; không suy từ tần số clock đơn lẻ. | A03,R05,R10,R11 | M |
| PL23 | [#25 High-Speed PCB Design Tips](https://fedevel.com/blog/high-speed-pcb-design-tips-phils-lab-25) | 02:40 plane; 04:42 impedance; 06:48 length/spacing; 07:53 via; 09:35 diff | Tổng quan routing tốc độ cao với plane tham chiếu, trace geometry, via và differential pairs. | R05,R07,R10 | M |
| PL24 | [#112 PCB Traces 101](https://fedevel.com/blog/pcb-traces-101-phils-lab-112) | 11:33 power; 14:09 PDN L; 16:43 planes; 23:01 guidelines | Định kích thước trace theo dẫn điện, nhiệt, điện cảm, trở kháng, propagation delay và current handling. | R04,R08,R11 | M |
| PL25 | [#83 Differential Pairs Basics](https://courses.fedevel.com/blog/differential-pairs-pcb-design-basics-phils-lab-83) | 09:55 impedance; 12:55 width/gap; 14:16 match; 18:10 terminate | Diff pair cần thiết kế width/gap, kiểm soát trở kháng, matching và termination theo interface. | R07 | M |
| PL26 | [#156 PCB Crosstalk Basics](https://fedevel.com/blog/pcb-crosstalk-basics-tips-tricks-phils-lab-156) | 16:30 measurement; 22:56 edge speed; 26:26 mitigation | Crosstalk, thực nghiệm đo, ảnh hưởng rise/fall và cách giảm bằng routing/spacing. | R10 | M |
| PL27 | [#59 FPGA/SoC + DDR PCB Tips](https://www.fedevel.com/blog/fpga-soc-ddr-pcb-design-tips-phils-lab-59) | 07:04 stack; 13:30 BGA/caps; 16:12 timing; 22:00 DDR term | Layout FPGA/DDR phụ thuộc pinout, decoupling, fanout, timing và termination. | P09,R02,R07 | M |
| PL28 | [#115 Interfacing FPGAs with DDR](https://www.fedevel.com/blog/interfacing-fpgas-with-ddr-memory-phils-lab-115) | 15:37 pinout; 18:51 constraints; 22:52 PCB tips | Ràng buộc từ pin banks/DDR interface nên được xác minh trước khi placement; không để router quyết định sai pin chức năng. | A01,P10 | M |
| PL29 | [#5 STM32 + RF + USB, supplemental routing review](https://www.youtube.com/watch?v=14_jh3nLSsU) | 29:40 RF/USB; 36:53 guard; 38:45 gap | **Không phải video riêng:** đây là phần tiếp của PL04 để bookmark kiểm tra kỹ RF, guard/clearance và via-in-pad. **Không cộng là nguồn video riêng.** | R11,G03 | M |

## C. Altium Academy / Altium — placement, routing, phản biện

| ID | Video / link | Chapter liên quan | Tóm tắt có thể xác minh từ nguồn | Rules | Status |
|---|---|---|---|---|---|
| AA01 | [PCB Component Placement: Placement of Components](https://www.youtube.com/watch?v=lswq83QKMvU) | Nguồn mô tả area-based, move/drag, coordinate, locking, cross-select | Công cụ placement theo nhóm, vị trí chính xác, khóa phần tử và đối chiếu schematic. Chỉ ra workflow thao tác, không tự quyết định topology điện. | P01,P02,P10 | M |
| AA02 | [PCB Routing: Setting Preferences](https://www.youtube.com/watch?v=vQWHRFmlopE) | Conflict resolution; routing behavior; glossing; width sourcing | Thiết lập chế độ route, xử lý va chạm, trace glossing và nguồn width theo rule. Chuyển ý tưởng sang cấu hình router KiCad, không bê nguyên shortcut Altium. | A02,R08,R13 | M |
| AA03 | [Does Decoupling Capacitor Placement Actually Matter?](https://www.youtube.com/watch?v=SSpyE9CP97g) | 09:27 placement; 11:28 trace L; 15:17 spreading L; 17:13 planes | Phản biện quy tắc “tụ càng gần càng tốt”: hiệu quả phụ thuộc package và plane/trace inductance. Không bỏ ưu tiên placement trong board hai lớp. | P04,R05 | M |
| AA04 | [Decoupling Capacitor Routing: Vias vs Traces](https://www.youtube.com/watch?v=1O48JZX8j5g) | 05:25 pin; 06:30 layout; 08:21 inductance; 12:17 trace vs via | Khoảng cách pin và geometry quyết định via-to-plane hay trace ngắn có tổng L tốt hơn; video đưa các ví dụ định lượng trong bối cảnh cụ thể (không lấy số đó làm hằng số thiết kế). | P04,R05 | M |
| AA05 | [AI PCB Layout vs. Human Design: The Honest Truth](https://www.youtube.com/watch?v=qX29OWSYTmI) | 03:38 human; 08:36 switch layout; 10:10 DRC; 12:36 placement; 18:47 black-box | So sánh board buck 4 lớp cùng schematic; mô tả video nêu AI đặt linh kiện chưa tốt, route khó hiểu và 168 lỗi DRC. Bài học: kiểm chứng kỹ ý đồ và constraints, không tin hình ảnh “đẹp” hay route thành công đơn thuần. | P03,R03,G07 | M |
| AA06 | [How to Route in CircuitStudio](https://www.youtube.com/watch?v=PeB0RF6eyqU) | Mô tả single/multiple traces và các routing modes | Hướng dẫn công cụ route một/nhiều trace, có thể tham khảo chiến lược tương tác; ít giá trị kỹ thuật hơn 5 video trên. | R08 | M |

## D. Nguồn bổ trợ chưa tính là video/channel chính
- [Altium PCB Component Placement Webinar](https://resources.altium.com/webinars/pcb-component-placement) — nội dung chính: mechanical constraints, keepout, preliminary placement, assembly, SI và nguồn; dùng đối chiếu P01/P02.
- [Altium official placement and routing tutorial](https://www.altium.com/documentation/altium-designer/tutorial/component-placement-routing-board) — tài liệu text, không tính trong số video.
- [Phil's Lab video index](https://www.phils-lab.net/videos) — hỗ trợ tìm tiếp, không tính là video.

## Next verification queue
1. **PL03, PL02, PL01, PL05, AA01** — xem/nghe từng chapter placement/routing, ghi ví dụ BEFORE/AFTER, con số constraint nếu xuất hiện.
2. **AA03, AA04, PL09** — làm rõ khi nào tụ cần sát chân pin, khi nào plane/via thay thế được.
3. **PL14–PL16, AA05** — xác nhận những lỗi cụ thể của từng bản PCB trong video; ghi snapshot/case if permitted.
4. **PL19–PL23** — chuyển sang các kiểm tra machine-checkable, đặc biệt return path trên board 2-layer.

### Audit format khi hoàn tất xem/đọc transcript
`video_id | source_url | last_checked_utc | status M/T/V | watched_ranges | key_claim | chapter_ts | rule_id | implementation_check | counterexample_or_exception`

**Không nâng M → T/V nếu không thật sự có bằng chứng đầy đủ.** Không tái phát tán nguyên văn transcript có bản quyền.
