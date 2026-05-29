from __future__ import annotations
from answer_grader import grade_for_db, response_is_correct
from latex_parser import parse_placement_tex_file, parse_tex_file

import json
import glob
import os
import random
import re
import secrets
import shutil
import sqlite3
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from placement_report_pdf import build_placement_parent_pdf

# =====================================================
# BASIC CONFIG
# =====================================================

APP_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(APP_DIR, ".env"))

# SQLite file. Default: sat.db next to this app. For Render (or similar), mount a
# persistent disk and set DB_PATH to an absolute path on that volume, e.g.
#   /var/data/sat.db
# Otherwise redeploys / restarts may reset the container filesystem.
RENDER_PERSISTENT_DB_DIR = "/var/data"
LEGACY_EPHEMERAL_DB_PATH = os.path.join(APP_DIR, "sat.db")


def _is_render_runtime() -> bool:
    return os.environ.get("RENDER", "").lower() in ("true", "1", "yes")


def _resolve_db_path() -> str:
    db_env = os.environ.get("DB_PATH", "").strip()
    if db_env:
        return db_env if os.path.isabs(db_env) else os.path.normpath(os.path.join(APP_DIR, db_env))
    if _is_render_runtime():
        return os.path.join(RENDER_PERSISTENT_DB_DIR, "sat.db")
    return LEGACY_EPHEMERAL_DB_PATH


DB_PATH = _resolve_db_path()
SEED_USERS_PATH = os.path.join(APP_DIR, "data", "render_users_seed.json")
RENDER_BACKUP_DIR = os.path.join(RENDER_PERSISTENT_DB_DIR, "backups")
RENDER_SEED_SNAPSHOT_PATH = os.path.join(RENDER_BACKUP_DIR, "users_seed_latest.json")
BACKUP_INTERVAL_SECONDS = 4 * 3600
BACKUP_KEEP_COUNT = 30
BACKUP_AFTER_WRITE_SECONDS = 3600

COMPILED_BANK_PATH = os.path.join(APP_DIR, "data", "question_bank.json")
COURSE_MATERIALS_PATH = os.path.join(APP_DIR, "data", "course_materials.json")
COURSE_MATERIALS_MANIFEST_PATH = os.path.join(APP_DIR, "data", "course_materials_manifest.json")
PLACEMENT_META_PATH = os.path.join(APP_DIR, "data", "placement_meta.json")
DESMOS_API_KEY = os.environ.get("DESMOS_API_KEY", "").strip()
COMPILED_BANK_CACHE = None
COURSE_MATERIALS_CACHE = None

STATIC_DIR = os.path.join(APP_DIR, "static")
TEMPLATES_DIR = os.path.join(APP_DIR, "templates")
app = Flask(
    __name__,
    root_path=APP_DIR,
    static_folder=STATIC_DIR,
    template_folder=TEMPLATES_DIR,
)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("RENDER", "").lower() in ("true", "1", "yes"),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)

LOGIN_ATTEMPTS: dict[str, List[float]] = {}

# Bump when bundled CSS changes. Optional env override per environment.
STYLE_CSS_REVISION = os.environ.get("STYLE_CSS_REVISION", "20260528-course-materials-v17")


def _site_brand_name() -> str:
    return (os.environ.get("SITE_BRAND_NAME") or "Novel Prep Math Studio").strip() or "Novel Prep Math Studio"


SITE_BRAND_NAME = _site_brand_name()
SITE_BRAND_SHORT = (os.environ.get("SITE_BRAND_SHORT") or "Novel Prep").strip() or "Novel Prep"
SITE_META_DESCRIPTION = (
    os.environ.get("SITE_META_DESCRIPTION")
    or f"{SITE_BRAND_NAME} — SAT Math practice (Units 1–4), course placement, mistake analytics, and a unified workspace."
).strip()
SITE_LOGIN_KICKER = (
    os.environ.get("SITE_LOGIN_KICKER") or f"{SITE_BRAND_SHORT} · SAT Math Studio"
).strip()
SITE_TEACHER_LABEL = (os.environ.get("SITE_TEACHER_LABEL") or "Novel Prep").strip()
SITE_SUPPORT_CONTACT = (
    os.environ.get("SITE_SUPPORT_CONTACT") or SITE_TEACHER_LABEL
).strip()
SITE_ADMIN_KICKER = (os.environ.get("SITE_ADMIN_KICKER") or f"{SITE_BRAND_SHORT} Admin").strip()
SITE_FOOTER_TAGLINE = (
    os.environ.get("SITE_FOOTER_TAGLINE") or "Practice · placement · analytics"
).strip()


def _site_branding_context() -> dict[str, str]:
    return {
        "site_brand_name": SITE_BRAND_NAME,
        "site_brand_short": SITE_BRAND_SHORT,
        "site_meta_description": SITE_META_DESCRIPTION,
        "site_login_kicker": SITE_LOGIN_KICKER,
        "site_teacher_label": SITE_TEACHER_LABEL,
        "site_support_contact": SITE_SUPPORT_CONTACT,
        "site_admin_kicker": SITE_ADMIN_KICKER,
        "site_footer_tagline": SITE_FOOTER_TAGLINE,
    }


def _verify_style_bundle_best_effort() -> None:
    """Warn if style.css is missing or far smaller than the full Studio bundle."""
    try:
        p = os.path.join(STATIC_DIR, "style.css")
        sz = os.path.getsize(p)
        if sz < 300_000:
            app.logger.warning("style.css looks too small (%s bytes); layout may be broken.", sz)
    except OSError:
        app.logger.warning("style.css missing under %s", STATIC_DIR)


_verify_style_bundle_best_effort()


def _production_config_guard() -> None:
    """Warn when obvious secrets misconfiguration on Render."""
    if not _is_render_runtime():
        return
    sk = os.environ.get("SECRET_KEY", "").strip()
    if not sk or sk == "dev-secret-change-me":
        app.logger.warning(
            "SECRET_KEY is missing or still the dev default on Render. "
            "Set SECRET_KEY in Environment or use generateValue in render.yaml."
        )


def _path_on_render_disk(path: str) -> bool:
    """True when path lives on a mounted volume (Render persistent disk), not ephemeral FS."""
    if not _is_render_runtime():
        return True
    abs_path = os.path.abspath(path)
    persistent_root = os.path.abspath(RENDER_PERSISTENT_DB_DIR)
    if not (abs_path == persistent_root or abs_path.startswith(persistent_root + os.sep)):
        return False
    try:
        with open("/proc/mounts", "r", encoding="utf-8") as mounts:
            for line in mounts:
                parts = line.split()
                if len(parts) < 2:
                    continue
                mount_point = parts[1]
                if mount_point in ("/", ""):
                    continue
                if abs_path == mount_point or abs_path.startswith(mount_point.rstrip("/") + os.sep):
                    return True
    except OSError:
        pass
    return False


def _sqlite_db_stats(db_path: str) -> dict[str, int]:
    stats = {"user_count": 0, "admin_count": 0, "attempt_count": 0}
    if not os.path.isfile(db_path):
        return stats
    try:
        conn = sqlite3.connect(db_path)
        stats["user_count"] = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        stats["admin_count"] = int(
            conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
            ).fetchone()[0]
        )
        try:
            stats["attempt_count"] = int(
                conn.execute("SELECT COUNT(*) FROM practice_attempts").fetchone()[0]
            )
        except sqlite3.Error:
            stats["attempt_count"] = 0
        conn.close()
    except sqlite3.Error:
        stats["user_count"] = -1
    return stats


def _backup_marker_path() -> str:
    return os.path.join(RENDER_BACKUP_DIR, ".last_backup")


def _list_render_db_backups() -> list[str]:
    if not os.path.isdir(RENDER_BACKUP_DIR):
        return []
    return sorted(glob.glob(os.path.join(RENDER_BACKUP_DIR, "sat-*.db")))


def _latest_backup_path() -> str | None:
    backups = _list_render_db_backups()
    return backups[-1] if backups else None


def _last_backup_timestamp() -> float | None:
    marker = _backup_marker_path()
    if os.path.isfile(marker):
        try:
            return os.path.getmtime(marker)
        except OSError:
            pass
    backups = _list_render_db_backups()
    if backups:
        try:
            return os.path.getmtime(backups[-1])
        except OSError:
            pass
    return None


