#!/usr/bin/env python3
"""Stable A/B assignment for the skill-loop usability pilot.

Arm is stored in skill_loop_assignments on first assignment and never recomputed
from hash after that row exists. Changing this file cannot reassign existing users.

Admins/teachers are excluded from experiment analysis. They can still be forced
into A or B via assignment_source='admin' for QA.
"""
from __future__ import annotations

import hashlib
from typing import Literal

Arm = Literal["A", "B"]

EXPERIMENT_ID = "skill_loop_v1_linear_rate_remaining"
SALT_VERSION = "v1"
# Local/dev default only. Production must set SKILL_LOOP_ASSIGN_SALT.
DEFAULT_DEV_SALT = "np-skill-loop-local-dev-salt-v1"


def assignment_hash_hex(experiment_id: str, user_id: int, salt: str) -> str:
    msg = f"{experiment_id}|{int(user_id)}|{salt}".encode("utf-8")
    return hashlib.sha256(msg).hexdigest()


def arm_from_hash(hash_hex: str) -> Arm:
    return "A" if (int(hash_hex, 16) % 2 == 0) else "B"


def propose_arm(user_id: int, salt: str, experiment_id: str = EXPERIMENT_ID) -> tuple[Arm, str]:
    digest = assignment_hash_hex(experiment_id, user_id, salt)
    return arm_from_hash(digest), digest


def is_excluded_from_analysis(role: str | None, username: str | None = None) -> bool:
    role_l = (role or "").strip().lower()
    if role_l in {"admin", "staff", "teacher", "supervisor", "test"}:
        return True
    name = (username or "").strip().lower()
    return name.startswith("test") or name.endswith("+test")
