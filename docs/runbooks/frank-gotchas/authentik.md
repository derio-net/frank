# Frank Gotchas — Authentik

Long-form companion to the **Authentik** section in `.claude/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

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

## Embedded outpost requires `AUTHENTIK_HOST`

`AUTHENTIK_HOST` env var must be set to the external URL (e.g., `https://auth.frank.derio.net`) — without it, forward-auth redirects use `0.0.0.0:9000`.
