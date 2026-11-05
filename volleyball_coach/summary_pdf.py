"""One PDF for the numbers already on the pause card. Same formulas, no second scoreboard."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fpdf import FPDF

from volleyball_coach.quick import build_digest

FONT_PATH = Path(__file__).resolve().parents[1] / "fonts" / "NotoSansSC-Regular.otf"
NAVY = (12, 35, 64)
MUTED = (62, 81, 102)
COLUMBIA = (185, 217, 235)
LINE = (213, 227, 238)
WHITE = (255, 255, 255)


class _SummaryPDF(FPDF):
    def __init__(self, title: str):
        super().__init__(format="A4")
        self._title = title
        self.add_font("Noto", "", str(FONT_PATH))
        self.set_auto_page_break(auto=True, margin=16)
        self.set_margins(14, 16, 14)

    def footer(self):
        self.set_y(-12)
        self.set_font("Noto", size=8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, f"{self._title}  ·  第 {self.page_no()} 页", align="C")


def _text(pdf: _SummaryPDF, value: str, size: float = 10, color: tuple[int, int, int] = NAVY, height: float = 6) -> None:
    pdf.set_font("Noto", size=size)
    pdf.set_text_color(*color)
    pdf.multi_cell(0, height, value)
    pdf.ln(1)


def _rule(pdf: _SummaryPDF) -> None:
    pdf.set_draw_color(*LINE)
    pdf.set_line_width(0.3)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(3)


def _heading(pdf: _SummaryPDF, title: str) -> None:
    if pdf.get_y() > pdf.h - 40:
        pdf.add_page()
    pdf.ln(2)
    pdf.set_font("Noto", size=13)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
    _rule(pdf)


def _table(pdf: _SummaryPDF, headers: list[str], rows: list[list[str]], weights: list[float]) -> None:
    if not rows:
        _text(pdf, "这场这里还没有记录。", size=9, color=MUTED, height=5)
        return
    widths = [pdf.epw * weight / sum(weights) for weight in weights]
    line_h = 7

    def paint_header() -> None:
        pdf.set_font("Noto", size=8)
        pdf.set_fill_color(*NAVY)
        pdf.set_text_color(*WHITE)
        for header, width in zip(headers, widths):
            pdf.cell(width, line_h, header, border=0, align="C", fill=True)
        pdf.ln(line_h)

    paint_header()
    pdf.set_font("Noto", size=8)
    for index, row in enumerate(rows):
        if pdf.get_y() + line_h > pdf.h - 18:
            pdf.add_page()
            paint_header()
            pdf.set_font("Noto", size=8)
        pdf.set_fill_color(*(COLUMBIA if index % 2 == 0 else WHITE))
        pdf.set_text_color(*NAVY)
        for value, width in zip(row, widths):
            pdf.cell(width, line_h, str(value), border=0, align="C", fill=True)
        pdf.ln(line_h)
    pdf.ln(2)


def render_summary_pdf(digest: dict, *, team: str, opponent: str) -> bytes:
    title = f"{team} 对 {opponent}" if opponent else team
    pdf = _SummaryPDF(title)
    pdf.add_page()
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, pdf.w, 28, "F")
    pdf.set_y(6)
    pdf.set_font("Noto", size=9)
    pdf.set_text_color(*COLUMBIA)
    pdf.cell(0, 5, "场边快记  ·  数据汇总", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Noto", size=16)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 8, title, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_xy(pdf.l_margin, 34)

    if digest["sets"]:
        scores = "    ".join(f"第{item['set_index']}局 {item['score_us']}–{item['score_them']}" for item in digest["sets"])
        _text(pdf, scores, size=12)
    else:
        _text(pdf, "这场还没有记分。", size=12)
    pending = f"其中 {digest['pending']} 分待补，不进进攻成功率。" if digest["pending"] else "没有只记比分的球。"
    _text(pdf, f"已记 {digest['recorded']} 分。{pending} 未知不记成 0。分母为 0 显示 —。", size=9, color=MUTED, height=5)

    lines = digest["lines"]
    _heading(pdf, "整场")
    for label, key in (("进攻", "attack"), ("一传", "receive"), ("发球", "serve"), ("对方", "opp")):
        _text(pdf, f"{label}    {lines[key]}", size=10, height=5.5)

    team_row = digest["team"]
    _heading(pdf, "全队进攻")
    _text(
        pdf,
        f"{team_row['phrase']}    成功率 {team_row['rate']}    效率 {team_row['eff']}"
        + (f"    只计次数 {team_row['count_only']}" if team_row["count_only"] else ""),
        size=11,
    )
    _text(pdf, "成功率＝扣死/进攻次数。效率＝（扣死－失误－被拦死）/进攻次数。只计次数进分母，不计个人失误。", size=8, color=MUTED, height=4.5)

    _heading(pdf, "个人")
    _table(
        pdf,
        ["姓名", "进攻", "失误", "被拦", "成功率", "效率", "拦网得分", "ACE", "直接得分"],
        [
            [
                row["name"],
                row["phrase"],
                row["errors"],
                row["blocked"],
                f"{row['rate_ratio']} {row['rate']}".strip() if row.get("rate_ratio") else row["rate"],
                row["eff"],
                row["block_points"],
                row["ace"],
                row["points"],
            ]
            for row in digest["people"]
        ],
        [22, 28, 12, 12, 16, 16, 18, 12, 18],
    )
    _text(pdf, "直接得分＝扣死＋ACE＋拦死。扣球打手出界算扣死。被打手出界是对方的分，不加拦网得分。", size=8, color=MUTED, height=4.5)

    _heading(pdf, "一传")
    _table(
        pdf,
        ["姓名", "到位", "半到位", "不到位", "直接失分", "未知", "到位率"],
        [
            [row["name"], row["in_system"], row["half"], row["out"], row["error"], row["unknown"], row["rate"]]
            for row in digest["match"]["passes"]
        ],
        [24, 14, 16, 16, 18, 12, 16],
    )

    _heading(pdf, "发球")
    _table(
        pdf,
        ["姓名", "ACE", "失误", "逼不到位", "对方到位", "未知", "威胁", "进界"],
        [
            [row["name"], row["ace"], row["error"], row["out"], row["in_system"], row["unknown"], row["threat_ratio"], row["in_ratio"]]
            for row in digest["match"]["serves"]
        ],
        [24, 12, 12, 18, 18, 12, 14, 14],
    )
    _text(pdf, "威胁＝（ACE＋逼不到位）/已判定。未知不进威胁的分母。进界＝（总数－失误）/总数。", size=8, color=MUTED, height=4.5)

    if digest["match"]["opponents"]:
        _heading(pdf, "对方起攻")
        _table(
            pdf,
            ["位置", "结果", "线路", "备注"],
            [
                [row["name"], row["phrase"], row["line_text"] or "—", row["line_note"] or "—"]
                for row in digest["match"]["opponents"]
            ],
            [22, 32, 40, 28],
        )
        _text(pdf, "不猜号码。线路只标在已记的球上。", size=8, color=MUTED, height=4.5)

    if len(digest["sets"]) > 1:
        _heading(pdf, "分局")
        for item in digest["sets"]:
            _text(pdf, f"第{item['set_index']}局  {item['score_us']}–{item['score_them']}    {item['team']['phrase']}    成功率 {item['team']['rate']}", size=10, height=5.5)
            _text(pdf, item["lines"]["receive"], size=9, color=MUTED, height=5)

    _heading(pdf, "逐回合")
    if not digest["detail"]:
        _text(pdf, "没有已结分的回合。", size=9, color=MUTED, height=5)
    for row in digest["detail"]:
        mark = "  待补" if row["pending"] else ""
        _text(
            pdf,
            f"第{row['set_index']}局  {row['score']} → {row['winner']}  {row['story']}{mark}",
            size=8,
            height=4.6,
        )

    output = BytesIO()
    pdf.output(output)
    return output.getvalue()


def summary_pdf_bytes(rallies: list[dict], actions: list[dict], names: dict[str, str], *, team: str, opponent: str) -> bytes:
    return render_summary_pdf(build_digest(rallies, actions, names), team=team, opponent=opponent)
