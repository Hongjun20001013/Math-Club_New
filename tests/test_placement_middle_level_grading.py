"""Middle level placement entry hints and grading upgrades."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from answer_grader import (  # noqa: E402
    free_response_matches,
    placement_effective_is_correct,
    response_is_correct,
)
from placement_middle_level_hints import (  # noqa: E402
    enrich_middle_level_question,
    enrich_middle_level_questions,
    hints_for_question,
)

BANK_PATH = ROOT / "data" / "question_bank.json"


class MiddleLevelHintTests(unittest.TestCase):
    def test_q6_mixed_fraction_hint(self):
        q = {"correct_answer": "3 1/6", "stem": "Add fractions."}
        hints = hints_for_question(6, q)
        self.assertTrue(any("3 1/6" in h for h in hints["entry_hints_en"]))

    def test_q7_percent_hint(self):
        q = {"correct_answer": "75", "stem": "What percent?"}
        hints = hints_for_question(7, q)
        self.assertTrue(any("75" in h and "%" in h for h in hints["entry_hints_en"]))

    def test_q13_decimal_round_hint(self):
        q = {"correct_answer": "632 R3", "stem": "Divide."}
        hints = hints_for_question(13, q)
        self.assertIn("accept_decimal_quotient", hints)
        self.assertTrue(any("632.500" in h for h in hints["entry_hints_en"]))


class MiddleLevelGradingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(BANK_PATH, encoding="utf-8") as f:
            bank = json.load(f)
        cls.questions = enrich_middle_level_questions(
            bank["placement"]["middle_level"]
        )

    def test_q13_decimal_accepted(self):
        q = self.questions[12]
        self.assertTrue(response_is_correct(q, "632.500"))
        self.assertTrue(response_is_correct(q, "632 R3"))
        self.assertFalse(response_is_correct(q, "632"))

    def test_q30_five_decimal_places(self):
        q = self.questions[29]
        self.assertTrue(response_is_correct(q, "607.83333"))
        self.assertTrue(response_is_correct(q, "607 R5"))

    def test_q4_time_without_pm(self):
        q = self.questions[3]
        self.assertTrue(response_is_correct(q, "2:15"))
        self.assertTrue(response_is_correct(q, "2:15 PM"))

    def test_q7_percent_without_symbol(self):
        q = self.questions[6]
        self.assertTrue(response_is_correct(q, "75"))
        self.assertTrue(response_is_correct(q, "75%"))

    def test_q21_units_stripped(self):
        q = self.questions[20]
        self.assertTrue(response_is_correct(q, "449"))
        self.assertTrue(response_is_correct(q, "449 cherries"))


class SupervisorOverrideTests(unittest.TestCase):
    def test_effective_prefers_supervisor(self):
        self.assertEqual(placement_effective_is_correct(0, 1), 1)
        self.assertEqual(placement_effective_is_correct(1, 0), 0)
        self.assertEqual(placement_effective_is_correct(1, None), 1)


if __name__ == "__main__":
    unittest.main()
