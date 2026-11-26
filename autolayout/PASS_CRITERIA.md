# Tieu chi DAT / KHONG DAT (chot truoc khi chay, 2026-11-23 17:19)
Owner chi nhan 1 ket luan DAT/KHONG DAT. Moi muc duoi day phai dat.

## A. Ban STM8 (autolayout, khong pre-route tay)
1. KiCad DRC: 0 loi (canh bao silk duoc phep), 0 net chua noi.
2. Tu review quan he (self_review R1-R3): khong track P1/P2 duoi than IC; khong track P1/P2 bi kep giua pad 2 linh kien tru ngoai le dau pad connector; thu tu cap nguon dung (TVS->bulk->tu->chan).
3. Via khong GND <= trung vi cua ref x 1.5 (via/100mm), B.Cu share <= p90 cua ref.

## B. Ref benchmark (cac board ref 2 lop 40-80 linh kien, xoa track roi cho autolayout route lai)
1. Ti le net route duoc trung binh >= 90%.
2. Tren cac board da route tron ven: via/100mm <= 1.5 x ban cua nguoi.

## C. Bai luyen tap bus2ic
1. Cac bai can thang hang (dy <= 1 mm, cung chieu): 0 via, 0 net loi.
