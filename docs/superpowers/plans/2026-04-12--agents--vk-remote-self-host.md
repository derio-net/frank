# VK Remote Self-Host Implementation Plan

> **For VK agents:** Use vk-execute to implement assigned phases.
> **For local execution:** Use subagent-driven-development or executing-plans.
> **For dispatch:** Use vk-dispatch to create Issues from this plan.

**Spec:** `docs/superpowers/specs/2026-04-12--agents--vk-remote-self-host-design.md`
**Status:** In Progress (Phases 0-2 complete — pending: Phase 3 post-deploy checklist)

**Goal:** Deploy VK's remote crate as a self-hosted Kubernetes service on Frank, replacing the dying VK cloud backend.
**Architecture:** PostgreSQL 16 (dedicated, WAL logical) → vk-remote (Rust/Axum API) → ElectricSQL (real-time sync). Secure-agent-pod connects via in-cluster DNS. Operator accesses via Traefik IngressRoute with Authentik forward-auth.
**Tech Stack:** Rust/Axum (vk-remote), PostgreSQL 16, ElectricSQL, ArgoCD manifests, Infisical (secrets), Traefik (ingress), Authentik (SSO)

**Domain deviation:** Spec says `vk.frank.derio.net` but Frank's Traefik wildcard cert covers `*.cluster.derio.net`. This plan uses `vk.cluster.derio.net` to avoid provisioning a new cert.

**Namespace note:** Spec says deploy in `agents` namespace "alongside secure-agent-pod", but secure-agent-pod is in namespace `secure-agent-pod`. This plan creates a new `agents` namespace for vk-remote. Cross-namespace communication uses FQDN (`vk-remote.agents.svc.cluster.local:8081`).

---

## Phase 0: Fork & CI [manual]
<!-- Tracking: https://github.com/derio-net/frank/issues/61 -->

This phase sets up the VK fork and container image build pipeline. Must be completed before Phase 1 can reference the GHCR image.

### Task 1: Fork the VK repository

1. Go to `https://github.com/BloopAI/vibe-kanban`
2. Fork to `derio-net/vibe-kanban` (keep all branches, default branch only)
3. Clone locally: `git clone git@github.com:derio-net/vibe-kanban.git ~/repos/vibe-kanban`

### Task 2: Create GitHub Actions workflow for vk-remote image

Create `.github/workflows/build-remote.yaml` in the fork:

```yaml
name: Build vk-remote
on:
  push:
    branches: [main]
    paths:
      - 'crates/remote/**'
      - 'Cargo.toml'
      - 'Cargo.lock'
      - '.github/workflows/build-remote.yaml'
  workflow_dispatch:

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: derio-net/vk-remote

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          file: crates/remote/Dockerfile
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest
```

### Task 3: Verify the Dockerfile and trigger first build

1. Check that `crates/remote/Dockerfile` exists in the fork. If not, create a multi-stage Dockerfile:
   - Stage 1: `rust:1.82-bookworm` — `cargo build --release -p vk-remote`
   - Stage 2: `debian:bookworm-slim` — copy binary, expose 8081
2. Push the workflow file and trigger via `workflow_dispatch`
3. Verify the image appears at `ghcr.io/derio-net/vk-remote:<sha>`
4. Record the image SHA for use in Phase 1 manifests

### Task 4: Create Infisical secrets

In Infisical (`frank-cluster-iwpg` project, `prod` environment), create:

| Key | Value | Notes |
|-----|-------|-------|
| `VK_REMOTE_JWT_SECRET` | `openssl rand -base64 48` | JWT signing key |
| `VK_REMOTE_LOCAL_AUTH_PASSWORD` | Strong password | Local login password |
| `VK_REMOTE_ELECTRIC_PASSWORD` | Strong password | ElectricSQL PG role |
| `VK_REMOTE_PG_PASSWORD` | Strong password | Main PG user password |

---

## Phase 1: ArgoCD Manifests [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/62 -->

All manifests for deploying vk-remote, PostgreSQL, and ElectricSQL on Frank. Single ArgoCD Application using raw manifests pattern.

### Task 1: Create namespace manifest

**Files:**
- Create: `apps/vk-remote/manifests/namespace.yaml`

- [x] **Step 1: Write the namespace manifest**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: agents
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/audit: baseline
    pod-security.kubernetes.io/warn: baseline
