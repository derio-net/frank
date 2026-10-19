<!-- fr:journal-schema=2 -->
# Journal: 2026-10-18--cicd--github-preferred-gitea-fallback

<!-- fr:journal kind=discovery scope=spec id=operator-brief-issue-875 created=2026-10-18T14:33:01+00:00 input=true -->
### operator-brief-issue-875 · discovery · Operator brief: derio-net/frank#875 (verbatim)

# cicd: GitHub-preferred CI with automatic Gitea fallback across derio-net, derio-homelab and agentic-stoa

## Goal

CI for the three GitHub orgs (derio-net, derio-homelab, agentic-stoa) prefers GitHub Actions and falls back to Gitea Actions on Frank **automatically** when a GitHub org's free minutes run low. Each repo has a forge tier, and a monthly report reviews the tiers.

## Why now

- On 2026-10-18 derio-net ran out of its 2,000 free private-repo minutes ("job was not started because ... spending limit"). Most of it came from a macOS matrix leg (10x billing). willikins#488 has since path-filtered that leg.
- derio-homelab is at 1,801 / 2,000 for October.
- agentic-stoa moved to Gitea on 2026-07-22, but the move is manual and two-sided (`cicd-stoa-ci-authority-cutover`).
- Nothing monitors GitHub minutes today.

October usage (billing API `/organizations/<org>/settings/billing/usage`, private repos only; public repos are free):

| Org | Repo | Minutes |
|---|---|---|
| derio-net | willikins | 304 Linux + 128 macOS (×10) |
| derio-net | herdr-vertical-tabs | 37 Linux + 12 macOS (×10) |
| derio-net | vibe-kanban | 109 |
| derio-net | .github-private | 78 (workflow since disabled) |
| derio-net | presentation-craft | 25 |
| derio-homelab | kid-laptops | 1,201 (being gated and moved to Gitea now) |
| derio-homelab | proxmox-cluster | 478 |
| derio-homelab | omada-controller | 90 |
| derio-homelab | ansible-pihole | 18 |
| derio-homelab | homelab | 14 |

The billing period is the calendar month.

## Decided (operator, 2026-10-18)

- **Tiers per repo:**
  - `github-only`: all public repos, which bill nothing, and any job with `runs-on: macos-*`, since Gitea has no macOS runner.
  - `gitea-only`.
  - `github-preferred` (standby): runs on GitHub, flips to Gitea automatically.
- **The tier list is reviewed monthly**, from per-repo billed minutes. The report counts each job rounded up to a whole minute, and macOS at ×10.
- **Automatic fallback:**
  - A watcher reads each org's billing usage.
  - At **≥85%** of the included minutes, it flips that org's `github-preferred` repos to `CI_AUTHORITY=gitea`. At the monthly reset it flips them back.
  - **Order:** to Gitea, set the Gitea side first, then GitHub. Back to GitHub, set the GitHub side first, then Gitea. Then there is never a window where neither forge runs, and at worst both run briefly.
  - **Backstop:** if a job fails with the "spending limit" annotation, flip at once and re-run the job on Gitea.
- **Runners stay on pc-1 only.** No runners on the minis or gpu-1 for now. Keep capacity 2. Raise the act-runner `runner` container memory limit from 1Gi to 2Gi; the 30-day peak was 925 MB.
- Public repos are **not** routed to Gitea. super-fr alone ran ~41k minutes in October, and pc-1 cannot absorb that.

## Scope

1. **Onboard derio-net onto Gitea** for its `github-preferred` repos:
   - a Gitea org;
   - a derio-net GitHub App token (`github-app-derio` exists);
   - Tekton push-sync triggers, including PR heads as `sync-pr-<N>`;
   - `apps/tekton/webhooks.yaml` entries;
   - the mirror-reconcile `MAIN_REPOS` / `PR_REPOS` lists, checked by `scripts/tests/test_ci_mirror_resilience.py`;
   - Gitea org secrets and variables.
2. **Generalise the status bridge.** `gitea-status-bridge` filters on `full_name.startsWith('agentic-stoa/')`, so derio-homelab results never reach GitHub. Make it cover all three orgs, with the right token per org.
3. **Budget watcher:**
   - a CronJob on Frank, hourly;
   - per-org tier config (in git);
   - idempotent, with a dry-run mode;
   - flips both forges in the order above;
   - notifies on every flip (alert or issue);
   - an alert when the watcher itself goes stale.
   - On the free plan, GitHub org variables do not apply to private repos, so the GitHub side is **per-repo** variables. The Gitea side can be an org variable.
   - The spec must establish which GitHub App permissions read org billing usage and write repo Actions variables, and whether one App per org is needed.
4. **Monthly review report:** per-repo billed minutes and a proposed tier change per repo. The output target (issue, file or dashboard) is the spec's choice.
5. **Gate coverage check:**
   - Flag any workflow in a `github-preferred` or `gitea-only` repo whose jobs lack the `CI_AUTHORITY` `if:` gate. Known gaps: `release.yml` in cnc-frd and cnc-fru, and most derio-homelab repos.
   - The tiers above cover `macos-*` jobs.
