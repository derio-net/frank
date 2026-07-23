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

## Gitea Actions runner: a config edit does NOT roll the pod by itself

`act_runner` reads `/config/config.yaml` exactly **once, at boot**. Shipped as a plain ConfigMap the name never changes, so ArgoCD writes new content into a ConfigMap the running pod has already read: **the app reports Synced, the live ConfigMap holds the new config, and the runner keeps serving the old one indefinitely.** Bit on 2026-07-23 deploying frank#674 — ArgoCD was `Synced` at the merge commit and the ConfigMap carried `network: "host"`, while the runner still had the previous day's config; it only took effect after a manual `kubectl rollout restart deploy/act-runner`. Same shape as the gitea `gitea-inline-config` gotcha.

Fixed by shipping the config through Kustomize `configMapGenerator` (`apps/gitea-runner/manifests/kustomization.yaml`), which hash-suffixes the name (`act-runner-config-<hash>`) and rewrites the Deployment's volume reference — so an edit changes the **pod spec** and ArgoCD rolls it automatically. The config itself now lives at `manifests/files/config.yaml`; do not convert it back to a literal ConfigMap manifest.

That requires `prune: true` on the Application (each edit orphans the previous ConfigMap, else permanent OutOfSync). Unlike homepage — the repo's other `prune: true` app, which holds only a Deployment/Service/ConfigMaps — this app owns exactly what the repo-wide `prune: false` rule protects, so both opt out individually with `argocd.argoproj.io/sync-options: Prune=false`:

- `act-runner-data` PVC — the runner's registration identity (`/data/.runner`)
- the registration-token ExternalSecret

Guarded by `test_config_edit_rolls_the_pod` and `test_prune_is_enabled_but_stateful_resources_opt_out`.

## Re-triggering mirror CI with an empty commit is PATH-FILTER-BLIND

The quick way to re-run a mirror's CI is to push an empty commit (same tree, new sha) to the PR branch. That works only where the workflow's `push:` trigger has no `paths:` filter — an empty commit changes **zero files**, so every paths-filtered workflow correctly matches nothing and no Gitea run is created at all.

The failure mode is misleading: the branch syncs to Gitea fine, the sha is correct, the runner is healthy, and there are simply **no runs and no `gitea-actions/*` statuses** — which reads exactly like a broken mirror or a dead webhook. Chased on 2026-07-23 against `cnc-fr#94` before spotting that all three of its push workflows (`acceptance-report`, `compose-smoke`, `parity`) are paths-filtered; `cnc-fru`/`cnc-frd`/`second-brain` are not, which is why only `cnc-fr` looked broken.

Check before diagnosing anything else:

```bash
gh api repos/agentic-stoa/<repo>/commits/<sha> --jq '.files|length'   # 0 = empty commit
gh api repos/agentic-stoa/<repo>/contents/.github/workflows/<wf>.yml?ref=<branch> \
  --jq .content | base64 -d | awk '/^on:/{f=1} f{print} /^jobs:/{exit}'
```

To actually exercise a paths-filtered workflow, touch a path it matches — or merge the PR, since `main` is normally in the branch filter and the merge commit carries the real diff.

## The shared DinD daemon has no per-job isolation — two failure modes

GitHub-hosted runners give every job a **fresh VM**: an empty tool cache, an empty Docker daemon, free port and name space. Frank's `act_runner` gives every job a **container against one long-lived shared DinD daemon**. Workflows written for the former quietly depend on that freshness, and two distinct failures fall out. Both were diagnosed on cnc-frd on 2026-07-23, and both are reproducible.

### 1. Concurrent identical tool installs race the SHARED tool cache

`actions/setup-go@v6` can fail having apparently succeeded:

```
Successfully cached go to /opt/hostedtoolcache/go/1.25.7/x64
Added go to the path
Successfully set up Go version 1.25.7
/bin/sh: 1: version: not found
::error::Command failed:  version
  ❌  Failure - Main actions/setup-go@v6
```

The doubled space is the tell: the executable resolved to `''`, so act ran `sh -c " version"`. setup-go resolved, downloaded, extracted and cached Go correctly, then failed at its very last act — resolving `go` from PATH.

act mounts `/opt/hostedtoolcache` as a **volume shared by all concurrent jobs**. With `capacity: 2`, `test` (task 301) and `lint` (task 302) started five seconds apart and both installed the *same* Go 1.25.7 into that shared path. One won; the other got an unusable tree.

**It is not intermittent — it is deterministic on cold cache + concurrency**, which is exactly why it looks random. Proven by re-running with the cache warm and the same 5-second concurrency: `lint` went `failure` → **`success` in 1m26s**, no other change. Expect it to return on any tool-version bump (the first run after it is cold again); a re-run clears it because the cache is then warm.

Ruled out along the way: @v6 actions in general (`setup-node@v6`, `setup-python@v5` pass), the DinD/`network: host` work, file-derived version resolution (`test` uses the identical `go-version-file` and passed), and action fetching.

### 2. Fixed-name Docker resources leak between jobs and collide

```
Error response from daemon: network with name smoke already exists
  ❌  Failure - Main serve + healthz
```

Workflows create fixed-name resources (`docker network create smoke`, `--name pg`, `--name cncd`). On a fresh VM those names are always free. Here the daemon persists across jobs **and across repos** — cnc-fr, cnc-fru and cnc-frd all use the name `smoke` — and a job that fails skips its cleanup, so orphans accumulate.

cnc-frd's `image-smoke` removes `cncd` but never `pg` or the network, so **it can only succeed once**: the run after a success collides. Observed exactly that (`success 1m58s` → `failure 39s`), with a leftover `smoke` network and a `pg` container up 41 minutes still on the daemon.

Note this is not caused by the `network: host` change — before that fix the job died at `docker build` in 5s and never got far enough to create anything.

Inspect and clear orphans (only when no job is running):

```bash
kubectl -n gitea-runner exec deploy/act-runner -c dind -- docker ps -a --format '{{.Names}}\t{{.Status}}'
kubectl -n gitea-runner exec deploy/act-runner -c dind -- docker network ls
# safe only if `docker ps` shows no GITEA-ACTIONS-* container:
kubectl -n gitea-runner exec deploy/act-runner -c dind -- sh -c 'docker rm -f pg; docker network rm smoke'
```

`/var/lib/docker` is an emptyDir, so a runner pod restart also clears everything.

**Durable remedies** (neither applied yet): workflow-side, use run-scoped names (`smoke-${{ github.run_id }}`) and clean up with `if: always()`; runner-side, prune orphans between jobs. `capacity: 1` would serialise both failure modes away at the cost of halving throughput.

## Gitea Actions runner: registration is one-shot PVC state

`act_runner` registers against Gitea once and persists its identity in `/data/.runner` on the PVC. Rotating `STOA_GITEA_RUNNER_TOKEN` (or re-minting the registration token) does **NOT** re-register an already-registered runner — the token is only read when `/data/.runner` is absent. To force a fresh registration: scale the Deployment to 0, delete `/data/.runner` (or the whole PVC — the tool cache is rebuildable), scale back up. Symptom of a half-dead registration: runner pod healthy but the Gitea admin runners page shows it Offline.
