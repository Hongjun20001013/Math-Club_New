"""Placement item-level acceptance: keys, figures, FR grading, preview isolation."""
from __future__ import annotations

import json
import math
import os
import re
import sys
import unittest
from math import comb, perm
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from answer_grader import (  # noqa: E402
    is_placement_graphing_item,
    is_placement_paper_item,
    placement_auto_score_breakdown,
    placement_result_status,
    response_is_correct,
)

BANK = os.path.join(ROOT, "data", "question_bank.json")
Q27_SVG = os.path.join(ROOT, "static", "placement", "upper_q27_circle_chords.svg")
COUNTS = {
    "middle_level": 100,
    "enhanced_math_1": 65,
    "enhanced_math_2": 69,
    "placement_full": 85,
}


def _bank():
    with open(BANK, encoding="utf-8") as f:
        return json.load(f)


class TestEM2Q67(unittest.TestCase):
    def test_10_1_correct_10_0_wrong_equivalents(self):
        q = _bank()["placement"]["enhanced_math_2"][66]
        self.assertTrue(response_is_correct(q, "10.1"))
        self.assertTrue(response_is_correct(q, "10.07"))
        self.assertTrue(response_is_correct(q, "10.073"))
        self.assertTrue(response_is_correct(q, "10.0731"))
        self.assertFalse(response_is_correct(q, "10.0"))
        self.assertTrue(response_is_correct(q, "60.2"))


class TestUpperQ59(unittest.TestCase):
    def test_unique_choices_only_a_correct(self):
        q = _bank()["placement"]["placement_full"][58]
        choices = q["choices"]
        self.assertEqual(len(choices), 5)
        texts = [re.sub(r"\s+", "", str(c)) for c in choices]
        self.assertEqual(len(set(texts)), 5, texts)
        self.assertEqual(q["correct_answer"], "A")
        self.assertIn(r"(-\infty,-1)", choices[2])
        self.assertIn(r"[2,\infty)", choices[2])
        self.assertNotIn(r"setminus", choices[2])
        for letter, choice in zip("ABCDE", choices):
            ok = response_is_correct(q, letter)
            if letter == "A":
                self.assertTrue(ok, choice)
            else:
                self.assertFalse(ok, choice)


class TestUpperQ27Figure(unittest.TestCase):
    def test_svg_resource_and_intersecting_chords(self):
        self.assertTrue(os.path.isfile(Q27_SVG))
        svg = Path(Q27_SVG).read_text(encoding="utf-8")
        self.assertIn('id="circle-o"', svg)
        self.assertIn('id="chord-ac"', svg)
        self.assertIn('id="chord-be"', svg)
        self.assertIn('id="right-angle-d"', svg)
        for label in ("label-a", "label-b", "label-c", "label-d", "label-e"):
            self.assertIn(f'id="{label}"', svg)
        ac = re.search(
            r'id="chord-ac" x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)"',
            svg,
        )
        be = re.search(
            r'id="chord-be" x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)"',
            svg,
        )
        self.assertIsNotNone(ac)
        self.assertIsNotNone(be)
        ax1, ay1, ax2, ay2 = map(float, ac.groups())
        bx1, by1, bx2, by2 = map(float, be.groups())
        self.assertAlmostEqual(ay1, ay2, places=2)
        self.assertAlmostEqual(bx1, bx2, places=2)
        self.assertAlmostEqual(bx1, 102.0, places=1)
        self.assertAlmostEqual(ay1, 186.2, places=1)
        stem = _bank()["placement"]["placement_full"][26]["stem"]
        self.assertIn("chord-ac", stem)
        self.assertIn("chord-be", stem)
        self.assertIsNone(re.search(r"<line[^>]*\sy=", stem))


class TestMiddleLevelText(unittest.TestCase):
    def test_q21_cherries_449(self):
        q = _bank()["placement"]["middle_level"][20]
        self.assertIn("1347 cherries", q["stem"])
        self.assertTrue(response_is_correct(q, "449"))
        self.assertFalse(response_is_correct(q, "1347"))
        stem = _bank()["placement"]["middle_level"][84]["stem"]
        self.assertIn("120 blue frogs", stem)
        self.assertNotIn("fogs", stem)

    def test_q92_equivalents(self):
        q = _bank()["placement"]["middle_level"][91]
        for ans in ("2602 1/7", "18215/7", "2602.142857", "2602.14"):
            self.assertTrue(response_is_correct(q, ans), ans)
        self.assertFalse(response_is_correct(q, "2600"))

    def test_q99_scientific_hint(self):
        stem = _bank()["placement"]["middle_level"][98]["stem"]
        self.assertIn("scientific notation", stem.lower())
        self.assertIn("coefficient", stem.lower())
        q = _bank()["placement"]["middle_level"][98]
        self.assertTrue(response_is_correct(q, "5.17e-6"))
        self.assertTrue(response_is_correct(q, "5.17 x 10^-6"))


