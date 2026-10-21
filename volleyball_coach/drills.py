"""Acceptance drills from the coaching plan. They use the rules, not a scripted demo score."""

from __future__ import annotations

from volleyball_coach.lineup import build_card, build_suggestion, validate_pairs
from volleyball_coach.match import MatchError, apply_point, apply_sub, replay, start_set
from volleyball_coach.model import FRONT_SLOTS, Player, Rules, TeamPlan
from volleyball_coach.report import build_report, execution_of, question_receive, question_serve, question_subs
from volleyball_coach.seed import build_mens_plan, mens_locked_pairs


TABLE = {
    1: ["michael", "leo", "andy-a", "eric", "vitas", "andy-b"],
    2: ["leo", "andy-a", "eric", "vitas", "andy-b", "michael"],
    3: ["andy-a", "eric", "vitas", "andy-b", "michael", "leo"],
    4: ["eric", "vitas", "andy-b", "michael", "leo", "andy-a"],
    5: ["vitas", "andy-b", "michael", "leo", "andy-a", "eric"],
    6: ["andy-b", "michael", "leo", "andy-a", "eric", "vitas"],
}


def _line(state) -> list[str]:
    return [state.occupants[slot] for slot in range(1, 7)]


def _event(seq: int, event_type: str, **payload) -> dict:
    return {
        "seq": seq,
        "type": event_type,
        "payload": payload,
        "created_at": f"2026-10-19T18:{seq:02d}:00+00:00",
    }


def _check(name: str, fn) -> dict:
    try:
        detail = fn() or "通过"
        return {"name": name, "passed": True, "detail": detail}
    except Exception as exc:  # noqa: BLE001 — drills report the failure instead of crashing the page
        return {"name": name, "passed": False, "detail": f"{type(exc).__name__}: {exc}"}


def acceptance_drills() -> list[dict]:
    plan = build_mens_plan()
    locked = mens_locked_pairs(include_harvey=True)
    drills = [
        ("两个完整轮转循环都和六轮表一致", lambda: _cycles(plan, locked)),
        ("我方连续发球得分不轮转", lambda: _serve_streak(plan, locked)),
        ("对方连续发球得分，我方不轮转", lambda: _their_streak(plan, locked)),
        ("换人不改轮次，D 和 Andy A 可以反复换", lambda: _d_swaps(plan, locked)),
        ("Harvey 锁定 Michael 时不能换 Leo", lambda: _no_cross_pair(plan, locked)),
        ("Harvey 换下 Michael 之后，补位人不再是 Michael", lambda: _backup_leaves_with_michael(plan, locked)),
        ("Harvey 占着后排组织槽时，停止位置建议", lambda: _setter_conflict(plan, locked)),
        ("R6 的 Harvey 要在回到 R1 前换回 Michael", lambda: _harvey_return(plan, locked)),
        ("R5 的 D 要在进入 R6 前换回 Andy A", lambda: _d_return(plan, locked)),
        ("D 留在前排槽时停止位置建议", lambda: _d_in_front(plan, locked)),
        ("撤销得分后，轮次和比分回到上一个状态", lambda: _undo_point(plan, locked)),
        ("撤销换人后，人回到场上", lambda: _undo_sub(plan, locked)),
        ("校正只建立新状态，不反推漏掉的比分", lambda: _correction_gap(plan, locked)),
        ("R2 不把已经转到后排的 Leo 排进前排进攻", lambda: _r2_front(plan, locked)),
        ("R5 不把已经转到后排的 Vitas 排进前排进攻", lambda: _r5_front(plan, locked)),
        ("建议里不出现后排进攻", lambda: _no_backrow_attack(plan, locked)),
        ("一传未知不记成 0", lambda: _unknown_pass()),
        ("换人报告不把胜负差写成提升", lambda: _sub_report_does_not_overclaim()),
        ("没核对的发球目标不进执行率", lambda: _serve_unchecked()),
        ("只有关键片段时不判断哪一轮最难", lambda: _key_clips()),
        ("关掉再打开，重放事件日志得到同一状态", lambda: _reopen(plan, locked)),
        ("一个人不能同时锁两名替换对象", _two_partners),
        ("另一支球队不使用固定配对，也可以单独设换人上限", _other_team_cap),
        ("手动改轮次会带着替补走，并停用比分链", lambda: _manual_rotation(plan, locked)),
        ("轮转时 D 跟着 Andy A 的槽走", lambda: _d_rotates_with_slot(plan, locked)),
        ("对方轮次保持未知", lambda: _opponent_unknown(plan, locked)),
        ("Harvey 还是候选时，卡片写明窗口但不当成已经上场", lambda: _harvey_candidate_note(plan)),
    ]
    return [_check(name, fn) for name, fn in drills]


