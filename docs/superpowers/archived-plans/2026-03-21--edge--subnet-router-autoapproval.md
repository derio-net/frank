# Subnet Router Auto-Approval + Split DNS Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Configure Headscale to auto-approve subnet routes and exit nodes for tagged nodes, and add split DNS for internal domains.

**Architecture:** Update the Headscale ConfigMap's ACL policy with `autoApprovers` and add split DNS nameservers. Document raspi-side setup and tagging workflow in the operating blog post.

**Tech Stack:** Headscale 0.25.1, Kubernetes ConfigMap, Hugo blog

**Status:** Deployed

**Spec:** `docs/superpowers/specs/2026-03-21--edge--subnet-router-autoapproval-design.md`

---

### Task 1: Update Headscale ACL Policy with autoApprovers

**Files:**
- Modify: `clusters/hop/apps/headscale/manifests/configmap.yaml:62-72`

- [x] **Step 1: Replace the `acl.yaml` section in the ConfigMap**

Replace lines 62-72 of `clusters/hop/apps/headscale/manifests/configmap.yaml` — the `acl.yaml` data key — with:

```yaml
  acl.yaml: |
    {
      // Allow all traffic within the mesh for now — tighten later
      "acls": [
        {
          "action": "accept",
          "src": ["*"],
          "dst": ["*:*"]
        }
      ],
      "tagOwners": {
        "tag:subnet-router": ["default"]
      },
      "autoApprovers": {
        "routes": {
          "192.168.10.0/24": ["tag:subnet-router"],
          "192.168.50.0/24": ["tag:subnet-router"],
          "192.168.55.0/24": ["tag:subnet-router"]
        },
        "exitNode": ["tag:subnet-router"]
      }
    }
```

- [x] **Step 2: Verify the YAML is valid**

Run: `kubectl --dry-run=client -o yaml -f clusters/hop/apps/headscale/manifests/configmap.yaml`
Expected: Valid YAML output, no errors.

---

### Task 2: Add Split DNS Nameservers to Headscale Config

**Files:**
- Modify: `clusters/hop/apps/headscale/manifests/configmap.yaml:40-53`

- [x] **Step 1: Add the `split` key under `dns.nameservers`**

In the `config.yaml` data key, replace the `dns` section (lines 40-53) with:

```yaml
    dns:
      base_domain: mesh.hop.derio.net
      magic_dns: true
      nameservers:
        global:
          - 1.1.1.1
          - 8.8.8.8
        split:
          lab.derio.net:
            - 192.168.10.11
            - 192.168.10.12
          frank.derio.net:
            - 192.168.10.11
            - 192.168.10.12
      extra_records:
        - name: headplane.hop.derio.net
          type: A
          value: 100.64.0.4
        - name: entry.hop.derio.net
          type: A
          value: 100.64.0.4
```

- [x] **Step 2: Verify the full ConfigMap is valid**

Run: `kubectl --dry-run=client -o yaml -f clusters/hop/apps/headscale/manifests/configmap.yaml`
Expected: Valid YAML output, no errors.

- [x] **Step 3: Commit the ConfigMap changes**

```bash
git add clusters/hop/apps/headscale/manifests/configmap.yaml
git commit -m "feat(edge): add autoApprovers and split DNS to Headscale config"
```

---

### Task 3: Update Operating Blog Post

**Files:**
- Modify: `blog/content/operating/11-public-edge/index.md`

- [x] **Step 1: Rewrite the "Registering an Exit Node" section (line 186)**

Replace the existing "Registering an Exit Node" section (lines 186-234) with an updated version that covers the combined subnet router + exit node setup:

```markdown
### Registering a Subnet Router / Exit Node

A subnet router advertises LAN subnets to the mesh, making homelab services reachable from any mesh client. An exit node routes all internet traffic through itself. The Raspberry Pi subnet routers serve both roles.

**Prerequisites on the device:**

```bash
# Enable IP forwarding (required for routing — persistent across reboots)
sudo sysctl -w net.ipv4.ip_forward=1
echo 'net.ipv4.ip_forward = 1' | sudo tee /etc/sysctl.d/99-ip-forward.conf
```

**Step 1 — Register the device with subnet routes, exit node, and tag:**

```bash
sudo tailscale up \
  --login-server=https://headscale.hop.derio.net \
  --advertise-exit-node \
  --advertise-routes=192.168.10.0/24,192.168.50.0/24,192.168.55.0/24 \
  --advertise-tags=tag:subnet-router \
  --accept-dns=false \
  --hostname=$(hostname) \
  --authkey $HEADSCALE_PREAUTH_KEY
