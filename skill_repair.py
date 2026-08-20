"""Repair-this-skill layer on the existing mistake log.

Does not replace Session Report, Coach Walkthrough, Miss Quiz, or Analytics.
Independent of SKILL_LOOP_PILOT so students can repair while the A/B flag is off.
Original-item redo never counts as independent_pass or auto-mastery.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from repair_html import (
    content_fingerprint,
    html_to_plain,
    normalize_item_for_render,
    stem_normalized_hash,
)

LINEAR_RATE_CODE = "sat.alg.linear_rate_remaining"
ALLOWED_MICRO_SKILLS = {
    "sat.alg.linear_rate_remaining": "Linear remaining quantity at a constant rate",
    "sat.alg.translate_words_to_equation": "Translate a word problem into an equation",
    "sat.alg.solve_linear_equation": "Solve a linear equation in one variable",
    "sat.alg.no_solution_parameter": "Parameter that makes a linear equation have no solution",
    "sat.alg.identity_infinite_solutions": "Identity: infinitely many solutions",
    "sat.alg.percent_cost_model": "Percent, discount, tax, or cost model",
}
INEQUALITY_SKILLS = {"sat.alg.inequality_direction"}
NEEDS_DIAGNOSIS_CODE = "sat.alg.needs_further_diagnosis"
LINEAR_RATE_HINTS = (
    "remain",
    "remaining",
    "constant rate",
    "per hour",
    "pounds remain",
    "gallons remain",
)
NO_SOLUTION_HINTS = (
    "no solution",
    "has no solution",
    "no value of",
    "no values of",
    "never true",
    "no real solution",
)
IDENTITY_HINTS = (
    "infinitely many",
    "all real numbers",
    "all values of",
    "identity",
    "infinitely many solutions",
    "all real values",
)
PERCENT_HINTS = (
    "percent",
    "%",
    "discount",
    "markup",
    "sale price",
    "original price",
    "tax",
    "cost of the",
)
TRANSLATE_HINTS = (
    "which equation",
    "which of the following equations",
    "which expression",
    "can be modeled",
    "models the",
    "represents the",
    "in terms of",
    "which of the following is equivalent",
)
SOLVE_HINTS = (
    "what is the value of",
    "what value of",
    "is the solution to",
    "solve for",
    "what is x",
    "find the value",
    "solve the equation",
)
INEQUALITY_HINTS = (
    "inequality",
    "greater than",
    "less than",
    "at least",
    "at most",
    "≥",
    "≤",
    "flip the inequality",
)
PHASES = ("worked", "faded", "isomorphic", "transfer", "delayed")
INDEPENDENT_PHASES = {"isomorphic", "transfer", "delayed"}
TEACHING_PHASES = {"worked", "faded"}
RESUME_STATUSES = {"active", "delayed_wait", "needs_review"}
DELAY_HOURS = 48
PACK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "skill_loop_pilot")

skill_repair_bp = Blueprint("skill_repair", __name__, url_prefix="/practice/repair")

PACK_SLOT = {
    "worked": "worked_example",
    "faded": "faded",
    "isomorphic": "independent",
    "transfer": "transfer",
    "delayed": "delayed",
}


def now_utc() -> datetime:
    factory = None
    try:
        cfg = current_app.config
        if cfg.get("TESTING") and callable(cfg.get("SKILL_LOOP_CLOCK")):
            factory = cfg.get("SKILL_LOOP_CLOCK")
    except RuntimeError:
        factory = None
    if factory:
        dt = factory()
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = str(raw).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_pack(skill_code: str) -> dict[str, Any] | None:
    if skill_code not in ALLOWED_MICRO_SKILLS:
        return None
    path = os.path.join(PACK_DIR, f"{skill_code}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else None


def pack_items_for_slot(pack: dict[str, Any], slot: str) -> list[dict[str, Any]]:
    items = pack.get("items") or []
    out = []
    for item in items:
        if str(item.get("slot") or "") == slot:
            out.append(item)
    out.sort(key=lambda x: int(x.get("variant_index") or 1))
    return out


def _blob_for_row(row: dict[str, Any]) -> str:
    stem = str(row.get("stem_html") or row.get("stem") or "").lower()
    title = str(row.get("knowledge_title") or row.get("topic_title") or "").lower()
    return f"{stem} {title}"


def primary_micro_skill(row: dict[str, Any]) -> dict[str, Any]:
    blob = _blob_for_row(row)
    code = ""
    if any(h in blob for h in NO_SOLUTION_HINTS):
        code = "sat.alg.no_solution_parameter"
    elif any(h in blob for h in IDENTITY_HINTS):
        code = "sat.alg.identity_infinite_solutions"
    elif any(h in blob for h in LINEAR_RATE_HINTS) and ("rate" in blob or "remain" in blob):
        code = "sat.alg.linear_rate_remaining"
    elif any(h in blob for h in PERCENT_HINTS):
        code = "sat.alg.percent_cost_model"
    elif any(h in blob for h in TRANSLATE_HINTS):
        code = "sat.alg.translate_words_to_equation"
    elif any(h in blob for h in SOLVE_HINTS) or "solve " in blob:
        code = "sat.alg.solve_linear_equation"
    elif any(h in blob for h in INEQUALITY_HINTS):
        code = "sat.alg.inequality_direction"
    if code in ALLOWED_MICRO_SKILLS:
        return {
            "code": code,
            "title": ALLOWED_MICRO_SKILLS[code],
            "has_pack": load_pack(code) is not None,
        }
    return {
        "code": NEEDS_DIAGNOSIS_CODE,
        "title": "Needs further diagnosis",
        "has_pack": False,
    }


def _priority_for_count(count: int, diagnosis_level: str) -> str:
    if count >= 4 or diagnosis_level == "High":
        return "High"
    if count >= 2 or diagnosis_level == "Medium":
        return "Medium"
    return "Watch"


def _student_chosen_error(row: dict[str, Any]) -> str:
    note = str(row.get("note") or row.get("mistake_note") or "").strip()
    if note:
        return note
    tags = [str(t).strip() for t in (row.get("tag_labels") or []) if str(t).strip()]
    if tags:
        return "Student tagged: " + ", ".join(tags[:3])
    return ""


def cluster_stuck_copy(bucket: dict[str, Any], skill_code: str) -> dict[str, str]:
    """Do not present template speculation as a confirmed stuck point."""
    chosen = []
    for row in bucket.get("rows") or []:
        text = _student_chosen_error(row)
        if text:
            chosen.append(text)
    if chosen:
        return {
            "stuck_label": "Possible focus",
            "common_stuck": chosen[0][:240],
            "stuck_certainty": "student_chosen",
        }
    if skill_code in INEQUALITY_SKILLS:
        pack = load_pack(skill_code) if skill_code in ALLOWED_MICRO_SKILLS else None
        pitfall = ""
        if pack:
            pitfall = str(pack.get("common_mistake") or "").strip()
        if pitfall and "inequality" in pitfall.lower():
            return {
                "stuck_label": "Possible focus",
                "common_stuck": pitfall,
                "stuck_certainty": "skill_specific",
            }
    return {
        "stuck_label": "Possible focus",
        "common_stuck": "需要进一步诊断",
        "stuck_certainty": "insufficient",
    }


def cluster_wrong_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group active misses by primary micro-skill. Archived/mastered stay out of the queue."""
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        effective = str(row.get("mastery_effective") or "unreviewed")
        if effective in {"mastered", "archived"}:
            continue
        skill = primary_micro_skill(row)
        row["primary_micro_skill"] = skill
        key = skill["code"]
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "code": key,
                "title": skill["title"],
                "has_pack": bool(skill["has_pack"]),
                "rows": [],
                "diagnoses": Counter(),
            }
            buckets[key] = bucket
        bucket["rows"].append(row)
        diag = str(row.get("diagnosis_label") or row.get("diagnosis_id") or "Concept gap")
        bucket["diagnoses"][diag] += 1

    clusters: list[dict[str, Any]] = []
    for key, bucket in buckets.items():
        rows_sorted = sorted(
            bucket["rows"],
            key=lambda r: str(r.get("when") or ""),
            reverse=True,
        )
        representative = rows_sorted[0]
        common_diag = bucket["diagnoses"].most_common(1)
        stuck = cluster_stuck_copy(bucket, key)
        level = str((representative.get("pattern_pack") or {}).get("level") or "")
        diag_level = "High" if bucket["diagnoses"] and common_diag and common_diag[0][1] >= 3 else (
            "Medium" if len(rows_sorted) >= 2 else "Low"
        )
        if level:
            diag_level = level
        priority = _priority_for_count(len(rows_sorted), diag_level)
        stem = str(representative.get("stem_html") or representative.get("stem") or "")
        stem_plain = html_to_plain(stem)
        try:
            repair_href = url_for("skill_repair.start", skill_code=key) if bucket["has_pack"] else ""
        except RuntimeError:
            repair_href = f"/practice/repair/{key}/start" if bucket["has_pack"] else ""
        clusters.append(
            {
                "code": key,
                "title": bucket["title"],
                "has_pack": bucket["has_pack"],
                "miss_count": len(rows_sorted),
                "priority": priority,
                "stuck_label": stuck["stuck_label"],
                "common_stuck": stuck["common_stuck"],
                "stuck_certainty": stuck["stuck_certainty"],
                "representative": representative,
                "representative_preview": " ".join(stem_plain.split())[:180],
                "rows": rows_sorted,
                "repair_href": repair_href,
                "diagnosis_label": common_diag[0][0] if common_diag else "Concept gap",
            }
        )
    clusters.sort(key=lambda c: ({"High": 0, "Medium": 1, "Watch": 2}.get(c["priority"], 9), -c["miss_count"]))
    return clusters


