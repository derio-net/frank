# Journal: 2026-10-13-ci-fails-silently

<!-- fr:journal kind=repro scope=debug id=07d555715485 created=2026-10-13T17:10:26+00:00 -->
### 07d555715485 · repro · Timed-out CI PipelineRuns post no commit status

From 2026-10-11T21:22Z to 2026-10-12T04:21Z, 23 PipelineRuns (cnc-ci / cnc-frd-ci / agentic-stoa-main-sync) ended PipelineRunTimeout. Example cnc-frd-ci-82dr7: spec.timeouts={pipeline: 1h} (controller default; no template sets timeouts); childReferences=[mirror] only; skippedTasks: github-status-failure and gitea-status-failure with reason 'PipelineRun timeout has been reached'. Repro: kubectl -n tekton-pipelines get pipelinerun cnc-frd-ci-82dr7 -o json | jq .status.skippedTasks. The mirror pod was blocked on its volumeClaimTemplate PVC (longhorn-hdd: disk tag hdd does not exist). Net effect: GitHub received no tekton/ci status, so PRs looked green.

<!-- fr:journal kind=root-cause scope=debug id=0937b3ddabb3 created=2026-10-13T17:10:29+00:00 -->
### 0937b3ddabb3 · root-cause · No finally budget: the pipeline timeout cancels finally, and nothing posts pending up front

Tekton v1.6.0: when only timeouts.pipeline is set and it expires, finally tasks are skipped ('PipelineRun timeout has been reached'). Every CI TriggerTemplate omits timeouts, so the 1h default applies with zero finally budget. The status tasks (github-status / gitea-status) bind no workspace and would have scheduled fine; they never got a budget. Compounded by: no pending status at run start (an unreported run is absent, not pending), and no alert on PVC ProvisioningFailed or PipelineRun timeouts.

<!-- fr:journal kind=ruled-out scope=debug id=ee3bce080eb5 created=2026-10-13T17:14:54+00:00 -->
### ee3bce080eb5 · ruled-out · Status tasks are not blocked by the unprovisionable PVC

github-status and gitea-status declare no workspaces, and the finally entries bind none, so the affinity assistant (coschedule=workspaces) does not pin them to the PVC. Evidence: the finally tasks were skipped with reason 'PipelineRun timeout has been reached', never created as Pending TaskRuns. Giving finally a budget is sufficient for them to run.