```

Key flags:
- `--advertise-routes` — exposes these LAN subnets to all mesh clients
- `--advertise-exit-node` — offers this node as an exit node for tunneling all traffic
- `--advertise-tags=tag:subnet-router` — carries the tag with registration so `autoApprovers` in the ACL policy auto-approves routes immediately
- `--accept-dns=false` — prevents MagicDNS from overriding the device's OS-level DNS (the raspis need their local DNS to resolve internal hostnames)
- `--authkey` — pre-auth key from `.env_hop` (`HEADSCALE_PREAUTH_KEY`)

**Step 2 — Tag the node (one-time, for existing nodes without the tag):**

If the node was registered before `--advertise-tags` was added, apply the tag server-side:

```bash
source .env_hop
kubectl -n headscale-system exec deploy/headscale -- headscale nodes list
kubectl -n headscale-system exec deploy/headscale -- \
  headscale nodes tag --identifier <NODE_ID> --tags tag:subnet-router
```

Future re-registrations carry the tag automatically via `--advertise-tags`.

**Step 3 — Verify routes are approved:**

```bash
kubectl -n headscale-system exec deploy/headscale -- headscale routes list
```

All routes should show `Enabled: true`. With `autoApprovers` configured, no manual `headscale routes enable` is needed.

**Step 4 — Use the exit node from another mesh client:**

```bash
# Connect to the exit node
tailscale set --exit-node=<exit-node-hostname>

# Verify internet traffic routes through the exit node
curl ifconfig.me
# Should show the exit node's network's public IP

# Verify LAN access
ping 192.168.55.21  # Frank cluster mini-1

# Disconnect
tailscale set --exit-node=
```

**Gotcha:** `--login-server` must use the **public URL** (`https://headscale.hop.derio.net`), not the Kubernetes-internal service name. The internal name only resolves inside the Hop cluster's pod network.

**Gotcha:** Without `net.ipv4.ip_forward=1` on the device, exit node connections will appear to work (Tailscale reports connected) but all traffic will black-hole — `ping google.com` hangs silently.
```

- [x] **Step 2: Add a "Split DNS" section after the new subnet router section**

Insert after the rewritten section (before "Adding a Mesh-Only Service"):

```markdown
### Split DNS for Internal Domains

Headscale pushes split DNS configuration to all mesh clients. Queries for internal domains go to the home DNS servers; everything else uses public DNS.

| Domain | Nameservers | Purpose |
|--------|-------------|---------|
| `*.lab.derio.net` | 192.168.10.11, 192.168.10.12 | Home lab services |
| `*.frank.derio.net` | 192.168.10.11, 192.168.10.12 | Frank cluster services |
| Everything else | 1.1.1.1, 8.8.8.8 | Public DNS |

The home DNS servers (192.168.10.11/12) are on the 192.168.10.0/24 subnet, which is advertised by the subnet routers. Any mesh client can reach them — you don't need to be using an exit node.

**Verify split DNS from a mesh client:**

```bash
# Should resolve via home DNS
dig litellm.frank.derio.net

# Should resolve via public DNS
dig google.com
```

**Limitation:** If both Raspberry Pi subnet routers are offline, mesh clients lose both the subnet routes and DNS resolution for `*.lab.derio.net` and `*.frank.derio.net`. This is consistent — the services themselves are also unreachable without the subnet routes.

To add more internal domains to split DNS, edit the Headscale ConfigMap's `dns.nameservers.split` section and restart Headscale:

```bash
kubectl -n headscale-system rollout restart deploy/headscale
```
```

- [x] **Step 3: Verify the blog builds**

Run: `cd blog && hugo --minify`
Expected: Build succeeds with no errors.

- [x] **Step 4: Commit the blog update**

```bash
git add blog/content/operating/11-public-edge/index.md
git commit -m "docs(edge): add subnet router, exit node, and split DNS operations"
```

---

### Task 4: Deploy and Verify

- [x] **Step 1: Push and let ArgoCD sync**

```bash
git push
```

ArgoCD auto-syncs the ConfigMap changes. Verify sync:

```bash
source .env_hop
argocd app get headscale --port-forward --port-forward-namespace argocd
```

Expected: `Synced` and `Healthy`.

- [x] **Step 2: Restart Headscale to pick up config changes**

```bash
kubectl -n headscale-system rollout restart deploy/headscale
kubectl -n headscale-system rollout status deploy/headscale
```

Expected: Rollout completes successfully.

- [x] **Step 3: Verify ACL policy loaded**

```bash
kubectl -n headscale-system logs deploy/headscale | grep -i "acl\|policy\|error"
```

Expected: No policy errors. Look for successful policy load messages.

- [x] **Step 4: Tag existing raspi nodes (skip if re-registering in Steps 5-6)**

If the raspis will be re-registered with `--advertise-tags=tag:subnet-router` in Steps 5-6, this step is redundant — the tag travels with registration. Only needed if deferring raspi re-registration.

```bash
# Get node IDs
kubectl -n headscale-system exec deploy/headscale -- headscale nodes list

# Tag both nodes
kubectl -n headscale-system exec deploy/headscale -- \
  headscale nodes tag --identifier <RASPI_D_ID> --tags tag:subnet-router
kubectl -n headscale-system exec deploy/headscale -- \
  headscale nodes tag --identifier <RASPI_E_ID> --tags tag:subnet-router
