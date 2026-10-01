#!/usr/bin/env python3
"""Audit Unit 1 & Unit 2 SAT bank items for CB walkthrough coverage."""

from __future__ import annotations

import json
import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK_PATH = os.path.join(APP_DIR, "data", "question_bank.json")

UNIT1 = ("1_1", "1_2", "1_3", "1_4", "1_5")
UNIT2 = ("2_1", "2_2", "2_3")


def _audit_slice(domain: str, topic: str, questions: list) -> list[str]:
    issues: list[str] = []
    for i, q in enumerate(questions):
        e = (q.get("explanation_en") or "").strip()
        label = f"{domain}:{topic}:{i}"
        if not e:
            issues.append(f"{label}: missing explanation_en")
            continue
        if "np-sol-block--walkthrough" not in e:
            issues.append(f"{label}: no walkthrough block")
        elif "Step 1" not in e and "Step 1:" not in e:
            issues.append(f"{label}: walkthrough missing Step 1")
        if "Final answer" not in e and "Verified key" not in e:
            issues.append(f"{label}: no final answer / key section")
    return issues


def main() -> int:
    with open(BANK_PATH, encoding="utf-8") as f:
        bank = json.load(f)
    all_issues: list[str] = []
    for tk in UNIT1:
        all_issues.extend(_audit_slice("algebra", tk, bank.get("algebra", {}).get(tk) or []))
    for tk in UNIT2:
        all_issues.extend(
            _audit_slice("advanced_math", tk, bank.get("advanced_math", {}).get(tk) or [])
        )
    n1 = sum(len(bank.get("algebra", {}).get(t) or []) for t in UNIT1)
    n2 = sum(len(bank.get("advanced_math", {}).get(t) or []) for t in UNIT2)
    print(f"Unit 1 algebra slices: {n1} questions")
    print(f"Unit 2 advanced_math slices: {n2} questions")
    if all_issues:
        print(f"FAIL: {len(all_issues)} issue(s)", file=sys.stderr)
        for line in all_issues[:30]:
            print(line, file=sys.stderr)
        if len(all_issues) > 30:
            print(f"... and {len(all_issues) - 30} more", file=sys.stderr)
        return 1
    print("audit_sat_unit_walkthroughs: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
