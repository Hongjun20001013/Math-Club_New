"""English placement advisor report — Reading, Language, Writing modules."""

from __future__ import annotations

from typing import Any

from placement_english_rubrics import WRITING_SCORE_BANDS, writing_score_band

ENGLISH_PARTS: dict[str, list[dict[str, str]]] = {
    "english_g7_8": [
        {"key": "reading", "part": "Part I", "title": "Reading", "range": "Q1–9 · 9 items"},
        {"key": "language", "part": "Part II", "title": "Language & conventions", "range": "Q10–31 · 22 items"},
        {"key": "writing", "part": "Part III", "title": "Writing (essay)", "range": "20 points · advisor scored"},
    ],
    "english_g9_11": [
        {"key": "reading", "part": "Part I", "title": "Reading", "range": "Q1–12 · 12 items"},
        {"key": "language", "part": "Part II", "title": "Language & conventions", "range": "Q13–40 · 28 items"},
        {"key": "writing", "part": "Part III", "title": "Writing (essay)", "range": "20 points · advisor scored"},
    ],
}


def _mcq_readiness(correct: int, total: int) -> dict[str, str]:
    if total <= 0:
        return {
            "status": "empty",
            "status_label": "—",
            "interpretation": "No scored items in this part.",
        }
    pct = round(100.0 * correct / total)
    if pct >= 85:
        return {
            "status": "strong",
            "status_label": "Strong",
            "interpretation": f"High accuracy ({pct}%). Ready for rigorous work in this skill area.",
        }
    if pct >= 70:
        return {
            "status": "solid",
            "status_label": "Solid",
            "interpretation": f"Grade-level performance ({pct}%). Targeted review on misses will help.",
        }
    if pct >= 55:
        return {
            "status": "developing",
            "status_label": "Developing",
            "interpretation": f"Mixed results ({pct}%). Explicit teaching in this part is recommended.",
        }
    return {
        "status": "needs_support",
        "status_label": "Needs support",
        "interpretation": f"This part needs structured support ({pct}% correct).",
    }


def _writing_readiness(points: int | None, max_pts: int) -> dict[str, str]:
    if points is None:
        return {
            "status": "review",
            "status_label": "Awaiting grade",
            "interpretation": "Essay submitted — score with the official 20-point rubric.",
        }
    band = writing_score_band(int(points))
    return {
        "status": "graded",
        "status_label": band.get("title") or band.get("range") or "Graded",
        "interpretation": band.get("summary") or "",
        "writing_band": band,
    }


def build_english_section_stats(
    topic: str,
    questions: list[dict],
    items: list[dict],
    english_writing: dict | None,
) -> list[dict[str, Any]]:
    buckets: dict[str, list[int]] = {"reading": [0, 0], "language": [0, 0]}
    for row, q in zip(items, questions):
        sec = str(q.get("placement_section") or "")
        if sec not in buckets:
            continue
        if str(row.get("question_kind") or q.get("question_kind") or "") == "english_writing":
            continue
        buckets[sec][1] += 1
        if row.get("status") == "correct":
            buckets[sec][0] += 1

    out: list[dict[str, Any]] = []
    for spec in ENGLISH_PARTS.get(topic, []):
        key = spec["key"]
        if key == "writing":
            wmax = int((english_writing or {}).get("max_points") or 20)
            wpts = (english_writing or {}).get("points")
            if wpts is None:
                wpts = (english_writing or {}).get("total_points")
            reading = _writing_readiness(wpts if wpts is not None else None, wmax)
            scored = wpts is not None
            out.append(
                {
                    "section": key,
                    "title_en": spec["title"],
                    "part_label": spec["part"],
                    "area_title": spec["title"],
                    "range_label": spec["range"],
                    "correct": int(wpts) if scored else 0,
                    "total": wmax,
                    "pct": round(100.0 * int(wpts) / wmax) if scored and wmax else 0,
                    "paper": not scored,
                    "paper_kind": True,
                    "item_count": 1,
                    "status": reading["status"],
                    "status_label": reading["status_label"],
                    "interpretation": reading["interpretation"],
                    "is_writing": True,
                }
            )
            continue
        correct, total = buckets.get(key, [0, 0])
        reading = _mcq_readiness(correct, total)
        pct = round(100.0 * correct / total) if total else 0
        out.append(
            {
                "section": key,
                "title_en": spec["title"],
                "part_label": spec["part"],
                "area_title": spec["title"],
                "range_label": spec["range"],
                "correct": correct,
                "total": total,
                "pct": pct,
                "paper": False,
                "status": reading["status"],
                "status_label": reading["status_label"],
                "interpretation": reading["interpretation"],
                "is_writing": False,
            }
        )
    return out


