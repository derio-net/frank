## Frank Cluster Gotchas

- Always use `ServerSideApply=true` in ArgoCD sync options (avoids annotation size limits)
- Ignore Secret data diffs in ArgoCD (`ignoreDifferences` on `/data` jsonPointer)
- `prune: false` in syncPolicy — manual pruning only to avoid accidental deletion
- Intel GPU Resource Driver uses vendored chart with K8s 1.35 DRA patches
- GPU-1 has a NoSchedule taint — only GPU workloads schedule there
- SOPS/age encryption for secrets — never commit plaintext secrets
- Longhorn default replicaCount: 3 (matches 3 control-plane nodes)
- SOPS + ArgoCD ServerSideApply don't mix — encrypted secrets must live outside ArgoCD-managed paths (see `secrets/` dir) and be applied out-of-band
- Sympozium Helm chart is Git-sourced (not OCI) — chart isn't published to any registry
- Sympozium chart service template doesn't support type/annotations — use separate LB Service in extras
- Sympozium image.tag must be overridden (chart appVersion lags behind latest fix releases)
- Authentik blueprints may not auto-discover from ConfigMaps — create providers/apps via API as fallback
- Authentik API requires Bearer token (not basic auth) — create token via Django ORM: `Token.objects.get_or_create(identifier="name", defaults={"user": user, "intent": TokenIntents.INTENT_API})`
- Authentik 2026.x requires `invalidation_flow` and `redirect_uris` as list format in API calls
- Authentik `global.env` applies env vars to both server + worker (avoids duplication)
- Grafana OIDC: secret key must be `GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET` for `envFromSecret` to work
- Authentik embedded outpost requires `AUTHENTIK_HOST` env var set to external URL (e.g., `https://auth.frank.derio.net`) — without it, forward-auth redirects use `0.0.0.0:9000`
