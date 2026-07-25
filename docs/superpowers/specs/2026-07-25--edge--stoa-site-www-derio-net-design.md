# agentic-stoa/site → www.derio.net — Design

**Date:** 2026-07-25
**Layer:** edge (extension of Layer 17 Public Edge; cicd aspects reuse the
existing stoa mirror + Gitea Actions platform)
**Status:** Draft
**Driver:** Operator ask — stand up a private `agentic-stoa/site` repo with
GitHub → Gitea mirroring and Gitea Actions CI matching the other agentic-stoa
repos, and put a "coming soon" `www.derio.net` page online that is secured and
monitored to blog parity.

## Goal

`www.derio.net` serves a real, versioned, container-delivered page instead of a
12-byte Caddy string literal — built from a private repo, mirrored to Frank's
Gitea, built by Gitea Actions on Frank, and watched by the same access-log /
CrowdSec / uptime-probe / analytics stack that guards the blog.

Scope is the "coming soon" page plus the whole delivery and observability
pipeline behind it. The conversion funnel is explicitly **not** in this spec —
the framework choice (§Decisions, Q2) exists so the funnel can land later
without a re-platform.

## Operator decisions (batched Q&A, 2026-07-25)

| # | Decision | Answer |
|---|---|---|
| 1 | Manifest ownership / image delivery | **Manifests in frank; image tag bumped by a Tekton promotion pipeline** using the existing `frank-gitops-push` credential |
| 2 | Site framework | **Astro** — static-first, zero JS by default, islands/SSR available when the funnel needs them |
| 3 | Narrative treatment | **Infra-only** — blog/README cover edge + CI mechanics, no business detail; repo referred to as "site" |
| 4 | Security / monitoring depth | **Blog parity plus security headers**, headers applied to the blog vhost too |
| 5 | Phase model tier | **Opus for every tier** |
| 6 | Manual-work placement | **Back-loaded** into one final `[manual]` phase |

Full rationale and rejected alternatives:
`docs/superpowers/journals/specs/2026-07-25--edge--stoa-site-www-derio-net.md`.

## Current state (measured 2026-07-25, not assumed)

- **`www.derio.net`**: DNS → `91.99.8.121` (Hop), TLS valid, served by a literal
  `respond "Coming soon." 200` in the Caddyfile. **No** access log, **no**
  `crowdsec` directive, **no** blackbox probe, **no** analytics. The apex
  `derio.net` resolves elsewhere (Cloudflare, `2a06:98c1:3120::3`) and is **out
  of scope** — only `www` is touched.
- **`agentic-stoa/site`**: exists, **private**, **empty** (size 0, no branches),
  default branch `main`. Covered by the `stoa-fr-automation` App —
  `repository_selection: all`, and `GET /repos/agentic-stoa/site` returns 200 on
  the ESO-minted token. Contents read/write confirmed against a peer private
  repo (200).
- **CI platform**: fully live. `act-runner` 2/2 Running on pc-1,
  `config.actions.ENABLED: true` in `apps/gitea/values.yaml`, GitHub →
  `webhooks.hop.derio.net` → Tekton `github-pull-sync` mirror path in service,
  Gitea→GitHub `stoa-status-bridge` trigger on `el-gitea-listener`. Nothing
  about the platform needs building — `site` is an *enrollment*, not a buildout.
- **`CI_AUTHORITY`**: currently `gitea` on **both** forges (flipped 2026-07-22
  when the GitHub Actions minutes tier was exhausted). New workflows must carry
  the standard guard so they inherit the flip correctly.
- **Hop**: has **no** External Secrets Operator and uses **no** `imagePullSecrets`
  anywhere — every image pull on Hop is anonymous. `ghcr.io/derio-net/blog` is
  confirmed publicly pullable (unauth manifest fetch → 200).

## Design

### 1. Repo: `agentic-stoa/site` (private, GitHub-origin)

Astro project at the repo root, plus a container image build. Layout:

```
src/pages/index.astro     # the coming-soon page
src/layouts/Base.astro    # shared shell (meta, analytics hook, CSP-friendly)
astro.config.mjs          # output: 'static'
Dockerfile                # build stage (node) → runtime stage (static server)
.github/workflows/ci.yml  # build + checks, both forges
CLAUDE.md / AGENTS.md     # agent instructions for the repo
```

Workflows live in `.github/workflows/` (not `.gitea/workflows/`) — Gitea Actions
reads that path, so a single file serves both forges, which is the established
stoa pattern of near-verbatim reuse.

