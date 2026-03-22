# Auth Plan Audit + Missing Implementation

## Context

The Authentik plan (`docs/superpowers/plans/2026-03-11--auth--authentik.md`) says `Status: Deployed` but has **11 manual-operation blocks all `status: pending`**. Several declarative artifacts were also never created. Live cluster checks reveal the core is working but integration is incomplete.

## Live Cluster Audit Results

### Confirmed DONE (update status → `done`)

| Manual Op ID | Evidence |
|---|---|
| `auth-authentik-bootstrap-secrets` | Secret exists in `authentik` namespace |
| `auth-traefik-authentik-route` | `curl https://auth.frank.derio.net/` → 302 (working) |
| `auth-argocd-oidc-secret` | Secret exists in `argocd` namespace |
| `auth-grafana-oidc-secret` | Secret exists in `monitoring` namespace |

Also confirmed:
- Authentik pods healthy (2 server, 1 worker, 1 postgresql) — 6-10 days old
- LB at 192.168.55.211 active
- ArgoCD OIDC live in `argocd-cm` (issuer, clientID, scopes correct)
- OIDC discovery endpoint working
- Grafana OIDC config already in `apps/victoria-metrics/values.yaml` (envFromSecret, auth.generic_oauth)

### Confirmed NOT DONE

| Item | Evidence |
|---|---|
| `auth-infisical-oidc-config` (secret) | `infisical-oidc-secret` not in `infisical` namespace |
| `auth-agent-machine-user` (secret) | `k8s-agent-secret` not in `authentik` namespace |

### Cannot verify from CLI (need browser)

| Manual Op ID | What to check |
|---|---|
| `auth-akadmin-group` | Is akadmin in root-admins? |
| `auth-argocd-oidc-client-secret` | Does ArgoCD SSO login work? |
| `auth-grafana-oidc-client-secret` | Does Grafana SSO login work? |
| `auth-traefik-forward-auth` | Are Longhorn/Hubble/Sympozium behind auth? |
| `auth-talos-oidc-patch` | Is OIDC on kube-apiserver? (talosctl timed out) |

### Missing declarative artifacts (code never written)

| File | Purpose |
|---|---|
| `blueprints-provider-grafana.yaml` | Grafana OIDC provider in Authentik |
| `blueprints-provider-infisical.yaml` | Infisical OIDC provider in Authentik |
| `blueprints-proxy-providers.yaml` | Proxy auth for Longhorn/Hubble/Sympozium |
| `blueprints-agent-auth.yaml` | K8s agent OAuth2 provider |

---

## Implementation Plan

### Task 1: Update confirmed-done manual-op statuses

Update the 4 confirmed-done operations from `status: pending` → `status: done` in the plan file.

**File:** `docs/superpowers/plans/2026-03-11--auth--authentik.md`
- Line 147: `auth-authentik-bootstrap-secrets` → done
- Line 602: `auth-traefik-authentik-route` → done
- Line 692: `auth-argocd-oidc-secret` → done
- Line 900: `auth-grafana-oidc-secret` → done

### Task 2: Change plan Status header

**File:** `docs/superpowers/plans/2026-03-11--auth--authentik.md` line 12
- Change `**Status:** Deployed` → `**Status:** Partial`

### Task 3: Create Grafana OIDC provider blueprint

The Grafana values are already configured in `apps/victoria-metrics/values.yaml` (envFromSecret, auth.generic_oauth). What's missing is the Authentik-side blueprint.

**Create:** `apps/authentik-extras/manifests/blueprints-provider-grafana.yaml`
- Model from plan lines 907-953 (OAuth2 provider + application)
- Follow ArgoCD blueprint pattern exactly

**Modify:** `apps/authentik/values.yaml` — add `authentik-blueprints-provider-grafana` to `blueprints.configMaps` list

### Task 4: Create Infisical OIDC provider blueprint

**Create:** `apps/authentik-extras/manifests/blueprints-provider-infisical.yaml`
- Model from plan lines 1047-1092

**Modify:** `apps/authentik/values.yaml` — add `authentik-blueprints-provider-infisical` to `blueprints.configMaps` list

Note: The SOPS secret exists at `secrets/authentik/infisical-oidc-secret.yaml` but hasn't been applied. The manual-op `auth-infisical-oidc-config` covers both applying the secret AND configuring Infisical's admin UI — that remains manual.

### Task 5: Create proxy outpost blueprints

**Create:** `apps/authentik-extras/manifests/blueprints-proxy-providers.yaml`
- Model from plan lines 1196-1277
- Proxy providers for Longhorn, Hubble, Sympozium using `forward_single` mode

**Modify:** `apps/authentik/values.yaml` — add `authentik-blueprints-proxy-providers` to `blueprints.configMaps` list

Note: The Traefik forward-auth middleware config on raspi-omni remains a manual operation.

### Task 6: Create agent auth blueprint

**Create:** `apps/authentik-extras/manifests/blueprints-agent-auth.yaml`
- Model from plan lines 1335-1384
- OAuth2 provider for k8s-agent with 8-hour token validity

**Modify:** `apps/authentik/values.yaml` — add `authentik-blueprints-agent-auth` to `blueprints.configMaps` list

Note: Machine user creation + client secret + `.env_agent` remain manual operations.

### Task 7: Sync runbook

Run `/sync-runbook` to update `docs/runbooks/manual-operations.yaml` with corrected statuses.

---

## Key files

- `docs/superpowers/plans/2026-03-11--auth--authentik.md` — Plan file (status updates)
- `apps/authentik/values.yaml` — Blueprint ConfigMap references
- `apps/authentik-extras/manifests/` — New blueprint files (4 new)
- `apps/victoria-metrics/values.yaml` — Grafana OIDC config (already done, no changes needed)
- `docs/runbooks/manual-operations.yaml` — Runbook sync target

## Verification

After implementation:
1. `kubectl get cm -n authentik -l app.kubernetes.io/component=blueprint` — should show all 6 ConfigMaps
2. ArgoCD sync: `argocd app sync authentik-extras --port-forward --port-forward-namespace argocd`
3. Check blueprint processing: `kubectl logs -n authentik -l app.kubernetes.io/component=worker --tail=50 | grep -i blueprint`
4. Verify Authentik admin shows new providers/applications (browser check)

## Remaining manual operations after this work

These stay `status: pending` — they require browser/UI/SSH access:
- `auth-akadmin-group` — akadmin → root-admins assignment
- `auth-argocd-oidc-client-secret` — Set ArgoCD client secret in Authentik UI
- `auth-grafana-oidc-client-secret` — Set Grafana client secret in Authentik UI
- `auth-infisical-oidc-config` — Apply SOPS secret + configure both UIs
- `auth-traefik-forward-auth` — Configure Traefik middleware on raspi-omni
- `auth-agent-machine-user` — Create service account in Authentik UI
- `auth-talos-oidc-patch` — Apply OIDC patch via Omni
