#!/usr/bin/env python3
"""Generate SAT_4.1–4.4 Beamer courseware from geometry banks + unit4_supplement.json."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANKS = ROOT / "banks" / "geometry"
UNIT4_IMG = ROOT / "static" / "unit4"
SUPPLEMENT = ROOT / "data" / "unit4_supplement.json"

# Bank filename -> (output tex, section number, unit title, manifest section name)
SECTIONS = [
    ("4_1.tex", "SAT_4.1_Volume_and_Area.tex", "4.1", "Volume and Area"),
    ("4_2.tex", "SAT_4.2_Line_Angel_Triangle.tex", "4.2", "Lines, Angles, and Triangles"),
    ("4_3.tex", "SAT_4.3_Trigonometry.tex", "4.3", "Trigonometry"),
    ("4_4.tex", "SAT_4.4_Circle.tex", "4.4", "Circles"),
]

# Optional one-line strategy hints for answer slides (topic_key -> list aligned with questions).
ANSWER_HINTS: dict[str, list[str]] = {
    "4_1": [
        "Similar figures: area scales as $k^2$ when side lengths scale by $k$.",
        "Subtract sphere volume from cube volume; use $V=\\dfrac{4}{3}\\pi r^3$.",
        "Volume scales as $R^2 H$; match the factor $392 = 7\\cdot 8^2$ (or equivalent).",
        "Percent increase in area: multiply linear scale factors and square.",
        "Surface area of a cylinder: $2\\pi r^2 + 2\\pi rh$.",
        "Cone volume is $\\dfrac{1}{3}$ of a cylinder with the same base and height.",
        "Use $A=\\dfrac{1}{2}bh$ or the shoelace formula on the grid.",
        "Equilateral triangle height: $\\dfrac{s\\sqrt{3}}{2}$; area $\\dfrac{s^2\\sqrt{3}}{4}$.",
        "Similar triangles give proportional sides; set up a ratio.",
        "Sphere volume formula: $V=\\dfrac{4}{3}\\pi r^3$.",
        "Read the diagram: identify radius and height from labels.",
        "Scale each dimension and apply the volume formula.",
        "Right triangle on coordinates: use distance or area formula.",
        "Compare cross-section areas when solids share the same height.",
        "Composite solid: add/subtract known volumes.",
        "Similarity ratio squared gives the area ratio.",
        "Plug given dimensions into the correct volume formula.",
    ],
    "4_2": [
        "Isosceles sides $AC=CD$; use triangle angle sum and exterior angles.",
        "Track angles around point $W$ using triangle sum and linear pairs.",
        "Three intersecting lines: vertical and supplementary angle pairs.",
        "Vertical angles and linear pairs at intersection $Q$.",
        "Parallel lines + transversal: alternate interior angles are equal.",
        "Triangle sum is $180^\\circ$; combine with isosceles base angles.",
        "Exterior angle equals sum of remote interior angles.",
        "Congruent triangles: match corresponding parts (CPCTC).",
        "Similar triangles: set up a proportion for missing length.",
        "Area ratio of similar triangles equals $(\\text{scale factor})^2$.",
        "Coordinate geometry: slope or distance for parallel/perpendicular.",
        "Angle chase using straight angle ($180^\\circ$) and vertical angles.",
        "ASA/AAS/SAS: identify which congruence criterion applies.",
        "Use $\\dfrac{1}{2}bh$ after finding base and height from the diagram.",
    ],
    "4_3": [
        "Right triangle: $\\sin B=\\dfrac{\\text{opp}}{\\text{hyp}}$; find the missing side.",
        "Label opposite/hypotenuse relative to angle $x$.",
        "Equilateral triangles: height $=\\dfrac{s\\sqrt{3}}{2}$; shaded area from symmetry.",
        "Equilateral triangle side $=\\dfrac{\\text{perimeter}}{3}$; height $=\\dfrac{s\\sqrt{3}}{2}$.",
        "Use $\\tan B=\\dfrac{3}{4}$ to find missing legs, then similar triangles.",
        "Isosceles right triangle: legs $=\\dfrac{h}{\\sqrt{2}}$; perimeter $=2\\ell+h$.",
        "Perimeter $=2\\ell+\\ell\\sqrt{2}$; solve for leg $\\ell$.",
        "Similar triangles: $\\tan W$ matches $\\tan T$ (corresponding acute angles).",
        "$\\sin 30^\\circ=\\dfrac{1}{2}$; use $30$-$60$-$90$ side ratios.",
        "Complementary angles: $\\sin A=\\cos B$ when $A+B=90^\\circ$.",
        "Pythagorean theorem to find the third side, then compute the ratio.",
        "Similar right triangles share equal acute angles; trig ratios match.",
        "$30$-$60$-$90$ or $\\tan A=\\sqrt{3}$ fixes the angle; use SOH-CAH-TOA on the similar triangle.",
        "Pythagorean theorem: $\\text{longer}^2 = d^2 - 3^2$.",
        "A square inscribed in a circle has diagonal $=$ diameter $=2r$.",
        "Similar right triangles: $\\sin D=\\sin A$ when $A$ corresponds to $D$.",
        "Complementary acute angles: $\\tan(90^\\circ-\\theta)=\\dfrac{1}{\\tan\\theta}$.",
        "Parallel lines create similar triangles; set up a proportion for $CE$.",
        "Draw a right triangle for $\\cos K$; use Pythagorean theorem for adjacent side.",
        "$30$-$60$-$90$ triangle side ratio $1:\\sqrt{3}:2$.",
    ],
    "4_4": [
        "Standard form $(x-h)^2+(y-k)^2=r^2$ reveals center and radius.",
        "Complete the square on both $x$ and $y$.",
        "Distance from center to point equals radius.",
        "Tangent line is perpendicular to the radius at the point of tangency.",
        "Substitute the point into the circle equation to solve for $r$ or $k$.",
        "Shift $y$ by $k$ in the equation to move the center vertically.",
        "Expand and match coefficients after completing the square.",
        "Two circles: compare centers and radii for intersection.",
        "Arc length $=\\dfrac{\\theta}{360^\\circ}\\cdot 2\\pi r$.",
        "Sector area $=\\dfrac{\\theta}{360^\\circ}\\cdot \\pi r^2$.",
        "Inscribed angle relates to intercepted arc.",
        "Use the distance formula for chord length or radius.",
        "Perpendicular from center bisects a chord.",
        "System: substitute line into circle equation.",
        "Graph the center and radius; read intercepts from symmetry.",
        "Angle in semicircle or central vs. inscribed angle relationship.",
        "Reflect over center to find symmetric point on the circle.",
        "Slope of tangent is negative reciprocal of radius slope.",
        "Difference of areas of two circles with radii $R$ and $r$.",
        "Apply vertical/horizontal shift to center coordinates.",
    ],
}

CONCEPT_SLIDES: dict[str, list[str]] = {
    "4.1": [
        r"""
