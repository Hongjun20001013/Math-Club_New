"""Parse Beamer slide decks (.tex) into rich HTML slides for the course materials viewer."""
from __future__ import annotations

import json
import os
import html as html_module
import re
from typing import Any, Optional

from latex_parser import (
    _convert_latex_lists,
    _extract_braced_content,
    _mathjax_safe_lt_in_tex_math,
    clean_math,
    latex_array_and_tabular_to_html,
    strip_document_noise,
)
from tikz_svg import replace_tikz_with_svg_html


def _strip_beamer_preamble(tex: str) -> str:
    idx = tex.find(r"\begin{document}")
    if idx >= 0:
        tex = tex[idx + len(r"\begin{document}") :]
    end = tex.rfind(r"\end{document}")
    if end >= 0:
        tex = tex[:end]
    return tex


def _normalize_tex_text_escapes(text: str) -> str:
    """Turn LaTeX text-mode escapes into plain characters for UI strings."""
    if not text:
        return text
    text = text.replace(r"\&", "&")
    text = text.replace(r"\$", "$")
    text = text.replace(r"\%", "%")
    text = text.replace(r"\_", "_")
    return text


def _extract_beamer_field(tex: str, command: str) -> str:
    m = re.search(
        r"\\" + command + r"(?:\[[^\]]*\])?\{((?:[^{}]|\{[^{}]*\})*)\}",
        tex,
        re.S,
    )
    if not m:
        return ""
    raw = _normalize_tex_text_escapes(_unwrap_inline_markup(m.group(1)))
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


def _flatten_columns(text: str) -> str:
    """Unwrap beamer columns/column blocks but keep all inner content."""
    out = text
    col_inner = re.compile(
        r"\\begin\{column\}\{[^}]*\}(.*?)\\end\{column\}",
        re.S,
    )
    while col_inner.search(out):
        out = col_inner.sub(r"\n\1\n", out)
    return _unwrap_environment(out, "columns")


def _env_begin_pattern(env: str) -> str:
    """Match \\begin{env} with optional [...] arguments."""
    return rf"\\begin\{{{re.escape(env)}\}}(?:\[[^\]]*\])?"


def _find_env_begin(text: str, env: str, start: int = 0) -> tuple[int, int] | None:
    """Return (begin_idx, content_start) for \\begin{env} or \\begin{env}[...]."""
    pat = re.compile(_env_begin_pattern(env))
    m = pat.search(text, start)
    if not m:
        return None
    return m.start(), m.end()


def _unwrap_environment(text: str, env: str) -> str:
    """Replace \\begin{env}…\\end{env} with its inner content (keep figures/text)."""
    out = text
    end = rf"\end{{{env}}}"
    while True:
        found = _find_env_begin(out, env)
        if not found:
            break
        idx, pos = found
        end_idx = out.find(end, pos)
        if end_idx == -1:
            out = out[:idx] + out[pos:]
            continue
        inner = out[pos:end_idx].strip()
        out = out[:idx] + inner + out[end_idx + len(end) :]
    return out


def _remove_environment(text: str, env: str) -> str:
    out = text
    end = rf"\end{{{env}}}"
    while True:
        found = _find_env_begin(out, env)
        if not found:
            break
        idx, pos = found
        end_idx = out.find(end, pos)
        if end_idx == -1:
            out = out[:idx] + out[pos:]
            continue
        out = out[:idx] + out[end_idx + len(end) :]
    return out


def _unwrap_beamer_block_environment(text: str) -> str:
    """Unwrap beamer block/alertblock/exampleblock, preserving the block title."""
    out = text
    for env in ("block", "alertblock", "exampleblock"):
        marker = rf"\begin{{{env}}}"
        end = rf"\end{{{env}}}"
        while True:
            idx = out.find(marker)
            if idx == -1:
                break
            pos = idx + len(marker)
            while pos < len(out) and out[pos].isspace():
                pos += 1
            title = ""
            if pos < len(out) and out[pos] == "{":
                parsed = _extract_braced_content(out, pos)
                if parsed[0] is not None:
                    title, pos = parsed
            end_idx = out.find(end, pos)
            if end_idx == -1:
                out = out[:idx] + out[pos:]
                continue
            inner = out[pos:end_idx].strip()
            replacement = (rf"\textbf{{{title}}}" + "\n\n" if title.strip() else "") + inner
            out = out[:idx] + replacement + out[end_idx + len(end) :]
    return out


def _includegraphics_width_style(options: str) -> str:
    """Map LaTeX includegraphics width options to inline CSS (hard-question scale)."""
    if not options:
        return ""
    m = re.search(r"width\s*=\s*([\d.]+)\s*\\(?:linewidth|textwidth|columnwidth)", options)
    if not m:
        return ""
    frac = float(m.group(1))
    # 0.4 linewidth ≈ 280px in hard-question figures.
    px = max(160, min(420, int(round(frac / 0.4 * 280))))
    height = int(round(px * 0.72))
    return f' style="max-width: {px}px; max-height: {height}px; object-fit: contain;"'


def _resolve_course_material_figure(fname: str) -> tuple[str, str] | None:
    """Return (static_url_prefix, filename) for a Beamer figure if it exists on disk."""
    safe = re.sub(r"[^a-zA-Z0-9._-]", "", fname.strip())
    if not safe:
        return None
    base, ext = os.path.splitext(safe)
    root = os.path.dirname(__file__)
    search_dirs = (
        ("hard", os.path.join(root, "static", "hard")),
        ("unit4", os.path.join(root, "static", "unit4")),
        ("course_materials", os.path.join(root, "static", "course_materials")),
    )
    candidates: list[str] = []
    if ext:
        candidates.append(safe)
    else:
        candidates.extend([base + e for e in (".svg", ".png", ".jpg", ".jpeg")])
    for alt_ext in (".svg", ".png", ".jpg", ".jpeg"):
        alt = base + alt_ext
        if alt not in candidates:
            candidates.append(alt)
    for prefix, static_dir in search_dirs:
        for candidate in candidates:
            if os.path.isfile(os.path.join(static_dir, candidate)):
                return prefix, candidate
    return None


def _hard_figure_style(fname: str) -> str:
    """Per-asset sizing tuned for hard-question diagrams (matches practice bank)."""
    styles = {
        "hard_2_f1.png": "max-width: 300px; max-height: 220px; object-fit: contain;",
        "hard_2_f2.jpg": "max-width: 320px; max-height: 240px; object-fit: contain;",
        "hard_3_f9.png": "max-width: 260px; max-height: 190px; object-fit: contain;",
        "hard_7_f4.png": "max-width: 280px; max-height: 200px; object-fit: contain;",
        "hard_8_f5.png": "max-width: 300px; max-height: 190px; object-fit: contain;",
        "hard_9_f7.png": "max-width: 300px; max-height: 200px; object-fit: contain;",
        "hard_10_f8.png": "max-width: 280px; max-height: 200px; object-fit: contain;",
        "hard_14_f12.png": "max-width: 300px; max-height: 220px; object-fit: contain;",
    }
    return styles.get(fname, "")


def _replace_course_material_figures(text: str) -> str:
    """Turn \\includegraphics{file} into slide figures under /static/."""

    def repl(m: re.Match[str]) -> str:
        options = (m.group(1) or "").strip()
        fname = m.group(2).strip()
        resolved = _resolve_course_material_figure(fname)
        if not resolved:
            return ""
        prefix, safe = resolved
        hard_cls = " stem-figure-img--hard" if prefix == "hard" else ""
        hard_style = _hard_figure_style(safe)
        if hard_style:
            style_attr = f' style="{hard_style}"'
        else:
            style_attr = _includegraphics_width_style(options)
        return (
            f'<div class="cm-slide-figure"><img class="stem-figure-img cm-slide-figure-img{hard_cls}" '
            f'src="/static/{prefix}/{safe}" alt="" loading="lazy"{style_attr} /></div>'
        )

    return re.sub(
        r"\\includegraphics(?:\[([^\]]*)\])?\{([^}]+)\}",
        repl,
        text,
    )


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
    text = _replace_braced_command(
        text,
        "fbox",
        lambda c: f'<span class="cm-answer-box">{_apply_inline_markup(c)}</span>',
    )
    return _unwrap_inline_markup(text)


def _convert_semantic_markup(text: str) -> str:
    text = _replace_textcolor_commands(text)
    text = _apply_inline_markup(text)
    return text


def _scrub_latex_remnants(text: str) -> str:
    """Remove leftover publisher color macros and broken command fragments."""
    text = text.replace(r"\Rightarrow", "⇒")
    text = text.replace(r"\Longrightarrow", "⇒")
    text = re.sub(r"\\quad\b", " ", text)
    text = re.sub(r"\\,\s*", " ", text)
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
        r"<p>\\(?:tiny|scriptsize|small|footnotesize|renewcommand|setlength)[^<]*</p>\s*",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\\(?:textrm|textsf|textit|textbf|textit|emph|bfseries|itshape)\b\s*",
        "",
        text,
    )
    text = re.sub(r"\{,\}", ",", text)
    return text


def _strip_beamer_layout_commands(text: str) -> str:
    text = re.sub(
        r"\\(?:tiny|scriptsize|small|footnotesize|normalsize|large|Large|LARGE|Huge|huge)\b\s*",
        "",
        text,
    )
    text = re.sub(r"\\renewcommand\{[^}]+\}\{[^}]*\}\s*", "", text)
    text = re.sub(r"\\setlength\{[^}]+\}\{[^}]*\}\s*", "", text)
    text = re.sub(r"\\begin\{minipage\}\{[^}]*\}\s*", "", text)
    text = re.sub(r"\\end\{minipage\}\s*", "", text)
    text = re.sub(r"\\centering\b\s*", "", text)
    text = re.sub(r"\\(?:raggedright|raggedleft)\b\s*", "", text)
    text = re.sub(r"\\(?:medskip|bigskip|smallskip|vfill)\b\s*", "\n", text)
    text = re.sub(r"\\hfill\b\s*", " %%HFILL%% ", text)
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


def _enumerate_uses_auto_labels(enum_opt: str) -> bool:
    opt = (enum_opt or "").strip()
    if re.match(r"^[A-Da-d]\.?\s*$", opt):
        return True
    if re.search(r"\\Alph\*|\\alph\*", opt):
        return True
    return bool(re.match(r"^\([A-Da-d]\)$", opt))


