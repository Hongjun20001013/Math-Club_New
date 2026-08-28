"""Admin placement PDF that mirrors the on-screen advisor report page."""
from __future__ import annotations

from io import BytesIO
from typing import Any

from answer_grader import display_answer_plain
from placement_report_pdf import (
    FPDF,
    XPos,
    YPos,
    _FPDF2_INSTALL_HINT,
    _pdf_line_for_font,
    _setup_font,
)

_C_PAGE = (236, 234, 245)
_C_INK = (26, 20, 48)
_C_MUTED = (95, 87, 120)
_C_KICKER = (91, 77, 138)
_C_PURPLE = (79, 50, 186)
_C_LINE = (226, 222, 240)
_C_CARD = (255, 255, 255)
_C_CHIP = (244, 241, 252)
_C_CHIP_INK = (95, 87, 120)
_C_SOFT = (252, 250, 255)
_C_SOFT2 = (246, 243, 255)
_C_OK = (22, 101, 52)
_C_OK_BG = (226, 243, 228)
_C_BAD = (159, 18, 57)
_C_BAD_BG = (252, 231, 236)
_C_SKIP = (87, 83, 99)
_C_SKIP_BG = (236, 234, 240)
_C_MUTE_BG = (237, 233, 246)
_C_RING = (167, 139, 255)
_C_RING_TRACK = (230, 224, 246)
_C_BAR = (79, 50, 186)
_C_BAR_TRACK = (232, 226, 246)

_PILL = {
    "pass_strong": ((22, 101, 52), (226, 243, 228)),
    "pass": ((29, 78, 216), (226, 236, 252)),
    "borderline": ((154, 106, 0), (255, 244, 204)),
    "needs_support": ((159, 18, 57), (252, 231, 236)),
    "not_ready": ((159, 18, 57), (252, 231, 236)),
    "review": ((15, 118, 110), (220, 245, 241)),
}


def _item_status(status: str) -> tuple[str, tuple[int, int, int], tuple[int, int, int]]:
    s = (status or "").strip().lower()
    if s == "correct":
        return "Correct", _C_OK, _C_OK_BG
    if s == "incorrect":
        return "Incorrect", _C_BAD, _C_BAD_BG
    if s == "submitted":
        return "Submitted", _C_SKIP, _C_SKIP_BG
    if s == "unscored":
        return "Unscored", _C_SKIP, _C_SKIP_BG
    if s == "nocheck":
        return "Review", _C_KICKER, _C_MUTE_BG
    return "Skipped", _C_SKIP, _C_SKIP_BG


def _study_headline(pct: int, auto_total: int) -> str:
    if pct >= 85:
        return "Strong diagnostic."
    if pct >= 70:
        return "Solid base. Review the misses."
    if auto_total:
        return "Useful placement signal."
    return "Waiting on scored answers."


class _AtelierPDF(FPDF):
    def __init__(self, font_family: str) -> None:
        super().__init__(orientation="P", unit="mm", format="Letter")
        self._ff = font_family
        self.set_margins(11, 11, 11)
        self.set_auto_page_break(False)

    def header(self) -> None:
        self.set_fill_color(*_C_PAGE)
        self.rect(0, 0, self.w, self.h, style="F")

    def footer(self) -> None:
        self.set_y(-13)
        self.set_font(self._ff, "", 7)
        self.set_text_color(*_C_MUTED)
        uw = self.w - self.l_margin - self.r_margin
        self.set_x(self.l_margin)
        self.cell(uw * 0.7, 4, "Novel Prep Math Studio  ·  Placement results")
        self.cell(uw * 0.3, 4, f"{self.page_no()}", align="R")


def _cw(pdf: FPDF) -> float:
    return pdf.w - pdf.l_margin - pdf.r_margin


def _txt(pdf: FPDF, s: str) -> str:
    return _pdf_line_for_font(pdf._ff, s)  # type: ignore[attr-defined]