def _cycles(plan, locked) -> str:
    state = start_set(plan, rotation=1, serving="us", locked_pairs=locked, mode="light")
    if _line(state) != TABLE[1]:
        raise AssertionError(f"R1 开局是 {_line(state)}")
    rotation = 1
    for _ in range(12):
        state = apply_point(plan, state, "them")
        if state.rotation != rotation or state.serving != "them":
            raise AssertionError("丢发球权时轮次不该变")
        state = apply_point(plan, state, "us")
        rotation = 1 if rotation == 6 else rotation + 1
        if state.rotation != rotation or _line(state) != TABLE[rotation] or state.serving != "us":
            raise AssertionError(f"第 {rotation} 轮不一致：{_line(state)}")
    return "连续两次走完 R1 到 R6，槽位和表一致。"


def _serve_streak(plan, locked) -> str:
    state = start_set(plan, rotation=1, serving="us", locked_pairs=locked, mode="light")
    for _ in range(5):
        state = apply_point(plan, state, "us")
    if (state.rotation, state.score_us, state.score_them, state.occupants[1]) != (1, 5, 0, "michael"):
        raise AssertionError(f"连续得分后状态异常：R{state.rotation} {state.score_us}-{state.score_them}")
    return "我方 5 分，仍是 R1，Michael 继续发球。"


def _their_streak(plan, locked) -> str:
    state = start_set(plan, rotation=1, serving="them", locked_pairs=locked, mode="light")
    for _ in range(3):
        state = apply_point(plan, state, "them")
    if (state.rotation, state.score_us, state.score_them, state.serving) != (1, 0, 3, "them"):
        raise AssertionError("对方连续得分带动了我方轮转")
    return "对方 3 分，我方仍是 R1。"


def _d_swaps(plan, locked) -> str:
    state = start_set(plan, rotation=3, serving="us", locked_pairs=locked, mode="light")
    for _ in range(4):
        state = apply_sub(plan, state, "andy-a", "d")
        if state.rotation != 3 or state.occupants[1] != "d":
            raise AssertionError("D 上场后轮次或槽位错了")
        state = apply_sub(plan, state, "d", "andy-a")
        if state.occupants[1] != "andy-a":
            raise AssertionError("Andy A 没有换回来")
    if state.sub_count != 8:
        raise AssertionError(f"往返次数记成了 {state.sub_count}")
    return "D 与 Andy A 往返 4 次，轮次始终是 R3。"


def _no_cross_pair(plan, locked) -> str:
    state = start_set(plan, rotation=1, serving="us", locked_pairs=locked, mode="light")
    try:
        apply_sub(plan, state, "leo", "harvey")
    except MatchError as exc:
        if "跨配对" not in str(exc):
            raise
    else:
        raise AssertionError("跨配对换人没有被拦住")
    if _line(state) != TABLE[1]:
        raise AssertionError("被拒绝的换人改动了场上名单")
    unlocked = mens_locked_pairs(include_harvey=False)
    quiet = start_set(plan, rotation=4, serving="us", locked_pairs=unlocked, mode="light")
    try:
        apply_sub(plan, quiet, "michael", "harvey")
    except MatchError:
        pass
    else:
        raise AssertionError("没有锁定的 Harvey 仍然上了场")
    return "Harvey 只能替换本场锁定的那一个人。"


