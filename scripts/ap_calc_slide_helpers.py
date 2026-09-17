"""HTML slide building blocks for AP Calculus course materials."""
from __future__ import annotations

FIG = "/static/ap_calc/figures"


def fig(path: str, caption: str = "", cls: str = "ap-fig--standard", notice: str = "") -> str:
    """Embed a graph. Size classes (use consistently across AP lessons):
    ap-fig--teach — primary slide visual (one graph is the focus)
    ap-fig--standard — supporting illustration
    ap-fig--practice — guided / worked example reference
    ap-fig--gallery — 2×2 comparison card (use *_gallery SVG assets)
    ap-fig--case — 4-across summary strip (use *_thumb SVG assets)
    """
    cap = f'<figcaption class="ap-fig-cap">{caption}</figcaption>' if caption else ""
    notice_html = (
        f'<p class="ap-fig-notice"><strong>What to notice:</strong> '
        f'<span class="ap-fig-notice-math">{notice}</span></p>'
    ) if notice else ""
    return (
        f'<figure class="ap-fig {cls}">'
        f'<img src="{path}" alt="{caption or "Graph"}" loading="lazy"/>'
        f"{cap}{notice_html}</figure>"
    )


def fig_svg_inline(svg_path: str, caption: str = "", notice: str = "") -> str:
    """Reference pre-built SVG by URL (same as fig)."""
    return fig(svg_path, caption, notice=notice)


def big_idea(html: str) -> str:
    return (
        '<div class="ap-box ap-box--big-idea">'
        '<span class="ap-box-label">Big Idea</span>'
        f'<div class="ap-box-body">{html}</div></div>'
    )


def definition(title: str, html: str) -> str:
    return (
        '<div class="ap-box ap-box--definition">'
        f'<span class="ap-box-label">Definition · {title}</span>'
        f'<div class="ap-box-body">{html}</div></div>'
    )


def key_point(title: str, html: str) -> str:
    return (
        '<div class="ap-box ap-box--key">'
        f'<span class="ap-box-label">Key Point · {title}</span>'
        f'<div class="ap-box-body">{html}</div></div>'
    )


def checkpoint(html: str) -> str:
    return (
        '<div class="ap-box ap-box--checkpoint">'
        '<span class="ap-box-label">AP Checkpoint</span>'
        f'<div class="ap-box-body">{html}</div></div>'
    )


def warning(html: str) -> str:
    return (
        '<div class="ap-box ap-box--warning">'
        '<span class="ap-box-label">Common Mistake</span>'
        f'<div class="ap-box-body">{html}</div></div>'
    )


def optional_note(html: str) -> str:
    return (
        '<details class="ap-box ap-box--optional">'
        '<summary class="ap-box-label">Optional enrichment</summary>'
        f'<div class="ap-box-body">{html}</div></details>'
    )


def concept_frame(what: str, why: str, recognize: str, mistake: str, check: str) -> str:
    return (
        '<div class="ap-concept-frame">'
        f'<div class="ap-concept-row"><span>What it means</span><p>{what}</p></div>'
        f'<div class="ap-concept-row"><span>Why it matters</span><p>{why}</p></div>'
        f'<div class="ap-concept-row"><span>How to recognize</span><p>{recognize}</p></div>'
        f'<div class="ap-concept-row ap-concept-row--warn"><span>Common mistake</span><p>{mistake}</p></div>'
        f'<div class="ap-concept-row"><span>How to check</span><p>{check}</p></div>'
        "</div>"
    )


def role(label: str, title: str, lead: str) -> str:
    return (
        f'<div class="cm-slide-role cm-slide-role--lesson">'
        f'<span class="cm-slide-role-label">{label}</span>'
        f"<strong>{title}</strong><p>{lead}</p></div>"
    )


def math_block(tex: str) -> str:
    """Display math card — auto \\displaystyle inside \\[ ... \\] for limits/fractions."""
    inner = tex
    if "\\[" in inner and "\\displaystyle" not in inner and ("\\lim" in inner or "\\frac" in inner):
        inner = inner.replace("\\[", "\\[\\displaystyle ", 1)
    return (
        f'<div class="stem-math-block cm-math-block ap-math-block ap-math-display">{inner}</div>'
    )


