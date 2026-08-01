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