def _backup_leaves_with_michael(plan, locked) -> str:
    state = start_set(plan, rotation=4, serving="us", locked_pairs=locked, mode="light")
    state = apply_sub(plan, state, "michael", "harvey")
    card = build_card(plan, state.rotation, state.overrides, state.locked_pairs)
    if card.setter_id != "eric":
        raise AssertionError(f"组织者变成了 {card.setter_name}")
    if card.backup_id != "andy-b":
        raise AssertionError(f"补位人是 {card.backup_name}，Michael 已经不在场")
    if card.backup_id in {None, "michael", "harvey"}:
        raise AssertionError("补位人仍指向 Michael 或 Harvey")
    return "R4 由 Eric 组织，Andy B 候选补位，不是 Michael。"


def _setter_conflict(plan, locked) -> str:
    state = start_set(plan, rotation=1, serving="them", locked_pairs=locked, mode="light")
    state = apply_sub(plan, state, "michael", "harvey")
    suggestion = build_suggestion(plan, state)
    if not suggestion.blocked:
        raise AssertionError("组织冲突时仍给出了位置建议")
    if "停止按位置" not in suggestion.action:
        raise AssertionError(suggestion.action)
    return "Harvey 留在 R1 的组织槽，建议卡要求先校正。"


def _harvey_return(plan, locked) -> str:
    state = start_set(plan, rotation=6, serving="us", locked_pairs=locked, mode="light")
    state = apply_sub(plan, state, "michael", "harvey")
    suggestion = build_suggestion(plan, state)
    if suggestion.blocked:
        raise AssertionError("R6 前排窗口不应被当成名单冲突")
    if "换回 Michael" not in suggestion.switch:
        raise AssertionError(suggestion.switch)
    return "当前这一球照常指挥，切换条件写明回到 R1 前换回 Michael。"


def _d_return(plan, locked) -> str:
    state = start_set(plan, rotation=5, serving="them", locked_pairs=locked, mode="light")
    state = apply_sub(plan, state, "andy-a", "d")
    suggestion = build_suggestion(plan, state)
    if suggestion.blocked or "换回 Andy A" not in suggestion.switch:
        raise AssertionError(suggestion.switch)
    return "R5 可以继续打，进入 R6 前要换回 Andy A。"


def _d_in_front(plan, locked) -> str:
    state = start_set(plan, rotation=6, serving="us", locked_pairs=locked, mode="light")
    state = apply_sub(plan, state, "andy-a", "d")
    suggestion = build_suggestion(plan, state)
    if not suggestion.blocked or not any("前排" in item for item in state.conflicts):
        raise AssertionError(state.conflicts)
    return "D 占着 R6 的前排槽，位置建议停下。"


def _undo_point(plan, locked) -> str:
    events = [
        _event(1, "set_start", rotation=1, serving="them", set_index=1, mode="light"),
        _event(2, "point", winner="us"),
        _event(3, "undo", target_seq=2),
    ]
    state, points = replay(plan, events, locked, "light")
    if state is None or (state.rotation, state.score_us, state.serving) != (1, 0, "them"):
        raise AssertionError("撤销没有回到发球权转换之前")
    if points:
        raise AssertionError("被撤销的得分还留在比分链里")
    return "重放后仍是 R1，0 比 0，对方发球。"


def _undo_sub(plan, locked) -> str:
    events = [
        _event(1, "set_start", rotation=3, serving="us", set_index=1, mode="light"),
        _event(2, "sub", out="andy-a", **{"in": "d"}),
        _event(3, "undo", target_seq=2),
    ]
    state, _points = replay(plan, events, locked, "light")
    if state is None or state.occupants[1] != "andy-a" or state.overrides:
        raise AssertionError("撤销换人后 D 还在场上")
    return "撤销之后 Andy A 回到右后。"


