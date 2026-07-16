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

## `OMNI_SERVICE_ACCOUNT_KEY` — the `devops` Omni service account (non-interactive auth)

`OMNI_SERVICE_ACCOUNT_KEY` (in `.env_devops`) is what lets `omnictl` and
`talosctl` authenticate to Omni **without a browser** — it is the credential the
automation (and the `omnictl kubeconfig` / `omnictl talosconfig` mints in the
section below) runs on. Not to be confused with the *minted kubeconfig* in the
next section: that is a k8s JWT this key is used to **issue**; this is the Omni
identity that authorizes the issuing.

- **What it is.** Base64 of a small JSON blob `{name, pgp_key}` where `pgp_key`
  is an armored **ed25519 PGP private key**. `name` is `devops`; the full Omni
  identity is `devops@serviceaccount.omni.sidero.dev`, role **Admin**.
- **Where it lives.** A plaintext blob on **one line of the gitignored
  `.env_devops`** — **no SOPS, no in-repo vault path**. The external
  Infisical / host secret store is the source of truth; `.env_devops` is the
  local working copy. `.env` chains `.env_common`; `.env_devops` is sourced
  separately (that's where this key and `OMNICONFIG` live).
- **Expiry.** The SA's own PGP key is long-lived — current key expires
  **2027-03-02** (created 2026-03-02). It does not auto-rotate and has no alert;
  put the date somewhere you watch, same as the kubeconfig below.

### The two-identities model (read this before debugging any auth failure)

Every Omni request is PGP-signed. Two different identities sign on this
workstation, and a failure is almost always about *which one* signed:

| Identity | Used when | Signing key |
|---|---|---|
| `devops@serviceaccount.omni.sidero.dev` (the SA) | `OMNI_SERVICE_ACCOUNT_KEY` is set in the env | signs **directly** with the SA key — no browser, valid to the SA key's own expiry (2027-03-02) |
| `you@example.com` (interactive Google login) | the SA env var is **absent** | a **short-lived** (≈4 h TTL) local keypair in `~/.talos/keys/<context>-<identity>.pgp`, re-minted via browser OIDC on expiry |

`omnictl serviceaccount list` shows the SA's registered public keys: the
long-lived one (fingerprint `2945F95C…214304568`, exp 2027-03-02) plus a litter
of already-expired short-lived signing keys — the expired ones are normal churn,
the long-lived one is what authenticates.

**Reading the error:**

- `Unauthenticated: invalid signature` — the presented signing key is
  expired / not registered (a **crypto** rejection, not authz). Usually means the
  tool fell back to an interactive identity whose local key has lapsed.
- `public key <> id mismatch` (during a browser re-auth) — the locally-cached
  identity keypair is stale versus Omni's on-file record. Fix: delete the stale
  `~/.talos/keys/<context>-<identity>.pgp` file(s) for that identity, then re-auth
  so a fresh keypair registers (see Recovery below).

### The gotcha that costs an afternoon: the key must be present at **`talosctl` runtime**

`OMNI_SERVICE_ACCOUNT_KEY` being set when you **generate** a talosconfig is not
enough — it must also be set in the shell when `talosctl` actually **runs**, because
the generated Omni talosconfig stores only the *identity* (`auth.siderov1.identity:
devops@serviceaccount.omni.sidero.dev`), and the SA key is read from the env
**per request** to sign. Two ways this bites:

- Running `talosctl` in a shell where `.env_devops` was never sourced → no SA key
  → talosctl falls back to `~/.talos/config`'s **current context** (an interactive
  identity, e.g. `omni-frank-1` → `you@example.com`) → `invalid
  signature` if that key has expired (and a browser popup on the re-auth attempt).
- Bare `talosctl …` with no `--talosconfig` uses `~/.talos/config`, whose current
  context may be an interactive one, **not** the SA — same failure.

**Do it right:**

```bash
cd <repo-root>
source .env && source .env_devops                 # sets OMNICONFIG + OMNI_SERVICE_ACCOUNT_KEY
omnictl talosconfig <out.yaml>                     # identity = devops@serviceaccount…
talosctl --talosconfig <out.yaml> -n <machine-id> version   # SA key still in env → signs silently
```

The `<machine-id>` is an Omni machine UUID from `omnictl get machines`; the call
routes through `https://omni.frank.derio.net` (the endpoint in the generated
config), Omni proxies to the node. Verified end-to-end 2026-07-16.

### Diagnose the SA key (offline — no cluster needed)

The key is self-describing; decode metadata only, **never** print the private
block:

```bash
# name + confirm structure
printf '%s' "$OMNI_SERVICE_ACCOUNT_KEY" | base64 -d | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["name"])'
# fingerprint + expiry of the embedded PGP key
printf '%s' "$OMNI_SERVICE_ACCOUNT_KEY" | base64 -d \
  | python3 -c 'import sys,json;open("/tmp/sa.asc","w").write(json.load(sys.stdin)["pgp_key"])'
gpg --show-keys /tmp/sa.asc     # read fingerprint + [expires: …]; then: rm /tmp/sa.asc
```

