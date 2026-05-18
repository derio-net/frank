# The Frank Papers — Paper 11: Identity for a Heterogeneous Stack

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Draft

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete and
`2026-05-16--repo--frank-papers-paper-00` published — series tooling
(scripts, shortcodes, dossier gate, Mermaid theme) and the publishing
voice are both established.

Paper 11 is the auth landscape paper: *Identity for a Heterogeneous Stack.*
Where Paper 00 mapped philosophies and Paper 10 mapped inference engines,
this paper maps **identity providers and their failure modes** for a
self-hosted cluster running a mix of OIDC-aware services, opaque
ingress-only web UIs, and CLIs that want short-lived tokens.

The capability question: when you have ten different web UIs, three of
which speak OIDC natively, four of which speak nothing but a username
field, two of which want SAML, and one of which is a CLI talking to a
gRPC backend — what do you put in front of all of them, and what do you
do when *that* thing goes down?

The paper maps seven vendors: **Authentik** (Frank's choice), **Keycloak**
(the heavy-enterprise default), **Dex** (federation-broker IdP behind
ArgoCD and friends), **Zitadel** (newer cloud-native IdP with a Rust
core), **Authelia** (lightweight forward-auth-only), **Ory Hydra +
Kratos** (composable identity primitives), and **Pomerium** (identity-aware
proxy that occupies a different stack position entirely).

Frank's case study is Authentik with the embedded outpost doing
forward-auth for every ingress-only service, plus OIDC for the apps that
speak it (Grafana, ArgoCD, Gitea). The scar tissue is real and
operationally relevant: blueprints can declare proxy providers but
cannot assign them to the embedded outpost (manual Django ORM step
forever), `AUTHENTIK_HOST` must be set or the outpost advertises
`0.0.0.0:9000`, and the 2026.x schema migration silently broke every
existing ProxyProvider until each blueprint was retrofitted.

## Phase 1: Dossier construction

Research the IdP / forward-auth / identity-aware-proxy landscape
independently. Source material: BeyondCorp (2014) as the IAP origin
paper, vendor docs from Authentik, Keycloak, Dex, Zitadel, and Authelia,
a practitioner talk on self-hosted SSO at homelab/SMB scale, and a
postmortem of an IdP outage that affected service-mesh-style fan-out.

Frank artefacts: the per-service forward-auth blueprint
(`apps/authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml`),
the Authentik Helm values with `blueprints.configMaps` and
`global.env: AUTHENTIK_HOST` (`apps/authentik/values.yaml`), the manual
Django ORM provider-assignment incident from `agents/rules/frank-argocd.md`,
the Grafana OIDC env-var-name gotcha
(`GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET`), the 2026.x schema migration
incident (added `invalidation_flow`, object-shaped `redirect_uris`,
`signing_key` UUID), and an Authentik admin-UI screenshot from
`https://authentik.cluster.derio.net`.

Parallel subagents are appropriate: one per vendor (Authentik, Keycloak,
Dex, Zitadel, Authelia, Ory, Pomerium). Merger reviews coverage and
deduplicates primary sources.

## Phase 2: Gate validation

Run `validate-dossier.py` and fix any gaps. Human gate: author reviews
the named gaps and counter-arguments. The key counter to nail:
**"OAuth-via-GitHub / Google is already federated and free for personal
use — why self-host an IdP at all?"** Frank's answer: the failure modes,
the multi-tenancy story (vCluster-per-tenant identity isolation), and
the offline-survival property (the cluster keeps working when the
upstream IdP doesn't).

## Phase 3: Scaffold + draft

Scaffold if not already done. Fill all sections in order, leaving TL;DR
for last. Capability paper budgets apply (not Paper 00's reduced budget):

- TL;DR (≤150 words) — written last
- §1 The capability (200–350 words) — where an IdP sits in the stack
  (between user and application, alongside ingress). `flowchart LR`
  showing browser → ingress → forward-auth outpost → IdP → application.
- §2 The landscape (400–600 words) — quadrant chart on
  *forward-auth-only ↔ full IdP* and *lightweight ↔ enterprise*; capability
  matrix on forward-auth, OIDC, SAML, federation, multi-tenancy.
- §3 How each option handles the hard part (800–1400 words) — one
  `flowchart TD` per vendor showing how it handles forward-auth and OIDC.
- §4 What scale changes (300–600 words) — token rotation cost, session
  storage, multi-replica state sync, the forward-auth fan-out problem
  (every request hits the outpost).
- §5 Frank's choice, and what happened (300–600 words) — Authentik +
  embedded outpost; **three scar callouts** (manual outpost-assignment,
  `AUTHENTIK_HOST` redirect-loop, 2026.x schema migration).
- §6 When Frank's answer doesn't generalize (200–400 words) — decision
  flowchart with four leaves: small-team-with-AD → Authelia,
  heterogeneous-stack → Authentik, enterprise-federation → Keycloak,
  on-service-mesh → Pomerium.
- §7 Roadmap (200–400 words) — passkeys, WebAuthn-first identity,
  the slow death of password-form login.

## Phase 4: Media fill

Per-paper cover: Frank examining a wall of glowing passport-style
identity badges, weighing/skeptical expression, reading glasses and tie.
Mermaid diagrams for §1, §3 (seven small architecture diagrams), §6
decision tree. Authentik admin-UI screenshot for §5. Validate with a
local `hugo --minify` build.

## Phase 5: Review + publish

Voice pass, TL;DR, dossier-link verification. Set `draft: false` and
`status: published`. The three scar callouts are load-bearing here —
they are why a reader trusts the paper. Voice pass must verify all three
land with real dates pulled from `docs/runbooks/frank-gotchas/authentik.md`
or commit history.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: update `blog/content/docs/papers/_index.md`,
verify the auto-rendered cross-link chips on `docs/building/13-unified-auth`
and `docs/operating/08-auth` (no manual edit needed — `papers-backlink.html`
queries Paper frontmatter at build time), update README if relevant,
set plan `**Status:**` to `Complete`.

## Phase summary

| # | Phase | Depends on |
|---|-------|-----------|
| 1 | Dossier construction | — |
| 2 | Gate validation | 1 |
| 3 | Scaffold + draft | 2 |
| 4 | Media fill | 3 |
| 5 | Review + publish | 4 |
| 6 | Post-deploy checklist | 5 |
