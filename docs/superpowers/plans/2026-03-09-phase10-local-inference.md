# Local Inference Gateway — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy a unified LLM inference gateway (Ollama + LiteLLM) behind a single OpenAI-compatible API at `192.168.55.206:4000`, routing between local models on gpu-1's RTX 5070 and free cloud models via OpenRouter.

**Architecture:** Ollama runs on gpu-1 serving local models (Qwen 3.5 9B, DeepSeek Coder 6.7B) via ClusterIP. LiteLLM runs on any non-tainted node as the unified gateway, routing requests to Ollama or OpenRouter based on model name. Secrets (OpenRouter API key, LiteLLM master key) managed via Infisical → ExternalSecret → K8s Secret.

**Tech Stack:** Ollama (otwld/ollama-helm `1.50.0`), LiteLLM (OCI `docker.litellm.ai/berriai/litellm-helm` `1.81.13`), Infisical + ExternalSecret, ArgoCD App-of-Apps, Longhorn PVC

**Prereqs:** `source .env` (KUBECONFIG) and `source .env_devops` (OMNI) available. Phase 4 (GPU Operator) complete — gpu-1 has `nvidia.com/gpu` resource and NoSchedule taint. Infisical running at `192.168.55.204`.

**Design doc:** `docs/superpowers/plans/2026-03-09-phase10-local-inference-design.md`

---

## Task 1: Create Ollama ArgoCD app

**Files:**
- Create: `apps/ollama/values.yaml`
- Create: `apps/root/templates/ollama.yaml`

**Step 1: Create values file**

`apps/ollama/values.yaml`:
```yaml
# Ollama — local LLM inference on gpu-1's RTX 5070
# Serves models via OpenAI-compatible API on ClusterIP:11434
# Consumed by LiteLLM gateway, not exposed externally

ollama:
  gpu:
    enabled: true
    type: nvidia
    number: 1
    nvidiaResource: "nvidia.com/gpu"

  models:
    pull:
      - qwen3.5:9b
      - deepseek-coder:6.7b
    run: []
    clean: false

extraEnv:
  - name: OLLAMA_KEEP_ALIVE
    value: "24h"
  - name: OLLAMA_MAX_LOADED_MODELS
    value: "1"

persistentVolume:
  enabled: true
  size: 30Gi
  storageClass: longhorn
  accessModes:
    - ReadWriteOnce

tolerations:
  - key: nvidia.com/gpu
    operator: Exists
    effect: NoSchedule

nodeSelector:
  kubernetes.io/hostname: gpu-1

resources:
  requests:
    memory: 16Gi
    cpu: 4000m
  limits:
    memory: 32Gi

livenessProbe:
  enabled: true
  initialDelaySeconds: 120
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 6

readinessProbe:
  enabled: true
  initialDelaySeconds: 60
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 6

terminationGracePeriodSeconds: 120
```

**Step 2: Create Application CR**

`apps/root/templates/ollama.yaml`:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ollama
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://helm.otwld.com/
      chart: ollama
      targetRevision: "1.50.0"
      helm:
        releaseName: ollama
        valueFiles:
          - $values/apps/ollama/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: ollama
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
git add apps/ollama/values.yaml apps/root/templates/ollama.yaml
git commit -m "feat(ollama): add ArgoCD app for local LLM inference on gpu-1"
```

---

## Task 2: Create LiteLLM ExternalSecret manifests

**Files:**
- Create: `apps/litellm/manifests/external-secret.yaml`

**Step 1: Create ExternalSecret CR**

This pulls `OPENROUTER_API_KEY` and `LITELLM_MASTER_KEY` from Infisical into a K8s Secret in the `litellm` namespace. The ClusterSecretStore `infisical` already exists.

`apps/litellm/manifests/external-secret.yaml`:
```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: litellm-api-keys
  namespace: litellm
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: litellm-api-keys
    creationPolicy: Owner
  data:
    - secretKey: OPENROUTER_API_KEY
      remoteRef:
        key: OPENROUTER_API_KEY
    - secretKey: LITELLM_MASTER_KEY
      remoteRef:
        key: LITELLM_MASTER_KEY
