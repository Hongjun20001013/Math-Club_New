"""Courtside rally pad. Score and rotation still go through the match log."""

from __future__ import annotations

from volleyball_coach.model import FRONT_SLOTS, TeamPlan, MatchState


class QuickError(ValueError):
    pass


PASS_RESULTS = {
    "in_system": "到位",
    "half": "半到位",
    "out": "不到位",
    "error": "直接失分",
    "unknown": "没看清",
}
SERVE_RESULTS = {
    "ace": "ACE",
    "error": "发球失误",
    "in_system": "对方到位",
    "half": "半到位",
    "out": "不到位",
    "unknown": "没看清",
}
ATTACK_RESULTS = {
    "kill": "扣球得分",
    "tool": "打手出界",
    "in_play": "没打死",
    "error": "失误",
    "blocked": "被拦死",
    "count": "只计次数",
}
OPP_STARTS = {
    "4": "四号位",
    "3": "中路",
    "2": "二号位",
    "back": "后排",
    "second": "二次球",
    "unknown": "未知",
}
OPP_LINES = {
    "line": "直线",
    "cross": "大斜线",
    "sharp": "小斜线",
    "tip": "吊球",
    "unknown": "未知",
}
OPP_RESULTS = {
    "kill": "得分",
    "in_play": "没打死",
    "error": "失误",
    "blocked": "被拦死",
}
BLOCK_RESULTS = {
    "kill": "拦网得分",
    "rebound": "拦回",
    "touch": "无效触球",
    "tool": "被打手出界",
}
DEFENSE_RESULTS = {
    "dig": "起球",
    "system": "起球到位",
    "dig_spike": "防起扣球",
    "dig_second": "接二次",
    "dig_free": "接无攻",
}
RECEPTION_EDITABLE = ("in_system", "half", "out", "unknown")
SCOPES = ("set", "last10", "match")


def _winner(kind: str, result: str) -> str | None:
    if kind == "opp_serve" and result == "error":
        return "us"
    table = {
        ("pass", "error"): "them",
        ("serve", "ace"): "us",
        ("serve", "error"): "them",
        ("attack", "kill"): "us",
        ("attack", "error"): "them",
        ("attack", "blocked"): "them",
        ("opp", "kill"): "them",
        ("opp", "error"): "us",
        ("opp", "blocked"): "us",
        ("block", "kill"): "us",
        ("block", "tool"): "them",
        ("attack", "tool"): "us",
    }
    return table.get((kind, result))


def draft_rally(match_id: str, state: MatchState) -> dict:
    server = ""
    if state.trusted and state.serving == "us":
        server = state.occupants.get(1) or ""
    return {
        "id": "",
        "match_id": match_id,
        "set_index": state.set_index,
        "status": "open",
        "serving": state.serving,
        "rotation": state.rotation,
        "score_us_before": state.score_us,
        "score_them_before": state.score_them,
        "winner": "",
        "point_seq": None,
        "completeness": "open",
        "server_id": server,
        "phase": "serve" if state.serving == "us" else "pass_player",
        "focus_player": server,
        "focus_start": "",
        "focus_line": "",
        "focus_tag": "",
        "flag": 0,
        "lineup_confirmed": int(bool(state.trusted and state.occupants)),
    }


def _action(rally: dict, *, side: str, player_id: str, kind: str, result: str, start: str = "", line: str = "", count_only: int = 0, tag: str = "") -> dict:
    return {
        "rally_id": rally.get("id") or "",
        "side": side,
        "player_id": player_id,
        "kind": kind,
        "result": result,
        "start": start,
        "line": line,
        "count_only": count_only,
        "tag": tag,
    }


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise QuickError(message)


