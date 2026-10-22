"""AP Calculus Unit 1.7 — selecting procedures (rationalize & complex fractions)."""
from __future__ import annotations

from ap_calc_slide_helpers import (
    SlideBuilder,
    strategy_label_html,
    big_idea,
    bridge_slide,
    checkpoint,
    concept_frame,
    data_table,
    definition,
    exit_ticket,
    guided_example,
    intro,
    key_point,
    limit_card,
    limit_problem,
    limit_strategy_row,
    math_block,
    mcq_reveal,
    phase_divider,
    practice_packet,
    role,
    solution_steps,
    warning,
    worked_example,
)

DIRECT = "Direct substitution"
FACTOR = "Factor & cancel \\(\\tfrac{0}{0}\\)"
RATIONALIZE = "Rationalize (conjugate)"
COMPLEX = "Complex fraction (common denominator)"
DNE_INF = "Limit does not exist (infinite)"
CHOOSE = "Procedure selection"


def _ex(
    strategy: str,
    limit_tex: str,
    setup: str,
    method: str,
    steps: list[str],
    answer: str,
    check: str,
) -> str:
    return worked_example(
        strategy,
        setup,
        method,
        solution_steps(steps),
        answer,
        check,
        limit_latex=limit_tex,
        strategy_focus=strategy,
        collapsible_model=True,
    )


