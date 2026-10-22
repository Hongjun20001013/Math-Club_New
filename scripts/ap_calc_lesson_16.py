"""AP Calculus Unit 1.6 — determining limits by algebraic manipulation."""
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
    fig,
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

# Shorthand strategy labels (shown as "Strategy · …" on each problem card)
DIRECT = "Direct substitution"
CONST = "Direct substitution (constant)"
FACTOR = "Factor & cancel \\(\\tfrac{0}{0}\\)"
DIFF_SQ = "Factor & cancel (difference of squares)"
DNE_INF = "Limit does not exist (infinite)"
TRIG_SIN = "Special trig limit \\(\\sin(kx)/x\\)"
TRIG_RATIO = "Special trig limit (ratio of sines)"
TRIG_ID = "Trig identity + \\(\\sin x/x\\)"
SIGN_FLIP = "Factor & cancel (watch denominator sign)"
TRIG_POINT = "Direct substitution (trig at a point)"
TRIG_MIX = "Trig identity + special limits"


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
    s = SlideBuilder("1.6")
    g = graphs

    s.add(
        "1.6 · Limit strategies",
        intro(
            "1",
            "1.6",
            "Determining limits using algebraic manipulation",
            [
                (3, "Strategies"),
                (5, "Direct sub"),
                (11, "Factor"),
                (20, "Trig"),
                (28, "Mixed"),
                (33, "Check"),
                (37, "Exit"),
            ],
            lede="Every limit starts with a strategy: substitute, factor, trig limit, or recognize DNE",
        ),
        kind="intro",
        group="divider",
    )

    s.add(
        "Bridge · from 1.5",
        bridge_slide(
            "1.6",
            "Laws → strategies",
            "<p><strong>1.5</strong> combined limits with algebra laws.</p>",
            "<p><strong>1.6</strong> is your <em>limit strategy</em> unit: pick a tactic, show the limit clearly, "
            "then simplify.</p>",
            "Each example below labels the strategy before the solution.",
            "notation",
            protocol_mode="notation",
            demo_html=limit_card("x\\to 0", expr="\\dfrac{\\sin x}{x}", equals="1"),
        ),
        path_phase="Launch",
    )

    s.add(
        "Limit strategy map",
        phase_divider("Launch", "Choose before you calculate")
        + big_idea(
            "<ol class='ap-procedure-list'>"
            "<li><strong>Direct substitution</strong> — polynomials, constants, continuous trig at \\(c\\).</li>"
            "<li><strong>Factor & cancel</strong> — when substitution gives \\(\\tfrac{0}{0}\\).</li>"
            "<li><strong>Special trig limits</strong> — \\(\\sin(kx)/x\\), \\(\\cos\\) identities near \\(0\\).</li>"
            "<li><strong>DNE / infinite</strong> — denominator \\(\\to 0\\) with no cancellable factor.</li>"
            "</ol>"
        )
        + data_table(
            ["Strategy", "When you use it", "What you do first"],
            [
                [strategy_label_html(DIRECT), "Clean number after plugging in \\(c\\)", "Substitute and stop"],
                [strategy_label_html(FACTOR), "\\(\\tfrac{0}{0}\\) rational form", "Factor, cancel, substitute"],
                [strategy_label_html(TRIG_SIN), "\\(\\sin(kx)\\) with \\(x\\to 0\\)", "Build \\(\\sin(kx)/(kx)\\)"],
                [strategy_label_html(DNE_INF), "Nonzero over zero after factoring", "Do not invent a finite value"],
            ],
        )
        + concept_frame(
            "Name the strategy before doing algebra.",
            "AP items reward a clear method, not guessing.",
            "Indeterminate \\(\\tfrac{0}{0}\\) vs blow-up form.",
            "Canceling terms instead of factors.",
            "Write the strategy name in the margin on every limit you attempt.",
        ),
        path_phase="Launch",
    )

    s.add(
        "Direct substitution",
        phase_divider("Concept & Definition", "When plugging in works")
        + definition(
            "Direct substitution",
            "<p>If \\(f\\) is a polynomial, constant, or continuous at \\(c\\), then</p>"
            + math_block("\\[\\displaystyle\\lim_{x\\to c} f(x) = f(c).\\]")
        ),
        path_phase="Concept & Definition",
    )

    s.add(
        "Example · constant",
        _ex(
            CONST,
            r"\lim_{x\to 2} 6",
            "A constant does not depend on \\(x\\).",
            "The value is already simplified.",
            ["\\(\\displaystyle\\lim_{x\\to 2} 6 = \\mathbf{6}\\)."],
            "\\(6\\)",
            "Constants are the fastest direct-substitution case.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · polynomial",
        _ex(
            DIRECT,
            r"\lim_{x\to -1}(x^2+2x-4)",
            "Polynomial → substitute \\(x=-1\\).",
            "Evaluate the expression at the approach value.",
            [
                "\\((-1)^2+2(-1)-4 = 1-2-4\\).",
                "\\(\\displaystyle\\lim_{x\\to -1}(x^2+2x-4)=\\mathbf{-5}\\).",
            ],
            "\\(-5\\)",
            "No factoring when there is no denominator.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · quadratic expression",
        _ex(
            DIRECT,
            r"\lim_{x\to 2}(x-x^2)",
            "Substitute \\(x=2\\).",
            "Watch the sign on \\(x^2\\).",
            ["\\(2-4=\\mathbf{-2}\\)."],
            "\\(-2\\)",
            "Order of terms does not change the limit.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · squared binomial",
        _ex(
            DIRECT,
            r"\lim_{x\to 5}(x+1)^2",
            "Expand or substitute first — here substitution is faster.",
            "Compute \\((5+1)^2\\).",
            ["\\(6^2=\\mathbf{36}\\)."],
            "\\(36\\)",
            "Powers of continuous expressions use direct substitution.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "More direct substitution",
        guided_example(
            limit_strategy_row([
                (DIRECT, r"\lim_{x\to -2}(3x^2-x+1)"),
                (DIRECT, r"\lim_{x\to 3}(2x^2+5x-6)"),
            ])
            + "<p>Try each limit before opening hints.</p>",
            [
                "At \\(x=-2\\): \\(3(4)-(-2)+1=12+2+1=15\\).",
                "At \\(x=3\\): \\(2(9)+15-6=18+15-6=27\\).",
            ],
            math_block(
                "\\[\\displaystyle\\lim_{x\\to -2}(3x^2-x+1)=15,"
                "\\qquad"
                "\\lim_{x\\to 3}(2x^2+5x-6)=27\\]"
            ),
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Factor and cancel",
        phase_divider("Why It Works", "Remove the hole")
        + definition(
            "Factor & cancel",
            "<p>When direct substitution gives \\(\\tfrac{0}{0}\\), factor, cancel common factors, "
            "then substitute into the simplified form.</p>"
            + warning("Cancel factors, not individual terms.")
        ),
        path_phase="Why It Works",
    )

    s.add(
        "Example · factor \\(x\\)",
        _ex(
            FACTOR,
            r"\lim_{x\to 0}\dfrac{4x^2-15x}{x}",
            "Direct sub gives \\(\\tfrac{0}{0}\\).",
            "Factor \\(x\\) from the numerator, then cancel.",
            [
                "\\(\\dfrac{x(4x-15)}{x}=4x-15\\) for \\(x\\neq 0\\).",
                "Limit \\(=4(0)-15=\\mathbf{-15}\\).",
            ],
            "\\(-15\\)",
            "State that \\(x\\neq 0\\) when you cancel.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · difference of squares (1)",
        _ex(
            DIFF_SQ,
            r"\lim_{x\to -7}\dfrac{x^2-49}{x+7}",
            "Substitution gives \\(\\tfrac{0}{0}\\).",
            "Factor \\(x^2-49=(x-7)(x+7)\\).",
            [
                "Cancel \\((x+7)\\): left with \\(x-7\\).",
                "\\(\\displaystyle\\lim_{x\\to -7}(x-7)=-7-7=\\mathbf{-14}\\).",
            ],
            "\\(-14\\)",
            "Difference of squares is a common AP pattern.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · factor quadratic",
        _ex(
            FACTOR,
            r"\lim_{x\to 1}\dfrac{x^2+5x-6}{x-1}",
            "True \\(\\tfrac{0}{0}\\).",
            "Factor numerator: \\((x+6)(x-1)\\).",
            [
                "Cancel \\((x-1)\\).",
                "\\(\\displaystyle\\lim_{x\\to 1}(x+6)=\\mathbf{7}\\).",
            ],
            "\\(7\\)",
            "Always check for a shared linear factor.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · difference of squares (2)",
        _ex(
            DIFF_SQ,
            r"\lim_{x\to 8}\dfrac{x^2-64}{x-8}",
            "Numerator is \\(x^2-8^2\\).",
            "Cancel \\((x-8)\\), then substitute.",
            [
                "Simplified form: \\(x+8\\).",
                "Limit \\(=8+8=\\mathbf{16}\\).",
            ],
            "\\(16\\)",
            "Same strategy as the \\(x=-7\\) example with a different center.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · factor at \\(x=4\\)",
        _ex(
            FACTOR,
            r"\lim_{x\to 4}\dfrac{5x^2-21x+4}{x-4}",
            "Substitution gives \\(\\tfrac{0}{0}\\).",
            "Factor numerator: \\((5x-1)(x-4)\\).",
            [
                "Cancel \\((x-4)\\); simplified form \\(5x-1\\).",
                "\\(\\displaystyle\\lim_{x\\to 4}(5x-1)=5(4)-1=\\mathbf{19}\\).",
            ],
            "\\(19\\)",
            "Synthetic division at \\(x=4\\) is fast when the quadratic is messy.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · rational at \\(x=\\tfrac{1}{3}\\)",
        _ex(
            FACTOR,
            r"\lim_{x\to \frac{1}{3}}\dfrac{6x^2+7x-3}{3x-1}",
            "Check \\(\\tfrac{0}{0}\\) at \\(x=\\tfrac{1}{3}\\).",
            "Factor numerator: \\((3x-1)(2x+3)\\).",
            [
                "Cancel \\((3x-1)\\); left with \\(2x+3\\).",
                "\\(\\displaystyle\\lim_{x\\to \\frac{1}{3}}(2x+3)=\\dfrac{2}{3}+3=\\mathbf{\\dfrac{11}{3}}\\).",
            ],
            "\\(\\dfrac{11}{3}\\)",
            "Fractional centers still use the same factor-and-cancel strategy.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · limit DNE",
        _ex(
            DNE_INF,
            r"\lim_{x\to 1}\dfrac{x^2-5x}{x-1}",
            "Numerator \\(\\to -4\\), denominator \\(\\to 0\\).",
            "No common factor \\((x-1)\\) in the numerator.",
            [
                "Left and right approaches have opposite infinite behavior.",
                "Two-sided limit <strong>does not exist</strong>.",
            ],
            "DNE",
            "Not every rational with denominator \\(0\\) is a removable hole.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · cancel to a finite value",
        _ex(
            FACTOR,
            r"\lim_{x\to -6}\dfrac{x^2+11x+30}{x+6}",
            "This is \\(\\tfrac{0}{0}\\) with a shared factor.",
            "Factor quadratic numerator.",
            [
                "\\(x^2+11x+30=(x+5)(x+6)\\).",
                "Cancel \\((x+6)\\): limit \\(\\displaystyle\\lim_{x\\to -6}(x+5)=\\mathbf{-1}\\).",
            ],
            "\\(-1\\)",
            "Contrast with the previous slide: factoring can give a finite answer.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · factor at \\(x=4\\) (numerator quadratic)",
        _ex(
            FACTOR,
            r"\lim_{x\to 4}\dfrac{x^2-2x-8}{x-4}",
            "\\(\\tfrac{0}{0}\\) form.",
            "Factor \\(x^2-2x-8=(x-4)(x+2)\\).",
            [
                "Cancel \\((x-4)\\).",
                "\\(\\displaystyle\\lim_{x\\to 4}(x+2)=4+2=\\mathbf{6}\\).",
            ],
            "\\(6\\)",
            "Always verify that your factorization shares the denominator factor.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Factor & cancel · try two",
        guided_example(
            limit_strategy_row([
                (DIFF_SQ, r"\lim_{x\to 4}\dfrac{x^2-16}{x-4}"),
                (FACTOR, r"\lim_{x\to -3}\dfrac{x^2+4x+3}{x+3}"),
            ])
            + "<p>Name the strategy, then simplify each limit.</p>",
            [
                "First: \\(x^2-16=(x-4)(x+4)\\); after cancel, \\(x+4\\to 8\\).",
                "Second: \\(x^2+4x+3=(x+3)(x+1)\\); after cancel, \\(x+1\\to -2\\).",
            ],
            math_block(
                "\\[\\displaystyle\\lim_{x\\to 4}\\frac{x^2-16}{x-4}=8,"
                "\\qquad"
                "\\lim_{x\\to -3}\\frac{x^2+4x+3}{x+3}=-2\\]"
            ),
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Special trigonometric limits",
        phase_divider("AP Connection", "Near \\(x=0\\)")
        + definition(
            "Memorize these",
            math_block(
                "\\[\\displaystyle\\lim_{x\\to 0}\\frac{\\sin x}{x}=1"
                "\\qquad"
                "\\displaystyle\\lim_{x\\to 0}\\frac{1-\\cos x}{x}=0\\]"
            )
        )
        + fig(g["sin_over_x_16"], "Graph of \\(\\dfrac{\\sin x}{x}\\)", cls="ap-fig--teach"),
        path_phase="AP Connection",
    )

    s.add(
        "Example · \\(\\sin(3x)/x\\)",
        _ex(
            TRIG_SIN,
            r"\lim_{x\to 0}\dfrac{\sin(3x)}{x}",
            "Build \\(\\dfrac{\\sin(3x)}{3x}\\).",
            "Multiply by \\(3/3\\).",
            [
                "\\(\\dfrac{\\sin(3x)}{x}=3\\cdot\\dfrac{\\sin(3x)}{3x}\\to 3\\cdot 1\\).",
            ],
            "\\(3\\)",
            "Any \\(\\sin(kx)/x\\) at \\(0\\) becomes \\(k\\).",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · ratio \\(\\sin(7x)/\\sin(9x)\\)",
        _ex(
            TRIG_RATIO,
            r"\lim_{x\to 0}\dfrac{\sin(7x)}{\sin(9x)}",
            "Divide top and bottom by \\(x\\).",
            "Rewrite using \\(\\sin(kx)/(kx)\\to 1\\).",
            [
                "Limit \\(=\\dfrac{7}{9}\\cdot\\dfrac{\\sin(7x)/(7x)}{\\sin(9x)/(9x)}\\to \\dfrac{7}{9}\\).",
            ],
            "\\(\\dfrac{7}{9}\\)",
            "General form: \\(\\displaystyle\\lim_{x\\to 0}\\frac{\\sin(ax)}{\\sin(bx)}=\\frac{a}{b}\\).",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · \\(\\cos^2 x-1\\)",
        _ex(
            TRIG_ID,
            r"\lim_{x\to 0}\dfrac{\cos^2 x-1}{x(\cos x+4)}",
            "Use \\(\\cos^2 x-1=-\\sin^2 x\\).",
            "Factor \\(\\sin^2 x\\) and use \\(\\sin x/x\\).",
            [
                "Numerator \\(\\to 0\\) faster than denominator \\(\\to 0\\).",
                "Limit \\(=\\mathbf{0}\\).",
            ],
            "\\(0\\)",
            "Pythagorean identity is the key strategy here.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Trig strategy pair",
        guided_example(
            limit_strategy_row([
                (TRIG_SIN, r"\lim_{x\to 0}\dfrac{3x}{\sin x}"),
                (TRIG_SIN, r"\lim_{x\to 0}\dfrac{\sin(2x)}{3x}"),
            ]),
            [
                "First: \\(3\\cdot\\dfrac{x}{\\sin x}\\to 3\\).",
                "Second: \\(\\dfrac{2}{3}\\cdot\\dfrac{\\sin(2x)}{2x}\\to \\dfrac{2}{3}\\).",
            ],
            math_block(
                "\\[\\displaystyle\\lim_{x\\to 0}\\frac{3x}{\\sin x}=3,"
                "\\qquad"
                "\\lim_{x\\to 0}\\frac{\\sin(2x)}{3x}=\\frac{2}{3}\\]"
            ),
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · factor \\(x\\) in numerator (2)",
        _ex(
            FACTOR,
            r"\lim_{x\to 0}\dfrac{3x^2+5x}{x}",
            "\\(\\tfrac{0}{0}\\) — factor \\(x\\).",
            "Cancel and substitute.",
            [
                "\\(\\dfrac{x(3x+5)}{x}=3x+5\\to \\mathbf{5}\\).",
            ],
            "\\(5\\)",
            "Same strategy as the \\(4x^2-15x\\) example.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · denominator sign flip (1)",
        _ex(
            SIGN_FLIP,
            r"\lim_{x\to 2}\dfrac{x^2+6x-16}{2-x}",
            "Rewrite \\(2-x=-(x-2)\\).",
            "Factor numerator by \\((x-2)\\).",
            [
                "\\(x^2+6x-16=(x-2)(x+8)\\).",
                "Limit \\(=-(2+8)=\\mathbf{-10}\\).",
            ],
            "\\(-10\\)",
            "Track the negative from the denominator.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · denominator sign flip (2)",
        _ex(
            SIGN_FLIP,
            r"\lim_{x\to 5}\dfrac{2x^2-17x+35}{5-x}",
            "Factor numerator; \\(5-x=-(x-5)\\).",
            "Cancel \\((x-5)\\) with sign care.",
            [
                "\\(2x^2-17x+35=(2x-7)(x-5)\\).",
                "Limit \\(=-(10-7)=\\mathbf{-3}\\).",
            ],
            "\\(-3\\)",
            "Pair with the \\(2-x\\) example for review.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · trig at a point",
        _ex(
            TRIG_POINT,
            r"\lim_{x\to \pi}\cos x",
            "\\(\\cos x\\) is continuous at \\(\\pi\\).",
            "Direct substitution.",
            ["\\(\\cos\\pi=\\mathbf{-1}\\)."],
            "\\(-1\\)",
            "Not every trig limit needs \\(\\sin x/x\\).",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · nested trig",
        _ex(
            TRIG_MIX,
            r"\lim_{x\to 0}\dfrac{(1-\cos^2 x)\sin x}{x^2}",
            "Use \\(1-\\cos^2 x=\\sin^2 x\\).",
            "Rewrite as \\(\\dfrac{\\sin^3 x}{x^2}\\).",
            [
                "\\(=\\dfrac{\\sin x}{x}\\cdot\\sin^2 x\\to 1\\cdot 0=\\mathbf{0}\\).",
            ],
            "\\(0\\)",
            "Combine identities before applying special limits.",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · infinite from rational",
        _ex(
            DNE_INF,
            r"\lim_{x\to 0}\dfrac{7x^2+5}{x}",
            "Denominator \\(\\to 0\\), numerator \\(\\to 5\\neq 0\\).",
            "No factor of \\(x\\) to cancel in the numerator at this form.",
            [
                "Magnitude grows without bound as \\(x\\to 0\\).",
                "Limit <strong>does not exist</strong> (infinite behavior).",
            ],
            "DNE",
            "Distinguish \\(\\tfrac{0}{0}\\) from \\(\\tfrac{\\text{nonzero}}{0}\\).",
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Checkpoint MCQ · logarithm",
        mcq_reveal(
            limit_problem(r"\lim_{x\to 1}\dfrac{\ln x}{3x}", DIRECT)
            + "<p>Which value is correct?</p>",
            ["\\(0\\)", "\\(\\dfrac{3}{e}\\)", "\\(e\\)", "\\(3\\)", "The limit does not exist"],
            "A",
            "ln 1 = 0",
            "<p><strong>A</strong> — direct substitution on a continuous expression at \\(x=1\\).</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Checkpoint MCQ · perfect square",
        mcq_reveal(
            limit_problem(r"\lim_{x\to a}\dfrac{x^2-2ax+a^2}{x-a}", FACTOR)
            + "<p>Which value is correct?</p>",
            ["\\(-\\infty\\)", "\\(a\\)", "\\(0\\)", "\\(\\infty\\)", "The limit does not exist"],
            "C",
            "Numerator is (x-a)^2",
            "<p><strong>C</strong> — cancel one \\((x-a)\\); remaining factor \\((x-a)\\to 0\\).</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Checkpoint MCQ · trig rational",
        mcq_reveal(
            limit_problem(r"\lim_{x\to 0}\dfrac{4\sin x\cos x-\sin x}{x^2}", TRIG_MIX)
            + "<p>Which value is correct?</p>",
            ["\\(2\\)", "\\(\\dfrac{40}{3}\\)", "\\(\\infty\\)", "\\(0\\)", "undefined"],
            "D",
            "Factor sin x",
            "<p><strong>D</strong> — \\(\\sin x(4\\cos x-1)/x^2\\to 0\\) from small-angle behavior.</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Checkpoint MCQ · cosine in numerator",
        mcq_reveal(
            limit_problem(r"\lim_{x\to 0}\left(\dfrac{3x^2+5\cos x-5}{2x}\right)", FACTOR)
            + "<p>Which value is correct?</p>",
            ["\\(0\\)", "\\(\\dfrac{5}{2}\\)", "\\(3\\)", "\\(4\\)", "Does not exist"],
            "A",
            "0/0 with cos expansion",
            "<p><strong>A</strong> — numerator \\(\\to 0\\), denominator \\(\\to 0\\); algebra gives limit \\(0\\).</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Exit ticket · 1.6",
        exit_ticket([
            (
                "List two strategies from this lesson.",
                "<p><strong>Direct substitution</strong> and <strong>factor & cancel</strong> "
                "(plus special trig when you see \\(\\sin(kx)\\) near \\(0\\)).</p>",
            ),
            (
                limit_problem(r"\lim_{x\to 0}\dfrac{\sin(5x)}{x}", TRIG_SIN)
                + "<p>Final value?</p>",
                "<p>\\(\\mathbf{5}\\).</p>",
            ),
            (
                limit_problem(r"\lim_{x\to 4}\dfrac{x^2-16}{x-4}", DIFF_SQ)
                + "<p>Final value?</p>",
                "<p>\\(\\mathbf{8}\\).</p>",
            ),
        ]),
        group="practice",
        path_phase="Exit Ticket",
    )

    s.add(
        "Practice packet · 1.6",
        practice_packet("1.6", "Unit 1.6 · Algebraic manipulation of limits"),
        kind="lesson",
        group="practice",
    )

    return {
        "slug": "ap-1-6-algebraic-manipulation-limits",
        "unit": 1,
        "unit_name": "Limits and Continuity",
        "section": "1.6",
        "title": "Determining Limits Using Algebraic Manipulation",
        "deck_title": "AP Unit 1.6 · Limit strategies",
        "slide_count": len(s.slides),
        "slides": s.slides,
        "practice_section": "1.6",
    }
