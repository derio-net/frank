# Browser Automation — local Brave-Clawdia (THIS MAC ONLY)

> **Scope guard — read this first.** This applies **only on the local macOS workstation**, where
> browser-harness drives the **Brave-Clawdia** profile over local CDP on port 9222 (e.g. capturing
> screenshots for the blog). It does **not** apply on the secure-agent-pod or any other clone of
> this repo: there, browser-harness uses the **remote Browser Use cloud browser**
> (`BROWSER_USE_API_KEY`). This file is deliberately **not** in `agents/rules/` (the always-loaded
> shared rule registry); frank's SessionStart adapter injects it into context only when running on
> this Mac (`uname = Darwin` and `brave-clawdia` present). The host-neutral browser-harness rule in
> `agents/rules/browser-harness.md` loads everywhere and points here for the Mac specifics.

Browser automation uses **browser-harness**, a machine-global skill on `$PATH` (not checked into
this repo). Source of truth: `~/Developer/browser-harness/SKILL.md`. Invoke as a heredoc; first
navigation is `new_tab(url)`, not `goto_url`.

## Session shape (use the pair)

```
brave-clawdia          # begin: ensure Brave (Clawdia profile) up with CDP; blocks until ready
... drive it via browser-harness; close_tab() each tab you open ...
brave-clawdia-stop     # end: quit Brave, tearing down CDP
```

- **`brave-clawdia` self-heals.** CDP already serving → no-op. Brave running *without* the debug
  port → quits and relaunches with it (a normally-launched Brave can't be retrofitted; a second
  `open` only spawns an empty window). Not running → launches.
- **CDP is process-wide.** A debug-enabled Brave exposes **every** profile opened into it —
  including the personal **derio** profile — on 9222. Close the tabs you open (`close_tab()`), then
  end with **`brave-clawdia-stop`** so your next launch (derio) is clean and unexposed.
- Profiles: **Clawdia → Default** (automation), **derio → Profile 1** (personal; keep CDP-free).

The `brave-clawdia` / `brave-clawdia-stop` scripts live in the operator's dotfiles
(`~/.dotfiles/zsh/bin/`, symlinked onto `$PATH`); the full machine-global convention is documented
alongside the operator's global agent rules.

## Caveat: `uv` can clobber the wrapper

`browser-harness` is installed via `uv` (`~/.local/bin/browser-harness`); a dotfiles symlink
overrides the entrypoint so it attaches to Brave instead of launching Chrome. **`uv tool upgrade
browser-harness` recreates uv's entrypoint and silently clobbers the override.**

- **Symptom:** a bare `browser-harness` launches Chrome, not Brave-Clawdia.
- **Detect:** `readlink ~/.local/bin/browser-harness` should resolve to `~/.dotfiles/zsh/bin/browser-harness`.
- **Repair:** `browser-harness-doctor` (idempotent), or `ln -sf ~/.dotfiles/zsh/bin/browser-harness ~/.local/bin/browser-harness`.