def _sqlite_backup_file(src_path: str, dest_path: str) -> None:
    """Hot backup via SQLite API (safe while the app holds the DB open)."""
    parent = os.path.dirname(dest_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    src = sqlite3.connect(f"file:{os.path.abspath(src_path)}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(dest_path)
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()


def _db_persistence_status() -> dict[str, Any]:
    """Report whether SQLite lives on a volume that survives redeploys."""
    db_path = os.path.abspath(DB_PATH)
    dir_path = os.path.dirname(db_path)
    on_render = _is_render_runtime()
    on_persistent_volume = _path_on_render_disk(db_path)
    dir_exists = os.path.isdir(dir_path)
    db_exists = os.path.isfile(db_path)
    writable = False
    if dir_exists:
        probe = os.path.join(dir_path, ".np_db_write_probe")
        try:
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("ok")
            os.remove(probe)
            writable = True
        except OSError:
            writable = False

    stats = _sqlite_db_stats(db_path) if db_exists else _sqlite_db_stats("")
    backups = _list_render_db_backups()
    last_backup_ts = _last_backup_timestamp()
    persistence_ok = (not on_render) or (on_persistent_volume and dir_exists and writable)

    return {
        "db_path": db_path,
        "on_render": on_render,
        "on_persistent_volume": on_persistent_volume,
        "dir_exists": dir_exists,
        "db_exists": db_exists,
        "writable": writable,
        "user_count": stats["user_count"],
        "admin_count": stats["admin_count"],
        "attempt_count": stats["attempt_count"],
        "persistence_ok": persistence_ok,
        "backup_count": len(backups),
        "last_backup_at": (
            datetime.utcfromtimestamp(last_backup_ts).strftime("%Y-%m-%dT%H:%M:%SZ")
            if last_backup_ts
            else None
        ),
        "seed_snapshot_exists": os.path.isfile(RENDER_SEED_SNAPSHOT_PATH),
        "legacy_ephemeral_exists": (
            os.path.isfile(LEGACY_EPHEMERAL_DB_PATH)
            and os.path.abspath(LEGACY_EPHEMERAL_DB_PATH) != db_path
        ),
    }



def _try_restore_from_render_backups() -> None:
    """If the live DB lost accounts, restore the newest on-disk backup."""
    target = os.path.abspath(DB_PATH)
    live_stats = _sqlite_db_stats(target)
    if live_stats["admin_count"] > 0:
        return
    if not os.path.isdir(RENDER_BACKUP_DIR):
        return
    for path in reversed(_list_render_db_backups()):
        backup_stats = _sqlite_db_stats(path)
        if backup_stats["admin_count"] <= 0 and backup_stats["user_count"] <= 0:
            continue
        if live_stats["user_count"] > 0 and backup_stats["user_count"] <= live_stats["user_count"]:
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(path, target)
        app.logger.warning(
            "Restored SQLite database from backup %s (users %s→%s, attempts %s→%s)",
            path,
            live_stats["user_count"],
            backup_stats["user_count"],
            live_stats["attempt_count"],
            backup_stats["attempt_count"],
        )
        return


def _backup_database_now(
    *,
    force: bool = False,
    min_interval_seconds: int = BACKUP_INTERVAL_SECONDS,
) -> str | None:
    """Write a timestamped SQLite snapshot on the Render persistent disk."""
    if not _is_render_runtime() or not _path_on_render_disk(DB_PATH) or not os.path.isfile(DB_PATH):
        return None
    os.makedirs(RENDER_BACKUP_DIR, exist_ok=True)
    marker = _backup_marker_path()
    now = time.time()
    if not force and _last_backup_timestamp() is not None:
        if now - _last_backup_timestamp() < min_interval_seconds:
            return None
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dest = os.path.join(RENDER_BACKUP_DIR, f"sat-{stamp}.db")
    db = g.pop("db", None)
    if db is not None:
        db.commit()
        db.close()
    _sqlite_backup_file(DB_PATH, dest)
    with open(marker, "w", encoding="utf-8") as fh:
        fh.write(stamp)
    backups = _list_render_db_backups()
    for old in backups[:-BACKUP_KEEP_COUNT]:
        try:
            os.remove(old)
        except OSError:
            pass
    app.logger.info("SQLite backup saved to %s", dest)
    return dest


def _maybe_auto_backup_database() -> None:
    """Periodic snapshot on Render persistent disk (survives redeploys)."""
    _backup_database_now(force=False, min_interval_seconds=BACKUP_INTERVAL_SECONDS)


def _users_seed_payload_from_db(db: sqlite3.Connection) -> dict[str, Any]:
    rows = db.execute(
        """
        SELECT username, password_hash, role, is_active, access_grants
        FROM users
        WHERE password_hash IS NOT NULL AND password_hash != ''
        ORDER BY id
        """
    ).fetchall()
    return {
        "_note": "Live account snapshot (password hashes only). Auto-written on Render.",
        "users": [
            {
                "username": str(row["username"]),
                "password_hash": str(row["password_hash"]),
                "role": str(row["role"] or ROLE_STUDENT),
                "is_active": int(row["is_active"] or 0),
                **(
                    {"access_grants": str(row["access_grants"])}
                    if row["access_grants"]
                    else {}
                ),
            }
            for row in rows
        ],
    }


def _write_users_seed_file(path: str, payload: dict[str, Any]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def _sync_render_users_seed_snapshot(db: sqlite3.Connection | None = None) -> None:
    """Keep a hash-only account snapshot on the persistent disk (second recovery path)."""
    if not _is_render_runtime() or not _path_on_render_disk(DB_PATH):
        return
    close_after = False
    if db is None:
        if not os.path.isfile(DB_PATH):
            return
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        db = conn
        close_after = True
    try:
        payload = _users_seed_payload_from_db(db)
        if not payload["users"]:
            return
        _write_users_seed_file(RENDER_SEED_SNAPSHOT_PATH, payload)
    finally:
        if close_after:
            db.close()


def _seed_users_sources() -> list[str]:
    paths: list[str] = []
    if os.path.isfile(RENDER_SEED_SNAPSHOT_PATH):
        paths.append(RENDER_SEED_SNAPSHOT_PATH)
    if os.path.isfile(SEED_USERS_PATH):
        paths.append(SEED_USERS_PATH)
    return paths


def _backup_after_account_change(db: sqlite3.Connection) -> None:
    _sync_render_users_seed_snapshot(db)
    _backup_database_now(force=False, min_interval_seconds=BACKUP_AFTER_WRITE_SECONDS)


def _seed_users_if_empty(db: sqlite3.Connection) -> None:
    """Restore known accounts when Render DB was wiped (hashes only, no plaintext passwords)."""
    if _admin_exists(db):
        return
    for seed_path in _seed_users_sources():
        try:
            with open(seed_path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        users = payload.get("users") or []
        if not isinstance(users, list):
            continue
        inserted = 0
        for row in users:
            if not isinstance(row, dict):
                continue
            username = str(row.get("username") or "").strip()
            password_hash = str(row.get("password_hash") or "").strip()
            if not username or not password_hash:
                continue
            role = str(row.get("role") or ROLE_STUDENT)
            is_active = int(row.get("is_active") or 1)
            access_grants = row.get("access_grants")
            grants_sql = str(access_grants).strip() if access_grants else None
            try:
                db.execute(
                    """
                    INSERT INTO users (
                        username, password, password_hash, role, is_active,
                        access_grants, created_at, password_changed_at
                    )
                    VALUES (?, '', ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (username, password_hash, role, is_active, grants_sql),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass
        if inserted:
            db.commit()
            app.logger.warning(
                "Seeded %s account(s) from %s after missing admin.",
                inserted,
                seed_path,
            )
            _sync_render_users_seed_snapshot(db)
            return


def _maybe_migrate_ephemeral_db() -> None:
    """One-time copy if accounts were created before persistent disk was configured."""
    legacy = os.path.abspath(LEGACY_EPHEMERAL_DB_PATH)
    target = os.path.abspath(DB_PATH)
    if legacy == target or os.path.isfile(target) or not os.path.isfile(legacy):
        return
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(legacy, target)
    app.logger.warning("Copied legacy SQLite database from %s to %s", legacy, target)


def _bootstrap_db_storage() -> None:
    parent = os.path.dirname(os.path.abspath(DB_PATH))
    if parent:
        os.makedirs(parent, exist_ok=True)
    _maybe_migrate_ephemeral_db()
    _try_restore_from_render_backups()
    status = _db_persistence_status()
    if status["on_render"] and not status["persistence_ok"]:
        app.logger.error(
            "SQLite is not on a persistent Render disk (path=%s). "
            "Add a disk mounted at /var/data and set DB_PATH=/var/data/sat.db "
            "or accounts will disappear after each deploy.",
            status["db_path"],
        )


_production_config_guard()
_bootstrap_db_storage()

# =====================================================
# DATABASE
# =====================================================

def get_db() -> sqlite3.Connection:
    if "db" not in g:
        parent = os.path.dirname(os.path.abspath(DB_PATH))
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _table_columns(db: sqlite3.Connection, table: str) -> List[str]:
    cur = db.execute(f"PRAGMA table_info({table})")
    return [str(r[1]) for r in cur.fetchall()]


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS practice_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            domain TEXT NOT NULL,
            topic TEXT NOT NULL,
            qnum INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS practice_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            selected_answer TEXT NOT NULL,
            correct_answer TEXT,
            is_correct INTEGER,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (attempt_id) REFERENCES practice_attempts (id)
        );
        """
    )
    user_cols = _table_columns(db, "users")
    if "password_hash" not in user_cols:
        db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    if "role" not in user_cols:
        db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'student'")
    if "is_active" not in user_cols:
        db.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    if "created_at" not in user_cols:
        db.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
        db.execute(
            "UPDATE users SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP)"
        )
    if "last_login_at" not in user_cols:
        db.execute("ALTER TABLE users ADD COLUMN last_login_at TEXT")
    if "password_changed_at" not in user_cols:
        db.execute("ALTER TABLE users ADD COLUMN password_changed_at TEXT")
    if "access_scope" not in user_cols:
        db.execute(
            "ALTER TABLE users ADD COLUMN access_scope TEXT NOT NULL DEFAULT 'full'"
        )
    user_cols = _table_columns(db, "users")
    if "access_grants" not in user_cols:
        db.execute("ALTER TABLE users ADD COLUMN access_grants TEXT")
        # Migrate legacy single-scope column into JSON grants when present.
        if "access_scope" in user_cols:
            for scope, grants_json in (
                ("sat", '["sat"]'),
                ("placement", '["placement"]'),
                ("full", None),
            ):
                if grants_json:
                    db.execute(
                        "UPDATE users SET access_grants = ? WHERE access_scope = ? AND (access_grants IS NULL OR access_grants = '')",
                        (grants_json, scope),
                    )
    cols = _table_columns(db, "practice_responses")
    if "question_index" not in cols:
        db.execute("ALTER TABLE practice_responses ADD COLUMN question_index INTEGER")
    if "mistake_tags" not in cols:
        db.execute("ALTER TABLE practice_responses ADD COLUMN mistake_tags TEXT")
    if "mistake_note" not in cols:
        db.execute("ALTER TABLE practice_responses ADD COLUMN mistake_note TEXT")
    att_cols = _table_columns(db, "practice_attempts")
    if "placement_student_name" not in att_cols:
        db.execute(
            "ALTER TABLE practice_attempts ADD COLUMN placement_student_name TEXT"
        )
    if "placement_student_grade" not in att_cols:
        db.execute(
            "ALTER TABLE practice_attempts ADD COLUMN placement_student_grade TEXT"
        )
    if "placement_student_math_course" not in att_cols:
        db.execute(
            "ALTER TABLE practice_attempts ADD COLUMN placement_student_math_course TEXT"
        )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS mistake_learning_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            learner_key TEXT NOT NULL,
            domain TEXT NOT NULL,
            topic TEXT NOT NULL,
            question_index INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'unreviewed',
            correct_after_last_wrong INTEGER NOT NULL DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(learner_key, domain, topic, question_index)
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_mistake_progress_learner "
        "ON mistake_learning_progress(learner_key)"
    )
    _seed_users_if_empty(db)
    _sync_render_users_seed_snapshot(db)
    _maybe_auto_backup_database()
    db.commit()


@app.before_request
def ensure_db_initialized():
    if request.endpoint in ("health", "health_db", "health_stylesheet_bundle"):
        return
    init_db()


@app.before_request
def redirect_legacy_unit2_under_algebra():
    """Unit 2 now lives under domain advanced_math, not algebra."""
    p = request.path or ""
    prefix = "/practice/algebra/"
    if not p.startswith(prefix):
        return None
    tail = p[len(prefix) :]
    if tail.startswith("unit_2") or tail.startswith("2_"):
        return redirect("/practice/advanced_math/" + tail, code=301)
    return None


@app.context_processor
def inject_template_config():
    track_lookup = {t["key"]: t for t in LEARNING_TRACKS}
    active_track = session.get("active_track_label", "Platform")
    p = request.path or "/"
    if p == "/":
        active_track = "Platform"
    elif p.startswith("/practice"):
        active_track = "SAT Math"
    elif p.startswith("/placement"):
        active_track = "Course placement"
    elif p.startswith("/learn/"):
        k = p.split("/learn/", 1)[1].split("/", 1)[0]
        active_track = track_lookup.get(k, {}).get("title", "Platform")

    # MathJax is heavy (~hundreds of KB); skip on mostly-static pages to reduce jank.
    load_mathjax = not (
        p.startswith("/practice/analytics")
        or p.startswith("/admin")
        or p in ("/", "")
        or p.startswith("/login")
        or p.startswith("/register")
    )

    grants = current_user_access_grants()
    visible_tracks = []
    for t in LEARNING_TRACKS:
        key = t.get("key")
        if grants is None:
            visible_tracks.append(t)
            continue
        if key == "sat" and "sat" in grants:
            visible_tracks.append(t)
        elif key == "placement" and "placement" in grants:
            visible_tracks.append(t)
    nav_show_dashboard = grants is None or "dashboard" in grants
    nav_show_workspace = grants is None or "sat" in grants
    nav_show_analytics = grants is None or "sat" in grants
    student_home_href = url_for("index") if grants is None else _student_home_url(grants)

    show_np_desmos = bool(
        DESMOS_API_KEY
        and p.startswith("/practice")
        and not p.startswith("/practice/analytics")
    )

    return {
        "desmos_api_key": DESMOS_API_KEY,
        "show_np_desmos": show_np_desmos,
        "np_desmos_shortcut": True,
        "active_track_label": active_track,
        "nav_path": p,
        "learning_tracks": visible_tracks if grants is not None else LEARNING_TRACKS,
        "student_access_grants": grants,
        "student_access_grants_label": _access_grants_label(session.get("user_access_grants")),
        "student_resource_grant_options": STUDENT_RESOURCE_GRANTS,
        "student_has_full_access": grants is None,
        "nav_show_dashboard": nav_show_dashboard,
        "nav_show_workspace": nav_show_workspace,
        "nav_show_analytics": nav_show_analytics,
        "student_home_href": student_home_href,
        "user_logged_in": "user_id" in session,
        "user_is_admin": current_user_can_access_admin(),
        "user_is_supervisor": current_user_is_supervisor(),
        "user_can_access_admin": current_user_can_access_admin(),
        "current_user_role": current_user_role(),
        "load_mathjax": load_mathjax,
        "style_css_revision": STYLE_CSS_REVISION,
        **_site_branding_context(),
    }


def require_login() -> bool:
    return "user_id" in session


ROLE_ADMIN = "admin"
ROLE_STAFF = "staff"
ROLE_STUDENT = "student"
STAFF_ROLES = frozenset({ROLE_ADMIN, ROLE_STAFF})

STUDENT_RESOURCE_GRANTS: tuple[dict[str, str], ...] = (
    {
        "key": "dashboard",
        "label": "Home dashboard",
        "description": "Track catalog, overview, and navigation hub",
        "home_href": "/",
    },
    {
        "key": "sat",
        "label": "SAT Math",
        "description": "Units 1–4, Hard Drill, workspace & mistake analytics",
        "home_href": "/practice",
    },
    {
        "key": "placement",
        "label": "Course placement",
        "description": "70-item placement diagnostic & PDF report",
        "home_href": "/placement",
    },
)
STUDENT_GRANT_KEYS = frozenset(g["key"] for g in STUDENT_RESOURCE_GRANTS)
SAT_STUDENT_DOMAINS = frozenset(
    {"algebra", "advanced_math", "problem_solving", "geometry", "hard_problem"}
)
_PRACTICE_PATH_DOMAIN_RE = re.compile(r"^/practice/(?P<dom>[^/]+)")
_SESSION_ATTEMPT_RE = re.compile(r"^/practice/session/(?P<aid>\d+)")


def _grants_full_access(raw: Any) -> bool:
    if raw is None:
        return True
    if isinstance(raw, str):
        s = raw.strip()
        if not s or s in ("*", "all", "full"):
            return True
        try:
            parsed = json.loads(s)
        except (json.JSONDecodeError, TypeError):
            if s == ACCESS_SCOPE_FULL:
                return True
            if s in STUDENT_GRANT_KEYS:
                return False
            return True
        raw = parsed
    if isinstance(raw, (list, tuple, set)):
        keys = {str(x).strip() for x in raw if str(x).strip()}
        if not keys or "all" in keys or "*" in keys:
            return True
        return False
    return True


def _normalize_access_grants(raw: Any) -> set[str] | None:
    """None = unrestricted (all materials). Otherwise a set of grant keys."""
    if _grants_full_access(raw):
        return None
    if isinstance(raw, str):
        s = raw.strip()
        if s == ACCESS_SCOPE_SAT:
            return {"sat"}
        if s == ACCESS_SCOPE_PLACEMENT:
            return {"placement"}
        try:
            parsed = json.loads(s)
        except (json.JSONDecodeError, TypeError):
            return None
        raw = parsed
    if isinstance(raw, (list, tuple, set)):
        keys = {str(x).strip() for x in raw if str(x).strip() in STUDENT_GRANT_KEYS}
        return keys or None
    return None


def _access_grants_from_form(values: Any) -> str | None:
    """Serialize admin checkbox list; None stored as NULL (= full access)."""
    if not values:
        return None
    if isinstance(values, str):
        values = [values]
    keys = []
    for v in values:
        k = str(v).strip()
        if k == "all":
            return None
        if k in STUDENT_GRANT_KEYS and k not in keys:
            keys.append(k)
    if not keys:
        return None
    return json.dumps(keys)


def _access_grants_label(raw: Any) -> str:
    grants = _normalize_access_grants(raw)
    if grants is None:
        return "All materials"
    labels = []
    lookup = {g["key"]: g["label"] for g in STUDENT_RESOURCE_GRANTS}
    for g in STUDENT_RESOURCE_GRANTS:
        if g["key"] in grants:
            labels.append(lookup[g["key"]])
    return ", ".join(labels) if labels else "All materials"


def current_user_access_grants() -> set[str] | None:
    if current_user_can_access_admin():
        return None
    return _normalize_access_grants(session.get("user_access_grants"))


def student_has_grant(grant_key: str) -> bool:
    grants = current_user_access_grants()
    if grants is None:
        return True
    return grant_key in grants


def _student_home_url(grants: set[str] | None) -> str:
    if grants is None:
        return url_for("index")
    for spec in STUDENT_RESOURCE_GRANTS:
        if spec["key"] in grants:
            return spec["home_href"]
    return url_for("index")


def _practice_domain_from_path(path: str) -> str | None:
    m = _PRACTICE_PATH_DOMAIN_RE.match(path or "")
    if not m:
        return None
    dom = m.group("dom")
    if dom in (
        "specialized",
        "challenge",
        "analytics",
        "exams",
        "submit",
        "miss-quiz",
        "mistake-redo",
        "session",
        "challenge",
    ):
        return None
    return dom


def _domain_allowed_by_grants(domain: str, grants: set[str] | None) -> bool:
    if grants is None:
        return True
    if domain == "placement":
        return "placement" in grants
    if domain in SAT_STUDENT_DOMAINS:
        return "sat" in grants
    return False


def _path_allowed_for_grants(path: str, grants: set[str] | None, db: sqlite3.Connection) -> bool:
    if grants is None:
        return True
    p = (path or "/").split("?")[0].rstrip("/") or "/"

    if p.startswith("/admin"):
        return False
    if p == "/guide" or p.startswith("/guide/"):
        return True
    if p == "/logout":
        return True

    if p == "/" or p.startswith("/#"):
        return "dashboard" in grants

    if p.startswith("/learn/"):
        return False

    if p.startswith("/placement"):
        return "placement" in grants

    if p.startswith("/practice"):
        dom = _practice_domain_from_path(p)
        if dom:
            return _domain_allowed_by_grants(dom, grants)
        if p.startswith("/practice/analytics") or p.startswith("/practice/miss-quiz"):
            return "sat" in grants
        if p.startswith("/practice/challenge/materials"):
            return "sat" in grants
        if p.startswith("/practice/specialized"):
            return "sat" in grants
        if p.startswith("/practice/exams"):
            return "sat" in grants
        if p.startswith("/practice/challenge"):
            return "sat" in grants
        if p == "/practice":
            return "sat" in grants
        m = _SESSION_ATTEMPT_RE.match(p)
        if m:
            att = db.execute(
                "SELECT domain FROM practice_attempts WHERE id = ? AND user_id = ?",
                (int(m.group("aid")), session.get("user_id")),
            ).fetchone()
            if att is None:
                return True
            return _domain_allowed_by_grants(str(att["domain"]), grants)
        return "sat" in grants or "placement" in grants

    return False


def _enforce_student_resource_access(db: sqlite3.Connection):
    if current_user_can_access_admin():
        return None
    row = db.execute(
        "SELECT access_grants, access_scope FROM users WHERE id = ?",
        (session.get("user_id"),),
    ).fetchone()
    raw = row["access_grants"] if row else None
    if raw is None and row and row["access_scope"]:
        raw = row["access_scope"]
    grants = _normalize_access_grants(raw)
    session["user_access_grants"] = raw
    path = request.path or "/"
    if _path_allowed_for_grants(path, grants, db):
        return None
    flash("Your account does not include access to this section. Contact your instructor.")
    return redirect(_student_home_url(grants))


# Legacy aliases kept for any in-flight references
ACCESS_SCOPE_FULL = "full"
ACCESS_SCOPE_SAT = "sat"
ACCESS_SCOPE_PLACEMENT = "placement"


def current_user_role() -> str:
    return str(session.get("user_role") or ROLE_STUDENT)


def current_user_is_supervisor() -> bool:
    """Site owner / lead teacher — full admin powers including staff accounts."""
    return current_user_role() == ROLE_ADMIN


def current_user_can_access_admin() -> bool:
    """Supervisor or colleague — student data & account management."""
    return current_user_role() in STAFF_ROLES


def current_user_is_admin() -> bool:
    """Backward-compatible alias used in templates for admin nav visibility."""
    return current_user_can_access_admin()


def _admin_exists(db: sqlite3.Connection) -> bool:
    row = db.execute(
        "SELECT 1 FROM users WHERE role = 'admin' AND is_active = 1 LIMIT 1"
    ).fetchone()
    return row is not None


def _password_matches(user: sqlite3.Row, password: str) -> bool:
    password_hash = str(user["password_hash"] or "")
    if password_hash and check_password_hash(password_hash, password):
        return True

    # Backward compatibility for existing local accounts created before hashing.
    legacy_password = str(user["password"] or "")
    return bool(legacy_password and legacy_password == password)


def _login_throttle_key(username: str) -> str:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    return f"{ip}|{username.lower()}"


def _login_is_throttled(username: str) -> bool:
    key = _login_throttle_key(username)
    now = time.time()
    recent = [t for t in LOGIN_ATTEMPTS.get(key, []) if now - t < 10 * 60]
    LOGIN_ATTEMPTS[key] = recent
    return len(recent) >= 8


def _record_failed_login(username: str) -> None:
    key = _login_throttle_key(username)
    now = time.time()
    recent = [t for t in LOGIN_ATTEMPTS.get(key, []) if now - t < 10 * 60]
    recent.append(now)
    LOGIN_ATTEMPTS[key] = recent


def _clear_failed_logins(username: str) -> None:
    LOGIN_ATTEMPTS.pop(_login_throttle_key(username), None)


def _set_login_session(user: sqlite3.Row) -> None:
    session.clear()
    session.permanent = True
    session["user_id"] = int(user["id"])
    session["username"] = str(user["username"])
    session["user_role"] = str(user["role"] or "student")
    try:
        session["user_access_grants"] = user["access_grants"]
    except (KeyError, IndexError, TypeError):
        session["user_access_grants"] = None


def _require_staff_response():
    if not require_login():
        return redirect(url_for("login", next=request.full_path or request.path))
    if not current_user_can_access_admin():
        abort(403)
    return None


def _require_supervisor_response():
    if not require_login():
        return redirect(url_for("login", next=request.full_path or request.path))
    if not current_user_is_supervisor():
        abort(403)
    return None


def _require_admin_response():
    """Legacy name — most admin routes allow staff; use _require_supervisor_response for owner-only."""
    return _require_staff_response()


@app.before_request
def require_authenticated_user():
    endpoint = request.endpoint or ""
    if endpoint in {
        "static",
        "health",
        "health_stylesheet_bundle",
        "login",
        "logout",
        "admin_setup",
        "student_guide",
    }:
        return None

    if endpoint == "":
        return None

    if "user_id" not in session:
        return redirect(url_for("login", next=request.full_path or request.path))

    db = get_db()
    user = db.execute(
        "SELECT username, role, is_active, access_grants, access_scope FROM users WHERE id = ?",
        (session.get("user_id"),),
    ).fetchone()
    if user is None or int(user["is_active"] or 0) != 1:
        session.clear()
        flash("Please sign in again.")
        return redirect(url_for("login"))
    session["username"] = str(user["username"])
    session["user_role"] = str(user["role"] or "student")
    session["user_access_grants"] = user["access_grants"]
    gate = _enforce_student_resource_access(db)
    if gate is not None:
        return gate

    return None


def extract_correct_answer(question: dict) -> str | None:
    """
    Canonical key from compiled question (MCQ letter or SPR value), or None.
    """
    direct_key = question.get("correct_answer") or question.get("answer") or question.get("key")
    if direct_key is None:
        for index_field in ("answer_index", "correct_index"):
            idx = question.get(index_field)
            if isinstance(idx, int) and 0 <= idx < 4:
                return "ABCD"[idx]
        return None
    s = str(direct_key).strip()
    return s if s else None


def _load_placement_meta_file() -> dict:
    if not os.path.isfile(PLACEMENT_META_PATH):
        return {}
    try:
        with open(PLACEMENT_META_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _placement_tier_for_course_key(course_key: str) -> int:
    return {
        "algebra_i": 1,
        "geometry": 2,
        "algebra_ii": 3,
        "precalculus": 4,
        "calculus_readiness": 5,
    }.get(course_key, 2)


def _placement_course_recommendation(score_pct: int, meta: dict) -> dict | None:
    for row in meta.get("rubric", []):
        if not isinstance(row, dict):
            continue
        lo = int(row.get("min_percent", 0))
        hi = int(row.get("max_percent", 100))
        if lo <= score_pct <= hi:
            return row
    return None


def _enrich_placement_rec(row: dict, raw_score: int, total_q: int) -> dict:
    out = dict(row)
    lo = int(out.get("min_score", 0))
    hi = int(out.get("max_score", total_q or 70))
    out["band_range"] = f"{lo}-{hi}"
    out["raw_score"] = raw_score
    out["total_q"] = total_q
    ck = str(out.get("course_key") or "")
    out["tier"] = int(out.get("tier") or _placement_tier_for_course_key(ck))
    if not isinstance(out.get("highlights"), list):
        out["highlights"] = []
    return out


def _placement_recommendation(meta: dict, raw_score: int, total_q: int) -> dict | None:
    """Prefer total-score bands (out of 70); fall back to percent rubric."""
    for row in meta.get("score_band_rubric") or []:
        if not isinstance(row, dict):
            continue
        lo = int(row.get("min_score", -1))
        hi = int(row.get("max_score", 999))
        if lo <= raw_score <= hi:
            return _enrich_placement_rec(row, raw_score, total_q)
    if total_q > 0:
        pct = round(100.0 * raw_score / total_q)
        fb = _placement_course_recommendation(pct, meta)
        if isinstance(fb, dict):
            out = dict(fb)
            out.setdefault("title", "Course recommendation")
            out.setdefault("headline", "Estimated placement (percent fallback)")
            out["band_range"] = "-"
            out["raw_score"] = raw_score
            out["total_q"] = total_q
            out["tier"] = int(
                out.get("tier") or _placement_tier_for_course_key(str(out.get("course_key") or ""))
            )
            if not isinstance(out.get("highlights"), list):
                out["highlights"] = []
            return out
    return None


def apply_placement_calculator_flags(questions: List[dict]) -> List[dict]:
    """Attach calculator_allowed from placement_meta (default false if unset)."""
    meta = _load_placement_meta_file()
    m = meta.get("calculator_by_index") or {}
    out: List[dict] = []
    for i, q in enumerate(questions):
        key = str(i + 1)
        raw = m.get(key)
        if raw is None:
            raw = m.get(i)
        allowed = bool(raw) if raw is not None else False
        qc = dict(q)
        qc["calculator_allowed"] = allowed
        out.append(qc)
    return out


def load_compiled_bank() -> Dict[str, Dict[str, List[dict]]]:
    global COMPILED_BANK_CACHE
    if COMPILED_BANK_CACHE is not None:
        return COMPILED_BANK_CACHE
    if not os.path.isfile(COMPILED_BANK_PATH):
        COMPILED_BANK_CACHE = {}
        return COMPILED_BANK_CACHE
    try:
        with open(COMPILED_BANK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            COMPILED_BANK_CACHE = data
        else:
            COMPILED_BANK_CACHE = {}
    except (OSError, json.JSONDecodeError):
        COMPILED_BANK_CACHE = {}
    return COMPILED_BANK_CACHE


def load_course_materials() -> dict[str, Any]:
    global COURSE_MATERIALS_CACHE
    if COURSE_MATERIALS_CACHE is not None:
        return COURSE_MATERIALS_CACHE
    if not os.path.isfile(COURSE_MATERIALS_PATH):
        COURSE_MATERIALS_CACHE = {"materials": [], "total": 0, "available": 0}
        return COURSE_MATERIALS_CACHE
    try:
        with open(COURSE_MATERIALS_PATH, "r", encoding="utf-8") as f:
            COURSE_MATERIALS_CACHE = json.load(f)
    except (OSError, json.JSONDecodeError):
        COURSE_MATERIALS_CACHE = {"materials": [], "total": 0, "available": 0}
    return COURSE_MATERIALS_CACHE


def _course_material_manifest_row(slug: str) -> dict[str, Any] | None:
    if not os.path.isfile(COURSE_MATERIALS_MANIFEST_PATH):
        return None
    try:
        with open(COURSE_MATERIALS_MANIFEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    for row in data.get("materials") or []:
        if row.get("slug") == slug:
            return row
    return None


def _course_material_by_slug(slug: str) -> dict[str, Any] | None:
    for row in load_course_materials().get("materials") or []:
        if row.get("slug") == slug:
            return row
    return None


def _course_materials_hub_context() -> dict[str, Any]:
    materials = list(load_course_materials().get("materials") or [])
    unit_groups: list[dict[str, Any]] = []
    for unit_num in (1, 2, 3, 4):
        rows = [m for m in materials if int(m.get("unit") or 0) == unit_num]
        if not rows:
            continue
        unit_groups.append(
            {
                "unit": unit_num,
                "unit_name": rows[0].get("unit_name") or f"Unit {unit_num}",
                "materials": rows,
                "ready_count": sum(1 for m in rows if m.get("tex_available")),
                "pdf_count": sum(1 for m in rows if m.get("pdf_available")),
            }
        )
    payload = load_course_materials()
    return {
        "unit_groups": unit_groups,
        "materials_total": int(payload.get("total") or len(materials)),
        "materials_ready": int(payload.get("available") or 0),
    }


def _course_material_pdf_path(slug: str) -> str | None:
    manifest = _course_material_manifest_row(slug)
    if not manifest:
        return None
    return _resolve_first_existing_path(list(manifest.get("pdf_candidates") or []))


def get_questions_for_topic(domain: str, topic: str, file_path: str) -> List[dict]:
    compiled = load_compiled_bank()
    topic_questions = compiled.get(domain, {}).get(topic)
    if isinstance(topic_questions, list) and topic_questions:
        if domain == "placement":
            return apply_placement_calculator_flags([dict(q) for q in topic_questions])
        return _finalize_questions(domain, topic, topic_questions)

    full_path = os.path.join(APP_DIR, file_path)
    if not os.path.isfile(full_path):
        return []
    try:
        if domain == "placement":
            qs = parse_placement_tex_file(full_path)
        else:
            qs = parse_tex_file(full_path)
    except OSError:
        return []
    if domain == "placement":
        return apply_placement_calculator_flags(qs)
    return _finalize_questions(domain, topic, qs)


# =====================================================
# BANK STRUCTURE
# =====================================================

# Planned SAT Math domains in this workspace (used for roadmap chip counts).
PRACTICE_DOMAIN_TARGET_COUNT = 4

BANKS: Dict[str, Dict[str, str]] = {
    # Unit 1 only (linear equations through inequalities)
    "algebra": {
        "unit_1_all": "Unit_1_Algebra.tex",
        "1_1": "banks/algebra/1_1.tex",
        "1_2": "banks/algebra/1_2.tex",
        "1_3": "banks/algebra/1_3.tex",
        "1_4": "banks/algebra/1_4.tex",
        "1_5": "banks/algebra/1_5.tex",
        "1_pt": "banks/algebra/1_pt.tex",
    },
    # Unit 2 only (advanced math — separate domain from algebra)
    "advanced_math": {
        "unit_2_all": "Unit_2_Advanced_Math.tex",
        "2_1": "banks/algebra/2_1.tex",
        "2_2": "banks/algebra/2_2.tex",
        "2_3": "banks/algebra/2_3.tex",
        "2_pt": "banks/algebra/2_pt.tex",
    },
    "problem_solving": {
        "unit_3_all": "Unit_3_PS_and_Stats.tex",
        "3_1": "banks/problem_solving/3_1.tex",
        "3_2": "banks/problem_solving/3_2.tex",
        "3_3": "banks/problem_solving/3_3.tex",
        "3_4": "banks/problem_solving/3_4.tex",
        "3_5": "banks/problem_solving/3_5.tex",
        "3_6": "banks/problem_solving/3_6.tex",
        "3_7": "banks/problem_solving/3_7.tex",
        "3_pt": "banks/problem_solving/3_pt.tex",
    },
    "geometry": {
        "unit_4_all": "Unit_4_Geometry.tex",
        "4_1": "banks/geometry/4_1.tex",
        "4_2": "banks/geometry/4_2.tex",
        "4_3": "banks/geometry/4_3.tex",
        "4_4": "banks/geometry/4_4.tex",
        "4_pt": "banks/geometry/4_pt.tex",
    },
    "hard_problem": {
        "hard_1": "banks/hard/hard_1.tex",
        "hard_2": "banks/hard/hard_2.tex",
        "hard_3": "banks/hard/hard_3.tex",
        "hard_4": "banks/hard/hard_4.tex",
        "hard_5": "banks/hard/hard_5.tex",
        "hard_6": "banks/hard/hard_6.tex",
        "hard_7": "banks/hard/hard_7.tex",
        "hard_8": "banks/hard/hard_8.tex",
        "hard_9": "banks/hard/hard_9.tex",
        "hard_10": "banks/hard/hard_10.tex",
        "hard_11": "banks/hard/hard_11.tex",
        "hard_12": "banks/hard/hard_12.tex",
        "hard_13": "banks/hard/hard_13.tex",
        "hard_14": "banks/hard/hard_14.tex",
        "hard_16": "banks/hard/hard_16.tex",
    },
    # Course placement (Algebra I/II vs Precalculus vs Calc AB) — see /placement and data/placement_meta.json
    "placement": {
        "placement_full": "Placement_Test.tex",
    },
}

HARD_PRACTICE_MATERIALS: Dict[str, Dict[str, Dict[str, str]]] = {
    "hard_1": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_1.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable version for paper practice or homework packets.",
            "download_name": "NovelPrep-SAT-Hard-Practice-1-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_1_PPT.pdf",
            "label": "Teaching slides",
            "description": "Classroom presentation version for walkthrough lessons.",
            "download_name": "NovelPrep-SAT-Hard-Practice-1-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
    "hard_2": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_2.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable version for paper practice or homework packets.",
            "download_name": "NovelPrep-SAT-Hard-Practice-2-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_PPT.pdf",
            "label": "Teaching slides",
            "description": "Classroom presentation version for walkthrough lessons.",
            "download_name": "NovelPrep-SAT-Hard-Practice-2-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
    "hard_3": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_3.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable version for paper practice or homework packets.",
            "download_name": "NovelPrep-SAT-Hard-Practice-3-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_3_PPT.pdf",
            "label": "Teaching slides",
            "description": "Classroom presentation version for walkthrough lessons.",
            "download_name": "NovelPrep-SAT-Hard-Practice-3-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
    "hard_4": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_4.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable version for paper practice or homework packets.",
            "download_name": "NovelPrep-SAT-Hard-Practice-4-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_4_PPT.pdf",
            "label": "Teaching slides",
            "description": "Classroom presentation version for walkthrough lessons.",
            "download_name": "NovelPrep-SAT-Hard-Practice-4-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
    "hard_5": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part _5.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable version for paper practice or homework packets.",
            "download_name": "NovelPrep-SAT-Hard-Practice-5-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_5_PPT.pdf",
            "label": "Teaching slides",
            "description": "Classroom presentation version for walkthrough lessons.",
            "download_name": "NovelPrep-SAT-Hard-Practice-5-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
    "hard_6": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_6.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable version for paper practice or homework packets.",
            "download_name": "NovelPrep-SAT-Hard-Practice-6-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_6_PPT.pdf",
            "label": "Teaching slides",
            "description": "Classroom presentation version for walkthrough lessons.",
            "download_name": "NovelPrep-SAT-Hard-Practice-6-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
    "hard_7": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_7.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable version for paper practice or homework packets.",
            "download_name": "NovelPrep-SAT-Hard-Practice-7-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_PPT_7.pdf",
            "label": "Teaching slides",
            "description": "Classroom presentation version for walkthrough lessons.",
            "download_name": "NovelPrep-SAT-Hard-Practice-7-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
    "hard_8": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_8.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable version for paper practice or homework packets.",
            "download_name": "NovelPrep-SAT-Hard-Practice-8-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_8_PPT.pdf",
            "label": "Teaching slides",
            "description": "Classroom presentation version for walkthrough lessons.",
            "download_name": "NovelPrep-SAT-Hard-Practice-8-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
    "hard_9": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_9.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable version for paper practice or homework packets.",
            "download_name": "NovelPrep-SAT-Hard-Practice-9-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_9_PPT.pdf",
            "label": "Teaching slides",
            "description": "Classroom presentation version for walkthrough lessons.",
            "download_name": "NovelPrep-SAT-Hard-Practice-9-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
    "hard_10": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_10.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable version for paper practice or homework packets.",
            "download_name": "NovelPrep-SAT-Hard-Practice-10-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_10_PPT.pdf",
            "label": "Teaching slides",
            "description": "Classroom presentation version for walkthrough lessons.",
            "download_name": "NovelPrep-SAT-Hard-Practice-10-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
    "hard_11": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_11.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable version for paper practice or homework packets.",
            "download_name": "NovelPrep-SAT-Hard-Practice-11-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_11_PPT.pdf",
            "label": "Teaching slides",
            "description": "Classroom presentation version for walkthrough lessons.",
            "download_name": "NovelPrep-SAT-Hard-Practice-11-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
    "hard_12": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_12.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable version for paper practice or homework packets.",
            "download_name": "NovelPrep-SAT-Hard-Practice-12-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_12_PPT.pdf",
            "label": "Teaching slides",
            "description": "Classroom presentation version for walkthrough lessons.",
            "download_name": "NovelPrep-SAT-Hard-Practice-12-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
    "hard_13": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_13.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable version for paper practice or homework packets.",
            "download_name": "NovelPrep-SAT-Hard-Practice-13-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_13_PPT.pdf",
            "label": "Teaching slides",
            "description": "Classroom presentation version for walkthrough lessons.",
            "download_name": "NovelPrep-SAT-Hard-Practice-13-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
    "hard_14": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_14.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable version for paper practice or homework packets.",
            "download_name": "NovelPrep-SAT-Hard-Practice-14-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_14_PPT.pdf",
            "label": "Teaching slides",
            "description": "Classroom presentation version for walkthrough lessons.",
            "download_name": "NovelPrep-SAT-Hard-Practice-14-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
    "hard_16": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_16.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable worksheet — Hard Practice XVI.",
            "download_name": "NovelPrep-SAT-Hard-Practice-16-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_16_PPT.pdf",
            "label": "Teaching slides",
            "description": "Slide deck with worked solutions for classroom review.",
            "download_name": "NovelPrep-SAT-Hard-Practice-16-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
}

UNIT_PDF_MATERIALS: Dict[str, Dict[str, Any]] = {
    "algebra": {
        "unit": "Unit 1",
        "title": "Algebra",
        "topic": "unit_1_all",
        "candidates": [
            "SAT_Unit_1_Algebra.pdf",
            "Unit _1_Algebra.pdf",
            "Unit_1_Algebra.pdf",
            "Unit 1 Algebra.pdf",
        ],
        "download_name": "NovelPrep-SAT-Unit-1-Algebra.pdf",
        "practice_test_candidates": ["SAT_Practice_Test_Unit_1.pdf"],
        "practice_test_download_name": "NovelPrep-SAT-Unit-1-Practice-Test.pdf",
    },
    "advanced_math": {
        "unit": "Unit 2",
        "title": "Advanced Math",
        "topic": "unit_2_all",
        "candidates": [
            "SAT_Unit_2_Advanced_Math.pdf",
            "Unit_2_Advanced_Math.pdf",
            "Unit 2 Advanced Math.pdf",
        ],
        "download_name": "NovelPrep-SAT-Unit-2-Advanced-Math.pdf",
        "practice_test_candidates": ["SAT_Practice_Test_Unit_2.pdf"],
        "practice_test_download_name": "NovelPrep-SAT-Unit-2-Practice-Test.pdf",
    },
    "problem_solving": {
        "unit": "Unit 3",
        "title": "Problem Solving & Data",
        "topic": "unit_3_all",
        "candidates": [
            "SAT_Unit_3_PS_and_Stats.pdf",
            "Unit_3_PS_DA.pdf",
            "Unit_3_PS_and_Stats.pdf",
            "Unit 3 Problem Solving and Data.pdf",
        ],
        "download_name": "NovelPrep-SAT-Unit-3-Problem-Solving-Data.pdf",
        "practice_test_candidates": ["SAT_Practice_Test_Unit_3.pdf"],
        "practice_test_download_name": "NovelPrep-SAT-Unit-3-Practice-Test.pdf",
    },
    "geometry": {
        "unit": "Unit 4",
        "title": "Geometry",
        "topic": "unit_4_all",
        "candidates": [
            "SAT_Unit_4_Geometry.pdf",
            "Unit_4_Geometry.pdf",
            "Unit 4 Geometry.pdf",
        ],
        "download_name": "NovelPrep-SAT-Unit-4-Geometry.pdf",
        "practice_test_candidates": ["SAT_Practice_Test_Unit_4.pdf"],
        "practice_test_download_name": "NovelPrep-SAT-Unit-4-Practice-Test.pdf",
    },
}


def _resolve_first_existing_path(candidates: List[str]) -> str | None:
    for rel in candidates:
        p = os.path.join(APP_DIR, rel)
        if os.path.isfile(p):
            return p
    return None


def _unit_pdf_cards() -> List[dict]:
    cards: List[dict] = []
    for domain, meta in UNIT_PDF_MATERIALS.items():
        found = _resolve_first_existing_path(list(meta.get("candidates") or []))
        cards.append(
            {
                "domain": domain,
                "unit": meta["unit"],
                "title": meta["title"],
                "topic": meta["topic"],
                "available": found is not None,
                "href": url_for("practice_unit_pdf", domain=domain) if found else "",
                "filename_hint": str((meta.get("candidates") or [""])[0]),
            }
        )
    return cards

# Landing page copy for /placement — mirrors `latex_parser._placement_part_meta` ranges.
PLACEMENT_LANDING_PARTS: List[Dict[str, str]] = [
    {"code": "I", "range": "1–15", "label": "Foundations & algebra"},
    {"code": "II", "range": "16–30", "label": "Exponents, rationals & functions"},
    {"code": "III", "range": "31–45", "label": "Graphs, geometry & radicals"},
    {"code": "IV", "range": "46–60", "label": "Functions, trig & precalc"},
    {"code": "V", "range": "61–70", "label": "Geometry & advanced readiness"},
]

# Human-readable labels for /practice/<domain> headers
PRACTICE_DOMAIN_TITLES: Dict[str, str] = {
    "algebra": "Algebra — Unit 1",
    "advanced_math": "Advanced Math — Unit 2",
    "problem_solving": "Problem Solving & Data — Unit 3",
    "geometry": "Geometry — Unit 4",
    "hard_problem": "SAT Hard Problem Drill",
    "placement": "Course placement diagnostic",
}

# Short labels for dashboard / compact UI (avoid repeating long domain strings).
DASHBOARD_TRACK_SHORT: Dict[str, str] = {
    "algebra": "SAT · Algebra",
    "advanced_math": "SAT · Adv. math",
    "problem_solving": "SAT · Data",
    "geometry": "SAT · Geometry",
    "hard_problem": "SAT · Hard",
    "placement": "Placement",
}

def _practice_session_key(domain: str, topic: str) -> str:
    return f"pa_{domain}_{topic}"


def _practice_mistake_redo_session_key(domain: str, topic: str, q_index: int) -> str:
    """Session key for a one-off redo from the mistake log (isolated from full-bank runs)."""
    return f"pa_mr_{domain}_{topic}_{q_index}"


KNOWN_ANALYTICS_PART_IDS = frozenset(
    {"sat", "unit1", "unit2", "unit3", "unit4", "placement", "other"}
)


def _mistake_analytics_return_href(part_raw: str | None, anchor_raw: str | None) -> str:
    """Build a safe link back to mistake analytics (optional unit anchor)."""
    pid = (part_raw or "").strip().lower()
    if pid and pid not in KNOWN_ANALYTICS_PART_IDS:
        pid = ""
    base = url_for("practice_analytics", part=pid) if pid else url_for("practice_analytics")
    frag = _safe_url_fragment(anchor_raw)
    if frag:
        return f"{base}#{frag}"
    return base


def _mistake_redo_flag(val: str | None) -> bool:
    return (val or "").strip().lower() in ("1", "yes", "true")


MQ_PACK_KEY = "miss_quiz_pack"
MQ_FEEDBACK_KEY = "miss_quiz_feedback"
MQ_PACK_VERSION = 2

# Miss quiz run must meet this accuracy or ladder mastery for these slots is reset.
MISS_QUIZ_PASS_PERCENT = 90


def _safe_url_fragment(raw: str | None) -> str | None:
    s = (raw or "").strip()
    if not s or len(s) > 80:
        return None
    if not re.match(r"^[A-Za-z0-9_\-]+$", s):
        return None
    return s


def _redirect_practice_analytics(part: str, anchor: str | None = None):
    part_q = (part or "").strip().lower()
    base = (
        url_for("practice_analytics", part=part_q) if part_q else url_for("practice_analytics")
    )
    frag = _safe_url_fragment(anchor)
    if frag:
        return redirect(f"{base}#{frag}")
    return redirect(base)


def _mistake_progress_reset_items_after_failed_quiz(
    db: sqlite3.Connection, learner_key: str, items: List[dict]
) -> int:
    """Demote stored ladder progress for every bank slot in this miss quiz (failed accuracy bar)."""
    n = 0
    for it in items:
        cur = db.execute(
            """
            UPDATE mistake_learning_progress
            SET status = 'unreviewed',
                correct_after_last_wrong = 0,
                updated_at = datetime('now')
            WHERE learner_key = ? AND domain = ? AND topic = ? AND question_index = ?
            """,
            (learner_key, str(it["domain"]), str(it["topic"]), int(it["q_index"])),
        )
        n += int(cur.rowcount or 0)
    return n


def _mistake_progress_reset_slots_after_failed_quiz(
    db: sqlite3.Connection, learner_key: str, domain: str, topic: str, indices: List[int]
) -> int:
    items = [{"domain": domain, "topic": topic, "q_index": int(qi)} for qi in indices]
    return _mistake_progress_reset_items_after_failed_quiz(db, learner_key, items)


def _attempt_user_matches(db: sqlite3.Connection, attempt_id: int, user_id: Any) -> bool:
    row = db.execute(
        "SELECT user_id FROM practice_attempts WHERE id = ?",
        (attempt_id,),
    ).fetchone()
    if row is None:
        return False
    au = row["user_id"]
    if user_id is None:
        return au is None
    return int(au) == int(user_id)


def _distinct_wrong_indices_for_topic(
    db: sqlite3.Connection, user_id: Any, domain: str, topic: str
) -> List[int]:
    """Distinct bank indices with at least one incorrect (tracked attempts only for SAT)."""
    tracked_sql = _tracked_attempt_sql("pa")
    if user_id is not None:
        rows = db.execute(
            f"""
            SELECT DISTINCT pr.question_index AS qi
            FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pr.is_correct = 0
              AND pr.question_index IS NOT NULL
              AND pa.domain = ? AND pa.topic = ?
              AND pa.user_id IS ?
              AND {tracked_sql}
            ORDER BY qi
            """,
            (domain, topic, user_id),
        ).fetchall()
    else:
        rows = db.execute(
            f"""
            SELECT DISTINCT pr.question_index AS qi
            FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pr.is_correct = 0
              AND pr.question_index IS NOT NULL
              AND pa.domain = ? AND pa.topic = ?
              AND pa.user_id IS NULL
              AND {tracked_sql}
            ORDER BY qi
            """,
            (domain, topic),
        ).fetchall()
    return [int(r["qi"]) for r in rows if r["qi"] is not None]


def _wrong_indices_from_attempt(db: sqlite3.Connection, attempt_id: int) -> List[int]:
    rows = db.execute(
        """
        SELECT question_index FROM practice_responses
        WHERE attempt_id = ? AND is_correct = 0 AND question_index IS NOT NULL
        ORDER BY submitted_at ASC
        """,
        (attempt_id,),
    ).fetchall()
    seen: set[int] = set()
    out: List[int] = []
    for r in rows:
        qi = int(r["question_index"])
        if qi not in seen:
            seen.add(qi)
            out.append(qi)
    return out


def _miss_quiz_answered_in_pack(
    db: sqlite3.Connection, attempt_id: int, indices: List[int]
) -> int:
    if not indices:
        return 0
    ph = ",".join("?" * len(indices))
    row = db.execute(
        f"""
        SELECT COUNT(DISTINCT question_index) AS c
        FROM practice_responses
        WHERE attempt_id = ? AND question_index IN ({ph})
        """,
        (attempt_id, *indices),
    ).fetchone()
    return int(row["c"] or 0) if row else 0


def _mq_attempt_map_key(domain: str, topic: str) -> str:
    return f"{domain}|||{topic}"


def _mq_normalize_pack_session(pack: dict | None) -> dict:
    """Upgrade legacy single-topic miss-quiz session packs to v2 (items + per-topic attempts)."""
    if not pack:
        return {}
    if pack.get("v") == MQ_PACK_VERSION:
        return pack
    indices = pack.get("indices")
    dom = pack.get("domain")
    top = pack.get("topic")
    if not indices or not dom or not top:
        return pack
    new_p = {**pack}
    new_p["v"] = MQ_PACK_VERSION
    new_p["items"] = [
        {"domain": str(dom), "topic": str(top), "q_index": int(i)} for i in indices
    ]
    am: dict[str, int] = {}
    aid = new_p.get("attempt_id")
    if aid:
        am[_mq_attempt_map_key(str(dom), str(top))] = int(aid)
    new_p["attempt_map"] = am
    pid = MISS_PART_BY_DOMAIN.get(str(dom))
    if pid:
        new_p.setdefault("summary_part_id", pid)
    session[MQ_PACK_KEY] = new_p
    session.modified = True
    return new_p


def _mq_get_pack_items(pack: dict) -> List[dict]:
    if pack.get("v") == MQ_PACK_VERSION:
        return [dict(x) for x in (pack.get("items") or [])]
    d, t = pack.get("domain"), pack.get("topic")
    if not d or not t:
        return []
    return [{"domain": str(d), "topic": str(t), "q_index": int(i)} for i in pack.get("indices") or []]


def _miss_quiz_ensure_attempt_for_topic(
    db: sqlite3.Connection, user_id: Any, pack: dict, domain: str, topic: str, seed_q_index: int
) -> int:
    am = pack.setdefault("attempt_map", {})
    k = _mq_attempt_map_key(domain, topic)
    if k in am and int(am[k]) > 0:
        return int(am[k])
    aid = _insert_practice_attempt(db, user_id, domain, topic, int(seed_q_index))
    am[k] = int(aid)
    session[MQ_PACK_KEY] = pack
    session.modified = True
    return int(aid)


def _miss_quiz_answered_in_pack_v2(
    db: sqlite3.Connection, attempt_map: dict, items: List[dict]
) -> int:
    n = 0
    for it in items:
        k = _mq_attempt_map_key(str(it["domain"]), str(it["topic"]))
        aid = attempt_map.get(k)
        if not aid:
            continue
        r = db.execute(
            """
            SELECT 1 FROM practice_responses
            WHERE attempt_id = ? AND question_index = ?
            LIMIT 1
            """,
            (int(aid), int(it["q_index"])),
        ).fetchone()
        if r:
            n += 1
    return n


def _placement_profile_from_session() -> tuple[str, str, str]:
    """Student info collected on /placement/start before the diagnostic."""
    name = (session.get("placement_student_name") or "").strip()
    grade = (session.get("placement_student_grade") or "").strip()
    course = (session.get("placement_student_math_course") or "").strip()
    return name, grade, course


def _clear_placement_profile_session() -> None:
    session.pop("placement_student_name", None)
    session.pop("placement_student_grade", None)
    session.pop("placement_student_math_course", None)


def _clear_placement_full_session_attempt() -> None:
    """Drop in-progress placement attempt binding so the next run creates a new row."""
    session.pop(_practice_session_key("placement", "placement_full"), None)


def _backfill_placement_student_profile(
    db: sqlite3.Connection, attempt_id: int, domain: str
) -> None:
    """If the browser still holds an old attempt id, attach intake fields once the DB row is empty."""
    if domain != "placement":
        return
    name, grade, course = _placement_profile_from_session()
    if not name:
        return
    row = db.execute(
        "SELECT placement_student_name FROM practice_attempts WHERE id = ? AND domain = 'placement'",
        (attempt_id,),
    ).fetchone()
    if row is None:
        return
    if (str(row["placement_student_name"] or "")).strip():
        return
    db.execute(
        """
        UPDATE practice_attempts
        SET placement_student_name = ?, placement_student_grade = ?, placement_student_math_course = ?
        WHERE id = ?
        """,
        (name, grade or None, course or None, attempt_id),
    )
    db.commit()


# Quick reflection tags after a wrong attempt (shown on reflect + analytics pages).
MISTAKE_TAG_OPTIONS: List[Dict[str, str]] = [
    {"id": "careless", "label": "Careless slip"},
    {"id": "concept", "label": "Concept gap"},
    {"id": "setup", "label": "Setup / modeling error"},
    {"id": "algebra", "label": "Algebra / arithmetic error"},
    {"id": "reading", "label": "Misread the prompt"},
    {"id": "time", "label": "Ran out of time"},
    {"id": "guess", "label": "Guessed"},
    {"id": "other", "label": "Other"},
]

TOPIC_TITLES = {
    "unit_1_all": "Unit 1 – Algebra (full bank)",
    "1_1": "Unit 1.1 – Linear Equations in One Variable",
    "1_2": "Unit 1.2 – Linear Functions",
    "1_3": "Unit 1.3 – Linear Equations in Two Variables",
    "1_4": "Unit 1.4 – Systems of Linear Equations",
    "1_5": "Unit 1.5 – Linear Inequalities",
    "1_pt": "Unit 1 Practice Test",
    "unit_2_all": "Unit 2 – Advanced Math (full bank)",
    "2_1": "Unit 2.1 – Equivalent Expressions",
    "2_2": "Unit 2.2 – Nonlinear Equations & Systems",
    "2_3": "Unit 2.3 – Nonlinear Functions",
    "2_pt": "Unit 2 Practice Test",
    "3_pt": "Unit 3 Practice Test",
    "4_pt": "Unit 4 Practice Test",
    "unit_3_all": "Unit 3 – Problem Solving & Data (full bank)",
    "3_1": "Unit 3.1 – Ratios, rates, proportional relationships, and units",
    "3_2": "Unit 3.2 – Percentages",
    "3_3": "Unit 3.3 – One-variable data: distributions and center/spread",
    "3_4": "Unit 3.4 – Two-variable data: models and scatterplots",
    "3_5": "Unit 3.5 – Probability and conditional probability",
    "3_6": "Unit 3.6 – Inference from sample statistics and margin of error",
    "3_7": "Unit 3.7 – Evaluating statistical claims: studies and experiments",
    "unit_4_all": "Unit 4 – Geometry (full bank)",
    "geo_all": "Unit 4 – Geometry (full bank)",
    "4_1": "Unit 4.1 – Volume and area",
    "4_2": "Unit 4.2 – Lines, angles, and triangles",
    "4_3": "Unit 4.3 – Right triangles and trigonometry",
    "4_4": "Unit 4.4 – Circles",
    "hard_1": "SAT Hard Question Set 1 (Practice I)",
    "hard_2": "SAT Hard Question Set 2 (Practice II)",
    "hard_3": "SAT Hard Question Set 3 (Practice III)",
    "hard_4": "SAT Hard Question Set 4 (Practice IV)",
    "hard_5": "SAT Hard Question Set 5 (Practice V)",
    "hard_6": "SAT Hard Question Set 6 (Practice VI)",
    "hard_7": "SAT Hard Question Set 7 (Practice VII)",
    "hard_8": "SAT Hard Question Set 8 (Practice VIII)",
    "hard_9": "SAT Hard Question Set 9 (Practice IX)",
    "hard_10": "SAT Hard Question Set 10 (Practice X)",
    "hard_11": "SAT Hard Question Set 11 (Practice XI)",
    "hard_12": "SAT Hard Question Set 12 (Practice XII)",
    "hard_13": "SAT Hard Question Set 13 (Practice XIII)",
    "hard_14": "SAT Hard Question Set 14 (Practice XIV)",
    "hard_16": "SAT Hard Question Set 16 (Practice XVI)",
    "psd_all": "Unit 3 – Problem Solving & Data (full bank)",
    "placement_full": "Course placement (full diagnostic)",
}

SAT_UNIT_LABELS: Dict[str, tuple[str, str]] = {
    "U1": ("Unit 1", "Algebra"),
    "U2": ("Unit 2", "Advanced Math"),
    "U3": ("Unit 3", "Problem Solving & Data"),
    "U4": ("Unit 4", "Geometry"),
}

# SAT Math domain → four-unit taxonomy (specialized training banks).
DOMAIN_SAT_UNIT: Dict[str, tuple[str, str]] = {
    "algebra": SAT_UNIT_LABELS["U1"],
    "advanced_math": SAT_UNIT_LABELS["U2"],
    "problem_solving": SAT_UNIT_LABELS["U3"],
    "geometry": SAT_UNIT_LABELS["U4"],
}

# Per-question SAT unit tags for Hard Problem Drill — see data/hard_question_units.json
_HARD_UNITS_CACHE: Dict[str, List[dict]] | None = None


def _load_hard_question_units() -> Dict[str, List[dict]]:
    global _HARD_UNITS_CACHE
    if _HARD_UNITS_CACHE is not None:
        return _HARD_UNITS_CACHE
    path = os.path.join(APP_DIR, "data", "hard_question_units.json")
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        _HARD_UNITS_CACHE = {}
        return _HARD_UNITS_CACHE
    out: Dict[str, List[dict]] = {}
    for topic, items in raw.items():
        if topic.startswith("_") or not isinstance(items, list):
            continue
        out[topic] = [dict(x) for x in items if isinstance(x, dict) and x.get("unit")]
    _HARD_UNITS_CACHE = out
    return out


def _enrich_domain_sat_unit(domain: str, questions: List[dict]) -> None:
    pair = DOMAIN_SAT_UNIT.get(domain)
    if not pair:
        return
    unit_label, unit_title = pair
    for q in questions:
        q["sat_unit_label"] = unit_label
        q["sat_unit_title"] = unit_title


def _apply_hard_question_metadata(topic: str, questions: List[dict]) -> None:
    keys = HARD_ANSWER_KEYS.get(topic, [])
    for i, meta in enumerate(keys):
        if i < len(questions):
            questions[i].update(meta)
    _apply_hard_question_units(topic, questions)


def _finalize_questions(domain: str, topic: str, questions: List[dict]) -> List[dict]:
    out = [dict(q) for q in questions]
    if domain == "hard_problem":
        _apply_hard_question_metadata(topic, out)
    elif domain in DOMAIN_SAT_UNIT:
        _enrich_domain_sat_unit(domain, out)
    return out


def _hard_unit_meta(unit_key: str) -> tuple[str, str]:
    sec, title = SAT_UNIT_LABELS.get(unit_key, ("—", ""))
    return sec, title


def _summary_topic_fields(domain: str, qobj: dict) -> tuple[str, str, str]:
    """Return (section tag, unit title, detail line) for session summary topic column."""
    if domain == "hard_problem":
        sec = str(qobj.get("knowledge_section") or "—")
        title = str(qobj.get("knowledge_section_title_en") or "")
        detail = str(qobj.get("hard_skill") or "")
        return sec, title, detail
    if domain in DOMAIN_SAT_UNIT:
        sec, title = DOMAIN_SAT_UNIT[domain]
        detail = str(qobj.get("knowledge_section_title_en") or qobj.get("knowledge_section") or "")
        return sec, title, detail
    sec = str(qobj.get("knowledge_section") or "—")
    title = str(qobj.get("knowledge_section_title_en") or "")
    return sec, title, ""


def _apply_hard_question_units(topic: str, questions: List[dict]) -> None:
    units = _load_hard_question_units().get(topic) or []
    keys = HARD_ANSWER_KEYS.get(topic, [])
    for i, q in enumerate(questions):
        meta: dict = {}
        if i < len(units):
            meta = units[i]
        elif i < len(keys):
            meta = keys[i]
        unit_key = str(meta.get("unit") or "").strip()
        if not unit_key:
            continue
        sec, title = _hard_unit_meta(unit_key)
        q["knowledge_section"] = sec
        q["knowledge_section_title_en"] = title
        skill = str(meta.get("skill") or "").strip()
        if skill:
            q["hard_skill"] = skill


HARD_ANSWER_KEYS: Dict[str, List[dict]] = {
    "hard_1": [
        {"correct_answer": "7744"},
        {"correct_answer": "1021"},
        {"correct_answer": "17/2", "answer_alternates": ["8.5"]},
        {"correct_answer": "14"},
        {"correct_answer": "D"},
        {"correct_answer": "62"},
        {"correct_answer": "B"},
        {"correct_answer": "750"},
        {"correct_answer": "195"},
        {"correct_answer": "D"},
        {"correct_answer": "D"},
    ],
    "hard_2": [
        {"correct_answer": "C"},
        {"correct_answer": "B"},
        {"correct_answer": "D"},
        {"correct_answer": "D"},
        {"correct_answer": "D"},
        {"correct_answer": "86.5", "answer_alternates": ["173/2"]},
        {"correct_answer": "A"},
        {"correct_answer": "B"},
        {"correct_answer": "D"},
    ],
    "hard_3": [
        {"correct_answer": "B"},
        {"correct_answer": "C"},
        {"correct_answer": "B"},
        {"correct_answer": "3.88", "answer_alternates": ["3.883", "3.8834"]},
        {"correct_answer": "C"},
    ],
    "hard_4": [
        {"correct_answer": "A"},
        {"correct_answer": "D"},
        {"correct_answer": "D"},
        {"correct_answer": "C"},
        {"correct_answer": "8"},
        {"correct_answer": "22/3", "answer_alternates": ["7.333", "7.3333", "7.33"]},
        {"correct_answer": "2,-5", "answer_alternates": ["(2,-5)", "(2, -5)", "2, -5"]},
    ],
    "hard_5": [
        {"correct_answer": "A"},
        {"correct_answer": "D"},
        {"correct_answer": "D"},
        {"correct_answer": "A"},
        {"correct_answer": "C"},
        {"correct_answer": "-19"},
        {"correct_answer": "B"},
        {"correct_answer": "D"},
        {"correct_answer": "C"},
        {"correct_answer": "D"},
        {"correct_answer": "A"},
        {"correct_answer": "A"},
        {"correct_answer": "D"},
        {"correct_answer": "D"},
        {"correct_answer": "C"},
    ],
    "hard_6": [
        {"correct_answer": "3/350", "answer_alternates": ["0.00857", "0.008571"]},
        {"correct_answer": "D"},
        {"correct_answer": "73/8", "answer_alternates": ["9.125", "9.13"]},
        {"correct_answer": "D"},
        {"correct_answer": "D"},
        {"correct_answer": "B"},
        {"correct_answer": "A"},
        {"correct_answer": "A"},
        {"correct_answer": "B"},
        {"correct_answer": "C"},
        {"correct_answer": "B"},
        {"correct_answer": "C"},
        {"correct_answer": "B"},
        {"correct_answer": "4"},
        {"correct_answer": "4"},
    ],
    "hard_7": [
        {"correct_answer": "B"},
        {"correct_answer": "B"},
        {"correct_answer": "B"},
        {"correct_answer": "B"},
        {"correct_answer": "-28"},
        {"correct_answer": "630"},
        {"correct_answer": "188.5", "answer_alternates": ["377/2"]},
        {"correct_answer": "B"},
        {"correct_answer": "D"},
        {"correct_answer": "D"},
        {"correct_answer": "A"},
        {"correct_answer": "A"},
    ],
    "hard_8": [
        {"correct_answer": "A"},
        {"correct_answer": "C"},
        {"correct_answer": "A"},
        {"correct_answer": "A"},
        {"correct_answer": "C"},
        {"correct_answer": "C"},
        {"correct_answer": "A"},
        {"correct_answer": "C"},
        {"correct_answer": "D"},
        {"correct_answer": "1560"},
        {"correct_answer": "D"},
        {"correct_answer": "D"},
    ],
    "hard_9": [
        {"correct_answer": "C"},
        {"correct_answer": "B"},
        {"correct_answer": "A"},
        {"correct_answer": "A"},
        {"correct_answer": "D"},
        {"correct_answer": "D"},
        {"correct_answer": "C"},
        {"correct_answer": "B"},
        {"correct_answer": "A"},
    ],
    "hard_10": [
        {"correct_answer": "B"},
        {"correct_answer": "D"},
        {"correct_answer": "D"},
        {"correct_answer": "A"},
        {"correct_answer": "B"},
        {"correct_answer": "D"},
        {"correct_answer": "A"},
        {"correct_answer": "C"},
    ],
    "hard_11": [
        {"correct_answer": "A"},
        {"correct_answer": "A"},
        {"correct_answer": "A"},
        {"correct_answer": "A"},
        {"correct_answer": "A"},
        {"correct_answer": "2381"},
        {"correct_answer": "C"},
        {"correct_answer": "C"},
        {"correct_answer": "A"},
        {"correct_answer": "B"},
        {"correct_answer": "A"},
        {"correct_answer": "D"},
    ],
    "hard_12": [
        {"correct_answer": "B"},
        {"correct_answer": "C"},
        {"correct_answer": "B"},
        {"correct_answer": "D"},
        {"correct_answer": "A"},
        {"correct_answer": "D"},
        {"correct_answer": "C"},
        {"correct_answer": "C"},
        {"correct_answer": "A"},
    ],
    "hard_13": [
        {"correct_answer": "D"},
        {"correct_answer": "C"},
        {"correct_answer": "C"},
        {"correct_answer": "A"},
        {"correct_answer": "C"},
        {"correct_answer": "-2"},
        {"correct_answer": "B"},
        {"correct_answer": "A"},
        {"correct_answer": "C"},
        {"correct_answer": "B"},
        {"correct_answer": "A"},
        {"correct_answer": "B"},
        {"correct_answer": "D"},
    ],
    "hard_14": [
        {"correct_answer": "5"},
        {"correct_answer": "-3/14", "answer_alternates": ["-0.214", "-0.2143"]},
        {"correct_answer": "72/5", "answer_alternates": ["14.4"]},
        {"correct_answer": "B"},
        {"correct_answer": "5/28", "answer_alternates": ["0.1786", "0.179"]},
        {"correct_answer": "-8"},
        {"correct_answer": "C"},
        {"correct_answer": "4"},
        {"correct_answer": "140t+48", "answer_alternates": ["48+140t"]},
        {"correct_answer": "60000"},
        {"correct_answer": "D"},
        {"correct_answer": "A"},
        {"correct_answer": "C"},
        {"correct_answer": "A"},
        {"correct_answer": "1944"},
        {"correct_answer": "A"},
        {"correct_answer": "127"},
    ],
    "hard_16": [
        {"correct_answer": "1.6", "answer_alternates": ["8/5", "1.60"]},
        {"correct_answer": "51"},
        {"correct_answer": "14500", "answer_alternates": ["14,500", "14500"]},
        {"correct_answer": "13"},
        {"correct_answer": "D"},
        {"correct_answer": "6.2"},
        {"correct_answer": "B"},
        {"correct_answer": "-5/3", "answer_alternates": ["-1.667", "-1.67"]},
        {"correct_answer": "167"},
        {"correct_answer": "A"},
        {"correct_answer": "B"},
        {"correct_answer": "B"},
        {"correct_answer": "31.8"},
    ],
}

# catalog: "standardized" = admissions-style exams; "school" = in-school / college curriculum (placement gates level).
LEARNING_TRACKS = [
    {
        "key": "sat",
        "catalog": "standardized",
        "title": "SAT Math",
        "level": "Active",
        "description": "Full adaptive bank—timed feel, instant scoring, shareable session reports.",
        "cta_label": "Enter workspace",
        "cta_href": "/practice",
        "pill": "Live",
    },
    {
        "key": "isee",
        "catalog": "standardized",
        "title": "ISEE Math",
        "level": "Planned",
        "description": "Upper-level quantitative reasoning & QC—same polish as SAT when it ships.",
        "cta_label": "Preview roadmap",
        "cta_href": "/learn/isee",
        "pill": "Roadmap",
    },
    {
        "key": "placement",
        "catalog": "school",
        "title": "Course placement",
        "level": "Active",
        "description": "70-item diagnostic with printable + in-app reports—lock the right level for honors or AP, then walk into advising with a polished PDF.",
        "cta_label": "Start placement",
        "cta_href": "/placement",
        "pill": "Live",
    },
    {
        "key": "ap_calc",
        "catalog": "school",
        "title": "AP Calculus AB / BC",
        "level": "Planned",
        "description": "AP-style calculus from limits through series. Full bank is on the roadmap.",
        "cta_label": "Preview roadmap",
        "cta_href": "/learn/ap_calc",
        "pill": "Roadmap",
    },
    {
        "key": "ap_stats",
        "catalog": "school",
        "title": "AP Statistics",
        "level": "Planned",
        "description": "Inference-first AP Statistics storyline. Module on the roadmap.",
        "cta_label": "Preview roadmap",
        "cta_href": "/learn/ap_stats",
        "pill": "Roadmap",
    },
    {
        "key": "ap_precalc",
        "catalog": "school",
        "title": "AP Precalculus",
        "level": "Planned",
        "description": "College Board–style precalculus—functions, modeling, trigonometry, and a bridge into AP Calculus. Question bank on the roadmap.",
        "cta_label": "Preview roadmap",
        "cta_href": "/learn/ap_precalc",
        "pill": "Roadmap",
    },
    {
        "key": "multivariable",
        "catalog": "school",
        "title": "Multivariable Calculus",
        "level": "Planned",
        "description": "Honors or early college multivariable calculus—visual-first bank planned.",
        "cta_label": "Preview roadmap",
        "cta_href": "/learn/multivariable",
        "pill": "Roadmap",
    },
    {
        "key": "linear_algebra",
        "catalog": "school",
        "title": "Linear Algebra",
        "level": "Planned",
        "description": "Matrices and eigensystems for advanced school or early college. Roadmap.",
        "cta_label": "Preview roadmap",
        "cta_href": "/learn/linear_algebra",
        "pill": "Roadmap",
    },
    {
        "key": "diff_eq",
        "catalog": "school",
        "title": "Differential Equations",
        "level": "Planned",
        "description": "ODEs and modeling for honors STEM paths. Roadmap.",
        "cta_label": "Preview roadmap",
        "cta_href": "/learn/diff_eq",
        "pill": "Roadmap",
    },
]


def _pct(correct: int, total: int) -> int:
    if total <= 0:
        return 0
    return round(100.0 * correct / total)


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


MIN_TRACKED_SAT_RESPONSES = 3


def _tracked_attempt_sql(alias: str = "pa") -> str:
    """Only count deliberate SAT sessions; placement diagnostics are always tracked."""
    return (
        f"({alias}.domain = 'placement' OR "
        f"(SELECT COUNT(*) FROM practice_responses pr_track "
        f"WHERE pr_track.attempt_id = {alias}.id "
        f"AND pr_track.is_correct IN (0, 1)) >= {MIN_TRACKED_SAT_RESPONSES})"
    )


def _practice_distinct_answered(db: sqlite3.Connection, user_id: Any, domain: str, topic: str) -> int:
    """How many distinct question indices in this full-bank topic have at least one saved response."""
    tracked_sql = _tracked_attempt_sql("pa")
    if user_id is not None:
        row = db.execute(
            f"""
            SELECT COUNT(DISTINCT pr.question_index) AS c
            FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pa.user_id IS ? AND pa.domain = ? AND pa.topic = ?
              AND pr.question_index IS NOT NULL
              AND {tracked_sql}
            """,
            (user_id, domain, topic),
        ).fetchone()
    else:
        row = db.execute(
            f"""
            SELECT COUNT(DISTINCT pr.question_index) AS c
            FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pa.user_id IS NULL AND pa.domain = ? AND pa.topic = ?
              AND pr.question_index IS NOT NULL
              AND {tracked_sql}
            """,
            (domain, topic),
        ).fetchone()
    if not row:
        return 0
    return int(row["c"] or 0)


def _practice_latest_complete_attempt_id(
    db: sqlite3.Connection, user_id: Any, domain: str, topic: str, total_q: int
) -> int | None:
    """Most recent attempt where every question in the bank was answered."""
    if total_q <= 0:
        return None
    if user_id is not None:
        row = db.execute(
            """
            SELECT pa.id
            FROM practice_attempts pa
            JOIN practice_responses pr ON pr.attempt_id = pa.id
            WHERE pa.user_id IS ? AND pa.domain = ? AND pa.topic = ?
              AND pr.question_index IS NOT NULL
            GROUP BY pa.id
            HAVING COUNT(DISTINCT pr.question_index) >= ?
            ORDER BY pa.id DESC
            LIMIT 1
            """,
            (user_id, domain, topic, total_q),
        ).fetchone()
    else:
        row = db.execute(
            """
            SELECT pa.id
            FROM practice_attempts pa
            JOIN practice_responses pr ON pr.attempt_id = pa.id
            WHERE pa.user_id IS NULL AND pa.domain = ? AND pa.topic = ?
              AND pr.question_index IS NOT NULL
            GROUP BY pa.id
            HAVING COUNT(DISTINCT pr.question_index) >= ?
            ORDER BY pa.id DESC
            LIMIT 1
            """,
            (domain, topic, total_q),
        ).fetchone()
    if not row:
        return None
    return int(row["id"])


def _practice_report_href(
    db: sqlite3.Connection, user_id: Any, domain: str, topic: str, total_q: int
) -> str | None:
    attempt_id = _practice_latest_complete_attempt_id(db, user_id, domain, topic, total_q)
    if attempt_id is None:
        return None
    return url_for("practice_session_summary", attempt_id=attempt_id)


def _dashboard_track_short(domain: str | None) -> str:
    d = (domain or "").strip()
    if not d:
        return "Practice"
    return DASHBOARD_TRACK_SHORT.get(d, d.replace("_", " ").title())


def _session_when_label(created_at: str | None) -> str:
    if not created_at:
        return ""
    s = str(created_at).strip()
    try:
        dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        d_only = dt.date()
        today = date.today()
        if d_only == today:
            return "Today"
        if (today - d_only).days == 1:
            return "Yesterday"
        return f"{dt.strftime('%b')} {d_only.day}"
    except ValueError:
        return s[:10] if len(s) >= 10 else s


def _topic_practice_href(domain: str, topic_key: str) -> str | None:
    spec = BANKS.get(domain)
    if not isinstance(spec, dict) or topic_key not in spec:
        return None
    return url_for("practice_question", domain=domain, topic=topic_key, qnum=0)


def _build_focus_topics(rows: List[dict]) -> List[dict]:
    """Lowest-accuracy topics with enough graded items to be meaningful; cap list length."""
    min_sample = 3
    with_sample = [t for t in rows if int(t.get("total") or 0) >= min_sample]
    pool = with_sample if with_sample else list(rows)
    pool = sorted(
        pool,
        key=lambda x: (int(x.get("pct") or 0), -int(x.get("total") or 0)),
    )
    out: List[dict] = []
    for t in pool[:4]:
        dom = str(t.get("domain") or "")
        tk = str(t.get("topic_key") or "")
        if not dom or not tk:
            continue
        out.append(
            {
                "track_short": _dashboard_track_short(dom),
                "topic_title": TOPIC_TITLES.get(tk, tk),
                "correct": int(t.get("correct") or 0),
                "total": int(t.get("total") or 0),
                "pct": int(t.get("pct") or 0),
                "practice_href": _topic_practice_href(dom, tk),
            }
        )
    return out


def _dashboard_context() -> dict:
    db = get_db()
    user_id = session.get("user_id")
    tracked_sql = _tracked_attempt_sql("pa")
    where = f"WHERE pa.user_id = ? AND {tracked_sql}" if user_id else f"WHERE {tracked_sql}"
    params: tuple[Any, ...] = (user_id,) if user_id else ()

    attempts_total = db.execute(
        f"SELECT COUNT(*) AS c FROM practice_attempts pa {where}",
        params,
    ).fetchone()["c"]

    graded = db.execute(
        f"""
        SELECT
          SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct,
          SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded_total
        FROM practice_responses pr
        JOIN practice_attempts pa ON pa.id = pr.attempt_id
        {where}
        """,
        params,
    ).fetchone()
    total_correct = int(graded["correct"] or 0)
    total_graded = int(graded["graded_total"] or 0)
    wrong_total = max(0, total_graded - total_correct)

    sat_topic_rows = db.execute(
        f"""
        SELECT pa.domain,
               pa.topic,
               SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct,
               SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded_total
        FROM practice_responses pr
        JOIN practice_attempts pa ON pa.id = pr.attempt_id
        {where}
        GROUP BY pa.domain, pa.topic
        """,
        params,
    ).fetchall()

    sat_topics: List[dict] = []
    for row in sat_topic_rows:
        gt = int(row["graded_total"] or 0)
        c = int(row["correct"] or 0)
        dom = row["domain"] or "algebra"
        topic_key = str(row["topic"] or "")
        sat_topics.append(
            {
                "domain": dom,
                "topic_key": topic_key,
                "correct": c,
                "total": gt,
                "pct": _pct(c, gt),
            }
        )
    sat_topics.sort(key=lambda x: x["pct"])
    focus_topics = _build_focus_topics(sat_topics)

    recent_rows = db.execute(
        f"""
        SELECT
          pa.id,
          pa.domain,
          pa.topic,
          pa.created_at,
          SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct,
          SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded_total
        FROM practice_attempts pa
        LEFT JOIN practice_responses pr ON pr.attempt_id = pa.id
        {where}
        GROUP BY pa.id, pa.domain, pa.topic, pa.created_at
        ORDER BY pa.id DESC
        LIMIT 3
        """,
        params,
    ).fetchall()

    recent_sessions: List[dict] = []
    for row in recent_rows:
        gt = int(row["graded_total"] or 0)
        c = int(row["correct"] or 0)
        dom = row["domain"]
        topic_slug = str(row["topic"] or "")
        topic_title = TOPIC_TITLES.get(topic_slug, topic_slug)
        summary_href = (
            url_for("practice_session_summary", attempt_id=int(row["id"]))
            if gt
            else None
        )
        bank_total = 0
        if dom in BANKS and topic_slug in BANKS.get(dom, {}):
            bank_total = len(
                get_questions_for_topic(dom, topic_slug, BANKS[dom][topic_slug])
            )
        attempt_answered_row = db.execute(
            """
            SELECT COUNT(DISTINCT question_index) AS c
            FROM practice_responses
            WHERE attempt_id = ? AND question_index IS NOT NULL
            """,
            (int(row["id"]),),
        ).fetchone()
        attempt_answered = (
            int(attempt_answered_row["c"] or 0) if attempt_answered_row else 0
        )
        session_complete = bank_total > 0 and attempt_answered >= bank_total
        if session_complete and summary_href:
            resume_href = summary_href
        elif dom and topic_slug:
            resume_href = url_for(
                "practice_question", domain=dom, topic=topic_slug, qnum=0
            )
        else:
            resume_href = None
        recent_sessions.append(
            {
                "track_short": _dashboard_track_short(dom),
                "topic": topic_title,
                "domain": dom,
                "topic_key": topic_slug,
                "score_label": f"{c}/{gt}" if gt else "Ungraded",
                "pct": _pct(c, gt),
                "summary_href": summary_href,
                "when_label": _session_when_label(row["created_at"]),
                "resume_href": resume_href,
                "resume_label": "View report" if session_complete else "Continue",
            }
        )

    compiled = load_compiled_bank()
    sat_bank_total = 0
    for key in ("1_1", "1_2", "1_3", "1_4", "1_5"):
        sat_bank_total += len(compiled.get("algebra", {}).get(key, []))
    for key in ("2_1", "2_2", "2_3"):
        sat_bank_total += len(compiled.get("advanced_math", {}).get(key, []))
    for u3k in ("3_1", "3_2", "3_3", "3_4", "3_5", "3_6", "3_7"):
        sat_bank_total += len(compiled.get("problem_solving", {}).get(u3k) or [])
    for u4k in ("4_1", "4_2", "4_3", "4_4"):
        sat_bank_total += len(compiled.get("geometry", {}).get(u4k) or [])

    u1_all = len(compiled.get("algebra", {}).get("unit_1_all") or [])
    u2_all = len(compiled.get("advanced_math", {}).get("unit_2_all") or [])
    u3_all = len(compiled.get("problem_solving", {}).get("unit_3_all") or [])
    u4_all = len(compiled.get("geometry", {}).get("unit_4_all") or [])
    sat_bank_cap = u1_all + u2_all + u3_all + u4_all
    if sat_bank_cap <= 0:
        sat_bank_cap = sat_bank_total
    sat_engaged = 0
    if sat_bank_cap > 0:
        sat_engaged += _practice_distinct_answered(db, user_id, "algebra", "unit_1_all")
        sat_engaged += _practice_distinct_answered(db, user_id, "advanced_math", "unit_2_all")
        sat_engaged += _practice_distinct_answered(db, user_id, "problem_solving", "unit_3_all")
        sat_engaged += _practice_distinct_answered(db, user_id, "geometry", "unit_4_all")
    sat_engagement_pct = (
        min(100, int(round(100 * sat_engaged / sat_bank_cap))) if sat_bank_cap else 0
    )

    def _unit_pct(eng: int, cap: int) -> int:
        return min(100, int(round(100 * eng / cap))) if cap else 0

    sat_unit_progress = [
        {
            "key": "unit_1",
            "domain": "algebra",
            "num": "1",
            "label": "Unit 1",
            "subtitle": "Algebra",
            "engaged": _practice_distinct_answered(db, user_id, "algebra", "unit_1_all"),
            "cap": u1_all,
            "href": url_for(
                "practice_question", domain="algebra", topic="unit_1_all", qnum=0
            ),
        },
        {
            "key": "unit_2",
            "domain": "advanced_math",
            "num": "2",
            "label": "Unit 2",
            "subtitle": "Advanced Math",
            "engaged": _practice_distinct_answered(
                db, user_id, "advanced_math", "unit_2_all"
            ),
            "cap": u2_all,
            "href": url_for(
                "practice_question",
                domain="advanced_math",
                topic="unit_2_all",
                qnum=0,
            ),
        },
        {
            "key": "unit_3",
            "domain": "problem_solving",
            "num": "3",
            "label": "Unit 3",
            "subtitle": "Problem Solving & Data",
            "engaged": _practice_distinct_answered(
                db, user_id, "problem_solving", "unit_3_all"
            ),
            "cap": u3_all,
            "href": url_for(
                "practice_question",
                domain="problem_solving",
                topic="unit_3_all",
                qnum=0,
            ),
        },
        {
            "key": "unit_4",
            "domain": "geometry",
            "num": "4",
            "label": "Unit 4",
            "subtitle": "Geometry",
            "engaged": _practice_distinct_answered(db, user_id, "geometry", "unit_4_all"),
            "cap": u4_all,
            "href": url_for(
                "practice_question", domain="geometry", topic="unit_4_all", qnum=0
            ),
        },
    ]
    dom_top_map = {
        "unit_1": ("algebra", "unit_1_all"),
        "unit_2": ("advanced_math", "unit_2_all"),
        "unit_3": ("problem_solving", "unit_3_all"),
        "unit_4": ("geometry", "unit_4_all"),
    }
    unit_desc = {
        "unit_1": "Linear equations through inequalities—five chapter slices, a full merged bank, and a 22-question practice test.",
        "unit_2": "Equivalent expressions, nonlinear equations, and nonlinear functions—three chapter slices, full bank, and practice test.",
        "unit_3": "Ratios, percentages, probability, charts, inference, and study design—seven chapter slices, full bank, and practice test.",
        "unit_4": "Volume and area, lines and triangles, trigonometry, and circles—four chapter slices, full bank, and practice test.",
    }
    for u in sat_unit_progress:
        u["pct"] = _unit_pct(int(u["engaged"]), int(u["cap"] or 0))
        cap = int(u.get("cap") or 0)
        engaged = int(u.get("engaged") or 0)
        dom = str(u.get("domain") or "")
        u["studio_href"] = url_for("practice_topics", domain=dom) if dom else ""
        part_id = MISS_PART_BY_DOMAIN.get(dom)
        u["miss_count"] = (
            len(_wrong_miss_items_for_module(db, user_id, part_id)) if part_id else 0
        )
        u["miss_href"] = (
            url_for("practice_miss_quiz_sat_module", part_id=part_id)
            if u["miss_count"] and part_id
            else None
        )
        dom_top = dom_top_map.get(str(u.get("key") or ""))
        u["report_href"] = (
            _practice_report_href(db, user_id, dom_top[0], dom_top[1], cap)
            if dom_top and cap
            else None
        )
        u["featured"] = str(u.get("num") or "") == "1"
        u["kicker"] = "Recommended start" if u["featured"] else "Focused slice"
        u["name"] = str(u.get("subtitle") or "")
        u["title"] = f"Unit {u['num']} – {u['subtitle']} (full bank)"
        u["desc"] = unit_desc.get(str(u.get("key") or ""), "")
        u["count"] = cap
        u["touched"] = engaged
        u["complete"] = cap > 0 and engaged >= cap
        if u["complete"] and u["report_href"]:
            u["cta_href"] = u["report_href"]
            u["cta_label"] = "View report"
        elif engaged:
            u["cta_href"] = u["href"]
            u["cta_label"] = "Continue full set"
        else:
            u["cta_href"] = u["href"]
            u["cta_label"] = "Start full set"
        if cap > 0 and engaged >= cap:
            if dom_top and u["report_href"]:
                u["href"] = u["report_href"]

    next_unit = next(
        (u for u in sat_unit_progress if int(u.get("cap") or 0) and int(u.get("pct") or 0) < 100),
        sat_unit_progress[0] if sat_unit_progress else None,
    )
    if next_unit:
        next_unit = dict(next_unit)
        remaining = max(0, int(next_unit.get("cap") or 0) - int(next_unit.get("engaged") or 0))
        next_unit["remaining"] = remaining

    resume_practice = None
    if recent_sessions:
        top = recent_sessions[0]
        if top.get("resume_href") and top.get("topic_key"):
            resume_practice = {
                "href": top["resume_href"],
                "line": f"{top['track_short']} · {top['topic']}",
                "when_label": top.get("when_label") or "",
                "label": top.get("resume_label") or "Continue last session",
            }

    return {
        "stats": {
            "attempts_total": int(attempts_total or 0),
            "total_graded": total_graded,
            "accuracy_pct": _pct(total_correct, total_graded),
            "tracks_live": 1,
            "tracks_planned": len(LEARNING_TRACKS) - 1,
            "sat_bank_total": sat_bank_total,
            "sat_bank_cap": sat_bank_cap,
            "sat_engaged": sat_engaged,
            "sat_engagement_pct": sat_engagement_pct,
            "wrong_total": wrong_total,
            "sat_remaining": max(0, sat_bank_cap - sat_engaged),
        },
        "dashboard_username": (session.get("username") or "").strip() or None,
        "sat_unit_progress": sat_unit_progress,
        "next_unit": next_unit,
        "resume_practice": resume_practice,
        "recent_sessions": recent_sessions,
        "focus_topics": focus_topics,
    }

# =====================================================
# ROUTES
# =====================================================


@app.route("/health")
def health():
    """For load balancers and hosting probes (no DB hit)."""
    return "ok", 200


@app.route("/health/db")
def health_db():
    """Verify SQLite path and persistence (for Render ops; no secrets)."""
    status = _db_persistence_status()
    ok = (
        status["persistence_ok"]
        and (status["db_exists"] or status["writable"])
        and status["user_count"] != 0
    )
    return jsonify(ok=ok, **status), (200 if ok else 503)


@app.route("/admin/data/backup-now", methods=["POST"])
def admin_backup_database_now():
    gate = _require_supervisor_response()
    if gate is not None:
        return gate

    path = _backup_database_now(force=True)
    if path:
        flash(f"Database backup saved ({os.path.basename(path)}).")
    else:
        flash("Backup skipped — persistent disk or database not available.")
    return redirect(url_for("admin"))


@app.route("/admin/data/download-backup")
def admin_download_database_backup():
    gate = _require_supervisor_response()
    if gate is not None:
        return gate

    path = _latest_backup_path()
    if not path or not os.path.isfile(path):
        abort(404, description="No backup file found on disk.")
    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path),
        mimetype="application/x-sqlite3",
    )


@app.route("/admin/data/download-db")
def admin_download_live_database():
    gate = _require_supervisor_response()
    if gate is not None:
        return gate

    if not os.path.isfile(DB_PATH):
        abort(404, description="Database file not found.")
    path = _backup_database_now(force=True)
    if not path or not os.path.isfile(path):
        abort(503, description="Could not create a database snapshot.")
    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path),
        mimetype="application/x-sqlite3",
    )


@app.route("/health/style")
def health_stylesheet_bundle():
    """JSON probe: confirms the large bundled CSS is on disk (no DB hit)."""
    try:
        sz = os.path.getsize(os.path.join(STATIC_DIR, "style.css"))
    except OSError:
        return jsonify(ok=False, error="style.css missing"), 500
    return jsonify(ok=True, bytes=sz, revision=STYLE_CSS_REVISION)


@app.route("/")
def index():
    grants = current_user_access_grants()
    if grants is not None and "dashboard" not in grants:
        return redirect(_student_home_url(grants))
    return render_template(
        "dashboard.html",
        tracks=LEARNING_TRACKS,
        **_dashboard_context(),
    )


@app.route("/guide")
def student_guide():
    """Public bilingual guide for students and parents."""
    return render_template("student_guide.html")


@app.route("/admin/export/students.csv")
def admin_export_students_csv():
    gate = _require_admin_response()
    if gate is not None:
        return gate

    db = get_db()
    students = _student_rows(db, "")
    compiled = load_compiled_bank()
    u_caps = {
        "u1": len(compiled.get("algebra", {}).get("unit_1_all") or []),
        "u2": len(compiled.get("advanced_math", {}).get("unit_2_all") or []),
        "u3": len(compiled.get("problem_solving", {}).get("unit_3_all") or []),
        "u4": len(compiled.get("geometry", {}).get("unit_4_all") or []),
    }

    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "username",
            "active",
            "access",
            "sessions",
            "responses",
            "accuracy_pct",
            "unit1_answered",
            "unit1_cap",
            "unit2_answered",
            "unit2_cap",
            "unit3_answered",
            "unit3_cap",
            "unit4_answered",
            "unit4_cap",
            "last_login_at",
            "last_activity",
            "created_at",
        ]
    )
    for s in students:
        uid = int(s["id"])
        u1 = _practice_distinct_answered(db, uid, "algebra", "unit_1_all")
        u2 = _practice_distinct_answered(db, uid, "advanced_math", "unit_2_all")
        u3 = _practice_distinct_answered(db, uid, "problem_solving", "unit_3_all")
        u4 = _practice_distinct_answered(db, uid, "geometry", "unit_4_all")
        writer.writerow(
            [
                s["username"],
                "yes" if s["is_active"] else "no",
                s.get("access_grants_label") or "All materials",
                s["attempts_total"],
                s["responses_total"],
                s["accuracy_pct"] if s["accuracy_pct"] is not None else "",
                u1,
                u_caps["u1"],
                u2,
                u_caps["u2"],
                u3,
                u_caps["u3"],
                u4,
                u_caps["u4"],
                s.get("last_login_at") or "",
                s.get("last_activity") or "",
                s.get("created_at") or "",
            ]
        )

    payload = buf.getvalue()
    filename = f"novel-prep-students-{date.today().isoformat()}.csv"
    return Response(
        payload,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/learn/<track_key>")
def learning_track(track_key: str):
    track = next((t for t in LEARNING_TRACKS if t["key"] == track_key), None)
    if track is None:
        return "Unknown learning track", 404
    session["active_track_label"] = track["title"]
    return render_template("learning_track.html", track=track)


def _full_bank_question_count(domain: str, full_key: str, tex_path: str) -> int:
    """Prefer compiled JSON slice; fall back to TeX parse only if missing."""
    compiled = load_compiled_bank()
    topic_questions = compiled.get(domain, {}).get(full_key)
    if isinstance(topic_questions, list) and topic_questions:
        return len(topic_questions)
    return len(get_questions_for_topic(domain, full_key, tex_path))


def _practice_workspace_counts() -> Dict[str, Any]:
    """Counts for /practice hero + cards; full-bank topics only (no double-counting slices)."""
    n_live = len(BANKS)
    out: Dict[str, Any] = {
        "pw_domains_live": n_live,
        "pw_domain_target": PRACTICE_DOMAIN_TARGET_COUNT,
        "pw_roadmap_units": max(0, PRACTICE_DOMAIN_TARGET_COUNT - n_live),
        "pw_workspace_progress_pct": min(
            100, int(round(100 * n_live / PRACTICE_DOMAIN_TARGET_COUNT))
        ),
        "pw_algebra_count": 0,
        "pw_advanced_math_count": 0,
        "pw_problem_solving_count": 0,
        "pw_geometry_count": 0,
        "pw_total_questions": 0,
        "pw_algebra_touched": 0,
        "pw_advanced_math_touched": 0,
        "pw_problem_solving_touched": 0,
        "pw_geometry_touched": 0,
        "pw_algebra_progress_pct": 0,
        "pw_advanced_math_progress_pct": 0,
        "pw_problem_solving_progress_pct": 0,
        "pw_geometry_progress_pct": 0,
        "pw_total_touched": 0,
        "pw_aggregate_progress_pct": 0,
    }
    for domain, topics in BANKS.items():
        full_key = (
            "unit_1_all"
            if domain == "algebra"
            else "unit_2_all"
            if domain == "advanced_math"
            else "unit_3_all"
            if domain == "problem_solving"
            else "unit_4_all"
            if domain == "geometry"
            else None
        )
        if not full_key or full_key not in topics:
            continue
        path = topics[full_key]
        n = _full_bank_question_count(domain, full_key, path)
        if domain == "algebra":
            out["pw_algebra_count"] = n
        elif domain == "advanced_math":
            out["pw_advanced_math_count"] = n
        elif domain == "problem_solving":
            out["pw_problem_solving_count"] = n
        elif domain == "geometry":
            out["pw_geometry_count"] = n
        out["pw_total_questions"] += n
    return out


def _practice_workspace_merge_progress(
    ctx: Dict[str, Any], db: sqlite3.Connection, user_id: Any
) -> None:
    """Fill per-unit and aggregate touched counts for the specialized workspace."""
    specs = (
        ("algebra", "unit_1_all", "pw_algebra"),
        ("advanced_math", "unit_2_all", "pw_advanced_math"),
        ("problem_solving", "unit_3_all", "pw_problem_solving"),
        ("geometry", "unit_4_all", "pw_geometry"),
    )
    touched_sum = 0
    for domain, topic, prefix in specs:
        total = int(ctx.get(f"{prefix}_count") or 0)
        touched = _practice_distinct_answered(db, user_id, domain, topic)
        ctx[f"{prefix}_touched"] = touched
        pct = min(100, int(round(100 * touched / total))) if total else 0
        ctx[f"{prefix}_progress_pct"] = pct
        complete = total > 0 and touched >= total
        ctx[f"{prefix}_complete"] = complete
        report_href = _practice_report_href(db, user_id, domain, topic, total)
        practice_href = url_for("practice_question", domain=domain, topic=topic, qnum=0)
        ctx[f"{prefix}_cta_href"] = report_href if complete and report_href else practice_href
        if complete:
            ctx[f"{prefix}_cta_label"] = "View report"
        elif touched:
            ctx[f"{prefix}_cta_label"] = "Continue full set"
        else:
            ctx[f"{prefix}_cta_label"] = "Start full set"
        touched_sum += touched
    ctx["pw_total_touched"] = touched_sum
    tot = int(ctx.get("pw_total_questions") or 0)
    ctx["pw_aggregate_progress_pct"] = (
        min(100, int(round(100 * touched_sum / tot))) if tot else 0
    )
    ctx["pw_logged_in"] = user_id is not None


def _practice_unit_atelier_cards(
    ctx: Dict[str, Any], db: sqlite3.Connection, user_id: Any
) -> List[dict]:
    """Premium bento card payloads for Units 1–4 (specialized + dashboard)."""
    units = (
        (
            "algebra",
            "unit_1_all",
            "pw_algebra",
            "1",
            "Algebra",
            "Linear equations through inequalities—five chapter slices.",
        ),
        (
            "advanced_math",
            "unit_2_all",
            "pw_advanced_math",
            "2",
            "Advanced Math",
            "Nonlinear equations, equivalent expressions, and advanced functions.",
        ),
        (
            "problem_solving",
            "unit_3_all",
            "pw_problem_solving",
            "3",
            "Problem Solving & Data",
            "Ratios, percentages, probability, charts, and study design.",
        ),
        (
            "geometry",
            "unit_4_all",
            "pw_geometry",
            "4",
            "Geometry",
            "Area, volume, triangles, trigonometry, and circles.",
        ),
    )
    cards: List[dict] = []
    for domain, topic, prefix, num, name, desc in units:
        total = int(ctx.get(f"{prefix}_count") or 0)
        touched = int(ctx.get(f"{prefix}_touched") or 0)
        pct = int(ctx.get(f"{prefix}_progress_pct") or 0)
        complete = bool(ctx.get(f"{prefix}_complete"))
        part_id = MISS_PART_BY_DOMAIN.get(domain)
        miss_count = (
            len(_wrong_miss_items_for_module(db, user_id, part_id)) if part_id else 0
        )
        miss_href = (
            url_for("practice_miss_quiz_sat_module", part_id=part_id)
            if miss_count and part_id
            else None
        )
        report_href = _practice_report_href(db, user_id, domain, topic, total)
        studio_href = url_for("practice_topics", domain=domain)
        slice_meta = _unit_chapter_slice_meta(domain)
        pdf_meta = next(
            (c for c in _unit_pdf_cards() if c.get("domain") == domain), None
        )
        pdf_href = (pdf_meta or {}).get("href") or None
        pdf_available = bool(pdf_meta and pdf_meta.get("available") and pdf_href)
        cards.append(
            {
                "domain": domain,
                "topic": topic,
                "num": num,
                "name": name,
                "title": f"Unit {num} – {name}",
                "desc": desc,
                "kicker": f"Unit {num}",
                "count": total,
                "touched": touched,
                "pct": pct,
                "complete": complete,
                "studio_href": studio_href,
                "report_href": report_href,
                "miss_href": miss_href,
                "miss_count": miss_count,
                "pdf_href": pdf_href if pdf_available else None,
                "pdf_available": pdf_available,
                **slice_meta,
            }
        )
    return cards


def _mistake_tags_json_from_form(form) -> str:
    allowed = {o["id"] for o in MISTAKE_TAG_OPTIONS}
    picked = sorted({x for x in form.getlist("mistake_tag") if x in allowed})
    return json.dumps(picked, ensure_ascii=False)


def _learner_key() -> str:
    """Stable per-account or per-browser key for mistake learning progress."""
    uid = session.get("user_id")
    if uid is not None:
        return f"u:{int(uid)}"
    if "np_guest_learner" not in session:
        session["np_guest_learner"] = secrets.token_urlsafe(20)
        session.modified = True
    return f"g:{session['np_guest_learner']}"


def _full_bank_topic_for_domain(domain: str) -> str | None:
    return {
        "algebra": "unit_1_all",
        "advanced_math": "unit_2_all",
        "problem_solving": "unit_3_all",
        "geometry": "unit_4_all",
        "placement": "placement_full",
    }.get(domain)


def _mistake_progress_on_wrong(
    db: sqlite3.Connection, learner_key: str, domain: str, topic: str, q_index: int
) -> None:
    db.execute(
        """
        INSERT INTO mistake_learning_progress
            (learner_key, domain, topic, question_index, status, correct_after_last_wrong, updated_at)
        VALUES (?, ?, ?, ?, 'unreviewed', 0, datetime('now'))
        ON CONFLICT(learner_key, domain, topic, question_index) DO UPDATE SET
            status = 'unreviewed',
            correct_after_last_wrong = 0,
            updated_at = datetime('now')
        """,
        (learner_key, domain, topic, q_index),
    )


def _mistake_progress_on_correct(
    db: sqlite3.Connection, learner_key: str, domain: str, topic: str, q_index: int
) -> None:
    row = db.execute(
        """
        SELECT correct_after_last_wrong, status
        FROM mistake_learning_progress
        WHERE learner_key = ? AND domain = ? AND topic = ? AND question_index = ?
        """,
        (learner_key, domain, topic, q_index),
    ).fetchone()
    if row is None:
        return
    n = int(row["correct_after_last_wrong"] or 0) + 1
    if n >= 2:
        st = "mastered"
    else:
        st = "redo_correct"
    db.execute(
        """
        UPDATE mistake_learning_progress
        SET correct_after_last_wrong = ?, status = ?, updated_at = datetime('now')
        WHERE learner_key = ? AND domain = ? AND topic = ? AND question_index = ?
        """,
        (n, st, learner_key, domain, topic, q_index),
    )


def _mistake_progress_mark_reviewed(
    db: sqlite3.Connection, learner_key: str, domain: str, topic: str, q_index: int
) -> None:
    row = db.execute(
        """
        SELECT status, correct_after_last_wrong
        FROM mistake_learning_progress
        WHERE learner_key = ? AND domain = ? AND topic = ? AND question_index = ?
        """,
        (learner_key, domain, topic, q_index),
    ).fetchone()
    if row is None:
        db.execute(
            """
            INSERT INTO mistake_learning_progress
                (learner_key, domain, topic, question_index, status, correct_after_last_wrong, updated_at)
            VALUES (?, ?, ?, ?, 'reviewed', 0, datetime('now'))
            """,
            (learner_key, domain, topic, q_index),
        )
        return
    st = str(row["status"] or "")
    if st in ("redo_correct", "mastered"):
        return
    db.execute(
        """
        UPDATE mistake_learning_progress
        SET status = 'reviewed', updated_at = datetime('now')
        WHERE learner_key = ? AND domain = ? AND topic = ? AND question_index = ?
        """,
        (learner_key, domain, topic, q_index),
    )


def _mistake_progress_force_mastered(
    db: sqlite3.Connection, learner_key: str, domain: str, topic: str, q_index: int
) -> None:
    db.execute(
        """
        INSERT INTO mistake_learning_progress
            (learner_key, domain, topic, question_index, status, correct_after_last_wrong, updated_at)
        VALUES (?, ?, ?, ?, 'mastered', 2, datetime('now'))
        ON CONFLICT(learner_key, domain, topic, question_index) DO UPDATE SET
            status = 'mastered',
            correct_after_last_wrong = 2,
            updated_at = datetime('now')
        """,
        (learner_key, domain, topic, q_index),
    )


def _mistake_progress_revert_mastered(
    db: sqlite3.Connection, learner_key: str, domain: str, topic: str, q_index: int
) -> bool:
    """Undo a mistaken 'mastered' mark; slot goes back to reviewed (redo ladder resets)."""
    row = db.execute(
        """
        SELECT status FROM mistake_learning_progress
        WHERE learner_key = ? AND domain = ? AND topic = ? AND question_index = ?
        """,
        (learner_key, domain, topic, q_index),
    ).fetchone()
    if row is None or str(row["status"] or "") != "mastered":
        return False
    db.execute(
        """
        UPDATE mistake_learning_progress
        SET status = 'reviewed', correct_after_last_wrong = 0, updated_at = datetime('now')
        WHERE learner_key = ? AND domain = ? AND topic = ? AND question_index = ?
        """,
        (learner_key, domain, topic, q_index),
    )
    return True


def _mistake_similar_links(
    domain: str, topic: str, q_index: int, knowledge_section: str, limit: int = 3
) -> List[dict]:
    tex_file = BANKS.get(domain, {}).get(topic)
    if not tex_file:
        return []
    questions = get_questions_for_topic(domain, topic, tex_file)
    if not questions:
        return []
    same_sec: List[int] = []
    rest: List[int] = []
    for i, q in enumerate(questions):
        if i == q_index:
            continue
        if knowledge_section and q.get("knowledge_section") == knowledge_section:
            same_sec.append(i)
        else:
            rest.append(i)
    ordered = same_sec + rest
    out: List[dict] = []
    for i in ordered[:limit]:
        q = questions[i]
        out.append(
            {
                "q_index": i,
                "label": f"Q{i + 1}",
                "href": url_for("practice_question", domain=domain, topic=topic, qnum=i),
                "skill": (q.get("knowledge_section_title_en") or "")[:72],
            }
        )
    return out


def _mistake_mixed_review_href(domain: str) -> str | None:
    fb = _full_bank_topic_for_domain(domain)
    if not fb or fb not in BANKS.get(domain, {}):
        return None
    return url_for("practice_question", domain=domain, topic=fb, qnum=0)


SECTION_FAMILY_HINTS: Dict[str, Dict[str, Any]] = {
    "_": {
        "keywords": ["given", "target", "units", "equation"],
        "playbook": "Restate what you are solving for, then translate one sentence at a time into math.",
        "pitfall": "Answering a nearby quantity (like perimeter when area was asked).",
    },
    "1.": {
        "keywords": ["linear", "equation", "slope", "intercept", "system"],
        "playbook": "Isolate the variable with legal moves; for systems, match coefficients or substitute cleanly.",
        "pitfall": "Distributive sign errors and forgetting to flip the inequality when multiplying by a negative.",
    },
    "2.": {
        "keywords": ["quadratic", "exponent", "factor", "function", "vertex"],
        "playbook": "Identify structure (factored vs expanded), domain restrictions, and where the graph hits axes.",
        "pitfall": "Extraneous solutions after squaring; losing track of exponent rules on negative bases.",
    },
    "3.": {
        "keywords": ["ratio", "percent", "table", "probability", "sample", "units"],
        "playbook": "Write two clear fractions or percents and set up a proportion; label every column in tables.",
        "pitfall": "Using the wrong denominator for conditional probability or percent change.",
    },
    "4.": {
        "keywords": ["triangle", "circle", "angle", "length", "volume", "trig"],
        "playbook": "Draw or mark the figure; decide which theorem (Pythagorean, similar triangles, SOHCAHTOA) fits.",
        "pitfall": "Mixing up radius vs diameter, or using the wrong triangle pair for similarity.",
    },
}


def _section_family_prefix(knowledge_section: str) -> str:
    s = (knowledge_section or "").strip()
    if len(s) >= 2 and s[1] == ".":
        return s[:2]
    return "_"


STUDENT_DIAGNOSIS_PLAIN: Dict[str, str] = {
    "concept": "You likely need a cleaner rule in mind before computing—name the idea, then redo slowly.",
    "setup": "The story probably turned into the wrong model—lock variables and units before you crunch numbers.",
    "execution": "Your plan may be fine; the slip is in algebra, substitution, or arithmetic—check signs twice.",
    "reading": "You may have solved a different question than the one asked—underline the exact target phrase.",
    "pacing": "This miss may be from rushing or guessing—decide solve vs skip earlier, then return with fresh eyes.",
    "pattern": "The same skill keeps showing up—treat it as one mini-unit until the first step feels automatic.",
}


def _mistake_pattern_pack(row: dict) -> dict:
    did = str(row.get("diagnosis_id") or "concept")
    if did not in DIAGNOSIS_MODEL:
        did = "concept"
    dm = DIAGNOSIS_MODEL[did]
    fam = _section_family_prefix(str(row.get("knowledge_section") or ""))
    cat = SECTION_FAMILY_HINTS.get(fam) or SECTION_FAMILY_HINTS["_"]
    plain = STUDENT_DIAGNOSIS_PLAIN.get(did, STUDENT_DIAGNOSIS_PLAIN["concept"])
    return {
        "diagnosis_id": did,
        "title": dm["label"],
        "student_line": f"{dm['short']} — {plain}",
        "coach_move": dm["action"],
        "keywords": list(cat.get("keywords") or []),
        "playbook": str(cat.get("playbook") or ""),
        "pitfall": str(cat.get("pitfall") or ""),
    }


def _analytics_wrong_rows(db: sqlite3.Connection, user_id: Any) -> List[dict]:
    """Recent incorrect attempts for the mistake log (optionally scoped to user)."""
    tracked_sql = _tracked_attempt_sql("pa")
    if user_id is not None:
        rows = db.execute(
            f"""
            SELECT pr.id AS pr_id, pr.submitted_at, pr.question_index,
                   pr.selected_answer, pr.correct_answer, pr.mistake_tags, pr.mistake_note,
                   pa.domain, pa.topic
            FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pr.is_correct = 0 AND pr.question_index IS NOT NULL
              AND pa.user_id IS ?
              AND {tracked_sql}
            ORDER BY pr.submitted_at DESC
            LIMIT 200
            """,
            (user_id,),
        ).fetchall()
    else:
        rows = db.execute(
            f"""
            SELECT pr.id AS pr_id, pr.submitted_at, pr.question_index,
                   pr.selected_answer, pr.correct_answer, pr.mistake_tags, pr.mistake_note,
                   pa.domain, pa.topic
            FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pr.is_correct = 0 AND pr.question_index IS NOT NULL
              AND pa.user_id IS NULL
              AND {tracked_sql}
            ORDER BY pr.submitted_at DESC
            LIMIT 200
            """,
        ).fetchall()

    id_to_label = {o["id"]: o["label"] for o in MISTAKE_TAG_OPTIONS}
    question_meta_cache: Dict[tuple[str, str], List[dict]] = {}

    def _question_meta(domain: str, topic: str, q_index: int) -> dict:
        cache_key = (domain, topic)
        if cache_key not in question_meta_cache:
            tex_file = BANKS.get(domain, {}).get(topic)
            question_meta_cache[cache_key] = (
                get_questions_for_topic(domain, topic, tex_file) if tex_file else []
            )
        questions = question_meta_cache.get(cache_key) or []
        if q_index < 0 or q_index >= len(questions):
            return {}
        q = questions[q_index]
        return q if isinstance(q, dict) else {}

    out: List[dict] = []
    for r in rows:
        q_index = int(r["question_index"])
        meta = _question_meta(str(r["domain"]), str(r["topic"]), q_index)
        tags_raw = r["mistake_tags"]
        tag_labels: List[str] = []
        if tags_raw:
            try:
                arr = json.loads(tags_raw)
                if isinstance(arr, list):
                    tag_labels = [id_to_label.get(x, x) for x in arr if isinstance(x, str)]
            except (json.JSONDecodeError, TypeError):
                tag_labels = [str(tags_raw)]
        tag_ids: List[str] = []
        if tags_raw:
            try:
                arr = json.loads(tags_raw)
                if isinstance(arr, list):
                    tag_ids = [x for x in arr if isinstance(x, str)]
            except (json.JSONDecodeError, TypeError):
                pass
        out.append(
            {
                "pr_id": r["pr_id"],
                "when": r["submitted_at"],
                "domain": r["domain"],
                "topic": r["topic"],
                "topic_title": TOPIC_TITLES.get(r["topic"], r["topic"]),
                "q_index": q_index,
                "knowledge_section": meta.get("knowledge_section") or "",
                "knowledge_title": (
                    meta.get("knowledge_section_title_en")
                    or TOPIC_TITLES.get(r["topic"], r["topic"])
                ),
                "question_kind": meta.get("question_kind") or "mcq",
                "yours": r["selected_answer"] or "—",
                "key": r["correct_answer"] or "—",
                "tag_labels": tag_labels,
                "tag_ids": tag_ids,
                "note": (r["mistake_note"] or "").strip(),
                "practice_href": url_for(
                    "practice_question",
                    domain=r["domain"],
                    topic=r["topic"],
                    qnum=int(r["question_index"]),
                    mistake_redo=1,
                    analytics_part=MISS_PART_BY_DOMAIN.get(str(r["domain"]), ""),
                    miss_anchor=f"np-miss-pr-{r['pr_id']}",
                ),
            }
        )
    if not out:
        return out
    lk = _learner_key()
    pmap_rows = db.execute(
        """
        SELECT domain, topic, question_index, status, correct_after_last_wrong
        FROM mistake_learning_progress
        WHERE learner_key = ?
        """,
        (lk,),
    ).fetchall()
    pmap: Dict[tuple[str, str, int], dict] = {}
    for pr in pmap_rows:
        pmap[(str(pr["domain"]), str(pr["topic"]), int(pr["question_index"]))] = {
            "status": str(pr["status"] or "unreviewed"),
            "correct_after_last_wrong": int(pr["correct_after_last_wrong"] or 0),
        }
    labels = {
        "unreviewed": "Unreviewed",
        "reviewed": "Reviewed",
        "redo_correct": "Redo correct",
        "mastered": "Mastered",
    }
    for item in out:
        key = (item["domain"], item["topic"], item["q_index"])
        pr = pmap.get(key)
        db_status = pr["status"] if pr else "unreviewed"
        if db_status == "unreviewed" and (item.get("tag_ids") or item.get("note")):
            effective = "reviewed"
        else:
            effective = db_status
        item["mastery_effective"] = effective
        item["mastery_db_status"] = db_status
        item["mastery_label"] = labels.get(effective, effective.title())
        item["similar_questions"] = _mistake_similar_links(
            item["domain"],
            item["topic"],
            item["q_index"],
            str(item.get("knowledge_section") or ""),
        )
        item["mixed_review_href"] = _mistake_mixed_review_href(item["domain"])
    return out


DIAGNOSIS_MODEL: Dict[str, Dict[str, str]] = {
    "concept": {
        "label": "Concept gap",
        "short": "Know-what issue",
        "action": "Relearn the rule, then redo 3 untimed questions from the same skill before mixing topics.",
    },
    "setup": {
        "label": "Setup / modeling",
        "short": "Translation issue",
        "action": "Before calculating, write the quantities, units, and target variable in one scratch line.",
    },
    "execution": {
        "label": "Execution slip",
        "short": "Know-how issue",
        "action": "Use a two-pass check: recompute signs, arithmetic, and substitution before selecting.",
    },
    "reading": {
        "label": "Prompt precision",
        "short": "Read-the-task issue",
        "action": "Circle the exact ask: value, expression, percent change, or total. Answer only that target.",
    },
    "pacing": {
        "label": "Pacing / guessing",
        "short": "Time allocation issue",
        "action": "Set a 60-second decision point: solve, backsolve, or skip and return.",
    },
    "pattern": {
        "label": "Repeated skill cluster",
        "short": "Pattern detected",
        "action": "Block-review this skill until you can explain the first step without seeing choices.",
    },
}


def _diagnosis_for_row(row: dict, skill_counts: Dict[str, int]) -> str:
    tag_ids = set(row.get("tag_ids") or [])
    if "concept" in tag_ids:
        return "concept"
    if "setup" in tag_ids:
        return "setup"
    if "algebra" in tag_ids or "careless" in tag_ids:
        return "execution"
    if "reading" in tag_ids:
        return "reading"
    if "time" in tag_ids or "guess" in tag_ids:
        return "pacing"
    skill_key = row.get("knowledge_section") or row.get("topic") or ""
    if skill_key and skill_counts.get(skill_key, 0) >= 2:
        return "pattern"
    return "concept"


def _build_mistake_classifier(rows: List[dict]) -> dict:
    """Lightweight rule-based classifier for actionable mistake analytics."""
    total = len(rows)
    empty = {
        "total": 0,
        "health_score": 100,
        "primary": None,
        "diagnoses": [],
        "diagnosis_groups": [],
        "skills": [],
        "review_plan": [],
    }
    if not rows:
        return empty

    skill_counts: Dict[str, int] = defaultdict(int)
    skill_titles: Dict[str, str] = {}
    skill_hrefs: Dict[str, str] = {}
    for row in rows:
        skill_key = row.get("knowledge_section") or row.get("topic") or "unknown"
        skill_counts[skill_key] += 1
        skill_titles[skill_key] = row.get("knowledge_title") or row.get("topic_title") or skill_key
        skill_hrefs[skill_key] = row.get("practice_href") or "#"

    diagnosis_counts: Dict[str, int] = defaultdict(int)
    diagnosis_examples: Dict[str, List[str]] = defaultdict(list)
    tagged_count = 0
    for row in rows:
        if row.get("tag_ids"):
            tagged_count += 1
        diagnosis_id = _diagnosis_for_row(row, skill_counts)
        row["diagnosis_id"] = diagnosis_id
        row["diagnosis_label"] = DIAGNOSIS_MODEL[diagnosis_id]["label"]
        row["pattern_pack"] = _mistake_pattern_pack(row)
        diagnosis_counts[diagnosis_id] += 1
        topic = row.get("knowledge_title") or row.get("topic_title")
        if topic and topic not in diagnosis_examples[diagnosis_id]:
            diagnosis_examples[diagnosis_id].append(topic)

    diagnoses: List[dict] = []
    for diagnosis_id, count in sorted(diagnosis_counts.items(), key=lambda x: -x[1]):
        model = DIAGNOSIS_MODEL[diagnosis_id]
        pct = round(100 * count / total)
        confidence = min(96, 46 + count * 10 + (6 if tagged_count else 0))
        level = "High" if pct >= 45 or count >= 4 else "Medium" if pct >= 22 or count >= 2 else "Low"
        diagnoses.append(
            {
                "id": diagnosis_id,
                "label": model["label"],
                "short": model["short"],
                "action": model["action"],
                "count": count,
                "pct": pct,
                "confidence": confidence,
                "level": level,
                "evidence": diagnosis_examples[diagnosis_id][:3],
            }
        )

    diagnosis_groups: List[dict] = []
    for diagnosis in diagnoses:
        grouped_rows = [
            row for row in rows if row.get("diagnosis_id") == diagnosis["id"]
        ]
        group_skill_counts: Dict[str, int] = defaultdict(int)
        for row in grouped_rows:
            group_skill_counts[row.get("knowledge_title") or row.get("topic_title") or "Other"] += 1
        diagnosis_groups.append(
            {
                **diagnosis,
                "rows": grouped_rows,
                "skill_summary": [
                    {"title": title, "count": count}
                    for title, count in sorted(group_skill_counts.items(), key=lambda x: -x[1])
                ],
            }
        )

    skills: List[dict] = []
    for skill_key, count in sorted(skill_counts.items(), key=lambda x: -x[1])[:6]:
        pct = round(100 * count / total)
        skills.append(
            {
                "key": skill_key,
                "title": skill_titles.get(skill_key, skill_key),
                "count": count,
                "pct": pct,
                "href": skill_hrefs.get(skill_key, "#"),
                "risk": "High" if count >= 3 or pct >= 35 else "Medium" if count >= 2 else "Watch",
            }
        )

    review_plan = []
    if diagnoses:
        primary = diagnoses[0]
        review_plan.append(f"Start with {primary['label'].lower()}: {primary['action']}")
    if skills:
        review_plan.append(f"Redo the top cluster: {skills[0]['title']} ({skills[0]['count']} miss(es)).")
    if tagged_count < max(3, total // 2):
        review_plan.append("Tag more missed questions after each set so the classifier becomes sharper.")

    health_score = max(0, min(100, 100 - total * 3 - max(skill_counts.values()) * 4))
    return {
        "total": total,
        "health_score": health_score,
        "primary": diagnoses[0] if diagnoses else None,
        "diagnoses": diagnoses,
        "diagnosis_groups": diagnosis_groups,
        "skills": skills,
        "review_plan": review_plan,
    }


SAT_ANALYTICS_UNITS: Dict[str, Dict[str, Any]] = {
    "algebra": {
        "id": "sat-unit-1",
        "label": "Unit 1",
        "subtitle": "Algebra",
        "order": 1,
    },
    "advanced_math": {
        "id": "sat-unit-2",
        "label": "Unit 2",
        "subtitle": "Advanced Math",
        "order": 2,
    },
    "problem_solving": {
        "id": "sat-unit-3",
        "label": "Unit 3",
        "subtitle": "Problem Solving & Data",
        "order": 3,
    },
    "geometry": {
        "id": "sat-unit-4",
        "label": "Unit 4",
        "subtitle": "Geometry",
        "order": 4,
    },
}

# Mistake analytics + miss-quiz are organized by these SAT modules (1.1–1.5 = Unit 1, etc.).
SAT_MISS_MODULE_SPECS: List[Dict[str, Any]] = [
    {
        "part_id": "unit1",
        "label": "Unit 1 – Algebra",
        "subtitle": "Sections 1.1–1.5 + Practice Test (full bank + topic slices)",
        "domain": "algebra",
        "topics": ("unit_1_all", "1_1", "1_2", "1_3", "1_4", "1_5", "1_pt"),
        "order": 1,
    },
    {
        "part_id": "unit2",
        "label": "Unit 2 – Advanced Math",
        "subtitle": "Sections 2.1–2.3 + Practice Test (full bank + topic slices)",
        "domain": "advanced_math",
        "topics": ("unit_2_all", "2_1", "2_2", "2_3", "2_pt"),
        "order": 2,
    },
    {
        "part_id": "unit3",
        "label": "Unit 3 – Problem Solving & Data",
        "subtitle": "Sections 3.1–3.7",
        "domain": "problem_solving",
        "topics": (
            "unit_3_all",
            "3_1",
            "3_2",
            "3_3",
            "3_4",
            "3_5",
            "3_6",
            "3_7",
            "3_pt",
        ),
        "order": 3,
    },
    {
        "part_id": "unit4",
        "label": "Unit 4 – Geometry",
        "subtitle": "Sections 4.1–4.4",
        "domain": "geometry",
        "topics": ("unit_4_all", "4_1", "4_2", "4_3", "4_4", "4_pt"),
        "order": 4,
    },
]

MISS_PART_BY_DOMAIN: Dict[str, str] = {
    "algebra": "unit1",
    "advanced_math": "unit2",
    "problem_solving": "unit3",
    "geometry": "unit4",
    "hard_problem": "hard",
}


def _miss_module_spec(part_id: str) -> Dict[str, Any] | None:
    for s in SAT_MISS_MODULE_SPECS:
        if s["part_id"] == part_id:
            return s
    return None


def _knowledge_section_sort_key(sec: str) -> tuple:
    s = (sec or "").strip()
    if not s or s in ("—", "-", "Other"):
        return (99, 99, s)
    if s.lower().startswith("unit "):
        try:
            n = int(s.split()[1])
            return (n, 0, s)
        except (ValueError, IndexError):
            pass
    parts = s.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        return (major, minor, s)
    except ValueError:
        return (50, 0, s)


def _wrong_miss_items_for_module(
    db: sqlite3.Connection, user_id: Any, part_id: str
) -> List[dict]:
    spec = _miss_module_spec(part_id)
    if not spec:
        return []
    domain = str(spec["domain"])
    topics = list(spec["topics"])
    ph = ",".join("?" * len(topics))
    tracked_sql = _tracked_attempt_sql("pa")
    if user_id is not None:
        rows = db.execute(
            f"""
            SELECT DISTINCT pa.topic AS t, pr.question_index AS qi
            FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pr.is_correct = 0
              AND pr.question_index IS NOT NULL
              AND pa.domain = ?
              AND pa.topic IN ({ph})
              AND pa.user_id IS ?
              AND {tracked_sql}
            ORDER BY pa.topic, pr.question_index
            """,
            (domain, *topics, user_id),
        ).fetchall()
    else:
        rows = db.execute(
            f"""
            SELECT DISTINCT pa.topic AS t, pr.question_index AS qi
            FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pr.is_correct = 0
              AND pr.question_index IS NOT NULL
              AND pa.domain = ?
              AND pa.topic IN ({ph})
              AND pa.user_id IS NULL
              AND {tracked_sql}
            """,
            (domain, *topics),
        ).fetchall()
    seen: set[tuple[str, int]] = set()
    out: List[dict] = []
    for r in rows:
        t = str(r["t"])
        qi = int(r["qi"])
        key = (t, qi)
        if key in seen:
            continue
        seen.add(key)
        out.append({"domain": domain, "topic": t, "q_index": qi})
    return out


def _placement_analytics_unit(q_index: int) -> dict:
    if q_index < 15:
        return {
            "id": "placement-part-i",
            "label": "Part I",
            "subtitle": "Foundations & algebra",
            "order": 1,
        }
    if q_index < 30:
        return {
            "id": "placement-part-ii",
            "label": "Part II",
            "subtitle": "Exponents, rationals & functions",
            "order": 2,
        }
    if q_index < 45:
        return {
            "id": "placement-part-iii",
            "label": "Part III",
            "subtitle": "Graphs, geometry & radicals",
            "order": 3,
        }
    if q_index < 60:
        return {
            "id": "placement-part-iv",
            "label": "Part IV",
            "subtitle": "Functions, trig & precalc",
            "order": 4,
        }
    return {
        "id": "placement-part-v",
        "label": "Part V",
        "subtitle": "Geometry & advanced readiness",
        "order": 5,
    }


def _analytics_unit_for_row(row: dict) -> dict:
    domain = row.get("domain")
    if domain in SAT_ANALYTICS_UNITS:
        return dict(SAT_ANALYTICS_UNITS[str(domain)])
    if domain == "placement":
        return _placement_analytics_unit(int(row.get("q_index") or 0))
    return {
        "id": f"other-{domain or 'practice'}",
        "label": str(domain or "Other"),
        "subtitle": "Other practice",
        "order": 99,
    }


def _analytics_partitions(rows: List[dict]) -> List[dict]:
    """Mistake analytics: SAT (parent) → Units 1–4, then Placement and Other."""
    partitions: List[dict] = []
    used_domains: set[str] = set()
    sat_unit_parts: List[dict] = []

    for mod in sorted(SAT_MISS_MODULE_SPECS, key=lambda x: x["order"]):
        topic_set = set(mod["topics"])
        domain = str(mod["domain"])
        part_rows = [
            r
            for r in rows
            if r.get("domain") == domain and str(r.get("topic") or "") in topic_set
        ]
        if not part_rows:
            continue
        used_domains.add(domain)
        sec_buckets: Dict[str, List[dict]] = defaultdict(list)
        for row in part_rows:
            sec = str(row.get("knowledge_section") or "").strip() or "—"
            sec_buckets[sec].append(row)
        units: List[dict] = []
        for sec, urows in sorted(sec_buckets.items(), key=lambda x: _knowledge_section_sort_key(x[0])):
            sec_id = sec.replace(".", "-").replace(" ", "-")
            if not sec_id or sec_id == "—":
                sec_id = "misc"
            um = SAT_ANALYTICS_UNITS.get(domain, {})
            units.append(
                {
                    "id": f"{mod['part_id']}-sec-{sec_id}",
                    "label": sec if sec != "—" else "Section TBD",
                    "subtitle": (urows[0].get("knowledge_title") or um.get("subtitle") or "")[:120],
                    "order": _knowledge_section_sort_key(sec)[0] * 10
                    + _knowledge_section_sort_key(sec)[1],
                    "rows": urows,
                    "count": len(urows),
                    "classifier": _build_mistake_classifier(urows),
                }
            )
        full_bank_topic = str(mod["topics"][0])
        sat_unit_parts.append(
            {
                "id": mod["part_id"],
                "label": mod["label"],
                "subtitle": mod["subtitle"],
                "count": len(part_rows),
                "classifier": _build_mistake_classifier(part_rows),
                "domains": {domain},
                "unit_module_id": mod["part_id"],
                "units": units,
                "practice_domain": domain,
                "practice_topic": full_bank_topic,
            }
        )

    if sat_unit_parts:
        for mod in SAT_MISS_MODULE_SPECS:
            used_domains.add(str(mod["domain"]))
        hard_rows = [r for r in rows if r.get("domain") == "hard_problem"]
        if hard_rows:
            used_domains.add("hard_problem")
            hard_buckets: Dict[str, List[dict]] = defaultdict(list)
            for row in hard_rows:
                sec = str(row.get("knowledge_section") or "").strip() or "—"
                hard_buckets[sec].append(row)
            hard_units: List[dict] = []
            for sec in ("Unit 1", "Unit 2", "Unit 3", "Unit 4"):
                urows = hard_buckets.get(sec, [])
                if not urows:
                    continue
                sec_id = sec.replace(" ", "-").lower()
                hard_units.append(
                    {
                        "id": f"hard-{sec_id}",
                        "label": sec,
                        "subtitle": (urows[0].get("knowledge_title") or "")[:120],
                        "order": _knowledge_section_sort_key(sec)[0],
                        "rows": urows,
                        "count": len(urows),
                        "classifier": _build_mistake_classifier(urows),
                    }
                )
            sat_unit_parts.append(
                {
                    "id": "hard",
                    "label": "Hard Problem Drill",
                    "subtitle": "Hard sets I–XVI · classified by SAT unit",
                    "count": len(hard_rows),
                    "classifier": _build_mistake_classifier(hard_rows),
                    "domains": {"hard_problem"},
                    "unit_module_id": "hard",
                    "units": hard_units,
                }
            )
        sat_all_rows: List[dict] = []
        for p in sat_unit_parts:
            for u in p["units"]:
                sat_all_rows.extend(u["rows"])
        dom_union: set[str] = set()
        for p in sat_unit_parts:
            dom_union |= set(p.get("domains") or set())
        partitions.append(
            {
                "id": "sat",
                "label": "SAT Math",
                "subtitle": "Digital SAT math · open a unit to drill mistakes",
                "count": len(sat_all_rows),
                "classifier": _build_mistake_classifier(sat_all_rows),
                "domains": dom_union,
                "unit_module_id": "sat",
                "units": [],
                "sat_children": sat_unit_parts,
            }
        )

    placement_rows = [r for r in rows if r.get("domain") == "placement"]
    used_domains.add("placement")
    if placement_rows:
        unit_buckets: Dict[str, dict] = {}
        for row in placement_rows:
            unit_meta = _placement_analytics_unit(int(row.get("q_index") or 0))
            row["analytics_unit_label"] = unit_meta["label"]
            row["analytics_unit_subtitle"] = unit_meta["subtitle"]
            bucket = unit_buckets.setdefault(
                unit_meta["id"],
                {
                    **unit_meta,
                    "rows": [],
                },
            )
            bucket["rows"].append(row)
        units = []
        for unit in sorted(unit_buckets.values(), key=lambda x: x["order"]):
            unit_rows = unit["rows"]
            units.append(
                {
                    **unit,
                    "count": len(unit_rows),
                    "classifier": _build_mistake_classifier(unit_rows),
                }
            )
        partitions.append(
            {
                "id": "placement",
                "label": "Placement Test",
                "subtitle": "Course placement diagnostic mistakes only",
                "count": len(placement_rows),
                "classifier": _build_mistake_classifier(placement_rows),
                "domains": {"placement"},
                "unit_module_id": "placement",
                "units": units,
            }
        )

    other_rows = [r for r in rows if r.get("domain") not in used_domains]
    if other_rows:
        partitions.append(
            {
                "id": "other",
                "label": "Other Practice",
                "subtitle": "Mistakes outside tracked SAT units and placement",
                "count": len(other_rows),
                "classifier": _build_mistake_classifier(other_rows),
                "domains": set(),
                "unit_module_id": "other",
                "units": [
                    {
                        "id": "other-all",
                        "label": "Other",
                        "subtitle": "Other practice",
                        "order": 99,
                        "rows": other_rows,
                        "count": len(other_rows),
                        "classifier": _build_mistake_classifier(other_rows),
                    }
                ],
            }
        )
    return partitions


def _analytics_partition_by_id(partitions: List[dict], part_id: str) -> dict | None:
    """Resolve ?part= (top-level SAT / placement / other, or nested unit1–4 under SAT)."""
    if not part_id:
        return None
    for p in partitions:
        if p["id"] == part_id:
            return p
        for ch in p.get("sat_children") or []:
            if ch["id"] == part_id:
                return ch
    return None


def _analytics_partition_flat_rows(partition: Optional[dict]) -> List[dict]:
    """All mistake rows belonging to one analytics dashboard (SAT subtree, placement, …)."""
    if not partition:
        return []
    rows: List[dict] = []
    if partition.get("sat_children"):
        for ch in partition["sat_children"]:
            for u in ch.get("units") or []:
                rows.extend(u.get("rows") or [])
        return rows
    for u in partition.get("units") or []:
        rows.extend(u.get("rows") or [])
    return rows


def _analytics_learning_loop_snapshot(
    rows: List[dict], classifier: Dict[str, Any]
) -> Dict[str, Any]:
    """Per-dashboard stats for the 4-layer learning loop UI (mistake analytics)."""
    total = len(rows)
    mastery_order = ("unreviewed", "reviewed", "redo_correct", "mastered")
    mastery_counts: Dict[str, int] = {k: 0 for k in mastery_order}
    for r in rows:
        eff = str(r.get("mastery_effective") or "unreviewed")
        if eff in mastery_counts:
            mastery_counts[eff] += 1
        else:
            mastery_counts["unreviewed"] += 1
    kp_keys: set[str] = set()
    for r in rows:
        sec = str(r.get("knowledge_section") or "").strip()
        kt = str(r.get("knowledge_title") or "").strip()
        kp_keys.add(sec or kt or str(r.get("topic_title") or r.get("topic") or ""))
    kp_touchpoints = len([k for k in kp_keys if k]) or (1 if total else 0)

    mastery_human = {
        "unreviewed": ("Unreviewed", "Captured in the log; add tags or notes to move forward."),
        "reviewed": ("Reviewed", "You reflected after the miss."),
        "redo_correct": ("Redo correct", "One solid correct since the mistake."),
        "mastered": ("Mastered", "Two consecutive corrects, or manually marked mastered."),
    }
    mastery_ladder = []
    for k in mastery_order:
        mh = mastery_human.get(
            k, (k.replace("_", " ").title(), "")
        )
        mastery_ladder.append(
            {
                "id": k,
                "title": mh[0],
                "hint": mh[1],
                "count": mastery_counts[k],
            }
        )

    diagnoses = classifier.get("diagnoses") or []
    primary = classifier.get("primary")
    tagged_count = sum(1 for r in rows if (r.get("tag_ids") or []))

    return {
        "total": total,
        "mastery_order": mastery_order,
        "mastery_counts": mastery_counts,
        "kp_touchpoints": kp_touchpoints,
        "tagged_count": tagged_count,
        "tagged_pct": round(100 * tagged_count / total) if total else 0,
        "diagnosis_cards": len(diagnoses),
        "primary_cause_label": primary.get("label") if isinstance(primary, dict) else None,
        "primary_cause_pct": primary.get("pct") if isinstance(primary, dict) else None,
        "mastery_ladder": mastery_ladder,
    }


_ANALYTICS_VIZ_PART_COLORS: Dict[str, str] = {
    "sat": "#5b4dff",
    "placement": "#0d9488",
    "other": "#78716c",
    "unit1": "#4f46e5",
    "unit2": "#7c3aed",
    "unit3": "#db2777",
    "unit4": "#ea580c",
    "hard": "#6366f1",
}


def _viz_analytics_partition_color(part_id: str, index: int) -> str:
    pid = (part_id or "").strip().lower()
    if pid in _ANALYTICS_VIZ_PART_COLORS:
        return _ANALYTICS_VIZ_PART_COLORS[pid]
    return f"hsl({(218 + index * 41) % 360} 58% 52%)"


def _viz_analytics_hero_conic_gradient(parts: List[dict]) -> str | None:
    """Conic gradient stops from partition % shares (Track split / hero donut)."""
    segs: List[str] = []
    pos = 0.0
    for i, p in enumerate(parts):
        pct = float(p.get("pct") or 0)
        if pct <= 0:
            continue
        col = str(p.get("viz_color") or _viz_analytics_partition_color(str(p.get("id") or ""), i))
        a, b = pos, pos + pct
        segs.append(f"{col} {a:.3f}% {b:.3f}%")
        pos = b
    if not segs:
        return None
    return f"conic-gradient(from -90deg, {', '.join(segs)})"


def _viz_top_tags_bars(top_tags: List[tuple[str, int]]) -> List[dict]:
    """Relative bar width (0–100) for tag frequency mini-chart."""
    if not top_tags:
        return []
    mx = max(c for _, c in top_tags)
    out: List[dict] = []
    for lab, c in top_tags[:6]:
        out.append(
            {
                "label": lab,
                "count": int(c),
                "rel_pct": round(100 * int(c) / mx) if mx else 0,
            }
        )
    return out


def _viz_risk_chart_max(selected: dict | None) -> int:
    if not selected:
        return 1
    if selected.get("sat_children"):
        xs = [int(x.get("count") or 0) for x in selected["sat_children"]]
        return max(xs) if xs else 1
    if selected.get("units"):
        xs = [int(x.get("count") or 0) for x in selected["units"]]
        return max(xs) if xs else 1
    return 1


@app.route("/placement")
def placement_landing():
    session["active_track_label"] = "Course placement"
    return render_template(
        "placement_landing.html",
        placement_parts=PLACEMENT_LANDING_PARTS,
    )


@app.route("/placement/start")
def placement_start():
    session["active_track_label"] = "Course placement"
    # New intake = new diagnostic: do not resume an old in-browser attempt (fixes stale answers).
    _clear_placement_full_session_attempt()
    session.modified = True
    return render_template("placement_start.html")


@app.route("/placement/begin", methods=["POST"])
def placement_begin():
    session["active_track_label"] = "Course placement"
    _clear_placement_full_session_attempt()
    name = request.form.get("student_name", "").strip()
    grade = request.form.get("student_grade", "").strip()
    course = request.form.get("student_math_course", "").strip()
    if len(name) < 1:
        flash("Please enter the student name.")
        return redirect(url_for("placement_start"))
    if len(name) > 160:
        flash("Name is too long (160 characters max).")
        return redirect(url_for("placement_start"))
    grade = grade[:120]
    course = course[:400]
    session["placement_student_name"] = name[:160]
    session["placement_student_grade"] = grade
    session["placement_student_math_course"] = course
    session.modified = True
    return redirect(
        url_for("practice_question", domain="placement", topic="placement_full", qnum=0)
    )


@app.route("/practice")
def practice():
    """SAT Math home: four modules (specialized, challenge, exams, analytics)."""
    session["active_track_label"] = "SAT Math"
    cm = load_course_materials()
    return render_template(
        "practice_hub.html",
        cm_total=int(cm.get("total") or 0),
        cm_ready=int(cm.get("available") or 0),
    )


@app.route("/practice/specialized")
def practice_specialized():
    session["active_track_label"] = "SAT Math"
    db = get_db()
    uid = session.get("user_id")
    ctx = _practice_workspace_counts()
    _practice_workspace_merge_progress(ctx, db, uid)
    ctx["unit_pdf_cards"] = _unit_pdf_cards()
    ctx["pw_unit_cards"] = _practice_unit_atelier_cards(ctx, db, uid)
    return render_template("practice_specialized.html", **ctx)


@app.route("/practice/specialized/pdf/<domain>")
def practice_unit_pdf(domain: str):
    session["active_track_label"] = "SAT Math"
    meta = UNIT_PDF_MATERIALS.get(domain)
    if not meta:
        abort(404)
    path = _resolve_first_existing_path(list(meta.get("candidates") or []))
    if not path:
        abort(404)
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=meta.get("download_name") or os.path.basename(path),
    )


@app.route("/practice/specialized/practice-test/<domain>.pdf")
def practice_unit_practice_test_pdf(domain: str):
    session["active_track_label"] = "SAT Math"
    meta = UNIT_PDF_MATERIALS.get(domain)
    if not meta:
        abort(404)
    path = _resolve_first_existing_path(list(meta.get("practice_test_candidates") or []))
    if not path:
        abort(404)
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=meta.get("practice_test_download_name") or os.path.basename(path),
    )


