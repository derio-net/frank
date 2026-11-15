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
