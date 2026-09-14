# Journal: 2026-09-13--obs--pipelinerun-failure-alerting

<!-- fr:journal kind=discovery scope=plan id=71c87342ad8a created=2026-09-13T22:26:02 -->
### 71c87342ad8a · discovery · no-refactor-because P1.T2

The task adds two YAML keys to a manifest (an action:drop metricRelabelConfigs entry) and one test that derives the metric name from the committed census. The only shared machinery it needs — the repo-anchored YAML loader — was extracted one task earlier in P1.T1.S3, so there is nothing left to restructure. Inventing a refactor step here would mean restructuring a four-line YAML literal.

<!-- fr:journal kind=discovery scope=plan id=9fa1f7b72dfc created=2026-09-13T22:26:03 -->
### 9fa1f7b72dfc · discovery · no-refactor-because P2.T2

This task replaces a placeholder PromQL string with the real expression and sets relativeTimeRange on three refIds. The unit of change is a query literal inside a Grafana provisioning document, not code: there is no duplication to collapse and no abstraction to extract. The test-side helpers (_rule_by_uid, _query_expr) were extracted in P2.T1.S3 precisely so this task and phase 3 would not each grow their own.

<!-- fr:journal kind=discovery scope=plan id=a5b62a6f87e4 created=2026-09-13T22:26:05 -->
### a5b62a6f87e4 · discovery · no-refactor-because P3.T3

One test function plus one deliberate red-then-revert demonstration. It consumes the _idle_rules() helper extracted in P3.T1.S3 and adds no duplication. The step that would normally be the refactor is instead spent proving the guard can fail — which is the more valuable use of the step for a test whose entire purpose is to catch a rename nobody will be watching for.

<!-- fr:journal kind=discovery scope=plan id=746b1bab2f52 created=2026-09-13T22:26:07 -->
### 746b1bab2f52 · discovery · no-refactor-because P4.T2

Documentation and status bookkeeping: prose into docs/runbooks/frank-gotchas/grafana.md, a one-liner into agents/rules/frank-gotchas.md, a spec Status field, and a final full-suite run. No code is written, so red-green-refactor does not apply. The deliberate structural decision — prose in the per-topic file, one-liner in the hot file, never both — is stated in the step text rather than discovered by refactoring.

<!-- fr:journal kind=discovery scope=plan id=4bf5761496e8 created=2026-09-13T22:40:44 phase=1 -->
### 4bf5761496e8 · discovery · Baseline suite is fully green; phase adds 2 tests cleanly (phase 1)