def _ensure(pdf: FPDF, need: float, bottom: float = 18) -> None:
    if pdf.get_y() + need > pdf.h - bottom:
        pdf.add_page()


def _card(pdf: FPDF, x: float, y: float, w: float, h: float, radius: float = 5.2) -> None:
    pdf.set_fill_color(*_C_CARD)
    pdf.set_draw_color(*_C_LINE)
    pdf.set_line_width(0.18)
    pdf.rect(x, y, w, h, style="DF", round_corners=True, corner_radius=radius)


def _chip_row(pdf: FPDF, chips: list[str], y: float) -> float:
    x = pdf.l_margin
    h = 6.4
    for raw in chips:
        label = _txt(pdf, raw)
        if not label:
            continue
        pdf.set_font(pdf._ff, "B", 6.6)  # type: ignore[attr-defined]
        tw = pdf.get_string_width(label) + 6.4
        if x + tw > pdf.w - pdf.r_margin:
            y += h + 1.6
            x = pdf.l_margin
        pdf.set_fill_color(*_C_CHIP)
        pdf.set_draw_color(226, 220, 242)
        pdf.rect(x, y, tw, h, style="DF", round_corners=True, corner_radius=3.2)
        pdf.set_text_color(*_C_CHIP_INK)
        pdf.set_xy(x, y + 1.3)
        pdf.cell(tw, 4, label, align="C")
        x += tw + 2.2
    return y + h


def _score_ring(
    pdf: FPDF,
    cx: float,
    cy: float,
    correct: int,
    total: int,
    pct: int,
    pct_label: str = "correct",
) -> None:
    size = 36
    x = cx - size / 2
    y = cy - size / 2
    pdf.set_fill_color(248, 246, 255)
    pdf.set_draw_color(*_C_LINE)
    pdf.rect(cx - 24, cy - 28, 48, 62, style="DF", round_corners=True, corner_radius=6)
    pdf.set_fill_color(*_C_RING_TRACK)
    pdf.ellipse(x, y, size, size, style="F")
    if pct > 0:
        sweep = max(8, min(360, 360 * pct / 100.0))
        pdf.set_fill_color(*_C_RING)
        pdf.arc(
            x,
            y,
            size,
            start_angle=90,
            end_angle=90 - sweep,
            clockwise=True,
            start_from_center=True,
            end_at_center=True,
            style="F",
        )
    inner = 24
    pdf.set_fill_color(255, 255, 255)
    pdf.ellipse(cx - inner / 2, cy - inner / 2, inner, inner, style="F")
    pdf.set_text_color(*_C_INK)
    pdf.set_font(pdf._ff, "B", 16)  # type: ignore[attr-defined]
    pdf.set_xy(cx - 16, cy - 7)
    pdf.cell(32, 7, str(correct), align="C")
    pdf.set_font(pdf._ff, "", 8)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_MUTED)
    pdf.set_xy(cx - 16, cy + 0.4)
    pdf.cell(32, 5, f"/ {total}", align="C")
    pdf.set_font(pdf._ff, "B", 8.5)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_INK)
    pdf.set_xy(cx - 22, cy + 16)
    pdf.cell(44, 4.5, f"{pct}% {pct_label}", align="C")
    pdf.set_font(pdf._ff, "", 7.2)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_MUTED)
    pdf.set_xy(cx - 22, cy + 21)
    pdf.cell(44, 4, f"Score {correct} / {total}", align="C")


