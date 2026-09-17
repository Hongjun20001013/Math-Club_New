"""Precise SVG graph generation for AP Calculus Unit 1 lessons."""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Callable, Literal

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_DIR = os.path.join(APP_DIR, "static", "ap_calc", "figures")

PURPLE = "#6a4ce6"
PURPLE_DARK = "#4c3d99"
LEFT_COLOR = "#2563eb"
RIGHT_COLOR = "#ea580c"
GREEN = "#059669"
GRID = "#e8e4ff"
BG = "#faf8ff"


@dataclass
class PlotPoint:
    x: float
    y: float
    style: Literal["open", "filled", "none"] = "filled"
    label: str = ""
    r: float = 6


@dataclass
class PlotSegment:
    fn: Callable[[float], float]
    x0: float
    x1: float
    samples: int = 120
    color: str = PURPLE
    width: float = 3
    dashed: bool = False


@dataclass
class PlotLine:
    x0: float
    y0: float
    x1: float
    y1: float
    color: str = "#94a3b8"
    width: float = 2
    dashed: bool = True


@dataclass
class GraphSpec:
    graph_id: str
    title: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    segments: list[PlotSegment] = field(default_factory=list)
    lines: list[PlotLine] = field(default_factory=list)
    points: list[PlotPoint] = field(default_factory=list)
    v_asymptotes: list[float] = field(default_factory=list)
    notice: str = ""
    x_label: str = "x"
    y_label: str = "y"


def _x_map(x: float, spec: GraphSpec, w: int, pad_l: int, pad_r: int) -> float:
    return pad_l + (x - spec.x_min) / (spec.x_max - spec.x_min) * (w - pad_l - pad_r)


def _y_map(y: float, spec: GraphSpec, h: int, pad_t: int, pad_b: int) -> float:
    return h - pad_b - (y - spec.y_min) / (spec.y_max - spec.y_min) * (h - pad_t - pad_b)