def apply_tap(rally: dict, tap: str, value: str) -> tuple[dict, list[dict], str | None]:
    """Advance one button. Returns the rally patch, new actions, and a winner when the rally ends."""
    updated = dict(rally)
    actions: list[dict] = []
    winner: str | None = None
    phase = updated["phase"]
    value = (value or "").strip()

    def close(kind: str, result: str, action: dict, completeness: str = "complete") -> None:
        nonlocal winner
        actions.append(action)
        winner = _winner(kind, result)
        updated["status"] = "scored"
        updated["completeness"] = completeness
        updated["winner"] = winner or ""
        updated["phase"] = "done"

    if tap == "discard":
        updated["status"] = "discarded"
        updated["phase"] = "done"
        return updated, [], None

    if tap == "choose":
        _need(value in ("attack", "opp", "block", "defense"), "动作只能切到进攻、对方、拦网或防守。")
        mapping = {"attack": "attack_player", "opp": "opp_start", "block": "block_player", "defense": "defense_player"}
        updated["phase"] = mapping[value]
        if value != "attack":
            updated["focus_player"] = ""
        updated["focus_tag"] = ""
        return updated, [], None

    if tap == "pass_player":
        _need(phase in ("pass_player", "pass_all"), "现在不在选接球人。")
        _need(value, "先选接球人。")
        updated["focus_player"] = "" if value == "unknown" else value
        updated["phase"] = "pass_quality"
        return updated, [], None

    if tap == "pass_quality":
        _need(phase == "pass_quality", "先选接球人，再记质量。")
        _need(value in PASS_RESULTS, "一传质量不在可选范围内。")
        action = _action(updated, side="us", player_id=updated.get("focus_player") or "", kind="pass", result=value)
        if value == "error":
            close("pass", value, action)
        else:
            actions.append(action)
            updated["phase"] = "attack_player"
            updated["focus_player"] = ""
            updated["focus_tag"] = ""
        return updated, actions, winner

    if tap == "serve_player":
        _need(phase == "serve", "这一球的发球人已经记过了。")
        _need(value and value != "unknown", "发球人要从名单里选。")
        updated["focus_player"] = value
        updated["server_id"] = value
        return updated, [], None

    if tap == "serve":
        _need(phase == "serve", "这一球不是待记的发球。")
        _need(value in SERVE_RESULTS, "发球结果不在可选范围内。")
        player_id = updated.get("focus_player") or updated.get("server_id") or ""
        _need(bool(player_id), "发球人还没确认。先点是谁发的。")
        action = _action(updated, side="us", player_id=player_id, kind="serve", result=value)
        if value in ("ace", "error"):
            close("serve", value, action)
        else:
            actions.append(action)
            updated["phase"] = "opp_start"
            updated["focus_player"] = ""
            updated["focus_start"] = ""
            updated["focus_line"] = ""
        return updated, actions, winner

    if tap == "attack_player":
        _need(phase in ("attack_player", "attack_result", "choose"), "现在不能换攻手。")
        _need(value and value != "unknown", "先选攻手。")
        updated["focus_player"] = value
        updated["focus_tag"] = ""
        updated["phase"] = "attack_result"
        return updated, [], None

    if tap == "attack_tag":
        _need(phase == "attack_result", "先选攻手，再标快攻或探头。")
        _need(value in ("quick", "dump", ""), "标签只能是快攻或探头。")
        updated["focus_tag"] = value
        return updated, [], None

    if tap == "attack_result":
        _need(phase == "attack_result", "先选攻手，再记这一下的结果。")
        _need(value in ATTACK_RESULTS, "进攻结果不在可选范围内。")
        _need(bool(updated.get("focus_player")), "这一下还没有攻手。")
        count_only = 1 if value == "count" else 0
        action = _action(
            updated,
            side="us",
            player_id=updated["focus_player"],
            kind="attack",
            result=value,
            count_only=count_only,
            tag=updated.get("focus_tag") or "",
        )
        if value in ("kill", "error", "blocked"):
            close("attack", value, action)
        else:
            actions.append(action)
            updated["phase"] = "attack_result"
            updated["focus_tag"] = ""
        return updated, actions, winner

    if tap == "opp_start":
        _need(phase in ("opp_start", "opp_result"), "现在不是记对方起攻。")
        _need(value in OPP_STARTS, "起攻位置不在可选范围内。")
        updated["focus_start"] = value
        updated["phase"] = "opp_result"
        return updated, [], None

    if tap == "opp_line":
        _need(phase == "opp_result", "先选起攻位置，再记线路。")
        _need(value in OPP_LINES, "线路不在可选范围内。")
        updated["focus_line"] = value
        return updated, [], None

    if tap == "opp_result":
        _need(phase == "opp_result", "先选对方从哪里起攻。")
        _need(value in OPP_RESULTS, "对方进攻结果不在可选范围内。")
        _need(bool(updated.get("focus_start")), "还没有起攻位置。")
        action = _action(
            updated,
            side="them",
            player_id="",
            kind="opp",
            result=value,
            start=updated["focus_start"],
            line=updated.get("focus_line") or "",
        )
        if value == "in_play":
            actions.append(action)
            updated["phase"] = "choose"
            updated["focus_start"] = ""
            updated["focus_line"] = ""
        else:
            close("opp", value, action)
        return updated, actions, winner

    if tap == "block_player":
        _need(phase in ("block_player", "block_result"), "现在不是记拦网。")
        _need(value and value != "unknown", "先选拦网的人。")
        updated["focus_player"] = value
        updated["phase"] = "block_result"
        return updated, [], None

    if tap == "block_result":
        _need(phase == "block_result", "先选谁碰的球。")
        _need(value in BLOCK_RESULTS, "拦网结果不在可选范围内。")
        action = _action(updated, side="us", player_id=updated.get("focus_player") or "", kind="block", result=value)
        if value in ("kill", "tool"):
            close("block", value, action)
        else:
            actions.append(action)
            updated["phase"] = "attack_player"
            updated["focus_player"] = ""
        return updated, actions, winner

    if tap == "defense_player":
        _need(phase in ("defense_player", "defense_result"), "现在不是记防守。")
        _need(value and value != "unknown", "先选防守的人。")
        updated["focus_player"] = value
        updated["phase"] = "defense_result"
        return updated, [], None

    if tap == "defense_result":
        _need(phase == "defense_result", "先选谁防的。")
        _need(value in DEFENSE_RESULTS, "防守结果不在可选范围内。")
        actions.append(_action(updated, side="us", player_id=updated.get("focus_player") or "", kind="defense", result=value))
        updated["phase"] = "choose"
        updated["focus_player"] = ""
        return updated, actions, None

    if tap in ("score", "flag_score"):
        _need(value in ("us", "them"), "结分要选我方或对方。")
        _need(phase != "done", "这一球已经结过分。")
        updated["status"] = "scored"
        updated["winner"] = value
        updated["flag"] = 1 if tap == "flag_score" else int(updated.get("flag") or 0)
        updated["completeness"] = "pending" if tap == "flag_score" else "complete"
        updated["phase"] = "done"
        return updated, [], value

    raise QuickError("这个按钮现在不能用。")