def _practice_test_pdf_for_domain(domain: str) -> dict[str, Any] | None:
    meta = UNIT_PDF_MATERIALS.get(domain) or {}
    found = _resolve_first_existing_path(list(meta.get("practice_test_candidates") or []))
    if not found:
        return None
    return {
        "href": url_for("practice_unit_practice_test_pdf", domain=domain),
        "label": "Practice test PDF",
        "description": "Printable practice test for offline review",
    }


@app.route("/practice/materials")
def practice_course_materials():
    session["active_track_label"] = "SAT Math"
    ctx = _course_materials_hub_context()
    return render_template("course_materials.html", **ctx)


@app.route("/practice/materials/<slug>")
def practice_course_material_view(slug: str):
    session["active_track_label"] = "SAT Math"
    material = _course_material_by_slug(slug)
    if not material:
        abort(404)
    pdf_href = (
        url_for("practice_course_material_pdf", slug=slug)
        if material.get("pdf_available")
        else None
    )
    return render_template(
        "course_material_view.html",
        material=material,
        pdf_href=pdf_href,
    )


@app.route("/practice/materials/<slug>.pdf")
def practice_course_material_pdf(slug: str):
    session["active_track_label"] = "SAT Math"
    path = _course_material_pdf_path(slug)
    if not path:
        abort(404)
    manifest = _course_material_manifest_row(slug) or {}
    download_name = f"NovelPrep-SAT-{manifest.get('section', slug).replace('.', '-')}-{slug}.pdf"
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_name,
    )


