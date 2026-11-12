# Retire secure-agent-pod (retire VK, Phase 2)

**Status:** In Progress
**Layer:** agents
**Spec:** `docs/superpowers/specs/2026-11-08--agents--retire-vk-design.md`

This plan implements requirements R9-R15: the pod, its namespace, 50Gi PVC, three
LoadBalancers and the `agent-sa` cluster-admin binding go away, with the alert rules
tombstoned, the blog posts marked superseded, and the archive script shipped.

Two rules shape it:

- **Nothing agentic touches the live cluster.** Phase 1 changes git only. The merge
  that triggers the cascade, the archive, and every sweep step are Phase 2, run by
  the operator. R9 holds the PR in draft until the triage run on the pod has ended
  and the archive is verified in `~/Archives/secure-agent-pod-2026-11`.
- **The cluster-admin binding is deleted explicitly.** `secure-agent-pod-cluster-admin`
  is cluster-scoped and outlives a namespace delete. frank#912 requires it gone, and
  asserted gone, before frank#913's upgrade sessions hold credentials.

The `derio-net/agent-images` PR that removes the `kali` build leg is separate and
merges after this one, as in Phase 1.

`scripts/tests/fixtures/life/pin-exceptions.yaml` arrives with frank#913. Whichever of
#913 and this PR merges second removes its `vk-local` and `secure-agent-kali` entries.

## Reviving chorebot (R15)

chorebot and the pod's other crons stop with the pod and are not migrated. To revive
chorebot, redeploy `scripts/chorebot` from `derio-net/willikins` as its own workload.
Its data is in Notion. Its `config.yaml` is not in git; the only copy after the
teardown is in the archive, which stays off git and off shared storage because the
file may hold tokens.

## Manual operations

```yaml
# manual-operation
id: agents-retire-pod-archive
layer: agents
app: secure-agent-pod
plan: docs/superpowers/plans/2026-11-12--agents--retire-secure-agent-pod
when: Before the Phase 2 PR leaves draft, once the triage run on the pod has ended
why_manual: The files exist only on the pod's PVC, the archive may hold tokens so it must land on the operator's Mac, and only the operator can say the session has ended.
commands:
  - bash scripts/retire-secure-agent-pod.sh archive
  - bash scripts/retire-secure-agent-pod.sh verify
verify:
  - verify prints PASS for every check and exits 0.
  - ~/Archives/secure-agent-pod-2026-11 is mode 0700 and its tarball lists repos/willikins/scripts/chorebot/config.yaml.
  - The operator has opened the archive and is satisfied nothing else on the pod is worth keeping.
status: pending
```

```yaml
# manual-operation
id: agents-retire-pod-premerge
layer: agents
app: secure-agent-pod
plan: docs/superpowers/plans/2026-11-12--agents--retire-secure-agent-pod
when: Before merging the Phase 2 PR, after the archive is verified
why_manual: The gates read live cluster state and a SOPS-decrypted key, and the silence must exist before the pod stops pushing heartbeats.
commands:
  - |-
    kubectl get clustergenerator github-app-derio -o jsonpath='{.metadata.annotations.argocd\.argoproj\.io/tracking-id}'  # must start with tekton-extras:
  - |-
    kubectl -n argocd get application secure-agent-pod -o jsonpath='{.status.resources[*].kind}'  # must not list ClusterGenerator
  - bash scripts/retire-secure-agent-pod.sh key-fingerprint
  - |-
    kubectl -n argocd get application root -o jsonpath='{.spec.syncPolicy.automated.prune}'  # must print true
  - Create one Grafana silence (Alerting, Silences) matching alertname or rule uid for exercise-reminder-stale, session-manager-stale, audit-digest-stale, agent-pod-not-running and layer-18-persistent-agent-degraded, expiring in 48 hours. Note its id.
verify:
  - The generator's tracking id is tekton-extras and the Application does not track it.
  - key-fingerprint reports the Tekton copy equal to both SOPS files.
  - root reports prune true.
  - The silence is active.
status: pending
```

```yaml
# manual-operation
id: agents-retire-pod-postmerge-sweep
layer: agents
app: secure-agent-pod
plan: docs/superpowers/plans/2026-11-12--agents--retire-secure-agent-pod
when: After the Phase 2 PR merges
why_manual: The cascade must be observed on live artifacts, a ClusterRoleBinding survives a namespace delete, Grafana reads provisioning only at boot, and prune false leaves the dashboard ConfigMap behind.
commands:
  - Start a sync operation on root (with prune true), grafana-alerting and victoria-metrics, passing ServerSideApply=true and RespectIgnoreDifferences=true. Then confirm on root and grafana-alerting that status.operationState.phase is Succeeded and status.operationState.syncResult.revision contains the merge SHA.
  - kubectl -n argocd get application secure-agent-pod --ignore-not-found
  - kubectl get ns secure-agent-pod --ignore-not-found
  - kubectl delete clusterrolebinding secure-agent-pod-cluster-admin --ignore-not-found
  - kubectl auth can-i get secrets -n upgrade-sessions --as=system:serviceaccount:secure-agent-pod:agent-sa
  - |-
    kubectl -n monitoring get cm grafana-alerting-rules -o yaml | grep 'orgId: 1, uid: agent-pod-not-running'  # the tombstone proves the sync; restart only once this matches
  - kubectl -n monitoring rollout restart deploy/victoria-metrics-grafana
  - Delete the retained exercise_reminder, session_manager and audit_digest groups from the pushgateway (DELETE /metrics/job/<job> on the pushgateway Service in monitoring).
  - kubectl -n monitoring delete configmap grafana-secure-agent-pod-dashboard --ignore-not-found
  - Delete the silence created before the merge once the Grafana API lists none of the five rule uids.
verify:
  - The Application and the namespace are NotFound, the agent-home PV is gone, and no Service holds 192.168.55.215, .218 or .219.
  - kubectl get clusterrolebinding secure-agent-pod-cluster-admin is NotFound and the auth can-i check prints no.
  - GET /api/v1/provisioning/alert-rules on Grafana lists none of the five uids.
  - The pushgateway serves no exercise_reminder, session_manager or audit_digest group.
  - kubectl -n monitoring get configmap grafana-secure-agent-pod-dashboard is NotFound.
  - At least an hour after the silence was deleted, no alert has fired because of the removal and frank-gitops-push is still SecretSynced with a token refreshed within that hour.
status: pending
```

```yaml
# manual-operation
id: agents-retire-pod-leftovers
layer: agents
app: secure-agent-pod
plan: docs/superpowers/plans/2026-11-12--agents--retire-secure-agent-pod
when: After the sweep passes and the agent-images PR has merged
why_manual: Infisical keys, the operator's Mac configuration and GitHub trackers are outside the GitOps loop.
commands:
  - In Infisical, remove the agent-secrets-tier2 keys no other consumer reads, including VK_ORG_ID and VK_DERIO_OPS_PROJECT_ID. Check each key against the remaining ExternalSecrets before deleting it.
  - Remove the user-level vibe_kanban MCP server entry from the Claude configuration on the Mac.
  - Remove the secure-agent-pod SSH and mosh host entries and the wezterm launcher from the Mac's client configuration.
  - Close the frank-ops#18 health tracker, since every rule labelled with it is tombstoned.
  - If frank#913 merged first, confirm scripts/tests/fixtures/life/pin-exceptions.yaml on main names neither vk-local nor secure-agent-kali.
verify:
  - Every remaining ExternalSecret in the cluster is SecretSynced after the Infisical cleanup.
  - The first agent-images bump run created after both the Frank merge and the agent-images kali removal completes with its coverage check green.
status: pending
```
