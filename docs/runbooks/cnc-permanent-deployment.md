# CNC Permanent Deployment

This runbook describes the operator-controlled phases for the Frank-side CNC
deployment. Git remains the deploy authority: Tekton changes the image tag in
this repository and ArgoCD reconciles the resulting manifests. No workload is
deployed by Tekton directly.

**Validation posture.** This PR is validated OFFLINE only (kustomize / helm
template + schema / yamllint). There is NO live ArgoCD/Tekton validation here —
every live step below is a manual rollout gate.

## GitOps Layout

- `apps/cnc-staging/` is a raw-manifest overlay for the registered
  `cnc-staging` vCluster.
- `apps/cnc-prod/` is a raw-manifest overlay for the host-cluster `cnc`
  namespace.
- `apps/cnc-{staging,prod}-db/` are independent Bitnami PostgreSQL Argo apps.
- `apps/cnc-base/` contains the shared cncd, cnc-fru, node StatefulSet,
  services, PVCs, ESO references, NetworkPolicies, and RBAC.
- IngressRoutes live host-side in `apps/traefik/manifests/ingressroutes.yaml`
  (`traefik-system`) — the host Traefik cannot see CRs inside the vCluster, so
  an in-namespace IngressRoute would never reconcile for staging.

## Workload contracts (why the manifests look the way they do)

- **cncd image is distroless** (`gcr.io/distroless/static-debian12:nonroot`,
  `ENTRYPOINT ["/cncd"]`, uid 65532, no shell/PATH). Manifests use
  **`args: ["serve"]` / `args: ["migrate"]` / `args: ["ingest", ...]`** — a
  `command:` would replace the entrypoint and exec a nonexistent binary. cncd
  pods/jobs that mount PVCs set `securityContext: {runAsUser: 65532,
  runAsGroup: 65532, fsGroup: 65532}` so Longhorn RWO volumes are writable.
- **Master key posture: ENV-KEY (deliberate).** cncd reads
  `CNCD_SECRETS_MASTER_KEY` from env (Infisical via ESO), which takes precedence
  over the on-PVC key file. Infisical is the single source of truth; there is no
  root initContainer seeding a key file. Consequence: rotation is an Infisical
  change + pod restart, **not** `cncd rotate-master-key` (which re-seals the
  file path and would be shadowed by the env key). If file-key + in-cluster
  rotation is ever wanted, switch to `CNCD_SECRETS_MASTER_KEY_FILE` on a PVC and
  drop the env var — a conscious re-decision.
- **Forward-auth header.** cncd's `AUTH_HEADER` is set to
  `X-authentik-username` (the header the Authentik outpost emits). The
  `traefik-system/authentik-forwardauth` middleware MUST be configured to copy
  that header to the backend (`authResponseHeaders`), else cncd sees no actor
  and 403s every browser request. Alternative: an Authentik property-mapping
  that emits `X-Forwarded-User` (then leave `AUTH_HEADER` at its default).
- **East-west isolation (SEC-3).** `apps/cnc-base/manifests/networkpolicy.yaml`
  pins cncd:8080 ingress to cnc-fru + cnc-node, and cnc-fru:80 ingress to the
  `traefik-system` pods, so no in-cluster pod can forge the actor header by
  dialing cncd directly. Prod (host `cnc` ns) enforces via Cilium; staging
  enforcement depends on the vCluster's networkPolicy sync (see the bridge
  section) — treat staging isolation as an operator gate.

## The node (agent-session) and the attach plane

- The `cnc-node` StatefulSet serves the **agent-session** endpoint on :8765
  ONLY with `AGENT_SESSION_SERVE=1` **and** `AGENT_SESSION_BIND=0.0.0.0` **and**
  a runner token. The server fails closed on a non-loopback bind with no token,
  so the token (ESO secret `cnc-runner-auth`, mounted as
  `AGENT_SESSION_RUNNER_TOKEN_FILE`) is mandatory — the `:8765` probes/Service
  only pass once it is set. The node image is PUBLIC
  (`ghcr.io/derio-net/multi-agent-shell`) — no imagePullSecret.