class TestEnhancedOpenResponse(unittest.TestCase):
    def test_q55_no_solution_wording(self):
        q = _bank()["placement"]["enhanced_math_1"][54]
        self.assertTrue(response_is_correct(q, "no solution"))
        self.assertTrue(response_is_correct(q, "No solution."))
        self.assertTrue(response_is_correct(q, "no solution because the constants differ"))
        self.assertIsNone(
            response_is_correct(q, "the two sides simplify to different constants")
        )
        self.assertNotEqual(
            placement_result_status(q, None, "the two sides simplify to different constants"),
            "auto incorrect",
        )
        self.assertEqual(
            placement_result_status(q, 1, "no solution"),
            "auto correct",
        )

    def test_prose_not_auto_incorrect(self):
        q = _bank()["placement"]["enhanced_math_1"][55]
        got = response_is_correct(q, "C = 21h + 66 with slope the hourly rate")
        self.assertIsNone(got)
        self.assertEqual(
            placement_result_status(q, None, "C = 21h + 66 with slope the hourly rate"),
            "awaiting review",
        )
        self.assertEqual(
            placement_result_status(q, 1, "10.1"),
            "auto correct",
        )

    def test_graphing_unscored(self):
        q = _bank()["placement"]["enhanced_math_1"][50]
        self.assertEqual(q.get("question_kind"), "constructed_response")
        self.assertIsNone(response_is_correct(q, "graphed on the number line"))
        self.assertEqual(
            placement_result_status(q, None, "graphed on the number line"),
            "submitted",
        )
        self.assertEqual(placement_result_status(q, None, ""), "unscored")

    def test_item_counts(self):
        b = _bank()["placement"]
        self.assertEqual(len(b["middle_level"]), 100)
        self.assertEqual(len(b["enhanced_math_1"]), 65)
        self.assertEqual(len(b["enhanced_math_2"]), 69)
        self.assertEqual(len(b["placement_full"]), 85)
        self.assertEqual(sum(len(b[k]) for k in COUNTS), 319)


EXPECTED_MCQ = {
    "middle_level": 0,
    "enhanced_math_1": 50,
    "enhanced_math_2": 55,
    "placement_full": 85,
}


class TestScoredFillIns(unittest.TestCase):
    def test_item_kinds(self):
        b = _bank()["placement"]
        for topic, n in EXPECTED_MCQ.items():
            mcq = sum(1 for q in b[topic] if q.get("question_kind") in ("mcq", "mcq5"))
            paper = sum(1 for q in b[topic] if is_placement_paper_item(q))
            graph = sum(1 for q in b[topic] if is_placement_graphing_item(q))
            self.assertEqual(mcq, n, topic)
            self.assertEqual(paper, 0, topic)
            self.assertEqual(graph, 4 if topic.startswith("enhanced") else 0, topic)

    def test_keyed_frq_is_not_auto_scored_on_em2(self):
        qs = _bank()["placement"]["enhanced_math_2"]
        selected = {}
        graded = {}
        for i, q in enumerate(qs):
            if q.get("question_kind") in ("mcq", "mcq5"):
                selected[i] = q["correct_answer"]
                graded[i] = 1
        base = placement_auto_score_breakdown(qs, selected, graded, topic="enhanced_math_2")
        selected_fr = dict(selected)
        graded_fr = dict(graded)
        selected_fr[66] = "10.1"
        graded_fr[66] = 1
        scored = placement_auto_score_breakdown(
            qs, selected_fr, graded_fr, topic="enhanced_math_2"
        )
        self.assertEqual(base["mcq_total"], 55)
        self.assertEqual(scored["mcq_correct"], base["mcq_correct"])
        self.assertEqual(scored["auto_incorrect"], 0)
        self.assertEqual(scored["paper_frq_total"], 4)
        self.assertEqual(scored["fr_paper_total"], 10)
        self.assertEqual(scored["max_points"], 99)
        self.assertEqual(scored["paper_max_points"], 44)

    def test_incomplete_frq_is_not_wrong(self):
        qs = _bank()["placement"]["enhanced_math_1"]
        selected = {i: q["correct_answer"] for i, q in enumerate(qs) if q.get("question_kind") == "mcq"}
        score = placement_auto_score_breakdown(qs, selected, {i: 1 for i in selected}, topic="enhanced_math_1")
        self.assertEqual(score["mcq_total"], 50)
        self.assertEqual(score["mcq_correct"], 50)
        self.assertEqual(score["auto_incorrect"], 0)
        self.assertEqual(score["paper_frq_total"], 4)
        self.assertEqual(score["max_points"], 98)
        q = qs[54]
        self.assertEqual(placement_result_status(q, None, "", topic="enhanced_math_1"), "paper")