def _correction_gap(plan, locked) -> str:
    occupants = {str(slot): player_id for slot, player_id in enumerate(TABLE[3], start=1)}
    events = [
        _event(1, "set_start", rotation=1, serving="us", set_index=1, mode="light"),
        _event(2, "point", winner="us"),
        _event(
            3,
            "correct",
            rotation=3,
            serving="them",
            score_us=8,
            score_them=6,
            occupants=occupants,
        ),
    ]
    state, points = replay(plan, events, locked, "light")
    if points:
        raise AssertionError("校正之后仍把漏掉的过程连成了比分链")
    if state is None or (state.rotation, state.score_us, state.score_them, state.serving) != (3, 8, 6, "them"):
        raise AssertionError("校正没有停在教练确认的状态")
    if not state.history_gap:
        raise AssertionError("校正应该留下历史缺口")
    return "直接停在 R3、8 比 6、对方发球，没有补造中间的分。"


def _assert_front(plan, locked, rotation: int, expected: list[str], absent: str) -> str:
    card = build_card(plan, rotation, {}, locked)
    names = [item["name"] for item in card.front_attack]
    ids = [item["player_id"] for item in card.front_attack]
    if absent in names or absent in ids:
        raise AssertionError(f"{absent} 仍在 R{rotation} 前排：{names}")
    if names != expected:
        raise AssertionError(f"R{rotation} 前排是 {names}")
    for item in card.front_attack:
        if item["slot"] not in FRONT_SLOTS:
            raise AssertionError("前排进攻用了后排槽")
    return "、".join(names)


def _r2_front(plan, locked) -> str:
    return _assert_front(plan, locked, 2, ["Vitas", "Andy A", "Eric"], "Leo")


def _r5_front(plan, locked) -> str:
    return _assert_front(plan, locked, 5, ["Leo", "Andy B", "Michael"], "Vitas")


def _no_backrow_attack(plan, locked) -> str:
    for rotation in range(1, 7):
        for serving in ("us", "them"):
            state = start_set(plan, rotation=rotation, serving=serving, locked_pairs=locked, mode="plan")
            suggestion = build_suggestion(plan, state)
            text = " ".join((suggestion.action, suggestion.alternative, suggestion.switch))
            if "后排进攻" in text or "后排攻击" in text:
                raise AssertionError(f"R{rotation} 的建议提到了后排进攻：{text}")
    return "六个轮次、两种发球权，建议都没有后排进攻。"


def _unknown_pass() -> str:
    rallies = [
        {
            "rotation": 1,
            "serving_side": "them",
            "winner": "us",
            "pass_quality": "unknown",
            "sample_scope": "complete",
            "server_label": "",
        },
        {
            "rotation": 1,
            "serving_side": "them",
            "winner": "them",
            "pass_quality": "in_system",
            "sample_scope": "complete",
            "server_label": "",
        },
    ]
    row = next(item for item in question_receive(rallies)["rows"] if item["rotation"] == 1)
    if row["pass_quality_recorded"] != 1 or row["pass_unknown"] != 1:
        raise AssertionError(f"未知被算进了质量分母：{row}")
    if row["wins"] != 1 or row["losses"] != 1:
        raise AssertionError("胜负次数不对")
    if row["pass_quality"]["unknown"] != 1:
        raise AssertionError("未知次数丢了")
    return "两次接发里，质量分母只有 1 个已确认的到位。"