**Runtime image.** Static output served by the same lightweight server the blog
image uses, listening on **8080** (matches the blog's container port and Hop's
probe conventions). Non-root, read-only-friendly, no shell tooling in the final
layer.

### 2. Image: `ghcr.io/agentic-stoa/site`, public package

Built and pushed by Gitea Actions using the existing Gitea org secret
`STOA_CI_GH_TOKEN` (the GHCR-capable token already provisioned for this exact
purpose), with the standard `${{ secrets.STOA_CI_GH_TOKEN || secrets.GITHUB_TOKEN }}`
fallback so the workflow is a no-op change on the GitHub side.

**The package is public; the source repo stays private.** This is a deliberate
trade-off, made because Hop has no ESO and no existing pull-secret path:

- A private package would require Hop's **first** `imagePullSecret`, backed by a
  long-lived manually-rotated token on a cluster that **cannot** auto-rotate it.
  That is precisely the silently-expiring-credential failure class this estate
  has been bitten by repeatedly (alert-agent OAuth, the Omni service-account
  kubeconfig) — a dead credential would present as an ImagePullBackOff on the
  public edge with no rotation alarm behind it.
- The artifact is a **public website**. Its content is served anonymously at
  `www.derio.net` by construction, so the package exposes nothing the site
  doesn't already publish.
- Residual risk is *pre-announcement content leakage* — someone who guesses the
  package name could read marketing copy before launch. Accepted for a
  coming-soon page.
- **Escalation path if that ever matters**: flip the package to private and add
  a SOPS-managed pull secret on Hop (consistent with Hop's existing manual
  Caddy/Tailscale secret pattern), accepting the rotation burden. Documented
  here so the decision is revisitable rather than rediscovered.

### 3. Delivery: Gitea Actions builds, Tekton promotes, ArgoCD deploys

```
GitHub push (main)
  → webhook → webhooks.hop.derio.net → Tekton github-pull-sync
  → Gitea mirror agentic-stoa/site (main)
  → Gitea Actions: build Astro → image → ghcr.io/agentic-stoa/site:<sha>
  → Gitea push webhook → el-gitea-listener → Tekton site-promotion
  → commits the tag into derio-net/frank
       clusters/hop/apps/www/manifests/deployment.yaml
  → ArgoCD (Hop) syncs → new pod → Caddy serves it
```

**Why Tekton owns the tag bump.** The promotion step needs push rights on
`derio-net/frank`, and the stoa-side App token explicitly cannot do that. The
`frank-gitops-push` ExternalSecret already mints a short-lived derio-net
installation token in `tekton-pipelines` for exactly this, and `cnc-promotion`
already proves the pattern (clone frank → `sed` the tag → commit → push main).
`site-promotion` is that pipeline narrowed to one manifest. **No new credential
is introduced anywhere in this design.**

The bump commit must be idempotent and race-safe: reset to `origin/main` on each
attempt (never `pull --rebase`, which leaves a conflicted tree when two builds
touch the same line), exit clean when already pinned, yield when a newer build
already won, and retry on a rejected push.

One deviation from the blog workflow, found in review: the ordering check must
run against **agentic-stoa/site**, not the frank clone. Both shas being compared
are *site* commits, and frank's object database has never seen them — so
`git merge-base` there errors out and, with stderr discarded, reads as "not an
ancestor", producing a guard that silently never fires. The pipeline therefore
fetches the site repo's history (using the already-present, read-only
`stoa-github-mirror` token) to resolve ancestry, and says so loudly when either
sha falls outside the fetched window rather than pretending the check happened.

#### Blocking prerequisite discovered while verifying this design

`frank-gitops-push` **does not currently work**, and has not since
2026-07-18 — 1477 consecutive failures measured on 2026-07-25:

```
error processing spec.dataFrom[0].sourceRef.generatorRef, err: error using
generator: error getting GH pem from secret: secrets
"github-app-derio-key" not found
```

The `github-app-derio` generator resolves `auth.privateKey.secretRef` in the
**consuming ExternalSecret's namespace** and ignores `secretRef.namespace` — the
documented ESO gotcha. `github-app-derio-key` exists only in `secure-agent-pod`;
its sibling `github-app-stoa-key` *is* in `tekton-pipelines`, which is exactly
why `stoa-github-mirror` syncs and this one does not.

**This is pre-existing and not introduced by this work**, but it is worth
flagging loudly because `cnc-promotion` is the current consumer: **CNC
staging/prod tag promotion into `derio-net/frank` cannot authenticate today.**

