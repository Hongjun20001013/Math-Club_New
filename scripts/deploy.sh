#!/usr/bin/env bash
# Push local changes to GitHub; Render auto-deploys from Math-Club_New (main).
#
#   origin → https://github.com/Hongjun20001013/Math-Club_New.git
#   Render → novel-prep-sat @ https://novel-prep-sat-0f9q.onrender.com
# Usage:
#   ./scripts/deploy.sh
#   ./scripts/deploy.sh "Update hard drill layout"
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REMOTE="${DEPLOY_REMOTE:-origin}"
BRANCH="${DEPLOY_BRANCH:-main}"
MSG="${1:-Site update $(date +%Y-%m-%d)}"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Error: not a git repository."
  exit 1
fi

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  echo "Error: remote '$REMOTE' not found."
  echo "Add it with: git remote add origin https://github.com/Hongjun20001013/Math-Club_New.git"
  exit 1
fi

echo "==> Changes to deploy:"
git status --short
echo

if [ -z "$(git status --porcelain)" ]; then
  echo "Nothing to deploy (working tree clean)."
  exit 0
fi

git add -A
git commit -m "$MSG"
git push "$REMOTE" "$BRANCH"

echo
echo "==> Pushed to $REMOTE/$BRANCH"
echo "Render will rebuild in ~2–5 minutes."
echo
echo "Check deploy status:"
echo "  https://dashboard.render.com"
echo
echo "After Deploy live, refresh your site:"
echo "  https://novel-prep-sat-0f9q.onrender.com/guide"
echo "  https://novelmathprep.org"
