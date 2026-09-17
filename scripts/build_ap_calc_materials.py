#!/usr/bin/env python3
"""Build AP Calculus AB/BC course materials JSON — Unit 1 sections 1.1–1.3."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP_DIR, "scripts"))

from ap_calc_graphs import build_all_graphs  # noqa: E402
from ap_calc_lesson_11 import build as build_lesson_11  # noqa: E402
from ap_calc_lesson_12 import build as build_lesson_12  # noqa: E402
from ap_calc_lesson_13 import build as build_lesson_13  # noqa: E402

OUTPUT = os.path.join(APP_DIR, "data", "ap_calc_materials.json")


def _finalize_materials(materials: list[dict]) -> list[dict]:
    for i, material in enumerate(materials):
        slides = material.get("slides") or []
        material["interactive_count"] = sum(1 for s in slides if s.get("kind") == "question")
        material["checkpoint_count"] = sum(
            1 for s in slides if s.get("kind") == "question" or "Exit Ticket" in s.get("title", "")
        )
        material["tex_available"] = True
        material["pdf_available"] = False
        material["phase"] = 1
        material["prev_lesson_slug"] = materials[i - 1]["slug"] if i > 0 else None
        material["next_lesson_slug"] = materials[i + 1]["slug"] if i + 1 < len(materials) else None
        phases = []
        for s in slides:
            ph = s.get("path_phase")
            if ph and (not phases or phases[-1]["label"] != ph):
                phases.append({"label": ph, "slide_index": s["index"]})
        if phases:
            material["knowledge_map"] = phases
    return materials


def build() -> dict:
    graphs = build_all_graphs()
    materials = _finalize_materials([
        build_lesson_11(graphs),
        build_lesson_12(graphs),
        build_lesson_13(graphs),
    ])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "track": "ap_calc",
        "total": len(materials),
        "available": len(materials),
        "materials": materials,
    }


def main() -> None:
    payload = build()
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    counts = [m["slide_count"] for m in payload["materials"]]
    print(f"Wrote {OUTPUT} ({payload['total']} lessons, slides: {counts})")


if __name__ == "__main__":
    main()
