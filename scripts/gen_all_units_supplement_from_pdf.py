#!/usr/bin/env python3
"""
Parse SAT_CB_Bank_Question_New_Answer.pdf (Units 1–4) and refresh
data/unit1_supplement.json … unit4_supplement.json.

Usage:
  python3 scripts/gen_all_units_supplement_from_pdf.py [path/to/answer.pdf]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, List, Union

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = ROOT / "SAT_CB_Bank_Question_New_Answer.pdf"

Cell = Union[str, dict[str, Any]]

_FOOTER_RE = re.compile(
    r"Novel Prep SAT Preparation Answer Key Jack Zeng.*",
    re.I | re.S,
)

# Expected question counts per topic (must match banks/* slices).
EXPECTED_COUNTS: dict[int, dict[str, int]] = {
    1: {"1_1": 13, "1_2": 15, "1_3": 22, "1_4": 20, "1_5": 16},
    2: {"2_1": 23, "2_2": 40, "2_3": 54},
    3: {"3_1": 9, "3_2": 16, "3_3": 18, "3_4": 9, "3_5": 7, "3_6": 5, "3_7": 5},
    4: {"4_1": 17, "4_2": 14, "4_3": 20, "4_4": 20},
}


def _strip_footer(ans: str) -> str:
    m = _FOOTER_RE.search(ans)
    if m:
        ans = ans[: m.start()]
    return ans.strip()


def _normalize_answer(ans: str) -> Cell:
    ans = _strip_footer(ans)
    if not ans:
        raise ValueError("empty answer after footer strip")
    if re.fullmatch(r"[A-Da-d]", ans):
        return ans.upper()
    low = ans.lower()
    if " or " in low:
        segs = re.split(r"\s+or\s+", ans, flags=re.I)
        flat: List[str] = []
        for seg in segs:
            seg = seg.strip()
            if not seg:
                continue
            if "," in seg:
                flat.extend(p.strip() for p in seg.split(",") if p.strip())
            else:
                flat.append(seg)
        if not flat:
            return ans
        if len(flat) == 1:
            return flat[0]
        return {"canonical": flat[0], "alternates": flat[1:]}
    if "," in ans:
        parts = [p.strip() for p in ans.split(",") if p.strip()]
        if len(parts) == 1:
            return parts[0]
        return {"canonical": parts[0], "alternates": parts[1:]}
    return ans


def _answers_in_section(sec_body: str) -> List[Cell]:
    markers = [
        (m.start(), m.end(), int(m.group(1)))
        for m in re.finditer(r"Q(\d+):\s*", sec_body)
    ]
    if not markers:
        raise ValueError("No Q markers in section body")
    pairs: list[tuple[int, str]] = []
    for i, (_s, e, n) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else len(sec_body)
        ans = sec_body[e:end].strip()
        pairs.append((n, ans))
    nums = [n for n, _ in pairs]
    if nums != list(range(1, len(nums) + 1)):
        raise ValueError(f"Q numbering gap: {nums[:12]}")
    return [_normalize_answer(ans) for _, ans in pairs]


def _parse_unit(full: str, unit_num: int) -> dict[str, List[Cell]]:
    start_pat = rf"Unit {unit_num}:"
    end_pat = rf"Unit {unit_num + 1}:"
    m = re.search(start_pat, full)
    if not m:
        raise ValueError(f"Could not find {start_pat}")
    start = m.end()
    m2 = re.search(end_pat, full[start:])
    body = full[start : start + m2.start()] if m2 else full[start:]
    header_re = re.compile(rf"^{unit_num}\.(\d)\s+[^\n]*$", re.M)
    matches = list(header_re.finditer(body))
    expected = EXPECTED_COUNTS[unit_num]
    if len(matches) != len(expected):
        raise ValueError(
            f"Unit {unit_num}: expected {len(expected)} section headers, found {len(matches)}"
        )
    out: dict[str, List[Cell]] = {}
    for i, m in enumerate(matches):
        sec_num = int(m.group(1))
        key = f"{unit_num}_{sec_num}"
        sec_start = m.end()
        sec_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        row = _answers_in_section(body[sec_start:sec_end])
        exp = expected.get(key)
        if exp is not None and len(row) != exp:
            raise ValueError(f"{key}: expected {exp} answers, got {len(row)}")
        out[key] = row
    return out


def _load_titles(unit_num: int) -> tuple[dict, dict]:
    path = ROOT / "data" / f"unit{unit_num}_supplement.json"
    if path.is_file():
        cur = json.loads(path.read_text(encoding="utf-8"))
        return cur.get("section_titles_zh", {}), cur.get("section_titles_en", {})
    return {}, {}


def _write_unit(unit_num: int, answers_by_topic: dict[str, List[Cell]], source_note: str) -> None:
    titles_zh, titles_en = _load_titles(unit_num)
    payload = {
        "version": 2 if unit_num == 1 else 1,
        "source_note": source_note,
        "section_titles_zh": titles_zh,
        "section_titles_en": titles_en,
        "answers_by_topic": answers_by_topic,
    }
    out = ROOT / "data" / f"unit{unit_num}_supplement.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    for k in sorted(answers_by_topic):
        print(f"  {k}: {len(answers_by_topic[k])}")


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

    full = "".join((p.extract_text() or "") for p in PdfReader(str(pdf_path)).pages)
    source = f"Parsed from {pdf_path.name}; order matches banks/* slices for Unit 1–4."

    for unit_num in range(1, 5):
        answers = _parse_unit(full, unit_num)
        _write_unit(unit_num, answers, source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