def describe_action(action: dict, names: dict[str, str]) -> str:
    player = names.get(action.get("player_id") or "", "")
    kind = action["kind"]
    result = action["result"]
    if kind == "opp_serve":
        return "对方发球失误"
    if kind == "pass":
        who = player or "没看清"
        return f"{who} 一传{PASS_RESULTS.get(result, result)}"
    if kind == "serve":
        who = player or "待确认"
        if result == "out":
            return f"{who} 发球破坏一传"
        if result == "ace":
            return f"{who} ACE"
        if result == "error":
            return f"{who} 发球失误"
        return f"{who} 发球，{SERVE_RESULTS.get(result, result)}"
    if kind == "attack":
        who = player or "未指定"
        tag = {"quick": "快攻", "dump": "探头"}.get(action.get("tag") or "", "")
        label = ATTACK_RESULTS.get(result, result)
        if tag and result == "in_play":
            return f"{who} {tag}"
        if tag and result == "kill":
            return f"{who} {tag}得分"
        return f"{who} {label}"
    if kind == "opp":
        start = OPP_STARTS.get(action.get("start") or "", "未知")
        line = OPP_LINES.get(action.get("line") or "", "")
        outcome = {"kill": "得分", "in_play": "没打死", "error": "失误", "blocked": "被拦死"}.get(result, result)
        piece = f"对方{start}"
        if line:
            piece += line
        return f"{piece}{outcome}"
    if kind == "block":
        who = player or "未指定"
        return f"{who} {BLOCK_RESULTS.get(result, result)}"
    if kind == "defense":
        who = player or "未指定"
        return f"{who} {DEFENSE_RESULTS.get(result, result)}"
    return "未记录"