```

**Step 2: Commit**

```bash
git add apps/litellm/manifests/external-secret.yaml
git commit -m "feat(litellm): add ExternalSecret for OpenRouter and master key"
```

---

## Task 3: Create LiteLLM ArgoCD apps

**Files:**
- Create: `apps/litellm/values.yaml`
- Create: `apps/root/templates/litellm.yaml`
- Create: `apps/root/templates/litellm-extras.yaml`

Two ArgoCD apps following the longhorn/longhorn-extras pattern: one for the Helm chart, one for raw manifests (ExternalSecret).

**Step 1: Create values file**

`apps/litellm/values.yaml`:
```yaml
# LiteLLM — unified LLM inference gateway
# Routes between local Ollama models and cloud providers via OpenRouter
# Exposed at 192.168.55.206:4000 as OpenAI-compatible API

image:
  repository: ghcr.io/berriai/litellm-database
  pullPolicy: Always

# Master key from ExternalSecret-managed K8s Secret
masterkeySecretName: "litellm-api-keys"
masterkeySecretKey: "LITELLM_MASTER_KEY"

# Inject API keys from K8s Secret as env vars
# ExternalSecret "litellm-api-keys" syncs from Infisical
environmentSecrets:
  - litellm-api-keys

# LiteLLM proxy configuration (rendered as config.yaml)
proxy_config:
  model_list:
    # ──────────────────────────────────────────────
    # LOCAL MODELS (Ollama on gpu-1)
    # ──────────────────────────────────────────────

    # Qwen 3.5 9B — default general-purpose model
    # Multimodal (text+image), 256K context, tool calling, thinking mode
    # Runs fully in VRAM on RTX 5070 (6.6GB Q4)
    - model_name: qwen3.5
      litellm_params:
        model: ollama/qwen3.5:9b
        api_base: http://ollama.ollama.svc.cluster.local:11434

    # DeepSeek Coder 6.7B — code generation and completion
    # Swapped in on-demand (~5s cold load)
    - model_name: deepseek-coder
      litellm_params:
        model: ollama/deepseek-coder:6.7b
        api_base: http://ollama.ollama.svc.cluster.local:11434

    # ──────────────────────────────────────────────
    # CLOUD MODELS — Free tier via OpenRouter
    # Rate limit: 20 req/min, 200 req/day per model
    # ──────────────────────────────────────────────

    # DeepSeek R1 — 671B MoE (37B active), reasoning model
    # Visible chain-of-thought, on par with OpenAI o1
    # ⚠ Data: Chinese servers, prompts may train models, no opt-out
    - model_name: deepseek-r1
      litellm_params:
        model: openrouter/deepseek/deepseek-r1:free
        api_key: os.environ/OPENROUTER_API_KEY

    # Gemini 2.0 Flash Exp — 1M context, long document processing
    # ⚠ Data: Google experimental; prompts may train future models
    - model_name: gemini-flash
      litellm_params:
        model: openrouter/google/gemini-2.0-flash-exp:free
        api_key: os.environ/OPENROUTER_API_KEY

    # Devstral 2 — Mistral's 123B dense coding model, 256K context
    # Agentic coding, multi-file project understanding
    # ⚠ Data: Mistral Experiment plan; prompts may train models
    - model_name: devstral
      litellm_params:
        model: openrouter/mistralai/devstral-2512:free
        api_key: os.environ/OPENROUTER_API_KEY

    # Llama 3.3 70B — Meta's general-purpose open model, 128K context
    # Strong all-rounder, Apache-like license
    # ✅ Data: Open-weight, served by third-party; check provider policy
    - model_name: llama-70b
      litellm_params:
        model: openrouter/meta-llama/llama-3.3-70b-instruct:free
        api_key: os.environ/OPENROUTER_API_KEY

    # GPT-OSS 120B — OpenAI's open-weight MoE (5.1B active), 131K context
    # Designed for agentic and general-purpose production use
    # ✅ Data: Open-weight (Apache 2.0), served by third-party
    - model_name: gpt-oss
      litellm_params:
        model: openrouter/openai/gpt-oss-120b:free
        api_key: os.environ/OPENROUTER_API_KEY

    # Step 3.5 Flash — StepFun's 196B MoE (11B active), 256K context
    # Reasoning model, strong general-purpose
    # ⚠ Data: Training disabled, but prompts retained by StepFun
    - model_name: step-flash
      litellm_params:
        model: openrouter/stepfun/step-3.5-flash:free
        api_key: os.environ/OPENROUTER_API_KEY

  litellm_settings:
    default_model: qwen3.5

  general_settings:
    master_key: os.environ/LITELLM_MASTER_KEY

