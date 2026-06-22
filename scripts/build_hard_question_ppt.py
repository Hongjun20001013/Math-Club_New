#!/usr/bin/env python3
"""Generate SAT_Hard_Question_N_PPT.tex from banks/hard/hard_N.tex."""

from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import APP_DIR, HARD_ANSWER_KEYS  # noqa: E402

CLOSING_FRAME = r"""
\begin{frame}{}
    \begin{tikzpicture}[remember picture, overlay]
        \shade[top color=novelPurple!40, bottom color=white]
            (current page.north west) rectangle (current page.south east);
        \fill[white, opacity=0.15] (current page.center) circle (5cm);
        \foreach \x in {1,2,3,4,5} {
            \fill[novelPurple, opacity=0.12] (rand*10-5, rand*7-3.5) circle (0.1+\x*0.05);
        }
    \end{tikzpicture}
    \centering
    \vspace{5em}
    {\Huge \textbf{\textcolor{novelPurple}{Thank You!}}} \\[1em]
    {\large \textcolor{gray}{We appreciate your time and focus.}} \\[3em]
    {\LARGE \textbf{\textcolor{novelPurple}{\textsf{Novel Prep}}}}
    \vfill
\end{frame}
""".strip()


def read_braced_content(text: str, start: int) -> tuple[str, int] | None:
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    i = start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i], i + 1
        i += 1
    return None


def first_choicebox_span(text: str) -> tuple[int, int, str, str] | None:
    marker = "\\choicebox{"
    idx = text.find(marker)
    if idx == -1:
        return None
    pos = idx + len(marker)
    letter_end = text.find("}", pos)
    if letter_end == -1:
        return None
    letter = text[pos:letter_end].strip()
    pos = letter_end + 1
    while pos < len(text) and text[pos].isspace():
        pos += 1
    if pos >= len(text) or text[pos] != "{":
        return None
    parsed = read_braced_content(text, pos)
    if not parsed:
        return None
    content, end = parsed
    return idx, end, letter, content.strip()


def extract_all_choiceboxes(text: str) -> tuple[str, list[tuple[str, str]]]:
    out = text
    choices: list[tuple[str, str]] = []
    while True:
        span = first_choicebox_span(out)
        if not span:
            break
        i, j, letter, content = span
        choices.append((letter, content))
        out = out[:i] + out[j:]
    return out, choices


def transform_question_body(body: str) -> str:
    out = body
    out = re.sub(r"\\newpage\s*", "", out)
    out = re.sub(r"\\vspace\{[^}]+\}\s*", "", out)
    out, choices = extract_all_choiceboxes(out)
    if choices:
        items = "\n".join(
            rf"    \item[{letter}.] {content.strip()}" for letter, content in choices
        )
        out = out.rstrip() + "\n\\vspace{0.35cm}\n\\begin{enumerate}\n" + items + "\n\\end{enumerate}\n"

    def fig_repl(m: re.Match[str]) -> str:
        width = m.group(1) or "0.48\\linewidth"
        fname = m.group(2).strip()
        return rf"\includegraphics[width={width}]{{{fname}}}"

    out = re.sub(
        r"\\includegraphics(?:\[width=([^\]]+)\])?\{([^}]+)\}",
        fig_repl,
        out,
    )
    if r"\includegraphics" in out and r"\begin{center}" not in out:
        out = re.sub(
            r"(\\includegraphics\[[^\]]+\]\{[^}]+\})",
            r"\\begin{center}\n    \1\n\\end{center}",
            out,
            count=1,
        )
    return out.strip()


def split_questions(bank_tex: str) -> list[str]:
    parts = re.split(r"\\noindent\\markforreview", bank_tex)
    blocks: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("\\vspace"):
            lines = part.split("\n", 1)
            part = lines[1].strip() if len(lines) > 1 else ""
        if part:
            blocks.append(part)
    return blocks


def format_answer(meta: dict) -> str:
    ans = str(meta.get("correct_answer") or "").strip()
    if re.fullmatch(r"[A-D]", ans, flags=re.I):
        return f"\\textbf{{Correct Answer:}} {ans.upper()}"
    escaped = ans.replace(",", ", ")
    if "/" in escaped and not escaped.startswith("\\"):
        parts = escaped.split("/")
        if len(parts) == 2 and parts[0].lstrip("-").isdigit() and parts[1].isdigit():
            escaped = rf"\dfrac{{{parts[0]}}}{{{parts[1]}}}"
    return f"\\textbf{{Final Answer:}} $\\boxed{{{escaped}}}$"


