# Declarative DNS nameservers on all Frank hosts — Design

**Date:** 2026-07-12
**Layer:** net
**Status:** Draft
**Slug:** declarative-nameservers
**Branch:** feat/declarative-nameservers

## Context — the incident that motivated this

On 2026-07-12, after a full cluster power-restart, **gpu-1 was down ~12h**:
pingable at the IP layer but with Talos `apid`/`kubelet`/`siderolink` never
starting — the node hung "pinging but dead."

Root-cause chain (fully diagnosed live):

1. gpu-1's USB 2.5G adapter is configured with a **static** address via
   `patches/phase04-gpu/404-gpu1-usb-25g-nic.yaml`
   (`deviceSelector.hardwareAddr: 6c:1f:f7:c6:e0:da`, `dhcp: false`,
   `addresses: [192.168.55.31/24]`) — but **no `nameservers`**.
2. A static Talos interface with `dhcp: false` and no nameservers falls back to
   Talos's built-in **public** resolvers `1.1.1.1` / `8.8.8.8`.
3. Those public resolvers are **ACL-blocked network-wide by design** (the
   homelab forces internal DNS). So gpu-1 could not resolve **anything**.
4. Talos NTP (`time.cloudflare.com`) is a hostname → DNS failure → **NTP never
   synced**.
5. Talos **gates service startup on time-sync** → `apid`, `kubelet`,
   `siderolink` block forever. Network up (ICMP), service layer dead.

The console screenshot confirmed the exact failure: repeated
`error serving dns request … read udp …->192.168.10.12:53: i/o timeout`,
`failed looking up "time.cloudflare.com"`, `lookup omni.frank.derio.net …
server misbehaving`, and `startAllServices: service "apid" to be up`.

**Why the other nodes were fine:** the minis / raspis / pc-1 use **DHCP**, and
the DHCP server hands them the internal resolvers `192.168.10.11` /
`192.168.10.12`. Only a **static-configured** host is exposed — and gpu-1 was
the first static-networked host in the fleet.