def limit_card(x_to: str, expr: str = "f(x)", equals: str | None = None) -> str:
    """Hero limit anchor — matches Novel Prep display limit visual (Fig. 1 style)."""
    eq = f" = {equals}" if equals is not None else ""
    return math_block(f"\\[\\displaystyle\\lim_{{{x_to}}} {expr}{eq}\\]")


def limit_inline(x_to: str, expr: str = "f(x)", equals: str | None = None) -> str:
    eq = f" = {equals}" if equals is not None else ""
    return f"\\(\\displaystyle\\lim_{{{x_to}}} {expr}{eq}\\)"


def rate_card(formula: str, label: str = "") -> str:
    cap = f'<span class="ap-math-display__label">{label}</span>' if label else ""
    return f'<div class="ap-math-display ap-math-display--rate">{cap}{math_block(f"\\[\\displaystyle {formula}\\]")}</div>'


def visual_limit_vs_value(
    c: str,
    limit_val: str,
    fc_val: str | None = None,
    fc_undefined: bool = False,
) -> str:
    """Side-by-side limit (approach) vs function value (at c) — visual model."""
    x_to = f"x\\to {c}"
    if fc_undefined:
        fc_inner = math_block(f"\\[\\displaystyle f({c})\\ \\text{{undefined}}\\]")
    elif fc_val is not None:
        fc_inner = math_block(f"\\[\\displaystyle f({c}) = {fc_val}\\]")
    else:
        fc_inner = '<p class="ap-visual-pair__na">Inspect the filled point after comparing sides.</p>'
    return (
        '<div class="ap-visual-pair">'
        '<div class="ap-visual-pair__col">'
        '<span class="ap-visual-pair__tag">Approach (limit)</span>'
        + limit_card(x_to, equals=limit_val)
        + "</div>"
        '<div class="ap-visual-pair__col">'
        '<span class="ap-visual-pair__tag">At the point (value)</span>'
        + fc_inner
        + "</div></div>"
    )


# Standard figure notices (LaTeX)
NOTICE_LIMIT_EQ_FC = "\\(\\displaystyle\\lim_{x\\to c} f(x) = f(c)\\)"
NOTICE_JUMP_DNE = (
    "\\(L^{-}=-1\\), \\(L^{+}=4\\), "
    "\\(\\displaystyle\\lim_{x\\to 3} f(x)\\) DNE"
)
NOTICE_HOLE = "\\(\\displaystyle\\lim_{x\\to c} f(x)\\) exists; \\(f(c)\\) may be missing"
NOTICE_INFINITE = "\\(|y|\\to\\infty\\) near \\(c\\) — finite two-sided limit DNE"


def data_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<table class="ap-data-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def phase_divider(phase: str, subtitle: str = "") -> str:
    sub = f'<p class="ap-phase-sub">{subtitle}</p>' if subtitle else ""
    return (
        f'<div class="ap-phase-divider" data-ap-phase="{phase}">'
        f'<span class="ap-phase-label">{phase}</span>'
        f'<h3 class="ap-phase-title">{subtitle or phase}</h3>{sub}</div>'
    )


def intro(unit: str, section: str, title: str, chips: list[tuple[str, str]]) -> str:
    chip_html = "".join(
        f'<button type="button" class="cm-intro-chip" data-cm-jump-section="{idx}">'
        f'<span class="cm-intro-chip-num">{num}</span>'
        f'<span class="cm-intro-chip-label">{label}</span></button>'
        for num, (idx, label) in enumerate(chips, 1)
    )
    return (
        '<div class="cm-intro-canvas ap-calc-intro">'
        '<div class="cm-intro-bg" aria-hidden="true">'
        '<span class="cm-intro-orb cm-intro-orb--1"></span>'
        '<span class="cm-intro-orb cm-intro-orb--2"></span>'
        '<span class="cm-intro-grid"></span></div>'
        '<div class="cm-intro-content">'
        '<span class="cm-intro-kicker">Novel Prep · AP Calculus AB / BC</span>'
        f'<p class="cm-intro-unit">Unit {unit} · Section {section}</p>'
        f'<h1 class="cm-intro-title">{title}</h1>'
        '<p class="cm-intro-lede">Classroom-ready deck: visual investigation → definitions → worked &amp; guided practice → exit ticket.</p>'
        '<div class="cm-intro-meta">'
        '<span class="cm-intro-meta-item"><em>Flow</em>Launch · Visual · Concept · Practice</span>'
        '<span class="cm-intro-meta-item"><em>Tools</em>Study mode · Projector · Packet PDF</span>'
        "</div>"
        f'<div class="cm-intro-chips">{chip_html}</div>'
        '<p class="cm-intro-cta">Tap a phase or press <strong>Next</strong> to begin.</p>'
        "</div></div>"
    )


