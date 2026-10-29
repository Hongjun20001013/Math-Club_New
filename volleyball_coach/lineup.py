"""Rotation slots, duty cards, and the one suggestion the coach can actually call."""

from __future__ import annotations

from volleyball_coach.model import (
    BACK_SLOTS,
    FRONT_SLOTS,
    SLOT_GEO_WING,
    SLOT_NAME,
    WING_BY_ROLE,
    MatchState,
    Reminder,
    RotationCard,
    ServePlan,
    SlotView,
    Suggestion,
    TeamPlan,
)


class PlanError(ValueError):
    pass


def origins_for_rotation(order: list[str], rotation: int) -> dict[int, str]:
    if len(order) != 6:
        raise PlanError("需要六个首发槽位才能排轮转。")
    if rotation not in range(1, 7):
        raise PlanError("轮次必须是 1 到 6。")
    shift = rotation - 1
    return {slot: order[(slot - 1 + shift) % 6] for slot in range(1, 7)}


def next_rotation(rotation: int) -> int:
    if rotation not in range(1, 7):
        raise PlanError("轮次必须是 1 到 6。")
    return 1 if rotation == 6 else rotation + 1


def occupants_from(origins: dict[int, str], overrides: dict[str, str]) -> dict[int, str]:
    return {slot: overrides.get(origin, origin) for slot, origin in origins.items()}


def validate_pairs(pairs: list[tuple[str, str]]) -> str | None:
    """One player cannot be locked to two partners at the same time."""
    seen: dict[str, str] = {}
    for left, right in pairs:
        if not left or not right or left == right:
            return "配对的两个人必须是不同的球员。"
        for player in (left, right):
            other = right if player == left else left
            if player in seen and seen[player] != other:
                return "一个人不能同时对应两名替换对象。"
            seen[player] = other
    return None


def _pair_locked(locked: set[frozenset[str]], left: str, right: str) -> bool:
    return frozenset((left, right)) in locked


def project_lineup(
    plan: TeamPlan,
    rotation: int,
    overrides: dict[str, str],
    locked_pairs: set[frozenset[str]],
) -> tuple[dict[int, str], dict[int, str], list[str], list[str]]:
    order = plan.base_order()
    structural: list[str] = []
    tactical: list[str] = []
    if not order:
        return {}, {}, ["首发六个槽位还没排完，不能推算轮转。"], []
    if rotation not in range(1, 7):
        return {}, {}, ["轮次必须是 1 到 6。"], []
    for origin, occupant in overrides.items():
        if origin not in order:
            structural.append(f"{plan.name_of(origin)} 不在首发轮转里，不能占一个槽。")
        if occupant not in plan.players:
            structural.append(f"{occupant} 不在这支球队的名单里。")
    origins = origins_for_rotation(order, rotation)
    occupants = occupants_from(origins, overrides)
    values = list(occupants.values())
    if len(values) != len(set(values)):
        structural.append("场上有重复球员，名单不能用。")
    if plan.rules.fixed_pair_subs:
        for slot, origin in origins.items():
            occupant = occupants[slot]
            if occupant != origin and not _pair_locked(locked_pairs, origin, occupant):
                structural.append(
                    f"{plan.name_of(occupant)} 占着 {plan.name_of(origin)} 的轮转槽，"
                    "但这不是本场锁定的固定配对。"
                )
    else:
        for occupant in occupants.values():
            if occupant not in plan.players:
                structural.append(f"{occupant} 不在名单里。")
    if structural:
        return origins, occupants, structural, tactical

    designated: list[tuple[int, str]] = []
    for slot, origin in origins.items():
        player = plan.players[origin]
        if player.sets_when == "always" or (player.sets_when == "back_row" and slot in BACK_SLOTS):
            designated.append((slot, origin))
    if len(designated) != 1:
        tactical.append("组织者不唯一，或者这一轮没有人负责组织。先不要按位置指挥。")
    else:
        slot, origin = designated[0]
        occupant = occupants[slot]
        if occupant != origin:
            occupier = plan.players.get(occupant)
            if occupier and occupier.setting_verified and occupier.sets_when != "never":
                pass
            else:
                tactical.append(
                    f"{plan.name_of(occupant)} 占着 {plan.name_of(origin)} 的组织槽位，"
                    "但二传能力尚未验证。不能默认由替补组织。"
                )

    for slot, occupant in occupants.items():
        player = plan.players.get(occupant)
        if player and player.role == "defender" and slot in FRONT_SLOTS:
            tactical.append(
                f"{player.name} 是防守替补，现在占着前排槽位。"
                "按当前计划只在后排使用，请换回前排球员。"
            )

    wings: list[str] = []
    for slot in FRONT_SLOTS:
        origin = origins[slot]
        wing = WING_BY_ROLE.get(plan.players[origin].role)
        if wing:
            wings.append(wing)
    if len(wings) != len(set(wings)):
        tactical.append("前排有两个人被排进同一条进攻线。先改职责，再指挥。")
    return origins, occupants, structural, tactical


