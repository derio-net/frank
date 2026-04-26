# Append this block to /home/claude/.bashrc inside the pod. Bash has no
# `chpwd` hook, so we wrap `cd` (and `pushd`/`popd`) to call the recolor
# script after each directory change.
#
# $TMUX_PANE is exported by tmux for any shell running inside a pane.

if [ -n "$TMUX" ] && [ -x "$HOME/.config/tmux/color-by-cwd.sh" ]; then
  _tmux_recolor() { "$HOME/.config/tmux/color-by-cwd.sh" "$PWD" "$TMUX_PANE"; }

  cd()    { builtin cd    "$@" && _tmux_recolor; }
  pushd() { builtin pushd "$@" && _tmux_recolor; }
  popd()  { builtin popd  "$@" && _tmux_recolor; }

  # Also paint on shell startup so the pane's initial cwd is colored without
  # waiting for the first cd.
  _tmux_recolor
fi
