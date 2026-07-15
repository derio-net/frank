---
title: "Operating on Storage & Backups"
series: ["operating"]
layer: stor
date: 2026-03-13
draft: false
tags: ["operations", "longhorn", "storage", "backup", "r2", "troubleshooting"]
summary: "Day-to-day commands for managing Longhorn volumes, checking backup health, restoring from Cloudflare R2, and debugging common storage failures on Frank."
weight: 3
reader_goal: "Check Longhorn volume health, manage R2 backups, expand a volume, restore from backup, and debug degraded volumes, failed backups, or stuck attachments — without relying on the Longhorn UI."
diataxis: [how-to, reference]
last_updated: 2026-07-15
last_updated_commit: https://github.com/derio-net/frank/commit/a8bed9a1d358b7ad87bb6dcaa9b0162e5fb0e127
---

{{< last-updated >}}

This is the operational runbook for Longhorn storage and Cloudflare R2 backups on Frank. For the full story on how storage was set up, see [Persistent Storage with Longhorn]({{< relref "/docs/building/03-storage" >}}). For the backup architecture and the Longhorn 1.11 gotchas that shaped the current design, see [Backup — Longhorn to Cloudflare R2]({{< relref "/docs/building/08-backup" >}}).

Source your environment before running any commands:

```bash
source .env   # sets KUBECONFIG
```

## Overview

Frank runs Longhorn for distributed block storage. The default StorageClass replicates every volume three times across the control-plane nodes (`apps/longhorn/values.yaml:3`, `defaultReplicaCount: 3`). Two additional StorageClasses exist:

- **`longhorn-gpu-local`** — single-replica, strict-local (`dataLocality: strict-local`), pinned to gpu-1's dedicated SSDs via `diskSelector: gpu-local` (`apps/longhorn/manifests/gpu-local-sc.yaml`)
- **`longhorn-cicd`** — single-replica, best-effort, for CI/CD workloads on pc-1 (`apps/longhorn/manifests/storageclass-longhorn-cicd.yaml`)

Raspberry Pi nodes have scheduling disabled — Longhorn does not place replicas on them.

All volumes in the `default` group are backed up to a Cloudflare R2 bucket on two schedules:

- **Daily** at 02:00 UTC — 7 recovery points retained (`apps/longhorn/manifests/recurring-job-daily.yaml`)
- **Weekly** on Sunday at 03:00 UTC — 4 recovery points retained (`apps/longhorn/manifests/recurring-job-weekly.yaml`)

Both RecurringJobs target the R2 BackupTarget (`apps/longhorn/manifests/backup-target-default.yaml`, URL `s3://frank-longhorn-backups@auto/`). NFS backup target is disabled pending a Longhorn bug fix in v1.13 (`apps/longhorn/manifests/backup-target-nas.yaml`, entirely commented out).

### Verify

```bash
# All volumes healthy, no degraded/faulted entries
kubectl get volumes.longhorn.io -n longhorn-system

# Backup target reachable
kubectl get backuptargets.longhorn.io -n longhorn-system -o wide
```

Healthy output for volumes shows all `ROBUSTNESS: healthy`. For backup targets, `AVAILABLE` must be `true`.

## Observing State

### Volume Health

```bash
kubectl get volumes.longhorn.io -n longhorn-system
```

A healthy volume shows `State: attached` (if in use) or `detached` (if idle), with `Robustness: healthy`. Anything showing `degraded` or `faulted` needs attention.

```console
$ kubectl get volumes.longhorn.io -n longhorn-system
NAME                                       DATA ENGINE   STATE      ROBUSTNESS   SCHEDULED   SIZE           NODE      AGE
pvc-0ea5fae9-9f12-488e-83e8-a69e4b533b50   v1            attached   healthy                  32212254720    gpu-1     42d
pvc-1211b9cd-8062-43ca-8fa9-93ec43c36c35   v1            attached   healthy                  1073741824     mini-2    8d
# ... (truncated — 20 volumes, all healthy)
```

For more detail on a specific volume:

```bash
kubectl get volume.longhorn.io <volume-name> -n longhorn-system -o yaml
# or
kubectl describe volume.longhorn.io <volume-name> -n longhorn-system
```