\begin{frame}{Perimeter Formulas}

\begin{itemize}
    \item Square: $P = 4s$
    \item Rectangle: $P = 2(\ell + w)$
    \item Triangle: $P = a + b + c$
    \item Circle (circumference): $C = 2\pi r = \pi d$
\end{itemize}

\vspace{0.2cm}
\textbf{SAT move:} perimeter is a \textit{length} measurement, so it scales linearly.

\end{frame}
""",
        r"""
\begin{frame}{Area Formulas}

\begin{itemize}
    \item Square: $A = s^2$
    \item Rectangle: $A = \ell w$
    \item Triangle: $A = \dfrac{1}{2}bh$
    \item Parallelogram: $A = bh$
    \item Trapezoid: $A = \dfrac{1}{2}(b_1+b_2)h$
    \item Circle: $A = \pi r^2$
\end{itemize}

\vspace{0.2cm}
\textbf{SAT move:} area is two-dimensional, so a scale factor $k$ becomes $k^2$ for area.

\end{frame}
""",
        r"""
\begin{frame}{Prism and Cylinder Volume}

\textbf{Prism:} A prism has two parallel congruent bases.
\[
V_{\text{prism}} = Bh
\]

\textbf{Cylinder:} The base is a circle, so $B=\pi r^2$.
\[
V_{\text{cylinder}} = Bh = \pi r^2h
\]

\vspace{0.15cm}
\textbf{SAT move:} identify the base area first, then multiply by height.

\end{frame}
""",
        r"""
\begin{frame}{Worked Example: Surface Area of a Cube}

\textbf{Question:} A cube has volume $42{,}875$ cubic inches. What is the surface area?

\vspace{0.2cm}
\textbf{Solution:}
\[
s^3 = 42{,}875 \quad \Rightarrow \quad s = 35
\]
\[
\text{Surface Area} = 6s^2 = 6(35)^2 = 7{,}350
\]

\textbf{Answer:} $\boxed{7{,}350}$ square inches.

\end{frame}
""",
        r"""
\begin{frame}{Worked Example: Cylinder Diameter}

\textbf{Question:} A cylinder has volume $980\pi$ cubic feet and height $5$ feet. What is the base diameter?

\vspace{0.2cm}
\[
V=\pi r^2h
\]
\[
980\pi = \pi r^2(5) \quad \Rightarrow \quad r^2=196 \quad \Rightarrow \quad r=14
\]
\[
d=2r=28
\]

\textbf{Answer:} $\boxed{28}$ feet.

\end{frame}
""",
        r"""
\begin{frame}{Pyramid and Cone Volume}

\textbf{Pyramid:}
\[
V_{\text{pyramid}} = \dfrac{1}{3}Bh
\]

\textbf{Cone:}
\[
V_{\text{cone}} = \dfrac{1}{3}\pi r^2h
\]

\vspace{0.15cm}
\textbf{Key idea:} a pyramid or cone is one-third of the matching prism or cylinder with the same base and height.

\end{frame}
""",
        r"""
\begin{frame}{Worked Example: Square Pyramid}

\textbf{Question:} A right square pyramid has height $33$ cm and square base side length $14$ cm. Find the volume.

\vspace{0.2cm}
\[
B = 14\cdot 14 = 196
\]
\[
V = \dfrac{1}{3}Bh = \dfrac{1}{3}(196)(33)=2{,}156
\]

\textbf{Answer:} $\boxed{2{,}156}$ cubic centimeters.

\end{frame}
""",
        r"""
\begin{frame}{Density}

\textbf{Definition:} density measures how much mass is packed into a given volume.
\[
\text{Density} = \dfrac{\text{Mass}}{\text{Volume}}
\]

\vspace{0.2cm}
\textbf{Example:} A rock has mass $200$ g and volume $50\text{ cm}^3$.
\[
\text{Density}=\dfrac{200}{50}=4\text{ g/cm}^3
\]

\end{frame}
""",
        r"""
\begin{frame}{Worked Example: Density}

\textbf{Question:} A foam block has mass $8$ kg and volume $20\text{ m}^3$. What is the density?

\vspace{0.2cm}
\[
\text{Density}=\dfrac{8}{20}=0.4
\]

\textbf{Answer:} $\boxed{0.4}$ kg/m$^3$.

\vspace{0.2cm}
\textbf{SAT move:} always check the units: mass divided by volume.

\end{frame}
""",
        r"""
\begin{frame}{Ratio of Length, Area, and Volume}

When a figure is scaled by factor $k$:
\begin{itemize}
    \item Lengths scale by $k$
    \item Areas scale by $k^2$
    \item Volumes scale by $k^3$
\end{itemize}

\vspace{0.2cm}
\textbf{Example:} If every dimension is tripled, area becomes $3^2=9$ times as large and volume becomes $3^3=27$ times as large.

\end{frame}
""",
        r"""
\begin{frame}{Worked Example: Scaled Poster}

\textbf{Question:} A rectangular poster has area $360$ square inches. Its length and width are each increased by $20\%$. What is the new area?

\vspace{0.2cm}
\[
k=1.2
\]
\[
\text{New Area}=360(1.2)^2 = 360(1.44)=518.4
\]

\textbf{Answer:} $\boxed{518.4}$ square inches.

\end{frame}
""",
    ],
    "4.2": [
        r"""
\begin{frame}{Angle Relationships}

\begin{itemize}
    \item Vertical angles are equal.
    \item A linear pair sums to $180^\circ$.
    \item Angles around a point sum to $360^\circ$.
\end{itemize}

\vspace{0.2cm}
\textbf{SAT move:} mark what you know on the diagram first, then chase missing angles one relationship at a time.

