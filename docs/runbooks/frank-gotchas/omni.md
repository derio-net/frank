# Frank Gotchas — Omni

Long-form companion to the **Omni** section in `agents/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

## TLS cert is NOT renewed by the snap-installed certbot timer

Omni's TLS cert for `omni.frank.derio.net` is NOT renewed by the snap-installed `snap.certbot.renew.timer` — the initial `certonly` (per `omni/certbot/certbot.md`) used `--config-dir /opt/manual_install/certbot/config` (etc.), so the renewal config lives at `/opt/manual_install/certbot/config/renewal/omni.frank.derio.net.conf` instead of `/etc/letsencrypt/renewal/`. The snap timer only scans `/etc/letsencrypt/`, so it fires daily as a clean no-op (`certbot certificates` → `No certificates found`) and the cert silently ages to expiry.

### Symptom at expiry

- `kubectl get nodes` returns `oidc discovery error: 500 Internal Server Error`
- `omnictl` returns gRPC `500`
- Browser hits `https://omni.frank.derio.net/` and gets `500 Internal Server Error` with body `tls: failed to verify certificate: x509: certificate has expired or is not yet valid: current time ... is after <notAfter>`

That error comes from **Traefik's outbound TLS verify** rejecting Omni's expired upstream cert on `:8100` (Omni and Traefik are both containers on the omni Pi). Omni's own log shows `http: TLS handshake error from 172.18.0.2:<port>: remote error: tls: bad certificate` for the same exchange (172.18.0.2 is Traefik in the Docker bridge).

### Fix

Run the manual renew + install the dedicated `omni-cert-renew.{service,timer}` unit, both documented in `omni/certbot/certbot.md`. The `--deploy-hook 'docker restart omni'` is mandatory — Omni v1.5.0 reads `/tls.crt` once at process start and has no SIGHUP cert-reload path.

Discovered 2026-05-11 when the cert expired 2026-05-09.

### The renewer itself can silently break (cert ages to expiry with NO alert)

The `omni-cert-renew.{service,timer}` from the fix above is the *only* thing renewing this cert (the snap timer is a no-op for it). So if the **renewer script** breaks, the cert silently ages to expiry and **nothing pages** — the failing unit is invisible until `https://omni.frank.derio.net` starts 500-ing (the symptom above). The cert is a separate object from the unit; a `failed` renewer doesn't surface as a cluster/health alert.

**Seen 2026-06-20:** `/usr/local/sbin/omni-cert-renew.sh` had drifted from the canonical version in `omni/certbot/certbot.md` — it lost the `/snap/bin/certbot renew \` + `--config-dir` + `--work-dir` lines and started mid-command at `--logs-dir`, so the shell ran `--logs-dir …` as a command → `status=127` in **~8 ms, before doing anything**. It had failed daily since at least Jun 12 (the timer fires nightly). Nothing was half-renewed; it just never renewed. Caught with runway (cert valid to Aug 9, renewal window opens ~Jul 10) while investigating the wedge below.

**Detect:**
```bash
ssh frank-omni
systemctl is-failed omni-cert-renew.service           # "failed" = broken renewer
journalctl -u omni-cert-renew.service -n 20            # the actual error (e.g. 127 / command not found)
sudo openssl x509 -enddate -noout -in /opt/manual_install/certbot/config/live/omni.frank.derio.net/cert.pem   # runway
```

**Fix:** restore the canonical script (the full `/snap/bin/certbot renew …` block in `omni/certbot/certbot.md`), then validate + clear the failed state:
```bash
/snap/bin/certbot renew --config-dir /opt/manual_install/certbot/config \
  --work-dir /opt/manual_install/certbot/work --logs-dir /opt/manual_install/certbot/logs --dry-run   # staging, no rate limit
