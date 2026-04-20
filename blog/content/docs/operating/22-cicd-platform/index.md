---
title: "Operating on CI/CD Platform"
date: 2026-04-13
draft: false
tags: ["operations", "cicd", "gitea", "tekton", "zot", "cosign", "pipelines", "troubleshooting"]
summary: "Day-to-day commands for the CI/CD platform — Gitea mirrors, Tekton pipelines, Zot registry health, cosign verification, and troubleshooting webhook delivery."
weight: 122
---

Companion operations guide for [CI/CD Platform — Gitea, Tekton, Zot, and Cosign]({{< relref "/docs/building/27-cicd-platform" >}}).

## Quick Health Check

```bash
# All CI/CD pods
kubectl get pods -n gitea -o wide
kubectl get pods -n tekton-pipelines -o wide
kubectl get pods -n zot -o wide

# ArgoCD app status
kubectl get applications -n argocd gitea gitea-extras \
  tekton-pipelines tekton-triggers tekton-dashboard tekton-extras \
  zot zot-extras

# ExternalSecrets sync status
kubectl get externalsecret -n gitea
kubectl get externalsecret -n tekton-pipelines
kubectl get externalsecret -n zot
```

Healthy state: all pods Running on pc-1, all ArgoCD apps Synced/Healthy, all ExternalSecrets SecretSynced.

<!-- MEDIA: asciinema | CI/CD platform baseline across three namespaces | source .env && kubectl get pods -n gitea -o wide && echo '---tekton---' && kubectl get pods -n tekton-pipelines -o wide && echo '---zot---' && kubectl get pods -n zot -o wide -->
<!-- {{</* asciinema src="cicd-baseline-pods.cast" */>}} -->

## Gitea Operations

### Mirror Sync Status

```bash
# Check mirror sync time via API
GITEA_URL="http://192.168.55.209:3000"
curl -s "$GITEA_URL/api/v1/repos/tekton-bot/frank" | jq '{
  mirror: .mirror,
  updated_at: .updated_at,
  mirror_interval: .mirror_interval
}'
```

Expected: `mirror: true`, `updated_at` within the last 10 minutes.

### Force Mirror Sync

```bash
# Trigger immediate mirror sync
ADMIN_TOKEN=$(kubectl get secret -n gitea gitea-secrets -o jsonpath='{.data.admin-password}' | base64 -d)
curl -sf -X POST "$GITEA_URL/api/v1/repos/tekton-bot/frank/mirror-sync" \
  -H "Authorization: token $ADMIN_TOKEN"
```

### Gitea Logs

```bash
kubectl logs -n gitea deploy/gitea --tail=50
kubectl logs -n gitea deploy/gitea -f  # Follow
```

### Restart Gitea

```bash
kubectl rollout restart deploy/gitea -n gitea
kubectl rollout status deploy/gitea -n gitea
```

Note: Gitea uses `strategy: Recreate` (RWO PVC) — expect a brief downtime window during restart.

### Common Gitea Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| OIDC login fails | Authentik provider misconfigured or down | Check `kubectl logs -n gitea deploy/gitea \| grep oauth` |
| Mirror not updating | GitHub PAT expired or rate-limited | Verify `GITHUB_MIRROR_TOKEN` in Infisical is valid |
| Webhook delivery fails | `ALLOWED_HOST_LIST` missing cluster DNS | Add `*.svc.cluster.local` to `gitea.config.webhook.ALLOWED_HOST_LIST` |
| Pod stuck in Pending | PVC can't mount (pc-1 down) | Check `kubectl get pv` and node status |

## Tekton Operations

### List Recent PipelineRuns

```bash
# All PipelineRuns, most recent first
kubectl get pipelinerun -n tekton-pipelines --sort-by=.metadata.creationTimestamp

# Only failed runs
kubectl get pipelinerun -n tekton-pipelines \
  -o jsonpath='{range .items[?(@.status.conditions[0].status=="False")]}{.metadata.name}{"\t"}{.status.conditions[0].message}{"\n"}{end}'
```

