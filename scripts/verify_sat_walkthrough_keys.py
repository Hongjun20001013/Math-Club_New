#!/usr/bin/env python3
"""Verify every key in data/sat_extended_walkthroughs.json maps to a real question slot."""

from __future__ import annotations

import json
import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK_PATH = os.path.join(APP_DIR, "data", "question_bank.json")
WT_PATH = os.path.join(APP_DIR, "data", "sat_extended_walkthroughs.json")


def main() -> int:
    if not os.path.isfile(WT_PATH):
        print("OK: no sat_extended_walkthroughs.json")
        return 0
    with open(WT_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    wt = raw.get("walkthroughs")
    if not isinstance(wt, dict):
        print("OK: no walkthroughs object")
        return 0
    with open(BANK_PATH, encoding="utf-8") as f:
        bank = json.load(f)

    errs: list[str] = []
    for key, val in wt.items():
        parts = str(key).split(":")
        if len(parts) != 3:
            errs.append(f"Bad key format (want domain:topic:idx): {key!r}")
            continue
        dom, tk, idx_s = parts
        try:
            idx = int(idx_s)
        except ValueError:
            errs.append(f"Bad index in key: {key!r}")
            continue
        qs = (bank.get(dom) or {}).get(tk)
        if not isinstance(qs, list) or idx < 0 or idx >= len(qs):
            errs.append(f"Unknown slot or index out of range: {key!r}")
            continue
        if isinstance(val, dict):
            t = (val.get("text") or val.get("en") or "").strip()
        else:
            t = str(val).strip()
        if not t:
            errs.append(f"Empty walkthrough text for {key!r}")

    if errs:
        print("verify_sat_walkthrough_keys: FAILED", file=sys.stderr)
        for e in errs:
            print(e, file=sys.stderr)
        return 1
    print(f"verify_sat_walkthrough_keys: OK ({len(wt)} keys)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
