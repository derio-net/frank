# In-Cluster Ingress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy Traefik as an in-cluster ingress controller with ACME TLS and Authentik forward-auth, serving all cluster services under `*.cluster.derio.net`, plus a Homepage dashboard.

**Architecture:** Traefik runs as a single-replica Deployment on raspi edge nodes, exposed via Cilium L2 LoadBalancer at 192.168.55.220. Built-in ACME handles wildcard TLS via Cloudflare DNS-01. Middlewares provide IP allowlisting, security headers, and Authentik forward-auth. A gethomepage.dev instance serves as the cluster landing page.

**Tech Stack:** Traefik v3 (Helm chart), Traefik CRDs (IngressRoute, Middleware), cert via built-in ACME, Authentik forward-auth, gethomepage.dev, ArgoCD App-of-Apps

**Spec:** `docs/superpowers/specs/2026-03-29--net--in-cluster-ingress-design.md`
**Status:** Not Started

**IMPORTANT:** Do NOT `git push` until Task 9 Step 4. ArgoCD will try to sync Traefik immediately on push, and the SOPS secret (Task 9 Step 1) must exist in the cluster first. All commits in Tasks 1-8 are local only.

---

### Task 1: Verify backend service names and ports

Before writing any IngressRoutes, resolve all VERIFY markers from the spec by checking actual deployed services.

**Files:**
- None created or modified — this is a discovery task

- [ ] **Step 1: Source the Frank cluster environment**

```bash
source .env
```

- [ ] **Step 2: List all ClusterIP and LoadBalancer services**

```bash
kubectl get svc -A -o wide | grep -E '(ClusterIP|LoadBalancer)' | sort -k1,1
```

- [ ] **Step 3: Resolve each VERIFY marker**

Record the actual service name, namespace, and port for each:

| Spec Reference | What to find |
|---------------|-------------|
| `sympozium ClusterIP in sympozium-system` | The ClusterIP service name for the Sympozium API server |
| `authentik-server.authentik ClusterIP port` | Which port (80 or 9000) the ClusterIP service exposes |
| `victoria-metrics-grafana.monitoring` | The actual Grafana service name (deployed as VM sub-chart) |
| `infisical ClusterIP in infisical ns` | The actual Infisical ClusterIP service name |
| `paperclip ClusterIP in paperclip-system` | Whether a ClusterIP service exists (or only LB) |

If any service only has a LoadBalancer type with no ClusterIP, note it — we'll need to create a ClusterIP service in that app's `-extras` manifests or reference the LB service directly.

- [ ] **Step 4: Check Authentik outpost forward-auth port**

```bash
kubectl get svc -n authentik -o wide
```

Determine whether `/outpost.goauthentik.io/auth/traefik` is reachable on the ClusterIP service's port 80 or port 9000.

- [ ] **Step 5: Record findings**

Note the discovered service names, namespaces, and ports. These will be used directly in Tasks 5 and 6 when creating middlewares and IngressRoutes. No need to commit — just carry the values forward into the manifest files.

---

### Task 2: Create Traefik ArgoCD Application CR

**Files:**
- Create: `apps/root/templates/traefik.yaml`

- [ ] **Step 1: Research the current Traefik Helm chart version**

```bash
helm repo add traefik https://traefik.github.io/charts 2>/dev/null || true
helm repo update traefik
helm search repo traefik/traefik --versions | head -5
```

Note the latest chart version (expected: `36.x.x` range). Pin to the exact latest patch.

- [ ] **Step 2: Create the Application CR**

Create `apps/root/templates/traefik.yaml` following the multi-source pattern from `litellm.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: traefik
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://traefik.github.io/charts
      chart: traefik
      targetRevision: "<VERSION_FROM_STEP_1>"
      helm:
        releaseName: traefik
        valueFiles:
          - $values/apps/traefik/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: traefik-system
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

- [ ] **Step 3: Commit**

```bash
git add apps/root/templates/traefik.yaml
git commit -m "feat(net): add Traefik ArgoCD Application CR"
```

---

### Task 3: Create Traefik Extras ArgoCD Application CR

**Files:**
- Create: `apps/root/templates/traefik-extras.yaml`

- [ ] **Step 1: Create the extras Application CR**

Create `apps/root/templates/traefik-extras.yaml` following the `-extras` pattern from `authentik-extras.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: traefik-extras
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/traefik/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: traefik-system
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
      - CreateNamespace=false
