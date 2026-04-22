Course placement diagnostic
-----------------------------
Source of truth: **Placement_Test.tex** at the repo root (70 items with `\circnum{n}`, `\mc{...}{...}{...}{...}{...}`, or graph `enumerate` blocks). `BANKS["placement"]["placement_full"]` points to that file only — nothing is merged from SAT Unit 1 or Unit 2.

1. Calculator policy: `data/placement_meta.json` → `calculator_by_index` (1-based). Default: Q1–60 off, Q61–70 on (Part 5).

2. Answers: parsed from the Answer Key table inside the same `Placement_Test.tex` when you run `python3 scripts/build_question_bank.py`. No copying from algebra or advanced_math banks.

3. Course bands: `score_band_rubric` in `placement_meta.json` uses **raw score out of 70** (0–18 Algebra I, …, 61–70 calculus readiness). Optional `rubric` percent rows are only a fallback if bands are removed.

4. Run `python3 scripts/build_question_bank.py` after any placement `.tex` change.

5. App URL: `/placement`