def _convert_choices_environment(text: str) -> str:
    """Convert ``\\begin{choices}`` / ``\\choice`` blocks into A–D enumerate for MCQ UI."""

    def repl(m: re.Match[str]) -> str:
        body = m.group(1).strip()
        parts = re.split(r"\\choice\s*", body)
        items = [p.strip() for p in parts if p.strip()]
        if not items:
            return m.group(0)
        return (
            r"\begin{enumerate}[label=(\Alph*)]"
            + "\n"
            + "\n".join(rf"\item {item}" for item in items)
            + "\n"
            + r"\end{enumerate}"
        )

    return re.sub(
        r"\\begin\{choices\}(.*?)\\end\{choices\}",
        repl,
        text,
        flags=re.S,
    )


def _convert_beamer_enumerate(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        enum_opt = (m.group(1) or "").strip()
        body = m.group(2)
        parts = re.split(r"\\item\s*", body)
        choices: list[tuple[str, str]] = []
        auto_letters = (
            list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
            if _enumerate_uses_auto_labels(enum_opt)
            else []
        )
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
            elif auto_letters and len(choices) < len(auto_letters):
                label = auto_letters[len(choices)]
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
        r"\\begin\{enumerate\}(?:\[([^\]]*)\])?(.*?)\\end\{enumerate\}",
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


def _shield_vaulted_blocks(text: str, pattern: str, vault: list[str]) -> str:
    pat = re.compile(pattern, re.S)
    while True:
        m = pat.search(text)
        if not m:
            break
        vault.append(m.group(0))
        text = pat.sub(f"<<<MATHVAULT_{len(vault) - 1}>>>", text, count=1)
    return text


def _unshield_vaulted_blocks(text: str, vault: list[str]) -> str:
    for i, chunk in enumerate(vault):
        text = text.replace(f"<<<MATHVAULT_{i}>>>", chunk)
    return text


def _repair_math_delimiters(text: str) -> str:
    """Fix inline/display delimiters broken by legacy cleanup passes."""
    # Fix `\(... )` typos where the closing delimiter lost its backslash.
    out: list[str] = []
    i = 0
    open_d, close_d = r"\(", r"\)"
    while True:
        idx = text.find(open_d, i)
        if idx == -1:
            out.append(text[i:])
            break
        out.append(text[i:idx])
        end = text.find(close_d, idx + 2)
        if end == -1:
            bare = idx + 2
            while bare < len(text):
                if text[bare] == ")" and (bare + 1 >= len(text) or text[bare + 1] != ")"):
                    inner = text[idx + 2 : bare].strip()
                    out.append(f"\\({inner}\\)")
                    i = bare + 1
                    break
                bare += 1
            else:
                out.append(text[idx:])
                break
            continue
        out.append(text[idx : end + 2])
        i = end + 2
    text = "".join(out)
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

    def fix_inline_inner(inner: str) -> str:
        if "<" not in inner:
            return r"\(" + inner + r"\)"
        latex, html = _split_latex_and_html(inner)
        parts: list[str] = []
        if latex:
            parts.append(r"\(" + latex + r"\)")
        if html:
            parts.append(html)
        return " ".join(parts)

    out: list[str] = []
    i = 0
    open_d, close_d = r"\(", r"\)"
    olen, clen = len(open_d), len(close_d)
    while i < len(text):
        idx = text.find(open_d, i)
        if idx == -1:
            out.append(text[i:])
            break
        out.append(text[i:idx])
        end = text.find(close_d, idx + olen)
        if end == -1:
            out.append(text[idx:])
            break
        inner = text[idx + olen : end]
        out.append(fix_inline_inner(inner))
        i = end + clen
    return "".join(out)


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
    html_vault: list[str] = []

    def _vault_html(m: re.Match[str]) -> str:
        html_vault.append(m.group(0))
        return f"<<<HTMLVAULT_{len(html_vault) - 1}>>>"

    text = re.sub(
        r'<div class="cm-slide-figure">.*?</div>|<div class="stem-figure-wrap"[^>]*>.*?</div>',
        _vault_html,
        text,
        flags=re.S,
    )
    math_vault: list[str] = []

    def _vault_math(m: re.Match[str]) -> str:
        math_vault.append(m.group(0))
        return f"<<<MATHVAULT_{len(math_vault) - 1}>>>"

    text = re.sub(r"\\\[.*?\\\]", _vault_math, text, flags=re.S)
    text = re.sub(r"\\\(.*?\\\)", _vault_math, text, flags=re.S)
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
    for idx, block in enumerate(math_vault):
        text = text.replace(f"<<<MATHVAULT_{idx}>>>", block)
    for idx, block in enumerate(html_vault):
        text = text.replace(f"<<<HTMLVAULT_{idx}>>>", block)
    return strip_document_noise(text)


def _convert_markdown_bold(text: str) -> str:
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)


def _format_plain_paragraphs(text: str) -> str:
    lines = [line.strip() for line in text.split("\n")]
    html_parts: list[str] = []
    i = 0
    while i < len(lines):
        line = re.sub(r"\\+\s*$", "", lines[i]).strip()
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
        r'|<div class="cm-closing-canvas">.*?</div>'
        r'|<div class="cm-slide-figure">.*?</div>'
        r'|<div class="stem-figure-wrap"[^>]*>.*?</div>)'
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


def _normalize_mcq_marker(marker: str) -> str | None:
    clean = re.sub(r"<[^>]+>", "", marker).strip().rstrip(".:").strip()
    clean = clean.strip("()")
    m = re.match(r"^([A-D])", clean)
    return m.group(1) if m else None


