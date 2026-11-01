"""The men's roster is the one plan already confirmed. Other teams start empty."""

from __future__ import annotations

from volleyball_coach.model import Pair, Player, Rules, ServePlan, SubWindow, TeamPlan


MENS_TEAM_ID = "team-mens"


def _player(**kwargs) -> Player:
    return Player(**kwargs)


def build_mens_plan() -> TeamPlan:
    players = {
        "michael": _player(
            id="michael",
            name="Michael",
            role="opposite",
            base_slot=1,
            sets_when="back_row",
            can_backup_set=False,
            jersey="",
        ),
        "leo": _player(id="leo", name="Leo", role="outside", base_slot=2, receive_primary=True),
        "andy-a": _player(id="andy-a", name="Andy A", role="middle", base_slot=3),
        "eric": _player(
            id="eric",
            name="Eric",
            role="opposite",
            base_slot=4,
            sets_when="back_row",
        ),
        "vitas": _player(id="vitas", name="Vitas", role="outside", base_slot=5, receive_primary=True),
        "andy-b": _player(
            id="andy-b",
            name="Andy B",
            role="middle",
            base_slot=6,
            receive_primary=True,
            can_backup_set=True,
            backup_rank=1,
        ),
        "d": _player(
            id="d",
            name="D",
            role="defender",
            receive_primary=True,
            can_backup_set=True,
            backup_rank=2,
            private_note="姓名和号码还没补。",
        ),
        "harvey": _player(
            id="harvey",
            name="Harvey",
            role="flex",
            private_note="可以打主攻或接应。二传和接发都还没验证，所以不进主接发，也不能默认留在后排组织。",
        ),
    }
    rules = Rules(
        no_back_row_attack=True,
        no_libero=True,
        fixed_pair_subs=True,
        unlimited_subs=True,
        max_subs=None,
        pair_lock_scope="match",
        overlap_confirmed=False,
        timeouts_known=False,
    )
    pairs = [
        Pair("pair-d", "andy-a", "d", "confirmed", "已确认。整场锁定，禁止和别人交叉替换。"),
        Pair(
            "pair-harvey",
            "michael",
            "harvey",
            "candidate",
            "优先测试的候选，不是已经确定的最终配对。开赛前要明确锁定，不锁定就不能上场。",
        ),
    ]
    serve_plans = {
        rotation: ServePlan(
            rotation=rotation,
            target_type="unset",
            backup_label="这个发球队员最稳的落点",
            block_note="一传没被破坏，就按到位球拦防；被破坏了，再按调整球改防。",
            evidence="暂无对手证据",
        )
        for rotation in range(1, 7)
    }
    windows = [
        SubWindow("andy-a", "d", (3, 4, 5), "D 只计划承担 Andy A 的后排。前排阶段换回 Andy A。"),
        SubWindow(
            "michael",
            "harvey",
            (4, 5, 6),
            "只有本场锁定 Harvey 换 Michael 时才提醒。Harvey 打前排，Michael 回后排组织。",
        ),
    ]
    guidance = [
        {
            "partner_id": "michael",
            "title": "Harvey 换 Michael",
            "when": "需要加强 Michael 的前排右翼或拦网，而且 Harvey 补得上。",
            "cost": "Michael 后排组织，Harvey 前排。回到后排前换回 Michael。Harvey 的二传没验证，不能留他在后排组织。",
        },
        {
            "partner_id": "eric",
            "title": "Harvey 换 Eric",
            "when": "Eric 的前排需要调整，Harvey 更适合这个对位。",
            "cost": "Eric 留在后排组织。Harvey 打前排。",
        },
        {
            "partner_id": "leo",
            "title": "Harvey 换 Leo",
            "when": "Leo 的某项任务需要保护，Harvey 能接住这个轮转角色。",
            "cost": "主攻的接发和攻防跟着槽位走。要单独看接发有没有变差。",
        },
        {
            "partner_id": "vitas",
            "title": "Harvey 换 Vitas",
            "when": "Vitas 的某项任务需要保护。",
            "cost": "同样要看接发和左右翼转换，不能只比扣球。",
        },
    ]
    return TeamPlan(
        team_id=MENS_TEAM_ID,
        name="男排",
        rules=rules,
        players=players,
        pairs=pairs,
        serve_plans=serve_plans,
        sub_windows=windows,
        calls={"in_system": "全开", "half": "两翼", "out": "高球"},
        guidance=guidance,
        board_note=(
            "R2 和 R5 的前排按槽位重算过。原稿把 R1–R2、R4–R5 写成同一组前排，"
            "但 R2 的 Leo、R5 的 Vitas 已经转到后排。这支球队禁止后排进攻，卡片不沿用那个合并写法。"
        ),
        notes=(
            "8 人。本地赛制：禁止后排进攻、无自由人、固定一对一、无限往返。"
            "Andy A 和 Andy B 是临时标签。D 的姓名还没补。配对默认整场锁定。"
            "女排和其他小队不要套用这份名单，也不要套用这套规则。"
        ),
    )


MENS_ABILITIES = {
    "leo": ["接发覆盖", "接发后助跑", "困难球", "左翼拦网"],
    "vitas": ["接发覆盖", "接发后助跑", "困难球", "左翼拦网"],
    "michael": ["右翼进攻", "拦网", "转入前排后的角色执行"],
    "eric": ["到位组织", "不到位组织", "传球落点", "二传移动"],
    "andy-a": ["快攻", "拦网", "发球"],
    "andy-b": ["六轮职责", "接发范围", "后排补位传球"],
    "d": ["接发", "后排防守", "发球", "补位传球"],
    "harvey": ["右翼攻击", "左翼攻击", "拦网", "接发", "与二传配合"],
}


def mens_locked_pairs(*, include_harvey: bool) -> set[frozenset[str]]:
    locked = {frozenset(("andy-a", "d"))}
    if include_harvey:
        locked.add(frozenset(("michael", "harvey")))
    return locked
