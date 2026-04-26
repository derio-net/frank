# Append this block to ~/.zshrc (or a file under ~/.zsh_config.d/ if you use
# zsh4humans's modular config layout). It re-colors the originating tmux pane
# whenever its cwd changes via `cd`.
#
# $TMUX_PANE is set by tmux for any shell running inside a pane; we pass it
# explicitly so the script colors the *originating* pane, not whatever pane
# happens to be active when the async tmux command actually runs.

function _tmux_color_by_cwd() {
  [ -n "$TMUX" ] && ~/.config/tmux/color-by-cwd.sh "$PWD" "$TMUX_PANE"
}
autoload -Uz add-zsh-hook
add-zsh-hook chpwd _tmux_color_by_cwd
_tmux_color_by_cwd
