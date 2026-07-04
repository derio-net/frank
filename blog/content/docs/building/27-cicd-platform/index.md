---
title: "CI/CD Platform — Gitea, Tekton, Zot, and Cosign"
series: ["building"]
layer: cicd
date: 2026-04-13
draft: false
tags: ["cicd", "gitea", "tekton", "zot", "cosign", "oci", "pipelines", "supply-chain", "kaniko"]
summary: "Deploying a full Kubernetes-native CI/CD platform on pc-1 — Gitea for git mirroring, Tekton for pipelines, Zot for container images, and cosign for supply chain signing."
weight: 28
---

For 25 layers, every container image Frank ran came from somewhere else — Docker Hub, GitHub Container Registry, upstream Helm charts. The cluster consumed images but never built them. That's fine for adoption, but it means the cluster has no opinion about what it runs. No local builds, no signature verification, no audit trail from commit to deployment.

This post changes that. We deploy a complete CI/CD platform on pc-1: **Gitea** mirrors GitHub repos locally, **Tekton** runs webhook-driven pipelines, **Zot** stores OCI container images, and **cosign** signs every image that comes out the other end. All four components are ArgoCD-managed, secrets flow through Infisical, and the whole thing runs on a single worker node with local storage.

## Architecture

```
GitHub ──pull mirror──> Gitea (192.168.55.209)
                          │
                     webhook (push)
                          │
                    Tekton EventListener
                          │
              ┌───────────┴───────────┐
              │    gitea-ci Pipeline   │
              ├─ clone (git-clone)     │
              ├─ test (run-tests)      │
              ├─ build (Kaniko)────────┼──push──> Zot (192.168.55.210)
              ├─ sign (cosign)─────────┼──sign──> Zot (signature)
              └─ report status─────────┼──POST──> Gitea commit status
                                       │
                    Tekton Dashboard (192.168.55.217)
```

Every component runs on pc-1 — the legacy desktop with 32GB RAM that previously sat idle in the Edge zone. A dedicated `longhorn-cicd` StorageClass pins PVCs to that node with single-replica storage. Not HA, but CI/CD pipelines are ephemeral — if pc-1 goes down, builds queue until it comes back.

## Prerequisites

The CI/CD layer builds on top of existing infrastructure:

- **Longhorn** — persistent storage for Gitea repos and Zot image blobs
- **Cilium L2** — LoadBalancer IPs for all three services
- **Infisical + ExternalSecrets** — secrets for admin passwords, API tokens, push credentials
- **cert-manager** — self-signed TLS certificate for the Zot registry
- **Authentik** — OIDC SSO for Gitea, forward-auth proxy for Tekton Dashboard

## StorageClass: longhorn-cicd

Before deploying anything, we need a StorageClass that pins storage to pc-1. CI/CD data doesn't need 3-replica replication — the repos are mirrors (GitHub is the source of truth), the registry images are rebuilt from source, and pipeline workspaces are ephemeral:

```yaml
# apps/longhorn/manifests/storageclass-longhorn-cicd.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: longhorn-cicd
provisioner: driver.longhorn.io
reclaimPolicy: Delete
volumeBindingMode: Immediate
allowVolumeExpansion: true
parameters:
  numberOfReplicas: "1"
  dataLocality: best-effort
  nodeSelector: "kubernetes.io/hostname:pc-1"
```

Single replica, pinned to pc-1. Longhorn still manages the volume lifecycle, but it won't replicate across the cluster.

## Gitea — Self-Hosted Git Forge

Gitea is a lightweight Git forge — think self-hosted GitHub without the enterprise pricing. We use it purely as a **pull mirror**: it clones repositories from GitHub on a 10-minute interval, giving Tekton a local source to clone from without depending on external network access.

### Deployment

Gitea deploys via the upstream Helm chart (v11.0.3) with SQLite (no PostgreSQL for a single-user homelab), Longhorn-CICD storage, and Authentik OIDC for SSO:

