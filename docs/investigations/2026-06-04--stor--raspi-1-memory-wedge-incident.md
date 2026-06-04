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

- `container_memory_working_set = usage − inactive_file`. Longhorn replica/engine
  I/O keeps page-cache pages **active**, so the instance-manager's working set
  (4.2 GB) exceeded physical RAM while remaining theoretically reclaimable.
  Under pressure the kernel thrashed reclaiming pages Longhorn immediately
  re-touched — **no OOM kill, everything stalls**. This is why the node died
  silently instead of recovering via the OOM killer.
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
