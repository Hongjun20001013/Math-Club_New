#!/usr/bin/env python3
"""Fetch Overleaf courseware from GitHub SAT_- repo and normalize to Novel Prep format."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = APP_DIR / "static" / "course_materials"
GITHUB_RAW = "https://raw.githubusercontent.com/Hongjun20001013/SAT_-/main"
MANIFEST_PATH = APP_DIR / "data" / "course_materials_manifest.json"

def build_preamble(title_short: str, title_line: str) -> str:
    return f"""\\documentclass{{beamer}}
\\usepackage{{graphicx}}
\\usepackage{{xcolor}}
\\usepackage{{tikz}}
\\usepackage{{amsmath}}

% 自定义颜色
\\definecolor{{purpleblue}}{{RGB}}{{80, 80, 180}}
\\definecolor{{lightgray}}{{RGB}}{{230, 230, 230}}
\\definecolor{{novelPurple}}{{RGB}}{{98, 54, 255}}
\\definecolor{{darkgray}}{{RGB}}{{50, 50, 50}}
\\definecolor{{softPurple}}{{RGB}}{{180, 170, 255}}
\\definecolor{{softGray}}{{RGB}}{{235, 235, 245}}
\\definecolor{{lightText}}{{RGB}}{{90, 90, 110}}
\\graphicspath{{{{static/course_materials/}}{{./}}}}

% 主题设置
\\usetheme{{Madrid}}
\\usecolortheme{{dolphin}}

\\setbeamerfont{{title}}{{size=\\Large,series=\\bfseries}}
\\setbeamerfont{{frametitle}}{{size=\\LARGE,series=\\bfseries}}
\\setbeamercolor{{frametitle}}{{fg=white, bg=novelPurple}}
\\setbeamercolor{{title}}{{fg=white, bg=purpleblue}}

\\title[{title_short}]{{\\textbf{{{title_line}}}}}
\\author{{\\textbf{{Jack Zeng}}}}
\\institute{{\\textcolor{{white}}{{\\textbf{{Novel Prep}}}}}}
\\date{{\\today}}

\\begin{{document}}
"""

CLOSING = r"""
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

