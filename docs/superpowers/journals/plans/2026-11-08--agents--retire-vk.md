<!-- fr:journal-schema=3 -->
# Journal: 2026-11-08--agents--retire-vk

<!-- fr:journal kind=decision scope=plan id=p1-pod-dir-exempt-from-reference-scan created=2026-11-08T22:09:07+00:00 phase=1 -->
### p1-pod-dir-exempt-from-reference-scan · decision · Guard test exempts apps/secure-agent-pod from the vk.cluster.derio.net scan (phase 1)

The spec's guard says no apps/ file references vk.cluster.derio.net, but the live pod Deployment (untouched by the HARD INVARIANT) sets two VK URLs on vk-local. test_vk_retired.py therefore skips apps/secure-agent-pod for that scan only; Phase 2 deletes the pod and the exemption together.

<!-- fr:journal kind=decision scope=plan id=p1-fixture-repo-renamed created=2026-11-08T22:09:07+00:00 phase=1 -->
### p1-fixture-repo-renamed · decision · CI budget fixtures renamed vibe-kanban to runs-fr instead of loosened (phase 1)

usage.json and test_ci_budget_watcher.py used vibe-kanban as one of three preferred repos. Renamed it to runs-fr (a surviving github-preferred repo) so all counts and ratios (200/410, 300/410) stay identical. test_ci_status_backfill.py REPO and default_repos assertion moved to runs-fr likewise.

<!-- fr:journal kind=discovery scope=plan id=p1-manual-ops-in-prose created=2026-11-08T22:09:07+00:00 phase=1 -->
### p1-manual-ops-in-prose · discovery · retire-vk manual-operation blocks live in _prose.md, not NN.yaml (phase 1)

The sync-runbook skill greps docs/superpowers/plans/ recursively, so the four blocks in _prose.md were appended to docs/runbooks/manual-operations.yaml (the file is chronological, not sorted, so appended at the end). vibe-kanban-dispatch-pat is status: decommissioned in both the 2026-04-15 plan block and the runbook, following the Paperclip precedent.

<!-- fr:journal kind=discovery scope=plan id=p1-deliberate-leftovers created=2026-11-08T22:09:07+00:00 phase=1 -->
### p1-deliberate-leftovers · discovery · Deliberate Phase 2 / historical leftovers after grep accounting (phase 1)

Remaining hits: everything under apps/secure-agent-pod (Deployment VK env, service-vibekanban.yaml, disabled cilium egress); agents/rules/frank-infrastructure.md pod row (spec: waits for Phase 2); README pod rows; frank-gotchas lines marked HISTORICAL; the PGDATA gotcha and a hermes Deployment comment citing apps/vk-remote as a past precedent; the tombstone slug in the Authentik blueprint; the tekton generator comment; test files naming VK to guard its absence. The deployment.yaml diff against origin/main is empty; the only apps/secure-agent-pod change is the generator file moving out.

<!-- fr:journal kind=discovery scope=plan id=p1-silences-and-deleterules created=2026-11-08T22:09:07+00:00 phase=1 -->
### p1-silences-and-deleterules · discovery · Alerts removed via deleteRules plus dashboard selector edit (phase 1)

Layer 18 keeps three heartbeats (exercise_reminder, session_manager, audit_digest); Phase 2 owns them. The Layer 15 namespace regex dropped the agents namespace, and the notification-policy comment now notes the original health_bridge_only first user was retired.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t1 created=2026-11-08T22:09:07+00:00 phase=1 -->
### no-refactor-p1-t1 · discovery · no-refactor-because P1.T1 (phase 1)

A single new guard test file with no duplicated helpers; nothing to clean.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t2 created=2026-11-08T22:09:07+00:00 phase=1 -->
### no-refactor-p1-t2 · discovery · no-refactor-because P1.T2 (phase 1)

Pure deletions plus tombstones; no logic left to simplify.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t3 created=2026-11-08T22:09:07+00:00 phase=1 -->
### no-refactor-p1-t3 · discovery · no-refactor-because P1.T3 (phase 1)

Pure deletions and tombstones copied from the Ruflo shape; nothing to clean.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t5 created=2026-11-08T22:09:07+00:00 phase=1 -->
### no-refactor-p1-t5 · discovery · no-refactor-because P1.T5 (phase 1)

