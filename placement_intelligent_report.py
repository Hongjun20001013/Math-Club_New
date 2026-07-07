"""
Build structured bilingual placement assessment reports from session results.

Uses placement meta, per-topic skill maps, and the printed teacher guide
(16/20 band rule, study-plan bands) to generate Olivia-style report payloads.
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from typing import Any

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_MAP_CACHE: dict[str, dict] = {}


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _skill_map_for_topic(topic: str) -> dict | None:
    if topic in _SKILL_MAP_CACHE:
        return _SKILL_MAP_CACHE[topic]
    fname = {
        "middle_level": "placement_middle_level_skill_map.json",
    }.get(topic)
    if not fname:
        return None
    path = os.path.join(_APP_DIR, "data", fname)
    if not os.path.isfile(path):
        return None
    data = _load_json(path)
    _SKILL_MAP_CACHE[topic] = data
    return data


def _band_status(correct: int, total: int) -> str:
    if total <= 0:
        return "not_ready"
    if correct >= 18:
        return "pass_strong"
    if correct >= 16:
        return "pass"
    if correct >= 14:
        return "borderline"
    if correct >= 8:
        return "needs_support"
    return "not_ready"


def _band_interpretation(code: str, correct: int, total: int, status: str) -> tuple[str, str]:
    rate = round(100.0 * correct / total) if total else 0
    if status == "pass_strong":
        return (
            f"Strong foundation ({rate}%).",
            "基础计算与低阶应用较稳。",
        )
    if status == "pass":
        extras = {
            "II": (
                "Passed this band; review place value, division with remainder, and money setup.",
                "通过该阶段，但需复习 place value、division with remainder、money setup。",
            ),
            "III": (
                "Passed this band with room to tighten fraction/percent fluency.",
                "通过该阶段，但分数/百分比流畅度仍可加强。",
            ),
            "IV": (
                "Passed this band; keep practicing ratios and measurement.",
                "通过该阶段；继续巩固比例与测量。",
            ),
            "V": (
                "Passed the Algebra 1/2 readiness band on this run.",
                "本档 Algebra 1/2 准备度达标。",
            ),
        }
        return extras.get(
            code,
            (f"Passed this band ({rate}%).", f"通过该阶段（{rate}%）。"),
        )
    if status == "borderline":
        return (
            f"Borderline ({correct}/{total}). Slightly below the 16/20 advance line — first clear reinforcement band.",
            f"边缘（{correct}/{total}）。略低于 16/20 晋级线，是第一个需要明显补强的阶段。",
        )
    if status == "needs_support":
        return (
            f"Significant support needed ({rate}%). Ratios, measurement, geometry, or unit conversion gaps showed up.",
            f"需要明显支持（{rate}%）。比例、测量、几何或单位转换出现较多问题。",
        )
    if code == "V":
        return (
            "Not yet Algebra-ready. Do not place directly into Algebra 1.",
            "目前不建议直接进入 Algebra 1。",
        )
    return (
        f"Below the 16/20 band threshold ({correct}/{total}).",
        f"未达 16/20 档位线（{correct}/{total}）。",
    )


def _first_name(name: str) -> str:
    parts = re.split(r"\s+", (name or "").strip())
    return parts[0] if parts else "The student"


def _recommendation_from_bands(
    bands: list[dict[str, Any]], skill_map: dict, student_name: str
) -> dict[str, Any]:
    paths = skill_map.get("placement_paths") or []
    first_fail_idx: int | None = None
    for i, b in enumerate(bands):
        if int(b.get("correct") or 0) < 16:
            first_fail_idx = i
            break

    path_row = None
    for row in paths:
        fb = row.get("first_fail_band")
        if fb is None and first_fail_idx is None:
            path_row = row
            break
        if fb is not None and fb == first_fail_idx:
            path_row = row
            break
    if path_row is None:
        path_row = paths[-1] if paths else {}

    fn = _first_name(student_name)
    drop_band = bands[first_fail_idx]["code"] if first_fail_idx is not None else None
    if first_fail_idx is None:
        narrative_en = (
            f"{fn} met the 16/20 threshold across all five bands. "
            "A follow-up Algebra 1 or upper-school diagnostic is appropriate."
        )
        narrative_zh = (
            f"{fn} 在五个档位均达到 16/20。"
            "建议进行 Algebra 1 或更高阶诊断。"
        )
        pills = [
            {"en": "All bands passed", "zh": "各档达标", "tone": "plum"},
            {"en": "Consider Algebra 1+ diagnostic", "zh": "可考虑 Algebra 1+ 诊断", "tone": "plum"},
        ]
    elif first_fail_idx <= 1:
        narrative_en = (
            f"{fn} needs more work in early middle-school readiness before advancing. "
            "Use targeted arithmetic and place-value instruction first."
        )
        narrative_zh = (
            f"{fn} 在初中低阶准备度上仍需加强。"
            "建议先进行算术与位值的针对性训练。"
        )
        pills = [
            {"en": "Build Math 6 foundations", "zh": "巩固 Math 6 基础", "tone": "rose"},
            {"en": "Re-test Part I-II", "zh": "重测 Part I-II", "tone": "plum"},
        ]
    elif first_fail_idx == 2:
        narrative_en = (
            f"{fn} has a solid arithmetic foundation, but the score pattern shows a clear drop from Part III onward. "
            "The best next step is a targeted bridge course before Algebra 1 placement."
        )
        narrative_zh = (
            f"{fn} 的基础计算能力不错，但从 Part III 开始分数明显下降。"
            "建议先完成 Math 7 / Pre-Algebra 衔接，再考虑 Algebra 1 或更高阶测试。"
        )
        pills = [
            {"en": "Do not place directly into Algebra 1", "zh": "不建议直接进入 Algebra 1", "tone": "rose"},
            {"en": "Focus on Math 7-8 readiness", "zh": "重点补强 Math 7-8 准备度", "tone": "plum"},
        ]
    elif first_fail_idx == 3:
        narrative_en = (
            f"{fn} passed Parts I-III but Part IV measurement/ratio work needs support. "
            "A Math 8 / pre-algebra bridge is the best fit."
        )
        narrative_zh = (
            f"{fn} 已通过 Part I-III，但 Part IV 的比例与测量需要支持。"
            "建议进入 Math 8 / Pre-Algebra 衔接课程。"
        )
        pills = [
            {"en": "Math 8 bridge recommended", "zh": "建议 Math 8 衔接", "tone": "plum"},
            {"en": "Target ratios & measurement", "zh": "重点补比例与测量", "tone": "rose"},
        ]
    else:
        narrative_en = (
            f"{fn} shows middle-school readiness in earlier bands, but Part V is not yet secure. "
            "Use an Algebra 1/2 readiness bridge — not direct Algebra 1 placement."
        )
        narrative_zh = (
            f"{fn} 在前几档有初中准备度，但 Part V 尚未稳定。"
            "建议 Algebra 1/2 预备衔接，而非直接 Algebra 1。"
        )
        pills = [
            {"en": "Not direct Algebra 1", "zh": "暂不建议直接 Algebra 1", "tone": "rose"},
            {"en": "Strengthen Part V skills", "zh": "补强 Part V 能力", "tone": "plum"},
        ]

    return {
        "title_en": str(path_row.get("label_en") or "Placement recommendation"),
        "title_zh": str(path_row.get("label_zh") or "分班建议"),
        "bridge_en": str(path_row.get("bridge_en") or ""),
        "bridge_zh": str(path_row.get("bridge_zh") or ""),
        "narrative_en": narrative_en,
        "narrative_zh": narrative_zh,
        "pills": pills,
        "first_fail_band": drop_band,
    }


def _strengths_and_growth(
    bands: list[dict[str, Any]],
    incorrect_counts: dict[str, int],
    categories: dict,
    *,
    answered: int,
    total: int,
    skill_map: dict,
    first_fail_idx: int | None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    strengths: list[dict[str, str]] = []
    passed_bands = [b for b in bands if int(b.get("correct") or 0) >= 16]
    strong_bands = [b for b in bands if int(b.get("correct") or 0) >= 18]

    if strong_bands:
        codes = ", ".join(f"Part {b['code']}" for b in strong_bands[:2])
        strengths.append(
            {
                "en": f"Strong performance in {codes}.",
                "zh": f"{codes} 表现扎实。",
            }
        )
    if passed_bands:
        strengths.append(
            {
                "en": f"Passed {len(passed_bands)} readiness band(s) at the 16/20 threshold.",
                "zh": f"共有 {len(passed_bands)} 个档位达到 16/20 晋级线。",
            }
        )
    if bands and int(bands[0].get("correct") or 0) >= 14:
        strengths.append(
            {
                "en": "Foundational arithmetic skills are usable.",
                "zh": "基础四则运算能力可用。",
            }
        )
    if answered >= total * 0.85:
        strengths.append(
            {
                "en": "High completion rate on the full diagnostic.",
                "zh": "完成度高，诊断数据完整。",
            }
        )
    if not strengths:
        if answered < total * 0.5:
            strengths.append(
                {
                    "en": "Partial attempt captured — re-test when ready for a full profile.",
                    "zh": "本次为部分完成 — 建议补做后获得完整评估。",
                }
            )
        else:
            strengths.append(
                {
                    "en": "Attempt completed — review list below targets the highest-impact gaps.",
                    "zh": "测试已完成 — 下方清单标出最高优先级的提升点。",
                }
            )

    growth: list[dict[str, str]] = []
    ranked = sorted(incorrect_counts.items(), key=lambda x: (-x[1], x[0]))
    for cat_key, count in ranked[:5]:
        cat = categories.get(cat_key) or {}
        label_en = str(cat.get("label_en") or cat_key.replace("_", " ").title())
        label_zh = str(cat.get("label_zh") or label_en)
        growth.append(
            {
                "en": f"{label_en} ({count} miss{'es' if count != 1 else ''})",
                "zh": f"{label_zh}（{count} 题）",
            }
        )

    if not growth:
        tier_key = "all_pass" if first_fail_idx is None else str(first_fail_idx)
        diag = (skill_map.get("diagnostic_study_plans") or {}).get(tier_key) or {}
        summary_en = str(diag.get("summary_focus_en") or "")
        summary_zh = str(diag.get("summary_focus_zh") or "")
        if summary_en:
            growth.append({"en": summary_en, "zh": summary_zh})
        elif answered < total * 0.5:
            growth.append(
                {
                    "en": "Complete the diagnostic first — skipped items prevent a skill profile.",
                    "zh": "请先完成诊断 — 跳过题目过多，无法形成技能画像。",
                }
            )

    defaults = [
        {"en": "Multi-step problem setup", "zh": "多步骤题目设定"},
        {"en": "Fractions, percents, and ratios", "zh": "分数、百分比、比例"},
        {"en": "Geometry and measurement", "zh": "几何、面积、体积和单位"},
    ]
    seen = {g["en"] for g in growth}
    for d in defaults:
        if len(growth) >= 5:
            break
        if d["en"] not in seen:
            growth.append(d)
    return strengths[:4], growth[:5]


def _error_patterns(
    missed_qnums: list[int], skill_map: dict
) -> list[dict[str, Any]]:
    categories = skill_map.get("categories") or {}
    questions = skill_map.get("questions") or {}
    by_cat: dict[str, list[int]] = defaultdict(list)
    for qn in missed_qnums:
        qmeta = questions.get(str(qn)) or {}
        cat = str(qmeta.get("category") or "basic_arithmetic")
        by_cat[cat].append(qn)

    out: list[dict[str, Any]] = []
    for cat_key, qlist in sorted(by_cat.items(), key=lambda x: (-len(x[1]), x[0])):
        cat = categories.get(cat_key) or {}
        qlist = sorted(qlist)
        if len(qlist) == 1:
            sample = f"Q{qlist[0]}"
        elif len(qlist) == 2:
            sample = f"Q{qlist[0]}, Q{qlist[1]}"
        else:
            sample = ", ".join(f"Q{q}" for q in qlist[:6])
            if len(qlist) > 6:
                sample += f", Q{qlist[-1]}"
        out.append(
            {
                "type_en": str(cat.get("label_en") or cat_key),
                "type_zh": str(cat.get("label_zh") or cat_key),
                "pattern_en": str(cat.get("pattern_en") or ""),
                "pattern_zh": str(cat.get("pattern_zh") or ""),
                "sample_questions": sample,
                "count": len(qlist),
            }
        )
    return out


def _study_plan(
    incorrect_counts: dict[str, int],
    skill_map: dict,
    bands: list[dict],
    *,
    skipped_count: int,
    answered: int,
    gradable_total: int,
    recommendation: dict[str, Any],
) -> list[dict[str, str]]:
    diag_plans = skill_map.get("diagnostic_study_plans") or {}
    first_fail = next((i for i, b in enumerate(bands) if int(b.get("correct") or 0) < 16), None)
    tier_key = "all_pass" if first_fail is None else str(first_fail)
    diag = diag_plans.get(tier_key) or diag_plans.get("0") or {}

    plan: list[dict[str, str]] = []
    if diag:
        summary_en = str(diag.get("summary_focus_en") or "")
        summary_zh = str(diag.get("summary_focus_zh") or "")
        lessons_en = str(diag.get("lessons_en") or "")
        lessons_zh = str(diag.get("lessons_zh") or "")
        plan.append(
            {
                "phase_en": str(diag.get("diagnostic_en") or recommendation.get("title_en") or ""),
                "phase_zh": str(diag.get("diagnostic_zh") or recommendation.get("title_zh") or ""),
                "focus_en": f"{lessons_en} — {summary_en}".strip(" —"),
                "focus_zh": f"{lessons_zh} — {summary_zh}".strip(" —"),
            }
        )

    skipped_ratio = skipped_count / gradable_total if gradable_total else 0.0
    if skipped_ratio > 0.5 or answered < gradable_total * 0.25:
        plan.append(
            {
                "phase_en": "First step",
                "phase_zh": "第一步",
                "focus_en": "Complete skipped items or re-take the full diagnostic before following this plan.",
                "focus_zh": "先补做跳过的题目或完整重做诊断，再按此计划补习。",
            }
        )

    for phase in diag.get("phases") or []:
        plan.append(
            {
                "phase_en": str(phase.get("phase_en") or ""),
                "phase_zh": str(phase.get("phase_zh") or ""),
                "focus_en": str(phase.get("focus_en") or ""),
                "focus_zh": str(phase.get("focus_zh") or ""),
            }
        )

    if incorrect_counts and skipped_ratio <= 0.5:
        categories = skill_map.get("categories") or {}
        top_cat, top_n = max(incorrect_counts.items(), key=lambda x: x[1])
        cat = categories.get(top_cat) or {}
        insert_at = max(1, len(plan) - 1)
        plan.insert(
            insert_at,
            {
                "phase_en": "Priority focus",
                "phase_zh": "优先补强",
                "focus_en": f"Target {cat.get('label_en', top_cat)} ({top_n} incorrect).",
                "focus_zh": f"重点突破{cat.get('label_zh', top_cat)}（{top_n} 题答错）。",
            },
        )

    return plan[:7]


def build_middle_level_intelligent_report(
    *,
    topic: str,
    topic_title: str,
    attempt_id: int,
    rows: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    section_stats: list[dict[str, Any]],
    placement_student: dict[str, str] | None,
    correct_count: int,
    gradable_total: int,
    score_pct: int,
    meta: dict,
) -> dict[str, Any]:
    skill_map = _skill_map_for_topic(topic)
    if not skill_map:
        return {}

    categories = skill_map.get("categories") or {}
    qmeta = skill_map.get("questions") or {}
    student_name = (placement_student or {}).get("name") or "Student"

    band_meta = meta.get("bands") or []
    band_by_code = {str(b.get("code")): b for b in band_meta if isinstance(b, dict)}
    stat_by_sec = {str(s.get("section")): s for s in section_stats}

    bands: list[dict[str, Any]] = []
    for code in ("I", "II", "III", "IV", "V"):
        stat = stat_by_sec.get(code, {})
        bmeta = band_by_code.get(code, {})
        correct = int(stat.get("correct") or 0)
        total = int(stat.get("total") or 20)
        status = _band_status(correct, total)
        interp_en, interp_zh = _band_interpretation(code, correct, total, status)
        bands.append(
            {
                "code": code,
                "label_en": str(bmeta.get("label") or stat.get("title_en") or f"Part {code}"),
                "label_zh": str(bmeta.get("label_zh") or bmeta.get("label") or ""),
                "correct": correct,
                "total": total,
                "rate_pct": round(100.0 * correct / total) if total else 0,
                "interpretation_en": interp_en,
                "interpretation_zh": interp_zh,
                "status": status,
            }
        )

    missed_items: list[dict[str, Any]] = []
    missed_qnums: list[int] = []
    incorrect_qnums: list[int] = []
    incorrect_counts: dict[str, int] = defaultdict(int)
    skipped_count = 0

    for row, qobj in zip(rows, questions):
        status = str(row.get("status") or "")
        if status not in ("incorrect", "skipped", "submitted"):
            continue
        qn = int(qobj.get("display_number") or row.get("q_display") or 0)
        if qn <= 0:
            continue
        missed_qnums.append(qn)
        qinfo = qmeta.get(str(qn)) or {}
        cat = str(qinfo.get("category") or "basic_arithmetic")
        if status == "skipped":
            skipped_count += 1
        else:
            incorrect_qnums.append(qn)
            incorrect_counts[cat] += 1
        yours = row.get("yours_display") or "—"
        if status == "skipped" or yours == "—":
            yours = "Skipped"
        missed_items.append(
            {
                "q_display": str(qn),
                "part": str(qobj.get("knowledge_section") or row.get("knowledge_section") or "—"),
                "student": str(yours),
                "correct": str(row.get("key_display") or "—"),
                "note_en": str(qinfo.get("note_en") or categories.get(cat, {}).get("pattern_en") or ""),
                "note_zh": str(qinfo.get("note_zh") or categories.get(cat, {}).get("pattern_zh") or ""),
                "status": status,
            }
        )

    missed_skipped = len(missed_items)
    answered = max(0, gradable_total - skipped_count)
    first_fail_idx = next(
        (i for i, b in enumerate(bands) if int(b.get("correct") or 0) < 16), None
    )
    recommendation = _recommendation_from_bands(bands, skill_map, student_name)
    strengths, growth = _strengths_and_growth(
        bands,
        incorrect_counts,
        categories,
        answered=answered,
        total=gradable_total,
        skill_map=skill_map,
        first_fail_idx=first_fail_idx,
    )
    error_patterns = _error_patterns(incorrect_qnums, skill_map)
    study_plan = _study_plan(
        incorrect_counts,
        skill_map,
        bands,
        skipped_count=skipped_count,
        answered=answered,
        gradable_total=gradable_total,
        recommendation=recommendation,
    )

    fn = _first_name(student_name)
    if answered < gradable_total * 0.25:
        final_en = (
            f"{fn} submitted an incomplete diagnostic ({answered}/{gradable_total} answered). "
            "Re-test when ready; the study plan below follows the placement tier, not skipped-item patterns."
        )
        final_zh = (
            f"{fn} 本次诊断完成度很低（作答 {answered}/{gradable_total}）。"
            "建议补做或重做；下方学习计划按分班档位制定，而非根据跳过题目推断。"
        )
    elif recommendation.get("first_fail_band"):
        if first_fail_idx is not None and first_fail_idx <= 1:
            final_en = (
                f"{fn} needs foundational middle-school readiness work before advancing. "
                "Targeted arithmetic and place-value instruction should produce clear gains."
            )
            final_zh = (
                f"{fn} 在初中低阶准备度上仍需加强。"
                "建议先进行算术与位值的针对性训练，提升空间明确。"
            )
        else:
            final_en = (
                f"{fn} shows usable skills in earlier bands, but the score profile does not support "
                "direct Algebra 1 placement yet. Targeted bridge instruction should produce clear gains."
            )
            final_zh = (
                f"{fn} 在前几档有一定基础，但修正后的成绩尚不支持直接进入 Algebra 1。"
                "针对薄弱点进行系统衔接训练，提升空间明确。"
            )
    else:
        final_en = (
            f"{fn} performed strongly across all readiness bands on this diagnostic. "
            "Confirm with classwork and a follow-up Algebra 1 or upper-school assessment."
        )
        final_zh = (
            f"{fn} 在各准备度档位表现扎实。"
            "建议结合课堂表现进行 Algebra 1 或更高阶诊断确认。"
        )

    teacher_en = (
        f"Recommended next step: {recommendation['title_en']}. "
        f"{recommendation.get('bridge_en') or ''}"
    ).strip()
    teacher_zh = (
        f"建议下一步：{recommendation['title_zh']}。"
        f"{recommendation.get('bridge_zh') or ''}"
    ).strip()

    brand = meta.get("brand") or {}
    return {
        "report_kind": "bilingual_assessment",
        "topic": topic,
        "topic_title_en": topic_title,
        "topic_title_zh": "初中段数学分班测试",
        "report_subtitle_en": "Graded Diagnostic Report",
        "report_subtitle_zh": "中英双语评估版",
        "student_name": student_name,
        "attempt_id": attempt_id,
        "metrics": {
            "correct": correct_count,
            "total_gradable": gradable_total,
            "accuracy_pct": score_pct,
            "missed_skipped": missed_skipped,
            "placement_label_en": recommendation["title_en"],
            "placement_label_zh": recommendation["title_zh"],
        },
        "bands": bands,
        "recommendation": recommendation,
        "strengths": strengths,
        "growth_areas": growth,
        "error_patterns": error_patterns,
        "missed_items": missed_items,
        "study_plan": study_plan,
        "final_evaluation": {"en": final_en, "zh": final_zh},
        "teacher_summary": {"en": teacher_en, "zh": teacher_zh},
        "brand_trust_en": str(brand.get("trust_line") or ""),
        "brand_trust_zh": str(brand.get("trust_line_zh") or ""),
    }


def build_generic_intelligent_report(
    *,
    topic: str,
    topic_title: str,
    attempt_id: int,
    rows: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    section_stats: list[dict[str, Any]],
    placement_student: dict[str, str] | None,
    placement_rec: dict[str, Any] | None,
    placement_gate_scores: list[dict[str, Any]] | None,
    correct_count: int,
    gradable_total: int,
    score_pct: int,
    meta: dict,
) -> dict[str, Any]:
    """Simpler bilingual report for upper-school / enhanced placement tests."""
    student_name = (placement_student or {}).get("name") or "Student"
    rec = placement_rec or {}
    gates = placement_gate_scores or []

    bands: list[dict[str, Any]] = []
    if gates:
        for g in gates:
            correct = int(g.get("correct") or 0)
            total = int(g.get("total") or 0)
            status = _band_status(correct, total)
            tier = str(g.get("pass_tier") or "")
            if tier == "strong":
                interp_en = "Strong pass on this gate."
                interp_zh = "本 Gate 表现扎实。"
            elif tier == "standard":
                interp_en = "Met the gate threshold."
                interp_zh = "达到本 Gate 门槛。"
            else:
                interp_en = "Below gate threshold — targeted review recommended."
                interp_zh = "未达 Gate 门槛 — 建议针对性复习。"
            bands.append(
                {
                    "code": str(g.get("gate") or ""),
                    "label_en": str(g.get("readiness_label") or g.get("title_en") or ""),
                    "label_zh": "",
                    "correct": correct,
                    "total": total,
                    "rate_pct": int(g.get("pct") or (round(100 * correct / total) if total else 0)),
                    "interpretation_en": interp_en,
                    "interpretation_zh": interp_zh,
                    "status": status,
                    "range": str(g.get("range") or ""),
                }
            )
    else:
        for s in section_stats:
            correct = int(s.get("correct") or 0)
            total = int(s.get("total") or 0)
            status = _band_status(correct, total)
            interp_en, interp_zh = _band_interpretation(
                str(s.get("section") or ""), correct, total, status
            )
            bands.append(
                {
                    "code": str(s.get("section") or ""),
                    "label_en": str(s.get("title_en") or ""),
                    "label_zh": "",
                    "correct": correct,
                    "total": total,
                    "rate_pct": int(s.get("pct") or 0),
                    "interpretation_en": interp_en,
                    "interpretation_zh": interp_zh,
                    "status": status,
                }
            )

    missed_items: list[dict[str, Any]] = []
    for row, qobj in zip(rows, questions):
        status = str(row.get("status") or "")
        if status not in ("incorrect", "skipped", "submitted"):
            continue
        yours = row.get("yours_display") or "—"
        if status == "skipped" or yours == "—":
            yours = "Skipped"
        missed_items.append(
            {
                "q_display": str(row.get("q_display") or ""),
                "part": str(qobj.get("knowledge_section") or row.get("knowledge_section") or "—"),
                "student": str(yours),
                "correct": str(row.get("key_display") or "—"),
                "note_en": str(qobj.get("knowledge_section_title_en") or "Review this item."),
                "note_zh": "请复习本题。",
                "status": status,
            }
        )

    highlights = rec.get("highlights") or []
    strengths = [{"en": str(h), "zh": ""} for h in highlights[:3] if h]
    if not strengths:
        strengths = [{"en": "Completed the diagnostic.", "zh": "已完成诊断。"}]

    growth = [
        {"en": f"Missed/skipped {len(missed_items)} item(s) — see itemized list.", "zh": f"共 {len(missed_items)} 题需复习。"}
    ]
    if missed_items:
        growth.append({"en": "Use misses as a personalized review list.", "zh": "以错题清单作为个性化复习计划。"})

    return {
        "report_kind": "bilingual_assessment",
        "topic": topic,
        "topic_title_en": topic_title,
        "topic_title_zh": "",
        "report_subtitle_en": "Placement Diagnostic Report",
        "report_subtitle_zh": "分班诊断报告",
        "student_name": student_name,
        "attempt_id": attempt_id,
        "metrics": {
            "correct": correct_count,
            "total_gradable": gradable_total,
            "accuracy_pct": score_pct,
            "missed_skipped": len(missed_items),
            "placement_label_en": str(rec.get("title") or "Placement recommendation"),
            "placement_label_zh": str(rec.get("title") or ""),
        },
        "bands": bands,
        "recommendation": {
            "title_en": str(rec.get("title") or "Placement recommendation"),
            "title_zh": str(rec.get("headline_zh") or rec.get("title") or ""),
            "bridge_en": str(rec.get("summary") or rec.get("headline") or ""),
            "bridge_zh": str(rec.get("summary_zh") or ""),
            "narrative_en": str(rec.get("headline") or ""),
            "narrative_zh": str(rec.get("headline_zh") or ""),
            "pills": [],
            "first_fail_band": None,
        },
        "strengths": strengths,
        "growth_areas": growth,
        "error_patterns": [],
        "missed_items": missed_items,
        "study_plan": [
            {
                "phase_en": "Next step",
                "phase_zh": "下一步",
                "focus_en": str(rec.get("summary") or "Review misses and re-assess."),
                "focus_zh": str(rec.get("summary_zh") or "复习错题并再次评估。"),
            }
        ],
        "final_evaluation": {
            "en": str(rec.get("summary") or ""),
            "zh": str(rec.get("summary_zh") or ""),
        },
        "teacher_summary": {
            "en": str(rec.get("headline") or ""),
            "zh": str(rec.get("headline_zh") or ""),
        },
        "brand_trust_en": str((meta.get("brand") or {}).get("trust_line") or ""),
        "brand_trust_zh": str((meta.get("brand") or {}).get("trust_line_zh") or ""),
    }


def build_intelligent_placement_report(
    *,
    topic: str,
    topic_title: str,
    attempt_id: int,
    rows: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    section_stats: list[dict[str, Any]],
    placement_student: dict[str, str] | None,
    placement_rec: dict[str, Any] | None,
    placement_gate_scores: list[dict[str, Any]] | None,
    correct_count: int,
    gradable_total: int,
    score_pct: int,
    meta: dict,
) -> dict[str, Any]:
    if topic == "middle_level":
        return build_middle_level_intelligent_report(
            topic=topic,
            topic_title=topic_title,
            attempt_id=attempt_id,
            rows=rows,
            questions=questions,
            section_stats=section_stats,
            placement_student=placement_student,
            correct_count=correct_count,
            gradable_total=gradable_total,
            score_pct=score_pct,
            meta=meta,
        )
    return build_generic_intelligent_report(
        topic=topic,
        topic_title=topic_title,
        attempt_id=attempt_id,
        rows=rows,
        questions=questions,
        section_stats=section_stats,
        placement_student=placement_student,
        placement_rec=placement_rec,
        placement_gate_scores=placement_gate_scores,
        correct_count=correct_count,
        gradable_total=gradable_total,
        score_pct=score_pct,
        meta=meta,
    )