```

# manual-operation
```yaml
id: edge-tag-subnet-routers
layer: edge
app: headscale
plan: docs/superpowers/plans/2026-03-21--edge--subnet-router-autoapproval.md
when: After ConfigMap deploy and Headscale restart
why_manual: Node tagging is an imperative Headscale CLI operation; cannot be declared in config
commands:
  - source .env_hop
  - kubectl -n headscale-system exec deploy/headscale -- headscale nodes list
  - kubectl -n headscale-system exec deploy/headscale -- headscale nodes tag --identifier <RASPI_D_ID> --tags tag:subnet-router
  - kubectl -n headscale-system exec deploy/headscale -- headscale nodes tag --identifier <RASPI_E_ID> --tags tag:subnet-router
verify:
  - kubectl -n headscale-system exec deploy/headscale -- headscale nodes list  # Both nodes should show tag:subnet-router
status: pending
```

- [x] **Step 5: Configure raspi-vlan10-D (SSH to device)**

```bash
# On raspi-vlan10-D:
sudo sysctl -w net.ipv4.ip_forward=1
echo 'net.ipv4.ip_forward = 1' | sudo tee /etc/sysctl.d/99-ip-forward.conf

sudo tailscale up \
  --login-server=https://headscale.hop.derio.net \
  --advertise-exit-node \
  --advertise-routes=192.168.10.0/24,192.168.50.0/24,192.168.55.0/24 \
  --advertise-tags=tag:subnet-router \
  --accept-dns=false \
  --hostname=$(hostname) \
  --authkey $HEADSCALE_PREAUTH_KEY
```

# manual-operation
```yaml
id: edge-configure-raspi-d
layer: edge
app: headscale
plan: docs/superpowers/plans/2026-03-21--edge--subnet-router-autoapproval.md
when: After Headscale ConfigMap deploy
why_manual: Raspberry Pis are standalone devices outside the cluster; OS and Tailscale config is imperative
commands:
  - sudo sysctl -w net.ipv4.ip_forward=1
  - echo 'net.ipv4.ip_forward = 1' | sudo tee /etc/sysctl.d/99-ip-forward.conf
  - sudo tailscale up --login-server=https://headscale.hop.derio.net --advertise-exit-node --advertise-routes=192.168.10.0/24,192.168.50.0/24,192.168.55.0/24 --advertise-tags=tag:subnet-router --accept-dns=false --hostname=$(hostname) --authkey $HEADSCALE_PREAUTH_KEY
verify:
  - cat /proc/sys/net/ipv4/ip_forward  # Should return 1
  - tailscale status  # Should show connected with tag:subnet-router
status: complete
```

- [x] **Step 6: Configure raspi-vlan10-E (SSH to device)**

Same commands as Step 5, on raspi-vlan10-E.

# manual-operation
```yaml
id: edge-configure-raspi-e
layer: edge
app: headscale
plan: docs/superpowers/plans/2026-03-21--edge--subnet-router-autoapproval.md
when: After Headscale ConfigMap deploy
why_manual: Raspberry Pis are standalone devices outside the cluster; OS and Tailscale config is imperative
commands:
  - sudo sysctl -w net.ipv4.ip_forward=1
  - echo 'net.ipv4.ip_forward = 1' | sudo tee /etc/sysctl.d/99-ip-forward.conf
  - sudo tailscale up --login-server=https://headscale.hop.derio.net --advertise-exit-node --advertise-routes=192.168.10.0/24,192.168.50.0/24,192.168.55.0/24 --advertise-tags=tag:subnet-router --accept-dns=false --hostname=$(hostname) --authkey $HEADSCALE_PREAUTH_KEY
verify:
  - cat /proc/sys/net/ipv4/ip_forward  # Should return 1
  - tailscale status  # Should show connected with tag:subnet-router
status: complete
```

- [x] **Step 7: Verify end-to-end from a mesh client (e.g., Mac)**

```bash
# Verify split DNS
dig litellm.frank.derio.net  # Should resolve via 192.168.10.11
dig google.com                # Should resolve via 1.1.1.1

# Verify subnet routes (without exit node)
ping 192.168.55.21  # Should reach Frank mini-1

# Verify exit node
tailscale set --exit-node=raspi-vlan10-d
ping google.com         # Should work
ping nas.lab.derio.net  # Should resolve and respond
tailscale set --exit-node=  # Disconnect

# Verify routes list
source .env_hop
kubectl -n headscale-system exec deploy/headscale -- headscale routes list
# All routes should show Enabled: true
```

- [x] **Step 8: Update plan status**

Set Status in this plan header to `Deployed`.

- [x] **Step 9: Sync Hop blog**

```bash
source .env_hop
kubectl -n blog-system rollout restart deploy/blog
```

- [x] **Step 10: Sync runbook**

Run `/sync-runbook` to sync the three `# manual-operation` blocks to `docs/runbooks/manual-operations.yaml`.
