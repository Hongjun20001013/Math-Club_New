"""AP Calculus Unit 1.5 lesson builder — algebraic limit properties & piecewise functions."""
from __future__ import annotations

from ap_calc_slide_helpers import (
    SlideBuilder,
    big_idea,
    bridge_slide,
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
    limit_cards_row,
    limit_compare_note,
    math_block,
    mcq_reveal,
    one_sided_limits_panel,
    phase_divider,
    practice_packet,
    role,
    solution_steps,
    warning,
    worked_example,
)


def build(graphs: dict[str, str]) -> dict:
    s = SlideBuilder("1.5")
    g = graphs

    s.add(
        "1.5 · Algebraic properties & piecewise",
        intro(
            "1",
            "1.5",
            "Algebraic properties of limits and piecewise functions",
            [
                (3, "Properties"),
                (6, "Piecewise"),
                (9, "One-sided"),
                (13, "Examples"),
                (17, "AP Practice"),
                (20, "Exit"),
            ],
            lede="Split complicated limits into sums and differences — then read piecewise graphs with \\(L^{-}\\) and \\(L^{+}\\)",
        ),
        kind="intro",
        group="divider",
    )

    s.add(
        "Bridge · from 1.4",
        bridge_slide(
            "1.5",
            "Evidence → algebra",
            "<p><strong>1.4</strong> used tables to estimate \\(L^{-}\\), \\(L^{+}\\), and two-sided limits.</p>",
            "<p><strong>1.5</strong> adds <em>limit laws</em> for sums, differences, and products — and piecewise formulas "
            "that tell you which branch to use on each side of a breakpoint.</p>",
            "Same one-sided language as 1.3–1.4; new tool: combine known limits.",
            "notation",
            protocol_mode="notation",
            demo_html=limit_cards_row([
                ("Split", "L_1 \\pm L_2", "\\text{laws}"),
                ("Piecewise", "L^{-}", "x\\to c^-"),
            ]),
        ),
        path_phase="Launch",
    )

    s.add(
        "Limit laws (when individual limits exist)",
        phase_divider("Launch", "Combine limits term by term")
        + role("Launch", "Why laws matter", "Break a messy expression into parts you already know.")
        + big_idea(
            "<p>If \\(\\displaystyle\\lim_{x\\to c} f(x)=L\\) and \\(\\displaystyle\\lim_{x\\to c} g(x)=M\\) "
            "(both finite), then you may <strong>distribute</strong> the limit across algebra:</p>"
            + data_table(
                ["Law", "Formula"],
                [
                    ["Sum", "\\(\\displaystyle\\lim_{x\\to c}[f(x)+g(x)]=L+M\\)"],
                    ["Difference", "\\(\\displaystyle\\lim_{x\\to c}[f(x)-g(x)]=L-M\\)"],
                    ["Constant multiple", "\\(\\displaystyle\\lim_{x\\to c}[k\\,f(x)]=kL\\)"],
                    ["Product / quotient", "\\(\\displaystyle\\lim_{x\\to c}[f(x)g(x)]=LM\\); quotient when \\(M\\neq 0\\)"],
                ],
            )
        )
        + concept_frame(
            "Rewrite the expression, then apply a limit to each simpler piece.",
            "AP free-response often nests \\(f\\), \\(g\\), and \\(h\\) in one limit.",
            "Each piece must have a limit at the same \\(c\\).",
            "Plugging in \\(f(c)\\) instead of \\(\\displaystyle\\lim_{x\\to c} f(x)\\).",
            "Label each sub-limit before you add or subtract.",
        ),
        path_phase="Launch",
    )

    s.add(
        "Worked example · combine given limits",
        worked_example(
            "Packet notes · table of limits",
            "Suppose \\(\\displaystyle\\lim_{x\\to 1} f(x)=2\\), \\(\\displaystyle\\lim_{x\\to 1} g(x)=4\\), and "
            "\\(\\displaystyle\\lim_{x\\to -1} f(x)=4\\). Find \\(\\displaystyle\\lim_{x\\to 1}\\bigl[f(-x)+\\tfrac{g(x)}{2}\\bigr]\\).",
            "Use laws on the outside; inside, \\(x\\to 1\\) still drives the approach.",
            solution_steps([
                "<strong>Inside \\(f(-x)\\):</strong> as \\(x\\to 1\\), \\(-x\\to -1\\), so "
                "\\(\\displaystyle\\lim_{x\\to 1} f(-x)=4\\).",
                "<strong>Inside \\(\\tfrac{g(x)}{2}\\):</strong> \\(\\displaystyle\\lim_{x\\to 1} g(x)=4\\) "
                "⇒ \\(\\displaystyle\\lim_{x\\to 1}\\tfrac{g(x)}{2}=2\\).",
                "<strong>Sum law:</strong> \\(4+2=\\mathbf{6}\\).",
            ]),
            "\\(\\displaystyle\\lim_{x\\to 1}\\bigl[f(-x)+\\tfrac{g(x)}{2}\\bigr]=6\\)",
            "Composition \\(f(-x)\\) changes the <em>input</em> trend — track what happens to \\(-x\\) as \\(x\\to c\\).",
            collapsible_model=True,
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Guided example · three functions at x = 5",
        guided_example(
            "<p><strong>Given at \\(x=5\\):</strong></p>"
            + data_table(
                ["", "\\(f\\)", "\\(g\\)", "\\(h\\)"],
                [
                    ["Value", "\\(f(5)=1\\)", "\\(g(5)=2\\)", "\\(h(5)=3\\)"],
                    ["Limit", "\\(\\displaystyle\\lim_{x\\to 5} f(x)=6\\)", "\\(-1\\)", "\\(5\\)"],
                ],
            )
            + "<p>Find \\(\\displaystyle\\lim_{x\\to 5}\\bigl[h(x)f(x)+2g(x)\\bigr]-h(5)\\).</p>",
            [
                "Product: \\(\\displaystyle\\lim h(x)f(x)=5\\cdot 6=30\\).",
                "Constant multiple + sum: \\(30+2(-1)=28\\).",
                "Subtract \\(h(5)=3\\): \\(28-3=\\mathbf{25}\\).",
            ],
            math_block("\\[\\displaystyle\\lim_{x\\to 5}\\bigl[h(x)f(x)+2g(x)\\bigr]-h(5)=25\\]")
            + warning(
                "<p><strong>Limit vs value:</strong> \\(f(5)=1\\) but \\(\\displaystyle\\lim_{x\\to 5} f(x)=6\\). "
                "Use limits inside the expression; use \\(h(5)\\) only where the problem asks for the value at \\(5\\).</p>"
            ),
        ),
        path_phase="Guided Example",
    )

    s.add(
        "What is a piecewise function?",
        phase_divider("Concept & Definition", "Different rules on different intervals")
        + definition(
            "Piecewise-defined function",
            "<p>A function is <strong>piecewise</strong> when its formula <strong>changes</strong> depending on where "
            "\\(x\\) lies on the number line.</p>"
            + math_block(
                "\\[f(x)=\\begin{cases}"
                "\\text{rule}_1 & \\text{if } x \\text{ in interval } I_1 \\\\"
                "\\text{rule}_2 & \\text{if } x \\text{ in interval } I_2"
                "\\end{cases}\\]"
            )
            + key_point(
                "Breakpoints",
                "<p>Numbers where the rule switches (e.g. \\(x=-4\\) or \\(x=2\\)) are where "
                "<strong>one-sided limits</strong> matter most. Each side may follow a different branch.</p>",
            ),
        )
        + concept_frame(
            "Read the correct branch for the side of approach.",
            "Piecewise graphs are the standard AP setup for jump vs continuous limits.",
            "Inequalities in the definition (\\(\\lt\\) vs \\(\\le\\)) tell you which branch at the endpoint.",
            "Using the wrong branch at a breakpoint.",
            "Ask: is \\(x\\) approaching \\(c\\) from the left or right? Then pick that branch.",
        ),
        path_phase="Concept & Definition",
    )

    s.add(
        "Left-hand and right-hand limits (review)",
        phase_divider("Why It Works", "One direction at a time")
        + definition(
            "One-sided limits at a breakpoint",
            limit_cards_row([
                ("Left-hand limit", "L^{-}", "x\\to c^-"),
                ("Right-hand limit", "L^{+}", "x\\to c^+"),
            ])
            + key_point(
                "Superscripts again",
                "<p><strong>Minus</strong> means \\(x\\) approaches \\(c\\) with \\(x&lt;c\\) (left). "
                "<strong>Plus</strong> means \\(x\\) approaches with \\(x&gt;c\\) (right). "
                "The sign is <em>not</em> part of the number \\(c\\).</p>",
            )
            + math_block(
                "\\[\\displaystyle\\lim_{x\\to c} f(x)=L"
                "\\ \\Longleftrightarrow\\ "
                "\\lim_{x\\to c^-} f(x)=\\lim_{x\\to c^+} f(x)=L\\]"
            ),
        )
        + role("Visual", "Jump at a breakpoint", "When \\(L^{-}\\neq L^{+}\\), the two-sided limit does not exist.")
        + one_sided_limits_panel("-5", "4", "0.1", two_sided_dne=True)
        + limit_compare_note("4", "0.1", "-5")
        + fig(
            g["piecewise_f_minus5_15"],
            "Example: \\(f(x)=\\sqrt{11-x}\\) for \\(x&lt;-5\\); rational rule for \\(x\\ge -5\\)",
            cls="ap-fig--teach",
            notice="Trace the blue branch toward −5 from the left; trace orange from the right.",
        ),
        path_phase="Why It Works",
    )

    s.add(
        "Graph protocol for piecewise",
        phase_divider("Representation Transfer", "Left → Right → Compare → Value")
        + big_idea(
            "<ol class='ap-procedure-list'>"
            "<li><strong>Left:</strong> follow the branch with \\(x&lt;c\\) toward \\(c\\) → \\(L^{-}\\)</li>"
            "<li><strong>Right:</strong> follow the branch with \\(x&gt;c\\) toward \\(c\\) → \\(L^{+}\\)</li>"
            "<li><strong>Compare:</strong> equal one-sided limits ⇒ two-sided limit exists</li>"
            "<li><strong>Value:</strong> read \\(f(c)\\) from the branch that <em>includes</em> \\(c\\) (filled dot)</li>"
            "</ol>"
        )
        + fig(
            g["piecewise_limit_2"],
            "Review from 1.3 — limit can differ from \\(f(c)\\)",
            cls="ap-fig--standard",
            notice="Branches agree at height 3; filled dot shows \\(f(2)=1.5\\).",
        )
        + checkpoint(
            "For piecewise limits, <strong>branch choice</strong> replaces guessing from a single formula."
        ),
        path_phase="Representation Transfer",
    )

    s.add(
        "Worked example · practice #7 style",
        worked_example(
            "Limits of a three-branch function",
            "Let "
            "\\(g(x)=\\begin{cases}\\sqrt{5-x}, & x&lt;-4\\\\ x^2-5, & -4\\le x&lt;2\\\\ x-3, & x\\ge 2\\end{cases}\\). "
            "Find \\(\\displaystyle\\lim_{x\\to 2^-} g(x)\\), \\(\\displaystyle\\lim_{x\\to 2^+} g(x)\\), and "
            "\\(\\displaystyle\\lim_{x\\to 2} g(x)\\).",
            "At \\(x=2\\) the middle branch ends and the linear branch begins.",
            solution_steps([
                "<strong>\\(x\\to 2^{-}\\):</strong> use \\(x^2-5\\) → \\(4-5=\\mathbf{-1}\\).",
                "<strong>\\(x\\to 2^{+}\\):</strong> use \\(x-3\\) → \\(2-3=\\mathbf{-1}\\).",
                "<strong>Two-sided:</strong> \\(L^{-}=L^{+}=-1\\) ⇒ \\(\\displaystyle\\lim_{x\\to 2} g(x)=\\mathbf{-1}\\).",
                "<strong>Value:</strong> \\(x\\ge 2\\) gives \\(g(2)=2-3=\\mathbf{-1}\\) (continuous at 2).",
            ])
            + one_sided_limits_panel("2", "-1", "-1", two_sided="-1")
            + limit_card("x\\to 2", equals="-1"),
            "\\(\\displaystyle\\lim_{x\\to 2^-} g(x)=\\lim_{x\\to 2^+} g(x)=\\lim_{x\\to 2} g(x)=-1\\); \\(g(2)=-1\\).",
            "Also try \\(x=-4\\): \\(L^{-}=3\\), \\(L^{+}=11\\) → two-sided limit DNE at −4.",
            stem_math=fig(
                g["piecewise_g_15"],
                "Graph of \\(g\\)",
                cls="ap-fig--practice",
            ),
            collapsible_model=True,
        ),
        template="investigation",
        path_phase="Worked Example",
    )

    s.add(
        "Checkpoint · x = −4 on the same g",
        guided_example(
            "<p>For the same \\(g(x)\\) as the previous slide, analyze <strong>\\(x=-4\\)</strong>.</p>",
            [
                "<strong>Left:</strong> \\(\\sqrt{5-x}\\) → \\(\\sqrt{9}=3\\).",
                "<strong>Right:</strong> \\(x^2-5\\) → \\(16-5=11\\).",
                "<strong>Two-sided:</strong> \\(3\\neq 11\\) ⇒ limit DNE.",
                "<strong>Value:</strong> \\(-4\\le x&lt;2\\) ⇒ \\(g(-4)=11\\).",
            ],
            limit_compare_note("3", "11", "-4")
            + math_block("\\[\\displaystyle\\lim_{x\\to -4} g(x)\\ \\text{DNE};\\qquad g(-4)=11\\]"),
        ),
        path_phase="Worked Example",
    )

    s.add(
        "Practice · pick the branch",
        mcq_reveal(
            "<p>Let \\(h(x)=\\begin{cases}-|x|, & x\\le -5\\\\ 20-x^2, & -5&lt;x\\le 3\\\\ 4x-1, & x&gt;3\\end{cases}\\). "
            "What is \\(\\displaystyle\\lim_{x\\to -5^+} h(x)\\)?</p>",
            ["\\(-5\\)", "\\(0\\)", "\\(-3\\)", "DNE"],
            "A",
            "Right of −5 uses the quadratic branch.",
            "<p><strong>A</strong> — for \\(x\\to -5^{+}\\), use \\(20-x^2\\): "
            "\\(20-25=\\mathbf{-5}\\). (Packet practice #8)</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Practice · continuous function",
        mcq_reveal(
            "<p>If \\(f\\) is continuous and \\(f(3)=7\\), which statement <strong>must</strong> be true?</p>",
            [
                "\\(\\displaystyle\\lim_{x\\to 3} f(3x)=9\\)",
                "\\(\\displaystyle\\lim_{x\\to 3} f(2x)=14\\)",
                "\\(\\displaystyle\\lim_{x\\to 3}\\dfrac{f(x)-f(3)}{x-3}=7\\)",
                "\\(\\displaystyle\\lim_{x\\to 3} f(x^2)=49\\)",
                "\\(\\displaystyle\\lim_{x\\to 3}[f(x)]^2=49\\)",
            ],
            "E",
            "Continuity: limit equals f(3).",
            "<p><strong>E</strong> — \\(\\displaystyle\\lim_{x\\to 3} f(x)=f(3)=7\\), so the square of the limit is "
            "\\(49\\). (Test Prep #11)</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Practice · piecewise logarithm at x = 3",
        mcq_reveal(
            "<p>Let \\(f(x)=\\begin{cases}\\ln(3x), & 0&lt;x\\le 3\\\\ x\\ln 3, & 3&lt;x\\le 4\\end{cases}\\). "
            "Find \\(\\displaystyle\\lim_{x\\to 3} f(x)\\).</p>",
            [
                "\\(\\ln 9\\)",
                "\\(\\ln 27\\)",
                "\\(3\\ln 3\\)",
                "\\(3+\\ln 3\\)",
                "The limit does not exist",
            ],
            "E",
            "Compare one-sided limits on each branch.",
            "<p><strong>E</strong> — \\(x\\to 3^{-}\\Rightarrow \\ln(3x)\\to \\ln 9=2\\ln 3\\); "
            "\\(x\\to 3^{+}\\Rightarrow x\\ln 3\\to 3\\ln 3\\). Unequal ⇒ DNE. (Test Prep #12)</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Practice · piecewise at x = 2",
        mcq_reveal(
            "<p>Let \\(f(x)=\\begin{cases}\\ln x, & 0&lt;x\\le 2\\\\ x^2\\ln 2, & 2&lt;x\\le 4\\end{cases}\\). "
            "Find \\(\\displaystyle\\lim_{x\\to 2} f(x)\\).</p>",
            [
                "\\(\\ln 2\\)",
                "\\(\\ln 8\\)",
                "\\(\\ln 16\\)",
                "\\(4\\)",
                "The limit does not exist",
            ],
            "E",
            "Left → ln 2; right → 4 ln 2.",
            "<p><strong>E</strong> — \\(2\\ln 2\\neq 4\\ln 2\\). (Test Prep #13)</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Common mistakes",
        phase_divider("Contrast / Error Analysis", "Piecewise traps")
        + warning(
            "<p><strong>Wrong branch:</strong> using the \\(x\\ge c\\) rule when \\(x\\to c^{-}\\).</p>"
            "<p><strong>Endpoint confusion:</strong> \\(\\le\\) vs \\(\\lt\\) decides which formula defines \\(f(c)\\), "
            "not which side you approach from.</p>"
            "<p><strong>Limit laws:</strong> do not split unless each piece has a limit at the same \\(c\\).</p>"
        ),
        path_phase="Contrast / Error Analysis",
    )

    s.add(
        "Exit ticket · 1.5",
        exit_ticket([
            (
                "State the sum law for limits in words.",
                "<p>The limit of a sum equals the sum of the limits (when both limits exist).</p>",
            ),
            (
                "<p>For a piecewise function, how do you find \\(L^{-}\\) at \\(x=c\\)?</p>",
                "<p>Use the branch that applies for \\(x&lt;c\\) and evaluate the trend as \\(x\\to c^{-}\\) "
                "(substitute values or read the graph from the left).</p>",
            ),
            (
                "<p>\\(g(x)=\\begin{cases}x+1, & x&lt;0\\\\ 5-x, & x\\ge 0\\end{cases}\\). "
                "Does \\(\\displaystyle\\lim_{x\\to 0} g(x)\\) exist?</p>",
                "<p>Left: \\(x+1\\to 1\\). Right: \\(5-x\\to 5\\). "
                "\\(1\\neq 5\\) ⇒ \\(\\displaystyle\\lim_{x\\to 0} g(x)\\) DNE.</p>",
            ),
        ]),
        group="practice",
        path_phase="Exit Ticket",
    )

    s.add(
        "Practice packet · 1.5",
        practice_packet("1.5", "Unit 1.5 · Algebraic properties & piecewise"),
        kind="lesson",
        group="practice",
    )

    return {
        "slug": "ap-1-5-algebraic-limits-piecewise",
        "unit": 1,
        "unit_name": "Limits and Continuity",
        "section": "1.5",
        "title": "Algebraic Properties of Limits and Piecewise Functions",
        "deck_title": "AP Unit 1.5 · Limit laws & piecewise",
        "slide_count": len(s.slides),
        "slides": s.slides,
        "practice_section": "1.5",
    }
