# Plan: Surge Detector — Rework 1 (cooldown + grounded narrative)

Rework against `2026-05-25--obs--surge-detector-fix` (Deployed). See `_meta.yaml`
for `parent_plan` and `origin_items`. Parent shipped correctly; two issues
surfaced in operation on 2026-05-26.

## Why

1. **Notable spam.** With the probe excluded, the blog edge still sees frequent
   crawler bursts (Baiduspider, wpbot, scrapers) of 50–270 req/hr — 10 of 24
   hours on 2026-05-26 exceeded `SURGE_ABS_FLOOR`. Each such hour is an
   edge-Major that the visitor gate correctly downgrades to a non-urgent
   Notable (GoatCounter shows ~0 humans) — but `/surge-check` is stateless and
   runs every 15 min against the same completed hour, so it **re-sends the same
   Notable ~4× per hot hour** (~20/night). Exactly the repeat-message risk the
   parent's code review flagged (finding I2) and deferred.
2. **Phantom Hacker News.** `prompts/investigate-surge.txt` pre-seeds "likely a
   Hacker News hit" as the first cause, while `build_for_surge` ships a fact
   sheet with no referrers/paths/UAs. The model can't satisfy "cite specific
   referrers if they appear" (none present) so it parrots the seeded HN label
   with zero evidence, every time.

## What this rework does

**A — De-duplicate notifications (edge-triggered + cooldown floor).** The helper
is a single replica, so keep a small **in-memory** notification state (last tier
+ timestamp) — no PVC, `readOnlyRootFilesystem` stays. Notify only on a rising
edge (tier first appears, or escalates Notable→Major), stay silent while the
same-or-lower tier persists across ticks, re-arm when traffic returns to `None`.
A `SURGE_COOLDOWN_HOURS` floor (default 6) suppresses re-notification of the same
tier even across short dips, so a flapping crawler isn't a fresh episode each
hour. A pod restart re-arms (at most one extra message — acceptable). URGENT
escalation always passes immediately.

**B — Ground the narrative.** Enrich `build_for_surge` with the data the prompt
already asks the model to cite — top referrers (GoatCounter `/api/v0/stats/toprefs`
for the window), top paths and top user-agents (Caddy, probe-excluded) — and
rewrite `investigate-surge.txt` to classify **only from evidence**: HN only if
`news.ycombinator.com` is in referrers; scraper/crawler if UAs are bots and
visitors ≈ 0; "cause undetermined" when there's no discriminating data. Never
name a cause absent supporting facts.

## Non-goals

- No probe/blackbox changes (parent's identity tagging is correct and stable).
- No cron suspend during deploy — this rework only *reduces* notifications, so
  there's no false-page risk window to guard against.
- No persistent (PVC) notification state — in-memory on the single replica is
  sufficient; a restart re-arming is harmless.

## Config (env, on the Deployment)

| Var | Default | Meaning |
|---|---|---|
| `SURGE_COOLDOWN_HOURS` | `6` | Min hours before re-notifying the same tier (edge-triggered dedup floor) |

(`SURGE_ABS_FLOOR=50`, `SURGE_VISITOR_FLOOR=10` unchanged from the parent.)

## Phases

1. **ai-alert-helper logic (TDD)** — cooldown dedup, enriched `build_for_surge`,
   grounded prompt.
2. **Build, deploy & verify (on main)** — bump 0.1.5→0.1.6, CI build, deploy,
   observe dedup + grounded narrative live.
3. **Docs & close-out** — operating-post tuning update, gotchas, building-post
   note, status.

## Build / deploy

Same as parent: `gh workflow run build-ai-alert-helper.yml --ref <branch>`
(version-pinned tag bumped to 0.1.6), merge to main, ArgoCD syncs. No manual
docker.