```

- [ ] **Step 2: Commit**

```bash
git add apps/root/templates/traefik-extras.yaml
git commit -m "feat(net): add Traefik Extras ArgoCD Application CR"
```

---

### Task 4: Create Traefik Helm values

**Files:**
- Create: `apps/traefik/values.yaml`

**Docs to check:**
- Traefik Helm chart values: https://github.com/traefik/traefik-helm-chart/blob/master/traefik/values.yaml
- Traefik ACME DNS challenge: https://doc.traefik.io/traefik/https/acme/#dnschallenge

- [ ] **Step 1: Create the values file**

Create `apps/traefik/values.yaml`:

```yaml
# Traefik In-Cluster Ingress Controller
# Spec: docs/superpowers/specs/2026-03-29--net--in-cluster-ingress-design.md

deployment:
  replicas: 1

# RWO PVC requires Recreate strategy (see frank-gotchas.md)
updateStrategy:
  type: Recreate

# Schedule on raspi edge nodes
nodeSelector:
  zone: edge
  tier: low-power

# Cilium L2 LoadBalancer with static IP
service:
  type: LoadBalancer
  annotations:
    lbipam.cilium.io/ips: "192.168.55.220"

# Entrypoints
ports:
  web:
    exposedPort: 80
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
          permanent: true
  websecure:
    exposedPort: 443

# Allow IngressRoutes to reference services in other namespaces
providers:
  kubernetesCRD:
    allowCrossNamespace: true

# Built-in ACME — wildcard cert via Cloudflare DNS-01
certificatesResolvers:
  cloudflare:
    acme:
      email: "familiedermitzaki@gmail.com"
      storage: /data/acme.json
      dnsChallenge:
        provider: cloudflare
        disablePropagationCheck: true

# Persist ACME cert data on Longhorn
persistence:
  enabled: true
  size: 128Mi
  accessMode: ReadWriteOnce

# Cloudflare API token from SOPS-encrypted Secret
env:
  - name: CF_DNS_API_TOKEN
    valueFrom:
      secretKeyRef:
        name: traefik-cloudflare-credentials
        key: api-token

# Disable Traefik dashboard (accessed via ArgoCD, not needed)
ingressRoute:
  dashboard:
    enabled: false
```

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('apps/traefik/values.yaml'))"
```

Expected: no output (valid YAML).

- [ ] **Step 3: Commit**

```bash
git add apps/traefik/values.yaml
git commit -m "feat(net): add Traefik Helm values with ACME and Cilium L2"
```

---

### Task 5: Create Middleware CRDs

**Files:**
- Create: `apps/traefik/manifests/middlewares.yaml`

- [ ] **Step 1: Create the middlewares file**

Create `apps/traefik/manifests/middlewares.yaml` with all four Middleware CRDs. Use the Authentik service port discovered in Task 1.

```yaml
# Traefik Middleware CRDs for *.cluster.derio.net
# Spec: docs/superpowers/specs/2026-03-29--net--in-cluster-ingress-design.md
---
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: security-headers
  namespace: traefik-system
spec:
  headers:
    frameDeny: true
    browserXssFilter: true
    contentTypeNosniff: true
    forceSTSHeader: true
    stsIncludeSubdomains: true
    stsPreload: true
    stsSeconds: 15552000
    customFrameOptionsValue: SAMEORIGIN
    referrerPolicy: strict-origin-when-cross-origin
    customRequestHeaders:
      X-Forwarded-Proto: https
    customResponseHeaders:
      X-Robots-Tag: none
---
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: ip-allowlist
  namespace: traefik-system
spec:
  ipAllowList:
    sourceRange:
      - "10.0.0.0/8"
      - "192.168.0.0/16"
      - "172.16.0.0/12"
---
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: authentik-forwardauth
  namespace: traefik-system
spec:
  forwardAuth:
    # Port: use value discovered in Task 1
    address: "http://authentik-server.authentik.svc.cluster.local:<DISCOVERED_PORT>/outpost.goauthentik.io/auth/traefik"
    trustForwardHeader: true
    authResponseHeaders:
      - X-authentik-username
      - X-authentik-groups
      - X-authentik-email
      - X-authentik-name
      - X-authentik-uid
      - X-authentik-jwt
      - X-authentik-meta-jwks
      - X-authentik-meta-outpost
      - X-authentik-meta-provider
      - X-authentik-meta-app
      - X-authentik-meta-version
```

