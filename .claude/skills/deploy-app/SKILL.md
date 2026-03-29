---
name: deploy-app
description: Deploy a new app to Frank cluster via ArgoCD App-of-Apps pattern
user-invocable: true
disable-model-invocation: false
arguments:
  - name: app-name
    description: Name of the app to deploy (kebab-case, e.g. "cert-manager")
    required: true
  - name: type
    description: "helm (upstream Helm chart) or manifests (raw K8s manifests)"
    required: false
    default: helm
---

# Deploy App to ArgoCD

Deploy a new application to Frank cluster using the App-of-Apps pattern.

## Arguments

- `$ARGUMENTS.app-name` — the app name (kebab-case)
- `$ARGUMENTS.type` — `helm` (default) or `manifests`

## Steps

### 1. Research

Before creating any files, research the app:
- Find the official Helm chart repository URL and latest stable version
- Identify the correct namespace convention
- Check if the app needs a dedicated namespace
- Review default values and determine what needs customizing for this cluster

### 2. Create App Values

**For Helm charts** (`type=helm`):

Create `apps/$ARGUMENTS.app-name/values.yaml` with the Helm values.
Only include values that differ from upstream defaults.

**For raw manifests** (`type=manifests`):

Create `apps/$ARGUMENTS.app-name/manifests/` directory with the K8s YAML files.

### 3. Create Namespace Template (if needed)

If the app needs a dedicated namespace, create `apps/root/templates/ns-$ARGUMENTS.app-name.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: <namespace>
```

### 4. Create Application CR

Create `apps/root/templates/$ARGUMENTS.app-name.yaml`.

**For Helm charts** — use dual-source pattern (reference `apps/root/templates/cilium.yaml` as the canonical example):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: $ARGUMENTS.app-name
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: <upstream-helm-repo-url>
      chart: <chart-name>
      targetRevision: "<version>"
      helm:
        releaseName: $ARGUMENTS.app-name
        valueFiles:
          - $values/apps/$ARGUMENTS.app-name/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: <namespace>
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      jsonPointers:
        - /data
```

**For raw manifests** — use single-source pattern (reference `apps/root/templates/openrgb.yaml`):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: $ARGUMENTS.app-name
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/$ARGUMENTS.app-name/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: <namespace>
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
```

### 5. Conventions (CRITICAL)

- Always use `ServerSideApply=true` for Helm-based apps
- Always set `prune: false` — manual pruning only
- Always set `selfHeal: true`
- Always ignore Secret `/data` diffs for Helm-based apps
- Always add the `resources-finalizer.argocd.argoproj.io` finalizer
- Use `{{ .Values.repoURL }}` and `{{ .Values.targetRevision }}` — never hardcode
- Use `{{ .Values.destination.server }}` — never hardcode

### 6. Summary

After creating all files, show the user:
- Files created
- What to do next (commit, push, ArgoCD auto-syncs)
- How to verify: `argocd app list --port-forward --port-forward-namespace argocd`
