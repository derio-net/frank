# Scope AI-agent cluster access down from cluster-admin: plan

One agentic phase delivers everything the repo can hold: the generated per-namespace
RoleBindings, the two explicit read ClusterRoles, the removal of the cluster-admin
binding from git, the static guard and the coupled test and doc updates. The live half
(SubjectAccessReview matrices, Authentik membership move of `claude-agent`, deleting the
old binding by hand because prune is false) is the spec's devops-gated Test Plan, carried
as ops, not as a phase. One phase is enough: every piece is one reviewable ask (R1-R8).
