#!/usr/bin/env bash
# PostToolUse hook: after editing a plan file, validate its header.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$(cd "$(dirname "$0")/../.." && pwd)")"
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_response.filePath // empty')

# Only care about legacy flat/phased plan .md files.
# Skip v2 folder components (_prose.md, _meta.yaml, NN.yaml inside a plan dir).
case "$FILE_PATH" in
  *docs/superpowers/plans/*/_prose.md|\
  *docs/superpowers/plans/*/_meta.yaml|\
  *docs/superpowers/plans/*/*.yaml|\
  *docs/superpowers/archived-plans/*/_prose.md|\
  *docs/superpowers/archived-plans/*/_meta.yaml|\
  *docs/superpowers/archived-plans/*/*.yaml) exit 0 ;;
  *docs/superpowers/plans/*.md|*docs/superpowers/archived-plans/*.md) ;;
  *) exit 0 ;;
esac

ERRORS=$("$REPO_ROOT/scripts/validate-plans.sh" "$FILE_PATH" 2>&1 || true)
[ -z "$ERRORS" ] && exit 0

# Validation failed — inject context
echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"Plan header validation failed:\\n$ERRORS\\nFix the issues before committing.\"}}"