def build_english_placement_report(
    topic: str,
    mcq_correct: int,
    mcq_total: int,
    mcq_recommendation: dict | None,
    english_writing: dict | None,
) -> dict[str, Any]:
    wmax = int((english_writing or {}).get("max_points") or 20)
    wpts = (english_writing or {}).get("points")
    if wpts is None:
        wpts = (english_writing or {}).get("total_points")
    writing_graded = wpts is not None
    writing_band = writing_score_band(int(wpts)) if writing_graded else None

    mcq_pct = round(100.0 * mcq_correct / mcq_total) if mcq_total else 0
    headline = "English placement snapshot"
    if mcq_recommendation:
        headline = str(mcq_recommendation.get("title") or headline)

    summary_lines: list[str] = []
    if mcq_recommendation:
        summary_lines.append(
            str(mcq_recommendation.get("headline") or mcq_recommendation.get("summary") or "")
        )
    if writing_graded and writing_band:
        summary_lines.append(
            f"Writing {int(wpts)}/{wmax} ({writing_band.get('range')} · {writing_band.get('title')})."
        )
    elif english_writing and (english_writing.get("body") or english_writing.get("needs_grade")):
        summary_lines.append("Writing essay is submitted and awaiting advisor score.")

    essay_excerpt = ""
    if english_writing:
        body = str(english_writing.get("body") or "").strip()
        if body:
            essay_excerpt = body if len(body) <= 320 else body[:317].rstrip() + "…"

    return {
        "mcq_correct": mcq_correct,
        "mcq_total": mcq_total,
        "mcq_pct": mcq_pct,
        "mcq_recommendation": mcq_recommendation,
        "writing_points": int(wpts) if writing_graded else None,
        "writing_max": wmax,
        "writing_graded": writing_graded,
        "writing_band": writing_band,
        "headline": headline,
        "summary": " ".join(s for s in summary_lines if s).strip(),
        "essay_excerpt": essay_excerpt,
        "essay_review_href": (english_writing or {}).get("review_href"),
        "combined_graded": writing_graded,
        "combined_points": (mcq_correct + int(wpts)) if writing_graded else None,
        "combined_max": mcq_total + wmax,
    }


def criterion_performance_level(points: int, max_points: int) -> str:
    cap = max(1, int(max_points))
    pts = max(0, int(points))
    if pts >= cap * 0.75:
        return "strong"
    if pts >= cap * 0.4:
        return "partial"
    return "weak"


def build_english_writing_pdf_payload(
    topic: str,
    english_writing: dict | None,
    english_report: dict | None,
) -> dict[str, Any] | None:
    if not english_writing:
        return None
    rubric = english_writing.get("rubric") or {}
    criteria = list(rubric.get("criteria") or [])
    breakdown = dict(english_writing.get("breakdown") or {})
    wmax = int(english_writing.get("max_points") or 20)
    wpts = english_writing.get("points")
    if wpts is None:
        wpts = english_writing.get("total_points")
    graded = wpts is not None
    band = writing_score_band(int(wpts)) if graded else None
    body = str(english_writing.get("body") or "").strip()
    essay_excerpt = body if len(body) <= 2400 else body[:2397].rstrip() + "…"
    rows: list[dict[str, Any]] = []
    for crit in criteria:
        cid = str(crit.get("id") or "")
        cap = int(crit.get("max_points") or 0)
        pts = breakdown.get(cid)
        if pts is None and graded:
            pts = 0
        level = criterion_performance_level(int(pts or 0), cap) if graded else ""
        desc_key = level if level in ("strong", "partial", "weak") else "partial"
        descriptor = str(crit.get(desc_key) or "")
        rows.append(
            {
                "id": cid,
                "label": str(crit.get("label") or ""),
                "max_points": cap,
                "points": int(pts) if pts is not None else None,
                "level": level.title() if level else "—",
                "descriptor": descriptor,
                "strong": str(crit.get("strong") or ""),
                "partial": str(crit.get("partial") or ""),
                "weak": str(crit.get("weak") or ""),
            }
        )
    rep = english_report or {}
    mcq_rec = rep.get("mcq_recommendation") if isinstance(rep.get("mcq_recommendation"), dict) else None
    return {
        "topic": topic,
        "title": str(rubric.get("title") or "Writing"),
        "option": str(english_writing.get("option") or ""),
        "word_count": int(english_writing.get("word_count") or 0),
        "word_min": int(english_writing.get("word_min") or 0),
        "word_max": int(english_writing.get("word_max") or 0),
        "graded": graded,
        "total_points": int(wpts) if graded else None,
        "max_points": wmax,
        "score_band": band,
        "criteria_rows": rows,
        "essay_excerpt": essay_excerpt,
        "mcq_recommendation": mcq_rec,
        "score_bands": list(WRITING_SCORE_BANDS),
    }
