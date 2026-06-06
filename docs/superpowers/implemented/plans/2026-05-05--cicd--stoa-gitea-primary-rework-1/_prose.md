# Stoa Org Gitea-Primary Implementation Plan — Rework 1: GitHub-primary

**Spec:** `docs/superpowers/specs/2026-05-04--cicd--stoa-gitea-primary-design.md` (amended 2026-05-13 with `## Architectural Constraint`, `## Direction Inversion`, `## Active Architecture`, `## Active Sync Model`, `## Active Pipelines`, `## Active Org & Auth` sections describing the inverted direction)
**Parent plan:** `docs/superpowers/archived-plans/2026-05-05--cicd--stoa-gitea-primary/` (Complete; substrate from Phases 0–2 reused; Phases 3–4 marked skipped with supersedence note)

## Why this rework exists

Discovered 2026-05-13 during Phase 3 of the parent plan: **Paperclip AI does not support any non-GitHub git remote for repository management.** Paperclip-driven agents need a GitHub PR surface to do their job — opening PRs, commenting, reading issues. The original plan's Gitea-primary direction (where Gitea was the PR surface and GitHub was a backup) made Paperclip-driven workflows impossible.

This rework inverts the direction: GitHub is the source of truth and the PR surface; Gitea becomes a CI replica that runs Tekton on PR-head commits and reports status back to the GitHub PR. The same Gitea/Tekton substrate is reused.

## What survives, what's scrapped (from parent plan)

**Reused as-is** (shipped by parent Phases 0–2):
- `agentic-stoa` Gitea org + `stoa-bot` user (admin on `agentic-stoa/*`)
- The 3 repos on Gitea: `hum`, `content-factory`, `stoa-blog` (initial state already mirror-cloned from GitHub during parent Phase 3 — now this is the **initial state of Gitea as a replica**)
- `apps/tekton/manifests/externalsecret-stoa-github-mirror.yaml` (PAT-loading ESO; PAT scope unchanged at `repo`)
- `apps/tekton/manifests/triggers-rbac.yaml` (generic Tekton-Triggers RBAC; reused by the new EventListener)
- The CI body of `hum-ci.yaml` and `content-factory-ci.yaml` (pipelines kept; only triggers + final status post change)

**Scrapped at Phase 0 of this rework** (direction inverted):
- `apps/tekton/pipelines/github-backup-sync.yaml` (Gitea→GitHub direction no longer needed)
- `agentic-stoa-backup` Trigger and `agentic-stoa-backup-template` TriggerTemplate in `apps/tekton/triggers/eventlistener.yaml`
- The parent plan's Phase 3 Task 7 (Gitea branch protection — moot when Gitea is a replica that only Tekton writes to)

**New artifacts** (built by this rework):
- New Caddy route on Hop: `webhooks.hop.derio.net` → Tailscale-mesh → Frank's github-listener
- `apps/tekton/triggers/eventlistener-github.yaml` (new EventListener — `github` interceptor, ClusterIP)
- `apps/tekton/tasks/github-status.yaml` (POST GitHub Commit Status API)
- `apps/tekton/pipelines/github-pull-sync.yaml` (fetch from GitHub, push to Gitea)
- `apps/tekton/pipelines/stoa-blog-ci.yaml` (3rd repo, not in the parent plan)
- `STOA_GITHUB_WEBHOOK_SECRET` Infisical key (HMAC shared secret between GitHub webhook and Caddy validator)

## Phase outline

| Phase | Tag | Title |
|---|---|---|
| 0 | manual+agentic | Decommission scrap items + Infisical secret prep |
| 1 | agentic | Caddy-on-Hop webhook relay |
| 2 | agentic | github-listener EventListener in Frank |
| 3 | agentic | github-status Task + github-pull-sync Pipeline |
| 4 | agentic | Wire per-repo CI to GitHub triggers (rework hum-ci, content-factory-ci; add stoa-blog-ci); dual-status post in `finally` |
| 5 | agentic | Main-branch sync pipeline (post-merge GitHub→Gitea) |
| 6 | manual | Bootstrap GitHub webhooks on each of the 3 repos |
| 7 | manual | End-to-end smoke (PR→pull→CI→status→merge→main-sync) |
| 8 | manual | Post-Deploy Checklist (operating post update — extension of layer 19) |

Phase dependencies are linear (each phase depends on the previous); Phase 4 depends on Phase 2 + Phase 3 (the EventListener + the new artifacts).

## Anti-drift dual-status guarantee

Per spec `## Active Sync Model (2026-05-13)`:

- Both `github-status` and `gitea-status` posts run inside the per-repo CI pipeline's single `finally` block (one outcome computation, no possibility of disagreeing on success/failure).
- Both use the same `context` string (`tekton/ci`).
- Both refer to the same commit SHA (git's content-addressing ensures GitHub and Gitea hold byte-identical commits for the same content; pull-sync transports the SHA verbatim).
- `github-status` is mandatory (failure of the post fails the pipeline). `gitea-status` is best-effort (failure does not fail the pipeline; provides Gitea-side visibility for operators browsing Gitea PRs).
- Failure mode: if Gitea API is transient-down, GitHub stays correct; Gitea may show a stale state until the next CI run.

## Notes for the executor

- **No changes outside Frank + Hop + Cloudflare + GitHub.** This rework touches: Frank cluster (new manifests + a few rewrites), Hop cluster (one Caddy route), Cloudflare DNS (one A record), GitHub (3 webhook configs in the agentic-stoa org's repos).
- **Infisical is the only secret store.** New keys land in the `/agentic-stoa` Infisical project per the parent plan's pattern.
- **Don't touch the 3 mirrored Gitea repos.** They're the replica destination; `git push` to them only ever happens via Tekton's pull-sync. Operator should not push to them directly (which is enforced socially, not by branch protection — that was the parent plan's Phase 3 Task 7, scrapped).
- **Status posting requires GitHub PAT scope `repo:status`.** The `STOA_GITHUB_TOKEN` (renamed from `STOA_GITHUB_MIRROR_TOKEN` in Phase 0) needs `repo` scope (gives both fetch read and status write).
- **Caddy validates webhook HMAC before forwarding.** Shared secret with GitHub's webhook config. Rejects unsigned/wrong-sig at L7. Frank's EventListener never sees an unvalidated request.
