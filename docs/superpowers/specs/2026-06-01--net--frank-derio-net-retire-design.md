# Retire `frank.derio.net` — Domain Decommission (Phase 2 of in-cluster ingress)

**Date:** 2026-06-01
**Last validated:** 2026-07-30
**Status:** Draft
**Layer:** net
**Supersedes/extends:** `docs/superpowers/specs/2026-03-29--net--in-cluster-ingress-design.md` (its "Future Work / Phase 2")

## Overview

Complete the Phase 2 work the in-cluster-ingress spec deferred. Make `cluster.derio.net` the sole domain for all Frank cluster services. Retire every `frank.derio.net` name **except `omni.frank.derio.net`** (architectural — Omni runs outside the cluster on raspi-omni and cannot be migrated). Cut over the kube-apiserver OIDC issuer with **zero OIDC-kubectl downtime** via dual-issuer authentication.

Phase 3 of the original spec — granting native OIDC to currently-forward-auth services (Gitea, Sympozium, Harbor) and removing their forward-auth middleware — is **out of scope** and tracked separately.

## Why now

Phase 1 of the in-cluster-ingress spec shipped 2026-03-29 and put every service behind `*.cluster.derio.net` via the in-cluster Traefik. The corresponding `*.frank.derio.net` routes on the off-repo raspi-omni Traefik were deliberately left running in parallel, with reference migration listed as future work. The half-done state is causing friction:

- Dozens of in-repo references still pin `frank.derio.net` (OIDC issuers, app callbacks, compatibility routes, blackbox probes, and landing links).
- Two parallel ingress paths must be reasoned about for every new service.
- The kube-apiserver still treats `auth.frank.derio.net` as its OIDC trust anchor — a single-point dependency on a legacy raspi-omni Traefik route.

The 2026-06-20 raspi-omni hardware outage made the dependency concrete. To restore access without changing every consumer while Omni was unavailable, the in-cluster Traefik temporarily took over `auth.frank.derio.net` and eight legacy service names. Omni is online again as of 2026-07-30, so machine configuration can be changed safely, but the emergency routes are now additional retirement scope rather than a reason to restore the old edge.

### 2026-07-30 live validation

- Omni UI and discovery return HTTP 200; its unauthenticated `:8100` API returns the expected HTTP 401.
- All seven Frank nodes are Ready on Kubernetes v1.35.3 / Talos v1.12.6; all three kube-apiserver static pods are Ready.
- The live kube-apiserver still carries the four legacy `--oidc-*` flags with issuer `auth.frank.derio.net`; no structured authentication file is mounted.
- Both `auth.frank.derio.net` and `auth.cluster.derio.net` serve discovery and JWKS. Each discovery document advertises the hostname used for that request, proving Authentik derives the issuer per request rather than fixing it from `AUTHENTIK_HOST`.
- The live `Kubernetes Agent Access` provider uses an eight-hour access-token lifetime and a 30-day refresh-token lifetime.
- Live ArgoCD state shows the affected leaf applications Synced/Healthy. The root application is Healthy but OutOfSync for unrelated `gpu-operator` and `longhorn` Application objects; implementation must start from a clean or explicitly understood GitOps baseline.

## Current state — in-repo inventory

Three blast-radius tiers:

### Tier 1 — OIDC trust anchors (control-plane + Authentik)

| File | Line | Field | Risk |
|------|------|-------|------|
| `patches/phase13-auth/oidc-apiserver.yaml` | 6 | `oidc-issuer-url` | Duplicate raw Talos patch; not the recorded rollout artifact |
| `patches/phase13-auth/omni-configpatch.yaml` | 12 | `oidc-issuer-url` | Authoritative Omni-applied kube-apiserver trust anchor |
| `apps/authentik/values.yaml` | 36 | `AUTHENTIK_HOST` | External host used by the embedded outpost for browser redirects |

### Tier 2 — Per-app OIDC callbacks and launch URLs

