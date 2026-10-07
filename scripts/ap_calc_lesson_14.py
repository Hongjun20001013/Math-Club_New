"""AP Calculus Unit 1.4 lesson builder — limits from tables."""
from __future__ import annotations

from ap_calc_slide_helpers import (
    SlideBuilder,
    big_idea,
    checkpoint,
    concept_frame,
    data_table,
    definition,
    exit_ticket,
    guided_example,
    intro,
    key_point,
    bridge_slide,
    limit_card,
    limit_cards_row,
    limit_compare_note,
    limit_data_table,
    math_block,
    mcq_reveal,
    phase_divider,
    practice_packet,
    role,
    solution_steps,
    warning,
    worked_example,
)


def build(graphs: dict[str, str]) -> dict:
    s = SlideBuilder("1.4")
    _ = graphs

    s.add(
        "1.4 · Limits from tables",
        intro(
            "1",
            "1.4",
            "Estimating limit values from tables",
            [
                (3, "Launch"),
                (4, "One-sided"),
                (5, "Examples"),
                (11, "Tools"),
                (12, "AP Practice"),
                (16, "Exit"),
            ],
            lede="Numerical evidence for \\(\\displaystyle\\lim_{x\\to c} f(x)\\) — left column vs right column",
        ),
        kind="intro",
        group="divider",
    )

    s.add(
        "Bridge · from 1.3",
        bridge_slide(
            "1.4",
            "Same protocol · new representation",
            "<p><strong>1.3</strong>: trace left → \\(L^{-}\\), right → \\(L^{+}\\), then compare.</p>",
            "<p><strong>Tables</strong> list the same story: left columns (\\(x&lt;c\\)) vs right columns (\\(x&gt;c\\)).</p>",
            "Use several inputs close to \\(c\\) on each side so the trend is visible.",
            "table",
            protocol_mode="table",
            demo_html=limit_data_table(
                ["2.99", "2.999", "2.9999", "3.0001", "3.001", "3.01"],
                ["3.99", "3.999", "3.9999", "4.0001", "4.001", "4.01"],
                caption="Live preview · \\(c=3\\), outputs → \\(4\\)",
                split_at=3,
            ),
        ),
        path_phase="Launch",
    )

    s.add(
        "When we do not have a graph",
        phase_divider("Launch", "Tables as numerical evidence")
        + role("Launch", "Same question, new tool", "Graphs show approach visually; tables show approach numerically.")
        + big_idea(
            "<p>If \\(y=f(x)\\) near \\(x=3\\) looks like outputs near <strong>4</strong>, then "
            "\\(\\displaystyle\\lim_{x\\to 3} f(x)\\approx 4\\).</p>"
            + limit_data_table(
                ["2.9", "2.99", "2.999", "3.001", "3.01", "3.1"],
                ["3.90", "3.99", "3.999", "4.001", "4.01", "4.10"],
                caption="Sample table near \\(c=3\\) — watch \\(f(x)\\) close in on \\(4\\)",
                split_at=3,
            )
            + math_block("\\[\\displaystyle\\lim_{x\\to 3} f(x) \\approx 4\\]")
        )
        + concept_frame(
            "Use inputs close to c from both sides and watch outputs stabilize.",
            "AP exams often give tables when a graph would be too messy.",
            "Values of x straddle c (left list + right list).",
            "Picking only one side or averaging mismatched sides.",
            "Record \\(L^{-}\\) from left columns and \\(L^{+}\\) from right columns before deciding.",
        ),
        path_phase="Launch",
    )

    s.add(
        "One-sided limits from tables",
        phase_divider("Concept & Definition", "Read left columns vs right columns")
        + definition(
            "Table procedure",
            "<ol class='ap-procedure-list'>"
            "<li>Identify the target \\(c\\) in the limit.</li>"
            "<li><strong>Left:</strong> use \\(x\\) values with \\(x&lt;c\\) — outputs → \\(L^{-}\\).</li>"
            "<li><strong>Right:</strong> use \\(x\\) values with \\(x&gt;c\\) — outputs → \\(L^{+}\\).</li>"
            "<li>If \\(L^{-}=L^{+}\\), the two-sided limit exists and equals that value.</li>"
            "</ol>"
            + limit_cards_row([
                ("From table (left cols)", "L^{-}", "x\\to c^-"),
                ("From table (right cols)", "L^{+}", "x\\to c^+"),
            ])
        )
        + key_point(
            "Superscript reminder",
            "<p>\\(x\\to 9^{-}\\) means <em>from the left</em>; \\(x\\to 9^{+}\\) means <em>from the right</em>. "
            "The sign is not part of the number \\(c\\).</p>",
        ),
        path_phase="Concept & Definition",
    )

    s.add(
        "Example · limit exists",
        worked_example(
            "Limit at \\(x=-4\\)",
            "Use the table to estimate \\(\\displaystyle\\lim_{x\\to -4} f(x)\\).",
            "Left outputs approach 2.5; right outputs approach 2.5.",
            solution_steps([
                "<strong>Left of \\(-4\\):</strong> From \\(x=-4.4\\) and \\(-4.001\\), \\(f(x)\\) is near <strong>2.5</strong>.",
                "<strong>Right of \\(-4\\):</strong> From \\(x=-3.999\\) and \\(-3.5\\), \\(f(x)\\) is still near <strong>2.5</strong>.",
                "<strong>Conclusion:</strong> \\(L^{-}=L^{+}=2.5\\) ⇒ \\(\\displaystyle\\lim_{x\\to -4} f(x)=2.5\\).",
            ]),
            "\\(\\displaystyle\\lim_{x\\to -4} f(x)=2.5\\) (estimate from table)",
            "Round to three decimals on AP if asked; here the pattern is clear.",
            stem_math=limit_data_table(
                ["-4.4", "-4.01", "-4.001", "-3.999", "-3.99", "-3.5"],
                ["2.43", "2.48", "2.499", "2.501", "2.52", "2.68"],
                caption="Packet example 1 · \\(c=-4\\)",
                split_at=3,
            ),
            collapsible_model=True,
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · two-sided limit from symmetric table",
        guided_example(
            "<p><strong>Estimate at \\(x=9\\)</strong></p>"
            + limit_data_table(
                ["8.7", "8.99", "8.999", "9.001", "9.01", "9.8"],
                ["-5.8", "-5.05", "-5.001", "-4.999", "-4.05", "-4.0"],
                caption="Practice sheet #1 · \\(c=9\\)",
                split_at=3,
            ),
            [
                "Left columns: outputs near \\(-5\\).",
                "Right columns: outputs near \\(-4\\).",
                "\\(L^{-}\\neq L^{+}\\) ⇒ two-sided limit DNE.",
            ],
            limit_compare_note("-5", "-4", "9")
            + math_block("\\[\\displaystyle\\lim_{x\\to 9} f(x)\\ \\text{DNE}\\]"),
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · limit exists at a hole",
        worked_example(
            "Rational function table",
            "For \\(f(x)=\\dfrac{x^3-4x^2-7x+40}{x+2}\\), estimate \\(\\displaystyle\\lim_{x\\to -2} f(x)\\).",
            "Build your own table; \\(f(-2)\\) may be undefined even when the limit exists.",
            solution_steps([
                "<strong>Choose \\(x\\):</strong> Use \\(x=-2.1,\\,-2.001,\\,-2,\\,-1.999,\\,-1.9\\) (skip undefined if needed).",
                "<strong>Left trend:</strong> Outputs near <strong>21</strong> as \\(x\\to -2^{-}\\).",
                "<strong>Right trend:</strong> Outputs near <strong>21</strong> as \\(x\\to -2^{+}\\).",
            ]),
            "\\(\\displaystyle\\lim_{x\\to -2} f(x)=21\\) (table estimate; \\(f(-2)\\) undefined)",
            "Undefined in the table does not kill the limit — look at nearby rows.",
            stem_math=limit_data_table(
                ["-2.1", "-2.01", "-2.001", "-1.999", "-1.99", "-1.9"],
                ["22.01", "21.20", "21.01", "20.99", "20.80", "20.01"],
                caption="Model table (packet #2) · limit near \\(21\\)",
                split_at=3,
            ),
            collapsible_model=True,
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · textbook DNE pattern",
        phase_divider("Why It Works", "Conflicting one-sided trends")
        + definition(
            "When the limit does not exist",
            limit_data_table(
                ["-0.1", "-0.05", "-0.01", "-0.001", "0.001", "0.01", "0.05", "0.1"],
                ["-1.05", "-1.02", "-1.01", "-1.001", "0.999", "1.001", "1.02", "1.05"],
                caption="\\(g(x)\\) near \\(0\\) (textbook 1.4.2) — \\(L^{-}\\approx -1\\), \\(L^{+}\\approx 1\\)",
                split_at=4,
            )
            + limit_compare_note("-1", "1", "0")
            + math_block("\\[\\displaystyle\\lim_{x\\to 0} g(x)\\ \\text{DNE}\\]"),
        )
        + warning(
            "<p><strong>Do not average</strong> \\(-1\\) and \\(1\\). Unequal one-sided limits mean the two-sided limit "
            "does not exist.</p>"
        ),
        path_phase="Why It Works",
    )

    s.add(
        "Example · \\(x\\sqrt{x+1}-1\\) near 0",
        worked_example(
            "Textbook 1.4.1",
            "Estimate \\(\\displaystyle\\lim_{x\\to 0}\\bigl(x\\sqrt{x+1}-1\\bigr)\\) using a table.",
            "Outputs approach 2 from both sides.",
            solution_steps([
                "<strong>Left:</strong> For small negative \\(x\\), values near <strong>2</strong>.",
                "<strong>Right:</strong> For small positive \\(x\\), values near <strong>2</strong>.",
                "<strong>Limit:</strong> \\(L^{-}=L^{+}=2\\).",
            ]),
            "\\(\\displaystyle\\lim_{x\\to 0}\\bigl(x\\sqrt{x+1}-1\\bigr)=2\\)",
            "Calculator table view is fast; three-decimal reporting on AP when specified.",
            stem_math=limit_data_table(
                ["-0.1", "-0.01", "-0.001", "0.001", "0.01", "0.1"],
                ["1.94987", "1.99499", "1.99950", "2.00050", "2.00499", "2.04987"],
                caption="Textbook 1.4.1 · values approach \\(2\\)",
                split_at=3,
            ),
            collapsible_model=True,
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Nested functions · \\(\\cos(f(x))\\)",
        phase_divider("AP Connection", "Composition with table input")
        + role("Example", "Packet notes #3", "First estimate \\(f(2)\\) from the table, then think about \\(\\cos(f(x))\\).")
        + limit_data_table(
            ["1.99", "1.999", "1.9999", "2.0001", "2.001", "2.01"],
            ["4.85", "4.99", "4.999", "5.001", "5.01", "5.15"],
            caption="\\(f\\) increasing · \\(f(x)\\to 5\\) as \\(x\\to 2\\)",
            split_at=3,
        )
        + key_point(
            "Chain of reasoning",
            "<p>Table suggests \\(f(x)\\to 5\\) as \\(x\\to 2\\). By continuity of \\(\\cos\\), "
            "\\(\\displaystyle\\lim_{x\\to 2}\\cos(f(x))=\\cos(5)\\approx 0.284\\).</p>",
        )
        + math_block("\\[\\displaystyle\\lim_{x\\to 2}\\cos(f(x)) \\approx 0.284\\]")
        + checkpoint(
            "Tables give evidence for the <em>inside</em> function first; apply the outer function to the limiting value."
        )
        + key_point(
            "Unit thread",
            "<p>Graph (1.3) → table (1.4) → algebra (1.5+): each representation should give the same "
            "\\(L^{-}\\), \\(L^{+}\\), and two-sided conclusion when the limit exists.</p>",
        ),
        path_phase="AP Connection",
    )

    s.add(
        "Calculator habits",
        phase_divider("Tools", "Building tables quickly")
        + data_table(
            ["Method", "When to use"],
            [
                ["Table setup", "Fast scan near \\(c\\); watch left vs right columns"],
                ["Function notation", "More accurate values for rational expressions"],
            ],
        )
        + warning(
            "<p><strong>Evidence ≠ proof.</strong> Tables suggest limits; algebra (sections 1.5–1.6) confirms when possible.</p>"
        ),
        path_phase="Tools",
    )

    s.add(
        "Practice · classify from table",
        mcq_reveal(
            "<p>The table shows \\(f(x)\\) near \\(x=9\\):</p>"
            + limit_data_table(
                ["8.9", "8.99", "8.999", "9.001", "9.01", "9.1"],
                ["0.7", "0.8", "0.999", "2.001", "2.01", "2.3"],
                split_at=3,
            )
            + "<p>Which statement is true?</p>",
            [
                "\\(\\displaystyle\\lim_{x\\to 9} f(x)=1\\)",
                "\\(\\displaystyle\\lim_{x\\to 9} f(x)=2\\)",
                "\\(\\displaystyle\\lim_{x\\to 9^-} f(x)=2\\) and \\(\\displaystyle\\lim_{x\\to 9^+} f(x)=1\\)",
                "\\(\\displaystyle\\lim_{x\\to 9^-} f(x)=1\\) and \\(\\displaystyle\\lim_{x\\to 9^+} f(x)=2\\)",
            ],
            "D",
            "Left → 1, right → 2.",
            "<p><strong>D</strong> — left columns approach <strong>1</strong>; right columns approach <strong>2</strong>. "
            "Two-sided limit DNE. (Packet Test Prep #13)</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Practice · limit at -2 from table",
        mcq_reveal(
            "<p>Use the table (practice sheet #3):</p>"
            + limit_data_table(
                ["-2.1", "-2.001", "-1.999", "-1.9"],
                ["-8.7", "-8.999", "-9.001", "-9.4"],
            )
            + "<p>Estimate \\(\\displaystyle\\lim_{x\\to -2} f(x)\\).</p>",
            ["\\(-8.7\\)", "\\(-9\\)", "\\(-9.4\\)", "DNE"],
            "B",
            "Both sides near -9.",
            "<p><strong>B</strong> — \\(L^{-}\\approx -9\\) and \\(L^{+}\\approx -9\\).</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Practice · which limit exists?",
        mcq_reveal(
            "<p>At \\(x=11\\) the left outputs approach <strong>10</strong> and the right outputs approach <strong>9.6</strong>. "
            "Which is correct?</p>",
            [
                limit_card("x\\to 11", equals="10"),
                limit_card("x\\to 11", equals="9.6"),
                math_block("\\[\\displaystyle\\lim_{x\\to 11} f(x)\\ \\text{DNE}\\]"),
                limit_card("x\\to 11", equals="9.8"),
            ],
            "C",
            "Unequal one-sided trends.",
            "<p><strong>C</strong> — practice sheet #4 pattern (\\(10\\) vs \\(9.6\\)).</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Error analysis · averaging sides",
        phase_divider("Contrast / Error Analysis", "Table traps")
        + warning(
            "<p><strong>Mistake:</strong> averaging left and right outputs when they disagree.</p>"
            "<p><strong>Fix:</strong> report \\(L^{-}\\) and \\(L^{+}\\) separately; only claim a two-sided limit when they match.</p>"
        ),
        path_phase="Contrast / Error Analysis",
    )

    s.add(
        "Exit ticket · 1.4",
        exit_ticket([
            (
                "From a table, how do you find \\(L^{-}\\) and \\(L^{+}\\)?",
                "<p>Use columns with \\(x&lt;c\\) for \\(L^{-}\\); columns with \\(x&gt;c\\) for \\(L^{+}\\).</p>",
            ),
            (
                limit_data_table(
                    ["-0.1", "-0.05", "-0.01", "-0.001", "0.001", "0.01", "0.05", "0.1"],
                    ["-1.05", "-1.02", "-1.01", "-1.001", "1.001", "1.01", "1.02", "1.05"],
                    caption="Exit · does the two-sided limit exist at \\(0\\)?",
                    split_at=4,
                )
                + "<p>Does \\(\\displaystyle\\lim_{x\\to 0} f(x)\\) exist?</p>",
                limit_compare_note("-1", "1", "0")
                + math_block("\\[\\displaystyle\\lim_{x\\to 0} f(x)\\ \\text{DNE}\\]"),
            ),
            (
                "<p>Why can \\(f(c)\\) be missing from a table but \\(\\displaystyle\\lim_{x\\to c} f(x)\\) still exist?</p>",
                "<p>Limits describe <strong>approach</strong>; the hole at \\(c\\) does not change nearby trends.</p>",
            ),
        ]),
        group="practice",
        path_phase="Exit Ticket",
    )

    s.add(
        "Practice packet · 1.4",
        practice_packet("1.4", "Unit 1.4 · Limits from tables"),
        kind="lesson",
        group="practice",
    )

    return {
        "slug": "ap-1-4-limits-from-tables",
        "unit": 1,
        "unit_name": "Limits and Continuity",
        "section": "1.4",
        "title": "Estimating Limit Values from Tables",
        "deck_title": "AP Unit 1.4 · Limits from tables",
        "slide_count": len(s.slides),
        "slides": s.slides,
        "practice_section": "1.4",
    }
