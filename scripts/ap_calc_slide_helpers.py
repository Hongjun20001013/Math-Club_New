"""HTML slide building blocks for AP Calculus course materials."""
from __future__ import annotations

FIG = "/static/ap_calc/figures"


def fig(path: str, caption: str = "", cls: str = "", notice: str = "") -> str:
    cap = f'<figcaption class="ap-fig-cap">{caption}</figcaption>' if caption else ""
    notice_html = f'<p class="ap-fig-notice"><strong>What to notice:</strong> {notice}</p>' if notice else ""
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
    return f'<div class="stem-math-block cm-math-block ap-math-block">{tex}</div>'


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


def secant_interactive_embed() -> str:
    return (
        '<div class="ap-interactive ap-secant-demo" data-ap-secant-demo '
        'data-a="2" data-base-y="5" data-slope-limit="4">'
        '<div class="ap-interactive__header">'
        '<span class="ap-interactive__badge">Interactive</span>'
        '<p class="ap-interactive__lead">Drag <strong>h</strong> to see how '
        '\\(\\dfrac{s(a+h)-s(a)}{h}\\) is <em>rise over run</em> on the graph.</p>'
        "</div>"
        '<div class="ap-secant-controls">'
        '<label for="ap-secant-h">Interval h = <strong data-ap-h-val>1.00</strong> s</label>'
        '<input type="range" id="ap-secant-h" class="ap-range" min="0.05" max="1" step="0.05" '
        'value="1" data-ap-secant-slider/>'
        "</div>"
        '<div class="ap-secant-metrics">'
        '<div class="ap-metric"><span>Rise Δs</span><strong data-ap-rise-val>5.00</strong> m</div>'
        '<div class="ap-metric"><span>Run h</span><strong data-ap-run-val>1.00</strong> s</div>'
        '<div class="ap-metric ap-metric--accent"><span>Avg rate</span>'
        '<strong data-ap-rate-val>5.00</strong> m/s</div>'
        "</div>"
        '<p class="ap-formula-readout" data-ap-formula-val>'
        "[5.00 m] ÷ [1.00 s] = 5.00 m/s</p>"
        '<svg class="ap-secant-svg" viewBox="0 0 520 320" aria-label="Difference quotient visualization">'
        '<rect width="520" height="320" fill="#faf8ff" rx="12"/>'
        '<polygon data-ap-rise-poly fill="rgba(37,99,235,0.08)" stroke="none"/>'
        '<line data-ap-run stroke="#ea580c" stroke-width="2.5" stroke-dasharray="6 4"/>'
        '<line data-ap-rise stroke="#2563eb" stroke-width="2.5" stroke-dasharray="6 4"/>'
        '<path data-ap-curve fill="none" stroke="#6a4ce6" stroke-width="3"/>'
        '<line data-ap-secant stroke="#2563eb" stroke-width="2.5"/>'
        '<line data-ap-tangent stroke="#059669" stroke-width="2" stroke-dasharray="6 4"/>'
        '<circle data-ap-fixed cx="0" cy="0" r="7" fill="#6a4ce6"/>'
        '<circle data-ap-moving cx="0" cy="0" r="6" fill="#fff" stroke="#2563eb" stroke-width="2.5"/>'
        '<text data-ap-lbl-rise font-size="12" fill="#2563eb" font-weight="600"></text>'
        '<text data-ap-lbl-run font-size="12" fill="#ea580c" font-weight="600" text-anchor="middle"></text>'
        "</svg>"
        '<p class="ap-fig-notice"><strong>What to notice:</strong> Orange <strong>h</strong> (run) and blue '
        '<strong>Δs</strong> (rise) form a slope triangle. As h → 0, secant → tangent (green), rate → <strong>4</strong>.</p>'
        "</div>"
    )


