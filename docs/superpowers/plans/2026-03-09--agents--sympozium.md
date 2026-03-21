# Sympozium Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy Sympozium (Kubernetes-native agentic control plane) on Frank via ArgoCD, with cert-manager as a prerequisite, LiteLLM as the LLM backend, and built-in PersonaPacks for cluster ops + dev workflows.

**Architecture:** Three ArgoCD apps — `cert-manager` (Helm, webhook TLS), `sympozium` (Helm, control plane), `sympozium-extras` (raw manifests, CRs). Agents route through existing LiteLLM gateway for access to local Ollama + cloud models. Web dashboard exposed at 192.168.55.207.

**Tech Stack:** Sympozium v0.1.0 Helm chart (OCI), cert-manager v1.17.1, NATS JetStream (bundled), ExternalSecrets for Infisical, Cilium L2 LoadBalancer.

**Design doc:** `docs/superpowers/specs/2026-03-09--agents--sympozium-design.md`
**Status:** Deployed

---

### Task 1: cert-manager ArgoCD Application

Deploy cert-manager as a standalone ArgoCD app. This is a prerequisite for Sympozium's admission webhook TLS.

**Files:**
- Create: `apps/cert-manager/values.yaml`
- Create: `apps/root/templates/cert-manager.yaml`

**Step 1: Create cert-manager Helm values**

Create `apps/cert-manager/values.yaml`:

```yaml
# cert-manager — X.509 certificate management for Kubernetes
# Required by Sympozium for admission webhook TLS
# Deployed as Agents layer prerequisite

# Install CRDs with the chart
crds:
  enabled: true

# Minimal install — just webhook TLS for Sympozium
# No additional issuers or certificates configured
```

**Step 2: Create cert-manager Application CR**

Create `apps/root/templates/cert-manager.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: cert-manager
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-1"
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://charts.jetstack.io
      chart: cert-manager
      targetRevision: "1.17.1"
      helm:
        releaseName: cert-manager
        valueFiles:
          - $values/apps/cert-manager/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: cert-manager
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

**Step 3: Commit**

```bash
git add apps/cert-manager/values.yaml apps/root/templates/cert-manager.yaml
git commit -m "feat(phase11): add cert-manager ArgoCD application

Prerequisite for Sympozium webhook TLS. Sync wave -1 ensures
it deploys before Sympozium."
```

---

### Task 2: Sympozium Helm ArgoCD Application

Deploy the Sympozium control plane via the OCI Helm chart.

**Files:**
- Create: `apps/sympozium/values.yaml`
- Create: `apps/root/templates/sympozium.yaml`

**Step 1: Research Helm chart values**

Before writing values, verify the chart's configurable fields:

```bash
helm show values oci://ghcr.io/alexsjones/sympozium/charts/sympozium --version 0.1.0 > /tmp/sympozium-values.yaml
```

Review the output to confirm field names for: `apiserver.service`, `nats.persistence`, `certManager`, `observability`, `defaultPersonas`, `networkPolicies`. Adjust Step 2 if field names differ.

**Step 2: Create Sympozium Helm values**

Create `apps/sympozium/values.yaml`:

```yaml
# Sympozium — Kubernetes-native agentic control plane
# Deploys controller, API server, webhook, NATS JetStream, OTel collector
# Web UI exposed at 192.168.55.207:8080 via Cilium L2 LoadBalancer

# API server with embedded web dashboard
apiserver:
  webUI:
    enabled: true
    token: ""  # Auto-generates Secret on first deploy

  service:
    type: LoadBalancer
    annotations:
      lbipam.cilium.io/ips: "192.168.55.207"

# NATS JetStream — durable event bus for inter-component messaging
nats:
  persistence:
    enabled: true
    storageClass: longhorn
    size: 1Gi

# cert-manager integration for webhook TLS
certManager:
  enabled: true

# Install Sympozium CRDs
installCRDs: true

# Network policies for pod isolation
networkPolicies:
  enabled: true

# Built-in OTel collector for observability
observability:
  enabled: true

# We deploy our own PersonaPack manifests in sympozium-extras
# with LiteLLM-specific auth config, so skip chart defaults
defaultPersonas:
  enabled: false
