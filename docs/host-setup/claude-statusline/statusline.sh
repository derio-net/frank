#!/bin/bash
# Claude Code status line — reads session JSON from stdin
data=$(cat)

# ANSI color palette
DIM='\033[2m'
BOLD='\033[1m'
CYAN='\033[36m'
BLUE='\033[34m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
MAGENTA='\033[35m'
RESET='\033[0m'
SEP="${DIM} | ${RESET}"

# --- Model + context window size ---
model_display=$(echo "$data" | jq -r '.model.display_name // empty' | sed 's/^Claude //')
ctx_size=$(echo "$data" | jq -r '.context_window.context_window_size // empty')
if [ -n "$ctx_size" ] && [ "$ctx_size" -gt 0 ] 2>/dev/null; then
  if [ "$ctx_size" -ge 1000000 ]; then
    size_label="$(( ctx_size / 1000000 ))M context"
  else
    size_label="$(( ctx_size / 1000 ))k context"
  fi
  model_str="${BOLD}${CYAN}${model_display}${RESET} ${DIM}(${size_label})${RESET}"
else
  model_str="${BOLD}${CYAN}${model_display}${RESET}"
fi

# --- Context used percentage + window size label ---
ctx_used=$(echo "$data" | jq -r '.context_window.used_percentage // empty')
if [ -n "$ctx_used" ] && [ -n "$ctx_size" ]; then
  ctx_int=${ctx_used%.*}
  if [ "$ctx_size" -ge 1000000 ]; then
    window_label="$(( ctx_size / 1000000 ))M"
  else
    window_label="$(( ctx_size / 1000 ))k"
  fi
  # Color code: green < 50%, yellow 50-75%, red > 75%
  if [ "$ctx_int" -ge 75 ]; then
    ctx_color="$RED"
  elif [ "$ctx_int" -ge 50 ]; then
    ctx_color="$YELLOW"
  else
    ctx_color="$GREEN"
  fi
  ctx_str="${DIM}ctx:${RESET}${ctx_color}${ctx_int}%${RESET}${DIM} of ${window_label}${RESET}"
elif [ -n "$ctx_used" ]; then
  ctx_int=${ctx_used%.*}
  ctx_str="${DIM}ctx:${RESET}${GREEN}${ctx_int}%${RESET}"
else
  ctx_str="${DIM}ctx:?${RESET}"
fi

# --- Rate limits (color-coded) ---
_rate_color() {
  local pct=$1
  if [ "$pct" -ge 75 ]; then
    echo "$RED"
  elif [ "$pct" -ge 50 ]; then
    echo "$YELLOW"
  else
    echo "$GREEN"
  fi
}

five_pct=$(echo "$data" | jq -r '.rate_limits.five_hour.used_percentage // empty')
seven_pct=$(echo "$data" | jq -r '.rate_limits.seven_day.used_percentage // empty')
rate_str=""
if [ -n "$five_pct" ]; then
  five_int=${five_pct%.*}
  fc=$(_rate_color "$five_int")
  rate_str="${DIM}5h:${RESET}${fc}${five_int}%${RESET}"
fi
if [ -n "$seven_pct" ]; then
  seven_int=${seven_pct%.*}
  sc=$(_rate_color "$seven_int")
  [ -n "$rate_str" ] && rate_str="${rate_str} "
  rate_str="${rate_str}${DIM}7d:${RESET}${sc}${seven_int}%${RESET}"
fi

# --- Git branch ---
branch=$(git -C "$(echo "$data" | jq -r '.cwd // "."')" --no-optional-locks branch --show-current 2>/dev/null)
branch_str=""
if [ -n "$branch" ]; then
  branch_str="${MAGENTA}${branch}${RESET}"
fi

# --- CWD with ~ substitution ---
cwd=$(echo "$data" | jq -r '.cwd // empty')
cwd_short="${cwd/#$HOME/~}"
cwd_str="${BLUE}${cwd_short}${RESET}"

# --- Git worktrees (third line, only if >1 worktree exists) ---
repo_root=$(git -C "$(echo "$data" | jq -r '.cwd // "."')" --no-optional-locks rev-parse --show-toplevel 2>/dev/null)
worktree_line=""
if [ -n "$repo_root" ]; then
  # Parse porcelain worktree list: each entry is a "worktree <path>" line
  # followed by attribute lines (HEAD/branch/detached/bare) until a blank line.
  wt_entries=()
  cur_path=""; cur_branch=""; cur_head=""
  _flush() {
    [ -z "$cur_path" ] && return
    local b="$cur_branch"
    # Detached / no branch → short HEAD sha
    [ -z "$b" ] && b="${cur_head:0:7}"
    wt_entries+=("${cur_path}|${b}")
    cur_path=""; cur_branch=""; cur_head=""
  }
  while IFS= read -r line; do
    case "$line" in
      "worktree "*)            _flush; cur_path="${line#worktree }" ;;
      "HEAD "*)                cur_head="${line#HEAD }" ;;
      "branch refs/heads/"*)   cur_branch="${line#branch refs/heads/}" ;;
      bare)                    cur_branch="bare" ;;
    esac
  done < <(git -C "$repo_root" --no-optional-locks worktree list --porcelain 2>/dev/null)
  _flush

  if [ "${#wt_entries[@]}" -gt 1 ]; then
    # The current worktree is already shown on line 2 (branch | folder),
    # so list only the OTHERS here. Label count stays the total (WIP gauge).
    total=${#wt_entries[@]}
    others=()
    for entry in "${wt_entries[@]}"; do
      [ "${entry%%|*}" = "$repo_root" ] && continue
      others+=("$entry")
    done

    # Width-bounded list with "+N more" overflow. Budget is plain-text chars
    # of the list portion (label excluded); tune via STATUSLINE_WT_WIDTH.
    budget=${STATUSLINE_WT_WIDTH:-110}
    worktree_line="${DIM}worktrees (${total}):${RESET} "
    plain_len=0
    shown=0
    n=${#others[@]}
    for ((i=0; i<n; i++)); do
      entry="${others[$i]}"
      wt_b="${entry##*|}"
      wt_base="${entry%%|*}"; wt_base="${wt_base##*/}"   # leaf dir only
      token="${wt_b}:${wt_base}"
      sep_len=0; [ "$shown" -gt 0 ] && sep_len=2
      # Stop before overflow, but always show at least one entry
      if [ "$shown" -gt 0 ] && [ $(( plain_len + sep_len + ${#token} )) -gt "$budget" ]; then
        worktree_line="${worktree_line}${DIM} +$(( n - shown )) more${RESET}"
        break
      fi
      [ "$shown" -gt 0 ] && worktree_line="${worktree_line}${DIM},${RESET} "
      worktree_line="${worktree_line}${DIM}${token}${RESET}"
      plain_len=$(( plain_len + sep_len + ${#token} ))
      shown=$(( shown + 1 ))
    done
  fi
fi

# --- Line 1: model + context + rate limits ---
out="$model_str"
out="${out}${SEP}${ctx_str}"
[ -n "$rate_str" ]   && out="${out}${SEP}${rate_str}"

echo -e "$out"

# --- Line 2: branch + folder ---
line2=""
[ -n "$branch_str" ] && line2="$branch_str"
if [ -n "$cwd_short" ]; then
  [ -n "$line2" ] && line2="${line2}${SEP}"
  line2="${line2}${cwd_str}"
fi
[ -n "$line2" ] && echo -e "$line2"

# --- Line 3: worktrees (only when multiple exist) ---
if [ -n "$worktree_line" ]; then
  echo -e "$worktree_line"
fi