service:
  type: LoadBalancer
  port: 4000

# Standalone PostgreSQL for virtual keys, spend tracking, usage logs
db:
  deployStandalone: true

postgresql:
  auth:
    username: litellm
    database: litellm
  primary:
    persistence:
      enabled: true
      size: 5Gi
      storageClass: longhorn
```

**Step 2: Create LiteLLM Application CR (Helm chart)**

`apps/root/templates/litellm.yaml`:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: litellm
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: docker.litellm.ai/berriai
      chart: litellm-helm
      targetRevision: "1.81.13"
      helm:
        releaseName: litellm
        valueFiles:
          - $values/apps/litellm/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: litellm
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

**Step 3: Create LiteLLM extras Application CR (ExternalSecret manifests)**

`apps/root/templates/litellm-extras.yaml`:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: litellm-extras
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/litellm/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: litellm
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

**Step 4: Commit**

```bash
git add apps/litellm/values.yaml \
        apps/root/templates/litellm.yaml \
        apps/root/templates/litellm-extras.yaml
git commit -m "feat(litellm): add ArgoCD app for LLM inference gateway"
```

---

## Task 4: Add secrets to Infisical

```yaml
# manual-operation
id: inference-infisical-secrets
phase: inference
app: litellm
plan: docs/superpowers/plans/2026-03-09-phase10-local-inference.md
when: "Before Task 5 — secrets must exist in Infisical before ExternalSecret can sync"
why_manual: "API keys are user credentials — must be entered via Infisical UI"
commands:
  - "Open Infisical UI at http://192.168.55.204"
  - "Navigate to frank-cluster project → prod environment"
  - "Add secret: Key=OPENROUTER_API_KEY, Value=<your OpenRouter API key from https://openrouter.ai/settings/keys>"
  - "Add secret: Key=LITELLM_MASTER_KEY, Value=<generate with: openssl rand -hex 32>"
verify:
  - "Secrets visible in Infisical UI under frank-cluster/prod"
status: pending
```

---

## Task 5: Push and deploy Ollama

**Files:** None (cluster operations only)

**Step 1: Push all commits**

```bash
git push
```

**Step 2: Sync ArgoCD root app to discover new apps**

```bash
source .env
argocd app sync root --port-forward --port-forward-namespace argocd
```

**Step 3: Sync Ollama app**

```bash
argocd app sync ollama --port-forward --port-forward-namespace argocd
```

**Step 4: Wait for Ollama pod to be ready**

The pod will take a while on first deploy — it needs to pull the container image AND download both models (~11GB total).

```bash
kubectl get pods -n ollama -w
# Wait for STATUS = Running, READY = 1/1
# This may take 5-10 minutes on first deploy due to model downloads
```

**Step 5: Verify Ollama is serving**

```bash
# Check models are downloaded
kubectl exec -n ollama deploy/ollama -- ollama list
# Expected: qwen3.5:9b and deepseek-coder:6.7b listed

# Test inference
kubectl exec -n ollama deploy/ollama -- ollama run qwen3.5:9b "Say hello in one word"
# Expected: a one-word greeting

# Check ClusterIP service
kubectl get svc -n ollama
# Expected: ollama service on port 11434, type ClusterIP
```

**Step 6: Verify GPU allocation**

```bash
kubectl describe pod -n ollama -l app.kubernetes.io/name=ollama | grep -A5 "Limits\|Requests\|nvidia"
# Expected: nvidia.com/gpu: 1 in both requests and limits