6. **Runner observability on pc-1:**
   - alerts for runner offline, job queue depth or wait, and DinD `/var` usage. pc-1 `/var` has dropped to 19% free, and the DinD emptyDir can grow to 40Gi;
   - the 1Gi to 2Gi memory change.

## Constraints and known risks

- pc-1 is a single point of failure: 4 old cores, and it also hosts Gitea (sqlite), zot and the Tekton sync pods. Today's load is ~2,550 jobs and ~1,300 job-minutes a month, 97.5% idle, with peak concurrency 2 (the capacity). derio-net standby adds roughly 600–1,000 job-minutes a month.
- DinD runs jobs with `network: host` and one shared daemon. Concurrent jobs can collide on ports or container names. Adding derio-net code widens the privileged-DinD trust boundary.
- Mirror lag: webhook push is fast, but mirror-reconcile repair can take 15–25 minutes.
- **Cross-repo consumer (willikins, not this repo):** `scripts/doc-pr ship` merges once `gh pr checks` is green. While Gitea is in charge, GitHub shows only `skipped` jobs at first, so doc-pr could merge before the `gitea-actions/*` statuses arrive. Track the willikins side as a follow-up issue there; this work should expose what doc-pr needs, such as the current authority per repo.

## Current tier proposal (to confirm in the spec)

| Org | Tier | Repos |
|---|---|---|
| derio-net | `github-preferred` | willikins, herdr-vertical-tabs (Linux jobs), presentation-craft, vibe-kanban, runs-fr |
| derio-net | `github-only` | all public repos, plus macOS jobs |
| derio-homelab | `gitea-only` | kid-laptops |
| derio-homelab | `github-preferred` | proxmox-cluster, omada-controller, homelab, ansible-pihole |
| agentic-stoa | `gitea-only` | stays as is |

## References

- `docs/runbooks/manual-operations.yaml` (`cicd-stoa-ci-authority-cutover`)
- `docs/runbooks/frank-gotchas/tekton.md`
- `docs/runbooks/ci-observability.md`
- `docs/superpowers/implemented/specs/2026-07-19--cicd--stoa-full-mirror-gitea-actions-design.md`
- `apps/gitea-runner/manifests/`
- `apps/tekton/triggers/`
- `apps/tekton/manifests/mirror-reconcile.yaml`
- derio-net/willikins#488, derio-net/willikins#489 (decision log entry)

<!-- fr:journal kind=decision scope=spec id=q1-cross-repo-edits created=2026-10-18T14:33:01+00:00 decided_by=operator -->
### q1-cross-repo-edits · decision · Workflow edits in the 9 repos ship in this run via cross-repo agents

Round 1 Q1: chosen 'Cross-repo agents now' over Frank-only + filed issues. One agent per repo, one PR per repo (R17).

decider: operator (AskUserQuestion, fr-goal brainstorm gate)

<!-- fr:journal kind=decision scope=spec id=q2-check-jobs-only created=2026-10-18T14:33:01+00:00 decided_by=operator -->
### q2-check-jobs-only · decision · Only check jobs fall back to Gitea

Round 1 Q2: 'Check jobs only' (recommended). Release/deploy/publish/auto-tag/acceptance-report and macOS jobs stay GitHub-only (R2).

decider: operator (AskUserQuestion, fr-goal brainstorm gate)

<!-- fr:journal kind=decision scope=spec id=q3-homelab-onboarding created=2026-10-18T14:33:01+00:00 decided_by=operator -->
### q3-homelab-onboarding · decision · Onboard the 4 derio-homelab github-preferred repos too

Round 1 Q3: 'Yes, same as derio-net' (recommended) (R5).

decider: operator (AskUserQuestion, fr-goal brainstorm gate)

<!-- fr:journal kind=decision scope=spec id=q4-app-identity created=2026-10-18T14:33:01+00:00 decided_by=operator -->
### q4-app-identity · decision · Extend the existing per-org GitHub Apps

Round 1 Q4: 'Extend existing per-org Apps' (recommended); watcher token scoped down per org.

decider: operator (AskUserQuestion, fr-goal brainstorm gate)

<!-- fr:journal kind=decision scope=spec id=q5-notify created=2026-10-18T14:33:01+00:00 decided_by=operator -->
### q5-notify · decision · Telegram direct + Grafana heartbeat dead-man

Round 1 Q5: crowdsec-canary pattern (recommended) (R13).

decider: operator (AskUserQuestion, fr-goal brainstorm gate)

<!-- fr:journal kind=decision scope=spec id=q6-report-target created=2026-10-18T14:33:01+00:00 decided_by=operator -->
### q6-report-target · decision · Monthly report is a GitHub issue in derio-net/frank

