"""Public Placement access gate tests. Local copy DB only. No production writes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

BANK = os.path.join(ROOT, "data", "question_bank.json")
LIVE_DB = os.path.join(ROOT, "sat.db")
BANK_SHA = "238934f8b1893d91f8b6fd92e7d326854620f1da1fc14ef2dde36a4a58be83c0"
SLUGS = (
    "middle-level",
    "enhanced-math-1",
    "enhanced-math-2",
    "upper-algebra-precalc",
)
COUNTS = {
    "middle_level": 100,
    "enhanced_math_1": 65,
    "enhanced_math_2": 69,
    "placement_full": 85,
}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_db(dest: str) -> None:
    shutil.copy2(LIVE_DB, dest)
    _wipe_placement_tables_in_copy(dest)


def _wipe_placement_tables_in_copy(db_path: str) -> None:
    """Clear Placement rows on a TEMP copy only. Never touches LIVE_DB or production."""
    live = os.path.realpath(LIVE_DB)
    dest = os.path.realpath(db_path)
    if dest == live or dest.startswith("/var/data"):
        raise RuntimeError("refusing to wipe placement tables on live/production db")
    conn = sqlite3.connect(db_path)
    try:
        names = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table in (
            "placement_candidate_sessions",
            "placement_candidate_drafts",
            "placement_candidate_responses",
            "placement_candidate_attempts",
            "placement_candidates",
        ):
            if table in names:
                conn.execute(f"DELETE FROM {table}")
        conn.commit()
    finally:
        conn.close()


def _count(db_path: str, table: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pl-pub-")
        self.db = os.path.join(self.tmp, "sat.db")
        copy_db(self.db)
        self.attempts_before = _count(self.db, "practice_attempts")
        self.responses_before = _count(self.db, "practice_responses")
        import app as app_mod
        from placement_public import reset_rate_limits_for_tests

        reset_rate_limits_for_tests()
        self.app_mod = app_mod
        self._orig_db = app_mod.DB_PATH
        self._orig_ready = app_mod._DB_SCHEMA_READY
        app_mod.DB_PATH = self.db
        app_mod._DB_SCHEMA_READY = False
        app_mod.app.config["TESTING"] = True
        app_mod.app.config["PLACEMENT_PUBLIC_ACCESS"] = False
        os.environ.pop("PLACEMENT_PUBLIC_ACCESS", None)
        self.client = app_mod.app.test_client()

    def tearDown(self):
        self.app_mod.DB_PATH = self._orig_db
        self.app_mod._DB_SCHEMA_READY = self._orig_ready
        os.environ.pop("PLACEMENT_PUBLIC_ACCESS", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def flag_on(self):
        self.app_mod.app.config["PLACEMENT_PUBLIC_ACCESS"] = True
        os.environ["PLACEMENT_PUBLIC_ACCESS"] = "1"

    def login(self, user_id=2, role="student", username="s1"):
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_role"] = role
            sess["username"] = username
            sess["csrf_token"] = "test-csrf"

    def csrf(self) -> str:
        with self.client.session_transaction() as sess:
            token = sess.get("csrf_token") or "test-csrf"
            sess["csrf_token"] = token
            return token

    def begin(self, slug="enhanced-math-1", name="Alex Chen", grade="8th", advisor="Mia Hu", confirm=True):
        self.client.get(f"/placement/{slug}/start")
        nonce = ""
        html = self.client.get(f"/placement/{slug}/start").get_data(as_text=True)
        m = re.search(r'name="begin_nonce" value="([^"]+)"', html)
        if m:
            nonce = m.group(1)
        data = {
            "csrf_token": self.csrf(),
            "student_name": name,
            "student_grade": grade,
            "student_math_course": "Algebra I Honors",
            "student_school": "Test School",
            "begin_nonce": nonce,
        }
        if advisor:
            if advisor in ("Mia Hu", "Jimmy Zheng"):
                data["advisor_choice"] = advisor
            else:
                data["advisor_choice"] = "Other"
                data["advisor_other"] = advisor
        if confirm:
            data["counselor_confirm"] = "1"
        rv = self.client.post(
            f"/placement/{slug}/begin",
            data=data,
            follow_redirects=False,
        )
        return rv

    def attempt_id(self, public_id: str) -> int:
        conn = sqlite3.connect(self.db)
        try:
            row = conn.execute(
                "SELECT id FROM placement_candidate_attempts WHERE public_id=?",
                (public_id,),
            ).fetchone()
            self.assertIsNotNone(row, public_id)
            return int(row[0])
        finally:
            conn.close()

    def public_id_from_location(self, rv) -> str:
        loc = rv.headers.get("Location") or ""
        m = re.search(r"/placement/run/([^/]+)/", loc)
        self.assertIsNotNone(m, loc)
        return m.group(1)


class TestFlagOff(_Base):
    def test_unauthenticated_placement_still_login(self):
        for path in ["/placement"] + [f"/placement/{s}/start" for s in SLUGS]:
            rv = self.client.get(path, follow_redirects=False)
            self.assertEqual(rv.status_code, 302, path)
            self.assertIn("/login", rv.headers.get("Location") or "")
        conn = sqlite3.connect(self.db)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='placement_candidates'"
            ).fetchone()[0]
            if n:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM placement_candidates").fetchone()[0], 0)
        finally:
            conn.close()

    def test_admin_candidates_hidden(self):
        self.login(user_id=1, role="admin", username="teacher")
        rv = self.client.get("/admin")
        self.assertEqual(rv.status_code, 200)
        self.assertNotIn("Placement testers", rv.get_data(as_text=True))
        self.assertNotIn("np-admin-placement", rv.get_data(as_text=True))
        self.assertEqual(self.client.get("/admin/placement-candidates").status_code, 404)


class TestNonPlacementStillGated(_Base):
    def test_flag_on_blocks_sat_and_admin(self):
        self.flag_on()
        for path in ["/", "/practice", "/practice/algebra/1_1/0", "/admin", "/practice/analytics"]:
            rv = self.client.get(path, follow_redirects=False)
            self.assertEqual(rv.status_code, 302, path)
            self.assertIn("/login", rv.headers.get("Location") or "")


class TestShippedDefaultAllowsGuest(_Base):
    def test_guest_opens_catalog_without_signin(self):
        os.environ.pop("PLACEMENT_PUBLIC_ACCESS", None)
        self.app_mod.app.config["PLACEMENT_PUBLIC_ACCESS"] = True
        rv = self.client.get("/placement", follow_redirects=False)
        self.assertEqual(rv.status_code, 200)
        start = self.client.get("/placement/enhanced-math-1/start", follow_redirects=False)
        self.assertEqual(start.status_code, 200)
        self.assertIn("No account needed", self.client.get("/login").get_data(as_text=True))


class TestPublicProfile(_Base):
    def test_four_slugs_complete_profile(self):
        self.flag_on()
        catalog = self.client.get("/placement")
        self.assertEqual(catalog.status_code, 200)
        html = catalog.get_data(as_text=True)
        self.assertNotIn("Dashboard", html)
        self.assertNotIn('href="/practice"', html)
        for slug in SLUGS:
            start = self.client.get(f"/placement/{slug}/start")
            self.assertEqual(start.status_code, 200, slug)
            body = start.get_data(as_text=True)
            self.assertIn("You selected", body)
            self.assertIn("Mia Hu", body)
            self.assertIn("Jimmy Zheng", body)
            self.assertIn("Before you begin", body)
            self.assertIn("I confirm that I selected the appropriate placement test and will complete it independently.", body)
            rv = self.begin(slug=slug, name=f"Student {slug}")
            self.assertEqual(rv.status_code, 302, slug)
            self.assertIn("/placement/run/", rv.headers.get("Location") or "")

    def test_login_shows_placement_button(self):
        off = self.client.get("/login")
        self.assertEqual(off.status_code, 200)
        off_html = off.get_data(as_text=True)
        self.assertIn("Start Placement Test", off_html)
        self.assertIn('id="np-login-placement-start"', off_html)
        self.assertIn('href="/placement"', off_html)
        self.assertNotIn("Already started? Recover with your code", off_html)
        self.flag_on()
        on = self.client.get("/login")
        self.assertEqual(on.status_code, 200)
        on_html = on.get_data(as_text=True)
        self.assertIn("Start Placement Test", on_html)
        self.assertIn('id="np-login-placement-start"', on_html)
        self.assertIn('href="/placement"', on_html)
        self.assertIn("No account needed", on_html)
        self.assertIn("Your advisor sent you here.", on_html)
        self.assertIn("Already started? Recover with your code", on_html)

    def test_required_profile_rejects_incomplete(self):
        self.flag_on()
        html = self.client.get("/placement/enhanced-math-1/start").get_data(as_text=True)
        self.assertIn("Advisor <span class=\"np-pl-req\">required</span>", html)
        nonce = re.search(r'name="begin_nonce" value="([^"]+)"', html).group(1)
        token = self.csrf()
        base = {
            "csrf_token": token,
            "student_name": "Alex Chen",
            "student_grade": "8th",
            "student_math_course": "Algebra I Honors",
            "counselor_confirm": "1",
            "begin_nonce": nonce,
        }
        missing_course = dict(base, student_math_course="")
        missing_confirm = dict(base, counselor_confirm="")
        missing_advisor = dict(base)
        other_blank = dict(base, advisor_choice="Other", advisor_other=" ")
        for payload in (missing_course, missing_confirm, missing_advisor, other_blank):
            rv = self.client.post("/placement/enhanced-math-1/begin", data=payload)
            self.assertEqual(rv.status_code, 302)
            self.assertIn("/placement/enhanced-math-1/start", rv.headers.get("Location") or "")
        conn = sqlite3.connect(self.db)
        try:
            before = conn.execute("SELECT COUNT(*) FROM placement_candidates").fetchone()[0]
        finally:
            conn.close()
        html = self.client.get("/placement/enhanced-math-1/start").get_data(as_text=True)
        nonce = re.search(r'name="begin_nonce" value="([^"]+)"', html).group(1)
        ok = self.client.post(
            "/placement/enhanced-math-1/begin",
            data=dict(base, begin_nonce=nonce, advisor_choice="Mia Hu"),
        )
        self.assertEqual(ok.status_code, 302)
        pid = self.public_id_from_location(ok)
        conn = sqlite3.connect(self.db)
        try:
            after = conn.execute("SELECT COUNT(*) FROM placement_candidates").fetchone()[0]
            row = conn.execute(
                """
                SELECT c.counselor_source, c.grade, c.math_course
                FROM placement_candidates c
                JOIN placement_candidate_attempts a ON a.candidate_id = c.id
                WHERE a.public_id=?
                """,
                (pid,),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(after, before + 1)
        self.assertEqual(row[0], "Mia Hu")
        self.assertEqual(row[1], "8th")
        self.assertEqual(row[2], "Algebra I Honors")
        self.login(user_id=1, role="admin", username="teacher")
        listing = self.client.get("/admin/placement-candidates").get_data(as_text=True)
        self.assertIn("Mia Hu", listing)

    def test_advisor_query_is_plain_text_prefill_not_auth(self):
        self.flag_on()
        html = self.client.get(
            "/placement/enhanced-math-1/start?advisor=Mia%20Hu"
        ).get_data(as_text=True)
        self.assertIn('value="Mia Hu"', html)
        self.assertIn("checked", html)
        evil = self.client.get(
            "/placement/enhanced-math-1/start?advisor=%3Cscript%3Ealert(1)%3C/script%3E"
        ).get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", evil)
        self.assertIn("scriptalert(1)/script", evil.replace(" ", ""))
        catalog = self.client.get("/placement?advisor=Jimmy%20Zheng").get_data(as_text=True)
        self.assertIn("advisor=Jimmy", catalog)
        landing = self.client.get(
            "/placement/upper-algebra-precalc?advisor=Jimmy%20Zheng"
        ).get_data(as_text=True)
        self.assertIn("advisor=Jimmy", landing)

    def test_same_name_different_candidates(self):
        self.flag_on()
        self.begin(name="Alex Chen")
        c2 = self.app_mod.app.test_client()
        c2.get("/placement/enhanced-math-1/start")
        html = c2.get("/placement/enhanced-math-1/start").get_data(as_text=True)
        nonce = re.search(r'name="begin_nonce" value="([^"]+)"', html).group(1)
        with c2.session_transaction() as sess:
            token = sess.get("csrf_token") or "test-csrf"
            sess["csrf_token"] = token
        c2.post(
            "/placement/enhanced-math-1/begin",
            data={
                "csrf_token": token,
                "student_name": "Alex Chen",
                "student_grade": "8th",
                "student_math_course": "Algebra I",
                "advisor_choice": "Jimmy Zheng",
                "counselor_confirm": "1",
                "begin_nonce": nonce,
            },
        )
        conn = sqlite3.connect(self.db)
        try:
            rows = conn.execute(
                "SELECT public_id FROM placement_candidates WHERE display_name='Alex Chen'"
            ).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertNotEqual(rows[0][0], rows[1][0])
        finally:
            conn.close()


class TestIdempotency(_Base):
    def test_refresh_does_not_duplicate_attempt(self):
        self.flag_on()
        rv = self.begin()
        pid = self.public_id_from_location(rv)
        self.client.get(f"/placement/run/{pid}/ready")
        self.client.get(f"/placement/run/{pid}/item/0")
        self.client.get(f"/placement/enhanced-math-1/start")
        self.client.get(f"/placement/run/{pid}/item/0")
        conn = sqlite3.connect(self.db)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM placement_candidate_attempts WHERE public_id=?",
                (pid,),
            ).fetchone()[0]
            self.assertEqual(n, 1)
        finally:
            conn.close()

    def test_double_begin_and_double_submit(self):
        self.flag_on()
        self.client.get("/placement/enhanced-math-1/start")
        html = self.client.get("/placement/enhanced-math-1/start").get_data(as_text=True)
        nonce = re.search(r'name="begin_nonce" value="([^"]+)"', html).group(1)
        data = {
            "csrf_token": self.csrf(),
            "student_name": "Pat Lee",
            "student_grade": "9th",
            "student_math_course": "Geometry",
            "advisor_choice": "Mia Hu",
            "counselor_confirm": "1",
            "begin_nonce": nonce,
        }
        a = self.client.post("/placement/enhanced-math-1/begin", data=data)
        b = self.client.post("/placement/enhanced-math-1/begin", data=data)
        self.assertEqual(a.status_code, 302)
        self.assertEqual(b.status_code, 302)
        self.assertEqual(a.headers.get("Location"), b.headers.get("Location"))
        pid = self.public_id_from_location(a)
        self.client.get(f"/placement/run/{pid}/item/0")
        finish = {
            "csrf_token": self.csrf(),
            "confirm": "1",
        }
        self.client.post(f"/placement/run/{pid}/finish", data=finish)
        self.client.post(f"/placement/run/{pid}/finish", data=finish)
        conn = sqlite3.connect(self.db)
        try:
            rows = conn.execute(
                "SELECT status FROM placement_candidate_attempts WHERE public_id=?",
                (pid,),
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "submitted")
            cand = conn.execute(
                """
                SELECT COUNT(*) FROM placement_candidates c
                JOIN placement_candidate_attempts a ON a.candidate_id = c.id
                WHERE a.public_id=?
                """,
                (pid,),
            ).fetchone()[0]
            self.assertEqual(cand, 1)
        finally:
            conn.close()


class TestRecoveryAndIsolation(_Base):
    def test_recover_wrong_expired_revoked(self):
        self.flag_on()
        rv = self.begin()
        pid = self.public_id_from_location(rv)
        ready = self.client.get(f"/placement/run/{pid}/ready").get_data(as_text=True)
        code = re.search(r'data-pl-recovery-code>([^<]+)', ready).group(1)
        other = self.app_mod.app.test_client()
        other.get("/placement/recover")
        with other.session_transaction() as sess:
            token = sess.get("csrf_token") or "x"
            sess["csrf_token"] = token
        bad = other.post("/placement/recover", data={"csrf_token": token, "recovery_code": "NOPE-NOPE-NOPE-NOPE"})
        self.assertEqual(bad.status_code, 302)
        ok = other.post("/placement/recover", data={"csrf_token": token, "recovery_code": code})
        self.assertEqual(ok.status_code, 302)
        self.assertIn(pid, ok.headers.get("Location") or "")
        self.login(user_id=1, role="admin", username="teacher")
        attempt_id = self.attempt_id(pid)
        self.client.post(
            f"/admin/placement-candidates/{attempt_id}/invalidate",
            data={"csrf_token": "test-csrf"},
        )
        third = self.app_mod.app.test_client()
        third.get("/placement/recover")
        with third.session_transaction() as sess:
            token = sess.get("csrf_token") or "x"
            sess["csrf_token"] = token
        revoked = third.post("/placement/recover", data={"csrf_token": token, "recovery_code": code})
        self.assertEqual(revoked.status_code, 302)
        self.assertIn("/placement/recover", revoked.headers.get("Location") or "")

    def test_student_a_cannot_read_student_b(self):
        self.flag_on()
        rv = self.begin(name="Aaa")
        pid_a = self.public_id_from_location(rv)
        other = self.app_mod.app.test_client()
        other.get("/placement/enhanced-math-1/start")
        html = other.get("/placement/enhanced-math-1/start").get_data(as_text=True)
        nonce = re.search(r'name="begin_nonce" value="([^"]+)"', html).group(1)
        with other.session_transaction() as sess:
            token = sess.get("csrf_token") or "x"
            sess["csrf_token"] = token
        rv_b = other.post(
            "/placement/enhanced-math-1/begin",
            data={
                "csrf_token": token,
                "student_name": "Bbb",
                "student_grade": "8th",
                "student_math_course": "Algebra I",
                "advisor_choice": "Mia Hu",
                "counselor_confirm": "1",
                "begin_nonce": nonce,
            },
        )
        steal = other.get(f"/placement/run/{pid_a}/item/0", follow_redirects=False)
        self.assertEqual(steal.status_code, 404)
        self.assertIn("/placement/run/", rv_b.headers.get("Location") or "")


class TestLockAndAdmin(_Base):
    def test_final_submit_locks_answers(self):
        self.flag_on()
        rv = self.begin()
        pid = self.public_id_from_location(rv)
        self.client.get(f"/placement/run/{pid}/item/0")
        self.client.post(
            f"/placement/run/{pid}/item/0",
            data={"csrf_token": self.csrf(), "selected_answer": "A", "qnum": "0"},
        )
        self.client.post(
            f"/placement/run/{pid}/finish",
            data={"csrf_token": self.csrf(), "confirm": "1"},
        )
        locked = self.client.post(
            f"/placement/run/{pid}/item/0",
            data={"csrf_token": self.csrf(), "selected_answer": "B", "qnum": "0"},
        )
        self.assertEqual(locked.status_code, 302)
        self.assertIn("/done", locked.headers.get("Location") or "")
        conn = sqlite3.connect(self.db)
        try:
            ans = conn.execute(
                "SELECT selected_answer FROM placement_candidate_responses WHERE attempt_id=? AND question_index=0",
                (self.attempt_id(pid),),
            ).fetchone()[0]
            self.assertEqual(ans, "A")
        finally:
            conn.close()

    def test_admin_progress_report_reopen(self):
        self.flag_on()
        rv = self.begin()
        pid = self.public_id_from_location(rv)
        self.client.get(f"/placement/run/{pid}/item/0")
        self.client.post(
            f"/placement/run/{pid}/item/0",
            data={"csrf_token": self.csrf(), "selected_answer": "A", "qnum": "0"},
        )
        self.client.post(
            f"/placement/run/{pid}/finish",
            data={"csrf_token": self.csrf(), "confirm": "1"},
        )
        self.login(user_id=1, role="admin", username="teacher")
        home = self.client.get("/admin")
        self.assertEqual(home.status_code, 200)
        home_html = home.get_data(as_text=True)
        self.assertIn("Placement testers", home_html)
        self.assertIn("Alex Chen", home_html)
        self.assertIn("Mia Hu", home_html)
        listing = self.client.get("/admin/placement-candidates")
        self.assertEqual(listing.status_code, 200)
        listing_html = listing.get_data(as_text=True)
        self.assertIn("Alex Chen", listing_html)
        self.assertIn("Mia Hu", listing_html)
        self.assertIn("Advisor", listing_html)
        self.assertNotIn("Provisional — paper responses not reviewed", listing_html)
        self.assertNotIn("Final score", listing_html)
        attempt_id = self.attempt_id(pid)
        detail = self.client.get(f"/admin/placement-candidates/{attempt_id}")
        self.assertEqual(detail.status_code, 200)
        detail_html = detail.get_data(as_text=True)
        self.assertIn("Score", detail_html)
        self.assertNotIn("Paper FRQ", detail_html)
        self.assertNotIn("Provisional — paper responses not reviewed", detail_html)
        self.assertNotIn("Final score", detail_html)
        pdf = self.client.get(f"/admin/placement-candidates/{attempt_id}/report.pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertIn("pdf", pdf.mimetype)
        from io import BytesIO
        from pypdf import PdfReader

        pdf_text = "\n".join(
            (page.extract_text() or "") for page in PdfReader(BytesIO(pdf.data)).pages
        )
        self.assertIn("Placement results", pdf_text)
        self.assertIn("Score by section", pdf_text)
        self.assertIn("Item-by-item results", pdf_text)
        self.assertNotIn("Course placement report", pdf_text)
        self.assertNotIn("Reopen submitted attempt", pdf_text)
        self.client.post(
            f"/admin/placement-candidates/{attempt_id}/reopen",
            data={"csrf_token": "test-csrf"},
        )
        conn = sqlite3.connect(self.db)
        try:
            status = conn.execute(
                "SELECT status FROM placement_candidate_attempts WHERE public_id=?",
                (pid,),
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(status, "in_progress")


class TestBanksAndLegacy(_Base):
    def test_item_counts_unchanged(self):
        from app import BANKS, get_questions_for_topic

        mapping = {
            "middle_level": "middle-level",
            "enhanced_math_1": "enhanced-math-1",
            "enhanced_math_2": "enhanced-math-2",
            "placement_full": "upper-algebra-precalc",
        }
        for topic, expected in COUNTS.items():
            qs = get_questions_for_topic("placement", topic, BANKS["placement"][topic])
            self.assertEqual(len(qs), expected, topic)
            self.assertTrue(any(q.get("correct_answer") or q.get("answer") or q.get("choices") for q in qs))
            self.assertEqual(mapping[topic] in SLUGS, True)
        self.assertEqual(sha256_file(BANK), BANK_SHA)

    def test_logged_in_student_still_uses_practice_attempts(self):
        self.flag_on()
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("UPDATE users SET access_grants=NULL, access_scope='full' WHERE username='s1'")
            conn.commit()
        finally:
            conn.close()
        self.login()
        start = self.client.get("/placement/enhanced-math-1/start")
        self.assertEqual(start.status_code, 200)
        start_html = start.get_data(as_text=True)
        self.assertNotIn("begin_nonce", start_html)
        self.assertIn("Advisor", start_html)
        self.assertIn("Current school math class", start_html)
        self.assertIn("Before you begin", start_html)
        self.assertIn("Mia Hu", start_html)
        rv = self.client.post(
            "/placement/enhanced-math-1/begin",
            data={
                "csrf_token": "test-csrf",
                "student_name": "Account Student",
                "student_grade": "10th",
                "student_math_course": "Algebra II Honors",
                "counselor_confirm": "1",
            },
        )
        self.assertEqual(rv.status_code, 302)
        self.assertIn("/practice/placement/", rv.headers.get("Location") or "")
        self.client.get("/practice/placement/enhanced_math_1/0")
        self.assertGreaterEqual(_count(self.db, "practice_attempts"), self.attempts_before + 1)
        conn = sqlite3.connect(self.db)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM placement_candidates").fetchone()[0], 0)
        finally:
            conn.close()

    def test_old_tables_never_shrink(self):
        self.flag_on()
        self.begin()
        self.assertGreaterEqual(_count(self.db, "practice_attempts"), self.attempts_before)
        self.assertGreaterEqual(_count(self.db, "practice_responses"), self.responses_before)


class TestRateLimit(_Base):
    def test_create_rate_limit(self):
        self.flag_on()
        from placement_public import RATE_LIMITS, record_rate_hit, reset_rate_limits_for_tests

        reset_rate_limits_for_tests()
        max_n, _ = RATE_LIMITS["create"]
        self.client.get("/placement/enhanced-math-1/start")
        html = self.client.get("/placement/enhanced-math-1/start").get_data(as_text=True)
        nonce = re.search(r'name="begin_nonce" value="([^"]+)"', html).group(1)
        for _ in range(max_n):
            record_rate_hit("create", "127.0.0.1")
        rv = self.client.post(
            "/placement/enhanced-math-1/begin",
            data={
                "csrf_token": self.csrf(),
                "student_name": "Rate",
                "student_grade": "8th",
                "student_math_course": "Algebra I",
                "advisor_choice": "Mia Hu",
                "counselor_confirm": "1",
                "begin_nonce": nonce,
            },
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        )
        self.assertEqual(rv.status_code, 429)


class TestMigration(_Base):
    def test_sql_additive_dry_run_idempotent_rollback(self):
        from scripts import placement_public_migrate as migrate

        blob = "\n".join(migrate.SQL_STATEMENTS)
        for word in ("DROP", "TRUNCATE", "DELETE", "ALTER"):
            self.assertNotRegex(blob, rf"\b{word}\b")
        migrate.assert_sql_is_additive()
        with mock.patch.object(migrate.sqlite3, "connect") as connect:
            with mock.patch.object(sys, "argv", ["placement_public_migrate.py", "--dry-run"]):
                self.assertEqual(migrate.main(), 0)
            connect.assert_not_called()
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "placement_public_migrate.py"), "--dry-run"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("DRY-RUN", proc.stdout)
        local = os.path.join(self.tmp, "mig.db")
        copy_db(local)
        migrate.apply_schema(local)
        migrate.apply_schema(local)
        conn = sqlite3.connect(local)
        try:
            names = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'placement_candidate%'"
                )
            }
        finally:
            conn.close()
        self.assertIn("placement_candidates", names)
        with self.assertRaises(SystemExit):
            migrate.apply("/var/data/sat.db")
        boom = os.path.join(self.tmp, "boom.db")
        sqlite3.connect(boom).close()
        from placement_public import SQL_STATEMENTS

        def _partial(conn):
            conn.execute(SQL_STATEMENTS[0])
            raise RuntimeError("boom")

        with mock.patch.object(migrate, "ensure_tables", side_effect=_partial):
            with self.assertRaises(RuntimeError):
                migrate.apply_schema(boom)
        conn = sqlite3.connect(boom)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='placement_candidates'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(n, 0)

    def test_bank_hash_untouched(self):
        self.assertEqual(sha256_file(BANK), BANK_SHA)


def _student_answer(q: dict) -> str:
    from answer_grader import _enhanced_fr_tokens, is_placement_graphing_item

    kind = q.get("question_kind")
    if kind in ("mcq", "mcq5"):
        return str(q.get("correct_answer") or "A")
    if is_placement_graphing_item(q):
        return "graphed"
    tokens = _enhanced_fr_tokens(q) if q.get("knowledge_section") == "FR" else []
    if tokens:
        return tokens[0]
    alts = q.get("answer_alternates") or []
    if alts:
        return str(alts[0])
    key = str(q.get("correct_answer") or "")
    if "no solution" in key.lower():
        return "no solution"
    return key


class TestPreviewNotMixed(_Base):
    def test_upper_landing_preview_is_one_visual_example(self):
        self.flag_on()
        html = self.client.get("/placement/upper-algebra-precalc").get_data(as_text=True)
        self.assertIn(r"\( 2x + 5 = 17 \)", html)
        self.assertNotIn("10x + 15y = 85", html)
        self.assertNotIn("462; 332,640", html)
        self.assertNotIn("332,640", html)


class TestFullPaperSubmits(_Base):
    def _submit_paper(self, slug: str, topic: str, expected_n: int):
        from app import BANKS, get_questions_for_topic
        from placement_public import reset_rate_limits_for_tests

        self.flag_on()
        reset_rate_limits_for_tests()
        qs = get_questions_for_topic("placement", topic, BANKS["placement"][topic])
        self.assertEqual(len(qs), expected_n, topic)
        rv = self.begin(slug=slug, name=f"Paper {topic}")
        self.assertEqual(rv.status_code, 302, topic)
        pid = self.public_id_from_location(rv)
        self.client.get(f"/placement/run/{pid}/item/0")
        for i, q in enumerate(qs):
            post = self.client.post(
                f"/placement/run/{pid}/item/{i}",
                data={
                    "csrf_token": self.csrf(),
                    "selected_answer": _student_answer(q),
                    "qnum": str(i),
                },
            )
            self.assertNotEqual(post.status_code, 429, f"{topic} save {i}")
            self.assertIn(post.status_code, (200, 302), f"{topic} save {i}")
        # Repeat last save: must not duplicate the response row.
        last_ans = _student_answer(qs[-1])
        self.client.post(
            f"/placement/run/{pid}/item/{expected_n - 1}",
            data={
                "csrf_token": self.csrf(),
                "selected_answer": last_ans,
                "qnum": str(expected_n - 1),
            },
        )
        fin = self.client.post(
            f"/placement/run/{pid}/finish",
            data={"csrf_token": self.csrf(), "confirm": "1"},
        )
        self.assertNotEqual(fin.status_code, 429, topic)
        self.assertEqual(fin.status_code, 302, topic)
        self.assertIn("/done", fin.headers.get("Location") or "")
        aid = self.attempt_id(pid)
        conn = sqlite3.connect(self.db)
        try:
            rows = conn.execute(
                """
                SELECT question_index, is_correct, selected_answer
                FROM placement_candidate_responses
                WHERE attempt_id=?
                ORDER BY question_index
                """,
                (aid,),
            ).fetchall()
            n_attempts = conn.execute(
                "SELECT COUNT(*) FROM placement_candidate_attempts WHERE public_id=?",
                (pid,),
            ).fetchone()[0]
            att = conn.execute(
                "SELECT status, answered_count, total_count, score_json FROM placement_candidate_attempts WHERE public_id=?",
                (pid,),
            ).fetchone()
        finally:
            conn.close()
        idxs = [r[0] for r in rows]
        self.assertEqual(n_attempts, 1, topic)
        self.assertEqual(len(rows), expected_n, topic)
        self.assertEqual(len(set(idxs)), expected_n, topic)
        self.assertEqual(idxs, list(range(expected_n)), topic)
        self.assertEqual(att[0], "submitted", topic)
        self.assertEqual(int(att[1]), expected_n, topic)
        self.assertEqual(int(att[2]), expected_n, topic)
        return pid, aid, rows, json.loads(att[3] or "{}"), qs

    def test_middle_level_100_submitted(self):
        pid, aid, rows, score, qs = self._submit_paper("middle-level", "middle_level", 100)
        self.assertEqual(score.get("mcq_total"), 100)
        self.assertEqual(score.get("mcq_correct"), 100)
        self.assertEqual(score.get("paper_frq_total"), 0)
        self.assertEqual(score.get("auto_incorrect"), 0)
        self.assertFalse(score.get("provisional"))
        self.assertTrue(all(r[1] == 1 for r in rows))
        html = self.client.get(f"/placement/run/{pid}/done").get_data(as_text=True)
        self.assertIn("100 / 100", html)
        self.assertNotIn("Paper FRQ", html)
        self.assertNotIn("Final score", html)

    def test_enhanced_math_1_65_manual_counts(self):
        pid, aid, rows, score, qs = self._submit_paper("enhanced-math-1", "enhanced_math_1", 65)
        graphing = sum(1 for q in qs if q.get("question_kind") == "constructed_response")
        self.assertEqual(graphing, 4)
        self.assertEqual(score.get("mcq_total"), 61)
        self.assertEqual(score.get("paper_frq_total"), 4)
        self.assertEqual(score.get("auto_incorrect"), 0)
        self.assertEqual(score.get("total"), 61)
        q55 = rows[54]
        self.assertIn(q55[1], (0, 1, None))
        self.assertNotEqual(q55[2], "PAPER_COMPLETE")

    def test_enhanced_math_2_69_q67(self):
        pid, aid, rows, score, qs = self._submit_paper("enhanced-math-2", "enhanced_math_2", 69)
        self.assertEqual(score.get("mcq_total"), 65)
        self.assertEqual(score.get("paper_frq_total"), 4)
        self.assertNotEqual(rows[66][2], "PAPER_COMPLETE")
        self.assertEqual(rows[66][1], 1)
        self.assertEqual(score.get("auto_incorrect"), 0)

    def test_upper_school_85_q59_unique(self):
        pid, aid, rows, score, qs = self._submit_paper(
            "upper-algebra-precalc", "placement_full", 85
        )
        self.assertEqual(score.get("mcq_total"), 85)
        self.assertEqual(score.get("paper_frq_total"), 0)
        q59 = qs[58]
        texts = [re.sub(r"\s+", "", str(c)) for c in q59["choices"]]
        self.assertEqual(len(texts), 5)
        self.assertEqual(len(set(texts)), 5)
        self.assertEqual(q59["correct_answer"], "A")
        self.assertEqual(rows[58][2], "A")
        self.assertEqual(rows[58][1], 1)

    def test_frq_keys_are_auto_scored(self):
        from app import BANKS, get_questions_for_topic
        from placement_public import reset_rate_limits_for_tests

        self.flag_on()
        reset_rate_limits_for_tests()
        qs = get_questions_for_topic("placement", "enhanced_math_2", BANKS["placement"]["enhanced_math_2"])
        rv = self.begin(slug="enhanced-math-2", name="FRQ isolation")
        pid = self.public_id_from_location(rv)
        self.client.get(f"/placement/run/{pid}/item/0")
        for i, q in enumerate(qs):
            self.client.post(
                f"/placement/run/{pid}/item/{i}",
                data={"csrf_token": self.csrf(), "selected_answer": _student_answer(q), "qnum": str(i)},
            )
        self.client.post(
            f"/placement/run/{pid}/finish",
            data={"csrf_token": self.csrf(), "confirm": "1"},
        )
        html = self.client.get(f"/placement/run/{pid}/done").get_data(as_text=True)
        self.assertIn("Score", html)
        self.assertNotIn("Paper FRQ", html)
        self.assertNotIn("Provisional — paper responses not reviewed", html)
        self.assertNotIn("Final score", html)
        self.login(user_id=1, role="admin", username="teacher")
        aid = self.attempt_id(pid)
        admin_html = self.client.get(f"/admin/placement-candidates/{aid}").get_data(as_text=True)
        self.assertIn("Score", admin_html)
        self.assertNotIn("Paper FRQ", admin_html)
        conn = sqlite3.connect(self.db)
        try:
            rows = conn.execute(
                "SELECT question_index, is_correct FROM placement_candidate_responses WHERE attempt_id=?",
                (aid,),
            ).fetchall()
            score = json.loads(
                conn.execute(
                    "SELECT score_json FROM placement_candidate_attempts WHERE public_id=?",
                    (pid,),
                ).fetchone()[0]
            )
        finally:
            conn.close()
        by_i = {r[0]: r[1] for r in rows}
        self.assertEqual(by_i.get(66), 1)
        self.assertEqual(score["mcq_total"], 65)
        self.assertEqual(score["auto_incorrect"], 0)
        self.assertGreaterEqual(score["mcq_correct"], 55)

    def test_graphing_has_textarea_and_mcq_has_choices(self):
        from placement_public import reset_rate_limits_for_tests

        self.flag_on()
        reset_rate_limits_for_tests()
        rv = self.begin(slug="enhanced-math-1", name="Paper UI")
        pid = self.public_id_from_location(rv)
        with self.client.session_transaction() as sess:
            sess["placement_em1_seen_graphing"] = True
            sess["placement_em1_seen_fr"] = True
        html = self.client.get(f"/placement/run/{pid}/item/50").get_data(as_text=True)
        self.assertIn('id="constructed-answer-input"', html)
        self.assertNotIn("I completed this question on paper", html)
        fr = self.client.get(f"/placement/run/{pid}/item/54").get_data(as_text=True)
        self.assertIn('id="spr-answer-input"', fr)
        mcq = self.client.get(f"/placement/run/{pid}/item/0").get_data(as_text=True)
        self.assertIn("choice-radio-input", mcq)
        self.assertNotIn("Complete this question on paper", mcq)

    def test_incomplete_frq_is_not_auto_incorrect(self):
        from app import BANKS, get_questions_for_topic
        from placement_public import reset_rate_limits_for_tests

        self.flag_on()
        reset_rate_limits_for_tests()
        qs = get_questions_for_topic(
            "placement", "enhanced_math_1", BANKS["placement"]["enhanced_math_1"]
        )
        rv = self.begin(slug="enhanced-math-1", name="Incomplete FRQ")
        pid = self.public_id_from_location(rv)
        self.client.get(f"/placement/run/{pid}/item/0")
        for i, q in enumerate(qs):
            if q.get("question_kind") not in ("mcq", "mcq5"):
                continue
            self.client.post(
                f"/placement/run/{pid}/item/{i}",
                data={
                    "csrf_token": self.csrf(),
                    "selected_answer": q["correct_answer"],
                    "qnum": str(i),
                },
            )
        self.client.post(
            f"/placement/run/{pid}/finish",
            data={"csrf_token": self.csrf(), "confirm": "1"},
        )
        aid = self.attempt_id(pid)
        conn = sqlite3.connect(self.db)
        try:
            rows = conn.execute(
                "SELECT question_index, is_correct FROM placement_candidate_responses WHERE attempt_id=?",
                (aid,),
            ).fetchall()
            score = json.loads(
                conn.execute(
                    "SELECT score_json FROM placement_candidate_attempts WHERE public_id=?",
                    (pid,),
                ).fetchone()[0]
            )
        finally:
            conn.close()
        self.assertEqual(len(rows), 50)
        self.assertTrue(all(r[1] == 1 for r in rows))
        self.assertEqual(score["mcq_correct"], 50)
        self.assertEqual(score["mcq_total"], 61)
        self.assertEqual(score["auto_incorrect"], 0)
        self.assertEqual(score["paper_frq_completed"], 0)
        self.assertEqual(score["paper_frq_total"], 4)
        self.login(user_id=1, role="admin", username="teacher")
        detail = self.client.get(f"/admin/placement-candidates/{aid}").get_data(as_text=True)
        self.assertIn("Score 50 / 61", detail)
        self.assertIn("Graphing 0 / 4 submitted", detail)
        self.assertNotIn("Final score", detail)
        listing = self.client.get("/admin/placement-candidates").get_data(as_text=True)
        self.assertIn("50/61", listing)
        self.assertIn("0/4", listing)
        self.assertNotIn("Final score", listing)

    def test_logged_in_paper_item_and_summary_not_final(self):
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                "UPDATE users SET access_grants=NULL, access_scope='full' WHERE username='s1'"
            )
            conn.commit()
        finally:
            conn.close()
        self.flag_on()
        self.login()
        self.client.get("/placement/enhanced-math-1/start")
        from app import BANKS, get_questions_for_topic

        qs = get_questions_for_topic(
            "placement", "enhanced_math_1", BANKS["placement"]["enhanced_math_1"]
        )
        rv = self.client.post(
            "/placement/enhanced-math-1/begin",
            data={
                "csrf_token": "test-csrf",
                "student_name": "Account Student",
                "student_grade": "10th",
                "student_math_course": "Algebra II Honors",
                "counselor_confirm": "1",
            },
        )
        self.assertEqual(rv.status_code, 302)
        with self.client.session_transaction() as sess:
            sess["placement_em1_seen_graphing"] = True
            sess["placement_em1_seen_fr"] = True
            sess["csrf_token"] = "test-csrf"
        page = self.client.get("/practice/placement/enhanced_math_1/50")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="constructed-answer-input"', html)
        self.assertNotIn("I completed this question on paper", html)
        self.assertNotIn('id="spr-answer-input"', html)
        aid_m = re.search(r'name="attempt_id" value="(\d+)"', html)
        self.assertIsNotNone(aid_m)
        aid = int(aid_m.group(1))
        self.client.post(
            "/practice/submit",
            data={
                "csrf_token": "test-csrf",
                "domain": "placement",
                "topic": "enhanced_math_1",
                "qnum": "50",
                "attempt_id": str(aid),
                "selected_answer": "graphed on the number line",
            },
        )
        self.client.post(
            "/practice/submit",
            data={
                "csrf_token": "test-csrf",
                "domain": "placement",
                "topic": "enhanced_math_1",
                "qnum": "0",
                "attempt_id": str(aid),
                "selected_answer": qs[0]["correct_answer"],
            },
        )
        summary = self.client.get(f"/practice/session/{aid}/summary").get_data(as_text=True)
        self.assertIn("Your results", summary)
        self.assertNotIn("Paper FRQ", summary)
        self.assertNotIn("Provisional — paper responses not reviewed", summary)
        self.assertNotIn("Final score", summary)
        self.assertIn("/ 61", summary)
        conn = sqlite3.connect(self.db)
        try:
            paper = conn.execute(
                "SELECT selected_answer, is_correct FROM practice_responses WHERE attempt_id=? AND question_index=50",
                (aid,),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(paper[0], "graphed on the number line")
        self.assertIsNone(paper[1])


if __name__ == "__main__":
    unittest.main()
