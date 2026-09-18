"""AP Calculus Unit 1.2 lesson builder."""
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
    limit_approach_embed,
    key_point,
    limit_card,
    math_block,
    NOTICE_LIMIT_EQ_FC,
    NOTICE_JUMP_DNE,
    NOTICE_HOLE,
    NOTICE_INFINITE,
    visual_cases_gallery_12,
    visual_limit_vs_value,
    mcq_reveal,
    optional_note,
    phase_divider,
    practice_packet,
    role,
    solution_steps,
    warning,
    worked_example,
)


def build(graphs: dict[str, str]) -> dict:
    s = SlideBuilder("1.2")
    g = graphs

    s.add(
        "1.2 · Defining limits and notation",
        intro("1", "1.2", "Defining limits and limit notation", [
            (2, "Launch"), (5, "Definition"), (10, "Four cases"), (14, "Practice"), (18, "Exit"),
        ]),
        kind="intro", group="divider",
    )

    s.add(
        "Limits describe approach, not always value",
        phase_divider("Launch", "Near vs at a point")
        + role("Launch", "The language of approach", "We care what happens as x gets close to c.")
        + big_idea(
            "<p>\\(\\displaystyle\\lim_{x\\to c} f(x)=L\\) describes behavior <strong>near</strong> \\(x=c\\), "
            "not necessarily <strong>at</strong> \\(x=c\\).</p>"
        )
        + concept_frame(
            "As x approaches c, outputs f(x) approach L.",
            "Limits let us define instantaneous rate and continuity.",
            "Phrase “as x approaches c” or the notation \\(x \\to c\\).",
            "Assuming f(c) must equal L.",
            "Compare table values near c from both sides.",
        ),
        path_phase="Launch",
    )

    s.add(
        "Reading limit notation",
        phase_divider("Concept & Definition", "Symbol by symbol")
        + definition(
            "Informal limit",
            limit_card("x\\to c", equals="L")
            + limit_card("x\\to 3", equals="5")
            + data_table(
                ["Symbol", "Meaning"],
                [
                    ["x", "input variable"],
                    ["c", "the value x approaches"],
                    ["\\(x \\to c\\)", "x gets arbitrarily close to c (not necessarily equal)"],
                    ["f(x)", "output values of the function"],
                    ["L", "the value f(x) approaches"],
                ],
            ),
        )
        + key_point(
            "Say it aloud",
            "<p><em>“The limit of f(x) as x approaches c is L.”</em></p>",
        ),
        path_phase="Concept & Definition",
    )

    s.add(
        "Four contrast cases",
        phase_divider("Visual Investigation", "Limit vs function value")
        + role("Visual", "Four possibilities", "Same limit language — different graphs.")
        + '<div class="ap-graph-grid ap-graph-grid--cases">'
        + fig(g["limit_case_a_thumb"], "A · Continuous", cls="ap-fig--case", notice=NOTICE_LIMIT_EQ_FC)
        + fig(
            g["limit_case_b_thumb"], "B · Limit ≠ value", cls="ap-fig--case",
            notice="\\(\\displaystyle\\lim_{x\\to 3} f(x)=5\\), \\(f(3)=10\\).",
        )
        + fig(g["limit_case_c_thumb"], "C · Undefined at c", cls="ap-fig--case", notice=NOTICE_HOLE)
        + fig(g["limit_case_d_thumb"], "D · Limit DNE", cls="ap-fig--case", notice=NOTICE_JUMP_DNE)
        + "</div>"
        + visual_cases_gallery_12()
        + limit_approach_embed(),
        path_phase="Visual Investigation",
    )

    s.add(
        "Representation transfer: graph, table, words",
        phase_divider("Representation Transfer", "One idea — four forms")
        + role("Transfer", "Connect representations", "AP questions mix all four.")
        + data_table(
            ["Form", "Statement for \\(\\lim_{x\\to 3} f(x)=5\\)"],
            [
                ["Symbolic", "\\(\\displaystyle\\lim_{x\\to 3} f(x)=5\\)"],
                ["Verbal", "As x approaches 3, f(x) approaches 5."],
                ["Table", "\\(x\\): 2.9, 2.99, 3.01 \\(\\Rightarrow f(x)\\to 5\\)"],
                ["Graph", "Branches near x=3 approach height y=5"],
            ],
        )
        + checkpoint("None of these automatically imply \\(f(3)=5\\)."),
        path_phase="Representation Transfer",
    )

    s.add(
        "Worked example: limit vs f(c)",
        worked_example(
            "Piecewise at x = 3",
            "Find \\(\\lim_{x\\to 3} f(x)\\) and compare to \\(f(3)\\) for the piecewise function.",
            "Algebraic rule for x ≠ 3; separate rule at x = 3.",
            solution_steps([
                "For x ≠ 3, f(x) = x + 2, so near 3 the outputs behave like x + 2.",
                "Compute: \\(\\lim_{x\\to 3}(x+2)=5\\).",
                "By definition, \\(f(3)=10\\).",
                "Conclusion: limit exists and equals 5, but \\(f(3)\\neq 5\\).",
            ]),
            "\\(\\displaystyle\\lim_{x\\to 3} f(x)=5\\) while \\(f(3)=10\\).",
            "Graph would show open circle at (3,5) and filled dot at (3,10).",
        )
        + visual_limit_vs_value("3", "5", fc_val="10"),
        path_phase="Worked Example",
    )

    s.add(
        "Contrast: common mis-readings",
        phase_divider("Contrast / Error Analysis", "What the limit does NOT say")
        + warning(
            "<p><strong>Wrong:</strong> “\\(f(3)=5\\) because the limit is 5.”</p>"
            "<p><strong>Why:</strong> Limits describe approach; \\(f(3)\\) is read from the definition or filled dot.</p>"
        )
        + warning(
            "<p><strong>Wrong:</strong> “As x approaches 5, f(x) approaches 3” for \\(\\lim_{x\\to 3} f(x)=5\\).</p>"
            "<p><strong>Why:</strong> The input approaches <em>c</em> and outputs approach <em>L</em> — do not swap numbers.</p>"
        ),
        path_phase="Contrast / Error Analysis",
    )

    s.add(
        "Guided: write the verbal statement",
        guided_example(
            "<p>Write a correct verbal interpretation of \\(\\displaystyle\\lim_{x\\to -1} f(x)=2\\).</p>",
            [
                "Which number does x approach?",
                "Which number do outputs approach?",
                "Does this say anything about f(−1)?",
            ],
            "<p><strong>Solution:</strong> As x approaches −1, the values of f(x) approach 2. "
            "(We cannot conclude f(−1)=2.)</p>",
        ),
        group="practice", path_phase="Guided Example",
    )

    s.add(
        "Practice: table to limit statement",
        mcq_reveal(
            "<p>A table shows \\(f(x)\\) near \\(x=2\\): 1.9→4.8, 1.99→4.98, 2.01→5.02, 2.1→5.2. "
            "Which limit statement is best supported?</p>",
            [
                "\\(\\displaystyle\\lim_{x\\to 2} f(x)=5\\)",
                "\\(\\displaystyle\\lim_{x\\to 5} f(x)=2\\)",
                "\\(f(2)=5\\) is guaranteed",
                "\\(\\displaystyle\\lim_{x\\to 2} f(x)\\) does not exist",
            ],
            "A",
            "Table values near x=2 approach 5 from both sides.",
            "<p><strong>A</strong> matches the table trend. <strong>B</strong> swaps 2 and 5. "
            "<strong>C</strong> confuses limit with value. <strong>D</strong> contradicts agreeing sides.</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: words to symbols",
        mcq_reveal(
            "<p>Which expression matches: “As \\(x\\) approaches \\(-2\\), \\(f(x)\\) approaches \\(7\\)”?</p>",
            [
                "\\(\\displaystyle\\lim_{x\\to -2} f(x)=7\\)",
                "\\(\\displaystyle\\lim_{x\\to 7} f(x)=-2\\)",
                "\\(f(-2)=7\\)",
                "\\(\\displaystyle\\lim_{x\\to -2} f(x)=-2\\)",
            ],
            "A",
            "Input approaches c; outputs approach L.",
            "<p><strong>A</strong> is correct notation. <strong>B</strong> swaps input and output targets. "
            "<strong>C</strong> is a function value, not a limit. <strong>D</strong> uses the wrong limit value.</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: best interpretation",
        mcq_reveal(
            "<p>Best interpretation of \\(\\displaystyle\\lim_{x\\to 4} f(x)=8\\)?</p>",
            [
                "\\(f(4)=8\\)",
                "\\(f(8)=4\\)",
                "As \\(x\\to 4\\), \\(f(x)\\to 8\\)",
                "As \\(x\\to 8\\), \\(f(x)\\to 4\\)",
            ],
            "C",
            "Match input approach with output approach.",
            "<p><strong>A</strong> confuses limit with value. <strong>B,D</strong> swap 4 and 8. <strong>C</strong> is correct.</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: limit vs value from graph",
        mcq_reveal(
            "<p>\\(\\displaystyle\\lim_{x\\to 2} f(x)=3\\) but \\(f(2)=1.5\\). Which is true?</p>",
            ["The limit does not exist", "f is continuous at x=2", "The limit exists but ≠ f(2)", "Cannot tell from the information"],
            "C",
            "Both statements can be true simultaneously.",
            "<p>Limit 3 and value 1.5 can coexist (Case B). <strong>C</strong> is correct.</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Practice: identify the error",
        mcq_reveal(
            "<p>A student says: “Because \\(\\lim_{x\\to 1} f(x)=4\\), we know \\(f(1)=4\\) in all cases.” True?</p>",
            ["True — always", "False — removable holes exist", "True only if f is linear", "False — limits never equal values"],
            "B",
            "Counterexample: piecewise with f(1) defined differently.",
            "<p><strong>B</strong> is correct. Case B shows limit 5 with f(3)=10. Limits do not force f(c)=L.</p>",
        ),
        kind="question", group="practice", path_phase="AP Practice",
    )

    s.add(
        "Optional: ε–δ definition",
        optional_note(
            math_block(
                "\\[\\forall\\varepsilon>0,\\ \\exists\\delta>0:\\ 0<|x-c|<\\delta\\Rightarrow|f(x)-L|<\\varepsilon\\]"
            )
            + "<p>Precision for “arbitrarily close.” Not required for AP computation at this stage.</p>"
        ),
        path_phase="Optional",
    )

    s.add(
        "Exit ticket · 1.2",
        exit_ticket([
            (
                "Write \\(\\displaystyle\\lim_{x\\to 5} f(x)=-2\\) in words.",
                "<p>As x approaches 5, f(x) approaches −2.</p>",
            ),
            (
                "True or false: \\(f(1)=\\lim_{x\\to 1} f(x)\\) in all cases.",
                "<p><strong>False.</strong> Counterexample: removable hole or jump.</p>",
            ),
            (
                "Name two things that can differ when \\(\\lim_{x\\to c} f(x)=L\\).",
                "<p>\\(f(c)\\) may be undefined or may equal a value different from L.</p>",
            ),
        ]),
        group="practice", path_phase="Exit Ticket",
    )

    s.add(
        "Practice packet · 1.2",
        practice_packet("1.2", "Unit 1.2 · Defining limits"),
        kind="lesson", group="practice",
    )

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