Cross-check the fingerprint against the `PUBLIC KEY ID` / `EXPIRATION` columns of
`omnictl serviceaccount list` (needs the SA env sourced) — the env key's
fingerprint should match the one non-expired registered entry.

### Renew (rotate) the key

The SA key does not need renewing until near its expiry, but to rotate it (or if
it is ever compromised), with the **current** SA env still valid (Admin authorizes
its own renewal, no browser):

```bash
cd <repo-root>
source .env && source .env_devops
omnictl serviceaccount renew devops        # prints a new OMNI_SERVICE_ACCOUNT_KEY value
```

Then paste the new value into **`.env_devops`** *and* the **external
Infisical / host vault** (the vault is the source of truth; the file is the
working copy). Re-source and verify with the Diagnose block above. If the
interactive admin identity is itself broken (see the mismatch case below) you
cannot fall back to browser auth to renew — the still-valid SA env is what makes
`renew` work, so rotate *before* the key lapses, not after.

### Recovery — a wedged interactive identity (`invalid signature` / `public key id mismatch`)

If the SA path works (API + Talos both fine under `source .env_devops`) but bare
`talosctl` / browser `omnictl` fails, the interactive `you@example.com`
identity is the broken one, not the SA. Clear its stale local keys and re-auth:

```bash
rm ~/.talos/keys/*you@example.com.pgp    # stale local keypairs (per-context)
cd <repo-root> && source .env                        # OMNICONFIG, but NOT the SA env
omnictl get clusters                                 # completes the Google SSO re-auth → fresh key registers
```

Note re-authing via `omnictl` only re-mints the key for the **`OMNICONFIG`
context** (`default` → `~/.talos/keys/default-…pgp`); the **talos** contexts
(`omni-frank`, `omni-frank-1`) get their own key on the next `talosctl`
interactive call, which triggers **one more** (expected) browser click. For
automation you never need the interactive path at all — use the SA env + a
SA-generated talosconfig and no browser is ever involved.

### Incident

2026-07-16 — `talosctl` against the Omni-generated talosconfig returned
`Unauthenticated: invalid signature` on two talosctl versions while `omnictl get
clusters` / `omnictl talosconfig` succeeded. Root cause was **not** the SA key
(valid to 2027-03-02, proven working through the Talos proxy against a live CP
node with the SA env sourced) and **not** clock skew (workstation vs Omni = 0 s):
`talosctl` was using `~/.talos/config`'s interactive context
(`omni-frank-1` → `you@example.com`) whose ~4 h local key had lapsed,
either without the SA env in scope or via the bare-config fallback. Fixed by the
Recovery block (stale-key delete + re-auth) for the interactive path; the durable
answer for automation is the SA-env + SA-talosconfig runtime sequence above.

## Three-key model — per-tower shutdown service accounts (gondor)

The single shared `devops` key above is being split so the **gondor** Proxmox HA
cluster (`derio-homelab/proxmox-cluster`) drives frank's power-outage safety
shutdown with a **least-privilege, single-homed** credential instead of the
Admin-scoped `devops` key. Three Omni service accounts, not one:

| Identity | Role | TTL | Homed on | Consumed by |
|---|---|---|---|---|
| `devops@serviceaccount.omni.sidero.dev` | **Admin** | to 2027-03-02 | workstation `.env_devops` (+ external Infisical/host vault) | interactive / automation `omnictl` + `talosctl` (unchanged) |
| `shutdown-tirith@serviceaccount.omni.sidero.dev` | **Operator**, frank-scoped | 1 yr (Omni max — **annual renewal**) | gondor ansible-vault, `tirith` only | orchestrator role on tirith |
| `shutdown-morgul@serviceaccount.omni.sidero.dev` | **Operator**, frank-scoped | 1 yr (Omni max — **annual renewal**) | gondor ansible-vault, `morgul` only | orchestrator role on morgul |

### Why per-tower (one key each, not one shared)

PR #38 (`proxmox-cluster`, dual-pve-nut-failover) retires `osgiliath` (the Pi
QDevice) as the single orchestrator SPOF and moves shutdown-driver duty to
**either PVE node — `tirith` or `morgul`** — elected via Proxmox HA / quorum.
Whichever node holds quorum during an outage runs `talosctl shutdown` against
frank (workers before control-plane). Either can be the driver, so **each tower
carries its own key**:

- **Single-homed → renewal touches exactly one place.** Rotating
  `shutdown-tirith` edits one vault var on one node; no shared secret fanned out
  across hosts, no cross-repo drift, no "which copy is current" ambiguity.
- **Blast radius per key is one tower.** A compromised or leaked tower key is
  revoked (`omnictl serviceaccount destroy shutdown-<node>`) without disturbing
  the other tower or the `devops` automation path.

### Least privilege — role and cluster scope

Omni roles are coarse: `None` < `Reader` < `Operator` < `Admin`. `talosctl
shutdown`/`reboot` through the Omni proxy is a machine-maintenance op, so the
floor is **`Operator`** — `Reader` is view-only and cannot reboot/shutdown;
there is no finer "reboot-only" capability to drop to. `Admin` (what `devops`
uses) is strictly more than a shutdown driver needs.

