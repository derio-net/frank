# Design: health-bridge — blindness ≠ death (DatasourceError handling + alertname-agnostic heal)

**Layer:** obs (fix/extension of the health-bridge layer)
**Date:** 2026-06-08
**Status:** Deployed
**Code repo:** `derio-net/health-bridge` (Go) — `bridge.go`, `github.go`, `bridge_test.go`
**Deploy/docs repo:** `derio-net/frank` — `apps/health-bridge/`, blog Layer 23/16

## Implementation Plans

| Plan | Target repo | Slug | Status |
|------|-------------|------|--------|
| 2026-06-08--obs--health-bridge-blind-state | `derio-net/frank` | `2026-06-08--obs--health-bridge-blind-state` | Deployed |

## Motivation — 2026-06-08 power-outage incident

A whole-cluster power outage took Frank down overnight. On recovery, Grafana's
datasource was briefly unreachable, so Grafana fired its built-in
**`DatasourceError`** alert. Because the affected alert *rules* carry
`github_issue` labels, the `DatasourceError` instances inherited those labels
(~10 layer rules). health-bridge faithfully:

- set ~10 Derio Ops board trackers to `dead`/`degraded`, and
- created 5 bug Issues (`frank-ops#44–48`), all titled
  `[Bug] DatasourceError is dead — …`, every summary showing `[no value]`
  (the alert templates could not resolve their data because the datasource
  itself was erroring).

Grafana was then **rescheduled to a fresh pod** (`restarts=0`, started
04:03:25Z — *after* the 04:03:00–04:03:16Z firing). A new Grafana process has
no in-flight `DatasourceError` instance to clear, so the matching `resolved`
webhook **never fired**. Result: the board stayed red and the bugs were
stranded, with no self-heal possible.

Manual recovery was a synthetic-resolve replay (a `resolved` payload with
`alertname=DatasourceError` + the stranded `github_issue` labels), which
flipped all 10 trackers healthy and closed all 5 bugs via the bridge's own
idempotent path.

## Root cause

Two distinct defects, both exposed by the outage:

1. **Blindness treated as death.** A `DatasourceError` (and `NoData`) means
   *"monitoring cannot see this layer,"* not *"this layer is dead."* The bridge
   mapped a critical-severity `DatasourceError` firing to `dead` and
   manufactured a bug — none of which described a real fault.

2. **Auto-close keyed on alertname.** `Bridge.processAlert` closes bugs via
   `github.FindOpenBugs(repo, alertName, number)`, which matches a bug by its
   title prefix `[Bug] <alertName> is dead` **and** the body feature ref. A bug
   created under `alertname=DatasourceError` can therefore only be closed by a
   `DatasourceError` resolve — never by the real per-rule resolve
   (e.g. `Layer 18 Persistent Agent Heartbeat Stale`) that actually arrives on
   recovery. (Observed: `frank-ops#18` flipped healthy at 04:13:40Z via the
   real-rule resolve, yet its bug `#44` stayed open.)

## Design (operator-approved)

### 1. Source fix — `DatasourceError`/`NoData` ⇒ `degraded`, no bug

Add `isBlindAlert(alertname) bool` (true for `DatasourceError`, `NoData`). In
`processAlert`, when the alert is firing **and** `isBlindAlert`:

- cap the lifecycle state at `degraded` (never `dead`), and
- skip bug creation entirely.

`degraded` reuses an existing board state — no schema change. This stops the
false-bug storm at its source: an outage that blinds monitoring marks the
affected layers `degraded` ("can't fully see this") instead of fabricating
deaths and bugs.

### 2. Safety net — heal closes bugs by feature-ref alone

Add `github.FindOpenBugsByFeature(repo string, number int) ([]int, error)` that
matches open `[Bug] …` issues by the body feature ref
(`**Feature Issue:** <org>/<repo>#<n>\n`, newline-terminated to avoid `#2`
matching `#24`) **regardless of alertname**. In `processAlert`'s
`status == "resolved"` branch, use `FindOpenBugsByFeature` (not the
alertname-aware `FindOpenBugs`) so a tracker returning to `healthy` closes
*any* open bug for that tracker — including bugs stranded by a future
alertname mismatch.

Keep the existing alertname-aware `FindOpenBugs(repo, alertName, number)` for
the **create-dedup** path (`newState == "dead"`) so two distinct real alerts on
the same tracker still each get their own bug.

This is defense-in-depth: fix (1) prevents the specific storm; fix (2) makes
recovery robust to *any* alertname mismatch.

## Test plan (TDD — tests first)

In `bridge_test.go`:

- (a) `DatasourceError` firing, severity `critical` ⇒ state `degraded`, **no**
  `CreateBugIssue` call.
- (b) `NoData` firing ⇒ state `degraded`, no bug.
- (c) Real critical alert (e.g. `Agent Pod Not Running`) firing ⇒ state `dead`
  **and** a bug created (regression guard — unchanged behaviour).
- (d) Resolve with `alertname="Layer 18 …"` closes an open
  `[Bug] DatasourceError is dead` bug for the same feature ref
  (cross-alertname heal via `FindOpenBugsByFeature`).

## Deployment

- Tag-driven release of `health-bridge` (`v0.3.1 → v0.4.0`). **Verify the tag
  tree contains the new symbols before relying on the GHCR build**
  (`git grep isBlindAlert <tag>` non-empty) — the v0.3.0 stale-tag incident.
- Bump the image pin in `apps/health-bridge/manifests/deployment.yaml`; ArgoCD
  syncs.
- **Verify end-to-end**: replay a synthetic `DatasourceError` resolve against
  the rolled-out pod and confirm a cross-alertname bug close + lifecycle revert
  in the logs (a layer is not "Deployed" until the workflow is observed).

## Named gaps / non-goals

- We do **not** add a distinct `unknown`/`blind` board state (operator chose to
  reuse `degraded`); revisit only if `degraded` proves ambiguous in practice.
- `NoData` semantics: treated identically to `DatasourceError` (blindness). If a
  real "expected metric absent" signal is ever wired through health-bridge it
  must use a non-blind alertname.
- Does not address willikins-namespace trackers not being on the Derio Ops
  board (pre-existing `issue willikins#N is not on project` log noise) — out of
  scope here.