Round 1 Q6: recommended option (R15).

decider: operator (AskUserQuestion, fr-goal brainstorm gate)

<!-- fr:journal kind=decision scope=spec id=q7-backstop created=2026-10-18T14:33:01+00:00 decided_by=operator -->
### q7-backstop · decision · Backstop by 10-minute polling, no new webhooks

Round 1 Q7: 'Poll every 10 min' (recommended); billing poll stays hourly (R12).

decider: operator (AskUserQuestion, fr-goal brainstorm gate)

<!-- fr:journal kind=decision scope=spec id=q8-verification created=2026-10-18T14:33:01+00:00 decided_by=operator -->
### q8-verification · decision · Verification: CI tests pre-merge + live post-merge, gate devops

Round 1 Q8: recommended; recorded in the spec's ## Verification.

decider: operator (AskUserQuestion, fr-goal brainstorm gate)

<!-- fr:journal kind=decision scope=spec id=r2q1-readonly-secrets created=2026-10-18T14:33:01+00:00 decided_by=operator -->
### r2q1-readonly-secrets · decision · Read-only secrets may be mirrored to Gitea for check jobs

Round 2 Q1 (behind Q2 + vibe-kanban test.yml VK_PRIVATE_DEPLOY_KEY): 'Read-only secrets go to Gitea' (recommended) (R3).

decider: operator (AskUserQuestion, fr-goal brainstorm gate)

<!-- fr:journal kind=decision scope=spec id=r2q2-agent-pr-scope created=2026-10-18T14:33:01+00:00 decided_by=operator -->
### r2q2-agent-pr-scope · decision · Agent PRs: 9 github-preferred repos + cnc-frd/cnc-fru release.yml

Round 2 Q2 (behind Q1 + the known stoa release.yml gap): chose '9 + cnc-frd/cnc-fru release.yml' — 11 PRs (R17).

decider: operator (AskUserQuestion, fr-goal brainstorm gate)

<!-- fr:journal kind=decision scope=spec id=r2q3-go-live created=2026-10-18T14:33:01+00:00 decided_by=operator -->
### r2q3-go-live · decision · Watcher ships dry-run; a git change turns it live

Round 2 Q3 (behind Q1: repo PRs merge independently): recommended (R10, manual op cicd-ci-budget-go-live).

decider: operator (AskUserQuestion, fr-goal brainstorm gate)

<!-- fr:journal kind=decision scope=spec id=r2q4-admin-read created=2026-10-18T14:33:01+00:00 decided_by=operator -->
### r2q4-admin-read · decision · Accept org Administration:read via a separately scoped generator

Round 2 Q4 (behind Q4 + finding that ESO scopes per ClusterGenerator): recommended (spec §4 Tokens).

decider: operator (AskUserQuestion, fr-goal brainstorm gate)

<!-- fr:journal kind=decision scope=spec id=gate-question-rounds-brainstorm created=2026-10-18T14:33:06+00:00 -->
### gate-question-rounds-brainstorm · decision · Operator gate `brainstorm` took two question rounds

Trigger: design-risk. Round 1 chose cross-repo agents and check-only fallback; code check found secret-using check jobs, a just-gated kid-laptops, the ungated stoa release.yml and per-generator ESO scoping, each needing an operator decision.

<!-- fr:journal kind=finding scope=spec id=sr-r1-1 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-1 · finding [open] (reviewer: in scope) · Gitea-side authority is one org variable shared with gitea-only/refused repos

See reviewer return (spec-review-r1).

<!-- fr:journal kind=finding scope=spec id=sr-r1-2 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-2 · finding [open] (reviewer: in scope) · Watcher token permission set has a wrong key and lacks permissions

See reviewer return (spec-review-r1).

<!-- fr:journal kind=finding scope=spec id=sr-r1-3 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-3 · finding [open] (reviewer: in scope) · Monthly report's token cannot read what the report must contain

See reviewer return (spec-review-r1).

<!-- fr:journal kind=finding scope=spec id=sr-r1-4 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-4 · finding [open] (reviewer: in scope) · Mirror tokens lack pull_requests:read

See reviewer return (spec-review-r1).

<!-- fr:journal kind=finding scope=spec id=sr-r1-5 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-5 · finding [open] (reviewer: in scope) · Test Plan 4 is unreachable under the month stamp; no single-repo live mode

See reviewer return (spec-review-r1).

<!-- fr:journal kind=finding scope=spec id=sr-r1-6 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-6 · finding [open] (reviewer: in scope) · Edge-triggered notifications and hourly cadence need state

See reviewer return (spec-review-r1).

<!-- fr:journal kind=finding scope=spec id=sr-r1-7 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-7 · finding [open] (reviewer: in scope) · 'PR close deletes the ref' is false

See reviewer return (spec-review-r1).

<!-- fr:journal kind=finding scope=spec id=sr-r1-8 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-8 · finding [open] (reviewer: in scope) · Reconcile/delivery-check extension under-specified