@app.route("/practice/challenge")
def practice_challenge():
    session["active_track_label"] = "SAT Math"
    db = get_db()
    uid = session.get("user_id")

    def _int_to_roman(value: int) -> str:
        pairs = (
            (1000, "M"),
            (900, "CM"),
            (500, "D"),
            (400, "CD"),
            (100, "C"),
            (90, "XC"),
            (50, "L"),
            (40, "XL"),
            (10, "X"),
            (9, "IX"),
            (5, "V"),
            (4, "IV"),
            (1, "I"),
        )
        out = ""
        n = max(1, int(value))
        for amount, numeral in pairs:
            while n >= amount:
                out += numeral
                n -= amount
        return out

    def _hard_set_number(topic: str, fallback_idx: int) -> int:
        match = re.match(r"^hard_(\d+)$", topic)
        return int(match.group(1)) if match else fallback_idx

    hard_sets = []
    for idx, (topic, tex_path) in enumerate(BANKS.get("hard_problem", {}).items(), start=1):
        set_number = _hard_set_number(topic, idx)
        set_roman = _int_to_roman(set_number)
        questions = get_questions_for_topic("hard_problem", topic, tex_path)
        answered_row = db.execute(
            """
            SELECT COUNT(DISTINCT pr.question_index) AS c
            FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pa.user_id IS ? AND pa.domain = 'hard_problem' AND pa.topic = ?
              AND pr.question_index IS NOT NULL
            """,
            (uid, topic),
        ).fetchone()
        answered = int(answered_row["c"] or 0) if answered_row else 0
        total = len(questions)
        materials = []
        for kind, meta in HARD_PRACTICE_MATERIALS.get(topic, {}).items():
            rel_path = meta.get("path", "")
            full_path = os.path.join(APP_DIR, rel_path)
            if not rel_path or not os.path.isfile(full_path):
                continue
            materials.append(
                {
                    "kind": kind,
                    "label": meta.get("label", kind),
                    "description": meta.get("description", ""),
                    "href": url_for("practice_hard_material", topic=topic, kind=kind),
                    "is_slides": "slide" in kind,
                }
            )
        if total and answered >= total:
            progress_state = "done"
        elif answered:
            progress_state = "progress"
        else:
            progress_state = "new"
        practice_href = url_for(
            "practice_question", domain="hard_problem", topic=topic, qnum=0
        )
        report_href = (
            _practice_report_href(db, uid, "hard_problem", topic, total)
            if progress_state == "done"
            else None
        )
        hard_sets.append(
            {
                "index": idx,
                "set_number": set_number,
                "roman": set_roman,
                "topic": topic,
                "title": f"Hard Practice {set_roman}",
                "subtitle": TOPIC_TITLES.get(topic, f"SAT Hard Question Set {idx}"),
                "total": total,
                "answered": answered,
                "progress_pct": min(100, round(100 * answered / total)) if total else 0,
                "href": report_href or practice_href,
                "practice_href": practice_href,
                "report_href": report_href,
                "restart_href": url_for("practice_new_session", domain="hard_problem", topic=topic),
                "status": "Continue" if answered else "Start",
                "progress_state": progress_state,
                "range_bucket": (set_number - 1) // 10 + 1,
                "is_live": total > 0,
                "materials": materials,
            }
        )
    total_questions = sum(s["total"] for s in hard_sets)
    total_answered = sum(s["answered"] for s in hard_sets)
    hard_stats = {
        "done": sum(1 for s in hard_sets if s["progress_state"] == "done"),
        "progress": sum(1 for s in hard_sets if s["progress_state"] == "progress"),
        "new": sum(1 for s in hard_sets if s["progress_state"] == "new"),
    }
    last_topic_row = db.execute(
        """
        SELECT pa.topic
        FROM practice_responses pr
        JOIN practice_attempts pa ON pa.id = pr.attempt_id
        WHERE pa.user_id IS ? AND pa.domain = 'hard_problem'
        ORDER BY pr.submitted_at DESC
        LIMIT 1
        """,
        (uid,),
    ).fetchone()
    continue_set = None
    if last_topic_row:
        last_topic = str(last_topic_row["topic"] or "")
        continue_set = next((s for s in hard_sets if s["topic"] == last_topic), None)
    if continue_set is None:
        continue_set = next((s for s in hard_sets if s["progress_state"] == "progress"), None)
    if continue_set is None:
        continue_set = next((s for s in hard_sets if s["progress_state"] == "new"), None)
    next_set = next((s for s in hard_sets if s["progress_state"] != "done"), None)
    default_index = continue_set["index"] if continue_set else (hard_sets[0]["index"] if hard_sets else 1)
    return render_template(
        "practice_challenge.html",
        hard_sets=hard_sets,
        hard_stats=hard_stats,
        continue_set=continue_set,
        next_set=next_set,
        default_index=default_index,
        total_questions=total_questions,
        total_answered=total_answered,
        overall_pct=min(100, round(100 * total_answered / total_questions)) if total_questions else 0,
    )


