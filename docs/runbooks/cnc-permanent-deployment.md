# CNC Permanent Deployment

This runbook describes the operator-controlled phases for the Frank-side CNC
deployment. Git remains the deploy authority: Tekton changes the image tag in
this repository and ArgoCD reconciles the resulting manifests. No workload is
deployed by Tekton directly.

## GitOps Layout

- `apps/cnc-staging/` is a raw-manifest overlay for the registered
  `cnc-staging` vCluster.
- `apps/cnc-prod/` is a raw-manifest overlay for the host-cluster `cnc`
  namespace.
- `apps/cnc-{staging,prod}-db/` are independent Bitnami PostgreSQL Argo apps.
- `apps/cnc-base/` contains the shared cncd, cnc-fru, node StatefulSet,
  services, PVCs, ESO references, NetworkPolicy, and Authentik-backed route.

## Manual Prerequisites

These steps require operator credentials or live cluster access and are not
performed by the deployment PR.

1. Install `stoa-fr-automation` access to `agentic-stoa/cnc-fr`,
   `agentic-stoa/cnc-frd`, and `agentic-stoa/cnc-fru`. The existing
   `github-app-stoa` ClusterGenerator then supplies the staging source token
   and Tekton mirror token.
2. Install the same GitHub App in `derio-net` with contents read/write access
   to `derio-net/frank`, or provide an equivalent existing automation path.
   The promotion Pipeline intentionally fails if it cannot push the Frank
   GitOps repository.
3. Create the three Infisical entries consumed by ESO:
   `CNCD_SECRETS_MASTER_KEY`, `GHCR_DOCKERCONFIGJSON`, and
   `CNC_RUNNER_SESSION_TOKEN`. Values are operator-managed credentials and are
   not committed here.
4. Provision the vCluster from `apps/root/templates/cnc-staging-vcluster.yaml`
   and register it in ArgoCD as destination name `cnc-staging`. Do not commit
   the generated ArgoCD cluster Secret.
5. Ensure the staging vCluster has the ESO/Infisical and Traefik CRDs needed by
   its raw overlay, or provide an equivalent host-to-vCluster secret/ingress
   bridge. A vCluster does not automatically inherit host-cluster CRDs or
   ExternalSecret values.
6. Create Authentik proxy providers for `cnc-staging.cluster.derio.net` and
   `cnc.cluster.derio.net`, register them with the embedded outpost, and verify
   the existing `traefik-system/authentik-forwardauth` middleware sees both
   hosts.
7. Create the three Gitea mirror repositories and register GitHub webhooks at
   `webhooks.hop.derio.net`. The existing `agentic-stoa-main-sync` trigger
   mirrors main; the CNC PR triggers run `cnc-ci`.

## Data Safety

- Staging PostgreSQL and the bundle PVC persist across normal syncs.
- `cnc-staging-reseed` is a normal completed Job, not a deploy hook. Delete it
  only as an explicit staging-only action to request another demo bundle
  ingest. It never appears in the prod overlay.
- The reseed job currently replaces the bundle files and calls the canonical
  `POST /v1/ingest` endpoint. CNC's supported demo-owned purge operation must
  be added before this is treated as a destructive reset; ingest alone is
  idempotent and does not delete arbitrary rows.
- Prod has no seed job. Its PreSync snapshot Job produces a verified custom
  `pg_dump` on `cnc-prod-snapshots`, then the migration hook runs. Longhorn
  snapshots of `cncd-data` and the master-key material remain an operator
  prerequisite because those PVCs are RWO.
- A failed prod migration blocks the Argo sync. Do not auto-rollback against
  real data; restore the verified snapshot and resume only after the migration
  owner confirms the database state.

## Promotion

The `cnc-image-promotion` repository-dispatch trigger expects a payload with
`cncd_tag` and `fru_tag`. It commits the staging image references, waits for
the configured staging health gate, and only then commits the prod references.
The trigger does not run until the CNC release workflow emits the dispatch;
this avoids guessing whether separate cncd and cnc-fru tags are compatible.

The default gate is health-only until a staging-authenticated smoke endpoint is
available to Tekton. Replace the PipelineRun's `quality-command` with the
adapted compose-smoke assertions once the staging URL and authentication
contract are provisioned.

## Verification

Offline checks from the repository root:

```bash
kubectl kustomize apps/cnc-staging/manifests
kubectl kustomize apps/cnc-prod/manifests
helm template root apps/root
yamllint -d relaxed apps/cnc-base/manifests apps/cnc-staging/manifests apps/cnc-prod/manifests
```

Live verification is intentionally omitted from this PR. It requires the
operator-controlled prerequisites above and must be performed through ArgoCD,
not direct `kubectl apply`.
