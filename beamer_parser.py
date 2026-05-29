"""Parse Beamer slide decks (.tex) into rich HTML slides for the course materials viewer."""
from __future__ import annotations

import re
from typing import Any, Optional

from latex_parser import (
    _convert_latex_lists,
    _extract_braced_content,
    clean_math,
    latex_array_and_tabular_to_html,
    strip_document_noise,
)


def _strip_beamer_preamble(tex: str) -> str:
    idx = tex.find(r"\begin{document}")
    if idx >= 0:
        tex = tex[idx + len(r"\begin{document}") :]
    end = tex.rfind(r"\end{document}")
    if end >= 0:
        tex = tex[:end]
    return tex


def _extract_beamer_field(tex: str, command: str) -> str:
    m = re.search(
        r"\\" + command + r"(?:\[[^\]]*\])?\{((?:[^{}]|\{[^{}]*\})*)\}",
        tex,
        re.S,
    )
    if not m:
        return ""
    raw = _unwrap_inline_markup(m.group(1))
    raw = re.sub(r"\\\\", " · ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def _extract_document_title(tex: str) -> str:
    return _extract_beamer_field(tex, "title")


def _extract_document_meta(tex: str) -> dict[str, str]:
    title = _extract_document_title(tex)
    author = _extract_beamer_field(tex, "author")
    institute = _extract_beamer_field(tex, "institute")
    return {
        "title": title,
        "author": author,
        "institute": institute or "Novel Prep",
    }


def _split_title_lines(deck_title: str) -> tuple[str, str]:
    title = re.sub(r"\s*·\s*", " · ", deck_title).strip()
    if " · " in title:
        parts = [p.strip() for p in title.split(" · ", 1)]
        return parts[0], parts[1]
    m = re.match(r"^(SAT\s+Unit\s+[\d.]+)\s+(.+)$", title, re.I)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "SAT Course Material", title or "Lesson overview"


def _build_intro_html(meta: dict[str, str], lesson_path: list[dict[str, Any]]) -> str:
    unit_line, topic_line = _split_title_lines(meta.get("title", ""))
    author = meta.get("author", "")
    institute = meta.get("institute", "Novel Prep")
    chip_parts: list[str] = []
    for i, item in enumerate(lesson_path[:4], 1):
        title = str(item.get("title") or "").strip()
        idx = int(item.get("index") or 0)
        if title and idx:
            chip_parts.append(
                f'<button type="button" class="cm-intro-chip" data-cm-jump-section="{idx}">'
                f'<span class="cm-intro-chip-num">{i:02d}</span>'
                f'<span class="cm-intro-chip-label">{title}</span>'
                f"</button>"
            )
    if not chip_parts:
        for name in ("Concepts", "Examples", "Practice", "Review"):
            chip_parts.append(f'<span class="cm-intro-chip">{name}</span>')
    chip_html = "".join(chip_parts)
    author_html = (
        f'<span class="cm-intro-meta-item"><em>Presenter</em>{author}</span>'
        if author
        else ""
    )
    return (
        '<div class="cm-intro-canvas">'
        '<div class="cm-intro-bg" aria-hidden="true">'
        '<span class="cm-intro-orb cm-intro-orb--1"></span>'
        '<span class="cm-intro-orb cm-intro-orb--2"></span>'
        '<span class="cm-intro-grid"></span>'
        "</div>"
        '<div class="cm-intro-content">'
        '<span class="cm-intro-kicker">Lesson introduction</span>'
        f'<p class="cm-intro-unit">{unit_line}</p>'
        f'<h1 class="cm-intro-title">{topic_line}</h1>'
        '<p class="cm-intro-lede">Work through guided examples and SAT-style practice. '
        "Use study mode to try problems before revealing solutions.</p>"
        f'<div class="cm-intro-meta">{author_html}'
        f'<span class="cm-intro-meta-item"><em>From</em>{institute}</span>'
        "</div>"
        f'<div class="cm-intro-chips">{chip_html}</div>'
        '<p class="cm-intro-cta">Tap a section above, or press <strong>Next</strong> for the full outline</p>'
        "</div>"
        "</div>"
    )


def _build_contents_html(
    meta: dict[str, str],
    deck_title: str,
    lesson_path: list[dict[str, Any]],
    slide_count: int,
) -> str:
    unit_line, topic_line = _split_title_lines(meta.get("title", "") or deck_title)
    rows: list[str] = []
    for i, item in enumerate(lesson_path, 1):
        title = str(item.get("title") or "").strip()
        idx = int(item.get("index") or 0)
        if not title or not idx:
            continue
        rows.append(
            f'<li><button type="button" class="cm-content-item" data-cm-jump-section="{idx}">'
            f'<span class="cm-content-num">{i:02d}</span>'
            f'<span class="cm-content-copy"><strong>{title}</strong>'
            f'<span>Session {i:02d} · jump to section start</span></span>'
            f'<span class="cm-content-arrow" aria-hidden="true">→</span>'
            f"</button></li>"
        )
    list_html = "".join(rows) or "<li><p class=\"cm-content-empty\">Sections will appear here once parsed.</p></li>"
    count_label = f"{slide_count} slides" if slide_count else "this lesson"
    return (
        '<div class="cm-content-canvas">'
        '<div class="cm-content-bg" aria-hidden="true">'
        '<span class="cm-content-orb cm-content-orb--1"></span>'
        '<span class="cm-content-orb cm-content-orb--2"></span>'
        '<span class="cm-content-grid"></span>'
        "</div>"
        '<div class="cm-content-inner">'
        '<span class="cm-content-kicker">Lesson outline</span>'
        f'<p class="cm-content-unit">{unit_line}</p>'
        f'<h2 class="cm-content-title">{topic_line}</h2>'
        f'<p class="cm-content-lede">{count_label} · tap any section to jump there instantly.</p>'
        f'<ol class="cm-content-list">{list_html}</ol>'
        "</div>"
        "</div>"
    )


def _remove_environment(text: str, env: str) -> str:
    out = text
    begin = rf"\begin{{{env}}}"
    end = rf"\end{{{env}}}"
    while True:
        m = re.search(re.escape(begin), out)
        if not m:
            break
        end_idx = out.find(end, m.end())
        if end_idx == -1:
            out = out[: m.start()] + out[m.end() :]
            continue
        out = out[: m.start()] + out[end_idx + len(end) :]
    return out


def _unwrap_environment(text: str, env: str) -> str:
    """Replace \\begin{env}…\\end{env} with its inner content (keep figures/text)."""
    out = text
    begin = rf"\begin{{{env}}}"
    end = rf"\end{{{env}}}"
    while True:
        m = re.search(re.escape(begin), out)
        if not m:
            break
        end_idx = out.find(end, m.end())
        if end_idx == -1:
            out = out[: m.start()] + out[m.end() :]
            continue
        inner = out[m.end() : end_idx].strip()
        out = out[: m.start()] + inner + out[end_idx + len(end) :]
    return out


def _replace_course_material_figures(text: str) -> str:
    """Turn \\includegraphics{file} into slide figures under /static/course_materials/."""

    def repl(m: re.Match[str]) -> str:
        fname = m.group(1).strip()
        safe = re.sub(r"[^a-zA-Z0-9._-]", "", fname)
        if not safe:
            return ""
        if safe == "E73.png":
            safe = "E73.svg"
        if safe == "E74.png":
            safe = "E74.svg"
        if safe == "E14.png":
            safe = "E14.svg"
        return (
            f'<div class="cm-slide-figure"><img class="stem-figure-img cm-slide-figure-img" '
            f'src="/static/course_materials/{safe}" alt="" loading="lazy" /></div>'
        )

    return re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", repl, text)


def _unwrap_inline_markup(text: str) -> str:
    """Turn nested \\textbf / \\textcolor / font wrappers into plain text or HTML."""
    out = text
    for _ in range(12):
        prev = out
        out = re.sub(
            r"\\textcolor\{[^}]+\}\{((?:[^{}]|\{[^{}]*\})*)\}",
            r"\1",
            out,
            flags=re.S,
        )
        out = re.sub(
            r"\\(?:textbf|bfseries|textit|itshape|emph|textsf|textrm|text)\{((?:[^{}]|\{[^{}]*\})*)\}",
            r"\1",
            out,
            flags=re.S,
        )
        out = re.sub(
            r"\{\\(?:Huge|huge|LARGE|Large|large|small|footnotesize|normalsize)\s+((?:[^{}]|\{[^{}]*\})*)\}",
            r"\1",
            out,
            flags=re.S,
        )
        if out == prev:
            break
    out = re.sub(r"\\(?:Huge|huge|LARGE|Large|large|small|footnotesize|normalsize)\b", "", out)
    out = re.sub(r"\\(?:bfseries|itshape)\b", "", out)
    return out


def _replace_braced_command(text: str, command: str, repl_fn) -> str:
    marker = f"\\{command}"
    out = text
    i = 0
    while True:
        idx = out.find(marker, i)
        if idx == -1:
            break
        brace_at = idx + len(marker)
        while brace_at < len(out) and out[brace_at].isspace():
            brace_at += 1
        if brace_at >= len(out) or out[brace_at] != "{":
            i = idx + len(marker)
            continue
        content, end = _extract_braced_content(out, brace_at)
        if content is None:
            out = out[:idx] + out[idx + len(marker) :]
            continue
        replacement = repl_fn(content)
        out = out[:idx] + replacement + out[end:]
        i = idx + len(replacement)
    return out


def _replace_textcolor_commands(text: str) -> str:
    """Convert \\textcolor{color}{content} without breaking on nested braces."""
    marker = r"\textcolor"
    out = text
    i = 0
    highlight_colors = {
        "novelpurple",
        "purpleblue",
        "nppurple",
        "nppurple2",
        "novelblue",
    }
    while True:
        idx = out.find(marker, i)
        if idx == -1:
            break
        pos = idx + len(marker)
        while pos < len(out) and out[pos].isspace():
            pos += 1
        if pos >= len(out) or out[pos] != "{":
            i = idx + 1
            continue
        color, pos = _extract_braced_content(out, pos)
        if color is None:
            i = idx + 1
            continue
        while pos < len(out) and out[pos].isspace():
            pos += 1
        if pos >= len(out) or out[pos] != "{":
            i = idx + 1
            continue
        content, end = _extract_braced_content(out, pos)
        if content is None:
            i = idx + 1
            continue
        inner = _apply_inline_markup(content)
        if color.strip().lower() in highlight_colors or "purple" in color.lower():
            replacement = f'<span class="cm-answer-highlight">{inner}</span>'
        else:
            replacement = inner
        out = out[:idx] + replacement + out[end:]
        i = idx + len(replacement)
    return out


def _apply_inline_markup(text: str) -> str:
    """Apply inline LaTeX text commands to a fragment (no block-level conversion)."""
    text = _replace_braced_command(
        text,
        "textbf",
        lambda c: f"<strong>{_apply_inline_markup(c)}</strong>",
    )
    text = _replace_braced_command(
        text,
        "textit",
        lambda c: f"<em>{_apply_inline_markup(c)}</em>",
    )
    text = _replace_braced_command(
        text,
        "emph",
        lambda c: f"<em>{_apply_inline_markup(c)}</em>",
    )
    text = _replace_braced_command(
        text,
        "text",
        lambda c: _apply_inline_markup(c),
    )
    text = _replace_braced_command(
        text,
        "textsf",
        lambda c: f'<span class="cm-sans">{_apply_inline_markup(c)}</span>',
    )
    text = _replace_braced_command(
        text,
        "boxed",
        lambda c: f'<span class="cm-answer-box">{_apply_inline_markup(c)}</span>',
    )
    return _unwrap_inline_markup(text)


def _convert_semantic_markup(text: str) -> str:
    text = _replace_textcolor_commands(text)
    text = _apply_inline_markup(text)
    return text


def _scrub_latex_remnants(text: str) -> str:
    """Remove leftover publisher color macros and broken command fragments."""
    text = re.sub(
        r"color\{(?:novelPurple|purpleblue|nppurple2?|novelblue)\}\{((?:[^{}]|<[^>]+>)*)\}",
        r'<span class="cm-answer-highlight">\1</span>',
        text,
        flags=re.S,
    )
    text = re.sub(
        r"color\{[^}]+\}\{((?:[^{}]|\{[^{}]*\})*)\}",
        r"\1",
        text,
        flags=re.S,
    )
    text = re.sub(r"\\color\{[^}]+\}\s*", "", text)
    text = re.sub(
        r"\\(?:textrm|textsf|textit|textbf|textit|emph|bfseries|itshape)\b\s*",
        "",
        text,
    )
    text = re.sub(r"\{,\}", ",", text)
    return text


def _strip_beamer_layout_commands(text: str) -> str:
    text = re.sub(r"\\(?:small|footnotesize|normalsize|large|Large|LARGE|Huge|huge)\b\s*", "", text)
    text = re.sub(r"\\centering\b\s*", "", text)
    text = re.sub(r"\\(?:raggedright|raggedleft)\b\s*", "", text)
    text = re.sub(r"\\(?:medskip|bigskip|smallskip|vfill)\b\s*", "\n", text)
    text = re.sub(r"\\vspace\*?\{[^}]*\}", "\n", text)
    text = re.sub(r"\\hspace\*?\{[^}]*\}", " ", text)
    text = re.sub(r"\\(?:noindent|newline|linebreak)\b\s*", "\n", text)
    text = re.sub(r"\\pause\b\s*", "", text)
    text = re.sub(r"\\only<[^>]+>\{((?:[^{}]|\{[^{}]*\})*)\}", r"\1", text, flags=re.S)
    text = re.sub(r"\\section\*?\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\subsection\*?\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\tableofcontents\b", "", text)
    text = re.sub(r"\\titlepage\b", "", text)
    text = re.sub(r"\\column\{[^}]*\}", "", text)
    text = re.sub(r"\\\[(\d+(?:\.\d+)?(?:em|cm|pt|mm))\]", "\n", text)
    text = re.sub(r"^\s*\[(\d+(?:\.\d+)?(?:em|cm|pt|mm))\]\s*$", "", text, flags=re.M)
    text = re.sub(r"^\s*\{+\s*([^}]+)\s*\}+\s*$", r"\1", text, flags=re.M)
    return text


def _convert_beamer_enumerate(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        body = m.group(1)
        parts = re.split(r"\\item\s*", body)
        choices: list[tuple[str, str]] = []
        for chunk in parts:
            chunk = chunk.strip()
            if not chunk:
                continue
            label = ""
            mlab = re.match(r"^\[([^\]]*)\]\s*(.*)$", chunk, re.S)
            if mlab:
                label = re.sub(r"\\textbf\{([^{}]*)\}", r"\1", mlab.group(1)).strip()
                label = label.rstrip(".")
                chunk = mlab.group(2).strip()
            letter = re.match(r"^([A-D])\.?", label)
            if letter:
                label = letter.group(1)
            choices.append((label, chunk))

        if choices and all(c[0] in {"A", "B", "C", "D"} for c in choices):
            cells = []
            for letter, content in choices:
                cells.append(
                    f'<div class="cm-mcq-choice"><span class="cm-mcq-letter">{letter}</span>'
                    f'<span class="cm-mcq-text">{content}</span></div>'
                )
            return '<div class="cm-mcq-grid">' + "".join(cells) + "</div>"
        lis = []
        for label, content in choices:
            if label:
                lis.append(
                    f'<li class="stem-li-labeled"><span class="stem-li-marker">{label}</span>'
                    f'<span class="stem-li-body">{content}</span></li>'
                )
            else:
                lis.append(f"<li>{content}</li>")
        return '<ol class="stem-enumerate cm-beamer-list">' + "".join(lis) + "</ol>"

    return re.sub(
        r"\\begin\{enumerate\}(.*?)\\end\{enumerate\}",
        repl,
        text,
        flags=re.S,
    )


def _convert_dash_bullets(text: str) -> str:
    lines = text.split("\n")
    parts: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("- "):
            items: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:].strip())
                i += 1
            lis = "".join(f"<li>{item}</li>" for item in items if item)
            parts.append(f'<ul class="stem-itemize cm-dash-list">{lis}</ul>')
            continue
        parts.append(lines[i])
        i += 1
    return "\n".join(parts)


