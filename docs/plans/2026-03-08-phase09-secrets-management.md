# Phase 09: Secrets Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy External Secrets Operator (ESO) and self-hosted Infisical to replace the manual SOPS workflow for runtime secrets, providing a UI-managed secret store that syncs into Kubernetes via ClusterSecretStore + ExternalSecret CRs.

**Architecture:** Infisical runs in the `infisical` namespace with a bundled PostgreSQL (5Gi Longhorn) and Redis, exposed at `192.168.55.204` via Cilium L2 LoadBalancer. ESO runs in `external-secrets` and bridges Infisical → K8s Secrets via a ClusterSecretStore. Infisical's own DB/app credentials are bootstrapped with SOPS (the only remaining SOPS use case).

**Tech Stack:** Infisical Helm chart, External Secrets Operator Helm chart, SOPS/age, ArgoCD App-of-Apps, Cilium L2 LoadBalancer, Longhorn storage.

---

## Design Reference

See: `docs/plans/2026-03-07-phase09-secrets-management-design.md`

---

## Task 1: Discover Chart Versions

**Files:** None (research only)

**Step 1: Add Helm repos**

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo add infisical-helm-charts https://dl.cloudsmith.io/public/infisical/helm-charts/helm/charts/
helm repo update
```

**Step 2: Check latest stable versions**

```bash
helm search repo external-secrets/external-secrets --versions | head -5
helm search repo infisical-helm-charts/infisical --versions | head -5
```

Expected: You will see version numbers like `0.12.x` for ESO and `0.x.x` for Infisical. **Record these versions** — you will use them in the Application CRs.

**Step 3: Inspect Infisical chart values**

```bash
helm show values infisical-helm-charts/infisical > /tmp/infisical-values.yaml
cat /tmp/infisical-values.yaml | grep -A5 -i "secret\|service\|postgresql\|redis\|encryption\|auth"
```

Expected: Confirm field names for `kubeSecretRef` (or equivalent), `service.type`, PostgreSQL and Redis subchart config. Adjust Task 3 values if the chart schema differs from the plan.

---

## Task 2: Deploy ESO (External Secrets Operator)

**Files:**
- Create: `apps/root/templates/ns-external-secrets.yaml`
- Create: `apps/external-secrets/values.yaml`
- Create: `apps/root/templates/external-secrets.yaml`

**Step 1: Create namespace manifest**

```yaml
# apps/root/templates/ns-external-secrets.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: external-secrets
  labels:
    pod-security.kubernetes.io/enforce: privileged
    pod-security.kubernetes.io/warn: privileged
    pod-security.kubernetes.io/audit: privileged
```

**Step 2: Create ESO values.yaml**

```yaml
# apps/external-secrets/values.yaml
installCRDs: true

crds:
  createClusterExternalSecret: true
  createClusterSecretStore: true
  createPushSecret: false

webhook:
  create: true

certController:
  create: true
```

**Step 3: Create ESO Application CR**

Replace `<ESO_VERSION>` with the version from Task 1.

```yaml
# apps/root/templates/external-secrets.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: external-secrets
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://charts.external-secrets.io
      chart: external-secrets
      targetRevision: "<ESO_VERSION>"
      helm:
        releaseName: external-secrets
        valueFiles:
          - $values/apps/external-secrets/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: external-secrets
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
      - CreateNamespace=false
```

**Step 4: Verify file structure**

```bash
ls apps/external-secrets/
ls apps/root/templates/ | grep external
```

Expected: `values.yaml` in `apps/external-secrets/`, and both `ns-external-secrets.yaml` and `external-secrets.yaml` in `apps/root/templates/`.

**Step 5: Commit**

```bash
git add apps/root/templates/ns-external-secrets.yaml \
        apps/external-secrets/values.yaml \
        apps/root/templates/external-secrets.yaml
git commit -m "feat(secrets): add ESO namespace and Application"
```

---

## Task 3: Deploy Infisical

**Files:**
- Create: `apps/root/templates/ns-infisical.yaml`
- Create: `apps/infisical/values.yaml`
- Create: `apps/root/templates/infisical.yaml`

**Step 1: Create namespace manifest**

```yaml
# apps/root/templates/ns-infisical.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: infisical
  labels:
    pod-security.kubernetes.io/enforce: privileged
    pod-security.kubernetes.io/warn: privileged
    pod-security.kubernetes.io/audit: privileged