| File | Purpose |
|------|---------|
| `apps/argocd/values.yaml:111,114` | ArgoCD `url` + Dex issuer URL |
| `apps/authentik-extras/manifests/blueprints-provider-argocd.yaml:32-33,52` | ArgoCD provider redirect URIs + launch URL |
| `apps/authentik-extras/manifests/blueprints-provider-grafana.yaml:32,50` | Grafana provider redirect + launch |
| `apps/authentik-extras/manifests/blueprints-provider-infisical.yaml:33,50` | Infisical provider redirect + launch |
| `apps/victoria-metrics/values.yaml:143,150-152` | Grafana `root_url` + OAuth auth/token/userinfo endpoints |
| `apps/n8n-01/manifests/deployment.yaml:75` | n8n `WEBHOOK_URL` |
| `apps/authentik-extras/manifests/blueprints-proxy-providers.yaml:31,40,53,62,75,84,97,106` | Proxy-provider `external_host` + launch for Longhorn / Hubble / Sympozium / n8n |
| `apps/paperclip/manifests/configmap.yaml:24` | Legacy hostname remains in Paperclip's allowlist |

### Tier 2a — outage-era compatibility routes

`apps/traefik/manifests/ingressroutes.yaml` now contains temporary routes for `auth`, `grafana`, `argocd`, `longhorn`, `hubble`, `infisical`, `paperclip`, `sympozium`, and `n8n-01` under `frank.derio.net`. They terminate certificates in-cluster and must remain through the dual-issuer overlap, then be deleted in Phase 4.

### Tier 3 — Cosmetic / monitoring

| File | Purpose |
|------|---------|
| `apps/blackbox-exporter/manifests/vmprobe.yaml:11-12` | Uptime probes against `paperclip.frank` + `grafana.frank` |
| `clusters/hop/apps/landing/manifests/configmap.yaml:28-30` | Hop landing page links (ArgoCD, Grafana, Longhorn) |
| `apps/authentik-extras/manifests/lb-service.yaml:2` | Stale comment |
| `references/access.md:10` | Operator reference for Infisical |

### Preserved (architectural, NOT in scope)

| File | Purpose |
|------|---------|
| `apps/homepage/manifests/files/bookmarks.yaml:7` | Omni bookmark — Omni stays on `omni.frank.derio.net` |
| `apps/blackbox-exporter/manifests/vmprobe.yaml:30-31` | Omni uptime probes — kept |

## Target state

- Every `frank.derio.net` name except `omni` returns NXDOMAIN or no route.
- All services reachable + authenticating on `cluster.derio.net`.
- `kubectl` OIDC login works against a kubeconfig minted with `iss: auth.cluster.derio.net`; the apiserver trusts only `auth.cluster`.
- raspi-omni Traefik serves only Omni; everything else stripped.
- The Headscale split-DNS `frank.derio.net` entry survives (mesh clients still need to resolve `omni.frank.derio.net`); all other `frank.derio.net` records removed from on-prem DNS.

## Design decisions

### Dual-issuer apiserver authentication (zero-downtime)

The kube-apiserver's `--oidc-issuer-url` flag is a **cryptographic trust anchor**: tokens carry an `iss` claim that must exactly match the configured issuer URL, and the apiserver fetches discovery + JWKS from that URL. A single Authentik provider mints tokens with one `iss` value at a time, so a naive "flip the flag" cutover would invalidate every in-flight token at the moment Authentik's advertised host changes.

The cure is K8s structured `AuthenticationConfiguration` (GA on K8s 1.35), which allows the apiserver to register **multiple JWT authenticators**, each with its own issuer URL and discovery. During the overlap window:

- Authenticator A trusts `https://auth.frank.derio.net/application/o/k8s-agent/` → validates already-issued tokens until their TTL expires.
- Authenticator B trusts `https://auth.cluster.derio.net/application/o/k8s-agent/` → validates new tokens minted after Authentik flips its advertised host.

No token-rejection window. Once the old-token TTL elapses, authenticator A is removed and `auth.frank.derio.net` DNS can be retired.

