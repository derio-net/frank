---
title: "Unified Auth — Authentik SSO for the Entire Cluster"
date: 2026-03-11
draft: false
tags: ["authentik", "oidc", "sso", "security", "auth", "rbac", "traefik"]
summary: "One identity provider for every service — Authentik brings OIDC SSO to ArgoCD, Grafana, and Infisical, forward-auth proxy to Longhorn, Hubble, and Sympozium, and OIDC-backed kubectl access."
weight: 14
cover:
  image: cover.png
  alt: "Frank the cluster monster guarding a gate with OIDC tokens flowing through it"
  relative: true
---

Twelve layers deep, every service on the cluster has its own local admin account. ArgoCD has its built-in admin user. Grafana has a default `admin/admin` login. Infisical has a self-created admin account. Longhorn, Hubble, and Sympozium have no authentication at all — anyone on the LAN can access them.

This is fine for a homelab with one user. It is not fine the moment you add a second person, set up CI agents, or want an audit trail that says who did what.

Layer 13 fixes this. One identity provider — [Authentik](https://goauthentik.io) — handles authentication and authorization for every service on the cluster. Log in once, access everything your group membership allows.

## Why Authentik?

The CNCF-native answer is Dex or Keycloak. Both are mature and well-documented. Authentik won for three reasons:

1. **Proxy outpost** — services that have no OIDC support (Longhorn UI, Hubble UI, Sympozium) get authentication via a reverse proxy that sits in front of Traefik. No code changes, no sidecars.
2. **Blueprint system** — providers, applications, and groups can be defined as YAML. In theory, this makes the configuration declarative and GitOps-friendly. In practice, this had complications (more on that below).
3. **Self-hosted and free** — the open-source edition includes everything needed: OIDC, proxy providers, group management, admin UI.

## The Architecture

Three integration patterns, one identity provider:

```
                          ┌─────────────────┐
                          │    Authentik     │
                          │  192.168.55.211  │
                          │  IdP + Outpost   │
                          └────────┬────────┘
                                   │
              ┌────────────────────┼───────────────────┐
              │                    │                    │
    ┌─────────▼──────────┐ ┌──────▼───────────┐ ┌─────▼──────────────┐
    │   OIDC (native)    │ │ Forward Auth     │ │ Agent Auth         │
    │                    │ │ (proxy outpost)  │ │ (client creds)     │
    │ ArgoCD             │ │                  │ │                    │
    │ Grafana            │ │ Longhorn UI      │ │ k8s-agent          │
    │ Infisical          │ │ Hubble UI        │ │ (OIDC → apiserver) │
    │                    │ │ Sympozium        │ │                    │
    └────────────────────┘ └──────────────────┘ └────────────────────┘
```

### Pattern 1: Native OIDC

Services that support OpenID Connect get a dedicated OAuth2 provider in Authentik. The service redirects to Authentik for login, receives a JWT with group claims, and maps groups to roles.

- **ArgoCD** — `oidc.config` in `argocd-cm`, groups mapped via `policy.csv` RBAC
- **Grafana** — `auth.generic_oauth` in `grafana.ini`, JMESPath role mapping from group claims
- **Infisical** — OIDC configured via admin UI (no Helm value for this)

### Pattern 2: Forward Auth Proxy

Services with no authentication support get protected by Authentik's embedded proxy outpost. Traefik (running on raspi-omni, outside K8s) uses `forwardAuth` middleware to check every request against the outpost before forwarding to the backend.

The flow:

1. User navigates to `longhorn.frank.derio.net`
2. Traefik sends a sub-request to the Authentik outpost
3. If the user has no valid session, Authentik redirects to login
4. After login, the outpost returns a success response to Traefik
5. Traefik forwards the original request to the backend

**Critical: `AUTHENTIK_HOST`** — The embedded outpost needs to know its own external URL to generate correct OAuth2 redirect URIs. Without the `AUTHENTIK_HOST` environment variable, the outpost defaults to `http://0.0.0.0:9000` (the container's bind address), and forward-auth redirects send users to an unreachable address instead of `https://auth.frank.derio.net`.

```yaml
global:
  env:
    - name: AUTHENTIK_HOST
      value: "https://auth.frank.derio.net"
```

This is set via `global.env` so it applies to both the server and worker deployments.

### Pattern 3: Agent Auth (Kubernetes OIDC)

The kube-apiserver itself can validate Authentik-issued tokens. A Talos machine config patch adds OIDC flags to the apiserver:

```yaml
cluster:
  apiServer:
    extraArgs:
      oidc-issuer-url: https://auth.frank.derio.net/application/o/k8s-agent/
      oidc-client-id: k8s-agent
      oidc-username-claim: preferred_username
      oidc-groups-claim: groups
```

ClusterRoleBindings map Authentik groups to Kubernetes RBAC roles:

| Authentik Group | K8s ClusterRole |
|----------------|----------------|
| root-admins | cluster-admin |
| root-devops | admin |
| root-developers | view |
| root-agents | cluster-admin |

## Deploying Authentik

The deployment follows the standard ArgoCD pattern: two apps.

**`authentik`** — the Helm chart. Authentik server, worker, and embedded PostgreSQL. The chart bundles its own PostgreSQL subchart (unlike Infisical's chart, no env var collision bug here). Redis is also embedded. Secret key and PostgreSQL password come from a SOPS-encrypted Kubernetes Secret applied out-of-band.

**`authentik-extras`** — raw manifests. Blueprint ConfigMaps for OIDC and proxy providers, a Cilium L2 LoadBalancer Service for external access, and ClusterRoleBindings for OIDC group-to-role mapping.

Key values:

```yaml
authentik:
  secret_key: ""  # from Secret
  postgresql:
    password: ""  # from Secret
  bootstrap_password: ""
server:
  env:
    - name: AUTHENTIK_SECRET_KEY
      valueFrom:
        secretKeyRef:
          name: authentik-secrets
          key: AUTHENTIK_SECRET_KEY
```

The bootstrap password creates an initial `akadmin` user on first boot. After SSO is working, this account becomes a break-glass fallback.

## Blueprints: Declarative in Theory (and Eventually in Practice)

Authentik supports YAML blueprints for defining providers, applications, and groups. The plan was to mount them as ConfigMaps and let Authentik auto-discover them.

The groups blueprint worked. Three groups (`root-admins`, `root-devops`, `root-developers`) materialized on startup. The provider blueprints did not. The auto-discovery mechanism found the mounted files but failed to parse some of them, reporting `status: error` with no actionable message.

Manually triggering blueprint discovery via the API failed with a `CurrentTaskNotFound` error — the function requires a Dramatiq task context that does not exist outside the worker process.

After several attempts, the initial approach shifted to the Authentik REST API. Every provider, application, and outpost assignment was created via `curl` against `/api/v3/`. The API is well-documented and worked on every attempt.

**Update:** A later audit revisited the blueprint failures and found the issue was blueprint YAML syntax — not an Authentik bug. With corrected YAML, all provider blueprints now work as ConfigMaps in `authentik-extras`. The full set:

- `blueprints-groups.yaml` — group hierarchy (root-admins, root-devops, root-developers)
- `blueprints-provider-argocd.yaml` — ArgoCD OIDC provider and application
- `blueprints-provider-grafana.yaml` — Grafana OIDC provider and application
- `blueprints-provider-infisical.yaml` — Infisical OIDC provider and application
- `blueprints-proxy-providers.yaml` — forward-auth proxy providers for Longhorn, Hubble, and Sympozium
- `blueprints-agent-auth.yaml` — k8s-agent OAuth2 provider for OIDC-backed kubectl

Layer 13 is now fully declarative. If Authentik's database is lost, all providers, applications, and group mappings are recreated from blueprints on startup.

## ArgoCD: Self-Management

A surprise requirement: ArgoCD was not managing itself. It was bootstrapped manually with `helm install` during Layer 0 and never brought under App-of-Apps control. Changing its Helm values (to add OIDC config) had no declarative path — every change would require a manual `helm upgrade`.

The fix was to create an Application CR for ArgoCD:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: argocd
  namespace: argocd
spec:
  project: infrastructure
  sources:
    - repoURL: https://argoproj.github.io/argo-helm
      chart: argo-cd
      targetRevision: "9.4.6"
      helm:
        releaseName: argocd
        valueFiles:
          - $values/apps/argocd/values.yaml
    - repoURL: <git-repo>
      targetRevision: main
      ref: values
```

With `ignoreDifferences` on Secret `/data` and `prune: false`, ArgoCD adopted the existing Helm release without destroying anything. Now OIDC config changes are a git push away.

## Grafana: The Secret Key Name Trap

Grafana's OIDC integration uses `envFromSecret` to inject the client secret as an environment variable. The `grafana.ini` config references it with `${GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET}`.

The trap: the Kubernetes Secret key must exactly match the environment variable name. If the key is `client_secret`, Grafana gets an env var called `client_secret` — but the config references `GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET`. No error, no warning, just a silent authentication failure.

The role mapping uses a JMESPath expression on the `groups` claim:

```yaml
role_attribute_path: >-
  contains(groups[*], 'root-admins') && 'Admin'
  || contains(groups[*], 'root-devops') && 'Editor'
  || 'Viewer'
```

## What Remains Manual

Layer 13's manual operations are mostly complete. The Talos OIDC patch has been applied, ArgoCD and Grafana SSO are working, and forward-auth protects the proxy-outpost services. The one exception: **Infisical OIDC** was dropped (`n/a`) — Infisical's admin UI requires manual OIDC configuration, and the integration was deprioritized.

All manual operation statuses are tracked in `docs/runbooks/manual-operations.yaml`.

## The Result

Before Layer 13, the cluster had seven independent authentication boundaries. After:

- **One login** for ArgoCD, Grafana, and (pending) Infisical
- **One gate** protecting Longhorn, Hubble, and Sympozium UIs
- **One group model** mapping to roles across all services
- **One audit point** for who accessed what

The cluster still works without Authentik — every service falls back to local auth if the IdP is unreachable. But when it is reachable, one identity covers everything.