```

**Step 2: Create Infisical values.yaml**

> **Note:** Verify field names against `helm show values infisical-helm-charts/infisical` from Task 1. Adjust if chart schema differs.

```yaml
# apps/infisical/values.yaml
infisical:
  replicaCount: 1

  image:
    pullPolicy: IfNotPresent

  # Name of the pre-existing K8s Secret with Infisical env vars.
  # The secret is bootstrapped via SOPS in Task 4.
  kubeSecretRef: infisical-secrets

  service:
    type: LoadBalancer
    annotations:
      lbipam.cilium.io/ips: "192.168.55.204"

postgresql:
  enabled: true
  primary:
    persistence:
      size: 5Gi
      storageClass: longhorn
  auth:
    username: infisical
    database: infisical
    # Pull password from the same bootstrap secret.
    # Bitnami PostgreSQL expects key "password" for the regular user.
    existingSecret: infisical-secrets
    secretKeys:
      userPasswordKey: postgresql-password

redis:
  enabled: true
  auth:
    enabled: false
  master:
    persistence:
      enabled: false
  replica:
    replicaCount: 0
```

**Step 3: Create Infisical Application CR**

Replace `<INFISICAL_VERSION>` with the version from Task 1.

```yaml
# apps/root/templates/infisical.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: infisical
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://dl.cloudsmith.io/public/infisical/helm-charts/helm/charts/
      chart: infisical
      targetRevision: "<INFISICAL_VERSION>"
      helm:
        releaseName: infisical
        valueFiles:
          - $values/apps/infisical/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: infisical
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
      - CreateNamespace=false
```

**Step 4: Verify file structure**

```bash
ls apps/infisical/
ls apps/root/templates/ | grep infisical
```

Expected: `values.yaml` in `apps/infisical/`, and `ns-infisical.yaml` + `infisical.yaml` in `apps/root/templates/`.

**Step 5: Commit**

```bash
git add apps/root/templates/ns-infisical.yaml \
        apps/infisical/values.yaml \
        apps/root/templates/infisical.yaml
git commit -m "feat(secrets): add Infisical namespace and Application"
```

---

## Task 4: Create Infisical Bootstrap Secret (SOPS)

The Infisical server and its PostgreSQL subchart both need credentials before they can start. These credentials must exist in the cluster before ArgoCD deploys Infisical. Apply manually, then ArgoCD ignores the Secret's data field.

**Files:**
- Create: `secrets/infisical/infisical-secrets.yaml`

**Step 1: Generate credentials**

Run these commands and note the output:

```bash
# PostgreSQL password (url-safe)
openssl rand -base64 24 | tr -d '/+=' | head -c 32
# Auth secret (JWT signing key)
openssl rand -base64 32
# Encryption key (must be exactly 16 hex chars = 8 bytes)
openssl rand -hex 8
```

**Step 2: Create plaintext secret**

Fill in the values generated above. Replace every `<...>` placeholder.

```yaml
# secrets/infisical/infisical-secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: infisical-secrets
  namespace: infisical
type: Opaque
stringData:
  # Infisical app env vars
  DB_CONNECTION_URI: "postgresql://infisical:<PG_PASSWORD>@infisical-postgresql:5432/infisical"
  AUTH_SECRET: "<AUTH_SECRET>"
  ENCRYPTION_KEY: "<ENCRYPTION_KEY>"
  REDIS_URL: "redis://infisical-redis-master:6379"
  SITE_URL: "http://192.168.55.204"
  # PostgreSQL subchart (Bitnami) expects "password" key for the user password
  postgresql-password: "<PG_PASSWORD>"