def _slot_of(mapping: dict[int, str], player_id: str) -> int | None:
    for slot, occupant in mapping.items():
        if occupant == player_id:
            return slot
    return None


def _origin_slot(origins: dict[int, str], player_id: str) -> int | None:
    for slot, origin in origins.items():
        if origin == player_id:
            return slot
    return None


def choose_setter(plan: TeamPlan, origins: dict[int, str], occupants: dict[int, str]) -> tuple[str | None, str]:
    designated: list[tuple[int, str]] = []
    for slot, origin in origins.items():
        player = plan.players[origin]
        if player.sets_when == "always" or (player.sets_when == "back_row" and slot in BACK_SLOTS):
            designated.append((slot, origin))
    if len(designated) != 1:
        return None, "这一轮组织者不明确。"
    slot, origin = designated[0]
    occupant = occupants[slot]
    if occupant != origin:
        occupier = plan.players.get(occupant)
        if occupier and occupier.setting_verified and occupier.sets_when != "never":
            note = "替补的二传能力已由教练标记为验证过。"
            if not occupier.setting_verified:
                note = ""
            return occupant, note
        return None, (
            f"{plan.name_of(occupant)} 占着 {plan.name_of(origin)} 的组织槽位，"
            "二传能力尚未验证。"
        )
    note = ""
    if not plan.players[occupant].setting_verified:
        note = "二传能力尚未验证。这是职责安排，不是能力评价。"
    return occupant, note


def choose_backup(
    plan: TeamPlan,
    occupants: dict[int, str],
    setter_id: str | None,
) -> tuple[str | None, str]:
    on_court = list(occupants.values())

    def slot_rank(player_id: str, prefer_front: bool) -> tuple[int, str]:
        slot = _slot_of(occupants, player_id)
        front = slot in FRONT_SLOTS
        return (0 if front == prefer_front else 1, plan.name_of(player_id))

    planned = []
    for player_id in on_court:
        if player_id == setter_id:
            continue
        player = plan.players[player_id]
        if player.sets_when in ("back_row", "always"):
            planned.append(player_id)
    if planned:
        planned.sort(key=lambda player_id: slot_rank(player_id, prefer_front=True))
        chosen = planned[0]
        return chosen, f"{plan.name_of(chosen)} 在场，第一球防起后由他补位传球。"

    backups = []
    for player_id in on_court:
        if player_id == setter_id:
            continue
        player = plan.players[player_id]
        if player.can_backup_set:
            backups.append(player)
    if backups:
        backups.sort(key=lambda player: (player.backup_rank, player.name))
        chosen = backups[0]
        return chosen.id, (
            f"原定的另一名二传不在场。现在由在场的 {chosen.name} 候选补位，"
            "这还没有被验证成固定职责。"
        )
    return None, "场上没有可指定的补位传球人。死球时要明确谁喊「我传」。"


def choose_receivers(plan: TeamPlan, occupants: dict[int, str], setter_id: str | None) -> tuple[list[dict], list[str]]:
    people = []
    for slot, player_id in occupants.items():
        player = plan.players[player_id]
        if not player.receive_primary or player_id == setter_id:
            continue
        front = slot in FRONT_SLOTS
        people.append(
            {
                "id": player_id,
                "name": player.name,
                "slot": slot,
                "row": "前排" if front else "后排",
                "role": player.role,
                "note": "前排接发，需要留下助跑路线。" if front else "后排接发。",
            }
        )
    backs = [item for item in people if item["row"] == "后排"]
    fronts = [item for item in people if item["row"] == "前排"]
    fronts.sort(key=lambda item: (0 if item["role"] == "outside" else 1, item["slot"]))
    chosen = backs[:3]
    for item in fronts:
        if len(chosen) >= 3:
            break
        chosen.append(item)
    chosen_ids = {item["id"] for item in chosen}
    extra = [item["name"] for item in people if item["id"] not in chosen_ids]
    return chosen, extra


