"""Three coaching questions. Counts stay counts; missing data stays missing."""

from __future__ import annotations

from volleyball_coach.model import ATTACK_RESULT, BLOCK_TOUCH, DEFENSE_QUALITY, PASS_QUALITY, SEVERE_ERROR, SEVERE_KIND


CAUTION = (
    "对手、发球队员和一传质量可能同时变化。"
    "这里只列出实际阵容、换人时间和可比条件下的完整回合，不能单独归因于这次换人。"
)

OVERCLAIM_PHRASES = (
    "上场后胜率更高",
    "胜率更高",
    "换人带来了提升",
    "因此建议继续换",
)


def _norm(value: str | None) -> str:
    return (value or "").strip().casefold()


def execution_of(rally: dict) -> str:
    """hit, miss, unchecked, or no_target. Unchecked is not a miss and not a zero."""
    if not (rally.get("target_label") or "").strip():
        return "no_target"
    person = _norm(rally.get("actual_receiver"))
    zone = _norm(rally.get("actual_zone"))
    target = _norm(rally.get("target_label"))
    if rally.get("target_type") == "zone":
        if not zone:
            return "unchecked"
        return "hit" if zone == target else "miss"
    if not person:
        return "unchecked"
    return "hit" if person == target else "miss"


def _known_result(rally: dict) -> bool:
    return rally.get("winner") in ("us", "them")


def _in_rates(rally: dict) -> bool:
    return rally.get("sample_scope") in ("complete", "sample")


def _rate_pair(wins: int, losses: int) -> dict:
    decided = wins + losses
    return {
        "wins": wins,
        "losses": losses,
        "decided": decided,
        "rate": None if decided < 8 else wins / decided,
        "display": "—" if decided == 0 else f"{wins}/{decided}",
    }


def question_receive(rallies: list[dict]) -> dict:
    receiving = [rally for rally in rallies if rally.get("serving_side") == "them"]
    usable = [rally for rally in receiving if _in_rates(rally)]
    clips = [rally for rally in receiving if rally.get("sample_scope") == "key_clip"]
    rows = []
    for rotation in list(range(1, 7)) + [None]:
        if rotation is not None:
            group = [rally for rally in usable if rally.get("rotation") == rotation]
        else:
            group = [rally for rally in usable if rally.get("rotation") in (None, "")]
        if not group and rotation is None:
            continue
        wins = sum(1 for rally in group if rally.get("winner") == "us")
        losses = sum(1 for rally in group if rally.get("winner") == "them")
        unknown_winner = sum(1 for rally in group if rally.get("winner") == "unknown")
        qualities = {key: 0 for key in PASS_QUALITY}
        recorded_quality = 0
        for rally in group:
            quality = rally.get("pass_quality")
            if quality in PASS_QUALITY:
                qualities[quality] += 1
                if quality != "unknown":
                    recorded_quality += 1
        servers: dict[str, int] = {}
        for rally in group:
            label = (rally.get("server_label") or "").strip()
            if label:
                servers[label] = servers.get(label, 0) + 1
        pair = _rate_pair(wins, losses)
        rows.append(
            {
                "rotation": rotation,
                "label": "轮次未知" if rotation is None else f"R{rotation}",
                "recorded": len(group),
                "unknown_winner": unknown_winner,
                "pass_quality": qualities,
                "pass_quality_recorded": recorded_quality,
                "pass_unknown": qualities["unknown"],
                "servers": servers,
                **pair,
            }
        )
    decided_total = sum(row["decided"] for row in rows)
    headline = "还没有接发回合记录。"
    if clips and not usable:
        headline = "目前只有关键片段。这些片段不能用来判断哪一轮接发最难，也不能计算整场得分率。"
    elif decided_total == 0 and usable:
        headline = "接发回合还没有分出胜负，或者胜方标了未知。未知不计入胜负。"
    elif 0 < decided_total < 8:
        headline = "样本不足。下面是次数，不排名，也不把某一轮说成最难。"
    elif decided_total >= 8:
        ranked = [row for row in rows if row["rotation"] is not None and row["decided"] > 0]
        if len(ranked) >= 2:
            top = max(ranked, key=lambda row: (row["losses"], row["decided"]))
            others = [row["losses"] for row in ranked if row is not top]
            gap = top["losses"] - max(others)
            if top["losses"] >= 3 and gap >= 3 and top["decided"] >= 5:
                headline = (
                    f"记录里接发失分次数最多的是 {top['label']}："
                    f"{top['losses']} 次失分 / {top['decided']} 个已分胜负的接发回合。"
                    "这是描述，不是原因。"
                )
            else:
                headline = "各轮差距还不够清楚。先看表，不指定最难的一轮。"
        else:
            headline = "能比较的轮次还不够。先看表，不指定最难的一轮。"
    scope = "complete"
    scopes = {rally.get("sample_scope") for rally in usable}
    if scopes == {"sample"} or scopes == {"complete", "sample"}:
        scope = "sample"
    if clips:
        scope = "mixed_clips" if usable else "key_clip"
    return {
        "headline": headline,
        "rows": [row for row in rows if row["rotation"] is not None or row["recorded"]],
        "key_clip_count": len(clips),
        "scope": scope,
        "note": "分母只含已分胜负的接发回合。一传未知不进质量比例，也不记成 0。关键片段不进这张表。",
    }


