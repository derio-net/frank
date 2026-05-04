# Terminal 2 — data-plane observer

Role: pod / ReplicaSet / AnalysisRun watcher for the LiteLLM canary.

## What I saw, in order

| Local time | Event |
|---|---|
| 17:05:30 | T0 baseline. 5 stable on RS `79db46b9fc`, one pod per node (mini-1/2/3, gpu-1, pc-1). Rollout `Healthy`, step 6/6, weight 100/100. The 39-day-stuck Progressing state is gone — PR 1 was the unstick. |
| 17:07:35Z | ArgoCD sync operation started. Phase Running. Blocked on PreSync hook `Job/litellm-migrations`. |
| 17:11:14Z | Migration pod scheduled to **raspi-1** (arm64). Image pull took **3m53s** (714 MB ARM layer cold). |
| 17:13:20Z | `prisma migrate deploy` → "No pending migrations". Then post-migration sanity check **detected schema drift**, auto-generated `20260504151320_baseline_diff/migration.sql`, applied it via `prisma db execute`. Data-state-mutating, not just code-state-mutating. |
| 17:15:04 | Canary RS `litellm-67b4ccbdb4` created at `replicas: 1`. Stable RS scaled 5 → 4. Ghost RS `litellm-c78cd66fd` also appeared at `replicas: 0` (probably double-render of the Deployment template during sync). |
| 17:15:23 | Canary pod `Ready 1/1` on mini-3. Rollout phase `Paused` at step 1/6, ActualWeight 20. Math check: `ceil(20 × 5 / 100) = 1` ✅. |
| ~17:23:51Z | AnalysisRun `litellm-67b4ccbdb4-2-2` started. *(Question for T1: was this a manual promote? AR start time predates your "promote upcoming" message in my channel.)* |
| 17:24:31Z | 5 consecutive `Error` measurements at 10s cadence. Rollout aborted. All replicas back to stable. |

## The big finding — the runbook is wrong about the failure mode

The runbook (`docs/runbooks/litellm-canary-observation.md`) says:

> With idle traffic the result is NaN → inconclusive → eventually aborts.

That is **not what happens**. The actual failure path is:

1. Query: `sum(rate(litellm_request_total{status!~"2..|3.."}[5m])) / sum(rate(litellm_request_total[5m]))`
2. With no recent samples, *both* sub-expressions return an **empty result vector** (`[]`), not NaN.
3. Argo Rollouts' Prometheus provider does `result[0]` without a length check.
4. Go runtime panics with `reflect: slice index out of range`.
5. The metric phase becomes `Error`, not `Inconclusive`.
6. After 5 consecutive Errors at 10-second retry cadence (not the configured 1-min interval — Errors retry faster), the default `consecutiveErrorLimit: 4` is exceeded and the rollout aborts.

**Implications:**

- `inconclusiveLimit: 3` in the AnalysisTemplate is dead code on this query — we never reach the Inconclusive path.
- The fast 10s error-retry cadence means the rollout aborts in ~50 seconds of zero traffic, not the ~5 minutes one would expect from `interval: 1m, count: 5`. **Anyone driving synthetic traffic from Terminal 3 has under a minute to start producing requests after promote.**
- Defensive fix: `(query) or on() vector(0)` to guarantee a result vector, or pre-warm by driving traffic *before* hitting promote.

## Questions for the room

**For Terminal 1:**
1. Did you fire `kubectl argo rollouts promote` before sending "promote upcoming," or after? If after — there's something else auto-promoting, and we need to find it. If before — minor: heads-up landed late.
2. Re-trigger strategy: do you want to (a) fix the AnalysisTemplate query first and re-merge PR 1.5, (b) re-trigger as-is with synthetic traffic running pre-promote, or (c) investigate whether `litellm_request_total` even exists in VM before either?

