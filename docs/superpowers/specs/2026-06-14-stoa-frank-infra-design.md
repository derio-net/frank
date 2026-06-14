# Stoa Frank Infra — Design

**Status:** Draft
**Layer:** agents (12 — Agentic Control Plane) / gpu (4 — AI Compute)
**Date:** 2026-06-14
**Repos touched:** `frank` (this spec + ComfyUI/n8n-01 wiring, the PR this run delivers),
`agentic-stoa/content-factory` (private — Phase-2 verify writeback only, no code)

## Implementation Plans

| Plan | Target repo | Slug | Status |
|------|-------------|------|--------|
| 2026-06-14-stoa-frank-infra | `derio-net/frank` | `2026-06-14-stoa-frank-infra` | — |

## Context

The **stoa** content pipeline (private, `agentic-stoa/content-factory`) is a standing local AI
pipeline producing serialized short-form video. Its pipeline plan, Phase 2 (issue
[content-factory#55](https://github.com/agentic-stoa/content-factory/issues/55), tagged
`manual`) is a **Frank-readiness gate**: it requests two **additive** infrastructure changes
on Frank and then verifies the live contract once Frank lands them.

The operator runs *as Frank* here, so there is **no separate request issue** — this PR **is**
Frank landing the request. The two changes:

1. **ComfyUI on `gpu-1`** enabled for stoa video/audio generation: custom nodes + model
   weights (LTX-2 NVFP8, Wan 2.2 14B Q8 GGUF, LTX-Video 0.9.x, TTS), VRAM/offload tuned for
   the 16 GB RTX 5070 Ti, the API reachable, and an Authentik-gated Traefik route.
2. A **`multi-agent-shell` sidecar** on the `n8n-01` pod hosting a **persistent,
   operator-attachable `claude` session** that n8n drives over a pod-local interface — never
   `claude -p`.

The interface shapes Frank must satisfy are pinned in the content-factory **interface-contracts
decision record**, with machine-checkable fixtures alongside it in that private repo. The
content-factory build proceeds against those fixtures/mocks; only its measurement gates and the
pilot need this live infra.

### Privacy boundary (load-bearing)

`derio-net/frank` is **public**; `content-factory` is **private**. This spec and the PR it
drives carry **technical detail only — no business context** (OPSEC). "stoa" here means a
serialized-video generation workload; nothing about titles, market, or strategy belongs in
this repo.

## Goals

- ComfyUI on `gpu-1` serves the stoa generation workflows through its **native API**
  (`POST /prompt`, `GET /history/{id}`, `GET /view`), with the required custom nodes + model
  weights present and VRAM bounded to run one model at a time on 16 GB.
- A `multi-agent-shell` sidecar on `n8n-01` exposes a **persistent** `claude` session via a
  send/receive driver conforming to the `agent_session.*` contract (turn counter evidencing
  continuity), driven by n8n over a pod-local transport and attachable by the operator.
- **Declarative-only:** every artifact reproducible from this repo (ArgoCD). The only
  out-of-band steps are the documented `# manual-operation` blocks (model weights, OAuth
  login, Authentik outpost, live verification).
- **Reuse, not reinvention:** align with the existing **k8s-native agentic-runs** design
  (`docs/superpowers/specs/2026-06-07--agents--k8s-native-runs-design.md`) rather than fork a
  parallel session mechanism.

## Non-goals (out of scope for this run)

- The stoa **application code** (runner, registry, gates, assembly, n8n graphs) — that is
  P3–P7 in `content-factory`, built against the fixtures, not here.
- **Quality calibration** of the models (does LTX-2 look good, is the audio acceptable) —
  measured at the content-factory manual gates (G2/G3/G5), not asserted here.
- A standalone **agent-session HTTP server** image in `agent-images` (the rejected Option 2).
  The driver is a thin frank-side script over the established `tmux send-keys`/`capture-pane`
  pattern.
- Deploying / depending on **`runs-fr`** (Component C is a walking skeleton, not yet deployed
  — runs-fr#9). It is the *future* browser-attach path; operator-attach here is SSH/`kubectl
  exec` + `tmux attach`.
- **Cloud generation fallback** — stays off; not provisioned here.

## Architecture

Two independent components. They share nothing except the pod (`n8n-01`) the sidecar joins
and the GPU node (`gpu-1`) both ultimately run on.

### Reuse map (why this is EXTEND, not BUILD-NEW)

Investigation (operator-directed: check `agent-images` and `runs-fr`) established the
substrate already exists:

| Need | Existing artifact | Action |
|------|-------------------|--------|
| ComfyUI API (submit/poll/fetch) | stock ComfyUI on `gpu-1` (`apps/comfyui`) | **reuse as-is** — the contract shapes are native ComfyUI; no shim |
| Shell + `claude` + tmux + sshd | `agent-images/multi-agent-shell` (the design's **L1** image) | **reuse as the sidecar image** |
| Persistent-session drive pattern | the k8s-native-runs design's Tier-2 mechanism: interactive tmux session + `tmux send-keys`→`capture-pane`, **never `claude -p`** | **extend** into a thin send/receive driver + turn counter |
| Operator browser-attach | `runs-fr` (Component C) | **note as future** — not deployed; attach via SSH/`kubectl exec` now |

The `kali` `session-manager.sh`/`wrap-claude.py` machinery was evaluated and **rejected** as a
base: it drives `claude remote-control`, coupled to the willikins remote-control bridge, not a
clean pod-local send/receive driver.

### Component 1 — ComfyUI stoa enablement (`apps/comfyui`)

Current state: `apps/comfyui` is a stock ComfyUI Deployment on `gpu-1`, `replicas: 0`
(GPU-Switcher-gated), image `ghcr.io/derio-net/comfyui:comfyui-v0.9.2-pt2.10.0-cu128` built by
`.github/workflows/build-comfyui.yml` from `apps/comfyui/docker/`, with a 100 Gi `comfyui-models`
PVC and a 10 Gi `comfyui-custom-nodes` PVC, exposed at LB `192.168.55.213:8188` and ClusterIP
`comfyui.comfyui.svc:8188`. The Traefik route, Authentik proxy provider, and homepage tile for
`comfyui.cluster.derio.net` **already exist** in the repo (gated live only by the embedded-outpost
assignment, MO-3). **Missing: the stoa nodes/models and the VRAM/offload flags.**

**1a. Custom nodes — baked into the image (your choice: bake + pin).** Extend
`apps/comfyui/docker/Dockerfile` to `git clone` the required custom nodes at pinned refs and
install their `requirements.txt`, gated behind a new `NODES_REF`/per-node `ARG` so the build is
reproducible. Nodes (pinned to real upstreams; exact refs locked in the plan):
- **LTX-Video** (`Lightricks/ComfyUI-LTXVideo`) — LTX-Video 0.9.x **and** LTX-2 NVFP8 sampler
  nodes.
- **GGUF loader** (`city96/ComfyUI-GGUF`) — for Wan 2.2 14B **Q8 GGUF**.
- **WanVideo wrapper** (`kijai/ComfyUI-WanVideoWrapper`) — Wan 2.2 nodes.
- **TTS** — both engines (your choice "Both"): a **Kokoro** node (`stavsap/comfyui-kokoro` or
  equivalent) and a **Fish-Speech** node (`AIFSH/ComfyUI-FishSpeech` or equivalent).

The image tag gains a node-set dimension (e.g. `…-cu128-stoa<N>`) so the Deployment's pinned
tag moves only when the node set changes (mirrors the repo's digest-pin philosophy and the
Falco "no runtime binary installs" posture). `build-comfyui.yml` env + the Deployment image tag
bump together.

> **Rejected:** runtime install via ComfyUI-Manager onto the PVC — non-reproducible and trips
> the runtime-install Falco rule.

**1b. Model weights — declarative download Job (your choice: download Job).** A new idempotent
`Job` (`apps/comfyui/manifests/job-model-download.yaml`) hydrates the `comfyui-models` PVC:
LTX-2 NVFP8, Wan 2.2 14B Q8 GGUF, LTX-Video 0.9.x, Kokoro, Fish-Speech S2. Idempotent
(skip-if-present by target path + size/sha), `nodeSelector: gpu-1`, mounts the same PVC, runs
once. Weight **source URLs are confirmed on the live box** (HF repo paths / quant filenames may
move) → the Job ships with sourced-and-commented URLs but the **actual download run is a
back-loaded `# manual-operation`** (GB-scale pull, gpu-1).

**1c. VRAM / offload for 16 GB.** The stoa runner drives **one clip at a time** (submit →
poll → fetch), so models load serially. Set ComfyUI launch flags in the Deployment `CMD` for a
16 GB ceiling (candidate: `--lowvram` / `--reserve-vram <GiB>` / `--cache-none`; exact flags
validated on the live box and recorded). This is config, not code; final values are tuned at
the live gate.

**1d. Traefik route + auth (your choice: Authentik SSO + ClusterIP runner) — ALREADY PRESENT.**
The declarative pieces for `comfyui.cluster.derio.net` already exist in the repo and are kept as-is
(a regression guard test asserts their presence + shape):
- IngressRoute in `apps/traefik/manifests/ingressroutes.yaml` (`authentik-forwardauth` middleware).
- Proxy provider in `apps/authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml`
  (`forward_single`, `invalidation_flow`).
- Homepage tile in `apps/homepage/manifests/files/services.yaml`.
- **Manual (MO-3):** outpost-provider assignment (Django ORM, per `frank-argocd.md`) — the one
  non-declarative piece; verify SSO actually presents and run it if not.

The **in-cluster runner + n8n call the ClusterIP** (`comfyui.comfyui.svc:8188`) with no SSO;
the Traefik route is the human/ops surface only. (If the runner is ever moved outside the
cluster, that's a separate decision — not provisioned here.)

**1e. API contract.** Native ComfyUI already serves `POST /prompt` →
`{prompt_id, number, node_errors}`, `GET /history/{prompt_id}` →
`{status:{completed,status_str,…}, outputs:{<node>:{gifs:[…]}}}`, `GET /view?filename&subfolder&type`.
These match the fixtures (`comfyui_submit_response.json`, `comfyui_status_response.json`,
`comfyui_view_request.json`) verbatim — **no shim**. Conformance is proven by a live
submit→poll→fetch at the manual gate.

### Component 2 — `multi-agent-shell` sidecar on `n8n-01` (`apps/n8n-01`)

Current state: `apps/n8n-01/manifests/deployment.yaml` is a single-container `n8nio/n8n:2.13.4`
Deployment on `gpu-1`, `strategy: Recreate`, data PVC `n8n-01-data`.

**2a. Sidecar container.** Add a `multi-agent-shell` container to the `n8n-01` Deployment, image
`ghcr.io/derio-net/multi-agent-shell:<pinned>`, with:
- A **dedicated PVC** (`n8n-01-agent-home`) at the agent `$HOME` for PV-resident OAuth creds +
  tmux-resurrect session state (the image's documented contract — creds never in the image).
- `securityContext` honoring the image's non-root agent uid; explicit `HOME`.
- No `ANTHROPIC_API_KEY` in `env:` — subscription OAuth per the multi-harness standard.

**2b. Persistent session bootstrap.** A small bootstrap (ConfigMap-mounted, run by the image's
`cont-init.d`/s6 convention or an explicit command) ensures a **tmux session named
`stoa-script-claude`** running **interactive `claude`** (never `-p`), started once and kept
alive (tmux-resurrect/continuum already in the L0 base). This is the same "agent in a named
tmux session" shape the k8s-native-runs design uses.

**2c. Send/receive driver (the EXTEND).** A ConfigMap-mounted script `agent-session`
implementing the `agent_session.*` contract:
- **send**: input `{session_id, agent, message, expect?, timeout_s?}` → selects the tmux
  session, `tmux send-keys` the message, waits (bounded by `timeout_s`) for the reply marker.
- **receive**: `tmux capture-pane` the reply, extract the structured `payload` (the shot-list
  JSON the agent emits), increment a **persisted per-session turn counter** (`$HOME/.stoa/
  <session_id>.turn`), emit `{session_id, agent, status:"ok", turn, payload}`.
- The driver matches `agent_session_send_request.json` / `agent_session_receive_response.json`
  exactly. The `turn` increment across calls is the evidence-of-persistence the contract wants
  (a fresh `claude -p` could never advance it).

**2d. Pod-local interface n8n reaches (your choice: Option 1 — script over exec, no HTTP
server).** n8n and the sidecar share the pod (and its network namespace). n8n drives the driver
over the sidecar's **own `sshd` on `localhost:22`** using the **n8n SSH node**: n8n SSHes to
`localhost` (the sidecar, since n8n's container binds 5678 not 22) and runs
`agent-session send …`, receiving the JSON on stdout. Auth via a key on the agent PVC. This
keeps the interface a **script invocation** (Option 1), not a long-running HTTP service.
- *Constraint:* `shareProcessNamespace` is **incompatible with the image's s6-overlay v3**
  (PID-1 must be `suexec`) — so cross-container drive uses the shared **network** namespace
  (localhost sshd) or a shared workspace volume, **never** `shareProcessNamespace`.

**2e. Operator-attach.** `kubectl exec -it -c multi-agent-shell n8n-01-… -- tmux attach -t
stoa-script-claude`, or `ssh` into the sidecar (image is SSH-able) + `tmux attach`. The
operator inspects/redirects/re-rolls a beat by hand — the creative analog of the editable n8n
graph. (Future: surface the same tmux session in the `runs-fr` browser gateway once it is
deployed, by labeling the pod `fr.run/*`.)

**2f. Auth (manual).** One-time `claude login` (subscription OAuth) inside the sidecar lands the
credential on `n8n-01-agent-home`; survives restarts. `# manual-operation`.

## Conformance contract (what "satisfied" means)

The live infra is conformant when, run from inside the cluster:
1. `POST comfyui.comfyui.svc:8188/prompt` with a stoa graph returns `prompt_id` +
   `node_errors: {}`; `GET /history/{id}` reaches `status.completed: true` with an
   `outputs.<node>.gifs[]` descriptor; `GET /view?…` returns the clip bytes. (Models LTX-2 /
   Wan 2.2 / LTX-Video / Kokoro / Fish present; target list visible.)
2. `agent-session send {session_id:"stoa-script-claude", agent:"claude", message:"…",
   expect:"shotlist"}` returns `{status:"ok", turn:N, payload:{…}}`; a **second** call returns
   `turn:N+1` (persistence proof); the operator can `tmux attach` to the same session.

These are the content-factory Phase-2 S2 checks; their results + the live endpoints/route get
recorded back in the **Frank-request runbook** in content-factory (private), and #55 closed.

## Manual / back-loaded operations (all in the final phase; nothing agentic depends on them)

Per fr-goal placement policy, the PR ships these **unimplemented**, for the operator to run on
the live box and push to the same PR / drive post-merge:

- **MO-1 ComfyUI model download** — run the download Job on `gpu-1`; confirm weights present.
  (Source URLs confirmed live.)
- **MO-2 ComfyUI VRAM tune** — validate the launch flags actually bound 16 GB under a real
  generation; record final flags.
- **MO-3 Authentik outpost assignment** — add the ComfyUI proxy provider to the embedded
  outpost (Django ORM).
- **MO-4 claude OAuth login** — `claude login` in the sidecar; credential on the PVC.
- **MO-5 Live contract verification** — run the two conformance checks above end-to-end.
- **MO-6 content-factory writeback** — record endpoints/route + Frank PR URL in the
  Frank-request runbook (content-factory, private); mark Phase-2 steps; close content-factory#55.
- **MO-7 n8n→sidecar transport keypair** — SOPS-managed `n8n-01-agent-ssh` Secret (public key
  → sidecar `authorized_keys`, private key → n8n container) so n8n's SSH node can reach the
  driver on localhost. Prerequisite for MO-5b. Secrets aren't ArgoCD-managed (declarative-only
  exception), hence manual.

## Test plan (post-merge, operator-driven)

The deterministic artifacts (manifests, Dockerfile, Job YAML, driver script, ConfigMaps) are
validated in-repo (YAML/manifest validation, driver script unit tests against the fixtures —
`tmux` mocked). The **behavioral** proof is MO-5 above: the two live conformance checks on
`gpu-1`, run interactively the production way (in-session, not `claude -p`), mirroring the
k8s-native-runs Tier-2 doctrine. A layer is not "Deployed" until those run end-to-end.

## Risks & open considerations

- **16 GB VRAM fit is unproven for LTX-2 NVFP8 + Wan 2.2 14B.** One-model-at-a-time + offload
  flags are the mitigation; the live tune (MO-2) is the real test. If a model can't fit, that's
  a content-factory gate decision (G2/G3), not a Frank blocker — the API still conforms.
- **Model source churn.** HF repo paths / quant filenames move; the Job's URLs are confirmed
  live at MO-1, not assumed at author time.
- **gpu-1 is the only GPU node and hosts pinned agent pods.** ComfyUI is `replicas: 0`
  (GPU-Switcher-gated) so it contends only when activated; the sidecar is CPU-only (no GPU
  request). No new hard GPU pin is added.
- **Sidecar inflates the `n8n-01` pod** (memory/restart coupling — `Recreate` strategy means
  both restart together). Bound the sidecar's resources; keep n8n's own limits intact.
- **`runs-fr` not deployed.** Operator-attach must not depend on it; SSH/`kubectl exec` is the
  baseline. Browser-attach is a future nicety.
- **Privacy.** Keep business context out of this public repo; technical only.
