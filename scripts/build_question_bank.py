from __future__ import annotations

import html
import json
import os
import re
import sys
from datetime import datetime
from typing import Any, List, Optional

_SOLUTION_HTML_PREFIX = '<article class="np-solution-pro"'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import APP_DIR, BANKS
from latex_parser import parse_placement_answer_key, parse_placement_tex_file, parse_tex_file


OUTPUT_DIR = os.path.join(APP_DIR, "data")
OUTPUT_BANK = os.path.join(OUTPUT_DIR, "question_bank.json")
OUTPUT_REPORT = os.path.join(OUTPUT_DIR, "question_bank_report.json")
UNIT1_MANIFEST = os.path.join(OUTPUT_DIR, "unit1_question_manifest.json")
UNIT1_SUPPLEMENT = os.path.join(OUTPUT_DIR, "unit1_supplement.json")
UNIT1_EXPL_EN = os.path.join(OUTPUT_DIR, "unit1_explanations_en.json")
UNIT2_MANIFEST = os.path.join(OUTPUT_DIR, "unit2_question_manifest.json")
UNIT2_SUPPLEMENT = os.path.join(OUTPUT_DIR, "unit2_supplement.json")
UNIT2_EXPL_EN = os.path.join(OUTPUT_DIR, "unit2_explanations_en.json")
UNIT3_MANIFEST = os.path.join(OUTPUT_DIR, "unit3_question_manifest.json")
UNIT3_SUPPLEMENT = os.path.join(OUTPUT_DIR, "unit3_supplement.json")
UNIT3_EXPL_EN = os.path.join(OUTPUT_DIR, "unit3_explanations_en.json")
UNIT4_MANIFEST = os.path.join(OUTPUT_DIR, "unit4_question_manifest.json")
UNIT4_SUPPLEMENT = os.path.join(OUTPUT_DIR, "unit4_supplement.json")
UNIT4_EXPL_EN = os.path.join(OUTPUT_DIR, "unit4_explanations_en.json")
SAT_EXTENDED_WALKTHROUGHS = os.path.join(OUTPUT_DIR, "sat_extended_walkthroughs.json")

SECTION_HINT_EN = {
    "1.1": "Turn the words into one equation in one variable; watch for no solution, identities, and rational equations.",
    "1.2": "Use slope and intercept; a table or two points fixes a line.",
    "1.3": "Link equations to graphs (intercepts, slope); substitute to verify.",
    "1.4": "Use substitution or elimination; know when a system has no solution or infinitely many.",
    "1.5": "Sketch or test regions; note solid vs dashed boundaries and whether endpoints are included.",
    "2.1": "Expand, factor, and combine rational or radical expressions; match exponents term by term.",
    "2.2": "Use completing the square, the quadratic formula, and substitution; watch extraneous solutions.",
    "2.3": "Read vertex/intercept meaning on quadratics and exponentials; track transformations and growth factors.",
    "3.1": "Set up a proportion or unit rate; keep units consistent and cancel dimensions.",
    "3.2": "Translate percent language to decimals or fractions; watch “of,” “more than,” and successive changes.",
    "3.3": "Match shape of a distribution to context; compare center (median/mean) and spread (IQR/range).",
    "3.4": "Use scatterplot direction/strength; read slope and intercept in a fitted linear model.",
    "3.5": "Multiply probabilities along branches; for conditional probability, shrink the sample space.",
    "3.6": "Connect sample proportion to population; interpret margin of error as plausible swing, not certainty.",
    "3.7": "Separate correlation from causation; check random assignment, controls, and confounding.",
    "4.1": "Relate length, area, and volume under scaling; sum faces for surface area; pick the right solid formula before crunching numbers.",
    "4.2": "Use parallel lines and transversals; triangle angle sums and exteriors; similar triangles give proportional sides.",
    "4.3": "Apply the Pythagorean theorem and trig ratios; label opposite/adjacent to the referenced angle carefully.",
    "4.4": "Link radius, diameter, circumference, and area; read circle equations for center and radius; arc length is a fraction of the full circumference.",
}

_SLICE_ORDER = ("1_1", "1_2", "1_3", "1_4", "1_5")
_SLICE_SECTION = {
    "1_1": "1.1",
    "1_2": "1.2",
    "1_3": "1.3",
    "1_4": "1.4",
    "1_5": "1.5",
}

_SLICE_ORDER_U2 = ("2_1", "2_2", "2_3")
_SLICE_SECTION_U2 = {
    "2_1": "2.1",
    "2_2": "2.2",
    "2_3": "2.3",
}

