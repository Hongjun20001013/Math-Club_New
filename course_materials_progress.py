"""Course materials progress storage and AI coach helpers."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\\[a-zA-Z]+\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def merge_answers(existing: Any, incoming: Any) -> dict[str, Any]:
    """Merge per-slide answers; first locked answer always wins."""
    out: dict[str, Any] = {}
    for src in (existing, incoming):
        if not isinstance(src, dict):
            continue
        for key, value in src.items():
            if not isinstance(value, dict):
                continue
            slot = str(key)
            prev = out.get(slot)
            if prev and prev.get("locked"):
                continue
            if value.get("locked") or not prev:
                row = dict(value)
                row["locked"] = bool(value.get("locked"))
                out[slot] = row
                continue
            try:
                newer = int(value.get("at") or 0) >= int(prev.get("at") or 0)
            except (TypeError, ValueError):
                newer = True
            if newer:
                out[slot] = dict(value)
    return out


def merge_progress(local: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
    """Merge localStorage and server progress (union + best checkpoint)."""
    out: dict[str, Any] = {
        "viewed": [],
        "done": [],
        "reflections": {},
        "answers": {},
    }
    for key in ("viewed", "done"):
        merged: set[int] = set()
        for src in (local, remote):
            for n in src.get(key) or []:
                try:
                    merged.add(int(n))
                except (TypeError, ValueError):
                    continue
        out[key] = sorted(merged)
    refs_local = local.get("reflections") or {}
    refs_remote = remote.get("reflections") or {}
    if isinstance(refs_local, dict) and isinstance(refs_remote, dict):
        out["reflections"] = {**refs_remote, **refs_local}
    else:
        out["reflections"] = refs_local if isinstance(refs_local, dict) else {}
    out["answers"] = merge_answers(remote.get("answers"), local.get("answers"))

    cp_local = local.get("checkpoint") or {}
    cp_remote = remote.get("checkpoint") or {}
    if not isinstance(cp_local, dict):
        cp_local = {}
    if not isinstance(cp_remote, dict):
        cp_remote = {}
    best_score = max(int(cp_local.get("best_score") or 0), int(cp_remote.get("best_score") or 0))
    best_total = max(int(cp_local.get("best_total") or 0), int(cp_remote.get("best_total") or 0))
    last_run = cp_local.get("last_run") or cp_remote.get("last_run")
    if cp_remote.get("last_run") and cp_local.get("last_run"):
        try:
            if int(cp_remote["last_run"].get("at") or 0) > int(cp_local["last_run"].get("at") or 0):
                last_run = cp_remote["last_run"]
        except (TypeError, ValueError, AttributeError):
            pass
    missed = cp_local.get("missed") or cp_remote.get("missed") or []
    out["checkpoint"] = {
        "best_score": best_score,
        "best_total": best_total,
        "last_run": last_run,
        "missed": missed if isinstance(missed, list) else [],
    }
    study = local.get("study_mode")
    if study is None:
        study = remote.get("study_mode")
    if study is not None:
        out["study_mode"] = study

    local_at = int(local.get("last_active_at") or 0)
    remote_at = int(remote.get("last_active_at") or 0)
    if remote_at > local_at:
        out["last_active_at"] = remote_at
        out["last_slide_index"] = int(remote.get("last_slide_index") or 1)
    elif local_at > 0:
        out["last_active_at"] = local_at
        out["last_slide_index"] = int(local.get("last_slide_index") or 1)
    else:
        out["last_active_at"] = 0
        out["last_slide_index"] = int(local.get("last_slide_index") or remote.get("last_slide_index") or 1)
    return out


def mastery_pct_from_progress(progress: dict[str, Any], slide_count: int, checkpoint_count: int) -> int:
    if slide_count <= 0:
        return 0
    viewed = len(progress.get("viewed") or [])
    done = len(progress.get("done") or [])
    slide_pct = min(100, round(100 * (viewed * 0.35 + done * 0.45) / slide_count))
    cp = progress.get("checkpoint") or {}
    cp_pct = 0
    if cp.get("last_run") and isinstance(cp["last_run"], dict):
        cp_pct = int(cp["last_run"].get("pct") or 0)
    elif cp.get("best_total"):
        cp_pct = round(100 * int(cp.get("best_score") or 0) / int(cp["best_total"]))
    if checkpoint_count:
        return min(100, round(slide_pct * 0.65 + cp_pct * 0.35))
    return slide_pct


def build_coach_system_prompt() -> str:
    return (
        "You are a SAT Math study coach for Novel Prep. "
        "The student is viewing an interactive lesson slide. "
        "Use clear, encouraging language. Keep answers concise (under 180 words). "
        "Use plain text; write math with LaTeX in \\(...\\) when needed. "
        "For practice or multiple-choice slides, use Socratic hints — do NOT reveal "
        "the final letter answer unless the student already submitted a wrong attempt "
        "and explicitly asks why their choice was wrong. "
        "Focus only on the slide context provided; do not invent unrelated topics."
    )


def build_coach_user_message(
    *,
    lesson_section: str,
    lesson_title: str,
    slide_title: str,
    slide_section: str,
    slide_kind: str,
    study_tip: str,
    strategy_hint: str,
    slide_plain: str,
    student_question: str,
    mode: str,
) -> str:
    mode_line = {
        "explain": "Explain the core idea on this slide in simpler terms with one short example.",
        "hint": "Give a strategy hint for solving this problem without stating the final answer.",
        "why": "The student wants to understand the reasoning; clarify the solution approach step by step.",
    }.get(mode, "Answer the student's question about this slide.")
    return (
        f"Lesson: {lesson_section} — {lesson_title}\n"
        f"Slide ({slide_kind}): {slide_title}\n"
        f"Section: {slide_section}\n"
        f"Study tip: {study_tip}\n"
        f"Strategy hint: {strategy_hint}\n"
        f"Slide content (plain text):\n{slide_plain[:2800]}\n\n"
        f"Student request ({mode}): {student_question.strip()}\n\n"
        f"Coach instruction: {mode_line}"
    )


def openai_chat_completion(system: str, user: str, *, api_key: str, model: str = "gpt-4o-mini") -> str:
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.35,
            "max_tokens": 550,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"OpenAI API error ({exc.code}): {body}") from exc
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Empty response from AI coach")
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        raise RuntimeError("Empty message from AI coach")
    return content
