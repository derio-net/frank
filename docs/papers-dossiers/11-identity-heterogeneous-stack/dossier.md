---
paper: 11-identity-heterogeneous-stack
status: ready
---

## Vendors in scope (≥3, typically 4–6)
- name: Authentik
  positioning: "Opinionated open-source IdP with embedded forward-auth outpost — Frank's choice."
  primary_url: "https://goauthentik.io/"
- name: Keycloak
  positioning: "Red Hat / CNCF-incubating enterprise IdP — the heavy-enterprise default."
  primary_url: "https://www.keycloak.org/"
- name: Dex
  positioning: "CoreOS-origin OIDC IdP that federates upstream providers — used by ArgoCD and others."
  primary_url: "https://dexidp.io/"
- name: Zitadel
  positioning: "Cloud-native IdP with a Go core and multi-tenancy by design."
  primary_url: "https://zitadel.com/"
- name: Authelia
  positioning: "Lightweight forward-auth-only authentication portal — popular in the homelab world."
  primary_url: "https://www.authelia.com/"
- name: Ory (Hydra + Kratos)
  positioning: "Composable identity primitives — library-first, you assemble the IdP."
  primary_url: "https://www.ory.sh/"
- name: Pomerium
  positioning: "Identity-aware reverse proxy — different stack position; SSO and proxy in one."
  primary_url: "https://www.pomerium.com/"

## Primary sources (≥5, ≥3 distinct type values)
- title: "BeyondCorp: A New Approach to Enterprise Security (Ward & Beyer, 2014)"
  type: paper
  url: "https://research.google/pubs/beyondcorp-a-new-approach-to-enterprise-security/"
  quoted_passages:
    - "Virtually every company today uses firewalls to enforce perimeter security. However, this security model is problematic because, when that perimeter is breached, an attacker has relatively easy access to a company's privileged intranet."
    - "The BeyondCorp initiative is moving to a new model that dispenses with a privileged corporate network. Instead, access depends solely on device and user credentials, regardless of a user's network location."
  relevance: "The IAP / zero-trust origin paper. Establishes the model that every forward-auth IdP — Authentik's embedded outpost, Pomerium, Cloudflare Access — implements 11 years later. Anchors §1's framing of where an IdP sits in a modern stack."

- title: "Authentik docs — Forward auth (Proxy provider)"
  type: vendor-docs
  url: "https://docs.goauthentik.io/docs/add-secure-apps/providers/proxy/forward_auth/"
  quoted_passages:
    - "Forward auth uses your reverse proxy (like NGINX, Traefik, or Caddy) to forward authentication requests to authentik before serving the application."
    - "Single application mode allows you to protect a single application with a single proxy provider. Domain level mode allows you to protect multiple applications under the same domain with a single proxy provider."
  relevance: "Vendor's own description of the forward-auth pattern that Frank uses for every protected web UI. Defines the seam between the IdP, the ingress controller (Traefik) and the upstream application, which §3 needs to render as a flowchart."

- title: "Keycloak docs — Identity Brokering"
  type: vendor-docs
  url: "https://www.keycloak.org/docs/latest/server_admin/index.html"
  quoted_passages:
    - "Keycloak is an open source software product to allow single sign-on with identity and access management aimed at modern applications and services."
    - "An Identity Broker is an intermediary service that connects multiple service providers with different identity providers. As an intermediary service, the identity broker is responsible for creating a trust relationship with an external identity provider in order to use its identities to access internal services exposed by service providers."
  relevance: "Defines how a heavy-enterprise IdP positions itself against the smaller open-source IdPs. Supplies the §2 vendor-landscape claim that Keycloak's centre of gravity is brokering / federation, not embedded forward-auth."

- title: "Dex docs — A federated OpenID Connect provider"
  type: vendor-docs
  url: "https://dexidp.io/docs/"
  quoted_passages:
    - "Dex is an identity service that uses OpenID Connect to drive authentication for other apps. Dex acts as a portal to other identity providers through 'connectors.'"
    - "This lets dex defer authentication to LDAP servers, SAML providers, or established identity providers like GitHub, Google, and Active Directory."
  relevance: "Defines the 'federation-only' position in the §2 landscape — Dex deliberately does not store users, only proxies authentication. Explains why projects that adopted Dex (ArgoCD's bundled provider) end up adding a 'real' IdP behind it as soon as they want password policies, MFA enrolment, or admin UI."

- title: "TechnoTim — 2 Factor Auth and Single Sign on with Authelia (Traefik forward-auth)"
  type: talk
  url: "https://docs.technotim.com/posts/authelia-traefik/"
  quoted_passages:
    - "Authelia is an open-source authentication and authorization server providing two-factor authentication and single sign-on (SSO) for your applications via a web portal."
    - "It acts as a companion of reverse proxies like nginx, Traefik or HAProxy to let them know whether requests should either be allowed or redirected to Authelia's portal for authentication."
  relevance: "Highest-visibility homelab/SMB-scale write-up of the forward-auth pattern. Anchors the §2 claim that the open-source homelab world has converged on a small set of forward-auth IdPs glued to one of three reverse proxies."