### View Pipeline Logs

```bash
# Latest PipelineRun logs (requires tkn CLI)
tkn pipelinerun logs -n tekton-pipelines --last

# Without tkn — find the pod and read logs per step
kubectl get pods -n tekton-pipelines -l tekton.dev/pipelineRun --sort-by=.metadata.creationTimestamp | tail -5
kubectl logs -n tekton-pipelines <pod-name> -c step-clone
kubectl logs -n tekton-pipelines <pod-name> -c step-test
kubectl logs -n tekton-pipelines <pod-name> -c step-build-and-push
kubectl logs -n tekton-pipelines <pod-name> -c step-sign
```

### Cancel a Running PipelineRun

```bash
kubectl patch pipelinerun -n tekton-pipelines <name> \
  --type=merge -p '{"spec":{"status":"CancelledRunFinally"}}'
```

### Clean Up Old PipelineRuns

```bash
# Delete PipelineRuns older than 7 days
kubectl get pipelinerun -n tekton-pipelines \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.creationTimestamp}{"\n"}{end}' \
  | awk -v cutoff="$(date -d '7 days ago' -u +%Y-%m-%dT%H:%M:%SZ)" '$2 < cutoff {print $1}' \
  | xargs -r kubectl delete pipelinerun -n tekton-pipelines
```

### EventListener Health

```bash
# EventListener pod logs
kubectl logs -n tekton-pipelines -l app.kubernetes.io/managed-by=EventListener --tail=30

# EventListener service reachability (from within cluster)
kubectl run test-curl --rm -it --image=curlimages/curl -- \
  curl -s -o /dev/null -w "%{http_code}" \
  http://el-gitea-listener.tekton-pipelines.svc.cluster.local:8080
# Expect: 200 or 202
```

### Tekton Dashboard

Access at `http://192.168.55.217:9097` or `https://tekton.cluster.derio.net` (Authentik forward-auth).

The dashboard is read-only — it shows PipelineRuns, TaskRuns, and logs. Useful for non-CLI users or quick visual debugging.

<!-- MEDIA: screenshot | Tekton Dashboard PipelineRun history with a successful gitea-ci run open | Navigate to http://192.168.55.217:9097 (or via Authentik at tekton.cluster.derio.net), open a recent gitea-ci PipelineRun, capture the DAG view with all steps green -->
<!-- {{</* screenshot src="tekton-pipelinerun-history.png" caption="Tekton Dashboard: recent PipelineRuns with a successful gitea-ci run expanded" */>}} -->

### Common Tekton Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| PipelineRun stuck in Pending | PVC can't provision (pc-1 down or Longhorn unhealthy) | Check `kubectl get pv` and Longhorn UI |
| `ComparisonError` in ArgoCD | Task YAML uses `resources` instead of `computeResources` | Fix the Task manifest and re-sync |
| `report-success` not firing | `$(tasks.status)` is `"Completed"` not `"Succeeded"` | Check `when` clause accepts both values |
| Step fails with `permission denied` | Missing `fsGroup: 65534` on PipelineRun pod template | Add to TriggerTemplate's `taskRunTemplate.podTemplate.securityContext` |
| `git config` fails | `HOME=/` is read-only for UID 65534 | Set `HOME=/tekton/home` env var on the step |
| PodSecurity violation | Missing `securityContext` on Task steps | Add `runAsNonRoot`, `capabilities.drop`, `seccompProfile` |
| Webhook doesn't trigger pipeline | Gitea sends `X-Gitea-Event`, not `X-GitHub-Event` | Use CEL interceptor, not `github` interceptor |

## Zot Registry Operations

### Registry Health

