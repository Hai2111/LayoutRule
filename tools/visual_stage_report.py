#!/usr/bin/env python3
"""Auditable image provenance, pinpointed ROI and per-stage HTML/JSON trail.

PNG pixels are exported by KiCad. SVG crops embed those pixels and cannot
invent traces. This validates transport/provenance, not the agent's diagnosis.
"""
import base64
import hashlib
import html
import json
import struct
import zlib
from datetime import datetime, timezone
from pathlib import Path


LAYERS = ("F.Cu", "B.Cu")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def png_metadata(path):
    """Validate PNG chunks, CRC, dimensions and existence of image payload."""
    raw = Path(path).read_bytes()
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG file")
    i, width, height, seen_idat, ended = 8, None, None, False, False
    while i + 12 <= len(raw):
        length = struct.unpack(">I", raw[i:i+4])[0]
        if length > 100_000_000 or i+12+length > len(raw):
            raise ValueError("invalid PNG chunk length")
        tag = raw[i+4:i+8]
        chunk = raw[i+8:i+8+length]
        crc = struct.unpack(">I", raw[i+8+length:i+12+length])[0]
        if (zlib.crc32(tag+chunk) & 0xffffffff) != crc:
            raise ValueError("PNG CRC mismatch")
        if tag == b"IHDR":
            if length != 13 or width is not None:
                raise ValueError("invalid/duplicate PNG header")
            width, height = struct.unpack(">II", chunk[:8])
        elif tag == b"IDAT":
            seen_idat = True
        elif tag == b"IEND":
            ended = True
            i += 12 + length
            break
        i += 12 + length
    if not (width and height and width <= 30000 and height <= 30000
            and seen_idat and ended and i == len(raw)):
        raise ValueError("incomplete or invalid PNG")
    return {"width":width, "height":height, "sha256":hashlib.sha256(raw).hexdigest()}


def validate_capture(board, observation, *, require_provenance=True):
    """Verify same board and layer-specific export command attestations."""
    board = Path(board).resolve()
    board_sha = sha(board)
    if observation.get("board_sha256") != board_sha:
        raise ValueError("observer PCB SHA differs from routed board")
    images = observation.get("images", {})
    evidence = observation.get("image_evidence", {})
    result = {}
    for layer in LAYERS:
        if layer not in images or not Path(images[layer]).is_file():
            raise ValueError(f"missing {layer} KiCad copper export")
        image = Path(images[layer]).resolve()
        meta = png_metadata(image)
        if require_provenance:
            proof = evidence.get(layer)
            if not isinstance(proof, dict):
                raise ValueError(f"missing {layer} export provenance")
            if (proof.get("board_sha256") != board_sha or
                    proof.get("layer") != layer or
                    proof.get("png_sha256") != meta["sha256"] or
                    proof.get("export_exit_code") != 0):
                raise ValueError(f"{layer} image provenance mismatch")
            command = proof.get("export_command", [])
            if (not isinstance(command, list) or len(command)<7
                    or command[1:4] != ["pcb","export","svg"]
                    or "--layers" not in command
                    or command.index("--layers")+1 >= len(command)
                    or command[command.index("--layers")+1] != layer
                    or Path(command[-1]).resolve()!=board):
                raise ValueError(f"{layer} KiCad SVG layer/source selection not evidenced")
            svg_file=Path(proof.get("source_svg",""))
            if (not svg_file.is_file() or sha(svg_file)!=proof.get("svg_sha256")
                    or "<svg" not in svg_file.read_text(encoding="utf-8")[:2000]
                    or proof.get("rasterizer_exit_code")!=0
                    or not proof.get("rasterizer")
                    or Path(proof.get("png_path","")).resolve()!=image):
                raise ValueError(f"{layer} SVG-to-PNG provenance chain incomplete")
        result[layer] = {"image":str(image), **meta,
                         "board_sha256":board_sha,
                         "provenance_status":"CHECKED" if require_provenance else "UNVERIFIED"}
    return result


