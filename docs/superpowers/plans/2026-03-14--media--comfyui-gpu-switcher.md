# Media Generation Stack Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy ComfyUI for diffusion-based media generation (video/image/audio) on gpu-1, with a GPU Switcher web app for time-sharing the GPU between Ollama and ComfyUI.

**Architecture:** ComfyUI runs as a Kubernetes Deployment on gpu-1 with a 100Gi Longhorn PVC for model storage. A custom Go web app ("GPU Switcher") provides a dashboard to scale one GPU workload up and the other down, ensuring only one holds the GPU at a time. Both are managed via ArgoCD App-of-Apps.

**Tech Stack:** ComfyUI (ai-dock CUDA image), Go 1.22+ (client-go, net/http, embed), Longhorn storage, Cilium L2 LoadBalancer, ArgoCD

---

## File Structure

### ComfyUI ArgoCD App

| Action | Path | Purpose |
|--------|------|---------|
| Create | `apps/root/templates/ns-comfyui.yaml` | Namespace with pod-security labels |
| Create | `apps/root/templates/comfyui.yaml` | ArgoCD Application CR (raw manifests) |
| Create | `apps/comfyui/manifests/pvc.yaml` | 100Gi Longhorn PVC for models |
| Create | `apps/comfyui/manifests/deployment.yaml` | ComfyUI Deployment (GPU, node affinity) |
| Create | `apps/comfyui/manifests/service.yaml` | ClusterIP Service on port 8188 |
| Create | `apps/comfyui/manifests/service-lb.yaml` | LoadBalancer Service at 192.168.55.213 |

### GPU Switcher Go Application

| Action | Path | Purpose |
|--------|------|---------|
| Create | `apps/gpu-switcher/app/go.mod` | Go module definition |
| Create | `apps/gpu-switcher/app/main.go` | HTTP server, routes, embedded assets |
| Create | `apps/gpu-switcher/app/k8s.go` | Kubernetes client: scale, get status |
| Create | `apps/gpu-switcher/app/k8s_test.go` | Tests with fake K8s clientset |
| Create | `apps/gpu-switcher/app/static/index.html` | Dashboard UI (single-page) |
| Create | `apps/gpu-switcher/app/Dockerfile` | Multi-stage Go build → distroless |

### GPU Switcher ArgoCD App

| Action | Path | Purpose |
|--------|------|---------|
| Create | `apps/root/templates/ns-gpu-switcher.yaml` | Namespace with pod-security labels |
| Create | `apps/root/templates/gpu-switcher.yaml` | ArgoCD Application CR (raw manifests) |
| Create | `apps/gpu-switcher/manifests/serviceaccount.yaml` | ServiceAccount for K8s API access |
| Create | `apps/gpu-switcher/manifests/clusterrole.yaml` | ClusterRole: scale deployments, list pods |
| Create | `apps/gpu-switcher/manifests/clusterrolebinding.yaml` | Bind ClusterRole to ServiceAccount |
| Create | `apps/gpu-switcher/manifests/deployment.yaml` | GPU Switcher Deployment (no GPU) |
| Create | `apps/gpu-switcher/manifests/service.yaml` | LoadBalancer at 192.168.55.214 |

---

## Chunk 1: ComfyUI ArgoCD Deployment

### Task 1: Create ComfyUI namespace

**Files:**
- Create: `apps/root/templates/ns-comfyui.yaml`

- [ ] **Step 1: Create the namespace manifest**

```yaml
# apps/root/templates/ns-comfyui.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: comfyui
  labels:
    pod-security.kubernetes.io/enforce: privileged
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/audit: privileged
    pod-security.kubernetes.io/warn: privileged
```

> **Why privileged?** ComfyUI needs GPU access via the NVIDIA runtime, which requires privileged pod-security (same pattern as `ns-gpu-operator.yaml` and `ns-openrgb.yaml`).

- [ ] **Step 2: Verify template renders**

Run: `helm template apps/root/ | grep -A6 'name: comfyui'`
Expected: The namespace manifest appears in the rendered output.

- [ ] **Step 3: Commit**

```bash
git add apps/root/templates/ns-comfyui.yaml
git commit -m "feat(comfyui): add comfyui namespace"
```

---

### Task 2: Create ComfyUI PVC for model storage

**Files:**
- Create: `apps/comfyui/manifests/pvc.yaml`

- [ ] **Step 1: Create the PVC manifest**

```yaml
# apps/comfyui/manifests/pvc.yaml
# Persistent storage for ComfyUI models (checkpoints, LoRAs, VAEs)
# Sized for video (LTX-2.3 ~5GB), image (Flux/SDXL ~12GB), audio (~4GB) + headroom
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: comfyui-models
  namespace: comfyui
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn
  resources:
    requests:
      storage: 100Gi
```

- [ ] **Step 2: Validate YAML syntax**

Run: `kubectl apply --dry-run=client -f apps/comfyui/manifests/pvc.yaml`
Expected: `persistentvolumeclaim/comfyui-models created (dry run)`

- [ ] **Step 3: Commit**

```bash
git add apps/comfyui/manifests/pvc.yaml
git commit -m "feat(comfyui): add 100Gi Longhorn PVC for model storage"
```

---

### Task 3: Create ComfyUI Deployment

**Files:**
- Create: `apps/comfyui/manifests/deployment.yaml`

- [ ] **Step 1: Create the Deployment manifest**

