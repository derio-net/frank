# Rolling back an update

One section per path. Pick the path from what changed; do not improvise across them.
Every update that touches the cluster is declared in git first (a PR), so every rollback
starts by making git say what the cluster should now be.

| Changed | Path |
|---|---|
| Image, chart, manifest, policy | Revert PR |
| Application data (migration ran) | Longhorn snapshot restore |
| Frank Talos | Frank Talos revert through Omni |
| Hop Talos | Hop Talos rollback |
| Kubernetes minor | One-way: there is no rollback |

## Revert PR

For anything ArgoCD applies from `main`:

1. Revert the merge commit: `git revert -m 1 <merge-sha>` on a branch, open the PR, merge it.
2. ArgoCD syncs the revert. `prune: false` is the repo convention, so a revert that DELETES a
   resource removes nothing from the cluster: delete it by hand and assert it is gone.
3. "Synced" is not proof. Compare `status.operationState.operation.sync.revision` against the revert
   SHA and assert on the live artifact (see `frank-gotchas.md`, ArgoCD).
4. A Rollout-backed app: after the sync check `.status.phase` and promote or abort a paused canary.

A revert does not undo data a migration already wrote. If the new version migrated its database,
use the next section as well.

## Longhorn snapshot restore

Sessions snapshot the volume the migration writes to BEFORE requesting the merge (the stateful
brief). A snapshot is in the replica chain, not an off-site backup.

Find the snapshot and the volume:

```sh
VOL=$(kubectl -n <ns> get pvc <pvc> -o jsonpath='{.spec.volumeName}')
kubectl -n longhorn-system get snapshots.longhorn.io -l longhornvolume=$VOL
```

Restore (the volume must be detached, so stop the workload first):

1. Revert the version PR (previous section) and let ArgoCD sync, or suspend the app's selfHeal
   (pass the WHOLE `automated` map, see `frank-argocd.md`).
2. Scale the workload to 0: `kubectl -n <ns> scale deploy/<name> --replicas=0` (a StatefulSet the same way).
   Wait until the volume reports `detached`: `kubectl -n longhorn-system get volumes.longhorn.io $VOL`.
3. In the Longhorn UI (`http://192.168.55.201`): Volume -> `$VOL` -> Attach in maintenance mode
   -> Snapshots and Backups -> choose the snapshot -> Revert -> Detach.
4. Scale the workload back up and check the data.
5. Re-enable selfHeal and force a sync (explicit `syncOptions`), then confirm `Synced`.

Deleting the snapshot CR does not free replica space until Longhorn merges the chain. Do not
force-delete a `VolumeAttachment`.

## Frank Talos revert through Omni

Frank is managed by Omni, which reconciles toward its cluster spec. A per-node change is undone;
the version field is the lever. Do NOT use `talosctl rollback` on Frank.

1. Revert the declared version: a PR putting the previous Talos version back in
   `versions/frank.yaml`, merged first (git leads).
2. In Omni set the cluster's Talos version to the previous one (the cluster's version field only,
   `omnictl` or the UI; never apply a template, which would own every ConfigPatch).
3. Omni rolls the nodes back one at a time. Watch `omnictl get clustermachinestatuses` until every
   machine is `ready`.
4. If a node stays on the newer version, the Omni v1.5 hash race may have bitten: use
   `scripts/omni-legacy-recovery/` (see [`omni-upgrade.md`](omni-upgrade.md), Recovery).
5. `etcd` `extraArgs` changes only take effect on a reboot; a rolled-back node reboots, so
   re-check the etcd listener after the rollback.
6. Longhorn: do not roll more than one node at a time while a node holds the last replica of a volume.

## Hop Talos rollback

Hop is a single node, not managed by Omni, so `talosctl` is the tool.

1. `talosctl rollback --nodes $HOP_IP` boots the previous installed image (the A/B slot). Source
   `.env_hop` first, never `.env`.
2. Wait for the node `Ready`: `kubectl get nodes`, and `talosctl --nodes $HOP_IP version` shows the old version.
3. Revert the declared version: a PR putting the previous Talos version back in `versions/hop.yaml`.
4. Run the Hop smoke checks under `smoke/hop/` (caddy, headscale, blog). Public traffic is down
   for the reboot (`hostPort` + `Recreate`), so announce it.

If the node does not come back, recover from the Hetzner console, not by repeating the rollback.

## Kubernetes is one-way

A Kubernetes minor cannot be rolled back: etcd storage versions and API objects move forward and
Talos has no downgrade path. The only recovery after a bad Kubernetes minor is forward (fix and
upgrade) or a restore from an etcd snapshot, which loses everything since. So:

- Confirm with the operator before applying a Kubernetes minor step.
- Take an etcd snapshot first (`talosctl etcd snapshot`) and check the removed APIs against the live cluster.
- Never apply two Kubernetes minors in one step; the track (`scripts/life_tracks.py`) enforces it.
- A Kubernetes PATCH (same minor) is not one-way, but rollback is still a forward fix in practice.