- **cncd → node dial (follow-up):** for cncd's agent-session adapter to reach
  the node, cncd must be given the SAME runner token (the client side of the
  Bearer auth) via its adapter config (`CNCD_ACP_ADAPTER` + token env). That
  cncd-side wiring is a cnc-frd concern and is not set here — flag at rollout.
- **Attach plane (deferred).** The interactive Runners-panel shell attaches via
  runs-fr's `term.KubeAttacher` (the `pods/exec` path). The RBAC it needs
  (`apps/cnc-base/manifests/rbac.yaml`: Role `cnc-node-attach` + binding to SA
  `cnc`, granting `pods`/`pods/exec`) is in place, but the **runs-fr gateway
  Deployment that consumes it is deferred to runs-fr#30's live rollout** (it
  needs the runs-fr image/config and live pod-exec). No pretend gateway is
  shipped here.

## Manual Prerequisites

These require operator credentials or live cluster access and are NOT performed
by the deployment PR.

1. Install `stoa-fr-automation` access to `agentic-stoa/cnc-fr`,
   `agentic-stoa/cnc-frd`, and `agentic-stoa/cnc-fru`. The existing
   `github-app-stoa` ClusterGenerator then supplies the staging source token and
   the Tekton mirror token (agentic-stoa installation).
2. **derio-net push token.** Install the GitHub App in `derio-net` with
   `contents:read/write` on `derio-net/frank`. The promotion pipeline pushes
   image-tag bumps using `frank-gitops-push` (ExternalSecret minted from the
   `github-app-derio` ClusterGenerator = the derio-net installation). The mirror
   token cannot push to frank (wrong installation). The pipeline fails closed if
   it cannot push. **Operator decision recorded:** promotion pushes DIRECTLY to
   `main` (no PR, no branch protection gate on that path) — accepted as the
   automation contract; revisit if frank's main gains required checks.
3. Create the Infisical entries consumed by ESO: `CNCD_SECRETS_MASTER_KEY`,
   `GHCR_DOCKERCONFIGJSON`, and `CNC_RUNNER_SESSION_TOKEN`. Operator-managed
   credentials, not committed here.
4. Provision the vCluster from `apps/root/templates/cnc-staging-vcluster.yaml`
   (now sync-wave `-1`, ahead of its DB/app) and register it in ArgoCD as
   destination name `cnc-staging`. Do not commit the generated cluster Secret.
5. **vCluster ingress + secret bridge (design gate).** A vCluster does not
   inherit host CRDs or host ESO secrets, and the host Traefik cannot see CRs
   inside it. Two bridges are required:
   - **Ingress:** the host-side IngressRoute `cnc-staging` (in
     `apps/traefik/manifests/ingressroutes.yaml`) targets the vCluster's
     host-synced Service `cnc-fru-x-cnc-staging-x-cnc-staging` in the
     `cnc-staging` namespace (from `sync.toHost.services.enabled: true`).
     **Confirm the exact synced Service name** against the live vCluster and
     adjust if the vCluster's sync config differs.
   - **Secrets:** the `cnc-base` ExternalSecrets reconcile host-side (fine for
     prod). Inside the staging vCluster they will NOT reconcile without ESO/an
     `infisical` ClusterSecretStore + the generators present in the vCluster, OR
     a host→vCluster Secret sync. Provide one before the staging overlay can pull
     images / read the master key.
   - Also ensure the vCluster has the Traefik CRDs / ESO CRDs its raw overlay
     references (the IngressRoute is host-side, but the ExternalSecrets and
     NetworkPolicies land in the vCluster).
6. Create Authentik proxy providers for `cnc-staging.cluster.derio.net` and
   `cnc.cluster.derio.net`, register them with the embedded outpost, and confirm
   the `traefik-system/authentik-forwardauth` middleware both sees both hosts
   AND forwards `X-authentik-username` to the backend (see the header contract).
7. Create the three Gitea mirror repositories and register GitHub webhooks at
   `webhooks.hop.derio.net`. The existing `agentic-stoa-main-sync` trigger
   mirrors main; the CNC PR triggers run `cnc-ci`.

## CI notes (per-repo)

- `cnc-frd` (Go control plane) — `go test ./...` on **golang:1.25-alpine**;
  go.mod requires go 1.25.7 and a 1.24 image would fail the blocked toolchain
  download.