```

> **Note:** Field names above are based on research of the chart's values.yaml. After running `helm show values` in Step 1, verify and adjust field names if they differ. The key settings are: LoadBalancer service, NATS persistence on Longhorn, cert-manager enabled, CRDs installed, observability on, default personas off.

**Step 3: Create Sympozium Application CR**

Create `apps/root/templates/sympozium.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: sympozium
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: ghcr.io/alexsjones/sympozium/charts
      chart: sympozium
      targetRevision: "0.1.0"
      helm:
        releaseName: sympozium
        valueFiles:
          - $values/apps/sympozium/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: sympozium-system
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
      jsonPointers:
        - /data
```

> **Note:** The `repoURL` for OCI Helm charts in ArgoCD uses the registry path without `oci://` prefix. If ArgoCD fails to pull, try the full `oci://ghcr.io/alexsjones/sympozium/charts/sympozium` format in `repoURL` with no separate `chart` field. See [ArgoCD OCI docs](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/#helm-oci-repository).

**Step 4: Commit**

```bash
git add apps/sympozium/values.yaml apps/root/templates/sympozium.yaml
git commit -m "feat(phase11): add Sympozium control plane ArgoCD application

OCI Helm chart from ghcr.io/alexsjones/sympozium. NATS persistent
on Longhorn, web UI on 192.168.55.207, OTel enabled."
```

---

### Task 3: sympozium-extras Application CR + ExternalSecret

Create the ArgoCD app for raw manifests and the ExternalSecret for LiteLLM API key.

**Files:**
- Create: `apps/root/templates/sympozium-extras.yaml`
- Create: `apps/sympozium-extras/manifests/external-secret.yaml`

**Step 1: Create sympozium-extras Application CR**

Create `apps/root/templates/sympozium-extras.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: sympozium-extras
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/sympozium-extras/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: sympozium-system
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

**Step 2: Create ExternalSecret for LiteLLM API key**

Create `apps/sympozium-extras/manifests/external-secret.yaml`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: sympozium-llm-key
  namespace: sympozium-system
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: sympozium-llm-key
    creationPolicy: Owner
  data:
    - secretKey: OPENAI_API_KEY
      remoteRef:
        key: SYMPOZIUM_LITELLM_KEY
```

> **Note:** The target secret key is `OPENAI_API_KEY` because Sympozium's OpenAI-compatible provider reads this env var. The Infisical remote key is `SYMPOZIUM_LITELLM_KEY` — created in the manual operation (Task 7).

**Step 3: Commit**

```bash
git add apps/root/templates/sympozium-extras.yaml apps/sympozium-extras/manifests/external-secret.yaml
git commit -m "feat(phase11): add sympozium-extras app and ExternalSecret

Raw manifests app for Sympozium CRs. ExternalSecret syncs
LiteLLM API key from Infisical to sympozium-system namespace."
```

---

### Task 4: SympoziumPolicy Manifests

Create policy presets that control agent tool access.

**Files:**
- Create: `apps/sympozium-extras/manifests/policy-default.yaml`
- Create: `apps/sympozium-extras/manifests/policy-restrictive.yaml`

**Step 1: Create default policy (for platform-team ops agents)**

Create `apps/sympozium-extras/manifests/policy-default.yaml`:

```yaml
apiVersion: sympozium.ai/v1alpha1
kind: SympoziumPolicy
metadata:
  name: default-policy
  namespace: sympozium-system
spec:
  toolGating:
    defaultAction: allow
    rules:
      - tool: execute_command
        action: ask
      - tool: write_file
        action: allow
      - tool: fetch_url
        action: allow
  subagentPolicy:
    maxDepth: 3
    maxConcurrent: 5
  sandboxPolicy:
    required: false
    maxCPU: "4"
    maxMemory: 8Gi
  featureGates:
    browser-automation: false
    code-execution: true
    file-access: true
    sub-agents: true
```

**Step 2: Create restrictive policy (for devops-essentials dev agents)**

Create `apps/sympozium-extras/manifests/policy-restrictive.yaml`:

```yaml
apiVersion: sympozium.ai/v1alpha1
kind: SympoziumPolicy
metadata:
  name: restrictive-policy
  namespace: sympozium-system
spec:
  toolGating:
    defaultAction: deny
    rules:
      - tool: execute_command
        action: ask
      - tool: read_file
        action: allow
      - tool: list_directory
        action: allow
      - tool: write_file
        action: deny
      - tool: fetch_url
        action: deny
      - tool: send_channel_message
        action: allow
  subagentPolicy:
    maxDepth: 2
    maxConcurrent: 3
  sandboxPolicy:
    required: true
    maxCPU: "2"
    maxMemory: 4Gi
  featureGates:
    browser-automation: false
    code-execution: true
    file-access: false
    sub-agents: true
```