### Longhorn UI

The dashboard at `http://192.168.55.201` gives a visual overview of volume health, replica distribution, node capacity, and backup status.

{{< screenshot src="longhorn-ui-volumes.png" caption="Longhorn UI Volume page: replica distribution and robustness at a glance" >}}

### Backup Jobs

Check the RecurringJob schedule and retention:

```bash
kubectl get recurringjobs.longhorn.io -n longhorn-system
```

Check the backup target status:

```bash
kubectl get backuptargets.longhorn.io -n longhorn-system
```

Expected output:
```
NAME      URL                              CREDENTIAL        AVAILABLE   LASTSYNCEDAT
default   s3://frank-longhorn-backups@auto/   longhorn-r2-secret   true        2026-07-15T02:00:00Z
```

List recent backups for a specific volume:

```bash
kubectl get backups.longhorn.io -n longhorn-system \
  -l longhornvolume=<volume-name> \
  --sort-by=.metadata.creationTimestamp
```

### Node and Disk Status

```bash
kubectl get nodes.longhorn.io -n longhorn-system -o wide
```

This shows per-node scheduling state and disk capacity. Both Raspberry Pi nodes should show `ALLOWSCHEDULING: false`.

## Routine Operations

### Expand a Volume

Longhorn supports online volume expansion. Edit the PVC:

```bash
kubectl patch pvc <pvc-name> -n <namespace> \
  -p '{"spec":{"resources":{"requests":{"storage":"20Gi"}}}}'
```

The underlying Longhorn volume and filesystem expand automatically. No pod restart needed for ext4. For XFS, run inside the pod:

```bash
xfs_growfs /
```

### Trigger a Manual Backup

Before maintenance, take an immediate backup outside the scheduled window:

```bash
kubectl create -f - <<EOF
apiVersion: longhorn.io/v1beta2
kind: Backup
metadata:
  generateName: manual-backup-
  namespace: longhorn-system
  labels:
    longhornvolume: <volume-name>
spec:
  snapshotName: ""
EOF
```

Leaving `snapshotName` empty tells Longhorn to take a fresh snapshot and back it up. Track progress in the Longhorn UI under **Backup**.

### Restore a Volume from Backup

Via the Longhorn UI:

1. Open `http://192.168.55.201` → **Backup**
2. Find the volume, select a recovery point (daily or weekly)
3. Click **Restore** — choose replica count and target StorageClass
4. Longhorn creates a new volume

Via CLI, create a new volume referencing the backup URL:

```bash
kubectl create -f - <<EOF
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: restored-<volume-name>
  namespace: longhorn-system
spec:
  fromBackup: "s3://frank-longhorn-backups@auto/?backup=<backup-name>&volume=<volume-name>"
  numberOfReplicas: 3
  dataLocality: best-effort
EOF
```

Then create a PV and PVC pointing to the restored volume, or use the Longhorn UI to create the PVC automatically.

### Manage Snapshots

```bash
# List snapshots for a volume
kubectl get snapshots.longhorn.io -n longhorn-system \
  -l longhornvolume=<volume-name>

# Delete old snapshots (Longhorn retains per RecurringJob retain count)
kubectl delete snapshot.longhorn.io <snapshot-name> -n longhorn-system
```

### Verify R2 Backup Credentials

If backups start failing:

```bash
kubectl get secret longhorn-r2-secret -n longhorn-system
kubectl get backuptargets.longhorn.io -n longhorn-system
```

If `AVAILABLE` is `false`, the R2 credentials may be missing or invalid. Re-apply from the encrypted source:

```bash
sops --decrypt secrets/longhorn/r2-secret.yaml | kubectl apply -f -
```

## Runbook

### Volume Degraded

A degraded volume has fewer healthy replicas than requested.

```bash
# Check which replicas are unhealthy
kubectl get replicas.longhorn.io -n longhorn-system \
  -l longhornvolume=<volume-name>

# Check node status — is a node offline?
kubectl get nodes
kubectl get nodes.longhorn.io -n longhorn-system
```