def recommended_next_step(clusters: list[dict[str, Any]]) -> dict[str, Any] | None:
    return clusters[0] if clusters else None


def repair_session_progress(db, user_id: Any, skill_code: str) -> dict[str, Any] | None:
    if user_id is None:
        return None
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    ensure_repair_tables(db)
    row = get_session_row(db, uid, skill_code)
    if row is None:
        return None
    status = str(row["status"] or "")
    phase = str(row["current_phase"] or "")
    due = parse_iso(row["delayed_available_at"] if "delayed_available_at" in row.keys() else None)
    hours_left = None
    if due is not None:
        hours_left = max(0, int((due - now_utc()).total_seconds() / 3600))
    mastered = status == "mastered"
    immediate = (status == "delayed_wait" or phase == "delayed") and not mastered
    payload = _payload(row)
    return {
        "session_id": int(row["id"]),
        "status": status,
        "phase": phase,
        "immediate_complete": immediate,
        "not_mastered": not mastered,
        "hours_left": hours_left,
        "delayed_available_at": row["delayed_available_at"] if "delayed_available_at" in row.keys() else None,
        "instruction_completed_at": payload.get("instruction_completed_at"),
        "entry_label": "View delayed check" if immediate else "Repair this skill",
        "hide_ordinary_repair": immediate,
    }