def worked_example(
    title: str,
    understand: str,
    representation: str,
    steps_html: str,
    conclusion: str,
    check: str,
) -> str:
    return (
        role("Worked Example", title, "Teacher model — follow strategy, algebra, and verification.")
        + definition("Understand", f"<p>{understand}</p>")
        + key_point("Representation", f"<p>{representation}</p>")
        + steps_html
        + checkpoint(f"<strong>Conclusion:</strong> {conclusion}")
        + key_point("Check", f"<p>{check}</p>")
    )


def solution_steps(steps: list[str]) -> str:
    """Progressive reveal via cm-step-block (Step 1, Step 2, ...)."""
    toolbar = (
        '<div class="cm-steps-toolbar" data-cm-steps-toolbar>'
        '<span class="cm-steps-label">Walk through the solution</span>'
        '<div class="cm-steps-actions">'
        '<button type="button" class="cm-steps-btn" data-cm-next-step>Next step</button>'
        '<button type="button" class="cm-steps-btn cm-steps-btn--ghost" data-cm-show-all-steps>Show all</button>'
        "</div></div>"
    )
    blocks = []
    for i, step in enumerate(steps, 1):
        hidden = " cm-step--hidden" if i > 1 else ""
        blocks.append(f'<div class="cm-step-block{hidden}" data-step="{i}"><p><strong>Step {i}.</strong> {step}</p></div>')
    return toolbar + "".join(blocks)


def guided_example(problem_html: str, hints: list[str], solution_html: str) -> str:
    hints_html = "".join(
        f'<li class="ap-hint-item ap-hint-item--hidden" data-ap-hint="{i}"><strong>Hint {i}:</strong> {h}</li>'
        for i, h in enumerate(hints, 1)
    )
    return (
        role("Guided Example", "Your turn", "Use Thinking Space first; reveal hints only when stuck.")
        + '<div class="ap-thinking-space">'
        '<p class="ap-thinking-label">Thinking Space</p>'
        '<p class="ap-thinking-prompt">Write your setup and first step before opening any hint.</p>'
        "</div>"
        + f'<div class="ap-problem-stem">{problem_html}</div>'
        + f'<ul class="ap-hint-list" data-ap-hints>{hints_html}</ul>'
        + '<button type="button" class="cm-reveal-btn ap-hint-btn" data-ap-reveal-hint>Reveal next hint</button>'
        + '<div class="cm-try-banner" data-cm-try-banner>'
        '<div class="cm-try-banner-icon" aria-hidden="true">✦</div>'
        '<div class="cm-try-banner-copy"><strong>Ready to check?</strong>'
        "<span>Reveal the model solution only after you've written a full attempt.</span></div>"
        '<button type="button" class="cm-reveal-btn" data-cm-reveal-solution>Show solution</button>'
        "</div>"
        + f'<div class="cm-solution-panel cm-is-collapsed" data-cm-solution-panel>{solution_html}</div>'
    )