**Cluster scoping is not a `create` flag** — `omnictl serviceaccount create` only
sets a *global* role. To bind Operator to **cluster `frank` only** you apply an
Omni **AccessPolicy (ACL)**, which grants a role to an identity scoped to a
cluster. ACLs *elevate* per-cluster and cannot downgrade an existing global role
(so devops's Admin is unaffected). This Omni currently runs **no ACL**
(`omnictl get accesspolicy` is empty) and has **one cluster** (`frank`), which
gives two equivalent-today options:

- **Simplest (single-cluster):** create each SA with global `--role Operator`,
  no ACL. Blast radius today = frank only, because frank is the only cluster.
- **Future-proof (true least-privilege):** create each SA with global
  `--role Reader` (harmless view-only everywhere) and apply an ACL granting
  `Operator` on cluster `frank`. If a second cluster is ever added to this Omni,
  these keys do **not** inherit Operator on it.

> Not live-verified: create/ACL-apply were not run this session (diagnosis only),
> so the base-Reader + ACL-elevation path is grounded in the Omni ACL docs' role
> examples, not exercised on this backend (v1.5.0). If in doubt, use the simplest
> form now and add the ACL when a second cluster appears.

### Create commands (run by the operator; DO NOT run from here)

TTL: `omnictl serviceaccount create` defaults to **8760h (1 year)**, and on this
backend **1 year is also the hard maximum** — a longer value was rejected
empirically (a `43800h` / 5-year create failed). So these are **annual-renewal**
keys: `--ttl 8760h` below (equivalently, omit `--ttl` for the 1-year default).
A short-lived key on a crisis-only safety path makes the active expiry check
(see verification) **non-negotiable** — it is the compensating control.

```bash
cd /Users/derio/Docs/projects/DERIO_NET/frank
source .env && source .env_devops          # devops (Admin) authorizes the create; no browser

# Simplest (single-cluster) — global Operator:
omnictl serviceaccount create shutdown-tirith --use-user-role=false --role Operator --ttl 8760h
omnictl serviceaccount create shutdown-morgul --use-user-role=false --role Operator --ttl 8760h

# Future-proof variant — create as Reader, then scope Operator@frank via ACL:
#   omnictl serviceaccount create shutdown-tirith --use-user-role=false --role Reader --ttl 8760h
#   omnictl serviceaccount create shutdown-morgul --use-user-role=false --role Reader --ttl 8760h
#   omnictl apply -f frank-shutdown-acl.yaml
```

ACL (only for the future-proof variant) — `frank-shutdown-acl.yaml`:

```yaml
metadata:
  namespace: default
  type: AccessPolicies.omni.sidero.dev
  id: frank-shutdown
spec:
  rules:
    - users:
        - shutdown-tirith@serviceaccount.omni.sidero.dev
        - shutdown-morgul@serviceaccount.omni.sidero.dev
      clusters:
        - frank
      role: Operator
  tests: []
```

Each `create` prints an `OMNI_SERVICE_ACCOUNT_KEY=<blob>` line. **Do not** put it
in frank's `.env_devops` — these are gondor-only. Paste each into the
**proxmox-cluster ansible-vault** (`config/host_vars/cluster_frank/vault.yml`):
`shutdown-tirith` → `vault_omni_sa_key_tirith`, `shutdown-morgul` →
`vault_omni_sa_key_morgul`, wired through
`config/inventory/group_vars/cluster_frank/vars.yml` exactly as the existing
`omni_sa_key: "{{ vault_omni_sa_key }}"` line does (add per-node
`omni_sa_key_tirith` / `_morgul`). That repo standardizes on ansible-vault
(AES256) — no SOPS/Infisical.

### Active verification is mandatory (a silent expiry defeats the shutdown)

A shutdown key that has silently expired fails at the **worst** moment — mid power
outage, when the driver tower tries `talosctl shutdown` and gets `invalid
signature`. `config/playbooks/homelab-shutdown-verify.yml` must therefore, for
**each** tower key:

1. **Prove it authenticates** — `talosctl --talosconfig <gen> -n <machine-id>
   version` through the Omni proxy succeeds (the same runtime rule as `devops`:
   the SA key must be in the env when `talosctl` runs, not just at generation).
2. **Alert on days-to-expiry** — decode the key's PGP expiry offline (the
   "Diagnose the SA key" block above) and page at **T-30d**. With only a 1-year
   TTL this alert is **mandatory**, not a nice-to-have: it is the sole thing
   standing between an annual renewal slipping and the shutdown failing mid-outage.

### Renewal (per key, one place)

Same mechanism as `devops` — with a still-valid authorizing identity sourced:

```bash
omnictl serviceaccount renew shutdown-tirith    # or shutdown-morgul; prints a new key value
```

Paste the new value into **that one tower's** vault var
(`vault_omni_sa_key_tirith` *or* `_morgul`) and nothing else — single-homed means
one edit, no drift. `renew` registers an additional public key to the SA (the old
one ages out); the identity and its ACL/role are unchanged.

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
