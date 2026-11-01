"""Append-only match log. Score, rotation, and subs are replayed; they are never guessed back into history."""

from __future__ import annotations

from dataclasses import replace

from volleyball_coach.lineup import PlanError, next_rotation, project_lineup
from volleyball_coach.model import MatchState, TeamPlan


REVERSIBLE = {"point", "sub", "correct", "manual_rotation", "bookmark"}


class MatchError(ValueError):
    pass


def _clone(state: MatchState) -> MatchState:
    return replace(
        state,
        overrides=dict(state.overrides),
        locked_pairs=set(state.locked_pairs),
        conflicts=list(state.conflicts),
        structural=list(state.structural),
        origins=dict(state.origins),
        occupants=dict(state.occupants),
    )


def refresh(plan: TeamPlan, state: MatchState) -> MatchState:
    origins, occupants, structural, tactical = project_lineup(
        plan, state.rotation, state.overrides, state.locked_pairs
    )
    state.origins = origins
    state.occupants = occupants
    state.structural = structural
    state.conflicts = structural + tactical
    state.trusted = not structural
    return state


def start_set(
    plan: TeamPlan,
    *,
    rotation: int,
    serving: str,
    locked_pairs: set[frozenset[str]],
    mode: str,
    set_index: int = 1,
    overrides: dict[str, str] | None = None,
) -> MatchState:
    if serving not in ("us", "them"):
        raise MatchError("发球方只能是我方或对方。")
    if mode not in ("plan", "light"):
        raise MatchError("模式只能是预案或轻记录。")
    state = MatchState(
        rotation=rotation,
        serving=serving,
        score_us=0,
        score_them=0,
        overrides=dict(overrides or {}),
        set_index=set_index,
        trusted=True,
        history_gap=False,
        score_tracked=mode == "light",
        mode=mode,
        locked_pairs=set(locked_pairs),
        sub_count=0,
    )
    refresh(plan, state)
    if state.structural:
        raise MatchError(state.structural[0])
    return state


def apply_point(plan: TeamPlan, state: MatchState, winner: str) -> MatchState:
    if winner not in ("us", "them"):
        raise MatchError("胜方只能是我方或对方。")
    if not state.trusted:
        raise MatchError("状态还没校正，先不要继续记分。")
    updated = _clone(state)
    if winner == updated.serving:
        if winner == "us":
            updated.score_us += 1
        else:
            updated.score_them += 1
    elif winner == "us":
        updated.rotation = next_rotation(updated.rotation)
        updated.serving = "us"
        updated.score_us += 1
    else:
        updated.serving = "them"
        updated.score_them += 1
    updated.score_tracked = True
    return refresh(plan, updated)


def _origin_for_occupant(state: MatchState, occupant_id: str) -> str | None:
    for slot, occupant in state.occupants.items():
        if occupant == occupant_id:
            return state.origins.get(slot)
    return None


def apply_sub(plan: TeamPlan, state: MatchState, out_id: str, in_id: str) -> MatchState:
    if out_id not in set(state.occupants.values()):
        raise MatchError(f"{plan.name_of(out_id)} 现在不在场上。")
    if in_id in set(state.occupants.values()):
        raise MatchError(f"{plan.name_of(in_id)} 已经在场上。")
    if in_id not in plan.players or out_id not in plan.players:
        raise MatchError("换人双方都要在这支球队的名单里。")
    if plan.rules.fixed_pair_subs and frozenset((out_id, in_id)) not in state.locked_pairs:
        raise MatchError(
            f"{plan.name_of(in_id)} 本场没有锁定替换 {plan.name_of(out_id)}。"
            "一个人不能跨配对上场。"
        )
    if not plan.rules.unlimited_subs and plan.rules.max_subs is not None:
        if state.sub_count_uncertain:
            raise MatchError("校正过比分以后，换人次数不再可靠。先不要用次数上限拦截，把上限留空或重新开局。")
        if state.sub_count >= plan.rules.max_subs:
            raise MatchError(f"本局换人已到你设置的上限 {plan.rules.max_subs} 次。")
    origin = _origin_for_occupant(state, out_id)
    if origin is None:
        raise MatchError("找不到被换下球员的轮转槽。")
    updated = _clone(state)
    if in_id == origin:
        updated.overrides.pop(origin, None)
    else:
        updated.overrides[origin] = in_id
    updated.sub_count += 1
    return refresh(plan, updated)


def apply_manual_rotation(plan: TeamPlan, state: MatchState, rotation: int) -> MatchState:
    if rotation not in range(1, 7):
        raise MatchError("轮次必须是 1 到 6。")
    updated = _clone(state)
    updated.rotation = rotation
    updated.score_tracked = False
    updated.history_gap = True
    return refresh(plan, updated)