def annotate_clusters_with_progress(db, user_id: Any, clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for cluster in clusters:
        progress = repair_session_progress(db, user_id, str(cluster.get("code") or ""))
        cluster["repair_progress"] = progress
    return clusters


def _user_id() -> int:
    uid = session.get("user_id")
    try:
        return int(uid)
    except (TypeError, ValueError):
        abort(403)


def ensure_repair_tables(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_repair_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            skill_code TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'analytics',
            representative_domain TEXT,
            representative_topic TEXT,
            representative_q_index INTEGER,
            current_phase TEXT NOT NULL DEFAULT 'worked',
            current_variant INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'active',
            saw_answer INTEGER NOT NULL DEFAULT 0,
            delayed_available_at TEXT,
            mastered_at TEXT,
            payload_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_skill_repair_user_skill "
        "ON skill_repair_sessions(user_id, skill_code, status)"
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_repair_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            phase TEXT NOT NULL,
            item_ref TEXT NOT NULL,
            selected_answer TEXT,
            is_correct INTEGER,
            counts_as_independent INTEGER NOT NULL DEFAULT 0,
            solution_viewed INTEGER NOT NULL DEFAULT 0,
            hint_level TEXT NOT NULL DEFAULT 'none',
            is_original_item INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_skill_repair_events_session "
        "ON skill_repair_events(session_id, phase)"
    )


def get_session_row(db, user_id: int, skill_code: str):
    return db.execute(
        """
        SELECT * FROM skill_repair_sessions
        WHERE user_id = ? AND skill_code = ?
        ORDER BY id DESC LIMIT 1
        """,
        (user_id, skill_code),
    ).fetchone()


def _payload(row) -> dict[str, Any]:
    raw = row["payload_json"] if row is not None else None
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _save_payload(db, row, payload: dict[str, Any]) -> None:
    db.execute(
        "UPDATE skill_repair_sessions SET payload_json = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps(payload), int(row["id"])),
    )


def _origin_meta(representative: dict[str, Any] | None) -> dict[str, Any]:
    if not representative:
        return {}
    stem = str(representative.get("stem_html") or representative.get("stem") or "")
    return {
        "domain": representative.get("domain"),
        "topic": representative.get("topic"),
        "q_index": representative.get("q_index"),
        "pr_id": representative.get("pr_id"),
        "item_id": f"origin:{representative.get('domain')}:{representative.get('topic')}:{representative.get('q_index')}",
        "stem_hash": stem_normalized_hash(stem),
        "content_fingerprint": content_fingerprint({"stem_html": stem, "choices": representative.get("choices") or []}),
    }


def start_repair_session(db, user_id: int, skill_code: str, representative: dict[str, Any] | None) -> Any:
    pack = load_pack(skill_code)
    if pack is None:
        return None
    payload: dict[str, Any] = {
        "source": "pack",
        "primary_skill": skill_code,
        "seen_item_ids": [],
        "seen_stem_hashes": [],
        "seen_fingerprints": [],
        "teaching_item_ids": [],
        "teaching_stem_hashes": [],
        "origin": _origin_meta(representative),
    }
    existing = get_session_row(db, user_id, skill_code)
    if existing is not None and str(existing["status"] or "") in RESUME_STATUSES:
        return existing
    cur = db.execute(
        """
        INSERT INTO skill_repair_sessions (
            user_id, skill_code, representative_domain, representative_topic,
            representative_q_index, current_phase, current_variant, status, payload_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'worked', 1, 'active', ?, datetime('now'))
        """,
        (
            user_id,
            skill_code,
            str((representative or {}).get("domain") or "") or None,
            str((representative or {}).get("topic") or "") or None,
            representative.get("q_index") if representative else None,
            json.dumps(payload),
        ),
    )
    db.commit()
    return db.execute("SELECT * FROM skill_repair_sessions WHERE id = ?", (cur.lastrowid,)).fetchone()


def _letter_for_index(i: int) -> str:
    return chr(ord("A") + i)


def _identity_tuple(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("item_id") or item.get("id") or ""),
        str(item.get("stem_hash") or stem_normalized_hash(str(item.get("stem_html") or item.get("stem") or ""))),
        str(item.get("content_fingerprint") or content_fingerprint(item)),
    )