- `cnc-fru` (Vite/React) — `npm ci && npm test` (vitest) on node:22-alpine.
- `cnc-fr` — deploy artifacts (manifests + demo bundle), **no compile step**;
  CI is mirror + a bundle-presence sanity on alpine (its compose-smoke/parity
  gates live in the repo's own GitHub workflows). `go test ./...` was removed —
  it always failed (no Go).
- `cnc-ci` now posts a dual GitHub+Gitea status (`tekton/ci` context, one
  outcome, deep-linked to the PipelineRun) in a `finally` block — it previously
  reported no GitHub check at all. `github-status` is mandatory; `gitea-status`
  is best-effort.

## Data Safety

- Staging PostgreSQL and the demo data persist across normal syncs.
- `cnc-staging-reseed` is a normal completed Job, not a deploy hook. Delete it
  as the explicit staging-only "conscious act" to request another demo seed. It
  is absent from the prod overlay. An initContainer refreshes the demo bundle
  into a scratch emptyDir, then the cncd image runs `ingest` **in-process**
  (authenticated as admin in-process; no forgeable HTTP identity — the old
  unauthenticated `wget POST /v1/ingest` 403'd). Prod-refusal is env-supplied
  (`CNC_DEPLOYMENT_ENV=staging`, read by cncd) plus the Job's staging-only
  presence — NOT a manifest shell literal.
- **Pending:** today's `cncd ingest` is idempotent (upsert; deletes no rows).
  The destructive purge-and-ingest (audited, prod-refusing) is a **cnc-frd
  subcommand row not yet built**; until it lands, "reset to dummy data" means
  the disposable-DB path, not an in-place purge.
- **Prod is migrate-only and never seeded.** Its PreSync snapshot Job writes a
  single named custom `pg_dump` and verifies THAT file (`test -s "$f"`, not a
  `*.dump` glob that errored on the 2nd rollout), keeping the 7 most recent
  dumps. Longhorn snapshots of `cncd-data` and the master-key material remain a
  separate operator prerequisite (RWO PVCs). **Prod initial data** is imported
  by the operator out-of-band (there is deliberately no seed job on prod); the
  migration hook only advances the schema.
- A failed prod migration blocks the Argo sync. Do NOT auto-rollback against
  real data; restore the verified snapshot and resume only after the migration
  owner confirms the database state.

## Promotion

The `cnc-image-promotion` repository-dispatch trigger expects a payload with
`cncd_tag` and `fru_tag`. It commits the staging image references (pushed to
`derio-net/frank` via `frank-gitops-push`), waits for the staging health gate,
and only then commits the prod references. The trigger does not fire until the
CNC release workflow emits the dispatch.

The quality gate hits cncd's **ungated** `/healthz` in-cluster (not the
external Authentik-fronted URL, which 302s before /healthz and is unroutable
from Tekton). Its default target is the vCluster's host-synced cncd Service
(`cncd-x-cnc-staging-x-cnc-staging.cnc-staging.svc:8080`) — **confirm this synced
name at rollout** (same vCluster bridge as the ingress). The retry budget is
40×15s (10 min), comfortably beyond ArgoCD's ~3-min reconcile poll + migrate +
rollout. Replace `quality-command` with the adapted compose-smoke assertions
once a staging-authenticated smoke path is available to Tekton.

## Verification

Offline checks from the repository root:

```bash
kubectl kustomize apps/cnc-staging/manifests
kubectl kustomize apps/cnc-prod/manifests
helm template root apps/root                    # renders all 5 cnc-* Applications
helm pull vcluster --repo https://charts.loft.sh --version 0.32.1 --untar
helm template cnc-staging ./vcluster \
  -f apps/vclusters/template/values.yaml \
  -f apps/vclusters/cnc-staging/values.yaml     # passes values.schema.json
yamllint -d relaxed apps/cnc-base/manifests apps/cnc-staging/manifests \
  apps/cnc-prod/manifests apps/tekton
```

Live verification is intentionally omitted from this PR. It requires the
operator-controlled prerequisites above and must be performed through ArgoCD,
not direct `kubectl apply`.
