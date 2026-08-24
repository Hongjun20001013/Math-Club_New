"""Source-alignment regression: current Placement bank vs original PDFs + git HEAD.

Original PDFs and `git show HEAD:data/question_bank.json` are read-only baselines.
The working-tree question_bank.json is never compared to itself.
Upper Q33 is not allowlisted: the original PDF key A must be restored.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import unittest
from math import comb, perm
from pathlib import Path

from pypdf import PdfReader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from answer_grader import response_is_correct  # noqa: E402
from latex_parser import parse_placement_answer_key  # noqa: E402

BANK = os.path.join(ROOT, "data", "question_bank.json")
# Last committed bank that still matches the original Placement PDFs
# on every non-allowlisted field. Pinned so later commits cannot become
# a self-baseline.
PDF_ERA_BANK_COMMIT = "367940fec6615004776a371a65de988e492e6c48"
ALLOWLIST_PATH = os.path.join(
    ROOT, "tests", "fixtures", "placement_source_alignment_allowlist.json"
)
PDFS = {
    "placement_full": os.path.join(ROOT, "Placement_Test.pdf"),
    "middle_level": os.path.join(ROOT, "Placement_Middle_Level.pdf"),
    "enhanced_math_1": os.path.join(ROOT, "Placement_Enhanced_Math_1.pdf"),
    "enhanced_math_2": os.path.join(ROOT, "Placement_Enhanced_Math_2.pdf"),
}
TEX_SOURCES = (
    os.path.join(ROOT, "Placement_Test.tex"),
    os.path.join(ROOT, "banks", "placement", "placement_test.tex"),
)
FROZEN_COUNTS = {
    "middle_level": 100,
    "enhanced_math_1": 65,
    "enhanced_math_2": 69,
    "placement_full": 85,
}
COMPARE_FIELDS = (
    "display_number",
    "question_kind",
    "stem",
    "choices",
    "correct_answer",
    "answer_alternates",
)
CHOICE_LETTERS = "ABCDE"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_current_bank() -> dict:
    with open(BANK, encoding="utf-8") as handle:
        return json.load(handle)


def load_pdf_era_bank() -> tuple[dict, bytes]:
    """Read-only original compiled bank. Never opens the working-tree JSON path."""
    raw = subprocess.check_output(
        ["git", "show", f"{PDF_ERA_BANK_COMMIT}:data/question_bank.json"],
        cwd=ROOT,
    )
    return json.loads(raw.decode("utf-8")), raw


def load_allowlist() -> dict:
    with open(ALLOWLIST_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def extract_upper_pdf_keys(path: str) -> dict[int, str]:
    reader = PdfReader(path)
    text = reader.pages[-1].extract_text() or ""
    keys = {int(n): letter for n, letter in re.findall(r"(\d+)\.\s*([A-E])\b", text)}
    return keys


def extract_enhanced_pdf_mcq_keys(path: str) -> dict[int, str]:
    reader = PdfReader(path)
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    keys: dict[int, str] = {}
    for block in re.finditer(
        r"Q\s+([\d ]+)\nAns\s+([A-D ]+)",
        text,
    ):
        nums = [int(n) for n in block.group(1).split()]
        letters = re.findall(r"[A-D]", block.group(2))
        if len(nums) != len(letters):
            raise AssertionError(
                f"PDF MCQ table misaligned in {path}: {nums} vs {letters}"
            )
        for num, letter in zip(nums, letters):
            keys[num] = letter
    return keys


def normalize_middle_pdf_key(value: str) -> str:
    text = (
        value.replace("×10−", "e-")
        .replace("×10-", "e-")
        .replace("−", "-")
        .replace("mm3", "mm^3")
        .replace("m3", "m^3")
        .replace("mi2", "mi^2")
        .replace("cm2", "cm^2")
        .replace("m2", "m^2")
        .replace("sq. in.", "sq in")
    )
    return " ".join(text.split())


def extract_middle_pdf_keys(path: str) -> dict[int, str]:
    reader = PdfReader(path)
    text = "\n".join((page.extract_text() or "") for page in reader.pages[-2:])
    keys: dict[int, str] = {}
    current_n: int | None = None
    current_parts: list[str] = []

    def flush() -> None:
        nonlocal current_n, current_parts
        if current_n is None:
            return
        keys[current_n] = " ".join(current_parts).strip()
        current_n = None
        current_parts = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("Page ") or line.startswith("Novel Prep"):
            continue
        if line == "Answer Key":
            continue
        numbered = re.match(r"^(\d+)\.\s*(.*)$", line)
        if numbered:
            flush()
            current_n = int(numbered.group(1))
            rest = numbered.group(2).strip()
            current_parts = [rest] if rest else []
            continue
        if current_n is not None and re.fullmatch(r"\d+", line):
            if current_parts:
                current_parts[-1] = f"{current_parts[-1]}/{line}"
            else:
                current_parts.append(line)
    flush()
    return keys


def extract_em2_pdf_fr8(path: str) -> str:
    reader = PdfReader(path)
    text = "\n".join((page.extract_text() or "") for page in reader.pages[-2:])
    match = re.search(r"FR8:\s*(c\s*≈\s*10\.\d)", text)
    if not match:
        raise AssertionError("EM2 PDF FR8 side-c value not found")
    return re.sub(r"\s+", "", match.group(1))


def _field(item: dict, name: str):
    if name == "answer_alternates":
        return item.get("answer_alternates")
    return item.get(name)


def _choice_index(letter: str) -> int:
    return CHOICE_LETTERS.index(letter)


def collect_diffs(baseline: dict, current: dict) -> dict[tuple[str, int, str], tuple]:
    diffs: dict[tuple[str, int, str], tuple] = {}
    for topic in FROZEN_COUNTS:
        base_qs = baseline["placement"][topic]
        cur_qs = current["placement"][topic]
        for i, (base_q, cur_q) in enumerate(zip(base_qs, cur_qs), start=1):
            for field in COMPARE_FIELDS:
                left = _field(base_q, field)
                right = _field(cur_q, field)
                if left != right:
                    diffs[(topic, i, field)] = (left, right)
    return diffs


class TestPlacementCountsFrozen(unittest.TestCase):
    def test_four_forms_and_total(self):
        current = load_current_bank()["placement"]
        baseline, _ = load_pdf_era_bank()
        for topic, n in FROZEN_COUNTS.items():
            self.assertEqual(len(current[topic]), n, topic)
            self.assertEqual(len(baseline["placement"][topic]), n, topic)
        self.assertEqual(sum(len(current[k]) for k in FROZEN_COUNTS), 319)


class TestUpperQ33NotAllowlisted(unittest.TestCase):
    def test_independent_math_and_pdf_key(self):
        self.assertEqual(comb(11, 6), 462)
        self.assertEqual(perm(11, 6), 332640)
        pdf_keys = extract_upper_pdf_keys(PDFS["placement_full"])
        self.assertEqual(pdf_keys[33], "A")

        q = load_current_bank()["placement"]["placement_full"][32]
        matching = [
            i
            for i, text in enumerate(q["choices"])
            if [int(tok.replace(",", "")) for tok in re.findall(r"\d[\d,]*", text)][:2]
            == [462, 332640]
        ]
        self.assertEqual(matching, [0])
        self.assertEqual(q["correct_answer"], "A")
        self.assertTrue(response_is_correct(q, "A"))
        self.assertFalse(response_is_correct(q, "B"))

        pdf_era, _ = load_pdf_era_bank()
        self.assertEqual(
            pdf_era["placement"]["placement_full"][32]["correct_answer"], "A"
        )

        allowlist = load_allowlist()
        forbidden = [
            entry
            for entry in allowlist["entries"]
            if entry["topic"] == "placement_full" and entry["question_number"] == 33
        ]
        self.assertEqual(forbidden, [], "Upper Q33 must not be on the allowlist")


class TestSourceAlignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current_raw = Path(BANK).read_bytes()
        cls.current = json.loads(cls.current_raw.decode("utf-8"))
        cls.baseline, cls.baseline_raw = load_pdf_era_bank()
        cls.allowlist = load_allowlist()
        cls.entries = cls.allowlist["entries"]
        cls.allowed = {
            (e["topic"], e["question_number"], e["changed_field"]): e for e in cls.entries
        }
        cls.diffs = collect_diffs(cls.baseline, cls.current)

    def test_baselines_are_not_the_working_tree_file(self):
        self.assertNotEqual(
            _sha256_bytes(self.current_raw),
            _sha256_bytes(self.baseline_raw),
            "frozen PDF-era bank unexpectedly equals working tree; refuse self-comparison",
        )
        for path in PDFS.values():
            self.assertTrue(os.path.isfile(path), path)
            self.assertTrue(os.access(path, os.R_OK))

    def test_allowlist_schema_and_q33_absent(self):
        required = {
            "topic",
            "question_number",
            "changed_field",
            "original_value",
            "current_value",
            "reason",
            "independently_verified_answer",
        }
        for entry in self.entries:
            missing = required - set(entry)
            self.assertFalse(missing, missing)
            self.assertIn(entry["topic"], FROZEN_COUNTS)
            self.assertIsInstance(entry["question_number"], int)
            self.assertTrue(str(entry["reason"]).strip())
            self.assertNotEqual(
                (entry["topic"], entry["question_number"]),
                ("placement_full", 33),
            )

    def test_no_unregistered_diffs_against_committed_baseline(self):
        unexpected = sorted(
            key for key in self.diffs if key not in self.allowed
        )
        unused = sorted(key for key in self.allowed if key not in self.diffs)
        self.assertEqual(unexpected, [], f"unregistered diffs: {unexpected}")
        self.assertEqual(unused, [], f"stale allowlist entries: {unused}")

    def test_allowlist_values_match_head_and_current(self):
        for entry in self.entries:
            topic = entry["topic"]
            n = entry["question_number"]
            field = entry["changed_field"]
            base_q = self.baseline["placement"][topic][n - 1]
            cur_q = self.current["placement"][topic][n - 1]
            if topic in ("middle_level", "placement_full"):
                self.assertEqual(base_q.get("display_number"), n)
                self.assertEqual(cur_q.get("display_number"), n)

            if field == "stem" and "original_sha256" in entry:
                self.assertEqual(_sha256_text(base_q["stem"]), entry["original_sha256"])
                self.assertEqual(_sha256_text(cur_q["stem"]), entry["current_sha256"])
                self.assertIsNotNone(re.search(r"<line[^>]*\sy=", base_q["stem"]))
                self.assertIsNone(re.search(r"<line[^>]*\sy=", cur_q["stem"]))
                self.assertIn("chord-ac", cur_q["stem"])
                continue

            if field == "choices":
                letter = entry["choice_letter"]
                idx = _choice_index(letter)
                self.assertEqual(base_q["choices"][idx], entry["original_value"])
                self.assertEqual(cur_q["choices"][idx], entry["current_value"])
                for i, (left, right) in enumerate(
                    zip(base_q["choices"], cur_q["choices"])
                ):
                    if i == idx:
                        continue
                    self.assertEqual(left, right, f"{topic} Q{n} choice {CHOICE_LETTERS[i]}")
                continue

            self.assertEqual(_field(base_q, field), entry["original_value"], (topic, n, field))
            self.assertEqual(_field(cur_q, field), entry["current_value"], (topic, n, field))

    def test_pdf_mcq_keys_match_except_allowlisted_key_changes(self):
        allow_key_changes = {
            (e["topic"], e["question_number"])
            for e in self.entries
            if e["changed_field"] == "correct_answer"
        }
        upper = extract_upper_pdf_keys(PDFS["placement_full"])
        self.assertEqual(len(upper), 85)
        self.assertEqual(upper[33], "A")
        for n, letter in upper.items():
            current_letter = self.current["placement"]["placement_full"][n - 1][
                "correct_answer"
            ]
            if ("placement_full", n) in allow_key_changes:
                continue
            self.assertEqual(current_letter, letter, f"Upper PDF Q{n}")

        em1 = extract_enhanced_pdf_mcq_keys(PDFS["enhanced_math_1"])
        self.assertEqual(len(em1), 50)
        for n, letter in em1.items():
            current_letter = self.current["placement"]["enhanced_math_1"][n - 1][
                "correct_answer"
            ]
            self.assertEqual(current_letter, letter, f"EM1 PDF Q{n}")

        em2 = extract_enhanced_pdf_mcq_keys(PDFS["enhanced_math_2"])
        self.assertEqual(len(em2), 55)
        for n, letter in em2.items():
            current_letter = self.current["placement"]["enhanced_math_2"][n - 1][
                "correct_answer"
            ]
            self.assertEqual(current_letter, letter, f"EM2 PDF Q{n}")

    def test_pdf_middle_keys_still_grade_correct(self):
        pdf_keys = extract_middle_pdf_keys(PDFS["middle_level"])
        self.assertEqual(len(pdf_keys), 100)
        self.assertEqual(pdf_keys[85], "420 frogs")
        self.assertEqual(pdf_keys[92], "2602.142857")
        for n, pdf_value in pdf_keys.items():
            item = self.current["placement"]["middle_level"][n - 1]
            student = normalize_middle_pdf_key(pdf_value)
            self.assertTrue(
                response_is_correct(item, student) or response_is_correct(item, pdf_value),
                f"Middle PDF Q{n} {pdf_value!r} / {student!r} rejected by current item",
            )

    def test_em2_q67_pdf_had_10_0_current_is_10_1(self):
        self.assertEqual(extract_em2_pdf_fr8(PDFS["enhanced_math_2"]), "c≈10.0")
        a, b, angle = 12.0, 15.0, math.radians(42.0)
        side_c = math.sqrt(a * a + b * b - 2 * a * b * math.cos(angle))
        self.assertAlmostEqual(side_c, 10.0731, places=3)
        self.assertEqual(round(side_c, 1), 10.1)
        q = self.current["placement"]["enhanced_math_2"][66]
        self.assertTrue(response_is_correct(q, "10.1"))
        self.assertFalse(response_is_correct(q, "10.0"))

    def test_working_tree_tex_q33_is_a(self):
        for path in TEX_SOURCES:
            keys = parse_placement_answer_key(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(keys[33], "A", path)
            self.assertEqual(len(keys), 85, path)

    def test_independent_verified_answers_for_allowlist(self):
        self.assertEqual(120 + 200 + 100, 420)
        self.assertAlmostEqual(1821.5 / 0.7, 2602.142857, places=6)
        sq_miles = 144 / (5280 ** 2)
        self.assertEqual(float(f"{sq_miles:.2e}"), 5.17e-6)
        from fractions import Fraction

        fifth = Fraction(6) * Fraction(1, 3) ** 4
        self.assertEqual(fifth, Fraction(2, 27))
        self.assertAlmostEqual(6 * math.sqrt(100), 60)
        self.assertEqual(math.hypot(9, 12), 15)
        def poly(x: int) -> int:
            return 2 * x * x - 7 * x - 15

        def factored(x: int) -> int:
            return (2 * x + 3) * (x - 5)

        self.assertEqual(
            [poly(x) for x in range(-3, 8)],
            [factored(x) for x in range(-3, 8)],
        )


if __name__ == "__main__":
    unittest.main()
