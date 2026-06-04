"""
Convert a subset of TikZ/pgfplots used in SAT LaTeX banks into inline SVG for the web.
MathJax does not render TikZ; this keeps figures readable without a LaTeX server.
"""

from __future__ import annotations

import html
import math
import re
from typing import List, Optional, Tuple

_svg_marker_seq = 0

# Novel Prep–style stroke for graphs (higher contrast on light plot field)
_STROKE = "#4f2fd4"
_GRID = "rgba(79, 47, 212, 0.14)"
_AXIS = "#352875"
_PLOT_BG = "#f7f5ff"
_TICK = "#2d2657"


def _escape(s: str) -> str:
    return html.escape(s, quote=True)


def _match_brackets(s: str, open_ch: str, close_ch: str, start: int) -> Optional[Tuple[str, int]]:
    """Return (inner, index_after_close) for balanced bracket pair starting at start (position of open_ch)."""
    if start >= len(s) or s[start] != open_ch:
        return None
    depth = 0
    i = start
    inner_start = start + 1
    while i < len(s):
        if s[i] == open_ch:
            depth += 1
        elif s[i] == close_ch:
            depth -= 1
            if depth == 0:
                return s[inner_start:i], i + 1
        i += 1
    return None


def _parse_axis_options(opt: str) -> dict:
    """Best-effort key=value extraction from pgfplots axis[...] (handles nested braces in xtick={...})."""
    out: dict = {}
    # Pull simple numeric / label keys first
    for key in ("xmin", "xmax", "ymin", "ymax"):
        m = re.search(rf"\b{key}\s*=\s*([-+]?[\d.]+)", opt)
        if m:
            out[key] = float(m.group(1))
    # xlabel / ylabel may be {$x$} or plain
    for key in ("xlabel", "ylabel"):
        m = re.search(r"\b" + key + r"\s*=\s*\{([^}]*)\}", opt)
        if m:
            out[key] = m.group(1).strip()
        else:
            m2 = re.search(rf"\b{key}\s*=\s*([^,\n]+)", opt)
            if m2:
                out[key] = m2.group(1).strip().strip("{}")
    out["enlargelimits"] = not bool(re.search(r"\benlargelimits\s*=\s*false", opt))
    return out


def _fmt_tick_num(v: float) -> str:
    if abs(v - round(v)) < 1e-5:
        return str(int(round(v)))
    return f"{v:g}"


def _expand_tick_inner(inner: str) -> List[float]:
    """Parse pgfplots tick list: {0,5,10} or {0,2,...,20} (comma on both sides of ...)."""
    compact = re.sub(r"\s+", "", inner.strip())
    # PGFPlots: first,second,...,last — note the comma before and after "..."
    m = re.match(
        r"^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?),\.\.\.,(-?\d+(?:\.\d+)?)$",
        compact,
    )
    if not m:
        # Older / compact: 0,2...20 without comma after second value (rare)
        m = re.match(
            r"^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)\.\.\.(-?\d+(?:\.\d+)?)$",
            compact,
        )
    if m:
        a, b, c = float(m.group(1)), float(m.group(2)), float(m.group(3))
        step = b - a
        vals: List[float] = []
        if abs(step) < 1e-12:
            return [a]
        if step > 0:
            x = a
            while x <= c + 1e-6:
                vals.append(x)
                x += step
        else:
            x = a
            while x >= c - 1e-6:
                vals.append(x)
                x += step
        return vals
    parts = [p for p in inner.split(",") if p.strip() and p.strip() != "..."]
    return [float(p) for p in parts]


def _auto_ticks(lo: float, hi: float, max_ticks: int = 11) -> List[float]:
    """Evenly spaced ticks when pgfplots omits xtick/ytick."""
    if hi <= lo:
        return [lo]
    span = hi - lo
    rough = max(1e-9, span / max(2, max_ticks - 1))
    mag = 10 ** math.floor(math.log10(rough))
    err = rough / mag
    if err >= 5:
        step = 5 * mag
    elif err >= 2:
        step = 2 * mag
    else:
        step = mag
    vals: List[float] = []
    x = math.ceil(lo / step - 1e-9) * step
    guard = 0
    while x <= hi + 1e-6 * max(abs(hi), 1) and guard < 96:
        vals.append(round(x, 8))
        x += step
        guard += 1
    return vals or [lo, hi]


def _axis_tick_list(opt: str, key: str) -> Optional[List[float]]:
    m = re.search(r"\b" + key + r"\s*=\s*\{([^}]*)\}", opt)
    if not m:
        return None
    try:
        return _expand_tick_inner(m.group(1))
    except ValueError:
        return None


def _extract_axis_inner(tikz_block: str) -> Optional[Tuple[str, str]]:
    """Return (axis_options_str, inner_after_begin_axis) for first axis env."""
    m = re.search(r"\\begin\{axis\}", tikz_block)
    if not m:
        return None
    i = m.end()
    while i < len(tikz_block) and tikz_block[i].isspace():
        i += 1
    if i < len(tikz_block) and tikz_block[i] == "[":
        inner_opt = _match_brackets(tikz_block, "[", "]", i)
        if not inner_opt:
            return None
        opt_str, j = inner_opt
        inner = tikz_block[j:]
    else:
        opt_str = ""
        inner = tikz_block[i:]
    end = inner.find(r"\end{axis}")
    if end == -1:
        return None
    return opt_str, inner[:end]


