# Phase XX — Unified Authentication & Authorization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy Authentik as the cluster identity provider with OIDC SSO for ArgoCD/Grafana/Infisical, proxy outpost for Longhorn/Hubble/Sympozium, agent auth via client credentials, and org-based group hierarchy.

**Architecture:** Three ArgoCD apps — `authentik` (Helm, core server + worker + PostgreSQL), `authentik-extras` (raw manifests, LB Service + blueprint ConfigMaps + outpost config). Secrets bootstrapped via SOPS out-of-band. Declarative blueprints define groups, OIDC providers, proxy providers, and applications. Traefik on raspi-omni provides TLS termination via `*.frank.derio.net` wildcard cert.

**Tech Stack:** Authentik 2026.2.1 Helm chart, PostgreSQL 17 (bundled subchart), Cilium L2 LoadBalancer (192.168.55.211), SOPS/age secrets, Authentik blueprints (YAML).

**Design doc:** `docs/superpowers/specs/2026-03-11-unified-auth-design.md`

---

## Chunk 1: Core Deployment (Tasks 1-5)

### Task 1: Research Authentik Helm Chart

Before creating any files, research the chart to confirm values structure and version.

- [ ] **Step 1: Add Authentik Helm repo and inspect chart**

```bash
helm repo add authentik https://charts.goauthentik.io
helm repo update
helm search repo authentik/authentik --versions | head -5
```

Expected: shows `authentik/authentik` with latest version `2026.2.1` (or newer).

- [ ] **Step 2: Inspect default values**

```bash
helm show values authentik/authentik > /tmp/authentik-values-full.yaml
```

Review `/tmp/authentik-values-full.yaml` to confirm:
- `authentik.secret_key` path exists
- `postgresql.enabled` defaults to `false` (needs explicit enable)
- `server.replicas`, `server.tolerations`, `server.env` paths exist
- `worker.replicas`, `worker.tolerations`, `worker.env` paths exist
- `blueprints.configMaps` path exists
- `server.service.type` defaults to `ClusterIP`

- [ ] **Step 3: Check subchart behavior**

Verify whether the bundled PostgreSQL subchart has the same env var collision bug as Infisical's chart. Check if enabling `postgresql.enabled: true` alongside `server.env` for `AUTHENTIK_POSTGRESQL__PASSWORD` causes duplicate env injection.

If collision exists: adopt split-app pattern (separate `authentik-postgresql` ArgoCD app).
If no collision: use bundled subchart with `ignoreDifferences` on auto-generated secrets.

Document finding in a comment in `apps/authentik/values.yaml`.

---

### Task 2: Create SOPS-Encrypted Bootstrap Secrets

Create the Kubernetes secrets Authentik needs before it can start. These are applied out-of-band.

**Files:**
- Create: `secrets/authentik/authentik-secrets.yaml` (SOPS-encrypted)

- [ ] **Step 1: Generate secret values**

```bash
# Generate a 50-char random secret key
AUTHENTIK_SECRET_KEY=$(openssl rand -base64 50 | tr -d '\n' | head -c 50)
# Generate PostgreSQL password
AUTHENTIK_PG_PASSWORD=$(openssl rand -base64 32 | tr -d '\n' | head -c 32)
# Generate bootstrap admin password
AUTHENTIK_BOOTSTRAP_PASSWORD=$(openssl rand -base64 32 | tr -d '\n' | head -c 32)

echo "Secret Key: $AUTHENTIK_SECRET_KEY"
echo "PG Password: $AUTHENTIK_PG_PASSWORD"
echo "Bootstrap Password: $AUTHENTIK_BOOTSTRAP_PASSWORD"
```

**Save these values securely — you'll need them in the next step.**

- [ ] **Step 2: Create the Kubernetes Secret manifest**

Create `secrets/authentik/authentik-secrets.yaml` (plaintext, will encrypt next):

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: authentik-secrets
  namespace: authentik
type: Opaque
stringData:
  secret_key: "<AUTHENTIK_SECRET_KEY>"
  postgresql_password: "<AUTHENTIK_PG_PASSWORD>"
  bootstrap_password: "<AUTHENTIK_BOOTSTRAP_PASSWORD>"
```

Replace the placeholders with the generated values from Step 1.

- [ ] **Step 3: Encrypt with SOPS**

```bash
cd /Users/idermitzakis/Docs/projects/HOMELAB/frank-cluster
sops --encrypt --in-place secrets/authentik/authentik-secrets.yaml
```

Verify encryption:
```bash
head -20 secrets/authentik/authentik-secrets.yaml
```

Expected: `data` or `stringData` values are encrypted, metadata is readable.

- [ ] **Step 4: Apply the secret to the cluster**

```bash
sops --decrypt secrets/authentik/authentik-secrets.yaml | kubectl apply -f -
```

Verify:
```bash
kubectl get secret authentik-secrets -n authentik
```

Note: The `authentik` namespace must be created first (via the namespace manifest from Task 2a), then secrets applied:
```bash
kubectl apply -f apps/root/templates/ns-authentik.yaml
sops --decrypt secrets/authentik/authentik-secrets.yaml | kubectl apply -f -
kubectl get secret authentik-secrets -n authentik
```

Expected: `secret/authentik-secrets created`

```yaml
# manual-operation
id: phase13-authentik-bootstrap-secrets
phase: XX
app: authentik
plan: docs/plans/2026-03-11-phase13-unified-auth.md
when: "Before Task 3 — secrets must exist before Authentik pods start"
why_manual: "SOPS-encrypted secrets cannot be applied via ArgoCD (SOPS + ServerSideApply don't mix)"
commands:
  - kubectl apply -f apps/root/templates/ns-authentik.yaml
  - sops --decrypt secrets/authentik/authentik-secrets.yaml | kubectl apply -f -
verify:
  - kubectl get secret authentik-secrets -n authentik -o jsonpath='{.data.secret_key}' | base64 -d | head -c 5 && echo '...'
status: pending
```

- [ ] **Step 5: Commit encrypted secrets**

```bash
git add secrets/authentik/authentik-secrets.yaml
git commit -m "feat(phase13): add SOPS-encrypted Authentik bootstrap secrets

Contains: secret_key, postgresql_password, bootstrap_password.
Applied out-of-band before ArgoCD sync."
```

---

### Task 2a: Create Authentik Namespace Manifest

Create a declarative namespace manifest, consistent with other apps (infisical, longhorn).

**Files:**
- Create: `apps/root/templates/ns-authentik.yaml`

- [ ] **Step 1: Create namespace manifest**

Create `apps/root/templates/ns-authentik.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: authentik
  labels:
    pod-security.kubernetes.io/enforce: privileged
```

- [ ] **Step 2: Commit**

```bash
git add apps/root/templates/ns-authentik.yaml
git commit -m "feat(phase13): add Authentik namespace manifest

