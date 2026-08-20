#!/usr/bin/env python3
"""Additive skill-loop schema + optional draft seed. Never touches official banks.

Usage:
  python3 scripts/skill_loop_migrate.py --dry-run
  python3 scripts/skill_loop_migrate.py --schema-only --db /abs/path/to/LOCAL-copy.db
  python3 scripts/skill_loop_migrate.py --schema-only --allow-render-production --db /var/data/sat.db
  python3 scripts/skill_loop_migrate.py --apply --db /abs/path/to/LOCAL-copy.db

Dry-run prints SQL and does not connect.
Schema-only runs the 15 CREATE TABLE/INDEX IF NOT EXISTS statements in one
transaction and never seeds. --apply still refuses /var/data. Production path
is allowed only with --schema-only --allow-render-production.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys

RENDER_FORBIDDEN = "/var/data"
FORBIDDEN_SQL = re.compile(r"\b(DROP|TRUNCATE|DELETE|ALTER)\b", re.IGNORECASE)
PACK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "skill_loop_pilot",
    "sat.alg.linear_rate_remaining.json",
)

SQL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS skill_loop_skills (
        code TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        microskill_statement TEXT NOT NULL,
        control_lesson_slug TEXT,
        control_practice_url TEXT,
        is_active INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS skill_loop_items (
        id TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        skill_code TEXT NOT NULL,
        slot TEXT NOT NULL,
        variant_index INTEGER NOT NULL DEFAULT 1,
        stem_html TEXT NOT NULL,
        choices_json TEXT,
        question_kind TEXT NOT NULL,
        correct_answer TEXT,
        answer_alternates_json TEXT,
        worked_steps_json TEXT,
        faded_json TEXT,
        review_status TEXT NOT NULL DEFAULT 'draft',
        publish_status TEXT NOT NULL DEFAULT 'unpublished',
        reviewed_by INTEGER,
        reviewed_at TEXT,
        source_note TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (id, version)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_skill_loop_items_skill_slot ON skill_loop_items(skill_code, slot, review_status, publish_status)",
    """
    CREATE TABLE IF NOT EXISTS skill_loop_item_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id TEXT NOT NULL,
        item_version INTEGER NOT NULL DEFAULT 1,
        reviewer_user_id INTEGER,
        decision TEXT NOT NULL,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS skill_loop_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        skill_code TEXT NOT NULL,
        arm TEXT NOT NULL,
        assignment_source TEXT NOT NULL,
        hash_hex TEXT,
        salt_version TEXT,
        assigned_by INTEGER,
        override_reason TEXT,
        assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(experiment_id, user_id)
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_loop_assignments_exp_user ON skill_loop_assignments(experiment_id, user_id)",
    "CREATE INDEX IF NOT EXISTS idx_skill_loop_assignments_user ON skill_loop_assignments(user_id, skill_code)",
    "CREATE INDEX IF NOT EXISTS idx_skill_loop_assignments_exp ON skill_loop_assignments(experiment_id, arm)",
    """
    CREATE TABLE IF NOT EXISTS skill_loop_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        skill_code TEXT NOT NULL,
        experiment_id TEXT NOT NULL,
        arm TEXT NOT NULL,
        mastery_status TEXT NOT NULL DEFAULT 'not_started',
        current_phase TEXT NOT NULL DEFAULT 'precheck',
        current_variant INTEGER NOT NULL DEFAULT 1,
        started_at TEXT,
        instruction_completed_at TEXT,
        immediate_completed_at TEXT,
        delayed_available_at TEXT,
        delayed_deadline_at TEXT,
        delayed_completed_at TEXT,
        delayed_elapsed_hours REAL,
        delayed_timing TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(user_id, skill_code)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_skill_loop_runs_user_skill ON skill_loop_runs(user_id, skill_code)",
    """
    CREATE TABLE IF NOT EXISTS skill_loop_step_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        item_id TEXT NOT NULL,
        item_version INTEGER NOT NULL DEFAULT 1,
        phase TEXT NOT NULL,
        selected_answer TEXT,
        is_correct INTEGER,
        hint_used INTEGER NOT NULL DEFAULT 0,
        hint_level TEXT NOT NULL DEFAULT 'none',
        solution_viewed INTEGER NOT NULL DEFAULT 0,
        elapsed_ms INTEGER,
        started_at TEXT,
        submitted_at TEXT,
        counts_as_independent INTEGER NOT NULL DEFAULT 0,
        is_repeat_of_seen_item INTEGER NOT NULL DEFAULT 0,
        elapsed_hours REAL,
        completion_timing TEXT,
        UNIQUE(run_id, item_id, phase)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_skill_loop_steps_run ON skill_loop_step_results(run_id, phase)",
    """
    CREATE TABLE IF NOT EXISTS skill_loop_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_name TEXT NOT NULL,
        user_id INTEGER,
        run_id INTEGER,
        item_id TEXT,
        payload_json TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_skill_loop_events_name ON skill_loop_events(event_name, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_skill_loop_events_user ON skill_loop_events(user_id, created_at)",
]

SCHEMA_TABLES = (
    "skill_loop_skills",
    "skill_loop_items",
    "skill_loop_item_reviews",
    "skill_loop_assignments",
    "skill_loop_runs",
    "skill_loop_step_results",
    "skill_loop_events",
)
SCHEMA_INDEXES = (
    "idx_skill_loop_items_skill_slot",
    "idx_skill_loop_assignments_exp_user",
    "idx_skill_loop_assignments_user",
    "idx_skill_loop_assignments_exp",
    "idx_skill_loop_runs_user_skill",
    "idx_skill_loop_steps_run",
    "idx_skill_loop_events_name",
    "idx_skill_loop_events_user",
)


def assert_sql_is_additive() -> None:
    for sql in SQL_STATEMENTS:
        if FORBIDDEN_SQL.search(sql):
            raise SystemExit("Refusing SQL with DROP/TRUNCATE/DELETE/ALTER:\n" + sql)


def is_forbidden_path(path: str) -> bool:
    abs_path = os.path.abspath(path or "")
    return (
        abs_path.startswith(RENDER_FORBIDDEN)
        or "/var/data/" in abs_path
        or abs_path.endswith("/var/data/sat.db")
        or "/var/data/sat.db" in abs_path
    )


def seed_pack(conn: sqlite3.Connection, pack_path: str = PACK_PATH) -> int:
    with open(pack_path, encoding="utf-8") as fh:
        pack = json.load(fh)
    conn.execute(
        """
        INSERT OR IGNORE INTO skill_loop_skills
            (code, title, microskill_statement, control_lesson_slug, control_practice_url, is_active)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (
            pack["skill_code"],
            pack["title"],
            pack["microskill_statement"],
            (pack.get("control_arm") or {}).get("lesson_slug"),
            (pack.get("control_arm") or {}).get("practice_url"),
        ),
    )
    inserted = 0
    for it in pack.get("items") or []:
        faded = json.dumps(
            {
                "blanks": it.get("blanks") or [],
                "given_steps": it.get("given_steps") or [],
                "light_hint": it.get("light_hint") or "",
                "critical_hint": it.get("critical_hint") or "",
                "core_idea": it.get("core_idea") or "",
                "common_mistake": it.get("common_mistake") or "",
                "explanation_check": it.get("explanation_check") or "",
                "unknown_change": it.get("unknown_change") or "",
            },
            ensure_ascii=False,
        )
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO skill_loop_items (
                id, version, skill_code, slot, variant_index, stem_html, choices_json,
                question_kind, correct_answer, answer_alternates_json, worked_steps_json,
                faded_json, review_status, publish_status, source_note
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', 'unpublished', ?)
            """,
            (
                it["id"],
                it.get("skill_code") or pack["skill_code"],
                it["slot"],
                int(it.get("variant_index") or 1),
                it["stem_html"],
                json.dumps(it.get("choices") or [], ensure_ascii=False),
                it["question_kind"],
                it.get("correct_answer"),
                json.dumps(it.get("answer_alternates") or [], ensure_ascii=False),
                json.dumps(it.get("worked_steps") or [], ensure_ascii=False),
                faded,
                it.get("source_note") or "",
            ),
        )
        inserted += cur.rowcount or 0
        conn.execute(
            """
            UPDATE skill_loop_items
            SET stem_html = ?, choices_json = ?, worked_steps_json = ?, faded_json = ?,
                correct_answer = ?, answer_alternates_json = ?, source_note = ?
            WHERE id = ? AND version = 1 AND review_status = 'draft'
            """,
            (
                it["stem_html"],
                json.dumps(it.get("choices") or [], ensure_ascii=False),
                json.dumps(it.get("worked_steps") or [], ensure_ascii=False),
                faded,
                it.get("correct_answer"),
                json.dumps(it.get("answer_alternates") or [], ensure_ascii=False),
                it.get("source_note") or "",
                it["id"],
            ),
        )
    return inserted


def _print_sql_statements() -> None:
    print("skill_loop_migrate: additive CREATE TABLE IF NOT EXISTS only")
    print("does not modify question_bank.json")
    print()
    for i, sql in enumerate(SQL_STATEMENTS, 1):
        print(f"-- [{i}/{len(SQL_STATEMENTS)}]")
        print(" ".join(sql.split()))
        print()


def _print_schema_only_banner(db_path: str) -> None:
    print("SCHEMA_ONLY")
    print("db=" + os.path.abspath(db_path))
    print(f"statements={len(SQL_STATEMENTS)}")


def _run_sql_statements(db_path: str, *, seed: bool) -> None:
    assert_sql_is_additive()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        for sql in SQL_STATEMENTS:
            conn.execute(sql)
        if seed:
            seed_pack(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_schema(db_path: str, *, allow_render_production: bool = False) -> None:
    """Run the 15 CREATE IF NOT EXISTS statements. Never seeds."""
    if is_forbidden_path(db_path) and not allow_render_production:
        raise SystemExit("ERROR: refusing to touch Render /var/data database")
    _print_schema_only_banner(db_path)
    _run_sql_statements(db_path, seed=False)


def apply(db_path: str) -> None:
    if is_forbidden_path(db_path):
        raise SystemExit("ERROR: refusing to touch Render /var/data database")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        for sql in SQL_STATEMENTS:
            conn.execute(sql)
        seed_pack(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--allow-render-production", action="store_true")
    parser.add_argument("--db")
    args = parser.parse_args()
    assert_sql_is_additive()
    _print_sql_statements()

    if args.allow_render_production and not args.schema_only:
        print("ERROR: --allow-render-production is only valid with --schema-only.", file=sys.stderr)
        return 4
    if args.schema_only and args.apply:
        print("ERROR: --schema-only and --apply are mutually exclusive.", file=sys.stderr)
        return 2

    if args.schema_only:
        if not args.db:
            print("ERROR: --schema-only requires --db.", file=sys.stderr)
            return 2
        if args.dry_run:
            _print_schema_only_banner(args.db)
            print("DRY-RUN complete. No database connection or writes.")
            return 0
        apply_schema(args.db, allow_render_production=args.allow_render_production)
        print("schema-only applied to", os.path.abspath(args.db))
        return 0

    if args.dry_run or not args.apply:
        print("DRY-RUN complete. No database connection or writes.")
        return 0

    if not args.db:
        print("ERROR: --apply requires --db pointing at a local copy.", file=sys.stderr)
        return 2
    if is_forbidden_path(args.db):
        print("ERROR: refusing to touch Render disk path", args.db, file=sys.stderr)
        return 3
    apply(args.db)
    print("applied to", os.path.abspath(args.db))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
