# AWX on Frank — Design

**Status:** Draft
**Layer:** `auto` (Infrastructure Automation, number 20 — new layer)
**Spec date:** 2026-05-26

## Goal

Deploy AWX (the upstream Ansible automation controller) onto Frank as a new
capability layer. AWX provides a web UI + API + task engine for running Ansible
playbooks against hosts. On Frank it serves as the **imperative counterweight to
a declarative cluster**: Ansible reaches the edges that Talos (immutable OS, no
SSH/package manager) and ArgoCD (GitOps) cannot — non-Talos home-lab and
external devices (network gear, NAS, the home router/egress, IoT, other
non-Talos boxes).

The layer is also explicitly an experiment, true to Frank's "the cluster will
have opinions" philosophy: deploy imperative Ansible alongside the declarative
machinery and let the work decide whether it earns a permanent place.

## Motivation

Everything Frank runs today is declarative — Talos machine config via patches,
all workloads via ArgoCD App-of-Apps. That model has a hard boundary: it can
only manage what speaks Talos or Kubernetes. Devices on the home LAN that are
not part of the cluster (switches, the router, a NAS, IoT) have no declarative
control plane here. AWX fills that gap with the opposite paradigm — SSH in, run
a playbook, converge state imperatively.

Deploying competing paradigms side by side and letting the work decide is the
operating philosophy. This layer makes that tension concrete and observable.

## Decisions (locked during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| What AWX automates | Non-Talos external/home-lab devices + learning experiment | The edges GitOps can't reach; doubles as a paradigm experiment |
| Deployment method | AWX Operator via ArgoCD | The only path Ansible officially supports; fits App-of-Apps |
| Postgres | Operator-managed | Officially blessed, one less app, operator owns version/lifecycle |
| Auth | AWX native OIDC → Authentik | Group→team RBAC mapping; richer than forward-auth for an automation controller |
| Exposure | Internal LB IP + `awx.cluster.derio.net` + homepage tile | Matches in-cluster services; no public exposure |

## Architecture

ArgoCD App-of-Apps adds one app, `apps/awx/`, as a **multi-source** Application:

- Upstream `awx-operator` Helm chart (version-pinned) + `$values/apps/awx/values.yaml`
- `apps/awx/manifests/awx.yaml` — the `AWX` custom resource (raw manifest, same source ref)

The operator runs in the `awx` namespace and reconciles the AWX web + task
Deployments, the Service, and DB migrations from the `AWX` CR. This is a
**two-layer reconciliation**: ArgoCD owns the operator chart and the `AWX` CR;
the awx-operator owns the runtime workload (pods, Postgres StatefulSet,
internal Service).

```
ArgoCD (root App-of-Apps)
  └── apps/awx (Application, multi-source)
        ├── awx-operator Helm chart  ──► awx-operator Deployment
        └── apps/awx/manifests/awx.yaml (AWX CR)
                                       ──► awx-operator reconciles:
                                             • awx-web Deployment
                                             • awx-task Deployment
                                             • Postgres StatefulSet (operator-managed)
                                             • awx Service (ClusterIP)
```

### Implications of two-layer reconciliation

- **`Synced/Healthy` in ArgoCD does NOT mean AWX is running.** ArgoCD reports the
  app healthy the moment the operator + CR exist; the operator then does the real
  work asynchronously (image pulls, migrations, pod startup can take minutes).
  This is the documented Frank trap — a layer is not Deployed until its workflow
  is observed end-to-end (see Testing).
- Operator-created resources (pods, StatefulSet, internal Service) are **not in
  Git** — ArgoCD does not track them. That's expected.
- The operator generates Kubernetes Secrets for the admin password and Django
  secret key if not supplied. To keep the layer reproducible we supply these via
  SOPS (see Secrets). `ignoreDifferences` on Secret `/data` per repo principle.
- **CRD-before-CR ordering.** The awx-operator Helm chart installs the `AWX`
  CRD; the `AWX` CR cannot apply until that CRD exists. With both in one
  Application this is a first-sync race. Mitigate with ArgoCD sync waves (operator
  chart in an earlier wave than the CR) and/or `SkipDryRunOnMissingResource=true`
  on the CR manifest. Confirm a clean first sync on an empty namespace at deploy.

## Components

| Piece | Owner | Notes |
|---|---|---|
| awx-operator | ArgoCD (Helm) | Version-pinned, like all other charts |
| `AWX` CR | ArgoCD (raw manifest) | Declares replicas, `ingress_type: none`, postgres config, OIDC settings refs |
| awx-web / awx-task Deployments | awx-operator | Reconciled from the CR; not in Git |
| Postgres StatefulSet + PVC | awx-operator | Operator-managed; Longhorn-backed |
| awx Service (ClusterIP) | awx-operator | Fronted by the shared Traefik IngressRoute (added by us); no dedicated LB IP |
| Bootstrap secrets | **SOPS, out-of-band** | admin password, Django secret key, OIDC client secret |
| Authentik OIDC provider + Application | ArgoCD (blueprint) | New blueprint in `apps/authentik-extras/` |

## Auth — AWX native OIDC → Authentik

AWX uses its **built-in OIDC** (`SOCIAL_AUTH_OIDC_*` settings), pointed at
Authentik. This is deliberately **not** the `authentik-forwardauth` Traefik
middleware that other cluster services use — AWX handles its own login redirect,
which lets Authentik groups map to AWX teams/roles for real RBAC.

- New Authentik **OAuth2/OpenID provider + Application** defined as a blueprint
  in `apps/authentik-extras/manifests/` (model it on
  `blueprints-provider-infisical.yaml` — confidential client, `redirect_uris`,
  scope mappings) and registered in
  `apps/authentik/values.yaml → blueprints.configMaps`.
