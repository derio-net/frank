# vk-local OOMKill Remediation — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-04-30--agents--vk-local-oom-remediation-design.md`
**Status:** In Progress

**Type:** Fix/extension of the `agents` layer (extends [`2026-04-15--agents--agent-images-and-vk-local-sidecar`](../archived-plans/2026-04-15--agents--agent-images-and-vk-local-sidecar.md)). Per `repo-workflows.md`: same layer code, retroactively update existing layer's blog posts (no new posts).

**Goal:** Stop `vk-local` from OOMKilling under normal usage and put the cluster in a position to ratchet the memory limit back down once configurable safeguards land. Specifically: verify the already-shipped 8 Gi limit bump (PR #142), restore the cadvisor metric pipeline for 5 affected nodes, ship npm-cache + worktree-prune housekeeping in agent-images, add a `max_concurrent_executions` cap to the vibe-kanban fork, and file B2/B3/regression as tracking issues.

**Why now:** 27 OOMKills in 18 h on 2026-04-28 made the 2 Gi limit untenable. PR #142 unblocked the operator at 8 Gi but did not address the underlying working-set issues (unbounded concurrency, retained npm cache, residual worktree heap). Without continuous cadvisor metrics on `gpu-1`, there is no way to validate when it is safe to dial the limit back down.

**Cross-repo coordination:**
- Phases 1, 2, 4 (Frank-side surface), 5, 6 land in this repo.
- Phase 3 (housekeeping cron) and Phase 4's binary work land in [`derio-net/agent-images`](https://github.com/derio-net/agent-images). Each must produce a new GHCR image SHA before this plan's image-bumper PR picks it up.
- Phase 4's frank-side env var must wait for the agent-images binary that reads `VK_MAX_CONCURRENT_EXECUTIONS`.

---

## Phase 1: Verify Option A in production [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/152 -->
**Depends on:** —

PR [#142](https://github.com/derio-net/frank/pull/142) raised the limit from 2 Gi to 8 Gi. This phase confirms the live deployment carries the new value, captures a baseline restart count, and starts the 30-day no-OOMKill clock that the success criterion depends on.

### Task 1: Confirm live limit and zero post-bump OOMKills

- [x] **Step 1: Verify live container spec**

```bash
kubectl -n secure-agent-pod get pod -l app=secure-agent-pod \
  -o jsonpath='{.items[0].spec.containers[?(@.name=="vk-local")].resources.limits.memory}'
# expect: 8Gi
```

- [x] **Step 2: Read restart count and last-termination reason**

```bash
kubectl -n secure-agent-pod get pod -l app=secure-agent-pod \
  -o jsonpath='{range .items[0].status.containerStatuses[?(@.name=="vk-local")]}restartCount={.restartCount}{"\n"}lastReason={.lastState.terminated.reason}{"\n"}{end}'
```

  Expectation: `restartCount` is whatever it was at PR #142 merge time and has not advanced since. `lastReason` should not be `OOMKilled` for any termination after PR #142's merge timestamp (`d9bc2ea` parent).

- [x] **Step 3: Inspect kubelet events for OOM since merge**

```bash
kubectl -n secure-agent-pod get events --sort-by=.lastTimestamp \
  | grep -i 'oom\|killed' || echo "no OOM events found"
```

- [x] **Step 4: Capture pre-cadvisor RSS baseline**

  `kubectl top` is unavailable (the metrics-server / cadvisor pipeline gap is what Phase 2 addresses). Fallback: read `/sys/fs/cgroup/memory.current` and `memory.stat` directly from the vk-local cgroup. See the Verification Log entry below.

### Task 2: Document the verification

- [x] **Step 1:** Add an entry to the `Verification Log (Phase 1)` section at the bottom of this plan with: timestamp, live limit value, current restart count, OOM events found (or none), and the `kubectl top` reading. This becomes the input to Phase 5's soak comparison.

---

## Phase 2: Fix cadvisor metric pipeline for 5 nodes [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/153 -->
**Depends on:** Phase 1

The cadvisor `VMNodeScrape` reports all 7 nodes' targets healthy in vmagent, but `container_memory_working_set_bytes` series only persist for `raspi-1` and `raspi-2`. `count(scrape_samples_scraped{metrics_path="/metrics/cadvisor"}) by (node)` confirms the gap: 5 nodes (`mini-1`, `mini-2`, `mini-3`, `gpu-1`, `pc-1`) emit no samples through to vmsingle. Without this fix, Phase 5 cannot quantify the effect of housekeeping or B1.

### Task 1: Investigate root cause

- [x] **Step 1: Read vmagent scrape stats for cadvisor targets**

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

- [x] **Step 2: Test the relabel-rule hypothesis (case 1)**

  The `VMNodeScrape` for cadvisor includes:

```yaml
metricRelabelConfigs:
- action: labeldrop
  regex: (uid)
- action: labeldrop
  regex: (id|name)
```

  The second rule drops any label matching `id` or `name`. Some cadvisor metric variants legacy-mirror their identifiers in those exact label names. Test by temporarily commenting out the second rule on a non-prod scrape (or via a dedicated test `VMNodeScrape` selecting only `gpu-1`) and re-querying for amd64 series after one scrape interval.

- [x] **Step 3: Test cardinality / disk-usage limits (case 2)**

```bash
kubectl -n monitoring logs deploy/vmagent-victoria-metrics-victoria-metrics-k8s-stack -c vmagent \
  | grep -iE 'limit|drop|reject|cardinality' | tail -50
```

  Look for messages mentioning `gpu-1` / `mini-1` / `pc-1` instances, dropped samples, or per-target rate limits.

- [x] **Step 4: Test cadvisor endpoint directly on an affected node**

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

- [x] **Step 1: Apply the case-specific fix.** One of:
  - **Case 1 (relabel rule):** Edit `apps/victoria-metrics/values.yaml` to override the cadvisor `VMNodeScrape` `metricRelabelConfigs`, removing the `(id|name)` labeldrop. Commit, ArgoCD syncs, wait one scrape interval (30 s), re-query.
  - **Case 2 (vmagent limit):** Edit `apps/victoria-metrics/values.yaml` to bump the relevant `vmagent.spec.extraArgs` flag (`promscrape.maxScrapeSize`, `remoteWrite.maxBlockSize`, etc., depending on the log message). Commit, ArgoCD sync, observe vmagent logs for resumed ingest.
  - **Case 3 (vmsingle limit):** Bump retention or per-tenant series limit in `vmsingle.spec` in the same values file. Commit, ArgoCD sync.

- [ ] **Step 2: Verify.** Wait 5 minutes, then run:

```bash
kubectl -n monitoring exec vmagent-victoria-metrics-victoria-metrics-k8s-stack-* -c vmagent -- \
  wget -qO- 'http://vmsingle-victoria-metrics-victoria-metrics-k8s-stack:8428/api/v1/query?query=count(container_memory_working_set_bytes)by(node)'
```

  All 7 nodes must appear with non-zero counts.

- [x] **Step 3 (Grafana panel):** Add a `vk-local working-set RSS` panel to the existing operating dashboard. Query: `container_memory_working_set_bytes{namespace="secure-agent-pod", container="vk-local"}`. Pin to the secure-agent-pod operating folder so Phase 5's soak readings have a UI.

### Task 3: 24h soak

- [ ] **Step 1:** After 24 h, re-query the count. Series count must be non-zero for all 7 nodes continuously. Document the result in this plan's Deployment Notes section.

### Task 4: Fallback if root cause cannot be isolated

- [-] **Step 1:** *(skipped — root cause was isolated in Task 1, see Deployment Deviations below).* If after one working day the cause is still unknown, file a tracking issue in `derio-net/frank` titled `obs: cadvisor scrape data gap on amd64 nodes` with the investigation log so far. Mark Phase 2 as `Closed (deferred)` in this plan and continue with Phase 3 — the housekeeping work does not depend on Phase 2's outcome, only Phase 5's evaluation does.

---

## Phase 3: Housekeeping — npm cache + worktree prune [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/154 -->
**Depends on:** —

*(Can land in parallel with Phase 2 — no blocking phase.)*

This phase is a pure agent-images change. It targets the ~900 MiB retained npm file-cache and the ~17 MiB/worktree heap residue identified in the memprofile findings. After landing, saturated-idle for `vk-local` should drop from ~1,157 MiB toward ~220 MiB.

### Task 1: Decide cron host

- [x] **Step 1:** Inspect `kali`'s supercronic crontab and the PVC mount layout. The default placement is `kali`'s supercronic crontab, since it already runs scheduled work and shares the agent-home PVC with `vk-local`. Confirm by reading the kali Dockerfile / `crontab` content in agent-images.

  *Confirmed:* `kali/config-templates/crontab.txt` is seeded to `$AGENT_HOME/.crontab` via `etc/cont-init.d/50-seed-config`, supercronic is supervised by s6 (`agent-shell-base/etc/services.d/supercronic/run`), and both containers share the `agent-home` PVC mounted at `/home/claude`. No CronJob fallback needed.

  If supercronic is unavailable in `kali` for any reason, fall back to a Kubernetes `CronJob` in `apps/secure-agent-pod/manifests/cronjob-housekeeping.yaml` mounting the same PVC.

### Task 2: Implement the crons (agent-images repo)

This work happens in [`derio-net/agent-images`](https://github.com/derio-net/agent-images), not this repo. Open a PR there with the following two cron entries.

- [x] **Step 1: npm cache prune cron** — shipped as [`kali/scripts/npm-cache-prune.sh`](https://github.com/derio-net/agent-images/blob/agents/vk-local-housekeeping-crons/kali/scripts/npm-cache-prune.sh). Crontab line: `0 4 * * 0 /opt/scripts/npm-cache-prune.sh >> __AGENT_HOME__/.willikins-agent/npm-cache-prune.log 2>&1`.

- [x] **Step 2: Worktree prune cron** — shipped as [`kali/scripts/worktree-prune.sh`](https://github.com/derio-net/agent-images/blob/agents/vk-local-housekeeping-crons/kali/scripts/worktree-prune.sh). Iterates `$AGENT_HOME/repos/*/.git` (the canonical repo root on Frank — vibe-kanban worktrees under `/var/tmp/vibe-kanban/worktrees/` link back via gitdir files). Crontab line: `30 4 * * * /opt/scripts/worktree-prune.sh >> __AGENT_HOME__/.willikins-agent/worktree-prune.log 2>&1`.

- [x] **Step 3: Open PR in agent-images** — [`derio-net/agent-images#34`](https://github.com/derio-net/agent-images/pull/34).

### Task 3: Image-bumper picks up the new SHA

- [ ] **Step 1:** Once Task 2's PR merges in agent-images, the existing image-bumper workflow opens a PR in this repo updating the image SHA in `apps/secure-agent-pod/manifests/deployment.yaml`. Merge that PR. ArgoCD syncs. The kali container restarts; supercronic loads the new crontab automatically (no extra restart needed — supercronic auto-reloads on file change, see `frank-gotchas.md`).

### Task 4: Verify housekeeping is running

- [ ] **Step 1:** After the first weekly window passes (or trigger manually inside the pod for verification: `kubectl -n secure-agent-pod exec -c kali deploy/secure-agent-pod -- supercronic -test /home/claude/.crontab`), inspect the log files:

```bash
kubectl -n secure-agent-pod exec -c kali deploy/secure-agent-pod -- \
  ls -la /home/claude/.willikins-agent/npm-cache-prune.log \
         /home/claude/.willikins-agent/worktree-prune.log
```

- [ ] **Step 2 (verify metric — depends on Phase 2):** Once Phase 2 is complete, query

```promql
container_memory_working_set_bytes{namespace="secure-agent-pod", container="vk-local"} / 1024 / 1024
```

  in Grafana. Median should trend down toward 200–300 MiB once a session-idle period rolls over the prune cron.

---

## Phase 4: Option B1 — `max_concurrent_executions` cap [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/155 -->
**Depends on:** Phase 3

*(Specifically: Phase 3's image-bumper PR must be merged before Phase 4 Task 2 picks up the new SHA. Strictly the Task 1 binary work in agent-images is independent — see note below.)*

Adds a configurable concurrency cap to vibe-kanban (queue, not reject), surfaces it as a Frank env var, and adds a minimal `/metrics` endpoint so the cap is observable in cadvisor + a vmagent scrape.

> **Note on dependency:** Strictly the binary work in Task 1 is independent of Phase 3 — they could land in either order in agent-images. Listed here as Phase 3 → Phase 4 because the housekeeping change is faster to implement and review, and validating its effect is cleaner before adding a second variable.

### Task 1: Add the cap to the vibe-kanban fork (agent-images repo)

This work happens in [`derio-net/agent-images`](https://github.com/derio-net/agent-images). The PR there should reference this plan.

- [x] **Step 1: Bump config schema v8 → v9**

  Add `max_concurrent_executions: Option<usize>` to the binary's config struct. Default: `None` (current unbounded behavior — backwards-compatible for non-Frank users of the fork). Run the existing migration test suite to confirm v8 configs load cleanly on v9.

- [x] **Step 2: Add env-var fallback**

  At process startup, after config load, if `VK_MAX_CONCURRENT_EXECUTIONS` is set in the environment, parse and use it (overriding any config-file value). This avoids needing a config-file mount on Frank.

- [x] **Step 3: Wrap executor spawn in a counting semaphore**

  In the executor's spawn path (whatever module hosts the `claude` / `npm` / `node` fork logic — locate via `grep -rn 'tokio::process\|Command::new' src/`), acquire a permit from a `tokio::sync::Semaphore` sized to the cap. Permits are released on child exit. When all permits are taken, the next spawn awaits in the queue — do not error.

- [x] **Step 4: Add structured queue logs**

  On every spawn that has to wait, emit a structured log line:

```json
{"event":"execution_queued","waiting":N,"max":M,"task_id":"..."}
```

  This is the cap's primary observability surface until Step 5 ships.

- [x] **Step 5: Add `/metrics` endpoint**

  Expose three Prometheus gauges on the existing 8081 listener:
  - `vibekanban_active_executions`
  - `vibekanban_queued_executions`
  - `vibekanban_max_executions`

  Path: `/metrics`. Use the existing axum/hyper router (whichever vibe-kanban already uses). No labels yet.

- [x] **Step 6: Open PR in agent-images.** Tests must cover: missing field / `null` (treated as `None`, no cap, current behavior), `cap=1` (serialization round-trip), and `cap=N` with N+1 concurrent spawns (queueing — the (N+1)th must wait until one permit is released, not error). `cap=0` should be rejected at config-load with a clear error (degenerate "never spawn anything"). Reviewer should verify the v8→v9 migration works on a recorded v8 config.

### Task 2: Surface the env var on Frank

> **Depends on:** Task 1 PR merged in agent-images, image-bumper PR merged in this repo.

- [x] **Step 1: Edit `apps/secure-agent-pod/manifests/deployment.yaml`**

  In the `vk-local` container's `env:` block, add:

```yaml
- name: VK_MAX_CONCURRENT_EXECUTIONS
  value: "4"
```

  Cap rationale (per spec): saturated-idle ~220 MiB + 4 × 480 MiB = ~2,140 MiB worst-case live cgroup. Fits in 3 Gi with margin; the unchanged 8 Gi limit becomes a deep safety net.

- [x] **Step 2: Add a `VMPodScrape` for the new endpoint**

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
<!-- Tracking: https://github.com/derio-net/frank/issues/156 -->
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
<!-- Tracking: https://github.com/derio-net/frank/issues/157 -->
**Depends on:** —

*(Can run any time after Phase 4 Task 1 PR is filed in agent-images.)*

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
<!-- Tracking: https://github.com/derio-net/frank/issues/158 -->
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

### Phase 2 — cadvisor gap root cause was *not* the `(id|name)` labeldrop (2026-05-02)

The plan's Case 1 hypothesis (the cadvisor `VMNodeScrape`'s `(id|name)` labeldrop dropping data on amd64) was wrong. Investigation showed:

- **Task 1 / Step 1** — vmagent reports all 7 cadvisor targets healthy with non-zero `lastSamplesScraped`. amd64 nodes scrape *more* samples than raspi (gpu-1=7575, mini-1=13658, raspi-1=3245). So the loss is downstream of vmagent's parser, not at the target.
- **Task 1 / Step 3** — vmsingle logs are full of `timeserieslimits/timeseries_limits.go:72 ignoring series with N labels for {…}; either reduce the number of labels for this metric or increase -maxLabelsPerTimeseries=40 cmd-line flag value`, where N is 60–135 for amd64 series (containing all NFD `feature_node_kubernetes_io_*`, Talos `extensions_talos_dev_*`, NVIDIA `nvidia_com_*`, and `beta_kubernetes_io_*` labels propagated by the chart's default `labelmap __meta_kubernetes_node_label_(.+)` rule). raspi series carry ~33 labels and pass under VictoriaMetrics' default `-maxLabelsPerTimeseries=40`, which is why only the 2 raspi nodes were ever visible.

This is not the canonical Case 1, 2, or 3 the plan enumerates — closest is Case 1 (a relabel-rule fix) but with a different rule than the plan suggested. **Fix applied:** added a 4th `metricRelabelConfigs` `labeldrop` rule under `kubelet.vmScrape.spec` in `apps/victoria-metrics/values.yaml` that strips `feature_node_kubernetes_io_.*|extensions_talos_dev_.*|nvidia_com_.*|beta_kubernetes_io_.*` before metrics are remoteWritten to vmsingle. The chart's default labelmap is preserved, so useful node labels (`tier`, `zone`, `kubernetes_io_arch`, `node`, `instance`, `accelerator`, `igpu`) still attach. The override applies to all four kubelet-derived scrapes (cadvisor, resources, probes, kubelet itself) since the chart's `kubelet.vmScrape.spec` is shared — intentional, the same root cause was visible for `/metrics/resource` series in vmsingle's drop logs.

For Phase 5 soak visibility, a new **Secure Agent Pod — Operating** Grafana dashboard was added (`apps/grafana-alerting/manifests/secure-agent-pod-dashboard-cm.yaml`, mounted via `apps/victoria-metrics/values.yaml`'s `extraConfigmapMounts`). It pins three panels in a new `secure-agent-pod` folder: vk-local working-set RSS time series (with 3 GiB / 6 GiB thresholds matching the 8 GiB cgroup limit), a cumulative-restart stat panel, and a last-terminated-reason table. Verification (Task 2 Step 2) and 24 h soak (Task 3 Step 1) happen post-merge once ArgoCD syncs and the dashboard provisions. To be appended to the Verification Log on completion.

**Operational gotcha for `frank-gotchas.md`** (apply during Phase 7): VictoriaMetrics' default `-maxLabelsPerTimeseries=40` silently drops entire series (logs at `timeserieslimits/timeseries_limits.go:72` only, no impact on vmagent target health). Frank's amd64 nodes (NFD CPU features + Talos extension labels + NVIDIA driver labels) produce 60–135 labels per series when the kubelet `VMNodeScrape` chart default `labelmap __meta_kubernetes_node_label_(.+)` runs, so they always exceed the threshold. Counter-fix: drop high-cardinality node-meta labels in `metricRelabelConfigs` rather than bumping `-maxLabelsPerTimeseries`. Bumping the limit just kicks the cardinality bomb downstream into vmsingle storage.

### Phase 1 — `kubectl top` unavailable (2026-04-30)

The plan's Task 1 Step 4 instructed `kubectl top pod -l app=secure-agent-pod --containers`. The Kubernetes metrics API returned `error: Metrics API not available`. This is a confirming symptom of the cadvisor pipeline gap that Phase 2 was created to fix — the same five amd64 nodes (`mini-1/2/3`, `gpu-1`, `pc-1`) whose `container_memory_working_set_bytes` series are missing in VictoriaMetrics also have no flow into metrics-server. `vk-local`'s pod is on `gpu-1`, so `kubectl top` for it is silent end-to-end.

Substituted: read `/sys/fs/cgroup/memory.current` and `memory.stat` directly from the vk-local cgroup via `kubectl exec`. Recorded in the Verification Log below.

### Phase 3 — path corrections (2026-04-30)

The plan's example commands used placeholder paths; the agent-images PR (`#34`) and follow-up PR (`#47`) ship the verified-on-Frank versions:

- Worktree iteration root: plan said `/home/claude/vibe-kanban/repos` (placeholder). Actual canonical repo root is `$AGENT_HOME/repos/*/.git`. Vibe-kanban worktrees live under `/var/tmp/vibe-kanban/worktrees/` (tmpfs, wiped on pod restart) and link back via `.git` gitdir files.
- Log destination: plan said `/var/log/agent/`. Actual log dir is `$AGENT_HOME/.willikins-agent/` (matches existing cron entries; `/var/log/agent` does not exist in the kali image).
- Both crons use `__AGENT_HOME__` placeholder, substituted by `cont-init.d/50-seed-config` on first boot. Existing PVs (e.g. `secure-agent-pod`) keep the older crontab — same gotcha as the `~/.tmux.conf` seed pattern documented in `frank-gotchas.md`. Two new lines must be appended to the live `~/.crontab` once via `kubectl exec`; supercronic auto-reloads, no pod restart required.
- Hardening added in #47 after code review: `flock` single-instance guard on both crons, atime/noatime probe with mtime fallback in npm-cache-prune, propagation of `npm cache verify` exit codes, and per-repo failure tracking in worktree-prune.

## Verification Log (Phase 1)

### 2026-04-30 — Initial verification

| Field | Value |
|-------|-------|
| Timestamp (UTC) | 2026-04-30 |
| Pod | `secure-agent-pod-57447df468-x488f` (node `gpu-1`) |
| Pod startTime | 2026-04-29T22:10:28Z |
| Container memory limit | `8Gi` ✓ matches PR #142 |
| `restartCount` | `0` |
| Last termination reason | _(none — never restarted on this pod)_ |
| OOM events in namespace | none found via `kubectl get events` |
| `kubectl top` | unavailable (metrics-server / cadvisor pipeline gap — see Phase 2) |
| `memory.current` (vk-local cgroup) | 6,183,456,768 B ≈ **5,896 MiB** |
| `memory.max` (vk-local cgroup) | 8,589,934,592 B = 8 GiB ✓ |
| `memory.stat anon` | 1,545,146,368 B ≈ 1,473 MiB |
| `memory.stat file` (page cache) | 4,120,395,776 B ≈ 3,930 MiB |
| `memory.stat kernel` | 512,790,528 B ≈ 489 MiB |

**Interpretation.** True working set (anon + kernel + non-reclaimable) ≈ 1.96 GiB; the rest is reclaimable file cache (npm cache + git worktree files). At ~73% of the 8 GiB limit but with no restarts since the PR #142 bump, the headroom is functioning as intended. This baseline is the input row Phase 5 compares against after Phase 3 housekeeping and Phase 4's concurrency cap land.

**Note (Step 4 fallback).** The metric the plan originally asked for (`kubectl top`) requires the cadvisor pipeline that Phase 2 fixes. The cgroup-direct reading above is the substitute baseline; once Phase 2 lands, Phase 5 should re-read the same fields plus `container_memory_working_set_bytes` from VictoriaMetrics for a continuous time-series.

## Soak Log (Phase 5)

**Soak window:** 2026-05-03 → 2026-05-17 (14 days from Phase 4 Task 2 merge in [`c88b755`](https://github.com/derio-net/frank/commit/c88b755) at 2026-05-03 01:52 +0200; vk-local pod `secure-agent-pod-f89b886c5-48pgn` started 07:49:13 UTC).

Daily readings — `restartCount`, p99 working-set RSS over the prior 24 h, and peak queue depth — are auto-filled by [`scripts/phase5-soak-daily.sh`](../../../scripts/phase5-soak-daily.sh) from a supercronic entry on the secure-agent-pod (`0 8 * * *` UTC, kali sibling container). On each fire the script branches `vk/phase-5-soak-data-collection` off the latest `origin/main` (or pulls it if it already exists on origin), queries vmsingle for the day's p99 + queue peak, queries `kubectl` for restartCount, replaces the `_tbd_` placeholder for that Day-N row, pushes to `vk/phase-5-soak-data-collection`, and opens a PR against `main` if none is already open against that branch. Subsequent fires append daily commits to the same branch and the same PR. After Day 14 (2026-05-16) the script switches to cleanup-nag mode: one open `vk-ready` GitHub issue with daily one-line comments until the operator removes the cron line and deletes the script. Phase 4 Task 2 already wired the metrics surface end-to-end (`vibekanban_max_executions=4`, the cadvisor pipeline fix from Phase 2, and the new Grafana panels), so each day is a single read.

| Day | Date (UTC) | `restartCount` | OOMKills since soak start | p99 working-set (24 h) | Peak `vibekanban_queued_executions` (24 h) | Notes |
|-----|------------|----------------|---------------------------|------------------------|---------------------------------------------|-------|
| 1 | 2026-05-03 | 0 | 0 | ~2.35 GiB (cadvisor) / ~2.53 GiB (resource), instant 2.09 GiB | 0 (active=2 at sample time, max=4) | Soak start. Phase 4 image `8af0d080` live, env `VK_MAX_CONCURRENT_EXECUTIONS=4` confirmed via `/metrics`. No queue events yet. |
| 2 | 2026-05-04 | 0 | 0 | 2.95 GiB | 3 | pod=secure-agent-pod-c976f9946-rqdqc |
| 3 | 2026-05-05 | 0 | 0 | 0.74 GiB | 0 | pod=secure-agent-pod-c976f9946-rqdqc |
| 4 | 2026-05-06 | 0 | 0 | 0.97 GiB | 0 | pod=secure-agent-pod-c976f9946-rqdqc |
| 5 | 2026-05-07 | 0 | 0 | 1.05 GiB | 0 | pod=secure-agent-pod-5c46cb8f7b-9765c |
| 6 | 2026-05-08 | 0 | 0 | 0.24 GiB | 0 | pod=secure-agent-pod-5c46cb8f7b-9765c |
| 7 | 2026-05-09 | 0 | 0 | 0.38 GiB | 0 | pod=secure-agent-pod-5c46cb8f7b-9765c |
| 8 | 2026-05-10 | 0 | 0 | 1.11 GiB | 0 | pod=secure-agent-pod-5c46cb8f7b-9765c |
| 9 | 2026-05-11 | 0 | 0 | 0.99 GiB | 0 | pod=secure-agent-pod-5c46cb8f7b-9765c |
| 10 | 2026-05-12 | 0 | 0 | 1.56 GiB | 0 | pod=secure-agent-pod-5c46cb8f7b-9765c |
| 11 | 2026-05-13 | 0 | 0 | 1.73 GiB | 0 | pod=secure-agent-pod-5c46cb8f7b-9765c |
| 12 | 2026-05-14 | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _operator entry_ |
| 13 | 2026-05-15 | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _operator entry_ |
| 14 | 2026-05-16 | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _operator entry_ |

### Day 1 raw query output (2026-05-03)

```
$ kubectl -n secure-agent-pod get pod -l app=secure-agent-pod \
    -o jsonpath='{range .items[0].status.containerStatuses[?(@.name=="vk-local")]}restartCount={.restartCount}{"\n"}lastReason={.lastState.terminated.reason}{"\n"}{end}'
restartCount=0
lastReason=

$ kubectl -n secure-agent-pod get pod -l app=secure-agent-pod \
    -o jsonpath='{.items[0].spec.containers[?(@.name=="vk-local")].resources.limits.memory}'
8Gi

$ # vibekanban_max_executions / queued / active (via vmsingle, instant)
vibekanban_max_executions{...,pod="secure-agent-pod-f89b886c5-48pgn"} = 4
vibekanban_queued_executions{...} = 0
vibekanban_active_executions{...} = 2

$ # quantile_over_time(0.99, container_memory_working_set_bytes[1d]) — current pod, last 24 h
cadvisor   = 2_521_899_008  B  ≈ 2.35 GiB
resource   = 2_723_295_232  B  ≈ 2.54 GiB

$ # current instant
cadvisor   = 2_244_149_248  B  ≈ 2.09 GiB
resource   = 2_250_391_552  B  ≈ 2.10 GiB
```

The "p99 over 24 h" series above includes the brief overlap with the previous pod (`secure-agent-pod-67cddc9d8-xlsz4`, image `3fdae2b7`) and the older `6bc54b47f6-nx82m` (image `3e3e5a2d`) before it; from Day 2 onwards the same query restricted to `pod="secure-agent-pod-f89b886c5-48pgn"` will give a clean Phase-4-image-only number.

> **Decision (Task 2) is blocked until 2026-05-17.** Outcomes (a)/(b)/(c) require the full 14-row table; do not promote this PR's Day 1 reading to a decision rationale on its own.