@app.route("/practice/challenge/materials/<topic>/<kind>")
def practice_hard_material(topic: str, kind: str):
    session["active_track_label"] = "SAT Math"
    meta = HARD_PRACTICE_MATERIALS.get(topic, {}).get(kind)
    if not meta:
        abort(404)
    rel_path = meta.get("path", "")
    full_path = os.path.join(APP_DIR, rel_path)
    if not rel_path or not os.path.isfile(full_path):
        abort(404)
    return send_file(
        full_path,
        mimetype=meta.get("mimetype") or "application/octet-stream",
        as_attachment=kind == "paper_pdf",
        download_name=meta.get("download_name") or os.path.basename(full_path),
    )


@app.route("/practice/exams")
def practice_exams():
    session["active_track_label"] = "SAT Math"
    return render_template(
        "practice_module_placeholder.html",
        title="Real exam mode",
        lead="Timed sections and full mock papers that mirror official pacing and layout.",
        pill="Coming soon",
    )


@app.route("/practice/analytics")
def practice_analytics():
    session["active_track_label"] = "SAT Math"
    db = get_db()
    uid = session.get("user_id")
    rows = _analytics_wrong_rows(db, uid)
    tag_totals: Dict[str, int] = defaultdict(int)
    for row in rows:
        for lab in row["tag_labels"]:
            tag_totals[lab] += 1
    top_tags = sorted(tag_totals.items(), key=lambda x: -x[1])[:8]
    classifier = _build_mistake_classifier(rows)
    analytics_partitions = _analytics_partitions(rows)
    for part in analytics_partitions:
        part["pct"] = round(100 * int(part.get("count") or 0) / len(rows)) if rows else 0
        part_total = int(part.get("count") or 0)
        for unit in part.get("units") or []:
            unit["pct"] = round(100 * int(unit.get("count") or 0) / part_total) if part_total else 0
        for child in part.get("sat_children") or []:
            c_total = int(child.get("count") or 0)
            for unit in child.get("units") or []:
                unit["pct"] = round(100 * int(unit.get("count") or 0) / c_total) if c_total else 0
        if part.get("id") == "sat" and part.get("sat_children"):
            st = int(part.get("count") or 0)
            for j, ch in enumerate(part["sat_children"]):
                ch["viz_pct"] = round(100 * int(ch.get("count") or 0) / st) if st else 0
                ch["viz_color"] = _viz_analytics_partition_color(str(ch.get("id") or ""), j)
    for i, part in enumerate(analytics_partitions):
        part["viz_color"] = _viz_analytics_partition_color(str(part.get("id") or ""), i)
    viz_hero_conic = _viz_analytics_hero_conic_gradient(analytics_partitions)
    top_tags_viz = _viz_top_tags_bars(top_tags)
    selected_part_id = (request.args.get("part") or "").strip().lower()
    selected_partition = _analytics_partition_by_id(analytics_partitions, selected_part_id)
    if (
        selected_partition
        and selected_partition.get("units")
        and not selected_partition.get("sat_children")
    ):
        for j, u in enumerate(selected_partition["units"]):
            u["viz_color"] = _viz_analytics_partition_color(
                f"{selected_partition.get('id') or 'unit'}-s{j}", j
            )
    active_classifier = (
        selected_partition["classifier"] if selected_partition else classifier
    )
    risk_viz_max = _viz_risk_chart_max(selected_partition)
    loop_rows = (
        _analytics_partition_flat_rows(selected_partition)
        if selected_partition
        else rows
    )
    learning_loop_snapshot = _analytics_learning_loop_snapshot(
        loop_rows, active_classifier
    )
    return render_template(
        "practice_analytics.html",
        wrong_rows=rows,
        wrong_total=len(rows),
        top_mistake_tags=top_tags,
        top_tags_viz=top_tags_viz,
        mistake_tag_options=MISTAKE_TAG_OPTIONS,
        classifier=active_classifier,
        analytics_partitions=analytics_partitions,
        selected_partition=selected_partition,
        viz_hero_conic=viz_hero_conic,
        risk_viz_max=risk_viz_max,
        learning_loop_snapshot=learning_loop_snapshot,
    )


