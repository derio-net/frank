# CI/CD: Stoa Org GitHub-Primary (was Gitea-Primary) — Design

**Date:** 2026-05-04 (original design); inverted 2026-05-13
**Status:** Design — direction inverted; active design is the GitHub-primary sections below
**Layer:** cicd (19) — extension

> **READ THIS FIRST.** This spec was authored on 2026-05-04 with a Gitea-primary, GitHub-backup direction. On 2026-05-13 the direction was inverted to GitHub-primary, Gitea-as-CI-replica (see `## Architectural Constraint` and `## Direction Inversion` sections immediately below). The original Gitea-primary content is preserved verbatim from `## Goals` onward as historical context for the original design's investigation work (e.g. "Why not Gitea push-mirror"). The **active** architecture, sync model, and pipelines are described in `## Active Architecture (2026-05-13)`, `## Active Sync Model (2026-05-13)`, and `## Active Pipelines (2026-05-13)` further down. Where the active sections supersede an original section, a pointer is left in place.

## Overview (original)

Onboard the `agentic-stoa` org's repos onto Frank's existing CI/CD platform (Gitea + Tekton + Zot from layer 19) with a **Gitea-primary, GitHub-backup** sync model. Two repos in scope today: `hum` and `content-factory`. The pattern is reusable for any future repo in the org.

This is the **inverse direction** of how `derio-net/frank` itself uses Gitea. `frank` is a public infra repo: GitHub-primary, Gitea pull-mirrors as a CI cache. `agentic-stoa/*` repos are private business-side code: Gitea-primary, GitHub push-mirrors as offsite backup. Both directions live on the same Gitea/Tekton stack — only the per-repo mirror configuration differs.

## Architectural Constraint: Paperclip AI requires GitHub-primary

Discovered 2026-05-13 during execution of Phase 3 of the original plan: **Paperclip AI does not support any non-GitHub git remote for repository management.** Agents driven by Paperclip can only open PRs against GitHub repos, comment on GitHub PRs, and read GitHub issues. This invalidates the original design's premise that `agentic-stoa` repos could live Gitea-primary and offer a meaningful workflow to Paperclip-driven agents — those agents would have no UX for the PR cycle they are supposed to drive.

The constraint forces direction inversion: GitHub becomes the source of truth and the PR surface; Gitea becomes a CI replica that runs Tekton on PR-head commits and reports status back to the GitHub PR. The same Gitea/Tekton substrate is reused, but the data flow reverses.

## Direction Inversion (2026-05-13)

The original plan (`docs/superpowers/archived-plans/2026-05-05--cicd--stoa-gitea-primary/`) drove Phases 0–2 to completion (org + bot + Gitea repos created on Gitea side; per-repo CI Pipeline manifests + the Gitea-listener triggers committed; the github-backup-sync Pipeline shipped). Phase 3 (migration of `hum` + `content-factory`) was partially done — the operator had successfully mirror-pushed `hum`, `content-factory`, and `stoa-blog` from GitHub into Gitea — when the Paperclip constraint surfaced.

After the inversion the mirror-cloned Gitea-side state remains useful: it is now the **initial state of Gitea as a replica**. The substrate (org, bot, repos, CI-pipeline manifests, Gitea-listener Triggers, ESO-loaded GitHub PAT Secret) is largely reusable; the pieces that flow the wrong way (`github-backup-sync` Pipeline, the `agentic-stoa-backup` Trigger and TriggerTemplate, the Phase-3 Gitea branch-protection step) get scrapped.

Active design follows in `## Active Architecture (2026-05-13)` below. The original `## Architecture`, `## Sync Model`, and `### Shared github-backup-sync Pipeline` sections are kept verbatim for context — see `## Original Architecture`, `## Original Sync Model`, and `### Original Shared github-backup-sync Pipeline` (renamed from the un-prefixed forms) further down.

The active implementation landed in the rework plan, now archived: `docs/superpowers/archived-plans/2026-05-05--cicd--stoa-gitea-primary-rework-1/` (Complete 2026-05-14).

## Active Architecture (2026-05-13)

```
                       github.com/agentic-stoa/<repo>             ◄── source of truth
                          │                ▲
                          │ PR webhook     │ POST /repos/.../statuses/<sha>
                          ▼                │ (github-status task, Commit Status API)
              ┌───────── Hop ──────────┐   │
              │ Caddy (public TLS)     │   │
              │ webhooks.hop.derio.net │   │
              │ HMAC validates body    │   │
              │ → Tailscale mesh       │   │
              └────────────┬───────────┘   │
                           │               │
              ┌─────────── Frank cluster ──────────────────────────┐
              │            │                                       │
              │            ▼                                       │
              │   el-github-listener.tekton-pipelines.svc:8080    │
              │            │                                       │
              │            ├──► PR-event Trigger (per-repo)        │
              │            │      → github-pull-sync PipelineRun:  │
              │            │         git fetch <PR-head> from GH   │
              │            │         git push refs/pull/N/head     │
              │            │         into Gitea                    │
              │            │      → fires the per-repo CI Pipeline │
              │            │         on the Gitea-replica ref:     │
              │            │         clone (Gitea) → tests →       │
              │            │         finally: github-status (GH)   │
              │            │                  + gitea-status (GH)  │
              │            │                                       │
              │            └──► push-to-main Trigger               │
              │                   → github-pull-sync (main):       │
              │                      pulls main from GH → Gitea    │
              │                                                    │
              └────────────────────────────────────────────────────┘

         Gitea: agentic-stoa/<repo> on 192.168.55.209:2222
         (replica — only Tekton ever pushes to it; operator
          and Paperclip never push to Gitea directly)
```

