# AWX Deployment Implementation Plan

**Spec:** `docs/superpowers/specs/2026-05-26--auto--awx-deployment-design.md`
**Status:** Not Started

## Overview

Deploy AWX (the upstream Ansible automation controller) as Frank's new `auto`
layer (#20) — the imperative counterweight to a declarative cluster, reaching
the non-Talos / external home-lab devices that Talos and ArgoCD cannot manage.

The deployment follows the locked spec decisions: **AWX Operator via ArgoCD**
(two-layer reconciliation — ArgoCD owns the operator chart + the `AWX` CR, the
operator owns the runtime workload), **operator-managed Postgres** on Longhorn,
**native OIDC to Authentik** (not forward-auth), and **internal exposure** at
`awx.cluster.derio.net` via the shared Traefik LB (no dedicated LB IP).

## Phase shape and dependencies

- **Phase 1** (agentic, root) — register the `auto` layer, then author the
  ArgoCD app: operator chart values, the `AWX` CR, and a multi-source
  Application with sync waves + `SkipDryRunOnMissingResource` to handle the
  CRD-before-CR first-sync race, plus `ignoreDifferences` on operator-generated
  Secrets.
- **Phase 2** (manual, depends on 1) — generate/SOPS-encrypt/apply the AWX
  bootstrap secrets (`awx-admin-password`, `awx-secret-key`) out-of-band. Names
  match the CR refs from Phase 1. Per repo principle SOPS secrets are never
  ArgoCD-managed.
- **Phase 3** (agentic + manual, independent root) — Authentik OIDC provider
  blueprint modelled on the Infisical one, registered in the worker's
  `blueprints.configMaps`. A manual op sets the shared `client_secret` on both
  the Authentik provider and AWX's `SOCIAL_AUTH_OIDC_SECRET` (neither belongs in
  git).
- **Phase 4** (agentic, depends on 1) — Traefik IngressRoute (no forward-auth
  middleware — AWX owns its login) + homepage tile.
- **Phase 5** (manual, fan-in on 1–4) — the Deployed gate: sync, confirm the
  operator reconciles AWX + Postgres to Running, UI reachable, OIDC login
  round-trips through Authentik, and a smoke `ping` playbook runs green against
  one real non-Talos host. The layer is not Deployed until that playbook
  succeeds.

## Key risks and mitigations

- **CRD-before-CR race:** the operator chart installs the `AWX` CRD; the CR
  can't apply until it exists. Mitigated by sync waves (operator wave 0, CR
  wave 1) and `SkipDryRunOnMissingResource=true`.
- **OIDC secret in git:** avoided — only non-secret OIDC settings live in the CR
  `extra_settings`; the secret is set via the AWX Settings API out-of-band.
- **`Synced/Healthy` ≠ running:** the two-layer reconciliation means ArgoCD
  reports healthy before the operator finishes. Phase 5 verifies pods + workflow
  directly.
- **OIDC settings vehicle:** `SOCIAL_AUTH_OIDC_*` via `extra_settings` is correct
  for the pinned AWX 2.19.x; re-confirm at implementation since recent AWX has
  been migrating auth config toward the DB-backed Settings flow.

## Out of scope

Custom Execution Environments, receptor mesh, full device-inventory build-out,
public exposure, a dedicated `awx-db` app, and AWX DB backups — all deferred per
the spec.

## Deployment Deviations

- **P1 — managed Postgres CrashLoopBackOff (volume permissions).** After
  Phases 1–2 the operator-managed `awx-postgres-15-0` pod entered
  CrashLoopBackOff (696 restarts over ~2.5 days) with
  `mkdir: cannot create directory '/var/lib/pgsql/data/userdata': Permission
  denied`. Root cause: the `sclorg/postgresql-15` image runs as UID 26, but a
  freshly provisioned Longhorn PVC mounts root-owned, and the AWX operator emits
  an **empty** pod `securityContext` unless told otherwise — so UID 26 cannot
  create its PGDATA subdir. `awx-web` then CrashLooped (no DB) and `awx-task`
  stuck at `Init:0/2` (waiting on migrations). **Fix:** added
  `postgres_data_volume_init: true` to the AWX CR (`apps/awx/manifests/awx.yaml`),
  which injects a root init container that `chown`s the data volume to the
  postgres UID before the container starts. Chosen over
  `postgres_security_context_settings: {fsGroup: 26}` because it is
  storage-agnostic (works regardless of CSI fsGroup support). Gotcha recorded
  under Storage / Secrets / SSA.
