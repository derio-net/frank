#!/usr/bin/env bash
# Wait until every machine in the cluster is fully recovered and STAYS that way.
#
# The stability requirement is not padding. Omni can report a config applied
# immediately BEFORE a scheduled reboot, so a single healthy sample is a lie you
# will act on. This requires every machine at stage 4 (Running), ready,
# config-up-to-date and APPLIED for STABLE_SAMPLES consecutive polls.
#
# Exit 0 = recovered and stable. Exit 1 = timed out (still not stable).
#
# Usage:
#   ./wait-recovery.sh
#   STABLE_SAMPLES=10 ATTEMPTS=360 ./wait-recovery.sh
set -euo pipefail

CLUSTER="${CLUSTER:-frank}"
ATTEMPTS="${ATTEMPTS:-180}"
INTERVAL="${INTERVAL:-10}"
STABLE_SAMPLES="${STABLE_SAMPLES:-6}"

BASE_REPO="${BASE_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
for f in .env .env_devops; do
  if [ ! -f "$BASE_REPO/$f" ]; then
    echo "ERROR: $BASE_REPO/$f not found. Set BASE_REPO to the operator checkout." >&2
    exit 1
  fi
done
cd "$BASE_REPO"
set -a; . ./.env; . ./.env_devops; set +a

# Derived, not hardcoded: a machine added or replaced since the last incident
# must be counted, or "all recovered" is measured against the wrong denominator.
expected="$(omnictl get clustermachines -l "omni.sidero.dev/cluster=$CLUSTER" -o json \
  | jq -s 'length')"
if [ "${expected:-0}" -lt 1 ]; then
  echo "ERROR: could not determine machine count for cluster=$CLUSTER" >&2
  exit 1
fi
echo "# cluster=$CLUSTER expecting $expected machine(s), need $STABLE_SAMPLES stable samples" >&2

stable=0
for attempt in $(seq 1 "$ATTEMPTS"); do
    statuses="$(omnictl get clustermachinestatuses -l "omni.sidero.dev/cluster=$CLUSTER" -o json 2>/dev/null || true)"
    if [ -z "$statuses" ]; then
        printf 'attempt=%s omni unreachable\n' "$attempt"
        stable=0
        sleep "$INTERVAL"
        continue
    fi
    recovered="$(jq -s '[.[] | select(.spec.stage == 4 and .spec.ready == true and .spec.configuptodate == true and .spec.configapplystatus == 2)] | length' <<<"$statuses")"
    pending="$(jq -sr '[.[] | select(.spec.stage != 4 or .spec.ready != true or .spec.configuptodate != true or .spec.configapplystatus != 2) | .metadata.labels["omni.sidero.dev/hostname"]] | join(",")' <<<"$statuses")"
    printf 'attempt=%s recovered=%s/%s pending=%s\n' "$attempt" "$recovered" "$expected" "${pending:-none}"
    if [ "$recovered" -eq "$expected" ]; then
        stable=$((stable + 1))
        printf 'stable_samples=%s/%s\n' "$stable" "$STABLE_SAMPLES"
        if [ "$stable" -ge "$STABLE_SAMPLES" ]; then
            echo "# RECOVERED: $expected/$expected stable for $STABLE_SAMPLES samples." >&2
            exit 0
        fi
    else
        stable=0
    fi
    sleep "$INTERVAL"
done
echo "# TIMEOUT after $ATTEMPTS attempts — NOT stable. Do not remove the patches yet." >&2
exit 1
