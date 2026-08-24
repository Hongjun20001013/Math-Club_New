#!/usr/bin/env python3
"""Validate placement answer keys and common student-format equivalences."""
from __future__ import annotations

import json
import os
import sys
from math import comb, perm

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

from answer_grader import display_answer_plain, response_is_correct  # noqa: E402

BANK_PATH = os.path.join(APP_DIR, "data", "question_bank.json")

MIDDLE_LEVEL_CASES = [
    # Format-equivalent correct
    (7, "75", True),
    (7, "75%", True),
    (21, "449", True),
    (21, "449 cherries", True),
    (43, "450", True),
    (59, "62.5", True),
    (52, "1/2", True),
    (80, "70", True),
    (36, "12.5", True),
    (36, "12 1/2", True),
    (90, "800", True),
    (90, "800 m^3", True),
    (92, "2602 1/7", True),
    (92, "18215/7", True),
    (92, "2602.142857", True),
    (92, "2602.14", True),
    (99, "5.17e-6", True),
    (99, "5.17 x 10^-6", True),
    (99, "5.17×10^-6", True),
    (13, "632 R3", True),
    (13, "632R3", True),
    (26, "818080", True),
    (38, "3000,3100,3200", True),
    # Must stay wrong
    (37, "5", False),
    (76, "no", False),
    (13, "632", False),
    (4, "14:11", False),
    (1, "2.83", False),
]

ENHANCED_FR_CASES = [
    ("enhanced_math_1", 55, "no solution", True),
    ("enhanced_math_1", 55, "No solution.", True),
    ("enhanced_math_1", 55, "no solution because the constants differ", True),
    ("enhanced_math_1", 55, "none", True),
    ("enhanced_math_1", 58, "440.59", True),
    ("enhanced_math_1", 63, "√29", True),
    ("enhanced_math_2", 64, "43", True),
    ("enhanced_math_2", 64, "48", False),
    ("enhanced_math_2", 64, "38", False),
    ("enhanced_math_2", 67, "10.1", True),
    ("enhanced_math_2", 67, "10.07", True),
    ("enhanced_math_2", 67, "10.073", True),
    ("enhanced_math_2", 67, "10.0731", True),
    ("enhanced_math_2", 67, "10.0", False),
    ("enhanced_math_2", 68, "59.4", True),
    ("enhanced_math_2", 68, "35", False),
    ("enhanced_math_2", 69, "5π", True),
    # Unrelated numbers must not be auto-correct; prose is awaiting review (None)
    ("enhanced_math_1", 56, "21", None),
    ("enhanced_math_2", 60, "2", None),
]


def main() -> int:
    with open(BANK_PATH, encoding="utf-8") as f:
        bank = json.load(f)
    errors: list[str] = []

    for topic in ("placement_full", "enhanced_math_1", "enhanced_math_2", "middle_level"):
        questions = bank["placement"][topic]
        for i, q in enumerate(questions, start=1):
            key = q.get("correct_answer")
            if not key:
                if q.get("question_kind") in ("mcq", "mcq5", "free_response"):
                    errors.append(f"{topic} Q{i}: missing correct_answer")
                continue
            if q.get("knowledge_section") in ("FR", "G") or q.get("question_kind") == "constructed_response":
                pass
            elif not response_is_correct(q, str(key)):
                errors.append(f"{topic} Q{i}: canonical does not match itself ({key!r})")
            disp = display_answer_plain(str(key))
            if topic == "middle_level" and ("\\" in disp or "frac" in disp.lower()):
                errors.append(f"{topic} Q{i}: LaTeX in display ({disp!r})")
            for alt in q.get("answer_alternates") or []:
                if not response_is_correct(q, str(alt)):
                    errors.append(f"{topic} Q{i}: alternate does not match ({alt!r})")

    ml = bank["placement"]["middle_level"]
    for qnum, student, expect in MIDDLE_LEVEL_CASES:
        got = response_is_correct(ml[qnum - 1], student)
        if got is not expect:
            errors.append(
                f"middle_level Q{qnum}: student {student!r} expected {expect}, got {got}"
            )

    for topic, qnum, student, expect in ENHANCED_FR_CASES:
        q = bank["placement"][topic][qnum - 1]
        got = response_is_correct(q, student)
        if got is not expect:
            errors.append(
                f"{topic} Q{qnum}: student {student!r} expected {expect}, got {got} "
                f"(key={q.get('correct_answer')!r} alts={q.get('answer_alternates')!r})"
            )

    # MCQ letter completeness
    for topic, kind in (("placement_full", "mcq5"), ("enhanced_math_1", "mcq"), ("enhanced_math_2", "mcq")):
        qs = [q for q in bank["placement"][topic] if q.get("question_kind") == kind]
        for i, q in enumerate(qs, start=1):
            key = str(q.get("correct_answer") or "").upper()
            allowed = set("ABCDE") if kind == "mcq5" else set("ABCD")
            if key not in allowed:
                errors.append(f"{topic} MCQ#{i}: invalid key {key!r}")

    q33 = bank["placement"]["placement_full"][32]
    if comb(11, 6) != 462 or perm(11, 6) != 332640:
        errors.append("independent C(11,6)/P(11,6) mismatch")
    if q33.get("correct_answer") != "A":
        errors.append(f"upper Q33 key must be A, got {q33.get('correct_answer')!r}")
    if response_is_correct(q33, "A") is not True:
        errors.append("upper Q33: A must score correct")
    if response_is_correct(q33, "B") is not False:
        errors.append("upper Q33: B must score incorrect")

    if errors:
        print("PLACEMENT GRADING AUDIT FAILED")
        for err in errors:
            print(" -", err)
        return 1

    print("Placement grading audit passed (all 4 tests).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
