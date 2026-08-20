"""Allowlist HTML sanitization and stem fingerprints for Repair cycles."""
from __future__ import annotations

import hashlib
import re
from html import escape, unescape
from html.parser import HTMLParser
from typing import Any

ALLOWED_TAGS = frozenset(
    {
        "p",
        "div",
        "span",
        "article",
        "section",
        "header",
        "footer",
        "aside",
        "strong",
        "em",
        "b",
        "i",
        "u",
        "br",
        "ol",
        "ul",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "td",
        "th",
        "caption",
        "img",
        "a",
        "figure",
        "figcaption",
        "svg",
        "path",
        "g",
        "line",
        "circle",
        "rect",
        "ellipse",
        "polyline",
        "polygon",
        "text",
        "tspan",
        "defs",
        "use",
        "title",
        "desc",
        "blockquote",
        "code",
        "pre",
        "sup",
        "sub",
        "hr",
        "small",
        "mark",
        "math",
        "mrow",
        "mi",
        "mo",
        "mn",
        "msup",
        "msub",
        "mfrac",
        "msqrt",
        "mtext",
        "mjx-container",
        "mjx-assistive-mml",
    }
)
VOID_TAGS = frozenset({"br", "hr", "img"})
SKIP_TAGS = frozenset({"script", "style", "iframe", "object", "embed", "link", "meta", "form"})
ALLOWED_ATTRS = frozenset(
    {
        "class",
        "id",
        "alt",
        "title",
        "role",
        "aria-label",
        "aria-hidden",
        "width",
        "height",
        "colspan",
        "rowspan",
        "viewbox",
        "xmlns",
        "fill",
        "stroke",
        "stroke-width",
        "stroke-linecap",
        "stroke-linejoin",
        "d",
        "cx",
        "cy",
        "r",
        "rx",
        "ry",
        "x",
        "y",
        "x1",
        "y1",
        "x2",
        "y2",
        "points",
        "transform",
        "lang",
    }
)
URL_ATTRS = frozenset({"src", "href", "xlink:href"})
_TAG_RE = re.compile(r"<[^>]+>", re.S)
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_WS_RE = re.compile(r"\s+")
_SAFE_URL_RE = re.compile(r"^(?:https?:|data:image/|/|#|\./)", re.I)


def coerce_html_source(raw: str) -> str:
    text = "" if raw is None else str(raw).strip()
    if not text:
        return ""
    if "&lt;" in text and not re.search(r"<[a-zA-Z/]", text[:80]):
        text = unescape(text)
    if text.startswith("&lt;"):
        text = unescape(text)
    return text


class _AllowlistSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = (tag or "").lower()
        if tag in SKIP_TAGS:
            self._skip += 1
            return
        if self._skip or tag not in ALLOWED_TAGS:
            return
        attr_html = self._format_attrs(tag, attrs)
        if tag in VOID_TAGS:
            self._chunks.append(f"<{tag}{attr_html}>")
            return
        self._chunks.append(f"<{tag}{attr_html}>")

    def handle_endtag(self, tag: str) -> None:
        tag = (tag or "").lower()
        if tag in SKIP_TAGS:
            if self._skip:
                self._skip -= 1
            return
        if self._skip or tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        self._chunks.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = (tag or "").lower()
        if self._skip or tag in SKIP_TAGS or tag not in ALLOWED_TAGS:
            return
        attr_html = self._format_attrs(tag, attrs)
        self._chunks.append(f"<{tag}{attr_html}>")

    def handle_data(self, data: str) -> None:
        if self._skip or not data:
            return
        self._chunks.append(escape(data, quote=False))

    def handle_comment(self, data: str) -> None:
        return

    def _format_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        parts: list[str] = []
        for name, value in attrs:
            key = (name or "").lower()
            if not key or key.startswith("on") or key.startswith("data-on"):
                continue
            val = "" if value is None else str(value)
            if key in URL_ATTRS:
                if not _SAFE_URL_RE.match(val.strip()) or "javascript:" in val.lower():
                    continue
                parts.append(f' {key}="{escape(val, quote=True)}"')
                continue
            if key not in ALLOWED_ATTRS and not key.startswith("aria-"):
                continue
            parts.append(f' {key}="{escape(val, quote=True)}"')
        return "".join(parts)

    def output(self) -> str:
        return "".join(self._chunks)


