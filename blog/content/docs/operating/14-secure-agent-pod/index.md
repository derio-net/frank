---
title: "Operating on Secure Agent Pod"
date: 2026-03-31
draft: false
tags: ["operations", "security", "agent", "claude", "ssh", "vibekanban", "cilium", "cron", "telegram", "monitoring"]
summary: "Day-to-day commands for managing the secure agent pod — SSH access, process health, VibeKanban, secret rotation, and troubleshooting."
weight: 114
---

This is the operational companion to [Secure Agent Pod — Hardening an AI Coding Workstation]({{< relref "/docs/building/21-secure-agent-pod" >}}). That post explains the architecture and security model. This one is the day-to-day runbook.

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

```console
$ kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- ps aux
USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
claude         1  0.0  0.0   2580  1660 ?        Ss   10:04   0:00 /usr/bin/tini -- /entrypoint.sh
claude         7  0.0  0.0   4800  4004 ?        S    10:04   0:00 /bin/bash /entrypoint.sh
claude        61  0.0  0.0  11728  7824 ?        S    10:04   0:02 sshd: /usr/sbin/sshd -f /opt/sshd_config -D [listener] 0 of 10-100 startups
claude        62  0.0  0.0 1235728 12888 ?       Sl   10:04   0:01 supercronic /home/claude/.crontab
claude        87  2.9  0.2 74304156 289264 ?     Sl   10:04  12:07 claude remote-control --name willikins
claude        90  0.0  0.0      0     0 ?        Z    10:04   0:00 [bash] <defunct>
claude       114  2.2  0.2 74801300 337700 ?     Sl   10:05   9:16 /home/claude/.local/share/claude/versions/2.1.114 --print --sdk-url https://api.anthropic.com/v1/code/sessions/cse_017vLRL4XN2iH98AYwTRrJP1 --session-id cse_017vLRL4XN2iH98AYwTRrJP1 --input-format stream-json --output-format stream-json --replay-user-messages
claude       139  0.0  0.0 1331420 82652 ?       Sl   10:05   0:00 npm exec @upstash/context7-mcp
claude       140  0.0  0.0 1331360 80980 ?       Sl   10:05   0:00 npm exec @playwright/mcp@latest
claude       233  0.0  0.0   2692  1804 ?        S    10:05   0:00 sh -c playwright-mcp
claude       234  0.0  0.0 11546244 101744 ?     Sl   10:05   0:00 node /home/claude/.npm/_npx/9833c18b2d85bc59/node_modules/.bin/playwright-mcp
claude       241  0.0  0.0   2692  1896 ?        S    10:05   0:00 sh -c context7-mcp
claude       242  0.0  0.0 22080036 86712 ?      Sl   10:05   0:00 node /home/claude/.npm/_npx/eea2bd7412d4593b/node_modules/.bin/context7-mcp
claude       496  0.0  0.0   2688  1868 ?        S    10:05   0:00 sh /home/claude/.vscode-server/cli/servers/Stable-41dd792b5e652393e7787322889ed5fdc58bd75b/server/bin/code-server --connection-token=remotessh --accept-server-license-terms --start-server --enable-remote-auto-shutdown --socket-path=/tmp/code-e55d48f9-02d8-48a6-bde0-c569cba2545b
claude       500  0.1  0.1 11857512 135668 ?     Sl   10:05   0:47 /home/claude/.vscode-server/cli/servers/Stable-41dd792b5e652393e7787322889ed5fdc58bd75b/server/node /home/claude/.vscode-server/cli/servers/Stable-41dd792b5e652393e7787322889ed5fdc58bd75b/server/out/server-main.js --connection-token=remotessh --accept-server-license-terms --start-server --enable-remote-auto-shutdown --socket-path=/tmp/code-e55d48f9-02d8-48a6-bde0-c569cba2545b
claude       522  0.5  0.5 55084784 775564 ?     Sl   10:05   2:18 /home/claude/.vscode-server/cli/servers/Stable-41dd792b5e652393e7787322889ed5fdc58bd75b/server/node --dns-result-order=ipv4first /home/claude/.vscode-server/cli/servers/Stable-41dd792b5e652393e7787322889ed5fdc58bd75b/server/out/bootstrap-fork --type=extensionHost --transformURIs --useHostProxy=false
claude       534  0.0  0.0 1461952 69704 ?       Sl   10:05   0:05 /home/claude/.vscode-server/cli/servers/Stable-41dd792b5e652393e7787322889ed5fdc58bd75b/server/node /home/claude/.vscode-server/cli/servers/Stable-41dd792b5e652393e7787322889ed5fdc58bd75b/server/out/bootstrap-fork --type=fileWatcher
claude       547  0.2  0.0 1167188 82896 ?       Sl   10:05   1:03 /home/claude/.vscode-server/cli/servers/Stable-41dd792b5e652393e7787322889ed5fdc58bd75b/server/node /home/claude/.vscode-server/cli/servers/Stable-41dd792b5e652393e7787322889ed5fdc58bd75b/server/out/bootstrap-fork --type=ptyHost --logsPath /home/claude/.vscode-server/data/logs/20260420T100549
claude       834  0.0  0.0 1056608 97932 ?       Sl   10:05   0:02 /home/claude/.vscode-server/cli/servers/Stable-41dd792b5e652393e7787322889ed5fdc58bd75b/server/node /home/claude/.vscode-server/cli/servers/Stable-41dd792b5e652393e7787322889ed5fdc58bd75b/server/extensions/markdown-language-features/dist/serverWorkerMain --node-ipc --clientProcessId=522
claude       842  0.0  0.0 1027804 67276 ?       Sl   10:05   0:01 /home/claude/.vscode-server/cli/servers/Stable-41dd792b5e652393e7787322889ed5fdc58bd75b/server/node /home/claude/.vscode-server/cli/servers/Stable-41dd792b5e652393e7787322889ed5fdc58bd75b/server/extensions/json-language-features/server/dist/node/jsonServerMain --node-ipc --clientProcessId=522
claude      2317  0.0  0.0   4560  4116 pts/0    Ss   10:06   0:00 /bin/bash --init-file /home/claude/.vscode-server/cli/servers/Stable-41dd792b5e652393e7787322889ed5fdc58bd75b/server/out/vs/workbench/contrib/terminal/common/scripts/shellIntegration-bash.sh
claude     29115  0.0  0.0  16932 10008 ?        Ss   11:16   0:00 sshd-session: claude [priv]
claude     29117  0.1  0.0  17812  7724 ?        S    11:16   0:23 sshd-session: claude@notty
claude     29118  0.0  0.0   4164  3400 ?        Ss   11:16   0:00 -bash
claude     29122  0.0  0.0   2688  2040 ?        S    11:16   0:00 sh
claude     29140  0.1  0.0 104044 22456 ?        Sl   11:16   0:27 /home/claude/.vscode-server/code-41dd792b5e652393e7787322889ed5fdc58bd75b command-shell --cli-data-dir /home/claude/.vscode-server/cli --parent-process-id 29122 --on-host=127.0.0.1 --on-port
claude    123942  3.8  0.3 75020492 441656 pts/0 Sl+  16:24   1:10 claude
claude    123971  0.0  0.0 1331164 81652 pts/0   Sl+  16:24   0:00 npm exec @upstash/context7-mcp
claude    124143  0.0  0.0   2688  1800 pts/0    S+   16:24   0:00 sh -c context7-mcp
claude    124144  0.0  0.0 22080388 85884 pts/0  Sl+  16:24   0:00 node /home/claude/.npm/_npx/eea2bd7412d4593b/node_modules/.bin/context7-mcp
claude    130927  0.0  0.0   4560  4144 pts/1    Ss   16:36   0:00 /bin/bash --init-file /home/claude/.vscode-server/cli/servers/Stable-41dd792b5e652393e7787322889ed5fdc58bd75b/server/out/vs/workbench/contrib/terminal/common/scripts/shellIntegration-bash.sh
claude    130990  1.2  0.2 74914732 370680 pts/1 Sl+  16:36   0:14 claude
claude    131020  0.0  0.0 1332068 81756 pts/1   Sl+  16:36   0:00 npm exec @upstash/context7-mcp
claude    131026  0.0  0.0 1330936 80600 pts/1   Sl+  16:36   0:00 npm exec @playwright/mcp@latest
claude    131236  0.0  0.0   2688  1832 pts/1    S+   16:36   0:00 sh -c playwright-mcp
claude    131237  0.0  0.0 11545984 102492 pts/1 Sl+  16:36   0:00 node /home/claude/.npm/_npx/9833c18b2d85bc59/node_modules/.bin/playwright-mcp
claude    131243  0.0  0.0   2688  1960 pts/1    S+   16:36   0:00 sh -c context7-mcp
claude    131244  0.0  0.0 22080376 86764 pts/1  Sl+  16:36   0:00 node /home/claude/.npm/_npx/eea2bd7412d4593b/node_modules/.bin/context7-mcp
claude    133948  0.0  0.0   2596  1636 ?        S    16:52   0:00 sleep 180
claude    134228 42.8  0.0   6544  3976 ?        Rs   16:55   0:00 ps aux
```

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

