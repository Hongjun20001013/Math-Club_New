#!/usr/bin/env python3
"""
Verify compiled question_bank.json matches Unit 1–3 masters + slices:
  - unit_1_all count == sum(1_1..1_5); stems align
  - unit_2_all count == sum(2_1..2_3); stems align
  - unit_3_all count == sum(3_1..3_7); stems align

Run: python3 scripts/verify_bank_alignment.py
"""

from __future__ import annotations

import json
import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK_PATH = os.path.join(APP_DIR, "data", "question_bank.json")
MANIFEST_PATH = os.path.join(APP_DIR, "data", "unit1_question_manifest.json")
MANIFEST2_PATH = os.path.join(APP_DIR, "data", "unit2_question_manifest.json")
MANIFEST3_PATH = os.path.join(APP_DIR, "data", "unit3_question_manifest.json")

SLICES = ["1_1", "1_2", "1_3", "1_4", "1_5"]
SECTION_LABEL = {
    "1_1": "1.1",
    "1_2": "1.2",
    "1_3": "1.3",
    "1_4": "1.4",
    "1_5": "1.5",
}

SLICES2 = ["2_1", "2_2", "2_3"]
SECTION2_LABEL = {
    "2_1": "2.1",
    "2_2": "2.2",
    "2_3": "2.3",
}

SLICES3 = ["3_1", "3_2", "3_3", "3_4", "3_5", "3_6", "3_7"]
SECTION3_LABEL = {
    "3_1": "3.1",
    "3_2": "3.2",
    "3_3": "3.3",
    "3_4": "3.4",
    "3_5": "3.5",
    "3_6": "3.6",
    "3_7": "3.7",
}


def _verify_unit(
    alg: dict,
    full_key: str,
    slice_keys: list[str],
    section_label: dict[str, str],
    label: str,
    manifest_path: str,
) -> int:
    full = alg.get(full_key)
    if not full:
        print(f"Missing domain payload {full_key!r}", file=sys.stderr)
        return 1

    parts: list[tuple[str, list]] = []
    total_slice = 0
    for key in slice_keys:
        q = alg.get(key)
        if not q:
            print(f"Missing slice key {key!r}", file=sys.stderr)
            return 1
        parts.append((key, q))
        total_slice += len(q)

    if len(full) != total_slice:
        print(
            f"Count mismatch: {full_key}={len(full)} sum(slices)={total_slice}",
            file=sys.stderr,
        )
        return 1

    gi = 0
    manifest: list[dict] = []
    for topic_key, qs in parts:
        for li, q in enumerate(qs):
            if q["stem"] != full[gi]["stem"]:
                print(
                    f"[{label}] Stem mismatch at global index {gi} ({topic_key} local {li})",
                    file=sys.stderr,
                )
                return 1
            manifest.append(
                {
                    "display_number": gi + 1,
                    "section": section_label[topic_key],
                    "topic_key": topic_key,
                    "topic_local_index": li,
                }
            )
            gi += 1

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"OK: {len(full)} {label} questions aligned; wrote {manifest_path}")
    for topic_key, qs in parts:
        print(f"  {section_label[topic_key]} ({topic_key}): {len(qs)}")
    return 0


def main() -> int:
    with open(BANK_PATH, encoding="utf-8") as f:
        bank = json.load(f)
    alg = bank.get("algebra", {})
    r1 = _verify_unit(
        alg, "unit_1_all", SLICES, SECTION_LABEL, "Unit 1", MANIFEST_PATH
    )
    if r1 != 0:
        return r1
    adv = bank.get("advanced_math", {})
    r2 = _verify_unit(
        adv, "unit_2_all", SLICES2, SECTION2_LABEL, "Unit 2", MANIFEST2_PATH
    )
    if r2 != 0:
        return r2
    ps = bank.get("problem_solving", {})
    r3 = _verify_unit(
        ps, "unit_3_all", SLICES3, SECTION3_LABEL, "Unit 3", MANIFEST3_PATH
    )
    return r3


if __name__ == "__main__":
    raise SystemExit(main())