def _seen_sets(payload: dict[str, Any]) -> dict[str, set[str]]:
    origin = payload.get("origin") or {}
    return {
        "ids": set(str(x) for x in (payload.get("seen_item_ids") or []) if x)
        | ({str(origin.get("item_id"))} if origin.get("item_id") else set()),
        "hashes": set(str(x) for x in (payload.get("seen_stem_hashes") or []) if x)
        | ({str(origin.get("stem_hash"))} if origin.get("stem_hash") else set()),
        "fps": set(str(x) for x in (payload.get("seen_fingerprints") or []) if x)
        | ({str(origin.get("content_fingerprint"))} if origin.get("content_fingerprint") else set()),
        "teaching_ids": set(str(x) for x in (payload.get("teaching_item_ids") or []) if x),
        "teaching_hashes": set(str(x) for x in (payload.get("teaching_stem_hashes") or []) if x),
    }


def item_is_unseen(item: dict[str, Any], payload: dict[str, Any]) -> bool:
    seen = _seen_sets(payload)
    item_id, stem_hash, fingerprint = _identity_tuple(item)
    if item_id and item_id in seen["ids"]:
        return False
    if stem_hash and stem_hash in seen["hashes"]:
        return False
    if fingerprint and fingerprint in seen["fps"]:
        return False
    return True


