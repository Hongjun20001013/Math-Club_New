"""Playwright E2E for public Placement (flag on/off). Local copy DB only."""
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

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.test_placement_public_access import BANK, copy_db, sha256_file  # noqa: E402

E2E_PASSWORD = "e2e-local-pass"
SHOT_DIR = os.path.join(ROOT, "tests", "e2e", "screenshots")


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _wait_http(url: str, seconds: float = 25) -> None:
    import urllib.request

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
    def __init__(self, flag_on: bool):
        self.tmp = tempfile.mkdtemp(prefix="pl-e2e-")
        self.db = os.path.join(self.tmp, "sat.db")
        copy_db(self.db)
        from werkzeug.security import generate_password_hash

        conn = sqlite3.connect(self.db)
        pw = generate_password_hash(E2E_PASSWORD)
        conn.execute(
            "UPDATE users SET password_hash=?, password='' WHERE username IN ('s1','s2','teacher')",
            (pw,),
        )
        conn.commit()
        conn.close()
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        env = os.environ.copy()
        env["DB_PATH"] = self.db
        env["E2E_PORT"] = str(self.port)
        env["SECRET_KEY"] = "e2e-placement-public"
        env["PLACEMENT_PUBLIC_ACCESS"] = "1" if flag_on else "0"
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

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.tmp, ignore_errors=True)


def _shot(page, name: str) -> str:
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, name)
    page.screenshot(path=path, full_page=True)
    return path


def _open_upper_q27(page) -> None:
    """Q27 is index 26; Gate 2 intro intercepts until its session flag is set."""
    run_root = page.url.rsplit("/item/", 1)[0]
    if "/placement/run/" not in run_root:
        run_root = page.url.rsplit("/ready", 1)[0]
    target = run_root + "/item/26"
    page.goto(target, wait_until="networkidle")
    for _ in range(8):
        if page.locator(".stem-figure-wrap--placement-chords").count():
            return
        if page.locator("form.np-pl-part__dock-form button[type=submit]").count():
            page.click("form.np-pl-part__dock-form button[type=submit]")
            page.wait_for_load_state("networkidle")
            page.goto(target, wait_until="networkidle")
            continue
        break