kubectl describe node gpu-1 | grep -A5 "Allocated resources"
# Expected: nvidia.com/gpu shows 1 allocated
```

---

## Task 6: Deploy and verify LiteLLM

**Files:** None (cluster operations only)

**Step 1: Sync litellm-extras first (ExternalSecret)**

```bash
source .env
argocd app sync litellm-extras --port-forward --port-forward-namespace argocd
```

**Step 2: Verify ExternalSecret synced**

```bash
kubectl get externalsecret -n litellm
# Expected: litellm-api-keys with status SecretSynced

kubectl get secret litellm-api-keys -n litellm
# Expected: Secret exists with OPENROUTER_API_KEY and LITELLM_MASTER_KEY keys
```

**Step 3: Sync litellm app**

```bash
argocd app sync litellm --port-forward --port-forward-namespace argocd
```

**Step 4: Wait for LiteLLM to be ready**

```bash
kubectl get pods -n litellm -w
# Wait for the litellm pod to be Running and Ready
# The PostgreSQL pod should come up first, then the migration job, then litellm
```

**Step 5: Verify LoadBalancer IP**

```bash
kubectl get svc -n litellm
# Expected: litellm service with EXTERNAL-IP 192.168.55.206, port 4000
```

If the LoadBalancer IP is not `192.168.55.206`, patch the service:

```bash
kubectl patch svc litellm -n litellm -p '{"spec":{"loadBalancerIP":"192.168.55.206"}}'
```

> **Note:** If the chart does not support `loadBalancerIP` natively, add a Service manifest override to `apps/litellm/manifests/` or use `service.annotations` in values.yaml with the appropriate Cilium annotation. Check `kubectl get svc -n litellm -o yaml` to see the rendered service spec.

**Step 6: Verify LiteLLM health**

```bash
curl http://192.168.55.206:4000/health
# Expected: {"status":"healthy"}
```

---

## Task 7: End-to-end smoke test

**Files:** None (verification only)

**Step 1: Test local model (Ollama via LiteLLM)**

```bash
curl -s http://192.168.55.206:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <LITELLM_MASTER_KEY>" \
  -d '{
    "model": "qwen3.5",
    "messages": [{"role": "user", "content": "Say hello in one word"}],
    "max_tokens": 10
  }' | jq '.choices[0].message.content'
# Expected: a greeting word
```

**Step 2: Test cloud model (OpenRouter via LiteLLM)**

```bash
curl -s http://192.168.55.206:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <LITELLM_MASTER_KEY>" \
  -d '{
    "model": "llama-70b",
    "messages": [{"role": "user", "content": "Say hello in one word"}],
    "max_tokens": 10
  }' | jq '.choices[0].message.content'
# Expected: a greeting word (served by OpenRouter)
```

**Step 3: Test default model routing**

```bash
curl -s http://192.168.55.206:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <LITELLM_MASTER_KEY>" \
  -d '{
    "messages": [{"role": "user", "content": "What model are you?"}],
    "max_tokens": 50
  }' | jq '.model'
# Expected: should route to qwen3.5 (default model)
```

**Step 4: Test model listing**

```bash
curl -s http://192.168.55.206:4000/v1/models \
  -H "Authorization: Bearer <LITELLM_MASTER_KEY>" | jq '.data[].id'
# Expected: qwen3.5, deepseek-coder, deepseek-r1, gemini-flash,
#           devstral, llama-70b, gpt-oss, step-flash
```

**Step 5: Verify ArgoCD shows all apps healthy**

```bash
argocd app list --port-forward --port-forward-namespace argocd | grep -E "ollama|litellm"
# Expected: ollama, litellm, litellm-extras all Synced/Healthy
```

---

## Task 8: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

Add Ollama and LiteLLM to the Services table and update Current Apps list.

**Step 1: Add to Services table**

Add these rows to the Services table in CLAUDE.md:
```
| LiteLLM Gateway | 192.168.55.206 | Cilium L2 LoadBalancer |
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add LiteLLM gateway to services table"
```