def _sitting_from_ctx(ctx: dict[str, Any]) -> dict[str, Any]:
    """Match the on-screen report ring: sitting total when paper/written points exist."""
    mcq_c = int(
        ctx.get("mcq_correct") if ctx.get("mcq_correct") is not None else ctx.get("correct_count") or 0
    )
    mcq_t = int(ctx.get("mcq_total") if ctx.get("mcq_total") is not None else ctx.get("total_q") or 0)
    paper_max = int(ctx.get("paper_max_points") or 0)
    paper_pts = int(ctx.get("paper_points") or 0)
    if paper_max:
        correct = int(
            ctx.get("total_points") if ctx.get("total_points") is not None else ctx.get("correct_count") or 0
        )
        total = int(ctx.get("max_points") or ctx.get("placement_score_total") or (mcq_t + paper_max))
    else:
        correct = int(ctx.get("correct_count") or 0)
        total = int(ctx.get("placement_score_total") or ctx.get("total_q") or 0)
    return {
        "correct": correct,
        "total": total,
        "mcq_c": mcq_c,
        "mcq_t": mcq_t,
        "paper_max": paper_max,
        "paper_pts": paper_pts,
        "paper_complete": bool(ctx.get("paper_complete")),
        "paper_frq_done": int(ctx.get("paper_frq_completed") or 0),
        "paper_frq_total": int(ctx.get("paper_frq_total") or 0),
    }


def _draw_hero(pdf: FPDF, ctx: dict[str, Any]) -> None:
    w = _cw(pdf)
    y0 = pdf.get_y()
    student = ctx.get("placement_student") if isinstance(ctx.get("placement_student"), dict) else {}
    name = str(student.get("name") or "").strip() or "Student"
    grade = str(student.get("grade") or "").strip()
    course = str(student.get("math_course") or "").strip()
    school = str(student.get("school") or "").strip()
    advisor = str(ctx.get("advisor") or student.get("advisor") or "").strip()
    status = str(ctx.get("status_label") or "Submitted")
    topic = str(ctx.get("topic_title") or "Placement diagnostic")
    brand = str(ctx.get("brand_name") or "Novel Prep Math Studio")
    answered = int(ctx.get("answered_live") or 0)
    item_total = int(ctx.get("item_total") or ctx.get("total_q") or 0)
    sitting = _sitting_from_ctx(ctx)
    correct = sitting["correct"]
    total = sitting["total"]
    pct = int(ctx.get("score_pct") or 0)
    paper_done = sitting["paper_frq_done"]
    paper_total = sitting["paper_frq_total"]
    paper_max = sitting["paper_max"]

    extra = 0
    if paper_max:
        extra = 10 if sitting["mcq_t"] else 6
    elif paper_total:
        extra = 6
    card_h = 72 + extra
    _card(pdf, pdf.l_margin, y0, w, card_h, radius=6)
    left = pdf.l_margin + 8
    pdf.set_xy(left, y0 + 7)
    pdf.set_font(pdf._ff, "B", 7)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_KICKER)
    pdf.cell(110, 4, _txt(pdf, f"Advisor report · {status}").upper())
    pdf.set_xy(left, y0 + 13)
    pdf.set_font(pdf._ff, "B", 11)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_PURPLE)
    pdf.cell(110, 6, _txt(pdf, brand))
    # Confetti squares
    for dx, dy, rgb, rot_w in (
        (102, 8, (34, 211, 238), 2.1),
        (108, 14, (250, 204, 21), 2.0),
        (114, 9, (244, 114, 182), 2.2),
    ):
        pdf.set_fill_color(*rgb)
        pdf.rect(left + dx, y0 + dy, rot_w, rot_w, style="F", round_corners=True, corner_radius=0.4)
    pdf.set_xy(left, y0 + 21)
    pdf.set_font(pdf._ff, "B", 22)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_INK)
    pdf.cell(118, 10, "Placement results")
    pdf.set_xy(left, y0 + 32)
    pdf.set_font(pdf._ff, "", 10)  # type: ignore[attr-defined]
    who = f"For {name}" + (f"  ·  {grade}" if grade else "")
    pdf.cell(118, 5, _txt(pdf, who))
    pdf.set_xy(left, y0 + 38)
    pdf.set_text_color(*_C_MUTED)
    pdf.set_font(pdf._ff, "", 8.4)  # type: ignore[attr-defined]
    pdf.cell(118, 4.5, _txt(pdf, topic)[:72])
    pdf.set_xy(left, y0 + 44)
    pdf.set_text_color(*_C_INK)
    pdf.set_font(pdf._ff, "B", 9.5)  # type: ignore[attr-defined]
    pdf.cell(118, 5, _txt(pdf, f"Answered {answered}/{item_total or '—'}"))
    chips = [
        f"Grade {grade or '—'}",
        course or "Course —",
        school or "School —",
        f"Advisor {advisor or '—'}",
    ]
    pdf.set_y(y0 + 51)
    pdf.set_left_margin(left)
    _chip_row(pdf, chips, y0 + 51)
    pdf.set_left_margin(11)
    _score_ring(
        pdf,
        pdf.w - pdf.r_margin - 28,
        y0 + 34,
        correct,
        total,
        pct,
        pct_label="of sitting" if paper_max else "correct",
    )
    pdf.set_font(pdf._ff, "", 6.8)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_MUTED)
    foot_x = pdf.w - pdf.r_margin - 50
    if paper_max and sitting["mcq_t"]:
        pdf.set_xy(foot_x, y0 + 64)
        pdf.cell(44, 4, f"MC auto-scored {sitting['mcq_c']}/{sitting['mcq_t']}", align="C")
        paper_line = f"Graphing 1 pt · FR 4 pt · Paper {sitting['paper_pts']}/{paper_max}"
        if not sitting["paper_complete"]:
            paper_line += " · still grading"
        pdf.set_xy(foot_x - 8, y0 + 68.5)
        pdf.cell(60, 4, paper_line, align="C")
    elif paper_max:
        written = f"Written work · {correct} / {total}"
        if not sitting["paper_complete"]:
            written += " · still grading"
        pdf.set_xy(foot_x, y0 + 64)
        pdf.cell(44, 4, written, align="C")
    elif paper_total:
        pdf.set_xy(foot_x, y0 + 64)
        pdf.cell(44, 4, f"Graphing {paper_done} / {paper_total} submitted", align="C")
    pdf.set_y(y0 + card_h + 6)


