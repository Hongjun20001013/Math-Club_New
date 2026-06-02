#!/usr/bin/env python3
"""Batch-fix LaTeX format issues in SAT_2.* and SAT_3.* courseware."""
from __future__ import annotations

import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]


def fix_double_frame_braces(text: str) -> str:
    return re.sub(
        r"\\begin\{frame\}\{\{([^}]+)\}\}",
        lambda m: f"\\begin{{frame}}{{\\textbf{{{m.group(1).strip()}}}}}",
        text,
    )


def fix_trailing_line_breaks(text: str) -> str:
    """Remove stray \\\\ at end of prose lines (not tabular/tikz)."""
    lines = text.split("\n")
    out: list[str] = []
    in_tabular = False
    in_tikz = False
    for line in lines:
        if "\\begin{tabular" in line or "\\begin{tabular*" in line:
            in_tabular = True
        if "\\end{tabular" in line:
            in_tabular = False
        if "\\begin{tikzpicture" in line:
            in_tikz = True
        if "\\end{tikzpicture" in line:
            in_tikz = False
        if not in_tabular and not in_tikz:
            stripped = line.rstrip()
            if stripped.endswith("\\\\") and "\\item" not in stripped:
                if not any(
                    tok in stripped
                    for tok in (
                        "\\node",
                        "\\hline",
                        "&",
                        "\\foreach",
                        "tabular",
                        "\\section",
                        "\\title",
                    )
                ):
                    line = stripped[:-2].rstrip()
        out.append(line)
    return "\n".join(out)


def fix_table_env(text: str) -> str:
    text = re.sub(
        r"\\begin\{table\}\[h\]\s*\n\s*\\centering\s*\n\s*\\scriptsize[^\n]*\n\s*\\renewcommand\{\\arraystretch\}\{[^}]+\}\s*\n",
        r"\\begin{center}\n\\scriptsize\n\\renewcommand{\\arraystretch}{1.2}\n",
        text,
    )
    text = re.sub(
        r"\\begin\{table\}\[h\]\s*\n\s*\\centering\s*\n",
        r"\\begin{center}\n",
        text,
    )
    text = text.replace("\\end{table}", "\\end{center}")
    return text


def fix_item_paren_mcq(text: str) -> str:
    text = re.sub(r"\\item\[\(([A-D])\)\]", r"\\item[\\textbf{\1.}]", text)
    text = re.sub(r"\\item\[([A-D])\.\]", r"\\item[\\textbf{\1.}]", text)
    return text


def fix_final_answer(text: str) -> str:
    text = re.sub(
        r"\\textbf\{Final Answer:\}\s*\\?\(\s*\\mathbf\{([^}]+)\}\s*\\?\)",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
    )
    text = re.sub(
        r"\\textbf\{Final Answer:\}\s*\\?\(\s*\\boxed\{([^}]+)\}\s*\\?\)",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
    )
    text = re.sub(
        r"\\textbf\{Final Answer:\}\s*\\?\(\s*([^\\$]+?)\s*\\?\)\s*$",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
        flags=re.M,
    )
    text = re.sub(
        r"\\textbf\{Final Answer:\}\s*\\textcolor\{blue\}\{\s*([^}]+)\}",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
    )
    text = re.sub(
        r"\\textbf\{Final Answer:\}\s*\\?\(\s*\\boxed\{([^}]+)\}\s*\\?\)",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
    )
    text = re.sub(
        r"\\textbf\{Final Answer:\}\s*([^\\\n]+)",
        lambda m: f"\\textbf{{Correct Answer:}} \\( \\boxed{{{m.group(1).strip()}}} \\)",
        text,
    )
    return text


def fix_answer_frame_titles(text: str) -> str:
    text = text.replace(
        r"\begin{frame}{\textbf{Answer}}",
        r"\begin{frame}{\textbf{Answer Explanation}}",
    )
    return text


def fix_percent_math(text: str) -> str:
    text = text.replace("50\\times(1+x\\%)=200", "50 \\times \\left(1 + \\frac{x}{100}\\right) = 200")
    text = text.replace("(1+x\\%)", "\\left(1 + \\frac{x}{100}\\right)")
    return text


def fix_duplicate_boxed_tail(text: str) -> str:
    return re.sub(
        r"(\\textbf\{Correct Answer:\} \\( \\boxed\{[A-D]\} \\))\\([^)]+\\)",
        r"\1",
        text,
    )


def fix_broken_boxed(text: str) -> str:
    text = re.sub(
        r"\\textbf\{Closest answer:\}\s*\\boxed\{\(([A-D])\)[^}]+\}",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
        flags=re.I,
    )
    return text


def strip_size_and_layout_commands(text: str) -> str:
    """Remove standalone LaTeX size/layout commands that leak into web HTML."""
    lines = text.split("\n")
    out: list[str] = []
    skip_patterns = (
        r"\\(?:tiny|scriptsize|small|footnotesize)\s*$",
        r"\\renewcommand\{[^}]+\}\{[^}]*\}\s*$",
        r"\\setlength\{[^}]+\}\{[^}]*\}\s*$",
    )
    for line in lines:
        stripped = line.strip()
        if any(re.match(p, stripped) for p in skip_patterns):
            continue
        out.append(line)
    return "\n".join(out)