def describe(actions: list[dict], names: dict[str, str]) -> str:
    skills = [action for action in actions if action.get("kind") != "score" and not action.get("voided")]
    if not skills:
        return "未记录技术动作"
    return " → ".join(describe_action(action, names) for action in skills)


def action_winner(action: dict) -> str | None:
    if action.get("kind") == "score" and action.get("result") in ("us", "them"):
        return action["result"]
    return _winner(action.get("kind") or "", action.get("result") or "")


def record_cell(
    rally: dict,
    *,
    kind: str,
    result: str,
    player_id: str = "",
    start: str = "",
    line: str = "",
    tag: str = "",
) -> tuple[dict, list[dict], str | None]:
    """One cell. Does not require the previous step. A closed rally only gains a touch."""
    catalogs = {
        "pass": PASS_RESULTS,
        "serve": SERVE_RESULTS,
        "attack": ATTACK_RESULTS,
        "opp": OPP_RESULTS,
        "block": BLOCK_RESULTS,
        "defense": DEFENSE_RESULTS,
    }
    updated = dict(rally)
    if kind == "score":
        if result not in ("us", "them"):
            raise QuickError("结分要选我方或对方。")
    elif kind == "opp_serve":
        if result != "error":
            raise QuickError("对方发丢只有一种记法。")
    elif kind not in catalogs or result not in catalogs[kind]:
        raise QuickError("这一格不在记录表里。")
    if kind == "opp" and start not in OPP_STARTS:
        raise QuickError("先有起攻位置。")
    action = _action(
        updated,
        side="them" if kind in ("opp", "opp_serve") else "us",
        player_id="" if player_id in ("", "unknown", "shared") else player_id,
        kind=kind,
        result=result,
        start=start,
        line=line,
        count_only=1 if kind == "attack" and result == "count" else 0,
        tag=tag or ("shared" if player_id == "shared" else ""),
    )
    if player_id == "shared":
        action["player_id"] = ""
        action["tag"] = "shared"
    if updated.get("status") == "scored":
        return updated, [action], None
    if kind == "serve" and action["player_id"]:
        updated["server_id"] = action["player_id"]
    winner = action_winner(action)
    if winner:
        updated["status"] = "scored"
        updated["winner"] = winner
        updated["phase"] = "done"
        updated["completeness"] = "pending" if kind == "score" else "complete"
        updated["flag"] = 1 if kind == "score" else int(updated.get("flag") or 0)
    return updated, [action], winner


def sheet_after(kind: str, result: str, serving: str) -> str:
    """The next sheet follows the point. A manual tab change does not outlive the rally."""
    if action_winner({"kind": kind, "result": result}):
        return "serve" if serving == "us" else "pass"
    if kind == "pass":
        return "attack"
    if kind == "serve":
        return "opp"
    if kind in ("attack", "opp"):
        return kind
    if kind in ("block", "defense"):
        return "more"
    return "pass" if serving != "us" else "serve"


def sheet_for_context(actions: list[dict], serving: str) -> str:
    live = [action for action in actions if not action.get("voided")]
    if not live:
        return "serve" if serving == "us" else "pass"
    last = live[-1]
    return sheet_after(last.get("kind") or "", last.get("result") or "", serving)


def sheet_after_undo(voided: dict, earlier: list[dict], serving: str) -> str:
    kept = [action for action in earlier if not action.get("voided")]
    if kept:
        return sheet_for_context(kept, serving)
    kind = voided.get("kind") or ""
    if kind in ("pass", "attack", "serve", "opp"):
        return kind
    if kind in ("block", "defense"):
        return "more"
    return "serve" if serving == "us" else "pass"