- title: "Authentik — release notes and breaking-change archive"
  type: postmortem
  url: "https://docs.goauthentik.io/docs/releases"
  quoted_passages:
    - "Starting with this release, Outposts will use the URL set in the authentik configuration to access authentik."
    - "OAuth2/OIDC and Proxy Providers now require an Invalidation flow to be set. This flow is used to log the user out of the application."
  relevance: "Source for the schema-migration scar tissue Paper 11 documents — `invalidation_flow`, object-shaped `redirect_uris`, the `AUTHENTIK_HOST` requirement on the embedded outpost. Concrete evidence that 'pin the chart and forget' is not a viable strategy for any self-hosted IdP."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "apps/authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml"
  date: 2026-04-15
  demonstrates: "Every forward-auth-protected service on Frank requires its own ProxyProvider blueprint entry — the declarative half of the workflow. The file is the source of truth for which services Authentik fronts; adding a new one is a code change, not a UI click."

- kind: yaml
  path_or_url: "apps/authentik/values.yaml"
  date: 2026-04-15
  demonstrates: "Helm `global.env` registers `AUTHENTIK_HOST` for both server and worker pods, and `blueprints.configMaps` mounts the cluster-wide ProxyProvider blueprint into the worker. The chart structure itself documents the two non-obvious operating constraints: the outpost will redirect to `0.0.0.0:9000` without `AUTHENTIK_HOST`, and blueprints only mount into the worker."

- kind: incident
  path_or_url: "agents/rules/frank-argocd.md"
  date: 2026-04-20
  demonstrates: "Every new forward-auth service requires a manual `kubectl exec` running Django ORM inside the authentik-server pod to add the provider to the embedded outpost — blueprints cannot manage the outpost's provider list without replacing existing assignments. The cost of a 'declarative-everything' policy is a documented manual escape hatch for one specific Authentik limitation."

- kind: incident
  path_or_url: "docs/runbooks/frank-gotchas/authentik.md"
  date: 2026-05-10
  demonstrates: "Compressed scar tissue from running Authentik on Frank: 2026.x schema requires `invalidation_flow`, object-shaped `redirect_uris`, and a `signing_key` UUID; the API moved from basic auth to Bearer tokens; `global.env` must cover both server and worker. Concrete evidence that an IdP upgrade is a controlled migration, not a chart bump."

- kind: incident
  path_or_url: "docs/runbooks/frank-gotchas/grafana.md"
  date: 2026-04-25
  demonstrates: "Grafana's OIDC integration accepts the client secret *only* under the exact env-var name `GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET` when sourced via `envFromSecret` — any other key silently leaves the integration broken. A single per-app gotcha multiplied across every protected service: the IdP's design is half the story; the relying party's configuration surface is the other half."

## Diagrams planned
- stack_position:
    type: "flowchart LR"
    description: "Where an IdP sits — between user and application, alongside ingress. User → Browser → Traefik IngressRoute → forward-auth middleware → Authentik embedded outpost → Authentik server → (allow) → upstream application."
- landscape:
    x_axis: "lightweight forward-auth ↔ full enterprise IdP"
    y_axis: "single-tenant homelab ↔ multi-tenant SaaS-grade"
    vendors_plotted: ["Authelia", "Authentik", "Dex", "Keycloak", "Zitadel", "Ory", "Pomerium"]
- capability_matrix:
    rows: ["Authentik", "Keycloak", "Dex", "Zitadel", "Authelia", "Ory", "Pomerium"]
    columns: ["OIDC", "SAML", "Forward-auth", "Federation", "MFA built-in", "Multi-tenant", "Helm chart"]
- architecture_comparison:
    vendors: ["Authentik", "Keycloak", "Dex", "Zitadel", "Authelia", "Ory", "Pomerium"]
    diagram_type: "flowchart TD per vendor"
- decision_tree:
    leaves: 4
    description: "Question: which IdP for a heterogeneous self-hosted stack? Branches on (a) do you already run a service mesh / IAP, (b) do you need multi-tenancy, (c) is forward-auth enough or do you need SAML+OIDC+federation, terminating in: Pomerium, Keycloak/Zitadel, Authentik, Authelia."

## Named gaps (≥1)
- "No widely-cited side-by-side outage analysis comparing forward-auth and identity-aware-proxy failure modes — specifically, what fails when the IdP is *down* vs *slow* vs *misconfigured*. The available postmortems are single-vendor and rarely separate the three modes, yet the operational consequences differ sharply: forward-auth with a down outpost 502s every request to every protected service; an OIDC-only IdP outage lets existing browser sessions ride but blocks every token refresh and every CLI re-auth. Frank's own evidence is anecdotal — a couple of restarts during 2026.x migration — not enough to characterise the long tail."

## Counter-arguments considered (≥1)
- "OAuth-via-GitHub / Google is already federated, free for personal use, and runs at 99.9%+ uptime. Why self-host an IdP at all? Answer: Frank wants the failure modes (you cannot run an IdP outage drill against Google), the multi-tenancy story (vCluster-per-tenant identity isolation is impossible against a third-party IdP, since you cannot create or scope users in a tenant you do not own), and the offline-survival property — the cluster must keep functioning when the upstream IdP doesn't, or when the upstream IdP decides your account is now spam. The cost is real (schema migrations, manual outpost-provider assignment, per-app OIDC quirks) but the cost *is the point*: this is the layer where you learn what an IdP actually does."
