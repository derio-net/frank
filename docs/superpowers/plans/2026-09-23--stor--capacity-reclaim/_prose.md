# Capacity reclaim — Implementation Plan

**Layer:** stor (touches infer, agents, tenant) · **Repo:** derio-net/frank · **Branch:** `feat/capacity-reclaim`

## Why

The 2026-09-23 capacity audit found Frank averaging ~7% CPU and ~20% RAM, so compute is not the constraint. The constraints are:

- **Longhorn scheduling on mini-1/mini-2 is at 98%/97% of the provisioning ceiling.** Most of it is two re-downloadable model stores (`ollama`, `comfyui-models`, 200 Gi each) whose third replica sits on each of those minis. A new 3-replica volume over ~29 Gi could not be placed.
- **The inference gateway was over-provisioned and stuck.** The LiteLLM Rollout sat at its first canary pause for 60 days (since 2026-07-25), running 5 pods × ~1.9 GiB with zero memory requests, for ~10 real requests in 14 days.
- **Idle apps.** Sympozium (9 schedules erroring for 110 days, ~170k error log lines/day), Ruflo (no use; 285 Gi of Longhorn) and vcluster-experiments were never used. The operator retired all three; they restore from git history.

AWX stays by operator decision.

## Approach

Phase 1 is the git change. Phase 2 is back-loaded live work: two steps ArgoCD cannot do, and one it would do wrong.

- **Model stores:** both volumes already hold a gpu-1 replica on the `gpu-local`-tagged 3.7 TB disks. Setting `numberOfReplicas: 1` with `diskSelector: [gpu-local]` and deleting the mini replicas frees ~400 Gi on each of mini-1 and mini-2, with no data copy. The PVCs keep StorageClass `longhorn` because `storageClassName` is immutable. If they are ever recreated, use `longhorn-gpu-local` (already declared in `apps/longhorn/manifests/gpu-local-sc.yaml`).
- **LiteLLM:** the right-size changes the pod template, which starts a new canary on merge. One promotion then clears both the stale July change and this one.
- **Retirement:** root has `prune: true` and each child Application has `resources-finalizer`, so ArgoCD deletes what it manages. It never owned the StatefulSet PVCs, the auto-created namespaces, Sympozium's CRDs, or the two IngressRoutes owned by `traefik-extras` (`prune: false`). Those are swept by hand.

## Follow-ups (not in this plan)

- Retroactively note the retirements in the Layer 12 (Sympozium) and Ruflo building/operating blog posts.
- The 1/min `litellm_chat` probe loads `gemma-12b` every minute. With `OLLAMA_MAX_LOADED_MODELS=1`, it evicts whatever hermes last loaded (qwen3.6, 23 GB), so an active hermes session reloads its model every minute.

## Manual operations

```yaml
# manual-operation
id: stor-model-stores-single-replica
layer: stor
app: longhorn
plan: 2026-09-23--stor--capacity-reclaim
when: Any time; independent of the merge. Ollama stays attached and serving.
why_manual: Longhorn Volume CRs are not ArgoCD-managed and a PVC's StorageClass is immutable; the replica count of an existing volume can only be changed live.
commands: |
  source .env
  for pvc in ollama/ollama comfyui/comfyui-models; do
    vol=$(kubectl get pvc -n "${pvc%/*}" "${pvc#*/}" -o jsonpath='{.spec.volumeName}')
    # Gate: a healthy gpu-1 replica on a gpu-local disk must exist first.
    kubectl -n longhorn-system get replicas.longhorn.io -l longhornvolume="$vol" \
      -o jsonpath='{range .items[*]}{.spec.nodeID} {.spec.diskPath} {.spec.failedAt}{"\n"}{end}'
    kubectl -n longhorn-system patch volumes.longhorn.io "$vol" --type merge \
      -p '{"spec":{"numberOfReplicas":1,"diskSelector":["gpu-local"],"dataLocality":"best-effort"}}'
    kubectl -n longhorn-system get replicas.longhorn.io -l longhornvolume="$vol" -o name \
      | while read r; do
          n=$(kubectl -n longhorn-system get "$r" -o jsonpath='{.spec.nodeID}')
          [ "$n" != gpu-1 ] && kubectl -n longhorn-system delete "$r"
        done
  done
verify: |
  # One replica per model store, on gpu-1:
  kubectl -n longhorn-system get replicas.longhorn.io -o custom-columns=V:.spec.volumeName,N:.spec.nodeID | grep -E "$(kubectl get pvc -n ollama ollama -o jsonpath='{.spec.volumeName}')|$(kubectl get pvc -n comfyui comfyui-models -o jsonpath='{.spec.volumeName}')"
  # storageScheduled on mini-1/mini-2 dropped by ~400 Gi each:
  kubectl -n longhorn-system get nodes.longhorn.io -o json | jq -r '.items[] | .metadata.name + " " + ([.status.diskStatus[].storageScheduled] | add / 1073741824 | floor | tostring)'
  kubectl -n ollama exec deploy/ollama -- ollama list
status: done
```

