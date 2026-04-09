#!/usr/bin/env bash
# Show implementation status of all plans at a glance.
# Parses the --<layer>--<details> filename convention and reads **Status:**/**Spec:** headers.
#
# Usage:
#   plan-status.sh              # list all plans
#   plan-status.sh --archive    # move Complete/Deployed/Closed plans to archived-plans/
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLANS_DIR="$REPO_ROOT/docs/superpowers/plans"
SPECS_DIR="$REPO_ROOT/docs/superpowers/specs"
ARCHIVE_DIR="$REPO_ROOT/docs/superpowers/archived-plans"

DO_ARCHIVE=false
if [[ "${1:-}" == "--archive" ]]; then
  DO_ARCHIVE=true
  mkdir -p "$ARCHIVE_DIR"
fi

# Collect plan files from both active and archived directories
declare -a ALL_FILES=()
declare -A IS_ARCHIVED=()

for f in "$PLANS_DIR"/*.md; do
  [ -e "$f" ] || continue
  ALL_FILES+=("$f")
  IS_ARCHIVED["$f"]="no"
done
if [ -d "$ARCHIVE_DIR" ]; then
  for f in "$ARCHIVE_DIR"/*.md; do
    [ -e "$f" ] || continue
    ALL_FILES+=("$f")
    IS_ARCHIVED["$f"]="yes"
  done
fi

# Sort by basename
mapfile -t SORTED < <(for f in "${ALL_FILES[@]}"; do echo "$(basename "$f")|$f"; done | sort | cut -d'|' -f2)

# Track warnings
WARNINGS=()

printf "%-10s %-12s %-40s %-6s %-10s %s\n" "Layer" "Date" "Details" "Spec" "Archived" "Status"
printf "%s\n" "────────── ──────────── ──────────────────────────────────────── ────── ────────── ──────"

for f in "${SORTED[@]}"; do
  base="$(basename "$f" .md)"
  archived="${IS_ARCHIVED[$f]}"

  # Parse filename: YYYY-MM-DD--<layer>--<details>
  if [[ "$base" =~ ^([0-9]{4}-[0-9]{2}-[0-9]{2})--([^-]+)--(.+)$ ]]; then
    date="${BASH_REMATCH[1]}"
    layer="${BASH_REMATCH[2]}"
    details="${BASH_REMATCH[3]}"
  else
    date="${base:0:10}"
    layer="???"
    details="${base:11}"
    WARNINGS+=("Malformed filename: $base")
  fi

  # Extract Spec reference from first 20 lines
  spec_ref=$(head -20 "$f" | sed -n 's/.*\*\*Spec:\*\* `\([^`]*\)`.*/\1/p' | head -1)
  if [ -z "$spec_ref" ]; then
    spec="no"
    WARNINGS+=("Missing **Spec:** line: $base")
  elif [ "$spec_ref" = "none" ]; then
    spec="none"
  elif [[ "$spec_ref" == willikins/* ]]; then
    spec="ext"
  elif [ -f "$REPO_ROOT/$spec_ref" ]; then
    spec="yes"
  else
    spec="MISS"
    WARNINGS+=("Broken spec ref: $base -> $spec_ref")
  fi

  # Extract Status from first 20 lines
  status=$(head -20 "$f" | sed -n 's/.*\*\*Status:\*\* \(.*\)/\1/p' | head -1)
  # Strip inline comments: "Deployed (some detail)" → "Deployed (...)"
  if [[ "$status" == *" ("* ]]; then
    status="${status%% (*} (...)"
  fi
  [ -z "$status" ] && status="(missing)"

  # Archive if requested and status qualifies
  if $DO_ARCHIVE && [[ "$archived" == "no" ]]; then
    case "$status" in
      Complete|Deployed|Closed)
        mv "$f" "$ARCHIVE_DIR/$(basename "$f")"
        archived="yes"
        ;;
    esac
  fi

  printf "%-10s %-12s %-40s %-6s %-10s %s\n" "$layer" "$date" "$details" "$spec" "$archived" "$status"
done

# Print warnings if any
if [ ${#WARNINGS[@]} -gt 0 ]; then
  echo ""
  echo "⚠ Warnings:"
  for w in "${WARNINGS[@]}"; do
    echo "  - $w"
  done
fi
