#!/usr/bin/env bash
#
# Points frontend/.env.local at the deployed backend

set -euo pipefail
cd "$(dirname "$0")/../.."

REGION="${AWS_REGION:-eu-west-2}"

APP_ID="${APP_ID:-$(aws amplify list-apps --region "$REGION" \
  --query "apps[?contains(repository,'personalised-planning')].appId" --output text)}"
case "$APP_ID" in
  ""|None|*[[:space:]]*) echo "Could not find one Amplify app. Pass APP_ID=..." >&2; exit 1 ;;
esac

BRANCH="${BRANCH:-$(aws amplify list-branches --app-id "$APP_ID" --region "$REGION" \
  --query 'branches[0].branchName' --output text)}"

# The build tags the function, so finding it needs no node_modules and no ampx.
FUNCTION=$(aws resourcegroupstaggingapi get-resources --region "$REGION" \
  --resource-type-filters lambda \
  --tag-filters "Key=pp:component,Values=backend" "Key=pp:branch,Values=$BRANCH" \
  --query 'ResourceTagMappingList[].ResourceARN' --output text)
case "$FUNCTION" in
  ""|None|*[[:space:]]*) echo "Expected one backend Lambda for branch '$BRANCH', found: ${FUNCTION:-none}" >&2; exit 1 ;;
esac

URL=$(aws lambda get-function-url-config --region "$REGION" \
  --function-name "$FUNCTION" --query FunctionUrl --output text)
KEY=$(aws amplify get-app --app-id "$APP_ID" --region "$REGION" \
  --query 'app.environmentVariables.BACKEND_API_KEY' --output text)

printf 'BACKEND_URL=%s\nBACKEND_API_KEY=%s\nBACKEND_TIMEOUT_MS=300000\nMOCK_MODE=false\n' \
  "${URL%/}" "$KEY" > frontend/.env.local

echo "frontend/.env.local now points at the deployed backend on branch $BRANCH."