def _parse_coord_pairs(blob: str) -> List[Tuple[float, float]]:
    pts: List[Tuple[float, float]] = []
    for m in re.finditer(r"\(\s*([+-]?[\d.]+)\s*,\s*([+-]?[\d.]+)\s*\)", blob):
        pts.append((float(m.group(1)), float(m.group(2))))
    return pts


def _safe_linear_y(expr: str, x: float) -> float:
    """
    Evaluate y for expressions like '-0.25*x + 2', '10 - 0.5*x' (linear in x only).
    """
    e = expr.strip().strip("{}").replace(" ", "")
    e = e.replace("x", str(x))
    if not re.fullmatch(r"[0-9+\-*/.()]+", e):
        raise ValueError("unsupported plot expression")
    return float(eval(e, {"__builtins__": {}}, {}))


def _extract_addplots(
    axis_inner: str, axis_options: str = ""
) -> Tuple[List[Tuple[str, object]], List[Tuple[float, float]]]:
    """
    Return (series, scatter) where series entries are ("line", pts) or ("expr", expr_str).
    Coordinate \\addplots with `only marks` (often in axis options via every axis plot/.append style)
    become scatter points.
    """
    series: List[Tuple[str, object]] = []
    scatter: List[Tuple[float, float]] = []
    opt_blob = f"{axis_options}\n{axis_inner}"
    only_marks = bool(re.search(r"only\s+marks", opt_blob, re.I))

    for m in re.finditer(r"\\filldraw\s*\[[^\]]*\]\s*\(([^)]+)\)\s*circle", axis_inner):
        inner = m.group(1)
        pm = re.match(r"\s*([+-]?[\d.]+)\s*,\s*([+-]?[\d.]+)\s*", inner)
        if pm:
            scatter.append((float(pm.group(1)), float(pm.group(2))))

    pos = 0
    while True:
        i = axis_inner.find(r"\addplot", pos)
        if i == -1:
            break
        rest = axis_inner[i:]
        semi = rest.find(";")
        if semi == -1:
            break
        one = rest[: semi + 1]
        if "coordinates" in one:
            cm = re.search(r"coordinates\s*\{", one)
            if cm:
                brace_pos = i + cm.start() + len(cm.group(0)) - 1
                br = _match_brackets(axis_inner, "{", "}", brace_pos)
                if br:
                    body, _ = br
                    pts = _parse_coord_pairs(body)
                    if pts:
                        if only_marks:
                            scatter.extend(pts)
                        else:
                            series.append(("line", pts))
        else:
            m2 = re.search(r"\{([^{}]+)\}\s*;$", one)
            if m2:
                expr = m2.group(1).strip()
                if "x" in expr:
                    series.append(("expr", expr))
        pos = i + len(one)

    return series, scatter


def _series_to_points(
    series: List[Tuple[str, object]],
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
) -> List[Tuple[str, List[Tuple[float, float]]]]:
    out: List[Tuple[str, List[Tuple[float, float]]]] = []
    for kind, payload in series:
        if kind == "line":
            out.append(("line", payload))  # type: ignore[arg-type]
        elif kind == "expr":
            expr = str(payload)
            try:
                y0 = _safe_linear_y(expr, xmin)
                y1 = _safe_linear_y(expr, xmax)
                out.append(("line", [(xmin, y0), (xmax, y1)]))
            except Exception:
                continue
    return out


def _data_bounds(
    lines: List[Tuple[str, List[Tuple[float, float]]]], scatter: List[Tuple[float, float]]
) -> Optional[Tuple[float, float, float, float]]:
    xs: List[float] = []
    ys: List[float] = []
    for _, pts in lines:
        for x, y in pts:
            xs.append(x)
            ys.append(y)
    for x, y in scatter:
        xs.append(x)
        ys.append(y)
    if not xs:
        return None
    return min(xs), max(xs), min(ys), max(ys)


