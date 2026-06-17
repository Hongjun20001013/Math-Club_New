#!/usr/bin/env python3
"""
Render middle-level placement diagram macros from ``Placement_Middle_Level.tex``
into PNG files under ``static/placement_middle/``.

Unlike Unit 4 (embedded raster ``\\includegraphics``), this workbook draws figures
with TikZ. There are no separate embedded images in the PDF, so we compile each
``\\newcommand`` diagram block with the same preamble as the workbook, then
``pdfcrop`` + Ghostscript (300 DPI PNG) for crisp figures that match the print/PDF layout.

Usage:
  python3 scripts/extract_middle_level_figures_from_pdf.py
  python3 scripts/extract_middle_level_figures_from_pdf.py /path/to/Placement_Middle_Level.tex
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEX = ROOT / "Placement_Middle_Level.tex"
OUT_DIR = ROOT / "static" / "placement_middle"
RENDER_DPI = 300

# Diagram macros used in the 100-item placement (document order).
DIAGRAM_MACROS = [
    "rectmixed",
    "quarterSquare",
    "rectangleSixFour",
    "numberLineTwoEightSix",
    "rulerST",
    "rectRuler",
    "segmentABC",
    "lShapeArea",
    "pentagonSquare",
    "triPrism",
    "similarTriangles",
    "trapezoidSolid",
    "baseSolid",
]

STANDALONE_PREAMBLE = r"""\documentclass[border=2pt]{standalone}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{amsmath,amssymb}
\usepackage{tikz}
\usepackage{xcolor}
\usetikzlibrary{arrows.meta,calc,patterns,positioning}
\definecolor{npPurple}{RGB}{118,83,255}
\definecolor{npDeep}{RGB}{76,54,180}
\definecolor{npLilac}{RGB}{246,243,255}
\definecolor{npLine}{RGB}{206,196,255}
\definecolor{npInk}{RGB}{31,31,38}
"""


def _strip_diagram_chips(block: str) -> str:
    """Remove Q-number chips from TikZ (question # is already in the UI chrome)."""
    return re.sub(
        r"\\begin\{scope\}\[shift=\{[^}]*\}\]\\diagramchip\{[^}]*\}\\end\{scope\}",
        "",
        block,
    )


def _extract_diagram_block(tex: str, *, strip_chips: bool = True) -> str:
    chip_i = tex.find(r"\newcommand{\diagramchip}")
    longdiv_i = tex.find(r"\newcommand{\longdiv}")
    if chip_i < 0 or longdiv_i < 0 or longdiv_i <= chip_i:
        raise RuntimeError("Could not locate diagram macro block in tex preamble")
    block = tex[chip_i:longdiv_i]
    return _strip_diagram_chips(block) if strip_chips else block


def _render_tex_body(tex_path: Path, body: str, job: str, work: Path, png_name: str) -> Path:
    tex = tex_path.read_text(encoding="utf-8")
    diagram_block = _extract_diagram_block(tex)
    longdiv_block = ""
    ld_i = tex.find(r"\newcommand{\longdiv}")
    if ld_i >= 0:
        ld_end = tex.find(r"\newcommand{\verticalmul}", ld_i)
        if ld_end > ld_i:
            longdiv_block = tex[ld_i:ld_end]
    doc = STANDALONE_PREAMBLE + diagram_block + longdiv_block + r"\begin{document}" + body + r"\end{document}"
    work.mkdir(parents=True, exist_ok=True)
    tex_file = work / f"{job}.tex"
    pdf_file = work / f"{job}.pdf"
    crop_pdf = work / f"{job}-crop.pdf"
    png_file = OUT_DIR / png_name

    tex_file.write_text(doc, encoding="utf-8")
    for cmd in (
        ["pdflatex", "-interaction=nonstopmode", "-output-directory", str(work), str(tex_file)],
        ["pdfcrop", str(pdf_file), str(crop_pdf)],
    ):
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"{' '.join(cmd[:2])} failed for {job}: {err}")

    gs_out = work / f"{job}-render.png"
    gs = subprocess.run(
        [
            "gs",
            "-dNOPAUSE",
            "-dBATCH",
            "-sDEVICE=pngalpha",
            f"-r{RENDER_DPI}",
            f"-sOutputFile={gs_out}",
            str(crop_pdf),
        ],
        capture_output=True,
        text=True,
    )
    if gs.returncode != 0 or not gs_out.is_file():
        err = (gs.stderr or gs.stdout or "").strip()
        raise RuntimeError(f"ghostscript failed for {job}: {err}")
    png_file.write_bytes(gs_out.read_bytes())

    if not png_file.is_file() or png_file.stat().st_size < 200:
        raise RuntimeError(f"PNG missing or too small for {job}")
    return png_file


def _render_macro(tex_path: Path, macro: str, work: Path) -> Path:
    return _render_tex_body(tex_path, f"\\{macro}", macro, work, f"{macro}.png")


def _collect_longdiv_calls(tex: str) -> list[tuple[str, str]]:
    return re.findall(r"\\longdiv\{([^{}]*)\}\{([^{}]*)\}", tex)


def main() -> int:
    tex_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_TEX
    if not tex_path.is_file():
        print("TeX source not found:", tex_path, file=sys.stderr)
        return 1

    tex = tex_path.read_text(encoding="utf-8")
    missing = [m for m in DIAGRAM_MACROS if f"\\newcommand{{\\{m}}}" not in tex]
    if missing:
        print("Missing diagram macros in tex:", ", ".join(missing), file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    work = OUT_DIR / "_build"
    if work.exists():
        for p in work.iterdir():
            if p.is_file():
                p.unlink()
    else:
        work.mkdir(parents=True)

    for macro in DIAGRAM_MACROS:
        out = _render_macro(tex_path, macro, work)
        print("wrote", out, out.stat().st_size)

    for divisor, dividend in _collect_longdiv_calls(tex):
        name = f"longdiv_{divisor}_{dividend}.png"
        out = _render_tex_body(
            tex_path,
            f"\\longdiv{{{divisor}}}{{{dividend}}}",
            f"longdiv_{divisor}_{dividend}",
            work,
            name,
        )
        print("wrote", out, out.stat().st_size)

    total = len(DIAGRAM_MACROS) + len(_collect_longdiv_calls(tex))
    print("Done:", total, "files ->", OUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
