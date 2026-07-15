---
title: "Operating on Authentication"
series: ["operating"]
layer: auth
date: 2026-03-13
draft: false
tags: ["operations", "authentik", "oidc", "sso", "security", "troubleshooting"]
summary: "Day-to-day commands for managing Authentik SSO, checking OIDC flows, and debugging authentication issues across the cluster."
weight: 9
reader_goal: "Manage Authentik SSO users and providers, rotate OIDC client secrets, debug login loops and forward auth redirects, and validate token flows."
diataxis: [how-to, reference]
last_updated: 2026-07-15
last_updated_commit: https://github.com/derio-net/frank/commit/a8bed9a1d358b7ad87bb6dcaa9b0162e5fb0e127
---

{{< last-updated >}}

This is the operational companion to [Unified Auth — Authentik SSO for the Entire Cluster]({{< relref "/docs/building/13-unified-auth" >}}). That post covers the OIDC provider setup and forward auth proxy configuration. This one is the day-to-day runbook for managing users, rotating secrets, and debugging login issues.

Source your environment:

```bash
source .env
```

## What "Healthy" Looks Like

Authentication is healthy when Authentik at `192.168.55.211:9000` is responding, all OIDC providers show valid status, and users can log into ArgoCD, Grafana, and Infisical via SSO without errors. Forward auth should pass requests through for Longhorn UI, Hubble UI, and Sympozium.

### Verify

```bash
# Authentik pods running
kubectl get pods -n authentik

# Test OIDC well-known endpoint
curl -s http://192.168.55.211:9000/application/o/<provider-slug>/.well-known/openid-configuration | jq
```

{{< screenshot src="authentik-providers-healthy.png" caption="Authentik admin UI: all cluster OIDC and proxy providers with healthy status" >}}

## Observing State

### Authentik Status

```bash
kubectl get pods -n authentik
kubectl logs -n authentik deploy/authentik-server --tail=50
kubectl logs -n authentik deploy/authentik-worker --tail=50
```

### API Access

Authentik API requires a Bearer token. Generate one via the Django shell:

```bash
kubectl exec -n authentik deploy/authentik-server -it -- ak shell
```

```python
from authentik.core.models import Token, TokenIntents, User
user = User.objects.get(username="akadmin")
token, created = Token.objects.get_or_create(
    identifier="api-ops",
    defaults={"user": user, "intent": TokenIntents.INTENT_API}
)
print(token.key)
```

```bash
# List providers
curl -s -H "Authorization: Bearer <token>" \
  http://192.168.55.211:9000/api/v3/providers/all/ | jq '.results[].name'

# List users
curl -s -H "Authorization: Bearer <token>" \
  http://192.168.55.211:9000/api/v3/core/users/ | jq '.results[] | {username, email, is_active}'
```

## Routine Operations

### Add Users and Groups

```bash
# Via API
curl -s -X POST -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  http://192.168.55.211:9000/api/v3/core/users/ \
  -d '{"username": "newuser", "name": "New User", "email": "user@example.com", "is_active": true}'

# List groups
curl -s -H "Authorization: Bearer <token>" \
  http://192.168.55.211:9000/api/v3/core/groups/ | jq '.results[] | {name, pk}'
```

Or use the Authentik admin UI at `http://192.168.55.211:9000/if/admin/` for one-off changes.

### Rotate Client Secrets

1. Generate a new secret in Authentik admin UI under the provider settings.
2. Update the secret in Infisical.
3. Force ESO resync: `kubectl annotate es <name> -n <ns> force-sync=$(date +%s) --overwrite`
4. Restart the affected service.

For Grafana specifically, the secret must be stored with key `GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET` for `envFromSecret` to work.

### Manage API Tokens

```bash
kubectl exec -n authentik deploy/authentik-server -it -- ak shell
```

