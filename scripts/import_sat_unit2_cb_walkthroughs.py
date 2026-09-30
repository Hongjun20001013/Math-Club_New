#!/usr/bin/env python3
"""Import Unit 2 CB step-by-step solutions (LaTeX) into sat_extended_walkthroughs.json."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WT_PATH = os.path.join(APP_DIR, "data", "sat_extended_walkthroughs.json")
BANK_PATH = os.path.join(APP_DIR, "data", "question_bank.json")
DEFAULT_TEX = os.path.join(APP_DIR, "SAT_Unit2_CB_Solutions.tex")
DEFAULT_PDF = os.path.join(APP_DIR, "SAT_Unit2_CB_Solutions.pdf")
DOMAIN = "advanced_math"

SECTION_TO_TOPIC = {
    "2.1": "2_1",
    "2.2": "2_2",
    "2.3": "2_3",
}

_QUESTION_HDR = re.compile(
    r"\{\\Large\\bfseries\\color\{NPdeep\}\s*(2\.\d+)\s*/\s*Question\s*(\d+)\}"
)


def _read_braced_group(s: str, open_brace: int) -> tuple[str, int]:
    """Return (inner, index after closing brace). open_brace points at '{'."""
    if open_brace >= len(s) or s[open_brace] != "{":
        raise ValueError("expected '{'")
    depth = 0
    i = open_brace
    start = i + 1
    while i < len(s):
        ch = s[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start:i], i + 1
        i += 1
    raise ValueError("unclosed brace")


def _strip_latex_command(s: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == "\\":
            if i + 1 < len(s) and s[i + 1] in "{}$%&_#^":
                out.append(s[i + 1])
                i += 2
                continue
            if i + 1 < len(s) and s[i + 1] in "[]":
                out.append("\n")
                i += 2
                continue
            m = re.match(r"\\([a-zA-Z@]+)(\*?)", s[i:])
            if not m:
                out.append(s[i])
                i += 1
                continue
            cmd = m.group(1)
            i += len(m.group(0))
            if cmd in ("textbf", "emph", "textit", "color", "textcolor"):
                if i < len(s) and s[i] == "{":
                    inner, i = _read_braced_group(s, i)
                    out.append(_strip_latex_command(inner))
                continue
            if cmd in ("left", "right"):
                if i < len(s) and s[i] in "({[|.":
                    out.append(s[i])
                    i += 1
                continue
            if cmd in ("par", "vspace", "hfill", "clearpage", "newline"):
                out.append("\n")
                if i < len(s) and s[i] == "{":
                    _, i = _read_braced_group(s, i)
                continue
            if cmd in ("dfrac", "tfrac", "frac"):
                if i < len(s) and s[i] == "{":
                    num, i = _read_braced_group(s, i)
                    if i < len(s) and s[i] == "{":
                        den, i = _read_braced_group(s, i)
                        out.append(f"({num.strip()})/({den.strip()})")
                continue
            if cmd == "sqrt":
                if i < len(s) and s[i] == "[":
                    j = s.find("]", i)
                    if j != -1:
                        i = j + 1
                if i < len(s) and s[i] == "{":
                    inner, i = _read_braced_group(s, i)
                    out.append(f"√({_strip_latex_command(inner)})")
                continue
            repl = {
                "Rightarrow": "⇒",
                "Leftarrow": "⇐",
                "Leftrightarrow": "⇔",
                "ne": "≠",
                "neq": "≠",
                "le": "≤",
                "ge": "≥",
                "cdot": "·",
                "times": "×",
                "pm": "±",
                "infty": "∞",
                "quad": "  ",
                "qquad": "    ",
            }.get(cmd)
            if repl is not None:
                out.append(repl)
            continue
        if s[i] == "{":
            inner, i = _read_braced_group(s, i)
            out.append(_strip_latex_command(inner))
            continue
        if s[i] in "$":
            i += 1
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def _normalize_ws(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _solution_block_to_walkthrough(solution: str) -> str:
    parts: list[str] = []
    pos = 0
    while True:
        m = re.search(r"\\step\{", solution[pos:])
        if not m:
            break
        i = pos + m.start() + len("\\step")
        if i >= len(solution) or solution[i] != "{":
            break
        step_no, i = _read_braced_group(solution, i)
        title, i = _read_braced_group(solution, i)
        body, i = _read_braced_group(solution, i)
        title = _normalize_ws(_strip_latex_command(title))
        body = _normalize_ws(_strip_latex_command(body))
        parts.append(f"**Step {step_no.strip()}:** {title}\n\n{body}")
        pos = i

    am = re.search(r"\\answer\{", solution)
    if am:
        ans, _ = _read_braced_group(solution, am.end() - 1)
        ans = _normalize_ws(_strip_latex_command(ans))
        parts.append(f"**Final answer:** {ans}")

    return "\n\n".join(parts)


def parse_walkthroughs(tex: str, sections: set[str] | None = None) -> dict[str, str]:
    cut = tex.find(r"\section*{Verification Notes}")
    if cut != -1:
        tex = tex[:cut]

    out: dict[str, str] = {}
    matches = list(_QUESTION_HDR.finditer(tex))
    for idx, m in enumerate(matches):
        sec, q_raw = m.group(1), m.group(2)
        if sections is not None and sec not in sections:
            continue
        topic = SECTION_TO_TOPIC.get(sec)
        if not topic:
            continue
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(tex)
        block = tex[m.end() : end]
        mm = re.search(
            r"\\begin\{minipage\}.*?Worked solution.*?\\par\s*(.*?)\\end\{minipage\}",
            block,
            re.S,
        )
        if not mm:
            continue
        text = _solution_block_to_walkthrough(mm.group(1))
        if not text:
            continue
        qnum = int(q_raw)
        key = f"{DOMAIN}:{topic}:{qnum - 1}"
        out[key] = text
    return out


def _pdf_text(path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(path)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _u1_body_to_walkthrough(body: str) -> str:
    import importlib.util

    u1_path = os.path.join(APP_DIR, "scripts", "import_sat_unit1_cb_walkthroughs.py")
    spec = importlib.util.spec_from_file_location("import_sat_unit1_cb_walkthroughs", u1_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load import_sat_unit1_cb_walkthroughs")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._body_to_walkthrough(body)


def _parse_walkthroughs_from_pdf(pdf_text: str, sections: set[str] | None) -> dict[str, str]:
    """Cross-check PDF text; LaTeX source remains the canonical import."""

    out: dict[str, str] = {}
    for block in re.split(r"Worked solution\s*", pdf_text)[1:]:
        m = re.match(r"([\d.]+)\s*/\s*Q(\d+)\s*(.*)", block, re.S)
        if not m:
            continue
        sec, q_raw, body = m.group(1), m.group(2), m.group(3)
        if sections is not None and sec not in sections:
            continue
        topic = SECTION_TO_TOPIC.get(sec)
        if not topic:
            continue
        body = re.split(r"\n\d+\s*/\s*\d+\s*\n", body)[0]
        body = re.sub(r"\s+\d+\s*/\s*\d+\s*$", "", body.strip())
        text = _u1_body_to_walkthrough(body)
        if text:
            out[f"{DOMAIN}:{topic}:{int(q_raw) - 1}"] = text
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("tex", nargs="?", default=DEFAULT_TEX, help="Path to SAT_Unit2_CB_Solutions.tex")
    p.add_argument(
        "--pdf",
        default=None,
        help="Optional PDF to verify slot count (SAT_Unit2_CB_Solutions.pdf)",
    )
    p.add_argument(
        "--sections",
        default="2.1,2.2,2.3",
        help="Comma-separated section ids (default: all Unit 2 algebra slices)",
    )
    p.add_argument(
        "--copy-tex",
        action="store_true",
        help="Copy source .tex into repo root as SAT_Unit2_CB_Solutions.tex",
    )
    p.add_argument(
        "--copy-pdf",
        action="store_true",
        help="Copy --pdf into repo root as SAT_Unit2_CB_Solutions.pdf",
    )
    args = p.parse_args()

    tex_path = os.path.abspath(args.tex)
    if not os.path.isfile(tex_path):
        print(f"Missing LaTeX: {tex_path}", file=sys.stderr)
        return 1

    if args.copy_tex and os.path.abspath(tex_path) != os.path.abspath(DEFAULT_TEX):
        shutil.copy2(tex_path, DEFAULT_TEX)
        print(f"Copied LaTeX → {DEFAULT_TEX}")

    pdf_path = os.path.abspath(args.pdf or DEFAULT_PDF)
    if args.copy_pdf and os.path.isfile(pdf_path):
        if os.path.abspath(pdf_path) != os.path.abspath(DEFAULT_PDF):
            shutil.copy2(pdf_path, DEFAULT_PDF)
            print(f"Copied PDF → {DEFAULT_PDF}")
        pdf_path = DEFAULT_PDF

    sections = {s.strip() for s in args.sections.split(",") if s.strip()}
    with open(tex_path, encoding="utf-8") as f:
        parsed = parse_walkthroughs(f.read(), sections)

    if os.path.isfile(pdf_path):
        pdf_parsed = _parse_walkthroughs_from_pdf(_pdf_text(pdf_path), sections)
        missing = sorted(set(parsed) - set(pdf_parsed))
        extra = sorted(set(pdf_parsed) - set(parsed))
        if missing or extra:
            print(f"PDF verify warning: missing={len(missing)} extra={len(extra)}", file=sys.stderr)
        else:
            print(f"PDF verify OK ({len(pdf_parsed)} slots match LaTeX import)")

    with open(BANK_PATH, encoding="utf-8") as f:
        bank = json.load(f)
    errs: list[str] = []
    for key in sorted(parsed):
        _, topic, idx_s = key.split(":")
        idx = int(idx_s)
        qs = (bank.get(DOMAIN) or {}).get(topic)
        if not isinstance(qs, list) or idx < 0 or idx >= len(qs):
            errs.append(f"Bank slot missing: {key}")

    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        return 1

    raw: dict = {"version": 1}
    if os.path.isfile(WT_PATH):
        with open(WT_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    wt = raw.get("walkthroughs")
    if not isinstance(wt, dict):
        wt = {}
    topics_importing = {SECTION_TO_TOPIC[s] for s in sections if s in SECTION_TO_TOPIC}
    for k in list(wt):
        if not k.startswith(f"{DOMAIN}:"):
            continue
        parts = k.split(":")
        if len(parts) == 3 and parts[1] in topics_importing:
            del wt[k]
    wt.update(parsed)
    raw["walkthroughs"] = wt
    raw["readme"] = (
        "Keys are domain:topic_key:local_index (0-based). "
        "Unit 1 algebra and Unit 2 advanced_math walkthroughs imported from CB solution sources. "
        "Use **double asterisks** for bold."
    )
    with open(WT_PATH, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote {len(parsed)} walkthroughs to {WT_PATH}")
    adv = bank.get(DOMAIN) or {}
    for sec, topic in SECTION_TO_TOPIC.items():
        if sec not in sections:
            continue
        n = len(adv.get(topic) or [])
        got = sum(1 for k in parsed if k.startswith(f"{DOMAIN}:{topic}:"))
        print(f"  {sec} ({topic}): {got}/{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