Declarative namespace with pod-security labels, applied before
SOPS secrets and ArgoCD app sync."
```

---

### Task 3: Create Authentik ArgoCD Application

Deploy Authentik server + worker + PostgreSQL via the official Helm chart.

**Files:**
- Create: `apps/authentik/values.yaml`
- Create: `apps/root/templates/authentik.yaml`

- [ ] **Step 1: Create Authentik Helm values**

Create `apps/authentik/values.yaml`:

```yaml
# Authentik — Identity Provider for Frank Cluster
# Phase XX: Unified Authentication & Authorization
# Chart: goauthentik/authentik (https://charts.goauthentik.io)
#
# Secrets are injected via env vars from SOPS-bootstrapped K8s Secret
# (secrets/authentik/authentik-secrets.yaml, applied out-of-band).
# Bundled PostgreSQL subchart is used (no env var collision detected).
# If collision is found during Task 1 research, split into separate app.

# -- Authentik core configuration
authentik:
  # secret_key injected via env var AUTHENTIK_SECRET_KEY from Secret
  secret_key: ""
  log_level: info
  error_reporting:
    enabled: false

# -- Server (Django web app + OIDC provider)
server:
  replicas: 2
  tolerations:
    - key: node-role.kubernetes.io/control-plane
      effect: NoSchedule
  nodeSelector:
    node-role.kubernetes.io/control-plane: ""
  env:
    - name: AUTHENTIK_SECRET_KEY
      valueFrom:
        secretKeyRef:
          name: authentik-secrets
          key: secret_key
    - name: AUTHENTIK_POSTGRESQL__PASSWORD
      valueFrom:
        secretKeyRef:
          name: authentik-secrets
          key: postgresql_password
    - name: AUTHENTIK_BOOTSTRAP_PASSWORD
      valueFrom:
        secretKeyRef:
          name: authentik-secrets
          key: bootstrap_password
  service:
    type: ClusterIP
  metrics:
    enabled: true
    serviceMonitor:
      enabled: false  # Enable after Prometheus is deployed

# -- Worker (background tasks, blueprint processing)
worker:
  replicas: 1
  tolerations:
    - key: node-role.kubernetes.io/control-plane
      effect: NoSchedule
  nodeSelector:
    node-role.kubernetes.io/control-plane: ""
  env:
    - name: AUTHENTIK_SECRET_KEY
      valueFrom:
        secretKeyRef:
          name: authentik-secrets
          key: secret_key
    - name: AUTHENTIK_POSTGRESQL__PASSWORD
      valueFrom:
        secretKeyRef:
          name: authentik-secrets
          key: postgresql_password

# -- Blueprints (declarative config, mounted from ConfigMaps)
# ConfigMaps are created by authentik-extras app
blueprints:
  configMaps:
    - authentik-blueprints-groups

# -- Bundled PostgreSQL subchart
# Production note: Authentik docs recommend external PostgreSQL for production.
# For homelab use, the bundled subchart with Longhorn persistence is acceptable.
postgresql:
  enabled: true
  auth:
    username: authentik
    database: authentik
    existingSecret: authentik-secrets
    secretKeys:
      userPasswordKey: postgresql_password
  primary:
    tolerations:
      - key: node-role.kubernetes.io/control-plane
        effect: NoSchedule
    nodeSelector:
      node-role.kubernetes.io/control-plane: ""
    persistence:
      enabled: true
      storageClass: longhorn
      size: 8Gi

# -- Redis (bundled via chart dependency)
# Authentik chart bundles Redis for caching and task queuing.
# No authentication configured (cluster-internal only).
redis:
  enabled: true
  master:
    tolerations:
      - key: node-role.kubernetes.io/control-plane
        effect: NoSchedule
    nodeSelector:
      node-role.kubernetes.io/control-plane: ""
    persistence:
      enabled: true
      storageClass: longhorn
      size: 2Gi
```

- [ ] **Step 2: Create Authentik Application CR**

Create `apps/root/templates/authentik.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: authentik
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://charts.goauthentik.io
      chart: authentik
      targetRevision: "2026.2.1"
      helm:
        releaseName: authentik
        valueFiles:
          - $values/apps/authentik/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: authentik
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      name: authentik-secrets
      namespace: authentik
      jsonPointers:
        - /data
    # Scope to specific auto-generated secrets after Task 1 research.
    # Add entries for PostgreSQL and Redis auto-generated secrets here.
```

- [ ] **Step 3: Commit**

```bash
git add apps/authentik/values.yaml apps/root/templates/authentik.yaml
git commit -m "feat(phase13): add Authentik ArgoCD application

Deploys Authentik server (2 replicas), worker, bundled PostgreSQL + Redis.
Secrets injected from SOPS-bootstrapped K8s Secret via env vars.
Scheduled on control-plane nodes with tolerations."
```

---

### Task 4: Create Authentik Extras (LoadBalancer + Blueprints)

Deploy supplementary resources: LoadBalancer Service, blueprint ConfigMaps.

**Files:**
- Create: `apps/authentik-extras/manifests/lb-service.yaml`
- Create: `apps/authentik-extras/manifests/blueprints-groups.yaml`
- Create: `apps/authentik-extras/manifests/blueprints-flows.yaml`
- Create: `apps/root/templates/authentik-extras.yaml`

- [ ] **Step 1: Create LoadBalancer Service**

Create `apps/authentik-extras/manifests/lb-service.yaml`:

```yaml
# LoadBalancer Service for Authentik UI + OIDC endpoint
# Exposed at auth.frank.derio.net via Traefik on raspi-omni
apiVersion: v1
kind: Service
metadata:
  name: authentik-server-lb
  namespace: authentik
  annotations:
    lbipam.cilium.io/ips: "192.168.55.211"
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/name: authentik
    app.kubernetes.io/component: server
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
    - name: https
      port: 443
      targetPort: https
      protocol: TCP
```

- [ ] **Step 2: Create groups blueprint ConfigMap**

Create `apps/authentik-extras/manifests/blueprints-groups.yaml`:

```yaml
# Authentik Blueprint: Organization Groups
# Defines the root organization's group hierarchy.
# Groups use org-aware naming for future multi-org support (Phase 12).
apiVersion: v1
kind: ConfigMap
metadata:
  name: authentik-blueprints-groups
  namespace: authentik
  labels:
    app.kubernetes.io/component: blueprint
