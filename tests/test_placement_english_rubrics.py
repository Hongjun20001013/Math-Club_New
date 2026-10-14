import unittest

from placement_english_rubrics import writing_rubric_for, writing_score_band
from placement_english_ui import clean_essay_body_for_display, english_writing_max_points


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

    def test_clean_essay_body(self) -> None:
        raw = "[Option A]\n\nOption A · Personal experience\n\nMy real essay starts here."
        cleaned = clean_essay_body_for_display(raw, "A")
        self.assertIn("My real essay", cleaned)
        self.assertNotIn("Personal experience Everyone", cleaned)


if __name__ == "__main__":
    unittest.main()
