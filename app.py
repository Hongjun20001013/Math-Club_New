from __future__ import annotations
from answer_grader import display_answer_plain, grade_for_db, response_is_correct
from course_materials_progress import (
    build_coach_system_prompt,
    build_coach_user_message,
    mastery_pct_from_progress,
    merge_progress,
    openai_chat_completion,
    strip_html,
)
from latex_parser import (
    parse_enhanced_math_placement_tex_file,
    parse_middle_level_placement_tex_file,
    parse_placement_tex_file,
    parse_tex_file,
)

import json
import glob
import os
import random
import re
import secrets
import shutil
import sqlite3
import tempfile
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
PLACEMENT_CATALOG_PATH = os.path.join(APP_DIR, "data", "placement_catalog.json")
PLACEMENT_META_BY_TOPIC: Dict[str, str] = {
    "placement_full": PLACEMENT_META_PATH,
    "enhanced_math_1": os.path.join(APP_DIR, "data", "placement_enhanced_math_1_meta.json"),
    "enhanced_math_2": os.path.join(APP_DIR, "data", "placement_enhanced_math_2_meta.json"),
    "middle_level": os.path.join(APP_DIR, "data", "placement_middle_level_meta.json"),
}

# Part transitions for the 100-item middle-level placement (0-based q indices).
MIDDLE_LEVEL_PART_GATES: List[dict[str, Any]] = [
    {
        "section": "part_ii",
        "session_flag": "placement_middle_seen_part_ii",
        "first_qnum": 20,
        "after_q_index": 19,
        "part_num": 2,
        "band_label": "Math 6 readiness",
        "part_title": "Part II — Math 6/5 Readiness",
        "prev_band": "Math 5",
    },
    {
        "section": "part_iii",
        "session_flag": "placement_middle_seen_part_iii",
        "first_qnum": 40,
        "after_q_index": 39,
        "part_num": 3,
        "band_label": "Math 7 readiness",
        "part_title": "Part III — Math 7/6 Readiness",
        "prev_band": "Math 6",
    },
    {
        "section": "part_iv",
        "session_flag": "placement_middle_seen_part_iv",
        "first_qnum": 60,
        "after_q_index": 59,
        "part_num": 4,
        "band_label": "Math 8 readiness",
        "part_title": "Part IV — Math 8/7 Readiness",
        "prev_band": "Math 7",
    },
    {
        "section": "part_v",
        "session_flag": "placement_middle_seen_part_v",
        "first_qnum": 80,
        "after_q_index": 79,
        "part_num": 5,
        "band_label": "Algebra 1/2 readiness",
        "part_title": "Part V — Algebra 1/2 Readiness",
        "prev_band": "Math 8",
    },
]


def _upper_placement_gate_gates() -> List[dict[str, Any]]:
    """Gate 2–5 transition screens for the upper-school Five-Gate diagnostic."""
    meta = _load_placement_meta_file("placement_full")
    rubric = meta.get("gate_rubric") or []
    if not rubric:
        return []
    rows = sorted(
        [r for r in rubric if isinstance(r, dict)],
        key=lambda r: int(r.get("gate") or 0),
    )
    out: List[dict[str, Any]] = []
    for i, row in enumerate(rows):
        gate_num = int(row.get("gate") or 0)
        if gate_num <= 1:
            continue
        rng = str(row.get("range") or "")
        m = re.match(r"(\d+)\s*[–-]\s*(\d+)", rng)
        if not m:
            continue
        q_start = int(m.group(1))
        q_end = int(m.group(2))
        item_count = int(row.get("items") or (q_end - q_start + 1))
        prev = rows[i - 1]
        prev_num = int(prev.get("gate") or gate_num - 1)
        prev_label = str(prev.get("readiness_label") or f"Gate {prev_num}")
        gate_label = str(row.get("readiness_label") or f"Gate {gate_num}")
        out.append(
            {
                "section": f"gate_{gate_num}",
                "session_flag": f"placement_upper_seen_gate_{gate_num}",
                "first_qnum": q_start - 1,
                "after_q_index": q_start - 2,
                "gate_num": gate_num,
                "gate_label": gate_label,
                "gate_title": f"Gate {gate_num} — {gate_label}",
                "prev_gate": prev_label,
                "prev_gate_title": f"Gate {prev_num} — {prev_label}",
                "item_count": item_count,
                "q_start": q_start,
                "q_end": q_end,
            }
        )
    return out


DESMOS_API_KEY = os.environ.get("DESMOS_API_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
COMPILED_BANK_CACHE = None
COMPILED_BANK_CACHE_MTIME: float | None = None
COURSE_MATERIALS_CACHE = None
COURSE_MATERIALS_CACHE_MTIME: float | None = None

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
    SESSION_COOKIE_SECURE=(
        os.environ.get("RENDER", "").lower() in ("true", "1", "yes")
        or os.environ.get("FORCE_HTTPS", "").lower() in ("true", "1", "yes")
        or os.environ.get("FLASK_ENV", "").lower() == "production"
    ),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)

LOGIN_ATTEMPTS: dict[str, List[float]] = {}

_CSRF_EXEMPT_ENDPOINTS = frozenset({
    "static",
    "health",
    "health_db",
    "health_stylesheet_bundle",
    "login",
    "logout",
    "admin_setup",
    "student_guide",
})


def _ensure_csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_hex(32)
        session["csrf_token"] = token
    return str(token)


def _csrf_token() -> str:
    """Template helper: current session CSRF token."""
    return _ensure_csrf_token()


def _safe_redirect_target(raw: str, *, default: str = "") -> str:
    """Allow only same-site relative paths (blocks //evil.com open redirects)."""
    target = (raw or "").strip()
    if not target.startswith("/") or target.startswith("//"):
        return default
    if "://" in target.split("?", 1)[0]:
        return default
    return target

# Bump when bundled CSS changes. Optional env override per environment.
STYLE_CSS_REVISION = os.environ.get("STYLE_CSS_REVISION", "20260720-test1-tikz-compact")

_DB_SCHEMA_READY = False

_MOJIBAKE_REPAIRS = (
    ("â€™", "'"),
    ("â€˜", "'"),
    ("â€œ", '"'),
    ("â€\x9d", '"'),
    ("â€”", "—"),
    ("â€“", "–"),
    ("Ã—", "×"),
    ("Â°", "°"),
    ("\ufffd", ""),
)


def _sanitize_display_text(value: Any) -> str:
    text = "" if value is None else str(value)
    for bad, good in _MOJIBAKE_REPAIRS:
        text = text.replace(bad, good)
    return text


def _sanitize_question_for_render(q: dict) -> dict:
    out = dict(q)
    out["stem"] = _sanitize_display_text(out.get("stem"))
    choices = out.get("choices")
    if isinstance(choices, list):
        out["choices"] = [_sanitize_display_text(c) for c in choices]
    return out


def _safe_db_commit(db: sqlite3.Connection) -> bool:
    try:
        db.commit()
        return True
    except sqlite3.OperationalError as exc:
        app.logger.warning("DB commit failed: %s", exc)
        try:
            db.rollback()
        except sqlite3.Error:
            pass
        return False


def _wants_json_error() -> bool:
    p = request.path or ""
    if p.startswith("/practice/") and "/api/" in p:
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept


