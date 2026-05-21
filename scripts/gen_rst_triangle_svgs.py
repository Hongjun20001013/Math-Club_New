#!/usr/bin/env python3
"""
Emit right-triangle RST diagrams (pure SVG) for Unit 4.3.

Layout: S top-left (right angle), R bottom-left, T top-right; RS vertical, ST horizontal.

Run: python3 scripts/gen_rst_triangle_svgs.py
"""

from __future__ import annotations

import math
from pathlib import Path


def _sqrt(x: float) -> float:
    return math.sqrt(x)


def build_svg(rs: int, st: int, tr: int) -> str:
    # Larger canvas for readability; short-leg triangles use almost full width.
    w, h = 520.0, 480.0
    margin = 58.0
    maxleg = max(rs, st)
    vlen = (h - 2 * margin) * (rs / maxleg) * 0.94
    hlen = (w - 2 * margin) * (st / maxleg) * 0.94
    sx = margin + (w - 2 * margin - hlen) / 2
    sy = margin + (h - 2 * margin - vlen) / 2
    rx, ry = sx, sy + vlen
    tx, ty = sx + hlen, sy
    tick = min(vlen, hlen) * 0.1
    ax, ay = sx, sy + tick
    bx, by = sx + tick, sy + tick
    cx, cy = sx + tick, sy
    path_tri = f"M {rx:.1f},{ry:.1f} L {sx:.1f},{sy:.1f} L {tx:.1f},{ty:.1f} Z"

    # Edge-midpoint labels, offset along outward normals (clear of the sides).
    d_rs = max(22.0, min(vlen, hlen) * 0.09)  # RS: to the left of vertical leg
    rs_x = sx - d_rs
    rs_y = (sy + ry) / 2

    d_st = max(20.0, min(vlen, hlen) * 0.085)  # ST: above top horizontal leg (smaller y)
    st_x = (sx + tx) / 2
    st_y = sy - d_st

    mx, my = (rx + tx) / 2, (ry + ty) / 2
    gx = (sx + rx + tx) / 3
    gy = (sy + ry + ty) / 3
    vx, vy = mx - gx, my - gy
    n = _sqrt(vx * vx + vy * vy) or 1.0
    d_hyp = max(18.0, min(vlen, hlen) * 0.075)
    htx = mx + (vx / n) * d_hyp
    hty = my + (vy / n) * d_hyp

    fs_num = 21 if max(rs, st) <= 48 else 19
    fs_vert = 24 if max(rs, st) <= 48 else 23

    grid = """
  <defs>
    <pattern id="npDotGrid" width="9" height="9" patternUnits="userSpaceOnUse">
      <circle cx="0.9" cy="0.9" r="0.55" fill="#c8c2dc" opacity="0.45"/>
    </pattern>
  </defs>
  <rect x="0" y="0" width="100%" height="100%" fill="url(#npDotGrid)"/>
"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">
{grid}
  <path d="{path_tri}" fill="rgba(255,255,255,0.38)" stroke="#111" stroke-width="2.75" stroke-linejoin="miter"/>
  <polyline points="{sx:.1f},{sy:.1f} {ax:.1f},{ay:.1f} {bx:.1f},{by:.1f} {cx:.1f},{cy:.1f}"
    fill="none" stroke="#111" stroke-width="1.85"/>
  <text x="{rs_x:.1f}" y="{rs_y:.1f}" text-anchor="end" dominant-baseline="middle"
    font-family="Georgia, Times New Roman, serif" font-size="{fs_num}" font-weight="500" fill="#111">{rs}</text>
  <text x="{st_x:.1f}" y="{st_y:.1f}" text-anchor="middle" dominant-baseline="middle"
    font-family="Georgia, Times New Roman, serif" font-size="{fs_num}" font-weight="500" fill="#111">{st}</text>
  <text x="{htx:.1f}" y="{hty:.1f}" text-anchor="middle" dominant-baseline="middle"
    font-family="Georgia, Times New Roman, serif" font-size="{fs_num}" font-weight="500" fill="#111">{tr}</text>
  <text x="{rx - 34:.1f}" y="{ry + 14:.1f}" text-anchor="end"
    font-family="Georgia, Times New Roman, serif" font-size="{fs_vert}" font-style="italic" fill="#111">R</text>
  <text x="{sx - 28:.1f}" y="{sy - 12:.1f}" text-anchor="end"
    font-family="Georgia, Times New Roman, serif" font-size="{fs_vert}" font-style="italic" fill="#111">S</text>
  <text x="{tx + 28:.1f}" y="{ty + 14:.1f}" text-anchor="start"
    font-family="Georgia, Times New Roman, serif" font-size="{fs_vert}" font-style="italic" fill="#111">T</text>
</svg>
"""


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = root / "static" / "unit4"
    out.mkdir(parents=True, exist_ok=True)
    pairs = (
        ("rst_tri_440_384_584.svg", 440, 384, 584),
        ("rst_tri_20_48_52.svg", 20, 48, 52),
        ("rst_tri_12_5_13.svg", 12, 5, 13),
    )
    for name, a, b, c in pairs:
        p = out / name
        p.write_text(build_svg(a, b, c), encoding="utf-8")
        print("Wrote", p)


if __name__ == "__main__":
    main()
