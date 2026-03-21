#!/usr/bin/env bash
# Show implementation status of all plans at a glance.
# Parses the --<layer>--<details> filename convention and reads **Status:** headers.
set -euo pipefail

PLANS_DIR="$(cd "$(dirname "$0")/../docs/superpowers/plans" && pwd)"

printf "%-10s %-12s %-40s %s\n" "Layer" "Date" "Details" "Status"
printf "%-10s %-12s %-40s %s\n" "─────" "────" "───────" "──────"

for f in "$PLANS_DIR"/*.md; do
  base="$(basename "$f" .md)"

  # Parse filename: YYYY-MM-DD--<layer>--<details>
  if [[ "$base" =~ ^([0-9]{4}-[0-9]{2}-[0-9]{2})--([^-]+)--(.+)$ ]]; then
    date="${BASH_REMATCH[1]}"
    layer="${BASH_REMATCH[2]}"
    details="${BASH_REMATCH[3]}"
  else
    date="${base:0:10}"
    layer="???"
    details="${base:11}"
  fi

  # Extract Status from first 20 lines (macOS-compatible)
  status=$(head -20 "$f" | sed -n 's/.*\*\*Status:\*\* \(.*\)/\1/p' | head -1)
  # Truncate long status lines (e.g., Hop's detailed status)
  if [ ${#status} -gt 30 ]; then
    status="${status:0:27}..."
  fi
  [ -z "$status" ] && status="(missing)"

  printf "%-10s %-12s %-40s %s\n" "$layer" "$date" "$details" "$status"
done
