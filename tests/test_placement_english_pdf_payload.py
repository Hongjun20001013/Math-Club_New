import unittest

from placement_english_report import (
    build_english_writing_pdf_payload,
    criterion_performance_level,
)


class TestEnglishPdfPayload(unittest.TestCase):
    def test_criterion_level(self) -> None:
        self.assertEqual(criterion_performance_level(3, 4), "strong")
        self.assertEqual(criterion_performance_level(3, 6), "partial")
        self.assertEqual(criterion_performance_level(1, 4), "weak")

    def test_pdf_payload_rows(self) -> None:
        ew = {
            "max_points": 20,
            "points": 11,
            "option": "A",
            "body": "Essay text here.",
            "word_count": 50,
            "word_min": 200,
            "word_max": 300,
            "breakdown": {"focus": 1, "development": 2, "reflection": 2, "organization": 3, "language": 3},
            "rubric": {
                "title": "Option A · Personal experience",
                "criteria": [
                    {"id": "focus", "label": "Focus", "max_points": 4, "strong": "S", "partial": "P", "weak": "W"},
                ],
            },
        }
        payload = build_english_writing_pdf_payload("english_g7_8", ew, {"mcq_correct": 0, "mcq_total": 31})
        self.assertTrue(payload)
        self.assertEqual(payload["criteria_rows"][0]["points"], 1)
        self.assertEqual(payload["criteria_rows"][0]["level"], "Weak")


if __name__ == "__main__":
    unittest.main()
