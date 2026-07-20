# Full agentic-stoa Mirror + Gitea Actions CI on Frank — Design

**Date:** 2026-07-19
**Layer:** cicd (extension of the stoa-gitea-primary rework)
**Status:** Draft
**Driver:** GitHub Actions minutes on private agentic-stoa repos are too expensive.

## Goal

Every private agentic-stoa repo mirrors to Frank's Gitea, and the CI that today
burns GitHub Actions minutes runs on Frank instead — with results written back
to the originating GitHub PRs so branch protection stays meaningful.

## Operator decisions (batched Q&A, 2026-07-19)

| Decision | Answer |
|---|---|
| CI engine | **Gitea Actions (act_runner)** — near-verbatim workflow reuse; Tekton keeps its current jobs |
| Scope | **Mirror all private repos; keep GitHub Actions enabled** (parallel operation; operator disables GH side later, manually) |
| PR gating | **Status writeback to GitHub** commit statuses |
| Test Plan | **One repo per class** (detailed below) |

### The compatibility question, answered

Tekton's format (Task/Pipeline CRDs) is **not** compatible with GitHub Actions
workflow YAML — every existing per-repo Tekton pipeline in `apps/tekton/` was a
hand translation. **Gitea Actions** is the Actions-compatible engine: same
workflow syntax, `actions/*` resolved from github.com, service containers,
artifacts, and schedules. Direct reuse therefore means Gitea Actions runners on
Frank, not Tekton. Tekton remains what it already is here: the mirror/trigger
layer (github-pull-sync, dual-status, cnc promotion) — those flows are untouched.

## Current state (verified 2026-07-19)

- **Mirrored already (7/11):** hum, content-factory, stoa-blog, companies,
  cnc-fr, cnc-frd, cnc-fru — webhook-driven via `github-pull-sync`
  (GitHub PR → `sync-pr-<N>` branch on Gitea; push-to-main → main sync).
- **Not mirrored:** second-brain, hermes-brain, flexible-health
  (+ paperclip, public — Actions free, stays out of scope).
- **Actions estate (5 repos, 13 workflows):**
  - `second-brain`: tests.yml (python unittest ×2 jobs, push main + PR),
    acceptance-report.yml (fr toolchain; artifact upload; weekly issue upsert)
  - `cnc-fr`: compose-smoke.yml (docker compose + GHCR pulls),
    parity.yml (cross-repo checkout via stoa-fr-automation App token),
    acceptance-report.yml, **pins-update.yml — every 30 min** (~1,500 runs/mo;
    the single largest cost driver; creates PRs via App token)
  - `cnc-frd`: ci.yml (go vet/build/test + postgres service container +
    golangci-lint + docker image-smoke), release.yml (image → GHCR on tag),
    auto-tag.yml (tag + release + image on VERSION change)
  - `cnc-fru`: ci.yml (npm checks + Playwright e2e + docker smoke),
    release.yml (image → GHCR), fixtures-recapture.yml (weekly; postgres;
    App token)
  - `hermes-brain`: backup-restore-tests.yml (BDD suite, push main/feat/fix/chore + PR)
- **Gitea:** chart 12.5.0, live image `docker.gitea.com/gitea:1.25.4-rootless`
  (verified on-cluster) — Actions, schedules, and the `status` webhook event all
  available; Actions **not** enabled yet. Runs on pc-1, sqlite, LB 192.168.55.209.
- **Webhook path:** GitHub → `https://webhooks.hop.derio.net/` → mesh →
  el-github-listener-lb (192.168.55.223). Per-repo webhook creation is an
  established manual op (`cicd-stoa-github-webhook-*`).
- **App token machinery:** `clustergenerator-stoa-github-app.yaml` (ESO
  GithubAccessToken generator for stoa-fr-automation, app-id 3994156) already
  on-cluster; the same App key backs `STOA_APP_PRIVATE_KEY` in the workflows.

## Design

### 1. Complete the mirror set (frank-side, declarative)

Extend `apps/tekton/triggers/eventlistener-github.yaml`:

- Add `second-brain`, `hermes-brain`, `flexible-health` to the
  `agentic-stoa-main-sync` CEL filter (main catch-up sync).
