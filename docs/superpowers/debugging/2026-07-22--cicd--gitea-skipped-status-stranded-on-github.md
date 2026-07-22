# Gitea `skipped` statuses strand GitHub PR checks on `pending` forever

**Date:** 2026-07-22
**Layer:** cicd
**Fix:** `apps/tekton/triggers/eventlistener.yaml` (gitea-status-bridge `gh_state` overlay)
**Guard:** `scripts/tests/test_stoa_status_bridge.py::test_bridge_maps_gitea_only_states`

## Symptom & reproduction

Four open PRs across the stoa mirrors — all titled `ci: gate automatic
workflows on CI_AUTHORITY` — showed `gitea-actions/*` checks stuck **pending**
on GitHub, while the corresponding Gitea Actions jobs had long since finished
as **skipped**. No rerun, no new push, and no amount of waiting cleared them;
`mergeStateStatus` sat at `UNSTABLE` indefinitely.

Reproduce: push any commit to a mirrored repo while the Gitea org variable
`CI_AUTHORITY=github`, so the `CI_AUTHORITY`-guarded jobs skip on the Gitea
side. The bridge writes `pending` when the job is queued and never writes
anything again.

```bash
gh pr view 39 --repo agentic-stoa/cnc-frd --json statusCheckRollup \
  --jq '.statusCheckRollup[] | select(.context? // "" | startswith("gitea-actions/"))'
# → every entry: "state": "PENDING", targetUrl → a finished Gitea run
```

## Evidence

**1. The two halves are separate questions.** The skipping is correct; only
the reporting is broken.

The PRs add a job-level guard:

```yaml
if: (vars.CI_AUTHORITY || 'github') == (github.server_url == 'https://github.com' && 'github' || 'gitea')
```

On the Gitea side `github.server_url` is the Gitea instance, so the
right-hand side is `'gitea'`, while the org variable is deliberately
`CI_AUTHORITY=github` for the parallel-running window (manual op
`cicd-stoa-gitea-org-actions-config`; cutover is the August flip). `'github'
!= 'gitea'` → **every guarded job skips on Gitea, by design.**

**2. The stranded status is a commit status, not a check run.** In the
rollup, the `gitea-actions/*` entries are `StatusContext`, not `CheckRun` —
plain `POST /repos/{o}/{r}/statuses/{sha}` writes from the
`stoa-status-bridge` pipeline. A commit status has no lifecycle of its own:
it is whatever the last *successful* POST said, with no timeout and nothing
that reconciles it.

**3. The bridge was failing, loudly, in a place nobody looks.**

```
$ kubectl -n tekton-pipelines get pipelinerun | grep stoa-status-bridge
stoa-status-bridge-khp9s   False   Failed   ...     (× 30)

$ kubectl -n tekton-pipelines logs <pod> --all-containers
Reported status 'skipped' for aea1954d... (HTTP 422)
{
  "message": "Validation Failed",
  "errors": "Validation failed: State is not included in the list",
  ...
}
```

All 30 failures, one state: `skipped`. (`warning` was not observed but is the
same class.)

## Root cause

**Gitea's `CommitStatusState` vocabulary is a superset of GitHub's, and the
bridge assumed the two were identical.** GitHub's status API accepts exactly
`pending | success | error | failure`; Gitea additionally has `skipped` and
`warning`. `stoa-status-bridge` forwards `body.state` verbatim — its own
header says *"State vocabulary … is identical between the two APIs and passes
through unmapped."* It is not.

So a skipped job produces: Gitea posts `pending` at queue time → bridge
forwards it → GitHub shows pending. Gitea then posts `skipped` → bridge
forwards it → GitHub 422s → `github-status` exits non-zero → **the pending
status is never superseded.** Permanently pending, because commit statuses
never expire.

The failure mode was anticipated and explicitly accepted in the trigger's own
comment:

> *Gitea state values outside GitHub's vocabulary (e.g. 'warning') would 422
> in github-status and fail the PipelineRun visibly — acceptable failure
> shape, revisit only if it fires.*

It fired. The shape was **not** acceptable: the PipelineRun failure is visible
only in the Tekton namespace, while the consequence — a permanently blocked
PR — is what the operator actually sees, with no link between the two.

## Fix

Narrow Gitea's vocabulary to GitHub's in the `gitea-status-bridge` CEL
overlays, before the value is ever bound:

```yaml
- key: gh_state
  expression: "(body.state == 'skipped' || body.state == 'warning') ? 'success' : body.state"
- key: description
  expression: "(body.state == 'skipped' || body.state == 'warning') ? 'Gitea: ' + body.state : (has(body.description) ? body.description : '')"
```

…with the `state` binding moved from `$(body.state)` to
`$(extensions.gh_state)`.

Both Gitea-only states mean "not a failure", so both map to `success` — which
also matches GitHub's own Checks semantics, where a skipped job is
non-blocking. The real state survives in the description (`Gitea: skipped`),
so a skipped job never masquerades as a genuine green check.

**Why the CEL overlay and not the Pipeline's task params** — the natural place
for a translation is `stoa-status-bridge`'s `state` param, but
`apps/root/templates/tekton-extras.yaml` still carries array-item
`jqPathExpressions` on `Pipeline` (`.spec.tasks[]?…`). Under
`RespectIgnoreDifferences=true` those freeze the whole `.spec.tasks` array:
ArgoCD carries the live array into every apply and silently discards the edit
while reporting Synced (frank#664; `test_tekton_ignore_rules_no_arrays.py`
documents `Pipeline`/`Task` as known, still-exempted debt). The
`EventListener` rule was de-arrayed by that same fix, so `spec.triggers` does
apply — it is the only surface where this fix actually reaches the cluster.

Verified by evaluating both expressions with `cel-python` against real payload
shapes: `skipped`/`warning` → `success`, and `pending`/`success`/`failure`
pass through untouched with their original descriptions.

## Rejected hypotheses

- **Gitea never sent a terminal status.** Ruled out — the bridge logs show the
  `skipped` status arriving and being forwarded.
- **The CEL filter dropped the event.** Ruled out — the filter only excludes
  non-`agentic-stoa` repos and `tekton/*` contexts; the PipelineRuns exist.
- **The GitHub token lost `statuses: write`.** Ruled out — the 422 is a
  validation error on the payload, and `tekton/ci` statuses posted `SUCCESS`
  on the same shas at the same time with the same Secret.
- **The `CI_AUTHORITY` guard is itself wrong.** Ruled out — skipping on the
  Gitea side is exactly what `CI_AUTHORITY=github` is for during parallel
  running. The guard PRs are correct and unrelated to the reporting bug; they
  merely triggered the first mass `skipped` event.
- **The GitHub-native checks failing (`FAILURE`) is part of this bug.** Ruled
  out — those are the exhausted GitHub Actions minutes tier, a known
  pre-existing condition on these repos.

## Backfill (one-shot, operator)

The fix only affects future webhook events; Gitea does not re-send statuses
for jobs that already finished. The already-stranded contexts on the four open
PRs must be overwritten once, by hand, after the fix is synced.