```yaml
# apps/comfyui/manifests/deployment.yaml
# ComfyUI diffusion model server on gpu-1
# Starts at 0 replicas — activate via GPU Switcher
apiVersion: apps/v1
kind: Deployment
metadata:
  name: comfyui
  namespace: comfyui
  labels:
    app.kubernetes.io/name: comfyui
    app.kubernetes.io/component: server
spec:
  replicas: 0
  selector:
    matchLabels:
      app.kubernetes.io/name: comfyui
      app.kubernetes.io/component: server
  strategy:
    type: Recreate
  template:
    metadata:
      labels:
        app.kubernetes.io/name: comfyui
        app.kubernetes.io/component: server
    spec:
      nodeSelector:
        kubernetes.io/hostname: gpu-1
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
      terminationGracePeriodSeconds: 30
      containers:
        - name: comfyui
          image: ghcr.io/ai-dock/comfyui:latest-cuda
          ports:
            - name: http
              containerPort: 8188
              protocol: TCP
          env:
            - name: COMFYUI_FLAGS
              value: "--listen 0.0.0.0"
            - name: WEB_ENABLE_AUTH
              value: "false"
          resources:
            requests:
              cpu: 4000m
              memory: 16Gi
              nvidia.com/gpu: "1"
            limits:
              memory: 24Gi
              nvidia.com/gpu: "1"
          volumeMounts:
            - name: models
              mountPath: /opt/ComfyUI/models
          livenessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 120
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 6
          readinessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 60
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 6
      volumes:
        - name: models
          persistentVolumeClaim:
            claimName: comfyui-models
```

> **Key decisions:**
> - `replicas: 0` — Ollama is active by default; ComfyUI activates via GPU Switcher
> - `strategy: Recreate` — only one GPU pod can exist at a time
> - `--listen 0.0.0.0` — required for Kubernetes Service routing
> - Models PVC mounted at `/opt/ComfyUI/models` (ai-dock default model path)
> - Resource requests mirror Ollama's pattern (4 CPU, 16Gi RAM, 1 GPU)
> - **Image tag:** Using `latest-cuda` initially. After first successful deploy, pin to a specific digest or version tag (e.g., `v2-cuda-12.1.1-base-22.04-v0.2.7`) for reproducibility. Add the pinned tag to CLAUDE.md gotchas (similar to Sympozium/LiteLLM pattern).

- [ ] **Step 2: Validate YAML syntax**

Run: `kubectl apply --dry-run=client -f apps/comfyui/manifests/deployment.yaml`
Expected: `deployment.apps/comfyui created (dry run)`

- [ ] **Step 3: Commit**

```bash
git add apps/comfyui/manifests/deployment.yaml
git commit -m "feat(comfyui): add Deployment with GPU scheduling and model PVC"
```

---

### Task 4: Create ComfyUI Services

**Files:**
- Create: `apps/comfyui/manifests/service.yaml`
- Create: `apps/comfyui/manifests/service-lb.yaml`

- [ ] **Step 1: Create ClusterIP Service**

```yaml
# apps/comfyui/manifests/service.yaml
# ClusterIP Service for internal access (agents call the API here)
apiVersion: v1
kind: Service
metadata:
  name: comfyui
  namespace: comfyui
  labels:
    app.kubernetes.io/name: comfyui
    app.kubernetes.io/component: server
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: comfyui
    app.kubernetes.io/component: server
  ports:
    - name: http
      port: 8188
      targetPort: http
      protocol: TCP
```

- [ ] **Step 2: Create LoadBalancer Service**

```yaml
# apps/comfyui/manifests/service-lb.yaml
# LoadBalancer Service for browser access to ComfyUI Web UI
# Exposed at 192.168.55.213:8188 via Cilium L2 IPAM
apiVersion: v1
kind: Service
metadata:
  name: comfyui-lb
  namespace: comfyui
  annotations:
    lbipam.cilium.io/ips: "192.168.55.213"
  labels:
    app.kubernetes.io/name: comfyui
    app.kubernetes.io/component: server
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/name: comfyui
    app.kubernetes.io/component: server
  ports:
    - name: http
      port: 8188
      targetPort: http
      protocol: TCP
```

- [ ] **Step 3: Validate both**

Run: `kubectl apply --dry-run=client -f apps/comfyui/manifests/service.yaml && kubectl apply --dry-run=client -f apps/comfyui/manifests/service-lb.yaml`
Expected: Both created (dry run).

- [ ] **Step 4: Commit**

```bash
git add apps/comfyui/manifests/service.yaml apps/comfyui/manifests/service-lb.yaml
git commit -m "feat(comfyui): add ClusterIP and LoadBalancer services"
```

---

### Task 5: Create ComfyUI ArgoCD Application CR

**Files:**
- Create: `apps/root/templates/comfyui.yaml`

- [ ] **Step 1: Create the Application CR**

```yaml
# apps/root/templates/comfyui.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: comfyui
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/comfyui/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: comfyui
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: apps
      kind: Deployment
      name: comfyui
      jsonPointers:
        - /spec/replicas
```

> Follows the raw-manifests pattern (single `source` with `path`) like `gpu-operator-extras`. Namespace pre-created via `ns-comfyui.yaml`. `CreateNamespace=false` because we manage it explicitly.
>
> **Critical:** `ignoreDifferences` on `/spec/replicas` prevents ArgoCD self-heal from reverting GPU Switcher's scaling changes. Without this, ArgoCD would continuously fight the switcher by resetting replicas to the declared value (0).

- [ ] **Step 2: Verify template renders**

Run: `helm template apps/root/ | grep -A20 'name: comfyui' | head -25`
Expected: Application CR renders with the correct repoURL and path.

- [ ] **Step 3: Commit**

```bash
git add apps/root/templates/comfyui.yaml
git commit -m "feat(comfyui): add ArgoCD Application CR"
```

---

### Task 5b: Add ignoreDifferences to existing Ollama Application CR

