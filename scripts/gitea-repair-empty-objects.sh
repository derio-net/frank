#!/usr/bin/env bash
# Repair zero-byte loose objects in a Gitea-hosted mirror by re-supplying them
# from a clone of the authoritative source (GitHub).
#
# WHY NOT "delete the empties and re-push": measured wrong (frank#849,
# derio-homelab/kid-laptops, 2026-10-13). The branch tip is itself one of the
# empty objects, so deleting leaves `refs/heads/main` pointing at a missing
# commit, and the pushing client never re-sends objects it believes the remote
# already has. The objects have to be put back explicitly.
#
# Usage:
#   gitea-repair-empty-objects.sh --repo <owner/name> --source <clone-dir> [--apply] [--allow-missing]
#
#   --repo           repository as Gitea names it, e.g. derio-homelab/kid-laptops
#   --source         a CURRENT clone of the authoritative remote (run `git fetch` first)
#   --apply          do it; without this the script only reports the plan
#   --allow-missing  also delete empties the source cannot supply (unreachable
#                    garbage, e.g. from a deleted branch); they are reported
#
# Env:
#   GITEA_EXEC        command prefix that runs a command inside the Gitea pod
#                     (default: kubectl -n gitea exec -i deploy/gitea -c gitea --).
#                     Set to the empty string to operate on a local directory.
#   GITEA_REPOS_DIR   where Gitea keeps bare repos (default /data/git/gitea-repositories)
#
# Exit: 0 ok / nothing to do · 1 repair did not verify · 2 plan unsafe (nothing changed) · 64 usage
set -euo pipefail

REPO="" SOURCE="" APPLY=0 ALLOW_MISSING=0
GITEA_EXEC="${GITEA_EXEC-kubectl -n gitea exec -i deploy/gitea -c gitea --}"
GITEA_REPOS_DIR="${GITEA_REPOS_DIR:-/data/git/gitea-repositories}"

usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 64; }

while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2 ;;
    --source) SOURCE="${2:-}"; shift 2 ;;
    --apply) APPLY=1; shift ;;
    --allow-missing) ALLOW_MISSING=1; shift ;;
    -h|--help) usage ;;
    *) echo "unknown argument: $1" >&2; usage ;;
  esac
done
[ -n "$REPO" ] && [ -n "$SOURCE" ] || usage

# shellcheck disable=SC2086  # GITEA_EXEC is deliberately word-split into a command prefix
gexec() { $GITEA_EXEC "$@"; }

BARE="$GITEA_REPOS_DIR/$REPO.git"
git -C "$SOURCE" rev-parse --git-dir >/dev/null 2>&1 || { echo "--source is not a git repository: $SOURCE" >&2; exit 64; }

empties="$(gexec find "$BARE/objects" -type f -size 0 -path '*/objects/??/*' \
  | sed -E 's#.*/([0-9a-f]{2})/([0-9a-f]{38})$#\1\2#' | grep -E '^[0-9a-f]{40}$' | sort || true)"

if [ -z "$empties" ]; then
  echo "No empty loose objects in $REPO — nothing to do."
  exit 0
fi

count="$(printf '%s\n' "$empties" | wc -l | tr -d ' ')"
echo "$REPO: $count empty loose object(s):"
# shellcheck disable=SC2086  # hex object ids only
printf '  %s\n' $empties

recoverable="" missing=""
for h in $empties; do
  if git -C "$SOURCE" cat-file -e "$h" 2>/dev/null; then
    recoverable="$recoverable$h"$'\n'
  else
    missing="$missing$h"$'\n'
  fi
done

if [ -n "$missing" ]; then
  echo "The source cannot supply:"
  # shellcheck disable=SC2086  # hex object ids only
  printf '  %s\n' $missing
  if [ "$ALLOW_MISSING" -ne 1 ]; then
    echo "Refusing: deleting an empty object nobody can re-supply turns a loud failure into a silent hole." >&2
    echo "Fetch the source again, or pass --allow-missing if these are unreachable garbage." >&2
    exit 2
  fi
fi

if [ "$APPLY" -ne 1 ]; then
  echo "Dry run — nothing changed. Re-run with --apply."
  exit 0
fi

# 1. remove every empty file (they are already unusable)
for h in $empties; do
  gexec rm -f "$BARE/objects/${h:0:2}/${h:2}"
done

# 2. put back exactly the objects the source can supply
if [ -n "$recoverable" ]; then
  printf '%s' "$recoverable" | git -C "$SOURCE" pack-objects --stdout -q \
    | gexec git --git-dir="$BARE" unpack-objects -q
fi

# 3. verify, don't assume
for h in $recoverable; do
  gexec git --git-dir="$BARE" cat-file -e "$h" || { echo "NOT RESTORED: $h" >&2; exit 1; }
done
fsck_out="$(gexec git --git-dir="$BARE" fsck --no-dangling 2>&1 || true)"
if [ -n "$fsck_out" ]; then
  echo "git fsck is not clean after repair:" >&2
  echo "$fsck_out" >&2
  exit 1
fi

echo "Repaired $REPO: restored $(printf '%s' "$recoverable" | grep -c . || true) object(s); git fsck clean."
[ -z "$missing" ] || echo "Deleted but NOT restorable (unreferenced): $(printf '%s' "$missing" | tr '\n' ' ')"
