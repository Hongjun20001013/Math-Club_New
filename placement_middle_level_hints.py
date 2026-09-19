"""Student entry hints and grading metadata for Middle Level placement (100 items)."""
from __future__ import annotations

import re
from typing import Any

from answer_grader import _clean_answer_text, _remainder_parts, _strip_trailing_units

_UNIT_TAIL = re.compile(
    r"\s+(?:cherries|chairs|frogs|birds|beans|miles?|mi\b|members|years\s*old|"
    r"hamburgers|average\s*pumpkins|per\s*container|containers|seconds|"
    r"sides|square\s*inches|sq\.\s*in\.|in\.|mm\b|cm\b|m\^3|m\^2|mm\^3|mi\^2)\s*$",
    re.I,
)

_TIME_KEY = re.compile(r"^\d{1,2}:\d{2}\s*(?:A\.?M\.?|P\.?M\.?)?$", re.I)
_MIXED_FRAC = re.compile(r"^\d+\s+\d+/\d+$")
_FRAC_ONLY = re.compile(r"^\d+/\d+$")

# Division items where students may enter a rounded decimal instead of quotient R remainder.
_DECIMAL_QUOTIENT = {
    13: {"value": 3795 / 6, "places": 3, "example": "632.500"},
    30: {"value": 3647 / 6, "places": 5, "example": "607.83333"},
}

_GLOBAL_HINTS_EN = [
    "Type numbers only unless the hint below says otherwise.",
    "Fractions: use a slash (3/4). Mixed numbers: whole, space, fraction — e.g. 3 1/6.",
    "Do not add units (miles, cm, %, AM/PM) unless a hint says you need them.",
]

_GLOBAL_HINTS_ZH = [
    "除非下方有特别说明，只输入数字即可。",
    "分数用斜杠（如 3/4）；带分数：整数 空格 分子/分母，例如 3 1/6。",
    "除非提示说明，不要输入单位（英里、厘米、百分号、AM/PM 等）。",
]


def _key_plain(key: str) -> str:
    return _strip_trailing_units(_clean_answer_text(key))


def _is_percent_key(key: str) -> bool:
    t = _key_plain(key)
    return t.endswith("%") or (t.replace(".", "", 1).isdigit() and "%" in key)


def _has_units_in_key(key: str) -> bool:
    raw = _clean_answer_text(key)
    if _UNIT_TAIL.search(raw):
        return True
    if re.search(r"(?<=\d)(?:m\^3|m\^2|mm\^3|mi\^2|cm|mm)\b", raw, re.I):
        return True
    return bool(re.search(r"\b(?:cherries|chairs|frogs|birds|beans|members|seconds|hamburgers)\b", raw, re.I))


def _is_mixed_fraction_key(key: str) -> bool:
    t = _key_plain(key).replace("$", "").strip()
    return bool(_MIXED_FRAC.match(t) or (_FRAC_ONLY.match(t) and "/" in t))


def _is_time_key(key: str) -> bool:
    return bool(_TIME_KEY.match(_key_plain(key)))


def _is_scientific_key(key: str) -> bool:
    low = key.lower()
    return "10^" in low or "e-" in low or "e+" in low or "×10" in low