def render_graph(spec: GraphSpec, width: int = 520, height: int = 320) -> str:
    pad_l, pad_r, pad_t, pad_b = 52, 24, 36, 44
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{spec.title}" class="ap-graph-svg">',
        f'<rect width="{width}" height="{height}" fill="{BG}" rx="12"/>',
    ]
    # grid
    for i in range(6):
        gx = pad_l + i * (width - pad_l - pad_r) / 5
        parts.append(f'<line x1="{gx:.1f}" y1="{pad_t}" x2="{gx:.1f}" y2="{height-pad_b}" stroke="{GRID}" stroke-width="1"/>')
    for i in range(5):
        gy = pad_t + i * (height - pad_t - pad_b) / 4
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width-pad_r}" y2="{gy:.1f}" stroke="{GRID}" stroke-width="1"/>')
    # axes
    parts.append(f'<line x1="{pad_l}" y1="{height-pad_b}" x2="{width-pad_r}" y2="{height-pad_b}" stroke="{PURPLE_DARK}" stroke-width="2"/>')
    parts.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height-pad_b}" stroke="{PURPLE_DARK}" stroke-width="2"/>')
    parts.append(f'<text x="{width-pad_r+4}" y="{height-pad_b+4}" font-size="13" fill="{PURPLE_DARK}">{spec.x_label}</text>')
    parts.append(f'<text x="{pad_l-8}" y="{pad_t-8}" font-size="13" fill="{PURPLE_DARK}">{spec.y_label}</text>')
    if spec.title:
        parts.append(f'<text x="{pad_l}" y="22" font-size="14" font-weight="700" fill="{PURPLE_DARK}">{spec.title}</text>')

    for va in spec.v_asymptotes:
        vx = _x_map(va, spec, width, pad_l, pad_r)
        parts.append(
            f'<line x1="{vx:.1f}" y1="{pad_t}" x2="{vx:.1f}" y2="{height-pad_b}" '
            f'stroke="#cbd5e1" stroke-width="1.5" stroke-dasharray="5 4"/>'
        )

    for seg in spec.segments:
        pts = []
        step = (seg.x1 - seg.x0) / max(seg.samples, 2)
        x = seg.x0
        while x <= seg.x1 + 1e-9:
            try:
                y = seg.fn(x)
                if math.isfinite(y):
                    pts.append(f"{_x_map(x, spec, width, pad_l, pad_r):.2f},{_y_map(y, spec, height, pad_t, pad_b):.2f}")
            except (ValueError, ZeroDivisionError):
                pass
            x += step
        if len(pts) >= 2:
            dash = ' stroke-dasharray="6 4"' if seg.dashed else ""
            parts.append(
                f'<polyline points="{" ".join(pts)}" fill="none" stroke="{seg.color}" '
                f'stroke-width="{seg.width}"{dash} stroke-linecap="round"/>'
            )

    for ln in spec.lines:
        x0, y0 = _x_map(ln.x0, spec, width, pad_l, pad_r), _y_map(ln.y0, spec, height, pad_t, pad_b)
        x1, y1 = _x_map(ln.x1, spec, width, pad_l, pad_r), _y_map(ln.y1, spec, height, pad_t, pad_b)
        dash = ' stroke-dasharray="6 4"' if ln.dashed else ""
        parts.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{ln.color}" stroke-width="{ln.width}"{dash}/>')

    for pt in spec.points:
        if pt.style == "none":
            continue
        cx = _x_map(pt.x, spec, width, pad_l, pad_r)
        cy = _y_map(pt.y, spec, height, pad_t, pad_b)
        if pt.style == "open":
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{pt.r}" fill="#fff" stroke="{PURPLE}" stroke-width="2.5"/>')
        else:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{pt.r}" fill="{PURPLE}"/>')
        if pt.label:
            parts.append(f'<text x="{cx+10:.1f}" y="{cy-8:.1f}" font-size="12" fill="{PURPLE_DARK}">{pt.label}</text>')

    if spec.notice:
        parts.append(
            f'<text x="{pad_l}" y="{height-8}" font-size="11" fill="#5b5380" font-style="italic">'
            f'Notice: {spec.notice}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def write_graph(spec: GraphSpec) -> str:
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, f"{spec.graph_id}.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_graph(spec))
    return f"/static/ap_calc/figures/{spec.graph_id}.svg"


def build_all_graphs() -> dict[str, str]:
    paths: dict[str, str] = {}

    # 1.1 position parabola s(t)=t^2+1
    paths["s_parabola_11"] = write_graph(GraphSpec(
        graph_id="s_parabola_11",
        title="s(t) = t² + 1",
        x_min=-0.5, x_max=4.5, y_min=0, y_max=18,
        x_label="t (s)", y_label="s (m)",
        segments=[PlotSegment(lambda t: t * t + 1, 0, 4)],
        points=[
            PlotPoint(2, 5, "filled", "(2, 5)"),
            PlotPoint(3, 10, "open", "(3, 10)"),
        ],
        notice="Secant from t=2 to t=3 has slope 5.",
    ))

    # Secant lines at t=2 for h=1,0.5,0.1
    def s(t: float) -> float:
        return t * t + 1

    segs_11 = [PlotSegment(s, 0, 4, color=PURPLE, width=2.5)]
    lines_11 = []
    for h, col in [(1, "#c4b5fd"), (0.5, "#a78bfa"), (0.1, LEFT_COLOR)]:
        slope = (s(2 + h) - s(2)) / h
        y0 = s(2) - slope * 2
        lines_11.append(PlotLine(0.5, y0 + slope * 0.5, 4, y0 + slope * 4, color=col, dashed=True))
    paths["secants_t2_11"] = write_graph(GraphSpec(
        graph_id="secants_t2_11",
        title="Secants approaching tangent at t = 2",
        x_min=0, x_max=4.2, y_min=0, y_max=18,
        x_label="t", y_label="s",
        segments=segs_11,
        lines=lines_11 + [PlotLine(0, s(2) - 4 * 2, 4.2, s(2) + 4 * 2.2, color=GREEN, width=2.5, dashed=False)],
        points=[PlotPoint(2, 5, "filled", "t=2")],
        notice="Blue secant (h=0.1) is closest to tangent slope 4.",
    ))

    # 1.2 Case A: continuous f(x)=x+1 at x=2, f(2)=3
    paths["limit_case_a"] = write_graph(GraphSpec(
        graph_id="limit_case_a",
        title="Case A: limit exists and equals f(c)",
        x_min=-1, x_max=5, y_min=-1, y_max=6,
        segments=[PlotSegment(lambda x: x + 1, -0.5, 4.5)],
        points=[PlotPoint(2, 3, "filled", "f(2)=3")],
        notice="lim x→2 f(x) = 3 = f(2).",
    ))

    # Case B: limit 5, f(3)=10 piecewise
    paths["limit_case_b"] = write_graph(GraphSpec(
        graph_id="limit_case_b",
        title="Case B: limit exists but f(c) differs",
        x_min=0, x_max=6, y_min=0, y_max=12,
        segments=[PlotSegment(lambda x: x + 2, 0.5, 5.5)],
        points=[PlotPoint(3, 5, "open", "→5"), PlotPoint(3, 10, "filled", "f(3)=10")],
        notice="lim x→3 f(x)=5 while f(3)=10.",
    ))

    # Case C: hole at (2,4), undefined at 2
    paths["limit_case_c"] = write_graph(GraphSpec(
        graph_id="limit_case_c",
        title="Case C: limit exists, f(c) undefined",
        x_min=0, x_max=5, y_min=0, y_max=7,
        segments=[PlotSegment(lambda x: 2 * x, 0.5, 1.9, color=PURPLE),
                  PlotSegment(lambda x: 2 * x, 2.1, 4.5, color=PURPLE)],
        points=[PlotPoint(2, 4, "open", "lim=4")],
        notice="f(2) is undefined; limit is 4.",
    ))

    # Case D: jump, f(c) defined
    paths["limit_case_d"] = write_graph(GraphSpec(
        graph_id="limit_case_d",
        title="Case D: limit DNE, f(c) defined",
        x_min=0, x_max=6, y_min=-2, y_max=5,
        segments=[
            PlotSegment(lambda x: -1.0, 0, 2.9, color=LEFT_COLOR),
            PlotSegment(lambda x: 2.0, 3.1, 5.5, color=RIGHT_COLOR),
        ],
        points=[PlotPoint(3, 0, "filled", "f(3)=0")],
        notice="Left → −1, right → 2; two-sided limit DNE.",
    ))

    # 1.3 piecewise from tex: x+1 for x<2, -x+5 for x>2, open (2,3), filled (2,1.5)
    paths["piecewise_limit_2"] = write_graph(GraphSpec(
        graph_id="piecewise_limit_2",
        title="lim x→2 f(x) = 3, f(2) = 1.5",
        x_min=-0.5, x_max=4.5, y_min=-0.5, y_max=5,
        segments=[
            PlotSegment(lambda x: x + 1, -0.5, 1.99, color=LEFT_COLOR),
            PlotSegment(lambda x: -x + 5, 2.01, 4.4, color=RIGHT_COLOR),
        ],
        points=[PlotPoint(2, 3, "open", "limit 3"), PlotPoint(2, 1.5, "filled", "f(2)=1.5")],
        notice="Both branches approach y=3. The filled point does not change the limit.",
    ))

    # Jump at 3
    paths["jump_at_3"] = write_graph(GraphSpec(
        graph_id="jump_at_3",
        title="Jump discontinuity at x = 3",
        x_min=0, x_max=6, y_min=-2, y_max=4,
        segments=[
            PlotSegment(lambda x: -1, 0, 2.99, color=LEFT_COLOR),
            PlotSegment(lambda x: 2, 3.01, 5.5, color=RIGHT_COLOR),
        ],
        points=[PlotPoint(3, -1, "open"), PlotPoint(3, 2, "open")],
        notice="lim x→3⁻ = −1, lim x→3⁺ = 2 → two-sided limit DNE.",
    ))

    # Infinite behavior
    paths["infinite_limit_13"] = write_graph(GraphSpec(
        graph_id="infinite_limit_13",
        title="Infinite behavior near x = 0",
        x_min=-2, x_max=2, y_min=-4, y_max=4,
        segments=[
            PlotSegment(lambda x: 1 / x, -1.9, -0.15, color=LEFT_COLOR),
            PlotSegment(lambda x: 1 / x, 0.15, 1.9, color=RIGHT_COLOR),
        ],
        v_asymptotes=[0],
        notice="|y| grows without bound as x→0⁺ or x→0⁻.",
    ))

    # Sketch task graph
    paths["sketch_task_13"] = write_graph(GraphSpec(
        graph_id="sketch_task_13",
        title="Sketch: lim x→2 f(x)=3, f(2)=−1",
        x_min=-1, x_max=5, y_min=-2, y_max=5,
        segments=[
            PlotSegment(lambda x: 0.5 * x + 2, 0, 1.99, color=PURPLE),
            PlotSegment(lambda x: -0.5 * x + 4, 2.01, 4.5, color=PURPLE),
        ],
        points=[PlotPoint(2, 3, "open", "→3"), PlotPoint(2, -1, "filled", "f(2)=−1")],
        notice="Open circle at limit height; filled dot at actual value.",
    ))

    # Removable hole only
    paths["removable_hole"] = write_graph(GraphSpec(
        graph_id="removable_hole",
        title="Removable discontinuity",
        x_min=0, x_max=5, y_min=0, y_max=6,
        segments=[PlotSegment(lambda x: x + 1, 0.5, 1.95),
                  PlotSegment(lambda x: x + 1, 2.05, 4.5)],
        points=[PlotPoint(2, 3, "open", "lim=3")],
        notice="A single point can be removed without changing the limit.",
    ))

    # Endpoint / one-sided domain: f(x)=sqrt(x) on [0,4]
    paths["endpoint_sqrt_13"] = write_graph(GraphSpec(
        graph_id="endpoint_sqrt_13",
        title="Endpoint: domain starts at x = 0",
        x_min=-0.5, x_max=4.5, y_min=-0.5, y_max=3.5,
        segments=[PlotSegment(lambda x: math.sqrt(x), 0, 4.2, color=PURPLE)],
        points=[PlotPoint(0, 0, "filled", "f(0)=0")],
        notice="Only a right-hand approach exists at x=0; lim x→0⁻ f(x) is undefined on this domain.",
    ))

    return paths


if __name__ == "__main__":
    built = build_all_graphs()
    print(f"Wrote {len(built)} graphs")
