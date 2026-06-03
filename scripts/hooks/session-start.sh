#!/usr/bin/env bash
# SessionStart hook — inject the local Brave-Clawdia browser rule ONLY on this Mac.
#
# This repo is cloned on the secure-agent-pod too, where browser-harness uses the remote cloud
# browser (not local Brave/CDP). The Mac-specific rule therefore lives OUTSIDE agents/rules/
# (which .claude/rules symlinks to, and which auto-loads everywhere) and is injected here only
# when running on this Mac with the Clawdia setup present. On Linux/pod clones, uname != Darwin
# → skipped, so the rule never pollutes pod context.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
RULE="$REPO_DIR/agents/browser-harness-mac.md"

if [[ "$(uname)" == "Darwin" ]] && command -v brave-clawdia >/dev/null 2>&1 && [[ -f "$RULE" ]]; then
  esc=$(python3 -c 'import sys,json; print(json.dumps(open(sys.argv[1]).read()))' "$RULE")
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":${esc}}}"
fi

exit 0
