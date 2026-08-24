"""Anonymous Placement candidates. Isolated from users / practice_attempts.

Guest Placement is on by default so students can start without signing in.
Do not put PLACEMENT_PUBLIC_ACCESS in render.yaml. Set the env to 0 only to disable.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from typing import Any

from flask import current_app, request, session

FORBIDDEN_SQL = re.compile(r"\b(DROP|TRUNCATE|DELETE|ALTER)\b", re.IGNORECASE)

SLUG_TO_TOPIC = {
    "middle-level": "middle_level",
    "enhanced-math-1": "enhanced_math_1",
    "enhanced-math-2": "enhanced_math_2",
    "upper-algebra-precalc": "placement_full",
}
TOPIC_TO_SLUG = {v: k for k, v in SLUG_TO_TOPIC.items()}
ITEM_COUNTS = {
    "middle_level": 100,
    "enhanced_math_1": 65,
    "enhanced_math_2": 69,
    "placement_full": 85,
}
TIMER_MINUTES = {
    "middle_level": 150,
    "enhanced_math_1": 120,
    "enhanced_math_2": 130,
    "placement_full": 115,
}
OPEN_STATUSES = frozenset({"profile_completed", "in_progress"})
ADVISOR_PRESETS = ("Mia Hu", "Jimmy Zheng")
ADVISOR_OTHER = "Other"
ADVISOR_CHOICES = ADVISOR_PRESETS + (ADVISOR_OTHER,)
SESSION_CANDIDATE = "pp_candidate_id"
SESSION_ATTEMPT = "pp_attempt_public_id"
SESSION_TOKEN = "pp_session_token"
SESSION_RECOVERY_ONCE = "pp_recovery_once"
SESSION_BEGIN_NONCE = "pp_begin_nonce"
SESSION_CONSUMED_NONCE = "pp_consumed_nonce"

RATE_LIMITS = {
    "create": (5, 10 * 60),
    "recover": (8, 10 * 60),
    "save": (180, 60),
    "autosave": (400, 60),
    "finish": (12, 60),
}
_RATE_HITS: dict[str, list[float]] = {}

SQL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS placement_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        public_id TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL,
        grade TEXT,
        math_course TEXT,
        school TEXT,
        counselor_source TEXT,
        selected_slug TEXT NOT NULL,
        selected_topic TEXT NOT NULL,
        counselor_confirmed_at TEXT,
        recovery_code_hash TEXT NOT NULL,
        recovery_revoked_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_activity_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pc_slug ON placement_candidates(selected_slug, created_at)",
    """
    CREATE TABLE IF NOT EXISTS placement_candidate_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL,
        public_id TEXT UNIQUE NOT NULL,
        slug TEXT NOT NULL,
        topic TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at TEXT,
        submitted_at TEXT,
        last_activity_at TEXT,
        answered_count INTEGER NOT NULL DEFAULT 0,
        total_count INTEGER NOT NULL,
        score_json TEXT,
        recommendation_json TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_pca_one_open_attempt
    ON placement_candidate_attempts(candidate_id)
    WHERE status IN ('profile_completed', 'in_progress')
    """,
    "CREATE INDEX IF NOT EXISTS idx_pca_candidate ON placement_candidate_attempts(candidate_id, created_at)",
    """
    CREATE TABLE IF NOT EXISTS placement_candidate_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL,
        attempt_id INTEGER,
        token_hash TEXT UNIQUE NOT NULL,
        expires_at TEXT NOT NULL,
        revoked_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_seen_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pcs_candidate ON placement_candidate_sessions(candidate_id)",
    """
    CREATE TABLE IF NOT EXISTS placement_candidate_responses (
        attempt_id INTEGER NOT NULL,
        question_index INTEGER NOT NULL,
        selected_answer TEXT,
        correct_answer TEXT,
        is_correct INTEGER,
        submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (attempt_id, question_index)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS placement_candidate_drafts (
        attempt_id INTEGER NOT NULL,
        question_index INTEGER NOT NULL,
        selected_answer TEXT,
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (attempt_id, question_index)
    )
    """,
]


def assert_sql_is_additive() -> None:
    for sql in SQL_STATEMENTS:
        if FORBIDDEN_SQL.search(sql):
            raise SystemExit("Refusing SQL with DROP/TRUNCATE/DELETE/ALTER:\n" + sql)