```yaml
# apps/gitea/values.yaml (key excerpts)
gitea:
  admin:
    existingSecret: gitea-secrets

  config:
    server:
      DOMAIN: 192.168.55.209
      ROOT_URL: http://192.168.55.209:3000/
      SSH_PORT: 2222

    service:
      DISABLE_REGISTRATION: false
      ALLOW_ONLY_EXTERNAL_REGISTRATION: true

    mirror:
      ENABLED: true
      DEFAULT_INTERVAL: 10m

    webhook:
      ALLOWED_HOST_LIST: "*.svc.cluster.local"

persistence:
  enabled: true
  size: 10Gi
  storageClass: longhorn-cicd

strategy:
  type: Recreate   # RWO PVC — can't rolling-update

postgresql:
  enabled: false
```

Two important details: `ALLOW_ONLY_EXTERNAL_REGISTRATION: true` means only Authentik OIDC users can create accounts (no local signup form), and `webhook.ALLOWED_HOST_LIST` must include `*.svc.cluster.local` or Gitea silently drops outgoing webhook delivery to in-cluster services like the Tekton EventListener.

### Authentik OIDC

Gitea's OAuth integration uses the `gitea.oauth` section in Helm values. The Authentik provider and application are created via a setup script that calls the Authentik API to create an OAuth2 provider with the correct redirect URI (`http://192.168.55.209:3000/user/oauth2/authentik/callback`). The client secret is stored in Infisical and synced via ExternalSecret.

After deployment, clicking "Sign in with authentik" on the Gitea login page redirects to the Authentik login flow. On first login, Gitea auto-creates a linked account.

### GitHub Mirror

With Gitea running, we create a pull mirror of the frank repo via the migration API:

```bash
curl -sf -X POST "$GITEA_URL/api/v1/repos/migrate" \
  -H "Authorization: token $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "clone_addr": "https://github.com/derio-net/frank.git",
    "repo_name": "frank",
    "repo_owner": "tekton-bot",
    "service": "github",
    "mirror": true,
    "mirror_interval": "10m"
  }'
```

A `tekton-bot` service account owns the mirror and has an API token stored in Infisical for pipeline status reporting. The mirror syncs every 10 minutes — fast enough for CI, without hammering GitHub's API.

{{< screenshot src="gitea-pull-mirrors.png" caption="The tekton-bot/frank pull mirror in Gitea — mirror badge in the title, freshly synced from GitHub" >}}

## Tekton — Kubernetes-Native Pipelines

Tekton is a K8s-native CI/CD engine — pipelines are CRDs, each step runs in its own container, and workspaces are PVCs. No external CI server, no agents phoning home, no YAML DSL wrapping shell scripts. Just Kubernetes resources.

### Core Components

Three vendored release YAMLs deployed as separate ArgoCD apps:

| Component | Version | What It Does |
|-----------|---------|-------------|
| Tekton Pipelines | v0.65.2 | Pipeline controller, CRDs (Task, Pipeline, PipelineRun) |
| Tekton Triggers | v0.28.1 | EventListener, TriggerBinding, TriggerTemplate |
| Tekton Dashboard | v0.52.0 | Web UI for viewing pipelines and logs |

The vendored YAML approach (downloading release manifests into the repo) keeps Tekton under ArgoCD management without needing a Helm chart. The dashboard gets a separate Cilium L2 LoadBalancer at `192.168.55.217:9097`.

### EventListener and Triggers

The EventListener receives webhooks from Gitea, extracts push event data, and creates PipelineRuns:

```yaml
# apps/tekton/triggers/eventlistener.yaml (simplified)
apiVersion: triggers.tekton.dev/v1beta1
kind: EventListener
metadata:
  name: gitea-listener
  namespace: tekton-pipelines
spec:
  triggers:
    - name: gitea-push
      interceptors:
        - ref:
            name: "cel"
          params:
            - name: "filter"
              value: >-
                header.match('X-Gitea-Event', 'push')
            - name: "overlays"
              value:
                - key: branch_name
                  expression: "body.ref.split('/')[2]"
      bindings:
        - ref: gitea-push-binding
      template:
        ref: gitea-pipeline-template
```

