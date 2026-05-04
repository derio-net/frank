# CI/CD: Stoa Org Gitea-Primary — Design

**Date:** 2026-05-04
**Status:** Design
**Layer:** cicd (19) — extension

## Overview

Onboard the `agentic-stoa` org's repos onto Frank's existing CI/CD platform (Gitea + Tekton + Zot from layer 19) with a **Gitea-primary, GitHub-backup** sync model. Two repos in scope today: `hum` and `content-factory`. The pattern is reusable for any future repo in the org.

This is the **inverse direction** of how `derio-net/frank` itself uses Gitea. `frank` is a public infra repo: GitHub-primary, Gitea pull-mirrors as a CI cache. `agentic-stoa/*` repos are private business-side code: Gitea-primary, GitHub push-mirrors as offsite backup. Both directions live on the same Gitea/Tekton stack — only the per-repo mirror configuration differs.

## Goals

- Develop, branch, PR, and run CI entirely on Frank for `agentic-stoa` repos
- GitHub holds a code-only backup (push-mirror), not part of any active workflow
- Establish a reusable pattern (org + bot account + push-mirror + Tekton pipeline + webhook) for future repos
- Reuse the layer-19 platform — no new infrastructure components

## Non-Goals

- Migrating issues, PRs, projects, or wikis from GitHub (Gitea starts fresh; the one open issue on `hum` is being closed manually)
- Image build + Zot push in MVP pipelines (deferred until a repo actually ships a container)
- Deploy steps inside pipelines (n8n workflow deploy, Supabase migrations, mobile builds) — manual for now
- "Future-public" inversion — flipping a repo back to GitHub-primary if it ever goes public is out of scope and will be designed when the first repo flips
- GitHub-side branch protection — honor system, mirror PAT is the only writer

## Architecture

```
            ┌───── Frank cluster ───────────────────────────────┐
            │                                                    │
 dev pushes │   ┌─ agentic-stoa/<repo> on Gitea                  │
   over SSH ├──►│  (192.168.55.209:2222 via Tailscale)           │
  (humans + │   │                                                │
   Paperclip│   │   on push: Gitea webhook                       │
   agents)  │   │       │                                        │
            │   │       ▼                                        │
            │   │  el-gitea-listener.tekton-pipelines.svc:8080   │
            │   │       │                                        │
            │   │       ▼                                        │
            │   │  TriggerBinding → TriggerTemplate              │
            │   │       │                                        │
            │   │       ▼                                        │
            │   │  PipelineRun on pc-1                           │
            │   │   ├─ git-clone                                 │
            │   │   ├─ run-tests (per-repo: npm / pytest)        │
            │   │   └─ gitea-status (commit status → Gitea PR)   │
            │   │                                                │
            │   └─ Gitea push-mirror                             │
            │           │ (real-time, branch-filtered)           │
            └───────────┼────────────────────────────────────────┘
                        │
                        ▼
              github.com/agentic-stoa/<repo>
                  (private, code-only backup;
                   only writer is STOA_GITHUB_MIRROR_TOKEN)
```

## Sync Model

**Direction:** Gitea → GitHub, one-way. Nothing pulls from GitHub. PRs and issues live exclusively on Gitea (they are not git refs and don't propagate via push-mirror; that's acceptable since Gitea state is on Longhorn-backed PVC with R2 backup).

**Two-phase mirror configuration per repo:**

1. **Migration phase** — push-mirror configured with **no branch filter**. The one-shot `git push --mirror` (run from a workstation, not from Gitea) carries every branch and tag from GitHub into Gitea. After the initial push, Gitea's push-mirror back to GitHub will keep all branches in sync.

2. **Steady-state phase** — once migration is verified, on the GitHub side prune everything except `main` and tags, then on the Gitea side narrow the push-mirror branch filter to `main` only (tags continue to push). All other branches (`vk/*`, `claude/*`, work-in-progress, etc.) remain Gitea-only and never reach GitHub. Phase transition is per-repo and irreversible without redoing migration.

**Branch filter mechanism:** Gitea push-mirror supports a branch filter pattern in repo settings (Mirror Settings → Push → Branch filter). Confirmed against Gitea 1.21+. If the running version doesn't support filters cleanly, fall back to a Tekton `finally`-task that force-deletes non-`main` branches on GitHub via the GitHub API after each push — adds a moving part but bounded.

**What propagates:** code (every commit on `main`), tags. **What doesn't:** issues, PRs, comments, releases, wikis, runner state, webhook deliveries.

## Org & Auth

**Gitea org:** Create `agentic-stoa` (matches GitHub org name for symmetry). Owner: the operator's Authentik-mapped Gitea account.

