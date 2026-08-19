"""Skill-loop pilot: six-phase learning cycle behind SKILL_LOOP_PILOT.

Does not read or write question_bank.json. Feature flag defaults off.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from scripts.skill_loop_assignment import (
    DEFAULT_DEV_SALT,
    EXPERIMENT_ID,
    SALT_VERSION,
    is_excluded_from_analysis,
    propose_arm,
)

SKILL_CODE = "sat.alg.linear_rate_remaining"
PHASES_B = ("precheck", "instruction", "faded", "independent", "transfer", "delayed")
PHASES_A = ("precheck", "control", "delayed")
DELAY_HOURS = 48
DELAY_MAX_HOURS = 168
SCORED_PHASES = {"precheck", "faded", "independent", "transfer", "delayed"}

skill_loop_bp = Blueprint("skill_loop", __name__, url_prefix="/practice/skill-loop")

CONCLUSION_LABELS = ("有效", "提升", "显著", "优于", "significant", "outperform", "score lift")
TRANSFER_ITEMS_EXPECTED = 2
DELAYED_ITEMS_EXPECTED = 2


class SkillLoopConfigError(RuntimeError):
    """Raised when production is missing required pilot configuration."""


def production_runtime() -> bool:
    return (
        os.environ.get("RENDER", "").strip().lower() in ("true", "1", "yes")
        or os.environ.get("FLASK_ENV", "").strip().lower() == "production"
    )


def now_utc() -> datetime:
    """Server UTC clock. Tests may inject SKILL_LOOP_CLOCK only when TESTING."""
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
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def production_salt_missing() -> bool:
    return production_runtime() and not (os.environ.get("SKILL_LOOP_ASSIGN_SALT") or "").strip()


def skill_loop_enabled() -> bool:
    if production_salt_missing():
        try:
            current_app.logger.error(
                "SKILL_LOOP_PILOT disabled: SKILL_LOOP_ASSIGN_SALT is required in production"
            )
        except Exception:
            pass
        return False
    env = (os.environ.get("SKILL_LOOP_PILOT") or "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    try:
        return bool(current_app.config.get("SKILL_LOOP_PILOT"))
    except Exception:
        return False


def assign_salt() -> str:
    salt = (os.environ.get("SKILL_LOOP_ASSIGN_SALT") or "").strip()
    if salt:
        return salt
    if production_runtime():
        raise SkillLoopConfigError(
            "SKILL_LOOP_ASSIGN_SALT is required in production; refusing dev-salt fallback"
        )
    return DEFAULT_DEV_SALT


def _db() -> sqlite3.Connection:
    from app import get_db

    return get_db()


def emit(
    db: sqlite3.Connection,
    name: str,
    user_id: int | None,
    run_id: int | None,
    item_id: str | None,
    payload: dict | None = None,
) -> None:
    db.execute(
        """
        INSERT INTO skill_loop_events (event_name, user_id, run_id, item_id, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, user_id, run_id, item_id, json.dumps(payload or {}, ensure_ascii=False), iso(now_utc())),
    )


def published_item(db: sqlite3.Connection, item_id: str) -> sqlite3.Row | None:
    return db.execute(
        """
        SELECT * FROM skill_loop_items
        WHERE id = ? AND review_status = 'reviewed' AND publish_status = 'published'
        ORDER BY version DESC LIMIT 1
        """,
        (item_id,),
    ).fetchone()


def item_for_slot(db: sqlite3.Connection, skill_code: str, slot: str, variant: int) -> sqlite3.Row | None:
    return db.execute(
        """
        SELECT * FROM skill_loop_items
        WHERE skill_code = ? AND slot = ? AND variant_index = ?
          AND review_status = 'reviewed' AND publish_status = 'published'
        ORDER BY version DESC LIMIT 1
        """,
        (skill_code, slot, variant),
    ).fetchone()


def teaching_fields(row: sqlite3.Row) -> dict[str, Any]:
    blob = json.loads(row["faded_json"] or "{}") if row["faded_json"] else {}
    steps = json.loads(row["worked_steps_json"] or "[]")
    light = str(blob.get("light_hint") or "").strip()
    critical = str(blob.get("critical_hint") or "").strip()
    if not light:
        light = (
            "Use the two snapshots to identify the constant rate first. "
            "Do not jump to the final numerical answer yet."
        )
    if not critical:
        bits = [str(step.get("do") or "") for step in steps[:2]]
        critical = " ".join(b for b in bits if b) or (
            "Write Q(t) = Q0 − r t, find r from a snapshot, then solve for the unknown."
        )
    return {
        "light_hint": light,
        "critical_hint": critical,
        "core_idea": str(blob.get("core_idea") or "A quantity changing at a constant rate follows Q(t) = Q0 − r t."),
        "common_mistake": str(
            blob.get("common_mistake")
            or "Mixing up total time from the start with additional time after a snapshot."
        ),
        "explanation_check": str(blob.get("explanation_check") or ""),
        "unknown_change": str(blob.get("unknown_change") or ""),
        "worked_steps": steps,
        "correct_answer": str(row["correct_answer"] or ""),
        "choices": json.loads(row["choices_json"] or "[]"),
    }


def display_correct_answer(row: sqlite3.Row) -> str:
    fields = teaching_fields(row)
    ans = fields["correct_answer"]
    choices = fields["choices"]
    if ans in "ABCD" and choices and (ord(ans) - 65) < len(choices):
        return f"{ans}. {choices[ord(ans) - 65]}"
    return ans


def public_payload(row: sqlite3.Row, phase: str) -> dict[str, Any]:
    choices = json.loads(row["choices_json"] or "[]")
    data: dict[str, Any] = {
        "id": row["id"],
        "version": int(row["version"]),
        "slot": row["slot"],
        "stem_html": row["stem_html"],
        "choices": choices,
        "question_kind": row["question_kind"],
        "variant_index": int(row["variant_index"]),
    }
    if phase == "instruction":
        teach = teaching_fields(row)
        data["worked_steps"] = teach["worked_steps"]
        data["explanation_check"] = teach["explanation_check"]
        data["correct_answer_display"] = display_correct_answer(row)
    if phase == "faded" and row["faded_json"]:
        faded = json.loads(row["faded_json"])
        data["given_steps"] = faded.get("given_steps") or []
        data["blanks"] = [
            {"id": b.get("id"), "prompt": b.get("prompt")} for b in (faded.get("blanks") or [])
        ]
    return data


def answers_equivalent(expected: str, alternates: list[str], given: str) -> bool:
    def norm(s: str) -> str:
        return "".join(str(s or "").strip().lower().split())

    g = norm(given)
    if not g:
        return False
    if g == norm(expected):
        return True
    letters = "ABCD"
    if expected in letters and g == expected.lower():
        return True
    return any(g == norm(a) for a in alternates)


def grade_row(row: sqlite3.Row, selected: str, faded_fields: dict | None = None) -> bool:
    if row["question_kind"] == "faded":
        faded = json.loads(row["faded_json"] or "{}")
        fields = faded_fields or {}
        for blank in faded.get("blanks") or []:
            got = str(fields.get(blank.get("id")) or "")
            alts = list(blank.get("alternates") or [])
            if not answers_equivalent(str(blank.get("correct") or ""), alts, got):
                return False
        return True
    alts = json.loads(row["answer_alternates_json"] or "[]")
    return answers_equivalent(str(row["correct_answer"] or ""), alts, selected)


