#!/usr/bin/env bash
# Color a single tmux pane's background based on its working directory.
#
# Trigger paths (each passes the right cwd + pane id for that event):
#   • zsh chpwd hook (zshrc-snippet.zsh) — pane's cwd changed via `cd`
#   • tmux after-split-window hook       — new pane just created
#   • tmux after-new-window/session hook — new window/session, new pane
#
# Args (both optional):
#   $1 — cwd. Falls back to active pane's #{pane_current_path}.
#   $2 — pane id (e.g. %12). Falls back to $TMUX_PANE if set, else the
#        active pane's #{pane_id}.
#
# Side effect: per-pane background via `select-pane -P` on the target pane.
# Does not touch status-style or window-style.
#
# To adapt this to your own project layout: edit the case statement below
# to match the paths you care about. The palette is example dark, muted
# tones tuned for a terminal background with white foreground; replace or
# extend as you like.

set -eu

# --- Palette (example) -----------------------------------------------------
DEFAULT_BLACK="#000000"
SLATE_GRAY="#2a2a2a"
FOREST_GREEN="#2a4a2a"
OLIVE_YELLOW="#4a4020"
DUSTY_ROSE="#4a2030"
DEEP_PURPLE="#3a2a4a"
MIDNIGHT_TEAL="#1a3a4a"
BURNT_AMBER="#4a3a1a"
DARK_PLUM="#3a1a3a"
SEA_MOSS="#1a4a3a"
COOL_BLUE="#1a2a4a"
IRON_BRONZE="#3a3520"
PLUM_ROSE="#3a2030"
# ---------------------------------------------------------------------------

# Path roots (example — edit for your own project layout).
PROJECTS="$HOME/projects"
REPOS="$HOME/repos"

# Resolve cwd: arg wins; otherwise pull from tmux's active pane.
cwd="${1:-}"
if [ -z "$cwd" ]; then
  cwd=$(tmux display-message -p -F '#{pane_current_path}' 2>/dev/null || echo "$HOME")
fi
cwd_slash="${cwd%/}/"

# Resolve target pane: arg wins; otherwise $TMUX_PANE; otherwise active pane.
pane="${2:-}"
if [ -z "$pane" ]; then
  pane="${TMUX_PANE:-}"
fi
if [ -z "$pane" ]; then
  pane=$(tmux display-message -p -F '#{pane_id}' 2>/dev/null) || exit 0
fi

# Decide bg color from cwd.
# First match wins, so put more-specific subtrees before the generic parent.
# Add or remove branches to taste.
case "$cwd_slash" in
  "$PROJECTS/cluster/"*)        bg="$FOREST_GREEN" ;;
  "$PROJECTS/agent-images/"*)   bg="$DEEP_PURPLE" ;;
  "$PROJECTS/content/"*)        bg="$MIDNIGHT_TEAL" ;;
  "$PROJECTS/learning/"*)       bg="$SEA_MOSS" ;;
  "$PROJECTS/"*)                bg="$SLATE_GRAY" ;;

  "$REPOS/cluster/"*)           bg="$FOREST_GREEN" ;;
  "$REPOS/agent-images/"*)      bg="$DEEP_PURPLE" ;;
  "$REPOS/"*)                   bg="$SLATE_GRAY" ;;

  *)                            bg="$DEFAULT_BLACK" ;;
esac

desired="bg=$bg,fg=default"

# tmux 3.6: per-pane style is set via `select-pane -P style`, not via
# `set-option -p pane-style` (that option doesn't exist; pane styling lives
# in pane runtime state, not the options tree). The -t target ensures we
# style the originating pane, not whatever happens to be active.
tmux select-pane -t "$pane" -P "$desired" >/dev/null 2>&1 || true

exit 0
