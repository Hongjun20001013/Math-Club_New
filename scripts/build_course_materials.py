from __future__ import annotations

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import APP_DIR
from beamer_parser import parse_beamer_file

MANIFEST = os.path.join(APP_DIR, "data", "course_materials_manifest.json")
OUTPUT = os.path.join(APP_DIR, "data", "course_materials.json")


def _resolve(candidates: list[str]) -> str | None:
    for rel in candidates:
        path = os.path.join(APP_DIR, rel)
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            return path
    return None


def build() -> dict:
    with open(MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    items: list[dict] = []
    available = 0
    for row in manifest.get("materials") or []:
        tex_path = _resolve(list(row.get("tex_candidates") or []))
        pdf_path = _resolve(list(row.get("pdf_candidates") or []))
        entry = {
            "slug": row["slug"],
            "unit": row["unit"],
            "unit_name": row["unit_name"],
            "section": row["section"],
            "title": row["title"],
            "deck_title": row["title"],
            "slide_count": 0,
            "slides": [],
            "tex_available": tex_path is not None,
            "pdf_available": pdf_path is not None,
            "tex_file": os.path.basename(tex_path) if tex_path else None,
            "pdf_file": os.path.basename(pdf_path) if pdf_path else None,
        }
        if tex_path:
            try:
                parsed = parse_beamer_file(tex_path)
                entry["deck_title"] = parsed.get("title") or row["title"]
                entry["slide_count"] = parsed.get("slide_count") or 0
                entry["slides"] = parsed.get("slides") or []
                entry["interactive_count"] = parsed.get("interactive_count") or 0
                entry["learn_count"] = parsed.get("learn_count") or 0
                entry["practice_slide_count"] = parsed.get("practice_slide_count") or 0
                entry["lesson_path"] = parsed.get("lesson_path") or []
                available += 1
            except Exception as exc:
                print("Warning: failed to parse", tex_path, exc)
        items.append(entry)

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total": len(items),
        "available": available,
        "materials": items,
    }
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("Wrote:", OUTPUT)
    print("Materials:", len(items), "· parsed:", available)
    return payload


if __name__ == "__main__":
    build()