def _clean_mcq_body(body: str) -> str:
    body = re.sub(r"\\quad\s*", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    return body


def _looks_like_plain_mcq_items(items: list[str]) -> bool:
    """True when four list items look like SAT answer values, not prose bullets."""
    cleaned = [re.sub(r"<[^>]+>", "", item).strip() for item in items]
    cleaned = [item for item in cleaned if item]
    if len(cleaned) != 4:
        return False
    if all(re.match(r"^[\d,.\s/+-]+$", item) for item in cleaned):
        return True
    if any(re.search(r"\b(the|and|your|always|check|use|write|cancel|need)\b", item, re.I) for item in cleaned):
        return False
    return all(len(item) <= 24 and re.search(r"\d", item) for item in cleaned)


def _valid_mcq_choice_set(choices: list[tuple[str, str]]) -> bool:
    if len(choices) not in {3, 4}:
        return False
    letters = [letter for letter, _ in choices]
    if not all(letter in {"A", "B", "C", "D"} for letter in letters):
        return False
    return letters == list("ABCD")[: len(letters)]


def _extract_mcq_choices_from_list(list_html: str) -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = []
    for item in re.finditer(
        r'<li class="stem-li-labeled">\s*<span class="stem-li-marker">(.*?)</span>\s*'
        r'<span class="stem-li-body">(.*?)</span>\s*</li>',
        list_html,
        flags=re.S,
    ):
        letter = _normalize_mcq_marker(item.group(1))
        if letter:
            choices.append((letter, _clean_mcq_body(item.group(2))))
    if not choices:
        for item in re.finditer(
            r"<li><strong>([A-D]):\s*</strong>\s*(.*?)</li>",
            list_html,
            flags=re.S,
        ):
            choices.append((item.group(1), _clean_mcq_body(item.group(2))))
    if not choices:
        plain_items = [
            re.sub(r"<[^>]+>", "", body).strip()
            for body in re.findall(r"<li>(.*?)</li>", list_html, flags=re.S)
        ]
        plain_items = [body for body in plain_items if body]
        if len(plain_items) == 4 and _looks_like_plain_mcq_items(plain_items):
            for letter, body in zip("ABCD", plain_items, strict=True):
                choices.append((letter, _clean_mcq_body(body)))
    if not choices:
        for item in re.finditer(r"<li>([A-D])\.\s*(.*?)</li>", list_html, flags=re.S):
            choices.append((item.group(1), _clean_mcq_body(item.group(2))))
    return choices


def _extract_mcq_choices_from_ul(ul_html: str) -> list[tuple[str, str]]:
    return _extract_mcq_choices_from_list(ul_html)


def _extract_mcq_choices_from_table(table_html: str) -> list[tuple[str, str]]:
    """Parse A/B/C/D rows from stem-table HTML (array MCQ converted to table)."""
    choices: list[tuple[str, str]] = []
    for cell_a, cell_b in re.findall(
        r"<t(?:h|d)[^>]*>(.*?)</t(?:h|d)>\s*"
        r"<t(?:h|d)[^>]*>(.*?)</t(?:h|d)>",
        table_html,
        flags=re.S | re.I,
    ):
        plain_a = re.sub(r"<[^>]+>", "", cell_a).strip()
        letter_m = re.match(r"^([A-D])\.?$", plain_a, flags=re.I)
        if not letter_m:
            continue
        letter = letter_m.group(1).upper()
        body = _clean_mcq_body(cell_b)
        if _needs_math_delimiters(body) and not re.search(r"\\\(|\\\[", body):
            body = f"\\({body}\\)"
        choices.append((letter, body))
    return choices


def _build_mcq_interactive(
    choices: list[tuple[str, str]], *, correct: str | None = None
) -> str:
    correct_attr = f' data-cm-correct="{correct}"' if correct else ""
    buttons = []
    for letter, body in choices:
        buttons.append(
            f'<button type="button" class="cm-mcq-choice" data-choice="{letter}">'
            f'<span class="cm-mcq-letter">{letter}</span>'
            f'<span class="cm-mcq-text">{body}</span>'
            "</button>"
        )
    return (
        f'<div class="cm-mcq-interactive" data-cm-mcq{correct_attr}>'
        '<p class="cm-mcq-prompt">Choose your answer</p>'
        '<div class="cm-mcq-grid">'
        + "".join(buttons)
        + "</div>"
        '<div class="cm-mcq-actions">'
        '<button type="button" class="cm-mcq-check" data-cm-check-mcq disabled>Check answer</button>'
        '<button type="button" class="cm-mcq-skip" data-cm-go-answer>View worked solution →</button>'
        "</div>"
        "</div>"
    )


def _wrap_answer_choices(html: str) -> str:
    """Turn A–D answer choice lists into interactive pickers."""
    if "cm-mcq-interactive" in html:
        return html

    m = re.search(
        r"(<p><strong>(?:Answer Choices|Options|Choices):\s*</strong></p>\s*)"
        r'(<div class="cm-mcq-grid">((?:\s*<div class="cm-mcq-choice">.*?</div>)+)\s*</div>)',
        html,
        flags=re.I | re.S,
    )
    if m:
        choices: list[tuple[str, str]] = []
        for item in re.finditer(
            r'<div class="cm-mcq-choice"><span class="cm-mcq-letter">([A-D])</span>'
            r'<span class="cm-mcq-text">(.*?)</span></div>',
            m.group(3),
            flags=re.S,
        ):
            choices.append((item.group(1), _clean_mcq_body(item.group(2))))
        if len(choices) >= 2:
            return html[: m.start()] + m.group(1) + _build_mcq_interactive(choices) + html[m.end() :]

    m = re.search(
        r"(<p><strong>(?:Answer Choices|Options|Choices):\s*</strong></p>\s*)"
        r'(<(?:ul|ol) class="(?:stem-itemize|stem-enumerate cm-beamer-list)">(.*?)</(?:ul|ol)>)',
        html,
        flags=re.I | re.S,
    )
    if m:
        choices = _extract_mcq_choices_from_list(m.group(2))
        if len(choices) >= 2:
            return html[: m.start()] + m.group(1) + _build_mcq_interactive(choices) + html[m.end() :]

    return html


def _wrap_standalone_mcq_list(html: str) -> str:
    """Wrap trailing A–D itemize lists (Practice section style) as MCQ grids."""
    if "cm-mcq-interactive" in html:
        return html
    grid_matches = list(
        re.finditer(
            r'(<div class="cm-mcq-grid">((?:\s*<div class="cm-mcq-choice">.*?</div>)+)\s*</div>)',
            html,
            flags=re.S,
        )
    )
    if grid_matches:
        m = grid_matches[-1]
        choices: list[tuple[str, str]] = []
        for item in re.finditer(
            r'<div class="cm-mcq-choice"><span class="cm-mcq-letter">([A-D])</span>'
            r'<span class="cm-mcq-text">(.*?)</span></div>',
            m.group(2),
            flags=re.S,
        ):
            choices.append((item.group(1), _clean_mcq_body(item.group(2))))
        if len(choices) == 4:
            return html[: m.start()] + _build_mcq_interactive(choices) + html[m.end() :]
    matches = list(
        re.finditer(
            r'(<(?:ul|ol) class="(?:stem-itemize|stem-enumerate cm-beamer-list)">(.*?)</(?:ul|ol)>)',
            html,
            flags=re.S,
        )
    )
    if not matches:
        return html
    m = matches[-1]
    choices = _extract_mcq_choices_from_list(m.group(2))
    if not _valid_mcq_choice_set(choices):
        return html
    return html[: m.start()] + _build_mcq_interactive(choices) + html[m.end() :]


def _wrap_table_mcq_list(html: str) -> str:
    """Turn stem-table A/B/C/D rows into clickable MCQs."""
    if "cm-mcq-interactive" in html:
        return html

    def repl(m: re.Match[str]) -> str:
        choices = _extract_mcq_choices_from_table(m.group(0))
        if not _valid_mcq_choice_set(choices):
            return m.group(0)
        return _build_mcq_interactive(choices)

    return re.sub(
        r'<div class="stem-table-wrap">\s*<table class="stem-table">.*?</table>\s*</div>',
        repl,
        html,
        flags=re.S,
    )


def _wrap_display_array_mcq_list(html: str) -> str:
    """Turn display-math array answer choices into clickable MCQs."""
    if "cm-mcq-interactive" in html:
        return html

    def repl(m: re.Match[str]) -> str:
        body = m.group(1)
        rows = [row.strip() for row in re.split(r"\\\\", body) if row.strip()]
        choices: list[tuple[str, str]] = []
        for row in rows:
            row = re.sub(r"\\textbf\{([^{}]*)\}", r"\1", row).strip()
            item = re.match(r"^\{?\s*([A-D])\.?\s*\}?\s*&\s*(.*?)\s*$", row, flags=re.S)
            if not item:
                return m.group(0)
            letter = item.group(1)
            choice = _clean_mcq_body(item.group(2))
            if _needs_math_delimiters(choice) and not re.search(r"\\\(|\\\[", choice):
                choice = f"\\({choice}\\)"
            choices.append((letter, choice))
        if len(choices) != 4 or [letter for letter, _ in choices] != list("ABCD"):
            return m.group(0)
        return _build_mcq_interactive(choices)

    return re.sub(
        r'<div class="stem-math-block cm-math-block">\s*\\\[\s*'
        r"\\begin\{array\}\{[^{}]*\}(.*?)\\end\{array\}\s*\\\]\s*</div>",
        repl,
        html,
        flags=re.S,
    )


def _wrap_question_challenge(html: str, title: str) -> str:
    """Question slides use cm-question-workspace (stem + interact) — no legacy banner."""
    if "cm-mcq-interactive" in html or "cm-grid-in-interactive" in html or "cm-question-workspace" in html:
        return html
    return html


def _extract_div_block(html: str, class_substr: str) -> tuple[str, str]:
    if class_substr == "cm-grid-in-interactive":
        pat = re.compile(
            r'(<div class="cm-grid-in-interactive"[\s\S]*?'
            r'<p class="cm-grid-in-feedback"[^>]*></p>\s*</div>)',
            re.S,
        )
    elif class_substr == "cm-mcq-interactive":
        pat = re.compile(
            r'(<div class="cm-mcq-interactive"[\s\S]*?'
            r'<div class="cm-mcq-actions">[\s\S]*?</div>\s*</div>)',
            re.S,
        )
    elif class_substr == "cm-try-banner":
        pat = re.compile(
            r'(<div class="cm-try-banner[^"]*"[\s\S]*?</div>\s*(?:</div>\s*)?)',
            re.S,
        )
    else:
        pat = re.compile(
            rf'(<div class="[^"]*{re.escape(class_substr)}[^"]*"[\s\S]*?</div>)',
            re.S,
        )
    m = pat.search(html)
    if not m:
        return html, ""
    block = m.group(1)
    rest = (html[: m.start()] + html[m.end() :]).strip()
    return rest, block


def _remove_try_banners(html: str) -> str:
    for _ in range(12):
        if "cm-try-banner" not in html:
            break
        rest, block = _extract_div_block(html, "cm-try-banner")
        if not block:
            break
        html = rest
    return html.strip()


def _extract_figure_blocks(html: str) -> tuple[str, list[str]]:
    """Pull figure containers out of question HTML for reordering."""
    figures: list[str] = []
    rest = html
    for pat in (
        r'<div class="cm-slide-figure">.*?</div>',
        r'<div class="stem-figure-wrap"[^>]*>.*?</div>',
    ):
        while True:
            m = re.search(pat, rest, flags=re.S)
            if not m:
                break
            figures.append(m.group(0))
            rest = (rest[: m.start()] + rest[m.end() :]).strip()
    return rest, figures


def _normalize_question_figure_layout(html: str) -> str:
    """Figure above stem text (after strategy / role chips) for every diagram question."""
    rest, figures = _extract_figure_blocks(html)
    if not figures:
        return html
    fig_block = "\n".join(figures)
    chip_pat = re.compile(
        r'(<div class="cm-strategy-chip"[\s\S]*?</div>'
        r'|<div class="cm-slide-role[^"]*"[\s\S]*?</div>)',
        flags=re.S,
    )
    chips = list(chip_pat.finditer(rest))
    if chips:
        insert_at = chips[-1].end()
        rest = rest[:insert_at] + "\n" + fig_block + "\n" + rest[insert_at:].lstrip()
    else:
        rest = fig_block + "\n" + rest
    return rest.strip()


def _finalize_question_slide_layout(html: str, strategy_hint: str = "") -> str:
    if "cm-question-workspace" in html:
        stem_m = re.search(
            r'(<div class="cm-question-stem">)(.*?)(</div>\s*<div class="cm-question-interact")',
            html,
            flags=re.S,
        )
        if stem_m:
            stem = _normalize_question_figure_layout(stem_m.group(2))
            return html[: stem_m.start(2)] + stem + html[stem_m.end(2) :]
        stem_only = re.search(
            r'(<div class="cm-question-stem">)(.*?)(</div>\s*</div>\s*$)',
            html,
            flags=re.S,
        )
        if stem_only:
            stem = _normalize_question_figure_layout(stem_only.group(2))
            return html[: stem_only.start(2)] + stem + html[stem_only.end(2) :]
        return html

    html = _remove_try_banners(html)
    stem = html
    interact = ""
    for cls in ("cm-grid-in-interactive", "cm-mcq-interactive"):
        stem, block = _extract_div_block(stem, cls)
        if block:
            interact = block
            break
    stem = _normalize_question_figure_layout(stem.strip())
    has_figure = "cm-slide-figure" in stem or "stem-figure-wrap" in stem
    if not interact and not has_figure:
        return html
    strategy_html = ""
    if strategy_hint.strip():
        safe_hint = html_module.escape(strategy_hint.strip())
        strategy_html = (
            f'<div class="cm-strategy-chip">'
            f'<span class="cm-strategy-chip-label">Strategy</span>'
            f"<p>{safe_hint}</p>"
            f"</div>"
        )
    if interact:
        return (
            f'<div class="cm-question-workspace">'
            f'<div class="cm-question-stem">{strategy_html}{stem}</div>'
            f'<div class="cm-question-interact">{interact}</div>'
            f"</div>"
        )
    return (
        f'<div class="cm-question-workspace cm-question-workspace--figure-only">'
        f'<div class="cm-question-stem">{strategy_html}{stem}</div>'
        f"</div>"
    )


def _finalize_all_question_slides(slides: list[dict[str, Any]]) -> None:
    for slide in slides:
        if slide.get("kind") not in {"question", "practice", "example"}:
            continue
        html = slide.get("html") or ""
        has_interact = "data-cm-mcq" in html or "data-cm-grid-in" in html
        has_figure = "cm-slide-figure" in html or "stem-figure-wrap" in html
        if not has_interact and not has_figure:
            continue
        slide["html"] = _finalize_question_slide_layout(
            html,
            str(slide.get("strategy_hint") or ""),
        )


def _needs_math_delimiters(text: str) -> bool:
    t = re.sub(r"<[^>]+>", "", text).strip()
    if not t:
        return False
    if re.search(r"Option\s+[A-D]|only\)", t, re.I):
        return False
    if re.match(r"^[A-D]\.$", t.strip()):
        return False
    if re.search(
        r"\\(?:d|t)?frac|\\sqrt|\\left|\\right|\\Rightarrow|\\neq|\\boxed"
        r"|\\(?:pi|theta|sin|cos|tan|angle|widehat|overline)\b"
        r"|=|\^|_[{]|\d+\.?\d*[a-z]|[a-z]\s*[-+]\s*(?:\d|\\)",
        t,
    ):
        return True
    if len(re.findall(r"[A-Za-z]{2,}", t)) >= 5:
        return False
    return False


def _strip_inline_math_delimiters(text: str) -> str:
    """Remove delimiters only when the entire string is one inline-math block."""
    out = text.strip()
    if (
        out.startswith(r"\(")
        and out.endswith(r"\)")
        and out.count(r"\(") == 1
        and out.count(r"\)") == 1
    ):
        out = out[2:-2].strip()
    out = re.sub(r"\\text\{([^}]*)\}", r"\1", out)
    out = re.sub(r"\\mathbf\{([^}]*)\}", r"\1", out)
    return out.strip()


def _unwrap_outer_math_delimiters(text: str) -> str:
    out = text.strip()
    if out.startswith(r"\(") and out.endswith(r"\)"):
        return out[2:-2].strip()
    return out


def _format_mcq_letter_answer(raw: str) -> str | None:
    """Format '(B) \\frac{...}{...}' / 'D) \\displaystyle 14.3' answer cards."""
    text = re.sub(r"<[^>]+>", "", raw).strip()
    text = _unwrap_outer_math_delimiters(text)
    text = re.sub(r"\\?\(\s*\\displaystyle\s*\\?\)\s*", "", text).strip()
    m = re.match(r"^\(?([A-D])\)?\.?\s*(.*)$", text, re.I | re.S)
    if not m:
        return None
    letter = m.group(1).upper()
    rest = m.group(2).strip()
    if not rest:
        return f"<strong>{letter}</strong>"
    rest = _unwrap_outer_math_delimiters(rest)
    rest = re.sub(r"\\displaystyle\s*", "", rest).strip()
    if (
        _needs_math_delimiters(rest)
        or re.search(r"\\(?:d|t)?frac|\\left|\\right|\\dfrac|\\\\|^\\%", rest)
        or re.search(r"\\%|\d+\.\d+\\%", rest)
    ):
        return (
            f'<strong>{letter}</strong> '
            f'<span class="cm-answer-card-math">\\({rest}\\)</span>'
        )
    return f"<strong>{letter}</strong> {rest}"


def _answer_card(label: str, value_html: str) -> str:
    clean_label = label.rstrip(":").strip()
    return (
        f'<div class="cm-answer-card">'
        f'<span class="cm-answer-card-label">{clean_label}</span>'
        f'<div class="cm-answer-card-value">{value_html}</div>'
        f"</div>"
    )


def _format_mixed_prose_answer(raw: str) -> str:
    text = raw.strip()
    text = re.sub(
        r"\\?\(\s*\\mathbf\{([^}]*)\}\s*\\?\)",
        r"<strong>\1</strong>",
        text,
    )
    # Delimiters may already be stripped upstream (e.g. _format_answer_value).
    text = re.sub(r"\\mathbf\{([^}]*)\}", r"<strong>\1</strong>", text)

    out: list[str] = []
    i = 0
    open_d, close_d = r"\(", r"\)"
    olen, clen = len(open_d), len(close_d)
    while i < len(text):
        idx = text.find(open_d, i)
        if idx == -1:
            out.append(text[i:])
            break
        out.append(text[i:idx])
        end = text.find(close_d, idx + olen)
        if end == -1:
            out.append(text[idx:])
            break
        inner = text[idx + olen : end].strip()
        if _needs_math_delimiters(inner):
            out.append(f"\\({inner}\\)")
        else:
            out.append(inner)
        i = end + clen
    return "".join(out)


def _repair_latex_garble(html: str) -> str:
    """Fix LaTeX fragments left outside MathJax delimiters after HTML conversion."""
    while True:
        merged = re.sub(
            r"\\?\(\s*\\displaystyle\s+(.*?)\\?\)\s*,?\s*\\quad\s*\\?\(\s*\\displaystyle\s+(.*?)\\?\)",
            lambda m: f"\\(\\displaystyle {m.group(1)}, \\quad {m.group(2)}\\)",
            html,
            flags=re.S,
        )
        if merged == html:
            break
        html = merged

    html = re.sub(
        r"\\?\(\s*\\displaystyle\s*\\?\)\s*(?=<span class=\"cm-answer-box\">)",
        "",
        html,
        flags=re.S,
    )

    def fix_broken_card_math(m: re.Match[str]) -> str:
        inner = _strip_inline_math_delimiters(m.group(2))
        if _needs_math_delimiters(inner):
            return f"{m.group(1)}\\(\displaystyle {inner}\\){m.group(3)}"
        return f"{m.group(1)}{inner}{m.group(3)}"

    html = re.sub(
        r'(<span class="cm-answer-card-math">)\\?\(\s*\\displaystyle\s*\\?\)\s*(.*?)(</span>)',
        fix_broken_card_math,
        html,
        flags=re.S,
    )

    html = re.sub(
        r'(<div class="cm-answer-card-value">)\\?\(\s*\\displaystyle\s*\\?\)\s*(<span class="cm-answer-box">(.*?)</span>)(</div>)',
        lambda m: f'{m.group(1)}{_format_answer_value(m.group(2))}{m.group(4)}',
        html,
        flags=re.S,
    )

    return html


def _format_mcq_letter_with_math(inner: str) -> str | None:
    """Format 'Correct Answer: C. \\frac{4}{3}' style boxed content."""
    text = re.sub(r"<[^>]+>", "", inner).strip()
    text = re.sub(r"\\text\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    m = re.match(
        r"^(?:Correct Answer:\s*)?([A-D])\.?\s*(.*)$",
        text,
        flags=re.I | re.S,
    )
    if not m:
        return None
    letter = m.group(1).upper()
    rest = m.group(2).strip()
    if not rest:
        return f"<strong>{letter}</strong>"
    if _needs_math_delimiters(rest):
        return (
            f'<strong>{letter}</strong> '
            f'<span class="cm-answer-card-math">\\({rest}\\)</span>'
        )
    return f"<strong>{letter}</strong> {rest}"


def _format_answer_value(raw: str) -> str:
    raw = raw.strip()
    mcq_formatted = _format_mcq_letter_answer(raw)
    if mcq_formatted:
        return mcq_formatted
    if r"\(" in raw or r"\)" in raw:
        if not re.search(r'<span class="cm-answer-(?:box|highlight|card)', raw):
            raw = _format_mixed_prose_answer(raw)
    raw = re.sub(r"\\?\(\s*\\displaystyle\s*\\?\)\s*", "", raw)
    raw = _unwrap_outer_math_delimiters(raw)
    plain_preview = re.sub(r"<[^>]+>", "", raw)
    plain_stripped = _strip_inline_math_delimiters(plain_preview)
    if re.search(r"\\boxed\{", plain_stripped) and _needs_math_delimiters(plain_stripped):
        return f'<span class="cm-answer-card-math">\\({plain_stripped}\\)</span>'
    if len(re.findall(r"[A-Za-z]{2,}", plain_preview)) >= 5:
        return _format_mixed_prose_answer(raw)
    raw = re.sub(
        r'^\\?\(\s*(<span class="cm-answer-box">.*?</span>)\s*\\?\)$',
        r"\1",
        raw,
        flags=re.S,
    )
    box_m = re.search(r'<span class="cm-answer-box">(.*?)</span>', raw, flags=re.S)
    if box_m and raw.strip() not in {box_m.group(0), f"\\({box_m.group(0)}\\)"}:
        inner = _strip_inline_math_delimiters(box_m.group(1))
        prefix = raw[: box_m.start()].strip()
        tail = raw[box_m.end() :].strip()
        prefix = re.sub(r"\\[()$]", "", prefix).strip()
        prefix = re.sub(r"\\displaystyle\s*", "", prefix).strip()
        tail = re.sub(r"\\[()$]", "", tail).strip()
        tail = re.sub(r"\\displaystyle\s*", "", tail).strip()
        if re.match(r"^[A-Za-z]\s*=\s*$", prefix):
            return f'<span class="cm-answer-card-math">\\({prefix}{inner}\\)</span>'
        if _needs_math_delimiters(inner):
            value = f'<span class="cm-answer-card-math">\\(\\boxed{{{inner}}}\\)</span>'
        else:
            value = f'<span class="cm-answer-box">{inner}</span>'
        extra = " ".join(p for p in (prefix, tail) if p)
        return f"{value} {extra}".strip()
    if box_m and raw.strip() in {box_m.group(0), f"\\({box_m.group(0)}\\)"}:
        inner = _strip_inline_math_delimiters(box_m.group(1))
        mcq_formatted = _format_mcq_letter_with_math(inner)
        if mcq_formatted:
            return mcq_formatted
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
    if re.search(r"\\[\(\)]", plain):
        if "<span class=" in raw:
            return raw
        return f'<span class="cm-answer-card-math">{plain}</span>'
    if _needs_math_delimiters(plain):
        return f'<span class="cm-answer-card-math">\\({plain}\\)</span>'
    if plain and not re.search(r"[<>]", raw):
        return plain
    return raw


def _polish_answer_lines(html: str) -> str:
    """Turn legacy \\( … \\) answer markup into premium answer cards."""
    html = _repair_latex_garble(html)
    html = re.sub(
        r'<p><strong>(Final Answer|Correct Answer|Correct answer|Closest answer|Answer):\s*(\d+(?:\.\d+)?)\s*</strong></p>',
        lambda m: _answer_card(m.group(1), _format_answer_value(m.group(2))),
        html,
        flags=re.S | re.I,
    )
    html = re.sub(
        r'<p><strong>(Final Answer|Correct Answer|Correct answer|Closest answer|Answer):\s*</strong>\s*(.*?)</p>',
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
    html = re.sub(
        r'<div class="stem-math-block cm-math-block"><span class="cm-answer-box">(.*?)</span></div>',
        lambda m: _answer_card(
            "Correct Answer",
            _format_answer_value(f'<span class="cm-answer-box">{m.group(1)}</span>'),
        ),
        html,
        flags=re.S,
    )
    html = _repair_latex_garble(html)
    html = re.sub(
        r'(<div class="cm-answer-card-value">)(\\(?:d|t)?frac\{[^}]+\}\{[^}]+\}(?:[^<]*?)?)(</div>)',
        lambda m: (
            f'{m.group(1)}<span class="cm-answer-card-math">\\({m.group(2).strip()}\\)</span>{m.group(3)}'
            if _needs_math_delimiters(m.group(2))
            else m.group(0)
        ),
        html,
        flags=re.S,
    )
    html = re.sub(
        r'(<span class="cm-answer-card-math">)\\\(\s*\\boxed\{([^{}]+)\}\s+([^<]*?[A-Za-z][^<]*?)\\\)(</span>)',
        lambda m: (
            f'{m.group(1)}\\(\\boxed{{{m.group(2).strip()}}}\\){m.group(4)} '
            f'{m.group(3).strip()}'
        ),
        html,
        flags=re.S,
    )
    html = re.sub(
        r'(<span class="cm-answer-card-math">)\\\(\s*\\boxed\{([^{}]+)\}\s*[.,;:]\s*\\\)(</span>)',
        lambda m: f'{m.group(1)}\\(\\boxed{{{m.group(2).strip()}}}\\){m.group(3)}',
        html,
        flags=re.S,
    )
    html = re.sub(
        r'(<span class="cm-answer-card-math">)\\\((.*?)\\\)(\\\))(</span>)',
        lambda m: (
            f'{m.group(1)}\\({m.group(2)}\\){m.group(4)}'
            if m.group(2).count(r"\(") == 0 and m.group(2).count(r"\)") == 0
            else m.group(0)
        ),
        html,
        flags=re.S,
    )
    html = re.sub(
        r'(<div class="cm-answer-card-value">)([^<]*?)\\\)([^<]*?)(</div>)',
        lambda m: (
            f"{m.group(1)}{m.group(2).strip()}{m.group(3).strip()}{m.group(4)}"
            if m.group(2).strip()
            and not m.group(2).strip().startswith(r"\(")
            and r"\(" not in m.group(2)
            else m.group(0)
        ),
        html,
        flags=re.S,
    )
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


_SLIDE_ROLE_META: dict[str, tuple[str, str, str]] = {
    "concept": (
        "Knowledge Point",
        "Learn the rule",
        "Understand the definition, formula, or theorem before trying a problem.",
    ),
    "lesson": (
        "Knowledge Point",
        "Build the method",
        "Focus on the worked idea and the steps you will reuse later.",
    ),
    "example": (
        "Guided Example",
        "Watch the process",
        "Follow the model first, then try the next similar problem yourself.",
    ),
    "question": (
        "Question Practice",
        "Try it first",
        "Pause and solve before checking the answer or worked solution.",
    ),
    "practice": (
        "Question Practice",
        "Independent attempt",
        "Treat this like a test question: choose a strategy, solve, then verify.",
    ),
    "answer": (
        "Answer Review",
        "Check and correct",
        "Compare your work with the final answer and fix any missed step.",
    ),
    "solution": (
        "Solution Review",
        "Study the reasoning",
        "Read the steps carefully, then summarize the method in your own words.",
    ),
}


def _slide_role_banner(kind: str) -> str:
    meta = _SLIDE_ROLE_META.get(kind)
    if not meta:
        return ""
    label, action, guidance = meta
    return (
        f'<div class="cm-slide-role cm-slide-role--{kind}">'
        f'<span class="cm-slide-role-label">{label}</span>'
        f'<strong>{action}</strong>'
        f'<p>{guidance}</p>'
        f"</div>"
    )


def _enrich_slide_html(html: str, kind: str, title: str) -> str:
    html = html.replace("%%HFILL%%", " ")
    if kind in {"question", "practice", "example"}:
        html = _wrap_table_mcq_list(html)
        html = _wrap_display_array_mcq_list(html)
    html = _wrap_answer_choices(html)
    if kind in {"question", "practice", "example"}:
        html = _wrap_standalone_mcq_list(html)
    html = _wrap_concept_focus(html, kind)
    html = _wrap_law_rule_slides(html, title)
    html = _wrap_property_formula_list(html, title)
    html = _wrap_summary_recap(html, title)
    if kind == "example" or re.search(r"<p><strong>Solution:\s*</strong></p>", html, re.I):
        html = _wrap_inline_solution(html)
    if kind in {"answer", "solution"}:
        html = _wrap_solution_steps(html)
    if kind in {"question", "practice"}:
        html = _wrap_question_challenge(html, title)
    html = _polish_answer_lines(html)
    banner = _slide_role_banner(kind)
    if banner and "cm-slide-role" not in html:
        html = banner + html
    return html


def _body_has_mcq_choices(html: str) -> bool:
    for lst in re.finditer(
        r'<(?:ul|ol) class="(?:stem-itemize|stem-enumerate cm-beamer-list)">(.*?)</(?:ul|ol)>',
        html,
        flags=re.S,
    ):
        choices = _extract_mcq_choices_from_list(lst.group(1))
        if _valid_mcq_choice_set(choices):
            return True
    for tbl in re.finditer(
        r'<div class="stem-table-wrap">\s*<table class="stem-table">.*?</table>\s*</div>',
        html,
        flags=re.S,
    ):
        choices = _extract_mcq_choices_from_table(tbl.group(0))
        if _valid_mcq_choice_set(choices):
            return True
    return False


def _detect_slide_kind(title: str, plain: str, html: str) -> str:
    t = (title + " " + plain).lower()
    tl = title.lower().strip()
    if "cm-intro-canvas" in html:
        return "intro"
    if "cm-content-canvas" in html:
        return "content"
    if "cm-section-divider" in html:
        return "section"
    if "thank you" in t or "great work" in t or "cm-slide-closing" in html or "cm-closing-canvas" in html:
        return "closing"
    if (
        tl.startswith("answer:")
        or tl.startswith("answer :")
        or tl.startswith("answer explanation:")
        or tl.startswith("answer to")
        or tl == "answer"
        or tl.startswith("answer explanation")
        or re.match(r"^answer\b", tl)
    ):
        return "answer"
    if tl.startswith("solution:") or (tl.startswith("solution") and "finding" in tl):
        return "solution"
    if re.match(r"^example:\s*solution\b", tl):
        return "solution"
    if tl.startswith("challenge:"):
        return "question"
    if re.search(r"\bquestion:\s", plain, re.I) and not re.search(
        r"step\s*1", plain, re.I
    ):
        if not tl.startswith("solution"):
            return "question"
    if re.search(r"\bquestion\b", tl) and not tl.startswith("solution") and "questions" not in tl:
        return "question"
    if (
        re.search(r"\bproblem\b", tl)
        and "?" in plain
        and not tl.startswith("solution")
        and not re.search(r"step\s*1", plain, re.I)
    ):
        return "question"
    if tl.startswith("example"):
        return "example"
    if "word problem" in tl or "problem statement" in t[:220]:
        if not tl.startswith("solution") and "step 1" not in t:
            return "practice"
    if tl.startswith("solution") or ": solution" in tl:
        return "solution"
    if _body_has_mcq_choices(html) and not tl.startswith("answer"):
        return "question"
    if "introduction" in t or "overview" in t or "definition" in t:
        return "concept"
    if "summary" in tl:
        return "lesson"
    if "table:" in tl or "cm-mcq-grid" in html or "answer choices" in t:
        return "question"
    if len(plain) < 40 and not re.search(r"\\[\(\[]", plain):
        return "section"
    return "lesson"


def _normalize_math_snippet(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\\displaystyle\s*", "", text)
    text = re.sub(r"\\?\(\s*", "", text)
    text = re.sub(r"\s*\\?\)", "", text)
    text = re.sub(r"\\boxed\{", "", text)
    text = re.sub(r"\\text\{", "", text)
    text = text.replace("}", "")
    text = re.sub(r"\s+", "", text)
    return text.strip().rstrip(".,;")


def _letter_from_answer_value(value: str) -> str | None:
    m = re.search(r"^([A-D])\.?", value, flags=re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"\\boxed\{([A-D])", value, flags=re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"\\boxed\{\\text\{([A-D])", value, flags=re.I)
    if m:
        return m.group(1).upper()
    return None


def _match_mcq_from_numeric_answer(
    answer_html: str, question_html: str
) -> str | None:
    """When the answer slide gives a numeric value, map it to the MCQ letter."""
    if not question_html or "cm-mcq-interactive" not in question_html:
        return None
    numeric_answer = None
    for pattern in (
        r'cm-answer-card-math">\\?\(\\?\\boxed\{([^}]+)\}',
        r'cm-answer-card-value"><span class="cm-answer-card-math">\\?\(\\?\\boxed\{([^}]+)\}',
        r'cm-answer-box">\\?\\boxed\{([^}]+)\}',
        r'cm-answer-card-label">(?:Final Answer|Answer|Correct Answer|Correct answer)</span>.*?cm-answer-card-value">(.*?)</div>',
    ):
        m = re.search(pattern, answer_html, flags=re.S | re.I)
        if not m:
            continue
        raw = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        raw = _strip_inline_math_delimiters(raw)
        raw = re.sub(r"^\\boxed\{([^}]+)\}$", r"\1", raw)
        numeric_answer = _normalize_math_snippet(raw)
        if numeric_answer:
            break
    if not numeric_answer:
        return None
    for item in re.finditer(
        r'data-choice="([A-D])".*?cm-mcq-text">(.*?)</span>',
        question_html,
        flags=re.S,
    ):
        option_value = _normalize_math_snippet(item.group(2))
        if option_value and option_value == numeric_answer:
            return item.group(1).upper()
    return None


def _extract_correct_choice(answer_html: str, question_html: str = "") -> str | None:
    plain = _plain_text_from_html(answer_html)
    for pattern in (
        r"correct answer[^a-zA-Z]*([A-D])\b",
        r"correct interpretation[^a-zA-Z]*([A-D])\b",
        r"correct answer is[^a-zA-Z]*([A-D])\b",
        r"closest answer[^a-zA-Z]*\(?([A-D])\)?",
        r"\\textbf\{Answer:\}[^a-zA-Z]*\\textcolor\{[^}]+\}\{([A-D])\.",
        r"\\textcolor\{[^}]+\}\{([A-D])\.?\}",
        r"correct answer is[^a-zA-Z]*\\textcolor\{[^}]+\}\{([A-D])",
        r"<strong>Answer:</strong>\s*(?:<[^>]+>)*([A-D])\.",
        r"option\s*<strong>\s*([A-D])\b",
        r"option\s+\**([A-D])\b",
        r'cm-answer-box">\s*\(?([A-D])\)?',
        r'cm-answer-box">([A-D])\.',
        r'cm-answer-card-value">\s*<strong>\s*([A-D])\s*</strong>',
        r'cm-answer-card-value">\s*([A-D])\.(?:\s|<|</)',
        r"\\boxed\{\\text\{Correct Answer:\s*([A-D])",
        r"\\boxed\{\\text\{([A-D])\.",
        r"\\boxed\{([A-D])\.?\}",
        r"\\boxed\{([A-D])\.\s",
        r"\\boxed\{\\text\{([A-D])\}\}",
        r'cm-answer-card-math">\\?\(\\?\\boxed\{([A-D])\.',
    ):
        m = re.search(pattern, answer_html, flags=re.I | re.S)
        if m:
            return m.group(1).upper()

    m = re.search(
        r'cm-answer-box"><strong>([A-D])</strong>',
        answer_html,
        flags=re.S | re.I,
    )
    if m:
        return m.group(1).upper()

    m = re.search(
        r'cm-answer-card-label">(?:Correct Answer|Final Answer)</span>.*?cm-answer-card-value">(?:\s*<strong>\s*)?([A-D])\b',
        answer_html,
        flags=re.S | re.I,
    )
    if m:
        return m.group(1).upper()

    m = re.search(
        r'cm-answer-card-label">Correct Answer</span>.*?cm-answer-card-value">(?:<strong>)?([A-D])',
        answer_html,
        flags=re.S | re.I,
    )
    if m:
        return m.group(1).upper()

    m = re.search(
        r'cm-answer-card-label">Correct answer</span>.*?cm-answer-card-(?:value|math)[^>]*>.*?\(?([A-D])\)',
        answer_html,
        flags=re.S | re.I,
    )
    if m:
        return m.group(1).upper()

    m = re.search(
        r"<p><strong>([A-D])\.?</strong>",
        answer_html,
    )
    if m and re.search(r"correct interpretation", plain, re.I):
        return m.group(1).upper()

    final_m = re.search(
        r'cm-answer-card-label">Final Answer</span>.*?cm-answer-card-value">(.*?)</div>',
        answer_html,
        flags=re.S | re.I,
    )
    if final_m and question_html and "cm-mcq-interactive" in question_html:
        final_value = _normalize_math_snippet(final_m.group(1))
        letter = _letter_from_answer_value(final_m.group(1))
        if letter:
            return letter
        if re.fullmatch(r"[A-D]", final_value, flags=re.I):
            return final_value.upper()
        final_body = re.sub(r"^[A-D]\.?", "", final_value, flags=re.I)
        for item in re.finditer(
            r'data-choice="([A-D])".*?cm-mcq-text">(.*?)</span>',
            question_html,
            flags=re.S,
        ):
            option_value = _normalize_math_snippet(item.group(2))
            if option_value and (option_value == final_value or option_value == final_body):
                return item.group(1).upper()

    matched = _match_mcq_from_numeric_answer(answer_html, question_html)
    if matched:
        return matched

    return None


def _answer_slides_for_question(
    slides: list[dict[str, Any]], question_index: int, first_answer_index: int
) -> list[dict[str, Any]]:
    """Collect consecutive answer/solution slides after a question."""
    by_index = {slide["index"]: slide for slide in slides}
    first = by_index.get(first_answer_index)
    if not first:
        return []
    start_pos = next(i for i, s in enumerate(slides) if s["index"] == first_answer_index)
    answer_kinds = {"answer", "solution"}
    question_kinds = {"question", "practice", "example"}
    collected: list[dict[str, Any]] = []
    for slide in slides[start_pos:]:
        kind = slide.get("kind", "lesson")
        title = slide.get("title", "").lower()
        if collected and kind in question_kinds:
            break
        if kind in answer_kinds or title.startswith("answer") or title.startswith("solution"):
            collected.append(slide)
            continue
        if collected:
            break
    return collected


def _inject_mcq_correct_answers(slides: list[dict[str, Any]]) -> None:
    by_index = {slide["index"]: slide for slide in slides}
    for slide in slides:
        html = slide.get("html", "")
        if "data-cm-mcq" not in html or "data-cm-correct" in html:
            continue
        answer_index = slide.get("answer_index")
        if not answer_index:
            continue
        letter = None
        for ans_slide in _answer_slides_for_question(slides, slide["index"], answer_index):
            letter = _extract_correct_choice(ans_slide.get("html", ""), html)
            if letter:
                answer_index = ans_slide["index"]
                break
        if not letter:
            continue
        slide["html"] = html.replace(
            "data-cm-mcq>",
            f'data-cm-mcq data-cm-correct="{letter}">',
            1,
        )
        slide["correct_choice"] = letter
        slide["answer_index"] = answer_index


def _replace_dfracs(text: str) -> str:
    out = text
    marker = r"\dfrac"
    while True:
        idx = out.find(marker)
        if idx == -1:
            break
        pos = idx + len(marker)
        while pos < len(out) and out[pos].isspace():
            pos += 1
        num, pos = _extract_braced_content(out, pos)
        if num is None:
            break
        while pos < len(out) and out[pos].isspace():
            pos += 1
        den, pos = _extract_braced_content(out, pos)
        if den is None:
            break
        out = out[:idx] + f"{num}/{den}" + out[pos:]
    return out


def _latex_to_compare_forms(latex: str) -> list[str]:
    s = latex.strip()
    boxed_m = re.match(r"\\boxed\{(.+)\}\s*$", s, flags=re.S)
    if boxed_m:
        s = boxed_m.group(1).strip()
    s = re.sub(r"\\displaystyle\s*", "", s)
    s = re.sub(r"\\(?:left|right)\b", "", s)
    s = _replace_dfracs(s)
    s = re.sub(r"\\(?:d|t)?frac\{([^{}]+)\}\{([^{}]+)\}", r"\1/\2", s)
    s = re.sub(r"\^\{([^{}]+)\}", r"^(\1)", s)
    s = re.sub(r"\^([^{\s(])", r"^\1", s)
    s = re.sub(r"_\{([^{}]+)\}", r"_\1", s)
    s = re.sub(r"\\cdot", "*", s)
    s = re.sub(r"\\times", "*", s)
    s = re.sub(r"\s+", "", s)
    forms: list[str] = []
    if s:
        forms.append(s)
    var_m = re.match(r"([a-zA-Z]+)=(.+)", s)
    if var_m:
        forms.append(var_m.group(2))
        forms.append(f"{var_m.group(1)}={var_m.group(2)}")
    alt = s.replace("^(", "^").replace(")", "")
    if alt and alt not in forms:
        forms.append(alt)
    for f in list(forms):
        frac_m = re.fullmatch(r"(-?\d+)/(-?\d+)", f)
        if frac_m:
            num, den = int(frac_m.group(1)), int(frac_m.group(2))
            if den:
                val = num / den
                forms.append(str(val))
                forms.append(f"{val:.4f}".rstrip("0").rstrip("."))
    return list(dict.fromkeys(x for x in forms if x))


def _boxed_latex_values(text: str) -> list[str]:
    values: list[str] = []
    for m in re.finditer(r"\\boxed\{([^{}]*(?:\{[^{}]*\})*)\}", text):
        value = m.group(1).strip()
        if value:
            values.append(value)
    return values


def _looks_like_grid_in_value(value: str) -> bool:
    if not value or len(value) > 48:
        return False
    if value.upper() in {"A", "B", "C", "D"}:
        return False
    if re.match(r"^[A-D]\.", value):
        return False
    if re.search(r"\b(is|greater|less|median|group|option)\b", value, re.I):
        return False
    return bool(
        re.search(
            r"[\d./\\^\-]|\\(?:d|t)?frac|\\sqrt|pi\b|[a-z]=|[a-z]\^",
            value,
            re.I,
        )
    )


def _extract_numeric_answer_text(text: str) -> str | None:
    """Pull a numeric SAT grid-in value from answer prose or markup."""
    plain = re.sub(r"<[^>]+>", " ", text)
    plain = re.sub(r"\s+", " ", plain).strip()
    for pattern in (
        r"Correct Answer:\s*(\d+(?:\.\d+)?)",
        r"Final Answer:\s*(?:[^0-9]{0,24})?(\d+(?:\.\d+)?)",
        r"is\s+(\d+(?:\.\d+)?)\s+greater\s+than",
        r"(\d+(?:\.\d+)?)\s*[-+×*/]\s*\d+(?:\.\d+)?\s*=\s*(\d+(?:\.\d+)?)",
        r"=\s*(\\boxed\{(\d+(?:\.\d+)?)\})",
    ):
        m = re.search(pattern, plain, re.I)
        if not m:
            continue
        value = m.group(m.lastindex or 1).strip()
        value = re.sub(r"^\\boxed\{([^}]+)\}$", r"\1", value)
        if value and re.fullmatch(r"\d+(?:\.\d+)?", value):
            return value
    step_blocks = re.findall(r'cm-step-block[^>]*>(.*?)</div>', text, flags=re.S)
    for block in reversed(step_blocks):
        eq_m = re.search(
            r"(\d+(?:\.\d+)?)\s*[-+×*/]\s*\d+(?:\.\d+)?\s*=\s*(\d+(?:\.\d+)?)",
            re.sub(r"<[^>]+>", " ", block),
        )
        if eq_m:
            return eq_m.group(2)
    return None


def _grid_in_from_latex(latex: str) -> dict[str, Any] | None:
    latex = latex.strip()
    if not _looks_like_grid_in_value(latex):
        return None
    accept = _latex_to_compare_forms(latex)
    if accept:
        return {"display": latex, "accept": accept}
    return None


def _extract_grid_in_answer(answer_html: str) -> dict[str, Any] | None:
    """Extract a numeric or expression answer for fill-in-the-blank widgets."""
    if re.search(
        r'cm-answer-card-value">\s*<strong>[A-D]</strong>\s*</div>',
        answer_html,
        flags=re.S | re.I,
    ):
        return None
    if re.search(
        r'cm-answer-card-value"><strong>[A-D]</strong>\s*[\d,]',
        answer_html,
        flags=re.S | re.I,
    ):
        return None

    for boxed in reversed(_boxed_latex_values(answer_html)):
        extracted = _grid_in_from_latex(boxed)
        if extracted:
            return extracted

    eq_boxed = re.search(r"=\s*\\boxed\{([^}]+)\}", answer_html)
    if eq_boxed:
        extracted = _grid_in_from_latex(eq_boxed.group(1).strip())
        if extracted:
            return extracted

    math_matches = list(
        re.finditer(r'cm-answer-card-math">\\?\((.*?)\\?\)</span>', answer_html, flags=re.S)
    )
    if math_matches:
        latex = math_matches[-1].group(1).strip()
        for boxed in reversed(_boxed_latex_values(latex)):
            extracted = _grid_in_from_latex(boxed)
            if extracted:
                return extracted
        extracted = _grid_in_from_latex(latex)
        if extracted:
            return extracted

    card_m = re.search(r'cm-answer-card-value">(.*?)</div>', answer_html, flags=re.S)
    if card_m:
        raw = re.sub(r"<[^>]+>", "", card_m.group(1)).strip()
        raw = re.sub(r"^\\mathbf\{([^}]+)\}$", r"\1", raw)
        for boxed in reversed(_boxed_latex_values(raw)):
            extracted = _grid_in_from_latex(boxed)
            if extracted:
                return extracted
        if raw and raw.upper() not in {"A", "B", "C", "D"}:
            extracted = _grid_in_from_latex(raw)
            if extracted:
                return extracted

    final_m = re.search(
        r'cm-answer-card-label">Final Answer</span>\s*'
        r'<div class="cm-answer-card-value">(.*?)</div>',
        answer_html,
        flags=re.S | re.I,
    )
    if final_m:
        raw = re.sub(r"<[^>]+>", "", final_m.group(1)).strip()
        raw = re.sub(r"^\\mathbf\{([^}]+)\}$", r"\1", raw)
        for boxed in reversed(_boxed_latex_values(raw)):
            extracted = _grid_in_from_latex(boxed)
            if extracted:
                return extracted
        if raw and raw.upper() not in {"A", "B", "C", "D"}:
            extracted = _grid_in_from_latex(raw)
            if extracted:
                return extracted

    for boxed in reversed(re.findall(r'cm-answer-box">([^<]+)</span>', answer_html, flags=re.S)):
        boxed = boxed.strip()
        extracted = _grid_in_from_latex(boxed)
        if extracted:
            return extracted

    numeric = _extract_numeric_answer_text(answer_html)
    if numeric:
        return _grid_in_from_latex(numeric)

    return None


def _build_grid_in_interactive(data: dict[str, Any]) -> str:
    accept_json = html_module.escape(json.dumps(data.get("accept") or []), quote=True)
    display = str(data.get("display") or "")
    if re.search(r"[a-zA-Z]", display) and re.search(r"[/^]", display):
        placeholder = "Expression, e.g. x^(4/3)/(3y^2)"
        hint = (
            '<p class="cm-grid-in-hint">Use <code>^</code> for exponents and '
            "<code>/</code> for fractions.</p>"
        )
    elif re.search(r"frac|/", display):
        placeholder = "Fraction or decimal, e.g. 7/6"
        hint = '<p class="cm-grid-in-hint">Enter an exact fraction or decimal equivalent.</p>'
    else:
        placeholder = "Your answer"
        hint = ""
    return (
        f'<div class="cm-grid-in-interactive" data-cm-grid-in data-cm-accept="{accept_json}">'
        '<p class="cm-grid-in-prompt">Your answer</p>'
        '<div class="cm-grid-in-row">'
        f'<input type="text" class="cm-grid-in-input" inputmode="text" '
        f'placeholder="{html_module.escape(placeholder, quote=True)}" '
        'autocomplete="off" spellcheck="false" aria-label="Your answer" />'
        '<button type="button" class="cm-grid-in-check" data-cm-check-grid-in disabled>'
        "Check</button>"
        "</div>"
        f"{hint}"
        '<div class="cm-grid-in-actions">'
        '<button type="button" class="cm-reveal-btn cm-reveal-btn--ghost" data-cm-go-answer">'
        "View worked solution →"
        "</button>"
        "</div>"
        '<p class="cm-grid-in-feedback" aria-live="polite"></p>'
        "</div>"
    )


def _find_grid_in_answer(slides: list[dict[str, Any]], answer_index: int | None) -> dict[str, Any] | None:
    if not answer_index:
        return None
    by_index = {slide["index"]: slide for slide in slides}
    for offset in range(3):
        slide = by_index.get(answer_index + offset)
        if not slide:
            break
        if offset > 0:
            title = slide.get("title", "").lower()
            if slide.get("kind") not in {"answer", "solution", "lesson"}:
                break
            if not re.search(r"answer|explanation|solution", title):
                break
        extracted = _extract_grid_in_answer(slide.get("html") or "")
        if extracted:
            return extracted
    return None


def _inject_grid_in_widgets(slides: list[dict[str, Any]]) -> None:
    by_index = {slide["index"]: slide for slide in slides}
    for slide in slides:
        html = slide.get("html") or ""
        if slide.get("kind") not in {"question", "practice", "example"}:
            continue
        if slide.get("inline_solution"):
            continue
        if "data-cm-mcq" in html or "data-cm-grid-in" in html:
            continue
        if _body_has_mcq_choices(html):
            continue
        answer_index = slide.get("answer_index")
        if not answer_index:
            continue
        extracted = _find_grid_in_answer(slides, answer_index)
        if not extracted:
            continue
        html = _remove_try_banners(html)
        slide["html"] = html.strip() + "\n" + _build_grid_in_interactive(extracted)
        slide["grid_in_answer"] = extracted
        slide["interactive"] = True


_FILL_IN_TEACHING_HINTS = (
    "definition",
    "introduction",
    "overview",
    "summary",
    "key takeaway",
    "understanding",
    "visual",
    "properties",
    "types of",
    "standard form",
    "vertex form",
    "factored form",
    "parabolas",
    "axis of symmetry",
    "conditional probability (concept)",
    "more on mean",
    "percent greater or less",
    "rationalizing denomin",
    "real-world application",
)


def _looks_like_fill_in_question(title: str, plain: str) -> bool:
    tl = title.lower()
    if any(hint in tl for hint in _FILL_IN_TEACHING_HINTS):
        return False
    if "?" in plain:
        return True
    return bool(
        re.search(
            r"\b(what is|how many|how much|find the|calculate|probability|express your answer)\b",
            plain,
            re.I,
        )
    )


def _promote_fill_in_slides(slides: list[dict[str, Any]]) -> None:
    """Turn lesson/example slides followed by numeric answers into questions."""
    for i, slide in enumerate(slides):
        if slide.get("kind") not in {"lesson", "example"}:
            continue
        html = slide.get("html") or ""
        if _body_has_mcq_choices(html):
            continue
        plain = _plain_text_from_html(html)
        if not _looks_like_fill_in_question(slide.get("title", ""), plain):
            continue
        if i + 1 >= len(slides):
            continue
        nxt = slides[i + 1]
        if nxt.get("kind") not in {"answer", "solution"}:
            continue
        if not _extract_grid_in_answer(nxt.get("html") or ""):
            continue
        slide["kind"] = "question"


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
            if nk in question_kinds:
                break
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
        if "triangle inequality" in t:
            return "Triangle inequality: the third side must be greater than the difference and less than the sum of the other two sides."
        if "system" in t and "inequal" in t:
            return "For a system, test each point in every inequality — only the overlap region counts."
        if "inequal" in t and ("table" in t or "array" in plain.lower()):
            return "Substitute each table row into the inequality — all three rows must satisfy it."
        if "inequal" in t and "graph" in t:
            return "Sketch or test regions; note solid vs dashed boundaries and whether endpoints are included."
        if "inequal" in t:
            return "When you multiply or divide by a negative, flip the inequality sign — then check with a test value."
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
    if "triangle inequality" in t:
        return "Use a + b > c, a + c > b, and b + c > a — combine to get the valid range for the unknown side."
    if "volume" in t or "area" in t or "cylinder" in t or "cone" in t or "prism" in t:
        return "Identify the formula, then track how scaling or unit changes affect the result."
    if "triangle" in t or "angle" in t or "parallel" in t or "similar" in t:
        return "Mark known angles and side relationships first, then use triangle or parallel-line facts."
    if "line segment" in t or "figure above" in t or "figure shown" in t or "in degrees" in t:
        return "Mark known angles and side relationships first, then use triangle or parallel-line facts."
    if "sin" in t or "cos" in t or "tan" in t or "trigon" in t:
        return "Label opposite, adjacent, and hypotenuse relative to the given angle."
    if "circle" in t or "arc" in t or "radius" in t or "circumference" in t:
        return "Rewrite the equation in standard form to read off the center and radius."
    if "exponential" in t or "decay" in t or "(1." in plain or re.search(r"\)\^|\^\{", plain):
        return "Identify the initial value, growth or decay factor, and how the exponent scales with time."
    if "quadratic" in t or "parabola" in t or "vertex" in t or "discriminant" in t:
        return "Use the graph shape, vertex or symmetry, and discriminant to narrow the answer."
    if "radical" in t or "sqrt" in plain or "\\sqrt" in plain:
        return "Isolate the radical, square both sides if needed, then check for extraneous solutions."
    if "percent" in t or "%" in plain:
        return "Translate the percent change into a multiplier, then match the time unit in the exponent."
    if "system" in t and "inequal" in t:
        return "Plug the point into each inequality separately; both must be true."
    if "inequal" in t and ("table" in t or "6x + 2" in plain):
        return "Compute the boundary 6x + 2 at each x, then confirm every y is strictly below it."
    if "inequal" in t:
        return "Boundary first: rewrite as an equation, then pick a test point to decide which side to shade."
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


def _convert_hfill_examples(text: str) -> str:
    """Neutralize \\hfill examples before math/list conversion breaks on nested parens."""
    marker = "%%HFILL%%"
    out: list[str] = []
    i = 0
    while True:
        idx = text.find(marker, i)
        if idx == -1:
            out.append(text[i:])
            break
        out.append(text[i:idx])
        pos = idx + len(marker)
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos < len(text) and text[pos] == "(":
            group = _extract_paren_group(text, pos)
            if group:
                inner, end = group
                if re.match(r"e\.g\.,\s*", inner, flags=re.I):
                    example = re.sub(r"^e\.g\.,\s*", "", inner, flags=re.I).strip()
                    out.append(f" (e.g., {example})")
                    i = end
                    continue
        out.append(marker)
        i = idx + len(marker)
    return "".join(out)


def _extract_paren_group(text: str, start: int) -> tuple[str, int] | None:
    if start >= len(text) or text[start] != "(":
        return None
    depth = 0
    j = start
    while j < len(text):
        if j + 1 < len(text) and text[j : j + 2] == r"\(":
            j += 2
            continue
        if j + 1 < len(text) and text[j : j + 2] == r"\)":
            j += 2
            continue
        ch = text[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1 : j], j + 1
        j += 1
    return None


def _split_rule_formula_example(rest: str) -> tuple[str, str]:
    rest = rest.replace("%%HFILL%%", " ").strip()
    m = re.search(r"\(e\.g\.,\s*(.*?)\)\s*$", rest, flags=re.S | re.I)
    if m:
        return rest[: m.start()].strip(), m.group(1).strip()
    return rest.strip(), ""


def _build_rule_card(name: str, formula: str, example: str = "") -> str:
    example_html = ""
    if example:
        ex = example if example.lower().startswith("e.g.") else f"e.g., {example}"
        example_html = f'<span class="cm-rule-example">{ex}</span>'
    return (
        f'<div class="cm-rule-card">'
        f'<span class="cm-rule-name">{name}</span>'
        f'<span class="cm-rule-formula">{formula}</span>'
        f"{example_html}"
        f"</div>"
    )


def _wrap_law_rule_slides(html: str, title: str) -> str:
    """Turn exponent-law bullet lists into premium rule cards."""
    if "cm-rule-grid" in html:
        return html
    tl = title.lower()
    if "laws of exponents" not in tl and "%%HFILL%%" not in html:
        return html

    groups: list[str] = []
    for m in re.finditer(
        r'<p><strong>([^<]+)</strong></p>\s*(<ul class="stem-itemize">.*?</ul>)',
        html,
        flags=re.S,
    ):
        group_name = _normalize_tex_text_escapes(m.group(1).strip())
        cards: list[str] = []
        for li_m in re.finditer(r"<li>.*?</li>", m.group(2), flags=re.S):
            li = li_m.group(0)
            rule_m = re.match(
                r"<li><strong>([^:]+):</strong>\s*(.*?)</li>",
                li.strip(),
                flags=re.S,
            )
            if not rule_m:
                continue
            formula, example = _split_rule_formula_example(rule_m.group(2))
            if formula:
                cards.append(_build_rule_card(rule_m.group(1).strip(), formula, example))
        if cards:
            groups.append(
                f'<div class="cm-rule-group">'
                f'<h4 class="cm-rule-group-title">{group_name}</h4>'
                f'<div class="cm-rule-cards">{"".join(cards)}</div>'
                f"</div>"
            )

    if not groups:
        return html.replace("%%HFILL%%", " ").strip()

    return (
        f'<div class="cm-rule-grid">'
        f'<span class="cm-rule-grid-tag">Key rules</span>'
        f'{"".join(groups)}'
        f"</div>"
    )


def _wrap_property_formula_list(html: str, title: str) -> str:
    """Format compact property lists (e.g. radical identities) as rule cards."""
    if "cm-rule-grid" in html or "cm-rule-card" in html:
        return html
    tl = title.lower()
    if "properties of" not in tl:
        return html
    ul_m = re.search(r'(<ul class="stem-itemize">.*?</ul>)', html, flags=re.S)
    if not ul_m:
        return html
    cards: list[str] = []
    for li_m in re.finditer(r"<li>(.*?)</li>", ul_m.group(1), flags=re.S):
        body = li_m.group(1).strip()
        if not body:
            continue
        name = ""
        formula = body
        label_m = re.match(r"<strong>([^:]+):</strong>\s*(.*)", body, flags=re.S)
        if label_m:
            name = label_m.group(1).strip()
            formula = label_m.group(2).strip()
        cards.append(_build_rule_card(name or "Property", formula))
    if len(cards) < 2:
        return html
    prefix = html[: ul_m.start()].strip()
    suffix = html[ul_m.end() :].strip()
    grid = (
        f'<div class="cm-rule-grid cm-rule-grid--compact">'
        f'<span class="cm-rule-grid-tag">Properties</span>'
        f'<div class="cm-rule-group">'
        f'<div class="cm-rule-cards">{"".join(cards)}</div>'
        f"</div></div>"
    )
    parts = [p for p in (prefix, grid, suffix) if p]
    return "\n".join(parts)


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


def _extract_checkpoint_item(slide: dict[str, Any]) -> dict[str, Any] | None:
    """Build a compact checkpoint item from an interactive MCQ slide."""
    html = slide.get("html", "")
    if "data-cm-mcq" not in html:
        return None
    stem_html = html.split('<div class="cm-mcq-interactive"', 1)[0].strip()
    if not stem_html:
        return None
    correct_m = re.search(r'data-cm-correct="([A-D])"', html, flags=re.I)
    correct = slide.get("correct_choice") or (correct_m.group(1).upper() if correct_m else None)
    choices: list[dict[str, str]] = []
    for m in re.finditer(
        r'data-choice="([A-D])".*?class="cm-mcq-text">(.*?)</span>',
        html,
        flags=re.S | re.I,
    ):
        choices.append({"letter": m.group(1).upper(), "text": m.group(2).strip()})
    if len(choices) != 4:
        return None
    title = slide.get("title", "")
    title = re.sub(r"^(Question|Practice|Example):\s*", "", title, flags=re.I).strip()
    return {
        "slide_index": slide["index"],
        "title": title or f"Question {slide['index']}",
        "section": slide.get("section", ""),
        "kind": slide.get("kind", "question"),
        "correct": correct,
        "answer_index": slide.get("answer_index"),
        "stem_html": stem_html,
        "choices": choices,
    }


def _build_lesson_checkpoint(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect all MCQ slides from the lesson for end-of-lesson review."""
    by_index = {slide["index"]: slide for slide in slides}
    items: list[dict[str, Any]] = []
    for slide in slides:
        if slide.get("kind") in {"intro", "content", "section", "closing"}:
            continue
        item = _extract_checkpoint_item(slide)
        if not item:
            continue
        if not item.get("correct"):
            ans_idx = slide.get("answer_index")
            answer_slide = by_index.get(ans_idx) if ans_idx else None
            if answer_slide:
                letter = _extract_correct_choice(
                    answer_slide.get("html", ""),
                    slide.get("html", ""),
                )
                if letter:
                    item["correct"] = letter
        if item.get("correct"):
            items.append(item)
    return items


def _build_knowledge_map(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group lesson slides into sections for mastery tracking."""
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for slide in slides:
        kind = slide.get("kind", "lesson")
        if kind == "section":
            title = re.sub(r"^up next\s*", "", slide.get("title", ""), flags=re.I).strip()
            current = {
                "title": title or slide.get("title", "Section"),
                "start_index": slide["index"],
                "items": [],
            }
            sections.append(current)
            continue
        if kind in {"intro", "content", "closing"}:
            continue
        if current is None:
            current = {
                "title": "Introduction",
                "start_index": slide["index"],
                "items": [],
            }
            sections.append(current)
        if kind in {"concept", "lesson", "example", "question", "practice", "answer", "solution"}:
            current["items"].append(
                {
                    "index": slide["index"],
                    "kind": kind,
                    "title": (slide.get("title") or "")[:96],
                    "interactive": bool(slide.get("interactive")),
                    "has_mcq": "data-cm-mcq" in (slide.get("html") or ""),
                }
            )
    return sections


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
    if re.search(r"thank you|great work", body, re.I):
        return _build_closing_html(body)

    body = _unwrap_beamer_block_environment(body)

    if re.search(r"\\begin\{tikzpicture\}", body) and not re.search(
        r"\\begin\{(?:tabular|align|itemize|enumerate)\}", body
    ):
        section_m = re.search(r"\\section\*?\{([^{}]+)\}", body)
        if section_m:
            section_title = _normalize_tex_text_escapes(section_m.group(1).strip())
            return (
                f'<div class="cm-section-divider">'
                f'<span class="cm-section-kicker">Up next</span>'
                f'<h3 class="cm-section-title">{section_title}</h3>'
                f"</div>"
            )
        return ""

    body = _strip_beamer_layout_commands(body)
    body = re.sub(r"\\begin\{table\}(?:\[[^\]]*\])?\s*", "", body)
    body = re.sub(r"\\end\{table\}\s*", "", body)
    body = re.sub(r"\\centering\s*", "", body)
    body = _convert_hfill_examples(body)
    body = replace_tikz_with_svg_html(body)
    body = _remove_environment(body, "tikzpicture")
    body = _flatten_columns(body)
    body = _unwrap_environment(body, "center")
    body = _remove_environment(body, "flushright")
    body = _remove_environment(body, "flushleft")
    body = _strip_beamer_layout_commands(body)

    def _convert_array_in_display_math(text: str) -> str:
        def repl_block(m: re.Match[str]) -> str:
            inner = m.group(1)
            if r"\begin{array}" not in inner and r"\begin{tabular}" not in inner:
                return m.group(0)
            # Arrays inside \left...\right or with inference arrows belong in MathJax.
            if re.search(r"\\left|\\right|\\Rightarrow|\\Leftrightarrow|\\implies", inner):
                return m.group(0)
            converted = latex_array_and_tabular_to_html(inner)
            return converted if converted != inner else m.group(0)

        return re.sub(r"\\\[(.*?)\\\]", repl_block, text, flags=re.S)

    body = _convert_array_in_display_math(body)
    math_vault: list[str] = []
    body = _shield_vaulted_blocks(body, r"\\\[.*?\\\]", math_vault)
    body = _shield_vaulted_blocks(body, r"\\\(.*?\\\)", math_vault)
    body = _shield_vaulted_blocks(
        body,
        r"\\begin\{(?:align\*?|equation\*?|gather\*?)\}.*?\\end\{(?:align\*?|equation\*?|gather\*?)\}",
        math_vault,
    )
    body = _convert_semantic_markup(body)
    body = _unwrap_inline_markup(body)
    body = latex_array_and_tabular_to_html(body)
    body = _unshield_vaulted_blocks(body, math_vault)
    body = _convert_choices_environment(body)
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
    body = _replace_course_material_figures(body)
    body = _format_beamer_html(body)
    body = _mathjax_safe_lt_in_tex_math(body)
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


def _strip_inline_math_from_title(text: str) -> str:
    """Remove \\( … \\) from slide titles, respecting nested parentheses."""
    result: list[str] = []
    i = 0
    while i < len(text):
        if i + 1 < len(text) and text[i : i + 2] == "\\(":
            j = i + 2
            depth = 0
            matched = False
            while j < len(text):
                if j + 1 < len(text) and text[j : j + 2] == "\\(":
                    depth += 1
                    j += 2
                    continue
                if j + 1 < len(text) and text[j : j + 2] == "\\)":
                    if depth == 0:
                        result.append(text[i + 2 : j].strip())
                        i = j + 2
                        matched = True
                        break
                    depth -= 1
                    j += 2
                    continue
                if text[j] == "(":
                    depth += 1
                elif text[j] == ")":
                    depth -= 1
                j += 1
            if not matched:
                result.append(text[i])
                i += 1
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


def _clean_slide_title(title: str) -> str:
    title = _normalize_tex_text_escapes(_unwrap_inline_markup(title))
    title = _strip_inline_math_from_title(title)
    title = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", title)
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

    _promote_fill_in_slides(slides)
    _link_question_answer_slides(slides)
    _inject_mcq_correct_answers(slides)
    _inject_grid_in_widgets(slides)
    _annotate_slides(slides)
    _finalize_all_question_slides(slides)
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
            if re.search(r"thank you|great work", fbody, re.I):
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
    checkpoint = _build_lesson_checkpoint(slides)
    knowledge_map = _build_knowledge_map(slides)
    return {
        "title": deck_title or "SAT Course Material",
        "slides": slides,
        "slide_count": len(slides),
        "lesson_path": lesson_path,
        "checkpoint": checkpoint,
        "checkpoint_count": len(checkpoint),
        "knowledge_map": knowledge_map,
        **stats,
    }
