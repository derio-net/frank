# Retire `frank.derio.net` — Domain Decommission (Phase 2 of in-cluster ingress)

**Date:** 2026-06-01
**Status:** Draft
**Layer:** net
**Supersedes/extends:** `docs/superpowers/specs/2026-03-29--net--in-cluster-ingress-design.md` (its "Future Work / Phase 2")

## Overview

Complete the Phase 2 work the in-cluster-ingress spec deferred. Make `cluster.derio.net` the sole domain for all Frank cluster services. Retire every `frank.derio.net` name **except `omni.frank.derio.net`** (architectural — Omni runs outside the cluster on raspi-omni and cannot be migrated). Cut over the kube-apiserver OIDC issuer with **zero OIDC-kubectl downtime** via dual-issuer authentication.

Phase 3 of the original spec — granting native OIDC to currently-forward-auth services (Gitea, Sympozium, Harbor) and removing their forward-auth middleware — is **out of scope** and tracked separately.

## Why now

Phase 1 of the in-cluster-ingress spec shipped 2026-03-29 and put every service behind `*.cluster.derio.net` via the in-cluster Traefik. The corresponding `*.frank.derio.net` routes on the off-repo raspi-omni Traefik were deliberately left running in parallel, with reference migration listed as future work. Eight months on, the half-done state is causing friction:

- 26 in-repo references still pin `frank.derio.net` (OIDC issuers, app callbacks, blackbox probes, landing links).
- Two parallel ingress paths must be reasoned about for every new service.
- The kube-apiserver still treats `auth.frank.derio.net` as its OIDC trust anchor — a single-point dependency on a legacy raspi-omni Traefik route.

## Current state — in-repo inventory

Three blast-radius tiers:

### Tier 1 — OIDC trust anchors (control-plane + Authentik)

| File | Line | Field | Risk |
|------|------|-------|------|
| `patches/phase13-auth/oidc-apiserver.yaml` | 6 | `oidc-issuer-url` | kube-apiserver trust anchor |
| `patches/phase13-auth/omni-configpatch.yaml` | 12 | `oidc-issuer-url` | Omni-injected apiserver arg (one of these two is authoritative — to be determined in Phase 1) |
| `apps/authentik/values.yaml` | 36 | `AUTHENTIK_HOST` | Issuer Authentik advertises in tokens (`iss` claim) |

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

### Tier 3 — Cosmetic / monitoring

| File | Purpose |
|------|---------|
| `apps/blackbox-exporter/manifests/vmprobe.yaml:11-12` | Uptime probes against `paperclip.frank` + `grafana.frank` |
| `clusters/hop/apps/landing/manifests/configmap.yaml:28-30` | Hop landing page links (ArgoCD, Grafana, Longhorn) |
| `apps/authentik-extras/manifests/lb-service.yaml:2` | Stale comment |

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

**Consequence:** structured `AuthenticationConfiguration` and the legacy `--oidc-issuer-url` flag are **mutually exclusive** on the apiserver. This is not "add a second issuer flag" — it is *replacing* the legacy `oidc-*` extraArgs in `patches/phase13-auth/` with a Talos-delivered `AuthenticationConfiguration` file mounted into the apiserver via `cluster.apiServer.extraVolumes` + `--authentication-config`. The work to determine which existing patch (`oidc-apiserver.yaml` vs `omni-configpatch.yaml`) is authoritative is a Phase 1 lookup.

### Single coordinated app-reference flip (vs. per-app incremental)

Once dual-issuer is in place on the apiserver, the remaining migrations are independent hostname swaps with a shared safety net (cert-based admin `KUBECONFIG` works throughout, dual-issuer covers in-flight tokens). Spreading them across many small PRs trades a brief planning win for a long-lived half-frank/half-cluster state and many separate verification runs.

This design flips Authentik's `AUTHENTIK_HOST` and all in-repo app/proxy/probe/landing references in **one coordinated PR**. Mixed state is hours, not weeks.

### Phase 4 trigger gated by token TTL

The wait between "Authentik now mints `iss: auth.cluster`" and "remove authenticator A from the apiserver" is bounded by the lifetime of the longest already-issued `auth.frank` token. That lifetime is unknown today — it lives in the Authentik `k8s-agent` OIDC provider configuration. Phase 1 must read it from the live cluster.

Decision rule (made at the end of Phase 3, not pre-baked):

- TTL ≤ a few hours → wait it out; Phase 4 runs in a follow-up session.
- TTL is days or weeks → force re-authentication by revoking active sessions in the Authentik admin UI; Phase 4 runs back-to-back.

### raspi-omni teardown documented, not declarative

