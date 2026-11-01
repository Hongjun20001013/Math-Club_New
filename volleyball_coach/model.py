"""Data the coach can confirm. Nothing here is inferred from a video model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


FRONT_SLOTS = frozenset({2, 3, 4})
BACK_SLOTS = frozenset({1, 5, 6})

SLOT_NAME = {
    1: "右后",
    2: "右前",
    3: "中前",
    4: "左前",
    5: "左后",
    6: "中后",
}

# Wing duty follows the player's role, not the rotation slot they happen to stand in.
WING_BY_ROLE = {
    "opposite": "右翼",
    "middle": "中路",
    "outside": "左翼",
}

SLOT_GEO_WING = {4: "左翼", 3: "中路", 2: "右翼"}

PASS_QUALITY = {
    "in_system": "到位",
    "half": "半到位",
    "out": "不到位",
    "unknown": "未知",
}

ABILITY_LABEL = {
    "stable": "稳定可用",
    "protect": "需要保护",
    "unknown": "尚未验证",
}


@dataclass
class Rules:
    no_back_row_attack: bool = False
    no_libero: bool = False
    fixed_pair_subs: bool = False
    unlimited_subs: bool = False
    max_subs: Optional[int] = None
    pair_lock_scope: str = "match"
    overlap_confirmed: bool = False
    timeouts_known: bool = False

    def to_json(self) -> dict:
        return {
            "no_back_row_attack": self.no_back_row_attack,
            "no_libero": self.no_libero,
            "fixed_pair_subs": self.fixed_pair_subs,
            "unlimited_subs": self.unlimited_subs,
            "max_subs": self.max_subs,
            "pair_lock_scope": self.pair_lock_scope,
            "overlap_confirmed": self.overlap_confirmed,
            "timeouts_known": self.timeouts_known,
        }

    @staticmethod
    def from_json(data: dict) -> "Rules":
        max_subs = data.get("max_subs")
        if max_subs == "":
            max_subs = None
        return Rules(
            no_back_row_attack=bool(data.get("no_back_row_attack")),
            no_libero=bool(data.get("no_libero")),
            fixed_pair_subs=bool(data.get("fixed_pair_subs")),
            unlimited_subs=bool(data.get("unlimited_subs")),
            max_subs=None if max_subs is None else int(max_subs),
            pair_lock_scope=data.get("pair_lock_scope") or "match",
            overlap_confirmed=bool(data.get("overlap_confirmed")),
            timeouts_known=bool(data.get("timeouts_known")),
        )


@dataclass
class Player:
    id: str
    name: str
    role: str
    base_slot: Optional[int] = None
    receive_primary: bool = False
    sets_when: str = "never"
    can_backup_set: bool = False
    backup_rank: int = 9
    setting_verified: bool = False
    jersey: str = ""
    private_note: str = ""

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "base_slot": self.base_slot,
            "receive_primary": self.receive_primary,
            "sets_when": self.sets_when,
            "can_backup_set": self.can_backup_set,
            "backup_rank": self.backup_rank,
            "setting_verified": self.setting_verified,
            "jersey": self.jersey,
            "private_note": self.private_note,
        }

    @staticmethod
    def from_json(data: dict) -> "Player":
        slot = data.get("base_slot")
        return Player(
            id=data["id"],
            name=data["name"],
            role=data.get("role") or "other",
            base_slot=None if slot in (None, "") else int(slot),
            receive_primary=bool(data.get("receive_primary")),
            sets_when=data.get("sets_when") or "never",
            can_backup_set=bool(data.get("can_backup_set")),
            backup_rank=int(data.get("backup_rank") or 9),
            setting_verified=bool(data.get("setting_verified")),
            jersey=data.get("jersey") or "",
            private_note=data.get("private_note") or "",
        )


@dataclass
class Pair:
    id: str
    a: str
    b: str
    status: str
    notes: str = ""

    def key(self) -> frozenset[str]:
        return frozenset((self.a, self.b))

    def matches(self, left: str, right: str) -> bool:
        return left != right and {left, right} == {self.a, self.b}

    def to_json(self) -> dict:
        return {"id": self.id, "a": self.a, "b": self.b, "status": self.status, "notes": self.notes}

    @staticmethod
    def from_json(data: dict) -> "Pair":
        return Pair(data["id"], data["a"], data["b"], data.get("status") or "candidate", data.get("notes") or "")


@dataclass
class ServePlan:
    rotation: int
    target_type: str = "unset"
    target_label: str = ""
    backup_label: str = ""
    block_note: str = ""
    evidence: str = "暂无对手证据"

    def to_json(self) -> dict:
        return {
            "rotation": self.rotation,
            "target_type": self.target_type,
            "target_label": self.target_label,
            "backup_label": self.backup_label,
            "block_note": self.block_note,
            "evidence": self.evidence,
        }

    @staticmethod
    def from_json(data: dict) -> "ServePlan":
        return ServePlan(
            rotation=int(data["rotation"]),
            target_type=data.get("target_type") or "unset",
            target_label=data.get("target_label") or "",
            backup_label=data.get("backup_label") or "",
            block_note=data.get("block_note") or "",
            evidence=data.get("evidence") or "暂无对手证据",
        )


@dataclass
class SubWindow:
    player_out: str
    player_in: str
    active_rotations: tuple[int, ...]
    notes: str = ""

    def to_json(self) -> dict:
        return {
            "player_out": self.player_out,
            "player_in": self.player_in,
            "active_rotations": list(self.active_rotations),
            "notes": self.notes,
        }

    @staticmethod
    def from_json(data: dict) -> "SubWindow":
        return SubWindow(
            data["player_out"],
            data["player_in"],
            tuple(int(n) for n in data.get("active_rotations") or []),
            data.get("notes") or "",
        )


@dataclass
class TeamPlan:
    team_id: str
    name: str
    rules: Rules
    players: dict[str, Player] = field(default_factory=dict)
    pairs: list[Pair] = field(default_factory=list)
    serve_plans: dict[int, ServePlan] = field(default_factory=dict)
    sub_windows: list[SubWindow] = field(default_factory=list)
    calls: dict[str, str] = field(default_factory=lambda: {"in_system": "全开", "half": "两翼", "out": "高球"})
    guidance: list[dict] = field(default_factory=list)
    board_note: str = ""
    notes: str = ""

    def base_order(self) -> list[str]:
        slotted = [player for player in self.players.values() if player.base_slot]
        slotted.sort(key=lambda player: player.base_slot or 0)
        if [player.base_slot for player in slotted] != [1, 2, 3, 4, 5, 6]:
            return []
        return [player.id for player in slotted]

    def name_of(self, player_id: Optional[str]) -> str:
        if not player_id:
            return "未指定"
        player = self.players.get(player_id)
        return player.name if player else player_id

    def to_json(self) -> dict:
        return {
            "team_id": self.team_id,
            "name": self.name,
            "rules": self.rules.to_json(),
            "players": [player.to_json() for player in self.players.values()],
            "pairs": [pair.to_json() for pair in self.pairs],
            "serve_plans": [plan.to_json() for plan in self.serve_plans.values()],
            "sub_windows": [window.to_json() for window in self.sub_windows],
            "calls": self.calls,
            "guidance": self.guidance,
            "board_note": self.board_note,
            "notes": self.notes,
        }

    @staticmethod
    def from_json(data: dict) -> "TeamPlan":
        players = [Player.from_json(item) for item in data.get("players") or []]
        return TeamPlan(
            team_id=data["team_id"],
            name=data["name"],
            rules=Rules.from_json(data.get("rules") or {}),
            players={player.id: player for player in players},
            pairs=[Pair.from_json(item) for item in data.get("pairs") or []],
            serve_plans={int(item["rotation"]): ServePlan.from_json(item) for item in data.get("serve_plans") or []},
            sub_windows=[SubWindow.from_json(item) for item in data.get("sub_windows") or []],
            calls=data.get("calls") or {"in_system": "全开", "half": "两翼", "out": "高球"},
            guidance=list(data.get("guidance") or []),
            board_note=data.get("board_note") or "",
            notes=data.get("notes") or "",
        )


@dataclass
class Reminder:
    text: str
    urgent: bool


@dataclass
class Suggestion:
    situation: str
    action: str
    basis: str
    confidence: str
    alternative: str
    switch: str
    source: str
    blocked: bool


@dataclass
class SlotView:
    slot: int
    slot_name: str
    row: str
    origin_id: str
    occupant_id: str
    origin_name: str
    occupant_name: str
    is_sub: bool
    wing: str
    wing_note: str
    badges: list[str]


@dataclass
class RotationCard:
    rotation: int
    setter_id: Optional[str]
    setter_name: str
    setter_note: str
    backup_id: Optional[str]
    backup_name: str
    backup_note: str
    front_attack: list[dict]
    receivers: list[dict]
    seam: str
    short_ball: str
    position_note: str
    movement_serve: str
    movement_receive: str
    reminders: list[Reminder]
    extra_notes: list[str]
    serve: ServePlan
    slots: dict[int, SlotView]
    conflicts: list[str]
    structural: list[str]


@dataclass
class MatchState:
    rotation: int
    serving: str
    score_us: int
    score_them: int
    overrides: dict[str, str]
    set_index: int
    trusted: bool
    history_gap: bool
    score_tracked: bool
    mode: str
    locked_pairs: set[frozenset[str]]
    sub_count: int
    sub_count_uncertain: bool = False
    conflicts: list[str] = field(default_factory=list)
    structural: list[str] = field(default_factory=list)
    origins: dict[int, str] = field(default_factory=dict)
    occupants: dict[int, str] = field(default_factory=dict)

    @property
    def advice_blocked(self) -> bool:
        return (not self.trusted) or bool(self.conflicts)
