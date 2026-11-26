"""strip_tracks.py IN.kicad_pcb OUT.kicad_pcb - bo moi (segment ...) va (via ...) o muc cao nhat, giu footprint + zone.
Chay bang python thuong (khong can pcbnew). Khong sua file goc."""
import sys

src = open(sys.argv[1], encoding="utf-8").read()
out, i, n, removed = [], 0, len(src), {"segment": 0, "via": 0, "arc": 0}
while i < n:
    for kw in ("(segment", "(via", "(arc"):
        if src.startswith(kw, i) and src[i + len(kw)] in " \t\r\n" and (i == 0 or src[i - 1] in "\t\n "):
            # chi cat khi nam o muc 1 (thut 1 tab)
            ls = src.rfind("\n", 0, i) + 1
            if src[ls:i] == "\t":
                depth, j = 0, i
                while True:
                    c = src[j]
                    if c == '"':
                        j = src.index('"', j + 1)
                    elif c == "(":
                        depth += 1
                    elif c == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                removed[kw[1:]] += 1
                # xoa ca dong (tab dau + newline sau)
                while out and out[-1] == "\t":
                    out.pop()
                i = j + 1
                if i < n and src[i] == "\n":
                    i += 1
                break
    else:
        out.append(src[i])
        i += 1
        continue
open(sys.argv[2], "w", encoding="utf-8").write("".join(out))
print("removed", removed)
