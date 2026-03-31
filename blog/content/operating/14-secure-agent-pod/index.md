---
title: "Operating on Secure Agent Pod"
date: 2026-03-31
draft: false
tags: ["operations", "security", "agent", "claude", "ssh", "vibekanban", "cilium"]
summary: "Day-to-day commands for managing the secure agent pod — SSH access, process health, VibeKanban, secret rotation, and troubleshooting."
weight: 114
cover:
  image: cover.png
  alt: "Frank monitoring a hardened workstation dashboard with process status indicators"
  relative: true
---

This is the operational companion to [Secure Agent Pod — Hardening an AI Coding Workstation]({{< relref "/building/21-secure-agent-pod" >}}). That post explains the architecture and security model. This one is the day-to-day runbook.

## What "Healthy" Looks Like

A healthy secure-agent-pod has:
- One pod running (`1/1 Ready`) on gpu-1
- Three processes inside: sshd, supercronic, vibe-kanban
- SSH accessible at `192.168.55.215:22`
- VibeKanban UI accessible at `192.168.55.218:8081`
- All running as UID 1000 (`claude`), no root

## Observing State

### Pod Health

```bash
# Pod status
kubectl -n secure-agent-pod get pods -o wide

# Detailed events and conditions
kubectl -n secure-agent-pod describe pod -l app=secure-agent-pod

# Container identity
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- id
# Expected: uid=1000(claude) gid=1000(claude) groups=1000(claude)
```

### Process Health

All three processes should be running inside the container:

```bash
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- ps aux
```

Expected output:

```
USER       PID  COMMAND
claude       1  /bin/bash /entrypoint.sh
claude      12  sshd: /usr/sbin/sshd -f /opt/sshd_config -D [listener]
claude      13  supercronic /home/claude/.crontab
claude      14  node /usr/bin/vibe-kanban
claude      33  /home/claude/.vibe-kanban/bin/.../vibe-kanban
```

If any process is missing, the pod will restart via `wait -n` — check restart count.

### Services and Networking

```bash
# Verify LoadBalancer IPs
kubectl -n secure-agent-pod get svc

# SSH connectivity
ssh -o ConnectTimeout=5 claude@192.168.55.215 echo "SSH works"

# VibeKanban health
curl -s -o /dev/null -w "%{http_code}" http://192.168.55.218:8081
# Expected: 200
```

### ArgoCD Sync Status

```bash
argocd app get secure-agent-pod --port-forward --port-forward-namespace argocd
```

## SSH Access

### Connecting

```bash
# Standard SSH
ssh claude@192.168.55.215

# With specific key
ssh -i ~/.ssh/id_rsa claude@192.168.55.215
```

The Service maps external port 22 → internal port 2222 (non-root sshd). SSH clients don't need to specify a port.

### Updating Authorized Keys

The SSH authorized keys come from a Kubernetes Secret:

```bash
# View current keys
kubectl get secret agent-ssh-keys -n secure-agent-pod -o jsonpath='{.data.authorized_keys}' | base64 -d

# Replace with a new key
kubectl create secret generic agent-ssh-keys \
  --namespace=secure-agent-pod \
  --from-file=authorized_keys=~/.ssh/id_rsa.pub \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart pod to pick up the new key
kubectl rollout restart deployment/secure-agent-pod -n secure-agent-pod
```

The entrypoint copies authorized_keys from the Secret mount to `~/.ssh/authorized_keys` on each boot.

### SSH Host Key Changed Warning

If you see "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED", the PVC was recreated (host keys regenerated):

```bash
ssh-keygen -R 192.168.55.215
ssh claude@192.168.55.215
```

## VibeKanban

### Accessing the UI

VibeKanban runs on port 8081, exposed via LoadBalancer at `192.168.55.218`:

```
http://192.168.55.218:8081
```

Access via Tailscale/Headscale mesh or direct LAN. First login uses VibeKanban's built-in local auth.

### Configuration

VibeKanban stores its SQLite database and binary cache on the PVC:

```
/home/claude/.vibe-kanban/     # Binary cache + SQLite DB
/home/claude/repos/            # Git workspaces managed by VibeKanban
```

Key environment variables (set in the Deployment manifest):

| Variable | Value | Purpose |
|----------|-------|---------|
| `PORT` | `8081` | Fixed server port (default is random) |
| `HOST` | `0.0.0.0` | Listen on all interfaces (default is 127.0.0.1) |

### Checking VibeKanban Logs

```bash
# Full pod logs (includes all three processes)
kubectl logs -n secure-agent-pod deploy/secure-agent-pod -c kali

# Follow logs
kubectl logs -n secure-agent-pod deploy/secure-agent-pod -c kali -f

# Filter for VibeKanban only
kubectl logs -n secure-agent-pod deploy/secure-agent-pod -c kali | grep -E "vibe-kanban|server|INFO|WARN|ERROR"
```

## Secret Management

### Tier 1: Infisical (ESO)

Currently no active Tier 1 secrets (Claude Code uses Max subscription login). When needed:

1. Add the secret to Infisical
2. Create/update the ExternalSecret manifest at `apps/secure-agent-pod/manifests/externalsecret.yaml`
3. Commit and push — ArgoCD syncs, ESO creates the K8s Secret
4. Restart the pod to pick up new env vars

### Tier 2: Manual Secrets

```bash
# View current tier-2 secrets
kubectl get secret agent-secrets-tier2 -n secure-agent-pod -o jsonpath='{.data}' | python3 -c "import json,sys,base64; d=json.load(sys.stdin); [print(f'{k}: {base64.b64decode(v).decode()[:20]}...') for k,v in d.items()]"

# Update a secret value
kubectl patch secret agent-secrets-tier2 -n secure-agent-pod \
  --type merge -p '{"stringData":{"GITHUB_TOKEN":"new-token-here"}}'

# Restart to pick up changes
kubectl rollout restart deployment/secure-agent-pod -n secure-agent-pod
```

### Config Files (talosconfig, kubeconfig, omniconfig)

Mounted at `/home/claude/.kube/configs/`:

```bash
# Verify configs are mounted
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- ls -la /home/claude/.kube/configs/

# Rotate configs
sops --decrypt secrets/secure-agent-pod/agent-configs.yaml | kubectl apply -f -
kubectl rollout restart deployment/secure-agent-pod -n secure-agent-pod
```

## Pod Lifecycle

### Restarting

```bash
# Graceful restart (new pod, then old pod terminates)
kubectl rollout restart deployment/secure-agent-pod -n secure-agent-pod

# Force restart (immediate)
kubectl delete pod -l app=secure-agent-pod -n secure-agent-pod
```

Strategy is `Recreate` (RWO PVC), so there's always a brief downtime during restart.

### Checking PVC Data

```bash
# PVC status
kubectl get pvc -n secure-agent-pod

# What's on the PVC
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- du -sh /home/claude/*
```

### Image Updates

The deployment uses `ghcr.io/derio-net/secure-agent-kali:latest`. To pick up a new image:

```bash
# Force pull latest
kubectl rollout restart deployment/secure-agent-pod -n secure-agent-pod
```

For pinned SHA tags, update the `image:` field in `apps/secure-agent-pod/manifests/deployment.yaml` and push.

## Cron Jobs

Cron is managed by supercronic reading `/home/claude/.crontab`:

```bash
# View current crontab
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- cat /home/claude/.crontab

# Edit crontab (SSH in first)
ssh claude@192.168.55.215
vi ~/.crontab
# supercronic picks up changes automatically (no restart needed)
```

For cron jobs that need K8s env vars (API keys, etc.), source the env loader first:

```bash
# In .crontab:
*/5 * * * * source /home/claude/.load-env.sh && /path/to/script.sh
```

## Cilium Egress Policy

**Current status:** Temporarily disabled due to Cilium 1.17 FQDN LRU bug.

The policy manifest is at `apps/secure-agent-pod/cilium-egress.yaml.disabled`. To re-enable:

```bash
# Move back to manifests directory
mv apps/secure-agent-pod/cilium-egress.yaml.disabled apps/secure-agent-pod/manifests/cilium-egress.yaml
git add -A && git commit -m "feat(agents): re-enable Cilium egress policy" && git push

# Verify policy status
kubectl get ciliumnetworkpolicy -n secure-agent-pod
# VALID column should be True
```

If the policy shows `VALID: False` with "LRU not yet initialized":

```bash
# Restart Cilium agent on gpu-1
kubectl delete pod -n kube-system -l k8s-app=cilium --field-selector spec.nodeName=gpu-1

# Wait for agent restart, then delete and reapply
kubectl delete ciliumnetworkpolicy agent-egress -n secure-agent-pod
kubectl apply -f apps/secure-agent-pod/manifests/cilium-egress.yaml

# Delete the pod to clear stale BPF state
kubectl delete pod -l app=secure-agent-pod -n secure-agent-pod
```

### Testing Egress (When Policy is Active)

```bash
# Should SUCCEED
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- \
  curl -s --connect-timeout 5 -o /dev/null -w "%{http_code}" https://api.anthropic.com/
# Expected: 404

# Should FAIL (blocked)
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- \
  curl -s --connect-timeout 5 https://httpbin.org/ip
# Expected: timeout
```

## Troubleshooting

### CrashLoopBackOff

Check which process died:

```bash
kubectl logs -n secure-agent-pod deploy/secure-agent-pod -c kali --previous
```

Common causes:
- **"Download failed"** — VibeKanban can't reach `npm-cdn.vibekanban.com` (Cilium blocking or DNS issue)
- **"No such file or directory: /entrypoint.sh"** — image didn't include the entrypoint (rebuild needed)
- **sshd fails** — check host key permissions (`chmod 600` on private keys, `chmod 700` on `.ssh-host-keys/`)

### Pod Stuck in CreateContainerConfigError

A referenced Secret doesn't exist:

```bash
kubectl describe pod -l app=secure-agent-pod -n secure-agent-pod | grep -A5 "Warning"
```

The `agent-secrets-tier1` and `agent-secrets-tier2` secretRefs are `optional: true`, so they won't block. But `agent-ssh-keys` is required — create it if missing:

```bash
kubectl create secret generic agent-ssh-keys \
  --namespace=secure-agent-pod \
  --from-file=authorized_keys=~/.ssh/id_rsa.pub
```

### Can't SSH In

1. **Check pod is running:** `kubectl get pods -n secure-agent-pod`
2. **Check sshd process:** `kubectl exec ... -- ps aux | grep sshd`
3. **Check service IP:** `kubectl get svc -n secure-agent-pod` — verify `192.168.55.215` is assigned
4. **Check authorized_keys:** `kubectl exec ... -- cat /home/claude/.ssh/authorized_keys`
5. **Check sshd logs:** `kubectl logs ... | grep sshd`

### VibeKanban Not Accessible

1. **Check process:** `kubectl exec ... -- pgrep -f vibe-kanban`
2. **Check port:** `kubectl exec ... -- curl -s http://127.0.0.1:8081` — should return HTML
3. **Check service:** `kubectl get svc secure-agent-vibekanban -n secure-agent-pod`
4. **Check env vars:** `kubectl exec ... -- env | grep -E "PORT|HOST"` — should show `PORT=8081`, `HOST=0.0.0.0`

### Env Vars Not Updated After Secret Change

Environment variables are set at container start. After changing a Secret:

```bash
kubectl rollout restart deployment/secure-agent-pod -n secure-agent-pod
```

## References

- [Building Post 21: Secure Agent Pod]({{< relref "/building/21-secure-agent-pod" >}})
- [Claude Code Hooks Documentation](https://docs.anthropic.com/en/docs/claude-code/hooks)
- [VibeKanban](https://github.com/BloopAI/vibe-kanban)
- [Cilium Network Policies](https://docs.cilium.io/en/stable/security/policy/)
- [supercronic](https://github.com/aptible/supercronic)
