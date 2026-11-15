# REFERENCE DESIGN CATALOG — hãng sản xuất + PCB công khai

Updated: 2026-11-15. Mục đích: **lấy minh chứng bố trí linh kiện/routing** từ PCB thực thay vì chỉ học khẩu hiệu. Tài liệu này **không** chứa PCB source gốc có giấy phép hạn chế.

## Trạng thái bằng chứng
- **VISUAL_LAYOUT_INSPECTED**: đã xem hình layout thực tế (screenshot PCB/gerber); phạm vi xem ghi rõ.
- **VENDOR_GUIDE_READ**: đã đối chiếu mục layout guidelines của hãng; không khẳng định đã kiểm tra toàn bộ PCB.
- **ARTIFACT_LISTED**: trang nguồn xác nhận có PCB/Gerber/zip nhưng chưa tải, parse hoặc xem đầy đủ.
- **SOURCE_PROJECT_LINKED**: có project công khai gắn với chuỗi tutorial, chưa audit chính xác geometry.
- **CAD_GEOMETRY_PARSED**: trích xuất programmatic tọa độ linh kiện, pad, layer, net; **chưa có**.
- **BOARD_ELECTRICALLY_VALIDATED**: có đo kiểm của chính người review; **chưa có**. Board hãng là reference, không có nghĩa layout nào cũng sao chép được.

