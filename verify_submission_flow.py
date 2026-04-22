import json
import os
import re
import sqlite3
from dataclasses import dataclass

from app import (
    APP_DIR,
    BANKS,
    DB_PATH,
    COMPILED_BANK_PATH,
    app,
    extract_correct_answer,
    get_questions_for_topic,
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def check_correct_answer_extraction() -> CheckResult:
    if not os.path.isfile(COMPILED_BANK_PATH):
        return CheckResult(
            "1) Correct answer extraction",
            False,
            "Missing data/question_bank.json (run scripts/build_question_bank.py)",
        )
    with open(COMPILED_BANK_PATH, "r", encoding="utf-8") as f:
        bank = json.load(f)
    qs = bank.get("algebra", {}).get("1_1")
    if not qs:
        return CheckResult("1) Correct answer extraction", False, "No algebra.1_1 in compiled bank")

    sample = qs[0]
    extracted = extract_correct_answer(sample)
    if extracted:
        return CheckResult(
            "1) Correct answer extraction",
            True,
            f"Extracted key = {extracted!r}",
        )
    return CheckResult(
        "1) Correct answer extraction",
        False,
        "Compiled question has no correct_answer",
    )


def run_web_flow_checks() -> list[CheckResult]:
    results: list[CheckResult] = []
    client = app.test_client()

    # Touch one practice page so before_request initializes DB and creates attempt.
    get_resp = client.get("/practice/algebra/1_1/0")
    if get_resp.status_code != 200:
        results.append(
            CheckResult(
                "2-4) Submission flow",
                False,
                f"GET /practice/algebra/1_1/0 failed with {get_resp.status_code}",
            )
        )
        return results

    html = get_resp.get_data(as_text=True)
    m = re.search(r'name="attempt_id"\s+value="(\d+)"', html)
    if not m:
        results.append(CheckResult("2) attempt_id pass-through", False, "attempt_id hidden input missing"))
        return results
    attempt_id = int(m.group(1))
    results.append(CheckResult("2) attempt_id pass-through", True, f"attempt_id={attempt_id} found in question page"))

    conn = sqlite3.connect(DB_PATH)
    try:
        has_attempts = table_exists(conn, "practice_attempts")
        has_responses = table_exists(conn, "practice_responses")
        if not (has_attempts and has_responses):
            results.append(
                CheckResult(
                    "3) SQLite response insert",
                    False,
                    f"Missing tables: attempts={has_attempts}, responses={has_responses}",
                )
            )
            return results

        before_count = count_rows(conn, "practice_responses")

        m_total = re.search(r'class="progress-total">(\d+)', html)
        if not m_total:
            results.append(CheckResult("3) SQLite response insert", False, "Could not parse progress-total"))
            return results
        total = int(m_total.group(1))
        last_idx = total - 1

        last_get = client.get(f"/practice/algebra/1_1/{last_idx}")
        if last_get.status_code != 200:
            results.append(
                CheckResult(
                    "3) SQLite response insert",
                    False,
                    f"GET last question failed: {last_get.status_code}",
                )
            )
            return results
        last_html = last_get.get_data(as_text=True)
        m2 = re.search(r'name="attempt_id"\s+value="(\d+)"', last_html)
        if not m2:
            results.append(CheckResult("3) SQLite response insert", False, "attempt_id missing on last question"))
            return results
        attempt_id = int(m2.group(1))

        qs = get_questions_for_topic("algebra", "1_1", BANKS["algebra"]["1_1"])
        last_key = extract_correct_answer(qs[last_idx]) if qs and last_idx < len(qs) else None
        final_pick = (last_key or "A").strip().upper()[:1]

        post_resp = client.post(
            "/practice/submit",
            data={
                "attempt_id": str(attempt_id),
                "domain": "algebra",
                "topic": "1_1",
                "qnum": str(last_idx),
                "selected_answer": final_pick,
            },
            follow_redirects=True,
        )
        if post_resp.status_code != 200:
            results.append(
                CheckResult(
                    "3) SQLite response insert",
                    False,
                    f"POST /practice/submit failed with {post_resp.status_code}",
                )
            )
            return results

        after_count = count_rows(conn, "practice_responses")
        if after_count <= before_count:
            results.append(
                CheckResult(
                    "3) SQLite response insert",
                    False,
                    f"Response count did not increase ({before_count} -> {after_count})",
                )
            )
        else:
            latest = conn.execute(
                """
                SELECT pr.attempt_id, pr.selected_answer, pr.question_index, pa.id
                FROM practice_responses pr
                LEFT JOIN practice_attempts pa ON pa.id = pr.attempt_id
                ORDER BY pr.id DESC
                LIMIT 1
                """
            ).fetchone()
            linked_ok = latest is not None and latest[3] is not None
            idx_ok = latest is not None and latest[2] == last_idx
            results.append(
                CheckResult(
                    "3) SQLite response insert",
                    linked_ok and idx_ok,
                    f"Rows {before_count} -> {after_count}; link={linked_ok}; question_index={latest[2] if latest else None}",
                )
            )

        result_html = post_resp.get_data(as_text=True)
        required_tokens = [
            "Your results",
            "Session complete",
            "Practice this topic again",
        ]
        missing = [t for t in required_tokens if t not in result_html]
        results.append(
            CheckResult(
                "4) Session summary page",
                len(missing) == 0,
                "Missing tokens: " + ", ".join(missing) if missing else "Summary page rendered expected sections",
            )
        )
    finally:
        conn.close()

    return results


def check_route_and_template_consistency() -> CheckResult:
    route_ok = "submit_practice_answer" in app.view_functions
    pq_path = os.path.join(APP_DIR, "templates/practice_question.html")
    rs_path = os.path.join(APP_DIR, "templates/result.html")
    if not (os.path.exists(pq_path) and os.path.exists(rs_path)):
        return CheckResult("5) Route/template consistency", False, "Missing expected template files")

    with open(pq_path, "r", encoding="utf-8") as f:
        pq = f.read()
    with open(rs_path, "r", encoding="utf-8") as f:
        rs = f.read()

    form_ok = "url_for('submit_practice_answer')" in pq
    inputs_ok = all(
        token in pq
        for token in ('name="attempt_id"', 'name="domain"', 'name="topic"', 'name="qnum"', 'name="selected_answer"')
    )
    result_tokens_ok = all(token in rs for token in ("correct", "total", "score_pct", "detailed"))

    ok = route_ok and form_ok and inputs_ok and result_tokens_ok
    detail = (
        f"route={route_ok}, form_action={form_ok}, hidden_inputs={inputs_ok}, "
        f"result_tokens={result_tokens_ok}"
    )
    return CheckResult("5) Route/template consistency", ok, detail)


def main() -> int:
    checks = [check_correct_answer_extraction()]
    checks.extend(run_web_flow_checks())
    checks.append(check_route_and_template_consistency())

    print("\n=== SAT Submission Flow Verification ===")
    failed = 0
    for item in checks:
        status = "PASS" if item.ok else "FAIL"
        print(f"[{status}] {item.name}: {item.detail}")
        if not item.ok:
            failed += 1

    print(f"\nTotal: {len(checks)} checks, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