**Files:**
- Modify: `apps/root/templates/ollama.yaml`

> **Why:** ArgoCD's `selfHeal: true` will fight GPU Switcher scaling. When the switcher sets Ollama replicas to 0, ArgoCD would revert it back to the declared value. We must tell ArgoCD to ignore replica drift on Ollama too.

- [ ] **Step 1: Add ignoreDifferences to ollama.yaml**

Add before the closing of the `spec:` block in `apps/root/templates/ollama.yaml`:

```yaml
  ignoreDifferences:
    - group: apps
      kind: Deployment
      name: ollama
      jsonPointers:
        - /spec/replicas
```

The full file should end with:
```yaml
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: apps
      kind: Deployment
      name: ollama
      jsonPointers:
        - /spec/replicas
```

- [ ] **Step 2: Verify template renders**

Run: `helm template apps/root/ | grep -A30 'name: ollama' | head -35`
Expected: `ignoreDifferences` section appears in the rendered Ollama Application.

- [ ] **Step 3: Commit**

```bash
git add apps/root/templates/ollama.yaml
git commit -m "feat(ollama): add ignoreDifferences for replicas (GPU Switcher support)"
```

---

## Chunk 2: GPU Switcher Go Application

### Task 6: Initialize Go module

**Files:**
- Create: `apps/gpu-switcher/app/go.mod`

- [ ] **Step 1: Create directory and initialize Go module**

Run:
```bash
mkdir -p apps/gpu-switcher/app/static
cd apps/gpu-switcher/app && go mod init github.com/derio-net/gpu-switcher
```

- [ ] **Step 2: Add kubernetes client-go dependency**

Run:
```bash
cd apps/gpu-switcher/app && go get k8s.io/client-go@latest k8s.io/apimachinery@latest k8s.io/api@latest
```

- [ ] **Step 3: Commit**

```bash
git add apps/gpu-switcher/app/go.mod apps/gpu-switcher/app/go.sum
git commit -m "feat(gpu-switcher): initialize Go module with client-go"
```

---

### Task 7: Implement Kubernetes client operations

**Files:**
- Create: `apps/gpu-switcher/app/k8s.go`

- [ ] **Step 1: Write the failing test first**

Create `apps/gpu-switcher/app/k8s_test.go`:

```go
package main

import (
	"context"
	"testing"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"
)

func newTestWorkloads() (*fake.Clientset, []Workload) {
	client := fake.NewSimpleClientset(
		&appsv1.Deployment{
			ObjectMeta: metav1.ObjectMeta{Name: "ollama", Namespace: "ollama"},
			Spec:       appsv1.DeploymentSpec{Replicas: int32Ptr(1)},
			Status:     appsv1.DeploymentStatus{ReadyReplicas: 1},
		},
		&appsv1.Deployment{
			ObjectMeta: metav1.ObjectMeta{Name: "comfyui", Namespace: "comfyui"},
			Spec:       appsv1.DeploymentSpec{Replicas: int32Ptr(0)},
			Status:     appsv1.DeploymentStatus{ReadyReplicas: 0},
		},
		&corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name: "ollama-abc123", Namespace: "ollama",
				Labels: map[string]string{"app.kubernetes.io/name": "ollama"},
			},
			Status: corev1.PodStatus{Phase: corev1.PodRunning},
		},
	)
	workloads := []Workload{
		{Name: "ollama", Namespace: "ollama", DeploymentName: "ollama"},
		{Name: "comfyui", Namespace: "comfyui", DeploymentName: "comfyui"},
	}
	return client, workloads
}

func int32Ptr(i int32) *int32 { return &i }

func TestGetStatus(t *testing.T) {
	client, workloads := newTestWorkloads()
	statuses, err := GetStatus(context.Background(), client, workloads)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(statuses) != 2 {
		t.Fatalf("expected 2 statuses, got %d", len(statuses))
	}
	// Ollama should be active (replicas=1)
	if statuses[0].Replicas != 1 {
		t.Errorf("expected ollama replicas=1, got %d", statuses[0].Replicas)
	}
	// ComfyUI should be inactive (replicas=0)
	if statuses[1].Replicas != 0 {
		t.Errorf("expected comfyui replicas=0, got %d", statuses[1].Replicas)
	}
}

func TestActivateWorkload(t *testing.T) {
	client, workloads := newTestWorkloads()
	// Activate comfyui (should scale comfyui to 1, ollama to 0)
	err := ActivateWorkload(context.Background(), client, workloads, "comfyui")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Check comfyui scaled up
	dep, _ := client.AppsV1().Deployments("comfyui").Get(context.Background(), "comfyui", metav1.GetOptions{})
	if *dep.Spec.Replicas != 1 {
		t.Errorf("expected comfyui replicas=1, got %d", *dep.Spec.Replicas)
	}
	// Check ollama scaled down
	dep, _ = client.AppsV1().Deployments("ollama").Get(context.Background(), "ollama", metav1.GetOptions{})
	if *dep.Spec.Replicas != 0 {
		t.Errorf("expected ollama replicas=0, got %d", *dep.Spec.Replicas)
	}
}

func TestActivateWorkload_InvalidName(t *testing.T) {
	client, workloads := newTestWorkloads()
	err := ActivateWorkload(context.Background(), client, workloads, "nonexistent")
	if err == nil {
		t.Fatal("expected error for invalid workload name")
	}
}

func TestDeactivateAll(t *testing.T) {
	client, workloads := newTestWorkloads()
	err := DeactivateAll(context.Background(), client, workloads)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for _, w := range workloads {
		dep, _ := client.AppsV1().Deployments(w.Namespace).Get(context.Background(), w.DeploymentName, metav1.GetOptions{})
		if *dep.Spec.Replicas != 0 {
			t.Errorf("expected %s replicas=0, got %d", w.Name, *dep.Spec.Replicas)
		}
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/gpu-switcher/app && go test -v -run TestGetStatus`
Expected: FAIL — compilation error (undefined: `Workload`, `GetStatus`, `ActivateWorkload`, `DeactivateAll`). This is expected TDD — the types and functions don't exist yet.