## Các reference ưu tiên, không trùng video
| ID | Reference thiết kế | Nguồn gốc / file | Mức xác minh | Pattern khả thi | Cảnh báo |
|---|---|---|---|---|---|
| RD01 | TI TPS62933 synchronous buck 2-layer | [Datasheet §12.1–12.2 (PDF)](https://www.ti.com/lit/ds/symlink/tps62933.pdf) — trang in 40,41; [EVM](https://www.ti.com/tool/TPS62933EVM) | **VISUAL_LAYOUT_INSPECTED** (top/bottom hình 12-2/3 + đọc §12.1) | VIN bypass với VIN–GND sát IC; SW tới cuộn cảm; FB divider gần FB và xa SW; local BST/SS/RT, copper GND thấp L. | Chỉ áp dụng topology và IC thích hợp; recommendation 2oz, 2-layer là cho TPS62933, không suy thành thông số chung. |
| RD02 | TI TPS62933 single-layer EMI example | [TI E2E reference example](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/1064106/faq-tps62933-how-to-achieve-single-layer-pcb-layout-with-improved-emi) | **VISUAL_LAYOUT_INSPECTED** (hình E2E) | Placement theo chân IC nhằm giảm loop và routing trên 1 lớp; đánh giá pinout trước khi tối ưu net length. | Không kết luận board 1 lớp nào cũng đạt EMC. Cùng IC với RD01, không đếm là thiết kế độc lập. |
| RD03 | Espressif ESP32-S3 chip/module | [Official PCB Layout Design](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html) | **VENDOR_GUIDE_READ** (power, crystal, RF, flash, USB, module) | Crystal/series Rs/ground, 0201 RF CLC, RF antenna edge/keepout; USB pair + contiguous return, SPI series resistor near MCU. | **Quan trọng**: crystal guideline hãng đề nghị khoảng cách từ clock pin **ít nhất 2.0 mm**; không dùng luật “crystal sát chân nhất”. Các số RF/USB từ S3 không mặc định cho S3-WROOM module hay MCU khác. |
| RD04 | Nordic nRF54L15 DK PCA10156 | [nRF54L15 DK hardware files](https://www.nordicsemi.com/Products/Development-hardware/nRF54L15-DK/Hardware-files) / [hardware guide](https://docs.nordicsemi.com/r/bundle/ug_nrf54l15_dk/page/ug/nrf54l15_dk/intro/intro.html) | **ARTIFACT_LISTED** | Schematic+layout+Gerber+BOM dành cho RF/MCU, clock, supply, SWD; so sánh revision DK 1.0.0 và radio reference rev 0.8. | DK 1.0.0 gồm nhiều circuit chỉ phục vụ debug/measurement; không sao chép toàn bộ placement sang sản phẩm pin nhỏ. ZIP chưa parse. |
| RD05 | Analog Devices EVAL-AD5940BIOZ Rev B (impedance 4-wire) | [User guide + design files](https://wiki.analog.com/resources/eval/user-guides/eval-ad5940/hardware/eval-ad5940bioz); [PCB layer artwork PDF](https://wiki.analog.com/_media/resources/eval/user-guides/eval-ad5940/hardware/08-049988-01-b.pdf) | **VISUAL_LAYOUT_INSPECTED** (PDF trang 1 silkscreen, trang 2 layer-1 copper; chưa xem tất cả layer) | Board có các vùng connector/sensor, electrode/RTIA/CTIA/RCAL, power, MCU/interface; nên gán tuyến nhạy cảm trước bulk signal. | Là EVAL shield cho BIA, không chứng minh mọi clearance/guard cho HoofVision; chưa tracing từng net từ schematics. |
| RD06 | Analog Devices EVAL-AD5940ELCZ Rev A | [Electrochemical shield guide + PCB layout, BOM, Gerbers](https://wiki.analog.com/resources/eval/user-guides/eval-ad5940/hardware/eval-ad5940elcz) | **ARTIFACT_LISTED** | Review đường electrode CE/RE/SE/DE, BNC buffer high-Z, analog supply, cáp đo, RCAL; so sánh BIOZ. | ADI cảnh báo cáp crocodile có ký sinh R/C ảnh hưởng đo trở kháng; layout không giải quyết toàn bộ lỗi đo. |
| RD07 | Raspberry Pi RP2040 Minimal KiCad | [RP2040 Product Information Portal / Minimal-KiCAD (ZIP)](https://pip.raspberrypi.com/categories/814-rp2040) / [RP2040 design guide](https://www.raspberrypi.com/documentation/microcontrollers/microcontroller-chips.html) | **ARTIFACT_LISTED** | PCB KiCad mẫu 2-layer: MCU–flash–crystal–decoupling–USB/power, rất phù hợp tạo gold-standard placement test. | ZIP trên product portal chưa đọc/parse thành tọa độ trong phiên này. |
| RD08 | FEDEVEL custom keyboard (RP2040) | [GitHub hardware source](https://github.com/FEDEVEL/custom-keyboard), [interactive PCB](https://oshwlab.com/robertferanec/custom-keyboard), [Part 3 placement](https://home.fedevel.com/blog/tutorial-custom-diy-keyboard-design-and-build-part-3-pcb-component-placement), [Part 4 routing](https://fedevel.com/blog/tutorial-custom-diy-keyboard-design-and-build-part-4-pcb-layout), [Part 5 improve](https://home.fedevel.com/blog/tutorial-custom-diy-keyboard-design-and-build-part-5-pcb-layout-improvement) | **SOURCE_PROJECT_LINKED** | Paired reference: mechanical placement→MCU periphery→fanout→critical USB→power→GND stitching→DRC; dùng so sánh before/after. | License ghi CC BY-NC-SA 4.0: chỉ lưu liên kết và tóm tắt, không nhập file source của người khác vào repo này mà bỏ qua license. |
| RD09 | Espressif development kits (ESP32-S3 and others) | [Official esp-dev-kits](https://github.com/espressif/esp-dev-kits) | **ARTIFACT_LISTED** (docs/schematics có sẵn; không xác nhận PCB source layout cho mọi board) | Đối chiếu pinout, USB, EN/BOOT, regulator, module orientation. | Repo chỉ đảm bảo hardware resources/schematic theo từng devkit, không suy ra có edit-able PCB của tất cả. |

## Findings có thể nâng lên kiểm tra ngay
- **RD01 / TI TPS62933 §12.1**: đặt IC, inductor, input/output capacitors trên cùng layer; CIN 0.1uF sát cặp VIN/GND; SW ngắn/rộng khi thực tế cho phép; FB divider gần FB và tách khỏi SW; FB sensing về đầu ra bằng tuyến riêng. Đây là **hướng dẫn hãng theo IC**, không phải công thức chung cho mọi buck.
- **RD03 / Espressif**: 2-layer ưu tiên TOP components/signals và BOTTOM GND liên tục; crystal cách clock pin tối thiểu 2.0 mm theo trang này, không via trên 2 clock traces; SPI series Rs near ESP32-S3; module antenna ở edge/nhô ra; RF 50Ω trace và USB 90Ω differential ±10% khi áp dụng giao diện tương ứng.
- **RD05 / ADI 4-wire BIA**: đã xác nhận trên artwork có nhiều connector/pad electrode/guard reference và đường trace; chưa có bằng chứng đủ để áp số clearance cụ thể hoặc thứ tự điện cực cho HoofVision.
- **RD08 / FEDEVEL keyboard**: chapter placement và routing cung cấp **trình tự học placement + iterative refinement**, không chứng minh trình tự đó tối ưu cho mọi MCU board.

## Chỉ tiêu kiểm tra nâng mức tiếp theo
1. Với file KiCad/Altium/EasyEDA có phép truy cập: tải bản *gốc*, ghi SHA, layer stack, dimensions, placement xy/rotation, pad-net, via positions, copper pour, clearance và screenshot.
2. Gắn functional blocks với refdes; chụp ROI (region of interest) quanh power/clock/AFE/USB/RF.
3. Trích **quan hệ hình học**: cùng mặt, gần cổng, trước/sau topology, trace length, loop area, reference continuity, khoảng cách tới nhiễu.
4. Viết **phản ví dụ + giới hạn** và đối chiếu manual/datasheet; chỉ lúc đó nâng pattern geometry thành test tự động.
5. Không dùng một reference design để đánh giá tất cả thiết kế nếu không cùng IC/package/stackup/revision.

**Ngày ghi nhận không có nghĩa toàn bộ file CAD/ZIP được tải hoặc layout đã được mô phỏng.**
