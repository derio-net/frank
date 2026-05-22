---
paper: 15-ingress-and-service-catalog
status: draft
---

## Vendors in scope (≥3, typically 4–6)
- name: Traefik (with authentik-forwardauth middleware)
  positioning: "K8s-native ingress controller — IngressRoute CRD, built-in ACME, middleware chain (including forwardAuth). Frank's pick for `*.cluster.derio.net`."
  primary_url: "https://doc.traefik.io/traefik/v3.5/middlewares/http/forwardauth/"
- name: Nginx Ingress Controller (with oauth2-proxy)
  positioning: "The default reference ingress for K8s — annotation-driven, mature, integrates with oauth2-proxy via auth-url / auth-signin annotations."
  primary_url: "https://kubernetes.github.io/ingress-nginx/"
- name: Envoy / Contour (Gateway API path)
  positioning: "L7 proxy + xDS control plane; Gateway API is the post-Ingress contract. ext_authz for external auth, Gateway-API-first."
  primary_url: "https://projectcontour.io/docs/"
- name: Authentik embedded outpost (forward-auth backend)
  positioning: "OIDC IdP + proxy-provider outpost — IngressRoute middleware forwards every request to /outpost.goauthentik.io/auth/<provider>."
  primary_url: "https://docs.goauthentik.io/docs/add-secure-apps/providers/proxy/"
- name: oauth2-proxy (forward-auth alternative)
  positioning: "Stateless OIDC reverse proxy — sits between the ingress and the upstream; bring-your-own IdP. The forward-auth choice without an Authentik-shaped IdP."
  primary_url: "https://oauth2-proxy.github.io/oauth2-proxy/"
- name: gethomepage.dev Homepage (service catalogue)
  positioning: "Static-config dashboard for the cluster — services.yaml + bookmarks.yaml in ConfigMaps, container at /app/config. Frank's catalogue layer at master.cluster.derio.net."
  primary_url: "https://gethomepage.dev/configs/services/"

## Primary sources (≥5, ≥3 distinct type values)
- title: "Traefik v3.5 — ForwardAuth middleware"
  type: vendor-docs
  url: "https://doc.traefik.io/traefik/v3.5/middlewares/http/forwardauth/"
  quoted_passages:
    - "The ForwardAuth middleware delegates authentication to an external Service."
  relevance: "Defines the middleware Frank actually uses to route every SSO-gated IngressRoute to the Authentik embedded outpost. The 'authResponseHeaders' field is what propagates X-authentik-username / -groups / -email to upstream services."
- title: "Authentik — Proxy provider documentation"
  type: vendor-docs
  url: "https://docs.goauthentik.io/docs/add-secure-apps/providers/proxy/"
  quoted_passages:
    - "In this mode, the regular expressions are matched against the Request's Path."
    - "In this mode, the regular expressions are matched against the Request's full URL."
  relevance: "Defines the proxy-provider modes (forward_single, forward_domain, proxy) that Frank's blueprint declares for every SSO-gated service. The forward_single vs forward_domain distinction is what determines whether one Authentik provider serves one app or a wildcard subdomain."
- title: "Kubernetes — Ingress Controllers (project recommendation)"
  type: vendor-docs
  url: "https://kubernetes.io/docs/concepts/services-networking/ingress-controllers/"
  quoted_passages:
    - "The Kubernetes project recommends using Gateway instead of Ingress. The Ingress API has been frozen."
    - "In order for an Ingress to work in your cluster, there must be an ingress controller running."
  relevance: "Authoritative statement that the Ingress API is feature-frozen and Gateway API is the forward path — load-bearing for §7's roadmap argument."
- title: "Kubernetes Gateway API"
  type: paper
  url: "https://gateway-api.sigs.k8s.io/"
  quoted_passages:
    - "Gateway API is an official Kubernetes project focused on L4 and L7 routing in Kubernetes."
  relevance: "The post-Ingress contract — splits GatewayClass / Gateway / HTTPRoute into three CRDs with separate role boundaries (infra owner, cluster operator, application developer). The shape every controller is converging on."