- [ ] **Step 3: Implement k8s.go**

Create `apps/gpu-switcher/app/k8s.go`:

```go
package main

import (
	"context"
	"fmt"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

// Workload represents a GPU workload that can be activated/deactivated.
type Workload struct {
	Name           string // Display name (e.g., "ollama", "comfyui")
	Namespace      string // Kubernetes namespace
	DeploymentName string // Deployment to scale
}

// WorkloadStatus is the current state of a workload.
type WorkloadStatus struct {
	Workload
	Replicas      int32  // Desired replicas
	ReadyReplicas int32  // Running and ready
	PodPhase      string // Phase of first matching pod, or "None"
}

// GetStatus returns the current status of all workloads.
func GetStatus(ctx context.Context, client kubernetes.Interface, workloads []Workload) ([]WorkloadStatus, error) {
	statuses := make([]WorkloadStatus, 0, len(workloads))
	for _, w := range workloads {
		dep, err := client.AppsV1().Deployments(w.Namespace).Get(ctx, w.DeploymentName, metav1.GetOptions{})
		if err != nil {
			return nil, fmt.Errorf("get deployment %s/%s: %w", w.Namespace, w.DeploymentName, err)
		}
		var replicas int32
		if dep.Spec.Replicas != nil {
			replicas = *dep.Spec.Replicas
		}
		podPhase := "None"
		pods, err := client.CoreV1().Pods(w.Namespace).List(ctx, metav1.ListOptions{
			LabelSelector: fmt.Sprintf("app.kubernetes.io/name=%s", w.Name),
			Limit:         1,
		})
		if err == nil && len(pods.Items) > 0 {
			podPhase = string(pods.Items[0].Status.Phase)
		}
		statuses = append(statuses, WorkloadStatus{
			Workload:      w,
			Replicas:      replicas,
			ReadyReplicas: dep.Status.ReadyReplicas,
			PodPhase:      podPhase,
		})
	}
	return statuses, nil
}

// ActivateWorkload scales the target workload to 1 and all others to 0.
func ActivateWorkload(ctx context.Context, client kubernetes.Interface, workloads []Workload, name string) error {
	found := false
	for _, w := range workloads {
		if w.Name == name {
			found = true
			break
		}
	}
	if !found {
		return fmt.Errorf("unknown workload: %s", name)
	}
	for _, w := range workloads {
		var target int32
		if w.Name == name {
			target = 1
		}
		if err := scaleDeployment(ctx, client, w.Namespace, w.DeploymentName, target); err != nil {
			return err
		}
	}
	return nil
}

// DeactivateAll scales all workloads to 0.
func DeactivateAll(ctx context.Context, client kubernetes.Interface, workloads []Workload) error {
	for _, w := range workloads {
		if err := scaleDeployment(ctx, client, w.Namespace, w.DeploymentName, 0); err != nil {
			return err
		}
	}
	return nil
}

func scaleDeployment(ctx context.Context, client kubernetes.Interface, namespace, name string, replicas int32) error {
	scale, err := client.AppsV1().Deployments(namespace).GetScale(ctx, name, metav1.GetOptions{})
	if err != nil {
		return fmt.Errorf("get scale %s/%s: %w", namespace, name, err)
	}
	scale.Spec.Replicas = replicas
	_, err = client.AppsV1().Deployments(namespace).UpdateScale(ctx, name, scale, metav1.UpdateOptions{})
	if err != nil {
		return fmt.Errorf("update scale %s/%s: %w", namespace, name, err)
	}
	return nil
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/gpu-switcher/app && go test -v ./...`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/gpu-switcher/app/k8s.go apps/gpu-switcher/app/k8s_test.go
git commit -m "feat(gpu-switcher): implement K8s client operations with tests"
```

---

### Task 8: Implement HTTP server and dashboard UI

**Files:**
- Create: `apps/gpu-switcher/app/main.go`
- Create: `apps/gpu-switcher/app/static/index.html`

- [ ] **Step 1: Create the dashboard HTML**

Create `apps/gpu-switcher/app/static/index.html` — a single-page dashboard using safe DOM construction (no innerHTML):

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GPU Switcher - Frank Cluster</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
    .container { max-width: 600px; width: 100%; padding: 2rem; }
    h1 { font-size: 1.5rem; margin-bottom: 0.5rem; color: #f8fafc; }
    .subtitle { color: #94a3b8; margin-bottom: 2rem; font-size: 0.875rem; }
    .card { background: #1e293b; border-radius: 12px; padding: 1.5rem; margin-bottom: 1rem; border: 1px solid #334155; transition: border-color 0.2s; }
    .card.active { border-color: #22c55e; }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
    .card-name { font-size: 1.125rem; font-weight: 600; }
    .badge { padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
    .badge-active { background: #166534; color: #86efac; }
    .badge-inactive { background: #1e293b; color: #64748b; border: 1px solid #334155; }
    .badge-pending { background: #854d0e; color: #fde047; }
    .meta { display: flex; gap: 1.5rem; color: #94a3b8; font-size: 0.875rem; }
    .actions { display: flex; gap: 0.75rem; margin-top: 2rem; }
    button { flex: 1; padding: 0.75rem 1.5rem; border-radius: 8px; border: none; font-size: 0.875rem; font-weight: 600; cursor: pointer; transition: background 0.2s, opacity 0.2s; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .btn-ollama { background: #3b82f6; color: white; }
    .btn-ollama:hover:not(:disabled) { background: #2563eb; }
    .btn-comfyui { background: #a855f7; color: white; }
    .btn-comfyui:hover:not(:disabled) { background: #9333ea; }
    .btn-stop { background: #334155; color: #e2e8f0; }
    .btn-stop:hover:not(:disabled) { background: #475569; }
    .error { background: #7f1d1d; color: #fca5a5; padding: 1rem; border-radius: 8px; margin-top: 1rem; display: none; }
    .loading { opacity: 0.6; pointer-events: none; }
    .refresh-note { text-align: center; color: #475569; font-size: 0.75rem; margin-top: 1rem; }
  </style>
</head>
<body>
  <div class="container">
    <h1>GPU Switcher</h1>
    <p class="subtitle">Frank Cluster - RTX 5070 Ti (16 GB)</p>

    <div id="workloads"></div>

    <div class="actions">
      <button class="btn-ollama" onclick="activate('ollama')">Activate Ollama</button>
      <button class="btn-comfyui" onclick="activate('comfyui')">Activate ComfyUI</button>
      <button class="btn-stop" onclick="deactivateAll()">Stop All</button>
    </div>

    <div id="error" class="error"></div>
    <p class="refresh-note">Auto-refreshes every 5 seconds</p>
  </div>

  <script>
    function createWorkloadCard(w) {
      var isActive = w.replicas > 0;
      var isReady = w.readyReplicas > 0;

      var card = document.createElement('div');
      card.className = 'card' + (isActive ? ' active' : '');

      var header = document.createElement('div');
      header.className = 'card-header';

      var nameEl = document.createElement('span');
      nameEl.className = 'card-name';
      nameEl.textContent = w.name;
      header.appendChild(nameEl);

      var badge = document.createElement('span');
      if (isActive && isReady) {
        badge.className = 'badge badge-active';
        badge.textContent = 'Active';
      } else if (isActive) {
        badge.className = 'badge badge-pending';
        badge.textContent = 'Starting';
      } else {
        badge.className = 'badge badge-inactive';
        badge.textContent = 'Inactive';
      }
      header.appendChild(badge);
      card.appendChild(header);

      var meta = document.createElement('div');
      meta.className = 'meta';
      var items = [
        'Replicas: ' + w.replicas,
        'Ready: ' + w.readyReplicas,
        'Pod: ' + w.podPhase
      ];
      items.forEach(function(text) {
        var span = document.createElement('span');
        span.textContent = text;
        meta.appendChild(span);
      });
      card.appendChild(meta);

      return card;
    }

    function renderWorkloads(workloads) {
      var container = document.getElementById('workloads');
      while (container.firstChild) {
        container.removeChild(container.firstChild);
      }
      workloads.forEach(function(w) {
        container.appendChild(createWorkloadCard(w));
      });
    }

    async function fetchStatus() {
      try {
        var resp = await fetch('/api/status');
        if (!resp.ok) throw new Error(await resp.text());
        var data = await resp.json();
        renderWorkloads(data);
        document.getElementById('error').style.display = 'none';
      } catch (e) {
        showError(e.message);
      }
    }

    async function activate(name) {
      if (!confirm('Switch GPU to ' + name + '? This will stop the other workload.')) return;
      document.body.classList.add('loading');
      try {
        var resp = await fetch('/api/activate/' + name, { method: 'POST' });
        if (!resp.ok) throw new Error(await resp.text());
        await fetchStatus();
      } catch (e) {
        showError(e.message);
      } finally {
        document.body.classList.remove('loading');
      }
    }

    async function deactivateAll() {
      if (!confirm('Stop all GPU workloads?')) return;
      document.body.classList.add('loading');
      try {
        var resp = await fetch('/api/deactivate', { method: 'POST' });
        if (!resp.ok) throw new Error(await resp.text());
        await fetchStatus();
      } catch (e) {
        showError(e.message);
      } finally {
        document.body.classList.remove('loading');
      }
    }

    function showError(msg) {
      var el = document.getElementById('error');
      el.textContent = msg;
      el.style.display = 'block';
    }

    fetchStatus();
    setInterval(fetchStatus, 5000);
  </script>
</body>
</html>
```

