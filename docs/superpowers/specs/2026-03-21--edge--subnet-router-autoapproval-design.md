# Subnet Router Auto-Approval + Split DNS

**Date:** 2026-03-21
**Layer:** edge
**Status:** Draft

## Problem

The Hop Headscale mesh has two Raspberry Pi subnet routers (raspi-vlan10-D, raspi-vlan10-E) that advertise exit node and subnet routes for three home network subnets. Currently:

1. Route approval is manual (`headscale routes enable` per route per node)
2. MagicDNS overrides the raspis' local DNS, breaking resolution of internal domains (`*.lab.derio.net`, `*.frank.derio.net`)
3. Mesh clients using an exit node can't resolve internal domains because Headscale pushes public DNS (1.1.1.1/8.8.8.8)
4. IP forwarding must be enabled on the raspis for exit node and subnet routing to work

## Solution

### Declarative changes (Headscale ConfigMap)

Single file: `clusters/hop/apps/headscale/manifests/configmap.yaml`

**1. ACL policy — add `tagOwners` + `autoApprovers`:**

```json
{
  "acls": [
    { "action": "accept", "src": ["*"], "dst": ["*:*"] }
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

- `tag:subnet-router` is owned by the `default` user (the only user currently)
- Any node tagged `tag:subnet-router` that advertises these subnets or exit node capability gets auto-approved
- The wide-open ACL stays as-is (tightening is a separate effort)

**2. DNS config — add split nameservers:**

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

- Queries for `*.lab.derio.net` and `*.frank.derio.net` go to home DNS servers (192.168.10.11/12)
- All other queries stay on 1.1.1.1/8.8.8.8
- Home DNS servers are reachable by all mesh clients via the subnet routes to 192.168.10.0/24
- `extra_records` section unchanged

### Manual operations (one-time, on each raspi)

**Raspi OS-level (both raspi-vlan10-D and raspi-vlan10-E):**

```bash
# Enable IP forwarding (persistent)
sudo sysctl -w net.ipv4.ip_forward=1
echo 'net.ipv4.ip_forward = 1' | sudo tee /etc/sysctl.d/99-ip-forward.conf

# Re-register with subnet routes + exit node + tag + no MagicDNS override
sudo tailscale up \
  --login-server=https://headscale.hop.derio.net \
  --advertise-exit-node \
  --advertise-routes=192.168.10.0/24,192.168.50.0/24,192.168.55.0/24 \
  --advertise-tags=tag:subnet-router \
  --accept-dns=false \
  --hostname=$(hostname) \
  --authkey $HEADSCALE_PREAUTH_KEY
```

- `--advertise-tags=tag:subnet-router` ensures the tag travels with registration, so autoApprovers triggers immediately on re-registration (no race condition with server-side tagging)
- `--accept-dns=false` prevents MagicDNS from overriding the raspi's OS-level DNS config
- `--authkey` uses the pre-auth key from `.env_hop` (HEADSCALE_PREAUTH_KEY)
- IP forwarding is required for both exit node and subnet routing to work

**Headscale-side (from Hop cluster, after ConfigMap deploy):**

```bash
source .env_hop

# Restart Headscale to pick up ACL + DNS changes
kubectl -n headscale-system rollout restart deploy/headscale

# Tag both nodes (one-time; future re-registrations carry the tag via --advertise-tags)
# Use `headscale nodes list` to find node IDs
kubectl -n headscale-system exec deploy/headscale -- headscale nodes list
kubectl -n headscale-system exec deploy/headscale -- headscale nodes tag --identifier <RASPI_D_ID> --tags tag:subnet-router
kubectl -n headscale-system exec deploy/headscale -- headscale nodes tag --identifier <RASPI_E_ID> --tags tag:subnet-router
```

### Blog updates

Update `blog/content/operating/11-public-edge/index.md`:
- Add a "Subnet Router Setup" section documenting the raspi-side configuration (IP forwarding, tailscale flags)
- Add a "Split DNS" section explaining the home DNS integration
- Update the "Registering an Exit Node" section to include `--advertise-routes` and `--accept-dns=false`
- Document the tagging workflow

## What does NOT change

- Headscale version (stays at 0.25.1)
- Headplane version (stays at 0.5.5)
- Existing approved routes (remain as-is)
- Other Headscale config sections (DERP, database, prefixes, logging)

## Known Limitations

- **DNS depends on subnet routes**: Split DNS for `*.lab.derio.net` and `*.frank.derio.net` relies on the home DNS servers (192.168.10.11/12) being reachable via the subnet route to 192.168.10.0/24. If both raspis are offline, mesh clients lose resolution of these domains. This is acceptable — those services are also unreachable without the subnet routes.

## Verification

After deployment:

```bash
# Verify ACL policy loaded (check Headscale logs for errors)
kubectl -n headscale-system logs deploy/headscale | grep -i "acl\|policy\|error"

# Verify split DNS works from a mesh client
dig lab.derio.net  # Should resolve via 192.168.10.11

# Verify subnet routes work (without exit node)
ping 192.168.55.21  # Should reach mini-1 via subnet route

# Verify exit node connectivity
tailscale set --exit-node=raspi-vlan10-d
ping google.com        # Should work (IP forwarding enabled)
ping nas.lab.derio.net # Should resolve and respond
tailscale set --exit-node=  # Disconnect exit node

# Verify auto-approval (simulate by re-registering a raspi)
# New routes should appear as Enabled without manual approval
```