**Consequence:** structured `AuthenticationConfiguration` and the legacy `--oidc-issuer-url` flag are **mutually exclusive** on the apiserver. This is not "add a second issuer flag" — it is *replacing* the legacy `oidc-*` extraArgs in the authoritative `omni-configpatch.yaml` with a Talos-delivered `AuthenticationConfiguration` file mounted into the apiserver via `cluster.apiServer.extraVolumes` + `--authentication-config`. The duplicate raw `oidc-apiserver.yaml` is removed in Phase 1.

### Single coordinated app-reference flip (vs. per-app incremental)

Once dual-issuer is in place on the apiserver, the remaining migrations are independent hostname swaps with a shared safety net (cert-based admin `KUBECONFIG` works throughout, dual-issuer covers in-flight tokens). Spreading them across many small PRs trades a brief planning win for a long-lived half-frank/half-cluster state and many separate verification runs.

This design flips Authentik's `AUTHENTIK_HOST` and all in-repo app/proxy/probe/landing references in **one coordinated PR**. Mixed state is hours, not weeks.

### Phase 4 trigger gated by token TTL

The wait between "Authentik now mints `iss: auth.cluster`" and "remove authenticator A from the apiserver" is bounded by the longest already-issued `auth.frank` access token. The blueprint and live provider both set the `k8s-agent` access-token lifetime to eight hours. Refresh tokens live for 30 days, but after consumers are repointed to `auth.cluster`, refreshed tokens use the request hostname and therefore carry the new issuer.

Phase 4 runs no sooner than eight hours after the final Phase 3 credential mint. Before removing authenticator A, verify both that a newly minted `auth.cluster` credential works and that the deliberately retained old `auth.frank` test credential has expired. There is no need to revoke all Authentik sessions for this migration.

### Control-plane recovery path

The current isolation kubeconfig authenticates to the Omni Kubernetes proxy with an Omni token; it is not a direct certificate-based Kubernetes admin kubeconfig. That path should remain usable if Kubernetes OIDC is misconfigured because Omni proxies with its own cluster authority, but it still depends on Omni being online.

Before Phase 2, prove the Omni-admin proxy path with a non-OIDC service-account credential and retain a second recovery mechanism if Omni supports minting a direct certificate-based admin kubeconfig. Do not begin the structured-auth rollout with only the interactive `auth.frank` login path available.

### Alternatives considered

- **Direct issuer flip:** simpler configuration, but immediately invalidates old tokens and turns a reversible hostname migration into an authentication maintenance window. Rejected.
- **Keep the compatibility routes indefinitely:** avoids control-plane work, but preserves the exact external-edge dependency this project is trying to remove and leaves two hostname schemes to maintain. Rejected.
- **Dual issuer with an eight-hour overlap:** more deliberate control-plane work, but preserves active sessions, provides an explicit rollback window, and ends in one canonical service domain. Selected.

### raspi-omni teardown documented, not declarative

The raspi-omni Traefik config that currently serves `*.frank.derio.net` is Ansible-managed and lives outside this repo. The plan cannot drive it declaratively. Instead, the cleanup is captured as a `# manual-operation` block in the plan, synced to `docs/runbooks/manual-operations.yaml` via `/sync-runbook`. The block covers stripping raspi-omni Traefik down to just Omni and removing `*.frank.derio.net` DNS records except `omni`. The Headscale `frank.derio.net` split-DNS entry stays because mesh clients still need the on-prem resolver for Omni.

## Architecture — migration sequence

