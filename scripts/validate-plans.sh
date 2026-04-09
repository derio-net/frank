#!/usr/bin/env bash
# Validate plan file headers for required fields and naming conventions.
# Exit 0 if all valid, exit 1 with details if any issues found.
# If given file arguments, validates only those files; otherwise validates all plans.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ERRORS=()

validate_file() {
  local f="$1"
  local base
  base="$(basename "$f" .md)"

  # Check filename convention: YYYY-MM-DD--<layer>--<details>
  if ! [[ "$base" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}--[a-z]+--[a-z0-9].*$ ]]; then
    ERRORS+=("$base: malformed filename (expected YYYY-MM-DD--<layer>--<details>)")
  fi

  # Check for **Spec:** line (not **Design doc:**)
  local header
  header=$(head -20 "$f")
  if echo "$header" | grep -q '\*\*Design doc:\*\*'; then
    ERRORS+=("$base: uses **Design doc:** — rename to **Spec:**")
  elif ! echo "$header" | grep -q '\*\*Spec:\*\*'; then
    ERRORS+=("$base: missing **Spec:** line in header")
  else
    # Validate spec reference
    local spec_ref
    spec_ref=$(echo "$header" | sed -n 's/.*\*\*Spec:\*\* `\([^`]*\)`.*/\1/p' | head -1)
    if [ -z "$spec_ref" ]; then
      ERRORS+=("$base: **Spec:** line has no backtick-enclosed path")
    elif [ "$spec_ref" != "none" ] && [[ "$spec_ref" != willikins/* ]]; then
      if [ ! -f "$REPO_ROOT/$spec_ref" ]; then
        ERRORS+=("$base: spec ref not found: $spec_ref")
      fi
    fi
  fi

  # Check for **Status:** line
  if ! echo "$header" | grep -q '\*\*Status:\*\*'; then
    ERRORS+=("$base: missing **Status:** line in header")
  fi

  # Check task headers use ### (h3), not ## (h2)
  if grep -q '^## Task [0-9]' "$f"; then
    ERRORS+=("$base: uses '## Task' — should be '### Task'")
  fi
}

# Determine which files to validate
if [ $# -gt 0 ]; then
  for f in "$@"; do
    [ -f "$f" ] && validate_file "$f"
  done
else
  for f in "$REPO_ROOT/docs/superpowers/plans"/*.md "$REPO_ROOT/docs/superpowers/archived-plans"/*.md; do
    [ -e "$f" ] && validate_file "$f"
  done
fi

if [ ${#ERRORS[@]} -gt 0 ]; then
  echo "Plan validation failed:" >&2
  for e in "${ERRORS[@]}"; do
    echo "  - $e" >&2
  done
  exit 1
fi
