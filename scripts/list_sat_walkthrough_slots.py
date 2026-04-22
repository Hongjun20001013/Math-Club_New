#!/usr/bin/env python3
"""
List SAT extended-walkthrough *authoring* slots for Unit 1–3 slices in data/question_bank.json.

After each build, every question already receives an auto-generated Full walkthrough in
question_bank.json. This script lists keys for data/sat_extended_walkthroughs.json so you
can add **custom** long-form steps where you want to replace the template.

Usage:
  python3 scripts/list_sat_walkthrough_slots.py              # TSV: key, has_author_json, stem_preview
  python3 scripts/list_sat_walkthrough_slots.py --missing     # keys with no JSON override yet
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK_PATH = os.path.join(APP_DIR, "data", "question_bank.json")
WT_PATH = os.path.join(APP_DIR, "data", "sat_extended_walkthroughs.json")

DOMAINS = ("algebra", "advanced_math", "problem_solving")


def _strip(s: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", s or "").split())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--missing",
        action="store_true",
        help="Only print keys that have no entry in sat_extended_walkthroughs.json",
    )
    args = p.parse_args()

    with open(BANK_PATH, encoding="utf-8") as f:
        bank = json.load(f)
    wt: dict = {}
    if os.path.isfile(WT_PATH):
        with open(WT_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        w = raw.get("walkthroughs")
        if isinstance(w, dict):
            wt = w

    rows: list[tuple[str, bool, str]] = []
    for domain in DOMAINS:
        dom = bank.get(domain) or {}
        for topic_key, qs in dom.items():
            if not isinstance(qs, list) or topic_key.startswith("unit_"):
                continue
            for i, q in enumerate(qs):
                key = f"{domain}:{topic_key}:{i}"
                has = bool(
                    wt.get(key)
                    if not isinstance(wt.get(key), dict)
                    else (wt.get(key) or {}).get("text") or (wt.get(key) or {}).get("en")
                )
                prev = _strip(q.get("stem", ""))[:88]
                rows.append((key, has, prev))

    if args.missing:
        rows = [r for r in rows if not r[1]]

    print("key\thas_author_json\tstem_preview")
    for key, has, prev in rows:
        prev = prev.replace("\t", " ")
        print(f"{key}\t{int(has)}\t{prev}")
    print(f"# total rows: {len(rows)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
