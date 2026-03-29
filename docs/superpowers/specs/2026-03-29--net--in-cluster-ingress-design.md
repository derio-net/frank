# In-Cluster Ingress: Traefik + Authentik Forward-Auth

**Date:** 2026-03-29
**Status:** Proposed
**Layer:** net

## Overview

Move TLS termination, hostname routing, and Authentik forward-auth from the external Traefik on raspi-omni into the Kubernetes cluster. Traefik runs as an in-cluster ingress controller with built-in ACME (Let's Encrypt + Cloudflare DNS-01), serving all cluster services under `*.cluster.derio.net`. A gethomepage.dev Homepage dashboard at `master.cluster.derio.net` provides a landing page for all cluster services.

The existing `*.frank.derio.net` setup on raspi-omni remains untouched and runs in parallel. Migration of references and eventual decommissioning of raspi-omni's cluster routes are future work (Phase 2/3), out of scope for this spec.

## Architecture

```
Pi-hole (HA pair)
  *.cluster.derio.net → 192.168.55.220
                              │
                    Traefik (in-cluster)
                    ├─ Cilium L2 LoadBalancer (192.168.55.220)
                    ├─ TLS via built-in ACME (Let's Encrypt + Cloudflare DNS-01)
                    ├─ Wildcard cert: *.cluster.derio.net
                    ├─ Middleware chain: IP allowlist + security headers + HTTPS redirect
                    └─ Node placement: raspi-1/raspi-2 (zone: edge, tier: low-power)
                              │
              ┌───────────────┴───────────────┐
        Forward-auth services           Direct proxy services
        (via Authentik outpost)         (no extra auth, or native OIDC)
              │                               │
  Longhorn, Hubble, ComfyUI,       ArgoCD, Sympozium, Authentik,
  Infisical, LiteLLM, Grafana,     Homepage
  GPU Switcher, Paperclip,
  KubeVirt†, n8n†, Harbor†,
  Gitea†

  † = not yet deployed as ArgoCD apps; IngressRoutes added when apps are deployed
```

## Design Decisions

### Ingress Controller: Traefik

Evaluated Traefik, Envoy Gateway, and Contour. Traefik wins on:

- **Authentik integration**: Official docs + Traefik plugin, battle-tested forward-auth middleware
- **Resource footprint**: Single pod (~50-100MB idle), proven on RPi 4 ARM64
- **Familiarity**: Same middleware model as the existing Ansible-managed Traefik — near 1:1 translation
- **Community**: 62k GitHub stars, largest homelab community, extensive troubleshooting resources
- **Gateway API**: Supports v1.4 (current) — future migration path available without changing controllers

### TLS: Traefik Built-in ACME (not cert-manager)

cert-manager is already deployed but only handles internal webhook TLS. For this use case:

- Traefik's built-in ACME resolver is simpler (no extra CRDs, no Issuer/Certificate objects)
- Single wildcard cert for `*.cluster.derio.net` via Cloudflare DNS-01 challenge
- `disablePropagationCheck: true` — required because local DNS ACLs block outbound queries to Cloudflare nameservers (same as current raspi-omni config)
- Cert stored in `acme.json` on a small Longhorn PV (128Mi)
- Single-replica Deployment with `strategy: Recreate` (RWO PVC constraint)

### Backend Routing: Kubernetes Service DNS (not L2 IPs)

IngressRoutes reference backend services via cluster DNS (e.g., `grafana.monitoring.svc.cluster.local:3000`), not Cilium L2 IPs. Benefits:

- Traffic stays cluster-internal (pod-to-service via Cilium eBPF)
- No hairpin through L2 announcement
- Survives IP reassignment
- Requires `allowCrossNamespace: true` in Traefik config (IngressRoutes in `traefik-system`, services in their own namespaces)

### Auth Strategy

Two tiers based on native OIDC availability (free tier only):

**Phase 1 (this spec): All routed services use forward-auth or no auth.**

Native OIDC requires callback URLs pointing at `*.cluster.derio.net`, which means updating each app's OIDC config — that's Phase 3 work. In Phase 1, services that *could* use native OIDC (ArgoCD, Grafana, Gitea, Harbor, Sympozium) are proxied without forward-auth since their existing OIDC is configured for `*.frank.derio.net`.

**Forward-auth via Authentik embedded outpost:**
- Longhorn — no auth support
- Hubble UI — no auth support
- ComfyUI — no auth support
- GPU Switcher — custom app, TBD
- Paperclip — custom app, TBD
- Infisical — OIDC is enterprise-only
- LiteLLM — UI auth limited
- Grafana — has native OIDC but callbacks point at `frank.derio.net` (Phase 3)
- n8n† — OIDC is enterprise-only ([docs](https://docs.n8n.io/user-management/oidc/))
- KubeVirt† — forward-auth as default
- Harbor† — has native OIDC but not yet deployed
- Gitea† — has native OIDC but not yet deployed

† = not yet deployed as ArgoCD apps; IngressRoutes added when apps are deployed

**No auth:**
- ArgoCD — has its own login page + existing OIDC via `frank.derio.net`
- Sympozium — has its own login page + existing OIDC via `frank.derio.net`
- Authentik — it IS the IdP
- Homepage — landing page, no sensitive data

**Not routable via HTTP ingress:**
- Kali Workstation (192.168.55.215) — SSH only, not HTTP

## Components

### 1. Traefik Deployment

ArgoCD App-of-Apps, multi-source Application CR:

- **Helm chart**: `traefik/traefik` (pin to `36.x.x` major)
- **Namespace**: `traefik-system`
- **Replicas**: 1
- **Node selector**: `zone: edge`, `tier: low-power` (raspi-1/raspi-2)
- **Service**: `type: LoadBalancer` with `lbipam.cilium.io/ips: "192.168.55.220"`
- **Entrypoints**: `web` (80) with global HTTP→HTTPS redirect, `websecure` (443)
- **ACME resolver**: `cloudflare` — Let's Encrypt production, DNS-01 via Cloudflare
- **Persistence**: 128Mi Longhorn PV for `acme.json`
- **Deployment strategy**: `Recreate` (RWO PVC)
- **CF API token**: From SOPS-encrypted Secret `traefik-cloudflare-credentials` in `traefik-system` namespace, mounted as `CF_DNS_API_TOKEN` env var

**Files:**

| File | Purpose |
|------|---------|
| `apps/traefik/values.yaml` | Helm values |
| `apps/traefik/manifests/middlewares.yaml` | Middleware CRDs |
| `apps/traefik/manifests/ingressroutes.yaml` | All IngressRoute CRDs |
| `apps/root/templates/traefik.yaml` | Application CR |
| `secrets/traefik-cloudflare-credentials.yaml` | SOPS-encrypted CF token |

### 2. Middlewares

Four Middleware CRDs in `traefik-system`:

**`https-redirect`** — `redirectScheme: https, permanent: true`
(Applied at entrypoint level in Helm values, not per-route.)

**`security-headers`** — mirrors current Traefik config:
- `frameDeny: true`, `browserXssFilter: true`, `contentTypeNosniff: true`
- HSTS: `forceSTSHeader: true`, `stsIncludeSubdomains: true`, `stsPreload: true`, `stsSeconds: 15552000`
- `customFrameOptionsValue: SAMEORIGIN`
- `referrerPolicy: strict-origin-when-cross-origin`
- `X-Forwarded-Proto: https` (request header)
- `X-Robots-Tag: none` (response header)

**`ip-allowlist`** — `sourceRange: 10.0.0.0/8, 192.168.0.0/16, 172.16.0.0/12`

**`authentik-forwardauth`** — forward-auth to Authentik via service DNS:
- Address: `http://authentik-server.authentik.svc.cluster.local:<VERIFY_PORT>/outpost.goauthentik.io/auth/traefik` (verify whether the ClusterIP service exposes the outpost endpoint on port 80 or 9000)
- `trustForwardHeader: true`
- Auth response headers: `X-authentik-username`, `X-authentik-groups`, `X-authentik-email`, `X-authentik-name`, `X-authentik-uid`, `X-authentik-jwt`, `X-authentik-meta-jwks`, `X-authentik-meta-outpost`, `X-authentik-meta-provider`, `X-authentik-meta-app`, `X-authentik-meta-version`
- **Prerequisite**: Authentik's `AUTHENTIK_HOST` env var must be set to the external URL (currently `https://auth.frank.derio.net`). Without it, forward-auth redirects use `0.0.0.0:9000`. This is already configured — verify during implementation that it still works when the outpost serves `*.cluster.derio.net` requests.

### 3. IngressRoutes

All IngressRoutes in a single `ingressroutes.yaml`. Each route:
- Entrypoint: `websecure`
- TLS: `certResolver: cloudflare`, `domains: [{main: "*.cluster.derio.net"}]`
- Middlewares: `ip-allowlist` + `security-headers` (all), plus `authentik-forwardauth` (selected)
- Services: Kubernetes service DNS, cross-namespace

**Routing table:**

**Deployed services (IngressRoutes created in Phase 1):**

| Hostname | Auth | Backend Service | Port |
|----------|------|-----------------|------|
| `master.cluster.derio.net` | none | homepage.homepage | 3000 |
| `argocd.cluster.derio.net` | none | argocd-server.argocd | 80 |
| `sympozium.cluster.derio.net` | none | VERIFY: sympozium ClusterIP in sympozium-system | 8080 |
| `auth.cluster.derio.net` | none | VERIFY: authentik-server.authentik ClusterIP port | 80 or 9000 |
| `grafana.cluster.derio.net` | forward-auth | VERIFY: victoria-metrics-grafana.monitoring | 80 |
| `longhorn.cluster.derio.net` | forward-auth | longhorn-frontend.longhorn-system | 80 |
| `hubble.cluster.derio.net` | forward-auth | hubble-ui.kube-system | 80 |
| `infisical.cluster.derio.net` | forward-auth | VERIFY: infisical ClusterIP in infisical ns | 8080 |
| `litellm.cluster.derio.net` | forward-auth | litellm.litellm | 4000 |
| `paperclip.cluster.derio.net` | forward-auth | VERIFY: paperclip ClusterIP in paperclip-system | 3100 |
| `comfyui.cluster.derio.net` | forward-auth | comfyui.comfyui | 8188 |
| `gpu.cluster.derio.net` | forward-auth | gpu-switcher.gpu-switcher | 8080 |

**Implementation prerequisite:** Before creating IngressRoutes, run `kubectl get svc -A` to verify all backend service names, namespaces, and ClusterIP ports. Several services above are marked VERIFY because the actual Helm-templated names may differ from conventions (e.g., Grafana is a victoria-metrics sub-chart, Infisical uses a long compound name, Paperclip may only have a LoadBalancer service). Create ClusterIP services where needed.

**Future services (IngressRoutes added when apps are deployed):**

| Hostname | Auth | Backend Service | Port |
|----------|------|-----------------|------|
| `n8n.cluster.derio.net` | forward-auth | TBD | 5678 |
| `gitea.cluster.derio.net` | forward-auth* | TBD | 3000 |
| `harbor.cluster.derio.net` | forward-auth* | TBD | 80 |
| `kubevirt.cluster.derio.net` | forward-auth | TBD | 80 |

\* = has native OIDC; switch from forward-auth to native OIDC in Phase 3.

### 4. Homepage Dashboard

gethomepage.dev deployment at `master.cluster.derio.net`:

- **Deployment**: `ghcr.io/gethomepage/homepage` image
- **Namespace**: `homepage`
- **Node selector**: `zone: edge` (co-locate with Traefik on raspi nodes)
- **Service config**: ConfigMap with all cluster services, organized by category (Infrastructure, Development)
- **IngressRoute**: `master.cluster.derio.net` → `homepage.homepage:3000`, no forward-auth

**Service entries** (derived from existing Ansible vars):

| Service | Category | Icon |
|---------|----------|------|
| ArgoCD | Infrastructure | argo-cd |
| Longhorn | Infrastructure | longhorn |
| Hubble | Infrastructure | cilium |
| Grafana | Infrastructure | grafana |
| Infisical | Infrastructure | infisical |
| Gitea | Infrastructure | gitea |
| Harbor | Infrastructure | harbor |
| Authentik | Infrastructure | authentik |
| KubeVirt | Infrastructure | kubevirt |
| LiteLLM | Development | mdi-robot |
| Sympozium | Development | element |
| n8n | Development | n8n |
| Paperclip | Development | mdi-paperclip |
| ComfyUI | Development | mdi-alpha-c-box-outline |
| GPU Switcher | Development | mdi-expansion-card |

### 5. ArgoCD Application CRs

**Traefik** — multi-source (Helm chart + values):
```
sources:
  - upstream Helm chart (traefik/traefik, 36.x.x)
  - $values ref (apps/traefik/values.yaml)
syncPolicy:
  ServerSideApply=true, CreateNamespace=true
  automated: selfHeal=true, prune=false
```

**Traefik Extras** — raw manifests (following the repo's `-extras` pattern for Helm+manifests apps):
```
source: apps/traefik/manifests/
destination: namespace traefik-system
syncPolicy: same as above
```

**Homepage** — raw manifests:
```
source: apps/homepage/manifests/
destination: namespace homepage
syncPolicy:
  ServerSideApply=true, CreateNamespace=true
  automated: selfHeal=true, prune=false
```

## Manual Operations

### MO-1: Create and apply Traefik Cloudflare credentials

```yaml
# manual-operation
id: net-traefik-cloudflare-secret
layer: net
app: traefik
plan: 2026-03-29--net--in-cluster-ingress
when: Before Traefik deployment
why_manual: Bootstrap secret must exist before Traefik starts ACME challenge
commands:
  - |
    cat <<EOF > secrets/traefik-cloudflare-credentials.yaml
    apiVersion: v1
    kind: Secret
    metadata:
      name: traefik-cloudflare-credentials
      namespace: traefik-system
    type: Opaque
    stringData:
      api-token: "<CF_DNS_API_TOKEN value>"
    EOF
  - sops --encrypt --in-place secrets/traefik-cloudflare-credentials.yaml
  - kubectl create namespace traefik-system || true
  - sops --decrypt secrets/traefik-cloudflare-credentials.yaml | kubectl apply -f -
verify:
  - kubectl get secret traefik-cloudflare-credentials -n traefik-system
status: pending
```

### MO-2: Configure Pi-hole DNS

```yaml
# manual-operation
id: net-pihole-cluster-wildcard
layer: net
app: traefik
plan: 2026-03-29--net--in-cluster-ingress
when: Before testing IngressRoutes
why_manual: Pi-hole DNS is managed via web UI, not declarative
commands:
  - "Pi-hole Admin → Local DNS → DNS Records"
  - "Add: *.cluster.derio.net → 192.168.55.220"
  - "Repeat on both Pi-hole instances"
verify:
  - nslookup master.cluster.derio.net
  - nslookup grafana.cluster.derio.net
status: pending
```

### MO-3: Create Authentik Proxy Provider for cluster.derio.net

```yaml
# manual-operation
id: net-authentik-cluster-proxy-provider
layer: net
app: authentik
plan: 2026-03-29--net--in-cluster-ingress
when: Before testing forward-auth services
why_manual: Authentik provider/app creation requires API or UI interaction
commands:
  - "Create Proxy Provider in Authentik (forward-auth mode)"
  - "External host: https://*.cluster.derio.net"
  - "Note: redirect_uris must be list of objects [{matching_mode: strict, url: ...}]"
  - "Note: signing_key UUID — query an existing provider to find it"
  - "Add the provider to the embedded outpost"
verify:
  - "curl -k https://longhorn.cluster.derio.net → redirects to Authentik login"
  - "After login → Longhorn UI loads"
status: pending
```

## Claude Rules Update

Extend `.claude/rules/frank-argocd.md` with:

```markdown
### Homepage Dashboard

When adding a new outward-facing service with an IngressRoute:
1. Add the service to `apps/homepage/` config (icon, category, description, URL)
2. Add the IngressRoute to `apps/traefik/manifests/ingressroutes.yaml`
```

## Future Work (out of scope)

**Phase 2: Migrate references**
- Update all in-cluster `frank.derio.net` references to `cluster.derio.net` (Authentik OIDC issuer URLs, Grafana OIDC callbacks, etc.)
- Optionally point `*.frank.derio.net` Pi-hole record at 192.168.55.220
- Strip raspi-omni Traefik down to Portainer + Omni only

**Phase 3: Native OIDC expansion**
- Configure native OIDC for ArgoCD, Grafana, Gitea, Harbor, Sympozium with `*.cluster.derio.net` callback URLs
- Remove forward-auth for services that gain native OIDC

## File Summary

| File | Purpose |
|------|---------|
| `apps/traefik/values.yaml` | Traefik Helm values |
| `apps/traefik/manifests/middlewares.yaml` | 4 Middleware CRDs |
| `apps/traefik/manifests/ingressroutes.yaml` | 12 IngressRoute CRDs (deployed services) |
| `apps/root/templates/traefik.yaml` | ArgoCD Application CR for Traefik (Helm chart) |
| `apps/root/templates/traefik-extras.yaml` | ArgoCD Application CR for Traefik raw manifests |
| `apps/homepage/manifests/` | Homepage deployment, service, configmaps |
| `apps/root/templates/homepage.yaml` | ArgoCD Application CR for Homepage |
| `secrets/traefik-cloudflare-credentials.yaml` | SOPS-encrypted CF API token |
| `.claude/rules/frank-argocd.md` | Updated with Homepage update rule |
| `.claude/rules/frank-infrastructure.md` | Updated with Traefik (192.168.55.220) and Homepage entries |
