"""AP Calculus Unit 1.6 — determining limits by algebraic manipulation."""
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
    s = SlideBuilder("1.6")
    g = graphs

    s.add(
        "1.6 · Algebraic manipulation",
        intro(
            "1",
            "1.6",
            "Determining limits using algebraic manipulation",
            [
                (3, "Strategies"),
                (6, "Direct sub"),
                (9, "Factor"),
                (14, "Trig"),
                (19, "Mixed"),
                (23, "AP Practice"),
                (26, "Exit"),
            ],
            lede="Choose a strategy: substitute, factor and cancel, or use special trig limits",
        ),
        kind="intro",
        group="divider",
    )

    s.add(
        "Bridge · from 1.5",
        bridge_slide(
            "1.6",
            "Laws → tactics",
            "<p><strong>1.5</strong> let you split limits across sums, products, and piecewise branches.</p>",
            "<p><strong>1.6</strong> is the <em>toolbox</em>: when substitution stalls, rewrite the expression "
            "(factor, rationalize, trig identities) so the limit becomes obvious.</p>",
            "Tables and graphs suggest the answer; algebra confirms it.",
            "notation",
            protocol_mode="notation",
            demo_html=limit_card("x\\to 0", expr="\\dfrac{\\sin x}{x}", equals="1"),
        ),
        path_phase="Launch",
    )

    s.add(
        "Limit strategy flowchart",
        phase_divider("Launch", "Pick a tactic before calculating")
        + big_idea(
            "<ol class='ap-procedure-list'>"
            "<li><strong>Try direct substitution</strong> — plug \\(c\\) into a simplified form.</li>"
            "<li>If you get a <strong>number</strong>, stop (unless the domain blocks \\(x=c\\)).</li>"
            "<li>If you get <strong>\\(\\tfrac{0}{0}\\)</strong>, factor / cancel common terms or rationalize.</li>"
            "<li>If you see <strong>\\(\\sin\\)</strong> or <strong>\\(\\cos\\)</strong> near \\(0\\), use special trig limits.</li>"
            "<li>If simplified denominators still go to \\(0\\) with nonzero numerator → often <strong>DNE</strong> or infinite.</li>"
            "</ol>"
        )
        + data_table(
            ["Strategy", "When to use", "Packet cue"],
            [
                ["Direct substitution", "Polynomials, continuous functions at \\(c\\)", "Notes #1–2"],
                ["Factor & cancel", "\\(\\tfrac{0}{0}\\) with algebraic factors", "Notes #3–5, Practice #3–4"],
                ["Special trig", "\\(\\sin(kx)/x\\), \\(\\cos\\) near \\(0\\)", "Notes #6–8"],
                ["Rewrite / conjugate", "\\(\\cos^2 x-1\\), nested fractions", "Practice #18, #23"],
            ],
        )
        + concept_frame(
            "Match the algebra move to the indeterminate form.",
            "AP exam items cycle the same four moves with different coefficients.",
            "Factor completely before canceling; cancel only common factors.",
            "Canceling terms instead of factors; forgetting \\(x\\neq c\\) in the simplified form.",
            "Name your strategy in the margin before simplifying.",
        ),
        path_phase="Launch",
    )

    s.add(
        "Direct substitution",
        phase_divider("Concept & Definition", "When plugging in works")
        + definition(
            "Direct substitution",
            "<p>If \\(f\\) is a polynomial or a rational function with nonzero denominator at \\(c\\), then</p>"
            + math_block("\\[\\displaystyle\\lim_{x\\to c} f(x) = f(c).\\]")
            + key_point(
                "Constants",
                "<p>\\(\\displaystyle\\lim_{x\\to 2} 6 = 6\\). A constant function ignores the approach value.</p>",
            ),
        ),
        path_phase="Concept & Definition",
    )

    s.add(
        "Example · polynomial at c",
        worked_example(
            "Notes #1",
            "Evaluate \\(\\displaystyle\\lim_{x\\to -1}(x^2+2x-4)\\).",
            "Polynomial → direct substitution.",
            solution_steps([
                "Strategy: <strong>direct substitution</strong>.",
                "\\((-1)^2+2(-1)-4 = 1-2-4\\).",
                "\\(\\displaystyle\\lim_{x\\to -1}(x^2+2x-4)=\\mathbf{-5}\\).",
            ]),
            "\\(-5\\)",
            "No factoring needed when the denominator is absent.",
            collapsible_model=True,
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · more direct substitution",
        guided_example(
            "<p><strong>Practice sheet</strong> (direct substitution only):</p>"
            + data_table(
                ["Limit", "Work", "Value"],
                [
                    ["\\(\\displaystyle\\lim_{x\\to 2}(x-x^2)\\)", "\\(2-4\\)", "\\(-2\\)"],
                    ["\\(\\displaystyle\\lim_{x\\to 5}(x+1)^2\\)", "\\(6^2\\)", "\\(36\\)"],
                    ["\\(\\displaystyle\\lim_{x\\to -2}(3x^2-x+1)\\)", "\\(12+2+1\\)", "\\(15\\)"],
                    ["\\(\\displaystyle\\lim_{x\\to 3}(2x^2+5x-6)\\)", "\\(18+15-6\\)", "\\(27\\)"],
                ],
            ),
            [
                "Each integrand is a polynomial — substitute \\(x=c\\).",
                "Watch signs on squared terms.",
            ],
            checkpoint("If substitution gives a single number and no domain issue, you are done."),
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Factor and cancel",
        phase_divider("Why It Works", "Remove the hole algebraically")
        + definition(
            "Factor & cancel",
            "<p>When direct substitution yields \\(\\tfrac{0}{0}\\), factor numerator and denominator, "
            "cancel <strong>common factors</strong>, then substitute into the simplified expression.</p>"
            + math_block(
                "\\[\\displaystyle\\lim_{x\\to c}\\frac{p(x)}{q(x)}"
                "=\\lim_{x\\to c}\\frac{(x-c)\\,p_1(x)}{(x-c)\\,q_1(x)}"
                "=\\lim_{x\\to c}\\frac{p_1(x)}{q_1(x)}\\]"
            )
            + warning(
                "<p>Canceling \\((x-c)\\) creates a <em>removable hole</em> at \\(x=c\\); the limit uses the "
                "simplified function, not the original value at \\(c\\).</p>"
            ),
        ),
        path_phase="Why It Works",
    )

    s.add(
        "Example · factor x (notes #3)",
        worked_example(
            "\\(\\displaystyle\\lim_{x\\to 0}\\dfrac{4x^2-15x}{x}\\)",
            "Direct sub gives \\(\\tfrac{0}{0}\\). Factor \\(x\\) from the numerator.",
            "Cancel \\(x\\) for \\(x\\neq 0\\), then substitute.",
            solution_steps([
                "\\(\\dfrac{4x^2-15x}{x}=\\dfrac{x(4x-15)}{x}=4x-15\\) for \\(x\\neq 0\\).",
                "\\(\\displaystyle\\lim_{x\\to 0}(4x-15)=-15\\).",
            ]),
            "\\(-15\\)",
            "Always state what you canceled.",
            collapsible_model=True,
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · linear factor in denominator (notes #4)",
        worked_example(
            "\\(\\displaystyle\\lim_{x\\to -7}\\dfrac{x^2-49}{x+7}\\)",
            "Substitution at \\(x=-7\\) gives \\(\\tfrac{0}{0}\\). Factor the numerator.",
            "Difference of squares.",
            solution_steps([
                "\\(x^2-49=(x-7)(x+7)\\).",
                "Cancel \\((x+7)\\): remaining expression \\(x-7\\).",
                "\\(\\displaystyle\\lim_{x\\to -7}(x-7)=-7-7=\\mathbf{-14}\\).",
            ]),
            "\\(-14\\)",
            "Same template as practice #10 with a different center.",
            collapsible_model=True,
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · practice #3",
        worked_example(
            "\\(\\displaystyle\\lim_{x\\to 1}\\dfrac{x^2-5x}{x-1}\\)",
            "Numerator \\(1-5=-4\\), denominator \\(0\\) → not merely \\(\\tfrac{0}{0}\\); the factor \\((x-1)\\) is not in the numerator.",
            "After checking factors, use simplified behavior near \\(1\\).",
            solution_steps([
                "Near \\(x=1\\), \\(x^2-5x\\to -4\\) while \\(x-1\\to 0^{\\pm}\\).",
                "Magnitude blows up with opposite signs left vs right.",
                "\\(\\displaystyle\\lim_{x\\to 1}\\dfrac{x^2-5x}{x-1}\\) <strong>does not exist</strong> (infinite behavior).",
            ]),
            "DNE (infinite)",
            "Contrast with true \\(\\tfrac{0}{0}\\) cases where a common factor exists.",
            collapsible_model=True,
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · practice #4 style",
        worked_example(
            "\\(\\displaystyle\\lim_{x\\to 1}\\dfrac{x^2+5x-6}{x-1}\\)",
            "True \\(\\tfrac{0}{0}\\) — factor the numerator.",
            "Find two numbers that multiply to \\(-6\\) and add to \\(5\\): \\(6\\) and \\(-1\\).",
            solution_steps([
                "\\(x^2+5x-6=(x+6)(x-1)\\).",
                "Cancel \\((x-1)\\): limit \\(\\displaystyle\\lim_{x\\to 1}(x+6)=7\\).",
            ]),
            "\\(7\\)",
            "Adapted from your practice sheet #4 (same factor-and-cancel move).",
            collapsible_model=True,
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · rational at x = 8 (practice #10)",
        worked_example(
            "\\(\\displaystyle\\lim_{x\\to 8}\\dfrac{x^2-64}{x-8}\\)",
            "Difference of squares in the numerator.",
            "Cancel \\((x-8)\\), then substitute \\(x=8\\).",
            solution_steps([
                "\\(x^2-64=(x-8)(x+8)\\).",
                "Cancel \\((x-8)\\): limit \\(\\displaystyle\\lim_{x\\to 8}(x+8)=16\\).",
            ]),
            "\\(16\\)",
            "Classic factor-and-cancel template.",
            collapsible_model=True,
        ),
        path_phase="Guided Example",
    )

    s.add(
        "When cancellation fails (notes #5)",
        phase_divider("Contrast / Error Analysis", "Limit does not exist")
        + role("Contrast", "Non-removable", "After factoring, a zero denominator can still remain.")
        + guided_example(
            "<p><strong>Notes #5 pattern:</strong> \\(\\displaystyle\\lim_{x\\to -6}\\dfrac{x^2+11x+30}{x+6}\\).</p>",
            [
                "Factor: \\(x^2+11x+30=(x+5)(x+6)\\).",
                "Cancel \\((x+6)\\): limit \\(\\displaystyle\\lim_{x\\to -6}(x+5)=-1\\).",
                "If cancellation leaves denominator \\(0\\) with nonzero numerator → <strong>DNE</strong>.",
            ],
            math_block("\\[\\displaystyle\\lim_{x\\to -6}\\dfrac{x^2+11x+30}{x+6}=-1\\]")
            + warning(
                "<p><strong>Mistake:</strong> assuming every rational \\(\\tfrac{0}{0}\\) blows up. "
                "Some factor to a finite number.</p>"
            ),
        ),
        path_phase="Contrast / Error Analysis",
    )

    s.add(
        "Special trigonometric limits",
        phase_divider("AP Connection", "Near \\(x=0\\)")
        + definition(
            "Two limits to memorize",
            math_block(
                "\\[\\displaystyle\\lim_{x\\to 0}\\frac{\\sin x}{x}=1"
                "\\qquad"
                "\\displaystyle\\lim_{x\\to 0}\\frac{1-\\cos x}{x}=0\\]"
            )
            + key_point(
                "Equivalents",
                "<p>\\(\\displaystyle\\lim_{x\\to 0}\\frac{x}{\\sin x}=1\\) and "
                "\\(\\displaystyle\\lim_{x\\to 0}\\frac{\\cos x-1}{x}=0\\) are the same facts with sign flips.</p>",
            ),
        )
        + fig(
            g["sin_over_x_16"],
            "Graph of \\(\\dfrac{\\sin x}{x}\\)",
            cls="ap-fig--teach",
            notice="Open circle at the origin; branches approach height \\(1\\).",
        ),
        path_phase="AP Connection",
    )

    s.add(
        "Example · sin(3x)/x (notes #6)",
        worked_example(
            "\\(\\displaystyle\\lim_{x\\to 0}\\dfrac{\\sin(3x)}{x}\\)",
            "Create \\(\\dfrac{\\sin(3x)}{3x}\\) to use the standard limit.",
            "Multiply by \\(3/3\\) to match \\(\\sin u/u\\).",
            solution_steps([
                "Rewrite: \\(\\dfrac{\\sin(3x)}{x}=3\\cdot\\dfrac{\\sin(3x)}{3x}\\).",
                "As \\(x\\to 0\\), \\(3x\\to 0\\) so \\(\\dfrac{\\sin(3x)}{3x}\\to 1\\).",
                "Limit \\(=3\\cdot 1=\\mathbf{3}\\).",
            ]),
            "\\(3\\)",
            "Scale factor stays outside the sine ratio.",
            collapsible_model=True,
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · sin(7x)/sin(9x) (notes #7)",
        worked_example(
            "\\(\\displaystyle\\lim_{x\\to 0}\\dfrac{\\sin(7x)}{\\sin(9x)}\\)",
            "Divide numerator and denominator by \\(x\\).",
            "Rewrite as a ratio of two \\(\\sin(kx)/(kx)\\) limits.",
            solution_steps([
                "\\(\\dfrac{\\sin(7x)}{\\sin(9x)}="
                "\\dfrac{\\sin(7x)/(7x)}{\\sin(9x)/(9x)}\\cdot\\dfrac{7}{9}\\).",
                "Each sine ratio \\(\\to 1\\).",
                "Limit \\(=\\dfrac{7}{9}\\).",
            ]),
            "\\(\\dfrac{7}{9}\\)",
            "Works for any nonzero constants \\(a,b\\): \\(\\displaystyle\\lim_{x\\to 0}\\frac{\\sin(ax)}{\\sin(bx)}=\\frac{a}{b}\\).",
            collapsible_model=True,
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Example · cos identity (notes #8)",
        worked_example(
            "\\(\\displaystyle\\lim_{x\\to 0}\\dfrac{\\cos^2 x-1}{x(\\cos x+4)}\\)",
            "Use \\(\\cos^2 x-1=-\\sin^2 x\\).",
            "Convert to \\(\\sin x/x\\) factors, then let \\(x\\to 0\\).",
            solution_steps([
                "Numerator \\(-\\sin^2 x = -x^2\\cdot\\bigl(\\tfrac{\\sin x}{x}\\bigr)^2\\).",
                "Expression \\(\\approx \\dfrac{-x^2}{x(\\cos x+4)}=\\dfrac{-x}{\\cos x+4}\\cdot\\dfrac{\\sin^2 x}{x^2}\\).",
                "As \\(x\\to 0\\): \\(\\dfrac{\\sin^2 x}{x^2}\\to 1\\), \\(\\dfrac{-x}{\\cos x+4}\\to 0\\).",
                "Limit \\(=\\mathbf{0}\\).",
            ]),
            "\\(0\\)",
            "Pythagorean identity is the standard move when you see \\(\\cos^2 x-1\\).",
            collapsible_model=True,
        ),
        path_phase="Guided Example",
    )

    s.add(
        "Trig practice pair",
        guided_example(
            "<p><strong>Practice #5–6</strong></p>",
            [
                "\\(\\displaystyle\\lim_{x\\to 0}\\dfrac{3x}{\\sin x}=3\\cdot\\dfrac{x}{\\sin x}\\to 3\\).",
                "\\(\\displaystyle\\lim_{x\\to 0}\\dfrac{\\sin(2x)}{3x}=\\dfrac{2}{3}\\cdot\\dfrac{\\sin(2x)}{2x}\\to \\dfrac{2}{3}\\).",
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
        "Mixed · practice #21–22",
        phase_divider("Worked Example", "Factor after rearranging")
        + worked_example(
            "\\(\\displaystyle\\lim_{x\\to 2}\\dfrac{x^2+6x-16}{2-x}\\)",
            "Denominator \\(2-x=-(x-2)\\); factor numerator by \\((x-2)\\).",
            "Factor, cancel, and watch the sign on \\(2-x\\).",
            solution_steps([
                "\\(x^2+6x-16=(x-2)(x+8)\\).",
                "\\(\\dfrac{(x-2)(x+8)}{2-x}=\\dfrac{(x-2)(x+8)}{-(x-2)}=-(x+8)\\) for \\(x\\neq 2\\).",
                "Limit \\(=-(2+8)=\\mathbf{-10}\\).",
            ]),
            "\\(-10\\)",
            "Flip the linear denominator factor first.",
            collapsible_model=True,
        )
        + worked_example(
            "\\(\\displaystyle\\lim_{x\\to 5}\\dfrac{2x^2-17x+35}{5-x}\\)",
            "Factor numerator; note \\(5-x=-(x-5)\\).",
            "Same sign-flip pattern as practice #21.",
            solution_steps([
                "\\(2x^2-17x+35=(2x-7)(x-5)\\).",
                "Cancel \\((x-5)\\) with sign: \\(\\dfrac{(2x-7)(x-5)}{5-x}=-(2x-7)\\).",
                "Limit \\(=-(10-7)=\\mathbf{-3}\\).",
            ]),
            "\\(-3\\)",
            "Same template as #21 with different roots.",
            collapsible_model=True,
        ),
        path_phase="Worked Example",
    )

    s.add(
        "Mixed · evaluate at π and nested trig",
        guided_example(
            "<p><strong>Practice #19–20, #23</strong></p>",
            [
                "\\(\\displaystyle\\lim_{x\\to \\pi}\\cos x=\\cos\\pi=\\mathbf{-1}\\) (direct).",
                "\\(\\displaystyle\\lim_{x\\to 0}\\sin(4x)=0\\) (direct continuity).",
                "\\(\\displaystyle\\lim_{x\\to 0}\\dfrac{(1-\\cos^2 x)\\sin x}{x^2}=\\lim\\dfrac{\\sin^3 x}{x^2}"
                "=\\lim \\dfrac{\\sin x}{x}\\cdot\\sin^2 x = 0\\).",
            ],
            checkpoint("Use \\(\\sin^2 x+\\cos^2 x=1\\) to rewrite before applying \\(\\sin x/x\\)."),
        ),
        path_phase="Worked Example",
    )

    s.add(
        "Practice MCQ · ln limit",
        mcq_reveal(
            "<p>Evaluate \\(\\displaystyle\\lim_{x\\to 1}\\dfrac{\\ln x}{3x}\\).</p>",
            ["\\(0\\)", "\\(\\dfrac{3}{e}\\)", "\\(e\\)", "\\(3\\)", "The limit does not exist"],
            "A",
            "ln 1 = 0",
            "<p><strong>A</strong> — numerator \\(\\to 0\\), denominator \\(\\to 3\\). (Test Prep #24)</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Practice MCQ · perfect square factor",
        mcq_reveal(
            "<p>\\(\\displaystyle\\lim_{x\\to a}\\dfrac{x^2-2ax+a^2}{x-a}=\\) ?</p>",
            ["\\(-\\infty\\)", "\\(a\\)", "\\(0\\)", "\\(\\infty\\)", "The limit does not exist"],
            "C",
            "Numerator is (x-a)^2",
            "<p><strong>C</strong> — \\(x^2-2ax+a^2=(x-a)^2\\). Cancel one \\((x-a)\\); remaining factor \\((x-a)\\to 0\\). "
            "(Test Prep #26)</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Practice MCQ · trig rational",
        mcq_reveal(
            "<p>\\(\\displaystyle\\lim_{x\\to 0}\\dfrac{4\\sin x\\cos x-\\sin x}{x^2}\\) is</p>",
            ["\\(2\\)", "\\(\\dfrac{40}{3}\\)", "\\(\\infty\\)", "\\(0\\)", "undefined"],
            "D",
            "Factor sin x; use sin x ~ x and 1-cos x ~ x^2/2",
            "<p><strong>D</strong> — \\(\\sin x(4\\cos x-1)/x^2\\to 1\\cdot(-1)/x\\to 0\\) from the standard small-angle behavior. "
            "(Test Prep #25)</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Practice MCQ · bracketed rational",
        mcq_reveal(
            "<p>\\(\\displaystyle\\lim_{x\\to 0}\\left(\\dfrac{3x^2+5\\cos x-5}{2x}\\right)=\\) ?</p>",
            ["\\(0\\)", "\\(\\dfrac{5}{2}\\)", "\\(3\\)", "\\(4\\)", "Does not exist"],
            "A",
            "cos part → 0, x part → 0",
            "<p><strong>A</strong> — numerator \\(\\to 0\\), denominator \\(\\to 0\\); expand \\(\\cos x\\approx 1-\\tfrac{x^2}{2}\\) "
            "or factor numerically → limit \\(0\\). (Test Prep #27)</p>",
        ),
        kind="question",
        group="practice",
        path_phase="AP Practice",
    )

    s.add(
        "Exit ticket · 1.6",
        exit_ticket([
            (
                "Name three limit strategies from this section.",
                "<p><strong>Direct substitution</strong>, <strong>factor & cancel</strong>, "
                "<strong>special trig limits</strong> (plus rewrite/conjugate when needed).</p>",
            ),
            (
                "\\(\\displaystyle\\lim_{x\\to 0}\\dfrac{\\sin(5x)}{x}=\\) ?",
                "<p>\\(5\\cdot\\dfrac{\\sin(5x)}{5x}\\to 5\\).</p>",
            ),
            (
                "\\(\\displaystyle\\lim_{x\\to 4}\\dfrac{x^2-16}{x-4}=\\) ?",
                "<p>Factor: \\((x-4)(x+4)/(x-4)\\to 8\\).</p>",
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