def _draw_study(pdf: FPDF, ctx: dict[str, Any]) -> None:
    w = _cw(pdf)
    y0 = pdf.get_y()
    student = ctx.get("placement_student") if isinstance(ctx.get("placement_student"), dict) else {}
    sitting = _sitting_from_ctx(ctx)
    correct = sitting["correct"]
    total = sitting["total"]
    pct = int(ctx.get("score_pct") or 0)
    answered = int(ctx.get("answered_live") or 0)
    item_total = int(ctx.get("item_total") or 0)
    misses = ctx.get("miss_ns") or []
    advisor = str(ctx.get("advisor") or "").strip() or "—"
    grade = str(student.get("grade") or "").strip() or "Grade —"
    course = str(student.get("math_course") or "").strip()
    headline = _study_headline(pct, total)
    _ensure(pdf, 52)
    y0 = pdf.get_y()
    _card(pdf, pdf.l_margin, y0, w, 50, radius=5.5)
    pdf.set_xy(pdf.l_margin + 8, y0 + 6)
    pdf.set_font(pdf._ff, "B", 7.2)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_KICKER)
    pdf.cell(0, 4, "STUDY REPORT")
    pdf.set_xy(pdf.l_margin + 8, y0 + 10.2)
    pdf.set_font(pdf._ff, "B", 13)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_INK)
    pdf.cell(0, 6.5, _txt(pdf, headline), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if sitting["paper_max"] and sitting["mcq_t"]:
        band_note = f"{sitting['mcq_c']} MC of {sitting['mcq_t']} · {correct}/{total} total"
    elif sitting["paper_max"]:
        band_note = f"{correct}/{total} written"
    else:
        band_note = f"{correct} correct of {total} scored items"
    cards = [
        ("Score band", f"{pct}%", band_note),
        ("Progress", f"{answered}/{item_total or '—'}", str(ctx.get("status_label") or "")),
        ("Misses", str(len(misses)), "Auto-incorrect items to review" if misses else "No auto-incorrect items"),
        ("Advisor", advisor, grade + (f" · {course}" if course else "")),
    ]
    gap = 3
    cw = (w - 16 - gap * 3) / 4
    cy = y0 + 20
    for i, (label, value, note) in enumerate(cards):
        x = pdf.l_margin + 8 + i * (cw + gap)
        pdf.set_fill_color(250, 248, 255)
        pdf.set_draw_color(*_C_LINE)
        pdf.rect(x, cy, cw, 24, style="DF", round_corners=True, corner_radius=3.4)
        pdf.set_xy(x + 3, cy + 2.4)
        pdf.set_font(pdf._ff, "B", 6.2)  # type: ignore[attr-defined]
        pdf.set_text_color(*_C_MUTED)
        pdf.cell(cw - 6, 3.4, _txt(pdf, label).upper())
        pdf.set_xy(x + 3, cy + 6.6)
        pdf.set_font(pdf._ff, "B", 12)  # type: ignore[attr-defined]
        pdf.set_text_color(*_C_INK)
        pdf.cell(cw - 6, 6, _txt(pdf, value)[:18])
        pdf.set_xy(x + 3, cy + 13.4)
        pdf.set_font(pdf._ff, "", 6.4)  # type: ignore[attr-defined]
        pdf.set_text_color(*_C_MUTED)
        pdf.multi_cell(cw - 6, 3.2, _txt(pdf, note)[:56])
    pdf.set_y(y0 + 56)


def _pill(pdf: FPDF, x: float, y: float, label: str, status: str) -> float:
    colors = _PILL.get(status, ((67, 48, 143), (237, 233, 246)))
    ink, bg = colors
    text = _txt(pdf, label).upper()
    pdf.set_font(pdf._ff, "B", 6)  # type: ignore[attr-defined]
    tw = min(pdf.get_string_width(text) + 5.2, 42)
    pdf.set_fill_color(*bg)
    pdf.rect(x, y, tw, 4.6, style="F", round_corners=True, corner_radius=2.3)
    pdf.set_text_color(*ink)
    pdf.set_xy(x, y + 0.6)
    pdf.cell(tw, 3.4, text, align="C")
    return tw


def _draw_sections(pdf: FPDF, ctx: dict[str, Any]) -> None:
    stats = ctx.get("section_stats") or []
    if not stats:
        return
    w = _cw(pdf)
    _ensure(pdf, 38)
    y0 = pdf.get_y()
    cap_h = 22
    est_h = cap_h + 10 + 16.2 * len(stats) + 8
    if y0 + est_h <= pdf.h - 18:
        _card(pdf, pdf.l_margin, y0, w, est_h, radius=5.5)
        inner_x = pdf.l_margin + 6
        table_w = w - 12
    else:
        _card(pdf, pdf.l_margin, y0, w, cap_h, radius=5.5)
        inner_x = pdf.l_margin
        table_w = w
    pdf.set_xy(pdf.l_margin + 8, y0 + 5)
    pdf.set_font(pdf._ff, "B", 7)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_KICKER)
    pdf.cell(0, 4, "PRINTED DIAGNOSTIC")
    pdf.set_xy(pdf.l_margin + 8, y0 + 10)
    pdf.set_font(pdf._ff, "B", 14)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_INK)
    pdf.cell(0, 7, "Score by section")
    pdf.set_y(y0 + cap_h + 1)

    cols = (28, 46, 18, 22)
    read_w = table_w - sum(cols)
    headers = ("Part", "Area", "Score", "Rate", "Reading")
    widths = (*cols, read_w)

    def header_row() -> None:
        y = pdf.get_y()
        _ensure(pdf, 10)
        y = pdf.get_y()
        pdf.set_fill_color(*_C_PURPLE)
        pdf.rect(inner_x, y, table_w, 8, style="F", round_corners=True, corner_radius=2.2)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font(pdf._ff, "B", 7)  # type: ignore[attr-defined]
        x = inner_x
        for title, cw in zip(headers, widths):
            pdf.set_xy(x + 2.2, y + 2)
            pdf.cell(cw - 4, 4, title.upper())
            x += cw
        pdf.set_y(y + 8)

    header_row()
    for i, sec in enumerate(stats):
        part = str(sec.get("part_label") or sec.get("section") or "")
        rng = str(sec.get("range_label") or "")
        area = str(sec.get("area_title") or sec.get("title_en") or "")
        correct = int(sec.get("correct") or 0)
        total = int(sec.get("total") or 0)
        pct = int(sec.get("pct") or 0)
        paper = bool(sec.get("paper"))
        reading = str(sec.get("interpretation") or "")
        status = str(sec.get("status") or "")
        status_label = str(sec.get("status_label") or "")
        interp = _txt(pdf, reading)
        pdf.set_font(pdf._ff, "", 7.4)  # type: ignore[attr-defined]
        interp_h = 8
        if interp:
            lines = pdf.multi_cell(read_w - 4, 3.4, interp, dry_run=True, output="LINES")
            interp_h = max(8, 6 + len(lines) * 3.4)
        row_h = max(15.2, interp_h + 5)
        _ensure(pdf, row_h + 2)
        if pdf.get_y() < 20:
            inner_x = pdf.l_margin
            table_w = w
            read_w = table_w - sum(cols)
            widths = (*cols, read_w)
            header_row()
        y = pdf.get_y()
        fill = _C_SOFT if i % 2 == 0 else _C_SOFT2
        pdf.set_fill_color(*fill)
        pdf.set_draw_color(*_C_LINE)
        pdf.rect(inner_x, y, table_w, row_h, style="DF")
        x = inner_x
        pdf.set_xy(x + 2.2, y + 2.4)
        pdf.set_font(pdf._ff, "B", 8.5)  # type: ignore[attr-defined]
        pdf.set_text_color(*_C_INK)
        pdf.cell(cols[0] - 3, 4.2, _txt(pdf, part))
        if rng:
            pdf.set_xy(x + 2.2, y + 6.8)
            pdf.set_font(pdf._ff, "", 6.6)  # type: ignore[attr-defined]
            pdf.set_text_color(*_C_MUTED)
            pdf.cell(cols[0] - 3, 3.4, _txt(pdf, rng))
        x += cols[0]
        pdf.set_xy(x + 1.5, y + 3.4)
        pdf.set_font(pdf._ff, "B", 8)  # type: ignore[attr-defined]
        pdf.set_text_color(*_C_INK)
        pdf.multi_cell(cols[1] - 3, 3.6, _txt(pdf, area))
        x += cols[1]
        pdf.set_xy(x, y + 4.4)
        pdf.set_font(pdf._ff, "B", 9)  # type: ignore[attr-defined]
        pdf.cell(cols[2], 5, f"{correct}/{total}", align="C")
        x += cols[2]
        pdf.set_xy(x, y + 3.2)
        pdf.set_font(pdf._ff, "B", 9)  # type: ignore[attr-defined]
        pdf.set_text_color(*_C_PURPLE)
        pdf.cell(cols[3], 4.5, "Review" if paper else f"{pct}%", align="C")
        if not paper:
            bar_x = x + 3
            bar_w = cols[3] - 6
            pdf.set_fill_color(*_C_BAR_TRACK)
            pdf.rect(bar_x, y + 9, bar_w, 2.1, style="F", round_corners=True, corner_radius=1)
            if pct:
                pdf.set_fill_color(*_C_BAR)
                pdf.rect(bar_x, y + 9, max(1.2, bar_w * pct / 100.0), 2.1, style="F", round_corners=True, corner_radius=1)
        x += cols[3]
        _pill(pdf, x + 2, y + 2.2, status_label, status)
        pdf.set_xy(x + 2, y + 7.4)
        pdf.set_font(pdf._ff, "", 7)  # type: ignore[attr-defined]
        pdf.set_text_color(*_C_MUTED)
        pdf.multi_cell(read_w - 4, 3.4, interp)
        pdf.set_y(y + row_h)
    pdf.ln(5)


