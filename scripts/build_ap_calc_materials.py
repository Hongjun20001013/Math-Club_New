#!/usr/bin/env python3
"""Build AP Calculus AB/BC course materials JSON (Unit 1 sections 1.1–1.3)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(APP_DIR, "data", "ap_calc_materials.json")


def _role(label: str, title: str, lead: str) -> str:
    return (
        f'<div class="cm-slide-role cm-slide-role--lesson">'
        f'<span class="cm-slide-role-label">{label}</span>'
        f"<strong>{title}</strong><p>{lead}</p></div>"
    )


def _intro(unit: str, section: str, title: str, chips: list[tuple[str, str]]) -> str:
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
        '<p class="cm-intro-lede">Expanded lesson deck with theory, worked examples, and packet-aligned practice — same studio flow as SAT Math.</p>'
        '<div class="cm-intro-meta">'
        '<span class="cm-intro-meta-item"><em>Track</em>Limits &amp; Continuity</span>'
        '<span class="cm-intro-meta-item"><em>Practice</em>Packet + solutions PDF</span>'
        "</div>"
        f'<div class="cm-intro-chips">{chip_html}</div>'
        '<p class="cm-intro-cta">Tap a section chip or press <strong>Next</strong> to begin.</p>'
        "</div></div>"
    )


def _outline(unit: str, section: str, title: str, items: list[tuple[str, str]]) -> str:
    rows = "".join(
        f'<li><button type="button" class="cm-content-item" data-cm-jump-section="{idx}">'
        f'<span class="cm-content-num">{num:02d}</span>'
        f'<span class="cm-content-copy"><strong>{label}</strong>'
        f"<span>Jump to section</span></span>"
        f'<span class="cm-content-arrow" aria-hidden="true">→</span></button></li>'
        for num, (idx, label) in enumerate(items, 1)
    )
    return (
        '<div class="cm-content-canvas"><div class="cm-content-bg" aria-hidden="true">'
        '<span class="cm-content-orb cm-content-orb--1"></span>'
        '<span class="cm-content-orb cm-content-orb--2"></span>'
        '<span class="cm-content-grid"></span></div>'
        '<div class="cm-content-inner">'
        '<span class="cm-content-kicker">Lesson outline</span>'
        f'<p class="cm-content-unit">Unit {unit} · {section}</p>'
        f'<h2 class="cm-content-title">{title}</h2>'
        f'<p class="cm-content-lede">{len(items)} sections · theory, examples, and AP-style checks.</p>'
        f'<ol class="cm-content-list">{rows}</ol>'
        "</div></div>"
    )


def _section_divider(num: str, title: str) -> str:
    return (
        f'<div class="cm-section-divider"><span class="cm-section-num">{num}</span>'
        f'<span class="cm-section-kicker">Up next</span>'
        f'<h3 class="cm-section-title">{title}</h3></div>'
    )


def _mcq(stem: str, choices: list[str], correct: str, strategy: str = "") -> str:
    letters = "ABCD"
    grid = "".join(
        f'<button type="button" class="cm-mcq-choice" data-choice="{letters[i]}">'
        f'<span class="cm-mcq-letter">{letters[i]}</span>'
        f'<span class="cm-mcq-text">{c}</span></button>'
        for i, c in enumerate(choices[:4])
    )
    strat = (
        f'<div class="cm-strategy-chip"><span class="cm-strategy-chip-label">Strategy</span>'
        f"<p>{strategy}</p></div>"
        if strategy
        else ""
    )
    return (
        '<div class="cm-question-workspace"><div class="cm-question-stem">'
        f"{strat}"
        '<div class="cm-slide-role cm-slide-role--question">'
        '<span class="cm-slide-role-label">Question Practice</span>'
        "<strong>Try it first</strong>"
        "<p>Pause and solve before revealing the worked solution.</p></div>"
        f"{stem}</div>"
        '<div class="cm-question-interact">'
        f'<div class="cm-mcq-interactive" data-cm-mcq data-cm-correct="{correct}">'
        '<p class="cm-mcq-prompt">Choose your answer</p>'
        f'<div class="cm-mcq-grid">{grid}</div>'
        '<div class="cm-mcq-actions">'
        '<button type="button" class="cm-mcq-check" data-cm-check-mcq disabled>Check answer</button>'
        '<button type="button" class="cm-mcq-skip" data-cm-go-answer>View worked solution →</button>'
        "</div></div></div></div>"
    )


def _answer(correct_line: str, solution_html: str) -> str:
    return (
        '<div class="cm-slide-role cm-slide-role--answer">'
        '<span class="cm-slide-role-label">Answer Review</span>'
        "<strong>Check and correct</strong>"
        "<p>Compare your work with the final answer and fix any missed step.</p></div>"
        f"<p><strong>{correct_line}</strong></p>"
        '<div class="cm-try-banner" data-cm-try-banner>'
        '<div class="cm-try-banner-icon" aria-hidden="true">✦</div>'
        '<div class="cm-try-banner-copy"><strong>Your turn</strong>'
        "<span>Work it out on paper first — reveal when you're ready.</span></div>"
        '<button type="button" class="cm-reveal-btn" data-cm-reveal-solution>Show solution</button>'
        "</div>"
        '<p><strong>Solution:</strong></p>'
        f'<div class="cm-solution-panel cm-is-collapsed" data-cm-solution-panel>{solution_html}</div>'
    )


def _practice_packet(section: str, title: str) -> str:
    return (
        '<div class="ap-calc-packet-card glass-panel np-glass">'
        '<p class="np-atelier-kicker">Practice packet</p>'
        f"<h2>{title}</h2>"
        "<p>Download the classroom packet and solutions — aligned with this lesson deck.</p>"
        '<div class="ap-calc-packet-actions">'
        f'<a class="np-atelier-btn np-atelier-btn--primary" href="/ap/calc/practice/{section}/packet.pdf" target="_blank" rel="noopener">Open packet PDF</a>'
        f'<a class="np-atelier-btn np-atelier-btn--ghost" href="/ap/calc/practice/{section}/solutions.pdf" target="_blank" rel="noopener">Open solutions PDF</a>'
        "</div></div>"
    )


def lesson_1_1() -> dict:
    slides = []
    idx = 1

    def add(title, html, kind="lesson", **kw):
        nonlocal idx
        slides.append(
            {
                "index": idx,
                "title": title,
                "html": html,
                "kind": kind,
                "group": kw.get("group", "learn"),
                "section": kw.get("section", "1.1"),
                "study_tip": kw.get("study_tip", ""),
                **{k: v for k, v in kw.items() if k not in ("group", "section", "study_tip")},
            }
        )
        idx += 1

    add(
        "AP Unit 1.1 · Can change occur at an instant?",
        _intro("1", "1.1", "Can change occur at an instant?", [(4, "Average rate"), (7, "Secant → tangent"), (10, "Context graphs"), (14, "Packet practice")]),
        kind="intro",
        group="divider",
    )
    add(
        "Lesson outline",
        _outline(
            "1",
            "1.1",
            "Can change occur at an instant?",
            [(4, "Average vs instantaneous"), (7, "Secant slopes"), (10, "Graph interpretation"), (12, "AP-style MCQ"), (14, "Practice packet")],
        ),
        kind="content",
        group="divider",
    )
    add(
        "Section 01 · Average vs instantaneous",
        _section_divider("01", "Average vs instantaneous"),
        kind="section",
        group="divider",
    )
    add(
        "The big question of calculus",
        _role("Knowledge Point", "Build the method", "Average rate uses an interval; instantaneous rate asks about a single instant.")
        + "<p>Calculus begins with a precise question:</p>"
        '<blockquote class="ap-calc-quote"><em>How can we describe what is happening at an instant when change usually takes time?</em></blockquote>'
        "<p><strong>Average rate of change</strong> on \\([a,b]\\):</p>"
        '<div class="stem-math-block cm-math-block">\\[\\frac{f(b)-f(a)}{b-a}\\]</div>'
        "<p><strong>Instantaneous rate</strong> at \\(t=a\\) uses shorter intervals and a <strong>limit</strong>.</p>",
        section="1.1",
    )
    add(
        "Secant slopes shrink toward a tangent",
        _role("Knowledge Point", "Build the method", "Shrink the interval — the secant slope approaches the tangent slope.")
        + "<p>For position \\(s(t)=t^2+1\\), the average rate from \\(t=2\\) to \\(t=2+h\\) is</p>"
        '<div class="stem-math-block cm-math-block">\\[\\frac{s(2+h)-s(2)}{h}=4+h\\]</div>'
        "<p>As \\(h\\to 0\\), the rate approaches <strong>\\(4\\)</strong>. That limiting value is the instantaneous rate at \\(t=2\\).</p>",
        section="1.1",
    )
    add(
        "Section 02 · Secant → tangent",
        _section_divider("02", "Secant → tangent"),
        kind="section",
        group="divider",
    )
    add(
        "Worked example: simplify the difference quotient",
        _role("Worked Example", "Show every algebra step", "Expand, cancel \\(h\\), then interpret the limit.")
        + "<p>Given \\(s(t)=t^2+1\\), simplify \\(\\dfrac{s(2+h)-s(2)}{h}\\).</p>"
        '<div class="stem-math-block cm-math-block">\\[\\frac{(2+h)^2+1-(4+1)}{h}=\\frac{4h+h^2}{h}=4+h\\]</div>'
        "<p>So the instantaneous rate at \\(t=2\\) is <strong>\\(4\\)</strong>.</p>",
        section="1.1",
    )
    add(
        "Section 03 · Context graphs",
        _section_divider("03", "Context graphs"),
        kind="section",
        group="divider",
    )
    add(
        "Interpreting motion on a graph (packet: Mr. Brust)",
        _role("Application", "Read the graph", "Slope of a secant = average rate; tangent slope ≈ instantaneous rate.")
        + "<p>Distance-from-home \\(D(t)\\) vs. time: turning around creates a non-monotonic graph.</p>"
        "<ul class=\"stem-itemize\">"
        "<li><strong>(a)</strong> Average speed for the whole trip: \\(\\dfrac{D(8)-D(0)}{8-0}\\).</li>"
        "<li><strong>(b)</strong> Average rate from \\(t=2\\) to \\(t=6\\): slope of the secant on that interval.</li>"
        "<li><strong>(c)</strong> Near \\(t=2\\), use a <em>short</em> interval (e.g. \\(2\\) to \\(2.1\\)) to estimate the instantaneous rate.</li>"
        "</ul>",
        section="1.1",
    )
    add(
        "Social-media views: tangent at w = 10",
        _role("Application", "Estimate from the graph", "Draw a tangent line; its slope estimates the instantaneous rate.")
        + "<p>Channel views \\(v(w)\\) vs. weeks \\(w\\): at \\(w=10\\), sketch a tangent line and estimate its slope "
        "(views per week at that instant).</p>"
        "<p>To <em>estimate</em> without a tangent, use average rate on a tiny interval: "
        "\\(\\dfrac{v(10.1)-v(9.9)}{0.2}\\).</p>",
        section="1.1",
    )
    add(
        "Section 04 · AP-style MCQ",
        _section_divider("04", "AP-style MCQ"),
        kind="section",
        group="divider",
    )
    q_idx = idx
    add(
        "Question: buffalo population interpretation",
        _mcq(
            "<p>Buffalo population \\(b(t)\\), \\(t\\) = years since 1800. What does "
            "\\(\\dfrac{b(50)-b(0)}{50-0}\\) represent?</p>",
            [
                "The population in year 1850",
                "The average rate of change of population from 1800 to 1850",
                "The instantaneous rate in 1800",
                "The total change in population in 50 years only at year 50",
            ],
            "B",
            "Difference quotient over an interval → average rate of change.",
        ),
        kind="question",
        group="practice",
        answer_index=q_idx + 1,
        correct_choice="B",
        section="1.1",
    )
    add(
        "Answer: buffalo population",
        _answer(
            "Correct Answer: B",
            "<p>\\(\\dfrac{b(50)-b(0)}{50-0}\\) is the <strong>average rate of change</strong> of buffalo population "
            "from \\(t=0\\) to \\(t=50\\) (years 1800–1850).</p>",
        ),
        kind="answer",
        group="practice",
        question_index=q_idx,
        section="1.1",
        inline_solution=True,
        interactive=True,
    )
    add(
        "Section 05 · Practice packet",
        _section_divider("05", "Practice packet"),
        kind="section",
        group="divider",
    )
    add(
        "Download Unit 1.1 practice",
        _practice_packet("1.1", "Unit 1.1 · Can change occur at an instant?"),
        kind="lesson",
        group="practice",
        section="1.1",
    )
    return {
        "slug": "ap-1-1-instantaneous-change",
        "unit": 1,
        "unit_name": "Limits and Continuity",
        "section": "1.1",
        "title": "Can Change Occur at an Instant?",
        "deck_title": "AP Unit 1.1 · Instantaneous change",
        "slide_count": len(slides),
        "slides": slides,
        "practice_section": "1.1",
    }


def lesson_1_2() -> dict:
    slides = []
    idx = 1

    def add(title, html, kind="lesson", **kw):
        nonlocal idx
        slides.append({"index": idx, "title": title, "html": html, "kind": kind, "group": kw.get("group", "learn"), "section": kw.get("section", "1.2"), "study_tip": kw.get("study_tip", ""), **{k: v for k, v in kw.items() if k not in ("group", "section", "study_tip")}})
        idx += 1

    add("AP Unit 1.2 · Defining limits", _intro("1", "1.2", "Defining limits and limit notation", [(4, "Limit meaning"), (8, "Value vs limit"), (12, "Graph limits"), (16, "Packet practice")]), kind="intro", group="divider")
    add("Lesson outline", _outline("1", "1.2", "Defining limits", [(4, "Informal definition"), (8, "Piecewise example"), (12, "Graph reading"), (14, "AP MCQ"), (16, "Practice packet")]), kind="content", group="divider")
    add("Section 01 · Limit meaning", _section_divider("01", "What a limit means"), kind="section", group="divider")
    add(
        "Informal definition",
        _role("Knowledge Point", "Build the method", "A limit describes approach, not necessarily the function value.")
        + "<p>\\(\\displaystyle\\lim_{x\\to c} f(x)=L\\) means: as \\(x\\) approaches \\(c\\), \\(f(x)\\) approaches \\(L\\).</p>"
        "<p><strong>Key:</strong> the limit can exist even when \\(f(c)\\) is undefined or different from \\(L\\).</p>",
        section="1.2",
    )
    add(
        "Limit notation cheat sheet",
        _role("Reference", "Read notation fluently", "Say the limit aloud before computing.")
        + "<ul class=\"stem-itemize\">"
        "<li>\\(\\lim_{x\\to 3} f(x)=5\\): “as \\(x\\) approaches 3, \\(f(x)\\) approaches 5.”</li>"
        "<li>\\(f(3)\\) is a <em>separate</em> question (filled dot on the graph).</li>"
        "<li>Open circle at \\((c,L)\\) often signals \\(\\lim_{x\\to c} f(x)=L\\) but \\(f(c)\\neq L\\).</li>"
        "</ul>",
        section="1.2",
    )
    add("Section 02 · Value vs limit", _section_divider("02", "Function value vs limit"), kind="section", group="divider")
    add(
        "Piecewise example",
        _role("Worked Example", "Compare limit and value", "Simplify on both sides of the hole.")
        + "<p>Let \\(f(x)=x+2\\) for \\(x\\neq 3\\), and \\(f(3)=10\\).</p>"
        "<p>\\(\\displaystyle\\lim_{x\\to 3} f(x)=5\\) but \\(f(3)=10\\). The limit and the function value <strong>differ</strong>.</p>",
        section="1.2",
    )
    add("Section 03 · Graph limits", _section_divider("03", "Limits from graphs"), kind="section", group="divider")
    add(
        "Reading limits at x = 2",
        _role("Graphical Skill", "Two-sided approach", "Left-hand and right-hand must agree for the two-sided limit to exist.")
        + "<p>From a graph: trace \\(x\\to 2^{-}\\) and \\(x\\to 2^{+}\\). If both approach the same \\(y\\)-value, "
        "\\(\\lim_{x\\to 2} f(x)\\) exists.</p>"
        "<p><strong>False generalization:</strong> \\(f(1)\\) is <em>not always</em> equal to \\(\\lim_{x\\to 1} f(x)\\).</p>",
        section="1.2",
    )
    add("Section 04 · AP MCQ", _section_divider("04", "AP-style multiple choice"), kind="section", group="divider")
    q_idx = idx
    add(
        "Question: best interpretation of a limit",
        _mcq(
            "<p>Which is the best interpretation of \\(\\displaystyle\\lim_{x\\to 4} f(x)=8\\)?</p>",
            [
                "The value of \\(f\\) at \\(x=4\\) is 8",
                "The value of \\(f\\) at \\(x=8\\) is 4",
                "As \\(x\\) approaches 4, the values of \\(f(x)\\) approach 8",
                "As \\(x\\) approaches 8, the values of \\(f(x)\\) approach 4",
            ],
            "C",
            "Limits describe approaching behavior, not necessarily the function value at the point.",
        ),
        kind="question",
        group="practice",
        answer_index=q_idx + 1,
        correct_choice="C",
        section="1.2",
    )
    add(
        "Answer: limit interpretation",
        _answer("Correct Answer: C", "<p>A limit statement is always about <strong>approaching</strong> inputs and outputs — choice C.</p>"),
        kind="answer",
        group="practice",
        question_index=q_idx,
        section="1.2",
        inline_solution=True,
        interactive=True,
    )
    q_idx = idx
    add(
        "Question: limit as x approaches −1",
        _mcq(
            "<p>Which is the best interpretation of \\(\\displaystyle\\lim_{x\\to -1} f(x)=2\\)?</p>",
            [
                "As \\(x\\) approaches 2, \\(f(x)\\) approaches \\(-1\\)",
                "The value of \\(f\\) at \\(x=-1\\) is 2",
                "The value of \\(f\\) at \\(x=2\\) is \\(-1\\)",
                "As \\(x\\) approaches \\(-1\\), the values of \\(f(x)\\) approach 2",
            ],
            "D",
            "Match the arrow direction: \\(x\\to -1\\), outputs approach 2.",
        ),
        kind="question",
        group="practice",
        answer_index=q_idx + 1,
        correct_choice="D",
        section="1.2",
    )
    add(
        "Answer: limit at −1",
        _answer("Correct Answer: D", "<p>As \\(x\\to -1\\), outputs approach 2 — that is exactly choice D.</p>"),
        kind="answer",
        group="practice",
        question_index=q_idx,
        section="1.2",
        inline_solution=True,
        interactive=True,
    )
    add("Section 05 · Practice packet", _section_divider("05", "Practice packet"), kind="section", group="divider")
    add("Download Unit 1.2 practice", _practice_packet("1.2", "Unit 1.2 · Defining limits"), kind="lesson", group="practice", section="1.2")
    return {
        "slug": "ap-1-2-defining-limits",
        "unit": 1,
        "unit_name": "Limits and Continuity",
        "section": "1.2",
        "title": "Defining Limits and Using Limit Notation",
        "deck_title": "AP Unit 1.2 · Defining limits",
        "slide_count": len(slides),
        "slides": slides,
        "practice_section": "1.2",
    }


def lesson_1_3() -> dict:
    slides = []
    idx = 1

    def add(title, html, kind="lesson", **kw):
        nonlocal idx
        slides.append({"index": idx, "title": title, "html": html, "kind": kind, "group": kw.get("group", "learn"), "section": kw.get("section", "1.3"), "study_tip": kw.get("study_tip", ""), **{k: v for k, v in kw.items() if k not in ("group", "section", "study_tip")}})
        idx += 1

    add("AP Unit 1.3 · Limits from graphs", _intro("1", "1.3", "Estimating limits from graphs", [(4, "One-sided limits"), (8, "Jump discontinuity"), (12, "Sketch constraints"), (16, "Packet practice")]), kind="intro", group="divider")
    add("Lesson outline", _outline("1", "1.3", "Limits from graphs", [(4, "One-sided limits"), (8, "When limits DNE"), (12, "Graph design"), (14, "AP MCQ"), (16, "Practice packet")]), kind="content", group="divider")
    add("Section 01 · One-sided limits", _section_divider("01", "One-sided limits"), kind="section", group="divider")
    add(
        "Left-hand and right-hand limits",
        _role("Knowledge Point", "Build the method", "Approach from one side only — use superscript − or +.")
        + "<p>A <strong>one-sided limit</strong> is the value \\(f(x)\\) approaches as \\(x\\) nears \\(c\\) from the left (\\(x\\to c^{-}\\)) "
        "or right (\\(x\\to c^{+}\\)).</p>"
        "<p>Two-sided limit exists only when left and right limits exist and are <strong>equal</strong>.</p>",
        section="1.3",
    )
    add("Section 02 · When limits DNE", _section_divider("02", "When limits fail to exist"), kind="section", group="divider")
    add(
        "Jump at x = 3",
        _role("Worked Example", "Compare one-sided limits", "Different left and right limits → two-sided limit DNE.")
        + "<p>Example: \\(\\lim_{x\\to 3^{-}} f(x)=-1\\), \\(\\lim_{x\\to 3^{+}} f(x)=2\\). "
        "Because \\(-1\\neq 2\\), \\(\\displaystyle\\lim_{x\\to 3} f(x)\\) <strong>does not exist</strong>.</p>",
        section="1.3",
    )
    add("Section 03 · Graph design", _section_divider("03", "Sketching with constraints"), kind="section", group="divider")
    add(
        "Sketch a function with given limits",
        _role("Application", "Design the graph", "Open vs closed dots encode limits vs function values.")
        + "<p>Sketch \\(g\\) such that: \\(g(3)=-1\\), \\(\\lim_{x\\to 3} g(x)=4\\), and \\(g\\) is increasing on \\((-2,3)\\).</p>"
        "<p><strong>Tip:</strong> open circle at \\((3,4)\\) for the limit, filled dot at \\((3,-1)\\) for the value.</p>",
        section="1.3",
    )
    add("Section 04 · AP MCQ", _section_divider("04", "AP-style multiple choice"), kind="section", group="divider")
    q_idx = idx
    add(
        "Question: which statement is true?",
        _mcq(
            "<p>The graph of \\(f\\) has a jump at \\(x=b\\) with left limit 3 and right limit 5. Which is true?</p>",
            [
                "\\(\\displaystyle\\lim_{x\\to b} f(x)=4\\)",
                "\\(\\displaystyle\\lim_{x\\to b} f(x)=5\\)",
                "\\(\\displaystyle\\lim_{x\\to b} f(x)\\) does not exist",
                "\\(\\displaystyle\\lim_{x\\to b} f(x)=3\\)",
            ],
            "C",
            "Mismatched one-sided limits ⇒ two-sided limit does not exist.",
        ),
        kind="question",
        group="practice",
        answer_index=q_idx + 1,
        correct_choice="C",
        section="1.3",
    )
    add(
        "Answer: jump discontinuity",
        _answer("Correct Answer: C", "<p>Left limit \\(3\\) and right limit \\(5\\) disagree, so the two-sided limit <strong>does not exist</strong>.</p>"),
        kind="answer",
        group="practice",
        question_index=q_idx,
        section="1.3",
        inline_solution=True,
        interactive=True,
    )
    add("Section 05 · Practice packet", _section_divider("05", "Practice packet"), kind="section", group="divider")
    add("Download Unit 1.3 practice", _practice_packet("1.3", "Unit 1.3 · Limits from graphs"), kind="lesson", group="practice", section="1.3")
    return {
        "slug": "ap-1-3-limits-from-graphs",
        "unit": 1,
        "unit_name": "Limits and Continuity",
        "section": "1.3",
        "title": "Estimating Limit Values from Graphs",
        "deck_title": "AP Unit 1.3 · Limits from graphs",
        "slide_count": len(slides),
        "slides": slides,
        "practice_section": "1.3",
    }


def _finalize_materials(materials: list[dict]) -> list[dict]:
    for i, material in enumerate(materials):
        slides = material.get("slides") or []
        material["interactive_count"] = sum(1 for s in slides if s.get("kind") == "question")
        material["checkpoint_count"] = material["interactive_count"]
        material["tex_available"] = True
        material["pdf_available"] = False
        material["phase"] = 1
        material["prev_lesson_slug"] = materials[i - 1]["slug"] if i > 0 else None
        material["next_lesson_slug"] = materials[i + 1]["slug"] if i + 1 < len(materials) else None
    return materials


def build() -> dict:
    materials = _finalize_materials([lesson_1_1(), lesson_1_2(), lesson_1_3()])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "track": "ap_calc",
        "total": len(materials),
        "available": len(materials),
        "materials": materials,
    }


def main() -> None:
    payload = build()
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote {OUTPUT} ({payload['total']} lessons)")


if __name__ == "__main__":
    main()
