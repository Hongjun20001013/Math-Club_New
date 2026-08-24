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
    mixed = _mixed_number_to_decimal(t)
    if mixed is not None:
        try:
            return float(mixed)
        except ValueError:
            return None
    # Scientific notation written as "3.87 x 10^-4" / "3.87×10^-4"
    sci = re.fullmatch(
        r"([-+]?\d+(?:\.\d+)?)\s*[x×]\s*10\s*\^?\s*([-+]?\d+)",
        t,
        flags=re.I,
    )
    if sci:
        try:
            return float(sci.group(1)) * (10.0 ** int(sci.group(2)))
        except ValueError:
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
    r"m\^3|m\^2|mm\^3|mi\^2"
)


def _strip_trailing_units(s: str) -> str:
    t = s.strip()
    t = re.sub(rf"\s+(?:{_MIDDLE_LEVEL_UNITS})\s*$", "", t, flags=re.I)
    # Also accept glued forms like 800m^3 / 138m^2
    t = re.sub(r"(?<=\d)(?:m\^3|m\^2|mm\^3|mi\^2|cm|mm)\s*$", "", t, flags=re.I)
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
    t = re.sub(r"\^\{([^{}]+)\}", r"^(\1)", t)
    t = re.sub(r"\\[(),]", "", t)
    t = re.sub(r"\{|\}", "", t)
    t = re.sub(r"\\approx", "≈", t)
    t = re.sub(r"\\sqrt\{([^{}]+)\}", r"√\1", t)
    t = re.sub(r"\\sqrt(\d+)", r"√\1", t)
    t = re.sub(r"\\sin", "sin", t)
    t = re.sub(r"\\cos", "cos", t)
    t = re.sub(r"\\tan", "tan", t)
    t = re.sub(r"\\theta", "θ", t)
    t = re.sub(r"\\pi", "π", t)
    t = re.sub(r"\^?\\circ", "°", t)
    t = re.sub(r"\\[a-zA-Z]+\b", "", t)
    t = t.replace("P.M.", "PM").replace("A.M.", "AM").replace("p.m.", "PM").replace("a.m.", "AM")
    # Word-style scientific notation → e-form for display/compare helpers
    t = re.sub(
        r"([-+]?\d+(?:\.\d+)?)\s*[x×]\s*10\s*\^?\s*([-+]?\d+)",
        r"\1e\2",
        t,
        flags=re.I,
    )
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


def _remainder_parts(s: str) -> Optional[tuple[str, str]]:
    """Parse division-with-remainder answers like '632 R3'."""
    m = re.fullmatch(r"(-?\d+)\s*[rR]\s*(-?\d+)", s.strip())
    if not m:
        return None
    return m.group(1), m.group(2)


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
        rem = _remainder_parts(cand)
        if rem:
            # Canonical remainder form only (reject bare quotient).
            variants.add(_norm_text(f"{rem[0]}R{rem[1]}"))
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
    if abs(a - b) <= tol:
        return True
    # Accept common student rounding of larger-magnitude decimals
    # (e.g. 600/19 ≈ 31.5789 entered as 31.58 or 31.6).
    if abs(b) >= 10:
        if round(a, 1) == round(b, 1) and abs(a - b) < 0.06:
            return True
        if round(a, 2) == round(b, 2) and abs(a - b) < 0.006:
            return True
    return False


def _is_no_solution_ref(refs: List[str]) -> bool:
    for ref in refs:
        n = _norm_text(str(ref))
        low = str(ref).lower()
        if "nosolution" in n or "no solution" in low:
            return True
        if n in {"none", "nosolutions"}:
            return True
    return False


def _student_says_no_solution(student: str) -> bool:
    t = (student or "").strip().lower()
    if not t:
        return False
    if re.search(r"\bno\s+solutions?\b", t):
        return True
    n = _norm_text(student)
    return n in {"none", "nosolution", "nosolutions"}


