"""AP Calculus Unit 1.1 lesson builder."""
from __future__ import annotations

from ap_calc_slide_helpers import (
    SlideBuilder,
    big_idea,
    checkpoint,
    concept_frame,
    data_table,
    definition,
    exit_ticket,
    fig,
    guided_example,
    intro,
    key_point,
    limit_card,
    math_block,
    rate_card,
    mcq_reveal,
    phase_divider,
    practice_packet,
    role,
    secant_interactive_embed,
    solution_steps,
    warning,
    worked_example,
)


def build(graphs: dict[str, str]) -> dict:
    s = SlideBuilder("1.1")
    g = graphs

    s.add(
        "1.1 · Can change occur at an instant?",
        intro("1", "1.1", "Can change occur at an instant?", [
            (2, "Launch"), (5, "Visual"), (9, "Concept"), (13, "Practice"), (15, "Exit"),
        ]),
        kind="intro", group="divider", path_phase="Launch",
    )

    s.add(
        "Why we need calculus",
        phase_divider("Launch", "Motion at an instant")
        + role("Launch", "A speedometer moment", "Average speed is easy; instantaneous speed is not.")
        + big_idea(
            "<p>A car travels 60 miles in 2 hours — average speed is <strong>30 mph</strong>. "
            "But what does the speedometer read at <em>exactly</em> 1:00 PM?</p>"
            "<p>That is not an average over time. It is a rate <strong>at an instant</strong>.</p>"
        )
        + concept_frame(
            "Instantaneous rate asks how fast something changes at one input value.",
            "This question leads to derivatives and the limit idea.",
            "Words like “at t = 2 exactly” or “at this moment.”",
            "Using a long interval and calling it instantaneous.",
            "Shrink the interval and see if the average rates stabilize.",
        ),
        path_phase="Launch",
    )

    s.add(
        "Position graph s(t) = t² + 1",
        phase_divider("Visual Investigation", "Position vs time")
        + role("Visual", "Read the curve", "Slope of a secant = average rate on that time interval.")
        + fig(
            g["s_parabola_11"],
            "Position function \\(s(t) = t^2 + 1\\) (meters)",
            cls="ap-fig--teach",
            notice="Slope of the secant \\(=\\dfrac{\\Delta s}{\\Delta t}\\) — steeper as \\(t\\) increases.",
        ),
        path_phase="Visual Investigation",
    )

    s.add(
        "Average rate of change",
        phase_divider("Concept & Definition", "Average rate of change")
        + definition(
            "Average rate of change on [a, b]",
            math_block("\\[\\text{Average rate}=\\frac{s(b)-s(a)}{b-a}\\]")
            + "<p>Geometrically: <strong>slope of the secant line</strong> connecting the two points on the graph.</p>"
            + "<p>Units: (output units) per (input unit) — here, meters per second.</p>",
        )
        + key_point(
            "At t = 2",
            math_block("\\[\\frac{s(3)-s(2)}{3-2}=\\frac{10-5}{1}=5\\ \\text{m/s}\\]")
            + "<p>This is the average velocity from t = 2 s to t = 3 s — not the velocity <em>at</em> t = 2.</p>",
        ),
        path_phase="Concept & Definition",
    )

    s.add(
        "Shrinking the interval — numeric evidence",
        phase_divider("Visual Investigation", "Table of average rates")
        + role("Visual", "Let h → 0", "Use both positive and negative h to approach t = 2.")
        + data_table(
            ["h", "Interval", "Average rate (slope)"],
            [
                ["1", "[2, 3]", "5"],
                ["0.5", "[2, 2.5]", "4.5"],
                ["0.1", "[2, 2.1]", "4.1"],
                ["0.01", "[2, 2.01]", "4.01"],
                ["−0.1", "[1.9, 2]", "3.9"],
                ["−0.01", "[1.99, 2]", "3.99"],
            ],
        )
        + limit_card("h\\to 0", expr="\\dfrac{s(2+h)-s(2)}{h}", equals="4")
        + checkpoint(
            "From both sides, average rates approach <strong>4</strong>. "
            "That limiting value is the instantaneous rate at \\(t=2\\)."
        ),
        path_phase="Visual Investigation",
    )

    s.add(
        "Secant → tangent",
        secant_interactive_embed(),
        template="investigation",
        path_phase="Visual Investigation",
    )

    s.add(
        "The difference quotient",
        phase_divider("Concept & Definition", "Difference quotient")
        + definition(
            "Difference quotient at t = a",
            math_block("\\[\\frac{s(a+h)-s(a)}{h}\\]")
            + "<ul class='stem-itemize'>"
            "<li><strong>s(a+h) − s(a)</strong> — vertical rise Δs on the graph</li>"
            "<li><strong>h</strong> — horizontal run (time interval)</li>"
            "<li><strong>Quotient</strong> — secant slope = rise ÷ run</li>"
            "</ul>",
        )
        + fig(
            g["diff_quotient_11"],
            "Geometric meaning of the difference quotient",
            cls="ap-fig--teach",
            notice="\\(\\Delta s\\) = rise, \\(h\\) = run, \\(\\dfrac{\\Delta s}{h}\\) = secant slope.",
        )
        + key_point(
            "Preview only",
            "We will formalize approach in Section 1.2. Here: shorter intervals "
            "\\(\\Rightarrow\\) secant slope \\(\\Rightarrow\\) instantaneous rate.",
        ),
        path_phase="Concept & Definition",
    )

    s.add(
        "Why shrinking the interval works",
        phase_divider("Why It Works", "From average to instantaneous")
        + role("Reason", "Same idea on both sides", "Average rates stabilize when the interval is tiny.")
        + big_idea(
            "<p>When \\(h\\) is small, the secant slope \\(\\dfrac{s(a+h)-s(a)}{h}\\) measures change over a "
            "<strong>short</strong> interval — closer to what happens <em>at</em> \\(t=a\\).</p>"
            "<p>If left-side (\\(h&lt;0\\)) and right-side (\\(h&gt;0\\)) averages approach the <strong>same number</strong>, "
            "that common value is the instantaneous rate.</p>"
        )
        + checkpoint("We are not claiming \\(h=0\\). We observe a <em>pattern</em> as \\(h\\to 0\\)."),
        path_phase="Why It Works",
    )

    s.add(
        "Worked example: simplify the difference quotient",
        worked_example(
            "s(t) = t² + 1 at t = 2",
            "Find the instantaneous rate at t = 2 by simplifying the difference quotient.",
            "Algebra + table + secant graph all describe the same limiting slope.",
            solution_steps([
                "Build: \\(\\dfrac{s(2+h)-s(2)}{h}=\\dfrac{(2+h)^2+1-5}{h}\\).",
                "Expand: \\((2+h)^2+1-5 = 4+4h+h^2\\).",
                "Simplify: \\(\\dfrac{4h+h^2}{h}=4+h\\) for \\(h\\neq 0\\).",
                "Interpret: as \\(h\\to 0\\), the rate approaches \\(4\\) m/s.",
            ]),
            "The instantaneous rate of change of s at t = 2 is <strong>4 m/s</strong>.",
            "Secant slope on [2, 2.01] ≈ 4.01; tangent slope matches 4.",
        ),
        path_phase="Worked Example",
    )

    s.add(
        "Error analysis: plugging in h = 0",
        phase_divider("Contrast / Error Analysis", "Why h = 0 is not allowed yet")
        + warning(
            "<p>Substituting \\(h=0\\) gives \\(\\dfrac{s(2)-s(2)}{0}=\\dfrac{0}{0}\\), which is <strong>undefined</strong>.</p>"
            "<p><strong>Why wrong:</strong> \\(h=0\\) means “no interval,” so the difference quotient does not describe a secant slope.</p>"
            "<p><strong>Correct move:</strong> simplify algebraically first, <em>then</em> let \\(h\\to 0\\).</p>"
        ),
        path_phase="Contrast / Error Analysis",
    )

    s.add(
        "Guided: average rate from a table",
        guided_example(
            "<p>For \\(s(t)=t^2+1\\), use the table to estimate the instantaneous rate at \\(t=2\\).</p>"
            + data_table(["h", "Avg rate"], [["0.1", "4.1"], ["0.01", "4.01"], ["−0.01", "3.99"]]),
            [
                "What value are the average rates approaching?",
                "Does the left side (negative h) agree with the right side?",
                "State the instantaneous rate with units.",
            ],
            "<p><strong>Solution:</strong> Rates approach <strong>4 m/s</strong>. Left and right agree → instantaneous rate ≈ 4 m/s.</p>",
        ),
        path_phase="Guided Example",
        group="practice",
    )

    s.add(
        "Practice: compute an average rate",
        mcq_reveal(
            "<p>For \\(s(t)=t^2+1\\), what is the average rate of change on \\([1,4]\\)?</p>",
            [
                "\\(\\dfrac{s(4)-s(1)}{3}=5\\)",
                "\\(\\dfrac{s(4)-s(1)}{4}=\\dfrac{15}{4}\\)",
                "\\(s(4)-s(1)=16\\)",
                "\\(\\dfrac{s(1)-s(4)}{3}=-5\\)",
            ],
            "A",
            "Use (change in output) / (change in input) on [1, 4].",
            "<p>\\(s(4)=17\\), \\(s(1)=2\\), so average rate \\(=\\dfrac{17-2}{4-1}=5\\). "
            "<strong>B</strong> uses wrong denominator. <strong>C</strong> omits division by time. "
            "<strong>D</strong> reverses the interval sign. <strong>A</strong> is correct.</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: interpret a difference quotient",
        mcq_reveal(
            "<p>Buffalo population \\(b(t)\\), \\(t\\) years since 1800. What does \\(\\dfrac{b(50)-b(0)}{50}\\) represent?</p>",
            [
                "Population in year 1850",
                "Average rate of change of population from 1800 to 1850",
                "Instantaneous rate in 1800",
                "Total change only at t = 50",
            ],
            "B",
            "Interval in denominator → average, not instantaneous.",
            "<p><strong>A</strong> confuses a rate with a population value. "
            "<strong>C</strong> needs a limit of a difference quotient. "
            "<strong>D</strong> misreads “average over 50 years.” "
            "<strong>B</strong> is correct: average rate on [0, 50].</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: instantaneous rate setup",
        mcq_reveal(
            "<p>Which expression represents the instantaneous rate of \\(s(t)=t^2+1\\) at \\(t=2\\)?</p>",
            [
                "\\(\\dfrac{s(3)-s(2)}{1}\\)",
                "\\(\\displaystyle\\lim_{h\\to 0}\\dfrac{s(2+h)-s(2)}{h}\\)",
                "\\(s(2)\\)",
                "\\(\\dfrac{s(2.1)-s(2)}{0.1}\\) only",
            ],
            "B",
            "Instantaneous requires a limiting process, not one finite interval.",
            "<p><strong>A, D</strong> are average rates on one interval. "
            "<strong>C</strong> is position, not rate. "
            "<strong>B</strong> is the definition of instantaneous rate.</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Exit ticket · 1.1",
        exit_ticket([
            (
                "State the average rate of \\(s(t)=t^2+1\\) on \\([2,3]\\) and interpret it.",
                "<p>\\(\\dfrac{s(3)-s(2)}{1}=5\\) m/s — average velocity from t=2 to t=3.</p>",
            ),
            (
                "Simplify \\(\\dfrac{s(2+h)-s(2)}{h}\\) and state the instantaneous rate at \\(t=2\\).",
                "<p>Simplifies to \\(4+h\\); instantaneous rate is <strong>4</strong> m/s.</p>",
            ),
            (
                "Why can't we substitute \\(h=0\\) into the difference quotient before simplifying?",
                "<p>It gives \\(0/0\\) — undefined. We need \\(h\\neq 0\\) for a secant slope.</p>",
            ),
        ]),
        path_phase="Exit Ticket", group="practice",
    )

    s.add(
        "Practice packet · 1.1",
        practice_packet("1.1", "Unit 1.1 · Can change occur at an instant?"),
        kind="lesson", group="practice", path_phase="Packet",
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