def _pick_unseen_pack_item(
    items: list[dict[str, Any]],
    payload: dict[str, Any],
    *,
    skill_code: str,
    phase: str,
    prefer_index: int,
    allow_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    ordered = list(items)
    if 0 <= prefer_index < len(ordered):
        ordered = ordered[prefer_index:] + ordered[:prefer_index]
    allow_ids = allow_ids or set()
    for raw in ordered:
        item = dict(raw)
        if str(item.get("skill_code") or skill_code) != skill_code:
            continue
        if phase == "transfer" and not str(item.get("unknown_change") or "").strip():
            continue
        item_id = str(item.get("id") or "")
        if item_id and item_id in allow_ids:
            return item
        if not item_is_unseen(item, payload):
            continue
        return item
    return None


def _pinned_id(payload: dict[str, Any], phase: str, variant: int) -> str:
    pinned = payload.get("pinned") or {}
    slot = pinned.get(phase) or {}
    return str(slot.get(str(variant)) or slot.get(variant) or "")


def pin_item(payload: dict[str, Any], phase: str, variant: int, item_id: str) -> None:
    pinned = dict(payload.get("pinned") or {})
    slot = dict(pinned.get(phase) or {})
    slot[str(variant)] = item_id
    pinned[phase] = slot
    payload["pinned"] = pinned


def pin_current_item(db, row, phase: str, variant: int, item: dict[str, Any]) -> dict[str, Any]:
    payload = _payload(row)
    item_id, _stem_hash, _fp = _identity_tuple(item)
    pin_item(payload, phase, variant, item_id)
    payload["last_item"] = {
        "item_id": item_id,
        "stem_hash": str(item.get("stem_hash") or ""),
        "content_fingerprint": str(item.get("content_fingerprint") or ""),
        "phase": phase,
    }
    _save_payload(db, row, payload)
    return payload


def remember_shown_item(db, row, phase: str, item: dict[str, Any], variant: int | None = None) -> dict[str, Any]:
    payload = _payload(row)
    item_id, stem_hash, fingerprint = _identity_tuple(item)
    if variant is None:
        variant = int(row["current_variant"] or 1)
    pin_item(payload, phase, variant, item_id)
    def _add(key: str, value: str) -> None:
        lst = [str(x) for x in (payload.get(key) or [])]
        if value and value not in lst:
            lst.append(value)
        payload[key] = lst

    _add("seen_item_ids", item_id)
    _add("seen_stem_hashes", stem_hash)
    _add("seen_fingerprints", fingerprint)
    if phase in TEACHING_PHASES:
        _add("teaching_item_ids", item_id)
        _add("teaching_stem_hashes", stem_hash)
    payload["last_item"] = {
        "item_id": item_id,
        "stem_hash": stem_hash,
        "content_fingerprint": fingerprint,
        "phase": phase,
    }
    _save_payload(db, row, payload)
    return payload


def appeared_in_teaching_or_original(item: dict[str, Any], payload: dict[str, Any]) -> bool:
    seen = _seen_sets(payload)
    item_id, stem_hash, _fp = _identity_tuple(item)
    origin = payload.get("origin") or {}
    if item_id and item_id in seen["teaching_ids"]:
        return True
    if stem_hash and stem_hash in seen["teaching_hashes"]:
        return True
    if origin.get("item_id") and item_id == str(origin.get("item_id")):
        return True
    if origin.get("stem_hash") and stem_hash == str(origin.get("stem_hash")):
        return True
    return False


def current_item(db, row, phase: str, variant: int) -> dict[str, Any] | None:
    skill_code = str(row["skill_code"])
    pack = load_pack(skill_code)
    if not pack:
        return None
    slot = PACK_SLOT[phase]
    items = pack_items_for_slot(pack, slot)
    if not items:
        return None
    payload = _payload(row)
    prefer = max(0, variant - 1)
    allow = {_pinned_id(payload, phase, variant)} - {""}
    picked = _pick_unseen_pack_item(
        items,
        payload,
        skill_code=skill_code,
        phase=phase,
        prefer_index=prefer,
        allow_ids=allow,
    )
    if picked is None and phase in TEACHING_PHASES:
        # Worked/faded may re-show if the pool is exhausted; still never independent.
        picked = dict(items[min(len(items) - 1, prefer)])
    if picked is None:
        return None
    item = dict(picked)
    item["_ref"] = f"pack:{item.get('id')}"
    origin = payload.get("origin") or {}
    item["_is_original"] = bool(
        origin.get("stem_hash")
        and stem_normalized_hash(str(item.get("stem_html") or item.get("stem") or "")) == str(origin.get("stem_hash"))
    )
    item["choices"] = item.get("choices") or []
    item["skill_code"] = skill_code
    return normalize_item_for_render(item)


def _normalize_math_answer(raw: str) -> str:
    text = (raw or "").strip().lower()
    text = text.replace("−", "-").replace("–", "-")
    text = text.replace("≠", "!=").replace("=/=", "!=").replace("=/ ", "!=").replace("=/", "!=")
    text = text.replace("×", "*").replace("÷", "/")
    text = text.replace("$", "").replace(",", "")
    text = text.replace("hours", "").replace("hour", "")
    text = text.replace("kg/h", "").replace("kilograms per hour", "")
    text = "".join(text.split())
    return text


def _blank_matches(given: str, blank: dict[str, Any]) -> bool:
    got = _normalize_math_answer(given)
    if not got:
        return False
    options = [str(blank.get("correct") or "")] + [str(a) for a in (blank.get("alternates") or [])]
    return any(got == _normalize_math_answer(opt) for opt in options if str(opt).strip())


def _grade_blanks(item: dict[str, Any], form) -> tuple[bool, str]:
    blanks = item.get("blanks") or []
    bits = []
    ok = True
    for blank in blanks:
        if not isinstance(blank, dict):
            continue
        bid = str(blank.get("id") or "")
        given = str(form.get(bid) or form.get(f"blank_{bid}") or "").strip()
        bits.append(f"{bid}={given}")
        if not _blank_matches(given, blank):
            ok = False
    return ok, "; ".join(bits)


def _grade(item: dict[str, Any], selected: str) -> bool:
    expected = str(item.get("correct_answer") or "").strip()
    if not expected:
        return False
    given = (selected or "").strip()
    if len(expected) == 1 and expected.upper() in "ABCDE":
        if given[:1].upper() == expected.upper():
            return True
    alts = item.get("answer_alternates") or []
    compact = given.replace(" ", "").lower()
    if compact == expected.replace(" ", "").lower():
        return True
    for alt in alts:
        if compact == str(alt).replace(" ", "").lower():
            return True
    return given[:1].upper() == expected[:1].upper()


def independent_block_reasons(
    *,
    phase: str,
    is_correct: bool,
    solution_viewed: bool,
    hint_level: str,
    is_original: bool,
    saw_answer: bool,
    previously_seen_item: bool = False,
    previously_seen_stem: bool = False,
    appeared_in_teaching: bool = False,
) -> list[str]:
    if not is_correct:
        return []
    reasons: list[str] = []
    if phase not in INDEPENDENT_PHASES:
        reasons.append("Not an independent stage")
    if solution_viewed or saw_answer:
        reasons.append("Viewed solution")
    if hint_level == "critical":
        reasons.append("Used critical hint")
    if previously_seen_item or previously_seen_stem or appeared_in_teaching:
        reasons.append("Previously seen item")
    if is_original:
        reasons.append("Repeated original question")
    return reasons


def counts_as_independent(
    *,
    phase: str,
    is_correct: bool,
    solution_viewed: bool,
    hint_level: str,
    is_original: bool,
    saw_answer: bool,
    previously_seen_item: bool = False,
    previously_seen_stem: bool = False,
    appeared_in_teaching: bool = False,
) -> int:
    if not is_correct:
        return 0
    reasons = independent_block_reasons(
        phase=phase,
        is_correct=is_correct,
        solution_viewed=solution_viewed,
        hint_level=hint_level,
        is_original=is_original,
        saw_answer=saw_answer,
        previously_seen_item=previously_seen_item,
        previously_seen_stem=previously_seen_stem,
        appeared_in_teaching=appeared_in_teaching,
    )
    return 0 if reasons else 1


def delayed_locked(row) -> bool:
    if str(row["current_phase"] or "") != "delayed":
        return False
    due = parse_iso(row["delayed_available_at"] if "delayed_available_at" in row.keys() else None)
    if due is None:
        return False
    return now_utc() < due


def mark_cluster_mastered(db, user_id: int, skill_code: str, rows: list[dict[str, Any]]) -> None:
    import app as app_mod

    lk = app_mod._learner_key_for_user(user_id)
    for item in rows:
        domain = str(item.get("domain") or "")
        topic = str(item.get("topic") or "")
        try:
            q_index = int(item.get("q_index"))
        except (TypeError, ValueError):
            continue
        if not domain or not topic:
            continue
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
            (lk, domain, topic, q_index),
        )


