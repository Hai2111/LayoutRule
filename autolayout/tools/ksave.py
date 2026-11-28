"""ksave.py - ghi file an toan cho moi tool (L76).

save_board(board, path): ghi ra file tam -> kiem tra -> os.replace (nguyen tu).
  Neu tien trinh bi ngat giua chung, file dich cu van nguyen ven, khong bao gio co file dang do.
  Xoa .kicad_pro/.kicad_prl ma pcbnew tu sinh canh file tam/dich (file rac) neu truoc do chua co.
save_image(img, path): tuong tu cho anh PIL.
"""
import os


def _sidecars(path):
    base = path[: -len(".kicad_pcb")] if path.endswith(".kicad_pcb") else path
    return [base + ".kicad_pro", base + ".kicad_prl"]


def save_board(board, path):
    path = path.replace("\\", "/")
    tmp = path[: -len(".kicad_pcb")] + ".__tmp__.kicad_pcb"
    before = {s for s in _sidecars(path) if os.path.exists(s)}
    board.Save(tmp)
    with open(tmp, "rb") as fh:                      # kiem tra file tam day du truoc khi thay the
        fh.seek(max(0, os.path.getsize(tmp) - 8)); tail = fh.read()
    if b")" not in tail:
        raise RuntimeError(f"file tam {tmp} khong ket thuc dung - khong thay the {path}")
    os.replace(tmp, path)
    for s in _sidecars(tmp) + [s for s in _sidecars(path) if s not in before]:
        if os.path.exists(s):
            os.remove(s)
    return path


def save_image(img, path):
    root, ext = os.path.splitext(path)
    tmp = root + ".__tmp__" + ext
    img.save(tmp)
    os.replace(tmp, path)
    return path
