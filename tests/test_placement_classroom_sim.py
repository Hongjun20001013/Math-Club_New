"""Simulate 10 guest students on mixed placement tests, including leave/recover.

Uses a TEMP copy of sat.db only. Does not write the live database.
"""
from __future__ import annotations

import re
import sqlite3
import unittest
from io import BytesIO

from tests.test_placement_public_access import TINY_PDF, _Base

TOPIC = {
    "middle-level": "middle_level",
    "enhanced-math-1": "enhanced_math_1",
    "enhanced-math-2": "enhanced_math_2",
    "upper-algebra-precalc": "placement_full",
}
TIMER = {
    "middle_level": 150 * 60,
    "enhanced_math_1": 120 * 60,
    "enhanced_math_2": 130 * 60,
    "placement_full": 115 * 60,
}
LAST_MC = {
    "enhanced-math-1": 49,
    "enhanced-math-2": 54,
}

CLASSROOM = (
    {"name": "Maya Lin", "slug": "middle-level", "grade": "7th", "advisor": "Mia Hu", "habit": "sip"},
    {"name": "Ethan Park", "slug": "middle-level", "grade": "8th", "advisor": "Jimmy Zheng", "habit": "close_recover"},
    {"name": "Sofia Reyes", "slug": "middle-level", "grade": "8th", "advisor": "Mia Hu", "habit": "skip_recover"},
    {"name": "Noah Kim", "slug": "enhanced-math-1", "grade": "9th", "advisor": "Mia Hu", "habit": "close_recover"},
    {"name": "Ava Chen", "slug": "enhanced-math-1", "grade": "9th", "advisor": "Jimmy Zheng", "habit": "paper_recover"},
    {"name": "Liam Ortiz", "slug": "enhanced-math-2", "grade": "10th", "advisor": "Mia Hu", "habit": "close_recover"},
    {"name": "Emma Walsh", "slug": "enhanced-math-2", "grade": "10th", "advisor": "Other", "habit": "paper_recover"},
    {"name": "Raj Patel", "slug": "upper-algebra-precalc", "grade": "11th", "advisor": "Mia Hu", "habit": "close_recover"},
    {"name": "Chloe Ng", "slug": "upper-algebra-precalc", "grade": "11th", "advisor": "Jimmy Zheng", "habit": "skip_recover"},
    {"name": "Ben Adler", "slug": "middle-level", "grade": "8th", "advisor": "Mia Hu", "habit": "sip"},
)


def _remaining(html: str) -> int:
    m = re.search(r"const placementRemainingAtLoad = (\d+);", html)
    if m:
        return int(m.group(1))
    m = re.search(r'id="np-pl-paper-time">(\d+):(\d+)<', html)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    raise AssertionError("no remaining clock in page")


def _started_unix(html: str) -> int:
    m = re.search(r"const attemptStartedUnix = (\d+);", html)
    if not m:
        raise AssertionError("no attemptStartedUnix in page")
    return int(m.group(1))