```bash
# API check (anonymous read)
curl -sk https://192.168.55.210:5000/v2/
# Expect: {} or {"repositories":[]}

# List all repositories
curl -sk https://192.168.55.210:5000/v2/_catalog
# Expect: {"repositories":["test/alpine","..."]}

# List tags for a repo
curl -sk https://192.168.55.210:5000/v2/test/alpine/tags/list
```

### Test Push

```bash
# Push a test image (requires credentials)
ZOT_PASS=$(kubectl get secret -n tekton-pipelines zot-push-creds \
  -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d | jq -r '.auths["192.168.55.210:5000"].password')

# Using crane (lightweight OCI tool)
crane auth login 192.168.55.210:5000 -u tekton-push -p "$ZOT_PASS" --insecure
crane push /dev/null 192.168.55.210:5000/test/healthcheck:latest --insecure
```

### TLS Certificate Status

```bash
# cert-manager Certificate status
kubectl get certificate -n zot zot-tls
# Expect: Ready=True

# Certificate details
kubectl describe certificate -n zot zot-tls

# Check cert expiry
kubectl get secret -n zot zot-tls -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -dates
```

### Registry Logs

```bash
kubectl logs -n zot deploy/zot --tail=50
```

### Restart Zot

```bash
kubectl rollout restart deploy/zot -n zot
kubectl rollout status deploy/zot -n zot
```

Like Gitea, Zot uses `strategy: Recreate` for RWO PVC safety.

### Common Zot Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `401 Unauthorized` on push | Wrong password or htpasswd hash stale | Regenerate htpasswd if `ZOT_PUSH_PASSWORD` changed in Infisical |
| `x509: certificate signed by unknown authority` | Self-signed cert not trusted by client | Use `--insecure` flag or add cert to trust store |
| Containerd pull fails on nodes | Talos mirror patch not applied | Apply `patches/phase06-cicd/06-cluster-zot-registry.yaml` via Omni |
| Pod stuck (PVC) | pc-1 down or Longhorn unhealthy | Check node and Longhorn status |

## Cosign Operations

### Verify an Image Signature

```bash
cosign verify --key apps/tekton/cosign.pub \
  --insecure-ignore-tlog --allow-insecure-registry \
  192.168.55.210:5000/<repo>/<image>:<tag>
```

Expected: `Verification for 192.168.55.210:5000/... -- The following checks were performed: ...`

### Check if an Image Is Signed

```bash
# List signature artifacts for an image
crane ls 192.168.55.210:5000/<repo>/<image> --insecure
# Look for sha256-*.sig tags
```

### Rotate Signing Keys

1. Generate new key pair: `COSIGN_PASSWORD='' cosign generate-key-pair`
2. Store new private key in Infisical as `COSIGN_KEY`
3. Commit new `cosign.pub` to `apps/tekton/cosign.pub`
4. Wait for ExternalSecret to refresh (5 minutes) or force sync
5. New images will be signed with the new key; old signatures remain valid with old public key

## End-to-End Webhook Test

To verify the full pipeline chain from Gitea to signed image:

```bash
# 1. Trigger a mirror sync (or push directly to Gitea)
curl -sf -X POST "http://192.168.55.209:3000/api/v1/repos/tekton-bot/frank/mirror-sync" \
  -H "Authorization: token $ADMIN_TOKEN"

# 2. Watch for new PipelineRun
kubectl get pipelinerun -n tekton-pipelines -w

# 3. Check Gitea commit status (after pipeline completes)
curl -s "http://192.168.55.209:3000/api/v1/repos/tekton-bot/frank/statuses/<SHA>" \
  -H "Authorization: token $TOKEN" | jq '.[0].state'
# Expect: "success"
```

## References

- [Tekton CLI (tkn)](https://tekton.dev/docs/cli/)
- [crane — OCI registry tool](https://github.com/google/go-containerregistry/tree/main/cmd/crane)
- [cosign verification docs](https://docs.sigstore.dev/cosign/verifying/)
