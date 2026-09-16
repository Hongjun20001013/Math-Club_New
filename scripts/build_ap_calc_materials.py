#!/usr/bin/env python3
"""Build AP Calculus AB/BC course materials JSON — Unit 1 sections 1.1–1.3 (expert edition)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP_DIR, "scripts"))

from ap_calc_slide_helpers import (  # noqa: E402
    FIG,
    SlideBuilder,
    answer,
    big_idea,
    checkpoint,
    definition,
    fig,
    intro,
    key_point,
    math_block,
    mcq,
    outline,
    practice_packet,
    role,
    section_divider,
    warning,
)

OUTPUT = os.path.join(APP_DIR, "data", "ap_calc_materials.json")


def lesson_1_1() -> dict:
    s = SlideBuilder("1.1")
    s.add(
        "AP Unit 1.1 · Can change occur at an instant?",
        intro(
            "1",
            "1.1",
            "Can change occur at an instant?",
            [(4, "Big idea"), (8, "Average rate"), (14, "Difference quotient"), (20, "Context graphs"), (26, "AP practice")],
        ),
        kind="intro",
        group="divider",
    )
    s.add(
        "Lesson outline",
        outline(
            "1",
            "1.1",
            "Introducing calculus & instantaneous change",
            [
                (4, "Central question of calculus"),
                (8, "Average vs instantaneous rate"),
                (12, "Secant → tangent (visual)"),
                (16, "Difference quotient example"),
                (20, "Mr. Brust motion graph"),
                (24, "AP-style multiple choice"),
                (28, "Practice packet"),
            ],
        ),
        kind="content",
        group="divider",
    )
    s.add("Section 01 · Big idea", section_divider("01", "The central question"), kind="section", group="divider")
    s.add(
        "Why calculus begins with an instant",
        role("Conceptual Frame", "Start with the question", "Calculus is the language of change — including change at a single moment.")
        + big_idea(
            "<p><em>How can we describe what is happening at an instant when change usually takes time?</em></p>"
            "<p><strong>Average rate of change</strong> measures change across an interval. "
            "<strong>Instantaneous rate of change</strong> asks what happens at one input value — and that requires <strong>limits</strong>.</p>"
        )
        + fig(f"{FIG}/packet_1_1_p1.png", "Packet 1.1 · Historical motivation & Mr. Brust scenario", "ap-fig--wide"),
    )
    s.add(
        "Two types of rate — notation",
        role("Knowledge Point", "Distinguish the two rates", "Interval language vs. instant language.")
        + definition(
            "Average rate of change",
            "<p>On \\([a,b]\\), for a quantity \\(f\\):</p>"
            + math_block("\\[\\text{Average rate} = \\frac{f(b)-f(a)}{b-a}\\]")
            + "<p>This is the <strong>slope of a secant line</strong> on the graph of \\(f\\).</p>",
        )
        + definition(
            "Instantaneous rate of change (preview)",
            "<p>At \\(x=c\\), we examine shorter and shorter intervals and take a <strong>limit</strong>:</p>"
            + math_block(
                "\\[\\text{Instantaneous rate at }c = \\lim_{h\\to 0}\\frac{f(c+h)-f(c)}{h}\\]"
            ),
        ),
    )
    s.add("Section 02 · Average rate", section_divider("02", "Average rate of change"), kind="section", group="divider")
    s.add(
        "Position function example",
        role("Worked Example", "Compute an average rate", "Always identify the interval endpoints first.")
        + "<p>A particle has position \\(s(t)=t^2+1\\) (meters), with \\(t\\) in seconds.</p>"
        + key_point(
            "Interval [2, 3]",
            math_block(
                "\\[\\frac{s(3)-s(2)}{3-2}=\\frac{(9+1)-(4+1)}{1}=\\frac{10-5}{1}=5\\ \\text{m/s}\\]"
            )
            + "<p>Interpretation: on average, the particle moved 5 meters per second from \\(t=2\\) to \\(t=3\\).</p>",
        ),
    )
    s.add(
        "Shorter intervals — approaching an instant",
        role("Knowledge Point", "Shrink the interval", "Same formula — smaller \\(\\Delta t\\).")
        + "<p>From \\(t=2\\) to \\(t=2+h\\):</p>"
        + math_block("\\[\\frac{s(2+h)-s(2)}{h}=\\frac{(2+h)^2+1-5}{h}=4+h\\]")
        + "<table class='ap-data-table'><thead><tr><th>\\(h\\)</th><th>Interval</th><th>Average rate \\(4+h\\)</th></tr></thead>"
        "<tbody><tr><td>1</td><td>[2,3]</td><td>5</td></tr>"
        "<tr><td>0.5</td><td>[2,2.5]</td><td>4.5</td></tr>"
        "<tr><td>0.1</td><td>[2,2.1]</td><td>4.1</td></tr>"
        "<tr><td>0.01</td><td>[2,2.01]</td><td>4.01</td></tr></tbody></table>"
        + checkpoint("As \\(h\\to 0\\), the average rate approaches <strong>4</strong>. That limiting value is the instantaneous rate at \\(t=2\\)."),
    )
    s.add("Section 03 · Secant → tangent", section_divider("03", "Secant lines approach a tangent"), kind="section", group="divider")
    s.add(
        "Visual: secant slopes converge",
        role("Graphical Skill", "Connect algebra to the picture", "Each secant uses two points; the tangent uses one point and a limiting direction.")
        + fig(f"{FIG}/secant_to_tangent.svg", "Secant lines on \\(s(t)=t^2+1\\) as \\(h\\to 0\\)")
        + key_point(
            "Geometric meaning",
            "<ul class='stem-itemize'>"
            "<li><strong>Secant slope</strong> = average rate on \\([2,2+h]\\)</li>"
            "<li><strong>Tangent slope</strong> = instantaneous rate at \\(t=2\\)</li>"
            "<li>When the limit exists, secant slopes approach the tangent slope.</li>"
            "</ul>",
        ),
    )
    s.add("Section 04 · Difference quotient", section_divider("04", "Difference quotient"), kind="section", group="divider")
    s.add(
        "Full algebra: simplify before taking the limit",
        role("Worked Example", "Show every step", "Expand, combine like terms, cancel \\(h\\).")
        + "<p>Simplify \\(\\displaystyle\\frac{s(2+h)-s(2)}{h}\\) for \\(s(t)=t^2+1\\).</p>"
        + math_block(
            "\\[\\begin{aligned}"
            "\\frac{s(2+h)-s(2)}{h}"
            "&=\\frac{(2+h)^2+1-(2^2+1)}{h}\\\\"
            "&=\\frac{4+4h+h^2+1-5}{h}\\\\"
            "&=\\frac{4h+h^2}{h}=4+h\\quad (h\\neq 0)"
            "\\end{aligned}\\]"
        )
        + math_block("\\[\\lim_{h\\to 0}(4+h)=4\\]")
        + checkpoint("After simplification, the limit is visible. Without canceling \\(h\\), the expression is undefined at \\(h=0\\) — but the <em>limit</em> can still exist."),
    )
    s.add("Section 05 · Context graphs", section_divider("05", "Real contexts on graphs"), kind="section", group="divider")
    s.add(
        "Mr. Brust's trip — read the distance graph",
        role("Application", "Packet problem 1.1", "Turn around → graph is not monotone; secant slope = average rate.")
        + fig(f"{FIG}/packet_1_1_p2.png", "Mr. Brust distance-from-home \\(D(t)\\) vs. time", "ap-fig--wide")
        + "<ol class='stem-itemize ap-problem-list'>"
        "<li><strong>(a)</strong> Average speed whole trip: \\(\\dfrac{D(8)-D(0)}{8-0}\\).</li>"
        "<li><strong>(b)</strong> Average rate on \\([2,6]\\): slope of secant from \\(t=2\\) to \\(t=6\\).</li>"
        "<li><strong>(c)</strong> Shorter interval \\([2,3]\\) gives a better estimate of the rate <em>near</em> \\(t=2\\).</li>"
        "<li><strong>(d)</strong> Estimate instantaneous rate at \\(t=2\\) using \\(\\dfrac{D(2.1)-D(1.9)}{0.2}\\) (tiny interval).</li>"
        "</ol>",
    )
    s.add(
        "Social-media views — tangent interpretation",
        role("Application", "Estimate from a curve", "Views per week ≈ slope of tangent at that week.")
        + "<p>Channel views \\(v(w)\\) vs. weeks \\(w\\). At \\(w=10\\):</p>"
        + math_block("\\[\\text{Estimate} \\approx \\frac{v(10.1)-v(9.9)}{0.2}\\]")
        + warning(
            "Do not confuse <strong>average rate on an interval</strong> with <strong>instantaneous rate at a point</strong>. "
            "The notation \\(\\lim_{h\\to 0}\\frac{v(10+h)-v(10)}{h}\\) describes the latter."
        ),
    )
    s.add("Section 06 · AP practice", section_divider("06", "AP-style practice"), kind="section", group="divider")
    q = s.add(
        "Question: interpret a difference quotient",
        mcq(
            "<p>Buffalo population \\(b(t)\\), \\(t\\) = years since 1800. What does "
            "\\(\\dfrac{b(50)-b(0)}{50-0}\\) represent?</p>",
            [
                "The population in year 1850",
                "The average rate of change of population from 1800 to 1850",
                "The instantaneous rate of change at \\(t=0\\)",
                "The total population change only at \\(t=50\\)",
            ],
            "B",
            "A difference quotient over \\([0,50]\\) always describes an <em>average</em> rate on that interval.",
        ),
        kind="question",
        group="practice",
    )
    s.add(
        "Answer: buffalo population",
        answer(
            "Correct Answer: B",
            math_block("\\[\\frac{b(50)-b(0)}{50-0}=\\text{average rate of change on }[0,50]\\]")
            + "<p>Years 1800–1850: average change in population per year.</p>",
        ),
        kind="answer",
        group="practice",
        question_index=q,
        correct_choice="B",
        inline_solution=True,
        interactive=True,
    )
    q = s.add(
        "Question: instantaneous rate setup",
        mcq(
            "<p>For \\(s(t)=t^2+1\\), which expression represents the instantaneous rate at \\(t=2\\)?</p>",
            [
                "\\(\\dfrac{s(3)-s(2)}{3-2}\\)",
                "\\(\\displaystyle\\lim_{h\\to 0}\\dfrac{s(2+h)-s(2)}{h}\\)",
                "\\(s(2)\\)",
                "\\(\\dfrac{s(2+h)-s(2)}{h}\\) for a fixed \\(h=0.1\\) only",
            ],
            "B",
            "Instantaneous rate requires a limit as the interval length goes to 0.",
        ),
        kind="question",
        group="practice",
    )
    s.add(
        "Answer: instantaneous setup",
        answer(
            "Correct Answer: B",
            "<p>Only choice B uses the limit definition of instantaneous rate at \\(t=2\\).</p>",
        ),
        kind="answer",
        group="practice",
        question_index=q,
        correct_choice="B",
        inline_solution=True,
        interactive=True,
    )
    s.add("Section 07 · Practice packet", section_divider("07", "Practice packet"), kind="section", group="divider")
    s.add(
        "Download Unit 1.1 practice",
        practice_packet("1.1", "Unit 1.1 · Can change occur at an instant?"),
        kind="lesson",
        group="practice",
    )
    return {
        "slug": "ap-1-1-instantaneous-change",
        "unit": 1,
        "unit_name": "Limits and Continuity",
        "section": "1.1",
        "title": "Introducing Calculus: Can Change Occur at an Instant?",
        "deck_title": "AP Unit 1.1 · Instantaneous change",
        "slide_count": len(s.slides),
        "slides": s.slides,
        "practice_section": "1.1",
    }


def lesson_1_2() -> dict:
    s = SlideBuilder("1.2")
    s.add(
        "AP Unit 1.2 · Defining limits",
        intro(
            "1",
            "1.2",
            "Defining limits and limit notation",
            [(4, "Limit meaning"), (10, "Notation"), (16, "Value vs limit"), (22, "Graph practice"), (28, "AP MCQ")],
        ),
        kind="intro",
        group="divider",
    )
    s.add(
        "Lesson outline",
        outline(
            "1",
            "1.2",
            "Defining limits & limit notation",
            [
                (4, "Informal definition"),
                (8, "How to read \\(\\lim_{x\\to c} f(x)=L\\)"),
                (12, "Limit \\(\\neq\\) function value"),
                (16, "Piecewise worked example"),
                (20, "Packet graph problems"),
                (24, "True / false reasoning"),
                (28, "Practice packet"),
            ],
        ),
        kind="content",
        group="divider",
    )
    s.add("Section 01 · What is a limit?", section_divider("01", "What a limit means"), kind="section", group="divider")
    s.add(
        "Informal definition",
        role("Knowledge Point", "Approach, not necessarily equal", "A limit describes behavior near a point.")
        + definition(
            "Limit at a point (informal)",
            math_block("\\[\\lim_{x\\to c} f(x)=L\\]")
            + "<p>means: as \\(x\\) gets <strong>arbitrarily close</strong> to \\(c\\) (but not necessarily equal to \\(c\\)), "
            "the values \\(f(x)\\) get arbitrarily close to \\(L\\).</p>",
        )
        + key_point(
            "Read it aloud",
            "<p>“The limit of \\(f(x)\\) as \\(x\\) approaches \\(c\\) is \\(L\\).”</p>"
            + "<p>The arrow \\(x\\to c\\) always refers to the <strong>input</strong> variable.</p>",
        ),
    )
    s.add(
        "Formal precision (optional)",
        role("Extension", "ε–δ definition", "AP may reference this for rigor; focus on the idea first.")
        + definition(
            "Limit (precise)",
            math_block(
                "\\[\\forall \\varepsilon>0,\\ \\exists \\delta>0:\\ "
                "0<|x-c|<\\delta \\Rightarrow |f(x)-L|<\\varepsilon\\]"
            )
            + "<p>For every tolerance \\(\\varepsilon\\) on outputs, we can find a distance \\(\\delta\\) on inputs that forces \\(f(x)\\) within \\(\\varepsilon\\) of \\(L\\).</p>",
        ),
    )
    s.add("Section 02 · Notation reference", section_divider("02", "Limit notation cheat sheet"), kind="section", group="divider")
    s.add(
        "Notation you must read fluently",
        role("Reference", "Symbols → meaning", "Say the limit before computing.")
        + "<table class='ap-data-table ap-notation-table'>"
        "<thead><tr><th>Symbol</th><th>Meaning</th></tr></thead><tbody>"
        "<tr><td>\\(\\lim_{x\\to 3} f(x)=5\\)</td><td>As \\(x\\to 3\\), outputs approach 5</td></tr>"
        "<tr><td>\\(\\lim_{x\\to 3^-} f(x)\\)</td><td>Approach from the left (\\(x<3\\))</td></tr>"
        "<tr><td>\\(\\lim_{x\\to 3^+} f(x)\\)</td><td>Approach from the right (\\(x>3\\))</td></tr>"
        "<tr><td>\\(f(3)\\)</td><td>Actual function value at \\(x=3\\) (may differ from the limit)</td></tr>"
        "</tbody></table>"
        + warning("A limit statement never guarantees \\(f(c)=L\\). Always check the graph for a filled dot vs. open circle."),
    )
    s.add("Section 03 · Value vs limit", section_divider("03", "Function value vs limit"), kind="section", group="divider")
    s.add(
        "Piecewise example — limit exists but value differs",
        role("Worked Example", "Compare \\(\\lim\\) and \\(f(c)\\)", "Simplify on both sides of the hole.")
        + "<p>\\(f(x)=x+2\\) for \\(x\\neq 3\\), and \\(f(3)=10\\).</p>"
        + math_block(
            "\\[\\lim_{x\\to 3} f(x)=\\lim_{x\\to 3}(x+2)=5,\\qquad f(3)=10\\]"
        )
        + key_point(
            "When can they differ?",
            "<ul class='stem-itemize'>"
            "<li>Removable hole: open circle at \\((c,L)\\), filled dot elsewhere</li>"
            "<li>Undefined at \\(c\\) but limit still exists</li>"
            "</ul>",
        ),
    )
    s.add("Section 04 · Graph practice", section_divider("04", "Limits from the packet graph"), kind="section", group="divider")
    s.add(
        "Packet 1.2 — read limits from the graph",
        role("Graphical Skill", "Left, right, then two-sided", "Use the same graph for all items.")
        + fig(f"{FIG}/packet_1_2_p1.png", "Packet 1.2 · Limit notation with graphs", "ap-fig--wide")
        + fig(f"{FIG}/limit_graph_quiz.svg", "Reference graph for limit exercises")
        + "<ol class='stem-itemize ap-problem-list'>"
        "<li>\\(\\displaystyle\\lim_{x\\to 1} f(x)\\) — approach from both sides</li>"
        "<li>\\(f(-3)\\) — function <em>value</em>, not a limit</li>"
        "<li>\\(\\displaystyle\\lim_{x\\to 2} f(x)\\) — check left vs. right</li>"
        "<li>\\(f(2)\\) vs. \\(\\displaystyle\\lim_{x\\to 2} f(x)\\) — may differ</li>"
        "</ol>",
    )
    s.add(
        "Interpretation in words",
        role("Application", "Translate notation", "AP free-response often asks for verbal interpretation.")
        + definition(
            "Verbal form",
            "<p>\\(\\displaystyle\\lim_{x\\to 7} f(x)=10\\) means:</p>"
            "<p><em>As \\(x\\) approaches 7, the values of \\(f(x)\\) approach 10.</em></p>",
        )
        + checkpoint(
            "True or false? \\(f(1)=\\displaystyle\\lim_{x\\to 1} f(x)\\) in <strong>all</strong> cases. "
            "<strong>False.</strong> Counterexample: any removable discontinuity."
        ),
    )
    s.add("Section 05 · AP practice", section_divider("05", "AP-style multiple choice"), kind="section", group="divider")
    q = s.add(
        "Question: best interpretation",
        mcq(
            "<p>Which is the best interpretation of \\(\\displaystyle\\lim_{x\\to 4} f(x)=8\\)?</p>",
            [
                "The value of \\(f\\) at \\(x=4\\) is 8",
                "The value of \\(f\\) at \\(x=8\\) is 4",
                "As \\(x\\) approaches 4, the values of \\(f(x)\\) approach 8",
                "As \\(x\\) approaches 8, the values of \\(f(x)\\) approach 4",
            ],
            "C",
            "Match input approach (\\(x\\to 4\\)) with output approach (\\(\\to 8\\)).",
        ),
        kind="question",
        group="practice",
    )
    s.add(
        "Answer: interpretation",
        answer("Correct Answer: C", "<p>Limits describe approaching behavior — choice C.</p>"),
        kind="answer",
        group="practice",
        question_index=q,
        correct_choice="C",
        inline_solution=True,
        interactive=True,
    )
    q = s.add(
        "Question: limit at x = −1",
        mcq(
            "<p>Which is the best interpretation of \\(\\displaystyle\\lim_{x\\to -1} f(x)=2\\)?</p>",
            [
                "As \\(x\\) approaches 2, \\(f(x)\\) approaches \\(-1\\)",
                "The value of \\(f\\) at \\(x=-1\\) is 2",
                "The value of \\(f\\) at \\(x=2\\) is \\(-1\\)",
                "As \\(x\\) approaches \\(-1\\), the values of \\(f(x)\\) approach 2",
            ],
            "D",
            "Read the arrow on the input: \\(x\\to -1\\).",
        ),
        kind="question",
        group="practice",
    )
    s.add(
        "Answer: limit at −1",
        answer("Correct Answer: D", "<p>Input approaches \\(-1\\); outputs approach 2.</p>"),
        kind="answer",
        group="practice",
        question_index=q,
        correct_choice="D",
        inline_solution=True,
        interactive=True,
    )
    q = s.add(
        "Question: f(1) vs limit",
        mcq(
            "<p>On a graph, \\(\\displaystyle\\lim_{x\\to 1} f(x)=3\\) but \\(f(1)=5\\). Which is true?</p>",
            [
                "The limit does not exist",
                "\\(f\\) is continuous at \\(x=1\\)",
                "The limit exists but \\(f(1)\\neq\\displaystyle\\lim_{x\\to 1} f(x)\\)",
                "We cannot determine the limit from the graph",
            ],
            "C",
            "A limit can exist even when the function value differs.",
        ),
        kind="question",
        group="practice",
    )
    s.add(
        "Answer: f(1) vs limit",
        answer("Correct Answer: C", "<p>Limit 3, value 5 — removable-type mismatch.</p>"),
        kind="answer",
        group="practice",
        question_index=q,
        correct_choice="C",
        inline_solution=True,
        interactive=True,
    )
    s.add("Section 06 · Practice packet", section_divider("06", "Practice packet"), kind="section", group="divider")
    s.add("Download Unit 1.2 practice", practice_packet("1.2", "Unit 1.2 · Defining limits"), kind="lesson", group="practice")
    return {
        "slug": "ap-1-2-defining-limits",
        "unit": 1,
        "unit_name": "Limits and Continuity",
        "section": "1.2",
        "title": "Defining Limits and Using Limit Notation",
        "deck_title": "AP Unit 1.2 · Defining limits",
        "slide_count": len(s.slides),
        "slides": s.slides,
        "practice_section": "1.2",
    }


def lesson_1_3() -> dict:
    s = SlideBuilder("1.3")
    s.add(
        "AP Unit 1.3 · Limits from graphs",
        intro(
            "1",
            "1.3",
            "Estimating limit values from graphs",
            [(4, "One-sided limits"), (10, "Two-sided limits"), (16, "Jump & holes"), (22, "Sketching"), (28, "AP MCQ")],
        ),
        kind="intro",
        group="divider",
    )
    s.add(
        "Lesson outline",
        outline(
            "1",
            "1.3",
            "Estimating limits from graphs",
            [
                (4, "One-sided limits"),
                (8, "When two-sided limits exist"),
                (12, "Piecewise graph example"),
                (16, "Jump discontinuity"),
                (20, "Packet examples"),
                (24, "Graph checklist"),
                (28, "Practice packet"),
            ],
        ),
        kind="content",
        group="divider",
    )
    s.add("Section 01 · One-sided limits", section_divider("01", "One-sided limits"), kind="section", group="divider")
    s.add(
        "Definition: approach from one side",
        role("Knowledge Point", "Left vs right", "Superscript − and + tell you which direction.")
        + definition(
            "One-sided limits",
            math_block(
                "\\[\\lim_{x\\to c^-} f(x)=L \\quad\\text{(from the left)},\\qquad "
                "\\lim_{x\\to c^+} f(x)=M \\quad\\text{(from the right)}\\]"
            )
            + "<p>A <strong>one-sided limit</strong> is the value \\(f(x)\\) approaches as \\(x\\) nears \\(c\\) from one side only.</p>",
        )
        + fig(f"{FIG}/jump_discontinuity.svg", "Jump at \\(x=3\\): \\(\\lim_{x\\to 3^-}=-1\\), \\(\\lim_{x\\to 3^+}=2\\)"),
    )
    s.add(
        "Two-sided limit exists only when sides agree",
        role("Knowledge Point", "Combine one-sided limits", "Different sides → DNE.")
        + definition(
            "Two-sided limit",
            math_block(
                "\\[\\lim_{x\\to c} f(x)=L \\iff "
                "\\lim_{x\\to c^-} f(x)=\\lim_{x\\to c^+} f(x)=L\\]"
            )
        )
        + checkpoint("If left and right limits differ, the two-sided limit <strong>does not exist</strong> (even if \\(f(c)\\) is defined)."),
    )
    s.add("Section 02 · Piecewise graph", section_divider("02", "Classic piecewise graph"), kind="section", group="divider")
    s.add(
        "Read limits at x = 2",
        role("Worked Example", "Follow the graph checklist", "Open circle = limit; filled dot = function value.")
        + fig(f"{FIG}/limit_piecewise_at_2.svg", "Piecewise graph: limit at \\(x=2\\) is 3, but \\(f(2)=1.5\\)")
        + math_block(
            "\\[\\lim_{x\\to 2^-} f(x)=3,\\quad \\lim_{x\\to 2^+} f(x)=3,\\quad "
            "\\lim_{x\\to 2} f(x)=3,\\quad f(2)=1.5\\]"
        )
        + warning("\\(\\displaystyle\\lim_{x\\to 2} f(x)\\neq f(2)\\) — so \\(f\\) is <strong>not continuous</strong> at \\(x=2\\)."),
    )
    s.add("Section 03 · Packet graphs", section_divider("03", "Packet 1.3 exercises"), kind="section", group="divider")
    s.add(
        "Packet 1.3 — one-sided limits from graphs",
        role("Application", "Packet examples 1–3", "Work each limit from the graph before revealing solutions.")
        + fig(f"{FIG}/packet_1_3_p1.png", "Packet 1.3 · One-sided limits at \\(x=3\\)", "ap-fig--wide")
        + "<ol class='stem-itemize ap-problem-list'>"
        "<li>\\(\\displaystyle\\lim_{x\\to 3^-} f(x)=-1\\), \\(\\displaystyle\\lim_{x\\to 3^+} f(x)=2\\) → \\(\\displaystyle\\lim_{x\\to 3} f(x)\\) DNE</li>"
        "<li>At \\(x=-2\\): compare left and right limits</li>"
        "<li>Sketch \\(g\\) with \\(g(3)=-1\\), \\(\\displaystyle\\lim_{x\\to 3} g(x)=4\\), increasing on \\((-2,3)\\)</li>"
        "</ol>",
    )
    s.add(
        "Graph reading checklist",
        role("Reference", "Four questions every time", "Use this on every AP graph problem.")
        + key_point(
            "Graph checklist",
            "<ol class='stem-itemize'>"
            "<li>What does the graph approach from the <strong>left</strong>?</li>"
            "<li>What does the graph approach from the <strong>right</strong>?</li>"
            "<li>Are those values <strong>equal</strong>?</li>"
            "<li>Where is the <strong>filled dot</strong> (actual function value)?</li>"
            "</ol>",
        )
        + fig(f"{FIG}/packet_1_3_p2.png", "Additional packet graph exercises", "ap-fig--wide"),
    )
    s.add("Section 04 · Sketching", section_divider("04", "Sketching with constraints"), kind="section", group="divider")
    s.add(
        "Design a graph satisfying all conditions",
        role("Worked Example", "Open vs closed dots", "Constraints on value, limit, and monotonicity.")
        + "<p>Sketch \\(g\\) such that:</p>"
        + "<ul class='stem-itemize'>"
        "<li>\\(g(3)=-1\\) (filled dot at \\((3,-1)\\))</li>"
        "<li>\\(\\displaystyle\\lim_{x\\to 3} g(x)=4\\) (open circle at \\((3,4)\\))</li>"
        "<li>\\(g\\) increasing on \\((-2,3)\\)</li>"
        "</ul>"
        + checkpoint("Increasing on \\((-2,3)\\) means as \\(x\\) increases toward 3, \\(g(x)\\) increases — the graph rises toward the open circle at height 4."),
    )
    s.add("Section 05 · AP practice", section_divider("05", "AP-style multiple choice"), kind="section", group="divider")
    q = s.add(
        "Question: jump discontinuity",
        mcq(
            "<p>At \\(x=b\\), \\(\\displaystyle\\lim_{x\\to b^-} f(x)=3\\) and \\(\\displaystyle\\lim_{x\\to b^+} f(x)=5\\). Which is true?</p>",
            [
                "\\(\\displaystyle\\lim_{x\\to b} f(x)=4\\)",
                "\\(\\displaystyle\\lim_{x\\to b} f(x)=5\\)",
                "\\(\\displaystyle\\lim_{x\\to b} f(x)\\) does not exist",
                "\\(\\displaystyle\\lim_{x\\to b} f(x)=3\\)",
            ],
            "C",
            "Mismatched one-sided limits ⇒ two-sided limit DNE.",
        ),
        kind="question",
        group="practice",
    )
    s.add(
        "Answer: jump",
        answer("Correct Answer: C", "<p>Left limit 3, right limit 5 — two-sided limit does not exist.</p>"),
        kind="answer",
        group="practice",
        question_index=q,
        correct_choice="C",
        inline_solution=True,
        interactive=True,
    )
    q = s.add(
        "Question: read the piecewise graph",
        mcq(
            "<p>Using the piecewise graph at \\(x=2\\) (open circle at \\((2,3)\\), filled dot at \\((2,1.5)\\)), "
            "what is \\(\\displaystyle\\lim_{x\\to 2} f(x)\\)?</p>",
            [
                "1.5",
                "3",
                "Does not exist",
                "2.25",
            ],
            "B",
            "The limit is the \\(y\\)-value approached from both sides — the open circle height.",
        ),
        kind="question",
        group="practice",
    )
    s.add(
        "Answer: piecewise at 2",
        answer("Correct Answer: B", "<p>Both sides approach \\(y=3\\); \\(f(2)=1.5\\) is separate.</p>"),
        kind="answer",
        group="practice",
        question_index=q,
        correct_choice="B",
        inline_solution=True,
        interactive=True,
    )
    s.add("Section 06 · Practice packet", section_divider("06", "Practice packet"), kind="section", group="divider")
    s.add("Download Unit 1.3 practice", practice_packet("1.3", "Unit 1.3 · Limits from graphs"), kind="lesson", group="practice")
    return {
        "slug": "ap-1-3-limits-from-graphs",
        "unit": 1,
        "unit_name": "Limits and Continuity",
        "section": "1.3",
        "title": "Estimating Limit Values from Graphs",
        "deck_title": "AP Unit 1.3 · Limits from graphs",
        "slide_count": len(s.slides),
        "slides": s.slides,
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
    print(f"Wrote {OUTPUT} ({payload['total']} lessons, {sum(m['slide_count'] for m in payload['materials'])} slides)")


if __name__ == "__main__":
    main()
