"""Regression: pgfplots rational \\addplot curves must not flatten to a secant line."""

from __future__ import annotations

import unittest

from tikz_svg import replace_tikz_with_svg_html

TIKZ = r"""
\begin{tikzpicture}
\begin{axis}[
    axis lines=center,
    xlabel=$x$, ylabel=$y$,
    xmin=-10, xmax=0,
    ymin=-10, ymax=0,
    xtick={-10,-9,...,0},
    ytick={-10,-9,...,0},
    samples=200,
    grid=major,
    domain=-9.9:-3.9,
    restrict y to domain=-10:10
]
\addplot[thick, black] {6 / (x + 4)};
\end{axis}
\end{tikzpicture}
"""


class TikZRationalPlotTests(unittest.TestCase):
    def test_rational_addplot_is_curved_not_two_point_line(self) -> None:
        html = replace_tikz_with_svg_html(TIKZ)
        self.assertIn("stem-tikz-svg", html)
        self.assertGreater(html.count(" L "), 20, "hyperbola should sample many segments")
        self.assertIn('stroke="#4f2fd4"', html)


if __name__ == "__main__":
    unittest.main()