One important gotcha: the plan originally used the `github` ClusterInterceptor for webhook validation, but Gitea sends `X-Gitea-Event` headers instead of `X-GitHub-Event`. The GitHub interceptor silently drops anything without the expected header. We switched to a CEL interceptor that explicitly matches `X-Gitea-Event: push`.

The TriggerTemplate creates a PipelineRun with a `longhorn-cicd` PVC workspace, and sets `fsGroup: 65534` on the pod security context so non-root containers can write to the volume.

### The gitea-ci Pipeline

The pipeline has three stages, each gated so it works for test-only repos (no Dockerfile) and build repos alike:

**Stage A — Clone and Test:**
- `git-clone` (vendored from Tekton catalog) checks out the repo
- `run-tests` runs a configurable test command

**Stage B — Build and Push (optional):**
- `build-push` uses Kaniko to build a container image and push to Zot
- Skipped when `image` param is empty (test-only repos)

**Stage C — Sign (optional):**
- `cosign-sign` signs the pushed image with a private key
- Skipped alongside Stage B

**Finally block:**
- `report-success` or `report-failure` — posts commit status back to Gitea via the API
- Accepts both `"Succeeded"` and `"Completed"` as success states (Tekton reports `"Completed"` when tasks are skipped via `when` clauses)

```yaml
# apps/tekton/pipelines/gitea-ci.yaml (structure)
spec:
  tasks:
    - name: clone       # Always runs
    - name: test        # Always runs (after clone)
    - name: build-push  # Conditional: only if image param is set
    - name: sign        # Conditional: only if image param is set
  finally:
    - name: report-success  # When tasks succeeded/completed
    - name: report-failure  # When tasks failed
```

{{< screenshot src="tekton-pipelinerun.png" caption="Tekton Dashboard: a gitea-ci PipelineRun showing all stages completed" >}}

## Zot — OCI Container Registry

Zot is a minimal, OCI-native container registry — no Docker distribution overhead, no authentication proxies, just a single Go binary that speaks the OCI Distribution Spec. It runs on pc-1 with cert-manager TLS and htpasswd-based push authentication.

### TLS with cert-manager

The registry needs HTTPS — containerd (via Talos) won't pull from plain HTTP registries without explicit mirror configuration, and cosign refuses to sign over insecure connections by default. A self-signed ClusterIssuer generates a certificate with the registry's IP address as a SAN:

```yaml
# apps/zot/manifests/certificate.yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: zot-tls
  namespace: zot
spec:
  secretName: zot-tls
  issuerRef:
    name: selfsigned-issuer
    kind: ClusterIssuer
  ipAddresses:
    - "192.168.55.210"
  dnsNames:
    - "zot.frank.local"
```

### Registry Configuration

Zot's config lives in the Helm values as `configFiles.config.json`:

```json
{
  "storage": {
    "rootDirectory": "/var/lib/registry",
    "dedupe": true,
    "gc": true,
    "gcInterval": "1h"
  },
  "http": {
    "address": "0.0.0.0",
    "port": "5000",
    "tls": {
      "cert": "/etc/zot/tls/tls.crt",
      "key": "/etc/zot/tls/tls.key"
    }
  },
  "http.auth": {
    "htpasswd": {
      "path": "/etc/zot/auth/htpasswd"
    }
  }
}
```

Push operations require htpasswd authentication (the `tekton-push` user), but read operations are anonymous — any node can pull images without credentials. The htpasswd file is mounted from a Secret containing a bcrypt hash of the push password.

### Containerd Mirror

For the cluster nodes to pull images from `192.168.55.210:5000`, we apply a Talos machine config patch that registers the registry as a containerd mirror:

```yaml
# patches/phase06-cicd/06-cluster-zot-registry.yaml
machine:
  registries:
    mirrors:
      192.168.55.210:5000:
        endpoints:
          - https://192.168.55.210:5000
    config:
      192.168.55.210:5000:
        tls:
          insecureSkipVerify: true
```

