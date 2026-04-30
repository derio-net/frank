# vk-local OOMKill Remediation — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-04-30--agents--vk-local-oom-remediation-design.md`
**Status:** Not Started

**Type:** Fix/extension of the `agents` layer (extends [`2026-04-15--agents--agent-images-and-vk-local-sidecar`](../archived-plans/2026-04-15--agents--agent-images-and-vk-local-sidecar.md)). Per `repo-workflows.md`: same layer code, retroactively update existing layer's blog posts (no new posts).

**Goal:** Stop `vk-local` from OOMKilling under normal usage and put the cluster in a position to ratchet the memory limit back down once configurable safeguards land. Specifically: verify the already-shipped 8 Gi limit bump (PR #142), restore the cadvisor metric pipeline for 5 affected nodes, ship npm-cache + worktree-prune housekeeping in agent-images, add a `max_concurrent_executions` cap to the vibe-kanban fork, and file B2/B3/regression as tracking issues.

**Why now:** 27 OOMKills in 18 h on 2026-04-28 made the 2 Gi limit untenable. PR #142 unblocked the operator at 8 Gi but did not address the underlying working-set issues (unbounded concurrency, retained npm cache, residual worktree heap). Without continuous cadvisor metrics on `gpu-1`, there is no way to validate when it is safe to dial the limit back down.

**Cross-repo coordination:**
- Phases 1, 2, 4 (Frank-side surface), 5, 6 land in this repo.
- Phase 3 (housekeeping cron) and Phase 4's binary work land in [`derio-net/agent-images`](https://github.com/derio-net/agent-images). Each must produce a new GHCR image SHA before this plan's image-bumper PR picks it up.
- Phase 4's frank-side env var must wait for the agent-images binary that reads `VK_MAX_CONCURRENT_EXECUTIONS`.

---

## Phase 1: Verify Option A in production [agentic]
**Depends on:** —

PR [#142](https://github.com/derio-net/frank/pull/142) raised the limit from 2 Gi to 8 Gi. This phase confirms the live deployment carries the new value, captures a baseline restart count, and starts the 30-day no-OOMKill clock that the success criterion depends on.

### Task 1: Confirm live limit and zero post-bump OOMKills

- [ ] **Step 1: Verify live container spec**

```bash
kubectl -n secure-agent-pod get pod -l app=secure-agent-pod \
  -o jsonpath='{.items[0].spec.containers[?(@.name=="vk-local")].resources.limits.memory}'
# expect: 8Gi
```

- [ ] **Step 2: Read restart count and last-termination reason**

```bash
kubectl -n secure-agent-pod get pod -l app=secure-agent-pod \
  -o jsonpath='{range .items[0].status.containerStatuses[?(@.name=="vk-local")]}restartCount={.restartCount}{"\n"}lastReason={.lastState.terminated.reason}{"\n"}{end}'
```

  Expectation: `restartCount` is whatever it was at PR #142 merge time and has not advanced since. `lastReason` should not be `OOMKilled` for any termination after PR #142's merge timestamp (`d9bc2ea` parent).

- [ ] **Step 3: Inspect kubelet events for OOM since merge**

```bash
kubectl -n secure-agent-pod get events --sort-by=.lastTimestamp \
  | grep -i 'oom\|killed' || echo "no OOM events found"
```

- [ ] **Step 4: Capture pre-cadvisor RSS baseline**

```bash
kubectl -n secure-agent-pod top pod -l app=secure-agent-pod --containers
# record the vk-local row in the plan as the Phase 1 baseline reading
```

  Append the reading to this plan as a Deployment Notes row dated today.

### Task 2: Document the verification

- [ ] **Step 1:** Add an entry to the `Verification Log (Phase 1)` section at the bottom of this plan with: timestamp, live limit value, current restart count, OOM events found (or none), and the `kubectl top` reading. This becomes the input to Phase 5's soak comparison.

---

## Phase 2: Fix cadvisor metric pipeline for 5 nodes [agentic]
**Depends on:** Phase 1

The cadvisor `VMNodeScrape` reports all 7 nodes' targets healthy in vmagent, but `container_memory_working_set_bytes` series only persist for `raspi-1` and `raspi-2`. `count(scrape_samples_scraped{metrics_path="/metrics/cadvisor"}) by (node)` confirms the gap: 5 nodes (`mini-1`, `mini-2`, `mini-3`, `gpu-1`, `pc-1`) emit no samples through to vmsingle. Without this fix, Phase 5 cannot quantify the effect of housekeeping or B1.

### Task 1: Investigate root cause

- [ ] **Step 1: Read vmagent scrape stats for cadvisor targets**

```bash
VMAGENT=$(kubectl -n monitoring get pod -l app.kubernetes.io/name=vmagent -o jsonpath='{.items[0].metadata.name}')
kubectl -n monitoring exec deploy/vmsingle-victoria-metrics-victoria-metrics-k8s-stack -- \
  wget -qO- "http://vmagent-victoria-metrics-victoria-metrics-k8s-stack:8429/api/v1/targets?state=active" \
  | python3 -c "
import json, sys
d=json.load(sys.stdin)['data']['activeTargets']
for t in (x for x in d if x.get('labels',{}).get('metrics_path')=='/metrics/cadvisor'):
    print(t['labels'].get('instance'), 'samples=', t.get('lastSamplesScraped'), 'ms=', t.get('lastScrapeDuration'))"
```

  Note the per-node `lastSamplesScraped`. If amd64 nodes return non-zero here but vmsingle has no series for them, the loss is in the relabel/ingestion pipeline (case 1 below). If they return zero here, cadvisor itself is silent on those nodes (case 2).

- [ ] **Step 2: Test the relabel-rule hypothesis (case 1)**

  The `VMNodeScrape` for cadvisor includes:

```yaml
metricRelabelConfigs:
- action: labeldrop
  regex: (uid)
- action: labeldrop
  regex: (id|name)
```

  The second rule drops any label matching `id` or `name`. Some cadvisor metric variants legacy-mirror their identifiers in those exact label names. Test by temporarily commenting out the second rule on a non-prod scrape (or via a dedicated test `VMNodeScrape` selecting only `gpu-1`) and re-querying for amd64 series after one scrape interval.

- [ ] **Step 3: Test cardinality / disk-usage limits (case 2)**

```bash
kubectl -n monitoring logs deploy/vmagent-victoria-metrics-victoria-metrics-k8s-stack -c vmagent \
  | grep -iE 'limit|drop|reject|cardinality' | tail -50
```

  Look for messages mentioning `gpu-1` / `mini-1` / `pc-1` instances, dropped samples, or per-target rate limits.

- [ ] **Step 4: Test cadvisor endpoint directly on an affected node**

```bash
kubectl -n monitoring run cadvisor-test-$$ --rm -i --restart=Never \
  --image=curlimages/curl:8.4.0 \
  --overrides='{"spec":{"nodeSelector":{"kubernetes.io/hostname":"gpu-1"}}}' \
  -- curl -sk -H "Authorization: Bearer $(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
  https://gpu-1:10250/metrics/cadvisor | grep -c '^container_memory_working_set_bytes' \
  || echo "scrape returned no samples or auth failed"
```

  Compare to the same probe against `raspi-1`. Confirms whether the kubelet itself emits the series.

### Task 2: Apply the fix

Pick exactly one of the three sub-steps below depending on which case Task 1 confirmed; then run the verify and Grafana steps.

- [ ] **Step 1: Apply the case-specific fix.** One of:
  - **Case 1 (relabel rule):** Edit `apps/victoria-metrics/values.yaml` to override the cadvisor `VMNodeScrape` `metricRelabelConfigs`, removing the `(id|name)` labeldrop. Commit, ArgoCD syncs, wait one scrape interval (30 s), re-query.
  - **Case 2 (vmagent limit):** Edit `apps/victoria-metrics/values.yaml` to bump the relevant `vmagent.spec.extraArgs` flag (`promscrape.maxScrapeSize`, `remoteWrite.maxBlockSize`, etc., depending on the log message). Commit, ArgoCD sync, observe vmagent logs for resumed ingest.
  - **Case 3 (vmsingle limit):** Bump retention or per-tenant series limit in `vmsingle.spec` in the same values file. Commit, ArgoCD sync.

- [ ] **Step 2: Verify.** Wait 5 minutes, then run:

```bash
kubectl -n monitoring exec vmagent-victoria-metrics-victoria-metrics-k8s-stack-* -c vmagent -- \
  wget -qO- 'http://vmsingle-victoria-metrics-victoria-metrics-k8s-stack:8428/api/v1/query?query=count(container_memory_working_set_bytes)by(node)'
```

  All 7 nodes must appear with non-zero counts.

- [ ] **Step 3 (Grafana panel):** Add a `vk-local working-set RSS` panel to the existing operating dashboard. Query: `container_memory_working_set_bytes{namespace="secure-agent-pod", container="vk-local"}`. Pin to the secure-agent-pod operating folder so Phase 5's soak readings have a UI.

### Task 3: 24h soak

- [ ] **Step 1:** After 24 h, re-query the count. Series count must be non-zero for all 7 nodes continuously. Document the result in this plan's Deployment Notes section.

### Task 4: Fallback if root cause cannot be isolated

- [ ] **Step 1:** If after one working day the cause is still unknown, file a tracking issue in `derio-net/frank` titled `obs: cadvisor scrape data gap on amd64 nodes` with the investigation log so far. Mark Phase 2 as `Closed (deferred)` in this plan and continue with Phase 3 — the housekeeping work does not depend on Phase 2's outcome, only Phase 5's evaluation does.

---

## Phase 3: Housekeeping — npm cache + worktree prune [agentic]
**Depends on:** —

*(Can land in parallel with Phase 2.)*

This phase is a pure agent-images change. It targets the ~900 MiB retained npm file-cache and the ~17 MiB/worktree heap residue identified in the memprofile findings. After landing, saturated-idle for `vk-local` should drop from ~1,157 MiB toward ~220 MiB.

### Task 1: Decide cron host

- [ ] **Step 1:** Inspect `kali`'s supercronic crontab and the PVC mount layout. The default placement is `kali`'s supercronic crontab, since it already runs scheduled work and shares the agent-home PVC with `vk-local`. Confirm by reading the kali Dockerfile / `crontab` content in agent-images.

  If supercronic is unavailable in `kali` for any reason, fall back to a Kubernetes `CronJob` in `apps/secure-agent-pod/manifests/cronjob-housekeeping.yaml` mounting the same PVC.

### Task 2: Implement the crons (agent-images repo)

This work happens in [`derio-net/agent-images`](https://github.com/derio-net/agent-images), not this repo. Open a PR there with the following two cron entries.

- [ ] **Step 1: npm cache prune cron**

  Weekly (`0 4 * * 0` — Sunday 04:00 UTC). Command:

```sh
# Remove tarballs older than 7 days. `npm cache verify` reaps stale entries
# and reports size. Do not blow away the entire cache; that would re-pay
# download cost on every active session.
find /home/claude/.npm/_cacache -type f -atime +7 -delete 2>/dev/null
HOME=/home/claude npm cache verify >/var/log/agent/npm-cache-verify.log 2>&1
```

- [ ] **Step 2: Worktree prune cron**

  Daily (`30 4 * * *` — 04:30 UTC). Command:

```sh
# vibe-kanban creates worktrees under ~/vibe-kanban/worktrees/. Each tracked
# repo (project_dir under the workspace) has its own worktree set. Prune
# administrative metadata for already-deleted worktrees.
for repo in $(find /home/claude/vibe-kanban/repos -maxdepth 2 -type d -name '.git' -prune); do
  git --git-dir="$repo" worktree prune -v
done >/var/log/agent/worktree-prune.log 2>&1
```

> **Note:** The exact path `~/vibe-kanban/repos` is a placeholder — confirm the actual workspace root from vibe-kanban's config before merging. The path is whatever `--workspace-root` resolves to at runtime; `find` falls through gracefully if it doesn't exist.

- [ ] **Step 3: Open PR in agent-images** with both cron entries plus a brief reference back to this plan and to [`agent-images:kali/docs/findings/2026-04-22-vk-local-memory-profile.md`](https://github.com/derio-net/agent-images/blob/main/kali/docs/findings/2026-04-22-vk-local-memory-profile.md).

### Task 3: Image-bumper picks up the new SHA

- [ ] **Step 1:** Once Task 2's PR merges in agent-images, the existing image-bumper workflow opens a PR in this repo updating the image SHA in `apps/secure-agent-pod/manifests/deployment.yaml`. Merge that PR. ArgoCD syncs. The kali container restarts; supercronic loads the new crontab automatically (no extra restart needed — supercronic auto-reloads on file change, see `frank-gotchas.md`).

### Task 4: Verify housekeeping is running

- [ ] **Step 1:** After the first weekly window passes (or trigger manually inside the pod for verification: `kubectl -n secure-agent-pod exec -c kali deploy/secure-agent-pod -- supercronic -test /home/claude/.crontab`), inspect the log files:

```bash
kubectl -n secure-agent-pod exec -c kali deploy/secure-agent-pod -- \
  ls -la /var/log/agent/npm-cache-verify.log /var/log/agent/worktree-prune.log
```

- [ ] **Step 2 (verify metric — depends on Phase 2):** Once Phase 2 is complete, query

```promql
container_memory_working_set_bytes{namespace="secure-agent-pod", container="vk-local"} / 1024 / 1024
```

  in Grafana. Median should trend down toward 200–300 MiB once a session-idle period rolls over the prune cron.

---

## Phase 4: Option B1 — `max_concurrent_executions` cap [agentic]
**Depends on:** Phase 3

Adds a configurable concurrency cap to vibe-kanban (queue, not reject), surfaces it as a Frank env var, and adds a minimal `/metrics` endpoint so the cap is observable in cadvisor + a vmagent scrape.

> **Note on dependency:** Strictly the binary work in Task 1 is independent of Phase 3 — they could land in either order in agent-images. Listed here as Phase 3 → Phase 4 because the housekeeping change is faster to implement and review, and validating its effect is cleaner before adding a second variable.

### Task 1: Add the cap to the vibe-kanban fork (agent-images repo)

This work happens in [`derio-net/agent-images`](https://github.com/derio-net/agent-images). The PR there should reference this plan.

- [ ] **Step 1: Bump config schema v8 → v9**

  Add `max_concurrent_executions: Option<usize>` to the binary's config struct. Default: `None` (current unbounded behavior — backwards-compatible for non-Frank users of the fork). Run the existing migration test suite to confirm v8 configs load cleanly on v9.

- [ ] **Step 2: Add env-var fallback**

  At process startup, after config load, if `VK_MAX_CONCURRENT_EXECUTIONS` is set in the environment, parse and use it (overriding any config-file value). This avoids needing a config-file mount on Frank.

- [ ] **Step 3: Wrap executor spawn in a counting semaphore**

  In the executor's spawn path (whatever module hosts the `claude` / `npm` / `node` fork logic — locate via `grep -rn 'tokio::process\|Command::new' src/`), acquire a permit from a `tokio::sync::Semaphore` sized to the cap. Permits are released on child exit. When all permits are taken, the next spawn awaits in the queue — do not error.

- [ ] **Step 4: Add structured queue logs**

  On every spawn that has to wait, emit a structured log line:

```json
{"event":"execution_queued","waiting":N,"max":M,"task_id":"..."}
```

  This is the cap's primary observability surface until Step 5 ships.

- [ ] **Step 5: Add `/metrics` endpoint**

  Expose three Prometheus gauges on the existing 8081 listener:
  - `vibekanban_active_executions`
  - `vibekanban_queued_executions`
  - `vibekanban_max_executions`

  Path: `/metrics`. Use the existing axum/hyper router (whichever vibe-kanban already uses). No labels yet.

- [ ] **Step 6: Open PR in agent-images.** Tests must cover: missing field / `null` (treated as `None`, no cap, current behavior), `cap=1` (serialization round-trip), and `cap=N` with N+1 concurrent spawns (queueing — the (N+1)th must wait until one permit is released, not error). `cap=0` should be rejected at config-load with a clear error (degenerate "never spawn anything"). Reviewer should verify the v8→v9 migration works on a recorded v8 config.

### Task 2: Surface the env var on Frank

> **Depends on:** Task 1 PR merged in agent-images, image-bumper PR merged in this repo.

- [ ] **Step 1: Edit `apps/secure-agent-pod/manifests/deployment.yaml`**

  In the `vk-local` container's `env:` block, add:

```yaml
- name: VK_MAX_CONCURRENT_EXECUTIONS
  value: "4"
```

  Cap rationale (per spec): saturated-idle ~220 MiB + 4 × 480 MiB = ~2,140 MiB worst-case live cgroup. Fits in 3 Gi with margin; the unchanged 8 Gi limit becomes a deep safety net.

- [ ] **Step 2: Add a `VMPodScrape` for the new endpoint**

  Create `apps/secure-agent-pod/manifests/vmpodscrape.yaml`:

```yaml
apiVersion: operator.victoriametrics.com/v1beta1
kind: VMPodScrape
metadata:
  name: vk-local
  namespace: secure-agent-pod
spec:
  selector:
    matchLabels:
      app: secure-agent-pod
  podMetricsEndpoints:
    - port: vk-http
      path: /metrics
      interval: 30s
```

  Verify the port name `vk-http` matches the Deployment's container port. Commit. ArgoCD syncs.

- [ ] **Step 3: Verify metrics arrive**

```bash
kubectl -n monitoring exec vmagent-victoria-metrics-victoria-metrics-k8s-stack-* -c vmagent -- \
  wget -qO- 'http://vmsingle-victoria-metrics-victoria-metrics-k8s-stack:8428/api/v1/query?query=vibekanban_max_executions'
```

  Expect a single result with value `4`. If empty, debug the VMPodScrape selector / port-name match.

- [ ] **Step 4: Add a Grafana panel for queue depth**

  Add to the secure-agent-pod operating dashboard: a stat panel `vibekanban_queued_executions` and a time-series of `vibekanban_active_executions` vs `vibekanban_max_executions`.

---

## Phase 5: Soak + dial-back assessment [manual]
**Depends on:** Phase 1, Phase 2, Phase 3, Phase 4

Run a **14-day soak** under normal operator workload. Then make a sized decision about the 8 Gi limit.

### Task 1: Collect soak data

- [ ] **Step 1: Daily checks**

  For 14 days from Phase 4 Task 2 merge:

```bash
# Restart count (must remain at the Phase 1 baseline)
kubectl -n secure-agent-pod get pod -l app=secure-agent-pod \
  -o jsonpath='{.items[0].status.containerStatuses[?(@.name=="vk-local")].restartCount}'

# Daily p99 working-set
# (run in Grafana — or curl vmsingle from inside-cluster)
quantile_over_time(0.99, container_memory_working_set_bytes{namespace="secure-agent-pod", container="vk-local"}[1d])

# Queue depth peak
max_over_time(vibekanban_queued_executions[1d])
```

- [ ] **Step 2: Record findings**

  Append a `## Phase 5 Soak Log` section at the bottom of this plan, one row per day.

### Task 2: Decision and follow-up PR

- [ ] **Step 1:** After 14 days, choose one outcome and document the rationale:

  - **(a) Keep 8 Gi.** Document p99 RSS + max queue depth in the plan. No code change.
  - **(b) Dial back to 3 Gi.** Open a PR editing `apps/secure-agent-pod/manifests/deployment.yaml` from `8Gi` to `3Gi`. Cite Phase 5 p99 as evidence.
  - **(c) Raise the cap.** Open a PR editing the env var value (e.g., 4 → 6). Cite sustained queue depth as evidence.

  Outcome (a), (b), or (c) is permitted; the success criterion is not "the limit must shrink", it is "we know which choice the data supports."

---

## Phase 6: File tracking issues for B2, B3, R [agentic]
**Depends on:** —

*(Can run any time after Phase 4 Task 1 PR is filed.)*

Three follow-up items deferred from this plan. Filed as GitHub issues so they appear on the Derio Ops board with explicit gating criteria. No implementation here.

### Task 1: File B2 tracking issue

- [x] **Step 1:** Open issue in `derio-net/frank` titled `agents: B2 — delegate vk-local child spawn to kali sibling cgroup`.

  Body: short summary of the architecture (sibling-container exec relay), the trigger conditions (B1 + housekeeping insufficient: cap=4 still drives ≥2 OOMKills/month, *or* explicit per-session OS-isolation requirement appears), and a link to this plan + the memprofile findings. Label `architecture`, `parked`.

  **Filed:** [#160](https://github.com/derio-net/frank/issues/160).

### Task 2: File B3 tracking issue

- [x] **Step 1:** Open issue in `derio-net/frank` titled `agents: B3 — per-task Kubernetes Jobs for vibe-kanban executions`.

  Body: per-task pod isolation, suitable when sustained concurrency reaches ≥10 sessions or per-task GPU/network policy is needed. Trigger: B1 cap pushed to 8 and queue p99 > 1 sustained for 7 days. Link to this plan. Label `architecture`, `parked`.

  **Filed:** [#161](https://github.com/derio-net/frank/issues/161).

### Task 3: File the R (regression cross-check) tracking issue

- [x] **Step 1:** Open issue in `derio-net/frank` titled `agents: investigate 9× OOM-rate escalation on vibe-kanban image dc414b4`.

  Body: cite the memprofile findings — Phase 1 image (`d3bbcd70…`) showed 6 kills/48h; Phase 2 retake on `dc414b4` showed 20 kills/17.4h with similar workload. Possible causes: workload variance, vibe-kanban regression, or measurement-window effect. Action: re-run the Phase 2 synthetic workload against both binaries with the Phase 2 cadvisor pipeline in place. Link to this plan + agent-images PR #21. Label `obs`, `agents`.

  **Filed:** [#162](https://github.com/derio-net/frank/issues/162).

---

## Phase 7: Post-Deploy Checklist [manual]
**Depends on:** Phase 1, Phase 2, Phase 3, Phase 4, Phase 5, Phase 6

This is a fix/extension plan (per the Type at top), so most post-deploy steps are skipped per `repo-workflows.md`.

- [-] **Step 1: Expose externally** — *(skipped — internal change, no new public surface)*
- [-] **Step 2: Write building blog post** — *(skipped — fix/extension; update existing layer post instead)*
- [-] **Step 3: Write operating blog post** — *(skipped — same)*
- [ ] **Step 4: Update existing layer's blog posts** — Add a "Memory remediation" subsection to the existing `2026-04-15--agents--agent-images-and-vk-local-sidecar` building post (root cause + housekeeping + B1 cap). Add operational commands (how to read queue depth, how to flip the cap) to the operating post.
- [ ] **Step 5: Update gotchas** — Add to `.claude/rules/frank-gotchas.md`: "vibe-kanban v9 introduces `VK_MAX_CONCURRENT_EXECUTIONS`. The vk-local cgroup limit is sized to the cap — do not raise the cap without re-evaluating the limit. See `2026-04-30--agents--vk-local-oom-remediation`." Plus the cadvisor-gap finding if Phase 2 produced a generalizable rule.
- [ ] **Step 6: Update README** — Run `/update-readme` to sync the agents section.
- [ ] **Step 7: Sync runbook** — Run `/sync-runbook` if any `# manual-operation` blocks were added to this plan during execution.
- [ ] **Step 8: Update plan status** — Set `**Status:**` to `Deployed` once Phase 5 outcome is documented and Phase 6 issues are filed.

---

## Deployment Deviations

*(Append findings here as phases execute.)*

## Verification Log (Phase 1)

*(Filled in by Phase 1 Task 2.)*

## Soak Log (Phase 5)

*(Filled in by Phase 5 Task 1.)*
