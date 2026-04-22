#!/usr/bin/env python3
"""
Build data/unit2_supplement.json from Novel Prep Answer.tex (Unit 2 tables).
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, List, Union

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(APP_DIR, "data", "unit2_supplement.json")

# Default if Answer.tex not beside repo (user can set NOVEL_PREP_ANSWER_TEX)
_DEFAULT_ANSWER = os.path.join(
    os.path.expanduser("~"),
    "Downloads",
    "SAT_CB_Bank_Question",
    "Answer.tex",
)


def _norm_letter(s: str) -> Union[str, None]:
    s = s.strip().upper()
    if len(s) == 1 and s in "ABCD":
        return s
    return None


def _token_to_cell(tok: str) -> Union[str, dict[str, Any]]:
    t = tok.strip()
    if not t:
        raise ValueError("empty token")
    let = _norm_letter(t)
    if let:
        return let
    if re.search(r"\bor\b", t, re.I):
        parts = [p.strip() for p in re.split(r"\s+or\s+", t, flags=re.I) if p.strip()]
        if len(parts) >= 2:
            return {"canonical": parts[0], "alternates": parts[1:]}
    # comma-separated alternates (decimals / fractions)
    bits = [b.strip() for b in t.split(",") if b.strip()]
    if not bits:
        raise ValueError(tok)
    if len(bits) == 1:
        return bits[0]
    # Prefer fraction as canonical when present
    fracs = [b for b in bits if "/" in b and re.fullmatch(r"[-+]?[\d.]+/[\d.]+", b.replace(" ", ""))]
    if fracs:
        can = fracs[-1]
        alts = [b for b in bits if b != can]
        return {"canonical": can, "alternates": alts}
    return {"canonical": bits[0], "alternates": bits[1:]}


def _extract_table_rows(subtex: str) -> List[str]:
    rows: List[str] = []
    for line in subtex.splitlines():
        line = line.strip()
        if line.startswith("Q") and "&" in line:
            rows.append(line.rstrip("\\").strip())
    return rows


def _row_to_cells(row: str) -> List[str]:
    # Split on & but keep Qn: patterns
    parts = row.split("&")
    cells: List[str] = []
    for p in parts:
        p = p.strip()
        m = re.match(r"^(Q\d+):\s*(.+)$", p, re.I)
        if not m:
            continue
        cells.append(m.group(2).strip())
    return cells


def parse_unit2_answer_tex(path: str) -> dict[str, List[Any]]:
    text = open(path, encoding="utf-8").read()
    m1 = re.search(
        r"\\subsubsection\*\{2\.1[^}]*\}(.*?)\\subsubsection\*\{2\.2",
        text,
        re.S,
    )
    m2 = re.search(
        r"\\subsubsection\*\{2\.2[^}]*\}(.*?)\\subsubsection\*\{2\.3",
        text,
        re.S,
    )
    m3 = re.search(
        r"\\subsubsection\*\{2\.3[^}]*\}(.*?)\\(?:newpage|\\subsection\*)",
        text,
        re.S,
    )
    if not (m1 and m2 and m3):
        print("Could not find Unit 2 answer subsubsections in", path, file=sys.stderr)
        sys.exit(1)
    out: dict[str, List[Any]] = {"2_1": [], "2_2": [], "2_3": []}
    for key, sec in ("2_1", m1.group(1)), ("2_2", m2.group(1)), ("2_3", m3.group(1)):
        for row in _extract_table_rows(sec):
            for cell in _row_to_cells(row):
                out[key].append(_token_to_cell(cell))
    return out


def main() -> None:
    src = os.environ.get("NOVEL_PREP_ANSWER_TEX", _DEFAULT_ANSWER)
    if not os.path.isfile(src):
        print("Answer.tex not found at", src, file=sys.stderr)
        sys.exit(1)
    answers = parse_unit2_answer_tex(src)
    for k, row in answers.items():
        print(k, len(row), "answers")
    payload = {
        "version": 1,
        "source_note": "Parsed from Novel Prep Answer.tex Unit 2 tables; order matches banks/algebra 2_1–2_3.",
        "section_titles_zh": {
            "2.1": "2.1 等价表达式",
            "2.2": "2.2 非线性方程与方程组",
            "2.3": "2.3 非线性函数",
        },
        "section_titles_en": {
            "2.1": "2.1 Equivalent expressions",
            "2.2": "2.2 Nonlinear equations and systems",
            "2.3": "2.3 Nonlinear functions",
        },
        "answers_by_topic": answers,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
