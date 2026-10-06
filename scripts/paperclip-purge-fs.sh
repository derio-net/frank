#!/usr/bin/env bash
# paperclip-purge-fs.sh
#
# Removes leftover filesystem state for paperclip companies that have already
# been hard-deleted from the database. Defaults to dry-run; pass --apply to act.
#
# Where to run:
#   Inside the paperclip container (it mounts the paperclip-data PVC at
#   /paperclip).
#
#   kubectl -n paperclip-system exec -it deploy/paperclip -c paperclip -- bash
#   # then run this script
#
# What it does:
#   - Removes per-company subtrees under
#       /paperclip/instances/default/{companies,projects,data/storage}/<id>
#     for each deleted company id.
#   - Refuses to touch the keeper id and refuses to touch
#     /paperclip/.cache, or anything outside the instance-scoped paths.
#   - Lists orphan workspaces (named by workspace_id, not company_id) for you
#     to handle separately — those need a DB lookup to attribute.

set -euo pipefail

INSTANCE_ROOT='/paperclip/instances/default'

# The ONE company to keep, as a safety guard: the script aborts if a deleted id
# ever matches it. Empty since the 2026-10 fresh start wiped the instance (the
# old Stoa/TMP ids no longer exist); fill both in before the next purge.
KEEP_ID=''

# UUIDs whose FS subtrees should be removed. Each one must already be gone from
# the database.
DELETED_IDS=()

# Subtrees whose immediate child directories are named by company UUID.
SUBTREES=(
  "$INSTANCE_ROOT/companies"
  "$INSTANCE_ROOT/projects"
  "$INSTANCE_ROOT/data/storage"
)

DRY_RUN=1
case "${1:-}" in
  --apply) DRY_RUN=0 ;;
  ''|--dry-run) DRY_RUN=1 ;;
  *) echo "usage: $0 [--apply|--dry-run]"; exit 2 ;;
esac

if [[ ${#DELETED_IDS[@]} -eq 0 ]]; then
  echo "DELETED_IDS is empty — nothing to purge. Edit the script first." >&2
  exit 0
fi
if [[ -z "$KEEP_ID" ]]; then
  echo "KEEP_ID is empty — set the company to keep before purging." >&2
  exit 1
fi

# Safety: keeper must never appear in the deletion list.
for id in "${DELETED_IDS[@]}"; do
  if [[ "$id" == "$KEEP_ID" ]]; then
    echo "ABORT: deleted-id $id == keeper $KEEP_ID" >&2
    exit 1
  fi
done

# Safety: every SUBTREES path must live under $INSTANCE_ROOT.
for tree in "${SUBTREES[@]}"; do
  case "$tree" in
    "$INSTANCE_ROOT"/*) : ;;
    *) echo "ABORT: subtree $tree is outside $INSTANCE_ROOT" >&2; exit 1 ;;
  esac
done

echo "instance root : $INSTANCE_ROOT"
echo "keeper id     : $KEEP_ID"
echo "deleted ids   : ${#DELETED_IDS[@]}"
echo "mode          : $([[ $DRY_RUN == 1 ]] && echo DRY-RUN || echo APPLY)"
echo

total=0
for tree in "${SUBTREES[@]}"; do
  if [[ ! -d "$tree" ]]; then
    echo "  - $tree  (no such dir, skipping)"
    continue
  fi
  for id in "${DELETED_IDS[@]}"; do
    target="$tree/$id"
    [[ -d "$target" ]] || continue
    hum=$(du -sh "$target" 2>/dev/null | cut -f1)
    if (( DRY_RUN )); then
      printf '  DRY   rm -rf %s  (%s)\n' "$target" "$hum"
    else
      rm -rf -- "$target"
      printf '  GONE  %s  (%s)\n' "$target" "$hum"
    fi
    total=$((total + 1))
  done
done

echo
if (( total == 0 )); then
  echo "Nothing to delete — all per-company subtrees already gone."
else
  echo "$total path(s) $([[ $DRY_RUN == 1 ]] && echo 'would be' || echo 'were') removed."
fi

# Surface orphan workspaces — those need separate handling because their dir
# names are workspace UUIDs, not company UUIDs. The safe way to identify them
# is `SELECT workspace_id FROM project_workspaces` against the live DB.
WS_DIR="$INSTANCE_ROOT/workspaces"
if [[ -d "$WS_DIR" ]]; then
  echo
  echo "Workspaces (named by workspace_id, not company_id):"
  echo "  $(find "$WS_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l) directories under $WS_DIR"
  echo "  Identify survivors by querying the live DB:"
  echo "    psql -c \"SELECT id FROM project_workspaces;\""
  echo "  Then rm -rf anything in $WS_DIR not in that list."
fi

if (( DRY_RUN )); then
  echo
  echo "Dry-run. Re-run with --apply to actually delete."
fi
