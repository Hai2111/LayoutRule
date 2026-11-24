#!/usr/bin/env python3
"""KiCad 10 native copper SVG export -> real PNG rasterization.

KiCad 10 kicad-cli supports pcb export svg but not pcb export png.
Never render synthetic PCB geometry: PNG pixels come from the KiCad SVG.
Requires CairoSVG (Python package with Cairo runtime), or Inkscape on PATH.
"""
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from visual_stage_report import png_metadata


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rasterize_svg(svg, png, *, width_px=1600):
    svg,png=Path(svg).resolve(),Path(png).resolve()
    errors=[]
    try:
        import cairosvg
    except ImportError:
        errors.append("CairoSVG not installed")
    else:
        try:
            cairosvg.svg2png(url=str(svg),write_to=str(png),output_width=width_px)
            if png.is_file():
                return {"rasterizer":"CairoSVG","rasterizer_exit_code":0,
                        "rasterizer_command":["cairosvg.svg2png",str(svg),str(png),
                                              f"output_width={width_px}"]}
        except Exception as exc:
            errors.append(f"CairoSVG failed: {str(exc)[:300]}")
            png.unlink(missing_ok=True)
    inkscape = os.environ.get("INKSCAPE_BIN") or shutil.which("inkscape")
    if inkscape:
        cmd=[str(inkscape),str(svg),"--export-type=png",
             f"--export-filename={png}",f"--export-width={width_px}"]
        try:
            result=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
            if result.returncode==0 and png.is_file():
                return {"rasterizer":"Inkscape","rasterizer_exit_code":0,
                        "rasterizer_command":cmd}
            errors.append("Inkscape failed: "+(result.stderr or result.stdout)[-400:])
        except (OSError,subprocess.TimeoutExpired) as exc:
            errors.append(f"Inkscape error: {exc}")
    raise RuntimeError("No working SVG-to-PNG rasterizer. Install CairoSVG or "
                       "Inkscape (or set INKSCAPE_BIN). "+
                       " | ".join(errors))


def export_layer(board,layer,directory,*,kicad_cli="kicad-cli",width_px=1600):
    if layer not in ("F.Cu","B.Cu"):
        raise ValueError(f"unsupported copper export layer {layer}")
    board,dirpath=Path(board).resolve(),Path(directory).resolve()
    if not board.is_file() or board.suffix!=".kicad_pcb":
        raise ValueError("KiCad source board missing")
    if width_px<320 or width_px>12000:
        raise ValueError("unreasonable PNG export width")
    dirpath.mkdir(parents=True,exist_ok=True)
    for stale in (*dirpath.glob("*.png"),*dirpath.glob("*.svg")):
        stale.unlink()
    common=f"{layer[0]}.SilkS,{layer[0]}.CrtYd,Edge.Cuts"
    cmd=[str(kicad_cli),"pcb","export","svg",
         "--exclude-drawing-sheet","--mode-single",
         "--layers",layer,"--common-layers",common,
         "--output",str(dirpath),str(board)]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
    svgs=sorted(dirpath.glob("*.svg"))
    if p.returncode!=0 or len(svgs)!=1:
        raise RuntimeError(f"KiCad 10 SVG {layer} export failed or ambiguous: "
                           + (p.stderr or p.stdout)[-600:])
    source_svg=svgs[0]
    png=dirpath/(layer.replace(".","_")+".png")
    render=rasterize_svg(source_svg,png,width_px=width_px)
    meta=png_metadata(png)
    return {
        "layer":layer,"board_sha256":sha(board),
        "source_svg":str(source_svg),"svg_sha256":sha(source_svg),
        "png_path":str(png),"png_sha256":meta["sha256"],
        "dimensions_px":[meta["width"],meta["height"]],
        "export_command":cmd,"export_exit_code":p.returncode,
        **render,
    }