**The generalization (operator's framing):** internal DNS is *a cornerstone of
the homelab's network isolation*. Public DNS is intentionally blocked. Any host
that does not have the internal resolvers set **explicitly** is one static-NIC
change (or one lost DHCP lease) away from this outage. Today the whole fleet
silently relies on DHCP-provided DNS. This should be **declarative on every
host**.

## Problem statement

1. No Frank host declares DNS `nameservers` in its Talos machine config — every
   node silently depends on DHCP-provided DNS. A static-networked host gets the
   ACL-blocked public fallback and hangs at boot.
2. `patches/phase04-gpu/404-gpu1-usb-25g-nic.yaml` (and its `.template.yaml`)
   omit nameservers — the concrete trap, and a template that would reproduce it
   for the next static NIC.
3. gpu-1 currently carries **config drift**: a live console/platform-layer edit
   (added during the incident to restore DNS) left **DHCP active** on the USB
   interface, so it holds **two IPv4 addresses** — the intended static
   `192.168.55.31` *and* a floating DHCP `192.168.55.150`. End state must be a
   single declarative source of truth.
4. The failure chain is non-obvious and undocumented — no gotcha captures it.

## Design decisions (from operator Q&A, 2026-07-12)

- **Rollout: STAGED.** Apply to gpu-1 first (the drifted, highest-risk node),
  verify, then the minis, then edge (raspis / pc-1). gpu-1 must not break.
- **Scope: nameservers only.** NTP (`machine.time.servers`) hardening is a
  deliberate separate follow-up, not this PR.
- **gpu-1 .150 drift: fixed in this PR** as a back-loaded manual phase.

## Design

### 1. Cluster-wide nameservers ConfigPatch (the core change)

A single Omni ConfigPatch, labelled for the whole cluster (mirrors the existing
`omni.sidero.dev/cluster: frank` cluster-wide patches such as
`02-cluster-wide-cni-none.yaml`):

```yaml
# patches/phase01-node-config/02-cluster-wide-nameservers.yaml
metadata:
    namespace: default
    type: ConfigPatches.omni.sidero.dev
    id: 102-cluster-nameservers
    labels:
        omni.sidero.dev/cluster: frank
spec:
    data: |
        machine:
            network:
                nameservers:
                    - 192.168.10.11
                    - 192.168.10.12
```

- **Applies to all 7 hosts** (cluster label, no per-machine label).
- `machine.network.nameservers` is a machine-level list that **merges
  independently** of any per-node interface config (e.g., gpu-1's 404 patch) —
  Omni composes patches, so nameservers from this patch + interfaces from 404
  coexist.
- For DHCP hosts (minis/raspis/pc-1) the values **equal what DHCP already
  serves**, so no behavioural change — it just makes the dependency explicit and
  declarative (the config layer wins over DHCP-provided DNS going forward, which
  is the intent).
- **Single source of truth:** the gpu-1 404 patch is **not** given its own
  nameservers; it relies on this cluster-wide patch. Its comments are updated to
  say so (see §2), so the next static NIC doesn't reintroduce the trap.

### 2. Fix the gpu-1 404 patch + template (documentation, not behaviour)

`404-gpu1-usb-25g-nic.yaml` and `.template.yaml` keep `dhcp: false` + static
`.31`, but gain a comment block: **"DNS nameservers are provided cluster-wide by
`102-cluster-nameservers` — a static interface (`dhcp: false`) has NO DNS
of its own and falls back to ACL-blocked public resolvers, so that cluster-wide
patch MUST be applied. Never ship a static-NIC patch without it."** The template
is the durable teaching surface for the next static NIC.

### 3. Regression guard test

`scripts/tests/test_cluster_wide_nameservers.py` (mirrors the existing
`scripts/tests/test_crowdsec_*.py` guards — pure-Python, no cluster access):

- Asserts `102-cluster-nameservers` patch exists, is cluster-labelled, and
  lists **both** `192.168.10.11` and `192.168.10.12` under
  `machine.network.nameservers`.
- **Regression guard:** scans `patches/**` for any patch declaring a static
  interface (`dhcp: false` with `addresses:`); the test passes only while the
  cluster-wide nameservers patch is present — encoding "a static NIC without
  guaranteed internal DNS is the bug." (Guards the class, not just gpu-1.)

### 4. Documentation

- **`agents/rules/frank-gotchas.md`** — one-liner under Networking (and/or the
  gpu-1 section) pointing at the full prose.
- **`docs/runbooks/frank-gotchas/networking.md`** (primary — it's a fleet-wide
  DNS/isolation gotcha) and a cross-ref in **`gpu-1.md`** — full prose: the
  static-NIC-no-nameservers → public-DNS-fallback → NTP → time-sync-gate →
  boot-hang chain, the "pinging but dead" signature, and the fix.

### 5. Manual operations (back-loaded, operator-run post-merge)

Declarative-only principle: Talos config is applied via `omnictl` by the
operator (as in `scripts/rename-nodes.sh`), never CI. Two `# manual-operation`
blocks, staged:

- **`net-apply-cluster-nameservers`** — staged `omnictl apply -f` of the
  cluster-wide patch, verifying per group (gpu-1 → minis → edge) that
  `talosctl -n <ip> get resolvers` shows the resolvers **and the node stays
  Ready** before proceeding.
- **`net-gpu1-clear-dhcp-drift`** — AFTER the nameservers patch is applied and
  gpu-1 verified: revert gpu-1's console/platform network override so the
  machine-config `dhcp: false` is authoritative; verify
  `talosctl -n 192.168.55.31 get addresses` shows a **single** `.31` on
  `enp0s20f0u7` (no `.150`) and resolvers are intact. **Order matters** —
  reverting before the config-layer DNS is in place would re-break gpu-1.

Synced into `docs/runbooks/manual-operations.yaml` via `/sync-runbook`.

## Test Plan (post-merge, operator-driven)

Staged, with a checkpoint after each group:

1. `omnictl apply -f patches/phase01-node-config/02-cluster-wide-nameservers.yaml`
2. **gpu-1 first:** `talosctl -n 192.168.55.31 get resolvers` shows
   `["192.168.10.11","192.168.10.12"]` from the config layer; `kubectl get node
   gpu-1` stays `Ready`.
3. **gpu-1 drift cleanup:** revert the console/platform network override;
   confirm `talosctl -n 192.168.55.31 get addresses` shows a single
   `192.168.55.31/24` on `enp0s20f0u7` (no `.150`); resolvers still correct;
   node still `Ready`.
4. **minis:** `talosctl -n 192.168.55.2{1,2,3} get resolvers` reflect the
   config-layer nameservers; all `Ready`.
5. **edge:** same for `192.168.55.{41,42,71}`.
6. Regression: `python -m pytest scripts/tests/test_cluster_wide_nameservers.py`
   green in CI.

## Acceptance criteria (business-level)

1. Every Frank host has the internal DNS resolvers set **declaratively** in its
   Talos machine config (not solely via DHCP).
2. A static-networked Frank host (e.g., gpu-1 on its USB adapter) resolves DNS
   via the internal resolvers and boots cleanly — no public-DNS fallback.
3. gpu-1 presents a **single** declarative IPv4 address on its USB adapter (no
   DHCP-drift `.150`).
4. The failure mode is guarded against regression (a static-NIC patch cannot
   silently omit internal DNS) and documented.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-07-12--net--declarative-nameservers | `derio-net/frank` | `2026-07-12--net--declarative-nameservers` | — |

## Rollback

Cluster-wide patch is additive and idempotent. To roll back:
`omnictl delete configpatch 102-cluster-nameservers` → hosts revert to
DHCP-provided DNS (minis/raspis/pc-1 unaffected; static hosts regain the latent
exposure). The 404-patch/template edits are comment-only. The `.150` cleanup is
not auto-reversible but is a strict improvement.

## Out of scope / follow-ups

- **NTP hardening** (`machine.time.servers` → internal source) — same isolation
  logic, deliberately deferred (Q&A).
- **Hop cluster** — separate standalone-talosctl cluster on Hetzner (DHCP);
  not Omni-managed, out of scope here.
