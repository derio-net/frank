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
