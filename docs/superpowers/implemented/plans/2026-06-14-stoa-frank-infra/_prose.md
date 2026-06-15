# Stoa Frank Infra — Plan

Land the two additive Frank infrastructure changes that satisfy
`agentic-stoa/content-factory#55` (stoa-pipeline Phase 2 contract):
ComfyUI stoa enablement on `gpu-1`, and a persistent, operator-attachable
`claude` session sidecar on `n8n-01`.

**Spec:** `docs/superpowers/specs/2026-06-14-stoa-frank-infra-design.md`

## Strategy

**EXTEND, not BUILD-NEW.** The substrate already exists (operator-directed
investigation of `agent-images` and `runs-fr` confirmed it):

- ComfyUI's native API (`POST /prompt`, `GET /history/{id}`, `GET /view`)
  already matches the contract shapes — Component 1 is pure provisioning
  (custom nodes baked into the image, weights via a download Job, VRAM flags,
  an Authentik-gated Traefik route). No API shim.
- The `multi-agent-shell` image (the k8s-native-runs design's **L1** layer)
  carries `claude` + tmux + sshd. The persistent-session interface is the
  design's already-blessed **`tmux send-keys` → `capture-pane`** pattern
  (never `claude -p`); the stoa driver is a thin script over it + a turn
  counter. Operator-attach is SSH/`kubectl exec` + `tmux attach` (the
  `runs-fr` browser gateway is the future path — not yet deployed).

## TDD posture for GitOps

The deterministic artifacts are unit-tested in `scripts/tests/` (pytest,
the repo's `dev`-profile check) — `pyyaml` assertions over manifests, a
**tag-consistency guard** (deployment image tag == the tag the build
workflow renders, closing the health-bridge tag-drift hole), and the real
centerpiece: the **agent-session driver** tested against the vendored
contract fixtures with `tmux` mocked (turn-counter persistence, exact
`{session_id, agent, status, turn, payload}` output). Generative quality is
NOT unit-asserted — that is measured at the live `[manual]` gates.

## Phase map

```text
1 ComfyUI image + model-Job ──► 2 ComfyUI VRAM + route + tile ─┐
3 n8n sidecar + tmux session ──► 4 agent-session driver ───────┴─► 5 [manual] verify + writeback
```

Phases 1→2 (ComfyUI) and 3→4 (agent session) are two independent agentic
tracks (parallel-able roots); the `[manual]` phase 5 fans in from both.

## Manual is back-loaded (fr-goal placement policy)

Every cluster/secret/UI/verify operation lives in **Phase 5** and nothing
agentic depends on it. The PR ships Phase 5 deliberately **unimplemented**,
marked for the operator: MO-1 model download (gpu-1), MO-2 VRAM tune, MO-3
Authentik outpost assignment, MO-4 `claude` OAuth login, MO-5 live contract
verification (both interfaces), MO-6 content-factory writeback + close #55.
MO-1 also confirms-and-locks the model weight source URLs against the live
box (HF paths/quant filenames drift).

## Privacy boundary

`derio-net/frank` is public; `content-factory` is private. This plan and the
PR carry **technical detail only** — no business context (OPSEC).

## Notes for the implementing agent

- The comfyui image only rebuilds on `push:main` touching
  `apps/comfyui/docker/**`, so the new tag's image exists **after merge**;
  ComfyUI is `replicas: 0` (GPU-Switcher-gated), so nothing serves a missing
  tag in the meantime.
- Do NOT author any manual step into phases 1–4 — `fr plan self-review`
  fails agentic-purity violations with error severity.
- Vendoring the `agent_session` fixtures into frank is fine: they are
  generic technical shapes (session id, turn, shot-list schema), no business
  content.