Clean-tree baseline (git stash -u, run, stash pop), confirmed twice: 789 passed, 1 xfailed, 0 failures — uv run --frozen pytest scripts/tests/ -q, ~150-235s wall time depending on machine load. Post-phase-1 tree: 791 passed, 1 xfailed, 0 failures (the +2 is exactly the new test_pipelinerun_outcome_alerting.py file; no other test's outcome changed). No pre-existing red tests to attribute or avoid touching.

<!-- fr:journal kind=discovery scope=plan id=6e4e443fd378 created=2026-09-13T22:40:54 phase=1 -->
### 6e4e443fd378 · discovery · Post-drop series count: 851 (6572 - 5721), per the 2026-09-13 census (phase 1)

test_the_scrape_drops_the_unbounded_metric derives the offending metric (tekton_pipelines_controller_taskruns_pod_latency_milliseconds, 5721/6572 = 87.1%) from scripts/tests/fixtures/tekton/controller-series-census.json rather than hardcoding it. Once the manifest's metricRelabelConfigs drop lands on the cluster (phase 5, manual), the tekton-pipelines-controller scrape is expected to add 6572 - 5721 = 851 new series to VMSingle — useful for the PR body's 'what did this actually add' framing per the plan's task 2 step 2 note.

<!-- fr:journal kind=finding scope=plan id=55b7558a4da0 created=2026-09-13T22:41:54 phase=1 state=fixed -->
### 55b7558a4da0 · finding [fixed] · Acceptance row pipelinerun-outcomes-visible intentionally left not-implemented (phase 1)

fr plan edit --complete-phase 1 warned that acceptance row 'pipelinerun-outcomes-visible' is still not-implemented. Left it as-is: the row's own notes say it is 'Verified post-merge by the series being present in VMSingle' — that needs the live cluster (phase 5, manual/post-merge), and phase 1 is tagged skeleton: true in 01.yaml. Flipping it now would be asserting something not yet observed. No plan change needed; noting so a later phase or reviewer doesn't re-raise this as a gap.

<!-- fr:journal kind=finding scope=plan id=review-p1-selector-message created=2026-09-13T22:43:56 phase=1 state=fixed -->
### review-p1-selector-message · finding [fixed] · Assertion message called the scrape selector a Deployment selector (phase 1)

A VMServiceScrape discovers targets through a SERVICE's Endpoints; it never looks at a Deployment. The failure message said 'the tekton-pipelines-controller Deployment's labels', which is wrong in exactly the place someone reads it — while debugging a scrape that is not selecting. Behaviourally harmless, but the message is the documentation at the moment it matters most. Reworded to name the Service and the Endpoints mechanism. Verified alongside: the selector matches exactly ONE Service in tekton-pipelines (tekton-pipelines-webhook and tekton-events-controller carry different app labels), so there is no accidental second target.

<!-- fr:journal kind=finding scope=plan id=review-p1-deploy-time-false-positive created=2026-09-13T22:43:58 phase=1 state=fixed -->
### review-p1-deploy-time-false-positive · finding [fixed] · The github-pull-sync dead-man will probably fire once at deploy time — phase 3 must say so (phase 1)

The spec documents a post-restart false-positive window for layer-25-pipeline-idle-github-pull-sync but missed its FIRST and most certain instance: the moment the scrape goes live. Before the first github-pull-sync run is scraped there is no series at all, so 'or vector(0)' reads 0, 'lt 1' is true, and after for:2h the rule fires. At 10.4 runs/day the mean gap between runs is ~2.3h, so this is roughly a coin flip on any given deploy — not a rare edge. stoa-status-bridge is unaffected (148/day, first run inside ~10 minutes, for:1h). Carrying forward: phase 3 step P3.T1.S2 now requires the rule comment to name the deploy-time case explicitly alongside the restart case, and phase 5 step P5.T2.S3 now tells the operator to expect it and to treat it as resolved once the first run lands rather than as a defect. Left open until phase 3 lands the comment.

**Fixed (phase 3):** the layer-25-pipeline-outcomes group comment and the block comment directly above the two idle rules in `apps/grafana-alerting/manifests/alert-rules-cm.yaml` now name DEPLOY TIME explicitly as the certain false-positive case (no series exists before the first scrape, so `or vector(0)` reads 0 and the rule fires after its `for` window) alongside CONTROLLER RESTART as the same mechanism, quantify github-pull-sync's exposure (~half of deploys, ~1 in 10 restarts at the observed cadence) and state both self-clear on the first post-event run. No rule-shape change was needed — only the comment was missing this case.

<!-- fr:journal kind=decision scope=plan id=ba2a677a78af created=2026-09-13T22:56:02 phase=2 -->
### ba2a677a78af · decision · no-refactor-because: P2.T3 (phase 2)

P2.T3.S1 adds one regression-tripwire test asserting the >= 3 floor lives in refId A and C's evaluator is {type: gt, params: [0]}. It is a freeze test for a shape already correct after P2.T2 — nothing to extract or restructure, per the plan's own note that a test whose purpose is to pin a correct shape has no refactor step.

<!-- fr:journal kind=discovery scope=plan id=8a34f71ccc46 created=2026-09-13T22:58:49 phase=2 -->
### 8a34f71ccc46 · discovery · Isolation container disk ran out mid-phase (host docker VM, not repo-related) (phase 2)

First test run failed with 'No space left on device' from uv (ENOSPC) inside the fr-isolation container; df showed the container's overlay root at 100% (59G/59G). Root cause was the HOST docker VM's build cache (docker system df: 5.5GB reclaimable build cache, 0 active), unrelated to this repo or plan. Fixed with 'docker builder prune -f' run from the host (outside the container) — freed ~7GB, brought the container to 90% and unblocked uv. Not a plan defect; noting for later phases/orchestrator in case the same environment hits it again — check 'docker system df' before assuming a real test failure.

<!-- fr:journal kind=finding scope=plan id=review-p2-title-convention created=2026-09-13T23:01:26 phase=2 state=fixed -->
### review-p2-title-convention · finding [fixed] · Rule title dropped the 'Layer NN' prefix every other layer-tracker rule carries (phase 2)

Shipped as 'Pipeline failing with no successes'; every other layer-tracker rule in the folder reads 'Layer NN <thing>' (Layer 2 OS Control-Plane NotReady, Layer 24 Traefik Ingress Down, Layer 25 CI/CD Platform Degraded). The title is not cosmetic here: it is the Telegram message subject AND the health-bridge tile and bug-issue title, so an operator scanning a list of alerts loses the layer anchor that every neighbour provides. Renamed to 'Layer 25 Pipeline Failing'. No guard enforces this convention and I did not add one — inventing folder-wide policy is outside this PR's scope.

<!-- fr:journal kind=finding scope=plan id=review-p2-invalid-tkn-flag created=2026-09-13T23:01:28 phase=2 state=fixed -->
### review-p2-invalid-tkn-flag · finding [fixed] · The runbook shipped a tkn invocation that does not exist (phase 2)

Shipped 'tkn pipelinerun logs -n tekton-pipelines -p <pipeline> --last'. 'tkn pipelinerun logs' has no -p flag — that belongs to 'tkn pipeline logs <name>', a different subcommand. The command would have failed on the spot for anyone who ran it, and a runbook is read under pressure, so a wrong command costs more than no command. tkn itself is legitimate here (the layer-22 operating post documents 'tkn pipelinerun logs -n tekton-pipelines --last'), so the fix keeps it and corrects the subcommand: 'tkn pipeline logs <pipeline> -n tekton-pipelines --last'. Also added --sort-by=.metadata.creationTimestamp to the kubectl half, since the useful run is the most recent and the default ordering is not chronological.

<!-- fr:journal kind=decision scope=plan id=9de08f9f9ae6 created=2026-09-13T23:09:17 phase=3 -->
### 9de08f9f9ae6 · decision · no-refactor-because: P3.T2 (phase 3)

test_each_idle_rule_carries_a_zero_fallback and test_the_idle_rules_fire_below_a_floor_not_above_a_ceiling are regression tripwires for a shape P3.T1.S2 already wrote correctly; both went GREEN immediately, nothing to extract.

<!-- fr:journal kind=finding scope=plan id=review-p3-idle-runbook created=2026-09-13T23:44:06 phase=3 state=fixed -->
### review-p3-idle-runbook · finding [fixed] · The idle rules' runbook listed PipelineRuns — the one thing guaranteed to be empty when they fire (phase 3)

Both dead-man rules shipped with 'kubectl -n tekton-pipelines get pipelinerun -l tekton.dev/pipeline=X --sort-by=...'. The alert's entire meaning is that NO runs arrived, so that command returns nothing by construction (and the 7-day TTL GC removes older ones anyway) — an operator following it learns only what the alert already said. The repo names the real cause in apps/tekton/webhooks.yaml: an EventListener trigger is only half a delivery path, the webhook is forge state with no IaC here, and on 2026-07-26 a missing Gitea webhook 'reads as a broken pipeline rather than a missing webhook, which is why it cost a debugging round' — which is exactly this alert's failure mode. Both runbooks now say the empty list proves nothing, point at the listener log (el-gitea-listener / el-github-listener) to ask whether events arrive at all, and send the operator to webhooks.yaml and the forge. This is the runbook whose only reader is someone mid-incident, so pointing it at the wrong surface is expensive.

<!-- fr:journal kind=discovery scope=plan id=observed-preexisting-telegram-html-debt created=2026-09-13T23:44:26 phase=3 -->
### observed-preexisting-telegram-html-debt · discovery · 12 PRE-EXISTING rules carry bare angle brackets in annotations — latent Telegram-400 debt, deliberately not fixed here (phase 3)

While verifying the three new rules are clean of the documented Telegram HTML parse_mode trap (a bare < > or & makes Telegram reject with 400: the rule fires, dispatches, and silently never delivers), a sweep of the whole alert-rules ConfigMap found twelve pre-existing offenders across several layers: exercise-reminder-stale, session-manager-stale, audit-digest-stale, layer-1-node-memory-headroom (summary AND runbook), tls-cert-expiring-14d, tls-cert-expiring-7d, tls-cert-canary-absent, headscale-api-key-expiry-warning (runbook), crowdsec-decision-burst. The three rules added by this plan are clean. NOT fixed here on purpose — that is twelve rules across unrelated layers, each needing its own delivery verification, and widening this PR into them would make a detection-gap change unreviewable. Worth its own issue; the sweep query is a three-line yaml walk over the ConfigMap's annotations.

<!-- fr:journal kind=discovery scope=plan id=6d6ad52a63aa created=2026-09-13T23:56:07 phase=4 -->
### 6d6ad52a63aa · discovery · P4.T1.S2 RED demonstration: the drop-regex half of the guard is what actually fires (phase 4)

Pointing the github-pull-sync idle rule's metric at tekton_pipelines_controller_taskruns_pod_latency_milliseconds does NOT fail the 'appears in the fixture' half of test_the_scrape_and_the_rules_agree_on_the_metric_name — that metric IS present in controller-metrics-sample.txt (truncated to its first 3 samples, per the fixture's own header comment). The guard instead goes RED on the second half: the name matches the scrape's own drop regex verbatim (re.fullmatch on the literal string). Confirmed RED with a targeted sed edit + single-test run, then reverted (git diff clean, full file green again, 11/11). This is the correct failure surface: it proves the half of the guard that specifically closes the scrape<->rules loop, not the half that just confirms the controller emits the metric at all.

