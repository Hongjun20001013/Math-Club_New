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
    return 20


def _dedupe_paragraphs(text: str) -> str:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for p in paras:
        key = re.sub(r"\s+", " ", p.lower())[:160]
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return "\n\n".join(out)


def clean_essay_body_for_display(body: str, option: str = "") -> str:
    """Strip accidental prompt paste from the essay field."""
    text = (body or "").strip()
    if not text:
        return ""
    text = re.sub(
        r"^\[Option\s+([AB])\]\s*(?:ption\s+[AB]\s*·)?",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    ).lstrip()
    opt = (option or "").strip().upper()
    for prefix in (
        f"[Option {opt}]",
        f"Option {opt}",
        f"Option {opt} ·",
        f"Option {opt} -",
        "Option A · Personal experience",
        "Option B · Argument",
    ):
        if text.startswith(prefix):
            text = text[len(prefix) :].lstrip(" ·-\n")
    lines = [ln.strip() for ln in text.splitlines()]
    while lines and lines[0].lower().startswith("prompt:"):
        lines.pop(0)
    filtered: list[str] = []
    skip_phrases = (
        "everyone faces moments that are hard",
        "some people believe homework helps",
        "prompt:",
        "write about a time you faced a challenge",
        "should middle school students have homework",
        "will ai do more good than harm",
    )
    for ln in lines:
        low = ln.lower()
        if low.startswith("option a ·") or low.startswith("option b ·"):
            continue
        if any(low.startswith(p) for p in skip_phrases) and len(ln) < 200:
            continue
        filtered.append(ln)
    text = "\n\n".join(filtered).strip()
    return _dedupe_paragraphs(text)


def essay_word_count(text: str) -> int:
    return len((text or "").strip().split())


def filter_writing_prompt_for_review(prompt_html: str, option: str) -> str:
    """Show only the prompt the student chose (G7-8 A/B); drop duplicate option cards."""
    html = (prompt_html or "").strip()
    opt = (option or "").strip().upper()
    if not html or opt not in ("A", "B"):
        return html
    hide = "B" if opt == "A" else "A"
    hide_pat = re.compile(
        rf'<article\s+class="np-en-writing-option"[^>]*>\s*<h3>\s*Option\s+{hide}\b.*?</article>',
        re.DOTALL | re.IGNORECASE,
    )
    html = hide_pat.sub("", html)
    html = re.sub(
        r'<p\s+class="np-en-writing-prompt__lead"[^>]*>.*?</p>',
        "",
        html,
        count=1,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return html.strip()
