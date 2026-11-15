# kid-laptops mirror: PR heads, a repair alert, and the pull-sync that "never succeeded"

**Layer:** cicd (fix/extension of the GitHub→Gitea mirror)
**Issues:** derio-net/frank#952, derio-net/frank#850, derio-net/frank#798 (batch `kid-laptops-mirror`)
**Date:** 2026-11-15

## Context

Every derio-homelab repo is mirrored from GitHub into Gitea by `derio-homelab-pull-sync`
(`apps/tekton/pipelines/derio-homelab-pull-sync.yaml`). The path has two triggers on the
github-listener (`apps/tekton/triggers/eventlistener-github.yaml`): `derio-homelab-main-sync`,
which covers all five repos, and `derio-homelab-pr-sync`, which covers four of them.
kid-laptops is the exception: it is mirrored on `main` only. `mirror-reconcile`
(`apps/tekton/manifests/mirror-reconcile.yaml`) repairs any drift every 15 minutes, and
`ci-delivery-check` (`apps/tekton/manifests/ci-delivery-check.yaml`) compares mirror refs
and forwarded statuses every 5 minutes.

The three issues are one pipeline seen from three sides:

- **#952**: kid-laptops PR heads are not mirrored, so its Gitea Actions molecule cannot
  report on PRs.
- **#850**: a `mirror-reconcile` repair is the only trace of an event the webhook path
  dropped, and nothing alerts on it.
- **#798**: `derio-homelab-pull-sync` was recorded at 24 failures and 0 successes on
  2026-09-13.

## Findings (brainstorm, 2026-11-14/15)

**#798 is already fixed at the root.** That failure count was the zero-byte-loose-object
corruption in Gitea's `kid-laptops.git`, which #859 repaired on 2026-10-13 (see
`frank-gotchas.md`, Tekton section). VictoriaLogs retains pod logs from 2026-10-18 onward.
In that window, **every one of the 9 kid-laptops `main` commits** was pushed by a pull-sync
PipelineRun that ended `OK`:

- 5c096b5, c23b02f, ba8615a, 82afee5 on 2026-10-18, under the old `kid-laptops-main-sync-*` name
- 5239384, 9cdd393, 064e944, 8dea86f, ada3141 on 2026-11-02/03, as `derio-homelab-main-sync-*`

Gitea `main` equals GitHub `main` (ada3141). No `mirror-reconcile repaired …kid-laptops`
line exists in the window. Tekton PipelineRuns do not survive the 7-day TTL, so this evidence
comes from VictoriaLogs pod logs, not from PipelineRun objects. The detection half of #798 also landed, via #797's
`layer-25-pipeline-failing`. It groups by *pipeline*, though, and five repos share this
pipeline, so a kid-laptops-only failure would be masked by the other repos' successes.
#850's per-repo repair alert is that per-repo signal. A failing sync is repaired within
roughly 25 minutes, and each repair is logged against the repo. The alert fires on the
*second* repair within 6h. One isolated repair (a single dropped commit) is tolerated by
design (operator decision q3), so the signal catches a recurring per-repo loss, not every
single drop.

**The repo side of #952 is not on kid-laptops `main` yet.** The `push: sync-pr-**` trigger
exists only on draft derio-homelab/kid-laptops#139. Until #139 merges, a mirrored
`sync-pr-<N>` starts no molecule. `ci-delivery-check` treats an absent status as healthy
(path-filtered CI), so merging this change first is harmless. The weekly molecule run on
Gitea already failed on 2026-11-09 with an unexpanded `${{ matrix.role }}` job, which is
the dynamic-matrix limitation #139 removes.

**Second-hop fan-out.** The Gitea-side `kid-laptops-push` trigger
(`apps/tekton/triggers/eventlistener.yaml`, around line 177) has no ref filter. Once PR heads
are mirrored, every `sync-pr-<N>` push would also start a Tekton `kid-laptops-ci` run.

**Load.** pc-1 `/var` has 13 GiB free of 57. The DinD `emptyDir` (sizeLimit 40Gi) lives
there. #824 is still open and puts pc-1's HDDs into Longhorn, which does not relieve `/var`
directly. `layer-25-pc1-var-low` already guards `/var`.

## Requirements

