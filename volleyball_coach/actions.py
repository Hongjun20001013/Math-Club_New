"""Action-level stats. Unknown stays out of judged denominators and is never stored as zero."""

from __future__ import annotations


PASS_QUALITY = {
    "in_system": "到位",
    "half": "半到位",
    "out": "不到位",
    "error": "直接失误",
    "unknown": "未知",
}

PASS_STANDARD = {
    "in_system": "到位：二传可以组织快攻。",
    "half": "半到位：只能组织调整进攻。",
    "out": "不到位：无法组织进攻。",
    "error": "直接失误：一传出界、下网，或让对方直接得分。",
    "unknown": "未知：看不清。不进入已判断质量的分母。",
}

ATTACK_RESULT = {
    "kill": "得分",
    "error": "失误",
    "blocked": "被拦死",
    "continue": "继续比赛",
    "unknown": "未知",
}

BLOCK_RESULT = {
    "kill": "拦死",
    "touch": "有效触球",
    "used": "被打手利用",
    "fault": "拦网犯规",
    "unknown": "未知",
}

SKILLS = {
    "pass": "一传",
    "attack": "扣球",
    "block": "拦网",
    "serve": "发球",
    "dig": "防守",
    "set": "二传",
}

SKILL_RESULTS = {
    "pass": PASS_QUALITY,
    "attack": ATTACK_RESULT,
    "block": BLOCK_RESULT,
    "serve": {"ace": "得分", "error": "失误", "continue": "继续比赛", "unknown": "未知"},
    "dig": {"in_system": "到位", "out": "不到位", "error": "失误", "unknown": "未知"},
    "set": {"continue": "继续比赛", "error": "失误", "unknown": "未知"},
}

STARTS = {
    "left": "左侧",
    "middle": "中间",
    "right": "右侧",
    "pipe": "后排",
    "unknown": "未知",
}

LINES = {
    "straight": "直线",
    "cross": "大斜线",
    "cut": "小斜线",
    "tip": "吊球",
    "unknown": "未知",
}

PHASES = {
    "sideout": "一攻",
    "transition": "防反",
    "unknown": "未知",
}

SET_QUALITY = {
    "in_system": "到位",
    "out": "调整球",
    "unknown": "未知",
}

SCOPES = {
    "sample": "抽样",
    "complete": "完整",
    "key_clip": "关键片段",
}

DEPTHS = {
    "light": "场边简记",
    "complete": "完整记录",
}

RESULT_TONE = {
    "kill": "good",
    "ace": "good",
    "in_system": "good",
    "touch": "good",
    "error": "bad",
    "blocked": "bad",
    "fault": "bad",
    "used": "bad",
    "out": "bad",
    "continue": "mid",
    "half": "mid",
    "unknown": "unknown",
}


def pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "—"
    return f"{numerator / denominator:.0%}"


def _count(rows: list[dict], key: str, code: str) -> int:
    return sum(1 for row in rows if row.get(key) == code)


def pass_summary(rows: list[dict]) -> dict:
    judged_codes = ("in_system", "half", "out", "error")
    counts = {code: _count(rows, "quality", code) for code in PASS_QUALITY}
    judged = sum(counts[code] for code in judged_codes)
    return {
        "attempts": len(rows),
        "counts": counts,
        "judged": judged,
        "unknown": counts["unknown"],
        "in_rate": pct(counts["in_system"], judged),
        "error_rate": pct(counts["error"], judged),
        "in_system": counts["in_system"],
        "error": counts["error"],
    }


def attack_summary(rows: list[dict]) -> dict:
    counts = {code: _count(rows, "result", code) for code in ATTACK_RESULT}
    judged = counts["kill"] + counts["error"] + counts["blocked"] + counts["continue"]
    kills = counts["kill"]
    errors = counts["error"]
    blocked = counts["blocked"]
    return {
        "attempts": judged,
        "recorded": len(rows),
        "counts": counts,
        "unknown": counts["unknown"],
        "kills": kills,
        "errors": errors,
        "blocked": blocked,
        "continue": counts["continue"],
        "success": pct(kills, judged),
        "efficiency": pct(kills - errors - blocked, judged) if judged else "—",
        "efficiency_num": kills - errors - blocked,
    }


