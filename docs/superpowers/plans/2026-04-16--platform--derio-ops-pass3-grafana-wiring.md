# Derio Ops Pass 3 — Grafana Wiring — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-04-16--platform--derio-ops-layers-restoration-design.md`
**Status:** Not Started

> **Stub** — to be drafted by a Frank agent. Captures goal, scope, and open questions only.

## Goal

Wire the 20 Layer trackers on the Derio Ops board to Grafana alert rules so the Health Bridge can drive their lifecycle field automatically (`healthy` / `degraded` / `dead`), replacing the current manual states.

## Scope

For each Layer Issue (`derio-net/frank#8`, `#10`, `#11`, `#87–#103`), produce one or more Grafana alert rules whose labels include `github_issue=derio-net/frank/<number>`. The Health Bridge (already deployed at `apps/health-bridge`) translates alert state changes into lifecycle transitions.

Each Layer's intended probe is documented in its own Issue body's "Health-check basis" section. The plan should treat those as input, not re-derive them.

## Suggested phasing

1. **Layer 8 — Observability** first (dogfooding — the bridge alerts on its own absence).
2. **Layer 18 — Persistent Agent** (heartbeat probes for the willikins crons — the original motivating problem).
3. Foundation Layers (1, 2, 3, 4, 5, 6) — mostly already covered by kube-state-metrics + existing dashboards.
4. Remaining Layers, opportunistically.

## Open questions for the drafter

- Are alert rules managed via Grafana UI, Grafana API (per `reference_grafana_api_provenance.md`), or as code in this repo (e.g. Grafana provisioning files)? Pick one and stick to it.
- Single rule per Layer, or one rule per probe with `github_issue` shared across? The Bridge probably needs one source-of-truth alert per Layer to avoid flapping; verify against `apps/health-bridge` source.
- Severity mapping the Bridge consumes: confirm `warning → degraded`, `critical → dead`, `resolved → healthy` (per the spec) matches Bridge code.
- For Layers backed by multiple components (e.g. Layer 8: VM + Grafana + Pushgateway + Bridge), is the alert "any-component-down" or "majority-down"?
- For Layer 17 (Hop, extended scope) — Hetzner API status check needs a credential; verify what's already in Infisical and how it should be exposed to Grafana.
- Several Layers don't yet have meaningful health metrics (e.g. Layer 7 was dropped; Layer 15 has multiple deployed-but-blocked components). The plan should flag any Layer where a probe can't be defined and propose what to add.

## Out of scope

- Re-litigating the Layer set or lifecycle field options (decided in spec).
- Bridge code changes (assume current behaviour; file separately if a gap is found).
- New blackbox/Pushgateway deployments (assume what's in `apps/` is current).

---

### Task 1: Draft this plan

- [ ] **Step 1: Resolve the open questions above with a Frank agent and replace this stub task with real phases/tasks.**
