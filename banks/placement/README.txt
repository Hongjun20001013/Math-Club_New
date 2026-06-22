Course placement diagnostics (multi-track)
------------------------------------------
The placement hub lives at **/placement** (`data/placement_catalog.json`). Each available test has its own slug, LaTeX source, PDF, and meta JSON.

**Available now**
- **Middle school** — `Placement_Middle_Level.tex` (100 CR items, topic `middle_level`, slug `middle-level`)
  - Five 20-question bands: Math 5 → Math 6 → Math 7 → Math 8 → Algebra 1/2
  - Meta: `data/placement_middle_level_meta.json`
- **Enhanced Math 1 / Math I** — `Placement_Enhanced_Math_1.tex` (65 online items; slug `enhanced-math-1`)
- **Enhanced Math 2 / Math II** — `Placement_Enhanced_Math_2.tex` (69 online items; slug `enhanced-math-2`)
- **Upper school** — `Placement_Test.tex` (85 MCQ, Five-Gate Hybrid; slug `upper-algebra-precalc`)

Build steps
1. Edit the relevant `.tex` at repo root (source of truth).
2. Run `bash scripts/build_placement_pdfs.sh` to compile all blank-test PDFs.
3. Run `python3 scripts/build_question_bank.py` to refresh `data/question_bank.json`.

URLs
- Catalog: `/placement`
- Middle level: `/placement/middle-level`
- Legacy `/placement/start` redirects to upper-school test.