```yaml
# manual-operation
id: infer-litellm-promote-after-rightsize
layer: infer
app: litellm
plan: 2026-09-23--stor--capacity-reclaim
when: After the PR merges and ArgoCD syncs litellm — the new pod template starts a canary that pauses indefinitely.
why_manual: The Rollout's canary pauses are operator gates by design; promotion is an operator decision.
commands: |
  source .env
  kubectl -n litellm get rollout litellm -o jsonpath='{.status.phase} step={.status.currentStepIndex}{"\n"}'
  # Evidence gate: a real completion from the canary pod by IP.
  K=$(kubectl -n monitoring get secret litellm-master-key -o jsonpath='{.data.litellm-master-key}' | base64 -d)
  CANARY=$(kubectl -n litellm get rollout litellm -o jsonpath='{.status.currentPodHash}')
  IP=$(kubectl -n litellm get pod -l rollouts-pod-template-hash="$CANARY" -o jsonpath='{.items[0].status.podIP}')
  kubectl -n monitoring exec deploy/blackbox-exporter -- wget -qO- \
    --header "Authorization: Bearer $K" --header 'Content-Type: application/json' \
    --post-data '{"model":"gemma-12b-nothin","max_tokens":4,"messages":[{"role":"user","content":"reply with the single word: ok"}]}' \
    "http://$IP:4000/v1/chat/completions"
  kubectl argo rollouts promote litellm -n litellm --full
verify: |
  kubectl -n litellm get rollout litellm   # Healthy, 2/2
  kubectl -n litellm get pods              # 2 litellm pods + postgresql
  kubectl -n litellm get pod litellm-postgresql-0 -o jsonpath='{.spec.containers[0].resources}'
status: done
```

```yaml
# manual-operation
id: agents-retire-sympozium-ruflo-sweep
layer: agents
app: sympozium
plan: 2026-09-23--stor--capacity-reclaim
when: After the PR merges and root has pruned the retired Applications (they disappear from `kubectl -n argocd get applications`).
why_manual: ArgoCD cascade-deletes only what it manages. StatefulSet PVCs, CreateNamespace namespaces, Sympozium's CRDs, and IngressRoutes owned by the prune:false traefik-extras app are left behind.
commands: |
  source .env
  kubectl -n argocd get applications sympozium sympozium-extras ruflo ruflo-db vcluster-experiments   # expect NotFound
  kubectl -n traefik-system delete ingressroute sympozium ruflo --ignore-not-found
  kubectl delete namespace sympozium-system ruflo-system vcluster-experiments --ignore-not-found
  kubectl get crd -o name | grep sympozium.ai | xargs -r kubectl delete
  kubectl get clusterrole,clusterrolebinding,mutatingwebhookconfiguration,validatingwebhookconfiguration -o name | grep -iE 'sympozium|ruflo|experiments' | xargs -r kubectl delete
verify: |
  kubectl get ns | grep -E 'sympozium|ruflo|vcluster-experiments' || echo "namespaces gone"
  kubectl get crd | grep -c sympozium.ai    # 0
  kubectl -n longhorn-system get volumes.longhorn.io -o json | jq -r '.items[].status.kubernetesStatus.namespace' | grep -E 'ruflo|experiments|sympozium' || echo "volumes gone"
status: done
```
