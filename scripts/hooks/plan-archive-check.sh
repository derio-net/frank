#!/usr/bin/env bash
# PostToolUse hook: after editing a plan file, check if status changed to a
# done state and suggest archiving.
set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_response.filePath // empty')

# Only care about active plan files (not already archived)
case "$FILE_PATH" in
  *docs/superpowers/plans/*.md) ;;
  *) exit 0 ;;
esac

[ -f "$FILE_PATH" ] || exit 0

# Check current status
STATUS=$(head -20 "$FILE_PATH" | sed -n 's/.*\*\*Status:\*\* \(.*\)/\1/p' | head -1)

case "$STATUS" in
  Complete|Deployed|Closed)
    echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"The plan $(basename "$FILE_PATH") now has Status: $STATUS. Ask the user if they want to archive it (run: scripts/plan-status.sh --archive).\"}}"
    ;;
esac
