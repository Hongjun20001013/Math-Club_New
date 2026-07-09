"""
Parent-facing PDF for placement session results (premium layout, UTF-8 via DejaVu when available).
"""
from __future__ import annotations

import os
import sys
import re
from io import BytesIO
from typing import Any, Callable

# Bundled wheels so PDF export works even when the active venv/system Python
# does not have fpdf2 installed (common in IDEs picking the wrong interpreter).
_THIRD_PARTY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "third_party")
if os.path.isdir(os.path.join(_THIRD_PARTY, "fpdf")):
    _abs_tp = os.path.abspath(_THIRD_PARTY)
    if _abs_tp not in sys.path:
        sys.path.insert(0, _abs_tp)

from answer_grader import display_answer_plain

# PyPI package name is fpdf2; it exposes the import path `fpdf`.
try:
    from fpdf import FPDF
    from fpdf.enums import MethodReturnValue, XPos, YPos
except ImportError:  # pragma: no cover
    FPDF = None  # type: ignore[misc, assignment]
    MethodReturnValue = None  # type: ignore[misc, assignment]
    XPos = None  # type: ignore[misc, assignment]
    YPos = None  # type: ignore[misc, assignment]

_FPDF2_INSTALL_HINT = (
    "PDF export could not load fpdf2. If the folder `third_party/` is missing, run:\n"
    "  ./scripts/vendor_fpdf_bootstrap.sh\n"
    "Otherwise install into your environment:\n"
    "  pip install fpdf2\n"
    "  pip install -r requirements.txt\n"
)

_HTML_TAG = re.compile(r"<[^>]+>")

# Brand palette (RGB)
_C_INK = (26, 21, 48)
_C_MUTED = (95, 88, 120)
_C_LINE = (225, 222, 238)
_C_VIOLET = (79, 61, 214)
_C_VIOLET_SOFT = (108, 78, 255)
_C_SURFACE = (248, 246, 255)
_C_SURFACE2 = (241, 238, 252)
_C_OK = (22, 163, 74)
_C_BAD = (220, 38, 38)
_C_SKIP = (120, 113, 108)


def _pdf_brand_name() -> str:
    return (os.environ.get("SITE_BRAND_NAME") or "Novel Prep").strip() or "Novel Prep"