```
Phase 1: Prep & verify             ──> Phase 2: Dual-issuer apiserver
  (no cutover, reversible)              (load-bearing: control-plane rollout)
        │                                       │
        ▼                                       ▼
  - Verify auth.cluster serves           - Replace legacy --oidc-* with
    Authentik (UI + discovery + JWKS)      structured AuthenticationConfig
  - Additively register cluster.* URIs   - Both auth.frank + auth.cluster
    on every Authentik provider            trusted simultaneously
  - Confirm *.cluster wildcard cert      - Verify with current token that
  - Confirm 8h access-token TTL            kubectl still works
  - Prove Omni-admin recovery path

Phase 3: Coordinated flip ──> Phase 4: Drop old issuer + DNS + raspi-omni
  (one PR, all references)         (TTL-gated, decision at end of Phase 3)
        │                                       │
        ▼                                       ▼
  - AUTHENTIK_HOST → auth.cluster       - Remove authenticator A
  - All Tier-2 app refs → cluster.*     - Remove frank.* redirect URIs from
  - All Tier-3 refs → cluster.*           Authentik providers
  - Re-mint k8s-agent kubeconfigs       - MANUAL: strip raspi-omni Traefik
  - auth.frank DNS MUST stay up         - MANUAL: remove *.frank DNS
    (apiserver JWKS for in-flight)        (except omni)
                                        - Keep Headscale split-DNS for Omni

                          Phase 5: Post-deploy checklist
                                  │
                                  ▼
                  - Retroactively update net-layer
                    building + operating posts
                  - Add gotchas (dual-issuer; structured auth on Talos)
                  - /sync-runbook + /update-readme
                  - Mark in-cluster-ingress spec Future Work as done
```

### Phase 1 — Prep & verify (no cutover)

Fully reversible. Establishes the safety net and gathers the unknowns.

- Confirm `auth.cluster.derio.net` serves Authentik end-to-end: load `/.well-known/openid-configuration`, verify `issuer` field, fetch `/jwks/`.
- Additively register `cluster.derio.net` redirect URIs on the ArgoCD, Grafana, and Infisical OIDC providers alongside the existing `frank` entries. The k8s-agent client-credentials provider has no redirect URI.
- Confirm the existing `*.cluster.derio.net` proxy providers are assigned to the embedded outpost. Their declarative definitions already coexist with the legacy providers; do not create another duplicate set.
- Confirm the in-cluster Traefik `*.cluster.derio.net` wildcard cert covers `auth.cluster`.
- Confirm the live `k8s-agent` access-token lifetime remains eight hours and record the exact cutover timestamp used to gate Phase 4.
- Mint and retain a direct old-issuer `k8s-agent` test credential before Phase 2 so continuity is measured rather than inferred from the Omni-proxied operator kubeconfig.
- Treat `patches/phase13-auth/omni-configpatch.yaml` as the authoritative rollout artifact: manual operation `auth-talos-oidc-patch` applied it and is marked done, and the live flags match its payload. Remove or repurpose the duplicate raw `oidc-apiserver.yaml` so the repository no longer carries two independently editable representations.
- Prove the Omni service-account kubeconfig can administer the cluster without an Authentik login. Mint and test a direct certificate-based admin kubeconfig as an additional recovery path if Omni supports it.
- Resolve or explicitly explain the root ArgoCD OutOfSync baseline before merging migration work.

### Phase 2 — Apiserver dual-issuer

The riskiest phase. Touches Talos machine config + control-plane rollout.

- Author `AuthenticationConfiguration` YAML listing two JWT authenticators (`auth.frank.derio.net` and `auth.cluster.derio.net`). Map `preferred_username` with the same explicit neutral `authentik:` prefix for both issuers and map `groups` with an empty prefix. The legacy flag implicitly used `<issuer>#` for usernames, which would make identities hostname-dependent; no RBAC binding targets `kind: User`, so this one-time normalization does not change authorization. Group names remain identical.
- Deliver it via Talos `machine.files` at `/var/lib/kubernetes/authn-config.yaml` (`op: create`, mode 0644), then mount that host file read-only at `/etc/kubernetes/authn-config.yaml` inside kube-apiserver and point `cluster.apiServer.extraArgs.authentication-config` at the container path. Talos v1.12 rejects `create` outside `/var`; mode 0600 also blocks kube-apiserver's non-root UID from reading the non-secret file.
- Replace the legacy `oidc-*` extraArgs in the authoritative Omni ConfigPatch and remove the duplicate raw patch representation.
- Roll out to all three control-plane nodes via Omni.
- **Verify before proceeding:** existing `k8s-agent` kubeconfig (`iss: auth.frank`) still authenticates kubectl after the rollout. If it does not, roll back the patch and diagnose before any user-facing flip.

