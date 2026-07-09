#!/usr/bin/env python3
"""Validate placement answer keys and common student-format equivalences."""
from __future__ import annotations

import json
import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

from answer_grader import display_answer_plain, response_is_correct  # noqa: E402

BANK_PATH = os.path.join(APP_DIR, "data", "question_bank.json")

MIDDLE_LEVEL_CASES = [
    (7, "75", True),
    (21, "449", True),
    (43, "450", True),
    (59, "62.5", True),
    (52, "1/2", True),
    (80, "70", True),
    (36, "12.5", True),
    (37, "5", False),
    (76, "no", False),
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
            if not response_is_correct(q, str(key)):
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

    if errors:
        print("PLACEMENT GRADING AUDIT FAILED")
        for err in errors:
            print(" -", err)
        return 1

    print("Placement grading audit passed (all 4 tests).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