def fix_section_quotes(text: str) -> str:
    text = text.replace(
        'section{“Increased By” vs. “Decreased By}',
        'section{Increased By vs. Decreased By}',
    )
    text = text.replace(
        'textcolor{purpleblue}{“Increased By” vs. “Decreased By}',
        'textcolor{purpleblue}{Increased By vs. Decreased By}',
    )
    return text


def convert_fill_in_examples(text: str) -> str:
    """Convert duplicate Example of the Percent frames to proper Question/Answer pairs."""
    text = re.sub(
        r"\\begin\{frame\}\{\\textbf\{Example of the Percent\}\}\s*\n"
        r"\s*The number \\( a \\).*?how many times \\( b \\)\?\s*\n\\end\{frame\}\s*\n\s*"
        r"% Slide 3: Answer\s*\n"
        r"\\begin\{frame\}\{\\textbf\{Answer Explanation\}\}",
        r"\\begin{frame}{\\textbf{Question: Percent Relationship Between \\(a\\), \\(b\\), and \\(c\\)}}\n"
        r"The number \\( a \\) is \\textbf{70\\% less} than the positive number \\( b \\).\n\n"
        r"The number \\( c \\) is \\textbf{60\\% greater} than \\( a \\).\n\n"
        r"The number \\( c \\) is how many times \\( b \\)?\n"
        r"\\end{frame}\n\n"
        r"\\begin{frame}{\\textbf{Answer Explanation: Percent Relationship Between \\(a\\), \\(b\\), and \\(c\\)}}",
        text,
        flags=re.S,
    )
    text = re.sub(
        r"\\begin\{frame\}\{\\textbf\{Example of the Percent\}\}\s*\n"
        r"\s*The regular price.*?Disregard the \\\$ sign when entering your answer\.\)\}\s*\n\\end\{frame\}",
        r"\\begin{frame}{\\textbf{Question: Store Cost from Sale Price}}\n"
        r"The regular price of a shirt at a store is \\(\\$11.70\\).\n\n"
        r"The sale price of the shirt is \\textbf{80\\% less} than the regular price,\n"
        r"and the sale price is \\textbf{30\\% greater} than the store's cost for the shirt.\n\n"
        r"What was the store's cost, in dollars, for the shirt?\n\n"
        r"\\textbf{(Disregard the \\$ sign when entering your answer.)}\n"
        r"\\end{frame}",
        text,
        flags=re.S,
    )
    return text


def fix_practice_question_titles(text: str) -> str:
    replacements = [
        (
            r"\\begin\{frame\}\{Percent Greater Relationship\}",
            r"\\begin{frame}{\\textbf{Question: Percent Greater Relationship}}",
        ),
        (
            r"\\begin\{frame\}\{Percent Relationship Problem\}",
            r"\\begin{frame}{\\textbf{Question: Percent Relationship Problem}}",
        ),
        (
            r"\\begin\{frame\}\{\\textbf\{Answer Explanation: Net Percentage Increase\}\}\s*\nLet \\(x\\)",
            r"\\begin{frame}{\\textbf{Answer Explanation: Percent Greater Relationship}}\nLet \\(x\\)",
        ),
    ]
    count = 0
    for old, new in replacements:
        if "Percent Relationship Problem" in old:
            # only replace first occurrence for Town B, second gets different title via counter
            parts = text.split(old.replace("\\", "\\\\"), 1)
            if len(parts) == 2:
                text = parts[0] + new + parts[1]
                count += 1
            continue
        new_text, n = re.subn(old, new, text, count=1)
        if n:
            text = new_text
            count += n
    # Second Percent Relationship Problem answer
    text = re.sub(
        r"(\\begin\{frame\}\{\\textbf\{Question: Percent Relationship Problem\}\}[\s\S]*?"
        r"\\end\{frame\}\s*\n\s*"
        r")\\begin\{frame\}\{\\textbf\{Answer Explanation: Net Percentage Increase\}\}",
        r"\1\\begin{frame}{\\textbf{Answer Explanation: Percent of \\(c\\) that is \\(a\\)}}",
        text,
        count=1,
    )
    # Third practice pair
    text = re.sub(
        r"(\\begin\{frame\}\{\\textbf\{Question: Percent Relationship Problem\}\}[\s\S]*?160\\%[\s\S]*?"
        r"\\end\{frame\}\s*\n\s*"
        r")\\begin\{frame\}\{\\textbf\{Answer Explanation: Net Percentage Increase\}\}",
        r"\1\\begin{frame}{\\textbf{Answer Explanation: Percent of \\(z\\) that is \\(x\\)}}",
        text,
        count=1,
    )
    return text


def process_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = original
    for fn in (
        fix_double_frame_braces,
        fix_trailing_line_breaks,
        fix_table_env,
        fix_item_paren_mcq,
        fix_final_answer,
        fix_answer_frame_titles,
        fix_percent_math,
        fix_duplicate_boxed_tail,
        fix_broken_boxed,
        fix_section_quotes,
        strip_size_and_layout_commands,
    ):
        updated = fn(updated)
    if path.name == "SAT_3.2.tex":
        updated = convert_fill_in_examples(updated)
        updated = fix_practice_question_titles(updated)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def main() -> None:
    files = sorted(APP_DIR.glob("SAT_2.*.tex")) + sorted(APP_DIR.glob("SAT_3.*.tex"))
    changed = [f.name for f in files if process_file(f)]
    print(f"Updated {len(changed)} files: {', '.join(changed)}")


if __name__ == "__main__":
    main()
