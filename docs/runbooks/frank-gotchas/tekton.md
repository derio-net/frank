# Frank Gotchas — Tekton

Long-form companion to the **Tekton** section in `agents/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

## `computeResources`, not `resources`

Tekton v1 Task CRD uses `computeResources` (not `resources`) for step resource requests/limits — `resources` silently fails schema validation, causing ArgoCD `ComparisonError` ("field not declared in schema") that blocks all syncs for the app. (Note: native K8s containers in CronJobs/Jobs use `resources` — this only applies to Tekton Task steps.)

## `$(tasks.status)` returns "Completed" when tasks are skipped

Tekton `$(tasks.status)` in `finally` blocks returns `"Completed"` (not `"Succeeded"`) when some tasks are skipped via `when` clauses — use `in ["Succeeded", "Completed"]` for success checks.

## PVC workspaces mount as root

Tekton PipelineRun PVC workspaces mount as root — tasks running as non-root UID need `taskRunTemplate.podTemplate.securityContext.fsGroup` set in the TriggerTemplate/PipelineRun spec.

## `runAsUser: 65534` (nobody) → `HOME=/` (read-only)

Tekton tasks with `runAsUser: 65534` get `HOME=/` from `/etc/passwd`. Since `/` is read-only, any command that writes to `$HOME` fails — including `git config --global`. Set `env: [{name: HOME, value: /tekton/home}]` explicitly on the step.

## Gitea sends `X-Gitea-Event`, not `X-GitHub-Event`

Tekton `github` ClusterInterceptor silently drops Gitea webhooks because Gitea sends `X-Gitea-Event` header instead. Use `cel` interceptor with `header.match('X-Gitea-Event', 'push')` instead.

## Gitea Actions runner: DinD needs `DOCKER_TLS_CERTDIR=""`

The `docker:dind` sidecar in `apps/gitea-runner` defaults to generating TLS certs and listening on **2376** when `DOCKER_TLS_CERTDIR` is unset. act_runner is pointed at plain-TCP `tcp://localhost:2375`, so the pair comes up "Running" while every job hangs waiting for a docker daemon that is listening one port over, TLS-only. Set `DOCKER_TLS_CERTDIR: ""` and pass `--host=tcp://0.0.0.0:2375` explicitly (guarded by `scripts/tests/test_gitea_runner_app.py`).

## Status bridge: Gitea's state vocabulary is a SUPERSET of GitHub's

GitHub's commit-status API accepts exactly `pending | success | error | failure`. Gitea's `CommitStatusState` **also** has `skipped` and `warning`. The `stoa-status-bridge` originally forwarded `body.state` verbatim on the documented assumption that the vocabularies were identical — they are not.

The failure is asymmetric and nastier than it looks, because a **commit status has no lifecycle of its own**: it is whatever the last *successful* POST said, with no timeout and nothing that reconciles it. So a skipped Gitea job produces:

1. Gitea posts `pending` at queue time → bridge forwards it → GitHub shows pending.
2. Gitea posts `skipped` when the job is gated out → bridge forwards it → GitHub **422s** (`"Validation failed: State is not included in the list"`) → `github-status` exits non-zero.
3. The pending status is never superseded. **The PR stays `UNSTABLE` forever**, and no rerun or new push clears it.

The PipelineRun failure *is* visible — but only in `tekton-pipelines`, with nothing linking it to the blocked PR. Diagnose with:

```bash
kubectl -n tekton-pipelines get pipelinerun | grep stoa-status-bridge   # Failed rows
kubectl -n tekton-pipelines logs <pod> --all-containers | grep 'HTTP 4'
```

Fixed 2026-07-22 by narrowing the vocabulary in the `gitea-status-bridge` CEL overlays (`gh_state`: `skipped`/`warning` → `success`, everything else pass-through) and binding `state` to `$(extensions.gh_state)`. The real state is kept in the description (`Gitea: skipped`) so a gated-out job never reads as a genuine green check. Guarded by `scripts/tests/test_stoa_status_bridge.py::test_bridge_maps_gitea_only_states`.

**Why the fix lives in the EventListener and not the Pipeline:** `apps/root/templates/tekton-extras.yaml` still carries array-item `jqPathExpressions` on `Pipeline` (`.spec.tasks[]?…`), which under `RespectIgnoreDifferences=true` freeze the whole `.spec.tasks` array — an edit to the bridge's task params would be silently discarded while ArgoCD reports Synced (see the ArgoCD section; frank#664). The `EventListener` rule was de-arrayed by that fix, so `spec.triggers` genuinely applies.

**Trigger context:** the first mass `skipped` event came from the `CI_AUTHORITY` guard PRs. Skipping on the Gitea side is *correct* while the org variable is `CI_AUTHORITY=github` (the parallel-running default) — don't chase the guard, it isn't the bug. Incident writeup: `docs/superpowers/debugging/2026-07-22--cicd--gitea-skipped-status-stranded-on-github.md`.

Note the bridge does **not** backfill: Gitea never re-sends a status for a job that already finished, so statuses stranded before the fix must be overwritten once by hand.

## Gitea Actions runner: registration is one-shot PVC state

`act_runner` registers against Gitea once and persists its identity in `/data/.runner` on the PVC. Rotating `STOA_GITEA_RUNNER_TOKEN` (or re-minting the registration token) does **NOT** re-register an already-registered runner — the token is only read when `/data/.runner` is absent. To force a fresh registration: scale the Deployment to 0, delete `/data/.runner` (or the whole PVC — the tool cache is rebuildable), scale back up. Symptom of a half-dead registration: runner pod healthy but the Gitea admin runners page shows it Offline.