## Active Sync Model (2026-05-13)

**Direction:** GitHub → Gitea, one-way (replica). Operator and Paperclip push to GitHub only. Tekton pulls into Gitea on (a) GitHub PR webhook events, (b) GitHub `push` to main webhook events. Tekton CI runs on the Gitea-side ref. Status posts back to the GitHub PR via the Commit Status API.

**Webhook ingress.** GitHub webhooks reach Frank via Caddy on Hop:
- A new Caddy route on Hop listens at `webhooks.hop.derio.net` (Cloudflare DNS A-record → Hop public IP) over HTTPS.
- Caddy validates the GitHub `X-Hub-Signature-256` HMAC against a shared secret before forwarding (rejects unsigned/wrong-sig at L7 with 403).
- Validated requests are reverse-proxied over the Tailscale mesh to `el-github-listener.tekton-pipelines.svc.cluster.local:8080` on Frank.
- Frank's `github-listener` EventListener is internal-only (ClusterIP); never publicly reachable.

**Two pipeline shapes:**

1. **`github-pull-sync`.** Triggered by PR webhook (`pull_request` opened/synchronized) AND by push-to-main webhook. Parameters: `repo`, `ref`, `sha`. Body:
   - Fetch `<sha>` from GitHub using `STOA_GITHUB_TOKEN` (PAT scope: `repo`).
   - Push as `refs/pull/<N>/head` (PR case) or `refs/heads/main` (push-to-main case) into Gitea, using `stoa-bot` SSH key.
   - For the PR case, fire the per-repo CI Pipeline against the new Gitea ref.

2. **Per-repo CI** (`hum-ci`, `content-factory-ci`, `stoa-blog-ci`). Trigger source flips from `gitea-listener` (original) to `github-listener` (rework). Body unchanged in concept (clone → test → build → push artifacts → ...). The `finally` block adds two status posts:
   - **`github-status`** — `POST repos/agentic-stoa/<repo>/statuses/<sha>` with state `success`/`failure`/`error`/`pending`, context `tekton/ci`, target_url to the Tekton dashboard PipelineRun page. Mandatory; failure of this post fails the pipeline. PAT scope: `repo:status` (a subset of `repo`; the same `STOA_GITHUB_TOKEN` works).
   - **`gitea-status`** — same payload shape, posted to Gitea. Best-effort; failure does not fail the pipeline. Provides Gitea-side visibility for operators browsing Gitea PRs.

**Anti-drift guarantee for dual-status.** Both posts run inside the pipeline's single `finally` block, sharing one outcome computation. They use the same `context` string (`tekton/ci`) and refer to the same commit SHA (git's content-addressing means GitHub and Gitea hold byte-identical commits for the same content). If one API is transient-down, GitHub's post is the mandatory one — Gitea-side may show a stale state until the next CI run, but GitHub stays correct.

**Why not Gitea built-in mirror (polling)?** PR refs (`refs/pull/N/head`) aren't part of Gitea's mirror set, and polling adds 5+ minutes of latency to PR feedback. Webhook-driven pull-sync is the correct shape for PR-driven CI.

**Tag/branch deletion.** Out-of-scope until a use case appears. Pull-sync only ever creates/updates refs; never deletes.

## Active Pipelines (2026-05-13)

Replaces `## Pipelines` below. The Per-Repo CI Pipeline shape is preserved from the original spec; only the trigger source and the status-post step change. The shared `github-backup-sync` Pipeline is removed (Gitea→GitHub direction is no longer needed); a new shared `github-pull-sync` Pipeline takes its place but flows the opposite direction.

See the rework plan's phase content for manifest-level detail.

## Active Org & Auth (2026-05-13)

Mostly unchanged from original `## Org & Auth`. Key deltas:

- **`stoa-bot` Gitea user**: still exists, still has write access to `agentic-stoa/*` on Gitea. But its push role is now used by Tekton's `github-pull-sync` pipeline pushing INTO Gitea (not by `github-backup-sync` pushing OUT to GitHub). Operator and Paperclip never use `stoa-bot` for git operations now — those go to GitHub via the operator's normal credentials.
- **`STOA_GITHUB_MIRROR_TOKEN` Infisical key**: the name is now slightly misleading (no longer "mirror to GitHub"). Renaming to `STOA_GITHUB_TOKEN` is a Phase-0 task in the rework. PAT scope tightens — original needed `repo` (write) for backup-push; rework needs `repo` for fetch + `repo:status` for status writes (still satisfied by full `repo` scope; could downgrade later if we split into two PATs).
- **GitHub webhook secret** (`STOA_GITHUB_WEBHOOK_SECRET`): new Infisical key, shared between GitHub's webhook config and Caddy's HMAC validator on Hop.

## Goals

## Goals

