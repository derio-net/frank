# Design: OSS-vCluster-compatible secret delivery for CNC staging

**Status:** Draft
**Date:** 2026-07-19
**Layer:** secrets
**Branch:** feat/cnc-staging-secret-sync

## Problem

The CNC staging stack runs **inside the `cnc-staging` vCluster**. Its three
secrets are defined as ExternalSecrets in `apps/cnc-base/manifests/externalsecrets.yaml`
(shared with prod via the kustomize base) and, for staging, are created **inside
the vCluster** (the `cnc-staging` overlay sets `namespace: cnc-staging`).

They cannot resolve there: an OSS vCluster has **no ESO controller and no
`infisical` ClusterSecretStore**. So `cncd`/`node`/`fru` can never mount their
secrets, and staging workloads can't come up.

The first attempt (frank #651) enabled vCluster's `integrations.externalSecrets`
— but that is a **vCluster Pro** feature; on Frank's OSS vCluster it fails closed
at control-plane boot (CrashLoopBackOff). Reverted by #652. See the incident
record in the rollout cascade `terminal-2.md`.

## The three secrets (invariants — must stay product-invisible)

`cncd`/`node`/`fru` mount by name+key in their own namespace, blind to how the
Secret was produced. Preserve:

| Secret | Key(s) | Type | Consumed by |
|---|---|---|---|
| `cnc-secrets` | `CNCD_SECRETS_MASTER_KEY` | Opaque | cncd (env) |
| `cnc-ghcr-pull` | `.dockerconfigjson` | `kubernetes.io/dockerconfigjson` | all (imagePullSecret) |
| `cnc-runner-auth` | `token` | Opaque | cncd (env) + node (file mount) |

Invariants: (1) names unchanged, (2) keys unchanged, (3) `cnc-ghcr-pull` stays
`dockerconfigjson`, (4) they land in the **in-vCluster namespace the pods consume
from** (`cnc-staging`). Consuming specs (`cnc-base` deployments/statefulset) do
**not** change.

## Approach (operator-chosen "A")

Resolve the ExternalSecrets on the **host** (where ESO + `infisical` work) and
sync the resolved Secrets **into** the vCluster via OSS-native
`sync.fromHost.secrets`.

```
Infisical --host ESO--> Secret in host ns cnc-staging-vcluster
          --vCluster fromHost sync (byName)--> Secret in vCluster ns cnc-staging
          --> cncd/node/fru mount (unchanged)
```

`sync.fromHost.secrets` is confirmed present in the **OSS** rendered config
(`enabled: false, mappings.byName: {}`) — core sync, not a Pro integration.

## Changes

### 1. New host-side app `apps/cnc-staging-host/`
- `manifests/externalsecrets.yaml` — the 3 ExternalSecret CRs (copied from
  `cnc-base`, unchanged spec: same names, keys, `cnc-ghcr-pull` dockerconfigjson
  template), created in **host ns `cnc-staging-vcluster`**.
- `manifests/kustomization.yaml` — `namespace: cnc-staging-vcluster`.
- `apps/root/templates/cnc-staging-host.yaml` — Application CR, destination
  **host cluster**, ns `cnc-staging-vcluster`, `sync-wave` **before** the vCluster
  workloads sync (so the host Secrets exist before the vCluster syncs them in).
  `ignoreDifferences` on Secret `/data` (ESO-managed), `prune: false`,
  `ServerSideApply=true`.

### 2. Exclude the 3 ExternalSecrets from the in-vCluster staging deploy (D2)
- In `apps/cnc-staging/manifests/kustomization.yaml`, add a `$patch: delete`
  entry for each of the 3 ExternalSecrets. `cnc-base` is untouched → **prod is
  unaffected** (prod keeps resolving them directly in host ns `cnc`).

### 3. vCluster `sync.fromHost.secrets` (D1: reuse the vcluster host ns)
In `apps/vclusters/cnc-staging/values.yaml`:
```yaml
sync:
  fromHost:
    secrets:
      enabled: true
      mappings:
        byName:
          "cnc-staging-vcluster/cnc-secrets": "cnc-staging/cnc-secrets"
          "cnc-staging-vcluster/cnc-ghcr-pull": "cnc-staging/cnc-ghcr-pull"
          "cnc-staging-vcluster/cnc-runner-auth": "cnc-staging/cnc-runner-auth"
```
Host source ns = the vCluster's own host ns `cnc-staging-vcluster` (native RBAC).
Target = vCluster ns `cnc-staging` (where pods consume).

## Decisions
- **D1 — host ns for the ExternalSecrets:** reuse `cnc-staging-vcluster` (the
  vCluster reads its own host ns natively; no extra cross-ns RBAC). *(operator-confirmed)*
- **D2 — exclusion mechanism:** kustomize `$patch: delete` in the staging overlay
  (surgical; leaves `cnc-base`/prod untouched) rather than restructuring
  `cnc-base` into components. *(operator-confirmed)*

## Technical risks — VERIFY, do not assume (lesson from #651)

A verification spike must run on-cluster **before B.5 is declared done**:
1. **Type preservation** — does `sync.fromHost.secrets` copy the
   `kubernetes.io/dockerconfigjson` **type**, or does `cnc-ghcr-pull` land as
   `Opaque` (→ image pulls break)? PRIMARY risk.
2. **RBAC** — does the vCluster syncer actually read the host `cnc-staging-vcluster`
   ns without extra rules? (Native for own host ns, but confirm.)
3. **Names/keys land intact** in vCluster ns `cnc-staging`.

`helm template` proves schema-validity only, NOT runtime/edition behaviour
(that is exactly what #651 missed). Verification is on-cluster or it does not count.

## Out of scope / orthogonal
- **Blocker B** (register the vCluster as an ArgoCD cluster `cnc-staging`) — still
  separately required; unaffected by this design.
- **`cnc-source-token`** (ClusterGenerator ExternalSecret) — powers the reseed job,
  which is **skipped** for the first rollout; off the critical path. Same host-side
  pattern can be applied later if reseed is enabled.
- **Node PVC one-time `claude`/`agy`/`codex` login** — orthogonal harness auth.
- **prod** — unchanged (host-ESO direct).

## Divergence note (for the runbook)
Staging's secret path now differs from prod: prod = host-ESO direct in ns `cnc`;
staging = host-ESO in ns `cnc-staging-vcluster` + a `fromHost` sync hop into the
vCluster. Names/keys/type identical, mechanism differs — so the staging
acceptance walk proves the agent-session seam but **not** prod's exact secret
delivery.

## Rollback
- Revert the vCluster values (`sync.fromHost.secrets`) + the host-side app +
  restore the in-vCluster ExternalSecrets (drop the `$patch: delete`).
- The vCluster control-plane is NOT reconfigured with any Pro feature, so this
  design cannot crash it the way #651 did (`fromHost.secrets` is core OSS sync).
