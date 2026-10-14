"""English placement exam UI helpers — writing answer packing and display."""

import re

_OPTION_PREFIX = re.compile(r"^\[Option\s+([AB])\]\s*(?:\n+)?(.*)$", re.IGNORECASE | re.DOTALL)


def pack_english_writing_answer(option: str, body: str) -> str:
    """Persist chosen prompt letter with essay text for advisor review."""
    text = (body or "").strip()
    opt = (option or "").strip().upper()
    if opt in ("A", "B"):
        return f"[Option {opt}]\n\n{text}" if text else f"[Option {opt}]\n"
    return text


def unpack_english_writing_answer(raw: str) -> tuple[str, str]:
    """Return (option_letter, essay_body)."""
    blob = (raw or "").strip()
    if not blob:
        return "", ""
    m = _OPTION_PREFIX.match(blob)
    if m:
        return str(m.group(1)).upper(), (m.group(2) or "").strip()
    return "", blob


def merge_form_english_writing(q_kind: str, form) -> str:
    if str(q_kind or "") != "english_writing":
        return (form.get("selected_answer") or "").strip()
    return pack_english_writing_answer(
        form.get("english_writing_option") or "",
        form.get("selected_answer") or "",
    )


def writing_word_targets(topic: str) -> tuple[int, int]:
    if topic == "english_g9_11":
        return 350, 500
    return 200, 300


ENGLISH_PLACEMENT_TOPICS = frozenset({"english_g7_8", "english_g9_11"})


def placement_track_for_topic(topic: str) -> str:
    t = str(topic or "").strip()
    if t in ENGLISH_PLACEMENT_TOPICS or t.startswith("english_"):
        return "english"
    return "math"


def english_writing_max_points(topic: str) -> int:
    return 30 if topic == "english_g9_11" else 20


def essay_word_count(text: str) -> int:
    return len((text or "").strip().split())
