#!/usr/bin/env python3
"""Build English placement banks (G7–8, G9–11) from Novel Prep PDFs into question_bank.json."""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK_PATH = ROOT / "data" / "question_bank.json"

DEFAULT_TEST_PDFS = {
    "english_g7_8": ROOT / "uploads" / "G7-8______71b6.pdf",
    "english_g9_11": ROOT / "uploads" / "G9-11______a858.pdf",
}
DEFAULT_KEY_PDFS = {
    "english_g7_8": ROOT / "uploads" / "G7-8________3a26.pdf",
    "english_g9_11": ROOT / "uploads" / "G9-11________d35a.pdf",
}

# Uploaded paths on Cloud Agent VM
UPLOAD = Path("/home/ubuntu/.cursor/projects/workspace/uploads")
if UPLOAD.is_dir():
    DEFAULT_TEST_PDFS = {
        "english_g7_8": UPLOAD / "G7-8______71b6.pdf",
        "english_g9_11": UPLOAD / "G9-11______a858.pdf",
    }
    DEFAULT_KEY_PDFS = {
        "english_g7_8": UPLOAD / "G7-8________3a26.pdf",
        "english_g9_11": UPLOAD / "G9-11________d35a.pdf",
    }


def _pdf_text(path: Path) -> str:
    import pymupdf as fitz

    doc = fitz.open(str(path))
    return "\n".join(doc[i].get_text() for i in range(doc.page_count))


def _parse_answer_key(text: str, max_q: int) -> dict[int, str]:
    keys: dict[int, str] = {}
    lines = [ln.strip() for ln in text.splitlines()]
    i = 0
    while i < len(lines) - 1:
        if lines[i].isdigit() and lines[i + 1] in "ABCD":
            n = int(lines[i])
            if 1 <= n <= max_q:
                keys[n] = lines[i + 1]
            i += 2
            continue
        i += 1
    missing = [q for q in range(1, max_q + 1) if q not in keys]
    if missing:
        raise ValueError(f"Answer key missing questions: {missing[:10]}{'...' if len(missing) > 10 else ''}")
    return keys


def _paragraphs_to_html(block: str) -> str:
    paras: list[str] = []
    for raw in re.split(r"\n\s*\n", block.strip()):
        chunk = raw.strip()
        if not chunk:
            continue
        chunk = re.sub(r"\s*\n\s*", " ", chunk)
        paras.append(f"<p>{html.escape(chunk)}</p>")
    return "\n".join(paras)


def _extract_passages(part_i_text: str) -> list[dict[str, str]]:
    part_ii = part_i_text.find("Part II")
    body = part_i_text[:part_ii] if part_ii > 0 else part_i_text
    matches = list(re.finditer(r"Passage (\d+)([^\n]*)", body))
    out: list[dict[str, str]] = []
    for idx, pm in enumerate(matches):
        start = pm.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        passage_body = body[start:end]
        # Drop question block from passage text
        first_q = re.search(r"\n\s*1\.\s", passage_body)
        if idx > 0:
            first_q = re.search(r"\n\s*\d+\.\s", passage_body)
        if first_q:
            passage_body = passage_body[: first_q.start()]
        title = f"Passage {pm.group(1)} {pm.group(2).strip()}"
        pid = f"p{pm.group(1)}"
        out.append(
            {
                "id": pid,
                "title": title,
                "html": _paragraphs_to_html(passage_body),
            }
        )
    return out


def _passage_question_map(topic: str) -> dict[int, str | None]:
    if topic == "english_g7_8":
        return {**{n: "p1" for n in range(1, 4)}, **{n: "p2" for n in range(4, 10)}}
    return {
        **{n: "p1" for n in range(1, 5)},
        **{n: "p2" for n in range(5, 9)},
        **{n: "p3" for n in range(9, 13)},
    }


