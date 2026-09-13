#!/usr/bin/env bash
# Force Omni to resend each machine's full config after a rollback race.
#
# WHEN: a bad cluster-wide ConfigPatch rebooted machines, you reverted it, and
# some machines are still running the bad config. Omni v1.5 records a config
# hash; because the revert restored the ORIGINAL desired config, that hash
# matches what Omni already believes it sent, so it never resends the rollback
# to nodes that persisted the bad version. See the "Rollback race on Omni v1.5"
# section of docs/runbooks/frank-gotchas/omni.md.
#
# HOW: write a harmless per-machine marker under /var. The resulting REAL hash
# change is the whole point — it makes Omni push each node's full corrected
# config. The file itself does nothing.
#
# The marker content carries a UTC timestamp so every run differs from the last.
# That is load-bearing. The original incident scripts used a fixed string and
# had to be hand-bumped (…-v1, -v2, -v3) because re-running with identical
# content produces NO hash change and therefore no resend — the failure looks
# exactly like the problem you are trying to fix.
#
# Machines are derived live from Omni, not hardcoded, so a replaced node cannot
# be silently skipped.
#
# Usage:
#   ./force-recovery.sh --dry-run     # print the patches, touch nothing
#   ./force-recovery.sh --apply       # apply them
#   BASE_REPO=/path/to/frank ./force-recovery.sh --apply
set -euo pipefail

CLUSTER="${CLUSTER:-frank}"
MARKER_PATH="/var/omni-recovery-marker"

usage() { sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

MODE=""
case "${1:-}" in
  --dry-run) MODE=dry ;;
  --apply)   MODE=apply ;;
  -h|--help) usage 0 ;;
  *) echo "ERROR: pass --dry-run or --apply" >&2; usage 1 ;;
esac

# `.env` sets OMNICONFIG/TALOSCONFIG to paths RELATIVE to the repo root, so the
# working directory is load-bearing: sourced from anywhere else omnictl silently
# falls back to a different (or absent) config. Default to this script's own
# checkout; a worktree has no gitignored .talos/, hence the explicit check.
BASE_REPO="${BASE_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
for f in .env .env_devops; do
  if [ ! -f "$BASE_REPO/$f" ]; then
    echo "ERROR: $BASE_REPO/$f not found." >&2
    echo "       Set BASE_REPO to the operator checkout holding .env and .env_devops" >&2
    echo "       (an fr worktree does not carry the gitignored .talos/ directory)." >&2
    exit 1
  fi
done
cd "$BASE_REPO"
set -a; . ./.env; . ./.env_devops; set +a

MARKER_CONTENT="legacy-config-recovery-$(date -u +%Y%m%dT%H%M%SZ)"

machines="$(omnictl get clustermachinestatuses -l "omni.sidero.dev/cluster=$CLUSTER" -o json \
  | jq -sr '.[] | "\(.metadata.id) \(.metadata.labels["omni.sidero.dev/hostname"] // .metadata.id)"')"

if [ -z "$machines" ]; then
  echo "ERROR: no cluster machines found for cluster=$CLUSTER — refusing to continue." >&2
  exit 1
fi

count="$(printf '%s\n' "$machines" | wc -l | tr -d ' ')"
echo "# cluster=$CLUSTER machines=$count marker=$MARKER_CONTENT" >&2

render() {
  local first=1
  while read -r id host; do
    [ -z "$id" ] && continue
    [ $first -eq 1 ] || echo "---"
    first=0
    cat <<YAML
metadata:
    namespace: default
    type: ConfigPatches.omni.sidero.dev
    id: 999-recovery-$host
    labels:
        omni.sidero.dev/cluster: $CLUSTER
        omni.sidero.dev/cluster-machine: $id
spec:
    data: |
        machine:
            files:
                - path: $MARKER_PATH
                  op: create
                  permissions: 0o600
                  content: $MARKER_CONTENT
YAML
  done <<< "$machines"
}

if [ "$MODE" = dry ]; then
  render
  echo "# DRY RUN — nothing applied. Re-run with --apply." >&2
  exit 0
fi

render | omnictl apply -f -
echo "# applied $count recovery patch(es)." >&2
echo "# next: ./wait-recovery.sh   then: ./remove-recovery.sh" >&2
