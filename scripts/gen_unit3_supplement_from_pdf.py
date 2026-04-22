#!/usr/bin/env python3
"""
Build data/unit3_supplement.json from the Novel Prep answer-key PDF
(SAT_CB_Bank_Question - …pdf). Unit 3 sections 3.1–3.7 only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, List, Union

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = ROOT / "SAT_CB_Bank_Question - 2026-04-21T141306.525.pdf"
OUT = ROOT / "data" / "unit3_supplement.json"

Cell = Union[str, dict[str, Any]]


def _normalize_answer(ans: str) -> Cell:
    ans = ans.strip()
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


def _extract_unit3_block(pdf_text: str) -> str:
    m = re.search(r"Unit 3:.*?(?=Unit 4:)", pdf_text, re.S)
    if not m:
        raise ValueError("Could not find Unit 3 block before Unit 4")
    return m.group(0)


def _answers_in_section(sec_body: str) -> List[Cell]:
    """Many Qn: entries appear on one line; split on each Qn: marker."""
    markers = [(m.start(), m.end(), int(m.group(1))) for m in re.finditer(r"Q(\d+):\s*", sec_body)]
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


def _parse_sections(body: str) -> dict[str, List[Cell]]:
    """Return answers_by_topic keys 3_1 … 3_7."""
    header_re = re.compile(r"^3\.(\d)\s+[^\n]*$", re.M)
    matches = list(header_re.finditer(body))
    if len(matches) != 7:
        raise ValueError(f"Expected 7 section headers 3.1–3.7, found {len(matches)}")
    out: dict[str, List[Cell]] = {}
    for i, m in enumerate(matches):
        sec_num = int(m.group(1))
        if sec_num != i + 1:
            raise ValueError(f"Section order mismatch at {m.group(0)}")
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sec_body = body[start:end]
        out[f"3_{sec_num}"] = _answers_in_section(sec_body)
    return out


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

    reader = PdfReader(str(pdf_path))
    full = "".join((p.extract_text() or "") for p in reader.pages)
    body = _extract_unit3_block(full)
    answers_by_topic = _parse_sections(body)

    payload = {
        "version": 1,
        "source_note": "Parsed from SAT_CB_Bank_Question answer PDF; order matches banks/problem_solving 3_1–3_7.",
        "section_titles_zh": {
            "3.1": "3.1 比率、速率与单位",
            "3.2": "3.2 百分数",
            "3.3": "3.3 一元数据：分布与集中/离散程度",
            "3.4": "3.4 二元数据：模型与散点图",
            "3.5": "3.5 概率与条件概率",
            "3.6": "3.6 由样本统计量推断与误差范围",
            "3.7": "3.7 对统计论断的评估：观察性研究与实验",
        },
        "section_titles_en": {
            "3.1": "3.1 Ratios, rates, proportional relationships, and units",
            "3.2": "3.2 Percentages",
            "3.3": "3.3 One-variable data: distributions and center/spread",
            "3.4": "3.4 Two-variable data: models and scatterplots",
            "3.5": "3.5 Probability and conditional probability",
            "3.6": "3.6 Inference from sample statistics and margin of error",
            "3.7": "3.7 Evaluating statistical claims: studies and experiments",
        },
        "answers_by_topic": answers_by_topic,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Wrote", OUT)
    for k, row in answers_by_topic.items():
        print(k, len(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
