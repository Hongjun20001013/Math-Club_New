#!/usr/bin/env python3
"""Build Test IX dual-module PPT (Module I specialized + Module II hard_28)."""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import APP_DIR, HARD_ANSWER_KEYS  # noqa: E402
import build_hard_question_ppt as hq  # noqa: E402

CLOSING_FRAME = hq.CLOSING_FRAME
format_answer = hq.format_answer
split_questions = hq.split_questions
transform_question_body = hq.transform_question_body

CAMP_SNAP = os.path.join(APP_DIR, "data", "sat_camp_test9.json")
QUESTION_BANK = os.path.join(APP_DIR, "data", "question_bank.json")
HARD_28 = os.path.join(APP_DIR, "banks", "hard", "hard_28.tex")
OUT_PPT = os.path.join(APP_DIR, "SAT_Hard_Question_28_PPT.tex")
OUT_PART = os.path.join(APP_DIR, "SAT_Hard_Question_Part_28.tex")


def _escape_latex_text(text: str) -> str:
    """Escape LaTeX specials outside math.

    Critical:
    - bare % comments out the rest of the line
    - bare $ starts math mode (currency like $40…$60 swallows the sentence)
    """
    out: list[str] = []
    i = 0
    while i < len(text):
        # Preserve \( ... \) and \[ ... \] math islands.
        if text.startswith("\\(", i) or text.startswith("\\[", i):
            closer = "\\)" if text.startswith("\\(", i) else "\\]"
            end = text.find(closer, i + 2)
            if end == -1:
                out.append(text[i:])
                break
            out.append(text[i : end + len(closer)])
            i = end + len(closer)
            continue
        ch = text[i]
        escaped = i > 0 and text[i - 1] == "\\"
        if ch == "%" and not escaped:
            out.append("\\%")
        elif ch == "&" and not escaped:
            out.append("\\&")
        elif ch == "#" and not escaped:
            out.append("\\#")
        elif ch == "$" and not escaped:
            out.append("\\$")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _cell_to_latex(raw: str) -> str:
    """Inline cell/content conversion (no block tables)."""
    text = html_lib.unescape(raw or "")
    text = re.sub(r"<br\s*/?>", r"\\\\", text, flags=re.I)
    text = re.sub(r"<strong>(.*?)</strong>", r"\\textbf{\1}", text, flags=re.I | re.S)
    text = re.sub(r"<em>(.*?)</em>", r"\\textit{\1}", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _escape_latex_text(text)


def html_table_to_latex(table_html: str) -> str:
    rows: list[list[str]] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.I | re.S):
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, flags=re.I | re.S)
        if cells:
            rows.append([_cell_to_latex(c) for c in cells])
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    spec = "|" + "c|" * ncols
    lines = [
        r"\begin{center}",
        rf"\begin{{tabular}}{{{spec}}}",
        r"\hline",
    ]
    for row in rows:
        padded = row + [""] * (ncols - len(row))
        lines.append(" & ".join(padded) + r" \\")
        lines.append(r"\hline")
    lines.extend([r"\end{tabular}", r"\end{center}"])
    return "\n".join(lines)


def html_img_to_latex(img_html: str) -> str:
    m = re.search(r'src=["\']([^"\']+)["\']', img_html, flags=re.I)
    if not m:
        return ""
    src = m.group(1).lstrip("/")
    # Prefer PDF/PNG siblings for Beamer when SVG is given.
    abs_src = os.path.join(APP_DIR, src)
    candidates = [src]
    base, ext = os.path.splitext(src)
    if ext.lower() == ".svg":
        for alt_ext in (".png", ".pdf"):
            alt = base + alt_ext
            if os.path.isfile(os.path.join(APP_DIR, alt)):
                candidates.insert(0, alt)
    path = candidates[0]
    return (
        "\\begin{center}\n"
        f"\\includegraphics[width=0.82\\linewidth]{{{path}}}\n"
        "\\end{center}"
    )


