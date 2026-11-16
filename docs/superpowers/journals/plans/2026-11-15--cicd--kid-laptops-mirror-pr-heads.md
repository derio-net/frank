<!-- fr:journal-schema=4 -->
# Journal: 2026-11-15--cicd--kid-laptops-mirror-pr-heads

<!-- fr:journal kind=decision scope=plan id=plan-one-agentic-phase created=2026-11-15T06:14:04+00:00 -->
### plan-one-agentic-phase · decision · One agentic phase (standard tier) plus post-merge devops ops; no [manual] phase

All three asks edit one mirror pipeline's lists, one alert rule and their guards, which one reviewer can hold. The webhook change is a post-merge op in ops.yaml, following the 2026-11-14 root-agents plan.

<!-- fr:journal kind=discovery scope=plan id=p1-kubectl-dryrun-needs-cluster created=2026-11-15T06:48:59+00:00 phase=1 -->
### p1-kubectl-dryrun-needs-cluster · discovery · kubectl create --dry-run=client cannot validate EventListener files offline (phase 1)

With no reachable API server it fails fetching openapi and the Tekton CRDs are absent, so P1.T4.S2 was met by parsing every touched apps/ YAML with yaml.safe_load_all (all ok) plus the offline guard tests. System python3 has no yaml; use the repo .venv python.

<!-- fr:journal kind=discovery scope=plan id=p1-handoff-empty created=2026-11-15T06:48:59+00:00 phase=1 -->
### p1-handoff-empty · discovery · journal handoff file held only a usage error (phase 1)

handoff-p1.md contained the fr journal handoff usage error (missing --slug), so the phase ran from the dispatch brief, pickup and spec alone.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t1 created=2026-11-15T06:48:59+00:00 phase=1 -->
### no-refactor-p1-t1 · discovery · no-refactor-because P1.T1 (phase 1)

the kid-laptops-push filter test parses its own trigger via a small _trigger_filter helper; test_site_promotion_pipeline uses a text window, so there was no shared helper worth extracting

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t2 created=2026-11-15T06:48:59+00:00 phase=1 -->
### no-refactor-p1-t2 · discovery · no-refactor-because P1.T2 (phase 1)

test_mirror_repair_alert.py already imports _rules from test_ci_outcome_alert_repeat.py, so there was no duplicated rule loader left to share

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t3 created=2026-11-15T06:48:59+00:00 phase=1 -->
### no-refactor-p1-t3 · discovery · no-refactor-because P1.T3 (phase 1)

docs and manual-op edits only, nothing to clean

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t4 created=2026-11-15T06:48:59+00:00 phase=1 -->
### no-refactor-p1-t4 · discovery · no-refactor-because P1.T4 (phase 1)

gate steps only, no production code touched

<!-- fr:journal kind=review scope=plan id=p1-review-r1 created=2026-11-15T06:58:38+00:00 phase=1 -->
### p1-review-r1 · review · Phase 1 code review: 9 findings (3 important, 6 minor), all in scope, all fixed (phase 1)