```

### Task 2: Create ExternalSecret for VK Remote secrets

**Files:**
- Create: `apps/vk-remote/manifests/externalsecret.yaml`

- [x] **Step 1: Write the ExternalSecret**

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: vk-remote-secrets
  namespace: agents
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: vk-remote-secrets
    creationPolicy: Owner
    deletionPolicy: Retain
  data:
    - secretKey: VIBEKANBAN_REMOTE_JWT_SECRET
      remoteRef:
        key: VK_REMOTE_JWT_SECRET
    - secretKey: SELF_HOST_LOCAL_AUTH_PASSWORD
      remoteRef:
        key: VK_REMOTE_LOCAL_AUTH_PASSWORD
    - secretKey: ELECTRIC_ROLE_PASSWORD
      remoteRef:
        key: VK_REMOTE_ELECTRIC_PASSWORD
    - secretKey: POSTGRES_PASSWORD
      remoteRef:
        key: VK_REMOTE_PG_PASSWORD
```

### Task 3: Create PostgreSQL StatefulSet

**Files:**
- Create: `apps/vk-remote/manifests/postgres.yaml`

- [x] **Step 1: Write the PVC**

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-vk-data
  namespace: agents
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn
  resources:
    requests:
      storage: 1Gi
```

- [x] **Step 2: Write the PostgreSQL Deployment**

Use Recreate strategy (RWO PVC deadlock — see gotchas).

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres-vk
  namespace: agents
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: postgres-vk
  template:
    metadata:
      labels:
        app: postgres-vk
    spec:
      containers:
        - name: postgres
          image: postgres:16-alpine
          ports:
            - containerPort: 5432
          env:
            - name: POSTGRES_DB
              value: vibekanban
            - name: POSTGRES_USER
              value: vibekanban
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: vk-remote-secrets
                  key: POSTGRES_PASSWORD
          args:
            - "-c"
            - "wal_level=logical"
            - "-c"
            - "max_replication_slots=5"
            - "-c"
            - "max_wal_senders=5"
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: postgres-vk-data
```

- [x] **Step 3: Write the PostgreSQL Service**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres-vk
  namespace: agents
spec:
  selector:
    app: postgres-vk
  ports:
    - port: 5432
      targetPort: 5432
```

### Task 4: Create PostgreSQL init Job for ElectricSQL role

**Files:**
- Create: `apps/vk-remote/manifests/postgres-init-job.yaml`

ElectricSQL requires a dedicated PG role with replication privileges. This Job runs once after PG is ready.

- [x] **Step 1: Write the init Job**

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: postgres-vk-init-electric
  namespace: agents
  annotations:
    argocd.argoproj.io/hook: PostSync
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: init
          image: postgres:16-alpine
          command:
            - sh
            - -c
            - |
              until pg_isready -h postgres-vk -U vibekanban; do sleep 2; done
              PGPASSWORD="$POSTGRES_PASSWORD" psql -h postgres-vk -U vibekanban -d vibekanban -c "
                DO \$\$
                BEGIN
                  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'electric') THEN
                    CREATE ROLE electric WITH LOGIN PASSWORD '$ELECTRIC_PASSWORD' REPLICATION;
                  END IF;
                END
                \$\$;
                GRANT ALL ON DATABASE vibekanban TO electric;
                GRANT ALL ON SCHEMA public TO electric;
                ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO electric;
              "
          env:
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: vk-remote-secrets
                  key: POSTGRES_PASSWORD
            - name: ELECTRIC_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: vk-remote-secrets
                  key: ELECTRIC_ROLE_PASSWORD
  backoffLimit: 5
```

### Task 5: Create ElectricSQL Deployment

**Files:**
- Create: `apps/vk-remote/manifests/electric.yaml`

- [x] **Step 1: Write the ElectricSQL Deployment and Service**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: electric
  namespace: agents
spec:
  replicas: 1
  selector:
    matchLabels:
      app: electric
  template:
    metadata:
      labels:
        app: electric
    spec:
      containers:
        - name: electric
          image: electricsql/electric:1.4.13
          ports:
            - containerPort: 3000
          env:
            - name: ELECTRIC_ROLE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: vk-remote-secrets
                  key: ELECTRIC_ROLE_PASSWORD
            - name: DATABASE_URL
              value: "postgresql://electric:$(ELECTRIC_ROLE_PASSWORD)@postgres-vk:5432/vibekanban?sslmode=disable"
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 200m
              memory: 128Mi
---
apiVersion: v1
kind: Service
metadata:
  name: electric
  namespace: agents
spec:
  selector:
    app: electric
  ports:
    - port: 3000
      targetPort: 3000