def _sub_report_does_not_overclaim() -> str:
    rallies = []
    for quality, winner, bench in (
        ("in_system", "us", []),
        ("out", "them", ["Harvey"]),
    ):
        rallies.append(
            {
                "rotation": 4,
                "serving_side": "them",
                "winner": winner,
                "pass_quality": quality,
                "sample_scope": "complete",
                "server_label": "对手1号",
                "bench_ids": bench,
                "opponent": "A队",
            }
        )
    subs = question_subs(
        rallies,
        [{"at": "2026-10-19T18:10:00+00:00", "out": "Michael", "in": "Harvey", "rotation": 4, "set_index": 1}],
    )
    if not subs["stints"] or "不能和替补上场前直接比" not in subs["stints"][0]["reading"]:
        raise AssertionError(subs["stints"])
    report = build_report(rallies=rallies, events=[], points=[], history_gap=False)
    if "不能单独归因" not in report["subs"]["caution"]:
        raise AssertionError("报告少了换人归因的限制")
    return subs["stints"][0]["reading"]


def _serve_unchecked() -> str:
    rallies = [
        {
            "serving_side": "us",
            "target_type": "person",
            "target_label": "主攻",
            "actual_receiver": "主攻",
            "actual_zone": "",
            "winner": "us",
            "sample_scope": "complete",
            "pass_quality": "out",
            "rotation": 1,
        },
        {
            "serving_side": "us",
            "target_type": "person",
            "target_label": "主攻",
            "actual_receiver": "自由人",
            "actual_zone": "",
            "winner": "them",
            "sample_scope": "complete",
            "pass_quality": "in_system",
            "rotation": 1,
        },
        {
            "serving_side": "us",
            "target_type": "person",
            "target_label": "主攻",
            "actual_receiver": "",
            "actual_zone": "",
            "winner": "us",
            "sample_scope": "complete",
            "pass_quality": None,
            "rotation": 1,
        },
    ]
    if [execution_of(rally) for rally in rallies] != ["hit", "miss", "unchecked"]:
        raise AssertionError("执行状态分错了")
    result = question_serve(rallies)
    if (result["hits"], result["misses"], result["unchecked"], result["display"]) != (1, 1, 1, "1/2"):
        raise AssertionError(result)
    if result["rate"] is not None:
        raise AssertionError("样本不到 8 仍算出了百分比")
    return "三次里一次未核对，执行情况是 1/2。"


def _key_clips() -> str:
    rallies = [
        {
            "rotation": 2,
            "serving_side": "them",
            "winner": "them",
            "pass_quality": "out",
            "sample_scope": "key_clip",
        }
        for _ in range(6)
    ]
    result = question_receive(rallies)
    if "不能" not in result["headline"] or result["rows"] and any(row["decided"] for row in result["rows"]):
        raise AssertionError(result["headline"])
    return result["headline"]


def _reopen(plan, locked) -> str:
    events = [
        _event(1, "set_start", rotation=2, serving="us", set_index=1, mode="light"),
        _event(2, "point", winner="us"),
        _event(3, "point", winner="them"),
        _event(4, "point", winner="us"),
        _event(5, "sub", out="andy-a", **{"in": "d"}),
    ]
    first, first_points = replay(plan, events, locked, "light")
    second, second_points = replay(plan, list(events), locked, "light")
    if first is None or second is None:
        raise AssertionError("重放没有得到状态")
    if (first.rotation, first.score_us, first.score_them, first.occupants) != (
        second.rotation,
        second.score_us,
        second.score_them,
        second.occupants,
    ):
        raise AssertionError("两次重放结果不同")
    if first_points != second_points or first.rotation != 3:
        raise AssertionError("轮次没有按两次边线得分转到 R3")
    return f"重放两次都是 R{first.rotation}，{first.score_us}-{first.score_them}。"


def _two_partners() -> str:
    message = validate_pairs([("harvey", "michael"), ("harvey", "leo")])
    if not message or "两名" not in message:
        raise AssertionError(message)
    if validate_pairs([("andy-a", "d"), ("michael", "harvey")]) is not None:
        raise AssertionError("两对不重叠的配对被拒绝了")
    return "Harvey 不能同时对应 Michael 和 Leo。"