R1. A same-repo derio-homelab/kid-laptops pull request that is opened, synchronized or reopened is force-pushed to Gitea as `refs/heads/sync-pr-<N>` by the `derio-homelab-pr-sync` trigger; a fork PR never writes a sync-pr ref.
R2. `apps/tekton/webhooks.yaml` declares the kid-laptops GitHub repo hook with events `[push, pull_request]` and `serves: [derio-homelab-main-sync, derio-homelab-pr-sync]`, and a post-merge manual operation adds `pull_request` to the live hook.
R3. `mirror-reconcile` (its `heads` and `plan` initContainers, in sorted position) and `ci-delivery-check` list kid-laptops in `PR_REPOS`, so its open PRs' `sync-pr-<N>` refs are reconciled and delivery-checked.
R4. The Gitea-side `kid-laptops-push` Tekton trigger fires only on pushes to `refs/heads/main`; a `sync-pr-*` or `sync-rerun-*` push starts no Tekton `kid-laptops-ci` run.
R5. A Grafana alert rule fires at severity `warning` when `mirror-reconcile` logs two or more repairs for the same repository within 6 hours; it is evaluated from VictoriaLogs (`queryType: stats`, `_msg`), carries the repository as a label, resolves through NoData (`noDataState: OK`), is routed through the `ci_outcome` 4-hour repeat, and has a runbook that uses `get pipelinerun -A` (the form `test_ci_outcome_alert_repeat.py` requires of `ci_outcome` rules).
R6. The `layer-25-mirror-sync-failing` runbook annotation no longer claims kid-laptops is unreconciled, and names the repair alert as the per-repo signal.
R7. The comments that describe kid-laptops as push-only or main-sync-only describe the new state: `eventlistener-github.yaml:226-228`, the kid-laptops GitHub entry note at `webhooks.yaml:173-175`, and `mirror-reconcile.yaml:11`.
R8. The offline guards encode R1–R5. The three sites that pin kid-laptops out of the PR path are updated: `test_github_preferred_mirrors.py:89-92`, `test_ci_mirror_resilience.py:201-208` and `test_ci_delivery_check.py:143-144`. New assertions fail if the `kid-laptops-push` filter loses its `refs/heads/main` clause (as `test_site_promotion_pipeline.py` does for site), or if the repair rule loses its datasource, `stats by (repo)` grouping, threshold, `noDataState: OK` or `ci_outcome` label (the uid joins `CI_OUTCOME_RULES`).
R9. The operating post `operating/22-cicd-platform` and the building post `building/35-gitea-actions-ci` describe kid-laptops PR mirroring and the repair alert; `frank-gotchas.md` and its Tekton topic file record the shared-pipeline masking of per-pipeline outcome alerts.

## Design

### #952: mirror PR heads (R1–R3, R7)

- `eventlistener-github.yaml`: add `'derio-homelab/kid-laptops'` to the `derio-homelab-pr-sync`
  CEL list. The existing same-repo guard
  (`body.pull_request.head.repo.full_name == body.repository.full_name`) keeps fork code off
  the runner. Rewrite the "kid-laptops is main-sync only" comment block.
- `webhooks.yaml`: change the kid-laptops GitHub hook entry (`target: derio-homelab/kid-laptops`,
  lines 166-178) to events `[push, pull_request]` and
  `serves: [derio-homelab-main-sync, derio-homelab-pr-sync]` (matching the proxmox-cluster
  entry), and update its note.
- `mirror-reconcile.yaml`: add kid-laptops to `PR_REPOS` on both the `heads` and the `plan`
  initContainers (the `push` container carries no repo lists). The test compares a sorted list,
  so it goes between `homelab` and `omada-controller`. Rewrite the header line "kid-laptops has
  a push trigger only…".
  `ci-delivery-check.yaml`: add it to `PR_REPOS`.
- Manual op `cicd-kid-laptops-github-webhook-pull-request` (post-merge): add `pull_request` to
  the live derio-homelab/kid-laptops GitHub webhook, then verify with a delivery. It mirrors
  `cicd-kid-laptops-github-webhook`.
- Runner: no change (operator decision). Capacity stays 2. `layer-25-pc1-var-low` is the
  guard, and the first PR-time molecule run is a Test Plan row.

### Second hop: main-only Tekton (R4)

Add `&& body.ref == 'refs/heads/main'` to the `kid-laptops-push` CEL filter, and record why
in the comment. PR evidence comes only from Gitea Actions molecule, which keeps PR load to
what #952 budgeted. It also means deleting a `sync-pr` ref can never start a run on a
zero SHA.

