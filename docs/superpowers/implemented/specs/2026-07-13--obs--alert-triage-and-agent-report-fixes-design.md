# Design: Frank alert-triage skill + alert-agent report fixes

**Status:** Deployed
**Layer:** obs
**Branch:** feat/alert-triage-and-agent-fixes
**Date:** 2026-07-13

## Context

Two related deliverables, built in one workspace / one PR because they share a
format contract:

1. A new operator-invoked **`frank-alert-triage`** skill — the interactive
   counterpart to the autonomous alert-agent. Today, "Grafana is alerting on
   Frank" is investigated ad-hoc (6+ exploratory tool calls: fetch firing
   alerts, inspect pods, cross-reference known-benign patterns). Every step is
   deterministic and repo-documented, so it belongs in a skill.
2. Five operator-reported **alert-agent** misbehaviours, all root-caused this
   session, all deploying via the existing hash-suffixed ConfigMap roll (no
   image rebuild).

The two share one thing: the **alert-classification decision tree** and the
**compact report format**. They stay separate implementations (different
execution contexts — a kube-credentialed laptop vs an HTTP-only pod) but cite
the same documented contract.

## Deliverable 1 — `frank-alert-triage` skill

Repo-local skill at `agents/skills/frank-alert-triage/`. A markdown playbook
(`SKILL.md`) plus a small **stdlib-only pure classifier** (`classify.py` +
`test_classify.py`) — no new runtime service. Invoked by the operator from the
laptop, where `kubectl` + the Grafana alert API are reachable.

`classify.py` exposes `classify(labels: dict, pod_state: str | None) -> Verdict`
— pure, no kube/network dependency (the caller supplies the resolved pod state),
so it is deterministically unit-tested. The skill's `SKILL.md` drives the fetch
(Grafana API) + pod-resolution (`kubectl`) and calls `classify()` per alert. The
alert-agent does **not** import it (separate HTTP-only ConfigMap) — it documents
the same tree in its own `SKILL.md`.

### Flow
1. Fetch firing alerts (`/api/prometheus/grafana/api/v1/alerts`, admin creds
   from the `victoria-metrics-grafana` secret; state `Alerting`).
2. Classify each via a **label-driven decision tree**:
   | Signal | Verdict |
   |---|---|
   | `canary: true` | **muted/expected** — canary, never paged (e.g. cert-expiry #251) |
   | `gpu_timeshare: true` | **by-design** — one GPU workload down by design; real pager is `gpu-node-both-down` only |
   | readiness rule + referenced pod is `Succeeded`/`Completed`/absent | **false-positive** — stale KSM series / graceful-shutdown tombstone |
   | `github_issue: frank-ops#N` | annotate with the **known tracker** |
   | none of the above | **unexplained** — escalate |
3. For readiness-based alerts, resolve the alert's `pod` label against the live
   cluster (live vs ghost tombstone) — the check that distinguishes a real
   NotReady from a graceful-shutdown artifact.
4. Emit a **compact table verdict** (same column style as the agent report):
   `alert | severity | verdict | one-line reason/action`.
5. **Classify-and-recommend only** — never mutate (no pod deletes/acks; the
   auto-mode classifier correctly blocks these). Genuinely-unexplained alerts
   hand off to `fr-debugging`.

### Non-goals
- No cluster mutation. No auto-remediation. No new deployed service.
- Not a replacement for the alert-agent (autonomous/Telegram) — the interactive
  sibling.

## Deliverable 2 — alert-agent fixes

All in `apps/alert-agent/`. Root causes and fixes:

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | Fixates on "Hacker News" | Hard-coded example in `SKILL.md:12` + `orchestration.py:81` | Evidence-driven phrasing (name source from `top_referrers`/`top_user_agents`, else "undetermined"); name **no** example |
| 2 | Replies with raw JSON | `{"text":…}` envelope contract (`SKILL.md:19`); `render_payload` posts a string envelope verbatim (`bridge.py:160`) | Drop the envelope from the taught contract (plain-text reply); `render_payload` defensively unwraps a `{"text":…}` **string** as belt-and-braces |
| 3 | Too talkative / no tables | `SKILL.md:17-22` forbids tables + `<>&` — **stale** (sender is plain-text, no parse_mode, `bridge.py:5,51`) | Rewrite output contract: **prefer** a compact plain-text aligned table + a hard line budget |
| 4 | Times out on explicit asks | `DM_TIMEOUT_S=600` but the agent probe-sweeps past it | **Behavioural**: bound a DM turn to ≤2 probes + "answer now"; the table format forces brevity. NOT a bigger timeout |

### Decided design
- **Telegram output = compact PLAIN-TEXT aligned lines**, no parse_mode — immune
  to the historic `<>&` 400 gotcha. "Table-like" = aligned `label value detail`
  columns, not a monospaced grid (Telegram plain text isn't monospaced).
- **Unify the contract to plain-text everywhere.** Drop the `{"text":…}` JSON
  envelope from the DM path *and* the cron digest/surge prompts
  (`orchestration.py:82,106`); `render_payload`'s dict branch + a new
  string-unwrap branch stay purely as defensive fallbacks. Removes the
  dual-contract the model has to juggle.
- **Skill and agent stay separate**, sharing the decision tree + table format as
  a documented convention (the agent SKILL.md notes it matches the skill's).

### Testing
- `classify.py` → `test_classify.py`: one case per decision-tree branch
  (canary, gpu_timeshare, readiness+ghost pod, readiness+live pod, known
  tracker, unexplained) using the real label shapes captured this session.
- `render_payload` string-envelope unwrap → new unit test in `test_bridge.py`
  (existing patterns: canned `_http_post_json`, dict-payload assertions).
- No behavioural regression to allowlist / routing / reaction / threading tests.
- Prompt-content assertions: no "Hacker News" literal; plain-text contract.

## Deployment
- `SKILL.md`, `orchestration.py`, `bridge.py` are all hash-suffixed
  ConfigMap-mounted → any edit rolls the pod (Application has `prune: true`).
  Deploy = git merge + ArgoCD sync. No image rebuild.
- The `frank-alert-triage` skill is repo-only (no cluster artifact).

## Test Plan (post-merge, operator-driven, from host)

These prove real deployment; they need the operator's kube-credentialed host +
the live Telegram bot, so they run after merge (not in CI).

1. **Skill** (`obs-alert-triage-classifies`) — run `frank-alert-triage` against
   the live firing set; the verdict table matches this session's manual triage
   (canaries → muted, `gpu_timeshare` → by-design, a readiness false-positive
   flagged when a `Succeeded`/absent pod is present), with zero cluster
   mutation.
2. **Agent — no Hacker News** (`obs-alert-agent-evidence-not-hn`) — trigger a
   digest/surge (or `/surge`); the narrative attributes the source from
   evidence or says "undetermined", never "Hacker News".
3. **Agent — plain-text table** (`obs-alert-agent-plain-text-table`) — DM the
   agent (`/status` or a free-text question); the reply is a compact plain-text
   table, no raw `{"text":…}` envelope, no prose wall.
4. **Agent — answers explicit asks** (`obs-alert-agent-answers-explicit-asks`) —
   a focused explicit question returns a real answer within the turn budget,
   not the timeout fallback.

## Implementation Plans

| Plan | Repo | File | Depends on |
| ---- | ---- | ---- | ---------- |
| 2026-07-13--obs--alert-triage-agent-fixes | `derio-net/frank` | `2026-07-13--obs--alert-triage-agent-fixes` | — |