- title: "oauth2-proxy — reverse-proxy authentication"
  type: vendor-docs
  url: "https://oauth2-proxy.github.io/oauth2-proxy/"
  quoted_passages:
    - "A reverse proxy and static file server that provides authentication using Providers (Google, GitHub, and others) to validate accounts by email, domain or group."
  relevance: "The non-Authentik forward-auth alternative — same architectural slot (sits between ingress and upstream), different IdP shape. Important §3 comparison point: Nginx + oauth2-proxy is the most common forward-auth stack outside Authentik shops."
- title: "Contour — Ingress controller built on Envoy"
  type: vendor-docs
  url: "https://projectcontour.io/docs/"
  quoted_passages:
    - "Contour is an Ingress controller for Kubernetes that works by deploying the Envoy proxy as a reverse proxy and load balancer."
  relevance: "Reference for the Envoy + Gateway API + ext_authz architecture — the §3 diagram for 'mesh-shaped' ingress that pushes auth into Envoy's external-authorization filter rather than chaining middleware at the ingress."
- title: "gethomepage.dev — Services configuration"
  type: vendor-docs
  url: "https://gethomepage.dev/configs/services/"
  quoted_passages:
    - "Services are configured inside the services.yaml file. You can have any number of groups, and any number of services per group."
  relevance: "Defines Frank's catalogue shape. The static-config model (ConfigMap → /app/config/services.yaml) is the simplest possible service catalogue — no API server, no scrape loop, no auto-discovery. The blast radius of a typo is one wrong tile, not a broken dashboard."
- title: "Frank gotcha registry — operational lessons"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/agents/rules/frank-gotchas.md"
  quoted_passages:
    - "Cilium: lbipam.cilium.io/ips alone is NOT a sharing directive — separate Services need matching lbipam.cilium.io/sharing-key."
    - "Blueprints don't assign providers to embedded outpost — manual Django ORM step (see frank-argocd.md)."
  relevance: "Frank's own one-line gotcha registry — the two lines above are the load-bearing scars for §5. The full prose lives in per-topic files under docs/runbooks/frank-gotchas/."
- title: "Frank Authentik runbook — per-topic gotcha file"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/docs/runbooks/frank-gotchas/authentik.md"
  quoted_passages:
    - "Embedded outpost needs AUTHENTIK_HOST env or forward-auth redirects use 0.0.0.0:9000."
    - "2026.x requires invalidation_flow + object-shaped redirect_uris + signing_key UUID."
  relevance: "Full-prose recovery commands for the three Authentik scars cited in §5 (manual outpost-provider step, AUTHENTIK_HOST env, 2026.x API shape changes). Direct evidence the scars are real, dated, and have documented recovery paths."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "apps/traefik/manifests/ingressroutes.yaml"
  date: 2026-05-22
  demonstrates: "18+ IngressRoute CRs showing the two routing tiers (forward-auth vs direct) and the common middleware chain (ip-allowlist, security-headers, optional authentik-forwardauth). The pattern: adding a new SSO-gated service is a single middleware reference, not a per-app OIDC integration."
- kind: yaml
  path_or_url: "apps/traefik/manifests/middlewares.yaml"
  date: 2026-05-22
  demonstrates: "The three middlewares reused across every IngressRoute: security-headers, ip-allowlist, authentik-forwardauth. The forwardAuth middleware addresses http://authentik-server.authentik.svc.cluster.local:80/outpost.goauthentik.io/auth/traefik — the embedded outpost endpoint. authResponseHeaders lists the X-authentik-* headers the upstream sees. One Middleware CR is reused across the entire cluster — no per-app SDK."
- kind: yaml
  path_or_url: "apps/homepage/manifests/configmap-services.yaml"
  date: 2026-05-22
  demonstrates: "The cluster service catalogue as a ConfigMap: three categories (Infrastructure, CI/CD, Development), every service grouped with icon, description, href, siteMonitor. The siteMonitor field uses cluster-internal DNS so the catalogue's uptime indicator runs at pod-to-service latency rather than via the public ingress — the catalogue is supposed to be the lowest-latency view of cluster health, not the slowest."
