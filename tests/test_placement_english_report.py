import unittest

from placement_english_report import build_english_placement_report, build_english_section_stats


class TestPlacementEnglishReport(unittest.TestCase):
    def test_section_stats_three_parts(self) -> None:
        questions = [
            {"placement_section": "reading", "question_kind": "mcq"},
            {"placement_section": "language", "question_kind": "mcq"},
            {"placement_section": "writing", "question_kind": "english_writing"},
        ]
        items = [
            {"status": "correct", "question_kind": "mcq"},
            {"status": "incorrect", "question_kind": "mcq"},
            {"status": "paper", "question_kind": "english_writing"},
        ]
        stats = build_english_section_stats(
            "english_g7_8",
            questions,
            items,
            {"max_points": 20, "points": 15},
        )
        self.assertEqual(len(stats), 3)
        self.assertEqual(stats[0]["correct"], 1)
        self.assertEqual(stats[1]["correct"], 0)
        self.assertEqual(stats[2]["correct"], 15)
        self.assertTrue(stats[2]["is_writing"])

    def test_report_combined_when_graded(self) -> None:
        rec = {"title": "On-level", "headline": "Solid", "band_range": "19-26"}
        rep = build_english_placement_report(
            "english_g7_8",
            22,
            31,
            rec,
            {"max_points": 20, "points": 16},
        )
        self.assertEqual(rep["combined_points"], 38)
        self.assertEqual(rep["combined_max"], 51)


if __name__ == "__main__":
    unittest.main()
