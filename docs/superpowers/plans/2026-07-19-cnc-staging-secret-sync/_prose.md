# Plan: OSS-vCluster-compatible secret delivery for CNC staging

Implements approach A from
`docs/superpowers/specs/2026-07-19--secrets--cnc-staging-vcluster-secret-sync-design.md`:
deliver the three CNC staging secrets (`cnc-secrets`, `cnc-ghcr-pull`,
`cnc-runner-auth`) into the **OSS** `cnc-staging` vCluster by resolving the
ExternalSecrets **host-side** (host ESO + `infisical` work there) and syncing the
resolved Secrets **into** the vCluster via OSS-native `sync.fromHost.secrets`.

This replaces the reverted Pro-only `integrations.externalSecrets` approach
(frank #651, which crashed the OSS control-plane; reverted by #652).

## Why this shape

- **Agentic phases 1–2** are pure manifest work verifiable *statically* (kustomize
  build / helm template + YAML assertions) — guard tests catch regressions and
  pin the prod-unaffected invariant.
- **Manual phase 3** carries everything that only a live cluster can prove. The
  `dockerconfigjson` type-preservation through the host→vCluster sync and the
  vCluster's RBAC read are **runtime** facts — `helm template` proves schema only,
  and trusting a green template over runtime is exactly what caused the #651
  incident. So the primary risk is verified on-cluster or the work is not done.

## Product invariants (T1)

Consuming specs (`cncd`/`node`/`fru`) are unchanged: they mount by name+key in ns
`cnc-staging`. Preserve names, keys, `cnc-ghcr-pull` type `dockerconfigjson`, and
the target namespace. The whole design is product-invisible when those hold.

## Dependencies / scope

- **Blocker B** (register the vCluster as an ArgoCD cluster `cnc-staging`) is a
  separate out-of-band prerequisite for full staging workload bring-up; the
  fromHost secret sync itself does not require it.
- `cnc-source-token` / reseed stay skipped for the first rollout.
- Node PVC one-time login is orthogonal. Prod is unchanged.

## Rollback

Revert the vcluster values + host-side app and drop the `$patch: delete`. No Pro
feature is enabled on the control-plane, so this cannot crash the vCluster the way
#651 did.
