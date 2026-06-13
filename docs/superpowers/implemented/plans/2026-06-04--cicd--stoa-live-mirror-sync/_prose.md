# Stoa live-mirror-sync trigger — implementation plan

**Spec:** docs/superpowers/specs/2026-06-04--cicd--stoa-live-mirror-sync-trigger-design.md
**Status:** In Progress
**Driver:** [derio-net/frank#444](https://github.com/derio-net/frank/issues/444) (Stoa STO-75 / STO-72)

## What this builds

A merge to `agentic-stoa/companies` `main` fires Paperclip routine `2f4d361b`
push-driven, replacing a daily cron. Chain: GitHub push webhook (existing
`webhooks.hop.derio.net` → `github-listener`) → `github-pull-sync` mirrors
`companies` into Gitea (mirror created in this plan — it did not exist) →
Gitea push webhook → upstream-canonical `live-mirror-sync` EventListener
(ArgoCD-applied from the mirror, SHA-pinned `b61b374d`, never vendored) →
TaskRun that HMAC-signs a POST to Paperclip's internal fire URL (202 =
accepted).

All design decisions, alternatives, and verified findings are in the spec —
read it before executing. Key load-bearing facts re-verified during planning:

- `taskruns` create RBAC already granted to `tekton-triggers-sa` (vendored
  ClusterRole) — no RBAC work in this plan.
- Gitea is 1.25.4 → GitHub-compat webhook headers → the upstream `github`
  interceptor is **expected to work**; the repo gotcha saying otherwise is
  stale and gets corrected in Phase 3.
- Gitea service DNS: `gitea-http.gitea.svc.cluster.local:3000`.
- Stoa-org Infisical keys live under the absolute path `/agentic-stoa/`.

## Phase shape

1. **Frank manifests** (agentic) — argocd-extras app with Frank's first ArgoCD
   repo credential, the pinned `stoa-live-mirror-sync` Application, the
   one-line `agentic-stoa-main-sync` cel-filter extension, two Tekton
   ExternalSecrets, render validation, PR assembly. **The PR is the
   deliverable**; merge gates on Phase 2.
2. **Pre-merge provisioning** (manual) — Infisical inserts (incl. the
   out-of-band CTO HMAC handoff), Gitea mirror repo + stoa-bot push,
   dedicated least-privilege `argocd-reader` Gitea user + token, one-time
   backfill push, GitHub webhook. Ordering is load-bearing (see spec
   "Manual operations & bring-up ordering").
3. **Post-merge cutover + end-to-end test plan** (manual, driven with the
   operator) — sync verification, Gitea webhook wired deliberately LAST,
   test merge through the whole chain to the 202 + Paperclip run issue,
   stale-gotcha correction, acceptance report on #444, closeout.

## Bring-up ordering (why Phase 2/3 step order is non-negotiable)

Two first-provisioning races: (a) the GitHub→Gitea sync trigger firing
against a not-yet-existing Gitea repo (failed PipelineRun); (b) the backfill
push spuriously firing the live-mirror trigger into Paperclip. Hence:
secrets → mirror repo → backfill → GitHub webhook → *merge* → verify →
Gitea webhook last → test merge.

## Hard constraints (from issue #444)

- Never vendor the upstream manifests into frank — the pinned Application
  pulls from the mirror.
- The HMAC secret value never appears in any issue, PR, or chat — Infisical
  only, delivered out-of-band.
- The Paperclip cron stays armed until the end-to-end signal is observed;
  Stoa retires it after the Phase 3 handback.
