"""Real-browser E2E for Repair this skill. Does not deploy or migrate production."""
from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.test_skill_loop_gate import copy_db  # noqa: E402

E2E_PASSWORD = "e2e-repair-fresh-pass"
SKILL = "sat.alg.linear_rate_remaining"
SHOT_DIR = os.path.join(ROOT, "tests", "e2e", "screenshots")
LOG_PATH = os.path.join(SHOT_DIR, "repair_phase_log.json")
FRESH_USER = "e2e_repair_fresh"


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _wait_http(url: str, seconds: float = 20) -> None:
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except Exception as exc:
            last = exc
            time.sleep(0.2)
    raise RuntimeError(f"server did not start: {last}")


class _Server:
    def __init__(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="sr-e2e-")
        self.db = os.path.join(self.tmp, "sat.db")
        copy_db(self.db)
        from werkzeug.security import generate_password_hash

        conn = sqlite3.connect(self.db)
        pw = generate_password_hash(E2E_PASSWORD)
        conn.execute(
            """
            INSERT INTO users (username, password, password_hash, role, is_active, access_scope, student_view_scope)
            VALUES (?, '', ?, 'student', 1, 'full', 'own')
            """,
            (FRESH_USER, pw),
        )
        self.user_id = int(conn.execute("SELECT id FROM users WHERE username=?", (FRESH_USER,)).fetchone()[0])
        cur = conn.execute(
            "INSERT INTO practice_attempts (user_id, domain, topic, qnum) VALUES (?, 'algebra', '1_1', 0)",
            (self.user_id,),
        )
        aid = cur.lastrowid
        conn.execute(
            """
            INSERT INTO practice_responses
                (attempt_id, question_index, selected_answer, correct_answer, is_correct)
            VALUES (?, 0, 'A', 'C', 0), (?, 1, 'B', 'B', 1), (?, 2, 'A', 'A', 1)
            """,
            (aid, aid, aid),
        )
        conn.commit()
        conn.close()
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        env = os.environ.copy()
        env["DB_PATH"] = self.db
        env["E2E_PORT"] = str(self.port)
        env["SKILL_LOOP_PILOT"] = "0"
        env.pop("RENDER", None)
        env.pop("FLASK_ENV", None)
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "tests", "e2e", "launch_flask.py")],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _wait_http(self.base + "/login")

    def sql(self, sql: str, args=()):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql, args)
        rows = cur.fetchall()
        conn.commit()
        conn.close()
        return rows

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.tmp, ignore_errors=True)


def _login(page, base: str, username: str) -> None:
    page.goto(base + "/login")
    page.fill("#np-login-user", username)
    page.fill("#np-login-pass", E2E_PASSWORD)
    page.locator("form").locator("button[type=submit], input[type=submit]").first.click()
    page.wait_for_load_state("networkidle")


def _shot(page, name: str) -> None:
    os.makedirs(SHOT_DIR, exist_ok=True)
    page.screenshot(path=os.path.join(SHOT_DIR, name), full_page=True)


def _meta(page, server: _Server) -> dict:
    wrap = page.locator("[data-skill-repair-phase], [data-skill-loop-feedback], .sl-wrap").first
    item_id = wrap.get_attribute("data-item-id") or ""
    stem_hash = wrap.get_attribute("data-stem-hash") or ""
    phase = wrap.get_attribute("data-skill-repair-phase") or page.locator(".np-atelier-kicker").inner_text()
    stem = ""
    if page.locator("[data-sl-stem]").count():
        stem = page.locator("[data-sl-stem]").inner_text().strip()
    events = server.sql(
        """
        SELECT e.phase, e.item_ref, e.counts_as_independent, e.is_correct
        FROM skill_repair_events e
        JOIN skill_repair_sessions s ON s.id = e.session_id
        WHERE s.user_id = ?
        ORDER BY e.id DESC LIMIT 1
        """,
        (server.user_id,),
    )
    last = dict(events[0]) if events else {}
    return {
        "phase": phase,
        "item_id": item_id,
        "stem_hash": stem_hash,
        "stem": stem[:180],
        "counts_as_independent": last.get("counts_as_independent"),
        "last_event_phase": last.get("phase"),
        "last_item_ref": last.get("item_ref"),
    }