The `insecureSkipVerify: true` handles the self-signed cert at the containerd level. Every node in the cluster gets this patch via Omni, so any pod can reference images from the local registry.

## Cosign — Supply Chain Signing

The final pipeline stage signs every image pushed to Zot using cosign. The signing key is generated offline (`cosign generate-key-pair`), the private key stored in Infisical via ExternalSecret, and the public key committed to the repo at `apps/tekton/cosign.pub`.

```yaml
# apps/tekton/tasks/cosign-sign.yaml (simplified)
steps:
  - name: sign
    image: gcr.io/projectsigstore/cosign:v2.4.1
    args:
      - "sign"
      - "--key"
      - "/cosign/cosign.key"
      - "--tlog-upload=false"
      - "--allow-insecure-registry"
      - "$(params.image)"
    volumeMounts:
      - name: cosign-key
        mountPath: /cosign
        readOnly: true
```

`--tlog-upload=false` disables Rekor transparency log upload — this is a private registry, not a public supply chain. `--allow-insecure-registry` handles the self-signed TLS. The cosign task also needs Zot push credentials (mounted at `/docker`) because signing pushes a `.sig` artifact alongside the image.

Verification from any machine with the public key:

```bash
cosign verify --key apps/tekton/cosign.pub \
  --insecure-ignore-tlog --allow-insecure-registry \
  192.168.55.210:5000/test/myapp:latest
```

```console
$ cosign verify --key /Users/derio/Docs/projects/DERIO_NET/frank/apps/tekton/cosign.pub --insecure-ignore-tlog --allow-insecure-registry 192.168.55.210:5000/test/ci-hello:v3 2>&1 | head -20
WARNING: Skipping tlog verification is an insecure practice that lacks transparency and auditability verification for the signature.

Verification for 192.168.55.210:5000/test/ci-hello:v3 --
The following checks were performed on each of these signatures:
  - The cosign claims were validated
  - The signatures were verified against the specified public key

[{"critical":{"identity":{"docker-reference":"192.168.55.210:5000/test/ci-hello"},"image":{"docker-manifest-digest":"sha256:e63bfc1c8d77ab62d5e12d13f0018ac77b85f01d15742e22215823752b678234"},"type":"cosign container image signature"},"optional":null}]
```

## Gotchas and Lessons

### Tekton v1 CRD: computeResources, Not resources

Tekton v1 Tasks use `computeResources` for step resource limits, not `resources`. The `resources` field silently fails schema validation, causing an ArgoCD `ComparisonError` that blocks all syncs for the tekton-extras app. A subtle one — no error in Tekton itself, just ArgoCD refusing to render.

### PodSecurity Restricted Namespace

The vendored Tekton Pipelines release YAML sets `pod-security.kubernetes.io/enforce: restricted` on the `tekton-pipelines` namespace. This blocks Kaniko (needs privileged-ish access to build images). We patched the vendored release to use `baseline` instead. A standalone namespace label override in tekton-extras didn't work — the tekton-pipelines ArgoCD app overwrites it on every sync.

### Gitea Webhooks to In-Cluster Services

Gitea's default `webhook.ALLOWED_HOST_LIST` blocks all outgoing webhook delivery. The webhook appears to send successfully in the Gitea UI, but the request never reaches the EventListener. Add `*.svc.cluster.local` to the allowlist.

### HOME=/ for Non-Root Containers

Tekton Tasks running as UID 65534 (nobody) get `HOME=/` from `/etc/passwd`. Since `/` is read-only, any command that writes to `$HOME` fails — including `git config --global`. Fix: set `env: [{name: HOME, value: /tekton/home}]` on the step.

### $(tasks.status) Returns "Completed", Not "Succeeded"

When pipeline tasks are skipped via `when` clauses (like build-push when no Dockerfile), Tekton reports the overall status as `"Completed"` rather than `"Succeeded"`. The `finally` block must check for both values, or success pipelines get reported as failures.