def sanitize_repair_html(raw: str) -> str:
    source = coerce_html_source(raw)
    if not source:
        return ""
    parser = _AllowlistSanitizer()
    try:
        parser.feed(source)
        parser.close()
    except Exception:
        return f"<p>{escape(_TAG_RE.sub(' ', source), quote=False)}</p>"
    return parser.output().strip()


def html_to_plain(raw: str) -> str:
    text = _TAG_RE.sub(" ", unescape(coerce_html_source(raw) or ""))
    return _WS_RE.sub(" ", text).strip()


def as_html_fragment(raw: str) -> str:
    source = coerce_html_source(raw)
    if not source:
        return ""
    if re.search(r"<[a-zA-Z]", source):
        return sanitize_repair_html(source)
    return f"<p>{escape(source, quote=False)}</p>"


def stem_normalized_hash(raw: str) -> str:
    plain = html_to_plain(raw).lower()
    plain = _NUM_RE.sub("#", plain)
    plain = re.sub(r"[^\w\s#=+\-]", " ", plain)
    plain = _WS_RE.sub(" ", plain).strip()
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()[:16]


def content_fingerprint(item: dict[str, Any]) -> str:
    stem = str(item.get("stem_html") or item.get("stem") or "")
    asked = str(item.get("asked") or item.get("asked_html") or "")
    choices = "|".join(str(c) for c in (item.get("choices") or []))
    blob = f"{stem_normalized_hash(stem)}|{stem_normalized_hash(asked)}|{stem_normalized_hash(choices)}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def extract_asked_html(item: dict[str, Any]) -> str:
    explicit = str(item.get("asked") or "").strip()
    if explicit:
        return as_html_fragment(explicit)
    stem = coerce_html_source(str(item.get("stem_html") or item.get("stem") or ""))
    plain = html_to_plain(stem)
    sentences = [s.strip() for s in re.split(r"(?<=[.?])\s+", plain) if s.strip()]
    asked = ""
    for chunk in reversed(sentences):
        if "?" in chunk or re.search(r"\b(what|which|how many|find|solve|write)\b", chunk, flags=re.I):
            asked = chunk
            break
    if not asked and sentences:
        asked = sentences[-1]
    if not asked:
        asked = "Answer the question below."
    return f"<p>{escape(asked, quote=False)}</p>"


def distinct_hints(item: dict[str, Any]) -> tuple[str, str]:
    light = str(item.get("light_hint") or "").strip()
    critical = str(item.get("critical_hint") or "").strip()
    if not light:
        light = (
            "Name the structure first: what is given, what stays constant, and what the "
            "question is asking for. Do not write the working equation yet."
        )
    if not critical or critical == light:
        steps = item.get("worked_steps") or []
        setup = ""
        for step in steps[:2]:
            if isinstance(step, dict) and str(step.get("do") or "").strip():
                setup = str(step.get("do")).strip()
                break
        if setup:
            critical = (
                f"Set this up next: {setup} Then write the equation for the unknown. "
                "Do not compute the final numerical answer from this hint alone."
            )
        else:
            critical = (
                "Write the key equation that connects the given snapshots or conditions "
                "to the unknown. Stop before evaluating the final answer."
            )
    if critical == light:
        critical = light + " Now write the key setup equation, but not the final answer."
    return light, critical


