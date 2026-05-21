#!/usr/bin/env python3
"""
Optional: schematic SVG figures (not pixel-identical to the PDF).

Sections **4.1–4.2** should use rasters from ``scripts/extract_unit4_figures_from_pdf.py``
so the web app matches your compiled ``Unit_4_Geometry.pdf``. This script is only
for quick placeholders or non-PDF diagrams.

Run from repo root:
  python3 scripts/gen_unit4_geometry_svgs.py

Writes static/unit4/{6..24}.svg (skips 15).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "unit4"

# Align with tikz_svg / app palette
ST = "#4f2fd4"
ST_DARK = "#352875"
GRID = "rgba(79, 47, 212, 0.18)"
FILL_SOFT = "rgba(79, 47, 212, 0.10)"
TXT = "#1e1b4b"
GRAY = "#64748b"


def _doc(w: int, h: int, body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="100%" role="img" aria-hidden="true">\n'
        f'<rect width="{w}" height="{h}" rx="10" fill="#ffffff"/>\n'
        f"{body}\n</svg>"
    )


def _txt(x: float, y: float, s: str, *, size: int = 13, anchor: str = "middle", bold: bool = False) -> str:
    fw = "600" if bold else "400"
    ta = "middle" if anchor == "middle" else ("end" if anchor == "end" else "start")
    esc = (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-family="system-ui,Segoe UI,sans-serif" '
        f'fill="{TXT}" text-anchor="{ta}" font-weight="{fw}">{esc}</text>'
    )


def _line(x1: float, y1: float, x2: float, y2: float, *, sw: float = 2.0, c: str = ST_DARK) -> str:
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{c}" stroke-width="{sw}" stroke-linecap="round"/>'


def _poly(pts: list[tuple[float, float]], *, fill: str = "none", stroke: str = ST, sw: float = 2.0) -> str:
    s = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return f'<polygon points="{s}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round"/>'


def _circ(cx: float, cy: float, r: float, *, fill: str = "none", stroke: str = ST, sw: float = 2.0) -> str:
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def _arc_path(cx: float, cy: float, r: float, a0: float, a1: float) -> str:
    """Degrees CCW from +x; SVG y-down so flip."""
    def pt(a):
        rad = math.radians(a)
        return cx + r * math.cos(rad), cy - r * math.sin(rad)

    x0, y0 = pt(a0)
    x1, y1 = pt(a1)
    large = 1 if abs(a1 - a0) % 360 > 180 else 0
    sweep = 0 if a1 > a0 else 1
    return f"M {x0:.2f} {y0:.2f} A {r:.2f} {r:.2f} 0 {large} {sweep} {x1:.2f} {y1:.2f}"


def fig_06() -> str:
    """Cube + inscribed sphere (schematic)."""
    w, h = 520, 360
    cx, cy, s = 260, 190, 140
    r = s / 2
    body = []
    body.append(_poly([(cx - s / 2, cy - s / 2), (cx + s / 2, cy - s / 2), (cx + s / 2, cy + s / 2), (cx - s / 2, cy + s / 2)], fill="none", stroke=ST_DARK, sw=2.5))
    body.append(_circ(cx, cy, r * 0.92, fill=FILL_SOFT, stroke=ST, sw=2.2))
    body.append(_txt(cx, cy + s / 2 + 28, "Cube with sphere touching face centers (schematic)", size=12))
    return _doc(w, h, "\n".join(body))


def fig_07() -> str:
    """Angles AC=CD, ∠EBC=45°, ∠ACD=104°, find x (schematic)."""
    w, h = 520, 380
    body = []
    # C vertex center-bottom, rays to A (left-up) and D (right-up), B left, E right
    Cx, Cy = 260, 280
    Ax, Ay = 120, 120
    Dx, Dy = 400, 110
    Bx, By = 140, 260
    Ex, Ey = 420, 250
    body.append(_line(Ax, Ay, Cx, Cy, sw=2.2))
    body.append(_line(Cx, Cy, Dx, Dy, sw=2.2))
    body.append(_line(Bx, By, Ex, Ey, sw=2.0, c=GRAY))
    body.append(_line(Bx, By, Cx, Cy, sw=2.0, c=GRAY))
    for x, y, lab in ((Ax, Ay, "A"), (Bx, By, "B"), (Cx, Cy, "C"), (Dx, Dy, "D"), (Ex, Ey, "E")):
        body.append(_circ(x, y, 5, fill="#111", stroke="#fff", sw=1))
        body.append(_txt(x + (12 if x > Cx else -12), y - 14, lab, bold=True))
    body.append(_txt(200, 60, "104°", size=14))
    body.append(_txt(150, 230, "45°", size=14))
    body.append(_txt(300, 200, "x°", size=14, bold=True))
    body.append(_txt(260, 350, "AC = CD (not to scale)", size=11, anchor="middle"))
    return _doc(w, h, "\n".join(body))


def fig_08() -> str:
    """Collinear P–Q–R–S–T on PV; transversals (schematic)."""
    w, h = 560, 320
    body = []
    y0 = 200
    x0, x1 = 60, 500
    body.append(_line(x0, y0, x1, y0, sw=3))
    pts = [("P", 70), ("Q", 150), ("R", 230), ("S", 310), ("T", 390), ("V", 480)]
    for lab, px in pts:
        body.append(_circ(px, y0, 4, fill=ST, stroke="#fff", sw=1))
        body.append(_txt(px, y0 + 22, lab, size=12, bold=True))
    body.append(_line(150, y0, 180, 80, sw=2, c=ST))
    body.append(_line(310, y0, 340, 90, sw=2, c=ST))
    body.append(_txt(280, 40, "48°, 86°, 85°, 162° (diagram schematic)", size=11))
    return _doc(w, h, "\n".join(body))


def fig_09() -> str:
    """Three lines r, s, t; angle x."""
    w, h = 480, 360
    cx, cy = 240, 180
    body = []
    for ang in (0, 60, 120):
        rad = math.radians(ang)
        x2 = cx + 160 * math.cos(rad)
        y2 = cy - 160 * math.sin(rad)
        body.append(_line(cx, cy, x2, y2, sw=2.5))
    body.append(_txt(cx + 55, cy - 55, "x°", size=16, bold=True))
    body.append(_txt(40, 40, "r", size=14, bold=True))
    body.append(_txt(cx + 120, cy - 120, "s", size=14, bold=True))
    body.append(_txt(cx - 130, cy + 100, "t", size=14, bold=True))
    return _doc(w, h, "\n".join(body))


def fig_10() -> str:
    """MQ and NR intersect at P; NP = QP, MP = PR (schematic)."""
    w, h = 520, 340
    body = []
    P = (260, 170)
    M, Q = (120, 80), (400, 80)
    N, R = (140, 260), (380, 260)
    body.append(_line(*M, *Q, sw=2.5))
    body.append(_line(*N, *R, sw=2.5))
    for lab, pt in (("M", M), ("Q", Q), ("N", N), ("R", R)):
        body.append(_circ(*pt, 5, fill="#111", stroke="#fff", sw=1))
        body.append(_txt(pt[0], pt[1] - 16, lab, bold=True))
    body.append(_circ(*P, 5, fill=ST, stroke="#fff", sw=1))
    body.append(_txt(P[0], P[1] + 22, "P", bold=True))
    body.append(_txt(260, 310, "NP = QP, MP = PR", size=11, anchor="middle"))
    return _doc(w, h, "\n".join(body))


def fig_11() -> str:
    """Parallelogram-style figure for NQ length (schematic)."""
    w, h = 520, 320
    body = []
    pts = [(120, 220), (380, 220), (440, 100), (180, 100)]
    body.append(_poly(pts + [pts[0]], fill=FILL_SOFT, stroke=ST_DARK, sw=2.5))
    labels = ["M", "N", "P", "Q"]
    for (x, y), lab in zip(pts, labels):
        body.append(_txt(x, y + 28 if y > 150 else y - 16, lab, bold=True))
    body.append(_line(120, 220, 440, 100, sw=1.8, c=GRAY))
    body.append(_line(380, 220, 180, 100, sw=1.8, c=GRAY))
    body.append(_txt(260, 300, "Find NQ (schematic)", size=11, anchor="middle"))
    return _doc(w, h, "\n".join(body))


def fig_12() -> str:
    """Isosceles RT = TU; find x (schematic)."""
    w, h = 480, 360
    R, T, U = (240, 90), (120, 280), (360, 280)
    body = []
    body.append(_poly([R, T, U, R], fill="none", stroke=ST_DARK, sw=2.8))
    for lab, pt in (("R", R), ("T", T), ("U", U)):
        body.append(_circ(*pt, 5, fill="#111", stroke="#fff", sw=1))
        body.append(_txt(pt[0], pt[1] + (28 if lab != "R" else -22), lab, bold=True))
    body.append(_txt(240, 200, "x°", size=15, bold=True))
    body.append(_txt(240, 335, "RT = TU", size=11, anchor="middle"))
    return _doc(w, h, "\n".join(body))


def fig_13() -> str:
    """Right △ABC, altitude BD; area bounds (schematic)."""
    w, h = 520, 360
    A, B, C = (120, 100), (120, 280), (400, 280)
    body = []
    body.append(_poly([A, B, C, A], fill=FILL_SOFT, stroke=ST_DARK, sw=2.6))
    # D foot from B to AC
    D = (260, 190)
    body.append(_line(*B, *D, sw=2, c=ST))
    body.append(_circ(*A, 5, fill="#111", stroke="#fff", sw=1))
    body.append(_circ(*B, 5, fill="#111", stroke="#fff", sw=1))
    body.append(_circ(*C, 5, fill="#111", stroke="#fff", sw=1))
    body.append(_circ(*D, 4, fill=ST, stroke="#fff", sw=1))
    for lab, pt in (("A", A), ("B", B), ("C", C), ("D", D)):
        body.append(_txt(pt[0] + (0 if lab != "D" else 18), pt[1] - 18, lab, bold=True))
    body.append(_txt(260, 40, "Area between 48 and 60 (schematic)", size=11, anchor="middle"))
    return _doc(w, h, "\n".join(body))


def fig_14() -> str:
    """Parallel lines q, t cut by r, s; a = 43°, b = 122°, find w (schematic)."""
    w, h = 540, 340
    body = []
    y1, y2 = 120, 220
    body.append(_line(60, y1, 480, y1, sw=2.5))
    body.append(_line(60, y2, 480, y2, sw=2.5))
    body.append(_line(160, 40, 220, 300, sw=2, c=ST))
    body.append(_line(320, 50, 400, 300, sw=2, c=ST))
    body.append(_txt(80, y1 - 18, "q", bold=True))
    body.append(_txt(80, y2 - 18, "t", bold=True))
    body.append(_txt(100, 40, "r", bold=True))
    body.append(_txt(420, 40, "s", bold=True))
    body.append(_txt(200, 160, "43°", size=13))
    body.append(_txt(360, 170, "122°", size=13))
    body.append(_txt(280, 250, "w°", size=15, bold=True))
    return _doc(w, h, "\n".join(body))


def fig_16() -> str:
    """Right △ABC (∠B = 90°), altitude from B to hypotenuse AC at D; BD = 6, AD = 8 (schematic)."""
    w, h = 520, 380
    B = (120, 260)
    A = (120, 100)
    C = (400, 260)
    D = (248, 178)  # on AC, schematic foot
    body = []
    body.append(_poly([A, B, C, A], fill="none", stroke=ST_DARK, sw=2.8))
    body.append(_line(*B, *D, sw=2.2, c=ST))
    for lab, pt in (("A", A), ("B", B), ("C", C), ("D", D)):
        body.append(_circ(*pt, 5, fill="#111", stroke="#fff", sw=1))
        body.append(_txt(pt[0] + (-18 if lab == "B" else 14), pt[1] - 14, lab, bold=True))
    body.append(_txt(320, 150, "BD = 6", size=12))
    body.append(_txt(200, 130, "AD = 8", size=12))
    body.append(_txt(260, 350, "∠B = 90° (schematic)", size=11, anchor="middle"))
    return _doc(w, h, "\n".join(body))


def fig_17() -> str:
    """Right triangle, sin(B)=5/13 (B acute, right angle at C)."""
    w, h = 480, 360
    C, B, A = (420, 280), (140, 280), (420, 90)
    body = []
    body.append(_poly([A, B, C, A], fill=FILL_SOFT, stroke=ST_DARK, sw=2.8))
    for lab, pt in (("A", A), ("B", B), ("C", C)):
        body.append(_circ(*pt, 5, fill="#111", stroke="#fff", sw=1))
        body.append(_txt(pt[0] + (-22 if lab == "B" else 12), pt[1] + (18 if lab == "C" else -18), lab, bold=True))
    body.append(_txt(260, 200, "∠C = 90°", size=12))
    body.append(_txt(260, 40, "sin(B) = 5/13", size=13, bold=True))
    return _doc(w, h, "\n".join(body))


def fig_18() -> str:
    """Triangle with angle x for sin x."""
    w, h = 460, 340
    A, B, C = (80, 260), (360, 260), (220, 80)
    body = []
    body.append(_poly([A, B, C, A], fill="none", stroke=ST_DARK, sw=2.8))
    for lab, pt in (("A", A), ("B", B), ("C", C)):
        body.append(_circ(*pt, 5, fill="#111", stroke="#fff", sw=1))
        body.append(_txt(pt[0], pt[1] + 26, lab, bold=True))
    body.append(_txt(230, 220, "x°", size=16, bold=True))
    return _doc(w, h, "\n".join(body))


def fig_19() -> str:
    """Three congruent equilateral triangles → trapezoid logo; shaded ends (schematic)."""
    w, h = 560, 280
    body = []
    h_tri = 90
    w_tri = 100
    xs = [80, 180, 280]
    for i, x0 in enumerate(xs):
        pts = [(x0, 200), (x0 + w_tri, 200), (x0 + w_tri / 2, 200 - h_tri)]
        fill = FILL_SOFT if i in (0, 2) else "#ffffff"
        body.append(_poly(pts + [pts[0]], fill=fill, stroke=ST_DARK, sw=2.4))
    body.append(_txt(280, 250, "Three congruent equilateral triangles (shaded schematic)", size=11, anchor="middle"))
    return _doc(w, h, "\n".join(body))


def fig_20() -> str:
    """tan B = 3/4; BC = 15, DA = 4 (schematic stacked right triangles)."""
    w, h = 520, 380
    body = []
    B = (260, 280)
    C = (420, 280)
    A = (260, 120)
    D = (360, 120)
    E = (420, 120)
    body.append(_poly([A, B, C, A], fill="none", stroke=ST_DARK, sw=2.5))
    body.append(_line(*D, *E, sw=2, c=GRAY))
    body.append(_line(*B, *D, sw=1.8, c=GRAY))
    for lab, pt in (("A", A), ("B", B), ("C", C), ("D", D), ("E", E)):
        body.append(_circ(*pt, 4, fill="#111", stroke="#fff", sw=1))
        body.append(_txt(pt[0] + 10, pt[1] - 12, lab, bold=True))
    body.append(_txt(260, 40, "tan B = 3/4 (schematic)", size=12, bold=True))
    return _doc(w, h, "\n".join(body))


def fig_21() -> str:
    """Triangle RST with angle labels (schematic)."""
    w, h = 500, 360
    R, S, T = (250, 90), (120, 280), (380, 280)
    body = []
    body.append(_poly([R, S, T, R], fill=FILL_SOFT, stroke=ST_DARK, sw=2.8))
    for lab, pt in (("R", R), ("S", S), ("T", T)):
        body.append(_circ(*pt, 5, fill="#111", stroke="#fff", sw=1))
        body.append(_txt(pt[0], pt[1] - 22 if lab == "R" else pt[1] + 26, lab, bold=True))
    body.append(_txt(250, 200, "W on RT (not shown)", size=11, anchor="middle"))
    return _doc(w, h, "\n".join(body))


def fig_22() -> str:
    """BD ∥ AE (similar triangles schematic)."""
    w, h = 520, 360
    body = []
    A, B, C, D, E = (420, 80), (180, 80), (120, 280), (260, 280), (460, 280)
    body.append(_line(*A, *E, sw=2, c=GRAY))
    body.append(_line(*B, *D, sw=2.5, c=ST))
    body.append(_poly([B, C, D, B], fill=FILL_SOFT, stroke=ST_DARK, sw=2))
    body.append(_poly([A, C, E, A], fill="none", stroke=ST_DARK, sw=2))
    for lab, pt in (("A", A), ("B", B), ("C", C), ("D", D), ("E", E)):
        body.append(_circ(*pt, 4, fill="#111", stroke="#fff", sw=1))
        body.append(_txt(pt[0] + 8, pt[1] - 14, lab, bold=True))
    body.append(_txt(260, 40, "BD ∥ AE", size=13, bold=True))
    return _doc(w, h, "\n".join(body))


def fig_23() -> str:
    """Circle center O; arcs ADC / ABC; x = 100° (schematic)."""
    w, h = 420, 420
    cx, cy, r = 210, 210, 150
    body = []
    body.append(_circ(cx, cy, r, fill="none", stroke=ST_DARK, sw=2.8))
    body.append(_circ(cx, cy, 5, fill=ST, stroke="#fff", sw=1))
    body.append(_txt(cx, cy - 12, "O", bold=True))
    # A top, D left, C right-ish on circle
    for ang, lab in [(90, "A"), (200, "D"), (0, "C"), (270, "B")]:
        rad = math.radians(ang)
        px, py = cx + (r - 18) * math.cos(rad), cy - (r - 18) * math.sin(rad)
        body.append(_circ(px, py, 4, fill="#111", stroke="#fff", sw=1))
        body.append(_txt(px + 12 * math.cos(rad), py - 12 * math.sin(rad), lab, bold=True))
    body.append(_txt(210, 400, "arc ADC = 5π, x = 100° (schematic)", size=11, anchor="middle"))
    return _doc(w, h, "\n".join(body))


def fig_24() -> str:
    """Circle O; ∠OAB = 30°, OC = 18 (schematic)."""
    w, h = 420, 420
    cx, cy, r = 210, 210, 150
    body = []
    body.append(_circ(cx, cy, r, fill="none", stroke=ST_DARK, sw=2.8))
    body.append(_circ(cx, cy, 5, fill=ST, stroke="#fff", sw=1))
    body.append(_txt(cx - 8, cy - 18, "O", bold=True))
    A = (cx + r - 10, cy)
    B = (cx + (r - 30) * math.cos(math.radians(40)), cy - (r - 30) * math.sin(math.radians(40)))
    C = (cx + r, cy)
    body.append(_line(cx, cy, *A, sw=2, c=ST))
    body.append(_line(cx, cy, *C, sw=1.5, c=GRAY))
    body.append(_line(*A, *B, sw=2, c=ST_DARK))
    for lab, pt in (("A", A), ("B", B), ("C", C)):
        body.append(_circ(*pt, 4, fill="#111", stroke="#fff", sw=1))
        body.append(_txt(pt[0] + 10, pt[1] - 10, lab, bold=True))
    body.append(_txt(60, 60, "∠OAB = 30°", size=12))
    body.append(_txt(60, 85, "OC = 18", size=12))
    return _doc(w, h, "\n".join(body))


FIGS: dict[str, str] = {
    "6": fig_06(),
    "7": fig_07(),
    "8": fig_08(),
    "9": fig_09(),
    "10": fig_10(),
    "11": fig_11(),
    "12": fig_12(),
    "13": fig_13(),
    "14": fig_14(),
    "16": fig_16(),
    "17": fig_17(),
    "18": fig_18(),
    "19": fig_19(),
    "20": fig_20(),
    "21": fig_21(),
    "22": fig_22(),
    "23": fig_23(),
    "24": fig_24(),
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, xml in FIGS.items():
        p = OUT / f"{name}.svg"
        p.write_text(xml, encoding="utf-8")
        print("wrote", p)
    print("Wrote", len(FIGS), "SVG figures to", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