```

**Step 3: Encrypt in-place with SOPS**

```bash
sops --encrypt --in-place secrets/infisical/infisical-secrets.yaml
```

Expected: The `stringData` block is now encrypted (shows `ENC[AES256_GCM,...]`). The metadata and apiVersion remain plaintext.

**Step 4: Verify encryption**

```bash
grep -c "ENC\[" secrets/infisical/infisical-secrets.yaml
```

Expected: `5` (one per stringData key).

**Step 5: Apply the secret to the cluster**

```yaml
# manual-operation
id: phase09-infisical-bootstrap-secrets
phase: 9
app: infisical
plan: docs/plans/2026-03-08-phase09-secrets-management.md
when: "Task 4 — after SOPS-encrypting infisical-secrets.yaml and infisical-db-uri.yaml"
why_manual: "SOPS metadata is rejected by ArgoCD ServerSideApply schema validation; encrypted secrets must live outside ArgoCD-managed paths and be applied out-of-band"
commands:
  - source .env
  - sops --decrypt secrets/infisical/infisical-secrets.yaml | kubectl apply -f -
  - sops --decrypt secrets/infisical/infisical-db-uri.yaml | kubectl apply -f -
verify:
  - kubectl get secret infisical-secrets -n infisical
  - kubectl get secret infisical-db-uri -n infisical
status: done
```

```bash
source .env
sops --decrypt secrets/infisical/infisical-secrets.yaml | kubectl apply -f -
```

Expected:
```
secret/infisical-secrets created
```

**Step 6: Verify the secret is in the cluster**

```bash
kubectl get secret infisical-secrets -n infisical
```

Expected: Secret exists with `Opaque` type and `5` data keys (or however many SOPS encrypted).

**Step 7: Commit the encrypted secret**

```bash
git add secrets/infisical/infisical-secrets.yaml
git commit -m "feat(secrets): add SOPS-encrypted Infisical bootstrap secret"
```

---

## Task 5: Push and Verify ESO + Infisical Deploy

**Step 1: Push to git**

```bash
git push
```

**Step 2: Trigger ArgoCD sync (if needed)**

```bash
source .env
argocd app sync root --port-forward --port-forward-namespace argocd
```

Expected: ArgoCD picks up the new `external-secrets`, `infisical`, namespace applications.

**Step 3: Watch ESO pods come up**

```bash
kubectl get pods -n external-secrets -w
```

Expected within 2 minutes:
```
external-secrets-<hash>          1/1  Running
external-secrets-webhook-<hash>  1/1  Running
external-secrets-cert-controller-<hash>  1/1  Running
```

**Step 4: Watch Infisical pods come up**

```bash
kubectl get pods -n infisical -w
```

Expected within 5 minutes:
```
infisical-<hash>            1/1  Running
infisical-postgresql-0      1/1  Running
infisical-redis-master-0    1/1  Running
```

**Step 5: Check LoadBalancer IP assignment**

```bash
kubectl get svc -n infisical
```

Expected: Infisical service shows `EXTERNAL-IP: 192.168.55.204`.

**Step 6: Check Infisical health**

```bash
curl -s http://192.168.55.204/api/status | python3 -m json.tool
```

Expected: JSON response with `"status": "ok"` or similar health indicator.

---

## Task 6: Infisical UI Setup (Manual)

```yaml
# manual-operation
id: phase09-infisical-ui-setup
phase: 9
app: infisical
plan: docs/plans/2026-03-08-phase09-secrets-management.md
when: "Task 5 complete — Infisical pod Running and UI reachable at http://192.168.55.204"
why_manual: "Initial admin account, project creation, and Machine Identity setup have no CLI equivalent in self-hosted Infisical"
commands:
  - "Open http://192.168.55.204 → Sign Up → create admin account"
  - "Create project: frank-cluster"
  - "Verify prod environment exists (Settings → Environments)"
  - "Organization Settings → Machine Identities → Create Identity: eso-cluster-reader, Universal Auth"
  - "Click Add Client Secret → copy Client ID and Client Secret (shown once)"
  - "frank-cluster project → Access Control → add eso-cluster-reader with Viewer role"
verify:
  - "Machine Identity eso-cluster-reader exists in Organization Settings"
  - "eso-cluster-reader has Viewer access to frank-cluster project"
status: pending
```

These steps are performed in the Infisical web UI. There is no CLI equivalent for initial setup.

**Step 1: Open the Infisical UI**

Navigate to: `http://192.168.55.204`

**Step 2: Create the admin account**

- Click "Sign Up"
- Email: use your own email (this is local-only)
- Password: choose a strong password (store in your password manager)
- Complete email verification (check terminal logs if email is not configured: `kubectl logs -n infisical deploy/infisical | grep -i verification`)

**Step 3: Create the project**

- Click "Create Project"
- Name: `frank-cluster`
- Leave other defaults