- Add PR-sync triggers (pull_request → `sync-pr-<N>` push) for `second-brain`
  and `hermes-brain` — both have PR-triggered CI. These reuse
  `agentic-stoa-main-sync-template`-style plumbing bound to `github-pull-sync`
  (mirror-only; the CI itself fires Gitea-side on the branch push — no
  per-repo Tekton CI pipeline for these, unlike the Phase-4 repos).
- `flexible-health` has no workflows → main sync only.

Manual ops (per established patterns):
- Gitea repo creation + backfill for the 3 repos (pattern:
  `cicd-stoa-companies-gitea-mirror` / `-backfill`).
- GitHub per-repo webhook for the 3 repos (pattern:
  `cicd-stoa-github-webhook-<repo>`; payload URL `https://webhooks.hop.derio.net/`,
  events: pull_request, push).

### 2. Enable Gitea Actions

`apps/gitea/values.yaml`:

```yaml
config:
  actions:
    ENABLED: true
```

Schedules note: Gitea runs `on: schedule` workflows against the default branch —
after mirroring, that is a synced `main`, so pins-update and the weekly robots
fire on Frank per their cron.

### 3. New app: `apps/gitea-runner/` (act_runner + DinD)

- Deployment on pc-1: `gitea/act_runner` container + `docker:dind` sidecar
  (privileged; DOCKER_HOST over localhost). DinD is required because the
  workflows use docker builds, docker compose, and service containers.
- Namespace `gitea` gains `pod-security.kubernetes.io/enforce: privileged`
  label (or the runner gets its own namespace with that label — decide at
  implementation; own namespace preferred to keep Gitea itself unprivileged).
- Runner config ConfigMap: label map `ubuntu-latest` →
  `gitea/runner-images:ubuntu-latest` (or catthehacker equivalent), capacity 2
  (pc-1 is 32GB and shared with Gitea + Tekton runs + Longhorn).
- Cache PVC (longhorn-cicd) for act_runner's action/tool cache — Playwright
  and setup-go/node downloads are heavy; without cache every run re-downloads.
- Registration: ExternalSecret delivering a runner registration token from
  Infisical (`STOA_GITEA_RUNNER_TOKEN`); minting the token is a manual op
  (`gitea actions generate-runner-token` in the Gitea pod, store in Infisical).
- Resource limits sized so two concurrent jobs cannot starve pc-1
  (requests/limits on both runner and DinD; DinD memory limit is the one that
  matters for compose/Playwright).

### 4. Workflow adaptations (repo-side, 5 repos — small PRs, parallel-safe)

Each of the 5 repos gets one small PR. All changes are no-ops on the GitHub
side so parallel operation is safe:

1. **Trigger:** add `push: branches: ["sync-pr-**"]` to PR-triggered workflows
   (those branches exist only on the Gitea mirror; GitHub never fires them).
2. **Registry/API secrets:** where `secrets.GITHUB_TOKEN` is used against
   github.com/ghcr.io (GHCR login, `gh` CLI), switch to the fallback pattern
   `${{ secrets.STOA_CI_GH_TOKEN || secrets.GITHUB_TOKEN }}` — unset on
   GitHub (falls back to the native token, unchanged behavior), set as a Gitea
   org secret on Frank. Workflows already using `STOA_APP_PRIVATE_KEY` +
   `create-github-app-token` work as-is once the key is a Gitea org secret.
3. **Double-mutation guard:** mutating jobs (pins-update PR creation, auto-tag,
   release image pushes, acceptance-report issue upsert, fixtures-recapture)
   gate on a repo/org **variable** `CI_AUTHORITY` (`github` | `gitea`):
   `if: (vars.CI_AUTHORITY || 'github') == <this side>`, where "this side" is
   derived from `github.server_url`. Default authority stays `github`; the
   operator later flips the variable to move mutation to Frank — no workflow
   edit needed at cutover. Non-mutating test/lint jobs run on both sides.

Gitea org-level secrets/variables (manual op): `STOA_APP_PRIVATE_KEY`,
`STOA_CI_GH_TOKEN` (GHCR-capable GitHub token), `CI_AUTHORITY=github`.

