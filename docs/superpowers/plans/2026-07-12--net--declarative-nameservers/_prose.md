# Declarative DNS nameservers on all Frank hosts

**Spec:** `docs/superpowers/specs/2026-07-12--net--declarative-nameservers-design.md`
**Layer:** net · **Branch:** feat/declarative-nameservers

## Why

A power-restart put gpu-1 into a 12h "pinging but dead" hang. Root cause: its
USB 2.5G adapter is statically configured (`dhcp: false`) with **no
`nameservers`**, so Talos fell back to the built-in public resolvers
`1.1.1.1`/`8.8.8.8` — which the homelab blocks network-wide by ACL. No DNS → no
NTP (`time.cloudflare.com` is a hostname) → Talos gates `apid`/`kubelet`/
`siderolink` on time-sync → the node never finishes booting.

The minis/raspis/pc-1 never hit this only because they use **DHCP** and receive
the internal resolvers `192.168.10.11`/`192.168.10.12` from the DHCP server.
Internal DNS is a **cornerstone of the homelab's network isolation**, and today
the whole fleet depends on it silently. This plan makes it **declarative on
every host** so no static-networked host is ever one config change away from the
outage.

## Approach

A single **cluster-wide Omni ConfigPatch** (`102-cluster-nameservers`, labelled
`omni.sidero.dev/cluster: frank`) sets `machine.network.nameservers` for all 7
hosts. It merges independently of gpu-1's per-node interface config, and for the
DHCP hosts the values equal what DHCP already serves — so it changes nothing
behaviourally, only makes the dependency explicit. A pure-Python guard test
prevents regression: any static-interface patch (`dhcp: false` + `addresses:`)
requires the cluster-wide nameservers patch to exist.

## Phases

- **Phase 1 (agentic, TDD):** guard test (red) → cluster-wide nameservers patch
  (green). Closes acceptance `net-all-hosts-declarative-dns` via the unit guard.
- **Phase 2 (agentic):** point the gpu-1 404 patch + template at the cluster
  patch (single source of truth); gotcha docs (`frank-gotchas.md` one-liner +
  `networking.md` full prose + `gpu-1.md` cross-ref); `/sync-runbook`.
- **Phase 3 (manual, back-loaded):** operator applies the patch staged
  (gpu-1 → minis → edge, verifying each), then clears the gpu-1 DHCP drift.
  Closes `net-static-host-resolves-internal-dns` and
  `net-gpu1-single-declarative-ip` in the post-merge Test Plan.

## Manual operations

Both are authored as `# manual-operation` blocks in `03.yaml` and synced to
`docs/runbooks/manual-operations.yaml` in Phase 2:

- `net-apply-cluster-nameservers` — staged `omnictl apply -f` with per-group
  verification; gpu-1 first (the static host that proves the mechanism), then
  minis, then edge.
- `net-gpu1-clear-dhcp-drift` — after the nameservers patch is applied and
  verified, revert gpu-1's console/platform network override so the
  machine-config `dhcp: false` is authoritative → single `.31`, no `.150`.
  **Order matters**: reverting before config-layer DNS exists would re-break
  gpu-1.

## Safety

gpu-1 is currently `Ready`. The apply is additive/idempotent (nameservers equal
DHCP-provided values), staged, and verified per group. Rollback:
`omnictl delete configpatch 102-cluster-nameservers`.
