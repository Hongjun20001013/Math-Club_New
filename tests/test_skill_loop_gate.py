"""Required gate tests for the skill-loop pilot vertical slice.

Run from repo root:
  python3 -m unittest tests.test_skill_loop_gate -v

Does not connect to production, does not migrate sat.db in place,
and does not modify data/question_bank.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

BANK = os.path.join(ROOT, "data", "question_bank.json")
LIVE_DB = os.path.join(ROOT, "sat.db")
SKILL = "sat.alg.linear_rate_remaining"
PREFIX = "/practice/skill-loop"
PILOT_PATHS = (
    PREFIX,
    PREFIX + "/",
    f"{PREFIX}/{SKILL}",
    f"{PREFIX}/{SKILL}/precheck",
    f"{PREFIX}/{SKILL}/instruction",
    f"{PREFIX}/{SKILL}/faded",
    f"{PREFIX}/{SKILL}/independent",
    f"{PREFIX}/{SKILL}/transfer",
    f"{PREFIX}/{SKILL}/feedback",
    f"{PREFIX}/{SKILL}/control",
    f"{PREFIX}/admin/review",
    f"{PREFIX}/admin/report",
)
BASELINE_MIN = {
    "users": 16,
    "course_materials_count": 48,
    "question_bank_count": 1507,
    "practice_attempts": 17,
    "practice_responses": 61,
    "mistake_learning_progress": 27,
}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_db(dest: str) -> None:
    src = sqlite3.connect(LIVE_DB)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def open_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


class TestBaselineProtection(unittest.TestCase):
    def test_live_local_baseline_and_bank_hash(self):
        from scripts.skill_loop_baseline import baseline

        before = baseline(LIVE_DB)
        self.assertGreaterEqual(before["users"], BASELINE_MIN["users"])
        self.assertGreaterEqual(before["course_materials_count"], BASELINE_MIN["course_materials_count"])
        self.assertEqual(before["question_bank_count"], BASELINE_MIN["question_bank_count"])
        self.assertGreaterEqual(before["practice_attempts"], BASELINE_MIN["practice_attempts"])
        self.assertGreaterEqual(before["practice_responses"], BASELINE_MIN["practice_responses"])
        self.assertGreaterEqual(before["mistake_learning_progress"], BASELINE_MIN["mistake_learning_progress"])
        digest = sha256_file(BANK)
        self.assertEqual(before["question_bank_sha256"], digest)
        self.assertEqual(len(digest), 64)
        TestBaselineProtection.bank_sha256 = digest
        TestBaselineProtection.baseline_before = before
        print("\nBASELINE BEFORE")
        for k, v in before.items():
            print(f"  {k}={v}")
        print(f"  question_bank.json SHA-256={digest}")


class TestMigrationSafety(unittest.TestCase):
    def test_sql_is_additive_only(self):
        from scripts import skill_loop_migrate as migrate

        blob = "\n".join(migrate.SQL_STATEMENTS)
        for word in ("DROP", "TRUNCATE", "DELETE", "ALTER", "INSERT", "UPDATE"):
            self.assertNotRegex(blob, rf"\b{word}\b")
        self.assertEqual(len(migrate.SQL_STATEMENTS), 15)
        self.assertEqual(len(migrate.SCHEMA_TABLES), 7)
        self.assertEqual(len(migrate.SCHEMA_INDEXES), 8)
        migrate.assert_sql_is_additive()

    def test_dry_run_prints_sql_and_does_not_connect(self):
        from scripts import skill_loop_migrate as migrate

        with mock.patch.object(migrate.sqlite3, "connect") as connect:
            argv = ["skill_loop_migrate.py", "--dry-run"]
            with mock.patch.object(sys, "argv", argv):
                code = migrate.main()
            self.assertEqual(code, 0)
            connect.assert_not_called()

    def test_dry_run_subprocess_no_db_write(self):
        tmp = tempfile.mkdtemp(prefix="sl-dry-")
        fake = os.path.join(tmp, "should-not-be-created.db")
        try:
            proc = subprocess.run(
                [sys.executable, os.path.join(ROOT, "scripts", "skill_loop_migrate.py"), "--dry-run", "--db", fake],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("DRY-RUN", proc.stdout)
            self.assertIn("CREATE TABLE", proc.stdout)
            self.assertFalse(os.path.exists(fake))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_apply_requires_explicit_local_db(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "skill_loop_migrate.py"), "--apply"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--db", proc.stderr)

    def test_refuses_var_data_path(self):
        from scripts.skill_loop_migrate import is_forbidden_path, apply

        self.assertTrue(is_forbidden_path("/var/data/sat.db"))
        with self.assertRaises(SystemExit):
            apply("/var/data/sat.db")
        proc = subprocess.run(
            [
                sys.executable,
                os.path.join(ROOT, "scripts", "skill_loop_migrate.py"),
                "--apply",
                "--db",
                "/var/data/sat.db",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 3)

    def test_apply_is_transactional_on_failure(self):
        from scripts import skill_loop_migrate as migrate

        tmp = tempfile.mkdtemp(prefix="sl-fail-")
        db = os.path.join(tmp, "copy.db")
        copy_db(db)
        try:
            with mock.patch.object(migrate, "seed_pack", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    migrate.apply(db)
            conn = open_db(db)
            names = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'skill_loop_%'"
                )
            }
            conn.close()
            self.assertEqual(names, set())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_second_run_idempotent_does_not_break_assignments(self):
        from scripts.skill_loop_migrate import apply

        tmp = tempfile.mkdtemp(prefix="sl-idemp-")
        db = os.path.join(tmp, "copy.db")
        copy_db(db)
        try:
            apply(db)
            conn = open_db(db)
            conn.execute(
                """
                INSERT INTO skill_loop_assignments (
                    experiment_id, user_id, skill_code, arm, assignment_source, assigned_at
                ) VALUES ('skill_loop_v1_linear_rate_remaining', 2, ?, 'B', 'hash', '2026-01-01T00:00:00Z')
                """,
                (SKILL,),
            )
            conn.commit()
            n1 = conn.execute("SELECT COUNT(*) FROM skill_loop_items").fetchone()[0]
            conn.close()
            apply(db)
            apply(db)
            conn = open_db(db)
            n2 = conn.execute("SELECT COUNT(*) FROM skill_loop_items").fetchone()[0]
            asg = conn.execute(
                "SELECT arm, assignment_source FROM skill_loop_assignments WHERE user_id = 2"
            ).fetchone()
            tables = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'skill_loop_%'"
            ).fetchone()[0]
            conn.close()
            self.assertEqual(n1, n2)
            self.assertEqual(n1, 12)
            self.assertEqual(asg["arm"], "B")
            self.assertEqual(tables, 7)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_rollback_prints_plan_without_confirm(self):
        from scripts import skill_loop_rollback as rb

        with mock.patch.object(sqlite3, "connect") as connect:
            with mock.patch.object(sys, "argv", ["skill_loop_rollback.py"]):
                code = rb.main()
            self.assertEqual(code, 0)
            connect.assert_not_called()
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "skill_loop_rollback.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("DRY plan only", proc.stdout)
        self.assertIn("DROP TABLE IF EXISTS skill_loop_items", proc.stdout)
        self.assertNotIn("users", proc.stdout.split("DROP TABLE")[-1] if False else "ok")
        for old in ("practice_attempts", "users", "mistake_learning_progress"):
            self.assertNotIn(f"DROP TABLE IF EXISTS {old}", proc.stdout)

    def test_rollback_only_new_objects_and_requires_confirm(self):
        from scripts.skill_loop_migrate import apply
        from scripts.skill_loop_rollback import NEW_TABLES, plan_sql

        sql = "\n".join(plan_sql())
        for name in NEW_TABLES:
            self.assertIn(name, sql)
        self.assertNotIn("practice_attempts", sql)
        tmp = tempfile.mkdtemp(prefix="sl-rb-")
        db = os.path.join(tmp, "copy.db")
        copy_db(db)
        try:
            apply(db)
            proc = subprocess.run(
                [
                    sys.executable,
                    os.path.join(ROOT, "scripts", "skill_loop_rollback.py"),
                    "--confirm-rollback",
                    "--db",
                    db,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0)
            conn = open_db(db)
            names = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'skill_loop_%'"
                )
            }
            users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            conn.close()
            self.assertEqual(names, set())
            self.assertGreaterEqual(users, 16)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_baseline_unchanged_across_local_copy_migration(self):
        from scripts.skill_loop_baseline import baseline
        from scripts.skill_loop_migrate import apply

        tmp = tempfile.mkdtemp(prefix="sl-base-")
        db = os.path.join(tmp, "copy.db")
        copy_db(db)
        try:
            before = baseline(db)
            bank_before = sha256_file(BANK)
            apply(db)
            after = baseline(db)
            bank_after = sha256_file(BANK)
            self.assertEqual(before, after)
            self.assertEqual(bank_before, bank_after)
            print("\nBASELINE AFTER LOCAL COPY MIGRATION")
            for k, v in after.items():
                print(f"  {k}={v}")
            print(f"  question_bank.json SHA-256 before={bank_before}")
            print(f"  question_bank.json SHA-256 after ={bank_after}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestSchemaOnlyMigration(unittest.TestCase):
    def _schema_state(self, db):
        conn = open_db(db)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'skill_loop_%'"
            )
        }
        indexes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_skill_loop_%'"
            )
        }
        counts = {}
        for name in sorted(tables):
            counts[name] = int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
        conn.close()
        return tables, indexes, counts

    def test_schema_only_creates_empty_objects_without_seed(self):
        from scripts import skill_loop_migrate as migrate
        from scripts.skill_loop_baseline import baseline

        tmp = tempfile.mkdtemp(prefix="sl-schema-")
        db = os.path.join(tmp, "copy.db")
        copy_db(db)
        try:
            before = baseline(db)
            with mock.patch.object(migrate, "seed_pack", wraps=migrate.seed_pack) as seed:
                migrate.apply_schema(db)
                seed.assert_not_called()
            tables, indexes, counts = self._schema_state(db)
            self.assertEqual(tables, set(migrate.SCHEMA_TABLES))
            self.assertEqual(indexes, set(migrate.SCHEMA_INDEXES))
            self.assertTrue(counts)
            self.assertTrue(all(n == 0 for n in counts.values()), counts)
            after = baseline(db)
            self.assertEqual(before, after)
            proc = subprocess.run(
                [
                    sys.executable,
                    os.path.join(ROOT, "scripts", "skill_loop_migrate.py"),
                    "--schema-only",
                    "--db",
                    db,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("SCHEMA_ONLY", proc.stdout)
            self.assertIn("statements=15", proc.stdout)
            self.assertIn(os.path.abspath(db), proc.stdout)
            self.assertNotIn("INSERT", proc.stdout)
            tables2, indexes2, counts2 = self._schema_state(db)
            self.assertEqual(tables, tables2)
            self.assertEqual(indexes, indexes2)
            self.assertEqual(counts, counts2)
            self.assertEqual(baseline(db), before)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_schema_only_transaction_rollback_on_mid_failure(self):
        from scripts import skill_loop_migrate as migrate
        from scripts.skill_loop_baseline import baseline

        tmp = tempfile.mkdtemp(prefix="sl-schema-fail-")
        db = os.path.join(tmp, "copy.db")
        copy_db(db)
        try:
            before = baseline(db)
            broken = list(migrate.SQL_STATEMENTS)
            broken.insert(4, "THIS IS NOT VALID SQL")
            with mock.patch.object(migrate, "SQL_STATEMENTS", broken):
                with self.assertRaises(sqlite3.OperationalError):
                    migrate.apply_schema(db)
            tables, indexes, _counts = self._schema_state(db)
            self.assertEqual(tables, set())
            self.assertEqual(indexes, set())
            self.assertEqual(baseline(db), before)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_apply_still_refuses_var_data_and_allow_flag_is_schema_only(self):
        from scripts.skill_loop_migrate import apply, apply_schema, is_forbidden_path

        self.assertTrue(is_forbidden_path("/var/data/sat.db"))
        with self.assertRaises(SystemExit):
            apply("/var/data/sat.db")
        with self.assertRaises(SystemExit):
            apply_schema("/var/data/sat.db")
        apply_proc = subprocess.run(
            [
                sys.executable,
                os.path.join(ROOT, "scripts", "skill_loop_migrate.py"),
                "--apply",
                "--db",
                "/var/data/sat.db",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(apply_proc.returncode, 3)
        mixed = subprocess.run(
            [
                sys.executable,
                os.path.join(ROOT, "scripts", "skill_loop_migrate.py"),
                "--apply",
                "--allow-render-production",
                "--db",
                "/var/data/sat.db",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(mixed.returncode, 4)
        blocked = subprocess.run(
            [
                sys.executable,
                os.path.join(ROOT, "scripts", "skill_loop_migrate.py"),
                "--schema-only",
                "--db",
                "/var/data/sat.db",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(blocked.returncode, 0)
        from scripts import skill_loop_migrate as migrate

        with mock.patch.object(migrate, "apply_schema") as schema:
            argv = [
                "skill_loop_migrate.py",
                "--schema-only",
                "--allow-render-production",
                "--db",
                "/var/data/sat.db",
            ]
            with mock.patch.object(sys, "argv", argv):
                code = migrate.main()
            self.assertEqual(code, 0)
            schema.assert_called_once_with("/var/data/sat.db", allow_render_production=True)


class _PilotCase(unittest.TestCase):
    flag_on = True
    publish = True

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sl-app-")
        self.db = os.path.join(self.tmp, "sat.db")
        copy_db(self.db)
        import app as app_mod
        from scripts.skill_loop_migrate import apply
        import skill_loop

        self.app_mod = app_mod
        self.sl = skill_loop
        self._orig_db = app_mod.DB_PATH
        self._orig_ready = app_mod._DB_SCHEMA_READY
        app_mod.DB_PATH = self.db
        app_mod._DB_SCHEMA_READY = False
        app_mod.app.config["TESTING"] = True
        app_mod.app.config["SKILL_LOOP_PILOT"] = self.flag_on
        os.environ.pop("SKILL_LOOP_PILOT", None)
        apply(self.db)
        self.app_mod.app.config.pop("SKILL_LOOP_CLOCK", None)
        if self.publish:
            with app_mod.app.app_context():
                db = app_mod.get_db()
                skill_loop.publish_all_drafts(db, 1)
                db.commit()
        self.client = app_mod.app.test_client()
        self.bank_hash = sha256_file(BANK)

    def tearDown(self):
        self.app_mod.app.config.pop("SKILL_LOOP_CLOCK", None)
        self.app_mod.DB_PATH = self._orig_db
        self.app_mod._DB_SCHEMA_READY = self._orig_ready
        self.app_mod.app.config["SKILL_LOOP_PILOT"] = False
        os.environ.pop("SKILL_LOOP_PILOT", None)
        os.environ.pop("SKILL_LOOP_ASSIGN_SALT", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _set_clock(self, factory):
        if factory is None:
            self.app_mod.app.config.pop("SKILL_LOOP_CLOCK", None)
        else:
            self.app_mod.app.config["TESTING"] = True
            self.app_mod.app.config["SKILL_LOOP_CLOCK"] = factory

    def login(self, user_id=2, role="student", username="s1"):
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_role"] = role
            sess["username"] = username
            sess["csrf_token"] = "test-csrf"

    def headers(self):
        return {
            "X-CSRF-Token": "test-csrf",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json",
        }

    def qdb(self):
        return open_db(self.db)

    def force_arm(self, user_id: int, arm: str, operator_id: int = 1):
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            self.sl.admin_override_arm(db, user_id, SKILL, arm, operator_id, "qa override")
            db.commit()

    def post_submit(self, **payload):
        return self.client.post(
            f"{PREFIX}/{SKILL}/submit",
            data=json.dumps(payload),
            headers=self.headers(),
        )

    def start_b(self, user_id=2):
        self.login(user_id=user_id)
        self.force_arm(user_id, "B")
        rv = self.client.get(f"{PREFIX}/{SKILL}/precheck")
        self.assertEqual(rv.status_code, 200, rv.data[:300])
        return rv


class TestFeatureFlagIsolation(_PilotCase):
    flag_on = False
    publish = True

    def test_all_pilot_routes_404_when_flag_off(self):
        self.login()
        for path in PILOT_PATHS:
            rv = self.client.get(path)
            self.assertEqual(rv.status_code, 404, path)
        rv = self.client.get("/practice")
        self.assertEqual(rv.status_code, 200)
        html = rv.get_data(as_text=True)
        self.assertNotIn("data-skill-loop-entry", html)
        self.assertNotIn("skill_loop.js", html)
        self.assertNotIn("/practice/skill-loop", html)

    def test_flag_off_does_not_write_pilot_rows_or_create_assignment(self):
        self.login()
        self.client.get("/practice")
        self.client.get(f"{PREFIX}/{SKILL}/precheck")
        self.post_submit(phase="precheck", item_id="slq_lrr_precheck_01", selected_answer="C")
        conn = self.qdb()
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM skill_loop_assignments").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM skill_loop_runs").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM skill_loop_events").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM skill_loop_step_results").fetchone()[0], 0)
        finally:
            conn.close()

    def test_old_practice_unchanged_with_flag_off(self):
        self.login()
        rv = self.client.get("/practice/algebra/1_1/0")
        self.assertIn(rv.status_code, (200, 302))
        conn = self.qdb()
        try:
            attempts = conn.execute("SELECT COUNT(*) FROM practice_attempts").fetchone()[0]
            mistakes = conn.execute("SELECT COUNT(*) FROM mistake_learning_progress").fetchone()[0]
        finally:
            conn.close()
        self.assertGreaterEqual(attempts, 17)
        self.assertGreaterEqual(mistakes, 27)


class TestPublishAndStudentVisibility(_PilotCase):
    publish = False

    def test_draft_rejected_archived_hidden_and_unscored(self):
        self.login()
        self.force_arm(2, "B")
        rv = self.client.get(f"{PREFIX}/{SKILL}/precheck")
        self.assertEqual(rv.status_code, 404)
        self.post_submit(phase="precheck", item_id="slq_lrr_precheck_01", selected_answer="C")
        # run does not exist yet; creating via hub still cannot score drafts
        self.client.get(PREFIX + "/")
        rv = self.post_submit(phase="precheck", item_id="slq_lrr_precheck_01", selected_answer="C")
        self.assertIn(rv.status_code, (403, 404))
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            self.sl.publish_item(db, "slq_lrr_precheck_01", 1, 1)
            db.execute(
                "UPDATE skill_loop_items SET review_status='rejected', publish_status='unpublished' WHERE id='slq_lrr_ind_01'"
            )
            db.execute(
                "UPDATE skill_loop_items SET review_status='reviewed', publish_status='archived' WHERE id='slq_lrr_ind_02'"
            )
            db.commit()
        rv = self.client.get(f"{PREFIX}/{SKILL}/precheck")
        self.assertEqual(rv.status_code, 200)
        html = rv.get_data(as_text=True)
        self.assertNotIn("correct_answer", html)
        self.assertNotIn("data-correct", html)
        rv = self.post_submit(phase="independent", item_id="slq_lrr_ind_01", selected_answer="C")
        self.assertEqual(rv.status_code, 403)
        rv = self.post_submit(phase="independent", item_id="slq_lrr_ind_02", selected_answer="B")
        self.assertEqual(rv.status_code, 403)

    def test_publish_stores_reviewer_time_version_and_does_not_touch_bank(self):
        self.login(user_id=1, role="admin", username="teacher")
        rv = self.client.post(
            f"{PREFIX}/admin/publish",
            data=json.dumps({"item_id": "slq_lrr_precheck_01", "version": 1}),
            headers=self.headers(),
        )
        self.assertEqual(rv.status_code, 200)
        conn = self.qdb()
        try:
            row = conn.execute(
                "SELECT review_status, publish_status, reviewed_by, reviewed_at, version FROM skill_loop_items WHERE id=?",
                ("slq_lrr_precheck_01",),
            ).fetchone()
            review = conn.execute(
                "SELECT reviewer_user_id, decision FROM skill_loop_item_reviews WHERE item_id=?",
                ("slq_lrr_precheck_01",),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["review_status"], "reviewed")
        self.assertEqual(row["publish_status"], "published")
        self.assertEqual(int(row["reviewed_by"]), 1)
        self.assertTrue(row["reviewed_at"])
        self.assertEqual(int(row["version"]), 1)
        self.assertEqual(int(review["reviewer_user_id"]), 1)
        self.assertEqual(sha256_file(BANK), self.bank_hash)

    def test_edit_published_item_creates_new_version_keeps_history(self):
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            self.sl.publish_all_drafts(db, 1)
            db.commit()
        self.login()
        self.force_arm(2, "B")
        self.client.get(f"{PREFIX}/{SKILL}/precheck")
        rv = self.post_submit(phase="precheck", item_id="slq_lrr_precheck_01", selected_answer="C")
        self.assertEqual(rv.status_code, 200)
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            new_v = self.sl.revise_published_item(db, "slq_lrr_precheck_01", "<p>edited stem</p>")
            db.commit()
        self.assertEqual(new_v, 2)
        conn = self.qdb()
        try:
            v1 = conn.execute(
                "SELECT stem_html, publish_status FROM skill_loop_items WHERE id=? AND version=1",
                ("slq_lrr_precheck_01",),
            ).fetchone()
            v2 = conn.execute(
                "SELECT review_status, publish_status FROM skill_loop_items WHERE id=? AND version=2",
                ("slq_lrr_precheck_01",),
            ).fetchone()
            step = conn.execute(
                "SELECT item_version FROM skill_loop_step_results WHERE item_id=?",
                ("slq_lrr_precheck_01",),
            ).fetchone()
        finally:
            conn.close()
        self.assertIn("warehouse", v1["stem_html"])
        self.assertEqual(v1["publish_status"], "published")
        self.assertEqual(v2["review_status"], "draft")
        self.assertEqual(int(step["item_version"]), 1)
        self.assertEqual(sha256_file(BANK), self.bank_hash)

    def test_submit_json_does_not_leak_key(self):
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            self.sl.publish_all_drafts(db, 1)
            db.commit()
        self.start_b()
        rv = self.post_submit(phase="precheck", item_id="slq_lrr_precheck_01", selected_answer="C")
        self.assertEqual(rv.status_code, 200)
        body = rv.get_json()
        self.assertNotIn("correct_answer", body)
        self.assertNotIn("answer", body)
        blob = json.dumps(body)
        self.assertNotIn('"C"', blob)


class TestStateMachine(_PilotCase):
    def _walk_to(self, stop_before: str | None = None):
        steps = [
            ("precheck", "slq_lrr_precheck_01", "C", None),
            ("instruction", "slq_lrr_example_01", "ok", None),
            ("faded", "slq_lrr_faded_01", "", {"rate": "150", "total_hours": "12"}),
            ("independent", "slq_lrr_ind_01", "C", None),
            ("independent", "slq_lrr_ind_02", "B", None),
            ("transfer", "slq_lrr_tr_01", "C", None),
            ("transfer", "slq_lrr_tr_02", "B", None),
        ]
        for phase, item_id, selected, faded in steps:
            if stop_before and phase == stop_before and item_id.endswith("_01"):
                return
            rv = self.client.get(f"{PREFIX}/{SKILL}/{phase}")
            self.assertEqual(rv.status_code, 200, phase)
            payload = {
                "phase": phase,
                "item_id": item_id,
                "selected_answer": selected,
                "hint_level": "none",
                "solution_viewed": False,
            }
            if faded:
                payload["faded"] = faded
            rv = self.post_submit(**payload)
            self.assertEqual(rv.status_code, 200, f"{phase} {item_id} {rv.data[:200]}")

    def test_happy_path_six_phases_then_delayed(self):
        self.start_b()
        self._walk_to()
        conn = self.qdb()
        try:
            run = conn.execute("SELECT * FROM skill_loop_runs WHERE user_id=2").fetchone()
            self.assertEqual(run["mastery_status"], "immediate_pass")
            self.assertEqual(run["current_phase"], "delayed")
            start = self.sl.parse_iso(run["instruction_completed_at"])
        finally:
            conn.close()
        html = self.client.get(f"{PREFIX}/{SKILL}/independent").get_data(as_text=True)
        self.assertNotIn("已掌握", html)
        self.assertIn("Immediate pass is not mastery", html)
        self._set_clock(lambda: start + timedelta(hours=48))
        rv = self.client.get(f"{PREFIX}/{SKILL}/delayed")
        self.assertEqual(rv.status_code, 200)
        self.post_submit(phase="delayed", item_id="slq_lrr_del_01", selected_answer="D")
        self.client.get(f"{PREFIX}/{SKILL}/delayed")
        self.post_submit(phase="delayed", item_id="slq_lrr_del_02", selected_answer="B")
        conn = self.qdb()
        try:
            run = conn.execute("SELECT mastery_status FROM skill_loop_runs WHERE user_id=2").fetchone()
        finally:
            conn.close()
        self.assertEqual(run["mastery_status"], "delayed_pass")
        html = self.client.get(PREFIX + "/").get_data(as_text=True)
        self.assertIn("已掌握", html)

    def test_skip_phase_and_direct_url_blocked(self):
        self.start_b()
        for phase in ("instruction", "faded", "independent", "transfer", "delayed"):
            self.assertEqual(self.client.get(f"{PREFIX}/{SKILL}/{phase}").status_code, 403)
        rv = self.post_submit(phase="independent", item_id="slq_lrr_ind_01", selected_answer="C")
        self.assertEqual(rv.status_code, 403)

    def test_refresh_keeps_progress(self):
        self.start_b()
        self.post_submit(phase="precheck", item_id="slq_lrr_precheck_01", selected_answer="C")
        rv1 = self.client.get(f"{PREFIX}/{SKILL}/instruction")
        rv2 = self.client.get(f"{PREFIX}/{SKILL}/instruction")
        self.assertEqual(rv1.status_code, 200)
        self.assertEqual(rv2.status_code, 200)
        conn = self.qdb()
        try:
            phase = conn.execute("SELECT current_phase FROM skill_loop_runs WHERE user_id=2").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(phase, "instruction")

    def test_duplicate_submit_does_not_repeat_events_or_scores(self):
        self.start_b()
        self.post_submit(phase="precheck", item_id="slq_lrr_precheck_01", selected_answer="C")
        self.post_submit(phase="precheck", item_id="slq_lrr_precheck_01", selected_answer="C")
        conn = self.qdb()
        try:
            steps = conn.execute("SELECT COUNT(*) FROM skill_loop_step_results").fetchone()[0]
            events = conn.execute(
                "SELECT COUNT(*) FROM skill_loop_events WHERE event_name='precheck_answered'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(steps, 1)
        self.assertEqual(events, 1)

    def test_going_back_does_not_reaward_pass(self):
        self.start_b()
        self.post_submit(phase="precheck", item_id="slq_lrr_precheck_01", selected_answer="C")
        self.client.get(f"{PREFIX}/{SKILL}/precheck")
        self.post_submit(phase="precheck", item_id="slq_lrr_precheck_01", selected_answer="C")
        conn = self.qdb()
        try:
            n = conn.execute("SELECT COUNT(*) FROM skill_loop_step_results WHERE phase='precheck'").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(n, 1)

    def test_solution_and_critical_hint_zero_independent(self):
        self.start_b()
        self._walk_to(stop_before="independent")
        self.client.get(f"{PREFIX}/{SKILL}/independent")
        rv = self.post_submit(
            phase="independent",
            item_id="slq_lrr_ind_01",
            selected_answer="C",
            solution_viewed=True,
        )
        self.assertEqual(rv.status_code, 200)
        conn = self.qdb()
        try:
            flag = conn.execute(
                "SELECT counts_as_independent FROM skill_loop_step_results WHERE item_id='slq_lrr_ind_01'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(int(flag), 0)
        rv = self.post_submit(
            phase="independent",
            item_id="slq_lrr_ind_02",
            selected_answer="B",
            hint_level="critical",
        )
        self.assertEqual(rv.status_code, 200)
        conn = self.qdb()
        try:
            flag2 = conn.execute(
                "SELECT counts_as_independent FROM skill_loop_step_results WHERE item_id='slq_lrr_ind_02'"
            ).fetchone()[0]
            status = conn.execute("SELECT mastery_status FROM skill_loop_runs WHERE user_id=2").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(int(flag2), 0)
        self.assertNotEqual(status, "immediate_pass")
        self.assertNotEqual(status, "delayed_pass")

    def test_first_independent_correct_is_one(self):
        self.start_b()
        self._walk_to(stop_before="independent")
        self.post_submit(phase="independent", item_id="slq_lrr_ind_01", selected_answer="C")
        conn = self.qdb()
        try:
            flag = conn.execute(
                "SELECT counts_as_independent FROM skill_loop_step_results WHERE item_id='slq_lrr_ind_01'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(int(flag), 1)

    def test_same_item_cannot_be_independent_and_delayed_evidence(self):
        self.start_b()
        self._walk_to()
        start = None
        conn = self.qdb()
        try:
            start = self.sl.parse_iso(
                conn.execute("SELECT instruction_completed_at FROM skill_loop_runs WHERE user_id=2").fetchone()[0]
            )
        finally:
            conn.close()
        self._set_clock(lambda: start + timedelta(hours=48))
        rv = self.post_submit(phase="delayed", item_id="slq_lrr_ind_01", selected_answer="C")
        self.assertEqual(rv.status_code, 403)

    def test_old_mastered_does_not_create_pilot_pass(self):
        conn = self.qdb()
        conn.execute(
            """
            INSERT OR REPLACE INTO mistake_learning_progress
            (learner_key, domain, topic, question_index, status, correct_after_last_wrong, updated_at)
            VALUES ('u:2', 'algebra', '1_1', 0, 'mastered', 2, datetime('now'))
            """
        )
        conn.commit()
        conn.close()
        self.start_b()
        conn = self.qdb()
        try:
            status = conn.execute("SELECT mastery_status FROM skill_loop_runs WHERE user_id=2").fetchone()[0]
        finally:
            conn.close()
        self.assertIn(status, ("learning", "not_started"))
        self.assertNotEqual(status, "immediate_pass")
        self.assertNotEqual(status, "delayed_pass")


class TestDelayedClock(_PilotCase):
    def _finish_instruction(self):
        self.start_b()
        self.post_submit(phase="precheck", item_id="slq_lrr_precheck_01", selected_answer="C")
        self.client.get(f"{PREFIX}/{SKILL}/instruction")
        self.post_submit(phase="instruction", item_id="slq_lrr_example_01", selected_answer="ok")
        conn = self.qdb()
        try:
            row = conn.execute("SELECT instruction_completed_at FROM skill_loop_runs WHERE user_id=2").fetchone()
            return self.sl.parse_iso(row[0])
        finally:
            conn.close()

    def test_locked_before_48h_open_at_exactly_48h(self):
        start = self._finish_instruction()
        self._set_clock(lambda: start + timedelta(hours=48) - timedelta(seconds=1))
        self.assertEqual(self.client.get(f"{PREFIX}/{SKILL}/delayed").status_code, 403)
        self._set_clock(lambda: start + timedelta(hours=48))
        # still on instruction/faded path; delayed URL allowed only if current_phase reached
        conn = self.qdb()
        try:
            conn.execute("UPDATE skill_loop_runs SET current_phase='delayed', current_variant=1 WHERE user_id=2")
            conn.commit()
        finally:
            conn.close()
        self._set_clock(lambda: start + timedelta(hours=48) - timedelta(seconds=1))
        self.assertEqual(self.client.get(f"{PREFIX}/{SKILL}/delayed").status_code, 403)
        self._set_clock(lambda: start + timedelta(hours=48))
        self.assertEqual(self.client.get(f"{PREFIX}/{SKILL}/delayed").status_code, 200)

    def test_delayed_window_boundaries_and_overdue_still_allowed(self):
        start = self._finish_instruction()
        conn = self.qdb()
        try:
            conn.execute("UPDATE skill_loop_runs SET current_phase='delayed', current_variant=1 WHERE user_id=2")
            conn.commit()
            run = conn.execute("SELECT * FROM skill_loop_runs WHERE user_id=2").fetchone()
        finally:
            conn.close()
        cases = [
            (timedelta(hours=47, minutes=59), "locked", 403),
            (timedelta(hours=48), "due", 200),
            (timedelta(hours=168), "due", 200),
            (timedelta(hours=168, seconds=1), "overdue", 200),
        ]
        for delta, state, status in cases:
            self._set_clock(lambda d=delta: start + d)
            with self.app_mod.app.app_context():
                self.assertEqual(self.sl.delayed_window_state(run), state, state)
            self.assertEqual(self.client.get(f"{PREFIX}/{SKILL}/delayed").status_code, status, state)
        self._set_clock(lambda: start + timedelta(hours=170))
        self.client.get(f"{PREFIX}/{SKILL}/delayed")
        self.post_submit(phase="delayed", item_id="slq_lrr_del_01", selected_answer="D")
        self.client.get(f"{PREFIX}/{SKILL}/delayed")
        self.post_submit(phase="delayed", item_id="slq_lrr_del_02", selected_answer="B")
        conn = self.qdb()
        try:
            row = conn.execute(
                "SELECT mastery_status, delayed_timing, delayed_elapsed_hours FROM skill_loop_runs WHERE user_id=2"
            ).fetchone()
            step = conn.execute(
                "SELECT elapsed_hours, completion_timing FROM skill_loop_step_results WHERE phase='delayed' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["mastery_status"], "delayed_pass")
        self.assertEqual(row["delayed_timing"], "overdue")
        self.assertGreater(float(row["delayed_elapsed_hours"]), 168)
        self.assertEqual(step["completion_timing"], "overdue")
        self.assertGreater(float(step["elapsed_hours"]), 168)

    def test_timezone_does_not_unlock_early(self):
        start = self._finish_instruction()
        conn = self.qdb()
        try:
            conn.execute("UPDATE skill_loop_runs SET current_phase='delayed' WHERE user_id=2")
            conn.commit()
        finally:
            conn.close()
        pacific = timezone(timedelta(hours=-8))
        almost = (start + timedelta(hours=48) - timedelta(minutes=1)).astimezone(pacific)
        self._set_clock(lambda: almost)
        self.assertEqual(self.client.get(f"{PREFIX}/{SKILL}/delayed").status_code, 403)

    def test_clock_injection_only_when_testing_no_system_time_change(self):
        self.assertFalse(hasattr(self.sl, "set_clock"))
        sentinel = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self._set_clock(lambda: sentinel)
        with self.app_mod.app.app_context():
            self.assertEqual(self.sl.now_utc(), sentinel)
        self._set_clock(None)
        with self.app_mod.app.app_context():
            delta = abs((self.sl.now_utc() - datetime.now(timezone.utc)).total_seconds())
        self.assertLess(delta, 5)

    def test_refresh_logout_other_client_do_not_unlock_early(self):
        start = self._finish_instruction()
        conn = self.qdb()
        try:
            conn.execute("UPDATE skill_loop_runs SET current_phase='delayed' WHERE user_id=2")
            conn.commit()
        finally:
            conn.close()
        self._set_clock(lambda: start + timedelta(hours=24))
        self.client.get(f"{PREFIX}/{SKILL}/delayed")
        self.client.get("/logout")
        other = self.app_mod.app.test_client()
        with other.session_transaction() as sess:
            sess["user_id"] = 2
            sess["user_role"] = "student"
            sess["username"] = "s1"
            sess["csrf_token"] = "test-csrf"
        self.assertEqual(other.get(f"{PREFIX}/{SKILL}/delayed").status_code, 403)

    def test_delayed_items_are_unseen_and_solution_not_independent(self):
        with open(os.path.join(ROOT, "data", "skill_loop_pilot", "sat.alg.linear_rate_remaining.json"), encoding="utf-8") as fh:
            pack = json.load(fh)
        by_slot = {}
        for it in pack["items"]:
            by_slot.setdefault(it["slot"], []).append(it["id"])
        delayed = set(by_slot["delayed"])
        seen_slots = ("precheck", "worked_example", "faded", "independent", "transfer")
        taught = {i for s in seen_slots for i in by_slot[s]}
        self.assertTrue(delayed.isdisjoint(taught))
        start = self._finish_instruction()
        conn = self.qdb()
        try:
            conn.execute("UPDATE skill_loop_runs SET current_phase='delayed', current_variant=1 WHERE user_id=2")
            conn.commit()
        finally:
            conn.close()
        self._set_clock(lambda: start + timedelta(hours=48))
        self.client.get(f"{PREFIX}/{SKILL}/delayed")
        self.post_submit(
            phase="delayed",
            item_id="slq_lrr_del_01",
            selected_answer="D",
            solution_viewed=True,
        )
        conn = self.qdb()
        try:
            flag = conn.execute(
                "SELECT counts_as_independent FROM skill_loop_step_results WHERE item_id='slq_lrr_del_01'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(int(flag), 0)


class TestAssignmentAB(_PilotCase):
    def test_hash_stable_across_calls_and_salt_change_after_write(self):
        from scripts.skill_loop_assignment import propose_arm, EXPERIMENT_ID

        a1, d1 = propose_arm(2, "salt-one", EXPERIMENT_ID)
        a2, d2 = propose_arm(2, "salt-one", EXPERIMENT_ID)
        self.assertEqual((a1, d1), (a2, d2))
        os.environ["SKILL_LOOP_ASSIGN_SALT"] = "salt-one"
        self.login()
        self.client.get(PREFIX + "/")
        conn = self.qdb()
        try:
            first = conn.execute("SELECT arm, hash_hex FROM skill_loop_assignments WHERE user_id=2").fetchone()
        finally:
            conn.close()
        os.environ["SKILL_LOOP_ASSIGN_SALT"] = "salt-changed-should-not-move"
        self.client.get(PREFIX + "/")
        conn = self.qdb()
        try:
            second = conn.execute("SELECT arm, hash_hex FROM skill_loop_assignments WHERE user_id=2").fetchone()
        finally:
            conn.close()
        self.assertEqual(first["arm"], second["arm"])
        self.assertEqual(first["hash_hex"], second["hash_hex"])

    def test_subprocess_hash_matches(self):
        from scripts.skill_loop_assignment import assignment_hash_hex, arm_from_hash, EXPERIMENT_ID

        digest = assignment_hash_hex(EXPERIMENT_ID, 2, "abc")
        code = (
            "from scripts.skill_loop_assignment import assignment_hash_hex, EXPERIMENT_ID;"
            "print(assignment_hash_hex(EXPERIMENT_ID, 2, 'abc'))"
        )
        proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(proc.stdout.strip(), digest)
        self.assertIn(arm_from_hash(digest), ("A", "B"))

    def test_admin_override_records_operator_time_reason_and_wins(self):
        self.login(user_id=1, role="admin", username="teacher")
        rv = self.client.post(
            f"{PREFIX}/admin/assign",
            data=json.dumps({"user_id": 2, "arm": "A", "reason": "qa pairing"}),
            headers=self.headers(),
        )
        self.assertEqual(rv.status_code, 200)
        conn = self.qdb()
        try:
            row = conn.execute("SELECT * FROM skill_loop_assignments WHERE user_id=2").fetchone()
        finally:
            conn.close()
        self.assertEqual(row["arm"], "A")
        self.assertEqual(row["assignment_source"], "admin")
        self.assertEqual(int(row["assigned_by"]), 1)
        self.assertEqual(row["override_reason"], "qa pairing")
        self.assertTrue(row["assigned_at"])

    def test_excluded_roles_and_arm_isolation_and_equivalent_items(self):
        from scripts.skill_loop_assignment import is_excluded_from_analysis

        self.assertTrue(is_excluded_from_analysis("admin", "teacher"))
        self.assertTrue(is_excluded_from_analysis("staff", "1"))
        self.assertTrue(is_excluded_from_analysis("student", "test_user"))
        self.assertFalse(is_excluded_from_analysis("student", "s1"))
        self.force_arm(2, "A")
        self.login(user_id=2)
        self.client.get(PREFIX + "/")
        self.assertEqual(self.client.get(f"{PREFIX}/{SKILL}/instruction").status_code, 403)
        self.force_arm(3, "B")
        self.login(user_id=3, username="s2")
        self.assertEqual(self.client.get(f"{PREFIX}/{SKILL}/precheck").status_code, 200)
        with open(os.path.join(ROOT, "data", "skill_loop_pilot", "sat.alg.linear_rate_remaining.json"), encoding="utf-8") as fh:
            pack = json.load(fh)
        slots = {it["id"]: it["slot"] for it in pack["items"]}
        self.assertEqual(slots["slq_lrr_precheck_01"], "precheck")
        self.assertEqual(slots["slq_lrr_del_01"], "delayed")
        self.assertEqual(slots["slq_lrr_ind_01"], "independent")
        self.assertNotEqual(slots["slq_lrr_ind_01"], slots["slq_lrr_del_01"])
        self.login(user_id=1, role="admin", username="teacher")
        rv = self.client.get(f"{PREFIX}/admin/report")
        self.assertEqual(rv.status_code, 200)
        html = rv.get_data(as_text=True)
        self.assertIn("Immediate performance", html)
        self.assertIn("Transfer", html)
        self.assertIn("Delayed retention", html)
        self.assertIn("Pilot only — usability and data-integrity evaluation", html)
        self.assertIn("不构成教学有效性或提分证明", html)
        self.assertIn("data-no-conclusion", html)
        self.assertNotIn("显著", html)
        self.assertNotIn("优于", html)
        export = self.client.get(f"{PREFIX}/admin/report.txt")
        self.assertEqual(export.status_code, 200)
        text = export.get_data(as_text=True)
        self.assertIn("Pilot only — usability and data-integrity evaluation", text)
        self.assertIn("assigned_denominator=", text)
        self.assertIn("completed_denominator=", text)


class TestIsolationAndPermissions(_PilotCase):
    def test_student_cannot_read_other_run_or_open_review(self):
        self.login(user_id=3, username="s2")
        self.force_arm(3, "B")
        self.client.get(f"{PREFIX}/{SKILL}/precheck")
        conn = self.qdb()
        try:
            other_run = conn.execute("SELECT id FROM skill_loop_runs WHERE user_id=3").fetchone()[0]
        finally:
            conn.close()
        self.login(user_id=2, username="s1")
        self.force_arm(2, "B")
        self.client.get(f"{PREFIX}/{SKILL}/precheck")
        rv = self.client.get(f"{PREFIX}/api/run/{other_run}")
        self.assertEqual(rv.status_code, 403)
        rv = self.client.get(f"{PREFIX}/{SKILL}/precheck?user_id=3")
        self.assertEqual(rv.status_code, 403)
        self.assertEqual(self.client.get(f"{PREFIX}/admin/review").status_code, 403)
        self.assertEqual(self.client.get(f"{PREFIX}/admin/report").status_code, 403)

    def test_teacher_review_does_not_modify_question_bank(self):
        before = sha256_file(BANK)
        self.login(user_id=1, role="admin", username="teacher")
        self.client.get(f"{PREFIX}/admin/review")
        self.client.post(
            f"{PREFIX}/admin/publish",
            data=json.dumps({"item_id": "slq_lrr_precheck_01", "version": 1}),
            headers=self.headers(),
        )
        self.assertEqual(sha256_file(BANK), before)

    def test_anonymous_cannot_assign_or_submit(self):
        rv = self.client.post(
            f"{PREFIX}/{SKILL}/submit",
            data=json.dumps({"phase": "precheck", "item_id": "slq_lrr_precheck_01", "selected_answer": "C"}),
            headers=self.headers(),
        )
        self.assertIn(rv.status_code, (302, 401, 403))
        conn = self.qdb()
        try:
            n = conn.execute("SELECT COUNT(*) FROM skill_loop_assignments").fetchone()[0]
            steps = conn.execute("SELECT COUNT(*) FROM skill_loop_step_results").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(n, 0)
        self.assertEqual(steps, 0)

    def test_csrf_and_direct_state_tamper_blocked(self):
        self.start_b()
        rv = self.client.post(
            f"{PREFIX}/{SKILL}/submit",
            data=json.dumps({"phase": "precheck", "item_id": "slq_lrr_precheck_01", "selected_answer": "C"}),
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(rv.status_code, 403)
        self.client.get(f"{PREFIX}/{SKILL}/precheck")
        rv = self.post_submit(
            phase="precheck",
            item_id="slq_lrr_precheck_01",
            selected_answer="C",
            current_phase="delayed",
            mastery_status="delayed_pass",
        )
        self.assertEqual(rv.status_code, 403)


class TestAnalyticsIsolation(_PilotCase):
    def test_old_mark_mastered_writes_only_old_table(self):
        self.login()
        before = self._counts()
        rv = self.client.post(
            "/practice/analytics/api/mastery",
            data=json.dumps({"domain": "algebra", "topic": "1_1", "question_index": 0}),
            headers=self.headers(),
        )
        self.assertEqual(rv.status_code, 200)
        after = self._counts()
        self.assertEqual(after["runs"], before["runs"])
        self.assertEqual(after["events"], before["events"])
        self.assertGreaterEqual(after["mistakes"], before["mistakes"])
        conn = self.qdb()
        try:
            st = conn.execute(
                """
                SELECT status FROM mistake_learning_progress
                WHERE learner_key='u:2' AND domain='algebra' AND topic='1_1' AND question_index=0
                """
            ).fetchone()
            pilot_status = conn.execute("SELECT COUNT(*) FROM skill_loop_runs").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(st["status"], "archived")
        self.assertEqual(pilot_status, 0)

    def test_pilot_writes_only_new_tables_and_does_not_change_old_analytics(self):
        self.login()
        before = self._counts()
        self.start_b()
        self.post_submit(phase="precheck", item_id="slq_lrr_precheck_01", selected_answer="A")
        after = self._counts()
        self.assertEqual(after["attempts"], before["attempts"])
        self.assertEqual(after["responses"], before["responses"])
        self.assertEqual(after["mistakes"], before["mistakes"])
        self.assertGreater(after["runs"], before["runs"])
        self.assertGreater(after["events"], before["events"])
        self.assertGreater(after["steps"], before["steps"])

    def test_two_mastery_systems_do_not_overwrite(self):
        self.login()
        self.client.post(
            "/practice/analytics/api/mastery",
            data=json.dumps({"domain": "algebra", "topic": "1_1", "question_index": 0}),
            headers=self.headers(),
        )
        self.start_b()
        conn = self.qdb()
        try:
            old = conn.execute(
                """
                SELECT status FROM mistake_learning_progress
                WHERE learner_key='u:2' AND domain='algebra' AND topic='1_1' AND question_index=0
                """
            ).fetchone()[0]
            pilot = conn.execute("SELECT mastery_status FROM skill_loop_runs WHERE user_id=2").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(old, "archived")
        self.assertNotEqual(pilot, "delayed_pass")
        self.assertNotEqual(pilot, "immediate_pass")

    def test_flag_toggle_does_not_change_old_analytics_counts(self):
        self.login()
        before = self._counts()
        self.app_mod.app.config["SKILL_LOOP_PILOT"] = False
        self.client.get("/practice")
        self.client.get(PREFIX + "/")
        self.app_mod.app.config["SKILL_LOOP_PILOT"] = True
        after = self._counts()
        self.assertEqual(before["attempts"], after["attempts"])
        self.assertEqual(before["responses"], after["responses"])
        self.assertEqual(before["mistakes"], after["mistakes"])

    def _counts(self):
        conn = self.qdb()
        try:
            def n(sql):
                return int(conn.execute(sql).fetchone()[0])

            return {
                "attempts": n("SELECT COUNT(*) FROM practice_attempts"),
                "responses": n("SELECT COUNT(*) FROM practice_responses"),
                "mistakes": n("SELECT COUNT(*) FROM mistake_learning_progress"),
                "runs": n("SELECT COUNT(*) FROM skill_loop_runs"),
                "events": n("SELECT COUNT(*) FROM skill_loop_events"),
                "steps": n("SELECT COUNT(*) FROM skill_loop_step_results"),
            }
        finally:
            conn.close()


class TestAssignmentConcurrency(_PilotCase):
    def test_unique_experiment_user_and_concurrent_first_assign(self):
        import threading

        conn = self.qdb()
        try:
            sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='skill_loop_assignments'"
            ).fetchone()[0]
            idx = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_skill_loop_assignments_exp_user'"
            ).fetchone()
        finally:
            conn.close()
        compact = " ".join(sql.split())
        self.assertIn("UNIQUE(experiment_id, user_id)", compact)
        self.assertIsNotNone(idx)

        barrier = threading.Barrier(2)
        arms: list[str | None] = [None, None]
        errors: list[BaseException] = []

        def worker(i: int) -> None:
            c = sqlite3.connect(self.db, timeout=30)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA busy_timeout=30000")
            try:
                barrier.wait(timeout=5)
                row = self.sl.ensure_assignment(c, 14, SKILL)
                c.commit()
                arms[i] = str(row["arm"])
            except BaseException as exc:
                errors.append(exc)
            finally:
                c.close()

        t1 = threading.Thread(target=worker, args=(0,))
        t2 = threading.Thread(target=worker, args=(1,))
        t1.start()
        t2.start()
        t1.join(10)
        t2.join(10)
        self.assertFalse(errors, errors)
        self.assertEqual(arms[0], arms[1])
        conn = self.qdb()
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM skill_loop_assignments WHERE user_id=14"
            ).fetchone()[0]
            stored = conn.execute(
                "SELECT arm FROM skill_loop_assignments WHERE user_id=14"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(n, 1)
        self.assertEqual(stored, arms[0])

    def test_admin_override_does_not_insert_second_row(self):
        self.login()
        self.client.get(PREFIX + "/")
        self.force_arm(2, "A")
        self.force_arm(2, "B")
        conn = self.qdb()
        try:
            rows = conn.execute(
                "SELECT arm, assignment_source, override_reason FROM skill_loop_assignments WHERE user_id=2"
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["arm"], "B")
        self.assertEqual(rows[0]["assignment_source"], "admin")


class TestTransferAccuracy(_PilotCase):
    def _insert_run(self, user_id: int, arm: str = "B") -> int:
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            self.sl.admin_override_arm(db, user_id, SKILL, arm, 1, "metrics fixture")
            run = self.sl.ensure_run(db, user_id, SKILL, arm)
            db.commit()
            return int(run["id"])

    def _insert_step(self, run_id: int, item_id: str, phase: str, **kw):
        conn = self.qdb()
        conn.execute(
            """
            INSERT INTO skill_loop_step_results (
                run_id, item_id, item_version, phase, selected_answer, is_correct,
                hint_used, hint_level, solution_viewed, counts_as_independent,
                is_repeat_of_seen_item
            ) VALUES (?, ?, 1, ?, 'C', ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                item_id,
                phase,
                kw.get("is_correct", 1),
                kw.get("hint_used", 0),
                kw.get("hint_level", "none"),
                kw.get("solution_viewed", 0),
                kw.get("counts_as_independent", 1),
                kw.get("is_repeat_of_seen_item", 0),
            ),
        )
        conn.commit()
        conn.close()

    def test_transfer_accuracy_rules_and_denominators(self):
        run2 = self._insert_run(2, "B")
        run3 = self._insert_run(3, "B")
        run14 = self._insert_run(14, "B")
        self._insert_step(run2, "slq_lrr_ind_01", "independent", counts_as_independent=1)
        self._insert_step(run2, "slq_lrr_ind_02", "independent", counts_as_independent=1)
        self._insert_step(run2, "slq_lrr_tr_01", "transfer", counts_as_independent=1)
        self._insert_step(run2, "slq_lrr_tr_02", "transfer", counts_as_independent=1)
        self._insert_step(run3, "slq_lrr_tr_01", "transfer", counts_as_independent=1)
        self._insert_step(
            run14, "slq_lrr_tr_01", "transfer", counts_as_independent=0, solution_viewed=1
        )
        self._insert_step(
            run14, "slq_lrr_tr_02", "transfer", counts_as_independent=0, hint_level="critical"
        )
        conn = self.qdb()
        conn.execute("UPDATE skill_loop_runs SET current_phase='delayed' WHERE id=?", (run2,))
        conn.execute("UPDATE skill_loop_runs SET current_phase='transfer' WHERE id=?", (run3,))
        conn.execute("UPDATE skill_loop_runs SET current_phase='independent' WHERE id=?", (run14,))
        conn.commit()
        conn.close()
        self._insert_step(run2, "slq_lrr_del_01", "delayed", counts_as_independent=1)
        with self.app_mod.app.app_context():
            db = self.app_mod.get_db()
            metrics = self.sl.compute_analysis_report(db)
        self.assertEqual(metrics["transfer_assigned_denominator"], 3)
        self.assertEqual(metrics["transfer_started_denominator"], 3)
        self.assertEqual(metrics["transfer_completed_denominator"], 2)
        self.assertEqual(metrics["transfer_independent_correct_completed"], 2)
        self.assertEqual(metrics["transfer_accuracy_completed"], 0.5)
        self.assertEqual(metrics["transfer_independent_correct_started"], 3)
        self.assertEqual(metrics["transfer_accuracy_started"], 0.5)
        self.assertIn("Assigned students who have not started", metrics["incomplete_rule"])
        self.assertFalse(metrics["allow_conclusion_labels"])
        conn = self.qdb()
        try:
            mixed = conn.execute(
                "SELECT COUNT(*) FROM skill_loop_step_results WHERE phase='independent' AND counts_as_independent=1"
            ).fetchone()[0]
            delayed_indep = conn.execute(
                "SELECT COUNT(*) FROM skill_loop_step_results WHERE phase='delayed' AND counts_as_independent=1"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(mixed, 2)
        self.assertEqual(delayed_indep, 1)
        self.assertNotEqual(metrics["transfer_independent_correct_completed"], mixed + delayed_indep)


class TestClockIsolation(_PilotCase):
    def test_no_set_clock_or_clock_routes_in_production_modules(self):
        for rel in ("skill_loop.py", "app.py"):
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                text = fh.read()
            self.assertNotIn("def set_clock", text)
            self.assertNotRegex(text, r"@skill_loop_bp\.route\([^\n]*clock")
            self.assertNotRegex(text, r"@app\.route\([^\n]*clock")
        self.login()
        for path in (
            f"{PREFIX}/clock",
            f"{PREFIX}/set-clock",
            f"{PREFIX}/{SKILL}/clock",
            "/admin/clock",
            "/__test__/clock",
        ):
            rv = self.client.get(path)
            self.assertEqual(rv.status_code, 404, path)

    def test_env_cannot_enable_clock(self):
        os.environ["SKILL_LOOP_CLOCK"] = "2099-01-01T00:00:00Z"
        os.environ["ENABLE_TIME_TRAVEL"] = "1"
        try:
            self.app_mod.app.config.pop("SKILL_LOOP_CLOCK", None)
            with self.app_mod.app.app_context():
                delta = abs((self.sl.now_utc() - datetime.now(timezone.utc)).total_seconds())
            self.assertLess(delta, 5)
        finally:
            os.environ.pop("SKILL_LOOP_CLOCK", None)
            os.environ.pop("ENABLE_TIME_TRAVEL", None)

    def test_clock_ignored_when_not_testing(self):
        sentinel = datetime(2099, 1, 1, tzinfo=timezone.utc)
        self.app_mod.app.config["SKILL_LOOP_CLOCK"] = lambda: sentinel
        self.app_mod.app.config["TESTING"] = False
        try:
            with self.app_mod.app.app_context():
                delta = abs((self.sl.now_utc() - datetime.now(timezone.utc)).total_seconds())
            self.assertLess(delta, 5)
        finally:
            self.app_mod.app.config["TESTING"] = True
            self.app_mod.app.config.pop("SKILL_LOOP_CLOCK", None)


class TestProductionSalt(_PilotCase):
    def test_production_without_salt_disables_pilot_and_refuses_dev_fallback(self):
        os.environ["RENDER"] = "true"
        os.environ.pop("SKILL_LOOP_ASSIGN_SALT", None)
        self.app_mod.app.config["SKILL_LOOP_PILOT"] = True
        os.environ["SKILL_LOOP_PILOT"] = "1"
        try:
            with self.app_mod.app.app_context():
                self.assertTrue(self.sl.production_salt_missing())
                self.assertFalse(self.sl.skill_loop_enabled())
                with self.assertRaises(self.sl.SkillLoopConfigError):
                    self.sl.assign_salt()
            self.login()
            self.assertEqual(self.client.get(PREFIX + "/").status_code, 404)
        finally:
            os.environ.pop("RENDER", None)
            os.environ.pop("SKILL_LOOP_PILOT", None)
            self.app_mod.app.config["SKILL_LOOP_PILOT"] = True

    def test_salt_not_leaked_to_client_or_report(self):
        os.environ["SKILL_LOOP_ASSIGN_SALT"] = "super-secret-salt-value"
        self.login()
        self.client.get(PREFIX + "/")
        html = self.client.get(PREFIX + "/").get_data(as_text=True)
        self.assertNotIn("super-secret-salt-value", html)
        self.assertNotIn("np-skill-loop-local-dev-salt-v1", html)
        self.login(user_id=1, role="admin", username="teacher")
        report = self.client.get(f"{PREFIX}/admin/report").get_data(as_text=True)
        export = self.client.get(f"{PREFIX}/admin/report.txt").get_data(as_text=True)
        self.assertNotIn("super-secret-salt-value", report)
        self.assertNotIn("super-secret-salt-value", export)
        with open(os.path.join(ROOT, "static", "skill_loop.js"), encoding="utf-8") as handle:
            js = handle.read()
        self.assertNotIn("super-secret-salt-value", js)


class TestStaticJsSafety(unittest.TestCase):
    def test_static_js_has_no_secrets_or_answers(self):
        with open(os.path.join(ROOT, "static", "skill_loop.js"), encoding="utf-8") as handle:
            js = handle.read()
        lowered = js.lower()
        for needle in (
            "correct_answer",
            "sk-",
            "salt",
            "unpublished",
            "slq_lrr_",
            "password",
            "secret",
            "np-skill-loop-local-dev-salt-v1",
        ):
            self.assertNotIn(needle.lower(), lowered)
        self.assertIn("fetch(", js)


class TestLoginStorage(unittest.TestCase):
    def test_login_template_does_not_store_password(self):
        with open(os.path.join(ROOT, "templates", "login.html"), encoding="utf-8") as handle:
            html = handle.read()
        self.assertIn("Remember username", html)
        self.assertNotIn("Remember password", html)
        self.assertNotIn("saved.password", html)
        self.assertNotIn("password: pass", html)
        self.assertNotIn("password:pass", html)
        self.assertNotRegex(html, r"localStorage\.setItem\([^)]*password")
        self.assertNotRegex(html, r"sessionStorage\.setItem\([^)]*password")
        self.assertIn('type="password"', html)
        self.assertIn("setPasswordVisible(false)", html)
        self.assertIn('JSON.stringify({ username:', html)


class TestTeachingExperience(_PilotCase):
    def test_hints_and_solution_are_visible_and_zero_independent(self):
        self.start_b()
        self._walk_to_from_state_machine("independent")
        page = self.client.get(f"{PREFIX}/{SKILL}/independent").get_data(as_text=True)
        self.assertNotIn("Books gone in 6 hours", page)
        self.assertNotIn("Why: Removed = start − remaining.", page)
        rv = self.client.post(
            f"{PREFIX}/{SKILL}/event",
            data=json.dumps({"kind": "hint", "level": "light", "item_id": "slq_lrr_ind_01"}),
            headers=self.headers(),
        )
        self.assertEqual(rv.status_code, 200)
        light = rv.get_json()
        self.assertTrue("rate" in light["hint_text"].lower() or "snapshot" in light["hint_text"].lower())
        self.assertNotIn("t = 18", light["hint_text"])
        rv = self.client.post(
            f"{PREFIX}/{SKILL}/event",
            data=json.dumps({"kind": "hint", "level": "critical", "item_id": "slq_lrr_ind_01"}),
            headers=self.headers(),
        )
        crit = rv.get_json()
        self.assertIn("250", crit["hint_text"])
        self.assertIn("4,500", crit["hint_text"])
        rv = self.client.post(
            f"{PREFIX}/{SKILL}/event",
            data=json.dumps({"kind": "solution", "item_id": "slq_lrr_ind_01"}),
            headers=self.headers(),
        )
        sol = rv.get_json()["solution"]
        self.assertIn("18", sol["answer_display"])
        self.assertGreaterEqual(len(sol["worked_steps"]), 4)
        self.assertTrue(all(step.get("why") for step in sol["worked_steps"]))
        self.assertIn("4,500", sol["explanation_check"])
        self.post_submit(
            phase="independent",
            item_id="slq_lrr_ind_01",
            selected_answer="C",
            solution_viewed=True,
            hint_level="critical",
        )
        conn = self.qdb()
        try:
            flag = conn.execute(
                "SELECT counts_as_independent FROM skill_loop_step_results WHERE item_id='slq_lrr_ind_01'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(int(flag), 0)
        fb = self.client.get(f"{PREFIX}/{SKILL}/feedback")
        self.assertEqual(fb.status_code, 200)
        html = fb.get_data(as_text=True)
        self.assertIn("data-skill-loop-feedback", html)
        self.assertIn("Correct", html)
        self.assertIn("Core idea", html)

    def _walk_to_from_state_machine(self, stop_before: str):
        TestStateMachine._walk_to(self, stop_before=stop_before)

    def test_precheck_miss_still_enters_instruction_without_fail_label(self):
        self.start_b()
        rv = self.post_submit(phase="precheck", item_id="slq_lrr_precheck_01", selected_answer="A")
        body = rv.get_json()
        self.assertEqual(body["next_phase"], "instruction")
        self.assertNotEqual(body["mastery_status"], "needs_review")
        html = self.client.get(f"{PREFIX}/{SKILL}/feedback").get_data(as_text=True)
        self.assertIn("Incorrect", html)
        self.assertIn("does not apply a fail tag", html)
        self.assertEqual(self.client.get(f"{PREFIX}/{SKILL}/instruction").status_code, 200)

    def test_faded_miss_routes_to_example_and_new_faded_item(self):
        self.start_b()
        TestStateMachine._walk_to(self, stop_before="faded")
        rv = self.post_submit(
            phase="faded",
            item_id="slq_lrr_faded_01",
            selected_answer="",
            faded={"rate": "1", "total_hours": "1"},
        )
        body = rv.get_json()
        self.assertEqual(body["remediation"], "faded_rework")
        self.assertEqual(body["next_phase"], "faded")
        self.assertNotEqual(body["next_phase"], "independent")
        conn = self.qdb()
        try:
            run = conn.execute("SELECT current_phase, current_variant FROM skill_loop_runs WHERE user_id=2").fetchone()
        finally:
            conn.close()
        self.assertEqual(run["current_phase"], "faded")
        self.assertEqual(self.client.get(f"{PREFIX}/{SKILL}/independent").status_code, 403)
        fb = self.client.get(f"{PREFIX}/{SKILL}/feedback").get_data(as_text=True)
        self.assertIn("Incorrect", fb)
        self.assertIn("data-sl-feedback-continue", fb)
        self.assertIn("/instruction", fb)
        inst = self.client.get(f"{PREFIX}/{SKILL}/instruction").get_data(as_text=True)
        self.assertIn("data-sl-remediation", inst)
        self.assertIn("new faded attempt", inst)
        faded = self.client.get(f"{PREFIX}/{SKILL}/faded").get_data(as_text=True)
        self.assertIn("slq_lrr_faded_02", faded)
        self.assertIn("3,600", faded)

    def test_independent_and_transfer_miss_do_not_pass(self):
        self.start_b()
        TestStateMachine._walk_to(self, stop_before="independent")
        rv = self.post_submit(phase="independent", item_id="slq_lrr_ind_01", selected_answer="A")
        body = rv.get_json()
        self.assertEqual(body["remediation"], "independent_new_item")
        self.assertNotEqual(body["mastery_status"], "immediate_pass")
        conn = self.qdb()
        try:
            row = conn.execute(
                "SELECT is_correct, counts_as_independent FROM skill_loop_step_results WHERE item_id='slq_lrr_ind_01'"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(int(row["is_correct"]), 0)
        self.assertEqual(int(row["counts_as_independent"]), 0)
        nxt = self.client.get(f"{PREFIX}/{SKILL}/independent").get_data(as_text=True)
        self.assertNotIn("9,000 books", nxt)
        self.post_submit(phase="independent", item_id="slq_lrr_ind_01", selected_answer="C")
        conn = self.qdb()
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM skill_loop_step_results WHERE item_id='slq_lrr_ind_01'"
            ).fetchone()[0]
            status = conn.execute("SELECT mastery_status FROM skill_loop_runs WHERE user_id=2").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(n, 1)
        self.assertNotEqual(status, "immediate_pass")
        self.post_submit(phase="independent", item_id="slq_lrr_ind_02", selected_answer="B")
        self.post_submit(phase="independent", item_id="slq_lrr_ind_03", selected_answer="C")
        rv = self.post_submit(phase="transfer", item_id="slq_lrr_tr_01", selected_answer="A")
        self.assertEqual(rv.get_json()["remediation"], "transfer_new_item")
        conn = self.qdb()
        try:
            status = conn.execute("SELECT mastery_status FROM skill_loop_runs WHERE user_id=2").fetchone()[0]
            flag = conn.execute(
                "SELECT counts_as_independent FROM skill_loop_step_results WHERE item_id='slq_lrr_tr_01'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertNotEqual(status, "delayed_pass")
        self.assertEqual(int(flag), 0)
        fb = self.client.get(f"{PREFIX}/{SKILL}/feedback").get_data(as_text=True)
        self.assertIn("What changed about the unknown", fb)
        transfer_page = self.client.get(f"{PREFIX}/{SKILL}/transfer").get_data(as_text=True)
        self.assertTrue("additional hours" in transfer_page or "R(t)" in transfer_page)

    def test_delayed_miss_sets_needs_review(self):
        self.start_b()
        TestStateMachine._walk_to(self)
        conn = self.qdb()
        try:
            start = self.sl.parse_iso(
                conn.execute("SELECT instruction_completed_at FROM skill_loop_runs WHERE user_id=2").fetchone()[0]
            )
        finally:
            conn.close()
        self._set_clock(lambda: start + timedelta(hours=48))
        rv = self.post_submit(phase="delayed", item_id="slq_lrr_del_01", selected_answer="A")
        self.assertEqual(rv.get_json()["mastery_status"], "needs_review")
        conn = self.qdb()
        try:
            status = conn.execute("SELECT mastery_status FROM skill_loop_runs WHERE user_id=2").fetchone()[0]
            scheduled = conn.execute(
                "SELECT COUNT(*) FROM skill_loop_events WHERE event_name='review_scheduled'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(status, "needs_review")
        self.assertGreaterEqual(scheduled, 1)

    def test_arm_a_self_report_and_report_disclaimer(self):
        self.login()
        self.force_arm(2, "A")
        self.assertEqual(self.client.get(f"{PREFIX}/{SKILL}/precheck").status_code, 200)
        self.post_submit(phase="precheck", item_id="slq_lrr_precheck_01", selected_answer="C")
        html = self.client.get(f"{PREFIX}/{SKILL}/control").get_data(as_text=True)
        self.assertIn("self-report", html.lower())
        self.client.post(
            f"{PREFIX}/{SKILL}/complete-control",
            data=json.dumps({}),
            headers=self.headers(),
        )
        fb = self.client.get(f"{PREFIX}/{SKILL}/feedback").get_data(as_text=True)
        self.assertIn("self-report", fb.lower())
        self.login(user_id=1, role="admin", username="teacher")
        report = self.client.get(f"{PREFIX}/admin/report").get_data(as_text=True)
        export = self.client.get(f"{PREFIX}/admin/report.txt").get_data(as_text=True)
        self.assertIn("cannot be fully verified", report)
        self.assertIn("无法完全验证", report)
        self.assertIn("cannot be fully verified", export)
        self.assertIn("data-no-conclusion", report)
        self.assertIn("Not evidence of instructional effectiveness", report)

    def test_representation_transfer_item_is_draft_until_review(self):
        with open(
            os.path.join(ROOT, "data", "skill_loop_pilot", "sat.alg.linear_rate_remaining.json"),
            encoding="utf-8",
        ) as handle:
            pack = json.load(handle)
        tr = next(item for item in pack["items"] if item["id"] == "slq_lrr_tr_03")
        self.assertEqual(tr["slot"], "transfer")
        self.assertEqual(tr["review_status"], "draft")
        self.assertIn("<table", tr["stem_html"])
        self.assertTrue(any("R(t)" in choice for choice in tr["choices"]))
        self.assertIn("9,600", tr["stem_html"])
        conn = self.qdb()
        try:
            row = conn.execute(
                "SELECT stem_html, slot FROM skill_loop_items WHERE id='slq_lrr_tr_03'"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["slot"], "transfer")
        self.assertIn("<table", row["stem_html"])


class TestBankHashAfterSuite(unittest.TestCase):
    def test_question_bank_still_untouched(self):
        digest = sha256_file(BANK)
        self.assertEqual(len(digest), 64)
        if getattr(TestBaselineProtection, "bank_sha256", None):
            self.assertEqual(digest, TestBaselineProtection.bank_sha256)
        print(f"\nquestion_bank.json SHA-256 after tests={digest}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
