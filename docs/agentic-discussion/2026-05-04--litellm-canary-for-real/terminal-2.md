# Terminal 2 — data-plane observer (real canary)

Same role as the rehearsal: pod / ReplicaSet / AnalysisRun watcher for the LiteLLM canary. Now with a real image bump.

## Pre-flight (~19:15)

### Cluster resting state

- **Rollout:** `✔ Healthy`, Step 4/4, SetWeight 100, ActualWeight 100. Path A's 4-step list intact (`[setWeight 20, pause, setWeight 50, pause]`). No analysis steps came back.
- **Active stable RS:** `79db46b9fc` with `ghcr.io/berriai/litellm-database:main-v1.82.3-stable`, 5 pods one-per-node (mini-1, mini-2, mini-3, gpu-1, pc-1), all 60–64 min old.
- **ArgoCD:** `Synced / Healthy`. Last operation Succeeded at 16:10:18Z (18:10 local), ~65 min ago.
- **Bg logger:** still alive (PID 42396, 6.6s CPU time), unchanged from rehearsal session.

### RS landscape — 7 objects

| RS | Replicas | Image |
|---|---|---|
| `79db46b9fc` | **5/5** | v1.82.3-stable (active) |
| `67b4ccbdb4` | 0 | v1.82.3-stable (retired PR 1.5 canary, post-PR-1.6 demotion) |
| `84d78cd556` | 0 | v1.82.3-stable (older artifact) |
| `547765b96b`, `54ddbf47f5`, `6f64b677d9`, `fcdbfdb94` | 0 | `main-stable` (ancient) |

PR #210 bumps to `v1.83.14-stable` — that's a brand-new pod-template-hash, not a recycle. Expect an **8th** RS object to appear when the sync lands. The cluster's RS list grew by zero across the entire rehearsal; this real canary breaks that streak by exactly +1.

## What's structurally different from the rehearsal

1. **Image actually changes.** Rehearsal cycled between two known v1.82.3 templates by toggling a synthetic env var. PR #210 changes the container image to v1.83.14-stable. Each canary pod that lands on a node without the new image cached pays an image-pull. With the canary scaling 1 → 3 → 5 across mini-1/mini-2/mini-3/gpu-1/pc-1 in some order, that's potentially 5 cold pulls in serial-ish, parallelisable across nodes but bounded by registry bandwidth.
2. **Migration Job on raspi-1 will cold-pull arm64 v1.83.14.** First time on this version. Expect ~4 min image-pull tax (similar to v1.82.3's first pull on raspi-1 during the rehearsal). The Job itself may or may not have real schema work this time (v1.83.14 has 11 more migrations than v1.82.3 per the upstream changelog — the post-migration sanity check from PR #215 showed 108 migrations applied; v1.83.14's migrations dir is somewhere around 119 last I checked). So expect both image-pull *and* genuine schema work, not just the synthetic baseline_diff.
3. **Path A means no metric gating.** The rollout will pause at 20% and 50% based on operator action, no AnalysisRun. Aborts won't auto-fire on backend errors. If a real regression lands and traffic at the canary starts 5xx-ing, the canary will keep serving until someone notices and aborts manually. **Operator vigilance during the pause windows is the only safety net** — that's the trade-off Path A explicitly takes.

## One operational flag I want to surface before the canary fires

**Ollama models for the new lineup are NOT pre-pulled.** Currently 3 stale models on disk (`qwen3.5:9b`, `deepseek-coder:6.7b`, `carstenuhlig/omnicoder-9b`), all 6 weeks old, all marked for removal in PR #210's new lineup. None of the 11 new aliases (`mistral-small3.2:24b`, `gemma3:12b`, `qwen2.5vl:7b-q8_0`, `qwen2.5-coder:14b-instruct-q6_K`, `qwen3:14b`, etc.) are present.

The canary observation runbook explicitly warns:
> Local models trigger Ollama's first-time pull on the initial request — that takes 30–120s per model and may exceed LiteLLM's default upstream timeout. Pre-pull each tag manually before the verification loop.

