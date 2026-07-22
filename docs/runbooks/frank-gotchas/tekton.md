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

## `CI_AUTHORITY` is two variables, one per forge

The parallel-running guard on the stoa mirrors is a job-level condition:

```yaml
if: (vars.CI_AUTHORITY || 'github') == (github.server_url == 'https://github.com' && 'github' || 'gitea')
```

The design note says cutover is *"flip one variable, not edit five repos again"* — true **per forge**, and easy to misread as one variable overall. `vars.CI_AUTHORITY` resolves in the **forge that is running the workflow**, and Gitea and GitHub have entirely separate Actions-variable namespaces. Setting only Gitea's leaves GitHub's unset, which falls back to `'github'` — so **both** sides consider themselves authoritative and both run.

A real cutover is therefore two writes:

- **Gitea** — org variable, settable via API with the admin creds in secret `gitea-secrets` (ns `gitea`, keys `username`/`password`):
  ```bash
  curl -X PUT -u "$GU:$GP" -H 'Content-Type: application/json' -d '{"value":"gitea"}' \
    http://gitea-http.gitea.svc.cluster.local:3000/api/v1/orgs/agentic-stoa/actions/variables/CI_AUTHORITY
  ```
  (HTTP 204; the `tekton-bot` token is **not** enough — it lacks `read:organization`.)
- **GitHub** — **must be REPO-level, not org-level.** The `agentic-stoa` GitHub plan does not allow *organization* variables to be used by **private** repos (`"Organization variables cannot be used by private repositories with your plan"`), and every mirror is private — so the single org-level lever the migration plan assumed **does not exist on this plan**. *Repository* variables are not plan-gated and work fine; it is 5 writes instead of 1. Needs repo `admin`: the personal account has it, the `clawdia` token does not (`permissions.admin=false`).
  ```bash
  for r in second-brain cnc-fr cnc-frd cnc-fru hermes-brain; do
    gh api -X POST "/repos/agentic-stoa/$r/actions/variables" -f name=CI_AUTHORITY -f value=gitea
  done
  ```

Symptom of doing only the Gitea half: Gitea jobs run and report correctly, while GitHub jobs *also* run — visible as `failure` check runs rather than `skipped` ones. Both halves flipped to `gitea` on 2026-07-22 (proven on `cnc-fru#36` sha `aac669d1`: GitHub `test`/`e2e`/`smoke` all `skipped`). **Reversing in August needs both halves too** — delete the 5 repo variables *and* set the Gitea org variable back to `github`, or you land in the mirror-image split.

Unrelated to the variable but adjacent: `release.yml` in `cnc-frd` and `cnc-fru` carries **no** `CI_AUTHORITY` guard at all, so it is unaffected by either side of the flip. Every other workflow across the 5 mirrors is fully guarded.

Manual op: `cicd-stoa-ci-authority-cutover`.

## Gitea Actions runner: job containers are DinD SIBLINGS, not its host

Workflows written for GitHub-hosted runners assume the job and the Docker daemon share one machine. On `act_runner` + DinD they do not — the job is a container created *on* the daemon — so **both** affordances are missing and every `docker` step fails ~5s in:

```
ERROR: failed to connect to the docker API at unix:///var/run/docker.sock
       dial unix /var/run/docker.sock: connect: no such file or directory
```

1. **The daemon.** act_runner only mounts the docker host into job containers when it is a **unix socket** (its own `generate-config` doc: `"-"` means *"the docker host won't be mounted to the job containers"*). Ours is TCP, so the job gets no `DOCKER_HOST` at all and the CLI falls back to the non-existent socket. `docker_host: tcp://localhost:2375` is still correct **for act_runner itself** — it shares the pod netns with DinD — it just never reaches the job.
2. **Published ports.** `docker run -p 8088:80` publishes on the DinD host, so the job's own `curl http://localhost:8088` misses it.

Measured on the live daemon 2026-07-22:

```
bridge  daemon localhost:2375 FAIL   published port FAIL
host    daemon localhost:2375 OK     published port OK
```

Fix — `network: host` covers both halves; `options` injects what act_runner won't:

```yaml
container:
  docker_host: "tcp://localhost:2375"
  network: "host"
  options: "-e DOCKER_HOST=tcp://localhost:2375"
```

Guarded by `scripts/tests/test_gitea_runner_app.py::test_job_containers_can_reach_the_docker_daemon`. **Trade-off:** with `capacity: 2` two concurrent docker-using jobs share one port namespace, so fixed published ports can collide — the shared daemon already collided on fixed container/network *names*, so this widens an existing hazard, not a new one. Drop capacity to 1 if it bites.

**Why this hid for so long:** of the 14 workflows across the 5 mirrors only `cnc-fr`/`cnc-frd`/`cnc-fru` use the docker CLI. The migration's "smoke-proven" evidence ran on `second-brain`, one of the two repos that don't — so the gap only surfaced when `CI_AUTHORITY=gitea` made Gitea the sole authority. Full prose: `docs/superpowers/debugging/2026-07-22--cicd--gitea-job-containers-cannot-reach-dind.md`.

## Gitea Actions runner: registration is one-shot PVC state

`act_runner` registers against Gitea once and persists its identity in `/data/.runner` on the PVC. Rotating `STOA_GITEA_RUNNER_TOKEN` (or re-minting the registration token) does **NOT** re-register an already-registered runner — the token is only read when `/data/.runner` is absent. To force a fresh registration: scale the Deployment to 0, delete `/data/.runner` (or the whole PVC — the tool cache is rebuildable), scale back up. Symptom of a half-dead registration: runner pod healthy but the Gitea admin runners page shows it Offline.