def verified_key_markup(item: dict[str, Any]) -> str:
    letter = str(item.get("correct_answer") or "").strip()
    math = str(item.get("correct_math") or item.get("correct_answer_display") or "").strip()
    choices = item.get("choices") or []
    is_letter = len(letter) == 1 and letter.upper() in "ABCDE"
    parts: list[str] = []
    if choices:
        parts.append('<ul class="sl-key-choices">')
        for i, choice in enumerate(choices):
            lab = chr(ord("A") + i)
            correct = is_letter and lab == letter.upper()
            inner = f"{lab}. {choice}"
            if correct:
                inner += " (correct)"
                parts.append(f"<li><strong>{escape(inner, quote=False)}</strong></li>")
            else:
                parts.append(f"<li>{escape(inner, quote=False)}</li>")
        parts.append("</ul>")
    if math:
        parts.append(f"<p>Mathematical conclusion: <strong>{escape(math, quote=False)}</strong></p>")
    elif letter and not is_letter:
        parts.append(f"<p>Verified key: <strong>{escape(letter, quote=False)}</strong></p>")
    elif letter and is_letter and not choices:
        parts.append(f"<p>Verified key: <strong>{escape(letter, quote=False)}</strong></p>")
    if not parts:
        parts.append("<p>Verified key: <strong>—</strong></p>")
    return "".join(parts)


def walkthrough_sections(item: dict[str, Any]) -> dict[str, str]:
    strategy = as_html_fragment(str(item.get("core_idea") or item.get("strategy") or "").strip())
    if not strategy:
        strategy = as_html_fragment(
            "Translate the given information into one equation, then isolate the unknown."
        )
    verified = verified_key_markup(item)
    expl = str(item.get("explanation_en") or item.get("explanation_check") or "").strip()
    steps = item.get("worked_steps") or []
    parts: list[str] = []
    if steps:
        parts.append("<ol class=\"sl-steps\">")
        for step in steps:
            if not isinstance(step, dict):
                continue
            do_html = as_html_fragment(str(step.get("do") or ""))
            why = str(step.get("why") or "").strip()
            why_html = f'<em class="sl-why">Why: {escape(why, quote=False)}</em>' if why else ""
            num = escape(str(step.get("step") or ""), quote=False)
            parts.append(f"<li><strong>Step {num}.</strong> {do_html}{why_html}</li>")
        parts.append("</ol>")
    if expl:
        parts.append(as_html_fragment(expl))
    walkthrough = "".join(parts).strip()
    if not walkthrough:
        walkthrough = as_html_fragment("Re-read the given information and complete the same steps as the example.")
    return {
        "strategy_html": sanitize_repair_html(f'<section class="sl-strategy-body">{strategy}</section>'),
        "verified_key_html": sanitize_repair_html(f'<section class="sl-key-body">{verified}</section>'),
        "walkthrough_html": sanitize_repair_html(f'<section class="sl-walkthrough-body">{walkthrough}</section>'),
    }


def solution_panel_html(item: dict[str, Any]) -> str:
    sections = walkthrough_sections(item)
    html = (
        '<article class="sl-solution-rendered">'
        '<section class="sl-strategy" data-sl-strategy><h2>Strategy</h2>'
        f'{sections["strategy_html"]}</section>'
        '<section class="sl-verified-key" data-sl-verified-key><h2>Verified key</h2>'
        f'{sections["verified_key_html"]}</section>'
        '<section class="sl-walkthrough" data-sl-walkthrough><h2>Full walkthrough</h2>'
        f'{sections["walkthrough_html"]}</section>'
        "</article>"
    )
    return sanitize_repair_html(html)


def normalize_item_for_render(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    stem_source = str(out.get("stem_html") or out.get("stem") or "").strip()
    figure_source = str(out.get("figure_html") or out.get("figure") or "").strip()
    out["stem_html"] = as_html_fragment(stem_source)
    out["figure_html"] = as_html_fragment(figure_source) if figure_source else ""
    out["asked_html"] = extract_asked_html(out)
    out["stem_plain"] = html_to_plain(out["stem_html"])
    out["stem_hash"] = stem_normalized_hash(out["stem_html"])
    out["content_fingerprint"] = content_fingerprint(out)
    out["item_id"] = str(out.get("id") or out.get("_ref") or "")
    light, critical = distinct_hints(out)
    out["light_hint"] = light
    out["critical_hint"] = critical
    sections = walkthrough_sections(out)
    out.update(sections)
    out["solution_html"] = solution_panel_html(out)
    if isinstance(out.get("choices"), list):
        out["choices"] = [str(c) for c in out["choices"]]
    else:
        out["choices"] = []
    return out