def get_assignment(db: sqlite3.Connection, user_id: int, skill_code: str | None = None) -> sqlite3.Row | None:
    return db.execute(
        """
        SELECT * FROM skill_loop_assignments
        WHERE experiment_id = ? AND user_id = ?
        """,
        (EXPERIMENT_ID, user_id),
    ).fetchone()


def ensure_assignment(
    db: sqlite3.Connection, user_id: int, skill_code: str, role: str = "", username: str = ""
) -> sqlite3.Row:
    row = get_assignment(db, user_id, skill_code)
    if row is not None:
        return row
    arm, digest = propose_arm(user_id, assign_salt(), EXPERIMENT_ID)
    cur = db.execute(
        """
        INSERT INTO skill_loop_assignments (
            experiment_id, user_id, skill_code, arm, assignment_source,
            hash_hex, salt_version, assigned_at
        ) VALUES (?, ?, ?, ?, 'hash', ?, ?, ?)
        ON CONFLICT(experiment_id, user_id) DO NOTHING
        """,
        (EXPERIMENT_ID, user_id, skill_code, arm, digest, SALT_VERSION, iso(now_utc())),
    )
    out = get_assignment(db, user_id, skill_code)
    if out is None:
        raise RuntimeError("assignment insert failed")
    if int(cur.rowcount or 0) == 1:
        emit(db, "loop_assigned", user_id, None, None, {"arm": out["arm"], "source": "hash"})
    return out


def admin_override_arm(
    db: sqlite3.Connection,
    user_id: int,
    skill_code: str,
    arm: str,
    operator_id: int,
    reason: str,
) -> None:
    if arm not in ("A", "B"):
        raise ValueError("arm")
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("reason required")
    now = iso(now_utc())
    db.execute(
        """
        INSERT INTO skill_loop_assignments (
            experiment_id, user_id, skill_code, arm, assignment_source,
            salt_version, assigned_by, override_reason, assigned_at
        ) VALUES (?, ?, ?, ?, 'admin', ?, ?, ?, ?)
        ON CONFLICT(experiment_id, user_id) DO UPDATE SET
            arm = excluded.arm,
            assignment_source = 'admin',
            assigned_by = excluded.assigned_by,
            override_reason = excluded.override_reason,
            assigned_at = excluded.assigned_at
        """,
        (EXPERIMENT_ID, user_id, skill_code, arm, SALT_VERSION, operator_id, reason, now),
    )
    emit(
        db,
        "loop_assigned",
        user_id,
        None,
        None,
        {"arm": arm, "source": "admin", "operator_id": operator_id, "reason": reason},
    )
    db.execute(
        "UPDATE skill_loop_runs SET arm = ? WHERE user_id = ? AND skill_code = ?",
        (arm, user_id, skill_code),
    )


def get_run(db: sqlite3.Connection, user_id: int, skill_code: str) -> sqlite3.Row | None:
    return db.execute(
        """
        SELECT * FROM skill_loop_runs
        WHERE user_id = ? AND skill_code = ?
        ORDER BY id DESC LIMIT 1
        """,
        (user_id, skill_code),
    ).fetchone()


def ensure_run(db: sqlite3.Connection, user_id: int, skill_code: str, arm: str) -> sqlite3.Row:
    row = get_run(db, user_id, skill_code)
    if row is not None:
        return row
    db.execute(
        """
        INSERT INTO skill_loop_runs (
            user_id, skill_code, experiment_id, arm, mastery_status,
            current_phase, current_variant, started_at, created_at
        ) VALUES (?, ?, ?, ?, 'learning', 'precheck', 1, ?, ?)
        """,
        (user_id, skill_code, EXPERIMENT_ID, arm, iso(now_utc()), iso(now_utc())),
    )
    row = get_run(db, user_id, skill_code)
    if row is None:
        raise RuntimeError("run insert failed")
    emit(db, "run_started", user_id, int(row["id"]), None, {"arm": arm})
    return row


def delayed_window_state(run: sqlite3.Row, now: datetime | None = None) -> str:
    start = parse_iso(run["instruction_completed_at"] if "instruction_completed_at" in run.keys() else None)
    if start is None:
        return "not_started"
    elapsed = (now or now_utc()) - start
    if elapsed < timedelta(hours=DELAY_HOURS):
        return "locked"
    if elapsed <= timedelta(hours=DELAY_MAX_HOURS):
        return "due"
    return "overdue"


def delayed_elapsed_hours(run: sqlite3.Row, now: datetime | None = None) -> float | None:
    start = parse_iso(run["instruction_completed_at"] if "instruction_completed_at" in run.keys() else None)
    if start is None:
        return None
    return ((now or now_utc()) - start).total_seconds() / 3600.0


def delayed_unlocked(run: sqlite3.Row) -> bool:
    return delayed_window_state(run) in ("due", "overdue")


def delayed_in_window(run: sqlite3.Row) -> bool:
    """True when delayed check is due on time (48–168h inclusive)."""
    return delayed_window_state(run) == "due"


def allowed_phases(arm: str) -> tuple[str, ...]:
    return PHASES_A if arm == "A" else PHASES_B


def next_phase(arm: str, phase: str, variant: int) -> tuple[str, int]:
    if phase == "independent" and variant == 1:
        return "independent", 2
    if phase == "transfer" and variant == 1:
        return "transfer", 2
    if phase == "delayed" and variant == 1:
        return "delayed", 2
    seq = allowed_phases(arm)
    try:
        idx = seq.index(phase)
    except ValueError:
        return seq[0], 1
    if idx + 1 >= len(seq):
        return seq[-1], variant
    return seq[idx + 1], 1


def attempted_item_ids(db: sqlite3.Connection, run_id: int, phase: str) -> set[str]:
    rows = db.execute(
        "SELECT item_id FROM skill_loop_step_results WHERE run_id = ? AND phase = ?",
        (run_id, phase),
    ).fetchall()
    return {str(r[0]) for r in rows if r[0]}


def next_unused_variant(
    db: sqlite3.Connection, skill_code: str, slot: str, run_id: int, phase: str
) -> int | None:
    used = attempted_item_ids(db, run_id, phase)
    rows = db.execute(
        """
        SELECT variant_index, id FROM skill_loop_items
        WHERE skill_code = ? AND slot = ?
          AND review_status = 'reviewed' AND publish_status = 'published'
        ORDER BY variant_index
        """,
        (skill_code, slot),
    ).fetchall()
    for row in rows:
        if str(row["id"]) not in used:
            return int(row["variant_index"])
    return None


def independent_success_count(db: sqlite3.Connection, run_id: int) -> int:
    row = db.execute(
        """
        SELECT COUNT(*) AS n FROM skill_loop_step_results
        WHERE run_id = ? AND phase = 'independent' AND counts_as_independent = 1
        """,
        (run_id,),
    ).fetchone()
    return int(row["n"] if row["n"] is not None else row[0])


def set_pending_remediation(
    db: sqlite3.Connection, run_id: int, user_id: int, payload: dict[str, Any]
) -> None:
    emit(db, "remediation_pending", user_id, run_id, payload.get("item_id"), payload)