data:
  groups.yaml: |
    # yaml-language-server: $schema=https://goauthentik.io/blueprints/schema.json
    version: 1
    metadata:
      name: Root Organization Groups
      labels:
        blueprints.goauthentik.io/instantiate: "true"
    entries:
      # Root organization parent group
      - model: authentik_core.group
        state: present
        identifiers:
          name: root
        id: group-root
        attrs:
          is_superuser: false

      # Root organization roles
      - model: authentik_core.group
        state: present
        identifiers:
          name: root-admins
        attrs:
          is_superuser: true
          parent: !KeyOf group-root

      - model: authentik_core.group
        state: present
        identifiers:
          name: root-devops
        attrs:
          is_superuser: false
          parent: !KeyOf group-root

      - model: authentik_core.group
        state: present
        identifiers:
          name: root-developers
        attrs:
          is_superuser: false
          parent: !KeyOf group-root

      - model: authentik_core.group
        state: present
        identifiers:
          name: root-agents
        attrs:
          is_superuser: false
          parent: !KeyOf group-root
```

Note: Authentik ships with default authentication and authorization flows out of the box. We don't need custom flow blueprints for the initial deployment — the defaults work for username/password + OIDC. Custom flows (e.g., MFA enrollment) can be added later as additional blueprint ConfigMaps.

- [ ] **Step 3: Create authentik-extras Application CR**

Create `apps/root/templates/authentik-extras.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: authentik-extras
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/authentik-extras/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: authentik
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

- [ ] **Step 5: Commit**

```bash
git add apps/authentik-extras/ apps/root/templates/authentik-extras.yaml
git commit -m "feat(phase13): add Authentik extras (LB service + blueprints)

LoadBalancer at 192.168.55.211 for auth.frank.derio.net.
Blueprint ConfigMaps define root org groups (admins, devops,
developers, agents) with nested group hierarchy."
```

---

### Task 5: Deploy and Verify Authentik

Push changes and verify Authentik comes up correctly.

- [ ] **Step 1: Push to remote**

```bash
git push origin main
```

- [ ] **Step 2: Sync ArgoCD root app**

```bash
argocd app sync root --port-forward --port-forward-namespace argocd
```

Wait for sync:
```bash
argocd app list --port-forward --port-forward-namespace argocd | grep authentik
```

Expected: `authentik` and `authentik-extras` both show `Synced` / `Healthy`.

- [ ] **Step 3: Verify pods are running**

```bash
kubectl get pods -n authentik
```

Expected output (names will vary):
```
authentik-server-xxx-xxx       1/1     Running
authentik-server-xxx-xxx       1/1     Running
authentik-worker-xxx-xxx       1/1     Running
authentik-postgresql-0         1/1     Running
authentik-redis-master-0       1/1     Running
```

- [ ] **Step 4: Verify LoadBalancer**

```bash
kubectl get svc -n authentik | grep LoadBalancer
```

Expected: `authentik-server-lb` with `EXTERNAL-IP` `192.168.55.211`.

- [ ] **Step 5: Add Traefik route on raspi-omni**

Add to the Traefik config on raspi-omni:

```yaml
authentik:
  cilium_ip: "192.168.55.211"
  port: 80
  url: "auth.frank.derio.net"
```

```yaml
# manual-operation
id: phase13-traefik-authentik-route
phase: XX
app: authentik
plan: docs/plans/2026-03-11-phase13-unified-auth.md
when: "After Task 5 Step 4 — LB service has external IP"
why_manual: "Traefik config on raspi-omni is outside cluster management"
commands:
  - "Add authentik entry to Traefik config on raspi-omni: cilium_ip 192.168.55.211, port 80, url auth.frank.derio.net"
  - "Restart Traefik on raspi-omni"
verify:
  - "curl -s https://auth.frank.derio.net/if/flow/initial-setup/ | grep -i authentik"
status: pending
```

- [ ] **Step 6: Access Authentik initial setup**

Navigate to `https://auth.frank.derio.net/if/flow/initial-setup/` in a browser.

Log in with:
- Username: `akadmin`
- Password: the `bootstrap_password` value from Step 2

Verify:
- Authentik admin dashboard loads
- Groups `root`, `root-admins`, `root-devops`, `root-developers`, `root-agents` exist (check Admin > Directory > Groups)
- `akadmin` user exists

- [ ] **Step 7: Add akadmin to root-admins group**

In Authentik Admin UI:
1. Go to Directory > Users > `akadmin`
2. Edit > Groups tab > Add to `root-admins`

```yaml
# manual-operation
id: phase13-akadmin-group
phase: XX
app: authentik
plan: docs/plans/2026-03-11-phase13-unified-auth.md
when: "After Task 5 Step 6 — Authentik initial setup complete"
why_manual: "Bootstrap user assignment cannot be done via blueprint (user doesn't exist until first login)"
commands:
  - "In Authentik Admin UI: Directory > Users > akadmin > Groups > Add to root-admins"
verify:
  - "In Authentik Admin UI: Directory > Users > akadmin shows root-admins group membership"
status: pending
```

---

## Chunk 2: Service SSO — ArgoCD (Task 6)

### Task 6: ArgoCD OIDC Integration with Authentik

Configure ArgoCD to use Authentik as its OIDC provider, replacing the built-in Dex.

**Files:**
- Create: `apps/authentik-extras/manifests/blueprints-provider-argocd.yaml`
- Create: `secrets/authentik/argocd-oidc-secret.yaml` (SOPS-encrypted)
- Modify: `apps/argocd/values.yaml` (add OIDC config)

- [ ] **Step 1: Create OIDC client secret for ArgoCD**

```bash
ARGOCD_CLIENT_SECRET=$(openssl rand -base64 32 | tr -d '\n' | head -c 32)
echo "ArgoCD Client Secret: $ARGOCD_CLIENT_SECRET"
```

Create `secrets/authentik/argocd-oidc-secret.yaml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: argocd-oidc-secret
  namespace: argocd
  labels:
    app.kubernetes.io/part-of: argocd
type: Opaque
stringData:
  oidc.authentik.clientSecret: "<ARGOCD_CLIENT_SECRET>"
```

Encrypt and apply:
```bash
sops --encrypt --in-place secrets/authentik/argocd-oidc-secret.yaml
sops --decrypt secrets/authentik/argocd-oidc-secret.yaml | kubectl apply -f -
```

```yaml
# manual-operation
id: phase13-argocd-oidc-secret
phase: XX
app: argocd
plan: docs/plans/2026-03-11-phase13-unified-auth.md
when: "Before Task 6 Step 3 — ArgoCD needs the OIDC secret before OIDC is enabled"
why_manual: "SOPS-encrypted secret applied out-of-band"
commands:
  - sops --decrypt secrets/authentik/argocd-oidc-secret.yaml | kubectl apply -f -
verify:
  - kubectl get secret argocd-oidc-secret -n argocd
status: pending
```

- [ ] **Step 2: Create Authentik OIDC provider blueprint for ArgoCD**

Create `apps/authentik-extras/manifests/blueprints-provider-argocd.yaml`:

```yaml
# Authentik Blueprint: ArgoCD OIDC Provider
# Creates an OAuth2 provider and application entry for ArgoCD SSO.
apiVersion: v1
kind: ConfigMap
metadata:
  name: authentik-blueprints-provider-argocd
  namespace: authentik
  labels:
    app.kubernetes.io/component: blueprint
data:
  provider-argocd.yaml: |
    # yaml-language-server: $schema=https://goauthentik.io/blueprints/schema.json
    version: 1
    metadata:
      name: ArgoCD OIDC Provider
      labels:
        blueprints.goauthentik.io/instantiate: "true"
    entries:
      # OAuth2 Provider for ArgoCD
      - model: authentik_providers_oauth2.oauth2provider
        state: present
        identifiers:
          name: ArgoCD
        id: provider-argocd
        attrs:
          authorization_flow: !Find [authentik_flows.flow, [slug, default-provider-authorization-implicit-consent]]
          authentication_flow: !Find [authentik_flows.flow, [slug, default-authentication-flow]]
          client_type: confidential
          client_id: argocd
          # client_secret is set manually in Authentik UI (from SOPS secret)
          redirect_uris: |
            https://argocd.frank.derio.net/auth/callback
            https://argocd.frank.derio.net/api/dex/callback
          signing_key: !Find [authentik_crypto.certificatekeypair, [name, authentik Self-signed Certificate]]
          property_mappings:
            - !Find [authentik_providers_oauth2.scopemapping, [scope_name, openid]]
            - !Find [authentik_providers_oauth2.scopemapping, [scope_name, email]]
            - !Find [authentik_providers_oauth2.scopemapping, [scope_name, profile]]
            - !Find [authentik_providers_oauth2.scopemapping, [scope_name, offline_access]]
          sub_mode: hashed_user_id
          include_claims_in_id_token: true
          access_token_validity: hours=1

      # Application entry
      - model: authentik_core.application
        state: present
        identifiers:
          slug: argocd
        attrs:
          name: ArgoCD
          provider: !KeyOf provider-argocd
          meta_launch_url: https://argocd.frank.derio.net
```

- [ ] **Step 3: Update authentik values to include new blueprint ConfigMap**

Modify `apps/authentik/values.yaml` — add the new ConfigMap to the blueprints list:

```yaml
blueprints:
  configMaps:
    - authentik-blueprints-groups
    - authentik-blueprints-provider-argocd
```

- [ ] **Step 4: Update ArgoCD values for OIDC**

