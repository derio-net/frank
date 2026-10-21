# CI forge tiers — onboarding and offboarding repos

How a repo gets onto GitHub-preferred CI with Gitea fallback, how it comes off, and
the script that checks every step. Design: `docs/superpowers/specs/2026-10-18--cicd--github-preferred-gitea-fallback-design.md`
(frank#875).

**Script:** `bash scripts/ci-budget-ops.sh`. Run it with no arguments for a read-only
`DONE`/`OPEN` report. It derives the repo list from `apps/ci-budget/tiers.yaml`, so
the tier file is the single input.

## Which tier?

| The repo is… | Tier | What you do |
|---|---|---|
| public | `github-only` (always) | nothing; public minutes are free |
| private, cheap on GitHub, or mostly macOS | `github-only` | nothing (the default for repos absent from `tiers.yaml`) |
| private, should survive an exhausted budget | `github-preferred` | the full onboarding below |
| private, should never use GitHub minutes | `gitea-only` | the onboarding below, with the authority pinned to `gitea` |

The monthly `CI tier review <YYYY-MM>` issue, in the private derio-net/willikins
repo, proposes tier changes from billed minutes. It also lists billed repos that
`tiers.yaml` does not know yet; those are your onboarding candidates.

## Onboarding a repo (`github-preferred`), in an org that is already mirrored

This covers derio-net and derio-homelab. A new org also needs its own App, token
generator, webhook secret, pull-sync pipeline and triggers; use spec §2 as the
template.

1. **In the repo:** apply the gate convention (spec §6).
   - Check jobs get the authority gate.
   - Mutating jobs and `macos-*` jobs get the GitHub pin.
   - Split any matrix that mixes macOS and Linux.
   - Add `sync-pr-**` and `sync-rerun-**` push triggers.
   - Gated jobs use `runs-on: ubuntu-latest` or `ubuntu-24.04`.

   Then run the checker until it is clean:

   `python3 scripts/ci_gate_coverage.py <clone> --tier github-preferred --runner-config apps/gitea-runner/manifests/files/config.yaml`

   Merge that repo's PR. It is safe before anything else: an unset `CI_AUTHORITY` means `github`.
2. **In frank:** add the repo to `apps/ci-budget/tiers.yaml`, then run
   `.venv/bin/pytest scripts/tests/test_github_preferred_mirrors.py scripts/tests/test_ci_mirror_resilience.py scripts/tests/test_webhook_delivery_paths.py scripts/tests/test_ci_budget_tiers.py scripts/tests/test_ci_budget_manifests.py`.
   The guards fail until the repo appears in every place that must name it:
   - the `*-main-sync` / `*-pr-sync` CEL filters;
   - `MAIN_REPOS` / `PR_REPOS` in `mirror-reconcile` (both stages) and `ci-delivery-check`;
   - the `gitea-status-bridge` allowlist;
   - a `webhooks.yaml` entry;
   - the `repositories:` of the org's mirror and `ci-authority` ClusterGenerators.

   Follow the failures.
3. **GitHub App:** add the repo to the org App installation's repository access (UI).
   Check with `bash scripts/ci-budget-ops.sh status app-permissions`.
4. **Gitea side, before the frank PR merges:** run `bash scripts/ci-budget-ops.sh apply gitea-mirrors`.
   It creates the private mirror with Actions enabled and the repo variable
   `CI_AUTHORITY=github`, then backfills branches and tags. It is idempotent and
   only touches repos missing on Gitea.
   **Backfilled tags start workflows.** Gitea fires `on: push: tags` workflows as the
   tags arrive, and an old tag carries the *old* workflow file, which has no forge gate.
   `derio-net/vibe-kanban` (2026-10-19) queued eight tag runs / 54 jobs on the single
   runner for 9 hours. Before running this op on a repo, check what its tags would
   trigger (`git show <tag>:.github/workflows/`); if any `on: push: tags` workflow is
   ungated, push the branches first and skip or cancel the tag runs. Gitea 1.25 has no
   API to cancel a run (only the web UI), and a queued run cannot be deleted.
5. **Merge the frank PR.** Then run `bash scripts/ci-budget-ops.sh apply github-webhooks`
   to add the repo webhook (push + pull_request, the org's HMAC secret).
6. **Secrets:** if a gated job needs a read-only secret, declare it under the repo's
   `gitea_secrets` and in `readonly_secrets`. Then run `apply readonly-secrets`
   (repository-level, never org-level).
7. **Verify:** `bash scripts/ci-budget-ops.sh status`. Then push to a PR and check
   that `gitea-actions/*` statuses appear when you hand-set `pin_authority: gitea`
   (spec Test Plan rows 1–2).

**`gitea-only`:** use the same steps, with `tier: gitea-only`. Then set both
authority variables to `gitea`: the Gitea repo variable, then the GitHub repo
variable, in that order. The watcher never writes `gitea-only` repos.

## Offboarding a repo

The order matters, and two failures pull in opposite directions:

- **While the repo is still in `tiers.yaml`, the watcher owns its `CI_AUTHORITY`.**
  Every 10 minutes it writes the org's computed authority to both forges, so an
  `offboard` run first is undone: the variable goes back to `gitea` on the next tick.
- **Once the watcher stops managing it, a repo left at `CI_AUTHORITY=gitea` on
  GitHub skips its gated jobs forever.** Nothing else ever sets it back.

So the frank PR goes first and `offboard` second:

1. **Frank PR.** Remove the repo from `tiers.yaml` and let the guards list the
   other places to drop it (`MAIN_REPOS`/`PR_REPOS` in `mirror-reconcile` and
   `ci-delivery-check`, the mirror and ci-authority ClusterGenerators' `repositories:`,
   the github-listener and gitea-status-bridge CEL filters, `apps/tekton/webhooks.yaml`).
   As in onboarding step 2, these are list edits inside existing objects, so they
   apply despite `prune: false`.
2. **Confirm it landed.** Hard-refresh `root`, `ci-budget` and `tekton-extras`, then
   check `status.operationState.operation.sync.revision` against the merge SHA (it
   lagged for #896, and `Synced` alone does not prove anything). Then check the live
   tiers ConfigMap, CronJobs, ClusterGenerators and EventListeners no longer name the repo.
3. **Forge half.** `bash scripts/ci-budget-ops.sh offboard <org/repo>` (absolute
   `KUBECONFIG`, `.env` sourced from the base clone) does, in this order:
   1. GitHub repo variable `CI_AUTHORITY=github` (skipped if the repo was deleted);
   2. delete the GitHub webhook to the listener;
   3. delete the Gitea mirror (its `sync-pr`/`sync-rerun` refs go with it).
4. **Verify.** `status gitea-mirrors` reports 0 open (no orphan), and the next
   `ci-delivery-check` and `mirror-reconcile` runs *after the sync* have no line for
   the repo. If the repo still exists, also remove it from the App installation's
   repository access. Only now can the GitHub repo be deleted.

Between steps 1 and 3 the GitHub variable can still read `gitea`, so gated jobs
skip for that window. Keep it short. It is harmless for a repo about to be deleted.

| Situation | Notes |
|---|---|
| repo **deleted** on GitHub | the variable and webhook are already gone; `offboard` deletes the mirror |
| repo made **public** | it becomes `github-only` by rule; the monthly report proposes removing it |
| repo **moved** to `github-only` | its workflows can keep their gates, which are harmless with the authority at `github` |
| a **forgotten** mirror | `status gitea-mirrors` flags any Gitea mirror whose repo left `tiers.yaml` |

## The one-off manual operations (frank#875)

`bash scripts/ci-budget-ops.sh status` covers all of these.

| op | when | how |
|---|---|---|
| `app-permissions` | PRE-MERGE | UI; `status` verifies the permissions, the installation repos and a live billing read with each App token |
| `gitea-semantics` | PRE-MERGE | `apply gitea-semantics` (scratch repo, then cleanup; it records the proof) |
| `gitea-org` | PRE-MERGE | `apply gitea-org` (org, bot, tokens written as SOPS files + applied, status webhooks, and the read-only `ci-readers` team that lets `tekton-bot` — the `ci-delivery-check` identity — read every private mirror; without it the checker gets 404 and reports `read-error 404`) |
| (notifier) | declarative | `ci-budget-telegram` is an ExternalSecret over the C2 bot (`apps/ci-budget/externalsecrets.yaml`), not an op. The watcher treats it as optional, so a missing Secret silently disables every flip/would-flip/refusal message; `status gitea-org` flags it. |
| `gitea-mirrors` | PRE-MERGE | `apply gitea-mirrors` |
| `webhook-secret` | post-merge, before webhooks | `apply webhook-secret` — seeds the never-seeded derio-net HMAC secret (Infisical `/derio-net/GITHUB_WEBHOOK_SECRET`, pre-existing op `cicd-staging-gate-runs-fr-webhook`) and the same value into runs-fr's `FRANK_STAGING_GATE_WEBHOOK_SECRET` |
| `github-webhooks` | post-merge | `apply github-webhooks` |
| `readonly-secrets` | post-merge | `apply readonly-secrets` (none declared today) |
| `orphan-template` | post-merge | `apply orphan-template` |
| `go-live` | post-merge, per org | a PR setting `mode: live` |