**For Terminal 3:**
1. Was the synthetic traffic loop running during the 17:23:51 → 17:24:31 window? (One question, because the AR is gone now and there's no way for us to back-confirm.)
2. If yes: did you see any 5xx responses, or all 200? (Helps disambiguate "metric exists but query returns empty" from "metric doesn't exist at all".)
3. If no: was that intentional (waiting for go), or did the loop fail / get killed?
4. Suggested check whoever has cluster access can run, to disambiguate metric-existence vs zero-traffic:
   ```bash
   kubectl exec -n monitoring deploy/grafana -- wget -qO- \
     'http://vmsingle-victoria-metrics-victoria-metrics-k8s-stack.monitoring.svc.cluster.local:8428/api/v1/query?query=litellm_request_total' \
     | jq '.data.result | length'
   ```
   `>0` = metric exists, root cause was zero traffic during AR.
   `0` = metric doesn't exist; AnalysisTemplate query needs renaming.

## Other things worth surfacing for the docs

1. **PreSync hook tax**: 4 minutes per canary if the migration Job lands on raspi-1 (arm64 cold pull of a 714 MB image). If we round-trip PR 1.5 + PR 1.6 in succession this becomes ~8 min of pre-canary wait that has nothing to do with the canary. Worth a `nodeSelector: kubernetes.io/arch=amd64` on the migration Job in the chart values.
2. **Schema drift auto-reconciliation**: The post-migration sanity check generated and applied a baseline_diff migration without ceremony. Should be flagged in the operating runbook so an operator running the *next* canary doesn't see a mysterious 21-second `prisma db execute` and assume something is broken.
3. **Ghost ReplicaSet**: A Deployment-template-hash that briefly exists at `replicas: 0` and is then orphaned. Cosmetic, but if anyone's running RS-count assertions in CI, they'll need to tolerate it.
4. **No transient 6-pod state observed**: Controller did the 5-stable → 4-stable+1-canary swap as a single coordinated update. Either the canary `maxSurge` math collapsed it, or my 3s polling cadence missed a sub-second 6-pod window. Probably the former.

I'll update this file when there's new state to share.

---

## Update — read T1 and T3 (~17:30)

### Where my analysis was wrong

I floated "could be zero traffic OR missing metric" as the root cause of the AnalysisRun Error. **T1's diagnosis is the deeper one and supersedes mine:** the metric `litellm_request_total` is not in VictoriaMetrics at all, because the OSS LiteLLM image we run does not expose Prometheus metrics — that integration is an Enterprise (paid) feature. T1 confirmed by hitting the pod's `:4000/metrics` endpoint and getting HTTP 404. I tried to independently re-confirm from inside a stable pod (`/metrics`, `/prometheus/metrics`, `/metrics/prometheus`) but the container has neither `wget` nor `curl`, so my verification path was blocked. T1's finding stands; the bug is structural ("the AnalysisTemplate was wired to a metric source that was never present"), not transient.

T3 framed it slightly differently — "PR #216's new query correctly returns empty when the canary is healthy, and Argo's `result[0]` panics on empty vectors." That framing is also incomplete: in a `5xx_rate / total_rate` query, a fully-healthy backend produces a non-empty *denominator* (200s still count as `total`) and an empty *numerator*, and Prometheus arithmetic on `empty/non-empty` returns no result for that bucket — but the slice would still have one entry per *label set*. The reason there are *zero* label sets is that there are zero `litellm_request_total` series in VM at all. So T1's "metric doesn't exist" is the upstream cause; T3's "query returns empty" is the downstream symptom that would be true *even if* T3's traffic loop were producing 50% 5xx and 50% 200s.

### Answer to T1's question — was traffic distribution clean?

I can't measure the canary pod's share directly (RS scaled to 0 deleted the pod; logs are gone), but I can measure the stable side and infer.

Per-stable-pod request count over the last 15 min (covers pre-canary 90s false-start + 8.5min pause window + ~2min post-abort):

| Pod | Node | Requests |
|---|---|---|
| `litellm-79db46b9fc-4t757` | mini-1 | 152 |
| `litellm-79db46b9fc-9r6c5` | mini-2 | 142 |
| `litellm-79db46b9fc-dnmn6` | pc-1   | 127 |
| `litellm-79db46b9fc-wtjvx` | mini-3 | 139 |

Mean 140, std-dev ~9.4, **σ/μ ≈ 6.7%**. That is textbook uniform distribution from a 4-endpoint Service over independent connections (T3's curl loop opens a fresh socket per request — no HTTP keep-alive stickiness). There is no source-IP affinity bias, no node-locality bias, no Cilium cluster-mesh skew.

By symmetry I'd expect the canary endpoint to have received its proportional ~20% share during the canary window. I have no direct evidence to confirm that, but I have no evidence against it either, and the within-stable uniformity is strong indirect evidence that the load-balancing layer behaved correctly. **Tentative answer to T1: distribution realised cleanly. The 5-pod 20%/80% split was honoured at the kube-proxy level.**

(Caveat for the postmortem: future rehearsals should add `kubectl debug` or a Job sidecar that snapshots the canary pod's logs/metrics into a PV before scale-down, so we don't lose this signal on abort. The canary's logs are exactly the artifact we need most for post-abort analysis and they vanish first.)

### T3's "premature first Go" — clarifying who that was

T3 wrote: "**17:05 — first 'Go' was premature.** Terminal #1 called 'canary fired' but the live cluster was at `Status: Healthy, Step 6/6, SetWeight 100`."

For the record: that was T1 calling it, not me. My session log shows my "engage" prompt arrived at ~17:16:48, *after* the rollout had demonstrably reached `Paused / Step 1/6 / SetWeight 20` at 17:15:23. So the premature signal was upstream of me. Worth noting because the postmortem might otherwise read as "T2 mis-called the canary as paused" — I didn't, T1 did, and T3 was right to call it out.

### My take on T1's three options

**Lean A** — drop AnalysisRuns, replace with `pause: { duration: ... }` or indefinite-pause-with-manual-promote. Cheapest, finishes the rehearsal, and is *honest* about where we are: there's no metric source, so don't pretend there's metric gating. I'd add one structural touch: keep the AnalysisTemplate file in the repo even if unreferenced, with a stub showing the *pattern* (e.g. `web` provider against `/health/readiness`), so the next operator has a starting point. Document the gap explicitly in the operating runbook: "promotion is currently manual; metric-gated automation pending a real signal source."

**B** is interesting but deserves its own brainstorm. T3's "per-RS metric labels" suggestion (below) plus Hubble L7 stats together would actually solve three failure modes at once — but that's a design question worth a real spec, not an inline patch.

**C** is defensible. Five bugs caught and four captures recorded is itself a strong artifact. But A is ~30 min and gives us a working end-to-end pipeline to merge.

### On T3's per-RS metric labels suggestion

Strongly agree, and worth elevating. The current AnalysisTemplate's union-of-stable-and-canary aggregation has the dilution bias T3 quantified (a 100%-broken canary at 20% weight only shows as 20% union error, exactly at the 5% threshold's noise floor). Fix requires either: (a) a metric source that carries `pod` or `rollouts-pod-template-hash` as a label and a query like `... * on(pod) group_left() (kube_pod_labels{label_rollouts_pod_template_hash="<canary-hash>"})`, or (b) a different signal entirely. Both presuppose Bug #5 is fixed first — without the metric existing, label discrimination is moot.

### On T3's PR #215 nonce suggestion

Agree. `CANARY_REHEARSAL_NONCE: "<short-uuid>"` is more robust than a date-coded var. Same-day repeats and next-day repeats both work without collision. The PR template that creates the synthetic-trigger PR could `uuidgen | head -c 8` at draft time. Cheap fix, prevents a real footgun.

### One thing I want to flag for whoever writes the postmortem

The "5 latent bugs in the deploy layer" arc T1 sketched is good narrative, but Bug #5 is *load-bearing* in a way the others aren't: bugs 1–4 were all in our YAML / chart values / template logic, fixable in a PR. Bug #5 is a license/feature-tier mismatch — we're running OSS LiteLLM, the metric we wired to is Enterprise. Closing #5 properly means either paying for Enterprise, building our own exporter (sidecar that scrapes LiteLLM's logs or proxies the API and emits Prometheus metrics), or scrapping metric-gated promotion and using a different signal class entirely (Hubble L7, synthetic probes, web/HTTP). That decision is bigger than this rehearsal and probably bigger than this layer. Worth flagging to the operator that "fix Bug #5" is not a 30-minute task and shouldn't block landing PR 2.

---

I'll keep watching. If anything new shows up on the rollout (e.g. T1 fires a re-attempt, the operator merges PR #217 fixing the AnalysisTemplate, or the cluster goes weird in some other way) I'll append again.

---

## Update — read T1's consensus post (~17:50)

Operator confirmed: **proceed with Path A**. T1 has the work. Three short notes back.

### On T1's `lifecycle.preStop` hook attribution

T1 wrote: *"T2's `lifecycle.preStop` hook on canary pods that `tar`s `/var/log` to a known PVC mount before scale-down."*

For the record: I sketched it as `kubectl debug` or "Job sidecar that snapshots before scale-down." T1 elaborated it into a `preStop` hook, which is **strictly better** as a mechanism — preStop runs synchronously in the pod's own context during graceful termination, no external orchestration, no race against the RS controller deleting the pod. Ascription drift in T1's direction. The thing that should land is T1's mechanism, not mine. Endorsed.

### On the parked-aborted cluster state

Confirmed clean. As of 17:51 local:
- Rollout: `Degraded`, `Step 0/6`, ActualWeight 0, message still references the panic.
- 5 stable pods on RS `79db46b9fc`. Pre-canary placement was mini-1/2/3 + gpu-1 + pc-1; post-abort placement is the same 5 nodes — but the gpu-1 pod has a fresh identity (`bqjlp`, age 25m, created at abort moment). Pod names do not survive a canary rejection. Worth a footnote in the operating runbook.
- ArgoCD: `Synced / Healthy`, last operation finished `15:15:01Z` (the original PR #215 sync). No new sync since.
- Bg logger (PID 42396) still alive and recording state changes.

When T1's Path-A PR lands, I'll see ArgoCD start a new sync, then the Rollout controller will pick up the analysis-stripped spec, then `kubectl argo rollouts retry rollout litellm` will rerun the canary against the same pod-template (no need for a new RS). I'll capture the same 1+4 / 3+2 / 5+0 transitions for the postmortem.

### One small thing I noticed worth flagging (not blocking)

Bg logger captured a 17:48:30 → 17:48:41 blip where the stable RS briefly went `5 desired / 3 ready`. No pod restarts (`RESTARTS=0` on all 5 pods now), no ArgoCD activity, no rollout step change. Two of the five readiness probes flaked simultaneously for ~10 seconds and recovered.

Likely cause: LiteLLM's default readiness probe is on `/`, which (for OSS LiteLLM) touches the database. A brief DB hiccup or upstream stall would flake all probes that happen to fire during the window. Same gotcha is documented for ruvocal in `frank-gotchas.md`: *"`/api/v2/feature-flags` is the right readiness/liveness path for ruvocal, NOT `/` — ruvocal SSR-renders the model list at request time."*

Adjacent recommendation for the postmortem (not for this PR): add LiteLLM to the same gotcha — readiness should target a static endpoint that doesn't reach into upstreams. Otherwise canary readiness probes will lie about pod health any time the database is briefly slow, which is exactly the situation where you most want them to be honest.

Standing by for the rollout retry signal.

---

## Update — PR #217 (Path A) merged, both pause boundaries captured (~17:58)

The retry was clean. Both pauses captured. One genuine surprise on the math.

### Timeline

| Time | Event |
|---|---|
| ~17:53:08 | ArgoCD picked up PR #217. Rollout spec now has 4 steps (`setWeight 20 / pause / setWeight 50 / pause`), no `analysis` blocks. |
| 17:53:09 | Canary RS `litellm-67b4ccbdb4` scaled to 1 (controller picked up the analysis-stripped spec and treated it as a fresh canary, even though the RS hash matches the previously-aborted attempt — Argo Rollouts identifies revision by template hash, not by step list). |
| 17:53:27 | **Pause boundary #1: Step 1/4, SetWeight 20, ActualWeight 20**, 1 canary on RS `67b4ccbdb4` (mini-3) + 4 stable on `79db46b9fc` (mini-1, mini-2, gpu-1, pc-1). Total **5 pods, no surge**. |
| 17:57:14 | T1 promoted past the 20% pause. Step 2/4 progressing. |
| 17:57:17 | Canary RS desired=3, ready=1 (2 new canary pods scheduling). Bg logger caught this 18s sub-state. |
| 17:57:35 | All 3 canary pods ready. **Pause boundary #2: Step 3/4, SetWeight 50, ActualWeight 50**, 3 canary on `67b4ccbdb4` (mini-1/2/3) + 3 stable on `79db46b9fc` (mini-1/2 + gpu-1). Total **6 pods, surge of 1**. |

20% pause duration: 3min 47s. Canary pod survived through Step 2 and is now joined by 2 fresh canary peers — the pod that was ready at the 20% pause (`67b4ccbdb4-sjrhg`, mini-3, age 4m38s at the 50% pause) is the *same pod object* across both pauses. That is genuine continuity worth knowing for the postmortem narrative.

### The math correction

T1 (and I) predicted `3 canary + 2 stable = 5` at the 50% pause. **Reality: `3 canary + 3 stable = 6`.** The asymmetry between the two pauses comes from how Argo Rollouts canary (without traffic-routing) computes counts:

```
canary_count = ceil(canary_weight × desired / 100)
stable_count = ceil(stable_weight × desired / 100)
```

Both round *up*. With desired = 5:

| SetWeight | canary_count | stable_count | total | surge |
|---|---|---|---|---|
| 20 | ceil(1.0) = 1 | ceil(4.0) = 4 | 5 | 0 |
| 50 | ceil(2.5) = **3** | ceil(2.5) = **3** | **6** | **+1** |
| 100 | 5 | 0 | 5 | 0 |

The 50% pause is *structurally* a 6-pod state — not transient, not ramping, the configured equilibrium for that step. Pods stay at 3+3 until the next promote. My earlier prediction (`3+2`) assumed `total = desired = 5` was an invariant. It isn't. That's a runbook correction worth landing in PR 2: at the 50% pause, expect 6 pods, not 5. Anyone running a `replicas == 5` assertion at the pause boundary will see a false alarm.

(Also note: the surge happens at any weight where both `canary_weight` and `stable_weight` round up to exceed `desired`. With `desired = 5` that's only the 50% step. With `desired = 4` it would happen at 25% (1+3=4 no, ceil(1)=1, ceil(3)=3 = 4 no surge), 50% (ceil(2)+ceil(2) = 4 no surge), 75% (ceil(3)+ceil(1) = 4 no surge). So the surge is replica-count-and-step-list dependent. Worth explaining once in the runbook so the postmortem reader doesn't have to derive it.)

### Pod placement comparison

| Pause | mini-1 | mini-2 | mini-3 | gpu-1 | pc-1 |
|---|---|---|---|---|---|
| Pre-canary (T0) | s | s | s | s | s |
| 20% pause | s | s | **s+c** | s | s |
| 50% pause | **s+c** | **s+c** | **c** | s | — |

Where `s = stable, c = canary, s+c = both on the same node, — = empty`. As canary scales 1 → 3, the scheduler pulled fresh canary pods onto mini-1 and mini-2 (now hosting one of each). pc-1's stable pod was evicted to make room — its slot is now empty. mini-3 has the original canary plus has lost its pre-canary stable pod.

### What I'm watching for next

T1 has one more promote to fire (past the 50% pause) which will advance the rollout to 100% (or — strictly — to the implicit final state past the last `pause: {}` step list entry: 5 canary + 0 stable, no more surge).

Bg logger still tracking. Will append the 100% capture and pod placement when it lands.

### Side findings worth flagging

- **Canary pod identity continuity across promotes.** Pod `67b4ccbdb4-sjrhg` was created at the 20% pause and is still running at the 50% pause. Promoting through the canary does *not* roll the original canary pod — it scales the RS, which keeps existing pods alive and adds new ones. So if a canary pod has lazy-init state (warm caches, JIT), that state survives across promotes. Could matter for "the canary works fine in dev because the pod's been alive 30min" failure modes.
- **Identical RS hash across the aborted run and the retry.** The canary RS is still `litellm-67b4ccbdb4` — same hash as the aborted attempt. Argo Rollouts hashes by Deployment pod-template, and Path A only changed the *Rollout's* `strategy.canary.steps`, not the pod template. So the same RS got revived by `kubectl argo rollouts retry`. Cheap and clean.
- **No raspi-1 PreSync hook tax this time.** Path A's PR didn't change anything that triggers the migration Job re-run, so `kubectl argo rollouts retry` re-fired the canary instantly without a 4-minute image-pull on raspi-1. If the third planned step (PR 1.6 env-var revert) runs cleanly through the same retry mechanism rather than as a new sync, we save the tax twice. Worth confirming with T1.

---

## Update — final promote captured, rollout Healthy (~18:02)

T1 promoted past the 50% pause around 18:00. Bg logger caught the full transition without missing a frame.

### Final transition timeline

| Time | RS state | Note |
|---|---|---|
| 17:57:35 | canary=3/3, stable=3/3 | 50% pause boundary (already captured) |
| ~18:00:00 | promote fired (T1) | |
| 18:00:04 | canary desired=5 ready=3, stable desired=1 ready=1 | Mid-transition. Canary scaled 3→5 *simultaneously* with stable scaling 3→1. **Surge collapsed in this step**, not extended. |
| 18:00:21 | canary desired=5 ready=4, stable=0 | Stable RS fully drained. |
| 18:00:43 | canary desired=5 ready=5, stable=0 | All-new pods ready. |
| 18:02:20 | Status: ✔ Healthy, Step 4/4, SetWeight 100, ActualWeight 100 | Final state. |

**Total wall time, first canary pod ready → fully Healthy: ~7 minutes**, including two operator-paced pause windows.

### Final pod placement

| Pod | Node | Age (at 18:02:20) | Note |
|---|---|---|---|
| `67b4ccbdb4-67xnw` | gpu-1 | 2m21s | Fresh, scheduled at final promote |
| `67b4ccbdb4-bqwn5` | mini-2 | 5m07s | Scheduled at 50% promote |
| `67b4ccbdb4-qg5k7` | pc-1 | 2m21s | Fresh, scheduled at final promote |
| `67b4ccbdb4-sjrhg` | mini-3 | **9m15s** | **Original canary pod** from the 20% boundary — survived all three pauses |
| `67b4ccbdb4-vczdc` | mini-1 | 5m07s | Scheduled at 50% promote |

Distribution at 100%: same one-pod-per-node spread as the original baseline (mini-1, mini-2, mini-3, gpu-1, pc-1). Symmetry preserved.

### Two things worth flagging

**(1) The final promote does NOT surge.** The 50% pause was a 6-pod surge state (3+3). The final promote went 6 → 5, not 6 → 7 → 5. Bg logger's 18:00:04 entry shows the controller scaled canary 3→5 *simultaneously* with stable 3→1, not the surge-then-trim pattern of the intermediate step. So the maximum pod count for an entire canary cycle is `max(canary_count + stable_count over all steps)`, which here is 6 (at the 50% pause), not 7. Useful for capacity planning if you're doing this on a node-count-constrained cluster.

**(2) Original canary pod survived all three pauses.** `67b4ccbdb4-sjrhg` (mini-3) was created at the 20% pause boundary (17:53:27) and is still running at 18:02:20 — uninterrupted 9m15s. Promoting through the canary scales the RS up, it does NOT roll the existing canary pods. So whatever lazy initialisation that pod has done — connection pool warmup, JIT-compilation, cached model lookups — is amortised across the entire canary lifecycle. The pods scheduled at the *final* promote (`67xnw`, `qg5k7`, age 2m21s) had to do that warmup at full traffic instead. **For a real release with canary-passing-but-cold-start-slow risk, those late pods are the ones to watch in metrics — not the original canary.** Worth a runbook note.

### Status: ready for PR 1.6

Rollout is Healthy. Stable RS is now `67b4ccbdb4`. The "old stable" `79db46b9fc` is at 0 replicas.

PR 1.6 should revert the env-var change, producing a Deployment pod template **identical to the original pre-canary template** — whose hash was, conveniently, `79db46b9fc`. So when PR 1.6 syncs, the controller will *revive* the now-empty `79db46b9fc` RS as the canary, going through the same mechanics in mirror image. Same RS hash recycling we saw on the retry, but in the opposite direction. Should produce a clean second set of captures with no new pod-template hashes appearing.

(One small gotcha to anticipate: if PR 1.6's chart values touch anything beyond the synthetic env var — say, an annotation on the Deployment template, or a label change — the new template hash will be neither `67b4ccbdb4` nor `79db46b9fc`, and we'll see a third RS appear instead of a revival. Worth checking the PR's diff before T1 fires the sync.)

Bg logger still alive. Will track the PR 1.6 cycle when it lands.

---

## Update — PR #218 (PR 1.6, env-var revert) merged, 20% pause captured (~18:11)

The mirror-image canary fired. RS hash prediction held.

### Sync timing

| Time | Event |
|---|---|
| 18:06:50Z | ArgoCD operation started (auto-sync after PR #218 merge) |
| ~18:06:50 → 18:10:17 | **PreSync hook `Job/litellm-migrations` ran on raspi-1**. Duration 3m28s — same arm64 image-pull tax as PR #215, just slightly shorter because the layers were warm in raspi-1's cache (`crane`'s reckoning would have shown 0 bytes pulled, only re-extracted). |
| 18:10:39 | ArgoCD operation Succeeded |
| 18:10:43 | Rollout `Paused` at Step 1/4, SetWeight 20, ActualWeight 20 |

So **PR #218 paid the raspi-1 migration tax even though the env-var revert touches no schema**. ArgoCD's PreSync hook fires whenever the chart re-renders the Job — it doesn't introspect whether the Job actually needs to do work. The argument for `nodeSelector: kubernetes.io/arch=amd64` on the migration Job in the chart values now has ~7 cumulative minutes of evidence across this session. Worth landing in PR 2 alongside the runbook updates.

### RS hash recycling — confirmed

Pre-PR-1.6 state: stable on `67b4ccbdb4` (5 replicas), `79db46b9fc` at 0 replicas.

Post-PR-1.6 sync, paused at 20%:
- **Canary:** `79db46b9fc` at 1 replica — the *original* pre-PR-1.5 hash, revived from 0.
- **Stable:** `67b4ccbdb4` at 4 replicas — was the canary in PR 1.5, became stable at PR 1.5's final promote, now serves as the rollback target for PR 1.6.

So this whole rehearsal — two full canary cycles + one aborted attempt — used exactly **two distinct pod-template hashes**. The cluster's RS list has the same RS objects it had at T0; their `spec.replicas` just toggled. Argo Rollouts' template-hash-based RS lookup is the mechanism (it doesn't create a new RS for an already-known template hash).

### 20% pause pod placement

| Node | Stable (`67b4ccbdb4`) | Canary (`79db46b9fc`) |
|---|---|---|
| mini-1 | `vczdc` (age 13m) | — |
| mini-2 | *(empty — `bqwn5` was the one selected for eviction)* | — |
| mini-3 | `sjrhg` (age **18m**) | `8l4qg` (age 55s) |
| gpu-1 | `67xnw` (age 11m) | — |
| pc-1 | `qg5k7` (age 11m) | — |

Pod `sjrhg` is the longest-lived survivor — it was the original canary pod from PR 1.5's 20% pause boundary at 17:53:27, survived through PR 1.5's full canary lifecycle, and is now a *stable* pod sitting alongside the new PR 1.6 canary on the same node. **It has been alive across two full canary cycles. Eighteen minutes of continuous uptime.** That's the durability of canary-survivor-pod identity in Argo Rollouts: even when the rollout direction reverses, surviving pods continue.

Curious co-location: the new canary `8l4qg` and the stable `sjrhg` are both on mini-3, while mini-2 is empty. The scheduler chose to double-up rather than use the empty node — probably because the soft anti-affinity weighting at scheduling time (when mini-2 still had the to-be-evicted `bqwn5`) was different from the post-eviction weighting. By the time mini-2 was empty, the canary pod was already bound to mini-3.

### One mild flake worth noting

At 18:10:34 my polling caught a moment where the JSONPath `range .items[?(@.spec.replicas>0)]` returned an empty list, despite all 5 pods continuing to run on `67b4ccbdb4`. Three seconds later the same query showed `67b4ccbdb4=4 79db46b9fc=1`. Likely a transient API server view in the middle of a multi-resource update. **Not a real "no pods" state** — just a JSONPath evaluation hitting a sub-second window between `/replicas` updates. Worth knowing for anyone who runs RS-count assertions in CI or alerting; you'll occasionally see a 0-RS-with-replicas snapshot during canary transitions and it isn't real.

### What I expect for the rest of PR 1.6's cycle

By symmetry with PR 1.5:
- Step 2 (canary scales to 50%): expect `79db46b9fc` desired=3, `67b4ccbdb4` desired=3, total 6 (surge of 1).
- Step 3 (50% pause): same 3+3 = 6 equilibrium.
- Final promote: `79db46b9fc` scales to 5, `67b4ccbdb4` scales to 0 simultaneously, no surge phase. Returns to 5 pods total.

Mini-2 will probably get its pod back at the final promote when the scheduler has 5 fresh canary pods to place across 5 nodes. That'd restore the original one-per-node distribution, just with `79db46b9fc` as the active RS.

Bg logger still tracking. Will append the 50% and 100% captures.

---

## Update — PR 1.6 50% pause + final promote captured (~18:15)

Rehearsal complete. Two full canary round-trips, all six pause/transition events captured.

### PR 1.6 50% pause (18:12:55)

3 canary on `79db46b9fc` + 3 stable on `67b4ccbdb4` = 6 pods. Surge math holds, mirror image of PR 1.5.

| Node | Stable | Canary |
|---|---|---|
| mini-1 | `vczdc` | `wl8st` |
| mini-2 | — | `ffv4x` |
| mini-3 | — *(`sjrhg` evicted)* | `8l4qg` |
| gpu-1 | `67xnw` | — |
| pc-1 | `qg5k7` | — |

The notable death this round: **`sjrhg` was terminated at this transition.** It had been alive 19 minutes, surviving every prior pause boundary. Likely killed because soft anti-affinity preferred terminating the stable pod co-located with a canary peer (mini-3) over a stable pod alone on its node. So the controller's choice of which stable pod to reduce was *not* random — it was anti-affinity-aware. Worth a runbook note: when stable RS scales down by 1, expect the doubly-occupied node's pod to go.

### PR 1.6 final promote (18:14:18 → 18:14:53)

| Time | RS state | Note |
|---|---|---|
| 18:14:18 | canary 5/3, stable 1/1 | **6-pod transient** (canary already scaled-up but stable still draining) |
| 18:14:32 | canary 5/4, stable 0 | Stable RS fully drained |
| 18:14:53 | canary 5/5, stable 0 | All ready → Healthy |

Total promote → Healthy: **35 seconds**, vs PR 1.5's 43s. Faster because gpu-1 and pc-1 had warm image caches from the earlier cycle.

### Correction to my earlier "no surge on final promote" claim

I wrote earlier: *"The final promote (50% → 100%) doesn't surge."* That was wrong. Both final promotes go through a brief ~10-15s 6-pod surge state (canary scaled to 5 desired but stable still draining at 1 ready). PR 1.5's bg log shows it at 18:00:04 (`canary=5/3 stable=1/1`); PR 1.6's polling caught it at 18:14:18. The state is shorter and asymmetric compared to the 50% pause's 6-pod equilibrium, but it *is* a surge.

**Corrected mental model:** maximum pod count for a canary cycle on this rollout is **6**, not 5. Hit twice per cycle: once at the 50% pause as a stable equilibrium (3+3), once briefly during the final promote (5+1 → 5+0). Capacity planning should reserve for 6 + Job overhead. PR 2 runbook should reflect this; my earlier post understated by 1.

### Final pod placement (PR 1.6 → 100%)

5 pods on `79db46b9fc`, one-per-node distribution restored:

| Pod | Node | Age | Born at |
|---|---|---|---|
| `8l4qg` | mini-3 | 4m35s | 20% pause |
| `wl8st` | mini-1 | 2m27s | 50% pause |
| `ffv4x` | mini-2 | 2m27s | 50% pause |
| `8pdf7` | gpu-1 | 42s | Final promote |
| `j2xq6` | pc-1 | 42s | Final promote |

Three pod-generations co-existing in the new stable RS. The pattern for both round-trips: the 20%-pause canary pod has the longest run, the 50%-pause pods are the second tier, the final-promote pods are the youngest.

**Implication for canary signal interpretation**: a clean canary signal at the 20% pause window only certifies that the *single, well-warmed canary pod* serves traffic correctly. The pods that scale up at 50% and at the final promote do their warmup *under live traffic*. So a "canary passes at 20%" verdict is necessary but not sufficient — the operator should also watch metrics for the 5–10 minutes *after* Healthy to catch any cold-start regressions on the 4 fresh pods. PR 2 runbook should call this out.

### Round-trip is complete: cluster state

- **Active stable RS: `79db46b9fc`** — the original pre-PR-1.5 hash. The cluster is exactly where it started in terms of pod-template, just with 5 fresh pod identities.
- **Retired: `67b4ccbdb4`** at 0 replicas. The PR 1.5 canary that became stable, now demoted by PR 1.6.
- **Six historical empty RSs** unchanged at 0 (cluster's RS list grew by zero across this entire session — Argo Rollouts' template-hash-based RS lookup recycles).

### Cumulative wall-time accounting for the rehearsal

| Event | Wall time |
|---|---|
| PR #213 / PR #214 / PR #216 fixes | (covered by T1's notes; pre-this-conversation) |
| PR #215 sync + first canary fire (aborted) | ~10 min (4 min raspi-1 migration tax + 6 min canary cycle to abort) |
| Path A PR #217 + retry | ~7 min (no migration tax; `kubectl argo rollouts retry` re-fired the existing canary RS instantly) |
| PR #218 sync + mirror canary | ~8 min (4 min raspi-1 migration tax + 4 min canary cycle) |
| **Total observable canary work** | **~25 min** |

Of that 25 minutes, **~8 minutes was the migration Job on raspi-1** (twice, ~4 min each). That's the single biggest optimization target for the next rehearsal: pin the migration Job to amd64 nodes via chart values, halve the wall-time tax.

### What I think the postmortem narrative should center on

1. **The five latent bugs** (T1 has the canonical list). The structural one (Bug #5: paid-feature metric source) is the load-bearing finding for "why progressive delivery on this app is harder than it looked."
2. **What worked, even with no metric gating:** replica-count canary in Argo Rollouts is a real progressive-delivery primitive on its own. We got pause/promote checkpoints, automatic rollback on errors (the first canary's abort was clean), and accurate weight ratios via plain Service endpoint distribution. The "L7 traffic-router plugin" turned out to be unnecessary for the homelab use case.
3. **The runbook corrections** (mine): NaN→Inconclusive is wrong (it's empty-vector→Error→panic), 5+0 isn't transient through a no-surge step (the final promote has a ~15s 6-pod surge), and 50%-pause is structurally a 6-pod state.
4. **Pod-survival pattern across canary cycles**: 20%-pause pods are durable, late-promote pods are cold-start-fresh. The "watch the cold pods after Healthy" recommendation flows from this.
5. **The migration-Job-on-raspi-1 tax** is the single highest-leverage operational optimization.

Bg logger can stop now (the rehearsal is over). I'll append once more if anything weird happens to the cluster post-rehearsal.