- Develop, branch, PR, and run CI entirely on Frank for `agentic-stoa` repos
- GitHub holds a code-only backup (`main` + tags), not part of any active workflow
- Establish a reusable pattern (org + bot account + Tekton CI pipeline + Tekton backup-sync pipeline + webhook + branch protection) for future repos
- Reuse the layer-19 platform — no new infrastructure components

## Non-Goals

- Migrating issues, PRs, projects, or wikis from GitHub (Gitea starts fresh; the one open issue on `hum` is being closed manually)
- Image build + Zot push in MVP pipelines (deferred until a repo actually ships a container)
- Deploy steps inside pipelines (n8n workflow deploy, Supabase migrations, mobile builds) — manual for now
- "Future-public" inversion — flipping a repo back to GitHub-primary if it ever goes public is out of scope and will be designed when the first repo flips
- GitHub-side branch protection — honor system, mirror PAT is the only writer

## Original Architecture

> **Superseded** by `## Active Architecture (2026-05-13)` above. Kept for context.

```
            ┌───── Frank cluster ────────────────────────────────────┐
            │                                                        │
 dev pushes │   agentic-stoa/<repo> on Gitea                         │
   over SSH ├──►(192.168.55.209:2222 via Tailscale)                  │
  (humans + │     │                                                  │
   Paperclip│     │ on push / PR: Gitea webhook                      │
   agents)  │     ▼                                                  │
            │   el-gitea-listener.tekton-pipelines.svc:8080          │
            │     │                                                  │
            │     ├──► CI Trigger (per-repo)                         │
            │     │      → PipelineRun on pc-1:                      │
            │     │         git-clone → run-tests → gitea-status     │
            │     │      (reports commit status to Gitea PR)         │
            │     │                                                  │
            │     └──► github-backup-sync Trigger                    │
            │            filter: agentic-stoa/* AND                  │
            │                    (refs/heads/main || refs/tags/*)    │
            │            → PipelineRun on pc-1:                      │
            │               git-clone (Gitea) → push main+tags       │
            │               (uses STOA_GITHUB_MIRROR_TOKEN over HTTPS)│
            │                            │                           │
            └────────────────────────────┼───────────────────────────┘
                                         │
                                         ▼
                        github.com/agentic-stoa/<repo>
                            (private, main + tags only;
                             nothing else ever reaches GitHub)
```

## Original Sync Model

> **Superseded** by `## Active Sync Model (2026-05-13)` above. Kept because the "Why not Gitea native push-mirror" investigation below documents constraints that are still relevant in the active design (Gitea push-mirror is unsuitable in either direction; webhook-driven pipelines are the correct shape).