See reviewer return (spec-review-r1).

<!-- fr:journal kind=finding scope=spec id=sr-r1-9 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-9 · finding [open] (reviewer: in scope) · Manual ops omit stoa-bot write, has_actions, Gitea admin scope

See reviewer return (spec-review-r1).

<!-- fr:journal kind=finding scope=spec id=sr-r1-10 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-10 · finding [open] (reviewer: in scope) · Gate convention cannot express mixed macOS/Linux matrices; GITHUB_TOKEN exemption unsafe

See reviewer return (spec-review-r1).

<!-- fr:journal kind=finding scope=spec id=sr-r1-11 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-11 · finding [open] (reviewer: in scope) · Authority gate on cnc-frd/cnc-fru release.yml would move CNC releases to Gitea

See reviewer return (spec-review-r1).

<!-- fr:journal kind=finding scope=spec id=sr-r1-12 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-12 · finding [open] (reviewer: in scope) · Several requirements/live rows have no Test Plan step

See reviewer return (spec-review-r1).

<!-- fr:journal kind=finding scope=spec id=sr-r1-13 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-13 · finding [open] (reviewer: in scope) · Month-boundary and timezone edge cases

See reviewer return (spec-review-r1).

<!-- fr:journal kind=finding scope=spec id=sr-r1-14 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-14 · finding [open] (reviewer: in scope) · The remaining 15% must still carry GitHub-pinned jobs

See reviewer return (spec-review-r1).

<!-- fr:journal kind=finding scope=spec id=sr-r1-15 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-15 · finding [open] (reviewer: in scope) · Backstop re-run narrows the brief

See reviewer return (spec-review-r1).

<!-- fr:journal kind=finding scope=spec id=sr-r1-16 created=2026-10-18T14:43:00+00:00 state=open review_scope=in -->
### sr-r1-16 · finding [open] (reviewer: in scope) · Gap 2 overstates gitea-push double-run risk

See reviewer return (spec-review-r1).

<!-- fr:journal kind=review scope=spec id=spec-review-r1 created=2026-10-18T14:43:00+00:00 -->
### spec-review-r1 · review · independent spec review: 16 findings, all in scope

Dispatched fr-spec-reviewer read-only into the workspace. It verified every cited file:line and the 12 operator decisions, and raised 16 in-scope findings: shared org authority variable; token permissions; report tokens; pull_requests:read; unreachable Test Plan 4; stateless notifications; false PR-close claim; under-specified reconcile/delivery extension; missing manual-op prerequisites; matrix/GITHUB_TOKEN gaps in the convention; release.yml gate choice; missing Test Plan rows; UTC month boundary; pinned-job budget risk; backstop narrowing; overstated gap 2. All were fixed in the spec.

<!-- fr:journal kind=finding scope=spec id=sr-r1-1-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-1 -->
### sr-r1-1-resolved · finding [fixed] · resolves sr-r1-1: Gitea-side authority is one org variable shared with gitea-only/refused repos

Authority is now a per-repo Gitea variable for github-preferred repos; org variables are never written for authority, so kid-laptops is unaffected and refusals hold on both forges (§4 step 6, R9, R11). Repo-over-org precedence is a [PRE-MERGE] op (cicd-gitea-variable-semantics).

<!-- fr:journal kind=finding scope=spec id=sr-r1-2-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-2 -->
### sr-r1-2-resolved · finding [fixed] · resolves sr-r1-2: Watcher token permission set has a wrong key and lacks permissions

Two generators per org: ci-billing (organization_administration:read) for all three orgs and ci-authority (variables:write, actions/checks/contents:read) for derio-net and derio-homelab; stoa has no authority generator. Live billing read with an App installation token is a [PRE-MERGE] gate (cicd-ci-budget-app-permissions).

<!-- fr:journal kind=finding scope=spec id=sr-r1-3-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-3 -->
### sr-r1-3-resolved · finding [fixed] · resolves sr-r1-3: Monthly report's token cannot read what the report must contain

§5 lists every token the report uses; the repo list comes from billing line items, visibility from the ci-authority token, and stoa workflow files from stoa-github-mirror.

<!-- fr:journal kind=finding scope=spec id=sr-r1-4-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-4 -->
### sr-r1-4-resolved · finding [fixed] · resolves sr-r1-4: Mirror tokens lack pull_requests:read

pull_requests:read added to github-app-derio-mirror and to homelab-fr-automation in the manual op.

<!-- fr:journal kind=finding scope=spec id=sr-r1-5-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-5 -->
### sr-r1-5-resolved · finding [fixed] · resolves sr-r1-5: Test Plan 4 is unreachable under the month stamp; no single-repo live mode

Added per-org mode and per-repo pin_authority (a pin never stamps the month); Test Plan 4 uses the pin, and Test Plan 5 tests the month lock by back-dating the stamp.

