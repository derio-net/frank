---
title: "Operating on Paperclip"
date: 2026-04-09
draft: false
tags: ["operations", "paperclip", "ai-agents", "postgresql", "gpu-1"]
summary: "Day-to-day commands for managing Paperclip — checking pod health, database operations, secret sync, and handling the RWO PVC constraint."
weight: 118
---

This is the operational companion to [Paperclip — AI Agent Orchestrator]({{< relref "/docs/building/15-paperclip" >}}). That post explains the architecture and deployment. This one covers health checks, database access, secret management, and common failure modes.

## What "Healthy" Looks Like

Paperclip is healthy when:
- The paperclip pod is `1/1 Running` on `gpu-1` in the `paperclip-system` namespace
- The web UI responds at `http://192.168.55.212:3100`
- PostgreSQL is `1/1 Running` with the metrics sidecar (PostgreSQL is unconstrained — runs wherever the scheduler puts it)
- All four ExternalSecrets show `SecretSynced`
- The PVC is `Bound`

Paperclip is pinned to gpu-1 (`nodeSelector: kubernetes.io/hostname: gpu-1`) with a defensive `nvidia.com/gpu:NoSchedule` toleration. It does not request a GPU — gpu-1 is the cluster's biggest CPU/RAM box (128GB, ~20% requested) and absorbs the 12Gi memory limit without crowding the core-zone control-plane minis. See the building post's *Memory Tuning and the Move to gpu-1* section for the history.

<!-- MEDIA: screenshot | Paperclip dashboard showing agent overview and recent runs | Navigate to http://192.168.55.212:3100, log in, capture the main dashboard view with at least one agent visible, dark mode preferred -->
<!-- {{</* screenshot src="paperclip-dashboard.png" caption="Paperclip dashboard: the control plane's view of registered agents and recent runs" */>}} -->

Quick health check:

```bash
# All-in-one status
kubectl get pods,pvc,externalsecret -n paperclip-system -o wide
```

Expected output: one paperclip pod (on `gpu-1`), one paperclip-db pod, one 2Gi PVC bound, four ExternalSecrets synced.

```console
$ kubectl get pods,pvc,externalsecret -n paperclip-system
NAME                             READY   STATUS    RESTARTS   AGE
pod/paperclip-78cfb8db86-z7z4n   1/1     Running   0          12d
pod/paperclip-db-postgresql-0    2/2     Running   0          28d

NAME                                                   STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   VOLUMEATTRIBUTESCLASS   AGE
persistentvolumeclaim/data-paperclip-db-postgresql-0   Bound    pvc-1929c98e-6a59-4eec-8c41-353833f43dec   5Gi        RWO            longhorn       <unset>                 37d
persistentvolumeclaim/paperclip-data                   Bound    pvc-1ded449d-e2bc-4e38-b7c9-c5d5ee264294   2Gi        RWO            longhorn       <unset>                 37d

NAME                                                   STORETYPE            STORE       REFRESH INTERVAL   STATUS         READY
externalsecret.external-secrets.io/paperclip-auth      ClusterSecretStore   infisical   5m                 SecretSynced   True
externalsecret.external-secrets.io/paperclip-brave     ClusterSecretStore   infisical   5m                 SecretSynced   True
externalsecret.external-secrets.io/paperclip-llm-key   ClusterSecretStore   infisical   5m                 SecretSynced   True
externalsecret.external-secrets.io/paperclip-resend    ClusterSecretStore   infisical   5m                 SecretSynced   True
```

## Observing State

### Pod Health

```bash
# Check pod status and restarts
kubectl get pods -n paperclip-system -o wide

# Verify the web UI is responding
curl -s -o /dev/null -w "%{http_code}" http://192.168.55.212:3100/
# Expected: 200 (or 403 in private mode — either means the app is up)

# Check startup logs (migrations, Agent JWT, backup schedule)
kubectl logs -n paperclip-system -l app.kubernetes.io/name=paperclip | head -30

# Tail logs in real-time
kubectl logs -n paperclip-system -l app.kubernetes.io/name=paperclip -f --tail=50
```

