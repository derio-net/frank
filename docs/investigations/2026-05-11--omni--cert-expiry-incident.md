# Investigation: Omni cert expiry → cluster-wide management-plane 500

**Status:** Resolved — cert renewed, dedicated systemd timer installed.
**Layer:** `omni` (Sidero Omni self-hosted control plane)
**Trigger:** A `kubectl get nodes` call from the operator's laptop returned `oidc discovery error: 500 Internal Server Error` on 2026-05-11 ~15:30 CEST.
**Outage shape:** Workloads unaffected (kubelet, ArgoCD, all Frank workloads kept running). Management plane (kubectl, omnictl, Omni Web UI, kubeconfig-OIDC) all 500. Cluster was "running but unmanageable" — the failure mode you don't notice until you try to operate.
**Detected:** 2026-05-11 ~13:30 UTC (~46h after expiry).
**Resolved:** 2026-05-11 15:04 UTC (cert renewed + container restarted).

## Verdict

The Let's Encrypt leaf for `CN=omni.frank.derio.net` (issuer LE E7, ECDSA) expired at `notAfter=2026-05-09 13:52:36 UTC`. Renewal had not been wired: the cert was originally issued under non-default certbot dirs (`/opt/manual_install/certbot/config/...` per `omni/certbot/certbot.md`), and the snap-installed `snap.certbot.renew.timer` only scans `/etc/letsencrypt/`. The timer fired daily for 30+ days as a clean no-op (`certbot certificates` → `No certificates found`) while the cert aged through Let's Encrypt's 30-day pre-expiry renewal window.

## Symptom shape (why the 500 wasn't an Omni crash)

Across every affected client the error body contained the same Go x509 substring:
```
tls: failed to verify certificate: x509: certificate has expired or is not yet valid:
current time 2026-05-11T... is after 2026-05-09T13:52:36Z
```

That string is not produced by Omni — it's emitted by **Traefik's outbound TLS verify** when it forwards `https://omni.frank.derio.net/...` to the Omni backend on `:8100` and Omni presents the expired cert. Traefik returns 500 with the wrapped error in the body, which is what `kubectl`, `omnictl`, and the browser all see verbatim.

In Omni's own log the inverse direction shows up:
```
2026/05/11 14:04:33 http: TLS handshake error from 172.18.0.2:36092:
remote error: tls: bad certificate
```
where `172.18.0.2` is Traefik in the docker bridge — i.e. the same exchange, logged from the receiving side of the failed mTLS step. Omni v1.5.0 stayed `Up 3 weeks (healthy)` the entire time; the container never crashed and the docker-side health check never failed because it doesn't validate the served TLS leaf.

## Hardware / topology context

The Omni control-plane runs as Docker containers on a single Pi (`frank-omni`, hostname `omni`, 8 GiB RAM, NVMe-backed):

| Container | Image | Role |
|---|---|---|
| `traefik` | `traefik:v3.6.4` | TLS termination on `:443`, reverse-proxies to omni on `:8100` |
| `omni` | `ghcr.io/siderolabs/omni:v1.5.0` | Sidero Omni control plane; listens directly on `:8100` |
| `portainer` | `portainer/portainer-ce:2.32.0` | Side management UI |

Two separate cert pipelines exist on this host:
- `:443` cert (`CN=frank.derio.net`, issuer LE R12, RSA, valid through 2026-06-26) — managed by Traefik's built-in ACME
- `:8100` cert (`CN=omni.frank.derio.net`, issuer LE E7, ECDSA, **expired 2026-05-09**) — managed by certbot on the host with the Cloudflare DNS-01 plugin

The `:443` pipeline kept renewing fine throughout. The `:8100` pipeline never renewed once.

## What was ruled out (and how)

| Hypothesis | Source | Verdict |
|---|---|---|
| Clock drift on the Pi | `timedatectl` → "System clock synchronized: yes", NTP active | ❌ |
| Disk full | `df -h` → 12G/917G used | ❌ |
| OOM / RAM pressure | `free -h` → 819Mi/8Gi used | ❌ |
| Omni crashlooping | `docker ps` → `Up 3 weeks (healthy)`, container ID unchanged | ❌ |
| Two unrelated problems (TLS expiry + app bug) | After topology check: single root cause produces both `bad certificate` (inbound mTLS) and `tls: failed to verify certificate` (outbound TLS verify) log lines | ❌ |
| certbot timer broken | `journalctl -u snap.certbot.renew.service` → daily success for 30+ days | Yes, but no-op (different cause) |

