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
            if (not isinstance(command, list) or "--layers" not in command or
                    command[command.index("--layers")+1] != layer):
                raise ValueError(f"{layer} KiCad layer selection not evidenced")
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
        (self.output/"stage_results.json").write_text(
            json.dumps({"schema_version":1,"events":self.events},
                       ensure_ascii=False,indent=2,default=str),encoding="utf-8")
        cards=[]
        for event in self.events:
            def pretty(x):
                return html.escape(json.dumps(x,ensure_ascii=False,indent=2,default=str))
            pictures=[]
            for layer,asset in event["screenshots"].items():
                uri=asset["image"] if isinstance(asset,dict) and "image" in asset else asset
                try:
                    rel=Path(uri).resolve().relative_to(self.output).as_posix()
                except (ValueError,TypeError):
                    continue
                pictures.append(
                    f'<figure><figcaption>{html.escape(layer)}</figcaption>'
                    f'<img src="{html.escape(rel,quote=True)}" alt="KiCad {html.escape(layer)}"/></figure>')
            cards.append(
                f'<section><h3>Iteration {event["iteration"]} · {html.escape(event["stage"])}'
                f' — {html.escape(event["status"])}</h3>'
                f'<p>{html.escape(event["reason"])}</p>'
                + "".join(pictures)
                +f'<details><summary>Input / Output / Metrics / Findings</summary>'
                f'<pre>{pretty({k:event[k] for k in ("inputs","outputs","metrics","findings")})}</pre>'
                "</details></section>")
        html_doc=('<!doctype html><html lang="vi"><meta charset="utf-8">'
                  '<title>LayoutRule: evidence per stage</title>'
                  '<style>body{max-width:1100px;margin:2rem auto;font:15px system-ui;'
                  'padding:0 1rem}section{border:1px solid #8885;border-radius:10px;'
                  'padding:1rem;margin:1rem 0}img{max-width:100%;max-height:520px;'
                  'border:1px solid #aaa}figure{display:inline-block;width:46%;'
                  'vertical-align:top;margin:1%}pre{white-space:pre-wrap;overflow:auto}'
                  '</style><h1>LayoutRule — bằng chứng từng công đoạn</h1>'
                  '<p>Trạng thái mô tả thao tác; không đồng nghĩa layout đạt chuẩn điện.</p>'
                  + "".join(cards)+'</html>')
        (self.output/"STAGE_REPORT.html").write_text(html_doc,encoding="utf-8")