### Database Health

```bash
# Check PostgreSQL pod
kubectl get pods -n paperclip-system -l app.kubernetes.io/instance=paperclip-db

# Connect to the database
kubectl exec -it -n paperclip-system \
  $(kubectl get pod -n paperclip-system -l app.kubernetes.io/instance=paperclip-db -o name) \
  -- psql -U paperclip -d paperclip

# Quick table count (inside psql)
SELECT schemaname, count(*) FROM pg_tables GROUP BY schemaname;
```

### ExternalSecret Sync

```bash
# Check all secrets are synced from Infisical
kubectl get externalsecret -n paperclip-system

# Detailed sync status for a specific secret
kubectl describe externalsecret paperclip-llm-key -n paperclip-system
```

Four ExternalSecrets exist:
- `paperclip-llm-key` — OPENAI_API_KEY and OPENAI_BASE_URL (points to LiteLLM)
- `paperclip-auth` — BETTER_AUTH_SECRET for session signing
- `paperclip-brave` — BRAVE_API_KEY for agent web-search tools (optional, marked `optional: true`); sourced from Infisical key `BRAVE_SEARCH_KEY_PAPERCLIP` and remapped to the standard `BRAVE_API_KEY` env var
- `paperclip-resend` — RESEND_API_KEY for agent transactional email (optional, marked `optional: true`); sourced from Infisical key `EMAIL_RESEND_API_KEY` and remapped to the standard `RESEND_API_KEY` env var the Resend SDK and MCP server expect

Earlier deployments included `paperclip-anthropic` (`ANTHROPIC_API_KEY` for the `claude_local` adapter) and `paperclip-ghcr` (`.dockerconfigjson` for pulling our custom image from GHCR). Both were retired when Paperclip switched to the upstream public image and stopped using the `claude_local` adapter — see the building-side post for the full history.

## Common Operations

### Restarting Paperclip

The Deployment uses `strategy: Recreate` because the PVC is ReadWriteOnce. A rolling update would deadlock — the new pod can't mount the volume while the old pod holds it. Recreate kills the old pod first, then starts the new one.

```bash
# Restart (zero-downtime is not possible with RWO PVC)
kubectl rollout restart deployment/paperclip -n paperclip-system

# Watch the restart
kubectl get pods -n paperclip-system -w
```

Expect a brief gap (10-30s) where Paperclip is unavailable while the old pod terminates and the new one starts.

### Updating the Image

Paperclip runs the upstream public image. Upstream only publishes `latest` (master HEAD) and `sha-<short>` tags — no semver image tags — so we pin a specific `sha-<short>` build that maps to a known git tag. To deploy a new version:

```bash
# Update the image tag (preferred: edit the manifest and let ArgoCD sync)
# apps/paperclip/manifests/deployment.yaml → image: ghcr.io/paperclipai/paperclip:sha-<short>

# Imperative alternative (will drift from Git until the manifest catches up):
kubectl set image deployment/paperclip \
  paperclip=ghcr.io/paperclipai/paperclip:sha-<short> \
  -n paperclip-system
```

### Database Backup and Restore

PostgreSQL data lives on a Longhorn PVC backed up by the cluster-wide recurring backup job.

```bash
# Check Longhorn backup status for the paperclip-db volume
kubectl get volume -n longhorn-system | grep paperclip

# Manual backup via Longhorn UI
# Navigate to http://192.168.55.201 → Volumes → paperclip-db → Create Backup
```

## Troubleshooting

### Pod Stuck in CrashLoopBackOff

**Check the logs first:**

```bash
kubectl logs -n paperclip-system -l app.kubernetes.io/name=paperclip --previous
kubectl describe pod -n paperclip-system -l app.kubernetes.io/name=paperclip
```

