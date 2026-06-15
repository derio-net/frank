# Honest Health Probes for GPU-Time-Shared Layers (Inference + Media)

**Layer:** obs (fix/extension — grafana-alerting + blackbox-exporter)
**Status:** Draft
**Date:** 2026-06-15
**Related:** frank-ops#11 (Layer 11 Local Inference), frank-ops#16 (Layer 16 Media Generation)
**Supersedes behaviour of:** PR #550 (Layer 16 `replicas_unavailable` rule — folded into this design)

## Implementation Plans

| Plan | Target repo | Slug | Status |
|------|-------------|------|--------|
| 2026-06-15--obs--gpu-timeshare-health-probes | `derio-net/frank` | `2026-06-15--obs--gpu-timeshare-health-probes` | Deployed |

## Problem

The Derio Ops dashboard showed **all green** while local inference was **completely down**
cluster-wide. Root cause (diagnosed via systematic-debugging this session):

1. gpu-1 hosts the cluster's **only** GPU. A `gpu-switcher` hands it to **one** workload at a
   time — Ollama (Layer 11 inference) **or** ComfyUI (Layer 16 media). They are mutually
   exclusive: **exactly one of inference/media is ever live.**
2. Today the GPU was switched to ComfyUI (stoa video work; operator decision: ComfyUI keeps it
   indefinitely). Ollama scaled to `spec.replicas: 0`. The `ollama` ArgoCD App has
   `ignoreDifferences` on `/spec/replicas`, so it stays **Synced/Healthy with 0 pods**.
3. Every local LiteLLM model (all routing to `ollama.ollama.svc:11434` in
   `apps/litellm/values.yaml`) now returns **500** — Cilium socket-LB returns EPERM
   ("Operation not permitted") on a ClusterIP with **no endpoints**.
4. Visible symptom: `ai-alert-helper` App **Degraded** — its `digest` (08:00) and `surge-check`
   (*/15) CronJobs `curl -f` the helper → helper calls LiteLLM → 500 → `curl` exits 22 → Jobs
   Error. The helper Deployment itself is healthy. **The alerter is a victim of the same outage
   and cannot self-report.**

**Why the dashboard lied:** the `Layer 11 Local Inference Degraded` rule queries
`kube_pod_status_ready{namespace=~"ollama|litellm",condition="true"}` and fires if `< 1`. This is
a **per-pod** metric: **0 Ollama pods → 0 series → nothing `< 1` to fire on.** It can only catch
"a pod that exists but is NotReady," never "the pod was scaled away." `kube_deployment_status_
replicas_unavailable{ollama}` is **also** 0 (0 desired → 0 unavailable). LiteLLM emits **no**
Prometheus metrics (OSS — Enterprise-only). So local inference is **un-monitored end-to-end**.

The Layer 16 rule just shipped in #550 already moved past the per-pod trap (uses
`replicas_unavailable`), but it still only verifies "are desired replicas available" — **not**
"can ComfyUI actually generate." It stays green through the custom-node import failures seen in
today's stoa work.

## Goal

Make the ops board **tell the truth**: each GPU-time-shared layer's tile reflects whether that
workload can **actually do its job**, via end-to-end synthetic probes — without alert-fatigue
(one side is always down by design, so naive paging would be constant noise → muted → silent
again).

## Design

### 1. Two end-to-end synthetic probes (via existing blackbox-exporter)

`blackbox-exporter` (ns `monitoring`) already runs the blog/feature-health probes. Add **two
modules** to `apps/blackbox-exporter/manifests/configmap.yaml`:

- **`litellm_chat`** (Layer 11) — `prober: http`, `method: POST` to
  `http://litellm.litellm.svc.cluster.local:4000/v1/chat/completions`. Static JSON body: a
  trivial prompt against a **fast** Ollama-backed alias (`gemma-12b-nothin` — `think:false`,
  sub-second), `max_tokens` small. Auth via **`bearer_token_file`** (the LiteLLM master key, §4).
  `fail_if_body_not_matches_regexp: ['"choices"']` so a real completion is required (a 500
  or an error body fails the probe). `valid_status_codes: [200]`.