**Step 3: Commit**

```bash
git add apps/sympozium-extras/manifests/policy-default.yaml apps/sympozium-extras/manifests/policy-restrictive.yaml
git commit -m "feat(phase11): add Sympozium policy presets

Default policy: most tools allowed, execute_command needs approval.
Restrictive policy: deny-by-default for dev workflow agents."
```

---

### Task 5: PersonaPack Manifests

Create PersonaPack CRs for platform-team (SRE ops) and devops-essentials (dev workflows). These are the core agent configurations that tell Sympozium what agents to run.

**Files:**
- Create: `apps/sympozium-extras/manifests/personapack-platform-team.yaml`
- Create: `apps/sympozium-extras/manifests/personapack-devops-essentials.yaml`

**Step 1: Discover CRD baseURL field**

After cert-manager and sympozium have deployed (or locally via `helm template`), verify how to set the LiteLLM base URL on PersonaPack/SympoziumInstance:

```bash
# If CRDs are installed on cluster:
kubectl explain sympoziuminstance.spec.agents --recursive 2>/dev/null | head -40
kubectl explain personapack.spec --recursive 2>/dev/null | head -60

# Or inspect CRD YAML:
kubectl get crd sympoziuminstances.sympozium.ai -o yaml | grep -A5 baseURL
```

If a `baseURL` field exists on the agent/model spec, use it. If not, the LiteLLM gateway URL may need to be set via an environment variable (`OPENAI_BASE_URL`) in the auth secret. In that case, update the ExternalSecret in Task 3 to include a `OPENAI_BASE_URL` key.

**Step 2: Create platform-team PersonaPack**

Create `apps/sympozium-extras/manifests/personapack-platform-team.yaml`:

```yaml
apiVersion: sympozium.ai/v1alpha1
kind: PersonaPack
metadata:
  name: platform-team
  namespace: sympozium-system
spec:
  enabled: true
  description: "SRE/ops agents for cluster diagnostics, scaling, and incident triage"
  category: operations
  version: "1.0.0"

  authRefs:
    - provider: openai
      secret: sympozium-llm-key

  policyRef: default-policy

  personas:
    - name: sre-agent
      displayName: "SRE Agent"
      model: qwen3.5
      systemPrompt: |
        You are an SRE agent for the Frank Kubernetes cluster (Talos Linux).
        Your job is to monitor cluster health, diagnose failures, and recommend
        remediation steps. The cluster runs on 3 Intel Mini control-plane nodes,
        1 GPU worker (RTX 5070), 1 general worker, and 2 Raspberry Pi edge nodes.

        Key services: ArgoCD, Cilium CNI, Longhorn storage, VictoriaMetrics,
        Ollama (AI inference), LiteLLM (LLM gateway), Infisical (secrets).

        Always explain your reasoning. When suggesting commands, explain what
        they do and what the expected output should look like.
      skills:
        - k8s-ops
        - sre-observability
      schedule:
        type: heartbeat
        cron: "0 * * * *"
        task: |
          Perform a health check of the Frank cluster:
          1. Check node status and resource usage
          2. Check for any pods in CrashLoopBackOff or Error state
          3. Check Longhorn storage health
          4. Report any anomalies found
      memory:
        enabled: true
        seeds:
          - "Frank cluster: 7 nodes (3 mini control-plane, 1 gpu-1 worker, 1 pc-1 worker, 2 raspi workers)"
          - "Longhorn storage: 3 replicas on control-plane nodes"
          - "GPU-1 has NoSchedule taint for GPU workloads only"

    - name: incident-responder
      displayName: "Incident Responder"
      model: qwen3.5
      systemPrompt: |
        You are an incident response agent for the Frank Kubernetes cluster.
        You triage alerts, investigate failures, and coordinate remediation.
        Always gather evidence before suggesting changes. Prefer non-destructive
        diagnostic commands first.
      skills:
        - k8s-ops
        - incident-response
      memory:
        enabled: true
        seeds:
          - "Escalation: gather logs and diagnostics before suggesting fixes"
```

**Step 3: Create devops-essentials PersonaPack**

Create `apps/sympozium-extras/manifests/personapack-devops-essentials.yaml`:

```yaml
apiVersion: sympozium.ai/v1alpha1
kind: PersonaPack
metadata:
  name: devops-essentials
  namespace: sympozium-system
spec:
  enabled: true
  description: "Development workflow agents for code review and GitOps"
  category: development
  version: "1.0.0"

  authRefs:
    - provider: openai
      secret: sympozium-llm-key

  policyRef: restrictive-policy

  personas:
    - name: code-reviewer
      displayName: "Code Reviewer"
      model: qwen3.5
      systemPrompt: |
        You are a code review agent. You review pull requests and provide
        constructive feedback on code quality, security, and best practices.
        Focus on correctness, security vulnerabilities, and maintainability.
      skills:
        - code-review
      toolPolicy:
        allow:
          - read_file
          - list_directory
          - fetch_url
        deny:
          - write_file
          - execute_command
      memory:
        enabled: true
        seeds:
          - "Follow existing project conventions found in each repo"
```

**Step 4: Commit**

```bash
git add apps/sympozium-extras/manifests/personapack-platform-team.yaml apps/sympozium-extras/manifests/personapack-devops-essentials.yaml
git commit -m "feat(phase11): add platform-team and devops-essentials PersonaPacks

Platform-team: SRE + incident response agents with hourly heartbeat.
Devops-essentials: code reviewer with restrictive read-only policy.
Both use LiteLLM via qwen3.5 model."
```

---

### Task 6: Verify Helm Chart Values Against Actual Chart

Before pushing, validate the Helm values against the real chart schema.

**Step 1: Pull and inspect the chart**

```bash
helm show values oci://ghcr.io/alexsjones/sympozium/charts/sympozium --version 0.1.0 > /tmp/sympozium-defaults.yaml
```

**Step 2: Compare key fields**

Check each value path we set in `apps/sympozium/values.yaml`:

```bash
# Verify field paths exist in chart defaults:
grep -n "apiserver" /tmp/sympozium-defaults.yaml | head -5
grep -n "webUI" /tmp/sympozium-defaults.yaml
grep -n "nats" /tmp/sympozium-defaults.yaml | head -5
grep -n "persistence" /tmp/sympozium-defaults.yaml
grep -n "certManager" /tmp/sympozium-defaults.yaml
grep -n "installCRDs" /tmp/sympozium-defaults.yaml
grep -n "observability" /tmp/sympozium-defaults.yaml
grep -n "defaultPersonas" /tmp/sympozium-defaults.yaml
grep -n "networkPolicies" /tmp/sympozium-defaults.yaml
```

**Step 3: Fix mismatches**

If any field names differ from what we used, update `apps/sympozium/values.yaml` to match the actual chart schema. Common discrepancies to watch for:
- `apiserver.service.type` vs `apiserver.serviceType`
- `nats.persistence` vs `nats.jetstream.persistence`
- `certManager` vs `cert-manager` vs `certmanager`

**Step 4: Verify OCI chart URL for ArgoCD**

ArgoCD's OCI support may need the URL in a specific format. Check:
- Format A: `repoURL: ghcr.io/alexsjones/sympozium/charts` + `chart: sympozium`
- Format B: `repoURL: oci://ghcr.io/alexsjones/sympozium/charts/sympozium` (no separate chart field)

Consult ArgoCD docs or test with `argocd app create --dry-run` if available.

**Step 5: Commit any fixes**

```bash
git add -u
git commit -m "fix(phase11): align Sympozium values with actual chart schema"
```

---

### Task 7: Manual Operation — Create Infisical Secret

This task cannot be automated. Create the LiteLLM API key in Infisical so the ExternalSecret can sync it.

```yaml
# manual-operation
id: agents-create-sympozium-llm-key
layer: agents
app: sympozium-extras
plan: docs/superpowers/plans/2026-03-09--agents--sympozium.md
when: "Before pushing — ExternalSecret needs the Infisical source"
why_manual: "Infisical secret creation requires UI/API interaction outside ArgoCD"
commands:
  - "Generate a LiteLLM virtual key: curl -X POST http://192.168.55.206:4000/key/generate -H 'Authorization: Bearer <MASTER_KEY>' -H 'Content-Type: application/json' -d '{\"key_alias\": \"sympozium\"}'"
  - "Copy the generated key from the response"
  - "In Infisical UI (192.168.55.204:8080), project frank-cluster-iwpg, environment prod: create secret SYMPOZIUM_LITELLM_KEY with the generated key value"
verify:
  - "kubectl get externalsecret sympozium-llm-key -n sympozium-system — should show SecretSynced (after push and sync)"
status: pending
```

