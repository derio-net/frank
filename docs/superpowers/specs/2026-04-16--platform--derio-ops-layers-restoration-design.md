# Derio Ops Board — Layers Restoration

*Date: 2026-04-16*
*Status: Pass 1 + Pass 2 + Pass 3 complete (2026-04-20).*

## Problem

The "Derio Ops" GitHub Project (org-level board, derio-net/projects/1) was designed as a **1:1 health view of the Frank cluster's Layers** as depicted in the [`cluster-roadmap` shortcode](../../../blog/layouts/shortcodes/cluster-roadmap.html) on the [building/00-overview blog post](../../../blog/content/docs/building/00-overview/index.md).

Over time, the board drifted into a dispatch-progress view: 33 items at peak, ~23 of which were `vk-dispatch`-generated phase-issues (`*-N-agentic`, `*-N-manual`). The original Layer-tracking purpose was lost.

Additionally, the operational layer of the [Work Lifecycle Tracking design](../../../../willikins/docs/superpowers/specs/2026-04-01-work-lifecycle-tracking-design.md) — Grafana → Health Bridge → GitHub Issue lifecycle automation — was never wired up to the board. `healthy` / `degraded` states have been set manually, defeating the system's purpose (catching silent failures like dead cron jobs).

## Decision

Restore the board to its original intent: **one row per Layer, lifecycle field auto-driven by Grafana via the Health Bridge**.

## Layers Model

Each row on the board corresponds to one numbered Layer from the blog roadmap. Layer numbers follow the blog series ordering with gaps preserved (no Layer 7, 20, 22, 23 — those are absorbed into adjacent Layers per the editorial decision in the cluster-roadmap shortcode).

### Final layer set (20 trackers)

| # | Name | Issue | Initial state | Notes |
|---|------|------:|---------------|-------|
| 1 | Hardware | frank-ops#1 | healthy | 7 nodes, 3 zones |
| 2 | OS & Bootstrap | frank-ops#2 | healthy | Talos + Omni |
| 3 | Networking — Cilium | frank-ops#3 | healthy | eBPF, L2 LB, Hubble |
| 4 | Storage — Longhorn | frank-ops#4 | healthy | 3-replica block storage |
| 5 | GPU Compute | frank-ops#5 | healthy | NVIDIA + Intel DRA |
| 6 | GitOps — ArgoCD | frank-ops#6 | healthy | App-of-Apps |
| 8 | Observability | frank-ops#8 | healthy | Absorbs blog #22 (Health Monitoring) + #23 (Health Bridge) |
| 9 | Backup | frank-ops#9 | healthy | Longhorn → R2 |
| 10 | Secrets | frank-ops#10 | healthy | Infisical + ESO |
| 11 | Local Inference | frank-ops#11 | healthy | Ollama + LiteLLM |
| 12 | Agentic Control Plane | frank-ops#12 | healthy | Sympozium only — DevOps/Platform Engineering |
| 13 | Unified Auth | frank-ops#13 | healthy | Authentik |
| 14 | Multi-tenancy — vCluster | frank-ops#14 | healthy | K8s-in-K8s |
| 15 | Agentic Workflows | frank-ops#15 (repurposed) | in-progress | n8n + VK + Paperclip + Praison (planned). Repurposed from "Paperclip AI deployment". |
| 16 | Media Generation | frank-ops#16 (repurposed) | blocked | ComfyUI + GPU Switcher. Pending Traefik route + model downloads. |
| 17 | Public Edge — Hop | frank-ops#17 | healthy | Hetzner CX23 + Headscale + Caddy. Extended health basis: blackbox blog probe + mesh peer count + cert expiry + Hetzner API |
| 18 | Persistent Agent | frank-ops#18 (repurposed) | healthy | Absorbs blog #18 + #21 (workstation + hardening). Hosts willikins crons. Known sub-feature degradation tracked in body. |
| 19 | Progressive Delivery | frank-ops#19 | healthy | Argo Rollouts |
| 24 | In-Cluster Ingress | frank-ops#24 | healthy | Traefik + Authentik forward-auth |
| 25 | CI/CD Platform | frank-ops#25 | healthy | Gitea + Tekton + Zot |