def _looks_like_short_math(student: str) -> bool:
    t = (student or "").strip()
    if not t or len(t) > 48:
        return False
    compact = re.sub(r"\s+", "", t)
    return bool(
        re.fullmatch(
            r"[-+]?(?:\d+(?:\.\d+)?(?:e[-+]?\d+)?|\d+/\d+|\d+\s+\d+/\d+|√\d+|sqrt\(\d+\)|\d*[πpi]+|[πpi])"
            r"(?:[;,][-+]?(?:\d+(?:\.\d+)?(?:e[-+]?\d+)?|\d+/\d+|√\d+|sqrt\(\d+\)|\d*[πpi]+))*",
            compact,
            flags=re.I,
        )
    )


def _extract_math_pieces(student: str) -> List[str]:
    text = student or ""
    pieces = re.findall(
        r"-?\d+\s+\d+/\d+|-?\d+/\d+|-?\d+(?:\.\d+)?(?:e[-+]?\d+)?|"
        r"√\d+|sqrt\(\d+\)|\d+\s*[πpi]+|[πpi]",
        text,
        flags=re.I,
    )
    return [p.strip() for p in pieces if p.strip()]


def free_response_matches(student: str, canonical: str, alternates: List[str], tol: float = 0.002) -> bool:
    """True if student answer matches canonical or any alternate (numeric tolerance or normalized text)."""
    if not _strip_input(student):
        return False

    # Remainder answers must keep both quotient and remainder.
    can_rem = _remainder_parts(_clean_answer_text(canonical))
    stu_rem = _remainder_parts(_clean_answer_text(student))
    if can_rem is not None:
        if stu_rem is None:
            return False
        if can_rem == stu_rem:
            return True
        # Still allow exact alternate remainder strings below.

    student_vars = _answer_variants(student)
    refs = [canonical, *alternates]
    if _is_no_solution_ref([str(r) for r in refs]) and _student_says_no_solution(student):
        return True
    for ref in refs:
        ref_s = str(ref)
        if student_vars & _answer_variants(ref_s):
            return True

    sn = _try_numeric_value(student)
    if sn is not None and can_rem is None:
        for ref in refs:
            for rv in _answer_variants(str(ref)):
                if _remainder_parts(rv) is not None:
                    continue
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


def _enhanced_fr_tokens(question: dict) -> List[str]:
    """Short, auto-gradable tokens for Enhanced Math open-response items."""
    tokens: List[str] = []
    key = str(question.get("correct_answer") or "")
    if _is_no_solution_ref([key]):
        tokens.extend(["no solution", "none"])
    raw_alts = question.get("answer_alternates")
    if isinstance(raw_alts, list):
        for alt in raw_alts:
            a = str(alt).strip()
            if a and len(a) <= 32:
                tokens.append(a)
    seen: Set[str] = set()
    out: List[str] = []
    for tok in tokens:
        k = _norm_text(tok)
        if k and k not in seen:
            seen.add(k)
            out.append(tok)
    return out


def _enhanced_fr_is_correct(question: dict, student: str) -> Optional[bool]:
    """Grade Enhanced Math FR without using the full rubric string as a wrong-key.

    True: a reliable numeric/expression/no-solution token matches.
    False: a short math answer that does not match any reliable token.
    None: prose / explanation — awaiting review, never auto-incorrect.
    """
    tokens = _enhanced_fr_tokens(question)
    if tokens:
        if _is_no_solution_ref(tokens) and _student_says_no_solution(student):
            return True
        if free_response_matches(student, tokens[0], tokens[1:]):
            return True
        for piece in _extract_math_pieces(student):
            if free_response_matches(piece, tokens[0], tokens[1:]):
                return True
        if _looks_like_short_math(student):
            return False
        return None
    return None


def response_is_correct(question: dict, student_raw: str) -> Optional[bool]:
    """
    None: cannot grade (no key, empty response, graphing, or needs review).
    True / False: graded result.
    """
    kind = question.get("question_kind", "mcq")
    s = (student_raw or "").strip()
    if not s:
        return None

    if kind == "constructed_response" or question.get("knowledge_section") == "G":
        return None

    key = question.get("correct_answer")
    if key is None or str(key).strip() == "":
        return None

    if kind == "free_response" and question.get("knowledge_section") == "FR":
        return _enhanced_fr_is_correct(question, s)

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