```

### Task 6: Create vk-remote Deployment

**Files:**
- Create: `apps/vk-remote/manifests/deployment.yaml`

- [x] **Step 1: Write the vk-remote Deployment**

Replace `<IMAGE_SHA>` with the SHA from Phase 0, Task 4.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vk-remote
  namespace: agents
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vk-remote
  template:
    metadata:
      labels:
        app: vk-remote
    spec:
      containers:
        - name: vk-remote
          image: ghcr.io/derio-net/vk-remote:<IMAGE_SHA>
          ports:
            - containerPort: 8081
          env:
            - name: PORT
              value: "8081"
            - name: HOST
              value: "0.0.0.0"
            - name: NODE_ENV
              value: "production"
            - name: ELECTRIC_URL
              value: "http://electric:3000"
            - name: SELF_HOST_LOCAL_AUTH_EMAIL
              value: "admin@localhost"
            - name: VIBEKANBAN_REMOTE_JWT_SECRET
              valueFrom:
                secretKeyRef:
                  name: vk-remote-secrets
                  key: VIBEKANBAN_REMOTE_JWT_SECRET
            - name: SELF_HOST_LOCAL_AUTH_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: vk-remote-secrets
                  key: SELF_HOST_LOCAL_AUTH_PASSWORD
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: vk-remote-secrets
                  key: POSTGRES_PASSWORD
            - name: SERVER_DATABASE_URL
              value: "postgresql://vibekanban:$(POSTGRES_PASSWORD)@postgres-vk:5432/vibekanban?sslmode=disable"
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 256Mi
---
apiVersion: v1
kind: Service
metadata:
  name: vk-remote
  namespace: agents
spec:
  selector:
    app: vk-remote
  ports:
    - port: 8081
      targetPort: 8081
```

### Task 7: Create ArgoCD Application CR

**Files:**
- Create: `apps/root/templates/vk-remote.yaml`

- [x] **Step 1: Write the Application template**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: vk-remote
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: {{ .Values.spec.source.repoURL }}
    targetRevision: {{ .Values.spec.source.targetRevision }}
    path: apps/vk-remote/manifests
  destination:
    server: {{ .Values.spec.destination.server }}
    namespace: agents
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      jsonPointers:
        - /data
```

### Task 8: Add IngressRoute for vk-remote

**Files:**
- Modify: `apps/traefik/manifests/ingressroutes.yaml`

- [x] **Step 1: Append the VK Remote IngressRoute**

Add to the end of the file:

```yaml
---
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: vk-remote
  namespace: traefik-system
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`vk.cluster.derio.net`)
      kind: Rule
      middlewares:
        - name: ip-allowlist
        - name: security-headers
        - name: authentik-forwardauth
      services:
        - name: vk-remote
          namespace: agents
          port: 8081
  tls:
    certResolver: cloudflare
    domains:
      - main: "*.cluster.derio.net"
```

### Task 9: Add Authentik proxy provider for VK Remote

**Files:**
- Modify: `apps/authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml`

- [x] **Step 1: Append VK Remote proxy provider and application entries**

Add to the entries list in the blueprint:

```yaml
- model: authentik_providers_proxy.proxyprovider
  state: present
  identifiers:
    name: VK Remote (cluster)
  id: provider-vk-remote-cluster
  attrs:
    authorization_flow: !Find [authentik_flows.flow, [slug, default-provider-authorization-implicit-consent]]
    authentication_flow: !Find [authentik_flows.flow, [slug, default-authentication-flow]]
    invalidation_flow: !Find [authentik_flows.flow, [slug, default-provider-invalidation-flow]]
    mode: forward_single
    external_host: https://vk.cluster.derio.net

- model: authentik_core.application
  state: present
  identifiers:
    slug: vk-remote-cluster
  attrs:
    name: VK Remote (cluster)
    provider: !KeyOf provider-vk-remote-cluster
    meta_launch_url: https://vk.cluster.derio.net
```

### Task 10: Add secure-agent-pod VK_SHARED_API_BASE

**Files:**
- Modify: `apps/secure-agent-pod/manifests/deployment.yaml`

- [x] **Step 1: Add VK_SHARED_API_BASE env var**

Add to the container's `env` list:

```yaml
- name: VK_SHARED_API_BASE
  value: "http://vk-remote.agents.svc.cluster.local:8081"
```

### Task 11: Add homepage entry

**Files:**
- Modify: `apps/homepage/manifests/configmap-services.yaml`

- [x] **Step 1: Add VK Remote to the Development section**

```yaml
- VK Remote:
    icon: kanban
    href: https://vk.cluster.derio.net
    description: VibeKanban self-hosted kanban board
    siteMonitor: http://vk-remote.agents:8081
