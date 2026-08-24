#!/usr/bin/env python3
"""Additive Placement public-access schema. Never touches official banks or users.

Usage:
  python3 scripts/placement_public_migrate.py --dry-run
  python3 scripts/placement_public_migrate.py --schema-only --db /abs/path/to/LOCAL-copy.db
  python3 scripts/placement_public_migrate.py --apply --db /abs/path/to/LOCAL-copy.db

Dry-run prints SQL and does not connect.
--apply / --schema-only refuse /var/data unless --allow-render-production --schema-only.
No seed. No ALTER/DROP/DELETE.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from placement_public import SQL_STATEMENTS, assert_sql_is_additive, ensure_tables  # noqa: E402

RENDER_FORBIDDEN = "/var/data"


def is_forbidden_path(path: str) -> bool:
    abs_path = os.path.abspath(path or "")
    return (
        abs_path.startswith(RENDER_FORBIDDEN)
        or "/var/data/" in abs_path
        or abs_path.endswith("/var/data/sat.db")
        or "/var/data/sat.db" in abs_path
    )


def _print_sql_statements() -> None:
    print("placement_public_migrate: additive CREATE TABLE IF NOT EXISTS only")
    print("does not modify question_bank.json or users")
    print()
    for i, sql in enumerate(SQL_STATEMENTS, 1):
        print(f"-- [{i}/{len(SQL_STATEMENTS)}]")
        print(" ".join(sql.split()))
        print()


def apply_schema(db_path: str, *, allow_render_production: bool = False) -> None:
    if is_forbidden_path(db_path) and not allow_render_production:
        raise SystemExit("ERROR: refusing to touch Render /var/data database")
    print("SCHEMA_ONLY")
    print("db=" + os.path.abspath(db_path))
    print(f"statements={len(SQL_STATEMENTS)}")
    assert_sql_is_additive()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_tables(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply(db_path: str) -> None:
    apply_schema(db_path, allow_render_production=False)


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

    if args.dry_run and not args.apply and not args.schema_only:
        print("DRY-RUN")
        print("no database connection")
        return 0

    if args.apply or args.schema_only:
        if not args.db:
            print("ERROR: --db is required", file=sys.stderr)
            return 2
        if is_forbidden_path(args.db) and not (args.schema_only and args.allow_render_production):
            print("ERROR: refusing to touch Render /var/data database", file=sys.stderr)
            return 3
        apply_schema(args.db, allow_render_production=bool(args.allow_render_production and args.schema_only))
        return 0

    print("Pass --dry-run, or --schema-only/--apply with --db <local-copy>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
