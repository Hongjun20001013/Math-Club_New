"""AP Calculus Unit 1.3 lesson builder."""
from __future__ import annotations

from ap_calc_slide_helpers import (
    SlideBuilder,
    big_idea,
    checkpoint,
    concept_frame,
    definition,
    exit_ticket,
    fig,
    guided_example,
    intro,
    key_point,
    limit_tracer_embed,
    limit_card,
    math_block,
    NOTICE_HOLE,
    NOTICE_INFINITE,
    NOTICE_JUMP_DNE,
    NOTICE_LIMIT_EQ_FC,
    visual_limit_vs_value,
    mcq_reveal,
    phase_divider,
    practice_packet,
    role,
    solution_steps,
    warning,
    worked_example,
)


def build(graphs: dict[str, str]) -> dict:
    s = SlideBuilder("1.3")
    g = graphs

    s.add(
        "1.3 · Limits from graphs",
        intro("1", "1.3", "Estimating limits from graphs", [
            (2, "Procedure"), (6, "One-sided"), (11, "Cases"), (16, "Practice"), (21, "Exit"),
        ]),
        kind="intro", group="divider",
    )

    s.add(
        "The four-step graph procedure",
        phase_divider("Launch", "Left → Right → Compare → Value")
        + role("Launch", "A stable routine", "Use the same steps on every graph problem.")
        + big_idea(
            "<ol class='ap-procedure-list'>"
            "<li><strong>Trace from the left</strong> — \\(x\\to c^{-}\\)</li>"
            "<li><strong>Trace from the right</strong> — \\(x\\to c^{+}\\)</li>"
            "<li><strong>Compare</strong> — equal heights → two-sided limit exists</li>"
            "<li><strong>Inspect the filled point</strong> — \\(f(c)\\), only after limits</li>"
            "</ol>"
        )
        + concept_frame(
            "Estimate limits by approaching c on each side of the graph.",
            "Graphs appear on every AP exam before algebraic limit rules.",
            "Open circle vs filled dot; left vs right branch heights.",
            "Reading the filled dot before comparing sides.",
            "Re-trace both branches; label \\(L^{-}\\) and \\(L^{+}\\) before deciding.",
        ),
        path_phase="Launch",
    )

    s.add(
        "One-sided limits",
        phase_divider("Concept & Definition", "One-sided limits")
        + definition(
            "Left-hand and right-hand limits",
            math_block(
                "\\[\\lim_{x\\to c^-} f(x)=L \\quad\\text{(from left)},\\qquad "
                "\\lim_{x\\to c^+} f(x)=M \\quad\\text{(from right)}\\]"
            )
            + "<p>Superscript − means \\(x \\lt c\\); superscript + means \\(x \\gt c\\).</p>",
        )
        + limit_card("x\\to 3^-", equals="-1")
        + limit_card("x\\to 3^+", equals="4")
        + fig(g["jump_at_3"], "Jump at \\(x=3\\)", cls="ap-fig--teach", notice=NOTICE_JUMP_DNE),
        path_phase="Concept & Definition",
    )

    s.add(
        "Two-sided limit exists when sides agree",
        phase_divider("Why It Works", "Combining one-sided limits")
        + definition(
            "Two-sided limit",
            math_block(
                "\\[\\lim_{x\\to c} f(x)=L \\iff "
                "\\lim_{x\\to c^-} f(x)=\\lim_{x\\to c^+} f(x)=L\\]"
            )
        )
        + visual_limit_vs_value("2", "3", fc_val="1.5")
        + checkpoint(
            "If \\(L^{-}\\neq L^{+}\\), then "
            "\\(\\displaystyle\\lim_{x\\to c} f(x)\\) <strong>does not exist</strong>."
        ),
        path_phase="Why It Works",
    )

    s.add(
        "Worked example: piecewise at x = 2",
        worked_example(
            "Read limits at x = 2",
            "Find \\(\\lim_{x\\to 2} f(x)\\), \\(f(2)\\), and continuity at x=2.",
            "Graph: left branch y = x+1, right branch y = −x+5.",
            solution_steps([
                "Left trace: as \\(x\\to 2^{-}\\), \\(y\\to 3\\).",
                "Right trace: as \\(x\\to 2^{+}\\), \\(y\\to 3\\).",
                "Compare: both sides \\(\\to 3\\), so \\(\\displaystyle\\lim_{x\\to 2} f(x)=3\\).",
                "Filled dot at \\((2,1.5)\\) gives \\(f(2)=1.5\\neq 3\\) \\(\\Rightarrow\\) not continuous.",
            ]),
            "\\(\\displaystyle\\lim_{x\\to 2} f(x)=3\\), \\(f(2)=1.5\\), not continuous at 2.",
            "Open circle at height 3; filled dot at 1.5.",
        )
        + limit_tracer_embed(),
        path_phase="Worked Example",
    )

    s.add(
        "Case gallery: continuity types",
        phase_divider("Visual Investigation", "Compare discontinuity types")
        + '<div class="ap-graph-grid ap-graph-grid--gallery">'
        + fig(g["limit_case_a_gallery"], "Continuous", cls="ap-fig--gallery", notice=NOTICE_LIMIT_EQ_FC)
        + fig(g["removable_hole_gallery"], "Removable hole", cls="ap-fig--gallery", notice=NOTICE_HOLE)
        + fig(g["jump_at_3_gallery"], "Jump", cls="ap-fig--gallery", notice=NOTICE_JUMP_DNE)
        + fig(g["infinite_limit_13_gallery"], "Infinite (extension)", cls="ap-fig--gallery", notice=NOTICE_INFINITE)
        + "</div>",
        path_phase="Visual Investigation",
    )

    s.add(
        "Endpoint and one-sided domain",
        phase_divider("Representation Transfer", "When only one side exists")
        + role("Transfer", "Domain matters", "At an endpoint, a left-hand limit may be undefined.")
        + limit_card("x\\to 0^+", equals="0")
        + fig(
            g["endpoint_sqrt_13"],
            "\\(f(x)=\\sqrt{x}\\) on \\([0,4]\\)",
            cls="ap-fig--teach",
            notice="At \\(x=0\\) only \\(x\\to 0^{+}\\) is in the domain.",
        )
        + key_point(
            "At x = 0",
            "<p>\\(\\displaystyle\\lim_{x\\to 0^+} f(x)=0\\). There is <strong>no</strong> left-hand approach on this domain.</p>",
        ),
        path_phase="Representation Transfer",
    )

    s.add(
        "Worked example: jump discontinuity",
        worked_example(
            "Jump at x = 3",
            "Determine \\(\\lim_{x\\to 3} f(x)\\) from the jump graph.",
            "Use left trace, right trace, compare.",
            solution_steps([
                "Left: \\(\\lim_{x\\to 3^-} f(x)=-1\\).",
                "Right: \\(\\lim_{x\\to 3^+} f(x)=4\\).",
                "Compare: −1 ≠ 4.",
                "Conclusion: \\(\\displaystyle\\lim_{x\\to 3} f(x)\\) does not exist.",
            ]),
            "Two-sided limit DNE because one-sided limits disagree.",
            "A filled dot at f(3) would not repair the jump.",
        ),
        path_phase="Worked Example",
    )

    s.add(
        "Guided: trace from the left",
        guided_example(
            "<p>Use the piecewise graph at x=2. What is \\(\\displaystyle\\lim_{x\\to 2^-} f(x)\\)?</p>"
            + fig(g["piecewise_limit_2"], "Reference graph", cls="ap-fig--practice", notice="Follow left branch only."),
            ["Start at x < 2 on the left branch.", "Move toward x = 2 along that branch.", "Record the y-value approached."],
            "<p><strong>Solution:</strong> Left branch y = x+1 approaches <strong>3</strong>.</p>",
        ),
        group="practice", path_phase="Guided Example",
    )

    s.add(
        "Guided: compare sides",
        guided_example(
            "<p>For the jump graph at x=3, find \\(\\lim_{x\\to 3^-} f(x)\\), \\(\\lim_{x\\to 3^+} f(x)\\), and \\(\\lim_{x\\to 3} f(x)\\).</p>"
            + fig(g["jump_at_3"], "Jump graph", cls="ap-fig--practice"),
            ["Trace left branch to x=3.", "Trace right branch to x=3.", "Are the heights equal?"],
            "<p>\\(L^{-}=-1\\), \\(L^{+}=4\\), "
            "\\(\\displaystyle\\lim_{x\\to 3} f(x)\\) <strong>DNE</strong>.</p>",
        ),
        group="practice", path_phase="Guided Example",
    )

    s.add(
        "Guided: sketch with constraints",
        guided_example(
            "<p>Sketch a graph such that \\(\\lim_{x\\to 2^-} f(x)=3\\), \\(\\lim_{x\\to 2^+} f(x)=3\\), but \\(f(2)=-1\\).</p>",
            ["Draw open circle at (2, 3).", "Draw branches approaching that open circle.", "Place filled dot at (2, −1)."],
            fig(
                g["sketch_task_13"],
                "One valid sketch",
                cls="ap-fig--practice",
                notice="\\(\\displaystyle\\lim_{x\\to 2} f(x)=3\\); \\(f(2)=-1\\).",
            )
            + "<p>Your sketch may differ in shape — check open vs filled points and branch heights.</p>",
        ),
        group="practice", path_phase="Guided Example",
    )

    s.add(
        "Practice: jump discontinuity",
        mcq_reveal(
            "<p>Left limit 3, right limit 5 at x=b. Which is true?</p>",
            [
                "\\(\\displaystyle\\lim_{x\\to b} f(x)=4\\)",
                "\\(\\displaystyle\\lim_{x\\to b} f(x)=5\\)",
                "\\(\\displaystyle\\lim_{x\\to b} f(x)\\) DNE",
                "\\(\\displaystyle\\lim_{x\\to b} f(x)=3\\)",
            ],
            "C",
            "Unequal one-sided limits → DNE.",
            "<p><strong>C</strong> — cannot average 3 and 5. Jump means two-sided limit does not exist.</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: read piecewise graph",
        mcq_reveal(
            "<p>On the x=2 graph, \\(\\lim_{x\\to 2} f(x)=3\\) and \\(f(2)=1.5\\). Is f continuous at 2?</p>",
            ["Yes", "No", "Cannot tell", "Yes if we redefine f(2)=3"],
            "B",
            "Continuity requires limit = value.",
            "<p><strong>B</strong> — limit exists but ≠ f(2). Redefining would be “removing” discontinuity (topic 1.13).</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: filled dot trap",
        mcq_reveal(
            "<p>A student reads f(2)=−1 from a filled dot and concludes \\(\\lim_{x\\to 2} f(x)=-1\\). Error?</p>",
            ["No error", "Yes — limit comes from branches, not the dot", "Yes — limits never equal −1", "Cannot tell"],
            "B",
            "Filled dot gives f(c); limits come from approach.",
            "<p><strong>B</strong> — must trace left and right branches first.</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: infinite behavior",
        mcq_reveal(
            "<p>Near \\(x=0\\), the graph of \\(f(x)=\\dfrac{1}{x}\\) shows \\(|y|\\) growing without bound. "
            "What is \\(\\displaystyle\\lim_{x\\to 0} f(x)\\)?</p>",
            [
                "0",
                "1",
                "The limit does not exist (infinite behavior)",
                "The limit is ∞ only from the right",
            ],
            "C",
            "Infinite oscillation/growth means the two-sided limit DNE in the real-number sense.",
            "<p><strong>C</strong> — AP treats unbounded behavior as “limit DNE.” "
            "<strong>D</strong> describes one side only; the question asks about the two-sided limit.</p>",
        )
        + fig(g["infinite_limit_13"], "Reference: 1/x near 0", cls="ap-fig--standard", notice="Left and right diverge to −∞ and +∞."),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: endpoint one-sided limit",
        mcq_reveal(
            "<p>For \\(f(x)=\\sqrt{x}\\) on \\([0,4]\\), which statement is correct at \\(x=0\\)?</p>",
            [
                "\\(\\displaystyle\\lim_{x\\to 0^-} f(x)=0\\)",
                "\\(\\displaystyle\\lim_{x\\to 0^+} f(x)=0\\)",
                "\\(\\displaystyle\\lim_{x\\to 0} f(x)=0\\) with both sides in domain",
                "\\(f(0)\\) is undefined",
            ],
            "B",
            "Domain starts at 0; only right-hand approach exists.",
            "<p><strong>B</strong> — right-hand limit is 0. <strong>A</strong> is outside the domain. "
            "<strong>C</strong> incorrectly claims a two-sided approach. <strong>D</strong> — f(0)=0 is defined.</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: classify discontinuity",
        mcq_reveal(
            "<p>\\(\\displaystyle\\lim_{x\\to 2} f(x)=3\\) but \\(f(2)\\) is undefined (open circle only). "
            "What type of discontinuity?</p>",
            ["Jump", "Removable", "Infinite", "Continuous"],
            "B",
            "Limit exists but function value is missing — removable hole.",
            "<p><strong>B</strong> — a hole at x=2. <strong>A</strong> needs unequal one-sided limits. "
            "<strong>C</strong> involves unbounded behavior. <strong>D</strong> requires f(2)=limit.</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Error analysis: skipping a side",
        phase_divider("Contrast / Error Analysis", "Incomplete traces")
        + warning(
            "<p><strong>Mistake:</strong> checking only the left branch because it “looks closer.”</p>"
            "<p><strong>Fix:</strong> always record <em>both</em> \\(L^{-}\\) and \\(L^{+}\\) before deciding.</p>"
        ),
        path_phase="Contrast / Error Analysis",
    )

    s.add(
        "Exit ticket · 1.3",
        exit_ticket([
            (
                "State the four-step graph procedure in order.",
                "<p>Left trace → right trace → compare → inspect filled point.</p>",
            ),
            (
                "If \\(\\lim_{x\\to 3^-} f(x)=-1\\) and \\(\\lim_{x\\to 3^+} f(x)=2\\), does \\(\\lim_{x\\to 3} f(x)\\) exist?",
                "<p><strong>No</strong> — one-sided limits differ.</p>",
            ),
            (
                "On the x=2 piecewise graph, find \\(\\lim_{x\\to 2} f(x)\\) and \\(f(2)\\).",
                "<p>Limit = 3; f(2) = 1.5.</p>",
            ),
        ]),
        group="practice", path_phase="Exit Ticket",
    )

    s.add(
        "Practice packet · 1.3",
        practice_packet("1.3", "Unit 1.3 · Limits from graphs"),
        kind="lesson", group="practice",
    )

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
