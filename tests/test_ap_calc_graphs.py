"""Tests for AP Calc static graph SVG generation."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from ap_calc_graphs import (  # noqa: E402
    _format_tick,
    _tick_values,
    build_all_graphs,
)


class GraphTickTests(unittest.TestCase):
    def test_tick_values_cover_range(self):
        ticks = _tick_values(0, 6, 5)
        self.assertGreaterEqual(ticks[0], 0)
        self.assertLessEqual(ticks[-1], 6)
        self.assertGreaterEqual(len(ticks), 3)

    def test_format_tick_integers(self):
        self.assertEqual(_format_tick(3.0), "3")
        self.assertEqual(_format_tick(0.0), "0")

    def test_jump_graph_has_numeric_axis_labels(self):
        paths = build_all_graphs()
        svg_path = ROOT / "static" / "ap_calc" / "figures" / "jump_at_3.svg"
        self.assertTrue(svg_path.exists())
        text = svg_path.read_text(encoding="utf-8")
        self.assertIn('fill="#4c3d99">2</text>', text)
        self.assertIn('fill="#4c3d99">-2</text>', text)
        self.assertIn('fill="#4c3d99">0</text>', text)
        self.assertIn(paths["jump_at_3"], "/static/ap_calc/figures/jump_at_3.svg")


if __name__ == "__main__":
    unittest.main()