<!-- fr:journal kind=finding scope=spec id=sr-r1-6-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-6 -->
### sr-r1-6-resolved · finding [fixed] · resolves sr-r1-6: Edge-triggered notifications and hourly cadence need state

Added the ci-budget-state ConfigMap (last billing read, sent notification keys, handled backstop runs); notifications are keyed per event and month.

<!-- fr:journal kind=finding scope=spec id=sr-r1-7-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-7 -->
### sr-r1-7-resolved · finding [fixed] · resolves sr-r1-7: 'PR close deletes the ref' is false

Claim removed; pre-existing accumulation of sync-pr refs is now stated in Context and Risks.

<!-- fr:journal kind=finding scope=spec id=sr-r1-8-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-8 -->
### sr-r1-8-resolved · finding [fixed] · resolves sr-r1-8: Reconcile/delivery-check extension under-specified

§2 now lists the push-stage token, the delivery-check token mount and widened :85 status comparison, the corrected :404-408 cite, and every guard extended, including the kid-laptops trigger-name pin.

<!-- fr:journal kind=finding scope=spec id=sr-r1-9-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-9 -->
### sr-r1-9-resolved · finding [fixed] · resolves sr-r1-9: Manual ops omit stoa-bot write, has_actions, Gitea admin scope

Added to cicd-derio-net-gitea-org / cicd-github-preferred-gitea-mirrors; a separate read:admin probe token for runner listing.

<!-- fr:journal kind=finding scope=spec id=sr-r1-10-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-10 -->
### sr-r1-10-resolved · finding [fixed] · resolves sr-r1-10: Gate convention cannot express mixed macOS/Linux matrices; GITHUB_TOKEN exemption unsafe

Mixed matrices are split into two jobs; the checker flags expression-valued runs-on, unmirrored secrets, and GITHUB_TOKEN used against GitHub in gated jobs.

<!-- fr:journal kind=finding scope=spec id=sr-r1-11-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-11 -->
### sr-r1-11-resolved · finding [fixed] · resolves sr-r1-11: Authority gate on cnc-frd/cnc-fru release.yml would move CNC releases to Gitea

release.yml jobs take the GitHub pin, per the spec's mutating-job rule; today's release and cnc-image-ready promotion behaviour is kept, and the duplicate Gitea run stops.

<!-- fr:journal kind=finding scope=spec id=sr-r1-12-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-12 -->
### sr-r1-12-resolved · finding [fixed] · resolves sr-r1-12: Several requirements/live rows have no Test Plan step

Test Plan expanded to 10 steps covering R4-R19 for every live row; `none` rows are covered by CI.

<!-- fr:journal kind=finding scope=spec id=sr-r1-13-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-13 -->
### sr-r1-13-resolved · finding [fixed] · resolves sr-r1-13: Month-boundary and timezone edge cases

All months are UTC; backstop hits from runs created before the current month's start are ignored.

<!-- fr:journal kind=finding scope=spec id=sr-r1-14-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-14 -->
### sr-r1-14-resolved · finding [fixed] · resolves sr-r1-14: The remaining 15% must still carry GitHub-pinned jobs

Added to Risks; flip notifications and the monthly report (R15) show the GitHub-pinned share.

<!-- fr:journal kind=finding scope=spec id=sr-r1-15-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-15 -->
### sr-r1-15-resolved · finding [fixed] · resolves sr-r1-15: Backstop re-run narrows the brief

Default-branch commits are now re-run too, via a sync-rerun-<sha12> Gitea branch and sync-rerun-** push triggers; Gitea branch-create firing Actions is a [PRE-MERGE] op.

<!-- fr:journal kind=finding scope=spec id=sr-r1-16-resolved created=2026-10-18T14:43:00+00:00 state=fixed resolves=sr-r1-16 -->
### sr-r1-16-resolved · finding [fixed] · resolves sr-r1-16: Gap 2 overstates gitea-push double-run risk

Gap 2 reworded: not a live bug; the exclusion is defence in depth.

<!-- fr:journal kind=decision scope=spec id=exit-baseline created=2026-10-18T14:43:01+00:00 -->
### exit-baseline · decision · exit when spec-review resolved

The exit when spec-review resolved; `fr verification set` and `deliver` compare against it.

```yaml
row_gates:
  ci-authority-readable-on-github: devops
  ci-budget-backstop-spending-limit: devops
  ci-budget-flips-at-threshold: devops
  ci-budget-notifies-and-heartbeat: devops
  ci-fallback-mirrors-derio-orgs: devops
  ci-fallback-status-reaches-github: devops
  ci-tier-monthly-report: devops
  gate-coverage-checker-flags-gaps: none
  runner-health-alerts: devops
  runner-memory-and-placement: none
  tier-config-declares-repo-tiers: none
  workflows-carry-forge-gates: devops
row_kinds:
  ci-authority-readable-on-github: live
  ci-budget-backstop-spending-limit: live
  ci-budget-flips-at-threshold: live
  ci-budget-notifies-and-heartbeat: live
  ci-fallback-mirrors-derio-orgs: live
  ci-fallback-status-reaches-github: live
  ci-tier-monthly-report: live
  gate-coverage-checker-flags-gaps: none
  runner-health-alerts: live
  runner-memory-and-placement: none
  tier-config-declares-repo-tiers: none
  workflows-carry-forge-gates: live
run_gate: devops
run_kind: live
```

