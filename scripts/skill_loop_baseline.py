#!/usr/bin/env python3
"""Print baseline counts + SHA-256 of question_bank.json. Read-only."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = os.path.join(ROOT, "data", "question_bank.json")
MATERIALS = os.path.join(ROOT, "data", "course_materials.json")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def bank_question_count(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    total = 0
    for topics in payload.values():
        for qs in topics.values():
            if isinstance(qs, list):
                total += len(qs)
    return total


def baseline(db_path: str) -> dict:
    with open(MATERIALS, encoding="utf-8") as fh:
        materials_total = int(json.load(fh).get("total") or 0)
    out = {
        "question_bank_sha256": sha256_file(BANK),
        "question_bank_count": bank_question_count(BANK),
        "course_materials_count": materials_total,
    }
    conn = sqlite3.connect(f"file:{os.path.abspath(db_path)}?mode=ro", uri=True)
    try:
        def count(table: str) -> int:
            return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])

        out["users"] = count("users")
        out["practice_attempts"] = count("practice_attempts")
        out["practice_responses"] = count("practice_responses")
        out["mistake_learning_progress"] = count("mistake_learning_progress")
    finally:
        conn.close()
    return out


def main() -> int:
    db = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "sat.db")
    data = baseline(db)
    for k, v in data.items():
        print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
