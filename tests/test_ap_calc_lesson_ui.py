"""AP Calculus lesson UI regression tests (Phases 1–15)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATERIALS = ROOT / "data" / "ap_calc_materials.json"
LESSON_UI_CSS = ROOT / "static" / "ap_calc" / "ap_calc_lesson_ui.css"
LESSON_UI_JS = ROOT / "static" / "ap_calc" / "ap_calc_lesson_ui.js"
COURSE_MATERIALS_JS = ROOT / "static" / "course_materials.js"
MATH_LAB_JS = ROOT / "static" / "ap_calc" / "ap_calc_math_lab.js"
TEMPLATE = ROOT / "templates" / "course_material_view.html"
BASE_TEMPLATE = ROOT / "templates" / "base.html"


def _lesson_html(slug: str) -> str:
    from app import app

    with app.app_context():
        from app import get_db, init_db

        init_db()
        row = get_db().execute("SELECT id FROM users WHERE is_active=1 LIMIT 1").fetchone()
    client = app.test_client()
    with client.session_transaction() as sess:
        if row:
            sess["user_id"] = row["id"]
    return client.get(f"/ap/calc/materials/{slug}").get_data(as_text=True)


class LessonUIAssetTests(unittest.TestCase):
    def test_design_tokens_in_css(self) -> None:
        css = LESSON_UI_CSS.read_text(encoding="utf-8")
        for token in ("--space-1", "--space-8", "--ap-cm-path-compact: 68px", "--ap-content-read"):
            self.assertIn(token, css)

    def test_rail_padding_includes_24px_buffer(self) -> None:
        css = LESSON_UI_CSS.read_text(encoding="utf-8")
        self.assertIn("calc(4.75rem + 24px)", css)

    def test_resume_banner_dismissed_class(self) -> None:
        css = LESSON_UI_CSS.read_text(encoding="utf-8")
        self.assertIn(".ap-resume-banner.is-dismissed", css)
        js = COURSE_MATERIALS_JS.read_text(encoding="utf-8")
        self.assertIn("is-dismissed", js)

    def test_go_navigation_consumes_resume(self) -> None:
        js = COURSE_MATERIALS_JS.read_text(encoding="utf-8")
        self.assertIn("function go(delta)", js)
        self.assertIn("consumeResumeBanner()", js)

    def test_ap_calc_skips_auto_path_open(self) -> None:
        js = COURSE_MATERIALS_JS.read_text(encoding="utf-8")
        self.assertIn("np-cm-viewer--ap-calc", js)
        self.assertIn("!root.classList.contains(\"np-cm-viewer--ap-calc\")", js)

    def test_phase_stepper_in_template(self) -> None:
        tpl = TEMPLATE.read_text(encoding="utf-8")
        for phase in ("Understand", "Learn", "Investigate", "Explain"):
            self.assertIn(phase, tpl)
        self.assertIn("data-ap-phase-stepper", tpl)

    def test_path_mode_controls(self) -> None:
        tpl = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("data-ap-path-mode", tpl)
        js = LESSON_UI_JS.read_text(encoding="utf-8")
        self.assertIn("setPathMode", js)

    def test_course_dropdown_closed_by_default(self) -> None:
        tpl = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("data-cm-course-menu hidden", tpl)

    def test_body_class_for_ap_lesson(self) -> None:
        tpl = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("is-ap-calc-lesson", tpl)
        base = BASE_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("block body_class", base)

    def test_global_nav_track_switcher_hidden_on_ap_lesson(self) -> None:
        css = LESSON_UI_CSS.read_text(encoding="utf-8")
        self.assertIn("body.is-ap-calc-lesson .track-switcher", css)
        self.assertIn("display: none", css)

    def test_projector_hides_chrome(self) -> None:
        css = LESSON_UI_CSS.read_text(encoding="utf-8")
        self.assertIn("body.is-cm-projector", css)

    def test_structured_lesson_state_in_math_lab(self) -> None:
        js = MATH_LAB_JS.read_text(encoding="utf-8")
        self.assertIn("buildStructuredLessonState", js)
        self.assertIn("currentPhase", js)
        self.assertIn("misconceptionTags", js)

    def test_graph_notice_in_materials(self) -> None:
        data = json.loads(MATERIALS.read_text(encoding="utf-8"))
        lesson = next(m for m in data["materials"] if m["slug"] == "ap-1-2-defining-limits")
        slide4 = next(s for s in lesson["slides"] if s["index"] == 4)
        self.assertIn("What to notice", slide4["html"])

    def test_investigate_gate_in_materials(self) -> None:
        data = json.loads(MATERIALS.read_text(encoding="utf-8"))
        lesson = next(m for m in data["materials"] if m["slug"] == "ap-1-3-limits-from-graphs")
        slide5 = next(s for s in lesson["slides"] if s["index"] == 5)
        self.assertIn("Start investigation", slide5["html"])
        self.assertIn("data-ap-explore-panel", slide5["html"])

    def test_mastery_tooltip_on_ring(self) -> None:
        html = _lesson_html("ap-1-1-instantaneous-change")
        self.assertIn("Mastery is based on scored work", html)

    def test_lesson_pages_load_with_ui_assets(self) -> None:
        from app import app

        with app.app_context():
            from app import get_db, init_db

            init_db()
            row = get_db().execute("SELECT id FROM users WHERE is_active=1 LIMIT 1").fetchone()
        client = app.test_client()
        with client.session_transaction() as sess:
            if row:
                sess["user_id"] = row["id"]
        for slug in (
            "ap-1-1-instantaneous-change",
            "ap-1-2-defining-limits",
            "ap-1-3-limits-from-graphs",
        ):
            rv = client.get(f"/ap/calc/materials/{slug}")
            self.assertEqual(200, rv.status_code)
            html = rv.get_data(as_text=True)
            self.assertIn("ap_calc_lesson_ui.css", html)
            self.assertIn("ap_calc_lesson_ui.js", html)
            self.assertIn("is-ap-calc-lesson", html)

    def test_tracer_math_regression_node(self) -> None:
        script = r"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync(process.argv[process.argv.length - 1], 'utf8');
const sandbox = { window: {}, global: {}, document: { readyState: 'complete', addEventListener: function () {} }, matchMedia: () => ({ matches: false }) };
sandbox.window = sandbox.global = sandbox;
vm.runInNewContext(code, sandbox);
const lab = sandbox.ApCalcMathLab;
console.log(JSON.stringify({
  y199: lab.evaluateHoleWithValue(1.99),
  y1999: lab.evaluateHoleWithValue(1.999),
  y201: lab.evaluateHoleWithValue(2.01),
  y2001: lab.evaluateHoleWithValue(2.001),
  phase: lab.phaseFromLabStep(0),
}));
"""
        out = subprocess.run(
            ["node", "-e", script, str(MATH_LAB_JS)],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        )
        data = json.loads(out.stdout.strip())
        self.assertAlmostEqual(data["y199"], 2.99, places=2)
        self.assertAlmostEqual(data["y1999"], 2.999, places=3)
        self.assertAlmostEqual(data["y201"], 2.99, places=2)
        self.assertAlmostEqual(data["y2001"], 2.999, places=3)
        self.assertEqual(data["phase"], "understand")

    def test_hints_no_h_zero_in_12_13(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        from ap_calc_tutor_engine import TUTOR_HINT_LEVELS

        for lid in ("1.2", "1.3"):
            for entry in TUTOR_HINT_LEVELS.get(lid, []):
                self.assertNotIn("h = 0", entry.get("text", "").lower())


if __name__ == "__main__":
    unittest.main()