def build_reminders(
    plan: TeamPlan,
    rotation: int,
    origins: dict[int, str],
    occupants: dict[int, str],
    locked_pairs: set[frozenset[str]],
) -> list[Reminder]:
    if not origins:
        return []
    upcoming = next_rotation(rotation)
    reminders: list[Reminder] = []
    for window in plan.sub_windows:
        if not _pair_locked(locked_pairs, window.player_out, window.player_in):
            continue
        slot = _origin_slot(origins, window.player_out)
        if slot is None:
            continue
        in_now = occupants[slot] == window.player_in
        active_now = rotation in window.active_rotations
        active_next = upcoming in window.active_rotations
        out_name = plan.name_of(window.player_out)
        in_name = plan.name_of(window.player_in)
        if in_now and active_now and not active_next:
            reminders.append(
                Reminder(
                    f"下一次轮转到 R{upcoming} 前，换回 {out_name}。现在场上仍是 {in_name}。",
                    urgent=True,
                )
            )
        elif (not in_now) and (not active_now) and active_next:
            reminders.append(
                Reminder(
                    f"下一轮是 R{upcoming}。如果要让 {in_name} 换 {out_name}，在这次死球确认。"
                    "轮次到了，不等于人已经换完。",
                    urgent=False,
                )
            )
        elif (not in_now) and active_now:
            reminders.append(
                Reminder(
                    f"本轮计划是 {in_name} 替换 {out_name}，但 {out_name} 仍在场。换不换由你确认。",
                    urgent=False,
                )
            )
    reminders.sort(key=lambda item: (not item.urgent, item.text))
    return reminders