def question_serve(rallies: list[dict]) -> dict:
    ours = [rally for rally in rallies if rally.get("serving_side") == "us" and _in_rates(rally)]
    targeted = [rally for rally in ours if (rally.get("target_label") or "").strip()]
    rows = []
    hits = misses = unchecked = 0
    for rally in targeted:
        status = execution_of(rally)
        if status == "hit":
            hits += 1
        elif status == "miss":
            misses += 1
        elif status == "unchecked":
            unchecked += 1
        quality = rally.get("pass_quality")
        rows.append(
            {
                "rotation": rally.get("rotation"),
                "target_type": rally.get("target_type") or "person",
                "target_label": rally.get("target_label") or "",
                "actual_receiver": rally.get("actual_receiver") or None,
                "actual_zone": rally.get("actual_zone") or None,
                "execution": status,
                "pass_quality": PASS_QUALITY.get(quality) if quality else None,
                "winner": rally.get("winner"),
            }
        )
    checked = hits + misses
    if not targeted:
        headline = "发球目标还没记。没有记录，就不能说执行到了，也不能说没执行。"
    else:
        headline = (
            f"已核对 {checked} 次，执行到 {hits} 次，未执行到 {misses} 次，未核对 {unchecked} 次。"
            "未核对的不放进执行率，也不当成没执行。"
        )
    return {
        "headline": headline,
        "rows": rows,
        "hits": hits,
        "misses": misses,
        "unchecked": unchecked,
        "rate": None if checked < 8 else hits / checked,
        "display": "—" if checked == 0 else f"{hits}/{checked}",
    }


def _qualities(rows: list[dict]) -> set[str]:
    return {
        rally["pass_quality"]
        for rally in rows
        if rally.get("pass_quality") and rally["pass_quality"] != "unknown"
    }


def _labels(rows: list[dict], key: str) -> set[str]:
    return {(rally.get(key) or "").strip() for rally in rows if (rally.get(key) or "").strip()}


