# LiteLLM Canary Observation Runbook

Operational reference for observing and driving an Argo Rollouts canary deployment of the LiteLLM gateway. Reusable for any future LiteLLM image bump or model-list change that flows through the canary pipeline.

## History

This runbook is the **third draft**.

- **First draft** assumed a Cilium L7 traffic-router plugin (`rollouts-plugin-trafficrouter-cilium`) that turned out to never have been published as a release artifact. The Argo Rollouts controller failed to load the plugin on every reconciliation; the litellm `Rollout` sat stuck at Step 0/6 for 39 days while the Helm-managed `Deployment` quietly served traffic on its own.
- **Second draft** rewrote around a replica-count canary with metric-gated `AnalysisRun` between each `setWeight`. The metric query referenced `litellm_request_total` from VictoriaMetrics — but that metric does not exist on this cluster (LiteLLM's Prometheus integration is an Enterprise-paid feature, the OSS image we run does not emit it, no scrape config either). On the first end-to-end rehearsal the AnalysisRun panicked with `reflect: slice index out of range` on an empty result vector and the controller correctly fail-closed-aborted the canary.
- **Third draft (this one)** is pause-only: no `AnalysisRun` between pauses, fully manual gating at each step. Operator is the AnalysisRun. Restoring metric-gated promotion is brainstormed in `docs/superpowers/specs/2026-05-04--deploy--litellm-canary-metric-source-design.md` (Path B).

The full self-deception postmortem — five latent bugs in the deploy layer discovered during one cascade — is in `building/19-progressive-delivery` (Update: 2026-05-04 section).

## When to use this runbook

Any time `apps/litellm/values.yaml` changes in a way that triggers a Rollout — most commonly an `image.tag` bump, but also any change the Helm chart projects into the Deployment's pod template (env vars, resources, labels). Pure ConfigMap changes (model_list edits without a chart-template touch) update the CM in place and do **not** trigger a canary.

## What's wired up

```
                   ┌────────────────────────────────────────────┐
                   │ ArgoCD Application: litellm                │
                   │   targetRevision: <chart>                  │
                   │   helm.valueFiles: apps/litellm/values.yaml│
                   └───────────────────┬────────────────────────┘
                                       │ syncs
                                       ▼
   ┌────────────────────┐    ┌──────────────────────────┐
   │ Deployment/litellm │←───│ workloadRef               │
   │  replicas: 0       │    │ Rollout/litellm           │
   │  (managed by RO,   │    │  replicas: 5              │
   │   scaleDown:       │    │  scaleDown: onsuccess     │
   │   onsuccess)       │    │  strategy: canary         │
   └────────────────────┘    │  steps:                   │
                             │   20% (1/5) → pause       │
                             │   50% (3/5) → pause       │
                             │   100% (5/5)              │
                             └────────────┬──────────────┘
                                          │
                                          ▼
                              ┌──────────────────────┐
                              │ Service: litellm     │
                              │ (LB 192.168.55.206)  │
                              │ selector: name=litellm│
                              │ → ALL pods (stable + │
                              │    canary), weighted │
                              │    by pod count       │
                              └──────────────────────┘
```

The Argo Rollouts controller scales the Helm chart's `Deployment` to `replicas: 0` (via `workloadRef.scaleDown: onsuccess`) and runs its own ReplicaSets via `workloadRef`. ArgoCD has `ignoreDifferences` on `apps/Deployment/spec.replicas` so it doesn't fight the controller. Don't be alarmed by `Deployment.spec.replicas: 0` — that's correct.

The traffic split is implemented by **standard Service endpoint selection**: the chart's `Service/litellm` selects pods labeled `app.kubernetes.io/{name,instance}=litellm`, both stable and canary pods carry those labels (inherited from the Deployment template), and kube-proxy/Cilium round-robin across the union. There is no `CiliumEnvoyConfig`, no L7 weighting, no separate canary Service.

**There is no metric-gated promotion.** Each pause is indefinite — the rollout sits at `Status: Paused` until the operator runs `kubectl argo rollouts promote litellm -n litellm`. There's no NaN-abort risk because there's no AnalysisRun. The `apps/litellm/manifests/analysis-template.yaml` file is left in place as a scaffold for when Path B (metric-source replacement) lands.

## Pre-flight

```bash
cd /Users/derio/Docs/projects/DERIO_NET/frank
source .env

# 1. Argo Rollouts kubectl plugin is installed
kubectl argo rollouts version || \
  echo "Install: brew install argoproj/tap/kubectl-argo-rollouts"

# 2. Snapshot of current state (so you have before/after).
#    Expected: Status=Healthy, 5/5 pods Ready, all on the current image-tag hash.
kubectl argo rollouts get rollout litellm -n litellm
```

A healthy at-rest snapshot looks like this (real capture, 2026-05-04 17:54):

```
Name:            litellm
Namespace:       litellm
Status:          ✔ Healthy
Strategy:        Canary
  Step:          4/4
  SetWeight:     100
  ActualWeight:  100
Images:          ghcr.io/berriai/litellm-database:main-v1.82.3-stable (stable)
Replicas:
  Desired:       5
  Current:       5
  Updated:       5
  Ready:         5
  Available:     5

NAME                                 KIND        STATUS        AGE  INFO
⟳ litellm                            Rollout     ✔ Healthy
└──# revision:N
   ├──⧉ litellm-<hash-current>       ReplicaSet  ✔ Healthy          stable
   │  ├──□ litellm-<hash-current>-*  Pod         ✔ Running          ready:1/1
   │  └──[5 pods total, one per node — mini-1, mini-2, mini-3, gpu-1, pc-1]
   └──⧉ litellm-<hash-prev>          ReplicaSet  • ScaledDown
```

The previous-revision RS may linger as `ScaledDown` for a while — that's fine. It's GC'd eventually.

```bash
# 3. LITELLM_MASTER_KEY is in your env (needed for /v1/* requests)
echo "${LITELLM_MASTER_KEY:?not set}" | head -c 8 ; echo "…"

# 4. Note the current ReplicaSet hash so you can spot the new (canary) RS later
kubectl get rs -n litellm -l app.kubernetes.io/name=litellm \
  --sort-by=.metadata.creationTimestamp -o wide | tail -3
```

## Trigger the rollout

The canary fires when the change reaches the cluster:

```bash
# Either: merge a PR to main and let auto-sync poll it (~3min)
# Or: force-sync immediately after merge (note the explicit syncOptions —
# manual syncs do NOT inherit them, per frank-gotchas.md):
kubectl patch application litellm -n argocd --type=merge -p \
  '{"operation":{"sync":{"revision":"HEAD","syncOptions":["ServerSideApply=true","RespectIgnoreDifferences=true"]}}}'
```

The chart sync runs the litellm-migrations PreSync hook before applying the new Deployment. **Plan for 4–8 minutes of pre-canary wait** if the migrations Job lands on raspi-1 and the prisma-migrations image isn't cached on it (~714MB ARM image, cold pull). Once cached, ~3-4 minutes per subsequent canary. Worth a future improvement: pin the Job to amd64 nodes (see Path B spec for the adjacent-improvements list).

## Three-terminal observation

### Terminal 1 — The rollout pipeline (your primary dashboard)

```bash
kubectl argo rollouts get rollout litellm -n litellm --watch
```

Steps render as they execute: green check (done), hourglass (paused). When you see `Status: Paused, Message: CanaryPauseStep`, the canary is at the indicated weight (1/5 = 20% first, then 3/5 + 3/5 stable = 50% with maxSurge transient overcap) and waiting on you. The ArgoCD UI shows the Rollout as `Healthy`/`Progressing` but does **not** render the canary step state — this view is the source of truth.

### Terminal 2 — Pod distribution & ReplicaSet split

```bash
# Live view of which pods belong to which RS (stable vs canary).
# The "rollouts-pod-template-hash" label distinguishes the two RSes.
watch -n 2 'kubectl get pods -n litellm -l app.kubernetes.io/name=litellm \
  -L rollouts-pod-template-hash -o wide'

# One-shot inspection of ReplicaSet replica counts (filter zero-count old RSes):
kubectl get rs -n litellm -l app.kubernetes.io/name=litellm --no-headers | awk '$2!="0"'
```

Expected progression (real capture from 2026-05-04 17:53):

| State | Step | Canary RS | Stable RS | Total | ActualWeight |
|---|---|---|---|---|---|
| Pre-canary | n/a (Healthy) | — | 5 pods | 5 | n/a |
| Paused after setWeight 20 | 1/4 | 1 pod (e.g. mini-3) | 4 pods | 5 | 20 |
| Promote → setWeight 50 (mid-state) | 3/4 | 3 pods | 3 pods | **6** | 50 |
| Promote → 100% | 4/4 | 5 pods | 0 (ScaledDown) | 5 | 100 |

**Yes, the mid-state at SetWeight 50 has 6 pods**, not 5. Argo Rollouts' default `maxSurge: 25%` (= 2 with replicas=5) brings up the canary RS *before* scaling stable down. `ActualWeight: 50` is computed as `canary_count / total_count` (3/6 = 50%), not `canary_count / desired_replicas`. This is the property that makes the canary "no traffic loss" — every promote-step's first action is to bring up new pods. The 3rd `setWeight: 50` step only fully realizes as 3+2=5 *after* the operator promotes past this pause.

**Anti-affinity termination pattern across scale-downs.** Documented across 5 scale-downs (PR 1.5/1.6/210, both 20% and 50% boundaries):

- At the **20% scale-down** (5 → 4 stable), the controller terminates a stable pod *NOT* co-located with the canary (preserves spread across nodes).
- At the **50% scale-down** (4 → 3 stable, mid-promote-to-50), the controller terminates a stable pod *that IS* co-located with the canary (resolves the spread waste that's relatively more expensive at this density).

This isn't a quirky heuristic — it's the kube-scheduler's default anti-affinity scoring re-evaluating the optimal placement at each new total replica count. Same node hosts both a stable and a canary pod for the duration of the 20% pause; that co-tenant pod becomes the termination target at the next promote. Useful predictor when reading `kubectl get pods` mid-canary: **the stable pod sharing a node with the canary is the one that will get evicted next.**

**Pod-survival pattern under repeated canary cycles.** A stable pod can survive multiple consecutive canary cycles if it's never the soft-anti-affinity violator at the moment of scale-down. T2 documented one pod (`8l4qg`) surviving ~12 hours and 5 pause boundaries across PRs 1.6, 1.6-revert, and 210 before finally being terminated at PR #210's 50% scale-down. Worth knowing if you're relying on pod ages as proxies for "freshly promoted state" — they may be older than the most recent canary.

### Terminal 3 — Synthetic traffic (optional in pause-only mode)

The current pause-only canary doesn't run AnalysisRuns, so there's no NaN-abort risk to defend against. A traffic loop is **not required** to keep the rollout from failing. It IS still useful for:

- Bake-testing the canary by watching consumer-facing behavior live
- Catching obvious regressions (5xx spikes, latency anomalies) the operator can eyeball
- Confirming Service distribution is hitting both RSes (per-pod log inspection)

If you want it, **probe a single local-Ollama alias whose rejection path on the canary RS is gateway-level (alias-absent in the new model_list), not Ollama-level.** Pick an alias that exists in the *current-stable* model_list and is *removed* in the *canary's* model_list — the stable RS resolves it (200 from VRAM-loaded model), the canary RS rejects it at LiteLLM before ever touching Ollama (4xx from the gateway). The 200/4xx ratio across the loop becomes a clean routing-split signal for free, no thrashing.

```bash
# Substitute the alias for whichever one is being REMOVED in this canary's
# model_list change. For PR #210 the right pick was qwen3.5; for future
# bumps, look at the diff against current main's apps/litellm/values.yaml.
while true; do
  curl -s -o /dev/null -w "%{http_code} " \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"qwen3.5","messages":[{"role":"user","content":"hi"}],"max_tokens":5}' \
    http://192.168.55.206:4000/v1/chat/completions
  sleep 1
done
# Ctrl-C when the rollout reaches 100% / Healthy.
```

> **DO NOT alternate between two local-Ollama aliases.** This was Terminal #3's failed dual-probe in the PR #210 cascade. Ollama on gpu-1 runs with `OLLAMA_MAX_LOADED_MODELS=1` (16GB RTX 5070 Ti can only hold one model in VRAM at a time). Alternating between two local models forces VRAM swap on every alternation — ~10-30s per swap, well past curl's 8s default timeout — and **the probe becomes its own failure mode**. Multi-model rotation across local aliases is unsafe with `MAX_LOADED_MODELS=1`.

> **Single-model + gateway-level rejection is the safe shape.** The 4xx-path on the canary RS doesn't touch the GPU at all; it's a pure ConfigMap/router decision. Zero VRAM pressure from canary-routed requests. The 200/4xx ratio IS the routing split, exactly. T3's PR #210 final tally on a single-model `qwen3.5` loop: 856 samples / 0 ERRs / clean 80-20 → 50-50 → 0-100 progression across the canary phases — a more reliable signal than any multi-model rotation can be.

> **Multi-model rotation across CLOUD aliases is fine** — those don't share VRAM, they share OpenRouter quota. The hazard is rate-limiting (HTTP 429 once free-tier daily/hourly quota is hit), not VRAM swap. If you want broader bake-test coverage, rotate across cloud aliases instead. Trade-off: `:free` quotas are tight, so a 1 req/sec loop on multiple cloud aliases will exhaust quota in minutes.

If you want to bake-test the canary in isolation (probe only canary pods, not the union), target via pod IP rather than the Service:

```bash
# Find a canary pod IP
CANARY_HASH=$(kubectl get rollout litellm -n litellm -o jsonpath='{.status.currentPodHash}')
kubectl get pod -n litellm -l rollouts-pod-template-hash=$CANARY_HASH -o wide
# Curl any of those pod IPs directly:
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  http://<canary-pod-ip>:4000/v1/models | python3 -m json.tool
```

## Promote past each pause

```bash
# When you're satisfied with what you see at the current weight:
kubectl argo rollouts promote litellm -n litellm
```

Full happy-path interaction (2026-05-04 timing as reference):

1. **Rollout fires** within ~3 min of merge (after PreSync hook). 1 canary pod up at 20%.
2. **(Pause at Step 1/4)** — you observe, then `promote`. Controller advances toward setWeight 50.
3. **2 new canary pods come up** (~25–60s if image is cached on target nodes; longer for cold pulls). Mid-state of 6 pods (3 canary + 3 stable, maxSurge transient).
4. **(Pause at Step 3/4)** — you observe, then `promote`. Controller advances toward 100%.
5. **2 more canary pods come up + old stable pods scale to 0.** ~30s if cached.
6. **`Status: Healthy`, Step 4/4**. Old RS at `• ScaledDown 0`. New RS labeled `stable`. Deployment.spec.replicas=0 maintained by `scaleDown: onsuccess`.

Image-cache effect: the *first* canary on a fresh image takes ~7 minutes per node for cold pulls. Subsequent canaries (same image, image already cached on the cluster) complete in under a minute. Path B spec captures this as a runbook nuance.

## Verify the new model list end-to-end

While the canary is running (or after it settles), confirm each alias resolves. **Update this list whenever the model lineup changes.**

```bash
for model in qwen3.5 deepseek-coder omnicoder qwen3-coder hermes-405b gemma-27b mistral-small llama-70b step-flash; do
  printf "%-22s " "$model"
  curl -s http://192.168.55.206:4000/v1/chat/completions \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with one word.\"}],\"max_tokens\":10}" \
    | python3 -c "import json,sys; r=json.load(sys.stdin); print(r.get('choices',[{}])[0].get('message',{}).get('content','') or 'ERR: '+str(r.get('error',{}).get('message','UNKNOWN')))"
done
```

> Local Ollama models trigger a first-time pull on the initial request (~30–120s per model, may exceed LiteLLM's default upstream timeout). Pre-pull each tag manually before the verification loop:
>
> ```bash
> kubectl exec -n ollama deploy/ollama -- ollama list
> kubectl exec -n ollama deploy/ollama -- ollama pull <tag>  # for any missing
> ```

## If something goes wrong

```bash
# Pause in place — no further auto-progression (also useful for inspecting state)
kubectl argo rollouts pause litellm -n litellm

# Abort and roll back to the stable ReplicaSet
kubectl argo rollouts abort litellm -n litellm

# Inspect any AnalysisRuns (should be none in the pause-only design, but old
# ones from past rehearsals may linger as ⚠ in the tree until RS is GC'd)
kubectl get analysisrun -n litellm
kubectl describe analysisrun -n litellm <name> | grep -A 10 Phase

# If you want to retry without aborting:
kubectl argo rollouts retry rollout litellm -n litellm
```

`abort` scales the canary RS down to 0 and routes 100% of traffic back to the previous stable RS. The rollout will not auto-retry — you need to either push a new commit (which restarts the pipeline) or `retry` after fixing whatever was wrong.

**Note on "retry":** Argo Rollouts treats a Rollout-spec change as an *implicit* retry when the previous state was Degraded. So if you fixed the issue via a commit that touches the Rollout spec (vs the Deployment template), the controller will re-attempt the canary on the new spec without you having to call `retry` explicitly.

## Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Pre-flight shows `Status: Progressing` with `Step: 0/4-or-0/6, ActualWeight: 0, Desired: 1, Current: 0` | The Rollout still references a missing `trafficRouting` plugin (regression of the original 39-day bug) | `kubectl get rollout litellm -n litellm -o yaml \| grep -A 3 trafficRouting` — should return nothing. If it returns `argoproj-labs/cilium`, the manifest has been reverted. Restore `apps/litellm/manifests/rollout.yaml` to the replica-count form. |
| Canary aborts with `Metric "error-rate" assessed Error due to consecutiveErrors > consecutiveErrorLimit: "reflect: slice index out of range"` | The Rollout has been reverted to the metric-gated design (with `analysis: { templates: [litellm-error-rate] }` steps), but `litellm_request_total` doesn't exist in VictoriaMetrics. The AR Prometheus provider panics on the empty result vector. **Argo Rollouts retries Error at 10s cadence (not 1m), so the abort budget is ~50 seconds of zero metric data, not 5 minutes.** | Either remove the `analysis` step from the Rollout (current pause-only design), or implement Path B (real metric source) per `docs/superpowers/specs/2026-05-04--deploy--litellm-canary-metric-source-design.md` |
| Pod count split doesn't match `setWeight` (e.g. 2 canary + 3 stable at 20%) | `replicas` in the Rollout was changed away from 5 — Argo Rollouts rounds `ceil(replicas × weight/100)` | Restore `replicas: 5` in `apps/litellm/manifests/rollout.yaml`, or accept the rounded distribution if you bumped intentionally |
| At setWeight 50 you see 6 pods (3 canary + 3 stable), not 5 | Default `maxSurge: 25%` brings canary up before scaling stable down. Expected behavior — every pause is over-provisioned. | Not a fix; runbook nuance. ActualWeight is `canary/total` so `3/6 = 50` is correct. |
| `kubectl argo rollouts get` shows a stale `⚠ AnalysisRun` from a previous canary | AnalysisRun objects persist across canary cycles, only GC'd when the RS itself is. The `⚠` count is from a *prior* aborted attempt, not the current one. | Cosmetic; ignore. To clean: `kubectl delete analysisrun -n litellm <old-name>` after the current rollout completes. |
| Canary pod stuck `ContainerCreating` | New image tag doesn't exist on GHCR | Verify `repository:tag` resolves: `crane manifest ghcr.io/berriai/litellm-database:<tag>` |
| Migration Job (PreSync hook) takes 7+ minutes | Cold image pull (raspi-1, 714MB ARM image, no cache) | Wait it out the first time; subsequent canaries are 3–4 min. Future fix: pin Job to amd64 nodes (see Path B spec). |
| `kubectl argo rollouts get` hangs / returns stale state | Running on macOS with port-forward flake to gpu-1 | LiteLLM is not on gpu-1 — but if pods migrated, the gpu-1 port-forward gotcha applies; run the command from a control-plane shell instead |
| Promote runs but rollout stays at the same weight | `promote` was called when not at a Pause step | Wait for `Status: Paused`; `promote` only advances *out of* a manual pause |
| Old stable RS appears to "linger" briefly after Healthy is reached | The `Healthy` flag is computed from the new RS being Available, not from the old RS being fully gone. Old RS scale-down completes seconds after Healthy lights up. | Not a fix; runbook nuance. |

## Post-canary cleanup

For LiteLLM model-list refreshes (e.g. PR #210), remove obsolete Ollama models from the running pod's PVC:

```bash
kubectl exec -n ollama deploy/ollama -- ollama list
# Remove tags no longer in the LiteLLM model_list:
for tag in <obsolete-tags>; do
  kubectl exec -n ollama deploy/ollama -- ollama rm "$tag" || true
done
```

`ollama rm` is safe to run for a tag that doesn't exist (returns non-zero, no destructive effect).

## See also

- [Argo Rollouts spec](../../apps/litellm/manifests/rollout.yaml) — the pause-only Rollout
- [AnalysisTemplate (orphaned scaffold)](../../apps/litellm/manifests/analysis-template.yaml) — kept for when Path B lands
- [Path B design spec](../superpowers/specs/2026-05-04--deploy--litellm-canary-metric-source-design.md) — restoring metric-gated promotion (Hubble L7, sidecar exporter, web provider)
- [Operating: Progressive Delivery](../../blog/content/docs/operating/12-progressive-delivery/index.md) — day-to-day rollout commands across litellm + sympozium
- [Building: Progressive Delivery](../../blog/content/docs/building/19-progressive-delivery/index.md) — architecture, deployment narrative, **and the 2026-05-04 self-deception postmortem**
- [Operating: Local Inference](../../blog/content/docs/operating/07-inference/index.md) — day-to-day Ollama + LiteLLM operations
- [Building: Local Inference](../../blog/content/docs/building/10-local-inference/index.md) — architecture and deployment narrative
