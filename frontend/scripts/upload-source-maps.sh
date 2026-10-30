#!/usr/bin/env bash
# Uploads source maps to S3, as required by CloudWatch

set -euo pipefail

bucket="${1:-}"
release="${2:-}"

if [ -z "$bucket" ]; then
  echo "No bucket given, so no source maps uploaded"
  exit 0
fi

if [ -z "$release" ]; then
  echo "No release id given" >&2
  exit 1
fi

if [ ! -d .next/static ]; then
  echo "No build found: run this from frontend/ after pnpm build" >&2
  exit 1
fi

staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT

count=0

while IFS= read -r -d '' script; do
  last_line="$(tail -n 1 "$script")"
  map_name="${last_line#//# sourceMappingURL=}"

  if [ "$map_name" = "$last_line" ]; then
    continue
  fi

  map="$(dirname "$script")/$map_name"

  if [ ! -f "$map" ]; then
    echo "Skipping $script: its source map $map_name is missing" >&2
    continue
  fi

  destination="$staging/$release/_next/${script#.next/}.map"

  mkdir -p "$(dirname "$destination")"
  cp "$map" "$destination"
  count=$((count + 1))
done < <(find .next/static -name '*.js' -print0)

if [ "$count" -eq 0 ]; then
  echo "No source maps found, so none uploaded"
  exit 0
fi

(cd / && aws s3 cp "$staging" "s3://$bucket" --recursive --only-show-errors)

echo "Uploaded $count source maps for release $release to s3://$bucket"