<!-- fr:journal kind=discovery scope=plan id=fe344b88c5c9 created=2026-09-14T00:03:08 phase=4 -->
### fe344b88c5c9 · discovery · P4.T2 written record: prose in grafana.md only, one-liner in the hot file, spec Status flipped (phase 4)

Added a new dated section to docs/runbooks/frank-gotchas/grafana.md ('A CI platform can be 100% green on is it replicated while every pipeline it runs fails') covering: the #790 blind spot and layer-25-cicd-down's correct-but-incomplete scope; why the 2026-05-14 pod-readiness rewrite was right and still left this hole; the signal existing but never being scraped; the mandatory 87.1%-cardinality drop and its kube-state-metrics precedent; all three PromQL traps (unless vs and...==0, or vector(0) inert under sum by — spelled out as a label-set mismatch, not just a syntax note — and absent_over_time as the wrong primitive because the controller keeps emitting a stopped pipeline's histogram); the measured cadence table and why a shared 24h window would have paged on the first quiet Sunday; the documented github-pull-sync post-restart false-positive window; and the missing-webhook-not-broken-pipeline lesson from the 2026-07-26 site->www incident, pointing at apps/tekton/webhooks.yaml. Added exactly one bolded one-liner to the Grafana section of agents/rules/frank-gotchas.md pointing at that file -- confirmed the prose lives in grafana.md only (765 lines) and not duplicated in the hot file. Flipped the design spec's Status Draft -> In Progress; confirmed the Implementation Plans table row already pointed at this plan (no edit needed). Wrote no blog posts, per plan-post-deploy-checklist.md (fix/extension to layer 25, not a new layer).

