# Upgrading Omni (operator runbook)

Omni runs on a separate host (`omni.frank.derio.net`), outside the cluster. **No session ever
reaches the Omni host**, so the upgrade is not automated: you run it by hand from the laptop.
It is tracked as derio-net/willikins#528. The console shows Omni's running version (the
`omni-status` sidecar) against the pinned `OMNI_VERSION`, so an overdue upgrade is visible.

Omni is the control plane for Frank's nodes. Do it when no Talos or Kubernetes step is in flight.

## Backup

On the Omni host (ssh from the laptop):

1. Note the running version: `docker inspect omni --format '{{.Config.Image}}'`.
2. Back up the state the container mounts: the etcd directory (`ETCD_VOLUME_PATH`), the sqlite
   directory (`SQLITE_DB_PATH`) and the encryption key `omni.asc`. Stop nothing; copy to a dated
   directory, then off the host. The key is the one thing that cannot be regenerated.
3. Keep the previous image: `docker image ls ghcr.io/siderolabs/omni`.

## Upgrade

1. On the laptop, in a fr workspace, read the Omni release notes for every release between the
   running version and the target (removed flags, DB migrations). Omni only migrates forward.
2. Edit `omni/omni/omni.env.template`: set BOTH `OMNI_VERSION` and `OMNI_IMG_TAG` to the new tag (a
   test keeps them equal; compose reads `OMNI_IMG_TAG`). PR and merge. The repo copy edits nothing
   on the host.
3. Copy the new value into the host's `.env` (the live file is not in git), then:

   ```sh
   docker compose pull
   docker compose up -d
   ```

   Compose recreates the container on the new tag. Expect the Omni UI to drop for about a minute.
4. Do not combine this with a certificate renewal or a host reboot.

## Verify

1. `docker ps` shows the new image tag; `docker logs omni --tail 50` has no crash loop.
2. From the laptop: `omnictl get machines` and `omnictl get clustermachinestatuses` show every
   machine `ready`. Omni can wedge SILENTLY after a restart: reads keep working while its reconcile
   runtime is dead. Check a functional signal, not the logs: a pending change reconciles.
3. A restart rotates the Talos API certs, so the stored talosconfig loses elevated reads. Refresh it:
   `omnictl talosconfig .talos/Frank_Talos_Config.yaml -c frank -f --merge=false`.
4. The console's Omni card shows the new version.

## Recovery

- Container will not start or the cluster view is empty: `docker logs omni`, then re-pin
  `OMNI_IMG_TAG` to the previous tag and `docker compose up -d`. Restore the backup only if the
  newer version migrated state and the old one refuses it.
- Wedged reconcile (clock jump or after the restart): `docker restart omni`, then refresh the talosconfig.
- Machines that persisted a bad config and never get the rollback (the v1.5 hash race): use
  `scripts/omni-legacy-recovery/` (`force-recovery.sh --dry-run|--apply`, `wait-recovery.sh`,
  `remove-recovery.sh`). See [`frank-gotchas/omni.md`](frank-gotchas/omni.md).
- Certificate: Omni reads `/tls.crt` once at start, so a renewal needs `docker restart omni`.