The raspi-omni Traefik config that currently serves `*.frank.derio.net` is Ansible-managed and lives outside this repo. The plan cannot drive it declaratively. Instead, the cleanup is captured as a `# manual-operation` block in the plan, synced to `docs/runbooks/manual-operations.yaml` via `/sync-runbook`. The block covers: stripping raspi-omni Traefik down to just Omni, removing `*.frank.derio.net` DNS records (except `omni`), and trimming the Headscale `frank.derio.net` split-DNS entry if any of its on-prem targets become irrelevant.

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
  - Look up k8s-agent token TTL            kubectl still works
  - Resolve which of the two
    apiserver patches is authoritative

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
                                        - MANUAL: trim Headscale split-DNS

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
- Additively register `cluster.derio.net` redirect URIs on every Authentik provider (k8s-agent, argocd, grafana, infisical) and `external_host` / `meta_launch_url` entries on proxy providers — **alongside** the existing `frank` ones. Nothing removed.
- Confirm the in-cluster Traefik `*.cluster.derio.net` wildcard cert covers `auth.cluster`.
- **Look up the `k8s-agent` provider's access/ID-token TTL** in Authentik. Record it on the plan.
- **Determine which apiserver patch is authoritative** — `patches/phase13-auth/oidc-apiserver.yaml` (direct Talos) or `patches/phase13-auth/omni-configpatch.yaml` (Omni-injected). Read the live apiserver flags and trace which patch produced them.
- **Confirm Authentik's issuer-derivation behavior:** does it emit a fixed `iss` based on `AUTHENTIK_HOST`, or per-request based on the requesting host? This decides whether dropping `auth.frank` DNS in Phase 4 can break authenticator A's validation of in-flight tokens.

### Phase 2 — Apiserver dual-issuer

The riskiest phase. Touches Talos machine config + control-plane rollout.

- Author `AuthenticationConfiguration` YAML listing two JWT authenticators (`auth.frank.derio.net` and `auth.cluster.derio.net`). Define `claimMappings` for username + groups identically to the current `--oidc-username-claim` / `--oidc-groups-claim` flags.
- Deliver it via Talos `machine.files` (write to `/etc/kubernetes/authn-config.yaml`) + `cluster.apiServer.extraVolumes` mount + `cluster.apiServer.extraArgs.authentication-config: /etc/kubernetes/authn-config.yaml`.
- Remove the legacy `oidc-*` extraArgs from whichever patch was authoritative (Phase 1 finding).
- Roll out to all three control-plane nodes via Omni.
- **Verify before proceeding:** existing `k8s-agent` kubeconfig (`iss: auth.frank`) still authenticates kubectl after the rollout. If it does not, roll back the patch and diagnose before any user-facing flip.

### Phase 3 — Coordinated flip to `cluster.derio.net`

One PR, one merge, one ArgoCD sync wave for the whole reference set.

- `apps/authentik/values.yaml`: `AUTHENTIK_HOST` → `https://auth.cluster.derio.net`.
- `apps/argocd/values.yaml`: `url` + Dex issuer → `cluster.derio.net`.
- `apps/victoria-metrics/values.yaml`: Grafana `root_url` + `auth_url` + `token_url` + `api_url` → `cluster.derio.net`.
- `apps/n8n-01/manifests/deployment.yaml`: `WEBHOOK_URL` → `cluster.derio.net`.
- All four `blueprints-provider-*.yaml` files: redirect URIs + `meta_launch_url` → `cluster.derio.net` (the additive cluster URIs from Phase 1 stay; the frank ones come out only in Phase 4).
- `blueprints-proxy-providers.yaml`: `external_host` + `meta_launch_url` for Longhorn / Hubble / Sympozium / n8n → `cluster.derio.net`.
- `apps/blackbox-exporter/manifests/vmprobe.yaml`: `paperclip.frank` + `grafana.frank` probes → `cluster.derio.net`.
- `clusters/hop/apps/landing/manifests/configmap.yaml`: ArgoCD / Grafana / Longhorn links → `cluster.derio.net`.
- `apps/authentik-extras/manifests/lb-service.yaml`: update stale comment.
- Re-mint `k8s-agent` kubeconfigs for affected users (they now carry `iss: auth.cluster`).
- **Verify:** each migrated app loads on `cluster.derio.net`, OIDC login round-trips, a freshly-minted kubeconfig authenticates kubectl, an old kubeconfig still authenticates (covers authenticator A).
- **DNS invariant:** `auth.frank.derio.net` must stay resolving + serving JWKS throughout this phase — the apiserver still uses authenticator A for in-flight token validation.

### Phase 4 — Drop old issuer + DNS + raspi-omni teardown

TTL-gated, see decision rule above.

- Remove authenticator A (`auth.frank`) from the `AuthenticationConfiguration`; roll out.
- Remove the now-orphaned `frank.derio.net` redirect URIs from the four Authentik providers and proxy-provider entries.
- **`# manual-operation`** (synced to `docs/runbooks/manual-operations.yaml`):
  - Strip raspi-omni Traefik config to Omni-only (Ansible playbook).
  - Remove `*.frank.derio.net` records from on-prem DNS, leaving `omni.frank.derio.net` intact.
  - Audit `clusters/hop/apps/headscale/manifests/configmap.yaml:51-53` (`frank.derio.net` split-DNS entry) — keep if mesh clients still need to resolve `omni.frank.derio.net` via on-prem DNS; trim otherwise.

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
- `grep -rniE "[a-z0-9-]+\.frank\.derio\.net" apps/ patches/ clusters/ secrets/ | grep -v "omni\.frank\.derio\.net"` returns zero matches.

