"""
Olivia-style bilingual placement assessment PDF (fpdf2 + Noto Sans SC).

Uses Noto Sans SC for all text when available (reliable CJK embedding).
Measured multi-line table rows keep English and Chinese from overlapping.
"""

from __future__ import annotations

import os
from io import BytesIO
from typing import Any, Sequence

from placement_report_pdf import (
    FPDF,
    XPos,
    YPos,
    _FPDF2_INSTALL_HINT,
    _answer_display_for_pdf,
    _content_width,
    _pdf_brand_name,
    _strip_html,
)

_APP_DIR = os.path.dirname(os.path.abspath(__file__))

_C_NAVY = (42, 36, 70)
_C_INK = (32, 27, 51)
_C_MUTED = (97, 91, 115)
_C_VIOLET = (107, 76, 194)
_C_DEEP = (79, 50, 152)
_C_LINE = (216, 204, 245)
_C_PLUM_BG = (239, 232, 255)
_C_LILAC_BG = (250, 247, 255)
_C_ROSE_BG = (255, 245, 250)
_C_GOLD_BG = (255, 248, 232)
_C_WHITE = (255, 255, 255)
_C_ROW_A = (252, 250, 255)
_C_ROW_B = (246, 243, 255)


def _setup_bilingual_font(pdf: Any) -> str:
    """Return one Unicode font for the whole report (Noto SC preferred)."""
    font_dir = os.path.join(_APP_DIR, "fonts")
    candidates = (
        os.path.join(font_dir, "NotoSansSC-Regular.otf"),
        os.path.join(font_dir, "NotoSansSC-Regular.ttf"),
    )
    for path in candidates:
        try:
            if os.path.isfile(path):
                pdf.add_font("NotoSC", "", path)
                return "NotoSC"
        except Exception:
            continue
    return "Helvetica"


def _clean(s: str) -> str:
    return _strip_html(s or "").replace("\n", " ").strip()


def _bilingual_block(en: str, zh: str = "") -> str:
    en = _clean(en)
    zh = _clean(zh)
    if en and zh:
        return f"{en}\n{zh}"
    return en or zh


def _set_font(pdf: FPDF, primary: str, size: float, style: str = "") -> None:
    if primary == "NotoSC":
        pdf.set_font(primary, "", size)
    else:
        pdf.set_font(primary, style, size)


