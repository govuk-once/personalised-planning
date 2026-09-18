#!/usr/bin/env bash
#
# Sets Amplify app's config + starts a build.
# Run after creating app in console, and upon agent change

set -euo pipefail
cd "$(dirname "$0")/../.."

REGION="${AWS_REGION:-eu-west-2}"

from_env() { grep -m1 "^$1=" .env 2>/dev/null | cut -d= -f2- || true; }

PLANNER="${AGENT_RUNTIME_ARN:-$(from_env AGENT_RUNTIME_ARN)}"
CHAT="${CHAT_AGENT_RUNTIME_ARN:-$(from_env CHAT_AGENT_RUNTIME_ARN)}"
[ -n "$PLANNER" ] && [ -n "$CHAT" ] || {
  echo "No agent ARNs. Put them in .env, or pass AGENT_RUNTIME_ARN and CHAT_AGENT_RUNTIME_ARN." >&2
  exit 1
}

APP_ID="${APP_ID:-$(aws amplify list-apps --region "$REGION" \
  --query "apps[?contains(repository,'personalised-planning')].appId" --output text)}"
case "$APP_ID" in
  ""|None|*[[:space:]]*) echo "Could not find one Amplify app. Pass APP_ID=..." >&2; exit 1 ;;
esac

BRANCH="${BRANCH:-$(aws amplify list-branches --app-id "$APP_ID" --region "$REGION" \
  --query 'branches[0].branchName' --output text)}"
[ -n "$BRANCH" ] && [ "$BRANCH" != "None" ] || { echo "The app has no branch." >&2; exit 1; }

EXISTING=$(aws amplify get-app --app-id "$APP_ID" --region "$REGION" \
  --query 'app.environmentVariables.BACKEND_API_KEY' --output text)
[ "$EXISTING" = "None" ] && EXISTING=""
KEY="${BACKEND_API_KEY:-${EXISTING:-$(openssl rand -hex 24)}}"

# update-app replaces the whole variable map, so merge rather than overwrite.
VARS=$(aws amplify get-app --app-id "$APP_ID" --region "$REGION" \
  --query 'app.environmentVariables' --output json |
  jq --arg k "$KEY" --arg p "$PLANNER" --arg c "$CHAT" \
    '(. // {}) | .BACKEND_API_KEY = $k | .AGENT_RUNTIME_ARN = $p | .CHAT_AGENT_RUNTIME_ARN = $c')

aws amplify update-app --app-id "$APP_ID" --region "$REGION" \
  --environment-variables "$VARS" >/dev/null

# update-app auto-starts a build that began before the change, so start a fresh
# one. Amplify refuses while another is running, hence the retry.
for _ in $(seq 20); do
  JOB=$(aws amplify start-job --app-id "$APP_ID" --branch-name "$BRANCH" \
    --job-type RELEASE --region "$REGION" --query 'jobSummary.jobId' --output text 2>/dev/null) && break
  sleep 15
done
[ -n "${JOB:-}" ] || { echo "Variables set, but no build could be started. Start one in the console." >&2; exit 1; }

echo "App $APP_ID configured. Build #$JOB started on $BRANCH."