def mcq_reveal(
    stem: str,
    choices: list[str],
    correct: str,
    strategy: str,
    solution_html: str,
) -> str:
    letters = "ABCD"
    grid = "".join(
        f'<button type="button" class="cm-mcq-choice" data-choice="{letters[i]}">'
        f'<span class="cm-mcq-letter">{letters[i]}</span>'
        f'<span class="cm-mcq-text">{c}</span></button>'
        for i, c in enumerate(choices[:4])
    )
    return (
        '<div class="cm-question-workspace"><div class="cm-question-stem">'
        f'<div class="cm-strategy-chip"><span class="cm-strategy-chip-label">Strategy</span><p>{strategy}</p></div>'
        '<div class="cm-slide-role cm-slide-role--question">'
        '<span class="cm-slide-role-label">AP Practice</span>'
        "<strong>Try it first</strong><p>Choose an answer, then reveal the full reasoning.</p></div>"
        f"{stem}</div>"
        '<div class="cm-question-interact">'
        f'<div class="cm-mcq-interactive" data-cm-mcq data-cm-correct="{correct}">'
        '<p class="cm-mcq-prompt">Choose your answer</p>'
        f'<div class="cm-mcq-grid">{grid}</div>'
        '<div class="cm-mcq-actions">'
        '<button type="button" class="cm-mcq-check" data-cm-check-mcq disabled>Check answer</button>'
        "</div></div>"
        '<button type="button" class="cm-reveal-btn" data-cm-reveal-solution>Show full solution</button>'
        f'<div class="cm-solution-panel cm-is-collapsed" data-cm-solution-panel>{solution_html}</div>'
        "</div></div>"
    )


def exit_ticket(items: list[tuple[str, str]]) -> str:
    rows = "".join(
        f'<li><span class="ap-exit-num">{i}</span><div class="ap-exit-body">{q}'
        f'<div class="cm-solution-panel cm-is-collapsed ap-exit-solution" data-cm-solution-panel>{a}</div>'
        f'<button type="button" class="cm-reveal-btn ap-exit-reveal" data-cm-reveal-solution>Reveal</button>'
        f"</div></li>"
        for i, (q, a) in enumerate(items, 1)
    )
    return (
        role("Exit Ticket", "Check your learning", "Answer each item before revealing.")
        + f'<ol class="ap-exit-list">{rows}</ol>'
    )


def _math_lab_shell(spec_json: str, inner: str, lab_mod: str = "") -> str:
    mod_cls = f" ap-math-lab--{lab_mod}" if lab_mod else ""
    return (
        f'<div class="ap-math-lab tex2jax_ignore{mod_cls}" data-ap-math-lab>'
        f'<script type="application/json" data-ap-lab-spec>{spec_json}</script>'
        f"{inner}"
        '<div class="sr-only" data-ap-live aria-live="polite"></div>'
        "</div>"
    )


_LAB_VIEWBOX = "0 0 480 280"
_LAB_SVG = 480
_LAB_SVG_H = 280