**Service account:** `stoa-bot` (Gitea-local user, member of `agentic-stoa` org with **write access** on all repos). Paperclip agents identify as `stoa-bot` for all git operations: cloning, branch creation, commits, push, and PR open/comment via Gitea API. `tekton-bot` retains its existing role of writing commit statuses from inside pipelines (separate concern, separate token).

**Tokens:**
- `stoa-bot` Gitea API token → Infisical key `STOA_GITEA_TOKEN`. Projected into Paperclip agent envs via ESO ExternalSecret. Scopes: `write:repository`, `write:issue`, `read:organization`. Used for clone, push, PR open, comment.
- `tekton-bot` already has `GITEA_API_TOKEN` for status writes — extend its org membership to include `agentic-stoa` (org-write team) so commit statuses can post on `agentic-stoa/*` PRs.

**SSH access for humans:** the operator adds their SSH public key to their personal Gitea account (one-time UI step). Clone URL: `git@gitea.cluster.derio.net:agentic-stoa/<repo>.git` (resolves via mesh DNS over Tailscale to 192.168.55.209:2222 — Gitea's default SSH port). HTTPS clone via `https://gitea.cluster.derio.net/agentic-stoa/<repo>.git` is supported but SSH is preferred (no token rotation).

**GitHub-side credentials:** A single GitHub fine-grained PAT scoped to the `agentic-stoa` org with `Contents: read+write` and `Metadata: read` on the two starting repos (and any future ones — repo selection updated when new repos are added). Stored in Infisical as `STOA_GITHUB_MIRROR_TOKEN`. Configured per-repo in Gitea push-mirror settings (Gitea does not have an org-level mirror credential pool; one entry per repo).

## Pipelines (MVP)

Each repo gets a Tekton Pipeline + a Pipeline-bound Trigger config. All reuse the existing `el-gitea-listener` EventListener and `gitea-push-binding` TriggerBinding from layer 19 — no new EventListener.

**Common pipeline shape (3 tasks):**
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

**Pipeline files:**
```
apps/tekton/pipelines/
  hum.yaml             # Pipeline CR + repo-scoped Trigger
  content-factory.yaml # Pipeline CR + repo-scoped Trigger
```

The repo-scoped Trigger pattern (a `Trigger` resource bound to the existing EventListener that filters on `body.repository.full_name == "agentic-stoa/<repo>"`) lets each repo evolve its pipeline independently without touching the shared EventListener.

## Secrets

| Secret | Source | Type | Used by | When created |
|---|---|---|---|---|
| `STOA_GITHUB_MIRROR_TOKEN` | Infisical | GitHub fine-grained PAT (Contents R/W on `agentic-stoa/*`) | Gitea push-mirror | Before push-mirror configuration |
| `STOA_GITEA_TOKEN` | Infisical | Gitea API token (`stoa-bot`, write scope on `agentic-stoa`) | Paperclip agents (clone, push, PR ops) | After `stoa-bot` user created in Gitea |
| `GITEA_API_TOKEN` | Infisical (existing) | Gitea API token (`tekton-bot`, write scope) | Tekton `gitea-status` task | Already exists; org membership extended |
| `GITEA_WEBHOOK_SECRET` | Infisical (existing) | Random string | EventListener CEL interceptor + Gitea webhook | Already exists; reused |

The two new entries (`STOA_GITHUB_MIRROR_TOKEN`, `STOA_GITEA_TOKEN`) get ExternalSecret CRs:
- `STOA_GITEA_TOKEN` projected into the Paperclip namespace where agent pods consume it
- `STOA_GITHUB_MIRROR_TOKEN` is *only* used in the Gitea push-mirror UI — it's not auto-projected into a K8s Secret. Operator pastes it once per repo at config time. (Acceptable: rotation is rare, blast radius is one PAT.)

## Migration Sequence (per repo, runs for both `hum` and `content-factory` in parallel)

**Prerequisite (operator):** push all outstanding local work to current GitHub remotes. The migration starts with `git clone --mirror` from GitHub, so anything not on GitHub at that moment is lost.

1. **Gitea org + bot setup (one-time, both repos share):**
   - Create `agentic-stoa` org in Gitea (UI)
   - Create `stoa-bot` user in Gitea, add to org with Write team membership (UI)
   - Generate API token for `stoa-bot`, store in Infisical as `STOA_GITEA_TOKEN`
   - Verify `tekton-bot` has org membership with status-write permission

2. **GitHub PAT (one-time):**
   - Create fine-grained PAT in GitHub UI (`agentic-stoa` org, both repos selected, `Contents: R/W`)
   - Store in Infisical as `STOA_GITHUB_MIRROR_TOKEN`

3. **Per-repo migration (parallelizable):**

   a. Create empty repo in Gitea: `agentic-stoa/<repo>` (UI, default branch `main`, no README/license — needs to be empty for the mirror push)

   b. From a workstation:
      ```bash
      git clone --mirror https://github.com/agentic-stoa/<repo>.git /tmp/<repo>.git
      cd /tmp/<repo>.git
      git remote set-url --push origin git@gitea.cluster.derio.net:agentic-stoa/<repo>.git
      git push --mirror
      ```
      Verify in Gitea UI: all branches and tags present.

   c. Configure Gitea push-mirror back to GitHub (UI: repo → Settings → Mirror Settings → Push):
      - URL: `https://github.com/agentic-stoa/<repo>.git`
      - Username: `agentic-stoa` (or any string — GitHub PATs ignore username)
      - Password: `STOA_GITHUB_MIRROR_TOKEN` value
      - Sync interval: `0` (real-time, push on every commit) — verify Gitea's "sync now" works
      - Branch filter: empty (everything mirrors during migration phase)

   d. Smoke test: push a no-op commit on a non-`main` branch in Gitea, verify it appears on GitHub within seconds.

   e. Add Tekton webhook (UI: repo → Settings → Webhooks → Add → Gitea):
      - URL: `http://el-gitea-listener.tekton-pipelines.svc.cluster.local:8080`
      - Secret: `GITEA_WEBHOOK_SECRET` value
      - Events: Push, Pull Request

   f. Drop pipeline manifest at `apps/tekton/pipelines/<repo>.yaml`. Commit + push to `frank` repo. ArgoCD `tekton-extras` syncs.

   g. Verify pipeline triggers: push a commit to a feature branch in Gitea, watch Tekton Dashboard for PipelineRun. Confirm Gitea PR view shows commit status from `gitea-status` task.

   h. Update local working clones:
      ```bash
      cd ~/repos/<repo>
      git remote set-url origin git@gitea.cluster.derio.net:agentic-stoa/<repo>.git
      git fetch origin --prune
      ```

   i. Update Paperclip's repo configs (path TBD during plan phase — depends on Paperclip's repo registration mechanism) to point at Gitea remotes and consume `STOA_GITEA_TOKEN`.