\end{document}
"""

LESSONS = [
    {
        "section": "2.3.1",
        "github": "2.3.1_Rational and Polynomial.tex",
        "output": "SAT_2.3.1.tex",
        "title_short": "SAT Unit 2.3.1",
        "title_line": r"SAT Unit 2.3.1 \\Rational and Polynomial Functions",
        "slug": "2-3-1-rational-polynomial",
    },
    {
        "section": "2.3.2",
        "github": "2.3.2_Exponential Function.tex",
        "output": "SAT_2.3.2.tex",
        "title_short": "SAT Unit 2.3.2",
        "title_line": r"SAT Unit 2.3.2 \\Exponential Functions",
        "slug": "2-3-2-exponential-functions",
    },
    {
        "section": "3.1",
        "github": "3.1_Ratio_Rates.tex",
        "output": "SAT_3.1.tex",
        "title_short": "SAT Unit 3.1",
        "title_line": r"SAT Unit 3.1 \\Ratios, Rates, and Units",
        "slug": "3-1-ratios-rates",
    },
    {
        "section": "3.2",
        "github": "3.2_Percent.tex",
        "output": "SAT_3.2.tex",
        "title_short": "SAT Unit 3.2",
        "title_line": r"SAT Unit 3.2 \\Percentages",
        "slug": "3-2-percent",
    },
    {
        "section": "3.3",
        "github": "3.3_One Variable Data.tex",
        "output": "SAT_3.3.tex",
        "title_short": "SAT Unit 3.3",
        "title_line": r"SAT Unit 3.3 \\One-Variable Data",
        "slug": "3-3-one-variable-data",
    },
    {
        "section": "3.4",
        "github": "3.4_Model and Scatterplots.tex",
        "output": "SAT_3.4.tex",
        "title_short": "SAT Unit 3.4",
        "title_line": r"SAT Unit 3.4 \\Models and Scatterplots",
        "slug": "3-4-models-scatterplots",
    },
    {
        "section": "3.5",
        "github": "3.5_Probability.tex",
        "output": "SAT_3.5.tex",
        "title_short": "SAT Unit 3.5",
        "title_line": r"SAT Unit 3.5 \\Probability",
        "slug": "3-5-probability",
    },
    {
        "section": "3.6",
        "github": "3.6 Inference from sample statistics and margin or error.tex",
        "output": "SAT_3.6.tex",
        "title_short": "SAT Unit 3.6",
        "title_line": r"SAT Unit 3.6 \\Inference and Margin of Error",
        "slug": "3-6-inference-margin-of-error",
    },
    {
        "section": "3.7",
        "github": "3.7 Evaluating Statistical Claims.tex",
        "output": "SAT_3.7.tex",
        "title_short": "SAT Unit 3.7",
        "title_line": r"SAT Unit 3.7 \\Evaluating Statistical Claims",
        "slug": "3-7-statistical-claims",
    },
]


def fetch_url(url: str) -> bytes:
    proc = subprocess.run(
        ["curl", "-fsSL", url],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to fetch {url}: {proc.stderr.decode()}")
    return proc.stdout


def extract_body(source: str) -> str:
    m = re.search(r"\\begin\{document\}(.*)\\end\{document\}", source, re.S)
    if not m:
        raise ValueError("No document body found")
    return m.group(1).strip()


def convert_dollars(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "$" and (i == 0 or text[i - 1] != "\\"):
            j = i + 1
            while j < len(text):
                if text[j] == "$" and text[j - 1] != "\\":
                    inner = text[i + 1 : j]
                    out.append(f"\\({inner}\\)")
                    i = j + 1
                    break
                j += 1
            else:
                out.append(text[i])
                i += 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def normalize_body(body: str) -> str:
    text = body

    # Remove erroneous literal \n (not \node, \new, \ne, etc.)
    text = re.sub(r"(?<![\\a-zA-Z])\\n(?![a-zA-Z])", "\n", text)

    text = convert_dollars(text)
    text = re.sub(r"\\begin\{enumerate\}", r"\\begin{itemize}", text)
    text = re.sub(r"\\end\{enumerate\}", r"\\end{itemize}", text)
    text = re.sub(r"\\item\[([A-D])\.\]", r"\\item[\\textbf{\1.}]", text)
    text = re.sub(r"\\item\[([A-D])\)\]", r"\\item[\\textbf{\1.}]", text)
    text = re.sub(r"\\item\[([A-D])\]", r"\\item[\\textbf{\1.}]", text)
    text = re.sub(r"\\item \[([A-D])\]", r"\\item[\\textbf{\1.}]", text)
    text = re.sub(r"^([A-D])\) ", r"\\item[\\textbf{\1.}] ", text, flags=re.M)

    text = text.replace("\\section{Practices}", "\\section{Practice}")
    text = re.sub(r"\s*\\pause\s*", "\n", text)
    text = re.sub(r"\\textcolor\{novelGreen\}\{([^}]*)\}", r"\1", text)
    text = text.replace("✅", "").replace("❌", "")
    text = text.replace("、", "")

    # Frame titles
    text = re.sub(
        r"\\begin\{frame\}\{Question\}",
        r"\\begin{frame}{\\textbf{Question}}",
        text,
    )
    text = re.sub(
        r"\\begin\{frame\}\{Answer\}",
        r"\\begin{frame}{\\textbf{Answer Explanation}}",
        text,
    )
    text = re.sub(
        r"\\begin\{frame\}\{Solution:([^}]*)\}",
        r"\\begin{frame}{\\textbf{Answer Explanation:\1}}",
        text,
    )
    text = re.sub(
        r"\\begin\{frame\}\{\\textbf\{Answer and Explanation\}\}",
        r"\\begin{frame}{\\textbf{Answer Explanation}}",
        text,
    )
    text = re.sub(
        r"\\textbf\{Correct answer:\}\s*([A-D])\s*$",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
        flags=re.M | re.I,
    )
    text = re.sub(
        r"\\textbf\{Correct Answer:\}\s*\\?\(\\boxed\{([^}]+)\}\s*\)\}",
        r"\\textbf{Correct Answer:} \\( \\boxed{\1} \\)",
        text,
    )

    # Strip concept-frame \small at frame open (keep in long answer slides ok)
    text = re.sub(
        r"(\\begin\{frame\}\{[^}]*\})\n\\small\n",
        r"\1\n    ",
        text,
    )

    return text


def strip_duplicate_intro(body: str) -> str:
    """Remove the first three Beamer frames (title, brand, overview)."""
    body = body.lstrip()
    for _ in range(3):
        body = re.sub(
            r"^(?:\s*%[^\n]*\n)*\s*\\begin\{frame\}(?:\{[^}]*\})?\s.*?\\end\{frame\}\s*",
            "",
            body,
            count=1,
            flags=re.S,
        )
    return body.lstrip()


def standard_intro() -> str:
    return r"""
