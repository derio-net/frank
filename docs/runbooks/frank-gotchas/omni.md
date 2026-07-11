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

## frank-omni Pi DIED (hardware) — distinct from the wedge; the Pi was a 3-role SPOF

2026-06-20 — the frank-omni **Pi 5 died outright** (hardware: `ssh frank-omni` + both public vhosts time out — *not* the silent **wedge** above, which is a live-but-frozen runtime that `docker restart omni` fixes). Worst case, because that one un-HA'd Pi carried **three roles**:

1. the on-prem **Omni** control plane — the kubectl + talosctl access path;
2. the **public edge** (a Docker Traefik on the Pi) for every `*.frank.derio.net` name (`omni.`, `auth.`, and the legacy service aliases);
3. the **Let's Encrypt cert-minter** for the `frank.derio.net` zone.

### What survives, what dies

The **cluster keeps running** — control plane (mini-1/2/3) and workers boot independently of Omni, so every in-cluster workload (the Authentik pod, Grafana, …) and the LAN service IPs (192.168.55.2xx) stay up. What you lose:

- **kubectl / talosctl.** The stored kubeconfig points at `https://omni.frank.derio.net:8100/` (the dead Omni k8s proxy) with OIDC-via-Omni; the talosconfig routes through the same proxy. The **real apiserver (`192.168.55.21:6443`) and Talos API (`:50000`) stay reachable on the LAN**, but there is no non-Omni credential for them — no break-glass talosconfig is saved, and Omni (which mints them) is dead, so you can't make one. **ArgoCD (git → sync) becomes the only "apply" path.**
- **Everything on `*.frank.derio.net`** — Omni's own UI, plus the auth and legacy-service edges.

### Recovery (2026-06-20)

Omni itself can't be revived without hardware. But the *services* it fronted are re-frontable from **inside** the cluster, because DNS for `*.frank.derio.net` already points at the in-cluster Traefik (`192.168.55.220`) — they were merely missing routes. Full playbook in **`networking.md` → "External-edge death: re-front orphaned `*.frank` names on in-cluster Traefik"** (#590 / #591 / #592). Key point: in-cluster Traefik **re-mints the `frank.derio.net` certs itself** via its Cloudflare DNS-01 resolver — the `CF_DNS_API_TOKEN` is scoped to the whole `derio.net` zone, so it issues `frank.` certs exactly as it does `cluster.` ones — so the dead Pi's cert-minter role transfers cleanly. `auth.frank.derio.net` also needs an operator DNS flip (`.10 → .220`, it was a dedicated A record at the Pi); the other names already resolved to `.220`.

### The monitoring blind spot — Omni death does NOT page (a Layer 2 gap)

The Pi death was **near-silent across the whole stack**: the Derio Ops board stayed all-green and Telegram carried only the by-design canaries. Why:

- The board's layer-health is **in-cluster pod / ClusterIP** based (VictoriaMetrics, which stayed up because the cluster stayed up). Every workload was genuinely `Ready`, so nothing flipped — *correct* (no workload died), but it means the board is blind to an edge / management-plane death **by construction**.
- **Omni has no alert rule.** The blackbox `management_plane_probes` VMProbe (`apps/blackbox-exporter/manifests/vmprobe.yaml`) scrapes `probe_success{instance=~"https://omni.frank.derio.net.*"}`, but **nothing in `alert-rules-cm.yaml` consumes it** — no `github_issue` label, no card, no page. Omni is a **Layer 2 (OS & Bootstrap)** concern (the layer mentions Omni); it can die and the only signal is a human noticing `omni.frank.derio.net` 500s.
- **Fix (deferred until Omni is back):** add a Grafana rule on that existing metric — `severity: critical`, route to Telegram and/or `github_issue: frank-ops#2` (Layer 2). The data is already scraped; it's purely a missing rule.

### The durable fix — rebuild off the Pi

The root problem is the un-HA'd single-Pi SPOF, not this one death. The replacement is **not another Pi**: Omni is being rehomed onto an **Ansible-managed Proxmox host with HA + UPS** for the whole homelab. That migration is its own Layer 2 build/operating post (this incident is its cold open), and it also retires the **wedge** gotcha above — a UPS plus a real RTC end the cold-boot clock-jump class outright. Until then the temporary `*.frank` re-fronting (`networking.md`) carries the services.

## Renewing the fr-isolation cluster-admin kube token (Omni service-account kubeconfig)

The `fr-isolation` `cluster-admin` devcontainer profile
(`.devcontainer/cluster-admin/`) talks to Frank with an **Omni service-account
kubeconfig** — an `omni-omni-service-account-issuer` JWT carrying `system:masters`
on cluster `frank`. It is a *minted* token, not backed by a stored Omni object,
so it simply **expires** (default TTL 1 year) and re-minting is the only
"renewal". It has no alert: expired → every isolated `kubectl` gets `401`, and it
lapsed unnoticed once. **Put the expiry date somewhere you actually watch.**

### Diagnose (offline — no cluster needed)

It's a JWT, so `exp` is self-describing. Decode the base64 kubeconfig from the
host secrets file, take the `token:` value, split on `.`, base64url-decode the
middle (payload) segment, and read `exp` (Unix seconds). `exp` in the past →
expired. The token is structurally fine when this happens; it is purely a TTL
lapse, not corruption. `iss`/`sub`/`groups`/`cluster` in the same payload confirm
it's the right identity.

### Re-mint (from this repo, with Omni env sourced)

```bash
cd <repo-root>
source .env && source .env_devops          # OMNICONFIG + Omni service-account auth
omnictl kubeconfig --service-account \
  --user fr-isolation --groups system:masters \
  --cluster frank --ttl 8760h \
  --merge=false --force <out.yaml>
```

`--user` becomes the token `sub` — this is the *only* place the identity name
lives, so a stale `vk-isolation` sub is the leftover from the vk→fr rename;
re-mint with `--user fr-isolation` to retire it (there is no in-place rename of a
signed JWT). **Verify end-to-end before trusting it** — a well-formed token is
not the same as a working one:

```bash
kubectl --kubeconfig <out.yaml> auth whoami      # → fr-isolation / system:masters
kubectl --kubeconfig <out.yaml> auth can-i '*' '*'   # → yes
```

### Install

Base64 the kubeconfig into `KUBECONFIG_B64` in the host secrets env-file, then
**`chmod 600` the file** (see below). The `TALOSCONFIG_B64` in the same file is a
Siderov1 identity (no expiry) — it does not change on a kube-token renewal.
Nothing to delete for the old identity: a `kubeconfig`-minted service account is
just a signed token, not a stored object, so the previous token simply stays
expired.

> Precondition: this routes through `omni.frank.derio.net`, so Omni must be
> reachable — if it is wedged or dead, see the sections above first.

### Host secrets MUST be private (0600 / 0700)

The `~/.config/fr/secrets/` store must be owner-only. A world-readable store
(`0644` files under `0755` dirs) once exposed this live `system:masters` token to
any local process. Files `0600`, dirs `0700` — `0700` on the dir chain is the real
choke point (traversal is blocked there). The `fr` generator now births these
files private and self-heals loose perms on the next `fr isolation up` /
`fr init scaffold` (super-fr#376); if you ever hand-place a file under that dir,
`chmod 600` it yourself.