List edits only; counts in tests changed with the removed repo, and the fixture repo was renamed rather than counts loosened.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t6 created=2026-11-08T22:09:07+00:00 phase=1 -->
### no-refactor-p1-t6 · discovery · no-refactor-because P1.T6 (phase 1)

The vkr parameter was removed end to end (workflow, collect, legacy_body, CLI, tests), leaving no dead plumbing.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t7 created=2026-11-08T22:09:07+00:00 phase=1 -->
### no-refactor-p1-t7 · discovery · no-refactor-because P1.T7 (phase 1)

Doc edits only; nothing duplicated.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t8 created=2026-11-08T22:09:07+00:00 phase=1 -->
### no-refactor-p1-t8 · discovery · no-refactor-because P1.T8 (phase 1)

Refactor task: grep-accounted every remaining VK hit (removed, marked historical, or deliberate Phase 2 leftover) and found no duplication introduced by the edits.

<!-- fr:journal kind=finding scope=plan id=p1-r1 created=2026-11-08T22:40:56+00:00 phase=1 state=open review_scope=in -->
### p1-r1 · finding [open] (reviewer: in scope) · agent-images-bump.yml Update manifests step ended in a bare && list and exited 1 on every normal bump (phase 1)

Removing the vk-remote block made `[ -n "$SKIPPED" ] && echo` the step's last command. Reproduced rc=1 under bash -e. Text guards could not see it.

<!-- fr:journal kind=finding scope=plan id=p1-r2 created=2026-11-08T22:40:56+00:00 phase=1 state=open review_scope=in -->
### p1-r2 · finding [open] (reviewer: in scope) · sweep-grafana-restart check matched the new tombstones and could never pass (phase 1)

The runbook's grep -c gate also returned 1 before and after the sync.

<!-- fr:journal kind=finding scope=plan id=p1-r3 created=2026-11-08T22:40:56+00:00 phase=1 state=open review_scope=in -->
### p1-r3 · finding [open] (reviewer: in scope) · ops.yaml omitted the pre-merge pod diff and the stale-revision check before the sweeps (phase 1)

Test Plan row 0 had no runnable check, and a stale Application would undo the sweeps.

<!-- fr:journal kind=finding scope=plan id=p1-r4 created=2026-11-08T22:40:56+00:00 phase=1 state=open review_scope=in -->
### p1-r4 · finding [open] (reviewer: in scope) · pod-baseline.txt format differed between the runbook and ops.yaml (phase 1)

A false R7 failure at step-2, and the all-container form broke R7's vk-local tolerance.

<!-- fr:journal kind=finding scope=plan id=p1-r5 created=2026-11-08T22:40:56+00:00 phase=1 state=open review_scope=in -->
### p1-r5 · finding [open] (reviewer: in scope) · step-5 read ExternalSecret status immediately and never proved a refresh (phase 1)

It could read the pre-refresh status.

<!-- fr:journal kind=finding scope=plan id=p1-r6 created=2026-11-08T22:40:56+00:00 phase=1 state=open review_scope=in -->
### p1-r6 · finding [open] (reviewer: in scope) · Negated kubectl checks passed on any API or kubeconfig error (phase 1)

A dead kubeconfig read as success.

<!-- fr:journal kind=finding scope=plan id=p1-r7 created=2026-11-08T22:40:56+00:00 phase=1 state=open review_scope=in -->
### p1-r7 · finding [open] (reviewer: in scope) · Stale comments on health_bridge_only users, the generator key namespace and kali examples (phase 1)

Comments named the wrong rules and the wrong namespace.

<!-- fr:journal kind=finding scope=plan id=p1-r8 created=2026-11-08T22:40:56+00:00 phase=1 state=open review_scope=in -->
### p1-r8 · finding [open] (reviewer: in scope) · README still listed VK Relay (phase 1)

The relay was removed with vk-remote.

<!-- fr:journal kind=finding scope=plan id=p1-r9 created=2026-11-08T22:40:56+00:00 phase=1 state=open review_scope=in -->
### p1-r9 · finding [open] (reviewer: in scope) · test_vk_retired.py exemptions were wider than needed and the R7 pin and OLD_AI_SHA source were unguarded (phase 1)