<!-- fr:journal kind=finding scope=plan id=review-p4-prose-accuracy created=2026-09-14T00:05:44 phase=4 state=fixed -->
### review-p4-prose-accuracy · finding [fixed] · Gotchas prose disagreed with its own committed fixture, and overclaimed one historical fact (phase 4)

Two accuracy defects in otherwise strong prose. (1) It cited '~6,563 series' where the committed census fixture says 6,572 — the number a reader would check it against — and its own arithmetic then did not quite work (5721/6563 = 87.2%, not the stated 87.1%). The 6563 figure came from an earlier ad-hoc count during research, not from the fixture that shipped. Corrected to 6,572, and '~850 bounded series' made exact at 851. (2) It asserted that the tekton metric query 'returned nothing in VMSingle for as long as the cluster has existed' — an inference, not a measurement. What is actually known is that it returned empty when measured on 2026-09-13 and that git log -S VMServiceScrape -- apps/tekton/ shows no such manifest was ever declared (verified: the only hit is this plan's own phase-1 commit). Reworded to state exactly that, and to note a hand-applied scrape would escape both checks though the repo is declarative-only. The rest of the document is scrupulous about separating measured from inferred; a sentence like that is what later gets quoted as established fact.

<!-- fr:journal kind=decision scope=plan id=phase5-ships-unimplemented created=2026-09-14T00:06:40 phase=5 -->
### phase5-ships-unimplemented · decision · Phase 5 ships UNIMPLEMENTED by design — it is the back-loaded manual phase (phase 5)

Phase 5 is tagged [manual] and every step needs the live cluster: an ArgoCD sync of tekton-extras, a Grafana pod restart (provisioning files are read at boot, so a synced ConfigMap proves nothing about what is being evaluated), a synthetic always-failing PipelineRun run three times, and a passing run to prove the alert self-resolves. None of that is agent-completable and none of it can run in CI, which is why fr-plan's agentic-purity gate collected it into its own phase. It is back-loaded: no agentic phase depends on it, so the PR ships with it open and the operator drives it post-merge, pushing any resulting changes to the same PR. The three acceptance rows stay not-implemented until it runs — that is the correct state, not debt incurred by this PR. No phase-executor was dispatched for it; dispatching one would either fail or, worse, fabricate cluster evidence.

<!-- fr:journal kind=discovery scope=plan id=ci-did-not-trigger-on-draft-pr created=2026-09-14T00:27:03 -->
### ci-did-not-trigger-on-draft-pr · discovery · The pull_request event created NO run for the draft PR — CI obtained via workflow_dispatch instead

PR #797 showed 'no checks reported' 10+ minutes after creation. Verified rather than assumed: actions/runs?branch=... returned total_count 0, nothing queued or waiting on approval, Actions enabled:true, Repo Tripwires state:active, and a pull_request-triggered run on another branch had succeeded 37 minutes earlier. So the workflow is healthy and the event produced nothing for this PR. Obtained a real verdict with 'gh workflow run repo-tripwires.yml --ref <branch>' — run 34786663300, success — which does NOT attach to the PR as a check because it is a workflow_dispatch. Two consequences recorded in the PR body: (1) #797 is the only DRAFT PR among the last 12 in this repo and every other got checks, which is suggestive but not proof at n=1 (not tested by flipping draft state, since the fr-goal contract forbids readying the PR before the operator's review); (2) marking it ready will not trigger CI either, because repo-tripwires.yml declares a bare 'on: pull_request:' with no types, so it listens to opened/synchronize/reopened and ready_for_review is not among them — only a new push will attach a check. This is exactly the hazard that workflow's own header names about paths filters: on a PR page 'no run' is indistinguishable from 'passed'. If draft PRs systematically do not trigger CI here, every future fr-goal PR arrives looking unverified-but-clean. Worth its own issue.

<!-- fr:journal kind=finding scope=plan id=ci-synchronize-prediction-falsified created=2026-09-14T00:32:54 state=fixed -->
### ci-synchronize-prediction-falsified · finding [fixed] · Corrected the PR body: I predicted a push would attach a check, and the test disproved it

The first write-up of the CI anomaly reasoned from repo-tripwires.yml's bare 'on: pull_request:' (default types opened/synchronize/reopened) to the actionable claim that a new push WOULD attach a check. I then pushed a real commit and polled for four minutes: no pull_request run of any kind appeared, only the workflow_dispatch one. The prediction was mechanism-derived and presented as fact; testing it falsified it, and the PR body now says so explicitly rather than quietly dropping it. What is actually established: two independent pull_request events (opened, synchronize) both produced nothing while the PR is a draft, on a workflow that runs fine on dispatch and on every non-draft PR in the repo, with actions/permissions reporting enabled:true and allowed_actions:all. Draft is the only differing variable, but no governing setting was confirmable through the API — so this is UNEXPLAINED, not diagnosed, and the PR body states it that way. Same discipline this PR's own review applied to the prose: separate what was measured from what was inferred.