### Kaniko Docker Config Naming

Kaniko reads `$DOCKER_CONFIG/config.json`, but `kubernetes.io/dockerconfigjson` Secrets mount the file as `.dockerconfigjson`. The ExternalSecret template needs to output both keys, or Kaniko silently fails authentication and pushes fail with `401 Unauthorized`.

### `lbipam.cilium.io/ips` Is Not a Sharing Directive *(retroactively added 2026-05-09)*

The Gitea chart splits HTTP and SSH into two separate `Service` objects (`gitea-http` :3000 and `gitea-ssh` :2222). The original values requested both share a single LB IP by annotating each with `lbipam.cilium.io/ips: "192.168.55.209"`. That annotation alone tells Cilium L2 IPAM *which* IP to allocate — it does **not** tell IPAM that two Services intend to share. So IPAM gave the IP to whichever Service it processed first (`gitea-http` won) and left the other in `EXTERNAL-IP <pending>` indefinitely.

Effect: `192.168.55.209:2222` returned "no route to host" from anywhere outside the cluster for the entire 41-day life of the layer. In-cluster pipelines were unaffected because they clone via `gitea-http.gitea.svc.cluster.local:3000`, but operator workstations couldn't `git@gitea.cluster.derio.net:repo.git` at all. The bug stayed latent because nothing in the cluster's hot path used SSH — only humans did, and humans had been quietly using HTTPS instead.

Fix is two lines: add `lbipam.cilium.io/sharing-key: "gitea"` to both Service annotation blocks. That's Cilium's documented mechanism for letting separate Services share an LB IP when their port sets don't conflict. After the change, `gitea-ssh` got `192.168.55.209` and the SSH endpoint actually answered for the first time. The lesson: when the upstream chart splits one logical service into multiple `Service` objects, the only correct way to pin them to a shared IP is the sharing-key annotation. The `ips:` annotation is a request, not a coordination mechanism.

## Direction Inversion: GitHub-primary for agentic-stoa repos *(retroactively added 2026-05-13)*

Everything above describes the original direction: **Gitea is the PR surface** (mirror of GitHub), Tekton webhooks fire on Gitea pushes, status posts go back to Gitea. That works fine when humans (or `git push`) are the only thing opening PRs — Frank itself uses this model for its own repo to this day.