def _practice_redirect(domain: str, topic: str, qnum: int, *, mistake_redo: bool = False, analytics_part: str = "", miss_anchor: str = ""):
    if mistake_redo:
        return redirect(
            url_for(
                "practice_question",
                domain=domain,
                topic=topic,
                qnum=qnum,
                mistake_redo=1,
                analytics_part=analytics_part or None,
                miss_anchor=miss_anchor or None,
            )
        )
    return redirect(url_for("practice_question", domain=domain, topic=topic, qnum=qnum))


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
    if not os.environ.get("DESMOS_API_KEY", "").strip():
        app.logger.warning(
            "DESMOS_API_KEY is not set. Graph practice pages will not load Desmos."
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
    global _DB_SCHEMA_READY
    if _DB_SCHEMA_READY:
        return
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
    user_cols = _table_columns(db, "users")
    if "registered_by" not in user_cols:
        db.execute("ALTER TABLE users ADD COLUMN registered_by INTEGER")
    if "student_view_scope" not in user_cols:
        db.execute(
            "ALTER TABLE users ADD COLUMN student_view_scope TEXT NOT NULL DEFAULT 'own'"
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
    att_cols = _table_columns(db, "practice_attempts")
    if "exam_meta_json" not in att_cols:
        db.execute("ALTER TABLE practice_attempts ADD COLUMN exam_meta_json TEXT")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS miss_quiz_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            label TEXT,
            scope_part_id TEXT,
            item_count INTEGER NOT NULL DEFAULT 0,
            correct_count INTEGER NOT NULL DEFAULT 0,
            pct INTEGER NOT NULL DEFAULT 0,
            passed INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_miss_quiz_runs_user ON miss_quiz_runs(user_id, created_at DESC)"
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
        """
        CREATE TABLE IF NOT EXISTS sat_mistake_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            learner_key TEXT NOT NULL,
            items_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            time_limit_seconds INTEGER NOT NULL DEFAULT 2100,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS sat_mistake_test_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            item_order INTEGER NOT NULL,
            domain TEXT NOT NULL,
            topic TEXT NOT NULL,
            question_index INTEGER NOT NULL,
            selected_answer TEXT NOT NULL,
            correct_answer TEXT,
            is_correct INTEGER,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(test_id, item_order),
            FOREIGN KEY (test_id) REFERENCES sat_mistake_tests (id)
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_mistake_progress_learner "
        "ON mistake_learning_progress(learner_key)"
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS course_material_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lesson_slug TEXT NOT NULL,
            progress_json TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, lesson_slug),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_cm_progress_user "
        "ON course_material_progress(user_id)"
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS course_class_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_slug TEXT NOT NULL,
            title TEXT,
            created_by INTEGER,
            is_active INTEGER NOT NULL DEFAULT 1,
            current_slide_index INTEGER NOT NULL DEFAULT 1,
            slide_updated_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            ended_at DATETIME,
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_course_class_sessions_lesson "
        "ON course_class_sessions(lesson_slug, is_active)"
    )
    session_cols = _table_columns(db, "course_class_sessions")
    if "current_slide_index" not in session_cols:
        db.execute(
            "ALTER TABLE course_class_sessions ADD COLUMN current_slide_index INTEGER NOT NULL DEFAULT 1"
        )
    if "slide_updated_at" not in session_cols:
        db.execute("ALTER TABLE course_class_sessions ADD COLUMN slide_updated_at DATETIME")
    session_cols = _table_columns(db, "course_class_sessions")
    if "laser_slide_index" not in session_cols:
        db.execute("ALTER TABLE course_class_sessions ADD COLUMN laser_slide_index INTEGER")
    if "laser_x" not in session_cols:
        db.execute("ALTER TABLE course_class_sessions ADD COLUMN laser_x REAL")
    if "laser_y" not in session_cols:
        db.execute("ALTER TABLE course_class_sessions ADD COLUMN laser_y REAL")
    if "laser_active" not in session_cols:
        db.execute(
            "ALTER TABLE course_class_sessions ADD COLUMN laser_active INTEGER NOT NULL DEFAULT 0"
        )
    if "laser_updated_at" not in session_cols:
        db.execute("ALTER TABLE course_class_sessions ADD COLUMN laser_updated_at DATETIME")
    session_cols = _table_columns(db, "course_class_sessions")
    if "laser_trail_json" not in session_cols:
        db.execute("ALTER TABLE course_class_sessions ADD COLUMN laser_trail_json TEXT")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS course_class_roster (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, user_id),
            FOREIGN KEY (session_id) REFERENCES course_class_sessions (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_course_class_roster_session "
        "ON course_class_roster(session_id)"
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS course_class_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            lesson_slug TEXT NOT NULL,
            slide_index INTEGER NOT NULL,
            question_title TEXT,
            user_id INTEGER NOT NULL,
            username TEXT,
            selected_answer TEXT NOT NULL,
            correct_answer TEXT,
            is_correct INTEGER,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, slide_index, user_id),
            FOREIGN KEY (session_id) REFERENCES course_class_sessions (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_course_class_responses_session "
        "ON course_class_responses(session_id, slide_index)"
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS course_class_slide_ink (
            session_id INTEGER NOT NULL,
            slide_index INTEGER NOT NULL,
            strokes_json TEXT NOT NULL DEFAULT '[]',
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (session_id, slide_index),
            FOREIGN KEY (session_id) REFERENCES course_class_sessions (id) ON DELETE CASCADE
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS student_cohorts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS student_cohort_members (
            cohort_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (cohort_id, user_id),
            FOREIGN KEY (cohort_id) REFERENCES student_cohorts (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_student_cohort_members_user "
        "ON student_cohort_members(user_id)"
    )
    db.execute(
        """
        UPDATE users
        SET password = ''
        WHERE password_hash IS NOT NULL AND TRIM(password_hash) != ''
          AND password IS NOT NULL AND TRIM(password) != ''
        """
    )
    _seed_users_if_empty(db)
    _sync_render_users_seed_snapshot(db)
    _maybe_auto_backup_database()
    db.commit()
    _DB_SCHEMA_READY = True


@app.after_request
def apply_reliability_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    if response.content_type and response.content_type.startswith("application/json"):
        response.headers["Content-Type"] = "application/json; charset=utf-8"
    if response.content_type and "text/html" in response.content_type:
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.errorhandler(404)
def handle_not_found(_err):
    if _wants_json_error():
        return jsonify({"ok": False, "error": "not found"}), 404
    return (
        render_template(
            "error.html",
            code=404,
            title="Page not found",
            message="This page does not exist or may have moved.",
        ),
        404,
    )


@app.errorhandler(500)
def handle_internal_error(err):
    app.logger.exception("Unhandled server error: %s", err)
    if _wants_json_error():
        return jsonify({"ok": False, "error": "Server error. Please try again."}), 500
    return (
        render_template(
            "error.html",
            code=500,
            title="Something went wrong",
            message="Please refresh and try again. If you were submitting an answer, your progress is usually saved.",
        ),
        500,
    )


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
        p.startswith("/admin")
        or p in ("/", "")
        or p.startswith("/login")
        or p.startswith("/register")
    )

    grants = current_user_access_grants()
    visible_tracks = _visible_learning_tracks(grants)
    nav_show_dashboard = grants is None or "dashboard" in grants
    nav_show_workspace = grants is None or "sat" in grants
    nav_show_analytics = grants is None or "sat" in grants
    student_home_href = url_for("index") if grants is None else _student_home_url(grants)

    show_np_desmos = bool(p.startswith("/practice") and not p.startswith("/practice/analytics"))

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
        "hard_drill_meta": _hard_drill_display_meta(),
        "csrf_token": _csrf_token(),
        **_site_branding_context(),
    }


def require_login() -> bool:
    return "user_id" in session


ROLE_ADMIN = "admin"
ROLE_STAFF = "staff"
ROLE_STUDENT = "student"
STAFF_ROLES = frozenset({ROLE_ADMIN, ROLE_STAFF})
STAFF_VIEW_ALL = "all"
STAFF_VIEW_OWN = "own"

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
        "description": "Middle, Integrated, and upper-school placement diagnostics with PDF reports",
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
        "materials",
        "mistakes",
        "submit",
        "miss-quiz",
        "mistake-redo",
        "session",
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
        if p.startswith("/practice/materials"):
            return "sat" in grants
        if p.startswith("/practice/mistakes"):
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


def _current_staff_view_scope(db: sqlite3.Connection) -> str:
    if current_user_is_supervisor():
        return STAFF_VIEW_ALL
    if current_user_role() != ROLE_STAFF:
        return STAFF_VIEW_OWN
    uid = session.get("user_id")
    if not uid:
        return STAFF_VIEW_OWN
    row = db.execute(
        "SELECT student_view_scope FROM users WHERE id = ? AND role = ?",
        (uid, ROLE_STAFF),
    ).fetchone()
    if row is None:
        return STAFF_VIEW_OWN
    scope = str(row["student_view_scope"] or STAFF_VIEW_OWN).strip().lower()
    return scope if scope == STAFF_VIEW_ALL else STAFF_VIEW_OWN


def _staff_student_scope_clause(
    db: sqlite3.Connection, table_alias: str = "u"
) -> tuple[str, list[Any]]:
    """Limit student listings for colleagues who only manage their own enrollments."""
    if current_user_is_supervisor():
        return "", []
    if current_user_role() != ROLE_STAFF:
        return "", []
    if _current_staff_view_scope(db) == STAFF_VIEW_ALL:
        return "", []
    uid = session.get("user_id")
    if not uid:
        return f" AND {table_alias}.id = 0", []
    return f" AND {table_alias}.registered_by = ?", [int(uid)]


def _staff_can_view_student(db: sqlite3.Connection, student_id: int) -> bool:
    if current_user_is_supervisor():
        return True
    if current_user_role() != ROLE_STAFF:
        return False
    row = db.execute(
        "SELECT registered_by FROM users WHERE id = ? AND role = 'student'",
        (student_id,),
    ).fetchone()
    if row is None:
        return False
    if _current_staff_view_scope(db) == STAFF_VIEW_ALL:
        return True
    return int(row["registered_by"] or 0) == int(session.get("user_id") or 0)


def _require_student_access(db: sqlite3.Connection, student_id: int) -> None:
    if not _staff_can_view_student(db, student_id):
        abort(403)


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
def _prepare_csrf_token():
    if request.endpoint not in _CSRF_EXEMPT_ENDPOINTS:
        _ensure_csrf_token()


@app.before_request
def _validate_csrf_on_mutations():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None
    endpoint = request.endpoint or ""
    if endpoint in _CSRF_EXEMPT_ENDPOINTS or endpoint == "":
        return None
    submitted = (
        request.form.get("csrf_token")
        or request.headers.get("X-CSRF-Token")
        or ""
    )
    expected = str(session.get("csrf_token") or "")
    if expected and secrets.compare_digest(str(submitted), expected):
        return None
    wants_json = (
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in (request.accept_mimetypes.best or "")
    )
    if wants_json:
        return jsonify({"ok": False, "error": "Invalid or missing CSRF token."}), 403
    flash("Your session expired or the form was invalid. Please try again.")
    return redirect(request.referrer or url_for("index"))


@app.before_request
def require_authenticated_user():
    endpoint = request.endpoint or ""
    if endpoint in {
        "static",
        "health",
        "health_db",
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


def _placement_flow_config(topic: str) -> dict | None:
    """Online section layout for multi-part placement tests."""
    row = _placement_test_by_topic(topic)
    if not row or str(row.get("status") or "") != "available":
        return None
    if topic == "middle_level":
        return {
            "mc_count": 0,
            "graph_count": 0,
            "fr_count": 100,
            "total": 100,
            "has_gates": True,
            "gate_kind": "middle_parts",
            "session_prefix": "placement_middle",
            "mc_scored": False,
        }
    if topic == "placement_full":
        mc = int(row.get("online_mcq_count") or row.get("online_item_count") or 85)
        return {
            "mc_count": mc,
            "graph_count": 0,
            "fr_count": 0,
            "total": mc,
            "has_gates": True,
            "gate_kind": "upper_gates",
            "session_prefix": "placement_upper",
            "mc_scored": True,
        }
    mc = int(row.get("online_mcq_count") or 0)
    total = int(row.get("online_item_count") or 0)
    graph = 4 if topic in ("enhanced_math_1", "enhanced_math_2") else 0
    fr = max(0, total - mc - graph)
    session_prefix = {
        "enhanced_math_1": "placement_em1",
        "enhanced_math_2": "placement_em2",
    }.get(topic)
    return {
        "mc_count": mc,
        "graph_count": graph,
        "fr_count": fr,
        "total": total or (mc + graph + fr),
        "has_gates": bool(session_prefix and mc > 0 and graph > 0),
        "gate_kind": "enhanced_sections",
        "session_prefix": session_prefix,
        "mc_scored": topic in ("enhanced_math_1", "enhanced_math_2"),
    }


def _placement_timer_seconds(topic: str) -> int:
    return {
        "enhanced_math_1": 120 * 60,
        "enhanced_math_2": 130 * 60,
        "middle_level": 150 * 60,
        "placement_full": 115 * 60,
    }.get(topic, 115 * 60)


# Phase 3 mock / word-problem sets: ~Digital SAT Module pace (≈35 min / 22 Q).
PHASE3_PACE_SECONDS = 95  # 1 minute 35 seconds per question
PHASE3_PACE_TOPICS = frozenset({"hard_20", "hard_21"})


def _phase3_pace_seconds(domain: str, topic: str) -> int | None:
    if domain == "hard_problem" and topic in PHASE3_PACE_TOPICS:
        return PHASE3_PACE_SECONDS
    return None


def _clear_placement_section_flags(topic: str) -> None:
    cfg = _placement_flow_config(topic)
    if not cfg:
        return
    if cfg.get("gate_kind") == "middle_parts":
        for gate in MIDDLE_LEVEL_PART_GATES:
            session.pop(str(gate["session_flag"]), None)
        return
    if cfg.get("gate_kind") == "upper_gates":
        for gate in _upper_placement_gate_gates():
            session.pop(str(gate["session_flag"]), None)
        return
    prefix = cfg.get("session_prefix")
    if not prefix:
        return
    prefix = str(prefix)
    session.pop(f"{prefix}_seen_graphing", None)
    session.pop(f"{prefix}_seen_fr", None)


def _load_placement_meta_file(topic: str | None = None) -> dict:
    path = PLACEMENT_META_BY_TOPIC.get(str(topic or "placement_full"), PLACEMENT_META_PATH)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _load_placement_catalog() -> dict:
    if not os.path.isfile(PLACEMENT_CATALOG_PATH):
        return {"tiers": []}
    try:
        with open(PLACEMENT_CATALOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {"tiers": []}
    except (OSError, json.JSONDecodeError):
        return {"tiers": []}


def _placement_tests_flat() -> list[dict]:
    out: list[dict] = []
    for tier in _load_placement_catalog().get("tiers") or []:
        if not isinstance(tier, dict):
            continue
        for test in tier.get("tests") or []:
            if isinstance(test, dict):
                row = dict(test)
                row["tier_id"] = tier.get("id")
                row["tier_title"] = tier.get("title")
                row["tier_title_zh"] = tier.get("title_zh")
                row["tier_description"] = tier.get("description")
                out.append(row)
    return out


def _placement_test_by_slug(slug: str) -> dict | None:
    slug = (slug or "").strip().lower()
    for row in _placement_tests_flat():
        if str(row.get("slug") or "").lower() == slug:
            return row
    return None


def _placement_test_by_topic(topic: str) -> dict | None:
    topic = (topic or "").strip()
    for row in _placement_tests_flat():
        if str(row.get("topic") or "") == topic:
            return row
    return None


def _placement_topic_for_slug(slug: str) -> str | None:
    row = _placement_test_by_slug(slug)
    if not row:
        return None
    topic = str(row.get("topic") or "").strip()
    return topic if topic in BANKS.get("placement", {}) else None


def _placement_slug_for_topic(topic: str) -> str:
    row = _placement_test_by_topic(topic)
    if row and row.get("slug"):
        return str(row["slug"])
    if topic == "placement_full":
        return "upper-algebra-precalc"
    return topic.replace("_", "-")


def _placement_pdf_meta(pdf_file: str | None) -> dict[str, Any]:
    """Lightweight metadata for blank-test PDF download cards."""
    name = str(pdf_file or "").strip()
    if not name:
        return {"available": False}
    path = os.path.join(APP_DIR, name)
    if not os.path.isfile(path):
        return {"available": False, "file": name}
    pages: int | None = None
    log_path = os.path.splitext(path)[0] + ".log"
    if os.path.isfile(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
                for line in lf:
                    m = re.search(r"Output written on .*?\((\d+) pages,", line)
                    if m:
                        pages = int(m.group(1))
                        break
        except OSError:
            pass
    mtime = datetime.fromtimestamp(os.path.getmtime(path))
    updated_label = mtime.strftime("%b %d, %Y").replace(" 0", " ")
    return {
        "available": True,
        "file": name,
        "pages": pages,
        "updated_at": mtime.isoformat(),
        "updated_label": updated_label,
        "size_kb": max(1, int(os.path.getsize(path) / 1024)),
    }


def _enrich_placement_catalog_with_pdf_meta(catalog: dict) -> dict:
    out = dict(catalog)
    tiers: list[dict] = []
    for tier in out.get("tiers") or []:
        if not isinstance(tier, dict):
            continue
        tier_copy = dict(tier)
        tests: list[dict] = []
        for test in tier_copy.get("tests") or []:
            if not isinstance(test, dict):
                continue
            row = dict(test)
            row["pdf_meta"] = _placement_pdf_meta(row.get("pdf_file"))
            tests.append(row)
        tier_copy["tests"] = tests
        tiers.append(tier_copy)
    out["tiers"] = tiers
    return out


def _placement_landing_parts_for_topic(topic: str) -> list[dict[str, str]]:
    row = _placement_test_by_topic(topic)
    parts = row.get("parts") if isinstance(row, dict) else None
    if isinstance(parts, list) and parts:
        return [dict(p) for p in parts if isinstance(p, dict)]
    return list(PLACEMENT_LANDING_PARTS)


def _placement_tier_for_course_key(course_key: str, topic: str | None = None) -> int:
    if topic == "enhanced_math_1":
        return {
            "below_math_i": 1,
            "borderline_math_i": 2,
            "math_i_ready": 3,
            "borderline_enhanced": 4,
            "enhanced_math_i_ready": 5,
        }.get(course_key, 2)
    if topic == "enhanced_math_2":
        return {
            "below_math_ii": 1,
            "borderline_math_ii": 2,
            "math_ii_ready": 3,
            "borderline_enhanced_math_ii": 4,
            "enhanced_math_ii_ready": 5,
        }.get(course_key, 2)
    if topic == "middle_level":
        return {
            "math_5_focus": 1,
            "math_6_7_track": 2,
            "math_8_algebra_track": 3,
            "algebra_readiness": 4,
        }.get(course_key, 2)
    return _placement_tier_for_course_key_legacy(course_key)


def _placement_tier_for_course_key_legacy(course_key: str) -> int:
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


def _enrich_placement_rec(row: dict, raw_score: int, total_q: int, topic: str | None = None) -> dict:
    out = dict(row)
    lo = int(out.get("min_score", 0))
    hi = int(out.get("max_score", total_q or 70))
    out["band_range"] = f"{lo}-{hi}"
    out["raw_score"] = raw_score
    out["total_q"] = total_q
    ck = str(out.get("course_key") or "")
    out["tier"] = int(out.get("tier") or _placement_tier_for_course_key(ck, topic))
    if not isinstance(out.get("highlights"), list):
        out["highlights"] = []
    return out


def _placement_gate_scores_from_sections(
    section_stats: list[dict], meta: dict
) -> list[dict]:
    """Merge per-section stats with ``gate_rubric`` thresholds from placement meta."""
    rubric = meta.get("gate_rubric") or []
    if not rubric:
        return []
    by_sec = {str(s.get("section")): s for s in section_stats}
    out: list[dict] = []
    for row in rubric:
        if not isinstance(row, dict):
            continue
        gate = int(row.get("gate") or 0)
        if gate < 1:
            continue
        sec_key = str(gate)
        stat = by_sec.get(sec_key, {})
        correct = int(stat.get("correct") or 0)
        total = int(row.get("items") or stat.get("total") or 0)
        standard = int(row.get("standard_pass") or 0)
        strong = int(row.get("strong_pass") or standard)
        if correct >= strong:
            pass_tier = "strong"
        elif correct >= standard:
            pass_tier = "standard"
        else:
            pass_tier = "below"
        pct = round(100.0 * correct / total) if total else 0
        title = stat.get("title_en") or f"Gate {gate} — {row.get('readiness_label', '')}"
        out.append(
            {
                "gate": gate,
                "section": sec_key,
                "range": str(row.get("range") or ""),
                "readiness_label": str(row.get("readiness_label") or ""),
                "correct": correct,
                "total": total,
                "pct": pct,
                "standard_pass": standard,
                "strong_pass": strong,
                "passed": correct >= standard if standard else False,
                "pass_tier": pass_tier,
                "title_en": title,
            }
        )
    return out


def _placement_gate_recommendation(
    gate_scores: list[dict], meta: dict
) -> dict | None:
    """Gate-first placement label from the printed Five-Gate Hybrid teacher guide."""
    if not gate_scores:
        return None
    g = {int(x["gate"]): int(x.get("correct") or 0) for x in gate_scores}
    c1, c2, c3, c4, c5 = (
        g.get(1, 0),
        g.get(2, 0),
        g.get(3, 0),
        g.get(4, 0),
        g.get(5, 0),
    )
    if c1 >= 12 and c2 >= 16 and c3 >= 12 and c4 >= 12 and c5 >= 11:
        course_key = "calculus_readiness"
        headline = "Gate profile: calculus-track readiness on this diagnostic."
    elif c1 >= 11 and c2 >= 13 and c3 >= 11 and c4 >= 12:
        course_key = "precalculus"
        headline = "Gate profile: strong precalculus readiness; calculus bridge may be appropriate."
    elif c1 >= 11 and c2 >= 13 and c3 >= 11:
        course_key = "precalculus"
        headline = "Gate profile: precalculus is the matched next course level."
    elif c1 >= 11 and c2 >= 13:
        course_key = "algebra_ii"
        headline = "Gate profile: algebra II is the natural next step."
    elif c1 >= 11:
        course_key = "geometry"
        headline = "Gate profile: geometry readiness with algebra foundations in place."
    else:
        course_key = "algebra_i"
        headline = "Gate profile: strengthen algebra foundations before advancing."

    band_row = None
    for row in meta.get("score_band_rubric") or []:
        if isinstance(row, dict) and row.get("course_key") == course_key:
            band_row = row
            break
    title = str((band_row or {}).get("title") or course_key.replace("_", " ").title())
    summary = str(
        (band_row or {}).get("summary")
        or "Interpret gate scores together with classwork quality and school prerequisites."
    )
    tier = int(
        (band_row or {}).get("tier")
        or _placement_tier_for_course_key(course_key, "placement_full")
    )
    return {
        "course_key": course_key,
        "title": title,
        "headline": headline,
        "summary": summary,
        "tier": tier,
        "gate_scores": gate_scores,
    }


def _placement_recommendation(
    meta: dict, raw_score: int, total_q: int, topic: str | None = None
) -> dict | None:
    """Prefer total-score bands; fall back to percent rubric."""
    for row in meta.get("score_band_rubric") or []:
        if not isinstance(row, dict):
            continue
        lo = int(row.get("min_score", -1))
        hi = int(row.get("max_score", 999))
        if lo <= raw_score <= hi:
            return _enrich_placement_rec(row, raw_score, total_q, topic)
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
                out.get("tier")
                or _placement_tier_for_course_key(str(out.get("course_key") or ""), topic)
            )
            if not isinstance(out.get("highlights"), list):
                out["highlights"] = []
            return out
    return None


def apply_placement_calculator_flags(questions: List[dict], topic: str | None = None) -> List[dict]:
    """Attach calculator_allowed from placement meta (default false if unset)."""
    meta = _load_placement_meta_file(topic)
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
    global COMPILED_BANK_CACHE, COMPILED_BANK_CACHE_MTIME
    try:
        mtime = os.path.getmtime(COMPILED_BANK_PATH)
    except OSError:
        COMPILED_BANK_CACHE = {}
        COMPILED_BANK_CACHE_MTIME = None
        return COMPILED_BANK_CACHE
    if COMPILED_BANK_CACHE is not None and COMPILED_BANK_CACHE_MTIME == mtime:
        return COMPILED_BANK_CACHE
    try:
        with open(COMPILED_BANK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            COMPILED_BANK_CACHE = data
            COMPILED_BANK_CACHE_MTIME = mtime
        else:
            COMPILED_BANK_CACHE = {}
            COMPILED_BANK_CACHE_MTIME = mtime
    except (OSError, json.JSONDecodeError):
        COMPILED_BANK_CACHE = {}
        COMPILED_BANK_CACHE_MTIME = None
    return COMPILED_BANK_CACHE


def _resolve_course_material_file(candidates: list[str], *, require_content: bool = False) -> str | None:
    for rel in candidates:
        path = os.path.join(APP_DIR, rel)
        if not os.path.isfile(path):
            continue
        if require_content and os.path.getsize(path) <= 0:
            continue
        return path
    return None


def _course_materials_manifest_index() -> dict[str, dict[str, Any]]:
    if not os.path.isfile(COURSE_MATERIALS_MANIFEST_PATH):
        return {}
    try:
        with open(COURSE_MATERIALS_MANIFEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        str(row.get("slug") or ""): row
        for row in (data.get("materials") or [])
        if row.get("slug")
    }


def _apply_parsed_course_material(entry: dict[str, Any], parsed: dict[str, Any]) -> None:
    entry["deck_title"] = parsed.get("title") or entry.get("title")
    entry["slide_count"] = parsed.get("slide_count") or 0
    entry["slides"] = parsed.get("slides") or []
    entry["interactive_count"] = parsed.get("interactive_count") or 0
    entry["learn_count"] = parsed.get("learn_count") or 0
    entry["practice_slide_count"] = parsed.get("practice_slide_count") or 0
    entry["lesson_path"] = parsed.get("lesson_path") or []
    entry["checkpoint"] = parsed.get("checkpoint") or []
    entry["checkpoint_count"] = parsed.get("checkpoint_count") or 0
    entry["knowledge_map"] = parsed.get("knowledge_map") or []


def _sync_course_materials_with_disk(payload: dict[str, Any]) -> dict[str, Any]:
    """Align lesson availability with files on disk; parse LaTeX when JSON is stale."""
    manifest_index = _course_materials_manifest_index()
    if not manifest_index:
        return payload

    from beamer_parser import parse_beamer_file

    available = 0
    for entry in payload.get("materials") or []:
        slug = str(entry.get("slug") or "")
        manifest_row = manifest_index.get(slug)
        if not manifest_row:
            continue

        tex_path = _resolve_course_material_file(
            list(manifest_row.get("tex_candidates") or []),
            require_content=True,
        )
        pdf_path = _resolve_course_material_file(list(manifest_row.get("pdf_candidates") or []))

        entry["tex_available"] = tex_path is not None
        entry["pdf_available"] = pdf_path is not None
        entry["tex_file"] = os.path.basename(tex_path) if tex_path else None
        entry["pdf_file"] = os.path.basename(pdf_path) if pdf_path else None

        if not tex_path:
            continue

        needs_parse = not entry.get("slides") or int(entry.get("slide_count") or 0) <= 0
        if needs_parse:
            try:
                _apply_parsed_course_material(entry, parse_beamer_file(tex_path))
            except Exception as exc:
                app.logger.warning("Failed to parse course material %s: %s", slug, exc)
                entry["tex_available"] = False
                continue

        if entry.get("tex_available"):
            available += 1

    payload["available"] = available
    payload["total"] = len(payload.get("materials") or [])
    return payload


def load_course_materials() -> dict[str, Any]:
    global COURSE_MATERIALS_CACHE, COURSE_MATERIALS_CACHE_MTIME
    json_mtime: float | None = None
    if os.path.isfile(COURSE_MATERIALS_PATH):
        try:
            json_mtime = os.path.getmtime(COURSE_MATERIALS_PATH)
        except OSError:
            json_mtime = None

    if COURSE_MATERIALS_CACHE is not None and json_mtime == COURSE_MATERIALS_CACHE_MTIME:
        return COURSE_MATERIALS_CACHE

    if not os.path.isfile(COURSE_MATERIALS_PATH):
        COURSE_MATERIALS_CACHE = {"materials": [], "total": 0, "available": 0}
        COURSE_MATERIALS_CACHE_MTIME = json_mtime
        return COURSE_MATERIALS_CACHE

    try:
        with open(COURSE_MATERIALS_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        payload = {"materials": [], "total": 0, "available": 0}

    COURSE_MATERIALS_CACHE = _sync_course_materials_with_disk(payload)
    COURSE_MATERIALS_CACHE_MTIME = json_mtime
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


def _course_material_neighbors(material: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    prev_m = next_m = None
    prev_slug = material.get("prev_lesson_slug")
    next_slug = material.get("next_lesson_slug")
    if prev_slug:
        row = _course_material_by_slug(str(prev_slug))
        if row and row.get("tex_available"):
            prev_m = row
    if next_slug:
        row = _course_material_by_slug(str(next_slug))
        if row and row.get("tex_available"):
            next_m = row
    return prev_m, next_m


def _pick_continue_material(
    ready_materials: list[dict[str, Any]],
    user_progress: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Best lesson to resume: most recently active, else first incomplete."""
    best: dict[str, Any] | None = None
    best_at = 0
    for m in ready_materials:
        slug = str(m.get("slug") or "")
        prog = user_progress.get(slug) or {}
        at = int(prog.get("last_active_at") or 0)
        if at > best_at:
            best_at = at
            best = m
    if best and best_at > 0:
        prog = user_progress.get(str(best.get("slug") or "")) or {}
        return {
            **best,
            "continue_slide": int(prog.get("last_slide_index") or 1),
            "continue_mastery_pct": int(best.get("user_mastery_pct") or 0),
        }
    for m in ready_materials:
        slug = str(m.get("slug") or "")
        prog = user_progress.get(slug) or {}
        pct = mastery_pct_from_progress(
            prog,
            int(m.get("slide_count") or 0),
            int(m.get("checkpoint_count") or 0),
        )
        if pct < 100:
            return {
                **m,
                "continue_slide": int(prog.get("last_slide_index") or 1),
                "continue_mastery_pct": pct,
            }
    return None


def _course_materials_user_progress(materials: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    user_progress: dict[str, dict[str, Any]] = {}
    uid = session.get("user_id")
    if uid:
        db = get_db()
        rows = db.execute(
            "SELECT lesson_slug, progress_json FROM course_material_progress WHERE user_id = ?",
            (int(uid),),
        ).fetchall()
        for row in rows:
            try:
                user_progress[str(row["lesson_slug"])] = json.loads(row["progress_json"] or "{}")
            except json.JSONDecodeError:
                continue
    for m in materials:
        if not m.get("tex_available"):
            continue
        slug = str(m.get("slug") or "")
        prog = user_progress.get(slug) or {}
        m["user_mastery_pct"] = mastery_pct_from_progress(
            prog,
            int(m.get("slide_count") or 0),
            int(m.get("checkpoint_count") or 0),
        )
    return user_progress


def _course_materials_phase_groups(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    phase_meta = {
        1: {
            "label": "Phase 1",
            "kicker": "Basic Knowledge Training",
            "description": "Core SAT foundations — Units 1–4 definitions, methods, and guided practice.",
        },
        2: {
            "label": "Phase 2",
            "kicker": "Hard Question Training",
            "description": "Challenge problem sets with interactive slides and live classroom tracking.",
        },
        3: {
            "label": "Phase 3",
            "kicker": "Mock Exam Training",
            "description": "Full Module 2-style mock sets and exam drills that build speed, stamina, and test readiness.",
        },
    }
    phase_groups: list[dict[str, Any]] = []
    for phase_num in (1, 2, 3):
        phase_rows = [m for m in materials if int(m.get("phase") or 1) == phase_num]
        unit_groups: list[dict[str, Any]] = []
        unit_nums = sorted({int(m.get("unit") or 0) for m in phase_rows})
        for unit_num in unit_nums:
            rows = [m for m in phase_rows if int(m.get("unit") or 0) == unit_num]
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
        phase_groups.append(
            {
                "phase": phase_num,
                "label": phase_meta[phase_num]["label"],
                "kicker": phase_meta[phase_num]["kicker"],
                "description": phase_meta[phase_num]["description"],
                "unit_groups": unit_groups,
                "materials": phase_rows,
                "ready_count": sum(1 for m in phase_rows if m.get("tex_available")),
                "total_count": len(phase_rows),
            }
        )
    return phase_groups


def _course_materials_gate_context() -> dict[str, Any]:
    materials = list(load_course_materials().get("materials") or [])
    _course_materials_user_progress(materials)
    phase_groups = _course_materials_phase_groups(materials)
    return {"phase_cards": phase_groups}


def _course_materials_phase_context(phase_num: int) -> dict[str, Any] | None:
    if phase_num not in (1, 2, 3):
        return None
    materials = list(load_course_materials().get("materials") or [])
    user_progress = _course_materials_user_progress(materials)
    phase_groups = _course_materials_phase_groups(materials)
    phase_group = next((g for g in phase_groups if g["phase"] == phase_num), None)
    if not phase_group:
        return None
    phase_ready = sorted(
        [m for m in phase_group["materials"] if m.get("tex_available")],
        key=lambda m: tuple(
            int(p) if p.isdigit() else 0
            for p in str(m.get("section") or "0").split(".")
        ),
    )
    continue_material = _pick_continue_material(phase_ready, user_progress)
    spotlight_material = continue_material or (phase_ready[0] if phase_ready else None)
    spotlight_mode = "resume" if continue_material else "start"
    return {
        "phase_group": phase_group,
        "continue_material": continue_material,
        "spotlight_material": spotlight_material,
        "spotlight_mode": spotlight_mode,
        "user_progress_map": user_progress,
    }


def _course_materials_hub_context() -> dict[str, Any]:
    materials = list(load_course_materials().get("materials") or [])
    phase_groups = _course_materials_phase_groups(materials)
    unit_groups: list[dict[str, Any]] = []
    for unit_num in (1, 2, 3, 4):
        rows = [m for m in materials if int(m.get("phase") or 1) == 1 and int(m.get("unit") or 0) == unit_num]
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
    ready_materials = sorted(
        [m for m in materials if m.get("tex_available")],
        key=lambda m: tuple(
            int(p) if p.isdigit() else 0
            for p in str(m.get("section") or "0").split(".")
        ),
    )
    materials_total = int(payload.get("total") or len(materials))
    materials_ready = int(payload.get("available") or len(ready_materials))
    coverage_pct = round(100 * materials_ready / materials_total) if materials_total else 0
    featured = ready_materials[-1] if ready_materials else None
    user_progress = _course_materials_user_progress(materials)
    continue_material = _pick_continue_material(ready_materials, user_progress)
    unit1_path = [
        m for m in ready_materials
        if int(m.get("unit") or 0) == 1
    ]
    return {
        "phase_groups": phase_groups,
        "unit_groups": unit_groups,
        "materials_total": materials_total,
        "materials_ready": materials_ready,
        "coverage_pct": coverage_pct,
        "ready_materials": ready_materials,
        "featured_material": featured,
        "continue_material": continue_material,
        "unit1_path": unit1_path,
        "user_progress_map": user_progress,
    }


def _cm_progress_row(db: sqlite3.Connection, user_id: int, slug: str) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT progress_json, updated_at FROM course_material_progress "
        "WHERE user_id = ? AND lesson_slug = ?",
        (user_id, slug),
    ).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row["progress_json"] or "{}")
    except json.JSONDecodeError:
        data = {}
    return {"progress": data, "updated_at": row["updated_at"]}


def _cm_progress_save(db: sqlite3.Connection, user_id: int, slug: str, progress: dict[str, Any]) -> bool:
    db.execute(
        """
        INSERT INTO course_material_progress (user_id, lesson_slug, progress_json, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(user_id, lesson_slug) DO UPDATE SET
            progress_json = excluded.progress_json,
            updated_at = datetime('now')
        """,
        (user_id, slug, json.dumps(progress, ensure_ascii=False)),
    )
    return _safe_db_commit(db)


def _cm_classroom_question_slides(material: dict[str, Any]) -> list[dict[str, Any]]:
    slides = material.get("slides") or []
    questions: list[dict[str, Any]] = []
    for slide in slides:
        if slide.get("kind") not in {"question", "practice", "example"}:
            continue
        html = str(slide.get("html") or "")
        if "data-cm-mcq" not in html and "data-cm-grid-in" not in html:
            continue
        questions.append(
            {
                "slide_index": int(slide.get("index") or 0),
                "title": str(slide.get("title") or f"Slide {slide.get('index')}"),
                "kind": str(slide.get("kind") or "question"),
            }
        )
    return questions


def _cm_active_class_session(db: sqlite3.Connection, slug: str) -> sqlite3.Row | None:
    return db.execute(
        """
        SELECT id, lesson_slug, title, created_by, is_active, current_slide_index,
               slide_updated_at, created_at, ended_at
        FROM course_class_sessions
        WHERE lesson_slug = ? AND is_active = 1
        ORDER BY id DESC
        LIMIT 1
        """,
        (slug,),
    ).fetchone()


def _student_cohort_rows(db: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT
            c.id,
            c.name,
            c.description,
            c.is_default,
            c.created_at,
            COUNT(m.user_id) AS member_count
        FROM student_cohorts c
        LEFT JOIN student_cohort_members m ON m.cohort_id = c.id
        GROUP BY c.id, c.name, c.description, c.is_default, c.created_at
        ORDER BY c.is_default DESC, lower(c.name)
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _student_cohort_member_ids(db: sqlite3.Connection, cohort_id: int) -> set[int]:
    rows = db.execute(
        "SELECT user_id FROM student_cohort_members WHERE cohort_id = ?",
        (cohort_id,),
    ).fetchall()
    return {int(row["user_id"]) for row in rows}


def _student_cohorts_for_classroom(db: sqlite3.Connection) -> list[dict[str, Any]]:
    cohorts = []
    for row in _student_cohort_rows(db):
        cid = int(row["id"])
        member_ids = sorted(_student_cohort_member_ids(db, cid))
        cohorts.append(
            {
                "id": cid,
                "name": str(row["name"] or ""),
                "description": str(row["description"] or ""),
                "is_default": int(row["is_default"] or 0) == 1,
                "member_count": len(member_ids),
                "member_ids": member_ids,
            }
        )
    return cohorts


def _student_cohort_by_id(db: sqlite3.Connection, cohort_id: int) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT id, name, description, is_default, created_at FROM student_cohorts WHERE id = ?",
        (cohort_id,),
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["member_ids"] = sorted(_student_cohort_member_ids(db, cohort_id))
    data["member_count"] = len(data["member_ids"])
    data["is_default"] = int(data.get("is_default") or 0) == 1
    return data


def _set_default_student_cohort(db: sqlite3.Connection, cohort_id: int) -> None:
    db.execute("UPDATE student_cohorts SET is_default = 0")
    db.execute("UPDATE student_cohorts SET is_default = 1 WHERE id = ?", (cohort_id,))


def _cm_slide_ink_payload(
    db: sqlite3.Connection, session_id: int, slide_index: int
) -> dict[str, Any]:
    row = db.execute(
        """
        SELECT strokes_json, updated_at
        FROM course_class_slide_ink
        WHERE session_id = ? AND slide_index = ?
        """,
        (session_id, slide_index),
    ).fetchone()
    if row is None:
        return {"strokes": [], "updated_at": None}
    try:
        strokes = json.loads(row["strokes_json"] or "[]")
    except json.JSONDecodeError:
        strokes = []
    if not isinstance(strokes, list):
        strokes = []
    return {
        "strokes": strokes,
        "updated_at": row["updated_at"],
    }


def _cm_save_slide_ink(
    db: sqlite3.Connection, session_id: int, slide_index: int, strokes: list[Any]
) -> str | None:
    safe_strokes: list[Any] = []
    for stroke in strokes[:120]:
        if not isinstance(stroke, dict):
            continue
        points = stroke.get("points")
        if not isinstance(points, list) or len(points) < 2:
            continue
        norm_points: list[list[float]] = []
        for pt in points[:800]:
            if (
                isinstance(pt, (list, tuple))
                and len(pt) >= 2
                and isinstance(pt[0], (int, float))
                and isinstance(pt[1], (int, float))
            ):
                norm_points.append(
                    [
                        max(0.0, min(1.0, float(pt[0]))),
                        max(0.0, min(1.0, float(pt[1]))),
                    ]
                )
        if len(norm_points) < 2:
            continue
        color = str(stroke.get("color") or "#ef4444")[:16]
        try:
            width = float(stroke.get("width") or 3)
        except (TypeError, ValueError):
            width = 3.0
        kind = str(stroke.get("kind") or "")
        if kind == "latex":
            latex = str(stroke.get("latex") or "")[:500]
            if not latex:
                continue
            try:
                sx = max(0.0, min(1.0, float(stroke.get("x") or norm_points[0][0])))
                sy = max(0.0, min(1.0, float(stroke.get("y") or norm_points[0][1])))
                ssize = max(0.01, min(0.12, float(stroke.get("size") or 0.038)))
            except (TypeError, ValueError):
                continue
            safe_strokes.append(
                {
                    "kind": "latex",
                    "latex": latex,
                    "x": sx,
                    "y": sy,
                    "size": ssize,
                    "color": color,
                    "width": max(1.0, min(12.0, width)),
                    "points": [[sx, sy], [sx, sy]],
                    "tool": str(stroke.get("tool") or "math")[:16],
                }
            )
            continue
        if kind == "stamp":
            text = str(stroke.get("text") or "")[:8]
            if not text:
                continue
            try:
                sx = max(0.0, min(1.0, float(stroke.get("x") or norm_points[0][0])))
                sy = max(0.0, min(1.0, float(stroke.get("y") or norm_points[0][1])))
                ssize = max(0.01, min(0.12, float(stroke.get("size") or 0.032)))
            except (TypeError, ValueError):
                continue
            safe_strokes.append(
                {
                    "kind": "stamp",
                    "text": text,
                    "x": sx,
                    "y": sy,
                    "size": ssize,
                    "color": color,
                    "width": max(1.0, min(12.0, width)),
                    "points": [[sx, sy], [sx, sy]],
                    "tool": str(stroke.get("tool") or "math")[:16],
                }
            )
            continue
        safe_strokes.append(
            {
                "points": norm_points,
                "color": color,
                "width": max(1.0, min(12.0, width)),
                **{
                    k: stroke.get(k)
                    for k in (
                        "alpha",
                        "tool",
                        "kind",
                        "shape",
                        "cx",
                        "cy",
                        "r",
                        "x1",
                        "y1",
                        "x2",
                        "y2",
                        "x",
                        "y",
                        "w",
                        "h",
                        "text",
                        "latex",
                        "size",
                    )
                    if stroke.get(k) is not None
                },
            }
        )
    payload = json.dumps(safe_strokes, separators=(",", ":"))
    db.execute(
        """
        INSERT INTO course_class_slide_ink (session_id, slide_index, strokes_json, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(session_id, slide_index) DO UPDATE SET
            strokes_json = excluded.strokes_json,
            updated_at = datetime('now')
        """,
        (session_id, slide_index, payload),
    )
    row = db.execute(
        """
        SELECT updated_at FROM course_class_slide_ink
        WHERE session_id = ? AND slide_index = ?
        """,
        (session_id, slide_index),
    ).fetchone()
    return str(row["updated_at"]) if row else None


def _cm_laser_payload(
    db: sqlite3.Connection, session_id: int, slide_index: int
) -> dict[str, Any]:
    row = db.execute(
        """
        SELECT laser_slide_index, laser_x, laser_y, laser_active, laser_updated_at,
               laser_trail_json
        FROM course_class_sessions
        WHERE id = ?
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        return {
            "active": False,
            "x": None,
            "y": None,
            "slide_index": None,
            "updated_at": None,
            "trail": [],
        }
    active = bool(row["laser_active"]) and int(row["laser_slide_index"] or 0) == slide_index
    trail: list[list[float]] = []
    if active and row["laser_trail_json"]:
        try:
            parsed = json.loads(row["laser_trail_json"] or "[]")
            if isinstance(parsed, list):
                for pt in parsed[:20]:
                    if (
                        isinstance(pt, (list, tuple))
                        and len(pt) >= 2
                        and isinstance(pt[0], (int, float))
                        and isinstance(pt[1], (int, float))
                    ):
                        trail.append(
                            [
                                max(0.0, min(1.0, float(pt[0]))),
                                max(0.0, min(1.0, float(pt[1]))),
                            ]
                        )
        except json.JSONDecodeError:
            trail = []
    return {
        "active": active,
        "x": float(row["laser_x"]) if active and row["laser_x"] is not None else None,
        "y": float(row["laser_y"]) if active and row["laser_y"] is not None else None,
        "slide_index": int(row["laser_slide_index"]) if row["laser_slide_index"] is not None else None,
        "updated_at": row["laser_updated_at"],
        "trail": trail,
    }


def _cm_save_laser(
    db: sqlite3.Connection,
    session_id: int,
    slide_index: int,
    active: bool,
    x: float | None,
    y: float | None,
    trail: list[Any] | None = None,
) -> str | None:
    safe_trail: list[list[float]] = []
    if isinstance(trail, list):
        for pt in trail[:20]:
            if (
                isinstance(pt, (list, tuple))
                and len(pt) >= 2
                and isinstance(pt[0], (int, float))
                and isinstance(pt[1], (int, float))
            ):
                safe_trail.append(
                    [
                        max(0.0, min(1.0, float(pt[0]))),
                        max(0.0, min(1.0, float(pt[1]))),
                    ]
                )
    trail_json = json.dumps(safe_trail, separators=(",", ":")) if safe_trail else "[]"
    if active and x is not None and y is not None:
        db.execute(
            """
            UPDATE course_class_sessions
            SET laser_slide_index = ?,
                laser_x = ?,
                laser_y = ?,
                laser_active = 1,
                laser_trail_json = ?,
                laser_updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                slide_index,
                max(0.0, min(1.0, float(x))),
                max(0.0, min(1.0, float(y))),
                trail_json,
                session_id,
            ),
        )
    else:
        db.execute(
            """
            UPDATE course_class_sessions
            SET laser_active = 0,
                laser_trail_json = '[]',
                laser_updated_at = datetime('now')
            WHERE id = ?
            """,
            (session_id,),
        )
    row = db.execute(
        "SELECT laser_updated_at FROM course_class_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    return str(row["laser_updated_at"]) if row and row["laser_updated_at"] else None


def _cm_available_classroom_students(db: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT id, username, access_grants, access_scope
        FROM users
        WHERE role = 'student' AND is_active = 1
        ORDER BY lower(username)
        """
    ).fetchall()
    students = []
    for row in rows:
        students.append(
            {
                "id": int(row["id"]),
                "username": str(row["username"] or f"Student {row['id']}"),
                "access_label": _access_grants_label(row["access_grants"] or row["access_scope"]),
            }
        )
    return students


def _cm_session_roster(db: sqlite3.Connection, session_id: int) -> dict[int, str]:
    rows = db.execute(
        """
        SELECT user_id, username
        FROM course_class_roster
        WHERE session_id = ?
        ORDER BY lower(username)
        """,
        (session_id,),
    ).fetchall()
    if rows:
        return {
            int(row["user_id"]): str(row["username"] or f"Student {row['user_id']}")
            for row in rows
        }
    # Backward compatibility for sessions created before roster selection existed.
    return {
        item["id"]: item["username"]
        for item in _cm_available_classroom_students(db)
    }


def _cm_classroom_summary(db: sqlite3.Connection, material: dict[str, Any], session_id: int) -> dict[str, Any]:
    slug = str(material.get("slug") or "")
    session_row = db.execute(
        """
        SELECT ccs.*, u.username AS teacher_username
        FROM course_class_sessions ccs
        LEFT JOIN users u ON u.id = ccs.created_by
        WHERE ccs.id = ? AND ccs.lesson_slug = ?
        """,
        (session_id, slug),
    ).fetchone()
    if not session_row:
        return {"ok": False, "error": "session not found"}
    rows = db.execute(
        """
        SELECT slide_index, question_title, user_id, username, selected_answer,
               correct_answer, is_correct, submitted_at
        FROM course_class_responses
        WHERE session_id = ?
        ORDER BY slide_index, lower(username)
        """,
        (session_id,),
    ).fetchall()
    by_slide: dict[int, list[sqlite3.Row]] = {}
    students: dict[int, str] = {}
    for row in rows:
        slide_index = int(row["slide_index"])
        by_slide.setdefault(slide_index, []).append(row)
        students[int(row["user_id"])] = str(row["username"] or f"Student {row['user_id']}")
    roster = _cm_session_roster(db, int(session_id))
    questions = []
    student_stats = {
        uid: {
            "user_id": uid,
            "username": name,
            "submitted": 0,
            "correct": 0,
            "accuracy": None,
            "wrong_questions": [],
        }
        for uid, name in roster.items()
    }
    answered_by_student: dict[int, set[int]] = {}
    for q in _cm_classroom_question_slides(material):
        slide_index = int(q["slide_index"])
        q_rows = by_slide.get(slide_index, [])
        submitted = len(q_rows)
        correct = sum(1 for r in q_rows if int(r["is_correct"] or 0) == 1)
        choice_counts: dict[str, int] = {}
        submitted_ids = set()
        for r in q_rows:
            user_id = int(r["user_id"])
            submitted_ids.add(user_id)
            if user_id not in student_stats:
                student_stats[user_id] = {
                    "user_id": user_id,
                    "username": str(r["username"] or f"Student {user_id}"),
                    "submitted": 0,
                    "correct": 0,
                    "accuracy": None,
                    "wrong_questions": [],
                }
            answered_by_student.setdefault(user_id, set()).add(slide_index)
            student_stats[user_id]["submitted"] += 1
            if int(r["is_correct"] or 0) == 1:
                student_stats[user_id]["correct"] += 1
            else:
                student_stats[user_id]["wrong_questions"].append(
                    {
                        "slide_index": slide_index,
                        "title": str(q.get("title") or f"Slide {slide_index}"),
                        "selected": str(r["selected_answer"] or ""),
                        "correct_answer": str(r["correct_answer"] or ""),
                    }
                )
            choice = str(r["selected_answer"] or "—").strip() or "—"
            choice_counts[choice] = choice_counts.get(choice, 0) + 1
        missing_students = [
            {"user_id": uid, "username": name}
            for uid, name in roster.items()
            if uid not in submitted_ids
        ]
        completion = round(100 * submitted / len(roster)) if roster else None
        teach_ready = bool(roster and submitted >= len(roster))
        almost_ready = bool(roster and submitted >= max(1, round(len(roster) * 0.8)))
        questions.append(
            {
                **q,
                "submitted": submitted,
                "correct": correct,
                "accuracy": round(100 * correct / submitted) if submitted else None,
                "completion": completion,
                "teach_ready": teach_ready,
                "almost_ready": almost_ready,
                "choice_counts": choice_counts,
                "missing_students": missing_students,
                "responses": [
                    {
                        "user_id": int(r["user_id"]),
                        "username": str(r["username"] or f"Student {r['user_id']}"),
                        "selected_answer": str(r["selected_answer"] or ""),
                        "correct_answer": str(r["correct_answer"] or ""),
                        "is_correct": bool(r["is_correct"]),
                        "submitted_at": r["submitted_at"],
                    }
                    for r in q_rows
                ],
            }
        )
    all_question_slides = [int(q["slide_index"]) for q in questions]
    for uid, stat in student_stats.items():
        stat["accuracy"] = round(100 * stat["correct"] / stat["submitted"]) if stat["submitted"] else None
        stat["completion"] = round(100 * stat["submitted"] / len(questions)) if questions else None
        answered = answered_by_student.get(uid, set())
        missing = [si for si in all_question_slides if si not in answered]
        stat["missing_slides"] = missing
        stat["missing_count"] = len(missing)
    question_count = len(questions)
    total_submitted = sum(int(q["submitted"]) for q in questions)
    total_correct = sum(int(q["correct"]) for q in questions)
    total_expected = question_count * len(roster)
    weakest_questions = sorted(
        [q for q in questions if int(q["submitted"]) > 0],
        key=lambda item: (101 if item["accuracy"] is None else int(item["accuracy"]), -int(item["submitted"])),
    )[:5]
    report = {
        "question_count": question_count,
        "total_expected": total_expected,
        "total_submitted": total_submitted,
        "total_correct": total_correct,
        "overall_accuracy": round(100 * total_correct / total_submitted) if total_submitted else None,
        "completion_rate": round(100 * total_submitted / total_expected) if total_expected else None,
        "completed_questions": sum(1 for q in questions if q["teach_ready"]),
        "ready_questions": sum(1 for q in questions if q["teach_ready"] or q["almost_ready"]),
        "weakest_questions": weakest_questions,
        # Struggling students first so the teacher can intervene quickly;
        # students who have not started yet go to the end.
        "student_breakdown": sorted(
            student_stats.values(),
            key=lambda item: (
                1 if not item["submitted"] else 0,
                item["accuracy"] if item["accuracy"] is not None else 999,
                -(item["submitted"] or 0),
                item["username"].lower(),
            ),
        ),
    }
    return {
        "ok": True,
        "session": {
            "id": int(session_row["id"]),
            "lesson_slug": slug,
            "title": session_row["title"],
            "is_active": bool(session_row["is_active"]),
            "created_at": session_row["created_at"],
            "ended_at": session_row["ended_at"],
            "teacher_username": session_row["teacher_username"],
        },
        "lesson": {
            "slug": slug,
            "section": material.get("section"),
            "title": material.get("title"),
        },
        "student_count": len(students),
        "roster_count": len(roster),
        "roster_students": [
            {"user_id": uid, "username": name}
            for uid, name in roster.items()
        ],
        "report": report,
        "questions": questions,
    }


@app.route("/practice/materials/api/progress/<slug>", methods=["GET", "POST"])
def practice_course_material_progress_api(slug: str):
    if not require_login():
        return jsonify({"ok": False, "error": "login required"}), 401
    material = _course_material_by_slug(slug)
    if not material:
        return jsonify({"ok": False, "error": "lesson not found"}), 404
    uid = int(session["user_id"])
    db = get_db()
    if request.method == "GET":
        row = _cm_progress_row(db, uid, slug)
        return jsonify({"ok": True, "progress": (row or {}).get("progress") or {}, "updated_at": (row or {}).get("updated_at")})
    data = request.get_json(silent=True) or {}
    progress = data.get("progress")
    if not isinstance(progress, dict):
        return jsonify({"ok": False, "error": "invalid progress payload"}), 400
    try:
        if not _cm_progress_save(db, uid, slug, progress):
            return jsonify({"ok": False, "error": "server busy, please try again"}), 503
    except Exception:
        app.logger.exception("course material progress save failed slug=%s", slug)
        return jsonify({"ok": False, "error": "could not save progress"}), 500
    return jsonify({"ok": True})


@app.route("/practice/materials/<slug>/classroom")
def practice_course_material_classroom(slug: str):
    staff_redirect = _require_staff_response()
    if staff_redirect:
        return staff_redirect
    material = _course_material_by_slug(slug)
    if not material:
        abort(404)
    db = get_db()
    active = _cm_active_class_session(db, slug)
    latest = active or db.execute(
        """
        SELECT id, lesson_slug, title, created_by, is_active, current_slide_index,
               slide_updated_at, created_at, ended_at
        FROM course_class_sessions
        WHERE lesson_slug = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (slug,),
    ).fetchone()
    return render_template(
        "course_material_classroom.html",
        material=material,
        active_session=dict(latest) if latest else None,
        start_api=url_for("practice_course_material_classroom_start_api", slug=slug),
        end_api=url_for("practice_course_material_classroom_end_api", slug=slug),
        summary_api=url_for("practice_course_material_classroom_summary_api", slug=slug),
        lesson_href=url_for("practice_course_material_view", slug=slug),
        student_roster=_cm_available_classroom_students(db),
        student_cohorts=_student_cohorts_for_classroom(db),
    )


@app.route("/practice/materials/api/classroom/<slug>/active")
def practice_course_material_classroom_active_api(slug: str):
    if not require_login():
        return jsonify({"ok": False, "error": "login required"}), 401
    material = _course_material_by_slug(slug)
    if not material:
        return jsonify({"ok": False, "error": "lesson not found"}), 404
    db = get_db()
    row = _cm_active_class_session(db, slug)
    if not row:
        return jsonify({"ok": True, "active": False})
    if not current_user_can_access_admin():
        roster = _cm_session_roster(db, int(row["id"]))
        try:
            uid = int(session["user_id"])
        except (KeyError, TypeError, ValueError):
            uid = 0
        if uid not in roster:
            grants = current_user_access_grants()
            if grants is not None and "sat" not in grants:
                return jsonify({"ok": True, "active": False})
            username = str(session.get("username") or f"student-{uid}")[:120]
            db.execute(
                """
                INSERT OR IGNORE INTO course_class_roster (session_id, user_id, username, created_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (int(row["id"]), uid, username),
            )
            _safe_db_commit(db)
    slide_index = int(row["current_slide_index"] or 1)
    ink = _cm_slide_ink_payload(db, int(row["id"]), slide_index)
    laser = _cm_laser_payload(db, int(row["id"]), slide_index)
    return jsonify(
        {
            "ok": True,
            "active": True,
            "session": {
                "id": int(row["id"]),
                "lesson_slug": slug,
                "title": row["title"],
                "created_at": row["created_at"],
                "current_slide_index": slide_index,
                "slide_updated_at": row["slide_updated_at"],
                "ink_updated_at": ink.get("updated_at"),
                "laser": laser,
            },
        }
    )


@app.route("/practice/materials/api/classroom/<slug>/ink", methods=["GET", "POST"])
def practice_course_material_classroom_ink_api(slug: str):
    if not require_login():
        return jsonify({"ok": False, "error": "login required"}), 401
    material = _course_material_by_slug(slug)
    if not material:
        return jsonify({"ok": False, "error": "lesson not found"}), 404
    db = get_db()
    active = _cm_active_class_session(db, slug)
    if not active:
        return jsonify({"ok": False, "error": "no active classroom session"}), 409
    session_id = int(active["id"])
    if request.method == "GET":
        try:
            slide_index = int(request.args.get("slide_index") or active["current_slide_index"] or 1)
        except (TypeError, ValueError):
            slide_index = int(active["current_slide_index"] or 1)
        ink = _cm_slide_ink_payload(db, session_id, slide_index)
        laser = _cm_laser_payload(db, session_id, slide_index)
        if request.args.get("fields") == "laser":
            return jsonify({"ok": True, "session_id": session_id, "slide_index": slide_index, "laser": laser})
        return jsonify(
            {
                "ok": True,
                "session_id": session_id,
                "slide_index": slide_index,
                "strokes": ink["strokes"],
                "updated_at": ink["updated_at"],
                "laser": laser,
            }
        )

    staff_redirect = _require_staff_response()
    if staff_redirect:
        return jsonify({"ok": False, "error": "staff required"}), 403
    data = request.get_json(silent=True) or {}
    try:
        slide_index = int(data.get("slide_index"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "slide_index required"}), 400
    strokes = data.get("strokes")
    laser = data.get("laser")
    if strokes is None and laser is None:
        return jsonify({"ok": False, "error": "strokes or laser required"}), 400
    updated_at = None
    laser_updated_at = None
    if strokes is not None:
        if not isinstance(strokes, list):
            return jsonify({"ok": False, "error": "strokes must be a list"}), 400
        updated_at = _cm_save_slide_ink(db, session_id, slide_index, strokes)
    if laser is not None:
        if not isinstance(laser, dict):
            return jsonify({"ok": False, "error": "laser must be an object"}), 400
        active = bool(laser.get("active"))
        x = laser.get("x")
        y = laser.get("y")
        if active and x is not None and y is not None:
            try:
                x = float(x)
                y = float(y)
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "invalid laser coordinates"}), 400
        else:
            x = y = None
            active = False
        trail = laser.get("trail")
        if trail is not None and not isinstance(trail, list):
            return jsonify({"ok": False, "error": "laser.trail must be a list"}), 400
        laser_updated_at = _cm_save_laser(db, session_id, slide_index, active, x, y, trail)
    if not _safe_db_commit(db):
        return jsonify({"ok": False, "error": "server busy, please try again"}), 503
    return jsonify(
        {
            "ok": True,
            "session_id": session_id,
            "slide_index": slide_index,
            "updated_at": updated_at,
            "laser_updated_at": laser_updated_at,
        }
    )


@app.route("/practice/materials/api/classroom/<slug>/response", methods=["POST"])
def practice_course_material_classroom_response_api(slug: str):
    if not require_login():
        return jsonify({"ok": False, "error": "login required"}), 401
    material = _course_material_by_slug(slug)
    if not material:
        return jsonify({"ok": False, "error": "lesson not found"}), 404
    db = get_db()
    active = _cm_active_class_session(db, slug)
    if not active:
        return jsonify({"ok": False, "error": "no active classroom session"}), 409
    data = request.get_json(silent=True) or {}
    try:
        slide_index = int(data.get("slide_index"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "slide_index required"}), 400
    selected = str(data.get("selected_answer") or "").strip()[:120]
    correct = str(data.get("correct_answer") or "").strip()[:120]
    if not selected:
        return jsonify({"ok": False, "error": "selected_answer required"}), 400
    question_title = str(data.get("question_title") or "")[:240]
    if isinstance(data.get("is_correct"), bool):
        is_correct = 1 if data.get("is_correct") else 0
    else:
        is_correct = 1 if correct and selected.upper() == correct.upper() else 0
    uid = int(session["user_id"])
    roster = _cm_session_roster(db, int(active["id"]))
    if uid not in roster:
        grants = current_user_access_grants()
        if grants is not None and "sat" not in grants:
            return jsonify({"ok": False, "error": "student is not in this classroom roster"}), 403
        username = str(session.get("username") or f"student-{uid}")[:120]
        db.execute(
            """
            INSERT OR IGNORE INTO course_class_roster (session_id, user_id, username, created_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (int(active["id"]), uid, username),
        )
    username = str(session.get("username") or f"student-{uid}")[:120]
    try:
        db.execute(
            """
            INSERT INTO course_class_responses (
                session_id, lesson_slug, slide_index, question_title, user_id, username,
                selected_answer, correct_answer, is_correct, submitted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(session_id, slide_index, user_id) DO UPDATE SET
                question_title = excluded.question_title,
                username = excluded.username,
                selected_answer = excluded.selected_answer,
                correct_answer = excluded.correct_answer,
                is_correct = excluded.is_correct,
                submitted_at = datetime('now')
            """,
            (
                int(active["id"]),
                slug,
                slide_index,
                question_title,
                uid,
                username,
                selected,
                correct,
                is_correct,
            ),
        )
        if not _safe_db_commit(db):
            return jsonify({"ok": False, "error": "server busy, please try again"}), 503
    except Exception:
        app.logger.exception("classroom response save failed slug=%s slide=%s", slug, slide_index)
        return jsonify({"ok": False, "error": "could not save response"}), 500
    return jsonify({"ok": True, "session_id": int(active["id"]), "is_correct": bool(is_correct)})


@app.route("/practice/materials/api/classroom/<slug>/start", methods=["POST"])
def practice_course_material_classroom_start_api(slug: str):
    staff_redirect = _require_staff_response()
    if staff_redirect:
        return jsonify({"ok": False, "error": "staff required"}), 403
    material = _course_material_by_slug(slug)
    if not material:
        return jsonify({"ok": False, "error": "lesson not found"}), 404
    db = get_db()
    data = request.get_json(silent=True) or {}
    requested_ids = data.get("student_ids")
    available_students = _cm_available_classroom_students(db)
    available_by_id = {int(item["id"]): item for item in available_students}
    selected_ids: list[int] = []
    if isinstance(requested_ids, list):
        for raw_id in requested_ids:
            try:
                student_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if student_id in available_by_id and student_id not in selected_ids:
                selected_ids.append(student_id)
        if not selected_ids:
            return jsonify({"ok": False, "error": "choose at least one student"}), 400
    if not selected_ids:
        selected_ids = [int(item["id"]) for item in available_students]
    db.execute(
        "UPDATE course_class_sessions SET is_active = 0, ended_at = datetime('now') WHERE lesson_slug = ? AND is_active = 1",
        (slug,),
    )
    title = f"{material.get('section')} {material.get('title')} live class"
    cur = db.execute(
        """
        INSERT INTO course_class_sessions (
            lesson_slug, title, created_by, is_active, current_slide_index, slide_updated_at, created_at
        )
        VALUES (?, ?, ?, 1, 1, datetime('now'), datetime('now'))
        """,
        (slug, title, int(session["user_id"])),
    )
    session_id = int(cur.lastrowid)
    db.executemany(
        """
        INSERT OR IGNORE INTO course_class_roster (session_id, user_id, username, created_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        [
            (session_id, student_id, available_by_id[student_id]["username"])
            for student_id in selected_ids
        ],
    )
    db.commit()
    return jsonify({"ok": True, "session_id": session_id, "roster_count": len(selected_ids)})


@app.route("/practice/materials/api/classroom/<slug>/slide", methods=["POST"])
def practice_course_material_classroom_slide_api(slug: str):
    staff_redirect = _require_staff_response()
    if staff_redirect:
        return jsonify({"ok": False, "error": "staff required"}), 403
    material = _course_material_by_slug(slug)
    if not material:
        return jsonify({"ok": False, "error": "lesson not found"}), 404
    data = request.get_json(silent=True) or {}
    try:
        slide_index = int(data.get("slide_index"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "slide_index required"}), 400
    slide_count = int(material.get("slide_count") or 0)
    if slide_index < 1 or (slide_count and slide_index > slide_count):
        return jsonify({"ok": False, "error": "invalid slide_index"}), 400
    db = get_db()
    active = _cm_active_class_session(db, slug)
    if not active:
        return jsonify({"ok": False, "error": "no active classroom session"}), 409
    db.execute(
        """
        UPDATE course_class_sessions
        SET current_slide_index = ?, slide_updated_at = datetime('now')
        WHERE id = ? AND lesson_slug = ? AND is_active = 1
        """,
        (slide_index, int(active["id"]), slug),
    )
    if not _safe_db_commit(db):
        return jsonify({"ok": False, "error": "server busy, please try again"}), 503
    updated = db.execute(
        "SELECT slide_updated_at FROM course_class_sessions WHERE id = ?",
        (int(active["id"]),),
    ).fetchone()
    slide_updated_at = updated["slide_updated_at"] if updated else None
    return jsonify({
        "ok": True,
        "session_id": int(active["id"]),
        "current_slide_index": slide_index,
        "slide_updated_at": slide_updated_at,
    })


@app.route("/practice/materials/api/classroom/<slug>/end", methods=["POST"])
def practice_course_material_classroom_end_api(slug: str):
    staff_redirect = _require_staff_response()
    if staff_redirect:
        return jsonify({"ok": False, "error": "staff required"}), 403
    db = get_db()
    db.execute(
        "UPDATE course_class_sessions SET is_active = 0, ended_at = datetime('now') WHERE lesson_slug = ? AND is_active = 1",
        (slug,),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/practice/materials/api/classroom/<slug>/summary")
def practice_course_material_classroom_summary_api(slug: str):
    staff_redirect = _require_staff_response()
    if staff_redirect:
        return jsonify({"ok": False, "error": "staff required"}), 403
    material = _course_material_by_slug(slug)
    if not material:
        return jsonify({"ok": False, "error": "lesson not found"}), 404
    db = get_db()
    session_id = request.args.get("session_id", type=int)
    if not session_id:
        active = _cm_active_class_session(db, slug)
        if active:
            session_id = int(active["id"])
        else:
            row = db.execute(
                "SELECT id FROM course_class_sessions WHERE lesson_slug = ? ORDER BY id DESC LIMIT 1",
                (slug,),
            ).fetchone()
            session_id = int(row["id"]) if row else 0
    if not session_id:
        return jsonify({"ok": True, "session": None, "student_count": 0, "questions": []})
    summary = _cm_classroom_summary(db, material, session_id)
    status = 200 if summary.get("ok") else 404
    return jsonify(summary), status


@app.route("/practice/materials/api/coach", methods=["POST"])
def practice_course_material_coach_api():
    if not require_login():
        return jsonify({"ok": False, "error": "login required"}), 401
    if not OPENAI_API_KEY:
        return jsonify({"ok": False, "error": "AI coach is not configured on this server."}), 503
    data = request.get_json(silent=True) or {}
    slug = str(data.get("slug") or "").strip()
    slide_index = data.get("slide_index")
    question = str(data.get("question") or "").strip()
    mode = str(data.get("mode") or "explain").strip().lower()
    if not slug or slide_index is None or not question:
        return jsonify({"ok": False, "error": "slug, slide_index, and question are required"}), 400
    if len(question) > 1200:
        return jsonify({"ok": False, "error": "question too long"}), 400
    if mode not in {"explain", "hint", "why", "ask"}:
        mode = "ask"
    material = _course_material_by_slug(slug)
    if not material:
        return jsonify({"ok": False, "error": "lesson not found"}), 404
    slide = next(
        (s for s in material.get("slides") or [] if int(s.get("index") or 0) == int(slide_index)),
        None,
    )
    if not slide:
        return jsonify({"ok": False, "error": "slide not found"}), 404
    slide_plain = strip_html(str(slide.get("html") or ""))
    user_msg = build_coach_user_message(
        lesson_section=str(material.get("section") or ""),
        lesson_title=str(material.get("title") or ""),
        slide_title=str(slide.get("title") or ""),
        slide_section=str(slide.get("section") or ""),
        slide_kind=str(slide.get("kind") or "lesson"),
        study_tip=str(slide.get("study_tip") or ""),
        strategy_hint=str(slide.get("strategy_hint") or ""),
        slide_plain=slide_plain,
        student_question=question,
        mode=mode,
    )
    try:
        reply = openai_chat_completion(
            build_coach_system_prompt(),
            user_msg,
            api_key=OPENAI_API_KEY,
        )
    except RuntimeError as exc:
        app.logger.warning("AI coach error: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 502
    return jsonify({"ok": True, "reply": reply})


def _course_material_pdf_path(slug: str) -> str | None:
    manifest = _course_material_manifest_row(slug)
    if not manifest:
        return None
    return _resolve_first_existing_path(list(manifest.get("pdf_candidates") or []))


def get_questions_for_topic(domain: str, topic: str, file_path: str) -> List[dict]:
    try:
        compiled = load_compiled_bank()
        topic_questions = compiled.get(domain, {}).get(topic)
        if isinstance(topic_questions, list) and topic_questions:
            if domain == "placement":
                return apply_placement_calculator_flags([dict(q) for q in topic_questions], topic)
            return _finalize_questions(domain, topic, topic_questions)

        full_path = os.path.join(APP_DIR, file_path)
        if not os.path.isfile(full_path):
            return []
        if domain == "placement":
            if topic == "enhanced_math_1":
                qs = parse_enhanced_math_placement_tex_file(full_path, profile="math_1")
            elif topic == "enhanced_math_2":
                qs = parse_enhanced_math_placement_tex_file(full_path, profile="math_2")
            elif topic == "middle_level":
                qs = parse_middle_level_placement_tex_file(full_path, topic=topic)
            else:
                qs = parse_placement_tex_file(full_path)
        else:
            qs = parse_tex_file(full_path)
        if domain == "placement":
            return apply_placement_calculator_flags(qs, topic)
        return _finalize_questions(domain, topic, qs)
    except Exception as exc:
        app.logger.warning("Question load failed for %s/%s: %s", domain, topic, exc)
        return []


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
        "hard_15": "banks/hard/hard_15.tex",
        "hard_16": "banks/hard/hard_16.tex",
        "hard_20": "banks/hard/hard_20.tex",
        "hard_21": "banks/hard/hard_21.tex",
    },
    # Course placement (Algebra I/II vs Precalculus vs Calc AB) — see /placement and data/placement_meta.json
    "placement": {
        "placement_full": "Placement_Test.tex",
        "enhanced_math_1": "Placement_Enhanced_Math_1.tex",
        "enhanced_math_2": "Placement_Enhanced_Math_2.tex",
        "middle_level": "Placement_Middle_Level.tex",
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
    "hard_15": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_15.pdf",
            "label": "Student worksheet PDF",
            "description": "Printable worksheet — Hard Practice XV.",
            "download_name": "NovelPrep-SAT-Hard-Practice-15-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_15_PPT.pdf",
            "label": "Teaching slides",
            "description": "Slide deck with worked solutions for classroom review.",
            "download_name": "NovelPrep-SAT-Hard-Practice-15-Slides.pdf",
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
    "hard_20": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_20.pdf",
            "label": "Student worksheet PDF",
            "description": "Word Problem Training — printable student worksheet.",
            "download_name": "NovelPrep-Word-Problem-Training-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_20_PPT.pdf",
            "label": "Teaching slides",
            "description": "Word Problem Training — classroom slide deck.",
            "download_name": "NovelPrep-Word-Problem-Training-Slides.pdf",
            "mimetype": "application/pdf",
        },
    },
    "hard_21": {
        "paper_pdf": {
            "path": "SAT_Hard_Question_Part_21.pdf",
            "label": "Student worksheet PDF",
            "description": "Test 1 — full Module 2-style mock set for classroom practice.",
            "download_name": "NovelPrep-Test-1-Worksheet.pdf",
            "mimetype": "application/pdf",
        },
        "slides_pdf": {
            "path": "SAT_Hard_Question_Part_21_PPT.pdf",
            "label": "Teaching slides",
            "description": "Test 1 — classroom slide deck with answers.",
            "download_name": "NovelPrep-Test-1-Slides.pdf",
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
    {"code": "1", "range": "1–16", "label": "Gate 1 — Algebra I readiness"},
    {"code": "2", "range": "17–37", "label": "Gate 2 — Geometry readiness"},
    {"code": "3", "range": "38–53", "label": "Gate 3 — Algebra II readiness"},
    {"code": "4", "range": "54–69", "label": "Gate 4 — Precalculus readiness"},
    {"code": "5", "range": "70–85", "label": "Gate 5 — Calculus readiness"},
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
    "exam_word_problems": "Exam · Word",
    "exam_unit_bank": "Exam · Unit bank",
    "exam_random_test": "Exam · Random Test",
}

EXAM_DOMAIN_BY_SLUG: Dict[str, str] = {
    "word-problems": "exam_word_problems",
    "unit-bank": "exam_unit_bank",
    "random-test": "exam_random_test",
}
EXAM_DB_ATTEMPT_IDS_KEY = "exam_db_attempt_ids"

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


def _current_user_can_view_attempt(db: sqlite3.Connection, attempt_id: int) -> bool:
    if current_user_can_access_admin():
        return True
    return _attempt_user_matches(db, attempt_id, session.get("user_id"))


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


def _clear_placement_session_attempt(topic: str) -> None:
    """Drop in-progress placement attempt binding so the next run creates a new row."""
    session.pop(_practice_session_key("placement", topic), None)
    _clear_placement_section_flags(topic)


def _clear_placement_full_session_attempt() -> None:
    _clear_placement_session_attempt("placement_full")


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
    "hard_15": "SAT Hard Question Set 15 (Practice XV)",
    "hard_16": "SAT Hard Question Set 16 (Practice XVI)",
    "hard_20": "Word Problem Training",
    "hard_21": "Test 1",
    "psd_all": "Unit 3 – Problem Solving & Data (full bank)",
    "placement_full": "Upper school placement (Five-Gate Hybrid, Algebra–Calculus)",
    "enhanced_math_1": "Enhanced Math 1 / Math I placement",
    "enhanced_math_2": "Enhanced Math 2 / Math II placement",
    "middle_level": "Middle level math placement",
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
    "hard_15": [
        {"correct_answer": "D"},
        {"correct_answer": "C"},
        {"correct_answer": "B"},
        {"correct_answer": "C"},
        {"correct_answer": "B"},
        {
            "correct_answer": r"\sqrt{3}/2",
            "answer_alternates": [
                "√3/2",
                "sqrt(3)/2",
                "(\\sqrt{3})/2",
                "0.866",
                "0.8660",
                "0.87",
            ],
        },
        {"correct_answer": "C"},
        {"correct_answer": "1/2", "answer_alternates": ["0.5", ".5"]},
        {"correct_answer": "6"},
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
    "hard_20": [
        {"correct_answer": "C"},
        {"correct_answer": "B"},
        {"correct_answer": "1360"},
        {"correct_answer": "A"},
        {"correct_answer": "12"},
        {"correct_answer": "15435", "answer_alternates": ["15,435", "15435.0"]},
        {"correct_answer": "D"},
        {"correct_answer": "B"},
        {"correct_answer": "2"},
        {"correct_answer": "A"},
        {"correct_answer": "B"},
        {"correct_answer": "D"},
        {"correct_answer": "93"},
        {"correct_answer": "C"},
        {"correct_answer": "D"},
        {"correct_answer": "D"},
        {"correct_answer": "B"},
        {"correct_answer": "B"},
        {"correct_answer": "C"},
    ],
    "hard_21": [
        {"correct_answer": "B"},
        {"correct_answer": "31.8"},
        {"correct_answer": "B"},
        {"correct_answer": "A"},
        {"correct_answer": "B"},
        {"correct_answer": "403"},
        {"correct_answer": "D"},
        {"correct_answer": "-23"},
        {"correct_answer": "A"},
        {"correct_answer": "B"},
        {"correct_answer": "C"},
        {"correct_answer": "C"},
        {"correct_answer": "C"},
        {"correct_answer": "D"},
        {"correct_answer": "31"},
        {"correct_answer": "D"},
        {"correct_answer": "144"},
        {"correct_answer": "105"},
        {"correct_answer": "C"},
        {"correct_answer": "19.6"},
        {"correct_answer": "A"},
        {"correct_answer": "D"},
        {"correct_answer": "B"},
        {"correct_answer": "A"},
        {"correct_answer": "-13"},
        {"correct_answer": "C"},
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
        "description": "Placement catalog: Math 5–7, Enhanced Math, and Algebra–Precalculus tracks—printable + in-app reports.",
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


def _attempt_graded_count(db: sqlite3.Connection, attempt_id: int) -> int:
    row = db.execute(
        """
        SELECT COUNT(*) AS c FROM practice_responses
        WHERE attempt_id = ? AND is_correct IN (0, 1)
        """,
        (attempt_id,),
    ).fetchone()
    return int(row["c"] or 0) if row else 0


def _attempt_is_tracked(db: sqlite3.Connection, attempt_id: int, domain: str | None = None) -> bool:
    if domain == "placement":
        return True
    return _attempt_graded_count(db, attempt_id) >= MIN_TRACKED_SAT_RESPONSES


def _sync_attempt_mistake_progress(
    db: sqlite3.Connection, learner_key: str, attempt_id: int
) -> None:
    """Backfill mistake ladder for all graded responses once a session unlocks."""
    rows = db.execute(
        """
        SELECT pa.domain, pa.topic, pr.question_index, pr.is_correct
        FROM practice_responses pr
        JOIN practice_attempts pa ON pa.id = pr.attempt_id
        WHERE pr.attempt_id = ? AND pr.is_correct IN (0, 1) AND pr.question_index IS NOT NULL
        ORDER BY pr.id
        """,
        (attempt_id,),
    ).fetchall()
    for row in rows:
        domain = str(row["domain"] or "")
        topic = str(row["topic"] or "")
        q_index = int(row["question_index"])
        if int(row["is_correct"] or 0) == 1:
            _mistake_progress_on_correct(db, learner_key, domain, topic, q_index)
        else:
            _mistake_progress_on_wrong(db, learner_key, domain, topic, q_index)


def _apply_practice_mistake_progress(
    db: sqlite3.Connection,
    learner_key: str,
    attempt_id: int,
    domain: str,
    topic: str,
    q_index: int,
    is_correct: int | None,
    *,
    mistake_redo: bool,
    graded_before: int | None = None,
) -> None:
    if domain == "placement" or mistake_redo:
        if is_correct == 1:
            _mistake_progress_on_correct(db, learner_key, domain, topic, q_index)
        elif is_correct == 0:
            _mistake_progress_on_wrong(db, learner_key, domain, topic, q_index)
        return
    before = int(graded_before if graded_before is not None else _attempt_graded_count(db, attempt_id))
    after = _attempt_graded_count(db, attempt_id)
    was_tracked = before >= MIN_TRACKED_SAT_RESPONSES
    is_tracked = after >= MIN_TRACKED_SAT_RESPONSES
    if not was_tracked and is_tracked:
        _sync_attempt_mistake_progress(db, learner_key, attempt_id)
    elif is_tracked:
        if is_correct == 1:
            _mistake_progress_on_correct(db, learner_key, domain, topic, q_index)
        elif is_correct == 0:
            _mistake_progress_on_wrong(db, learner_key, domain, topic, q_index)


def _resume_incomplete_attempt_id(
    db: sqlite3.Connection,
    user_id: Any,
    domain: str,
    topic: str,
    bank_total: int,
) -> int | None:
    """Reuse a recent in-progress bank attempt instead of spawning another row."""
    if user_id is None or bank_total <= 0 or domain in ("placement",) or domain.startswith("exam_"):
        return None
    row = db.execute(
        """
        SELECT pa.id
        FROM practice_attempts pa
        JOIN practice_responses pr ON pr.attempt_id = pa.id
        WHERE pa.user_id = ? AND pa.domain = ? AND pa.topic = ?
          AND pa.created_at >= datetime('now', '-24 hours')
        GROUP BY pa.id
        HAVING COUNT(DISTINCT pr.question_index) < ?
        ORDER BY pa.id DESC
        LIMIT 1
        """,
        (user_id, domain, topic, bank_total),
    ).fetchone()
    return int(row["id"]) if row else None


def _tracked_attempt_sql(alias: str = "pa") -> str:
    """Only count deliberate SAT sessions; placement diagnostics are always tracked."""
    return (
        f"({alias}.domain = 'placement' OR "
        f"({alias}.domain NOT LIKE 'exam_%' AND "
        f"(SELECT COUNT(*) FROM practice_responses pr_track "
        f"WHERE pr_track.attempt_id = {alias}.id "
        f"AND pr_track.is_correct IN (0, 1)) >= {MIN_TRACKED_SAT_RESPONSES}))"
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
    if current_user_can_access_admin():
        return jsonify(ok=ok, **status), (200 if ok else 503)
    return jsonify(ok=ok, persistence_ok=status["persistence_ok"]), (200 if ok else 503)


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
    if not path:
        tmp = tempfile.NamedTemporaryFile(prefix="sat-live-", suffix=".db", delete=False)
        tmp.close()
        path = tmp.name
        _sqlite_backup_file(DB_PATH, path)
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
        tracks=_visible_learning_tracks(grants),
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


@app.route("/admin/export/weekly-digest.csv")
def admin_export_weekly_digest_csv():
    gate = _require_admin_response()
    if gate is not None:
        return gate

    import csv
    import io

    db = get_db()
    try:
        digest_days = int(request.args.get("days") or 7)
    except ValueError:
        digest_days = 7
    if digest_days not in (7, 14, 30):
        digest_days = 7
    hide_demo = request.args.get("hide_demo", "1") not in ("0", "false", "no")
    cohort_id: int | None = None
    raw_cohort = (request.args.get("cohort_id") or "").strip()
    if raw_cohort:
        try:
            cohort_id = int(raw_cohort)
        except ValueError:
            cohort_id = None
    digest = _admin_weekly_digest(db, digest_days, hide_demo=hide_demo, cohort_id=cohort_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "username",
            "status",
            "last_activity",
            "practice_sessions",
            "exam_sessions",
            "graded_responses",
            "latest_exam",
            "wrong_count",
            "accuracy_pct",
            "accuracy_basis",
            "weak_chapter",
            "weak_chapter_pct",
            "weak_unit",
            "weak_unit_pct",
            "mock_first_score",
            "mock_latest_score",
            "mock_trend",
            "mastery_pct",
            "quality_hint",
            "last_login_at",
        ]
    )
    for row in digest["students"]:
        writer.writerow(
            [
                row["username"],
                row["status"],
                row["last_activity"] or "",
                row["practice_sessions"],
                row["exam_sessions"],
                row.get("graded_count") or 0,
                row.get("latest_exam_label") or "",
                row["wrong_count"],
                row.get("accuracy_pct") if row.get("accuracy_pct") is not None else "",
                row.get("accuracy_basis") if row.get("accuracy_basis") is not None else "",
                row.get("weak_chapter") or "",
                row.get("weak_chapter_pct") if row.get("weak_chapter_pct") is not None else "",
                row.get("weak_unit") or "",
                row.get("weak_unit_pct") if row.get("weak_unit_pct") is not None else "",
                row.get("mock_first_score") if row.get("mock_first_score") is not None else "",
                row.get("mock_latest_score") if row.get("mock_latest_score") is not None else "",
                row.get("mock_trend_label") or "",
                row.get("mastery_pct") if row.get("mastery_pct") is not None else "",
                row.get("quality_hint") or "",
                row.get("last_login_at") or "",
            ]
        )
    filename = f"novel-prep-learning-pulse-{digest_days}d-{date.today().isoformat()}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/admin/learning-pulse/panel")
def admin_learning_pulse_panel():
    gate = _require_admin_response()
    if gate is not None:
        return gate

    db = get_db()
    digest_days, hide_demo, cohort_id, _student_id = _parse_learning_pulse_args()
    return render_template(
        "admin_learning_pulse_panel.html",
        **_learning_pulse_panel_context(
            db,
            digest_days=digest_days,
            hide_demo=hide_demo,
            cohort_id=cohort_id,
        ),
    )


@app.route("/admin/learning-pulse/print")
def admin_learning_pulse_print():
    gate = _require_admin_response()
    if gate is not None:
        return gate

    db = get_db()
    digest_days, hide_demo, cohort_id, _student_id = _parse_learning_pulse_args()
    return render_template(
        "admin_digest_print.html",
        weekly_digest=_admin_weekly_digest(
            db, digest_days, hide_demo=hide_demo, cohort_id=cohort_id
        ),
        digest_days=digest_days,
        hide_demo=hide_demo,
    )


@app.route("/learn/<track_key>")
def learning_track(track_key: str):
    track = next((t for t in LEARNING_TRACKS if t["key"] == track_key), None)
    if track is None:
        return "Unknown learning track", 404
    grants = current_user_access_grants()
    if grants is not None:
        if track_key == "sat" and "sat" not in grants:
            abort(404)
        if track_key == "placement" and "placement" not in grants:
            abort(404)
        if track_key not in ("sat", "placement"):
            return redirect(_student_home_url(grants))
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


def _learner_key_for_user(user_id: int | None) -> str:
    if user_id is not None:
        return f"u:{int(user_id)}"
    return _learner_key()


def _persist_miss_quiz_run(
    db: sqlite3.Connection,
    user_id: Any,
    *,
    label: str,
    scope_part_id: str | None,
    total: int,
    correct_n: int,
    pct: int,
    passed: bool,
) -> None:
    if not user_id:
        return
    db.execute(
        """
        INSERT INTO miss_quiz_runs
        (user_id, label, scope_part_id, item_count, correct_count, pct, passed)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id),
            str(label or "Miss quiz")[:220],
            str(scope_part_id)[:40] if scope_part_id else None,
            int(total),
            int(correct_n),
            int(pct),
            1 if passed else 0,
        ),
    )
    _safe_db_commit(db)


def _student_chapter_progress_rows(db: sqlite3.Connection, user_id: int | None) -> list[dict[str, Any]]:
    compiled = load_compiled_bank()
    rows: list[dict[str, Any]] = []
    unit_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for domain, topic, section, unit_label in STUDENT_CHAPTER_SLICES:
        cap = len(compiled.get(domain, {}).get(topic) or [])
        if cap <= 0:
            tex = BANKS.get(domain, {}).get(topic)
            if tex:
                cap = len(get_questions_for_topic(domain, topic, tex))
        engaged = _practice_distinct_answered(db, user_id, domain, topic) if cap else 0
        pct = min(100, round(100 * engaged / cap)) if cap else 0
        row = {
            "domain": domain,
            "topic": topic,
            "section": section,
            "unit_label": unit_label,
            "title": TOPIC_TITLES.get(topic, topic),
            "cap": cap,
            "engaged": engaged,
            "pct": pct,
            "href": url_for("practice_question", domain=domain, topic=topic, qnum=0) if cap else None,
            "is_pt": section == "PT",
        }
        rows.append(row)
        unit_groups[unit_label].append(row)
    unit_summaries: list[dict[str, Any]] = []
    for unit_label in ("Unit 1", "Unit 2", "Unit 3", "Unit 4"):
        group = unit_groups.get(unit_label) or []
        chapter_rows = [r for r in group if not r["is_pt"]]
        caps = sum(int(r["cap"] or 0) for r in chapter_rows)
        touched = sum(int(r["engaged"] or 0) for r in chapter_rows)
        unit_summaries.append(
            {
                "label": unit_label,
                "pct": min(100, round(100 * touched / caps)) if caps else 0,
                "touched": touched,
                "cap": caps,
            }
        )
    return rows, unit_summaries


def _student_mock_score_history(db: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT id, exam_meta_json, created_at
        FROM practice_attempts
        WHERE user_id = ? AND domain = 'exam_random_test' AND exam_meta_json IS NOT NULL
        ORDER BY id ASC
        """,
        (user_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            meta = json.loads(row["exam_meta_json"] or "{}")
            score = int(meta.get("score") or 0)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if score <= 0:
            continue
        out.append(
            {
                "attempt_id": int(row["id"]),
                "score": score,
                "when_label": _session_when_label(row["created_at"]),
                "created_at": row["created_at"],
                "summary_href": url_for("practice_session_summary", attempt_id=int(row["id"])),
                "bar_pct": max(8, round(100 * score / 800)),
            }
        )
    if out:
        first = out[0]["score"]
        last = out[-1]["score"]
        delta = last - first
        trend_label = f"{delta:+d} since first mock" if len(out) >= 2 else "First mock on record"
    else:
        trend_label = "No Random Test saved yet"
        delta = 0
    return {
        "scores": out,
        "latest": out[-1] if out else None,
        "best": max(out, key=lambda x: x["score"]) if out else None,
        "trend_label": trend_label,
        "trend_delta": delta if out else None,
        "chart_max": 800,
    }


def _student_weak_units(db: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT
            pa.domain,
            SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct,
            SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded
        FROM practice_attempts pa
        JOIN practice_responses pr ON pr.attempt_id = pa.id
        WHERE pa.user_id = ?
          AND pa.domain IN ('algebra', 'advanced_math', 'problem_solving', 'geometry', 'hard_problem')
        GROUP BY pa.domain
        HAVING graded >= 3
        """,
        (user_id,),
    ).fetchall()
    units: list[dict[str, Any]] = []
    for row in rows:
        graded = int(row["graded"] or 0)
        if graded <= 0:
            continue
        pct = round(100 * int(row["correct"] or 0) / graded)
        domain = str(row["domain"] or "")
        units.append(
            {
                "label": _dashboard_track_short(domain),
                "pct": pct,
                "href": url_for("practice_analytics", part=MISS_PART_BY_DOMAIN.get(domain, "sat")),
            }
        )
    units.sort(key=lambda x: (x["pct"], x["label"]))
    return units[:4]


def _student_mistake_mastery(db: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    lk = _learner_key_for_user(user_id)
    status_rows = db.execute(
        """
        SELECT status, COUNT(*) AS c
        FROM mistake_learning_progress
        WHERE learner_key = ?
        GROUP BY status
        """,
        (lk,),
    ).fetchall()
    counts = {str(r["status"] or ""): int(r["c"] or 0) for r in status_rows}
    total = sum(counts.values())
    mastered = counts.get("mastered", 0)
    in_progress = counts.get("reviewed", 0) + counts.get("redo_correct", 0)
    open_misses = counts.get("unreviewed", 0)
    digest_pct = round(100 * mastered / total) if total else None
    return {
        "total": total,
        "mastered": mastered,
        "in_progress": in_progress,
        "open_misses": open_misses,
        "digest_pct": digest_pct,
        "analytics_href": url_for("practice_analytics", part="sat"),
    }


def _student_miss_quiz_stats(db: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    rows = db.execute(
        """
        SELECT id, label, scope_part_id, item_count, correct_count, pct, passed, created_at
        FROM miss_quiz_runs
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 20
        """,
        (user_id,),
    ).fetchall()
    recent: list[dict[str, Any]] = []
    passed_n = 0
    for row in rows:
        passed = int(row["passed"] or 0) == 1
        if passed:
            passed_n += 1
        recent.append(
            {
                "label": str(row["label"] or "Miss quiz"),
                "pct": int(row["pct"] or 0),
                "passed": passed,
                "item_count": int(row["item_count"] or 0),
                "when_label": _session_when_label(row["created_at"]),
            }
        )
    total_runs = len(rows)
    pass_rate = round(100 * passed_n / total_runs) if total_runs else None
    return {
        "total_runs": total_runs,
        "passed_runs": passed_n,
        "pass_rate": pass_rate,
        "pass_threshold": MISS_QUIZ_PASS_PERCENT,
        "recent": recent[:8],
    }


def _student_weak_chapters(
    db: sqlite3.Connection, user_id: int, *, limit: int = 4
) -> list[dict[str, Any]]:
    chapter_topics = [(d, t, sec) for d, t, sec, _ in STUDENT_CHAPTER_SLICES]
    if not chapter_topics:
        return []
    chapter_ph = " OR ".join("(pa.domain = ? AND pa.topic = ?)" for _ in chapter_topics)
    params: list[Any] = [user_id]
    for domain, topic, _sec in chapter_topics:
        params.extend([domain, topic])
    rows = db.execute(
        f"""
        SELECT
            pa.domain,
            pa.topic,
            SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct,
            SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded
        FROM practice_attempts pa
        JOIN practice_responses pr ON pr.attempt_id = pa.id
        WHERE pa.user_id = ?
          AND ({chapter_ph})
        GROUP BY pa.domain, pa.topic
        HAVING graded >= 3
        """,
        params,
    ).fetchall()
    chapters: list[dict[str, Any]] = []
    for row in rows:
        graded = int(row["graded"] or 0)
        if graded <= 0:
            continue
        domain = str(row["domain"] or "")
        topic = str(row["topic"] or "")
        pct = round(100 * int(row["correct"] or 0) / graded)
        section = next(
            (sec for dom, top, sec, _ in STUDENT_CHAPTER_SLICES if dom == domain and top == topic),
            topic,
        )
        chapters.append(
            {
                "section": section,
                "label": _digest_chapter_slice_label(domain, topic),
                "pct": pct,
                "graded": graded,
                "href": url_for("practice_question", domain=domain, topic=topic, qnum=0),
            }
        )
    chapters.sort(key=lambda x: (x["pct"], x["section"]))
    return chapters[:limit]


def _student_period_activity(
    db: sqlite3.Connection, user_id: int, *, days: int = 30
) -> dict[str, Any]:
    window_sql = f"-{int(days)} days"
    row = db.execute(
        f"""
        SELECT
            MAX(COALESCE(pr.submitted_at, pa.created_at)) AS last_activity,
            COUNT(DISTINCT CASE
                WHEN pa.domain NOT LIKE 'exam_%' AND pa.domain != 'placement' THEN pa.id
            END) AS practice_sessions,
            COUNT(DISTINCT CASE WHEN pa.domain LIKE 'exam_%' THEN pa.id END) AS exam_sessions,
            SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded,
            SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct,
            SUM(CASE WHEN pr.is_correct = 0 THEN 1 ELSE 0 END) AS wrong_count
        FROM practice_attempts pa
        LEFT JOIN practice_responses pr ON pr.attempt_id = pa.id
        WHERE pa.user_id = ?
          AND pa.created_at >= datetime('now', ?)
        """,
        (user_id, window_sql),
    ).fetchone()
    graded = int(row["graded"] or 0) if row else 0
    correct = int(row["correct"] or 0) if row else 0
    last_activity = row["last_activity"] if row else None
    return {
        "days": days,
        "last_activity": last_activity,
        "last_activity_label": _session_when_label(last_activity) or "No activity",
        "status": _activity_status_label(last_activity),
        "practice_sessions": int(row["practice_sessions"] or 0) if row else 0,
        "exam_sessions": int(row["exam_sessions"] or 0) if row else 0,
        "graded_responses": graded,
        "wrong_count": int(row["wrong_count"] or 0) if row else 0,
        "accuracy_pct": round(100 * correct / graded) if graded else None,
    }


def _student_report_brief(ctx: dict[str, Any]) -> dict[str, Any]:
    mock = ctx["mock_history"]
    mastery = ctx["mistake_mastery"]
    miss_quiz = ctx["miss_quiz"]
    weak_chapters = ctx.get("weak_chapters") or []
    weak_units = ctx.get("weak_units") or []
    chapter_pct = int(ctx.get("chapter_overall_pct") or 0)
    activity = ctx.get("period_activity") or {}
    username = ctx.get("username") or "Student"

    has_mock = bool(mock.get("scores"))
    has_practice = chapter_pct > 0 or int(activity.get("graded_responses") or 0) > 0
    open_misses = int(mastery.get("open_misses") or 0)

    if has_mock and (mock.get("trend_delta") or 0) > 0:
        status = "improving"
    elif has_mock or (has_practice and chapter_pct >= 25):
        status = "on_track"
    elif has_practice:
        status = "building"
    else:
        status = "starting"

    if has_mock and mock.get("latest"):
        latest_score = int(mock["latest"]["score"])
        headline = f"Latest mock {latest_score}/800"
        if mock.get("best") and int(mock["best"]["score"]) > latest_score:
            headline += f" · best {mock['best']['score']}"
        if mock.get("trend_delta") is not None and len(mock.get("scores") or []) >= 2:
            headline += f" · {mock['trend_label']}"
    elif has_practice:
        headline = f"{chapter_pct}% chapter coverage — take a mock to set your score baseline"
    else:
        headline = "Ready to begin — one lesson, one drill, one mock starts your report"

    if ctx.get("viewer") == "admin":
        act_label = activity.get("last_activity_label") or "No activity"
        headline = f"{username}: {headline} · last active {act_label}"

    glance = [
        {
            "key": "mock",
            "label": "Latest mock",
            "value": str(mock["latest"]["score"]) if mock.get("latest") else "—",
            "hint": mock.get("trend_label") if has_mock else "No mock yet",
        },
        {
            "key": "coverage",
            "label": "Chapter coverage",
            "value": f"{chapter_pct}%",
            "hint": "Distinct questions across 1.1–4.4",
        },
        {
            "key": "mastery",
            "label": "Misses mastered",
            "value": f"{mastery['digest_pct']}%" if mastery.get("digest_pct") is not None else "—",
            "hint": f"{mastery.get('open_misses', 0)} open misses" if open_misses else "Mistake ladder",
        },
        {
            "key": "miss_quiz",
            "label": "Miss quiz pass",
            "value": f"{miss_quiz['pass_rate']}%" if miss_quiz.get("pass_rate") is not None else "—",
            "hint": f"{miss_quiz.get('passed_runs', 0)}/{miss_quiz.get('total_runs', 0)} runs"
            if miss_quiz.get("total_runs")
            else "Not started",
        },
    ]

    focus_steps: list[dict[str, Any]] = []
    if not has_mock:
        focus_steps.append(
            {
                "kind": "mock",
                "title": "Take a Random Test",
                "detail": "Save your first mock score — this becomes the anchor for all future progress.",
                "href": ctx.get("random_test_href"),
            }
        )
    if weak_chapters:
        focus = weak_chapters[0]
        focus_steps.append(
            {
                "kind": "review",
                "title": f"Review {focus['section']}",
                "detail": f"Lowest chapter slice at {focus['pct']}% ({focus['label'].split(' · ', 1)[-1]}).",
                "href": focus.get("href"),
            }
        )
    elif weak_units:
        focus = weak_units[0]
        focus_steps.append(
            {
                "kind": "review",
                "title": f"Strengthen {focus['label']}",
                "detail": f"Domain accuracy {focus['pct']}% — drill this unit next.",
                "href": focus.get("href"),
            }
        )
    if open_misses >= 3:
        focus_steps.append(
            {
                "kind": "miss_quiz",
                "title": "Run a miss quiz",
                "detail": f"{open_misses} misses still open — clear them with a focused redo set.",
                "href": ctx.get("analytics_href"),
            }
        )
    elif not has_practice:
        focus_steps.append(
            {
                "kind": "start",
                "title": "Start Unit 1.1",
                "detail": "Open the course deck or bank drill and answer at least 3 questions to unlock tracking.",
                "href": ctx.get("practice_href"),
            }
        )
    if not focus_steps:
        focus_steps.append(
            {
                "kind": "maintain",
                "title": "Keep the weekly loop",
                "detail": "One lesson deck, one bank drill, one mock, then mistake redo.",
                "href": ctx.get("practice_href"),
            }
        )

    for idx, step in enumerate(focus_steps[:3], start=1):
        step["step"] = idx

    focus_line = None
    if weak_chapters:
        w = weak_chapters[0]
        focus_line = f"{w['label']} — {w['pct']}% accuracy"
    elif weak_units:
        w = weak_units[0]
        focus_line = f"{w['label']} — {w['pct']}% accuracy"

    return {
        "headline": headline,
        "status": status,
        "glance": glance,
        "focus_steps": focus_steps[:3],
        "focus_line": focus_line,
    }


def _student_report_context(
    db: sqlite3.Connection,
    user_id: int,
    *,
    viewer: str = "student",
    student: dict[str, Any] | None = None,
    period_days: int = 30,
) -> dict[str, Any]:
    chapter_rows, unit_summaries = _student_chapter_progress_rows(db, user_id)
    chapter_only = [r for r in chapter_rows if not r["is_pt"]]
    chapter_caps = sum(int(r["cap"] or 0) for r in chapter_only)
    chapter_touched = sum(min(int(r["engaged"] or 0), int(r["cap"] or 0)) for r in chapter_only)
    weak_chapters = _student_weak_chapters(db, user_id)
    period_activity = _student_period_activity(db, user_id, days=period_days)
    recent_sessions = _admin_attempt_rows(db, user_id)[:6]

    if student is None:
        row = db.execute(
            "SELECT id, username, is_active, created_at FROM users WHERE id = ? AND role = 'student'",
            (user_id,),
        ).fetchone()
        student = dict(row) if row else {"id": user_id, "username": f"User {user_id}"}

    ctx: dict[str, Any] = {
        "viewer": viewer,
        "student": student,
        "username": str(student.get("username") or ""),
        "user_id": user_id,
        "period_days": period_days,
        "period_activity": period_activity,
        "mock_history": _student_mock_score_history(db, user_id),
        "weak_units": _student_weak_units(db, user_id),
        "weak_chapters": weak_chapters,
        "chapter_rows": chapter_rows,
        "unit_summaries": unit_summaries,
        "chapter_overall_pct": min(100, round(100 * chapter_touched / chapter_caps))
        if chapter_caps
        else 0,
        "mistake_mastery": _student_mistake_mastery(db, user_id),
        "miss_quiz": _student_miss_quiz_stats(db, user_id),
        "recent_sessions": recent_sessions,
        "random_test_href": url_for("practice_random_test_intro"),
        "analytics_href": url_for("practice_analytics", part="sat"),
        "practice_href": url_for("practice"),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    if viewer == "admin":
        ctx["admin_href"] = url_for("admin_student_detail", user_id=user_id)
        ctx["print_href"] = url_for("admin_student_report_print", user_id=user_id)
        ctx["back_href"] = url_for("admin")
    else:
        ctx["back_href"] = url_for("practice")
    ctx["report_brief"] = _student_report_brief(ctx)
    return ctx


def _student_progress_context(db: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    ctx = _student_report_context(db, user_id, viewer="student")
    return {
        "mock_history": ctx["mock_history"],
        "weak_units": ctx["weak_units"],
        "chapter_rows": ctx["chapter_rows"],
        "unit_summaries": ctx["unit_summaries"],
        "chapter_overall_pct": ctx["chapter_overall_pct"],
        "mistake_mastery": ctx["mistake_mastery"],
        "miss_quiz": ctx["miss_quiz"],
        "random_test_href": ctx["random_test_href"],
        "analytics_href": ctx["analytics_href"],
        "report_brief": ctx["report_brief"],
        "weak_chapters": ctx["weak_chapters"],
        "period_activity": ctx["period_activity"],
        "viewer": "student",
        "back_href": ctx["back_href"],
        "generated_at": ctx["generated_at"],
    }


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
        domain_name = str(r["domain"])
        if domain_name in DOMAIN_SAT_UNIT:
            unit_label, unit_title = DOMAIN_SAT_UNIT[domain_name]
        elif domain_name == "hard_problem":
            unit_label = str(meta.get("knowledge_section") or "Hard")
            unit_title = str(meta.get("knowledge_section_title_en") or "Hard Problem Drill")
        else:
            unit_label, unit_title = "SAT", TOPIC_TITLES.get(r["topic"], r["topic"])
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
                "analytics_unit_label": unit_label,
                "analytics_unit_title": unit_title,
                "stem_html": meta.get("stem") or "",
                "choices": meta.get("choices") or [],
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

SAT_MISTAKE_UNIT_ORDER = ("U1", "U2", "U3", "U4")
SAT_MISTAKE_UNIT_META: Dict[str, Dict[str, Any]] = {
    "U1": {"label": "Unit 1", "title": "Algebra", "domain": "algebra", "quota": 8, "pct": 35},
    "U2": {"label": "Unit 2", "title": "Advanced Math", "domain": "advanced_math", "quota": 8, "pct": 35},
    "U3": {"label": "Unit 3", "title": "Problem Solving & Data", "domain": "problem_solving", "quota": 3, "pct": 15},
    "U4": {"label": "Unit 4", "title": "Geometry", "domain": "geometry", "quota": 3, "pct": 15},
}
SAT_MISTAKE_TEST_SIZE = 22
SAT_MISTAKE_TEST_SECONDS = 35 * 60

STUDENT_CHAPTER_SLICES: List[tuple[str, str, str, str]] = [
    ("algebra", "1_1", "1.1", "Unit 1"),
    ("algebra", "1_2", "1.2", "Unit 1"),
    ("algebra", "1_3", "1.3", "Unit 1"),
    ("algebra", "1_4", "1.4", "Unit 1"),
    ("algebra", "1_5", "1.5", "Unit 1"),
    ("algebra", "1_pt", "PT", "Unit 1"),
    ("advanced_math", "2_1", "2.1", "Unit 2"),
    ("advanced_math", "2_2", "2.2", "Unit 2"),
    ("advanced_math", "2_3", "2.3", "Unit 2"),
    ("advanced_math", "2_pt", "PT", "Unit 2"),
    ("problem_solving", "3_1", "3.1", "Unit 3"),
    ("problem_solving", "3_2", "3.2", "Unit 3"),
    ("problem_solving", "3_3", "3.3", "Unit 3"),
    ("problem_solving", "3_4", "3.4", "Unit 3"),
    ("problem_solving", "3_5", "3.5", "Unit 3"),
    ("problem_solving", "3_6", "3.6", "Unit 3"),
    ("problem_solving", "3_7", "3.7", "Unit 3"),
    ("problem_solving", "3_pt", "PT", "Unit 3"),
    ("geometry", "4_1", "4.1", "Unit 4"),
    ("geometry", "4_2", "4.2", "Unit 4"),
    ("geometry", "4_3", "4.3", "Unit 4"),
    ("geometry", "4_4", "4.4", "Unit 4"),
    ("geometry", "4_pt", "PT", "Unit 4"),
]


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


def _sat_mistake_unit_key(domain: str, qobj: dict) -> str | None:
    if domain == "algebra":
        return "U1"
    if domain == "advanced_math":
        return "U2"
    if domain == "problem_solving":
        return "U3"
    if domain == "geometry":
        return "U4"
    if domain == "hard_problem":
        raw = str(qobj.get("knowledge_section") or qobj.get("sat_unit_label") or "").strip()
        m = re.search(r"Unit\s*([1-4])", raw, re.I)
        if m:
            return f"U{m.group(1)}"
    return None


def _sat_mistake_topic_candidates() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for spec in SAT_MISS_MODULE_SPECS:
        domain = str(spec["domain"])
        for topic in spec["topics"]:
            if topic in (BANKS.get(domain) or {}):
                out.append((domain, str(topic)))
    for topic in sorted((BANKS.get("hard_problem") or {}).keys(), key=_topic_bank_sort_key):
        out.append(("hard_problem", str(topic)))
    return out


def _sat_active_mistake_pool(db: sqlite3.Connection, user_id: Any) -> list[dict[str, Any]]:
    learner = _learner_key()
    tracked_sql = _tracked_attempt_sql("pa")
    pool: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for domain, topic in _sat_mistake_topic_candidates():
        if topic not in (BANKS.get(domain) or {}):
            continue
        if user_id is not None:
            rows = db.execute(
                f"""
                SELECT pr.question_index AS qi,
                       COUNT(*) AS wrong_count,
                       MAX(pr.submitted_at) AS last_wrong_at
                FROM practice_responses pr
                JOIN practice_attempts pa ON pa.id = pr.attempt_id
                LEFT JOIN mistake_learning_progress mlp
                  ON mlp.learner_key = ?
                 AND mlp.domain = pa.domain
                 AND mlp.topic = pa.topic
                 AND mlp.question_index = pr.question_index
                WHERE pr.is_correct = 0
                  AND pr.question_index IS NOT NULL
                  AND pa.domain = ?
                  AND pa.topic = ?
                  AND pa.user_id IS ?
                  AND {tracked_sql}
                  AND COALESCE(mlp.status, 'unreviewed') != 'mastered'
                GROUP BY pr.question_index
                ORDER BY wrong_count DESC, last_wrong_at DESC
                """,
                (learner, domain, topic, user_id),
            ).fetchall()
        else:
            rows = db.execute(
                f"""
                SELECT pr.question_index AS qi,
                       COUNT(*) AS wrong_count,
                       MAX(pr.submitted_at) AS last_wrong_at
                FROM practice_responses pr
                JOIN practice_attempts pa ON pa.id = pr.attempt_id
                LEFT JOIN mistake_learning_progress mlp
                  ON mlp.learner_key = ?
                 AND mlp.domain = pa.domain
                 AND mlp.topic = pa.topic
                 AND mlp.question_index = pr.question_index
                WHERE pr.is_correct = 0
                  AND pr.question_index IS NOT NULL
                  AND pa.domain = ?
                  AND pa.topic = ?
                  AND pa.user_id IS NULL
                  AND {tracked_sql}
                  AND COALESCE(mlp.status, 'unreviewed') != 'mastered'
                GROUP BY pr.question_index
                ORDER BY wrong_count DESC, last_wrong_at DESC
                """,
                (learner, domain, topic),
            ).fetchall()
        if not rows:
            continue
        questions = get_questions_for_topic(domain, topic, BANKS[domain][topic])
        for row in rows:
            qi = int(row["qi"])
            key = (domain, topic, qi)
            if key in seen or qi < 0 or qi >= len(questions):
                continue
            qobj = questions[qi]
            unit_key = _sat_mistake_unit_key(domain, qobj)
            if unit_key not in SAT_MISTAKE_UNIT_META:
                continue
            sec, title_en, detail = _summary_topic_fields(domain, qobj)
            pool.append(
                {
                    "domain": domain,
                    "topic": topic,
                    "q_index": qi,
                    "unit_key": unit_key,
                    "unit_label": SAT_MISTAKE_UNIT_META[unit_key]["label"],
                    "unit_title": SAT_MISTAKE_UNIT_META[unit_key]["title"],
                    "topic_title": TOPIC_TITLES.get(topic, topic),
                    "knowledge_section": sec,
                    "knowledge_title": title_en or detail or TOPIC_TITLES.get(topic, topic),
                    "display_number": qobj.get("display_number", qi + 1),
                    "wrong_count": int(row["wrong_count"] or 0),
                    "last_wrong_at": row["last_wrong_at"],
                    "source": "Hard Question" if domain == "hard_problem" else "SAT Unit Practice",
                }
            )
            seen.add(key)
    pool.sort(key=lambda x: (-int(x["wrong_count"]), str(x.get("last_wrong_at") or ""), x["unit_key"]))
    return pool


def _sat_mistake_dashboard(db: sqlite3.Connection, user_id: Any) -> dict[str, Any]:
    pool = _sat_active_mistake_pool(db, user_id)
    by_unit: dict[str, list[dict[str, Any]]] = {k: [] for k in SAT_MISTAKE_UNIT_ORDER}
    for item in pool:
        by_unit[item["unit_key"]].append(item)
    units = []
    for key in SAT_MISTAKE_UNIT_ORDER:
        meta = SAT_MISTAKE_UNIT_META[key]
        items = by_unit[key]
        top_skills: dict[str, int] = defaultdict(int)
        for item in items:
            top_skills[str(item.get("knowledge_title") or item["topic_title"])] += 1
        units.append(
            {
                "key": key,
                **meta,
                "count": len(items),
                "items": items,
                "top_skills": [
                    {"title": title, "count": count}
                    for title, count in sorted(top_skills.items(), key=lambda pair: -pair[1])[:5]
                ],
            }
        )
    return {
        "pool": pool,
        "units": units,
        "active_count": len(pool),
        "unlock_count": SAT_MISTAKE_TEST_SIZE,
        "can_generate": len(pool) >= SAT_MISTAKE_TEST_SIZE,
        "needed": max(0, SAT_MISTAKE_TEST_SIZE - len(pool)),
    }


def _select_sat_mistake_test_items(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_unit: dict[str, list[dict[str, Any]]] = {k: [] for k in SAT_MISTAKE_UNIT_ORDER}
    for item in pool:
        by_unit[item["unit_key"]].append(item)
    selected: list[dict[str, Any]] = []
    chosen: set[tuple[str, str, int]] = set()

    def take(item: dict[str, Any]) -> None:
        key = (item["domain"], item["topic"], int(item["q_index"]))
        if key in chosen:
            return
        chosen.add(key)
        selected.append(dict(item))

    for unit_key in SAT_MISTAKE_UNIT_ORDER:
        quota = int(SAT_MISTAKE_UNIT_META[unit_key]["quota"])
        for item in by_unit[unit_key][:quota]:
            take(item)
    if len(selected) < SAT_MISTAKE_TEST_SIZE:
        leftovers = [
            item
            for item in pool
            if (item["domain"], item["topic"], int(item["q_index"])) not in chosen
        ]
        leftovers.sort(key=lambda x: (-int(x["wrong_count"]), str(x.get("last_wrong_at") or "")))
        for item in leftovers:
            if len(selected) >= SAT_MISTAKE_TEST_SIZE:
                break
            take(item)
    selected = selected[:SAT_MISTAKE_TEST_SIZE]
    random.shuffle(selected)
    for i, item in enumerate(selected):
        item["order"] = i
    return selected


def _sat_mistake_test_row_or_404(db: sqlite3.Connection, test_id: int, user_id: Any) -> sqlite3.Row:
    row = db.execute(
        "SELECT * FROM sat_mistake_tests WHERE id = ? AND user_id IS ?",
        (test_id, user_id),
    ).fetchone()
    if row is None:
        abort(404)
    return row


def _sat_mistake_test_items(row: sqlite3.Row) -> list[dict[str, Any]]:
    try:
        raw = json.loads(row["items_json"] or "[]")
    except (TypeError, json.JSONDecodeError):
        raw = []
    return [dict(item) for item in raw if isinstance(item, dict)]


@app.route("/practice/mistakes/sat")
def practice_sat_mistakes():
    db = get_db()
    user_id = session.get("user_id")
    dashboard = _sat_mistake_dashboard(db, user_id)
    return render_template(
        "sat_mistakes.html",
        dashboard=dashboard,
        test_size=SAT_MISTAKE_TEST_SIZE,
        time_limit_minutes=SAT_MISTAKE_TEST_SECONDS // 60,
    )


@app.route("/practice/mistakes/sat/generate", methods=["POST"])
def practice_sat_mistake_test_generate():
    db = get_db()
    user_id = session.get("user_id")
    dashboard = _sat_mistake_dashboard(db, user_id)
    if not dashboard["can_generate"]:
        flash(f"You need {dashboard['needed']} more active SAT mistake(s) before a 22-question test unlocks.")
        return redirect(url_for("practice_sat_mistakes"))
    items = _select_sat_mistake_test_items(dashboard["pool"])
    cur = db.execute(
        """
        INSERT INTO sat_mistake_tests (user_id, learner_key, items_json, status, started_at, time_limit_seconds)
        VALUES (?, ?, ?, 'active', datetime('now'), ?)
        """,
        (user_id, _learner_key(), json.dumps(items), SAT_MISTAKE_TEST_SECONDS),
    )
    db.commit()
    return redirect(url_for("practice_sat_mistake_test_question", test_id=int(cur.lastrowid), step=0))


@app.route("/practice/mistakes/sat/test/<int:test_id>/<int:step>")
def practice_sat_mistake_test_question(test_id: int, step: int):
    db = get_db()
    user_id = session.get("user_id")
    row = _sat_mistake_test_row_or_404(db, test_id, user_id)
    items = _sat_mistake_test_items(row)
    if not items:
        flash("That mistake test has no questions.")
        return redirect(url_for("practice_sat_mistakes"))
    if str(row["status"]) == "completed":
        return redirect(url_for("practice_sat_mistake_test_done", test_id=test_id))
    step = max(0, min(step, len(items) - 1))
    item = items[step]
    questions = get_questions_for_topic(item["domain"], item["topic"], BANKS[item["domain"]][item["topic"]])
    q_index = int(item["q_index"])
    if q_index < 0 or q_index >= len(questions):
        abort(404)
    q = questions[q_index]
    answered_rows = db.execute(
        "SELECT item_order FROM sat_mistake_test_responses WHERE test_id = ?",
        (test_id,),
    ).fetchall()
    answered = {int(r["item_order"]) for r in answered_rows}
    started_row = db.execute(
        "SELECT CAST(strftime('%s', started_at) AS INTEGER) AS started_unix FROM sat_mistake_tests WHERE id = ?",
        (test_id,),
    ).fetchone()
    return render_template(
        "sat_mistake_test.html",
        test_id=test_id,
        item=item,
        q=_sanitize_question_for_render(q),
        step=step,
        total=len(items),
        answered_qset=answered,
        answered_count=len(answered),
        answered_pct=min(100, round(100 * len(answered) / len(items))) if items else 0,
        choice_letters=[chr(ord("A") + i) for i in range(len(q.get("choices") or []))],
        time_limit_seconds=int(row["time_limit_seconds"] or SAT_MISTAKE_TEST_SECONDS),
        started_unix=int(started_row["started_unix"] or 0) if started_row else 0,
    )


@app.route("/practice/mistakes/sat/test/<int:test_id>/submit", methods=["POST"])
def practice_sat_mistake_test_submit(test_id: int):
    db = get_db()
    user_id = session.get("user_id")
    row = _sat_mistake_test_row_or_404(db, test_id, user_id)
    if str(row["status"]) == "completed":
        return redirect(url_for("practice_sat_mistake_test_done", test_id=test_id))
    items = _sat_mistake_test_items(row)
    try:
        step = int(request.form.get("step") or 0)
    except ValueError:
        step = 0
    if step < 0 or step >= len(items):
        return redirect(url_for("practice_sat_mistake_test_done", test_id=test_id))
    raw_answer = (request.form.get("selected_answer") or "").strip()
    if not raw_answer:
        flash("Please enter or select an answer before submitting.")
        return redirect(url_for("practice_sat_mistake_test_question", test_id=test_id, step=step))
    item = items[step]
    questions = get_questions_for_topic(item["domain"], item["topic"], BANKS[item["domain"]][item["topic"]])
    q_index = int(item["q_index"])
    q = questions[q_index]
    q_kind = q.get("question_kind", "mcq")
    selected = raw_answer.upper()[:1] if q_kind in ("mcq", "mcq5") else raw_answer
    is_correct, correct_answer = grade_for_db(q, selected)
    db.execute(
        """
        INSERT INTO sat_mistake_test_responses (
            test_id, item_order, domain, topic, question_index,
            selected_answer, correct_answer, is_correct, submitted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(test_id, item_order) DO UPDATE SET
            selected_answer = excluded.selected_answer,
            correct_answer = excluded.correct_answer,
            is_correct = excluded.is_correct,
            submitted_at = datetime('now')
        """,
        (test_id, step, item["domain"], item["topic"], q_index, selected, correct_answer, is_correct),
    )
    if is_correct == 1:
        _mistake_progress_on_correct(db, _learner_key(), item["domain"], item["topic"], q_index)
    elif is_correct == 0:
        _mistake_progress_on_wrong(db, _learner_key(), item["domain"], item["topic"], q_index)
    db.commit()
    if step >= len(items) - 1:
        return redirect(url_for("practice_sat_mistake_test_done", test_id=test_id))
    return redirect(url_for("practice_sat_mistake_test_question", test_id=test_id, step=step + 1))


@app.route("/practice/mistakes/sat/test/<int:test_id>/done")
def practice_sat_mistake_test_done(test_id: int):
    db = get_db()
    user_id = session.get("user_id")
    row = _sat_mistake_test_row_or_404(db, test_id, user_id)
    items = _sat_mistake_test_items(row)
    responses = db.execute(
        """
        SELECT item_order, selected_answer, correct_answer, is_correct
        FROM sat_mistake_test_responses
        WHERE test_id = ?
        ORDER BY item_order
        """,
        (test_id,),
    ).fetchall()
    by_order = {int(r["item_order"]): r for r in responses}
    correct = sum(1 for r in responses if int(r["is_correct"] or 0) == 1)
    total = len(items)
    if len(responses) >= total and str(row["status"]) != "completed":
        db.execute(
            "UPDATE sat_mistake_tests SET status = 'completed', completed_at = datetime('now') WHERE id = ?",
            (test_id,),
        )
        db.commit()
    unit_summary: dict[str, dict[str, Any]] = {
        k: {"key": k, **SAT_MISTAKE_UNIT_META[k], "total": 0, "correct": 0}
        for k in SAT_MISTAKE_UNIT_ORDER
    }
    rows = []
    for i, item in enumerate(items):
        resp = by_order.get(i)
        unit = unit_summary[item["unit_key"]]
        unit["total"] += 1
        if resp and int(resp["is_correct"] or 0) == 1:
            unit["correct"] += 1
        rows.append(
            {
                **item,
                "selected_answer": resp["selected_answer"] if resp else "—",
                "correct_answer": resp["correct_answer"] if resp else "—",
                "is_correct": bool(resp and int(resp["is_correct"] or 0) == 1),
                "practice_href": url_for("practice_question", domain=item["domain"], topic=item["topic"], qnum=int(item["q_index"])),
            }
        )
    for unit in unit_summary.values():
        unit["accuracy"] = round(100 * unit["correct"] / unit["total"]) if unit["total"] else None
    return render_template(
        "sat_mistake_test_done.html",
        test_id=test_id,
        total=total,
        answered=len(responses),
        correct=correct,
        pct=round(100 * correct / total) if total else 0,
        units=list(unit_summary.values()),
        rows=rows,
    )


def _placement_analytics_unit(q_index: int, topic: str | None = None) -> dict:
    if topic == "enhanced_math_1":
        if q_index < 10:
            return {
                "id": "em1-part-a",
                "label": "Part A",
                "subtitle": "Core readiness",
                "order": 1,
            }
        if q_index < 30:
            return {
                "id": "em1-part-b",
                "label": "Part B",
                "subtitle": "Math I mastery",
                "order": 2,
            }
        if q_index < 50:
            return {
                "id": "em1-part-c",
                "label": "Part C",
                "subtitle": "Enhanced Math I readiness",
                "order": 3,
            }
        if q_index < 54:
            return {
                "id": "em1-graphing",
                "label": "Graphing",
                "subtitle": "Constructed response",
                "order": 4,
            }
        return {
            "id": "em1-fr",
            "label": "Free response",
            "subtitle": "Modeling & reasoning",
            "order": 5,
        }
    if topic == "enhanced_math_2":
        if q_index < 28:
            return {
                "id": "em2-part-a",
                "label": "Part A",
                "subtitle": "Math II readiness",
                "order": 1,
            }
        if q_index < 55:
            return {
                "id": "em2-part-b",
                "label": "Part B",
                "subtitle": "Enhanced Math II readiness",
                "order": 2,
            }
        if q_index < 59:
            return {
                "id": "em2-graphing",
                "label": "Graphing",
                "subtitle": "Constructed response",
                "order": 3,
            }
        return {
            "id": "em2-fr",
            "label": "Free response",
            "subtitle": "Modeling & reasoning",
            "order": 4,
        }
    if topic == "middle_level":
        if q_index < 20:
            return {
                "id": "middle-part-i",
                "label": "Part I",
                "subtitle": "Math 5 readiness",
                "order": 1,
            }
        if q_index < 40:
            return {
                "id": "middle-part-ii",
                "label": "Part II",
                "subtitle": "Math 6 readiness",
                "order": 2,
            }
        if q_index < 60:
            return {
                "id": "middle-part-iii",
                "label": "Part III",
                "subtitle": "Math 7 readiness",
                "order": 3,
            }
        if q_index < 80:
            return {
                "id": "middle-part-iv",
                "label": "Part IV",
                "subtitle": "Math 8 readiness",
                "order": 4,
            }
        return {
            "id": "middle-part-v",
            "label": "Part V",
            "subtitle": "Algebra 1/2 readiness",
            "order": 5,
        }
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
        return _placement_analytics_unit(int(row.get("q_index") or 0), str(row.get("topic") or ""))
    return {
        "id": f"other-{domain or 'practice'}",
        "label": str(domain or "Other"),
        "subtitle": "Other practice",
        "order": 99,
    }


def _analytics_partitions(rows: List[dict]) -> List[dict]:
    """Mistake analytics: SAT (parent) → Units 1–4 + hard question mistakes only."""
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
                    "subtitle": f"Hard sets {_hard_drill_display_meta()['range_label']} · classified by SAT unit",
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


def _placement_section_intro_meta(topic: str, section: str) -> dict[str, Any] | None:
    cfg = _placement_flow_config(topic)
    if not cfg or not cfg.get("has_gates"):
        return None
    if cfg.get("gate_kind") == "middle_parts":
        for gate in MIDDLE_LEVEL_PART_GATES:
            if gate["section"] != section:
                continue
            part_num = int(gate["part_num"])
            return {
                "section": section,
                "session_flag": str(gate["session_flag"]),
                "first_qnum": int(gate["first_qnum"]),
                "kicker": f"Placement · Part {part_num} of 5",
                "title": str(gate["band_label"]),
                "lead": (
                    f"You completed {gate['prev_band']} readiness (Part {part_num - 1}). "
                    f"Next: 20 questions at the {gate['band_label']} level — "
                    f"questions {int(gate['first_qnum']) + 1}–{int(gate['first_qnum']) + 20} of 100."
                ),
                "begin_label": f"Begin {gate['band_label']}",
                "part_num": part_num,
                "part_total": 5,
                "q_start": int(gate["first_qnum"]) + 1,
                "q_end": int(gate["first_qnum"]) + 20,
                "total_items": 100,
                "cards": [
                    {
                        "icon": str(part_num),
                        "title": f"Part {part_num}",
                        "body": str(gate["part_title"]),
                    },
                    {
                        "icon": "20",
                        "title": "Twenty items",
                        "body": "Show your work in the response box — same order as the printable placement test.",
                    },
                    {
                        "icon": "⏱",
                        "title": "Timer",
                        "body": "Your placement timer keeps running across all 100 questions.",
                    },
                ],
            }
        return None
    if cfg.get("gate_kind") == "upper_gates":
        for gate in _upper_placement_gate_gates():
            if gate["section"] != section:
                continue
            gate_num = int(gate["gate_num"])
            total_items = int(cfg.get("total") or 85)
            return {
                "section": section,
                "session_flag": str(gate["session_flag"]),
                "first_qnum": int(gate["first_qnum"]),
                "kicker": f"Placement · Gate {gate_num} of 5",
                "title": str(gate["gate_label"]),
                "lead": (
                    f"You finished {gate['prev_gate_title']}. "
                    f"This gate is complete — take a short breath, then continue with "
                    f"{int(gate['item_count'])} multiple-choice items "
                    f"(questions {int(gate['q_start'])}–{int(gate['q_end'])} of {total_items})."
                ),
                "begin_label": f"Begin Gate {gate_num}",
                "part_num": gate_num,
                "part_total": 5,
                "q_start": int(gate["q_start"]),
                "q_end": int(gate["q_end"]),
                "total_items": total_items,
                "cards": [
                    {
                        "icon": str(gate_num),
                        "title": f"Gate {gate_num}",
                        "body": str(gate["gate_title"]),
                    },
                    {
                        "icon": str(gate["item_count"]),
                        "title": f"{gate['item_count']} items",
                        "body": "Multiple-choice items in the same order as the printable placement test.",
                    },
                    {
                        "icon": "⏱",
                        "title": "Timer",
                        "body": "Your placement timer keeps running across all 85 questions.",
                    },
                ],
            }
        return None
    mc = int(cfg["mc_count"])
    graph = int(cfg["graph_count"])
    fr = int(cfg["fr_count"])
    prefix = str(cfg["session_prefix"])
    if section == "graphing":
        mc_label = str(mc)
        return {
            "section": "graphing",
            "session_flag": f"{prefix}_seen_graphing",
            "first_qnum": mc,
            "kicker": "Placement · Section 2 of 3",
            "title": "Graphing — show your work",
            "lead": (
                f"You finished the {mc_label} multiple-choice items. "
                f"Next: {graph} graphing and coordinate-reasoning questions."
            ),
            "begin_label": "Begin graphing section",
            "part_num": 2,
            "part_total": 3,
            "q_start": mc + 1,
            "q_end": mc + graph,
            "total_items": mc + graph + fr,
            "cards": [
                {
                    "icon": "G",
                    "title": "What to do",
                    "body": "Use the grid in each question (or graph paper). Type your graph description, interval notation, and key steps in the response box.",
                },
                {
                    "icon": str(graph),
                    "title": f"{graph} items",
                    "body": "Number line, inequalities, systems, and transformations — same order as the printable placement test.",
                },
                {
                    "icon": "✓",
                    "title": "Scoring",
                    "body": "These items are saved for your teacher or advisor. They are not auto-scored online.",
                },
            ],
        }
    if section == "free_response":
        return {
            "section": "free_response",
            "session_flag": f"{prefix}_seen_fr",
            "first_qnum": mc + graph,
            "kicker": "Placement · Section 3 of 3",
            "title": "Free response — modeling & reasoning",
            "lead": (
                f"Final section: {fr} written-response items covering modeling, proof, "
                "and Enhanced readiness challenge."
            ),
            "begin_label": "Begin free response section",
            "part_num": 3,
            "part_total": 3,
            "q_start": mc + graph + 1,
            "q_end": mc + graph + fr,
            "total_items": mc + graph + fr,
            "cards": [
                {
                    "icon": "FR",
                    "title": "What to do",
                    "body": "Show each step and explain your reasoning. Use the response box for your full solution — work on paper is fine too.",
                },
                {
                    "icon": str(fr),
                    "title": f"{fr} items",
                    "body": "Equation reasoning through advanced topics — matches the paper test’s free-response block.",
                },
                {
                    "icon": "⏱",
                    "title": "Timer",
                    "body": "Your placement timer keeps running. Take your time on proofs and explanations.",
                },
            ],
        }
    return None


def _placement_section_gate_redirect(topic: str, qnum: int) -> str | None:
    cfg = _placement_flow_config(topic)
    if not cfg or not cfg.get("has_gates"):
        return None
    slug = _placement_slug_for_topic(topic)
    if cfg.get("gate_kind") == "middle_parts":
        for gate in MIDDLE_LEVEL_PART_GATES:
            if qnum >= int(gate["first_qnum"]) and not session.get(str(gate["session_flag"])):
                return url_for(
                    "placement_section_intro",
                    slug=slug,
                    section=str(gate["section"]),
                )
        return None
    if cfg.get("gate_kind") == "upper_gates":
        for gate in _upper_placement_gate_gates():
            if qnum >= int(gate["first_qnum"]) and not session.get(str(gate["session_flag"])):
                return url_for(
                    "placement_section_intro",
                    slug=slug,
                    section=str(gate["section"]),
                )
        return None
    mc = int(cfg["mc_count"])
    graph = int(cfg["graph_count"])
    fr_start = mc + graph
    prefix = str(cfg["session_prefix"])
    if qnum >= fr_start and not session.get(f"{prefix}_seen_fr"):
        return url_for("placement_section_intro", slug=slug, section="free_response")
    if mc <= qnum < fr_start and not session.get(f"{prefix}_seen_graphing"):
        return url_for("placement_section_intro", slug=slug, section="graphing")
    return None


def _placement_section_back_href(topic: str, section: str) -> str:
    cfg = _placement_flow_config(topic) or {}
    if cfg.get("gate_kind") == "middle_parts":
        for gate in MIDDLE_LEVEL_PART_GATES:
            if gate["section"] == section:
                return url_for(
                    "practice_question",
                    domain="placement",
                    topic=topic,
                    qnum=int(gate["after_q_index"]),
                )
        return url_for("practice_question", domain="placement", topic=topic, qnum=0)
    if cfg.get("gate_kind") == "upper_gates":
        for gate in _upper_placement_gate_gates():
            if gate["section"] == section:
                return url_for(
                    "practice_question",
                    domain="placement",
                    topic=topic,
                    qnum=int(gate["after_q_index"]),
                )
        return url_for("practice_question", domain="placement", topic=topic, qnum=0)
    mc = int(cfg.get("mc_count") or 0)
    graph = int(cfg.get("graph_count") or 0)
    if section == "graphing":
        return url_for("practice_question", domain="placement", topic=topic, qnum=mc - 1)
    return url_for(
        "practice_question", domain="placement", topic=topic, qnum=mc + graph - 1
    )


@app.route("/placement/<slug>/section/<section>")
def placement_section_intro(slug: str, section: str):
    session["active_track_label"] = "Course placement"
    topic = _placement_topic_for_slug(slug)
    if not topic:
        abort(404)
    meta = _placement_section_intro_meta(topic, section)
    if not meta:
        abort(404)
    back_href = _placement_section_back_href(topic, section)
    return render_template(
        "placement_section_intro.html",
        test=_placement_test_by_slug(slug),
        slug=slug,
        topic=topic,
        section_kicker=meta["kicker"],
        section_title=meta["title"],
        section_lead=meta["lead"],
        section_cards=meta["cards"],
        part_num=meta.get("part_num", 1),
        part_total=meta.get("part_total", 1),
        q_start=meta.get("q_start"),
        q_end=meta.get("q_end"),
        total_items=meta.get("total_items"),
        begin_label=meta["begin_label"],
        back_href=back_href,
        begin_href=url_for("placement_section_begin", slug=slug, section=section),
    )


@app.route("/placement/<slug>/section/<section>/begin", methods=["POST"])
def placement_section_begin(slug: str, section: str):
    topic = _placement_topic_for_slug(slug)
    if not topic:
        abort(404)
    meta = _placement_section_intro_meta(topic, section)
    if not meta:
        abort(404)
    session[meta["session_flag"]] = True
    session.modified = True
    return redirect(
        url_for(
            "practice_question",
            domain="placement",
            topic=topic,
            qnum=meta["first_qnum"],
        )
    )


@app.route("/placement")
def placement_landing():
    session["active_track_label"] = "Course placement"
    catalog = _enrich_placement_catalog_with_pdf_meta(_load_placement_catalog())
    return render_template(
        "placement_catalog.html",
        catalog=catalog,
    )


@app.route("/placement/<slug>")
def placement_test_landing(slug: str):
    session["active_track_label"] = "Course placement"
    test = _placement_test_by_slug(slug)
    if not test:
        abort(404)
    if str(test.get("status") or "") != "available":
        flash(f"{test.get('title', 'That placement test')} is coming soon.")
        return redirect(url_for("placement_landing"))
    topic = _placement_topic_for_slug(slug)
    if not topic:
        abort(404)
    return render_template(
        "placement_test_landing.html",
        test=test,
        placement_parts=_placement_landing_parts_for_topic(topic),
        topic=topic,
        slug=slug,
        pdf_meta=_placement_pdf_meta(test.get("pdf_file")),
    )


@app.route("/placement/start")
def placement_start_legacy():
    return redirect(url_for("placement_test_landing", slug="upper-algebra-precalc"))


@app.route("/placement/<slug>/start")
def placement_test_start(slug: str):
    session["active_track_label"] = "Course placement"
    topic = _placement_topic_for_slug(slug)
    if not topic:
        abort(404)
    test = _placement_test_by_slug(slug)
    if not test or str(test.get("status") or "") != "available":
        abort(404)
    _clear_placement_session_attempt(topic)
    session.modified = True
    return render_template(
        "placement_start.html",
        test=test,
        topic=topic,
        slug=slug,
    )


@app.route("/placement/begin", methods=["POST"])
def placement_begin_legacy():
    return redirect(url_for("placement_test_landing", slug="upper-algebra-precalc"))


@app.route("/placement/<slug>/begin", methods=["POST"])
def placement_test_begin(slug: str):
    session["active_track_label"] = "Course placement"
    topic = _placement_topic_for_slug(slug)
    if not topic:
        abort(404)
    test = _placement_test_by_slug(slug)
    if not test or str(test.get("status") or "") != "available":
        abort(404)
    _clear_placement_session_attempt(topic)
    name = request.form.get("student_name", "").strip()
    grade = request.form.get("student_grade", "").strip()
    course = request.form.get("student_math_course", "").strip()
    if len(name) < 1:
        flash("Please enter the student name.")
        return redirect(url_for("placement_test_start", slug=slug))
    if len(name) > 160:
        flash("Name is too long (160 characters max).")
        return redirect(url_for("placement_test_start", slug=slug))
    grade = grade[:120]
    course = course[:400]
    session["placement_student_name"] = name[:160]
    session["placement_student_grade"] = grade
    session["placement_student_math_course"] = course
    session.modified = True
    return redirect(
        url_for("practice_question", domain="placement", topic=topic, qnum=0)
    )


@app.route("/practice")
def practice():
    """SAT Math home: four modules (specialized, challenge, exams, analytics)."""
    session["active_track_label"] = "SAT Math"
    return render_template("practice_hub.html", **_practice_hub_context())


@app.route("/practice/progress")
def practice_progress():
    """Student learning dashboard: mock trends, chapter coverage, miss-quiz digest."""
    session["active_track_label"] = "SAT Math"
    if not require_login():
        return redirect(url_for("login", next=url_for("practice_progress")))
    db = get_db()
    uid = int(session["user_id"])
    return render_template(
        "student_report.html", **_student_report_context(db, uid, viewer="student")
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
    ctx = _course_materials_gate_context()
    return render_template("course_materials_gate.html", **ctx)


@app.route("/practice/materials/phase/<int:phase_num>")
def practice_course_materials_phase(phase_num: int):
    session["active_track_label"] = "SAT Math"
    ctx = _course_materials_phase_context(phase_num)
    if not ctx:
        abort(404)
    return render_template("course_materials_phase.html", **ctx)


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
    prev_material, next_material = _course_material_neighbors(material)
    material_phase = int(material.get("phase") or 1)
    pace_training = material_phase == 3
    return render_template(
        "course_material_view.html",
        material=material,
        pdf_href=pdf_href,
        prev_material=prev_material,
        next_material=next_material,
        pace_training=pace_training,
        pace_seconds=PHASE3_PACE_SECONDS if pace_training else 0,
        cm_progress_api=url_for("practice_course_material_progress_api", slug=slug),
        cm_classroom_active_api=url_for("practice_course_material_classroom_active_api", slug=slug),
        cm_classroom_response_api=url_for("practice_course_material_classroom_response_api", slug=slug),
        cm_classroom_summary_api=url_for("practice_course_material_classroom_summary_api", slug=slug)
        if current_user_can_access_admin()
        else None,
        cm_classroom_start_api=url_for("practice_course_material_classroom_start_api", slug=slug)
        if current_user_can_access_admin()
        else None,
        cm_classroom_slide_api=url_for("practice_course_material_classroom_slide_api", slug=slug)
        if current_user_can_access_admin()
        else None,
        cm_classroom_ink_api=url_for("practice_course_material_classroom_ink_api", slug=slug),
        cm_classroom_href=url_for("practice_course_material_classroom", slug=slug)
        if current_user_can_access_admin()
        else None,
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
        display_title = (
            TOPIC_TITLES.get(topic)
            if topic in {"hard_20", "hard_21"}
            else f"Hard Practice {set_roman}"
        )
        pace_secs = _phase3_pace_seconds("hard_problem", topic)
        hard_sets.append(
            {
                "index": idx,
                "set_number": set_number,
                "roman": set_roman,
                "topic": topic,
                "title": display_title,
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
                "pace_training": bool(pace_secs),
                "pace_seconds": int(pace_secs or 0),
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
        hard_drill_meta=_hard_drill_display_meta(),
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
    ctx = _practice_exam_center_context()
    return render_template("word_problem_exams.html", **ctx)


WORD_PROBLEM_SET_SIZE = 22
WORD_PROBLEM_SECONDS = 35 * 60
WORD_PROBLEM_SESSION_KEY = "sat_word_problem_answers"
UNIT_BANK_EXAM_SESSION_KEY = "sat_unit_bank_exam_answers"
RANDOM_TEST_SESSION_KEY = "sat_random_test_attempt"
RANDOM_TEST_UNIT_TARGETS = (("unit1", 8), ("unit2", 8), ("unit3", 3), ("unit4", 3))


WORD_PROBLEM_CONTEXT_WORDS = frozenset(
    """
    account accounts aquarium average bank biologist bus business car class club company
    cost costs customer data day days distance dollar dollars drives earnings employees
    experiment fee fish flowers food garden gallons group hours interest jars kelvins
    lawn machine membership miles minutes month months population price product profit
    rate recipe rent repair restaurant revenue sale sales school scientist service shop
    store student students survey teacher temperature tickets time train trip week weeks
    window workers years
    """.split()
)


def _word_problem_sources() -> list[tuple[str, str]]:
    sources = [
        ("algebra", "unit_1_all"),
        ("advanced_math", "unit_2_all"),
        ("problem_solving", "unit_3_all"),
        ("geometry", "unit_4_all"),
    ]
    for topic in sorted(BANKS.get("hard_problem") or {}, key=_topic_bank_sort_key):
        sources.append(("hard_problem", topic))
    return sources


def _word_problem_plain_text(q: dict) -> str:
    text = strip_html(str(q.get("stem") or ""))
    return re.sub(r"\s+", " ", text).strip()


def _is_word_problem_question(q: dict) -> bool:
    if q.get("question_kind") not in ("mcq", "mcq5"):
        return False
    if len(q.get("choices") or []) < 4:
        return False
    text = _word_problem_plain_text(q).lower()
    words = re.findall(r"[a-z]+", text)
    if len(words) < 28:
        return False
    context_hits = sum(1 for w in words if w in WORD_PROBLEM_CONTEXT_WORDS)
    if context_hits >= 2:
        return True
    # Long applied prompts sometimes use uncommon nouns not in the list above.
    return len(words) >= 45 and any(w in words for w in ("which", "what", "how"))


def _word_problem_unit_key(item: dict) -> str:
    label = str(item.get("unit_label") or "")
    m = re.search(r"Unit\s+([1-4])", label)
    return f"unit{m.group(1)}" if m else "hard"


def _unit_bank_sources() -> list[tuple[str, str]]:
    sources = [
        ("algebra", "unit_1_all"),
        ("advanced_math", "unit_2_all"),
        ("problem_solving", "unit_3_all"),
        ("geometry", "unit_4_all"),
    ]
    for topic in sorted(BANKS.get("hard_problem") or {}, key=_topic_bank_sort_key):
        sources.append(("hard_problem", topic))
    return sources


def _exam_question_fingerprint(q: dict) -> str:
    plain = _word_problem_plain_text(q)
    return re.sub(r"\s+", " ", plain).lower()[:650]


def _exam_question_item(domain: str, topic: str, q_index: int, q: dict) -> dict:
    plain = _word_problem_plain_text(q)
    unit_label = str(q.get("sat_unit_label") or q.get("knowledge_section") or domain)
    unit_title = str(q.get("sat_unit_title") or q.get("knowledge_section_title_en") or TOPIC_TITLES.get(topic, topic))
    return {
        "id": f"{domain}:{topic}:{q_index}",
        "domain": domain,
        "topic": topic,
        "q_index": q_index,
        "q": q,
        "unit_label": unit_label,
        "unit_title": unit_title,
        "topic_title": TOPIC_TITLES.get(topic, topic),
        "excerpt": plain[:150],
    }


def _word_problem_bank() -> list[dict]:
    seen: set[str] = set()
    items: list[dict] = []
    for domain, topic in _word_problem_sources():
        tex_file = BANKS.get(domain, {}).get(topic)
        if not tex_file:
            continue
        questions = get_questions_for_topic(domain, topic, tex_file)
        for q_index, q in enumerate(questions):
            if not _is_word_problem_question(q):
                continue
            plain = _word_problem_plain_text(q)
            fingerprint = _exam_question_fingerprint(q)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            items.append(_exam_question_item(domain, topic, q_index, q))

    buckets: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        buckets[_word_problem_unit_key(item)].append(item)
    ordered: list[dict] = []
    bucket_order = ("unit1", "unit2", "unit3", "unit4", "hard")
    while any(buckets.values()):
        for key in bucket_order:
            if buckets.get(key):
                ordered.append(buckets[key].pop(0))
    return ordered


def _unit_bank_exam_bank() -> list[dict]:
    seen: set[str] = set()
    items: list[dict] = []
    for domain, topic in _unit_bank_sources():
        tex_file = BANKS.get(domain, {}).get(topic)
        if not tex_file:
            continue
        questions = get_questions_for_topic(domain, topic, tex_file)
        for q_index, q in enumerate(questions):
            if q.get("question_kind") not in ("mcq", "mcq5"):
                continue
            if len(q.get("choices") or []) < 4:
                continue
            fingerprint = _exam_question_fingerprint(q)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            items.append(_exam_question_item(domain, topic, q_index, q))
    return items


def _exam_unit_sort_key(label: str) -> tuple[int, str]:
    m = re.search(r"Unit\s+([1-4])", str(label))
    return (int(m.group(1)) if m else 99, str(label))


def _build_exam_sets(items: list[dict]) -> list[dict]:
    sets: list[dict] = []
    for start in range(0, len(items), WORD_PROBLEM_SET_SIZE):
        chunk = items[start:start + WORD_PROBLEM_SET_SIZE]
        unique_count = len(chunk)
        repeat_count = 0
        if chunk and len(chunk) < WORD_PROBLEM_SET_SIZE and len(items) > len(chunk):
            needed = WORD_PROBLEM_SET_SIZE - len(chunk)
            repeats = []
            for base in items:
                if base["id"] in {x["id"] for x in chunk}:
                    continue
                repeated = dict(base)
                repeated["is_repeat"] = True
                repeats.append(repeated)
                if len(repeats) >= needed:
                    break
            chunk = chunk + repeats
            repeat_count = len(repeats)
        unit_counts: dict[str, int] = defaultdict(int)
        for item in chunk:
            unit_counts[item["unit_label"]] += 1
        sets.append(
            {
                "id": len(sets) + 1,
                "items": chunk,
                "count": len(chunk),
                "unique_count": unique_count,
                "repeat_count": repeat_count,
                "is_full": len(chunk) == WORD_PROBLEM_SET_SIZE,
                "unit_counts": sorted(unit_counts.items(), key=lambda kv: _exam_unit_sort_key(kv[0])),
            }
        )
    return sets


def _word_problem_sets() -> list[dict]:
    return _build_exam_sets(_word_problem_bank())


def _unit_bank_exam_sets() -> list[dict]:
    return _build_exam_sets(_unit_bank_exam_bank())


def _specialized_exam_bank() -> list[dict]:
    seen: set[str] = set()
    items: list[dict] = []
    for domain, topic in [
        ("algebra", "unit_1_all"),
        ("advanced_math", "unit_2_all"),
        ("problem_solving", "unit_3_all"),
        ("geometry", "unit_4_all"),
    ]:
        tex_file = BANKS.get(domain, {}).get(topic)
        if not tex_file:
            continue
        for q_index, q in enumerate(get_questions_for_topic(domain, topic, tex_file)):
            if q.get("question_kind") not in ("mcq", "mcq5") or len(q.get("choices") or []) < 4:
                continue
            fingerprint = _exam_question_fingerprint(q)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            items.append(_exam_question_item(domain, topic, q_index, q))
    return items


def _hard_problem_exam_bank() -> list[dict]:
    seen: set[str] = set()
    items: list[dict] = []
    for topic in sorted(BANKS.get("hard_problem") or {}, key=_topic_bank_sort_key):
        tex_file = BANKS.get("hard_problem", {}).get(topic)
        if not tex_file:
            continue
        for q_index, q in enumerate(get_questions_for_topic("hard_problem", topic, tex_file)):
            if q.get("question_kind") not in ("mcq", "mcq5") or len(q.get("choices") or []) < 4:
                continue
            fingerprint = _exam_question_fingerprint(q)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            items.append(_exam_question_item("hard_problem", topic, q_index, q))
    return items


def _balanced_random_module_items(source_items: list[dict], seed: str, module_id: int) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for item in source_items:
        buckets[_word_problem_unit_key(item)].append(item)

    selected: list[dict] = []
    selected_ids: set[str] = set()
    for unit_key, target in RANDOM_TEST_UNIT_TARGETS:
        bucket = list(buckets.get(unit_key) or [])
        rng = random.Random(f"{seed}:module{module_id}:{unit_key}")
        rng.shuffle(bucket)
        for item in bucket[:target]:
            copy_item = dict(item)
            copy_item["module_id"] = module_id
            copy_item["unit_key"] = unit_key
            selected.append(copy_item)
            selected_ids.add(item["id"])

    if len(selected) < WORD_PROBLEM_SET_SIZE:
        leftovers = [item for item in source_items if item["id"] not in selected_ids]
        rng = random.Random(f"{seed}:module{module_id}:fill")
        rng.shuffle(leftovers)
        for item in leftovers[: WORD_PROBLEM_SET_SIZE - len(selected)]:
            copy_item = dict(item)
            copy_item["module_id"] = module_id
            copy_item["unit_key"] = _word_problem_unit_key(item)
            selected.append(copy_item)

    rng = random.Random(f"{seed}:module{module_id}:order")
    rng.shuffle(selected)
    return selected[:WORD_PROBLEM_SET_SIZE]


def _random_test_seed() -> str:
    attempt = session.get(RANDOM_TEST_SESSION_KEY)
    if isinstance(attempt, dict) and attempt.get("seed"):
        return str(attempt["seed"])
    seed = str(random.randrange(10**9, 10**10))
    session[RANDOM_TEST_SESSION_KEY] = {"seed": seed, "answers": {}, "deadlines": {}}
    session.modified = True
    return seed


def _random_test_attempt() -> dict[str, Any]:
    attempt = session.get(RANDOM_TEST_SESSION_KEY)
    if not isinstance(attempt, dict) or not attempt.get("seed"):
        seed = _random_test_seed()
        attempt = {"seed": seed, "answers": {}, "deadlines": {}}
    if not isinstance(attempt.get("answers"), dict):
        attempt["answers"] = {}
    if not isinstance(attempt.get("deadlines"), dict):
        attempt["deadlines"] = {}
    return attempt


def _random_test_modules(seed: str) -> dict[int, list[dict]]:
    return {
        1: _balanced_random_module_items(_specialized_exam_bank(), seed, 1),
        2: _balanced_random_module_items(_hard_problem_exam_bank(), seed, 2),
    }


def _random_test_score(raw_correct: int) -> int:
    raw_correct = max(0, min(44, raw_correct))
    return int(round((200 + (raw_correct / 44) * 600) / 10) * 10)


def _random_test_answered_set(module_id: int) -> set[int]:
    answers = _random_test_attempt().get("answers", {}).get(str(module_id), {})
    if not isinstance(answers, dict):
        return set()
    out: set[int] = set()
    for key, value in answers.items():
        if value:
            try:
                out.add(int(key))
            except (TypeError, ValueError):
                pass
    return out


def _save_random_test_answer(module_id: int, step: int, selected: str) -> None:
    attempt = _random_test_attempt()
    answers = attempt.setdefault("answers", {})
    module_answers = answers.get(str(module_id))
    if not isinstance(module_answers, dict):
        module_answers = {}
    module_answers[str(step)] = selected
    answers[str(module_id)] = module_answers
    session[RANDOM_TEST_SESSION_KEY] = attempt
    session.modified = True
    uid = session.get("user_id")
    if not uid:
        return
    seed = str(attempt.get("seed") or "")
    if not seed:
        return
    db = get_db()
    db_attempt_id = _ensure_exam_db_attempt(db, uid, "random-test", seed=seed)
    if not db_attempt_id:
        return
    q, qi = _random_test_question_at(module_id, step, seed)
    if q is not None and qi is not None:
        _persist_exam_response(db, db_attempt_id, qi, q, selected)


def _random_test_deadline_ms(module_id: int) -> int:
    attempt = _random_test_attempt()
    deadlines = attempt.setdefault("deadlines", {})
    key = str(module_id)
    raw = deadlines.get(key)
    try:
        deadline_ms = int(raw)
    except (TypeError, ValueError):
        deadline_ms = 0
    if deadline_ms <= 0:
        deadline_ms = int(time.time() * 1000) + WORD_PROBLEM_SECONDS * 1000
        deadlines[key] = deadline_ms
        session[RANDOM_TEST_SESSION_KEY] = attempt
        session.modified = True
    return deadline_ms


def _random_test_continue_href() -> str:
    attempt = _random_test_attempt()
    seed = str(attempt["seed"])
    modules = _random_test_modules(seed)
    answers = attempt.get("answers", {})
    for module_id in (1, 2):
        module_answers = answers.get(str(module_id), {}) if isinstance(answers, dict) else {}
        if not isinstance(module_answers, dict):
            module_answers = {}
        for idx in range(len(modules[module_id])):
            if not module_answers.get(str(idx)):
                return url_for("practice_random_test_question", module_id=module_id, step=idx)
    return url_for("practice_random_test_done")


def _empty_exam_bank() -> list[dict]:
    return []


def _empty_exam_sets() -> list[dict]:
    return []


def _practice_exam_categories() -> list[dict[str, Any]]:
    return [
        {
            "slug": "word-problems",
            "number": "01",
            "label": "Word Problem",
            "title": "Word Problem",
            "kicker": "Category · Word Problem",
            "short_label": "Word",
            "item_label": "Applied problem item",
            "question_kind_label": "Mixed applied questions in exam pacing.",
            "description": "Long-context and real-world SAT Math questions extracted from Specialized Training and Hard Problem Drill. Students complete the sets in order until every extracted applied problem has been covered.",
            "sets_fn": _word_problem_sets,
            "bank_fn": _word_problem_bank,
            "session_key": WORD_PROBLEM_SESSION_KEY,
            "is_live": True,
        },
        {
            "slug": "unit-bank",
            "number": "02",
            "label": "Unit 1-4 Full Bank",
            "title": "Unit 1-4 Full Bank",
            "kicker": "Category · Full Question Bank",
            "short_label": "Unit Bank",
            "item_label": "SAT bank item",
            "question_kind_label": "Mixed Unit 1-4 and hard-drill questions in exam pacing.",
            "description": "Every multiple-choice question from Unit 1 through Unit 4 plus all Hard Problem Drill questions is grouped into 22-question SAT-style practice sections. New uploaded questions will flow into this category after the question bank is rebuilt.",
            "sets_fn": _unit_bank_exam_sets,
            "bank_fn": _unit_bank_exam_bank,
            "session_key": UNIT_BANK_EXAM_SESSION_KEY,
            "is_live": True,
        },
        {
            "slug": "random-test",
            "number": "03",
            "label": "Random Test",
            "title": "Random Test",
            "kicker": "Category · Full SAT Simulation",
            "short_label": "Random",
            "item_label": "SAT Math module item",
            "question_kind_label": "Two-module SAT Math simulation.",
            "description": "A full SAT Math mock test: Module 1 pulls from Specialized Training and Module 2 pulls from Hard Problem Drill, each balanced Unit 1 35%, Unit 2 35%, Unit 3 15%, Unit 4 15%.",
            "sets_fn": _empty_exam_sets,
            "bank_fn": _empty_exam_bank,
            "session_key": RANDOM_TEST_SESSION_KEY,
            "is_live": True,
            "status_label": "Live",
            "is_random_test": True,
        },
        {
            "slug": "practice-test",
            "number": "04",
            "label": "Practice Test",
            "title": "Practice Test",
            "kicker": "Category · Practice Test",
            "short_label": "Practice Test",
            "item_label": "Practice test item",
            "question_kind_label": "Practice-test questions in exam pacing.",
            "description": "A reserved window for official-style practice test sections. This gives us a clean slot for future uploaded practice tests.",
            "sets_fn": _empty_exam_sets,
            "bank_fn": _empty_exam_bank,
            "session_key": "sat_practice_test_answers",
            "is_live": False,
            "status_label": "Coming soon",
        },
    ]


def _practice_exam_category_or_404(category_slug: str) -> dict[str, Any]:
    for category in _practice_exam_categories():
        if category["slug"] == category_slug:
            return category
    abort(404)


def _practice_exam_sets(category: dict[str, Any]) -> list[dict]:
    return category["sets_fn"]()


def _practice_exam_bank(category: dict[str, Any]) -> list[dict]:
    return category["bank_fn"]()


def _practice_exam_set_or_404(category_slug: str, set_id: int) -> tuple[dict[str, Any], dict]:
    category = _practice_exam_category_or_404(category_slug)
    sets = _practice_exam_sets(category)
    if set_id < 1 or set_id > len(sets):
        abort(404)
    return category, sets[set_id - 1]


def _word_problem_set_or_404(set_id: int) -> dict:
    return _practice_exam_set_or_404("word-problems", set_id)[1]


def _practice_exam_answers(category: dict[str, Any]) -> dict[str, dict[str, str]]:
    raw = session.get(category["session_key"])
    return raw if isinstance(raw, dict) else {}


def _save_practice_exam_answer(category: dict[str, Any], set_id: int, step: int, selected: str) -> None:
    answers = _practice_exam_answers(category)
    key = str(set_id)
    set_answers = answers.get(key)
    if not isinstance(set_answers, dict):
        set_answers = {}
    set_answers[str(step)] = selected
    answers[key] = set_answers
    session[category["session_key"]] = answers
    session.modified = True
    uid = session.get("user_id")
    category_slug = str(category.get("slug") or "")
    if not uid or category_slug not in EXAM_DOMAIN_BY_SLUG:
        return
    db = get_db()
    db_attempt_id = _ensure_exam_db_attempt(db, uid, category_slug, set_id=set_id)
    if not db_attempt_id:
        return
    _, exam_set = _practice_exam_set_or_404(category_slug, set_id)
    items = exam_set["items"]
    if step < 0 or step >= len(items):
        return
    _persist_exam_response(db, db_attempt_id, step, items[step]["q"], selected)


def _practice_exam_answered_set(category: dict[str, Any], set_id: int) -> set[int]:
    set_answers = _practice_exam_answers(category).get(str(set_id), {})
    if not isinstance(set_answers, dict):
        return set()
    out: set[int] = set()
    for key, value in set_answers.items():
        if value:
            try:
                out.add(int(key))
            except (TypeError, ValueError):
                pass
    return out


def _word_problem_answers() -> dict[str, dict[str, str]]:
    return _practice_exam_answers(_practice_exam_category_or_404("word-problems"))


def _save_word_problem_answer(set_id: int, step: int, selected: str) -> None:
    _save_practice_exam_answer(_practice_exam_category_or_404("word-problems"), set_id, step, selected)


def _word_problem_answered_set(set_id: int) -> set[int]:
    return _practice_exam_answered_set(_practice_exam_category_or_404("word-problems"), set_id)


def _practice_exam_category_context(category: dict[str, Any]) -> dict[str, Any]:
    sets = _practice_exam_sets(category)
    total_questions = 44 if category.get("is_random_test") else len(_practice_exam_bank(category))
    domain_counts: dict[str, int] = defaultdict(int)
    unit_counts: dict[str, int] = defaultdict(int)
    for s in sets:
        for item in s["items"]:
            domain_counts[item["domain"]] += 1
            unit_counts[item["unit_label"]] += 1
    category = dict(category)
    category.update(
        {
            "sets": sets,
            "total_questions": total_questions,
            "set_count": 2 if category.get("is_random_test") else len(sets),
            "set_size": WORD_PROBLEM_SET_SIZE,
            "time_limit_minutes": WORD_PROBLEM_SECONDS // 60,
            "domain_counts": sorted(domain_counts.items()),
            "unit_counts": sorted(unit_counts.items(), key=lambda kv: _exam_unit_sort_key(kv[0])),
            "start_href": url_for("practice_exam_question", category_slug=category["slug"], set_id=1, step=0) if sets else "#",
            "category_href": url_for("practice_random_test_intro") if category.get("is_random_test") else (url_for("practice_exam_category", category_slug=category["slug"]) if category.get("is_live") else "#"),
            "status_label": category.get("status_label") or ("Live" if sets else "Empty"),
        }
    )
    return category


def _practice_exam_center_context() -> dict[str, Any]:
    categories = [_practice_exam_category_context(category) for category in _practice_exam_categories()]
    return {
        "categories": categories,
        "total_sets": sum(category["set_count"] for category in categories),
        "total_questions": sum(category["total_questions"] for category in categories),
        "set_size": WORD_PROBLEM_SET_SIZE,
        "time_limit_minutes": WORD_PROBLEM_SECONDS // 60,
        "is_category_index": True,
    }


def _word_problem_exam_context() -> dict[str, Any]:
    category = _practice_exam_category_context(_practice_exam_category_or_404("word-problems"))
    return {
        "categories": [category],
        "sets": category["sets"],
        "total_sets": category["set_count"],
        "total_questions": category["total_questions"],
        "set_size": WORD_PROBLEM_SET_SIZE,
        "time_limit_minutes": WORD_PROBLEM_SECONDS // 60,
        "domain_counts": category["domain_counts"],
        "unit_counts": category["unit_counts"],
        "is_category_index": False,
    }


@app.route("/practice/exams/<category_slug>")
def practice_exam_category(category_slug: str):
    session["active_track_label"] = "SAT Math"
    if category_slug == "random-test":
        return redirect(url_for("practice_random_test_intro"))
    category = _practice_exam_category_context(_practice_exam_category_or_404(category_slug))
    return render_template(
        "word_problem_exams.html",
        categories=[category],
        total_sets=category["set_count"],
        total_questions=category["total_questions"],
        set_size=WORD_PROBLEM_SET_SIZE,
        time_limit_minutes=WORD_PROBLEM_SECONDS // 60,
        is_category_index=False,
    )


@app.route("/practice/exams/word-problems")
def practice_word_problem_exams():
    session["active_track_label"] = "SAT Math"
    return render_template("word_problem_exams.html", **_word_problem_exam_context())


@app.route("/practice/exams/random-test")
def practice_random_test_intro():
    session["active_track_label"] = "SAT Math"
    category = _practice_exam_category_context(_practice_exam_category_or_404("random-test"))
    raw_attempt = session.get(RANDOM_TEST_SESSION_KEY)
    has_active_attempt = isinstance(raw_attempt, dict) and bool(raw_attempt.get("seed"))
    return render_template(
        "random_test_intro.html",
        category=category,
        module_targets=RANDOM_TEST_UNIT_TARGETS,
        module_minutes=WORD_PROBLEM_SECONDS // 60,
        has_active_attempt=has_active_attempt,
        continue_href=_random_test_continue_href() if has_active_attempt else None,
    )


@app.route("/practice/exams/random-test/start", methods=["POST"])
def practice_random_test_start():
    seed = str(random.randrange(10**9, 10**10))
    session[RANDOM_TEST_SESSION_KEY] = {"seed": seed, "answers": {}, "deadlines": {}}
    session.modified = True
    return redirect(url_for("practice_random_test_question", module_id=1, step=0))


@app.route("/practice/exams/random-test/module/<int:module_id>/<int:step>")
def practice_random_test_question(module_id: int, step: int):
    session["active_track_label"] = "SAT Math"
    if module_id not in (1, 2):
        abort(404)
    attempt = _random_test_attempt()
    modules = _random_test_modules(str(attempt["seed"]))
    items = modules[module_id]
    if not items:
        abort(404)
    step = max(0, min(step, len(items) - 1))
    item = items[step]
    q = item["q"]
    category = _practice_exam_category_context(_practice_exam_category_or_404("random-test"))
    answered_qset = _random_test_answered_set(module_id)
    answered_count = len(answered_qset)
    return render_template(
        "word_problem_exam_question.html",
        category=category,
        category_slug="random-test",
        set_id=module_id,
        set_count=2,
        item=item,
        q=_sanitize_question_for_render(q),
        step=step,
        total=len(items),
        answered_qset=answered_qset,
        answered_count=answered_count,
        answered_pct=min(100, round(100 * answered_count / len(items))) if items else 0,
        choice_letters=[chr(ord("A") + i) for i in range(len(q.get("choices") or []))],
        time_limit_seconds=WORD_PROBLEM_SECONDS,
        deadline_ms=_random_test_deadline_ms(module_id),
        is_random_test=True,
        random_test_module=module_id,
        back_href=url_for("practice_random_test_intro"),
        back_label="SAT Math Test",
        prev_href=url_for("practice_random_test_question", module_id=module_id, step=step - 1) if step > 0 else None,
        next_href=url_for("practice_random_test_question", module_id=module_id, step=step + 1) if step < len(items) - 1 else None,
        form_action=url_for("practice_random_test_submit", module_id=module_id),
        submit_final_label="Finish Module 1" if module_id == 1 else "Submit test",
        submit_next_label="Save & next",
    )


@app.route("/practice/exams/random-test/module/<int:module_id>/submit", methods=["POST"])
def practice_random_test_submit(module_id: int):
    if module_id not in (1, 2):
        abort(404)
    attempt = _random_test_attempt()
    modules = _random_test_modules(str(attempt["seed"]))
    total = len(modules[module_id])
    try:
        step = int(request.form.get("step") or 0)
    except ValueError:
        step = 0
    step = max(0, min(step, max(0, total - 1)))
    raw_answer = (request.form.get("selected_answer") or "").strip().upper()[:1]
    if not raw_answer:
        flash("Please select an answer before continuing.")
        return redirect(url_for("practice_random_test_question", module_id=module_id, step=step))
    _save_random_test_answer(module_id, step, raw_answer)
    if step >= total - 1:
        if module_id == 1:
            return redirect(url_for("practice_random_test_question", module_id=2, step=0))
        return redirect(url_for("practice_random_test_done"))
    return redirect(url_for("practice_random_test_question", module_id=module_id, step=step + 1))


@app.route("/practice/exams/random-test/done")
def practice_random_test_done():
    attempt = _random_test_attempt()
    modules = _random_test_modules(str(attempt["seed"]))
    answers = attempt.get("answers", {})
    review: list[dict[str, Any]] = []
    module_results: list[dict[str, Any]] = []
    unit_stats: dict[str, dict[str, Any]] = {
        "unit1": {"key": "unit1", "label": "Unit 1", "title": "Algebra", "correct": 0, "total": 0},
        "unit2": {"key": "unit2", "label": "Unit 2", "title": "Advanced Math", "correct": 0, "total": 0},
        "unit3": {"key": "unit3", "label": "Unit 3", "title": "Problem Solving & Data", "correct": 0, "total": 0},
        "unit4": {"key": "unit4", "label": "Unit 4", "title": "Geometry", "correct": 0, "total": 0},
    }
    total_correct = 0
    total_questions = 0
    for module_id in (1, 2):
        module_answers = answers.get(str(module_id), {}) if isinstance(answers, dict) else {}
        if not isinstance(module_answers, dict):
            module_answers = {}
        module_correct = 0
        for idx, item in enumerate(modules[module_id]):
            q = item["q"]
            selected = str(module_answers.get(str(idx)) or "")
            key = str(q.get("correct_answer") or "")
            is_correct = response_is_correct(q, selected) is True if selected else False
            unit_key = str(item.get("unit_key") or _word_problem_unit_key(item))
            if unit_key in unit_stats:
                unit_stats[unit_key]["total"] += 1
                if is_correct:
                    unit_stats[unit_key]["correct"] += 1
            if is_correct:
                module_correct += 1
                total_correct += 1
            total_questions += 1
            review.append(
                {
                    "module_id": module_id,
                    "index": idx,
                    "item": item,
                    "selected": selected or "—",
                    "key": key or "—",
                    "is_correct": is_correct,
                    "href": url_for("practice_random_test_question", module_id=module_id, step=idx),
                }
            )
        module_results.append(
            {
                "module_id": module_id,
                "source": "Specialized Training" if module_id == 1 else "Hard Problem Drill",
                "correct": module_correct,
                "total": len(modules[module_id]),
                "accuracy": round(100 * module_correct / len(modules[module_id])) if modules[module_id] else 0,
                "wrong": len(modules[module_id]) - module_correct,
            }
        )
    unit_results: list[dict[str, Any]] = []
    for stat in unit_stats.values():
        total = int(stat["total"] or 0)
        correct = int(stat["correct"] or 0)
        stat["wrong"] = total - correct
        stat["accuracy"] = round(100 * correct / total) if total else 0
        unit_results.append(stat)
    weakest_unit = min(
        (unit for unit in unit_results if unit["total"]),
        key=lambda unit: (unit["accuracy"], -unit["wrong"]),
        default=None,
    )
    score = _random_test_score(total_correct)
    raw_accuracy = round(100 * total_correct / total_questions) if total_questions else 0
    score_pct = round(100 * (score - 200) / 600) if score >= 200 else 0
    module_gap = abs(int(module_results[0]["correct"]) - int(module_results[1]["correct"])) if len(module_results) == 2 else 0
    score_band = "Advanced" if score >= 700 else ("On Track" if score >= 600 else ("Building" if score >= 500 else "Needs Focus"))
    exam_meta = {
        "category_slug": "random-test",
        "seed": str(attempt.get("seed") or ""),
        "score": score,
        "total_correct": total_correct,
        "total_questions": total_questions,
        "raw_accuracy": raw_accuracy,
        "score_band": score_band,
    }
    session_summary_href = None
    uid = session.get("user_id")
    if uid:
        db = get_db()
        db_attempt_id = _persist_random_test_exam_to_db(
            db,
            uid,
            str(attempt.get("seed") or ""),
            modules,
            answers,
            exam_meta,
        )
        if db_attempt_id:
            session_summary_href = url_for("practice_session_summary", attempt_id=db_attempt_id)
    return render_template(
        "random_test_done.html",
        score=score,
        score_pct=max(0, min(100, score_pct)),
        score_band=score_band,
        total_correct=total_correct,
        total_questions=total_questions,
        raw_accuracy=raw_accuracy,
        module_results=module_results,
        module_gap=module_gap,
        unit_results=unit_results,
        weakest_unit=weakest_unit,
        target_600=max(0, 600 - score),
        target_700=max(0, 700 - score),
        review=review,
        session_summary_href=session_summary_href,
    )


@app.route("/practice/exams/<category_slug>/set/<int:set_id>/<int:step>")
def practice_exam_question(category_slug: str, set_id: int, step: int):
    session["active_track_label"] = "SAT Math"
    category, exam_set = _practice_exam_set_or_404(category_slug, set_id)
    category = _practice_exam_category_context(category)
    items = exam_set["items"]
    if not items:
        abort(404)
    step = max(0, min(step, len(items) - 1))
    item = items[step]
    q = item["q"]
    answered_qset = _practice_exam_answered_set(category, set_id)
    answered_count = len(answered_qset)
    return render_template(
        "word_problem_exam_question.html",
        category=category,
        category_slug=category_slug,
        set_id=set_id,
        set_count=category["set_count"],
        item=item,
        q=_sanitize_question_for_render(q),
        step=step,
        total=len(items),
        answered_qset=answered_qset,
        answered_count=answered_count,
        answered_pct=min(100, round(100 * answered_count / len(items))) if items else 0,
        choice_letters=[chr(ord("A") + i) for i in range(len(q.get("choices") or []))],
        time_limit_seconds=WORD_PROBLEM_SECONDS,
    )


@app.route("/practice/exams/word-problems/set/<int:set_id>/<int:step>")
def practice_word_problem_question(set_id: int, step: int):
    return practice_exam_question("word-problems", set_id, step)


@app.route("/practice/exams/<category_slug>/set/<int:set_id>/submit", methods=["POST"])
def practice_exam_submit(category_slug: str, set_id: int):
    category, exam_set = _practice_exam_set_or_404(category_slug, set_id)
    total = len(exam_set["items"])
    try:
        step = int(request.form.get("step") or 0)
    except ValueError:
        step = 0
    step = max(0, min(step, max(0, total - 1)))
    raw_answer = (request.form.get("selected_answer") or "").strip().upper()[:1]
    if not raw_answer:
        flash("Please select an answer before continuing.")
        return redirect(url_for("practice_exam_question", category_slug=category_slug, set_id=set_id, step=step))
    _save_practice_exam_answer(category, set_id, step, raw_answer)
    if step >= total - 1:
        return redirect(url_for("practice_exam_done", category_slug=category_slug, set_id=set_id))
    return redirect(url_for("practice_exam_question", category_slug=category_slug, set_id=set_id, step=step + 1))


@app.route("/practice/exams/word-problems/set/<int:set_id>/submit", methods=["POST"])
def practice_word_problem_submit(set_id: int):
    return practice_exam_submit("word-problems", set_id)


@app.route("/practice/exams/<category_slug>/set/<int:set_id>/done")
def practice_exam_done(category_slug: str, set_id: int):
    category, exam_set = _practice_exam_set_or_404(category_slug, set_id)
    category = _practice_exam_category_context(category)
    answers = _practice_exam_answers(category).get(str(set_id), {})
    if not isinstance(answers, dict):
        answers = {}
    review: list[dict] = []
    correct = 0
    for idx, item in enumerate(exam_set["items"]):
        q = item["q"]
        selected = str(answers.get(str(idx)) or "")
        key = str(q.get("correct_answer") or "")
        is_correct = response_is_correct(q, selected) is True if selected else False
        if is_correct:
            correct += 1
        review.append(
            {
                "index": idx,
                "item": item,
                "selected": selected or "—",
                "key": key or "—",
                "is_correct": is_correct,
                "href": url_for("practice_exam_question", category_slug=category_slug, set_id=set_id, step=idx),
            }
        )
    total = len(exam_set["items"])
    exam_meta = {
        "category_slug": category_slug,
        "set_id": set_id,
        "correct": correct,
        "total": total,
        "accuracy": round(100 * correct / total) if total else 0,
    }
    session_summary_href = None
    uid = session.get("user_id")
    if uid:
        db = get_db()
        db_attempt_id = _persist_category_exam_to_db(
            db,
            uid,
            category_slug,
            set_id,
            exam_set["items"],
            answers,
            exam_meta,
        )
        if db_attempt_id:
            session_summary_href = url_for("practice_session_summary", attempt_id=db_attempt_id)
    return render_template(
        "word_problem_exam_done.html",
        category=category,
        category_slug=category_slug,
        set_id=set_id,
        word_set=exam_set,
        total=total,
        correct=correct,
        accuracy=round(100 * correct / total) if total else 0,
        review=review,
        next_set_href=url_for("practice_exam_question", category_slug=category_slug, set_id=set_id + 1, step=0)
        if set_id < category["set_count"] else None,
        session_summary_href=session_summary_href,
    )


@app.route("/practice/exams/word-problems/set/<int:set_id>/done")
def practice_word_problem_done(set_id: int):
    return practice_exam_done("word-problems", set_id)


@app.route("/practice/analytics")
def practice_analytics():
    session["active_track_label"] = "SAT Math"
    db = get_db()
    uid = session.get("user_id")
    all_rows = _analytics_wrong_rows(db, uid)
    rows = [
        row for row in all_rows
        if row.get("domain") in {"algebra", "advanced_math", "problem_solving", "geometry", "hard_problem"}
    ]
    tag_totals: Dict[str, int] = defaultdict(int)
    for row in rows:
        for lab in row["tag_labels"]:
            tag_totals[lab] += 1
    top_tags = sorted(tag_totals.items(), key=lambda x: -x[1])[:8]
    classifier = _build_mistake_classifier(rows)
    unit_targets = [
        ("unit1", "Unit 1", "Algebra"),
        ("unit2", "Unit 2", "Advanced Math"),
        ("unit3", "Unit 3", "Problem Solving & Data"),
        ("unit4", "Unit 4", "Geometry"),
    ]
    unit_counts: Dict[str, int] = {key: 0 for key, _, _ in unit_targets}
    for row in rows:
        unit_label = str(row.get("analytics_unit_label") or "")
        for key, label, _subtitle in unit_targets:
            if unit_label.startswith(label):
                unit_counts[key] += 1
                break
    unit_total = sum(unit_counts.values())
    sat_unit_distribution = [
        {
            "id": key,
            "label": label,
            "subtitle": subtitle,
            "count": unit_counts.get(key, 0),
            "pct": round(100 * unit_counts.get(key, 0) / unit_total) if unit_total else 0,
            "href": url_for("practice_analytics", part=key),
            "is_active": False,
        }
        for key, label, subtitle in unit_targets
    ]
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
    selected_part_id = (request.args.get("part") or "sat").strip().lower()
    selected_partition = _analytics_partition_by_id(analytics_partitions, selected_part_id)
    if selected_partition is None and analytics_partitions:
        selected_partition = analytics_partitions[0]
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
    unit_label_by_part = {key: label for key, label, _subtitle in unit_targets}
    active_part_id = selected_part_id if selected_part_id in unit_label_by_part else (
        str(selected_partition.get("id") or "") if selected_partition else "sat"
    )
    visible_wrong_rows = rows
    if active_part_id in unit_label_by_part:
        unit_label = unit_label_by_part[active_part_id]
        visible_wrong_rows = [
            r for r in rows
            if str(r.get("analytics_unit_label") or "").startswith(unit_label)
        ]
    elif selected_partition and not selected_partition.get("sat_children"):
        visible_ids = {r.get("pr_id") for r in loop_rows}
        visible_wrong_rows = [r for r in rows if r.get("pr_id") in visible_ids]
    for item in sat_unit_distribution:
        item["is_active"] = item["id"] == active_part_id
    return render_template(
        "practice_analytics.html",
        wrong_rows=rows,
        visible_wrong_rows=visible_wrong_rows,
        wrong_total=len(rows),
        visible_wrong_total=len(visible_wrong_rows),
        sat_unit_distribution=sat_unit_distribution,
        top_mistake_tags=top_tags,
        top_tags_viz=top_tags_viz,
        mistake_tag_options=MISTAKE_TAG_OPTIONS,
        classifier=active_classifier,
        analytics_partitions=analytics_partitions,
        selected_partition=selected_partition,
        active_analytics_part=active_part_id,
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
              AND (? = 1 OR pa.user_id = ?)
            """,
            (
                attempt_id,
                q_index,
                domain,
                topic,
                1 if current_user_can_access_admin() else 0,
                session.get("user_id"),
            ),
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
          AND (? = 1 OR pa.user_id = ?)
        """,
        (
            attempt_id,
            q_index,
            domain,
            topic,
            1 if current_user_can_access_admin() else 0,
            session.get("user_id"),
        ),
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
        q=_sanitize_question_for_render(q),
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

    if domain == "placement":
        return redirect(url_for("placement_landing"))

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


def _visible_learning_tracks(grants: set[str] | None) -> list[dict[str, Any]]:
    if grants is None:
        return list(LEARNING_TRACKS)
    visible: list[dict[str, Any]] = []
    for track in LEARNING_TRACKS:
        key = track.get("key")
        if key == "sat" and "sat" in grants:
            visible.append(track)
        elif key == "placement" and "placement" in grants:
            visible.append(track)
    return visible


def _exam_topic(category_slug: str, *, set_id: int | None = None, seed: str | None = None) -> str:
    if category_slug == "random-test":
        return f"seed_{seed or 'unknown'}"
    return f"set_{int(set_id or 0)}"


def _exam_db_attempt_cache_key(category_slug: str, topic: str) -> str:
    return f"{category_slug}:{topic}"


def _get_exam_db_attempt_id(
    category_slug: str, *, set_id: int | None = None, seed: str | None = None
) -> int | None:
    topic = _exam_topic(category_slug, set_id=set_id, seed=seed)
    cache = session.get(EXAM_DB_ATTEMPT_IDS_KEY)
    if isinstance(cache, dict):
        raw = cache.get(_exam_db_attempt_cache_key(category_slug, topic))
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    if category_slug == "random-test":
        attempt = session.get(RANDOM_TEST_SESSION_KEY)
        if isinstance(attempt, dict) and attempt.get("db_attempt_id"):
            try:
                return int(attempt["db_attempt_id"])
            except (TypeError, ValueError):
                pass
    return None


def _set_exam_db_attempt_id(category_slug: str, topic: str, attempt_id: int) -> None:
    cache = session.get(EXAM_DB_ATTEMPT_IDS_KEY)
    if not isinstance(cache, dict):
        cache = {}
    cache[_exam_db_attempt_cache_key(category_slug, topic)] = attempt_id
    session[EXAM_DB_ATTEMPT_IDS_KEY] = cache
    if category_slug == "random-test":
        attempt = session.get(RANDOM_TEST_SESSION_KEY)
        if not isinstance(attempt, dict):
            attempt = {}
        attempt["db_attempt_id"] = attempt_id
        session[RANDOM_TEST_SESSION_KEY] = attempt
    session.modified = True


def _ensure_exam_db_attempt(
    db: sqlite3.Connection,
    user_id: Any,
    category_slug: str,
    *,
    set_id: int | None = None,
    seed: str | None = None,
) -> int | None:
    if not user_id:
        return None
    domain = EXAM_DOMAIN_BY_SLUG.get(category_slug)
    if not domain:
        return None
    topic = _exam_topic(category_slug, set_id=set_id, seed=seed)
    existing = _get_exam_db_attempt_id(category_slug, set_id=set_id, seed=seed)
    if existing:
        row = db.execute(
            """
            SELECT id FROM practice_attempts
            WHERE id = ? AND user_id = ? AND domain = ? AND topic = ?
            """,
            (existing, user_id, domain, topic),
        ).fetchone()
        if row:
            return int(row["id"])
    attempt_id = _insert_practice_attempt(db, user_id, domain, topic, 0)
    _set_exam_db_attempt_id(category_slug, topic, attempt_id)
    return attempt_id


def _persist_exam_response(
    db: sqlite3.Connection, attempt_id: int, question_index: int, question: dict, selected: str
) -> None:
    is_correct, correct_answer = grade_for_db(question, selected)
    db.execute(
        "DELETE FROM practice_responses WHERE attempt_id = ? AND question_index = ?",
        (attempt_id, question_index),
    )
    db.execute(
        """
        INSERT INTO practice_responses
        (attempt_id, question_index, selected_answer, correct_answer, is_correct)
        VALUES (?, ?, ?, ?, ?)
        """,
        (attempt_id, question_index, selected, correct_answer, is_correct),
    )
    _safe_db_commit(db)


def _finalize_exam_db_attempt(db: sqlite3.Connection, attempt_id: int, meta: dict[str, Any]) -> None:
    db.execute(
        "UPDATE practice_attempts SET exam_meta_json = ? WHERE id = ?",
        (json.dumps(meta, separators=(",", ":")), attempt_id),
    )
    _safe_db_commit(db)


def _random_test_question_index(module_id: int, step: int) -> int:
    return (module_id - 1) * WORD_PROBLEM_SET_SIZE + step


def _random_test_question_at(
    module_id: int, step: int, seed: str
) -> tuple[dict[str, Any] | None, int | None]:
    modules = _random_test_modules(seed)
    items = modules.get(module_id) or []
    if step < 0 or step >= len(items):
        return None, None
    return items[step]["q"], _random_test_question_index(module_id, step)


def _exam_attempt_label(domain: str, topic: str, exam_meta_json: str | None = None) -> str:
    meta: dict[str, Any] = {}
    if exam_meta_json:
        try:
            parsed = json.loads(exam_meta_json)
            if isinstance(parsed, dict):
                meta = parsed
        except json.JSONDecodeError:
            pass
    if domain == "exam_random_test":
        score = meta.get("score")
        return f"Random Test · {score}/800" if score else "Random Test"
    if domain == "exam_word_problems":
        set_id = topic.replace("set_", "") if topic.startswith("set_") else topic
        acc = meta.get("accuracy")
        return f"Word Problem exam · Set {set_id}" + (f" · {acc}%" if acc is not None else "")
    if domain == "exam_unit_bank":
        set_id = topic.replace("set_", "") if topic.startswith("set_") else topic
        acc = meta.get("accuracy")
        return f"Unit bank exam · Set {set_id}" + (f" · {acc}%" if acc is not None else "")
    return TOPIC_TITLES.get(topic, topic)


def _persist_random_test_exam_to_db(
    db: sqlite3.Connection,
    user_id: Any,
    seed: str,
    modules: dict[int, list[dict]],
    answers: dict[str, Any],
    meta: dict[str, Any],
) -> int | None:
    attempt_id = _ensure_exam_db_attempt(db, user_id, "random-test", seed=seed)
    if not attempt_id:
        return None
    for module_id in (1, 2):
        module_answers = answers.get(str(module_id), {}) if isinstance(answers, dict) else {}
        if not isinstance(module_answers, dict):
            module_answers = {}
        for idx, item in enumerate(modules.get(module_id) or []):
            selected = str(module_answers.get(str(idx)) or "")
            if not selected:
                continue
            qi = _random_test_question_index(module_id, idx)
            _persist_exam_response(db, attempt_id, qi, item["q"], selected)
    _finalize_exam_db_attempt(db, attempt_id, meta)
    return attempt_id


def _persist_category_exam_to_db(
    db: sqlite3.Connection,
    user_id: Any,
    category_slug: str,
    set_id: int,
    items: list[dict],
    answers: dict[str, str],
    meta: dict[str, Any],
) -> int | None:
    attempt_id = _ensure_exam_db_attempt(db, user_id, category_slug, set_id=set_id)
    if not attempt_id:
        return None
    for idx, item in enumerate(items):
        selected = str(answers.get(str(idx)) or "")
        if not selected:
            continue
        _persist_exam_response(db, attempt_id, idx, item["q"], selected)
    _finalize_exam_db_attempt(db, attempt_id, meta)
    return attempt_id


def _hub_active_classroom(db: sqlite3.Connection) -> dict[str, Any] | None:
    row = db.execute(
        """
        SELECT lesson_slug, title, current_slide_index
        FROM course_class_sessions
        WHERE is_active = 1
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return None
    slug = str(row["lesson_slug"] or "")
    return {
        "slug": slug,
        "title": str(row["title"] or "Live class"),
        "slide": int(row["current_slide_index"] or 1),
        "lesson_href": url_for("practice_course_material_view", slug=slug),
        "classroom_href": url_for("practice_course_material_classroom", slug=slug)
        if current_user_can_access_admin()
        else None,
    }


def _hub_resume_practice_session(db: sqlite3.Connection, uid: int) -> dict[str, Any] | None:
    rows = db.execute(
        """
        SELECT pa.id, pa.domain, pa.topic,
               COUNT(pr.id) AS answered
        FROM practice_attempts pa
        LEFT JOIN practice_responses pr
          ON pr.attempt_id = pa.id AND pr.question_index IS NOT NULL
        WHERE pa.user_id = ?
          AND pa.domain NOT LIKE 'exam_%'
          AND pa.domain != 'placement'
        GROUP BY pa.id
        HAVING COUNT(pr.id) > 0
        ORDER BY pa.id DESC
        LIMIT 12
        """,
        (uid,),
    ).fetchall()
    for row in rows:
        domain = str(row["domain"] or "")
        topic = str(row["topic"] or "")
        tex_file = BANKS.get(domain, {}).get(topic)
        if not tex_file:
            continue
        questions = get_questions_for_topic(domain, topic, tex_file)
        total = len(questions)
        answered = int(row["answered"] or 0)
        if total > 0 and answered < total:
            return {
                "attempt_id": int(row["id"]),
                "domain": domain,
                "topic": topic,
                "topic_title": TOPIC_TITLES.get(topic, topic),
                "answered": answered,
                "total": total,
                "href": url_for("practice_question", domain=domain, topic=topic, qnum=0),
                "track_short": _dashboard_track_short(domain),
            }
    return None


def _practice_hub_context() -> dict[str, Any]:
    cm = load_course_materials()
    ctx: dict[str, Any] = {
        "cm_total": int(cm.get("total") or 0),
        "cm_ready": int(cm.get("available") or 0),
    }
    materials = list(cm.get("materials") or [])
    ready_materials = sorted(
        [m for m in materials if m.get("tex_available")],
        key=lambda m: tuple(
            int(p) if p.isdigit() else 0 for p in str(m.get("section") or "0").split(".")
        ),
    )
    user_progress: dict[str, dict[str, Any]] = {}
    uid = session.get("user_id")
    db = get_db()
    if uid:
        prog_rows = db.execute(
            "SELECT lesson_slug, progress_json FROM course_material_progress WHERE user_id = ?",
            (int(uid),),
        ).fetchall()
        for row in prog_rows:
            try:
                user_progress[str(row["lesson_slug"])] = json.loads(row["progress_json"] or "{}")
            except json.JSONDecodeError:
                continue
        for m in ready_materials:
            slug = str(m.get("slug") or "")
            prog = user_progress.get(slug) or {}
            m["user_mastery_pct"] = mastery_pct_from_progress(
                prog,
                int(m.get("slide_count") or 0),
                int(m.get("checkpoint_count") or 0),
            )
        ctx["resume_session"] = _hub_resume_practice_session(db, int(uid))
        rt_row = db.execute(
            """
            SELECT exam_meta_json FROM practice_attempts
            WHERE user_id = ? AND domain = 'exam_random_test' AND exam_meta_json IS NOT NULL
            ORDER BY id DESC LIMIT 1
            """,
            (int(uid),),
        ).fetchone()
        if rt_row and rt_row["exam_meta_json"]:
            try:
                rt_meta = json.loads(rt_row["exam_meta_json"])
                if isinstance(rt_meta, dict) and rt_meta.get("score"):
                    ctx["latest_random_test_score"] = int(rt_meta["score"])
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
    ctx["continue_material"] = _pick_continue_material(ready_materials, user_progress)
    ctx["live_classroom"] = _hub_active_classroom(db)
    rt_attempt = session.get(RANDOM_TEST_SESSION_KEY)
    if isinstance(rt_attempt, dict) and rt_attempt.get("seed"):
        seed = str(rt_attempt["seed"])
        modules = _random_test_modules(seed)
        answers = rt_attempt.get("answers", {})
        answered = 0
        total = sum(len(modules.get(mid) or []) for mid in (1, 2))
        for module_id in (1, 2):
            module_answers = answers.get(str(module_id), {}) if isinstance(answers, dict) else {}
            if isinstance(module_answers, dict):
                answered += sum(1 for v in module_answers.values() if v)
        if answered > 0 and answered < total:
            ctx["random_test_continue"] = {
                "answered": answered,
                "total": total,
                "href": _random_test_continue_href(),
            }
    return ctx


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
        q=_sanitize_question_for_render(q),
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
        practice_timer_mode="elapsed",
        pace_training=False,
        pace_seconds=0,
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
    _persist_miss_quiz_run(
        db,
        session.get("user_id"),
        label=str(pack.get("label") or "Miss quiz"),
        scope_part_id=str(module_part_id) if module_part_id else None,
        total=total,
        correct_n=correct_n,
        pct=pct,
        passed=quiz_passed,
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
    _persist_miss_quiz_run(
        db,
        session.get("user_id"),
        label=str(pack.get("label") or TOPIC_TITLES.get(topic, topic)),
        scope_part_id=MISS_PART_BY_DOMAIN.get(domain),
        total=total,
        correct_n=correct_n,
        pct=pct,
        passed=quiz_passed,
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

    if domain == "placement" and _placement_flow_config(topic):
        gate_href = _placement_section_gate_redirect(topic, question_index)
        if gate_href:
            return redirect(gate_href)

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
            if row is not None and not _attempt_user_matches(db, int(row["id"]), user_id):
                session.pop(sk, None)
                session.modified = True
                row = None
                attempt_id = None
        if row is None:
            if domain == "placement" and not _placement_profile_from_session()[0]:
                flash("Please complete the student information before starting the diagnostic.")
                slug = _placement_slug_for_topic(topic)
                return redirect(url_for("placement_test_start", slug=slug))
            resumed_id = _resume_incomplete_attempt_id(
                db, user_id, domain, topic, len(questions)
            )
            if resumed_id is not None:
                attempt_id = resumed_id
                session[sk] = attempt_id
                session.modified = True
            else:
                attempt_id = None
                session.pop(sk, None)
                session.modified = True
        else:
            attempt_id = int(row["id"])
            _backfill_placement_student_profile(db, attempt_id, domain)

    if domain == "placement" and attempt_id is None and _placement_profile_from_session()[0]:
        attempt_id = _insert_practice_attempt(
            db, user_id, domain, topic, question_index
        )
        session[sk] = attempt_id
        session.modified = True

    if attempt_id is not None:
        answered_rows = db.execute(
            """
            SELECT DISTINCT question_index FROM practice_responses
            WHERE attempt_id = ? AND question_index IS NOT NULL
            """,
            (attempt_id,),
        ).fetchall()
    else:
        answered_rows = []
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
    pace_seconds = None if mistake_redo_mode else _phase3_pace_seconds(domain, topic)
    if placement_mode:
        practice_timer_seconds = _placement_timer_seconds(topic)
        practice_timer_summary_url = (
            url_for("practice_session_summary", attempt_id=attempt_id)
            if attempt_id is not None
            else None
        )
        practice_timer_mode = "countdown"
    elif pace_seconds:
        practice_timer_seconds = int(pace_seconds)
        practice_timer_summary_url = None
        practice_timer_mode = "per_question"
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

    tracked_responses_hint = None
    if domain != "placement" and not mistake_redo_mode:
        graded_row = db.execute(
            """
            SELECT COUNT(*) AS c FROM practice_responses
            WHERE attempt_id = ? AND is_correct IN (0, 1)
            """,
            (attempt_id,),
        ).fetchone()
        graded_count = int(graded_row["c"] or 0) if graded_row else 0
        if graded_count < MIN_TRACKED_SAT_RESPONSES:
            remaining = MIN_TRACKED_SAT_RESPONSES - graded_count
            tracked_responses_hint = (
                f"Answer {remaining} more question{'s' if remaining != 1 else ''} "
                f"in this set before mistakes count toward your error log."
            )

    placement_clear_storage = bool(
        placement_mode and attempt_id is not None and answered_count == 0
    )

    return render_template(
        "practice_question.html",
        q=_sanitize_question_for_render(q),
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
        pace_training=bool(pace_seconds),
        pace_seconds=int(pace_seconds or 0),
        attempt_started_unix=attempt_started_unix,
        miss_quiz_mode=False,
        miss_quiz_v2=False,
        mistake_redo_mode=mistake_redo_mode,
        mistake_return_href=mistake_return_href,
        mistake_analytics_part=analytics_part_q,
        mistake_miss_anchor=miss_anchor_q,
        tracked_responses_hint=tracked_responses_hint,
        placement_clear_storage=placement_clear_storage,
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
    elif q_kind in ("constructed_response", "free_response"):
        selected_answer = raw_answer.strip()
        if not selected_answer:
            flash("Please enter your answer before continuing.")
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

    try:
        # If attempt_id is missing/invalid/nonexistent, create a fallback attempt row.
        attempt_exists = None
        if attempt_id is not None:
            attempt_exists = db.execute(
                "SELECT id FROM practice_attempts WHERE id = ?",
                (attempt_id,),
            ).fetchone()
            if attempt_exists is not None and not _attempt_user_matches(
                db, attempt_id, session.get("user_id")
            ):
                session.pop(_practice_session_key(domain, topic), None)
                session.modified = True
                attempt_exists = None
                attempt_id = None

        if attempt_id is None or attempt_exists is None:
            user_id = session.get("user_id")
            attempt_id = _insert_practice_attempt(db, user_id, domain, topic, q_index)

        graded_before = _attempt_graded_count(db, attempt_id)
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
        _apply_practice_mistake_progress(
            db,
            lk,
            attempt_id,
            domain,
            topic,
            q_index,
            is_correct,
            mistake_redo=mistake_redo,
            graded_before=graded_before,
        )
        if not _safe_db_commit(db):
            flash("The server was busy and could not save your answer. Please submit again.")
            return _practice_redirect(
                domain,
                topic,
                qnum_for_redirect,
                mistake_redo=mistake_redo,
                analytics_part=analytics_part_f,
                miss_anchor=miss_anchor_f,
            )
        if domain != "placement" and not mistake_redo:
            sk = _practice_session_key(domain, topic)
            session[sk] = attempt_id
            session.modified = True
            _maybe_flash_tracking_hint(db, attempt_id)
    except Exception:
        app.logger.exception(
            "submit_practice_answer failed domain=%s topic=%s qnum=%s attempt=%s",
            domain,
            topic,
            q_index,
            attempt_id_raw,
        )
        flash("Could not save your answer due to a temporary error. Please try again.")
        return _practice_redirect(
            domain,
            topic,
            qnum_for_redirect,
            mistake_redo=mistake_redo,
            analytics_part=analytics_part_f,
            miss_anchor=miss_anchor_f,
        )

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
        flow = _placement_flow_config(topic) if domain == "placement" else None
        if flow and flow.get("has_gates"):
            slug = _placement_slug_for_topic(topic)
            if flow.get("gate_kind") == "middle_parts":
                for gate in MIDDLE_LEVEL_PART_GATES:
                    if q_index == int(gate["after_q_index"]):
                        return redirect(
                            url_for(
                                "placement_section_intro",
                                slug=slug,
                                section=str(gate["section"]),
                            )
                        )
            elif flow.get("gate_kind") == "upper_gates":
                for gate in _upper_placement_gate_gates():
                    if q_index == int(gate["after_q_index"]):
                        return redirect(
                            url_for(
                                "placement_section_intro",
                                slug=slug,
                                section=str(gate["section"]),
                            )
                        )
            else:
                mc = int(flow["mc_count"])
                graph = int(flow["graph_count"])
                if q_index == mc - 1:
                    return redirect(
                        url_for("placement_section_intro", slug=slug, section="graphing")
                    )
                if q_index == mc + graph - 1:
                    return redirect(
                        url_for(
                            "placement_section_intro", slug=slug, section="free_response"
                        )
                    )
        return redirect(
            url_for("practice_question", domain=domain, topic=topic, qnum=q_index + 1)
        )

    sk = _practice_session_key(domain, topic)
    session[sk] = attempt_id
    session.modified = True
    return redirect(url_for("practice_session_summary", attempt_id=attempt_id))


def _exam_session_summary_payload(
    attempt_id: int, att: sqlite3.Row, db: sqlite3.Connection
) -> dict[str, Any]:
    domain = str(att["domain"] or "")
    topic = str(att["topic"] or "")
    exam_meta: dict[str, Any] = {}
    try:
        raw_meta = att["exam_meta_json"]
    except (KeyError, IndexError, TypeError):
        raw_meta = None
    if raw_meta:
        try:
            parsed = json.loads(raw_meta)
            if isinstance(parsed, dict):
                exam_meta = parsed
        except json.JSONDecodeError:
            pass

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

    rows_out: List[dict] = []
    correct_count = 0
    for r in resp_rows:
        qi = int(r["question_index"])
        yours_raw = (r["selected_answer"] or "").strip()
        key_display = (r["correct_answer"] or "").strip() or "—"
        is_correct = r["is_correct"]
        if is_correct == 1:
            status = "correct"
            correct_count += 1
        elif is_correct == 0:
            status = "incorrect"
        else:
            status = "nocheck"
        rows_out.append(
            {
                "q_index": qi,
                "q_display": str(qi + 1),
                "session_q": str(len(rows_out) + 1),
                "row_id": f"summary-q-{qi}",
                "knowledge_section": "—",
                "knowledge_title_en": "",
                "topic_detail": "",
                "hard_skill": "",
                "yours_display": yours_raw or "—",
                "key_display": key_display,
                "status": status,
                "explanation_en": "",
                "review_href": None,
            }
        )

    total_q = len(rows_out)
    if exam_meta.get("total"):
        total_q = max(total_q, int(exam_meta["total"]))
    if exam_meta.get("total_correct") is not None:
        correct_count = int(exam_meta["total_correct"])
    elif exam_meta.get("correct") is not None:
        correct_count = int(exam_meta["correct"])
    score_pct = round(100.0 * correct_count / total_q) if total_q else 0
    topic_title = _exam_attempt_label(domain, topic, att["exam_meta_json"] if "exam_meta_json" in att.keys() else None)
    skipped_count = sum(1 for row in rows_out if row["status"] == "skipped")
    mistake_focus = [row for row in rows_out if row["status"] == "incorrect"]

    render = {
        "domain": domain,
        "topic": topic,
        "topic_title": topic_title,
        "attempt_id": attempt_id,
        "rows": rows_out,
        "correct_count": correct_count,
        "total_q": total_q,
        "score_pct": score_pct,
        "answered_count": total_q - skipped_count,
        "answered_pct": (
            round(100 * correct_count / (total_q - skipped_count))
            if total_q - skipped_count > 0
            else None
        ),
        "session_duration_seconds": duration_seconds,
        "session_duration_label": _format_duration(duration_seconds),
        "section_stats": [],
        "placement_rec": None,
        "placement_brand": None,
        "placement_student": None,
        "celebrate_confetti": bool(score_pct >= 55),
        "mistake_focus": mistake_focus,
        "skipped_count": skipped_count,
        "miss_quiz_session_href": None,
        "miss_quiz_all_href": None,
        "miss_quiz_all_count": 0,
        "miss_quiz_all_is_module": False,
        "is_exam_summary": True,
        "exam_meta": exam_meta,
    }
    return {"render": render, "pdf_ctx": render}


def _practice_session_summary_payload(
    attempt_id: int, *, for_pdf: bool = False
) -> dict[str, Any] | tuple[str, int]:
    """Shared data for HTML summary and placement PDF export."""
    db = get_db()
    att = db.execute(
        """
        SELECT id, domain, topic, user_id, created_at, placement_student_name, placement_student_grade,
               placement_student_math_course, exam_meta_json
        FROM practice_attempts WHERE id = ?
        """,
        (attempt_id,),
    ).fetchone()
    if att is None:
        return ("Session not found", 404)
    if not _current_user_can_view_attempt(db, attempt_id):
        return ("Session not found", 404)

    domain = att["domain"]
    if str(domain or "").startswith("exam_"):
        return _exam_session_summary_payload(attempt_id, att, db)
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
            timer_cap = _placement_timer_seconds(topic)
            now_row = db.execute("SELECT CAST(strftime('%s', 'now') AS INTEGER) AS now_s").fetchone()
            if now_row is not None and now_row["now_s"] is not None:
                duration_seconds = min(timer_cap, max(0, int(now_row["now_s"]) - start_s))
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
            key_display = display_answer_plain(key) if key else "—"
        else:
            yours_raw = (r["selected_answer"] or "").strip()
            yours = yours_raw if yours_raw else "—"
            key_display = display_answer_plain(key if key else (r["correct_answer"] or "—"))
            if yours == "—":
                status = "skipped"
            elif not key:
                if qobj.get("question_kind") in ("constructed_response", "free_response"):
                    status = "submitted" if yours != "—" else "skipped"
                else:
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
    placement_gradable_total = sum(1 for q in questions if extract_correct_answer(q))
    placement_ungraded_count = max(0, total_q - placement_gradable_total)
    placement_mcq_correct = correct_count
    placement_mcq_total = total_q
    flow_cfg = _placement_flow_config(topic) if domain == "placement" else None
    if flow_cfg and flow_cfg.get("mc_scored"):
        mcq_rows = [
            (row, qobj)
            for row, qobj in zip(rows_out, questions)
            if qobj.get("question_kind") in ("mcq", "mcq5")
        ]
        placement_mcq_total = len(mcq_rows)
        placement_mcq_correct = sum(1 for row, _ in mcq_rows if row["status"] == "correct")
        # Enhanced Math course placement is MCQ-based; keep displayed % aligned.
        if placement_mcq_total:
            score_pct = round(100.0 * placement_mcq_correct / placement_mcq_total)
    elif domain == "placement" and placement_gradable_total:
        score_pct = round(100.0 * correct_count / placement_gradable_total)
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
    if domain == "placement" and topic == "enhanced_math_1":
        part_order = ("A", "B", "C", "G", "FR")
    elif domain == "placement" and topic == "enhanced_math_2":
        part_order = ("A", "B", "G", "FR")
    elif domain == "placement" and topic == "middle_level":
        part_order = ("I", "II", "III", "IV", "V")
    elif domain == "placement" and topic == "placement_full":
        part_order = ("1", "2", "3", "4", "5")
    elif domain == "placement":
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

    placement_meta = _load_placement_meta_file(topic if domain == "placement" else None)
    placement_rec = None
    placement_gate_scores: list[dict] = []
    placement_gate_rec: dict | None = None
    placement_brand: dict | None = None
    if domain == "placement":
        flow_cfg = _placement_flow_config(topic)
        rec_total = placement_mcq_total if flow_cfg and flow_cfg.get("mc_scored") else total_q
        rec_correct = placement_mcq_correct if flow_cfg and flow_cfg.get("mc_scored") else correct_count
        placement_rec = _placement_recommendation(
            placement_meta, rec_correct, rec_total, topic
        )
        if topic == "placement_full":
            placement_gate_scores = _placement_gate_scores_from_sections(
                section_stats, placement_meta
            )
            placement_gate_rec = _placement_gate_recommendation(
                placement_gate_scores, placement_meta
            )
            if placement_rec and placement_gate_rec:
                placement_rec = dict(placement_rec)
                placement_rec["gate_title"] = placement_gate_rec.get("title")
                placement_rec["gate_headline"] = placement_gate_rec.get("headline")
                placement_rec["gate_summary"] = placement_gate_rec.get("summary")
                placement_rec["gate_tier"] = placement_gate_rec.get("tier")
                placement_rec["gate_scores"] = placement_gate_scores
        b = placement_meta.get("brand")
        placement_brand = dict(b) if isinstance(b, dict) else None
        if placement_brand is not None:
            placement_brand.setdefault("report_title", "Official course placement report")
            if not placement_brand.get("trust_line"):
                placement_brand["trust_line"] = (
                    f"Score bands follow the printed {SITE_BRAND_NAME} placement guide."
                )
            if not placement_brand.get("trust_line_zh"):
                placement_brand["trust_line_zh"] = "分数区间与纸质分班测试官方说明一致。"

    placement_intelligent_report: dict | None = None

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

    placement_score_total = (
        placement_mcq_total
        if flow_cfg and flow_cfg.get("mc_scored") and placement_mcq_total
        else (
            placement_gradable_total
            if domain == "placement" and placement_gradable_total
            else total_q
        )
    )
    display_correct_count = (
        placement_mcq_correct
        if flow_cfg and flow_cfg.get("mc_scored") and placement_mcq_total
        else correct_count
    )
    render = {
        "domain": domain,
        "topic": topic,
        "topic_title": topic_title,
        "attempt_id": attempt_id,
        "rows": rows_out,
        "correct_count": display_correct_count,
        "total_q": total_q,
        "placement_gradable_total": placement_gradable_total if domain == "placement" else None,
        "placement_ungraded_count": placement_ungraded_count if domain == "placement" else None,
        "placement_score_total": placement_score_total if domain == "placement" else None,
        "score_pct": score_pct,
        "answered_count": total_q - skipped_count,
        "answered_pct": (
            round(100 * correct_count / (total_q - skipped_count))
            if total_q - skipped_count > 0
            else None
        ),
        "session_duration_seconds": duration_seconds,
        "session_duration_label": session_duration_label,
        "section_stats": section_stats,
        "placement_rec": placement_rec,
        "placement_gate_scores": placement_gate_scores,
        "placement_gate_rec": placement_gate_rec,
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
        "placement_gate_scores": placement_gate_scores,
        "placement_gate_rec": placement_gate_rec,
        "section_stats": section_stats,
        "placement_brand": placement_brand,
        "placement_student": placement_student,
        "correct_count": correct_count,
        "total_q": total_q,
        "placement_score_total": placement_score_total if domain == "placement" else total_q,
        "score_pct": score_pct,
        "session_duration_seconds": duration_seconds,
        "session_duration_label": session_duration_label,
        "topic_title": topic_title,
        "attempt_id": attempt_id,
        "intelligent_report": placement_intelligent_report,
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
    if not _current_user_can_view_attempt(db, attempt_id):
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
    key_display = display_answer_plain(correct_key) if correct_key else (
        display_answer_plain((resp["correct_answer"] or "").strip()) if resp else "—"
    )
    if resp is None:
        status = "skipped"
    elif not yours_raw:
        status = "skipped"
    elif not correct_key:
        if qobj.get("question_kind") in ("constructed_response", "free_response"):
            status = "submitted"
        else:
            status = "nocheck"
    else:
        graded = response_is_correct(qobj, yours_raw)
        if graded is True:
            status = "correct"
        elif graded is False:
            status = "incorrect"
        else:
            status = "nocheck"
    choice_letters = ["A", "B", "C", "D", "E"]
    result_choices: List[dict] = []
    kind = qobj.get("question_kind", "mcq")
    if kind in ("mcq", "mcq5") and qobj.get("choices"):
        max_letters = 5 if kind == "mcq5" else 4
        for j, html in enumerate(qobj["choices"]):
            if j >= max_letters:
                break
            letter = choice_letters[j]
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
    payload = _practice_session_summary_payload(attempt_id, for_pdf=True)
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
    except Exception:
        app.logger.exception("Bilingual placement PDF failed for attempt %s", attempt_id)
        pdf_ctx = dict(payload["pdf_ctx"])
        pdf_ctx.pop("intelligent_report", None)
        body = build_placement_parent_pdf(pdf_ctx)
    name = f"novelprep-placement-report-{attempt_id}.pdf"
    return Response(
        body,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.route("/placement/blank-test.pdf")
def placement_blank_test_pdf_legacy():
    return redirect(url_for("placement_blank_test_pdf", slug="upper-algebra-precalc"))


@app.route("/placement/<slug>/blank-test.pdf")
def placement_blank_test_pdf(slug: str):
    test = _placement_test_by_slug(slug)
    if not test or str(test.get("status") or "") != "available":
        abort(404)
    pdf_name = str(test.get("pdf_file") or "").strip()
    if not pdf_name:
        abort(404)
    path = os.path.join(APP_DIR, pdf_name)
    if not os.path.isfile(path):
        abort(404)
    safe_slug = slug.replace("-", "_")
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"NovelPrep-Placement-{safe_slug}-Blank.pdf",
    )


@app.route("/practice/<domain>/<topic>/new-session")
def practice_new_session(domain: str, topic: str):
    db = get_db()
    user_id = session.get("user_id")
    if user_id is not None and domain != "placement" and not domain.startswith("exam_"):
        latest = db.execute(
            """
            SELECT
                pa.id,
                SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded
            FROM practice_attempts pa
            LEFT JOIN practice_responses pr ON pr.attempt_id = pa.id
            WHERE pa.user_id = ? AND pa.domain = ? AND pa.topic = ?
            GROUP BY pa.id
            ORDER BY pa.id DESC
            LIMIT 1
            """,
            (user_id, domain, topic),
        ).fetchone()
        if latest:
            graded = int(latest["graded"] or 0)
            if 0 < graded < MIN_TRACKED_SAT_RESPONSES:
                flash(
                    f"Finish at least {MIN_TRACKED_SAT_RESPONSES} questions in your current set "
                    f"before starting a new one — short tries don't count toward mistake tracking."
                )
                return redirect(url_for("practice_question", domain=domain, topic=topic, qnum=0))
    session.pop(_practice_session_key(domain, topic), None)
    if domain == "placement":
        _clear_placement_profile_session()
        slug = _placement_slug_for_topic(topic)
        return redirect(url_for("placement_test_start", slug=slug))
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
        setup_token = os.environ.get("ADMIN_SETUP_TOKEN", "").strip()
        if setup_token:
            submitted = request.form.get("setup_token", "").strip()
            if not secrets.compare_digest(submitted, setup_token):
                flash("Invalid setup token.")
                return render_template(
                    "admin_setup.html",
                    setup_token_required=True,
                )

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

    return render_template(
        "admin_setup.html",
        setup_token_required=bool(os.environ.get("ADMIN_SETUP_TOKEN", "").strip()),
    )


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
            next_url = _safe_redirect_target(request.args.get("next") or "")
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
    scope_clause, scope_params = _staff_student_scope_clause(db)

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
            u.registered_by,
            COUNT(DISTINCT pa.id) AS attempts_total,
            COUNT(pr.id) AS responses_total,
            SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct_total,
            MAX(COALESCE(pr.submitted_at, pa.created_at)) AS last_activity
        FROM users u
        LEFT JOIN practice_attempts pa ON pa.user_id = u.id
        LEFT JOIN practice_responses pr ON pr.attempt_id = pa.id
        WHERE {" AND ".join(filters)}{scope_clause}
        GROUP BY u.id
        ORDER BY u.is_active DESC, last_activity DESC, u.created_at DESC
        """,
        tuple(params) + tuple(scope_params),
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
        SELECT id, username, role, is_active, created_at, last_login_at, student_view_scope
        FROM users
        WHERE role = ?
        ORDER BY is_active DESC, created_at DESC
        """,
        (ROLE_STAFF,),
    ).fetchall()
    out: List[dict] = []
    for row in rows:
        item = dict(row)
        scope = str(item.get("student_view_scope") or STAFF_VIEW_OWN).strip().lower()
        item["student_view_scope"] = scope if scope == STAFF_VIEW_ALL else STAFF_VIEW_OWN
        item["student_view_scope_label"] = (
            "All students" if item["student_view_scope"] == STAFF_VIEW_ALL else "Own students only"
        )
        out.append(item)
    return out


def _recent_record_rows(db: sqlite3.Connection) -> List[dict]:
    scope_clause, scope_params = _staff_student_scope_clause(db, "u")
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
            WHERE u.role = 'student'{scope_clause}
            GROUP BY pa.id
            ORDER BY COALESCE(last_submitted_at, pa.created_at) DESC
            LIMIT 100
            """,
            tuple(scope_params),
        ).fetchall()
    ]


def _cleanup_empty_practice_attempts(db: sqlite3.Connection) -> None:
    """Drop abandoned starts and short untracked spam sessions."""
    try:
        db.execute(
            """
            DELETE FROM practice_attempts
            WHERE id NOT IN (SELECT DISTINCT attempt_id FROM practice_responses)
              AND created_at < datetime('now', '-24 hours')
            """
        )
        db.execute(
            f"""
            DELETE FROM practice_attempts
            WHERE id IN (
                SELECT pa.id
                FROM practice_attempts pa
                LEFT JOIN practice_responses pr ON pr.attempt_id = pa.id
                WHERE pa.domain NOT IN ('placement')
                  AND pa.domain NOT LIKE 'exam_%'
                GROUP BY pa.id
                HAVING COUNT(pr.id) > 0
                  AND SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) < {MIN_TRACKED_SAT_RESPONSES}
                  AND COALESCE(MAX(pr.submitted_at), pa.created_at) < datetime('now', '-2 hours')
            )
            """
        )
        db.commit()
    except sqlite3.Error:
        pass


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


def _hard_drill_display_meta() -> dict[str, Any]:
    topics = sorted(BANKS.get("hard_problem", {}).keys(), key=_topic_bank_sort_key)
    numbers: list[int] = []
    for topic in topics:
        match = re.match(r"^hard_(\d+)$", topic)
        if match:
            numbers.append(int(match.group(1)))
    count = len(topics)
    if not numbers:
        return {"count": 0, "range_label": ""}
    if count == 15 and 15 not in numbers and 16 in numbers:
        range_label = "I–XIV + XVI"
    elif len(numbers) == 1:
        range_label = _int_to_roman(numbers[0])
    else:
        range_label = f"{_int_to_roman(min(numbers))}–{_int_to_roman(max(numbers))}"
    return {"count": count, "range_label": range_label}


def _activity_status_label(last_activity: str | None, *, quiet_days: int = 3) -> str:
    if not last_activity:
        return "inactive"
    try:
        dt = datetime.strptime(str(last_activity).strip()[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return "quiet"
    age = (datetime.now() - dt).days
    if age <= quiet_days:
        return "active"
    return "quiet"


def _maybe_flash_tracking_hint(db: sqlite3.Connection, attempt_id: int) -> None:
    row = db.execute(
        """
        SELECT COUNT(*) AS c FROM practice_responses
        WHERE attempt_id = ? AND is_correct IN (0, 1)
        """,
        (attempt_id,),
    ).fetchone()
    graded = int(row["c"] or 0) if row else 0
    if graded >= MIN_TRACKED_SAT_RESPONSES:
        flash("Session unlocked — this set now counts toward mistake analytics and session reports.")
        return
    remaining = MIN_TRACKED_SAT_RESPONSES - graded
    flash(
        f"Saved · {remaining} more answer{'s' if remaining != 1 else ''} needed "
        f"for this set to count in analytics."
    )


DIGEST_DEMO_USERNAME_RE = re.compile(r"^live\d+_s\d+$", re.I)


def _is_digest_demo_username(username: str) -> bool:
    u = (username or "").strip().lower()
    if DIGEST_DEMO_USERNAME_RE.match(u):
        return True
    if u.startswith("demo_") or u.endswith("_demo") or u.startswith("test_"):
        return True
    return False


def _digest_demo_user_ids(db: sqlite3.Connection) -> set[int]:
    rows = db.execute("SELECT id, username FROM users WHERE role = 'student'").fetchall()
    return {
        int(row["id"])
        for row in rows
        if _is_digest_demo_username(str(row["username"] or ""))
    }


def _digest_chapter_slice_label(domain: str, topic: str) -> str:
    section = next(
        (sec for dom, top, sec, _ in STUDENT_CHAPTER_SLICES if dom == domain and top == topic),
        topic,
    )
    title = TOPIC_TITLES.get(topic, topic)
    short_title = title.split(" – ", 1)[-1] if " – " in title else title
    if len(short_title) > 34:
        short_title = short_title[:32] + "…"
    return f"{section} · {short_title}"


def _digest_topic_short_label(topic: str) -> str:
    title = TOPIC_TITLES.get(topic, topic)
    if " – " in title:
        title = title.split(" – ", 1)[-1]
    if len(title) > 36:
        title = title[:34] + "…"
    return title


def _digest_student_recent_wrongs(
    db: sqlite3.Connection, user_id: int, days: int, *, limit: int = 10
) -> list[dict[str, Any]]:
    window_sql = f"-{int(days)} days"
    tracked_sql = _tracked_attempt_sql("pa")
    rows = db.execute(
        f"""
        SELECT
            pa.domain,
            pa.topic,
            pr.question_index,
            pr.selected_answer,
            pr.correct_answer,
            COALESCE(pr.submitted_at, pa.created_at) AS answered_at
        FROM practice_responses pr
        JOIN practice_attempts pa ON pa.id = pr.attempt_id
        WHERE pa.user_id = ?
          AND pr.is_correct = 0
          AND pr.question_index IS NOT NULL
          AND pa.domain NOT LIKE 'exam_%'
          AND pa.domain != 'placement'
          AND COALESCE(pr.submitted_at, pa.created_at) >= datetime('now', ?)
          AND {tracked_sql}
        ORDER BY answered_at DESC
        LIMIT ?
        """,
        (user_id, window_sql, max(limit * 3, limit)),
    ).fetchall()
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for row in rows:
        domain = str(row["domain"] or "")
        topic = str(row["topic"] or "")
        qi = int(row["question_index"])
        key = (domain, topic, qi)
        if key in seen:
            continue
        seen.add(key)
        selected = str(row["selected_answer"] or "").strip()
        correct = str(row["correct_answer"] or "").strip()
        out.append(
            {
                "label": f"{_digest_topic_short_label(topic)} · Q{qi + 1}",
                "selected": selected,
                "correct": correct,
                "detail": f"{selected} → {correct}" if selected and correct else selected or correct or "",
                "when_label": _session_when_label(row["answered_at"]) or "",
            }
        )
        if len(out) >= limit:
            break
    return out


def _learning_pulse_session_rows(
    db: sqlite3.Connection,
    *,
    days: int,
    user_ids: set[int] | None = None,
    hide_demo: bool = True,
    tracked_only: bool = True,
    limit: int = 80,
) -> list[dict[str, Any]]:
    _cleanup_empty_practice_attempts(db)
    window_sql = f"-{int(days)} days"
    demo_ids = _digest_demo_user_ids(db) if hide_demo else set()

    user_filter = ""
    params: list[Any] = []
    if user_ids is not None:
        if not user_ids:
            return []
        ph = ",".join("?" * len(user_ids))
        user_filter = f"AND u.id IN ({ph})"
        params.extend(sorted(user_ids))

    params.extend([window_sql, limit])
    rows = db.execute(
        f"""
        SELECT
            pa.id,
            u.username,
            u.id AS user_id,
            pa.domain,
            pa.topic,
            pa.created_at,
            COUNT(pr.id) AS responses_total,
            SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct_total,
            SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded_total,
            MAX(pr.submitted_at) AS last_submitted_at
        FROM practice_attempts pa
        JOIN users u ON u.id = pa.user_id
        LEFT JOIN practice_responses pr ON pr.attempt_id = pa.id
        WHERE u.role = 'student' AND u.is_active = 1
          AND pa.domain NOT LIKE 'exam_%'
          AND pa.domain != 'placement'
          {user_filter}
        GROUP BY pa.id
        HAVING COUNT(pr.id) > 0
          AND COALESCE(MAX(pr.submitted_at), pa.created_at) >= datetime('now', ?)
        ORDER BY COALESCE(MAX(pr.submitted_at), pa.created_at) DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()

    out: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        uid = int(row["user_id"])
        if hide_demo and uid in demo_ids:
            continue
        if _is_digest_demo_username(str(row["username"] or "")):
            continue
        graded = int(row.get("graded_total") or 0)
        is_tracked = graded >= MIN_TRACKED_SAT_RESPONSES
        if tracked_only and not is_tracked:
            continue
        responses = int(row.get("responses_total") or 0)
        correct = int(row.get("correct_total") or 0)
        topic = str(row.get("topic") or "")
        out.append(
            {
                "id": int(row["id"]),
                "username": str(row["username"] or ""),
                "user_id": uid,
                "topic_title": TOPIC_TITLES.get(topic, topic),
                "responses_total": responses,
                "accuracy_pct": round(100 * correct / responses) if responses else None,
                "created_at": row["created_at"],
                "last_submitted_at": row["last_submitted_at"],
                "tracking_label": "Counts" if is_tracked else f"Preview · need {max(0, MIN_TRACKED_SAT_RESPONSES - graded)} more",
                "is_tracked": is_tracked,
                "session_href": url_for("practice_session_summary", attempt_id=int(row["id"])),
                "student_href": url_for("admin_student_detail", user_id=uid),
            }
        )
    return out


def _learning_pulse_panel_context(
    db: sqlite3.Connection,
    *,
    digest_days: int = 7,
    hide_demo: bool = True,
    cohort_id: int | None = None,
) -> dict[str, Any]:
    digest = _admin_weekly_digest(
        db, digest_days, hide_demo=hide_demo, cohort_id=cohort_id
    )
    scope_ids = {int(s["id"]) for s in digest.get("students") or []}
    session_rows = _learning_pulse_session_rows(
        db,
        days=digest_days,
        user_ids=scope_ids,
        hide_demo=hide_demo,
        tracked_only=True,
    )
    sessions_by_user: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in session_rows:
        sessions_by_user[int(row["user_id"])].append(row)

    roster_students: list[dict[str, Any]] = []
    for student in digest.get("students") or []:
        uid = int(student["id"])
        user_sessions = sessions_by_user.get(uid, [])
        roster_students.append(
            {
                **student,
                "sessions": user_sessions,
                "period_sessions": len(user_sessions),
            }
        )
    roster_students.sort(
        key=lambda s: (
            0 if s.get("period_sessions") else 1,
            0 if s.get("status") == "active" else 1,
            str(s.get("username") or "").lower(),
        )
    )

    selected_student_id: int | None = None
    raw_student = (request.args.get("student_id") or "").strip()
    if raw_student:
        try:
            candidate = int(raw_student)
            if any(int(s["id"]) == candidate for s in roster_students):
                selected_student_id = candidate
        except ValueError:
            pass
    if selected_student_id is None and roster_students:
        selected_student_id = int(roster_students[0]["id"])

    return {
        "weekly_digest": digest,
        "digest_days": digest_days,
        "hide_demo": hide_demo,
        "cohort_id": cohort_id,
        "student_cohorts": _student_cohort_rows(db),
        "session_rows": session_rows,
        "roster_students": roster_students,
        "selected_student_id": selected_student_id,
        "min_tracked_responses": MIN_TRACKED_SAT_RESPONSES,
    }


def _parse_learning_pulse_args() -> tuple[int, bool, int | None, int | None]:
    try:
        digest_days = int(request.args.get("digest_days") or request.args.get("days") or 7)
    except ValueError:
        digest_days = 7
    if digest_days not in (7, 14, 30):
        digest_days = 7
    hide_demo = request.args.get("hide_demo", "1") not in ("0", "false", "no")
    cohort_id: int | None = None
    raw_cohort = (request.args.get("cohort_id") or "").strip()
    if raw_cohort:
        try:
            cohort_id = int(raw_cohort)
        except ValueError:
            cohort_id = None
    student_id: int | None = None
    raw_student = (request.args.get("student_id") or "").strip()
    if raw_student:
        try:
            student_id = int(raw_student)
        except ValueError:
            student_id = None
    return digest_days, hide_demo, cohort_id, student_id


def _digest_weekly_trend_series(
    db: sqlite3.Connection,
    *,
    weeks: int = 8,
    exclude_user_ids: set[int] | None = None,
) -> dict[str, Any]:
    exclude_user_ids = exclude_user_ids or set()
    exclude_clause = ""
    exclude_params: list[Any] = []
    if exclude_user_ids:
        ph = ",".join("?" * len(exclude_user_ids))
        exclude_clause = f"AND u.id NOT IN ({ph})"
        exclude_params = sorted(exclude_user_ids)

    series: list[dict[str, Any]] = []
    for w in range(weeks - 1, -1, -1):
        start_days = (w + 1) * 7
        end_days = w * 7
        start_sql = f"-{start_days} days"
        end_clause = "datetime('now')" if end_days == 0 else f"datetime('now', '-{end_days} days')"
        row = db.execute(
            f"""
            SELECT
                COUNT(DISTINCT CASE WHEN pa.id IS NOT NULL THEN u.id END) AS active_students,
                COUNT(DISTINCT CASE
                    WHEN pa.domain NOT LIKE 'exam_%' AND pa.domain != 'placement' THEN pa.id
                END) AS practice_sessions,
                SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded,
                SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct
            FROM users u
            LEFT JOIN practice_attempts pa ON pa.user_id = u.id
              AND pa.created_at >= datetime('now', ?)
              AND pa.created_at < {end_clause}
            LEFT JOIN practice_responses pr ON pr.attempt_id = pa.id
            WHERE u.role = 'student' AND u.is_active = 1
              {exclude_clause}
            """,
            (start_sql, *exclude_params),
        ).fetchone()
        mock_rows = db.execute(
            f"""
            SELECT pa.exam_meta_json
            FROM practice_attempts pa
            JOIN users u ON u.id = pa.user_id
            WHERE u.role = 'student' AND u.is_active = 1
              {exclude_clause}
              AND pa.domain = 'exam_random_test'
              AND pa.exam_meta_json IS NOT NULL
              AND pa.created_at >= datetime('now', ?)
              AND pa.created_at < {end_clause}
            """,
            (*exclude_params, start_sql),
        ).fetchall()
        scores: list[int] = []
        for mock_row in mock_rows:
            try:
                score = int(json.loads(mock_row["exam_meta_json"] or "{}").get("score") or 0)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if score > 0:
                scores.append(score)
        graded = int(row["graded"] or 0) if row else 0
        correct = int(row["correct"] or 0) if row else 0
        week_end = datetime.now() - timedelta(days=end_days)
        series.append(
            {
                "label": week_end.strftime("%b %d"),
                "active_students": int(row["active_students"] or 0) if row else 0,
                "practice_sessions": int(row["practice_sessions"] or 0) if row else 0,
                "accuracy_pct": round(100 * correct / graded) if graded else None,
                "mock_median": sorted(scores)[len(scores) // 2] if scores else None,
                "mock_count": len(scores),
            }
        )

    max_active = max((s["active_students"] for s in series), default=0) or 1
    max_practice = max((s["practice_sessions"] for s in series), default=0) or 1
    acc_values = [s["accuracy_pct"] for s in series if s["accuracy_pct"] is not None]
    max_acc = max(acc_values, default=100) or 100
    mock_values = [s["mock_median"] for s in series if s["mock_median"] is not None]
    max_mock = max(mock_values, default=800) or 800
    for point in series:
        point["active_bar_pct"] = max(8, round(100 * point["active_students"] / max_active))
        point["practice_bar_pct"] = max(8, round(100 * point["practice_sessions"] / max_practice))
        point["accuracy_bar_pct"] = (
            max(8, round(100 * point["accuracy_pct"] / max_acc)) if point["accuracy_pct"] is not None else 0
        )
        point["mock_bar_pct"] = (
            max(8, round(100 * point["mock_median"] / max_mock)) if point["mock_median"] is not None else 0
        )
    return {"weeks": series, "weeks_count": weeks}


def _digest_class_mastery(
    db: sqlite3.Connection, exclude_user_ids: set[int] | None = None
) -> dict[str, Any]:
    exclude_user_ids = exclude_user_ids or set()
    rows = db.execute(
        "SELECT id FROM users WHERE role = 'student' AND is_active = 1"
    ).fetchall()
    learner_keys = [
        _learner_key_for_user(int(row["id"]))
        for row in rows
        if int(row["id"]) not in exclude_user_ids
    ]
    if not learner_keys:
        return {"mastered": 0, "total": 0, "digest_pct": None}
    ph = ",".join("?" * len(learner_keys))
    stat = db.execute(
        f"""
        SELECT
            SUM(CASE WHEN status = 'mastered' THEN 1 ELSE 0 END) AS mastered,
            COUNT(*) AS total
        FROM mistake_learning_progress
        WHERE learner_key IN ({ph})
        """,
        learner_keys,
    ).fetchone()
    mastered = int(stat["mastered"] or 0) if stat else 0
    total = int(stat["total"] or 0) if stat else 0
    return {
        "mastered": mastered,
        "total": total,
        "digest_pct": round(100 * mastered / total) if total else None,
    }


def _digest_student_mastery_pct(db: sqlite3.Connection, user_id: int) -> int | None:
    lk = _learner_key_for_user(user_id)
    row = db.execute(
        """
        SELECT
            SUM(CASE WHEN status = 'mastered' THEN 1 ELSE 0 END) AS mastered,
            COUNT(*) AS total
        FROM mistake_learning_progress
        WHERE learner_key = ?
        """,
        (lk,),
    ).fetchone()
    total = int(row["total"] or 0) if row else 0
    if not total:
        return None
    mastered = int(row["mastered"] or 0) if row else 0
    return round(100 * mastered / total)


def _digest_student_attention_reason(
    student: dict[str, Any], nudge_groups: dict[str, list[dict[str, Any]]]
) -> str | None:
    uid = int(student["id"])
    for kind, label in (
        ("inactive", "No activity this period"),
        ("no_practice", "Logged in but no practice"),
        ("no_mock", "Practicing but no mock yet"),
    ):
        if any(int(s["id"]) == uid for s in nudge_groups.get(kind) or []):
            return label
    if student.get("quality_hint"):
        return str(student["quality_hint"])
    if student.get("weak_chapter"):
        return f"Weak: {student['weak_chapter']} ({student['weak_chapter_pct']}%)"
    return None


def _digest_pulse_brief(digest: dict[str, Any]) -> dict[str, Any]:
    students = digest.get("students") or []
    summary = digest.get("summary") or {}
    nudge_groups = digest.get("nudge_groups") or {}
    nudge = digest.get("needs_attention") or []
    total = len(students)
    active = int(summary.get("active_students") or 0)
    acc = summary.get("accuracy_pct")

    if total == 0:
        headline = "No students in this view."
        status = "empty"
    elif not nudge and active >= max(1, (total + 1) // 2):
        headline = f"Class is engaged — {active} of {total} students active this period."
        status = "on_track"
    elif nudge and len(nudge) >= total:
        headline = f"Everyone needs a check-in — all {total} students need follow-up."
        status = "needs_attention"
    else:
        parts: list[str] = [f"{active} of {total} active"]
        if digest.get("class_weak_chapters"):
            chapter = str(digest["class_weak_chapters"][0]["label"]).split(" · ", 1)[0]
            parts.append(f"review {chapter} next")
        elif digest.get("class_weak_units"):
            parts.append(f"weak in {digest['class_weak_units'][0]['label']}")
        if nudge:
            parts.append(f"{len(nudge)} need follow-up")
        headline = ", ".join(parts).capitalize() + "."
        status = "mixed"

    glance = [
        {
            "key": "active",
            "label": "Active students",
            "value": f"{active}/{total}",
            "hint": digest.get("trends", {}).get("practice_sessions_delta"),
        },
        {
            "key": "mock",
            "label": "Took a mock",
            "value": str(int(summary.get("exam_takers") or 0)),
            "hint": digest.get("trends", {}).get("exam_sessions_delta"),
        },
        {
            "key": "accuracy",
            "label": "Class accuracy",
            "value": f"{acc}%" if acc is not None else "—",
            "hint": (
                f"Based on {summary.get('accuracy_basis')} answers"
                if summary.get("accuracy_basis")
                else None
            ),
        },
        {
            "key": "nudge",
            "label": "Need follow-up",
            "value": str(len(nudge)),
            "hint": "Inactive or missing mocks" if nudge else "Nobody flagged",
            "emphasis": bool(nudge),
        },
    ]

    step_titles = {
        "review": "Review in class",
        "assign": "Assign a mock",
        "nudge": "Send reminders",
        "quality": "Run miss quiz",
        "loop": "Keep the weekly loop",
    }
    priority_steps: list[dict[str, Any]] = []
    for action in digest.get("teaching_actions") or []:
        if len(priority_steps) >= 3:
            break
        step = dict(action)
        step["step"] = len(priority_steps) + 1
        step["short_title"] = step_titles.get(str(action.get("kind") or ""), action.get("title"))
        priority_steps.append(step)

    attention: list[dict[str, Any]] = []
    seen: set[int] = set()
    for student in nudge[:8]:
        uid = int(student["id"])
        attention.append(
            {
                "username": student["username"],
                "admin_href": student["admin_href"],
                "report_href": student.get("report_href") or student["admin_href"],
                "status": student["status"],
                "reason": _digest_student_attention_reason(student, nudge_groups) or "Needs follow-up",
                "last_active": student["last_activity_label"],
            }
        )
        seen.add(uid)
    for student in students:
        uid = int(student["id"])
        if uid in seen or not student.get("quality_hint"):
            continue
        attention.append(
            {
                "username": student["username"],
                "admin_href": student["admin_href"],
                "report_href": student.get("report_href") or student["admin_href"],
                "status": student["status"],
                "reason": str(student["quality_hint"]),
                "last_active": student["last_activity_label"],
            }
        )
        seen.add(uid)
        if len(attention) >= 8:
            break

    primary_ids = {int(s["id"]) for s in nudge}
    for student in students:
        if student.get("practice_sessions") or student.get("exam_sessions"):
            primary_ids.add(int(student["id"]))

    def _roster_note(student: dict[str, Any]) -> str:
        reason = _digest_student_attention_reason(student, nudge_groups)
        if reason:
            return reason
        if student.get("mock_trend_label"):
            return f"Mock: {student['mock_trend_label']}"
        if student.get("weak_chapter"):
            return f"{student['weak_chapter']} · {student['weak_chapter_pct']}%"
        if student.get("accuracy_pct") is not None:
            return f"{student['accuracy_pct']}% accuracy"
        return "On track"

    roster_primary = []
    roster_rest = []
    for student in students:
        row = dict(student)
        row["pulse_note"] = _roster_note(student)
        if int(student["id"]) in primary_ids:
            roster_primary.append(row)
        else:
            roster_rest.append(row)

    focus_line = None
    if digest.get("class_weak_chapters"):
        focus = digest["class_weak_chapters"][0]
        focus_line = f"{focus['label']} — class avg {focus['avg_pct']}%"
    elif digest.get("class_weak_units"):
        focus = digest["class_weak_units"][0]
        focus_line = f"{focus['label']} — class avg {focus['avg_pct']}%"

    return {
        "headline": headline,
        "status": status,
        "glance": glance,
        "priority_steps": priority_steps,
        "attention": attention,
        "roster_primary": roster_primary,
        "roster_rest": roster_rest,
        "focus_line": focus_line,
        "nudge_count": len(nudge),
        "student_count": total,
    }


def _digest_teaching_actions(
    digest: dict[str, Any],
    *,
    days: int,
    exam_hub_href: str,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    weak_chapters = digest.get("class_weak_chapters") or []
    if weak_chapters:
        focus = weak_chapters[0]
        actions.append(
            {
                "kind": "review",
                "title": f"Review: {focus['label']}",
                "detail": (
                    f"Class avg {focus['avg_pct']}% across {focus['students']} student(s) "
                    f"in the last {days} days."
                ),
            }
        )
    elif digest.get("class_weak_units"):
        focus = digest["class_weak_units"][0]
        actions.append(
            {
                "kind": "review",
                "title": f"Review: {focus['label']}",
                "detail": (
                    f"Domain avg {focus['avg_pct']}% across {focus['students']} student(s) "
                    f"this period."
                ),
            }
        )

    students = digest.get("students") or []
    no_mock = [s for s in students if not s.get("exam_sessions")]
    if no_mock:
        actions.append(
            {
                "kind": "assign",
                "title": "Assign: Random Test mock",
                "detail": f"{len(no_mock)}/{len(students)} student(s) have not taken a mock in this period.",
                "href": exam_hub_href,
            }
        )

    nudge = digest.get("nudge_groups") or {}
    inactive = nudge.get("inactive") or []
    if inactive:
        names = ", ".join(s["username"] for s in inactive[:6])
        if len(inactive) > 6:
            names += "…"
        actions.append(
            {
                "kind": "nudge",
                "title": "Nudge inactive students",
                "detail": f"{len(inactive)} student(s) with no activity: {names}",
                "copy_names": [s["username"] for s in inactive],
            }
        )

    low_quality = [
        s
        for s in students
        if s.get("accuracy_pct") is not None
        and s["accuracy_pct"] < 50
        and int(s.get("wrong_count") or 0) >= 5
    ]
    if low_quality:
        names = ", ".join(s["username"] for s in low_quality[:4])
        actions.append(
            {
                "kind": "quality",
                "title": "Suggest miss quiz / redo",
                "detail": f"Low accuracy with logged misses: {names}",
            }
        )

    tags = digest.get("top_mistake_tags") or []
    if tags and not any(a["kind"] == "review" for a in actions):
        actions.append(
            {
                "kind": "review",
                "title": f"Review: {tags[0][0]}",
                "detail": f"{tags[0][1]} tagged wrongs this period — good for a short recap.",
            }
        )

    if not actions:
        actions.append(
            {
                "kind": "loop",
                "title": "Keep the weekly loop",
                "detail": "One lesson deck, one bank drill, one mock, then mistake redo.",
            }
        )
    return actions[:4]


def _digest_period_stats(
    db: sqlite3.Connection,
    days: int,
    *,
    offset_days: int = 0,
    exclude_user_ids: set[int] | None = None,
) -> dict[str, int]:
    """Aggregate practice/exam activity for a window ending `offset_days` ago."""
    exclude_user_ids = exclude_user_ids or set()
    exclude_clause = ""
    exclude_params: list[Any] = []
    if exclude_user_ids:
        ph = ",".join("?" * len(exclude_user_ids))
        exclude_clause = f"AND u.id NOT IN ({ph})"
        exclude_params = sorted(exclude_user_ids)
    start_sql = f"-{int(days) + int(offset_days)} days"
    end_clause = "datetime('now')" if not offset_days else f"datetime('now', '-{int(offset_days)} days')"
    row = db.execute(
        f"""
        SELECT
            COUNT(DISTINCT CASE WHEN pa.id IS NOT NULL THEN u.id END) AS active_students,
            COUNT(DISTINCT CASE
                WHEN pa.domain NOT LIKE 'exam_%' AND pa.domain != 'placement' THEN pa.id
            END) AS practice_sessions,
            COUNT(DISTINCT CASE WHEN pa.domain LIKE 'exam_%' THEN pa.id END) AS exam_sessions,
            SUM(CASE WHEN pr.is_correct = 0 THEN 1 ELSE 0 END) AS wrong_count,
            SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded_count,
            SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct_count
        FROM users u
        LEFT JOIN practice_attempts pa ON pa.user_id = u.id
          AND pa.created_at >= datetime('now', ?)
          AND pa.created_at < {end_clause}
        LEFT JOIN practice_responses pr ON pr.attempt_id = pa.id
        WHERE u.role = 'student' AND u.is_active = 1
          {exclude_clause}
        """,
        (start_sql, *exclude_params),
    ).fetchone()
    graded = int(row["graded_count"] or 0) if row else 0
    correct = int(row["correct_count"] or 0) if row else 0
    return {
        "active_students": int(row["active_students"] or 0) if row else 0,
        "practice_sessions": int(row["practice_sessions"] or 0) if row else 0,
        "exam_sessions": int(row["exam_sessions"] or 0) if row else 0,
        "wrong_count": int(row["wrong_count"] or 0) if row else 0,
        "accuracy_pct": round(100 * correct / graded) if graded else None,
    }


def _digest_delta_label(current: int, previous: int) -> str:
    diff = current - previous
    if diff > 0:
        return f"+{diff} vs prior period"
    if diff < 0:
        return f"{diff} vs prior period"
    return "flat vs prior period"


def _admin_weekly_digest(
    db: sqlite3.Connection,
    days: int = 7,
    *,
    hide_demo: bool = True,
    cohort_id: int | None = None,
) -> dict[str, Any]:
    window_sql = f"-{int(days)} days"
    id_to_label = {o["id"]: o["label"] for o in MISTAKE_TAG_OPTIONS}
    demo_user_ids = _digest_demo_user_ids(db) if hide_demo else set()
    exam_hub_href = url_for("practice_exams")

    cohort_info: dict[str, Any] | None = None
    cohort_member_ids: set[int] | None = None
    if cohort_id is not None:
        cohort_info = _student_cohort_by_id(db, cohort_id)
        if cohort_info is None:
            cohort_id = None
        else:
            cohort_member_ids = set(cohort_info["member_ids"])

    all_active_student_ids = {
        int(row["id"])
        for row in db.execute(
            "SELECT id FROM users WHERE role = 'student' AND is_active = 1"
        ).fetchall()
    }
    digest_exclude_user_ids = set(demo_user_ids if hide_demo else set())
    if cohort_member_ids is not None:
        digest_exclude_user_ids |= all_active_student_ids - cohort_member_ids

    def _digest_user_in_scope(uid: int) -> bool:
        if hide_demo and uid in demo_user_ids:
            return False
        if cohort_member_ids is not None and uid not in cohort_member_ids:
            return False
        if not _staff_can_view_student(db, uid):
            return False
        return True

    scope_clause, scope_params = _staff_student_scope_clause(db)
    student_rows = db.execute(
        f"""
        SELECT
            u.id,
            u.username,
            u.last_login_at,
            MAX(COALESCE(pr.submitted_at, pa.created_at)) AS last_activity,
            COUNT(DISTINCT CASE
                WHEN pa.domain NOT LIKE 'exam_%' AND pa.domain != 'placement' THEN pa.id
            END) AS practice_sessions,
            COUNT(DISTINCT CASE WHEN pa.domain LIKE 'exam_%' THEN pa.id END) AS exam_sessions,
            SUM(CASE WHEN pr.is_correct = 0 THEN 1 ELSE 0 END) AS wrong_count,
            SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded_count,
            SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct_count
        FROM users u
        LEFT JOIN practice_attempts pa
          ON pa.user_id = u.id AND pa.created_at >= datetime('now', ?)
        LEFT JOIN practice_responses pr ON pr.attempt_id = pa.id
        WHERE u.role = 'student' AND u.is_active = 1{scope_clause}
        GROUP BY u.id, u.username, u.last_login_at
        ORDER BY last_activity DESC, lower(u.username)
        """,
        (window_sql, *scope_params),
    ).fetchall()

    exam_rows = db.execute(
        f"""
        SELECT pa.user_id, pa.domain, pa.topic, pa.exam_meta_json, pa.created_at
        FROM practice_attempts pa
        JOIN users u ON u.id = pa.user_id
        WHERE u.role = 'student' AND u.is_active = 1
          AND pa.domain LIKE 'exam_%'
          AND pa.created_at >= datetime('now', ?)
        ORDER BY pa.id DESC
        """,
        (window_sql,),
    ).fetchall()
    latest_exam_by_user: dict[int, str] = {}
    for row in exam_rows:
        uid = int(row["user_id"])
        if not _digest_user_in_scope(uid):
            continue
        if uid in latest_exam_by_user:
            continue
        latest_exam_by_user[uid] = _exam_attempt_label(
            str(row["domain"] or ""),
            str(row["topic"] or ""),
            row["exam_meta_json"],
        )

    tag_counts: dict[str, int] = defaultdict(int)
    tag_rows = db.execute(
        f"""
        SELECT pa.user_id, pr.mistake_tags
        FROM practice_responses pr
        JOIN practice_attempts pa ON pa.id = pr.attempt_id
        JOIN users u ON u.id = pa.user_id
        WHERE u.role = 'student' AND u.is_active = 1
          AND pr.is_correct = 0
          AND pr.mistake_tags IS NOT NULL
          AND pr.mistake_tags != ''
          AND COALESCE(pr.submitted_at, pa.created_at) >= datetime('now', ?)
        """,
        (window_sql,),
    ).fetchall()
    for row in tag_rows:
        uid = int(row["user_id"])
        if not _digest_user_in_scope(uid):
            continue
        try:
            arr = json.loads(row["mistake_tags"] or "[]")
        except json.JSONDecodeError:
            continue
        if not isinstance(arr, list):
            continue
        for tag_id in arr:
            if isinstance(tag_id, str):
                tag_counts[id_to_label.get(tag_id, tag_id)] += 1

    all_mock_rows = db.execute(
        """
        SELECT pa.user_id, pa.exam_meta_json, pa.created_at
        FROM practice_attempts pa
        JOIN users u ON u.id = pa.user_id
        WHERE u.role = 'student' AND u.is_active = 1
          AND pa.domain = 'exam_random_test'
          AND pa.exam_meta_json IS NOT NULL
        ORDER BY pa.user_id, pa.id
        """
    ).fetchall()
    all_scores_by_user: dict[int, list[int]] = defaultdict(list)
    for row in all_mock_rows:
        if not _digest_user_in_scope(int(row["user_id"])):
            continue
        try:
            meta = json.loads(row["exam_meta_json"] or "{}")
            score = int(meta.get("score") or 0)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if score > 0:
            all_scores_by_user[int(row["user_id"])].append(score)

    period_mock_rows = db.execute(
        f"""
        SELECT pa.user_id, pa.exam_meta_json, pa.created_at
        FROM practice_attempts pa
        JOIN users u ON u.id = pa.user_id
        WHERE u.role = 'student' AND u.is_active = 1
          AND pa.domain = 'exam_random_test'
          AND pa.exam_meta_json IS NOT NULL
          AND pa.created_at >= datetime('now', ?)
        ORDER BY pa.user_id, pa.id
        """,
        (window_sql,),
    ).fetchall()
    period_scores_by_user: dict[int, list[int]] = defaultdict(list)
    for row in period_mock_rows:
        if not _digest_user_in_scope(int(row["user_id"])):
            continue
        try:
            meta = json.loads(row["exam_meta_json"] or "{}")
            score = int(meta.get("score") or 0)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if score > 0:
            period_scores_by_user[int(row["user_id"])].append(score)

    students: list[dict[str, Any]] = []
    active_count = 0
    quiet_count = 0
    inactive_count = 0
    exam_takers = 0
    hidden_demo_count = 0
    for row in student_rows:
        uid = int(row["id"])
        username = str(row["username"] or "")
        is_demo = _is_digest_demo_username(username)
        if not _digest_user_in_scope(uid):
            if hide_demo and is_demo:
                hidden_demo_count += 1
            continue
        last_activity = row["last_activity"]
        status = _activity_status_label(last_activity)
        if status == "active":
            active_count += 1
        elif status == "quiet":
            quiet_count += 1
        else:
            inactive_count += 1
        exam_sessions = int(row["exam_sessions"] or 0)
        if exam_sessions:
            exam_takers += 1
        graded = int(row["graded_count"] or 0)
        correct = int(row["correct_count"] or 0)
        wrong_count = int(row["wrong_count"] or 0)
        accuracy_pct = round(100 * correct / graded) if graded else None
        all_scores = all_scores_by_user.get(uid) or []
        period_scores = period_scores_by_user.get(uid) or []
        mock_first = all_scores[0] if all_scores else None
        mock_latest = all_scores[-1] if all_scores else None
        if len(all_scores) >= 2:
            delta = all_scores[-1] - all_scores[0]
            mock_trend_label = f"{mock_first}→{mock_latest} ({delta:+d})"
        elif mock_latest is not None:
            mock_trend_label = f"{mock_latest}/800"
        else:
            mock_trend_label = None
        quality_hint = None
        if accuracy_pct is not None and accuracy_pct < 50 and wrong_count >= 5:
            quality_hint = "Suggest miss quiz"
        elif graded and graded < MIN_TRACKED_SAT_RESPONSES and (wrong_count or graded):
            quality_hint = f"Only {graded} graded — needs {MIN_TRACKED_SAT_RESPONSES}+ for analytics"
        students.append(
            {
                "id": uid,
                "username": username,
                "is_demo": is_demo,
                "last_activity": last_activity,
                "last_activity_label": _session_when_label(last_activity) or "No activity",
                "last_login_at": row["last_login_at"],
                "practice_sessions": int(row["practice_sessions"] or 0),
                "exam_sessions": exam_sessions,
                "latest_exam_label": latest_exam_by_user.get(uid),
                "wrong_count": wrong_count,
                "graded_count": graded,
                "accuracy_pct": accuracy_pct,
                "accuracy_basis": graded,
                "status": status,
                "admin_href": url_for("admin_student_detail", user_id=uid),
                "report_href": url_for("admin_student_report", user_id=uid),
                "mock_first_score": mock_first,
                "mock_latest_score": mock_latest,
                "mock_period_count": len(period_scores),
                "mock_trend_label": mock_trend_label,
                "mock_assign_href": exam_hub_href if not all_scores else None,
                "quality_hint": quality_hint,
                "mastery_pct": _digest_student_mastery_pct(db, uid),
            }
        )

    top_mistake_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))[:8]

    nudge_groups: dict[str, list[dict[str, Any]]] = {
        "inactive": [],
        "no_practice": [],
        "no_mock": [],
    }
    for student in students:
        if student["status"] == "inactive":
            nudge_groups["inactive"].append(student)
        elif student["practice_sessions"] == 0 and student["exam_sessions"] == 0:
            nudge_groups["no_practice"].append(student)
        elif student["status"] == "active" and student["exam_sessions"] == 0:
            nudge_groups["no_mock"].append(student)
    needs_attention = (
        nudge_groups["inactive"]
        + nudge_groups["no_practice"]
        + nudge_groups["no_mock"]
    )

    chapter_topics = [(d, t) for d, t, _, _ in STUDENT_CHAPTER_SLICES]
    chapter_ph = " OR ".join("(pa.domain = ? AND pa.topic = ?)" for _ in chapter_topics)
    chapter_params: list[Any] = [window_sql]
    for domain, topic in chapter_topics:
        chapter_params.extend([domain, topic])
    chapter_unit_rows = db.execute(
        f"""
        SELECT
            pa.user_id,
            pa.domain,
            pa.topic,
            SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct,
            SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded
        FROM practice_attempts pa
        JOIN practice_responses pr ON pr.attempt_id = pa.id
        JOIN users u ON u.id = pa.user_id
        WHERE u.role = 'student' AND u.is_active = 1
          AND pa.created_at >= datetime('now', ?)
          AND ({chapter_ph})
        GROUP BY pa.user_id, pa.domain, pa.topic
        HAVING graded >= 3
        """,
        chapter_params,
    ).fetchall()

    weak_chapter_by_user: dict[int, tuple[str, int, str]] = {}
    chapter_class: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in chapter_unit_rows:
        uid = int(row["user_id"])
        if not _digest_user_in_scope(uid):
            continue
        graded_u = int(row["graded"] or 0)
        if graded_u <= 0:
            continue
        pct = round(100 * int(row["correct"] or 0) / graded_u)
        domain = str(row["domain"] or "")
        topic = str(row["topic"] or "")
        label = _digest_chapter_slice_label(domain, topic)
        chapter_class[(domain, topic)].append(pct)
        prev = weak_chapter_by_user.get(uid)
        if prev is None or pct < prev[1]:
            weak_chapter_by_user[uid] = (label, pct, topic)
    class_weak_chapters: list[dict[str, Any]] = []
    for (domain, topic), pcts in chapter_class.items():
        if not pcts:
            continue
        class_weak_chapters.append(
            {
                "label": _digest_chapter_slice_label(domain, topic),
                "domain": domain,
                "topic": topic,
                "avg_pct": round(sum(pcts) / len(pcts)),
                "students": len(pcts),
            }
        )
    class_weak_chapters.sort(key=lambda x: (x["avg_pct"], -x["students"]))

    unit_rows = db.execute(
        f"""
        SELECT
            pa.user_id,
            pa.domain,
            SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct,
            SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded
        FROM practice_attempts pa
        JOIN practice_responses pr ON pr.attempt_id = pa.id
        JOIN users u ON u.id = pa.user_id
        WHERE u.role = 'student' AND u.is_active = 1
          AND pa.domain IN ('algebra', 'advanced_math', 'problem_solving', 'geometry', 'hard_problem')
          AND pa.created_at >= datetime('now', ?)
        GROUP BY pa.user_id, pa.domain
        HAVING graded >= 3
        """,
        (window_sql,),
    ).fetchall()
    weak_unit_by_user: dict[int, tuple[str, int]] = {}
    for row in unit_rows:
        uid = int(row["user_id"])
        if not _digest_user_in_scope(uid):
            continue
        graded_u = int(row["graded"] or 0)
        if graded_u <= 0:
            continue
        pct = round(100 * int(row["correct"] or 0) / graded_u)
        domain = str(row["domain"] or "")
        label = _dashboard_track_short(domain)
        prev = weak_unit_by_user.get(uid)
        if prev is None or pct < prev[1]:
            weak_unit_by_user[uid] = (label, pct)
    for student in students:
        uid = int(student["id"])
        weak_ch = weak_chapter_by_user.get(uid)
        student["weak_chapter"] = weak_ch[0] if weak_ch else None
        student["weak_chapter_pct"] = weak_ch[1] if weak_ch else None
        weak = weak_unit_by_user.get(uid)
        student["weak_unit"] = weak[0] if weak else None
        student["weak_unit_pct"] = weak[1] if weak else None

    prior = _digest_period_stats(
        db, days, offset_days=days, exclude_user_ids=digest_exclude_user_ids
    )
    current_agg = {
        "practice_sessions": sum(s["practice_sessions"] for s in students),
        "exam_sessions": sum(s["exam_sessions"] for s in students),
        "wrong_count": sum(s["wrong_count"] for s in students),
        "active_students": active_count,
        "graded_responses": sum(s["graded_count"] for s in students),
    }
    graded_all = current_agg["graded_responses"]
    correct_all = sum(
        round(s["graded_count"] * s["accuracy_pct"] / 100)
        for s in students
        if s.get("accuracy_pct") is not None and s["graded_count"]
    )
    current_accuracy = round(100 * correct_all / graded_all) if graded_all else None

    unit_class: dict[str, list[int]] = defaultdict(list)
    for row in unit_rows:
        uid = int(row["user_id"])
        if not _digest_user_in_scope(uid):
            continue
        graded_u = int(row["graded"] or 0)
        if graded_u <= 0:
            continue
        unit_class[str(row["domain"] or "")].append(
            round(100 * int(row["correct"] or 0) / graded_u)
        )
    class_weak_units = []
    for domain, pcts in unit_class.items():
        if not pcts:
            continue
        class_weak_units.append(
            {
                "label": _dashboard_track_short(domain),
                "avg_pct": round(sum(pcts) / len(pcts)),
                "students": len(pcts),
            }
        )
    class_weak_units.sort(key=lambda x: (x["avg_pct"], -x["students"]))

    class_mastery = _digest_class_mastery(db, digest_exclude_user_ids)
    weekly_trends = _digest_weekly_trend_series(
        db, weeks=8, exclude_user_ids=digest_exclude_user_ids
    )

    learning_insights: list[str] = []
    if class_weak_chapters:
        focus = class_weak_chapters[0]
        learning_insights.append(
            f"Chapter focus: {focus['label']} averages {focus['avg_pct']}% across {focus['students']} student(s) this period."
        )
    elif class_weak_units:
        focus = class_weak_units[0]
        learning_insights.append(
            f"Class focus: {focus['label']} averages {focus['avg_pct']}% across {focus['students']} student(s) this period."
        )
    if top_mistake_tags:
        learning_insights.append(
            f"Recurring misses: {top_mistake_tags[0][0]} ({top_mistake_tags[0][1]} tagged wrongs) — good candidate for a short review."
        )
    no_mock = [s["username"] for s in students if not s.get("exam_sessions")]
    if no_mock:
        learning_insights.append(
            f"{len(no_mock)} student(s) have not taken a mock exam in the last {days} days."
        )
    improvers = [
        s
        for s in students
        if s.get("mock_first_score") is not None
        and s.get("mock_latest_score") is not None
        and s["mock_latest_score"] > s["mock_first_score"]
    ]
    if improvers:
        learning_insights.append(
            f"Mock score gains: {', '.join(s['username'] for s in improvers[:4])}"
            + ("…" if len(improvers) > 4 else "")
            + " improved on Random Test."
        )
    if class_mastery.get("digest_pct") is not None:
        learning_insights.append(
            f"Mistake mastery: {class_mastery['digest_pct']}% of logged misses marked mastered ({class_mastery['mastered']}/{class_mastery['total']})."
        )
    if not learning_insights:
        learning_insights.append(
            "Keep the weekly loop: one lesson deck, one bank drill, one mock, then mistake redo."
        )

    miss_quiz_row = db.execute(
        f"""
        SELECT
            COUNT(*) AS runs,
            SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END) AS passed_runs
        FROM miss_quiz_runs mqr
        JOIN users u ON u.id = mqr.user_id
        WHERE u.role = 'student' AND u.is_active = 1
          AND mqr.created_at >= datetime('now', ?)
          {"AND u.id NOT IN (" + ",".join("?" * len(digest_exclude_user_ids)) + ")" if digest_exclude_user_ids else ""}
        """,
        (window_sql, *sorted(digest_exclude_user_ids)),
    ).fetchone()
    miss_quiz_runs = int(miss_quiz_row["runs"] or 0) if miss_quiz_row else 0
    miss_quiz_passed = int(miss_quiz_row["passed_runs"] or 0) if miss_quiz_row else 0
    miss_quiz_pass_rate = round(100 * miss_quiz_passed / miss_quiz_runs) if miss_quiz_runs else None
    if miss_quiz_runs:
        learning_insights.append(
            f"Miss quiz pass rate: {miss_quiz_passed}/{miss_quiz_runs} runs cleared the {MISS_QUIZ_PASS_PERCENT}% bar this period."
        )

    period_name = {7: "This week", 14: "Last 2 weeks", 30: "Last 30 days"}.get(days, f"Last {days} days")
    if cohort_info:
        period_name = f"{cohort_info['name']} · {period_name}"
    q_param = request.args.get("q") or ""
    hide_demo_param = "1" if hide_demo else "0"

    def _digest_admin_href(**extra: Any) -> str:
        params: dict[str, Any] = {
            "digest_days": days,
            "hide_demo": hide_demo_param,
            "q": q_param,
        }
        if cohort_id is not None:
            params["cohort_id"] = cohort_id
        params.update(extra)
        return url_for("admin", **params)

    digest: dict[str, Any] = {
        "days": days,
        "period_label": period_name,
        "cohort_id": cohort_id,
        "cohort_name": cohort_info["name"] if cohort_info else None,
        "cohort_member_count": len(cohort_member_ids) if cohort_member_ids is not None else None,
        "hide_demo": hide_demo,
        "hidden_demo_count": hidden_demo_count,
        "period_options": [
            {
                "days": 7,
                "label": "7 days",
                "href": _digest_admin_href(digest_days=7),
            },
            {
                "days": 14,
                "label": "14 days",
                "href": _digest_admin_href(digest_days=14),
            },
            {
                "days": 30,
                "label": "30 days",
                "href": _digest_admin_href(digest_days=30),
            },
        ],
        "demo_toggle_href": _digest_admin_href(
            hide_demo="0" if hide_demo else "1",
        ),
        "print_href": url_for(
            "admin_learning_pulse_print",
            days=days,
            hide_demo=hide_demo_param,
            cohort_id=cohort_id or None,
        ),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": {
            "students_total": len(students),
            "active_students": active_count,
            "quiet_students": quiet_count,
            "inactive_students": inactive_count,
            "exam_takers": exam_takers,
            "practice_sessions": current_agg["practice_sessions"],
            "exam_sessions": current_agg["exam_sessions"],
            "total_wrongs": current_agg["wrong_count"],
            "graded_responses": current_agg["graded_responses"],
            "accuracy_pct": current_accuracy,
            "accuracy_basis": graded_all,
            "mastery_pct": class_mastery.get("digest_pct"),
            "mastery_mastered": class_mastery.get("mastered"),
            "mastery_total": class_mastery.get("total"),
        },
        "trends": {
            "practice_sessions_delta": _digest_delta_label(
                current_agg["practice_sessions"], prior["practice_sessions"]
            ),
            "exam_sessions_delta": _digest_delta_label(
                current_agg["exam_sessions"], prior["exam_sessions"]
            ),
            "wrongs_delta": _digest_delta_label(current_agg["wrong_count"], prior["wrong_count"]),
            "prior_accuracy_pct": prior["accuracy_pct"],
        },
        "weekly_trends": weekly_trends,
        "students": students,
        "top_mistake_tags": top_mistake_tags,
        "needs_attention": needs_attention[:12],
        "nudge_groups": nudge_groups,
        "class_weak_units": class_weak_units[:4],
        "class_weak_chapters": class_weak_chapters[:6],
        "learning_insights": learning_insights[:6],
        "miss_quiz_pass_rate": miss_quiz_pass_rate,
        "miss_quiz_runs": miss_quiz_runs,
        "exam_hub_href": exam_hub_href,
    }
    digest["teaching_actions"] = _digest_teaching_actions(
        digest, days=days, exam_hub_href=exam_hub_href
    )
    digest["nudge_copy_text"] = ", ".join(s["username"] for s in needs_attention)
    digest["pulse_brief"] = _digest_pulse_brief(digest)
    return digest


def _admin_attempt_rows(
    db: sqlite3.Connection, user_id: int | None = None, *, tracked_only: bool = False
) -> List[dict]:
    _cleanup_empty_practice_attempts(db)
    where = ""
    params: list[Any] = []
    if user_id is not None:
        where = "WHERE pa.user_id = ?"
        params = [user_id]

    rows = [
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
                pa.exam_meta_json,
                COUNT(pr.id) AS responses_total,
                SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct_total,
                SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded_total,
                MAX(pr.submitted_at) AS last_submitted_at
            FROM practice_attempts pa
            LEFT JOIN users u ON u.id = pa.user_id
            LEFT JOIN practice_responses pr ON pr.attempt_id = pa.id
            {where}
            GROUP BY pa.id
            HAVING COUNT(pr.id) > 0
            ORDER BY COALESCE(last_submitted_at, pa.created_at) DESC
            LIMIT 300
            """,
            tuple(params),
        ).fetchall()
    ]
    out: list[dict] = []
    for row in rows:
        domain = str(row.get("domain") or "")
        graded = int(row.get("graded_total") or 0)
        is_tracked = domain == "placement" or graded >= MIN_TRACKED_SAT_RESPONSES
        if tracked_only and not is_tracked and not domain.startswith("exam_"):
            continue
        responses = int(row.get("responses_total") or 0)
        correct = int(row.get("correct_total") or 0)
        row["accuracy_pct"] = round(100 * correct / responses) if responses else None
        row["is_tracked"] = is_tracked
        row["topic_title"] = TOPIC_TITLES.get(str(row.get("topic") or ""), str(row.get("topic") or ""))
        row["tracking_label"] = (
            "Counts"
            if is_tracked or domain.startswith("exam_")
            else f"Preview · need {max(0, MIN_TRACKED_SAT_RESPONSES - graded)} more"
        )
        row["label"] = _exam_attempt_label(
            domain,
            str(row.get("topic") or ""),
            row.get("exam_meta_json"),
        )
        out.append(row)
    return out


def _admin_attempt_topic_summary(rows: list[dict]) -> list[dict[str, Any]]:
    """Roll tracked bank sessions up by topic for a cleaner teacher view."""
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if not row.get("is_tracked") or str(row.get("domain") or "").startswith("exam_"):
            continue
        key = (str(row.get("domain") or ""), str(row.get("topic") or ""))
        bucket = buckets.get(key)
        if bucket is None:
            buckets[key] = {
                "domain": key[0],
                "topic": key[1],
                "topic_title": row.get("topic_title") or key[1],
                "sessions": 1,
                "best_accuracy_pct": row.get("accuracy_pct"),
                "latest_accuracy_pct": row.get("accuracy_pct"),
                "latest_at": row.get("last_submitted_at") or row.get("created_at"),
                "total_responses": int(row.get("responses_total") or 0),
            }
            continue
        bucket["sessions"] += 1
        bucket["total_responses"] += int(row.get("responses_total") or 0)
        acc = row.get("accuracy_pct")
        if acc is not None and (
            bucket["best_accuracy_pct"] is None or acc > bucket["best_accuracy_pct"]
        ):
            bucket["best_accuracy_pct"] = acc
        latest_at = row.get("last_submitted_at") or row.get("created_at")
        if latest_at and str(latest_at) >= str(bucket["latest_at"] or ""):
            bucket["latest_at"] = latest_at
            bucket["latest_accuracy_pct"] = acc
    summary = list(buckets.values())
    summary.sort(key=lambda x: (x["topic_title"], x["domain"]))
    return summary


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


@app.route("/admin/cohorts", methods=["POST"])
def admin_cohort_create():
    gate = _require_admin_response()
    if gate is not None:
        return gate

    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Class group name is required.")
        return redirect(url_for("admin"))
    description = (request.form.get("description") or "").strip() or None
    db = get_db()
    cur = db.execute(
        "INSERT INTO student_cohorts (name, description) VALUES (?, ?)",
        (name, description),
    )
    db.commit()
    cohort_id = int(cur.lastrowid)
    flash(f'Class group "{name}" created. Add students on the edit page.')
    return redirect(url_for("admin_cohort_edit", cohort_id=cohort_id))


@app.route("/admin/cohorts/<int:cohort_id>", methods=["GET", "POST"])
def admin_cohort_edit(cohort_id: int):
    gate = _require_admin_response()
    if gate is not None:
        return gate

    db = get_db()
    cohort = _student_cohort_by_id(db, cohort_id)
    if cohort is None:
        abort(404)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Class group name is required.")
            return redirect(url_for("admin_cohort_edit", cohort_id=cohort_id))
        description = (request.form.get("description") or "").strip() or None
        make_default = request.form.get("is_default") == "1"
        raw_ids = request.form.getlist("student_ids")
        member_ids: set[int] = set()
        for raw in raw_ids:
            try:
                member_ids.add(int(raw))
            except ValueError:
                continue
        db.execute(
            "UPDATE student_cohorts SET name = ?, description = ? WHERE id = ?",
            (name, description, cohort_id),
        )
        if make_default:
            _set_default_student_cohort(db, cohort_id)
        elif cohort["is_default"]:
            db.execute(
                "UPDATE student_cohorts SET is_default = 0 WHERE id = ?",
                (cohort_id,),
            )
        db.execute("DELETE FROM student_cohort_members WHERE cohort_id = ?", (cohort_id,))
        for uid in sorted(member_ids):
            active = db.execute(
                "SELECT id FROM users WHERE id = ? AND role = 'student' AND is_active = 1",
                (uid,),
            ).fetchone()
            if active:
                db.execute(
                    "INSERT INTO student_cohort_members (cohort_id, user_id) VALUES (?, ?)",
                    (cohort_id, uid),
                )
        db.commit()
        flash(f'Class group "{name}" saved ({len(member_ids)} students).')
        return redirect(url_for("admin_cohort_edit", cohort_id=cohort_id))

    students = _student_rows(db, "")
    member_set = set(cohort["member_ids"])
    roster = [
        {
            **s,
            "in_cohort": int(s["id"]) in member_set,
        }
        for s in students
        if s["is_active"]
    ]
    return render_template(
        "admin_cohort.html",
        cohort=cohort,
        roster=roster,
        weekly_digest=_admin_weekly_digest(db, 7, hide_demo=True, cohort_id=cohort_id),
    )


@app.route("/admin/cohorts/<int:cohort_id>/delete", methods=["POST"])
def admin_cohort_delete(cohort_id: int):
    gate = _require_admin_response()
    if gate is not None:
        return gate

    confirm = _admin_confirm_value(request.form.get("confirm") or "")
    if confirm != "DELETE GROUP":
        flash('Type DELETE GROUP to remove this class group.')
        return redirect(url_for("admin_cohort_edit", cohort_id=cohort_id))

    db = get_db()
    cohort = _student_cohort_by_id(db, cohort_id)
    if cohort is None:
        abort(404)
    db.execute("DELETE FROM student_cohorts WHERE id = ?", (cohort_id,))
    db.commit()
    flash(f'Class group "{cohort["name"]}" deleted.')
    return redirect(url_for("admin"))


@app.route("/admin")
def admin():
    gate = _require_admin_response()
    if gate is not None:
        return gate

    db = get_db()
    q = (request.args.get("q") or "").strip()
    digest_days, hide_demo, cohort_id, _student_id = _parse_learning_pulse_args()
    pulse_ctx = _learning_pulse_panel_context(
        db,
        digest_days=digest_days,
        hide_demo=hide_demo,
        cohort_id=cohort_id,
    )
    students = _student_rows(db, q)
    recent_records = _recent_record_rows(db)
    data_snapshot = _admin_data_snapshot(db)
    student_cohorts = pulse_ctx["student_cohorts"]
    totals = {
        "students": len(students),
        "active_students": sum(1 for s in students if s["is_active"]),
        "responses": sum(int(s["responses_total"] or 0) for s in students),
    }
    staff_scope = _current_staff_view_scope(db) if current_user_role() == ROLE_STAFF else STAFF_VIEW_ALL
    staff_view_scope_label = (
        "All students"
        if staff_scope == STAFF_VIEW_ALL
        else "Your registered students only"
    )
    return render_template(
        "admin.html",
        students=students,
        staff_members=_staff_rows(db) if current_user_is_supervisor() else [],
        recent_records=recent_records,
        data_snapshot=data_snapshot,
        totals=totals,
        weekly_digest=pulse_ctx["weekly_digest"],
        session_rows=pulse_ctx["session_rows"],
        roster_students=pulse_ctx["roster_students"],
        selected_student_id=pulse_ctx["selected_student_id"],
        min_tracked_responses=pulse_ctx["min_tracked_responses"],
        digest_days=digest_days,
        hide_demo=hide_demo,
        cohort_id=cohort_id,
        student_cohorts=student_cohorts,
        q=q,
        user_is_supervisor=current_user_is_supervisor(),
        staff_view_scope_label=staff_view_scope_label,
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
    if not _staff_can_view_student(db, user_id):
        abort(403)
    student_dict = dict(student)
    student_dict["access_grants_label"] = _access_grants_label(
        student["access_grants"] or student["access_scope"]
    )
    student_dict["access_grants_set"] = _normalize_access_grants(
        student["access_grants"] or student["access_scope"]
    )
    attempts_all = _admin_attempt_rows(db, user_id)
    attempts = _admin_attempt_rows(db, user_id, tracked_only=True)
    attempt_topic_summary = _admin_attempt_topic_summary(attempts_all)
    preview_count = sum(1 for a in attempts_all if not a.get("is_tracked"))
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
        attempts_all=attempts_all,
        attempt_topic_summary=attempt_topic_summary,
        preview_session_count=preview_count,
        min_tracked_responses=MIN_TRACKED_SAT_RESPONSES,
        totals=totals,
        report_href=url_for("admin_student_report", user_id=user_id),
        student_resource_grant_options=STUDENT_RESOURCE_GRANTS,
    )


@app.route("/admin/students/<int:user_id>/report")
def admin_student_report(user_id: int):
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
    if not _staff_can_view_student(db, user_id):
        abort(403)
    student_dict = dict(student)
    return render_template(
        "student_report.html",
        **_student_report_context(db, user_id, viewer="admin", student=student_dict),
    )


@app.route("/admin/students/<int:user_id>/report/print")
def admin_student_report_print(user_id: int):
    gate = _require_admin_response()
    if gate is not None:
        return gate

    db = get_db()
    student = db.execute(
        "SELECT id, username, is_active, created_at FROM users WHERE id = ? AND role = 'student'",
        (user_id,),
    ).fetchone()
    if student is None:
        abort(404)
    _require_student_access(db, user_id)
    return render_template(
        "student_report_print.html",
        **_student_report_context(db, user_id, viewer="admin", student=dict(student)),
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
        creator_id = session.get("user_id")
        try:
            db.execute(
                """
                INSERT INTO users (username, password, password_hash, role, is_active, access_grants, registered_by, created_at)
                VALUES (?, '', ?, 'student', 1, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    username,
                    generate_password_hash(password),
                    grants_json,
                    int(creator_id) if creator_id else None,
                ),
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
    view_scope = (request.form.get("student_view_scope") or STAFF_VIEW_OWN).strip().lower()
    if view_scope not in (STAFF_VIEW_ALL, STAFF_VIEW_OWN):
        view_scope = STAFF_VIEW_OWN

    if not username or len(username) > 160:
        flash("Enter a colleague email or username.")
    elif not password:
        flash("Enter a password for this colleague account.")
    else:
        db = get_db()
        try:
            db.execute(
                """
                INSERT INTO users (username, password, password_hash, role, is_active, student_view_scope, created_at)
                VALUES (?, '', ?, ?, 1, ?, CURRENT_TIMESTAMP)
                """,
                (username, generate_password_hash(password), ROLE_STAFF, view_scope),
            )
            db.commit()
            scope_label = "all students" if view_scope == STAFF_VIEW_ALL else "only students they register"
            flash(f"Colleague account created for {username}. They can view {scope_label}.")
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


@app.route("/admin/staff/<int:user_id>/view-scope", methods=["POST"])
def admin_update_staff_view_scope(user_id: int):
    gate = _require_supervisor_response()
    if gate is not None:
        return gate

    view_scope = (request.form.get("student_view_scope") or STAFF_VIEW_OWN).strip().lower()
    if view_scope not in (STAFF_VIEW_ALL, STAFF_VIEW_OWN):
        view_scope = STAFF_VIEW_OWN

    db = get_db()
    row = db.execute(
        "SELECT username FROM users WHERE id = ? AND role = ?",
        (user_id, ROLE_STAFF),
    ).fetchone()
    if row is None:
        flash("Colleague account not found.")
        return redirect(url_for("admin"))

    db.execute(
        "UPDATE users SET student_view_scope = ? WHERE id = ? AND role = ?",
        (view_scope, user_id, ROLE_STAFF),
    )
    db.commit()
    label = "all students" if view_scope == STAFF_VIEW_ALL else "only their registered students"
    flash(f"Updated {row['username']} — can now view {label}.")
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
    _require_student_access(db, user_id)
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
    _require_student_access(db, user_id)
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
        _require_student_access(db, user_id)
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
