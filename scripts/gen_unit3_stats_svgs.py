#!/usr/bin/env python3
"""Generate clean SVG versions of Unit 3 statistics figures."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "unit3"


FONT = "Georgia, Times New Roman, serif"
STROKE = "#333333"
GRID = "#767676"
FILL = "#b6b6b6"


def _svg(w: int, h: int, body: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="100%" height="100%" fill="#fff"/>
  <style>
    .label {{ font-family: {FONT}; fill: #111; font-size: 25px; }}
    .small {{ font-family: {FONT}; fill: #111; font-size: 20px; }}
    .axis {{ stroke: {STROKE}; stroke-width: 2; stroke-linecap: square; }}
    .thin {{ stroke: {STROKE}; stroke-width: 1.8; fill: none; }}
    .grid {{ stroke: {GRID}; stroke-width: 1.7; }}
  </style>
{body}
</svg>
"""


def _text(x: float, y: float, s: str, cls: str = "label", anchor: str = "middle") -> str:
    return f'  <text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}">{s}</text>'


def box_plots() -> str:
    w, h = 760, 300
    x0, x1 = 165, 705
    y_axis = 178
    scale_min, scale_max = 19, 32

    def x(v: float) -> float:
        return x0 + (v - scale_min) / (scale_max - scale_min) * (x1 - x0)

    def box(y: float, mn: float, q1: float, med: float, q3: float, mx: float) -> str:
        return "\n".join(
            [
                f'  <line x1="{x(mn):.1f}" y1="{y:.1f}" x2="{x(q1):.1f}" y2="{y:.1f}" class="thin"/>',
                f'  <line x1="{x(q3):.1f}" y1="{y:.1f}" x2="{x(mx):.1f}" y2="{y:.1f}" class="thin"/>',
                f'  <line x1="{x(mn):.1f}" y1="{y-16:.1f}" x2="{x(mn):.1f}" y2="{y+16:.1f}" class="thin"/>',
                f'  <line x1="{x(mx):.1f}" y1="{y-16:.1f}" x2="{x(mx):.1f}" y2="{y+16:.1f}" class="thin"/>',
                f'  <rect x="{x(q1):.1f}" y="{y-20:.1f}" width="{x(q3)-x(q1):.1f}" height="40" fill="#fff" stroke="{STROKE}" stroke-width="1.8"/>',
                f'  <line x1="{x(med):.1f}" y1="{y-20:.1f}" x2="{x(med):.1f}" y2="{y+20:.1f}" class="thin"/>',
            ]
        )

    body = [
        _text(28, 55, "Group 1", anchor="start"),
        _text(28, 112, "Group 2", anchor="start"),
        box(48, 21, 22, 25, 26, 28),
        box(103, 22, 23, 24, 25, 28),
        f'  <line x1="{x0:.1f}" y1="{y_axis}" x2="{x1+26:.1f}" y2="{y_axis}" class="axis"/>',
    ]
    for v in range(20, 33):
        tick_h = 16 if v % 2 == 0 else 11
        body.append(f'  <line x1="{x(v):.1f}" y1="{y_axis-tick_h:.1f}" x2="{x(v):.1f}" y2="{y_axis+tick_h:.1f}" class="axis"/>')
        if v % 2 == 0:
            body.append(_text(x(v), y_axis + 45, str(v), "label"))
    body.append(_text((x0 + x1) / 2 + 18, 270, "Mass (kilograms)", "label"))
    return _svg(w, h, "\n".join(body))


def dot_plots_ab() -> str:
    w, h = 760, 280
    y_axis = 178
    sections = [
        ("Data Set A", 45, {10: 1, 11: 4, 12: 2, 13: 3, 14: 2, 15: 4, 16: 1}),
        ("Data Set B", 420, {10: 2, 11: 4, 12: 2, 13: 1, 14: 2, 15: 4, 16: 2}),
    ]
    body: list[str] = []
    for title, left, counts in sections:
        step = 43
        body.append(_text(left + 150, 36, title, "label"))
        body.append(f'  <line x1="{left:.1f}" y1="{y_axis}" x2="{left + step*6 + 13:.1f}" y2="{y_axis}" class="axis"/>')
        for i, v in enumerate(range(10, 17)):
            xx = left + step * i
            body.append(f'  <line x1="{xx:.1f}" y1="{y_axis-13:.1f}" x2="{xx:.1f}" y2="{y_axis+13:.1f}" class="axis"/>')
            body.append(_text(xx, y_axis + 43, str(v), "label"))
            for k in range(counts[v]):
                cy = y_axis - 22 - 26 * k
                body.append(f'  <circle cx="{xx:.1f}" cy="{cy:.1f}" r="6.3" fill="#000"/>')
        body.append(_text(left + 150, 262, "Value", "label"))
    return _svg(w, h, "\n".join(body))