def question_subs(rallies: list[dict], sub_events: list[dict], opponent: str = "") -> dict:
    usable = [rally for rally in rallies if _in_rates(rally)]
    groups: dict[tuple[str, ...], list[dict]] = {}
    for rally in usable:
        bench = tuple(sorted(rally.get("bench_ids") or []))
        groups.setdefault(bench, []).append(rally)
    base = groups.get(tuple(), [])
    stints = []
    for bench, rows in groups.items():
        if not bench:
            continue
        same_rotation = {rally.get("rotation") for rally in base} & {rally.get("rotation") for rally in rows}
        reasons: list[str] = []
        compared_base: list[dict] = []
        compared_rows: list[dict] = []
        if not base:
            reasons.append("没有替补上场前的回合")
        elif not same_rotation:
            reasons.append("轮次没有重合")
        else:
            compared_base = [rally for rally in base if rally.get("rotation") in same_rotation]
            compared_rows = [rally for rally in rows if rally.get("rotation") in same_rotation]
            if _labels(compared_base, "serving_side") != _labels(compared_rows, "serving_side"):
                reasons.append("发球方构成不同")
            base_quality = _qualities(compared_base)
            row_quality = _qualities(compared_rows)
            if base_quality and row_quality and base_quality != row_quality:
                reasons.append("一传质量不同")
            elif bool(base_quality) != bool(row_quality):
                reasons.append("一边没有一传质量，没法对齐条件")
            base_servers = _labels(compared_base, "server_label")
            row_servers = _labels(compared_rows, "server_label")
            if base_servers and row_servers and base_servers != row_servers:
                reasons.append("发球队员不同")
            elif bool(base_servers) != bool(row_servers):
                reasons.append("发球队员记录不齐")
            if opponent and any((rally.get("opponent") or opponent) != opponent for rally in compared_rows):
                reasons.append("对手不同")
        decided = [rally for rally in rows if _known_result(rally)]
        wins = sum(1 for rally in decided if rally["winner"] == "us")
        losses = sum(1 for rally in decided if rally["winner"] == "them")
        comparable = not reasons and len(decided) > 0
        if not comparable:
            reading = "条件对不齐（" + "、".join(reasons) + "）。不能和替补上场前直接比胜负。"
        elif len(decided) < 8:
            reading = (
                f"条件接近，但样本只有 {len(decided)} 个已分胜负的回合。"
                "只能把胜负列出来，还不能回答具体改善了什么。"
            )
        else:
            reading = (
                f"条件接近的回合里，胜 {wins}、负 {losses}。"
                "这仍是观察关联，不能单独归因于这次换人，也还不能回答具体改善了什么。"
            )
        stints.append(
            {
                "bench": list(bench),
                "rotations": sorted({rally.get("rotation") for rally in rows if rally.get("rotation")}),
                "rallies": len(rows),
                "wins": wins,
                "losses": losses,
                "comparable": comparable,
                "reasons": reasons,
                "reading": reading,
            }
        )
    if not sub_events and not stints:
        headline = "这场记录里还没有替补上场。"
    elif not stints:
        headline = "有换人操作，但还没有带阵容的回合记录。先不要从比分差读出改善。"
    else:
        headline = "下面按实际在场的替补拆开。没有可比条件的，不放在一起比。"
    return {
        "headline": headline,
        "caution": CAUTION,
        "events": sub_events,
        "stints": stints,
    }


def burden(events: list[dict]) -> dict:
    kinds = [event for event in events if event["type"] != "undo"]
    undos = [event for event in events if event["type"] == "undo"]
    corrections = [event for event in events if event["type"] == "correct"]
    manual = [event for event in events if event["type"] == "manual_rotation"]
    stamps = [event.get("created_at") for event in events if event.get("created_at")]
    return {
        "operations": len([event for event in events if event["type"] in {"point", "sub", "correct", "manual_rotation", "bookmark"}]),
        "undos": len(undos),
        "corrections": len(corrections),
        "manual_rotations": len(manual),
        "started_at": stamps[0] if stamps else None,
        "ended_at": stamps[-1] if stamps else None,
        "note": "起止时间只说明这些操作跨了多久。它不是已经验证过的 20 分钟复盘，也不是漏记次数本身。校正次数说明比分链被打断过。",
        "event_count": len(kinds),
    }