Cron is managed by supercronic reading `/home/claude/.crontab`. The crontab template is seeded from the image on first boot; after that it's user-modifiable on the PVC.

Scripts live at `/opt/scripts/` — baked into the image, immutable. They update when the `secure-agent-kali` image is rebuilt and the pod is restarted.

```bash
# View current crontab
cat ~/.crontab

# View available scripts
ls /opt/scripts/
# audit-digest.sh      guardrails-hook.py  push-heartbeat.sh
# exercise-cron.sh     notify-telegram.sh  session-manager.sh

# Edit crontab (supercronic picks up changes automatically)
vi ~/.crontab
```

### Current Schedule

| Job | Schedule | Script |
|-----|----------|--------|
| Session manager | Every 5 min | `/opt/scripts/session-manager.sh` |
| Self-update (git pull) | Daily 04:00 UTC | inline |
| Claude Code update | Weekly Sun 04:30 UTC | inline |
| Exercise reminders | 5x daily, Fri-Mon | `/opt/scripts/exercise-cron.sh` |
| Audit digest | Daily 21:00 UTC | `/opt/scripts/audit-digest.sh` |

### Updating Scripts

Scripts at `/opt/scripts/` are read-only (from the image). To update them:

1. Commit changes to the `secure-agent-kali` repo
2. GHA rebuilds and pushes the image to GHCR
3. Restart the pod: `kubectl rollout restart deployment/secure-agent-pod -n secure-agent-pod`

