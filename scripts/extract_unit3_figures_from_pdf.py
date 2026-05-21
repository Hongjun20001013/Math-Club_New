#!/usr/bin/env python3
"""
Extract embedded Unit 3 figures from ``Unit_3_PS_DA.pdf`` into ``static/unit3``.

The PDF embeds exactly five workbook figures, in document order:

1. ``5.jpg`` - Unit 3.2 line graph
2. ``1.png`` - Unit 3.3 box plots
3. ``2.png`` - Unit 3.3 dot plots
4. ``3.png`` - Unit 3.3 histograms
5. ``4.jpg`` - Unit 3.3 dot plot

If your global Pillow has the wrong architecture on macOS, run in a fresh venv:

    python3 -m venv .venv-unit3
    . .venv-unit3/bin/activate
    pip install pypdf pillow
    python scripts/extract_unit3_figures_from_pdf.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = ROOT / "Unit_3_PS_DA.pdf"
OUT_DIR = ROOT / "static" / "unit3"

TARGET_NAMES = [
    "5.jpg",
    "1.png",
    "2.png",
    "3.png",
    "4.jpg",
]


def _sniff_ext(raw: bytes) -> str:
    if raw[:2] == b"\xff\xd8":
        return ".jpg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    return ".bin"


def main() -> int:
    pdf_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_PDF
    if not pdf_path.is_file():
        print("PDF not found:", pdf_path, file=sys.stderr)
        return 1
    try:
        from pypdf import PdfReader
    except ImportError:
        print("Install pypdf and pillow: pip install pypdf pillow", file=sys.stderr)
        return 1

    reader = PdfReader(str(pdf_path))
    streams: list[bytes] = []
    for page in reader.pages:
        for image in getattr(page, "images", []):
            streams.append(image.data)

    if len(streams) != len(TARGET_NAMES):
        print(
            f"Expected {len(TARGET_NAMES)} embedded images in {pdf_path.name}, found {len(streams)}.",
            file=sys.stderr,
        )
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for raw, target in zip(streams, TARGET_NAMES):
        ext = _sniff_ext(raw)
        expected = Path(target).suffix.lower()
        if ext != ".bin" and ext != expected:
            target = Path(target).with_suffix(ext).name
        dest = OUT_DIR / target
        dest.write_bytes(raw)
        print("wrote", dest, len(raw))
    print("Done:", len(TARGET_NAMES), "files ->", OUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
