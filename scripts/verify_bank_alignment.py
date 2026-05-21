#!/usr/bin/env python3
"""
Verify compiled question_bank.json matches Unit 1–4 masters + slices:
  - unit_1_all count == sum(1_1..1_5); stems align
  - unit_2_all count == sum(2_1..2_3); stems align
  - unit_3_all count == sum(3_1..3_7); stems align
  - unit_4_all count == sum(4_1..4_4); stems align

Run: python3 scripts/verify_bank_alignment.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK_PATH = os.path.join(APP_DIR, "data", "question_bank.json")
MANIFEST_PATH = os.path.join(APP_DIR, "data", "unit1_question_manifest.json")
MANIFEST2_PATH = os.path.join(APP_DIR, "data", "unit2_question_manifest.json")
MANIFEST3_PATH = os.path.join(APP_DIR, "data", "unit3_question_manifest.json")
MANIFEST4_PATH = os.path.join(APP_DIR, "data", "unit4_question_manifest.json")

SLICES = ["1_1", "1_2", "1_3", "1_4", "1_5"]
SECTION_LABEL = {
    "1_1": "1.1",
    "1_2": "1.2",
    "1_3": "1.3",
    "1_4": "1.4",
    "1_5": "1.5",
}

SLICES2 = ["2_1", "2_2", "2_3"]
SECTION2_LABEL = {
    "2_1": "2.1",
    "2_2": "2.2",
    "2_3": "2.3",
}

SLICES3 = ["3_1", "3_2", "3_3", "3_4", "3_5", "3_6", "3_7"]
SECTION3_LABEL = {
    "3_1": "3.1",
    "3_2": "3.2",
    "3_3": "3.3",
    "3_4": "3.4",
    "3_5": "3.5",
    "3_6": "3.6",
    "3_7": "3.7",
}

SLICES4 = ["4_1", "4_2", "4_3", "4_4"]
SECTION4_LABEL = {
    "4_1": "4.1",
    "4_2": "4.2",
    "4_3": "4.3",
    "4_4": "4.4",
}


def _verify_unit(
    alg: dict,
    full_key: str,
    slice_keys: list[str],
    section_label: dict[str, str],
    label: str,
    manifest_path: str,
) -> int:
    full = alg.get(full_key)
    if not full:
        print(f"Missing domain payload {full_key!r}", file=sys.stderr)
        return 1

    parts: list[tuple[str, list]] = []
    total_slice = 0
    for key in slice_keys:
        q = alg.get(key)
        if not q:
            print(f"Missing slice key {key!r}", file=sys.stderr)
            return 1
        parts.append((key, q))
        total_slice += len(q)

    if len(full) != total_slice:
        print(
            f"Count mismatch: {full_key}={len(full)} sum(slices)={total_slice}",
            file=sys.stderr,
        )
        return 1

    gi = 0
    manifest: list[dict] = []
    for topic_key, qs in parts:
        for li, q in enumerate(qs):
            if q["stem"] != full[gi]["stem"]:
                print(
                    f"[{label}] Stem mismatch at global index {gi} ({topic_key} local {li})",
                    file=sys.stderr,
                )
                return 1
            manifest.append(
                {
                    "display_number": gi + 1,
                    "section": section_label[topic_key],
                    "topic_key": topic_key,
                    "topic_local_index": li,
                }
            )
            gi += 1

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"OK: {len(full)} {label} questions aligned; wrote {manifest_path}")
    for topic_key, qs in parts:
        print(f"  {section_label[topic_key]} ({topic_key}): {len(qs)}")
    return 0


def _verify_unit4_static_figures() -> int:
    """Every \\includegraphics basename under banks/geometry must exist under static/unit4/."""
    root = Path(APP_DIR)
    refs: set[str] = set()
    geo_dir = root / "banks" / "geometry"
    if not geo_dir.is_dir():
        print("Missing banks/geometry/", file=sys.stderr)
        return 1
    for tex in sorted(geo_dir.glob("*.tex")):
        text = tex.read_text(encoding="utf-8")
        for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", text):
            refs.add(m.group(1).strip())
    static = root / "static" / "unit4"
    for name in sorted(refs):
        p = static / name
        if not p.is_file():
            print(f"Unit 4 figure missing on disk: {p}", file=sys.stderr)
            return 1
        head = p.read_bytes()[:256].lstrip()
        ok_jpeg = head[:2] == b"\xff\xd8"
        ok_png = head[:8] == b"\x89PNG\r\n\x1a\n"
        ok_svg = head[:4] == b"<svg" or head[:5] == b"<?xml"
        if not (ok_jpeg or ok_png or ok_svg):
            print(f"Unit 4 figure is not a JPEG/PNG/SVG payload: {p}", file=sys.stderr)
            return 1
    print(f"OK: Unit 4 figures ({len(refs)} files) present under static/unit4/")
    return 0


def main() -> int:
    with open(BANK_PATH, encoding="utf-8") as f:
        bank = json.load(f)
    alg = bank.get("algebra", {})
    r1 = _verify_unit(
        alg, "unit_1_all", SLICES, SECTION_LABEL, "Unit 1", MANIFEST_PATH
    )
    if r1 != 0:
        return r1
    adv = bank.get("advanced_math", {})
    r2 = _verify_unit(
        adv, "unit_2_all", SLICES2, SECTION2_LABEL, "Unit 2", MANIFEST2_PATH
    )
    if r2 != 0:
        return r2
    ps = bank.get("problem_solving", {})
    r3 = _verify_unit(
        ps, "unit_3_all", SLICES3, SECTION3_LABEL, "Unit 3", MANIFEST3_PATH
    )
    if r3 != 0:
        return r3
    geo = bank.get("geometry", {})
    r4 = _verify_unit(
        geo, "unit_4_all", SLICES4, SECTION4_LABEL, "Unit 4", MANIFEST4_PATH
    )
    if r4 != 0:
        return r4
    return _verify_unit4_static_figures()


if __name__ == "__main__":
    raise SystemExit(main())
