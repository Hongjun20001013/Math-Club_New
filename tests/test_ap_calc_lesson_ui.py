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

    def test_rail_padding_includes_buffer(self) -> None:
        css = LESSON_UI_CSS.read_text(encoding="utf-8")
        self.assertIn("--ap-cm-rail-h:", css)
        self.assertIn("scroll-padding-bottom: calc(var(--ap-cm-rail-h) + 12px)", css)

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

    def test_phase_stepper_hidden_by_default(self) -> None:
        tpl = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('data-ap-phase-stepper', tpl)
        self.assertIn('data-ap-phase-stepper aria-label="Learning phases" hidden', tpl)

    def test_dropdown_menu_high_z_index(self) -> None:
        css = LESSON_UI_CSS.read_text(encoding="utf-8")
        self.assertIn("z-index: 140", css)

    def test_chrome_allows_dropdown_overflow(self) -> None:
        css = LESSON_UI_CSS.read_text(encoding="utf-8")
        self.assertIn(".np-cm-viewer--ap-calc .ap-lesson-chrome", css)
        self.assertIn("overflow: visible", css)
        self.assertNotIn("max-height: 148px", css)

    def test_slide_templates_in_materials(self) -> None:
        data = json.loads(MATERIALS.read_text(encoding="utf-8"))
        templates = set()
        for mat in data["materials"]:
            for slide in mat["slides"]:
                templates.add(slide.get("template"))
        self.assertEqual(
            templates,
            {"intro", "concept", "investigation", "worked-example", "practice", "summary"},
        )

    def test_intro_simplified_without_flow_meta(self) -> None:
        data = json.loads(MATERIALS.read_text(encoding="utf-8"))
        lesson = next(m for m in data["materials"] if m["slug"] == "ap-1-2-defining-limits")
        intro = lesson["slides"][0]["html"]
        self.assertNotIn("cm-intro-meta", intro)
        self.assertIn("ap-slide-template--intro", intro)

    def test_strategy_collapsed_in_practice(self) -> None:
        data = json.loads(MATERIALS.read_text(encoding="utf-8"))
        lesson = next(m for m in data["materials"] if m["slug"] == "ap-1-1-instantaneous-change")
        practice = next(s for s in lesson["slides"] if s.get("kind") == "question")
        self.assertIn("cm-strategy-details", practice["html"])
        self.assertNotIn('cm-strategy-chip"><span', practice["html"])

    def test_secant_interval_directed_notation(self) -> None:
        js = MATH_LAB_JS.read_text(encoding="utf-8")
        self.assertIn("formatSecantInterval", js)
        data = json.loads(MATERIALS.read_text(encoding="utf-8"))
        lesson = next(m for m in data["materials"] if m["slug"] == "ap-1-1-instantaneous-change")
        slide = next(s for s in lesson["slides"] if s["index"] == 6)
        self.assertIn("From → To", slide["html"])

    def test_piecewise_in_12_slide_6(self) -> None:
        data = json.loads(MATERIALS.read_text(encoding="utf-8"))
        lesson = next(m for m in data["materials"] if m["slug"] == "ap-1-2-defining-limits")
        slide = next(s for s in lesson["slides"] if s["index"] == 6)
        self.assertIn("begin{cases}", slide["html"])

    def test_12_slide_14_not_blank_optional(self) -> None:
        data = json.loads(MATERIALS.read_text(encoding="utf-8"))
        lesson = next(m for m in data["materials"] if m["slug"] == "ap-1-2-defining-limits")
        slide = next(s for s in lesson["slides"] if s["index"] == 14)
        self.assertNotIn("ap-box--optional", slide["html"])
        self.assertIn("varepsilon", slide["html"])

    def test_13_slide_14_mcq_no_yes_conflict(self) -> None:
        data = json.loads(MATERIALS.read_text(encoding="utf-8"))
        lesson = next(m for m in data["materials"] if m["slug"] == "ap-1-3-limits-from-graphs")
        slide = next(s for s in lesson["slides"] if s["index"] == 14)
        self.assertIn("What is wrong with that reasoning", slide["html"])
        self.assertNotIn("Yes — limits come from branches", slide["html"])

    def test_13_slide_15_one_sided_infinite_limits(self) -> None:
        data = json.loads(MATERIALS.read_text(encoding="utf-8"))
        lesson = next(m for m in data["materials"] if m["slug"] == "ap-1-3-limits-from-graphs")
        slide = next(s for s in lesson["slides"] if s["index"] == 15)
        self.assertIn("L^{-}=-\\infty", slide["html"])
        self.assertIn("L^{+}=+\\infty", slide["html"])

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
        self.assertIn("ap-lesson-chrome__sticky", css)
        self.assertIn("clamp(1.18rem, 1.7vw, 1.72rem)", css)

    def test_projector_keeps_lab_split_horizontal(self) -> None:
        css = LESSON_UI_CSS.read_text(encoding="utf-8")
        self.assertIn("ap-lab-body--tracer", css)
        self.assertNotIn(".is-focus-mode .ap-lab-body--split {\n  grid-template-columns: 1fr;\n}", css)

    def test_projector_focus_event_wired(self) -> None:
        js = COURSE_MATERIALS_JS.read_text(encoding="utf-8")
        ui = LESSON_UI_JS.read_text(encoding="utf-8")
        self.assertIn("np-cm-focus-mode", js)
        self.assertIn("onProjectorChange", ui)
        self.assertIn("data-ap-explore-gate", ui)

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
        self.assertEqual(slide5.get("template"), "investigation")
        slide6 = next(s for s in lesson["slides"] if s["index"] == 6)
        self.assertIn("data-ap-trace-left-slider", slide6["html"])
        self.assertNotIn("data-ap-explore-gate", slide6["html"])

    def test_phase_stepper_sync_in_js(self) -> None:
        js = LESSON_UI_JS.read_text(encoding="utf-8")
        self.assertIn("syncPhaseStepperVisibility", js)
        self.assertIn("phaseStepper.hidden", js)

    def test_intro_slide_body_full_width(self) -> None:
        css = LESSON_UI_CSS.read_text(encoding="utf-8")
        self.assertIn(".np-cm-slide--intro .np-cm-slide-body", css)
        self.assertIn("max-width: none", css)

    def test_tracer_graph_visible_during_predict(self) -> None:
        js = MATH_LAB_JS.read_text(encoding="utf-8")
        self.assertIn("exploreStack.hidden = gatedExplore", js)
        self.assertIn("predictPanel.hidden = !gatedExplore", js)
        self.assertIn("showMarkers = this.predictDone", js)

    def test_unified_lab_protocol_helpers(self) -> None:
        js = MATH_LAB_JS.read_text(encoding="utf-8")
        self.assertIn("function updateLabProtocol", js)
        self.assertIn("SECANT_STEP_LABELS", js)
        self.assertIn("_syncCaseChrome", js)
        self.assertNotIn("GraphCaseSwitcher", js)

    def test_tracer_lab_graph_left_controls_right(self) -> None:
        from ap_calc_slide_helpers import tracer_math_lab_embed
        from ap_calc_math_lab_specs import tracer_lab_13, spec_json

        html = tracer_math_lab_embed(spec_json(tracer_lab_13()), gated=True)
        split_idx = html.index('class="ap-lab-body ap-lab-body--split ap-lab-body--tracer"')
        graph_idx = html.index("ap-lab-main--graph", split_idx)
        aside_idx = html.index('class="ap-lab-side ap-lab-side--action"', split_idx)
        predict_idx = html.index("data-ap-predict-panel", aside_idx)
        dash_idx = html.index("data-ap-dashboard", aside_idx)
        self.assertLess(graph_idx, aside_idx)
        self.assertLess(aside_idx, predict_idx)
        self.assertLess(predict_idx, dash_idx)
        self.assertIn("ap-lab-graph-wrap--primary", html)
        self.assertIn("data-ap-explore-stack", html)
        self.assertIn("ap-lab-bench__head", html)
        self.assertIn("ap-lab-protocol-track", html)
        self.assertIn("data-ap-step-now-text", html)

    def test_secant_lab_protocol_dashboard(self) -> None:
        from ap_calc_slide_helpers import secant_math_lab_embed
        from ap_calc_math_lab_specs import secant_lab_11, spec_json

        html = secant_math_lab_embed(spec_json(secant_lab_11()))
        split_idx = html.index('class="ap-lab-body ap-lab-body--split ap-lab-body--secant"')
        graph_idx = html.index("ap-lab-main--graph", split_idx)
        aside_idx = html.index('class="ap-lab-side ap-lab-side--action"', split_idx)
        predict_idx = html.index("data-ap-predict-panel", aside_idx)
        dash_idx = html.index("data-ap-dashboard", aside_idx)
        self.assertLess(graph_idx, aside_idx)
        self.assertLess(predict_idx, dash_idx)
        self.assertIn("data-d-h", html)
        self.assertIn("data-d-left-est", html)
        self.assertIn("data-d-right-est", html)
        self.assertIn("data-ap-h-presets", html)
        self.assertIn("data-ap-tutor-action", html)
        self.assertNotIn("ap-lab-estimates", html)

    def test_limit_lab_protocol_dashboard(self) -> None:
        from ap_calc_slide_helpers import limit_cases_math_lab_embed
        from ap_calc_math_lab_specs import limit_cases_lab_12, spec_json

        spec = limit_cases_lab_12()
        self.assertEqual(spec["labType"], "OneSidedLimitTracer")
        self.assertEqual(len(spec["scenarios"]), 4)
        html = limit_cases_math_lab_embed(spec_json(spec))
        explore_idx = html.index("ap-lab-body--limit")
        dash_idx = html.index("data-ap-dashboard", explore_idx)
        self.assertIn("data-ap-predict-panel", html)
        self.assertIn("data-ap-trace-left-slider", html)
        self.assertIn("data-ap-lock-left-submit", html)
        self.assertIn("data-d-left", html)
        self.assertIn("data-d-two", html)
        self.assertIn("ap-lab-protocol-track", html)
        self.assertNotIn("data-ap-x-slider", html)

    def test_lab_slide_workstation_mode(self) -> None:
        css = LESSON_UI_CSS.read_text(encoding="utf-8")
        js = LESSON_UI_JS.read_text(encoding="utf-8")
        self.assertIn(".is-lab-slide", css)
        self.assertIn("syncLabSlideLayout", js)
        self.assertIn("ap-lab-bench", css)

    def test_path_open_restores_hidden_mode(self) -> None:
        js = COURSE_MATERIALS_JS.read_text(encoding="utf-8")
        self.assertIn('is-path-hidden") && window.ApCalcLessonUI', js)
        self.assertIn("is-path-drawer-open", js)

    def test_ap_calc_skips_intro_overview_inject(self) -> None:
        js = COURSE_MATERIALS_JS.read_text(encoding="utf-8")
        self.assertIn('kind === "intro" && !root.classList.contains("np-cm-viewer--ap-calc")', js)

    def test_intro_slide_hides_path(self) -> None:
        css = LESSON_UI_CSS.read_text(encoding="utf-8")
        self.assertIn(".is-intro-slide .np-cm-path", css)
        js = LESSON_UI_JS.read_text(encoding="utf-8")
        self.assertIn("syncIntroLayout", js)

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