def validate_findings(plan, obs):
    """Require an explicit, checkable locality claim, not vague 'trace ugly'."""
    if not plan.get("actions"):
        return []
    findings = plan.get("findings")
    if not isinstance(findings, list) or not 1 <= len(findings) <= 8:
        raise ValueError("nonempty action plan needs 1..8 localized findings")
    refs = set(obs.get("footprints", {}))
    nets = {x.get("net") for x in obs.get("tracks", []) if isinstance(x, dict)}
    for fp in obs.get("footprints", {}).values():
        for pad in fp.get("pads", []):
            nets.add(pad.get("net"))
    for index, item in enumerate(findings):
        if not isinstance(item, dict):
            raise ValueError(f"findings[{index}] must be object")
        layer, roi = item.get("layer"), item.get("roi")
        if layer not in LAYERS:
            raise ValueError(f"findings[{index}] invalid layer")
        if not (isinstance(roi,list) and len(roi)==4
                and all(isinstance(n,(float,int)) and not isinstance(n,bool) for n in roi)
                and 0 <= roi[0] < roi[2] <= 1 and 0 <= roi[1] < roi[3] <= 1):
            raise ValueError(f"findings[{index}] invalid normalized ROI")
        for key in ("problem","reason","expected_change"):
            if not isinstance(item.get(key),str) or not item[key].strip():
                raise ValueError(f"findings[{index}] missing {key}")
        ref,net = item.get("ref"),item.get("net")
        if not (ref or net):
            raise ValueError(f"findings[{index}] needs a footprint ref or existing net")
        if ref and ref not in refs:
            raise ValueError(f"findings[{index}] unknown footprint {ref}")
        if net and net not in nets:
            raise ValueError(f"findings[{index}] unknown net {net}")
    return findings


def roi_svg(image_path, roi, output):
    """Actual KiCad pixels cropped by SVG viewport, preserving original pixels."""
    image_path,output=Path(image_path),Path(output)
    info=png_metadata(image_path)
    w,h=info["width"],info["height"]
    x0,y0,x1,y1=roi
    left,top=round(w*x0),round(h*y0)
    cw,ch=max(1,round(w*(x1-x0))),max(1,round(h*(y1-y0)))
    b64=base64.b64encode(image_path.read_bytes()).decode("ascii")
    svg=(f'<svg xmlns="http://www.w3.org/2000/svg" '
         f'width="{cw}" height="{ch}" viewBox="0 0 {cw} {ch}">'
         f'<image x="{-left}" y="{-top}" width="{w}" height="{h}" '
         f'href="data:image/png;base64,{b64}"/>'
         f'<rect x="1" y="1" width="{max(1,cw-2)}" height="{max(1,ch-2)}" '
         f'fill="none" stroke="#f97316" stroke-width="2"/>'
         "</svg>")
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(svg,encoding="utf-8")
    return {"path":str(output.resolve()),"source_image_sha256":info["sha256"],
            "roi":roi,"crop_size_px":[cw,ch]}