def histograms() -> str:
    w, h = 760, 390
    body: list[str] = []
    charts = [
        ("Data Set A", 80, [0, 3, 4, 7, 9]),
        ("Data Set B", 460, [3, 4, 7, 9, 0]),
    ]
    for title, left, vals in charts:
        top, bottom = 62, 295
        x_step = 43
        y_step = (bottom - top) / 12
        body.append(_text(left + 110, 34, title, "label"))
        for yv in range(0, 13):
            yy = bottom - yv * y_step
            if yv % 2 == 0:
                body.append(_text(left - 16, yy + 7, str(yv), "label", "end"))
            body.append(f'  <line x1="{left:.1f}" y1="{yy:.1f}" x2="{left + 210:.1f}" y2="{yy:.1f}" class="grid"/>')
        body.append(f'  <line x1="{left:.1f}" y1="{top:.1f}" x2="{left:.1f}" y2="{bottom:.1f}" class="axis"/>')
        for i, lab in enumerate([10, 20, 30, 40, 50, 60]):
            xx = left + i * x_step
            body.append(f'  <line x1="{xx:.1f}" y1="{bottom-8:.1f}" x2="{xx:.1f}" y2="{bottom+15:.1f}" class="axis"/>')
            body.append(_text(xx, bottom + 43, str(lab), "label"))
        for i, height in enumerate(vals):
            if height <= 0:
                continue
            x = left + i * x_step
            y = bottom - height * y_step
            body.append(f'  <rect x="{x:.1f}" y="{y:.1f}" width="{x_step:.1f}" height="{bottom-y:.1f}" fill="{FILL}" stroke="{STROKE}" stroke-width="1.6"/>')
        body.append(_text(left - 58, 178, "Frequency", "label", "middle").replace(">", ' transform="rotate(-90 %.1f 178)">' % (left - 58), 1))
        body.append(_text(left + 105, 380, "Integer", "label"))
    return _svg(w, h, "\n".join(body))


def dot_plot_a() -> str:
    w, h = 320, 260
    left, step, y_axis = 50, 55, 195
    counts = {22: 5, 23: 4, 24: 3, 25: 2, 26: 1}
    body = [_text(185, 33, "Data Set A", "label")]
    body.append(f'  <line x1="{left-25:.1f}" y1="{y_axis}" x2="{left+step*4+28:.1f}" y2="{y_axis}" class="axis"/>')
    for i, v in enumerate(range(22, 27)):
        xx = left + step * i
        body.append(f'  <line x1="{xx:.1f}" y1="{y_axis-13:.1f}" x2="{xx:.1f}" y2="{y_axis+13:.1f}" class="axis"/>')
        body.append(_text(xx, y_axis + 43, str(v), "label"))
        for k in range(counts[v]):
            body.append(f'  <circle cx="{xx:.1f}" cy="{y_axis - 24 - 24*k:.1f}" r="6.2" fill="#000"/>')
    return _svg(w, h, "\n".join(body))


def line_graph() -> str:
    w, h = 840, 640
    left, right = 118, 794
    top, bottom = 70, 505
    years = list(range(2003, 2016))
    values = [40, 12, 12.5, 13.5, 10, 5, 7.5, 56, 10, 2, 3, 32, 18]

    def x(year: int) -> float:
        return left + (year - 2003) / 12 * (right - left)

    def y(val: float) -> float:
        return bottom - val / 60 * (bottom - top)

    body: list[str] = []
    for v in range(0, 61, 10):
        yy = y(v)
        body.append(f'  <line x1="{left:.1f}" y1="{yy:.1f}" x2="{right:.1f}" y2="{yy:.1f}" class="grid"/>')
        body.append(_text(left - 18, yy + 8, str(v), "label", "end"))
    body.append(f'  <line x1="{left:.1f}" y1="{top:.1f}" x2="{left:.1f}" y2="{bottom+20:.1f}" class="axis"/>')
    body.append(f'  <line x1="{left-8:.1f}" y1="{bottom:.1f}" x2="{right+4:.1f}" y2="{bottom:.1f}" class="axis"/>')
    pts = " ".join(f"{x(yr):.1f},{y(v):.1f}" for yr, v in zip(years, values))
    body.append(f'  <polyline points="{pts}" fill="none" stroke="#222" stroke-width="3.2" stroke-linejoin="round" stroke-linecap="round"/>')
    for yr, v in zip(years, values):
        body.append(f'  <circle cx="{x(yr):.1f}" cy="{y(v):.1f}" r="7.5" fill="#222"/>')
    for yr in years:
        xx = x(yr)
        body.append(f'  <line x1="{xx:.1f}" y1="{bottom-12:.1f}" x2="{xx:.1f}" y2="{bottom+20:.1f}" class="axis"/>')
        body.append(_text(xx - 4, bottom + 66, str(yr), "label").replace(">", f' transform="rotate(-45 {xx-4:.1f} {bottom+66:.1f})">', 1))
    body.append(_text(215, y(40) - 18, "(2003, 40)", "label"))
    body.append(_text(398, y(20) + 18, "(2007, 10)", "label"))
    body.append(f'  <line x1="{430:.1f}" y1="{y(19):.1f}" x2="{x(2007)+8:.1f}" y2="{y(10)-8:.1f}" stroke="#222" stroke-width="2" marker-end="url(#arrow)"/>')
    body.insert(0, '  <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#222"/></marker></defs>')
    body.append(_text(42, 292, "Annual snowfall (inches)", "label").replace(">", ' transform="rotate(-90 42 292)">', 1))
    body.append(_text(457, 622, "Year", "label"))
    return _svg(w, h, "\n".join(body))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "unit3_line_graph_snowfall.svg": line_graph(),
        "unit3_boxplots_gazelles.svg": box_plots(),
        "unit3_dotplots_ab.svg": dot_plots_ab(),
        "unit3_histograms_ab.svg": histograms(),
        "unit3_dotplot_a.svg": dot_plot_a(),
    }
    for name, content in files.items():
        path = OUT / name
        path.write_text(content, encoding="utf-8")
        print("wrote", path)


if __name__ == "__main__":
    main()