Note: the spec mentions "Four Middleware CRDs" but only 3 are created here. The `https-redirect` middleware is NOT needed as a CRD — HTTP→HTTPS redirect is handled at the entrypoint level in the Helm values (`ports.web.http.redirections`). This is a deliberate deviation: entrypoint-level redirects are more reliable than per-route middleware.

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "
import yaml
for doc in yaml.safe_load_all(open('apps/traefik/manifests/middlewares.yaml')):
    if doc: print(f'{doc[\"kind\"]}/{doc[\"metadata\"][\"name\"]}')
"
```

Expected:
```
Middleware/security-headers
Middleware/ip-allowlist
Middleware/authentik-forwardauth
```

- [ ] **Step 3: Commit**

```bash
git add apps/traefik/manifests/middlewares.yaml
git commit -m "feat(net): add Traefik middleware CRDs for security and auth"
```

---

### Task 6: Create IngressRoute CRDs

**Files:**
- Create: `apps/traefik/manifests/ingressroutes.yaml`

Use the service names/ports discovered in Task 1 to fill in all backend references.

- [ ] **Step 1: Create the IngressRoutes file**

Create `apps/traefik/manifests/ingressroutes.yaml` with one IngressRoute per deployed service. The template for each route follows one of two patterns:

**Pattern A — no forward-auth (ArgoCD, Sympozium, Authentik, Homepage):**

```yaml
---
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: <service-name>
  namespace: traefik-system
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`<service>.cluster.derio.net`)
      kind: Rule
      middlewares:
        - name: ip-allowlist
        - name: security-headers
      services:
        - name: <DISCOVERED_SERVICE_NAME>
          namespace: <DISCOVERED_NAMESPACE>
          port: <DISCOVERED_PORT>
  tls:
    certResolver: cloudflare
    domains:
      - main: "*.cluster.derio.net"
```

**Pattern B — with forward-auth (Longhorn, Hubble, Grafana, Infisical, LiteLLM, Paperclip, ComfyUI, GPU Switcher):**

Same as Pattern A but with an additional middleware:

```yaml
      middlewares:
        - name: ip-allowlist
        - name: security-headers
        - name: authentik-forwardauth
```

Create 12 IngressRoute documents in total (all deployed services from the spec routing table), using the actual service names discovered in Task 1.

Route order in the file:
1. `master.cluster.derio.net` → homepage (none)
2. `argocd.cluster.derio.net` → argocd-server (none)
3. `sympozium.cluster.derio.net` → sympozium (none)
4. `auth.cluster.derio.net` → authentik-server (none)
5. `grafana.cluster.derio.net` → grafana (forward-auth)
6. `longhorn.cluster.derio.net` → longhorn-frontend (forward-auth)
7. `hubble.cluster.derio.net` → hubble-ui (forward-auth)
8. `infisical.cluster.derio.net` → infisical (forward-auth)
9. `litellm.cluster.derio.net` → litellm (forward-auth)
10. `paperclip.cluster.derio.net` → paperclip (forward-auth)
11. `comfyui.cluster.derio.net` → comfyui (forward-auth)
12. `gpu.cluster.derio.net` → gpu-switcher (forward-auth)

- [ ] **Step 2: Verify YAML syntax and count**

```bash
python3 -c "
import yaml
docs = [d for d in yaml.safe_load_all(open('apps/traefik/manifests/ingressroutes.yaml')) if d]
print(f'{len(docs)} IngressRoutes:')
for d in docs:
    name = d['metadata']['name']
    host = d['spec']['routes'][0]['match']
    mws = [m['name'] for m in d['spec']['routes'][0].get('middlewares', [])]
    print(f'  {name}: {host} middlewares={mws}')
"
```

Expected: 12 IngressRoutes listed with correct hostnames and middleware assignments.

- [ ] **Step 3: Commit**

```bash
git add apps/traefik/manifests/ingressroutes.yaml
git commit -m "feat(net): add IngressRoute CRDs for all cluster services"
```

---

### Task 7: Create Homepage ArgoCD Application CR

**Files:**
- Create: `apps/root/templates/homepage.yaml`

- [ ] **Step 1: Create the Application CR**

Create `apps/root/templates/homepage.yaml` following the raw-manifests pattern from `comfyui.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: homepage
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/homepage/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: homepage
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

- [ ] **Step 2: Commit**