- AWX configured (via CR `extra_settings` / a settings ConfigMap or Secret) with
  the Authentik OIDC endpoint, client key, and client secret (secret from SOPS).
  *Verify at implementation:* confirm the pinned awx-operator/AWX version still
  drives OIDC via `SOCIAL_AUTH_OIDC_*` in `extra_settings` — recent AWX has been
  migrating some auth config to the DB-backed Settings → Authentication flow.
- Authentik group → AWX team mapping so group membership drives AWX RBAC.
- AWX keeps a local `admin` account for API access and break-glass.

**Host / redirect-URI:** AWX serves at **`awx.cluster.derio.net`** (the domain
that actually routes — every IngressRoute and homepage tile uses
`*.cluster.derio.net`). The Authentik provider's `redirect_uris` and
`meta_launch_url` MUST use this same host so the OAuth callback resolves. Note:
`*.frank.derio.net` is the **legacy** domain, being deprecated — only
`omni.frank.derio.net` should keep it. Existing OIDC blueprints (infisical,
argocd) still register `*.frank.derio.net` callbacks; those are stragglers
slated for cleanup, not the convention. AWX uses `cluster.derio.net` everywhere;
do not copy the `frank.derio.net` host.

**Divergence note:** because this is native OIDC, the Traefik IngressRoute does
**not** carry the `authentik-forwardauth` middleware, and there is **no**
embedded-outpost provider-assignment step (that manual ORM step applies only to
proxy/forward-auth providers — a pure OIDC provider does not touch the outpost).
Both are intentional; document so future readers don't "fix" them.

## Exposure

- **No dedicated LoadBalancer IP.** AWX is a web UI, so it follows the universal
  Frank pattern: the AWX Service stays `ClusterIP` and is reached through the
  shared Traefik LB (192.168.55.220). A standalone Cilium LB IP would be
  redundant (only raw-TCP/non-HTTP services need their own IP).
- Traefik IngressRoute at **`awx.cluster.derio.net`** → AWX `ClusterIP` Service
  (no forward-auth middleware, see Auth).
- Homepage tile in `apps/homepage/manifests/configmap-services.yaml` under an
  Automation category (icon, description, URL).
- **No public exposure.** AWX is internal/mesh-only; it is never fronted by the
  Hop Caddy edge.

## Secrets & inventory

- **Bootstrap secrets** (AWX admin password, Django secret key, OIDC client
  secret) are SOPS-encrypted, applied out-of-band from `secrets/`, and
  documented as a `# manual-operation` block in the plan (synced to the central
  runbook via `/sync-runbook`). Per repo principle, SOPS secrets are NOT
  ArgoCD-managed.
- **OIDC client_secret injection (second manual-op).** Authentik blueprints do
  not carry the OAuth2 `client_secret` (see `blueprints-provider-infisical.yaml`:
  "client_secret is set via Authentik Admin UI"). So beyond the AWX bootstrap
  secret, there is a separate manual step to set the provider's `client_secret`
  in Authentik (UI or API) to match the value AWX reads from SOPS. Document this
  as its own `# manual-operation` block.
- **Managed-host credentials** (SSH keys, sudo/become passwords for the devices
  AWX manages) live inside **AWX's own encrypted credential store** (Machine
  Credentials), NOT in SOPS or Kubernetes Secrets. Credential storage is AWX's
  core job and keeps the cluster out of the loop.
- **Device inventory** is configured in-app after deploy, not in Git. The
  inventory of imperative external devices is imperative state by nature; it does
  not belong in the declarative repo. Playbooks are pulled at runtime from Gitea
  via an AWX SCM Project.

## Storage

- Operator-managed Postgres PVC on **Longhorn** (default StorageClass, replica
  count 3). The operator deploys Postgres as a StatefulSet, so the RWO PVC +
  RollingUpdate deadlock does not apply (StatefulSets recreate pods one at a
  time, and the single-replica DB pod terminates before its replacement binds
  the volume).
- No AWX Projects PVC — playbooks are pulled from Gitea SCM at runtime, so the
  default `emptyDir`/ephemeral project storage is sufficient.

## Testing / "Deployed" gate

Per the standing rule that a layer is not Deployed until its workflow runs
end-to-end (ArgoCD `Synced/Healthy` is necessary but not sufficient), the
done-criteria are:

1. awx-operator reconciles AWX web + task pods to `Running`; DB migrations
   complete (operator logs / `kubectl get awx -n awx` shows the CR reconciled).
2. UI reachable at `awx.cluster.derio.net`.
3. Authentik OIDC login succeeds end-to-end — a real browser login through
   Authentik lands in AWX, and a test user's Authentik group maps to the
   expected AWX team/role.
4. One smoke playbook (e.g. an Ansible `ping` against a single real non-Talos
   host) runs green from an AWX Job Template.

Only after step 4 does the `auto` layer move to **Deployed**.

## Out of scope (YAGNI)

- Custom Execution Environments (use the default EE).
- Receptor mesh / multi-node execution.
- Full device inventory build-out (configured incrementally in-app post-deploy).
- Public exposure via Hop.
- Dedicated `awx-db` Postgres app (operator-managed Postgres chosen instead).
- Backups of the AWX Postgres DB — revisit once AWX holds real, hard-to-rebuild
  state (inventories, credentials, job history).

## Post-deploy checklist (standard layer)

This is a user-facing new layer, so the full post-deploy sequence applies:
expose externally (IngressRoute + homepage tile — already in the design),
building blog post, operating blog post, README update, runbook sync (the SOPS
bootstrap is a manual-operation), register the `auto` layer in
`docs/layers.yaml` and the roadmap shortcode, and set Status to Deployed.