**This won't break the canary itself** (the canary tests LiteLLM, not Ollama). But after Healthy, when someone runs the runbook's verification loop:

```bash
for model in mistral-small-24b gemma-12b qwen-vl-7b qwen-coder-14b ...; do
  curl ... model="$model" ...
done
```

…the first request to each new alias will trigger an Ollama-side cold pull, will time out at LiteLLM's upstream timeout (~30–60s), and will read like a model regression. It'll resolve itself on the second attempt (after Ollama finishes the pull), but the optics during the operator's "did the canary work?" check are bad.

**Recommendation:** start the pre-pull *now*, in parallel with the canary firing. The Ollama pulls run on gpu-1 and don't affect the LiteLLM canary; they just need to finish before the verification loop. Suggested command (from the runbook):

```bash
for tag in mistral-small3.2:24b gemma3:12b qwen2.5vl:7b-q8_0 \
           qwen2.5-coder:14b-instruct-q6_K qwen3:14b; do
  kubectl exec -n ollama deploy/ollama -- ollama pull "$tag"
done
```

Plus the larger ones from the lineup (`gemma-31b`, `nemotron-vl-12b`, `nemotron-omni-30b`, `qwen-next-80b`, `qwen-coder-480b`, `hermes-405b`) which will take longer. Some of those won't fit in 16GB VRAM all at once — Ollama's lazy-load model means they live on disk and get loaded on demand, so pre-pull just stages the disk content. Total disk footprint is the bigger concern (the chart's 30Gi → 200Gi PVC expansion is presumably for exactly this).

If it's already been kicked off elsewhere and I just can't see it from `ollama list`, ignore — but the model list returned only the 3 old ones at 19:15.

## What I'm watching for

When PR #210 syncs, expect this sequence in the bg logger:

1. **ArgoCD operation Running** — pre-sync hook (migration Job) starts. Expect ~4 min of arm64 image-pull on raspi-1 + genuine prisma work.
2. **Operation Succeeded → Rollout begins.** New canary RS appears (8th object on the list). Pod-template-hash will be different from any of the 7 existing RSs — note the new hash for the postmortem.
3. **Canary RS desired=1.** Canary pod schedules to a node, image-pulls v1.83.14-stable amd64 layers (cold on every node first time, ~30–60s for 700+ MB). Becomes Ready.
4. **Pause boundary 1: Step 1/4, SetWeight 20.** Expected 1 canary + 4 stable = 5 pods, no surge (confirmed from rehearsal math). Operator captures, verifies, promotes.
5. **Pause boundary 2: Step 3/4, SetWeight 50.** Expected 3 canary + 3 stable = 6 pods, surge of 1 (Argo Rollouts' canary math when both ceil() ops round up). Operator captures, verifies, promotes.
6. **Final promote.** Brief 5+1 → 5+0 transient (~10–15s), then Healthy on v1.83.14-stable.

Total wall time, optimistically: ~12 min (4 min migration + 8 min canary cycle), longer if image pulls on amd64 nodes serialize.

## Things to flag for T1 if they appear

- New RS hash collision with an existing one (unlikely — hash space is wide — but worth noting if it happens).
- Migration Job exit code != 0 (would mean real schema breakage, not just migration drift like rehearsal).
- A canary pod takes >2 min to reach Ready (suggests image pull is unexpectedly slow or the node is under pressure).
- Stable pod 5xx rate spike during the canary (not measurable directly without a metric source, but inferable from per-pod log error counts — I can run that check if you want it).
- Any pod restart during the pauses (would suggest a real regression in v1.83.14).

Bg logger is recording. Will append captures as the events fire.

---

## Update — read T1 and T3 pre-flights (~19:25)

Aligned. Two acknowledgments and one operational adjustment.

### Corrections to my pre-flight from T1

- **The Ollama PVC bump is part of PR #210**, not a separate PR as I implied. Sequencing matters: PVC expansion has to land *before* the pre-pull can run (current 30Gi has only 15GB free, can't hold even one new tag). T3's checklist has the right order: merge → wait for `kubectl get pvc -n ollama` to show `CAPACITY=200Gi` → kick off pre-pull → canary continues in parallel.
- **Revision 2 may disappear from the rollout tree mid-canary.** Argo Rollouts' eager rotation of empty revisions when revision 4 (the new one) appears. Won't affect my pod / RS observation but could surface as a "where did this RS go?" moment in the bg logger. Pre-noting so I don't chase a ghost.

### Adopting T3's dual-probe framing for my own per-pod-log analysis

T3's dual-probe (qwen3.5 OLD + mistral-small-24b NEW) gives clean 4xx routing-split signal. **Same logic applies to per-pod log analysis**: I'll compute, at each pause boundary, the per-pod request count by alias. If kube-proxy distribution is doing what we expect, every pod (canary AND stable) should see roughly equal *total* request count, but different *per-alias* counts:

- Stable pods: ~50% qwen3.5 (200), ~50% mistral-small-24b (4xx — alias absent on v1.82.3)
- Canary pods: ~50% qwen3.5 (4xx — alias removed in v1.83.14 model_list), ~50% mistral-small-24b (200, IF the new alias is wired up correctly)

Any deviation from that pattern is signal:
- Stable pod returning 200 for `mistral-small-24b` → wrong; ConfigMap leaked into stable somehow.
- Canary pod returning 200 for `qwen3.5` → wrong; new model_list didn't actually take effect on the canary.
- Either pod returning 5xx for either alias → upstream / runtime issue, not routing.

I'll compute this from logs at each pause boundary and report alongside the pod placement. T3's traffic loop produces the input; my per-pod log grep produces the routing-correctness check.

### One thing I want to add to T1's "things to watch for"

**The 20%-pause critical-path image pull.** First canary pod has to cold-pull `main-v1.83.14-stable` from GHCR before reaching Ready. That's 5-7 min on critical path between operation Succeeded and pause boundary 1 (per T3's estimate). If we see >10 min, suspect either GHCR rate-limit, the node's local image GC having evicted the PrEsync layers, or registry connectivity flake. Not a regression in v1.83.14 itself, but a wall-clock concern worth flagging.

**50% pause and final promote** parallelize the cold-pulls across the 2 new nodes each step. Critical path is `max(pull_time)` per phase, not sum. So total image-pull tax on critical path is approximately 3 × per-node-pull-time ≈ 15-21 min, matching T3's 15-20 estimate.

Standing by for the merge signal. Bg logger continues to track.

---

## Update — first attempt blocked, image patched, 20% pause reached (06:00:38)

### What happened (timeline)

PR #210 merged ~19:25 local with `main-v1.83.14-stable`. ArgoCD picked up the sync immediately. PreSync migration Job spawned on raspi-1 and **failed with `exec /app/.venv/bin/python: exec format error`**. That's a broken arm64 binary in the upstream image — not a multi-arch manifest mismatch, the layer was actually wrong-arch. The Job's `backoffLimit` would have eventually marked it Failed and rolled the sync back; operator intervened before that with a follow-up PR bumping the tag to `main-v1.83.14-stable.patch.1` (an upstream patch release with the arm64 build fixed).

Meanwhile, the operator ran the pre-pull for the new model lineup against Ollama's freshly-expanded 200Gi PVC. That took several hours (the larger tags like `qwen-coder-480b` and `hermes-405b` are massive). When the pre-pull finished, the operator nudged ArgoCD into picking up the patched image and we resumed observation.

| Time | Event |
|---|---|
| 19:25 (prev day) | PR #210 merged, ArgoCD sync started with broken `v1.83.14-stable` |
| 19:34 | Migration Job pod errored: `exec format error` on raspi-1 |
| ~19:35 → 05:51 | Operator: bump tag to `.patch.1`, run pre-pulls in parallel |
| 05:51:09 | ArgoCD picks up patched sync |
| 05:52:15 | Migration Job pod ContainerCreating on raspi-1 (cold ARM pull of patched image) |
| 05:54:24 | Migration Job pod Running |
| 05:58:40 | Sync Succeeded; canary RS `litellm-8c7b9765f` at desired=1; stable scaled 5→4 |
| 06:00:38 | Canary pod Ready; paused at Step 1/4, SetWeight 20 |

Wall-clock from patched-sync-start to 20% pause: **9m29s**. Faster than T3's 30-40min estimate because the canary pod's first-node cold-pull was unusually fast (~2min on mini-3, rather than the budgeted 5-7min).

### State at the 20% pause

**Rollout:** `Paused`, Step 1/4, SetWeight 20, ActualWeight 20. Updated=1.

**Images:**
- Stable: `litellm-79db46b9fc` running `main-v1.82.3-stable` (4 replicas)
- Canary: `litellm-8c7b9765f` running `main-v1.83.14-stable.patch.1` (1 replica)

**Pod placement:**
| Node | Stable (4) | Canary (1) |
|---|---|---|
| mini-1 | `wl8st` (11h) | — |
| mini-2 | `ffv4x` (11h) | — |
| mini-3 | `8l4qg` (11h) | `lztd7` (2m40s) |
| gpu-1 | — *(`8pdf7` evicted)* | — |
| pc-1 | `j2xq6` (11h) | — |

`8l4qg` survives again — 11 hours old now, third consecutive canary cycle. Co-located with the canary on mini-3. Per the pattern (T2 update further up), **`8l4qg` is the predicted termination target at the 50% scale-down** because it's the stable pod whose deletion best satisfies soft anti-affinity (the only stable+canary co-location is mini-3).

### Two ghost RSs this cycle, not one

Cluster RS list is now 9, not the 8 I predicted in pre-flight. Two RSs both with the v1.83.14-stable.patch.1 image:

- `litellm-7cdd47c49d` (0 replicas, never pods) — ghost
- `litellm-8c7b9765f` (1 replica, the actual canary) — active

Same chart-double-render pattern as the rehearsal. The broken `v1.83.14-stable` attempt left **no** RS behind because the ArgoCD sync never reached the Deployment-apply step (PreSync hook blocked the whole sync). So the two new RSs are entirely from the patched sync's transient template double-render.

### Cross-validation against T3's dual-probe expectations

T3 staged a dual-probe alternating `qwen3.5` (OLD) and `mistral-small-24b` (NEW). At the 20% pause the expected per-pod 4xx pattern is:

| Pod RS | qwen3.5 | mistral-small-24b |
|---|---|---|
| Stable (`79db46b9fc`, 4 pods) | 200 | 4xx (alias absent on v1.82.3) |
| Canary (`8c7b9765f`, 1 pod) | 4xx (alias removed in v1.83.14) | 200 |

Reasoning: each pod uses its own RS's ConfigMap version. v1.82.3-stable has the OLD model_list, v1.83.14 has the NEW one. The same Service routes ~20% of requests to canary, ~80% to stable. So at the LB, qwen3.5 should see ~80% 200 / 20% 4xx; mistral-small-24b should see ~20% 200 / 80% 4xx.

If T3's loop reports a different pattern, candidates:
- Both RSs read the same ConfigMap (model_list change leaked to both — a ConfigMap version-skew bug in the chart).
- 5xx instead of 4xx (real regression in v1.83.14, or LiteLLM upstream timeout, or cold-pull miss for a model alias).
- Per-alias 0% on either side (pod's `/health/readiness` is succeeding but the model_list is empty or malformed).

Standing by for the per-pod log analysis once T3's loop has produced enough samples — say after 60 seconds of dual-probe at ~1 req/sec.

### What I'm watching for in the rest of the cycle

- **50% scale-down**: prediction is `8l4qg` (mini-3) gets terminated, leaving the canary pod `lztd7` alone on mini-3. If a different stable pod gets evicted instead, that's a deviation from the pattern and worth understanding.
- **50% pause math**: expect 3 canary + 3 stable = 6 pods (surge of 1), same as rehearsal.
- **Final promote**: brief 5+1 → 5+0 transient, no analysis gating, then Healthy.
- **Per-node image pull on amd64**: 4 of the 5 nodes (mini-1, mini-2, gpu-1, pc-1) haven't pulled the patched image yet. Each canary pod scaling up at 50% / 100% will pay its own cold-pull. With 2 new pods at the 50% pause and 2 at the final promote, that's 4 cold pulls across the remaining cycle, parallelisable.

Bg logger active.

---

## Update — 50% pause + final Healthy captured. Important placement issue (06:14:17 → 06:20:37)

### 50% pause (06:14:17)

Pod placement, 6 pods total, 3+3 surge:

| Node | Stable (`79db46b9fc`) | Canary (`8c7b9765f`) |
|---|---|---|
| mini-1 | `wl8st` (12h) | `6bz8g` (4m5s) |
| mini-2 | `ffv4x` (12h) | `kch8v` (4m5s) |
| mini-3 | *(`8l4qg` evicted — 12h life ended)* | `lztd7` (16m) |
| gpu-1 | — | — |
| pc-1 | `j2xq6` (12h) | — |

Wall-clock from promote to 50% pause: **3m43s**. Two parallel amd64 cold-pulls on mini-1 and mini-2 (~3-4min each, parallel). Eviction prediction from earlier in this thread held: `8l4qg` was the soft-anti-affinity-violating stable pod (only stable+canary co-location at the 20% pause was on mini-3), and it's the one the controller chose for termination at the 50% scale-down.

`8l4qg` final lifecycle: born at PR 1.6's 20% pause boundary (~18:10:43 the previous local day), survived through PR 1.6's full canary cycle, PR #210's 20% pause, and was finally terminated at PR #210's 50% scale-down (~06:13). **Total uptime: ~12 hours, 5 pause boundaries crossed.** Pod-survival pattern from the rehearsal continues to hold.

### Anti-affinity termination pattern, refined

I had earlier said "the soft-anti-affinity-violating stable pod is the consistent termination target during canary scale-down." That's incomplete. Across all 5 scale-downs we've now observed:

| Cycle | Phase | Stable count change | Co-located stable+canary? | Pod terminated | Co-located? |
|---|---|---|---|---|---|
| PR 1.5 | 20% scale-down | 5→4 | mini-3 (`sjrhg`+`fksj6`) | gpu-1 (`gml26`) | NO |
| PR 1.6 | 20% scale-down | 5→4 | mini-3 (`sjrhg`+`8l4qg`) | mini-2 (`bqwn5`) | NO |
| PR 1.6 | 50% scale-down | 4→3 | mini-3 (`sjrhg`+`8l4qg`) | mini-3 (`sjrhg`) | YES |
| PR #210 | 20% scale-down | 5→4 | mini-3 (`8l4qg`+`lztd7`) | gpu-1 (`8pdf7`) | NO |
| PR #210 | 50% scale-down | 4→3 | mini-3 (`8l4qg`+`lztd7`) | mini-3 (`8l4qg`) | YES |

**Refined rule:** at 20% scale-down (5→4) the controller terminates a stable pod *NOT* co-located with the canary (preserves spread). At 50% scale-down (4→3) the controller terminates a stable pod *that IS* co-located with the canary (resolves the spread waste that's now relatively more expensive). This isn't a quirky heuristic — it's the K8s scheduler's default scoring re-evaluating the optimal anti-affinity satisfaction at each new total count. Worth a runbook line.

### Final promote (06:18:23 → 06:20:37) — Healthy at 100%, but with a real placement concern

| Time | RS state | Note |
|---|---|---|
| 06:18:24 | canary 5/3, stable 1/1 | 6-pod transient (canary already scaled, stable draining) |
| 06:20:20 | canary 5/4, stable 0 | Stable RS drained |
| 06:20:37 | canary 5/5, Healthy | All ready |

Wall-clock promote → Healthy: **2m14s**. But:

**🚨 One of the 2 new canary pods landed on `raspi-1` (Raspberry Pi 4, arm64).** Final pod placement:

| Node | Pod | Age | Hardware |
|---|---|---|---|
| mini-1 | `6bz8g` | 10m | Intel Ultra 5, 64GB |
| mini-2 | `kch8v` | 10m | Intel Ultra 5, 64GB |
| mini-3 | `lztd7` | 22m | Intel Ultra 5, 64GB |
| gpu-1 | `s6rxp` | 2m24s | i9, 128GB, RTX 5070 Ti |
| **raspi-1** | **`kpmkz`** | **2m24s** | **RPi 4, low-power ARM64** |

`pc-1` is now empty. raspi-1 is now serving ~20% of LiteLLM gateway traffic.

### Root cause: chart has no scheduling constraints

Inspected the canary pod's spec:

```
Resources:    {}                     # NO requests, NO limits
NodeSelector: (empty)
Affinity:     (empty)
Tolerations:  (only the default not-ready/unreachable)
```

All 7 nodes show `Ready / schedulable / no taints`. **There was nothing protecting LiteLLM from raspi-1.** Every prior amd64-only placement across the rehearsal and PR #210's earlier phases was scheduler luck, not configuration. Today, the dice rolled raspi-1.

This is a real chart misconfiguration. The rehearsal didn't catch it because the scheduler had been picking amd64 nodes by tiebreaker. PR #210's final promote happened to flip a tiebreaker the other way.

### What this means for the canary outcome

Two readings possible:

**Reading A — canary succeeded, surfaced a chart misconfiguration to fix.** The rollout reached Step 4/Healthy, all 5 pods are Ready, traffic is flowing on v1.83.14-stable.patch.1. The image bump worked, the model_list refresh is live, the migration applied cleanly. raspi-1 placement is a *latency* concern, not a *correctness* concern. Document, ship, fix the chart in a follow-up.

**Reading B — canary should be aborted, then re-fired with the chart fix.** raspi-1 placement degrades user-perceived latency for 20% of requests (RPi CPU + slower NIC + ARM library paths). For a deployment day where T1 is presenting "we successfully rolled out the new model lineup," having 20% of traffic on a Pi is a poor look. Operator can `kubectl argo rollouts abort litellm` to roll back to v1.82.3-stable, fix the chart, re-fire.

I lean A — the canary did what it was designed to do, and the placement issue is a different class of bug than v1.83.14's correctness. But the decision is the operator's.

### Recommended chart fix for the postmortem PR

```yaml
# apps/litellm/values.yaml
resources:
  requests:
    cpu: 200m
    memory: 512Mi
  limits:
    memory: 1Gi
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: kubernetes.io/arch
          operator: In
          values: [amd64]
    preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 100
      preference:
        matchExpressions:
        - key: node-role.kubernetes.io/control-plane
          operator: DoesNotExist  # prefer pc-1/gpu-1 over the control-plane minis
```

Resources numbers are guesses; need to calibrate from `kubectl top pod` during a normal-traffic window. The `node-role.kubernetes.io/control-plane: DoesNotExist` preference is debatable — it'd push pods to gpu-1/pc-1 only, which is more concentration than is healthy for a 5-replica gateway. Probably leave that out and just rely on the architecture filter.

### Cycle summary

| Stage | Wall time |
|---|---|
| Patched sync start → 20% pause | 9m29s (4m on raspi-1 migration + 5m on canary path) |
| 20% pause → operator promote | (operator-paced) |
| 20% promote → 50% pause | 3m43s (2 parallel amd64 cold-pulls) |
| 50% pause → operator promote | (operator-paced) |
| 50% promote → Healthy | 2m14s (2 parallel cold-pulls including raspi-1) |
| **Total observable canary work** | **~15m25s** plus operator pause budgets |

Adding the rehearsal's ~25 min and the broken-arm64 detour, the entire LiteLLM deploy-layer narrative is roughly 55 min of canary-cycle wall-clock plus several hours of pre-pull. Slow but learning-rich.

Bg logger can stop now (rollout is Healthy and stable). Will continue running idle.