PAPER_COMPLETE_TOKEN = "PAPER_COMPLETE"
PAPER_NOTICE = "Complete this question on paper. This item is not scored automatically."
PAPER_CHECKBOX_LABEL = "I completed this question on paper"


def is_placement_paper_item(question: dict) -> bool:
    """Placement FRQ, constructed response, and graphing items are paper-only."""
    kind = str(question.get("question_kind") or "")
    if kind in ("constructed_response", "free_response"):
        return True
    return str(question.get("knowledge_section") or "") in ("FR", "G")


def is_mcq_item(question: dict) -> bool:
    return str(question.get("question_kind") or "mcq") in ("mcq", "mcq5")


def is_paper_complete(selected: str) -> bool:
    return bool((selected or "").strip())


def placement_recorded_paper_answer(
    form_selected: str, paper_completed: str | None = None
) -> str:
    """Checkbox (or any leftover typed value) records completion only. Never a graded key."""
    flag = str(paper_completed or "").strip().lower()
    if flag in ("1", "on", "true", "yes", PAPER_COMPLETE_TOKEN.lower()):
        return PAPER_COMPLETE_TOKEN
    if (form_selected or "").strip():
        return PAPER_COMPLETE_TOKEN
    return ""


def placement_auto_score_breakdown(
    questions: list,
    selected_by_index: dict[int, str],
    is_correct_by_index: dict[int, Optional[int]] | None = None,
) -> dict:
    """MCQ-only auto score. Paper FRQ never changes the numerator or denominator."""
    is_correct_by_index = is_correct_by_index or {}
    mcq_total = 0
    mcq_correct = 0
    mcq_incorrect = 0
    paper_total = 0
    paper_completed = 0
    for i, question in enumerate(questions):
        selected = str(selected_by_index.get(i) or "")
        if is_placement_paper_item(question):
            paper_total += 1
            if is_paper_complete(selected):
                paper_completed += 1
            continue
        if not is_mcq_item(question):
            paper_total += 1
            if is_paper_complete(selected):
                paper_completed += 1
            continue
        mcq_total += 1
        ic = is_correct_by_index[i] if i in is_correct_by_index else None
        if i not in is_correct_by_index:
            graded = response_is_correct(question, selected) if selected.strip() else None
            ic = None if graded is None else int(bool(graded))
        if ic == 1:
            mcq_correct += 1
        elif ic == 0:
            mcq_incorrect += 1
    return {
        "mcq_correct": mcq_correct,
        "mcq_total": mcq_total,
        "mcq_incorrect": mcq_incorrect,
        "paper_frq_completed": paper_completed,
        "paper_frq_total": paper_total,
        "provisional": True,
        "correct": mcq_correct,
        "scored": mcq_correct + mcq_incorrect,
        "total": mcq_total,
        "item_total": len(questions),
        "auto_correct": mcq_correct,
        "auto_incorrect": mcq_incorrect,
        "paper_response": paper_completed,
        "unscored": paper_total - paper_completed,
        "awaiting_review": 0,
        "unscored_graphing": 0,
    }


def placement_result_status(question: dict, is_correct: Optional[int], selected: str) -> str:
    """Staff-facing label for one placement item.

    Paper FRQ / graphing items are never auto_correct or auto_incorrect.
    """
    has = bool((selected or "").strip())
    kind = question.get("question_kind")
    sec = question.get("knowledge_section")
    if is_placement_paper_item(question):
        return "paper_response" if has else "unscored"
    if kind == "constructed_response" or sec == "G":
        return "unscored" if has else "unscored"
    if is_correct == 1:
        return "auto correct"
    if is_correct == 0:
        return "auto incorrect"
    if has:
        return "awaiting review"
    return "skipped"


def grade_for_db(question: dict, student_raw: str) -> tuple[Optional[int], str]:
    """
    Returns (is_correct: 1/0/None, canonical_key string for practice_responses.correct_answer).
    None means unscored graphing or awaiting review — never store 0 for those.
    """
    key = question.get("correct_answer")
    key_s = str(key).strip() if key is not None else ""
    res = response_is_correct(question, student_raw)
    if res is None:
        return None, key_s
    return int(bool(res)), key_s