```python
from authentik.core.models import Token
for t in Token.objects.filter(intent="api"):
    print(f"{t.identifier}: {t.user.username} expires={t.expires}")
```

## Runbook

### OIDC Login Loop

If a service redirects back and forth between the login page:

```bash
kubectl logs -n authentik deploy/authentik-server --tail=100 | grep -i "oauth\|oidc\|redirect"
curl -s -H "Authorization: Bearer <token>" \
  http://192.168.55.211:9000/api/v3/providers/oauth2/ | jq '.results[] | {name, redirect_uris}'
```

Common causes:
- Redirect URI mismatch (must be exact, including trailing slash)
- `redirect_uris` must be a list in Authentik 2026.x API calls
- Missing `invalidation_flow` in provider config (required in 2026.x)

### Forward Auth Redirects to 0.0.0.0

The embedded outpost does not know its own external URL. Set `AUTHENTIK_HOST` in Helm values:

```yaml
global:
  env:
    - name: AUTHENTIK_HOST
      value: "https://auth.frank.derio.net"
```

After updating `apps/authentik/values.yaml`, ArgoCD syncs the change. Verify:

```bash
kubectl get deploy -n authentik authentik-server \
  -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="AUTHENTIK_HOST")].value}'
# Expected: https://auth.frank.derio.net

curl -sk -o /dev/null -w "%{redirect_url}\n" https://longhorn.frank.derio.net/
# Expected: https://auth.frank.derio.net/outpost.goauthentik.io/...
```

### Forward Auth 403

```bash
kubectl logs -n authentik -l app.kubernetes.io/component=outpost --tail=50
kubectl exec -n authentik -l app.kubernetes.io/component=outpost -- \
  curl -s http://authentik-server.authentik.svc:9000/api/v3/root/config/
```

### Grafana Secret Key Mismatch

If Grafana shows "login error" after OIDC redirect:

```bash
kubectl get secret -n grafana grafana-oidc -o jsonpath='{.data}' | jq 'keys'
# Must contain: GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET
# NOT: client_secret or clientSecret
```

### Token Validation Failures

```bash
curl -s http://192.168.55.211:9000/application/o/<provider-slug>/.well-known/openid-configuration | jq
curl -s -X POST http://192.168.55.211:9000/application/o/token/ \
  -d "grant_type=client_credentials&client_id=<id>&client_secret=<secret>"
```

## Missteps

| What we assumed | Why it was wrong | What it cost |
|-----------------|------------------|-------------|
| Authentik forward auth auto-resolves its external URL | The embedded outpost doesn't know its public URL — defaults to `0.0.0.0` in redirects | Forward auth redirects broke until `AUTHENTIK_HOST` was explicitly set in values. |
| Grafana OIDC secret key matches Authentik's default naming | Grafana's `envFromSecret` expects `GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET` — not `client_secret` | Login errors until the Secret key was renamed. |
| Authentik provider config is backwards-compatible across versions | 2026.x requires `invalidation_flow` and list-format `redirect_uris` | OIDC login loops until config was updated. |

## Quick Reference

| Command | What It Does |
|---------|-------------|
| `kubectl get pods -n authentik` | Check Authentik pod status |
| `kubectl logs -n authentik deploy/authentik-server` | Server logs |
| `kubectl logs -n authentik deploy/authentik-worker` | Worker logs |
| `kubectl exec -n authentik deploy/authentik-server -it -- ak shell` | Django admin shell |
| `curl -H "Authorization: Bearer <token>" .../api/v3/core/users/` | List users via API |
| `curl .../api/v3/providers/oauth2/` | List OIDC providers |
| `curl .../.well-known/openid-configuration` | Test OIDC discovery |

## References

- [Authentik Documentation](https://docs.goauthentik.io/docs/)
- [Authentik API Reference](https://docs.goauthentik.io/developer-docs/api/)
- [Building Post — Unified Auth]({{< relref "/docs/building/13-unified-auth" >}})
