"""A finished SAT mistake test is stored and visible in the admin record."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class MistakeTestRecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sat-mistake-record-")
        self.db = os.path.join(self.tmp, "sat.db")
        import app as app_mod

        self.app_mod = app_mod
        self._orig_db = app_mod.DB_PATH
        self._orig_ready = app_mod._DB_SCHEMA_READY
        app_mod.DB_PATH = self.db
        app_mod._DB_SCHEMA_READY = False
        app_mod.app.config["TESTING"] = True
        self.client = app_mod.app.test_client()
        self.client.get("/student-guide")
        conn = sqlite3.connect(self.db)
        conn.execute(
            "INSERT INTO users (username, password, role, is_active) VALUES ('record-student', 'x', 'student', 1)"
        )
        conn.execute(
            "INSERT INTO users (username, password, role, is_active) VALUES ('record-admin', 'x', 'admin', 1)"
        )
        self.user_id = int(conn.execute("SELECT id FROM users WHERE username = 'record-student'").fetchone()[0])
        self.admin_id = int(conn.execute("SELECT id FROM users WHERE username = 'record-admin'").fetchone()[0])
        items = [
            {
                "domain": "algebra",
                "topic": "1_1",
                "q_index": 0,
                "unit_key": "U1",
                "unit_label": "Unit 1",
                "unit_title": "Algebra",
                "topic_title": "Linear equations",
                "wrong_count": 2,
                "order": 0,
            },
            {
                "domain": "algebra",
                "topic": "1_1",
                "q_index": 1,
                "unit_key": "U1",
                "unit_label": "Unit 1",
                "unit_title": "Algebra",
                "topic_title": "Linear equations",
                "wrong_count": 1,
                "order": 1,
            },
        ]
        cur = conn.execute(
            """
            INSERT INTO sat_mistake_tests (
                user_id, learner_key, items_json, status, started_at, time_limit_seconds, item_count
            )
            VALUES (?, ?, ?, 'active', datetime('now'), 2100, 2)
            """,
            (self.user_id, f"u:{self.user_id}", json.dumps(items)),
        )
        self.test_id = int(cur.lastrowid)
        conn.commit()
        conn.close()
        self._login(self.user_id, "student", "record-student")

    def tearDown(self):
        import shutil

        self.app_mod.DB_PATH = self._orig_db
        self.app_mod._DB_SCHEMA_READY = self._orig_ready
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _login(self, user_id: int, role: str, username: str) -> None:
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_role"] = role
            sess["username"] = username
            sess["csrf_token"] = "test-csrf"

    def _submit(self, step: int, answer: str):
        return self.client.post(
            f"/practice/mistakes/sat/test/{self.test_id}/submit",
            data={"csrf_token": "test-csrf", "step": str(step), "selected_answer": answer},
        )

    def _stored_score(self):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT status, item_count, answered_count, correct_count, score_pct, completed_at
            FROM sat_mistake_tests WHERE id = ?
            """,
            (self.test_id,),
        ).fetchone()
        answers = conn.execute(
            """
            SELECT item_order, selected_answer, correct_answer, is_correct
            FROM sat_mistake_test_responses WHERE test_id = ? ORDER BY item_order
            """,
            (self.test_id,),
        ).fetchall()
        conn.close()
        return row, answers

    def test_each_answer_is_stored_and_a_finished_test_reaches_admin(self):
        first = self._submit(0, "A")
        self.assertEqual(first.status_code, 302)
        row, answers = self._stored_score()
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["answered_count"], 1)
        self.assertEqual(len(answers), 1)
        self.assertEqual(answers[0]["selected_answer"], "A")
        self.assertIsNotNone(answers[0]["correct_answer"])
        self.assertIn(int(answers[0]["is_correct"]), (0, 1))

        self._login(self.admin_id, "admin", "record-admin")
        detail = self.client.get(f"/admin/students/{self.user_id}")
        detail_html = detail.get_data(as_text=True)
        self.assertEqual(detail.status_code, 200)
        self.assertIn("SAT mistake tests", detail_html)
        self.assertIn("In progress", detail_html)
        self.assertIn("1/2", detail_html)
        home = self.client.get("/admin")
        home_html = home.get_data(as_text=True)
        self.assertEqual(home.status_code, 200)
        self.assertIn("record-student", home_html)
        self.assertIn("Mistake tests 0/1", home_html)

        self._login(self.user_id, "student", "record-student")
        second = self._submit(1, "B")
        self.assertEqual(second.status_code, 302)
        self.assertIn(f"/practice/mistakes/sat/test/{self.test_id}/done", second.headers["Location"])
        done = self.client.get(f"/practice/mistakes/sat/test/{self.test_id}/done")
        self.assertEqual(done.status_code, 200)
        self.assertIn("Saved on the student record", done.get_data(as_text=True))
        row, answers = self._stored_score()
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["item_count"], 2)
        self.assertEqual(row["answered_count"], 2)
        self.assertEqual(row["correct_count"], sum(int(a["is_correct"] or 0) for a in answers))
        self.assertEqual(row["score_pct"], round(100 * row["correct_count"] / 2))
        self.assertIsNotNone(row["completed_at"])
        self.assertEqual(len(answers), 2)

        blocked = self.client.get(f"/admin/students/{self.user_id}/mistake-tests/{self.test_id}")
        self.assertEqual(blocked.status_code, 403)

        self._login(self.admin_id, "admin", "record-admin")
        report = self.client.get(f"/admin/students/{self.user_id}/mistake-tests/{self.test_id}")
        report_html = report.get_data(as_text=True)
        self.assertEqual(report.status_code, 200)
        self.assertIn("record-student", report_html)
        self.assertIn("Saved on the student record", report_html)
        self.assertIn("Your answer: A", report_html)
        self.assertIn("Your answer: B", report_html)
        progress = self.client.get(f"/admin/students/{self.user_id}/report")
        self.assertEqual(progress.status_code, 200)
        self.assertIn("Mistake tests", progress.get_data(as_text=True))
        self.assertIn(f"{row['correct_count']}/2", progress.get_data(as_text=True))
        finished = self.client.get(f"/admin/students/{self.user_id}")
        self.assertIn("Finished", finished.get_data(as_text=True))
        self.assertIn("Mistake tests 1/1", self.client.get("/admin").get_data(as_text=True))

    def test_expired_partial_test_still_saves_a_finished_score(self):
        self._submit(0, "C")
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE sat_mistake_tests SET started_at = datetime('now', '-2 hours') WHERE id = ?",
            (self.test_id,),
        )
        conn.commit()
        conn.close()
        done = self.client.get(f"/practice/mistakes/sat/test/{self.test_id}/done")
        self.assertEqual(done.status_code, 200)
        self.assertIn("Not answered", done.get_data(as_text=True))
        row, answers = self._stored_score()
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["answered_count"], 1)
        self.assertEqual(len(answers), 1)
        self.assertIsNotNone(row["completed_at"])


if __name__ == "__main__":
    unittest.main()
