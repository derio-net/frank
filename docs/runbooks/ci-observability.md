# CI Observability Runbook (hum-ci)

How to read a failed `tekton/ci` check on an `agentic-stoa/hum` PR, and the
pipeline wiring that makes a red check actionable.

## Why this exists

The `tekton/ci` GitHub check used to be a bare `success`/`failure` with **no
link and no breadcrumb**. A red check told you *that* CI failed, never *why* or
*where the logs are* — so the only way to find the failing gate was to clone
the PR branch and reproduce `npm run check` locally. That's the systematic cost
of an opaque pass/fail: every contributor re-derives what the pipeline already
knew.

While wiring this up we also found a **correctness** bug it had been masking:
`pull-and-push` cloned the repo (landing on the **default branch, main**) and
only used the PR `sha` for the Gitea mirror push — it never checked the sha out.
So the gates ran against **main**, not the PR's changes, and every PR's
`tekton/ci` reflected main's state. (Concretely: hum#120's lint fix kept showing
red because CI was linting main, which still had the errors the PR fixed.) Now
`pull-and-push` does `git checkout --detach "$(params.sha)"` after cloning.

Fixed 2026-06-14 (`hum-ci-observability`) with three changes to
`apps/tekton/pipelines/hum-ci.yaml`:

0. **Test the PR commit** (correctness, above) — checkout the sha after clone.

1. **Deep-link the status.** Every `tekton/ci` status now sets `target_url` to
   the PipelineRun page on the Tekton dashboard. The "Details" link on the PR
   check goes straight to the run.
2. **Name the failing gate.** The monolithic `npm run check` step is split into
   named steps — `install → typecheck → lint → test`. The dashboard colours the
   failing step red, so you see which gate broke before opening a single log.

## When to use this runbook

Any time `tekton/ci` is red (or stuck) on a hum PR.

## How to read a failed run

1. On the PR, click **Details** next to the red `tekton/ci` check. It links to
   `https://tekton.cluster.derio.net/#/namespaces/tekton-pipelines/pipelineruns/<run>`.
   - **Over Tailscale:** the dashboard (`tekton.cluster.derio.net`, a
     LoadBalancer — `apps/tekton/manifests/dashboard-service.yaml`) is reachable
     over the derio tailnet, not public — which is where debugging happens.
     Without Tailscale, see "Reproduce locally" below.
2. In the run graph, find the red node:
   - **`pull-and-push`** red → infra (GitHub fetch / Gitea push / SSH), not your
     code. Check the step log; usually a token/SSH or Gitea-membership issue.
   - **`check`** red → open it and read which **step** failed:
     - `install` → `npm ci` (lockfile / registry / workspace-resolution).
     - `typecheck` → `tsc` errors. The log names file:line.
     - `lint` → ESLint errors. The log names file:line + rule.
     - `test` → a failing workspace test (`@hum/mobile` jest-expo is the heavy,
       slow one).
3. The step log is the same output `npm run <gate>` prints locally.

## Reproduce locally (no Tailscale, or to fix)

CI runs exactly this, so it reproduces 1:1:

```sh
npm ci
npm run check          # = typecheck && lint && test, --workspaces --if-present
# or a single gate:
npm run lint
```

## What's wired up

- **Pipeline:** `apps/tekton/pipelines/hum-ci.yaml`
  - `params.dashboard-base-url` (default `https://tekton.cluster.derio.net`) — base
    for the `target_url` deep-link; override per-run if the dashboard moves.
  - `check` task: `stepTemplate` carries the shared image/securityContext/env;
    steps `install/typecheck/lint/test` share the workspace PVC (one `npm ci`,
    reused by the gates). Pod requests/limits = the max across steps, set by the
    heavier `test` step (2Gi/4Gi for the RN/jest-expo suite).
  - `finally`: dual status to GitHub (mandatory) + Gitea (best-effort), same
    `tekton/ci` context and SHA. Both GitHub posts now carry `target-url`.
    `gitea-status` has no `target-url` param, so its post is unchanged.
- **Status task:** `apps/tekton/tasks/github-status.yaml` — already plumbs a
  `target-url` param end-to-end to the Commit Status API's `target_url`; the
  pipeline simply never passed it before.

## Future enhancements (not in this change)

- **Inline annotations.** The Commit Status API can't annotate files. A GitHub
  **check-run** (via the GitHub App) could surface the failing file:line/rule
  inline in the PR's Files tab. That's a larger change (different API + app
  auth) and is deliberately out of scope here.
- **Per-gate checks.** Splitting `tekton/ci` into `tekton/typecheck`,
  `tekton/lint`, `tekton/test` would name the gate in the check list itself
  (no click). Trade-off: multiple required checks to manage in branch
  protection. The named-steps approach gives most of the benefit for none of
  that cost.
