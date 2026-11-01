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

1. Revert the change on a branch and open the PR. The repo squash-merges, so the merged commit
   has ONE parent: use `git revert <sha>`. Only a true merge commit (two parents; check with
   `git show --no-patch --format=%p <sha>`) needs `git revert -m 1 <sha>`. Merge the revert PR.
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

Restore. The volume must be detached, so stop the workload first, and stop ArgoCD from undoing it:

1. Suspend selfHeal, passing the WHOLE `automated` map (`--type=merge` replaces it, and dropping
   `prune: false` leaves drift). If the leaf is re-templated by `root`, suspend ROOT's selfHeal
   first (see `agents/rules/frank-argocd.md`):

   ```sh
   kubectl patch application <app> -n argocd --type=merge \
     -p '{"spec":{"syncPolicy":{"automated":{"prune":false,"selfHeal":false}}}}'
   ```

2. Scale the workload to 0: `kubectl -n <ns> scale deploy/<name> --replicas=0` (a StatefulSet the same way).
   Wait until the volume reports `detached`: `kubectl -n longhorn-system get volumes.longhorn.io $VOL`.
3. In the Longhorn UI (`http://192.168.55.201`): Volume -> `$VOL` -> Attach in maintenance mode
   -> Snapshots and Backups -> choose the snapshot -> Revert -> Detach.
4. Revert the version PR (previous section) and merge it, so git no longer declares the new version.
5. Re-enable selfHeal (the same full map with `"selfHeal":true`, root last) and force a sync with
   explicit options, then scale the workload up if ArgoCD did not:

   ```sh
   kubectl patch application <app> -n argocd --type=merge \
     -p '{"operation":{"sync":{"revision":"HEAD","syncOptions":["ServerSideApply=true","RespectIgnoreDifferences=true"]}}}'
   ```

6. Check the data and that the app is `Synced`, not just `Healthy`.

Deleting the snapshot CR does not free replica space until Longhorn merges the chain. Do not
force-delete a `VolumeAttachment`.

## Frank Talos revert through Omni

Frank is managed by Omni, which reconciles toward its cluster spec. A per-node change is undone;
the version field is the lever. Do NOT use `talosctl rollback` on Frank.

**Precondition 1: the support window.** The target Talos minor must support the Kubernetes minor
that is RUNNING now, per `versions/support-matrix.yaml`. If not, a Talos revert is impossible and
the only path is a forward-fix. Worked example: Talos 1.13 with Kubernetes 1.36 cannot go back to
Talos 1.12, whose window ends at Kubernetes 1.35 (and Kubernetes cannot go back, see below).

**Precondition 2: Omni must accept a downgrade.** UNVERIFIED: whether Omni v1.5 permits setting a
Talos version lower than the running one (its UI normally offers upgrades only, and Talos itself
documents downgrades as best-effort). Try it on the version field below; if Omni refuses, stop and
forward-fix (move to the next Talos patch that fixes the problem). Do not work around a refusal
with `talosctl` against a node.

**Precondition 3: cluster health.**

- No node holds a sole replica of an attached Longhorn volume (a node holding the last replica
  cannot drain): list single-replica volumes with
  `kubectl -n longhorn-system get volumes.longhorn.io -o json | jq -r '.items[] | select(.spec.numberOfReplicas==1) | "\(.metadata.name) \(.status.state) \(.status.currentNodeID)"'`
  and for every `attached` row confirm the workload can stop or accept the drain delay (pc-1 holds several).
- etcd is healthy: `talosctl etcd status` shows every member, one leader, no errors; every node `Ready`.
- Take an etcd snapshot first: `talosctl etcd snapshot ./etcd-pre-rollback.db`.

Procedure:

1. Revert the declared version: a PR putting the previous Talos version back in
   `versions/frank.yaml`, merged first (git leads).
2. Change ONLY the cluster's Talos version field in Omni. With `omnictl` (UNVERIFIED on v1.5; the
   resource and field names are from the Omni cluster resource, check the dump first):

   ```sh
   omnictl get cluster frank -o yaml > cluster-frank.yaml   # find spec.talosversion
   # edit spec.talosversion to the previous version (no "v" prefix check: copy the current format)
   omnictl apply -f cluster-frank.yaml
   ```

   Or in the Omni UI: Clusters -> frank -> the Talos version control (UNVERIFIED that it offers a lower version).
   Never apply a cluster template: it would own every ConfigPatch (`patches/phase*`).
3. Omni rolls the nodes back one by one. Watch `omnictl get clustermachinestatuses` until every
   machine is `ready`, and re-run the etcd status check.
4. If a node stays on the newer version, the Omni v1.5 hash race may have bitten: use
   `scripts/omni-legacy-recovery/` (see [`omni-upgrade.md`](omni-upgrade.md), Recovery).
5. `etcd` `extraArgs` changes only take effect on a reboot; a rolled-back node reboots, so
   re-check the etcd listener after the rollback.

## Hop Talos rollback

Hop is a single node, not managed by Omni, so `talosctl` is the tool.

Limits: `talosctl rollback` boots the previous A/B slot only, so it covers just the LAST
`talosctl upgrade` (one step back, no further). It does NOT undo `talosctl upgrade-k8s`:
Kubernetes stays where it is.

**Precondition: the support window.** The previous Talos minor must support the RUNNING
Kubernetes minor per `versions/support-matrix.yaml`; otherwise there is no Talos revert, only a
forward-fix (the Frank example applies: Talos 1.13 + Kubernetes 1.36 cannot return to 1.12).

1. Source `.env_hop` (never `.env`, which points at Frank) and roll back, naming the config
   explicitly:

   ```sh
   source .env_hop
   talosctl --talosconfig clusters/hop/talosconfig/talosconfig --nodes $HOP_IP rollback
   ```

2. Wait for the node `Ready`: `kubectl get nodes`, and `talosctl --talosconfig clusters/hop/talosconfig/talosconfig --nodes $HOP_IP version`
   shows the old version.
3. Revert the declared version: a PR putting the previous Talos version back in `versions/hop.yaml`.
4. Run the Hop smoke checks under `smoke/hop/` (caddy, headscale, blog). Public traffic is down
   for the reboot (`hostPort` + `Recreate`), so announce it.

If the node does not come back, recover from the Hetzner console, not by repeating the rollback.

## Kubernetes is one-way

A Kubernetes minor cannot be rolled back: etcd storage versions and API objects move forward and
Talos has no supported downgrade path for it. The only recovery after a bad Kubernetes minor is forward (fix and
upgrade) or a restore from an etcd snapshot, which loses everything since. So:

- Confirm with the operator before applying a Kubernetes minor step.
- Take an etcd snapshot first (`talosctl etcd snapshot`) and check the removed APIs against the live cluster.
- Never apply two Kubernetes minors in one step; the track (`scripts/life_tracks.py`) enforces it.
- Only a Kubernetes MINOR move is one-way. A Kubernetes PATCH (same minor) is not flagged one-way, but
  its recovery is also a forward-fix in practice.