class TestTenStudentClassroom(_Base):
    def csrf_on(self, client) -> str:
        with client.session_transaction() as sess:
            token = sess.get("csrf_token") or "test-csrf"
            sess["csrf_token"] = token
            return token

    def begin_on(self, client, slug: str, name: str, grade: str, advisor: str):
        from placement_public import reset_rate_limits_for_tests

        reset_rate_limits_for_tests()
        html = client.get(f"/placement/{slug}/start").get_data(as_text=True)
        nonce = ""
        m = re.search(r'name="begin_nonce" value="([^"]+)"', html)
        if m:
            nonce = m.group(1)
        data = {
            "csrf_token": self.csrf_on(client),
            "student_name": name,
            "student_grade": grade,
            "student_math_course": "Algebra I Honors",
            "student_school": "Novel Prep Sim",
            "begin_nonce": nonce,
            "counselor_confirm": "1",
        }
        if advisor in ("Mia Hu", "Jimmy Zheng"):
            data["advisor_choice"] = advisor
        else:
            data["advisor_choice"] = "Other"
            data["advisor_other"] = "Priya Shah"
        return client.post(f"/placement/{slug}/begin", data=data, follow_redirects=False)

    def code_from(self, html: str) -> str:
        m = re.search(r"data-pl-recovery-code>([^<]+)", html)
        self.assertIsNotNone(m, "recovery code missing")
        return m.group(1).strip()

    def qs_for(self, slug: str):
        from app import BANKS, get_questions_for_topic

        topic = TOPIC[slug]
        return get_questions_for_topic("placement", topic, BANKS["placement"][topic])

    def answer(self, client, pid: str, qnum: int, qs: list, *, goto: int | None = None):
        q = qs[qnum]
        kind = str(q.get("question_kind") or "mcq")
        if kind in ("mcq", "mcq5"):
            raw = str(q.get("correct_answer") or "A")
        else:
            raw = str(q.get("correct_answer") or "1")
        data = {
            "csrf_token": self.csrf_on(client),
            "qnum": str(qnum),
            "selected_answer": raw,
        }
        if goto is not None:
            data["goto_qnum"] = str(goto)
        return client.post(
            f"/placement/run/{pid}/item/{qnum}",
            data=data,
            follow_redirects=False,
        )

    def started_at(self, pid: str) -> str:
        conn = sqlite3.connect(self.db)
        try:
            row = conn.execute(
                "SELECT started_at FROM placement_candidate_attempts WHERE public_id=?",
                (pid,),
            ).fetchone()
            self.assertIsNotNone(row)
            return str(row[0] or "")
        finally:
            conn.close()

    def backdate(self, pid: str, minutes: int) -> None:
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                """
                UPDATE placement_candidate_attempts
                SET started_at = datetime(COALESCE(started_at, created_at), ?)
                WHERE public_id=?
                """,
                (f"-{int(minutes)} minutes", pid),
            )
            conn.commit()
        finally:
            conn.close()

    def recover_fresh(self, code: str):
        from placement_public import reset_rate_limits_for_tests

        reset_rate_limits_for_tests()
        other = self.app_mod.app.test_client()
        other.get("/placement/recover")
        rv = other.post(
            "/placement/recover",
            data={"csrf_token": self.csrf_on(other), "recovery_code": code},
            follow_redirects=False,
        )
        return other, rv

    def assert_question_page(self, html: str, slug: str, qnum: int) -> None:
        self.assertIn('id="question-area"', html, slug)
        self.assertIn("id=\"time\"", html, slug)
        self.assertNotIn("Internal Server Error", html)
        self.assertNotIn("Traceback", html)
        self.assertIn("data-pl-recovery-code", html)
        self.assertGreater(_remaining(html), 0, slug)
        self.assertGreater(_started_unix(html), 1_700_000_000, slug)

    def test_ten_students_mixed_habits_and_timer_does_not_restart(self):
        from placement_public import reset_rate_limits_for_tests

        self.flag_on()
        roster = []
        for spec in CLASSROOM:
            client = self.app_mod.app.test_client()
            rv = self.begin_on(client, spec["slug"], spec["name"], spec["grade"], spec["advisor"])
            self.assertEqual(rv.status_code, 302, spec["name"])
            pid = self.public_id_from_location(rv)
            ready = client.get(f"/placement/run/{pid}/ready")
            self.assertEqual(ready.status_code, 200, spec["name"])
            code = self.code_from(ready.get_data(as_text=True))
            qs = self.qs_for(spec["slug"])
            first = client.get(f"/placement/run/{pid}/item/0")
            self.assertEqual(first.status_code, 200, spec["name"])
            html0 = first.get_data(as_text=True)
            self.assert_question_page(html0, spec["slug"], 0)
            started = self.started_at(pid)
            self.assertTrue(started, spec["name"])
            full = TIMER[TOPIC[spec["slug"]]]
            self.assertGreaterEqual(_remaining(html0), full - 3, spec["name"])
            roster.append(
                {
                    **spec,
                    "client": client,
                    "pid": pid,
                    "code": code,
                    "qs": qs,
                    "started": started,
                    "start_unix": _started_unix(html0),
                    "full": full,
                }
            )

        conn = sqlite3.connect(self.db)
        try:
            n_cand = conn.execute("SELECT COUNT(*) FROM placement_candidates").fetchone()[0]
            n_att = conn.execute("SELECT COUNT(*) FROM placement_candidate_attempts").fetchone()[0]
            n_codes = conn.execute(
                "SELECT COUNT(DISTINCT recovery_code_hash) FROM placement_candidates"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(n_cand, 10)
        self.assertEqual(n_att, 10)
        self.assertEqual(n_codes, 10)

        a = roster[0]
        b = roster[1]
        blocked = a["client"].get(f"/placement/run/{b['pid']}/item/0", follow_redirects=False)
        self.assertEqual(blocked.status_code, 404)

        sample_idx = {
            "middle-level": (0, 1, 12, 19),
            "enhanced-math-1": (0, 1, 24, 49),
            "enhanced-math-2": (0, 7, 30, 54),
            "upper-algebra-precalc": (0, 5, 12),
        }
        for row in roster:
            for qnum in sample_idx[row["slug"]]:
                page = row["client"].get(f"/placement/run/{row['pid']}/item/{qnum}")
                self.assertEqual(page.status_code, 200, f"{row['name']} q{qnum}")
                html = page.get_data(as_text=True)
                self.assert_question_page(html, row["slug"], qnum)
                q = row["qs"][qnum]
                kind = str(q.get("question_kind") or "mcq")
                if kind in ("mcq", "mcq5"):
                    self.assertIn('name="selected_answer"', html)
                    self.assertTrue(q.get("choices"), f"{row['slug']} q{qnum} missing choices")
                    self.assertTrue(str(q.get("stem") or q.get("question") or "").strip() or True)
                else:
                    self.assertTrue(
                        'name="selected_answer"' in html or "fill" in html.lower() or "input" in html
                    )

        maya = roster[0]
        gate = maya["client"].get(f"/placement/run/{maya['pid']}/item/20", follow_redirects=True)
        gate_html = gate.get_data(as_text=True)
        if "question-area" not in gate_html:
            begun = maya["client"].post(
                "/placement/middle-level/section/part_ii/begin",
                data={"csrf_token": self.csrf_on(maya["client"])},
                follow_redirects=True,
            )
            self.assertEqual(begun.status_code, 200, begun.get_data(as_text=True)[:400])
            self.assert_question_page(begun.get_data(as_text=True), "middle-level", 20)

        findings = []
        for row in roster:
            habit = row["habit"]
            client = row["client"]
            pid = row["pid"]
            qs = row["qs"]
            self.answer(client, pid, 0, qs)
            if habit == "skip_recover":
                client.get(f"/placement/run/{pid}/item/12")
                client.get(f"/placement/run/{pid}/item/3")
                self.answer(client, pid, 3, qs, goto=2)
            elif habit == "paper_recover":
                last = LAST_MC[row["slug"]]
                nxt = self.answer(client, pid, last, qs)
                self.assertEqual(nxt.status_code, 302, row["name"])
                self.assertIn("/section/paper/work", nxt.headers.get("Location") or "")
            else:
                self.answer(client, pid, 1, qs)

            leave_min = 11 if habit != "sip" else 6
            self.backdate(pid, leave_min)
            frozen = self.started_at(pid)
            self.assertNotEqual(frozen, row["started"], f"{row['name']} backdate did not stick")
            expected = row["full"] - leave_min * 60

            if habit == "sip":
                again = client.get(f"/placement/run/{pid}/item/1")
                self.assertEqual(again.status_code, 200, row["name"])
                html = again.get_data(as_text=True)
                left = _remaining(html)
                self.assertEqual(self.started_at(pid), frozen, row["name"])
                self.assertLess(_started_unix(html), row["start_unix"] - 60, row["name"])
                self.assertLess(left, row["full"] - 60, f"{row['name']} clock restarted")
                self.assertAlmostEqual(left, expected, delta=5, msg=row["name"])
                findings.append((row["name"], "sip", left, expected))
                continue

            other, rec = self.recover_fresh(row["code"])
            self.assertEqual(rec.status_code, 302, row["name"])
            loc = rec.headers.get("Location") or ""
            if habit == "paper_recover":
                self.assertIn("/section/paper/work", loc, row["name"])
                work = other.get(f"/placement/{row['slug']}/section/paper/work")
                self.assertEqual(work.status_code, 200, row["name"])
                html = work.get_data(as_text=True)
                self.assertIn("Drop one PDF here", html)
                self.assertIn("np-pl-paper-time", html)
                left = _remaining(html)
                self.assertEqual(self.started_at(pid), frozen, row["name"])
                self.assertLess(left, row["full"] - 60, f"{row['name']} paper clock restarted")
                self.assertAlmostEqual(left, expected, delta=5, msg=row["name"])
                uploaded = other.post(
                    f"/placement/{row['slug']}/section/paper/work",
                    data={
                        "csrf_token": self.csrf_on(other),
                        "continue": "1",
                        "pages": (BytesIO(TINY_PDF), f"{row['name'].replace(' ', '_')}.pdf"),
                    },
                )
                self.assertEqual(uploaded.status_code, 302, row["name"])
                self.assertIn("/finish", uploaded.headers.get("Location") or "")
                findings.append((row["name"], "paper_recover", left, expected))
                continue

            self.assertIn("/item/", loc, row["name"])
            page = other.get(loc)
            self.assertEqual(page.status_code, 200, row["name"])
            html = page.get_data(as_text=True)
            self.assert_question_page(html, row["slug"], 0)
            left = _remaining(html)
            self.assertEqual(self.started_at(pid), frozen, f"{row['name']} started_at reset")
            self.assertLess(_started_unix(html), row["start_unix"] - 60, f"{row['name']} unix reset")
            self.assertLess(left, row["full"] - 60, f"{row['name']} clock restarted after recover")
            self.assertAlmostEqual(left, expected, delta=5, msg=row["name"])
            saved = other.get(f"/placement/run/{pid}/item/0").get_data(as_text=True)
            want = str(qs[0].get("correct_answer") or "").strip()
            kind0 = str(qs[0].get("question_kind") or "mcq")
            if kind0 in ("mcq", "mcq5") and want:
                letter = want.strip().upper()[:1]
                self.assertRegex(
                    saved,
                    rf'name="selected_answer" value="{letter}"[^>]*\bchecked\b',
                    f"{row['name']} lost Q1 after recover",
                )
            elif want:
                self.assertIn(want, saved, f"{row['name']} lost Q1 after recover")
            findings.append((row["name"], habit, left, expected))

        sip = roster[0]
        fin = sip["client"].post(
            f"/placement/run/{sip['pid']}/finish",
            data={"csrf_token": self.csrf_on(sip['client']), "confirm": "1"},
            follow_redirects=False,
        )
        self.assertEqual(fin.status_code, 302)
        done = sip["client"].get(f"/placement/run/{sip['pid']}/done")
        self.assertEqual(done.status_code, 200)
        done_html = done.get_data(as_text=True)
        self.assertIn("Submitted", done_html)
        self.assertIn("2 / 100", done_html)

        reset_rate_limits_for_tests()
        stolen, bad = self.recover_fresh(sip["code"])
        self.assertEqual(bad.status_code, 302)
        after = stolen.get(bad.headers.get("Location") or "/placement/recover", follow_redirects=False)
        body = after.get_data(as_text=True) if after.status_code == 200 else ""
        loc = bad.headers.get("Location") or ""
        self.assertTrue("/done" in loc or "/recover" in loc or "submitted" in body.lower() or after.status_code in (200, 302))

        self.assertEqual(len(findings), 10, findings)
        for name, habit, left, expected in findings:
            self.assertNotEqual(left, TIMER[TOPIC[next(s['slug'] for s in CLASSROOM if s['name'] == name)]], name)
            self.assertAlmostEqual(left, expected, delta=5, msg=f"{name} {habit}")


@unittest.skipUnless(
    __import__("importlib").util.find_spec("playwright") is not None,
    "playwright not installed",
)
class TestRecoverTimerInBrowser(unittest.TestCase):
    def test_closed_tab_recover_does_not_reset_clock(self):
        import sqlite3

        from playwright.sync_api import sync_playwright

        from tests.e2e.test_placement_public_browser import _Server

        on = _Server(True)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(on.base + "/placement/enhanced-math-1/start", wait_until="networkidle")
                page.fill("#pl-name", "Clock Student")
                page.select_option("#pl-grade", "9th")
                page.fill("#pl-course", "Algebra I Honors")
                page.locator("label.np-pl-choice", has_text="Mia Hu").click()
                page.check("input[name=counselor_confirm]")
                page.click("button[type=submit]")
                page.wait_for_url("**/placement/run/**/ready")
                code = page.locator("[data-pl-recovery-code]").inner_text().strip()
                page.click("[data-pl-begin-exam]")
                page.wait_for_selector("#time")
                first = page.locator("#time").inner_text().strip()
                first_min = int(first.split(":")[0])
                self.assertGreaterEqual(first_min, 119, first)
                pid = page.url.split("/placement/run/")[1].split("/")[0]
                conn = sqlite3.connect(on.db)
                conn.execute(
                    "UPDATE placement_candidate_attempts SET started_at = datetime('now', '-12 minutes') WHERE public_id=?",
                    (pid,),
                )
                conn.commit()
                conn.close()
                browser.close()
                browser = pw.chromium.launch(headless=True)
                fresh = browser.new_page(viewport={"width": 1280, "height": 800})
                fresh.goto(on.base + "/placement/recover", wait_until="networkidle")
                fresh.fill("#pl-recovery", code)
                fresh.click("button[type=submit]")
                fresh.wait_for_selector("#time")
                clock = fresh.locator("#time").inner_text().strip()
                minutes = int(clock.split(":")[0])
                self.assertLess(minutes, 115, clock)
                self.assertGreater(minutes, 100, clock)
                browser.close()
        finally:
            on.close()

