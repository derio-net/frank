# 2026-06-04 — raspi-1 Memory-Thrash Wedge (5-Layer Alert Storm)

**Status:** Resolved (power-cycle) + durable fixes applied
**Layers alerted:** L3 (Cilium Agent Down), L4 (Longhorn Manager NotReady), L5 (GPU Operator NotReady), L8 (Observability Degraded), L24 (Traefik Ingress Down)
**Root cause:** Chronic memory over-commitment on raspi-1 (4 GB RPi 4) — Longhorn instance-manager working set ~4.2 GB; node ran at ~355 MB available for months, then tipped into kernel reclaim-thrash.

## What happened

All five alerts traced to **one node**. raspi-1 hosted the DaemonSet pods for
each alerting layer (cilium → L3, longhorn-manager → L4, gpu-operator NFD
worker → L5, fluent-bit + node-exporter → L8) **plus the Traefik pod itself**
(pinned to `tier=low-power, zone=edge` with its 128Mi ACME PVC → L24). When the
node wedged, every layer's "pod down / target down" rule fired at once.

## Timeline (UTC)

| Time | Event |
|------|-------|
| (months) | raspi-1 steady at ~355 MB MemAvailable (9.4% of 3.78 GB). node-exporter ×3179 restarts, cilium ×2052, NFD ×1893 — chronic pressure, never alerted |
| 12:00–16:40 | Longhorn instance-manager working set flat at ~4.18 GB, creeping +3 MB/h (4176→4190 MB) |
| 16:42–16:43 | Kubelet `/healthz` starts timing out (`context deadline exceeded`). No OOM kill — kernel reclaim-thrash instead (working set was "reclaimable" active page cache that Longhorn kept re-touching) |
| 16:45:30 | Last node-exporter scrape: 281 MB and falling |
| 16:46:31 | Node controller marks raspi-1 `NotReady` (NodeStatusUnknown) |
| 16:47+ | Longhorn iSCSI sessions time out (`connection3:0 ping timeout`); `sda` (Traefik's 128Mi volume, iSCSI-attached) throws `critical medium error` — *symptom*, not cause |
| ~17:05 | Triage: node pings, Talos API alive, CRI/kubelet wedged. `talosctl stats` returns only system containers |
| 17:15 | `talosctl reboot` issued — sequence wedges in `cleanup/stopAllPods` (graceful teardown needs the wedged CRI; D-state I/O unbreakable from API) |
| 17:32 | Physical power-cycle (only lever stronger than the API) |
| 17:34:35 | Node `Ready`, all pods recover, 2.68 GB available |

## Root-cause anatomy

> **Corrected (same evening, cluster-wide forensics):** the original
> page-cache theory below was wrong. The instance-manager memory is
> **anonymous Go heap** leaked by an upstream Longhorn v1.11.0 regression —
> proxy connection leaks in the new IM Proxy service APIs
> ([longhorn#12575](https://github.com/longhorn/longhorn/issues/12575), dupes
> #12573/#12643/#12668; **fixed in v1.11.1**). See "Evening follow-up" below.

- raspi-1's instance-manager "4.2 GB working set" was double-counted cadvisor
  series (two series under the kubelet job — use `max`, not `sum`); real value
  ~2.1 GiB — still >55% of the Pi's RAM, all anonymous heap (`talosctl memory`
  showed only 159 MB cache).
- Anonymous memory can't be reclaimed without swap (Talos runs none). The
  kernel thrashed the *remaining sliver* of file cache instead of OOM-killing
  the leaking giant — **no OOM kill, everything stalls**. This is why the node
  died silently instead of recovering via the OOM killer.
- Graceful `talosctl reboot` cannot recover this state: `stopAllPods` talks to
  the wedged CRI and D-state processes ignore SIGKILL. **Go straight to power.**
  Power-cut is safe: Talos OS partitions are immutable, EPHEMERAL is journaled,
  Longhorn replicas (3×) had already failed over.

## Durable fixes

1. **`layer-1-node-memory-headroom` alert** (`apps/grafana-alerting/manifests/alert-rules-cm.yaml`):
   `node_memory_MemAvailable_bytes < 1 GiB` for 30m → warning. Absolute floor,
   NOT a ratio — mini-1 sits at 6.3% of 64 GB (~4 GB, healthy) while raspi-1's
   fatal steady state was 9.4% of 4 GB (355 MB). A ratio rule false-positives on
   big nodes and under-warns on small ones.
2. **Longhorn replica scheduling disabled on Pis** (manual op below). At incident
   time the Pis held 0 of 93 replicas (raspi-1's failed over during the
   incident); this formalizes it so replicas never return to 28 Gi SD cards.
   Volume **attachment** (Traefik's engine on the edge zone) remains allowed —
   a single 128Mi volume engine is a modest footprint; it's replica data
   serving that balloons the instance-manager page cache.
3. **Traefik PVC decision:** keep. The PVC is the ACME cert store (Cloudflare
   DNS challenge) and is genuinely needed; with replicas banned from the Pis,
   the remaining engine-only footprint is acceptable. Revisit only if the
   headroom alert fires on raspi-2 (where Traefik now runs).

## Evening follow-up — cluster-wide leak audit (the real root cause)

Prompted by "mini-1 only has ~4 GB free", a cluster-wide sweep found the same
pathology everywhere, scaling with IM pod age:

| Node | IM pod age | IM working set (max, dedup) | Node MemAvailable |
|------|-----------|------------------------------|-------------------|
| gpu-1 | 74d (Mar 22) | 72.5 GiB / 128 | 39.8 GiB |
| mini-1 | 74d (Mar 22) | 48.3 GiB / 64 | **3.3 GiB** |
| mini-3 | 9d | 11.5 GiB | 40.3 GiB |
| pc-1 | 28d | 10.2 GiB | 18.0 GiB |
| mini-2 | 4d | 6.0 GiB | 46.0 GiB |
| raspi-2 | 10d | 0.2 GiB | 1.4 GiB |

- mini-1 IM trend: 35.4 → 47.5 GiB over 14 days, perfectly linear ≈ **0.9 GiB/day**
  → projected wedge in ~3–4 days at audit time (and it's an etcd member).
- Kernel breakdown on mini-1: `AnonPages` 55.6 GiB vs `Cached` 2.7 GiB —
  anonymous heap, not page cache. Matches upstream issue reports ("Go runtime
  heap, anonymous private dirty").
- Leak is NOT proportional to replica count (mini-2: 22 replicas / 6 GiB;
  mini-1: 18 replicas / 48 GiB) — it tracks engine/proxy activity × pod age.
- Cluster CPU is idle (≤10% util, load/core ≤0.2) and declared memory requests
  are 4–23% of allocatable — the cluster is NOT over-scheduled; this is one
  leaking component.

**Upstream:** Longhorn v1.11.0 IM Proxy service API regression — proxy
connection leaks ([longhorn#12575](https://github.com/longhorn/longhorn/issues/12575);
dupes #12573, #12643, #12668). **Fixed in v1.11.1**; latest 1.11.x chart is
**1.11.2**.

**Remediation — EXECUTED same night (2026-06-04 21:00 → 2026-06-05 00:20):**

Outcome: every node now runs a single v1.11.2 IM; old engine image gone
(refcount 169 → 0 → image removed). mini-1: 3.3 → **51.8 GB** available;
gpu-1: 39.8 → **116.5 GB**. All 27 attached volumes stayed `healthy`
end-to-end; total workload downtime was per-app pod cycles (~1 min each).

What the plan got right and wrong (full lessons in
`docs/runbooks/frank-gotchas/storage-secrets-ssa.md`):

1. Chart bump (#467) + per-volume `spec.image` live upgrade: worked exactly
   as designed — 27/27 live-upgraded with zero interruption, replicas moved
   to the new IMs immediately.
2. **Wrong assumption:** engines do NOT move on plain pod restart, and new
   engines started on a node JOIN the old IM while it exists. Plain
   `rollout restart` of all 24 volume-owning workloads retired nothing.
3. **The actual retirement procedure** (now the canonical recipe —
   `/tmp`-era scripts immortalized as the steps below):
   a. Suspend **root** app selfHeal FIRST (root re-templates leaf specs and
      reverts leaf-level patches — argocd gotcha), then suspend the involved
      leaf apps with `"syncPolicy":{"automated":null}` (selfHeal:false alone
      proved insufficient), and pause operator owners (awx-operator,
      victoria-metrics-operator) whose Deployments are themselves
      Argo-healed.
   b. Scale the old-IM-engine workloads to 0 **simultaneously per node**;
      verify no resurrection after 30 s.
   c. Wait for **natural** volume detach (seconds once nothing recreates
      pods). NEVER force-delete `VolumeAttachment` objects — doing that
      yanked mounted ext4 journals mid-write (`JBD2: I/O error`,
      `EXT4-fs: shut down`) and crash-looped ruflo until a clean
      reattach fsck'd the volumes.
   d. Old IM culls itself at 0 instances (delete its pod if the CR lingers
      empty); scale workloads back; restore root selfHeal + one root sync
      (re-templates all suspended leaves back to git truth).
4. GPU note: ollama/comfyui "parking" is just replica counts (gpu-switcher
   arbitrates the same field) — cycling ollama is safe while comfyui is at 0.
5. Measurement trap that cost an hour: `talosctl memory` row starts with
   NODE, so AVAILABLE is `$8`, not `$7` ($7 is CACHE).

```yaml
# manual-operation
id: stor-longhorn-disable-pi-replica-scheduling
layer: stor
app: longhorn
plan: docs/investigations/2026-06-04--stor--raspi-1-memory-wedge-incident.md
when: After the 2026-06-04 raspi-1 memory-wedge incident; re-apply if a raspi node is ever re-added/replaced
why_manual: nodes.longhorn.io CRs are created and owned by the Longhorn manager, not the Helm chart — replica scheduling intent is stored on the live CR and cannot be expressed declaratively in apps/longhorn
commands: |
  source .env
  kubectl -n longhorn-system patch nodes.longhorn.io raspi-1 --type=merge -p '{"spec":{"allowScheduling":false}}'
  kubectl -n longhorn-system patch nodes.longhorn.io raspi-2 --type=merge -p '{"spec":{"allowScheduling":false}}'
verify: |
  kubectl -n longhorn-system get nodes.longhorn.io
  # raspi-1 and raspi-2 must show ALLOWSCHEDULING=false
  kubectl -n longhorn-system get replicas.longhorn.io -o json | python3 -c "import json,sys,collections; print(collections.Counter(r['spec']['nodeID'] for r in json.load(sys.stdin)['items']))"
  # no replicas on raspi-1/raspi-2
status: applied 2026-06-04
```

## Recovery runbook (this incident class)

```bash
# 1. Identify: node NotReady, pings OK, Talos API OK, kubelet healthz timing out
source .env
kubectl describe node <node> | sed -n '/Conditions:/,/Addresses:/p'
talosctl -n <ip> service kubelet     # HEALTH Fail, context deadline exceeded
talosctl -n <ip> memory              # AVAILABLE near zero
talosctl -n <ip> dmesg | tail -40    # iSCSI timeouts / medium errors = symptoms

# 2. Try graceful (usually wedges in stopAllPods — give it ~5 min max)
talosctl -n <ip> reboot

# 3. Physical power-cycle. Safe: Talos immutable OS + journaled EPHEMERAL;
#    confirm Longhorn volumes healthy first (replicas elsewhere):
kubectl -n longhorn-system get volumes.longhorn.io | grep -v healthy

# 4. Verify after rejoin
kubectl get pods -A -o wide --field-selector spec.nodeName=<node>
kubectl -n longhorn-system get nodes.longhorn.io <node>
talosctl -n <ip> memory
```
