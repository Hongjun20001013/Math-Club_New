"""Independent math audit of every Repair-cycle pilot item.

Does not connect to production and does not modify question_bank.json.
"""
from __future__ import annotations

import json
import os
import re
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "data" / "skill_loop_pilot"
AUDIT_PATH = ROOT / "tests" / "e2e" / "screenshots" / "pilot_math_audit.md"

from repair_html import html_to_plain, stem_normalized_hash  # noqa: E402
from skill_repair import _normalize_math_answer  # noqa: E402


def load_packs() -> list[dict]:
    packs = []
    for path in sorted(PACK_DIR.glob("sat.alg.*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_path"] = str(path)
        packs.append(data)
    return packs


def all_items() -> list[tuple[str, dict]]:
    out = []
    for pack in load_packs():
        for item in pack.get("items") or []:
            out.append((str(pack.get("skill_code")), item))
    return out


def plain_stem(item: dict) -> str:
    return html_to_plain(str(item.get("stem_html") or item.get("stem") or ""))


def ints(text: str) -> list[int]:
    return [int(x.replace(",", "")) for x in re.findall(r"-?\d[\d,]*", text.replace("−", "-").replace("–", "-"))]


def letter_index(item: dict) -> int | None:
    ans = str(item.get("correct_answer") or "").strip()
    if len(ans) == 1 and ans.upper() in "ABCDE":
        return ord(ans.upper()) - ord("A")
    return None


def choice_text(item: dict) -> str:
    idx = letter_index(item)
    choices = item.get("choices") or []
    if idx is None or not (0 <= idx < len(choices)):
        return str(item.get("correct_math") or item.get("correct_answer") or "")
    return str(choices[idx])


def independent_linear_rate(item: dict) -> str:
    """Solve each rewritten LRR item from its stem quantities, not the stored letter."""
    iid = item.get("id")
    if iid == "slq_lrr_precheck_01":
        # 9600 start, after 3 h remain 8100, additional hours to remain 5100
        r = (9600 - 8100) / 3
        return str(int((8100 - 5100) / r))
    if iid == "slq_lrr_example_01":
        # table Q(0)=7200, Q(4)=5600; remaining at t=10
        r = (7200 - 5600) / 4
        return str(int(7200 - r * 10))
    if iid == "slq_lrr_faded_01":
        r = (4800 - 3550) / 5
        return str(int((4800 - 1300) / r))
    if iid == "slq_lrr_faded_02":
        # reverse Q0: remain 2160 after 4 h at 180 gal/h
        return str(int(2160 + 180 * 4))
    if iid == "slq_lrr_ind_01":
        # points (3, 4500), (8, 2500); remaining at t=11
        slope = (2500 - 4500) / (8 - 3)
        return str(int(4500 + slope * (11 - 3)))
    if iid == "slq_lrr_ind_02":
        # 9200 - 250t = 3200
        return str(int((9200 - 3200) / 250))
    if iid == "slq_lrr_ind_03":
        r = (11000 - 8300) / 6
        return str(int((11000 - 2900) / r))
    if iid == "slq_lrr_tr_01":
        # intercept 6000, slope -150; remaining after 8 h
        return str(int(6000 - 150 * 8))
    if iid == "slq_lrr_tr_02":
        # table (2, 4100), (5, 3200) -> Q0 and R(t)
        r = (4100 - 3200) / (5 - 2)
        q0 = 4100 + r * 2
        return f"R(t) = {int(q0)} − {int(r)}t"
    if iid == "slq_lrr_tr_03":
        r = (5400 - 2700) / 9
        return f"G(t) = 5400 − {int(r)}t"
    if iid == "slq_lrr_del_01":
        r = (8000 - 6250) / 5
        return str(int((6250 - 2750) / r))
    if iid == "slq_lrr_del_02":
        # remaining 13600 at t=4 and 8800 at t=10; unloading rate
        return str(int((13600 - 8800) / (10 - 4)))
    raise AssertionError(f"unsolved linear remaining item {iid}")


def independent_solve_linear(item: dict) -> str:
    stem = plain_stem(item).replace("−", "-")
    iid = item.get("id")
    # Independent closed-form solutions, not copied from the answer key letter.
    if iid == "slq_sle_example_01":
        return "x = 5"  # 5x - 7 = 18 -> 5x = 25
    if iid == "slq_sle_faded_01":
        return "n = 5"  # 4n + 9 = 29
    if iid == "slq_sle_faded_02":
        return "k = 5"  # 7k - 11 = 24
    if iid == "slq_sle_ind_01":
        # 3(x-2)+5=14 -> 3x-6+5=14 -> 3x=15
        return "x = 5"
    if iid == "slq_sle_ind_02":
        # 2y/3 + 4 = 10 -> 2y/3 = 6 -> y = 9
        return "y = 9"
    if iid == "slq_sle_tr_01":
        # 4x-3=9 -> x=3 -> 2x+1=7
        return "2x + 1 = 7"
    if iid == "slq_sle_tr_02":
        # 6(w+1)=30 -> w=4 -> 3w=12
        return "3w = 12"
    if iid == "slq_sle_del_01":
        return "t = 3"  # 8t+17=41
    if iid == "slq_sle_del_02":
        return "m = 2"  # 5(m+3)-4=21 -> 5m+15-4=21 -> 5m=10
    raise AssertionError(f"unsolved linear item {iid}: {stem}")


def independent_no_solution(item: dict) -> str:
    iid = item.get("id")
    # Expand independently.
    if iid == "slq_nsp_example_01":
        # 2x+5=2x+k -> 5=k identity; no solution iff k != 5
        return "k ≠ 5"
    if iid == "slq_nsp_faded_01":
        # 3(y+1)=3y+m -> 3y+3=3y+m -> no solution iff m != 3
        return "m ≠ 3"
    if iid == "slq_nsp_faded_02":
        return "c ≠ −1"  # -1 = c identity
    if iid == "slq_nsp_ind_01":
        return "n ≠ −10"  # 5x-10=5x+n
    if iid == "slq_nsp_ind_02":
        return "p ≠ −4"  # p = -4 identity
    if iid == "slq_nsp_tr_01":
        return "k ≠ 2"  # 2=k identity
    if iid == "slq_nsp_tr_02":
        # (2k)x+5=4x+3 needs 2k=4 and 5!=3 -> k=2 uniquely
        return "k = 2"
    if iid == "slq_nsp_del_01":
        return "r ≠ 4"
    if iid == "slq_nsp_del_02":
        return "q ≠ 14"  # 2x+14=2x+q
    raise AssertionError(iid)


def independent_identity(item: dict) -> str:
    iid = item.get("id")
    if iid == "slq_iis_example_01":
        # 4(x-1)+6=4x-4+6=4x+2 so k=2
        return "k = 2"
    if iid == "slq_iis_faded_01":
        # 5x+3 = 5x+5t-12 -> 3=5t-12 -> t=3
        return "t = 3"
    if iid == "slq_iis_faded_02":
        # 6x+2b=6x+10 -> b=5
        return "b = 5"
    if iid == "slq_iis_ind_01":
        # 7x+14-4=7x+10 -> m=10
        return "m = 10"
    if iid == "slq_iis_ind_02":
        # 3x-c = 3x-12+8=3x-4 -> c=4
        return "c = 4"
    if iid == "slq_iis_tr_01":
        # 2(x+5)=2x+10 identity
        return "infinitely many solutions"
    if iid == "slq_iis_tr_02":
        return "infinitely many intersection points"
    if iid == "slq_iis_del_01":
        # 8x+9=8x+8q-7 -> 9=8q-7 -> q=2
        return "q = 2"
    if iid == "slq_iis_del_02":
        # 9x-9+4=9x-5 -> d=-5
        return "d = −5"
    raise AssertionError(iid)


def independent_percent(item: dict) -> str:
    iid = item.get("id")
    if iid == "slq_pcm_example_01":
        return "60"  # 80*0.75
    if iid == "slq_pcm_faded_01":
        return "43.20"  # 40*1.08
    if iid == "slq_pcm_faded_02":
        return "60"  # 50*1.2
    if iid == "slq_pcm_ind_01":
        return "204"  # 240*0.85
    if iid == "slq_pcm_ind_02":
        return "26.50"  # 25*1.06
    if iid == "slq_pcm_tr_01":
        return "120"  # 96/0.8
    if iid == "slq_pcm_tr_02":
        return "165"  # 200*0.75*1.1
    if iid == "slq_pcm_del_01":
        return "63"  # 90*0.7
    if iid == "slq_pcm_del_02":
        return "18.90"  # 18*1.05
    raise AssertionError(iid)


def independent_translate(item: dict) -> str:
    iid = item.get("id")
    mapping = {
        "slq_twe_example_01": "30h + 45 = 165",
        "slq_twe_faded_01": "15c + 20 = 80",
        "slq_twe_faded_02": "4p + 12 = 52",
        "slq_twe_ind_01": "6t + 8 = 32",
        "slq_twe_ind_02": "7m + 40 = 89",
        "slq_twe_tr_01": "2.25n + 3.50",
        "slq_twe_tr_02": "C = 90 − 6t",
        "slq_twe_del_01": "40h + 120 = 280",
        "slq_twe_del_02": "0.10m + 25 = 31",
    }
    if iid not in mapping:
        raise AssertionError(iid)
    return mapping[iid]


def independent_linear_relationships_v2(item: dict) -> str:
    iid = item.get("id")
    if iid == "slq_lrv2_diag_01":
        r = (12000 - 9600) / 6
        return str(int((9600 - 4800) / r))
    if iid == "slq_lrv2_diag_02":
        hourly = (340 - 180) / (7 - 3)
        intercept = 180 - hourly * 3
        return f"{int(hourly)}x+{int(intercept)}"
    if iid == "slq_lrv2_diag_03":
        return "value at the shift"
    if iid == "slq_lrv2_ex_01":
        r = (6400 - 5600) / 4
        return str(int(6400 - r * 12))
    if iid == "slq_lrv2_ex_02":
        return "35h+50"
    if iid == "slq_lrv2_faded_01":
        r = (4500 - 3500) / 5
        return str(int((4500 - 1500) / r))
    if iid == "slq_lrv2_faded_02":
        return str(int(1680 + 140 * 6))
    if iid == "slq_lrv2_faded_03":
        return str(int(15 * 20 + 9 * 7))
    if iid == "slq_lrv2_ind_01":
        r = (3600 - 2400) / (10 - 4)
        return str(int(3600 - r * (13 - 4)))
    if iid == "slq_lrv2_ind_02":
        return str(int((7600 - 2000) / 400))
    if iid == "slq_lrv2_ind_03":
        slope = (6000 - 9000) / (50 - 30)
        return str(int(9000 + slope * (40 - 30)))
    if iid == "slq_lrv2_ind_04":
        a = (14 - 8) / (3 - 1)
        b = 8 - a * 1
        return str(int(a - b))
    if iid == "slq_lrv2_tr_01":
        return "decreases each year"
    if iid == "slq_lrv2_tr_02":
        r = (4700 - 3800) / 3
        return f"4700-{int(r)}t"
    if iid == "slq_lrv2_tr_03":
        return "value at the shift"
    if iid == "slq_lrv2_tr_04":
        return "additional hourly fee"
    if iid == "slq_lrv2_del_01":
        r = (14400 - 12000) / 4
        return str(int((12000 - 6000) / r))
    if iid == "slq_lrv2_del_02":
        return "95x+225"
    raise AssertionError(f"unsolved v2 item {iid}")


SOLVERS = {
    "sat.alg.linear_rate_remaining": independent_linear_rate,
    "sat.alg.solve_linear_equation": independent_solve_linear,
    "sat.alg.no_solution_parameter": independent_no_solution,
    "sat.alg.identity_infinite_solutions": independent_identity,
    "sat.alg.percent_cost_model": independent_percent,
    "sat.alg.translate_words_to_equation": independent_translate,
    "sat.alg.linear_relationships_v2": independent_linear_relationships_v2,
}


def math_close(a: str, b: str) -> bool:
    na, nb = _normalize_math_answer(a), _normalize_math_answer(b)
    if na == nb:
        return True
    # Allow 11600 vs 11,600 and 43.2 vs 43.20
    try:
        return abs(float(na) - float(nb)) < 1e-6
    except ValueError:
        return na.replace("−", "-") == nb.replace("−", "-")


def is_set_valued(math: str) -> bool:
    t = math.lower()
    return "≠" in math or "!=" in t or "except" in t or "infinitely" in t


def wording_issues(item: dict) -> list[str]:
    stem = plain_stem(item)
    low = stem.lower()
    math = str(item.get("correct_math") or "")
    issues = []
    if "single forbidden" in low:
        issues.append("contains confusing 'single forbidden k' language")
    if re.search(r"\bthe system\b", low) and not re.search(r"\band\b.*=.*=", low):
        issues.append("uses 'system' for a single equation")
    singular = re.search(r"what is the value of|for which value of|for what value of", low)
    if singular and is_set_valued(math):
        issues.append("asks for a single value but the math answer is a set")
    if item.get("slot") == "faded" and not (item.get("blanks") or []):
        issues.append("faded item has no blanks")
    if item.get("slot") == "faded" and (item.get("choices") or []):
        issues.append("faded item still uses MCQ choices instead of a scaffold")
    choices = item.get("choices") or []
    idx = letter_index(item)
    if choices and idx is not None:
        if idx < 0 or idx >= len(choices):
            issues.append("correct_answer letter does not match a choice")
        else:
            chosen = str(choices[idx])
            if math and not (
                math_close(chosen, math)
                or _normalize_math_answer(math) in _normalize_math_answer(chosen)
                or _normalize_math_answer(chosen) in _normalize_math_answer(math)
                or any(tok in chosen.lower() for tok in math.lower().replace("≠", "not").split() if len(tok) > 1)
            ):
                # For long choice sentences, require the math fragment to appear
                if "≠" in math or "!=" in math:
                    if "≠" not in chosen and "except" not in chosen.lower() and "!=" not in chosen:
                        issues.append("correct choice does not state the set-valued conclusion")
                elif math_close(chosen.replace("$", ""), math.replace("$", "")):
                    pass
                elif (
                    _normalize_math_answer(math) in _normalize_math_answer(chosen)
                    or re.sub(r"[^0-9A-Za-z.=-]", "", math.replace("−", "-").replace(",", ""))
                    in re.sub(r"[^0-9A-Za-z.=-]", "", chosen.replace("{,}", "").replace(",", "").replace("−", "-"))
                ):
                    pass
                elif re.sub(r"[^\d.]", "", chosen) and re.sub(r"[^\d.]", "", math):
                    if not math_close(re.sub(r"[^\d.]", "", chosen), re.sub(r"[^\d.]", "", math)):
                        issues.append("correct choice numeric value does not match correct_math")
    return issues


class PilotItemMathTests(unittest.TestCase):
    def test_independent_solve_and_wording_for_every_item(self):
        rows = []
        hashes = []
        ids = []
        failures = []
        for skill, item in all_items():
            iid = str(item.get("id"))
            ids.append(iid)
            stem = plain_stem(item)
            hashes.append(stem_normalized_hash(stem))
            solver = SOLVERS[skill]
            independent = solver(item)
            stored = str(item.get("correct_math") or "")
            if not math_close(independent, stored):
                failures.append(f"{iid}: independent {independent!r} != stored {stored!r}")
            issues = wording_issues(item)
            if issues:
                failures.append(f"{iid}: " + "; ".join(issues))
            # uniqueness of a numerical key among MCQ choices
            choices = item.get("choices") or []
            idx = letter_index(item)
            unique_ok = True
            if choices and idx is not None:
                norms = [_normalize_math_answer(c) for c in choices]
                unique_ok = norms.count(norms[idx]) == 1
                if not unique_ok:
                    failures.append(f"{iid}: correct choice is duplicated")
            rows.append(
                {
                    "skill": skill,
                    "id": iid,
                    "slot": item.get("slot"),
                    "stem": stem[:140],
                    "independent": independent,
                    "stored_math": stored,
                    "choice": choice_text(item),
                    "unique": unique_ok,
                    "issues": issues,
                }
            )
        self.assertEqual(len(ids), len(set(ids)), "duplicate item ids")
        coll = [h for h, n in Counter(hashes).items() if n > 1]
        self.assertFalse(coll, f"duplicate stem hashes: {coll}")
        os.makedirs(AUDIT_PATH.parent, exist_ok=True)
        lines = [
            "# Pilot item math audit",
            "",
            "| Skill | Item | Slot | Independent result | Stored math | Unique key | Issues |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in rows:
            lines.append(
                f"| `{row['skill']}` | `{row['id']}` | {row['slot']} | {row['independent']} | {row['stored_math']} | {row['unique']} | {'; '.join(row['issues']) or 'pass'} |"
            )
        AUDIT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertFalse(failures, "\n".join(failures))

    def test_lrr_pack_blueprint_and_bank_untouched(self):
        from scripts.skill_loop_baseline import sha256_file, bank_question_count

        pack = next(p for p in load_packs() if p["skill_code"] == "sat.alg.linear_rate_remaining")
        items = pack["items"]
        self.assertEqual(len(items), 12)
        ids = [it["id"] for it in items]
        self.assertEqual(len(ids), len(set(ids)))
        slots = Counter(it["slot"] for it in items)
        self.assertEqual(
            dict(slots),
            {
                "precheck": 1,
                "worked_example": 1,
                "faded": 2,
                "independent": 3,
                "transfer": 3,
                "delayed": 2,
            },
        )
        required = {
            "id",
            "slot",
            "phase",
            "difficulty",
            "representation",
            "tested_reasoning",
            "stem_html",
            "choices",
            "correct_answer",
            "answer_alternates",
            "distractor_rationale",
            "worked_steps",
            "faded",
            "common_mistake",
            "source_note",
        }
        standard = 0
        reps = set()
        for it in items:
            missing = required - set(it)
            self.assertFalse(missing, f"{it.get('id')} missing {missing}")
            self.assertEqual(it.get("review_status"), "draft")
            self.assertEqual(it.get("publish_status"), "unpublished")
            self.assertIn("Not copied from question_bank.json", it.get("source_note") or "")
            reps.add(it["representation"])
            if it.get("standard_snapshot_wording"):
                standard += 1
            choices = it.get("choices") or []
            idx = letter_index(it)
            if choices:
                self.assertEqual(len(choices), len(set(choices)))
                self.assertIsNotNone(idx)
                self.assertTrue(it.get("distractor_rationale"))
        self.assertLessEqual(standard, 4)
        self.assertTrue(any("table" in r for r in reps))
        self.assertTrue(any("function" in r or r.endswith("function") for r in reps))
        self.assertTrue(any("coordinate" in r for r in reps))
        self.assertTrue(any("reverse_initial" in r for r in reps))
        self.assertTrue(any("reverse_rate" in r for r in reps))
        self.assertTrue(any("slope" in r for r in reps))
        self.assertTrue(any("additional" in r for r in reps))
        delayed_reps = [it["representation"] for it in items if it["slot"] == "delayed"]
        transfer_reps = [it["representation"] for it in items if it["slot"] == "transfer"]
        self.assertEqual(len(delayed_reps), 2)
        self.assertEqual(len(set(delayed_reps)), 2)
        self.assertTrue(any("coordinate" in r for r in transfer_reps))
        self.assertNotIn("immediate", slots)
        self.assertEqual(sum(1 for it in items if it["slot"] == "precheck"), 1)
        bank = os.path.join(ROOT, "data", "question_bank.json")
        self.assertEqual(bank_question_count(bank), 1507)
        digest = sha256_file(bank)
        self.assertEqual(digest, "238934f8b1893d91f8b6fd92e7d326854620f1da1fc14ef2dde36a4a58be83c0")

    def test_no_solution_stems_use_statement_or_values_wording(self):
        for skill, item in all_items():
            if skill != "sat.alg.no_solution_parameter":
                continue
            stem = plain_stem(item).lower()
            math = str(item.get("correct_math") or "")
            if is_set_valued(math):
                self.assertNotRegex(stem, r"what is the value of k")
                self.assertNotIn("system", stem)
                self.assertNotIn("single forbidden", stem)


if __name__ == "__main__":
    unittest.main()