\end{frame}
""",
        r"""
\begin{frame}{Parallel Lines and Transversals}

When two parallel lines are cut by a transversal:
\begin{itemize}
    \item Corresponding angles are equal.
    \item Alternate interior angles are equal.
    \item Same-side interior angles sum to $180^\circ$.
\end{itemize}

\vspace{0.2cm}
\textbf{Shortcut:} if you see arrow marks for parallel lines, immediately look for equal or supplementary angle pairs.

\end{frame}
""",
        r"""
\begin{frame}{Triangles: Core Facts}

\begin{itemize}
    \item Interior angles of a triangle sum to $180^\circ$.
    \item Exterior angle equals the sum of the two remote interior angles.
    \item Isosceles triangle: equal sides have equal opposite angles.
    \item Triangle area: $A=\dfrac{1}{2}bh$.
\end{itemize}

\end{frame}
""",
        r"""
\begin{frame}{Triangle Congruence}

\textbf{Common congruence reasons:}
\begin{itemize}
    \item SSS: three sides match
    \item SAS: two sides and included angle match
    \item ASA/AAS: two angles and one side match
    \item HL: right triangles with hypotenuse and one leg match
\end{itemize}

\vspace{0.2cm}
\textbf{After congruence:} corresponding sides and angles are equal (CPCTC).

\end{frame}
""",
        r"""
\begin{frame}{Similar Triangles}

\textbf{AA similarity:} two equal angles are enough.

\vspace{0.2cm}
For similar triangles:
\[
\dfrac{\text{side}_1}{\text{matching side}_1}
=
\dfrac{\text{side}_2}{\text{matching side}_2}
\]

\vspace{0.2cm}
\textbf{SAT move:} write the proportion using matching positions, not just visually close sides.

\end{frame}
""",
        r"""
\begin{frame}{Coordinate Geometry With Triangles}

\begin{itemize}
    \item Horizontal/vertical distances can be read from coordinates.
    \item Distance formula: $d=\sqrt{(x_2-x_1)^2+(y_2-y_1)^2}$.
    \item Slope helps identify parallel or perpendicular lines.
    \item Area can be found by enclosing the triangle in a rectangle and subtracting.
\end{itemize}

\end{frame}
""",
        r"""
\begin{frame}{Worked Example: Triangle Area}

\textbf{Question:} A triangle has base $18$ and height $7$. What is its area?

\vspace{0.2cm}
\[
A=\dfrac{1}{2}bh=\dfrac{1}{2}(18)(7)=63
\]

\textbf{Answer:} $\boxed{63}$.

\end{frame}
""",
    ],
    "4.3": [
        r"""
\begin{frame}{Right-Triangle Trigonometry}

For acute angle $\theta$ in a right triangle:
\[
\sin \theta = \frac{\text{opp}}{\text{hyp}}, \quad
\cos \theta = \frac{\text{adj}}{\text{hyp}}, \quad
\tan \theta = \frac{\text{opp}}{\text{adj}}
\]

\vspace{0.15cm}
\textbf{Special right triangles:}
\begin{itemize}
    \item $45^\circ$-$45^\circ$-$90^\circ$: sides $s,\ s,\ s\sqrt{2}$
    \item $30^\circ$-$60^\circ$-$90^\circ$: sides $s,\ s\sqrt{3},\ 2s$
\end{itemize}

\end{frame}
""",
        r"""
\begin{frame}{SOH-CAH-TOA}

\begin{itemize}
    \item \textbf{SOH:} $\sin\theta=\dfrac{\text{opposite}}{\text{hypotenuse}}$
    \item \textbf{CAH:} $\cos\theta=\dfrac{\text{adjacent}}{\text{hypotenuse}}$
    \item \textbf{TOA:} $\tan\theta=\dfrac{\text{opposite}}{\text{adjacent}}$
\end{itemize}

\vspace{0.2cm}
\textbf{SAT move:} label opposite, adjacent, and hypotenuse relative to the angle named in the problem.

\end{frame}
""",
        r"""
\begin{frame}{Special Right Triangles}

\textbf{$45^\circ$-$45^\circ$-$90^\circ$:}
\[
s,\quad s,\quad s\sqrt{2}
\]

\textbf{$30^\circ$-$60^\circ$-$90^\circ$:}
\[
s,\quad s\sqrt{3},\quad 2s
\]

\vspace{0.2cm}
\textbf{SAT move:} if an angle is $30^\circ$, $45^\circ$, or $60^\circ$, use the ratio before doing extra algebra.

\end{frame}
""",
        r"""
\begin{frame}{Complementary Angles}

In a right triangle, the two acute angles add to $90^\circ$.
\[
\sin A = \cos(90^\circ-A)
\]
\[
\tan A \cdot \tan(90^\circ-A)=1
\]

\vspace{0.2cm}
\textbf{Example:} If $\tan A=\dfrac{3}{4}$, then the tangent of the other acute angle is $\dfrac{4}{3}$.

\end{frame}
""",
        r"""
\begin{frame}{Similar Right Triangles}

If two right triangles share an acute angle, they are similar.

\vspace{0.2cm}
That means their trig ratios match:
\[
\sin A,\quad \cos A,\quad \tan A
\]
stay the same even if the triangle is scaled.

\vspace{0.2cm}
\textbf{SAT move:} do not solve every side if a trig ratio already gives the relationship.

\end{frame}
""",
        r"""
\begin{frame}{Worked Example: Tangent}

\textbf{Question:} In a right triangle, $\tan B=\dfrac{3}{4}$. What can the legs be?

\vspace{0.2cm}
\[
\tan B=\dfrac{\text{opposite}}{\text{adjacent}}=\dfrac{3}{4}
\]
So the legs are in the ratio $3:4$.

\vspace{0.2cm}
The hypotenuse is then in ratio $5$ by the $3$-$4$-$5$ triangle.

\end{frame}
""",
        r"""
\begin{frame}{Common Trig Traps}

\begin{itemize}
    \item Opposite and adjacent change when the named angle changes.
    \item The hypotenuse is always across from the right angle.
    \item $\tan$ never uses the hypotenuse.
    \item Similar triangles preserve trig ratios, not necessarily side lengths.
\end{itemize}

