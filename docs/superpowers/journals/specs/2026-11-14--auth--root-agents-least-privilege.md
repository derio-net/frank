<!-- fr:journal-schema=4 -->
# Journal: 2026-11-14--auth--root-agents-least-privilege

<!-- fr:journal kind=discovery scope=spec id=brief-frank-912 created=2026-11-14T20:15:40+00:00 input=true -->
### brief-frank-912 · discovery · Operator brief: frank#912, scope root-agents down from cluster-admin

Issue derio-net/frank#912 plus its two comments, and the session brief.
Comment 1: #950 (Retire VK, Phase 2) removes secure-agent-pod, deleting ServiceAccount
agent-sa and its secure-agent-pod-cluster-admin binding (half of this issue); the
authentik-root-agents binding is cluster-scoped and must be deleted separately.
Comment 2: blocks the credential steps of #913 (operator decision 2026-11-12): no upgrade-session
credential (Omni upgrade SA key, Hop talosconfig/kubeconfig, session GitHub App PEM, tailscale
keys) is applied until this closes; enforced as P7.T1.S1. Two parts: (1) agent-sa goes with #950;
(2) root-agents -> cluster-admin (authentik-root-agents) needs its own least-privilege change.
Done when `kubectl auth can-i get secrets -n upgrade-sessions` answers no for agent-sa and for a
member of root-agents.
Brief: agent-sa and its binding are already gone (#955). Remaining is authentik-root-agents.
Human root-devops stays trusted. Target shape: cluster-wide read (no Secrets) + namespaced write
where needed; no access to upgrade-sessions, cluster-update-fr, runs-fr; no impersonate,
serviceaccounts/token, escalate/bind; plus a CI guard test. can-i --as is vacuous through the Omni
proxy (#963): prove with server-side SubjectAccessReview and a system:masters control. Plan a staged
rollout with a live SAR matrix before/after and a quick revert path.
Mid-run orchestrator note: the 2026-08-02 TokenReview of the k8s-agent token showed groups
[system:authenticated] only; re-verify and check Authentik membership read-only; do not re-ask.

<!-- fr:journal kind=decision scope=spec id=q1-agent-access created=2026-11-14T20:15:40+00:00 decided_by=operator -->
### q1-agent-access · decision · Agent access is read-only, no Secrets

Operator answer, round 1 question 1: read-only (cluster-scoped plus namespaced get/list/watch),
no Secrets, no write anywhere. decider: operator.

<!-- fr:journal kind=decision scope=spec id=q2-binding-shape created=2026-11-14T20:15:40+00:00 decided_by=operator -->
### q2-binding-shape · decision · Per-namespace RoleBindings plus a cluster-scoped-read ClusterRole

Operator answer, round 1 question 2: one generated RoleBinding per host app namespace minus the
three protected ones; a ClusterRoleBinding only for cluster-scoped reads; CI guard fails on
drift. decider: operator.

<!-- fr:journal kind=decision scope=spec id=q3-rollout created=2026-11-14T20:15:40+00:00 decided_by=operator -->
### q3-rollout · decision · Add new binding, prove with SAR matrix, then delete the old one

Operator answer, round 1 question 3: staged cutover. The old authentik-root-agents binding is
deleted by hand after the matrix passes (roleRef is immutable and prune is false).
decider: operator.

<!-- fr:journal kind=decision scope=spec id=q4-verification created=2026-11-14T20:15:40+00:00 decided_by=operator -->
### q4-verification · decision · Verification strategy live, gate devops

Operator answer, round 1 question 4: strategy live, gate devops, static CI guard pre-merge.
decider: operator.

<!-- fr:journal kind=discovery scope=spec id=authentik-root-agents-empty created=2026-11-14T20:15:40+00:00 -->
### authentik-root-agents-empty · discovery · root-agents has no members; the AI identity sits in root-admins

Read-only Authentik ORM query 2026-11-14: root-agents members none; root-admins members
claude-agent (service_account) and akadmin; the k8s-agent provider's profile scope mapping
emits a groups claim. So the binding grants nothing today and the real exposure is
claude-agent in root-admins (cluster-admin) reachable by requesting the profile scope. A fresh
TokenReview was not run (.env_agent absent on this host). Operator then chose, in the
second answered round, to move claude-agent from root-admins to root-agents as a devops-gated
live step (spec R5) and confirmed the four earlier answers as one design; decider: operator.
Revert is re-adding claude-agent to root-admins.

<!-- fr:journal kind=lens scope=spec id=lens-security-1 created=2026-11-14T20:15:40+00:00 lens=security step=brainstorm -->
### lens-security-1 · lens · RBAC scoping change on a credential boundary; examine for escalation paths

<!-- fr:journal kind=finding scope=spec id=s1 created=2026-11-14T20:18:11+00:00 state=open review_scope=in -->
### s1 · finding [open] (reviewer: in scope) · _destinations() includes Hop apps; RoleBindings would target nonexistent namespaces

life_sessions.py:84-93 filters only destination.name; life_policy walks frank+hop roots. Spec now keeps frank/* keys only (R6).

<!-- fr:journal kind=finding scope=spec id=s2 created=2026-11-14T20:18:11+00:00 state=open review_scope=in -->
### s2 · finding [open] (reviewer: in scope) · test_the_repo_binds_these_admin_subjects will fail after deleting the binding

test_life_admission_cel.py:342-347 set equality. Spec now lists the test and comment updates under Coupled files.

<!-- fr:journal kind=finding scope=spec id=s3 created=2026-11-14T20:18:11+00:00 state=open review_scope=in -->
### s3 · finding [open] (reviewer: in scope) · Docs and test coupling to the known-gap text unstated

test_life_briefs.py:257-266, rbac.yaml header, upgrade-briefs AGENTS/CLAUDE.md, blog post. Added R8 and Coupled files.

<!-- fr:journal kind=finding scope=spec id=s4 created=2026-11-14T20:18:11+00:00 state=open review_scope=in -->
### s4 · finding [open] (reviewer: in scope) · Guard's allowed admin set too narrow, flags legitimate ServiceAccounts

R7 now: Group subjects outside the admin groups, plus an explicit named ServiceAccount allowlist; Roles and ClusterRoles followed.

<!-- fr:journal kind=finding scope=spec id=s5 created=2026-11-14T20:18:11+00:00 state=open review_scope=in -->
### s5 · finding [open] (reviewer: in scope) · view aggregation and sensitive namespaces unexamined

Replaced view with explicit ClusterRole root-agents-ns-read (R2); sensitive-namespace reads stated as deliberate; matrix gains Secrets-denied cells there.

<!-- fr:journal kind=finding scope=spec id=s6 created=2026-11-14T20:18:11+00:00 state=open review_scope=in -->
### s6 · finding [open] (reviewer: in scope) · Moving claude-agent drops Authentik superuser; cutover ordering and token staleness

Cutover reordered (move membership, then delete the binding), superuser pre-check, fresh-token TokenReview step added.

<!-- fr:journal kind=finding scope=spec id=s7 created=2026-11-14T20:18:11+00:00 state=open review_scope=out -->
### s7 · finding [open] (reviewer: out of scope) · Matrix cells assumed, not cited

Precision nit; the spec now derives the allowed cells from the generated file anyway.

<!-- fr:journal kind=review scope=spec id=spec-review created=2026-11-14T20:18:11+00:00 -->
### spec-review · review · independent spec review: 7 findings

Reviewer verified k8s-rbac.yaml, blueprints-groups.yaml, life_sessions.py, life_policy.py, the CEL test, test_life_briefs and the acceptance rows against the spec; found 6 in-scope defects and 1 out-of-scope note. View aggregation could not be inspected live.

<!-- fr:journal kind=lens scope=spec id=lens-tests-1 created=2026-11-14T20:18:11+00:00 lens=tests step=spec-review -->
### lens-tests-1 · lens · Guard and existing set-equality tests need explicit update coverage

<!-- fr:journal kind=finding scope=spec id=s1-resolved created=2026-11-14T20:18:11+00:00 state=fixed resolves=s1 -->
### s1-resolved · finding [fixed] · resolves s1: _destinations() includes Hop apps; RoleBindings would target nonexistent namespaces

Fixed in the spec.

<!-- fr:journal kind=finding scope=spec id=s2-resolved created=2026-11-14T20:18:11+00:00 state=fixed resolves=s2 -->
### s2-resolved · finding [fixed] · resolves s2: test_the_repo_binds_these_admin_subjects will fail after deleting the binding

Fixed in the spec.

<!-- fr:journal kind=finding scope=spec id=s3-resolved created=2026-11-14T20:18:11+00:00 state=fixed resolves=s3 -->
### s3-resolved · finding [fixed] · resolves s3: Docs and test coupling to the known-gap text unstated

Fixed in the spec.

<!-- fr:journal kind=finding scope=spec id=s4-resolved created=2026-11-14T20:18:11+00:00 state=fixed resolves=s4 -->
### s4-resolved · finding [fixed] · resolves s4: Guard's allowed admin set too narrow, flags legitimate ServiceAccounts

Fixed in the spec.

<!-- fr:journal kind=finding scope=spec id=s5-resolved created=2026-11-14T20:18:11+00:00 state=fixed resolves=s5 -->
### s5-resolved · finding [fixed] · resolves s5: view aggregation and sensitive namespaces unexamined

Fixed in the spec.

<!-- fr:journal kind=finding scope=spec id=s6-resolved created=2026-11-14T20:18:11+00:00 state=fixed resolves=s6 -->
### s6-resolved · finding [fixed] · resolves s6: Moving claude-agent drops Authentik superuser; cutover ordering and token staleness

Fixed in the spec.

<!-- fr:journal kind=finding scope=spec id=s7-resolved created=2026-11-14T20:18:11+00:00 state=open resolves=s7 out_of_scope=true -->
### s7-resolved · finding [out-of-scope] · resolves s7: Matrix cells assumed, not cited

Precision nit not caused by this change; matrix cells are now derived from the generated file.

<!-- fr:journal kind=decision scope=spec id=exit-baseline created=2026-11-14T20:18:13+00:00 -->
### exit-baseline · decision · exit when spec-review resolved

The exit when spec-review resolved; `fr verification set` and `deliver` compare against it.

```yaml
row_gates:
  no-ai-agent-cluster-admin: devops
  root-agents-no-secrets: devops
  root-agents-read-only-triage: devops
row_kinds:
  no-ai-agent-cluster-admin: live
  root-agents-no-secrets: live
  root-agents-read-only-triage: live
run_gate: devops
run_kind: live
```

<!-- fr:journal kind=finding scope=spec id=s7-resolved-2 created=2026-11-14T21:20:17+00:00 state=open resolves=s7 tracked_by=https://github.com/derio-net/frank/issues/986 -->
### s7-resolved-2 · finding [deferred → https://github.com/derio-net/frank/issues/986] · resolves s7: Matrix cells assumed, not cited

Filed at deliver as https://github.com/derio-net/frank/issues/986.

<!-- fr:journal kind=discovery scope=spec id=test-plan-step-1 created=2026-11-16T12:09:53+00:00 -->
### test-plan-step-1 · discovery · Test Plan step 1: ran

Step: [ ] (op: premerge-namespaces) Before merging, confirm every generated namespace exists live.

Evidence: checked after the merge by hand not before, all 30 generated namespaces exist on the live cluster, read-only run from main at 1002

<!-- fr:journal kind=discovery scope=spec id=test-plan-step-2 created=2026-11-16T12:11:00+00:00 -->
### test-plan-step-2 · discovery · Test Plan step 2: ran

Step: [x] BEFORE matrix (recorded 2026-11-14, before the cutover, not an op: it can only be taken before the old binding is deleted): all 14 `root-agents` deny cells leaked through the live `cluster-admin` binding and every `system:masters` control answered allowed.

Evidence: taken live on 2026-11-14 before the old binding was deleted, all 14 root-agents deny cells leaked through the cluster-admin binding and every system:masters control answered allowed, raw output was in the delivering session and not committed