### 5. Status writeback to GitHub

Primary: **central bridge, zero per-workflow steps.** Gitea Actions sets commit
statuses on the mirror; Gitea (1.23+) emits a `status` webhook event. A new
trigger on an EventListener receives it and runs the existing
`github-status` task to post the same sha/state/context to GitHub — the sha is
identical on both sides by construction, so mapping is trivial. Context prefix
`gitea-actions/<workflow>` distinguishes Frank results from native GH checks.

Fallback (if 1.24's status webhook proves unusable at implementation time): a
final writeback step appended per workflow, using the App token. The spec
prefers the bridge; the plan must verify the webhook event early and pick.

Bridge filters: restrict to the agentic-stoa org, and drop statuses written by
Tekton's own `gitea-status` task (the Phase-4 dual-status pipelines post to
Gitea too) so Tekton results aren't re-forwarded to GitHub, which already gets
them directly from `github-status`. There is no feedback loop by construction:
the bridge listens on Gitea and posts only to GitHub.

### 6. What does NOT change

- GitHub Actions stays enabled everywhere (operator's call; parallel running).
- Existing per-repo Tekton CI pipelines (hum, content-factory, stoa-blog,
  cnc-*) keep running — retiring them in favor of Gitea Actions is a separate,
  later decision.
- cnc promotion (`repository_dispatch` → Tekton) stays GitHub-authoritative
  until `CI_AUTHORITY` flips.
- paperclip stays unmirrored (public).

## Cost model

pins-update alone is ~1,500 private-repo runs/month on GitHub. With
`CI_AUTHORITY=github` nothing is saved yet by design (operator chose parallel
first); the savings materialize when the operator disables Actions per repo /
flips authority — at that point all 13 workflows' minutes go to zero on GitHub.
The Frank-side capacity cost is bounded by runner capacity 2 on pc-1.

## Deliverables

- **frank (this repo, one PR):** eventlistener triggers for 3 new mirrors,
  `apps/gitea/values.yaml` Actions enable, `apps/gitea-runner/` app +
  root Application CR, status-bridge trigger + task wiring, manual-op blocks,
  runbook sync.
- **agentic-stoa ×5 (dispatched, one small PR each):** trigger additions,
  secret fallback swaps, `CI_AUTHORITY` guards. Repo names and workflow
  filenames only in this spec — no business logic detail (third-party privacy).

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|-------------|------|--------|
| 2026-07-19-cicd-stoa-mirror-gitea-actions | `derio-net/frank` | `2026-07-19-cicd-stoa-mirror-gitea-actions` | — |

## Test Plan (post-merge, operator-driven — one repo per class)

1. **PR class (Go + service container):** open a test PR in cnc-frd → watch the
   run on Frank's Gitea (`sync-pr-<N>`), postgres service comes up, tests pass →
   commit status appears on the GitHub PR sha with `gitea-actions/` context.
2. **Schedule class:** observe pins-update fire on Frank at its next half-hour
   tick; with `CI_AUTHORITY=github` confirm it runs check-only (no PR created
   from Frank).
3. **Artifact class:** trigger acceptance-report (workflow_dispatch) on
   second-brain's mirror → artifact uploaded and downloadable from Gitea.
4. **Steady state:** after a week of parallel green, operator decides per-repo
   GH Actions disable / authority flip (out of this plan's scope).

## Risks

- **DinD privileged pod** on pc-1: contained to a dedicated namespace, pinned
  to the Edge node, no cluster credentials mounted; accepted for a homelab CI.
- **Parallel mutation:** guarded by `CI_AUTHORITY` (default github). The guard
  is the load-bearing piece — reviewed per workflow in the repo-side PRs.
- **pc-1 capacity:** capacity 2 + limits; Playwright/compose are the heavy
  cases. If pc-1 strains, capacity drops to 1 before any node move.
- **Gitea 1.24 feature reality** (schedule semantics, status webhook event,
  artifact API): verified as the plan's first implementation step; status
  writeback has a designed fallback.
- **second-brain acceptance-report installs fr from derio-net/super-fr** —
  if that repo is private to the runner's network position, the job needs a
  token; checked during implementation.