def secant_math_lab_embed(spec_json: str) -> str:
    inner = (
        '<div class="ap-lab-phase ap-lab-phase--predict">'
        '<p class="ap-lab-phase__label">A · Predict</p>'
        '<p class="ap-lab-phase__prompt">As h → 0 from both sides, does the secant slope stabilize? What tangent slope do you predict?</p>'
        '<div class="ap-lab-predict-btns">'
        '<button type="button" class="ap-lab-btn" data-ap-predict="increase">Increases</button>'
        '<button type="button" class="ap-lab-btn" data-ap-predict="decrease">Decreases</button>'
        '<button type="button" class="ap-lab-btn ap-lab-btn--primary" data-ap-predict="stabilize-4">Stabilizes near 4</button>'
        "</div>"
        '<p class="ap-lab-feedback" data-ap-predict-result hidden></p>'
        "</div>"
        '<div class="ap-lab-phase ap-lab-phase--explore">'
        '<p class="ap-lab-phase__label">B · Explore</p>'
        '<div class="ap-lab-explore">'
        '<div class="ap-lab-controls" data-ap-controls></div>'
        '<label class="ap-lab-slider-label" for="ap-secant-h">'
        'Interval h = <strong data-ap-h-val>1</strong> s (h ≠ 0)</label>'
        '<input type="range" id="ap-secant-h" class="ap-range ap-lab-range" '
        'data-ap-h-slider aria-label="Secant interval h in seconds"/>'
        '<div class="ap-secant-metrics tex2jax_ignore">'
        '<div class="ap-metric"><span>Rise Δs</span><strong data-ap-rise-val>—</strong> m</div>'
        '<div class="ap-metric"><span>Run h</span><strong data-ap-run-val>—</strong> s</div>'
        '<div class="ap-metric ap-metric--accent"><span>Avg rate</span>'
        '<strong data-ap-rate-val>—</strong> m/s</div>'
        "</div>"
        '<p class="ap-formula-readout" data-ap-formula-val></p>'
        '<p class="ap-lab-eq"><span data-ap-secant-eq></span> · <span data-ap-tangent-eq></span></p>'
        '<div class="ap-lab-graph-wrap ap-lab-graph-wrap--interactive">'
        f'<svg class="ap-lab-svg ap-secant-svg" viewBox="{_LAB_VIEWBOX}" role="img" '
        'aria-label="Secant and tangent on s(t)=t²+1">'
        f'<rect width="{_LAB_SVG}" height="{_LAB_SVG_H}" fill="#faf8ff" rx="10"/>'
        '<line data-ap-run stroke="#ea580c" stroke-width="2.5" stroke-dasharray="5 3"/>'
        '<line data-ap-rise stroke="#2563eb" stroke-width="2.5" stroke-dasharray="5 3"/>'
        '<path data-ap-curve fill="none" stroke="#6c4eff" stroke-width="2.5"/>'
        '<line data-ap-secant-halo stroke="#ffffff" stroke-width="7" stroke-linecap="round"/>'
        '<line data-ap-secant stroke="#475569" stroke-width="4" stroke-linecap="round"/>'
        '<line data-ap-tangent stroke="#059669" stroke-width="2" stroke-dasharray="6 4"/>'
        '<circle data-ap-fixed r="7" fill="#6c4eff"/>'
        '<circle data-ap-moving r="5" fill="#fff" stroke="#2563eb" stroke-width="2"/>'
        "</svg></div>"
        '<table class="ap-lab-table"><thead><tr><th>h</th><th>Δs</th><th>Δs/h</th><th>Interval</th></tr></thead>'
        '<tbody data-ap-table-body></tbody></table>'
        '<div class="ap-lab-estimates">'
        '<span>Left estimate: <strong data-ap-left-est>—</strong></span>'
        '<span>Right estimate: <strong data-ap-right-est>—</strong></span>'
        '<span>Agreement: <strong data-ap-agree>Explore both sides</strong></span>'
        "</div>"
        "</div></div>"
        '<div class="ap-lab-phase ap-lab-phase--explain">'
        '<p class="ap-lab-phase__label">C · Explain</p>'
        '<p>Why can we use h → 0 but not h = 0?</p>'
        '<div class="ap-lab-predict-btns">'
        '<button type="button" class="ap-lab-btn ap-lab-btn--primary" data-ap-explain="h-not-zero">h → 0, h ≠ 0</button>'
        '<button type="button" class="ap-lab-btn" data-ap-explain="h-zero-ok">h = 0 is fine</button>'
        "</div>"
        '<p class="ap-lab-feedback" data-ap-explain-result hidden></p>'
        '<div class="ap-box ap-box--checkpoint" data-ap-conclusion hidden>'
        '<span class="ap-box-label">Formal conclusion</span>'
        '<div class="ap-box-body">Instantaneous rate at t = 2 is <strong>4 m/s</strong>. '
        "Left and right secant slopes approach 4; tangent slope 4.</div></div>"
        "</div>"
        '<div class="ap-lab-tutor" data-ap-tutor>'
        '<p data-ap-tutor-text>Need a nudge? Tap for a hint (Level 1).</p>'
        '<button type="button" class="ap-lab-btn" data-ap-tutor-next>Get hint</button>'
        '<p class="ap-lab-reflection" data-ap-reflection hidden>'
        '<strong>Reflection:</strong> In your own words, explain why the answer holds.</p>'
        "</div>"
    )
    controls_note = (
        '<button type="button" class="ap-lab-btn" data-ap-action="left">Approach from left</button>'
        '<button type="button" class="ap-lab-btn" data-ap-action="right">Approach from right</button>'
        '<button type="button" class="ap-lab-btn" data-ap-action="animate">Animate h→0</button>'
        '<button type="button" class="ap-lab-btn" data-ap-action="reset">Reset</button>'
        '<button type="button" class="ap-lab-btn" data-ap-action="reveal-tangent">Reveal tangent</button>'
    )
    return _math_lab_shell(spec_json, inner.replace(
        '<div class="ap-lab-controls" data-ap-controls></div>',
        '<div class="ap-lab-controls" data-ap-controls>' + controls_note + "</div>",
    ), lab_mod="secant")


