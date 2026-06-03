---
title: "Operating on Storage & Backups"
date: 2026-03-13
draft: false
tags: ["operations", "longhorn", "storage", "backup", "r2"]
summary: "Day-to-day commands for managing Longhorn volumes, checking backup health, and restoring from Cloudflare R2."
weight: 102
---

This is the operational runbook for Longhorn storage and Cloudflare R2 backups on Frank, the Talos Cluster. If you want the full story on how storage was set up, see [Persistent Storage with Longhorn]({{< relref "/docs/building/03-storage" >}}). For backup architecture and the Longhorn 1.11 gotchas that shaped the current design, see [Backup — Longhorn to Cloudflare R2]({{< relref "/docs/building/08-backup" >}}).

## Overview

Frank runs Longhorn for distributed block storage. The default StorageClass replicates every volume three times across the control-plane nodes (mini-1, mini-2, mini-3). A second StorageClass, `longhorn-gpu-local`, provides single-replica strict-local storage pinned to gpu-1's dedicated SSDs for AI workloads.

All volumes in the `default` group are backed up to a Cloudflare R2 bucket on two schedules:

- **Daily** at 02:00 UTC — 7 recovery points retained
- **Weekly** on Sunday at 03:00 UTC — 4 recovery points retained

Both RecurringJobs currently target R2 (NFS backup target is disabled pending a Longhorn bug fix in v1.13).

## Observing State

### Volume Health

List all Longhorn volumes and their current state:

```bash
kubectl get volumes.longhorn.io -n longhorn-system
```

A healthy volume shows `State: attached` (if in use) or `State: detached` (if idle), with `Robustness: healthy`. Anything showing `degraded` or `faulted` needs attention — jump to the Debugging section.

```console
$ kubectl get volumes.longhorn.io -n longhorn-system
NAME                                       DATA ENGINE   STATE      ROBUSTNESS   SCHEDULED   SIZE           NODE      AGE
pvc-0ea5fae9-9f12-488e-83e8-a69e4b533b50   v1            attached   healthy                  32212254720    gpu-1     42d
pvc-1211b9cd-8062-43ca-8fa9-93ec43c36c35   v1            attached   healthy                  1073741824     mini-2    8d
pvc-184f9b50-5d7f-400d-865b-4bb587dcf859   v1            attached   healthy                  8589934592     mini-2    39d
pvc-1929c98e-6a59-4eec-8c41-353833f43dec   v1            attached   healthy                  5368709120     mini-2    37d
pvc-1b0925db-fc13-4a8f-99da-2a09265ada47   v1            detached   unknown                  10737418240              35d
pvc-1ded449d-e2bc-4e38-b7c9-c5d5ee264294   v1            attached   healthy                  2147483648     mini-3    37d
pvc-26d07ae3-35c9-406f-b963-01894b9db240   v1            attached   healthy                  21474836480    mini-3    43d
pvc-40c7a93f-5a74-49f0-8dc6-ff900348879a   v1            attached   healthy                  10737418240    gpu-1     21d
pvc-4b1121bb-2285-42ec-8a8d-49cc96978ae1   v1            attached   healthy                  5368709120     mini-1    42d
pvc-61ea0ef7-097a-4362-8727-19db3475a07c   v1            attached   healthy                  53687091200    gpu-1     20d
pvc-64409163-fd82-49d1-bdfd-6a2a97f339c6   v1            attached   healthy                  1073741824     mini-3    43d
pvc-6555d86e-52c3-4d36-9f3d-498053f0525c   v1            attached   healthy                  2147483648     mini-1    42d
pvc-6ff35220-82b3-478e-849d-f3dd9e0f29af   v1            attached   healthy                  1073741824     gpu-1     41d
pvc-82bfe595-d342-41c4-9f68-7346b2317a6d   v1            attached   healthy                  53687091200    pc-1      7d8h
pvc-9cfe443a-e7e9-4894-a169-943b361124a5   v1            attached   healthy                  21474836480    gpu-1     43d
pvc-b17ad456-1c3b-45dc-a6c9-18df39a4dab6   v1            attached   healthy                  134217728      raspi-1   12d
pvc-c1d1b3b5-4e57-4488-a921-40814dac625a   v1            attached   healthy                  10737418240    pc-1      22d
pvc-c700abbe-9114-47b8-ac5b-2f408f6055ec   v1            detached   unknown                  107374182400             36d
pvc-cd8722f8-2077-41d5-86eb-a62c6437dd3f   v1            attached   healthy                  5368709120     mini-3    21d
pvc-de4ab602-205f-41d5-8f13-1d2982109b92   v1            attached   healthy                  5368709120     mini-2    42d
pvc-f083c9f7-8cbe-4cb7-89d0-7455c59a6f50   v1            attached   healthy                  5368709120     mini-3    39d
```

For more detail on a specific volume:

```bash
kubectl get volume.longhorn.io <volume-name> -n longhorn-system -o yaml
```

### Longhorn UI

The dashboard at `http://192.168.55.201` gives you a visual overview of volume health, replica distribution, node capacity, and backup status. It is the fastest way to spot problems.

{{< screenshot src="longhorn-ui-volumes.png" caption="Longhorn UI Volume page: replica distribution and robustness at a glance" >}}

### Backup Jobs

Check the RecurringJob schedule and retention:

```bash
kubectl get recurringjobs.longhorn.io -n longhorn-system
```

Check the backup target status (should show `AVAILABLE: true`):

```bash
kubectl get backuptargets.longhorn.io -n longhorn-system
```

List recent backups for a specific volume:

```bash
kubectl get backups.longhorn.io -n longhorn-system \
  -l longhornvolume=<volume-name> \
  --sort-by=.metadata.creationTimestamp
```

### Node and Disk Status

