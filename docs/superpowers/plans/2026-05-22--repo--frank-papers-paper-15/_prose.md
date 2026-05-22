# The Frank Papers — Paper 15: Ingress, Forward-Auth, and the Service Catalog

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Planning — Paper 15 plan drafted on branch `paper-15`; PR open for human review.

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete (scripts,
shortcodes, dossier gate, `agents/skills/papers/SKILL.md`). Papers 00, 02, 03,
04, 06, 07, 09, 10, 11, 14 published.

Paper 15 is the ingress-and-catalog Paper in the series: 2400–4200 words, the
standard skeleton (§1 capability → §2 landscape → §3 architecture per vendor
→ §4 scale → §5 Frank's choice → §6 generalization → §7 roadmap), and the
first Paper to map a *three-axis* vendor space — because once you have
services in the cluster, the question "how do humans reach them" is really
three questions stacked: which controller terminates TLS and routes by host,
where does auth happen (per-app SDK, edge forward-auth, mesh mTLS), and how
do humans find the services in the first place.

The capability question is: *once you have services in the cluster, how do
humans (and other clusters) actually reach them safely and discoverably —
without bolting per-app auth onto every workload?* The vendor space splits
along three axes: which ingress controller terminates TLS and routes by
hostname (Nginx, Traefik, Envoy/Contour, Gateway API conformant impls);
where authentication happens (per-app OIDC SDK, edge forward-auth via
Authentik / oauth2-proxy, or service-mesh mTLS via Istio/Linkerd); and how
services are catalogued for human discovery (Homepage, Heimdall, Dashy,
Organizr — or "no catalogue, just bookmarks"). Four-to-six candidates make
the landscape, with **Traefik + Authentik forward-auth + gethomepage.dev
Homepage** as Frank's case study — a three-layer composition where Traefik
terminates TLS at `*.cluster.derio.net` via Let's Encrypt + Cloudflare
DNS-01, every IngressRoute that wants SSO chains the `authentik-forwardauth`
middleware to the embedded Authentik outpost, and Homepage at
`master.cluster.derio.net` is the human-visible doorway to the cluster.

The scars are the point. The Cilium `lbipam.cilium.io/ips` annotation that
is NOT a sharing directive — separate Services that target the same LB IP
need a matching `lbipam.cilium.io/sharing-key` or one of them ends up
`<pending>` and you learn this only by `kubectl get svc -A | grep pending`.
The Authentik blueprint that creates proxy providers and applications
declaratively but does NOT assign them to the embedded outpost — that step
lives in Django ORM, runs manually after every fresh deploy, and is the only
out-of-band step in an otherwise fully-declarative auth chain. The
`AUTHENTIK_HOST` env var that, when omitted, makes forward-auth redirects
point at `0.0.0.0:9000` — the symptom is "login works but the redirect
lands on a broken URL", and the cause is buried in the outpost's
self-discovery logic. The 2026.x API shape changes that require
`invalidation_flow` and object-shaped `redirect_uris` and a `signing_key`
UUID — discovered by upgrading and watching every blueprint fail validation
silently. The three-axis fan-out itself: choosing Traefik commits you to a
specific forward-auth wiring; choosing per-app OIDC SDKs frees you from the
forward-auth tax but multiplies callback-URL maintenance by the number of
apps; choosing a service mesh moves auth into sidecars and gives up edge
visibility for east-west enforcement.

## Phase 1: Dossier construction

Four-to-six vendors across the ingress + auth + catalogue axes, ≥5 primary
sources across ≥3 type values, ≥3 Frank artefacts across ≥2 kinds, the
named gap on the absence of an apples-to-apples forward-auth latency
overhead benchmark at homelab QPS (vendor benchmarks measure 10k+ QPS
scenarios that don't translate to 0.5 QPS per service), and the
counter-argument that for a single-team SaaS behind Cloudflare Access, you
don't need any of this — Cloudflare handles ingress + auth + catalogue.
Parallel subagents per vendor are appropriate — one each for Traefik,
Nginx Ingress, Envoy/Contour or Gateway API conformant impls, Authentik
(as forward-auth provider), oauth2-proxy, service-mesh mTLS, and Homepage
(plus at least one comparison to Heimdall/Dashy) — with a merger pass.

## Phase 2: Gate validation

Run `validate-dossier.py`. Human gate: author reviews the named gap and
the counter-argument. The counter to nail: *"for a single-team SaaS
behind Cloudflare Access, you don't need any of this — Cloudflare handles
ingress + auth + catalogue. Why does Frank's in-cluster stack win?"*
Same shape as Paper 09's framing applied to the ingress capability.

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. Section order is fixed:

- TL;DR (≤150 words) — write last
- §1 The capability (200–350 words) + `flowchart LR` stack-position diagram
  ("where ingress, forward-auth, and catalogue sit between the cluster
  boundary and the human")
- §2 The landscape (400–600 words) + `{{< papers/landscape >}}` +
  `{{< papers/capability-matrix >}}` reading from `data/vendors.yaml`
- §3 How each option handles the hard part (800–1400 words) + one
  `flowchart TD` per vendor showing how the ingress hands off to auth
  (per-app SDK vs forward-auth vs mesh sidecar)
- §4 What scale changes (300–600 words) + benchmark callouts (forward-auth
  round-trip cost at p99, catalogue refresh cost, IngressRoute CRD
  reconcile latency at N routes)
- §5 Frank's choice, and what happened (300–600 words) + 1–3
  `{{< papers/scar >}}` callouts (Cilium LB sharing-key, Authentik
  blueprint manual outpost-provider step, `AUTHENTIK_HOST` env requirement,
  2026.x invalidation_flow + signing_key UUID API changes)
- §6 When Frank's answer doesn't generalize (200–400 words) + decision
  flowchart, ≤4 leaves (Cloudflare Access vs in-cluster forward-auth vs
  per-app OIDC SDK vs service-mesh mTLS)
- §7 Roadmap & where this space is going (200–400 words)
- §8 References — auto-rendered from frontmatter

## Phase 4: Media fill

Per-paper cover: Frank standing at a triage desk with multiple request
slips routing toward a single door labelled "AUTH", other doors labelled
with service names — weighing expression, thin black tie, round reading
glasses. The visual metaphor is *triage at the front door*. Mermaid
diagrams: §1 stack position, §2 landscape (quadrantChart) + capability
matrix, §3 four-to-six architecture flowcharts, §6 decision tree. At
least one Homepage dashboard screenshot from `master.cluster.derio.net`
or `kubectl describe ingressroute` output captured live from the cluster.
Cluster-side captures may be deferred with `-TODO.png` placeholders if
access is unavailable.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster — first-person plural or third-
person cluster, not academic). TL;DR ≤150 words written last. Dossier-link
rendering check (use either inline shortcode OR rely on automatic injection
— not both). Set `draft: false`, `status: published`. CI deploys via the
existing blog pipeline.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: update `_index.md`, verify the
auto-rendered cross-link chips appear on Building 24-in-cluster-ingress
and Operating 17-ingress, update README if relevant, set plan status to
Complete.

## Phase summary

| # | Phase | Depends on |
|---|-------|-----------|
| 1 | Dossier construction | — |
| 2 | Gate validation | 1 |
| 3 | Scaffold + draft | 2 |
| 4 | Media fill | 3 |
| 5 | Review + publish | 4 |
| 6 | Post-deploy checklist | 5 |