def limit_cases_math_lab_embed(spec_json: str) -> str:
    inner = (
        '<div class="ap-lab-case-tabs">'
        '<button type="button" class="ap-lab-case-tab is-active" data-ap-case="0">A</button>'
        '<button type="button" class="ap-lab-case-tab" data-ap-case="1">B</button>'
        '<button type="button" class="ap-lab-case-tab" data-ap-case="2">C</button>'
        '<button type="button" class="ap-lab-case-tab" data-ap-case="3">D</button>'
        "</div>"
        '<h3 class="ap-lab-case-title" data-ap-case-title></h3>'
        '<div class="ap-lab-phase ap-lab-phase--predict">'
        '<p class="ap-lab-phase__label">Predict → Explore → Explain</p>'
        '<p class="ap-lab-phase__prompt">Before tracing, predict whether left and right approach heights agree.</p>'
        "</div>"
        '<div class="ap-lab-explore">'
        '<div class="ap-lab-controls">'
        '<button type="button" class="ap-lab-btn" data-ap-action="left">Approach from left</button>'
        '<button type="button" class="ap-lab-btn" data-ap-action="right">Approach from right</button>'
        '<button type="button" class="ap-lab-btn" data-ap-action="reset">Reset</button>'
        "</div>"
        '<label for="ap-limit-x">x = <strong data-ap-x-read>2.60</strong></label>'
        '<input type="range" id="ap-limit-x" class="ap-range ap-lab-range" data-ap-x-slider '
        'aria-label="Trace x toward c"/>'
        '<p class="ap-lab-side-msg" data-ap-side-msg></p>'
        '<div class="ap-secant-metrics"><div class="ap-metric"><span>f(x)</span><strong data-ap-y-read>—</strong></div></div>'
        '<div class="ap-lab-graph-wrap ap-lab-graph-wrap--interactive">'
        f'<svg class="ap-lab-svg ap-lab-svg--limit" viewBox="{_LAB_VIEWBOX}" role="img" aria-label="Limit case graph">'
        f'<rect width="{_LAB_SVG}" height="{_LAB_SVG_H}" fill="#faf8ff" rx="10"/>'
        '<g data-ap-plot-layer>'
        '<line data-ap-axis-x stroke="#4c3d99" stroke-width="1.5"/>'
        '<line data-ap-axis-y stroke="#4c3d99" stroke-width="1.5"/>'
        '<line data-ap-target-x stroke="#c4b5fd" stroke-width="1.5" stroke-dasharray="4 3"/>'
        '<path data-ap-branch="0" data-ap-curve fill="none" stroke-width="2.5"/>'
        '<path data-ap-branch="1" fill="none" stroke-width="2.5"/>'
        '<circle data-ap-open-0 r="5" fill="#fff" stroke="#6c4eff" stroke-width="2" visibility="hidden"/>'
        '<circle data-ap-open-1 r="5" fill="#fff" stroke="#6c4eff" stroke-width="2" visibility="hidden"/>'
        '<circle data-ap-filled-0 r="5" fill="#6c4eff" visibility="hidden"/>'
        '<circle data-ap-tracer r="6" fill="#ea580c" stroke="#fff" stroke-width="2" visibility="hidden"/>'
        "</g></svg></div>"
        '<div class="ap-lab-lock-row">'
        '<button type="button" class="ap-lab-btn" data-ap-lock-left>Lock left observation</button>'
        '<button type="button" class="ap-lab-btn" data-ap-lock-right>Lock right observation</button>'
        "</div>"
        '<p>Left: <strong data-ap-left-obs>______</strong> · Right: <strong data-ap-right-obs>______</strong></p>'
        '<div class="ap-lab-limit-panel" data-ap-limit-panel hidden>'
        '<p>Compare: <strong data-ap-compare>—</strong> · Limit: <strong data-ap-limit-val>—</strong> · f(c): <strong data-ap-fc-val>—</strong></p>'
        "</div></div>"
        '<div class="ap-lab-tutor" data-ap-tutor><p data-ap-tutor-text>Need a nudge? Tap for a hint.</p>'
        '<button type="button" class="ap-lab-btn" data-ap-tutor-next>Get hint</button>'
        '<p class="ap-lab-reflection" data-ap-reflection hidden>'
        '<strong>Reflection:</strong> In your own words, explain why the answer holds.</p></div>'
    )
    return _math_lab_shell(spec_json, inner, lab_mod="limit")


