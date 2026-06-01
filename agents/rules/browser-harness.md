# Browser Automation — browser-harness (machine-global)

Browser automation here uses **browser-harness**, a machine-global skill — not
anything checked into this repo. Every shell on this Mac (interactive,
non-interactive, login, and Claude Code subagents alike) has it on `$PATH`, so an
agent in this repo or any sibling repo gets the identical setup with no extra
configuration.

- **Skill / source of truth:** `~/Developer/browser-harness/SKILL.md`
  (also `@`-imported by the global `~/.claude/CLAUDE.md`).
- **How it works:** `browser-harness` is a `$PATH` wrapper that resolves the live
  CDP WebSocket of the running **Brave-Clawdia** profile on port 9222 and delegates
  to the uv-installed CLI. Invoke as a heredoc; first navigation is `new_tab(url)`,
  not `goto_url`. Local = CDP to Brave only; cloud browsers need
  `BROWSER_USE_API_KEY` (not set on this machine).

## Caveat: `uv` can clobber the wrapper — recognize and repair it

`browser-harness` is installed via `uv` (entrypoint at `~/.local/bin/browser-harness`).
The dotfiles wrapper overrides that entrypoint with a symlink so the CLI attaches to
Brave instead of auto-launching Chrome. **`uv tool upgrade browser-harness` recreates
uv's own entrypoint and silently clobbers the override.**

- **Symptom:** a bare `browser-harness` call launches **Chrome**, not Brave-Clawdia.
- **Detect:** `readlink ~/.local/bin/browser-harness` should resolve to
  `~/.dotfiles/zsh/bin/browser-harness`. If it doesn't, it's clobbered.
- **Repair:** run `browser-harness-doctor` — idempotent; re-points the wrapper
  symlinks and reports status. Manual equivalent:
  `ln -sf ~/.dotfiles/zsh/bin/browser-harness ~/.local/bin/browser-harness`.

If you run any `uv tool upgrade` touching browser-harness, run `browser-harness-doctor`
afterward.

---

*This rule is mirrored in `willikins` and `frank` for in-repo discoverability. The
canonical source of truth is `~/Developer/browser-harness/SKILL.md`; keep the two
mirrors in sync with it.*