def ensure_tables(db: sqlite3.Connection) -> None:
    assert_sql_is_additive()
    for sql in SQL_STATEMENTS:
        db.execute(sql)


def placement_public_enabled() -> bool:
    env = (os.environ.get("PLACEMENT_PUBLIC_ACCESS") or "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    try:
        return bool(current_app.config.get("PLACEMENT_PUBLIC_ACCESS"))
    except RuntimeError:
        return False


def public_path_allowed(path: str) -> bool:
    p = (path or "/").split("?")[0]
    if p == "/placement" or p.startswith("/placement/"):
        return True
    return False


def _pepper() -> bytes:
    return str(current_app.secret_key or "dev-secret-change-me").encode("utf-8")


def hash_token(raw: str) -> str:
    return hmac.new(_pepper(), str(raw).encode("utf-8"), hashlib.sha256).hexdigest()


def new_public_id() -> str:
    return secrets.token_urlsafe(18)


def new_recovery_code() -> str:
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    chars = "".join(alphabet[secrets.randbelow(len(alphabet))] for _ in range(16))
    return "-".join(chars[i : i + 4] for i in range(0, 16, 4))


def new_session_token() -> str:
    return secrets.token_urlsafe(24)


def client_ip() -> str:
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or (request.remote_addr or "")


def rate_limited(kind: str, key: str | None = None) -> bool:
    max_n, window = RATE_LIMITS[kind]
    ident = f"{kind}|{key or client_ip()}"
    now = time.time()
    recent = [t for t in _RATE_HITS.get(ident, []) if now - t < window]
    _RATE_HITS[ident] = recent
    return len(recent) >= max_n


def record_rate_hit(kind: str, key: str | None = None) -> None:
    ident = f"{kind}|{key or client_ip()}"
    _RATE_HITS.setdefault(ident, []).append(time.time())


def reset_rate_limits_for_tests() -> None:
    _RATE_HITS.clear()


def is_public_guest() -> bool:
    return placement_public_enabled() and "user_id" not in session


def sanitize_advisor_prefill(raw: str) -> str:
    """Treat URL advisor= as plain text only — never as a role or permission."""
    text = re.sub(r"[\x00-\x1f<>]", "", str(raw or ""))
    text = " ".join(text.split())
    return text[:200]


def advisor_prefill_state(raw: str) -> dict[str, str]:
    text = sanitize_advisor_prefill(raw)
    if not text:
        return {"choice": "", "other": "", "text": ""}
    if text in ADVISOR_PRESETS:
        return {"choice": text, "other": "", "text": text}
    return {"choice": ADVISOR_OTHER, "other": text, "text": text}


def resolve_advisor(choice: str, other_name: str) -> str:
    """Optional advisor. Empty string means not provided — not an error."""
    picked = (choice or "").strip()
    if picked in ADVISOR_PRESETS:
        return picked
    if picked == ADVISOR_OTHER:
        custom = " ".join((other_name or "").split())
        if len(custom) < 2:
            return ""
        return custom[:200]
    extra = " ".join((other_name or "").split())
    if len(extra) >= 2:
        return extra[:200]
    return ""


def begin_nonce() -> str:
    token = session.get(SESSION_BEGIN_NONCE)
    if not token:
        token = secrets.token_urlsafe(12)
        session[SESSION_BEGIN_NONCE] = token
        session.modified = True
    return str(token)


def _row(db: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Row | None:
    return db.execute(sql, params).fetchone()


def bind_browser_session(db: sqlite3.Connection, candidate_id: int, attempt_id: int, raw_token: str) -> None:
    db.execute(
        """
        INSERT INTO placement_candidate_sessions
            (candidate_id, attempt_id, token_hash, expires_at, last_seen_at)
        VALUES (?, ?, ?, datetime('now', '+12 hours'), datetime('now'))
        """,
        (candidate_id, attempt_id, hash_token(raw_token)),
    )
    session[SESSION_CANDIDATE] = int(candidate_id)
    session[SESSION_ATTEMPT] = None
    att = _row(db, "SELECT public_id FROM placement_candidate_attempts WHERE id = ?", (attempt_id,))
    if att:
        session[SESSION_ATTEMPT] = att["public_id"]
    session[SESSION_TOKEN] = raw_token
    session.modified = True


def current_session_row(db: sqlite3.Connection) -> sqlite3.Row | None:
    raw = session.get(SESSION_TOKEN)
    cid = session.get(SESSION_CANDIDATE)
    if not raw or not cid:
        return None
    row = _row(
        db,
        """
        SELECT s.id, s.candidate_id, s.attempt_id, s.revoked_at, s.expires_at,
               c.public_id AS candidate_public_id, c.recovery_revoked_at,
               a.public_id AS attempt_public_id, a.status, a.slug, a.topic,
               a.answered_count, a.total_count, a.submitted_at
        FROM placement_candidate_sessions s
        JOIN placement_candidates c ON c.id = s.candidate_id
        JOIN placement_candidate_attempts a ON a.id = s.attempt_id
        WHERE s.token_hash = ? AND s.candidate_id = ?
        """,
        (hash_token(str(raw)), int(cid)),
    )
    if row is None:
        return None
    if row["revoked_at"] or row["recovery_revoked_at"]:
        return None
    expired = _row(
        db,
        "SELECT 1 FROM placement_candidate_sessions WHERE id = ? AND expires_at <= datetime('now')",
        (row["id"],),
    )
    if expired:
        return None
    db.execute(
        "UPDATE placement_candidate_sessions SET last_seen_at = datetime('now') WHERE id = ?",
        (row["id"],),
    )
    db.execute(
        "UPDATE placement_candidates SET last_activity_at = datetime('now') WHERE id = ?",
        (row["candidate_id"],),
    )
    return row


def load_attempt(db: sqlite3.Connection, public_id: str) -> sqlite3.Row | None:
    return _row(
        db,
        """
        SELECT a.*, c.display_name, c.grade, c.math_course, c.school,
               c.counselor_source, c.public_id AS candidate_public_id,
               c.id AS candidate_table_id, c.recovery_revoked_at
        FROM placement_candidate_attempts a
        JOIN placement_candidates c ON c.id = a.candidate_id
        WHERE a.public_id = ?
        """,
        (public_id,),
    )


def authorize_attempt(db: sqlite3.Connection, public_id: str) -> sqlite3.Row | None:
    sess = current_session_row(db)
    if sess is None:
        return None
    att = load_attempt(db, public_id)
    if att is None:
        return None
    if int(att["candidate_id"]) != int(sess["candidate_id"]):
        return None
    if str(att["public_id"]) != str(sess["attempt_public_id"]):
        return None
    return att


def create_candidate_attempt(
    db: sqlite3.Connection,
    *,
    slug: str,
    display_name: str,
    grade: str,
    math_course: str,
    school: str,
    counselor_source: str,
    nonce: str,
) -> dict[str, Any]:
    topic = SLUG_TO_TOPIC[slug]
    total = ITEM_COUNTS[topic]
    consumed = session.get(SESSION_CONSUMED_NONCE)
    if consumed and consumed == nonce:
        sess = current_session_row(db)
        if sess is not None and sess["slug"] == slug:
            att = load_attempt(db, str(sess["attempt_public_id"]))
            return {
                "candidate": att,
                "attempt_public_id": sess["attempt_public_id"],
                "recovery_code": None,
                "replayed": True,
            }
    existing = current_session_row(db)
    if existing is not None and existing["slug"] == slug and existing["status"] in OPEN_STATUSES:
        return {
            "candidate": load_attempt(db, str(existing["attempt_public_id"])),
            "attempt_public_id": existing["attempt_public_id"],
            "recovery_code": None,
            "replayed": True,
        }

    recovery = new_recovery_code()
    session_token = new_session_token()
    candidate_public = new_public_id()
    attempt_public = new_public_id()
    cur = db.execute(
        """
        INSERT INTO placement_candidates (
            public_id, display_name, grade, math_course, school, counselor_source,
            selected_slug, selected_topic, counselor_confirmed_at, recovery_code_hash,
            last_activity_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, datetime('now'))
        """,
        (
            candidate_public,
            display_name,
            grade or None,
            math_course or None,
            school or None,
            counselor_source or None,
            slug,
            topic,
            hash_token(recovery.replace("-", "").upper()),
        ),
    )
    candidate_id = int(cur.lastrowid)
    cur = db.execute(
        """
        INSERT INTO placement_candidate_attempts (
            candidate_id, public_id, slug, topic, status, total_count, last_activity_at
        ) VALUES (?, ?, ?, ?, 'profile_completed', ?, datetime('now'))
        """,
        (candidate_id, attempt_public, slug, topic, total),
    )
    attempt_id = int(cur.lastrowid)
    bind_browser_session(db, candidate_id, attempt_id, session_token)
    session[SESSION_CONSUMED_NONCE] = nonce
    session[SESSION_BEGIN_NONCE] = secrets.token_urlsafe(12)
    session[SESSION_RECOVERY_ONCE] = recovery
    session.modified = True
    db.commit()
    att = load_attempt(db, attempt_public)
    return {
        "candidate": att,
        "attempt_public_id": attempt_public,
        "recovery_code": recovery,
        "replayed": False,
    }


def pop_recovery_once() -> str | None:
    code = session.pop(SESSION_RECOVERY_ONCE, None)
    if code:
        session.modified = True
    return code


def mark_in_progress(db: sqlite3.Connection, attempt_id: int) -> None:
    db.execute(
        """
        UPDATE placement_candidate_attempts
        SET status = CASE WHEN status = 'submitted' THEN status ELSE 'in_progress' END,
            started_at = COALESCE(started_at, datetime('now')),
            last_activity_at = datetime('now')
        WHERE id = ? AND status IN ('profile_completed', 'in_progress')
        """,
        (attempt_id,),
    )


def _refresh_answered_count(db: sqlite3.Connection, attempt_id: int) -> int:
    row = _row(
        db,
        """
        SELECT COUNT(*) AS c FROM placement_candidate_responses
        WHERE attempt_id = ? AND TRIM(COALESCE(selected_answer, '')) != ''
        """,
        (attempt_id,),
    )
    n = int(row["c"] or 0) if row else 0
    db.execute(
        """
        UPDATE placement_candidate_attempts
        SET answered_count = ?, last_activity_at = datetime('now')
        WHERE id = ?
        """,
        (n, attempt_id),
    )
    return n


def save_draft(
    db: sqlite3.Connection,
    attempt_id: int,
    q_index: int,
    answer: str,
    *,
    clear_empty: bool = False,
) -> None:
    if not (answer or "").strip():
        if clear_empty:
            db.execute(
                "DELETE FROM placement_candidate_drafts WHERE attempt_id = ? AND question_index = ?",
                (attempt_id, q_index),
            )
        return
    db.execute(
        """
        INSERT INTO placement_candidate_drafts (attempt_id, question_index, selected_answer, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(attempt_id, question_index) DO UPDATE SET
            selected_answer = excluded.selected_answer,
            updated_at = datetime('now')
        """,
        (attempt_id, q_index, answer.strip()),
    )


def save_response(
    db: sqlite3.Connection,
    attempt_id: int,
    q_index: int,
    selected: str,
    correct: str | None,
    is_correct: int | None,
) -> None:
    db.execute(
        """
        INSERT INTO placement_candidate_responses
            (attempt_id, question_index, selected_answer, correct_answer, is_correct, submitted_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(attempt_id, question_index) DO UPDATE SET
            selected_answer = excluded.selected_answer,
            correct_answer = excluded.correct_answer,
            is_correct = excluded.is_correct,
            submitted_at = datetime('now')
        """,
        (attempt_id, q_index, selected, correct, is_correct),
    )
    save_draft(db, attempt_id, q_index, selected)
    _refresh_answered_count(db, attempt_id)


def clear_response(db: sqlite3.Connection, attempt_id: int, q_index: int) -> None:
    db.execute(
        "DELETE FROM placement_candidate_responses WHERE attempt_id = ? AND question_index = ?",
        (attempt_id, q_index),
    )
    db.execute(
        "DELETE FROM placement_candidate_drafts WHERE attempt_id = ? AND question_index = ?",
        (attempt_id, q_index),
    )
    _refresh_answered_count(db, attempt_id)


def saved_answer(db: sqlite3.Connection, attempt_id: int, q_index: int) -> str:
    row = _row(
        db,
        """
        SELECT selected_answer FROM placement_candidate_responses
        WHERE attempt_id = ? AND question_index = ?
        """,
        (attempt_id, q_index),
    )
    if row and str(row["selected_answer"] or "").strip():
        return str(row["selected_answer"])
    draft = _row(
        db,
        """
        SELECT selected_answer FROM placement_candidate_drafts
        WHERE attempt_id = ? AND question_index = ?
        """,
        (attempt_id, q_index),
    )
    return str(draft["selected_answer"] or "") if draft else ""


def answered_indices(db: sqlite3.Connection, attempt_id: int) -> set[int]:
    rows = db.execute(
        """
        SELECT question_index FROM placement_candidate_responses
        WHERE attempt_id = ? AND TRIM(COALESCE(selected_answer, '')) != ''
        """,
        (attempt_id,),
    ).fetchall()
    return {int(r["question_index"]) for r in rows}


def finish_attempt(db: sqlite3.Connection, attempt_id: int, score_json: str | None, rec_json: str | None) -> bool:
    cur = db.execute(
        """
        UPDATE placement_candidate_attempts
        SET status = 'submitted',
            submitted_at = COALESCE(submitted_at, datetime('now')),
            last_activity_at = datetime('now'),
            score_json = COALESCE(?, score_json),
            recommendation_json = COALESCE(?, recommendation_json)
        WHERE id = ? AND status IN ('profile_completed', 'in_progress')
        """,
        (score_json, rec_json, attempt_id),
    )
    return (cur.rowcount or 0) > 0


def recover_with_code(db: sqlite3.Connection, raw_code: str) -> dict[str, Any] | None:
    compact = re.sub(r"[^0-9A-Z]", "", (raw_code or "").upper().replace("O", "0").replace("I", "1"))
    if len(compact) < 12:
        return None
    digest = hash_token(compact)
    row = _row(
        db,
        """
        SELECT c.id AS candidate_id, a.id AS attempt_id, a.public_id, a.status,
               c.recovery_revoked_at
        FROM placement_candidates c
        JOIN placement_candidate_attempts a ON a.candidate_id = c.id
        WHERE c.recovery_code_hash = ?
        ORDER BY a.id DESC
        LIMIT 1
        """,
        (digest,),
    )
    if row is None or row["recovery_revoked_at"]:
        return None
    token = new_session_token()
    bind_browser_session(db, int(row["candidate_id"]), int(row["attempt_id"]), token)
    db.commit()
    return {"attempt_public_id": row["public_id"], "status": row["status"]}


def revoke_recovery(db: sqlite3.Connection, candidate_id: int) -> None:
    db.execute(
        "UPDATE placement_candidates SET recovery_revoked_at = datetime('now') WHERE id = ?",
        (candidate_id,),
    )
    db.execute(
        "UPDATE placement_candidate_sessions SET revoked_at = datetime('now') WHERE candidate_id = ? AND revoked_at IS NULL",
        (candidate_id,),
    )


def reopen_attempt(db: sqlite3.Connection, attempt_id: int) -> bool:
    row = _row(db, "SELECT id, status FROM placement_candidate_attempts WHERE id = ?", (attempt_id,))
    if row is None or row["status"] != "submitted":
        return False
    db.execute(
        """
        UPDATE placement_candidate_attempts
        SET status = 'in_progress', submitted_at = NULL, last_activity_at = datetime('now')
        WHERE id = ?
        """,
        (attempt_id,),
    )
    return True


def list_candidates(db: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT c.id, c.public_id AS candidate_public_id, c.display_name, c.grade,
               c.math_course, c.school, c.counselor_source, c.selected_slug,
               c.created_at AS candidate_created,
               a.id AS attempt_id, a.public_id AS attempt_public_id, a.status,
               a.started_at, a.submitted_at, a.last_activity_at,
               a.answered_count, a.total_count, a.score_json, a.recommendation_json
        FROM placement_candidates c
        JOIN placement_candidate_attempts a ON a.id = (
            SELECT a2.id FROM placement_candidate_attempts a2
            WHERE a2.candidate_id = c.id
            ORDER BY a2.id DESC LIMIT 1
        )
        ORDER BY COALESCE(a.last_activity_at, c.created_at) DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def status_label(status: str) -> str:
    return {
        "invited": "Invited",
        "profile_completed": "Profile completed",
        "in_progress": "In progress",
        "submitted": "Submitted",
        "expired": "Expired",
        "needs_review": "Needs review",
    }.get(status, status.replace("_", " ").title())