class StageReport:
    def __init__(self, output):
        self.output=Path(output).resolve()
        self.output.mkdir(parents=True,exist_ok=True)
        self.events=[]

    def add(self, stage, status, *, iteration=0, reason="", inputs=None,
            outputs=None, metrics=None, screenshots=None, findings=None):
        entry={"timestamp_utc":datetime.now(timezone.utc).isoformat(),
               "iteration":iteration,"stage":stage,"status":status,
               "reason":reason,"inputs":inputs or {},"outputs":outputs or {},
               "metrics":metrics or {},"screenshots":screenshots or {},
               "findings":findings or []}
        self.events.append(entry)
        self.save()
        return entry

    def save(self):
        # Full machine-readable evidence remains intact; only the owner-facing
        # HTML is intentionally condensed and progressive-disclosure based.
        (self.output/"stage_results.json").write_text(
            json.dumps({"schema_version": 1, "events": self.events},
                       ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        def esc(value):
            return html.escape(str(value), quote=True)

        def asset_path(asset):
            uri = asset.get("image") if isinstance(asset, dict) else asset
            if not isinstance(uri, str):
                return None
            try:
                return Path(uri).resolve().relative_to(self.output).as_posix()
            except ValueError:
                return None

        def pictures(event, layers, label):
            if not event:
                return ""
            parts = []
            for layer in layers:
                asset = event.get("screenshots", {}).get(layer)
                rel = asset_path(asset)
                if rel:
                    parts.append('<figure><figcaption>' + esc(label+" · "+layer)
                                 + '</figcaption><img loading="lazy" src="'
                                 + esc(rel) + '" alt="' + esc(label+" "+layer)
                                 + '"></figure>')
            return "".join(parts)

        def metric(event, key):
            if not event:
                return "—"
            value = event.get("metrics", {}).get(key)
            return str(value) if isinstance(value, (int, float)) else "—"

        initial = next((e for e in self.events
                        if e["stage"] == "BASELINE_IMAGE_AND_DRC"), None)
        final = next((e for e in reversed(self.events)
                      if e["stage"] == "FINAL_INTERNAL_RESULT"), None)
        latest_image = final or next(
            (e for e in reversed(self.events)
             if e["stage"] in ("IMAGE_CAPTURE_AND_DRC", "BASELINE_IMAGE_AND_DRC")),
            None)
        preflight = next((e for e in reversed(self.events)
                          if e["stage"] == "REFERENCE_PREFLIGHT"), None)
        blocked = bool(preflight and preflight["status"] == "BLOCKED")
        verdict = ("BỊ CHẶN — thiếu bằng chứng" if blocked else
                   "CHỜ REVIEW — chưa nghiệm thu" if final else
                   "ĐANG XỬ LÝ — chưa có kết quả cuối")
        decisions = [e for e in self.events
                     if e["stage"] == "BEFORE_AFTER_EVALUATION"]
        kept = sum(e["status"] == "KEEP" for e in decisions)
        rolled = sum(e["status"] == "ROLLBACK" for e in decisions)
        attempts = max((e["iteration"] for e in self.events), default=0)
        recent_findings = [f for e in reversed(self.events)
                           if e["stage"] == "AGENT_VISUAL_DIAGNOSIS"
                           for f in e.get("findings", [])]

        # Only meaningful results are visible by default; raw substage details
        # and all screenshots remain expandable and fully traceable.
        rows = []
        for n in sorted({e["iteration"] for e in self.events if e["iteration"] > 0}):
            events = [e for e in self.events if e["iteration"] == n]
            evaluation = next((e for e in reversed(events)
                               if e["stage"] == "BEFORE_AFTER_EVALUATION"), None)
            diagnosis = next((e for e in events
                              if e["stage"] == "AGENT_VISUAL_DIAGNOSIS"), None)
            failure = next((e for e in reversed(events)
                            if e["stage"] in ("ITERATION_FAILURE", "ROLLBACK")), None)
            result = evaluation or failure or diagnosis or events[-1]
            problem = (diagnosis.get("findings", [{}])[0].get("problem", "—")
                       if diagnosis and diagnosis.get("findings") else "—")
            before = result.get("inputs", {}).get("before", {})
            after = result.get("outputs", {}).get("after", {})
            change = ("DRC: " + str(before.get("drc_errors", "—")) + " → "
                      + str(after.get("drc_errors", "—")) + "; Nối: "
                      + str(before.get("unconnected", "—")) + " → "
                      + str(after.get("unconnected", "—"))
                      if evaluation else "Không có phép so sánh hoàn chỉnh")
            rows.append("<tr><td>"+str(n)+"</td><td>"+esc(problem[:85])
                        +"</td><td>"+esc(change)+"</td><td><strong>"
                        +esc(result["status"])+"</strong></td></tr>")
        if not rows:
            rows.append('<tr><td colspan="4">Chưa có lượt thử.</td></tr>')

        focus = []
        for item in recent_findings[:3]:
            target = item.get("ref") or item.get("net") or "không rõ"
            focus.append('<li><strong>'+esc(str(target))+'</strong> — '
                         +esc(item.get("problem", "Chưa mô tả"))
                         +' <small>(giả thuyết, chưa xác nhận)</small></li>')
        if not focus:
            focus.append("<li>Chưa có lỗi định vị được để trình bày.</li>")

        stage_details = []
        for index, event in enumerate(self.events, 1):
            images = []
            for name, asset in event.get("screenshots", {}).items():
                rel = asset_path(asset)
                if rel:
                    images.append('<figure><figcaption>'+esc(name)+'</figcaption>'
                                  '<img loading="lazy" src="'+esc(rel)+'" alt="'
                                  +esc(name)+'"></figure>')
            raw = {k:event[k] for k in ("inputs", "outputs", "metrics", "findings")}
            stage_details.append(
                '<details class="step"><summary>#'+str(index)+' · Lượt '
                +str(event["iteration"])+' · '+esc(event["stage"])+' — '
                +esc(event["status"])+'</summary><p>'+esc(event["reason"])
                +'</p><div class="photos">'+''.join(images)+'</div><pre>'
                +esc(json.dumps(raw, ensure_ascii=False, indent=2, default=str))
                +'</pre></details>')

        style = (
            "body{max-width:1020px;margin:30px auto;padding:0 18px;"
            "font:15px system-ui,sans-serif;line-height:1.55;color:#202124}"
            "h1{font-size:23px;margin-bottom:5px}h2{font-size:18px;margin-top:26px}"
            ".sub{color:#555}.summary{border:1px solid #bbb;border-radius:10px;"
            "padding:15px 18px;background:#fafafa}"
            ".stats{display:flex;gap:14px;flex-wrap:wrap}.stats span{border:1px solid #ccc;"
            "border-radius:7px;padding:7px 12px}.photos{display:flex;gap:12px;flex-wrap:wrap}"
            "figure{flex:1 1 280px;margin:0}img{display:block;max-width:100%;max-height:360px;"
            "border:1px solid #aaa;object-fit:contain}figcaption{font-weight:600;"
            "padding:7px 0}table{width:100%;border-collapse:collapse}"
            "td,th{border-bottom:1px solid #ddd;padding:9px;text-align:left}"
            "th{background:#f1f1f1}details{border-top:1px solid #ddd;padding:8px 0}"
            "summary{cursor:pointer;font-weight:500}pre{white-space:pre-wrap;"
            "overflow-wrap:anywhere;background:#f7f7f7;padding:12px}"
            ".step{margin-left:10px}.notice{color:#6b4c00}"
        )
        page = (
            '<!doctype html><html lang="vi"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>LayoutRule — Báo cáo dễ đọc</title><style>'+style+'</style>'
            '<h1>LayoutRule · Báo cáo layout</h1>'
            '<p class="sub">Một trang tóm tắt; chi tiết từng công đoạn được ẩn bên dưới.</p>'
            '<div class="summary"><strong>Kết quả: '+esc(verdict)+'</strong>'
            '<div class="stats"><span>Lượt thử: '+str(attempts)+'</span>'
            '<span>Giữ: '+str(kept)+'</span><span>Rollback: '+str(rolled)+'</span>'
            '<span>DRC: '+metric(latest_image, "drc_errors")+'</span>'
            '<span>Chưa nối: '+metric(latest_image, "unconnected")+'</span>'
            '<span>Via: '+metric(latest_image, "via_count")+'</span></div></div>'
            '<h2>1. Ảnh PCB trước / sau (F.Cu)</h2>'
            '<div class="photos">'+pictures(initial, ("F.Cu",), "Trước")
            +pictures(latest_image, ("F.Cu",), "Sau / mới nhất")+'</div>'
            '<details><summary>Xem thêm ảnh lớp B.Cu</summary><div class="photos">'
            +pictures(initial, ("B.Cu",), "Trước")
            +pictures(latest_image, ("B.Cu",), "Sau / mới nhất")
            +'</div></details>'
            '<h2>2. Lỗi đáng chú ý</h2><ul>'+''.join(focus)+'</ul>'
            '<h2>3. Các lần thử và quyết định</h2>'
            '<table><thead><tr><th>Lượt</th><th>Vấn đề</th>'
            '<th>DRC / kết nối trước → sau</th><th>Kết quả</th>'
            '</tr></thead><tbody>'+''.join(rows)+'</tbody></table>'
            '<p class="notice">Lỗi do agent khoanh là giả thuyết. Giảm DRC/via '
            'không tự chứng minh chất lượng điện hoặc sửa đúng lỗi.</p>'
            '<details><summary>Chi tiết kỹ thuật — '
            +str(len(self.events))+' công đoạn (bấm để mở)</summary>'
            +''.join(stage_details)+'</details>'
            '<p class="sub">Bằng chứng đầy đủ: stage_results.json. '
            'Chỉ chủ dự án được nghiệm thu bản cuối.</p></html>'
        )
        (self.output/"STAGE_REPORT.html").write_text(page, encoding="utf-8")