4. **Steady-state cutover (per repo, after both repos pass smoke tests):**

   a. On GitHub side, delete every branch except `main`. Tags retained.
      ```bash
      # From a workstation, or via GitHub UI
      gh api -X DELETE repos/agentic-stoa/<repo>/git/refs/heads/<branch>
      ```

   b. In Gitea push-mirror settings, edit branch filter: change from empty to `main` (verify Gitea version supports this; fallback noted in Sync Model section).

   c. Smoke test: push a commit to a non-`main` branch in Gitea, verify it does NOT appear on GitHub. Push to `main`, verify it does.

5. **Documentation:**
   - Update `apps/homepage/manifests/configmap-services.yaml` Gitea tile description to mention `agentic-stoa` org if it's user-visible (probably not — Gitea tile already exists).
   - Add entries to `frank-gotchas.md` for any quirks discovered (e.g., push-mirror branch filter behavior).

## Onboarding a New Repo (Runbook)

Once the migration is done, the steady-state pattern for adding a new repo to `agentic-stoa`:

1. Create empty private repo on GitHub: `agentic-stoa/<new-repo>`
2. Create empty repo on Gitea: `agentic-stoa/<new-repo>`
3. Push initial content to Gitea (clone Gitea remote, commit, push)
4. Configure Gitea push-mirror to GitHub with `main`-only branch filter from day one (skip the migration phase entirely)
5. Update `STOA_GITHUB_MIRROR_TOKEN` PAT scope on GitHub to include the new repo
6. Add Tekton webhook + pipeline manifest (follow `hum`/`content-factory` template)
7. (Optional) Add to Paperclip's repo registry

This is documented as a `# manual-operation` block so it lives in `docs/runbooks/manual-operations.yaml` alongside other one-shot procedures.

## Disaster Recovery

