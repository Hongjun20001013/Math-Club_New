#!/usr/bin/env python3
"""Rollback for skill-loop pilot tables only.

Default: print the plan. Will not execute unless --confirm-rollback AND --db
point at a local copy (never /var/data).
"""
from __future__ import annotations

import argparse
import os
import sys

RENDER_FORBIDDEN = "/var/data"


def is_forbidden_path(path: str) -> bool:
    abs_path = os.path.abspath(path or "")
    return (
        abs_path.startswith(RENDER_FORBIDDEN)
        or "/var/data/" in abs_path
        or "/var/data/sat.db" in abs_path
    )

NEW_INDEXES = [
    "idx_skill_loop_items_skill_slot",
    "idx_skill_loop_assignments_exp_user",
    "idx_skill_loop_assignments_user",
    "idx_skill_loop_assignments_exp",
    "idx_skill_loop_runs_user_skill",
    "idx_skill_loop_steps_run",
    "idx_skill_loop_events_name",
    "idx_skill_loop_events_user",
]
NEW_TABLES = [
    "skill_loop_events",
    "skill_loop_step_results",
    "skill_loop_runs",
    "skill_loop_assignments",
    "skill_loop_item_reviews",
    "skill_loop_items",
    "skill_loop_skills",
]


def plan_sql() -> list[str]:
    stmts = [f"DROP INDEX IF EXISTS {name}" for name in NEW_INDEXES]
    stmts.extend(f"DROP TABLE IF EXISTS {name}" for name in NEW_TABLES)
    return stmts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db")
    parser.add_argument("--confirm-rollback", action="store_true")
    args = parser.parse_args()
    stmts = plan_sql()
    print("Rollback plan (skill-loop NEW objects only):")
    for s in stmts:
        print(" ", s)
    if not args.confirm_rollback:
        print("DRY plan only. Pass --confirm-rollback --db <local-copy> to execute.")
        return 0
    if not args.db:
        print("ERROR: --db required", file=sys.stderr)
        return 2
    if is_forbidden_path(args.db):
        print("ERROR: refusing /var/data", file=sys.stderr)
        return 3
    import sqlite3

    conn = sqlite3.connect(args.db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        for s in stmts:
            conn.execute(s)
        conn.commit()
        print("dropped skill-loop objects on", os.path.abspath(args.db))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