_SLICE_ORDER_U3 = ("3_1", "3_2", "3_3", "3_4", "3_5", "3_6", "3_7")
_SLICE_SECTION_U3 = {
    "3_1": "3.1",
    "3_2": "3.2",
    "3_3": "3.3",
    "3_4": "3.4",
    "3_5": "3.5",
    "3_6": "3.6",
    "3_7": "3.7",
}

_SLICE_ORDER_U4 = ("4_1", "4_2", "4_3", "4_4")
_SLICE_SECTION_U4 = {
    "4_1": "4.1",
    "4_2": "4.2",
    "4_3": "4.3",
    "4_4": "4.4",
}


def _manifest_from_algebra_payload(alg: dict) -> List[dict]:
    """Rebuild unit1_question_manifest.json rows when slices align with unit_1_all."""
    full = alg.get("unit_1_all")
    if not full:
        return []
    rows: List[dict] = []
    g = 0
    for tk in _SLICE_ORDER:
        qs = alg.get(tk)
        if not qs:
            return []
        sec = _SLICE_SECTION[tk]
        for li in range(len(qs)):
            rows.append(
                {
                    "display_number": g + 1,
                    "section": sec,
                    "topic_key": tk,
                    "topic_local_index": li,
                }
            )
            g += 1
    if g != len(full):
        return []
    return rows


def _manifest_from_unit2_payload(alg: dict) -> List[dict]:
    full = alg.get("unit_2_all")
    if not full:
        return []
    rows: List[dict] = []
    g = 0
    for tk in _SLICE_ORDER_U2:
        qs = alg.get(tk)
        if not qs:
            return []
        sec = _SLICE_SECTION_U2[tk]
        for li in range(len(qs)):
            rows.append(
                {
                    "display_number": g + 1,
                    "section": sec,
                    "topic_key": tk,
                    "topic_local_index": li,
                }
            )
            g += 1
    if g != len(full):
        return []
    return rows


def _manifest_from_unit3_payload(ps: dict) -> List[dict]:
    full = ps.get("unit_3_all")
    if not full:
        return []
    rows: List[dict] = []
    g = 0
    for tk in _SLICE_ORDER_U3:
        qs = ps.get(tk)
        if not qs:
            return []
        sec = _SLICE_SECTION_U3[tk]
        for li in range(len(qs)):
            rows.append(
                {
                    "display_number": g + 1,
                    "section": sec,
                    "topic_key": tk,
                    "topic_local_index": li,
                }
            )
            g += 1
    if g != len(full):
        return []
    return rows


def _manifest_from_unit4_payload(geo: dict) -> List[dict]:
    full = geo.get("unit_4_all")
    if not full:
        return []
    rows: List[dict] = []
    g = 0
    for tk in _SLICE_ORDER_U4:
        qs = geo.get(tk)
        if not qs:
            return []
        sec = _SLICE_SECTION_U4[tk]
        for li in range(len(qs)):
            rows.append(
                {
                    "display_number": g + 1,
                    "section": sec,
                    "topic_key": tk,
                    "topic_local_index": li,
                }
            )
            g += 1
    if g != len(full):
        return []
    return rows


def _load_json(path: str):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _answer_cell_to_payload(cell: Any) -> tuple[str, List[str]]:
    """Return (canonical_answer, alternates) for supplement JSON cells."""
    if isinstance(cell, dict):
        can = str(cell.get("canonical", "")).strip()
        raw_alt = cell.get("alternates")
        if raw_alt is None:
            raw_alt = cell.get("alt") or []
        alts = [str(x) for x in raw_alt]
        return can, alts
    s = str(cell).strip()
    if len(s) == 1 and s.upper() in "ABCD":
        return s.upper(), []
    return s, []


def _sat_walkthrough_map() -> dict[str, Any]:
    raw = _load_json(SAT_EXTENDED_WALKTHROUGHS) or {}
    wt = raw.get("walkthroughs")
    if isinstance(wt, dict):
        return wt
    return {}


def _walkthrough_slot_key(domain: str, topic_key: str, local_index: int) -> str:
    return f"{domain}:{topic_key}:{int(local_index)}"