## Investigation path

1. Phase 1 evidence on the Pi: clock, disk, RAM, services, ports, container topology. Eliminated environmental causes.
2. Filtered docker logs: caught both directions of the TLS failure within seconds. The Traefik IP `172.18.0.2` in the "bad certificate" log was the key correlating clue.
3. Cert dates per port: `:8100` expired, `:443` valid → confirmed two pipelines, narrowed to the `:8100` one.
4. certbot state on host: timer firing fine, but `certbot certificates` empty and `/etc/letsencrypt/renewal/` absent → renewal config was elsewhere.
5. `docker inspect omni --format '{{range .Mounts}}...'` → cert bind-mount path `/opt/manual_install/certbot/config/live/...` → confirmed via `omni/certbot/certbot.md` that the original `certonly` used non-default dirs.

Total time from first symptom to identified root cause: ~30 minutes.

## Remediation

1. **Renew the cert:** ran `certbot renew` on the Pi with the matching `--config-dir`/`--work-dir`/`--logs-dir` flags + `--deploy-hook 'docker restart omni'`. Dry-run first (no LE quota cost), then real renew. Cert renewed to `notAfter=2026-08-09 14:04:29 GMT`.
2. **Reload Omni:** `docker restart omni` was mandatory — Omni v1.5.0 reads `/tls.crt` once at process start and has no SIGHUP reload path. Container ID preserved; Talos node state in `/etc/etcd -> /_out/etcd` bind-mount survived the restart.
3. **Install a dedicated systemd timer** (`omni-cert-renew.{service,timer}`) on `frank-omni` that runs the renewal daily with the correct flags and the deploy-hook. The `--deploy-hook` only fires when certbot actually issues a new cert, so the daily firing is a ~200ms no-op 88 days out of 90.

## What's still missing (recommendations)

Two gaps this incident exposed beyond the immediate fix:

- **No blackbox probe coverage for `omni.frank.derio.net`.** `apps/blackbox-exporter/manifests/vmprobe.yaml` only probes the workloads it knows about; the cluster's own management-plane endpoints have zero probe coverage. Adding `https://omni.frank.derio.net/` (and `argocd`, `authentik`, etc.) costs a few lines.
- **No cert-expiry alert.** A `probe_ssl_earliest_cert_expiry - time() < 14*86400` rule subscribed to Telegram would have paged at 2026-04-25 — 16 days before expiry. The rule was scoped in `docs/superpowers/specs/2026-04-20--obs--pass3-followups-design.md` and exists as a placeholder comment at `apps/grafana-alerting/manifests/alert-rules-cm.yaml:1173`, inside the Layer 18 (Hop) block. Even implemented in-place it wouldn't have caught this — needs to be a global rule keyed on any Probe instance.

Both are folded into the obs-pass3 follow-ups spec for the next pass.

## Files touched

- `omni/certbot/certbot.md` — added Renew section (manual, automated systemd timer, lock recovery, verification)
- `.claude/rules/frank-gotchas.md` — added the cert-renewal trap as a recurring-gotcha entry
- `docs/superpowers/specs/2026-04-20--obs--pass3-followups-design.md` — added "Concrete motivating incident" callout
- `docs/investigations/2026-05-11--omni--cert-expiry-incident.md` — this file
- `/usr/local/sbin/omni-cert-renew.sh` on `frank-omni` — wrapper script (new)
- `/etc/systemd/system/omni-cert-renew.{service,timer}` on `frank-omni` — daily timer (new)

## Changelog

- **2026-05-11 ~15:30 CEST** — Investigation opened. Root cause identified within ~30 min from `docker logs omni` + cert-dates comparison + certbot state inspection.
- **2026-05-11 17:03 CEST** — Cert renewed (`notAfter=2026-08-09 14:04:29 GMT`).
- **2026-05-11 17:04 CEST** — Omni container restarted. End-to-end verified: `https://omni.frank.derio.net/` → 200, OIDC discovery → 200, `:8100` API → 401 (correct).
- **2026-05-11 17:30 CEST** — `omni-cert-renew.timer` installed and enabled. Next firing 2026-05-12 00:57:34 CEST.