def _convert_align_blocks_for_mathjax(text: str) -> str:
    """Convert amsmath align blocks into MathJax aligned display math."""

    def repl(m: re.Match[str]) -> str:
        body = m.group(1).strip()
        lines = [ln.strip() for ln in re.split(r"\\\\", body) if ln.strip()]
        if not lines:
            return ""
        inner = " \\\\\n".join(lines)
        return f"\\[\\begin{{aligned}}\n{inner}\n\\end{{aligned}}\\]"

    return re.sub(
        r"\\begin\{align\*?\}(.*?)\\end\{align\*?\}",
        repl,
        text,
        flags=re.S,
    )


def _repair_math_delimiters(text: str) -> str:
    """Fix inline/display delimiters broken by legacy cleanup passes."""
    text = re.sub(r"\\\(\s*([^)]+?)\s+\)", r"\\(\1\\)", text)
    text = re.sub(
        r"(<div class=\"stem-math-block cm-math-block\">\\\[.*?)\n\s*\]",
        r"\1\n\\]",
        text,
        flags=re.S,
    )
    text = re.sub(
        r"(?<!<div class=\"stem-math-block cm-math-block\">)\\\[(.*?)\n\s*\](?!\\])",
        r"\\[\1\\]",
        text,
        flags=re.S,
    )
    return text


