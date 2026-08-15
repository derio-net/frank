# Browser Automation — browser-harness (machine-global)

Browser automation in this repo uses **browser-harness**, a machine-global skill on `$PATH` —
not anything checked into this repo. Any agent runtime, on any clone, gets the identical setup
with no per-repo configuration.

- **Source of truth:** `~/Developer/browser-harness/SKILL.md`. Read it before driving the browser.
- **Invocation:** call `browser-harness` as a heredoc; the first navigation is `new_tab(url)`,
  not `goto_url` (which clobbers the operator's active tab).
- **Scope:** browser-harness drives a *real, logged-in* browser. Local, unauthenticated
  rendering is exempt — see the next section.

## Scope — logged-in sessions, not local rendering

Use browser-harness whenever the target needs the operator's identity or cookies:

- Auth-walled cluster UIs: Grafana, ArgoCD, Longhorn, Authentik.
- Blog screenshots that must show a logged-in view.
- Anything behind SSO.

**Local, unauthenticated rendering is exempt.** To check a locally-served or public page — a
`hugo server` preview, a link/render/quality gate, a Lighthouse run — launch a disposable
headless browser directly (Playwright / Chrome for Testing). Do **not** route that through
browser-harness. Three reasons:

- The task needs no login, so the operator's logged-in profile buys nothing.
- browser-harness needs CDP on port 9222, and CDP is **process-wide**: it exposes every profile
  in that browser, including the operator's personal one, for as long as it runs.
- Tabs opened in a real profile come back. Session-restore resurrects them on the next launch.

**Rule of thumb:** needs a login → browser-harness. Renders localhost or a public URL →
headless is correct. If it needs both, prefer browser-harness and close the tabs you opened.

**Tear down either way.** A headless browser left running on the workstation is
indistinguishable from a leak. Close what you open: `close_tab()` for browser-harness tabs, and
shut down any headless instance when the check finishes.

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
