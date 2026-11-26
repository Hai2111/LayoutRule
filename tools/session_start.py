#!/usr/bin/env python3
"""Step 0 of every layout session: review the WHOLE board before editing anything.

  <kicad-python> tools/session_start.py review BOARD.kicad_pcb layout_intent.json --out DIR
  python tools/session_start.py check DIR/SESSION_START.md      # exit 3 until the agent has looked and written

`review` never modifies the board. It needs the .kicad_pro / schematics beside the board so DRC and
schematic parity use the project's own rules. Numbers are geometry screening, not electrical proof.
"""
import argparse
import collections
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
TODO = "TODO"


def ipc_width_mm(amps, rise_c=10.0, oz=1.0):
    """IPC-2221 external-layer width for a given current."""
    area_mil2 = (amps / (0.048 * rise_c ** 0.44)) ** (1 / 0.725)
    return area_mil2 / (1.378 * oz) * 0.0254


def polygon_area(points):
    n = len(points)
    return abs(sum(points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1] for i in range(n))) / 2


def unfinished(report_text):
    """Lines the agent still has to fill in."""
    return [line for line in report_text.splitlines() if line.rstrip().endswith(": " + TODO)]


def kicad_cli():
    exe = Path(sys.executable).with_name("kicad-cli.exe" if sys.platform == "win32" else "kicad-cli")
    return str(exe) if exe.exists() else "kicad-cli"


def run_drc(board, out):
    dj = out / "baseline_drc.json"
    dj.unlink(missing_ok=True)
    subprocess.run([kicad_cli(), "pcb", "drc", "--format", "json", "--severity-all", "--schematic-parity",
                    "--refill-zones", "-o", str(dj), str(board)], capture_output=True)
    if not dj.is_file():
        raise SystemExit("DRC did not run; no baseline, no edit")
    d = json.loads(dj.read_text(encoding="utf-8"))
    count = collections.Counter((v["severity"], v["type"]) for v in d.get("violations", []))
    return d, count


def render(board, out, boxes):
    """Top/bottom KiCad renders plus one crop per named region (top side)."""
    images = []
    for side in ("top", "bottom"):
        png = out / f"board_{side}.png"
        subprocess.run([kicad_cli(), "pcb", "render", "--side", side, "--width", "2000", "--height", "2600",
                        "-o", str(png), str(board)], capture_output=True)
        if png.is_file():
            images.append(png.name)
    top = out / "board_top.png"
    if not top.is_file():
        return images
    import pcbnew
    import wx
    app = wx.App(False)  # noqa: F841  wx.Image needs an app object
    img = wx.Image(str(top))
    w, h = img.GetWidth(), img.GetHeight()
    alpha = img.GetAlphaBuffer() if img.HasAlpha() else None
    data = img.GetDataBuffer()
    bg = bytes(data[0:3])

    def solid(x, y):
        i = y * w + x
        return alpha[i] not in (0, b"\x00") if alpha is not None else bytes(data[3 * i:3 * i + 3]) != bg

    cols = [x for x in range(0, w, 2) if any(solid(x, y) for y in range(0, h, 8))]
    rows = [y for y in range(0, h, 2) if any(solid(x, y) for x in range(0, w, 8))]
    if not cols or not rows:
        return images
    edge = pcbnew.LoadBoard(str(board)).GetBoardEdgesBoundingBox()
    ex, ey, ew, eh = (v * 1e-6 for v in (edge.GetX(), edge.GetY(), edge.GetWidth(), edge.GetHeight()))
    # shortcut: render bbox is taken as the board outline; parts overhanging the edge shift a crop by a few mm
    sx, sy = (cols[-1] - cols[0]) / ew, (rows[-1] - rows[0]) / eh
    for name, (x0, y0, x1, y1) in boxes.items():
        px0 = max(0, int(cols[0] + (x0 - ex) * sx)); py0 = max(0, int(rows[0] + (y0 - ey) * sy))
        px1 = min(w, int(cols[0] + (x1 - ex) * sx)); py1 = min(h, int(rows[0] + (y1 - ey) * sy))
        if px1 - px0 < 20 or py1 - py0 < 20:
            continue
        crop = img.GetSubImage(wx.Rect(px0, py0, px1 - px0, py1 - py0))
        scale = max(1.0, 900 / max(crop.GetWidth(), crop.GetHeight()))
        crop = crop.Scale(int(crop.GetWidth() * scale), int(crop.GetHeight() * scale), wx.IMAGE_QUALITY_HIGH)
        fn = "zoom_" + "".join(c if c.isalnum() else "_" for c in name) + ".png"
        crop.SaveFile(str(out / fn), wx.BITMAP_TYPE_PNG)
        images.append(fn)
    return images


