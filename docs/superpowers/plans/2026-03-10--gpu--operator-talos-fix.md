# GPU Operator Talos Validation Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unblock GPU Operator DaemonSet pods on Talos Linux by deploying a validation marker DaemonSet that creates the files the disabled toolkit DaemonSet would normally produce.

**Architecture:** A busybox DaemonSet in `gpu-operator` namespace creates `/run/nvidia/validations/toolkit-ready` and `driver-ready` on the host. This unblocks the hardcoded init containers in device-plugin, feature-discovery, DCGM exporter, and validator pods. Deployed as a new `gpu-operator-extras` ArgoCD app following the established `-extras` pattern.

**Tech Stack:** Kubernetes DaemonSet, ArgoCD Application CR, kubectl, busybox

---

### Task 1: Create the validation markers DaemonSet manifest

**Files:**
- Create: `apps/gpu-operator-extras/manifests/validation-markers.yaml`

**Step 1: Create the manifest directory**

```bash
mkdir -p apps/gpu-operator-extras/manifests
```

**Step 2: Write the DaemonSet manifest**

Create `apps/gpu-operator-extras/manifests/validation-markers.yaml`:

```yaml
# Fake validation markers for Talos Linux.
# The GPU Operator's toolkit DaemonSet is disabled (Talos provides it via
# system extensions), but other DaemonSets have hardcoded init containers
# that poll for /run/nvidia/validations/toolkit-ready.  This DaemonSet
# creates the expected files so the init containers unblock.
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nvidia-validation-markers
  namespace: gpu-operator
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: nvidia-validation-markers
  template:
    metadata:
      labels:
        app.kubernetes.io/name: nvidia-validation-markers
    spec:
      nodeSelector:
        nvidia.com/gpu.present: "true"
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
      containers:
        - name: marker
          image: busybox:1.37
          securityContext:
            privileged: true
          command: ["/bin/sh", "-c"]
          args:
            - |
              mkdir -p /host-run/nvidia/validations
              touch /host-run/nvidia/validations/driver-ready
              touch /host-run/nvidia/validations/toolkit-ready
              echo "Validation markers created"
              sleep infinity
          resources:
            requests:
              cpu: 1m
              memory: 4Mi
            limits:
              memory: 16Mi
          volumeMounts:
            - name: host-run
              mountPath: /host-run
      volumes:
        - name: host-run
          hostPath:
            path: /run
            type: Directory
```

**Step 3: Commit**

```bash
git add apps/gpu-operator-extras/manifests/validation-markers.yaml
git commit -m "feat(gpu-operator): add Talos validation marker DaemonSet"
```

---

### Task 2: Create the gpu-operator-extras ArgoCD Application

**Files:**
- Create: `apps/root/templates/gpu-operator-extras.yaml`

**Step 1: Write the Application CR**

Create `apps/root/templates/gpu-operator-extras.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: gpu-operator-extras
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/gpu-operator-extras/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: gpu-operator
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
      - ServerSideApply=true
```

Note: `CreateNamespace=false` because `gpu-operator` namespace already exists (managed by the `ns-gpu-operator` template).

**Step 2: Commit**

```bash
git add apps/root/templates/gpu-operator-extras.yaml
git commit -m "feat(gpu-operator): add gpu-operator-extras ArgoCD app"
```

---

### Task 3: Push and verify GPU Operator pods unblock

**Step 1: Push to remote**

```bash
git push
```

**Step 2: Sync the root app**

```bash
source .env
argocd app sync root --port-forward --port-forward-namespace argocd
```

**Step 3: Sync gpu-operator-extras**

```bash
argocd app sync gpu-operator-extras --port-forward --port-forward-namespace argocd
```

**Step 4: Verify the validation markers pod is running**

```bash
kubectl get pods -n gpu-operator -l app.kubernetes.io/name=nvidia-validation-markers
```

Expected: One pod on gpu-1 in `Running` state.

**Step 5: Verify the marker files exist on the host**

```bash
source .env
talosctl -n 192.168.55.31 ls /run/nvidia/validations/
```

Expected:
```
driver-ready
toolkit-ready
```

**Step 6: Wait for GPU Operator pods to unblock**

