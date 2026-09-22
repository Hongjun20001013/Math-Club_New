"""Tests for AP Calc tutor engine, specs, and tracer constraints."""
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
    secant_lab_11,
    tracer_lab_13,
    tracer_lab_13_worked_example,
)
from ap_calc_tutor_engine import (  # noqa: E402
    MISCONCEPTIONS,
    TUTOR_HINT_LEVELS,
    enrich_scenario,
    mastery_from_lab_progress,
    tracer_presets,
)


class TutorHintTests(unittest.TestCase):
    def test_13_hints_never_mention_h_zero(self):
        for entry in TUTOR_HINT_LEVELS["1.3"]:
            self.assertNotIn("h = 0", entry["text"].lower())
            self.assertNotIn("h=0", entry["text"].lower())

    def test_11_hints_may_mention_h_zero_context(self):
        texts = " ".join(e["text"] for e in TUTOR_HINT_LEVELS["1.1"]).lower()
        self.assertIn("h", texts)

    def test_misconceptions_have_level1_hint(self):
        for tag, meta in MISCONCEPTIONS.items():
            self.assertIn("level1Hint", meta)
            self.assertIn("studentFacingMessage", meta)


class TracerSpecTests(unittest.TestCase):
    def test_worked_example_defaults_hole_filled(self):
        spec = tracer_lab_13_worked_example()
        self.assertEqual(spec["initialScenarioId"], "hole-filled")
        self.assertFalse(spec["showScenarioTabs"])
        idx = next(i for i, s in enumerate(spec["scenarios"]) if s["id"] == "hole-filled")
        sc = spec["scenarios"][idx]
        self.assertEqual(sc["leftLimit"], 3)
        self.assertEqual(sc["rightLimit"], 3)
        self.assertEqual(sc["functionValue"], 1.5)
        self.assertEqual(sc["twoSidedLimit"], 3)

    def test_left_presets_stay_below_c(self):
        sc = enrich_scenario(next(s for s in tracer_lab_13()["scenarios"] if s["id"] == "hole-filled"))
        c = sc["targetX"]
        for x in sc["allowedTracerValues"]["left"]:
            self.assertLess(x, c)

    def test_right_presets_stay_above_c(self):
        sc = enrich_scenario(next(s for s in tracer_lab_13()["scenarios"] if s["id"] == "hole-filled"))
        c = sc["targetX"]
        for x in sc["allowedTracerValues"]["right"]:
            self.assertGreater(x, c)

    def test_filled_point_does_not_change_limit(self):
        sc = next(s for s in tracer_lab_13()["scenarios"] if s["id"] == "hole-filled")
        self.assertEqual(sc["twoSidedLimit"], 3)
        self.assertEqual(sc["functionValue"], 1.5)

    def test_unequal_sides_dne(self):
        sc = next(s for s in tracer_lab_13()["scenarios"] if s["id"] == "jump")
        self.assertNotEqual(sc["leftLimit"], sc["rightLimit"])
        self.assertIsNone(sc["twoSidedLimit"])

    def test_endpoint_one_sided(self):
        sc = next(s for s in tracer_lab_13()["scenarios"] if s["id"] == "endpoint")
        self.assertIsNone(sc["leftLimit"])
        self.assertEqual(sc["rightLimit"], 0)
        left = sc["allowedTracerValues"]["left"]
        self.assertEqual(left, [])

    def test_secant_includes_tiny_h_values(self):
        spec = secant_lab_11()
        self.assertIn(-0.001, spec["allowedValues"])
        self.assertIn(0.001, spec["allowedValues"])
        self.assertNotIn(0, spec["allowedValues"])

    def test_specs_include_tutor_context(self):
        for spec in (secant_lab_11(), tracer_lab_13()):
            self.assertIn("hintLevels", spec)
            self.assertEqual(len(spec["hintLevels"]), 5)


class MasteryTests(unittest.TestCase):
    def test_browse_only_capped(self):
        result = mastery_from_lab_progress({"slidesViewed": 5})
        self.assertLessEqual(result["total"], 40)

    def test_interaction_raises_mastery(self):
        result = mastery_from_lab_progress({
            "objectives": {
                "1.3-hole-filled": {
                    "exposure": 10,
                    "interaction": 20,
                    "guidedSuccess": 20,
                    "independentSuccess": 30,
                    "explanationQuality": 20,
                }
            }
        })
        self.assertGreaterEqual(result["total"], 80)


class SpecJsonTests(unittest.TestCase):
    def test_worked_example_spec_serializes(self):
        payload = json.dumps(tracer_lab_13_worked_example())
        parsed = json.loads(payload)
        self.assertEqual(parsed["initialScenarioId"], "hole-filled")


if __name__ == "__main__":
    unittest.main()