If a node is temporarily down (reboot, maintenance), Longhorn rebuilds the replica when the node returns. If a node is permanently gone, `nodeDownPodDeletionPolicy: delete-both-statefulset-and-deployment-pod` triggers auto-rebuild.

Force-rebuild a replica on a different node by deleting the failed replica:

```bash
kubectl delete replica.longhorn.io <replica-name> -n longhorn-system
```

Longhorn schedules a new replica on a healthy node automatically.

#### Recovery: IM memory wedge

If a node goes `NotReady` with memory pressure (Layer 1 alert `layer-1-node-memory-headroom` below 1 GiB), the Longhorn instance manager may have leaked memory. Known in v1.11.0 (`~0.9 GiB/day`) — fixed in v1.11.1+. The recovery is a power-cycle (`docs/investigations/2026-06-04--stor--raspi-1-memory-wedge-incident.md`).

```bash
# Confirm no volumes are degraded first
kubectl get volumes.longhorn.io -n longhorn-system | grep -v healthy

# If all healthy, reboot the affected node
talosctl reboot --nodes <node-ip>
```

Do **not** force-delete VolumeAttachments — scale the workload to 0 and let natural detach happen. A force-delete mid-write can blow up ext4 journals.

### Backup Failed

Check the backup target availability first:

```bash
kubectl get backuptargets.longhorn.io -n longhorn-system -o yaml
```

Look at `status.conditions` — common failures:

- **Credential error**: R2 secret missing or wrong. Verify with `kubectl get secret longhorn-r2-secret -n longhorn-system -o yaml` and check that `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_ENDPOINTS` are present.
- **Network error**: Check DNS resolution and outbound HTTPS connectivity from a Longhorn pod.
- **Bucket not found**: Verify the bucket name matches `backupTargetURL`.

Check the Longhorn manager logs:

```bash
kubectl logs -n longhorn-system -l app=longhorn-manager --tail=50 | grep -i backup
```

#### Recovery: stale backups (Grafana alert)

The Layer 9 alert `layer-9-backup-stale` fires when `daily-nas` goes >48h or `weekly-r2` >10d without success. To diagnose:

```bash
kubectl -n longhorn-system get jobs --sort-by=.status.startTime | tail -5
```

If the CronJob is healthy but individual backups fail, the BackupTarget may have drifted — check ArgoCD sync status on the `longhorn-extras` Application.

### Volume Stuck Attaching

A volume stuck in `attaching` state usually means iSCSI issues:

```bash
# Check the volume attachment status
kubectl describe volume.longhorn.io <volume-name> -n longhorn-system

# Check the engine status
kubectl get engines.longhorn.io -n longhorn-system \
  -l longhornvolume=<volume-name> -o yaml

# Verify iSCSI is running on the target node
talosctl -n <node-ip> services | grep iscsid

# If iscsid is missing, check extensions
talosctl -n <node-ip> get extensions
```

If iSCSI is not running, the `iscsi-tools` Talos extension may have been lost during an upgrade.

#### Recovery: force-detach

As a last resort:

```bash
kubectl patch volume.longhorn.io <volume-name> -n longhorn-system \
  --type merge -p '{"spec":{"nodeID":""}}'
```

This clears the node assignment and lets Longhorn re-attach the volume when the consuming pod is rescheduled. Do not force-delete the VolumeAttachment object — scale the workload to 0 and let the natural detach complete.

## Missteps

