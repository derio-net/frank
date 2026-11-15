<!-- fr:journal-schema=4 -->
# Journal: 2026-11-15--cicd--kid-laptops-mirror-pr-heads

<!-- fr:journal kind=discovery scope=spec id=operator-brief created=2026-11-15T06:04:01+00:00 input=true -->
### operator-brief · discovery · Operator brief (batch kid-laptops-mirror), verbatim

/fr-goal cicd: PR heads mirrored to Gitea, a repair alert, and why pull-sync never succeeded

Batch `kid-laptops-mirror` of derio-net/frank: 3 issues, delivered as ONE pull request.

## frank#952: cicd: mirror kid-laptops PR heads to Gitea (sync-pr), now that its molecule runs in Gitea Actions
Still push-only on main: the `derio-homelab-pr-sync` CEL filter (`apps/tekton/triggers/eventlistener-github.yaml:246`) omits kid-laptops and `mirror-reconcile.yaml:11` keeps it out of `PR_REPOS`. First run also tests systemd containers in the DinD sidecar.
Note: Manual op after merge: add `pull_request` to the live GitHub webhook. Watch runner load (up to 13 privileged jobs per run).

## frank#850: obs: alert when mirror-reconcile repairs drift — a repair means the webhook path silently dropped an event
mirror-reconcile repairs GitHub->Gitea drift every 15 min; a repair means the webhook path dropped an event, yet the Job stays green and only a log line records it. Follow-up of the mirror-resilience fix (PR frank#851).

## frank#798: cicd: derio-homelab-pull-sync (kid-laptops mirror) has never succeeded — 24 runs, 0 successes
24 failures, 0 successes from controller counters (live). Two problems: the sync itself, and that no rule alerts on pipeline outcome (frank#790 family).

## Why these belong together
One mirror pipeline. Start by reading the failing pull-sync run logs (#798) before designing anything; #913 is merged.

## Delivery rules
- Work on branch `feat/batch-kid-laptops-mirror`.
- Open a draft PR as soon as the spec is committed. Its body contains these lines, one per member, so every member closes when it merges:
  Closes derio-net/frank#952
  Closes derio-net/frank#850
  Closes derio-net/frank#798
- Do not name any member issue as a phase `tracking_issue` in the plan: the bridge would then own that issue's `fr:` labels.

Never add the `approved-fr` label: it is the operator's approval to merge, and fr voids it on your next push.

<!-- fr:journal kind=discovery scope=spec id=pull-sync-already-healthy created=2026-11-15T06:04:01+00:00 -->
### pull-sync-already-healthy · discovery · #798 root cause was the #859 zero-byte-object corruption; 9/9 kid-laptops main syncs OK since 2026-10-18

No pull-sync PipelineRun for kid-laptops within the 7-day Tekton TTL, so the evidence came
from VictoriaLogs (retention back to 2026-10-18): every kid-laptops main commit in that
window (5c096b5, c23b02f, ba8615a, 82afee5, 5239384, 9cdd393, 064e944, 8dea86f, ada3141)
was pushed by a pull-sync pod ending `OK`. Gitea main == GitHub main (ada3141). No
kid-laptops repair line in mirror-reconcile logs. Outcome alerting exists
(layer-25-pipeline-failing, #797), grouped per pipeline, which 5 repos share.

<!-- fr:journal kind=discovery scope=spec id=repo-side-trigger-unmerged created=2026-11-15T06:04:01+00:00 -->
### repo-side-trigger-unmerged · discovery · kid-laptops sync-pr-** molecule trigger exists only on draft kid-laptops#139

main's molecule.yml triggers on pull_request + schedule only; the push sync-pr-**/sync-rerun-**
trigger is on draft PR #139 (fix/molecule-ci-evidence). ci-delivery-check treats absent status
as healthy, so frank can merge first. The weekly Gitea molecule run failed 2026-11-09 with an
unexpanded matrix job, the limitation #139 removes.

<!-- fr:journal kind=discovery scope=spec id=second-hop-no-ref-filter created=2026-11-15T06:04:01+00:00 -->
### second-hop-no-ref-filter · discovery · kid-laptops-push Tekton trigger on gitea-listener has no ref filter

Mirroring PR heads would also start a Tekton kid-laptops-ci run per sync-pr push.

<!-- fr:journal kind=decision scope=spec id=q1-952-load created=2026-11-15T06:04:01+00:00 decided_by=operator -->
### q1-952-load · decision · Ship #952 now; no runner change; watch the first run

Operator chose: ship now, capacity stays 2, layer-25-pc1-var-low is the guard, first PR molecule run is a Test Plan row. Not sequenced after #824.

<!-- fr:journal kind=decision scope=spec id=q2-tekton-main-only created=2026-11-15T06:04:01+00:00 decided_by=operator -->
### q2-tekton-main-only · decision · Restrict the Gitea-side kid-laptops-push Tekton trigger to refs/heads/main

Operator chose: PR evidence comes from Gitea Actions molecule only.

<!-- fr:journal kind=decision scope=spec id=q3-repair-alert-shape created=2026-11-15T06:04:01+00:00 decided_by=operator -->
### q3-repair-alert-shape · decision · Repair alert per repo, >=2 repairs in 6h, warning, ci_outcome 4h route

Operator chose: grouped by repo (Telegram + Health Bridge via the ci_outcome route).

<!-- fr:journal kind=decision scope=spec id=q4-798-close-on-evidence created=2026-11-15T06:04:01+00:00 decided_by=operator -->
### q4-798-close-on-evidence · decision · Close #798 on evidence + #850's per-repo alert; fix the stale mirror-sync-failing runbook

Operator chose: no pipeline change, no fresh pre-merge run, no per-repo outcome metric.

<!-- fr:journal kind=decision scope=spec id=q5-verification created=2026-11-15T06:04:01+00:00 decided_by=operator -->
### q5-verification · decision · Verification strategy live, gate devops

Operator chose the house convention; the post-merge webhook manual op makes the close-out devops-gated.

<!-- fr:journal kind=lens scope=spec id=lens-tests-1 created=2026-11-15T06:04:01+00:00 lens=tests step=brainstorm -->
### lens-tests-1 · lens · Offline guards are the only pre-merge proof for CEL filters and the new LogsQL rule

<!-- fr:journal kind=review scope=spec id=spec-review-r1 created=2026-11-15T06:11:17+00:00 -->
### spec-review-r1 · review · independent spec review: 11 findings (10 in scope, 1 out)

Dispatched fr-spec-reviewer (read-only). The spec honours all five operator decisions
(q1–q5), and the Test Plan heading is exact. Mixed-datasource groups and `extract` already
exist in alert-rules-cm.yaml. The R4 ref filter does not break webhooks.yaml or
test_webhook_delivery_paths.py. Missed guards: test_github_preferred_mirrors.py:92 and the
`serves:` coverage. Positive controls were missing for the LogsQL rule and for main-push CI
after R4. Suggested lens: tests (already added at brainstorm).

<!-- fr:journal kind=finding scope=spec id=sr-1 created=2026-11-15T06:11:17+00:00 state=open review_scope=in -->
### sr-1 · finding [open] (reviewer: in scope) · R8 misses test_github_preferred_mirrors.py:92, which pins kid-laptops out of derio-homelab-pr-sync

scripts/tests/test_github_preferred_mirrors.py:89-92 asserts pr-sync repos == tiers.yaml preferred repos, and R1 turns it red. R8 must name all three pinning sites (plus test_ci_mirror_resilience.py:201-208 and test_ci_delivery_check.py:143-144).

<!-- fr:journal kind=finding scope=spec id=sr-2 created=2026-11-15T06:11:17+00:00 state=open review_scope=in -->
### sr-2 · finding [open] (reviewer: in scope) · R2 changes only `events`, but the webhooks.yaml guard also requires `serves:` to include derio-homelab-pr-sync

test_webhook_delivery_paths.py:143-166 requires a github-listener declaration for derio-homelab/kid-laptops whose serves contains derio-homelab-pr-sync (webhooks.yaml:171).

<!-- fr:journal kind=finding scope=spec id=sr-3 created=2026-11-15T06:11:17+00:00 state=open review_scope=in -->
### sr-3 · finding [open] (reviewer: in scope) · mirror-reconcile's repo-list stages are `heads` and `plan`, not plan and push; the PR_REPOS order is pinned

mirror-reconcile.yaml:393,412,432,448. The push container has no lists. test_ci_mirror_resilience.py:195-196 compares a sorted list.

<!-- fr:journal kind=finding scope=spec id=sr-4 created=2026-11-15T06:11:17+00:00 state=open review_scope=in -->
### sr-4 · finding [open] (reviewer: in scope) · R7 lists ci-delivery-check.yaml as carrying a push-only comment; it has none

The only kid-laptops reference in ci-delivery-check.yaml is the MAIN_REPOS value at :345. The stale comment that remains is webhooks.yaml:173-175.

<!-- fr:journal kind=finding scope=spec id=sr-5 created=2026-11-15T06:11:17+00:00 state=open review_scope=in -->
### sr-5 · finding [open] (reviewer: in scope) · Rule-group placement is left to the plan, but mixed-datasource groups already exist

ci-runner-health (alert-rules-cm.yaml:2980-3090) mixes VictoriaLogs and Prometheus rules. Place the rule in layer-25-pipeline-outcomes. It is the first multi-series VictoriaLogs rule.

<!-- fr:journal kind=finding scope=spec id=sr-6 created=2026-11-15T06:11:17+00:00 state=open review_scope=in -->
### sr-6 · finding [open] (reviewer: in scope) · Repair-alert Test Plan row is vacuous: Normal/no-series also passes for a broken query

Under noDataState OK a misspelled extract or field returns NoData, which reads as Normal. A positive control is needed over a window that contains real repair lines.

<!-- fr:journal kind=finding scope=spec id=sr-7 created=2026-11-15T06:11:17+00:00 state=open review_scope=in -->
### sr-7 · finding [open] (reviewer: in scope) · Row kid-laptops-main-sync-healthy has no Test Plan row, and its stated evidence source cannot exist

The Verification row cites PipelineRun outcomes, but they do not survive the 7-day TTL; the evidence is VictoriaLogs pod logs.

<!-- fr:journal kind=finding scope=spec id=sr-8 created=2026-11-15T06:11:17+00:00 state=open review_scope=in -->
### sr-8 · finding [open] (reviewer: in scope) · No positive control that a kid-laptops main push still starts kid-laptops-ci after the R4 filter

A typo in the ref clause would silently stop main CI. Add a post-merge positive row and an offline assertion on the clause, as test_site_promotion_pipeline.py:142 does.

<!-- fr:journal kind=finding scope=spec id=sr-9 created=2026-11-15T06:11:17+00:00 state=open review_scope=in -->
### sr-9 · finding [open] (reviewer: in scope) · R5 says two or more refs but the query counts repair events; Findings overstate what a single repair fires

count() counts repairs. Under gt 1 a single dropped commit fires nothing; say that is tolerated by design.

<!-- fr:journal kind=finding scope=spec id=sr-10 created=2026-11-15T06:11:17+00:00 state=open review_scope=in -->
### sr-10 · finding [open] (reviewer: in scope) · test_ci_outcome_alert_repeat.py not named; joining CI_OUTCOME_RULES constrains the runbook text

test_ci_outcome_alert_repeat.py:71-76 requires `get pipelinerun -A ` and forbids `-n tekton-pipelines` in ci_outcome runbooks.

<!-- fr:journal kind=finding scope=spec id=sr-11 created=2026-11-15T06:11:17+00:00 state=open review_scope=out -->
### sr-11 · finding [open] (reviewer: out of scope) · webhooks.yaml:164-165 claims all mirrored repos deliver push + pull_request (pre-existing stale header)

The header count and claim are stale since 2026-10-18. This predates the change.

<!-- fr:journal kind=finding scope=spec id=sr-1-resolved created=2026-11-15T06:11:17+00:00 state=fixed resolves=sr-1 -->
### sr-1-resolved · finding [fixed] · resolves sr-1: R8 misses test_github_preferred_mirrors.py:92, which pins kid-laptops out of derio-homelab-pr-sync

R8 now names all three pinning sites.

<!-- fr:journal kind=finding scope=spec id=sr-2-resolved created=2026-11-15T06:11:17+00:00 state=fixed resolves=sr-2 -->
### sr-2-resolved · finding [fixed] · resolves sr-2: R2 changes only `events`, but the webhooks.yaml guard also requires `serves:` to include derio-homelab-pr-sync

R2 and the Design now require serves: [derio-homelab-main-sync, derio-homelab-pr-sync].

<!-- fr:journal kind=finding scope=spec id=sr-3-resolved created=2026-11-15T06:11:17+00:00 state=fixed resolves=sr-3 -->
### sr-3-resolved · finding [fixed] · resolves sr-3: mirror-reconcile's repo-list stages are `heads` and `plan`, not plan and push; the PR_REPOS order is pinned

R3 and the Design name the heads and plan initContainers, sorted position between homelab and omada-controller.

<!-- fr:journal kind=finding scope=spec id=sr-4-resolved created=2026-11-15T06:11:17+00:00 state=fixed resolves=sr-4 -->
### sr-4-resolved · finding [fixed] · resolves sr-4: R7 lists ci-delivery-check.yaml as carrying a push-only comment; it has none

R7 now lists the three real comment sites: eventlistener-github.yaml:226-228, webhooks.yaml:173-175 and mirror-reconcile.yaml:11.

<!-- fr:journal kind=finding scope=spec id=sr-5-resolved created=2026-11-15T06:11:17+00:00 state=fixed resolves=sr-5 -->
### sr-5-resolved · finding [fixed] · resolves sr-5: Rule-group placement is left to the plan, but mixed-datasource groups already exist

The Design places the rule in layer-25-pipeline-outcomes and drops the conditional; it notes this is the first multi-series VictoriaLogs rule.

<!-- fr:journal kind=finding scope=spec id=sr-6-resolved created=2026-11-15T06:11:17+00:00 state=fixed resolves=sr-6 -->
### sr-6-resolved · finding [fixed] · resolves sr-6: Repair-alert Test Plan row is vacuous: Normal/no-series also passes for a broken query

Test Plan has a positive-control row: the exact LogsQL over the 2026-10-19 15:00Z window must return per-repo series.

<!-- fr:journal kind=finding scope=spec id=sr-7-resolved created=2026-11-15T06:11:17+00:00 state=fixed resolves=sr-7 -->
### sr-7-resolved · finding [fixed] · resolves sr-7: Row kid-laptops-main-sync-healthy has no Test Plan row, and its stated evidence source cannot exist

The Verification row names VictoriaLogs plus a Gitea/GitHub main comparison, and a Test Plan row was added.

<!-- fr:journal kind=finding scope=spec id=sr-8-resolved created=2026-11-15T06:11:17+00:00 state=fixed resolves=sr-8 -->
### sr-8-resolved · finding [fixed] · resolves sr-8: No positive control that a kid-laptops main push still starts kid-laptops-ci after the R4 filter

Post-merge positive-control row added, and R8 requires an offline assertion on the refs/heads/main clause.

<!-- fr:journal kind=finding scope=spec id=sr-9-resolved created=2026-11-15T06:11:17+00:00 state=fixed resolves=sr-9 -->
### sr-9-resolved · finding [fixed] · resolves sr-9: R5 says two or more refs but the query counts repair events; Findings overstate what a single repair fires

R5 now says repairs, and the Findings state that one isolated repair is tolerated by design (q3).

<!-- fr:journal kind=finding scope=spec id=sr-10-resolved created=2026-11-15T06:11:17+00:00 state=fixed resolves=sr-10 -->
### sr-10-resolved · finding [fixed] · resolves sr-10: test_ci_outcome_alert_repeat.py not named; joining CI_OUTCOME_RULES constrains the runbook text

R5 and the Design require a `get pipelinerun -A` runbook; R8 joins the uid to CI_OUTCOME_RULES.

<!-- fr:journal kind=finding scope=spec id=sr-11-resolved created=2026-11-15T06:11:17+00:00 state=open resolves=sr-11 out_of_scope=true -->
### sr-11-resolved · finding [out-of-scope] · resolves sr-11: webhooks.yaml:164-165 claims all mirrored repos deliver push + pull_request (pre-existing stale header)

Pre-existing stale header in webhooks.yaml (count and claim stale since the 2026-10-18 widening); not caused by this change, which only edits the kid-laptops entry.

<!-- fr:journal kind=decision scope=spec id=exit-baseline created=2026-11-15T06:11:19+00:00 -->
### exit-baseline · decision · exit when spec-review resolved

The exit when spec-review resolved; `fr verification set` and `deliver` compare against it.

```yaml
row_gates:
  kid-laptops-main-sync-healthy: devops
  kid-laptops-pr-heads-mirrored: devops
  mirror-repair-alert: devops
row_kinds:
  kid-laptops-main-sync-healthy: live
  kid-laptops-pr-heads-mirrored: live
  mirror-repair-alert: live
run_gate: devops
run_kind: live
```

<!-- fr:journal kind=finding scope=spec id=pr-sync-ref-create-race created=2026-11-15T07:14:08+00:00 state=open review_scope=out -->
### pr-sync-ref-create-race · finding [open] (reviewer: out of scope) · derio-homelab-pr-sync can fail 'cannot lock ref … reference already exists' when two writers create the same new sync-pr ref

2026-11-01 derio-homelab-pr-sync-jsd5j (proxmox-cluster sync-pr-122): remote rejected, 'cannot lock ref refs/heads/sync-pr-122: reference already exists'. Two concurrent writers (two pr-sync runs for one PR, or a run racing mirror-reconcile) created the same new ref. The push is fire-and-forget, so the run fails; mirror-reconcile later repairs the ref. Pre-existing and not caused by this change (found while reading pull-sync logs for #798). Possible fixes: retry once on 'cannot lock ref', or serialise pr-sync per PR.

<!-- fr:journal kind=finding scope=spec id=pr-sync-ref-create-race-resolved created=2026-11-15T07:15:34+00:00 state=open resolves=pr-sync-ref-create-race out_of_scope=true -->
### pr-sync-ref-create-race-resolved · finding [out-of-scope] · resolves pr-sync-ref-create-race: derio-homelab-pr-sync can fail 'cannot lock ref … reference already exists' when two writers create the same new sync-pr ref

Pre-existing concurrent-writer race on proxmox-cluster; not caused by this change.