systemctl reset-failed omni-cert-renew.service && systemctl start omni-cert-renew.service             # no-op until the 30-day window → exit 0
```
A clean run logs `Deactivated successfully` / `status=0/SUCCESS`; the dry-run prints `all simulated renewals succeeded`. Worth a periodic eyeball (or a real monitor) on `systemctl is-failed omni-cert-renew.service` — a broken renewer is the kind of thing you only discover at expiry.

## Omni wedges SILENTLY after a cold-boot clock-jump (reconcile death)

After a power outage (whole-infra cold boot), the on-prem `omni` container can come up **running and serving the API but with its reconcile runtime dead** — it accepts desired-state writes and answers reads from cached state, yet performs **zero reconciliation**. Every install-level change queues forever against a runtime that never acts.

### Symptom

- UI and `omnictl` look completely healthy: cluster `Running`, all machines `Running`/`connected`, `configuptodate: true`, no error banners, no taint warnings.
- But a **just-applied** `KernelArgs` / `ExtensionsConfigurations` / Talos-version change **never reboots or reinstalls its machine** — the node's live state never moves toward desired (e.g. `omnictl get kernelargsstatus <id>` stays `CURRENT ARGS: []`).
- `docker logs omni` is **frozen** — `docker logs omni 2>&1 | wc -l` is static over several seconds, and the newest line's timestamp is days/weeks old (often *older* than the container's `StartedAt`, an impossible ordering that confirms the clock chaos).
- The omni process is up (`docker top omni` shows `/omni …`), low CPU, not OOM-killed.

### Cause

The Omni host is a Raspberry Pi with **no battery-backed RTC**. On a cold boot it starts with a stale clock; the `omni` container launches and begins logging/operating against that wrong time. NTP later corrects the clock by a large forward jump (weeks/months). A big monotonic-time discontinuity wedges embedded etcd / raft leases and Go context timers — the controller runtime (`omni_runtime` / `qruntime`) deadlocks and goes quiet, while the gRPC read path keeps serving from cached/sqlite state. `docker logs` can also freeze because the json-file writer's view is stuck behind the jump.

This is why the gpu-1 NIC-flap fix sat un-applied for so long: `#515`'s `ConfigPatch` was the wrong mechanism (see `gpu-1.md`), **and** even the correct `KernelArgs` resource (#582) only reconciled *after* the runtime was revived.

### Recovery

```bash
ssh frank-omni
docker restart omni        # clock is NTP-synced now → clean re-init, reconciles the whole backlog
```

Confirm the runtime is alive again by the **functional** signal, not the logs (which may stay stale post-restart — a json-file attach quirk): re-check from the workstation that a pending change now reconciles, e.g. `omnictl get kernelargsstatus <machine-id>` shows `CURRENT ARGS` flipping to the desired value, and the target machine performs its reboot/upgrade.

Two side effects of the restart:
- It **rotates the Talos API certs**, so the stored talosconfig loses elevated reads (`talosctl read …` → `PermissionDenied`). Refresh it: `omnictl talosconfig .talos/Frank_Talos_Config.yaml -c frank -f --merge=false` (or download from the Omni UI). Reads route through the Omni proxy afterward — restores reads/dmesg/exec, but `talosctl upgrade` stays proxy-refused by design.
- Omni works through a **backlog** of un-reconciled desired-state — watch the first minutes for any *unexpected* machine reboots beyond the one you intended.

### Durable fix (Omni host, not this repo)

The `omni/` dir in this repo is a **copy** of the live Pi config — editing it does nothing to the running host. NOTE the omni container is **not** managed by a systemd unit (there is no compose unit to hang an ordering drop-in off): it autostarts purely via Docker's `restart: unless-stopped` policy, and `docker.service` is ordered only `After=network-online.target` — NOT time-sync. So at cold boot dockerd starts omni *before* the clock is corrected. Verified on the live Pi 2026-06-19: `systemd-timesyncd` (no chrony), **no RTC, no `fake-hwclock`** (`/etc/fake-hwclock.data` absent → nothing restores the clock at boot). Two host-level mitigations (applied 2026-06-20):

1. **`fake-hwclock`** — restores the last-saved time at boot so the NTP correction is a *nudge*, not a multi-week *jump* (the jump is what wedges etcd/timers). Root-cause mitigation.
   ```bash
   apt-get install -y fake-hwclock && fake-hwclock save
   ```
2. **Restart omni once the clock is CONFIRMED synced** — enable `systemd-time-wait-sync.service` so `time-sync.target` actually blocks on synchronization, then a oneshot unit that restarts omni after it (harmless if the clock was already fine):
   ```bash
   systemctl enable systemd-time-wait-sync.service
   cat > /etc/systemd/system/omni-restart-after-timesync.service <<'UNIT'
   [Unit]
   Description=Restart omni once the clock is NTP-synced (prevents reconcile wedge)
   After=time-sync.target docker.service
   Wants=time-sync.target
   Requires=docker.service
   [Service]
   Type=oneshot
   ExecStart=/usr/bin/docker restart omni
   [Install]
   WantedBy=multi-user.target
   UNIT
   systemctl daemon-reload && systemctl enable omni-restart-after-timesync.service
   ```

Strongest fix would be a hardware RTC module on the Pi so the clock survives power loss outright. (Compose + container live at `/opt/manual_install/omni/compose.yaml`, container name `omni`.)

### Incident

2026-06-19 — power outage ~10 days prior cold-booted the whole infra; Omni came up with a stale clock and wedged (last `omni` log line ~61 days old by its frozen clock; `wc -l` static; gpu-1's `KernelArgs` never applied). Found while deploying the gpu-1 `pcie_aspm=off` fix (#582). `docker restart omni` revived the runtime, which immediately reconciled the pending `KernelArgs` and applied the arg.
