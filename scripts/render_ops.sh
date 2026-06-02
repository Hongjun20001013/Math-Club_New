#!/usr/bin/env bash
# Manage Render services: delete duplicate, deploy latest to novel-prep-sat.
#
# One-time: Render Dashboard → Account Settings → API Keys → Create
#   export RENDER_API_KEY='rnd_...'
#
# Usage:
#   ./scripts/render_ops.sh              # list services + deploy sat
#   ./scripts/render_ops.sh --delete-math   # also delete novel-prep-math
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API="${RENDER_API_KEY:-}"
BASE="https://api.render.com/v1"
KEEP_NAME="${RENDER_KEEP_SERVICE:-novel-prep-sat}"
DELETE_NAME="${RENDER_DELETE_SERVICE:-novel-prep-math}"
DELETE_MATH=false

for arg in "$@"; do
  case "$arg" in
    --delete-math) DELETE_MATH=true ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

if [[ -z "$API" ]]; then
  echo "Error: set RENDER_API_KEY (Render Dashboard → Account Settings → API Keys)."
  exit 1
fi

api() {
  local method="$1"
  local path="$2"
  shift 2
  curl -sS -X "$method" \
    -H "Authorization: Bearer $API" \
    -H "Accept: application/json" \
    -H "Content-Type: application/json" \
    "$@" \
    "${BASE}${path}"
}

echo "==> Render services in your account:"
services_json="$(api GET "/services?limit=50")"
python3 - <<'PY' "$services_json" "$KEEP_NAME" "$DELETE_NAME"
import json, sys
data = json.loads(sys.argv[1])
keep, delete = sys.argv[2], sys.argv[3]
items = data if isinstance(data, list) else data.get("items") or data.get("services") or []
if not items:
    print("  (none found — check API key)")
    sys.exit(0)
ids = {}
for wrap in items:
    svc = wrap.get("service") or wrap
    name = svc.get("name") or svc.get("slug") or "?"
    sid = svc.get("id") or "?"
    repo = (svc.get("repo") or svc.get("serviceDetails") or {})
    if isinstance(repo, dict):
        repo = repo.get("repo") or repo.get("url") or "?"
    branch = svc.get("branch") or "?"
    st = svc.get("suspended") or svc.get("serviceDetails") or {}
    print(f"  • {name}  id={sid}")
    print(f"      repo={repo}  branch={branch}")
    ids[name] = sid
print()
if keep not in ids:
    print(f"Warning: '{keep}' not found.")
if delete in ids:
    print(f"Duplicate '{delete}' id={ids[delete]} — pass --delete-math to remove.")
PY

get_id() {
  local name="$1"
  python3 - <<'PY' "$services_json" "$name"
import json, sys
data = json.loads(sys.argv[1])
name = sys.argv[2]
items = data if isinstance(data, list) else data.get("items") or []
for wrap in items:
    svc = wrap.get("service") or wrap
    if (svc.get("name") or svc.get("slug")) == name:
        print(svc.get("id") or "")
        break
PY
}

SAT_ID="$(get_id "$KEEP_NAME" || true)"
MATH_ID="$(get_id "$DELETE_NAME" || true)"

if [[ "$DELETE_MATH" == true ]]; then
  if [[ -z "$MATH_ID" ]]; then
    echo "==> No service named '$DELETE_NAME' — nothing to delete."
  else
    echo "==> Deleting '$DELETE_NAME' ($MATH_ID)..."
    code="$(curl -sS -o /dev/null -w "%{http_code}" -X DELETE \
      -H "Authorization: Bearer $API" \
      "${BASE}/services/${MATH_ID}")"
    if [[ "$code" == "204" || "$code" == "200" ]]; then
      echo "    Deleted."
    else
      echo "    Delete failed (HTTP $code)."
      exit 1
    fi
  fi
fi

if [[ -z "$SAT_ID" ]]; then
  echo "Error: service '$KEEP_NAME' not found. Create it from render.yaml or Dashboard."
  exit 1
fi

echo "==> Service detail for '$KEEP_NAME'..."
svc_json="$(api GET "/services/${SAT_ID}")"
python3 - <<'PY' "$svc_json" "$KEEP_NAME"
import json, sys
raw = sys.argv[1]
name = sys.argv[2]
try:
    wrap = json.loads(raw)
except json.JSONDecodeError:
    print("  (could not parse service JSON)")
    sys.exit(0)
svc = wrap.get("service") or wrap
suspended = svc.get("suspended")
if suspended is None:
    details = svc.get("serviceDetails") or {}
    suspended = details.get("suspended")
url = svc.get("serviceDetails", {}).get("url") if isinstance(svc.get("serviceDetails"), dict) else None
url = url or svc.get("url") or "(see Dashboard)"
print(f"  url={url}")
print(f"  suspended={suspended}")
if suspended:
    print("  Service is suspended — will resume before deploy.")
PY

is_suspended="$(python3 - <<'PY' "$svc_json"
import json, sys
try:
    wrap = json.loads(sys.argv[1])
except json.JSONDecodeError:
    print("false")
    raise SystemExit
svc = wrap.get("service") or wrap
s = svc.get("suspended")
if s is None:
    s = (svc.get("serviceDetails") or {}).get("suspended")
print("true" if s else "false")
PY
)"

if [[ "$is_suspended" == "true" ]]; then
  echo "==> Resuming '$KEEP_NAME' ($SAT_ID)..."
  resume_code="$(curl -sS -o /tmp/render_resume.json -w "%{http_code}" -X POST \
    -H "Authorization: Bearer $API" \
    -H "Accept: application/json" \
    "${BASE}/services/${SAT_ID}/resume")"
  if [[ "$resume_code" == "202" || "$resume_code" == "200" ]]; then
    echo "    Resume accepted (HTTP $resume_code). Waiting 15s for instance..."
    sleep 15
  else
    echo "    Resume failed (HTTP $resume_code):"
    cat /tmp/render_resume.json 2>/dev/null || true
    echo
    echo "    Resume manually: Render Dashboard → $KEEP_NAME → Resume"
  fi
fi

echo "==> Triggering deploy on '$KEEP_NAME' ($SAT_ID)..."
deploy_resp="$(api POST "/services/${SAT_ID}/deploys" -d '{"clearCache":"clear"}')"
echo "$deploy_resp" | python3 - <<'PY'
import json, sys
try:
    d = json.load(sys.stdin)
except json.JSONDecodeError:
    print(sys.stdin.read() or "(empty response)")
    sys.exit(0)
dep = d.get("deploy") or d
print("    deploy id:", dep.get("id") or dep.get("deploy", {}).get("id") or "?")
print("    status:", dep.get("status") or "?")
PY

echo
echo "==> Done. Wait 2–5 min, then check:"
echo "  https://novel-prep-sat-0f9q.onrender.com/guide"
echo "  https://novel-prep-sat-0f9q.onrender.com/health/db"