def _draw_misses(pdf: FPDF, ctx: dict[str, Any]) -> None:
    misses = list(ctx.get("miss_ns") or [])
    if not misses:
        return
    w = _cw(pdf)
    rows = 1 + (len(misses) - 1) // 10
    need = 28 + rows * 8
    _ensure(pdf, need)
    y0 = pdf.get_y()
    _card(pdf, pdf.l_margin, y0, w, 22 + rows * 8, radius=5.5)
    pdf.set_xy(pdf.l_margin + 8, y0 + 5)
    pdf.set_font(pdf._ff, "B", 7)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_KICKER)
    pdf.cell(0, 4, "MISSES")
    pdf.set_xy(pdf.l_margin + 8, y0 + 10)
    pdf.set_font(pdf._ff, "B", 13)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_INK)
    pdf.cell(0, 6, "Jump to incorrect items")
    pdf.set_xy(pdf.l_margin + 8, y0 + 16.4)
    pdf.set_font(pdf._ff, "", 8)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_MUTED)
    n = len(misses)
    pdf.cell(0, 4, f"{n} auto-incorrect item{'s' if n != 1 else ''} in this sitting.")
    x = pdf.l_margin + 8
    y = y0 + 23
    pdf.set_font(pdf._ff, "B", 8)  # type: ignore[attr-defined]
    for qn in misses:
        label = f"Q{qn}"
        tw = 14
        if x + tw > pdf.w - pdf.r_margin - 6:
            x = pdf.l_margin + 8
            y += 8
        pdf.set_fill_color(243, 236, 252)
        pdf.set_draw_color(196, 176, 226)
        pdf.rect(x, y, tw, 6.6, style="DF", round_corners=True, corner_radius=3.2)
        pdf.set_text_color(91, 33, 182)
        pdf.set_xy(x, y + 1.2)
        pdf.cell(tw, 4.2, label, align="C")
        x += tw + 2.2
    pdf.set_y(y + 12)


