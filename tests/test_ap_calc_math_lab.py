"""Tests for AP Calculus Interactive Math Lab core math."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from ap_calc_math_lab_specs import (  # noqa: E402
    limit_cases_lab_12,
    secant_lab_11,
    spec_json,
    tracer_lab_13,
)
from ap_calc_slide_helpers import case_model_from_spec, visual_cases_gallery_12  # noqa: E402


def s(t: float) -> float:
    return t * t + 1


def secant_slope(a: float, h: float) -> float:
    return (s(a + h) - s(a)) / h


class SecantMathTests(unittest.TestCase):
    def test_slope_formula_at_t2(self):
        a = 2
        for h in [-1, -0.5, -0.1, -0.01, 0.01, 0.1, 0.5, 1]:
            self.assertAlmostEqual(secant_slope(a, h), 4 + h, places=6)

    def test_h_01_values(self):
        h = 0.1
        delta_s = s(2.1) - s(2)
        self.assertAlmostEqual(delta_s, 0.41, places=6)
        self.assertAlmostEqual(secant_slope(2, h), 4.1, places=6)

    def test_h_neg_01_values(self):
        h = -0.1
        delta_s = s(1.9) - s(2)
        self.assertAlmostEqual(delta_s, -0.39, places=6)
        self.assertAlmostEqual(secant_slope(2, h), 3.9, places=6)

    def test_both_approach_four(self):
        left = secant_slope(2, -0.01)
        right = secant_slope(2, 0.01)
        self.assertAlmostEqual(left, 3.99, places=6)
        self.assertAlmostEqual(right, 4.01, places=6)

    def test_h_zero_excluded_from_spec(self):
        spec = secant_lab_11()
        self.assertIn(0, spec["excludedValues"])
        self.assertNotIn(0, spec["allowedValues"])


class LimitCaseTests(unittest.TestCase):
    def test_unequal_one_sided_dne(self):
        cases = limit_cases_lab_12()["cases"]
        case_d = next(c for c in cases if c["id"] == "case-d")
        self.assertNotEqual(case_d["leftLimit"], case_d["rightLimit"])
        self.assertIsNone(case_d["twoSidedLimit"])

    def test_filled_point_does_not_change_limit_case_b(self):
        case_b = next(c for c in limit_cases_lab_12()["cases"] if c["id"] == "case-b")
        self.assertEqual(case_b["twoSidedLimit"], 5)
        self.assertEqual(case_b["functionValue"], 10)

    def test_endpoint_one_sided(self):
        scenarios = tracer_lab_13()["scenarios"]
        endpoint = next(s for s in scenarios if s["id"] == "endpoint")
        self.assertIsNone(endpoint["leftLimit"])
        self.assertEqual(endpoint["rightLimit"], 0)


class CaseModelTests(unittest.TestCase):
    def test_case_a_model_shows_limit_and_fc(self):
        case_a = next(c for c in limit_cases_lab_12()["cases"] if c["id"] == "case-a")
        html = case_model_from_spec(case_a)
        self.assertIn("lim", html)
        self.assertIn("f(3) = 5", html)

    def test_case_d_model_is_jump_layout(self):
        case_d = next(c for c in limit_cases_lab_12()["cases"] if c["id"] == "case-d")
        html = case_model_from_spec(case_d)
        self.assertIn("ap-visual-pair--jump", html)
        self.assertIn("DNE", html)
        self.assertIn("f(3) = 0", html)

    def test_gallery_has_four_cards(self):
        html = visual_cases_gallery_12()
        self.assertEqual(html.count("ap-cases-gallery__card"), 4)


class SpecSerializationTests(unittest.TestCase):
    def test_specs_are_json_serializable(self):
        for spec in (secant_lab_11(), limit_cases_lab_12(), tracer_lab_13()):
            payload = spec_json(spec)
            parsed = json.loads(payload)
            self.assertEqual(parsed["id"], spec["id"])


if __name__ == "__main__":
    unittest.main()
