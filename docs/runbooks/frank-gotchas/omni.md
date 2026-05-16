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