- kind: incident
  path_or_url: "docs/runbooks/frank-gotchas/authentik.md (Blueprints don't assign providers to embedded outpost)"
  date: 2026-03-30
  demonstrates: "Authentik blueprints declaratively create proxy providers + applications, but adding a provider to the embedded outpost is NOT in the blueprint API. After each fresh deploy (or whenever a new forward-auth service is added), a Django-ORM step is required: outpost.providers.add(provider). The only out-of-band step in an otherwise fully-declarative auth chain — the seam between Authentik's blueprint API surface and what the outpost actually consumes."
- kind: incident
  path_or_url: "docs/runbooks/frank-gotchas/authentik.md (AUTHENTIK_HOST env requirement)"
  date: 2026-04-12
  demonstrates: "Without AUTHENTIK_HOST set to the external URL, the embedded outpost's forward-auth redirects use 0.0.0.0:9000 — login appears to succeed, then redirects to an unreachable URL. The outpost self-discovers its callback URL from request context and gets it wrong by default inside a K8s Service. The fix is one env var; the lesson is that 'works in dev' and 'works behind a Service' are different verbs."
- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md (Networking — Cilium LB sharing-key)"
  date: 2026-03-29
  demonstrates: "lbipam.cilium.io/ips alone is NOT a sharing directive. When two Services target the same LoadBalancer IP, both need a matching lbipam.cilium.io/sharing-key annotation; without it, one Service ends up <pending> forever. The only signal is kubectl get svc -A | grep pending. The L2 announcement layer has its own multi-tenant model, independent of what the ingress controller wants."

## Diagrams planned
- landscape:
    x_axis: "Per-app OIDC ↔ Edge forward-auth"
    y_axis: "Catalogue included ↔ Catalogue separate"
    vendors_plotted:
      - Traefik + Authentik + Homepage
      - Nginx Ingress + oauth2-proxy
      - Envoy / Contour (Gateway API)
      - Per-app OIDC SDK only
      - Service mesh mTLS (Istio)
      - Cloudflare Access
- architecture_comparison:
    vendors:
      - Traefik + Authentik forward-auth + Homepage
      - Nginx Ingress + oauth2-proxy
      - Envoy / Contour with Gateway API + ext_authz
      - Per-app OIDC SDK (no forward-auth)
      - Service mesh mTLS + AuthorizationPolicy
- decision_tree:
    leaves: 4

## Named gaps (≥1)
- "No apples-to-apples benchmark of forward-auth latency overhead per request exists at homelab QPS (0.1–10 QPS per service). Vendor benchmarks measure 10k+ QPS scenarios where the marginal cost of an extra L7 hop is negligible compared to steady-state throughput; that result does not translate to the 'one human, one click, one cold-cache OIDC redirect' interaction that dominates homelab forward-auth use. The cost model that matters for a learning cluster is 'first-page-load latency after a 12-hour idle' — and no public benchmark measures that. Comparisons either skip this entirely or treat it as 'covered by your CDN' — which is the value system this Paper exists to contradict."

## Counter-arguments considered (≥1)
- "For a single-team SaaS behind Cloudflare Access, you don't need any of this. Cloudflare terminates TLS, enforces SSO via Cloudflare Access (or Google Workspace), and you don't need a service catalogue because every team member has the URLs in their bookmarks. Why does Frank's in-cluster Traefik + Authentik + Homepage stack win? Same shape as Paper 09. Frank is a learning platform. The reason to run in-cluster ingress + forward-auth is to encounter the Cilium LB sharing-key gotcha, the Authentik blueprint manual-outpost step, the AUTHENTIK_HOST env quirk, and the 2026.x API shape changes — first-hand. A team that has internalized these lessons can rationally fall back to Cloudflare Access for the production cluster and keep a thin in-cluster ingress for east-west. A team that has not will reinvent the same scars when they outgrow Cloudflare's pricing or hit a feature wall. The counter wins for the team that has already paid the tuition; for Frank, paying the tuition is the point."
