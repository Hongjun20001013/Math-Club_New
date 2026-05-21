#!/usr/bin/env python3
"""
Exit 0 iff each banks/geometry/4_*.tex file matches the corresponding slice of
Unit_4_Geometry.tex (line ranges must stay in sync when editing the master).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "Unit_4_Geometry.tex"
SLICES: tuple[tuple[str, int, int], ...] = (
    ("4_1.tex", 114, 374),
    ("4_2.tex", 375, 574),
    ("4_3.tex", 575, 840),
    ("4_4.tex", 841, 1092),
)


def main() -> int:
    lines = MASTER.read_text(encoding="utf-8").splitlines(keepends=True)
    err = 0
    for name, a, b in SLICES:
        bank = ROOT / "banks" / "geometry" / name
        if not bank.is_file():
            print("Missing", bank, file=sys.stderr)
            err = 1
            continue
        want = "".join(lines[a - 1 : b])
        got = bank.read_text(encoding="utf-8")
        if want != got:
            print(f"MISMATCH: {name} vs Unit_4_Geometry.tex lines {a}-{b}", file=sys.stderr)
            err = 1
    if err:
        return 1
    print("OK: Unit 4 bank TeX files match Unit_4_Geometry.tex slices.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
