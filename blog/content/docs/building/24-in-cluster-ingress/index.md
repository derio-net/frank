---
title: "In-Cluster Ingress — Traefik, Wildcard TLS, and a Homepage Dashboard"
date: 2026-04-08
draft: false
tags: ["networking", "traefik", "ingress", "tls", "acme", "authentik", "forward-auth", "homepage"]
summary: "Moving TLS termination and reverse proxying into the cluster with Traefik, Let's Encrypt wildcard certs, Authentik forward-auth, and a gethomepage.dev dashboard."
weight: 25
---

Up until now, all of Frank's services were reachable via direct Cilium L2 LoadBalancer IPs — type an IP and port into your browser, and you're in. That works fine on a local network, but it means no TLS, no unified authentication, no human-readable URLs, and no single place to see what's running. The external Traefik on raspi-omni handled `*.frank.derio.net` routing, but it sat *outside* the cluster — a separate Ansible-managed box with its own failure modes.

This post moves the ingress controller inside the cluster: Traefik v3 running on the raspi edge nodes, serving all services under `*.cluster.derio.net` with wildcard TLS from Let's Encrypt, Authentik forward-auth for services without native SSO, and a gethomepage.dev dashboard at `master.cluster.derio.net`.

## Architecture

```
Pi-hole (HA pair)
  *.cluster.derio.net → 192.168.55.220
                              │
                    Traefik (in-cluster)
                    ├─ Cilium L2 LoadBalancer (192.168.55.220)
                    ├─ TLS via built-in ACME (Let's Encrypt + Cloudflare DNS-01)
                    ├─ Wildcard cert: *.cluster.derio.net
                    ├─ Middleware chain: IP allowlist + security headers
                    └─ Node placement: raspi-1/raspi-2 (zone: edge)
                              │
              ┌───────────────┴───────────────┐
        Forward-auth services           Direct proxy services
        (via Authentik outpost)         (native auth or public)
              │                               │
  Longhorn, Hubble, ComfyUI,       ArgoCD, Sympozium, Authentik,
  Infisical, LiteLLM, Grafana,     Homepage
  GPU Switcher, Paperclip,
  n8n, Gitea, Zot, Tekton
```

Traefik runs as a single-replica Deployment on the raspi edge nodes. A Cilium L2 announcement puts it at `192.168.55.220`. Pi-hole resolves `*.cluster.derio.net` to that IP. Traefik terminates TLS with a wildcard cert, applies middleware, and routes to backend services via Kubernetes DNS — traffic stays cluster-internal, no hairpin through L2.

## Why Traefik

I evaluated Traefik, Envoy Gateway, and Contour. Traefik won on:

- **Authentik integration** — official docs, battle-tested forward-auth middleware
- **Resource footprint** — single pod, ~50MB idle, proven on RPi 4 ARM64
- **Familiarity** — same middleware model as the existing Ansible-managed Traefik, near 1:1 translation
- **Gateway API** — supports v1.4 for future migration without changing controllers

## TLS: Built-in ACME, Not cert-manager

cert-manager is already deployed for internal webhook TLS, but for this use case Traefik's built-in ACME resolver is simpler — no extra CRDs, no Issuer/Certificate objects. One wildcard cert for `*.cluster.derio.net` via Cloudflare DNS-01:

```yaml
# apps/traefik/values.yaml (excerpt)
certificatesResolvers:
  cloudflare:
    acme:
      email: "admin@derio.net"
      storage: /data/acme.json
      dnsChallenge:
        provider: cloudflare
        propagation:
          disableChecks: true
          delayBeforeChecks: 60
```

The `disableChecks: true` skips local DNS propagation verification (blocked by router ACLs), and `delayBeforeChecks: 60` gives Cloudflare 60 seconds to propagate the TXT record globally before Let's Encrypt verifies it.

The cert is stored in `acme.json` on a small 128Mi Longhorn PV. Since the PV is RWO, Traefik runs with `strategy: Recreate` — no rolling updates, but that's fine for a single-replica edge proxy.

```console
$ kubectl -n traefik-system exec deploy/traefik -- cat /data/acme.json 2>/dev/null | jq -r ".cloudflare.Certificates[].domain.main"
*.cluster.derio.net

$ kubectl -n traefik-system exec deploy/traefik -- cat /data/acme.json 2>/dev/null | jq -r ".cloudflare.Certificates[0].certificate" | base64 -d | openssl x509 -noout -dates
notBefore=Apr  8 05:28:35 2026 GMT
notAfter=Jul  7 05:28:34 2026 GMT
```

### PVC Permissions Gotcha

Longhorn creates root-owned volumes, but Traefik runs as uid 65532 (nonroot). Without `fsGroup`, the ACME resolver fails silently with `permission denied` on `/data/acme.json` — Traefik logs it as "ACME resolve is skipped from the resolvers list" and every IngressRoute complains about a "nonexistent certificate resolver":

```yaml
podSecurityContext:
  fsGroup: 65532
  fsGroupChangePolicy: "OnRootMismatch"
```

The Traefik Helm chart uses top-level `podSecurityContext`, not `deployment.podSecurityContext` — the nested path is silently ignored.

## Middlewares

Three Middleware CRDs in `traefik-system`:

**`security-headers`** — HSTS, X-Frame-Options, Content-Type sniffing protection, referrer policy. Mirrors the existing raspi-omni config.

**`ip-allowlist`** — restricts to RFC 1918 ranges (`10.0.0.0/8`, `192.168.0.0/16`, `172.16.0.0/12`). This is a homelab, not a public-facing cluster.

**`authentik-forwardauth`** — sends every request to the Authentik embedded outpost for authentication. The outpost checks the user's session cookie; if missing or expired, it redirects to the Authentik login page:

```yaml
spec:
  forwardAuth:
    address: "http://authentik-server.authentik.svc.cluster.local:80/outpost.goauthentik.io/auth/traefik"
    trustForwardHeader: true
    authResponseHeaders:
      - X-authentik-username
      - X-authentik-groups
      - X-authentik-email
      # ... plus uid, jwt, meta headers
```

The Authentik ClusterIP service exposes port 80 (mapped to pod port 9000). Using in-cluster DNS means forward-auth stays entirely within the cluster network.

## IngressRoutes

All 16 IngressRoutes live in a single `ingressroutes.yaml`. Each route targets the `websecure` entrypoint with the wildcard cert resolver and at least `ip-allowlist` + `security-headers` middlewares.

Services split into two tiers:

**Direct proxy (no forward-auth):** ArgoCD, Sympozium, Authentik, Homepage — these either have their own login page or are the IdP itself.

**Forward-auth via Authentik:** Grafana, Longhorn, Hubble, Infisical, LiteLLM, Paperclip, ComfyUI, GPU Switcher, n8n, Gitea, Zot, Tekton — services without native OIDC (or with OIDC configured for `frank.derio.net`, not yet migrated).

Backend services are referenced via Kubernetes DNS (`service.namespace:port`), not Cilium L2 IPs. Traffic stays cluster-internal via Cilium eBPF routing.

```console
$ kubectl get ingressroutes -n traefik-system -o wide
NAME           AGE
argocd         12d
authentik      12d
comfyui        12d
gitea          12d
gpu-switcher   12d
grafana        12d
homepage       12d
hubble         12d
infisical      12d
litellm        12d
longhorn       12d
n8n            12d
paperclip      12d
sympozium      12d
tekton         12d
vk-remote      8d
zot            12d
```

<!-- MEDIA: screenshot | Traefik dashboard showing routers, services, and middleware chains | Navigate to the Traefik dashboard and capture the routers overview page -->
<!-- {{</* screenshot src="traefik-dashboard.png" caption="Traefik dashboard showing configured routers" */>}} -->

## Authentik Blueprints

The proxy providers for `*.cluster.derio.net` are managed declaratively via an Authentik blueprint ConfigMap (`blueprints-cluster-proxy-providers.yaml`). Each service gets a `forward_single` proxy provider entry:

```yaml
- model: authentik_providers_proxy.proxyprovider
  state: present
  identifiers:
    name: Grafana (cluster)
  attrs:
    authorization_flow: !Find [authentik_flows.flow, [slug, default-provider-authorization-implicit-consent]]
    authentication_flow: !Find [authentik_flows.flow, [slug, default-authentication-flow]]
    invalidation_flow: !Find [authentik_flows.flow, [slug, default-provider-invalidation-flow]]
    mode: forward_single
    external_host: https://grafana.cluster.derio.net
```

The `invalidation_flow` field is required in Authentik 2026.x — without it, the blueprint fails silently with a serializer error and no providers are created.

The blueprint creates providers and applications, but does **not** assign them to the embedded outpost. Outpost assignment must be done via Django ORM after the blueprint applies — Authentik blueprints can't append to an outpost's provider list without replacing existing assignments.

## Homepage Dashboard

A gethomepage.dev instance at `master.cluster.derio.net` provides the cluster landing page — all services organized by category with HTTP health indicators:

- **Infrastructure**: ArgoCD, Longhorn, Hubble, Grafana, Infisical, Authentik
- **CI/CD**: Gitea, Zot, Tekton
- **Development**: LiteLLM, Sympozium, n8n, Paperclip, ComfyUI, GPU Switcher

Health checks use `siteMonitor` (HTTP HEAD/GET to internal ClusterIP URLs), not `ping` (ICMP) — Kubernetes ClusterIP addresses don't respond to ICMP from inside the cluster.

Custom bookmarks link to the Lab landing page, Omni, and Renovate.

<!-- MEDIA: screenshot | Homepage dashboard showing all cluster services organized by category | Navigate to https://master.cluster.derio.net and capture the full dashboard view -->
<!-- {{</* screenshot src="homepage-dashboard.png" caption="Homepage dashboard at master.cluster.derio.net" */>}} -->

## Gotchas

| Issue | Fix |
|-------|-----|
| `acme.json: permission denied` | `podSecurityContext.fsGroup: 65532` (top-level, not nested under `deployment`) |
| ACME DNS-01 NXDOMAIN | `propagation.delayBeforeChecks: 60` — give Cloudflare time to propagate TXT records |
| `disablePropagationCheck` deprecated | Use `propagation.disableChecks: true` in Traefik v3.6+ |
| Authentik blueprint `invalidation_flow` required | Authentik 2026.x serializer rejects providers without it |
| Blueprint doesn't assign outpost | Manual Django ORM: `outpost.providers.add(provider)` after blueprint applies |
| Homepage `ping:` shows DOWN | Use `siteMonitor:` (HTTP) instead — ICMP doesn't work for ClusterIP |
| Homepage `Host validation failed` | Set `HOMEPAGE_ALLOWED_HOSTS=master.cluster.derio.net` env var |

## References

- [Traefik Helm Chart](https://github.com/traefik/traefik-helm-chart)
- [Traefik ACME DNS Challenge](https://doc.traefik.io/traefik/https/acme/#dnschallenge)
- [Authentik Proxy Provider](https://docs.goauthentik.io/docs/providers/proxy/)
- [Authentik Blueprints](https://docs.goauthentik.io/docs/installation/blueprints/)
- [gethomepage.dev](https://gethomepage.dev/)