```bash
git add apps/root/templates/homepage.yaml
git commit -m "feat(net): add Homepage ArgoCD Application CR"
```

---

### Task 8: Create Homepage manifests

**Files:**
- Create: `apps/homepage/manifests/deployment.yaml`
- Create: `apps/homepage/manifests/service.yaml`
- Create: `apps/homepage/manifests/configmap-services.yaml`
- Create: `apps/homepage/manifests/configmap-settings.yaml`

**Docs to check:**
- Homepage Docker docs: https://gethomepage.dev/installation/docker/
- Homepage Kubernetes docs: https://gethomepage.dev/installation/k8s/
- Homepage service widgets: https://gethomepage.dev/configs/services/

- [ ] **Step 1: Create the Deployment**

Create `apps/homepage/manifests/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: homepage
  namespace: homepage
  labels:
    app: homepage
spec:
  replicas: 1
  selector:
    matchLabels:
      app: homepage
  template:
    metadata:
      labels:
        app: homepage
    spec:
      nodeSelector:
        zone: edge
      containers:
        - name: homepage
          image: ghcr.io/gethomepage/homepage:v1.12.1
          ports:
            - containerPort: 3000
              name: http
          volumeMounts:
            - name: config-services
              mountPath: /app/config/services.yaml
              subPath: services.yaml
            - name: config-settings
              mountPath: /app/config/settings.yaml
              subPath: settings.yaml
      volumes:
        - name: config-services
          configMap:
            name: homepage-services
        - name: config-settings
          configMap:
            name: homepage-settings
```

- [ ] **Step 2: Create the Service**

Create `apps/homepage/manifests/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: homepage
  namespace: homepage
  labels:
    app: homepage
spec:
  type: ClusterIP
  selector:
    app: homepage
  ports:
    - port: 3000
      targetPort: http
      name: http
```

- [ ] **Step 3: Create the services ConfigMap**

Create `apps/homepage/manifests/configmap-services.yaml`. Consult Homepage docs for the exact YAML schema. The services list should include all cluster services organized by category, using `*.cluster.derio.net` URLs:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: homepage-services
  namespace: homepage
data:
  services.yaml: |
    - Infrastructure:
        - ArgoCD:
            icon: argo-cd
            href: https://argocd.cluster.derio.net
            description: GitOps continuous delivery for Kubernetes
        - Longhorn:
            icon: longhorn
            href: https://longhorn.cluster.derio.net
            description: Distributed block storage for Kubernetes
        - Hubble:
            icon: cilium
            href: https://hubble.cluster.derio.net
            description: Cilium network observability
        - Grafana:
            icon: grafana
            href: https://grafana.cluster.derio.net
            description: Metrics dashboards and observability
        - Infisical:
            icon: infisical
            href: https://infisical.cluster.derio.net
            description: Secrets management platform
        - Authentik:
            icon: authentik
            href: https://auth.cluster.derio.net
            description: Identity provider and SSO
    - Development:
        - LiteLLM:
            icon: mdi-robot
            href: https://litellm.cluster.derio.net
            description: LLM proxy and gateway
        - Sympozium:
            icon: element
            href: https://sympozium.cluster.derio.net
            description: Matrix chat client
        - Paperclip:
            icon: mdi-paperclip
            href: https://paperclip.cluster.derio.net
            description: AI agent orchestrator
        - ComfyUI:
            icon: mdi-alpha-c-box-outline
            href: https://comfyui.cluster.derio.net
            description: Visual editor for diffusion model pipelines
        - GPU Switcher:
            icon: mdi-expansion-card
            href: https://gpu.cluster.derio.net
            description: Dashboard for managing GPU time-sharing
```

Note: Gitea, Harbor, KubeVirt, and n8n are omitted because they're not yet deployed. Add them when their ArgoCD apps are created (per the Claude rule update in Task 10).

- [ ] **Step 4: Create the settings ConfigMap**

Create `apps/homepage/manifests/configmap-settings.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: homepage-settings
  namespace: homepage
data:
  settings.yaml: |
    title: Frank Cluster
    background:
      opacity: 50
    theme: dark
    color: zinc
    headerStyle: clean
    layout:
      Infrastructure:
        style: row
        columns: 3
      Development:
        style: row
        columns: 3