\end{frame}
""",
    ],
    "4.4": [
        r"""
\begin{frame}{Circle Equation}

\textbf{Standard form:} $(x - h)^2 + (y - k)^2 = r^2$ has center $(h,k)$ and radius $r$.

\vspace{0.15cm}
\textbf{Key relationships:}
\begin{itemize}
    \item Diameter $= 2r$
    \item Arc measure equals central angle (in degrees)
    \item Arc length $= \dfrac{\text{arc measure}}{360^\circ} \times 2\pi r$
\end{itemize}

\vspace{0.15cm}
\textbf{Completing the square} converts general form to standard form.

\end{frame}
""",
        r"""
\begin{frame}{Completing the Square}

To rewrite a circle equation in standard form:
\[
x^2+6x+y^2-8y=11
\]
group variables and complete the square:
\[
(x^2+6x+9)+(y^2-8y+16)=11+9+16
\]
\[
(x+3)^2+(y-4)^2=36
\]

\textbf{Center:} $(-3,4)$ \quad \textbf{Radius:} $6$

\end{frame}
""",
        r"""
\begin{frame}{Radius, Diameter, and Chords}

\begin{itemize}
    \item Radius: center to circle.
    \item Diameter: $d=2r$.
    \item A radius perpendicular to a chord bisects the chord.
    \item Distance formula often gives radius or chord length.
\end{itemize}

\vspace{0.2cm}
\textbf{SAT move:} draw the radius to create a right triangle.

\end{frame}
""",
        r"""
\begin{frame}{Tangents}

A tangent line touches the circle at exactly one point.

\vspace{0.2cm}
\textbf{Key fact:}
\[
\text{radius} \perp \text{tangent at the point of tangency}
\]

\vspace{0.2cm}
\textbf{Coordinate move:} if the radius slope is $m$, the tangent slope is $-\dfrac{1}{m}$.

\end{frame}
""",
        r"""
\begin{frame}{Arc Length and Sector Area}

For central angle $\theta$:
\[
\text{Arc length}=\dfrac{\theta}{360^\circ}\cdot 2\pi r
\]
\[
\text{Sector area}=\dfrac{\theta}{360^\circ}\cdot \pi r^2
\]

\vspace{0.2cm}
\textbf{SAT move:} use the same fraction of the circle for arc length and sector area.

\end{frame}
""",
        r"""
\begin{frame}{Inscribed Angles}

\textbf{Central angle:} vertex at center.

\textbf{Inscribed angle:} vertex on circle.

\[
\text{Inscribed angle} = \dfrac{1}{2}(\text{intercepted arc})
\]

\vspace{0.2cm}
\textbf{Special case:} an angle inscribed in a semicircle is a right angle.

\end{frame}
""",
        r"""
\begin{frame}{Worked Example: Standard Form}

\textbf{Question:} What are the center and radius of $(x-5)^2+(y+2)^2=49$?

\vspace{0.2cm}
\[
(x-h)^2+(y-k)^2=r^2
\]
\[
h=5,\quad k=-2,\quad r=7
\]

\textbf{Answer:} center $(5,-2)$ and radius $7$.