**Step 4: Create the `prod` environment**

In the `frank-cluster` project:
- Go to Settings → Environments
- Ensure `prod` environment exists (it may be created by default)

**Step 5: Create a Machine Identity for ESO**

- Go to Organization Settings → Machine Identities
- Click "Create Identity"
- Name: `eso-cluster-reader`
- Auth method: **Universal Auth**
- Click "Create"
- Click "Add Client Secret" → note the **Client ID** and **Client Secret**

> **IMPORTANT:** The Client Secret is shown only once. Copy it now.

**Step 6: Grant the identity access to the project**

- Go to the `frank-cluster` project → Access Control
- Add the `eso-cluster-reader` identity with `Viewer` role (or custom role with secret read)

---

## Task 7: Create and Apply ESO Credentials Secret (SOPS)

**Files:**
- Create: `secrets/infisical/eso-credentials.yaml`

**Step 1: Create plaintext credentials secret**

Use the Client ID and Client Secret from Task 6 Step 5.

```yaml
# secrets/infisical/eso-credentials.yaml
apiVersion: v1
kind: Secret
metadata:
  name: infisical-credentials
  namespace: external-secrets
type: Opaque
stringData:
  clientId: "<CLIENT_ID_FROM_INFISICAL>"
  clientSecret: "<CLIENT_SECRET_FROM_INFISICAL>"
```

**Step 2: Encrypt in-place**

```bash
sops --encrypt --in-place secrets/infisical/eso-credentials.yaml
```

Expected: Both `stringData` values are now `ENC[AES256_GCM,...]`.

**Step 3: Apply to cluster**

```yaml
# manual-operation
id: phase09-eso-credentials-secret
phase: 9
app: external-secrets
plan: docs/plans/2026-03-08-phase09-secrets-management.md
when: "Task 7 — after SOPS-encrypting eso-credentials.yaml with Client ID and Secret from Infisical UI"
why_manual: "SOPS metadata is rejected by ArgoCD ServerSideApply schema validation; encrypted secrets must live outside ArgoCD-managed paths and be applied out-of-band"
commands:
  - source .env
  - sops --decrypt secrets/infisical/eso-credentials.yaml | kubectl apply -f -
verify:
  - kubectl get secret infisical-credentials -n external-secrets
status: pending
```

```bash
sops --decrypt secrets/infisical/eso-credentials.yaml | kubectl apply -f -
```

Expected:
```
secret/infisical-credentials created
```

**Step 4: Verify**

```bash
kubectl get secret infisical-credentials -n external-secrets
```

Expected: Secret exists with 2 data keys.

**Step 5: Commit**

```bash
git add secrets/infisical/eso-credentials.yaml
git commit -m "feat(secrets): add SOPS-encrypted ESO credentials secret"
```

---

## Task 8: Create ClusterSecretStore and infisical-extras App

**Files:**
- Create: `apps/infisical/manifests/cluster-secret-store.yaml`
- Create: `apps/root/templates/infisical-extras.yaml`

**Step 1: Create ClusterSecretStore manifest**

```yaml
# apps/infisical/manifests/cluster-secret-store.yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: infisical
spec:
  provider:
    infisical:
      auth:
        universalAuthCredentials:
          clientId:
            secretRef:
              name: infisical-credentials
              namespace: external-secrets
              key: clientId
          clientSecret:
            secretRef:
              name: infisical-credentials
              namespace: external-secrets
              key: clientSecret
      hostAPI: http://192.168.55.204/api
```

**Step 2: Create infisical-extras Application CR**

Following the `longhorn-extras` pattern for raw manifests.

```yaml
# apps/root/templates/infisical-extras.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: infisical-extras
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/infisical/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: external-secrets
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
```

**Step 3: Verify file structure**

```bash
ls apps/infisical/manifests/
ls apps/root/templates/ | grep infisical
```

Expected: `cluster-secret-store.yaml` in manifests, and 3 files in templates: `ns-infisical.yaml`, `infisical.yaml`, `infisical-extras.yaml`.

**Step 4: Commit**

```bash
git add apps/infisical/manifests/cluster-secret-store.yaml \
        apps/root/templates/infisical-extras.yaml
git commit -m "feat(secrets): add ClusterSecretStore and infisical-extras Application"
```

---