def _svg_axes_plot(
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    lines: List[Tuple[str, List[Tuple[float, float]]]],
    scatter: List[Tuple[float, float]],
    xlabel: str = "",
    ylabel: str = "",
    width: int = 420,
    height: int = 420,
    xticks: Optional[List[float]] = None,
    yticks: Optional[List[float]] = None,
) -> str:
    global _svg_marker_seq
    _svg_marker_seq += 1
    mid = f"npM{_svg_marker_seq}"

    xtick_vals = list(xticks) if xticks else _auto_ticks(xmin, xmax)
    ytick_vals = list(yticks) if yticks else _auto_ticks(ymin, ymax)

    pad_l, pad_r, pad_t, pad_b = 44, 32, 36, 52
    if xtick_vals:
        pad_b = max(pad_b, 58)
    if ytick_vals:
        pad_l = max(pad_l, 58)
    w = width
    h = height
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b
    font = 'font-family="DM Sans,system-ui,sans-serif"'

    def tx(x: float) -> float:
        return pad_l + (x - xmin) / (xmax - xmin) * plot_w

    def ty(y: float) -> float:
        return pad_t + (ymax - y) / (ymax - ymin) * plot_h

    parts: List[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" class="stem-tikz-svg" role="img" aria-label="Coordinate plane figure">')
    parts.append(
        "<defs>"
        f'<marker id="{mid}" markerWidth="7" markerHeight="7" refX="6" refY="3.5" '
        'orient="auto" markerUnits="userSpaceOnUse">'
        f'<path d="M0,0 L7,3.5 L0,7 Z" fill="{_AXIS}"/>'
        "</marker>"
        "</defs>"
    )
    parts.append(f'<rect x="0" y="0" width="{w}" height="{h}" fill="none"/>')
    parts.append(
        f'<rect x="{pad_l:.2f}" y="{pad_t:.2f}" width="{plot_w:.2f}" height="{plot_h:.2f}" '
        f'rx="4" fill="{_PLOT_BG}" stroke="rgba(79,47,212,0.08)" stroke-width="1"/>'
    )

    for gx in xtick_vals:
        if gx < xmin - 1e-6 or gx > xmax + 1e-6:
            continue
        x_ = tx(gx)
        parts.append(
            f'<line x1="{x_:.2f}" y1="{pad_t:.2f}" x2="{x_:.2f}" y2="{h - pad_b:.2f}" stroke="{_GRID}" stroke-width="1"/>'
        )

    for gy in ytick_vals:
        if gy < ymin - 1e-6 or gy > ymax + 1e-6:
            continue
        y_ = ty(gy)
        parts.append(
            f'<line x1="{pad_l:.2f}" y1="{y_:.2f}" x2="{w - pad_r:.2f}" y2="{y_:.2f}" stroke="{_GRID}" stroke-width="1"/>'
        )

    y0 = ty(0) if ymin <= 0 <= ymax else ty(ymin)
    x0 = tx(0) if xmin <= 0 <= xmax else tx(xmin)
    show_x_axis = ymin <= 0 <= ymax
    show_y_axis = xmin <= 0 <= xmax

    if show_x_axis:
        parts.append(
            f'<line x1="{pad_l:.2f}" y1="{y0:.2f}" x2="{w - pad_r:.2f}" y2="{y0:.2f}" '
            f'stroke="{_AXIS}" stroke-width="2" stroke-linecap="square" marker-end="url(#{mid})"/>'
        )
    if show_y_axis:
        parts.append(
            f'<line x1="{x0:.2f}" y1="{h - pad_b:.2f}" x2="{x0:.2f}" y2="{pad_t:.2f}" '
            f'stroke="{_AXIS}" stroke-width="2" stroke-linecap="square" marker-end="url(#{mid})"/>'
        )

    if show_x_axis:
        tick_h = 5
        for gx in xtick_vals:
            if gx < xmin - 1e-6 or gx > xmax + 1e-6:
                continue
            x_ = tx(gx)
            parts.append(
                f'<line x1="{x_:.2f}" y1="{y0:.2f}" x2="{x_:.2f}" y2="{y0 + tick_h:.2f}" '
                f'stroke="{_TICK}" stroke-width="1.2"/>'
            )
    if show_y_axis:
        tick_w = 5
        for gy in ytick_vals:
            if gy < ymin - 1e-6 or gy > ymax + 1e-6:
                continue
            y_ = ty(gy)
            parts.append(
                f'<line x1="{x0 - tick_w:.2f}" y1="{y_:.2f}" x2="{x0:.2f}" y2="{y_:.2f}" '
                f'stroke="{_TICK}" stroke-width="1.2"/>'
            )

    if show_x_axis and show_y_axis:
        parts.append(
            f'<circle cx="{x0:.2f}" cy="{y0:.2f}" r="2.2" fill="{_AXIS}" '
            'stroke="#fff" stroke-width="1" opacity="0.95"/>'
        )

    for _, pts in lines:
        if len(pts) < 2:
            continue
        d = "M " + " L ".join(f"{tx(x):.2f},{ty(y):.2f}" for x, y in pts)
        parts.append(
            f'<path d="{d}" fill="none" stroke="{_STROKE}" stroke-width="2.6" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )

    for x, y in scatter:
        cx, cy = tx(x), ty(y)
        parts.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="5" fill="{_STROKE}" '
            'stroke="#ffffff" stroke-width="2"/>'
        )

    if show_x_axis:
        for gx in xtick_vals:
            if gx < xmin - 1e-6 or gx > xmax + 1e-6:
                continue
            x_ = tx(gx)
            parts.append(
                f'<text x="{x_:.2f}" y="{h - pad_b + 20:.2f}" text-anchor="middle" '
                f'font-size="11.5" font-weight="600" fill="{_TICK}" {font}>'
                f"{_escape(_fmt_tick_num(gx))}</text>"
            )
    if show_y_axis:
        for gy in ytick_vals:
            if gy < ymin - 1e-6 or gy > ymax + 1e-6:
                continue
            y_ = ty(gy)
            parts.append(
                f'<text x="{pad_l - 12:.2f}" y="{y_ + 4:.2f}" text-anchor="end" '
                f'font-size="11.5" font-weight="600" fill="{_TICK}" {font}>'
                f"{_escape(_fmt_tick_num(gy))}</text>"
            )

    if xlabel:
        parts.append(
            f'<text x="{(pad_l + w - pad_r) / 2:.2f}" y="{h - 10:.2f}" text-anchor="middle" '
            f'font-size="12.5" font-weight="600" fill="{_AXIS}" {font}>{_escape(xlabel)}</text>'
        )
    if ylabel:
        parts.append(
            f'<text x="{pad_l:.2f}" y="{pad_t - 8:.2f}" text-anchor="start" '
            f'font-size="12.5" font-weight="600" fill="{_AXIS}" {font}>{_escape(ylabel)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def _pgfplots_to_svg(tikz_block: str) -> Optional[str]:
    ext = _extract_axis_inner(tikz_block)
    if not ext:
        return None
    opt_str, inner = ext
    opts = _parse_axis_options(opt_str)
    xmin = opts.get("xmin", -10.0)
    xmax = opts.get("xmax", 10.0)
    ymin = opts.get("ymin", -10.0)
    ymax = opts.get("ymax", 10.0)
    xlabel = str(opts.get("xlabel", "")).replace("$", "")
    ylabel = str(opts.get("ylabel", "")).replace("$", "")
    xticks = _axis_tick_list(opt_str, "xtick")
    yticks = _axis_tick_list(opt_str, "ytick")

    raw_series, scatter = _extract_addplots(inner, opt_str)
    lines = _series_to_points(raw_series, xmin, xmax, ymin, ymax)

    b = _data_bounds(lines, scatter)
    if b and opts.get("enlargelimits", True):
        dx = (b[1] - b[0]) * 0.05 or 0.5
        dy = (b[3] - b[2]) * 0.05 or 0.5
        xmin = min(xmin, b[0] - dx)
        xmax = max(xmax, b[1] + dx)
        ymin = min(ymin, b[2] - dy)
        ymax = max(ymax, b[3] + dy)

    if not lines and not scatter:
        return None

    # Wider aspect for some stems (job A/B graph)
    w, hg = 420, 420
    if xmax <= 22 and ymax <= 12 and (xmax - xmin) >= (ymax - ymin):
        w, hg = 480, 300

    return _svg_axes_plot(
        xmin,
        xmax,
        ymin,
        ymax,
        lines,
        scatter,
        xlabel=xlabel,
        ylabel=ylabel,
        width=w,
        height=hg,
        xticks=xticks,
        yticks=yticks,
    )


def _parse_tikz_thick_polyline_body(body: str) -> List[Tuple[float, float]]:
    """Parse ``(x,y)--(x,y)--...`` or trailing ``--cycle`` inside ``\\draw[thick] ... ;``."""
    parts = re.split(r"\s*--\s*", body.strip())
    pts: List[Tuple[float, float]] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if p == "cycle":
            if pts:
                pts.append(pts[0])
            break
        m = re.match(r"^\(([-\d.]+),([-\d.]+)\)$", p)
        if m:
            pts.append((float(m.group(1)), float(m.group(2))))
    return pts


def _placement_prism_wireframe_svg(tikz_block: str) -> Optional[str]:
    """
    Wireframe diagrams without a coordinate grid (e.g. Q63 rectangular prism in ``Placement_Test.tex``).
    """
    if r"\draw[step=" in tikz_block or r"\draw[thick,->]" in tikz_block:
        return None
    if r"\begin{axis}" in tikz_block:
        return None
    if "grid" in tikz_block:
        return None
    stmts = re.findall(r"\\draw\[thick\]\s*([^;]+);", tikz_block)
    if len(stmts) < 3:
        return None
    polylines: List[List[Tuple[float, float]]] = []
    for st in stmts:
        pts = _parse_tikz_thick_polyline_body(st)
        if len(pts) >= 2:
            polylines.append(pts)
    if len(polylines) < 3:
        return None

    xs = [p[0] for pl in polylines for p in pl]
    ys = [p[1] for pl in polylines for p in pl]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    dx = xmax - xmin or 1.0
    dy = ymax - ymin or 1.0
    w, h = 260, 200
    pad = 28.0

    def tx(x: float) -> float:
        return pad + (x - xmin) / dx * (w - 2 * pad)

    def ty(y: float) -> float:
        return pad + (ymax - y) / dy * (h - 2 * pad)

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        'class="stem-tikz-svg stem-tikz-svg--prism" role="img" aria-label="3D figure">'
    )
    for pl in polylines:
        d = "M " + " L ".join(f"{tx(px):.2f},{ty(py):.2f}" for px, py in pl)
        parts.append(
            f'<path d="{d}" fill="none" stroke="{_AXIS}" stroke-width="2.2" '
            'stroke-linejoin="round" stroke-linecap="round"/>'
        )

    for nm in re.finditer(
        r"\\node\[(below|left|right|above)\]\s*at\s*\(([-\d.]+),([-\d.]+)\)\s*\{\$([^$]*)\$\}",
        tikz_block,
    ):
        pos, x, y, lab = nm.group(1), float(nm.group(2)), float(nm.group(3)), nm.group(4).strip()
        cx, cy = tx(x), ty(y)
        anchor = "middle"
        dx_t, dy_t = 0.0, 0.0
        if pos == "below":
            dy_t = 16
            anchor = "middle"
        elif pos == "above":
            dy_t = -14
            anchor = "middle"
        elif pos == "left":
            dx_t = -10
            anchor = "end"
        elif pos == "right":
            dx_t = 10
            anchor = "start"
        parts.append(
            f'<text x="{cx + dx_t:.2f}" y="{cy + dy_t:.2f}" text-anchor="{anchor}" '
            f'font-size="15" font-weight="700" fill="{_STROKE}">{_escape(lab)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def _placement_plot_y(inner: str, xv: float) -> float:
    """
    Evaluate y from Placement_Test ``plot (\\x,{...})`` inner expression.
    Only ``\\x``, numbers, + - * / ^, parentheses, and sqrt(...) are allowed.
    """
    s0 = inner.strip().strip("{}")
    s = s0.replace("\\x", "xv").replace("^", "**")
    s = re.sub(r"\bsqrt\s*\(", "math.sqrt(", s)
    probe = re.sub(r"xv", "0", s)
    probe = re.sub(r"math\.sqrt", "M", probe)
    if re.search(r"[^0-9eE.+\-*/()M,\s]", probe):
        raise ValueError("unsafe plot expression")
    return float(eval(compile(s, "<plot>", "eval"), {"__builtins__": {}}, {"xv": xv, "math": math}))


def _novel_prep_placement_graph_svg(tikz_block: str) -> Optional[str]:
    """
    Novel Prep ``Placement_Test.tex`` graph macros: ``[scale=0.33]``, grid (-4,-4)--(4,4),
    ``\\draw[thick,->]`` axes, then one of: ``very thick,->`` segment(s), ``plot``, or ``circle``,
    optional ``\\fill`` point (radical graphs).
    """
    gm = re.search(
        r"\\draw\[step=[^\]]+\]\s*\(([-\d.]+),([-\d.]+)\)\s*grid\s*\(([-\d.]+),([-\d.]+)\)",
        tikz_block,
    )
    if not gm:
        return None
    x0, y0, x1, y1 = map(float, gm.groups())
    w, h = 220, 220
    pad = 20.0
    span_x = x1 - x0
    span_y = y1 - y0

    def tx(x: float) -> float:
        return pad + (x - x0) / span_x * (w - 2 * pad)

    def ty(y: float) -> float:
        return pad + (y1 - y) / span_y * (h - 2 * pad)

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        'class="stem-tikz-svg stem-tikz-svg--choice" role="img" aria-label="Graph choice">'
    )
    for i in range(int(x0), int(x1) + 1):
        x_ = tx(float(i))
        parts.append(
            f'<line x1="{x_:.2f}" y1="{pad:.2f}" x2="{x_:.2f}" y2="{h - pad:.2f}" '
            f'stroke="{_GRID}" stroke-width="1"/>'
        )
    for j in range(int(y0), int(y1) + 1):
        y_ = ty(float(j))
        parts.append(
            f'<line x1="{pad:.2f}" y1="{y_:.2f}" x2="{w - pad:.2f}" y2="{y_:.2f}" '
            f'stroke="{_GRID}" stroke-width="1"/>'
        )
    parts.append(
        f'<line x1="{tx(x0):.2f}" y1="{ty(0):.2f}" x2="{tx(x1):.2f}" y2="{ty(0):.2f}" '
        'stroke="#333" stroke-width="1.2"/>'
    )
    parts.append(
        f'<line x1="{tx(0):.2f}" y1="{ty(y0):.2f}" x2="{tx(0):.2f}" y2="{ty(y1):.2f}" '
        'stroke="#333" stroke-width="1.2"/>'
    )
    parts.append(f'<text x="{w - pad + 2:.2f}" y="{ty(0) + 4:.2f}" font-size="10" fill="#333">x</text>')
    parts.append(f'<text x="{tx(0) + 4:.2f}" y="{pad - 4:.2f}" font-size="10" fill="#333">y</text>')
    for gi in range(int(x0), int(x1) + 1):
        gx_ = tx(float(gi))
        parts.append(
            f'<text x="{gx_:.2f}" y="{h - pad + 14:.2f}" text-anchor="middle" '
            f'font-size="9" fill="#43318f">{gi}</text>'
        )
    for gj in range(int(y0), int(y1) + 1):
        gy_ = ty(float(gj))
        parts.append(
            f'<text x="{pad - 6:.2f}" y="{gy_ + 3:.2f}" text-anchor="end" '
            f'font-size="9" fill="#43318f">{gj}</text>'
        )

    # ``plot`` curves (parabolas / radicals)
    pm = re.search(
        r"\\draw\[very thick[^\]]*domain=([-\d.]+):([-\d.]+)[^\]]*\][^\n]*?"
        r"plot\s*\(\\x,\{([^}]+)\}\)",
        tikz_block,
        flags=re.S,
    )
    if pm:
        dom_lo, dom_hi = float(pm.group(1)), float(pm.group(2))
        inner = pm.group(3)
        n = 140
        pts: List[Tuple[float, float]] = []
        for i in range(n + 1):
            xv = dom_lo + (dom_hi - dom_lo) * i / n
            try:
                yv = _placement_plot_y(inner, xv)
            except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
                continue
            if not math.isfinite(yv) or yv < y0 - 2 or yv > y1 + 2:
                continue
            pts.append((xv, yv))
        if len(pts) >= 2:
            d = "M " + " L ".join(f"{tx(px):.2f},{ty(py):.2f}" for px, py in pts)
            parts.append(
                f'<path d="{d}" fill="none" stroke="{_STROKE}" stroke-width="2.5" '
                'stroke-linecap="round" stroke-linejoin="round"/>'
            )

    # Piecewise ``very thick,->`` segments (lines and absolute-value graphs)
    for sm in re.finditer(
        r"\\draw\[very thick,->\]\s*\(([-\d.]+),([-\d.]+)\)\s*--\s*\(([-\d.]+),([-\d.]+)\)",
        tikz_block,
    ):
        lx0, ly0, lx1, ly1 = map(float, sm.groups())
        d = f"M {tx(lx0):.2f},{ty(ly0):.2f} L {tx(lx1):.2f},{ty(ly1):.2f}"
        parts.append(
            f'<path d="{d}" fill="none" stroke="{_STROKE}" stroke-width="2.5" stroke-linecap="round"/>'
        )

    # SAT mini graph choices often use a plain answer line:
    # ``\draw[thick] (x0,y0) -- (x1,y1);``. Keep axes/grid separate by ignoring
    # arrowed and step/grid draw commands.
    for sm in re.finditer(
        r"\\draw\[([^\]]*\bthick\b[^\]]*)\]\s*"
        r"\(([-\d.]+),([-\d.]+)\)\s*--\s*\(([-\d.]+),([-\d.]+)\)",
        tikz_block,
    ):
        opts = sm.group(1)
        if "->" in opts or "step" in opts or "very thick" in opts:
            continue
        lx0, ly0, lx1, ly1 = map(float, sm.groups()[1:])
        d = f"M {tx(lx0):.2f},{ty(ly0):.2f} L {tx(lx1):.2f},{ty(ly1):.2f}"
        parts.append(
            f'<path d="{d}" fill="none" stroke="{_STROKE}" stroke-width="2.5" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )

    # Circle graphs: ``\\draw[very thick] (cx,cy) circle (Rcm)``
    cm = re.search(
        r"\\draw\[very thick\]\s*\(([-\d.]+),([-\d.]+)\)\s+circle\s*\(([-\d.]+)cm\)",
        tikz_block,
    )
    if cm:
        cx, cy, r_cm = map(float, cm.groups())
        r_pix = max(2.0, (tx(cx + r_cm) - tx(cx)) if r_cm != 0 else tx(2) - tx(0))
        parts.append(
            f'<circle cx="{tx(cx):.2f}" cy="{ty(cy):.2f}" r="{r_pix:.2f}" fill="none" '
            f'stroke="{_STROKE}" stroke-width="2.4"/>'
        )

    # Radical graph anchor points
    for fm in re.finditer(
        r"\\fill\s*\(([-\d.]+),([-\d.]+)\)\s+circle\s*\(([-\d.]+)pt\)",
        tikz_block,
    ):
        fx, fy, _rpt = map(float, fm.groups())
        parts.append(
            f'<circle cx="{tx(fx):.2f}" cy="{ty(fy):.2f}" r="4" fill="{_STROKE}" '
            'stroke="#ffffff" stroke-width="1.5"/>'
        )

    parts.append("</svg>")
    return "".join(parts)


def _simple_tikz_grid_to_svg(tikz_block: str) -> Optional[str]:
    """Handles \draw grid + axes + one segment line (SAT multiple-choice mini graphs)."""
    gm = re.search(
        r"\\draw\[step=[^\]]+\]\s*\(([-\d.]+),([-\d.]+)\)\s*grid\s*\(([-\d.]+),([-\d.]+)\)",
        tikz_block,
    )
    if not gm:
        return None
    x0, y0, x1, y1 = map(float, gm.groups())
    lm = re.search(
        r"\\draw\[thick\]\s*\(([-\d.]+),([-\d.]+)\)\s*--\s*\(([-\d.]+),([-\d.]+)\)",
        tikz_block,
    )
    if not lm:
        return None
    lx0, ly0, lx1, ly1 = map(float, lm.groups())

    w, h = 220, 220
    pad = 20
    span_x = x1 - x0
    span_y = y1 - y0

    def tx(x: float) -> float:
        return pad + (x - x0) / span_x * (w - 2 * pad)

    def ty(y: float) -> float:
        return pad + (y1 - y) / span_y * (h - 2 * pad)

    parts: List[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" class="stem-tikz-svg stem-tikz-svg--choice" role="img" aria-label="Graph choice">')
    # grid
    g = int(max(abs(x0), abs(x1)))
    for i in range(int(x0), int(x1) + 1):
        x_ = tx(float(i))
        parts.append(
            f'<line x1="{x_:.2f}" y1="{pad:.2f}" x2="{x_:.2f}" y2="{h-pad:.2f}" stroke="{_GRID}" stroke-width="1"/>'
        )
    for j in range(int(y0), int(y1) + 1):
        y_ = ty(float(j))
        parts.append(
            f'<line x1="{pad:.2f}" y1="{y_:.2f}" x2="{w-pad:.2f}" y2="{y_:.2f}" stroke="{_GRID}" stroke-width="1"/>'
        )
    # axes
    parts.append(
        f'<line x1="{tx(x0):.2f}" y1="{ty(0):.2f}" x2="{tx(x1):.2f}" y2="{ty(0):.2f}" stroke="#333" stroke-width="1.2"/>'
    )
    parts.append(
        f'<line x1="{tx(0):.2f}" y1="{ty(y0):.2f}" x2="{tx(0):.2f}" y2="{ty(y1):.2f}" stroke="#333" stroke-width="1.2"/>'
    )
    parts.append(f'<text x="{w-pad+2:.2f}" y="{ty(0)+4:.2f}" font-size="10" fill="#333">x</text>')
    parts.append(f'<text x="{tx(0)+4:.2f}" y="{pad-4:.2f}" font-size="10" fill="#333">y</text>')
    for gi in range(int(x0), int(x1) + 1):
        gx_ = tx(float(gi))
        parts.append(
            f'<text x="{gx_:.2f}" y="{h - pad + 14:.2f}" text-anchor="middle" '
            f'font-size="9" fill="#43318f">{gi}</text>'
        )
    for gj in range(int(y0), int(y1) + 1):
        gy_ = ty(float(gj))
        parts.append(
            f'<text x="{pad - 6:.2f}" y="{gy_ + 3:.2f}" text-anchor="end" '
            f'font-size="9" fill="#43318f">{gj}</text>'
        )
    d = f"M {tx(lx0):.2f},{ty(ly0):.2f} L {tx(lx1):.2f},{ty(ly1):.2f}"
    parts.append(f'<path d="{d}" fill="none" stroke="{_STROKE}" stroke-width="2.5" stroke-linecap="round"/>')
    parts.append("</svg>")
    return "".join(parts)


def _node_anchor_offsets(anchor: str) -> Tuple[float, float]:
    """TikZ node anchor → rough label offset in SVG px (y-down)."""
    a = anchor.replace(" ", "").lower()
    dx, dy = 0.0, 0.0
    if "left" in a:
        dx -= 10.0
    if "right" in a:
        dx += 10.0
    if "above" in a:
        dy -= 10.0
    if "below" in a:
        dy += 10.0
    if a in ("left",):
        dx -= 8.0
    if a in ("right",):
        dx += 8.0
    if a in ("above",):
        dy -= 10.0
    if a in ("below",):
        dy += 10.0
    return dx, dy


def _strip_math_label(raw: str) -> str:
    s = raw.strip()
    if s.startswith("$") and s.endswith("$"):
        s = s[1:-1]
    return html.escape(s.strip(), quote=False)


def _coord_plane_grid_filldraw_svg(tikz_block: str) -> Optional[str]:
    """
    PGF/TikZ coordinate planes like:
      \\draw[very thin,...] (x0,y0) grid (x1,y1);
      \\draw[->,thick] (xa,0)--(xb,0) node[...]{$x$};
      \\draw[->,thick] (0,ya)--(0,yb) node[...]{$y$};
      \\filldraw[black] (px,py) circle (3pt) node[above left]{$A(-3,4)$};
    Default grid step is 1 unit (no ``step=`` in \\draw).
    """
    gm = re.search(
        r"\\draw\[[^\]]*\]\s*\(([-\d.]+),([-\d.]+)\)\s+grid\s+\(([-\d.]+),([-\d.]+)\)",
        tikz_block,
    )
    if not gm:
        return None
    gx0, gy0, gx1, gy1 = map(float, gm.groups())
    xmin, xmax = (gx0, gx1) if gx0 <= gx1 else (gx1, gx0)
    ymin, ymax = (gy0, gy1) if gy0 <= gy1 else (gy1, gy0)

    axis_iter = list(
        re.finditer(
            r"\\draw\[->,thick\]\s*\(([-\d.]+),([-\d.]+)\)\s*--\s*\(([-\d.]+),([-\d.]+)\)"
            r"(?:\s*node\[[^\]]*\]\s*\{[^}]*\})?\s*;?",
            tikz_block,
        )
    )
    if len(axis_iter) < 2:
        return None

    pt_iter = list(
        re.finditer(
            r"\\filldraw\[[^\]]*\]\s*\(([-\d.]+),([-\d.]+)\)\s+circle\s*\(([\d.]+)pt\)"
            r"\s*node\[([^\]]+)\]\s*\{([^}]*)\}",
            tikz_block,
        )
    )
    if len(pt_iter) < 2:
        return None

    pts: List[Tuple[float, float, str, str]] = []
    for m in pt_iter:
        px, py, _rpt, anchor, label_raw = (
            float(m.group(1)),
            float(m.group(2)),
            m.group(3),
            m.group(4),
            m.group(5),
        )
        pts.append((px, py, anchor, label_raw))

    w, h = 440, 360
    pad = 28.0

    def tx(x: float) -> float:
        return pad + (x - xmin) / (xmax - xmin) * (w - 2 * pad)

    def ty(y: float) -> float:
        return pad + (ymax - y) / (ymax - ymin) * (h - 2 * pad)

    unit_x = (w - 2 * pad) / (xmax - xmin)
    unit_y = (h - 2 * pad) / (ymax - ymin)
    pr = max(4.0, min(unit_x, unit_y) * 0.22)

    global _svg_marker_seq
    _svg_marker_seq += 1
    mid = f"npAxis{_svg_marker_seq}"

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        'class="stem-tikz-svg stem-tikz-svg--coord" role="img" aria-label="Coordinate plane">'
    )
    parts.append("<defs>")
    parts.append(
        f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#2d2657"/></marker>'
    )
    parts.append("</defs>")
    parts.append(f'<rect x="0" y="0" width="{w}" height="{h}" rx="10" fill="{_PLOT_BG}"/>')

    # Integer grid (implicit step 1)
    lo_x, hi_x = int(math.floor(xmin)), int(math.ceil(xmax))
    lo_y, hi_y = int(math.floor(ymin)), int(math.ceil(ymax))
    for xi in range(lo_x, hi_x + 1):
        x_ = tx(float(xi))
        parts.append(
            f'<line x1="{x_:.2f}" y1="{ty(ymax):.2f}" x2="{x_:.2f}" y2="{ty(ymin):.2f}" '
            f'stroke="{_GRID}" stroke-width="1"/>'
        )
    for yi in range(lo_y, hi_y + 1):
        y_ = ty(float(yi))
        parts.append(
            f'<line x1="{tx(xmin):.2f}" y1="{y_:.2f}" x2="{tx(xmax):.2f}" y2="{y_:.2f}" '
            f'stroke="{_GRID}" stroke-width="1"/>'
        )

    # Axes on top of grid
    for am in axis_iter:
        ax0, ay0, ax1, ay1 = map(float, am.groups())
        parts.append(
            f'<line x1="{tx(ax0):.2f}" y1="{ty(ay0):.2f}" x2="{tx(ax1):.2f}" y2="{ty(ay1):.2f}" '
            f'stroke="{_AXIS}" stroke-width="2.2" marker-end="url(#{mid})"/>'
        )

    # Axis labels x / y (from optional node on the matching segment)
    for am in axis_iter:
        seg = am.group(0)
        if "node" not in seg:
            continue
        nm = re.search(r"node\[([^\]]*)\]\s*\{\$([^$]*)\$\}", seg)
        if not nm:
            continue
        lab = nm.group(2).strip()
        ax0, ay0, ax1, ay1 = map(float, am.groups()[:4])
        if abs(ay1 - ay0) < 1e-9 and abs(ay0) < 1e-9:
            parts.append(
                f'<text x="{tx(ax1) + 6:.2f}" y="{ty(0) + 4:.2f}" font-size="13" '
                f'font-style="italic" fill="{_AXIS}">{html.escape(lab, quote=False)}</text>'
            )
        elif abs(ax1 - ax0) < 1e-9 and abs(ax0) < 1e-9:
            parts.append(
                f'<text x="{tx(0) + 4:.2f}" y="{ty(ay1) - 6:.2f}" font-size="13" '
                f'font-style="italic" fill="{_AXIS}">{html.escape(lab, quote=False)}</text>'
            )

    # Triangle fill when exactly three vertices (SAT “area of triangle” stems)
    if len(pts) == 3:
        poly = " ".join(f"{tx(px):.2f},{ty(py):.2f}" for px, py, _, _ in pts)
        parts.append(
            f'<polygon points="{poly}" fill="rgba(79, 47, 212, 0.12)" '
            f'stroke="{_STROKE}" stroke-width="2" stroke-linejoin="round"/>'
        )

    for px, py, anchor, label_raw in pts:
        cx, cy = tx(px), ty(py)
        parts.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{pr:.2f}" fill="#111827" '
            'stroke="#ffffff" stroke-width="1.2"/>'
        )
        dx, dy = _node_anchor_offsets(anchor)
        lx = cx + dx
        ly = cy + dy
        parts.append(
            f'<text x="{lx:.2f}" y="{ly:.2f}" font-size="12" font-weight="600" '
            f'fill="#1e1b4b" dominant-baseline="middle">{_strip_math_label(label_raw)}</text>'
        )

    # Tick numbers (integers in view)
    for gi in range(lo_x, hi_x + 1):
        if gi == 0:
            continue
        gx_ = tx(float(gi))
        parts.append(
            f'<text x="{gx_:.2f}" y="{h - pad + 16:.2f}" text-anchor="middle" '
            f'font-size="10" fill="{_TICK}">{gi}</text>'
        )
    for gj in range(lo_y, hi_y + 1):
        if gj == 0:
            continue
        gy_ = ty(float(gj))
        parts.append(
            f'<text x="{pad - 8:.2f}" y="{gy_ + 4:.2f}" text-anchor="end" '
            f'font-size="10" fill="{_TICK}">{gj}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def _tikz_block_to_figure_html(block: str) -> Optional[str]:
    block = block.strip()
    if r"\begin{axis}" in block:
        svg = _pgfplots_to_svg(block)
        if svg:
            return f'<div class="stem-figure-wrap">{svg}</div>'
    prism = _placement_prism_wireframe_svg(block)
    if prism:
        return f'<div class="stem-figure-wrap stem-figure-wrap--prism">{prism}</div>'
    np_svg = _novel_prep_placement_graph_svg(block)
    if np_svg:
        return f'<div class="stem-figure-wrap stem-figure-wrap--choice">{np_svg}</div>'
    coord_svg = _coord_plane_grid_filldraw_svg(block)
    if coord_svg:
        return f'<div class="stem-figure-wrap stem-figure-wrap--coord">{coord_svg}</div>'
    sg = _simple_tikz_grid_to_svg(block)
    if sg:
        return f'<div class="stem-figure-wrap stem-figure-wrap--choice">{sg}</div>'
    return None


def replace_tikz_with_svg_html(text: str) -> str:
    """Replace each \\begin{tikzpicture}...\\end{tikzpicture} with inline SVG when supported."""
    out: List[str] = []
    pos = 0
    while True:
        start = text.find(r"\begin{tikzpicture}", pos)
        if start == -1:
            out.append(text[pos:])
            break
        out.append(text[pos:start])
        end = text.find(r"\end{tikzpicture}", start)
        if end == -1:
            out.append(text[start:])
            break
        end += len(r"\end{tikzpicture}")
        block = text[start:end]
        fig = _tikz_block_to_figure_html(block)
        out.append(fig if fig else block)
        pos = end
    return "".join(out)