_HTML_IN_MATH_TAG = re.compile(
    r"<(?:span|strong|em)\b[^>]*>.*?</(?:span|strong|em)>",
    re.S | re.I,
)


def _split_latex_and_html(inner: str) -> tuple[str, str]:
    html_chunks = _HTML_IN_MATH_TAG.findall(inner)
    if not html_chunks:
        return inner.strip(), ""
    latex = _HTML_IN_MATH_TAG.sub("", inner)
    latex = re.sub(r"\s+", " ", latex).strip()
    return latex, " ".join(html_chunks)


def _fix_html_in_display_math(text: str) -> str:
    """Move HTML answer highlights out of \\[ \\] / \\( \\) so MathJax can render."""

    def fix_delimited(open_d: str, close_d: str, body: str) -> str:
        out: list[str] = []
        i = 0
        olen, clen = len(open_d), len(close_d)
        while i < len(body):
            idx = body.find(open_d, i)
            if idx == -1:
                out.append(body[i:])
                break
            out.append(body[i:idx])
            end = body.find(close_d, idx + olen)
            if end == -1:
                out.append(body[idx:])
                break
            inner = body[idx + olen : end]
            if "<" not in inner:
                out.append(body[idx : end + clen])
            else:
                latex, html = _split_latex_and_html(inner)
                if latex:
                    out.append(f"{open_d}{latex}{close_d}")
                if html:
                    if latex:
                        out.append(" ")
                    out.append(html)
            i = end + clen
        return "".join(out)

    text = fix_delimited(r"\[", r"\]", text)

    def fix_inline(m: re.Match[str]) -> str:
        inner = m.group(1)
        if "<" not in inner:
            return m.group(0)
        latex, html = _split_latex_and_html(inner)
        parts: list[str] = []
        if latex:
            parts.append(r"\(" + latex + r"\)")
        if html:
            parts.append(html)
        return " ".join(parts)

    return re.sub(r"\\?\((.*?)\\?\)", fix_inline, text, flags=re.S)