It does **not** work when [Paperclip AI](https://github.com/embedded-cc/paperclip-ai) is opening PRs on the agentic-stoa org's repos. Paperclip's repository-management code paths only speak the GitHub REST API — there is no pluggable backend, no "Gitea provider", no abstraction. The agent literally cannot open a PR on Gitea.

So for the three repos under `agentic-stoa/*` (`hum`, `content-factory`, `stoa-blog`) we inverted the direction. **GitHub becomes the source of truth and the PR surface; Gitea becomes a CI replica.** Same Gitea/Tekton substrate, opposite arrows.

### Architecture (inverted slice)

```
GitHub (agentic-stoa/*)
   │
   ├─ webhook (PR sync, push to main) ──┐
   │                                    │
   │                              webhooks.hop.derio.net   ←  Caddy on Hop
   │                                    │                    (DNS-01 ACME, validates HMAC,
   │                                    │                     forwards X-Hub-Signature-256)
   │                                    ▼
   │                            Tailscale mesh (--accept-routes)
   │                                    │
   │                                    ▼
   │                       el-github-listener (192.168.55.223:8080)
   │                              │
   │                              ├─ TriggerTemplate: github-pull-sync
   │                              │      ↓
   │                              │   pulls refs/pull/N/head (or refs/heads/main)
   │                              │   from GitHub, force-pushes to Gitea
   │                              │      ↓
   │                              ├─ TriggerTemplate: <repo>-ci
   │                              │      ↓
   │                              │   clone (Gitea) → test → finally:
   │                              │      ├─ github-status (mandatory)  → POST  api.github.com  ──┐
   │                              │      └─ gitea-status (best-effort) → POST  192.168.55.209    │
   │                              │                                                              │
   ▲                                                                                             │
   └────────────────  tekton/ci status check appears on the PR  ─────────────────────────────────┘
```

Two webhook events drive the chain:

- **`pull_request` (opened, synchronized, reopened)** → fire pull-sync (carrying the PR head SHA) → fire `<repo>-ci` for that SHA.
- **`push` to `refs/heads/main`** → fire pull-sync only (no CI run; main is post-merge, already vetted by the PR-time CI).

The `pull_request` event uses the synthetic ref `refs/pull/N/head` that GitHub maintains for every PR — that's the only ref guaranteed to exist for cross-fork PRs and Paperclip's headless workflow. We force-push it to Gitea verbatim; Gitea then has a checkout-able branch named `refs/pull/N/head` (the slash makes it ugly in the UI but the API treats it like any other ref).

### Why a Caddy relay on Hop

GitHub's webhook deliveries originate from the public internet. Frank's EventListener (`el-github-listener`) lives on the LAN at `192.168.55.223:8080` — not reachable from the outside. Three options:

1. **Public-LB the EventListener.** Tempting but wrong: it punctures the LAN-only posture for a single public-traffic source, and the EventListener's HMAC handling would then face the entire internet. Also Frank's home connection has a CGN'd IP — no clean inbound port exposure.
2. **Cloudflare Tunnel from Frank.** Works but adds a dependency we don't want for one path. We already have public ingress at Hop via Caddy + Cloudflare DNS-01.
3. **Caddy reverse-proxy on Hop, mesh-forward to Frank.** Reuse the cluster we already have at the public edge; Hop is in the Tailscale mesh; Frank exposes the EventListener on a mesh-routable LB IP.

(3) won. The relay is `webhooks.hop.derio.net` → `reverse_proxy 192.168.55.223:8080` over Tailscale. Caddy is what validates TLS to GitHub (Cloudflare DNS-01 cert) and forwards the GitHub-signed payload verbatim, including `X-Hub-Signature-256`, `X-GitHub-Event`, `X-GitHub-Delivery`. The EventListener's `github` ClusterInterceptor then re-validates the HMAC against the same shared secret. **Two layers checking the same signature is intentional** — Caddy's check rejects garbage at L7 before it hits Tekton's quota, the EventListener's check is the authoritative one.

The one operational gotcha for the relay path: Hop needs `--accept-routes` in its Tailscale args for `192.168.55.0/24` to actually route through the mesh subnet router. We discovered this when Caddy started returning 502 on the new route — `nc 192.168.55.223 8080` from inside the Caddy pod failed, but `tailscale ping <frank-node>` worked. The flag flip was a one-line change to `clusters/hop/apps/headscale/manifests/tailscale-client.yaml`.

### Dual-status anti-drift design

The hardest thing about a CI replica is **keeping the two surfaces from disagreeing about whether a build passed.** If GitHub says green and Gitea says red, every operator looking at Gitea will think the build failed — and any other system reading either commit-status API gets contradictory data. We solved this by making the two posts share a code path:

- Both `github-status` and `gitea-status` Task invocations live in the **single `finally` block** of the per-repo CI Pipeline. Tekton evaluates `$(tasks.status)` once and substitutes that string into both `params: state:` values — there is no way for the two posts to disagree on success/failure.
- Both posts use the same `context: tekton/ci` label.
- Both refer to the same git SHA. Git's content-addressing guarantees that the byte-for-byte identical commit GitHub receives at PR open time is the same SHA Gitea receives via `git push --force-with-lease` from pull-sync (the SHA is the hash of the commit, not the location).
- `github-status` is mandatory — if the GitHub API call fails, the entire PipelineRun is marked failed and a human gets paged. `gitea-status` is best-effort (`onError: continue`) — if Gitea is transient-down, GitHub stays correct and the only consequence is Gitea showing a stale state until the next CI run.

Tradeoff: making both mandatory was tempting (full bidirectional consistency) but Gitea's role here is observability for operators browsing the replica, not a critical-path service. A flake in Gitea's API shouldn't fail an otherwise green build.

### The fourth Pipeline: `github-pull-sync`

The other interesting piece is the pull-sync Pipeline. Two design choices worth flagging:

**Inlined fetch+push, not the catalog `git-clone` Task.** The catalog task does a shallow clone into a workspace — fine for CI, useless for a sync that needs *both* refs (the PR head and the existing Gitea state). And the catalog task doesn't accept `depth: 0` (passes through to `git clone --depth=0` which fails: "depth 0 is not a positive number"). Pull-sync is ~30 lines of bash that fetches the relevant ref from GitHub with token auth and force-pushes to Gitea over SSH.

**Token-auth URL for the GitHub fetch, SSH for the Gitea push.** GitHub: `https://x-access-token:${GITHUB_TOKEN}@github.com/<org>/<repo>.git` — the token-prefix URL is the simplest way to thread the PAT through a non-interactive `git fetch`, and it works regardless of which repo we're syncing (the same token has access to all three under the agentic-stoa org). Gitea: SSH with stoa-bot's key. We tried bidirectional token auth first; Gitea's HTTPS push path goes through extra middleware that occasionally produced spurious 500s, while SSH was rock-stable.

One trap that cost us four fix loops: `GIT_SSH_COMMAND` must point explicitly at `$HOME/.ssh/id_rsa` because the Tekton pod runs as the `nobody` UID (65534), and OpenSSH's default key lookup walks `~/.ssh/id_*` against the pod's `/etc/passwd` HOME for that UID — which is `/`, where there's no readable `~/.ssh`. Setting `GIT_SSH_COMMAND="ssh -i $HOME/.ssh/id_rsa -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"` and then explicitly setting `HOME=/tekton/home` (so `$HOME` interpolates to a writable path the workspace volume mounts) made the SSH side work first try every time after.

## What's Running

| Service | IP | Port | Purpose |
|---------|-----|------|---------|
| Gitea | 192.168.55.209 | 3000 (HTTP), 2222 (SSH) | Git forge, GitHub mirror |
| Zot | 192.168.55.210 | 5000 (HTTPS) | OCI container registry |
| Tekton Dashboard | 192.168.55.217 | 9097 | Pipeline web UI |
| GitHub webhook receiver (`el-github-listener`) | 192.168.55.223 | 8080 | Receives GitHub webhooks for `agentic-stoa/*` repos via the Caddy relay at `webhooks.hop.derio.net` |

All three are exposed via Cilium L2 LoadBalancer and accessible through Traefik at `gitea.cluster.derio.net`, `zot.cluster.derio.net`, and `tekton.cluster.derio.net` with Authentik forward-auth.

## ArgoCD Apps

| App | Type | What It Manages |
|-----|------|----------------|
| `gitea` | Helm (multi-source) | Gitea StatefulSet, Services, ConfigMaps |
| `gitea-extras` | Directory | ExternalSecret for Gitea secrets |
| `tekton-pipelines` | Directory (vendored) | Tekton CRDs, controller, webhook |
| `tekton-triggers` | Directory (vendored) | Triggers controller, interceptors |
| `tekton-dashboard` | Directory (vendored) | Dashboard deployment |
| `tekton-extras` | Directory (recurse) | Tasks, Pipelines, TriggerBindings, RBAC, ExternalSecrets |
| `zot` | Helm (multi-source) | Zot Deployment, Service, PVC |
| `zot-extras` | Directory | Certificate, ClusterIssuer, ExternalSecret |

## References

- [Gitea Helm Chart](https://gitea.com/gitea/helm-chart)
- [Tekton Pipelines](https://tekton.dev/docs/pipelines/)
- [Tekton Triggers](https://tekton.dev/docs/triggers/)
- [Zot Registry](https://zotregistry.dev/)
- [cosign](https://docs.sigstore.dev/cosign/overview/)
- [Kaniko](https://github.com/GoogleContainerTools/kaniko)