\end{frame}
""",
    ],
}


def load_supplement() -> dict:
    with open(SUPPLEMENT, encoding="utf-8") as f:
        return json.load(f)


def ensure_pdf_raster_figures() -> None:
    """Create high-res PNG companions for SVG figures so pdflatex can embed them."""
    UNIT4_IMG.mkdir(parents=True, exist_ok=True)
    for svg in sorted(UNIT4_IMG.glob("*.svg")):
        png = UNIT4_IMG / f"{svg.stem}.png"
        if png.is_file() and png.stat().st_mtime >= svg.stat().st_mtime:
            continue
        tmp = UNIT4_IMG / f"{svg.name}.png"
        try:
            subprocess.run(
                ["qlmanage", "-t", "-s", "1200", "-o", str(UNIT4_IMG), str(svg)],
                check=True,
                capture_output=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            print(f"  warning: could not rasterize {svg.name}; PDF build may skip this figure")
            continue
        if tmp.is_file():
            tmp.replace(png)
            print(f"  raster: {svg.name} -> {png.name}")
        elif not png.is_file():
            print(f"  warning: missing PNG for {svg.name}")


def normalize_answer(entry: str | dict) -> tuple[str, list[str]]:
    if isinstance(entry, dict):
        return str(entry["canonical"]), [str(x) for x in entry.get("alternates", [])]
    return str(entry), []


def is_mcq_letter(ans: str) -> bool:
    return ans.strip().upper() in {"A", "B", "C", "D"}


def escape_frame_title(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s[:72] + ("…" if len(s) > 72 else "")


def to_plain_title(s: str) -> str:
    """Flatten LaTeX stem text into a Beamer-safe plain title."""
    prev = None
    while prev != s:
        prev = s
        s = re.sub(
            r"\\(?:dfrac|tfrac|frac)\{([^{}]*)\}\{([^{}]*)\}",
            r"\1/\2",
            s,
        )
        s = re.sub(
            r"\\(?:textbf|textit|overline|angle|boxed|text)\{([^{}]*)\}",
            r"\1",
            s,
        )
    s = re.sub(r"\^\s*\\circ", "°", s)
    s = re.sub(r"\\circ\b", "°", s)
    s = re.sub(r"\$([^$]+)\$", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+\b", " ", s)
    s = re.sub(r"[\$\\^_{}]", "", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return escape_frame_title(s)


def safe_frame_title(s: str) -> str:
    return to_plain_title(s)


def figure_tex_name(fname: str) -> str:
    """Use extensionless names for SVG so pdflatex picks the PNG raster companion."""
    path = Path(fname.strip())
    if path.suffix.lower() == ".svg":
        return path.stem
    return path.name


def read_braced_content(text: str, open_pos: int) -> tuple[str, int] | None:
    """Return (inner, index_after_closing) for text[open_pos] == '{'."""
    if open_pos >= len(text) or text[open_pos] != "{":
        return None
    i = open_pos + 1
    depth = 1
    start = i
    while i < len(text) and depth > 0:
        if text[i] == "\\":
            i += 1
            cmd_start = i
            while i < len(text) and text[i].isalpha():
                i += 1
            cmd = text[cmd_start:i]
            if cmd in {"frac", "dfrac", "tfrac", "binom"}:
                for _ in range(2):
                    while i < len(text) and text[i].isspace():
                        i += 1
                    if i < len(text) and text[i] == "{":
                        parsed = read_braced_content(text, i)
                        if parsed:
                            _, i = parsed
                continue
            if i < len(text) and text[i] == "{":
                parsed = read_braced_content(text, i)
                if parsed:
                    _, i = parsed
            continue
        elif text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i], i + 1
        i += 1
    return None


def first_choicebox_span(text: str) -> tuple[int, int, str, str] | None:
    marker = "\\choicebox{"
    idx = text.find(marker)
    if idx == -1:
        return None
    pos = idx + len(marker)
    letter_end = text.find("}", pos)
    if letter_end == -1:
        return None
    letter = text[pos:letter_end].strip()
    pos = letter_end + 1
    while pos < len(text) and text[pos].isspace():
        pos += 1
    if pos >= len(text) or text[pos] != "{":
        return None
    content_parsed = read_braced_content(text, pos)
    if not content_parsed:
        return None
    content, end = content_parsed
    return idx, end, letter, content.strip()


def extract_all_choiceboxes(text: str) -> tuple[str, list[tuple[str, str]]]:
    out = text
    choices: list[tuple[str, str]] = []
    while True:
        span = first_choicebox_span(out)
        if not span:
            break
        i, j, letter, content = span
        choices.append((letter, content))
        out = out[:i] + out[j:]
    return out, choices


def first_line(stem: str) -> str:
    stem = re.sub(r"\\begin\{center\}.*?\\end\{center\}", "", stem, flags=re.S)
    stem = re.sub(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", "", stem, flags=re.S)
    for line in stem.splitlines():
        t = line.strip()
        if not t or t.startswith("\\begin") or t.startswith("\\includegraphics"):
            continue
        m = re.search(r"\\textbf\{(.+)\}", t)
        if m:
            t = m.group(1)
        t = to_plain_title(t)
        if len(t) >= 12:
            return t
    return "Practice Question"


def transform_body(body: str) -> str:
    out = body
    out = re.sub(r"\\newpage\s*", "", out)
    out = re.sub(r"\\vspace\{[^}]+\}\s*", "", out)
    out = re.sub(r"\\vspace\{[^}]+\}\s*", "", out)

    # Fix known LaTeX typo in 4_3
    out = out.replace(r"125\frac{\sqrt{3}}{2}", r"125\dfrac{\sqrt{3}}{2}")

    # choicebox -> itemize (brace-safe)
    out, choices = extract_all_choiceboxes(out)
    if choices:
        items = "\n".join(
            rf"    \item[\textbf{{{letter}.}}] {content.strip()}"
            for letter, content in choices
        )
        out = out.rstrip() + "\n\\begin{itemize}\n" + items + "\n\\end{itemize}\n"

    # Keep original figure filenames and linewidths from the bank (100% fidelity).
    def fig_repl(m: re.Match[str]) -> str:
        width = m.group(1) or "0.54\\linewidth"
        fname = figure_tex_name(m.group(2).strip())
        return rf"\includegraphics[width={width}]{{{fname}}}"

    out = re.sub(
        r"\\includegraphics(?:\[width=([^\]]+)\])?\{([^}]+)\}",
        fig_repl,
        out,
    )

    # Wrap bare includegraphics in center if not already
    if r"\includegraphics" in out and r"\begin{center}" not in out:
        out = re.sub(
            r"(\\includegraphics\[[^\]]+\]\{[^}]+\})",
            r"\\begin{center}\n    \1\n\\end{center}",
            out,
            count=1,
        )

    return out.strip()


def split_questions(bank_tex: str) -> list[str]:
    bank_tex = re.sub(r"\\subsection\*\{[^}]+\}", "", bank_tex, count=1)
    bank_tex = re.sub(r"\\setcounter\{questionnum\}\{0\}", "", bank_tex)
    parts = re.split(r"\\noindent\\markforreview", bank_tex)
    blocks = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("\\vspace"):
            part = part.split("\n", 2)[-1] if "\n" in part else ""
        part = part.strip()
        if part:
            blocks.append(part)
    return blocks


def preamble(unit: str, title: str) -> str:
    return rf"""\documentclass{{beamer}}
\usepackage{{graphicx}}
\usepackage{{xcolor}}
\usepackage{{tikz}}
\usepackage{{amsmath}}
\DeclareGraphicsExtensions{{.png,.pdf,.jpg,.jpeg}}

\definecolor{{purpleblue}}{{RGB}}{{80, 80, 180}}
\definecolor{{lightgray}}{{RGB}}{{230, 230, 230}}
\definecolor{{novelPurple}}{{RGB}}{{98, 54, 255}}
\definecolor{{darkgray}}{{RGB}}{{50, 50, 50}}
\definecolor{{softPurple}}{{RGB}}{{180, 170, 255}}
\definecolor{{softGray}}{{RGB}}{{235, 235, 245}}
\definecolor{{lightText}}{{RGB}}{{90, 90, 110}}
\graphicspath{{{{static/unit4/}}{{./}}}}

\usetheme{{Madrid}}
\usecolortheme{{dolphin}}

\setbeamerfont{{title}}{{size=\Large,series=\bfseries}}
\setbeamerfont{{frametitle}}{{size=\LARGE,series=\bfseries}}
\setbeamercolor{{frametitle}}{{fg=white, bg=novelPurple}}
\setbeamercolor{{title}}{{fg=white, bg=purpleblue}}

\title[SAT Unit {unit}]{{\textbf{{SAT Unit {unit} \\{title}}}}}
\author{{\textbf{{Jack Zeng}}}}
\institute{{\textcolor{{white}}{{\textbf{{Novel Prep}}}}}}
\date{{\today}}

\begin{{document}}

\begin{{frame}}
    \titlepage
    \vfill
    \begin{{flushright}}
        \textcolor{{purpleblue}}{{\Huge \textbf{{Novel Prep}}}}
    \end{{flushright}}
\end{{frame}}

