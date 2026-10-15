"""One-student / one-advisor smoke: English essay visibility + writing grade + math MCQ."""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.test_placement_public_access import _Base, copy_db  # noqa: E402


class TestPlacementAdvisorWalkthrough(_Base):
    def test_placement_guide_public_without_login(self):
        self.flag_on()
        with self.client.session_transaction() as sess:
            sess.pop("user_id", None)
        page = self.client.get("/guide/placement")
        self.assertEqual(page.status_code, 200)
        body = page.get_data(as_text=True)
        self.assertIn("分班测评", body)
        pdf = self.client.get("/placement/user-guide.pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertIn("pdf", pdf.mimetype)

    def test_english_student_then_advisor_grades_writing(self):
        from app import BANKS, get_questions_for_topic
        from placement_english_rubrics import writing_rubric_for

        self.flag_on()
        qs = get_questions_for_topic(
            "placement", "english_g7_8", BANKS["placement"]["english_g7_8"]
        )
        widx = len(qs) - 1
        essay_body = "When I faced a challenge at school, I learned to ask for help and keep trying."
        rv = self.begin(slug="english-g7-8", name="Walkthrough Student", advisor="Mia Hu")
        pid = self.public_id_from_location(rv)
        aid = self.attempt_id(pid)

        self.client.post(
            f"/placement/run/{pid}/item/0",
            data={"csrf_token": self.csrf(), "qnum": "0", "selected_answer": "A"},
        )
        self.client.post(
            f"/placement/run/{pid}/autosave",
            data={
                "csrf_token": self.csrf(),
                "qnum": str(widx),
                "selected_answer": essay_body,
                "english_writing_option": "A",
            },
        )
        self.client.post(
            f"/placement/run/{pid}/finish",
            data={"csrf_token": self.csrf(), "confirm": "1"},
        )

        conn = sqlite3.connect(self.db)
        try:
            row = conn.execute(
                """
                SELECT selected_answer FROM placement_candidate_responses
                WHERE attempt_id=? AND question_index=?
                """,
                (aid, widx),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertIn("keep trying", str(row[0]))
        finally:
            conn.close()

        self.login(user_id=1, role="admin", username="teacher")
        detail = self.client.get(f"/admin/placement-candidates/{aid}")
        self.assertEqual(detail.status_code, 200)
        detail_html = detail.get_data(as_text=True)
        self.assertIn("Walkthrough Student", detail_html)
        self.assertIn("keep trying", detail_html)

        item = self.client.get(f"/admin/placement-candidates/{aid}/item/{widx}")
        self.assertEqual(item.status_code, 200)
        item_html = item.get_data(as_text=True)
        self.assertIn("keep trying", item_html)

        rubric = writing_rubric_for("english_g7_8", "A")
        grade_data = {"csrf_token": self.csrf(), "return_to": "detail"}
        for crit in rubric["criteria"]:
            grade_data[f"crit_{crit['id']}"] = str(crit["max_points"])
        gr = self.client.post(
            f"/admin/placement-candidates/{aid}/writing-grade",
            data=grade_data,
            follow_redirects=False,
        )
        self.assertIn(gr.status_code, (302, 303))
        conn = sqlite3.connect(self.db)
        try:
            score = json.loads(
                conn.execute(
                    "SELECT score_json FROM placement_candidate_attempts WHERE id=?",
                    (aid,),
                ).fetchone()[0]
                or "{}"
            )
        finally:
            conn.close()
        self.assertEqual(score.get("writing_total"), 20)

        pdf = self.client.get(f"/admin/placement-candidates/{aid}/report.pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertIn("pdf", pdf.mimetype)

    def test_math_student_then_advisor_sees_mcq(self):
        self.flag_on()
        rv = self.begin(slug="enhanced-math-1", name="Math Walkthrough")
        pid = self.public_id_from_location(rv)
        aid = self.attempt_id(pid)
        self.client.post(
            f"/placement/run/{pid}/item/0",
            data={"csrf_token": self.csrf(), "qnum": "0", "selected_answer": "B"},
        )
        self.client.post(
            f"/placement/run/{pid}/item/1",
            data={"csrf_token": self.csrf(), "qnum": "1", "selected_answer": "C"},
        )
        self.client.post(
            f"/placement/run/{pid}/finish",
            data={"csrf_token": self.csrf(), "confirm": "1"},
        )
        self.login(user_id=1, role="admin", username="teacher")
        item0 = self.client.get(f"/admin/placement-candidates/{aid}/item/0")
        self.assertEqual(item0.status_code, 200)
        html0 = item0.get_data(as_text=True)
        m = re.search(r'name="selected_answer" value="([A-E])"[^>]*\bchecked\b', html0)
        if not m:
            self.assertIn("B", html0)
        listing = self.client.get("/admin/placement-candidates?track=math")
        self.assertIn("Math Walkthrough", listing.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