### #850: repair alert (R5)

The new rule is `layer-25-mirror-repair-recurring`, in group `layer-25-pipeline-outcomes`
(interval 5m) beside `layer-25-mirror-reconcile-stale`. Groups in this file already mix the
Prometheus and VictoriaLogs datasources (`ci-runner-health`, around lines 2980-3090). This is
the first *multi-series* VictoriaLogs rule here, which is why the Test Plan carries a positive
control for it.

- Datasource: VictoriaLogs (`affdoo4s9258gc`), `queryType: stats`, window 6h:
  `kubernetes.namespace_name:tekton-pipelines AND _msg:"mirror-reconcile repaired" | extract "mirror-reconcile repaired <repo> " | stats by (repo) count() as value`
- Reduce `last`, threshold `gt 1` (that is, ≥ 2), `noDataState: OK` (the filter returns
  nothing when nothing was repaired, so NoData is how it resolves), `execErrState: Error`,
  `for: 0s`.
- Labels: `severity: warning`, `ci_outcome: "true"` (4h repeat, Telegram + Health Bridge),
  `github_issue: "frank-ops#25"`.
- Summary names the repo and count. Runbook: a repair means a dropped webhook delivery or a
  sync run that never started. Check the GitHub hook deliveries, then
  `kubectl get pipelinerun -A --sort-by=.metadata.creationTimestamp | grep pull-sync`, then the
  `mirror-reconcile repaired` lines in VictoriaLogs. Never `-n tekton-pipelines`, which
  `test_ci_outcome_alert_repeat.py` refuses.
- Grafana rejects a uid longer than 40 characters. The uid above is 32.

### #798: close on evidence (R6)

No pipeline change. Fix the `layer-25-mirror-sync-failing` runbook text. The diagnosis lives
in this spec's Findings.

### Out of scope, recorded

- 2026-11-01 `derio-homelab-pr-sync-jsd5j` failed with `cannot lock ref 'refs/heads/sync-pr-122':
  reference already exists` (proxmox-cluster): two writers creating the same new ref
  concurrently. Real, and not caused by this change. It will be filed as a follow-up.

## Verification

strategy: live
gate: devops

- kid-laptops-pr-heads-mirrored: live — needs a real kid-laptops PR push through the live GitHub webhook, which exists only after the post-merge manual op.
- mirror-repair-alert: live — the rule evaluates only inside the running Grafana against VictoriaLogs; CI proves its structure.
- kid-laptops-main-sync-healthy: live — the claim concerns the running pull-sync path; evidence is VictoriaLogs pull-sync pod logs (`OK` per kid-laptops main commit) plus Gitea main == GitHub main, because PipelineRuns do not outlive the 7-day TTL.

The structural guards (R8) run in the required CI tripwires on every PR; they are not acceptance rows.

## Test Plan

- post-merge — operator-driven: after the manual op, push to a same-repo kid-laptops PR. `sync-pr-<N>` appears on the Gitea mirror at the PR head SHA, and no Tekton `kid-laptops-ci` PipelineRun is created for it.
- post-merge — operator-driven: once kid-laptops#139 has merged, the PR head on GitHub shows `gitea-actions/molecule / molecule (push)`. Watch pc-1 `/var` and the DinD sidecar during the first full run (systemd containers have not run in this DinD before).
- post-merge — operator-driven: `mirror-reconcile` and `ci-delivery-check` logs list the kid-laptops `sync-pr-<N>` ref.
- post-merge — operator-driven: positive control for the repair rule. Run its exact LogsQL in Grafana Explore against VictoriaLogs over a window that contains real `mirror-reconcile repaired` lines (e.g. 2026-10-19T15:00Z–16:00Z, when homelab and omada-controller each had two). It must return one series per repo, carrying a `repo` label and the expected count. Only then is "loaded and Normal, no series" today meaningful.
- post-merge — operator-driven: positive control for R4. The next kid-laptops `main` push (or a repair of `main`) still creates a `kid-laptops-ci` PipelineRun in namespace `kid-laptops-ci`.
- post-merge — operator-driven: main-sync health. For each kid-laptops `main` commit since merge, VictoriaLogs shows a pull-sync pod pushing it and ending `OK`, and Gitea `main` equals GitHub `main`.
