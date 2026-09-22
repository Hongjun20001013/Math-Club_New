"""Production regression tests for AP Calc 1.2 #4 and 1.3 #5 labs."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from ap_calc_math_lab_specs import (  # noqa: E402
    limit_cases_lab_12,
    tracer_lab_13_worked_example,
)
from ap_calc_tutor_engine import (  # noqa: E402
    TUTOR_HINT_LEVELS,
    contextual_hints_for_spec,
)
from course_materials_progress import (  # noqa: E402
    ap_calc_mastery_from_progress,
    ap_calc_progress_from_progress,
)

MATERIALS_PATH = ROOT / "data" / "ap_calc_materials.json"
MATH_LAB_JS = ROOT / "static" / "ap_calc" / "ap_calc_math_lab.js"


def _node_tracer_probe() -> dict:
    script = r"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync(process.argv[1], 'utf8');
const sandbox = {
  window: {},
  global: {},
  document: { readyState: 'complete', addEventListener: function () {} },
  matchMedia: () => ({ matches: true }),
};
sandbox.window = sandbox.global = sandbox;
vm.runInNewContext(code, sandbox);
const lab = sandbox.ApCalcMathLab;
const c = 2;
const eps = lab.TRACER_EPS;
const leftX = lab.approachEndpoint(c, 'left', null);
const rightX = lab.approachEndpoint(c, 'right', null);
console.log(JSON.stringify({
  leftX,
  rightX,
  leftRead: lab.formatApproachX(leftX, c, 'left'),
  rightRead: lab.formatApproachX(rightX, c, 'right'),
  leftLtC: leftX < c,
  rightGtC: rightX > c,
  leftNotTwo: !lab.formatApproachX(leftX, c, 'left').includes('x = 2.00'),
  rightNotTwo: !lab.formatApproachX(rightX, c, 'right').includes('x = 2.00'),
}));
"""
    out = subprocess.run(
        ["node", "-e", script, str(MATH_LAB_JS)],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    return json.loads(out.stdout.strip())


def _extract_worked_example_spec(materials: dict) -> dict:
    lesson = next(m for m in materials["materials"] if m["slug"] == "ap-1-3-limits-from-graphs")
    slide = lesson["slides"][4]
    assert "Worked example" in slide.get("title", "") or "piecewise" in slide.get("html", "").lower()
    html = slide["html"]
    start = html.index('{"id":"one-sided-tracer-13"')
    end = html.index("</script>", start)
    return json.loads(html[start:end])


class ProductionRegressionTests(unittest.TestCase):
    def test_slide_13_5_defaults_hole_with_value(self):
        spec = tracer_lab_13_worked_example()
        self.assertEqual(spec["initialScenarioId"], "hole-with-value")
        self.assertFalse(spec["showScenarioTabs"])
        idx = next(i for i, s in enumerate(spec["scenarios"]) if s["id"] == "hole-with-value")
        self.assertEqual(idx, 2)

    def test_open_circle_at_2_3_filled_at_2_1_5(self):
        spec = tracer_lab_13_worked_example()
        sc = next(s for s in spec["scenarios"] if s["id"] == "hole-with-value")
        self.assertEqual(sc["openPoints"][0], {"x": 2, "y": 3})
        self.assertEqual(sc["closedPoints"][0], {"x": 2, "y": 1.5})

    def test_materials_json_embeds_hole_with_value(self):
        materials = json.loads(MATERIALS_PATH.read_text(encoding="utf-8"))
        spec = _extract_worked_example_spec(materials)
        self.assertEqual(spec["initialScenarioId"], "hole-with-value")

    def test_tracers_strictly_off_c(self):
        probe = _node_tracer_probe()
        self.assertLess(probe["leftX"], 2)
        self.assertGreater(probe["rightX"], 2)
        self.assertTrue(probe["leftNotTwo"])
        self.assertTrue(probe["rightNotTwo"])

    def test_tracers_approach_y_three_not_fc(self):
        probe = _node_tracer_probe()
        self.assertAlmostEqual(probe["leftX"] + 1, 3, places=2)
        self.assertAlmostEqual(-probe["rightX"] + 5, 3, places=2)

    def test_hints_12_and_13_no_h_zero(self):
        for lesson_id in ("1.2", "1.3"):
            for entry in TUTOR_HINT_LEVELS[lesson_id]:
                self.assertNotIn("h = 0", entry["text"].lower())
                self.assertNotIn("h=0", entry["text"].lower())
        for slide_id in ("1.2-4", "1.3-5"):
            ch = contextual_hints_for_spec({"slideId": slide_id})
            for entry in ch.get("sequence", []):
                self.assertNotIn("h = 0", entry["text"].lower())
            for entry in ch.get("caseOverrides", {}).values():
                self.assertNotIn("h = 0", entry["text"].lower())

    def test_math_lab_js_no_global_h_zero_hint(self):
        text = MATH_LAB_JS.read_text(encoding="utf-8")
        self.assertNotIn("do not jump to h = 0", text.lower())
        self.assertNotIn("focus on what changes as you approach", text.lower())

    def test_zero_challenges_zero_mastery(self):
        progress = {"viewed": [1, 2, 3, 4, 5], "done": [], "lab": {"events": [{"eventType": "tracer_moved"}] * 20}}
        mastery = ap_calc_mastery_from_progress(progress, slide_count=20, checkpoint_count=6)
        self.assertEqual(mastery, 0)
        browse_progress = ap_calc_progress_from_progress(progress, slide_count=20, challenge_count=6)
        self.assertEqual(browse_progress, 0)

    def test_lesson_12_four_cases_spec_has_slide_id(self):
        spec = limit_cases_lab_12()
        self.assertEqual(spec["slideId"], "1.2-4")
        self.assertTrue(spec.get("contextualHints", {}).get("sequence"))


if __name__ == "__main__":
    unittest.main()
