# Feature-Health Alert Resilience — Plan

**Plan type:** extension (hardening of deployed Layer 10 — Observability). Not a
new layer; per the post-deploy skip rules this updates existing posts/gotchas
rather than authoring new blog posts.

**Spec:** `docs/superpowers/specs/2026-05-31--obs--feature-health-alert-resilience-design.md`

## Why

On 2026-05-31 ~15:31 UTC a Longhorn `instance-manager` on mini-2 died (transient
CNI/gRPC reset, no OOM) and detached the **single-replica `vmsingle`** PVC for
~2 minutes. Every feature-health rule is configured `execErrState: Error`, so all
~30 went to `Error` state and fired critical `DatasourceError` alerts to Telegram
(rendered `[no value]` because the templating query never returned). Worse, those
`Error` alerts carry `severity=critical` AND match the `grafana_folder=feature-health`
→ **Health Bridge** route, so a transient blip can falsely mark GitHub
work-items `dead`.

Two root weaknesses: rules answer "is monitoring reachable?" individually and
wrongly; and `vmsingle` is a single Longhorn-backed SPOF.

## Approach — three pillars, preserving the original spec's spirit

Everything stays declarative (ConfigMaps + Helm values), PVC-loss-safe,
ArgoCD-self-healing, with the Health Bridge / GitHub work-lifecycle coupling
(`github_issue` labels, `continue: true` dual-routing) untouched. The change
*protects* lifecycle correctness rather than altering it.

1. **Pillar 1 (Phase 1):** `execErrState: Error → KeepLast` on the ~30
   feature-health rules. A transient exec error holds each feature's real last
   state — no false page, no false `dead`. `noDataState: OK` and the deliberately
   tuned `for:` values stay.
2. **Pillar 2 (Phase 2):** one **deadman watchdog** in a new `monitoring-meta`
   folder (`execErrState`/`noDataState: Alerting`, `for: 2m`, no `github_issue`,
   Telegram-only). It is the single rule allowed to fire on missing/errored data
   — converting the 30-way storm into one human page, fenced out of the Health
   Bridge plane.
3. **Pillar 3 (Phases 3–4):** **two-`VMSingle` HA pair** (anti-affinity, vmagent
   dual-write) fronted by **`vmauth`** (`first_available` failover). Grafana's
   datasource keeps UID `P4169E866C3094E38`; only its URL repoints to vmauth.
   VMCluster is the noted future scale-out path, deferred.

## Phase ordering / dependencies

- **Phase 1** — independent (`depends_on: []`); immediately shrinks blast radius.
- **Phase 2** — `depends_on: [1]`; delivers "one page not 30" even before HA exists.
- **Phase 3** (write-path HA) — independent (`depends_on: []`); can proceed in parallel.
- **Phase 4** (read-path HA) — `depends_on: [3]`; vmauth needs both stores first.
- **Phase 5** (post-deploy) — `depends_on: [1,2,3,4]`.

Each phase is a mergeable PR-sized unit. grafana-alerting ConfigMap changes
additionally require a Grafana pod restart (provisioning read at boot, not
watched — `frank-gotchas/grafana.md`).

## Verification highlights

The decisive test is in Phase 4: with the HA pair live, deleting the VMSingle
that vmauth is sticky to must produce **zero** `DatasourceError` and **zero**
watchdog page — i.e. the original incident reproduced as a non-event. Phase 2
independently proves the single-page property; Phase 1 proves no false Health
Bridge transition on an exec error.

## Plan-time unknowns (resolved in-phase, not guessed)

- Exact VM health-metric series name for the watchdog query (P2.T1.S1).
- Whether the 2nd VMSingle + vmauth are chart-values or sibling operator CRs
  (P3.T1.S1) — drives P4 wiring.
