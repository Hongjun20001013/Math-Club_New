"""Practice choice restore, review-only redo, and Repair-this-skill clustering.

Does not connect to production, does not modify data/question_bank.json.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LIVE_DB = os.path.join(ROOT, "sat.db")
BANK = os.path.join(ROOT, "data", "question_bank.json")


def copy_db(dest: str) -> None:
    shutil.copy2(LIVE_DB, dest)


class PracticeRestoreAndRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sat-restore-")
        self.db = os.path.join(self.tmp, "sat.db")
        copy_db(self.db)
        import app as app_mod

        self.app_mod = app_mod
        self._orig_db = app_mod.DB_PATH
        self._orig_ready = app_mod._DB_SCHEMA_READY
        app_mod.DB_PATH = self.db
        app_mod._DB_SCHEMA_READY = False
        app_mod.app.config["TESTING"] = True
        app_mod.app.config["SKILL_LOOP_PILOT"] = False
        app_mod.app.config["SKILL_REPAIR"] = True
        os.environ.pop("SKILL_LOOP_PILOT", None)
        os.environ.pop("SKILL_REPAIR", None)
        self.client = app_mod.app.test_client()

    def tearDown(self):
        self.app_mod.DB_PATH = self._orig_db
        self.app_mod._DB_SCHEMA_READY = self._orig_ready
        shutil.rmtree(self.tmp, ignore_errors=True)

    def login(self, user_id=2, role="student", username="s1"):
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_role"] = role
            sess["username"] = username
            sess["csrf_token"] = "test-csrf"

    def test_get_creates_attempt_and_native_radios(self):
        self.login()
        rv = self.client.get("/practice/algebra/1_1/0")
        self.assertEqual(rv.status_code, 200)
        html = rv.get_data(as_text=True)
        self.assertIn('type="radio"', html)
        self.assertIn('class="choice-radio-input"', html)
        self.assertIn('name="selected_answer"', html)
        self.assertIn('id="practice-answer-form"', html)
        self.assertRegex(html, r'name="attempt_id" value="[1-9]')

    def test_draft_previous_restores_choice_from_session(self):
        self.login()
        first = self.client.get("/practice/algebra/1_1/0")
        html = first.get_data(as_text=True)
        import re

        m = re.search(r'name="attempt_id" value="(\d+)"', html)
        self.assertIsNotNone(m)
        attempt_id = m.group(1)
        rv = self.client.post(
            "/practice/draft-answer",
            data={
                "csrf_token": "test-csrf",
                "domain": "algebra",
                "topic": "1_1",
                "qnum": "0",
                "goto_qnum": "1",
                "attempt_id": attempt_id,
                "selected_answer": "B",
            },
            headers={"X-CSRF-Token": "test-csrf"},
            follow_redirects=False,
        )
        self.assertEqual(rv.status_code, 302)
        back = self.client.get("/practice/algebra/1_1/0")
        back_html = back.get_data(as_text=True)
        self.assertIn('value="B" checked', back_html.replace("checked=\"checked\"", "checked"))
        self.assertRegex(back_html, r'value="B"[^>]*checked|checked[^>]*value="B"')

    def test_submitted_answer_restores_on_previous(self):
        self.login()
        first = self.client.get("/practice/algebra/1_1/0")
        html = first.get_data(as_text=True)
        import re

        m = re.search(r'name="attempt_id" value="(\d+)"', html)
        attempt_id = m.group(1)
        self.client.post(
            "/practice/submit",
            data={
                "csrf_token": "test-csrf",
                "domain": "algebra",
                "topic": "1_1",
                "qnum": "0",
                "attempt_id": attempt_id,
                "selected_answer": "C",
            },
            follow_redirects=False,
        )
        back = self.client.get("/practice/algebra/1_1/0")
        back_html = back.get_data(as_text=True)
        self.assertRegex(back_html, r'value="C"[^>]*checked|checked[^>]*value="C"')

    def test_original_redo_correct_is_review_not_mastered(self):
        self.login()
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            lk = self.app_mod._learner_key_for_user(2)
            db.execute(
                """
                INSERT INTO mistake_learning_progress
                    (learner_key, domain, topic, question_index, status, correct_after_last_wrong)
                VALUES (?, 'algebra', '1_1', 0, 'unreviewed', 0)
                """,
                (lk,),
            )
            db.commit()
            self.app_mod._apply_practice_mistake_progress(
                db, lk, 1, "algebra", "1_1", 0, 1, mistake_redo=True
            )
            db.commit()
            row = db.execute(
                """
                SELECT status FROM mistake_learning_progress
                WHERE learner_key = ? AND domain = 'algebra' AND topic = '1_1' AND question_index = 0
                """,
                (lk,),
            ).fetchone()
            self.assertEqual(row["status"], "reviewed")
            self.app_mod._apply_practice_mistake_progress(
                db, lk, 1, "algebra", "1_1", 0, 1, mistake_redo=True
            )
            db.commit()
            row = db.execute(
                """
                SELECT status FROM mistake_learning_progress
                WHERE learner_key = ? AND domain = 'algebra' AND topic = '1_1' AND question_index = 0
                """,
                (lk,),
            ).fetchone()
            self.assertNotEqual(row["status"], "mastered")

    def test_archive_button_is_not_mastery(self):
        self.login()
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            lk = self.app_mod._learner_key_for_user(2)
            self.app_mod._mistake_progress_archive(db, lk, "algebra", "1_1", 0)
            db.commit()
            row = db.execute(
                """
                SELECT status FROM mistake_learning_progress
                WHERE learner_key = ? AND domain = 'algebra' AND topic = '1_1' AND question_index = 0
                """,
                (lk,),
            ).fetchone()
            self.assertEqual(row["status"], "archived")

    def test_analytics_recommends_one_next_step_and_does_not_expand_all(self):
        self.login()
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            aid = db.execute(
                "INSERT INTO practice_attempts (user_id, domain, topic, qnum) VALUES (2, 'algebra', '1_1', 0)"
            ).lastrowid
            for i in range(5):
                db.execute(
                    """
                    INSERT INTO practice_responses
                        (attempt_id, question_index, selected_answer, correct_answer, is_correct)
                    VALUES (?, ?, 'A', 'B', 0)
                    """,
                    (aid, i),
                )
            db.commit()
        rv = self.client.get("/practice/analytics")
        html = rv.get_data(as_text=True)
        self.assertEqual(rv.status_code, 200)
        self.assertIn("Repair this skill", html)
        self.assertIn("One next step", html)
        self.assertNotIn("Mark mastered", html)
        unit = self.client.get("/practice/analytics?part=unit1")
        unit_html = unit.get_data(as_text=True)
        self.assertIn("Archive from mistake list", unit_html)
        self.assertIn("Show ", unit_html)
        self.assertIn("review only", unit_html.lower())

    def test_repair_flow_uses_required_phases_and_blocks_original_independent(self):
        import skill_repair as sr

        self.login()
        rv = self.client.get("/practice/repair/sat.alg.linear_rate_remaining/start", follow_redirects=False)
        self.assertEqual(rv.status_code, 302)
        self.assertIn("/worked", rv.headers.get("Location", ""))
        page = self.client.get("/practice/repair/sat.alg.linear_rate_remaining/worked")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Continue to faded example", html)
        cont = self.client.post(
            "/practice/repair/sat.alg.linear_rate_remaining/submit",
            data={"csrf_token": "test-csrf", "phase": "worked"},
            follow_redirects=False,
        )
        self.assertEqual(cont.status_code, 302)
        self.assertIn("/faded", cont.headers.get("Location", ""))
        self.assertEqual(
            sr.counts_as_independent(
                phase="isomorphic",
                is_correct=True,
                solution_viewed=True,
                hint_level="none",
                is_original=False,
                saw_answer=False,
            ),
            0,
        )
        self.assertEqual(
            sr.counts_as_independent(
                phase="isomorphic",
                is_correct=True,
                solution_viewed=False,
                hint_level="none",
                is_original=True,
                saw_answer=False,
            ),
            0,
        )
        self.assertEqual(
            sr.counts_as_independent(
                phase="delayed",
                is_correct=True,
                solution_viewed=False,
                hint_level="none",
                is_original=False,
                saw_answer=False,
            ),
            1,
        )

    def test_cluster_does_not_default_expand_and_maps_primary_skill(self):
        import skill_repair as sr

        rows = [
            {
                "stem_html": "<p>A tank starts with 8400 gallons. After 3 hours, 6900 remain at a constant rate.</p>",
                "knowledge_title": "Linear remaining",
                "knowledge_section": "1.1",
                "domain": "algebra",
                "topic": "1_1",
                "q_index": 2,
                "pr_id": 9,
                "yours": "A",
                "key": "C",
                "when": "2026-08-01",
                "mastery_effective": "unreviewed",
                "diagnosis_label": "Setup / modeling",
                "tag_labels": ["setup"],
                "pattern_pack": {"pitfall": "Adding the opening hours twice."},
                "practice_href": "/x",
            },
            {
                "stem_html": "<p>Solve 2x+3=11.</p>",
                "knowledge_title": "Solve linear equations",
                "knowledge_section": "1.1",
                "domain": "algebra",
                "topic": "1_1",
                "q_index": 3,
                "pr_id": 10,
                "yours": "B",
                "key": "A",
                "when": "2026-08-02",
                "mastery_effective": "unreviewed",
                "diagnosis_label": "Execution",
                "tag_labels": [],
                "pattern_pack": {},
                "practice_href": "/y",
            },
        ]
        clusters = sr.cluster_wrong_rows(rows, pack_backed=True)
        self.assertGreaterEqual(len(clusters), 1)
        codes = {c["code"] for c in clusters}
        self.assertIn("sat.alg.linear_rate_remaining", codes)
        self.assertIn("sat.alg.solve_linear_equation", codes)
        self.assertTrue(all(not str(c["code"]).startswith("bank.") for c in clusters))
        nxt = sr.recommended_next_step(clusters)
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt["miss_count"], clusters[0]["miss_count"])
        for cluster in clusters:
            blob = f"{cluster.get('stuck_label')} {cluster.get('common_stuck')}".lower()
            self.assertNotIn("inequality", blob)
            self.assertNotIn("flip the inequality", blob)
            self.assertEqual(cluster["stuck_label"], "Possible focus")
            if cluster["code"] == "sat.alg.solve_linear_equation":
                self.assertIn("需要进一步诊断", cluster["common_stuck"])
            if cluster["code"] == "sat.alg.linear_rate_remaining":
                self.assertIn("Student tagged", cluster["common_stuck"])

    def test_repair_stem_solution_html_and_unseen_items(self):
        import re
        import skill_repair as sr
        from repair_html import sanitize_repair_html

        dirty = '<article class="np-solution-pro"><section class="np-sol-block">Safe</section><script>alert(1)</script><img src="javascript:alert(1)"><a href="https://ok.example">ok</a></article>'
        clean = sanitize_repair_html(dirty)
        self.assertIn("Safe", clean)
        self.assertNotIn("<script", clean.lower())
        self.assertNotIn("javascript:", clean.lower())
        self.assertIn("https://ok.example", clean)

        self.login()
        blocked = self.client.get("/practice/repair/bank.algebra.1.1/start", follow_redirects=False)
        self.assertEqual(blocked.status_code, 302)
        self.assertIn("/practice/analytics", blocked.headers.get("Location", ""))

        start = self.client.get("/practice/repair/sat.alg.linear_rate_remaining/start", follow_redirects=False)
        self.assertEqual(start.status_code, 302)
        worked = self.client.get("/practice/repair/sat.alg.linear_rate_remaining/worked")
        html = worked.get_data(as_text=True)
        self.assertEqual(worked.status_code, 200)
        self.assertIn("holding-tank log", html)
        self.assertIn("Strategy", html)
        self.assertIn("Verified key", html)
        self.assertIn("Full walkthrough", html)
        self.assertNotIn("&lt;article class=", html)
        self.assertIn('data-sl-stem', html)
        self.client.post(
            "/practice/repair/sat.alg.linear_rate_remaining/submit",
            data={"csrf_token": "test-csrf", "phase": "worked"},
            follow_redirects=False,
        )
        faded = self.client.get("/practice/repair/sat.alg.linear_rate_remaining/faded")
        faded_html = faded.get_data(as_text=True)
        self.assertEqual(faded.status_code, 200)
        self.assertIn('data-sl-stem', faded_html)
        self.assertIn("cooling vat", faded_html)
        self.assertIn("data-faded-blank", faded_html)
        faded_id = re.search(r'data-item-id="([^"]+)"', faded_html).group(1)
        faded_hash = re.search(r'data-stem-hash="([^"]+)"', faded_html).group(1)
        self.client.post(
            "/practice/repair/sat.alg.linear_rate_remaining/submit",
            data={
                "csrf_token": "test-csrf",
                "phase": "faded",
                "rate": "1",
                "total_hours": "1",
                "hint_level": "none",
                "solution_viewed": "0",
            },
            follow_redirects=True,
        )
        faded2 = self.client.get("/practice/repair/sat.alg.linear_rate_remaining/faded")
        faded2_html = faded2.get_data(as_text=True)
        faded2_id = re.search(r'data-item-id="([^"]+)"', faded2_html).group(1)
        faded2_hash = re.search(r'data-stem-hash="([^"]+)"', faded2_html).group(1)
        self.assertNotEqual(faded_id, faded2_id)
        self.assertNotEqual(faded_hash, faded2_hash)
        self.assertIn("salt brine", faded2_html)
        self.client.post(
            "/practice/repair/sat.alg.linear_rate_remaining/submit",
            data={
                "csrf_token": "test-csrf",
                "phase": "faded",
                "removed_amount": "720",
                "start_amount": "2880",
                "hint_level": "none",
                "solution_viewed": "0",
            },
            follow_redirects=True,
        )
        iso = self.client.get("/practice/repair/sat.alg.linear_rate_remaining/isomorphic")
        iso_html = iso.get_data(as_text=True)
        iso_id = re.search(r'data-item-id="([^"]+)"', iso_html).group(1)
        iso_hash = re.search(r'data-stem-hash="([^"]+)"', iso_html).group(1)
        self.assertNotEqual(iso_id, faded_id)
        self.assertNotEqual(iso_id, faded2_id)
        self.assertNotEqual(iso_hash, faded_hash)
        self.assertIn("surveyor remaining-mass", iso_html)
        event = self.client.post(
            "/practice/repair/sat.alg.linear_rate_remaining/event",
            data={"csrf_token": "test-csrf", "kind": "hint_light"},
        )
        light = event.get_json()["hint"]
        event2 = self.client.post(
            "/practice/repair/sat.alg.linear_rate_remaining/event",
            data={"csrf_token": "test-csrf", "kind": "hint_critical"},
        )
        critical = event2.get_json()["hint"]
        self.assertTrue(light)
        self.assertTrue(critical)
        self.assertNotEqual(light, critical)
        sol = self.client.post(
            "/practice/repair/sat.alg.linear_rate_remaining/event",
            data={"csrf_token": "test-csrf", "kind": "solution"},
        ).get_json()
        self.assertIn("Strategy", sol["html"])
        self.assertIn("Verified key", sol["html"])
        self.assertIn("Full walkthrough", sol["html"])
        self.assertNotIn("<script", sol["html"].lower())
        self.assertEqual(
            sr.counts_as_independent(
                phase="isomorphic",
                is_correct=True,
                solution_viewed=False,
                hint_level="none",
                is_original=False,
                saw_answer=False,
                appeared_in_teaching=True,
            ),
            0,
        )
        reasons = sr.independent_block_reasons(
            phase="faded",
            is_correct=True,
            solution_viewed=False,
            hint_level="none",
            is_original=False,
            saw_answer=False,
        )
        self.assertIn("Not an independent stage", reasons)
        self.assertNotIn("solution/hint was used, or this was a seen item", " ".join(reasons))

    def test_no_solution_worked_example_shows_full_key(self):
        self.login()
        self.client.get("/practice/repair/sat.alg.no_solution_parameter/start")
        html = self.client.get("/practice/repair/sat.alg.no_solution_parameter/worked").get_data(as_text=True)
        self.assertIn("Which statement must be true about k", html)
        self.assertIn("k ≠ 5", html)
        self.assertIn("k = 2", html)
        self.assertIn("k = 5", html)
        self.assertIn("Mathematical conclusion", html)
        self.client.post(
            "/practice/repair/sat.alg.no_solution_parameter/submit",
            data={"csrf_token": "test-csrf", "phase": "worked"},
        )
        faded = self.client.get("/practice/repair/sat.alg.no_solution_parameter/faded").get_data(as_text=True)
        self.assertIn("3(y + 1) = 3y + m", faded)
        self.assertIn("data-faded-blank", faded)
        self.assertIn("For no solution, m must satisfy", faded)

    def test_start_resumes_same_delayed_run_without_resetting_clock(self):
        import json
        import skill_repair as sr

        self.login()
        due = "2026-08-22T17:30:29Z"
        payload = {
            "source": "pack",
            "instruction_completed_at": "2026-08-20T10:00:00Z",
            "seen_item_ids": ["slq_lrr_example_01"],
        }
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            sr.ensure_repair_tables(db)
            db.execute(
                """
                INSERT INTO skill_repair_sessions (
                    user_id, skill_code, current_phase, current_variant, status,
                    delayed_available_at, payload_json, updated_at
                ) VALUES (2, 'sat.alg.linear_rate_remaining', 'delayed', 1, 'delayed_wait', ?, ?, datetime('now'))
                """,
                (due, json.dumps(payload)),
            )
            db.commit()
            before = db.execute(
                "SELECT id, delayed_available_at, payload_json, status FROM skill_repair_sessions WHERE user_id=2 AND skill_code=?",
                ("sat.alg.linear_rate_remaining",),
            ).fetchall()
            self.assertEqual(len(before), 1)
            sid = before[0]["id"]
        first = self.client.get("/practice/repair/sat.alg.linear_rate_remaining/start", follow_redirects=False)
        self.assertEqual(first.status_code, 302)
        self.assertIn("/delayed", first.headers.get("Location", ""))
        wait = self.client.get("/practice/repair/sat.alg.linear_rate_remaining/delayed")
        wait_html = wait.get_data(as_text=True)
        self.assertIn(due, wait_html)
        self.assertIn("not mastered", wait_html.lower())
        second = self.client.get("/practice/repair/sat.alg.linear_rate_remaining/start", follow_redirects=False)
        self.assertIn("/delayed", second.headers.get("Location", ""))
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            after = db.execute(
                "SELECT id, delayed_available_at, payload_json, status FROM skill_repair_sessions WHERE user_id=2 AND skill_code=?",
                ("sat.alg.linear_rate_remaining",),
            ).fetchall()
            self.assertEqual(len(after), 1)
            self.assertEqual(after[0]["id"], sid)
            self.assertEqual(after[0]["delayed_available_at"], due)
            self.assertEqual(after[0]["status"], "delayed_wait")
            loaded = json.loads(after[0]["payload_json"])
            self.assertEqual(loaded.get("instruction_completed_at"), "2026-08-20T10:00:00Z")
            self.assertEqual(loaded.get("seen_item_ids"), ["slq_lrr_example_01"])

    def _hard21_attempt_id(self, html: str) -> str:
        import re

        m = re.search(r'name="attempt_id" value="(\d+)"', html)
        self.assertIsNotNone(m)
        return m.group(1)

    def test_mock_test1_fresh_attempt_is_clickable(self):
        self.login()
        self.client.get("/practice/hard_problem/hard_21/new-session", follow_redirects=False)
        rv = self.client.get("/practice/hard_problem/hard_21/0")
        self.assertEqual(rv.status_code, 200)
        html = rv.get_data(as_text=True)
        self.assertIn("const phase3AnswerLocked = false;", html)
        self.assertIn("Start this mock over", html)
        self.assertIn('class="choice-radio-input"', html)
        self.assertNotIn("choice-radio-input\" name=\"selected_answer\" value=\"A\" checked", html)

    def test_mock_test1_empty_response_does_not_lock(self):
        self.login()
        self.client.get("/practice/hard_problem/hard_21/new-session", follow_redirects=False)
        first = self.client.get("/practice/hard_problem/hard_21/0")
        self.assertEqual(first.status_code, 200)
        aid = int(self._hard21_attempt_id(first.get_data(as_text=True)))
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            db.execute(
                """
                INSERT INTO practice_responses
                    (attempt_id, question_index, selected_answer, correct_answer, is_correct)
                VALUES (?, 0, '', 'A', 0)
                """,
                (aid,),
            )
            db.commit()
        rv = self.client.get("/practice/hard_problem/hard_21/0")
        html = rv.get_data(as_text=True)
        self.assertEqual(rv.status_code, 200)
        self.assertIn("const phase3AnswerLocked = false;", html)

    def test_mock_test1_submitted_choice_stays_editable(self):
        self.login()
        self.client.get("/practice/hard_problem/hard_21/new-session", follow_redirects=False)
        first = self.client.get("/practice/hard_problem/hard_21/0")
        self.assertEqual(first.status_code, 200)
        aid = int(self._hard21_attempt_id(first.get_data(as_text=True)))
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            db.execute(
                """
                INSERT INTO practice_responses
                    (attempt_id, question_index, selected_answer, correct_answer, is_correct)
                VALUES (?, 0, 'B', 'A', 0)
                """,
                (aid,),
            )
            db.commit()
        rv = self.client.get("/practice/hard_problem/hard_21/0")
        html = rv.get_data(as_text=True)
        self.assertEqual(rv.status_code, 200)
        self.assertIn("const phase3AnswerLocked = false;", html)
        self.assertRegex(html, r'value="B"[^>]*checked|checked[^>]*value="B"')
        self.assertNotIn("disabled", html.split("choice-radio-input", 1)[-1][:180])

    def test_hard_question_submit_can_change_answer(self):
        self.login()
        self.client.get("/practice/hard_problem/hard_21/new-session", follow_redirects=False)
        first = self.client.get("/practice/hard_problem/hard_21/0")
        aid = self._hard21_attempt_id(first.get_data(as_text=True))
        self.client.post(
            "/practice/submit",
            data={
                "csrf_token": "test-csrf",
                "domain": "hard_problem",
                "topic": "hard_21",
                "qnum": "0",
                "attempt_id": aid,
                "selected_answer": "A",
            },
            headers={"X-CSRF-Token": "test-csrf"},
            follow_redirects=False,
        )
        again = self.client.post(
            "/practice/submit",
            data={
                "csrf_token": "test-csrf",
                "domain": "hard_problem",
                "topic": "hard_21",
                "qnum": "0",
                "attempt_id": aid,
                "selected_answer": "C",
            },
            headers={"X-CSRF-Token": "test-csrf"},
            follow_redirects=False,
        )
        self.assertEqual(again.status_code, 302)
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            row = db.execute(
                """
                SELECT selected_answer FROM practice_responses
                WHERE attempt_id = ? AND question_index = 0
                ORDER BY id DESC LIMIT 1
                """,
                (int(aid),),
            ).fetchone()
            self.assertEqual(str(row["selected_answer"]), "C")

    def test_mock_test1_restart_creates_unlocked_attempt(self):
        self.login()
        first = self.client.get("/practice/hard_problem/hard_21/0")
        aid = int(self._hard21_attempt_id(first.get_data(as_text=True)))
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            db.execute(
                """
                INSERT INTO practice_responses
                    (attempt_id, question_index, selected_answer, correct_answer, is_correct)
                VALUES (?, 0, 'C', 'A', 0)
                """,
                (aid,),
            )
            db.commit()
        restart = self.client.get(
            "/practice/hard_problem/hard_21/new-session", follow_redirects=False
        )
        self.assertEqual(restart.status_code, 302)
        rv = self.client.get("/practice/hard_problem/hard_21/0")
        html = rv.get_data(as_text=True)
        self.assertEqual(rv.status_code, 200)
        self.assertIn("const phase3AnswerLocked = false;", html)
        new_aid = int(self._hard21_attempt_id(html))
        self.assertNotEqual(new_aid, aid)

    def test_all_classroom_mocks_fresh_are_clickable(self):
        self.login()
        order = self.app_mod.PHASE3_TEST_ORDER
        self.assertEqual(len(order), 11)
        for topic, test_n in sorted(order.items(), key=lambda kv: kv[1]):
            with self.subTest(topic=topic, test=test_n):
                tex = self.app_mod.BANKS["hard_problem"][topic]
                questions = self.app_mod.get_questions_for_topic(
                    "hard_problem", topic, tex
                )
                self.assertTrue(questions, topic)
                self.client.get(
                    f"/practice/hard_problem/{topic}/new-session",
                    follow_redirects=False,
                )
                rv = self.client.get(f"/practice/hard_problem/{topic}/0")
                self.assertEqual(rv.status_code, 200, topic)
                html = rv.get_data(as_text=True)
                self.assertIn("const phase3AnswerLocked = false;", html, topic)
                self.assertIn("Start this mock over", html, topic)
                q0_kind = str((questions[0] or {}).get("question_kind") or "mcq")
                if q0_kind in ("mcq", "mcq5"):
                    self.assertIn('class="choice-radio-input"', html, topic)
                    self.assertIn('name="selected_answer"', html, topic)
                else:
                    self.assertTrue(
                        'id="spr-answer-input"' in html
                        or 'id="constructed-answer-input"' in html,
                        topic,
                    )
                mcq_index = next(
                    (
                        i
                        for i, q in enumerate(questions)
                        if str(q.get("question_kind") or "mcq") in ("mcq", "mcq5")
                    ),
                    None,
                )
                if mcq_index:
                    mcq = self.client.get(
                        f"/practice/hard_problem/{topic}/{mcq_index}"
                    )
                    self.assertEqual(mcq.status_code, 200, topic)
                    mcq_html = mcq.get_data(as_text=True)
                    self.assertIn("const phase3AnswerLocked = false;", mcq_html, topic)
                    self.assertIn('class="choice-radio-input"', mcq_html, topic)

    def test_test_ix_camp_exam_uses_native_radios(self):
        self.login()
        start = self.client.get("/practice/exams/camp-test-9/start", follow_redirects=False)
        self.assertEqual(start.status_code, 302)
        loc = start.headers.get("Location", "")
        self.assertIn("/practice/exams/random-test/module/1/0", loc)
        rv = self.client.get("/practice/exams/random-test/module/1/0")
        self.assertEqual(rv.status_code, 200)
        html = rv.get_data(as_text=True)
        self.assertIn('class="choice-radio-input"', html)
        self.assertIn('name="selected_answer"', html)
        self.assertIn("Start this mock over", html)
        self.assertNotIn('id="selected-answer-input" name="selected_answer"', html)

    def test_autosave_keeps_fill_in_without_next(self):
        self.login()
        self.client.get("/practice/hard_problem/hard_22/new-session", follow_redirects=False)
        first = self.client.get("/practice/hard_problem/hard_22/0")
        aid = self._hard21_attempt_id(first.get_data(as_text=True))
        rv = self.client.post(
            "/practice/autosave-answer",
            data={
                "csrf_token": "test-csrf",
                "domain": "hard_problem",
                "topic": "hard_22",
                "qnum": "0",
                "attempt_id": aid,
                "selected_answer": "15",
            },
            headers={"X-CSRF-Token": "test-csrf", "X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(rv.status_code, 200)
        self.assertTrue(rv.get_json().get("ok"))
        back = self.client.get("/practice/hard_problem/hard_22/0")
        self.assertIn('value="15"', back.get_data(as_text=True))

    def test_empty_next_does_not_erase_saved_draft(self):
        self.login()
        self.client.get("/practice/hard_problem/hard_22/new-session", follow_redirects=False)
        first = self.client.get("/practice/hard_problem/hard_22/0")
        aid = self._hard21_attempt_id(first.get_data(as_text=True))
        self.client.post(
            "/practice/autosave-answer",
            data={
                "csrf_token": "test-csrf",
                "domain": "hard_problem",
                "topic": "hard_22",
                "qnum": "0",
                "attempt_id": aid,
                "selected_answer": "9/2",
            },
            headers={"X-CSRF-Token": "test-csrf", "X-Requested-With": "XMLHttpRequest"},
        )
        self.client.post(
            "/practice/draft-answer",
            data={
                "csrf_token": "test-csrf",
                "domain": "hard_problem",
                "topic": "hard_22",
                "qnum": "0",
                "goto_qnum": "1",
                "attempt_id": aid,
                "selected_answer": "",
            },
            headers={"X-CSRF-Token": "test-csrf"},
            follow_redirects=False,
        )
        back = self.client.get("/practice/hard_problem/hard_22/0")
        self.assertIn('value="9/2"', back.get_data(as_text=True))

    def test_hard_spr_draft_restores_on_previous(self):
        self.login()
        self.client.get("/practice/hard_problem/hard_22/new-session", follow_redirects=False)
        first = self.client.get("/practice/hard_problem/hard_22/0")
        self.assertEqual(first.status_code, 200)
        html = first.get_data(as_text=True)
        self.assertIn('id="spr-answer-input"', html)
        aid = self._hard21_attempt_id(html)
        rv = self.client.post(
            "/practice/draft-answer",
            data={
                "csrf_token": "test-csrf",
                "domain": "hard_problem",
                "topic": "hard_22",
                "qnum": "0",
                "goto_qnum": "1",
                "attempt_id": aid,
                "selected_answer": "27/4",
            },
            headers={"X-CSRF-Token": "test-csrf"},
            follow_redirects=False,
        )
        self.assertEqual(rv.status_code, 302)
        back = self.client.get("/practice/hard_problem/hard_22/0")
        back_html = back.get_data(as_text=True)
        self.assertIn('id="spr-answer-input"', back_html)
        self.assertIn('value="27/4"', back_html)

    def test_hard_practice_set_uses_native_radios(self):
        self.login()
        self.client.get("/practice/hard_problem/hard_1/new-session", follow_redirects=False)
        rv = self.client.get("/practice/hard_problem/hard_1/0")
        self.assertEqual(rv.status_code, 200)
        html = rv.get_data(as_text=True)
        self.assertIn("const phase3AnswerLocked = false;", html)
        self.assertIn("Start this mock over", html)
        if 'id="spr-answer-input"' not in html:
            self.assertIn('class="choice-radio-input"', html)


class RepairFlagOffTests(unittest.TestCase):
    """With SKILL_REPAIR off, pack-backed Repair must not change student Analytics."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sat-repair-off-")
        self.db = os.path.join(self.tmp, "sat.db")
        copy_db(self.db)
        import app as app_mod

        self.app_mod = app_mod
        self._orig_db = app_mod.DB_PATH
        self._orig_ready = app_mod._DB_SCHEMA_READY
        app_mod.DB_PATH = self.db
        app_mod._DB_SCHEMA_READY = False
        app_mod.app.config["TESTING"] = True
        app_mod.app.config["SKILL_LOOP_PILOT"] = False
        app_mod.app.config["SKILL_REPAIR"] = False
        os.environ.pop("SKILL_LOOP_PILOT", None)
        os.environ.pop("SKILL_REPAIR", None)
        self.client = app_mod.app.test_client()

    def tearDown(self):
        os.environ.pop("SKILL_LOOP_PILOT", None)
        os.environ.pop("SKILL_REPAIR", None)
        self.app_mod.app.config["SKILL_REPAIR"] = False
        self.app_mod.app.config["SKILL_LOOP_PILOT"] = False
        self.app_mod.DB_PATH = self._orig_db
        self.app_mod._DB_SCHEMA_READY = self._orig_ready
        shutil.rmtree(self.tmp, ignore_errors=True)

    def login(self, user_id=2, role="student", username="s1"):
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_role"] = role
            sess["username"] = username
            sess["csrf_token"] = "test-csrf"

    def _insert_algebra_misses(self, count=5):
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            aid = db.execute(
                "INSERT INTO practice_attempts (user_id, domain, topic, qnum) VALUES (2, 'algebra', '1_1', 0)"
            ).lastrowid
            for i in range(count):
                db.execute(
                    """
                    INSERT INTO practice_responses
                        (attempt_id, question_index, selected_answer, correct_answer, is_correct)
                    VALUES (?, ?, 'A', 'B', 0)
                    """,
                    (aid, i),
                )
            db.commit()
            return db

    def test_flag_defaults_off(self):
        import skill_repair as sr

        self.assertFalse(self.app_mod.app.config.get("SKILL_REPAIR"))
        with self.app_mod.app.app_context():
            self.assertFalse(sr.skill_repair_enabled())

    def test_repair_routes_404_and_do_not_write_sessions(self):
        self.login()
        before = 0
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            try:
                before = int(db.execute("SELECT COUNT(*) FROM skill_repair_sessions").fetchone()[0])
            except sqlite3.Error:
                before = 0
        for path, method in (
            ("/practice/repair/sat.alg.linear_rate_remaining/start", "get"),
            ("/practice/repair/sat.alg.solve_linear_equation/worked", "get"),
            ("/practice/repair/sat.alg.no_solution_parameter/feedback", "get"),
        ):
            rv = self.client.get(path, follow_redirects=False)
            self.assertEqual(rv.status_code, 404, path)
        posted = self.client.post(
            "/practice/repair/sat.alg.linear_rate_remaining/submit",
            data={"csrf_token": "test-csrf", "phase": "worked"},
            follow_redirects=False,
        )
        self.assertEqual(posted.status_code, 404)
        evented = self.client.post(
            "/practice/repair/sat.alg.linear_rate_remaining/event",
            data={"csrf_token": "test-csrf", "event": "view_solution", "phase": "worked"},
            follow_redirects=False,
        )
        self.assertEqual(evented.status_code, 404)
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            try:
                after = int(db.execute("SELECT COUNT(*) FROM skill_repair_sessions").fetchone()[0])
            except sqlite3.Error:
                after = 0
        self.assertEqual(after, before)

    def test_analytics_hides_repair_ctas_and_new_pack_skills(self):
        self.login()
        self._insert_algebra_misses()
        rv = self.client.get("/practice/analytics")
        html = rv.get_data(as_text=True)
        self.assertEqual(rv.status_code, 200)
        self.assertNotIn("Repair this skill", html)
        self.assertNotIn("View delayed check", html)
        self.assertNotIn("Immediate practice complete", html)
        self.assertNotIn("/practice/repair/", html)
        self.assertNotIn("sat.alg.solve_linear_equation", html)
        self.assertNotIn("sat.alg.translate_words_to_equation", html)
        self.assertNotIn("sat.alg.no_solution_parameter", html)
        self.assertNotIn("sat.alg.identity_infinite_solutions", html)
        self.assertNotIn("sat.alg.percent_cost_model", html)
        self.assertNotIn("Needs further diagnosis", html)
        unit = self.client.get("/practice/analytics?part=unit1")
        unit_html = unit.get_data(as_text=True)
        self.assertIn("Archive from mistake list", unit_html)
        self.assertIn("review only", unit_html.lower())
        self.assertNotIn("Repair this skill", unit_html)

    def test_legacy_clustering_has_no_pack_hrefs(self):
        import skill_repair as sr

        rows = [
            {
                "stem_html": "<p>A tank starts with 8400 gallons. After 3 hours, 6900 remain at a constant rate.</p>",
                "knowledge_title": "Linear remaining",
                "knowledge_section": "1.1",
                "domain": "algebra",
                "topic": "1_1",
                "q_index": 2,
                "pr_id": 9,
                "yours": "A",
                "key": "C",
                "when": "2026-08-01",
                "mastery_effective": "unreviewed",
                "diagnosis_label": "Setup / modeling",
                "tag_labels": ["setup"],
                "pattern_pack": {"pitfall": "Adding the opening hours twice."},
                "practice_href": "/x",
            },
            {
                "stem_html": "<p>Solve 2x+3=11.</p>",
                "knowledge_title": "Solve linear equations",
                "knowledge_section": "1.1",
                "domain": "algebra",
                "topic": "1_1",
                "q_index": 3,
                "pr_id": 10,
                "yours": "B",
                "key": "A",
                "when": "2026-08-02",
                "mastery_effective": "unreviewed",
                "diagnosis_label": "Execution",
                "tag_labels": [],
                "pattern_pack": {},
                "practice_href": "/y",
            },
        ]
        clusters = sr.cluster_wrong_rows(rows, pack_backed=False)
        codes = {c["code"] for c in clusters}
        self.assertIn("sat.alg.linear_rate_remaining", codes)
        self.assertTrue(any(str(c).startswith("bank.") for c in codes))
        self.assertNotIn("sat.alg.solve_linear_equation", codes)
        for cluster in clusters:
            self.assertFalse(cluster["has_pack"])
            self.assertEqual(cluster["repair_href"], "")
            self.assertEqual(cluster["stuck_label"], "Common stuck point")

    def test_old_practice_still_works_when_repair_off(self):
        self.login()
        rv = self.client.get("/practice/algebra/1_1/0")
        self.assertEqual(rv.status_code, 200)
        html = rv.get_data(as_text=True)
        self.assertIn('type="radio"', html)
        self.assertIn('class="choice-radio-input"', html)

    def test_pilot_env_enables_repair_when_repair_env_unset(self):
        import skill_repair as sr

        os.environ["SKILL_LOOP_PILOT"] = "1"
        try:
            with self.app_mod.app.app_context():
                self.assertTrue(sr.skill_repair_enabled())
            self.login()
            rv = self.client.get(
                "/practice/repair/sat.alg.linear_rate_remaining/start",
                follow_redirects=False,
            )
            self.assertNotEqual(rv.status_code, 404)
        finally:
            os.environ.pop("SKILL_LOOP_PILOT", None)

    def test_explicit_repair_off_wins_over_pilot(self):
        import skill_repair as sr

        os.environ["SKILL_REPAIR"] = "0"
        os.environ["SKILL_LOOP_PILOT"] = "1"
        try:
            with self.app_mod.app.app_context():
                self.assertFalse(sr.skill_repair_enabled())
            self.login()
            rv = self.client.get(
                "/practice/repair/sat.alg.linear_rate_remaining/start",
                follow_redirects=False,
            )
            self.assertEqual(rv.status_code, 404)
        finally:
            os.environ.pop("SKILL_REPAIR", None)
            os.environ.pop("SKILL_LOOP_PILOT", None)


if __name__ == "__main__":
    unittest.main()
