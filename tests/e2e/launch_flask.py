#!/usr/bin/env python3
"""Local Flask launcher for skill-loop browser E2E. Never used in production."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

port = int(os.environ.get("E2E_PORT", "8899"))
from app import app  # noqa: E402

flag = (os.environ.get("SKILL_LOOP_PILOT") or "").strip().lower() in ("1", "true", "yes", "on")
app.config["SKILL_LOOP_PILOT"] = flag
app.config["TESTING"] = False
app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
