"""Minimal Playwright E2E for the skill-loop slice.

Requires Chromium:
  python3 -m pip install playwright
  python3 -m playwright install chromium

Does not touch production, sat.db in-place, or question_bank.json.
"""
from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.test_skill_loop_gate import BANK, copy_db, sha256_file  # noqa: E402

E2E_PASSWORD = "e2e-local-pass"
PREFIX = "/practice/skill-loop"
SKILL = "sat.alg.linear_rate_remaining"


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _utc_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    def __init__(self, flag_on: bool, migrate: bool):
        self.tmp = tempfile.mkdtemp(prefix="sl-e2e-")
        self.db = os.path.join(self.tmp, "sat.db")
        copy_db(self.db)
        from werkzeug.security import generate_password_hash

        if migrate:
            from scripts.skill_loop_migrate import apply

            apply(self.db)
        conn = sqlite3.connect(self.db)
        pw = generate_password_hash(E2E_PASSWORD)
        conn.execute(
            "UPDATE users SET password_hash=?, password='' WHERE username IN ('s1','s2','teacher')",
            (pw,),
        )
        conn.commit()
        conn.close()
        if migrate:
            from skill_loop import publish_all_drafts

            conn = sqlite3.connect(self.db)
            conn.row_factory = sqlite3.Row
            publish_all_drafts(conn, 1)
            conn.commit()
            conn.close()
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        env = os.environ.copy()
        env["DB_PATH"] = self.db
        env["E2E_PORT"] = str(self.port)
        env["SKILL_LOOP_PILOT"] = "1" if flag_on else "0"
        env["SKILL_LOOP_ASSIGN_SALT"] = "e2e-local-only-salt"
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

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.tmp, ignore_errors=True)


SHOT_DIR = os.path.join(ROOT, "tests", "e2e", "screenshots")


def _login(page, base: str, username: str, remember: bool = False) -> None:
    page.goto(base + "/login")
    page.fill("#np-login-user", username)
    page.fill("#np-login-pass", E2E_PASSWORD)
    if remember:
        page.check("#np-login-remember")
    page.locator("form").locator("button[type=submit], input[type=submit]").first.click()
    page.wait_for_load_state("networkidle")


def _shot(page, name: str) -> None:
    os.makedirs(SHOT_DIR, exist_ok=True)
    page.screenshot(path=os.path.join(SHOT_DIR, name), full_page=True)


def _continue_feedback(page) -> None:
    page.wait_for_selector("[data-skill-loop-feedback]")
    page.locator("[data-sl-feedback-continue]").click()
    page.wait_for_load_state("networkidle")


