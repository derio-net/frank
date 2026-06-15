# Honest Health Probes for GPU-Time-Shared Layers

**Status:** Planned
**Spec:** `docs/superpowers/specs/2026-06-15--obs--inference-media-honest-health-probes-design.md`
**Layer:** obs (fix/extension — grafana-alerting + blackbox-exporter)

## Why

The Derio Ops board showed **all green** while local inference was **down cluster-wide**. gpu-1
time-shares its single GPU between Ollama (Layer 11) and ComfyUI (Layer 16) — exactly one is ever
live. Today the GPU went to ComfyUI; Ollama scaled to 0; every Ollama-backed LiteLLM model began
returning 500; `ai-alert-helper` went Degraded (its cron probes `curl -f` the helper → LiteLLM
500 → exit 22). The board stayed green because the Layer 11 rule queried the **per-pod**
`kube_pod_status_ready` — 0 pods → 0 series → nothing to fire on. The alerter that should have
warned us is itself a victim of the outage.

## What

Replace pod-existence health signals with **end-to-end synthetic probes** (via the existing
blackbox-exporter), so each tile reflects whether the workload can actually do its job:

- **Layer 11** — real `POST /v1/chat/completions` through LiteLLM (fast `gemma-12b-nothin` alias),
  asserting a completion comes back.
- **Layer 16** — `GET /object_info` on ComfyUI, asserting a core node (`KSampler`) is loaded
  (catches custom-node import failures, not just liveness).

Because one side is **always** down by design, the per-layer tiles are **honest-but-quiet**:
routed to health-bridge (degraded tile, auto-greens on recovery) but **never to Telegram**. The
only pager is a new **`gpu-node-both-down`** rule — both probes down means gpu-1/driver is
genuinely broken or the switcher is stuck.

## Truth table

| GPU owner | L11 probe | L16 probe | L11 tile | L16 tile | Telegram |
|-----------|-----------|-----------|----------|----------|----------|
| Ollama    | pass | fail | green | degraded | silent |
| ComfyUI   | fail | pass | degraded | green | silent |
| neither   | fail | fail | degraded | degraded | **PAGE** |

## Phase map

1. **Blackbox modules** — `litellm_chat` + `comfyui_object_info` (TDD via `--config.check`).
2. **Probe key** — ESO ExternalSecret + **optional** mount (blog probe must not break pre-key).
3. **VMProbes** — inference + media, `probe_group: gpu_timeshare`, `layer` labels.
4. **Alert rules** — rewrite L11 + L16 to `probe_success`; add `gpu-node-both-down` (TDD).
5. **Quiet route** — `gpu_timeshare="true"` → Health Bridge only, before the severity routes.
6. **Docs** — gotcha one-liner + full prose; operating touch-up.
7. **Post-Deploy Checklist** — fix/extension scope (most steps skip).
8. **[manual]** — operator mints the LiteLLM probe virtual key + Infisical (back-loaded; nothing
   agentic depends on it because the key mount is `optional:true`).

## Post-merge Test Plan (operator-driven — live GPU-switch flip)

1. After merge + sync + key mint: with ComfyUI holding the GPU → **media green, inference
   degraded, NO Telegram**; confirm `probe_success{layer="11"}=0`, `{layer="16"}=1` in VMUI.
2. Operator flips the GPU to Ollama → tiles **swap**, still no page.
3. `gpu-node-both-down` paging leg verified by synthetic webhook replay (or a brief real
   both-down), respecting `for: 10m`.

## Non-goals

No health-bridge code change (pure routing + labels); no full ComfyUI generation probe; no
gpu-switcher change; Ollama is **not** re-enabled (operator keeps the GPU on ComfyUI).