<!-- fr:journal kind=decision scope=spec id=phase-split-2026-10-18--cicd--github-preferred-gitea-fallback-p2 created=2026-10-18T14:47:05+00:00 -->
### phase-split-2026-10-18--cicd--github-preferred-gitea-fallback-p2 · decision · ask: mirroring derio-net/derio-homelab and the three-org status bridge (R4-R6) is reviewable on its own

<!-- fr:journal kind=decision scope=spec id=phase-split-2026-10-18--cicd--github-preferred-gitea-fallback-p3 created=2026-10-18T14:47:08+00:00 -->
### phase-split-2026-10-18--cicd--github-preferred-gitea-fallback-p3 · decision · ask: the budget watcher (R7-R14) is the core fallback ask

<!-- fr:journal kind=decision scope=spec id=phase-split-2026-10-18--cicd--github-preferred-gitea-fallback-p4 created=2026-10-18T14:47:11+00:00 -->
### phase-split-2026-10-18--cicd--github-preferred-gitea-fallback-p4 · decision · ask: the monthly tier-review report (R15) is a separate ask in the brief

<!-- fr:journal kind=decision scope=spec id=phase-split-2026-10-18--cicd--github-preferred-gitea-fallback-p5 created=2026-10-18T14:47:13+00:00 -->
### phase-split-2026-10-18--cicd--github-preferred-gitea-fallback-p5 · decision · ask: runner memory and runner/pc-1 observability (R18-R19) is its own ask

<!-- fr:journal kind=discovery scope=spec id=test-plan-step-1 created=2026-10-19T17:09:45+00:00 -->
### test-plan-step-1 · discovery · Test Plan step 1: ran

Step: **Mirrors (R4, R5).** After the manual ops: push to a PR in one derio-net and one derio-homelab repo; the Gitea mirror shows `sync-pr-<N>` at the PR head sha; `mirror-reconcile` and `ci-delivery-check` logs list the new repos with no read errors.

Evidence: 2026-10-19: ci-budget-ops status gitea-mirrors 0 open (all 9 mirrors, CI_AUTHORITY var, default branch in sync). Probe PR derio-net/herdr-vertical-tabs#17: Gitea ran Actions at the PR head and gitea-actions/* statuses appeared on GitHub. derio-homelab open PRs (homelab 36/38, omada 41/53, proxmox 109, ansible-pihole 14) mirrored as sync-pr-N by mirror-reconcile after stoa-bot got write (#889): repaired=6 plan_errors=0. ci-delivery-check no longer reports read-error (fixed by #888/#889); it still reports status-delivery mismatches on pre-existing commits.

<!-- fr:journal kind=owed scope=spec id=test-plan-step-2 created=2026-10-19T17:09:48+00:00 -->
### test-plan-step-2 · owed · Test Plan step 2 owed

