# Full agentic-stoa Mirror + Gitea Actions CI on Frank

**Spec:** `docs/superpowers/specs/2026-07-19--cicd--stoa-full-mirror-gitea-actions-design.md`
**Status:** In progress

## Why

GitHub Actions minutes on private agentic-stoa repos are too expensive —
`cnc-fr/pins-update.yml` alone fires every 30 minutes (~1,500 runs/month), plus
per-PR CI across five repos (13 workflows total). The operator's engine
question ("isn't Tekton's format Actions-compatible?") is answered in the spec:
it is not — Gitea Actions is, and Gitea already runs on Frank. So: complete the
mirror set (3 repos missing), enable Gitea Actions, deploy an act_runner, and
bridge run results back to GitHub commit statuses.

## Shape of the work

- **Phase 1** extends the existing webhook-driven mirror (github-listener →
  `github-pull-sync`) to second-brain, hermes-brain (main + PR sync) and
  flexible-health (main only — no workflows). Unlike the Phase-4-era repos,
  these get NO bespoke Tekton CI pipeline: the mirror push itself triggers
  Gitea Actions.
- **Phase 2** enables `actions.ENABLED` in the gitea chart values and adds
  `apps/gitea-runner/` — act_runner + DinD sidecar in a new privileged-labeled
  `gitea-runner` namespace on pc-1, capacity 2, tool cache on a longhorn-cicd
  PVC, registration token via ESO from Infisical.
- **Phase 3** adds the status bridge: Gitea `status` webhook events (Gitea
  1.25.4 live) → `gitea-listener` trigger → new `stoa-status-bridge` pipeline →
  existing `github-status` task, context-prefixed `gitea-actions/`. Tekton's
  own dual-status contexts are filtered out to avoid double-posting.
- **Phase 4** does the extension-workflow docs: retro-updates to the cicd
  building/operating posts, gotcha capture, runbook + README sync.
- **Phase 5 [manual]** is deliberately back-loaded (fr-goal placement policy):
  runner token mint, Gitea repo creation + backfill ×3, GitHub webhooks ×3,
  Gitea org Actions secrets (`STOA_APP_PRIVATE_KEY`, `STOA_CI_GH_TOKEN`) +
  `CI_AUTHORITY=github` variable + org status webhook, and a smoke check.
  The PR ships with this phase unimplemented; the operator executes and pushes
  evidence to the same PR.

## Cross-repo coordination (not phases of this plan)

The five workflow-bearing repos (second-brain, cnc-fr, cnc-frd, cnc-fru,
hermes-brain) each need one small PR — `sync-pr-**` push triggers,
`${{ secrets.STOA_CI_GH_TOKEN || secrets.GITHUB_TOKEN }}` fallbacks, and
`CI_AUTHORITY` guards on mutating jobs. Per fr-goal's multi-repo rule those are
dispatched one agent per repo (worktree isolation) against this spec; they are
sequenced AFTER this plan's phases 1–3 merge and BEFORE the Test Plan runs.
All edits are no-ops on the GitHub side, so ordering risk is low. Repo names
and workflow filenames only in frank artifacts (third-party privacy rule).

## Parallel-running safety (the load-bearing guard)

The operator chose to keep GitHub Actions enabled. Non-mutating jobs running
twice is waste, not damage. Mutating jobs (pins-update PR robot, auto-tag,
release image pushes, acceptance-report issue upsert, fixtures-recapture) must
run from exactly one side: they gate on `vars.CI_AUTHORITY` (default `github`),
compared against the side derived from `github.server_url`. Cutover later =
flip one org variable, no workflow edits. This is acceptance row
`stoa-ci-no-double-mutation`.

## Test Plan (post-merge, operator-driven — from the spec)

1. PR class: test PR in cnc-frd → postgres service container run on Frank →
   status on the GitHub PR sha (`gitea-actions/…`).
2. Schedule class: pins-update fires on Frank's next half-hour tick,
   check-only under `CI_AUTHORITY=github`.
3. Artifact class: workflow_dispatch acceptance-report on second-brain's
   mirror → artifact downloadable from Gitea.
4. Steady state: a week of parallel green before the operator flips authority /
   disables GH Actions per repo (out of scope here).

## Deviations

(recorded during execution)

- 2026-07-20 P4.T2.S1: runbook merge done surgically (4 new cicd entries
  inserted after the last cicd entry, formatting preserved) rather than the
  skill's full-rewrite-and-sort — the live file's tail is append-ordered, and
  a full resort would have produced a large unrelated diff in this PR.
- 2026-07-20 P4.T2.S2: README updated by targeted edits (CI/CD Platform row,
  gitea row, new gitea-runner row) instead of a full /update-readme run; the
  full sync remains a post-merge post-deploy-checklist item.