\begin{{frame}}
    \begin{{tikzpicture}}[remember picture, overlay]
        \shade[top color=softPurple, bottom color=softGray]
            (current page.north west) rectangle (current page.south east);
        \fill[white, opacity=0.3] (current page.center) circle (4cm);
        \node[align=center] at (current page.center) {{
            {{\Huge\bfseries\textcolor{{purpleblue}}{{Novel Prep}}}} \\[0.5cm]
            {{\Large\itshape\textcolor{{lightText}}{{Excellence in SAT Prep}}}}
        }};
        \foreach \x in {{1,2,3,4,5}} {{
            \fill[purpleblue, opacity=0.2] (rand*10-5, rand*7-3.5) circle (0.1+\x*0.05);
        }}
    \end{{tikzpicture}}
\end{{frame}}

\begin{{frame}}{{Overview}}
    \tableofcontents
\end{{frame}}

"""


def section_divider(section_title: str) -> str:
    safe = section_title.replace("&", "\\&")
    return rf"""
\begin{{frame}}
\section{{{safe}}}
    \begin{{tikzpicture}}[remember picture, overlay]
        \shade[top color=softPurple, bottom color=softGray]
            (current page.north west) rectangle (current page.south east);
        \fill[white, opacity=0.3] (current page.center) circle (4cm);
        \node[align=center] at (current page.center) {{
            {{\LARGE\bfseries\textcolor{{purpleblue}}{{{safe}}}}} \\[0.5cm]
            {{\Large\itshape\textcolor{{lightText}}{{Excellence in SAT Prep}}}}
        }};
        \foreach \x in {{1,2,3,4,5}} {{
            \fill[purpleblue, opacity=0.2] (rand*10-5, rand*7-3.5) circle (0.1+\x*0.05);
        }}
    \end{{tikzpicture}}
\end{{frame}}

"""


def practice_divider() -> str:
    return r"""
\begin{frame}
\section{Practice}
    \begin{tikzpicture}[remember picture, overlay]
        \shade[top color=softPurple, bottom color=softGray]
            (current page.north west) rectangle (current page.south east);
        \fill[white, opacity=0.3] (current page.center) circle (4cm);
        \node[align=center] at (current page.center) {
            {\LARGE\bfseries\textcolor{purpleblue}{Practice}} \\[0.5cm]
            {\Large\itshape\textcolor{lightText}{Excellence in SAT Prep}}
        };
        \foreach \x in {1,2,3,4,5} {
            \fill[purpleblue, opacity=0.2] (rand*10-5, rand*7-3.5) circle (0.1+\x*0.05);
        }
    \end{tikzpicture}
\end{frame}

"""


def closing_frame() -> str:
    return r"""
\begin{frame}{}
    \begin{tikzpicture}[remember picture, overlay]
        \shade[top color=novelPurple!40, bottom color=white]
            (current page.north west) rectangle (current page.south east);
        \fill[white, opacity=0.15] (current page.center) circle (5cm);
        \foreach \x in {1,2,3,4,5} {
            \fill[novelPurple, opacity=0.12] (rand*10-5, rand*7-3.5) circle (0.1+\x*0.05);
        }
    \end{tikzpicture}
    \centering
    \vspace{5em}
    {\Huge \textbf{\textcolor{novelPurple}{Thank You!}}} \\[1em]
    {\large \textcolor{gray}{We appreciate your time and focus.}} \\[3em]
    {\LARGE \textbf{\textcolor{novelPurple}{\textsf{Novel Prep}}}}
    \vfill
\end{frame}

\end{document}
"""


def answer_frame(
    title: str,
    canonical: str,
    alternates: list[str],
    has_mcq: bool,
    hint: str | None = None,
) -> str:
    lines = [rf"\begin{{frame}}{{Answer: {title}}}"]
    if hint:
        lines.append(rf"\textit{{Strategy:}} {hint}")
        lines.append("")
    if is_mcq_letter(canonical):
        lines.append(rf"\textbf{{Correct Answer:}} \( \boxed{{{canonical.upper()}}} \)")
    else:
        lines.append(r"\textbf{Solution:}")
        lines.append(rf"\[ \boxed{{{canonical}}} \]")
        if alternates:
            alt = ", ".join(alternates)
            lines.append(rf"\textit{{Also accept: {alt}}}")
        lines.append(r"\textbf{Correct Answer:} \( \boxed{" + canonical + r"} \)")
    lines.append("\n\\end{frame}\n")
    return "\n".join(lines)


def unit41_pdf_practice_slides() -> list[str]:
    """Practice section matched to the uploaded SAT 4.1 source PDF."""
    return [
        r"""
\begin{frame}{Cube Problem}
\textbf{Question:}

The surface area, in square inches, of a cube can be represented by the expression $24a^2$, where $a$ is a positive constant.
Which expression represents the volume, in cubic inches, of the cube?

\begin{itemize}
    \item[A)] $8a^3$
    \item[B)] $16a^3$
    \item[C)] $64a^6$
    \item[D)] $216a^6$
\end{itemize}
\end{frame}
""",
        r"""
\begin{frame}{Solution}
\textbf{Solution:}
\begin{itemize}
    \item Let $s$ be the side length of the cube.
    \item The surface area is $6s^2=24a^2$.
    \[
    s^2=\dfrac{24a^2}{6}=4a^2
    \]
    \[
    s=2a
    \]
    \item The volume is
    \[
    V=s^3=(2a)^3=8a^3
    \]
\end{itemize}

\textbf{Answer:} $\boxed{8a^3}$ (Choice A)
\end{frame}
""",
        r"""
\begin{frame}{Volume of a Cylinder}
\textbf{Question:}

Given the function $f(x)=\pi x^3+\pi x^2$, where $f$ represents the volume (in cubic feet) of a right circular cylinder with radius $x$ feet, which expression represents the height (in feet) of the cylinder?

\begin{itemize}
    \item[A)] $x+1$
    \item[B)] $\pi x^3$
    \item[C)] $x$
    \item[D)] $x^3+1$
\end{itemize}
\end{frame}
""",
        r"""
\begin{frame}{Solution}
\textbf{Solution:}
\begin{itemize}
    \item The volume of a right circular cylinder is
    \[
    V=\pi r^2h
    \]
    \item Since the radius is $x$, factor the expression:
    \[
    f(x)=\pi x^3+\pi x^2=\pi x^2(x+1)
    \]
    \item Therefore $r=x$ and $h=x+1$.
