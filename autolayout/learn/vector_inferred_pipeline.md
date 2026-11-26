# Quy trình của Vector: suy ra từ dấu vết file (2026-11-26)

Vector từ chối mô tả cách làm, nên tài liệu này dựng lại từ file nó để lại trong
`training/stm8/final/stm8_rgb_usbc/` (`vector-drafts/`, các báo cáo DRC/ERC, các bản board đã lưu).
Đây là suy luận, không phải lời Vector.

## Dòng thời gian

| Giờ | Dấu vết | Việc đã làm |
|---|---|---|
| 14:43 | `stm8/vector-drafts/stm8_dy40-drc.json` | Chạy DRC trên board có sẵn để đánh giá trước khi đụng vào |
| 14:44 | thư mục `final/stm8_rgb_usbc` | Tạo project mới, không sửa đè lên bản gốc |
| 14:47–14:49 | schematic nháp 1–3 + ERC mỗi bản | **Vẽ lại schematic**, mạch giữ nguyên: khổ A4, chia khối chức năng, mỗi khối có tiêu đề nói rõ ý đồ (vd "RGB low-side switches, common-anode LED strip on +5V"). Bản 3 sắp xếp lại vị trí mọi ký hiệu |
| 14:56 | schematic nháp 4 + ERC | **Sửa mạch**: thêm C6 100n ở NRST, C2 1u→100n, D1 → PESD5V0U1UL |
| 14:58 | DRC, BOM có mã linh kiện | Đồng bộ board với schematic, kiểm DRC |
| 15:08 | `reroute-drc.json` | **Sửa bố trí rồi đi lại cục bộ**: đổi chỗ các cụm kênh LED, đặt C6, chỉ đi lại các net bị ảnh hưởng (giữ ~146 đoạn cũ) |
| 15:49 | `pour-drc.json` | Dời và xoay C3 sát chân nguồn U1; đổ đồng GND mặt trên |
| 15:53–15:55 | `via-drc.json`, bản lưu mới | Thêm via khâu GND; dọn lại PWM_B, UART_TX |

## Tư duy suy ra

1. **Hiểu mạch trước khi vẽ.** Vẽ lại schematic thành các khối có tiêu đề ý đồ. Đó là bước "khai báo ý đồ" mà
   `autolayout.infer()` của ta đang đoán ngầm từ netlist.
2. **Sửa mạch trước khi sửa layout.** Lỗi mạch được xử lý ở schematic, không bù bằng đi dây.
3. **Mỗi bước là một bản nháp, kiểm xong mới đi tiếp.** ERC/DRC sau từng bước, báo cáo đặt tên theo bước
   (reroute, pour, via).
4. **Sửa tăng dần, giữ phần tốt.** Không bao giờ xóa sạch dây. Chỉ đi lại net bị ảnh hưởng bởi thay đổi.
5. **Thứ tự mối quan tâm:** đúng mạch → nối đủ → bố trí hợp lý (cụm giống nhau, tụ sát chân) →
   chất lượng GND (đổ đồng 2 mặt, via khâu) → dọn dẹp.
6. **Placement là biến số.** Dời, xoay, hoán vị linh kiện bất cứ khi nào việc đó gỡ được vấn đề.

## So với quy trình của ta

| Vector | autolayout | Việc cần làm |
|---|---|---|
| Khai báo ý đồ từng khối | Đoán ngầm trong `infer()` | Xuất `plan.json` thành các khối có tên và ý đồ, người đọc được |
| Sửa tăng dần | Xóa sạch, đi lại từ đầu | Tác tử quan sát + gỡ/đi lại cục bộ (`tools/improve.py` là bước đầu) |
| Kiểm sau mỗi bước | DRC cuối | DRC sau mỗi tầng |
| Bước chất lượng GND | Chỉ có zone B.Cu | Thêm đổ đồng F.Cu + via khâu sau khi đi dây xong |
| Dời tụ sát chân | Placement cố định | Tác tử được phép dời/xoay |
