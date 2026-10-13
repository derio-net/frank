<!-- fr:journal-schema=2 -->
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

<!-- fr:journal kind=hypothesis scope=debug id=4cf649e0536b created=2026-10-13T17:14:57+00:00 -->
### 4cf649e0536b · hypothesis · timeouts {pipeline: 1h, tasks: 50m, finally: 10m} makes finally run and report failure

Tekton v1.6 semantics (also relied on by staging-gate-template, which already sets tasks < pipeline): when timeouts.tasks elapses, DAG tasks are cancelled and finally runs in its own window. A timed-out task makes $(tasks.status)=Failed (the incident runs already evaluated it to 'Failed'), so the existing *-status-failure finally tasks (when notin [Succeeded, Completed]) fire. 50m is safe: live VM shows zero successful runs over 30m for any pipeline (count - bucket{le=1800} = 0).

<!-- fr:journal kind=hypothesis scope=debug id=371d19ed668a created=2026-10-13T17:15:00+00:00 -->
### 371d19ed668a · hypothesis · Alert signals that exist live: kube-state-metrics PVC phase and the Tekton duration histogram

No VMAlert is deployed (kubectl get vmalert -A: none); frank alerting is Grafana unified alerting over VictoriaMetrics (apps/grafana-alerting alert-rules-cm.yaml). Tekton metrics carry only status=success|failed, no reason label, so a timeout is identified by duration: failed runs with duration > 1800s (count - bucket{le=1800}). Backtest: 30d shows 15 (cnc-ci) + 19 (github-pull-sync), all inside the incident, 0 elsewhere. PVC rule: count(phase=Pending == 1 and on(namespace,persistentvolumeclaim) (time() - kube_persistentvolumeclaim_created) > 900) in tekton-pipelines. Backtest: 19 at 2026-10-11T23:06Z, 20 at 2026-10-12T03:33Z, empty now.

<!-- fr:journal kind=finding scope=debug id=0e1f5d781b9a created=2026-10-13T17:36:40+00:00 state=fixed -->
### 0e1f5d781b9a · finding [fixed] · Every CI run now leaves a status: finally budget, pending first, silence alerts

Commit b6cb206d. Failing check first: scripts/tests/test_ci_status_always_reported.py went red (18 failed, 7 passed) before any manifest change: no timeouts.tasks/finally on 7 CI TriggerTemplates, no pending task in 5 Pipelines, no best-effort mode, no alert rules. Fix: timeouts {pipeline: 1h, tasks: 50m, finally: 10m} on hum / content-factory / stoa-blog / cnc-fr / cnc-frd / cnc-fru / gitea templates; github-status-pending DAG root task (no runAfter, no workspace, best-effort) + gitea-status-pending after the mirror push in cnc-ci, hum-ci, content-factory-ci, stoa-blog-ci; report-pending in gitea-ci; best-effort param on github-status/gitea-status (default false, curl transport failure still fatal unless best-effort); Grafana rules layer-25-ci-workspace-pvc-pending and layer-25-pipelinerun-timeout. Verified: targeted suites 96 passed; kubectl apply --dry-run=server clean for all 10 changed manifests; a rendered cnc-frd PipelineRun with the new timeouts passed Tekton's admission webhook.

<!-- fr:journal kind=review scope=debug id=adc6ec2e85f1 created=2026-10-13T17:37:09+00:00 -->
### adc6ec2e85f1 · review · Self-review before PR: no in-scope findings; two out-of-scope follow-ups noted

Checked: (1) pending vs final ordering: finally waits on every DAG task, so the pending post cannot land after success/failure. (2) best-effort default false keeps stoa-status-bridge and every finally post mandatory; test_github_status_quota_422 still green. (3) gitea pending for GitHub-sourced pipelines runs after the mirror push (Gitea rejects statuses for unknown commits); if the mirror never runs it is skipped, which does not affect $(tasks.status). (4) Alert le=1800 is below timeouts.tasks=50m, pinned by test. Full suite: 1129 passed, 1 xfailed. Out of scope, for the PR body: kid-laptops-ci-template (pipeline fetched from the kid-laptops repo by git resolver, contract-tested) and the main-sync templates (no finally status) were left unchanged; StorageClass gating (unmerged fix/stor-ci-workspaces-back-to-cicd) is the follow-up for the root trigger.