def block_summary(actions: list[dict], membership: dict[int, list[str]], player_id: str | None) -> dict:
    """Team kills count the action once. A player only counts participation."""
    if player_id is None:
        rows = [row for row in actions if row.get("skill") == "block"]
    else:
        rows = [
            row
            for row in actions
            if row.get("skill") == "block" and player_id in membership.get(row["id"], [])
        ]
    counts = {code: _count(rows, "result", code) for code in BLOCK_RESULT}
    return {
        "events": len(rows),
        "counts": counts,
        "kills": counts["kill"],
        "unknown": counts["unknown"],
    }


def team_block_kills(actions: list[dict]) -> int:
    return sum(1 for row in actions if row.get("skill") == "block" and row.get("result") == "kill")


def coverage(rallies: list[dict], actions: list[dict], point_count: int) -> dict:
    closed = [row for row in rallies if row.get("status") != "open" and not row.get("legacy")]
    scopes: dict[str, int] = {}
    for row in closed:
        scope = row.get("sample_scope") or "sample"
        scopes[scope] = scopes.get(scope, 0) + 1
    return {
        "actions": len(actions),
        "closed": len(closed),
        "open": sum(1 for row in rallies if row.get("status") == "open"),
        "legacy": sum(1 for row in rallies if row.get("legacy")),
        "points": point_count,
        "scopes": scopes,
    }


def arrow(start: str, line: str, *, flipped: bool = False) -> dict | None:
    """Opponent attacks downward. Their left is screen-right until a side change flips the view.

    The landing point is only where the arrow is drawn. It is not stored as the attack line.
    """
    if start not in STARTS or line not in LINES or start == "unknown" or line == "unknown":
        return None
    anchor = {"right": 22, "middle": 50, "left": 78, "pipe": 50}[start]
    height = 14 if start == "pipe" else 8
    ends = {
        "left": {"straight": (82, 78), "cross": (18, 82), "cut": (42, 62), "tip": (74, 36)},
        "right": {"straight": (18, 78), "cross": (82, 82), "cut": (58, 62), "tip": (26, 36)},
        "middle": {"straight": (50, 78), "cross": (22, 78), "cut": (78, 64), "tip": (50, 36)},
        "pipe": {"straight": (50, 84), "cross": (20, 80), "cut": (80, 68), "tip": (50, 40)},
    }
    end_x, end_y = ends[start][line]
    if flipped:
        anchor = 100 - anchor
        end_x = 100 - end_x
    return {"x1": anchor, "y1": height, "x2": end_x, "y2": end_y}


def line_groups(actions: list[dict]) -> list[dict]:
    grouped: dict[tuple, list[dict]] = {}
    for row in actions:
        if row.get("skill") != "attack":
            continue
        key = (row.get("start_zone") or "unknown", row.get("attack_line") or "unknown", bool(row.get("view_flip")))
        grouped.setdefault(key, []).append(row)
    rows = []
    for (start, line, flipped), items in grouped.items():
        geometry = arrow(start, line, flipped=flipped)
        if geometry is None:
            continue
        counts = {code: _count(items, "result", code) for code in ATTACK_RESULT}
        dominant = max(counts, key=lambda code: (counts[code], code == "unknown"))
        if counts[dominant] == 0:
            dominant = "unknown"
        rows.append(
            {
                "start": start,
                "line": line,
                "flipped": flipped,
                "count": len(items),
                "result": dominant,
                "counts": counts,
                "width": min(1.4 + len(items) * 1.1, 8),
                **geometry,
            }
        )
    rows.sort(key=lambda item: (-item["count"], item["start"], item["line"]))
    return rows
