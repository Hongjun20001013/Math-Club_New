"""Repair-this-skill layer on the existing mistake log.

Does not replace Session Report, Coach Walkthrough, Miss Quiz, or Analytics.
Independent of SKILL_LOOP_PILOT so students can repair while the A/B flag is off.
Original-item redo never counts as independent_pass or auto-mastery.
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
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

LINEAR_RATE_CODE = "sat.alg.linear_rate_remaining"
LINEAR_RATE_TITLE = "Linear remaining quantity at a constant rate"
LINEAR_RATE_HINTS = (
    "remain",
    "remaining",
    "constant rate",
    "per hour",
    "pounds remain",
    "gallons remain",
)
PHASES = ("worked", "faded", "isomorphic", "transfer", "delayed")
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


def primary_micro_skill(row: dict[str, Any]) -> dict[str, Any]:
    stem = str(row.get("stem_html") or "").lower()
    title = str(row.get("knowledge_title") or "").lower()
    blob = f"{stem} {title}"
    if any(h in blob for h in LINEAR_RATE_HINTS) and ("rate" in blob or "remain" in blob):
        return {
            "code": LINEAR_RATE_CODE,
            "title": LINEAR_RATE_TITLE,
            "has_pack": True,
        }
    sec = str(row.get("knowledge_section") or "").strip()
    title_h = str(row.get("knowledge_title") or row.get("topic_title") or sec or "This skill")
    domain = str(row.get("domain") or "sat")
    topic = str(row.get("topic") or "misc")
    code = f"bank.{domain}.{sec or topic}"
    return {"code": code, "title": title_h, "has_pack": load_pack(code) is not None}


def _priority_for_count(count: int, diagnosis_level: str) -> str:
    if count >= 4 or diagnosis_level == "High":
        return "High"
    if count >= 2 or diagnosis_level == "Medium":
        return "Medium"
    return "Watch"


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
                "tags": Counter(),
                "pitfalls": Counter(),
            }
            buckets[key] = bucket
        bucket["rows"].append(row)
        diag = str(row.get("diagnosis_label") or row.get("diagnosis_id") or "Concept gap")
        bucket["diagnoses"][diag] += 1
        for tag in row.get("tag_labels") or []:
            bucket["tags"][str(tag)] += 1
        pack = row.get("pattern_pack") or {}
        pitfall = str(pack.get("pitfall") or "").strip()
        if pitfall:
            bucket["pitfalls"][pitfall] += 1

    clusters: list[dict[str, Any]] = []
    for key, bucket in buckets.items():
        rows_sorted = sorted(
            bucket["rows"],
            key=lambda r: str(r.get("when") or ""),
            reverse=True,
        )
        representative = rows_sorted[0]
        common_diag = bucket["diagnoses"].most_common(1)
        common_pitfall = bucket["pitfalls"].most_common(1)
        common_tag = bucket["tags"].most_common(1)
        stuck = ""
        if common_pitfall:
            stuck = common_pitfall[0][0]
        elif common_tag:
            stuck = f"Often tagged: {common_tag[0][0]}"
        elif common_diag:
            stuck = common_diag[0][0]
        level = str((representative.get("pattern_pack") or {}).get("level") or "")
        diag_level = "High" if bucket["diagnoses"] and common_diag and common_diag[0][1] >= 3 else (
            "Medium" if len(rows_sorted) >= 2 else "Low"
        )
        if level:
            diag_level = level
        priority = _priority_for_count(len(rows_sorted), diag_level)
        stem = str(representative.get("stem_html") or "")
        stem_plain = (
            stem.replace("<p>", " ")
            .replace("</p>", " ")
            .replace("<br>", " ")
            .replace("<br/>", " ")
        )
        try:
            repair_href = url_for("skill_repair.start", skill_code=key)
        except RuntimeError:
            repair_href = f"/practice/repair/{key}/start"
        clusters.append(
            {
                "code": key,
                "title": bucket["title"],
                "has_pack": bucket["has_pack"],
                "miss_count": len(rows_sorted),
                "priority": priority,
                "common_stuck": stuck or "Relearn the core move, then try a new item.",
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


def _bank_queue(app_mod, representative: dict[str, Any]) -> dict[str, Any]:
    domain = str(representative.get("domain") or "")
    topic = str(representative.get("topic") or "")
    origin = int(representative.get("q_index") or 0)
    section = str(representative.get("knowledge_section") or "")
    tex = app_mod.BANKS.get(domain, {}).get(topic)
    questions = app_mod.get_questions_for_topic(domain, topic, tex) if tex else []
    same: list[int] = []
    other: list[int] = []
    for i, q in enumerate(questions):
        if i == origin:
            continue
        if section and str(q.get("knowledge_section") or "") == section:
            same.append(i)
        else:
            other.append(i)
    pool = same + other
    faded = pool[0] if pool else None
    iso_item = pool[1] if len(pool) > 1 else (pool[0] if pool else None)
    transfer = other[0] if other else (pool[2] if len(pool) > 2 else iso_item)
    delayed = None
    for idx in pool:
        if idx not in {faded, iso_item, transfer}:
            delayed = idx
            break
    if delayed is None:
        delayed = iso_item or faded
    return {
        "origin": {"domain": domain, "topic": topic, "q_index": origin},
        "faded": {"domain": domain, "topic": topic, "q_index": faded} if faded is not None else None,
        "isomorphic": {"domain": domain, "topic": topic, "q_index": iso_item} if iso_item is not None else None,
        "transfer": {"domain": domain, "topic": topic, "q_index": transfer} if transfer is not None else None,
        "delayed": {"domain": domain, "topic": topic, "q_index": delayed} if delayed is not None else None,
        "alts": {
            "faded": [{"domain": domain, "topic": topic, "q_index": i} for i in pool[1:4]],
            "isomorphic": [{"domain": domain, "topic": topic, "q_index": i} for i in pool[2:6]],
            "transfer": [{"domain": domain, "topic": topic, "q_index": i} for i in other[1:5] or pool[3:7]],
            "delayed": [{"domain": domain, "topic": topic, "q_index": i} for i in pool[3:8]],
        },
    }


def start_repair_session(db, user_id: int, skill_code: str, representative: dict[str, Any] | None) -> Any:
    import app as app_mod

    pack = load_pack(skill_code)
    payload: dict[str, Any] = {"source": "pack" if pack else "bank"}
    if representative:
        payload["origin"] = {
            "domain": representative.get("domain"),
            "topic": representative.get("topic"),
            "q_index": representative.get("q_index"),
            "pr_id": representative.get("pr_id"),
        }
        if not pack:
            payload.update(_bank_queue(app_mod, representative))
    existing = get_session_row(db, user_id, skill_code)
    if existing is not None and str(existing["status"] or "") in {"active", "delayed_wait", "needs_review"}:
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


def _bank_question(app_mod, ref: dict[str, Any] | None) -> dict[str, Any] | None:
    if not ref or ref.get("q_index") is None:
        return None
    domain = str(ref.get("domain") or "")
    topic = str(ref.get("topic") or "")
    q_index = int(ref["q_index"])
    tex = app_mod.BANKS.get(domain, {}).get(topic)
    questions = app_mod.get_questions_for_topic(domain, topic, tex) if tex else []
    if q_index < 0 or q_index >= len(questions):
        return None
    q = dict(questions[q_index])
    q["_ref"] = f"bank:{domain}:{topic}:{q_index}"
    q["_is_original"] = False
    return q


def current_item(db, row, phase: str, variant: int) -> dict[str, Any] | None:
    import app as app_mod

    skill_code = str(row["skill_code"])
    pack = load_pack(skill_code)
    if pack:
        slot = PACK_SLOT[phase]
        items = pack_items_for_slot(pack, slot)
        if not items:
            return None
        idx = max(0, min(len(items) - 1, variant - 1))
        item = dict(items[idx])
        item["_ref"] = f"pack:{item.get('id')}"
        item["_is_original"] = False
        item["choices"] = item.get("choices") or []
        return item
    payload = _payload(row)
    origin = payload.get("origin") or {}
    if phase == "worked":
        q = _bank_question(app_mod, origin)
        if q is None:
            return None
        q["question_kind"] = "worked_example"
        q["_is_original"] = True
        q["_ref"] = f"bank:{origin.get('domain')}:{origin.get('topic')}:{origin.get('q_index')}:worked"
        q["worked_steps"] = []
        expl = str(q.get("explanation_en") or "").strip()
        if expl:
            q["worked_steps"] = [{"step": 1, "do": expl, "why": "This is the original missed item used only as a worked example."}]
        q["core_idea"] = str(q.get("knowledge_section_title_en") or q.get("knowledge_section") or "")
        return q
    key = phase
    ref = payload.get(key)
    alts = (payload.get("alts") or {}).get(key) or []
    chosen = ref
    if variant > 1 and alts:
        chosen = alts[min(len(alts) - 1, variant - 2)]
    q = _bank_question(app_mod, chosen)
    if q is None:
        return None
    origin_idx = origin.get("q_index")
    q["_is_original"] = (
        str(chosen.get("domain")) == str(origin.get("domain"))
        and str(chosen.get("topic")) == str(origin.get("topic"))
        and int(chosen.get("q_index") or -1) == int(origin_idx if origin_idx is not None else -2)
    )
    if phase == "faded":
        q["given_steps"] = [
            {"label": "Given", "text": "Name the target quantity and the rate or relationship before computing."}
        ]
        q["light_hint"] = "Write the knowns, the unknown, and one equation. Do not jump to arithmetic."
    return q


def _grade(item: dict[str, Any], selected: str) -> bool:
    expected = str(item.get("correct_answer") or "").strip()
    if not expected:
        return False
    given = (selected or "").strip()
    if len(expected) == 1 and expected.upper() in "ABCDE":
        return given[:1].upper() == expected.upper()
    alts = item.get("answer_alternates") or []
    compact = given.replace(" ", "").lower()
    if compact == expected.replace(" ", "").lower():
        return True
    for alt in alts:
        if compact == str(alt).replace(" ", "").lower():
            return True
    return given[:1].upper() == expected[:1].upper()


def _used_refs(db, session_id: int, phase: str) -> set[str]:
    rows = db.execute(
        "SELECT item_ref FROM skill_repair_events WHERE session_id = ? AND phase = ?",
        (session_id, phase),
    ).fetchall()
    return {str(r["item_ref"]) for r in rows}


def counts_as_independent(
    *,
    phase: str,
    is_correct: bool,
    solution_viewed: bool,
    hint_level: str,
    is_original: bool,
    saw_answer: bool,
) -> int:
    if not is_correct:
        return 0
    if phase not in {"isomorphic", "transfer", "delayed"}:
        return 0
    if is_original or saw_answer or solution_viewed or hint_level == "critical":
        return 0
    return 1


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
                delayed_available_at = ?, updated_at = datetime('now')
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
            skill_title=load_pack(skill_code).get("title") if load_pack(skill_code) else skill_code,
            due_at=row["delayed_available_at"],
            hours_left=max(0, int(((due - now_utc()).total_seconds() if due else 0) / 3600)),
            status=row["status"],
        )
    item = current_item(db, row, phase, int(row["current_variant"] or 1))
    if item is None:
        flash("This skill does not have a complete repair set yet. Use similar items from Analytics.")
        return redirect(url_for("practice_analytics"))
    choices = item.get("choices") or []
    letters = [_letter_for_index(i) for i in range(len(choices))]
    mastered = str(row["status"] or "") == "mastered"
    return render_template(
        "skill_repair_phase.html",
        skill_code=skill_code,
        skill_title=(load_pack(skill_code) or {}).get("title") or skill_code,
        phase=phase,
        item=item,
        letters=letters,
        variant=int(row["current_variant"] or 1),
        status=row["status"],
        mastered=mastered,
        show_mastered=mastered,
        remediation=str(row["status"] or "") == "needs_review" or int(row["current_variant"] or 1) > 1,
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
    if kind in {"solution", "hint_critical"}:
        db.execute(
            "UPDATE skill_repair_sessions SET saw_answer = 1, updated_at = datetime('now') WHERE id = ?",
            (int(row["id"]),),
        )
        db.commit()
    item = current_item(db, row, str(row["current_phase"]), int(row["current_variant"] or 1)) or {}
    if kind == "solution":
        steps = item.get("worked_steps") or []
        text = "\n".join(
            f"Step {s.get('step')}: {s.get('do')} (Why: {s.get('why')})"
            for s in steps
            if isinstance(s, dict)
        ) or str(item.get("explanation_en") or item.get("explanation_check") or "")
        return jsonify({
            "ok": True,
            "solution": text,
            "answer": item.get("correct_answer") or item.get("correct_answer_display") or "",
        })
    if kind in {"hint_light", "hint_critical"}:
        hint = item.get("light_hint") if kind == "hint_light" else item.get("critical_hint")
        if not hint and kind == "hint_light":
            hint = "Name the target quantity and write one equation before computing."
        if not hint:
            hint = str(item.get("core_idea") or "Re-read the worked example, then try a new item.")
        return jsonify({"ok": True, "hint": hint})
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
        nxt = _advance(db, row, "worked", True, item)
        db.commit()
        return redirect(url_for("skill_repair.phase_view", skill_code=skill_code, phase=nxt))
    selected = (request.form.get("selected_answer") or "").strip()
    if not selected:
        flash("Choose an answer before submitting.")
        return redirect(url_for("skill_repair.phase_view", skill_code=skill_code, phase=phase))
    is_correct = _grade(item, selected)
    solution_viewed = (request.form.get("solution_viewed") or "0") == "1" or int(row["saw_answer"] or 0) == 1
    hint_level = (request.form.get("hint_level") or "none").strip() or "none"
    is_original = bool(item.get("_is_original"))
    independent = counts_as_independent(
        phase=phase,
        is_correct=is_correct,
        solution_viewed=solution_viewed,
        hint_level=hint_level,
        is_original=is_original,
        saw_answer=int(row["saw_answer"] or 0) == 1,
    )
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
            str(item.get("_ref") or ""),
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
