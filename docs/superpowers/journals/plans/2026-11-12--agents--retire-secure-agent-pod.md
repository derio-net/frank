<!-- fr:journal-schema=3 -->
# Journal: 2026-11-12--agents--retire-secure-agent-pod

<!-- fr:journal kind=decision scope=plan id=plan-one-agentic-phase created=2026-11-12T12:40:23+00:00 -->
### plan-one-agentic-phase · decision · One agentic phase for all git-state work, one back-loaded manual phase for the live sequence

R9-R15's git changes (removal, tombstones, tripwire, archive script, blog notices) are one
reviewable ask: retire the pod from git. The live sequence (archive, gates, merge, sweep,
explicit ClusterRoleBinding delete) is a back-loaded [manual] phase with 14 ops, because
the operator said the triage run is still going and no agentic phase may touch the pod.

<!-- fr:journal kind=discovery scope=plan id=plan-live-facts-2026-11-12 created=2026-11-12T12:40:23+00:00 -->
### plan-live-facts-2026-11-12 · discovery · Live state read on 2026-11-12 (read-only)

root Application: automated {prune: true, selfHeal: true}. ClusterGenerator
github-app-derio tracking id is already tekton-extras. ClusterRoleBinding
secure-agent-pod-cluster-admin exists and is tracked by the secure-agent-pod Application.
tekton-pipelines/github-app-derio-key exists (created 2026-07-25). The five rule uids are
present in the running Grafana (GET /api/v1/provisioning/alert-rules via the .203
LoadBalancer with the admin secret). Pushgateway is ClusterIP only. Pod home layout:
interviews 64M, orgs 77M, .hermes 424K, .willikins-agent/audit-archive,
.local/share/vibe-kanban/db.v2.sqlite, 12 git clones. agent-images#176 and bump PR
frank#953 are open.