**Steps:**

1. Source environment: `source .env`
2. Generate LiteLLM key:
   ```bash
   curl -X POST http://192.168.55.206:4000/key/generate \
     -H "Authorization: Bearer $(kubectl get secret litellm-api-keys -n litellm -o jsonpath='{.data.LITELLM_MASTER_KEY}' | base64 -d)" \
     -H "Content-Type: application/json" \
     -d '{"key_alias": "sympozium"}'
   ```
3. Copy the `key` value from the JSON response
4. Open Infisical at `http://192.168.55.204:8080`
5. Navigate to project `frank-cluster-iwpg` > environment `prod`
6. Create secret: key=`SYMPOZIUM_LITELLM_KEY`, value=the generated key

---

### Task 8: Push and Verify cert-manager Deployment

Push to remote and verify cert-manager syncs correctly before Sympozium.

**Step 1: Push**

```bash
git push origin main
```

**Step 2: Wait for ArgoCD sync**

```bash
source .env
argocd app list --port-forward --port-forward-namespace argocd | grep cert-manager
```

Expected: cert-manager app appears and begins syncing.

**Step 3: Verify cert-manager is healthy**

```bash
argocd app get cert-manager --port-forward --port-forward-namespace argocd
kubectl get pods -n cert-manager
```

Expected: 3 pods running — `cert-manager`, `cert-manager-webhook`, `cert-manager-cainjector`.

```bash
kubectl get crds | grep cert-manager
```

Expected: CRDs like `certificates.cert-manager.io`, `issuers.cert-manager.io` exist.

**Step 4: If cert-manager fails**

- Check ArgoCD sync status for errors
- Check pod logs: `kubectl logs -n cert-manager -l app=cert-manager`
- Common issue: if CRDs fail to install via Helm, apply them manually:
  ```bash
  kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.1/cert-manager.crds.yaml
  ```
  Then add `crds.enabled: false` to values and re-sync.

---

### Task 9: Verify Sympozium Control Plane Deployment

After cert-manager is healthy, verify Sympozium syncs.

**Step 1: Check ArgoCD sync**

```bash
argocd app list --port-forward --port-forward-namespace argocd | grep sympozium
```

Expected: Both `sympozium` and `sympozium-extras` apps appear.

**Step 2: Verify core pods**

```bash
kubectl get pods -n sympozium-system
```

Expected pods:
- `sympozium-controller-manager-*` — Running
- `sympozium-apiserver-*` — Running
- `sympozium-webhook-*` — Running (2 replicas)
- `sympozium-nats-*` — Running (StatefulSet)
- `sympozium-otel-collector-*` — Running (if observability enabled)

**Step 3: Verify CRDs installed**

```bash
kubectl get crds | grep sympozium
```

Expected: 6 CRDs — `sympoziuminstances`, `agentruns`, `sympoziumpolicies`, `skillpacks`, `sympoziumschedules`, `personapacks`.

**Step 4: Verify NATS persistence**

```bash
kubectl get pvc -n sympozium-system
```

Expected: PVC bound to Longhorn storage class.

**Step 5: Verify ExternalSecret synced**

```bash
kubectl get externalsecret -n sympozium-system
```

Expected: `sympozium-llm-key` with status `SecretSynced`.

**Step 6: Verify PersonaPacks created**

```bash
kubectl get personapacks -n sympozium-system
kubectl get sympoziuminstances -n sympozium-system
```

Expected: `platform-team` and `devops-essentials` PersonaPacks exist. The controller should have stamped out SympoziumInstances for each persona.

**Step 7: If Sympozium fails to sync**

- **OCI URL issue:** Try alternate ArgoCD OCI format (see Task 2 note)
- **Webhook fails:** Check cert-manager issued the certificate: `kubectl get certificates -n sympozium-system`
- **NATS PVC pending:** Check Longhorn: `kubectl get volumes -n longhorn-system`

---

### Task 10: Verify Web Dashboard and Test Agent Run

Confirm the web UI is accessible and run a test agent.

**Step 1: Verify LoadBalancer IP**

```bash
kubectl get svc -n sympozium-system | grep -i loadbalancer
```

Expected: API server service with external IP `192.168.55.207`.

**Step 2: Retrieve web UI token**

```bash
kubectl get secret sympozium-ui-token -n sympozium-system -o jsonpath='{.data.token}' | base64 -d
```

Save this token for dashboard login.

