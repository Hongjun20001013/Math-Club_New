"""
Grading helpers for MCQ (A–D) and numeric / short free-response answers.
Used by practice submit and session summary regrade.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any, List, Optional


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
    return re.sub(r"\s+", "", _strip_input(s).lower())


def numeric_match(a: float, b: float, tol: float = 0.002) -> bool:
    return abs(a - b) <= tol


def free_response_matches(student: str, canonical: str, alternates: List[str], tol: float = 0.002) -> bool:
    """True if student answer matches canonical or any alternate (numeric tolerance or normalized text)."""
    if not _strip_input(student):
        return False

    sn = _try_numeric_value(student)
    if sn is not None:
        for ref in [canonical, *alternates]:
            rn = _try_numeric_value(str(ref))
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