Modify `apps/argocd/values.yaml` to add OIDC configuration. Add under the `configs` section (or create it if it doesn't exist):

```yaml
configs:
  cm:
    # Dex is already disabled (dex.enabled: false in existing values).
    # Configure Authentik OIDC directly.
    url: https://argocd.frank.derio.net
    oidc.config: |
      name: Authentik
      issuer: https://auth.frank.derio.net/application/o/argocd/
      clientID: argocd
      clientSecret: $argocd-oidc-secret:oidc.authentik.clientSecret
      requestedScopes:
        - openid
        - profile
        - email
        - groups
        - offline_access
  rbac:
    policy.csv: |
      g, root-admins, role:admin
      g, root-devops, role:admin
      g, root-developers, role:readonly
    policy.default: role:readonly
    scopes: "[groups]"
```

- [ ] **Step 5: Set the client_secret in Authentik UI**

After the blueprint creates the ArgoCD provider, set the client secret manually:

1. In Authentik Admin UI: Applications > Providers > ArgoCD
2. Edit > Client Secret > paste the `ARGOCD_CLIENT_SECRET` value
3. Save

```yaml
# manual-operation
id: phase13-argocd-oidc-client-secret
phase: XX
app: authentik
plan: docs/plans/2026-03-11-phase13-unified-auth.md
when: "After Task 6 Step 4 — Blueprint has created the ArgoCD provider"
why_manual: "Client secret cannot be set via blueprint (secret value must not be in Git)"
commands:
  - "In Authentik Admin UI: Applications > Providers > ArgoCD > Edit > set Client Secret from SOPS secret value"
verify:
  - "In Authentik Admin UI: Providers > ArgoCD shows client_secret is set (not empty)"
status: pending
```

- [ ] **Step 6: Commit and deploy**

```bash
git add apps/authentik-extras/manifests/blueprints-provider-argocd.yaml \
        apps/authentik/values.yaml \
        apps/argocd/values.yaml \
        secrets/authentik/argocd-oidc-secret.yaml
git commit -m "feat(phase13): integrate ArgoCD with Authentik OIDC

Blueprint creates OAuth2 provider + application for ArgoCD.
ArgoCD config switches from Dex to Authentik OIDC.
RBAC: root-admins=admin, root-devops=admin, root-developers=readonly."
```

- [ ] **Step 7: Verify ArgoCD OIDC login**

After sync:
1. Navigate to `https://argocd.frank.derio.net`
2. Click "Log in via Authentik"
3. Log in with `akadmin` credentials
4. Verify admin access to ArgoCD

---

## Chunk 3: Service SSO — Grafana + Infisical (Tasks 7-8)

### Task 7: Grafana OIDC Integration with Authentik

**Files:**
- Create: `apps/authentik-extras/manifests/blueprints-provider-grafana.yaml`
- Create: `secrets/authentik/grafana-oidc-secret.yaml` (SOPS-encrypted)
- Modify: `apps/grafana/values.yaml` (or observability stack values — research actual path)

- [ ] **Step 1: Research current Grafana deployment**

Check how Grafana is deployed:
```bash
ls apps/ | grep -i graf
ls apps/ | grep -i monitor
ls apps/ | grep -i observ
```

Read the Grafana values file and Application CR to understand the current configuration. Grafana may be deployed as part of a kube-prometheus-stack or standalone.

- [ ] **Step 2: Generate OIDC client secret for Grafana**

```bash
GRAFANA_CLIENT_SECRET=$(openssl rand -base64 32 | tr -d '\n' | head -c 32)
echo "Grafana Client Secret: $GRAFANA_CLIENT_SECRET"
```

Create `secrets/authentik/grafana-oidc-secret.yaml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: grafana-oidc-secret
  namespace: monitoring
type: Opaque
stringData:
  client_secret: "<GRAFANA_CLIENT_SECRET>"
```

Encrypt and apply:
```bash
sops --encrypt --in-place secrets/authentik/grafana-oidc-secret.yaml
sops --decrypt secrets/authentik/grafana-oidc-secret.yaml | kubectl apply -f -
```

```yaml
# manual-operation
id: phase13-grafana-oidc-secret
phase: XX
app: grafana
plan: docs/plans/2026-03-11-phase13-unified-auth.md
when: "Before Task 7 Step 4 — Grafana needs OIDC secret"
why_manual: "SOPS-encrypted secret applied out-of-band"
commands:
  - sops --decrypt secrets/authentik/grafana-oidc-secret.yaml | kubectl apply -f -
verify:
  - kubectl get secret grafana-oidc-secret -n monitoring
status: pending
```

- [ ] **Step 3: Create Authentik OIDC provider blueprint for Grafana**

Create `apps/authentik-extras/manifests/blueprints-provider-grafana.yaml`:

```yaml
# Authentik Blueprint: Grafana OIDC Provider
apiVersion: v1
kind: ConfigMap
metadata:
  name: authentik-blueprints-provider-grafana
  namespace: authentik
  labels:
    app.kubernetes.io/component: blueprint
data:
  provider-grafana.yaml: |
    # yaml-language-server: $schema=https://goauthentik.io/blueprints/schema.json
    version: 1
    metadata:
      name: Grafana OIDC Provider
      labels:
        blueprints.goauthentik.io/instantiate: "true"
    entries:
      - model: authentik_providers_oauth2.oauth2provider
        state: present
        identifiers:
          name: Grafana
        id: provider-grafana
        attrs:
          authorization_flow: !Find [authentik_flows.flow, [slug, default-provider-authorization-implicit-consent]]
          authentication_flow: !Find [authentik_flows.flow, [slug, default-authentication-flow]]
          client_type: confidential
          client_id: grafana
          redirect_uris: |
            https://grafana.frank.derio.net/login/generic_oauth
          signing_key: !Find [authentik_crypto.certificatekeypair, [name, authentik Self-signed Certificate]]
          property_mappings:
            - !Find [authentik_providers_oauth2.scopemapping, [scope_name, openid]]
            - !Find [authentik_providers_oauth2.scopemapping, [scope_name, email]]
            - !Find [authentik_providers_oauth2.scopemapping, [scope_name, profile]]
            - !Find [authentik_providers_oauth2.scopemapping, [scope_name, offline_access]]
          sub_mode: hashed_user_id
          include_claims_in_id_token: true

      - model: authentik_core.application
        state: present
        identifiers:
          slug: grafana
        attrs:
          name: Grafana
          provider: !KeyOf provider-grafana
          meta_launch_url: https://grafana.frank.derio.net
```

- [ ] **Step 4: Update Grafana values for OIDC**

Add to Grafana's values (exact path depends on Step 1 research):

```yaml
grafana:
  grafana.ini:
    server:
      root_url: https://grafana.frank.derio.net
    auth.generic_oauth:
      enabled: true
      name: Authentik
      client_id: grafana
      client_secret: ${GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET}
      scopes: openid profile email offline_access
      auth_url: https://auth.frank.derio.net/application/o/authorize/
      token_url: https://auth.frank.derio.net/application/o/token/
      api_url: https://auth.frank.derio.net/application/o/userinfo/
      role_attribute_path: "contains(groups[*], 'root-admins') && 'Admin' || contains(groups[*], 'root-devops') && 'Editor' || 'Viewer'"
      allow_assign_grafana_admin: true
  envFromSecrets:
    - name: grafana-oidc-secret
      optional: false
  env:
    GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET:
      valueFrom:
        secretKeyRef:
          name: grafana-oidc-secret
          key: client_secret
```

Note: The exact YAML structure depends on whether Grafana is standalone or part of kube-prometheus-stack. Adjust paths accordingly during implementation.

- [ ] **Step 5: Update authentik values with new blueprint ConfigMap**

Add to `apps/authentik/values.yaml` blueprints list:
```yaml
    - authentik-blueprints-provider-grafana
```

- [ ] **Step 6: Set client secret in Authentik UI and commit**

Same process as ArgoCD (Task 6 Step 5): set the Grafana client secret in the Authentik provider via the admin UI.

```yaml
# manual-operation
id: phase13-grafana-oidc-client-secret
phase: XX
app: authentik
plan: docs/plans/2026-03-11-phase13-unified-auth.md
when: "After Task 7 Step 5 — Blueprint has created the Grafana provider"
why_manual: "Client secret cannot be set via blueprint"
commands:
  - "In Authentik Admin UI: Applications > Providers > Grafana > Edit > set Client Secret"
verify:
  - "Navigate to https://grafana.frank.derio.net, click 'Sign in with Authentik', login as akadmin"
status: pending
```

```bash
git add apps/authentik-extras/manifests/blueprints-provider-grafana.yaml \
        apps/authentik/values.yaml \
        secrets/authentik/grafana-oidc-secret.yaml
git commit -m "feat(phase13): integrate Grafana with Authentik OIDC

Blueprint creates OAuth2 provider for Grafana.
Role mapping: root-admins=Admin, root-devops=Editor, others=Viewer."
```

Note: Grafana values changes need to be committed separately once the exact file path is confirmed.

---

### Task 8: Infisical OIDC Integration with Authentik

**Files:**
- Create: `apps/authentik-extras/manifests/blueprints-provider-infisical.yaml`

- [ ] **Step 1: Research Infisical OIDC support**

Check Infisical's docs for OIDC/SSO configuration. Infisical supports OIDC but configuration may be done via the Infisical admin UI rather than Helm values.

```bash
grep -r "oidc\|oauth\|sso\|saml" apps/infisical/ --include="*.yaml" -i
```

- [ ] **Step 2: Create Authentik OIDC provider blueprint for Infisical**

Create `apps/authentik-extras/manifests/blueprints-provider-infisical.yaml`:

```yaml
# Authentik Blueprint: Infisical OIDC Provider
apiVersion: v1
kind: ConfigMap
metadata:
  name: authentik-blueprints-provider-infisical
  namespace: authentik
  labels:
    app.kubernetes.io/component: blueprint
data:
  provider-infisical.yaml: |
    # yaml-language-server: $schema=https://goauthentik.io/blueprints/schema.json
    version: 1
    metadata:
      name: Infisical OIDC Provider
      labels:
        blueprints.goauthentik.io/instantiate: "true"
    entries:
      - model: authentik_providers_oauth2.oauth2provider
        state: present
        identifiers:
          name: Infisical
        id: provider-infisical
        attrs:
          authorization_flow: !Find [authentik_flows.flow, [slug, default-provider-authorization-implicit-consent]]
          authentication_flow: !Find [authentik_flows.flow, [slug, default-authentication-flow]]
          client_type: confidential
          client_id: infisical
          redirect_uris: |
            https://infisical.frank.derio.net/api/v1/sso/oidc/callback
          signing_key: !Find [authentik_crypto.certificatekeypair, [name, authentik Self-signed Certificate]]
          property_mappings:
            - !Find [authentik_providers_oauth2.scopemapping, [scope_name, openid]]
            - !Find [authentik_providers_oauth2.scopemapping, [scope_name, email]]
            - !Find [authentik_providers_oauth2.scopemapping, [scope_name, profile]]
          sub_mode: hashed_user_id
          include_claims_in_id_token: true

      - model: authentik_core.application
        state: present
        identifiers:
          slug: infisical
        attrs:
          name: Infisical
          provider: !KeyOf provider-infisical
          meta_launch_url: https://infisical.frank.derio.net
```

- [ ] **Step 3: Generate and store Infisical OIDC client secret**

```bash
INFISICAL_CLIENT_SECRET=$(openssl rand -base64 32 | tr -d '\n' | head -c 32)
echo "Infisical Client Secret: $INFISICAL_CLIENT_SECRET"
```

Create `secrets/authentik/infisical-oidc-secret.yaml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: infisical-oidc-secret
  namespace: authentik
type: Opaque
stringData:
  client_secret: "<INFISICAL_CLIENT_SECRET>"
```

Encrypt:
```bash
sops --encrypt --in-place secrets/authentik/infisical-oidc-secret.yaml
```

This stores the client secret for reproducibility — if the Authentik DB is lost, the secret can be recovered from SOPS.

- [ ] **Step 4: Configure Infisical OIDC via admin UI**

Infisical's OIDC configuration is typically done through its admin panel:

1. Navigate to `https://infisical.frank.derio.net`
2. Go to Organization Settings > Security > SSO
3. Configure OIDC with:
   - Issuer URL: `https://auth.frank.derio.net/application/o/infisical/`
   - Client ID: `infisical`
   - Client Secret: the value from Step 3
   - Allowed email domains: (as appropriate)

```yaml
# manual-operation
id: phase13-infisical-oidc-config
phase: XX
app: infisical
plan: docs/plans/2026-03-11-phase13-unified-auth.md
when: "After Task 8 Step 2 — Blueprint has created the Infisical provider"
why_manual: "Infisical OIDC configuration is done via admin UI, not Helm values"
commands:
  - "Decrypt client secret: sops --decrypt secrets/authentik/infisical-oidc-secret.yaml"
  - "In Authentik Admin UI: Providers > Infisical > Edit > set Client Secret"
  - "In Infisical Admin UI: Organization Settings > Security > SSO > Configure OIDC"
  - "Set Issuer URL: https://auth.frank.derio.net/application/o/infisical/"
  - "Set Client ID: infisical"
  - "Set Client Secret: (same value as in Authentik)"
verify:
  - "Navigate to https://infisical.frank.derio.net, see 'Sign in with SSO' option"
status: pending
```

- [ ] **Step 4: Update authentik values and commit**

Add to `apps/authentik/values.yaml` blueprints list:
```yaml
    - authentik-blueprints-provider-infisical
```

```bash
git add apps/authentik-extras/manifests/blueprints-provider-infisical.yaml \
        apps/authentik/values.yaml \
        secrets/authentik/infisical-oidc-secret.yaml
git commit -m "feat(phase13): integrate Infisical with Authentik OIDC

Blueprint creates OAuth2 provider for Infisical.
OIDC configuration in Infisical done via admin UI (manual operation)."
```

---

## Chunk 4: Proxy Outpost for Non-OIDC Services (Task 9)

### Task 9: Proxy Outpost for Longhorn, Hubble, Sympozium

Deploy Authentik's embedded proxy outpost to protect services without native OIDC support.

**Files:**
- Create: `apps/authentik-extras/manifests/blueprints-proxy-providers.yaml`

- [ ] **Step 1: Research embedded outpost configuration**

The embedded outpost runs inside the Authentik server pod. It needs:
- A Proxy Provider per service in Authentik
- Each service's Traefik route updated to forward auth through Authentik

Check Authentik docs for embedded outpost + forward auth configuration:
- How forward auth headers work with Traefik
- Whether Traefik's `forwardAuth` middleware can be used
- **Verify the blueprint model name** for proxy providers (`authentik_providers_proxy.proxyprovider` — confirm via Authentik API schema or docs)

- [ ] **Step 2: Create proxy provider blueprints**

Create `apps/authentik-extras/manifests/blueprints-proxy-providers.yaml`:

```yaml
# Authentik Blueprint: Proxy Providers for non-OIDC services
# Uses embedded outpost with forward-auth for services that don't support OIDC.
apiVersion: v1
kind: ConfigMap
metadata:
  name: authentik-blueprints-proxy-providers
  namespace: authentik
  labels:
    app.kubernetes.io/component: blueprint
data:
  proxy-providers.yaml: |
    # yaml-language-server: $schema=https://goauthentik.io/blueprints/schema.json
    version: 1
    metadata:
      name: Proxy Providers for Non-OIDC Services
      labels:
        blueprints.goauthentik.io/instantiate: "true"
    entries:
      # Longhorn UI proxy provider
      - model: authentik_providers_proxy.proxyprovider
        state: present
        identifiers:
          name: Longhorn UI
        id: provider-longhorn
        attrs:
          authorization_flow: !Find [authentik_flows.flow, [slug, default-provider-authorization-implicit-consent]]
          authentication_flow: !Find [authentik_flows.flow, [slug, default-authentication-flow]]
          mode: forward_single
          external_host: https://longhorn.frank.derio.net

      - model: authentik_core.application
        state: present
        identifiers:
          slug: longhorn
        attrs:
          name: Longhorn UI
          provider: !KeyOf provider-longhorn
          meta_launch_url: https://longhorn.frank.derio.net

      # Hubble UI proxy provider
      - model: authentik_providers_proxy.proxyprovider
        state: present
        identifiers:
          name: Hubble UI
        id: provider-hubble
        attrs:
          authorization_flow: !Find [authentik_flows.flow, [slug, default-provider-authorization-implicit-consent]]
          authentication_flow: !Find [authentik_flows.flow, [slug, default-authentication-flow]]
          mode: forward_single
          external_host: https://hubble.frank.derio.net

      - model: authentik_core.application
        state: present
        identifiers:
          slug: hubble
        attrs:
          name: Hubble UI
          provider: !KeyOf provider-hubble
          meta_launch_url: https://hubble.frank.derio.net

      # Sympozium proxy provider
      - model: authentik_providers_proxy.proxyprovider
        state: present
        identifiers:
          name: Sympozium
        id: provider-sympozium
        attrs:
          authorization_flow: !Find [authentik_flows.flow, [slug, default-provider-authorization-implicit-consent]]
          authentication_flow: !Find [authentik_flows.flow, [slug, default-authentication-flow]]
          mode: forward_single
          external_host: https://sympozium.frank.derio.net

      - model: authentik_core.application
        state: present
        identifiers:
          slug: sympozium
        attrs:
          name: Sympozium
          provider: !KeyOf provider-sympozium
          meta_launch_url: https://sympozium.frank.derio.net
```

- [ ] **Step 3: Update authentik values with proxy blueprint**

Add to `apps/authentik/values.yaml` blueprints list:
```yaml
    - authentik-blueprints-proxy-providers
```

- [ ] **Step 4: Configure Traefik forward auth on raspi-omni**

For each proxied service, update Traefik config to use forward auth through Authentik:

```yaml
# manual-operation
id: phase13-traefik-forward-auth
phase: XX
app: authentik
plan: docs/plans/2026-03-11-phase13-unified-auth.md
when: "After Task 9 Step 3 — Proxy providers created in Authentik"
why_manual: "Traefik config on raspi-omni is outside cluster management"
commands:
  - "Configure Traefik forwardAuth middleware pointing to https://auth.frank.derio.net/outpost.goauthentik.io/auth/traefik"
  - "Apply forwardAuth middleware to Longhorn, Hubble, Sympozium routes"
  - "Restart Traefik on raspi-omni"
verify:
  - "Navigate to https://longhorn.frank.derio.net — redirects to Authentik login"
  - "After login, Longhorn UI loads normally"
  - "Repeat for https://hubble.frank.derio.net and https://sympozium.frank.derio.net"
status: pending
```

- [ ] **Step 5: Commit**

```bash
git add apps/authentik-extras/manifests/blueprints-proxy-providers.yaml \
        apps/authentik/values.yaml
git commit -m "feat(phase13): add proxy outpost for Longhorn, Hubble, Sympozium

Blueprint creates forward-auth proxy providers for services without
native OIDC. Uses embedded outpost via Traefik forwardAuth middleware."
```

---

## Chunk 5: Agent Authentication (Tasks 10-11)

### Task 10: Agent Auth — Authentik Client Credentials

Create a machine user and OAuth2 application in Authentik for non-interactive agent access.

**Files:**
- Create: `apps/authentik-extras/manifests/blueprints-agent-auth.yaml`

- [ ] **Step 1: Create agent auth blueprint**

Create `apps/authentik-extras/manifests/blueprints-agent-auth.yaml`:

```yaml
# Authentik Blueprint: Agent Authentication
# Creates a machine user and OAuth2 provider for non-interactive cluster access.
# Used by Claude Code and CI/CD to authenticate with kubectl via OIDC.
apiVersion: v1
kind: ConfigMap
metadata:
  name: authentik-blueprints-agent-auth
  namespace: authentik
  labels:
    app.kubernetes.io/component: blueprint
data:
  agent-auth.yaml: |
    # yaml-language-server: $schema=https://goauthentik.io/blueprints/schema.json
    version: 1
    metadata:
      name: Agent Authentication
      labels:
        blueprints.goauthentik.io/instantiate: "true"
    entries:
      # OAuth2 Provider for agent kubectl access (client credentials grant)
      - model: authentik_providers_oauth2.oauth2provider
        state: present
        identifiers:
          name: Kubernetes Agent Access
        id: provider-k8s-agent
        attrs:
          authorization_flow: !Find [authentik_flows.flow, [slug, default-provider-authorization-implicit-consent]]
          authentication_flow: !Find [authentik_flows.flow, [slug, default-authentication-flow]]
          client_type: confidential
          client_id: k8s-agent
          redirect_uris: ""
          signing_key: !Find [authentik_crypto.certificatekeypair, [name, authentik Self-signed Certificate]]
          property_mappings:
            - !Find [authentik_providers_oauth2.scopemapping, [scope_name, openid]]
            - !Find [authentik_providers_oauth2.scopemapping, [scope_name, email]]
            - !Find [authentik_providers_oauth2.scopemapping, [scope_name, profile]]
            - !Find [authentik_providers_oauth2.scopemapping, [scope_name, offline_access]]
          sub_mode: hashed_user_id
          include_claims_in_id_token: true
          access_token_validity: hours=8

      - model: authentik_core.application
        state: present
        identifiers:
          slug: k8s-agent
        attrs:
          name: Kubernetes Agent Access
          provider: !KeyOf provider-k8s-agent
```

- [ ] **Step 2: Update authentik values and commit**

Add to `apps/authentik/values.yaml` blueprints list:
```yaml
    - authentik-blueprints-agent-auth
```

```bash
git add apps/authentik-extras/manifests/blueprints-agent-auth.yaml \
        apps/authentik/values.yaml
git commit -m "feat(phase13): add agent authentication blueprint

Creates OAuth2 provider for non-interactive kubectl access via
client credentials grant. 8-hour token validity."
```

- [ ] **Step 3: Create machine user and set client secret in Authentik UI**

```yaml
# manual-operation
id: phase13-agent-machine-user
phase: XX
app: authentik
plan: docs/plans/2026-03-11-phase13-unified-auth.md
when: "After Task 10 Step 2 — Agent auth blueprint deployed"
why_manual: "Machine user credentials and client secret must be set via Authentik admin UI"
commands:
  - "In Authentik Admin UI: Directory > Users > Create Service Account"
  - "Username: claude-agent, Create group: No"
  - "In Authentik Admin UI: Directory > Users > claude-agent > Groups > Add to root-admins"
  - "In Authentik Admin UI: Providers > Kubernetes Agent Access > Edit > set Client Secret"
  - "Generate client secret: openssl rand -base64 32 | tr -d '\\n' | head -c 32"
  - "Save the client_id (k8s-agent) and client_secret for .env_agent"
verify:
  - "In Authentik Admin UI: Directory > Users shows claude-agent service account"
  - "In Authentik Admin UI: Directory > Users > claude-agent shows root-admins membership"
status: pending
```

---

### Task 11: Configure Kubernetes OIDC and Agent Kubeconfig

Configure the Kubernetes API server to accept Authentik OIDC tokens, and create the agent kubeconfig.

- [ ] **Step 1: Research Kubernetes OIDC configuration on Talos**

Talos configures kube-apiserver OIDC flags via machine config. Check Omni/Talos docs for:
- `cluster.apiServer.extraArgs` in machine config
- Required flags: `--oidc-issuer-url`, `--oidc-client-id`, `--oidc-username-claim`, `--oidc-groups-claim`

Research if this requires a Talos machine config patch in `patches/`.

- [ ] **Step 2: Create Talos OIDC patch**

Create a Talos machine config patch for OIDC:

```yaml
# patches/phase13-auth/oidc-apiserver.yaml
# Configures kube-apiserver to accept Authentik OIDC tokens
cluster:
  apiServer:
    extraArgs:
      oidc-issuer-url: https://auth.frank.derio.net/application/o/k8s-agent/
      oidc-client-id: k8s-agent
      oidc-username-claim: preferred_username
      oidc-groups-claim: groups
```

Create `patches/phase13-auth/README.md`:
```markdown
# Phase XX — Authentication OIDC API Server Patch

Configures kube-apiserver to accept Authentik OIDC tokens for kubectl authentication.
Applied to all control-plane nodes via Omni.
```

Apply via Omni (exact method depends on current Omni workflow).

```yaml
# manual-operation
id: phase13-talos-oidc-patch
phase: XX
app: n/a
plan: docs/plans/2026-03-11-phase13-unified-auth.md
when: "After Task 10 — Authentik agent provider exists"
why_manual: "Talos machine config patches are applied via Omni UI"
commands:
  - "Apply OIDC patch via Omni to control-plane machine set"
  - "Wait for rolling restart of kube-apiserver on all control-plane nodes"
verify:
  - "talosctl get kubernetesconfig -n 192.168.55.21 | grep oidc"
  - "kubectl logs -n kube-system kube-apiserver-mini-1 | grep oidc"
status: pending
```

- [ ] **Step 3: Create Kubernetes RBAC for Authentik groups**

Create `apps/authentik-extras/manifests/k8s-rbac.yaml`:

```yaml
# ClusterRoleBindings mapping Authentik groups to Kubernetes RBAC
# These groups come from the OIDC token's 'groups' claim.
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: authentik-root-admins
subjects:
  - kind: Group
    name: root-admins
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: cluster-admin
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: authentik-root-devops
subjects:
  - kind: Group
    name: root-devops
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: admin
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: authentik-root-developers
subjects:
  - kind: Group
    name: root-developers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: view
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: authentik-root-agents
subjects:
  - kind: Group
    name: root-agents
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: cluster-admin
  apiGroup: rbac.authorization.k8s.io
```

- [ ] **Step 4: Install kubelogin (oidc-login) plugin**

```bash
# Install kubelogin kubectl plugin for OIDC authentication
kubectl krew install oidc-login
# Or via Homebrew
brew install int128/kubelogin/kubelogin
```

- [ ] **Step 5: Create .env_agent with OIDC kubeconfig**

Create the `.env_agent` file (gitignored) with a kubeconfig that uses OIDC client credentials:

```bash
cat > .env_agent << 'ENVEOF'
# Agent credentials for non-interactive cluster access
# Source this file: source .env_agent

# Kubeconfig with OIDC authentication
export KUBECONFIG="$(pwd)/kubeconfig-agent.yaml"

# Talos/Omni (existing, check TTL)
export TALOSCONFIG="<path-to-talosconfig>"
export OMNICONFIG="<path-to-omniconfig>"
export OMNI_SERVICE_ACCOUNT_KEY="<existing-key>"
ENVEOF
```

Create `kubeconfig-agent.yaml` (gitignored):

```yaml
apiVersion: v1
kind: Config
clusters:
  - name: frank
    cluster:
      server: https://<kubernetes-api-server-endpoint>
      certificate-authority-data: <CA-DATA>
contexts:
  - name: frank-agent
    context:
      cluster: frank
      user: oidc-agent
current-context: frank-agent
users:
  - name: oidc-agent
    user:
      exec:
        apiVersion: client.authentication.k8s.io/v1beta1
        command: kubectl
        args:
          - oidc-login
          - get-token
          - --oidc-issuer-url=https://auth.frank.derio.net/application/o/k8s-agent/
          - --oidc-client-id=k8s-agent
          - --oidc-client-secret=<AGENT_CLIENT_SECRET>
          - --grant-type=client_credentials
```

Replace placeholders with actual values.

- [ ] **Step 6: Verify agent auth**

```bash
source .env_agent
kubectl get nodes
```

Expected: lists all cluster nodes without any browser popup.

- [ ] **Step 7: Commit RBAC manifests**

```bash
git add apps/authentik-extras/manifests/k8s-rbac.yaml
git commit -m "feat(phase13): add Kubernetes RBAC for Authentik groups

ClusterRoleBindings map Authentik groups to K8s roles:
root-admins/agents=cluster-admin, root-devops=admin, root-developers=view."
```

---

## Chunk 6: Omni Service Account Investigation (Task 12)

### Task 12: Investigate and Fix Omni Service Account TTL

- [ ] **Step 1: Check current Omni service account configuration**

```bash
source .env_devops
omnictl get serviceaccount
```

Check the Omni self-hosted config for service account TTL settings:

```bash
ls omni/
cat omni/docker-compose.yaml  # or whatever the Omni config file is
```

- [ ] **Step 2: Research Omni service account TTL docs**

Check the Siderolabs docs at `https://docs.siderolabs.com/omni/self-hosted/` for:
- Service account key TTL configuration
- Whether service account keys expire independently of Auth0 tokens
- How to generate non-expiring or long-lived service account keys

```bash
omnictl serviceaccount create claude-agent --ttl 87600h  # 10 years, if supported
```

- [ ] **Step 3: Document findings**

If TTL is configurable:
- Generate a new long-lived service account key
- Update `.env_agent` with the new key
- Document the TTL setting

If TTL is not configurable:
- Document the limitation
- Add a `# manual-operation` for periodic key rotation

---

## Chunk 7: Final Verification and Documentation (Task 13)

### Task 13: End-to-End Verification and Cleanup

- [ ] **Step 1: Verify all ArgoCD apps are healthy**

```bash
argocd app list --port-forward --port-forward-namespace argocd | grep -E "authentik|argocd|grafana|infisical"
```

Expected: all apps show `Synced` / `Healthy`.

- [ ] **Step 2: Verify OIDC login for all native OIDC services**

Test each service:
1. ArgoCD: `https://argocd.frank.derio.net` — "Log in via Authentik" works
2. Grafana: `https://grafana.frank.derio.net` — "Sign in with Authentik" works
3. Infisical: `https://infisical.frank.derio.net` — SSO login works

- [ ] **Step 3: Verify proxy outpost for non-OIDC services**

Test each proxied service:
1. Longhorn: `https://longhorn.frank.derio.net` — redirects to Authentik login, then loads
2. Hubble: `https://hubble.frank.derio.net` — same
3. Sympozium: `https://sympozium.frank.derio.net` — same

- [ ] **Step 4: Verify agent auth**

```bash
source .env_agent
kubectl get nodes -o wide
kubectl auth whoami  # Should show OIDC identity
```

- [ ] **Step 5: Create .env_agent alongside existing .env_devops**

`.env_agent` is a new file for non-interactive OIDC-based credentials (created in Task 11). `.env_devops` continues to exist for Omni service account access. Update CLAUDE.md to document both files:

```bash
# In CLAUDE.md, update the Environment commands section:
# source .env          # General (KUBECONFIG, TALOSCONFIG, OMNICONFIG)
# source .env_devops   # DevOps (OMNI_ENDPOINT, service account key)
# source .env_agent    # Agent (OIDC client credentials for non-interactive kubectl)
```

- [ ] **Step 6: Sync runbook**

Run `/sync-runbook` to collect all `# manual-operation` blocks from this plan into `docs/runbooks/manual-operations.yaml`.

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "feat(phase13): complete unified auth deployment

All services integrated with Authentik SSO:
- Native OIDC: ArgoCD, Grafana, Infisical
- Proxy outpost: Longhorn, Hubble, Sympozium
- Agent auth: kubectl via OIDC client credentials
- Groups: root-admins, root-devops, root-developers, root-agents"
```