@app.route("/practice/analytics/update/<int:pr_id>", methods=["POST"])
def practice_analytics_update(pr_id: int):
    db = get_db()
    uid = session.get("user_id")
    row = db.execute(
        """
        SELECT pr.id FROM practice_responses pr
        JOIN practice_attempts pa ON pa.id = pr.attempt_id
        WHERE pr.id = ? AND pr.is_correct = 0
          AND (pa.user_id IS ? OR (pa.user_id IS NULL AND ? IS NULL))
        """,
        (pr_id, uid, uid),
    ).fetchone()
    if row is None:
        flash("Could not update that record.")
        part_q = (request.form.get("part") or request.args.get("part") or "").strip().lower()
        anchor = request.form.get("anchor") or request.args.get("anchor")
        return _redirect_practice_analytics(part_q, anchor)
    tags_json = _mistake_tags_json_from_form(request.form)
    note = (request.form.get("mistake_note") or "").strip()[:2000]
    db.execute(
        """
        UPDATE practice_responses
        SET mistake_tags = ?, mistake_note = ?
        WHERE id = ?
        """,
        (tags_json, note, pr_id),
    )
    slot = db.execute(
        """
        SELECT pa.domain, pa.topic, pr.question_index
        FROM practice_responses pr
        JOIN practice_attempts pa ON pa.id = pr.attempt_id
        WHERE pr.id = ?
        """,
        (pr_id,),
    ).fetchone()
    if slot is not None and slot["question_index"] is not None:
        _mistake_progress_mark_reviewed(
            db,
            _learner_key(),
            str(slot["domain"]),
            str(slot["topic"]),
            int(slot["question_index"]),
        )
    db.commit()
    flash("Mistake log updated.")
    part = (request.form.get("part") or request.args.get("part") or "").strip().lower()
    anchor = request.form.get("anchor") or request.args.get("anchor")
    return _redirect_practice_analytics(part, anchor)


@app.route("/practice/analytics/mastery", methods=["POST"])
def practice_analytics_mastery():
    """Student marks this question slot as mastered on the learning ladder."""
    domain = (request.form.get("domain") or "").strip()
    topic = (request.form.get("topic") or "").strip()
    part = (request.form.get("part") or "").strip().lower()
    try:
        q_index = int(request.form.get("question_index", ""))
    except ValueError:
        flash("Could not update mastery for that question.")
        return redirect(url_for("practice_analytics"))
    if domain not in BANKS or topic not in BANKS.get(domain, {}):
        flash("Unknown topic.")
        return redirect(url_for("practice_analytics"))
    db = get_db()
    _mistake_progress_force_mastered(db, _learner_key(), domain, topic, q_index)
    db.commit()
    flash("Marked as mastered. Use Cancel on the row or Undo in the toast if that was a mistake.")
    return _redirect_practice_analytics(part, None)


@app.route("/practice/analytics/api/mastery", methods=["POST"])
def practice_analytics_api_mastery():
    """JSON: mark a (domain, topic, bank index) slot mastered without a full-page redirect."""
    data = request.get_json(silent=True) or {}
    domain = (data.get("domain") or "").strip()
    topic = (data.get("topic") or "").strip()
    try:
        q_index = int(data.get("question_index", ""))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid question index"}), 400
    if domain not in BANKS or topic not in BANKS.get(domain, {}):
        return jsonify({"ok": False, "error": "unknown topic"}), 400
    db = get_db()
    _mistake_progress_force_mastered(db, _learner_key(), domain, topic, q_index)
    db.commit()
    return jsonify(
        {
            "ok": True,
            "mastery_label": "Mastered",
            "mastery_effective": "mastered",
        }
    )


@app.route("/practice/analytics/api/mastery/cancel", methods=["POST"])
def practice_analytics_api_mastery_cancel():
    """JSON: clear a mistaken 'mastered' mark for this bank slot."""
    data = request.get_json(silent=True) or {}
    domain = (data.get("domain") or "").strip()
    topic = (data.get("topic") or "").strip()
    try:
        q_index = int(data.get("question_index", ""))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid question index"}), 400
    if domain not in BANKS or topic not in BANKS.get(domain, {}):
        return jsonify({"ok": False, "error": "unknown topic"}), 400
    db = get_db()
    ok = _mistake_progress_revert_mastered(db, _learner_key(), domain, topic, q_index)
    if not ok:
        return jsonify({"ok": False, "error": "not mastered or no record"}), 400
    db.commit()
    return jsonify(
        {
            "ok": True,
            "mastery_label": "Reviewed",
            "mastery_effective": "reviewed",
            "mastery_db_status": "reviewed",
        }
    )


@app.route("/practice/<domain>/<topic>/reflect/<int:q_index>", methods=["GET", "POST"])
def practice_mistake_reflect(domain: str, topic: str, q_index: int):
    """After a wrong answer: capture mistake tags + note before continuing."""
    domain_data = BANKS.get(domain)
    if not domain_data or topic not in domain_data:
        return "Unknown topic", 404
    tex_file = domain_data[topic]
    questions = get_questions_for_topic(domain, topic, tex_file)
    if not questions or q_index < 0 or q_index >= len(questions):
        return "Invalid question", 404

    db = get_db()
    if request.method == "POST":
        try:
            attempt_id = int(request.form.get("attempt_id") or 0)
        except ValueError:
            attempt_id = 0
        continue_to = (request.form.get("continue_to") or "").strip()
        if continue_to not in ("next", "summary"):
            continue_to = "next"
        tags_json = _mistake_tags_json_from_form(request.form)
        note = (request.form.get("mistake_note") or "").strip()[:2000]

        pr_row = db.execute(
            """
            SELECT pr.id FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pr.attempt_id = ? AND pr.question_index = ?
              AND pa.domain = ? AND pa.topic = ?
              AND pr.is_correct = 0
            """,
            (attempt_id, q_index, domain, topic),
        ).fetchone()
        if pr_row is None:
            flash("Could not save reflection for this attempt.")
            return redirect(
                url_for("practice_question", domain=domain, topic=topic, qnum=q_index)
            )
        db.execute(
            """
            UPDATE practice_responses
            SET mistake_tags = ?, mistake_note = ?
            WHERE id = ?
            """,
            (tags_json, note, int(pr_row["id"])),
        )
        _mistake_progress_mark_reviewed(db, _learner_key(), domain, topic, q_index)
        db.commit()

        sk = _practice_session_key(domain, topic)
        session[sk] = attempt_id
        session.modified = True

        if continue_to == "summary":
            return redirect(url_for("practice_session_summary", attempt_id=attempt_id))
        return redirect(
            url_for("practice_question", domain=domain, topic=topic, qnum=q_index + 1)
        )

    try:
        attempt_id = int(request.args.get("attempt_id") or 0)
    except ValueError:
        attempt_id = 0
    continue_to = (request.args.get("continue_to") or "").strip()
    if continue_to not in ("next", "summary"):
        continue_to = "next"

    pr_row = db.execute(
        """
        SELECT pr.id, pr.selected_answer, pr.correct_answer, pr.mistake_tags, pr.mistake_note
        FROM practice_responses pr
        JOIN practice_attempts pa ON pa.id = pr.attempt_id
        WHERE pr.attempt_id = ? AND pr.question_index = ?
          AND pa.domain = ? AND pa.topic = ?
          AND pr.is_correct = 0
        """,
        (attempt_id, q_index, domain, topic),
    ).fetchone()
    if pr_row is None:
        return redirect(
            url_for("practice_question", domain=domain, topic=topic, qnum=q_index)
        )

    q = questions[q_index]
    prev_tags: List[str] = []
    if pr_row["mistake_tags"]:
        try:
            raw = json.loads(pr_row["mistake_tags"])
            if isinstance(raw, list):
                prev_tags = [x for x in raw if isinstance(x, str)]
        except (json.JSONDecodeError, TypeError):
            prev_tags = []

    return render_template(
        "practice_mistake_reflect.html",
        domain=domain,
        topic=topic,
        topic_title=TOPIC_TITLES.get(topic, topic),
        q_index=q_index,
        attempt_id=attempt_id,
        continue_to=continue_to,
        total=len(questions),
        q=q,
        yours=(pr_row["selected_answer"] or "").strip(),
        key_disp=(pr_row["correct_answer"] or "").strip(),
        mistake_tag_options=MISTAKE_TAG_OPTIONS,
        prev_tags=prev_tags,
        prev_note=(pr_row["mistake_note"] or "").strip(),
    )


def _topic_short_label(topic_key: str) -> str:
    if topic_key.startswith("unit_"):
        return "Full"
    parts = topic_key.split("_")
    if len(parts) == 2 and parts[0].isdigit() and parts[1] == "pt":
        return "PT"
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{parts[0]}.{parts[1]}"
    return topic_key


def _topic_bank_sort_key(topic_key: str) -> tuple[int, int, str]:
    """Order banks: full first, then 1.1…1.5, then practice test (PT)."""
    if topic_key.startswith("unit_"):
        return (0, 0, topic_key)
    parts = topic_key.split("_")
    major = int(parts[0]) if parts and parts[0].isdigit() else 99
    if len(parts) > 1 and parts[1].isdigit():
        return (1, int(parts[1]), topic_key)
    if len(parts) > 1 and parts[1] == "pt":
        return (1, 99, topic_key)
    return (2, 0, topic_key)


def _unit_chapter_slice_meta(domain: str) -> dict[str, Any]:
    """Chapter slice count + range label (e.g. 1.1 – 1.5) for unit cards."""
    topics = BANKS.get(domain) or {}
    slice_keys = sorted(
        (
            k
            for k in topics
            if not str(k).startswith("unit_") and not str(k).endswith("_pt")
        ),
        key=_topic_bank_sort_key,
    )
    count = len(slice_keys)
    if not slice_keys:
        return {
            "slice_count": 0,
            "slice_range": "",
            "studio_btn_label": "Topic studio",
            "studio_btn_sub": "Browse banks",
        }
    labels = [_topic_short_label(k) for k in slice_keys]
    slice_range = f"{labels[0]} – {labels[-1]}" if len(labels) > 1 else labels[0]
    chapter_word = "chapters" if count != 1 else "chapter"
    return {
        "slice_count": count,
        "slice_range": slice_range,
        "studio_btn_label": "Chapter slices",
        "studio_btn_sub": f"{slice_range} · {count} {chapter_word}",
    }


def _build_unit_topic_studio(
    db: sqlite3.Connection, user_id: Any, domain: str
) -> dict[str, Any] | None:
    """Topic picker + detail panel data for Units 1–4 (Hard Drill–style studio)."""
    domain_data = BANKS.get(domain)
    if not domain_data or domain == "placement":
        return None

    topic_sets: List[dict] = []
    total_questions = 0
    total_answered_sum = 0
    idx = 0
    practice_test_pdf = _practice_test_pdf_for_domain(domain)

    for topic_key, file_path in sorted(
        domain_data.items(), key=lambda item: _topic_bank_sort_key(item[0])
    ):
        questions = get_questions_for_topic(domain, topic_key, file_path)
        if not questions:
            continue
        idx += 1
        total = len(questions)
        answered = _practice_distinct_answered(db, user_id, domain, topic_key)
        wrong_indices = _distinct_wrong_indices_for_topic(db, user_id, domain, topic_key)
        wrong_count = len(wrong_indices)

        if total and answered >= total:
            progress_state = "done"
        elif answered:
            progress_state = "progress"
        else:
            progress_state = "new"

        practice_href = url_for(
            "practice_question", domain=domain, topic=topic_key, qnum=0
        )
        report_href = _practice_report_href(db, user_id, domain, topic_key, total)
        href = report_href if progress_state == "done" and report_href else practice_href
        miss_quiz_href = (
            url_for("practice_miss_quiz_start", domain=domain, topic=topic_key)
            if wrong_count
            else None
        )

        topic_sets.append(
            {
                "index": idx,
                "topic": topic_key,
                "code": _topic_short_label(topic_key),
                "title": TOPIC_TITLES.get(topic_key, topic_key),
                "total": total,
                "answered": answered,
                "wrong_count": wrong_count,
                "progress_pct": min(100, round(100 * answered / total)) if total else 0,
                "progress_state": progress_state,
                "href": href,
                "practice_href": practice_href,
                "report_href": report_href,
                "restart_href": url_for(
                    "practice_new_session", domain=domain, topic=topic_key
                ),
                "miss_quiz_href": miss_quiz_href,
                "is_full_bank": topic_key.startswith("unit_"),
                "is_practice_test": topic_key.endswith("_pt"),
                "pdf_href": practice_test_pdf.get("href") if topic_key.endswith("_pt") and practice_test_pdf else None,
            }
        )
        total_questions += total
        total_answered_sum += answered

    if not topic_sets:
        return None

    stats = {
        "done": sum(1 for s in topic_sets if s["progress_state"] == "done"),
        "progress": sum(1 for s in topic_sets if s["progress_state"] == "progress"),
        "new": sum(1 for s in topic_sets if s["progress_state"] == "new"),
    }

    part_id = MISS_PART_BY_DOMAIN.get(domain)
    unit_miss_count = (
        len(_wrong_miss_items_for_module(db, user_id, part_id)) if part_id else 0
    )
    unit_miss_href = (
        url_for("practice_miss_quiz_sat_module", part_id=part_id)
        if unit_miss_count and part_id
        else None
    )

    full_bank = next((s for s in topic_sets if s["is_full_bank"]), topic_sets[0])
    continue_set = next(
        (s for s in topic_sets if s["progress_state"] == "progress"), None
    )
    if continue_set is None:
        continue_set = next((s for s in topic_sets if s["progress_state"] == "new"), None)
    if continue_set is None:
        continue_set = full_bank

    next_set = next((s for s in topic_sets if s["progress_state"] != "done"), None)

    unit_pdf = next(
        (c for c in _unit_pdf_cards() if c.get("domain") == domain and c.get("available")),
        None,
    )

    bank_groups = {
        "full": [s for s in topic_sets if s["is_full_bank"]],
        "chapters": [
            s for s in topic_sets if not s["is_full_bank"] and not s["is_practice_test"]
        ],
        "practice_tests": [s for s in topic_sets if s["is_practice_test"]],
    }

    return {
        "topic_sets": topic_sets,
        "bank_groups": bank_groups,
        "total_questions": total_questions,
        "total_answered": total_answered_sum,
        "overall_pct": (
            min(100, round(100 * total_answered_sum / total_questions))
            if total_questions
            else 0
        ),
        "topic_stats": stats,
        "continue_set": continue_set,
        "next_set": next_set,
        "default_index": continue_set["index"],
        "full_bank": full_bank,
        "unit_miss_count": unit_miss_count,
        "unit_miss_href": unit_miss_href,
        "analytics_href": url_for("practice_analytics", part="sat"),
        "unit_pdf": unit_pdf,
    }


# -----------------------------------------------------
# Topic List Page
# -----------------------------------------------------
@app.route("/practice/<domain>")
def practice_topics(domain):

    domain_data = BANKS.get(domain)
    if not domain_data:
        return "Unknown domain", 404

    db = get_db()
    uid = session.get("user_id")
    studio = _build_unit_topic_studio(db, uid, domain)

    if studio is not None:
        unit_labels = {
            "algebra": {"num": "1", "name": "Algebra"},
            "advanced_math": {"num": "2", "name": "Advanced Math"},
            "problem_solving": {"num": "3", "name": "Problem Solving & Data"},
            "geometry": {"num": "4", "name": "Geometry"},
        }
        unit_info = unit_labels.get(domain, {"num": "", "name": domain.replace("_", " ").title()})
        return render_template(
            "topics.html",
            domain=domain,
            domain_title=PRACTICE_DOMAIN_TITLES.get(
                domain, domain.replace("_", " ").title()
            ),
            studio_mode=True,
            unit_num=unit_info["num"],
            unit_name=unit_info["name"],
            **studio,
        )

    topic_list = []
    for topic_key, file_path in domain_data.items():
        questions = get_questions_for_topic(domain, topic_key, file_path)
        if not questions:
            continue
        topic_list.append({
            "key": topic_key,
            "title": TOPIC_TITLES.get(topic_key, topic_key),
            "count": len(questions),
        })

    return render_template(
        "topics.html",
        domain=domain,
        domain_title=PRACTICE_DOMAIN_TITLES.get(
            domain, domain.replace("_", " ").title()
        ),
        topics=topic_list,
        studio_mode=False,
    )


def _insert_practice_attempt(
    db: sqlite3.Connection, user_id: Any, domain: str, topic: str, q_index: int
) -> int:
    cols = ["user_id", "domain", "topic", "qnum"]
    vals: list[Any] = [user_id, domain, topic, q_index]
    if domain == "placement":
        name, grade, course = _placement_profile_from_session()
        cols.extend(
            [
                "placement_student_name",
                "placement_student_grade",
                "placement_student_math_course",
            ]
        )
        vals.extend([name or None, grade or None, course or None])
    placeholders = ", ".join(["?"] * len(vals))
    cur = db.execute(
        f"INSERT INTO practice_attempts ({', '.join(cols)}) VALUES ({placeholders})",
        tuple(vals),
    )
    db.commit()
    return int(cur.lastrowid)


# -----------------------------------------------------
# Miss quiz (wrong-only redo with instant feedback)
# -----------------------------------------------------


def _redirect_miss_quiz_items(items: List[dict], label: str, summary_part_id: str | None):
    items = [dict(x) for x in items]
    if not items:
        flash(
            "No misses found for this set yet—keep practicing, then check Mistake analytics."
        )
        return redirect(url_for("practice_analytics"))
    shuffled = list(items)
    if len(shuffled) > 1:
        random.shuffle(shuffled)
    session[MQ_PACK_KEY] = {
        "v": MQ_PACK_VERSION,
        "items": shuffled,
        "attempt_map": {},
        "label": label[:220],
        "summary_part_id": summary_part_id,
    }
    session.pop(MQ_FEEDBACK_KEY, None)
    session.modified = True
    return redirect(url_for("practice_miss_quiz_run_question", step=0))


def _redirect_miss_quiz_start(domain: str, topic: str, indices: List[int], label: str):
    part_id = MISS_PART_BY_DOMAIN.get(domain)
    items = [{"domain": domain, "topic": topic, "q_index": int(x)} for x in indices]
    return _redirect_miss_quiz_items(items, label, part_id)


@app.route("/practice/miss-quiz/module/<part_id>/start")
def practice_miss_quiz_sat_module(part_id: str):
    if _miss_module_spec(part_id) is None:
        abort(404)
    db = get_db()
    uid = session.get("user_id")
    items = _wrong_miss_items_for_module(db, uid, part_id)
    spec = _miss_module_spec(part_id)
    label = f"Unit miss quiz · {spec['label']}" if spec else "Unit miss quiz"
    return _redirect_miss_quiz_items(items, label, part_id)


@app.route("/practice/miss-quiz/<domain>/<topic>/start")
def practice_miss_quiz_start(domain: str, topic: str):
    if domain not in BANKS or topic not in BANKS[domain]:
        return "Unknown topic", 404
    if domain == "placement":
        flash("Miss quiz is available for SAT practice banks.")
        return redirect(url_for("placement_landing"))
    db = get_db()
    uid = session.get("user_id")
    indices = _distinct_wrong_indices_for_topic(db, uid, domain, topic)
    title = TOPIC_TITLES.get(topic, topic)
    label = f"Miss quiz · {title}"
    return _redirect_miss_quiz_start(domain, topic, indices, label)


@app.route("/practice/miss-quiz/from-session/<int:attempt_id>/start")
def practice_miss_quiz_from_session(attempt_id: int):
    db = get_db()
    uid = session.get("user_id")
    att = db.execute(
        "SELECT id, domain, topic FROM practice_attempts WHERE id = ?",
        (attempt_id,),
    ).fetchone()
    if att is None or not _attempt_user_matches(db, attempt_id, uid):
        flash("That session was not found or is not yours.")
        return redirect(url_for("practice_analytics"))
    domain = str(att["domain"])
    topic = str(att["topic"])
    if domain not in BANKS or topic not in BANKS.get(domain, {}):
        return redirect(url_for("practice"))
    if domain == "placement":
        flash("Miss quiz is for SAT practice sets.")
        return redirect(url_for("practice_session_summary", attempt_id=attempt_id))
    indices = _wrong_indices_from_attempt(db, attempt_id)
    label = f"This session's misses · {TOPIC_TITLES.get(topic, topic)}"
    return _redirect_miss_quiz_start(domain, topic, indices, label)


@app.route("/practice/miss-quiz/<domain>/<topic>/one/<int:q_index>")
def practice_miss_quiz_one(domain: str, topic: str, q_index: int):
    if domain not in BANKS or topic not in BANKS[domain]:
        return "Unknown topic", 404
    tex = BANKS[domain][topic]
    questions = get_questions_for_topic(domain, topic, tex)
    if not questions or q_index < 0 or q_index >= len(questions):
        return "Invalid question", 404
    title = TOPIC_TITLES.get(topic, topic)
    label = f"Single redo · Q{q_index + 1} · {title}"
    return _redirect_miss_quiz_start(domain, topic, [q_index], label)


def _miss_quiz_render_question_step(step: int):
    pack = _mq_normalize_pack_session(session.get(MQ_PACK_KEY) or {})
    items = _mq_get_pack_items(pack)
    if not items:
        flash("Start a miss quiz from your results page or Mistake analytics.")
        return redirect(url_for("practice_analytics"))
    if step < 0 or step >= len(items):
        return redirect(url_for("practice_miss_quiz_run_done"))
    it = items[step]
    domain = str(it["domain"])
    topic = str(it["topic"])
    bank_q = int(it["q_index"])
    db = get_db()
    uid = session.get("user_id")
    _miss_quiz_ensure_attempt_for_topic(db, uid, pack, domain, topic, bank_q)
    pack = session.get(MQ_PACK_KEY) or {}
    items = _mq_get_pack_items(pack)
    it = items[step]
    domain = str(it["domain"])
    topic = str(it["topic"])
    bank_q = int(it["q_index"])
    attempt_map = dict(pack.get("attempt_map") or {})
    k = _mq_attempt_map_key(domain, topic)
    attempt_id = int(attempt_map.get(k) or 0)
    if not attempt_id or not _attempt_user_matches(db, attempt_id, uid):
        flash("Miss quiz session no longer matches this browser.")
        session.pop(MQ_PACK_KEY, None)
        return redirect(url_for("practice_analytics"))

    domain_data = BANKS.get(domain) or {}
    tex_file = domain_data.get(topic)
    if not tex_file:
        return "Unknown topic", 404
    questions = get_questions_for_topic(domain, topic, tex_file)
    if not questions:
        return "No questions", 404
    if bank_q < 0 or bank_q >= len(questions):
        flash("Question list changed—restart the miss quiz.")
        session.pop(MQ_PACK_KEY, None)
        return redirect(url_for("practice_analytics"))

    q = questions[bank_q]
    answered_rows = db.execute(
        """
        SELECT DISTINCT question_index FROM practice_responses
        WHERE attempt_id = ? AND question_index IS NOT NULL
        """,
        (attempt_id,),
    ).fetchall()
    answered_qset = frozenset(
        int(r["question_index"]) for r in answered_rows if r["question_index"] is not None
    )
    answered_in_pack = _miss_quiz_answered_in_pack_v2(db, attempt_map, items)
    remaining = max(0, len(items) - answered_in_pack)
    choice_letters = [chr(ord("A") + i) for i in range(len(q.get("choices") or []))]
    calc_ok = bool(q.get("calculator_allowed", True))
    is_last_step = step >= len(items) - 1
    miss_quiz_v2 = bool(pack.get("v") == MQ_PACK_VERSION)
    return render_template(
        "practice_question.html",
        q=q,
        domain=domain,
        topic=topic,
        qnum=bank_q,
        total=len(questions),
        attempt_id=attempt_id,
        answered_qset=answered_qset,
        answered_count=answered_in_pack,
        answered_pct=min(100, int(round(100 * answered_in_pack / len(items)))) if items else 0,
        remaining_count=remaining,
        is_last=is_last_step,
        calculator_allowed=calc_ok,
        placement_mode=False,
        choice_letters=choice_letters,
        practice_timer_seconds=0,
        practice_timer_summary_url=None,
        miss_quiz_mode=True,
        miss_quiz_step=step,
        miss_quiz_total=len(items),
        miss_quiz_bank_qnum=bank_q,
        miss_quiz_label=str(pack.get("label") or "Miss quiz"),
        miss_quiz_is_last_step=is_last_step,
        miss_quiz_v2=miss_quiz_v2,
    )