**Direction:** Gitea → GitHub, one-way. Nothing pulls from GitHub. PRs and issues live exclusively on Gitea (they are not git refs and wouldn't propagate via mirror anyway; acceptable since Gitea state is on Longhorn-backed PVC with R2 backup).

**Why not Gitea's native push-mirror?** Verified against the Gitea changelog and docs (running 1.25.4, latest 1.26.x): Gitea's push-mirror has three limitations that would force compromise:
- No **branch filter** — pushes all branches or none, no in-between
- No **SSH/deploy-key auth** — HTTPS PAT only (open feature request)
- No **org-level config** — must be configured per-repo

Since "only `main` reaches GitHub" is a hard requirement, native push-mirror is the wrong tool for steady state. We use it not at all.

**Two-phase mechanism:**

1. **Migration phase (one-shot, per repo).** Run `git clone --mirror` from a workstation against the existing GitHub repo, then `git push --mirror` to the new empty Gitea repo. This seeds Gitea with every branch and tag GitHub already has — no Gitea-side configuration involved. After verification, prune non-`main` branches on the GitHub side via `gh` CLI.

2. **Steady state.** A Tekton **github-backup-sync** pipeline lives in `apps/tekton/pipelines/github-backup-sync.yaml`. A repo-scoped Trigger on `el-gitea-listener` fires it whenever a push event hits `agentic-stoa/<repo>` on `refs/heads/main` or any `refs/tags/*`. The pipeline clones from Gitea, force-pushes `main` + tags to `github.com/agentic-stoa/<repo>` using `STOA_GITHUB_MIRROR_TOKEN` over HTTPS. Other branches (`vk/*`, agent feature branches, etc.) emit Gitea push events but the trigger filters them out, so they never touch GitHub.

This is more declarative than Gitea's UI-configured push-mirror anyway — the sync mechanism lives in this repo as YAML, version-controlled, and the same one pipeline serves every `agentic-stoa/*` repo (parameterized).

**What propagates:** every commit on `main`, all tags. **What doesn't:** other branches, issues, PRs, comments, releases, wikis, webhook deliveries, runner state.

**Tag deletion edge case:** the trigger fires on tag *create* (push to `refs/tags/*`); `git push --tags` only adds. If a tag is deleted in Gitea, GitHub keeps it. Acceptable for backup semantics — tags are append-only in practice. If we ever need delete-propagation, the pipeline can switch to `git push --mirror --prune github main 'refs/tags/*'` (with the trigger filter still gating non-main branches).

## Original Org & Auth

> **Superseded in deltas** by `## Active Org & Auth (2026-05-13)` above. The bulk of this section's `agentic-stoa` org and `stoa-bot` user setup remains accurate; only the direction-of-use of those credentials has flipped.

**Gitea org:** Create `agentic-stoa` (matches GitHub org name for symmetry). Owner: the operator's Authentik-mapped Gitea account.

**Service account:** `stoa-bot` (Gitea-local user, member of `agentic-stoa` org with **write access** on all repos). Paperclip agents identify as `stoa-bot` for all git operations: cloning, branch creation, commits, push, and PR open/comment via Gitea API. `tekton-bot` retains its existing role of writing commit statuses from inside pipelines (separate concern, separate token).

**Branch protection on `main` (Gitea-side):** Each `agentic-stoa/*` repo gets a branch protection rule on `main`:
- Direct push to `main` is **blocked** for everyone except the operator's account (used for break-glass).
- Merge to `main` requires a PR with at least one approving review from the operator. `stoa-bot` cannot self-approve or merge its own PRs.
- Required status checks: `tekton/ci` (the per-repo pipeline must pass green).

This means `stoa-bot` can push branches and open PRs freely, but landing code on `main` always passes through operator review. Auto-merge-on-green is not enabled in MVP — Gitea supports it as a per-PR opt-in (operator can flip a PR into auto-merge mode); revisit as a default once the loop is proven trustworthy. Role-level permissions (e.g., "agent X can auto-merge to main on these paths") are out of scope.

**Tokens:**
- `stoa-bot` Gitea API token → Infisical key `STOA_GITEA_TOKEN`. Projected into Paperclip agent envs via ESO ExternalSecret. Scopes: `write:repository`, `write:issue`, `read:organization`. **TTL: no expiry** (Gitea allows this). Long TTL is acceptable here because the token is scoped to a single bot user with no `admin` rights and revocable instantly via Gitea UI.
- `tekton-bot` already has `GITEA_API_TOKEN` for status writes — extend its org membership to include `agentic-stoa` (org-write team) so commit statuses can post on `agentic-stoa/*` PRs.

**SSH access for humans:** the operator adds their SSH public key to their personal Gitea account (one-time UI step). Clone URL: `git@gitea.cluster.derio.net:agentic-stoa/<repo>.git` (resolves via mesh DNS over Tailscale to 192.168.55.209:2222 — Gitea's default SSH port). HTTPS clone via `https://gitea.cluster.derio.net/agentic-stoa/<repo>.git` is supported but SSH is preferred (no token rotation).

**GitHub-side credentials:** A single GitHub fine-grained PAT scoped to the `agentic-stoa` org with `Contents: read+write` and `Metadata: read` on every `agentic-stoa/*` repo (selection updated when new repos are added). Stored in Infisical as `STOA_GITHUB_MIRROR_TOKEN`. Used by the Tekton `github-backup-sync` pipeline (mounted via ExternalSecret). **TTL: GitHub fine-grained PATs cap at 1 year** — this is the rotation pain point. MVP accepts annual manual rotation; an automated rotator (Tekton CronJob that uses GitHub's PAT-rotate API and updates the Infisical secret) is captured in Open Items.

## Original Pipelines

> **Per-Repo CI** is preserved in concept (CI body unchanged); trigger source flips and a `github-status` step is added in the rework. **Shared github-backup-sync** is scrapped in the rework (direction inverted; see `## Active Pipelines (2026-05-13)` above).

Two kinds of pipelines run for `agentic-stoa/*` repos. Both reuse the existing `el-gitea-listener` EventListener and `gitea-push-binding` TriggerBinding from layer 19 — no new EventListener.

### Per-Repo CI Pipeline (MVP)

Fires on every push and PR event for the repo. Reports commit status back to the Gitea PR.

**Shape (3 tasks):**
1. `git-clone` — Tekton catalog task (vendored already)
2. `run-tests` — repo-specific (template below)
3. `gitea-status` — `finally` block, commit status → Gitea PR (existing task, reused as-is)

**`hum` pipeline:**
- Image: `node:22-alpine` (matches likely engines field in `package.json`; verify during plan phase)
- Steps: `npm ci` → `npm run typecheck` (if script defined) → `npm test` (if script defined)
- Workspaces affected: root, `backend/`, `shared/` (each has own `package.json`). Pipeline runs `npm ci` per workspace, tests where available. Final design may use `npm workspaces` if `hum` is set up that way — verify during plan.
- No image build, no deploy.

**`content-factory` pipeline:**
- Image: `python:3.13-slim` (verify against `requirements.txt` / `pytest.ini` constraints)
- Steps: `pip install -r requirements.txt` → `pytest`
- No n8n workflow validation in MVP (would need a JSON schema check; deferred)
- No deploy.

The repo-scoped Trigger pattern (a `Trigger` resource bound to the existing EventListener that filters on `body.repository.full_name == "agentic-stoa/<repo>"`) lets each repo evolve its CI pipeline independently without touching the shared EventListener.

### Original Shared `github-backup-sync` Pipeline (scrapped in rework)

One pipeline definition, used by every `agentic-stoa/*` repo. Replaces what Gitea's native push-mirror would have done.

**Trigger filter (CEL):** `body.repository.full_name.startsWith("agentic-stoa/") && (body.ref == "refs/heads/main" || body.ref.startsWith("refs/tags/"))`

**Shape:**
1. `git-clone` from Gitea (`agentic-stoa/<repo>`, all refs, full history — `--mirror` semantics)
2. `push-to-github` step: configures a `github` remote at `https://oauth2:${STOA_GITHUB_MIRROR_TOKEN}@github.com/agentic-stoa/<repo>.git`, runs `git push --force github main` followed by `git push github --tags`. Uses `--force` because in rare merge-rebase cases Gitea's `main` may have rewritten history, and the GitHub mirror is downstream-only.

**Why one pipeline, not per-repo:** the only thing that varies between repos is the URL pair (Gitea source, GitHub destination), which can be derived from `body.repository.full_name`. The Trigger params extract repo name; the Pipeline params take it. Adding a new repo means: add a webhook + (no new pipeline manifest needed for the backup side).

**Pipeline files:**
```
apps/tekton/pipelines/
  hum.yaml                   # CI Pipeline + repo-scoped Trigger
  content-factory.yaml       # CI Pipeline + repo-scoped Trigger
  github-backup-sync.yaml    # Shared Pipeline + org-scoped Trigger
  externalsecret-stoa-github-mirror.yaml  # ESO → STOA_GITHUB_MIRROR_TOKEN
```

## Secrets

All stoa-org secrets live under the `/agentic-stoa` folder in Infisical (prod env), separated from frank infra secrets which stay at `/`. The shared `infisical` ClusterSecretStore is scoped to `secretsPath: /`, so each `agentic-stoa/*` ExternalSecret references its key by absolute path (`/agentic-stoa/STOA_*`); ESO's Infisical provider supports cross-path lookups when the `key` is an absolute path. Future stoa secrets follow the same convention — never put stoa-scoped material at the root.

| Secret | Source (Infisical path) | Type | Used by | When created |
|---|---|---|---|---|
| `STOA_GITHUB_MIRROR_TOKEN` | Infisical `/agentic-stoa/` | GitHub fine-grained PAT (Contents R/W on `agentic-stoa/*`) | Tekton `github-backup-sync` pipeline | Before steady-state cutover |
| `STOA_GITEA_TOKEN` | Infisical `/agentic-stoa/` | Gitea API token (`stoa-bot`, write scope on `agentic-stoa`) | Paperclip agents (clone, push, PR ops) | After `stoa-bot` user created in Gitea |
| `GITEA_API_TOKEN` | Infisical `/` (existing) | Gitea API token (`tekton-bot`, write scope) | Tekton `gitea-status` task | Already exists; org membership extended |
| `GITEA_WEBHOOK_SECRET` | Infisical `/` (existing) | Random string | EventListener CEL interceptor + Gitea webhook | Already exists; reused |

Both new entries get ExternalSecret CRs (with `remoteRef.key` set to the absolute path, e.g. `/agentic-stoa/STOA_GITHUB_MIRROR_TOKEN`):
- `STOA_GITEA_TOKEN` projected into the Paperclip namespace where agent pods consume it
- `STOA_GITHUB_MIRROR_TOKEN` projected into `tekton-pipelines` namespace as Secret `stoa-github-mirror`, mounted into the `github-backup-sync` pipeline as a `secretEnv`. Single source of truth, no UI paste.

## Original Migration Sequence (per repo, runs for both `hum` and `content-factory` in parallel)

> **Superseded** by the rework's Phase 6 (GitHub webhook bootstrap) + Phase 7 (end-to-end smoke). Phase 3 of the original plan partially executed this sequence (mirror-clone of `hum`, `content-factory`, `stoa-blog` from GitHub to Gitea), and that mirror-cloned state is now the **initial state of Gitea as a replica** in the rework. The remaining Phase 3 steps (Gitea webhook setup, branch protection on Gitea, etc.) are scrapped.

**Prerequisite (operator):** push all outstanding local work to current GitHub remotes. The migration starts with `git clone --mirror` from GitHub, so anything not on GitHub at that moment is lost.

1. **Gitea org + bot setup (one-time, both repos share):**
   - Create `agentic-stoa` org in Gitea (UI)
   - Create `stoa-bot` user in Gitea, add to org with Write team membership (UI)
   - Generate API token for `stoa-bot`, store in Infisical under `/agentic-stoa/` as `STOA_GITEA_TOKEN` (create the folder via Secrets → Add Folder if absent)
   - Verify `tekton-bot` has org membership with status-write permission

2. **GitHub PAT (one-time):**
   - Create fine-grained PAT in GitHub UI (`agentic-stoa` org, both repos selected, `Contents: R/W`)
   - Store in Infisical under `/agentic-stoa/` as `STOA_GITHUB_MIRROR_TOKEN`

3. **Shared Tekton infrastructure (one-time):**
   - Drop `github-backup-sync.yaml` (Pipeline + org-scoped Trigger filtered on `agentic-stoa/*` + main/tags) at `apps/tekton/pipelines/`
   - Drop `externalsecret-stoa-github-mirror.yaml` projecting `STOA_GITHUB_MIRROR_TOKEN` into `tekton-pipelines` namespace
   - Commit + push to `frank` repo. ArgoCD `tekton-extras` syncs. Verify Trigger and Secret are healthy in Tekton Dashboard before proceeding.

4. **Per-repo migration (parallelizable):**

   a. Create empty repo in Gitea: `agentic-stoa/<repo>` (UI, default branch `main`, no README/license — needs to be empty for the mirror push)

   b. From a workstation:
      ```bash
      git clone --mirror https://github.com/agentic-stoa/<repo>.git /tmp/<repo>.git
      cd /tmp/<repo>.git
      git remote set-url --push origin git@gitea.cluster.derio.net:agentic-stoa/<repo>.git
      git push --mirror
      rm -rf /tmp/<repo>.git
      ```
      Verify in Gitea UI: all branches and tags present.

   c. Drop CI pipeline manifest at `apps/tekton/pipelines/<repo>.yaml` (Pipeline CR + repo-scoped Trigger). Commit + push to `frank` repo. ArgoCD `tekton-extras` syncs.

   d. Add Tekton webhook (Gitea UI: repo → Settings → Webhooks → Add → Gitea). One webhook serves both the per-repo CI Trigger and the shared `github-backup-sync` Trigger:
      - URL: `http://el-gitea-listener.tekton-pipelines.svc.cluster.local:8080`
      - Secret: `GITEA_WEBHOOK_SECRET` value
      - Events: Push, Pull Request

   e. Smoke test CI: push a commit to a feature branch in Gitea, confirm Tekton Dashboard shows the per-repo CI PipelineRun and Gitea PR view shows commit status.

   f. Smoke test backup: push a commit to `main` (small README touch is fine). Confirm a `github-backup-sync` PipelineRun fires within ~10s and the commit appears on `github.com/agentic-stoa/<repo>`. Confirm a feature-branch push does NOT trigger backup-sync.

   g. Prune non-`main` from GitHub:
      ```bash
      gh auth login   # use the operator's GitHub identity, not the mirror PAT
      for b in $(gh api repos/agentic-stoa/<repo>/branches --jq '.[].name' | grep -v '^main$'); do
        gh api -X DELETE repos/agentic-stoa/<repo>/git/refs/heads/$b
      done
      ```

   h. Enable Gitea branch protection on `main`:
      - Gitea UI: repo → Settings → Branches → Add Rule
      - Rule name: `main`
      - Block direct push: yes (allowlist: operator account only, for break-glass)
      - Require PR + approving review (count: 1, by operator team)
      - Required status check: `tekton/ci` (matches the CI pipeline's commit-status context)

   i. Update local working clones:
      ```bash
      cd ~/repos/<repo>
      git remote set-url origin git@gitea.cluster.derio.net:agentic-stoa/<repo>.git
      git fetch origin --prune
      ```

   j. Update Paperclip's repo configs (path TBD during plan phase — depends on Paperclip's repo registration mechanism) to point at Gitea remotes and consume `STOA_GITEA_TOKEN`.

5. **Documentation:**
   - Update `apps/homepage/manifests/configmap-services.yaml` Gitea tile description if user-visible changes are warranted (probably not — Gitea tile already exists).
   - Capture in `frank-gotchas.md` any quirks observed during the migration (e.g., webhook delivery oddities, Trigger CEL gotchas).

## Original Onboarding a New Repo (Runbook) — pending rewrite

> **Superseded** by a new runbook to be authored as part of the rework's Phase 6/7 work — the "onboard a new repo" flow under GitHub-primary is materially different (no Gitea-side branch protection, no Gitea-as-PR-surface; instead: register GitHub webhook, ensure Gitea-replica repo exists, optionally seed via mirror-clone).

Once the migration pattern is in place, adding a new repo to `agentic-stoa` is mostly mechanical:

1. Create empty private repo on GitHub: `agentic-stoa/<new-repo>` (this is what the backup pipeline will push to)
2. Update `STOA_GITHUB_MIRROR_TOKEN` PAT in GitHub to include the new repo in its `agentic-stoa/*` repo selection
3. Create empty repo on Gitea: `agentic-stoa/<new-repo>`. Push initial content over SSH (clone Gitea remote, commit, push)
4. Drop CI pipeline manifest at `apps/tekton/pipelines/<new-repo>.yaml` (copy `hum.yaml` or `content-factory.yaml` as template)
5. Add Tekton webhook in the Gitea repo (same URL + secret as existing repos)
6. Enable Gitea branch protection on `main` (same rule shape as existing repos)
7. (Optional) Add to Paperclip's repo registry

The shared `github-backup-sync` pipeline picks up the new repo automatically — its Trigger filter matches `agentic-stoa/*`. No additional pipeline definition needed for the backup side.

This is documented as a `# manual-operation` block so it lives in `docs/runbooks/manual-operations.yaml` alongside other one-shot procedures.

## Original Disaster Recovery — semantics flip in rework

> **Semantics inverted** by the rework. Original DR assumed Gitea is source of truth and GitHub is offsite backup. In the active design, GitHub is source of truth (managed by GitHub); Gitea-as-replica is recoverable by re-running `github-pull-sync` against each repo, which is essentially what bootstrap does — so the DR plan for Gitea collapses to "re-pull from GitHub." The original section below documents the prior-direction DR assumptions.

**Gitea down (Longhorn volume failure or pc-1 outage):**
- GitHub holds the latest `main` per repo. Code recovery is intact for `main`; non-`main` branches are lost (acceptable — they're WIP).
- Restore Gitea from Longhorn R2 backup (existing capability) — restores PRs, issues, all branches.
- If R2 restore is too slow and you need to keep working: clone from GitHub, set Gitea aside, work on a temporary GitHub remote, then reconcile after Gitea is back. Document explicitly so the operator doesn't accidentally enshrine GitHub as primary mid-outage.

**Push-mirror token compromised:**
- Rotate `/agentic-stoa/STOA_GITHUB_MIRROR_TOKEN` in Infisical, update each repo's push-mirror config in Gitea UI.
- GitHub-side: revoke the old PAT in GitHub.
- No data loss — the mirror is one-way.

**Gitea-side accidental force-push that wipes history:**
- GitHub mirror has `main` (and tags). Recover by force-pushing back from GitHub to Gitea.
- Non-`main` branches: lost. Acceptable — they're not on GitHub anyway by design.

## Open Items (Deferred)

- **Image build + Zot push** — when a repo first ships a container, extend its CI pipeline with `build-push` (existing layer-19 task) and image signing.
- **Pipeline deploy stages** — `content-factory` runs `n8n-deploy.sh` manually today; could become a Tekton stage gated on merge to `main`. Same for `hum` Supabase migrations.
- **Auto-merge on green CI** — Gitea supports per-PR auto-merge; revisit as a default policy once the agentic loop has a track record. Role-level "agent X can auto-merge on these paths" needs Gitea's CODEOWNERS-style permissions and stays out of scope for now.
- **GitHub PAT auto-rotation** — fine-grained PATs cap at 1 year. Build a Tekton CronJob that uses GitHub's PAT-rotate API (or a small operator) to mint a new PAT before expiry and write it to `/agentic-stoa/STOA_GITHUB_MIRROR_TOKEN` in Infisical. Until then, calendar-driven manual rotation; document the renewal SOP in `docs/runbooks/manual-operations.yaml`.
- **Switch to SSH-based backup push when Gitea supports it** — Forgejo/Gitea both have open feature requests for SSH-key push-mirror auth. Adopting that would eliminate the PAT-rotation problem entirely. Watch [go-gitea/gitea#18159](https://github.com/go-gitea/gitea/issues/18159). Until then, the Tekton-pipeline approach in this spec is the canonical mechanism.
- **Future-public inversion** — when a repo goes public, flip direction: disable the backup pipeline, set up GitHub Actions, configure Gitea pull-mirror from GitHub (matching the `frank` repo pattern). Designed when the first repo actually flips.
- **Gitea SSH host key in agent images** — Paperclip-side agents need `gitea.cluster.derio.net`'s SSH host key in `known_hosts` to clone non-interactively. Bake into agent base image OR distribute via a ConfigMap. Plan-phase decision.

## Manual Operations

```yaml
# manual-operation
id: stoa-gitea-org-create
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-04--cicd--stoa-gitea-primary.md
when: "Before any repo migration"
why_manual: "Gitea org creation is a UI/API operation; operator-owned"
commands:
  - "Gitea UI → + → New Organization → Name: agentic-stoa, visibility: private"
  - "Add operator's Authentik-mapped account as owner"
verify:
  - "curl -H 'Authorization: token $STOA_GITEA_TOKEN' http://192.168.55.209:3000/api/v1/orgs/agentic-stoa | jq .username — returns agentic-stoa"
status: pending
```

```yaml
# manual-operation
id: stoa-bot-user-create
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-04--cicd--stoa-gitea-primary.md
when: "After agentic-stoa org exists"
why_manual: "Gitea user + token creation requires UI/API interaction"
commands:
  - "Gitea UI → Site Administration → User Accounts → Create (username: stoa-bot, email: stoa@frank.local)"
  - "Add stoa-bot as member of agentic-stoa org with Write team membership"
  - "stoa-bot account → Settings → Applications → Generate Token (name: paperclip-agent, scopes: write:repository, write:issue, read:organization)"
  - "In Infisical (prod env), create folder /agentic-stoa if absent (Secrets → Add Folder), then store the token there as STOA_GITEA_TOKEN. Stoa-org secrets stay under /agentic-stoa to keep them separated from frank infra secrets at /."
verify:
  - "Infisical /agentic-stoa/STOA_GITEA_TOKEN exists with non-empty value"
  - "curl -s -o /dev/null -w '%{http_code}\\n' -H 'Authorization: token $STOA_GITEA_TOKEN' http://192.168.55.209:3000/api/v1/orgs/agentic-stoa/members/stoa-bot — returns 204 (stoa-bot is in agentic-stoa). The /api/v1/user endpoint cannot be used here because the token scopes deliberately omit read:user."
status: pending
```

```yaml
# manual-operation
id: stoa-github-mirror-pat
layer: cicd
app: tekton
plan: docs/superpowers/plans/2026-05-04--cicd--stoa-gitea-primary.md
when: "Before deploying github-backup-sync pipeline; recurs annually"
why_manual: "GitHub fine-grained PATs are UI-generated and cap at 1y TTL; rotation automation is a deferred Open Item"
commands:
  - "GitHub Settings → Developer settings → Fine-grained tokens → Generate new"
  - "Resource owner: agentic-stoa; Repository access: select all agentic-stoa/* repos"
  - "Permissions: Contents R/W, Metadata R"
  - "Expiration: 1 year (max). Set a calendar reminder 2 weeks before expiry."
  - "Store in Infisical under /agentic-stoa as STOA_GITHUB_MIRROR_TOKEN (same folder as STOA_GITEA_TOKEN; create the folder via Secrets → Add Folder if it does not yet exist)."
verify:
  - "Infisical /agentic-stoa/STOA_GITHUB_MIRROR_TOKEN exists and not expired"
  - "curl -H 'Authorization: token $STOA_GITHUB_MIRROR_TOKEN' https://api.github.com/repos/agentic-stoa/hum | jq .name — returns hum"
status: pending
```

```yaml
# manual-operation
id: stoa-repo-migrate-mirror-clone
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-04--cicd--stoa-gitea-primary.md
when: "Per repo, after empty Gitea repo created and operator's local WIP is pushed to GitHub"
why_manual: "git clone --mirror runs from operator workstation, not in-cluster"
commands:
  - "git clone --mirror https://github.com/agentic-stoa/<repo>.git /tmp/<repo>.git"
  - "cd /tmp/<repo>.git"
  - "git remote set-url --push origin git@gitea.cluster.derio.net:agentic-stoa/<repo>.git"
  - "git push --mirror"
  - "rm -rf /tmp/<repo>.git"
verify:
  - "Gitea UI → agentic-stoa/<repo> → Branches: shows all original branches"
  - "Gitea UI → agentic-stoa/<repo> → Tags: shows all original tags"
status: pending
```

```yaml
# manual-operation
id: stoa-repo-webhook
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-04--cicd--stoa-gitea-primary.md
when: "Per repo, after CI pipeline manifest is committed to frank"
why_manual: "Gitea per-repo webhook config is UI-only"
commands:
  - "Gitea UI → repo → Settings → Webhooks → Add → Gitea"
  - "URL: http://el-gitea-listener.tekton-pipelines.svc.cluster.local:8080"
  - "Secret: $GITEA_WEBHOOK_SECRET"
  - "Events: Push, Pull Request"
verify:
  - "Webhooks list → Test Delivery → returns 2xx"
  - "Push a feature-branch commit; Tekton Dashboard shows the per-repo CI PipelineRun within 10s"
  - "Push a commit on main; Tekton Dashboard shows BOTH the CI PipelineRun and a github-backup-sync PipelineRun"
status: pending
```

```yaml
# manual-operation
id: stoa-prune-github-non-main
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-04--cicd--stoa-gitea-primary.md
when: "Per repo, after backup smoke test confirms main propagates to GitHub"
why_manual: "One-time deletion of legacy branches on GitHub; operator-owned"
commands:
  - "gh auth login   # operator's GitHub identity, NOT the mirror PAT"
  - "for b in $(gh api repos/agentic-stoa/<repo>/branches --jq '.[].name' | grep -v '^main$'); do gh api -X DELETE repos/agentic-stoa/<repo>/git/refs/heads/$b; done"
verify:
  - "gh api repos/agentic-stoa/<repo>/branches --jq '.[].name' — returns only main"
  - "Tags retained: gh api repos/agentic-stoa/<repo>/tags — pre-migration tag list intact"
status: pending
```

```yaml
# manual-operation
id: stoa-gitea-branch-protection
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-04--cicd--stoa-gitea-primary.md
when: "Per repo, after migration verified and Paperclip can clone"
why_manual: "Branch protection is UI-configured per-repo; defines operator-only merge policy"
commands:
  - "Gitea UI → repo → Settings → Branches → Add Rule"
  - "Rule name pattern: main"
  - "Enable: Disable Push (allow only operator account for break-glass)"
  - "Enable: Require Pull Request to Merge"
  - "Required approvals: 1 (from operator team)"
  - "Required status checks: tekton/ci"
  - "Block on rejected reviews: yes"
verify:
  - "As stoa-bot, attempt git push origin main directly → rejected"
  - "Open a PR from a feature branch → merge button is disabled until CI passes and operator approves"
status: pending
```

```yaml
# manual-operation
id: stoa-local-clone-remap
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-04--cicd--stoa-gitea-primary.md
when: "Per repo, after migration verified"
why_manual: "Operator's local clones live outside the cluster"
commands:
  - "cd ~/repos/<repo>"
  - "git remote set-url origin git@gitea.cluster.derio.net:agentic-stoa/<repo>.git"
  - "git fetch origin --prune"
verify:
  - "git remote -v shows gitea.cluster.derio.net"
  - "git pull works"
status: pending
```

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| Stoa Org Gitea-Primary Implementation Plan | derio-net/frank | `docs/superpowers/archived-plans/2026-05-05--cicd--stoa-gitea-primary/` | layer 19 (deployed) |
| Stoa Org Gitea-Primary Implementation Plan — **Rework 1: GitHub-primary** | derio-net/frank | `docs/superpowers/archived-plans/2026-05-05--cicd--stoa-gitea-primary-rework-1/` | parent plan above |