```

### Task 12: Commit all manifests

- [x] **Step 1: Stage and commit**

```bash
git add apps/vk-remote/ apps/root/templates/vk-remote.yaml apps/traefik/manifests/ingressroutes.yaml apps/authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml apps/secure-agent-pod/manifests/deployment.yaml apps/homepage/manifests/configmap-services.yaml
git commit -m "feat(agents): add vk-remote self-hosted deployment manifests"
```

---

## Phase 2: Deploy & Configure [manual]
<!-- Tracking: https://github.com/derio-net/frank/issues/63 -->

After Phase 1 is merged and ArgoCD syncs, perform these manual steps.

### Task 1: Verify ArgoCD sync

1. `source .env`
2. `argocd app get vk-remote --port-forward --port-forward-namespace argocd`
3. Confirm all resources are Healthy/Synced
4. Check pods: `kubectl -n agents get pods` — expect `postgres-vk`, `electric`, `vk-remote` all Running
5. Check init Job completed: `kubectl -n agents get jobs` — `postgres-vk-init-electric` should be Complete

### Task 2: Verify health endpoint

```bash
kubectl -n agents exec deploy/vk-remote -- wget -qO- http://localhost:8081/v1/health
```

Expected: 200 OK (or equivalent health response).

### Task 3: Login and create org/project

1. Get the local auth password:
   ```bash
   kubectl -n agents get secret vk-remote-secrets -o jsonpath='{.data.SELF_HOST_LOCAL_AUTH_PASSWORD}' | base64 -d
   ```

2. Login via API:
   ```bash
   TOKEN=$(curl -s -X POST http://vk-remote.agents.svc:8081/v1/auth/local/login \
     -H 'Content-Type: application/json' \
     -d '{"email":"admin@localhost","password":"<PASSWORD>"}' | jq -r '.token')
   ```

   If running from outside the cluster, port-forward first:
   ```bash
   kubectl -n agents port-forward svc/vk-remote 8081:8081
   # Then use localhost:8081
   ```

3. Login creates a personal org automatically. List orgs to get the org ID:
   ```bash
   curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8081/v1/organizations | jq
   ```

4. Create the "Derio Ops" project:
   ```bash
   curl -s -X POST http://localhost:8081/v1/projects \
     -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"name":"Derio Ops","organization_id":"<ORG_ID>"}' | jq
   ```

5. Record the `org_id` and `project_id` from the responses.

6. Configure project statuses (if not auto-created):
   ```bash
   for status in Backlog Todo "In Progress" "In Review" Done; do
     curl -s -X POST http://localhost:8081/v1/projects/<PROJECT_ID>/statuses \
       -H "Authorization: Bearer $TOKEN" \
       -H 'Content-Type: application/json' \
       -d "{\"name\":\"$status\"}"
   done
   ```

### Task 4: Update bridge env vars

Add to Infisical (`frank-cluster-iwpg`, `prod`):

| Key | Value |
|-----|-------|
| `VK_ORG_ID` | Org ID from Task 3 |
| `VK_DERIO_OPS_PROJECT` | Project ID from Task 3 |

If these are consumed by the secure-agent-pod via ExternalSecret, add them to the appropriate ExternalSecret mapping. Otherwise, update the deployment env vars directly and commit.

### Task 5: Assign Authentik outpost provider

After the Authentik blueprint syncs the VK Remote proxy provider:

```bash
kubectl exec -n authentik deploy/authentik-server -- python -c "
import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','authentik.root.settings')
import django; django.setup()
from authentik.providers.proxy.models import ProxyProvider
from authentik.outposts.models import Outpost
outpost = Outpost.objects.get(name='authentik Embedded Outpost')
provider = ProxyProvider.objects.get(name='VK Remote (cluster)')
outpost.providers.add(provider)
print(f'Added {provider.name} to {outpost.name}')
"
```

### Task 6: Verify browser access

1. Open `https://vk.cluster.derio.net` in browser
2. Should redirect through Authentik SSO
3. After auth, VK Remote UI should load
4. Verify the "Derio Ops" project is visible

### Task 7: End-to-end bridge test

1. SSH into secure-agent-pod
2. Verify VK_SHARED_API_BASE is set:
   ```bash
   echo $VK_SHARED_API_BASE
   # Expected: http://vk-remote.agents.svc.cluster.local:8081
   ```
3. Test MCP tools:
   ```bash
   vk remote list-organizations
   vk remote list-projects
   ```
4. Create a test issue via the bridge or MCP and verify it appears in the browser UI
5. Delete the test issue

---

## Phase 3: Post-Deploy Checklist [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/64 -->

- [ ] **Step 1: Write building blog post** — Use `/blog-post` skill. Update series index in `blog/content/building/00-overview/index.md` and cluster roadmap in `blog/layouts/shortcodes/cluster-roadmap.html`
- [ ] **Step 2: Write operating blog post** — Use `/blog-post` skill for the companion operating guide. Update operating series index in `blog/content/building/00-overview/index.md`
- [ ] **Step 3: Update README** — Run `/update-readme` to sync Technology Stack, Repository Structure, Service Access, and Current Status
- [ ] **Step 4: Sync runbook** — Run `/sync-runbook` if the plan contains any `# manual-operation` blocks
- [ ] **Step 5: Update plan status** — Set `**Status:**` to `Deployed`
