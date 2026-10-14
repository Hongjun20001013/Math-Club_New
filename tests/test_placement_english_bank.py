"""English placement banks load with passage-split metadata."""

import json
import unittest
from pathlib import Path

from placement_english_ui import pack_english_writing_answer, unpack_english_writing_answer

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "data" / "question_bank.json"


class PlacementEnglishBankTests(unittest.TestCase):
    def test_g7_8_bank(self) -> None:
        bank = json.loads(BANK.read_text(encoding="utf-8"))
        qs = bank["placement"]["english_g7_8"]
        self.assertEqual(len(qs), 32)
        self.assertEqual(qs[-1]["question_kind"], "english_writing")
        mcqs = [q for q in qs if q.get("question_kind") == "mcq"]
        self.assertTrue(all(q.get("english_passage_html") for q in mcqs))
        self.assertEqual(qs[0]["correct_answer"], "A")
        self.assertEqual(qs[8]["placement_section"], "reading")
        self.assertEqual(qs[9]["placement_section"], "language")

    def test_english_writing_answer_pack(self) -> None:
        packed = pack_english_writing_answer("B", "Hello world essay.")
        self.assertIn("[Option B]", packed)
        opt, body = unpack_english_writing_answer(packed)
        self.assertEqual(opt, "B")
        self.assertEqual(body, "Hello world essay.")

    def test_g9_11_bank(self) -> None:
        bank = json.loads(BANK.read_text(encoding="utf-8"))
        qs = bank["placement"]["english_g9_11"]
        self.assertEqual(len(qs), 41)
        self.assertEqual(qs[-1]["question_kind"], "english_writing")
        self.assertEqual(qs[11]["placement_section"], "reading")
        self.assertEqual(qs[12]["placement_section"], "language")


if __name__ == "__main__":
    unittest.main()