def sideout_summary(points: list[dict], history_gap: bool) -> dict:
    if history_gap or not points:
        return {
            "usable": False,
            "headline": "比分链断过，或者还没有连续的场边比分。不用它推断哪一轮难。",
            "rows": [],
        }
    rows = []
    for rotation in range(1, 7):
        group = [point for point in points if point.get("rotation") == rotation]
        if not group:
            continue
        rows.append(
            {
                "rotation": rotation,
                "us": sum(1 for point in group if point["winner"] == "us"),
                "them": sum(1 for point in group if point["winner"] == "them"),
                "served": sum(1 for point in group if point["serving"] == "us"),
                "received": sum(1 for point in group if point["serving"] == "them"),
            }
        )
    return {
        "usable": True,
        "headline": "这只是场边按钮的比分流水，没有一传质量，不能回答接发难不难。",
        "rows": rows,
    }


def _ratio(numerator: int, denominator: int) -> dict:
    ready = denominator >= 8
    return {
        "num": numerator,
        "den": denominator,
        "rate": None if not ready else numerator / denominator,
        "percent": None if not ready else f"{round(100 * numerator / denominator)}%",
        "display": "—" if denominator == 0 else f"{numerator}/{denominator}",
        "ready": ready,
    }


def _filled(rally: dict, field: str) -> str:
    return (rally.get(field) or "").strip()