The init containers poll every 5 seconds. Within ~10 seconds of the marker files appearing, the init containers should complete. If the pods have been in `Init:0/1` for a while, they may need a restart:

```bash
kubectl delete pods -n gpu-operator --field-selector spec.nodeName=gpu-1
```

Then wait ~60 seconds for new pods to start and pass init:

```bash
kubectl get pods -n gpu-operator --field-selector spec.nodeName=gpu-1
```

Expected: All pods reach `Running` (device-plugin, feature-discovery, dcgm-exporter, validator, validation-markers, node-feature-discovery-worker).

**Step 7: Verify GPU is registered as allocatable**

```bash
kubectl describe node gpu-1 | grep -A5 "Allocatable:"
```

Expected: `nvidia.com/gpu: 1` appears in the allocatable resources.

**Step 8: Commit nothing — this is a verification task**

---

### Task 4: Verify Ollama schedules and serves models

**Step 1: Check Ollama pod status**

```bash
kubectl get pods -n ollama -o wide
```

Expected: Ollama pod transitions from `Pending` to `ContainerCreating` to `Running` on gpu-1.

If still `Pending`, check events:

```bash
kubectl describe pod -n ollama -l app.kubernetes.io/name=ollama | tail -20
```

**Step 2: Wait for model pull (may take several minutes)**

Ollama pulls `qwen3.5:9b` and `deepseek-coder:6.7b` on first start. Monitor:

```bash
kubectl logs -n ollama -l app.kubernetes.io/name=ollama -f
```

Wait until model download completes and the server shows `Listening on :11434`.

**Step 3: Test inference via LiteLLM**

```bash
curl -s http://192.168.55.206:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <LITELLM_KEY>" \
  -d '{"model": "qwen3.5", "messages": [{"role": "user", "content": "Say hello in one sentence."}]}' | python3 -m json.tool | head -20
```

Expected: A valid JSON response with a completion from qwen3.5 via the local Ollama backend.

**Step 4: Commit nothing — this is a verification task**

---

### Task 5: Update CLAUDE.md and documentation

**Files:**
- Modify: `CLAUDE.md` — update Layer 4 status in gotchas if needed
- Modify: `README.md` — update gpu-operator notes if needed

**Step 1: Update the gpu-operator app notes in README.md**

In the Current Status table, update the `gpu-operator` row:

```
| gpu-operator | gpu-operator | RTX 5070 on gpu-1 (Talos extensions + validation markers) |
```

Add the new app:

```
| gpu-operator-extras | gpu-operator | Talos validation markers DaemonSet |
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs(gpu-operator): update status after Talos validation fix"
```

---

### Task 6: Final push and verification

**Step 1: Push all remaining commits**

```bash
git push
```

**Step 2: Verify all three GPU-related ArgoCD apps are healthy**

```bash
argocd app list --port-forward --port-forward-namespace argocd | grep gpu
```

Expected:
```
gpu-operator          Synced  Healthy
gpu-operator-extras   Synced  Healthy
```

**Step 3: Run a Sympozium test agent to verify end-to-end**

Now that Ollama is serving models via LiteLLM, test a Sympozium AgentRun:

```bash
source .env
cat <<'EOF' | kubectl apply -f -
apiVersion: sympozium.ai/v1alpha1
kind: AgentRun
metadata:
  name: test-gpu-fix
  namespace: sympozium-system
spec:
  instanceRef: platform-team-sre-agent
  agentId: primary
  sessionKey: "test-gpu-fix"
  task: "How many nodes are in this cluster? List them with their roles."
  model:
    model: qwen3.5
    provider: openai
    baseURL: http://litellm.litellm.svc.cluster.local:4000/v1
    authSecretRef: sympozium-llm-key
  skills:
    - skillPackRef: k8s-ops
  timeout: "5m"
EOF
```

Watch:
```bash
kubectl get agentrun test-gpu-fix -n sympozium-system -w
```

Expected: Phase transitions from `Pending` → `Running` → `Succeeded`.

**Step 4: Clean up test run**

```bash
kubectl delete agentrun test-gpu-fix -n sympozium-system
```

**Step 5: Final push**

```bash
git push
```