def _sanitize_answer_boxes(html: str) -> str:
    """Strip leftover LaTeX text commands inside rendered answer boxes."""

    def clean_inner(inner: str) -> str:
        out = inner.strip()
        out = re.sub(r"\\text\{([^}]*)\}", r"\1", out)
        out = re.sub(r"\\mathbf\{([^}]*)\}", r"\1", out)
        out = re.sub(r"\\(?:textbf|textit|emph)\{([^}]*)\}", r"\1", out)
        out = re.sub(r"\{,\}", ",", out)
        return re.sub(r"\s+", " ", out).strip()

    return re.sub(
        r'(<span class="cm-answer-box">)(.*?)(</span>)',
        lambda m: f"{m.group(1)}{clean_inner(m.group(2))}{m.group(3)}",
        html,
        flags=re.S,
    )


def _normalize_display_math(text: str) -> str:
    """Wrap \\[ ... \\] blocks anywhere (including inside list items)."""
    out: list[str] = []
    i = 0
    while i < len(text):
        idx = text.find(r"\[", i)
        if idx == -1:
            out.append(text[i:])
            break
        out.append(text[i:idx])
        end = text.find(r"\]", idx + 2)
        if end == -1:
            bare = text.find("]", idx + 2)
            if bare == -1:
                out.append(text[idx:])
                break
            block = text[idx : bare + 1]
            if block.endswith("]") and not block.endswith(r"\]"):
                block = block[:-1] + r"\]"
            out.append(f'<div class="stem-math-block cm-math-block">{block}</div>')
            i = bare + 1
            continue
        block = text[idx : end + 2]
        out.append(f'<div class="stem-math-block cm-math-block">{block}</div>')
        i = end + 2
    return "".join(out)


def _clean_beamer_noise(text: str) -> str:
    lines_out = []
    for raw in text.splitlines():
        line = re.sub(r"(?<!\\)%.*$", "", raw).rstrip()
        if re.match(r"^--\s*\d+\s+of\s+\d+\s*--$", line.strip()):
            continue
        lines_out.append(line)
    text = "\n".join(lines_out)
    text = re.sub(r"\\newpage\s*", "", text)
    text = re.sub(r"\\pagebreak\s*", "", text)
    text = text.replace("{,}", ",")
    text = text.replace(r"\%", "%")
    return strip_document_noise(text)


def _convert_markdown_bold(text: str) -> str:
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)


def _format_plain_paragraphs(text: str) -> str:
    lines = [line.strip() for line in text.split("\n")]
    html_parts: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue
        if line.startswith("- "):
            items: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:].strip())
                i += 1
            lis = "".join(f"<li>{item}</li>" for item in items if item)
            html_parts.append(f'<ul class="stem-itemize cm-dash-list">{lis}</ul>')
            continue
        html_parts.append(f"<p>{line}</p>")
        i += 1
    return "\n".join(html_parts)


def _format_beamer_html(text: str) -> str:
    block_pat = (
        r'(<div class="(?:stem-math-block|cm-math-block)[^"]*">.*?</div>'
        r'|<ul[^>]*>.*?</ul>|<ol[^>]*>.*?</ol>'
        r'|<div class="cm-mcq-grid">.*?</div>'
        r'|<div class="stem-table-wrap">.*?</div>'
        r'|<div class="cm-section-divider">.*?</div>'
        r'|<div class="cm-slide-closing">.*?</div>'
        r'|<div class="cm-intro-canvas">.*?</div>'
        r'|<div class="cm-content-canvas">.*?</div>'
        r'|<div class="cm-closing-canvas">.*?</div>)'
    )
    parts = re.split(block_pat, text, flags=re.S)
    out: list[str] = []
    for i, part in enumerate(parts):
        if not part:
            continue
        if part.startswith("<"):
            out.append(part)
        else:
            out.append(_format_plain_paragraphs(part))
    return "\n".join(out)


def _build_closing_html(
    body: str,
    *,
    deck_title: str = "",
    slide_count: int = 0,
    section_titles: list[str] | None = None,
) -> str:
    plain = _unwrap_inline_markup(body)
    plain = _strip_beamer_layout_commands(plain)
    plain = re.sub(r"\\+\s*$", "", plain, flags=re.M)
    plain = re.sub(r"\s*\\+\s*", " ", plain)
    lines = [ln.strip() for ln in plain.split("\n") if ln.strip()]
    subtitle = "We appreciate your time and focus."
    brand = "Novel Prep"
    for ln in lines:
        low = ln.lower()
        if "appreciate" in low or "focus" in low:
            subtitle = ln
        elif "novel prep" in low:
            brand = "Novel Prep"
    _, topic_line = _split_title_lines(deck_title)
    topic_line = topic_line or deck_title or "this lesson"
    count_label = f"{slide_count} slides" if slide_count else "all slides"
    chips = section_titles or []
    chip_html = "".join(f'<span class="cm-closing-chip">{name}</span>' for name in chips[:5])
    chips_block = f'<div class="cm-closing-chips">{chip_html}</div>' if chip_html else ""
    return (
        '<div class="cm-closing-canvas">'
        '<div class="cm-closing-bg" aria-hidden="true">'
        '<span class="cm-closing-orb cm-closing-orb--1"></span>'
        '<span class="cm-closing-orb cm-closing-orb--2"></span>'
        '<span class="cm-closing-orb cm-closing-orb--3"></span>'
        '<span class="cm-closing-shimmer"></span>'
        "</div>"
        '<div class="cm-closing-content">'
        '<div class="cm-closing-badge" aria-hidden="true">'
        '<svg class="cm-closing-ring" viewBox="0 0 88 88">'
        '<circle class="cm-closing-ring-track" cx="44" cy="44" r="38"></circle>'
        '<circle class="cm-closing-ring-fill" cx="44" cy="44" r="38"></circle>'
        "</svg>"
        '<span class="cm-closing-check">✓</span>'
        "</div>"
        '<p class="cm-closing-eyebrow">Lesson complete</p>'
        '<h2 class="cm-closing-title">Outstanding work</h2>'
        f'<p class="cm-closing-sub">You finished {count_label} on '
        f"<strong>{topic_line}</strong>. {subtitle}</p>"
        f"{chips_block}"
        '<footer class="cm-closing-footer">'
        '<p class="cm-closing-thanks">Thank you</p>'
        '<div class="cm-closing-brand">'
        '<span class="cm-closing-brand-mark">N</span>'
        f'<div class="cm-closing-brand-copy"><strong>{brand}</strong>'
        "<span>Excellence in SAT Prep</span></div>"
        "</div>"
        "</footer>"
        "</div>"
        "</div>"
    )