- [ ] **Step 2: Create main.go with HTTP server**

Create `apps/gpu-switcher/app/main.go`:

```go
package main

import (
	"context"
	"embed"
	"encoding/json"
	"fmt"
	"io/fs"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
)

//go:embed static
var staticFiles embed.FS

// workloadStatusJSON is the JSON response for a workload status.
type workloadStatusJSON struct {
	Name          string `json:"name"`
	Namespace     string `json:"namespace"`
	Replicas      int32  `json:"replicas"`
	ReadyReplicas int32  `json:"readyReplicas"`
	PodPhase      string `json:"podPhase"`
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	client, err := buildClient()
	if err != nil {
		log.Fatalf("Failed to create Kubernetes client: %v", err)
	}

	workloads := parseWorkloads()

	mux := http.NewServeMux()

	// Serve static files at root
	staticFS, _ := fs.Sub(staticFiles, "static")
	mux.Handle("/", http.FileServer(http.FS(staticFS)))

	// API: get status of all workloads
	mux.HandleFunc("/api/status", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
		defer cancel()
		statuses, err := GetStatus(ctx, client, workloads)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		resp := make([]workloadStatusJSON, len(statuses))
		for i, s := range statuses {
			resp[i] = workloadStatusJSON{
				Name:          s.Name,
				Namespace:     s.Namespace,
				Replicas:      s.Replicas,
				ReadyReplicas: s.ReadyReplicas,
				PodPhase:      s.PodPhase,
			}
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	})

	// API: activate a specific workload
	mux.HandleFunc("/api/activate/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		name := strings.TrimPrefix(r.URL.Path, "/api/activate/")
		if name == "" {
			http.Error(w, "workload name required", http.StatusBadRequest)
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
		defer cancel()
		if err := ActivateWorkload(ctx, client, workloads, name); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, "activated %s", name)
	})

	// API: deactivate all workloads
	mux.HandleFunc("/api/deactivate", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
		defer cancel()
		if err := DeactivateAll(ctx, client, workloads); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, "all workloads deactivated")
	})

	log.Printf("GPU Switcher listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}

// buildClient creates a Kubernetes clientset using in-cluster config.
func buildClient() (kubernetes.Interface, error) {
	config, err := rest.InClusterConfig()
	if err != nil {
		return nil, fmt.Errorf("in-cluster config: %w", err)
	}
	return kubernetes.NewForConfig(config)
}

// parseWorkloads reads workload definitions from the WORKLOADS env var.
// Format: "name:namespace:deployment,name:namespace:deployment,..."
// Default: "ollama:ollama:ollama,comfyui:comfyui:comfyui"
func parseWorkloads() []Workload {
	raw := os.Getenv("WORKLOADS")
	if raw == "" {
		raw = "ollama:ollama:ollama,comfyui:comfyui:comfyui"
	}
	var workloads []Workload
	for _, entry := range strings.Split(raw, ",") {
		parts := strings.SplitN(entry, ":", 3)
		if len(parts) != 3 {
			log.Fatalf("invalid workload entry: %s (expected name:namespace:deployment)", entry)
		}
		workloads = append(workloads, Workload{
			Name:           parts[0],
			Namespace:      parts[1],
			DeploymentName: parts[2],
		})
	}
	return workloads
}
```