def pause_lines(board: dict) -> dict:
    if board["attacks"]:
        top = board["attacks"][0]
        attack = f"{top['name']} {top['phrase']}　成功率 {top['rate_ratio']} {top['rate']}"
        rated = [row for row in board["attacks"] if row["attempts"]]
        if rated:
            best = max(rated, key=lambda row: (row["kills"] / row["attempts"], row["attempts"]))
            if best["player_id"] != top["player_id"]:
                attack += f"。打得最顺是 {best['name']} {best['rate_ratio']} {best['rate']}"
    else:
        attack = "还没有进攻"
    if board["passes"]:
        bits = [f"{row['name']} {row['in_system']}到位/{row['rated'] + row['unknown']}接" for row in board["passes"][:3]]
        receive = "　".join(bits)
    else:
        receive = "还没有接发"
    if board["serves"]:
        row = board["serves"][0]
        serve = f"{row['name']} 威胁 {row['threat_ratio']}　ACE {row['ace']}　失误 {row['error']}　逼不到位 {row['out']}"
    else:
        serve = "还没有发球"
    if board["opponents"]:
        opp = "，".join(f"{row['name']} {row['phrase']}" for row in board["opponents"])
    else:
        opp = "还没有对方起攻"
    return {
        "attack": attack,
        "receive": receive,
        "serve": serve,
        "opp": opp,
        "recorded": len(board["rallies"]),
        "pending": board["pending"],
    }


def _pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "—"
    return f"{numerator / denominator * 100:.1f}%"


