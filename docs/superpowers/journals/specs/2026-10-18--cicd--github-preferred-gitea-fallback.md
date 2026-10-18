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