| What we assumed | Why it was wrong | What it cost |
|-----------------|------------------|-------------|
| Both daily and weekly backups can use separate targets (NFS + R2) | Longhorn `v1beta2` RecurringJob CRD has no `backupTargetName` field — only `concurrency, cron, groups, labels, name, parameters, retain, task` (#11392 closed without fix) | Both jobs route to single R2 target. NFS BackupTarget exists in the repo but is commented out (`apps/longhorn/manifests/backup-target-nas.yaml`). |
| NFS backup target works | Longhorn 1.11 generates `host/path` instead of `host:/path` for NFS (bug #11412) | NFS target disabled until v1.13 fix. |
| ArgoCD can manage the R2 backup secret through SSA | SOPS `.sops` metadata fields are rejected by ArgoCD's server-side apply — Secret goes OutOfSync immediately | R2 secret lives outside the manifests path, applied out-of-band via `sops --decrypt \| kubectl apply -f -` (`docs/runbooks/frank-gotchas/storage-secrets-ssa.md`). |
| Longhorn v1.11.0 is stable | Instance Manager anonymous heap leaks ~0.9 GiB/day (`docs/investigations/2026-06-04--stor--raspi-1-memory-wedge-incident.md`) | raspi-1 wedged at 8 GiB RAM — power-cycle recovery. Pinned to v1.11.2. |
| Volume health alerting is automatic | No ServiceMonitor scrapes Longhorn metrics — `longhorn_volume_robustness` is not surfaced | Fallback is `kube_pod_status_ready` on longhorn-manager pods. Alert rule exists but covers only pod liveness. |

## Quick Reference

| Task | Command |
|------|---------|
| List volumes | `kubectl get volumes.longhorn.io -n longhorn-system` |
| Volume detail | `kubectl describe volume.longhorn.io <name> -n longhorn-system` |
| List replicas | `kubectl get replicas.longhorn.io -n longhorn-system -l longhornvolume=<name>` |
| List backups | `kubectl get backups.longhorn.io -n longhorn-system` |
| Backup target status | `kubectl get backuptargets.longhorn.io -n longhorn-system` |
| Recurring jobs | `kubectl get recurringjobs.longhorn.io -n longhorn-system` |
| List snapshots | `kubectl get snapshots.longhorn.io -n longhorn-system -l longhornvolume=<name>` |
| Expand PVC | `kubectl patch pvc <name> -n <ns> -p '{"spec":{"resources":{"requests":{"storage":"<size>"}}}}'` |
| Re-apply R2 secret | `sops --decrypt secrets/longhorn/r2-secret.yaml \| kubectl apply -f -` |
| Longhorn manager logs | `kubectl logs -n longhorn-system -l app=longhorn-manager --tail=50` |
| Node disk capacity | `kubectl get nodes.longhorn.io -n longhorn-system -o wide` |
| Check Longhorn StorageClasses | `kubectl get storageclass \| grep longhorn` |
| Trigger manual backup | `kubectl create -f manual-backup.yaml` (see Routine Operations) |
| Restore from backup (CLI) | `kubectl create -f restored-volume.yaml` (see Routine Operations) |
| Force-detach stuck volume | `kubectl patch volume.longhorn.io <name> -n longhorn-system --type merge -p '{"spec":{"nodeID":""}}'` |
| Longhorn UI | `http://192.168.55.201` |

## Explanation

This post covers the Longhorn operations that keep Frank's data alive — volume health checks, backup management, and recovery from the failures that have actually bitten us (IM memory wedges, stuck attachments, stale backups). The building companion posts cover *why* we chose Longhorn and this backup architecture; this post is what you reach for when a volume degrades or a backup alert fires.

The design intention was for daily backups to go to NFS and weekly to R2, but Longhorn 1.11's NFS bug and the absent `backupTargetName` CRD field forced both onto R2. The NFS BackupTarget manifest is preserved commented out in the repo (`apps/longhorn/manifests/backup-target-nas.yaml`) for when the fix lands.

## References

- [Longhorn Documentation](https://longhorn.io/docs/1.8.1/) — official docs including snapshot, backup, and restore guides
- [Cloudflare R2 Documentation](https://developers.cloudflare.com/r2/) — bucket management, API tokens, S3 compatibility
- [Building: Persistent Storage with Longhorn]({{< relref "/docs/building/03-storage" >}}) — how storage was set up on Frank
- [Building: Backup — Longhorn to R2]({{< relref "/docs/building/08-backup" >}}) — backup architecture and Longhorn 1.11 gotchas
- [Frank Gotchas — Storage/Secrets](https://github.com/derio-net/frank/blob/main/docs/runbooks/frank-gotchas/storage-secrets-ssa.md) — IM leak, SSA/SOPS gotchas
- [Incident: raspi-1 Memory Wedge](https://github.com/derio-net/frank/blob/main/docs/investigations/2026-06-04--stor--raspi-1-memory-wedge-incident.md) — IM leak forensics and recovery
