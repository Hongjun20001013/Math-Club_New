#!/usr/bin/env python3
"""Post-process SAT_*.tex files: MCQ itemize, answer format, frame titles."""
from __future__ import annotations

import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
LABELS = ["A", "B", "C", "D", "E", "F"]


def fix_mcq_itemize(text: str) -> str:
    pattern = re.compile(
        r"\\begin\{itemize\}\[A\.\]\s*\n((?:\s*\\item[^\n]*\n)+)\s*\\end\{itemize\}",
        re.S,
    )

    def repl(m: re.Match[str]) -> str:
        items = re.findall(r"\\item\s*(.*)", m.group(1))
        lines = ["\\begin{itemize}"]
        for i, item in enumerate(items):
            if i < len(LABELS):
                lines.append(f" \\item[\\textbf{{{LABELS[i]}.}}] {item.strip()}")
        lines.append("\\end{itemize}")
        return "\n".join(lines)

    return pattern.sub(repl, text)


def fix_answer_formats(text: str) -> str:
    text = re.sub(
        r"\\textbf\{Answer:\}\s*([A-D])\.\s*$",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
        flags=re.M,
    )
    text = re.sub(
        r"\\textbf\{Correct Answer:\}\s*([A-D])\.\s+([^\\]+?)\s*$",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
        flags=re.M,
    )
    text = re.sub(
        r"\\textbf\{Correct Answer:\s*([A-D])\.\s*([^}]+)\}",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
    )
    text = re.sub(
        r"\\textbf\{Correct Answer:\s*(\d+(?:\.\d+)?)\}",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
    )
    text = re.sub(
        r"\\textbf\{Correct Answer:\s*([A-D])\s*\}",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
    )
    text = re.sub(
        r"\\textbf\{Correct Answer:\}\s*\\textcolor\{blue\}\{([A-D])\}",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
    )
    text = re.sub(
        r"\\textbf\{Correct Answer:\}\s*\\boxed\{([^}]+)\}(?!\s*\\)",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
    )
    text = re.sub(
        r"\\textbf\{Correct Answer:\}\s*\\textbf\{([A-D])\.\}\s*([^\\]+)",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
    )
    # Remove duplicate math after boxed letter (e.g. \boxed{B}\(\dfrac{12}{5}x\))
    text = re.sub(
        r"(\\textbf\{Correct Answer:\} \\( \\boxed\{[A-D]\} \\))\\([^)]+\\)",
        r"\1",
        text,
    )
    return text


def fix_answer_explanation_titles(text: str) -> str:
    return text.replace(
        r"\begin{frame}{\textbf{Answer Explanation}}",
        r"\begin{frame}{\textbf{Answer Explanation}}",
    )


def summarize_question_title(body: str, max_len: int = 55) -> str:
    body = re.sub(r"\\begin\{center\}.*?\\end\{center\}", "", body, flags=re.S)
    body = re.sub(r"\\includegraphics[^\n]*", "", body)
    body = re.sub(r"\\begin\{itemize\}.*?\\end\{itemize\}", "", body, flags=re.S)
    body = re.sub(r"\\begin\{tabular\}.*?\\end\{tabular\}", "", body, flags=re.S)
    plain = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", body)
    plain = re.sub(r"\\[a-zA-Z]+", "", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    if not plain:
        return "Practice"
    if len(plain) > max_len:
        cut = plain[:max_len].rsplit(" ", 1)[0]
        plain = cut + "…" if cut else plain[:max_len] + "…"
    return plain


def fix_generic_question_titles(text: str) -> str:
    pattern = re.compile(
        r"\\begin\{frame\}\{\\textbf\{Question\}\}\s*\n(.*?)\n\\end\{frame\}",
        re.S,
    )

    def repl(m: re.Match[str]) -> str:
        body = m.group(1)
        title = summarize_question_title(body)
        return f"\\begin{{frame}}{{\\textbf{{Question: {title}}}}}\n{body}\n\\end{{frame}}"

    text = pattern.sub(repl, text)

    # Pair Answer Explanation with preceding Question title
    frames = list(
        re.finditer(
            r"\\begin\{frame\}\{(\\textbf\{[^}]+\})\}\s*\n(.*?)\n\\end\{frame\}",
            text,
            re.S,
        )
    )
    last_q_title = None
    for i, fm in enumerate(frames):
        title_raw = fm.group(1)
        if "Question:" in title_raw:
            last_q_title = title_raw.replace("\\textbf{Question:", "").replace("}", "").strip()
        elif title_raw == "\\textbf{Answer Explanation}" and last_q_title:
            old = fm.group(0)
            new_title = f"\\textbf{{Answer Explanation: {last_q_title}}}"
            new = old.replace(
                f"\\begin{{frame}}{{{title_raw}}}",
                f"\\begin{{frame}}{{{new_title}}}",
                1,
            )
            text = text.replace(old, new, 1)

    return text


def process_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = original
    updated = fix_mcq_itemize(updated)
    updated = fix_answer_formats(updated)
    updated = fix_generic_question_titles(updated)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def main() -> None:
    targets = sorted(APP_DIR.glob("SAT_2.*.tex")) + sorted(APP_DIR.glob("SAT_3.*.tex"))
    changed = []
    for path in targets:
        if process_file(path):
            changed.append(path.name)
            print(f"Updated {path.name}")
    print(f"Done. {len(changed)} file(s) modified.")


if __name__ == "__main__":
    main()
