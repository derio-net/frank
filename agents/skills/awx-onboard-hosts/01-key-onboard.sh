#!/usr/bin/env bash
# Step 1: generate a dedicated AWX SSH key and install it on each host from the
# env file, verifying login THE WAY AWX WILL (new key only, no ssh-config/agent).
# Run on your Mac. Idempotent.  Usage: bash 01-key-onboard.sh [env-file]
set -euo pipefail

REPO="$(git rev-parse --show-toplevel)"
ENV_FILE="${1:-$REPO/scripts/tmp/awx-hosts.env}"
# shellcheck disable=SC1090
source "$ENV_FILE"

trim() { sed 's/^[[:space:]]*//; s/[[:space:]]*$//'; }

if [ -f "$AWX_KEY_PATH" ]; then
  echo "==> key exists, reusing: $AWX_KEY_PATH"
else
  echo "==> generating $AWX_KEY_TYPE key at $AWX_KEY_PATH (no passphrase)…"
  ssh-keygen -t "$AWX_KEY_TYPE" -f "$AWX_KEY_PATH" -N "" -C "$AWX_KEY_COMMENT"
fi

# Parse hosts into an array FIRST so nothing reads the loop's stdin.
hosts=()
while IFS= read -r line; do
  line="${line%%#*}"
  [ -z "$(printf '%s' "$line" | tr -d '[:space:]')" ] && continue
  hosts+=("$line")
done <<< "$AWX_HOSTS"

fail=0
for line in "${hosts[@]}"; do
  IFS='|' read -r alias host user becomev <<< "$line"
  alias="$(printf '%s' "$alias" | trim)"; host="$(printf '%s' "$host" | trim)"; user="$(printf '%s' "$user" | trim)"
  [ -z "$alias" ] && continue
  if [ -z "$host" ] || [ -z "$user" ]; then
    g="$(ssh -G "$alias" 2>/dev/null)"
    [ -z "$host" ] && host="$(printf '%s' "$g" | awk '/^hostname /{print $2;exit}')"
    [ -z "$user" ] && user="$(printf '%s' "$g" | awk '/^user /{print $2;exit}')"
  fi
  echo; echo "==> [$alias] ${user}@${host} : force-installing AWX public key…"
  if ! ssh-copy-id -f -i "${AWX_KEY_PATH}.pub" "$alias" < /dev/null; then
    echo "    !! ssh-copy-id FAILED for $alias" >&2; fail=1; continue
  fi
  echo "==> [$alias] verifying AWX-style (new key ONLY, ignoring ~/.ssh/config)…"
  if ssh -n -F /dev/null -i "$AWX_KEY_PATH" \
        -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
        "${user}@${host}" 'echo "    OK: $(whoami)@$(hostname) — reachable with AWX key alone"'; then :;
  else echo "    !! AWX-style verify FAILED for ${user}@${host}" >&2; fail=1; fi
done

echo
[ "$fail" = "0" ] && echo "All hosts onboarded + verified ✅" || { echo "One or more hosts FAILED ⚠️"; exit 1; }