def tracer_math_lab_embed(spec_json: str) -> str:
    inner = (
        '<div class="ap-lab-scenario-tabs">'
        '<button type="button" class="ap-lab-scenario-tab is-active" data-ap-scenario="0">Continuous</button>'
        '<button type="button" class="ap-lab-scenario-tab" data-ap-scenario="1">Hole</button>'
        '<button type="button" class="ap-lab-scenario-tab" data-ap-scenario="2">Hole + value</button>'
        '<button type="button" class="ap-lab-scenario-tab" data-ap-scenario="3">Jump</button>'
        '<button type="button" class="ap-lab-scenario-tab" data-ap-scenario="4">Endpoint</button>'
        '<button type="button" class="ap-lab-scenario-tab" data-ap-scenario="5">Infinite</button>'
        "</div>"
        '<p class="ap-lab-scenario-note" data-ap-scenario-note></p>'
        '<div class="ap-lab-body ap-lab-body--split">'
        '<div class="ap-lab-main">'
        '<div class="ap-lab-controls">'
        '<button type="button" class="ap-lab-btn" data-ap-action="left">Trace left</button>'
        '<button type="button" class="ap-lab-btn" data-ap-action="right">Trace right</button>'
        '<button type="button" class="ap-lab-btn" data-ap-action="reset">Reset</button>'
        '<button type="button" class="ap-lab-btn" data-ap-lock-left>Lock left</button>'
        '<button type="button" class="ap-lab-btn" data-ap-lock-right>Lock right</button>'
        '<button type="button" class="ap-lab-btn ap-lab-btn--primary" data-ap-lock-compare>Compare</button>'
        "</div>"
        '<label class="ap-lab-slider-label" for="ap-trace-x">'
        'x = <strong data-ap-trace-x>0.50</strong> · y = <strong data-ap-trace-y>—</strong></label>'
        '<input type="range" id="ap-trace-x" class="ap-range ap-lab-range" data-ap-trace-slider '
        'aria-label="Trace x on graph"/>'
        '<div class="ap-lab-graph-wrap ap-lab-graph-wrap--interactive">'
        f'<svg class="ap-lab-svg ap-trace-svg" viewBox="{_LAB_VIEWBOX}" role="img">'
        f'<rect width="{_LAB_SVG}" height="{_LAB_SVG_H}" fill="#faf8ff" rx="10"/>'
        '<g data-ap-plot-layer>'
        '<line data-ap-axis-x stroke="#4c3d99" stroke-width="1.5"/>'
        '<line data-ap-axis-y stroke="#4c3d99" stroke-width="1.5"/>'
        '<line data-ap-target-x stroke="#c4b5fd" stroke-width="1.5" stroke-dasharray="4 3"/>'
        '<path data-ap-branch="0" fill="none" stroke-width="2.5"/>'
        '<path data-ap-branch="1" fill="none" stroke-width="2.5"/>'
        '<circle data-ap-open-0 r="5" fill="#fff" stroke="#6c4eff" stroke-width="2" visibility="hidden"/>'
        '<circle data-ap-open-1 r="5" fill="#fff" stroke="#6c4eff" stroke-width="2" visibility="hidden"/>'
        '<circle data-ap-filled-0 r="5" fill="#6c4eff" visibility="hidden"/>'
        '<circle data-ap-tracer r="6" fill="#059669" stroke="#fff" stroke-width="2" visibility="hidden"/>'
        "</g></svg></div></div>"
        '<aside class="ap-lab-dashboard" data-ap-dashboard aria-label="Observation dashboard">'
        '<p class="ap-lab-dashboard__title">Observation dashboard</p>'
        '<p data-ap-step="1" class="ap-lab-step is-active">1 · Trace from the left</p>'
        '<p data-ap-step="2" class="ap-lab-step">2 · Lock left-hand result</p>'
        '<p data-ap-step="3" class="ap-lab-step">3 · Trace from the right</p>'
        '<p data-ap-step="4" class="ap-lab-step">4 · Lock right-hand result</p>'
        '<p data-ap-step="5" class="ap-lab-step">5 · Compare</p>'
        '<p data-ap-step="6" class="ap-lab-step">6 · Inspect filled point</p>'
        '<dl class="ap-lab-dash-stats">'
        '<dt>\\(L^{-}\\)</dt><dd data-d-left>—</dd>'
        '<dt>\\(L^{+}\\)</dt><dd data-d-right>—</dd>'
        "<dt>Same?</dt><dd data-d-same>—</dd>"
        "<dt>Two-sided</dt><dd data-d-two>—</dd>"
        "<dt>\\(f(c)\\)</dt><dd data-d-fc>—</dd>"
        "</dl></aside></div>"
        '<div class="ap-box ap-box--checkpoint" data-ap-conclusion hidden>'
        '<span class="ap-box-label">Conclusion</span>'
        '<div class="ap-box-body">Use Left → Right → Compare → Value on every graph.</div></div>'
        '<div class="ap-lab-tutor" data-ap-tutor><p data-ap-tutor-text>Need a nudge? Tap for a hint.</p>'
        '<button type="button" class="ap-lab-btn" data-ap-tutor-next>Get hint</button>'
        '<p class="ap-lab-reflection" data-ap-reflection hidden>'
        '<strong>Reflection:</strong> In your own words, explain why the answer holds.</p></div>'
    )
    return _math_lab_shell(spec_json, inner, lab_mod="tracer")