def review(board_path, intent_path, out):
    import pcbnew
    out.mkdir(parents=True, exist_ok=True)
    board_path = Path(board_path).resolve()
    sha = hashlib.sha256(board_path.read_bytes()).hexdigest()
    intent = json.loads(Path(intent_path).read_text(encoding="utf-8"))
    nets = {n: v for n, v in intent.get("nets", {}).items() if isinstance(v, dict)}
    drc, count = run_drc(board_path, out)
    b = pcbnew.LoadBoard(str(board_path))
    mm = 1e-6
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    tracks = [t for t in b.GetTracks() if t.GetClass() != "PCB_VIA"]
    vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    findings = []

    def pos(ref_pad):
        ref, num = ref_pad.split(".", 1)
        cand = [p for p in fps[ref].Pads() if p.GetNumber() == num]
        p = max(cand, key=lambda q: q.GetSize().x * q.GetSize().y)
        return (p.GetPosition().x * mm, p.GetPosition().y * mm)

    L = ["# Session start: whole-board review", "", f"Board: `{board_path.name}`  sha256 `{sha}`", "",
         "## 1. Baseline (project rules, before any edit)", ""]
    errors = sum(n for (s, _), n in count.items() if s == "error")
    unconnected, parity = len(drc.get("unconnected_items", [])), len(drc.get("schematic_parity", []))
    L += [f"DRC errors {errors}, unconnected {unconnected}, schematic parity {parity}", ""]
    L += [f"- {s} {t}: {n}" for (s, t), n in sorted(count.items())]
    L += [f"- parity: {v.get('description', v.get('type'))} " + "; ".join(i.get("description", "") for i in v.get("items", [])) for v in drc.get("schematic_parity", [])]
    if errors or unconnected:
        findings.append(f"HIGH baseline: {errors} DRC errors, {unconnected} unconnected")
    if parity:
        findings.append(f"MED baseline: {parity} schematic parity items")

    # ---- power tree and per-pin copper
    L += ["", "## 2. Power tree", "", "| net | A | IPC width 10C mm | widths used | F mm | B mm | vias |", "|---|---|---|---|---|---|---|"]
    zone_nets = {z.GetNetname() for z in b.Zones()}
    for n, spec in nets.items():
        amps = spec.get("current_a")
        mine = [t for t in tracks if t.GetNetname() == n]
        if not amps or not mine:
            continue
        need = ipc_width_mm(amps)
        widths = sorted({round(t.GetWidth() * mm, 2) for t in mine})
        length = collections.Counter()
        for t in mine:
            length[b.GetLayerName(t.GetLayer())] += t.GetLength() * mm
        L.append(f"| {n} | {amps} | {need:.2f} | {', '.join(map(str, widths))} | {length['F.Cu']:.0f} | {length['B.Cu']:.0f} | {sum(v.GetNetname() == n for v in vias)} |")
        if len(widths) > 3:
            findings.append(f"MED {n}: {len(widths)} different widths on one net")
    L += ["", "### Pins whose widest connected track is below the net's IPC width (pours not credited: look at them)", ""]
    for ref, f in sorted(fps.items()):
        if ref[0] not in "UQLDJ":
            continue
        for p in f.Pads():
            n = p.GetNetname()
            amps = nets.get(n, {}).get("current_a")
            if not amps:
                continue
            touch = [t.GetWidth() * mm for t in tracks if t.GetNetname() == n and (p.HitTest(t.GetStart()) or p.HitTest(t.GetEnd()))]
            if touch and max(touch) + 1e-3 < ipc_width_mm(amps):
                L.append(f"- {ref}.{p.GetNumber()} {n}: {max(touch):.2f} mm, net {amps} A needs {ipc_width_mm(amps):.2f}"
                         + (" (net has a pour)" if n in zone_nets else ""))
                if n not in zone_nets:
                    findings.append(f"HIGH {ref}.{p.GetNumber()} {n}: neck {max(touch):.2f} mm on a {amps} A net, no pour")

    # ---- switching loops
    L += ["", "## 3. Switching loops (pad centres)", ""]
    boxes = {}
    for loop in intent.get("hot_loops", []):
        pts = [pos(p) for p in loop["pads"] if p.split(".")[0] in fps]
        if len(pts) < 3:
            L.append(f"- {loop.get('name')}: pads missing from board")
            findings.append(f"HIGH hot loop {loop.get('name')}: intent pads not found")
            continue
        legs = [math.dist(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
        L.append(f"- {loop.get('name')}: area {polygon_area(pts):.0f} mm2, legs "
                 + ", ".join(f"{loop['pads'][i]}>{loop['pads'][(i + 1) % len(legs)]} {d:.1f}" for i, d in enumerate(legs)))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        boxes[loop.get("name", "loop")] = (min(xs) - 6, min(ys) - 6, max(xs) + 6, max(ys) + 6)
        if max(legs) > 8:
            findings.append(f"HIGH hot loop {loop.get('name')}: longest leg {max(legs):.1f} mm")

    # ---- thermal pads
    L += ["", "## 4. Thermal pads (numbered U/Q pads >= 7 mm2)", ""]
    for ref, f in sorted(fps.items()):
        if ref[0] not in "UQ":
            continue
        for p in f.Pads():
            area = p.GetSize().x * p.GetSize().y * mm * mm
            if area >= 7 and p.GetNumber() and p.GetNetname():
                inside = sum(p.HitTest(v.GetPosition()) for v in vias if v.GetNetname() == p.GetNetname())
                L.append(f"- {ref}.{p.GetNumber()} {p.GetNetname()}: {area:.1f} mm2, {inside} vias inside, pour on net: {p.GetNetname() in zone_nets}")

    # ---- noisy nodes against signals, both layers
    L += ["", "## 5. Signals within 2 mm of a switch-node pad (plan view, either layer)", ""]
    sw = [p for f in fps.values() for p in f.Pads() if nets.get(p.GetNetname(), {}).get("class") == "switch_node"]
    quiet = lambda n: n and nets.get(n, {}).get("class") not in ("power", "gnd", "switch_node")
    near, edge_hits = {}, collections.Counter()
    outline = b.GetBoardEdgesBoundingBox()
    for t in tracks:
        n = t.GetNetname()
        if not quiet(n):
            continue
        a, c = t.GetStart(), t.GetEnd()
        steps = max(2, int(t.GetLength() * mm / 0.25))
        for i in range(steps + 1):
            x, y = a.x + (c.x - a.x) * i / steps, a.y + (c.y - a.y) * i / steps
            if min(x - outline.GetLeft(), outline.GetRight() - x, y - outline.GetTop(), outline.GetBottom() - y) * mm < 1.5:
                edge_hits[n] += t.GetLength() * mm / (steps + 1)
            for p in sw:
                bb = p.GetBoundingBox()
                d = math.hypot(max(bb.GetLeft() - x, 0, x - bb.GetRight()), max(bb.GetTop() - y, 0, y - bb.GetBottom())) * mm - t.GetWidth() * mm / 2
                key = (n, f"{p.GetParentFootprint().GetReference()}.{p.GetNumber()}", b.GetLayerName(t.GetLayer()))
                if d < 2 and d < near.get(key, 9):
                    near[key] = d
    for (n, pad, layer), d in sorted(near.items(), key=lambda kv: kv[1]):
        L.append(f"- {n} ({layer}) to {pad}: {max(d, 0):.2f} mm")
        if d < 1:
            findings.append(f"MED {n} on {layer}: {max(d, 0):.2f} mm from switch pad {pad}")

    # ---- RF / ESD
    L += ["", "## 6. RF / ESD", ""]
    for n, mmlen in sorted(edge_hits.items(), key=lambda kv: -kv[1]):
        if mmlen > 5:
            L.append(f"- {n}: {mmlen:.0f} mm within 1.5 mm of the board edge")
            findings.append(f"MED {n}: {mmlen:.0f} mm along the board edge (ESD)")
    for ref, f in fps.items():
        if any(k in f.GetValue().upper() for k in ("ESP32", "ESP8266", "WROOM", "NRF5")):
            own = {p.GetNetname() for p in f.Pads()}
            bb = f.GetBoundingBox(False)
            under = sorted({t.GetNetname() for t in tracks if t.GetNetname() not in own and (bb.Contains(t.GetStart()) or bb.Contains(t.GetEnd()))})
            L.append(f"- radio module {ref} {f.GetValue()}: foreign nets inside its outline: {', '.join(under) or 'none'}; check antenna keep-out in the images")
            if under:
                findings.append(f"MED {ref}: {len(under)} foreign nets inside the radio module outline")

    # ---- the repository's existing checkers
    L += ["", "## 7. Existing LayoutRule checkers", ""]
    for name, args in (("layout_audit.py", [str(board_path), str(Path(intent_path).resolve())]), ("drc_body_keepout.py", [str(board_path)])):
        r = subprocess.run([sys.executable, str(TOOLS / name), *args], capture_output=True, text=True, errors="replace")
        (out / (name[:-3] + ".txt")).write_text(r.stdout + r.stderr, encoding="utf-8")
        if "Traceback" in r.stderr:
            L.append(f"- {name}: CRASHED, its checks did not run (see {name[:-3]}.txt)")
            findings.append(f"MED checker {name} crashed: that check is missing from this review")
        else:
            fails = sum(line.startswith("FAIL") for line in r.stdout.splitlines())
            L.append(f"- {name}: exit {r.returncode}, {fails} FAIL lines (full output: {name[:-3]}.txt)")

    # ---- major parts for context, then images the agent must open
    for ref, f in fps.items():
        if ref[0] in "UJL":
            bb = f.GetBoundingBox(False)
            boxes.setdefault(ref, (bb.GetLeft() * mm - 5, bb.GetTop() * mm - 5, bb.GetRight() * mm + 5, bb.GetBottom() * mm + 5))
    images = render(board_path, out, boxes)
    L += ["", "## 8. Visual review: open every image, then replace TODO with what you see", ""]
    L += [f"- {img}: {TODO}" for img in images] or [f"- no image could be rendered, review in KiCad: {TODO}"]
    L += ["", "## 9. Findings (fix order). Add the ones only your eyes found, then set the order", ""]
    order = {"HIGH": 0, "MED": 1, "LOW": 2}
    L += [f"- [ ] {f}" for f in sorted(findings, key=lambda s: order[s.split()[0]])]
    L += ["", f"- findings seen only in the images: {TODO}", f"- fix order and reason: {TODO}", ""]
    (out / "SESSION_START.md").write_text("\n".join(L), encoding="utf-8")
    print(f"{out / 'SESSION_START.md'}: {len(findings)} findings, {len(images)} images. Do not edit until `check` passes.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("review"); r.add_argument("board"); r.add_argument("intent"); r.add_argument("--out", default="session_start")
    c = sub.add_parser("check"); c.add_argument("report")
    a = ap.parse_args(argv)
    if a.cmd == "review":
        review(a.board, a.intent, Path(a.out).resolve())
        return 0
    left = unfinished(Path(a.report).read_text(encoding="utf-8"))
    if left:
        print(f"BLOCKED: {len(left)} review lines still {TODO}; do not edit the board yet")
        return 3
    print("OK: whole-board review is written; editing may start")
    return 0


if __name__ == "__main__":
    sys.exit(main())
