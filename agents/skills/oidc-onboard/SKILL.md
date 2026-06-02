---
name: oidc-onboard
description: Onboard a Frank service to Authentik SSO via OIDC — blueprint, secret extraction, injection, verify
user-invocable: true
disable-model-invocation: false
arguments:
  - name: service
    description: Service slug (kebab-case, becomes the OIDC client_id, e.g. "grafana")
    required: true
  - name: inject-mode
    description: "config (app reads OIDC from its own values/env) or api (PATCH the app's settings API after boot, e.g. AWX)"
    required: false
    default: config
---

# Onboard a Service to Authentik SSO (OIDC)

Wire a new cluster service into Authentik as an OIDC client. This is the
**login-button** flow (the app delegates auth to Authentik). For services that
have no auth of their own and should sit behind Traefik forward-auth instead,
use `/expose-service` (proxy provider), not this skill.

> Read first: `agents/rules/frank-gotchas.md` → **Authentik** section, and
> `docs/runbooks/frank-gotchas/authentik.md` for the full prose + recovery.
> The forward-auth/outpost details live in `agents/rules/frank-argocd.md`.

## Steps

### 1. Create the provider+application blueprint

Copy the closest existing blueprint as a template — do **not** write one from
scratch:

- OIDC login app → `apps/authentik-extras/manifests/blueprints-provider-grafana.yaml`
  (or `-argocd`, `-awx`, `-infisical` — pick the one whose redirect/scope shape
  matches your service).

Create `apps/authentik-extras/manifests/blueprints-provider-$ARGUMENTS.service.yaml`
with the OAuth2 provider + `authentik_core.application`. Keep `client_id` equal
to `$ARGUMENTS.service`.

**2026.x schema requirements (enforced — silent failure if missing):**
- `redirect_uris` must be the **object list** form: `[{matching_mode: strict, url: ...}]`
- `invalidation_flow` is **required**
- `signing_key` must reference the bundled cert via `!Find` (never hardcode a UUID)

### 2. Register the blueprint ConfigMap

Blueprints mount in the **worker** pod. Add the new ConfigMap name to
`apps/authentik/values.yaml` → `blueprints.configMaps` (around line 73).
Forgetting this means the blueprint never applies.

### 3. Commit & let ArgoCD apply, then confirm the provider exists

```bash
git add apps/authentik/values.yaml apps/authentik-extras/manifests/blueprints-provider-$ARGUMENTS.service.yaml
git commit -m "auth(blueprint): add $ARGUMENTS.service OIDC provider"
# ArgoCD auto-syncs. Confirm the blueprint applied:
kubectl -n authentik logs deploy/authentik-worker | grep -i "$ARGUMENTS.service"
```

### 4. Extract the auto-generated client_secret

Authentik generates the secret; blueprints can't set it. Read it via the Django
ORM in the **worker** pod:

```bash
CLIENT_SECRET=$(kubectl exec -n authentik deploy/authentik-worker -- python -c '
import os; os.environ.setdefault("DJANGO_SETTINGS_MODULE","authentik.root.settings")
import django; django.setup()
from authentik.providers.oauth2.models import OAuth2Provider
print(OAuth2Provider.objects.get(client_id="'$ARGUMENTS.service'").client_secret)' 2>/dev/null)
echo "secret length = ${#CLIENT_SECRET}"
```

Empty/not-found ⇒ blueprint hasn't applied or its YAML is broken (re-check step 3 logs).

### 5. Store the secret (SOPS, applied out-of-band)

Per `repo-principles.md`, SOPS secrets are **not** ArgoCD-managed. Create
`secrets/authentik/$ARGUMENTS.service-oidc-secret.yaml` (a `kind: Secret` in the
target namespace), encrypt, and apply:

```bash
sops -e -i secrets/authentik/$ARGUMENTS.service-oidc-secret.yaml
sops --decrypt secrets/authentik/$ARGUMENTS.service-oidc-secret.yaml | kubectl apply -f -
```

Document this apply as a `# manual-operation` block in the plan (see
`repo-manual-ops.md`) and run `/sync-runbook`.

### 6. Inject the secret into the service

**`inject-mode=config`** (ArgoCD, Grafana, Infisical, Gitea, most apps):
the app reads OIDC from its own `apps/$ARGUMENTS.service/values.yaml`. Add the
issuer, client_id, scopes, and the secret reference. Copy the exact key/mechanism
from a working peer:
- ArgoCD: `$<secret>:<key>` injection in `configs.cm.oidc.config`
- Grafana: `envFromSecret`; **secret key must be `GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET`** (gotcha)
- Gitea: `gitea.oauth[].existingSecret` with `GITEA_OAUTH_<PROVIDER>_CLIENT_SECRET`

Confirm the discovery URL by matching a peer's values, not from memory:
`https://<authentik-host>/application/o/$ARGUMENTS.service/.well-known/openid-configuration`

**`inject-mode=api`** (AWX and other apps with no OIDC config file):
PATCH the app's settings API after the pod is up, using `$CLIENT_SECRET` from
step 4. Worked example for AWX (confirm the deploy/container/secret names against
the live app first):

```bash
ADMIN_PW=$(kubectl -n awx get secret awx-admin-password -o jsonpath='{.data.password}' | base64 -d)
# PATCH the OIDC settings category (payload via stdin so the secret isn't shell-escaped):
printf '{"SOCIAL_AUTH_OIDC_SECRET":"%s"}' "$CLIENT_SECRET" \
  | kubectl -n awx exec -i deploy/awx-web -c awx-web -- \
      curl -sk -u "admin:${ADMIN_PW}" -X PATCH http://localhost:8052/api/v2/settings/oidc/ \
        -H 'Content-Type: application/json' --data-binary @-
# verify — expect an $encrypted$-prefixed value back:
kubectl -n awx exec deploy/awx-web -c awx-web -- \
  curl -sk -u "admin:${ADMIN_PW}" http://localhost:8052/api/v2/settings/oidc/
```

The endpoint and setting key are app-specific — for a non-AWX app, find its OIDC
settings endpoint and secret field name in that app's API docs. (Keep any
throwaway helper under the gitignored `scripts/tmp/`; do not reference it from
this skill.)

### 7. Verify

- Discovery endpoint resolves: `curl -sk https://<authentik-host>/application/o/$ARGUMENTS.service/.well-known/openid-configuration | jq .issuer`
- App shows the Authentik login button / completes an OIDC round-trip
- `inject-mode=api`: re-read the setting (expect an `$encrypted$`-prefixed value)

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| No login button | blueprint applied but provider not wired into app | re-check step 6 injection; for proxy/forward-auth see `/expose-service` |
| `client_secret` empty in step 4 | ConfigMap not registered in `values.yaml` | step 2 |
| Provider not found / blueprint ignored | 2026.x schema (missing `invalidation_flow`, string `redirect_uris`) | step 1 schema rules |
| Forward-auth redirects to `0.0.0.0:9000` | embedded outpost missing `AUTHENTIK_HOST` | see `authentik.md` gotcha |

## Summary

Show the user: blueprint file created, `values.yaml` line added, where the SOPS
secret lives, the injection mechanism used, and the verification output. Remind
them to `/sync-runbook` for the manual secret-apply, and to `/expose-service`
if the app also needs an external hostname.