def skill_summary(rallies: list[dict]) -> dict:
    """Per-skill counts. Unknown, blank, and key clips stay out of every rate."""
    usable = [rally for rally in rallies if _in_rates(rally)]
    clips = [rally for rally in rallies if rally.get("sample_scope") == "key_clip"]

    def buckets(field: str, labels: dict) -> dict[str, int]:
        counts = {key: 0 for key in labels}
        for rally in usable:
            value = _filled(rally, field)
            if value in counts:
                counts[value] += 1
        return counts

    passing = buckets("pass_quality", PASS_QUALITY)
    blocking = buckets("block_touch", BLOCK_TOUCH)
    defense = buckets("defense_quality", DEFENSE_QUALITY)
    attack = buckets("attack_result", ATTACK_RESULT)
    severe = buckets("severe_error", SEVERE_ERROR)
    kinds: dict[str, int] = {}
    for rally in usable:
        if _filled(rally, "severe_error") != "yes":
            continue
        kind = _filled(rally, "severe_kind")
        if kind in SEVERE_KIND:
            kinds[kind] = kinds.get(kind, 0) + 1

    pass_ratio = _ratio(
        passing["in_system"],
        passing["in_system"] + passing["half"] + passing["out"],
    )
    defense_ratio = _ratio(defense["in_system"], defense["in_system"] + defense["out"])
    attack_ratio = _ratio(
        attack["kill"],
        attack["kill"] + attack["error"] + attack["blocked"] + attack["continue"],
    )
    severe_ratio = _ratio(severe["yes"], severe["yes"] + severe["no"])
    touched = blocking["effective"] + blocking["disruptive"]
    judged = touched + blocking["none"]

    def detail_pass() -> str:
        return (
            f"到位 {passing['in_system']}，半到位 {passing['half']}，不到位 {passing['out']}。"
            f"未知 {passing['unknown']} 次不进分母。"
        )

    def detail_block() -> str:
        return (
            f"有效 {blocking['effective']}，破坏性 {blocking['disruptive']}，没有拦到 {blocking['none']}。"
            f"未知 {blocking['unknown']} 次不进。"
            + (" 触球样本已够，仍把两种拦网分开看。" if touched >= 8 else " 两种拦网先分开计次，不合成一个百分比。")
        )

    cards = [
        {
            "key": "pass",
            "label": "一传到位",
            "display": pass_ratio["percent"] or pass_ratio["display"],
            "fraction": pass_ratio["display"],
            "ready": pass_ratio["ready"],
            "detail": detail_pass(),
        },
        {
            "key": "block",
            "label": "拦网",
            "display": "—" if judged == 0 else f"{blocking['effective']} · {blocking['disruptive']}",
            "fraction": "—" if judged == 0 else f"有效 {blocking['effective']} / 破坏 {blocking['disruptive']}",
            "ready": touched >= 8,
            "detail": detail_block(),
        },
        {
            "key": "defense",
            "label": "防守到位",
            "display": defense_ratio["percent"] or defense_ratio["display"],
            "fraction": defense_ratio["display"],
            "ready": defense_ratio["ready"],
            "detail": (
                f"到位 {defense['in_system']}，不到位 {defense['out']}。"
                f"未知 {defense['unknown']} 次不进分母。"
            ),
        },
        {
            "key": "attack",
            "label": "扣球成功",
            "display": attack_ratio["percent"] or attack_ratio["display"],
            "fraction": attack_ratio["display"],
            "ready": attack_ratio["ready"],
            "detail": (
                f"得分 {attack['kill']}，失误 {attack['error']}，被拦死 {attack['blocked']}，"
                f"继续比赛 {attack['continue']}。未知 {attack['unknown']} 次不进分母。"
            ),
        },
        {
            "key": "severe",
            "label": "严重失误",
            "display": severe_ratio["percent"] or severe_ratio["display"],
            "fraction": severe_ratio["display"],
            "ready": severe_ratio["ready"],
            "detail": (
                f"有 {severe['yes']}，没有 {severe['no']}，未知 {severe['unknown']}。"
                + (
                    "种类：" + "、".join(f"{SEVERE_KIND[key]} {count}" for key, count in kinds.items()) + "。"
                    if kinds
                    else "还没有记下种类。"
                )
            ),
        },
    ]
    judged_any = bool(
        pass_ratio["den"] or judged or defense_ratio["den"] or attack_ratio["den"] or severe_ratio["den"]
    )
    ready_any = any(card["ready"] for card in cards)
    if clips and not usable:
        headline = "目前只有关键片段。这些片段可以回看，不能写成整场到位率或成功率。"
    elif not judged_any:
        headline = "还没有可计算的技术统计。留空和未知不会被当成 0。"
    elif not ready_any:
        headline = "次数已经记下。每一项已判断的回合还不足 8 个，先不报百分比。"
    else:
        headline = "样本够 8 个的项目给出比例，其余仍只报次数。"
    if clips and usable:
        headline += f" 另有关键片段 {len(clips)} 条，没有放进这些比例。"
    return {
        "headline": headline,
        "note": "分母只含完整或抽样、而且这项已经判断的回合。未知、留空和关键片段不进比例。不足 8 个只显示次数。",
        "key_clip_count": len(clips),
        "cards": cards,
    }


def build_report(
    *,
    rallies: list[dict],
    events: list[dict],
    points: list[dict],
    history_gap: bool,
    opponent: str = "",
) -> dict:
    sub_events = []
    for event in events:
        if event["type"] != "sub":
            continue
        payload = event["payload"]
        sub_events.append(
            {
                "at": event.get("created_at"),
                "out": payload.get("out_name") or payload.get("out"),
                "in": payload.get("in_name") or payload.get("in"),
                "set_index": payload.get("set_index"),
                "rotation": payload.get("rotation"),
            }
        )
    report = {
        "opponent_rotation": None,
        "skills": skill_summary(rallies),
        "receive": question_receive(rallies),
        "serve": question_serve(rallies),
        "subs": question_subs(rallies, sub_events, opponent),
        "burden": burden(events),
        "sideout": sideout_summary(points, history_gap),
        "review_budget": "试用目标是每场赛后 20 分钟先回答这三个问题。标不完的留未知，不要为了填满而猜。这个目标还没有被你的比赛验证过。",
    }
    blob = repr(report)
    for phrase in OVERCLAIM_PHRASES:
        if phrase in blob:
            raise RuntimeError("报告生成了过度结论")
    return report
