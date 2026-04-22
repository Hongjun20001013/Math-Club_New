#!/usr/bin/env python3
"""
One-off helper: packs RAW walkthrough strings into data/unit1_explanations_en.json.

IMPORTANT: Keys are global display_number values from data/unit1_question_manifest.json
(matching data/question_bank.json "unit_1_all" order). If TeX slices are reordered or
questions are inserted/removed, every RAW row must be re-verified against the live stem
for that display_number — otherwise students see the wrong walkthrough (see repo history).

Until walkthroughs are re-authored against the current manifest, keep OUT as {} and rely
on the default coach HTML from scripts/build_question_bank.py.
"""

# (display_number, explanation). Use \\n in strings for line breaks (displayed with pre-wrap).
RAW: list[tuple[int, str]] = [
    (
        1,
        "Step 1: Find how much corn was removed in the first 5 hours: 24,000 − 19,350 = 4,650 bushels.\n"
        "Step 2: Removal rate = 4,650 ÷ 5 = 930 bushels per hour.\n"
        "Step 3: To reach 12,840 bushels left, Hector must remove 24,000 − 12,840 = 11,160 bushels in total.\n"
        "Step 4: Total hours at this rate = 11,160 ÷ 930 = 12. Choice D.",
    ),
    (
        2,
        "Step 1: Current weekly gas use = 100 miles ÷ 25 mpg = 4 gallons. Cost = 4 × $4 = $16.\n"
        "Step 2: Alan wants to spend $5 less on gas, so target weekly cost is $11 → target gallons = 11 ÷ 4 = 11/4 gallons.\n"
        "Step 3: Miles he should drive at 25 mpg = (11/4) × 25 = 275/4. Miles to cut m = 100 − 275/4 = 125/4.\n"
        "Step 4: Dollars saved from cutting m miles: m miles saves m/25 gallons, worth 4·(m/25) = (4/25)m dollars. Set (4/25)m = 5 → choice D.",
    ),
    (
        3,
        "Step 1: Expand both sides: 10(15x − 9) = 150x − 90.\n"
        "Step 2: Right side: −15(6 − 10x) = −90 + 150x.\n"
        "Step 3: Both sides simplify to 150x − 90, so the equation is true for every x.\n"
        "Step 4: Infinitely many solutions → C.",
    ),
    (
        4,
        "Step 1: Sales price = $100. Commission = 20% of 100 = $20. Cost to make = $65.\n"
        "Step 2: Profit per unit = 100 − 65 − 20 = $15 (price minus manufacturing minus commission).\n"
        "Step 3: Total profit $6,840 from u units → 15u = 6,840.\n"
        "Step 4: That matches (100(1 − 0.2) − 65)u = (80 − 65)u = 15u. Choice A.",
    ),
    (
        5,
        "Step 1: Let x = original price. 40% discount → pay 0.6x, then 20% off that → pay 0.8(0.6x) = 0.48x.\n"
        "Step 2: That final price is the purchase price $140,000: 0.48x = 140,000.\n"
        "Step 3: x = 140,000 ÷ 0.48 ≈ 291,666.67, closest to $291,700.\n"
        "Step 4: Answer B.",
    ),
    (
        6,
        "Step 1: Count sides: 5n sides of length 8 cm, n sides of length 3 cm, and 6 sides of length 4 cm.\n"
        "Step 2: Total sides = 30 → 5n + n + 6 = 30 → 6n + 6 = 30.\n"
        "Step 3: That is choice B (not 5n + 6, which would ignore the n threes).",
    ),
    (
        7,
        "Step 1: Factor x: x(−3 + 21p) = 84.\n"
        "Step 2: “No solution” for a linear equation in x means the x-coefficient is 0 but the constant side is not 0.\n"
        "Step 3: Set −3 + 21p = 0 → p = 3/21 = 1/7. Then left side is 0·x = 0, but right side is 84 — impossible.\n"
        "Step 4: So p = 1/7 gives no solution → B.",
    ),
    (
        8,
        "Step 1: Cross-multiply (or multiply both sides by 39): 13(x+6) = 3(x+6) → 13(x+6) − 3(x+6) = 0 → 10(x+6)=0.\n"
        "Step 2: So x + 6 = 0, meaning x = −6.\n"
        "Step 3: Then x + 6 equals exactly 0, which lies strictly between −2 and 2.\n"
        "Step 4: Choice B.",
    ),
    (
        9,
        "Step 1: Expand right: a(x+b) = ax + ab. Equation 9x + 5 = ax + ab.\n"
        "Step 2: For no solution, slopes must match (coefficient of x equal) but constants unequal → a = 9.\n"
        "Step 3: Then 9x + 5 = 9x + 9b ⇒ 5 = 9b. No solution requires this to be false, so b ≠ 5/9.\n"
        "Step 4: I (a=9) and III (b ≠ 5/9) must hold → D.",
    ),
    (
        10,
        "Step 1: x stations for A, (5 − x) for B. Salt = 6x + 4(5 − x).\n"
        "Step 2: Simplify: 6x + 20 − 4x = 2x + 20.\n"
        "Step 3: Choice C.",
    ),
    (
        11,
        "Step 1: First 2 hours cost $220. Total for 5 hours is $400, so the extra 3 hours cost 400 − 220 = $180.\n"
        "Step 2: Extra hourly rate = 180 ÷ 3 = $60 per hour after the first two.\n"
        "Step 3: For x ≥ 2 hours: cost = 220 + 60(x − 2) = 220 + 60x − 120 = 60x + 100.\n"
        "Step 4: Choice A.",
    ),
    (
        12,
        "Step 1: Linear Q = mP + b. Slope m = (15,000 − 20,000)/(60 − 40) = −5000/20 = −250 units per dollar.\n"
        "Step 2: Q − 20,000 = −250(P − 40). At P = 55: Q = 20,000 − 250(15) = 20,000 − 3,750 = 16,250.\n"
        "Step 3: Choice A.",
    ),
    (
        13,
        "Step 1: Day 1 costs $270. Each extra day adds $135.\n"
        "Step 2: For x days, there are (x − 1) extra days after the first: y = 270 + 135(x − 1).\n"
        "Step 3: Simplify: y = 270 + 135x − 135 = 135x + 135.\n"
        "Step 4: Choice D.",
    ),
    (
        14,
        "Step 1: F is linear in x with slope 9/5. A change of Δx kelvins changes Fahrenheit by (9/5)·Δx.\n"
        "Step 2: Δx = 9.10 ⇒ ΔF = (9/5)(9.10) = 1.8 × 9.10 = 16.38.\n"
        "Step 3: Choice A.",
    ),
    (
        15,
        "Step 1: F(x) = 2.74 − 0.19(x − 3) is point-slope form F − 2.74 = −0.19(x − 3).\n"
        "Step 2: So when x = 3 months after Sept 1, F = 2.74 — that date is Dec 1, 2014.\n"
        "Step 3: The constant 2.74 is the model’s price at x = 3, not at x = 0.\n"
        "Step 4: D describes Dec 1 price.",
    ),
    (
        16,
        "Step 1: Slope a = (0 − (−64))/(2 − 1) = 64.\n"
        "Step 2: f(1) = a + b = −64 ⇒ b = −64 − 64 = −128.\n"
        "Step 3: a − b = 64 − (−128) = 192.\n"
        "Step 4: Choice D.",
    ),
    (
        17,
        "Step 1: From 2000 to 2013 is 13 years; production drops from 4 to 1.9 million barrels.\n"
        "Step 2: Slope = (1.9 − 4)/13 = −2.1/13 = −21/130.\n"
        "Step 3: f(t) = 4 + (−21/130)t in millions. Choice C.",
    ),
    (
        18,
        "Step 1: One coat uses w/220 gallons; two coats use 2·(w/220) = w/110.\n"
        "Step 2: So P = w/110 → A.",
    ),
    (
        19,
        "Step 1: F(x) is linear in x with slope 9/5 (the coefficient of x after simplifying).\n"
        "Step 2: A change of Δx kelvins changes Fahrenheit by ΔF = (9/5)·Δx; the −273.15 and +32 only shift the line vertically.\n"
        "Step 3: Here Δx = 2.10, so ΔF = 1.8 × 2.10 = 3.78.\n"
        "Step 4: Choice A.",
    ),
    (
        20,
        "Step 1: From the table, when x increases by 1, f(x) decreases by 3, so slope = −3.\n"
        "Step 2: f(x) = −3x + b. Use (−10, 18): 18 = −3(−10) + b ⇒ b = −12.\n"
        "Step 3: x-intercept: 0 = −3x − 12 ⇒ x = −4. Point (−4, 0).\n"
        "Step 4: Choice B.",
    ),
    (
        21,
        "Step 1: Protein p g gives 4p calories, fat f g gives 9f, carbs c g give 4c; total 180.\n"
        "Step 2: 4p + 9f + 4c = 180.\n"
        "Step 3: Solve for f: 9f = 180 − 4p − 4c ⇒ f = 20 − (4/9)(p + c).\n"
        "Step 4: Choice B.",
    ),
    (
        22,
        "Step 1: ℓ = 30 + 2w is linear in w with slope 2.\n"
        "Step 2: Slope means “change in ℓ per 1 unit increase in w.”\n"
        "Step 3: So 2 is the extra stretch (cm) for each extra newton of weight → D.",
    ),
    (
        23,
        "Step 1: You know f(3x) = x − 6 for all x.\n"
        "Step 2: To get f(6), pick x so that 3x = 6 ⇒ x = 2.\n"
        "Step 3: f(6) = 2 − 6 = −4.\n"
        "Step 4: Choice B.",
    ),
    (
        24,
        "Step 1: For n people, if n ≥ 25, cost = 21·25 + 14·(n − 25) = 525 + 14n − 350 = 14n + 175.\n"
        "Step 2: That matches the standard piecewise form in choice A.\n"
        "Step 3: Verify at n = 25 you pay 21·25 only.",
    ),
    (
        25,
        "Step 1: Slope between (−2, −6) and (0, −3) is (−3 − (−6))/(0 − (−2)) = 3/2.\n"
        "Step 2: Line through (0, −3): y = (3/2)x − 3 ⇒ multiply by 2: 2y = 3x − 6 ⇒ 3x − 2y = 6.\n"
        "Step 3: Compare to ax + ky = 6 ⇒ k = −2.\n"
        "Step 4: Choice A.",
    ),
    (
        26,
        "Step 1: From the table, slope of h: (160 − 130)/(23 − 18) = 30/5 = 6. Using (18,130): y − 130 = 6(x − 18) ⇒ y = 6x − 108 + 130 = 6x + 22.\n"
        "Step 2: x-intercept of h: 0 = 6x + 22 ⇒ x = −11/3.\n"
        "Step 3: Translating down 5 replaces y by y + 5 in the equation of the graph, so new line k: y = 6x + 22 − 5 = 6x + 17.\n"
        "Step 4: x-intercept of k: 0 = 6x + 17 ⇒ x = −17/6. Choice D.",
    ),
    (
        27,
        "Step 1: Line g in the figure is linear; read two clear grid points on g and compute slope m = (change in y)/(change in x).\n"
        "Step 2: You should get m = −1/4 (for each 4 units to the right, the line drops 1 unit).\n"
        "Step 3: Write y = −x/4 + b and substitute one point on g to solve for b.\n"
        "Step 4: Only choice A matches both the slope −1/4 and that intercept.",
    ),
    (
        28,
        "Step 1: Equation 3x + 5y = 32: x counts small jars (3 cups each), y counts large jars (5 cups each).\n"
        "Step 2: The term 5y is cups going into all large jars together.\n"
        "Step 3: So y is the count of large jars, and 5y is total cups in large jars → C.",
    ),
    (
        29,
        "Step 1: ax + by = b ⇒ by = −ax + b ⇒ y = (−a/b)x + 1 (since b ≠ 0).\n"
        "Step 2: y-intercept is 1. Slope −a/b is negative because a, b > 0.\n"
        "Step 3: Given 0 < a < b, |a/b| < 1, so −1 < slope < 0 (gentle downward line through (0,1)).\n"
        "Step 4: Pick the graph with that behavior → C.",
    ),
    (
        30,
        "Step 1: x-intercept: set y = 0 ⇒ 7x = −31 ⇒ a = −31/7.\n"
        "Step 2: y-intercept: set x = 0 ⇒ 2y = −31 ⇒ b = −31/2.\n"
        "Step 3: b/a = (−31/2) ÷ (−31/7) = (7/2).\n"
        "Step 4: Choice D.",
    ),
    (
        31,
        "Step 1: x = 2 is a vertical line (undefined slope).\n"
        "Step 2: A line perpendicular to a vertical line is horizontal, slope 0.\n"
        "Step 3: Choice A.",
    ),
    (
        32,
        "Step 1: Write slopes: 5x+7y=1 → y = −(5/7)x + … so m₁ = −5/7. ax+by=1 → m₂ = −a/b.\n"
        "Step 2: Perpendicular lines satisfy m₁·m₂ = −1: (−5/7)(−a/b) = −1 ⇒ 5a/(7b) = −1 ⇒ 5a = −7b.\n"
        "Step 3: In choice B the lines are 10x+7y=1 (slope −10/7) and ax+2by=1 (slope −a/(2b)). Multiply: (−10/7)(−a/(2b)) = 5a/(7b), the same expression as before, so it is still −1 when 5a = −7b.\n"
        "Step 4: The other choices do not preserve that product, so B is correct.",
    ),
    (
        33,
        "Step 1: Equation 10h_A + 20h_B = s. Intercepts of the segment in the graph give two easy (h_A, h_B) pairs.\n"
        "Step 2: e.g. all time at job A: if h_B = 0 and h_A = 16, then s = 10·16 = 160; check against the other intercept (0,8) gives 20·8 = 160.\n"
        "Step 3: s = 160 → B.",
    ),
    (
        34,
        "Step 1: Identify the vertices of the shaded region where the boundary lines meet on the grid (write each as an (x, y) pair).\n"
        "Step 2: Apply the shoelace formula: list the vertices in order around the polygon, sum xᵢyᵢ₊₁ − xᵢ₊₁yᵢ, take half the absolute value.\n"
        "Step 3: Alternatively, split the region into triangles/rectangles you can area-add; both routes simplify to 24/7 square units.\n"
        "Step 4: Match 24/7 → C.",
    ),
    (
        35,
        "Step 1: k: x + y = 0 has slope −1.\n"
        "Step 2: A perpendicular line has slope +1 (negative reciprocal of −1).\n"
        "Step 3: Through (0, 3): y − 3 = 1(x − 0) ⇒ y = x + 3 ⇒ x − y = −3.\n"
        "Step 4: Choice D.",
    ),
    (
        36,
        "Step 1: Time running = r/5 hours, time biking = b/10 hours.\n"
        "Step 2: “Biked twice as many hours as ran” ⇒ b/10 = 2(r/5) ⇒ b/10 = 2r/5 ⇒ b = 4r.\n"
        "Step 3: r + b = 200 ⇒ r + 4r = 200 ⇒ r = 40, b = 160.\n"
        "Step 4: Choice D.",
    ),
    (
        37,
        "Step 1: Multiply first equation by 6: 3x + 2y = 1.\n"
        "Step 2: Second: ax + y = c. For infinitely many solutions the equations must be scalar multiples with same constants.\n"
        "Step 3: Compare y-coefficients: multiply second by 2 gives 2ax + 2y = 2c; need 2a = 3 and 2c = 1, so a = 3/2.\n"
        "Step 4: Choice D.",
    ),
    (
        38,
        "Step 1: Solve the 2×2 system (elimination). Multiply first by 4 and second by 7, or subtract judiciously.\n"
        "Step 2: Faster trick: subtract equations after scaling to isolate combinations; standard elimination yields x = −13/36, y = −47/36.\n"
        "Step 3: Then 3x + 3y = 3(x + y) = 3(−60/36) = −5.\n"
        "Step 4: Choice B.",
    ),
    (
        39,
        "Step 1: Two lines y = 2x + 1 and y = ax − 8 have the same slope when a = 2.\n"
        "Step 2: If a = 2 but intercepts differ (1 vs −8), lines are parallel and distinct → no intersection.\n"
        "Step 3: So a = 2 → D.",
    ),
    (
        40,
        "Step 1: Second equation is 3× the first, so the system is dependent (one line).\n"
        "Step 2: All solutions satisfy 8x + 7y = 9 ⇒ y = (9 − 8x)/7.\n"
        "Step 3: Point (r, −8r/7 + 9/7) lies on the line for every r → A.",
    ),
    (
        41,
        "Step 1: Let r = pints raspberries, b = pints blackberries.\n"
        "Step 2: Store A: 5.5r + 3b = 37. Store B: 6.5r + 8b = 66.\n"
        "Step 3: Subtract: (6.5r − 5.5r) + (8b − 3b) = 66 − 37 ⇒ r + 5b = 29 ⇒ r = 29 − 5b.\n"
        "Step 4: Substitute: 5.5(29 − 5b) + 3b = 37 → b = 5 → B.",
    ),
    (
        42,
        "Step 1: Rewrite first: 4x − 9y = 9y + 5 ⇒ 4x − 18y = 5.\n"
        "Step 2: Second: hy = 2 + 4x ⇒ 4x − hy = −2.\n"
        "Step 3: For no solution, left-hand sides must be parallel (same x/y ratio) but right constants differ. Compare 4x − 18y and 4x − hy ⇒ h = 18, constants 5 vs −2 → D.",
    ),
    (
        43,
        "Step 1: Given line 2x + 6y = 10 ⇔ x + 3y = 5.\n"
        "Step 2: No solution requires the other line to be parallel but not identical: same slope −1/3, different constant.\n"
        "Step 3: x + 3y = −20 works; x + 3y = 5 is the same line (infinite solutions). Choice B.",
    ),
    (
        44,
        "Step 1: Second equation is 5× the first, so one line; all points satisfy 2x + 3y = 7.\n"
        "Step 2: Parametrize with y = r: 2x = 7 − 3r ⇒ x = −3r/2 + 7/2.\n"
        "Step 3: Point (−3r/2 + 7/2, r) → B.",
    ),
    (
        45,
        "Step 1: y = 6x + 18 has slope 6 and y-intercept 18.\n"
        "Step 2: No solution means the second line must be parallel (same slope 6) but not the same line (different intercept).\n"
        "Step 3: Rewrite each choice as y = 6x + k. Choice A gives y = 6x + 18 — identical to the given line (infinitely many solutions), so discard it.\n"
        "Step 4: Choice B gives y = 6x + 22 — parallel, distinct → no intersection → B.",
    ),
    (
        46,
        "Step 1: Compare the two lines drawn: compute or read their slopes from the grid.\n"
        "Step 2: If slopes are equal but the lines are not the same, they never meet → zero solutions.\n"
        "Step 3: That matches choice A.",
    ),
    (
        47,
        "Step 1: Walking takes 20 minutes. Riding the bus takes wait w plus ride 5 minutes: total w + 5.\n"
        "Step 2: Walking is faster when w + 5 > 20? Actually faster walk when walk time < bus time: 20 < w + 5.\n"
        "Step 3: Equivalently w + 5 > 20 (bus slower than walk) — choice D.",
    ),
    (
        48,
        "Step 1: Weight constraint: 7.35d + 6.2s ≤ 300.\n"
        "Step 2: “At least twice as many detergent as softener” ⇒ d ≥ 2s (not 2d ≥ s).\n"
        "Step 3: Match that system → A.",
    ),
    (
        49,
        "Step 1: Test each point in both inequalities y ≤ x + 7 and y ≥ −2x − 1.\n"
        "Step 2: (14, 0): 0 ≤ 21 ✓; 0 ≥ −28 − 1 = −29 ✓.\n"
        "Step 3: Other listed points fail one inequality → D.",
    ),
    (
        50,
        "Step 1: Earnings = x + 0.11s.\n"
        "Step 2: Need 3x ≤ x + 0.11s ≤ 4x ⇒ subtract x: 2x ≤ 0.11s ≤ 3x.\n"
        "Step 3: Divide by 0.11: (2/0.11)x ≤ s ≤ (3/0.11)x → B.",
    ),
    (
        51,
        "Step 1: Total participants 300. “More than 20% chose first picture” means (36 + p) > 0.20·300 = 60.\n"
        "Step 2: So 36 + p > 60 ⇔ p + 36 > 60, with p ≤ 150.\n"
        "Step 3: Choice D.",
    ),
    (
        52,
        "Step 1: Triangle inequality: third side x satisfies |12 − 6| < x < 12 + 6.\n"
        "Step 2: So 6 < x < 18.\n"
        "Step 3: Choice C.",
    ),
    (
        53,
        "Step 1: For each table row, check y < 6x + 2.\n"
        "Step 2: In the correct table every listed pair satisfies the strict inequality.\n"
        "Step 3: That is table C.",
    ),
    (
        54,
        "Step 1: For each row, require y > 13x − 18.\n"
        "Step 2: Eliminate tables where any pair fails.\n"
        "Step 3: Remaining table is D.",
    ),
    (
        55,
        "Step 1: Perimeter of base = 2(length + width) = 2(2.5x + x) = 7x.\n"
        "Step 2: Constraint: perimeter of base + height ≤ 130 ⇒ 7x + 60 ≤ 130 ⇒ 7x ≤ 70 ⇒ x ≤ 10.\n"
        "Step 3: Width positive: 0 < x ≤ 10 → A.",
    ),
    (
        56,
        "Step 1: Budget includes tax: 81 · (price before tax) · 1.07 ≤ 14,000.\n"
        "Step 2: Price ≤ 14,000 / (81 × 1.07) ≈ 14,000 / 86.67 ≈ 161.53.\n"
        "Step 3: Choice B.",
    ),
    (
        57,
        "Step 1: First 10 hours pay 8·10 = $80. After that, $10/hour.\n"
        "Step 2: Let h be extra hours; gross = 80 + 10h. Saves 90% ⇒ 0.9(80 + 10h) ≥ 270.\n"
        "Step 3: 72 + 9h ≥ 270 ⇒ 9h ≥ 198 ⇒ h ≥ 22.\n"
        "Step 4: Choice C.",
    ),
    (
        58,
        "Step 1: 2x > 5 ⇒ x > 2.5.\n"
        "Step 2: y > 2x − 1. For any x > 2.5, the lower bound 2x − 1 is greater than 2(2.5) − 1 = 4.\n"
        "Step 3: Because x can be arbitrarily close to 2.5 from above, y must be greater than values arbitrarily close to 4; overall y > 4.\n"
        "Step 4: Choice B.",
    ),
]


def main() -> None:
    data = {str(k): v for k, v in RAW}
    if len(data) != 58:
        raise SystemExit(f"expected 58 explanations, got {len(data)}")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
