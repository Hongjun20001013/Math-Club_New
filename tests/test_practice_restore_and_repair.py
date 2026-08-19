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
        clusters = sr.cluster_wrong_rows(rows)
        self.assertGreaterEqual(len(clusters), 1)
        codes = {c["code"] for c in clusters}
        self.assertIn("sat.alg.linear_rate_remaining", codes)
        nxt = sr.recommended_next_step(clusters)
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt["miss_count"], clusters[0]["miss_count"])

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


if __name__ == "__main__":
    unittest.main()
