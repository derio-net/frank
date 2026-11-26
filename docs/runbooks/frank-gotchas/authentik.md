# Frank Gotchas — Authentik

Long-form companion to the **Authentik** section in `agents/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

## Blueprints mount in the worker pod, not the server

Authentik blueprints are mounted into the **worker** pod (not server) via `blueprints.configMaps` in `apps/authentik/values.yaml`. New ConfigMaps must be registered in that list or they won't be discovered.

## Blueprints don't assign providers to the embedded outpost

Authentik blueprints create proxy providers and applications, but do NOT assign providers to the embedded outpost — outpost assignment must be done manually via Django ORM (`outpost.providers.add(provider)`) after the blueprint applies. See `frank-argocd.md` for the full command.

The embedded outpost provider assignment persists in the database — it survives pod restarts but not database loss.

## API uses Bearer tokens (not basic auth)

Create a token via Django ORM:

```python
Token.objects.get_or_create(
    identifier="name",
    defaults={"user": user, "intent": TokenIntents.INTENT_API}
)
```

## 2026.x API shape changes

Authentik 2026.x requires `invalidation_flow` and `redirect_uris` as a list of objects `[{"matching_mode": "strict", "url": "..."}]` (not strings) in API calls. Also requires `signing_key` UUID — query an existing provider to find it.

## `global.env` applies to both server + worker

Saves duplication when an env var needs to be set on both pods.

## Embedded outpost host exists in two places

`AUTHENTIK_HOST` must be set on the server and worker deployments, but changing it
does not rewrite the embedded outpost's database-backed `Outpost.config`. The
outpost uses its persisted `authentik_host` or `authentik_host_browser` value to
construct forward-auth browser redirects.

This split surfaced during the 2026-08-01 domain migration: the pods had
`AUTHENTIK_HOST=https://auth.cluster.derio.net`, while requests to
`grafana.cluster.derio.net` still redirected to `auth.frank.derio.net`. The
cluster proxy blueprint now identifies `authentik Embedded Outpost` by name and
declares only these config fields:

```yaml
attrs:
  config:
    authentik_host: https://auth.cluster.derio.net
    authentik_host_browser: https://auth.cluster.derio.net
```

Do not include `providers` in that blueprint entry. Provider assignments are
managed separately and must survive host changes.

## Decision (2026-07-12): hermes dashboard drops forward-auth for its own basic-auth

**Context.** The Hermes web dashboard was migrated to the official image (willikins#285). Its two Traefik `IngressRoute`s (`hermes` → `hermes-agent-shell-dashboard:9119`, `hermes-api` → `:8642`, both in `traefik-system`) were given the `authentik-forwardauth` middleware under the "login-less UIs get forward-auth" rule. But `https://hermes.cluster.derio.net` returned an **authentik 404** (`x-powered-by: authentik`) on every path — including `/outpost.goauthentik.io/start`. Root cause: **no authentik application / proxy-provider was ever configured for `hermes.cluster.derio.net`**, so the outpost's Host match found nothing and 404'd — the same class of failure as the frank-omni `.frank` re-front above, but here the Host was simply never registered rather than re-fronted.

**Why not just register the authentik app.** In the meantime frank#626 gave the dashboard its **own basic-auth** (`HERMES_DASHBOARD_BASIC_AUTH_*` — the dashboard refuses to bind `0.0.0.0` without an auth provider and self-authenticates at `:9119/login → 200`). That made the authentik edge layer both **broken** (404) and **redundant** (the app already authenticates users).

**Decision.** Drop `authentik-forwardauth` from both hermes routes; keep `ip-allowlist` + `security-headers`; rely on the dashboard's own basic-auth. SSO via authentik (registering a proper proxy-provider + outpost assignment for the Host) is left as a possible later follow-up. Change lives in `apps/traefik/manifests/ingressroutes.yaml`; ArgoCD reconciles the `traefik-system` IngressRoutes on merge. Acceptance-matrix row: `hermes-dashboard-api-routable`.

## authentik-server SIGBUS crashloop: Prometheus multiprocess files fill /dev/shm (2026-11-26)

**Symptom.** `layer-13-auth-down` fires with `deployment/authentik-server has 1 replica(s) unavailable`. One server pod is `Running 0/1` and failing its startup probe with 502s. Its log loops roughly twice a second: `Finished authentik bootstrap` → `applying django migrations` → `gunicorn process died, restarting … "error":"signal: bus error"`. The postgres connection succeeds every time, so the database is not the problem.

**Cause.** The image sets `TMPDIR=/dev/shm/`, and `/lifecycle/ak` defaults `PROMETHEUS_MULTIPROC_DIR` to `${TMPDIR}/authentik_prometheus_tmp` unless the variable is already set. `prometheus_client` writes mmap'd `counter_<id>.db` / `gauge_all_<id>.db` / `histogram_<id>.db` files there. Authentik's `gunicorn.conf.py` tries to key them by a reusable worker number, but metrics created in the master under `preload_app = True` keep keying by **worker PID**. A fresh pod's files are named after the PIDs in `Booting worker with pid: N`. gunicorn recycles workers every `max_requests = 1000` (+50 jitter), so each recycle leaks three files, about 1 MB/day per replica. `/dev/shm` is the **pod sandbox's** 64M tmpfs. After ~64 days it is full, the next mmap write raises SIGBUS rather than ENOSPC, and gunicorn can never start again. Restarting the container does not help, because the tmpfs belongs to the sandbox and survives the restart. Every failed start also mints new PIDs, so the leak feeds itself. Measured 2026-11-26: the failing pod had 64M/64M (~10k files) and its healthy sibling, the same age, had 60M/64M (2152 PIDs).

**Diagnose.** `kubectl -n authentik exec <pod> -- df -h /dev/shm` and `du -sh /dev/shm/*`. The worker deployment is unaffected (one long-lived process).

**Recover.** Delete the failing pod, so the new sandbox gets an empty `/dev/shm`. Then delete its sibling once the replacement is Ready, because both pods were created together and are on the same clock.

**Fix.** `server.env` sets `PROMETHEUS_MULTIPROC_DIR=/authentik-prometheus`, a **disk-backed** `emptyDir` with `sizeLimit: 1Gi`. That is about three years of growth at the measured rate. If the directory ever reaches the limit, the kubelet evicts the pod (a clean reset) instead of leaving it SIGBUS-looping forever. Never use `medium: Memory` here, because that recreates the original failure. Guard: `scripts/tests/test_authentik_prometheus_multiproc_dir.py`. Debug journal: `docs/superpowers/journals/debug/2026-11-26-authentik-shm-sigbus.md`.
