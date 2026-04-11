#!/usr/bin/env bash
# Show implementation status of all plans at a glance.
# Parses the --<layer>--<details> filename convention and reads **Status:**/**Spec:** headers.
#
# Usage:
#   plan-status.sh              # list all plans
#   plan-status.sh --archive    # move Complete/Deployed/Closed plans to archived-plans/
#   plan-status.sh --open       # show only in-progress plans with open tasks/steps
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLANS_DIR="$REPO_ROOT/docs/superpowers/plans"
SPECS_DIR="$REPO_ROOT/docs/superpowers/specs"
ARCHIVE_DIR="$REPO_ROOT/docs/superpowers/archived-plans"

DO_ARCHIVE=false
SHOW_OPEN=false
case "${1:-}" in
  --archive) DO_ARCHIVE=true; mkdir -p "$ARCHIVE_DIR" ;;
  --open)    SHOW_OPEN=true ;;
esac

# Collect plan files from both active and archived directories
declare -a ALL_FILES=()
declare -A IS_ARCHIVED=()

for f in "$PLANS_DIR"/*.md; do
  [ -e "$f" ] || continue
  ALL_FILES+=("$f")
  IS_ARCHIVED["$f"]="no"
done
if [ -d "$ARCHIVE_DIR" ]; then
  for f in "$ARCHIVE_DIR"/*.md; do
    [ -e "$f" ] || continue
    ALL_FILES+=("$f")
    IS_ARCHIVED["$f"]="yes"
  done
fi

# Sort by basename
mapfile -t SORTED < <(for f in "${ALL_FILES[@]}"; do echo "$(basename "$f")|$f"; done | sort | cut -d'|' -f2)

# Track warnings
WARNINGS=()

if ! $SHOW_OPEN; then
  printf "%-10s %-12s %-40s %-6s %-10s %s\n" "Layer" "Date" "Details" "Spec" "Archived" "Status"
  printf "%s\n" "────────── ──────────── ──────────────────────────────────────── ────── ────────── ──────"
fi

for f in "${SORTED[@]}"; do
  base="$(basename "$f" .md)"
  archived="${IS_ARCHIVED[$f]}"

  # Parse filename: YYYY-MM-DD--<layer>--<details>
  if [[ "$base" =~ ^([0-9]{4}-[0-9]{2}-[0-9]{2})--([^-]+)--(.+)$ ]]; then
    date="${BASH_REMATCH[1]}"
    layer="${BASH_REMATCH[2]}"
    details="${BASH_REMATCH[3]}"
  else
    date="${base:0:10}"
    layer="???"
    details="${base:11}"
    WARNINGS+=("Malformed filename: $base")
  fi

  # Extract Spec reference from first 20 lines
  spec_ref=$(head -20 "$f" | sed -n 's/.*\*\*Spec:\*\* `\([^`]*\)`.*/\1/p' | head -1)
  if [ -z "$spec_ref" ]; then
    spec="no"
    WARNINGS+=("Missing **Spec:** line: $base")
  elif [ "$spec_ref" = "none" ]; then
    spec="none"
  elif [[ "$spec_ref" == willikins/* ]]; then
    spec="ext"
  elif [ -f "$REPO_ROOT/$spec_ref" ]; then
    spec="yes"
  else
    spec="MISS"
    WARNINGS+=("Broken spec ref: $base -> $spec_ref")
  fi

  # Extract Status from first 20 lines (raw for filtering, display version for output)
  status_raw=$(head -20 "$f" | sed -n 's/.*\*\*Status:\*\* \(.*\)/\1/p' | head -1)
  status="$status_raw"
  if [[ "$status" == *" ("* ]]; then
    status="${status%% (*} (...)"
  fi
  [ -z "$status" ] && status="(missing)"

  # --open: skip archived and done plans
  if $SHOW_OPEN; then
    [[ "$archived" == "yes" ]] && continue
    case "$status_raw" in
      Complete|Deployed|Closed) continue ;;
    esac
  fi

  # Archive if requested and status qualifies
  if $DO_ARCHIVE && [[ "$archived" == "no" ]]; then
    case "$status" in
      Complete|Deployed|Closed)
        mv "$f" "$ARCHIVE_DIR/$(basename "$f")"
        archived="yes"
        ;;
    esac
  fi

  if $SHOW_OPEN; then
    # Print plan header
    rel_path="${f#"$REPO_ROOT/"}"
    printf "\n\033[1m%s\033[0m  %s  [%s]\n" "$layer" "$details" "$status"
    printf "\033[2m%s\033[0m\n" "$rel_path"

    # Collect tasks with their open steps
    declare -a task_names=()
    declare -a task_steps=()  # pipe-separated step lists per task
    current_phase=""
    current_task=""
    current_idx=-1

    while IFS= read -r line; do
      # Phase header: ## Phase N: Name [type]
      if [[ "$line" =~ ^##\ Phase\ [0-9]+:\ (.+)\ \[(manual|agentic)\]$ ]]; then
        current_phase="${BASH_REMATCH[1]}"
      fi

      # Task header: ### Task N: Name
      if [[ "$line" =~ ^###\ Task\ [0-9]+:\ (.+)$ ]]; then
        current_task="${BASH_REMATCH[1]}"
        if [ -n "$current_phase" ]; then
          current_task="$current_phase / $current_task"
        fi
        current_idx=$(( ${#task_names[@]} ))
        task_names+=("$current_task")
        task_steps+=("")
      fi

      # Open checkbox: - [ ] **...**
      if [[ "$line" =~ ^-\ \[\ \]\ \*\*(.+)\*\*$ ]]; then
        step_name="${BASH_REMATCH[1]}"
        step_name="${step_name#Step [0-9]: }"
        step_name="${step_name#Step [0-9][0-9]: }"
        if [ "$current_idx" -ge 0 ]; then
          if [ -n "${task_steps[$current_idx]}" ]; then
            task_steps[$current_idx]="${task_steps[$current_idx]}|$step_name"
          else
            task_steps[$current_idx]="$step_name"
          fi
        fi
      fi
    done < "$f"

    # Render tree: only tasks with open steps
    last_task_idx=-1
    for i in "${!task_names[@]}"; do
      [ -n "${task_steps[$i]}" ] && last_task_idx=$i
    done

    for i in "${!task_names[@]}"; do
      [ -z "${task_steps[$i]}" ] && continue
      if [ "$i" -eq "$last_task_idx" ]; then
        echo "  └── ${task_names[$i]}"
        prefix="      "
      else
        echo "  ├── ${task_names[$i]}"
        prefix="  │   "
      fi
      # Split steps and render
      IFS='|' read -ra steps <<< "${task_steps[$i]}"
      for j in "${!steps[@]}"; do
        if [ "$j" -eq $(( ${#steps[@]} - 1 )) ]; then
          echo "${prefix}└─ ${steps[$j]}"
        else
          echo "${prefix}├─ ${steps[$j]}"
        fi
      done
    done

    unset task_names task_steps
  else
    printf "%-10s %-12s %-40s %-6s %-10s %s\n" "$layer" "$date" "$details" "$spec" "$archived" "$status"
  fi
done

# Print warnings if any
if [ ${#WARNINGS[@]} -gt 0 ]; then
  echo ""
  echo "⚠ Warnings:"
  for w in "${WARNINGS[@]}"; do
    echo "  - $w"
  done
fi