> **Key decisions:**
> - Workload definitions via `WORKLOADS` env var — extensible without code changes
> - In-cluster K8s client (runs as a pod with ServiceAccount)
> - Embedded static files via `//go:embed` — single binary, no runtime dependencies
> - 5-second auto-refresh in the UI for live status updates
> - Confirm dialog before any switching action

- [ ] **Step 3: Verify it compiles**

Run: `cd apps/gpu-switcher/app && go build -o /dev/null .`
Expected: Compiles without errors.

- [ ] **Step 4: Run all tests**

Run: `cd apps/gpu-switcher/app && go test -v ./...`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/gpu-switcher/app/main.go apps/gpu-switcher/app/static/index.html
git commit -m "feat(gpu-switcher): add HTTP server and dashboard UI"
```

---

### Task 9: Create Dockerfile and build image

**Files:**
- Create: `apps/gpu-switcher/app/Dockerfile`

- [ ] **Step 1: Create multi-stage Dockerfile**

```dockerfile
# apps/gpu-switcher/app/Dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o gpu-switcher .

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /build/gpu-switcher /gpu-switcher
USER nonroot:nonroot
EXPOSE 8080
ENTRYPOINT ["/gpu-switcher"]
```

> Uses distroless for minimal attack surface. `nonroot` user for security. Static binary (CGO_ENABLED=0) so no libc needed.

- [ ] **Step 2: Verify Docker and GHCR access**

Run:
```bash
docker info > /dev/null 2>&1 && echo "Docker OK" || echo "Docker not available"
echo $GITHUB_TOKEN | docker login ghcr.io -u derio-net --password-stdin
```
Expected: Docker available and GHCR login successful.

- [ ] **Step 3: Build the image for amd64**

Run:
```bash
cd apps/gpu-switcher/app && docker build --platform linux/amd64 -t ghcr.io/derio-net/gpu-switcher:latest .
```
Expected: Image builds successfully.

> **Why amd64 only?** GPU Switcher runs on non-GPU nodes, but the cluster has ARM nodes (raspi-1/2). We constrain to amd64 via nodeSelector in the Deployment (Task 12) and build only amd64 to keep it simple.

- [ ] **Step 4: Push to GHCR**

Run:
```bash
docker push ghcr.io/derio-net/gpu-switcher:latest
```
Expected: Image pushed to `ghcr.io/derio-net/gpu-switcher:latest`.

- [ ] **Step 4: Tag with a version for reproducibility**

Run:
```bash
docker tag ghcr.io/derio-net/gpu-switcher:latest ghcr.io/derio-net/gpu-switcher:v0.1.0
docker push ghcr.io/derio-net/gpu-switcher:v0.1.0
```

- [ ] **Step 5: Commit**

```bash
git add apps/gpu-switcher/app/Dockerfile
git commit -m "feat(gpu-switcher): add multi-stage Dockerfile"
```

---

## Chunk 3: GPU Switcher ArgoCD Deployment

> **Prerequisite:** Chunk 2 must be complete — the GPU Switcher container image (`ghcr.io/derio-net/gpu-switcher:v0.1.0`) must be built and pushed to GHCR before these manifests can work. Verify with: `docker manifest inspect ghcr.io/derio-net/gpu-switcher:v0.1.0`

### Task 10: Create GPU Switcher namespace

**Files:**
- Create: `apps/root/templates/ns-gpu-switcher.yaml`

- [ ] **Step 1: Create the namespace manifest**

```yaml
# apps/root/templates/ns-gpu-switcher.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: gpu-switcher
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/audit: baseline
    pod-security.kubernetes.io/warn: baseline