### Phase 3 — Coordinated flip to `cluster.derio.net`

One PR, one merge, one ArgoCD sync wave for the whole reference set.

- `apps/authentik/values.yaml`: `AUTHENTIK_HOST` → `https://auth.cluster.derio.net`.
- `apps/argocd/values.yaml`: `url` + Dex issuer → `cluster.derio.net`.
- `apps/victoria-metrics/values.yaml`: Grafana `root_url` + `auth_url` + `token_url` + `api_url` → `cluster.derio.net`.
- `apps/n8n-01/manifests/deployment.yaml`: `WEBHOOK_URL` → `cluster.derio.net`.
- `apps/paperclip/manifests/configmap.yaml`: remove the legacy hostname from `PAPERCLIP_ALLOWED_HOSTNAMES` and its accompanying comment.
- The ArgoCD, Grafana, and Infisical `blueprints-provider-*.yaml` files: redirect URIs + `meta_launch_url` → `cluster.derio.net` (the additive cluster URIs from Phase 1 stay; the frank ones come out only in Phase 4). AWX is already cluster-only.
- Leave `blueprints-proxy-providers.yaml` unchanged during the cutover. The cluster-host proxy providers already exist as separate objects in `blueprints-cluster-proxy-providers.yaml`; rewriting the legacy objects would create duplicates.
- `apps/blackbox-exporter/manifests/vmprobe.yaml`: `paperclip.frank` + `grafana.frank` probes → `cluster.derio.net`.
- `clusters/hop/apps/landing/manifests/configmap.yaml`: ArgoCD / Grafana / Longhorn links → `cluster.derio.net`.
- `references/access.md`: Infisical operator URL → `cluster.derio.net`.
- `apps/authentik-extras/manifests/lb-service.yaml`: update stale comment.
- Re-mint `k8s-agent` kubeconfigs for affected users (they now carry `iss: auth.cluster`).
- **Verify:** each migrated app loads on `cluster.derio.net`, OIDC login round-trips, a freshly-minted kubeconfig authenticates kubectl, an old kubeconfig still authenticates (covers authenticator A).
- **DNS invariant:** `auth.frank.derio.net` must stay resolving + serving JWKS throughout this phase — the apiserver still uses authenticator A for in-flight token validation.

### Phase 4 — Drop old issuer + DNS + raspi-omni teardown

TTL-gated, see decision rule above.

- Remove authenticator A (`auth.frank`) from the `AuthenticationConfiguration`; roll out.
- Remove the now-orphaned `frank.derio.net` redirect URIs from the OIDC providers and change the legacy proxy-provider/application blueprint entries to `state: absent`. Keep that tombstone blueprint tracked so Authentik can enforce deletion without reintroducing hostname references.
- Delete all outage-era `*-frank` IngressRoutes and their `*.frank.derio.net` certificate requests from the in-cluster Traefik manifest.
- **`# manual-operation`** (synced to `docs/runbooks/manual-operations.yaml`):
  - Strip raspi-omni Traefik config to Omni-only (Ansible playbook).
  - Remove `*.frank.derio.net` records from on-prem DNS, leaving `omni.frank.derio.net` intact.
  - Keep `clusters/hop/apps/headscale/manifests/configmap.yaml:51-53` (`frank.derio.net` split-DNS entry), because mesh clients still need the on-prem resolver for `omni.frank.derio.net`.

### Phase 5 — Post-deploy checklist

This is a fix/extension of the existing **net** layer, so per `agents/rules/plan-post-deploy-checklist.md`:

- **Retroactively update** `blog/content/docs/building/24-in-cluster-ingress/index.md` and `blog/content/docs/operating/17-ingress/index.md` with the retirement narrative + the dual-issuer / structured-auth lessons. Do NOT create a new layer post.
- `/update-readme` — Service Access table loses any `frank.derio.net` references.
- `/sync-runbook` — picks up the Phase 4 `# manual-operation` block.
- One-liner in `agents/rules/frank-gotchas.md` (networking + a new auth note: "structured AuthenticationConfiguration is mutually exclusive with legacy `--oidc-*` flags") + full prose in `docs/runbooks/frank-gotchas/networking.md` and `docs/runbooks/frank-gotchas/authentik.md`.
- Mark Future Work in `2026-03-29--net--in-cluster-ingress-design.md` as done (only Phase 3 remains).
- Plan `**Status:**` → `Deployed`.

## Definition of done

- `dig auth.frank.derio.net @<on-prem-dns>` returns NXDOMAIN (or removed).
- `dig argocd.frank.derio.net`, `grafana.frank.derio.net`, `longhorn.frank.derio.net`, `comfyui.frank.derio.net`, `gpu.frank.derio.net`, `paperclip.frank.derio.net`, `hubble.frank.derio.net`, `infisical.frank.derio.net`, `litellm.frank.derio.net`, `n8n.frank.derio.net`, `sympozium.frank.derio.net`, `vk.frank.derio.net` all return NXDOMAIN (or removed).
- `dig omni.frank.derio.net` still resolves; `https://omni.frank.derio.net/` still serves Omni.
- All `*.cluster.derio.net` services unchanged in availability throughout the migration.
- A freshly-minted `k8s-agent` kubeconfig authenticates kubectl; an old `auth.frank`-issued kubeconfig is rejected (post-Phase 4).
- raspi-omni Traefik config (verified out-of-band on the host) serves only Omni.
- `rg "[a-z0-9-]+\.frank\.derio\.net" apps patches clusters references secrets` returns no non-historical matches except `omni.frank.derio.net` and the retained `frank.derio.net` Headscale split-DNS suffix.

## Test Plan

Post-merge Phase 1 verification is operator-driven and must complete before application cutover work begins:

1. Resolve or explicitly account for root ArgoCD drift, then prove the Omni service-account kubeconfig has cluster-admin access without an Authentik login.
2. Before applying the new patch, mint a direct old-issuer k8s-agent token. Record only its `iss`, `aud`, `exp`, `preferred_username`, groups, and TokenReview result; never commit token material.
3. Wait for `authentik-extras` to reconcile and confirm the live ArgoCD, Grafana, and Infisical providers contain both old and cluster callback URIs.
4. Record the pre-change ConfigPatch commit for rollback, then apply `patches/phase13-auth/omni-configpatch.yaml` through Omni.
5. Require all three kube-apiserver static pods Ready and `/readyz?verbose` passing throughout the rollout.
6. Inspect every kube-apiserver command and mount: exactly one `--authentication-config=/etc/kubernetes/authn-config.yaml`, no `--oidc-*` flags, and the authentication file mounted read-only.
7. Re-run TokenReview with the retained old token. Require username `authentik:<preferred_username>`, unchanged groups, and successful authorization; also verify Omni service-account administration still succeeds.
8. On any failed readiness, flag, mount, identity, group, or authorization check, re-apply the recorded legacy ConfigPatch and stop before Phase 3.

## Risks & rollback

| Risk | Mitigation | Rollback |
|------|------------|----------|
| Structured-auth misconfig bricks OIDC kubectl | Prove the Omni service-account proxy path before Phase 2; obtain direct certificate recovery if available; verify after each control-plane rollout step | Revert the Omni ConfigPatch through the proven non-OIDC path |
| Authentik issuer differs by hostname | Resolved live: each discovery document advertises the requested host, and both JWKS endpoints are healthy | Keep both host routes and authenticators until the overlap closes |
| Apiserver can't reach `auth.frank` JWKS mid-Phase-3 | DNS invariant: `auth.frank` stays up through Phase 3 | Keep the in-cluster compatibility route for `auth.frank` until Phase 4 |
| Re-minted kubeconfigs missed for some user | Inventory `k8s-agent` users in Phase 1 | Dual-issuer overlap covers them until next login |
| Headscale cleanup breaks `omni.frank` mesh resolution | The design explicitly retains the `frank.derio.net` split-DNS suffix | Restore the entry if it is changed out-of-band |
| ArgoCD self-heal partially syncs the Phase 3 PR | Single merge, all references in one commit; the root App-of-Apps reconciles every affected Application from the same SHA | Revert the commit; ArgoCD reconciles back |