def build_card(
    plan: TeamPlan,
    rotation: int,
    overrides: dict[str, str] | None = None,
    locked_pairs: set[frozenset[str]] | None = None,
) -> RotationCard:
    overrides = dict(overrides or {})
    locked = set(locked_pairs or [])
    origins, occupants, structural, tactical = project_lineup(plan, rotation, overrides, locked)
    conflicts = structural + tactical
    empty_serve = plan.serve_plans.get(rotation) or ServePlan(rotation=rotation)
    if not origins:
        return RotationCard(
            rotation=rotation,
            setter_id=None,
            setter_name="未指定",
            setter_note="",
            backup_id=None,
            backup_name="未指定",
            backup_note="",
            front_attack=[],
            receivers=[],
            seam="轮转还没排完。",
            short_ball="",
            position_note="",
            movement_serve="",
            movement_receive="",
            reminders=[],
            extra_notes=[],
            serve=empty_serve,
            slots={},
            conflicts=conflicts,
            structural=structural,
        )

    setter_id, setter_note = choose_setter(plan, origins, occupants)
    backup_id, backup_note = choose_backup(plan, occupants, setter_id)
    receivers, extra = choose_receivers(plan, occupants, setter_id)
    setter_name = plan.name_of(setter_id) if setter_id else "未指定"
    backup_name = plan.name_of(backup_id) if backup_id else "未指定"

    front_attack = []
    slots: dict[int, SlotView] = {}
    setter_slot = _slot_of(occupants, setter_id) if setter_id else None
    for slot in range(1, 7):
        origin = origins[slot]
        occupant = occupants[slot]
        origin_player = plan.players[origin]
        wing = ""
        wing_note = ""
        if slot in FRONT_SLOTS:
            wing = WING_BY_ROLE.get(origin_player.role, "")
            if wing:
                geo = SLOT_GEO_WING[slot]
                if occupant != origin:
                    wing_note = f"{plan.name_of(occupant)} 执行 {origin_player.name} 的{wing}职责。"
                if wing != geo:
                    switch = f"轮转槽在{SLOT_NAME[slot]}，发球后换到{wing}。"
                    wing_note = f"{wing_note} {switch}".strip()
                front_attack.append(
                    {
                        "wing": wing,
                        "slot": slot,
                        "player_id": occupant,
                        "name": plan.name_of(occupant),
                        "note": wing_note,
                    }
                )
        badges = []
        if slot == setter_slot:
            badges.append("主二传")
        if backup_id and occupant == backup_id:
            badges.append("补位传球")
        if any(item["id"] == occupant for item in receivers):
            badges.append("主接发")
        if occupant != origin:
            badges.append("替补")
        slots[slot] = SlotView(
            slot=slot,
            slot_name=SLOT_NAME[slot],
            row="前排" if slot in FRONT_SLOTS else "后排",
            origin_id=origin,
            occupant_id=occupant,
            origin_name=origin_player.name,
            occupant_name=plan.name_of(occupant),
            is_sub=occupant != origin,
            wing=wing,
            wing_note=wing_note,
            badges=badges,
        )

    wing_order = {"左翼": 0, "中路": 1, "右翼": 2}
    front_attack.sort(key=lambda item: wing_order.get(item["wing"], 9))

    back_receivers = [item for item in receivers if item["row"] == "后排"]
    seam_pool = back_receivers[:2] if len(back_receivers) >= 2 else receivers[:2]
    if len(seam_pool) >= 2:
        seam = f"{seam_pool[0]['name']} 与 {seam_pool[1]['name']}"
    elif seam_pool:
        seam = f"目前只有 {seam_pool[0]['name']}，结合部要当场再指定一个人。"
    else:
        seam = "在场的主接发不足，结合部要当场指定。"

    front_receivers = [item for item in receivers if item["row"] == "前排"]
    short_owner = front_receivers[0]["name"] if front_receivers else (receivers[0]["name"] if receivers else "当场指定")
    short_ball = f"短球候选是 {short_owner}，不要默认交给 {setter_name}。"

    if plan.rules.overlap_confirmed:
        position_note = "教练已标记重叠规则确认过。系统里仍然没有坐标图，场上以教练画的站位图为准。"
    else:
        position_note = (
            "发球和接发的实际站位、移动路线还不能定稿。"
            "本地重叠规则确认之前，这张卡只规定职责，不规定谁站在哪个坐标。"
        )

    attack_text = "、".join(f"{item['name']}{item['wing']}" for item in front_attack) or "前排职责未排"
    server_name = slots[1].occupant_name
    movement_serve = (
        f"{server_name} 从右后发球。发球后前排换到：{attack_text}。"
        "后排按这一轮的拦防收。具体落位不是这张轮转表。"
    )
    receiver_names = "、".join(item["name"] for item in receivers) or "未指定"
    movement_receive = (
        f"主接发是 {receiver_names}。{setter_name} 少接结合部和短球，接起来以后组织。"
        f"{backup_name} 准备在主二传碰到第一球时喊「我传」。"
    )

    extra_notes = []
    if extra:
        extra_notes.append("这一轮不默认扩进主接发：" + "、".join(extra) + "。")
    for player_id in occupants.values():
        player = plan.players[player_id]
        if player.role == "flex" and not player.receive_primary:
            extra_notes.append(f"{player.name} 在场，接发尚未验证，不自动算进主接发。")
    if plan.rules.no_back_row_attack:
        extra_notes.append("本队不使用后排进攻。前排名单以外的人，不能拿来补进攻点。")
    if not plan.rules.no_libero:
        extra_notes.append("这支球队没有关闭自由人。本版不会自动换自由人，每次上下都要手动确认。")
    upcoming = next_rotation(rotation)
    for window in plan.sub_windows:
        if _pair_locked(locked, window.player_out, window.player_in):
            continue
        if rotation not in window.active_rotations and upcoming not in window.active_rotations:
            continue
        status = next((pair.status for pair in plan.pairs if pair.matches(window.player_out, window.player_in)), "未建立")
        label = "候选，还没锁定" if status == "candidate" else "还没锁定"
        rounds = "、".join(f"R{number}" for number in window.active_rotations)
        extra_notes.append(
            f"{label}：{plan.name_of(window.player_in)} 换 {plan.name_of(window.player_out)} 的计划窗口是 {rounds}。"
            "窗口到了，也不等于人已经上场。"
        )

    reminders = build_reminders(plan, rotation, origins, occupants, locked)
    return RotationCard(
        rotation=rotation,
        setter_id=setter_id,
        setter_name=setter_name,
        setter_note=setter_note,
        backup_id=backup_id,
        backup_name=backup_name,
        backup_note=backup_note,
        front_attack=front_attack,
        receivers=receivers,
        seam=seam,
        short_ball=short_ball,
        position_note=position_note,
        movement_serve=movement_serve,
        movement_receive=movement_receive,
        reminders=reminders,
        extra_notes=extra_notes,
        serve=empty_serve,
        slots=slots,
        conflicts=conflicts,
        structural=structural,
    )