```

> **Note:** `baseline` (not `privileged`) — GPU Switcher doesn't need GPU or host access, just K8s API calls.

- [ ] **Step 2: Commit**

```bash
git add apps/root/templates/ns-gpu-switcher.yaml
git commit -m "feat(gpu-switcher): add gpu-switcher namespace"
```

---

### Task 11: Create RBAC resources

**Files:**
- Create: `apps/gpu-switcher/manifests/serviceaccount.yaml`
- Create: `apps/gpu-switcher/manifests/clusterrole.yaml`
- Create: `apps/gpu-switcher/manifests/clusterrolebinding.yaml`

- [ ] **Step 1: Create ServiceAccount**

```yaml
# apps/gpu-switcher/manifests/serviceaccount.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: gpu-switcher
  namespace: gpu-switcher
  labels:
    app.kubernetes.io/name: gpu-switcher
```

- [ ] **Step 2: Create ClusterRole**

```yaml
# apps/gpu-switcher/manifests/clusterrole.yaml
# Scoped permissions: scale deployments + read pods in GPU workload namespaces
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: gpu-switcher
  labels:
    app.kubernetes.io/name: gpu-switcher
rules:
  # Read deployments and their scale subresource
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get"]
  - apiGroups: ["apps"]
    resources: ["deployments/scale"]
    verbs: ["get", "update", "patch"]
  # Read pods for status display
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
```

> **Why ClusterRole (not Role)?** GPU Switcher needs to access deployments across two namespaces (`ollama` and `comfyui`). A ClusterRole with a ClusterRoleBinding is the cleanest way. The verb set is minimal — no create, delete, or list on deployments.

- [ ] **Step 3: Create ClusterRoleBinding**

```yaml
# apps/gpu-switcher/manifests/clusterrolebinding.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: gpu-switcher
  labels:
    app.kubernetes.io/name: gpu-switcher
subjects:
  - kind: ServiceAccount
    name: gpu-switcher
    namespace: gpu-switcher
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: gpu-switcher
```

- [ ] **Step 4: Validate all RBAC manifests**

Run:
```bash
kubectl apply --dry-run=client -f apps/gpu-switcher/manifests/serviceaccount.yaml && \
kubectl apply --dry-run=client -f apps/gpu-switcher/manifests/clusterrole.yaml && \
kubectl apply --dry-run=client -f apps/gpu-switcher/manifests/clusterrolebinding.yaml
```
Expected: All created (dry run).

- [ ] **Step 5: Commit**

```bash
git add apps/gpu-switcher/manifests/serviceaccount.yaml apps/gpu-switcher/manifests/clusterrole.yaml apps/gpu-switcher/manifests/clusterrolebinding.yaml
git commit -m "feat(gpu-switcher): add RBAC (ServiceAccount, ClusterRole, ClusterRoleBinding)"
```

---

### Task 12: Create GPU Switcher Deployment and Service

**Files:**
- Create: `apps/gpu-switcher/manifests/deployment.yaml`
- Create: `apps/gpu-switcher/manifests/service.yaml`

- [ ] **Step 1: Create the Deployment**

```yaml
# apps/gpu-switcher/manifests/deployment.yaml
# GPU Switcher dashboard — runs on any node (no GPU needed)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gpu-switcher
  namespace: gpu-switcher
  labels:
    app.kubernetes.io/name: gpu-switcher
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: gpu-switcher
  template:
    metadata:
      labels:
        app.kubernetes.io/name: gpu-switcher
    spec:
      serviceAccountName: gpu-switcher
      containers:
        - name: gpu-switcher
          image: ghcr.io/derio-net/gpu-switcher:v0.1.0
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
          env:
            - name: WORKLOADS
              value: "ollama:ollama:ollama,comfyui:comfyui:comfyui"
          resources:
            requests:
              cpu: 50m
              memory: 32Mi
            limits:
              cpu: 200m
              memory: 64Mi
          livenessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 5
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 2
            periodSeconds: 10
      # Constrain to amd64 (image is amd64-only; avoids ARM raspi nodes)
      nodeSelector:
        kubernetes.io/arch: amd64
```

- [ ] **Step 2: Create the LoadBalancer Service**

```yaml
# apps/gpu-switcher/manifests/service.yaml
# GPU Switcher dashboard at 192.168.55.214 via Cilium L2 IPAM
apiVersion: v1
kind: Service
metadata:
  name: gpu-switcher
  namespace: gpu-switcher
  annotations:
    lbipam.cilium.io/ips: "192.168.55.214"
  labels:
    app.kubernetes.io/name: gpu-switcher
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/name: gpu-switcher
  ports:
    - name: http
      port: 8080
      targetPort: http
      protocol: TCP
```

- [ ] **Step 3: Validate both**

Run:
```bash
kubectl apply --dry-run=client -f apps/gpu-switcher/manifests/deployment.yaml && \
kubectl apply --dry-run=client -f apps/gpu-switcher/manifests/service.yaml
```
Expected: Both created (dry run).

- [ ] **Step 4: Commit**

```bash
git add apps/gpu-switcher/manifests/deployment.yaml apps/gpu-switcher/manifests/service.yaml
git commit -m "feat(gpu-switcher): add Deployment and LoadBalancer Service"
```

---

### Task 13: Create GPU Switcher ArgoCD Application CR

**Files:**
- Create: `apps/root/templates/gpu-switcher.yaml`

- [ ] **Step 1: Create the Application CR**

```yaml
# apps/root/templates/gpu-switcher.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: gpu-switcher
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/gpu-switcher/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: gpu-switcher
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
      - ServerSideApply=true