@unittest.skipUnless(
    __import__("importlib").util.find_spec("playwright") is not None,
    "playwright not installed",
)
class PlacementPublicBrowserE2E(unittest.TestCase):
    def test_flag_off_and_flag_on_desktop_mobile(self):
        from playwright.sync_api import sync_playwright

        bank_sha = sha256_file(BANK)
        off = _Server(False)
        try:
            _wait_http(off.base + "/health")
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(off.base + "/login", wait_until="networkidle")
                self.assertGreaterEqual(page.locator("#np-login-placement-start").count(), 1)
                page.goto(off.base + "/placement", wait_until="networkidle")
                self.assertIn("/login", page.url)
                browser.close()
        finally:
            off.close()

        on = _Server(True)
        try:
            _wait_http(on.base + "/health")
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(on.base + "/practice", wait_until="networkidle")
                self.assertIn("/login", page.url)
                page.goto(on.base + "/login", wait_until="networkidle")
                self.assertIn("/login", page.url)
                page.click("#np-login-placement-start")
                page.wait_for_url("**/placement")
                page.goto(on.base + "/placement/enhanced-math-1/start", wait_until="networkidle")
                page.fill("#pl-name", "E2E Student")
                page.select_option("#pl-grade", "8th")
                page.fill("#pl-course", "Algebra I Honors")
                page.locator('label.np-pl-choice', has_text="Mia Hu").click()
                page.check("input[name=counselor_confirm]")
                page.click("button[type=submit]")
                page.wait_for_url("**/placement/run/**/ready")
                self.assertTrue(page.locator("[data-pl-recovery-code]").count() >= 1)
                code = page.locator("[data-pl-recovery-code]").inner_text().strip()
                page.click("[data-pl-begin-exam]")
                page.wait_for_selector("#practice-answer-form")
                _shot(page, "placement_public_desktop.png")
                page.goto(on.base + "/placement/upper-algebra-precalc/start", wait_until="networkidle")
                page.fill("#pl-name", "Q27 Student")
                page.select_option("#pl-grade", "10th")
                page.fill("#pl-course", "Algebra II")
                page.locator('label.np-pl-choice', has_text="Mia Hu").click()
                page.check("input[name=counselor_confirm]")
                page.click("button[type=submit]")
                page.wait_for_url("**/placement/run/**/ready")
                page.click("[data-pl-begin-exam]")
                page.wait_for_selector("#practice-answer-form")
                _open_upper_q27(page)
                page.wait_for_selector(".stem-figure-wrap--placement-chords")
                page.wait_for_function(
                    "() => document.querySelector('#chord-ac') && document.querySelector('#chord-be')"
                )
                self.assertTrue(page.locator("#chord-ac").count() >= 1)
                self.assertTrue(page.locator("#chord-be").count() >= 1)
                wrap = page.locator(".stem-figure-wrap--placement-chords").bounding_box()
                self.assertIsNotNone(wrap)
                self.assertGreater(wrap["width"], 80)
                self.assertGreater(wrap["height"], 80)
                ac_box = page.locator("#chord-ac").bounding_box()
                be_box = page.locator("#chord-be").bounding_box()
                self.assertIsNotNone(ac_box)
                self.assertIsNotNone(be_box)
                self.assertGreater(ac_box["width"], 20)
                self.assertGreater(be_box["height"], 20)
                _shot(page, "placement_q27_desktop.png")
                page.context.clear_cookies()
                page.goto(on.base + "/placement/recover", wait_until="networkidle")
                page.fill("#pl-recovery", code)
                page.click("button[type=submit]")
                page.wait_for_selector("#practice-answer-form")

                mobile = browser.new_page(viewport={"width": 390, "height": 844})
                mobile.goto(on.base + "/placement/enhanced-math-2/start", wait_until="networkidle")
                mobile.fill("#pl-name", "Mobile Student")
                mobile.select_option("#pl-grade", "9th")
                mobile.fill("#pl-course", "Geometry")
                mobile.locator('label.np-pl-choice', has_text="Jimmy Zheng").click()
                mobile.check("input[name=counselor_confirm]")
                mobile.click("button[type=submit]")
                mobile.wait_for_url("**/placement/run/**/ready")
                mobile.click("[data-pl-begin-exam]")
                mobile.wait_for_selector("#practice-answer-form")
                _shot(mobile, "placement_public_mobile.png")
                mobile.goto(on.base + "/placement/upper-algebra-precalc/start", wait_until="networkidle")
                mobile.fill("#pl-name", "Q27 Mobile")
                mobile.select_option("#pl-grade", "11th")
                mobile.fill("#pl-course", "Precalculus")
                mobile.locator('label.np-pl-choice', has_text="Jimmy Zheng").click()
                mobile.check("input[name=counselor_confirm]")
                mobile.click("button[type=submit]")
                mobile.wait_for_url("**/placement/run/**/ready")
                mobile.click("[data-pl-begin-exam]")
                mobile.wait_for_selector("#practice-answer-form")
                _open_upper_q27(mobile)
                mobile.wait_for_selector(".stem-figure-wrap--placement-chords")
                mobile.wait_for_function(
                    "() => document.querySelector('#chord-ac') && document.querySelector('#chord-be')"
                )
                wrap_m = mobile.locator(".stem-figure-wrap--placement-chords").bounding_box()
                self.assertIsNotNone(wrap_m)
                self.assertGreater(wrap_m["width"], 80)
                self.assertGreater(mobile.locator("#chord-be").bounding_box()["height"], 20)
                overflow = mobile.evaluate(
                    """() => {
                      const el = document.querySelector('.stem-figure-wrap--placement-chords');
                      if (!el) return true;
                      return el.scrollWidth > el.clientWidth + 1;
                    }"""
                )
                self.assertFalse(overflow)
                _shot(mobile, "placement_q27_mobile.png")
                browser.close()
        finally:
            on.close()
        self.assertEqual(sha256_file(BANK), bank_sha)


if __name__ == "__main__":
    unittest.main()