\end{itemize}

\textbf{Answer:} $\boxed{x+1}$ (Choice A)
\end{frame}
""",
        r"""
\begin{frame}{Rectangle Perimeter Problem}
\textbf{Question:}

Identical rectangles $X$ and $Y$ each have an area of $\dfrac{49}{5}$ square meters and a perimeter of $P$ meters.
If one of the shorter sides of rectangle $X$ is glued to one of the shorter sides of rectangle $Y$, the resulting rectangle has a perimeter of $\dfrac{14}{9}P$ meters.
What is the value of $P$?
\end{frame}
""",
        r"""
\begin{frame}{Solution}
\footnotesize
\textbf{Solution:}
\begin{itemize}
    \item Let $\ell$ and $w$ be the length and width of each rectangle.
    \[
    \ell w=\dfrac{49}{5}, \qquad 2(\ell+w)=P
    \]
    \item When two rectangles are glued along the shorter side, the new perimeter is
    \[
    2(\ell+2w)
    \]
    \item Given:
    \[
    2(\ell+2w)=\dfrac{14}{9}P
    \]
    \item Substitute $P=2(\ell+w)$:
    \[
    \ell+2w=\dfrac{14}{9}(\ell+w)
    \]
    \[
    9\ell+18w=14\ell+14w
    \]
    \[
    4w=5\ell
    \]
\end{itemize}
\end{frame}
""",
        r"""
\begin{frame}{Solution}
\footnotesize
\begin{itemize}
    \item From $4w=5\ell$, we get $w=\dfrac{5\ell}{4}$.
    \[
    \ell\left(\dfrac{5\ell}{4}\right)=\dfrac{49}{5}
    \]
    \[
    \dfrac{5\ell^2}{4}=\dfrac{49}{5}
    \]
    \[
    \ell^2=\dfrac{196}{25}, \qquad \ell=\dfrac{14}{5}
    \]
    \item Then
    \[
    w=\dfrac{5\ell}{4}=\dfrac{14}{4}=3.5
    \]
    \item Therefore
    \[
    P=2(\ell+w)=2\left(\dfrac{14}{5}+\dfrac{7}{2}\right)
    =2\left(\dfrac{63}{10}\right)=12.6
    \]
\end{itemize}

\textbf{Answer:} $\boxed{12.6}$
\end{frame}
""",
    ]


def build_unit41_pdf_matched(out_file: str, unit: str, section_title: str) -> None:
    """Build 4.1 around the user's uploaded source courseware structure."""
    slides = CONCEPT_SLIDES[unit]
    parts = [preamble(unit, section_title)]
    parts.append(section_divider("Perimeter and Area"))
    parts.extend(slides[0:2])
    parts.append(section_divider("Volume"))
    parts.extend(slides[2:7])
    parts.append(section_divider("Density"))
    parts.extend(slides[7:9])
    parts.append(section_divider("Ratio of Length, Area, and Volume"))
    parts.extend(slides[9:])
    parts.append(
        r"""
\begin{frame}{Question: Ratio of Length, Area, and Volume}
Suppose a cube has an original edge length of $2$ cm, and we scale it up by a factor of $k=3$.
How do the length, area, and volume change under this transformation?

\vspace{0.3cm}
\begin{itemize}
    \item[A)] Length scales by $k$, area by $k^2$, volume by $k^3$.
    \item[B)] Length scales by $k^2$, area by $k^3$, volume by $k^4$.
    \item[C)] Length scales by $k$, area by $k^3$, volume by $k^2$.
    \item[D)] Length scales by $k^3$, area by $k^2$, volume by $k$.
\end{itemize}
\end{frame}

\begin{frame}{Answer Explanation: Ratio of Length, Area, and Volume}
\textbf{Correct Answer:} \textcolor{novelPurple}{$\mathbf{k,\ k^2,\ k^3}$}

\vspace{0.2cm}
When a shape is scaled by factor $k$:
\begin{itemize}
    \item Length scales by $k$.
    \item Area scales by $k^2$.
    \item Volume scales by $k^3$.
\end{itemize}

\textbf{Final Answer:} $\boxed{k,\ k^2,\ k^3}$.
\end{frame}

\begin{frame}{Question: Finding the Volume of a Cube}
A cube has a surface area of $54$ square meters. What is the volume, in cubic meters, of the cube?

\begin{itemize}
    \item[A.] 18
    \item[B.] 27
    \item[C.] 36
    \item[D.] 81
\end{itemize}
\end{frame}

\begin{frame}{Answer Explanation: Finding the Volume of a Cube}
\textbf{Correct Answer:} \textcolor{novelPurple}{$\mathbf{B}$}

\vspace{0.2cm}
\[
6s^2=54 \quad \Rightarrow \quad s^2=9 \quad \Rightarrow \quad s=3
\]
\[
V=s^3=3^3=27
\]

\textbf{Final Answer:} $\boxed{27}$.
\end{frame}

\begin{frame}{Key Takeaways}
\begin{itemize}
    \item Memorize perimeter, area, and volume formulas.
    \item Length, area, and volume scale differently.
    \item SAT geometry often asks you to combine formulas with ratios.
\end{itemize}

\vfill
\centering
\textcolor{novelPurple}{\Huge \textbf{Practice Makes Perfect!}}
\end{frame}
"""
    )
    parts.append(practice_divider())
    parts.extend(unit41_pdf_practice_slides())
    parts.append(closing_frame())
    out_path = ROOT / out_file
    out_path.write_text("".join(parts), encoding="utf-8")
    print(f"Wrote {out_path} (matched uploaded 4.1 PDF)")