```

- [ ] **Step 5: Verify all manifests parse correctly**

```bash
for f in apps/homepage/manifests/*.yaml; do
  echo "--- $f ---"
  python3 -c "import yaml; [print(f'{d[\"kind\"]}/{d[\"metadata\"][\"name\"]}') for d in yaml.safe_load_all(open('$f')) if d]"
done
```

Expected: Deployment/homepage, Service/homepage, ConfigMap/homepage-services, ConfigMap/homepage-settings

- [ ] **Step 6: Commit**

```bash
git add apps/homepage/manifests/
git commit -m "feat(net): add Homepage dashboard manifests"
```

---

### Task 9: Manual operations — SOPS Secret, Pi-hole DNS, Authentik Provider

This task contains manual operations that require user interaction. The implementing agent should prompt the user to perform each step.

**Files:**
- Create: `secrets/traefik-cloudflare-credentials.yaml` (SOPS-encrypted)

- [ ] **Step 1: Create and encrypt the Cloudflare credentials Secret**

```yaml
# manual-operation
id: net-traefik-cloudflare-secret
layer: net
app: traefik
plan: 2026-03-29--net--in-cluster-ingress
when: Before Traefik deployment
why_manual: Bootstrap secret must exist before Traefik starts ACME challenge
commands:
  - |
    cat <<EOF > secrets/traefik-cloudflare-credentials.yaml
    apiVersion: v1
    kind: Secret
    metadata:
      name: traefik-cloudflare-credentials
      namespace: traefik-system
    type: Opaque
    stringData:
      api-token: "<CF_DNS_API_TOKEN value from .env_hop>"
    EOF
  - sops --encrypt --in-place secrets/traefik-cloudflare-credentials.yaml
  - kubectl create namespace traefik-system || true
  - sops --decrypt secrets/traefik-cloudflare-credentials.yaml | kubectl apply -f -
verify:
  - kubectl get secret traefik-cloudflare-credentials -n traefik-system
status: pending
```

Prompt user to execute these commands. Verify the secret exists after creation.

- [ ] **Step 2: Configure Pi-hole DNS**

```yaml
# manual-operation
id: net-pihole-cluster-wildcard
layer: net
app: traefik
plan: 2026-03-29--net--in-cluster-ingress
when: Before testing IngressRoutes
why_manual: Pi-hole DNS is managed via web UI, not declarative
commands:
  - "Pi-hole Admin → Local DNS → DNS Records"
  - "Add: *.cluster.derio.net → 192.168.55.220"
  - "Repeat on both Pi-hole instances"
verify:
  - nslookup master.cluster.derio.net
  - nslookup grafana.cluster.derio.net
status: pending
```

Prompt user to configure DNS. Verify resolution works after configuration.

- [ ] **Step 3: Commit the encrypted secret**

```bash
git add secrets/traefik-cloudflare-credentials.yaml
git commit -m "feat(net): add SOPS-encrypted Cloudflare credentials for Traefik"
```

- [ ] **Step 4: Push all commits and verify ArgoCD sync**

```bash
git push
```

Wait for ArgoCD to detect the new applications. Verify:

```bash
source .env
argocd app list --port-forward --port-forward-namespace argocd | grep -E '(traefik|homepage)'
```

Expected: `traefik`, `traefik-extras`, and `homepage` apps visible (may show as `OutOfSync` or `Syncing`).

- [ ] **Step 5: Verify Traefik pod is running**

```bash
kubectl get pods -n traefik-system
kubectl logs -n traefik-system -l app.kubernetes.io/name=traefik --tail=20
```

Expected: Traefik pod running on a raspi node. Logs should show ACME certificate request for `*.cluster.derio.net`.

- [ ] **Step 6: Verify ACME certificate was issued**

```bash
kubectl logs -n traefik-system -l app.kubernetes.io/name=traefik | grep -i "acme\|certificate\|challenge"
```

Expected: Successful certificate issuance from Let's Encrypt via Cloudflare DNS-01.

- [ ] **Step 7: Test a no-auth route**

```bash
curl -sI https://argocd.cluster.derio.net 2>&1 | head -20
```

Expected: HTTP 200 or 302 (ArgoCD login redirect), valid TLS certificate for `*.cluster.derio.net`.

- [ ] **Step 8: Create Authentik Proxy Provider**

```yaml
# manual-operation
id: net-authentik-cluster-proxy-provider
layer: net
app: authentik
plan: 2026-03-29--net--in-cluster-ingress
when: Before testing forward-auth services
why_manual: Authentik provider/app creation requires API or UI interaction
commands:
  - "Create Proxy Provider in Authentik (forward-auth mode)"
  - "External host: https://*.cluster.derio.net"
  - "Note: redirect_uris must be list of objects [{matching_mode: strict, url: ...}]"
  - "Note: signing_key UUID — query an existing provider to find it"
  - "Add the provider to the embedded outpost"
verify:
  - "curl -k https://longhorn.cluster.derio.net → redirects to Authentik login"
  - "After login → Longhorn UI loads"
status: pending
```

Prompt user to create the Authentik provider. Verify forward-auth works.

- [ ] **Step 9: Test a forward-auth route**

```bash
curl -sI https://longhorn.cluster.derio.net 2>&1 | head -20
```

Expected: HTTP 302 redirect to Authentik login page.

- [ ] **Step 10: Verify Homepage loads**

```bash
curl -sI https://master.cluster.derio.net 2>&1 | head -20
```

Expected: HTTP 200 with Homepage content.

---

### Task 10: Update Claude rules and infrastructure docs

**Files:**
- Modify: `.claude/rules/frank-argocd.md`
- Modify: `.claude/rules/frank-infrastructure.md`

- [ ] **Step 1: Update frank-argocd.md**

Append to `.claude/rules/frank-argocd.md`:

```markdown
### Homepage Dashboard

When adding a new outward-facing service with an IngressRoute:
1. Add the service to `apps/homepage/manifests/configmap-services.yaml` (icon, category, description, URL)
2. Add the IngressRoute to `apps/traefik/manifests/ingressroutes.yaml`
```

- [ ] **Step 2: Update frank-infrastructure.md Services table**

Add to the Services table in `.claude/rules/frank-infrastructure.md`:

```markdown
| Traefik Ingress | 192.168.55.220 | Cilium L2 LoadBalancer |
| Homepage | (via Traefik) | IngressRoute (master.cluster.derio.net) |
```

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/frank-argocd.md .claude/rules/frank-infrastructure.md
git commit -m "docs(net): update Claude rules for Homepage and Traefik ingress"
```

---

### Task 11: Sync manual operations runbook

**Files:**
- Modify: `docs/runbooks/manual-operations.yaml`

- [ ] **Step 1: Run the sync-runbook skill**

Use `/sync-runbook` to sync the 3 manual operation blocks from the spec into `docs/runbooks/manual-operations.yaml`.

- [ ] **Step 2: Verify all 3 manual ops are in the runbook**

```bash
grep -c "net-traefik-cloudflare-secret\|net-pihole-cluster-wildcard\|net-authentik-cluster-proxy-provider" docs/runbooks/manual-operations.yaml
```

Expected: 3

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/manual-operations.yaml
git commit -m "docs(net): sync manual operations for in-cluster ingress"
```

---

### Task 12: Final verification and spec status update

- [ ] **Step 1: Verify all routes**

Test each deployed IngressRoute:

```bash
for host in master argocd sympozium auth grafana longhorn hubble infisical litellm paperclip comfyui gpu; do
  status=$(curl -sI -o /dev/null -w "%{http_code}" "https://${host}.cluster.derio.net" 2>/dev/null)
  echo "${host}.cluster.derio.net → HTTP ${status}"
done
```

Expected:
- `master`, `argocd`, `sympozium`, `auth` → 200 or 302 (app login)
- `grafana`, `longhorn`, `hubble`, `infisical`, `litellm`, `paperclip`, `comfyui`, `gpu` → 302 (Authentik redirect) or 200 (if already authenticated)

- [ ] **Step 2: Verify Homepage shows all services**

Open `https://master.cluster.derio.net` in a browser. Verify:
- Infrastructure category shows: ArgoCD, Longhorn, Hubble, Grafana, Infisical, Authentik
- Development category shows: LiteLLM, Sympozium, Paperclip, ComfyUI, GPU Switcher
- All links work and point to `*.cluster.derio.net` URLs

- [ ] **Step 3: Update spec status**

Change the status in `docs/superpowers/specs/2026-03-29--net--in-cluster-ingress-design.md`:

```markdown
**Status:** Deployed
```

- [ ] **Step 4: Final commit**

```bash
git add docs/superpowers/specs/2026-03-29--net--in-cluster-ingress-design.md
git commit -m "feat(net): mark in-cluster ingress spec as deployed"
git push
```