## Out of scope

- **Phase 3 of the original spec** — native OIDC for Gitea / Sympozium / Harbor and removal of their forward-auth middleware. Separate future plan.
- Any change to Omni itself beyond keeping `omni.frank.derio.net` reachable.
- Migration of services not yet deployed (Harbor, KubeVirt) — they get `cluster.derio.net` from day one when deployed.
- Cosmetic rename of the `phase13-auth` patch directory.

## File summary

| File | Change |
|------|--------|
| `patches/phase13-auth/omni-configpatch.yaml` | Remove legacy `oidc-*` extraArgs; add structured `AuthenticationConfiguration` mount |
| `patches/phase13-auth/oidc-apiserver.yaml` | Remove duplicate non-authoritative patch representation |
| `patches/phase13-auth/authn-config.yaml` *(new)* | Structured `AuthenticationConfiguration` with two JWT authenticators (Phase 2), reduced to one (Phase 4) |
| `apps/authentik/values.yaml` | `AUTHENTIK_HOST` → `auth.cluster.derio.net` |
| `apps/argocd/values.yaml` | `url` + Dex `issuer` → cluster.derio.net |
| `apps/victoria-metrics/values.yaml` | Grafana `root_url` + OAuth URLs → cluster.derio.net |
| `apps/n8n-01/manifests/deployment.yaml` | `WEBHOOK_URL` → cluster.derio.net |
| `apps/paperclip/manifests/configmap.yaml` | Remove legacy hostname from allowed hosts |
| `apps/traefik/manifests/ingressroutes.yaml` | Remove nine outage-era `*.frank` compatibility routes after the overlap |
| `apps/authentik-extras/manifests/blueprints-provider-argocd.yaml` | Redirect URIs + launch → cluster.derio.net |
| `apps/authentik-extras/manifests/blueprints-provider-grafana.yaml` | Redirect + launch → cluster.derio.net |
| `apps/authentik-extras/manifests/blueprints-provider-infisical.yaml` | Redirect + launch → cluster.derio.net |
| `apps/authentik-extras/manifests/blueprints-proxy-providers.yaml` | Replace legacy Longhorn/Hubble/Sympozium/n8n objects with `state: absent` tombstones in Phase 4 |
| `apps/authentik-extras/manifests/lb-service.yaml` | Stale comment update |
| `apps/blackbox-exporter/manifests/vmprobe.yaml` | Probe targets `paperclip.frank` + `grafana.frank` → cluster.derio.net |
| `clusters/hop/apps/landing/manifests/configmap.yaml` | Landing links → cluster.derio.net |
| `references/access.md` | Infisical operator URL → cluster.derio.net |
| `docs/runbooks/manual-operations.yaml` | New entry from Phase 4 `# manual-operation` block (via `/sync-runbook`) |
| `agents/rules/frank-gotchas.md` | One-liner: structured-auth mutually exclusive with `--oidc-*` flags |
| `docs/runbooks/frank-gotchas/networking.md` | Full prose on the retirement + DNS sequencing |
| `docs/runbooks/frank-gotchas/authentik.md` | Full prose on the dual-issuer mechanism |
| `blog/content/docs/building/24-in-cluster-ingress/index.md` | Retroactive update — retirement narrative |
| `blog/content/docs/operating/17-ingress/index.md` | Retroactive update — operating notes |
| `README.md` | Service Access entries pruned (via `/update-readme`) |
| `docs/superpowers/specs/2026-03-29--net--in-cluster-ingress-design.md` | Mark Phase 2 of Future Work as done |

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-07-30--net--frank-derio-net-retire | `derio-net/frank` | `2026-07-30--net--frank-derio-net-retire` | — |