def confidence_text(sample_size: int) -> str:
    if sample_size <= 0:
        return "无统计依据。这是赛前预案，不是算出来的最优解。"
    if sample_size < 8:
        return f"本场已确认样本 {sample_size} 个，不够用来比较胜率。"
    return f"本场已确认样本 {sample_size} 个。只说明已经看到的情况，不是这条战术的因果收益。"


def build_suggestion(plan: TeamPlan, state: MatchState, sample_size: int = 0) -> Suggestion:
    card = build_card(plan, state.rotation, state.overrides, state.locked_pairs)
    server = card.slots[1].occupant_name if card.slots else "发球队员"
    serving_text = "我方发球" if state.serving == "us" else "对方发球" if state.serving == "them" else "发球方未知"
    situation = f"R{state.rotation}，{serving_text}，组织：{card.setter_name}。"
    if state.advice_blocked:
        basis = "；".join(state.conflicts) if state.conflicts else "当前状态还没确认。"
        alternative = "赛前预案还在，但不能把它当成已经完成的换人。"
        urgent = [item.text for item in card.reminders if item.urgent]
        if urgent:
            alternative = urgent[0]
        return Suggestion(
            situation=situation,
            action="停止按位置指挥。死球时确认发球队员、组织者和场上六人，再继续。",
            basis=basis,
            confidence="不适用。名单冲突时不给位置建议。",
            alternative=alternative,
            switch="冲突消失以后，再调用这一轮的发球或接发任务。",
            source="prematch_plan",
            blocked=True,
        )

    if state.serving == "us":
        serve = card.serve
        if serve.target_type == "unset" or not serve.target_label.strip():
            action = f"{server} 发球。这一轮没有已确认的追发目标，用基础预案，不要临时编一个目标。"
            basis = serve.evidence or "暂无对手证据"
        else:
            kind = "人" if serve.target_type == "person" else "区域"
            backup = serve.backup_label.strip() or "这个发球队员最稳的落点"
            action = f"{server} 追{kind}：{serve.target_label}。执行不到就改{backup}。"
            basis = serve.evidence or "赛前预案"
        alternative = serve.block_note.strip() or "如果没有破坏一传，拦防回到到位球，不要还按高球来守。"
        switch = "对方换了接发人，或站位明显变了，就停用这个目标。"
    else:
        action = f"接发看结合部：{card.seam}。短球不要给 {card.setter_name}。"
        basis = "赛前职责。轮转槽位不是发球或接发时的实际站位。"
        calls = plan.calls
        if card.backup_id:
            backup_sentence = f"{card.setter_name} 组织，{card.backup_name} 补第一球。"
        else:
            backup_sentence = card.backup_note
        alternative = (
            f"到位喊「{calls.get('in_system', '全开')}」，半到位喊「{calls.get('half', '两翼')}」，"
            f"不到位喊「{calls.get('out', '高球')}」。口令不是固定传给某一个人。{backup_sentence}"
        )
        switch = "连续组织混乱时，先核对责任和路线，再只留两种练熟的球。这是在收执行难度。"

    if card.reminders:
        switch = card.reminders[0].text + " " + switch
    return Suggestion(
        situation=situation,
        action=action,
        basis=basis,
        confidence=confidence_text(sample_size),
        alternative=alternative,
        switch=switch,
        source="prematch_plan",
        blocked=False,
    )


def legal_sub_options(plan: TeamPlan, state: MatchState) -> list[tuple[str, str]]:
    """Pairs the coach is allowed to confirm. Illegal crosses are absent, not merely discouraged."""
    on_court = set(state.occupants.values())
    options: list[tuple[str, str]] = []
    if plan.rules.fixed_pair_subs:
        for left, right in sorted((tuple(sorted(pair)) for pair in state.locked_pairs)):
            if left in on_court and right not in on_court:
                options.append((left, right))
            elif right in on_court and left not in on_court:
                options.append((right, left))
        return options
    bench = [player.id for player in plan.players.values() if player.id not in on_court]
    for occupant in on_court:
        for incoming in bench:
            options.append((occupant, incoming))
    return options
