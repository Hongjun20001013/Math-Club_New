#!/usr/bin/env python3
"""
Split the master Unit_1_Algebra.tex into banks/algebra/1_1.tex … 1_5.tex
at each \\subsection*{1.x} boundary (1.1 is everything before \\subsection*{1.2}).

Run from repo root after editing Unit_1_Algebra.tex:
  python3 scripts/sync_unit1_slices.py
"""

from __future__ import annotations

import os
import re
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, APP_DIR)
from latex_parser import parse_tex_file  # noqa: E402


def main() -> None:
    master = os.path.join(APP_DIR, "Unit_1_Algebra.tex")
    text = open(master, encoding="utf-8").read()
    parts = re.split(r"(?=\\subsection\*\{1\.)", text)
    if len(parts) != 5:
        print("Expected 5 parts after split, got", len(parts), file=sys.stderr)
        sys.exit(1)
    labels = ["1_1", "1_2", "1_3", "1_4", "1_5"]
    out_dir = os.path.join(APP_DIR, "banks", "algebra")
    os.makedirs(out_dir, exist_ok=True)
    total = 0
    for lab, chunk in zip(labels, parts):
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