See how much capacity each node has and whether disks are schedulable:

```bash
kubectl get nodes.longhorn.io -n longhorn-system -o wide
```

## Routine Operations

### Expand a Volume

Longhorn supports online volume expansion. Edit the PVC to request more storage:

```bash
kubectl patch pvc <pvc-name> -n <namespace> \
  -p '{"spec":{"resources":{"requests":{"storage":"20Gi"}}}}'
```

The underlying Longhorn volume and filesystem expand automatically. No pod restart needed for ext4; XFS may need a manual `xfs_growfs` inside the pod.

### Trigger a Manual Backup

If you want an immediate backup outside the scheduled window (before maintenance, for example):

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

Leaving `snapshotName` empty tells Longhorn to take a fresh snapshot and back it up. You can track progress in the Longhorn UI under **Backup**.

### Restore a Volume from Backup

To restore a volume from an R2 backup:

1. Open the Longhorn UI at `http://192.168.55.201`
2. Navigate to **Backup** and find the volume
3. Select the recovery point (daily or weekly) and click **Restore**
4. Choose the number of replicas and target StorageClass
5. Longhorn creates a new volume — create a PVC to bind it

Alternatively, via CLI, create a new volume referencing the backup URL:

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

List snapshots for a volume:

```bash
kubectl get snapshots.longhorn.io -n longhorn-system \
  -l longhornvolume=<volume-name>
```

Delete old snapshots manually (Longhorn retains per the RecurringJob `retain` count, but you can clean up extras):

```bash
kubectl delete snapshot.longhorn.io <snapshot-name> -n longhorn-system
```

### Verify R2 Backup Credentials

If backups start failing, check the secret is present and the backup target reports available:

```bash
kubectl get secret longhorn-r2-secret -n longhorn-system
kubectl get backuptargets.longhorn.io -n longhorn-system
```

If the secret was lost (node rebuild, namespace wipe), re-apply it from the encrypted source:

```bash
sops --decrypt secrets/longhorn/r2-secret.yaml | kubectl apply -f -
```

## Debugging

### Volume Degraded

A degraded volume has fewer healthy replicas than requested. Common causes:

```bash
# Check which replicas are unhealthy
kubectl get replicas.longhorn.io -n longhorn-system \
  -l longhornvolume=<volume-name>

# Check node status — is a node offline?
kubectl get nodes
kubectl get nodes.longhorn.io -n longhorn-system
```

If a node is down temporarily (reboot, maintenance), Longhorn will rebuild the replica when the node returns. If a node is permanently gone, Longhorn auto-rebuilds on remaining nodes once `nodeDownPodDeletionPolicy` kicks in.

Force-rebuild a replica on a different node by deleting the failed replica:

```bash
kubectl delete replica.longhorn.io <replica-name> -n longhorn-system
```

Longhorn schedules a new replica on a healthy node automatically.

### Backup Failed

Check the backup target availability first:

```bash
kubectl get backuptargets.longhorn.io -n longhorn-system -o yaml
```

Look at the `status.conditions` — common failures:

- **Credential error**: R2 secret missing or wrong. Verify with `kubectl get secret longhorn-r2-secret -n longhorn-system -o yaml` and check that `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_ENDPOINTS` are all present.
- **Network error**: Check DNS resolution and outbound HTTPS connectivity from a Longhorn pod.
- **Bucket not found**: Verify the bucket name matches what is in the `backupTargetURL`.

Check the Longhorn manager logs for detailed error messages:

```bash
kubectl logs -n longhorn-system -l app=longhorn-manager --tail=50 | grep -i backup
```

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
```

If iSCSI is not running, the `iscsi-tools` extension may have been lost during an upgrade. Verify extensions on the node:

```bash
talosctl -n <node-ip> get extensions
```

As a last resort, force-detach and re-attach:

```bash
kubectl patch volume.longhorn.io <volume-name> -n longhorn-system \
  --type merge -p '{"spec":{"nodeID":""}}'
```

This clears the node assignment and lets Longhorn re-attach the volume when the consuming pod is rescheduled.

## Quick Reference

| Task | Command |
|------|---------|
| List volumes | `kubectl get volumes.longhorn.io -n longhorn-system` |
| Volume detail | `kubectl get volume.longhorn.io <name> -n longhorn-system -o yaml` |
| List replicas | `kubectl get replicas.longhorn.io -n longhorn-system` |
| List backups | `kubectl get backups.longhorn.io -n longhorn-system` |
| Backup target status | `kubectl get backuptargets.longhorn.io -n longhorn-system` |
| Recurring jobs | `kubectl get recurringjobs.longhorn.io -n longhorn-system` |
| Expand PVC | `kubectl patch pvc <name> -n <ns> -p '{"spec":{"resources":{"requests":{"storage":"<size>"}}}}'` |
| Re-apply R2 secret | `sops --decrypt secrets/longhorn/r2-secret.yaml \| kubectl apply -f -` |
| Longhorn manager logs | `kubectl logs -n longhorn-system -l app=longhorn-manager --tail=50` |
| Node disk capacity | `kubectl get nodes.longhorn.io -n longhorn-system -o wide` |
| Longhorn UI | `http://192.168.55.201` |

## References

- [Longhorn Documentation](https://longhorn.io/docs/1.8.1/) — official docs including snapshot, backup, and restore guides
- [Cloudflare R2 Documentation](https://developers.cloudflare.com/r2/) — bucket management, API tokens, S3 compatibility
- [Building Post: Persistent Storage with Longhorn]({{< relref "/docs/building/03-storage" >}}) — how storage was set up on Frank
- [Building Post: Backup — Longhorn to Cloudflare R2]({{< relref "/docs/building/08-backup" >}}) — backup architecture and Longhorn 1.11 gotchas
