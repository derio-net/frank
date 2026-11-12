# Retire VK, Phase 1

**Status:** In Progress
**Layer:** agents
**Spec:** `docs/superpowers/specs/2026-11-08--agents--retire-vk-design.md`

This plan implements requirements R1-R8 only. R9-R15 (taking the pod down, the blog
notices, removing the `secure-agent-kali` image) ship in a later PR, held until the
operator's triage run on the pod has ended and the archive is verified.

The hard rule for this plan: **`apps/secure-agent-pod/manifests/deployment.yaml` is not
edited.** The Deployment is `Recreate`, so editing it ends a live session.

The `derio-net/agent-images` PR that removes the `vk-local` build leg is separate, and
merges after this one. `derio-net/vibe-kanban` is archived last.

## Manual operations

```yaml
# manual-operation
id: agents-retire-vk-silences
layer: agents
app: grafana-alerting
plan: docs/superpowers/plans/2026-11-08--agents--retire-vk
when: Created 2026-11-08 before merge, with operator approval. Delete after the post-merge sweep.
why_manual: A silence bridges the gap until the merged PR removes the rules. A live ConfigMap patch would be reverted by selfHeal.
commands:
  - Silence 821588e7-7f64-403a-86ae-b3947d41110f covers the three VK rules, and 90ece2ba-b456-43b2-9535-752405cedb86 covers the job=vk_issue_bridge instance of the Layer 18 rule. Both expire 2026-11-22T21:40Z.
  - After the sweep, delete both through the Grafana Alertmanager API (DELETE /api/alertmanager/grafana/api/v2/silence/<id>), or let them expire.
verify:
  - The Grafana alerts API shows no VK alert and no job=vk_issue_bridge instance, with the silences gone.
status: done
```

```yaml
# manual-operation
id: agents-retire-vk-premerge
layer: agents
app: vk-remote
plan: docs/superpowers/plans/2026-11-08--agents--retire-vk
when: Before merging the Phase 1 PR
why_manual: The dump must exist before the cascade destroys the PVC, and the baseline must be taken from the live pod.
commands:
  - mkdir -p "$HOME/frank-retire-vk-archive"
  - kubectl -n agents exec deploy/postgres-vk -- sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$HOME/frank-retire-vk-archive/postgres-vk.dump"
  - pg_restore --list "$HOME/frank-retire-vk-archive/postgres-vk.dump" | head
  - kubectl -n secure-agent-pod get pod -l app=secure-agent-pod -o jsonpath='{.items[0].metadata.uid} {.items[0].status.containerStatuses[?(@.name=="kali")].restartCount}' > "$HOME/frank-retire-vk-archive/pod-baseline.txt"
  - argocd app diff secure-agent-pod --port-forward --port-forward-namespace argocd
  - gh pr list -R derio-net/frank --state open --search 'head:bump/agent-images'
verify:
  - pg_restore lists tables from the dump.
  - The app diff shows no Deployment change.
  - No bump/agent-images PR is open; close any that is.
status: done
```

```yaml
# manual-operation
id: agents-retire-vk-postmerge-sweep
layer: agents
app: traefik-extras
plan: docs/superpowers/plans/2026-11-08--agents--retire-vk
when: After the Phase 1 PR merges
why_manual: prune false leaves the deleted IngressRoute serving, Grafana reads provisioning only at boot, and a stale Application may report Synced without applying the merge.
commands:
  - Compare status.operationState.operation.sync.revision with the merge SHA on root, grafana-alerting, traefik-extras, tekton-extras, authentik-extras, homepage and ci-budget. Sync any that lag, passing ServerSideApply=true and RespectIgnoreDifferences=true.
  - kubectl -n traefik-system delete ingressroute vk-remote
  - |-
    kubectl -n monitoring get cm grafana-alerting-rules -o yaml | grep 'orgId: 1, uid: vk-bridge-stale'  # the tombstone proves the sync; restart only once this matches
  - kubectl -n monitoring rollout restart deploy/victoria-metrics-grafana
  - Delete the retained job=vk_issue_bridge group from pushgateway if it persists (DELETE /metrics/job/vk_issue_bridge on the pushgateway Service).
  - kubectl -n tekton-pipelines annotate externalsecret frank-gitops-push force-sync=$(date +%s) --overwrite
verify:
  - kubectl -n traefik-system get ingressroute vk-remote is NotFound.
  - kubectl get ns agents is NotFound.
  - kubectl -n tekton-pipelines get externalsecret frank-gitops-push reports SecretSynced with a refreshed token.
  - The kubectl -n secure-agent-pod pod UID and kali restart count equal the pre-merge baseline.
status: done
```

```yaml
# manual-operation
id: agents-retire-vk-fork-archive
layer: agents
app: vibe-kanban
plan: docs/superpowers/plans/2026-11-08--agents--retire-vk
when: After the agent-images PR merges and its bump run is green
why_manual: GitHub repo settings and Infisical keys are outside the GitOps loop.
commands:
  - Delete the derio-net/vibe-kanban GitHub webhook that targets the Frank github-listener.
  - gh api -X PATCH repos/derio-net/vibe-kanban -F archived=true
  - Remove VK_REMOTE_JWT_SECRET, VK_REMOTE_LOCAL_AUTH_PASSWORD, VK_REMOTE_ELECTRIC_PASSWORD and VK_REMOTE_PG_PASSWORD from Infisical. Leave VK_ORG_ID and VK_DERIO_OPS_PROJECT_ID, which the pod's ExternalSecret still reads until Phase 2.
verify:
  - gh api repos/derio-net/vibe-kanban --jq .archived prints true.
  - agent-github-token and agent-secrets-tier2 in secure-agent-pod are still SecretSynced.
status: done
```