def pdf_source_extra_slides(unit: str, key: str) -> list[str]:
    """Small source-PDF concept slides not covered by the question-bank material."""
    if unit == "4.2" and key == "line":
        return [
            r"""
\begin{frame}{Definition of Line, Segment, and Ray}
\begin{itemize}
    \item \textbf{Line:} a straight arrangement of points extending infinitely in both directions.
    \item \textbf{Segment:} part of a line with two endpoints.
    \item \textbf{Ray:} part of a line with one endpoint extending infinitely in one direction.
\end{itemize}
\end{frame}
"""
        ]
    if unit == "4.3" and key == "radian":
        return [
            r"""
\begin{frame}{Understanding Radian Measure}
\textbf{Definition:} one radian is the angle created when arc length equals radius.
\[
\theta=\dfrac{s}{r}
\]
where $s$ is arc length and $r$ is radius.

\vspace{0.2cm}
\[
360^\circ=2\pi \text{ radians}
\]
\[
\theta_{\text{rad}}=\theta^\circ\cdot\dfrac{\pi}{180},
\qquad
\theta^\circ=\theta_{\text{rad}}\cdot\dfrac{180}{\pi}
\]
\end{frame}
""",
            r"""
\begin{frame}{Common Degree-Radian Conversions}
\begin{center}
\begin{tabular}{c|c}
Degrees & Radians \\
\hline
$30^\circ$ & $\dfrac{\pi}{6}$ \\
$45^\circ$ & $\dfrac{\pi}{4}$ \\
$60^\circ$ & $\dfrac{\pi}{3}$ \\
$90^\circ$ & $\dfrac{\pi}{2}$ \\
$180^\circ$ & $\pi$ \\
$360^\circ$ & $2\pi$
\end{tabular}
\end{center}
\end{frame}
""",
        ]
    if unit == "4.3" and key == "unit_circle":
        return [
            r"""
\begin{frame}{Trigonometric Ratios in the Unit Circle}
On the unit circle, a point at angle $\theta$ has coordinates:
\[
(\cos\theta,\ \sin\theta)
\]

\vspace{0.2cm}
\[
\tan\theta=\dfrac{\sin\theta}{\cos\theta}
\]

\textbf{SAT move:} connect right-triangle ratios to unit-circle coordinates.
\end{frame}
"""
        ]
    if unit == "4.4" and key == "arc":
        return [
            r"""
\begin{frame}{Arc Length of a Circle}
When $\theta$ is measured in radians:
\[
s=r\theta
\]
where $s$ is arc length and $r$ is radius.

\vspace{0.2cm}
\textbf{Example:} If $r=6$ and $\theta=60^\circ=\dfrac{\pi}{3}$,
\[
s=6\cdot\dfrac{\pi}{3}=2\pi
\]

\textbf{SAT Tip:} use $s=r\theta$ only when $\theta$ is in radians.
\end{frame}
""",
            r"""
\begin{frame}{Area of a Sector}
Radians:
\[
\text{Area}=\dfrac{1}{2}r^2\theta
\]

Degrees:
\[
\text{Area}=\dfrac{\theta^\circ}{360^\circ}\cdot \pi r^2
\]

\vspace{0.2cm}
\textbf{Example:} radius $4$, angle $45^\circ$:
\[
\dfrac{45}{360}\cdot\pi(4)^2=2\pi
\]
\end{frame}
""",
        ]
    return []


def source_matched_intro_parts(unit: str, section_title: str) -> list[str] | None:
    slides = CONCEPT_SLIDES.get(unit, [])
    parts = [preamble(unit, section_title)]
    if unit == "4.2":
        parts.append(section_divider("Line"))
        parts.extend(pdf_source_extra_slides(unit, "line"))
        parts.append(section_divider("Angle"))
        parts.extend(slides[0:2])
        parts.append(section_divider("Triangle"))
        parts.extend(slides[2:])
        return parts
    if unit == "4.3":
        parts.append(section_divider("Trigonometric Ratios of Acute Angles"))
        parts.extend(slides)
        parts.append(section_divider("Radian Measure"))
        parts.extend(pdf_source_extra_slides(unit, "radian"))
        parts.append(section_divider("Trigonometric In Unit Circle"))
        parts.extend(pdf_source_extra_slides(unit, "unit_circle"))
        return parts
    if unit == "4.4":
        parts.append(section_divider("Arc Length and Area of a Sector"))
        parts.extend(pdf_source_extra_slides(unit, "arc"))
        parts.append(section_divider("Properties of the Circle"))
        parts.extend(slides[2:6])
        parts.append(section_divider("Equation of a Circle in XY-Plane"))
        parts.extend(slides[0:2])
        parts.append(section_divider("Properties of the Circle"))
        parts.extend(slides[6:])
        return parts
    return None


def build_section(
    bank_file: str,
    out_file: str,
    unit: str,
    section_title: str,
    topic_key: str,
    answers: list,
) -> None:
    bank_path = BANKS / bank_file
    bank_tex = bank_path.read_text(encoding="utf-8")
    questions = split_questions(bank_tex)
    if len(questions) != len(answers):
        raise ValueError(
            f"{bank_file}: {len(questions)} questions vs {len(answers)} answers"
        )

    parts = [preamble(unit, section_title)]
    source_parts = source_matched_intro_parts(unit, section_title)
    if source_parts is not None:
        parts = source_parts
    else:
        parts.append(section_divider(section_title))
        parts.extend(CONCEPT_SLIDES.get(unit, []))
    parts.append(practice_divider())

    topic_hints = ANSWER_HINTS.get(topic_key, [])

    for i, (q_body, ans_entry) in enumerate(zip(questions, answers)):
        canonical, alternates = normalize_answer(ans_entry)
        body = transform_body(q_body)
        q_title = first_line(body)
        has_mcq = bool(re.search(r"\\begin\{itemize\}", body)) or r"\item[\textbf{A.}]" in body
        hint = topic_hints[i] if i < len(topic_hints) else None
        parts.append(rf"\begin{{frame}}{{Question: {q_title}}}" + "\n")
        parts.append(body)
        parts.append("\n\\end{frame}\n")
        parts.append(answer_frame(q_title, canonical, alternates, has_mcq, hint))

    parts.append(closing_frame())
    out_path = ROOT / out_file
    out_path.write_text("".join(parts), encoding="utf-8")
    print(f"Wrote {out_path} ({len(questions)} Q/A pairs)")


def main() -> None:
    supplement = load_supplement()
    answers_by_topic = supplement["answers_by_topic"]

    print("Preparing Unit 4 figure assets …")
    ensure_pdf_raster_figures()

    for bank_file, out_file, unit, title in SECTIONS:
        topic_key = bank_file.replace(".tex", "")
        print(f"Building {out_file} …")
        build_section(
            bank_file,
            out_file,
            unit,
            title,
            topic_key,
            answers_by_topic[topic_key],
        )


if __name__ == "__main__":
    main()
