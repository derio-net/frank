# Alert-Agent Persistent-Session Reliability + Telegram UX Hardening

**Layers:** obs (frank — `apps/alert-agent`, `apps/n8n-01`) + agent-images (the `agent-session` driver + `agent-shell-base` tmux config)
**Status:** Deployed (live 2026-06-18 on `multi-agent-shell:9ed7705`; free-text DMs verified end-to-end)
**Date:** 2026-06-17
**Repos:** `derio-net/frank`, `derio-net/agent-images` (multi-repo)
**Extends:** `2026-06-16--obs--alert-agent-telegram-ux-design.md` (the cold-start fix this supersedes-by-completing) + `2026-06-15--obs--agentic-alert-helper-design.md`

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|-------------|------|--------|
| agent-session-persistence (C+E+continuum, **gating**) | `derio-net/agent-images` | `2026-06-17-agent-session-persistence` | Deployed (#130/#131/#132/#133) |
| 2026-06-17--obs--alert-agent-session-reliability (A+D+env+bump) | `derio-net/frank` | `2026-06-17--obs--alert-agent-session-reliability` | Deployed (#571/#573/#575/#576/#578/#579) |

> Multi-repo, two plans. The **agent-images** plan (driver liveness + `--session-id` persistence +
> the `agent-shell-base` continuum conditional) gates the **frank** plan (bridge menu/threading + the
> `AGENT_TMUX_RESTORE` env on the two agent pods + the image-SHA bump). Sequence: agent-images merges
> → CI builds a new `multi-agent-shell` tag → frank bumps the SHA (auto-covered once frank#570 lands).

## Problem — proven live, today

The agentic alert-agent (frank#568 / agent-images#129, live) answers correctly on a **genuinely-fresh
session** (driving the endpoint: 7s trivial, 30s realistic "cluster status", `status=ok`). But a live
post-merge Test Plan proved the cold-start fix is **necessary but insufficient**, and surfaced three
more issues:

1. **tmux-continuum resurrects DEAD sessions** (the real blocker). `agent-shell-base` bakes
   tmux-resurrect/continuum (`@continuum-restore on`); on every fresh tmux-server start it restores
   saved sessions **as bash shells, not claude** (proven: `smoke-i1`/`smoke-i2` from a prior debug
   session reappeared; the operator's `alert-agent-tg-<chat>` came back as a shell). `ensure_session`
   sees `has-session` ok and **reuses the dead shell** — its readiness gate only runs on session
   *creation*. The DM is pasted into bash → `syntax error near '('` → 120s timeout → fallback. claude
   itself is fine (authenticated Max/Sonnet 4.6; the "not logged in" MOTD is a wrong check).
2. **`setMyCommands` 400** — `/edge-traffic`'s hyphen is an invalid Telegram command id
   (`[a-z0-9_]{1,32}`); one bad id rejects the **whole** menu, so it never registers.
3. **Head-of-line blocking** — the single synchronous getUpdates consumer blocks in `process_update`
   for the entire turn (`timeout_s=120`), so a queued static `/help` waits behind a slow/stuck turn.

And a structural gap: each driver launch starts a **fresh** claude conversation — no memory across
restarts. The operator wants durable, resumable named sessions.

## Fix A — Telegram menu command ids (frank `telegram-bridge`)

- Rename the `COMMANDS` key `/edge-traffic` → `/edge_traffic` (valid id; routing follows the key).
- `set_my_commands()` filters to ids matching `^[a-z0-9_]{1,32}$`, skipping (with a WARN) any invalid
  one — so a single bad id can never reject the whole menu again.
- Tests: every `COMMANDS` key (sans `/`) is a valid id; `set_my_commands` sends only valid ids (and
  still sends the rest if one were invalid). RED against the current `/edge-traffic`.

## Fix B — Disable continuum for agent pods (agent-images base + frank deployments)

- **agent-images** `agent-shell-base/etc/agent/tmux-resurrect.conf`: replace the static
  `set -g @continuum-restore 'on'` with a conditional honoring a new env —
  `@continuum-restore 'off'` when `AGENT_TMUX_RESTORE=off`, else `'on'` (default preserves human-shell
  behavior). Implemented with `if-shell '[ "${AGENT_TMUX_RESTORE:-on}" = off ]' …`, placed **before**
  the `run-shell …/continuum.tmux` so the plugin sees the setting at server start.
- **frank**: set `AGENT_TMUX_RESTORE=off` on the agent containers of `apps/alert-agent` **and**
  `apps/n8n-01` (operator: include n8n). Human shells (hermes, secure-agent-pod, paperclip, ruflo)
  leave it unset → continuum stays on, unchanged.
- This is defence/cleanliness; **Fix C is the load-bearing guarantee** (a dead session is recreated
  regardless of how it appeared).

## Fix C — Driver liveness check (agent-images `agent-session`)

`ensure_session` must stop trusting bare `has-session`. New behaviour: if the session is absent,
create it (as today, with `wait_ready`). If it **exists**, probe readiness quickly — capture the pane;
if it is **not a live claude REPL** (no `❯` within a short bounded wait — a dead bash shell, a
continuum-restored pane, or a crashed claude), **kill and recreate** it (then `wait_ready`). A live
REPL is reused untouched (warm path, no added latency). This generalizes the creation-only gate to
cover today's continuum bug and any future claude crash.

- TDD against the existing PATH-injected `FAKE_TMUX` harness, extended to model an *existing-but-dead*
  session (pane shows a shell prompt, no `❯`): assert the driver kills + recreates it, then submits to
  the fresh REPL; and that a live `❯` session is reused without a kill.

## Fix D — Thread agent turns (frank `telegram-bridge`)

Keep the single getUpdates consumer (one per bot token), but dispatch each agent turn to a **worker
thread** so the poll loop keeps reading and static commands answer immediately. A **per-`session_id`
lock** serializes same-session turns (no interleaved pastes into one tmux session); different sessions
and static `/help`/unknown replies run without waiting. The ⚡ receipt reaction still fires before the
turn; 👍/🤔 from the worker on completion.

- Tests over the patched seam: a slow turn on session A does not delay a `/help` reply; two concurrent
  same-session turns serialize (lock held); the reaction order per message is preserved.

## Fix E — Persistent resumable sessions + context management (agent-images `agent-session`)

Verified CLI semantics (claude 2.1.177): `claude --session-id <uuid>` (must be a valid UUID)
**creates-or-resumes** a conversation, works interactively with `--permission-mode auto`, persists to
`~/.claude/projects/<proj>/<uuid>.jsonl` (PVC-resident → survives restart). `--resume <id>` on a
*missing* session opens an interactive picker (would hang headless) — so `--session-id` is the right
create-or-resume primitive; `/clear` resets context keeping the id.

- **Deterministic id:** the driver derives `uuid = uuidv5(NAMESPACE, session_id)` (stable, valid UUID,
  no state file) and launches `claude --session-id <uuid> --permission-mode auto`. On pod restart the
  same `session_id` → same uuid → resumes the persisted conversation (memory across restarts), no
  reliance on continuum.
- **Idle reset (12h):** the driver tracks `last_activity` per session (a PVC file beside the turn
  counter). On a new request, if `now - last_activity > 12h`, send `/clear` first (fresh conversation,
  **same stable id**) before the message. Otherwise continue.
- **Proactive compact (>60%):** after a turn, read claude's context-usage indicator and send
  `/compact` when it exceeds 60%. **Measurement is the risk** — there is no programmatic "% full"
  signal; the driver parses the indicator from `/context` (or the status line) with the exact target
  **live-verified on the pod during implementation**, and falls back to claude's own auto-compact
  (near-limit) if parsing is unreliable. Flagged as a named gap.
- Persistence requires `~/.claude/projects` on the PVC — confirm the `alert-agent-home` mount covers
  it (it mounts `/home/agent`, so yes).

## Multi-repo sequencing

1. **agent-images** merges first (C + E + the `agent-shell-base` continuum conditional) → CI builds a
   new `multi-agent-shell` tag (all shells rebuild; human-shell behaviour unchanged by default).
2. **frank** implements A + D + the `AGENT_TMUX_RESTORE=off` env on alert-agent + n8n-01, then bumps
   `apps/alert-agent/manifests/deployment.yaml` (and `apps/n8n-01` for the env) to the new SHA
   (back-loaded last step; auto-covered by the generalized bumper once frank#570 lands).

`depends_on` is intra-plan only; this cross-repo order lives here + in PR sequencing.

## Test Plan (post-merge, operator-driven) — double cold-restart

After both PRs merge and ArgoCD rolls the new image:

1. **Cold restart #1** — `kubectl -n alert-agent rollout restart deploy/alert-agent` (genuinely cold;
   no continuum restore). From Telegram: send `what's the cluster status?` → expect ⚡ within ~1s →
   real answer in seconds → 👍 (no fallback). Tap/type `/help` → instant, **not** blocked behind the
   turn (threading). Confirm the command **menu is populated** and `/edge_traffic` works argless.
2. **Cold restart #2** — restart again, then DM a follow-up that references the prior turn → confirm
   the session **resumed with memory** (persistence via `--session-id`) and still answers. Verify no
   `smoke-*`/dead sessions reappear (`tmux ls` shows only live claude REPLs).
3. Spot-check: `tmux capture-pane` on the chat session shows a claude REPL (not a bash shell); the
   `~/.claude/projects/.../<uuid>.jsonl` for the chat exists and grew across restarts.

## Named gaps

- **60% compaction signal.** No programmatic context-% API; parsing claude's indicator is
  version-fragile. Mitigation: live-verify the parse target + fall back to claude auto-compact. If the
  parse is unreliable, the idle-12h `/clear` + auto-compact still bound growth (degraded, not broken).
- **`--session-id` resume across versions.** Behaviour verified by docs + must be live-verified on
  2.1.177 before relying on it; the reliability fixes (A–D) do **not** depend on E, so E can degrade to
  fresh-session-per-launch without breaking the bot.
- **`AGENT_TMUX_RESTORE` env reaching the tmux server.** The conditional needs the env in the tmux
  server's startup environment; live-verify the `if-shell` sees it (the driver/s6 env should carry it).

## Counter-arguments considered

- **"Just fix C; skip B."** C alone makes the bot work (dead sessions recreated), but continuum keeps
  saving/restoring dead shells every 5 min + on shutdown — wasted work and clutter. The operator chose
  to also disable it (incl. n8n), so B + C together.
- **"Use `--resume` not `--session-id`."** `--resume` on a missing id opens an interactive picker →
  hangs a headless driver. `--session-id <uuid>` is the create-or-resume primitive that never hangs.
- **"Daily-cron `/clear`."** Rejected for the operator's idle-12h + 60%-compact policy — resets tied to
  actual usage/idleness, not wall-clock, so an active conversation isn't wiped mid-stream.
