"""
Grading helpers for MCQ (A–D) and numeric / short free-response answers.
Used by practice submit and session summary regrade.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import List, Optional, Set


def _strip_input(s: str) -> str:
    return (
        s.strip()
        .replace("\u2212", "-")
        .replace("−", "-")
        .replace(",", "")
    )


def _try_numeric_value(s: str) -> Optional[float]:
    t = _strip_input(s)
    if not t:
        return None
    try:
        return float(Fraction(t))
    except (ValueError, ZeroDivisionError):
        pass
    try:
        return float(t)
    except ValueError:
        return None


def _norm_text(s: str) -> str:
    t = re.sub(r"\s+", "", _strip_input(s).lower())
    return t.replace("(", "").replace(")", "")


_MIDDLE_LEVEL_UNITS = (
    r"cherries|chairs|frogs|birds|beans|miles|mi\b|members|years\s*old|"
    r"hamburgers|average\s*pumpkins|per\s*container|containers|seconds|"
    r"sides|square\s*inches|sq\.\s*in\.|in\.|mm\b|cm\b|"
    r"m\^2|mm\^3|mi\^2"
)


def _strip_trailing_units(s: str) -> str:
    t = s.strip()
    t = re.sub(rf"\s+(?:{_MIDDLE_LEVEL_UNITS})\s*$", "", t, flags=re.I)
    return t.strip()


def _clean_answer_text(s: str) -> str:
    """Strip LaTeX / markup and normalize spacing for comparison."""
    t = (s or "").strip()
    if not t:
        return ""
    t = t.replace("\u2212", "-").replace("−", "-")
    if t.startswith(r"\(") and t.endswith(r"\)"):
        t = t[2:-2].strip()
    t = t.replace(r"\$", "").replace("$", "")
    t = t.replace(r"\%", "%")
    t = re.sub(r"\\displaystyle\s*", "", t)
    t = re.sub(r"\\(?:d|t)?frac\{([^{}]+)\}\{([^{}]+)\}", r"\1/\2", t)
    t = re.sub(r"\\frac(\d)(\d)\b", r"\1/\2", t)
    t = re.sub(r"\\frac\{?(\d+)\}?/\{?(\d+)\}?", r"\1/\2", t)
    t = re.sub(r"\\overline\{([^}]+)\}", r"\1", t)
    t = re.sub(r"\\text\{([^}]*)\}", r"\1", t)
    t = re.sub(r"\\mathbf\{([^}]*)\}", r"\1", t)
    t = re.sub(r"\\boxed\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"\\(?:left|right)\b", "", t)
    t = re.sub(r"\\times\s*10\^\{?([^}]+)\}?", r"e\1", t, flags=re.I)
    t = re.sub(r"\\cdot\b", "", t)
    t = re.sub(r"\^\{([^{}]+)\}", r"^\1", t)
    t = re.sub(r"\\[(),]", "", t)
    t = re.sub(r"\{|\}", "", t)
    t = re.sub(r"\\approx", "≈", t)
    t = re.sub(r"\\sqrt\{([^{}]+)\}", r"√\1", t)
    t = re.sub(r"\\sqrt(\d+)", r"√\1", t)
    t = re.sub(r"\\sin", "sin", t)
    t = re.sub(r"\\cos", "cos", t)
    t = re.sub(r"\\tan", "tan", t)
    t = re.sub(r"\\[a-zA-Z]+\b", "", t)
    t = t.replace("P.M.", "PM").replace("A.M.", "AM").replace("p.m.", "PM").replace("a.m.", "AM")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _strip_percent_symbol(s: str) -> str:
    return re.sub(r"%\s*$", "", s.strip()).strip()


def _mixed_number_to_decimal(s: str) -> Optional[str]:
    m = re.fullmatch(r"(-?\d+)\s+(\d+)/(\d+)", s.strip())
    if not m:
        return None
    try:
        whole = int(m.group(1))
        frac = Fraction(int(m.group(2)), int(m.group(3)))
        val = whole + float(frac) if whole >= 0 else whole - float(frac)
        return f"{val:g}"
    except (ValueError, ZeroDivisionError):
        return None


def _answer_variants(s: str) -> Set[str]:
    """Comparable forms for a reference or student answer."""
    variants: Set[str] = set()
    base = _clean_answer_text(s)
    if not base:
        return variants

    candidates = [base, _strip_trailing_units(base), _strip_percent_symbol(base)]
    candidates.append(_strip_trailing_units(_strip_percent_symbol(base)))

    for cand in candidates:
        if not cand:
            continue
        variants.add(_norm_text(cand))
        variants.add(_norm_text(cand.replace(",", "")))
        dec = _mixed_number_to_decimal(cand)
        if dec:
            variants.add(_norm_text(dec))
        if re.fullmatch(r"-?\d+/\d+", cand.replace(" ", "")):
            try:
                variants.add(_norm_text(f"{float(Fraction(cand.replace(' ', ''))):g}"))
            except (ValueError, ZeroDivisionError):
                pass
        if "," in cand:
            parts = [p.strip() for p in cand.split(",") if p.strip()]
            if parts:
                variants.add(_norm_text(",".join(parts)))
                variants.add(_norm_text(",".join(p.replace(" ", "") for p in parts)))

    return {v for v in variants if v}


def display_answer_plain(s: str, *, max_len: int = 48) -> str:
    """Readable answer text for PDF/UI (no raw LaTeX like \\frac12 or 75\\%)."""
    t = _clean_answer_text(s or "")
    if not t or t in ("—", "-"):
        return t or "—"
    t = re.sub(r"\s+", " ", t).strip()
    return t[:max_len] if t else "—"


def numeric_match(a: float, b: float, tol: float = 0.002) -> bool:
    return abs(a - b) <= tol


def free_response_matches(student: str, canonical: str, alternates: List[str], tol: float = 0.002) -> bool:
    """True if student answer matches canonical or any alternate (numeric tolerance or normalized text)."""
    if not _strip_input(student):
        return False

    student_vars = _answer_variants(student)
    refs = [canonical, *alternates]
    for ref in refs:
        ref_s = str(ref)
        if student_vars & _answer_variants(ref_s):
            return True

    sn = _try_numeric_value(student)
    if sn is not None:
        for ref in refs:
            for rv in _answer_variants(str(ref)):
                rn = _try_numeric_value(rv)
                if rn is not None and numeric_match(sn, rn, tol):
                    return True

    st = _norm_text(student)
    if st == _norm_text(canonical):
        return True
    for alt in alternates:
        if st == _norm_text(str(alt)):
            return True
    return False


def response_is_correct(question: dict, student_raw: str) -> Optional[bool]:
    """
    None: cannot grade (no key or empty response).
    True / False: graded result.
    """
    key = question.get("correct_answer")
    if key is None or str(key).strip() == "":
        return None

    kind = question.get("question_kind", "mcq")
    s = (student_raw or "").strip()
    if not s:
        return None

    if kind == "free_response":
        alts: List[str] = []
        raw_alts = question.get("answer_alternates")
        if isinstance(raw_alts, list):
            alts = [str(x) for x in raw_alts]
        return free_response_matches(s, str(key), alts)

    allowed = {"A", "B", "C", "D", "E"} if kind == "mcq5" else {"A", "B", "C", "D"}
    letter = s[:1].upper()
    if letter not in allowed:
        return False
    return letter == str(key).strip().upper()


def grade_for_db(question: dict, student_raw: str) -> tuple[Optional[int], str]:
    """
    Returns (is_correct: 1/0/None, canonical_key string for practice_responses.correct_answer).
    """
    key = question.get("correct_answer")
    key_s = str(key).strip() if key is not None else ""
    res = response_is_correct(question, student_raw)
    if res is None:
        return None, key_s
    return int(bool(res)), key_s
