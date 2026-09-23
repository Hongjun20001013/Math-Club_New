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
    limit_cards_row,
    limit_compare_note,
    limit_tracer_embed,
    limit_card,
    math_block,
    one_sided_limits_panel,
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
            (2, "Procedure"), (3, "One-sided"), (6, "Cases"), (12, "Practice"), (19, "Exit"),
        ]),
        kind="intro", group="divider",
    )

    s.add(
        "The four-step graph procedure",
        phase_divider("Launch", "Left → Right → Compare → Value")
        + role("Launch", "A stable routine", "Use the same steps on every graph problem.")
        + big_idea(
            "<ol class='ap-procedure-list'>"
            "<li><strong>Trace from the left</strong> — approach \\(x=c\\) with \\(x \\lt c\\)</li>"
            "<li><strong>Trace from the right</strong> — approach \\(x=c\\) with \\(x \\gt c\\)</li>"
            "<li><strong>Compare</strong> — if both branch heights match, the two-sided limit exists</li>"
            "<li><strong>Inspect the filled point</strong> — read \\(f(c)\\) only after you know the limit</li>"
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
            "<p>Each one-sided limit describes <strong>one direction</strong> of approach to \\(x=c\\).</p>"
            + limit_cards_row([
                ("Left-hand limit", "L", "x\\to c^-"),
                ("Right-hand limit", "M", "x\\to c^+"),
            ])
            + key_point(
                "Read the superscript",
                "<p><strong>Minus (−)</strong> means \\(x\\) approaches \\(c\\) from the left (\\(x \\lt c\\)). "
                "<strong>Plus (+)</strong> means \\(x\\) approaches from the right (\\(x \\gt c\\)). "
                "The superscript is <em>not</em> part of the number \\(c\\).</p>",
            ),
        )
        + role("Example", "Jump at x = 3", "Different branch heights on each side.")
        + one_sided_limits_panel("3", "-1", "4", two_sided_dne=True)
        + limit_compare_note("-1", "4", "3")
        + fig(g["jump_at_3"], "Jump at \\(x=3\\)", cls="ap-fig--teach", notice=NOTICE_JUMP_DNE),
        path_phase="Concept & Definition",
    )

    s.add(
        "Two-sided limit exists when sides agree",
        phase_divider("Why It Works", "Combining one-sided limits")
        + definition(
            "Two-sided limit",
            "<p>The two-sided limit exists only when <strong>both</strong> one-sided limits exist "
            "and are <strong>equal</strong>.</p>"
            + limit_card("x\\to c^-", equals="L")
            + limit_card("x\\to c^+", equals="L")
            + math_block(
                "\\[\\displaystyle\\Longrightarrow\\qquad "
                "\\lim_{x\\to c} f(x)=L\\]"
            )
            + "<p class=\"ap-prose-after-math\">If \\(L^{-}\\neq L^{+}\\), the two-sided limit "
            "<strong>does not exist</strong> — even if \\(f(c)\\) is defined.</p>",
        )
        + visual_limit_vs_value("2", "3", fc_val="1.5")
        + key_point(
            "Limit vs value",
            "<p>Branches approach height <strong>3</strong> at \\(x=2\\), but the filled dot is at "
            "<strong>1.5</strong>. The limit exists; the function is not continuous there.</p>",
        ),
        path_phase="Why It Works",
    )

    s.add(
        "Worked example: piecewise at x = 2",
        worked_example(
            "Read limits at x = 2",
            "Use the four-step procedure on the piecewise graph at \\(x=2\\).",
            "Left branch: \\(y=x+1\\). Right branch: \\(y=-x+5\\). Open circle at \\((2,3)\\); filled dot at \\((2,1.5)\\).",
            solution_steps([
                "Left trace: as \\(x\\to 2^{-}\\), outputs on \\(y=x+1\\) approach <strong>3</strong>.",
                "Right trace: as \\(x\\to 2^{+}\\), outputs on \\(y=-x+5\\) approach <strong>3</strong>.",
                "Compare: \\(L^{-}=L^{+}=3\\), so the two-sided limit is <strong>3</strong>.",
                "Filled dot at \\((2,1.5)\\) gives \\(f(2)=1.5\\neq 3\\) \\(\\Rightarrow\\) not continuous at 2.",
            ])
            + one_sided_limits_panel("2", "3", "3", two_sided="3")
            + limit_card("x\\to 2", equals="3")
            + math_block("\\[\\displaystyle f(2)=1.5\\]"),
            "Two-sided limit is 3; function value is 1.5 — limit exists but graph is not continuous.",
            "Open circle shows approach height 3; filled dot shows \\(f(2)=1.5\\).",
            collapsible_model=True,
        )
        + limit_tracer_embed(worked_example=True),
        template="investigation",
        path_phase="Worked Example",
    )

    s.add(
        "Case gallery: continuity types",
        phase_divider("Visual Investigation", "Compare discontinuity types")
        + role("Visual", "Four graph stories", "Same limit language — different pictures.")
        + '<p class="ap-prose-after-math"><em>Discontinuity preview</em> — formal classification in Section 1.10. '
        "Pick a case tab, predict from the graph beside your answers, then trace each scenario.</p>"
        + limit_tracer_embed(),
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
            "<p>Only values with \\(x\\ge 0\\) are in the domain, so we trace from the right. "
            "There is <strong>no</strong> left-hand approach on this graph.</p>",
        ),
        path_phase="Representation Transfer",
    )

    s.add(
        "Worked example: jump discontinuity",
        worked_example(
            "Jump at x = 3",
            "The left and right branches approach <strong>different</strong> heights at \\(x=3\\).",
            "Blue branch from the left; orange branch from the right.",
            solution_steps([
                "Left trace: branch height approaches <strong>−1</strong>.",
                "Right trace: branch height approaches <strong>4</strong>.",
                "Compare: \\(-1\\neq 4\\).",
                "Conclusion: the two-sided limit does not exist (jump discontinuity).",
            ])
            + one_sided_limits_panel("3", "-1", "4", two_sided_dne=True)
            + limit_compare_note("-1", "4", "3"),
            "Two-sided limit DNE because one-sided limits disagree.",
            "A filled dot at \\(f(3)\\) would not repair the jump — limits come from branches.",
        ),
        path_phase="Worked Example",
    )

    s.add(
        "Guided: trace from the left",
        guided_example(
            '<p class="ap-prose-after-math">Use the piecewise graph below. Find the <strong>left-hand</strong> limit at \\(x=2\\).</p>'
            + limit_card("x\\to 2^-", equals="?")
            + fig(g["piecewise_limit_2"], "Reference graph", cls="ap-fig--practice", notice="Follow the left branch only."),
            [
                "Start at \\(x \\lt 2\\) on the left branch (\\(y=x+1\\)).",
                "Move toward \\(x=2\\) along that branch — ignore the right side.",
                "Record the \\(y\\)-value the branch approaches.",
            ],
            limit_card("x\\to 2^-", equals="3")
            + "<p class=\"ap-prose-after-math\">The left branch \\(y=x+1\\) approaches height <strong>3</strong>.</p>",
        ),
        group="practice", path_phase="Guided Example",
    )

    s.add(
        "Guided: compare sides",
        guided_example(
            '<p class="ap-prose-after-math">For the jump graph at \\(x=3\\), find each one-sided limit, then decide whether the two-sided limit exists.</p>'
            + one_sided_limits_panel("3", "?", "?", two_sided=None)
            + fig(g["jump_at_3"], "Jump graph", cls="ap-fig--practice"),
            [
                "Trace the blue left branch toward \\(x=3\\).",
                "Trace the orange right branch toward \\(x=3\\).",
                "Are the approach heights equal?",
            ],
            one_sided_limits_panel("3", "-1", "4", two_sided_dne=True)
            + limit_compare_note("-1", "4", "3"),
        ),
        group="practice", path_phase="Guided Example",
    )

    s.add(
        "Guided: sketch with constraints",
        guided_example(
            "<p>Sketch a graph that satisfies <strong>all three</strong> conditions below.</p>"
            + one_sided_limits_panel("2", "3", "3", two_sided="3")
            + math_block("\\[\\displaystyle f(2)=-1\\]")
            + "<p class=\"ap-prose-after-math\">Branches must approach the open-circle height <strong>3</strong>, "
            "but the filled dot at \\(x=2\\) must be at <strong>−1</strong>.</p>",
            [
                "Draw an open circle at \\((2,3)\\) — this is the approach height.",
                "Draw left and right branches that meet that open circle.",
                "Place a filled dot at \\((2,-1)\\) for the function value.",
            ],
            fig(
                g["sketch_task_13"],
                "One valid sketch",
                cls="ap-fig--practice",
                notice="Limit = 3 at \\(x=2\\); \\(f(2)=-1\\).",
            )
            + "<p class=\"ap-prose-after-math\">Your sketch may differ in shape — check open vs filled points and branch heights.</p>",
        ),
        group="practice", path_phase="Guided Example",
    )

    s.add(
        "Practice: jump discontinuity",
        mcq_reveal(
            "<p>At \\(x=b\\), the left-hand limit is <strong>3</strong> and the right-hand limit is <strong>5</strong>. "
            "Which statement about the two-sided limit is correct?</p>"
            + limit_cards_row([
                ("From the left", "3", "x\\to b^-"),
                ("From the right", "5", "x\\to b^+"),
            ]),
            [
                limit_card("x\\to b", equals="4"),
                limit_card("x\\to b", equals="5"),
                math_block("\\[\\displaystyle\\lim_{x\\to b} f(x)\\ \\text{DNE}\\]"),
                limit_card("x\\to b", equals="3"),
            ],
            "C",
            "Unequal one-sided limits → two-sided limit DNE.",
            "<p><strong>C</strong> — you cannot average 3 and 5. A jump means the two-sided limit does not exist.</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: read piecewise graph",
        mcq_reveal(
            "<p>On the \\(x=2\\) graph:</p>"
            + limit_card("x\\to 2", equals="3")
            + math_block("\\[\\displaystyle f(2)=1.5\\]")
            + "<p>Is \\(f\\) continuous at \\(x=2\\)?</p>",
            ["Yes", "No", "Cannot tell", "Yes if we redefine \\(f(2)=3\\)"],
            "B",
            "Continuity requires limit = function value.",
            "<p><strong>B</strong> — the limit exists but does not equal \\(f(2)\\). Redefining would remove the discontinuity (topic 1.13).</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: filled dot trap",
        mcq_reveal(
            "<p>A student reads \\(f(2)=-1\\) from a filled dot and concludes the limit at \\(x=2\\) is \\(-1\\). "
            "What is wrong with that reasoning?</p>",
            [
                "Nothing — the filled dot determines the limit",
                "Limits come from branch approach, not the filled dot alone",
                "Limits can never equal \\(-1\\)",
                "Cannot tell without tracing both branches",
            ],
            "B",
            "Filled dot gives \\(f(c)\\); limits come from approach along branches.",
            "<p><strong>B</strong> — always trace left and right branches first. The filled dot gives \\(f(2)\\), not the limit.</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: infinite behavior",
        mcq_reveal(
            "<p>Near \\(x=0\\), the graph of \\(f(x)=\\dfrac{1}{x}\\) shows \\(|y|\\) growing without bound. "
            "Which statement about one-sided and two-sided limits is correct?</p>"
            + limit_card("x\\to 0", equals="?"),
            [
                "Both one-sided limits are 0",
                "\\(L^{-}=-\\infty\\), \\(L^{+}=+\\infty\\), so the two-sided limit DNE",
                "The two-sided limit is \\(+\\infty\\)",
                "The two-sided limit is \\(-\\infty\\)",
            ],
            "B",
            "Trace each branch: left goes to \\(-\\infty\\), right goes to \\(+\\infty\\).",
            "<p><strong>B</strong> — as \\(x\\to 0^{-}\\), \\(y\\to -\\infty\\); as \\(x\\to 0^{+}\\), \\(y\\to +\\infty\\). "
            "Unequal infinite behavior means the two-sided limit does not exist in \\(\\mathbb{R}\\). "
            "<strong>C</strong> and <strong>D</strong> describe only one side.</p>",
        )
        + fig(g["infinite_limit_13"], "Reference: \\(1/x\\) near 0", cls="ap-fig--standard", notice="Left branch → \\(-\\infty\\); right branch → \\(+\\infty\\)."),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: endpoint one-sided limit",
        mcq_reveal(
            "<p>For \\(f(x)=\\sqrt{x}\\) on \\([0,4]\\), which statement is correct at \\(x=0\\)?</p>",
            [
                limit_card("x\\to 0^-", equals="0"),
                limit_card("x\\to 0^+", equals="0"),
                limit_card("x\\to 0", equals="0"),
                math_block("\\[\\displaystyle f(0)\\ \\text{is undefined}\\]"),
            ],
            "B",
            "Domain starts at 0; only the right-hand approach exists.",
            "<p><strong>B</strong> — right-hand limit is 0. <strong>A</strong> is outside the domain. "
            "<strong>C</strong> incorrectly claims a two-sided approach. <strong>D</strong> — \\(f(0)=0\\) is defined.</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: classify discontinuity",
        mcq_reveal(
            "<p>A graph shows the following at \\(x=2\\):</p>"
            + limit_card("x\\to 2", equals="3")
            + math_block("\\[\\displaystyle f(2)\\ \\text{is undefined (open circle only)}\\]")
            + "<p>What type of discontinuity is this?</p>",
            ["Jump", "Removable", "Infinite", "Continuous"],
            "B",
            "Limit exists but function value is missing — removable hole.",
            "<p><strong>B</strong> — a hole at \\(x=2\\). <strong>A</strong> needs unequal one-sided limits. "
            "<strong>C</strong> involves unbounded behavior. <strong>D</strong> requires \\(f(2)=\\) limit.</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Error analysis: skipping a side",
        phase_divider("Contrast / Error Analysis", "Incomplete traces")
        + warning(
            "<p><strong>Mistake:</strong> checking only the left branch because it “looks closer.”</p>"
            "<p><strong>Fix:</strong> always record <em>both</em> \\(L^{-}\\) and \\(L^{+}\\) in display form before deciding.</p>"
        ),
        path_phase="Contrast / Error Analysis",
    )

    s.add(
        "Exit ticket · 1.3",
        exit_ticket([
            (
                "State the four-step graph procedure in order.",
                "<p><strong>Left trace</strong> → <strong>right trace</strong> → "
                "<strong>compare</strong> → <strong>inspect filled point</strong>.</p>",
            ),
            (
                '<div class="ap-exit-limit-prompt">'
                "<p>Given the one-sided limits below, does the two-sided limit at \\(x=3\\) exist?</p>"
                + one_sided_limits_panel("3", "-1", "2", two_sided=None)
                + "</div>",
                one_sided_limits_panel("3", "-1", "2", two_sided_dne=True)
                + limit_compare_note("-1", "2", "3"),
            ),
            (
                '<div class="ap-exit-limit-prompt">'
                "<p>On the \\(x=2\\) piecewise graph, find the two-sided limit and \\(f(2)\\).</p>"
                + limit_card("x\\to 2", equals="?")
                + math_block("\\[\\displaystyle f(2)=\\ ?\\]")
                + "</div>",
                limit_card("x\\to 2", equals="3")
                + math_block("\\[\\displaystyle f(2)=1.5\\]")
                + "<p class=\"ap-prose-after-math\">Limit comes from branches; \\(f(2)\\) comes from the filled dot.</p>",
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
