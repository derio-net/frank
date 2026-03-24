---
title: "Persistent Agent — A Kali Workstation on Kubernetes"
date: 2026-03-24
draft: false
tags: ["kali", "claude", "agent", "ssh", "gpu-1", "persistent"]
summary: "Deploying a persistent Kali Linux container on gpu-1 as an always-on Claude Code workstation — because laptops sleep and mobile apps have limits."
weight: 19
cover:
  image: cover.png
  alt: "Frank the cluster monster at a workstation terminal with an always-on green status light"
  relative: true
---

My laptop is not always online. The Claude mobile app is useful but limited — you can't run terminal commands, install tools, or maintain a persistent workspace from it. What I wanted was a Claude Code instance that's always reachable, always has context, and never sleeps because the lid closed.

This post covers deploying a persistent Kali Linux container on gpu-1 as an always-on development workstation, accessible via SSH from anywhere on the network.

## Why a Container Instead of a VM?

A Kubernetes Deployment with a PVC is simpler than standing up a full virtual machine. The container:

- **Survives restarts** — the 50Gi PVC at `/root` preserves the home directory, installed tools, SSH host keys, and Claude Code configuration across pod restarts.
- **Self-heals** — if the pod crashes, Kubernetes restarts it. If gpu-1 reboots, the pod comes back automatically.
- **Fits the GitOps model** — the entire workstation is defined in six YAML files under `apps/kali/manifests/`, managed by ArgoCD like every other service on the cluster.

A VM would give a full OS with its own kernel, but for a development workstation that mostly runs a terminal, a container is the right tool.

## Why Kali?

Kali Linux comes with a massive repository of security and networking tools pre-packaged. Even though the primary use case here is Claude Code, having `nmap`, `netcat`, `tcpdump`, and hundreds of other tools a single `apt-get install` away makes it a versatile workstation for anything beyond just coding.

## Architecture

```
gpu-1 (i9, 128GB RAM)
├── kali (replicas: 1, always-on)
│   ├── SSH server on port 22
│   ├── /root → 50Gi PVC (longhorn-gpu-local)
│   └── Claude Code (installed post-deploy)
├── ollama (replicas: 1, GPU workload)
└── comfyui (replicas: 0, GPU workload)
```

The Kali container runs on gpu-1 but does **not** request a GPU resource. It's there for the 128GB of RAM and the i9 CPU — overkill for a shell, but ideal for running Claude Code's agent loops, large context operations, and any compute-heavy tasks Claude might kick off. The GPU taint is tolerated but no `nvidia.com/gpu` resource is claimed, so it coexists peacefully with Ollama and ComfyUI.

One ArgoCD app, raw manifests:

| Resource | Purpose |
|----------|---------|
| Namespace | `kali-system` with privileged PodSecurity |
| Deployment | `kalilinux/kali-rolling`, pinned to gpu-1 |
| PVC | 50Gi on `longhorn-gpu-local` (single replica, local to gpu-1) |
| ConfigMap | Startup script — installs sshd, configures key-only auth |
| Secret | SSH `authorized_keys` (public key, managed by ArgoCD) |
| Service | LoadBalancer at `192.168.55.215:22` via Cilium L2 |

## The Startup Script

The container uses the official `kalilinux/kali-rolling` image with no customisation. A ConfigMap-mounted startup script handles everything:

```bash
#!/bin/bash
set -e

# Install SSH server (~30s on first boot, fast on subsequent)
apt-get update -qq
apt-get install -y -qq openssh-server curl git procps

# Persist SSH host keys in /root (PVC-backed)
HOST_KEY_DIR=/root/.ssh-host-keys
mkdir -p "$HOST_KEY_DIR"
if [ -f "$HOST_KEY_DIR/ssh_host_ed25519_key" ]; then
  cp "$HOST_KEY_DIR"/ssh_host_* /etc/ssh/
else
  ssh-keygen -A
  cp /etc/ssh/ssh_host_* "$HOST_KEY_DIR/"
fi

# Copy authorized_keys from mounted Secret
cp /etc/ssh-keys/authorized_keys /root/.ssh/authorized_keys

# Key-only auth, no passwords
cat > /etc/ssh/sshd_config.d/kali-k8s.conf <<'SSHCONF'
PermitRootLogin prohibit-password
PubkeyAuthentication yes
PasswordAuthentication no
SSHCONF

/usr/sbin/sshd
exec sleep infinity
```

Two things worth noting:

1. **Host key persistence.** SSH host keys are generated once and stored in `/root/.ssh-host-keys/` — which is on the PVC. Without this, every pod restart would regenerate the keys and every SSH client would warn about a changed host fingerprint.

2. **No custom image.** The `apt-get install` runs on every pod start (~30 seconds). For a workstation that restarts maybe once a month, building and maintaining a custom Docker image isn't worth the overhead. If startup time ever matters, the image can be baked later.

## SSH Key as a Public Resource

The SSH `authorized_keys` file contains a public key — it's not sensitive. Instead of the usual SOPS-encrypted secret applied out-of-band, the key lives directly in `apps/kali/manifests/secret.yaml` and ArgoCD manages it like any other resource. No manual steps required.

## Storage Choice

The PVC uses `longhorn-gpu-local` — a StorageClass configured for single-replica, strict-local storage on gpu-1. Since the pod is pinned to gpu-1 via `nodeSelector`, replicating the data to other nodes would be pure waste. Local storage means faster I/O and no network overhead.

## The Always-On Agent

The real value isn't the container itself — it's what runs inside it. After deployment:

```bash
ssh root@192.168.55.215
# Install Claude Code
# Run claude --remote for headless access
```

Claude Code's `--remote` flag starts a headless session that persists independently of the SSH connection. You can start a task from your laptop, close the lid, and check results from your phone later. The agent keeps running because the container keeps running — it doesn't depend on your local machine being online.

This turns the homelab into an always-on development environment. Schedule tasks, run long agent loops, maintain persistent project context — all on hardware you control, with 128GB of RAM and no session timeouts.

## What's Running

After ArgoCD syncs:

- **Pod** runs on gpu-1 with SSH listening on port 22
- **Service** exposes SSH at `192.168.55.215` via Cilium L2 LoadBalancer
- **PVC** preserves `/root` across restarts — Claude Code config, project files, tool installations all persist

Connect with `ssh root@192.168.55.215` from any machine on the `192.168.55.x` network. For remote access outside the LAN, the Headscale mesh from [Layer 17]({{< relref "/building/17-public-edge" >}}) routes traffic through the Hop edge cluster.
