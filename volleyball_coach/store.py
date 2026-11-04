"""Local match log. The file is the recovery copy if the page is closed."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from volleyball_coach.model import (
    ABILITY_LABEL,
    Pair,
    Player,
    Rules,
    ServePlan,
    SubWindow,
    TeamPlan,
)
from volleyball_coach.seed import MENS_ABILITIES, MENS_TEAM_ID, build_mens_plan


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS teams (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  board_note TEXT NOT NULL DEFAULT '',
  calls_json TEXT NOT NULL,
  guidance_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rules (
  team_id TEXT PRIMARY KEY REFERENCES teams(id),
  no_back_row_attack INTEGER NOT NULL,
  no_libero INTEGER NOT NULL,
  fixed_pair_subs INTEGER NOT NULL,
  unlimited_subs INTEGER NOT NULL,
  max_subs INTEGER,
  pair_lock_scope TEXT NOT NULL,
  overlap_confirmed INTEGER NOT NULL,
  timeouts_known INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL REFERENCES teams(id),
  display_name TEXT NOT NULL,
  jersey TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL,
  base_slot INTEGER,
  receive_primary INTEGER NOT NULL,
  sets_when TEXT NOT NULL,
  can_backup_set INTEGER NOT NULL,
  backup_rank INTEGER NOT NULL,
  setting_verified INTEGER NOT NULL,
  private_note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS abilities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT NOT NULL REFERENCES players(id),
  skill TEXT NOT NULL,
  label TEXT NOT NULL,
  context TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL,
  UNIQUE(player_id, skill)
);

CREATE TABLE IF NOT EXISTS pairs (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL REFERENCES teams(id),
  player_a TEXT NOT NULL,
  player_b TEXT NOT NULL,
  status TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS serve_plans (
  team_id TEXT NOT NULL,
  rotation INTEGER NOT NULL,
  target_type TEXT NOT NULL,
  target_label TEXT NOT NULL DEFAULT '',
  backup_label TEXT NOT NULL DEFAULT '',
  block_note TEXT NOT NULL DEFAULT '',
  evidence TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (team_id, rotation)
);

CREATE TABLE IF NOT EXISTS sub_windows (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  team_id TEXT NOT NULL,
  player_out TEXT NOT NULL,
  player_in TEXT NOT NULL,
  active_rotations TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS matches (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL,
  opponent TEXT NOT NULL DEFAULT '',
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  locked_pairs_json TEXT NOT NULL,
  plan_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  type TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(match_id, seq)
);

CREATE TABLE IF NOT EXISTS rallies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id TEXT NOT NULL,
  set_number INTEGER NOT NULL,
  rotation INTEGER,
  serving_side TEXT NOT NULL,
  winner TEXT NOT NULL,
  pass_quality TEXT,
  server_label TEXT NOT NULL DEFAULT '',
  target_type TEXT NOT NULL DEFAULT '',
  target_label TEXT NOT NULL DEFAULT '',
  actual_receiver TEXT NOT NULL DEFAULT '',
  actual_zone TEXT NOT NULL DEFAULT '',
  lineup_json TEXT NOT NULL DEFAULT '[]',
  bench_json TEXT NOT NULL DEFAULT '[]',
  video_timestamp TEXT NOT NULL DEFAULT '',
  sample_scope TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quick_rallies (
  id TEXT PRIMARY KEY,
  match_id TEXT NOT NULL,
  set_index INTEGER NOT NULL,
  status TEXT NOT NULL,
  serving TEXT NOT NULL,
  rotation INTEGER NOT NULL,
  score_us_before INTEGER NOT NULL,
  score_them_before INTEGER NOT NULL,
  winner TEXT NOT NULL DEFAULT '',
  point_seq INTEGER,
  completeness TEXT NOT NULL,
  server_id TEXT NOT NULL DEFAULT '',
  phase TEXT NOT NULL,
  focus_player TEXT NOT NULL DEFAULT '',
  focus_start TEXT NOT NULL DEFAULT '',
  focus_line TEXT NOT NULL DEFAULT '',
  focus_tag TEXT NOT NULL DEFAULT '',
  flag INTEGER NOT NULL DEFAULT 0,
  lineup_confirmed INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quick_actions (
  id TEXT PRIMARY KEY,
  rally_id TEXT NOT NULL,
  match_id TEXT NOT NULL,
  ord INTEGER NOT NULL,
  side TEXT NOT NULL,
  player_id TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL,
  result TEXT NOT NULL,
  start TEXT NOT NULL DEFAULT '',
  line TEXT NOT NULL DEFAULT '',
  count_only INTEGER NOT NULL DEFAULT 0,
  tag TEXT NOT NULL DEFAULT '',
  voided INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS op_tokens (
  token TEXT PRIMARY KEY,
  match_id TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self._seed_mens_if_empty()

    def close(self) -> None:
        self.conn.close()

    def _migrate(self) -> None:
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(quick_actions)")}
        if columns and "voided" not in columns:
            self.conn.execute("ALTER TABLE quick_actions ADD COLUMN voided INTEGER NOT NULL DEFAULT 0")
            self.conn.commit()

    def _seed_mens_if_empty(self) -> None:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM teams").fetchone()
        if row["n"]:
            return
        self.insert_plan(build_mens_plan())
        for player_id, skills in MENS_ABILITIES.items():
            for skill in skills:
                self.conn.execute(
                    """
                    INSERT INTO abilities (player_id, skill, label, context, updated_at)
                    VALUES (?, ?, 'unknown', '', ?)
                    """,
                    (player_id, skill, now()),
                )
        self.conn.commit()

    def insert_plan(self, plan: TeamPlan) -> None:
        self.conn.execute(
            """
            INSERT INTO teams (id, name, notes, board_note, calls_json, guidance_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan.team_id,
                plan.name,
                plan.notes,
                plan.board_note,
                json.dumps(plan.calls, ensure_ascii=False),
                json.dumps(plan.guidance, ensure_ascii=False),
                now(),
            ),
        )
        self._write_rules(plan.team_id, plan.rules)
        for player in plan.players.values():
            self._write_player(plan.team_id, player)
        for pair in plan.pairs:
            self.conn.execute(
                "INSERT INTO pairs (id, team_id, player_a, player_b, status, notes) VALUES (?, ?, ?, ?, ?, ?)",
                (pair.id, plan.team_id, pair.a, pair.b, pair.status, pair.notes),
            )
        for serve in plan.serve_plans.values():
            self._write_serve(plan.team_id, serve)
        for window in plan.sub_windows:
            self.conn.execute(
                """
                INSERT INTO sub_windows (team_id, player_out, player_in, active_rotations, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (plan.team_id, window.player_out, window.player_in, json.dumps(list(window.active_rotations)), window.notes),
            )
        self.conn.commit()

    def _write_rules(self, team_id: str, rules: Rules) -> None:
        self.conn.execute(
            """
            INSERT INTO rules (
              team_id, no_back_row_attack, no_libero, fixed_pair_subs, unlimited_subs,
              max_subs, pair_lock_scope, overlap_confirmed, timeouts_known
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id) DO UPDATE SET
              no_back_row_attack=excluded.no_back_row_attack,
              no_libero=excluded.no_libero,
              fixed_pair_subs=excluded.fixed_pair_subs,
              unlimited_subs=excluded.unlimited_subs,
              max_subs=excluded.max_subs,
              pair_lock_scope=excluded.pair_lock_scope,
              overlap_confirmed=excluded.overlap_confirmed,
              timeouts_known=excluded.timeouts_known
            """,
            (
                team_id,
                int(rules.no_back_row_attack),
                int(rules.no_libero),
                int(rules.fixed_pair_subs),
                int(rules.unlimited_subs),
                rules.max_subs,
                rules.pair_lock_scope,
                int(rules.overlap_confirmed),
                int(rules.timeouts_known),
            ),
        )

    def _write_player(self, team_id: str, player: Player) -> None:
        self.conn.execute(
            """
            INSERT INTO players (
              id, team_id, display_name, jersey, role, base_slot, receive_primary,
              sets_when, can_backup_set, backup_rank, setting_verified, private_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              display_name=excluded.display_name,
              jersey=excluded.jersey,
              role=excluded.role,
              base_slot=excluded.base_slot,
              receive_primary=excluded.receive_primary,
              sets_when=excluded.sets_when,
              can_backup_set=excluded.can_backup_set,
              backup_rank=excluded.backup_rank,
              setting_verified=excluded.setting_verified,
              private_note=excluded.private_note
            """,
            (
                player.id,
                team_id,
                player.name,
                player.jersey,
                player.role,
                player.base_slot,
                int(player.receive_primary),
                player.sets_when,
                int(player.can_backup_set),
                player.backup_rank,
                int(player.setting_verified),
                player.private_note,
            ),
        )

    def _write_serve(self, team_id: str, serve: ServePlan) -> None:
        self.conn.execute(
            """
            INSERT INTO serve_plans (
              team_id, rotation, target_type, target_label, backup_label, block_note, evidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id, rotation) DO UPDATE SET
              target_type=excluded.target_type,
              target_label=excluded.target_label,
              backup_label=excluded.backup_label,
              block_note=excluded.block_note,
              evidence=excluded.evidence
            """,
            (
                team_id,
                serve.rotation,
                serve.target_type,
                serve.target_label,
                serve.backup_label,
                serve.block_note,
                serve.evidence,
            ),
        )

    def list_teams(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT id, name, notes FROM teams ORDER BY created_at"))

    def load_plan(self, team_id: str) -> TeamPlan | None:
        team = self.conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
        if team is None:
            return None
        rules_row = self.conn.execute("SELECT * FROM rules WHERE team_id = ?", (team_id,)).fetchone()
        players = {}
        for row in self.conn.execute("SELECT * FROM players WHERE team_id = ? ORDER BY COALESCE(base_slot, 99), display_name", (team_id,)):
            players[row["id"]] = Player(
                id=row["id"],
                name=row["display_name"],
                role=row["role"],
                base_slot=row["base_slot"],
                receive_primary=bool(row["receive_primary"]),
                sets_when=row["sets_when"],
                can_backup_set=bool(row["can_backup_set"]),
                backup_rank=row["backup_rank"],
                setting_verified=bool(row["setting_verified"]),
                jersey=row["jersey"],
                private_note=row["private_note"],
            )
        pairs = [
            Pair(row["id"], row["player_a"], row["player_b"], row["status"], row["notes"])
            for row in self.conn.execute("SELECT * FROM pairs WHERE team_id = ?", (team_id,))
        ]
        serve_plans = {}
        for row in self.conn.execute("SELECT * FROM serve_plans WHERE team_id = ? ORDER BY rotation", (team_id,)):
            serve_plans[row["rotation"]] = ServePlan(
                rotation=row["rotation"],
                target_type=row["target_type"],
                target_label=row["target_label"],
                backup_label=row["backup_label"],
                block_note=row["block_note"],
                evidence=row["evidence"],
            )
        windows = []
        for row in self.conn.execute("SELECT * FROM sub_windows WHERE team_id = ?", (team_id,)):
            windows.append(
                SubWindow(row["player_out"], row["player_in"], tuple(json.loads(row["active_rotations"])), row["notes"])
            )
        rules = Rules(
            no_back_row_attack=bool(rules_row["no_back_row_attack"]),
            no_libero=bool(rules_row["no_libero"]),
            fixed_pair_subs=bool(rules_row["fixed_pair_subs"]),
            unlimited_subs=bool(rules_row["unlimited_subs"]),
            max_subs=rules_row["max_subs"],
            pair_lock_scope=rules_row["pair_lock_scope"],
            overlap_confirmed=bool(rules_row["overlap_confirmed"]),
            timeouts_known=bool(rules_row["timeouts_known"]),
        )
        return TeamPlan(
            team_id=team["id"],
            name=team["name"],
            rules=rules,
            players=players,
            pairs=pairs,
            serve_plans=serve_plans,
            sub_windows=windows,
            calls=json.loads(team["calls_json"]),
            guidance=json.loads(team["guidance_json"]),
            board_note=team["board_note"],
            notes=team["notes"],
        )

    def abilities_for(self, team_id: str) -> dict[str, list[sqlite3.Row]]:
        rows = self.conn.execute(
            """
            SELECT abilities.* FROM abilities
            JOIN players ON players.id = abilities.player_id
            WHERE players.team_id = ?
            ORDER BY abilities.skill
            """,
            (team_id,),
        )
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(row["player_id"], []).append(row)
        return grouped

    def save_rules(self, team_id: str, rules: Rules) -> None:
        self._write_rules(team_id, rules)
        self.conn.commit()

    def save_team_meta(self, team_id: str, notes: str, calls: dict[str, str]) -> None:
        self.conn.execute(
            "UPDATE teams SET notes = ?, calls_json = ? WHERE id = ?",
            (notes, json.dumps(calls, ensure_ascii=False), team_id),
        )
        self.conn.commit()

    def replace_locked_pairs(self, match_id: str, locked_pairs: set[frozenset[str]]) -> None:
        self.conn.execute(
            "UPDATE matches SET locked_pairs_json = ? WHERE id = ?",
            (json.dumps([sorted(pair) for pair in locked_pairs], ensure_ascii=False), match_id),
        )
        self.conn.commit()

    def delete_rally(self, match_id: str, rally_id: int) -> None:
        self.conn.execute("DELETE FROM rallies WHERE match_id = ? AND id = ?", (match_id, rally_id))
        self.conn.commit()

    def save_player(self, team_id: str, player: Player) -> None:
        self._write_player(team_id, player)
        self.conn.commit()

    def save_ability(self, player_id: str, skill: str, label: str) -> None:
        if label not in ABILITY_LABEL:
            raise ValueError("能力标签只能是尚未验证、需要保护或稳定可用。")
        self.conn.execute(
            """
            INSERT INTO abilities (player_id, skill, label, context, updated_at)
            VALUES (?, ?, ?, '', ?)
            ON CONFLICT(player_id, skill) DO UPDATE SET label=excluded.label, updated_at=excluded.updated_at
            """,
            (player_id, skill.strip(), label, now()),
        )
        self.conn.commit()

    def save_pair(self, team_id: str, pair: Pair) -> None:
        self.conn.execute(
            """
            INSERT INTO pairs (id, team_id, player_a, player_b, status, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              player_a=excluded.player_a,
              player_b=excluded.player_b,
              status=excluded.status,
              notes=excluded.notes
            """,
            (pair.id, team_id, pair.a, pair.b, pair.status, pair.notes),
        )
        self.conn.commit()

    def delete_pair(self, team_id: str, pair_id: str) -> None:
        self.conn.execute("DELETE FROM pairs WHERE team_id = ? AND id = ?", (team_id, pair_id))
        self.conn.commit()

    def save_serve(self, team_id: str, serve: ServePlan) -> None:
        self._write_serve(team_id, serve)
        self.conn.commit()

    def list_matches(self, team_id: str) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT id, opponent, mode, status, created_at FROM matches WHERE team_id = ? ORDER BY created_at DESC",
                (team_id,),
            )
        )

    def create_match(
        self,
        plan: TeamPlan,
        opponent: str,
        mode: str,
        locked_pairs: set[frozenset[str]],
        rotation: int,
        serving: str,
        *,
        require_lineup: bool = True,
    ) -> str:
        match_id = new_id("m")
        created = now()
        self.conn.execute(
            """
            INSERT INTO matches (id, team_id, opponent, mode, status, locked_pairs_json, plan_json, created_at)
            VALUES (?, ?, ?, ?, 'live', ?, ?, ?)
            """,
            (
                match_id,
                plan.team_id,
                opponent.strip(),
                mode,
                json.dumps([sorted(pair) for pair in locked_pairs], ensure_ascii=False),
                json.dumps(plan.to_json(), ensure_ascii=False),
                created,
            ),
        )
        self.append_event(
            match_id,
            "set_start",
            {
                "rotation": rotation,
                "serving": serving,
                "set_index": 1,
                "mode": mode,
                "overrides": {},
                "require_lineup": require_lineup,
                "serving_confirmed": require_lineup,
            },
            created=created,
        )
        return match_id

    def get_match(self, match_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()

    def events_for(self, match_id: str) -> list[dict]:
        rows = self.conn.execute("SELECT seq, type, payload, created_at FROM events WHERE match_id = ? ORDER BY seq", (match_id,))
        return [
            {"seq": row["seq"], "type": row["type"], "payload": json.loads(row["payload"]), "created_at": row["created_at"]}
            for row in rows
        ]

    def append_event(self, match_id: str, event_type: str, payload: dict, created: str | None = None, commit: bool = True) -> int:
        current = self.conn.execute("SELECT COALESCE(MAX(seq), 0) AS n FROM events WHERE match_id = ?", (match_id,)).fetchone()
        seq = int(current["n"]) + 1
        self.conn.execute(
            "INSERT INTO events (match_id, seq, type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (match_id, seq, event_type, json.dumps(payload, ensure_ascii=False), created or now()),
        )
        if commit:
            self.conn.commit()
        return seq

    def set_match_status(self, match_id: str, status: str) -> None:
        self.conn.execute("UPDATE matches SET status = ? WHERE id = ?", (status, match_id))
        self.conn.commit()

    def set_match_mode(self, match_id: str, mode: str) -> None:
        self.conn.execute("UPDATE matches SET mode = ? WHERE id = ?", (mode, match_id))
        self.conn.commit()

    def rallies_for(self, match_id: str) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM rallies WHERE match_id = ? ORDER BY id", (match_id,))
        parsed = []
        for row in rows:
            item = dict(row)
            item["bench_ids"] = json.loads(row["bench_json"])
            item["lineup"] = json.loads(row["lineup_json"])
            parsed.append(item)
        return parsed

    def add_rally(self, match_id: str, fields: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO rallies (
              match_id, set_number, rotation, serving_side, winner, pass_quality, server_label,
              target_type, target_label, actual_receiver, actual_zone, lineup_json, bench_json,
              video_timestamp, sample_scope, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match_id,
                fields["set_number"],
                fields["rotation"],
                fields["serving_side"],
                fields["winner"],
                fields["pass_quality"],
                fields["server_label"],
                fields["target_type"],
                fields["target_label"],
                fields["actual_receiver"],
                fields["actual_zone"],
                json.dumps(fields["lineup"], ensure_ascii=False),
                json.dumps(fields["bench_ids"], ensure_ascii=False),
                fields["video_timestamp"],
                fields["sample_scope"],
                fields["note"],
                now(),
            ),
        )
        self.conn.commit()

    def list_live_matches(self) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT matches.id, matches.opponent, matches.team_id, matches.created_at, teams.name AS team_name
                FROM matches JOIN teams ON teams.id = matches.team_id
                WHERE matches.status = 'live'
                ORDER BY matches.created_at DESC
                """
            )
        )

    def _rally_from_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "match_id": row["match_id"],
            "set_index": row["set_index"],
            "status": row["status"],
            "serving": row["serving"],
            "rotation": row["rotation"],
            "score_us_before": row["score_us_before"],
            "score_them_before": row["score_them_before"],
            "winner": row["winner"],
            "point_seq": row["point_seq"],
            "completeness": row["completeness"],
            "server_id": row["server_id"],
            "phase": row["phase"],
            "focus_player": row["focus_player"],
            "focus_start": row["focus_start"],
            "focus_line": row["focus_line"],
            "focus_tag": row["focus_tag"],
            "flag": row["flag"],
            "lineup_confirmed": row["lineup_confirmed"],
            "created_at": row["created_at"],
        }

    def _action_from_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "rally_id": row["rally_id"],
            "match_id": row["match_id"],
            "ord": row["ord"],
            "side": row["side"],
            "player_id": row["player_id"],
            "kind": row["kind"],
            "result": row["result"],
            "start": row["start"],
            "line": row["line"],
            "count_only": row["count_only"],
            "tag": row["tag"],
            "voided": row["voided"] if "voided" in row.keys() else 0,
        }

    def quick_rallies(self, match_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM quick_rallies WHERE match_id = ? ORDER BY created_at, id",
            (match_id,),
        )
        return [self._rally_from_row(row) for row in rows]

    def quick_actions(self, match_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM quick_actions WHERE match_id = ? ORDER BY ord, id",
            (match_id,),
        )
        return [self._action_from_row(row) for row in rows if not row["voided"]]

    def open_quick_rally(self, match_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM quick_rallies WHERE match_id = ? AND status = 'open' ORDER BY rowid DESC LIMIT 1",
            (match_id,),
        ).fetchone()
        return self._rally_from_row(row) if row else None

    def actions_for_rally(self, rally_id: str) -> list[dict]:
        if not rally_id:
            return []
        rows = self.conn.execute(
            "SELECT * FROM quick_actions WHERE rally_id = ? AND voided = 0 ORDER BY ord",
            (rally_id,),
        )
        return [self._action_from_row(row) for row in rows]

    def rally_by_id(self, rally_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM quick_rallies WHERE id = ?", (rally_id,)).fetchone()
        return self._rally_from_row(row) if row else None

    def latest_action(self, match_id: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT * FROM quick_actions
            WHERE match_id = ? AND voided = 0
            ORDER BY rowid DESC LIMIT 1
            """,
            (match_id,),
        ).fetchone()
        return self._action_from_row(row) if row else None

    def void_action(self, action_id: str) -> None:
        self.conn.execute("UPDATE quick_actions SET voided = 1 WHERE id = ?", (action_id,))

    def reopen_rally(self, rally_id: str) -> None:
        self.conn.execute(
            """
            UPDATE quick_rallies
            SET status = 'open', winner = '', point_seq = NULL, completeness = 'open', phase = 'choose'
            WHERE id = ?
            """,
            (rally_id,),
        )

    def update_latest_set_start(self, match_id: str, *, serving: str, serving_confirmed: bool) -> None:
        row = self.conn.execute(
            """
            SELECT seq, payload FROM events
            WHERE match_id = ? AND type = 'set_start'
            ORDER BY seq DESC LIMIT 1
            """,
            (match_id,),
        ).fetchone()
        if row is None:
            return
        payload = json.loads(row["payload"])
        payload["serving"] = serving
        payload["serving_confirmed"] = serving_confirmed
        self.conn.execute(
            "UPDATE events SET payload = ? WHERE match_id = ? AND seq = ?",
            (json.dumps(payload, ensure_ascii=False), match_id, row["seq"]),
        )

    def rename_team(self, team_id: str, name: str) -> None:
        self.conn.execute("UPDATE teams SET name = ? WHERE id = ?", (name, team_id))
        self.conn.commit()

    def set_set_court(self, match_id: str, player_ids: list[str]) -> None:
        """Who is on the floor for the current set. The next set can be a different list."""
        row = self.conn.execute(
            """
            SELECT seq, payload FROM events
            WHERE match_id = ? AND type = 'set_start'
            ORDER BY seq DESC LIMIT 1
            """,
            (match_id,),
        ).fetchone()
        if row is None:
            return
        payload = json.loads(row["payload"])
        payload["court"] = player_ids
        self.conn.execute(
            "UPDATE events SET payload = ? WHERE match_id = ? AND seq = ?",
            (json.dumps(payload, ensure_ascii=False), match_id, row["seq"]),
        )
        self.conn.commit()

    def mark_line(self, match_id: str, line: str) -> bool:
        row = self.conn.execute(
            """
            SELECT id FROM quick_actions
            WHERE match_id = ? AND voided = 0 AND kind = 'opp'
            ORDER BY rowid DESC LIMIT 1
            """,
            (match_id,),
        ).fetchone()
        if row is None:
            return False
        self.conn.execute("UPDATE quick_actions SET line = ? WHERE id = ?", (line, row["id"]))
        self.conn.commit()
        return True

    def last_scored_rally(self, match_id: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT * FROM quick_rallies
            WHERE match_id = ? AND status = 'scored'
            ORDER BY point_seq DESC LIMIT 1
            """,
            (match_id,),
        ).fetchone()
        return self._rally_from_row(row) if row else None

    def void_rally_for_point(self, match_id: str, point_seq: int) -> None:
        self.conn.execute(
            "UPDATE quick_rallies SET status = 'void' WHERE match_id = ? AND point_seq = ?",
            (match_id, point_seq),
        )
        self.conn.commit()

    def persist_tap(
        self,
        match_id: str,
        token: str,
        rally: dict,
        new_actions: list[dict],
        *,
        winner: str | None,
    ) -> bool:
        """One transaction. A repeated token does not add another point or action."""
        try:
            self.conn.execute(
                "INSERT INTO op_tokens (token, match_id, created_at) VALUES (?, ?, ?)",
                (token, match_id, now()),
            )
        except sqlite3.IntegrityError:
            self.conn.rollback()
            return False
        rally_id = rally.get("id") or new_id("q")
        created = now()
        if rally.get("id"):
            self.conn.execute(
                """
                UPDATE quick_rallies SET
                  status = ?, winner = ?, completeness = ?, server_id = ?, phase = ?,
                  focus_player = ?, focus_start = ?, focus_line = ?, focus_tag = ?, flag = ?
                WHERE id = ?
                """,
                (
                    rally["status"],
                    rally.get("winner") or "",
                    rally.get("completeness") or "open",
                    rally.get("server_id") or "",
                    rally.get("phase") or "done",
                    rally.get("focus_player") or "",
                    rally.get("focus_start") or "",
                    rally.get("focus_line") or "",
                    rally.get("focus_tag") or "",
                    int(rally.get("flag") or 0),
                    rally_id,
                ),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO quick_rallies (
                  id, match_id, set_index, status, serving, rotation, score_us_before, score_them_before,
                  winner, point_seq, completeness, server_id, phase, focus_player, focus_start, focus_line,
                  focus_tag, flag, lineup_confirmed, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rally_id,
                    match_id,
                    int(rally["set_index"]),
                    rally["status"],
                    rally["serving"],
                    int(rally["rotation"]),
                    int(rally["score_us_before"]),
                    int(rally["score_them_before"]),
                    rally.get("winner") or "",
                    rally.get("completeness") or "open",
                    rally.get("server_id") or "",
                    rally.get("phase") or "pass_player",
                    rally.get("focus_player") or "",
                    rally.get("focus_start") or "",
                    rally.get("focus_line") or "",
                    rally.get("focus_tag") or "",
                    int(rally.get("flag") or 0),
                    int(rally.get("lineup_confirmed") or 0),
                    created,
                ),
            )
        current = self.conn.execute("SELECT COALESCE(MAX(ord), 0) AS n FROM quick_actions WHERE rally_id = ?", (rally_id,)).fetchone()
        order = int(current["n"])
        for action in new_actions:
            order += 1
            self.conn.execute(
                """
                INSERT INTO quick_actions (
                  id, rally_id, match_id, ord, side, player_id, kind, result, start, line, count_only, tag, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("a"),
                    rally_id,
                    match_id,
                    order,
                    action["side"],
                    action.get("player_id") or "",
                    action["kind"],
                    action["result"],
                    action.get("start") or "",
                    action.get("line") or "",
                    int(action.get("count_only") or 0),
                    action.get("tag") or "",
                    created,
                ),
            )
        if winner:
            seq = self.append_event(match_id, "point", {"winner": winner, "rally_id": rally_id}, commit=False)
            self.conn.execute(
                "UPDATE quick_rallies SET point_seq = ?, winner = ?, status = 'scored' WHERE id = ?",
                (seq, winner, rally_id),
            )
        elif rally.get("status") == "discarded":
            self.conn.execute("DELETE FROM quick_actions WHERE rally_id = ?", (rally_id,))
            self.conn.execute("DELETE FROM quick_rallies WHERE id = ?", (rally_id,))
        self.conn.commit()
        return True

    def attach_action(self, match_id: str, token: str, rally_id: str, action: dict) -> bool:
        try:
            self.conn.execute(
                "INSERT INTO op_tokens (token, match_id, created_at) VALUES (?, ?, ?)",
                (token, match_id, now()),
            )
        except sqlite3.IntegrityError:
            self.conn.rollback()
            return False
        current = self.conn.execute("SELECT COALESCE(MAX(ord), 0) AS n FROM quick_actions WHERE rally_id = ?", (rally_id,)).fetchone()
        self.conn.execute(
            """
            INSERT INTO quick_actions (
              id, rally_id, match_id, ord, side, player_id, kind, result, start, line, count_only, tag, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', '', ?, ?, ?)
            """,
            (
                new_id("a"),
                rally_id,
                match_id,
                int(current["n"]) + 1,
                action["side"],
                action.get("player_id") or "",
                action["kind"],
                action["result"],
                int(action.get("count_only") or 0),
                action.get("tag") or "",
                now(),
            ),
        )
        self.conn.execute(
            """
            UPDATE quick_rallies
            SET completeness = 'complete'
            WHERE id = ? AND completeness IN ('score_only', 'pending', 'open')
            """,
            (rally_id,),
        )
        self.conn.commit()
        return True

    def edit_reception(self, match_id: str, token: str, action_id: str, result: str) -> bool:
        try:
            self.conn.execute(
                "INSERT INTO op_tokens (token, match_id, created_at) VALUES (?, ?, ?)",
                (token, match_id, now()),
            )
        except sqlite3.IntegrityError:
            self.conn.rollback()
            return False
        self.conn.execute("UPDATE quick_actions SET result = ? WHERE id = ? AND match_id = ?", (result, action_id, match_id))
        self.conn.commit()
        return True


def plan_for_match(store: Store, match: sqlite3.Row) -> TeamPlan:
    """Rules and windows stay as they were at the whistle. Names and serve targets follow later edits."""
    plan = TeamPlan.from_json(json.loads(match["plan_json"]))
    live = store.load_plan(match["team_id"])
    if live is None:
        return plan
    for player_id, player in plan.players.items():
        current = live.players.get(player_id)
        if current:
            player.name = current.name
            player.jersey = current.jersey
            player.role = current.role
            player.receive_primary = current.receive_primary
    for player_id, player in live.players.items():
        if player_id not in plan.players:
            plan.players[player_id] = player
    plan.name = live.name
    plan.serve_plans = live.serve_plans or plan.serve_plans
    return plan


def locked_pairs_of(match: sqlite3.Row) -> set[frozenset[str]]:
    return {frozenset(pair) for pair in json.loads(match["locked_pairs_json"])}


def ability_label(code: str) -> str:
    return ABILITY_LABEL.get(code, code)


MENS_ID = MENS_TEAM_ID