def _other_team_cap() -> str:
    players = {}
    roles = ["opposite", "outside", "middle", "opposite", "outside", "middle"]
    for index, role in enumerate(roles, start=1):
        players[f"p{index}"] = Player(
            id=f"p{index}",
            name=f"球员{index}",
            role=role,
            base_slot=index,
            sets_when="back_row" if role == "opposite" else "never",
        )
    players["bench"] = Player(id="bench", name="替补", role="other")
    plan = TeamPlan(
        team_id="other",
        name="另一支小队",
        rules=Rules(fixed_pair_subs=False, unlimited_subs=False, max_subs=2),
        players=players,
    )
    state = start_set(plan, rotation=1, serving="us", locked_pairs=set(), mode="light")
    state = apply_sub(plan, state, "p2", "bench")
    state = apply_sub(plan, state, "bench", "p2")
    try:
        apply_sub(plan, state, "p2", "bench")
    except MatchError as exc:
        if "上限" not in str(exc):
            raise
    else:
        raise AssertionError("第三次换人没有被上限拦住")
    open_rules = TeamPlan(
        team_id="other",
        name="另一支小队",
        rules=Rules(fixed_pair_subs=False, unlimited_subs=True, max_subs=None),
        players=players,
    )
    again = start_set(open_rules, rotation=1, serving="us", locked_pairs=set(), mode="light")
    again = apply_sub(open_rules, again, "p2", "bench")
    if again.occupants[2] != "bench":
        raise AssertionError("不设固定配对时，普通换人失败")
    return "这支球队没有固定配对；设了 2 次上限后，第三次换人被拦住。"


def _manual_rotation(plan, locked) -> str:
    events = [
        _event(1, "set_start", rotation=3, serving="us", set_index=1, mode="light"),
        _event(2, "point", winner="us"),
        _event(3, "sub", out="andy-a", **{"in": "d"}),
        _event(4, "manual_rotation", rotation=6),
    ]
    state, points = replay(plan, events, locked, "light")
    if points:
        raise AssertionError("手动改轮次之后还在用旧比分链做判断")
    if state is None or state.occupants.get(4) != "d" or state.score_tracked:
        raise AssertionError(f"D 没有跟着槽走到 R6：{None if state is None else _line(state)}")
    return "手动改到 R6 后，D 在 Andy A 的槽上，比分链停用。"


def _d_rotates_with_slot(plan, locked) -> str:
    state = start_set(plan, rotation=3, serving="us", locked_pairs=locked, mode="light")
    state = apply_sub(plan, state, "andy-a", "d")
    state = apply_point(plan, state, "them")
    state = apply_point(plan, state, "us")
    if state.rotation != 4 or state.occupants[6] != "d":
        raise AssertionError(f"R{state.rotation} 槽位是 {_line(state)}")
    return "边线得分进入 R4 后，D 在中后，仍然占着 Andy A 的槽。"


def _harvey_candidate_note(plan) -> str:
    confirmed = mens_locked_pairs(include_harvey=False)
    card = build_card(plan, 4, {}, confirmed)
    text = " ".join(card.extra_notes)
    if "Harvey" not in text or "还没锁定" not in text:
        raise AssertionError(text)
    if any(slot.occupant_id == "harvey" for slot in card.slots.values()):
        raise AssertionError("候选配对被写成了已经上场")
    return "R4 写明 Harvey 的窗口，人仍不在场上。"


def _opponent_unknown(plan, locked) -> str:
    state = start_set(plan, rotation=1, serving="them", locked_pairs=locked, mode="plan")
    suggestion = build_suggestion(plan, state)
    if "对方轮转" in suggestion.action or "对方阵容" in suggestion.action:
        raise AssertionError("建议编造了对方阵容")
    report = build_report(rallies=[], events=[], points=[], history_gap=False)
    if report["opponent_rotation"] is not None:
        raise AssertionError("对方轮次被填上了值")
    if state.serving != "them":
        raise AssertionError("发球方丢了")
    return "对方轮次是空的。没有输入，就不生成对方阵容。"