## Task 9: Push and Verify ClusterSecretStore

**Step 1: Push to git**

```bash
git push
```

**Step 2: Sync root app**

```bash
argocd app sync root --port-forward --port-forward-namespace argocd
```

**Step 3: Watch infisical-extras sync**

```bash
argocd app wait infisical-extras --port-forward --port-forward-namespace argocd --health --timeout 120
```

Expected: `Health Status: Healthy`, `Sync Status: Synced`.

**Step 4: Verify ClusterSecretStore is Ready**

```bash
kubectl get clustersecretstores
```

Expected:
```
NAME        AGE   STATUS   READY
infisical   30s   Valid    True
```

If status is `Invalid`, check the condition:

```bash
kubectl describe clustersecretstore infisical | grep -A10 "Status:"
```

Common issues: wrong `hostAPI` URL, credentials secret not in correct namespace, Machine Identity permissions.

---

## Task 10: Demo ExternalSecret Smoke Test

Verify the full pipeline: Infisical → ESO → K8s Secret.

**Step 1: Add a test secret in Infisical UI**

- In the Infisical UI, open the `frank-cluster` project → `prod` environment
- Click "Add Secret"
- Key: `CLUSTER_TEST_KEY`
- Value: `hello-from-infisical`
- Save

**Step 2: Create a demo ExternalSecret**

This is a one-off test manifest — apply directly, do not commit to git.

```bash
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Namespace
metadata:
  name: secrets-test
---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: cluster-test
  namespace: secrets-test
spec:
  refreshInterval: 30s
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: cluster-test-secret
    creationPolicy: Owner
  data:
    - secretKey: testValue
      remoteRef:
        key: CLUSTER_TEST_KEY
        metaData:
          secretPath: /
          projectSlug: frank-cluster
          envSlug: prod
EOF
```

**Step 3: Wait for sync (up to 60s)**

```bash
kubectl get externalsecret cluster-test -n secrets-test -w
```

Expected: `STATUS: SecretSynced`.

**Step 4: Verify the K8s Secret was created**

```bash
kubectl get secret cluster-test-secret -n secrets-test -o jsonpath='{.data.testValue}' | base64 -d
```

Expected: `hello-from-infisical`

**Step 5: Clean up the test resources**

```bash
kubectl delete namespace secrets-test
```

---

## Task 11: Write Blog Post

**Files:**
- Create: `blog/content/posts/09-secrets/index.md`

**Step 1: Create the post directory**

```bash
mkdir -p blog/content/posts/09-secrets
```

**Step 2: Write the blog post**

```markdown
---
title: "Secrets Management — Self-Hosting Infisical with External Secrets Operator"
date: 2026-03-08
draft: false
tags: ["secrets", "infisical", "external-secrets", "eso", "sops", "gitops", "security"]
summary: "Moving beyond SOPS for runtime secrets: deploying Infisical as a self-hosted Vault alternative and wiring it to Kubernetes via External Secrets Operator."
weight: 10
cover:
  image: cover.png
  alt: "Frank the cluster monster unlocking a glowing vault labeled Infisical while Kubernetes pods reach in to grab their secrets"
  relative: true
---

Every self-hosted cluster eventually reaches the same inflection point: you have secrets that need to be in Kubernetes, and you need a better story than "encrypt with SOPS and apply manually."

Frank's Phase 9 crosses that inflection point. The goal: a UI-managed secret store that syncs automatically into Kubernetes, with a clear audit trail and no secret-in-plaintext moment anywhere in the pipeline.

The stack: [Infisical](https://infisical.com) as the secret store, [External Secrets Operator](https://external-secrets.io) (ESO) as the Kubernetes sync engine.

## Why Not Vault?

HashiCorp Vault is the default answer. It is battle-hardened, has excellent documentation, and integrates with everything. It is also operationally heavy: unsealing, HA setup, Raft storage, agent injectors. For a homelab, the operational cost is disproportionate to the benefit.

Infisical is MIT-licensed, self-hostable, has a clean modern UI, and integrates with ESO via a native provider. The helm chart bundles PostgreSQL and Redis — one `helm install` and it is running.

## Why Not Just SOPS?

SOPS is still in the repo — it bootstraps Infisical's own credentials. But SOPS has friction for runtime secrets:

- Adding a secret requires editing a YAML file, encrypting, committing, and redeploying
- No audit trail (who changed what, when)
- No per-project or per-environment access control
- The "manual apply" pattern discovered in Phase 8 is a workflow smell

Infisical provides all of this with a UI and an API.

## Architecture

```
Infisical (self-hosted, infisical namespace)
  └── Projects / Environments / Secrets
          ↓  (ClusterSecretStore + ExternalSecret CRs)