% --- Title Slide ---
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
        \fill[white, opacity=0.3] (current page.center) circle (4cm);
        \node[align=center] at (current page.center) {
            {\Huge\bfseries\textcolor{purpleblue}{Novel Prep}} \\[0.5cm]
            {\Large\itshape\textcolor{lightText}{Excellence in SAT Prep}}
        };
        \foreach \x in {1,2,3,4,5} {
            \fill[purpleblue, opacity=0.2] (rand*10-5, rand*7-3.5) circle (0.1+\x*0.05);
        }
    \end{tikzpicture}
\end{frame}

\begin{frame}{Overview}
    \tableofcontents
\end{frame}
"""


def ensure_opening_slides(body: str) -> str:
    body = strip_duplicate_intro(body)
    return standard_intro() + "\n" + body


def ensure_closing(body: str) -> str:
    # Remove only the trailing Thank You slide, not content before it.
    idx = body.rfind("Thank You!")
    if idx != -1:
        start = body.rfind("\\begin{frame}", 0, idx)
        end = body.find("\\end{frame}", idx)
        if start != -1 and end != -1:
            body = body[:start] + body[end + len("\\end{frame}") :]
    return body.rstrip() + "\n" + CLOSING


def collect_images(tex: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", tex):
        fname = Path(m.group(1).strip()).name
        if fname:
            names.add(fname)
    return names


def download_image(name: str) -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    dest = STATIC_DIR / name
    if dest.is_file() and dest.stat().st_size > 0:
        return
    url = f"{GITHUB_RAW}/{name}"
    try:
        data = fetch_url(url)
    except RuntimeError:
        print(f"  Warning: image not found on GitHub: {name}")
        return
    dest.write_bytes(data)
    print(f"  Downloaded {name}")


def update_manifest(output_tex: str, slug: str) -> None:
    pdf = output_tex.replace(".tex", ".pdf")
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    for row in manifest.get("materials") or []:
        if row.get("slug") != slug:
            continue
        tex_list = list(row.get("tex_candidates") or [])
        pdf_list = list(row.get("pdf_candidates") or [])
        if output_tex not in tex_list:
            tex_list.insert(0, output_tex)
        if pdf not in pdf_list:
            pdf_list.insert(0, pdf)
        row["tex_candidates"] = tex_list
        row["pdf_candidates"] = pdf_list
        break
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def process_lesson(cfg: dict) -> None:
    print(f"Processing {cfg['section']} -> {cfg['output']}")
    url = f"{GITHUB_RAW}/{cfg['github'].replace(' ', '%20')}"
    source = fetch_url(url).decode("utf-8", errors="replace")
    body = extract_body(source)
    body = normalize_body(body)
    body = ensure_opening_slides(body)
    body = ensure_closing(body)

    preamble = build_preamble(cfg["title_short"], cfg["title_line"])
    full = preamble + "\n" + body

    out_path = APP_DIR / cfg["output"]
    out_path.write_text(full, encoding="utf-8")

    for img in sorted(collect_images(full)):
        download_image(img)

    update_manifest(cfg["output"], cfg["slug"])
    print(f"  Wrote {out_path} ({full.count(chr(10))} lines)")


def main(argv: list[str]) -> int:
    sections = argv[1:] if len(argv) > 1 else [c["section"] for c in LESSONS]
    for cfg in LESSONS:
        if cfg["section"] in sections or cfg["output"] in sections:
            try:
                process_lesson(cfg)
            except Exception as exc:
                print(f"  ERROR {cfg['section']}: {exc}", file=sys.stderr)
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
