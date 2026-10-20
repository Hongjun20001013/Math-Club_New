"""Schematic tactics hung off a lineup. Coordinates are not an overlap ruling."""

from __future__ import annotations

import json

from volleyball_coach.lineup import build_card
from volleyball_coach.model import FRONT_SLOTS, TeamPlan, role_chip


PHASES = {
    "receive": "接发",
    "attack": "进攻展开",
    "block": "拦防",
    "cover": "保护",
}

NOTE_KINDS = {
    "serve_target": "发球预案",
    "block_task": "拦防任务",
    "cover_note": "保护",
}

EXECUTIONS = {
    "hit": "执行到",
    "miss": "没执行到",
    "unchecked": "未核对",
}

SLOT_X = {4: 28.0, 5: 30.0, 3: 50.0, 6: 50.0, 2: 72.0, 1: 70.0}
WING_X = {"左翼": 26.0, "中路": 50.0, "右翼": 74.0}


def position_kind(plan: TeamPlan) -> str:
    if plan.rules.overlap_confirmed:
        return "已按本赛事规则核验的站位"
    return "示意站位"


def home_xy(slot: int) -> tuple[float, float]:
    return SLOT_X[slot], 38.0 if slot in FRONT_SLOTS else 78.0


def _phase_xy(card, slot: int, phase: str) -> tuple[float, float]:
    view = card.slots[slot]
    receiver_ids = {item["id"] for item in card.receivers}
    wing = view.wing or "中路"
    if phase == "receive":
        if slot in FRONT_SLOTS and view.occupant_id not in receiver_ids:
            return WING_X.get(wing, 50.0), 30.0
        if slot in FRONT_SLOTS and view.occupant_id in receiver_ids:
            return SLOT_X[slot], 54.0
        return SLOT_X[slot], 78.0
    if phase == "attack":
        if slot in FRONT_SLOTS:
            return WING_X.get(wing, 50.0), 24.0
        return SLOT_X[slot], 76.0
    if phase == "block":
        if slot in FRONT_SLOTS:
            return WING_X.get(wing, 50.0), 12.0
        return SLOT_X[slot], 68.0
    if view.occupant_id == card.setter_id:
        return 50.0, 58.0
    return SLOT_X[slot], 42.0 if view.role_label == "middle" else 72.0


def preview_marks(card, rotation: int, phase: str) -> list[dict]:
    """Unsaved receive shape for the court, before a tactic exists."""
    if not card.slots or phase not in PHASES:
        return []
    marks = []
    for slot, view in card.slots.items():
        x, y = _phase_xy(card, slot, phase)
        marks.append(
            {
                "rotation": rotation,
                "phase": phase,
                "slot": slot,
                "player_id": view.occupant_id,
                "x": x,
                "y": y,
            }
        )
    return marks


def default_marks(plan: TeamPlan, locked_pairs: set[frozenset[str]]) -> list[dict]:
    marks = []
    for rotation in range(1, 7):
        card = build_card(plan, rotation, {}, locked_pairs)
        if not card.slots:
            continue
        for phase in PHASES:
            for slot, view in card.slots.items():
                x, y = _phase_xy(card, slot, phase)
                marks.append(
                    {
                        "rotation": rotation,
                        "phase": phase,
                        "slot": slot,
                        "player_id": view.occupant_id,
                        "x": x,
                        "y": y,
                    }
                )
    return marks


def rotation_status(card, receive_marks: list[dict]) -> str:
    """Computed from the lineup and the receive marks. There is no ready checkbox."""
    if not card.slots:
        return "待补充"
    if card.structural:
        return "存在冲突"
    by_slot = {int(mark["slot"]): mark for mark in receive_marks}
    if len(by_slot) < 6:
        return "待补充"
    for slot, view in card.slots.items():
        mark = by_slot.get(slot)
        if mark is None or mark.get("player_id") != view.occupant_id:
            return "存在冲突"
    if not card.setter_id or not card.slots[1].occupant_id or not card.backup_id:
        return "待补充"
    return "已配置"


def identity_drift(cards: dict, marks: list[dict]) -> bool:
    for rotation, card in cards.items():
        if not card.slots:
            continue
        by_slot = {
            int(mark["slot"]): mark.get("player_id")
            for mark in marks
            if int(mark["rotation"]) == rotation and mark["phase"] == "receive"
        }
        for slot, view in card.slots.items():
            if by_slot.get(slot) != view.occupant_id:
                return True
    return False


def display_num(value) -> str:
    text = f"{float(value):.1f}"
    if text.endswith(".0"):
        return text[:-2]
    return text


def present_marks(plan: TeamPlan, card, marks: list[dict]) -> list[dict]:
    shown = []
    for mark in marks:
        slot = int(mark["slot"])
        player_id = mark["player_id"]
        player = plan.players.get(player_id)
        home_x, home_y = home_xy(slot)
        x = float(mark["x"])
        y = float(mark["y"])
        shown.append(
            {
                "rotation": int(mark["rotation"]),
                "phase": mark["phase"],
                "slot": slot,
                "player_id": player_id,
                "name": mark.get("name") or plan.name_of(player_id),
                "jersey": (player.jersey if player else "") or "",
                "row": "前排" if slot in FRONT_SLOTS else "后排",
                "setter": bool(card and card.setter_id and player_id == card.setter_id),
                "role": role_chip(player.role, setting=bool(card and card.setter_id == player_id)) if player else "",
                "x": display_num(x),
                "y": display_num(y),
                "home_x": display_num(home_x),
                "home_y": display_num(home_y),
                "moved": abs(x - home_x) + abs(y - home_y) > 6,
            }
        )
    shown.sort(key=lambda item: item["slot"])
    return shown


def snapshot_payload(tactic: dict, marks: list[dict], notes: list[dict], plan: TeamPlan, scheme_name: str) -> dict:
    named = []
    for mark in marks:
        named.append(
            {
                "rotation": int(mark["rotation"]),
                "phase": mark["phase"],
                "slot": int(mark["slot"]),
                "player_id": mark["player_id"],
                "name": plan.name_of(mark["player_id"]),
                "x": float(mark["x"]),
                "y": float(mark["y"]),
            }
        )
    return {
        "id": tactic["id"],
        "name": tactic["name"],
        "scheme_id": tactic["scheme_id"],
        "scheme_name": scheme_name,
        "status": "published",
        "position_kind": position_kind(plan),
        "marks": named,
        "notes": [
            {"rotation": int(note["rotation"]), "kind": note["kind"], "body": note["body"]}
            for note in notes
        ],
    }


def load_snapshot(raw: str) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not data.get("marks"):
        return None
    return data


def execution_counts(rallies: list[dict]) -> dict[str, int]:
    counts = {"hit": 0, "miss": 0, "unchecked": 0}
    for rally in rallies:
        mark = rally.get("plan_execution") or ""
        if mark in counts:
            counts[mark] += 1
    return counts


def execution_sentence(counts: dict[str, int], tactic_name: str) -> str:
    return (
        f"本场调用「{tactic_name}」。"
        f"执行到 {counts['hit']}，没执行到 {counts['miss']}，未核对 {counts['unchecked']}。"
        "没标的回合不进这三项。这些只说明当时选用的预案，不能说明球员站在示意点上。"
    )
