#!/usr/bin/env python3
"""Split Unit_3_PS_and_Stats.tex into banks/problem_solving/3_1.tex … 3_7.tex at \\subsection*{3.x markers."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "Unit_3_PS_and_Stats.tex"
OUTDIR = ROOT / "banks" / "problem_solving"


def main() -> int:
    if not MASTER.is_file():
        print("Missing", MASTER, file=sys.stderr)
        return 1
    text = MASTER.read_text(encoding="utf-8")
    idx = [m.start() for m in re.finditer(r"\\subsection\*\{3\.\d", text)]
    if len(idx) != 7:
        print("Expected 7 Unit 3 subsections, found", len(idx), file=sys.stderr)
        return 1
    OUTDIR.mkdir(parents=True, exist_ok=True)
    for si, start in enumerate(idx):
        end = idx[si + 1] if si + 1 < len(idx) else len(text)
        chunk = text[start:end]
        out = OUTDIR / f"3_{si + 1}.tex"
        out.write_text(chunk, encoding="utf-8")
        print("Wrote", out.relative_to(ROOT), len(chunk), "chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