An accidental bump of the pod's pin would have passed.

<!-- fr:journal kind=finding scope=plan id=p1-r10 created=2026-11-08T22:40:56+00:00 phase=1 state=open review_scope=in -->
### p1-r10 · finding [open] (reviewer: in scope) · Bump branch is unique per SHA rather than per run as specified (phase 1)

The deviation was not recorded.

<!-- fr:journal kind=finding scope=plan id=p1-r11 created=2026-11-08T22:40:56+00:00 phase=1 state=open review_scope=in -->
### p1-r11 · finding [open] (reviewer: in scope) · HISTORICAL wording said vk-local was retired while the container still runs (phase 1)

It lingers idle until Phase 2.

<!-- fr:journal kind=review scope=plan id=review-phase-1 created=2026-11-08T22:40:56+00:00 phase=1 -->
### review-phase-1 · review · independent code review: 11 findings, all in scope (phase 1)

Dispatched reviewer parsed the alert rules, compared the CEL filters, ran the bump step under bash -e, and checked generator ownership and ops selectors. It found one critical (p1-r1), three important and seven minor. R6 and R7 mechanics were sound. Its 22 test failures in an archive copy came from tests needing .git; the full suite in the real checkout is the evidence for the fixed tree.

<!-- fr:journal kind=finding scope=plan id=p1-r1-resolved created=2026-11-08T22:40:56+00:00 phase=1 state=fixed resolves=p1-r1 -->
### p1-r1-resolved · finding [fixed] · resolves p1-r1: agent-images-bump.yml Update manifests step ended in a bare && list and exited 1 on every normal bump (phase 1)

Replaced with an if. test_bump_step_exits_zero_when_nothing_is_skipped runs the step under bash -e and was red before the fix.

<!-- fr:journal kind=finding scope=plan id=p1-r2-resolved created=2026-11-08T22:40:56+00:00 phase=1 state=fixed resolves=p1-r2 -->
### p1-r2-resolved · finding [fixed] · resolves p1-r2: sweep-grafana-restart check matched the new tombstones and could never pass (phase 1)

The check asserts tombstone present and definition absent; the runbook gate uses the tombstone.

<!-- fr:journal kind=finding scope=plan id=p1-r3-resolved created=2026-11-08T22:40:56+00:00 phase=1 state=fixed resolves=p1-r3 -->
### p1-r3-resolved · finding [fixed] · resolves p1-r3: ops.yaml omitted the pre-merge pod diff and the stale-revision check before the sweeps (phase 1)

Added premerge-pod-diff and sweep-revisions, with sweeps depending on it. Pushgateway, silence cleanup and fork archive stay prose-only manual operations in _prose.md, on purpose: they touch external services or are conditional, and Test Plan rows 5 and 6 are operator-verified.

<!-- fr:journal kind=finding scope=plan id=p1-r4-resolved created=2026-11-08T22:40:56+00:00 phase=1 state=fixed resolves=p1-r4 -->
### p1-r4-resolved · finding [fixed] · resolves p1-r4: pod-baseline.txt format differed between the runbook and ops.yaml (phase 1)

Both procedures use the kali-filtered jsonpath and the app label.

<!-- fr:journal kind=finding scope=plan id=p1-r5-resolved created=2026-11-08T22:40:56+00:00 phase=1 state=fixed resolves=p1-r5 -->
### p1-r5-resolved · finding [fixed] · resolves p1-r5: step-5 read ExternalSecret status immediately and never proved a refresh (phase 1)

Apply waits, and the check compares refreshTime with the force-sync annotation.

<!-- fr:journal kind=finding scope=plan id=p1-r6-resolved created=2026-11-08T22:40:56+00:00 phase=1 state=fixed resolves=p1-r6 -->
### p1-r6-resolved · finding [fixed] · resolves p1-r6: Negated kubectl checks passed on any API or kubeconfig error (phase 1)

Checks capture output with --ignore-not-found and require kubectl to succeed before asserting empty.