def _extended_walkthrough_section_html(extended_plain: str) -> str:
    s = (extended_plain or "").strip()
    if not s:
        return ""
    esc = html.escape(s, quote=False)
    esc = _inline_bold_from_markdown(esc)
    parts = [p.strip() for p in re.split(r"\n\s*\n", esc) if p.strip()]
    if not parts:
        parts = [esc.replace("\n", "<br>")]
    inner = "".join(
        f'<p class="np-sol-walk-para">{p.replace(chr(10), "<br>")}</p>' for p in parts
    )
    foot = (
        "<p class=\"np-sol-walk-footer\">"
        "SAT workflow: try the problem first, then use this only for the step where your reasoning stopped. "
        "Close the tab and rework from the stem without the key when you review later."
        "</p>"
    )
    return (
        '<section class="np-sol-block np-sol-block--walkthrough" aria-label="SAT-style walkthrough">'
        '<span class="np-sol-label np-sol-label--walk">Full walkthrough</span>'
        f'<div class="np-sol-walk-body">{inner}</div>'
        f"{foot}"
        "</section>"
    )


def _inject_walkthrough_into_explanation(base: str, extended_plain: str) -> str:
    block = _extended_walkthrough_section_html(extended_plain)
    if not block:
        return base
    foot_idx = base.rfind('<footer class="np-sol-foot">')
    if foot_idx != -1:
        return base[:foot_idx] + block + base[foot_idx:]
    mark = base.rfind("</article>")
    if mark == -1:
        return base + block
    return base[:mark] + block + base[mark:]


def _stem_plain_for_walkthrough(stem_html: str, max_len: int = 220) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", " ", stem_html or ""))
    t = " ".join(t.split())
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t


def _auto_walkthrough_plain(
    sec: str,
    kind: str,
    key_display: str,
    alternates: Optional[List[Any]],
    stem_plain: str,
) -> str:
    """SAT-style four-step template when no authored slot text exists."""
    hint = SECTION_HINT_EN.get(
        sec, "Translate the situation into clear structure, then simplify step by step."
    )
    kd = str(key_display).strip()
    kind_l = (kind or "mcq").lower()
    stem_bit = stem_plain if stem_plain else "the quantities and relationships described in the stem."

    if kind_l == "free_response":
        alts = [str(x).strip() for x in (alternates or []) if str(x).strip()]
        alt_sentence = ""
        if alts:
            preview = ", ".join(alts[:5])
            alt_sentence = f" Equivalent forms such as **{preview}** may also be accepted if they match the key."
        return (
            f"Step 1: Reread the stem in your own words. Pull out what is fixed, what is unknown, and what you must output. Key givens: {stem_bit}\n\n"
            f"Step 2: **Expert angle —** {hint}\n\n"
            f"Step 3: Build one clean model (equation, proportion, or expression) and simplify carefully—watch distribution, clearing denominators, and sign errors before you lock a value.\n\n"
            f"Step 4: The official answer is **{kd}**.{alt_sentence} Rework the algebra once without looking at the key to see where your line of reasoning diverged."
        )

    letter = (kd[:1] or "?").upper()
    return (
        f"Step 1: Reread the stem. What quantity or condition is the question really asking for? Note units and constraints. Givens in brief: {stem_bit}\n\n"
        f"Step 2: **Expert angle —** {hint}\n\n"
        f"Step 3: Turn the wording into algebra or a table comparison; eliminate answer choices using estimates, impossible signs, or inconsistent units before you commit to heavy computation.\n\n"
        f"Step 4: The answer key marks choice **{letter}** as correct. Substitute **{letter}** (or test its consequence) back into the stem for a quick consistency check before you move on."
    )


def _apply_slot_walkthrough(
    q: Any,
    domain: str,
    topic_key: str,
    local_index: int,
    wt: Optional[dict[str, Any]],
) -> None:
    """Merge sat_extended_walkthroughs slot text, or a SAT-style auto template so every item has a full walkthrough."""
    wt = wt or {}
    key = _walkthrough_slot_key(domain, topic_key, local_index)
    cell = wt.get(key)
    text = ""
    if cell is not None:
        if isinstance(cell, dict):
            text = str(cell.get("text") or cell.get("en") or "").strip()
        else:
            text = str(cell).strip()
    if not text:
        stem_plain = _stem_plain_for_walkthrough(str(q.get("stem") or ""))
        sec = str(q.get("knowledge_section") or "")
        kind = str(q.get("question_kind") or "mcq")
        kd = str(q.get("correct_answer") or "")
        alts = q.get("answer_alternates") or []
        text = _auto_walkthrough_plain(sec, kind, kd, alts, stem_plain)
    cur = q.get("explanation_en") or ""
    q["explanation_en"] = _inject_walkthrough_into_explanation(cur, text)