@app.route("/practice/miss-quiz/run/q/<int:step>")
def practice_miss_quiz_run_question(step: int):
    return _miss_quiz_render_question_step(step)


@app.route("/practice/miss-quiz/<domain>/<topic>/q/<int:step>")
def practice_miss_quiz_question(domain: str, topic: str, step: int):
    pack = _mq_normalize_pack_session(session.get(MQ_PACK_KEY) or {})
    if pack.get("v") == MQ_PACK_VERSION:
        return redirect(url_for("practice_miss_quiz_run_question", step=step))
    if (
        pack.get("domain") != domain
        or pack.get("topic") != topic
        or not pack.get("indices")
    ):
        flash("Start a miss quiz from your results page or Mistake analytics.")
        return redirect(url_for("practice_analytics"))
    return redirect(url_for("practice_miss_quiz_run_question", step=step))


@app.route("/practice/miss-quiz/submit", methods=["POST"])
def practice_miss_quiz_submit():
    pack = _mq_normalize_pack_session(session.get(MQ_PACK_KEY) or {})
    domain = (request.form.get("domain") or "").strip()
    topic = (request.form.get("topic") or "").strip()
    raw_answer = (request.form.get("selected_answer") or "").strip()
    attempt_raw = (request.form.get("attempt_id") or "").strip()
    step_raw = (request.form.get("mq_step") or "0").strip()
    bank_raw = (request.form.get("mq_bank_q") or "").strip()
    try:
        step = int(step_raw)
        bank_q = int(bank_raw)
    except ValueError:
        flash("Invalid miss quiz step.")
        return redirect(url_for("practice_analytics"))
    items = _mq_get_pack_items(pack)
    if (
        not items
        or step < 0
        or step >= len(items)
        or str(items[step]["domain"]) != domain
        or str(items[step]["topic"]) != topic
        or int(items[step]["q_index"]) != bank_q
    ):
        flash("Miss quiz data was out of date—start again.")
        session.pop(MQ_PACK_KEY, None)
        return redirect(url_for("practice_analytics"))

    if not raw_answer:
        flash("Please enter or select an answer before submitting.")
        return redirect(url_for("practice_miss_quiz_run_question", step=step))

    domain_data = BANKS.get(domain)
    if not domain_data or topic not in domain_data:
        return "Unknown topic", 404
    tex_file = domain_data[topic]
    questions = get_questions_for_topic(domain, topic, tex_file)
    if not questions or bank_q < 0 or bank_q >= len(questions):
        return "Invalid question", 404
    question = questions[bank_q]
    q_kind = question.get("question_kind", "mcq")
    if q_kind in ("mcq", "mcq5"):
        selected_answer = raw_answer.strip().upper()[:1]
        allowed = {"A", "B", "C", "D", "E"} if q_kind == "mcq5" else {"A", "B", "C", "D"}
        if selected_answer not in allowed:
            flash("Please select a valid choice.")
            return redirect(url_for("practice_miss_quiz_run_question", step=step))
    else:
        selected_answer = raw_answer

    is_correct, correct_answer = grade_for_db(question, selected_answer)
    db = get_db()
    uid = session.get("user_id")
    attempt_id = _miss_quiz_ensure_attempt_for_topic(db, uid, pack, domain, topic, bank_q)
    try:
        attempt_form = int(attempt_raw)
    except ValueError:
        flash("Missing attempt.")
        return redirect(url_for("practice_analytics"))
    if attempt_form != attempt_id or not _attempt_user_matches(db, attempt_id, uid):
        flash("Session mismatch.")
        return redirect(url_for("practice_analytics"))

    db.execute(
        "DELETE FROM practice_responses WHERE attempt_id = ? AND question_index = ?",
        (attempt_id, bank_q),
    )
    db.execute(
        """
        INSERT INTO practice_responses
        (attempt_id, question_index, selected_answer, correct_answer, is_correct)
        VALUES (?, ?, ?, ?, ?)
        """,
        (attempt_id, bank_q, selected_answer, correct_answer, is_correct),
    )
    lk = _learner_key()
    if is_correct == 1:
        _mistake_progress_on_correct(db, lk, domain, topic, bank_q)
    elif is_correct == 0:
        _mistake_progress_on_wrong(db, lk, domain, topic, bank_q)
    db.commit()

    session[MQ_FEEDBACK_KEY] = {
        "domain": domain,
        "topic": topic,
        "step": step,
        "is_correct": bool(is_correct),
        "yours": selected_answer,
        "key": correct_answer or "",
        "explanation": (question.get("explanation_en") or "").strip(),
        "bank_q": bank_q,
        "quiz_total": len(items),
        "has_next": step < len(items) - 1,
    }
    session.modified = True
    return redirect(url_for("practice_miss_quiz_run_feedback", step=step))


@app.route("/practice/miss-quiz/run/feedback/<int:step>")
def practice_miss_quiz_run_feedback(step: int):
    _mq_normalize_pack_session(session.get(MQ_PACK_KEY) or {})
    fb = session.get(MQ_FEEDBACK_KEY) or {}
    if int(fb.get("step", -1)) != step:
        return redirect(url_for("practice_miss_quiz_run_question", step=step))
    pack = session.get(MQ_PACK_KEY) or {}
    domain = str(fb.get("domain") or "")
    topic = str(fb.get("topic") or "")
    return render_template(
        "miss_quiz_feedback.html",
        domain=domain,
        topic=topic,
        topic_title=TOPIC_TITLES.get(topic, topic),
        step=step,
        feedback=fb,
        pack=pack,
        miss_quiz_v2=True,
    )


@app.route("/practice/miss-quiz/<domain>/<topic>/feedback/<int:step>")
def practice_miss_quiz_feedback(domain: str, topic: str, step: int):
    pack = _mq_normalize_pack_session(session.get(MQ_PACK_KEY) or {})
    if pack.get("v") == MQ_PACK_VERSION:
        return redirect(url_for("practice_miss_quiz_run_feedback", step=step))
    fb = session.get(MQ_FEEDBACK_KEY) or {}
    if (
        fb.get("domain") != domain
        or fb.get("topic") != topic
        or int(fb.get("step", -1)) != step
    ):
        return redirect(url_for("practice_miss_quiz_question", domain=domain, topic=topic, step=step))
    return render_template(
        "miss_quiz_feedback.html",
        domain=domain,
        topic=topic,
        topic_title=TOPIC_TITLES.get(topic, topic),
        step=step,
        feedback=fb,
        pack=pack,
        miss_quiz_v2=False,
    )


@app.route("/practice/miss-quiz/run/done")
def practice_miss_quiz_run_done():
    pack_raw = session.get(MQ_PACK_KEY)
    pack = _mq_normalize_pack_session(pack_raw or {})
    session.pop(MQ_PACK_KEY, None)
    session.pop(MQ_FEEDBACK_KEY, None)
    session.modified = True
    if not pack or not _mq_get_pack_items(pack):
        flash("Miss quiz already closed or restarted.")
        return redirect(url_for("practice_analytics"))
    items = _mq_get_pack_items(pack)
    attempt_map = dict(pack.get("attempt_map") or {})
    db = get_db()
    correct_n = 0
    for it in items:
        k = _mq_attempt_map_key(str(it["domain"]), str(it["topic"]))
        aid = attempt_map.get(k)
        if not aid:
            continue
        r = db.execute(
            """
            SELECT is_correct FROM practice_responses
            WHERE attempt_id = ? AND question_index = ?
            ORDER BY submitted_at DESC LIMIT 1
            """,
            (int(aid), int(it["q_index"])),
        ).fetchone()
        if r and int(r["is_correct"] or 0) == 1:
            correct_n += 1
    total = len(items)
    pct = round(100.0 * correct_n / total) if total else 0
    quiz_passed = total == 0 or pct >= MISS_QUIZ_PASS_PERCENT
    mastery_reset = 0
    if total > 0 and not quiz_passed:
        lk = _learner_key()
        mastery_reset = _mistake_progress_reset_items_after_failed_quiz(db, lk, items)
        db.commit()
        flash(
            f"Below {MISS_QUIZ_PASS_PERCENT}% on this miss quiz—ladder progress for these "
            f"{mastery_reset} question slot(s) was reset. Run the quiz again until you clear the bar."
        )
    first = items[0]
    done_domain = str(first["domain"])
    done_topic = str(first["topic"])
    module_part_id = pack.get("summary_part_id")
    if module_part_id:
        scope_title = "All tracked misses in this SAT unit (this run, shuffled)."
    else:
        scope_title = TOPIC_TITLES.get(done_topic, done_topic)
    any_attempt = next(iter(attempt_map.values()), 0)
    return render_template(
        "miss_quiz_done.html",
        domain=done_domain,
        topic=done_topic,
        topic_title=scope_title,
        attempt_id=int(any_attempt or 0),
        total=total,
        correct_n=correct_n,
        pct=pct,
        label=str(pack.get("label") or "Miss quiz"),
        quiz_passed=quiz_passed,
        pass_percent=MISS_QUIZ_PASS_PERCENT,
        mastery_reset_count=mastery_reset,
        miss_quiz_module_part_id=module_part_id,
    )


@app.route("/practice/miss-quiz/<domain>/<topic>/done")
def practice_miss_quiz_done(domain: str, topic: str):
    pack_raw = session.get(MQ_PACK_KEY)
    pack = _mq_normalize_pack_session(pack_raw or {})
    if pack.get("v") == MQ_PACK_VERSION:
        return redirect(url_for("practice_miss_quiz_run_done"))
    pack = session.pop(MQ_PACK_KEY, None)
    session.pop(MQ_FEEDBACK_KEY, None)
    session.modified = True
    if not pack or pack.get("domain") != domain or pack.get("topic") != topic:
        flash("Miss quiz already closed or restarted.")
        return redirect(url_for("practice_analytics"))
    indices: List[int] = list(pack.get("indices") or [])
    attempt_id = int(pack.get("attempt_id") or 0)
    db = get_db()
    correct_n = 0
    if indices and attempt_id:
        for qi in indices:
            r = db.execute(
                """
                SELECT is_correct FROM practice_responses
                WHERE attempt_id = ? AND question_index = ?
                ORDER BY submitted_at DESC LIMIT 1
                """,
                (attempt_id, qi),
            ).fetchone()
            if r and int(r["is_correct"] or 0) == 1:
                correct_n += 1
    total = len(indices)
    pct = round(100.0 * correct_n / total) if total else 0
    quiz_passed = total == 0 or pct >= MISS_QUIZ_PASS_PERCENT
    mastery_reset = 0
    if total > 0 and not quiz_passed:
        lk = _learner_key()
        mastery_reset = _mistake_progress_reset_slots_after_failed_quiz(
            db, lk, domain, topic, indices
        )
        db.commit()
        flash(
            f"Below {MISS_QUIZ_PASS_PERCENT}% on this miss quiz—ladder progress for these "
            f"{mastery_reset} question slot(s) was reset. Run the quiz again until you clear the bar."
        )
    return render_template(
        "miss_quiz_done.html",
        domain=domain,
        topic=topic,
        topic_title=TOPIC_TITLES.get(topic, topic),
        attempt_id=attempt_id,
        total=total,
        correct_n=correct_n,
        pct=pct,
        label=str(pack.get("label") or "Miss quiz"),
        quiz_passed=quiz_passed,
        pass_percent=MISS_QUIZ_PASS_PERCENT,
        mastery_reset_count=mastery_reset,
        miss_quiz_module_part_id=None,
    )


# -----------------------------------------------------
# Question Page
# -----------------------------------------------------
@app.route("/practice/mistake-redo/outcome/<int:attempt_id>")
def practice_mistake_redo_outcome(attempt_id: int):
    """After a single-question redo from the mistake log: show key + walkthrough, then return."""
    q_index = request.args.get("q_index", type=int)
    if q_index is None or q_index < 0:
        flash("That review link is incomplete.")
        return redirect(url_for("practice_analytics", part="sat"))
    analytics_part = (request.args.get("analytics_part") or "").strip().lower()
    miss_anchor = (request.args.get("miss_anchor") or "").strip()
    db = get_db()
    user_id = session.get("user_id")
    if not _attempt_user_matches(db, attempt_id, user_id):
        flash("Session not found.")
        return redirect(url_for("practice_analytics", part="sat"))
    att = db.execute(
        "SELECT domain, topic FROM practice_attempts WHERE id = ?",
        (attempt_id,),
    ).fetchone()
    if att is None:
        flash("Session not found.")
        return redirect(url_for("practice_analytics", part="sat"))
    domain = str(att["domain"] or "")
    topic = str(att["topic"] or "")
    domain_data = BANKS.get(domain)
    if not domain_data or topic not in domain_data:
        return "Unknown topic", 404
    tex_file = domain_data[topic]
    questions = get_questions_for_topic(domain, topic, tex_file)
    if not questions or q_index >= len(questions):
        return "Invalid question", 404
    qobj = questions[q_index]
    resp = db.execute(
        """
        SELECT selected_answer, correct_answer, is_correct
        FROM practice_responses
        WHERE attempt_id = ? AND question_index = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (attempt_id, q_index),
    ).fetchone()
    if resp is None:
        flash("No submitted answer for that review yet.")
        return redirect(_mistake_analytics_return_href(analytics_part, miss_anchor))
    back_href = _mistake_analytics_return_href(analytics_part, miss_anchor)
    correct_key = extract_correct_answer(qobj)
    expl = qobj.get("explanation_en") or ""
    return render_template(
        "practice_mistake_redo_outcome.html",
        domain=domain,
        topic=topic,
        q_index=q_index,
        q=qobj,
        attempt_id=attempt_id,
        selected_answer=(resp["selected_answer"] or "").strip(),
        correct_answer=(resp["correct_answer"] or "").strip(),
        is_correct=int(resp["is_correct"] or 0),
        correct_key_display=correct_key if correct_key else (resp["correct_answer"] or "—"),
        explanation_en=expl,
        back_href=back_href,
        topic_title=TOPIC_TITLES.get(topic, topic),
        mistake_analytics_part=analytics_part,
        mistake_miss_anchor=miss_anchor,
    )


@app.route("/practice/<domain>/<topic>/<int:qnum>")
def practice_question(domain, topic, qnum):
    domain_data = BANKS.get(domain)
    if not domain_data:
        return "Unknown domain", 404

    tex_file = domain_data.get(topic)
    if not tex_file:
        return "Unknown topic", 404

    questions = get_questions_for_topic(domain, topic, tex_file)
    if not questions:
        return "Question bank file not found", 404

    q = questions[qnum % len(questions)]
    question_index = qnum % len(questions)

    mistake_redo_mode = domain != "placement" and _mistake_redo_flag(
        request.args.get("mistake_redo")
    )
    analytics_part_q = (request.args.get("analytics_part") or "").strip().lower()
    if analytics_part_q and analytics_part_q not in KNOWN_ANALYTICS_PART_IDS:
        analytics_part_q = ""
    miss_anchor_q = _safe_url_fragment(request.args.get("miss_anchor")) or ""
    mistake_return_href = _mistake_analytics_return_href(analytics_part_q, miss_anchor_q)

    db = get_db()
    user_id = session.get("user_id")
    sk = _practice_session_key(domain, topic)
    sk_mr = _practice_mistake_redo_session_key(domain, topic, question_index)
    if mistake_redo_mode:
        attempt_id = session.get(sk_mr)
        row = None
        if attempt_id is not None:
            row = db.execute(
                "SELECT id FROM practice_attempts WHERE id = ? AND domain = ? AND topic = ?",
                (attempt_id, domain, topic),
            ).fetchone()
        if row is None:
            attempt_id = _insert_practice_attempt(
                db, user_id, domain, topic, question_index
            )
            session[sk_mr] = attempt_id
        else:
            attempt_id = int(row["id"])
            _backfill_placement_student_profile(db, attempt_id, domain)
    else:
        attempt_id = session.get(sk)
        row = None
        if attempt_id is not None:
            row = db.execute(
                "SELECT id FROM practice_attempts WHERE id = ? AND domain = ? AND topic = ?",
                (attempt_id, domain, topic),
            ).fetchone()
        if row is None:
            if domain == "placement" and not _placement_profile_from_session()[0]:
                flash("Please complete the student information before starting the diagnostic.")
                return redirect(url_for("placement_start"))
            attempt_id = _insert_practice_attempt(
                db, user_id, domain, topic, question_index
            )
            session[sk] = attempt_id
        else:
            attempt_id = int(row["id"])
            _backfill_placement_student_profile(db, attempt_id, domain)

    answered_rows = db.execute(
        """
        SELECT DISTINCT question_index FROM practice_responses
        WHERE attempt_id = ? AND question_index IS NOT NULL
        """,
        (attempt_id,),
    ).fetchall()
    answered_qset = frozenset(
        int(r["question_index"])
        for r in answered_rows
        if r["question_index"] is not None
    )
    answered_count = len(answered_qset)
    bank_total = len(questions)
    if (
        not mistake_redo_mode
        and bank_total > 0
        and len(answered_qset) >= bank_total
    ):
        return redirect(url_for("practice_session_summary", attempt_id=attempt_id))
    if mistake_redo_mode:
        display_total = 1
        answered_pct = 100 if question_index in answered_qset else 0
        remaining_count = 0 if question_index in answered_qset else 1
    else:
        display_total = bank_total
        answered_pct = (
            min(100, int(round(100 * answered_count / bank_total))) if bank_total else 0
        )
        remaining_count = max(0, bank_total - answered_count)

    is_last = question_index >= bank_total - 1
    if mistake_redo_mode:
        is_last = True

    calc_ok = bool(q.get("calculator_allowed", True))
    placement_mode = domain == "placement"
    choice_letters = [chr(ord("A") + i) for i in range(len(q.get("choices") or []))]
    if placement_mode:
        practice_timer_seconds = 95 * 60
        practice_timer_summary_url = url_for(
            "practice_session_summary", attempt_id=attempt_id
        )
        practice_timer_mode = "countdown"
    else:
        practice_timer_seconds = 0
        practice_timer_summary_url = None
        practice_timer_mode = "elapsed"
    attempt_time_row = db.execute(
        "SELECT CAST(strftime('%s', created_at) AS INTEGER) AS started_unix FROM practice_attempts WHERE id = ?",
        (attempt_id,),
    ).fetchone()
    attempt_started_unix = (
        int(attempt_time_row["started_unix"])
        if attempt_time_row is not None and attempt_time_row["started_unix"] is not None
        else 0
    )

    return render_template(
        "practice_question.html",
        q=q,
        domain=domain,
        topic=topic,
        qnum=question_index,
        total=display_total,
        bank_total=bank_total,
        attempt_id=attempt_id,
        answered_qset=answered_qset,
        answered_count=answered_count,
        answered_pct=answered_pct,
        remaining_count=remaining_count,
        is_last=is_last,
        calculator_allowed=calc_ok,
        placement_mode=placement_mode,
        choice_letters=choice_letters,
        practice_timer_seconds=practice_timer_seconds,
        practice_timer_summary_url=practice_timer_summary_url,
        practice_timer_mode=practice_timer_mode,
        attempt_started_unix=attempt_started_unix,
        miss_quiz_mode=False,
        miss_quiz_v2=False,
        mistake_redo_mode=mistake_redo_mode,
        mistake_return_href=mistake_return_href,
        mistake_analytics_part=analytics_part_q,
        mistake_miss_anchor=miss_anchor_q,
    )


@app.route("/practice/submit", methods=["POST"])
def submit_practice_answer():
    domain = request.form.get("domain", "").strip()
    topic = request.form.get("topic", "").strip()
    raw_answer = request.form.get("selected_answer", "").strip()
    attempt_id_raw = request.form.get("attempt_id", "").strip()
    qnum_raw = request.form.get("qnum", "0").strip()
    mistake_redo = _mistake_redo_flag(request.form.get("mistake_redo"))
    analytics_part_f = (request.form.get("analytics_part") or "").strip().lower()
    if analytics_part_f and analytics_part_f not in KNOWN_ANALYTICS_PART_IDS:
        analytics_part_f = ""
    miss_anchor_f = _safe_url_fragment(request.form.get("miss_anchor")) or ""
    try:
        qnum_for_redirect = int(qnum_raw or 0)
    except ValueError:
        qnum_for_redirect = 0

    if not raw_answer:
        flash("Please enter or select an answer before submitting.")
        if mistake_redo:
            return redirect(
                url_for(
                    "practice_question",
                    domain=domain,
                    topic=topic,
                    qnum=qnum_for_redirect,
                    mistake_redo=1,
                    analytics_part=analytics_part_f or None,
                    miss_anchor=miss_anchor_f or None,
                )
            )
        return redirect(url_for("practice_question", domain=domain, topic=topic, qnum=qnum_for_redirect))

    domain_data = BANKS.get(domain)
    if not domain_data:
        return "Unknown domain", 404

    tex_file = domain_data.get(topic)
    if not tex_file:
        return "Unknown topic", 404

    questions = get_questions_for_topic(domain, topic, tex_file)
    if not questions:
        return "No questions found", 500

    try:
        qnum = int(qnum_raw or 0)
    except ValueError:
        qnum = 0

    q_index = qnum % len(questions)
    question = questions[q_index]
    q_kind = question.get("question_kind", "mcq")
    if q_kind in ("mcq", "mcq5"):
        selected_answer = raw_answer.strip().upper()[:1]
        allowed = {"A", "B", "C", "D", "E"} if q_kind == "mcq5" else {"A", "B", "C", "D"}
        if selected_answer not in allowed:
            span = "A through E" if q_kind == "mcq5" else "A through D"
            flash(f"Please select one answer choice ({span}).")
            if mistake_redo:
                return redirect(
                    url_for(
                        "practice_question",
                        domain=domain,
                        topic=topic,
                        qnum=qnum_for_redirect,
                        mistake_redo=1,
                        analytics_part=analytics_part_f or None,
                        miss_anchor=miss_anchor_f or None,
                    )
                )
            return redirect(
                url_for("practice_question", domain=domain, topic=topic, qnum=qnum_for_redirect)
            )
    else:
        selected_answer = raw_answer

    is_correct, correct_answer = grade_for_db(question, selected_answer)

    db = get_db()
    try:
        attempt_id = int(attempt_id_raw)
    except ValueError:
        attempt_id = None

    # If attempt_id is missing/invalid/nonexistent, create a fallback attempt row.
    attempt_exists = None
    if attempt_id is not None:
        attempt_exists = db.execute(
            "SELECT id FROM practice_attempts WHERE id = ?",
            (attempt_id,),
        ).fetchone()

    if attempt_id is None or attempt_exists is None:
        user_id = session.get("user_id")
        attempt_id = _insert_practice_attempt(db, user_id, domain, topic, q_index)

    db.execute(
        "DELETE FROM practice_responses WHERE attempt_id = ? AND question_index = ?",
        (attempt_id, q_index),
    )
    db.execute(
        """
        INSERT INTO practice_responses
        (attempt_id, question_index, selected_answer, correct_answer, is_correct)
        VALUES (?, ?, ?, ?, ?)
        """,
        (attempt_id, q_index, selected_answer, correct_answer, is_correct),
    )
    lk = _learner_key()
    if is_correct == 1:
        _mistake_progress_on_correct(db, lk, domain, topic, q_index)
    elif is_correct == 0:
        _mistake_progress_on_wrong(db, lk, domain, topic, q_index)
    db.commit()

    if mistake_redo:
        sk_mr = _practice_mistake_redo_session_key(domain, topic, q_index)
        session.pop(sk_mr, None)
        session.modified = True
        return redirect(
            url_for(
                "practice_mistake_redo_outcome",
                attempt_id=attempt_id,
                q_index=q_index,
                analytics_part=analytics_part_f,
                miss_anchor=miss_anchor_f,
            )
        )

    is_last = q_index >= len(questions) - 1
    if not is_last:
        return redirect(
            url_for("practice_question", domain=domain, topic=topic, qnum=q_index + 1)
        )

    sk = _practice_session_key(domain, topic)
    session[sk] = attempt_id
    session.modified = True
    return redirect(url_for("practice_session_summary", attempt_id=attempt_id))


def _practice_session_summary_payload(attempt_id: int) -> dict[str, Any] | tuple[str, int]:
    """Shared data for HTML summary and placement PDF export."""
    db = get_db()
    att = db.execute(
        """
        SELECT id, domain, topic, user_id, created_at, placement_student_name, placement_student_grade,
               placement_student_math_course
        FROM practice_attempts WHERE id = ?
        """,
        (attempt_id,),
    ).fetchone()
    if att is None:
        return ("Session not found", 404)

    domain = att["domain"]
    topic = att["topic"]

    def _att_str(col: str) -> str:
        try:
            v = att[col]
        except (KeyError, IndexError, TypeError):
            return ""
        if v is None:
            return ""
        return str(v).strip()

    placement_student: dict[str, str] | None = None
    if domain == "placement":
        placement_student = {
            "name": _att_str("placement_student_name"),
            "grade": _att_str("placement_student_grade"),
            "math_course": _att_str("placement_student_math_course"),
        }
    else:
        placement_student = None
    sk = _practice_session_key(domain, topic)
    if session.get(sk) != attempt_id:
        session[sk] = attempt_id
        session.modified = True

    tex_file = BANKS.get(domain, {}).get(topic)
    if not tex_file:
        return ("Unknown topic", 404)

    questions = get_questions_for_topic(domain, topic, tex_file)
    if not questions:
        return ("No questions", 500)

    total_q = len(questions)
    resp_rows = db.execute(
        """
        SELECT question_index, selected_answer, correct_answer, is_correct
        FROM practice_responses
        WHERE attempt_id = ? AND question_index IS NOT NULL
        ORDER BY question_index
        """,
        (attempt_id,),
    ).fetchall()
    duration_row = db.execute(
        """
        SELECT
          CAST(strftime('%s', pa.created_at) AS INTEGER) AS start_s,
          CAST(strftime('%s', MAX(pr.submitted_at)) AS INTEGER) AS end_s
        FROM practice_attempts pa
        LEFT JOIN practice_responses pr ON pr.attempt_id = pa.id
        WHERE pa.id = ?
        GROUP BY pa.id
        """,
        (attempt_id,),
    ).fetchone()
    duration_seconds: int | None = None
    if duration_row is not None and duration_row["start_s"] is not None:
        start_s = int(duration_row["start_s"])
        end_raw = duration_row["end_s"]
        if end_raw is not None:
            duration_seconds = max(0, int(end_raw) - start_s)
        elif domain == "placement":
            now_row = db.execute("SELECT CAST(strftime('%s', 'now') AS INTEGER) AS now_s").fetchone()
            if now_row is not None and now_row["now_s"] is not None:
                duration_seconds = min(95 * 60, max(0, int(now_row["now_s"]) - start_s))
    session_duration_label = _format_duration(duration_seconds)
    by_q: Dict[int, Any] = {}
    for r in resp_rows:
        qi = r["question_index"]
        if qi is not None:
            by_q[int(qi)] = r

    rows_out: List[dict] = []
    correct_count = 0
    for i, qobj in enumerate(questions):
        key = extract_correct_answer(qobj)
        r = by_q.get(i)
        disp = qobj.get("display_number", i + 1)
        sec, title_en, topic_detail = _summary_topic_fields(domain, qobj)
        expl = qobj.get("explanation_en", "")

        if r is None:
            status = "skipped"
            yours = "—"
            key_display = key if key else "—"
        else:
            yours_raw = (r["selected_answer"] or "").strip()
            yours = yours_raw if yours_raw else "—"
            key_display = key if key else (r["correct_answer"] or "—")
            if yours == "—":
                status = "skipped"
            elif not key:
                status = "nocheck"
            else:
                graded = response_is_correct(qobj, yours_raw)
                if graded is True:
                    status = "correct"
                    correct_count += 1
                elif graded is False:
                    status = "incorrect"
                else:
                    status = "nocheck"

        rows_out.append(
            {
                "q_index": i,
                "q_display": str(disp),
                "session_q": str(i + 1),
                "row_id": f"summary-q-{i}",
                "knowledge_section": sec,
                "knowledge_title_en": title_en,
                "topic_detail": topic_detail,
                "hard_skill": qobj.get("hard_skill") or "",
                "yours_display": yours,
                "key_display": key_display,
                "status": status,
                "explanation_en": expl,
                "review_href": url_for(
                    "practice_session_item", attempt_id=attempt_id, q_index=i
                ),
            }
        )

    score_pct = round(100.0 * correct_count / total_q) if total_q else 0
    mistake_focus: List[dict] = []
    skipped_count = sum(1 for r in rows_out if r["status"] == "skipped")
    if domain != "placement":
        for i, row in enumerate(rows_out):
            if row["status"] == "incorrect":
                mistake_focus.append(
                    {
                        **row,
                        "q_index": i,
                        "stem_html": questions[i].get("stem") or "",
                        "hard_skill": questions[i].get("hard_skill") or "",
                    }
                )

    section_stats: List[dict] = []
    acc = defaultdict(lambda: {"correct": 0, "total": 0, "title": ""})
    for row, qobj in zip(rows_out, questions):
        sec = qobj.get("knowledge_section", "—")
        acc[sec]["total"] += 1
        acc[sec]["title"] = qobj.get("knowledge_section_title_en", "") or acc[sec]["title"]
        if row["status"] == "correct":
            acc[sec]["correct"] += 1
    if domain == "placement":
        part_order = ("I", "II", "III", "IV", "V")
    elif domain == "algebra":
        part_order = ("1.1", "1.2", "1.3", "1.4", "1.5")
    elif domain == "advanced_math":
        part_order = ("2.1", "2.2", "2.3")
    elif domain == "problem_solving":
        part_order = ("3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7")
    elif domain == "geometry":
        part_order = ("4.1", "4.2", "4.3", "4.4")
    elif domain == "hard_problem":
        part_order = ("Unit 1", "Unit 2", "Unit 3", "Unit 4")
        acc_unit = defaultdict(lambda: {"correct": 0, "total": 0, "title": ""})
        for row, qobj in zip(rows_out, questions):
            sec = qobj.get("knowledge_section", "—")
            acc_unit[sec]["total"] += 1
            acc_unit[sec]["title"] = qobj.get("knowledge_section_title_en", "") or acc_unit[sec]["title"]
            if row["status"] == "correct":
                acc_unit[sec]["correct"] += 1
        acc = acc_unit
    else:
        part_order = tuple(sorted(acc.keys(), key=lambda x: str(x)))
    for sec in part_order:
        if sec not in acc:
            continue
        a = acc[sec]
        t = a["total"]
        section_stats.append(
            {
                "section": sec,
                "title_en": a["title"],
                "correct": a["correct"],
                "total": t,
                "pct": round(100.0 * a["correct"] / t) if t else 0,
            }
        )

    placement_meta = _load_placement_meta_file()
    placement_rec = None
    placement_brand: dict | None = None
    if domain == "placement":
        placement_rec = _placement_recommendation(
            placement_meta, correct_count, total_q
        )
        b = placement_meta.get("brand")
        placement_brand = dict(b) if isinstance(b, dict) else None
        if placement_brand is not None:
            placement_brand.setdefault("report_title", "Official course placement report")
            placement_brand["trust_line"] = (
                f"Score bands follow the printed {SITE_BRAND_NAME} placement guide "
                f"(same 70-item key as the paper diagnostic)."
            )
            placement_brand["trust_line_zh"] = (
                placement_brand.get("trust_line_zh")
                or "分数区间与纸质分班测试官方说明一致（70 题标准答案）。"
            )

    celebrate_confetti = bool(domain == "placement" or score_pct >= 55)

    topic_title = TOPIC_TITLES.get(topic, topic)
    miss_quiz_session_href: str | None = None
    miss_quiz_all_href: str | None = None
    miss_quiz_all_count = 0
    miss_quiz_all_is_module = False
    if domain != "placement":
        if mistake_focus:
            miss_quiz_session_href = url_for(
                "practice_miss_quiz_from_session", attempt_id=attempt_id
            )
        att_uid = att["user_id"]
        miss_ix = _distinct_wrong_indices_for_topic(db, att_uid, domain, topic)
        miss_quiz_all_count = len(miss_ix)
        if miss_quiz_all_count:
            mod_part = MISS_PART_BY_DOMAIN.get(domain)
            if mod_part:
                miss_quiz_all_is_module = True
                miss_quiz_all_href = url_for(
                    "practice_miss_quiz_sat_module", part_id=mod_part
                )
            else:
                miss_quiz_all_href = url_for(
                    "practice_miss_quiz_start", domain=domain, topic=topic
                )

    render = {
        "domain": domain,
        "topic": topic,
        "topic_title": topic_title,
        "attempt_id": attempt_id,
        "rows": rows_out,
        "correct_count": correct_count,
        "total_q": total_q,
        "score_pct": score_pct,
        "session_duration_seconds": duration_seconds,
        "session_duration_label": session_duration_label,
        "section_stats": section_stats,
        "placement_rec": placement_rec,
        "placement_brand": placement_brand,
        "placement_student": placement_student,
        "celebrate_confetti": celebrate_confetti,
        "mistake_focus": mistake_focus,
        "skipped_count": skipped_count,
        "miss_quiz_session_href": miss_quiz_session_href,
        "miss_quiz_all_href": miss_quiz_all_href,
        "miss_quiz_all_count": miss_quiz_all_count,
        "miss_quiz_all_is_module": miss_quiz_all_is_module,
    }
    pdf_ctx = {
        "rows": rows_out,
        "placement_rec": placement_rec,
        "section_stats": section_stats,
        "placement_brand": placement_brand,
        "placement_student": placement_student,
        "correct_count": correct_count,
        "total_q": total_q,
        "score_pct": score_pct,
        "session_duration_seconds": duration_seconds,
        "session_duration_label": session_duration_label,
        "topic_title": topic_title,
        "attempt_id": attempt_id,
    }
    return {"render": render, "pdf_ctx": pdf_ctx}


@app.route("/practice/session/<int:attempt_id>/summary")
def practice_session_summary(attempt_id: int):
    payload = _practice_session_summary_payload(attempt_id)
    if isinstance(payload, tuple):
        return payload[0], payload[1]
    return render_template("practice_session_summary.html", **payload["render"])


@app.route("/practice/session/<int:attempt_id>/item/<int:q_index>")
def practice_session_item(attempt_id: int, q_index: int):
    """Review a single item from a completed session (stem, choices, key, your answer)."""
    db = get_db()
    user_id = session.get("user_id")
    if not _attempt_user_matches(db, attempt_id, user_id):
        flash("Session not found.")
        return redirect(url_for("practice"))
    att = db.execute(
        "SELECT domain, topic FROM practice_attempts WHERE id = ?",
        (attempt_id,),
    ).fetchone()
    if att is None:
        flash("Session not found.")
        return redirect(url_for("practice"))
    domain = str(att["domain"] or "")
    topic = str(att["topic"] or "")
    domain_data = BANKS.get(domain)
    if not domain_data or topic not in domain_data:
        return "Unknown topic", 404
    tex_file = domain_data[topic]
    questions = get_questions_for_topic(domain, topic, tex_file)
    if not questions or q_index < 0 or q_index >= len(questions):
        return "Invalid question", 404
    qobj = questions[q_index]
    resp = db.execute(
        """
        SELECT selected_answer, correct_answer, is_correct
        FROM practice_responses
        WHERE attempt_id = ? AND question_index = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (attempt_id, q_index),
    ).fetchone()
    yours_raw = (resp["selected_answer"] or "").strip() if resp else ""
    correct_key = extract_correct_answer(qobj)
    key_display = correct_key if correct_key else (
        (resp["correct_answer"] or "").strip() if resp else "—"
    )
    if resp is None:
        status = "skipped"
    elif not yours_raw:
        status = "skipped"
    elif not correct_key:
        status = "nocheck"
    else:
        graded = response_is_correct(qobj, yours_raw)
        if graded is True:
            status = "correct"
        elif graded is False:
            status = "incorrect"
        else:
            status = "nocheck"
    choice_letters = ["A", "B", "C", "D"]
    result_choices: List[dict] = []
    if qobj.get("question_kind", "mcq") == "mcq" and qobj.get("choices"):
        for j, html in enumerate(qobj["choices"]):
            letter = choice_letters[j] if j < len(choice_letters) else "?"
            is_selected = yours_raw.upper() == letter if yours_raw else False
            is_correct_choice = (
                correct_key.upper() == letter if correct_key and len(correct_key) == 1 else False
            )
            result_choices.append(
                {
                    "letter": letter,
                    "html": html,
                    "is_selected": is_selected,
                    "is_correct": is_correct_choice,
                }
            )
    summary_href = url_for("practice_session_summary", attempt_id=attempt_id)
    prev_href = (
        url_for("practice_session_item", attempt_id=attempt_id, q_index=q_index - 1)
        if q_index > 0
        else None
    )
    next_href = (
        url_for("practice_session_item", attempt_id=attempt_id, q_index=q_index + 1)
        if q_index + 1 < len(questions)
        else None
    )
    return render_template(
        "practice_session_item.html",
        domain=domain,
        topic=topic,
        topic_title=TOPIC_TITLES.get(topic, topic),
        attempt_id=attempt_id,
        q_index=q_index,
        q=qobj,
        total_q=len(questions),
        status=status,
        yours_display=yours_raw if yours_raw else "—",
        key_display=key_display,
        result_choices=result_choices,
        explanation_en=qobj.get("explanation_en") or "",
        knowledge_section=qobj.get("knowledge_section") or "—",
        knowledge_title_en=qobj.get("knowledge_section_title_en") or "",
        hard_skill=qobj.get("hard_skill") or "",
        summary_href=summary_href,
        prev_href=prev_href,
        next_href=next_href,
    )


