#!/usr/bin/env bash
# Rebuild bundled PDF deps (fpdf2 + defusedxml + fonttools, no Pillow — text-only reports).
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf third_party
python3 -m pip install -q --target third_party --no-deps fpdf2==2.8.7 defusedxml fonttools
rm -rf third_party/bin third_party/share 2>/dev/null || true
echo "Done. third_party/ is ready (~$(du -sh third_party | cut -f1))."