def _ratio(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "—"
    return f"{numerator}/{denominator}"


def _attack_phrase(attempts: int, kills: int, errors: int, blocked: int) -> str:
    text = f"{attempts}扣{kills}中"
    if errors:
        text += f"{errors}失误"
    if blocked:
        text += f"{blocked}被拦"
    return text


def board_for(
    rallies: list[dict],
    actions: list[dict],
    names: dict[str, str],
    *,
    scope: str,
    set_index: int,
) -> dict:
    if scope not in SCOPES:
        scope = "set"
    scored = [rally for rally in rallies if rally.get("status") == "scored"]
    if scope == "set":
        scoped = [rally for rally in scored if int(rally["set_index"]) == int(set_index)]
    elif scope == "last10":
        scoped = scored[-10:]
    else:
        scoped = list(scored)
    allowed = {rally["id"] for rally in scoped}
    by_rally: dict[str, list[dict]] = {}
    for action in actions:
        if action["rally_id"] in allowed:
            by_rally.setdefault(action["rally_id"], []).append(action)
    for group in by_rally.values():
        group.sort(key=lambda item: item.get("ord") or 0)

    attacks: dict[str, dict] = {}
    passes: dict[str, dict] = {}
    serves: dict[str, dict] = {}
    blocks: dict[str, dict] = {}
    defenses: dict[str, dict] = {}
    opps: dict[str, dict] = {}
    pending = 0

    def attack_row(player_id: str) -> dict:
        row = attacks.get(player_id)
        if row is None:
            row = {
                "player_id": player_id,
                "name": names.get(player_id, "未指定") if player_id else "未指定",
                "attempts": 0,
                "kills": 0,
                "errors": 0,
                "blocked": 0,
                "in_play": 0,
                "count_only": 0,
                "first_ball": 0,
                "transition": 0,
                "unsure": 0,
                "rallies": [],
            }
            attacks[player_id] = row
        return row

    def bucket(store: dict, key: str, label: str) -> dict:
        row = store.get(key)
        if row is None:
            row = {"key": key, "name": label, "rallies": []}
            store[key] = row
        return row

    for rally in scoped:
        rally_actions = by_rally.get(rally["id"], [])
        if rally.get("completeness") in ("pending", "score_only") or not rally_actions:
            pending += 1
        seen_defense = False
        had_pass = False
        rally_attacks: list[tuple[dict, bool]] = []
        for action in rally_actions:
            kind = action["kind"]
            if kind == "pass":
                had_pass = True
            if kind == "pass":
                player_id = action.get("player_id") or ""
                if action.get("tag") == "shared":
                    player_id = "__shared__"
                label = "共同" if player_id == "__shared__" else (names.get(player_id, "没看清") if player_id else "没看清")
                row = bucket(passes, player_id, label)
                result = action["result"] if action["result"] in PASS_RESULTS else "unknown"
                row[result] = row.get(result, 0) + 1
                row["rallies"].append(rally["id"])
            elif kind == "serve":
                player_id = action.get("player_id") or ""
                row = bucket(serves, player_id, names.get(player_id, "待确认") if player_id else "待确认")
                result = action["result"]
                row[result] = row.get(result, 0) + 1
                row["total"] = row.get("total", 0) + 1
                row["rallies"].append(rally["id"])
            elif kind == "attack":
                row = attack_row(action.get("player_id") or "")
                row["attempts"] += 1
                result = action["result"]
                if result in ("kill", "tool"):
                    row["kills"] += 1
                elif result == "error":
                    row["errors"] += 1
                elif result == "blocked":
                    row["blocked"] += 1
                elif result == "count":
                    row["count_only"] += 1
                else:
                    row["in_play"] += 1
                rally_attacks.append((row, seen_defense))
                row["rallies"].append(rally["id"])
            elif kind == "opp":
                start = action.get("start") or "unknown"
                row = bucket(opps, start, OPP_STARTS.get(start, "未知"))
                row["attempts"] = row.get("attempts", 0) + 1
                result = action["result"]
                row[result] = row.get(result, 0) + 1
                line = action.get("line") or ""
                if line:
                    lines = row.setdefault("lines", {})
                    lines[line] = lines.get(line, 0) + 1
                    if result != "kill":
                        row["line_on_live"] = True
                row["rallies"].append(rally["id"])
            elif kind == "block":
                player_id = action.get("player_id") or ""
                row = bucket(blocks, player_id, names.get(player_id, "未指定") if player_id else "未指定")
                row[action["result"]] = row.get(action["result"], 0) + 1
                row["rallies"].append(rally["id"])
                if action["result"] in ("rebound", "touch"):
                    seen_defense = True
            elif kind == "defense":
                player_id = action.get("player_id") or ""
                row = bucket(defenses, player_id, names.get(player_id, "未指定") if player_id else "未指定")
                row[action["result"]] = row.get(action["result"], 0) + 1
                row["rallies"].append(rally["id"])
                seen_defense = True
        if seen_defense:
            for row, after_defense in rally_attacks:
                if after_defense:
                    row["transition"] += 1
                else:
                    row["first_ball"] += 1
        elif had_pass and len(rally_attacks) == 1:
            rally_attacks[0][0]["first_ball"] += 1
        else:
            for row, _before in rally_attacks:
                row["unsure"] += 1

    attack_rows = []
    for row in attacks.values():
        attempts = row["attempts"]
        row["phrase"] = _attack_phrase(attempts, row["kills"], row["errors"], row["blocked"])
        row["rate"] = _pct(row["kills"], attempts)
        row["rate_ratio"] = _ratio(row["kills"], attempts)
        row["eff"] = _pct(row["kills"] - row["errors"] - row["blocked"], attempts)
        bits = []
        if row["first_ball"] or row["transition"]:
            bits.append(f"第一攻 {row['first_ball']} · 防反 {row['transition']}")
        if row["unsure"]:
            bits.append(f"阶段未确认 {row['unsure']}")
        row["split"] = "　".join(bits)
        row["rally_links"] = _mentions(row["rallies"])
        attack_rows.append(row)
    attack_rows.sort(key=lambda item: (-item["attempts"], item["name"]))

    pass_rows = []
    for row in passes.values():
        for key in PASS_RESULTS:
            row.setdefault(key, 0)
        rated = row["in_system"] + row["half"] + row["out"] + row["error"]
        row["rated"] = rated
        row["rate"] = _pct(row["in_system"], rated)
        row["rate_ratio"] = _ratio(row["in_system"], rated)
        pass_rows.append(row)
    pass_rows.sort(key=lambda item: (-(item["rated"] + item["unknown"]), item["name"]))

    serve_rows = []
    for row in serves.values():
        for key in SERVE_RESULTS:
            row.setdefault(key, 0)
        row.setdefault("total", 0)
        judged = row["ace"] + row["out"] + row["error"] + row["in_system"] + row["half"]
        row["judged"] = judged
        row["threat_ratio"] = _ratio(row["ace"] + row["out"], judged)
        row["threat"] = _pct(row["ace"] + row["out"], judged)
        row["in_ratio"] = _ratio(row["total"] - row["error"], row["total"])
        row["in_rate"] = _pct(row["total"] - row["error"], row["total"])
        serve_rows.append(row)
    serve_rows.sort(key=lambda item: (-item["total"], item["name"]))

    opp_rows = []
    for row in opps.values():
        row.setdefault("attempts", 0)
        row.setdefault("kill", 0)
        row.setdefault("error", 0)
        row.setdefault("blocked", 0)
        row.setdefault("in_play", 0)
        row["phrase"] = _attack_phrase(row["attempts"], row["kill"], row["error"], row["blocked"])
        line_bits = []
        for key, count in (row.get("lines") or {}).items():
            line_bits.append(f"{OPP_LINES.get(key, key)} {count}")
        row["line_text"] = "、".join(line_bits)
        row["line_note"] = "" if row.get("line_on_live") or not line_bits else "仅失分片段"
        row["rate"] = _pct(row["kill"], row["attempts"])
        row["eff"] = _pct(row["kill"] - row["error"] - row["blocked"], row["attempts"])
        row["rally_links"] = _mentions(row["rallies"])
        opp_rows.append(row)
    order = {key: index for index, key in enumerate(OPP_STARTS)}
    opp_rows.sort(key=lambda item: order.get(item["key"], 99))

    return {
        "scope": scope,
        "attacks": attack_rows,
        "passes": pass_rows,
        "serves": serve_rows,
        "blocks": list(blocks.values()),
        "defenses": list(defenses.values()),
        "opponents": opp_rows,
        "pending": pending,
        "rallies": scoped,
    }


def _mentions(rally_ids: list[str]) -> list[dict]:
    order: list[str] = []
    counts: dict[str, int] = {}
    for rally_id in rally_ids:
        if rally_id not in counts:
            order.append(rally_id)
            counts[rally_id] = 0
        counts[rally_id] += 1
    return [{"id": rally_id, "n": counts[rally_id]} for rally_id in order]


def _team_attack(rows: list[dict]) -> dict:
    attempts = sum(row["attempts"] for row in rows)
    kills = sum(row["kills"] for row in rows)
    errors = sum(row["errors"] for row in rows)
    blocked = sum(row["blocked"] for row in rows)
    return {
        "name": "全队",
        "attempts": attempts,
        "kills": kills,
        "errors": errors,
        "blocked": blocked,
        "phrase": _attack_phrase(attempts, kills, errors, blocked),
        "rate": _pct(kills, attempts),
        "eff": _pct(kills - errors - blocked, attempts),
        "count_only": sum(row["count_only"] for row in rows),
    }


def person_sheet(board: dict) -> list[dict]:
    """One row per person. Direct points are kills, aces, and stuff blocks. A tool off our block is their point."""
    attacks = {row["player_id"]: row for row in board["attacks"]}
    serves = {row["key"]: row for row in board["serves"]}
    blocks = {row["key"]: row for row in board["blocks"]}
    keys = list(dict.fromkeys([*attacks, *serves, *blocks]))
    rows = []
    for key in keys:
        attack = attacks.get(key)
        serve = serves.get(key)
        block = blocks.get(key)
        source = attack or serve or block
        kills = attack["kills"] if attack else 0
        aces = int(serve.get("ace", 0)) if serve else 0
        block_points = int(block.get("kill", 0)) if block else 0
        rows.append(
            {
                "player_id": key,
                "name": source["name"],
                "phrase": attack["phrase"] if attack else "—",
                "errors": attack["errors"] if attack else 0,
                "blocked": attack["blocked"] if attack else 0,
                "rate": attack["rate"] if attack else "—",
                "rate_ratio": attack["rate_ratio"] if attack else "",
                "eff": attack["eff"] if attack else "—",
                "count_only": attack["count_only"] if attack else 0,
                "ace": aces,
                "block_points": block_points,
                "points": kills + aces + block_points,
            }
        )
    rows.sort(key=lambda item: (-item["points"], item["name"]))
    return rows


def build_digest(rallies: list[dict], actions: list[dict], names: dict[str, str]) -> dict:
    """The pause card, the summary page, and the PDF all read this."""
    scored = [rally for rally in rallies if rally.get("status") == "scored"]
    set_indexes = sorted({int(rally["set_index"]) for rally in scored})
    sets = []
    for index in set_indexes:
        board = board_for(rallies, actions, names, scope="set", set_index=index)
        sets.append(
            {
                "set_index": index,
                "score_us": sum(1 for rally in board["rallies"] if rally.get("winner") == "us"),
                "score_them": sum(1 for rally in board["rallies"] if rally.get("winner") == "them"),
                "board": board,
                "lines": pause_lines(board),
                "team": _team_attack(board["attacks"]),
                "people": person_sheet(board),
            }
        )
    match_board = board_for(rallies, actions, names, scope="match", set_index=set_indexes[-1] if set_indexes else 1)
    by_rally: dict[str, list[dict]] = {}
    for action in actions:
        by_rally.setdefault(action["rally_id"], []).append(action)
    for group in by_rally.values():
        group.sort(key=lambda item: item.get("ord") or 0)
    detail = []
    for rally in sorted(scored, key=lambda item: (int(item.get("set_index") or 0), int(item.get("point_seq") or 0), str(item.get("id")))):
        detail.append(
            {
                "set_index": int(rally["set_index"]),
                "score": f"{rally.get('score_us_before', 0)}–{rally.get('score_them_before', 0)}",
                "winner": "我方" if rally.get("winner") == "us" else "对方" if rally.get("winner") == "them" else "未知",
                "story": describe(by_rally.get(rally["id"], []), names),
                "pending": rally.get("completeness") in ("pending", "score_only"),
            }
        )
    return {
        "sets": sets,
        "match": match_board,
        "lines": pause_lines(match_board),
        "team": _team_attack(match_board["attacks"]),
        "people": person_sheet(match_board),
        "detail": detail,
        "recorded": len(match_board["rallies"]),
        "pending": match_board["pending"],
    }


def _people(plan: TeamPlan, state: MatchState) -> list:
    if state.occupants:
        ordered = []
        for slot in (4, 3, 2, 5, 6, 1):
            player_id = state.occupants.get(slot)
            player = plan.players.get(player_id or "")
            if player and player not in ordered:
                ordered.append(player)
        return ordered
    return list(plan.players.values())


def pad_for(plan: TeamPlan, state: MatchState, rally: dict | None, actions: list[dict]) -> dict:
    current = rally or draft_rally("", state)
    phase = current["phase"]
    court = _people(plan, state)
    front = []
    if state.occupants:
        for slot in (4, 3, 2):
            player = plan.players.get(state.occupants.get(slot) or "")
            if player:
                front.append(player)
    else:
        front = court[:3]
    primary = [player for player in court if player.receive_primary] or court
    names = {player.id: player.name for player in plan.players.values()}
    server_id = current.get("server_id") or ""
    server_name = names.get(server_id, "")
    if state.serving == "us" and not server_name:
        server_name = "待确认"
    story = describe(actions, names) if actions else ""
    return {
        "phase": phase,
        "story": story,
        "server_name": server_name,
        "server_pending": server_name == "待确认",
        "focus_name": names.get(current.get("focus_player") or "", ""),
        "focus_start": OPP_STARTS.get(current.get("focus_start") or "", ""),
        "focus_line": OPP_LINES.get(current.get("focus_line") or "", ""),
        "focus_tag": {"quick": "快攻", "dump": "探头"}.get(current.get("focus_tag") or "", ""),
        "primary": primary,
        "others": [player for player in court if player not in primary],
        "roster": list(plan.players.values()),
        "front": front or court,
        "court": court,
        "can_switch": phase in ("attack_player", "attack_result", "opp_start", "opp_result", "choose", "block_player", "defense_player"),
    }


def reception_editable(actions: list[dict]) -> dict | None:
    for action in actions:
        if action["kind"] == "pass" and action["result"] in PASS_RESULTS:
            return action
        if action["kind"] == "serve" and action["result"] in RECEPTION_EDITABLE:
            return action
    return None
