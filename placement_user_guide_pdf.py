"""Bilingual PDF user guide for Novel Prep course placement (students + advisors)."""

from __future__ import annotations

import os
from io import BytesIO
from typing import Any

from placement_bilingual_pdf import (
    FPDF,
    XPos,
    YPos,
    _BilingualReportPDF,
    _FPDF2_INSTALL_HINT,
    _bilingual_block,
    _clean,
    _content_width,
    _section_title,
    _set_font,
    _setup_bilingual_font,
)
from placement_report_pdf import _pdf_brand_name

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_SITE = os.environ.get("PLACEMENT_GUIDE_SITE_BASE", "https://novel-prep-sat-0f9q.onrender.com").rstrip(
    "/"
)

_C_MUTED = (97, 91, 115)
_C_DEEP = (79, 50, 152)
_C_NAVY = (42, 36, 70)
_C_LILAC_BG = (250, 247, 255)
_C_LINE = (216, 204, 245)


def _site(site_base: str | None) -> str:
    return (site_base or _DEFAULT_SITE).rstrip("/")


def _bullet_block(pdf: FPDF, primary: str, items: list[tuple[str, str]], font_size: float = 9.0) -> None:
    w = _content_width(pdf)
    line_h = 4.6
    for en, zh in items:
        if pdf.get_y() > pdf.h - pdf.b_margin - 18:
            pdf.add_page()
        text = _bilingual_block(en, zh)
        _set_font(pdf, primary, font_size)
        pdf.set_text_color(*_C_NAVY)
        pdf.multi_cell(w, line_h, f"• {text}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1.2)
    pdf.set_text_color(32, 27, 51)


def _numbered_steps(pdf: FPDF, primary: str, steps: list[tuple[str, str]]) -> None:
    w = _content_width(pdf)
    for i, (en, zh) in enumerate(steps, start=1):
        if pdf.get_y() > pdf.h - pdf.b_margin - 20:
            pdf.add_page()
        _set_font(pdf, primary, 10)
        pdf.set_text_color(*_C_DEEP)
        pdf.cell(8, 5.5, f"{i}.", new_x=XPos.RIGHT, new_y=YPos.TOP)
        _set_font(pdf, primary, 9)
        pdf.set_text_color(32, 27, 51)
        pdf.multi_cell(w - 8, 4.6, _bilingual_block(en, zh), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)


def _url_line(pdf: FPDF, primary: str, label: str, url: str) -> None:
    w = _content_width(pdf)
    _set_font(pdf, primary, 8.5)
    pdf.set_text_color(*_C_MUTED)
    pdf.multi_cell(w, 4.2, f"{label}: {url}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(32, 27, 51)
    pdf.ln(1)


def _draw_cover(pdf: FPDF, primary: str, site: str) -> None:
    w = _content_width(pdf)
    pdf.ln(8)
    _set_font(pdf, primary, 8)
    pdf.set_text_color(*_C_DEEP)
    pdf.cell(0, 5, f"{_pdf_brand_name().upper()} · COURSE PLACEMENT", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)
    _set_font(pdf, primary, 20)
    pdf.set_text_color(*_C_NAVY)
    pdf.cell(0, 10, "Placement User Guide", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    _set_font(pdf, primary, 14)
    pdf.cell(0, 8, "分班测评使用教程", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    _set_font(pdf, primary, 10)
    pdf.set_text_color(*_C_MUTED)
    pdf.multi_cell(
        w,
        5,
        _bilingual_block(
            "For students, parents, and advisors — English and Math diagnostics on the web.",
            "面向学生、家长与顾问老师——涵盖英语与数学分班测评的完整线上流程。",
        ),
        align="C",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(8)
    y0 = pdf.get_y()
    pdf.set_fill_color(*_C_LILAC_BG)
    pdf.set_draw_color(*_C_LINE)
    pdf.rect(pdf.l_margin, y0, w, 28, "DF", round_corners=True, corner_radius=3)
    pdf.set_xy(pdf.l_margin + 5, y0 + 4)
    _set_font(pdf, primary, 9)
    pdf.set_text_color(32, 27, 51)
    pdf.multi_cell(
        w - 10,
        4.8,
        _bilingual_block(
            "No login is required to take a test. Advisors sign in to review answers, grade writing, and export PDF reports.",
            "学生测评无需登录；老师登录后台批阅、给写作打分并导出 PDF 报告。",
        ),
    )
    pdf.set_xy(pdf.l_margin, y0 + 32)
    _url_line(pdf, primary, "Placement home 测评首页", f"{site}/placement")
    _url_line(pdf, primary, "Web guide 网页版教程", f"{site}/guide/placement")
    pdf.ln(4)


def _catalog_table(pdf: FPDF, primary: str) -> None:
    from placement_bilingual_pdf import _draw_table_row

    _section_title(pdf, primary, "Available diagnostics", "可选测评")
    w = _content_width(pdf)
    cols = [w * 0.28, w * 0.14, w * 0.12, w - w * 0.54]
    headers = ["Test 测评", "Items 题量", "Time 分钟", "Notes 说明"]
    _draw_table_row(pdf, primary, cols, headers, font_size=8, header=True, min_h=8)
    rows = [
        (
            "English G7–8\n英语 G7–8",
            "32",
            "55",
            "Reading + Language + Writing essay\n阅读+语言+写作",
        ),
        (
            "English G9–11\n英语 G9–11",
            "41",
            "65",
            "Same three-part arc; longer passages\n同上，篇幅更长",
        ),
        (
            "Middle Level Math\n中学数学",
            "100",
            "150",
            "Fill-in; five readiness bands\n填空；五段能力带",
        ),
        (
            "Enhanced Math I\n强化数学 I",
            "65",
            "120",
            "50 MCQ + paper PDF upload\n选择题+纸质卷上传",
        ),
        (
            "Enhanced Math II\n强化数学 II",
            "69",
            "130",
            "55 MCQ + paper PDF upload\n选择题+纸质卷上传",
        ),
        (
            "Upper Algebra / Precalc\n高阶代数预备微积分",
            "85",
            "115",
            "Five-gate MCQ diagnostic\n五关选择题",
        ),
    ]
    for idx, row in enumerate(rows):
        fill = (252, 250, 255) if idx % 2 == 0 else (246, 243, 255)
        _draw_table_row(pdf, primary, cols, row, font_size=7.8, fill=fill, min_h=10)
    pdf.ln(2)


def build_placement_user_guide_pdf(site_base: str | None = None) -> bytes:
    if FPDF is None or XPos is None or YPos is None:
        raise ImportError(_FPDF2_INSTALL_HINT)

    site = _site(site_base)
    pdf = _BilingualReportPDF("Helvetica", "Placement User Guide · 分班教程")
    primary = _setup_bilingual_font(pdf)
    pdf._primary = primary  # type: ignore[attr-defined]
    pdf.set_title(f"{_pdf_brand_name()} Placement Guide")
    pdf.alias_nb_pages()
    pdf.add_page()
    _draw_cover(pdf, primary, site)

    _section_title(pdf, primary, "Quick start — students", "学生快速上手")
    _numbered_steps(
        pdf,
        primary,
        [
            (
                f"Open {site}/placement and choose English or Math track.",
                f"打开 {site}/placement，选择英语或数学测评。",
            ),
            (
                "Pick the diagnostic that matches the student's grade (e.g. English G7–8).",
                "选择与学生年级匹配的测评（如 English G7–8）。",
            ),
            (
                "Complete the short profile (name, grade, school, advisor). Check the counselor confirmation box.",
                "填写姓名、年级、学校、顾问老师，并勾选顾问确认项。",
            ),
            (
                "On the Ready screen, copy the 24-hour recovery code. Keep it private — it reopens the same sitting on this device or another.",
                "在 Ready 页面复制 24 小时恢复码，妥善保存，可在本机或其他设备继续同一场考试。",
            ),
            (
                "Work through questions. Use Save & next or autosave. When completely done, click Submit test in the header and confirm.",
                "逐题作答，使用「保存并下一题」或自动保存。全部完成后点击页眉 Submit test 并确认交卷。",
            ),
        ],
    )

    _section_title(pdf, primary, "English placement flow", "英语测评流程")
    _bullet_block(
        pdf,
        primary,
        [
            (
                "Part I Reading and Part II Language are multiple-choice; answers auto-score when you save.",
                "阅读与语言部分为选择题，保存后系统自动判分。",
            ),
            (
                "Short transition screens appear between parts — read the timer and continue.",
                "各部分之间有过渡页，注意计时并点击继续。",
            ),
            (
                "Part III Writing: choose Option A or B, type the essay (word target shown). Autosave runs while you type.",
                "写作部分：选 A/B 题目，在文本框写作（有字数建议），输入时会自动保存。",
            ),
            (
                "Click Save essay & continue, then Submit test. Essays are not auto-scored — your advisor grades with the 20-point rubric.",
                "点击 Save essay & continue，再 Submit test。作文不自动打分，顾问老师按 20 分量表批阅。",
            ),
        ],
    )

    _section_title(pdf, primary, "Math placement flow", "数学测评流程")
    _bullet_block(
        pdf,
        primary,
        [
            (
                "Middle Level: type numeric answers (fractions, units, and common formats accepted). Use the on-screen entry guide for symbols.",
                "中学数学：填空作答（分数、单位等常见格式均可），可参考页面上的输入说明。",
            ),
            (
                "Enhanced Math I/II: finish on-screen MCQ, then upload one combined PDF of graphing and free-response work before final submit.",
                "强化数学 I/II：完成屏幕选择题后，上传含作图与解答的合并 PDF，再最终交卷。",
            ),
            (
                "Upper Algebra / Precalc: five gates with transition screens; MCQ auto-scores on save.",
                "高阶代数：五关结构，过渡页之间推进；选择题保存后自动判分。",
            ),
            (
                "Paper sections are reviewed by advisors; provisional scores update after paper grading.",
                "纸质部分由老师批阅，评分后报告分数会更新。",
            ),
        ],
    )

    pdf.add_page()
    _catalog_table(pdf, primary)

    _section_title(pdf, primary, "Advisor / teacher workflow", "顾问老师工作流程")
    _numbered_steps(
        pdf,
        primary,
        [
            (
                f"Sign in at {site}/login (admin or staff account from your team lead).",
                f"在 {site}/login 使用管理员/教务账号登录。",
            ),
            (
                "Open Admin → Placement testers (or /admin/placement-candidates). Filter Math vs English if needed.",
                "进入 Admin → Placement testers（或 /admin/placement-candidates），可按数学/英语筛选。",
            ),
            (
                "Click a student row for the full report: section scores, writing snapshot, and item list.",
                "点击学生行查看总报告：各部分分数、写作摘要、逐题列表。",
            ),
            (
                "Open any item to see the question, student answer, and key. Override auto-score if needed.",
                "打开单题查看题干、学生答案与标准答案，必要时可手动改分。",
            ),
            (
                "For English writing: open the last item or the writing panel, score each rubric row (20 pts max), then save.",
                "英语写作：打开最后一题或写作面板，按量表每项打分（满分 20），保存。",
            ),
            (
                "Download report.pdf for parents — English reports include reading, language, and writing levels.",
                "下载 report.pdf 给家长——英语报告含阅读、语言、写作等级。",
            ),
            (
                "Reopen a sitting only if the student must fix answers; otherwise keep status Submitted.",
                "仅在学生需要改答时 Reopen；否则保持 Submitted 状态。",
            ),
        ],
    )

    _section_title(pdf, primary, "Recovery & troubleshooting", "恢复与常见问题")
    _bullet_block(
        pdf,
        primary,
        [
            (
                "Lost session? Go to /placement/recover and enter the recovery code from the Ready screen.",
                "中途退出？打开 /placement/recover，输入 Ready 页的恢复码。",
            ),
            (
                "Open sittings expire after 24 hours if not submitted; advisors only see finished or in-progress sittings in the roster.",
                "未交卷的开放场次 24 小时后过期；名单主要显示进行中或已提交记录。",
            ),
            (
                "If an essay looks empty in admin, ensure the student clicked Submit test after writing (autosave is promoted on submit).",
                "若后台看不到作文，请确认学生写作后已 Submit test（交卷时会合并自动保存内容）。",
            ),
            (
                "For Enhanced Math paper upload issues, use one PDF, under the size limit, before the final submit button.",
                "强化数学 PDF 上传失败时，请交卷前上传单个 PDF，并注意大小限制。",
            ),
            (
                f"Student SAT practice accounts are separate from placement — use /guide for Workspace help.",
                f"SAT 练习账号与分班测评分开——Workspace 说明见 /guide。",
            ),
        ],
    )

    _section_title(pdf, primary, "Roles at a glance", "角色一览")
    _bullet_block(
        pdf,
        primary,
        [
            ("Student: take test, keep recovery code, submit when finished.", "学生：完成测评、保存恢复码、最后交卷。"),
            ("Parent: help with recovery code and PDF; no admin login needed.", "家长：协助保存恢复码与查看 PDF，无需后台账号。"),
            ("Advisor: review roster, grade writing/paper, export PDF, advise placement.", "顾问：查看名单、批写作/纸质题、导出 PDF、给出分班建议。"),
        ],
    )

    pdf.ln(4)
    _set_font(pdf, primary, 8)
    pdf.set_text_color(*_C_MUTED)
    w = _content_width(pdf)
    pdf.multi_cell(
        w,
        4.2,
        _clean(
            f"Document generated for {_pdf_brand_name()}. Live URLs use {site}. "
            "Re-run scripts/build_placement_user_guide_pdf.py after changing copy or site base."
        ),
    )

    bio = BytesIO()
    pdf.output(bio)
    return bio.getvalue()