what: **Statuses (R6).** On a repo whose authority is hand-pinned to `gitea` (`pin_authority: gitea`, org `mode: live`): the PR shows `gitea-actions/*` statuses with real durations on GitHub, its gated GitHub check jobs show `skipped`, and mutating and `macos-*` jobs still run on GitHub.
why: No repo is hand-pinned to gitea / org mode live yet. Forwarding itself was observed in authority=github mode (probe PR: gitea-actions/* incl. 'Gitea: skipped' mapped to success), but the pinned-authority check (real durations, gated GitHub jobs skipped, macos-* still on GitHub) needs the live flip of step 4.
how: fr journal resolve --scope spec --slug 2026-10-18--cicd--github-preferred-gitea-fallback --id test-plan-step-2 --state fixed --note "<evidence>"
owed_key: spec:2026-10-18--cicd--github-preferred-gitea-fallback#step2

<!-- fr:journal kind=owed scope=spec id=test-plan-step-3 created=2026-10-19T17:09:51+00:00 -->
### test-plan-step-3 · owed · Test Plan step 3 owed

what: **Watcher dry-run (R7, R10, R13).** All orgs in dry-run against the live billing APIs: the heartbeat shows each org's `pct`; an org over threshold produces exactly one would-flip message across at least three runs.
why: Watcher runs every 10 min in dry-run and logs per-org verdicts (derio-net would-flip pct=97.7, derio-homelab refused pct=91.0, agentic-stoa ok pct=5.2); not yet checked that exactly one would-flip MESSAGE is sent across >=3 runs, nor why derio-homelab is refused.
how: fr journal resolve --scope spec --slug 2026-10-18--cicd--github-preferred-gitea-fallback --id test-plan-step-3 --state fixed --note "<evidence>"
owed_key: spec:2026-10-18--cicd--github-preferred-gitea-fallback#step3

<!-- fr:journal kind=owed scope=spec id=test-plan-step-4 created=2026-10-19T17:09:54+00:00 -->
### test-plan-step-4 · owed · Test Plan step 4 owed

what: **Live flip, one repo (R8, R9, R14).** Set `pin_authority: gitea` on one repo in a live org: the watcher writes Gitea then GitHub, read-backs pass, `gh variable get CI_AUTHORITY` returns `gitea`. Remove the pin (the org is below threshold and the pin did not stamp the month): GitHub then Gitea return to `github`, and `gh variable get` returns `github`. The org's other repos and kid-laptops are untouched throughout.
why: Live flip changes CI_AUTHORITY on real repos; needs operator go-ahead. Urgent: GitHub already refuses derio-net jobs ('recent account payments have failed or your spending limit needs to be increased', seen on probe PR) while the watcher is still dry-run.
how: fr journal resolve --scope spec --slug 2026-10-18--cicd--github-preferred-gitea-fallback --id test-plan-step-4 --state fixed --note "<evidence>"
owed_key: spec:2026-10-18--cicd--github-preferred-gitea-fallback#step4

<!-- fr:journal kind=owed scope=spec id=test-plan-step-5 created=2026-10-19T17:09:57+00:00 -->
### test-plan-step-5 · owed · Test Plan step 5 owed

what: **Month lock (R8).** Set the Gitea org variable `CI_BUDGET_MONTH` to the previous month on an org at `gitea`: the next run returns the org's repos to `github`.
why: Needs an org at gitea (depends on step 4) and a Gitea org variable edit; operator-gated.
how: fr journal resolve --scope spec --slug 2026-10-18--cicd--github-preferred-gitea-fallback --id test-plan-step-5 --state fixed --note "<evidence>"
owed_key: spec:2026-10-18--cicd--github-preferred-gitea-fallback#step5

<!-- fr:journal kind=owed scope=spec id=test-plan-step-6 created=2026-10-19T17:10:00+00:00 -->
### test-plan-step-6 · owed · Test Plan step 6 owed

what: **Backstop (R12).** Replay a captured spending-limit annotation through the watcher's detector against a live repo (fixture injected via the watcher's test hook, dry-run off for a single org): the org flips, `sync-rerun-<sha12>` appears on Gitea, Gitea Actions runs at that sha, and its status lands on the GitHub commit.
why: Needs dry-run off for a single org and a captured spending-limit annotation; one real annotation is now available (herdr-vertical-tabs#17 check runs). Operator-gated.
how: fr journal resolve --scope spec --slug 2026-10-18--cicd--github-preferred-gitea-fallback --id test-plan-step-6 --state fixed --note "<evidence>"
owed_key: spec:2026-10-18--cicd--github-preferred-gitea-fallback#step6

<!-- fr:journal kind=owed scope=spec id=test-plan-step-7 created=2026-10-19T17:10:04+00:00 -->
### test-plan-step-7 · owed · Test Plan step 7 owed

what: **Heartbeat (R13).** Suspend the CronJob for 45 minutes: `ci-budget-heartbeat-stale` fires; resume it and it resolves.
why: Suspending the CronJob 45 min is an operator-approved window; not done.
how: fr journal resolve --scope spec --slug 2026-10-18--cicd--github-preferred-gitea-fallback --id test-plan-step-7 --state fixed --note "<evidence>"
owed_key: spec:2026-10-18--cicd--github-preferred-gitea-fallback#step7

<!-- fr:journal kind=owed scope=spec id=test-plan-step-8 created=2026-10-19T17:10:07+00:00 -->
### test-plan-step-8 · owed · Test Plan step 8 owed

what: **Report (R15).** `kubectl create job --from=cronjob/ci-budget-report` twice: the `CI tier review` issue appears once and is edited the second time.
why: Creates the CI tier review GitHub issue; not run without operator approval.
how: fr journal resolve --scope spec --slug 2026-10-18--cicd--github-preferred-gitea-fallback --id test-plan-step-8 --state fixed --note "<evidence>"
owed_key: spec:2026-10-18--cicd--github-preferred-gitea-fallback#step8

<!-- fr:journal kind=owed scope=spec id=test-plan-step-9 created=2026-10-19T17:10:11+00:00 -->
### test-plan-step-9 · owed · Test Plan step 9 owed

what: **Repo PRs (R17).** After the eleven PRs merge, run the checker against each default branch: every job is `ok`.
why: Checker is not all-ok: read-errors fixed, but status-delivery-mismatch lines remain on pre-existing backfill commits across 9 repos plus kid-laptops; needs a fresh-commit re-check once they are superseded.
how: fr journal resolve --scope spec --slug 2026-10-18--cicd--github-preferred-gitea-fallback --id test-plan-step-9 --state fixed --note "<evidence>"
owed_key: spec:2026-10-18--cicd--github-preferred-gitea-fallback#step9

<!-- fr:journal kind=owed scope=spec id=test-plan-step-10 created=2026-10-19T17:10:14+00:00 -->
### test-plan-step-10 · owed · Test Plan step 10 owed

what: **Runner (R18, R19).** The runner pod runs with a 2Gi limit on pc-1; the `ci-runner-probe` line shows `runners_online ≥ 1`; scale the runner to 0 for 15 minutes and `layer-25-runner-offline` fires (then restore); query the pc-1 `/var` series in VMUI and confirm `layer-25-pc1-var-low` evaluates against real data; with real `ci-runner-probe` lines present, run the queue-wait LogsQL in VMUI and confirm it yields a numeric `oldest_waiting_s`; revoke nothing, but confirm a missing probe token produces `ci-runner-probe-error` lines and `layer-25-runner-probe-blind` evaluates against them.
why: Verified: runner pod 2Gi limit on pc-1, ci-runner-probe runners_online=1. Not done: scale-to-0 offline alert, pc-1 /var rule on real data, queue-wait LogsQL on real probe lines, probe-error path. Queue-wait signal was real: 54 jobs / 9h stuck from vibe-kanban tag runs (cleared).
how: fr journal resolve --scope spec --slug 2026-10-18--cicd--github-preferred-gitea-fallback --id test-plan-step-10 --state fixed --note "<evidence>"
owed_key: spec:2026-10-18--cicd--github-preferred-gitea-fallback#step10

<!-- fr:journal kind=finding scope=spec id=7edebd205cc1 created=2026-10-19T17:33:10+00:00 state=fixed -->
### 7edebd205cc1 · finding [fixed] · Test Plan evidence added after #891 (outcomes are immutable once recorded)

Step 8 RAN 2026-10-19 17:27-17:29Z (recorded owed earlier): two ci-budget-report jobs -> 'issue=504 failed=0'; willikins#504 'CI tier review 2026-09' created 17:27:28Z, edited 17:28:27Z, only one exists. Step 3: verdicts every 10 min for all orgs; derio-homelab would-flip 91.4 (earlier 'refused' = stale gate gaps, cleared once the gate PRs merged); would-flip MESSAGE unverifiable: ci-budget-telegram Secret absent, notifier disabled, state.sent empty. Step 10: pc-1 /var series live (0.449), queue-wait LogsQL numeric on real probe lines. P6.T1.S2 gitea-semantics re-proven 2026-10-19T17:31:22Z (repo-wins=success, org-wins=skipped, sync-rerun push + paths-filtered run=success); probe repo deleted (404).

<!-- fr:journal kind=finding scope=spec id=43434a81aaae created=2026-10-19T19:32:35+00:00 state=fixed -->
### 43434a81aaae · finding [fixed] · Go-live derio-net (#892) and Test Plan evidence 2-6

2026-10-19 after #892: ArgoCD synced ci-budget at the merge commit (hard refresh needed; status.sync.revision lagged one commit), ExternalSecret ci-budget-telegram SecretSynced, 19:20Z tick verdict=flipped derio-net mode=live. Step 4 (flip half): CI_AUTHORITY=gitea on all five derio-net repos on BOTH forges (gh variable get + Gitea API); derio-homelab untouched (GitHub var absent, Gitea=github), kid-laptops untouched (gitea-only). 9 Telegram messages recorded in state.sent (5 flip: keys, 4 would-flip homelab) and not repeated on later ticks (step 3 once-only now observed). Step 4 (pin/return half) and step 5 are NOT exercisable while derio-net is above threshold: desired_authority returns gitea and re-stamps when pct>=threshold regardless of CI_BUDGET_MONTH; the return-to-github path is covered by unit tests only (test_desired_authority). CI_BUDGET_MONTH=2026-10 on the derio-net Gitea org. Step 2: probe PR herdr-vertical-tabs#18 (closed): gitea-actions/ci / test-linux 'Successful in 2m3s' on GitHub, GitHub test-linux skipped, test-macos still queued on GitHub. Step 6: organic, not replayed: the probe PRs' GitHub 'spending limit' failures were picked up at the 19:30Z tick (handled 16->20, four backstop: keys sent), sync-rerun-70e230abd54f and sync-rerun-decab6d4f0d4 created on Gitea, Gitea Actions ran at those shas (runs 7670-7675) and gitea-actions/* statuses landed on the GitHub commit. OPEN DEFECT: Gitea twin of a macos-* job (herdr-vertical-tabs ci / test-macos) stays 'Waiting to run' forever (label unserved, so its job-level if is never evaluated): a permanent pending gitea-actions status on every PR and a ci.yml run that never completes.
