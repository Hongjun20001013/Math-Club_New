#!/usr/bin/env python3
"""
Sanity-check custom English walkthroughs (unit*_explanations_en.json) against the live bank.

Keys must be global display_number strings matching unit*_question_manifest.json + question_bank
"unit_*_all" order. If slice order drifts without updating walkthroughs, stems and notes disagree
(students see wrong explanations).

Usage:
  python3 scripts/verify_custom_explanations.py

Exit 0 if all override files are empty or every keyed explanation passes a light numeric overlap
heuristic with its stem. Exit 1 on mismatch (print details).
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = os.path.join(APP_DIR, "data", "question_bank.json")


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "", flags=re.I)


def _nums(s: str) -> set[str]:
    return set(re.findall(r"\d[\d,.\s]*\d|\d+", s))


def _check_unit(
    label: str,
    domain: str,
    full_topic: str,
    expl_path: str,
    manifest_path: str,
    bank: dict,
) -> list[str]:
    errs: list[str] = []
    if not os.path.isfile(expl_path):
        return errs
    with open(expl_path, encoding="utf-8") as f:
        expl: dict[str, Any] = json.load(f)
    if not expl:
        return errs
    qs = bank.get(domain, {}).get(full_topic)
    if not qs:
        errs.append(f"{label}: missing {domain}/{full_topic} in bank")
        return errs
    by_disp: dict[int, dict] = {}
    if os.path.isfile(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            man = json.load(f)
        for row in man:
            d = int(row["display_number"])
            tk = row["topic_key"]
            li = int(row["topic_local_index"])
            by_disp[d] = bank[domain][tk][li]
    else:
        for i, q in enumerate(qs, start=1):
            by_disp[i] = q

    for k, text in expl.items():
        if not str(text).strip():
            continue
        try:
            d = int(k)
        except ValueError:
            errs.append(f"{label}: non-integer expl key {k!r}")
            continue
        q = by_disp.get(d)
        if not q:
            errs.append(f"{label}: expl key {k} has no question for display_number {d}")
            continue
        stem = _strip_tags(q.get("stem", ""))
        body = _strip_tags(str(text))
        sn = _nums(stem)
        en = _nums(body)
        if len(sn) >= 2 and len(en) >= 2 and not (sn & en):
            errs.append(
                f"{label}: display {d} — stem numbers {sorted(sn)[:8]}… vs expl numbers "
                f"{sorted(en)[:8]}… (no overlap; likely wrong pairing)"
            )
    return errs


def main() -> int:
    with open(BANK, encoding="utf-8") as f:
        bank = json.load(f)
    data_dir = os.path.join(APP_DIR, "data")
    checks = [
        (
            "Unit 1",
            "algebra",
            "unit_1_all",
            os.path.join(data_dir, "unit1_explanations_en.json"),
            os.path.join(data_dir, "unit1_question_manifest.json"),
        ),
        (
            "Unit 2",
            "advanced_math",
            "unit_2_all",
            os.path.join(data_dir, "unit2_explanations_en.json"),
            os.path.join(data_dir, "unit2_question_manifest.json"),
        ),
        (
            "Unit 3",
            "problem_solving",
            "unit_3_all",
            os.path.join(data_dir, "unit3_explanations_en.json"),
            os.path.join(data_dir, "unit3_question_manifest.json"),
        ),
        (
            "Unit 4",
            "geometry",
            "unit_4_all",
            os.path.join(data_dir, "unit4_explanations_en.json"),
            os.path.join(data_dir, "unit4_question_manifest.json"),
        ),
    ]
    all_errs: list[str] = []
    for label, dom, topic, ep, mp in checks:
        all_errs.extend(_check_unit(label, dom, topic, ep, mp, bank))
    if all_errs:
        print("verify_custom_explanations: FAILED", file=sys.stderr)
        for e in all_errs:
            print(e, file=sys.stderr)
        return 1
    print("verify_custom_explanations: OK (empty overrides or heuristics passed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