def _advance(db, row, phase: str, is_correct: bool, item: dict[str, Any]) -> str:
    session_id = int(row["id"])
    variant = int(row["current_variant"] or 1)
    if not is_correct and phase in {"faded", "isomorphic", "transfer"}:
        db.execute(
            """
            UPDATE skill_repair_sessions
            SET current_phase = ?, current_variant = ?, status = 'active',
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (phase, variant + 1, session_id),
        )
        return phase
    if not is_correct and phase == "delayed":
        due = iso(now_utc() + timedelta(hours=DELAY_HOURS))
        db.execute(
            """
            UPDATE skill_repair_sessions
            SET current_phase = 'worked', current_variant = 1, status = 'needs_review',
                delayed_available_at = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (due, session_id),
        )
        return "worked"
    if phase == "worked":
        nxt = "faded"
    elif phase == "faded":
        nxt = "isomorphic"
    elif phase == "isomorphic":
        nxt = "transfer"
    elif phase == "transfer":
        nxt = "delayed"
        due = iso(now_utc() + timedelta(hours=DELAY_HOURS))
        db.execute(
            """
            UPDATE skill_repair_sessions
            SET current_phase = 'delayed', current_variant = 1, status = 'delayed_wait',
                delayed_available_at = COALESCE(delayed_available_at, ?), updated_at = datetime('now')
            WHERE id = ?
            """,
            (due, session_id),
        )
        return "delayed"
    else:
        nxt = "delayed"
    db.execute(
        """
        UPDATE skill_repair_sessions
        SET current_phase = ?, current_variant = 1, status = 'active', updated_at = datetime('now')
        WHERE id = ?
        """,
        (nxt, session_id),
    )
    return nxt


@skill_repair_bp.route("/<skill_code>/start")
def start(skill_code: str):
    import app as app_mod

    uid = _user_id()
    if skill_code not in ALLOWED_MICRO_SKILLS or load_pack(skill_code) is None:
        flash("This cluster needs further diagnosis before a Repair cycle. Open the original item for review only.")
        return redirect(url_for("practice_analytics"))
    db = app_mod.get_db()
    ensure_repair_tables(db)
    all_rows = app_mod._analytics_wrong_rows(db, uid)
    match_rows = [
        r for r in all_rows
        if primary_micro_skill(r)["code"] == skill_code
        and str(r.get("mastery_effective") or "") not in {"mastered", "archived"}
    ]
    representative = match_rows[0] if match_rows else None
    row = start_repair_session(db, uid, skill_code, representative)
    if row is None:
        flash("This skill does not have a complete repair set yet.")
        return redirect(url_for("practice_analytics"))
    phase = str(row["current_phase"] or "worked")
    return redirect(url_for("skill_repair.phase_view", skill_code=skill_code, phase=phase))