def _parse_mcq_block(text: str, start: int, end: int) -> list[dict]:
    part_iii = text.find("Part III")
    chunk = text[:part_iii] if part_iii > 0 else text
    # Drop cover / directions before first question
    first_q = re.search(r"^1\.\s", chunk, re.M)
    if first_q:
        chunk = chunk[first_q.start() :]

    parts = re.split(r"\n(?=\d+\.\s)", chunk)
    items: list[dict] = []
    choice_re = re.compile(
        r"^A\.\s*(.+?)\n^B\.\s*(.+?)\n^C\.\s*(.+?)\n^D\.\s*(.+?)$",
        re.MULTILINE | re.DOTALL,
    )
    for part in parts:
        part = part.strip()
        if not part:
            continue
        head = re.match(r"^(\d+)\.\s+(.+)$", part, re.DOTALL)
        if not head:
            continue
        n = int(head.group(1))
        if n < start or n > end:
            continue
        body = head.group(2)
        cm = choice_re.search(body)
        if not cm:
            raise ValueError(f"Could not parse choices for question {n}")
        stem = body[: cm.start()].strip()
        stem = re.sub(r"\s+", " ", stem)
        choices = [re.sub(r"\s+", " ", cm.group(i).strip()) for i in range(1, 5)]
        items.append({"num": n, "stem": stem, "choices": choices})
    items.sort(key=lambda x: x["num"])
    return items


def build_topic(topic: str, test_pdf: Path, key_pdf: Path) -> list[dict]:
    max_q = 31 if topic == "english_g7_8" else 40
    test_text = _pdf_text(test_pdf)
    key_text = _pdf_text(key_pdf)
    keys = _parse_answer_key(key_text, max_q)
    passages = _extract_passages(test_text)
    passage_by_id = {p["id"]: p for p in passages}
    pmap = _passage_question_map(topic)
    mcqs = _parse_mcq_block(test_text, 1, max_q)
    if len(mcqs) != max_q:
        got = [x["num"] for x in mcqs]
        raise ValueError(f"{topic}: expected {max_q} MCQs, parsed {len(mcqs)}: {got}")

    language_panel = (
        '<div class="np-en-placement-lang-panel">'
        "<h3 class=\"np-en-placement-lang-panel__title\">Language &amp; conventions</h3>"
        "<p>These items test grammar, usage, and sentence skills. "
        "Read each question carefully and choose the best answer.</p>"
        "</div>"
    )

    questions: list[dict] = []
    for row in mcqs:
        n = row["num"]
        pid = pmap.get(n)
        section = "reading" if pid else "language"
        if pid and pid in passage_by_id:
            p = passage_by_id[pid]
            passage_html = (
                f'<header class="np-en-passage-head"><span class="np-en-passage-kicker">Reading</span>'
                f'<h2 class="np-en-passage-title">{html.escape(p["title"])}</h2></header>'
                f'<div class="np-en-passage-body">{p["html"]}</div>'
            )
        else:
            passage_html = language_panel

        section_title = "Reading" if section == "reading" else "Language & conventions"
        if topic == "english_g7_8":
            section_index = n if section == "reading" else n - 9
            section_total = 9 if section == "reading" else 22
            global_total = 31
        else:
            section_index = n if section == "reading" else n - 12
            section_total = 12 if section == "reading" else 28
            global_total = 40

        questions.append(
            {
                "stem": f"<p class=\"np-en-stem-question\">{html.escape(row['stem'])}</p>",
                "choices": row["choices"],
                "question_kind": "mcq",
                "correct_answer": keys[n],
                "answer_alternates": [],
                "placement_section": section,
                "placement_section_title": section_title,
                "placement_section_index": section_index,
                "placement_section_total": section_total,
                "placement_global_index": n,
                "placement_global_total": global_total,
                "english_passage_html": passage_html,
                "english_layout": "passage_split",
                "knowledge_section": topic,
                "display_number": n,
            }
        )
    return questions


def main() -> None:
    test_paths = DEFAULT_TEST_PDFS
    key_paths = DEFAULT_KEY_PDFS
    built: dict[str, list[dict]] = {}
    for topic in ("english_g7_8", "english_g9_11"):
        tp, kp = test_paths[topic], key_paths[topic]
        if not tp.is_file() or not kp.is_file():
            print(f"Skip {topic}: missing PDF ({tp} / {kp})", file=sys.stderr)
            sys.exit(1)
        built[topic] = build_topic(topic, tp, kp)
        print(f"Built {topic}: {len(built[topic])} items")

    bank = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    placement = bank.setdefault("placement", {})
    for topic, qs in built.items():
        placement[topic] = qs
    BANK_PATH.write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {BANK_PATH}")


if __name__ == "__main__":
    main()
