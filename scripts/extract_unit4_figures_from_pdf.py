#!/usr/bin/env python3
"""
Extract embedded raster images from ``Unit_4_Geometry.pdf`` into ``static/unit4/``
as ``6.jpg`` … ``24.png`` (document-embedded order). This matches what your LaTeX
build placed in the PDF—use it whenever figures must be **pixel-identical** to the
original workbook.

Requires a working **arm64** Pillow with pypdf (if your global Python has x86_64
Pillow, use a fresh venv: ``python3 -m venv .venv && . .venv/bin/activate && pip install pypdf pillow``).

Usage:
  python3 scripts/extract_unit4_figures_from_pdf.py
  python3 scripts/extract_unit4_figures_from_pdf.py /path/to/Unit_4_Geometry.pdf

Optional schematic SVGs for other layouts: ``scripts/gen_unit4_geometry_svgs.py``.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = ROOT / "Unit_4_Geometry.pdf"
OUT_DIR = ROOT / "static" / "unit4"

# Must match \\includegraphics{…} basenames under banks/geometry (document order in PDF).
TARGET_NAMES = [
    "6.jpg",
    "7.jpg",
    "8.jpg",
    "9.jpg",
    "10.png",
    "11.png",
    "12.jpg",
    "13.jpg",
    "14.png",
    "16.jpg",
    "17.jpg",
    "18.jpg",
    "19.png",
    "20.png",
    "21.png",
    "22.png",
    "23.png",
    "24.png",
]


def main() -> int:
    pdf_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_PDF
    if not pdf_path.is_file():
        print("PDF not found:", pdf_path, file=sys.stderr)
        return 1
    try:
        from pypdf import PdfReader
    except ImportError:
        print("Install pypdf: pip install pypdf", file=sys.stderr)
        return 1

    r = PdfReader(str(pdf_path))
    streams: list[bytes] = []
    for page in r.pages:
        if not hasattr(page, "images"):
            continue
        for im in page.images:
            streams.append(im.data)

    if len(streams) != len(TARGET_NAMES):
        print(
            f"Expected {len(TARGET_NAMES)} embedded images in PDF, found {len(streams)}. "
            "If the workbook was rebuilt, re-check ordering in this script.",
            file=sys.stderr,
        )
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for raw, tname in zip(streams, TARGET_NAMES):
        ext = Path(tname).suffix.lower()
        if raw[:2] == b"\xff\xd8" and ext != ".jpg":
            tname = Path(tname).with_suffix(".jpg").name
        elif raw[:8] == b"\x89PNG\r\n\x1a\n" and ext != ".png":
            tname = Path(tname).with_suffix(".png").name
        (OUT_DIR / tname).write_bytes(raw)
        print("wrote", OUT_DIR / tname, len(raw))
    print("Done:", len(TARGET_NAMES), "files ->", OUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