- **`comfyui_object_info`** (Layer 16) — `prober: http`, GET
  `http://comfyui.comfyui.svc.cluster.local:8188/object_info`, `valid_status_codes: [200]`,
  `fail_if_body_not_matches_regexp: ['KSampler']` — asserts a known core node is loaded, so the
  probe catches **custom-node import failures** (today's stoa node breakage), not just liveness.
  GET, no auth (in-cluster service is plain; SSO is ingress-only).

Two **VMProbe** CRs in `apps/blackbox-exporter/manifests/vmprobe.yaml`, each labelled
`probe_group: gpu_timeshare` + `layer: "11"` / `layer: "16"`, scraped into VictoriaMetrics as
`probe_success{layer="11"|"16"}`.

> **Why API-liveness not full generation for Layer 16** (operator decision): a real generation
> burns GPU time, queues behind live jobs, and false-fails under load. `/object_info` proves the
> server is up **and** nodes imported — cheap, fast, catches the real failure mode.

### 2. Alert rules (rewrite Layer 11 + Layer 16, add a combined paging rule)

In `apps/grafana-alerting/manifests/alert-rules-cm.yaml`:

- **Layer 11** — replace the `kube_pod_status_ready` query with `probe_success{layer="11"}`;
  threshold fires when `< 1`. **Quiet** (tile-only): labels `gpu_timeshare: "true"`,
  `github_issue: "frank-ops#11"`, `severity: warning`. `noDataState: Alerting` (absence of the
  probe series = probe broken = NOT healthy — the opposite of the old `noDataState: OK` trap).
- **Layer 16** — same shape, `probe_success{layer="16"}`, `gpu_timeshare: "true"`,
  `github_issue: "frank-ops#16"`. Replaces the #550 `replicas_unavailable` query.
- **NEW `gpu-node-both-down`** (paging) — fires when **both** probes are down:
  `sum(probe_success{probe_group="gpu_timeshare"}) < 1` (Grafana threshold `lt 1`, the idiom used
  by every other rule in the file; neither inference nor media works →
  gpu-1/driver dead, or both scaled to 0, or switcher stuck mid-transition). Labels
  `severity: critical`, `github_issue: "frank-ops#5"` (GPU layer), **no** `gpu_timeshare` label
  → routes normally → **pages Telegram + health-bridge files a bug.** `for: 10m` to ride out the
  brief both-down window during a legitimate GPU switch-over.

> **noData handling:** the quiet rules use `noDataState: Alerting` so a vanished probe series reads
> as down (degraded tile), never as the old silent `OK`. The combined rule must tolerate the
> switch-over gap via `for: 10m` so a normal GPU hand-off doesn't page.
>
> **Absent-series caveat (combined rule):** `sum(probe_success{...})` silently **skips absent
> series** — if the inference series is missing (not 0) and media=1, `sum=1` and both-down won't
> fire (correct: media works). But if **both** series vanish (blackbox/VMProbe itself broken),
> `sum` yields no series → NoData. That is monitoring-blindness, not a confirmed GPU death, so the
> combined paging rule sets **`noDataState: OK`** (do **not** page on a scrape gap — health-bridge
> philosophy: blindness ≠ death). A vanished-probe watchdog (`absent()`) is **out of scope** here;
> note it as a follow-up. The quiet per-layer rules already surface a vanished series as a degraded
> tile via their `noDataState: Alerting`, so total-probe-outage is still *visible*, just not paged.

### 3. Honest-but-quiet routing (no Telegram for the expected-down side)

The `feature-health` → Health Bridge route is **last**; the `severity=warning|critical` → Telegram
routes precede it with `continue: true`. So a feature-health alert carrying `severity` **would
page**. To keep the time-share tiles **visible but quiet**, add an **early `continue: false`
route** (mirroring the load-bearing cert-canary watchdog ordering) to
`apps/grafana-alerting/manifests/notification-policy-cm.yaml`, **before** the severity routes:

```yaml
# GPU time-share tiles (Layers 11/16): exactly one is always down by design.
# Route to health-bridge ONLY (degraded tile, no page) — the gpu-node-both-down
# rule (severity=critical, no gpu_timeshare label) handles the genuine fault.
# ORDER IS LOAD-BEARING: must precede the severity routes (continue:true→Telegram).
- receiver: "Health Bridge Webhook"
  matchers:
    - gpu_timeshare="true"
  continue: false
```

**Tile state, no bug issue:** the quiet alerts carry `severity: warning` (not `critical`), which
health-bridge maps to **degraded** — visible on the board, **no** never-closing bug issue (per
health-bridge v0.4.0+ "blindness ≠ death": only `dead`/critical mints a bug). `github_issue:
frank-ops#11|#16` keys the correct tile (feature-ref). When the GPU is handed back, the probe
passes, the alert resolves, and the tile **auto-greens** (health-bridge heal-by-feature-ref).
**No health-bridge code change — pure routing + labels, single-repo (frank).**

### 4. Probe key — the LiteLLM master key (no manual step)

The probe authenticates with the existing LiteLLM **master key** (operator decision — chosen over a
dedicated virtual key to avoid an out-of-band mint). `LITELLM_MASTER_KEY` already lives in Infisical
(the litellm app's `external-secret.yaml` reads the same key), so the flow is **fully declarative**:

1. New `ExternalSecret` (ns `monitoring`, `external-secret-litellm-key.yaml`) syncs Infisical
   `LITELLM_MASTER_KEY` → Secret `litellm-master-key`, reusing the existing ESO/Infisical pattern.
2. Mounted into the blackbox-exporter Deployment at `/etc/blackbox-secrets/litellm-master-key` as
   **`optional: true`** — so blackbox-exporter (which runs the **blog uptime probe**) still starts
   if the secret is ever briefly unsynced; only the `litellm_chat` probe would fail auth in that
   window. **No manual phase** — the key already exists, so ESO syncs it on deploy.

**Trade-off:** the probe carries full LiteLLM admin privilege. Accepted for simplicity — it is
read-only in practice (one chat completion), namespace-scoped to `monitoring`, and mounted
read-only. A future least-privilege follow-up could swap in a dedicated virtual key.

## Truth table (what the board shows)

| GPU owner | inference probe | media probe | L11 tile | L16 tile | Telegram |
|-----------|-----------------|-------------|----------|----------|----------|
| Ollama    | pass            | fail        | green    | degraded | silent   |
| ComfyUI   | fail            | pass        | degraded | green    | silent   |
| neither (fault) | fail      | fail        | degraded | degraded | **PAGE** (both-down) |

## Scope / non-goals

- **In scope (frank only):** 2 blackbox modules, 2 VMProbes, ESO + optional mount, rewrite L11 +
  L16 rules, add `gpu-node-both-down` rule, add quiet route, gotcha docs.
- **Non-goals:** no health-bridge code change; no full ComfyUI generation probe; no change to the
  gpu-switcher; not re-enabling Ollama (operator keeps the GPU on ComfyUI).

## Testing

- **Static:** `blackbox_exporter --config.check` on the new modules; yaml-lint + the repo's
  alert-rule / plan validators; assert the combined-rule PromQL (`sum(...) == 0`) logic.
- **Post-merge Test Plan (operator-driven — live GPU-switch flip):**
  1. After merge + ArgoCD sync + operator mints the probe key: current state (ComfyUI owns GPU) →
     **media tile green, inference tile degraded, NO Telegram.**
  2. Confirm `probe_success{layer="11"}=0`, `{layer="16"}=1` in VMUI.
  3. Operator flips the GPU to Ollama (scale ComfyUI→0 / Ollama→1) → tiles **swap**, still no page.
  4. Force both-down (briefly) or trust the `for:10m` reasoning → confirm `gpu-node-both-down`
     would page (synthetic webhook replay acceptable for the both-down leg).

## Documentation

- One-liner in `agents/rules/frank-gotchas.md` (Grafana section) + full prose in
  `docs/runbooks/frank-gotchas/grafana.md`: "GPU-switch to ComfyUI silently kills all
  Ollama-backed LiteLLM models; `kube_pod_status_ready` is blind to scale-to-0
  (`replicas_unavailable` too — 0 desired); use the blackbox end-to-end completion/`object_info`
  probes; honest-but-quiet `gpu_timeshare` route = degraded tile, no page; `gpu-node-both-down`
  is the only paging rule."
- Retroactively update the operating post for inference/media health if probe commands change
  (VMUI queries). No new blog post (fix/extension).