@skill_repair_bp.route("/<skill_code>/<phase>", methods=["GET"])
def phase_view(skill_code: str, phase: str):
    import app as app_mod

    if phase not in PHASES:
        abort(404)
    uid = _user_id()
    db = app_mod.get_db()
    ensure_repair_tables(db)
    row = get_session_row(db, uid, skill_code)
    if row is None:
        return redirect(url_for("skill_repair.start", skill_code=skill_code))
    current = str(row["current_phase"] or "worked")
    if phase != current:
        return redirect(url_for("skill_repair.phase_view", skill_code=skill_code, phase=current))
    if delayed_locked(row):
        due = parse_iso(row["delayed_available_at"])
        return render_template(
            "skill_repair_wait.html",
            skill_code=skill_code,
            skill_title=ALLOWED_MICRO_SKILLS.get(skill_code) or skill_code,
            due_at=row["delayed_available_at"],
            hours_left=max(0, int(((due - now_utc()).total_seconds() if due else 0) / 3600)),
            status=row["status"],
            session_id=int(row["id"]),
            delayed_available_at=row["delayed_available_at"],
        )
    item = current_item(db, row, phase, int(row["current_variant"] or 1))
    if item is None:
        flash("This skill does not have a complete unseen repair set yet. Use similar items from Analytics.")
        return redirect(url_for("practice_analytics"))
    pin_current_item(db, row, phase, int(row["current_variant"] or 1), item)
    db.commit()
    choices = item.get("choices") or []
    letters = [_letter_for_index(i) for i in range(len(choices))]
    mastered = str(row["status"] or "") == "mastered"
    payload = _payload(row)
    preview_independent = counts_as_independent(
        phase=phase,
        is_correct=True,
        solution_viewed=False,
        hint_level="none",
        is_original=bool(item.get("_is_original")),
        saw_answer=False,
        previously_seen_item=appeared_in_teaching_or_original(item, payload),
        previously_seen_stem=appeared_in_teaching_or_original(item, payload),
        appeared_in_teaching=appeared_in_teaching_or_original(item, payload),
    )
    return render_template(
        "skill_repair_phase.html",
        skill_code=skill_code,
        skill_title=ALLOWED_MICRO_SKILLS.get(skill_code) or (load_pack(skill_code) or {}).get("title") or skill_code,
        phase=phase,
        item=item,
        letters=letters,
        variant=int(row["current_variant"] or 1),
        status=row["status"],
        mastered=mastered,
        show_mastered=mastered,
        remediation=str(row["status"] or "") == "needs_review" or int(row["current_variant"] or 1) > 1,
        preview_independent=preview_independent,
    )


@skill_repair_bp.route("/<skill_code>/event", methods=["POST"])
def track_event(skill_code: str):
    import app as app_mod

    uid = _user_id()
    db = app_mod.get_db()
    row = get_session_row(db, uid, skill_code)
    if row is None:
        abort(404)
    payload = request.get_json(silent=True) or {}
    kind = str(request.form.get("kind") or payload.get("kind") or "")
    if kind == "solution":
        db.execute(
            "UPDATE skill_repair_sessions SET saw_answer = 1, updated_at = datetime('now') WHERE id = ?",
            (int(row["id"]),),
        )
        db.commit()
    item = current_item(db, row, str(row["current_phase"]), int(row["current_variant"] or 1)) or {}
    if kind == "solution":
        return jsonify({
            "ok": True,
            "html": item.get("solution_html") or "",
            "answer": item.get("correct_answer") or item.get("correct_answer_display") or "",
        })
    if kind in {"hint_light", "hint_critical"}:
        hint = item.get("light_hint") if kind == "hint_light" else item.get("critical_hint")
        return jsonify({"ok": True, "hint": hint or ""})
    return jsonify({"ok": True})