Every Issue lives in `derio-net/frank` regardless of which repo the underlying components are deployed from — the board tracks **Frank as a system**, not per-repo work.

### Editorial decisions

- **Layer 7 (Fun Stuff / OpenRGB) dropped** — not a meaningful operational layer.
- **Layers 18 + 21 merged** into Layer 18 — they describe the same workstation; #21 is a hardening pass on top of #18.
- **Layer 12 narrowed** to Sympozium only. n8n and VK Remote moved to Layer 15 (Agentic Workflows). This reflects current usage: Sympozium is the DevOps/Platform Engineering control plane; n8n/VK/Paperclip/Praison are user-facing agentic workflow tools.
- **Layer 8 absorbs blog #22 + #23** — Observability includes the Health Monitoring + Health Bridge subsystems per the cluster-roadmap shortcode's grouping.

### Excluded from the board

These are real Issues but **not Layer trackers**, so they live in their respective repos and stay off this board:

- `vk-dispatch`-generated phase-issues (`*-N-agentic`, `*-N-manual`) — implementation fragments tracked by `vk-progress`, not layers.
- Skill-level bugs (e.g. `willikins#15` Newsdesk timeout) — bugs of features that run *on* a Layer, not Layers themselves.
- Sub-feature bugs of Layer 18 (`willikins#11/12/13/18/32` — exercise reminder, audit digest, session manager) — referenced in Layer 18's body's "Known issues" section. The Layer 18 lifecycle reflects pod health; sub-feature regressions are tracked by the linked willikins Issues.

## Pass 3 — Grafana wiring (executed 2026-04-20)

For each Layer Issue, create one Grafana alert rule labelled `github_issue=frank-ops#<layer>`. The Health Bridge (`apps/health-bridge`) already exists and is responsible for translating alert state → Issue lifecycle:

- alert **firing, severity=warning** → `degraded`
- alert **firing, severity=critical** → `dead`
- alert **resolved** → `healthy`

The "Health-check basis" section in each Layer Issue body documents the intended probe(s).

### Wiring priority order (suggested)

1. **Layer 8 — Observability** first (dogfooding — the bridge alerts on its own absence).
2. **Layer 18 — Persistent Agent** (exercise/audit/session heartbeat metrics — the original motivating problem).
3. **Layer 1, 2, 3, 4, 5, 6** — foundation layers, mostly already covered by kube-state-metrics and existing dashboards.
4. The rest, opportunistically.

## Operational rules

- Lifecycle field is **the** signal; Status field (Todo/In Progress/Done) is vestigial and ignored.
- New Layer Issues should not be created lightly — the Layer set is editorial and tied to the blog roadmap.
- When a new capability is added to Frank, decide first: is it a new Layer (rare), a sub-component of an existing Layer (common), or a feature running on top (most common — not a board item).
- The board is for Frank cluster Layers only. Other repos (willikins, content-factory, etc.) track their own work in their own Issues.

## References

- [Building #00 — Overview & Roadmap](../../../blog/content/docs/building/00-overview/index.md)
- [`cluster-roadmap` shortcode](../../../blog/layouts/shortcodes/cluster-roadmap.html) — canonical Layer definition
- [Work Lifecycle Tracking design (willikins)](../../../../willikins/docs/superpowers/specs/2026-04-01-work-lifecycle-tracking-design.md) — original lifecycle state machine
- [Health Bridge app](../../../apps/health-bridge) — the bridge exists; needs Grafana alert rules to drive it
- [Derio Ops board](https://github.com/orgs/derio-net/projects/1)

## Implementation Plans

| Plan | Repo | File | Status | Depends on |
|------|------|------|--------|------------|
| Derio Ops Pass 3 — Grafana Wiring — Implementation Plan |  | `docs/superpowers/plans/2026-04-16--platform--derio-ops-pass3-grafana-wiring.md` | Not Started | — |