def preamble(set_num: int, short_title: str) -> str:
    return rf"""\documentclass{{beamer}}
\usepackage{{graphicx}}
\usepackage{{xcolor}}
\usepackage{{tikz}}
\usepackage{{amsmath}}

\definecolor{{purpleblue}}{{RGB}}{{80, 80, 180}}
\definecolor{{novelPurple}}{{RGB}}{{98, 54, 255}}
\definecolor{{softPurple}}{{RGB}}{{180, 170, 255}}
\definecolor{{softGray}}{{RGB}}{{235, 235, 245}}
\definecolor{{lightText}}{{RGB}}{{90, 90, 110}}

\usetheme{{Madrid}}
\usecolortheme{{dolphin}}
\graphicspath{{{{static/course_materials/}}{{static/hard/}}{{./}}}}

\setbeamerfont{{title}}{{size=\Large,series=\bfseries}}
\setbeamerfont{{frametitle}}{{size=\LARGE,series=\bfseries}}
\setbeamercolor{{frametitle}}{{fg=white, bg=novelPurple}}
\setbeamercolor{{title}}{{fg=white, bg=purpleblue}}

\title[{short_title}]{{\textbf{{SAT Hard Question\\ Set {set_num}}}}}
\author{{\textbf{{Jack Zeng}}}}
\institute{{\textcolor{{white}}{{\textbf{{Novel Prep}}}}}}
\date{{\today}}

\begin{{document}}

\begin{{frame}}
    \titlepage
    \vfill
    \begin{{flushright}}
        \textcolor{{purpleblue}}{{\Huge \textbf{{Novel Prep}}}}
    \end{{flushright}}
\end{{frame}}

\begin{{frame}}
    \begin{{tikzpicture}}[remember picture, overlay]
        \shade[top color=softPurple, bottom color=softGray]
            (current page.north west) rectangle (current page.south east);
        \node[align=center] at (current page.center) {{
            {{\Huge\bfseries\textcolor{{purpleblue}}{{Novel Prep}}}} \\[0.5cm]
            {{\Large\itshape\textcolor{{lightText}}{{Phase 2 · Hard Question Practice}}}}
        }};
    \end{{tikzpicture}}
\end{{frame}}

\begin{{frame}}{{Overview}}
    \tableofcontents
\end{{frame}}

\begin{{frame}}
\section{{Hard Question Set {set_num}}}
    \begin{{tikzpicture}}[remember picture, overlay]
        \shade[top color=softPurple, bottom color=softGray]
            (current page.north west) rectangle (current page.south east);
        \node[align=center] at (current page.center) {{
            {{\LARGE\bfseries\textcolor{{purpleblue}}{{Hard Question Set {set_num}}}}} \\[0.5cm]
            {{\Large\itshape\textcolor{{lightText}}{{{{QUESTION_COUNT_LABEL}}}}}}
        }};
    \end{{tikzpicture}}
\end{{frame}}
"""


def build_set(set_num: int) -> str:
    topic = f"hard_{set_num}"
    bank_path = os.path.join(APP_DIR, "banks", "hard", f"{topic}.tex")
    if not os.path.isfile(bank_path):
        raise FileNotFoundError(bank_path)

    with open(bank_path, "r", encoding="utf-8") as f:
        bank_tex = f.read()

    questions = split_questions(bank_tex)
    keys = HARD_ANSWER_KEYS.get(topic) or []
    if len(keys) != len(questions):
        print(
            f"Warning: hard_{set_num} has {len(questions)} questions "
            f"but {len(keys)} answer keys"
        )

    count = len(questions)
    label = f"{count} SAT-style challenge problem{'s' if count != 1 else ''}"
    short_title = f"SAT Hard Question {set_num}"
    parts = [preamble(set_num, short_title).replace("{QUESTION_COUNT_LABEL}", label)]

    for i, block in enumerate(questions, start=1):
        body = transform_question_body(block)
        parts.append(f"\n% --- Question {i} ---\n")
        parts.append(f"\\begin{{frame}}{{Question {i}}}\n\\small\n{body}\n\\end{{frame}}\n")
        meta = keys[i - 1] if i - 1 < len(keys) else {}
        answer_tex = format_answer(meta) if meta else "\\textbf{Answer pending}"
        parts.append(
            f"\\begin{{frame}}{{Answer {i}}}\n\\small\n{answer_tex}\n\\end{{frame}}\n"
        )

    parts.append("\n")
    parts.append(CLOSING_FRAME)
    parts.append("\n\n\\end{document}\n")
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sets", nargs="*", type=int, help="Set numbers (default 4-9)")
    parser.add_argument("--all", action="store_true", help="Regenerate sets 1-9")
    args = parser.parse_args()

    if args.all:
        sets = list(range(1, 10))
    elif args.sets:
        sets = args.sets
    else:
        sets = list(range(4, 10))

    for n in sets:
        tex = build_set(n)
        out_path = os.path.join(APP_DIR, f"SAT_Hard_Question_{n}_PPT.tex")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(tex)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
