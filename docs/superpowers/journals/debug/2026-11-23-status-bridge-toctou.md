<!-- fr:journal-schema=4 -->
# Journal: 2026-11-23-status-bridge-toctou

<!-- fr:journal kind=repro scope=debug id=f097f1018aa9 created=2026-11-23T07:28:30+00:00 -->
### f097f1018aa9 · repro · Stale pending posted to GitHub after its terminal status (runs-fr PR #52)

layer-25-delivery-overdue kind=status, derio-net/runs-fr, sha 5fb5d703, context 'acceptance-report / pages (push)'. Bridge run vwtxc (pending) created 21:41:18, current-state 21:41:18-28, forward POSTed 21:42:41. Run qzshd (success) created 21:41:52, POSTed 21:42:07. GitHub latest = pending forever. Repaired via scripts/ci_status_backfill.py (stoa-status-bridge-nc9nv). frank#1029.

<!-- fr:journal kind=ruled-out scope=debug id=f75fed955127 created=2026-11-23T07:28:33+00:00 -->
### f75fed955127 · ruled-out · Guard logic bug (wrong field / wrong context match)

At 21:41:2x Gitea genuinely held pending for the context: the success event was only created at 21:41:52. The guard answered correctly for the moment it asked.

<!-- fr:journal kind=root-cause scope=debug id=f6d2f9bfade0 created=2026-11-23T07:28:35+00:00 -->
### f6d2f9bfade0 · root-cause · Guard is check-then-act across two TaskRuns

current-state and forward are separate tasks, each its own pod. The 74s pod start of forward is the window in which the terminal event arrives and posts first; the stale pending then posts last and wins (statuses have no lifecycle). The guard narrows the race, cannot close it while check and POST live in different pods.

<!-- fr:journal kind=finding scope=debug id=81c5a128ec68 created=2026-11-23T07:34:51+00:00 state=fixed -->
### 81c5a128ec68 · finding [fixed] · Check and POST colocated as steps of one TaskRun

github-status-report StepAction (POST moved verbatim from github-status, plus fail-open guard-file); github-status Task refs it unguarded (script proven byte-identical); stoa-status-bridge is one task: check step writes /tekton/results/superseded, report step reads it. Failing-first tests: test_stoa_status_bridge.py::test_check_and_post_run_in_one_pod, test_github_status_report_guard.py (12 RED -> GREEN). Server-side dry-run accepted all three manifests on Tekton v1.6.0. 139 related + 73 Tekton/ArgoCD guard tests pass.

<!-- fr:journal kind=review scope=debug id=2780a2c0b2b6 created=2026-11-23T07:35:26+00:00 -->
### 2780a2c0b2b6 · review · Self-review: no findings; runtime proof owed post-merge

Checked: moved script byte-identical to the old Task (script, image, command, securityContext, env, params, computeResources); no non-prose reference to the old current-state task name; result file written by uid 65534 at default 0644, readable by the uid-100 report step (fail-open regardless); check-step crash behaviour unchanged (report never runs, as forward never ran before). Not provable pre-merge: the StepAction only exists on the cluster after ArgoCD syncs main. Post-merge: one github-status TaskRun from a CI pipeline Succeeded, one bridge run Succeeded, a stale-pending run logging 'pending is stale' from the report step, and ci-delivery-check clean.

<!-- fr:journal kind=finding scope=debug id=ab62f52d0fd0 created=2026-11-23T08:03:39+00:00 state=fixed -->
### ab62f52d0fd0 · finding [fixed] · CI: test_ci_status_always_reported parsed the Task script

Missed by the reference sweep because it builds the path as f'{task}.yaml'. Its _script() now follows a ref: step to the StepAction. 25 passed.
