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
    color: str = PURPLE


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
class PlotLabel:
    x: float
    y: float
    text: str
    color: str = PURPLE_DARK
    size: int = 11
    anchor: str = "start"  # start | middle | end


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
    labels: list[PlotLabel] = field(default_factory=list)
    v_asymptotes: list[float] = field(default_factory=list)
    breakpoints: list[float] = field(default_factory=list)
    notice: str = ""
    x_label: str = "x"
    y_label: str = "y"


def _x_map(x: float, spec: GraphSpec, w: int, pad_l: int, pad_r: int) -> float:
    return pad_l + (x - spec.x_min) / (spec.x_max - spec.x_min) * (w - pad_l - pad_r)


def _y_map(y: float, spec: GraphSpec, h: int, pad_t: int, pad_b: int) -> float:
    return h - pad_b - (y - spec.y_min) / (spec.y_max - spec.y_min) * (h - pad_t - pad_b)


def _nice_step(span: float, target: int = 5) -> float:
    if span <= 0:
        return 1.0
    raw = span / max(target, 1)
    mag = 10 ** math.floor(math.log10(raw))
    norm = raw / mag
    if norm <= 1:
        nice = 1
    elif norm <= 2:
        nice = 2
    elif norm <= 5:
        nice = 5
    else:
        nice = 10
    return nice * mag


def _tick_values(vmin: float, vmax: float, target: int = 5) -> list[float]:
    if vmax <= vmin:
        return [vmin]
    step = _nice_step(vmax - vmin, target)
    start = math.ceil(vmin / step - 1e-9) * step
    ticks: list[float] = []
    v = start
    while v <= vmax + step * 0.001:
        ticks.append(v)
        v += step
    return ticks


def _format_tick(v: float) -> str:
    if abs(v) < 1e-9:
        return "0"
    if abs(v - round(v)) < 1e-6:
        return str(int(round(v)))
    return f"{v:.2g}"


def _append_axis_ticks(
    parts: list[str],
    spec: GraphSpec,
    width: int,
    height: int,
    pad_l: int,
    pad_r: int,
    pad_t: int,
    pad_b: int,
    font_pt: int,
    compact: bool,
) -> None:
    target = 3 if compact else 5
    tick_len = 4 if compact else 6
    label_fs = max(8, font_pt - 2) if compact else font_pt
    axis_y = height - pad_b
    axis_x = pad_l
    x_ticks = _tick_values(spec.x_min, spec.x_max, target)
    y_ticks = _tick_values(spec.y_min, spec.y_max, target)
    for xv in x_ticks:
        px = _x_map(xv, spec, width, pad_l, pad_r)
        parts.append(
            f'<line x1="{px:.1f}" y1="{axis_y:.1f}" x2="{px:.1f}" y2="{axis_y + tick_len:.1f}" '
            f'stroke="{PURPLE_DARK}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{px:.1f}" y="{axis_y + tick_len + (14 if not compact else 11):.1f}" '
            f'text-anchor="middle" font-size="{label_fs}" fill="{PURPLE_DARK}">{_format_tick(xv)}</text>'
        )
    for yv in y_ticks:
        py = _y_map(yv, spec, height, pad_t, pad_b)
        parts.append(
            f'<line x1="{axis_x - tick_len:.1f}" y1="{py:.1f}" x2="{axis_x:.1f}" y2="{py:.1f}" '
            f'stroke="{PURPLE_DARK}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{axis_x - 6:.1f}" y="{py + 4:.1f}" text-anchor="end" '
            f'font-size="{label_fs}" fill="{PURPLE_DARK}">{_format_tick(yv)}</text>'
        )