**Step 3: Access web dashboard**

Open `http://192.168.55.207:8080` in browser. Log in with the token from Step 2.

Verify:
- Dashboard loads
- PersonaPacks visible (platform-team, devops-essentials)
- Agents show as active/ready

**Step 4: Run a test agent**

Create a test AgentRun to verify the full pipeline works:

```bash
kubectl apply -f - <<'EOF'
apiVersion: sympozium.ai/v1alpha1
kind: AgentRun
metadata:
  name: test-run-001
  namespace: sympozium-system
spec:
  instanceRef: sre-agent
  task: "How many nodes are in this cluster? List them with their roles."
  model:
    name: qwen3.5
    provider: openai
    baseURL: http://litellm.litellm.svc.cluster.local:4000/v1
  skills:
    - k8s-ops
  timeout: "5m"
EOF
```

> **Note:** The `instanceRef` name should match the SympoziumInstance created by the platform-team PersonaPack controller. Check with `kubectl get sympoziuminstances -n sympozium-system` and adjust the `instanceRef` value if it uses a different naming convention (e.g., `platform-team-sre-agent`).

**Step 5: Watch the agent run**

```bash
kubectl get agentrun test-run-001 -n sympozium-system -w
```

Expected: Status progresses from `Pending` → `Running` → `Completed`.

```bash
kubectl get agentrun test-run-001 -n sympozium-system -o yaml | grep -A20 status
```

Expected: Result contains cluster node information.

**Step 6: Clean up test run**

```bash
kubectl delete agentrun test-run-001 -n sympozium-system
```

**Step 7: If agent run fails**

- **LLM connection error:** Check that the LiteLLM service is reachable from sympozium-system namespace:
  ```bash
  kubectl run -it --rm curl-test -n sympozium-system --image=curlimages/curl -- curl -s http://litellm.litellm.svc.cluster.local:4000/health
  ```
- **Auth error:** Verify the secret has the right key:
  ```bash
  kubectl get secret sympozium-llm-key -n sympozium-system -o jsonpath='{.data.OPENAI_API_KEY}' | base64 -d | head -c 10
  ```
- **baseURL not supported on AgentRun:** If the CRD doesn't have a baseURL field, the LiteLLM URL may need to be set as `OPENAI_BASE_URL` environment variable. Update the ExternalSecret to include this key, or check if the SympoziumInstance spec supports a base URL field.

---

### Task 11: Update CLAUDE.md Services Table

Add Sympozium to the services table in CLAUDE.md.

**Files:**
- Modify: `CLAUDE.md:150-157` (Services table)

**Step 1: Add Sympozium Web UI entry**

Add after the LiteLLM Gateway row:

```
| Sympozium Web UI | 192.168.55.207 | Cilium L2 LoadBalancer |
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add Sympozium to CLAUDE.md services table"
```

---

### Task 12: Sync Runbook

The design doc and implementation plan contain `# manual-operation` blocks. Sync them to the central runbook.

**Step 1: Run sync-runbook skill**

```
/sync-runbook
```

**Step 2: Commit if changes**

```bash
git add docs/runbooks/manual-operations.yaml
git commit -m "docs(runbook): sync Phase 11 manual operations"
```

---

### Task 13: Final Push and Verification

**Step 1: Push all commits**

```bash
git push origin main
```

**Step 2: Full health check**

```bash
source .env
argocd app list --port-forward --port-forward-namespace argocd | grep -E "cert-manager|sympozium"
```

Expected: All three apps (`cert-manager`, `sympozium`, `sympozium-extras`) show `Synced` and `Healthy`.

```bash
kubectl get pods -n cert-manager
kubectl get pods -n sympozium-system
kubectl get personapacks -n sympozium-system
kubectl get sympoziuminstances -n sympozium-system
kubectl get sympoziumschedules -n sympozium-system
```

All resources should be in healthy/ready state.

---

## Post-Implementation

These are NOT part of this plan but are next steps to consider:

1. **Blog post** — Use `/blog-post` skill to write Sympozium blog post
2. **Update README** — Run `/update-readme` to sync service table
3. **Telegram channel** — Execute the deferred manual operation (agents-telegram-bot-setup)
4. **OTel → VictoriaMetrics** — Wire the Sympozium OTel collector to export metrics to VictoriaMetrics
5. **Custom SkillPacks** — Write Frank-specific skills (e.g., Longhorn storage management, ArgoCD app health)
