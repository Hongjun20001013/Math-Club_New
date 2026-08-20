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
    stem = plain_stem(item)
    n = ints(stem)
    low = stem.lower()
    if "which function" in low or "r(t)" in low:
        if n and n[0] == 0 and len(n) >= 4:
            q0, t1, q1 = n[1], n[2], n[3]
        else:
            q0, t1, q1 = n[0], n[1], n[2]
        r = (q0 - q1) / t1
        return f"R(t) = {q0} − {int(r)}t"
    q0, t1, q1 = n[0], n[1], n[2]
    r = (q0 - q1) / t1
    if "additional hours" in low:
        target = n[3]
        return str(int((q1 - target) / r))
    if "remain after" in low or "how many kilograms remain" in low or "how many gallons remain" in low:
        t = n[3]
        return str(int(q0 - r * t))
    target = n[3]
    return str(int((q0 - target) / r))


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


SOLVERS = {
    "sat.alg.linear_rate_remaining": independent_linear_rate,
    "sat.alg.solve_linear_equation": independent_solve_linear,
    "sat.alg.no_solution_parameter": independent_no_solution,
    "sat.alg.identity_infinite_solutions": independent_identity,
    "sat.alg.percent_cost_model": independent_percent,
    "sat.alg.translate_words_to_equation": independent_translate,
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