def render_graph(
    spec: GraphSpec,
    width: int = 520,
    height: int = 340,
    compact: bool = False,
) -> str:
    if compact:
        pad_l, pad_r, pad_t, pad_b = 26, 10, 14, 22
        stroke_w = 2
        pt_r = 4
        font_pt = 9
        rx = 8
    else:
        pad_l, pad_r, pad_t, pad_b = 58, 28, 52, 48
        stroke_w = 3
        pt_r = 6
        font_pt = 12
        rx = 12
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{spec.title}" class="ap-graph-svg'
        f'{" ap-graph-svg--compact" if compact else ""}">',
        f'<rect width="{width}" height="{height}" fill="{BG}" rx="{rx}"/>',
    ]
    if spec.title and not compact:
        parts.append(
            f'<text x="{width / 2:.1f}" y="24" text-anchor="middle" font-size="14" '
            f'font-weight="700" fill="{PURPLE_DARK}">{spec.title}</text>'
        )
    # grid
    for i in range(6):
        gx = pad_l + i * (width - pad_l - pad_r) / 5
        parts.append(f'<line x1="{gx:.1f}" y1="{pad_t}" x2="{gx:.1f}" y2="{height-pad_b}" stroke="{GRID}" stroke-width="1"/>')
    for i in range(5):
        gy = pad_t + i * (height - pad_t - pad_b) / 4
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width-pad_r}" y2="{gy:.1f}" stroke="{GRID}" stroke-width="1"/>')
    # axes
    axis_w = "1.25" if compact else "1.5"
    parts.append(
        f'<line x1="{pad_l}" y1="{height-pad_b}" x2="{width-pad_r}" y2="{height-pad_b}" '
        f'stroke="{PURPLE_DARK}" stroke-width="{axis_w}"/>'
    )
    parts.append(
        f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height-pad_b}" '
        f'stroke="{PURPLE_DARK}" stroke-width="{axis_w}"/>'
    )
    _append_axis_ticks(parts, spec, width, height, pad_l, pad_r, pad_t, pad_b, font_pt, compact)
    if not compact:
        parts.append(
            f'<text x="{width - pad_r + 2:.1f}" y="{height - pad_b + 18:.1f}" text-anchor="end" '
            f'font-size="{font_pt}" fill="{PURPLE_DARK}">{spec.x_label}</text>'
        )
        parts.append(
            f'<text x="16" y="{(pad_t + height - pad_b) / 2:.1f}" text-anchor="middle" '
            f'font-size="{font_pt}" fill="{PURPLE_DARK}" '
            f'transform="rotate(-90 16 {(pad_t + height - pad_b) / 2:.1f})">'
            f'{spec.y_label}</text>'
        )

    for va in spec.v_asymptotes:
        vx = _x_map(va, spec, width, pad_l, pad_r)
        parts.append(
            f'<line x1="{vx:.1f}" y1="{pad_t}" x2="{vx:.1f}" y2="{height-pad_b}" '
            f'stroke="#cbd5e1" stroke-width="1.5" stroke-dasharray="5 4"/>'
        )

    for bx in spec.breakpoints:
        vx = _x_map(bx, spec, width, pad_l, pad_r)
        parts.append(
            f'<line x1="{vx:.1f}" y1="{pad_t}" x2="{vx:.1f}" y2="{height-pad_b}" '
            f'stroke="rgba(106,76,230,0.22)" stroke-width="1.5" stroke-dasharray="4 5"/>'
        )
        if not compact:
            parts.append(
                f'<text x="{vx:.1f}" y="{pad_t - 6:.1f}" text-anchor="middle" font-size="10" '
                f'fill="#7c6fc9" font-weight="600">x={_format_tick(bx)}</text>'
            )

    y_pad = (spec.y_max - spec.y_min) * 0.04
    y_lo = spec.y_min - y_pad
    y_hi = spec.y_max + y_pad
    max_dy_px = 55 if not compact else 28

    def _emit_polyline(chunk: list[str], seg: PlotSegment) -> None:
        if len(chunk) < 2:
            return
        dash = ' stroke-dasharray="6 4"' if seg.dashed else ""
        sw = seg.width if not compact else stroke_w
        parts.append(
            f'<polyline points="{" ".join(chunk)}" fill="none" stroke="{seg.color}" '
            f'stroke-width="{sw}"{dash} stroke-linecap="round" stroke-linejoin="round"/>'
        )

    for seg in spec.segments:
        pts: list[str] = []
        prev_py: float | None = None
        step = (seg.x1 - seg.x0) / max(seg.samples, 2)
        x = seg.x0
        while x <= seg.x1 + 1e-9:
            try:
                y = seg.fn(x)
                if not math.isfinite(y) or y < y_lo or y > y_hi:
                    if pts:
                        _emit_polyline(pts, seg)
                        pts = []
                    prev_py = None
                else:
                    px = _x_map(x, spec, width, pad_l, pad_r)
                    py = _y_map(y, spec, height, pad_t, pad_b)
                    if py < pad_t or py > height - pad_b:
                        if pts:
                            _emit_polyline(pts, seg)
                            pts = []
                        prev_py = None
                        x += step
                        continue
                    if prev_py is not None and abs(py - prev_py) > max_dy_px:
                        if pts:
                            _emit_polyline(pts, seg)
                        pts = []
                    pts.append(f"{px:.2f},{py:.2f}")
                    prev_py = py
            except (ValueError, ZeroDivisionError):
                if pts:
                    _emit_polyline(pts, seg)
                    pts = []
                prev_py = None
            x += step
        if pts:
            _emit_polyline(pts, seg)

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
        r = pt.r if not compact else pt_r
        col = pt.color or PURPLE
        if pt.style == "open":
            parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="#fff" '
                f'stroke="{col}" stroke-width="2.5"/>'
            )
        else:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{col}"/>')
        if pt.label and not compact:
            lx, ly = cx + 10, cy - 8
            if cy < pad_t + 28:
                ly = cy + 18
            parts.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="{font_pt}" '
                f'fill="{PURPLE_DARK}">{pt.label}</text>'
            )

    for lab in spec.labels:
        if compact:
            continue
        lx = _x_map(lab.x, spec, width, pad_l, pad_r)
        ly = _y_map(lab.y, spec, height, pad_t, pad_b)
        tw = max(36, len(lab.text) * 6.2)
        parts.append(
            f'<rect x="{lx - (4 if lab.anchor == "start" else tw/2):.1f}" y="{ly - 14:.1f}" '
            f'width="{tw:.1f}" height="18" rx="6" fill="rgba(255,255,255,0.92)" '
            f'stroke="{lab.color}" stroke-width="1"/>'
        )
        tx = lx if lab.anchor == "start" else (lx - tw / 2 if lab.anchor == "middle" else lx - tw + 4)
        parts.append(
            f'<text x="{tx + 6:.1f}" y="{ly:.1f}" text-anchor="start" font-size="{lab.size}" '
            f'font-weight="600" fill="{lab.color}">{lab.text}</text>'
        )

    if spec.notice and not compact:
        parts.append(
            f'<text x="{pad_l}" y="{height-8}" font-size="11" fill="#5b5380" font-style="italic">'
            f'Notice: {spec.notice}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def write_graph(spec: GraphSpec, variant: str = "full") -> str:
    """Write SVG. variant: full (teaching), thumb (4-across strip), gallery (2×2 grid)."""
    os.makedirs(FIG_DIR, exist_ok=True)
    sizes = {"full": (520, 340), "thumb": (216, 128), "gallery": (280, 168)}
    if variant not in sizes:
        raise ValueError(f"unknown variant: {variant}")
    compact = variant != "full"
    w, h = sizes[variant]
    suffix = "" if variant == "full" else f"_{variant}"
    graph_id = f"{spec.graph_id}{suffix}"
    path = os.path.join(FIG_DIR, f"{graph_id}.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_graph(spec, width=w, height=h, compact=compact))
    return f"/static/ap_calc/figures/{graph_id}.svg"


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
    # Difference quotient rise/run at t=2, h=1
    paths["diff_quotient_11"] = write_graph(GraphSpec(
        graph_id="diff_quotient_11",
        title="Rise Δs and run h at t = 2",
        x_min=0, x_max=4.2, y_min=0, y_max=18,
        x_label="t (s)", y_label="s (m)",
        segments=[PlotSegment(s, 0, 4)],
        lines=[
            PlotLine(2, s(2), 3, s(2), color=RIGHT_COLOR, width=2.5, dashed=True),
            PlotLine(3, s(2), 3, s(3), color=LEFT_COLOR, width=2.5, dashed=True),
            PlotLine(2, s(2), 3, s(3), color="#94a3b8", width=2, dashed=True),
        ],
        points=[
            PlotPoint(2, s(2), "filled", "a"),
            PlotPoint(3, s(3), "open", "a+h"),
        ],
        notice="Blue vertical = Δs; orange horizontal = h; gray = secant slope.",
    ))

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

    # 1.2 Four contrast cases (aligned with interactive lab specs at x = 3)
    case_a = GraphSpec(
        graph_id="limit_case_a",
        title="Case A: limit exists and equals f(c)",
        x_min=0, x_max=6, y_min=0, y_max=10,
        segments=[PlotSegment(lambda x: x + 2, 0.5, 5.5)],
        points=[PlotPoint(3, 5, "filled")],
        notice="lim x→3 f(x) = 5 = f(3).",
    )
    case_b = GraphSpec(
        graph_id="limit_case_b",
        title="Case B: limit exists but f(c) differs",
        x_min=0, x_max=6, y_min=0, y_max=12,
        segments=[PlotSegment(lambda x: x + 2, 0.5, 5.5)],
        points=[PlotPoint(3, 5, "open"), PlotPoint(3, 10, "filled")],
        notice="lim x→3 f(x)=5 while f(3)=10.",
    )
    case_c = GraphSpec(
        graph_id="limit_case_c",
        title="Case C: limit exists, f(c) undefined",
        x_min=0, x_max=6, y_min=0, y_max=10,
        segments=[PlotSegment(lambda x: x + 2, 0.5, 5.5)],
        points=[PlotPoint(3, 5, "open")],
        notice="f(3) is undefined; limit is 5.",
    )
    case_d = GraphSpec(
        graph_id="limit_case_d",
        title="Case D: limit DNE, f(c) defined",
        x_min=0, x_max=6, y_min=-3, y_max=7,
        segments=[
            PlotSegment(lambda x: x - 4, 0.5, 2.92, color=LEFT_COLOR, width=3),
            PlotSegment(lambda x: x + 1, 3.08, 5.5, color=RIGHT_COLOR, width=3),
        ],
        points=[
            PlotPoint(3, -1, "open", color=LEFT_COLOR),
            PlotPoint(3, 4, "open", color=RIGHT_COLOR),
            PlotPoint(3, 0, "filled", "f(3)=0"),
        ],
        notice="L⁻ → −1, L⁺ → 4; two-sided limit DNE.",
    )
    for spec, key in (
        (case_a, "limit_case_a"),
        (case_b, "limit_case_b"),
        (case_c, "limit_case_c"),
        (case_d, "limit_case_d"),
    ):
        paths[key] = write_graph(spec)
        paths[f"{key}_thumb"] = write_graph(spec, variant="thumb")
        paths[f"{key}_gallery"] = write_graph(spec, variant="gallery")

    removable_hole = GraphSpec(
        graph_id="removable_hole",
        title="Removable discontinuity",
        x_min=0, x_max=5, y_min=0, y_max=6,
        segments=[PlotSegment(lambda x: x + 1, 0.5, 1.95),
                  PlotSegment(lambda x: x + 1, 2.05, 4.5)],
        points=[PlotPoint(2, 3, "open", "lim=3")],
        notice="A single point can be removed without changing the limit.",
    )
    jump_at_3 = GraphSpec(
        graph_id="jump_at_3",
        title="Jump discontinuity at x = 3",
        x_min=0, x_max=6, y_min=-3, y_max=7,
        segments=[
            PlotSegment(lambda x: x - 4, 0.5, 2.92, color=LEFT_COLOR, width=3),
            PlotSegment(lambda x: x + 1, 3.08, 5.5, color=RIGHT_COLOR, width=3),
        ],
        points=[
            PlotPoint(3, -1, "open", "L⁻→−1", color=LEFT_COLOR),
            PlotPoint(3, 4, "open", "L⁺→4", color=RIGHT_COLOR),
            PlotPoint(3, 0, "filled", "f(3)=0"),
        ],
        notice="lim x→3⁻ f(x)=−1, lim x→3⁺ f(x)=4 → two-sided limit DNE.",
    )
    infinite_limit_13 = GraphSpec(
        graph_id="infinite_limit_13",
        title="Infinite behavior near x = 0",
        x_min=-2, x_max=2, y_min=-4, y_max=4,
        segments=[
            PlotSegment(lambda x: 1 / x, -1.9, -0.15, color=LEFT_COLOR),
            PlotSegment(lambda x: 1 / x, 0.15, 1.9, color=RIGHT_COLOR),
        ],
        v_asymptotes=[0],
        notice="|y| grows without bound as x→0⁺ or x→0⁻.",
    )
    for spec, key in (
        (removable_hole, "removable_hole"),
        (jump_at_3, "jump_at_3"),
        (infinite_limit_13, "infinite_limit_13"),
    ):
        paths[key] = write_graph(spec)
        paths[f"{key}_gallery"] = write_graph(spec, variant="gallery")

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

    # Endpoint / one-sided domain: f(x)=sqrt(x) on [0,4]
    paths["endpoint_sqrt_13"] = write_graph(GraphSpec(
        graph_id="endpoint_sqrt_13",
        title="Endpoint: domain starts at x = 0",
        x_min=-0.5, x_max=4.5, y_min=-0.5, y_max=3.5,
        segments=[PlotSegment(lambda x: math.sqrt(x), 0, 4.2, color=PURPLE)],
        points=[PlotPoint(0, 0, "filled", "f(0)=0")],
        notice="Only a right-hand approach exists at x=0; lim x→0⁻ f(x) is undefined on this domain.",
    ))

    # 1.5 packet #7: three-branch piecewise g(x)
    def g_sqrt(x: float) -> float:
        return math.sqrt(5 - x)

    def g_quad(x: float) -> float:
        return x * x - 5

    def g_lin(x: float) -> float:
        return x - 3

    g15_segments = [
        PlotSegment(g_sqrt, -6.4, -4.04, color=LEFT_COLOR, width=3.2),
        PlotSegment(g_quad, -3.96, 1.96, color=PURPLE, width=3.2),
        PlotSegment(g_lin, 2.04, 4.3, color=RIGHT_COLOR, width=3.2),
    ]
    g15_breakpoints = [-4.0, 2.0]
    g15_branch_labels = [
        PlotLabel(-5.8, 2.2, "sqrt(5-x)", LEFT_COLOR),
        PlotLabel(-0.6, -4.2, "x^2 - 5", PURPLE, anchor="middle"),
        PlotLabel(3.2, 0.2, "x - 3", RIGHT_COLOR),
    ]

    paths["piecewise_g_15"] = write_graph(GraphSpec(
        graph_id="piecewise_g_15",
        title="g(x) — three branches (practice #7)",
        x_min=-6.5, x_max=4.5, y_min=-3, y_max=12,
        segments=g15_segments,
        breakpoints=g15_breakpoints,
        labels=g15_branch_labels,
        points=[
            PlotPoint(-4, 3, "open", "L- = 3", color=LEFT_COLOR),
            PlotPoint(-4, 11, "filled", "g(-4) = 11"),
            PlotPoint(2, -1, "filled", "g(2) = -1", color=RIGHT_COLOR),
        ],
        notice="Jump at x = -4; continuous at x = 2 (both sides approach -1).",
    ))

    paths["piecewise_g_15_zoom_neg4"] = write_graph(GraphSpec(
        graph_id="piecewise_g_15_zoom_neg4",
        title="Zoom at x = -4 (jump)",
        x_min=-6.2, x_max=-1.8, y_min=-1, y_max=12,
        segments=[
            PlotSegment(g_sqrt, -6.1, -4.04, color=LEFT_COLOR, width=3.5),
            PlotSegment(g_quad, -3.96, -1.9, color=PURPLE, width=3.5),
        ],
        breakpoints=[-4.0],
        points=[
            PlotPoint(-4, 3, "open", "L- = 3", color=LEFT_COLOR),
            PlotPoint(-4, 11, "filled", "g(-4) = 11"),
        ],
        labels=[
            PlotLabel(-5.5, 2.5, "sqrt branch", LEFT_COLOR),
            PlotLabel(-2.2, 8.5, "quadratic branch", PURPLE),
        ],
        notice="L- != g(-4): the two-sided limit at -4 does not exist.",
    ))

    paths["piecewise_g_15_zoom_2"] = write_graph(GraphSpec(
        graph_id="piecewise_g_15_zoom_2",
        title="Zoom at x = 2 (branches agree)",
        x_min=-1.5, x_max=4.2, y_min=-3.5, y_max=2,
        segments=[
            PlotSegment(g_quad, -1.45, 1.96, color=PURPLE, width=3.5),
            PlotSegment(g_lin, 2.04, 4.1, color=RIGHT_COLOR, width=3.5),
        ],
        breakpoints=[2.0],
        points=[PlotPoint(2, -1, "filled", "limit = g(2) = -1", color=GREEN)],
        labels=[
            PlotLabel(-0.8, -4.5, "x^2 - 5", PURPLE, anchor="middle"),
            PlotLabel(3.3, -2.6, "x - 3", RIGHT_COLOR),
        ],
        notice="L- = L+ = -1, so the two-sided limit exists and equals g(2).",
    ))

    # 1.5 notes example: piecewise at x = -5 (left sqrt, right rational)
    def f_left_15(x: float) -> float:
        return math.sqrt(11 - x)

    def f_right_15(x: float) -> float:
        return (x + 3) / (5 - x * x)

    paths["piecewise_f_minus5_15"] = write_graph(GraphSpec(
        graph_id="piecewise_f_minus5_15",
        title="f(x) near x = -5 (notes example)",
        x_min=-7.2, x_max=-3.2, y_min=-0.5, y_max=4.8,
        segments=[
            PlotSegment(f_left_15, -7.0, -5.04, color=LEFT_COLOR, width=3.2),
            PlotSegment(f_right_15, -4.96, -2.55, color=RIGHT_COLOR, width=3.2),
        ],
        breakpoints=[-5.0],
        labels=[
            PlotLabel(-6.4, 2.2, "sqrt(11-x)", LEFT_COLOR),
            PlotLabel(-3.6, 0.55, "(x+3)/(5-x^2)", RIGHT_COLOR),
        ],
        points=[
            PlotPoint(-5, 4, "open", "L- = 4", color=LEFT_COLOR),
            PlotPoint(-5, 0.1, "open", "L+ = 0.1", color=RIGHT_COLOR),
        ],
        notice="Compare one-sided limits before claiming a two-sided limit at -5.",
    ))

    # Practice #8 style: jump at x = -5
    def h_left(x: float) -> float:
        return -abs(x)

    def h_mid(x: float) -> float:
        return 20 - x * x

    paths["piecewise_h_jump_neg5_15"] = write_graph(GraphSpec(
        graph_id="piecewise_h_jump_neg5_15",
        title="h(x) — jump at x = -5 (practice #8)",
        x_min=-8, x_max=-2, y_min=-8, y_max=6,
        segments=[
            PlotSegment(h_left, -7.8, -5.04, color=LEFT_COLOR, width=3.2),
            PlotSegment(h_mid, -4.96, -2.1, color=RIGHT_COLOR, width=3.2),
        ],
        breakpoints=[-5.0],
        labels=[
            PlotLabel(-7.0, -6.5, "-|x|", LEFT_COLOR),
            PlotLabel(-3.5, 3.5, "20 - x^2", RIGHT_COLOR),
        ],
        points=[PlotPoint(-5, -5, "filled", "h(-5) = -5", color=PURPLE)],
        notice="For x -> -5+, follow the quadratic branch; limit is -5.",
    ))

    paths["piecewise_h_jump_neg5_15_gallery"] = write_graph(
        GraphSpec(
            graph_id="piecewise_h_jump_neg5_15",
            title="Jump at x = -5",
            x_min=-8, x_max=-2, y_min=-8, y_max=6,
            segments=[
                PlotSegment(h_left, -7.8, -5.04, color=LEFT_COLOR, width=3),
                PlotSegment(h_mid, -4.96, -2.1, color=RIGHT_COLOR, width=3),
            ],
            breakpoints=[-5.0],
            points=[
                PlotPoint(-5, -5, "filled", "", color=LEFT_COLOR),
                PlotPoint(-5, -5, "open", "", color=RIGHT_COLOR),
            ],
            notice="L- = -5, L+ = -5 at the seam (check inequality at endpoint).",
        ),
        variant="gallery",
    )

    # Teaching strip: continuous vs jump (simple two-line models)
    paths["piecewise_model_continuous_15"] = write_graph(GraphSpec(
        graph_id="piecewise_model_continuous_15",
        title="Continuous at the breakpoint",
        x_min=-1, x_max=4, y_min=-1, y_max=5,
        segments=[
            PlotSegment(lambda x: x + 1, -0.8, 1.96, color=LEFT_COLOR, width=3),
            PlotSegment(lambda x: -x + 5, 2.04, 3.8, color=RIGHT_COLOR, width=3),
        ],
        breakpoints=[2.0],
        points=[PlotPoint(2, 3, "filled", "L = f(2) = 3", color=GREEN)],
        notice="Both branches meet at the same height.",
    ))

    paths["piecewise_model_jump_15"] = write_graph(GraphSpec(
        graph_id="piecewise_model_jump_15",
        title="Jump at the breakpoint",
        x_min=-1, x_max=4, y_min=-1, y_max=5,
        segments=[
            PlotSegment(lambda x: x + 1, -0.8, 1.96, color=LEFT_COLOR, width=3),
            PlotSegment(lambda x: -x + 7, 2.04, 3.8, color=RIGHT_COLOR, width=3),
        ],
        breakpoints=[2.0],
        points=[
            PlotPoint(2, 3, "open", "L- = 3", color=LEFT_COLOR),
            PlotPoint(2, 5, "filled", "f(2) = 5", color=PURPLE),
        ],
        notice="L- != f(2); two-sided limit may still exist if L+ matches L-.",
    ))

    paths["piecewise_model_continuous_15_gallery"] = write_graph(
        GraphSpec(
            graph_id="piecewise_model_continuous_15",
            title="Continuous seam",
            x_min=-1, x_max=4, y_min=-1, y_max=5,
            segments=[
                PlotSegment(lambda x: x + 1, -0.8, 1.96, color=LEFT_COLOR, width=2.8),
                PlotSegment(lambda x: -x + 5, 2.04, 3.8, color=RIGHT_COLOR, width=2.8),
            ],
            breakpoints=[2.0],
            points=[PlotPoint(2, 3, "filled", "", color=GREEN)],
            notice="L- = L+ = f(c).",
        ),
        variant="gallery",
    )
    # 1.6 removable hole: sin(x)/x → 1
    paths["sin_over_x_16"] = write_graph(GraphSpec(
        graph_id="sin_over_x_16",
        title="y = sin(x)/x (x ≠ 0)",
        x_min=-6.5, x_max=6.5, y_min=-0.5, y_max=1.35,
        segments=[PlotSegment(lambda x: math.sin(x) / x, -6.2, -0.12, color=LEFT_COLOR, width=3),
                  PlotSegment(lambda x: math.sin(x) / x, 0.12, 6.2, color=RIGHT_COLOR, width=3)],
        points=[PlotPoint(0, 1, "open", "limit = 1", color=GREEN)],
        notice="Approach height 1 from both sides; f(0) is undefined.",
    ))

    paths["piecewise_model_jump_15_gallery"] = write_graph(
        GraphSpec(
            graph_id="piecewise_model_jump_15",
            title="Jump seam",
            x_min=-1, x_max=4, y_min=-1, y_max=5,
            segments=[
                PlotSegment(lambda x: x + 1, -0.8, 1.96, color=LEFT_COLOR, width=2.8),
                PlotSegment(lambda x: -x + 7, 2.04, 3.8, color=RIGHT_COLOR, width=2.8),
            ],
            breakpoints=[2.0],
            points=[
                PlotPoint(2, 3, "open", "", color=LEFT_COLOR),
                PlotPoint(2, 5, "filled", "", color=PURPLE),
            ],
            notice="L- != f(c); compare sides.",
        ),
        variant="gallery",
    )
    paths["piecewise_g_15_zoom_neg4_gallery"] = write_graph(
        GraphSpec(
            graph_id="piecewise_g_15_zoom_neg4",
            title="Jump at -4",
            x_min=-6.2, x_max=-1.8, y_min=-1, y_max=12,
            segments=[
                PlotSegment(g_sqrt, -6.1, -4.04, color=LEFT_COLOR, width=3),
                PlotSegment(g_quad, -3.96, -1.9, color=PURPLE, width=3),
            ],
            breakpoints=[-4.0],
            points=[
                PlotPoint(-4, 3, "open", "", color=LEFT_COLOR),
                PlotPoint(-4, 11, "filled", ""),
            ],
            notice="L- = 3, g(-4) = 11.",
        ),
        variant="gallery",
    )
    paths["piecewise_g_15_zoom_2_gallery"] = write_graph(
        GraphSpec(
            graph_id="piecewise_g_15_zoom_2",
            title="Agree at 2",
            x_min=-1.5, x_max=4.2, y_min=-3.5, y_max=2,
            segments=[
                PlotSegment(g_quad, -1.45, 1.96, color=PURPLE, width=3),
                PlotSegment(g_lin, 2.04, 4.1, color=RIGHT_COLOR, width=3),
            ],
            breakpoints=[2.0],
            points=[PlotPoint(2, -1, "filled", "", color=GREEN)],
            notice="L- = L+ = -1.",
        ),
        variant="gallery",
    )

    return paths


if __name__ == "__main__":
    built = build_all_graphs()
    print(f"Wrote {len(built)} graphs")