def _inline_bold_from_markdown(text: str) -> str:
    """Turn **segments** into <strong> after the rest of the string is already HTML-escaped."""

    def _sub(m: re.Match[str]) -> str:
        inner = m.group(1)
        return "<strong>" + inner + "</strong>"

    return re.sub(r"\*\*(.+?)\*\*", _sub, text, flags=re.DOTALL)


def _legacy_override_to_html(raw: str) -> str:
    """Pack author-written plain / markdown-ish notes into the same premium shell."""
    s = (raw or "").strip()
    if not s:
        return ""
    esc = html.escape(s, quote=False)
    esc = _inline_bold_from_markdown(esc)
    parts = [p.strip() for p in re.split(r"\n\s*\n", esc) if p.strip()]
    if not parts:
        parts = [esc.replace("\n", "<br>")]
    paras = "".join(
        f'<p class="np-sol-text">{p.replace(chr(10), "<br>")}</p>' for p in parts
    )
    return (
        f'<article class="np-solution-pro np-solution-pro--custom" lang="en">'
        f'<header class="np-sol-head"><p class="np-sol-eyebrow">Author notes</p>'
        f'<h3 class="np-sol-title">Walkthrough</h3></header>'
        f'<div class="np-sol-custom-body">{paras}</div></article>'
    )