External Secrets Operator (external-secrets namespace)
          ↓
  K8s Secret objects
          ↓
  App pods (secretKeyRef / envFrom)
```

Infisical stores secrets in **projects**, organized by **environment** (prod, staging, dev). ESO syncs them into Kubernetes via two CRDs:

- **`ClusterSecretStore`** — connects ESO to Infisical, cluster-wide. One store, all namespaces.
- **`ExternalSecret`** — declares which Infisical secret to sync and what K8s Secret to create.

## Bootstrap: Still SOPS

Infisical needs a PostgreSQL database and an encryption key before it can start. Those credentials are the one thing that cannot come from Infisical itself (the store doesn't exist yet). SOPS handles this bootstrap case:

```bash
# Generate credentials
PG_PASS=$(openssl rand -base64 24 | tr -d '/+=')
AUTH_SECRET=$(openssl rand -base64 32)
ENC_KEY=$(openssl rand -hex 8)

# Create secret, encrypt, apply
sops --encrypt --in-place secrets/infisical/infisical-secrets.yaml
sops --decrypt secrets/infisical/infisical-secrets.yaml | kubectl apply -f -
```

The secret contains:
- `DB_CONNECTION_URI` — PostgreSQL connection string (used by Infisical)
- `AUTH_SECRET` — JWT signing key
- `ENCRYPTION_KEY` — secret encryption key (16 hex chars)
- `postgresql-password` — consumed by the Bitnami PostgreSQL subchart

This is the last SOPS secret in the cluster. Everything else goes through Infisical.

## Deployment

ESO installs as a standard Helm chart — CRDs, webhook, cert controller. The values file is minimal:

```yaml
# apps/external-secrets/values.yaml
installCRDs: true
crds:
  createClusterExternalSecret: true
  createClusterSecretStore: true
```

Infisical is more involved. The chart bundles PostgreSQL and Redis, and references the bootstrap secret for all credentials:

```yaml
# apps/infisical/values.yaml
infisical:
  replicaCount: 1
  kubeSecretRef: infisical-secrets
  service:
    type: LoadBalancer
    annotations:
      lbipam.cilium.io/ips: "192.168.55.204"

postgresql:
  enabled: true
  primary:
    persistence:
      size: 5Gi
      storageClass: longhorn
  auth:
    existingSecret: infisical-secrets
    secretKeys:
      userPasswordKey: postgresql-password
```

The `lbipam.cilium.io/ips` annotation pins the LoadBalancer IP — same pattern as ArgoCD and Longhorn UI.

## Connecting ESO to Infisical

After Infisical is running, a Machine Identity is created in the UI:

1. Organization Settings → Machine Identities → Create
2. Name: `eso-cluster-reader`, Auth: Universal Auth
3. Grant Viewer access to the `frank-cluster` project
4. Copy the **Client ID** and **Client Secret**

The credentials go into a SOPS-encrypted secret in the `external-secrets` namespace:

```bash
sops --encrypt --in-place secrets/infisical/eso-credentials.yaml
sops --decrypt secrets/infisical/eso-credentials.yaml | kubectl apply -f -
```

The `ClusterSecretStore` wires it together:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: infisical
spec:
  provider:
    infisical:
      auth:
        universalAuthCredentials:
          clientId:
            secretRef:
              name: infisical-credentials
              namespace: external-secrets
              key: clientId
          clientSecret:
            secretRef:
              name: infisical-credentials
              namespace: external-secrets
              key: clientSecret
      hostAPI: http://192.168.55.204/api
```

## Consuming a Secret

An app that needs a secret declares an `ExternalSecret` in its namespace:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: my-app-secrets
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: my-app-secrets
  data:
    - secretKey: DATABASE_URL
      remoteRef:
        key: DATABASE_URL
        metaData:
          secretPath: /
          projectSlug: frank-cluster
          envSlug: prod
