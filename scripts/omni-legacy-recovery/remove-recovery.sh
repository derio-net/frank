#!/usr/bin/env bash
# Delete the temporary 999-recovery-* ConfigPatches, returning the fleet to its
# clean desired state.
#
# Run this ONLY after wait-recovery.sh exits 0. Removing the patches is itself a
# config change that Omni serialises across machines; doing it while a machine is
# still unstable prolongs the outage you are recovering from.
#
# Patches are discovered, not hardcoded — a run that created a patch for a new
# machine must be able to clean it up.
set -euo pipefail

CLUSTER="${CLUSTER:-frank}"

BASE_REPO="${BASE_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
for f in .env .env_devops; do
  if [ ! -f "$BASE_REPO/$f" ]; then
    echo "ERROR: $BASE_REPO/$f not found. Set BASE_REPO to the operator checkout." >&2
    exit 1
  fi
done
cd "$BASE_REPO"
set -a; . ./.env; . ./.env_devops; set +a

ids="$(omnictl get configpatches -o json 2>/dev/null \
  | jq -sr '.[] | select(.metadata.id | startswith("999-recovery-")) | .metadata.id' || true)"

if [ -z "$ids" ]; then
  echo "# no 999-recovery-* patches present — nothing to remove."
  exit 0
fi

echo "# removing:"; printf '%s\n' "$ids" | sed 's/^/#   /'
printf '%s\n' "$ids" | while read -r id; do
  [ -z "$id" ] && continue
  omnictl delete configpatches "$id"
done

remaining="$(omnictl get configpatches -o json 2>/dev/null \
  | jq -sr '[.[] | select(.metadata.id | startswith("999-recovery-"))] | length' || echo "?")"
echo "# done. remaining 999-recovery-* patches: $remaining (expect 0)"