def secant_interactive_embed() -> str:
    from ap_calc_math_lab_specs import secant_lab_11, spec_json as _sj
    return secant_math_lab_embed(_sj(secant_lab_11()))


def limit_approach_embed() -> str:
    from ap_calc_math_lab_specs import limit_cases_lab_12, spec_json as _sj
    return limit_cases_math_lab_embed(_sj(limit_cases_lab_12()))


def limit_tracer_embed() -> str:
    from ap_calc_math_lab_specs import tracer_lab_13, spec_json as _sj
    return tracer_math_lab_embed(_sj(tracer_lab_13()))


def practice_packet(section: str, title: str) -> str:
    return (
        '<div class="ap-calc-packet-card glass-panel np-glass">'
        '<p class="np-atelier-kicker">Practice packet</p>'
        f"<h2>{title}</h2>"
        "<p>Download the worksheet and solution key for additional practice beyond this deck.</p>"
        '<div class="ap-calc-packet-actions">'
        f'<a class="np-atelier-btn np-atelier-btn--primary" href="/ap/calc/practice/{section}/packet.pdf" target="_blank" rel="noopener">Open packet PDF</a>'
        f'<a class="np-atelier-btn np-atelier-btn--ghost" href="/ap/calc/practice/{section}/solutions.pdf" target="_blank" rel="noopener">Open solutions PDF</a>'
        "</div></div>"
    )


class SlideBuilder:
    def __init__(self, section: str):
        self.section = section
        self.slides: list[dict] = []
        self._idx = 1

    def add(self, title: str, html: str, kind: str = "lesson", **kw) -> int:
        idx = self._idx
        phase = kw.pop("path_phase", "")
        slide = {
            "index": idx,
            "title": title,
            "html": html,
            "kind": kind,
            "group": kw.get("group", "learn"),
            "section": kw.get("section", self.section),
            "study_tip": kw.get("study_tip", ""),
            **{k: v for k, v in kw.items() if k not in ("group", "section", "study_tip")},
        }
        if phase:
            slide["path_phase"] = phase
        self.slides.append(slide)
        self._idx += 1
        return idx