def hints_for_question(qnum: int, question: dict[str, Any]) -> dict[str, Any]:
    """Return entry_hints_en/zh and optional grading metadata for one item."""
    key = str(question.get("correct_answer") or "")
    stem = str(question.get("stem") or "")
    hints_en: list[str] = []
    hints_zh: list[str] = []

    if qnum in _DECIMAL_QUOTIENT:
        spec = _DECIMAL_QUOTIENT[qnum]
        hints_en.append(
            f"After dividing, enter a decimal rounded to {spec['places']} decimal places "
            f"(e.g. {spec['example']}). You may also type quotient R remainder (e.g. 632 R3)."
        )
        hints_zh.append(
            f"除法完成后，输入保留 {spec['places']} 位小数的答案（例如 {spec['example']}）。"
            f"也可输入商 R 余数（例如 632 R3）。"
        )
    elif _remainder_parts(_key_plain(key)):
        rem = _remainder_parts(_key_plain(key))
        hints_en.append(
            f"Enter quotient R remainder (e.g. {rem[0]} R{rem[1]}) or the exact decimal equivalent."
        )
        hints_zh.append(f"输入 商 R 余数（例如 {rem[0]} R{rem[1]}），或等值小数。")

    if _is_percent_key(key) or "%" in stem or "percent" in stem.lower():
        hints_en.append("This item is about percent. The % is already in the question — type the number only (e.g. 75, not 75%).")
        hints_zh.append("本题是百分数。题目里已有 % 号 — 只输入数字（例如 75，不要输入 75%）。")

    if _has_units_in_key(key):
        hints_en.append("Do not type units — enter the number only (e.g. 449, not 449 cherries).")
        hints_zh.append("不要输入单位 — 只输入数字（例如 449，不要写 449 cherries）。")

    if _is_time_key(key):
        hints_en.append("Enter time as h:mm only (e.g. 2:15). Do not type AM, PM, or A.M./P.M.")
        hints_zh.append("时间只输入 时:分（例如 2:15），不要输入 AM、PM。")

    if _is_mixed_fraction_key(key):
        hints_en.append(
            "Use a mixed number: whole number, space, then fraction — e.g. 3 1/6 for three and one-sixth. "
            "Prefer this form over a long decimal."
        )
        hints_zh.append("带分数格式：整数 空格 分子/分母，例如 3 1/6 表示三又六分之一。请用此格式，不要用很长的小数。")

    if _is_scientific_key(key) or "scientific notation" in stem.lower() or "10^" in stem:
        hints_en.append("Scientific notation: 5.17e-6 or 5.17 x 10^-6 (use the coefficient the question asks you to round).")
        hints_zh.append("科学计数法：5.17e-6 或 5.17 x 10^-6（按题目要求保留系数的小数位）。")

    if "nearest thousandth" in stem.lower() or "thousandth" in stem.lower():
        hints_en.append("Round to the nearest thousandth (3 decimal places) before you submit.")
        hints_zh.append("四舍五入到千分位（保留三位小数）后再提交。")

    if "round" in stem.lower() and "coefficient" in stem.lower():
        hints_en.append("Round only the coefficient to the number of decimal places shown in the question.")
        hints_zh.append("只按题目要求对系数（coefficient）保留小数位。")

    if "," in _key_plain(key) and re.search(r"\d,\d", _key_plain(key)):
        hints_en.append("Several answers: separate with commas, no spaces (e.g. 3000,3100,3200).")
        hints_zh.append("多个答案用英文逗号分隔，不要空格（例如 3000,3100,3200）。")

    if re.search(r"\$\d", _key_plain(key)):
        hints_en.append("Money answers: numbers only — e.g. 3.14 or 11.25 (no dollar sign).")
        hints_zh.append("金额题只输入数字，例如 3.14 或 11.25（不要输入 $ 符号）。")

    out: dict[str, Any] = {
        "entry_hints_en": hints_en,
        "entry_hints_zh": hints_zh,
    }
    if qnum in _DECIMAL_QUOTIENT:
        out["accept_decimal_quotient"] = _DECIMAL_QUOTIENT[qnum]
    return out


def enrich_middle_level_question(question: dict[str, Any], qnum: int) -> dict[str, Any]:
    q = dict(question)
    meta = hints_for_question(qnum, q)
    q.update(meta)
    return q


def enrich_middle_level_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [enrich_middle_level_question(q, i + 1) for i, q in enumerate(questions)]


def global_entry_hints() -> dict[str, list[str]]:
    return {"en": list(_GLOBAL_HINTS_EN), "zh": list(_GLOBAL_HINTS_ZH)}
