#!/usr/bin/env python3
"""Build docs/placement_user_guide.pdf (bilingual student + advisor tutorial)."""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from placement_user_guide_pdf import build_placement_user_guide_pdf


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--site",
        default=os.environ.get("PLACEMENT_GUIDE_SITE_BASE", "https://novel-prep-sat-0f9q.onrender.com"),
        help="Public site base URL printed in the guide",
    )
    parser.add_argument(
        "--out",
        default=os.path.join(ROOT, "docs", "placement_user_guide.pdf"),
    )
    args = parser.parse_args()
    data = build_placement_user_guide_pdf(args.site)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "wb") as f:
        f.write(data)
    print(f"Wrote {args.out} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