def limit_approach_embed() -> str:
    return (
        '<div class="ap-interactive ap-limit-demo" data-ap-limit-demo data-c="3">'
        '<div class="ap-interactive__header">'
        '<span class="ap-interactive__badge">Interactive</span>'
        '<p class="ap-interactive__lead">Slide <strong>x</strong> toward 3. Watch outputs approach '
        '<strong>L = 5</strong> — even when \\(f(3)\\neq 5\\).</p>'
        "</div>"
        '<div class="ap-secant-controls">'
        '<label for="ap-limit-x">Position x = <strong data-ap-x-read>2.50</strong></label>'
        '<input type="range" id="ap-limit-x" class="ap-range" min="2.5" max="3.5" step="0.05" '
        'value="2.5" data-ap-limit-slider/>'
        "</div>"
        '<div class="ap-secant-metrics">'
        '<div class="ap-metric"><span>f(x)</span><strong data-ap-y-read>4.50</strong></div>'
        '<div class="ap-metric ap-metric--wide"><span>Interpretation</span>'
        '<strong data-ap-limit-msg class="ap-metric-msg">From the left…</strong></div>'
        "</div>"
        '<svg class="ap-limit-svg" viewBox="0 0 520 300" aria-label="Limit approach visualization">'
        '<rect width="520" height="300" fill="#faf8ff" rx="12"/>'
        '<path data-ap-curve fill="none" stroke="#6a4ce6" stroke-width="3"/>'
        '<line x1="0" y1="0" x2="0" y2="0" stroke="rgba(108,78,230,0.2)" stroke-width="1.5" '
        'stroke-dasharray="4 4" data-ap-vline style="display:none"/>'
        '<circle data-ap-open cx="0" cy="0" r="6" fill="#fff" stroke="#6a4ce6" stroke-width="2.5"/>'
        '<circle data-ap-filled cx="0" cy="0" r="6" fill="#6a4ce6"/>'
        '<circle data-ap-tracer cx="0" cy="0" r="8" fill="#ea580c" stroke="#fff" stroke-width="2"/>'
        "</svg>"
        '<p class="ap-fig-notice"><strong>What to notice:</strong> Open circle at (3, 5) shows the limit. '
        "Filled dot at (3, 10) is \\(f(3)\\) — approach and value can differ.</p>"
        "</div>"
    )


def limit_tracer_embed() -> str:
    return (
        '<div class="ap-interactive ap-trace-demo" data-ap-trace-demo data-c="2">'
        '<div class="ap-interactive__header">'
        '<span class="ap-interactive__badge">Interactive</span>'
        '<p class="ap-interactive__lead">Drag along the graph: <strong>Left → Right → Compare → Value</strong>.</p>'
        "</div>"
        '<div class="ap-secant-controls">'
        '<label for="ap-trace-x">Trace at x = <strong data-ap-trace-x>0.50</strong></label>'
        '<input type="range" id="ap-trace-x" class="ap-range" min="0.5" max="3.8" step="0.05" '
        'value="0.5" data-ap-trace-slider/>'
        "</div>"
        '<div class="ap-secant-metrics">'
        '<div class="ap-metric"><span>y on graph</span><strong data-ap-trace-y>1.50</strong></div>'
        '<div class="ap-metric ap-metric--wide"><span>Branch</span>'
        '<strong data-ap-trace-side class="ap-metric-msg">Left branch</strong></div>'
        '<div class="ap-metric ap-metric--wide"><span>Limit read</span>'
        '<strong data-ap-trace-limit class="ap-metric-msg">L⁻ = 3</strong></div>'
        "</div>"
        '<svg class="ap-trace-svg" viewBox="0 0 520 300" aria-label="Graph limit tracer">'
        '<rect width="520" height="300" fill="#faf8ff" rx="12"/>'
        '<line data-ap-vline stroke="rgba(108,78,230,0.35)" stroke-width="1.5" stroke-dasharray="4 4"/>'
        '<path data-ap-left fill="none" stroke="#2563eb" stroke-width="3"/>'
        '<path data-ap-right fill="none" stroke="#ea580c" stroke-width="3"/>'
        '<circle data-ap-open cx="0" cy="0" r="6" fill="#fff" stroke="#6a4ce6" stroke-width="2.5"/>'
        '<text x="0" y="0" font-size="11" fill="#6a4ce6" data-ap-open-lbl>limit 3</text>'
        '<circle data-ap-filled cx="0" cy="0" r="6" fill="#6a4ce6"/>'
        '<circle data-ap-tracer cx="0" cy="0" r="8" fill="#059669" stroke="#fff" stroke-width="2"/>'
        "</svg>"
        '<p class="ap-fig-notice"><strong>What to notice:</strong> Both branches approach y = 3. '
        "The filled point at y = 1.5 is \\(f(2)\\), not the limit.</p>"
        "</div>"
    )


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