def _wrap_inline_solution(html: str) -> str:
    """Hide worked solution until the student chooses to reveal it."""
    m = re.search(
        r"(.*?)(<p><strong>Solution:\s*</strong></p>)([\s\S]+)",
        html,
        flags=re.I | re.S,
    )
    if not m or not m.group(3).strip():
        return html
    banner = (
        '<div class="cm-try-banner" data-cm-try-banner>'
        '<div class="cm-try-banner-icon" aria-hidden="true">✦</div>'
        '<div class="cm-try-banner-copy">'
        "<strong>Your turn</strong>"
        "<span>Work it out on paper first — reveal when you're ready.</span>"
        "</div>"
        '<button type="button" class="cm-reveal-btn" data-cm-reveal-solution>'
        "Show solution"
        "</button>"
        "</div>"
    )
    panel = (
        f'<div class="cm-solution-panel cm-is-collapsed" data-cm-solution-panel>'
        f"{m.group(3)}</div>"
    )
    return m.group(1) + banner + m.group(2) + panel


def _wrap_solution_steps(html: str) -> str:
    """Break multi-step solutions into progressive reveal blocks."""
    if not re.search(r"<p><strong>Step\s+\d+", html, re.I):
        return html
    parts = re.split(r"(?=<p><strong>Step\s+\d+)", html, flags=re.I)
    if len(parts) <= 1:
        return html
    toolbar = (
        '<div class="cm-steps-toolbar" data-cm-steps-toolbar>'
        '<span class="cm-steps-label">Walk through the solution</span>'
        '<div class="cm-steps-actions">'
        '<button type="button" class="cm-steps-btn" data-cm-next-step>Next step</button>'
        '<button type="button" class="cm-steps-btn cm-steps-btn--ghost" data-cm-show-all-steps>'
        "Show all"
        "</button>"
        "</div>"
        "</div>"
    )
    blocks: list[str] = [parts[0]]
    step_num = 0
    for part in parts[1:]:
        step_num += 1
        hidden = " cm-step--hidden" if step_num > 1 else ""
        blocks.append(
            f'<div class="cm-step-block{hidden}" data-step="{step_num}">{part}</div>'
        )
    return toolbar + "".join(blocks)


def _wrap_answer_choices(html: str) -> str:
    """Turn A–D answer choice lists into interactive pickers."""
    m = re.search(
        r"(<p><strong>Answer Choices:\s*</strong></p>\s*)"
        r'(<ul class="stem-itemize">(.*?)</ul>)',
        html,
        flags=re.I | re.S,
    )
    if not m:
        return html
    choices: list[str] = []
    for item in re.finditer(
        r'<li class="stem-li-labeled"><span class="stem-li-marker">([A-D])\.?</span>\s*'
        r'<span class="stem-li-body">(.*?)</span></li>',
        m.group(3),
        flags=re.S,
    ):
        letter, body = item.group(1), item.group(2)
        choices.append(
            f'<button type="button" class="cm-mcq-choice" data-choice="{letter}">'
            f'<span class="cm-mcq-letter">{letter}</span>'
            f'<span class="cm-mcq-text">{body}</span>'
            "</button>"
        )
    if not choices:
        return html
    grid = (
        '<div class="cm-mcq-interactive" data-cm-mcq>'
        '<p class="cm-mcq-prompt">Select your answer, then check when ready.</p>'
        '<div class="cm-mcq-grid">'
        + "".join(choices)
        + "</div>"
        '<div class="cm-mcq-actions">'
        '<button type="button" class="cm-mcq-check" data-cm-check-mcq disabled>Check answer</button>'
        '<button type="button" class="cm-mcq-skip" data-cm-go-answer>View worked solution →</button>'
        "</div>"
        "</div>"
    )
    return html[: m.start()] + m.group(1) + grid + html[m.end() :]


def _wrap_question_challenge(html: str, title: str) -> str:
    """Add a try-first banner on standalone question slides."""
    if "cm-try-banner" in html or "cm-mcq-interactive" in html:
        return html
    tl = title.lower()
    if not any(k in tl for k in ("question", "problem", "word problem", "example")):
        return html
    if re.search(r"<p><strong>Step\s+\d+", html, re.I):
        return html
    banner = (
        '<div class="cm-try-banner cm-try-banner--question" data-cm-try-banner>'
        '<div class="cm-try-banner-icon" aria-hidden="true">?</div>'
        '<div class="cm-try-banner-copy">'
        "<strong>Try it yourself</strong>"
        "<span>Pause here and attempt the problem before viewing the solution.</span>"
        "</div>"
        '<button type="button" class="cm-reveal-btn cm-reveal-btn--ghost" data-cm-go-answer>'
        "Go to solution →"
        "</button>"
        "</div>"
    )
    return banner + html


def _needs_math_delimiters(text: str) -> bool:
    t = re.sub(r"<[^>]+>", "", text).strip()
    if not t:
        return False
    if re.search(r"Option\s+[A-D]|only\)", t, re.I):
        return False
    if re.match(r"^[A-D]\.$", t.strip()):
        return False
    return bool(re.search(r"\\frac|\\Rightarrow|\\neq|=|\^|_[{]|\\boxed|\d+\.?\d*[a-z]|[a-z]\s*[-+]", t))


def _strip_inline_math_delimiters(text: str) -> str:
    out = text.strip()
    out = re.sub(r"^\\?\(", "", out)
    out = re.sub(r"\\?\)$", "", out)
    out = re.sub(r"\\text\{([^}]*)\}", r"\1", out)
    out = re.sub(r"\\mathbf\{([^}]*)\}", r"\1", out)
    return out.strip()


def _answer_card(label: str, value_html: str) -> str:
    clean_label = label.rstrip(":").strip()
    return (
        f'<div class="cm-answer-card">'
        f'<span class="cm-answer-card-label">{clean_label}</span>'
        f'<div class="cm-answer-card-value">{value_html}</div>'
        f"</div>"
    )