Common causes:
- **Database not ready** — paperclip-db pod must be Running before paperclip starts. Check `kubectl get pods -n paperclip-system`.
- **Missing secret** — if a non-optional ExternalSecret fails to sync, the pod hits `CreateContainerConfigError`. Check `kubectl get externalsecret -n paperclip-system`.
- **Port conflict** — another process on the node binding port 3100 (unlikely with Cilium LB, but check events).

### Multi-Attach Error on PVC

If you see `Multi-Attach error for volume` in events, the old pod didn't release the volume before the new one started. This shouldn't happen with Recreate strategy, but if it does:

```bash
# Force-delete the stuck pod
kubectl delete pod <old-pod-name> -n paperclip-system --grace-period=0 --force

# The new pod will mount the PVC and start
kubectl get pods -n paperclip-system -w
```

### ExternalSecret Not Syncing

```bash
# Check the ExternalSecret status
kubectl describe externalsecret paperclip-llm-key -n paperclip-system

# Common issue: Infisical secret path changed
# Verify the secret exists in Infisical under the expected path
# Then check the ClusterSecretStore is healthy
kubectl get clustersecretstore infisical
```

### LoadBalancer IP Not Assigned

```bash
# Check service status
kubectl get svc paperclip-lb -n paperclip-system

# If <pending>, check Cilium L2 IPAM
kubectl get ciliumpoolipaddress -A | grep 192.168.55.212
```

## Gotchas

- **No Argo Rollouts for Paperclip.** The RWO PVC makes it incompatible with blue-green and canary strategies. It runs as a plain Deployment with Recreate strategy. See [Operating on Progressive Delivery]({{< relref "/docs/operating/12-progressive-delivery" >}}) for context on the Phase 3 revert.

- **TCP probes, not HTTP.** In private mode, the root path returns 403 to non-localhost requests. Probes use `tcpSocket` on port `http` instead of `httpGet`.

- **PostgreSQL image uses GCR mirror.** Bitnami no longer serves named tags on Docker Hub. The chart uses `mirror.gcr.io/bitnamilegacy/*` images. If the mirror goes down, you'll need to find another source for the `14.1.10-debian-11-r16` tag.

- **Optional feature secrets.** `paperclip-brave` (Brave Search) and `paperclip-resend` (Resend transactional email) are both marked `optional: true` on their `secretRef` entries. If `BRAVE_SEARCH_KEY_PAPERCLIP` or `EMAIL_RESEND_API_KEY` doesn't exist in Infisical, the pod starts fine without that key — agents that don't invoke the corresponding tool are unaffected. The same `optional: true` pattern previously protected the now-retired `paperclip-anthropic` secret from blocking rollouts when its Infisical entry was missing; new optional feature secrets should follow the same convention.

- **Pinned to gpu-1, but does not request a GPU.** Paperclip is a CPU/RAM workload that lives on the GPU node because gpu-1 is also the cluster's biggest RAM box. The `nvidia.com/gpu:NoSchedule` toleration is *defensive* — gpu-1's live taint list is empty, but the GPU operator can re-assert the taint during driver re-validation, and a pinned workload without the toleration would be evicted in that window. Mirror the toleration on anything else you pin to gpu-1 (this is the cluster idiom — see `frank-gotchas.md`).

- **Memory limit is 12Gi, not a typo.** Paperclip's real working set under load is meaningfully larger than the 1Gi the original deployment shipped with — see *Memory Tuning and the Move to gpu-1* in the building post for the two-round OOM story. If you see new exit-137 (OOMKilled) crashes, check whether a recent feature added an SDK that eagerly inits at startup before assuming the limit needs another bump.

## References

- [Paperclip GitHub](https://github.com/paperclipai/paperclip) — Upstream source repository
- [Building Post: Paperclip]({{< relref "/docs/building/15-paperclip" >}}) — Architecture and deployment walkthrough
- [Operating on Progressive Delivery]({{< relref "/docs/operating/12-progressive-delivery" >}}) — Context on why Paperclip isn't a Rollout
