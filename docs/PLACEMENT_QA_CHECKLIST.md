# Placement QA checklist (internal)

Run before major placement releases.

## Automated

```bash
.venv/bin/python scripts/audit_placement_grading.py
.venv/bin/python -m unittest tests.test_placement_advisor_walkthrough tests.test_placement_public_access.TestLockAndAdmin.test_english_writing_draft_promoted_on_finish -v
```

## One student + one advisor (manual)

1. **Student (no login):** `/placement` → English G7–8 → profile → save recovery code → answer a few MCQ → writing essay → **Submit test**.
2. **Advisor (login):** Admin → Placement testers → open student → confirm essay text on report and last item → grade writing rubric → download `report.pdf`.
3. **Student (math):** Enhanced Math I → answer 2 MCQ → Submit test (paper upload optional for smoke).
4. **Advisor:** Math filter → open student → item review shows saved letters.

## User-facing tutorial

- Web: `/guide/placement`
- PDF: `/placement/user-guide.pdf` (rebuild: `.venv/bin/python scripts/build_placement_user_guide_pdf.py`)