def _format_answer_value(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(
        r'^\\?\(\s*(<span class="cm-answer-box">.*?</span>)\s*\\?\)$',
        r"\1",
        raw,
        flags=re.S,
    )
    box_m = re.search(r'<span class="cm-answer-box">(.*?)</span>', raw, flags=re.S)
    if box_m and raw.strip() in {box_m.group(0), f"\\({box_m.group(0)}\\)"}:
        inner = _strip_inline_math_delimiters(box_m.group(1))
        if _needs_math_delimiters(inner):
            return f'<span class="cm-answer-card-math">\\({inner}\\)</span>'
        return inner
    hl_m = re.search(
        r'<span class="cm-answer-highlight"><strong>(.*?)</strong></span>',
        raw,
        flags=re.S,
    )
    if hl_m:
        inner = _strip_inline_math_delimiters(hl_m.group(1))
        if _needs_math_delimiters(inner):
            return f'<span class="cm-answer-card-math">\\({inner}\\)</span>'
        return inner
    hl_m = re.search(
        r'<span class="cm-answer-highlight">(.*?)</span>',
        raw,
        flags=re.S,
    )
    if hl_m:
        inner = _strip_inline_math_delimiters(hl_m.group(1))
        if inner in {"A", "B", "C", "D"} or re.match(r"^[A-D]\.?$", inner):
            return f"<strong>{inner.rstrip('.')}</strong>"
        if _needs_math_delimiters(inner):
            return f'<span class="cm-answer-card-math">\\({inner}\\)</span>'
        return inner
    plain = re.sub(r"<[^>]+>", "", raw).strip()
    plain = _strip_inline_math_delimiters(plain)
    if plain in {"A", "B", "C", "D"} or re.match(r"^[A-D]\.?$", plain):
        return f"<strong>{plain.rstrip('.')}</strong>"
    if _needs_math_delimiters(plain):
        return f'<span class="cm-answer-card-math">\\({plain}\\)</span>'
    if plain and not re.search(r"[<>]", raw):
        return plain
    return raw


def _polish_answer_lines(html: str) -> str:
    """Turn legacy \\( … \\) answer markup into premium answer cards."""
    html = re.sub(
        r'<p><strong>(Final Answer|Correct Answer):\s*</strong>\s*(.*?)</p>',
        lambda m: _answer_card(m.group(1), _format_answer_value(m.group(2))),
        html,
        flags=re.S | re.I,
    )
    html = re.sub(
        r'<p><strong>(Final Answer|Correct Answer):\s*<span class="cm-answer-highlight">(.*?)</span></strong></p>',
        lambda m: _answer_card(m.group(1), _format_answer_value(m.group(2))),
        html,
        flags=re.S | re.I,
    )
    html = re.sub(
        r'<p><strong>(Step \d+:[^<]*)</strong>\s*\\?\(\s*<span class="cm-answer-box">(.*?)</span>\s*\\?\)\s*</p>',
        lambda m: _answer_card(
            "Answer",
            _format_answer_value(f'<span class="cm-answer-box">{m.group(2)}</span>'),
        ),
        html,
        flags=re.S | re.I,
    )
    html = re.sub(
        r'<p><strong>(Positive solution:)\s*</strong>\s*\\?\(\s*<span class="cm-answer-box">(.*?)</span>\s*\\?\)\s*</p>',
        lambda m: _answer_card(
            "Positive solution",
            _format_answer_value(f'<span class="cm-answer-box">{m.group(2)}</span>'),
        ),
        html,
        flags=re.S | re.I,
    )
    html = re.sub(r"\\?\(\s*(<span class=\"cm-answer-box\">.*?</span>)\s*\\?\)", r"\1", html, flags=re.S)
    html = re.sub(r"\\?\(\s*(<span class=\"cm-answer-highlight\">.*?</span>)\s*\\?\)", r"\1", html, flags=re.S)
    html = _sanitize_answer_boxes(html)
    return html


def _fix_aligned_prose(text: str) -> str:
    """Wrap English labels inside aligned math blocks with \\text{}."""

    def fix_inner(inner: str) -> str:
        inner = re.sub(
            r"(?<!\\text\{)([A-Z][A-Za-z]*(?:\s+[a-z]+)*:)(?=\s|\\quad|&|$)",
            r"\\text{\1}",
            inner,
        )
        inner = re.sub(r",\s+(and)\s+", r", \\text{\1} ", inner)
        inner = re.sub(
            r"\\Rightarrow\s+(This\s+[A-Za-z\s]+)",
            r"\\Rightarrow \\text{\1}",
            inner,
        )
        inner = re.sub(
            r"\\Rightarrow\s+(For\s+[A-Za-z\s]+)",
            r"\\Rightarrow \\text{\1}",
            inner,
        )
        return inner

    return re.sub(
        r"\\begin\{aligned\}(.*?)\\end\{aligned\}",
        lambda m: f"\\begin{{aligned}}{fix_inner(m.group(1))}\\end{{aligned}}",
        text,
        flags=re.S,
    )


def _enrich_slide_html(html: str, kind: str, title: str) -> str:
    html = _wrap_answer_choices(html)
    html = _wrap_concept_focus(html, kind)
    html = _wrap_summary_recap(html, title)
    if kind == "example" or re.search(r"<p><strong>Solution:\s*</strong></p>", html, re.I):
        html = _wrap_inline_solution(html)
    if kind in {"answer", "solution"}:
        html = _wrap_solution_steps(html)
    if kind in {"question", "practice"}:
        html = _wrap_question_challenge(html, title)
    html = _polish_answer_lines(html)
    return html


def _detect_slide_kind(title: str, plain: str, html: str) -> str:
    t = (title + " " + plain).lower()
    tl = title.lower().strip()
    if "cm-intro-canvas" in html:
        return "intro"
    if "cm-content-canvas" in html:
        return "content"
    if "thank you" in t or "cm-slide-closing" in html or "cm-closing-canvas" in html:
        return "closing"
    if tl.startswith("answer:"):
        return "answer"
    if tl.startswith("solution:") or (tl.startswith("solution") and "finding" in tl):
        return "solution"
    if re.search(r"\bquestion:\s", plain, re.I) and not re.search(
        r"step\s*1", plain, re.I
    ):
        if not tl.startswith("solution"):
            return "question"
    if "question" in tl and not tl.startswith("solution"):
        return "question"
    if tl.startswith("example"):
        return "example"
    if "word problem" in tl or "problem statement" in t[:220]:
        if not tl.startswith("solution") and "step 1" not in t:
            return "practice"
    if tl.startswith("solution") or ": solution" in tl:
        return "solution"
    if "introduction" in t or "overview" in t or "definition" in t:
        return "concept"
    if "summary" in tl:
        return "lesson"
    if "table:" in tl or "cm-mcq-grid" in html or "answer choices" in t:
        return "question"
    if len(plain) < 40 and not re.search(r"\\[\(\[]", plain):
        return "section"
    return "lesson"


def _link_question_answer_slides(slides: list[dict[str, Any]]) -> None:
    answer_kinds = {"answer", "solution"}
    question_kinds = {"question", "practice", "example"}
    for i, slide in enumerate(slides):
        kind = slide.get("kind", "lesson")
        if kind not in question_kinds:
            continue
        if slide.get("inline_solution"):
            slide["interactive"] = True
            continue
        for j in range(i + 1, len(slides)):
            nxt = slides[j]
            nk = nxt.get("kind", "lesson")
            nt = nxt.get("title", "").lower()
            if nk in answer_kinds or nt.startswith("answer") or nt.startswith("solution"):
                slide["answer_index"] = nxt["index"]
                nxt["question_index"] = slide["index"]
                slide["interactive"] = True
                break


def _slide_group(kind: str) -> str:
    if kind in {"intro", "content", "section"}:
        return "divider"
    if kind in {"concept", "lesson", "example"}:
        return "learn"
    if kind in {"question", "practice", "answer", "solution"}:
        return "practice"
    if kind == "closing":
        return "review"
    return "learn"


def _study_hint_for(kind: str, title: str, plain: str) -> str:
    t = (title + " " + plain).lower()
    if kind == "intro":
        return "This is your lesson overview — tap a section chip or press Next for the full outline."
    if kind == "content":
        return "Use this outline to jump straight to any section — great for review or picking up where you left off."
    if kind == "concept":
        return "Focus on definitions and vocabulary — SAT questions often test whether you recognize the form of an equation."
    if kind == "example":
        return "Watch the method, then close the solution and redo the problem from scratch."
    if kind == "question" or kind == "practice":
        if "no solution" in t:
            return "No-solution means parallel lines: same slope (coefficient of x), different constants."
        if "infinitely many" in t or "infinitely many solutions" in t:
            return "Infinite solutions mean the two sides are the same line — all coefficients must match."
        if "word problem" in t or "bushel" in t or "property" in t or "popcorn" in t:
            return "Word problem flow: define a variable → write the equation → solve → check the units."
        if "absolute value" in t:
            return "Absolute value equations often split into two cases — remember to check both branches."
        if "which of the following" in t or "answer choices" in t:
            return "For multiple choice, eliminate obviously wrong options before doing full algebra."
        return "Write your full work before opening the solution — partial credit thinking helps on test day."
    if kind in {"answer", "solution"}:
        return "Walk through each step and ask: why is this move valid? Could you explain it to a friend?"
    if kind == "lesson" and "summary" in t:
        return "Quick recap — make sure you can recall each bullet without looking."
    if kind == "section":
        return ""
    return "Take notes on anything that feels new — you'll reuse these ideas in practice sets."


def _strategy_hint_for(title: str, plain: str) -> str:
    t = (title + " " + plain).lower()
    if "no solution" in t:
        return "Set the coefficients of x equal, then verify the constants produce a contradiction."
    if "infinitely many" in t:
        return "Match coefficients of x and constants on both sides — they must be identical."
    if "word problem" in t or "bushel" in t:
        return "Find the rate of change first (Δy/Δx), then build the linear model."
    if "discount" in t or "property" in t:
        return "Translate each percentage change into a multiplier, then chain the operations."
    if "popcorn" in t:
        return "Express total amount, apply the percent consumed, then divide equally."
    if "absolute value" in t:
        return "Isolate |expression| first, then split into two linear equations."
    if "2(kx" in plain or "kx - n" in t:
        return "Expand both sides, then compare the coefficients of x for special solution types."
    return "Identify what type of linear equation this is (one solution, none, or infinite) before solving."


def _wrap_summary_recap(html: str, title: str) -> str:
    if "summary" not in title.lower():
        return html
    banner = (
        '<div class="cm-recap-banner">'
        '<span class="cm-recap-icon" aria-hidden="true">◆</span>'
        '<div class="cm-recap-copy">'
        "<strong>Lesson recap</strong>"
        "<span>Review these ideas before moving to practice tests.</span>"
        "</div>"
        "</div>"
    )
    return banner + html


def _wrap_concept_focus(html: str, kind: str) -> str:
    if kind != "concept":
        return html
    if "cm-learn-focus" in html:
        return html
    focus = (
        '<div class="cm-learn-focus">'
        '<span class="cm-learn-focus-tag">Core concept</span>'
        "<p>Understand this definition — every example and practice problem in this lesson builds on it.</p>"
        "</div>"
    )
    return focus + html


def _annotate_slides(slides: list[dict[str, Any]]) -> None:
    current_section = "Introduction"
    for slide in slides:
        kind = slide.get("kind", "lesson")
        if kind == "section":
            title = slide.get("title", "")
            current_section = re.sub(r"^up next\s*", "", title, flags=re.I).strip() or title
        slide["group"] = _slide_group(kind)
        slide["section"] = current_section
        plain = re.sub(r"<[^>]+>", " ", slide.get("html", ""))
        slide["study_tip"] = _study_hint_for(kind, slide.get("title", ""), plain)
        if kind in {"question", "practice", "example"}:
            slide["strategy_hint"] = _strategy_hint_for(slide.get("title", ""), plain)


def _build_lesson_path(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    path: list[dict[str, Any]] = []
    for slide in slides:
        if slide.get("kind") != "section":
            continue
        title = re.sub(r"^up next\s*", "", slide.get("title", ""), flags=re.I).strip()
        path.append({"index": slide["index"], "title": title or slide.get("title", "")})
    return path


def _enrich_section_slides(slides: list[dict[str, Any]], lesson_path: list[dict[str, Any]]) -> None:
    """Add premium section numbers to section divider canvases."""
    index_to_num = {int(item["index"]): i for i, item in enumerate(lesson_path, 1)}
    for slide in slides:
        if slide.get("kind") != "section":
            continue
        num = index_to_num.get(int(slide.get("index") or 0))
        if not num:
            continue
        html = slide.get("html") or ""
        if "cm-section-num" in html:
            continue
        slide["html"] = html.replace(
            '<div class="cm-section-divider">',
            f'<div class="cm-section-divider"><span class="cm-section-num">{num:02d}</span>',
            1,
        )


def _count_interactive_stats(slides: list[dict[str, Any]]) -> dict[str, int]:
    questions = sum(
        1
        for s in slides
        if s.get("interactive") or s.get("kind") in {"question", "practice", "example"}
    )
    learn = sum(1 for s in slides if s.get("group") == "learn" and s.get("kind") != "section")
    return {
        "interactive_count": questions,
        "learn_count": learn,
        "practice_slide_count": sum(1 for s in slides if s.get("group") == "practice"),
    }


def _clean_frame_body(body: str) -> str:
    if re.search(r"thank you", body, re.I):
        return _build_closing_html(body)

    if re.search(r"\\begin\{tikzpicture\}", body) and not re.search(
        r"\\begin\{(?:tabular|align|itemize|enumerate)\}", body
    ):
        section_m = re.search(r"\\section\*?\{([^{}]+)\}", body)
        if section_m:
            return (
                f'<div class="cm-section-divider">'
                f'<span class="cm-section-kicker">Up next</span>'
                f'<h3 class="cm-section-title">{section_m.group(1).strip()}</h3>'
                f"</div>"
            )
        return ""

    body = _remove_environment(body, "tikzpicture")
    body = _remove_environment(body, "columns")
    body = _replace_course_material_figures(body)
    body = _unwrap_environment(body, "center")
    body = _remove_environment(body, "flushright")
    body = _remove_environment(body, "flushleft")
    body = _strip_beamer_layout_commands(body)
    body = _convert_semantic_markup(body)
    body = _unwrap_inline_markup(body)
    body = latex_array_and_tabular_to_html(body)
    body = _convert_beamer_enumerate(body)
    body = _convert_align_blocks_for_mathjax(body)
    body = _fix_aligned_prose(body)
    body = _convert_latex_lists(body)
    body = _convert_dash_bullets(body)
    body = _clean_beamer_noise(body)
    body = _normalize_display_math(body)
    body = clean_math(body)
    body = _repair_math_delimiters(body)
    body = _fix_html_in_display_math(body)
    body = _scrub_latex_remnants(body)
    body = _convert_markdown_bold(body)
    body = _format_beamer_html(body)
    body = re.sub(r"<p>\s*</p>", "", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def _split_frames(tex: str) -> list[tuple[Optional[str], str]]:
    frames: list[tuple[Optional[str], str]] = []
    marker = r"\begin{frame}"
    i = 0
    while True:
        idx = tex.find(marker, i)
        if idx == -1:
            break
        j = idx + len(marker)
        while j < len(tex) and tex[j].isspace():
            j += 1
        if j < len(tex) and tex[j] == "[":
            depth = 1
            j += 1
            while j < len(tex) and depth:
                if tex[j] == "[":
                    depth += 1
                elif tex[j] == "]":
                    depth -= 1
                j += 1
        while j < len(tex) and tex[j].isspace():
            j += 1
        title: Optional[str] = None
        if j < len(tex) and tex[j] == "{":
            title, j = _extract_braced_content(tex, j)
        end_marker = r"\end{frame}"
        end_idx = tex.find(end_marker, j)
        if end_idx == -1:
            break
        frames.append((title, tex[j:end_idx]))
        i = end_idx + len(end_marker)
    return frames


def _plain_text_from_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\\[a-zA-Z]+\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_slide_title(title: str) -> str:
    title = _unwrap_inline_markup(title)
    title = re.sub(r"\\\(\s*([^\\]*?)\\?\s*\)", r"\1", title)
    title = re.sub(r"\\[a-zA-Z]+\b", " ", title)
    title = re.sub(r"[{}]", "", title)
    return re.sub(r"\s+", " ", title).strip()


def parse_beamer_file(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        tex = f.read()

    meta = _extract_document_meta(tex)
    deck_title = meta.get("title", "")
    body = _strip_beamer_preamble(tex)
    slides: list[dict[str, Any]] = []

    for ftitle, fbody in _split_frames(body):
        html = _clean_frame_body(fbody)
        if not html:
            continue
        plain = _plain_text_from_html(html)
        title = _clean_slide_title(ftitle or "")
        if not title and plain:
            title = plain[:72] + ("…" if len(plain) > 72 else "")
        if plain.lower() in {"novel prep", "excellence in sat prep"}:
            continue
        if len(plain) < 3 and not title:
            continue
        if not title:
            title = f"Slide {len(slides) + 1}"
        kind = _detect_slide_kind(title, plain, html)
        if kind == "closing":
            title = "Thank You"
        html = _enrich_slide_html(html, kind, title)
        slide_data: dict[str, Any] = {
            "index": len(slides) + 1,
            "title": title,
            "html": html,
            "kind": kind,
        }
        if "cm-solution-panel" in html:
            slide_data["inline_solution"] = True
            slide_data["interactive"] = True
        if "cm-mcq-interactive" in html:
            slide_data["interactive"] = True
        slides.append(slide_data)

    section_titles = [
        re.sub(r"^up next\s*", "", s.get("title", ""), flags=re.I).strip()
        for s in slides
        if s.get("kind") == "section"
    ]
    intro_slide: dict[str, Any] = {
        "index": 1,
        "title": deck_title or "Lesson overview",
        "html": "",
        "kind": "intro",
    }
    content_slide: dict[str, Any] = {
        "index": 2,
        "title": "Lesson outline",
        "html": "",
        "kind": "content",
    }
    for i, slide in enumerate(slides):
        slide["index"] = i + 3
    slides = [intro_slide, content_slide] + slides

    _link_question_answer_slides(slides)
    _annotate_slides(slides)
    lesson_path = _build_lesson_path(slides)
    _enrich_section_slides(slides, lesson_path)
    slides[0]["html"] = _build_intro_html(meta, lesson_path)
    slides[1]["html"] = _build_contents_html(
        meta,
        deck_title or "",
        lesson_path,
        len(slides),
    )

    if slides and slides[-1].get("kind") == "closing":
        closing_body = ""
        for ftitle, fbody in reversed(_split_frames(body)):
            if re.search(r"thank you", fbody, re.I):
                closing_body = fbody
                break
        slides[-1]["html"] = _build_closing_html(
            closing_body,
            deck_title=deck_title,
            slide_count=len(slides),
            section_titles=section_titles,
        )
        slides[-1]["html"] = _enrich_slide_html(
            slides[-1]["html"], slides[-1]["kind"], slides[-1]["title"]
        )

    if not deck_title and slides:
        deck_title = slides[0]["title"]

    stats = _count_interactive_stats(slides)
    return {
        "title": deck_title or "SAT Course Material",
        "slides": slides,
        "slide_count": len(slides),
        "lesson_path": lesson_path,
        **stats,
    }