def html_to_latex(raw: str) -> str:
    """Convert bank HTML stems to Beamer-safe LaTeX (tables/figures preserved)."""
    text = html_lib.unescape(raw or "")

    def _table_repl(match: re.Match[str]) -> str:
        return "\n" + html_table_to_latex(match.group(0)) + "\n"

    def _img_repl(match: re.Match[str]) -> str:
        return "\n" + html_img_to_latex(match.group(0)) + "\n"

    # Keep display-math blocks; strip wrapper divs later.
    text = re.sub(
        r'<div class="stem-math-block">\s*(\\\[[\s\S]*?\\\])\s*</div>',
        r"\n\1\n",
        text,
        flags=re.I,
    )
    text = re.sub(
        r'<div class="stem-table-wrap">\s*(<table[\s\S]*?</table>)\s*</div>',
        lambda m: "\n" + html_table_to_latex(m.group(1)) + "\n",
        text,
        flags=re.I,
    )
    text = re.sub(r"<table[\s\S]*?</table>", _table_repl, text, flags=re.I)
    text = re.sub(r"<img\b[^>]*>", _img_repl, text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n\n", text, flags=re.I)
    text = re.sub(r"</p>\s*<p[^>]*>", "\n\n", text, flags=re.I)
    text = re.sub(r"</?p[^>]*>", "", text, flags=re.I)
    text = re.sub(r"</?div[^>]*>", "", text, flags=re.I)
    # Convert labeled I./II. lists BEFORE stripping spans (markers live in spans).
    def _list_repl(match: re.Match[str]) -> str:
        block = match.group(0)
        items = re.findall(
            r'<li[^>]*>\s*(?:<span class="stem-li-marker">([^<]*)</span>\s*)?'
            r'(?:<span class="stem-li-body">)?(.*?)(?:</span>)?\s*</li>',
            block,
            flags=re.I | re.S,
        )
        if not items:
            return ""
        lines = [r"\begin{enumerate}"]
        for marker, body in items:
            body_tex = _cell_to_latex(body)
            marker = (marker or "").strip()
            if marker:
                # Beamer/HTML: keep Roman labels as [I.] not bare "\item I …"
                if re.fullmatch(r"I{1,3}|IV|VI{0,3}|IX", marker):
                    marker = marker + "."
                lines.append(rf"    \item[{marker}] {body_tex}")
            else:
                lines.append(rf"    \item {body_tex}")
        lines.append(r"\end{enumerate}")
        return "\n" + "\n".join(lines) + "\n"

    text = re.sub(r"<ul\b[^>]*>[\s\S]*?</ul>", _list_repl, text, flags=re.I)
    text = re.sub(r"<ol\b[^>]*>[\s\S]*?</ol>", _list_repl, text, flags=re.I)
    text = re.sub(r"</?span[^>]*>", "", text, flags=re.I)
    text = re.sub(r"<strong>(.*?)</strong>", r"\\textbf{\1}", text, flags=re.I | re.S)
    text = re.sub(r"<em>(.*?)</em>", r"\\textit{\1}", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return _escape_latex_text(text.strip())


def choice_to_latex(raw: str) -> str:
    return _cell_to_latex(raw)


def load_module1_items() -> list[dict]:
    with open(CAMP_SNAP, "r", encoding="utf-8") as fh:
        snap = json.load(fh)
    with open(QUESTION_BANK, "r", encoding="utf-8") as fh:
        bank = json.load(fh)
    items: list[dict] = []
    for item_id in (snap.get("module1") or {}).get("item_ids") or []:
        domain, topic, idx_s = item_id.split(":")
        idx = int(idx_s)
        q = bank[domain][topic][idx]
        items.append(
            {
                "id": item_id,
                "stem": q.get("stem") or "",
                "choices": list(q.get("choices") or []),
                "correct_answer": str(q.get("correct_answer") or "").strip().upper(),
            }
        )
    if len(items) != 22:
        raise RuntimeError(f"Module I expected 22 items, got {len(items)}")
    return items


def load_module2_blocks() -> tuple[list[str], list[dict]]:
    with open(HARD_28, "r", encoding="utf-8") as fh:
        bank_tex = fh.read()
    blocks = split_questions(bank_tex)
    keys = list(HARD_ANSWER_KEYS.get("hard_28") or [])
    if len(blocks) != 22:
        raise RuntimeError(f"Module II expected 22 questions, got {len(blocks)}")
    return blocks, keys


def module_divider(title: str, subtitle: str) -> str:
    return rf"""
\begin{{frame}}
\section{{{title}}}
    \begin{{tikzpicture}}[remember picture, overlay]
        \shade[top color=softPurple, bottom color=softGray]
            (current page.north west) rectangle (current page.south east);
        \node[align=center] at (current page.center) {{
            {{\LARGE\bfseries\textcolor{{purpleblue}}{{{title}}}}} \\[0.5cm]
            {{\Large\itshape\textcolor{{lightText}}{{{subtitle}}}}}
        }};
    \end{{tikzpicture}}
\end{{frame}}
"""


def preamble() -> str:
    return r"""\documentclass{beamer}
\usepackage{graphicx}
\usepackage{xcolor}
\usepackage{tikz}
\usepackage{amsmath}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}

\definecolor{purpleblue}{RGB}{80, 80, 180}
\definecolor{novelPurple}{RGB}{98, 54, 255}
\definecolor{softPurple}{RGB}{180, 170, 255}
\definecolor{softGray}{RGB}{235, 235, 245}
\definecolor{lightText}{RGB}{90, 90, 110}

\usetheme{Madrid}
\usecolortheme{dolphin}
\graphicspath{{static/course_materials/}{static/hard/}{static/unit3/}{static/unit1/}{static/unit2/}{static/unit4/}{./}}

\setbeamerfont{title}{size=\Large,series=\bfseries}
\setbeamerfont{frametitle}{size=\LARGE,series=\bfseries}
\setbeamercolor{frametitle}{fg=white, bg=novelPurple}
\setbeamercolor{title}{fg=white, bg=purpleblue}

\title[Test IX]{\textbf{Test IX · Module I + II}}
\author{\textbf{Jack Zeng}}
\institute{\textcolor{white}{\textbf{Novel Prep}}}
\date{\today}

\begin{document}

\begin{frame}
    \titlepage
    \vfill
    \begin{flushright}
        \textcolor{purpleblue}{\Huge \textbf{Novel Prep}}
    \end{flushright}
\end{frame}

\begin{frame}
    \begin{tikzpicture}[remember picture, overlay]
        \shade[top color=softPurple, bottom color=softGray]
            (current page.north west) rectangle (current page.south east);
        \node[align=center] at (current page.center) {
            {\Huge\bfseries\textcolor{purpleblue}{Novel Prep}} \\[0.5cm]
            {\Large\itshape\textcolor{lightText}{Phase 3 · Mock Exam Training}}
        };
    \end{tikzpicture}
\end{frame}

\begin{frame}{Overview}
    \tableofcontents
\end{frame}

\begin{frame}
\section{Test IX}
    \begin{tikzpicture}[remember picture, overlay]
        \shade[top color=softPurple, bottom color=softGray]
            (current page.north west) rectangle (current page.south east);
        \node[align=center] at (current page.center) {
            {\LARGE\bfseries\textcolor{purpleblue}{Test IX}} \\[0.5cm]
            {\Large\itshape\textcolor{lightText}{44 questions · Module I + Module II}}
        };
    \end{tikzpicture}
\end{frame}
"""


def m1_question_frame(n: int, item: dict) -> str:
    stem = html_to_latex(item["stem"])
    letters = "ABCD"
    choice_lines = []
    for i, choice in enumerate(item["choices"][:4]):
        letter = letters[i]
        choice_lines.append(rf"    \item[{letter}.] {choice_to_latex(str(choice))}")
    choices_tex = "\n".join(choice_lines)
    body = stem
    if choices_tex:
        body = (
            body.rstrip()
            + "\n\\vspace{0.35cm}\n\\begin{enumerate}\n"
            + choices_tex
            + "\n\\end{enumerate}\n"
        )
    ans = item["correct_answer"] or "?"
    # Keep frametitles as "Question N" / "Answer N" so beamer_parser
    # classifies kinds correctly; Module I/II come from \\section{} dividers.
    return (
        f"\n% --- Module I Question {n} ---\n"
        f"\\begin{{frame}}{{Question {n}}}\n\\small\n{body}\n\\end{{frame}}\n"
        f"\\begin{{frame}}{{Answer {n}}}\n\\small\n"
        f"\\textbf{{Correct Answer:}} {ans}\n\\end{{frame}}\n"
    )


def m2_question_frame(n: int, block: str, meta: dict) -> str:
    body = transform_question_body(block)
    answer_tex = format_answer(meta) if meta else "\\textbf{Answer pending}"
    return (
        f"\n% --- Module II Question {n} ---\n"
        f"\\begin{{frame}}{{Question {n}}}\n\\small\n{body}\n\\end{{frame}}\n"
        f"\\begin{{frame}}{{Answer {n}}}\n\\small\n{answer_tex}\n\\end{{frame}}\n"
    )


def build_ppt() -> str:
    m1 = load_module1_items()
    m2_blocks, m2_keys = load_module2_blocks()
    parts = [preamble()]
    parts.append(module_divider("Module I", "22 Specialized Training questions"))
    for i, item in enumerate(m1, start=1):
        parts.append(m1_question_frame(i, item))
    parts.append(module_divider("Module II", "22 Hard Problem Drill questions"))
    for i, block in enumerate(m2_blocks, start=1):
        meta = m2_keys[i - 1] if i - 1 < len(m2_keys) else {}
        parts.append(m2_question_frame(i, block, meta))
    parts.append("\n")
    parts.append(CLOSING_FRAME)
    parts.append("\n\n\\end{document}\n")
    return "".join(parts)


def part_preamble() -> str:
    return r"""\documentclass[12pt]{article}
\everymath{\displaystyle}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usepackage{amsmath}
\usepackage[margin=1in]{geometry}
\usepackage[most]{tcolorbox}
\usepackage{graphicx}
\usepackage{tikz}
\usepackage{enumitem}
\usepackage{fancyhdr}
\usepackage{pifont}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{tabularx}
\newcounter{questionnum}
\setcounter{questionnum}{0}
\definecolor{novelblue}{RGB}{70,60,150}
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0pt}
\fancyhead[L]{\color{novelblue}\textbf{Novel Prep}}
\fancyhead[C]{\color{novelblue}\textbf{SAT Preparation · Test IX}}
\fancyhead[R]{\color{novelblue}\textbf{Jack Zeng}}
\newcommand{\markforreview}{
  \stepcounter{questionnum}
  \begin{tikzpicture}[scale=1.05]
    \fill[black] (0,0) rectangle (0.8,0.6);
    \node[white, font=\bfseries\large] at (0.4,0.3) {\thequestionnum};
    \fill[gray!10] (0.8,0) rectangle (14.5,0.6);
    \node[anchor=west, font=\small] at (1.2,0.3) {\ding{72} \hspace{2pt}Mark for Review};
    \draw[thick, rounded corners=3pt] (13.5,0.12) rectangle (14.5,0.48);
    \node[font=\bfseries\normalsize] at (14.0,0.3) {ABC};
  \end{tikzpicture}
}
\newcommand{\choicebox}[2]{%
  \begin{tcolorbox}[colback=white,colframe=novelblue,boxrule=0.5pt,arc=4pt,left=6pt,right=6pt,top=6pt,bottom=6pt,width=\linewidth]
  \textbf{#1.} \ #2
  \end{tcolorbox}
}
\begin{document}
\begin{center}
{\LARGE\bfseries Test IX · Module I + Module II}\\[0.4em]
{\large 44 questions · Digital SAT Math mock}
\end{center}
\vspace{1em}
"""


def build_part() -> str:
    m1 = load_module1_items()
    m2_blocks, _keys = load_module2_blocks()
    parts = [part_preamble()]
    parts.append(r"\section*{Module I · Specialized Training}" + "\n")
    for item in m1:
        stem = html_to_latex(item["stem"])
        parts.append("\\noindent\\markforreview\\\\\n")
        parts.append(stem + "\n\n")
        for i, choice in enumerate(item["choices"][:4]):
            letter = "ABCD"[i]
            parts.append(
                f"\\choicebox{{{letter}}}{{{choice_to_latex(str(choice))}}}\n"
            )
        parts.append("\\vspace{1.2em}\n")
    parts.append(r"\newpage" + "\n")
    parts.append(r"\section*{Module II · Hard Problem Drill}" + "\n")
    # Reset visual numbers for Module II while keeping global counter continuous
    # (Digital SAT uses 1–22 per module; worksheet uses continuous 1–44 for printing).
    for block in m2_blocks:
        body = block
        body = re.sub(r"\\newpage\s*", "", body)
        parts.append("\\noindent\\markforreview\\\\\n")
        parts.append(body.strip() + "\n\n")
        parts.append("\\vspace{1.2em}\n")
    parts.append("\n\\end{document}\n")
    return "".join(parts)


def _extract_div_by_class(html: str, class_name: str) -> tuple[str, str | None]:
    """Return (html_without_first_block, block) for a div with the given class."""
    pat = re.compile(
        rf'(<div\b[^>]*class="[^"]*\b{re.escape(class_name)}\b[^"]*"[^>]*>)',
        flags=re.I,
    )
    m = pat.search(html)
    if not m:
        return html, None
    start = m.start()
    i = m.end()
    depth = 1
    while i < len(html) and depth:
        open_m = re.search(r"<div\b", html[i:], flags=re.I)
        close_m = re.search(r"</div>", html[i:], flags=re.I)
        if not close_m:
            break
        open_pos = open_m.start() if open_m else None
        close_pos = close_m.start()
        if open_pos is not None and open_pos < close_pos:
            depth += 1
            i += open_pos + 4
        else:
            depth -= 1
            i += close_pos + len("</div>")
    block = html[start:i]
    return html[:start] + html[i:], block


def patch_course_materials_module1() -> None:
    """Restore bank HTML stems for Module I so tables/figures render 100% on web."""
    materials_path = os.path.join(APP_DIR, "data", "course_materials.json")
    if not os.path.isfile(materials_path):
        print("Skip stem patch: course_materials.json missing")
        return
    with open(materials_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    m1_items = load_module1_items()
    patched = 0
    for material in payload.get("materials") or []:
        if material.get("slug") != "hard-question-28":
            continue
        m1_qs = [
            s
            for s in (material.get("slides") or [])
            if s.get("kind") == "question" and str(s.get("section") or "") == "Module I"
        ]
        if len(m1_qs) != 22:
            raise RuntimeError(f"Expected 22 Module I question slides, got {len(m1_qs)}")
        for slide, item in zip(m1_qs, m1_items):
            html = slide.get("html") or ""
            # Keep interactive MCQ block; replace stem body with bank HTML.
            interact = None
            for cls in ("cm-question-interact", "cm-mcq-interactive"):
                html2, block = _extract_div_by_class(html, cls)
                if block:
                    # Prefer outer interact wrapper when present.
                    if cls == "cm-question-interact":
                        interact = block
                        html = html2
                        break
                    interact = (
                        f'<div class="cm-question-interact">{block}</div>'
                    )
                    html = html2
            # Drop auto strategy chips — beamer heuristics often mismatch specialized stems.
            _html, _strat = _extract_div_by_class(html, "cm-strategy-chip")
            if _strat:
                html = _html
            role = (
                '<div class="cm-slide-role cm-slide-role--question">'
                '<span class="cm-slide-role-label">Question Practice</span>'
                "<strong>Try it first</strong>"
                "<p>Pause and solve before checking the answer or worked solution.</p>"
                "</div>"
            )
            bank_stem = item["stem"]
            # Normalize figure img paths for the course viewer.
            bank_stem = re.sub(
                r'src="(?!/|https?:)',
                'src="/',
                bank_stem,
            )
            # Keep percent signs visible even if content is later LaTeX-sanitized.
            bank_stem = re.sub(r"(?<!\\)%", "&#37;", bank_stem)
            # Currency as \(\$220\) — HTML &#36; becomes bare $ in the DOM and
            # pairs into math ($220…$400 swallows the sentence into italics).
            bank_stem = re.sub(r"&#36;(\d[\d,]*)", r"\\(\\$\1\\)", bank_stem)
            bank_stem = re.sub(r"(?<!\\)\$(\d[\d,]*)", r"\\(\\$\1\\)", bank_stem)
            # Normalize Roman list markers to "I." / "II."
            bank_stem = re.sub(
                r'(<span class="stem-li-marker">)\s*(I{1,3}|IV|VI{0,3}|IX)\.?\s*(</span>)',
                r"\1\2.\3",
                bank_stem,
                flags=re.I,
            )
            if not bank_stem.startswith("<"):
                bank_stem = f"<p>{bank_stem}</p>"
            stem_inner = f"{role}{bank_stem}"
            if interact:
                slide["html"] = (
                    '<div class="cm-question-workspace">'
                    f'<div class="cm-question-stem">{stem_inner}</div>'
                    f"{interact}"
                    "</div>"
                )
            else:
                slide["html"] = (
                    '<div class="cm-question-workspace">'
                    f'<div class="cm-question-stem">{stem_inner}</div>'
                    "</div>"
                )
            # Ensure answer key from bank.
            slide["correct_choice"] = item["correct_answer"]
            patched += 1
        material["title"] = "Test IX · Module I + II"
        material["deck_title"] = "Test IX · Module I + II"
        material["section"] = "Test IX"
        break
    with open(materials_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"Patched Module I stems in course_materials.json ({patched} questions)")


def _sanitize_course_html(html: str) -> str:
    """Fix common LaTeX leftovers that leak into the web viewer."""
    if not html:
        return html
    from latex_parser import _convert_latex_lists

    # Text emphasis left as raw TeX in bank/PPT HTML.
    html = re.sub(r"\\textbf\{([^{}]*)\}", r"<strong>\1</strong>", html)
    html = re.sub(r"\\(?:textit|emph)\{([^{}]*)\}", r"<em>\1</em>", html)
    # Currency: entities / bare $ → \(\$N\)
    html = re.sub(r"&#36;(\d[\d,]*)", r"\\(\\$\1\\)", html)
    html = re.sub(r"(?<!\\)\$(\d[\d,]*)", r"\\(\\$\1\\)", html)
    # Orphan list items
    if r"\item" in html:
        html = _convert_latex_lists(html)
    return html


def sanitize_hard28_slides() -> None:
    """Run HTML sanitizer across the full Test IX deck."""
    materials_path = os.path.join(APP_DIR, "data", "course_materials.json")
    with open(materials_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    fixed = 0
    for material in payload.get("materials") or []:
        if material.get("slug") != "hard-question-28":
            continue
        for slide in material.get("slides") or []:
            before = slide.get("html") or ""
            after = _sanitize_course_html(before)
            # Drop auto strategy chips — beamer heuristics often mismatch stems.
            after2, strat = _extract_div_by_class(after, "cm-strategy-chip")
            if strat:
                after = after2
            if after != before:
                slide["html"] = after
                fixed += 1
        break
    with open(materials_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"Sanitized hard-question-28 slides ({fixed} changed)")


def audit_test_ix_latex() -> None:
    """Fail fast on LaTeX/render bugs across Test IX Module I + II."""
    materials_path = os.path.join(APP_DIR, "data", "course_materials.json")
    with open(materials_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    material = next(
        m for m in payload["materials"] if m.get("slug") == "hard-question-28"
    )
    errors: list[str] = []
    m1_qs = [
        s
        for s in material["slides"]
        if s.get("kind") == "question" and s.get("section") == "Module I"
    ]
    for i, slide in enumerate(m1_qs, start=1):
        html = slide.get("html") or ""
        plain = re.sub(r"<[^>]+>", " ", html)
        plain = re.sub(r"\s+", " ", plain)
        if re.search(r"x\)\s*\\?\(?\\?displaystyle f\(x\)\)?\s*\d", plain) or re.search(
            r"f\(x\)\s*\d{5,}", plain
        ):
            errors.append(f"M1Q{i}: flattened table text still present")
        if "the table shows" in plain.lower() and "stem-table" not in html:
            errors.append(f"M1Q{i}: mentions table but missing stem-table")
        if "histograms shown" in plain.lower() and "<img" not in html:
            errors.append(f"M1Q{i}: missing histogram image")
        if "which is 5" in plain and "daily allowance" not in plain:
            errors.append(f"M1Q{i}: potassium stem truncated after 5%")
        if re.search(r"displaystyle\s+\d+\s+(per\s+unit|for\s+the)", html):
            errors.append(f"M1Q{i}: currency $ swallowed into math mode")
        if re.search(r"&#36;\d|\$\d", html) and re.search(
            r"(per unit|repair|dollar)", html, flags=re.I
        ):
            if "\\(\\$" not in html:
                errors.append(f"M1Q{i}: currency not in safe \\(\\$N\\) form")
        if r"\item" in html:
            errors.append(f"M1Q{i}: raw \\item leaked into HTML")
        if re.search(r"\\(?:textit|textbf|emph)\{", html):
            errors.append(f"M1Q{i}: raw \\textit/\\textbf leaked into HTML")
        if str(slide.get("correct_choice") or "") not in "ABCD":
            errors.append(f"M1Q{i}: bad correct_choice {slide.get('correct_choice')}")

    for slide in material.get("slides") or []:
        html = slide.get("html") or ""
        tag = f"{slide.get('section')} {slide.get('kind')} {slide.get('title')}"
        if r"\item" in html:
            errors.append(f"{tag}: raw \\item")
        if re.search(r"\\(?:textit|textbf|emph)\{", html):
            errors.append(f"{tag}: raw text emphasis command")
        if re.search(r"displaystyle\s+\d+\s+(per\s+unit|for\s+the|hours)", html):
            errors.append(f"{tag}: currency swallowed into math")
        # Leftover TeX outside math islands
        no_math = re.sub(r"\\\([\s\S]*?\\\)", " ", html)
        no_math = re.sub(r"\\\[[\s\S]*?\\\]", " ", no_math)
        no_math_plain = re.sub(r"<[^>]+>", " ", no_math)
        for cmd in (r"\vspace", r"\begin{", r"\noindent", r"\choicebox"):
            if cmd in no_math_plain:
                errors.append(f"{tag}: raw {cmd}")

    if errors:
        raise RuntimeError("Test IX LaTeX audit failed:\n- " + "\n- ".join(errors))
    print("Test IX LaTeX audit: OK")


def main() -> None:
    ppt = build_ppt()
    with open(OUT_PPT, "w", encoding="utf-8") as fh:
        fh.write(ppt)
    print(f"Wrote {OUT_PPT}")
    part = build_part()
    with open(OUT_PART, "w", encoding="utf-8") as fh:
        fh.write(part)
    print(f"Wrote {OUT_PART}")
    q_frames = len(re.findall(r"\\begin\{frame\}\{Question \d+\}", ppt))
    print(f"PPT question frames: {q_frames}")
    # Spot-check Q3 table survived in TeX
    if "1-6420364" in ppt:
        raise RuntimeError("PPT still contains smashed table token 1-6420364")
    if r"\begin{tabular}" not in ppt:
        raise RuntimeError("PPT missing LaTeX tabular for Module I tables")
    print("PPT table check: OK")


if __name__ == "__main__":
    main()
    # Rebuild + patch web deck when run as a one-shot fix.
    import subprocess

    subprocess.check_call(
        [sys.executable, os.path.join(ROOT, "scripts", "build_course_materials.py")],
        cwd=ROOT,
    )
    patch_course_materials_module1()
    sanitize_hard28_slides()
    audit_test_ix_latex()