def _no_horizontal_overflow(page, selector: str = ".sl-wrap") -> bool:
    return page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          if (!el) return false;
          const rect = el.getBoundingClientRect();
          return el.scrollWidth <= el.clientWidth + 4 && rect.right <= window.innerWidth + 4;
        }""",
        selector,
    )


@unittest.skipUnless(
    __import__("importlib").util.find_spec("playwright") is not None,
    "playwright not installed",
)
class SkillLoopBrowserE2E(unittest.TestCase):
    def test_flag_off_and_flag_on_desktop_mobile(self):
        from playwright.sync_api import sync_playwright

        bank_before = sha256_file(BANK)
        off = _Server(flag_on=False, migrate=False)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(off.base + "/login")
                self.assertEqual(page.locator("#np-login-pass").get_attribute("type"), "password")
                self.assertFalse(page.locator("#np-login-show-pass").is_checked())
                page.fill("#np-login-user", "s1")
                page.fill("#np-login-pass", E2E_PASSWORD)
                page.check("#np-login-remember")
                page.locator("form").locator("button[type=submit], input[type=submit]").first.click()
                page.wait_for_load_state("networkidle")
                stored = page.evaluate("() => window.localStorage.getItem('np-login-saved') || ''")
                session_blob = page.evaluate(
                    """() => {
                      const out = [];
                      for (let i = 0; i < sessionStorage.length; i++) {
                        const k = sessionStorage.key(i);
                        out.push(sessionStorage.getItem(k) || '');
                      }
                      return out.join(' ');
                    }"""
                )
                self.assertNotIn(E2E_PASSWORD, stored)
                self.assertNotIn(E2E_PASSWORD, session_blob)
                if stored:
                    self.assertNotIn("password", stored)
                page.goto(off.base + "/practice")
                html = page.content()
                self.assertNotIn("data-skill-loop-entry", html)
                self.assertNotIn("skill_loop.js", html)
                resp = page.goto(off.base + PREFIX)
                self.assertEqual(resp.status if resp else 0, 404)
                page.goto(off.base + "/practice/algebra/1_1/0")
                self.assertNotIn("skill-loop", page.url)
                page.goto(off.base + "/practice/analytics")
                self.assertIn("analytics", (page.url + page.content()).lower())
                browser.close()
            print("E2E flag-off desktop OK")
        finally:
            off.close()

        on = _Server(flag_on=True, migrate=True)
        try:
            for width, height, label, user_id, username in (
                (1280, 800, "desktop", 2, "s1"),
                (390, 844, "mobile", 3, "s2"),
            ):
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": width, "height": height})
                    _login(page, on.base, username)
                    page.goto(on.base + "/practice")
                    self.assertIn("data-skill-loop-entry", page.content())

                    on.sql(
                        """
                        INSERT INTO skill_loop_assignments (
                            experiment_id, user_id, skill_code, arm, assignment_source, assigned_at
                        ) VALUES ('skill_loop_v1_linear_rate_remaining', ?, ?, 'A', 'admin', ?)
                        ON CONFLICT(experiment_id, user_id) DO UPDATE SET
                            arm='A', assignment_source='admin'
                        """,
                        (user_id, SKILL, _utc_z(datetime.now(timezone.utc))),
                    )
                    on.sql("UPDATE skill_loop_runs SET arm='A' WHERE user_id=?", (user_id,))
                    page.goto(on.base + f"{PREFIX}/{SKILL}/precheck")
                    self.assertGreater(page.locator("[data-skill-loop-phase=precheck]").count(), 0)
                    resp = page.goto(on.base + f"{PREFIX}/{SKILL}/instruction")
                    self.assertIn(resp.status if resp else 0, (403, 404))

                    on.sql("UPDATE skill_loop_assignments SET arm='B' WHERE user_id=?", (user_id,))
                    on.sql(
                        "UPDATE skill_loop_runs SET arm='B', current_phase='precheck', current_variant=1 WHERE user_id=?",
                        (user_id,),
                    )
                    if label == "desktop":
                        page.goto(on.base + f"{PREFIX}/{SKILL}/precheck")
                        _shot(page, "phase_precheck.png")
                        page.click("#sl-hint-light")
                        page.wait_for_selector("[data-sl-hint-text]")
                        hint_text = page.locator("[data-sl-hint-text]").inner_text()
                        self.assertGreater(len(hint_text), 20)
                        page.click("#sl-solution")
                        page.wait_for_selector("[data-sl-solution-steps]")
                        self.assertGreater(page.locator("[data-sl-solution-steps] li").count(), 3)
                        self.assertIn("Why", page.locator("[data-sl-solution-panel]").inner_text())
                        self.assertGreater(page.locator("[data-sl-explanation-check]").count(), 0)
                        _shot(page, "phase_precheck_solution.png")
                        page.check("input[name=selected_answer][value=A]")
                        page.locator("#sl-form button[type=submit]").click()
                        page.wait_for_selector("[data-skill-loop-feedback]")
                        self.assertIn("Incorrect", page.locator("[data-sl-result]").inner_text())
                        self.assertGreater(page.locator("[data-sl-your-answer]").count(), 0)
                        self.assertGreater(page.locator("[data-sl-correct-answer]").count(), 0)
                        self.assertGreater(page.locator("[data-sl-core-idea]").count(), 0)
                        self.assertGreater(page.locator("[data-sl-feedback-steps] li").count(), 3)
                        _shot(page, "feedback_precheck_incorrect.png")
                        self.assertTrue(_no_horizontal_overflow(page))
                        _continue_feedback(page)

                        self.assertGreater(page.locator("[data-skill-loop-phase=instruction]").count(), 0)
                        _shot(page, "phase_instruction.png")
                        page.locator("#sl-form button[type=submit]").click()
                        page.wait_for_selector("[data-skill-loop-feedback]")
                        _shot(page, "feedback_instruction.png")
                        _continue_feedback(page)

                        self.assertGreater(page.locator("[data-skill-loop-phase=faded]").count(), 0)
                        _shot(page, "phase_faded.png")
                        page.fill("input[name=rate]", "1")
                        page.fill("input[name=total_hours]", "1")
                        page.locator("#sl-form button[type=submit]").click()
                        page.wait_for_selector("[data-skill-loop-feedback]")
                        self.assertIn("Incorrect", page.locator("[data-sl-result]").inner_text())
                        self.assertIn("instruction", page.locator("[data-sl-feedback-continue]").get_attribute("href") or "")
                        _shot(page, "feedback_faded_incorrect.png")
                        run = on.sql("SELECT current_phase FROM skill_loop_runs WHERE user_id=?", (user_id,))[0]
                        self.assertEqual(run["current_phase"], "faded")
                        _continue_feedback(page)
                        self.assertGreater(page.locator("[data-sl-remediation]").count(), 0)
                        _shot(page, "phase_instruction_remediation.png")
                        page.click("[data-sl-continue-faded]")
                        page.wait_for_load_state("networkidle")
                        self.assertIn("salt brine", page.content())
                        page.fill("input[name=removed_amount]", "720")
                        page.fill("input[name=start_amount]", "2880")
                        page.locator("#sl-form button[type=submit]").click()
                        page.wait_for_selector("[data-skill-loop-feedback]")
                        _continue_feedback(page)

                        self.assertGreater(page.locator("[data-skill-loop-phase=independent]").count(), 0)
                        _shot(page, "phase_independent.png")
                        page.check("input[name=selected_answer][value=A]")
                        page.locator("#sl-form button[type=submit]").click()
                        page.wait_for_selector("[data-skill-loop-feedback]")
                        self.assertIn("Incorrect", page.locator("[data-sl-result]").inner_text())
                        flags = on.sql(
                            """
                            SELECT s.counts_as_independent, s.is_correct, r.mastery_status
                            FROM skill_loop_step_results s
                            JOIN skill_loop_runs r ON r.id = s.run_id
                            WHERE r.user_id=? AND s.phase='independent'
                            """,
                            (user_id,),
                        )
                        self.assertTrue(flags)
                        self.assertEqual(int(flags[0]["is_correct"]), 0)
                        self.assertEqual(int(flags[0]["counts_as_independent"]), 0)
                        self.assertNotEqual(flags[0]["mastery_status"], "immediate_pass")
                        _shot(page, "feedback_independent_incorrect.png")
                        _continue_feedback(page)
                        page.check("input[name=selected_answer][value=B]")
                        page.locator("#sl-form button[type=submit]").click()
                        page.wait_for_selector("[data-skill-loop-feedback]")
                        _continue_feedback(page)
                        if page.locator("[data-skill-loop-phase=independent]").count():
                            if page.locator("input[name=selected_answer][value=C]").count():
                                page.check("input[name=selected_answer][value=C]")
                                page.locator("#sl-form button[type=submit]").click()
                                page.wait_for_selector("[data-skill-loop-feedback]")
                                _continue_feedback(page)
                        if page.locator("[data-skill-loop-phase=transfer]").count():
                            _shot(page, "phase_transfer.png")
                            page.check("input[name=selected_answer][value=A]")
                            page.locator("#sl-form button[type=submit]").click()
                            page.wait_for_selector("[data-skill-loop-feedback]")
                            self.assertIn("Incorrect", page.locator("[data-sl-result]").inner_text())
                            self.assertGreater(page.locator("[data-sl-unknown-change]").count(), 0)
                            _shot(page, "feedback_transfer_incorrect.png")
                            tr_flags = on.sql(
                                """
                                SELECT s.counts_as_independent, r.mastery_status
                                FROM skill_loop_step_results s
                                JOIN skill_loop_runs r ON r.id = s.run_id
                                WHERE r.user_id=? AND s.phase='transfer'
                                """,
                                (user_id,),
                            )
                            self.assertTrue(tr_flags)
                            self.assertEqual(int(tr_flags[0]["counts_as_independent"]), 0)
                            self.assertNotEqual(tr_flags[0]["mastery_status"], "delayed_pass")
                            _continue_feedback(page)
                            if page.locator("[data-skill-loop-phase=transfer]").count():
                                page.check("input[name=selected_answer][value=B]")
                                page.locator("#sl-form button[type=submit]").click()
                                page.wait_for_selector("[data-skill-loop-feedback]")
                                _continue_feedback(page)
                    else:
                        page.goto(on.base + f"{PREFIX}/{SKILL}/precheck")
                        page.check("input[name=selected_answer][value=C]")
                        page.locator("#sl-form button[type=submit]").click()
                        page.wait_for_selector("[data-skill-loop-feedback]")
                        self.assertTrue(_no_horizontal_overflow(page))
                        _shot(page, "mobile_feedback.png")
                        _continue_feedback(page)
                        page.locator("#sl-form button[type=submit]").click()
                        page.wait_for_selector("[data-skill-loop-feedback]")
                        _continue_feedback(page)
                        page.click("#sl-hint-critical")
                        page.wait_for_selector("[data-sl-hint-text][data-level=critical]")
                        self.assertGreater(len(page.locator("[data-sl-hint-text]").inner_text()), 20)
                        page.click("#sl-solution")
                        page.wait_for_selector("[data-sl-solution-panel]")
                        self.assertTrue(_no_horizontal_overflow(page))
                        _shot(page, "mobile_solution.png")
                        page.fill("input[name=rate]", "250")
                        page.fill("input[name=total_hours]", "14")
                        page.locator("#sl-form button[type=submit]").click()
                        page.wait_for_selector("[data-skill-loop-feedback]")
                        self.assertTrue(_no_horizontal_overflow(page))
                        _continue_feedback(page)
                        self.assertGreater(page.locator("[data-skill-loop-phase=independent]").count(), 0)
                        page.check("input[name=selected_answer][value=C]")
                        page.locator("#sl-form button[type=submit]").click()
                        page.wait_for_selector("[data-skill-loop-feedback]")
                        _continue_feedback(page)
                        page.check("input[name=selected_answer][value=B]")
                        page.locator("#sl-form button[type=submit]").click()
                        page.wait_for_selector("[data-skill-loop-feedback]")
                        _continue_feedback(page)
                        self.assertGreater(page.locator("[data-skill-loop-phase=transfer]").count(), 0)
                        page.check("input[name=selected_answer][value=C]")
                        page.locator("#sl-form button[type=submit]").click()
                        page.wait_for_selector("[data-skill-loop-feedback]")
                        _continue_feedback(page)
                        page.check("input[name=selected_answer][value=B]")
                        page.locator("#sl-form button[type=submit]").click()
                        page.wait_for_selector("[data-skill-loop-feedback]")
                        _continue_feedback(page)

                    now = datetime.now(timezone.utc)
                    on.sql(
                        """
                        UPDATE skill_loop_runs
                        SET instruction_completed_at=?, current_phase='delayed', current_variant=1
                        WHERE user_id=?
                        """,
                        (_utc_z(now - timedelta(hours=48)), user_id),
                    )
                    page.goto(on.base + f"{PREFIX}/{SKILL}/delayed")
                    self.assertGreater(page.locator("[data-skill-loop-phase=delayed]").count(), 0)
                    _shot(page, f"phase_delayed_{label}.png")
                    page.check("input[name=selected_answer][value=D]")
                    page.locator("#sl-form button[type=submit]").click()
                    page.wait_for_selector("[data-skill-loop-feedback]")
                    mid = on.sql("SELECT mastery_status FROM skill_loop_runs WHERE user_id=?", (user_id,))[0]
                    self.assertNotEqual(mid["mastery_status"], "delayed_pass")
                    _continue_feedback(page)
                    if page.locator("[data-skill-loop-phase=delayed]").count() == 0:
                        page.goto(on.base + f"{PREFIX}/{SKILL}/delayed")
                    page.check("input[name=selected_answer][value=B]")
                    page.locator("#sl-form button[type=submit]").click()
                    page.wait_for_selector("[data-skill-loop-feedback]")
                    passed = on.sql("SELECT mastery_status FROM skill_loop_runs WHERE user_id=?", (user_id,))[0]
                    self.assertEqual(passed["mastery_status"], "delayed_pass")

                    resp = page.goto(on.base + f"{PREFIX}/admin/review")
                    self.assertIn(resp.status if resp else 0, (403, 302))

                    page.goto(on.base + "/practice/algebra/1_1/0")
                    self.assertNotIn("skill-loop", page.url)
                    page.goto(on.base + "/practice/analytics")
                    self.assertIn("analytics", (page.url + page.content()).lower())

                    page.goto(on.base + "/logout")
                    _login(page, on.base, "teacher")
                    page.goto(on.base + f"{PREFIX}/admin/review")
                    self.assertIn("Teacher review", page.content())
                    page.evaluate(
                        """async (uid) => {
                          const token = document.querySelector('meta[name="csrf-token"]').content;
                          await fetch('/practice/skill-loop/admin/assign', {
                            method: 'POST',
                            headers: {
                              'Content-Type': 'application/json',
                              'X-CSRF-Token': token,
                              'X-Requested-With': 'XMLHttpRequest'
                            },
                            body: JSON.stringify({user_id: uid, arm: 'A', reason: 'e2e override'})
                          });
                        }""",
                        user_id,
                    )
                    row = on.sql(
                        "SELECT arm, assignment_source FROM skill_loop_assignments WHERE user_id=?",
                        (user_id,),
                    )[0]
                    self.assertEqual(row["arm"], "A")
                    self.assertEqual(row["assignment_source"], "admin")
                    if page.locator("button:has-text('Publish')").count():
                        page.locator("button:has-text('Publish')").first.click()
                        page.wait_for_load_state("networkidle")
                    page.goto(on.base + f"{PREFIX}/admin/report")
                    html = page.content()
                    self.assertIn("Pilot only — usability and data-integrity evaluation", html)
                    self.assertIn("不构成教学有效性或提分证明", html)
                    self.assertIn("cannot be fully verified", html)
                    browser.close()
                print(f"E2E flag-on {label} {width}x{height} OK")
        finally:
            on.close()
        self.assertEqual(sha256_file(BANK), bank_before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
