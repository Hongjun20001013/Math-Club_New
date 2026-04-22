#!/usr/bin/env bash
# Print the URL other devices on the same LAN should use (Flask dev server on 8888).
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8888}"
IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
if [[ -z "${IP}" ]]; then
  IP="$(ipconfig getifaddr en1 2>/dev/null || true)"
fi
if [[ -z "${IP}" ]]; then
  echo "Could not detect Wi-Fi IP (en0/en1). Check System Settings → Network → Wi-Fi → Details for your IP."
  exit 1
fi
echo "On another device (same Wi-Fi), open:"
echo "  http://${IP}:${PORT}"
echo ""
if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port ${PORT} is listening on this Mac."
    lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN | head -5
  else
    echo "Nothing is listening on port ${PORT} yet. Start the app first, e.g.:"
    echo "  cd $(pwd) && python3 app.py"
  fi
fi