def _draw_items(pdf: FPDF, ctx: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = ctx.get("rows") or []
    if not rows:
        return
    w = _cw(pdf)
    _ensure(pdf, 36)
    y0 = pdf.get_y()
    _card(pdf, pdf.l_margin, y0, w, 22, radius=5.5)
    pdf.set_xy(pdf.l_margin + 8, y0 + 5)
    pdf.set_font(pdf._ff, "B", 7)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_KICKER)
    pdf.cell(0, 4, "FULL BREAKDOWN")
    pdf.set_xy(pdf.l_margin + 8, y0 + 10)
    pdf.set_font(pdf._ff, "B", 14)  # type: ignore[attr-defined]
    pdf.set_text_color(*_C_INK)
    pdf.cell(0, 7, "Item-by-item results")
    pdf.set_y(y0 + 24)
    cols = (14, (w - 14 - 28) / 2, (w - 14 - 28) / 2, 28)

    def sheet_head() -> None:
        _ensure(pdf, 10)
        y = pdf.get_y()
        pdf.set_fill_color(244, 240, 252)
        pdf.rect(pdf.l_margin, y, w, 7.4, style="F", round_corners=True, corner_radius=2)
        pdf.set_font(pdf._ff, "B", 6.8)  # type: ignore[attr-defined]
        pdf.set_text_color(*_C_PURPLE)
        labels = ("#", "Student answer", "Correct", "Status")
        x = pdf.l_margin
        for lab, cw in zip(labels, cols):
            pdf.set_xy(x + 2, y + 1.6)
            pdf.cell(cw - 3, 4.2, lab.upper())
            x += cw
        pdf.set_y(y + 8)

    sheet_head()
    last_band = None
    for row in rows:
        band = (
            str(row.get("part_label") or ""),
            str(row.get("area_title") or ""),
            str(row.get("range_label") or ""),
        )
        if band != last_band and any(band):
            _ensure(pdf, 10)
            y = pdf.get_y()
            pdf.set_fill_color(244, 240, 252)
            pdf.rect(pdf.l_margin, y, w, 7.6, style="F")
            pdf.set_xy(pdf.l_margin + 3, y + 1.6)
            pdf.set_font(pdf._ff, "B", 7)  # type: ignore[attr-defined]
            pdf.set_text_color(*_C_PURPLE)
            pdf.cell(28, 4.4, _txt(pdf, band[0]).upper())
            pdf.set_text_color(*_C_INK)
            pdf.set_font(pdf._ff, "B", 8)  # type: ignore[attr-defined]
            pdf.cell(90, 4.4, _txt(pdf, band[1])[:42])
            pdf.set_font(pdf._ff, "", 7)  # type: ignore[attr-defined]
            pdf.set_text_color(*_C_MUTED)
            pdf.cell(40, 4.4, _txt(pdf, band[2]))
            pdf.set_y(y + 8)
            last_band = band
        _ensure(pdf, 9)
        if pdf.get_y() < 22:
            sheet_head()
        y = pdf.get_y()
        st = str(row.get("status") or "")
        if st == "incorrect":
            fill = (252, 244, 246)
        elif st == "correct":
            fill = (244, 250, 245)
        else:
            fill = (250, 249, 255)
        pdf.set_fill_color(*fill)
        pdf.set_draw_color(238, 234, 246)
        pdf.rect(pdf.l_margin, y, w, 8, style="DF", round_corners=True, corner_radius=1.8)
        qn = str(row.get("q_display") or "")
        yours = display_answer_plain(str(row.get("yours_display") or "—"), max_len=28) or "—"
        key = display_answer_plain(str(row.get("key_display") or "—"), max_len=28) or "—"
        label, ink, bg = _item_status(st)
        x = pdf.l_margin
        pdf.set_xy(x + 2, y + 1.8)
        pdf.set_font(pdf._ff, "B", 8.5)  # type: ignore[attr-defined]
        pdf.set_text_color(*_C_INK)
        pdf.cell(cols[0] - 2, 4.4, qn)
        x += cols[0]
        pdf.set_xy(x + 1, y + 1.8)
        pdf.set_font(pdf._ff, "", 8)  # type: ignore[attr-defined]
        pdf.cell(cols[1] - 2, 4.4, _txt(pdf, yours))
        x += cols[1]
        pdf.set_xy(x + 1, y + 1.8)
        pdf.cell(cols[2] - 2, 4.4, _txt(pdf, key))
        x += cols[2]
        pdf.set_font(pdf._ff, "B", 6.2)  # type: ignore[attr-defined]
        tw = min(pdf.get_string_width(label) + 5, cols[3] - 3)
        pdf.set_fill_color(*bg)
        pdf.rect(x + 2, y + 1.6, tw, 4.8, style="F", round_corners=True, corner_radius=2.2)
        pdf.set_text_color(*ink)
        pdf.set_xy(x + 2, y + 2)
        pdf.cell(tw, 4, label, align="C")
        pdf.set_y(y + 8.8)


def build_placement_atelier_pdf(ctx: dict[str, Any]) -> bytes:
    if FPDF is None or XPos is None or YPos is None:
        raise ImportError(_FPDF2_INSTALL_HINT)
    pdf = _AtelierPDF("Helvetica")
    font = _setup_font(pdf)
    pdf._ff = font
    pdf.set_title(_txt(pdf, "Placement results"))
    pdf.add_page()
    _draw_hero(pdf, ctx)
    _draw_study(pdf, ctx)
    _draw_sections(pdf, ctx)
    _draw_misses(pdf, ctx)
    _draw_items(pdf, ctx)
    bio = BytesIO()
    pdf.output(bio)
    return bio.getvalue()
