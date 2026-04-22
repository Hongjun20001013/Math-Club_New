#!/usr/bin/env python3
"""
Split Unit_2_Advanced_Math.tex into banks/algebra/2_1.tex … 2_3.tex
at each \\subsection*{2.x} boundary (content after \\begin{document}).

Run from repo root:
  python3 scripts/sync_unit2_slices.py
"""

from __future__ import annotations

import os
import re
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, APP_DIR)
from latex_parser import parse_tex_file  # noqa: E402


def main() -> None:
    master = os.path.join(APP_DIR, "Unit_2_Advanced_Math.tex")
    text = open(master, encoding="utf-8").read()
    if r"\begin{document}" not in text:
        print("Missing \\begin{document}", file=sys.stderr)
        sys.exit(1)
    body = text.split(r"\begin{document}", 1)[1]
    body = body.split(r"\end{document}", 1)[0]
    parts = re.split(r"(?=\\subsection\*\{2\.)", body)
    chunks = parts[1:]
    if len(chunks) != 3:
        print("Expected 3 subsections after split, got", len(chunks), file=sys.stderr)
        sys.exit(1)
    labels = ["2_1", "2_2", "2_3"]
    out_dir = os.path.join(APP_DIR, "banks", "algebra")
    os.makedirs(out_dir, exist_ok=True)
    total = 0
    for lab, chunk in zip(labels, chunks):
        path = os.path.join(out_dir, f"{lab}.tex")
        with open(path, "w", encoding="utf-8") as f:
            f.write(chunk)
        n = len(parse_tex_file(path))
        total += n
        print(f"{lab}: {n} questions -> {path}")
    print("Total:", total)
    if total != len(parse_tex_file(master)):
        print("Slice total does not match master parse count.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
