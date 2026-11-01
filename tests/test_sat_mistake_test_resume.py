"""An in-progress SAT mistake test stays available after the student leaves."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class MistakeTestResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sat-mistake-resume-")
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
            "INSERT INTO users (username, password, role, is_active) VALUES ('resume-student', 'x', 'student', 1)"
        )
        self.user_id = int(conn.execute("SELECT id FROM users WHERE username = 'resume-student'").fetchone()[0])
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
            INSERT INTO sat_mistake_tests (user_id, learner_key, items_json, status, started_at, time_limit_seconds)
            VALUES (?, ?, ?, 'active', datetime('now'), 2100)
            """,
            (self.user_id, f"u:{self.user_id}", json.dumps(items)),
        )
        self.test_id = int(cur.lastrowid)
        conn.execute(
            """
            INSERT INTO sat_mistake_test_responses (
                test_id, item_order, domain, topic, question_index,
                selected_answer, correct_answer, is_correct
            ) VALUES (?, 0, 'algebra', '1_1', 0, 'A', 'B', 0)
            """,
            (self.test_id,),
        )
        conn.commit()
        conn.close()
        with self.client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["user_role"] = "student"
            sess["username"] = "resume-student"
            sess["csrf_token"] = "test-csrf"

    def tearDown(self):
        import shutil

        self.app_mod.DB_PATH = self._orig_db
        self.app_mod._DB_SCHEMA_READY = self._orig_ready
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dashboard_and_hub_reopen_the_same_questions(self):
        page = self.client.get("/practice/mistakes/sat")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Continue · 1/2 saved", html)
        self.assertIn(f"/practice/mistakes/sat/test/{self.test_id}/1", html)
        self.assertNotIn("more needed to unlock", html)

        hub = self.client.get("/practice")
        hub_html = hub.get_data(as_text=True)
        self.assertEqual(hub.status_code, 200)
        self.assertIn("Continue test · 1/2", hub_html)
        self.assertIn(f"/practice/mistakes/sat/test/{self.test_id}/1", hub_html)

        question = self.client.get(f"/practice/mistakes/sat/test/{self.test_id}/1")
        qhtml = question.get_data(as_text=True)
        self.assertEqual(question.status_code, 200)
        self.assertIn("Saved · return from Mistake test", qhtml)
        started = re.search(r"const startedUnix = (\d+);", qhtml)
        self.assertIsNotNone(started)
        self.assertLess(abs(int(time.time()) - int(started.group(1))), 180)

        again = self.client.post(
            "/practice/mistakes/sat/generate",
            data={"csrf_token": "test-csrf"},
        )
        self.assertEqual(again.status_code, 302)
        self.assertIn(f"/practice/mistakes/sat/test/{self.test_id}/1", again.headers["Location"])
        conn = sqlite3.connect(self.db)
        count = conn.execute(
            "SELECT COUNT(*) FROM sat_mistake_tests WHERE user_id = ?",
            (self.user_id,),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_expired_sitting_still_lists_the_saved_questions(self):
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE sat_mistake_tests SET started_at = datetime('now', '-2 hours') WHERE id = ?",
            (self.test_id,),
        )
        conn.commit()
        conn.close()

        page = self.client.get("/practice/mistakes/sat")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Open saved questions", html)
        done_url = f"/practice/mistakes/sat/test/{self.test_id}/done"
        self.assertIn(done_url, html)

        hub = self.client.get("/practice")
        self.assertIn("Open saved test", hub.get_data(as_text=True))
        self.assertIn(done_url, hub.get_data(as_text=True))

        report = self.client.get(done_url)
        report_html = report.get_data(as_text=True)
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report_html.count("Linear equations"), 2)
        self.assertIn("Open original question", report_html)

        again = self.client.post(
            "/practice/mistakes/sat/generate",
            data={"csrf_token": "test-csrf"},
        )
        self.assertEqual(again.status_code, 302)
        self.assertIn(done_url, again.headers["Location"])
        conn = sqlite3.connect(self.db)
        row = conn.execute(
            "SELECT status, COUNT(*) FROM sat_mistake_tests WHERE user_id = ?",
            (self.user_id,),
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "completed")
        self.assertEqual(row[1], 1)


if __name__ == "__main__":
    unittest.main()