<!-- fr:journal kind=finding scope=plan id=p1-r7-resolved created=2026-11-08T22:40:56+00:00 phase=1 state=fixed resolves=p1-r7 -->
### p1-r7-resolved · finding [fixed] · resolves p1-r7: Stale comments on health_bridge_only users, the generator key namespace and kali examples (phase 1)

Comments corrected in the notification policy, canary test, both generators and the bump workflow.

<!-- fr:journal kind=finding scope=plan id=p1-r8-resolved created=2026-11-08T22:40:56+00:00 phase=1 state=fixed resolves=p1-r8 -->
### p1-r8-resolved · finding [fixed] · resolves p1-r8: README still listed VK Relay (phase 1)

Row removed.

<!-- fr:journal kind=finding scope=plan id=p1-r9-resolved created=2026-11-08T22:40:56+00:00 phase=1 state=fixed resolves=p1-r9 -->
### p1-r9-resolved · finding [fixed] · resolves p1-r9: test_vk_retired.py exemptions were wider than needed and the R7 pin and OLD_AI_SHA source were unguarded (phase 1)

The exemption is the Deployment file only, the state-absent exemption is gone, the pin is the exact SHA, and a test asserts the OLD_AI_SHA source.

<!-- fr:journal kind=finding scope=plan id=p1-r10-resolved created=2026-11-08T22:40:56+00:00 phase=1 state=fixed resolves=p1-r10 -->
### p1-r10-resolved · finding [fixed] · resolves p1-r10: Bump branch is unique per SHA rather than per run as specified (phase 1)

Spec amended to unique per SHA, which is what the workflow's own comment intends: an open PR for that SHA is skipped.

<!-- fr:journal kind=finding scope=plan id=p1-r11-resolved created=2026-11-08T22:40:56+00:00 phase=1 state=fixed resolves=p1-r11 -->
### p1-r11-resolved · finding [fixed] · resolves p1-r11: HISTORICAL wording said vk-local was retired while the container still runs (phase 1)

The historical note says vk-local lingers idle until Phase 2.

<!-- fr:journal kind=discovery scope=plan id=p2-live-sweep-2026-11-12 created=2026-11-12T12:44:38+00:00 phase=2 -->
### p2-live-sweep-2026-11-12 · discovery · Phase 1 live sweep ran three days after the merge, by hand (phase 2)

PR949 merged 2026-11-09 21:03 UTC and the post-merge sweep did not run until 2026-11-12. In that gap the vk-remote IngressRoute kept existing, Grafana (pod started 2026-11-03) still held all three VK rules and the old Layer 18 clause behind two silences, and the vk_issue_bridge pushgateway group persisted. traefik-extras reported a current sync revision while its last sync operation dated from 2026-08-02 at 920c9da, because a git deletion under prune false gives auto-sync nothing to apply.

`fr ops gate` refuses a non-interactive caller, so the ops were run one command at a time by an agent session under the operator's authorization and recorded with `fr closeout outcome`. The spec's Test Plan numbers its rows from 0 and fr numbers steps by position, so fr step N is spec row N-1; steps 1-4 carry a superseding entry for that reason.

Still owed: merging derio-net/agent-images#176 (branch build 43217543292 green at b6de16b; the agent session was refused the merge), the bump run that follows, the fork webhook delete and archive, and removing the four VK_REMOTE_ keys from Infisical.

<!-- fr:journal kind=discovery scope=plan id=p2-fork-archive-2026-11-12 created=2026-11-12T17:12:09+00:00 phase=2 -->
### p2-fork-archive-2026-11-12 · discovery · Fork archived; Infisical VK_REMOTE keys still owed by the operator (phase 2)

agent-images#176 merged as fe2fb9b, main build 43260930622 and Frank bump run 43264032464 are green, the fork webhook is deleted and derio-net/vibe-kanban is archived. Manual op agents-retire-vk-fork-archive is marked done for those parts. One command of that op is NOT done: removing VK_REMOTE_JWT_SECRET, VK_REMOTE_LOCAL_AUTH_PASSWORD, VK_REMOTE_ELECTRIC_PASSWORD and VK_REMOTE_PG_PASSWORD from Infisical. It needs the Infisical UI and is owed by the operator. VK_ORG_ID and VK_DERIO_OPS_PROJECT_ID stay until Phase 2.
