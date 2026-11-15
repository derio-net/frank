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