Reviewed by a dispatched general-purpose reviewer (superpowers:requesting-code-review
template), over d9eca14d..17e52d2e. No Critical issues. The CEL edits, PR_REPOS placement,
guard flips and rule A/B/C shape were judged correct; 168 related tests passed. The
orchestrator verified each finding against the code (receiving-code-review) before fixing:
p1a-r1 was confirmed live (Gitea has no kid-laptops sync-pr refs; PRs #104/#105/#139 are far
past grace), and p1a-r2 was confirmed (#139's head molecule.yml carries push: sync-pr-**).
The rule's exact LogsQL was run against live VictoriaLogs (30d) and returned one series per
repo with a `repo` label (6 repos), which settles the multi-series shape the reviewer
declined to judge offline. The automated security review's log-spoofing flag is the same
as p1a-r3.

<!-- fr:journal kind=finding scope=plan id=p1a-r1 created=2026-11-15T06:58:38+00:00 phase=1 state=open review_scope=in -->
### p1a-r1 · finding [open] (reviewer: in scope) · New rule fires ~15 min after merge on the first-reconcile backfill of 3 kid-laptops sync-pr refs; nothing expects it (phase 1)

mirror-reconcile PR_REPOS + alert-rules-cm.yaml layer-25-mirror-repair-recurring. Open PRs #104/#105/#139 have no sync-pr ref and are older than GRACE_MINUTES, so the first run produces 3 repairs (count 3 > 1).

<!-- fr:journal kind=finding scope=plan id=p1a-r2 created=2026-11-15T06:58:38+00:00 phase=1 state=open review_scope=in -->
### p1a-r2 · finding [open] (reviewer: in scope) · Spec Finding wrong: sync-pr-139 runs molecule as soon as it is mirrored, not after #139 merges (phase 1)

Gitea Actions evaluates on.push from the pushed commit's tree; #139's head carries push: branches [sync-pr-**]. The first systemd-in-DinD run is therefore immediately after merge.

<!-- fr:journal kind=finding scope=plan id=p1a-r3 created=2026-11-15T06:58:38+00:00 phase=1 state=open review_scope=in -->
### p1a-r3 · finding [open] (reviewer: in scope) · Repair-rule LogsQL spoofable by any tekton-pipelines pod; pin container_name:push (phase 1)

alert-rules-cm.yaml expr scoped only by namespace and message. Tekton step containers are step-*/sidecar-*, so container push is reconciler-only. Pod name is not pinned, so mr-manual-* runs keep counting.

<!-- fr:journal kind=finding scope=plan id=p1a-r4 created=2026-11-15T06:58:38+00:00 phase=1 state=open review_scope=in -->
### p1a-r4 · finding [open] (reviewer: in scope) · Summary renders the whole value struct ($values.B) (phase 1)

Use {{ $values.B.Value | printf "%.0f" }} like sibling rules.

<!-- fr:journal kind=finding scope=plan id=p1a-r5 created=2026-11-15T06:58:38+00:00 phase=1 state=open review_scope=in -->
### p1a-r5 · finding [open] (reviewer: in scope) · building/35 says kid-laptops statuses are not bridged; they are (phase 1)

gitea-status-bridge (eventlistener.yaml:86) lists kid-laptops, and ci-delivery-check verifies the derio-homelab org.

<!-- fr:journal kind=finding scope=plan id=p1a-r6 created=2026-11-15T06:58:38+00:00 phase=1 state=open review_scope=in -->
### p1a-r6 · finding [open] (reviewer: in scope) · tekton.md gives the wrong reason for the runbook's -A (phase 1)

Pull-sync runs are in tekton-pipelines. The real reason is the ci_outcome runbook convention enforced by test_ci_outcome_alert_repeat.py.

<!-- fr:journal kind=finding scope=plan id=p1a-r7 created=2026-11-15T06:58:38+00:00 phase=1 state=open review_scope=in -->
### p1a-r7 · finding [open] (reviewer: in scope) · Gotcha narrates the shared-pipeline masking as historical; it was hypothetical (phase 1)

#798's failures predate the other four repos joining the pipeline (#875, 2026-10-18).

<!-- fr:journal kind=finding scope=plan id=p1a-r8 created=2026-11-15T06:58:38+00:00 phase=1 state=open review_scope=in -->
### p1a-r8 · finding [open] (reviewer: in scope) · Main-only test is substring presence; an `|| body.ref == ...` would pass (phase 1)

test_kid_laptops_mirror_wiring.py::test_kid_laptops_push_trigger_is_main_only.

<!-- fr:journal kind=finding scope=plan id=p1a-r9 created=2026-11-15T06:58:38+00:00 phase=1 state=open review_scope=in -->
### p1a-r9 · finding [open] (reviewer: in scope) · One dropped event stranding two refs fires at once, despite 'one repair tolerated' wording (phase 1)

The rule counts repaired refs, not runs. Accept it and document.

<!-- fr:journal kind=finding scope=plan id=p1a-r1-resolved created=2026-11-15T06:58:38+00:00 phase=1 state=fixed resolves=p1a-r1 -->
### p1a-r1-resolved · finding [fixed] · resolves p1a-r1: New rule fires ~15 min after merge on the first-reconcile backfill of 3 kid-laptops sync-pr refs; nothing expects it (phase 1)

Made the expected one-off explicit and useful: a new post-merge op first-reconcile-backfill with a real VictoriaLogs check, a spec Finding and Test Plan row naming the burst as the rule's positive control, and the webhook op moved pre-merge (safe: the live CEL drops kid-laptops PR events until the merge syncs) to shorten the repair-only window.

<!-- fr:journal kind=finding scope=plan id=p1a-r2-resolved created=2026-11-15T06:58:38+00:00 phase=1 state=fixed resolves=p1a-r2 -->
### p1a-r2-resolved · finding [fixed] · resolves p1a-r2: Spec Finding wrong: sync-pr-139 runs molecule as soon as it is mirrored, not after #139 merges (phase 1)

Corrected the spec Finding and plan prose. The molecule-on-pr-head op now targets #139's head immediately after merge, and the /var + DinD watch moved to the post-merge window.

<!-- fr:journal kind=finding scope=plan id=p1a-r3-resolved created=2026-11-15T06:58:38+00:00 phase=1 state=fixed resolves=p1a-r3 -->
### p1a-r3-resolved · finding [fixed] · resolves p1a-r3: Repair-rule LogsQL spoofable by any tekton-pipelines pod; pin container_name:push (phase 1)

Added kubernetes.container_name:push to the rule expr, the guard (test_query_shape parts) and the operating-post query, with a comment naming why the pod name is not pinned. Verified live: container push carries all repair lines.

<!-- fr:journal kind=finding scope=plan id=p1a-r4-resolved created=2026-11-15T06:58:38+00:00 phase=1 state=fixed resolves=p1a-r4 -->
### p1a-r4-resolved · finding [fixed] · resolves p1a-r4: Summary renders the whole value struct ($values.B) (phase 1)

Summary uses $values.B.Value | printf "%.0f"; new test_summary_renders_the_count_not_the_value_struct.

<!-- fr:journal kind=finding scope=plan id=p1a-r5-resolved created=2026-11-15T06:58:38+00:00 phase=1 state=fixed resolves=p1a-r5 -->
### p1a-r5-resolved · finding [fixed] · resolves p1a-r5: building/35 says kid-laptops statuses are not bridged; they are (phase 1)

building/35 now says the statuses are bridged and delivery-checked.

<!-- fr:journal kind=finding scope=plan id=p1a-r6-resolved created=2026-11-15T06:58:38+00:00 phase=1 state=fixed resolves=p1a-r6 -->
### p1a-r6-resolved · finding [fixed] · resolves p1a-r6: tekton.md gives the wrong reason for the runbook's -A (phase 1)

tekton.md names the test_ci_outcome_alert_repeat.py convention as the reason.

<!-- fr:journal kind=finding scope=plan id=p1a-r7-resolved created=2026-11-15T06:58:38+00:00 phase=1 state=fixed resolves=p1a-r7 -->
### p1a-r7-resolved · finding [fixed] · resolves p1a-r7: Gotcha narrates the shared-pipeline masking as historical; it was hypothetical (phase 1)

Phrased conditionally, with the #875 date showing it never occurred.

<!-- fr:journal kind=finding scope=plan id=p1a-r8-resolved created=2026-11-15T06:58:38+00:00 phase=1 state=fixed resolves=p1a-r8 -->
### p1a-r8-resolved · finding [fixed] · resolves p1a-r8: Main-only test is substring presence; an `|| body.ref == ...` would pass (phase 1)

The test asserts the filter ends with `&& body.ref == 'refs/heads/main'` and contains no `||`.

<!-- fr:journal kind=finding scope=plan id=p1a-r9-resolved created=2026-11-15T06:58:38+00:00 phase=1 state=fixed resolves=p1a-r9 -->
### p1a-r9-resolved · finding [fixed] · resolves p1a-r9: One dropped event stranding two refs fires at once, despite 'one repair tolerated' wording (phase 1)

Accepted as designed and documented in the rule comment, operating/22 and tekton.md (counts refs, not runs).

<!-- fr:journal kind=review scope=plan id=lens-review-r1 created=2026-11-15T07:12:52+00:00 -->
### lens-review-r1 · review · Lens review (tests): 5 findings, all in scope, all fixed

One dispatched reviewer for the `tests` lens over d9eca14d..HEAD. It mutation-checked the
guards on a scratch copy. Caught: repo-clause, guard and action weakenings, PR_REPOS and event
removals. Survived: the repair rule's condition/expression chain, `for`, window and an
appended OR. It also found that `kubernetes.container_name:push` is a LogsQL WORD filter. The
orchestrator verified that live: it also matched Tekton's step-pull-from-github-push-to-gitea
(3038 lines over 30d), while `:="push"` matches only the reconciler and returns the same
per-repo series. All five were fixed, and the orchestrator re-ran the mutations against the
new tests: condition B, the word filter, an appended OR, an OR'd same-repo guard and a
removed main-only clause each now fail the suite.

<!-- fr:journal kind=finding scope=plan id=l-tests-r1 created=2026-11-15T07:12:52+00:00 state=open review_scope=in -->
### l-tests-r1 · finding [open] (reviewer: in scope) · repair-rule tests never pin condition C, the A->B->C chain, for: 0s or the B/C windows

scripts/tests/test_mirror_repair_alert.py test_threshold_and_states. condition: B would page on a single repair, reversing q3.

<!-- fr:journal kind=finding scope=plan id=l-tests-r2 created=2026-11-15T07:12:52+00:00 state=open review_scope=in -->
### l-tests-r2 · finding [open] (reviewer: in scope) · kubernetes.container_name:push is a LogsQL word filter that also matches step-pull-and-push etc.; the anti-spoof claim is false

alert-rules-cm.yaml:2432; test_query_shape checks the substring only. Use :="push" and assert it.

<!-- fr:journal kind=finding scope=plan id=l-tests-r3 created=2026-11-15T07:12:52+00:00 state=open review_scope=in -->
### l-tests-r3 · finding [open] (reviewer: in scope) · test_query_shape checks substrings only, so an appended OR clause survives

Assert the whole filter prefix by equality.

<!-- fr:journal kind=finding scope=plan id=l-tests-r4 created=2026-11-15T07:12:52+00:00 state=open review_scope=in -->
### l-tests-r4 · finding [open] (reviewer: in scope) · extract test never shows the push container emits the repair line

It reads the echo from anywhere in mirror-reconcile.yaml. Follow container -> command -> ConfigMap script.

<!-- fr:journal kind=finding scope=plan id=l-tests-r5 created=2026-11-15T07:12:52+00:00 state=open review_scope=in -->
### l-tests-r5 · finding [open] (reviewer: in scope) · pr-sync guard test is substring-only and redundant; no test evaluates the CEL against payloads

test_kid_laptops_mirror_wiring.py:175-181.

<!-- fr:journal kind=finding scope=plan id=l-tests-r1-resolved created=2026-11-15T07:12:52+00:00 state=fixed resolves=l-tests-r1 -->
### l-tests-r1-resolved · finding [fixed] · resolves l-tests-r1: repair-rule tests never pin condition C, the A->B->C chain, for: 0s or the B/C windows

test_expression_chain_windows_and_pending_period pins condition C, reduce(A)/threshold(B), reducer last, all three windows at 21600 and for 0s. Mutation condition:B now fails.

<!-- fr:journal kind=finding scope=plan id=l-tests-r2-resolved created=2026-11-15T07:12:52+00:00 state=fixed resolves=l-tests-r2 -->
### l-tests-r2-resolved · finding [fixed] · resolves l-tests-r2: kubernetes.container_name:push is a LogsQL word filter that also matches step-pull-and-push etc.; the anti-spoof claim is false

Rule, operating post, tekton.md and ops.yaml use kubernetes.container_name:="push". Live-verified that the word form matched step-pull-from-github-push-to-gitea and the exact form returns only the reconciler's per-repo series. The rule comment explains the trap. Mutation back to the word form now fails.

<!-- fr:journal kind=finding scope=plan id=l-tests-r3-resolved created=2026-11-15T07:12:52+00:00 state=fixed resolves=l-tests-r3 -->
### l-tests-r3-resolved · finding [fixed] · resolves l-tests-r3: test_query_shape checks substrings only, so an appended OR clause survives

test_query_shape splits the expr on | and asserts the filter stage and both pipes by equality. Mutation OR _msg:"repaired" now fails.

<!-- fr:journal kind=finding scope=plan id=l-tests-r4-resolved created=2026-11-15T07:12:52+00:00 state=fixed resolves=l-tests-r4 -->
### l-tests-r4-resolved · finding [fixed] · resolves l-tests-r4: extract test never shows the push container emits the repair line

test_the_filtered_container_runs_the_script_that_echoes_the_repair_line walks the CronJob container named in the filter, then its command, the /scripts volume, the ConfigMap and the script, asserts the echo is there, and checks no initContainer script emits it. The extract test now also proves the result summary line is not counted.

<!-- fr:journal kind=finding scope=plan id=l-tests-r5-resolved created=2026-11-15T07:12:52+00:00 state=fixed resolves=l-tests-r5 -->
### l-tests-r5-resolved · finding [fixed] · resolves l-tests-r5: pr-sync guard test is substring-only and redundant; no test evaluates the CEL against payloads

Replaced the substring test with a narrow CEL-subset evaluator (fails loudly on syntax outside the subset) and payload fixtures. R1 covers same-repo opened/synchronize/reopened admitted; fork, null head.repo, closed, labeled and another repo refused. R4 covers main admitted; sync-pr, sync-rerun, ref deletion, another repo and a non-push event refused. Mutations OR-ing the guard (5 fail) and removing the main-only clause (4 fail) are caught.

<!-- fr:journal kind=decision scope=plan id=op-trust-1 created=2026-11-16T19:59:32+00:00 decided_by=operator -->
### op-trust-1 · decision · op-trust: the operator trusted this op set (audit only; never read back)

sha256: 981f71bf55681419aadf39d2a9097aaaca5628f4b27cb2dd98a0ed855f3921fe

<!-- fr:journal kind=op scope=plan id=op-app-webhooks-permission-1 created=2026-11-16T19:59:48+00:00 -->
### op-app-webhooks-permission-1 · op · op app-webhooks-permission: open

op: app-webhooks-permission
result: open
reason: exit 1
phase: pre-merge

<!-- fr:journal kind=op scope=plan id=op-app-webhooks-permission-2 created=2026-11-16T20:01:01+00:00 -->
### op-app-webhooks-permission-2 · op · op app-webhooks-permission: done

op: app-webhooks-permission
result: done
phase: pre-merge

<!-- fr:journal kind=op scope=plan id=op-webhook-pull-request-1 created=2026-11-16T20:01:03+00:00 -->
### op-webhook-pull-request-1 · op · op webhook-pull-request: done

op: webhook-pull-request
result: done
phase: pre-merge

<!-- fr:journal kind=decision scope=plan id=gate-stage-1 created=2026-11-16T20:01:10+00:00 -->
### gate-stage-1 · decision · DevOps stage 1 done: pre-merge ops

head: a432079e0a465b4da539f0a2a5ded2810376e529
pre-merge ops closed on chore/ops-2026-11-15--cicd--kid-laptops-mirror-pr-heads
