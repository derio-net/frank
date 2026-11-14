# Scope AI-agent cluster access down from cluster-admin: plan

One agentic phase delivers everything the repo can hold: the generated per-namespace
RoleBindings, the two explicit read ClusterRoles, the removal of the cluster-admin
binding from git, the static guard and the coupled test and doc updates. The live half
(SubjectAccessReview matrices, Authentik membership move of `claude-agent`, deleting the
old binding by hand because prune is false) is the spec's devops-gated Test Plan, carried
as ops, not as a phase. One phase is enough: every piece is one reviewable ask (R1-R8).

## Cutover manual operation

The live half, run by the operator after merge (the devops-gate ops call `scripts/root-agents-cutover.sh`).

```yaml
# manual-operation
id: auth-root-agents-cutover
layer: auth
app: authentik-extras
plan: 2026-11-14--auth--root-agents-least-privilege
when: After the PR merges and ArgoCD applies the new bindings (devops gate)
why_manual: Authentik group membership lives in the running Authentik database, and prune is false so the old cluster-admin binding must be deleted by hand
commands: |
  source .env   # from the repo root, so KUBECONFIG resolves
  kubectl get ns -o name   # every namespace in apps/authentik-extras/manifests/root-agents-rbac.yaml must exist, or that sync fails
  Check what claude-agent uses its Authentik superuser status for (API calls with its token): leaving root-admins drops is_superuser, not only the kube binding
  bash scripts/root-agents-cutover.sh matrix   # BEFORE: server-side SubjectAccessReview matrix for groups root-agents and root-admins, each beside a system:masters control that must answer allowed (never kubectl auth can-i --as: the Omni proxy ignores it, frank#963)
  bash scripts/root-agents-cutover.sh move-membership   # Authentik ORM: add claude-agent to root-agents, then remove it from root-admins
  bash scripts/root-agents-cutover.sh token-review   # mints a fresh k8s-agent token from .env_agent, TokenReviews it, prints only the groups; root-admins must be absent
  kubectl delete clusterrolebinding authentik-root-agents --ignore-not-found   # prune is false, so git alone leaves it live
  bash scripts/root-agents-cutover.sh matrix   # AFTER
  REVERT (any step failing): kubectl apply the old binding from `git show <merge>~1:apps/authentik-extras/manifests/k8s-rbac.yaml` (the authentik-root-agents document), and re-add claude-agent to root-admins in Authentik
verify: |
  bash scripts/root-agents-cutover.sh verify exits 0: every allow cell allowed, every deny cell denied (Secrets in argocd, infisical, authentik, kube-system, longhorn-system, upgrade-sessions, cluster-update-fr, runs-fr), and the system:masters control allowed
  bash scripts/root-agents-cutover.sh membership exits 0: claude-agent is only in root-agents
  kubectl get clusterrolebinding authentik-root-agents is NotFound
status: pending
```
