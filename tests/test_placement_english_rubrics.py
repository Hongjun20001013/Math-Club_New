import unittest

from placement_english_rubrics import writing_rubric_for, writing_score_band
from placement_english_ui import (
    clean_essay_body_for_display,
    english_writing_answer_is_incomplete,
    essay_body_for_advisor_display,
    english_writing_max_points,
    filter_writing_prompt_for_review,
)


class TestPlacementEnglishRubrics(unittest.TestCase):
    def test_g7_option_a_criteria_total_20(self) -> None:
        rub = writing_rubric_for("english_g7_8", "A")
        total = sum(int(c["max_points"]) for c in rub["criteria"])
        self.assertEqual(total, 20)

    def test_g9_argument_total_20(self) -> None:
        rub = writing_rubric_for("english_g9_11", "A")
        total = sum(int(c["max_points"]) for c in rub["criteria"])
        self.assertEqual(total, 20)
        self.assertEqual(english_writing_max_points("english_g9_11"), 20)

    def test_score_bands(self) -> None:
        self.assertEqual(writing_score_band(18)["range"], "17–20")
        self.assertEqual(writing_score_band(14)["range"], "13–16")

    def test_filter_prompt_option(self) -> None:
        html = (
            '<div><p class="np-en-writing-prompt__lead">Choose one</p>'
            '<article class="np-en-writing-option"><h3>Option A · Personal</h3><p>A text</p></article>'
            '<article class="np-en-writing-option"><h3>Option B · Argument</h3><p>B text</p></article></div>'
        )
        out = filter_writing_prompt_for_review(html, "A")
        self.assertIn("Option A", out)
        self.assertNotIn("Option B", out)
        self.assertNotIn("Choose one", out)

    def test_clean_essay_body(self) -> None:
        raw = "[Option A]\n\nOption A · Personal experience\n\nMy real essay starts here."
        cleaned = clean_essay_body_for_display(raw, "A")
        self.assertIn("My real essay", cleaned)
        self.assertNotIn("Personal experience Everyone", cleaned)

    def test_incomplete_writing_answer(self) -> None:
        self.assertTrue(english_writing_answer_is_incomplete("[Option A]\n"))
        self.assertFalse(
            english_writing_answer_is_incomplete(
                "[Option A]\n\nI wrote several sentences about my challenge and what I learned."
            )
        )

    def test_advisor_display_falls_back_to_raw(self) -> None:
        body = "Personal experience"
        shown = essay_body_for_advisor_display(body, "A")
        self.assertEqual(shown, "Personal experience")


if __name__ == "__main__":
    unittest.main()
