#!/usr/bin/env python3
"""Run content, database, and config sanity checks for Novel Prep SAT app."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _run(script: str) -> tuple[int, str]:
    path = os.path.join(ROOT, "scripts", script)
    if not os.path.isfile(path):
        return 0, f"skip {script} (missing)"
    proc = subprocess.run(
        [sys.executable, path],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def _scan_course_materials() -> list[str]:
    path = os.path.join(ROOT, "data", "course_materials.json")
    if not os.path.isfile(path):
        return ["missing data/course_materials.json"]
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    issues: list[str] = []
    for mat in payload.get("materials", []):
        slug = mat.get("slug", "")
        for i, slide in enumerate(mat.get("slides", []), 1):
            html = slide.get("html", "")
            stripped = re.sub(r"\\[\(\[].*?\\[\)\]]", "", html, flags=re.S)
            stripped = re.sub(r"<[^>]+>", " ", stripped)
            if re.search(r"(?<!\\)\\(?:begin\{choices\}|choice\b)", stripped):
                issues.append(f"{slug} slide {i}: raw \\choice markup")
            if re.search(r"cm-answer-card-value\">[^<]*\\boxed\{[^}]+\}[^<]*[a-z]", html):
                if not re.search(r"cm-answer-card-math", html):
                    issues.append(f"{slug} slide {i}: raw \\boxed answer")
            if re.search(r"\\\\\)", stripped):
                issues.append(f"{slug} slide {i}: leaked \\)")
    return issues


def _scan_question_bank() -> list[str]:
    path = os.path.join(ROOT, "data", "question_bank.json")
    if not os.path.isfile(path):
        return ["missing data/question_bank.json"]
    with open(path, encoding="utf-8") as fh:
        bank = json.load(fh)
    issues: list[str] = []
    for domain, topics in bank.items():
        if not isinstance(topics, dict):
            continue
        for topic, qs in topics.items():
            if not isinstance(qs, list):
                continue
            for j, q in enumerate(qs, 1):
                if q.get("question_kind") == "mcq" and not q.get("correct_answer"):
                    issues.append(f"{domain}/{topic} Q{j}: MCQ missing correct_answer")
                stem = str(q.get("stem") or "")
                if re.search(r"\\begin\{choices\}|\\\\\)", stem):
                    issues.append(f"{domain}/{topic} Q{j}: LaTeX leak in stem")
    return issues


def _scan_database() -> list[str]:
    db_path = os.environ.get("DB_PATH", os.path.join(ROOT, "sat.db"))
    if not os.path.isfile(db_path):
        return [f"skip DB checks ({db_path} not found)"]
    db = sqlite3.connect(db_path)
    issues: list[str] = []
    orphan_resp = db.execute(
        """
        SELECT COUNT(*) FROM practice_responses pr
        LEFT JOIN practice_attempts pa ON pa.id = pr.attempt_id
        WHERE pa.id IS NULL
        """
    ).fetchone()[0]
    if orphan_resp:
        issues.append(f"orphan practice_responses: {orphan_resp}")
    plaintext = db.execute(
        "SELECT COUNT(*) FROM users WHERE password IS NOT NULL AND TRIM(password) != ''"
    ).fetchone()[0]
    if plaintext:
        issues.append(f"users with legacy plaintext password column: {plaintext}")
    no_cred = db.execute(
        """
        SELECT COUNT(*) FROM users
        WHERE (password_hash IS NULL OR TRIM(password_hash) = '')
          AND (password IS NULL OR TRIM(password) = '')
        """
    ).fetchone()[0]
    if no_cred:
        issues.append(f"users without password credentials: {no_cred}")
    db.close()
    return issues


def main() -> int:
    print("=== Novel Prep system health check ===\n")
    failed = 0

    for script in (
        "verify_bank_alignment.py",
        "verify_unit4_bank_matches_master.py",
        "verify_custom_explanations.py",
        "verify_sat_walkthrough_keys.py",
    ):
        code, out = _run(script)
        status = "OK" if code == 0 else "FAIL"
        print(f"[{status}] {script}")
        if out:
            print(out.splitlines()[-1])
        if code != 0:
            failed += 1

    print("\n--- Course materials ---")
    cm_issues = _scan_course_materials()
    if cm_issues:
        failed += 1
        for item in cm_issues[:20]:
            print("FAIL", item)
        if len(cm_issues) > 20:
            print(f"... and {len(cm_issues) - 20} more")
    else:
        print("OK: no LaTeX leak patterns detected")

    print("\n--- Question bank ---")
    qb_issues = _scan_question_bank()
    if qb_issues:
        failed += 1
        for item in qb_issues[:20]:
            print("FAIL", item)
        if len(qb_issues) > 20:
            print(f"... and {len(qb_issues) - 20} more")
    else:
        print("OK: MCQ keys and stems look clean")

    print("\n--- Database ---")
    db_issues = _scan_database()
    for item in db_issues:
        if item.startswith("skip"):
            print(item)
        elif item:
            print("FAIL", item)
            failed += 1
    if not db_issues or all(i.startswith("skip") for i in db_issues):
        pass
    elif not any(not i.startswith("skip") for i in db_issues):
        print("OK: referential integrity and credentials look clean")

    print(f"\n=== Done: {failed} failing check(s) ===")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
