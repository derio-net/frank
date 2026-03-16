---
title: "Operating on Authentication"
date: 2026-03-13
draft: false
tags: ["operations", "authentik", "oidc", "sso", "security"]
summary: "Day-to-day commands for managing Authentik SSO, checking OIDC flows, and debugging authentication issues across the cluster."
weight: 108
cover:
  image: cover.png
  alt: "Frank installing a new security lock system into his own chest"
  relative: true
---

This is the operational companion to [Unified Auth — Authentik SSO for the Entire Cluster]({{< relref "/building/13-unified-auth" >}}). That post covers the OIDC provider setup and forward auth proxy configuration. This one is the day-to-day runbook for managing users, rotating secrets, and debugging login issues.

## What "Healthy" Looks Like

Authentication is healthy when Authentik at `192.168.55.211:9000` is responding, all OIDC providers show valid status in the admin UI, and users can log into ArgoCD, Grafana, and Infisical via SSO without errors. Forward auth should be passing requests through for Longhorn UI, Hubble UI, and Sympozium.

## Observing State

### Authentik Status

```bash
# Check Authentik pods
kubectl get pods -n authentik

# Check server and worker logs
kubectl logs -n authentik deploy/authentik-server --tail=50
kubectl logs -n authentik deploy/authentik-worker --tail=50
```

### API Access

Authentik API requires a Bearer token. Create one via the Django shell if needed:

```bash
# Get a shell into the Authentik server
kubectl exec -n authentik deploy/authentik-server -it -- ak shell
```

```python
# In the Django shell:
from authentik.core.models import Token, TokenIntents, User
user = User.objects.get(username="akadmin")
token, created = Token.objects.get_or_create(
    identifier="api-ops",
    defaults={"user": user, "intent": TokenIntents.INTENT_API}
)
print(token.key)
```

```bash
# List providers via API
curl -s -H "Authorization: Bearer <token>" \
  http://192.168.55.211:9000/api/v3/providers/all/ | jq '.results[].name'

# List users
curl -s -H "Authorization: Bearer <token>" \
  http://192.168.55.211:9000/api/v3/core/users/ | jq '.results[] | {username, email, is_active}'
```

## Routine Operations

### Add Users and Groups

```bash
# Create a user via API
curl -s -X POST -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  http://192.168.55.211:9000/api/v3/core/users/ \
  -d '{"username": "newuser", "name": "New User", "email": "user@example.com", "is_active": true}'

# List groups
curl -s -H "Authorization: Bearer <token>" \
  http://192.168.55.211:9000/api/v3/core/groups/ | jq '.results[] | {name, pk}'
```

Or use the Authentik admin UI at `http://192.168.55.211:9000/if/admin/` — it is often faster for one-off changes.

### Rotate Client Secrets

When rotating an OIDC client secret for a service (e.g., Grafana):

1. Generate a new secret in Authentik admin UI under the provider settings
2. Update the secret in Infisical (the source of truth)
3. Force ESO to resync: `kubectl annotate es <name> -n <ns> force-sync=$(date +%s) --overwrite`
4. Restart the affected service to pick up the new secret

> For Grafana specifically, the secret must be stored with key `GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET` in the Kubernetes Secret for `envFromSecret` to work.

### Manage API Tokens

```bash
# List API tokens via Django shell
kubectl exec -n authentik deploy/authentik-server -it -- ak shell
```

```python
from authentik.core.models import Token
for t in Token.objects.filter(intent="api"):
    print(f"{t.identifier}: {t.user.username} expires={t.expires}")
```

## Debugging

### OIDC Login Loop

If a service redirects back and forth between the login page:

```bash
# Check Authentik server logs for OIDC errors
kubectl logs -n authentik deploy/authentik-server --tail=100 | grep -i "oauth\|oidc\|redirect"

# Verify redirect URIs match exactly
curl -s -H "Authorization: Bearer <token>" \
  http://192.168.55.211:9000/api/v3/providers/oauth2/ | jq '.results[] | {name, redirect_uris}'
```

Common causes:
- Redirect URI mismatch (must be exact, including trailing slash)
- `redirect_uris` must be a list in Authentik 2026.x API calls
- Missing `invalidation_flow` in provider config (required in 2026.x)

### Forward Auth Redirects to `0.0.0.0`

If clicking a forward-auth-protected service (Longhorn, Hubble, Sympozium) redirects the browser to `http://0.0.0.0:9000/...` instead of `https://auth.frank.derio.net/...`:

The embedded outpost does not know its own external URL. Set `AUTHENTIK_HOST` in the Helm values:

```yaml
global:
  env:
    - name: AUTHENTIK_HOST
      value: "https://auth.frank.derio.net"
```

After updating `apps/authentik/values.yaml`, ArgoCD will sync the change. Verify with:

```bash
# Check that the env var is set on the server pods
kubectl get deploy -n authentik authentik-server \
  -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="AUTHENTIK_HOST")].value}'
# Expected: https://auth.frank.derio.net

# Test that forward-auth now redirects correctly
curl -sk -o /dev/null -w "%{redirect_url}\n" https://longhorn.frank.derio.net/
# Expected: https://auth.frank.derio.net/outpost.goauthentik.io/... (not 0.0.0.0)
```

### Forward Auth 403

```bash
# Check the forward auth outpost logs
kubectl logs -n authentik -l app.kubernetes.io/component=outpost --tail=50

# Verify the outpost can reach the Authentik server
kubectl exec -n authentik -l app.kubernetes.io/component=outpost -- \
  curl -s http://authentik-server.authentik.svc:9000/api/v3/root/config/
```

### Grafana Secret Key Mismatch

If Grafana shows "login error" after OIDC redirect:

```bash
# Verify the secret key name in the K8s Secret
kubectl get secret -n grafana grafana-oidc -o jsonpath='{.data}' | jq 'keys'

# Must contain: GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET
# NOT: client_secret or clientSecret
```

### Token Validation Failures

```bash
# Test the OIDC well-known endpoint
curl -s http://192.168.55.211:9000/application/o/<provider-slug>/.well-known/openid-configuration | jq

# Check token endpoint manually
curl -s -X POST http://192.168.55.211:9000/application/o/token/ \
  -d "grant_type=client_credentials&client_id=<id>&client_secret=<secret>"
```

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
- [Building Post — Unified Auth]({{< relref "/building/13-unified-auth" >}})
