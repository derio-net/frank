# Stoa live-mirror-sync trigger — Tekton + Gitea webhook (GH #444)

**Date:** 2026-06-04
**Layer:** cicd (extension of the existing CI/Gitea layer — fix/extension workflow, no new blog post)
**Status:** Approved
**Driver:** [derio-net/frank#444](https://github.com/derio-net/frank/issues/444) — cross-org ask from Stoa (STO-75, parent STO-72)

## Goal

A merge to `agentic-stoa/companies` `main` fires the Paperclip live-mirror-sync
routine (`2f4d361b`) push-driven, replacing a daily `0 6 * * *` Paperclip cron.
The Tekton manifests are Stoa-canonical, checked into `agentic-stoa/companies`
at `stoa/ci/tekton/live-mirror-sync/` (merge commit `b61b374d`, PR
agentic-stoa/companies#15). Frank provisions the trigger chain; the cron stays
armed until the webhook path is verified end-to-end (no coverage gap).

## Findings the issue didn't know about

1. **The Gitea mirror of `agentic-stoa/companies` does not exist.** Verified
   via Gitea API: `hum`, `content-factory`, and `stoa-blog` all exist
   (`mirror: false` — plain repos push-synced by the `github-pull-sync`
   pipeline from the `github-listener`; exactly the three repos in the
   `agentic-stoa-main-sync` cel filter today), `companies` is `not found`.
   The entire webhook chain presupposes this mirror; creating it (and its
   sync path) is a prerequisite of this work.
2. **The upstream EventListener's `github` interceptor is *expected to
   work* on Frank — the repo gotcha saying otherwise is stale.** Frank's
   Tekton gotcha ("Gitea sends `X-Gitea-Event`, not `X-GitHub-Event` — use
   `cel`, not `github`") predates Frank's current Gitea: **1.25.4** (verified
   live) sets the GitHub-compat headers `X-GitHub-Event` *and*
   `X-Hub-Signature-256: sha256=<hex>` on every webhook delivery — exactly
   what the `github` ClusterInterceptor reads for `eventTypes` and HMAC.
   The existing `gitea-listener` uses `cel` for unrelated reasons (it also
   deliberately omits HMAC as ClusterIP-only); that is not evidence the
   `github` interceptor is broken. Still verified live before cutover (see
   Risks) — and the gotcha gets corrected either way (see Post-deploy).
3. **Namespace mapping:** the issue says `tekton-triggers` namespace; Frank's
   convention is `tekton-pipelines` (where `tekton-triggers-sa`, the
   interceptors, and all Tekton secrets live). Everything lands there. The
   upstream manifests carry no `namespace:` so the ArgoCD Application's
   destination handles it.
4. **ArgoCD has zero repository-credential secrets today** — every current
   source is the public `derio-net/frank` repo. Sourcing the private Gitea
   mirror requires Frank's first ArgoCD repo credential.
5. **RBAC is already sufficient.** The vendored ClusterRole
   `tekton-triggers-eventlistener-roles`
   (`apps/tekton/vendor/triggers/release.yaml`) grants `create` on
   `taskruns` (alongside `pipelineruns`), and `triggers-rbac.yaml` binds
   `tekton-triggers-sa` to it in `tekton-pipelines`. The TriggerTemplate's
   TaskRun creation needs **no RBAC change**.

## Decisions (with alternatives considered)

| # | Decision | Alternatives rejected |
|---|----------|----------------------|
| 1 | **Build the full mirror chain**, matching the existing convention for the other 3 stoa repos (create Gitea repo, stoa-bot push, extend `agentic-stoa-main-sync` cel filter, GitHub push webhook via `webhooks.hop.derio.net`) | Trigger off GitHub directly (deviates from STO-75 architecture, breaks acceptance criteria, no in-cluster manifest source); Gitea pull-mirror (polling delay in a flow meant to kill a cron; breaks repo convention) |
| 2 | **ArgoCD Application pinned to SHA `b61b374d`**, sourced from the Gitea mirror, path `stoa/ci/tekton/live-mirror-sync` — upstream changes propagate via explicit pin-bump PRs in frank | Track `main` (gives a third-party org unattended apply-to-cluster rights); vendor copies (contradicts the issue's explicit instruction) |
| 3 | **Verify the github-interceptor live** — expected to pass on Gitea 1.25.4 (GitHub-compat headers); only if it genuinely drops, investigate (webhook content-type, secret value, cel `body.ref`) before touching the interceptor, and any upstream PR must keep the `github` interceptor + HMAC | Pre-emptive upstream PR (would "fix" something Frank's Gitea demonstrably supports); swapping to cel-only (drops HMAC, weakens Stoa's defense-in-depth) |
| 4 | **Infisical + ExternalSecret** for both secrets, matching every existing Tekton secret | SOPS (these aren't bootstrap secrets); plain `kubectl create secret` (invisible to GitOps, unreproducible) |

## Architecture

```
merge to agentic-stoa/companies main (GitHub)
  └─ GitHub push webhook ──▶ webhooks.hop.derio.net (Hop Caddy, existing)
       └─▶ 192.168.55.223 github-listener (existing)
            └─ agentic-stoa-main-sync trigger          ← cel filter extended with 'companies'
                 └─▶ github-pull-sync PipelineRun       ← existing pipeline, stoa-bot SSH
                      └─ push to Gitea mirror main      ← mirror repo created in this work
                           └─ Gitea push webhook ──▶ el-live-mirror-sync.tekton-pipelines.svc:8080
                                └─ live-mirror-sync EventListener   ← upstream manifests, ArgoCD-applied
                                     ├─ HMAC verify (live-mirror-gitea-webhook secret)
                                     ├─ cel: ref == refs/heads/main
                                     └─▶ TaskRun fire-paperclip-webhook
                                          └─ POST paperclip-lb.paperclip-system.svc:3100
                                             /api/routine-triggers/public/31cbc6…/fire
                                             (X-Paperclip-Signature HMAC, 202 = accepted)
                                                └─ Paperclip run issue under routine 2f4d361b
```

Properties:

- **Everything new stays in-cluster.** Only public surface is the existing
  `webhooks.hop.derio.net` (HMAC-verified by `stoa-github-webhook-secret`).
  The new EventListener is ClusterIP-only; Gitea reaches it via
  `*.svc.cluster.local`, already permitted by its `ALLOWED_HOST_LIST`.
- **No vendoring.** Upstream manifests are applied straight from the Gitea
  mirror by ArgoCD; Stoa stays source of truth; frank controls *which* commit
  via the pin.
- **The daily Paperclip cron stays armed** until the end-to-end signal is
  observed; Stoa retires it (issue's own cutover rule).

## Components

### A. `derio-net/frank` changes (one PR)

1. **`apps/root/templates/stoa-live-mirror-sync.yaml`** — new Application:
   - `source.repoURL`: in-cluster Gitea mirror clone URL (exact Gitea service
     name confirmed at planning time)
   - `targetRevision: b61b374dce649744a914dfd2626c450c66fea8eb` (pinned)
   - `path: stoa/ci/tekton/live-mirror-sync` (`directory.exclude: README.md`
     is cosmetic — ArgoCD ignores non-manifest files — keep for clarity)
   - `destination.namespace: tekton-pipelines`; standard sync options
     (`ServerSideApply=true`, `prune: false`, `selfHeal: true`)
2. **ArgoCD repo credential** — ExternalSecret producing a Secret in the
   `argocd` namespace labeled `argocd.argoproj.io/secret-type: repository`
   with `url` + `username`/`password` (Gitea token from Infisical). Placement
   (new `apps/argocd-extras/` vs existing manifests dir) decided at planning.
3. **`apps/tekton/triggers/eventlistener-github.yaml`** — extend the
   `agentic-stoa-main-sync` cel filter's `in [...]` list (currently
   `'agentic-stoa/hum', 'agentic-stoa/content-factory',
   'agentic-stoa/stoa-blog'`) with `'agentic-stoa/companies'` — additive
   only, the existing three entries stay.
4. **Two ExternalSecrets in `apps/tekton/manifests/`:**
   - `externalsecret-live-mirror-paperclip.yaml` → Secret
     `live-mirror-paperclip` (keys `fireUrl`, `webhookSecret`)
   - `externalsecret-live-mirror-gitea-webhook.yaml` → Secret
     `live-mirror-gitea-webhook` (key `webhookSecret`)

### B. Upstream (`agentic-stoa/companies`) — contingent

If live verification shows the webhook genuinely not firing, diagnose from
EventListener pod logs before assuming the interceptor (likelier suspects:
webhook content-type not `application/json`, secret mismatch, cel
`body.ref`). If an upstream manifest change does turn out to be needed, the
PR **must preserve the `github` interceptor and HMAC verification** — no
cel-only downgrade — then bump the frank-side pin.

### C. Planning-time checks

- Exact Gitea HTTP service DNS name for the ArgoCD `repoURL` (expected
  `gitea-http.gitea.svc.cluster.local:3000` from the chart — confirm).
- Gitea token scope for the ArgoCD repo credential: verify whether Gitea
  1.25.4 tokens can be scoped read-only to a single repo; if scopes are
  repo-coarse, create a **dedicated low-privilege Gitea user** whose only
  visibility is `agentic-stoa/companies` rather than letting
  "least-privilege" stay aspirational.

## Secrets (Infisical → ESO)

| Infisical key | → Secret/key | Value origin |
|---|---|---|
| `STOA_LIVE_MIRROR_FIRE_URL` | `live-mirror-paperclip/fireUrl` | `http://paperclip-lb.paperclip-system.svc.cluster.local:3100/api/routine-triggers/public/31cbc6fb3c8ac34e3f25d677/fire` |
| `STOA_LIVE_MIRROR_HMAC_SECRET` | `live-mirror-paperclip/webhookSecret` | **Out-of-band from Stoa's CTO** — operator pastes into Infisical during handoff; never in git/issues/chat |
| `STOA_LIVE_MIRROR_GITEA_WEBHOOK_SECRET` | `live-mirror-gitea-webhook/webhookSecret` | Minted by us (`openssl rand -hex 32`); same value set on the Gitea webhook |
| `STOA_GITEA_ARGOCD_TOKEN` | ArgoCD repo credential | Gitea token scoped to read `agentic-stoa/companies` |

## Manual operations & bring-up ordering

Each becomes a `# manual-operation` block in the plan, synced via
`/sync-runbook`. **The order below is load-bearing** — it exists to avoid
two first-provisioning races: (a) the GitHub→Gitea sync trigger firing
against a not-yet-existing Gitea repo (failed PipelineRun), and (b) the
backfill push spuriously firing the live-mirror trigger into Paperclip
before the chain is meant to be live. The Gitea webhook is therefore wired
**last**, after the mirror is populated.

1. Infisical inserts, including coordinating the CTO secret handoff (comment
   on #444 to request the contact path) — first, so ESO has materialized
   both Secrets before any TaskRun can fire.
2. Create `agentic-stoa/companies` repo in Gitea + stoa-bot push rights
   (Gitea API).
3. One-time backfill push of the repo into the empty mirror; **confirm
   Gitea `main` exists and matches GitHub** before proceeding (the
   `github-pull-sync` pipeline force-pushes a single ref and assumes an
   existing repo).
4. GitHub push webhook on `agentic-stoa/companies` →
   `https://webhooks.hop.derio.net` (secret = existing
   `stoa-github-webhook-secret` value).
5. **Last:** Gitea webhook on the mirror →
   `http://el-live-mirror-sync.tekton-pipelines.svc.cluster.local:8080`
   (secret = minted value). From this point every mirror push fires
   Paperclip — by design.

## Verification (acceptance per #444)

The workflow must be observed end-to-end before the layer extension counts as
Deployed:

1. Test merge to `companies` `main` → GitHub webhook →
   `agentic-stoa-main-sync-*` PipelineRun → Gitea mirror updated.
2. Gitea webhook fires → `live-mirror-sync-*` TaskRun appears. **This is the
   live test of the github-interceptor question** (expected to pass on Gitea
   1.25.4); if the webhook is dropped, capture EventListener pod
   logs/headers and diagnose per Component B before touching the upstream
   manifests.
3. TaskRun logs show `HTTP 202` + run id; a Paperclip run issue appears under
   routine `2f4d361b` carrying the changed-file report.
4. Report the 202/run-issue signal back on #444; Stoa retires the cron.

## Risks / error handling

- **Interceptor verdict** — expected to pass (Findings #2); if not, the
  diagnostic-first fallback in Component B applies. Either way the stale
  repo gotcha gets corrected (Post-deploy).
- **HMAC replay window (300 s)** and `Idempotency-Key: live-mirror-<sha>` are
  handled correctly in the upstream Task; no frank-side action.
- **Runtime `apk add` in the Task** (`wolfi-base:latest` installs
  jq/openssl/curl per run) — works, needs egress; Falco runs on Hop only, so
  no paging. The unpinned `:latest` base tag plus runtime installs are a
  future upstream nicety (digest-pinned image with tools baked in) to
  mention when we next touch the upstream repo — their manifest, not ours
  to fix unilaterally; not blocking.
- **Third-party boundary:** `agentic-stoa` is outside `derio-net` — frank-side
  docs reference only what #444 and the upstream README already state (routine
  id, public trigger id, manifest paths); no Stoa business logic is described.
- **Coverage gap: none** — the cron remains until cutover is confirmed.

## Implementation Plans

| Plan | Repo | Scope | Status |
|------|------|-------|--------|
| 2026-06-04--cicd--stoa-live-mirror-sync | `derio-net/frank` | `2026-06-04--cicd--stoa-live-mirror-sync` | — |

## Post-deploy

Fix/extension workflow: no new blog post; retro-update the Tekton
building/operating posts if the mirror-chain extension warrants a mention.

**Correct the stale gotcha** once the live interceptor verdict is in: scope
the Tekton gotcha "Gitea sends `X-Gitea-Event` (not `X-GitHub-Event`) — use
`cel`, not `github`" in `agents/rules/frank-gotchas.md` +
`docs/runbooks/frank-gotchas/tekton.md` to old Gitea versions / the
HMAC-omitted ClusterIP case — Gitea 1.25.4 demonstrably ships the
GitHub-compat headers. Add any other newly discovered gotchas the same way.