def _assert_scored_stem(test, page, key_text: str) -> None:
    stem = page.locator("[data-sl-stem]").inner_text().strip()
    test.assertGreater(len(stem), 0)
    test.assertIn(key_text, stem)
    visible = page.locator("body").inner_text()
    test.assertNotIn('<article class="', visible)
    test.assertNotIn('<section class="', visible)
    test.assertGreater(page.locator("[data-sl-asked]").count(), 0)
    has_choices = page.locator(".sl-choices input[type=radio]").count() > 0
    has_spr = page.locator("input[name=selected_answer]").count() > 0
    has_blanks = page.locator("[data-faded-blank]").count() > 0
    test.assertTrue(has_choices or has_spr or has_blanks)


@unittest.skipUnless(
    __import__("importlib").util.find_spec("playwright") is not None,
    "playwright not installed",
)
class SkillRepairBrowserE2E(unittest.TestCase):
    def test_fresh_student_repair_cycle(self):
        from playwright.sync_api import sync_playwright

        server = _Server()
        log = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                _login(page, server.base, FRESH_USER)

                page.goto(server.base + "/practice/analytics")
                page.wait_for_load_state("networkidle")
                before_html = page.locator("body").inner_text()
                self.assertIn("Repair this skill", before_html)
                self.assertNotIn("Immediate practice complete", before_html)
                _shot(page, "repair_analytics_before.png")

                page.goto(server.base + f"/practice/repair/{SKILL}/start")
                page.wait_for_load_state("networkidle")
                self.assertIn("/worked", page.url)
                self.assertGreater(len(page.locator("[data-sl-stem]").inner_text().strip()), 0)
                self.assertIn("Maya pumps", page.locator("[data-sl-stem]").inner_text())
                visible = page.locator("body").inner_text()
                self.assertIn("Strategy", visible)
                self.assertIn("Verified key", visible)
                self.assertIn("Full walkthrough", visible)
                self.assertNotIn('<article class="', visible)
                self.assertNotIn('<section class="', visible)
                _shot(page, "repair_worked.png")
                log.append(_meta(page, server))
                page.locator("button[type=submit]").click()
                page.wait_for_load_state("networkidle")

                self.assertIn("/faded", page.url)
                _assert_scored_stem(self, page, "sands wood")
                faded_id = page.locator("[data-skill-repair-phase]").get_attribute("data-item-id")
                faded_hash = page.locator("[data-skill-repair-phase]").get_attribute("data-stem-hash")
                page.click("#sr-hint-light")
                page.wait_for_selector("#sr-hint-panel:not([hidden])")
                light = page.locator("#sr-hint-panel").inner_text().strip()
                self.assertGreater(len(light), 10)
                page.click("#sr-hint-critical")
                page.wait_for_timeout(200)
                critical = page.locator("#sr-hint-panel").inner_text().strip()
                self.assertGreater(len(critical), 10)
                self.assertNotEqual(light, critical)
                page.click("#sr-solution")
                page.wait_for_selector("#sr-solution-panel:not([hidden])")
                sol = page.locator("#sr-solution-panel").inner_text()
                self.assertIn("Strategy", sol)
                self.assertIn("Verified key", sol)
                self.assertIn("Full walkthrough", sol)
                self.assertNotIn('<article class="', sol)
                self.assertNotIn('<section class="', sol)
                self.assertGreater(page.locator("[data-faded-blank]").count(), 0)
                _shot(page, "repair_faded_wrong_attempt.png")
                log.append({**_meta(page, server), "note": "faded first attempt"})
                page.fill("input[data-faded-blank=rate]", "1")
                page.fill("input[data-faded-blank=total_hours]", "1")
                page.locator("#sr-form button[type=submit]").click()
                page.wait_for_load_state("networkidle")
                self.assertIn("Incorrect", page.locator("h1").inner_text())
                self.assertIn("remediation", page.locator("body").inner_text().lower())
                _shot(page, "repair_faded_wrong_feedback.png")
                log.append({**_meta(page, server), "note": "faded wrong"})
                page.click("[data-sl-feedback-continue]")
                page.wait_for_load_state("networkidle")

                self.assertIn("/faded", page.url)
                self.assertGreater(page.locator(".sl-remediation").count(), 0)
                _assert_scored_stem(self, page, "kiln dries clay")
                faded2_id = page.locator("[data-skill-repair-phase]").get_attribute("data-item-id")
                faded2_hash = page.locator("[data-skill-repair-phase]").get_attribute("data-stem-hash")
                self.assertNotEqual(faded_id, faded2_id)
                self.assertNotEqual(faded_hash, faded2_hash)
                _shot(page, "repair_faded_remediation.png")
                log.append({**_meta(page, server), "note": "faded remediation attempt"})
                page.fill("input[data-faded-blank=rate]", "200")
                page.fill("input[data-faded-blank=total_hours]", "14")
                page.locator("#sr-form button[type=submit]").click()
                page.wait_for_load_state("networkidle")
                body = page.locator("body").inner_text()
                self.assertIn("Correct", page.locator("h1").inner_text())
                self.assertIn("Not an independent stage", body)
                self.assertNotIn("solution/hint was used, or this was a seen item", body)
                _shot(page, "repair_faded_correct_feedback.png")
                log.append({**_meta(page, server), "note": "faded correct"})
                page.click("[data-sl-feedback-continue]")
                page.wait_for_load_state("networkidle")

                self.assertIn("/isomorphic", page.url)
                _assert_scored_stem(self, page, "donation drive")
                iso_id = page.locator("[data-skill-repair-phase]").get_attribute("data-item-id")
                iso_hash = page.locator("[data-skill-repair-phase]").get_attribute("data-stem-hash")
                self.assertNotEqual(iso_id, faded_id)
                self.assertNotEqual(iso_id, faded2_id)
                self.assertNotEqual(iso_hash, faded_hash)
                self.assertEqual(page.locator("[data-skill-repair-phase]").get_attribute("data-skill-code"), SKILL)
                _shot(page, "repair_isomorphic.png")
                log.append({**_meta(page, server), "note": "isomorphic attempt"})
                page.check("input[name=selected_answer][value=C]")
                page.locator("#sr-form button[type=submit]").click()
                page.wait_for_load_state("networkidle")
                iso_event = server.sql(
                    """
                    SELECT e.counts_as_independent, e.item_ref
                    FROM skill_repair_events e
                    JOIN skill_repair_sessions s ON s.id = e.session_id
                    WHERE s.user_id = ? AND e.phase = 'isomorphic'
                    ORDER BY e.id DESC LIMIT 1
                    """,
                    (server.user_id,),
                )[0]
                self.assertEqual(int(iso_event["counts_as_independent"]), 1)
                _shot(page, "repair_isomorphic_feedback.png")
                log.append({**_meta(page, server), "note": "isomorphic correct", "counts_as_independent": 1})
                page.click("[data-sl-feedback-continue]")
                page.wait_for_load_state("networkidle")

                self.assertIn("/transfer", page.url)
                _assert_scored_stem(self, page, "feed silo")
                visible = page.locator("body").inner_text().lower()
                self.assertNotIn("how many solutions", visible)
                self.assertNotIn("no solution", visible)
                tr_id = page.locator("[data-skill-repair-phase]").get_attribute("data-item-id")
                tr_hash = page.locator("[data-skill-repair-phase]").get_attribute("data-stem-hash")
                self.assertNotEqual(tr_id, iso_id)
                self.assertNotEqual(tr_hash, iso_hash)
                self.assertEqual(page.locator("[data-skill-repair-phase]").get_attribute("data-skill-code"), SKILL)
                _shot(page, "repair_transfer.png")
                log.append({**_meta(page, server), "note": "transfer attempt"})
                page.check("input[name=selected_answer][value=C]")
                page.locator("#sr-form button[type=submit]").click()
                page.wait_for_load_state("networkidle")
                tr_event = server.sql(
                    """
                    SELECT e.counts_as_independent
                    FROM skill_repair_events e
                    JOIN skill_repair_sessions s ON s.id = e.session_id
                    WHERE s.user_id = ? AND e.phase = 'transfer'
                    ORDER BY e.id DESC LIMIT 1
                    """,
                    (server.user_id,),
                )[0]
                self.assertEqual(int(tr_event["counts_as_independent"]), 1)
                _shot(page, "repair_transfer_feedback.png")
                log.append({**_meta(page, server), "note": "transfer correct", "counts_as_independent": 1})
                page.click("[data-sl-feedback-continue]")
                page.wait_for_load_state("networkidle")

                self.assertTrue("/delayed" in page.url or "locked" in page.locator("body").inner_text().lower() or "hours" in page.locator("body").inner_text().lower())
                due_attr = page.locator("[data-delayed-available-at]").get_attribute("data-delayed-available-at") or ""
                session_id = page.locator("[data-session-id]").get_attribute("data-session-id") or ""
                self.assertTrue(due_attr)
                _shot(page, "repair_delayed_locked.png")
                log.append({"phase": "delayed_locked", "item_id": "", "stem_hash": "", "counts_as_independent": 0, "url": page.url, "delayed_available_at": due_attr, "session_id": session_id})

                page.goto(server.base + "/practice/analytics")
                page.wait_for_load_state("networkidle")
                after_html = page.locator("body").inner_text()
                self.assertIn("Immediate practice complete", after_html)
                self.assertIn("unlocks in approximately", after_html.lower())
                self.assertIn("Not mastered yet", after_html)
                self.assertEqual(page.get_by_role("link", name="Repair this skill").count(), 0)
                self.assertGreater(page.get_by_role("link", name="View delayed check").count(), 0)
                _shot(page, "repair_analytics_after.png")

                page.get_by_role("link", name="View delayed check").first.click()
                page.wait_for_load_state("networkidle")
                self.assertIn("/delayed", page.url)
                due2 = page.locator("[data-delayed-available-at]").get_attribute("data-delayed-available-at")
                sid2 = page.locator("[data-session-id]").get_attribute("data-session-id")
                self.assertEqual(due2, due_attr)
                self.assertEqual(sid2, session_id)

                page.goto(server.base + f"/practice/repair/{SKILL}/start")
                page.wait_for_load_state("networkidle")
                self.assertIn("/delayed", page.url)
                due3 = page.locator("[data-delayed-available-at]").get_attribute("data-delayed-available-at")
                sid3 = page.locator("[data-session-id]").get_attribute("data-session-id")
                self.assertEqual(due3, due_attr)
                self.assertEqual(sid3, session_id)
                rows = server.sql(
                    "SELECT id, delayed_available_at, status FROM skill_repair_sessions WHERE user_id=?",
                    (server.user_id,),
                )
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["delayed_available_at"], due_attr)
                self.assertEqual(str(rows[0]["id"]), session_id)
                _shot(page, "repair_delayed_resume.png")
                browser.close()
            os.makedirs(SHOT_DIR, exist_ok=True)
            with open(LOG_PATH, "w", encoding="utf-8") as fh:
                json.dump(log, fh, indent=2)
            print("REPAIR_E2E_LOG", json.dumps(log, indent=2))
        finally:
            server.close()