def _finalize_explanation(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if s.lower().startswith(_SOLUTION_HTML_PREFIX.lower()):
        return s
    return _legacy_override_to_html(s)


def _expl_en_html(
    sec: str,
    kind: str,
    key_display: str,
    display_n: int,
    expl_en_ov: dict,
    titles_en: dict,
    alternates: Optional[List[str]] = None,
) -> str:
    k = str(display_n)
    if k in expl_en_ov and expl_en_ov[k]:
        return _finalize_explanation(str(expl_en_ov[k]))

    hint = SECTION_HINT_EN.get(
        sec, "Translate the situation into clear structure, then simplify step by step."
    )
    name = titles_en.get(sec, sec)
    name_e = html.escape(name, quote=False)
    hint_e = html.escape(hint, quote=False)
    key_e = html.escape(str(key_display).strip(), quote=False)
    sec_e = html.escape(sec, quote=False)

    review_mcq = (
        "Close the answer choices, restate the task in your own words, then decide from definitions and "
        "structure—not from which letter “feels” familiar."
    )
    review_spr = (
        "Recompute from a blank scratch line: watch signs, domain constraints, and whether your form matches "
        "an acceptable equivalent before you compare to the key."
    )

    if kind == "free_response":
        alts = [str(x).strip() for x in (alternates or []) if str(x).strip()]
        alts_e = [html.escape(a, quote=False) for a in alts[:6]]
        alt_block = ""
        if alts_e:
            lis = "".join(f"<li><code>{a}</code></li>" for a in alts_e)
            alt_block = (
                f'<div class="np-sol-alt-wrap"><span class="np-sol-label">Also accepted</span>'
                f'<ul class="np-sol-alt-list">{lis}</ul></div>'
            )
        key_row = (
            f'<div class="np-sol-key-spr" role="group" aria-label="Student-produced response">'
            f'<code class="np-sol-numeric">{key_e}</code></div>'
        )
        review_e = html.escape(review_spr, quote=False)
        body = (
            '<article class="np-solution-pro np-solution-pro--spr" lang="en">'
            f'<header class="np-sol-head">'
            f'<p class="np-sol-eyebrow">SAT Math · <span class="np-sol-sec-pill">{sec_e}</span></p>'
            f'<h3 class="np-sol-title">{name_e}</h3></header>'
            f'<section class="np-sol-block np-sol-block--strategy" aria-label="Strategy">'
            f'<span class="np-sol-label">Expert approach</span>'
            f'<p class="np-sol-text">{hint_e}</p></section>'
            f'<section class="np-sol-block np-sol-block--key" aria-label="Answer key">'
            f'<span class="np-sol-label">Verified key</span>{key_row}{alt_block}</section>'
            f'<footer class="np-sol-foot"><p class="np-sol-text">{review_e}</p></footer>'
            f"</article>"
        )
        return body

    letter = (str(key_display).strip()[:1] or "?").upper()
    letter_e = html.escape(letter, quote=False)
    review_e = html.escape(review_mcq, quote=False)
    return (
        '<article class="np-solution-pro np-solution-pro--mcq" lang="en">'
        f'<header class="np-sol-head">'
        f'<p class="np-sol-eyebrow">SAT Math · <span class="np-sol-sec-pill">{sec_e}</span></p>'
        f'<h3 class="np-sol-title">{name_e}</h3></header>'
        f'<section class="np-sol-block np-sol-block--strategy" aria-label="Strategy">'
        f'<span class="np-sol-label">Expert approach</span>'
        f'<p class="np-sol-text">{hint_e}</p></section>'
        f'<section class="np-sol-block np-sol-block--key" aria-label="Answer key">'
        f'<span class="np-sol-label">Verified key</span>'
        f'<div class="np-sol-key-mcq" aria-label="Multiple choice">'
        f'<span class="np-sol-letter" aria-hidden="true">{letter_e}</span>'
        f'<span class="np-sol-letter-caption">Correct letter</span></div></section>'
        f'<footer class="np-sol-foot"><p class="np-sol-text">{review_e}</p></footer>'
        f"</article>"
    )


def _attach_unit1_answer_row(
    q: Any,
    cell: Any,
    m: Any,
    titles_zh: dict,
    titles_en: dict,
    expl_en_ov: dict,
) -> None:
    can, alts = _answer_cell_to_payload(cell)
    sec = m["section"]
    display_n = m["display_number"]
    kind = q.get("question_kind")
    if kind not in ("mcq", "free_response"):
        kind = (
            "mcq"
            if q.get("choices") and len([c for c in q["choices"] if c]) == 4
            else "free_response"
        )
        q["question_kind"] = kind

    q["correct_answer"] = can
    q["answer_alternates"] = alts
    q["knowledge_section"] = sec
    q["knowledge_section_title_zh"] = titles_zh.get(sec, sec)
    q["knowledge_section_title_en"] = titles_en.get(sec, sec)
    q["display_number"] = display_n
    q["explanation_en"] = _expl_en_html(
        sec,
        kind,
        can,
        display_n,
        expl_en_ov,
        titles_en,
        alts if kind == "free_response" else None,
    )


def _enrich_unit1_algebra_questions(
    topic_key: str,
    questions: List[Any],
    manifest: Optional[List[Any]],
    walkthroughs: Optional[dict[str, Any]] = None,
) -> None:
    """Attach correct_answer, knowledge tags, and English explanations for Unit 1."""
    if not manifest:
        return
    supp = _load_json(UNIT1_SUPPLEMENT)
    if not supp:
        return
    expl_en_ov = _load_json(UNIT1_EXPL_EN) or {}
    titles_zh = supp.get("section_titles_zh", {})
    titles_en = supp.get("section_titles_en", {})
    by_topic = supp.get("answers_by_topic", {})

    def _cells_for_topic(tk: str) -> Optional[List[Any]]:
        row = by_topic.get(tk)
        return list(row) if isinstance(row, list) else None

    if topic_key == "unit_1_all":
        flat: List[Any] = []
        for tk in _SLICE_ORDER:
            cells = _cells_for_topic(tk)
            if not cells:
                print("Warning: missing answers for", tk)
                return
            flat.extend(cells)
        if len(flat) != len(questions) or len(manifest) != len(questions):
            print(
                "Warning: unit_1_all length mismatch; skip answer enrichment.",
                len(flat),
                len(questions),
                len(manifest),
            )
            return
        for i, q in enumerate(questions):
            _attach_unit1_answer_row(
                q, flat[i], manifest[i], titles_zh, titles_en, expl_en_ov
            )
            m = manifest[i]
            _apply_slot_walkthrough(
                q,
                "algebra",
                str(m.get("topic_key", "")),
                int(m.get("topic_local_index", 0)),
                walkthroughs or {},
            )
    elif topic_key in by_topic:
        cells = _cells_for_topic(topic_key)
        sub = [row for row in manifest if row.get("topic_key") == topic_key]
        if not cells or len(cells) != len(questions) or len(sub) != len(questions):
            print(
                "Warning: slice",
                topic_key,
                "answer length mismatch; skip enrichment.",
                len(cells or []),
                len(questions),
            )
            return
        for j, q in enumerate(questions):
            _attach_unit1_answer_row(
                q, cells[j], sub[j], titles_zh, titles_en, expl_en_ov
            )
            sj = sub[j]
            _apply_slot_walkthrough(
                q,
                "algebra",
                str(sj.get("topic_key", topic_key)),
                int(sj.get("topic_local_index", j)),
                walkthroughs or {},
            )


def _enrich_unit2_algebra_questions(
    topic_key: str,
    questions: List[Any],
    manifest: Optional[List[Any]],
    walkthroughs: Optional[dict[str, Any]] = None,
) -> None:
    if not manifest:
        return
    supp = _load_json(UNIT2_SUPPLEMENT)
    if not supp:
        return
    expl_en_ov = _load_json(UNIT2_EXPL_EN) or {}
    titles_zh = supp.get("section_titles_zh", {})
    titles_en = supp.get("section_titles_en", {})
    by_topic = supp.get("answers_by_topic", {})

    def _cells_for_topic(tk: str) -> Optional[List[Any]]:
        row = by_topic.get(tk)
        return list(row) if isinstance(row, list) else None

    if topic_key == "unit_2_all":
        flat: List[Any] = []
        for tk in _SLICE_ORDER_U2:
            cells = _cells_for_topic(tk)
            if not cells:
                print("Warning: missing Unit 2 answers for", tk)
                return
            flat.extend(cells)
        if len(flat) != len(questions) or len(manifest) != len(questions):
            print(
                "Warning: unit_2_all length mismatch; skip answer enrichment.",
                len(flat),
                len(questions),
                len(manifest),
            )
            return
        for i, q in enumerate(questions):
            _attach_unit1_answer_row(
                q, flat[i], manifest[i], titles_zh, titles_en, expl_en_ov
            )
            m = manifest[i]
            _apply_slot_walkthrough(
                q,
                "advanced_math",
                str(m.get("topic_key", "")),
                int(m.get("topic_local_index", 0)),
                walkthroughs or {},
            )
    elif topic_key in by_topic:
        cells = _cells_for_topic(topic_key)
        sub = [row for row in manifest if row.get("topic_key") == topic_key]
        if not cells or len(cells) != len(questions) or len(sub) != len(questions):
            print(
                "Warning: Unit 2 slice",
                topic_key,
                "answer length mismatch; skip enrichment.",
                len(cells or []),
                len(questions),
            )
            return
        for j, q in enumerate(questions):
            _attach_unit1_answer_row(
                q, cells[j], sub[j], titles_zh, titles_en, expl_en_ov
            )
            sj = sub[j]
            _apply_slot_walkthrough(
                q,
                "advanced_math",
                str(sj.get("topic_key", topic_key)),
                int(sj.get("topic_local_index", j)),
                walkthroughs or {},
            )


def _enrich_unit3_questions(
    topic_key: str,
    questions: List[Any],
    manifest: Optional[List[Any]],
    walkthroughs: Optional[dict[str, Any]] = None,
) -> None:
    if not manifest:
        return
    supp = _load_json(UNIT3_SUPPLEMENT)
    if not supp:
        return
    expl_en_ov = _load_json(UNIT3_EXPL_EN) or {}
    titles_zh = supp.get("section_titles_zh", {})
    titles_en = supp.get("section_titles_en", {})
    by_topic = supp.get("answers_by_topic", {})

    def _cells_for_topic(tk: str) -> Optional[List[Any]]:
        row = by_topic.get(tk)
        return list(row) if isinstance(row, list) else None

    if topic_key == "unit_3_all":
        flat: List[Any] = []
        for tk in _SLICE_ORDER_U3:
            cells = _cells_for_topic(tk)
            if not cells:
                print("Warning: missing Unit 3 answers for", tk)
                return
            flat.extend(cells)
        if len(flat) != len(questions) or len(manifest) != len(questions):
            print(
                "Warning: unit_3_all length mismatch; skip answer enrichment.",
                len(flat),
                len(questions),
                len(manifest),
            )
            return
        for i, q in enumerate(questions):
            _attach_unit1_answer_row(
                q, flat[i], manifest[i], titles_zh, titles_en, expl_en_ov
            )
            m = manifest[i]
            _apply_slot_walkthrough(
                q,
                "problem_solving",
                str(m.get("topic_key", "")),
                int(m.get("topic_local_index", 0)),
                walkthroughs or {},
            )
    elif topic_key in by_topic:
        cells = _cells_for_topic(topic_key)
        sub = [row for row in manifest if row.get("topic_key") == topic_key]
        if not cells or len(cells) != len(questions) or len(sub) != len(questions):
            print(
                "Warning: Unit 3 slice",
                topic_key,
                "answer length mismatch; skip enrichment.",
                len(cells or []),
                len(questions),
            )
            return
        for j, q in enumerate(questions):
            _attach_unit1_answer_row(
                q, cells[j], sub[j], titles_zh, titles_en, expl_en_ov
            )
            sj = sub[j]
            _apply_slot_walkthrough(
                q,
                "problem_solving",
                str(sj.get("topic_key", topic_key)),
                int(sj.get("topic_local_index", j)),
                walkthroughs or {},
            )


def _enrich_unit4_questions(
    topic_key: str,
    questions: List[Any],
    manifest: Optional[List[Any]],
    walkthroughs: Optional[dict[str, Any]] = None,
) -> None:
    if not manifest:
        return
    supp = _load_json(UNIT4_SUPPLEMENT)
    if not supp:
        return
    expl_en_ov = _load_json(UNIT4_EXPL_EN) or {}
    titles_zh = supp.get("section_titles_zh", {})
    titles_en = supp.get("section_titles_en", {})
    by_topic = supp.get("answers_by_topic", {})

    def _cells_for_topic(tk: str) -> Optional[List[Any]]:
        row = by_topic.get(tk)
        return list(row) if isinstance(row, list) else None

    if topic_key == "unit_4_all":
        flat: List[Any] = []
        for tk in _SLICE_ORDER_U4:
            cells = _cells_for_topic(tk)
            if not cells:
                print("Warning: missing Unit 4 answers for", tk)
                return
            flat.extend(cells)
        if len(flat) != len(questions) or len(manifest) != len(questions):
            print(
                "Warning: unit_4_all length mismatch; skip answer enrichment.",
                len(flat),
                len(questions),
                len(manifest),
            )
            return
        for i, q in enumerate(questions):
            _attach_unit1_answer_row(
                q, flat[i], manifest[i], titles_zh, titles_en, expl_en_ov
            )
            m = manifest[i]
            _apply_slot_walkthrough(
                q,
                "geometry",
                str(m.get("topic_key", "")),
                int(m.get("topic_local_index", 0)),
                walkthroughs or {},
            )
    elif topic_key in by_topic:
        cells = _cells_for_topic(topic_key)
        sub = [row for row in manifest if row.get("topic_key") == topic_key]
        if not cells or len(cells) != len(questions) or len(sub) != len(questions):
            print(
                "Warning: Unit 4 slice",
                topic_key,
                "answer length mismatch; skip enrichment.",
                len(cells or []),
                len(questions),
            )
            return
        for j, q in enumerate(questions):
            _attach_unit1_answer_row(
                q, cells[j], sub[j], titles_zh, titles_en, expl_en_ov
            )
            sj = sub[j]
            _apply_slot_walkthrough(
                q,
                "geometry",
                str(sj.get("topic_key", topic_key)),
                int(sj.get("topic_local_index", j)),
                walkthroughs or {},
            )


def build_bank():
    bank = {}
    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_topics": 0,
        "successful_topics": 0,
        "failed_topics": [],
        "empty_topics": [],
    }

    for domain, topics in BANKS.items():
        domain_payload = {}
        for topic_key, rel_path in topics.items():
            report["total_topics"] += 1
            full_path = os.path.join(APP_DIR, rel_path)

            if not os.path.isfile(full_path):
                report["failed_topics"].append(
                    {
                        "domain": domain,
                        "topic": topic_key,
                        "path": rel_path,
                        "reason": "file_not_found",
                    }
                )
                continue

            try:
                if domain == "placement":
                    questions = parse_placement_tex_file(full_path)
                    with open(full_path, "r", encoding="utf-8") as pf:
                        tex_full = pf.read()
                    keys = parse_placement_answer_key(tex_full)
                    for i, q in enumerate(questions):
                        ca = keys.get(i + 1)
                        if ca:
                            q["correct_answer"] = ca
                else:
                    questions = parse_tex_file(full_path)
            except Exception as exc:
                report["failed_topics"].append(
                    {
                        "domain": domain,
                        "topic": topic_key,
                        "path": rel_path,
                        "reason": "parse_error",
                        "error": str(exc),
                    }
                )
                continue

            if not questions:
                report["empty_topics"].append(
                    {
                        "domain": domain,
                        "topic": topic_key,
                        "path": rel_path,
                    }
                )
                continue

            domain_payload[topic_key] = questions
            report["successful_topics"] += 1

        if domain_payload:
            if domain == "algebra":
                order = ("1_1", "1_2", "1_3", "1_4", "1_5")
                if all(domain_payload.get(k) for k in order):
                    merged: List[Any] = []
                    for k in order:
                        merged.extend(domain_payload[k])
                    domain_payload["unit_1_all"] = merged
            elif domain == "advanced_math":
                order2 = ("2_1", "2_2", "2_3")
                if all(domain_payload.get(k) for k in order2):
                    merged2: List[Any] = []
                    for k in order2:
                        merged2.extend(domain_payload[k])
                    domain_payload["unit_2_all"] = merged2
            elif domain == "problem_solving":
                order3 = ("3_1", "3_2", "3_3", "3_4", "3_5", "3_6", "3_7")
                if all(domain_payload.get(k) for k in order3):
                    merged3: List[Any] = []
                    for k in order3:
                        merged3.extend(domain_payload[k])
                    domain_payload["unit_3_all"] = merged3
            elif domain == "geometry":
                order4 = ("4_1", "4_2", "4_3", "4_4")
                if all(domain_payload.get(k) for k in order4):
                    merged4: List[Any] = []
                    for k in order4:
                        merged4.extend(domain_payload[k])
                    domain_payload["unit_4_all"] = merged4
            bank[domain] = domain_payload

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    sat_wt = _sat_walkthrough_map()

    alg = bank.get("algebra", {})
    if alg.get("unit_1_all"):
        mrows = _manifest_from_algebra_payload(alg)
        if mrows:
            with open(UNIT1_MANIFEST, "w", encoding="utf-8") as f:
                json.dump(mrows, f, ensure_ascii=False, indent=2)
        else:
            mrows = _load_json(UNIT1_MANIFEST)
        if mrows:
            _enrich_unit1_algebra_questions(
                "unit_1_all", alg["unit_1_all"], mrows, sat_wt
            )
            for tk in _SLICE_ORDER:
                if tk in alg:
                    _enrich_unit1_algebra_questions(tk, alg[tk], mrows, sat_wt)

    adv = bank.get("advanced_math", {})
    if adv.get("unit_2_all"):
        mrows2 = _manifest_from_unit2_payload(adv)
        if mrows2:
            with open(UNIT2_MANIFEST, "w", encoding="utf-8") as f:
                json.dump(mrows2, f, ensure_ascii=False, indent=2)
        else:
            mrows2 = _load_json(UNIT2_MANIFEST)
        if mrows2:
            _enrich_unit2_algebra_questions(
                "unit_2_all", adv["unit_2_all"], mrows2, sat_wt
            )
            for tk in _SLICE_ORDER_U2:
                if tk in adv:
                    _enrich_unit2_algebra_questions(tk, adv[tk], mrows2, sat_wt)

    ps = bank.get("problem_solving", {})
    if ps.get("unit_3_all"):
        mrows3 = _manifest_from_unit3_payload(ps)
        if mrows3:
            with open(UNIT3_MANIFEST, "w", encoding="utf-8") as f:
                json.dump(mrows3, f, ensure_ascii=False, indent=2)
        else:
            mrows3 = _load_json(UNIT3_MANIFEST)
        if mrows3:
            _enrich_unit3_questions(
                "unit_3_all", ps["unit_3_all"], mrows3, sat_wt
            )
            for tk in _SLICE_ORDER_U3:
                if tk in ps:
                    _enrich_unit3_questions(tk, ps[tk], mrows3, sat_wt)

    geo = bank.get("geometry", {})
    if geo.get("unit_4_all"):
        mrows4 = _manifest_from_unit4_payload(geo)
        if mrows4:
            with open(UNIT4_MANIFEST, "w", encoding="utf-8") as f:
                json.dump(mrows4, f, ensure_ascii=False, indent=2)
        else:
            mrows4 = _load_json(UNIT4_MANIFEST)
        if mrows4:
            _enrich_unit4_questions(
                "unit_4_all", geo["unit_4_all"], mrows4, sat_wt
            )
            for tk in _SLICE_ORDER_U4:
                if tk in geo:
                    _enrich_unit4_questions(tk, geo[tk], mrows4, sat_wt)

    with open(OUTPUT_BANK, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("Wrote:", OUTPUT_BANK)
    print("Wrote:", OUTPUT_REPORT)
    print("Successful topics:", report["successful_topics"])
    print("Failed topics:", len(report["failed_topics"]))
    print("Empty topics:", len(report["empty_topics"]))


if __name__ == "__main__":
    build_bank()