Repair = apply the derio App PEM into `tekton-pipelines` as well, following the
existing SOPS pattern in `secrets/github-app/`. It needs SOPS and the age key
(neither is present in the agent pod), so it is an **operator manual op** and a
**hard prerequisite** for `site-promotion`. It is placed in the back-loaded
manual phase, where it repairs CNC promotion as a side effect.

### 4. Serving: new `www` app on Hop

`clusters/hop/apps/www/manifests/` — namespace `www-system`, Deployment
(`replicas: 1`, image pinned by CI with the `# updated by CI — do not pin
manually` marker, readiness probe on `/`), Service on 8080. Root Application CR
+ namespace CR under `clusters/hop/apps/root/templates/`, mirroring the blog's
`blog.yaml` / `ns-blog.yaml` pair exactly.

Caddyfile `www.derio.net` block replaces `respond "Coming soon." 200` with:

```
www.derio.net {
  log
  crowdsec
  import security_headers
  reverse_proxy www.www-system.svc:8080
  handle_errors {
    respond "Coming soon." 200
  }
}
```

**The `handle_errors` fallback is load-bearing, not decoration.** Without it,
merging this PR would point Caddy at a backend whose first image does not exist
until the operator has finished the enrollment ops — turning `www.derio.net`
from "Coming soon." into a 502. With it, the vhost degrades to exactly today's
behaviour whenever the backend is unreachable. That removes the ordering
dependency between this PR and the manual phase entirely, and it keeps paying
afterwards: a crashed `www` pod shows visitors a holding page instead of a
gateway error.

### 5. Security headers (new, and retrofitted to the blog)

A Caddy snippet applied to both public site vhosts:

- `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy` — deny geolocation/camera/microphone/interest-cohort
- `Content-Security-Policy` — `default-src 'self'`, with an explicit allowance
  for `https://counter.derio.net` (GoatCounter script + beacon) and nothing else.
  `X-Frame-Options` is subsumed by CSP `frame-ancestors 'none'`.

**HSTS is the one-way door in this spec.** `preload` plus `includeSubDomains` is
hard to walk back and applies to every `*.derio.net` name a browser has seen.
The plan therefore ships HSTS **without `preload`** initially, and treats
promotion to preload as a separate, deliberate operator decision — noted here so
the omission reads as intent rather than oversight.

CSP is verified against the *rendered* page (blog included) before merge; a CSP
that silently breaks GoatCounter would take analytics down without taking the
site down, which is exactly the kind of quiet failure this estate keeps
cataloguing.

**Trade-off the fallback creates.** Because `handle_errors` answers 200, a
blackbox probe of `https://www.derio.net` stays green when the *backend* is
down — it catches an edge/Caddy outage only. That is correct while the holding
page is the intended state (a content assertion would page continuously before
launch), but it means Layer 17 under-covers this site until the real page
ships. Closing it is a post-launch step, not a permanent gap: once the built
page is live the www probe moves to a module asserting page content, so serving
the fallback becomes a failure signal rather than a silent pass.

### 6. Observability: blog parity

- **Access logs**: the `log` directive puts JSON request lines on stdout →
  fluent-bit on Hop → Frank VictoriaLogs. Queryable as
  `request.host:"www.derio.net"` with `kubernetes.host:hop-1` (per the
  networking gotcha — the vhost is in `request.host`, never `_msg`).
- **CrowdSec**: the `crowdsec` directive puts the bouncer in front of the proxy,
  same as the blog.
- **Uptime**: `https://www.derio.net` added to the `feature-health-probes`
  VMProbe (`probe_group: feature_health`).
- **Alerting**: `layer-17-edge-down` currently hardcodes
  `instance="https://blog.derio.net"`. Per Q4(a) this stays a **single** Layer-17
  rule, widened to match both edge instances via a regex so either site failing
  pages Layer 17 — the alert summary already interpolates `{{ $labels.instance }}`,
  so the firing alert names which site is down without a second rule to maintain.
- **Analytics**: GoatCounter on the existing `counter.derio.net` ingest, reusing
  the **existing single site** (`site_id=1`, `code=serve-jyfx75k2br7`, cname
  `counter.cluster.derio.net` — the only site in the DB, verified 2026-07-25).

  A *separate* site was considered and rejected: GoatCounter resolves the site
  from the count host, and `counter.derio.net` is already bound to site 1, so a
  second site would need a new public count hostname plus DNS, a Caddy route and
  a cert — real infrastructure for no analytical gain. **The two sites are
  already cleanly separable by path**: the outer Caddy redirects all of
  `blog.derio.net/*` to `/frank/*`, so every blog pageview records under
  `/frank/…`, while `www` records `/`. No commingling in practice, and no new
  DNS name to own. If `www` ever grows a `/frank`-shaped path this stops being
  true and the second site becomes the right call.

