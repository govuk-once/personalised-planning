#!/usr/bin/env bash
#
# Packages backend/ for Lambda

set -euo pipefail
cd "$(dirname "$0")/../.."

BUNDLE="amplify/python-backend/.build/lambda"

rm -rf "$BUNDLE"
mkdir -p "$BUNDLE"

uv pip install --quiet --target "$BUNDLE" \
  --python-platform aarch64-manylinux2014 --python-version 3.12 \
  -r backend/pyproject.toml

cp -R backend/app "$BUNDLE/app"
cp backend/handler.py backend/log_utils.py backend/agent_mock_response.py "$BUNDLE/"
find "$BUNDLE" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

NATIVE=$(find "$BUNDLE" -name '_pydantic_core*.so' -print -quit)
file "$NATIVE" | grep -q 'ELF 64-bit.*aarch64' || {
  echo "Bundle is not Linux/arm64 — it would crash on Lambda." >&2
  exit 1
}

echo "Lambda bundle: $(du -sh "$BUNDLE" | cut -f1), Linux/arm64"
