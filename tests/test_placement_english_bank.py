"""English placement banks load with passage-split metadata."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "data" / "question_bank.json"


class PlacementEnglishBankTests(unittest.TestCase):
    def test_g7_8_bank(self) -> None:
        bank = json.loads(BANK.read_text(encoding="utf-8"))
        qs = bank["placement"]["english_g7_8"]
        self.assertEqual(len(qs), 31)
        self.assertTrue(all(q.get("english_passage_html") for q in qs))
        self.assertEqual(qs[0]["correct_answer"], "A")
        self.assertEqual(qs[8]["placement_section"], "reading")
        self.assertEqual(qs[9]["placement_section"], "language")

    def test_g9_11_bank(self) -> None:
        bank = json.loads(BANK.read_text(encoding="utf-8"))
        qs = bank["placement"]["english_g9_11"]
        self.assertEqual(len(qs), 40)
        self.assertEqual(qs[11]["placement_section"], "reading")
        self.assertEqual(qs[12]["placement_section"], "language")


if __name__ == "__main__":
    unittest.main()
