#!/usr/bin/env bash
# Thin wrapper — delegates to the canonical validator from superpowers-for-vk.
# Falls back to minimal local validation if the plugin validator is not found.
set -euo pipefail

PLUGIN_VALIDATOR=""
for candidate in \
  "$HOME/.claude/plugins/cache/derio-net/superpowers-for-vk/"*/scripts/validate-plans.sh \
  "$HOME/repos/superpowers-for-vk/scripts/validate-plans.sh"; do
  if [ -x "$candidate" ]; then
    PLUGIN_VALIDATOR="$candidate"
    break
  fi
done

if [ -n "$PLUGIN_VALIDATOR" ]; then
  exec "$PLUGIN_VALIDATOR" "$@"
fi

echo "WARNING: superpowers-for-vk validator not found — running minimal checks" >&2
ERRORS=()
for f in "$@"; do
  [ -f "$f" ] || continue
  base="$(basename "$f" .md)"
  header=$(head -20 "$f")
  if ! echo "$header" | grep -q '\*\*Status:\*\*'; then
    ERRORS+=("$base: missing **Status:**")
  fi
done
if [ ${#ERRORS[@]} -gt 0 ]; then
  echo "Plan validation failed:" >&2
  for e in "${ERRORS[@]}"; do echo "  - $e" >&2; done
  exit 1
fi