def pending_remediation(db: sqlite3.Connection, run_id: int) -> dict[str, Any] | None:
    row = db.execute(
        """
        SELECT payload_json FROM skill_loop_events
        WHERE run_id = ? AND event_name = 'remediation_pending'
        ORDER BY id DESC LIMIT 1
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["payload_json"] or "{}")
    except json.JSONDecodeError:
        return None


def next_action_copy(phase: str, is_correct: bool, remediation: str | None) -> str:
    if phase == "instruction":
        return "Continue to faded practice."
    if phase == "control":
        return "Self-report recorded. Delayed check unlocks after 48 hours."
    if phase == "precheck":
        return "Continue to the worked example. A precheck miss does not apply a fail tag."
    if remediation == "faded_rework":
        return "Re-read the worked example, then try a new faded attempt."
    if remediation == "independent_new_item":
        return "Study the targeted explanation, then try a new independent item. The missed item cannot count as independent mastery."
    if remediation == "transfer_new_item":
        return "Notice what changed about the unknown, then try a new transfer item."
    if remediation == "delayed_needs_review":
        return "This check is marked needs_review. A review session has been scheduled; the missed item cannot count as delayed mastery."
    if is_correct and phase == "independent":
        return "Continue to the next independent item, or to transfer if two independent successes are complete."
    if is_correct and phase == "transfer":
        return "Continue to the next transfer item, or wait for the delayed check."
    if is_correct and phase == "faded":
        return "Continue to independent practice."
    if is_correct and phase == "delayed":
        return "Continue to the next delayed item."
    return "Continue to the recommended next step."


def route_after_answer(
    db: sqlite3.Connection,
    run: sqlite3.Row,
    phase: str,
    item_row: sqlite3.Row | None,
    is_correct: bool,
) -> dict[str, Any]:
    run_id = int(run["id"])
    user_id = int(run["user_id"])
    arm = str(run["arm"])
    variant_now = int((item_row["variant_index"] if item_row is not None else run["current_variant"]) or 1)
    remediation = None
    if phase == "control":
        return {
            "next_phase": "delayed",
            "next_variant": 1,
            "remediation": None,
            "next_action": next_action_copy(phase, True, None),
        }
    if phase == "instruction":
        pending = pending_remediation(db, run_id)
        if pending and pending.get("kind") == "faded_rework":
            return {
                "next_phase": "faded",
                "next_variant": int(pending.get("next_variant") or 2),
                "remediation": "faded_rework",
                "next_action": "Return to a new faded attempt.",
            }
        return {
            "next_phase": "faded",
            "next_variant": 1,
            "remediation": None,
            "next_action": next_action_copy(phase, True, None),
        }
    if phase == "precheck":
        return {
            "next_phase": "instruction" if arm == "B" else "control",
            "next_variant": 1,
            "remediation": None,
            "next_action": next_action_copy(phase, is_correct, None),
        }
    if not is_correct:
        if phase == "faded":
            nxt = next_unused_variant(db, SKILL_CODE, "faded", run_id, "faded")
            payload = {
                "kind": "faded_rework",
                "next_variant": nxt or variant_now,
                "item_id": str(item_row["id"]) if item_row else None,
            }
            set_pending_remediation(db, run_id, user_id, payload)
            return {
                "next_phase": "faded",
                "next_variant": payload["next_variant"],
                "remediation": "faded_rework",
                "next_action": next_action_copy(phase, False, "faded_rework"),
            }
        if phase == "independent":
            nxt = next_unused_variant(db, SKILL_CODE, "independent", run_id, "independent")
            return {
                "next_phase": "independent",
                "next_variant": nxt or variant_now,
                "remediation": "independent_new_item",
                "next_action": next_action_copy(phase, False, "independent_new_item"),
            }
        if phase == "transfer":
            nxt = next_unused_variant(db, SKILL_CODE, "transfer", run_id, "transfer")
            return {
                "next_phase": "transfer",
                "next_variant": nxt or variant_now,
                "remediation": "transfer_new_item",
                "next_action": next_action_copy(phase, False, "transfer_new_item"),
            }
        if phase == "delayed":
            existing = db.execute(
                """
                SELECT 1 FROM skill_loop_events
                WHERE run_id = ? AND event_name = 'review_scheduled' LIMIT 1
                """,
                (run_id,),
            ).fetchone()
            if existing is None:
                due = iso(now_utc() + timedelta(hours=DELAY_HOURS))
                emit(
                    db,
                    "review_scheduled",
                    user_id,
                    run_id,
                    str(item_row["id"]) if item_row else None,
                    {"due_at": due, "reason": "delayed_incorrect"},
                )
            return {
                "next_phase": "delayed",
                "next_variant": variant_now,
                "remediation": "delayed_needs_review",
                "next_action": next_action_copy(phase, False, "delayed_needs_review"),
            }
    if phase == "faded":
        return {
            "next_phase": "independent",
            "next_variant": 1,
            "remediation": None,
            "next_action": next_action_copy(phase, True, None),
        }
    if phase == "independent":
        if independent_success_count(db, run_id) >= 2:
            return {
                "next_phase": "transfer",
                "next_variant": 1,
                "remediation": None,
                "next_action": "Two independent successes recorded. Continue to transfer.",
            }
        nxt = next_unused_variant(db, SKILL_CODE, "independent", run_id, "independent")
        return {
            "next_phase": "independent" if nxt else "transfer",
            "next_variant": nxt or 1,
            "remediation": None,
            "next_action": next_action_copy(phase, True, None),
        }
    if phase == "transfer":
        done = db.execute(
            "SELECT COUNT(*) AS n FROM skill_loop_step_results WHERE run_id = ? AND phase = 'transfer'",
            (run_id,),
        ).fetchone()
        n_done = int(done["n"] if done["n"] is not None else done[0])
        if n_done >= TRANSFER_ITEMS_EXPECTED:
            return {
                "next_phase": "delayed",
                "next_variant": 1,
                "remediation": None,
                "next_action": next_action_copy(phase, True, None),
            }
        nxt = next_unused_variant(db, SKILL_CODE, "transfer", run_id, "transfer")
        return {
            "next_phase": "transfer" if nxt else "delayed",
            "next_variant": nxt or 1,
            "remediation": None,
            "next_action": next_action_copy(phase, True, None),
        }
    if phase == "delayed":
        nxt = next_unused_variant(db, SKILL_CODE, "delayed", run_id, "delayed")
        return {
            "next_phase": "delayed",
            "next_variant": nxt or variant_now,
            "remediation": None,
            "next_action": next_action_copy(phase, True, None),
        }
    nxt_phase, nxt_var = next_phase(arm, phase, variant_now)
    return {
        "next_phase": nxt_phase,
        "next_variant": nxt_var,
        "remediation": remediation,
        "next_action": next_action_copy(phase, is_correct, remediation),
    }


def phase_blocked(run: sqlite3.Row, phase: str) -> bool:
    seq = allowed_phases(run["arm"])
    current = run["current_phase"]
    if phase not in seq:
        return True
    if phase == "delayed" and not delayed_unlocked(run):
        return True
    return seq.index(phase) > seq.index(current)


def slot_for_phase(phase: str) -> str:
    return {
        "precheck": "precheck",
        "instruction": "worked_example",
        "faded": "faded",
        "independent": "independent",
        "transfer": "transfer",
        "delayed": "delayed",
        "control": "precheck",
    }.get(phase, phase)


def seen_item_ids(db: sqlite3.Connection, run_id: int) -> set[str]:
    rows = db.execute(
        "SELECT DISTINCT item_id FROM skill_loop_step_results WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    shown = db.execute(
        """
        SELECT DISTINCT item_id FROM skill_loop_events
        WHERE run_id = ? AND event_name IN ('item_shown', 'precheck_shown', 'delayed_shown')
        """,
        (run_id,),
    ).fetchall()
    return {str(r[0]) for r in rows if r[0]} | {str(r[0]) for r in shown if r[0]}


def taught_item_ids(db: sqlite3.Connection, run_id: int, exclude_phase: str | None = None) -> set[str]:
    """Items already used in this student's teaching/measurement cycle."""
    if exclude_phase:
        rows = db.execute(
            """
            SELECT DISTINCT item_id FROM skill_loop_step_results
            WHERE run_id = ? AND phase != ?
            """,
            (run_id, exclude_phase),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT DISTINCT item_id FROM skill_loop_step_results
            WHERE run_id = ? AND phase != 'delayed'
            """,
            (run_id,),
        ).fetchall()
    return {str(r[0]) for r in rows if r[0]}


def counts_independent(
    db: sqlite3.Connection,
    run_id: int,
    item_id: str,
    phase: str,
    is_correct: bool,
    solution_viewed: bool,
    hint_level: str,
) -> int:
    if not is_correct:
        return 0
    if solution_viewed:
        return 0
    if hint_level == "critical":
        return 0
    prior = db.execute(
        """
        SELECT 1 FROM skill_loop_step_results
        WHERE run_id = ? AND item_id = ? AND counts_as_independent = 1
        """,
        (run_id, item_id),
    ).fetchone()
    if prior is not None:
        return 0
    if phase not in ("independent", "transfer", "delayed"):
        return 0
    return 1


def refresh_mastery(db: sqlite3.Connection, run: sqlite3.Row) -> str:
    run_id = int(run["id"])
    ind_pass = independent_success_count(db, run_id) >= 2
    status = "learning"
    if ind_pass:
        status = "immediate_pass"
        db.execute(
            "UPDATE skill_loop_runs SET immediate_completed_at = COALESCE(immediate_completed_at, ?) WHERE id = ?",
            (iso(now_utc()), run_id),
        )
    delayed_rows = db.execute(
        """
        SELECT item_id, counts_as_independent, is_correct, solution_viewed, hint_level
        FROM skill_loop_step_results WHERE run_id = ? AND phase = 'delayed'
        """,
        (run_id,),
    ).fetchall()
    window = delayed_window_state(run)
    if delayed_rows:
        any_wrong = any(int(r["is_correct"] or 0) != 1 for r in delayed_rows)
        if any_wrong:
            status = "needs_review"
            existing = db.execute(
                """
                SELECT 1 FROM skill_loop_events
                WHERE run_id = ? AND event_name = 'review_scheduled' LIMIT 1
                """,
                (run_id,),
            ).fetchone()
            if existing is None:
                emit(
                    db,
                    "review_scheduled",
                    int(run["user_id"]),
                    run_id,
                    str(delayed_rows[-1]["item_id"]),
                    {
                        "due_at": iso(now_utc() + timedelta(hours=DELAY_HOURS)),
                        "reason": "delayed_incorrect",
                    },
                )
        elif len(delayed_rows) >= 2 and window in ("due", "overdue"):
            ok = all(int(r["counts_as_independent"] or 0) == 1 for r in delayed_rows)
            if ok:
                status = "delayed_pass"
                elapsed = delayed_elapsed_hours(run)
                timing = "overdue" if window == "overdue" else "on_time"
                db.execute(
                    """
                    UPDATE skill_loop_runs
                    SET delayed_completed_at = COALESCE(delayed_completed_at, ?),
                        delayed_elapsed_hours = COALESCE(delayed_elapsed_hours, ?),
                        delayed_timing = COALESCE(delayed_timing, ?)
                    WHERE id = ?
                    """,
                    (iso(now_utc()), elapsed, timing, run_id),
                )
            elif any(int(r["solution_viewed"] or 0) or str(r["hint_level"]) == "critical" for r in delayed_rows):
                status = "needs_review"
    db.execute("UPDATE skill_loop_runs SET mastery_status = ? WHERE id = ?", (status, run_id))
    return status


def record_solution_or_hint(
    db: sqlite3.Connection,
    run_id: int,
    user_id: int,
    item_id: str,
    kind: str,
    level: str | None = None,
) -> None:
    if kind == "solution":
        db.execute(
            """
            UPDATE skill_loop_step_results
            SET solution_viewed = 1, counts_as_independent = 0
            WHERE run_id = ? AND item_id = ?
            """,
            (run_id, item_id),
        )
        emit(db, "solution_opened", user_id, run_id, item_id, {})
    else:
        db.execute(
            """
            UPDATE skill_loop_step_results
            SET hint_used = 1,
                hint_level = ?,
                counts_as_independent = CASE WHEN ? = 'critical' THEN 0 ELSE counts_as_independent END
            WHERE run_id = ? AND item_id = ?
            """,
            (level or "light", level or "light", run_id, item_id),
        )
        emit(db, "hint_opened", user_id, run_id, item_id, {"level": level or "light"})
    run = db.execute("SELECT * FROM skill_loop_runs WHERE id = ?", (run_id,)).fetchone()
    if run:
        refresh_mastery(db, run)


def mark_instruction_complete(db: sqlite3.Connection, run_id: int) -> None:
    now = now_utc()
    db.execute(
        """
        UPDATE skill_loop_runs
        SET instruction_completed_at = COALESCE(instruction_completed_at, ?),
            delayed_available_at = COALESCE(delayed_available_at, ?),
            delayed_deadline_at = COALESCE(delayed_deadline_at, ?)
        WHERE id = ?
        """,
        (
            iso(now),
            iso(now + timedelta(hours=DELAY_HOURS)),
            iso(now + timedelta(hours=DELAY_MAX_HOURS)),
            run_id,
        ),
    )


def submit_answer(
    db: sqlite3.Connection,
    run: sqlite3.Row,
    phase: str,
    item_row: sqlite3.Row | None,
    selected: str,
    faded_fields: dict | None,
    hint_level: str,
    solution_viewed: bool,
    elapsed_ms: int | None,
) -> dict[str, Any]:
    run_id = int(run["id"])
    if phase == "control":
        mark_instruction_complete(db, run_id)
        nxt_phase, nxt_var = "delayed", 1
        db.execute(
            "UPDATE skill_loop_runs SET current_phase = ?, current_variant = ? WHERE id = ?",
            (nxt_phase, nxt_var, run_id),
        )
        emit(db, "control_completed", int(run["user_id"]), run_id, None, {"self_report": True})
        emit(
            db,
            "answer_feedback",
            int(run["user_id"]),
            run_id,
            None,
            {
                "phase": "control",
                "correct": True,
                "selected": "self-report",
                "remediation": None,
                "next_action": next_action_copy("control", True, None),
                "next_phase": nxt_phase,
                "next_variant": nxt_var,
                "self_report": True,
            },
        )
        return {
            "ok": True,
            "correct": True,
            "duplicate": False,
            "mastery_status": str(run["mastery_status"]),
            "next_phase": nxt_phase,
            "next_variant": nxt_var,
            "remediation": None,
            "next_action": next_action_copy("control", True, None),
            "phase": "control",
            "item_id": None,
            "self_report": True,
        }

    if item_row is None:
        abort(403)
    item_id = str(item_row["id"])
    existing = db.execute(
        "SELECT * FROM skill_loop_step_results WHERE run_id = ? AND item_id = ? AND phase = ?",
        (run_id, item_id, phase),
    ).fetchone()
    if existing is not None:
        return {
            "ok": True,
            "duplicate": True,
            "correct": bool(existing["is_correct"]),
            "mastery_status": str(run["mastery_status"]),
            "next_phase": str(run["current_phase"]),
            "next_variant": int(run["current_variant"] or 1),
            "item_id": item_id,
            "phase": phase,
        }

    if phase == "instruction":
        is_correct = True
        flag = 0
        seen_repeat = 0
        elapsed_hours = None
        completion_timing = None
    else:
        is_correct = grade_row(item_row, selected, faded_fields)
        taught = taught_item_ids(db, run_id, exclude_phase=phase)
        seen_repeat = 1 if item_id in taught else 0
        flag = counts_independent(
            db, run_id, item_id, phase, is_correct, solution_viewed, hint_level
        )
        if seen_repeat:
            flag = 0
        elapsed_hours = None
        completion_timing = None
        if phase == "delayed":
            elapsed_hours = delayed_elapsed_hours(run)
            window = delayed_window_state(run)
            completion_timing = "overdue" if window == "overdue" else "on_time" if window == "due" else window
    db.execute(
        """
        INSERT INTO skill_loop_step_results (
            run_id, item_id, item_version, phase, selected_answer, is_correct,
            hint_used, hint_level, solution_viewed, elapsed_ms, started_at, submitted_at,
            counts_as_independent, is_repeat_of_seen_item, elapsed_hours, completion_timing
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            item_id,
            int(item_row["version"]),
            phase,
            selected,
            1 if is_correct else 0,
            1 if hint_level != "none" else 0,
            hint_level,
            1 if solution_viewed else 0,
            elapsed_ms,
            iso(now_utc()),
            iso(now_utc()),
            flag,
            seen_repeat,
            elapsed_hours,
            completion_timing,
        ),
    )
    emit(
        db,
        f"{phase}_answered",
        int(run["user_id"]),
        run_id,
        item_id,
        {"correct": is_correct, "independent": flag},
    )

    variant_now = int(item_row["variant_index"] or run["current_variant"] or 1)
    routed = route_after_answer(db, run, phase, item_row, is_correct)
    nxt_phase = routed["next_phase"]
    nxt_var = routed["next_variant"]
    extra_sql = []
    extra_args: list[Any] = []
    if phase in ("instruction", "control"):
        mark_instruction_complete(db, run_id)
    extra_sql.extend(["current_phase = ?", "current_variant = ?"])
    extra_args.extend([nxt_phase, nxt_var, run_id])
    db.execute(
        f"UPDATE skill_loop_runs SET {', '.join(extra_sql)} WHERE id = ?",
        extra_args,
    )
    run2 = db.execute("SELECT * FROM skill_loop_runs WHERE id = ?", (run_id,)).fetchone()
    status = refresh_mastery(db, run2)
    emit(
        db,
        "answer_feedback",
        int(run["user_id"]),
        run_id,
        item_id,
        {
            "phase": phase,
            "correct": is_correct,
            "selected": selected,
            "remediation": routed.get("remediation"),
            "next_action": routed.get("next_action"),
            "next_phase": nxt_phase,
            "next_variant": nxt_var,
        },
    )
    return {
        "ok": True,
        "correct": is_correct,
        "duplicate": False,
        "mastery_status": status,
        "next_phase": nxt_phase,
        "next_variant": nxt_var,
        "remediation": routed.get("remediation"),
        "next_action": routed.get("next_action"),
        "item_id": item_id,
        "phase": phase,
        "advanced_stage": nxt_phase != phase and is_correct,
    }


def publish_item(db: sqlite3.Connection, item_id: str, version: int, reviewer_id: int) -> None:
    db.execute(
        """
        UPDATE skill_loop_items
        SET review_status = 'reviewed', publish_status = 'published',
            reviewed_by = ?, reviewed_at = ?
        WHERE id = ? AND version = ?
        """,
        (reviewer_id, iso(now_utc()), item_id, version),
    )
    db.execute(
        """
        INSERT INTO skill_loop_item_reviews (item_id, item_version, reviewer_user_id, decision, created_at)
        VALUES (?, ?, ?, 'published', ?)
        """,
        (item_id, version, reviewer_id, iso(now_utc())),
    )


def publish_all_drafts(db: sqlite3.Connection, reviewer_id: int) -> int:
    rows = db.execute(
        "SELECT id, version FROM skill_loop_items WHERE review_status = 'draft'"
    ).fetchall()
    for row in rows:
        publish_item(db, str(row["id"]), int(row["version"]), reviewer_id)
    return len(rows)


def revise_published_item(db: sqlite3.Connection, item_id: str, stem_html: str) -> int:
    row = db.execute(
        "SELECT * FROM skill_loop_items WHERE id = ? ORDER BY version DESC LIMIT 1",
        (item_id,),
    ).fetchone()
    if row is None:
        raise ValueError("missing")
    new_v = int(row["version"]) + 1
    cols = [c[1] for c in db.execute("PRAGMA table_info(skill_loop_items)")]
    data = {c: row[c] for c in cols}
    data["version"] = new_v
    data["stem_html"] = stem_html
    data["review_status"] = "draft"
    data["publish_status"] = "unpublished"
    data["reviewed_by"] = None
    data["reviewed_at"] = None
    keys = [k for k in data.keys() if k != "created_at"]
    db.execute(
        f"INSERT INTO skill_loop_items ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})",
        [data[k] for k in keys],
    )
    return new_v


def label_for_status(status: str) -> str:
    return {
        "not_started": "Not started",
        "learning": "Learning",
        "immediate_pass": "Immediate pass (not mastery)",
        "delayed_pass": "已掌握 (delayed independent pass)",
        "needs_review": "Needs review",
    }.get(status, status)


def _eligible_assignments(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute(
        """
        SELECT a.user_id, a.arm, a.skill_code, u.username, u.role
        FROM skill_loop_assignments a
        JOIN users u ON u.id = a.user_id
        WHERE a.experiment_id = ?
        """,
        (EXPERIMENT_ID,),
    ).fetchall()


def compute_analysis_report(db: sqlite3.Connection) -> dict[str, Any]:
    assigned_all = []
    excluded = []
    for row in _eligible_assignments(db):
        rec = dict(row)
        if is_excluded_from_analysis(row["role"], row["username"]):
            excluded.append(rec)
        else:
            assigned_all.append(rec)

    runs = {
        int(r["user_id"]): r
        for r in db.execute(
            "SELECT * FROM skill_loop_runs WHERE experiment_id = ?",
            (EXPERIMENT_ID,),
        ).fetchall()
    }

    def steps(uid: int, phase: str) -> list[sqlite3.Row]:
        run = runs.get(uid)
        if run is None:
            return []
        return db.execute(
            """
            SELECT * FROM skill_loop_step_results
            WHERE run_id = ? AND phase = ?
            ORDER BY id
            """,
            (int(run["id"]), phase),
        ).fetchall()

    def transfer_independent_correct(rows: list[sqlite3.Row]) -> int:
        n = 0
        for row in rows:
            if str(row["phase"]) != "transfer":
                continue
            if int(row["is_repeat_of_seen_item"] or 0) == 1:
                continue
            if int(row["counts_as_independent"] or 0) != 1:
                continue
            n += 1
        return n

    transfer_assigned = [r for r in assigned_all if r["arm"] == "B"]
    transfer_started = []
    transfer_completed = []
    transfer_correct_started = 0
    transfer_correct_completed = 0
    for rec in transfer_assigned:
        uid = int(rec["user_id"])
        rows = steps(uid, "transfer")
        run = runs.get(uid)
        started = bool(rows) or (
            run is not None and str(run["current_phase"]) in ("transfer", "delayed")
        )
        if started:
            transfer_started.append(rec)
            transfer_correct_started += transfer_independent_correct(rows)
        if len(rows) >= TRANSFER_ITEMS_EXPECTED:
            transfer_completed.append(rec)
            transfer_correct_completed += transfer_independent_correct(rows)

    started_slots = len(transfer_started) * TRANSFER_ITEMS_EXPECTED
    completed_slots = len(transfer_completed) * TRANSFER_ITEMS_EXPECTED

    delayed_assigned = assigned_all
    delayed_on_time = 0
    delayed_overdue = 0
    delayed_pass_on_time = 0
    delayed_pass_overdue = 0
    for rec in delayed_assigned:
        run = runs.get(int(rec["user_id"]))
        if run is None:
            continue
        timing = str(run["delayed_timing"] or "")
        if timing == "on_time":
            delayed_on_time += 1
            if run["mastery_status"] == "delayed_pass":
                delayed_pass_on_time += 1
        elif timing == "overdue":
            delayed_overdue += 1
            if run["mastery_status"] == "delayed_pass":
                delayed_pass_overdue += 1

    sample_n = len(assigned_all)
    completed_runs = sum(1 for r in assigned_all if runs.get(int(r["user_id"])) and runs[int(r["user_id"])]["delayed_completed_at"])
    missing_n = sample_n - len(transfer_started)
    return {
        "sample_n": sample_n,
        "excluded_n": len(excluded),
        "assigned": assigned_all,
        "excluded": excluded,
        "completion_rate": (completed_runs / sample_n) if sample_n else 0.0,
        "missing_n": missing_n,
        "immediate_n": sum(
            1
            for r in assigned_all
            if runs.get(int(r["user_id"])) and runs[int(r["user_id"])]["mastery_status"] == "immediate_pass"
        ),
        "delayed_n": sum(
            1
            for r in assigned_all
            if runs.get(int(r["user_id"])) and runs[int(r["user_id"])]["mastery_status"] == "delayed_pass"
        ),
        "transfer_assigned_denominator": len(transfer_assigned),
        "transfer_started_denominator": len(transfer_started),
        "transfer_completed_denominator": len(transfer_completed),
        "transfer_independent_correct_started": transfer_correct_started,
        "transfer_independent_correct_completed": transfer_correct_completed,
        "transfer_accuracy_started": (
            transfer_correct_started / started_slots if started_slots else None
        ),
        "transfer_accuracy_completed": (
            transfer_correct_completed / completed_slots if completed_slots else None
        ),
        "incomplete_rule": (
            "Assigned students who have not started transfer stay in assigned denominator only. "
            "Students who started but have not finished remain in the started denominator; "
            "missing transfer items count as not independent-correct. "
            "Completed denominator includes only students with two transfer submissions."
        ),
        "delayed_on_time_n": delayed_on_time,
        "delayed_overdue_n": delayed_overdue,
        "delayed_pass_on_time": delayed_pass_on_time,
        "delayed_pass_overdue": delayed_pass_overdue,
        "allow_conclusion_labels": sample_n >= 30,
        "disclaimer_en": (
            "Pilot only — usability and data-integrity evaluation. "
            "Not evidence of instructional effectiveness."
        ),
        "disclaimer_zh": "仅用于可用性和数据完整性试点，不构成教学有效性或提分证明。",
        "arm_a_exposure_self_report_only": True,
        "arm_a_exposure_note_en": (
            'Arm A “I finished the existing lesson” is student self-report only. '
            "Control-lesson exposure cannot be fully verified, so no instructional-effectiveness "
            "conclusion is permitted from Arm A."
        ),
        "arm_a_exposure_note_zh": (
            "A组“我已完成现有课程”仅为学生自报，无法完全验证真实学习暴露，不能据此做教学效果结论。"
        ),
    }


def format_report_text(metrics: dict[str, Any]) -> str:
    lines = [
        metrics["disclaimer_en"],
        metrics["disclaimer_zh"],
        "",
        f"sample_n={metrics['sample_n']}",
        f"completion_rate={metrics['completion_rate']:.3f}",
        f"missing_n={metrics['missing_n']}",
        f"excluded_n={metrics['excluded_n']}",
        "",
        "Immediate performance (not mastery)",
        f"immediate_pass={metrics['immediate_n']}",
        "",
        "Transfer (stage=transfer only; first unseen item; counts_as_independent=1)",
        metrics["incomplete_rule"],
        f"assigned_denominator={metrics['transfer_assigned_denominator']}",
        f"started_denominator={metrics['transfer_started_denominator']}",
        f"completed_denominator={metrics['transfer_completed_denominator']}",
        f"transfer_accuracy_started={metrics['transfer_accuracy_started']}",
        f"transfer_accuracy_completed={metrics['transfer_accuracy_completed']}",
        "",
        "Delayed retention",
        f"delayed_pass_on_time={metrics['delayed_pass_on_time']}",
        f"delayed_pass_overdue={metrics['delayed_pass_overdue']}",
        f"delayed_on_time_n={metrics['delayed_on_time_n']}",
        f"delayed_overdue_n={metrics['delayed_overdue_n']}",
        "",
        "Arm A exposure",
        metrics["arm_a_exposure_note_en"],
        metrics["arm_a_exposure_note_zh"],
    ]
    return "\n".join(lines) + "\n"


def _session_user_id() -> int:
    uid = session.get("user_id")
    if not uid:
        abort(401)
    return int(uid)


def _current_user_row(db: sqlite3.Connection) -> sqlite3.Row | None:
    uid = session.get("user_id")
    if not uid:
        return None
    return db.execute("SELECT * FROM users WHERE id = ?", (int(uid),)).fetchone()


def _request_payload() -> dict[str, Any]:
    if request.is_json:
        data = request.get_json(silent=True) or {}
        return dict(data)
    faded = {
        "rate": request.form.get("rate") or "",
        "total_hours": request.form.get("total_hours") or "",
    }
    return {
        "phase": request.form.get("phase") or "",
        "item_id": request.form.get("item_id") or "",
        "selected_answer": request.form.get("selected_answer") or "",
        "faded": faded,
        "hint_level": request.form.get("hint_level") or "none",
        "solution_viewed": request.form.get("solution_viewed") == "1",
        "variant": request.form.get("variant") or 1,
    }


@skill_loop_bp.before_request
def _gate():
    if not skill_loop_enabled():
        abort(404)
    return None


@skill_loop_bp.route("/")
def hub():
    db = _db()
    user = _current_user_row(db)
    if user is None:
        abort(401)
    asg = ensure_assignment(db, int(user["id"]), SKILL_CODE, str(user["role"]), str(user["username"]))
    run = get_run(db, int(user["id"]), SKILL_CODE)
    db.commit()
    return render_template(
        "skill_loop_hub.html",
        assignment=asg,
        run=run,
        skill_code=SKILL_CODE,
        status_label=label_for_status((run["mastery_status"] if run else "not_started")),
        delayed_open=bool(run and delayed_unlocked(run)),
        show_mastered=bool(run and run["mastery_status"] == "delayed_pass"),
    )


@skill_loop_bp.route("/<skill_code>")
def skill_home(skill_code: str):
    if skill_code != SKILL_CODE:
        abort(404)
    return redirect(url_for("skill_loop.hub"))


@skill_loop_bp.route("/<skill_code>/feedback")
def feedback(skill_code: str):
    if skill_code != SKILL_CODE:
        abort(404)
    db = _db()
    user = _current_user_row(db)
    if user is None:
        abort(401)
    asg = get_assignment(db, int(user["id"]), SKILL_CODE)
    run = get_run(db, int(user["id"]), SKILL_CODE)
    if asg is None or run is None:
        abort(403)
    ev = db.execute(
        """
        SELECT event_name, item_id, payload_json FROM skill_loop_events
        WHERE run_id = ? AND event_name = 'answer_feedback'
        ORDER BY id DESC LIMIT 1
        """,
        (int(run["id"]),),
    ).fetchone()
    if ev is None:
        return redirect(url_for("skill_loop.hub"))
    payload = json.loads(ev["payload_json"] or "{}")
    item_id = ev["item_id"]
    item_row = published_item(db, item_id) if item_id else None
    teach = teaching_fields(item_row) if item_row is not None else {}
    phase = str(payload.get("phase") or "")
    is_correct = bool(payload.get("correct", True if phase in ("instruction", "control") else False))
    remediation = payload.get("remediation")
    selected = str(payload.get("selected") or "")
    if phase == "control":
        continue_href = url_for("skill_loop.hub")
        next_action = next_action_copy("control", True, None)
        correct_display = None
        selected_display = "I finished the existing lesson (self-report)"
        core_idea = "Arm A exposure is student self-report only and cannot be fully verified."
        steps: list[Any] = []
        check = ""
        mistake = "Treating this self-report as proof that the control lesson was completed."
        unknown_change = ""
        result_label = "Self-report recorded"
    else:
        if remediation == "faded_rework":
            continue_href = url_for("skill_loop.phase_view", skill_code=SKILL_CODE, phase="instruction")
        elif remediation == "delayed_needs_review":
            continue_href = url_for("skill_loop.hub")
        else:
            nxt_phase = str(payload.get("next_phase") or run["current_phase"])
            nxt_var = int(payload.get("next_variant") or run["current_variant"] or 1)
            continue_href = url_for(
                "skill_loop.phase_view", skill_code=SKILL_CODE, phase=nxt_phase, v=nxt_var
            )
        next_action = str(payload.get("next_action") or next_action_copy(phase, is_correct, remediation))
        correct_display = display_correct_answer(item_row) if item_row is not None else ""
        selected_display = selected or "(blank)"
        if item_row is not None and selected in "ABCD" and teach.get("choices"):
            idx = ord(selected) - 65
            choices = teach["choices"]
            if 0 <= idx < len(choices):
                selected_display = f"{selected}. {choices[idx]}"
        core_idea = teach.get("core_idea") or ""
        steps = teach.get("worked_steps") or []
        check = teach.get("explanation_check") or ""
        mistake = teach.get("common_mistake") or ""
        unknown_change = teach.get("unknown_change") or ""
        if phase == "instruction":
            result_label = "Worked example complete"
        else:
            result_label = "Correct" if is_correct else "Incorrect"
    return render_template(
        "skill_loop_feedback.html",
        phase=phase,
        result_label=result_label,
        is_correct=is_correct,
        selected_display=selected_display,
        correct_display=correct_display,
        core_idea=core_idea,
        worked_steps=steps,
        explanation_check=check,
        common_mistake=mistake,
        unknown_change=unknown_change,
        next_action=next_action,
        continue_href=continue_href,
        remediation=remediation,
        self_report=phase == "control",
        skill_code=SKILL_CODE,
        mastery_status=run["mastery_status"],
        mastery_label=label_for_status(run["mastery_status"]),
    )


@skill_loop_bp.route("/<skill_code>/<phase>")
def phase_view(skill_code: str, phase: str):
    if skill_code != SKILL_CODE:
        abort(404)
    if phase not in set(PHASES_A) | set(PHASES_B):
        abort(404)
    db = _db()
    user = _current_user_row(db)
    if user is None:
        abort(401)
    requested_uid = request.args.get("user_id")
    if requested_uid and int(requested_uid) != int(user["id"]):
        abort(403)
    asg = ensure_assignment(db, int(user["id"]), SKILL_CODE, str(user["role"]), str(user["username"]))
    run = ensure_run(db, int(user["id"]), SKILL_CODE, asg["arm"])
    if asg["arm"] == "A" and phase not in PHASES_A:
        db.commit()
        abort(403)
    if phase_blocked(run, phase):
        db.commit()
        abort(403)
    if phase == "control":
        if asg["arm"] != "A":
            abort(403)
        emit(db, "control_opened", int(user["id"]), int(run["id"]), None, {})
        db.commit()
        return render_template(
            "skill_loop_control.html",
            lesson_href="/practice/materials/1-1-linear-equations",
            practice_href="/practice/algebra/1_1/0",
            skill_code=SKILL_CODE,
        )
    variant = int(request.args.get("v") or run["current_variant"] or 1)
    slot = slot_for_phase(phase)
    pending = pending_remediation(db, int(run["id"]))
    if phase == "instruction" and pending and pending.get("kind") == "faded_rework":
        variant = 1
    elif phase in ("faded", "independent", "transfer", "delayed"):
        unused = next_unused_variant(db, SKILL_CODE, slot, int(run["id"]), phase)
        if unused is not None:
            variant = unused
    row = item_for_slot(db, SKILL_CODE, slot, variant)
    if row is None:
        abort(404)
    emit(db, "item_shown", int(user["id"]), int(run["id"]), row["id"], {"phase": phase})
    db.commit()
    payload = public_payload(row, phase)
    prior_instruction = db.execute(
        """
        SELECT 1 FROM skill_loop_step_results
        WHERE run_id = ? AND phase = 'instruction' LIMIT 1
        """,
        (int(run["id"]),),
    ).fetchone()
    review_example = bool(phase == "instruction" and prior_instruction)
    continue_href = None
    if review_example:
        nxt_v = int((pending or {}).get("next_variant") or run["current_variant"] or 2)
        continue_href = url_for("skill_loop.phase_view", skill_code=SKILL_CODE, phase="faded", v=nxt_v)
    return render_template(
        "skill_loop_phase.html",
        phase=phase,
        item=payload,
        skill_code=SKILL_CODE,
        arm=asg["arm"],
        mastery_status=run["mastery_status"],
        mastery_label=label_for_status(run["mastery_status"]),
        show_mastered=run["mastery_status"] == "delayed_pass",
        review_example=review_example,
        continue_href=continue_href,
        pending_remediation=pending,
    )


@skill_loop_bp.route("/<skill_code>/submit", methods=["POST"])
def submit(skill_code: str):
    if skill_code != SKILL_CODE:
        abort(404)
    db = _db()
    user = _current_user_row(db)
    if user is None:
        abort(401)
    data = _request_payload()
    phase = str(data.get("phase") or "")
    item_id = str(data.get("item_id") or "")
    selected = str(data.get("selected_answer") or "")
    faded_fields = data.get("faded") if isinstance(data.get("faded"), dict) else {}
    hint_level = str(data.get("hint_level") or "none")
    solution_viewed = bool(data.get("solution_viewed"))
    asg = get_assignment(db, int(user["id"]), SKILL_CODE)
    run = get_run(db, int(user["id"]), SKILL_CODE)
    if asg is None or run is None:
        abort(403)
    if phase_blocked(run, phase) and phase != "control":
        abort(403)
    if asg["arm"] == "A" and phase not in PHASES_A:
        abort(403)
    if data.get("current_phase") or data.get("mastery_status"):
        abort(403)
    row = None
    if phase != "control":
        row = published_item(db, item_id)
        if row is None:
            abort(403)
        expected_slot = slot_for_phase(phase)
        if str(row["slot"]) != expected_slot:
            abort(403)
    result = submit_answer(
        db, run, phase, row, selected, faded_fields, hint_level, solution_viewed, None
    )
    db.commit()
    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        out = dict(result)
        out.pop("correct_answer", None)
        out.pop("answer", None)
        out.pop("key", None)
        out["feedback_path"] = url_for("skill_loop.feedback", skill_code=SKILL_CODE)
        return jsonify(out)
    return redirect(url_for("skill_loop.feedback", skill_code=SKILL_CODE))


@skill_loop_bp.route("/<skill_code>/complete-control", methods=["POST"])
def complete_control(skill_code: str):
    if skill_code != SKILL_CODE:
        abort(404)
    db = _db()
    user = _current_user_row(db)
    if user is None:
        abort(401)
    asg = get_assignment(db, int(user["id"]), SKILL_CODE)
    run = get_run(db, int(user["id"]), SKILL_CODE)
    if asg is None or run is None or asg["arm"] != "A":
        abort(403)
    result = submit_answer(db, run, "control", None, "", None, "none", False, None)
    db.commit()
    if request.is_json:
        return jsonify(result)
    return redirect(url_for("skill_loop.feedback", skill_code=SKILL_CODE))


@skill_loop_bp.route("/<skill_code>/event", methods=["POST"])
def track_event(skill_code: str):
    if skill_code != SKILL_CODE:
        abort(404)
    db = _db()
    user = _current_user_row(db)
    if user is None:
        abort(401)
    data = request.get_json(silent=True) or {}
    run = get_run(db, int(user["id"]), SKILL_CODE)
    if run is None:
        abort(403)
    kind = str(data.get("kind") or "")
    item_id = str(data.get("item_id") or "")
    if kind not in ("solution", "hint"):
        abort(400)
    level = str(data.get("level") or "light")
    row = published_item(db, item_id)
    if row is None:
        abort(403)
    record_solution_or_hint(db, int(run["id"]), int(user["id"]), item_id, kind, level)
    db.commit()
    teach = teaching_fields(row)
    out: dict[str, Any] = {"ok": True, "counts_as_independent": 0 if kind == "solution" or level == "critical" else None}
    if kind == "hint" and level == "critical":
        out["hint_level"] = "critical"
        out["hint_text"] = teach["critical_hint"]
    elif kind == "hint":
        out["hint_level"] = "light"
        out["hint_text"] = teach["light_hint"]
    else:
        out["solution"] = {
            "answer_display": display_correct_answer(row),
            "worked_steps": teach["worked_steps"],
            "explanation_check": teach["explanation_check"],
            "core_idea": teach["core_idea"],
        }
    return jsonify(out)


@skill_loop_bp.route("/api/run/<int:run_id>")
def api_run(run_id: int):
    db = _db()
    uid = _session_user_id()
    run = db.execute("SELECT * FROM skill_loop_runs WHERE id = ?", (run_id,)).fetchone()
    if run is None or int(run["user_id"]) != uid:
        abort(403)
    steps = db.execute(
        """
        SELECT item_id, item_version, phase, is_correct, counts_as_independent
        FROM skill_loop_step_results WHERE run_id = ?
        """,
        (run_id,),
    ).fetchall()
    return jsonify(
        {
            "id": int(run["id"]),
            "user_id": int(run["user_id"]),
            "arm": run["arm"],
            "current_phase": run["current_phase"],
            "mastery_status": run["mastery_status"],
            "steps": [dict(s) for s in steps],
        }
    )


@skill_loop_bp.route("/admin/review")
def admin_review():
    from app import current_user_can_access_admin

    if not current_user_can_access_admin():
        abort(403)
    db = _db()
    items = db.execute(
        """
        SELECT id, version, slot, review_status, publish_status, reviewed_by, reviewed_at
        FROM skill_loop_items ORDER BY slot, id, version
        """
    ).fetchall()
    return render_template("skill_loop_admin_review.html", items=items, skill_code=SKILL_CODE)


@skill_loop_bp.route("/admin/publish", methods=["POST"])
def admin_publish():
    from app import current_user_can_access_admin

    if not current_user_can_access_admin():
        abort(403)
    data = request.get_json(silent=True) or request.form
    item_id = str(data.get("item_id") or "")
    version = int(data.get("version") or 1)
    db = _db()
    publish_item(db, item_id, version, int(session["user_id"]))
    db.commit()
    if request.is_json:
        return jsonify({"ok": True, "question_bank_touched": False})
    return redirect(url_for("skill_loop.admin_review"))


@skill_loop_bp.route("/admin/assign", methods=["POST"])
def admin_assign():
    from app import current_user_can_access_admin

    if not current_user_can_access_admin():
        abort(403)
    data = request.get_json(silent=True) or request.form
    db = _db()
    admin_override_arm(
        db,
        int(data.get("user_id")),
        SKILL_CODE,
        str(data.get("arm") or "A"),
        int(session["user_id"]),
        str(data.get("reason") or ""),
    )
    db.commit()
    return jsonify({"ok": True})


@skill_loop_bp.route("/admin/report")
def admin_report():
    from app import current_user_can_access_admin

    if not current_user_can_access_admin():
        abort(403)
    db = _db()
    metrics = compute_analysis_report(db)
    return render_template(
        "skill_loop_admin_report.html",
        metrics=metrics,
        skill_code=SKILL_CODE,
        export_href=url_for("skill_loop.admin_report_export"),
    )


@skill_loop_bp.route("/admin/report.txt")
def admin_report_export():
    from app import current_user_can_access_admin

    if not current_user_can_access_admin():
        abort(403)
    db = _db()
    metrics = compute_analysis_report(db)
    body = format_report_text(metrics)
    return current_app.response_class(body, mimetype="text/plain; charset=utf-8")
