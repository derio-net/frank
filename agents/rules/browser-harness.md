# Browser Automation — browser-harness (machine-global)

Browser automation in this repo uses **browser-harness**, a machine-global skill on `$PATH` —
not anything checked into this repo. Any agent runtime, on any clone, gets the identical setup
with no per-repo configuration.

- **Source of truth:** `~/Developer/browser-harness/SKILL.md`. Read it before driving the browser.
- **Invocation:** call `browser-harness` as a heredoc; the first navigation is `new_tab(url)`,
  not `goto_url` (which clobbers the operator's active tab).

## Transport is injected per environment

browser-harness talks to a real browser, but *which* browser depends on where this clone runs.
That host-specific detail is **not** kept in this always-loaded rule — it is supplied per
environment so a clone never inherits another host's setup:

- **Local workstation (macOS):** local CDP to a logged-in **Brave** profile. The Mac-only
  conventions (the `brave-clawdia` session pair, CDP exposure caveats, the `uv`-clobber repair)
  are injected into context only on that host. See `agents/browser-harness-mac.md`.
- **secure-agent-pod / Linux clones:** the remote **Browser Use** cloud browser, via
  `BROWSER_USE_API_KEY`. No local CDP, no Brave.

If you are unsure which transport is active, check for `BROWSER_USE_API_KEY` (cloud) versus a
local CDP endpoint (workstation) before assuming.