def apply_correction(
    plan: TeamPlan,
    state: MatchState,
    *,
    rotation: int,
    serving: str,
    occupants_by_slot: dict[int, str],
    score_us: int,
    score_them: int,
) -> MatchState:
    if serving not in ("us", "them"):
        raise MatchError("发球方只能是我方或对方。")
    if rotation not in range(1, 7):
        raise MatchError("轮次必须是 1 到 6。")
    if score_us < 0 or score_them < 0:
        raise MatchError("比分不能是负数。")
    if set(occupants_by_slot) != {1, 2, 3, 4, 5, 6}:
        raise MatchError("校正时六个槽位都要指定。")
    order = plan.base_order()
    if not order:
        raise MatchError("首发六个槽位还没排完。")
    from volleyball_coach.lineup import origins_for_rotation

    try:
        origins = origins_for_rotation(order, rotation)
    except PlanError as exc:
        raise MatchError(str(exc)) from exc
    overrides: dict[str, str] = {}
    for slot in range(1, 7):
        occupant = occupants_by_slot[slot]
        if occupant not in plan.players:
            raise MatchError("校正名单里有不在这支球队的人。")
        origin = origins[slot]
        if occupant != origin:
            if plan.rules.fixed_pair_subs and frozenset((origin, occupant)) not in state.locked_pairs:
                raise MatchError(
                    f"{plan.name_of(occupant)} 不能放进 {plan.name_of(origin)} 的槽位。"
                    "校正也不会替你跨配对。"
                )
            overrides[origin] = occupant
    if len(set(occupants_by_slot.values())) != 6:
        raise MatchError("校正后的六人有重复。")
    updated = _clone(state)
    updated.rotation = rotation
    updated.serving = serving
    updated.score_us = score_us
    updated.score_them = score_them
    updated.overrides = overrides
    updated.trusted = True
    updated.history_gap = True
    updated.score_tracked = True
    updated.sub_count_uncertain = True
    return refresh(plan, updated)


def apply_mode(state: MatchState, mode: str) -> MatchState:
    if mode not in ("plan", "light"):
        raise MatchError("模式只能是预案或轻记录。")
    updated = _clone(state)
    updated.mode = mode
    return updated


def replay(plan: TeamPlan, events: list[dict], locked_pairs: set[frozenset[str]], mode: str) -> tuple[MatchState | None, list[dict]]:
    """Replay the log. Undo drops the target event. Point rows are returned only when the chain was not later rewritten.

    A correction or manual rotation opens a history gap: earlier point rows stay available as raw log,
    but the returned point chain stops being a continuous rotation history.
    """
    undone = {
        event["payload"].get("target_seq")
        for event in events
        if event["type"] == "undo"
    }
    state: MatchState | None = None
    points: list[dict] = []
    current: list[dict] = []
    gap = False
    for event in events:
        if event["seq"] in undone or event["type"] == "undo":
            continue
        payload = event["payload"]
        if event["type"] == "set_start":
            if not gap:
                points.extend(current)
            current = []
            gap = False
            state = start_set(
                plan,
                rotation=int(payload["rotation"]),
                serving=payload["serving"],
                locked_pairs=locked_pairs,
                mode=payload.get("mode") or mode,
                set_index=int(payload.get("set_index") or 1),
                overrides=payload.get("overrides") or {},
            )
            continue
        if state is None:
            continue
        if event["type"] == "mode":
            state = apply_mode(state, payload["mode"])
            continue
        if event["type"] == "point":
            before_rotation = state.rotation
            before_serving = state.serving
            before_set = state.set_index
            state = apply_point(plan, state, payload["winner"])
            if not gap:
                current.append(
                    {
                        "kind": "point",
                        "seq": event["seq"],
                        "set_index": before_set,
                        "rotation": before_rotation,
                        "serving": before_serving,
                        "winner": payload["winner"],
                        "created_at": event.get("created_at"),
                    }
                )
            continue
        if event["type"] == "sub":
            state = apply_sub(plan, state, payload["out"], payload["in"])
            continue
        if event["type"] == "manual_rotation":
            state = apply_manual_rotation(plan, state, int(payload["rotation"]))
            gap = True
            current = []
            continue
        if event["type"] == "correct":
            occupants = {int(slot): player for slot, player in payload["occupants"].items()}
            state = apply_correction(
                plan,
                state,
                rotation=int(payload["rotation"]),
                serving=payload["serving"],
                occupants_by_slot=occupants,
                score_us=int(payload["score_us"]),
                score_them=int(payload["score_them"]),
            )
            gap = True
            current = []
            continue
    if not gap:
        points.extend(current)
    return state, points


def last_reversible_seq(events: list[dict]) -> int | None:
    undone = {
        event["payload"].get("target_seq")
        for event in events
        if event["type"] == "undo"
    }
    for event in reversed(events):
        if event["seq"] in undone or event["type"] not in REVERSIBLE:
            continue
        return event["seq"]
    return None