def build(graphs: dict[str, str]) -> dict:
    s = SlideBuilder("1.7")
    _g = graphs

    s.add(
        "1.7 · Choosing a limit procedure",
        intro(
            "1",
            "1.7",
            "Selecting procedures for determining limits",
            [
                (3, "Ladder"),
                (6, "Rationalize"),
                (14, "Fractions"),
                (22, "Mixed"),
                (28, "Check"),
                (32, "Exit"),
            ],
            lede="After 1.6 tactics: name the procedure, show the limit, then rationalize or clear denominators",
        ),
        kind="intro",
        group="divider",
    )

    s.add(
        "Bridge · from 1.6",
        bridge_slide(
            "1.7",
            "Strategies → procedures",
            "<p><strong>1.6</strong> practiced factoring, direct substitution, and special trig limits.</p>",
            "<p><strong>1.7</strong> adds <em>which tool when</em>: conjugates for radicals and LCD work for "
            "nested fractions — still with a clear limit and strategy label on every example.</p>",
            "If substitution is clean, stop. If you see \\(\\tfrac{0}{0}\\) with radicals or stacked fractions, "
            "pick rationalize or complex-fraction simplification.",
            "notation",
            protocol_mode="notation",
            demo_html=limit_card("x\\to 0", expr="\\dfrac{\\sqrt{x+7}-\\sqrt{7}}{x}", equals="\\dfrac{1}{2\\sqrt{7}}"),
        ),
        path_phase="Launch",
    )

    s.add(
        "Procedure ladder",
        phase_divider("Launch", "Decide before you compute")
        + big_idea(
            "<ol class='ap-procedure-list'>"
            "<li><strong>Direct substitution</strong> — polynomial, root at an interior point, continuous trig.</li>"
            "<li><strong>Factor & cancel</strong> — rational \\(\\tfrac{0}{0}\\) with algebraic factors.</li>"
            "<li><strong>Rationalize</strong> — \\(\\tfrac{0}{0}\\) with square roots (multiply by the conjugate).</li>"
            "<li><strong>Complex fractions</strong> — combine numerators/denominators with a common denominator, then cancel.</li>"
            "</ol>"
        )
        + data_table(
            ["Strategy", "When you use it", "What you do first"],
            [
                [strategy_label_html(DIRECT), "Finite value after plugging in \\(c\\)", "Substitute"],
                [strategy_label_html(FACTOR), "\\(\\tfrac{0}{0}\\) with polynomials", "Factor shared term"],
                [strategy_label_html(RATIONALIZE), "\\(\\tfrac{0}{0}\\) with \\(\\sqrt{\\cdot}\\)", "Multiply by conjugate"],
                [strategy_label_html(COMPLEX), "Fraction inside a fraction", "Single fraction via LCD"],
            ],
        )
        + concept_frame(
            "State the procedure in words before algebra.",
            "AP 1.7 items test method choice, not calculator speed.",
            "Radical \\(\\tfrac{0}{0}\\) vs polynomial \\(\\tfrac{0}{0}\\).",
            "Rationalizing the wrong expression (top only when the denominator has the root).",
            "After simplifying, re-check with direct substitution.",
        ),
        path_phase="Launch",
    )

    s.add(
        "Rationalizing · idea",
        phase_divider("Concept & Definition", "Conjugate multiplication")
        + definition(
            "Rationalize with a conjugate",
            "<p>For \\(\\displaystyle\\lim_{x\\to c}\\frac{\\sqrt{\\text{linear}}-\\sqrt{k}}{x-c}\\) or similar "
            "\\(\\tfrac{0}{0}\\) forms, multiply top and bottom by the conjugate "
            "\\(\\sqrt{\\text{linear}}+\\sqrt{k}\\) to remove the radical from the denominator "
            "(or to cancel the \\(x-c\\) factor).</p>"
            + warning("Multiply by \\(\\dfrac{\\text{conjugate}}{\\text{conjugate}}=1\\); do not distribute incorrectly.")
        ),
        path_phase="Concept & Definition",
    )

    s.add(
        "Example · \\(\\sqrt{x+7}-\\sqrt{7}\\) over \\(x\\)",
        _ex(
            RATIONALIZE,
            r"\lim_{x\to 0}\dfrac{\sqrt{x+7}-\sqrt{7}}{x}",
            "Substitution gives \\(\\tfrac{0}{0}\\).",
            "Multiply by \\(\\dfrac{\\sqrt{x+7}+\\sqrt{7}}{\\sqrt{x+7}+\\sqrt{7}}\\).",
            [
                "Numerator becomes \\((x+7)-7=x\\).",
                "Cancel \\(x\\): left with \\(\\dfrac{1}{\\sqrt{x+7}+\\sqrt{7}}\\).",
                "Substitute \\(x=0\\): \\(\\dfrac{1}{2\\sqrt{7}}=\\mathbf{\\dfrac{1}{2\\sqrt{7}}}\\).",
            ],
            "\\(\\dfrac{1}{2\\sqrt{7}}\\)",
            "Same pattern as \\(\\dfrac{\\sqrt{x+11}-\\sqrt{11}}{x}\\) at \\(0\\).",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · \\(\\sqrt{x+11}-\\sqrt{11}\\)",
        _ex(
            RATIONALIZE,
            r"\lim_{x\to 0}\dfrac{\sqrt{x+11}-\sqrt{11}}{x}",
            "\\(\\tfrac{0}{0}\\) with conjugate \\(\\sqrt{x+11}+\\sqrt{11}\\).",
            "Simplify to a single rational expression, then substitute.",
            [
                "After rationalizing: \\(\\dfrac{1}{\\sqrt{x+11}+\\sqrt{11}}\\).",
                "Limit \\(=\\dfrac{1}{2\\sqrt{11}}\\).",
            ],
            "\\(\\dfrac{1}{2\\sqrt{11}}\\)",
            "Memorize the template: difference of roots over a linear term.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · \\(\\sqrt{x+9}-3\\) over \\(x\\)",
        _ex(
            RATIONALIZE,
            r"\lim_{x\to 0}\dfrac{\sqrt{x+9}-3}{x}",
            "Classic conjugate setup (\\(3=\\sqrt{9}\\)).",
            "Rationalize; cancel the linear factor.",
            [
                "Simplified form \\(\\dfrac{1}{\\sqrt{x+9}+3}\\).",
                "Limit \\(=\\dfrac{1}{6}\\).",
            ],
            "\\(\\dfrac{1}{6}\\)",
            "Compare to \\(\\dfrac{\\sqrt{x+4}-2}{x}\\) at \\(0\\) (limit \\(\\tfrac{1}{4}\\)).",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · \\(\\sqrt{x+9}-4\\) at \\(x=7\\)",
        _ex(
            RATIONALIZE,
            r"\lim_{x\to 7}\dfrac{\sqrt{x+9}-4}{x-7}",
            "\\(\\tfrac{0}{0}\\); conjugate \\(\\sqrt{x+9}+4\\).",
            "Difference of squares in the numerator after multiply.",
            [
                "Cancel \\((x-7)\\); simplified \\(\\dfrac{1}{\\sqrt{x+9}+4}\\).",
                "At \\(x=7\\): \\(\\dfrac{1}{4+4}=\\mathbf{\\dfrac{1}{8}}\\).",
            ],
            "\\(\\dfrac{1}{8}\\)",
            "Breakpoint \\(x=7\\) matches \\(\\sqrt{16}-4=0\\).",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · \\(\\sqrt{x+4}-3\\) at \\(x=5\\)",
        _ex(
            RATIONALIZE,
            r"\lim_{x\to 5}\dfrac{\sqrt{x+4}-3}{x-5}",
            "Radical minus constant; denominator \\(x-5\\).",
            "Conjugate \\(\\sqrt{x+4}+3\\).",
            [
                "Numerator \\((x+4)-9=x-5\\); cancel.",
                "Limit \\(=\\dfrac{1}{\\sqrt{x+4}+3}\\big|_{x=5}=\\mathbf{\\dfrac{1}{6}}\\).",
            ],
            "\\(\\dfrac{1}{6}\\)",
            "Notes-style radical over a linear denominator.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · denominator has the root",
        _ex(
            RATIONALIZE,
            r"\lim_{x\to 10}\dfrac{x-10}{3-\sqrt{x-1}}",
            "Indeterminate; rationalize the <em>denominator</em>.",
            "Multiply by \\(\\dfrac{3+\\sqrt{x-1}}{3+\\sqrt{x-1}}\\).",
            [
                "Denominator \\(9-(x-1)=10-x=-(x-10)\\).",
                "Expression \\(\\to -(3+\\sqrt{x-1})\\).",
                "Limit \\(=-(3+3)=\\mathbf{-6}\\).",
            ],
            "\\(-6\\)",
            "Track the sign when \\(10-x\\) replaces \\(x-10\\).",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Rationalize pair",
        guided_example(
            limit_strategy_row([
                (RATIONALIZE, r"\lim_{x\to 0}\dfrac{\sqrt{x+7}-\sqrt{7}}{x}"),
                (RATIONALIZE, r"\lim_{x\to 7}\dfrac{\sqrt{x+9}-4}{x-7}"),
            ])
            + "<p>Name the strategy, then simplify.</p>",
            [
                "First limit: \\(\\dfrac{1}{2\\sqrt{7}}\\).",
                "Second limit: \\(\\dfrac{1}{8}\\).",
            ],
            math_block(
                "\\[\\displaystyle\\lim_{x\\to 0}\\frac{\\sqrt{x+7}-\\sqrt{7}}{x}=\\frac{1}{2\\sqrt{7}},"
                "\\qquad"
                "\\lim_{x\\to 7}\\frac{\\sqrt{x+9}-4}{x-7}=\\frac{1}{8}\\]"
            ),
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Complex fractions · idea",
        phase_divider("Why It Works", "One fraction at a time")
        + definition(
            "Simplify a complex fraction",
            "<p>Write nested fractions as a single ratio: combine terms in the numerator (and denominator if needed) "
            "using the <strong>least common denominator</strong>, then cancel common factors before taking the limit.</p>"
            + math_block(
                "\\[\\displaystyle\\frac{\\frac{1}{x+a}-\\frac{1}{a}}{x}"
                "\\ \\Longrightarrow\\ "
                "\\frac{-1}{a(x+a)}\\ \\Longrightarrow\\ "
                "-\\frac{1}{a^2}\\ \\text{ as } x\\to 0\\]"
            ),
        ),
        path_phase="Why It Works",
    )

    s.add(
        "Example · textbook stack",
        _ex(
            COMPLEX,
            r"\lim_{x\to 0}\dfrac{\dfrac{1}{x+2}-\dfrac{1}{2}}{x}",
            "\\(\\tfrac{0}{0}\\) from stacked fractions.",
            "LCD on the inner numerator: \\(\\dfrac{2-(x+2)}{2(x+2)}=\\dfrac{-x}{2(x+2)}\\).",
            [
                "Divide by \\(x\\): \\(-\\dfrac{1}{2(x+2)}\\).",
                "Substitute \\(x=0\\): \\(\\mathbf{-\\dfrac{1}{4}}\\).",
            ],
            "\\(-\\dfrac{1}{4}\\)",
            "Same structure as \\(\\dfrac{\\frac{1}{x+2}-\\frac12}{x}\\) in the course text.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · parameter \\(a\\)",
        _ex(
            COMPLEX,
            r"\lim_{x\to 0}\dfrac{\dfrac{1}{x+a}-\dfrac{1}{a}}{x}",
            "Combine \\(\\dfrac{1}{x+a}-\\dfrac{1}{a}\\) over LCD \\(a(x+a)\\).",
            "Cancel \\(x\\) after forming one fraction.",
            [
                "Inner numerator \\(=-\\dfrac{x}{a(x+a)}\\).",
                "Limit \\(=-\\dfrac{1}{a(x+a)}\\big|_{x=0}=\\mathbf{-\\dfrac{1}{a^2}}\\).",
            ],
            "\\(-\\dfrac{1}{a^2}\\)",
            "Keep \\(a\\neq 0\\) fixed as \\(x\\to 0\\).",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · \\(\\dfrac{1}{3}-\\dfrac{1}{3x}\\) over \\(x-1\\)",
        _ex(
            COMPLEX,
            r"\lim_{x\to 1}\dfrac{\dfrac{1}{3}-\dfrac{1}{3x}}{x-1}",
            "Complex fraction with \\((x-1)\\) in the outer denominator.",
            "LCD in numerator: \\(\\dfrac{x-1}{3x}\\).",
            [
                "Cancel \\((x-1)\\): \\(\\dfrac{1}{3x}\\).",
                "Limit \\(=\\mathbf{\\dfrac{1}{3}}\\).",
            ],
            "\\(\\dfrac{1}{3}\\)",
            "After canceling, direct substitution works.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · \\(x\\) over nested denominator",
        _ex(
            COMPLEX,
            r"\lim_{x\to 0}\dfrac{x}{\dfrac{1}{x-4}+3}",
            "Simplify denominator to a single rational expression.",
            "Combine \\(\\dfrac{1}{x-4}+3=\\dfrac{3x-11}{x-4}\\).",
            [
                "Rewrite as \\(x\\cdot\\dfrac{x-4}{3x-11}\\).",
                "Substitute \\(x=0\\): \\(0\\cdot\\dfrac{-4}{-11}=\\mathbf{0}\\).",
            ],
            "\\(0\\)",
            "Not every complex fraction gives \\(\\tfrac{0}{0}\\); check substitution last.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · \\(x\\) over reciprocal form at \\(6\\)",
        _ex(
            COMPLEX,
            r"\lim_{x\to 6}\dfrac{x}{\dfrac{1}{x+8}-\dfrac{1}{8}}",
            "Denominator \\(\\to 0\\) as a stacked difference of fractions.",
            "LCD: \\(\\dfrac{8-(x+8)}{8(x+8)}=\\dfrac{-x}{8(x+8)}\\).",
            [
                "Quotient \\(=x\\cdot\\dfrac{8(x+8)}{-x}=-8(x+8)\\) for \\(x\\neq 0\\).",
                "Limit \\(=-8(14)=\\mathbf{-112}\\).",
            ],
            "\\(-112\\)",
            "Clear the complex denominator before evaluating.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · nested reciprocal at \\(0\\)",
        _ex(
            DNE_INF,
            r"\lim_{x\to 0}\dfrac{\dfrac{1}{(x+3)^2-9}}{x}",
            "Simplify \\((x+3)^2-9=x(x+6)\\) first.",
            "Rewrite as \\(\\dfrac{1}{x^2(x+6)}\\).",
            [
                "As \\(x\\to 0\\), magnitude blows up.",
                "Two-sided limit <strong>does not exist</strong> (infinite behavior).",
            ],
            "DNE",
            "Contrast with limits that simplify to a finite number.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Complex fraction pair",
        guided_example(
            limit_strategy_row([
                (COMPLEX, r"\lim_{x\to 0}\dfrac{\dfrac{1}{x+2}-\dfrac{1}{2}}{x}"),
                (COMPLEX, r"\lim_{x\to 1}\dfrac{\dfrac{1}{3}-\dfrac{1}{3x}}{x-1}"),
            ]),
            [
                "First: \\(-\\dfrac{1}{4}\\).",
                "Second: \\(\\dfrac{1}{3}\\).",
            ],
            math_block(
                "\\[\\displaystyle\\lim_{x\\to 0}\\frac{\\frac{1}{x+2}-\\frac12}{x}=-\\frac14,"
                "\\qquad"
                "\\lim_{x\\to 1}\\frac{\\frac13-\\frac{1}{3x}}{x-1}=\\frac13\\]"
            ),
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Mixed procedures",
        phase_divider("AP Connection", "Pick one tool per limit")
        + role("AP Connection", "Procedure mix", "Factor when polynomials dominate; rationalize when roots appear.")
        + checkpoint("Read the limit once and label the strategy before touching algebra."),
        path_phase="AP Connection",
    )

    s.add(
        "Example · direct root",
        _ex(
            DIRECT,
            r"\lim_{x\to 1}\sqrt{x+4}",
            "\\(\\sqrt{x+4}\\) is continuous at \\(x=1\\).",
            "Substitute.",
            ["\\(\\sqrt{5}\\)."],
            "\\(\\sqrt{5}\\)",
            "Do not rationalize when substitution already works.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · factor rational",
        _ex(
            FACTOR,
            r"\lim_{x\to 5}\dfrac{x^2-5x}{x-5}",
            "\\(\\tfrac{0}{0}\\); factor \\(x\\) from the numerator.",
            "Cancel \\((x-5)\\).",
            [
                "\\(\\dfrac{x(x-5)}{x-5}=x\\) for \\(x\\neq 5\\).",
                "Limit \\(=\\mathbf{5}\\).",
            ],
            "\\(5\\)",
            "Procedure ladder: try factor before conjugates when there are no radicals.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · factor at \\(-3\\)",
        _ex(
            FACTOR,
            r"\lim_{x\to -3}\dfrac{x-2}{x^2-3x+2}",
            "Denominator nonzero at \\(-3\\); still check substitution.",
            "Direct substitution after quick factor check.",
            [
                "At \\(x=-3\\): \\(\\dfrac{-5}{9+9+2}=\\dfrac{-5}{20}=\\mathbf{-\\dfrac{1}{4}}\\).",
            ],
            "\\(-\\dfrac{1}{4}\\)",
            "If denominator were \\(0\\), you would factor and cancel instead.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · powers in numerator",
        _ex(
            DIRECT,
            r"\lim_{x\to 0}\dfrac{2x^4+5x^4}{x^4}",
            "Combine like terms in the numerator.",
            "Simplify to a constant for \\(x\\neq 0\\).",
            [
                "\\(\\dfrac{7x^4}{x^4}=7\\).",
                "Limit \\(=\\mathbf{7}\\).",
            ],
            "\\(7\\)",
            "Cancel powers before substituting.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · root over \\(x\\) at \\(3\\)",
        _ex(
            DIRECT,
            r"\lim_{x\to 3}\dfrac{\sqrt{2x-6}}{x}",
            "Numerator \\(\\to 0\\), denominator \\(3\\).",
            "Substitute into the simplified form.",
            ["\\(\\dfrac{0}{3}=\\mathbf{0}\\)."],
            "\\(0\\)",
            "Interior limit of a continuous root — no conjugate needed.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Procedure row · three types",
        guided_example(
            limit_strategy_row([
                (FACTOR, r"\lim_{x\to 4}\dfrac{x^2-16}{x-4}"),
                (RATIONALIZE, r"\lim_{x\to 0}\dfrac{\sqrt{x+9}-3}{x}"),
                (COMPLEX, r"\lim_{x\to 0}\dfrac{\dfrac{1}{x+2}-\dfrac{1}{2}}{x}"),
            ])
            + "<p>Match each limit to factor, rationalize, or complex fraction.</p>",
            [
                "Factor: \\(x+4\\to 8\\).",
                "Rationalize: \\(\\dfrac{1}{6}\\).",
                "Complex: \\(-\\dfrac{1}{4}\\).",
            ],
            math_block(
                "\\[8,\\quad \\tfrac{1}{6},\\quad -\\tfrac{1}{4}\\]"
            ),
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Checkpoint MCQ · conjugate form",
        mcq_reveal(
            limit_problem(
                r"\lim_{x\to b}\dfrac{b-x}{\sqrt{x}-\sqrt{b}}",
                RATIONALIZE,
            )
            + "<p>Which value is correct? (Assume \\(b>0\\).)</p>",
            [
                "\\(-2\\sqrt{b}\\)",
                "\\(-\\sqrt{b}\\)",
                "\\(2b\\)",
                "\\(\\sqrt{b}\\)",
                "\\(2\\sqrt{b}\\)",
            ],
            "A",
            "Multiply by conjugate; watch \\(x-b\\) sign.",
            "<p><strong>A</strong> — rationalize to \\(-(\\sqrt{x}+\\sqrt{b})\\to -2\\sqrt{b}\\).</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Checkpoint MCQ · procedure choice",
        mcq_reveal(
            limit_problem(r"\lim_{x\to 0}\dfrac{\sqrt{x+4}-2}{x}", CHOOSE)
            + "<p>Best first procedure?</p>",
            [
                "Direct substitution only",
                "Factor polynomials",
                "Rationalize with a conjugate",
                "Squeeze Theorem",
                "Compare one-sided limits only",
            ],
            "C",
            "Radical difference over linear term.",
            "<p><strong>C</strong> — \\(\\tfrac{0}{0}\\) with square roots calls for a conjugate; limit \\(=\\tfrac{1}{4}\\).</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Checkpoint MCQ · complex fraction",
        mcq_reveal(
            limit_problem(
                r"\lim_{x\to 0}\dfrac{\dfrac{1}{x+2}-\dfrac{1}{2}}{x}",
                COMPLEX,
            )
            + "<p>Final value?</p>",
            ["\\(-\\dfrac{1}{2}\\)", "\\(-\\dfrac{1}{4}\\)", "\\(0\\)", "\\(\\dfrac{1}{4}\\)", "DNE"],
            "B",
            "LCD then cancel x",
            "<p><strong>B</strong> — simplifies to \\(-\\dfrac{1}{2(x+2)}\\to -\\dfrac{1}{4}\\).</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Exit ticket · 1.7",
        exit_ticket([
            (
                "When do you rationalize instead of factor?",
                "<p>When \\(\\tfrac{0}{0}\\) involves <strong>square roots</strong> (difference of radicals or root minus constant), "
                "multiply by the conjugate.</p>",
            ),
            (
                limit_problem(r"\lim_{x\to 0}\dfrac{\sqrt{x+7}-\sqrt{7}}{x}", RATIONALIZE)
                + "<p>Final value?</p>",
                "<p>\\(\\mathbf{\\dfrac{1}{2\\sqrt{7}}}\\).</p>",
            ),
            (
                limit_problem(
                    r"\lim_{x\to 0}\dfrac{\dfrac{1}{x+2}-\dfrac{1}{2}}{x}",
                    COMPLEX,
                )
                + "<p>Final value?</p>",
                "<p>\\(\\mathbf{-\\dfrac{1}{4}}\\).</p>",
            ),
        ]),
        group="practice",
        path_phase="Exit Ticket",
    )

    s.add(
        "Practice packet · 1.7",
        practice_packet("1.7", "Unit 1.7 · Selecting limit procedures"),
        kind="lesson",
        group="practice",
    )

    return {
        "slug": "ap-1-7-selecting-limit-procedures",
        "unit": 1,
        "unit_name": "Limits and Continuity",
        "section": "1.7",
        "title": "Selecting Procedures for Determining Limits",
        "deck_title": "AP Unit 1.7 · Rationalize & complex fractions",
        "slide_count": len(s.slides),
        "slides": s.slides,
        "practice_section": "1.7",
    }
