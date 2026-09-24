#!/usr/bin/env python3
"""Import Unit 1 CB step-by-step solutions PDF into sat_extended_walkthroughs.json."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

from pypdf import PdfReader

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WT_PATH = os.path.join(APP_DIR, "data", "sat_extended_walkthroughs.json")
BANK_PATH = os.path.join(APP_DIR, "data", "question_bank.json")
DEFAULT_PDF = os.path.join(APP_DIR, "SAT_Unit1_CB_Solutions.pdf")

SECTION_TO_TOPIC = {
    "1.1": "1_1",
    "1.2": "1_2",
    "1.3": "1_3",
    "1.4": "1_4",
    "1.5": "1_5",
}


def _pdf_text(path: str) -> str:
    reader = PdfReader(path)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _clean_inline_spaces(text: str) -> str:
    s = text
    s = re.sub(r"(\d), (\d)", r"\1,\2", s)
    s = re.sub(r"(\d{1,2}) (\d{3})\b", r"\1,\2", s)
    s = re.sub(r"([a-zA-Z])(\d)", r"\1 \2", s)
    s = re.sub(r"(\d)(÷)", r"\1 \2", s)
    s = re.sub(r"(÷)(\d)", r"\1 \2", s)
    s = re.sub(r"(\d)(=)", r"\1 \2", s)
    s = re.sub(r"(=)(\d)", r"\1 \2", s)
    s = re.sub(r"(\d)(−|-)", r"\1 \2", s)
    s = re.sub(r"([−-])(\d)", r"\1 \2", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _body_to_walkthrough(body: str) -> str:
    body = re.split(r"\n\d+\s*/\s*98\s*\n", body)[0]
    body = re.split(r"Novel Prep \|", body)[0]
    body = body.strip()
    body = re.sub(r"Step (\d+)\.", r"Step \1:", body)
    chunks = re.split(r"(?=Step \d+:|Final answer:)", body, flags=re.IGNORECASE)
    parts: list[str] = []
    for chunk in chunks:
        chunk = _clean_inline_spaces(chunk.replace("\n", " "))
        if not chunk:
            continue
        if chunk.lower().startswith("final answer:"):
            ans = chunk.split(":", 1)[-1].strip()
            parts.append(f"**Final answer:** {ans}")
        else:
            parts.append(chunk)
    return "\n\n".join(parts)


def parse_walkthroughs(pdf_text: str, sections: set[str] | None = None) -> dict[str, str]:
    out: dict[str, str] = {}
    for block in re.split(r"Worked solution:\s*", pdf_text)[1:]:
        m = re.match(r"([\d.]+)\s*/\s*Q(\d+)\s*(.*)", block, re.S)
        if not m:
            continue
        sec, q_raw, body = m.group(1), m.group(2), m.group(3)
        if sections is not None and sec not in sections:
            continue
        topic = SECTION_TO_TOPIC.get(sec)
        if not topic:
            continue
        qnum = int(q_raw)
        key = f"algebra:{topic}:{qnum - 1}"
        text = _body_to_walkthrough(body)
        if text:
            out[key] = text
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("pdf", nargs="?", default=DEFAULT_PDF, help="Path to SAT_Unit1_CB_Solutions.pdf")
    p.add_argument(
        "--sections",
        default="1.1,1.2,1.3,1.4,1.5",
        help="Comma-separated section ids to import (default: all Unit 1 slices)",
    )
    p.add_argument("--copy-pdf", action="store_true", help="Copy PDF into repo root as SAT_Unit1_CB_Solutions.pdf")
    args = p.parse_args()

    pdf_path = os.path.abspath(args.pdf)
    if not os.path.isfile(pdf_path):
        print(f"Missing PDF: {pdf_path}", file=sys.stderr)
        return 1

    if args.copy_pdf and os.path.abspath(pdf_path) != os.path.abspath(DEFAULT_PDF):
        shutil.copy2(pdf_path, DEFAULT_PDF)
        print(f"Copied PDF → {DEFAULT_PDF}")

    sections = {s.strip() for s in args.sections.split(",") if s.strip()}
    parsed = parse_walkthroughs(_pdf_text(pdf_path), sections)

    with open(BANK_PATH, encoding="utf-8") as f:
        bank = json.load(f)
    errs: list[str] = []
    for key in sorted(parsed):
        _, topic, idx_s = key.split(":")
        idx = int(idx_s)
        qs = (bank.get("algebra") or {}).get(topic)
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
        if not k.startswith("algebra:"):
            continue
        parts = k.split(":")
        if len(parts) == 3 and parts[1] in topics_importing:
            del wt[k]
    wt.update(parsed)
    raw["walkthroughs"] = wt
    raw["readme"] = (
        "Keys are domain:topic_key:local_index (0-based). "
        "Unit 1 algebra walkthroughs imported from SAT_Unit1_CB_Solutions.pdf. "
        "Use **double asterisks** for bold."
    )
    with open(WT_PATH, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote {len(parsed)} walkthroughs to {WT_PATH}")
    for sec, topic in SECTION_TO_TOPIC.items():
        if sec not in sections:
            continue
        n = len((bank.get("algebra") or {}).get(topic) or [])
        got = sum(1 for k in parsed if k.startswith(f"algebra:{topic}:"))
        print(f"  {sec} ({topic}): {got}/{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
