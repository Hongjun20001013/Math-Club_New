"""Choose a teaching path from diagnostic performance and hint use.

Does not use user_id, arm, or user_id % 2. Does not migrate the database.
Serving a chosen path still uses the existing six-phase state machine; this
module only ranks later-slot variants inside one shared 18-item family.
"""
from __future__ import annotations

from typing import Any, Iterable

FOUNDATION = "foundation"
STANDARD = "standard"
ADVANCED = "advanced"
PATHS = (FOUNDATION, STANDARD, ADVANCED)

SLOT_ORDER = (
    "diagnostic",
    "worked_example",
    "faded",
    "independent",
    "transfer",
    "delayed",
)


def classify_path(diagnostic_rows: Iterable[dict[str, Any]]) -> str:
    """Return foundation / standard / advanced from diagnostic work only."""
    rows = list(diagnostic_rows or [])
    if not rows:
        return FOUNDATION
    correct = 0
    used_light = False
    used_strong = False
    for row in rows:
        if int(row.get("is_correct") or 0):
            correct += 1
        hint = str(row.get("hint_level") or "none").lower()
        if hint == "light":
            used_light = True
        if hint in {"critical", "strong", "stronger"} or bool(row.get("solution_viewed")):
            used_strong = True
    if used_strong or correct <= 1:
        return FOUNDATION
    if used_light or correct == 2:
        return STANDARD
    return ADVANCED


def items_for_path(pack: dict[str, Any], path: str) -> list[dict[str, Any]]:
    """Pick later-slot items from one shared pack. Diagnostics are always included."""
    wanted = path if path in PATHS else FOUNDATION
    selected: list[dict[str, Any]] = []
    for item in pack.get("items") or []:
        tags = item.get("path_tags") or item.get("path_affinity") or []
        if isinstance(tags, str):
            tags = [tags]
        slot = str(item.get("slot") or "")
        if slot == "diagnostic" or wanted in tags:
            selected.append(item)
    return selected


def recommended_variant_ids(pack: dict[str, Any], path: str) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {slot: [] for slot in SLOT_ORDER}
    for item in items_for_path(pack, path):
        slot = str(item.get("slot") or "")
        if slot in grouped:
            grouped[slot].append(str(item["id"]))
    return grouped


def _tags(item: dict[str, Any]) -> list[str]:
    tags = item.get("path_tags") or item.get("path_affinity") or []
    if isinstance(tags, str):
        return [tags]
    return [str(t) for t in tags]


def next_item_for_path(
    pack: dict[str, Any],
    slot: str,
    path: str | None,
    used_ids: Iterable[str],
) -> dict[str, Any] | None:
    """Next unused item in a slot. Diagnostics ignore path; later slots prefer path_tags."""
    used = {str(i) for i in used_ids or []}
    items = [it for it in (pack.get("items") or []) if str(it.get("slot") or "") == slot]
    if slot != "diagnostic" and path:
        tagged = [it for it in items if path in _tags(it)]
        if tagged:
            items = tagged
    for item in items:
        if str(item.get("id") or "") not in used:
            return item
    return None