### 7. Enrollment in the mirror + CI platform

- `apps/tekton/triggers/eventlistener-github.yaml`: add `agentic-stoa/site` to
  the `agentic-stoa-main-sync` CEL filter (main-sync only — the site has no
  PR-gated test suite worth mirroring per-PR at this stage).
- `apps/tekton/triggers/eventlistener.yaml`: add the `site-promotion` trigger on
  the Gitea listener, filtered to `agentic-stoa/site` push-to-main.
- New `apps/tekton/pipelines/site-promotion.yaml`.

Everything else the platform already provides.

## What does NOT change

- The apex `derio.net` (Cloudflare-hosted) — untouched.
- The blog's build/deploy path — only its Caddy vhost gains the headers snippet.
- `CI_AUTHORITY` semantics — the new workflow inherits the existing guard and
  the current `gitea` setting on both forges.
- Tekton's existing per-repo CI pipelines and the status bridge.

## Deliverables

- **derio-net/frank (this repo, one PR):** Hop `www` app + root Application/ns
  CRs, Caddyfile vhost rewrite + shared security-headers snippet (blog included),
  `site-promotion` pipeline, both EventListener additions, VMProbe target,
  Layer-17 alert widening, manual-op blocks, runbook sync, gotchas, blog +
  README updates.
- **agentic-stoa/site (pushed directly, not a PR — the repo is empty and has no
  base branch to target):** Astro scaffold, Dockerfile, `.github/workflows/ci.yml`,
  `CLAUDE.md`/`AGENTS.md`. Repo name and file paths only in any public artifact —
  no business detail (`agents/rules/third-party-privacy.md`).

## Test Plan (post-merge, operator-driven)

1. **Page is live and real**: `curl -sI https://www.derio.net` → 200 from the
   container (not the string literal); body is the Astro page.
2. **Headers**: response carries HSTS, `X-Content-Type-Options`,
   `Referrer-Policy`, `Permissions-Policy`, CSP. Same for
   `https://blog.derio.net/frank`.
3. **Analytics**: load `www.derio.net` in a browser; the pageview appears in
   GoatCounter recorded against path `/` (distinct from the blog's `/frank/…`),
   and the browser console shows **no CSP violation**.
4. **Access logs**: `request.host:"www.derio.net"` returns the request in
   VictoriaLogs within a minute.
5. **Uptime**: `probe_success{instance="https://www.derio.net"}` present and `1`
   in VMUI; Layer-17 rule matches both instances.
6. **End-to-end delivery**: push a trivial copy change to `agentic-stoa/site`
   main → Gitea mirror updates → Gitea Actions run goes green → image pushed →
   `site-promotion` commits a tag bump to frank main → ArgoCD on Hop rolls the
   pod → the change is live. *(This is the claim that proves the layer; ArgoCD
   Synced/Healthy alone does not — per the "a layer is not Deployed until its
   workflow has been observed end-to-end" practice note.)*
7. **CrowdSec**: `www` requests appear in the agent's acquisition metrics
   (`cscli metrics` — parsed count rises), confirming the vhost is actually being
   read and not just proxied.

## Risks

- **Empty-repo bootstrap**: `agentic-stoa/site` has no branches, so the first
  push creates `main`. Nothing to PR against; the scaffold is pushed directly.
- **CSP vs GoatCounter**: a wrong `script-src`/`connect-src` breaks analytics
  silently while the site stays up. Mitigated by Test Plan step 3 checking the
  console, not just the pageview.
- **HSTS blast radius**: applies to `*.derio.net` in any browser that has seen
  the header. Mitigated by shipping without `preload` (§5).
- **Public GHCR package**: accepted, with a documented escalation path (§2).
- **Promotion race**: two rapid pushes could race on the frank tag bump.
  Mitigated by reusing the blog workflow's idempotent retry loop.
- **`frank-gitops-push` is broken today** (§3). Until the operator applies the
  derio App key into `tekton-pipelines`, `site-promotion` cannot push and Test
  Plan step 6 cannot pass. Everything upstream of the bump (mirror, Actions
  build, image push) works without it, and the page itself goes live from the
  first manually-pinned tag — so the failure mode is "new commits stop
  auto-deploying", not "site down".
- **pc-1 capacity**: one more Actions consumer on a runner at capacity 2. An
  Astro static build is light relative to the existing Playwright/compose jobs.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-07-25-edge-stoa-site-www-derio-net | `derio-net/frank` | `docs/superpowers/plans/2026-07-25-edge-stoa-site-www-derio-net` | — |
