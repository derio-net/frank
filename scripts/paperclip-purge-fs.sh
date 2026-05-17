#!/usr/bin/env bash
# paperclip-purge-fs.sh
#
# Removes leftover filesystem state for paperclip companies that have already
# been hard-deleted from the database. Defaults to dry-run; pass --apply to act.
#
# Where to run:
#   Inside the paperclip-shell sidecar (or the paperclip container itself —
#   both mount the same paperclip-data PVC at /paperclip).
#
#   kubectl -n paperclip-system exec -it deploy/paperclip -c paperclip-shell -- bash
#   # then run this script
#
# What it does:
#   - Removes per-company subtrees under
#       /paperclip/instances/default/{companies,projects,data/storage}/<id>
#     for each deleted company id.
#   - Refuses to touch the keeper id and refuses to touch /paperclip/agent-bin,
#     /paperclip/.cache, or anything outside the instance-scoped paths.
#   - Lists orphan workspaces (named by workspace_id, not company_id) for you
#     to handle separately — those need a DB lookup to attribute.

set -euo pipefail

INSTANCE_ROOT='/paperclip/instances/default'

# The ONE company we keep. Used as a safety guard — the script aborts if a
# deleted-id ever matches this. As of 2026-05-16 this is the freshly-imported
# Stoa company; Stoa-old was deleted on the same day.
KEEP_ID='cad28615-93e9-46f9-b7f6-016308be4a57'  # Stoa (prefix STO)

# UUIDs whose FS subtrees should be removed. Each one is already gone from
# the database.
DELETED_IDS=(
  '6433a437-8ac8-435c-b765-2cadd82f2f23'  # TMP
)

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