def _strip_html(s: str) -> str:
    t = _HTML_TAG.sub("", s or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


# Helvetica / core PDF fonts only cover Latin-1.
_PDF_SAFE_TRANS = str.maketrans(
    {
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00ad": "",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u00a0": " ",
    }
)


def _pdf_core_font_safe(s: str) -> str:
    t = _strip_html(s).translate(_PDF_SAFE_TRANS)
    return t.encode("latin-1", errors="replace").decode("latin-1")


def _answer_display_for_pdf(s: str, *, max_len: int = 32) -> str:
    """Readable answer text for PDF cells (no raw LaTeX like \\frac12 or 75\\%)."""
    t = _strip_html(s or "").strip()
    if not t or t in ("—", "-"):
        return t or "—"
    t = t.translate(_PDF_SAFE_TRANS)
    if t.startswith(r"\(") and t.endswith(r"\)"):
        t = t[2:-2].strip()
    t = re.sub(r"\\displaystyle\s*", "", t)
    t = re.sub(r"\\(?:d|t)?frac\{([^{}]+)\}\{([^{}]+)\}", r"\1/\2", t)
    t = re.sub(r"\\frac(\d)(\d)\b", r"\1/\2", t)
    t = re.sub(r"\\frac\{?(\d+)\}?/\{?(\d+)\}?", r"\1/\2", t)
    t = t.replace(r"\%", "%")
    t = re.sub(r"\^\{([^{}]+)\}", r"^\1", t)
    t = re.sub(r"\\cdot\b", "·", t)
    t = re.sub(r"\\times\b", "×", t)
    t = re.sub(r"\\(?:left|right)\b", "", t)
    t = re.sub(r"\\text\{([^}]*)\}", r"\1", t)
    t = re.sub(r"\\mathbf\{([^}]*)\}", r"\1", t)
    t = re.sub(r"\\boxed\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"\\[a-zA-Z]+\b", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:max_len] if t else "—"


def _pdf_line_for_font(font: str, s: str) -> str:
    """Use full Unicode when DejaVu is active; otherwise Latin-1-safe."""
    t = _strip_html(s or "").strip()
    if not t:
        return ""
    if font == "DejaVu":
        return t[:400]
    return _pdf_core_font_safe(t)


def _strip_part_prefix(sec: str, title: str) -> str:
    """Avoid 'Part I' heading + 'Part I: ...' subtitle double-reading."""
    t = _strip_html(title).strip()
    if not t:
        return ""
    sec_s = str(sec).strip()
    candidates = (
        f"Part {sec_s}:",
        f"Part {sec_s}: ",
        f"Part {sec_s} :",
        f"Part{sec_s}:",
        f"Part {sec_s} -",
        f"Part {sec_s} - ",
    )
    tl = t
    for p in candidates:
        if len(tl) >= len(p) and tl[: len(p)].lower() == p.lower():
            return tl[len(p) :].strip()
    if sec_s and len(tl) > len(sec_s) + 1 and tl[: len(sec_s) + 1].lower() == f"{sec_s}:".lower():
        return tl[len(sec_s) + 1 :].strip()
    return t


_APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _setup_font(pdf: Any) -> str:
    """Return font family name for body text (DejaVu from repo fonts/ when present)."""
    font_dir = os.path.join(_APP_DIR, "fonts")
    regular = os.path.join(font_dir, "DejaVuSans.ttf")
    bold = os.path.join(font_dir, "DejaVuSans-Bold.ttf")
    try:
        if os.path.isfile(regular):
            pdf.add_font("DejaVu", "", regular)
            if os.path.isfile(bold):
                pdf.add_font("DejaVu", "B", bold)
            else:
                pdf.add_font("DejaVu", "B", regular)
            return "DejaVu"
    except Exception:
        pass
    return "Helvetica"


def _status_label(status: str) -> str:
    s = (status or "").strip().lower()
    if s == "correct":
        return "Correct"
    if s == "incorrect":
        return "Missed"
    if s == "skipped":
        return "Skipped"
    if s == "nocheck":
        return "N/A"
    return (status or "")[:10]


def _status_color(status: str) -> tuple[int, int, int]:
    s = (status or "").strip().lower()
    if s == "correct":
        return _C_OK
    if s == "incorrect":
        return _C_BAD
    if s == "skipped":
        return _C_SKIP
    return _C_MUTED


class _PlacementReportPDF(FPDF):
    """Letter-size report with footer and consistent margins."""

    def __init__(self, font_family: str) -> None:
        super().__init__(orientation="P", unit="mm", format="Letter")
        self._ff = font_family
        self.set_margins(16, 18, 16)
        self.set_auto_page_break(True, margin=20)

    def footer(self) -> None:
        self.set_y(-18)
        self.set_draw_color(*_C_LINE)
        self.set_line_width(0.25)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)
        self.set_font(self._ff, "", 7)
        self.set_text_color(*_C_MUTED)
        uw = self.w - self.l_margin - self.r_margin
        left = _pdf_core_font_safe(f"{_pdf_brand_name()}  ·  Course placement")
        self.set_x(self.l_margin)
        self.cell(uw * 0.58, 4, left, align="L")
        self.cell(uw * 0.42, 4, f"Page {self.page_no()}/{{nb}}", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*_C_INK)


def _content_width(pdf: FPDF) -> float:
    return pdf.w - pdf.l_margin - pdf.r_margin


def _draw_hero_band(pdf: FPDF, font: str, topic_title: str) -> None:
    """Institutional header: org first, then document type (never a Part card)."""
    pdf.set_fill_color(72, 52, 200)
    pdf.rect(0, 0, pdf.w, 46, "F")

    pdf.set_xy(0, 8)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(font, "B", 9)
    pdf.cell(0, 4, _pdf_core_font_safe("NOVEL PREP"), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(font, "", 8)
    pdf.set_text_color(235, 232, 255)
    pdf.cell(0, 3.5, _pdf_core_font_safe("Mathematics · Official placement export"), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(font, "B", 17)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, _pdf_core_font_safe("Course placement report"), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(font, "", 9)
    pdf.set_text_color(235, 232, 255)
    pdf.cell(0, 5, _pdf_core_font_safe(topic_title or "Placement diagnostic"), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_text_color(*_C_INK)
    pdf.set_xy(pdf.l_margin, 54)


def _draw_student_profile(pdf: FPDF, font: str, student: dict[str, Any]) -> None:
    name = (str(student.get("name") or "")).strip()
    grade = (str(student.get("grade") or "")).strip()
    course = (str(student.get("math_course") or "")).strip()
    w = _content_width(pdf)
    pdf.set_font(font, "B", 9)
    pdf.set_text_color(*_C_VIOLET)
    pdf.cell(0, 5, _pdf_line_for_font(font, "Student record"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    if not name and not grade and not course:
        pdf.set_font(font, "", 8)
        pdf.set_text_color(*_C_MUTED)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(
            w,
            4.2,
            _pdf_line_for_font(
                font,
                "No profile captured on this attempt. Re-run the diagnostic from the placement start page so the export lists name, grade, and current math class.",
            ),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    else:
        pdf.set_font(font, "", 8.5)
        pdf.set_text_color(*_C_INK)
        parts = []
        if name:
            parts.append(f"Name: {name}")
        if grade:
            parts.append(f"Grade: {grade}")
        if parts:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(
                w,
                4.3,
                _pdf_line_for_font(font, "   ·   ".join(parts)),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
        if course:
            pdf.set_font(font, "", 8)
            pdf.set_text_color(*_C_MUTED)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(
                w,
                4.1,
                _pdf_line_for_font(font, f"Current math course: {course}"),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

    pdf.ln(1)
    pdf.set_draw_color(*_C_LINE)
    pdf.set_line_width(0.3)
    y_rule = pdf.get_y()
    pdf.line(pdf.l_margin, y_rule, pdf.l_margin + w, y_rule)
    pdf.ln(7)
    pdf.set_text_color(*_C_INK)


def _draw_score_card(
    pdf: FPDF,
    font: str,
    correct: int,
    total: int,
    pct: int,
) -> None:
    """Score summary: plain rectangle (no rounded corners) so text is never clipped."""
    w = _content_width(pdf)
    y0 = pdf.get_y()
    h = 44.0
    pdf.set_fill_color(252, 250, 255)
    pdf.set_draw_color(200, 194, 224)
    pdf.set_line_width(0.2)
    pdf.rect(pdf.l_margin, y0, w, h, "DF", round_corners=False)

    left_col_w = w * 0.41
    mid_x = pdf.l_margin + left_col_w
    pdf.set_draw_color(210, 206, 232)
    pdf.set_line_width(0.2)
    pdf.line(mid_x, y0 + 10, mid_x, y0 + h - 10)

    pad = 10.0
    # Left: raw score (extra top padding avoids ascenders touching the box edge)
    pdf.set_xy(pdf.l_margin + pad, y0 + pad)
    pdf.set_font(font, "", 8)
    pdf.set_text_color(*_C_MUTED)
    pdf.cell(62, 5, _pdf_core_font_safe("RAW SCORE"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(pdf.l_margin + pad)
    pdf.set_font(font, "B", 26)
    pdf.set_text_color(*_C_INK)
    pdf.cell(30, 14, str(correct), align="L")
    pdf.set_font(font, "", 14)
    pdf.set_text_color(*_C_MUTED)
    pdf.cell(34, 14, f"/ {total}", align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(pdf.l_margin + pad)
    pdf.set_font(font, "", 9)
    pdf.set_text_color(*_C_MUTED)
    pdf.cell(66, 5, _pdf_core_font_safe(f"{pct}% of items correct"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    bar_x = mid_x + 10
    bar_w = pdf.l_margin + w - bar_x - pad
    pdf.set_xy(bar_x, y0 + pad)
    pdf.set_font(font, "B", 10)
    pdf.set_text_color(*_C_INK)
    pdf.cell(bar_w, 5, _pdf_core_font_safe("Session accuracy"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(bar_x)
    pdf.set_font(font, "", 8)
    pdf.set_text_color(*_C_MUTED)
    pdf.multi_cell(
        bar_w,
        4.2,
        _pdf_core_font_safe("How you performed on this diagnostic only—not a course grade."),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    track_y = y0 + 35
    pdf.set_fill_color(232, 228, 244)
    pdf.rect(bar_x, track_y, bar_w, 5, "F", round_corners=False)
    fill_w = max(0.0, min(bar_w, bar_w * (pct / 100.0)))
    if fill_w > 0.25:
        pdf.set_fill_color(*_C_VIOLET)
        pdf.rect(bar_x, track_y, fill_w, 5, "F", round_corners=False)

    pdf.set_xy(pdf.l_margin, y0 + h + 7)


def _draw_panel_title(pdf: FPDF, font: str, title: str) -> None:
    pdf.ln(3)
    cw = _content_width(pdf)
    pdf.set_font(font, "B", 12)
    pdf.set_text_color(*_C_INK)
    pdf.cell(0, 7, _pdf_core_font_safe(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    y_rule = pdf.get_y()
    pdf.set_draw_color(190, 184, 214)
    pdf.set_line_width(0.35)
    pdf.line(pdf.l_margin, y_rule, pdf.l_margin + cw, y_rule)
    pdf.ln(5)


def _draw_gate_scores_panel(
    pdf: FPDF,
    font: str,
    gate_scores: list[dict[str, Any]],
    gate_rec: dict[str, Any] | None,
) -> None:
    if not gate_scores:
        return
    _draw_panel_title(pdf, font, "Five-gate scorecard")
    if gate_rec:
        pdf.set_font(font, "B", 10)
        pdf.set_text_color(*_C_VIOLET)
        pdf.multi_cell(
            0,
            5.2,
            _pdf_core_font_safe(str(gate_rec.get("title") or "")),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.set_font(font, "", 8.5)
        pdf.set_text_color(*_C_MUTED)
        gh = _pdf_core_font_safe(str(gate_rec.get("headline") or ""))
        if gh:
            pdf.multi_cell(0, 4.8, gh, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

    w = _content_width(pdf)
    col_gate = w * 0.11
    col_rng = w * 0.16
    col_sc = w * 0.18
    col_thr = w * 0.22
    col_st = w - col_gate - col_rng - col_sc - col_thr

    pdf.set_font(font, "B", 7.5)
    pdf.set_fill_color(72, 52, 200)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(col_gate, 6, "Gate", border=1, align="C", fill=True)
    pdf.cell(col_rng, 6, "Items", border=1, align="C", fill=True)
    pdf.cell(col_sc, 6, "Correct", border=1, align="C", fill=True)
    pdf.cell(col_thr, 6, "Pass threshold", border=1, align="C", fill=True)
    pdf.cell(col_st, 6, "Status", border=1, align="C", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font(font, "", 7.5)
    line_h = 6.2
    for idx, row in enumerate(gate_scores):
        if pdf.get_y() + line_h > pdf.h - pdf.b_margin - 12:
            pdf.add_page()
            _draw_panel_title(pdf, font, "Five-gate scorecard (continued)")
            pdf.set_font(font, "B", 7.5)
            pdf.set_fill_color(72, 52, 200)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(col_gate, 6, "Gate", border=1, align="C", fill=True)
            pdf.cell(col_rng, 6, "Items", border=1, align="C", fill=True)
            pdf.cell(col_sc, 6, "Correct", border=1, align="C", fill=True)
            pdf.cell(col_thr, 6, "Pass threshold", border=1, align="C", fill=True)
            pdf.cell(col_st, 6, "Status", border=1, align="C", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font(font, "", 7.5)

        if idx % 2 == 0:
            pdf.set_fill_color(252, 251, 255)
        else:
            pdf.set_fill_color(246, 243, 255)
        pdf.set_text_color(*_C_INK)
        pdf.set_draw_color(*_C_LINE)

        gate = int(row.get("gate") or 0)
        rng = _pdf_core_font_safe(str(row.get("range") or ""))
        cor = int(row.get("correct") or 0)
        tot = int(row.get("total") or 0)
        standard = int(row.get("standard_pass") or 0)
        strong = int(row.get("strong_pass") or standard)
        tier = str(row.get("pass_tier") or "below")
        if tier == "strong":
            st_label = "Strong pass"
            r, g, b = _C_OK
        elif tier == "standard":
            st_label = "Pass"
            r, g, b = (34, 120, 70)
        else:
            st_label = "Below threshold"
            r, g, b = _C_BAD

        pdf.cell(col_gate, line_h, str(gate), border="LRBT", align="C", fill=True)
        pdf.cell(col_rng, line_h, rng, border="LRBT", align="C", fill=True)
        pdf.cell(col_sc, line_h, f"{cor} / {tot}", border="LRBT", align="C", fill=True)
        thr = f"{standard}/{tot}"
        if strong > standard:
            thr += f"  (strong {strong})"
        pdf.cell(col_thr, line_h, _pdf_core_font_safe(thr), border="LRBT", align="C", fill=True)
        pdf.set_font(font, "B", 7)
        pdf.set_text_color(r, g, b)
        pdf.cell(
            col_st,
            line_h,
            _pdf_core_font_safe(st_label),
            border="LRBT",
            align="C",
            fill=True,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.set_font(font, "", 7.5)
        pdf.set_text_color(*_C_INK)

    if gate_rec and gate_rec.get("summary"):
        pdf.ln(2)
        pdf.set_font(font, "", 8.5)
        pdf.set_text_color(*_C_INK)
        pdf.multi_cell(
            0,
            4.8,
            _pdf_core_font_safe(str(gate_rec.get("summary") or "")),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    pdf.ln(4)


def _section_card_label(sec: str, use_gates: bool) -> str:
    s = str(sec or "").strip()
    if use_gates and s.isdigit():
        return f"Gate {s}"
    return f"Part {s}"


def _draw_recommendation(
    pdf: FPDF,
    font: str,
    placement_rec: dict[str, Any],
    total_q: int,
) -> None:
    pdf.ln(1)
    title = _pdf_core_font_safe(str(placement_rec.get("title") or ""))
    band = _pdf_core_font_safe(str(placement_rec.get("band_range") or ""))
    pdf.set_font(font, "B", 12)
    pdf.set_text_color(*_C_VIOLET)
    pdf.multi_cell(0, 6, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(font, "", 9)
    pdf.set_text_color(*_C_MUTED)
    pdf.multi_cell(
        0,
        5,
        _pdf_core_font_safe(f"Score band: {band} correct (out of {total_q})"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(1)
    for key in ("headline", "summary"):
        val = _pdf_core_font_safe(str(placement_rec.get(key) or ""))
        if val:
            pdf.set_font(font, "", 9)
            pdf.set_text_color(*_C_INK)
            pdf.multi_cell(0, 5.2, val, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    hl = placement_rec.get("highlights")
    if isinstance(hl, list) and hl:
        pdf.ln(2)
        pdf.set_font(font, "B", 9)
        pdf.set_text_color(*_C_INK)
        pdf.cell(0, 5, _pdf_core_font_safe("Next steps"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font(font, "", 8.5)
        pdf.set_text_color(*_C_MUTED)
        for line in hl[:6]:
            lt = _pdf_core_font_safe(str(line))
            if lt:
                pdf.multi_cell(
                    0,
                    4.8,
                    _pdf_core_font_safe(f"    -  {lt}"),
                    new_x=XPos.LMARGIN,
                    new_y=YPos.NEXT,
                )


def _draw_sections_continuation_band(pdf: FPDF, font: str, topic_title: str) -> None:
    """If parts move to page 2+, top of that page is institutional—not a Part heading."""
    pdf.set_fill_color(72, 52, 200)
    pdf.rect(0, 0, pdf.w, 15, "F")
    pdf.set_xy(0, 3)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(font, "B", 10)
    pdf.cell(0, 5, _pdf_core_font_safe(_pdf_brand_name()), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(font, "", 7.5)
    pdf.set_text_color(238, 236, 255)
    pdf.cell(0, 4, _pdf_core_font_safe(topic_title or "Placement diagnostic"), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_C_INK)
    pdf.set_xy(pdf.l_margin, 20)


def _section_card_height_for_width(
    pdf: FPDF,
    font: str,
    s: dict[str, Any],
    card_w: float,
) -> float:
    """Match layout constants used in _draw_one_section_card_at."""
    accent_w = 1.2
    pad_x = 3.5
    row1_h = 5.5
    gap_after_row1 = 2.0
    title_line_h = 3.85
    cap_h = 3.4
    gap_cap_to_bar = 1.8
    bar_h = 2.8
    pad_bottom = 4.5
    inner_w = card_w - accent_w - pad_x * 2

    sec = str(s.get("section") or "")
    tit_raw = _pdf_core_font_safe(str(s.get("title_en") or ""))
    tit = _pdf_core_font_safe(_strip_part_prefix(sec, tit_raw))

    pdf.set_font(font, "", 8)
    pdf.set_text_color(*_C_MUTED)
    if MethodReturnValue is not None:
        # Never move to y=0 here — that corrupts the live cursor after the list comprehension.
        title_block_h = float(
            pdf.multi_cell(
                max(10.0, inner_w),
                title_line_h,
                tit or " ",
                dry_run=True,
                output=MethodReturnValue.HEIGHT,
            )
        )
    else:
        title_block_h = 10.0

    return (
        pad_x
        + row1_h
        + gap_after_row1
        + title_block_h
        + cap_h
        + gap_cap_to_bar
        + bar_h
        + pad_bottom
    )


def _draw_one_section_card_at(
    pdf: FPDF,
    font: str,
    s: dict[str, Any],
    x_left: float,
    y_top: float,
    card_w: float,
    h_card: float,
) -> None:
    accent_w = 1.2
    pad_x = 3.5
    row1_h = 5.5
    gap_after_row1 = 2.0
    title_line_h = 3.85
    cap_h = 3.4
    gap_cap_to_bar = 1.8
    bar_h = 2.8
    bar_margin = 3.5

    content_x = x_left + accent_w + pad_x
    inner_w = card_w - accent_w - pad_x * 2

    sec = _pdf_core_font_safe(str(s.get("section") or ""))
    tit_raw = _pdf_core_font_safe(str(s.get("title_en") or ""))
    tit = _pdf_core_font_safe(_strip_part_prefix(str(s.get("section") or ""), tit_raw))
    pct = int(s.get("pct") or 0)
    cor = int(s.get("correct") or 0)
    tot = int(s.get("total") or 0)

    pdf.set_fill_color(*_C_SURFACE)
    pdf.set_draw_color(208, 202, 228)
    pdf.set_line_width(0.2)
    pdf.rect(x_left, y_top, card_w, h_card, "DF", round_corners=False)
    pdf.set_fill_color(*_C_VIOLET)
    pdf.rect(x_left, y_top, accent_w, h_card, "F")

    y_cursor = y_top + pad_x
    pdf.set_xy(content_x, y_cursor)
    pdf.set_font(font, "B", 9.5)
    pdf.set_text_color(*_C_INK)
    pdf.cell(inner_w - 24, row1_h, _section_card_label(sec, bool(s.get("use_gate_label"))), align="L")
    pdf.set_text_color(*_C_VIOLET_SOFT)
    pdf.cell(24, row1_h, f"{pct}%", align="R")
    pdf.ln(row1_h)

    y_cursor = y_top + pad_x + row1_h + gap_after_row1
    pdf.set_xy(content_x, y_cursor)
    pdf.set_font(font, "", 8)
    pdf.set_text_color(*_C_MUTED)
    if tit:
        pdf.multi_cell(
            inner_w,
            title_line_h,
            tit,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    else:
        pdf.cell(inner_w, title_line_h, " ", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_xy(content_x, pdf.get_y())
    pdf.set_font(font, "", 6.8)
    pdf.set_text_color(120, 114, 148)
    pdf.cell(
        inner_w,
        cap_h,
        _pdf_core_font_safe(f"{cor} / {tot} in part"),
        align="L",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    bar_y = pdf.get_y() + gap_cap_to_bar
    bw = card_w - bar_margin * 2
    bx = x_left + bar_margin
    pdf.set_fill_color(228, 224, 242)
    pdf.rect(bx, bar_y, bw, bar_h, "F", round_corners=False)
    fw = max(0.0, min(bw, bw * (pct / 100.0)))
    if fw > 0.25:
        pdf.set_fill_color(72, 52, 200)
        pdf.rect(bx, bar_y, fw, bar_h, "F", round_corners=False)

    pdf.set_xy(x_left, y_top + h_card)


def _draw_section_cards(
    pdf: FPDF,
    font: str,
    section_stats: list[dict[str, Any]],
    topic_title: str,
) -> None:
    """Two-column part snapshot (page opened by caller)."""
    if not section_stats:
        pdf.set_font(font, "", 9)
        pdf.set_text_color(*_C_MUTED)
        pdf.multi_cell(
            0,
            5,
            _pdf_core_font_safe("No subsection tags were available for this export."),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        return

    cw = _content_width(pdf)
    col_gap = 3.5
    card_w = (cw - col_gap) / 2.0
    row_gap = 3.0
    footer_room = 24.0

    _sx, _sy = pdf.get_x(), pdf.get_y()
    heights = [_section_card_height_for_width(pdf, font, s, card_w) for s in section_stats]
    pdf.set_xy(_sx, _sy)
    row_max: list[float] = []
    for i in range(0, len(section_stats), 2):
        h1 = heights[i]
        h2 = heights[i + 1] if i + 1 < len(section_stats) else 0.0
        row_max.append(max(h1, h2))
    pdf.set_font(font, "", 8)
    pdf.set_text_color(*_C_MUTED)
    pdf.multi_cell(
        0,
        4,
        _pdf_core_font_safe(
            "Each card is one part of the diagnostic (I–V). The item-by-item table follows on the next page."
        ),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(2)

    y_row = pdf.get_y()
    lm = pdf.l_margin
    for i in range(0, len(section_stats), 2):
        rh = row_max[i // 2]
        if y_row + rh > pdf.h - pdf.b_margin - footer_room:
            pdf.add_page()
            _draw_sections_continuation_band(pdf, font, topic_title)
            pdf.ln(2)
            y_row = pdf.get_y()
        _draw_one_section_card_at(pdf, font, section_stats[i], lm, y_row, card_w, rh)
        if i + 1 < len(section_stats):
            _draw_one_section_card_at(
                pdf, font, section_stats[i + 1], lm + card_w + col_gap, y_row, card_w, rh
            )
        y_row += rh + row_gap
        pdf.set_xy(lm, y_row)

    pdf.set_xy(lm, y_row)


def _draw_trust_note(pdf: FPDF, font: str, placement_brand: dict[str, Any] | None) -> None:
    """Official band note under the score—height from dry_run so nothing clips."""
    if not placement_brand:
        return
    trust = _pdf_core_font_safe(str(placement_brand.get("trust_line") or ""))
    if not trust:
        return
    pdf.ln(3)
    cw = _content_width(pdf)
    x0 = pdf.l_margin
    y0 = pdf.get_y()
    text_w = cw - 14
    pdf.set_font(font, "", 8)
    pdf.set_text_color(*_C_MUTED)
    if MethodReturnValue is not None:
        th = float(
            pdf.multi_cell(
                text_w,
                4.2,
                trust,
                dry_run=True,
                output=MethodReturnValue.HEIGHT,
            )
        )
    else:
        th = 12.0
    box_h = max(13.0, th + 6.0)
    pdf.set_fill_color(246, 244, 252)
    pdf.set_draw_color(*_C_LINE)
    pdf.set_line_width(0.2)
    pdf.rect(x0, y0, cw, box_h, "DF", round_corners=False)
    pdf.set_fill_color(*_C_VIOLET)
    pdf.rect(x0, y0, 1.15, box_h, "F")
    pdf.set_xy(x0 + 5, y0 + 3)
    pdf.set_font(font, "", 8)
    pdf.set_text_color(*_C_MUTED)
    pdf.multi_cell(text_w, 4.2, trust, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_xy(x0, y0 + box_h + 4)
    pdf.set_text_color(*_C_INK)


def _draw_itemized_table(
    pdf: FPDF,
    font: str,
    rows: list[dict[str, Any]],
    draw_header_fn: Callable[[], None],
) -> None:
    w = _content_width(pdf)
    col_q = 14.0
    col_part = 16.0
    col_mid = (w - col_q - col_part - 34) / 2
    col_st = 34.0

    def header_row() -> None:
        pdf.set_font(font, "B", 8)
        pdf.set_fill_color(*_C_VIOLET)
        pdf.set_text_color(255, 255, 255)
        pdf.set_draw_color(70, 55, 180)
        pdf.set_line_width(0.2)
        h = 7.0
        pdf.cell(col_q, h, _pdf_core_font_safe("Q"), border=1, align="C", fill=True)
        pdf.cell(col_part, h, _pdf_core_font_safe("Part"), border=1, align="C", fill=True)
        pdf.cell(col_mid, h, _pdf_core_font_safe("Your answer"), border=1, align="C", fill=True)
        pdf.cell(col_mid, h, _pdf_core_font_safe("Correct key"), border=1, align="C", fill=True)
        pdf.cell(col_st, h, _pdf_core_font_safe("Result"), border=1, align="C", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*_C_INK)

    pdf.ln(6)
    pdf.set_font(font, "B", 13)
    pdf.set_text_color(*_C_INK)
    pdf.cell(0, 7, _pdf_core_font_safe("Itemized responses"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(font, "", 8)
    pdf.set_text_color(*_C_MUTED)
    pdf.multi_cell(
        0,
        4,
        _pdf_core_font_safe("One row per item from this session. Use with the in-app explanations for review."),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(2)
    header_row()

    pdf.set_font(font, "", 7.5)
    line_h = 5.2
    for idx, row in enumerate(rows):
        y = pdf.get_y()
        if y + line_h > pdf.h - pdf.b_margin - 18:
            pdf.add_page()
            draw_header_fn()
            pdf.ln(2)
            header_row()

        if idx % 2 == 0:
            pdf.set_fill_color(252, 251, 255)
        else:
            pdf.set_fill_color(246, 243, 255)

        st = str(row.get("status", "") or "")
        q = _pdf_core_font_safe(str(row.get("q_display", "")))
        part = _pdf_core_font_safe(str(row.get("knowledge_section", ""))[:8])
        yv = _pdf_core_font_safe(display_answer_plain(str(row.get("yours_display", "")), max_len=24))
        kv = _pdf_core_font_safe(display_answer_plain(str(row.get("key_display", "")), max_len=24))
        st_label = _pdf_core_font_safe(_status_label(st))
        r, g, b = _status_color(st)

        pdf.set_draw_color(*_C_LINE)
        pdf.set_text_color(*_C_INK)
        pdf.cell(col_q, line_h, q, border="LRBT", align="C", fill=True)
        pdf.cell(col_part, line_h, part, border="LRBT", align="C", fill=True)
        pdf.cell(col_mid, line_h, yv, border="LRBT", align="L", fill=True)
        pdf.cell(col_mid, line_h, kv, border="LRBT", align="L", fill=True)
        pdf.set_font(font, "B", 7)
        pdf.set_text_color(r, g, b)
        pdf.cell(col_st, line_h, st_label, border="LRBT", align="C", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font(font, "", 7.5)
        pdf.set_text_color(*_C_INK)


def build_placement_parent_pdf(ctx: dict[str, Any]) -> bytes:
    if FPDF is None or XPos is None or YPos is None:
        raise ImportError(_FPDF2_INSTALL_HINT)

    intelligent = ctx.get("intelligent_report")
    if isinstance(intelligent, dict) and intelligent.get("report_kind") == "bilingual_assessment":
        from placement_bilingual_pdf import build_bilingual_assessment_pdf

        return build_bilingual_assessment_pdf(intelligent)

    rows: list[dict[str, Any]] = ctx.get("rows") or []
    placement_rec: dict[str, Any] | None = ctx.get("placement_rec")
    placement_gate_scores: list[dict[str, Any]] = ctx.get("placement_gate_scores") or []
    placement_gate_rec: dict[str, Any] | None = ctx.get("placement_gate_rec")
    section_stats: list[dict[str, Any]] = ctx.get("section_stats") or []
    placement_brand: dict[str, Any] | None = ctx.get("placement_brand")
    use_gate_labels = bool(placement_gate_scores)
    if use_gate_labels:
        section_stats = [
            {**s, "use_gate_label": True} for s in section_stats
        ]

    pdf = _PlacementReportPDF("Helvetica")
    font = _setup_font(pdf)
    pdf._ff = font  # type: ignore[attr-defined]

    pdf.set_title(_pdf_core_font_safe(f"{_pdf_brand_name()} - Placement report"))
    pdf.alias_nb_pages()

    topic_title = _pdf_core_font_safe(str(ctx.get("topic_title") or "Placement diagnostic"))
    cc = int(ctx.get("correct_count") or 0)
    tq = int(ctx.get("placement_score_total") or ctx.get("total_q") or 85)
    pct = int(ctx.get("score_pct") or 0)

    pdf.add_page()
    _draw_hero_band(pdf, font, topic_title)
    stu = ctx.get("placement_student")
    _draw_student_profile(pdf, font, stu if isinstance(stu, dict) else {})
    _draw_score_card(pdf, font, cc, tq, pct)
    _draw_trust_note(pdf, font, placement_brand)

    if placement_gate_scores:
        _draw_gate_scores_panel(pdf, font, placement_gate_scores, placement_gate_rec)

    if placement_rec:
        _draw_panel_title(pdf, font, "Placement summary")
        if placement_gate_rec and placement_rec.get("gate_headline"):
            pdf.set_font(font, "B", 10)
            pdf.set_text_color(*_C_VIOLET)
            pdf.multi_cell(
                0,
                5.2,
                _pdf_core_font_safe(str(placement_rec.get("gate_title") or "")),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            pdf.set_font(font, "", 8.5)
            pdf.set_text_color(*_C_MUTED)
            pdf.multi_cell(
                0,
                4.8,
                _pdf_core_font_safe(str(placement_rec.get("gate_headline") or "")),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            pdf.ln(1)
            pdf.set_font(font, "", 8)
            pdf.set_text_color(*_C_MUTED)
            pdf.multi_cell(
                0,
                4.5,
                _pdf_core_font_safe(
                    f"Total score band: {placement_rec.get('band_range', '—')} correct (out of {tq})"
                ),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            pdf.ln(2)
        _draw_recommendation(pdf, font, placement_rec, tq)

    # Part snapshots always start on a new page so they never overlap the score block
    # (fpdf cursor + two-column rows previously could land on the same vertical band as RAW SCORE).
    pdf.add_page()
    _draw_sections_continuation_band(pdf, font, topic_title)
    _draw_panel_title(pdf, font, "Performance by gate" if use_gate_labels else "Performance by knowledge area")
    _draw_section_cards(pdf, font, section_stats, topic_title)

    attempt_id = ctx.get("attempt_id", "")

    def _continuation_header() -> None:
        pdf.set_font(font, "B", 11)
        pdf.set_text_color(*_C_MUTED)
        pdf.cell(0, 6, _pdf_core_font_safe("Itemized responses (continued)"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font(font, "", 7)
        pdf.set_text_color(*_C_MUTED)
        pdf.cell(0, 4, _pdf_core_font_safe(f"Attempt {attempt_id}  ·  {topic_title}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

    pdf.add_page()
    _draw_itemized_table(pdf, font, rows, _continuation_header)

    bio = BytesIO()
    pdf.output(bio)
    return bio.getvalue()