class TestEM1McqExactAndPaperTeacherGraded(unittest.TestCase):
    def test_fifty_mcq_keys_grade_exactly(self):
        from tests.test_placement_pdf_alignment import PDFS, extract_enhanced_pdf_mcq_keys
        from answer_grader import grade_placement_response, is_mcq_item

        qs = _bank()["placement"]["enhanced_math_1"]
        pdf_keys = extract_enhanced_pdf_mcq_keys(PDFS["enhanced_math_1"])
        self.assertEqual(len(pdf_keys), 50)
        for i, q in enumerate(qs[:50]):
            self.assertTrue(is_mcq_item(q), i)
            key = str(q["correct_answer"])
            self.assertEqual(key, pdf_keys[i + 1], i + 1)
            ok, stored = grade_placement_response(q, key, topic="enhanced_math_1")
            self.assertEqual(ok, 1, i + 1)
            self.assertEqual(stored, key)
            for letter in "ABCD":
                got, _ = grade_placement_response(q, letter, topic="enhanced_math_1")
                self.assertEqual(got, 1 if letter == key else 0, (i + 1, letter))

    def test_paper_items_are_not_auto_scored(self):
        from answer_grader import grade_placement_response, is_mcq_item

        qs = _bank()["placement"]["enhanced_math_1"]
        paper = [q for q in qs if not is_mcq_item(q)]
        self.assertEqual(len(paper), 15)
        for q in paper:
            ok, stored = grade_placement_response(q, "anything", topic="enhanced_math_1")
            self.assertIsNone(ok)
            self.assertEqual(stored, "")


class TestEM2McqExactAndPaperTeacherGraded(unittest.TestCase):
    def test_fifty_five_mcq_keys_grade_exactly(self):
        from tests.test_placement_pdf_alignment import PDFS, extract_enhanced_pdf_mcq_keys
        from answer_grader import grade_placement_response, is_mcq_item

        qs = _bank()["placement"]["enhanced_math_2"]
        pdf_keys = extract_enhanced_pdf_mcq_keys(PDFS["enhanced_math_2"])
        self.assertEqual(len(pdf_keys), 55)
        for i, q in enumerate(qs[:55]):
            self.assertTrue(is_mcq_item(q), i)
            key = str(q["correct_answer"])
            self.assertEqual(key, pdf_keys[i + 1], i + 1)
            ok, stored = grade_placement_response(q, key, topic="enhanced_math_2")
            self.assertEqual(ok, 1, i + 1)
            self.assertEqual(stored, key)
            for letter in "ABCD":
                got, _ = grade_placement_response(q, letter, topic="enhanced_math_2")
                self.assertEqual(got, 1 if letter == key else 0, (i + 1, letter))

    def test_paper_items_are_not_auto_scored(self):
        from answer_grader import grade_placement_response, is_mcq_item

        qs = _bank()["placement"]["enhanced_math_2"]
        paper = [q for q in qs if not is_mcq_item(q)]
        self.assertEqual(len(paper), 14)
        for q in paper:
            ok, stored = grade_placement_response(q, "anything", topic="enhanced_math_2")
            self.assertIsNone(ok)
            self.assertEqual(stored, "")
        score = placement_auto_score_breakdown(
            qs,
            {i: q["correct_answer"] for i, q in enumerate(qs) if is_mcq_item(q)},
            None,
            topic="enhanced_math_2",
        )
        self.assertEqual(score["mcq_total"], 55)
        self.assertEqual(score["max_points"], 99)
        q = qs[66]
        self.assertEqual(placement_result_status(q, None, "10.1", topic="enhanced_math_2"), "paper")


def _choice_integers(text: str) -> list[int]:
    return [int(tok.replace(",", "")) for tok in re.findall(r"\d[\d,]*", str(text))]


class TestUpperQ33Key(unittest.TestCase):
    """Q33 key must be A. Math is independent of the stored letter."""

    def test_independent_combinatorics(self):
        self.assertEqual(comb(11, 6), 462)
        self.assertEqual(perm(11, 6), 332640)
        self.assertEqual(462 * math.factorial(6), 332640)

    def test_choice_a_is_the_computed_pair_not_the_stored_key(self):
        q = _bank()["placement"]["placement_full"][32]
        choices = q["choices"]
        self.assertEqual(len(choices), 5)
        matching = [
            i
            for i, text in enumerate(choices)
            if _choice_integers(text)[:2] == [462, 332640]
        ]
        self.assertEqual(
            matching,
            [0],
            f"the 462; 332,640 pair must be choice A, got {choices}",
        )
        self.assertEqual(_choice_integers(choices[1])[:2], [462, 720])

    def test_correct_answer_is_a(self):
        q = _bank()["placement"]["placement_full"][32]
        self.assertEqual(q["display_number"], 33)
        self.assertEqual(q["correct_answer"], "A")

    def test_response_a_true_b_false(self):
        q = _bank()["placement"]["placement_full"][32]
        self.assertTrue(response_is_correct(q, "A"))
        self.assertFalse(response_is_correct(q, "B"))


if __name__ == "__main__":
    unittest.main()