def _line_count(text: str, col_width_mm: float, font_size_pt: float) -> int:
    """Fast wrap estimate — avoids fpdf offset_rendering (OOM on Render)."""
    if not text:
        return 1
    char_w_mm = max(1.0, font_size_pt * 0.19)
    cols = max(4, int(col_width_mm / char_w_mm))
    total = 0
    for raw in text.split("\n"):
        line = raw.strip() or " "
        units = sum(2 if ord(ch) > 127 else 1 for ch in line)
        total += max(1, (units + cols - 1) // cols)
    return max(1, total)


def _measure_cell_height(
    width: float,
    text: str,
    line_h: float,
    font_size: float = 8.0,
    pad: float = 1.8,
) -> float:
    lines = _line_count(text, max(8.0, width - 2.4), font_size)
    return lines * line_h + pad


def _draw_table_row(
    pdf: FPDF,
    primary: str,
    col_widths: Sequence[float],
    cells: Sequence[str],
    *,
    y: float | None = None,
    line_h: float = 4.0,
    font_size: float = 8.0,
    header: bool = False,
    fill: tuple[int, int, int] | None = None,
    min_h: float = 8.0,
) -> float:
    """Draw one table row with equal-height cells; text wraps inside each cell."""
    x0 = pdf.l_margin
    y0 = y if y is not None else pdf.get_y()
    if header:
        pdf.set_text_color(*_C_WHITE)
    else:
        pdf.set_text_color(*_C_INK)

    heights = [
        _measure_cell_height(max(8, w - 2.4), cell, line_h, font_size=font_size)
        for w, cell in zip(col_widths, cells)
    ]
    row_h = max(min_h, *heights)
    x = x0
    for w, cell in zip(col_widths, cells):
        if header:
            pdf.set_fill_color(*_C_DEEP)
        elif fill:
            pdf.set_fill_color(*fill)
        pdf.rect(x, y0, w, row_h, style="DF" if (fill or header) else "D")
        pdf.set_xy(x + 1.2, y0 + 1.5)
        _set_font(pdf, primary, font_size)
        pdf.multi_cell(w - 2.4, line_h, cell or "", align="L")
        x += w
    pdf.set_xy(x0, y0 + row_h)
    pdf.set_text_color(*_C_INK)
    return y0 + row_h


class _BilingualReportPDF(FPDF):
    def __init__(self, primary: str, header_label: str) -> None:
        super().__init__(orientation="P", unit="mm", format="Letter")
        self._primary = primary
        self._header = header_label
        self.set_margins(15.8, 15.8, 15.8)
        self.set_auto_page_break(True, margin=17)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_draw_color(*_C_LINE)
        self.set_line_width(0.25)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)
        _set_font(self, self._primary, 8)
        self.set_text_color(*_C_MUTED)
        uw = self.w - self.l_margin - self.r_margin
        self.cell(uw * 0.34, 4.2, f"{_pdf_brand_name()} Learning Center", align="L")
        self.cell(uw * 0.32, 4.2, self._header, align="C")
        self.cell(
            uw * 0.34,
            4.2,
            f"Page {self.page_no()}/{{nb}}",
            align="R",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        self.set_text_color(*_C_INK)


def _section_title(pdf: FPDF, primary: str, en: str, zh: str = "") -> None:
    pdf.ln(2)
    w = _content_width(pdf)
    _set_font(pdf, primary, 13)
    pdf.set_text_color(*_C_NAVY)
    pdf.cell(w * 0.58, 6.5, en, align="L")
    if zh:
        _set_font(pdf, primary, 11)
        pdf.set_text_color(*_C_DEEP)
        pdf.cell(w * 0.42, 6.5, zh, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.ln(6.5)
    y = pdf.get_y()
    pdf.set_draw_color(*_C_LINE)
    pdf.set_line_width(0.45)
    pdf.line(pdf.l_margin, y, pdf.l_margin + w, y)
    pdf.ln(4.5)
    pdf.set_text_color(*_C_INK)


def _metric_card(
    pdf: FPDF,
    primary: str,
    x: float,
    y: float,
    w: float,
    h: float,
    value: str,
    label_en: str,
    label_zh: str,
    bg: tuple[int, int, int],
) -> None:
    pdf.set_fill_color(*bg)
    pdf.set_draw_color(*_C_LINE)
    pdf.rect(x, y, w, h, "DF", round_corners=True, corner_radius=3)
    _set_font(pdf, primary, 14)
    pdf.set_text_color(*_C_NAVY)
    pdf.set_xy(x, y + 3.5)
    pdf.cell(w, 7.5, value[:20], align="C")
    _set_font(pdf, primary, 7.2)
    pdf.set_text_color(*_C_MUTED)
    pdf.set_xy(x, y + 11)
    pdf.cell(w, 3.8, label_en, align="C")
    if label_zh:
        pdf.set_xy(x, y + 14.2)
        pdf.cell(w, 3.8, label_zh, align="C")
    pdf.set_text_color(*_C_INK)


def _draw_hero(pdf: FPDF, primary: str, report: dict[str, Any]) -> None:
    w = _content_width(pdf)
    _set_font(pdf, primary, 7.5)
    pdf.set_text_color(*_C_DEEP)
    pdf.cell(0, 4.2, "NOVEL PREP LEARNING CENTER · MATHEMATICS PLACEMENT", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    y0 = pdf.get_y()
    box_h = 36
    pdf.set_fill_color(*_C_NAVY)
    pdf.set_draw_color(*_C_VIOLET)
    pdf.rect(pdf.l_margin, y0, w, box_h, "DF", round_corners=True, corner_radius=4)
    pdf.set_fill_color(*_C_VIOLET)
    pdf.rect(pdf.l_margin, y0, 4, box_h, "F")

    pdf.set_text_color(*_C_WHITE)
    pdf.set_xy(pdf.l_margin + 8, y0 + 5)
    _set_font(pdf, primary, 8)
    pdf.cell(w - 16, 5.2, "STUDENT ASSESSMENT REPORT · 学生测试报告", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(pdf.l_margin + 8)
    _set_font(pdf, primary, 16)
    pdf.cell(w - 16, 7.5, str(report.get("topic_title_en") or ""), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(pdf.l_margin + 8)
    _set_font(pdf, primary, 10)
    subtitle = _bilingual_block(
        str(report.get("report_subtitle_en") or ""),
        str(report.get("report_subtitle_zh") or ""),
    ).replace("\n", " · ")
    pdf.cell(w - 16, 5.2, subtitle, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(pdf.l_margin + 8)
    _set_font(pdf, primary, 9)
    left = f"Student 学生：{report.get('student_name') or 'Student'}"
    right = f"Attempt 编号：{report.get('attempt_id') or ''}"
    pdf.cell((w - 16) * 0.62, 5.2, left)
    pdf.cell((w - 16) * 0.38, 5.2, right, align="R")
    pdf.set_text_color(*_C_INK)
    pdf.set_xy(pdf.l_margin, y0 + box_h + 6)


def _draw_metrics(pdf: FPDF, primary: str, metrics: dict[str, Any]) -> None:
    w = _content_width(pdf)
    gap = 3
    cw = (w - 3 * gap) / 4
    y = pdf.get_y()
    h = 19
    placement = str(metrics.get("placement_label_en") or "")
    if len(placement) > 18:
        placement = placement[:16] + "…"
    cards = [
        (f"{metrics.get('correct')}/{metrics.get('total_gradable')}", "Corrected Score", "修正分数", _C_PLUM_BG),
        (f"{metrics.get('accuracy_pct')}%", "Accuracy", "正确率", _C_LILAC_BG),
        (str(metrics.get("missed_skipped") or 0), "Missed / Skipped", "错/空", _C_ROSE_BG),
        (placement, "Placement", "推荐级别", _C_GOLD_BG),
    ]
    x = pdf.l_margin
    for val, en, zh, bg in cards:
        _metric_card(pdf, primary, x, y, cw, h, val, en, zh, bg)
        x += cw + gap
    pdf.set_xy(pdf.l_margin, y + h + 7)


def _draw_band_table(pdf: FPDF, primary: str, bands: list[dict[str, Any]]) -> None:
    _section_title(pdf, primary, "Score by Readiness Band", "各阶段能力表现")
    w = _content_width(pdf)
    cols = [w * 0.09, w * 0.22, w * 0.1, w * 0.09, w - w * 0.50]
    headers = ["Band", "Area 能力区间", "Score", "Rate", "Interpretation 说明"]

    def _header_row() -> None:
        _draw_table_row(pdf, primary, cols, headers, line_h=3.8, font_size=8.2, header=True, min_h=8)

    _header_row()
    for idx, b in enumerate(bands):
        if pdf.get_y() > pdf.h - pdf.b_margin - 14:
            pdf.add_page()
            _section_title(pdf, primary, "Score by Readiness Band (cont.)", "各阶段能力表现（续）")
            _header_row()
        fill = _C_ROW_A if idx % 2 == 0 else _C_ROW_B
        cells = [
            f"Part {b.get('code')}",
            _bilingual_block(str(b.get("label_en") or ""), str(b.get("label_zh") or "")),
            f"{b.get('correct')}/{b.get('total')}",
            f"{b.get('rate_pct')}%",
            _bilingual_block(str(b.get("interpretation_en") or ""), str(b.get("interpretation_zh") or "")),
        ]
        _draw_table_row(pdf, primary, cols, cells, line_h=4.0, font_size=8, fill=fill, min_h=8.5)
    pdf.ln(2)


def _draw_recommendation(pdf: FPDF, primary: str, rec: dict[str, Any]) -> None:
    _section_title(pdf, primary, "Placement Recommendation", "分班建议")
    w = _content_width(pdf)
    y0 = pdf.get_y()
    box_h = 30
    pdf.set_fill_color(*_C_LILAC_BG)
    pdf.set_draw_color(*_C_LINE)
    pdf.rect(pdf.l_margin, y0, w, box_h, "DF", round_corners=True, corner_radius=3)
    pdf.set_fill_color(*_C_VIOLET)
    pdf.rect(pdf.l_margin, y0, 3, box_h, "F")

    pdf.set_xy(pdf.l_margin + 6, y0 + 4)
    _set_font(pdf, primary, 12.5)
    pdf.set_text_color(*_C_NAVY)
    pdf.cell(w - 12, 6.2, f"Recommended Placement: {rec.get('title_en')}", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(pdf.l_margin + 6)
    _set_font(pdf, primary, 10.5)
    pdf.set_text_color(*_C_MUTED)
    pdf.cell(w - 12, 5.2, f"建议级别：{rec.get('title_zh')}", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_text_color(*_C_INK)
    pdf.set_xy(pdf.l_margin, y0 + box_h + 3)
    for key in ("narrative_en", "narrative_zh"):
        txt = _clean(str(rec.get(key) or ""))
        if txt:
            _set_font(pdf, primary, 9)
            pdf.multi_cell(w, 4.5, txt, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)


def _draw_list_box(
    pdf: FPDF,
    primary: str,
    x: float,
    y: float,
    w: float,
    title_en: str,
    title_zh: str,
    items: list[dict[str, str]],
    tone: str,
) -> float:
    bg = _C_LILAC_BG if tone == "strength" else _C_ROSE_BG
    border = _C_VIOLET if tone == "strength" else (122, 74, 160)

    pdf.set_fill_color(*border)
    pdf.rect(x, y, w, 7.8, "F")
    pdf.set_text_color(*_C_WHITE)
    _set_font(pdf, primary, 8.5)
    pdf.set_xy(x + 2.5, y + 1.9)
    pdf.cell(w - 5, 5.2, f"{title_en} · {title_zh}")

    line_h = 4.2
    blocks: list[str] = []
    for item in items[:5]:
        blocks.append(_bilingual_block(item.get("en") or "", item.get("zh") or ""))
    body_text = "\n\n".join(f"- {b}" for b in blocks if b) or "- —"
    body_h = _measure_cell_height(w - 6, body_text, line_h, font_size=8, pad=3.2) + 2

    pdf.set_fill_color(*bg)
    pdf.set_draw_color(*border)
    pdf.set_text_color(*_C_INK)
    pdf.rect(x, y + 7.8, w, body_h, "DF")
    pdf.set_xy(x + 3, y + 10.2)
    _set_font(pdf, primary, 8)
    pdf.multi_cell(w - 6, line_h, body_text)
    return y + 7.8 + body_h


def _draw_error_patterns(pdf: FPDF, primary: str, patterns: list[dict[str, Any]]) -> None:
    if not patterns:
        return
    _section_title(pdf, primary, "Error Pattern Summary", "错误类型总结")
    w = _content_width(pdf)
    cols = [w * 0.24, w * 0.52, w - w * 0.76]
    headers = ["Error Type 错误类型", "Observed Pattern 表现", "Sample Questions 例题"]
    _draw_table_row(pdf, primary, cols, headers, line_h=3.8, font_size=8, header=True, min_h=8)

    for idx, p in enumerate(patterns[:10]):
        if pdf.get_y() > pdf.h - pdf.b_margin - 12:
            pdf.add_page()
            _section_title(pdf, primary, "Error Pattern Summary (cont.)", "错误类型总结（续）")
            _draw_table_row(pdf, primary, cols, headers, line_h=3.8, font_size=8, header=True, min_h=8)
        fill = _C_PLUM_BG if idx % 2 == 0 else _C_LILAC_BG
        cells = [
            _bilingual_block(str(p.get("type_en") or ""), str(p.get("type_zh") or "")),
            _bilingual_block(str(p.get("pattern_en") or ""), str(p.get("pattern_zh") or "")),
            str(p.get("sample_questions") or ""),
        ]
        _draw_table_row(pdf, primary, cols, cells, line_h=4.0, font_size=7.8, fill=fill, min_h=9)
    pdf.ln(2)


def _draw_missed_table(pdf: FPDF, primary: str, items: list[dict[str, Any]]) -> None:
    if not items:
        return
    _section_title(pdf, primary, "Incorrect / Skipped Questions", "错题与空题清单")
    w = _content_width(pdf)
    cols = [w * 0.06, w * 0.07, w * 0.17, w * 0.17, w - w * 0.47]
    headers = ["Q", "Part", "Student", "Correct", "Note 批改说明"]

    def _header_row() -> None:
        _draw_table_row(pdf, primary, cols, headers, line_h=3.6, font_size=7.8, header=True, min_h=7.5)

    _header_row()
    for idx, it in enumerate(items):
        if pdf.get_y() > pdf.h - pdf.b_margin - 10:
            pdf.add_page()
            _section_title(pdf, primary, "Incorrect / Skipped (cont.)", "错题清单（续）")
            _header_row()
        fill = _C_ROW_A if idx % 2 == 0 else _C_ROW_B
        student = _answer_display_for_pdf(str(it.get("student") or ""))
        if student in ("—", "-", ""):
            student = "Skipped"
        cells = [
            str(it.get("q_display") or ""),
            str(it.get("part") or ""),
            student,
            _answer_display_for_pdf(str(it.get("correct") or "")),
            _bilingual_block(str(it.get("note_en") or ""), str(it.get("note_zh") or "")),
        ]
        _draw_table_row(pdf, primary, cols, cells, line_h=3.8, font_size=7.8, fill=fill, min_h=8)
    pdf.ln(2)


def _draw_study_plan(pdf: FPDF, primary: str, plan: list[dict[str, str]]) -> None:
    if not plan:
        return
    _section_title(pdf, primary, "Recommended Study Plan", "后续学习建议")
    w = _content_width(pdf)
    cols = [w * 0.22, w - w * 0.22]
    headers = ["Phase 阶段", "Focus 重点"]
    _draw_table_row(pdf, primary, cols, headers, line_h=3.8, font_size=8.2, header=True, min_h=8)
    for idx, row in enumerate(plan):
        fill = _C_PLUM_BG if idx % 2 == 0 else _C_LILAC_BG
        cells = [
            _bilingual_block(str(row.get("phase_en") or ""), str(row.get("phase_zh") or "")),
            _bilingual_block(str(row.get("focus_en") or ""), str(row.get("focus_zh") or "")),
        ]
        _draw_table_row(pdf, primary, cols, cells, line_h=4.0, font_size=8, fill=fill, min_h=8.5)
    pdf.ln(2)


def _draw_final_box(pdf: FPDF, primary: str, report: dict[str, Any]) -> None:
    _section_title(pdf, primary, "Final Evaluation", "最终评估")
    w = _content_width(pdf)
    final = report.get("final_evaluation") or {}
    for key in ("en", "zh"):
        txt = _clean(str(final.get(key) or ""))
        if txt:
            _set_font(pdf, primary, 9)
            pdf.multi_cell(w, 4.5, txt, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    teacher = report.get("teacher_summary") or {}
    y0 = pdf.get_y()
    summary = _bilingual_block(str(teacher.get("en") or ""), str(teacher.get("zh") or ""))
    box_h = max(24, _measure_cell_height(w - 14, summary, 4.0, font_size=8.5, pad=10))

    pdf.set_fill_color(*_C_LILAC_BG)
    pdf.set_draw_color(*_C_VIOLET)
    pdf.rect(pdf.l_margin, y0, w, box_h, "DF", round_corners=True, corner_radius=3)
    pdf.set_fill_color(*_C_VIOLET)
    pdf.rect(pdf.l_margin, y0, 3, box_h, "F")
    pdf.set_xy(pdf.l_margin + 6, y0 + 3)
    _set_font(pdf, primary, 9)
    pdf.set_text_color(*_C_NAVY)
    pdf.cell(w - 12, 5.2, "Teacher Summary · 教师总结", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(pdf.l_margin + 6)
    pdf.set_text_color(*_C_INK)
    _set_font(pdf, primary, 8.5)
    pdf.multi_cell(w - 12, 4.0, summary, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def build_bilingual_assessment_pdf(report: dict[str, Any]) -> bytes:
    if FPDF is None or XPos is None or YPos is None:
        raise ImportError(_FPDF2_INSTALL_HINT)

    header = f"{report.get('topic_title_en')} · Bilingual Report"
    pdf = _BilingualReportPDF("Helvetica", header)
    primary = _setup_bilingual_font(pdf)
    pdf._primary = primary  # type: ignore[attr-defined]

    pdf.set_title(f"{_pdf_brand_name()} - Placement assessment")
    pdf.alias_nb_pages()
    pdf.add_page()

    _draw_hero(pdf, primary, report)
    _draw_metrics(pdf, primary, report.get("metrics") or {})
    _draw_band_table(pdf, primary, report.get("bands") or [])

    pdf.add_page()
    _draw_recommendation(pdf, primary, report.get("recommendation") or {})
    _section_title(pdf, primary, "Strengths and Growth Areas", "优势与待提升点")
    w = _content_width(pdf)
    y_row = pdf.get_y()
    col_w = (w - 4) / 2
    bottom = _draw_list_box(
        pdf, primary, pdf.l_margin, y_row, col_w,
        "Strengths", "优势", report.get("strengths") or [], "strength",
    )
    bottom2 = _draw_list_box(
        pdf, primary, pdf.l_margin + col_w + 4, y_row, col_w,
        "Growth Areas", "待提升点", report.get("growth_areas") or [], "growth",
    )
    pdf.set_xy(pdf.l_margin, max(bottom, bottom2) + 5)
    _draw_error_patterns(pdf, primary, report.get("error_patterns") or [])
    _draw_missed_table(pdf, primary, report.get("missed_items") or [])

    pdf.add_page()
    _draw_study_plan(pdf, primary, report.get("study_plan") or [])
    _draw_final_box(pdf, primary, report)

    bio = BytesIO()
    pdf.output(bio)
    return bio.getvalue()