**Gitea down (Longhorn volume failure or pc-1 outage):**
- GitHub holds the latest `main` per repo. Code recovery is intact for `main`; non-`main` branches are lost (acceptable — they're WIP).
- Restore Gitea from Longhorn R2 backup (existing capability) — restores PRs, issues, all branches.
- If R2 restore is too slow and you need to keep working: clone from GitHub, set Gitea aside, work on a temporary GitHub remote, then reconcile after Gitea is back. Document explicitly so the operator doesn't accidentally enshrine GitHub as primary mid-outage.

**Push-mirror token compromised:**
- Rotate `STOA_GITHUB_MIRROR_TOKEN` in Infisical, update each repo's push-mirror config in Gitea UI.
- GitHub-side: revoke the old PAT in GitHub.
- No data loss — the mirror is one-way.

**Gitea-side accidental force-push that wipes history:**
- GitHub mirror has `main` (and tags). Recover by force-pushing back from GitHub to Gitea.
- Non-`main` branches: lost. Acceptable — they're not on GitHub anyway by design.

## Open Items (Deferred)

- **Image build + Zot push** — when a repo first ships a container, extend its pipeline with `build-push` (existing layer-19 task) and image signing.
- **Pipeline deploy stages** — `content-factory` runs `n8n-deploy.sh` manually today; could become a Tekton stage gated on merge to `main`. Same for `hum` Supabase migrations.
- **Future-public inversion** — when a repo goes public, flip direction: tear down push-mirror, set up GitHub Actions, configure pull-mirror back into Gitea (matching the `frank` repo pattern). Designed when the first repo actually flips.
- **Org-wide mirror credential pool** — Gitea v1.22+ may add this; revisit if/when it lands so we don't store the same PAT in N per-repo configs.
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
  - "Store token in Infisical as STOA_GITEA_TOKEN"
verify:
  - "curl -H 'Authorization: token $STOA_GITEA_TOKEN' http://192.168.55.209:3000/api/v1/user — returns stoa-bot"
status: pending
```

```yaml
# manual-operation
id: stoa-github-mirror-pat
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-04--cicd--stoa-gitea-primary.md
when: "Before configuring push-mirror on any repo"
why_manual: "GitHub PAT generation is a github.com UI operation"
commands:
  - "GitHub Settings → Developer settings → Fine-grained tokens → Generate new"
  - "Resource owner: agentic-stoa; Repository access: select hum + content-factory (and any future repos)"
  - "Permissions: Contents R/W, Metadata R"
  - "Store in Infisical as STOA_GITHUB_MIRROR_TOKEN"
verify:
  - "Infisical → STOA_GITHUB_MIRROR_TOKEN exists"
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
id: stoa-repo-pushmirror-config
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-04--cicd--stoa-gitea-primary.md
when: "Per repo, after mirror clone is verified"
why_manual: "Gitea per-repo push-mirror config is UI-only (or one-shot API)"
commands:
  - "Gitea UI → repo → Settings → Mirror Settings → Push"
  - "URL: https://github.com/agentic-stoa/<repo>.git; Username: x; Password: $STOA_GITHUB_MIRROR_TOKEN"
  - "Sync interval: 0 (real-time); Branch filter: empty (migration phase)"
  - "Click 'Sync Now' to verify"
verify:
  - "Push a no-op commit on a feature branch in Gitea"
  - "Within 30s, GitHub branch list shows the new commit"
status: pending
```

```yaml
# manual-operation
id: stoa-repo-webhook
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-04--cicd--stoa-gitea-primary.md
when: "Per repo, after pipeline manifest is committed to frank"
why_manual: "Gitea per-repo webhook config is UI-only"
commands:
  - "Gitea UI → repo → Settings → Webhooks → Add → Gitea"
  - "URL: http://el-gitea-listener.tekton-pipelines.svc.cluster.local:8080"
  - "Secret: $GITEA_WEBHOOK_SECRET"
  - "Events: Push, Pull Request"
verify:
  - "Webhooks list → Test Delivery → returns 2xx"
  - "Push a commit; Tekton Dashboard shows PipelineRun within 10s"
status: pending
```

```yaml
# manual-operation
id: stoa-steady-state-cutover
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-04--cicd--stoa-gitea-primary.md
when: "Per repo, after pipeline + push-mirror smoke tests pass"
why_manual: "GitHub branch deletion + Gitea filter narrowing are one-shot operator decisions"
commands:
  - "On GitHub side, delete every branch except main (gh CLI or UI). Tags stay."
  - "  for b in $(gh api repos/agentic-stoa/<repo>/branches --jq '.[].name' | grep -v '^main$'); do gh api -X DELETE repos/agentic-stoa/<repo>/git/refs/heads/$b; done"
  - "Gitea UI → repo → Settings → Mirror Settings → Push → edit Branch filter to: main"
verify:
  - "GitHub branches list: only main"
  - "Push a commit to a non-main branch in Gitea; GitHub does NOT show the new branch"
  - "Push a commit to main in Gitea; GitHub main updates within 30s"
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

## Implementation Plan

| Plan | File | Status | Depends on |
|------|------|--------|------------|
| Stoa Gitea-Primary Implementation Plan | `docs/superpowers/plans/2026-05-04--cicd--stoa-gitea-primary.md` | TBD | layer 19 (deployed) |
