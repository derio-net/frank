#!/usr/bin/env bash
# PostToolUse hook: after writing a plan file, check if it includes the
# post-deploy checklist (blog, README, runbook, status steps).
# Only fires for new/modified plans in docs/superpowers/plans/.
set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_response.filePath // empty')

# Only care about active plan files
case "$FILE_PATH" in
  *docs/superpowers/plans/*.md) ;;
  *) exit 0 ;;
esac

[ -f "$FILE_PATH" ] || exit 0

# Skip if this is a fix/extension/investigation/audit/meta plan
BASE=$(basename "$FILE_PATH" .md)
DETAILS="${BASE#*--*--}"  # strip date--layer--
case "$DETAILS" in
  *fix*|*regression*|*investigation*|*audit*|*completion*) exit 0 ;;
esac
LAYER="${BASE#*--}"
LAYER="${LAYER%%--*}"
case "$LAYER" in
  repo) exit 0 ;;
esac

# Check for post-deploy checklist indicators
if ! grep -q 'blog.*post\|/blog-post\|Post-Deploy' "$FILE_PATH"; then
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"This standard layer plan is missing the Post-Deploy Checklist (blog post, README update, runbook sync). See .claude/rules/plan-post-deploy-checklist.md. Add a final task with these steps.\"}}"
fi
