#!/usr/bin/env python3
"""Export users from local sat.db → data/render_users_seed.json (hashes only)."""
from __future__ import annotations

import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "sat.db")
OUT = os.path.join(ROOT, "data", "render_users_seed.json")


def main() -> int:
    if not os.path.isfile(DB):
        print(f"No database at {DB}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    has_grants = "access_grants" in cols
    rows = conn.execute(
        f"""
        SELECT username, password_hash, role, is_active
        {", access_grants" if has_grants else ""}
        FROM users
        WHERE password_hash IS NOT NULL AND password_hash != ''
        ORDER BY id
        """
    ).fetchall()
    conn.close()
    users = []
    for r in rows:
        item = {
            "username": str(r["username"]),
            "password_hash": str(r["password_hash"]),
            "role": str(r["role"] or "student"),
            "is_active": int(r["is_active"] or 0),
        }
        if has_grants and r["access_grants"]:
            item["access_grants"] = str(r["access_grants"])
        users.append(item)
    payload = {
        "_note": "Disaster-recovery seed (password hashes only). Regenerate: python3 scripts/export_users_seed.py",
        "users": users,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    print(f"Wrote {len(payload['users'])} users to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