@skill_repair_bp.route("/<skill_code>/submit", methods=["POST"])
def submit(skill_code: str):
    import app as app_mod

    uid = _user_id()
    db = app_mod.get_db()
    ensure_repair_tables(db)
    row = get_session_row(db, uid, skill_code)
    if row is None:
        return redirect(url_for("skill_repair.start", skill_code=skill_code))
    phase = (request.form.get("phase") or str(row["current_phase"])).strip()
    if phase not in PHASES:
        abort(400)
    if delayed_locked(row) and phase == "delayed":
        return redirect(url_for("skill_repair.phase_view", skill_code=skill_code, phase="delayed"))
    item = current_item(db, row, phase, int(row["current_variant"] or 1))
    if item is None:
        flash("Repair item missing.")
        return redirect(url_for("practice_analytics"))
    if phase == "worked" or item.get("question_kind") == "worked_example":
        payload = _payload(row)
        payload.setdefault("instruction_completed_at", iso(now_utc()))
        _save_payload(db, row, payload)
        remember_shown_item(db, row, "worked", item)
        nxt = _advance(db, row, "worked", True, item)
        db.commit()
        return redirect(url_for("skill_repair.phase_view", skill_code=skill_code, phase=nxt))
    selected = (request.form.get("selected_answer") or "").strip()
    blanks = item.get("blanks") or []
    if phase == "faded" and blanks:
        is_correct, selected = _grade_blanks(item, request.form)
        if not selected:
            flash("Complete the faded steps before submitting.")
            return redirect(url_for("skill_repair.phase_view", skill_code=skill_code, phase=phase))
    elif not selected:
        flash("Choose an answer before submitting.")
        return redirect(url_for("skill_repair.phase_view", skill_code=skill_code, phase=phase))
    else:
        is_correct = _grade(item, selected)
    payload = _payload(row)
    solution_viewed = (request.form.get("solution_viewed") or "0") == "1"
    hint_level = (request.form.get("hint_level") or "none").strip() or "none"
    is_original = bool(item.get("_is_original"))
    seen_before_submit = appeared_in_teaching_or_original(item, payload)
    previously_seen_item = seen_before_submit
    previously_seen_stem = seen_before_submit
    appeared_teaching = seen_before_submit
    block_reasons = independent_block_reasons(
        phase=phase,
        is_correct=is_correct,
        solution_viewed=solution_viewed,
        hint_level=hint_level,
        is_original=is_original,
        saw_answer=False,
        previously_seen_item=previously_seen_item,
        previously_seen_stem=previously_seen_stem,
        appeared_in_teaching=appeared_teaching,
    )
    independent = 0 if (not is_correct or block_reasons) else 1
    remember_shown_item(db, row, phase, item)
    db.execute(
        """
        INSERT INTO skill_repair_events (
            session_id, phase, item_ref, selected_answer, is_correct,
            counts_as_independent, solution_viewed, hint_level, is_original_item
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(row["id"]),
            phase,
            str(item.get("_ref") or item.get("item_id") or ""),
            selected,
            1 if is_correct else 0,
            independent,
            1 if solution_viewed else 0,
            hint_level,
            1 if is_original else 0,
        ),
    )
    nxt = _advance(db, row, phase, is_correct, item)
    row = db.execute("SELECT * FROM skill_repair_sessions WHERE id = ?", (int(row["id"]),)).fetchone()
    if phase == "delayed" and independent == 1:
        all_rows = app_mod._analytics_wrong_rows(db, uid)
        cluster_rows = [
            r for r in all_rows if primary_micro_skill(r)["code"] == skill_code
        ]
        mark_cluster_mastered(db, uid, skill_code, cluster_rows)
        db.execute(
            """
            UPDATE skill_repair_sessions
            SET status = 'mastered', mastered_at = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (iso(now_utc()), int(row["id"])),
        )
        db.commit()
        flash("Mastered after an independent delayed pass on a new item.")
        return redirect(url_for("practice_analytics"))
    db.commit()
    session["skill_repair_feedback"] = {
        "skill_code": skill_code,
        "phase": phase,
        "is_correct": is_correct,
        "yours": selected,
        "key": item.get("correct_answer") or "",
        "core_idea": item.get("core_idea") or "",
        "common_mistake": item.get("common_mistake") or "",
        "next_phase": nxt,
        "remediation": not is_correct,
        "independent": independent,
        "original": is_original,
        "block_reasons": block_reasons,
        "item_id": item.get("item_id") or "",
        "stem_hash": item.get("stem_hash") or "",
        "content_fingerprint": item.get("content_fingerprint") or "",
        "counts_as_independent": independent,
    }
    session.modified = True
    return redirect(url_for("skill_repair.feedback", skill_code=skill_code))


@skill_repair_bp.route("/<skill_code>/feedback")
def feedback(skill_code: str):
    payload = session.get("skill_repair_feedback") or {}
    if payload.get("skill_code") != skill_code:
        return redirect(url_for("skill_repair.start", skill_code=skill_code))
    nxt = str(payload.get("next_phase") or "faded")
    return render_template(
        "skill_repair_feedback.html",
        skill_code=skill_code,
        feedback=payload,
        continue_href=url_for("skill_repair.phase_view", skill_code=skill_code, phase=nxt),
    )