@app.route("/practice/session/<int:attempt_id>/placement-report.pdf")
def practice_placement_report_pdf(attempt_id: int):
    payload = _practice_session_summary_payload(attempt_id)
    if isinstance(payload, tuple):
        abort(payload[1])
    render = payload["render"]
    if render["domain"] != "placement":
        abort(404)
    try:
        body = build_placement_parent_pdf(payload["pdf_ctx"])
    except ImportError as exc:
        return Response(
            str(exc),
            status=503,
            mimetype="text/plain; charset=utf-8",
        )
    name = f"novelprep-placement-report-{attempt_id}.pdf"
    return Response(
        body,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.route("/placement/blank-test.pdf")
def placement_blank_test_pdf():
    path = os.path.join(APP_DIR, "Placement_Test.pdf")
    if not os.path.isfile(path):
        abort(404)
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="NovelPrep-Course-Placement-Blank.pdf",
    )


@app.route("/practice/<domain>/<topic>/new-session")
def practice_new_session(domain: str, topic: str):
    session.pop(_practice_session_key(domain, topic), None)
    if domain == "placement" and topic == "placement_full":
        _clear_placement_profile_session()
        return redirect(url_for("placement_start"))
    return redirect(url_for("practice_question", domain=domain, topic=topic, qnum=0))


# =====================================================
# LOGIN
# =====================================================

@app.route("/admin/setup", methods=["GET", "POST"])
def admin_setup():
    init_db()
    db = get_db()
    if _admin_exists(db):
        return redirect(url_for("login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not username or len(username) > 160:
            flash("Enter an admin email or username.")
        elif not password:
            flash("Enter an admin password.")
        elif password != confirm_password:
            flash("Passwords do not match.")
        else:
            try:
                db.execute(
                    """
                    INSERT INTO users (
                        username, password, password_hash, role, is_active,
                        created_at, password_changed_at
                    )
                    VALUES (?, '', ?, 'admin', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (username, generate_password_hash(password)),
                )
                db.commit()
                _backup_after_account_change(db)
            except sqlite3.IntegrityError:
                flash("That username already exists.")
            else:
                flash("Admin account created. Please sign in.")
                return redirect(url_for("login"))

    return render_template("admin_setup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    init_db()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        db = get_db()
        if _login_is_throttled(username):
            flash("Too many failed attempts. Please wait a few minutes and try again.")
            return render_template(
                "login.html",
                needs_admin_setup=not _admin_exists(db),
                db_persistence=_db_persistence_status(),
            )

        user = db.execute(
            """
            SELECT id, username, password, password_hash, role, is_active, access_grants, access_scope
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

        if user and int(user["is_active"] or 0) != 1:
            flash(f"This account is inactive. Please contact {SITE_SUPPORT_CONTACT}.")
        elif user and _password_matches(user, password):
            if not str(user["password_hash"] or ""):
                db.execute(
                    """
                    UPDATE users
                    SET password_hash = ?, password = '', password_changed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (generate_password_hash(password), int(user["id"])),
                )
            db.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (int(user["id"]),))
            db.commit()
            _clear_failed_logins(username)
            _set_login_session(user)
            next_url = (request.args.get("next") or "").strip()
            if not next_url.startswith("/"):
                next_url = ""
            if current_user_can_access_admin():
                return redirect(next_url or url_for("admin"))
            grants = _normalize_access_grants(user["access_grants"] or user["access_scope"])
            if next_url and _path_allowed_for_grants(next_url.split("?")[0], grants, db):
                return redirect(next_url)
            return redirect(_student_home_url(grants))
        else:
            _record_failed_login(username)
            flash("Invalid username or password.")

    db = get_db()
    needs_admin_setup = not _admin_exists(db)

    return render_template(
        "login.html",
        needs_admin_setup=needs_admin_setup,
        db_persistence=_db_persistence_status(),
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _student_rows(db: sqlite3.Connection, q: str) -> List[dict]:
    like = f"%{q}%"
    filters = ["u.role = 'student'"]
    params: List[Any] = []
    if q:
        filters.append("u.username LIKE ?")
        params.append(like)

    rows = db.execute(
        f"""
        SELECT
            u.id,
            u.username,
            u.is_active,
            u.access_grants,
            u.access_scope,
            u.created_at,
            u.last_login_at,
            COUNT(DISTINCT pa.id) AS attempts_total,
            COUNT(pr.id) AS responses_total,
            SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct_total,
            MAX(COALESCE(pr.submitted_at, pa.created_at)) AS last_activity
        FROM users u
        LEFT JOIN practice_attempts pa ON pa.user_id = u.id
        LEFT JOIN practice_responses pr ON pr.attempt_id = pa.id
        WHERE {" AND ".join(filters)}
        GROUP BY u.id
        ORDER BY u.is_active DESC, last_activity DESC, u.created_at DESC
        """,
        tuple(params),
    ).fetchall()

    out: List[dict] = []
    for row in rows:
        responses_total = int(row["responses_total"] or 0)
        correct_total = int(row["correct_total"] or 0)
        out.append(
            {
                "id": int(row["id"]),
                "username": str(row["username"]),
                "is_active": int(row["is_active"] or 0) == 1,
                "access_grants": row["access_grants"],
                "access_grants_label": _access_grants_label(
                    row["access_grants"] or row["access_scope"]
                ),
                "access_grants_set": _normalize_access_grants(
                    row["access_grants"] or row["access_scope"]
                ),
                "created_at": row["created_at"],
                "last_login_at": row["last_login_at"],
                "attempts_total": int(row["attempts_total"] or 0),
                "responses_total": responses_total,
                "accuracy_pct": round(100 * correct_total / responses_total)
                if responses_total
                else None,
                "last_activity": row["last_activity"],
            }
        )
    return out


def _staff_rows(db: sqlite3.Connection) -> List[dict]:
    rows = db.execute(
        """
        SELECT id, username, role, is_active, created_at, last_login_at
        FROM users
        WHERE role = ?
        ORDER BY is_active DESC, created_at DESC
        """,
        (ROLE_STAFF,),
    ).fetchall()
    return [dict(row) for row in rows]


def _recent_record_rows(db: sqlite3.Connection) -> List[dict]:
    return [
        dict(row)
        for row in db.execute(
            """
            SELECT
                pa.id,
                u.username,
                pa.user_id,
                pa.domain,
                pa.topic,
                pa.qnum,
                pa.created_at,
                COUNT(pr.id) AS responses_total,
                SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct_total,
                MAX(pr.submitted_at) AS last_submitted_at
            FROM practice_attempts pa
            LEFT JOIN users u ON u.id = pa.user_id
            LEFT JOIN practice_responses pr ON pr.attempt_id = pa.id
            GROUP BY pa.id
            ORDER BY COALESCE(last_submitted_at, pa.created_at) DESC
            LIMIT 100
            """
        ).fetchall()
    ]


def _admin_attempt_rows(db: sqlite3.Connection, user_id: int | None = None) -> List[dict]:
    where = ""
    params: tuple[Any, ...] = ()
    if user_id is not None:
        where = "WHERE pa.user_id = ?"
        params = (user_id,)

    return [
        dict(row)
        for row in db.execute(
            f"""
            SELECT
                pa.id,
                u.username,
                pa.user_id,
                pa.domain,
                pa.topic,
                pa.qnum,
                pa.created_at,
                COUNT(pr.id) AS responses_total,
                SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct_total,
                MAX(pr.submitted_at) AS last_submitted_at
            FROM practice_attempts pa
            LEFT JOIN users u ON u.id = pa.user_id
            LEFT JOIN practice_responses pr ON pr.attempt_id = pa.id
            {where}
            GROUP BY pa.id
            ORDER BY COALESCE(last_submitted_at, pa.created_at) DESC
            LIMIT 300
            """,
            params,
        ).fetchall()
    ]


def _admin_attempt_detail(db: sqlite3.Connection, attempt_id: int) -> dict | None:
    attempt = db.execute(
        """
        SELECT
            pa.id,
            pa.user_id,
            u.username,
            pa.domain,
            pa.topic,
            pa.qnum,
            pa.created_at
        FROM practice_attempts pa
        LEFT JOIN users u ON u.id = pa.user_id
        WHERE pa.id = ?
        """,
        (attempt_id,),
    ).fetchone()
    if attempt is None:
        return None

    domain = str(attempt["domain"] or "")
    topic = str(attempt["topic"] or "")
    tex_file = BANKS.get(domain, {}).get(topic)
    questions = get_questions_for_topic(domain, topic, tex_file) if tex_file else []
    responses = db.execute(
        """
        SELECT id, question_index, selected_answer, correct_answer, is_correct, submitted_at
        FROM practice_responses
        WHERE attempt_id = ? AND question_index IS NOT NULL
        ORDER BY question_index
        """,
        (attempt_id,),
    ).fetchall()

    rows: List[dict] = []
    for r in responses:
        qi = int(r["question_index"])
        qobj = questions[qi] if 0 <= qi < len(questions) else {}
        selected = str(r["selected_answer"] or "").strip()
        correct = str(r["correct_answer"] or extract_correct_answer(qobj) or "").strip()
        is_correct = r["is_correct"]
        if is_correct == 1:
            status = "Correct"
        elif is_correct == 0:
            status = "Incorrect"
        else:
            status = "Ungraded"
        rows.append(
            {
                "question_number": qi + 1,
                "display_number": qobj.get("display_number", qi + 1),
                "stem_html": qobj.get("stem") or "",
                "choices": qobj.get("choices") or [],
                "selected_answer": selected or "—",
                "correct_answer": correct or "—",
                "status": status,
                "submitted_at": r["submitted_at"],
            }
        )

    correct_total = sum(1 for row in rows if row["status"] == "Correct")
    response_total = len(rows)
    return {
        "attempt": dict(attempt),
        "topic_title": TOPIC_TITLES.get(topic, topic),
        "rows": rows,
        "correct_total": correct_total,
        "response_total": response_total,
        "score_pct": round(100 * correct_total / response_total) if response_total else None,
    }


def _admin_data_snapshot(db: sqlite3.Connection) -> dict:
    def scalar(sql: str, params: tuple[Any, ...] = ()) -> int:
        row = db.execute(sql, params).fetchone()
        return int(row[0] or 0) if row else 0

    return {
        "legacy_attempts": scalar(
            "SELECT COUNT(*) FROM practice_attempts WHERE user_id IS NULL"
        ),
        "legacy_responses": scalar(
            """
            SELECT COUNT(*)
            FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pa.user_id IS NULL
            """
        ),
        "all_attempts": scalar("SELECT COUNT(*) FROM practice_attempts"),
        "all_responses": scalar("SELECT COUNT(*) FROM practice_responses"),
        "progress_rows": scalar("SELECT COUNT(*) FROM mistake_learning_progress"),
    }


def _delete_attempt_scope(db: sqlite3.Connection, where_sql: str, params: tuple[Any, ...]) -> int:
    rows = db.execute(f"SELECT id FROM practice_attempts WHERE {where_sql}", params).fetchall()
    attempt_ids = [int(r["id"]) for r in rows]
    if not attempt_ids:
        return 0
    placeholders = ",".join("?" for _ in attempt_ids)
    db.execute(
        f"DELETE FROM practice_responses WHERE attempt_id IN ({placeholders})",
        tuple(attempt_ids),
    )
    db.execute(
        f"DELETE FROM practice_attempts WHERE id IN ({placeholders})",
        tuple(attempt_ids),
    )
    return len(attempt_ids)


def _clear_all_practice_history(db: sqlite3.Connection) -> None:
    db.execute("DELETE FROM practice_responses")
    db.execute("DELETE FROM practice_attempts")
    db.execute("DELETE FROM mistake_learning_progress")


def _admin_confirm_value(raw: str) -> str:
    return " ".join((raw or "").strip().upper().split())


@app.route("/admin")
def admin():
    gate = _require_admin_response()
    if gate is not None:
        return gate

    db = get_db()
    q = (request.args.get("q") or "").strip()
    students = _student_rows(db, q)
    recent_records = _recent_record_rows(db)
    data_snapshot = _admin_data_snapshot(db)
    totals = {
        "students": len(students),
        "active_students": sum(1 for s in students if s["is_active"]),
        "responses": sum(int(s["responses_total"] or 0) for s in students),
    }
    return render_template(
        "admin.html",
        students=students,
        staff_members=_staff_rows(db) if current_user_is_supervisor() else [],
        recent_records=recent_records,
        data_snapshot=data_snapshot,
        totals=totals,
        q=q,
        user_is_supervisor=current_user_is_supervisor(),
        db_persistence=_db_persistence_status(),
        student_resource_grant_options=STUDENT_RESOURCE_GRANTS,
    )


@app.route("/admin/students/<int:user_id>")
def admin_student_detail(user_id: int):
    gate = _require_admin_response()
    if gate is not None:
        return gate

    db = get_db()
    student = db.execute(
        """
        SELECT id, username, is_active, created_at, access_grants, access_scope
        FROM users WHERE id = ? AND role = 'student'
        """,
        (user_id,),
    ).fetchone()
    if student is None:
        abort(404)
    student_dict = dict(student)
    student_dict["access_grants_label"] = _access_grants_label(
        student["access_grants"] or student["access_scope"]
    )
    student_dict["access_grants_set"] = _normalize_access_grants(
        student["access_grants"] or student["access_scope"]
    )
    attempts = _admin_attempt_rows(db, user_id)
    totals = {
        "sessions": len(attempts),
        "responses": sum(int(a["responses_total"] or 0) for a in attempts),
        "correct": sum(int(a["correct_total"] or 0) for a in attempts),
    }
    totals["accuracy_pct"] = (
        round(100 * totals["correct"] / totals["responses"]) if totals["responses"] else None
    )
    return render_template(
        "admin_student.html",
        student=student_dict,
        attempts=attempts,
        totals=totals,
        student_resource_grant_options=STUDENT_RESOURCE_GRANTS,
    )


@app.route("/admin/records/<int:attempt_id>")
def admin_record_detail(attempt_id: int):
    gate = _require_admin_response()
    if gate is not None:
        return gate
    return redirect(url_for("practice_session_summary", attempt_id=attempt_id))


@app.route("/admin/students", methods=["POST"])
def admin_create_student():
    gate = _require_admin_response()
    if gate is not None:
        return gate

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    grants_json = _access_grants_from_form(request.form.getlist("access_grants"))

    if not username or len(username) > 160:
        flash("Enter a student email or username.")
    elif not password:
        flash("Enter a password for this student.")
    else:
        db = get_db()
        try:
            db.execute(
                """
                INSERT INTO users (username, password, password_hash, role, is_active, access_grants, created_at)
                VALUES (?, '', ?, 'student', 1, ?, CURRENT_TIMESTAMP)
                """,
                (username, generate_password_hash(password), grants_json),
            )
            db.commit()
            label = _access_grants_label(grants_json)
            flash(f"Student account created for {username}. Access: {label}.")
            _backup_after_account_change(db)
        except sqlite3.IntegrityError:
            flash("That student username already exists.")

    return redirect(url_for("admin"))


@app.route("/admin/staff", methods=["POST"])
def admin_create_staff():
    gate = _require_supervisor_response()
    if gate is not None:
        return gate

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if not username or len(username) > 160:
        flash("Enter a colleague email or username.")
    elif not password:
        flash("Enter a password for this colleague account.")
    else:
        db = get_db()
        try:
            db.execute(
                """
                INSERT INTO users (username, password, password_hash, role, is_active, created_at)
                VALUES (?, '', ?, ?, 1, CURRENT_TIMESTAMP)
                """,
                (username, generate_password_hash(password), ROLE_STAFF),
            )
            db.commit()
            flash(f"Colleague account created for {username}. They can view student data in Admin.")
            _backup_after_account_change(db)
        except sqlite3.IntegrityError:
            flash("That username already exists.")

    return redirect(url_for("admin"))


@app.route("/admin/staff/<int:user_id>/reset-password", methods=["POST"])
def admin_reset_staff_password(user_id: int):
    gate = _require_supervisor_response()
    if gate is not None:
        return gate

    password = request.form.get("password", "").strip()
    if not password:
        flash("Enter a new password.")
        return redirect(url_for("admin"))

    db = get_db()
    db.execute(
        """
        UPDATE users
        SET password_hash = ?,
            password = '',
            password_changed_at = CURRENT_TIMESTAMP
        WHERE id = ? AND role = ?
        """,
        (generate_password_hash(password), user_id, ROLE_STAFF),
    )
    db.commit()
    flash("Colleague password updated.")
    _backup_after_account_change(db)
    return redirect(url_for("admin"))


@app.route("/admin/staff/<int:user_id>/toggle-active", methods=["POST"])
def admin_toggle_staff_active(user_id: int):
    gate = _require_supervisor_response()
    if gate is not None:
        return gate

    db = get_db()
    row = db.execute(
        "SELECT is_active FROM users WHERE id = ? AND role = ?",
        (user_id, ROLE_STAFF),
    ).fetchone()
    if row is None:
        flash("Colleague account not found.")
    else:
        next_active = 0 if int(row["is_active"] or 0) == 1 else 1
        db.execute("UPDATE users SET is_active = ? WHERE id = ?", (next_active, user_id))
        db.commit()
        flash("Colleague account status updated.")
        _backup_after_account_change(db)
    return redirect(url_for("admin"))


@app.route("/admin/staff/<int:user_id>/delete", methods=["POST"])
def admin_delete_staff(user_id: int):
    gate = _require_supervisor_response()
    if gate is not None:
        return gate

    confirm = _admin_confirm_value(request.form.get("confirm", ""))
    db = get_db()
    row = db.execute(
        "SELECT username FROM users WHERE id = ? AND role = ?",
        (user_id, ROLE_STAFF),
    ).fetchone()
    if row is None:
        flash("Colleague account not found.")
        return redirect(url_for("admin"))
    if confirm != "DELETE":
        flash("Type DELETE to permanently remove a colleague account.")
        return redirect(url_for("admin"))

    db.execute("DELETE FROM users WHERE id = ? AND role = ?", (user_id, ROLE_STAFF))
    db.commit()
    flash(f"Deleted colleague account {row['username']}.")
    _backup_after_account_change(db)
    return redirect(url_for("admin"))


@app.route("/admin/students/<int:user_id>/access", methods=["POST"])
def admin_update_student_access(user_id: int):
    gate = _require_admin_response()
    if gate is not None:
        return gate

    grants_json = _access_grants_from_form(request.form.getlist("access_grants"))
    db = get_db()
    row = db.execute(
        "SELECT id FROM users WHERE id = ? AND role = 'student'",
        (user_id,),
    ).fetchone()
    if row is None:
        flash("Student not found.")
        return redirect(url_for("admin"))
    db.execute(
        "UPDATE users SET access_grants = ?, access_scope = 'full' WHERE id = ?",
        (grants_json, user_id),
    )
    db.commit()
    flash(f"Access updated: {_access_grants_label(grants_json)}.")
    _backup_after_account_change(db)
    return redirect(url_for("admin_student_detail", user_id=user_id))


@app.route("/admin/students/<int:user_id>/reset-password", methods=["POST"])
def admin_reset_student_password(user_id: int):
    gate = _require_admin_response()
    if gate is not None:
        return gate

    password = request.form.get("password", "").strip()
    if not password:
        flash("Enter a new password.")
        return redirect(url_for("admin"))

    db = get_db()
    db.execute(
        """
        UPDATE users
        SET password_hash = ?,
            password = '',
            password_changed_at = CURRENT_TIMESTAMP
        WHERE id = ? AND role = 'student'
        """,
        (generate_password_hash(password), user_id),
    )
    db.commit()
    flash("Student password updated.")
    _backup_after_account_change(db)
    return redirect(url_for("admin"))


@app.route("/admin/students/<int:user_id>/toggle-active", methods=["POST"])
def admin_toggle_student_active(user_id: int):
    gate = _require_admin_response()
    if gate is not None:
        return gate

    db = get_db()
    row = db.execute(
        "SELECT is_active FROM users WHERE id = ? AND role = 'student'",
        (user_id,),
    ).fetchone()
    if row is None:
        flash("Student not found.")
    else:
        next_active = 0 if int(row["is_active"] or 0) == 1 else 1
        db.execute("UPDATE users SET is_active = ? WHERE id = ?", (next_active, user_id))
        db.commit()
        flash("Student account status updated.")
        _backup_after_account_change(db)
    return redirect(url_for("admin"))


@app.route("/admin/students/<int:user_id>/delete", methods=["POST"])
def admin_delete_student(user_id: int):
    gate = _require_supervisor_response()
    if gate is not None:
        return gate

    confirm = _admin_confirm_value(request.form.get("confirm", ""))
    db = get_db()
    row = db.execute(
        "SELECT username FROM users WHERE id = ? AND role = 'student'",
        (user_id,),
    ).fetchone()
    if row is None:
        flash("Student not found.")
        return redirect(url_for("admin"))
    if confirm != "DELETE":
        flash("Type DELETE to permanently remove a student account.")
        return redirect(url_for("admin"))

    deleted_attempts = _delete_attempt_scope(db, "user_id = ?", (user_id,))
    db.execute("DELETE FROM mistake_learning_progress WHERE learner_key = ?", (f"u:{user_id}",))
    db.execute("DELETE FROM users WHERE id = ? AND role = 'student'", (user_id,))
    db.commit()
    flash(f"Deleted {row['username']} and {deleted_attempts} linked practice sessions.")
    _backup_after_account_change(db)
    return redirect(url_for("admin"))


@app.route("/admin/data/clear-legacy", methods=["POST"])
def admin_clear_legacy_data():
    gate = _require_supervisor_response()
    if gate is not None:
        return gate

    confirm = _admin_confirm_value(request.form.get("confirm", ""))
    if confirm != "CLEAR LEGACY":
        flash("Type CLEAR LEGACY to remove guest / legacy practice records.")
        return redirect(url_for("admin"))

    db = get_db()
    deleted_attempts = _delete_attempt_scope(db, "user_id IS NULL", ())
    db.execute("DELETE FROM mistake_learning_progress WHERE learner_key LIKE 'g:%'")
    db.commit()
    flash(f"Cleared {deleted_attempts} guest / legacy practice sessions.")
    return redirect(url_for("admin"))


@app.route("/admin/data/reset-practice", methods=["POST"])
def admin_reset_practice_data():
    gate = _require_supervisor_response()
    if gate is not None:
        return gate

    confirm = _admin_confirm_value(request.form.get("confirm", ""))
    if confirm != "LAUNCH RESET":
        flash("Type LAUNCH RESET to clear all practice history while keeping accounts.")
        return redirect(url_for("admin"))

    db = get_db()
    _clear_all_practice_history(db)
    db.commit()
    flash("All practice history has been reset. Admin and student accounts were kept.")
    return redirect(url_for("admin"))


@app.route("/admin/records/clear", methods=["POST"])
def admin_clear_all_records():
    gate = _require_supervisor_response()
    if gate is not None:
        return gate

    confirm = _admin_confirm_value(request.form.get("confirm", ""))
    if confirm not in {"CLEAR RECORDS", "CLEAR ALL RECORDS", "LAUNCH RESET"}:
        flash("Type CLEAR RECORDS to remove all recent practice records.")
        return redirect(url_for("admin"))

    db = get_db()
    snapshot = _admin_data_snapshot(db)
    _clear_all_practice_history(db)
    db.commit()
    flash(
        f"Cleared {snapshot['all_attempts']} practice sessions and "
        f"{snapshot['all_responses']} responses. Accounts were kept."
    )
    return redirect(url_for("admin"))


# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888, debug=True)