## Risks & rollback

| Risk | Mitigation | Rollback |
|------|------------|----------|
| Structured-auth misconfig bricks OIDC kubectl | Phase 2 verification gate before any user-facing flip; cert admin `KUBECONFIG` is unaffected | Revert the Talos patch; Omni rolls control-plane back |
| Authentik issuer-derivation surprise (Phase 1 unknown) | Phase 1 lookup must resolve this before Phase 2 | n/a — gate; do not proceed if unresolved |
| Apiserver can't reach `auth.frank` JWKS mid-Phase-3 | DNS invariant: `auth.frank` stays up through Phase 3 | Keep raspi-omni Traefik route for `auth.frank` until Phase 4 |
| Re-minted kubeconfigs missed for some user | Inventory `k8s-agent` users in Phase 1 | Dual-issuer overlap covers them until next login |
| Headscale split-DNS trim breaks `omni.frank` mesh resolution | Phase 4 manual-op explicitly audits this | Restore the entry |
| ArgoCD self-heal partially syncs the Phase 3 PR | Single merge, all references in one commit; the root App-of-Apps reconciles every affected Application from the same SHA | Revert the commit; ArgoCD reconciles back |

## Out of scope

- **Phase 3 of the original spec** — native OIDC for Gitea / Sympozium / Harbor and removal of their forward-auth middleware. Separate future plan.
- Any change to Omni itself beyond keeping `omni.frank.derio.net` reachable.
- Migration of services not yet deployed (Harbor, KubeVirt) — they get `cluster.derio.net` from day one when deployed.
- Cosmetic rename of the `phase13-auth` patch directory.

## File summary

| File | Change |
|------|--------|
| `patches/phase13-auth/<authoritative>.yaml` | Remove legacy `oidc-*` extraArgs; add structured `AuthenticationConfiguration` mount |
| `patches/phase13-auth/authn-config.yaml` *(new)* | Structured `AuthenticationConfiguration` with two JWT authenticators (Phase 2), reduced to one (Phase 4) |
| `apps/authentik/values.yaml` | `AUTHENTIK_HOST` → `auth.cluster.derio.net` |
| `apps/argocd/values.yaml` | `url` + Dex `issuer` → cluster.derio.net |
| `apps/victoria-metrics/values.yaml` | Grafana `root_url` + OAuth URLs → cluster.derio.net |
| `apps/n8n-01/manifests/deployment.yaml` | `WEBHOOK_URL` → cluster.derio.net |
| `apps/authentik-extras/manifests/blueprints-provider-argocd.yaml` | Redirect URIs + launch → cluster.derio.net |
| `apps/authentik-extras/manifests/blueprints-provider-grafana.yaml` | Redirect + launch → cluster.derio.net |
| `apps/authentik-extras/manifests/blueprints-provider-infisical.yaml` | Redirect + launch → cluster.derio.net |
| `apps/authentik-extras/manifests/blueprints-proxy-providers.yaml` | `external_host` + launch for Longhorn/Hubble/Sympozium/n8n → cluster.derio.net |
| `apps/authentik-extras/manifests/lb-service.yaml` | Stale comment update |
| `apps/blackbox-exporter/manifests/vmprobe.yaml` | Probe targets `paperclip.frank` + `grafana.frank` → cluster.derio.net |
| `clusters/hop/apps/landing/manifests/configmap.yaml` | Landing links → cluster.derio.net |
| `docs/runbooks/manual-operations.yaml` | New entry from Phase 4 `# manual-operation` block (via `/sync-runbook`) |
| `agents/rules/frank-gotchas.md` | One-liner: structured-auth mutually exclusive with `--oidc-*` flags |
| `docs/runbooks/frank-gotchas/networking.md` | Full prose on the retirement + DNS sequencing |
| `docs/runbooks/frank-gotchas/authentik.md` | Full prose on the dual-issuer mechanism |
| `blog/content/docs/building/24-in-cluster-ingress/index.md` | Retroactive update — retirement narrative |
| `blog/content/docs/operating/17-ingress/index.md` | Retroactive update — operating notes |
| `README.md` | Service Access entries pruned (via `/update-readme`) |
| `docs/superpowers/specs/2026-03-29--net--in-cluster-ingress-design.md` | Mark Phase 2 of Future Work as done |

## Implementation plans

| Plan | Repo | File |
|------|------|------|
| Retire frank.derio.net (Phase 2) Implementation Plan | derio-net/frank | `docs/superpowers/plans/2026-06-01--net--frank-derio-net-retire.md` *(to be written)* |
