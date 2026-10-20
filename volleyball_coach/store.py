"""Local match log. The file is the recovery copy if the page is closed."""

from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from volleyball_coach.model import (
    ABILITY_LABEL,
    Pair,
    Player,
    RotationScheme,
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

CREATE TABLE IF NOT EXISTS schemes (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL,
  name TEXT NOT NULL,
  order_json TEXT NOT NULL,
  is_default INTEGER NOT NULL DEFAULT 0,
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
  block_touch TEXT,
  defense_quality TEXT,
  attack_result TEXT,
  severe_error TEXT,
  severe_kind TEXT NOT NULL DEFAULT '',
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

CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id TEXT NOT NULL,
  rally_id INTEGER NOT NULL,
  client_token TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  team_side TEXT NOT NULL,
  player_id TEXT NOT NULL DEFAULT '',
  skill TEXT NOT NULL,
  result TEXT NOT NULL,
  quality TEXT NOT NULL DEFAULT '',
  start_zone TEXT NOT NULL DEFAULT '',
  attack_line TEXT NOT NULL DEFAULT '',
  end_zone TEXT NOT NULL DEFAULT '',
  phase TEXT NOT NULL DEFAULT '',
  set_quality TEXT NOT NULL DEFAULT '',
  video_timestamp TEXT NOT NULL DEFAULT '',
  confirm_status TEXT NOT NULL DEFAULT 'confirmed',
  lineup_source TEXT NOT NULL DEFAULT 'live',
  lineup_json TEXT NOT NULL DEFAULT '[]',
  view_flip INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE(match_id, client_token)
);

CREATE TABLE IF NOT EXISTS action_players (
  action_id INTEGER NOT NULL,
  player_id TEXT NOT NULL,
  PRIMARY KEY (action_id, player_id)
);

CREATE TABLE IF NOT EXISTS opponents (
  id TEXT PRIMARY KEY,
  match_id TEXT NOT NULL,
  jersey TEXT NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  UNIQUE(match_id, jersey)
);

CREATE TABLE IF NOT EXISTS tactics (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL,
  scheme_id TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  notes TEXT NOT NULL DEFAULT '',
  parent_id TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  published_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS tactic_marks (
  tactic_id TEXT NOT NULL REFERENCES tactics(id),
  rotation INTEGER NOT NULL,
  phase TEXT NOT NULL,
  player_id TEXT NOT NULL,
  slot INTEGER NOT NULL,
  x REAL NOT NULL,
  y REAL NOT NULL,
  PRIMARY KEY (tactic_id, rotation, phase, slot)
);

CREATE TABLE IF NOT EXISTS tactic_notes (
  tactic_id TEXT NOT NULL REFERENCES tactics(id),
  rotation INTEGER NOT NULL,
  kind TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (tactic_id, rotation, kind)
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._backup_once()
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self._seed_mens_if_empty()

    def close(self) -> None:
        self.conn.close()

    def _backup_once(self) -> None:
        """Copy an existing log before the action tables are added. A second start does not overwrite it."""
        path = Path(self.path)
        if not path.exists() or path.stat().st_size == 0:
            return
        probe = sqlite3.connect(self.path)
        try:
            found = probe.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'actions'"
            ).fetchone()
        finally:
            probe.close()
        if found:
            return
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            shutil.copy2(path, backup)

    def _ensure_column(self, table: str, column: str, declaration: str) -> None:
        have = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in have:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def _migrate(self) -> None:
        for column in ("block_touch", "defense_quality", "attack_result", "severe_error", "severe_kind"):
            self._ensure_column("rallies", column, "TEXT")
        self._ensure_column("rallies", "status", "TEXT NOT NULL DEFAULT 'closed'")
        self._ensure_column("rallies", "legacy", "INTEGER NOT NULL DEFAULT 1")
        self._ensure_column("rallies", "score_us_before", "INTEGER")
        self._ensure_column("rallies", "score_them_before", "INTEGER")
        self._ensure_column("rallies", "score_us_after", "INTEGER")
        self._ensure_column("rallies", "score_them_after", "INTEGER")
        self._ensure_column("rallies", "their_rotation", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("rallies", "rally_index", "INTEGER")
        self._ensure_column("rallies", "scored", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("rallies", "lineup_source", "TEXT NOT NULL DEFAULT 'legacy'")
        self._ensure_column("matches", "record_depth", "TEXT NOT NULL DEFAULT 'light'")
        self._ensure_column("matches", "sample_scope", "TEXT NOT NULL DEFAULT 'sample'")
        self._ensure_column("matches", "tactic_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("matches", "tactic_json", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("rallies", "plan_execution", "TEXT NOT NULL DEFAULT ''")
        self._backfill_schemes()
        self.conn.commit()

    def _backfill_schemes(self) -> None:
        teams = self.conn.execute("SELECT id FROM teams").fetchall()
        for team in teams:
            count = self.conn.execute(
                "SELECT COUNT(*) AS n FROM schemes WHERE team_id = ?",
                (team["id"],),
            ).fetchone()["n"]
            if count:
                continue
            rows = self.conn.execute(
                "SELECT id, base_slot FROM players WHERE team_id = ? AND base_slot IS NOT NULL",
                (team["id"],),
            ).fetchall()
            by_slot: dict[int, str] = {}
            duplicate = False
            for row in rows:
                slot = row["base_slot"]
                if slot in by_slot:
                    duplicate = True
                    break
                by_slot[slot] = row["id"]
            if duplicate or sorted(by_slot) != [1, 2, 3, 4, 5, 6]:
                continue
            order = [by_slot[number] for number in range(1, 7)]
            if team["id"] == MENS_TEAM_ID:
                scheme_id = "scheme-mens-62"
                name = "6-2 默认"
            else:
                scheme_id = new_id("scheme")
                name = "当前首发"
            self.conn.execute(
                """
                INSERT INTO schemes (id, team_id, name, order_json, is_default, notes)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (
                    scheme_id,
                    team["id"],
                    name,
                    json.dumps(order),
                    "从现有首发槽生成。另存的方案不会改这一套，除非把它设成默认。",
                ),
            )

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
        for scheme in plan.schemes:
            self._write_scheme(plan.team_id, scheme)
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
        schemes = []
        for row in self.conn.execute(
            "SELECT * FROM schemes WHERE team_id = ? ORDER BY is_default DESC, name",
            (team_id,),
        ):
            schemes.append(
                RotationScheme(
                    id=row["id"],
                    name=row["name"],
                    order=list(json.loads(row["order_json"])),
                    is_default=bool(row["is_default"]),
                    notes=row["notes"],
                )
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
            schemes=schemes,
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
        self._align_default_scheme(team_id)
        self.conn.commit()

    def _align_default_scheme(self, team_id: str) -> None:
        rows = self.conn.execute(
            "SELECT id, base_slot FROM players WHERE team_id = ? AND base_slot BETWEEN 1 AND 6",
            (team_id,),
        ).fetchall()
        by_slot: dict[int, str] = {}
        for row in rows:
            slot = int(row["base_slot"])
            if slot in by_slot:
                return
            by_slot[slot] = row["id"]
        if sorted(by_slot) != [1, 2, 3, 4, 5, 6]:
            return
        order = [by_slot[number] for number in range(1, 7)]
        payload = json.dumps(order)
        current = self.conn.execute(
            "SELECT id, order_json FROM schemes WHERE team_id = ? AND is_default = 1",
            (team_id,),
        ).fetchone()
        if current is None:
            self.conn.execute(
                """
                INSERT INTO schemes (id, team_id, name, order_json, is_default, notes)
                VALUES (?, ?, '当前首发', ?, 1, ?)
                """,
                (new_id("scheme"), team_id, payload, "由六个首发槽生成。"),
            )
            return
        if list(json.loads(current["order_json"])) != order:
            self.conn.execute("UPDATE schemes SET order_json = ? WHERE id = ?", (payload, current["id"]))

    def _write_scheme(self, team_id: str, scheme: RotationScheme) -> None:
        self.conn.execute(
            """
            INSERT INTO schemes (id, team_id, name, order_json, is_default, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              order_json=excluded.order_json,
              is_default=excluded.is_default,
              notes=excluded.notes
            """,
            (
                scheme.id,
                team_id,
                scheme.name,
                json.dumps(scheme.order),
                int(scheme.is_default),
                scheme.notes,
            ),
        )

    def save_scheme(self, team_id: str, scheme: RotationScheme) -> None:
        if scheme.is_default:
            self.conn.execute("UPDATE schemes SET is_default = 0 WHERE team_id = ?", (team_id,))
        self._write_scheme(team_id, scheme)
        if scheme.is_default:
            self.conn.execute("UPDATE players SET base_slot = NULL WHERE team_id = ?", (team_id,))
            for index, player_id in enumerate(scheme.order, start=1):
                self.conn.execute(
                    "UPDATE players SET base_slot = ? WHERE team_id = ? AND id = ?",
                    (index, team_id, player_id),
                )
        self.conn.commit()

    def copy_scheme(self, team_id: str, scheme_id: str, name: str) -> str:
        row = self.conn.execute(
            "SELECT name, order_json, notes FROM schemes WHERE team_id = ? AND id = ?",
            (team_id, scheme_id),
        ).fetchone()
        if row is None:
            raise ValueError("找不到这套阵容。")
        copied = RotationScheme(
            id=new_id("scheme"),
            name=name.strip() or f"副本 · {row['name']}",
            order=list(json.loads(row["order_json"])),
            is_default=False,
            notes=row["notes"] or "",
        )
        self._write_scheme(team_id, copied)
        self.conn.commit()
        return copied.id

    def tactics_for_team(self, team_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM tactics WHERE team_id = ? ORDER BY created_at",
            (team_id,),
        )
        return [dict(row) for row in rows]

    def tactic(self, tactic_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM tactics WHERE id = ?", (tactic_id,)).fetchone()
        return dict(row) if row else None

    def tactic_marks(self, tactic_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT rotation, phase, player_id, slot, x, y
            FROM tactic_marks WHERE tactic_id = ?
            ORDER BY rotation, phase, slot
            """,
            (tactic_id,),
        )
        return [dict(row) for row in rows]

    def tactic_notes(self, tactic_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT rotation, kind, body FROM tactic_notes WHERE tactic_id = ? ORDER BY rotation, kind",
            (tactic_id,),
        )
        return [dict(row) for row in rows]

    def create_tactic(self, team_id: str, scheme_id: str, name: str, marks: list[dict]) -> str:
        tactic_id = new_id("tactic")
        self.conn.execute(
            """
            INSERT INTO tactics (id, team_id, scheme_id, name, status, notes, parent_id, created_at, published_at)
            VALUES (?, ?, ?, ?, 'draft', '', '', ?, '')
            """,
            (tactic_id, team_id, scheme_id, name.strip(), now()),
        )
        self._insert_marks(tactic_id, marks)
        self.conn.commit()
        return tactic_id

    def _insert_marks(self, tactic_id: str, marks: list[dict]) -> None:
        self.conn.executemany(
            """
            INSERT INTO tactic_marks (tactic_id, rotation, phase, player_id, slot, x, y)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    tactic_id,
                    int(mark["rotation"]),
                    mark["phase"],
                    mark["player_id"],
                    int(mark["slot"]),
                    float(mark["x"]),
                    float(mark["y"]),
                )
                for mark in marks
            ],
        )

    def duplicate_tactic(self, tactic_id: str, name: str = "") -> str:
        source = self.tactic(tactic_id)
        if source is None:
            raise ValueError("找不到这套战术。")
        copied_id = new_id("tactic")
        self.conn.execute(
            """
            INSERT INTO tactics (id, team_id, scheme_id, name, status, notes, parent_id, created_at, published_at)
            VALUES (?, ?, ?, ?, 'draft', ?, ?, ?, '')
            """,
            (
                copied_id,
                source["team_id"],
                source["scheme_id"],
                name.strip() or f"副本 · {source['name']}",
                source["notes"] or "",
                source["id"],
                now(),
            ),
        )
        self._insert_marks(copied_id, self.tactic_marks(tactic_id))
        for note in self.tactic_notes(tactic_id):
            self.conn.execute(
                "INSERT INTO tactic_notes (tactic_id, rotation, kind, body) VALUES (?, ?, ?, ?)",
                (copied_id, note["rotation"], note["kind"], note["body"]),
            )
        self.conn.commit()
        return copied_id

    def publish_tactic(self, tactic_id: str) -> None:
        source = self.tactic(tactic_id)
        if source is None:
            raise ValueError("找不到这套战术。")
        if source["status"] == "published":
            return
        self.conn.execute(
            "UPDATE tactics SET status = 'published', published_at = ? WHERE id = ?",
            (now(), tactic_id),
        )
        self.conn.commit()

    def _require_draft(self, tactic_id: str) -> dict:
        source = self.tactic(tactic_id)
        if source is None:
            raise ValueError("找不到这套战术。")
        if source["status"] != "draft":
            raise ValueError("已发布的版本不能改。先另存成草稿。")
        return source

    def update_tactic_mark(self, tactic_id: str, rotation: int, phase: str, slot: int, player_id: str, x: float, y: float) -> tuple[float, float]:
        self._require_draft(tactic_id)
        row = self.conn.execute(
            """
            SELECT player_id FROM tactic_marks
            WHERE tactic_id = ? AND rotation = ? AND phase = ? AND slot = ?
            """,
            (tactic_id, rotation, phase, slot),
        ).fetchone()
        if row is None:
            raise ValueError("这一格还没有站位。")
        if row["player_id"] != player_id:
            raise ValueError("拖动不能改轮转身份。")
        x = max(0.0, min(100.0, round(float(x), 1)))
        y = max(0.0, min(100.0, round(float(y), 1)))
        self.conn.execute(
            """
            UPDATE tactic_marks SET x = ?, y = ?
            WHERE tactic_id = ? AND rotation = ? AND phase = ? AND slot = ?
            """,
            (x, y, tactic_id, rotation, phase, slot),
        )
        self.conn.commit()
        return x, y

    def save_tactic_notes(self, tactic_id: str, rotation: int, notes: dict[str, str]) -> None:
        self._require_draft(tactic_id)
        for kind, body in notes.items():
            self.conn.execute(
                """
                INSERT INTO tactic_notes (tactic_id, rotation, kind, body)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tactic_id, rotation, kind) DO UPDATE SET body = excluded.body
                """,
                (tactic_id, rotation, kind, body.strip()),
            )
        self.conn.commit()

    def sync_tactic_players(self, tactic_id: str, occupants: dict[int, dict[int, str]]) -> None:
        self._require_draft(tactic_id)
        for rotation, slots in occupants.items():
            for slot, player_id in slots.items():
                self.conn.execute(
                    """
                    UPDATE tactic_marks SET player_id = ?
                    WHERE tactic_id = ? AND rotation = ? AND slot = ?
                    """,
                    (player_id, tactic_id, rotation, slot),
                )
        self.conn.commit()

    def delete_scheme(self, team_id: str, scheme_id: str) -> bool:
        row = self.conn.execute(
            "SELECT is_default FROM schemes WHERE team_id = ? AND id = ?",
            (team_id, scheme_id),
        ).fetchone()
        if row is None or row["is_default"]:
            return False
        self.conn.execute("DELETE FROM schemes WHERE team_id = ? AND id = ?", (team_id, scheme_id))
        self.conn.commit()
        return True

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

    def latest_live_match(self):
        return self.conn.execute(
            """
            SELECT id, team_id, opponent FROM matches
            WHERE status = 'live' ORDER BY created_at DESC LIMIT 1
            """
        ).fetchone()

    def create_match(
        self,
        plan: TeamPlan,
        opponent: str,
        mode: str,
        locked_pairs: set[frozenset[str]],
        rotation: int,
        serving: str,
        tactic_id: str = "",
        tactic_json: str = "",
    ) -> str:
        match_id = new_id("m")
        created = now()
        self.conn.execute(
            """
            INSERT INTO matches (
              id, team_id, opponent, mode, status, locked_pairs_json, plan_json, created_at, tactic_id, tactic_json
            ) VALUES (?, ?, ?, ?, 'live', ?, ?, ?, ?, ?)
            """,
            (
                match_id,
                plan.team_id,
                opponent.strip(),
                mode,
                json.dumps([sorted(pair) for pair in locked_pairs], ensure_ascii=False),
                json.dumps(plan.to_json(), ensure_ascii=False),
                created,
                tactic_id,
                tactic_json,
            ),
        )
        self.append_event(
            match_id,
            "set_start",
            {"rotation": rotation, "serving": serving, "set_index": 1, "mode": mode, "overrides": {}},
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

    def append_event(self, match_id: str, event_type: str, payload: dict, created: str | None = None) -> int:
        current = self.conn.execute("SELECT COALESCE(MAX(seq), 0) AS n FROM events WHERE match_id = ?", (match_id,)).fetchone()
        seq = int(current["n"]) + 1
        self.conn.execute(
            "INSERT INTO events (match_id, seq, type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (match_id, seq, event_type, json.dumps(payload, ensure_ascii=False), created or now()),
        )
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
              match_id, set_number, rotation, serving_side, winner, pass_quality,
              block_touch, defense_quality, attack_result, severe_error, severe_kind,
              server_label,
              target_type, target_label, actual_receiver, actual_zone, lineup_json, bench_json,
              video_timestamp, sample_scope, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match_id,
                fields["set_number"],
                fields["rotation"],
                fields["serving_side"],
                fields["winner"],
                fields["pass_quality"],
                fields.get("block_touch"),
                fields.get("defense_quality"),
                fields.get("attack_result"),
                fields.get("severe_error"),
                fields.get("severe_kind") or "",
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

    def set_recording(self, match_id: str, depth: str, scope: str) -> None:
        self.conn.execute(
            "UPDATE matches SET record_depth = ?, sample_scope = ? WHERE id = ?",
            (depth, scope, match_id),
        )
        self.conn.commit()

    def open_rally(self, match_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM rallies WHERE match_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
            (match_id,),
        ).fetchone()
        return self._rally(row) if row else None

    def rally(self, match_id: str, rally_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM rallies WHERE match_id = ? AND id = ?",
            (match_id, rally_id),
        ).fetchone()
        return self._rally(row) if row else None

    def _rally(self, row: sqlite3.Row) -> dict:
        item = dict(row)
        item["bench_ids"] = json.loads(row["bench_json"] or "[]")
        item["lineup"] = json.loads(row["lineup_json"] or "[]")
        return item

    def insert_open_rally(self, match_id: str, fields: dict) -> int:
        index = self.conn.execute(
            "SELECT COALESCE(MAX(rally_index), 0) + 1 AS n FROM rallies WHERE match_id = ?",
            (match_id,),
        ).fetchone()["n"]
        cursor = self.conn.execute(
            """
            INSERT INTO rallies (
              match_id, set_number, rotation, serving_side, winner, pass_quality,
              server_label, target_type, target_label, actual_receiver, actual_zone,
              lineup_json, bench_json, video_timestamp, sample_scope, note, created_at,
              status, legacy, score_us_before, score_them_before, their_rotation,
              rally_index, scored, lineup_source
            ) VALUES (?, ?, ?, ?, '', NULL, '', '', '', '', '', ?, '[]', '', ?, '', ?, 'open', 0, ?, ?, 'unknown', ?, 0, 'live')
            """,
            (
                match_id,
                fields["set_number"],
                fields["rotation"],
                fields["serving_side"],
                json.dumps(fields["lineup"], ensure_ascii=False),
                fields["sample_scope"],
                now(),
                fields["score_us_before"],
                fields["score_them_before"],
                index,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def close_rally(
        self,
        match_id: str,
        rally_id: int,
        winner: str,
        score_us_after: int,
        score_them_after: int,
        scored: int,
        plan_execution: str = "",
    ) -> None:
        if plan_execution not in ("hit", "miss", "unchecked"):
            plan_execution = ""
        self.conn.execute(
            """
            UPDATE rallies
            SET status = 'closed', winner = ?, score_us_after = ?, score_them_after = ?, scored = ?, plan_execution = ?
            WHERE match_id = ? AND id = ?
            """,
            (winner, score_us_after, score_them_after, scored, plan_execution, match_id, rally_id),
        )
        self.conn.commit()

    def reopen_rally(self, match_id: str, rally_id: int) -> None:
        self.conn.execute(
            """
            UPDATE rallies
            SET status = 'open', winner = '', score_us_after = NULL, score_them_after = NULL, scored = 0, plan_execution = ''
            WHERE match_id = ? AND id = ?
            """,
            (match_id, rally_id),
        )
        self.conn.commit()

    def add_action(self, match_id: str, fields: dict, participants: list[str]) -> tuple[int, bool]:
        existing = self.conn.execute(
            "SELECT id FROM actions WHERE match_id = ? AND client_token = ?",
            (match_id, fields["client_token"]),
        ).fetchone()
        if existing:
            return int(existing["id"]), False
        sequence = self.conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS n FROM actions WHERE rally_id = ?",
            (fields["rally_id"],),
        ).fetchone()["n"]
        cursor = self.conn.execute(
            """
            INSERT INTO actions (
              match_id, rally_id, client_token, sequence, team_side, player_id, skill, result,
              quality, start_zone, attack_line, end_zone, phase, set_quality, video_timestamp,
              confirm_status, lineup_source, lineup_json, view_flip, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match_id,
                fields["rally_id"],
                fields["client_token"],
                sequence,
                fields["team_side"],
                fields.get("player_id") or "",
                fields["skill"],
                fields["result"],
                fields.get("quality") or "",
                fields.get("start_zone") or "",
                fields.get("attack_line") or "",
                fields.get("end_zone") or "",
                fields.get("phase") or "",
                fields.get("set_quality") or "",
                fields.get("video_timestamp") or "",
                fields.get("confirm_status") or "confirmed",
                fields.get("lineup_source") or "live",
                json.dumps(fields.get("lineup") or [], ensure_ascii=False),
                1 if fields.get("view_flip") else 0,
                now(),
            ),
        )
        action_id = int(cursor.lastrowid)
        for player_id in dict.fromkeys(participants):
            if player_id:
                self.conn.execute(
                    "INSERT OR IGNORE INTO action_players (action_id, player_id) VALUES (?, ?)",
                    (action_id, player_id),
                )
        self.conn.commit()
        return action_id, True

    def update_action(self, match_id: str, action_id: int, fields: dict, participants: list[str] | None) -> bool:
        row = self.conn.execute(
            "SELECT id FROM actions WHERE match_id = ? AND id = ?",
            (match_id, action_id),
        ).fetchone()
        if row is None:
            return False
        self.conn.execute(
            """
            UPDATE actions
            SET player_id = ?, result = ?, quality = ?, start_zone = ?, attack_line = ?, end_zone = ?,
                phase = ?, set_quality = ?, video_timestamp = ?, view_flip = ?, confirm_status = ?
            WHERE match_id = ? AND id = ?
            """,
            (
                fields.get("player_id") or "",
                fields["result"],
                fields.get("quality") or "",
                fields.get("start_zone") or "",
                fields.get("attack_line") or "",
                fields.get("end_zone") or "",
                fields.get("phase") or "",
                fields.get("set_quality") or "",
                fields.get("video_timestamp") or "",
                1 if fields.get("view_flip") else 0,
                fields.get("confirm_status") or "confirmed",
                match_id,
                action_id,
            ),
        )
        if participants is not None:
            self.conn.execute("DELETE FROM action_players WHERE action_id = ?", (action_id,))
            for player_id in dict.fromkeys(participants):
                if player_id:
                    self.conn.execute(
                        "INSERT INTO action_players (action_id, player_id) VALUES (?, ?)",
                        (action_id, player_id),
                    )
        self.conn.commit()
        return True

    def delete_action(self, match_id: str, action_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM actions WHERE match_id = ? AND id = ?",
            (match_id, action_id),
        ).fetchone()
        if row is None:
            return None
        self.conn.execute("DELETE FROM action_players WHERE action_id = ?", (action_id,))
        self.conn.execute("DELETE FROM actions WHERE id = ?", (action_id,))
        rally_id = row["rally_id"]
        remaining = self.conn.execute(
            "SELECT COUNT(*) AS n FROM actions WHERE rally_id = ?",
            (rally_id,),
        ).fetchone()["n"]
        rally = self.conn.execute("SELECT status FROM rallies WHERE id = ?", (rally_id,)).fetchone()
        removed_rally = False
        if rally and rally["status"] == "open" and remaining == 0:
            self.conn.execute("DELETE FROM rallies WHERE id = ?", (rally_id,))
            removed_rally = True
        self.conn.commit()
        item = dict(row)
        item["removed_rally"] = removed_rally
        return item

    def actions_for(self, match_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT actions.*, rallies.set_number, rallies.rotation, rallies.sample_scope,
                   rallies.status AS rally_status, rallies.legacy, rallies.serving_side, rallies.winner
            FROM actions
            JOIN rallies ON rallies.id = actions.rally_id
            WHERE actions.match_id = ?
            ORDER BY actions.rally_id, actions.sequence, actions.id
            """,
            (match_id,),
        )
        parsed = []
        for row in rows:
            item = dict(row)
            item["lineup"] = json.loads(row["lineup_json"] or "[]")
            item["view_flip"] = bool(row["view_flip"])
            parsed.append(item)
        if not parsed:
            return parsed
        ids = [item["id"] for item in parsed]
        marks = {item["id"]: [] for item in parsed}
        query = f"SELECT action_id, player_id FROM action_players WHERE action_id IN ({','.join('?' for _ in ids)})"
        for link in self.conn.execute(query, ids):
            marks[link["action_id"]].append(link["player_id"])
        for item in parsed:
            item["participants"] = marks[item["id"]]
        return parsed

    def opponents_for(self, match_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, jersey, name FROM opponents WHERE match_id = ? ORDER BY CAST(jersey AS INTEGER), jersey",
            (match_id,),
        )
        return [dict(row) for row in rows]

    def ensure_opponent(self, match_id: str, jersey: str, name: str = "") -> dict:
        jersey = jersey.strip()
        row = self.conn.execute(
            "SELECT id, jersey, name FROM opponents WHERE match_id = ? AND jersey = ?",
            (match_id, jersey),
        ).fetchone()
        if row:
            return dict(row)
        opponent_id = new_id("opp")
        self.conn.execute(
            "INSERT INTO opponents (id, match_id, jersey, name) VALUES (?, ?, ?, ?)",
            (opponent_id, match_id, jersey, name.strip()),
        )
        self.conn.commit()
        return {"id": opponent_id, "jersey": jersey, "name": name.strip()}


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
    plan.serve_plans = live.serve_plans or plan.serve_plans
    return plan


def locked_pairs_of(match: sqlite3.Row) -> set[frozenset[str]]:
    return {frozenset(pair) for pair in json.loads(match["locked_pairs_json"])}


def ability_label(code: str) -> str:
    return ABILITY_LABEL.get(code, code)


MENS_ID = MENS_TEAM_ID