```

- [ ] **Step 2: Verify template renders**

Run: `helm template apps/root/ | grep -A18 'name: gpu-switcher'`
Expected: Application CR renders correctly.

- [ ] **Step 3: Commit**

```bash
git add apps/root/templates/gpu-switcher.yaml
git commit -m "feat(gpu-switcher): add ArgoCD Application CR"
```

---

## Chunk 4: Integration & Manual Verification

### Task 14: Push and verify ArgoCD sync

- [ ] **Step 1: Push all commits to main**

Run: `git push origin main`

- [ ] **Step 2: Wait for ArgoCD to sync the root app**

Run:
```bash
argocd app sync root --port-forward --port-forward-namespace argocd
```

- [ ] **Step 3: Verify ComfyUI app is synced and healthy**

Run:
```bash
argocd app get comfyui --port-forward --port-forward-namespace argocd
```
Expected: Status `Synced`, Health `Healthy` (or `Suspended` since replicas=0).

- [ ] **Step 4: Verify GPU Switcher app is synced and running**

Run:
```bash
argocd app get gpu-switcher --port-forward --port-forward-namespace argocd
kubectl get pods -n gpu-switcher
```
Expected: GPU Switcher pod is Running.

- [ ] **Step 5: Verify ComfyUI PVC is bound**

Run: `kubectl get pvc -n comfyui`
Expected: `comfyui-models` PVC is `Bound` (Longhorn provisioned the volume).

- [ ] **Step 6: Verify GPU Switcher is accessible**

Run: `curl -s http://192.168.55.214:8080/api/status | jq .`
Expected: JSON with two workloads — ollama (replicas=1) and comfyui (replicas=0).

---

### Task 15: Test GPU switching end-to-end

- [ ] **Step 1: Open GPU Switcher UI in browser**

Navigate to `http://192.168.55.214:8080`
Expected: Dashboard shows Ollama as Active, ComfyUI as Inactive.

- [ ] **Step 2: Switch to ComfyUI via the dashboard**

Click "Activate ComfyUI" and confirm.
Expected: Ollama scales down, ComfyUI scales up. UI shows ComfyUI as "Starting" then "Active".

- [ ] **Step 3: Verify ComfyUI is running**

Run:
```bash
kubectl get pods -n comfyui
kubectl get pods -n ollama
```
Expected: ComfyUI pod Running in `comfyui`, no pods in `ollama`.

- [ ] **Step 4: Verify ComfyUI Web UI is accessible**

Navigate to `http://192.168.55.213:8188`
Expected: ComfyUI node-based workflow editor loads.

- [ ] **Step 5: Switch back to Ollama**

Click "Activate Ollama" in GPU Switcher and confirm.
Expected: ComfyUI scales down, Ollama scales up.

- [ ] **Step 6: Verify Ollama restored**

Run:
```bash
kubectl get pods -n ollama
kubectl exec -n ollama deploy/ollama -- ollama list
```
Expected: Ollama pod Running, model list returned.

- [ ] **Step 7: Test "Stop All"**

Click "Stop All" in GPU Switcher and confirm.
Expected: Both workloads scaled to 0. No GPU pods running.

---

### Task 16: Download initial models (one-time setup)

```yaml
# manual-operation
id: media-comfyui-model-download
layer: media
app: comfyui
plan: docs/superpowers/plans/2026-03-14--media--comfyui-gpu-switcher.md
when: "After Task 15 - ComfyUI first confirmed running"
why_manual: "Model files must be downloaded interactively into the PVC; cannot be declarative"
commands:
  - "# Activate ComfyUI via GPU Switcher UI at http://192.168.55.214:8080"
  - "# Wait for ComfyUI pod to be Running"
  - "# Open ComfyUI Manager at http://192.168.55.213:8188 -> Manager -> Install Models"
  - "# Install LTX-2.3 video model (~5GB)"
  - "# Optionally install Flux/SDXL image model and audio models"
verify:
  - "kubectl exec -n comfyui deploy/comfyui -- ls -la /opt/ComfyUI/models/checkpoints/"
  - "# Verify models appear in ComfyUI Web UI model dropdown"
status: pending
```

---

### Task 17: Final commit — update CLAUDE.md services table

**Files:**
- Modify: `CLAUDE.md` (Services table)

- [ ] **Step 0: Add Traefik routes on raspi-omni**

ComfyUI and GPU Switcher need Traefik routes to be accessible at their `frank.derio.net` subdomains. Traefik runs outside K8s on raspi-omni.

```yaml
# manual-operation
id: media-traefik-comfyui-route
layer: media
app: comfyui
plan: docs/superpowers/plans/2026-03-14--media--comfyui-gpu-switcher.md
when: "After ComfyUI deployment is healthy — add Traefik route on raspi-omni"
why_manual: "Traefik runs outside K8s on raspi-omni, managed via Ansible"
commands:
  - "Add comfyui entry to Traefik Ansible vars: host comfyui.frank.derio.net, backend 192.168.55.213:8188"
  - "Add gpu-switcher entry to Traefik Ansible vars: host gpu.frank.derio.net, backend 192.168.55.214:8080"
  - "Run Ansible playbook to apply Traefik config on raspi-omni"
verify:
  - "curl -sk https://comfyui.frank.derio.net/ returns 200 (or auth redirect if forward-auth enabled)"
  - "curl -sk https://gpu.frank.derio.net/ returns 200 (or auth redirect if forward-auth enabled)"
status: pending
```

- [ ] **Step 1: Add ComfyUI and GPU Switcher to the Services table in CLAUDE.md**

Add after the Paperclip entry:

```markdown
| ComfyUI | 192.168.55.213 | Cilium L2 LoadBalancer (port 8188) |
| GPU Switcher | 192.168.55.214 | Cilium L2 LoadBalancer (port 8080) |
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add ComfyUI and GPU Switcher to services table"
```