```

ESO creates a K8s Secret named `my-app-secrets` with the value from Infisical, refreshed every 5 minutes. The app references it via `secretKeyRef` or `envFrom` — standard Kubernetes, no Infisical SDK required.

## What Changed

Before Phase 9:
- Runtime secrets: manual SOPS workflow (edit YAML → encrypt → commit → apply)
- No audit trail, no access control per secret
- Bootstrap and runtime secrets are the same class of object

After Phase 9:
- Runtime secrets: Infisical UI → ExternalSecret → K8s Secret (automatic)
- SOPS only for Infisical's own bootstrap credentials
- Audit trail, project/environment scoping, Machine Identity access control
- One `ClusterSecretStore` serves all namespaces

## Services

| Service | IP | Notes |
|---------|----|-------|
| Infisical UI | `192.168.55.204` | Cilium L2 LoadBalancer |
| ESO | ClusterIP only | Internal operator |

## References

- [Infisical Self-Hosted Documentation](https://infisical.com/docs/self-hosting/overview)
- [External Secrets Operator](https://external-secrets.io/latest/)
- [ESO Infisical Provider](https://external-secrets.io/latest/provider/infisical/)
- [Infisical Machine Identity](https://infisical.com/docs/documentation/platform/identities/machine-identities)
- [SOPS Documentation](https://github.com/getsops/sops)
```

**Step 3: Add cover image prompt to post directory**

Create `blog/content/posts/09-secrets/cover-prompt.txt` with an image generation prompt for the cover art (so you remember what to generate):

```
Frank the friendly cluster monster (green, wide eyes, cheerful) carefully unlocking a large glowing vault door labeled "Infisical" with a golden key. Multiple Kubernetes pods (small cubes with the K8s wheel logo) are lined up eagerly waiting to receive their secrets. The background shows a dark server room with glowing rack lights. Digital padlock motifs float in the air. Cozy, warm lighting. Pixel art / retro game aesthetic.
```

**Step 4: Commit blog post**

```bash
git add blog/content/posts/09-secrets/
git commit -m "docs(blog): add Phase 9 secrets management post"
```

**Step 5: Preview in Hugo dev server**

```bash
cd blog && hugo server --buildDrafts
```

Navigate to `http://localhost:1313` and verify the post renders correctly — frontmatter, headings, code blocks, cover image placeholder.

**Step 6: Final push**

```bash
git push
```

---

## Verification Checklist

After all tasks are complete:

```bash
# ESO is running
kubectl get pods -n external-secrets
# All 3 pods (controller, webhook, cert-controller) Running

# Infisical is running
kubectl get pods -n infisical
# infisical, infisical-postgresql-0, infisical-redis-master-0 all Running

# ClusterSecretStore is valid
kubectl get clustersecretstores
# infisical READY=True

# ArgoCD apps are healthy
argocd app list --port-forward --port-forward-namespace argocd | grep -E "external-secrets|infisical"
# Both Healthy + Synced

# Longhorn has the Infisical PostgreSQL PVC
kubectl get pvc -n infisical
# data-infisical-postgresql-0 Bound 5Gi
```

---

## Known Gotchas

- **SOPS + ArgoCD ServerSideApply**: SOPS-encrypted secrets cannot live in ArgoCD-managed manifest paths. Apply them manually with `sops --decrypt | kubectl apply -f -`. See Phase 8 write-up for details.
- **Machine Identity token shown once**: The Client Secret in Infisical's UI is only shown at creation time. Encrypt it immediately with SOPS.
- **Infisical chart values drift**: The Infisical helm chart is actively developed. Always run `helm show values infisical-helm-charts/infisical` to confirm field names before writing `values.yaml`. The key field is `kubeSecretRef` (or similar) pointing to the bootstrap secret.
- **ClusterSecretStore namespace**: The `ClusterSecretStore` is cluster-scoped but ESO deploys it into the `external-secrets` namespace conceptually. The `infisical-extras` ArgoCD app targets the `external-secrets` namespace so the secret reference `namespace: external-secrets` resolves correctly.
- **ExternalSecret `metaData` fields**: The `secretPath`, `projectSlug`, and `envSlug` fields in `remoteRef.metaData` must exactly match what's in Infisical. `projectSlug` is the URL-safe slug shown in project settings, not the display name.