The crontab on the PVC is independent — editing `~/.crontab` takes effect immediately via supercronic's file watcher.

## Health Monitoring

Each cron script pushes a heartbeat metric to Prometheus Pushgateway after successful execution:

```bash
# Check current heartbeat state
curl -s http://pushgateway.monitoring.svc.cluster.local:9091/api/v1/metrics | \
  python3 -c "
import json, sys
from datetime import datetime, timezone
for g in json.load(sys.stdin)['data']:
    job = g['labels'].get('job','?')
    ts = float(g['push_time_seconds']['metrics'][0]['value'])
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%H:%M:%S UTC')
    print(f'{job:30s} {dt}')
"
```

Grafana alert rules fire when heartbeats go stale:

| Alert | Threshold | Severity |
|-------|-----------|----------|
| `exercise-reminder-stale` | 3 hours | critical |
| `audit-digest-stale` | 26 hours | warning |
| `session-manager-stale` | 10 minutes | critical |

Alerts are bridged to GitHub Issues via the health-bridge webhook — the Quartermaster (Willikins staff) tracks these on the "Derio Ops" project board.

### Manually Pushing a Heartbeat

```bash
/opt/scripts/push-heartbeat.sh <job_name> [label=value ...]
# Example: /opt/scripts/push-heartbeat.sh exercise_reminder context=desk
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

- [Building Post 21: Secure Agent Pod]({{< relref "/docs/building/21-secure-agent-pod" >}})
- [Claude Code Hooks Documentation](https://docs.anthropic.com/en/docs/claude-code/hooks)
- [VibeKanban](https://github.com/BloopAI/vibe-kanban)
- [Cilium Network Policies](https://docs.cilium.io/en/stable/security/policy/)
- [supercronic](https://github.com/aptible/supercronic)
