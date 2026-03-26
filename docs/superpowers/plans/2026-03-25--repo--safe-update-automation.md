# Safe Update Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate Helm chart update detection + pre-merge smoke testing (ArgoCD layer) and Talos/Kubernetes version tracking (Omni layer) for the Frank cluster.

**Architecture:** Three pipelines: (1) Renovate opens PRs for chart version bumps, GitHub Actions runs a Helm smoke test in an ephemeral namespace on a self-hosted ARC runner pinned to pc-1, and auto-merges stateless apps on green; (2) a weekly cron workflow detects new Talos/K8s patch releases and opens a PR updating `versions.yaml`; (3) ARC v2 (controller + runner set as two separate ArgoCD apps) provides the self-hosted runner with in-cluster kubectl access.

**Tech Stack:** ARC v2 (`gha-runner-scale-set-controller` + `gha-runner-scale-set` OCI charts), Renovate GitHub App, GitHub Actions, Helm 3, kubectl, yq, SOPS/age.

**Design doc:** `docs/superpowers/specs/2026-03-25--repo--safe-update-automation-design.md`
**Status:** In Progress

---

## File Structure

```
apps/arc-controller/
  values.yaml                          # gha-runner-scale-set-controller Helm values
apps/arc-runners/
  values.yaml                          # gha-runner-scale-set Helm values (pc-1 pin)
  manifests/
    rbac.yaml                          # ClusterRole + ClusterRoleBinding for smoke tests
apps/root/templates/
  arc-controller.yaml                  # Application CR, sync-wave: "-1"
  arc-runners.yaml                     # Application CR, ignoreDifferences on Secrets
secrets/arc/
  github-app-secret.yaml               # SOPS-encrypted GitHub App credentials
versions.yaml                          # Declarative Talos + K8s version targets
renovate.json                          # Renovate config (regex manager, packageRules)
.github/workflows/
  smoke-test.yaml                      # Helm smoke test on Renovate PRs
  version-check.yaml                   # Omni/Talos version detection (weekly cron)
```

---

## Chunk 1: ARC Self-Hosted Runner

ARC v2 uses two charts: `gha-runner-scale-set-controller` (cluster-scoped, sync-wave -1) and `gha-runner-scale-set` (namespaced runner pool). The runner needs a GitHub App installed on the repo and its credentials as a Kubernetes Secret before it can register.

**Before starting:** Install the ARC GitHub App on your GitHub account/repo. From the [Actions Runner Controller GitHub App setup](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners-with-actions-runner-controller/authenticating-to-the-github-api), create a GitHub App with the required permissions and note: App ID, Installation ID, and private key (PEM).

### Task 1: ARC Controller ArgoCD App

**Files:**
- Create: `apps/arc-controller/values.yaml`
- Create: `apps/root/templates/arc-controller.yaml`

- [ ] **Step 1: Create controller values**

Create `apps/arc-controller/values.yaml`:

```yaml
# gha-runner-scale-set-controller
# Chart: oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller
# Check latest version: helm show chart oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller
#
# The controller is a cluster-scoped deployment that manages RunnerScaleSet CRDs.
# One instance per cluster — all runner sets share this controller.

replicaCount: 1

resources:
  limits:
    cpu: 500m
    memory: 128Mi
  requests:
    cpu: 100m
    memory: 64Mi
```

- [ ] **Step 2: Look up the current stable chart version**

```bash
helm show chart oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller 2>/dev/null | grep '^version:'
```

Note the version for use in the Application CR.

- [ ] **Step 3: Create controller Application CR**

Create `apps/root/templates/arc-controller.yaml` (substitute the version from step 2):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: arc-controller
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-1"
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: oci://ghcr.io/actions/actions-runner-controller-charts
      chart: gha-runner-scale-set-controller
      targetRevision: "0.10.1"          # update to version from step 2
      helm:
        releaseName: arc-controller
        valueFiles:
          - $values/apps/arc-controller/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: arc-system
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

- [ ] **Step 4: Commit**

```bash
git add apps/arc-controller/values.yaml apps/root/templates/arc-controller.yaml
git commit -m "feat(repo): add ARC controller ArgoCD app"
```

---

### Task 2: ARC Runner Set ArgoCD App + RBAC

The runner set registers with GitHub and runs smoke test jobs. It needs: (a) the GitHub App secret (Task 3), (b) `nodeSelector` to pin to pc-1, (c) RBAC allowing it to manage `smoke-test-*` namespaces and install Helm charts within them.

**Files:**
- Create: `apps/arc-runners/values.yaml`
- Create: `apps/arc-runners/manifests/rbac.yaml`
- Create: `apps/root/templates/arc-runners.yaml`

- [ ] **Step 1: Create runner set values**

Create `apps/arc-runners/values.yaml`:

```yaml
# gha-runner-scale-set
# Chart: oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set
#
# Registers a runner pool labelled "frank-cluster" pinned to pc-1.
# The GitHub App credentials are in the arc-github-app-secret Secret (applied out-of-band).

githubConfigUrl: "https://github.com/<YOUR_GITHUB_ORG_OR_USER>/<YOUR_REPO>"
githubConfigSecret: arc-github-app-secret

minRunners: 1
maxRunners: 3

runnerGroup: "Default"

template:
  spec:
    nodeSelector:
      kubernetes.io/hostname: pc-1
    containers:
      - name: runner
        image: ghcr.io/actions/actions-runner:latest
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 2000m
            memory: 2Gi
        env:
          - name: ACTIONS_RUNNER_CONTAINER_HOOKS
            value: /home/runner/k8s/index.js
          - name: ACTIONS_RUNNER_POD_NAME
            valueFrom:
              fieldRef:
                fieldPath: metadata.name
          - name: ACTIONS_RUNNER_REQUIRE_JOB_CONTAINER
            value: "false"
    initContainers:
      - name: init-dind-externals
        image: ghcr.io/actions/actions-runner:latest
        command: ["cp", "-r", "-v", "/home/runner/externals/.", "/home/runner/tmpDir/"]
        volumeMounts:
          - name: dind-externals
            mountPath: /home/runner/tmpDir
    volumes:
      - name: dind-externals
        emptyDir: {}
```

Replace `<YOUR_GITHUB_ORG_OR_USER>/<YOUR_REPO>` with the actual repo path (e.g. `derio-net/frank-cluster`).

- [ ] **Step 2: Create RBAC manifest**

Create `apps/arc-runners/manifests/rbac.yaml`. This grants the runner's ServiceAccount permission to manage ephemeral `smoke-test-*` namespaces and install arbitrary Helm charts within them.

Note: Kubernetes doesn't support wildcard namespace matching in RoleBindings. The ClusterRole grants namespace-scoped resource access cluster-wide, but the runner will only exercise it within `smoke-test-*` namespaces in practice.

```yaml
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: arc-smoke-test-namespace-manager
rules:
  # Namespace lifecycle (smoke-test-* only enforced by convention)
  - apiGroups: [""]
    resources: ["namespaces"]
    verbs: ["create", "delete", "get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: arc-smoke-test-workloads
rules:
  # All namespaced resources — needed for arbitrary Helm chart installs
  - apiGroups: ["*"]
    resources: ["*"]
    verbs: ["*"]
---
# Bind namespace manager role to the runner ServiceAccount
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: arc-smoke-test-namespace-manager
subjects:
  - kind: ServiceAccount
    name: frank-cluster-gha-rs-no-permission   # ARC v2 default SA name pattern: <runner-set-name>-no-permission
    namespace: arc-system
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: arc-smoke-test-namespace-manager
---
# Bind workload role — cluster-wide but only exercised in smoke-test-* by convention
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: arc-smoke-test-workloads
subjects:
  - kind: ServiceAccount
    name: frank-cluster-gha-rs-no-permission
    namespace: arc-system
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: arc-smoke-test-workloads
```

**Important:** Verify the actual ServiceAccount name after deploying. ARC v2 names it `<runner-set-release-name>-gha-rs-no-permission`. If you name the Helm release `frank-cluster`, it becomes `frank-cluster-gha-rs-no-permission`. Check with: `kubectl get sa -n arc-system`.

- [ ] **Step 3: Create runner set Application CR**

Create `apps/root/templates/arc-runners.yaml` (substitute chart version from Task 1 Step 2):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: arc-runners
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: oci://ghcr.io/actions/actions-runner-controller-charts
      chart: gha-runner-scale-set
      targetRevision: "0.10.1"          # update to version from Task 1 Step 2
      helm:
        releaseName: frank-cluster
        valueFiles:
          - $values/apps/arc-runners/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: arc-system
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
  # ARC continuously rotates runner registration tokens into Secrets.
  # Ignore Secret /data diffs to prevent perpetual OutOfSync.
  ignoreDifferences:
    - group: ""
      kind: Secret
      namespace: arc-system
      jsonPointers:
        - /data
```

- [ ] **Step 4: Add raw manifests Application CR for RBAC**

The RBAC lives in `apps/arc-runners/manifests/` and needs its own ArgoCD source or can be added as a second source to the runner set app. Add it as a second Helm source by appending to the `sources` array of `arc-runners.yaml`:

```yaml
    # Raw RBAC manifests
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      path: apps/arc-runners/manifests
```

Place this as the third entry in `sources` (after the OCI chart source and before the `ref: values` source). The full `sources` list order: OCI chart, RBAC manifests path, values ref.

- [ ] **Step 5: Commit**

```bash
git add apps/arc-runners/ apps/root/templates/arc-runners.yaml
git commit -m "feat(repo): add ARC runner set ArgoCD app with smoke-test RBAC"
```

---

### Task 3: Bootstrap Secret (Manual Operation)

The GitHub App credentials must exist as a Kubernetes Secret before the runner pod can register. This is a SOPS-encrypted bootstrap secret applied out-of-band.

```yaml
# manual-operation
id: arc-github-app-secret
layer: repo
app: arc-runners
plan: docs/superpowers/plans/2026-03-25--repo--safe-update-automation.md
when: "After arc-controller and arc-runners apps are synced by ArgoCD, before runner pod reaches Running state"
why_manual: "GitHub App credentials are a bootstrap secret. The runner cannot register without it, and SOPS+ArgoCD don't mix per repo convention."
commands:
  - |
    # Create the Secret manifest
    kubectl create secret generic arc-github-app-secret \
      --namespace arc-system \
      --from-literal=github_app_id=<APP_ID> \
      --from-literal=github_app_installation_id=<INSTALLATION_ID> \
      --from-literal=github_app_private_key="$(cat path/to/private-key.pem)" \
      --dry-run=client -o yaml > /tmp/arc-secret.yaml
    # Encrypt with SOPS (use the same age key as other secrets/)
    sops --encrypt /tmp/arc-secret.yaml > secrets/arc/github-app-secret.yaml
    rm /tmp/arc-secret.yaml
    # Apply to cluster
    sops --decrypt secrets/arc/github-app-secret.yaml | kubectl apply -f -
verify:
  - kubectl get secret arc-github-app-secret -n arc-system
  - kubectl get pods -n arc-system   # runner pod should reach Running within ~60s
  - kubectl get runners -n arc-system  # should show registered runner
status: pending
```

- [ ] **Step 1: Create secrets directory**

```bash
mkdir -p secrets/arc
```

- [ ] **Step 2: Apply and encrypt the secret**

Follow the commands in the manual-operation block above. Replace `<APP_ID>`, `<INSTALLATION_ID>`, and `path/to/private-key.pem` with your actual GitHub App values.

- [ ] **Step 3: Commit the encrypted secret**

```bash
git add secrets/arc/github-app-secret.yaml
git commit -m "feat(repo): add SOPS-encrypted ARC GitHub App secret"
```

- [ ] **Step 4: Push and verify runner registers**

```bash
git push
# Wait for ArgoCD to sync arc-controller (wave -1) then arc-runners (wave 0)
source .env
kubectl get pods -n arc-system -w
# Expected: arc-controller pod Running, frank-cluster-* runner pod Running
kubectl get runners -n arc-system
# Expected: runner shows as registered
```

Also verify the runner is pinned to pc-1:
```bash
kubectl get pod -n arc-system -o wide | grep runner
# EXPECTED: node column shows "pc-1"
```

---

## Chunk 2: Version Tracking

### Task 4: Create versions.yaml

**Files:**
- Create: `versions.yaml`

- [ ] **Step 1: Check current cluster versions**

```bash
source .env
omnictl get cluster frank -o yaml | grep -E 'talosVersion|kubernetesVersion'
# Note the current running versions
```

- [ ] **Step 2: Create versions.yaml**

Create `versions.yaml` at repo root with the actual running versions from step 1:

```yaml
# versions.yaml
# Declarative record of target cluster versions for Frank.
# Updated by .github/workflows/version-check.yaml when new stable patch releases exist.
# K8s minor version is pinned — update manually when Omni supports a new minor.
# Omni applies the actual upgrade; this file is the audit trail and PR review trigger.

talos: v1.9.x          # replace x with actual patch from omnictl output
kubernetes:
  minor: "1.32"        # pinned — only patch bumps are automated
  patch: v1.32.x       # replace x with actual patch from omnictl output
```

- [ ] **Step 3: Commit**

```bash
git add versions.yaml
git commit -m "feat(repo): add versions.yaml for Talos/K8s version tracking"
```

---

### Task 5: Omni/Talos Version Check Workflow

This workflow runs weekly, compares current versions in `versions.yaml` against latest stable GitHub releases, and opens a PR if newer patches exist.

**Files:**
- Create: `.github/workflows/version-check.yaml`

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/version-check.yaml`:

```yaml
name: Version Check

on:
  schedule:
    - cron: "0 9 * * 1"   # Monday 09:00 UTC
  workflow_dispatch:        # allow manual trigger

permissions:
  contents: write
  pull-requests: write

jobs:
  check-versions:
    # Runs on GitHub-hosted runner — only needs GitHub API and git, no cluster access.
    # This keeps version detection independent of the ARC runner being healthy.
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Install yq
        run: |
          if ! command -v yq &>/dev/null; then
            wget -qO /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64
            chmod +x /usr/local/bin/yq
          fi

      - name: Read current versions
        id: current
        run: |
          TALOS=$(yq '.talos' versions.yaml)
          K8S_MINOR=$(yq '.kubernetes.minor' versions.yaml)
          K8S_PATCH=$(yq '.kubernetes.patch' versions.yaml)
          echo "talos=$TALOS" >> $GITHUB_OUTPUT
          echo "k8s_minor=$K8S_MINOR" >> $GITHUB_OUTPUT
          echo "k8s_patch=$K8S_PATCH" >> $GITHUB_OUTPUT

      - name: Get latest stable Talos release
        id: latest_talos
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          # Extract current minor from current talos version (e.g. v1.9.3 -> 1.9)
          CURRENT_TALOS="${{ steps.current.outputs.talos }}"
          CURRENT_MINOR=$(echo "$CURRENT_TALOS" | grep -oP 'v\d+\.\d+')
          # Find latest patch within same minor
          LATEST=$(gh api repos/siderolabs/talos/releases \
            --jq "[.[] | select(.prerelease == false) | select(.tag_name | startswith(\"$CURRENT_MINOR.\")) | .tag_name] | first")
          echo "version=$LATEST" >> $GITHUB_OUTPUT
          echo "release_url=https://github.com/siderolabs/talos/releases/tag/$LATEST" >> $GITHUB_OUTPUT

      - name: Get latest stable K8s release
        id: latest_k8s
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          MINOR="v${{ steps.current.outputs.k8s_minor }}"
          LATEST=$(gh api repos/kubernetes/kubernetes/releases \
            --jq "[.[] | select(.prerelease == false) | select(.tag_name | startswith(\"$MINOR.\")) | .tag_name] | first")
          echo "version=$LATEST" >> $GITHUB_OUTPUT
          echo "release_url=https://github.com/kubernetes/kubernetes/releases/tag/$LATEST" >> $GITHUB_OUTPUT

      - name: Check for updates
        id: updates
        run: |
          TALOS_CHANGED=false
          K8S_CHANGED=false
          if [ "${{ steps.latest_talos.outputs.version }}" != "${{ steps.current.outputs.talos }}" ]; then
            TALOS_CHANGED=true
          fi
          if [ "${{ steps.latest_k8s.outputs.version }}" != "${{ steps.current.outputs.k8s_patch }}" ]; then
            K8S_CHANGED=true
          fi
          echo "talos_changed=$TALOS_CHANGED" >> $GITHUB_OUTPUT
          echo "k8s_changed=$K8S_CHANGED" >> $GITHUB_OUTPUT

      - name: Update versions.yaml
        if: steps.updates.outputs.talos_changed == 'true' || steps.updates.outputs.k8s_changed == 'true'
        run: |
          if [ "${{ steps.updates.outputs.talos_changed }}" == "true" ]; then
            yq -i '.talos = "${{ steps.latest_talos.outputs.version }}"' versions.yaml
          fi
          if [ "${{ steps.updates.outputs.k8s_changed }}" == "true" ]; then
            yq -i '.kubernetes.patch = "${{ steps.latest_k8s.outputs.version }}"' versions.yaml
          fi

      - name: Open PR
        if: steps.updates.outputs.talos_changed == 'true' || steps.updates.outputs.k8s_changed == 'true'
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          BRANCH="update/cluster-versions-$(date +%Y%m%d)"
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git checkout -b "$BRANCH"
          git add versions.yaml
          git commit -m "chore(os): update cluster versions"
          git push origin "$BRANCH"

          BODY="## Cluster Version Updates\n\n"
          if [ "${{ steps.updates.outputs.talos_changed }}" == "true" ]; then
            BODY+="- **Talos:** ${{ steps.current.outputs.talos }} → ${{ steps.latest_talos.outputs.version }} ([release notes](${{ steps.latest_talos.outputs.release_url }}))\n"
          fi
          if [ "${{ steps.updates.outputs.k8s_changed }}" == "true" ]; then
            BODY+="- **Kubernetes:** ${{ steps.current.outputs.k8s_patch }} → ${{ steps.latest_k8s.outputs.version }} ([release notes](${{ steps.latest_k8s.outputs.release_url }}))\n"
          fi
          BODY+="\n### Before merging\n- [ ] Review release notes for breaking changes\n- [ ] Verify Omni supports this Talos/K8s combination\n\n### After merging\n\`\`\`bash\nomnictl patch cluster frank --patch '[{\"op\":\"replace\",\"path\":\"/spec/talosVersion\",\"value\":\"${{ steps.latest_talos.outputs.version }}\"}]'\n\`\`\`\n"

          gh pr create \
            --title "chore(os): update cluster versions" \
            --body "$(printf '%b' "$BODY")" \
            --base main \
            --head "$BRANCH"
```

- [ ] **Step 2: Test by triggering manually**

After the runner is live (Task 3 complete), trigger the workflow manually:

```bash
# In GitHub UI: Actions → Version Check → Run workflow
# Or via CLI:
gh workflow run version-check.yaml
```

Expected: workflow runs, reads `versions.yaml`, checks releases API, exits without opening a PR if already on latest.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/version-check.yaml
git commit -m "feat(repo): add Talos/K8s version check workflow"
```

---

## Chunk 3: Renovate Configuration

### Task 6: Renovate Configuration

Install Renovate as a GitHub App from [https://github.com/apps/renovate](https://github.com/apps/renovate) and grant it access to this repo. Renovate will read `renovate.json` on first run.

**Files:**
- Create: `renovate.json`

- [ ] **Step 1: Create renovate.json**

Create `renovate.json` at repo root:

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:base"],
  "schedule": ["every weekend"],
  "labels": ["renovate"],
  "prCreation": "not-pending",
  "customManagers": [
    {
      "customType": "regex",
      "description": "ArgoCD Application CR Helm chart versions",
      "fileMatch": ["apps/root/templates/.+\\.yaml"],
      "matchStrings": [
        "repoURL: (?<registryUrl>https://[^\\n]+)\\n      chart: (?<depName>[^\\n]+)\\n      targetRevision: \"(?<currentValue>[^\"]+)\""
      ],
      "datasourceTemplate": "helm"
    }
  ],
  "packageRules": [
    {
      "description": "Stateless apps — auto-merge on green smoke test",
      "matchFileNames": ["apps/root/templates/*.yaml"],
      "matchPackageNames": [
        "grafana",
        "hubble-ui",
        "gpu-switcher"
      ],
      "automerge": true,
      "automergeType": "pr",
      "automergeStrategy": "squash"
    },
    {
      "description": "Stateful apps — manual review required",
      "matchFileNames": ["apps/root/templates/*.yaml"],
      "matchPackageNames": [
        "authentik",
        "infisical",
        "paperclip",
        "postgresql",
        "redis"
      ],
      "automerge": false
    },
    {
      "description": "Core infra — manual only, skip smoke test",
      "matchFileNames": ["apps/root/templates/*.yaml"],
      "matchPackageNames": [
        "cilium",
        "argo-cd",
        "cert-manager",
        "gpu-operator",
        "longhorn",
        "external-secrets",
        "fluent-bit",
        "victoria-metrics-k8s-stack",
        "victoria-logs-single"
      ],
      "automerge": false,
      "labels": ["renovate", "no-smoke-test"]
    },
    {
      "description": "ARC charts — manual only, skip smoke test",
      "matchPackageNames": [
        "gha-runner-scale-set-controller",
        "gha-runner-scale-set"
      ],
      "automerge": false,
      "labels": ["renovate", "no-smoke-test"]
    }
  ]
}
```

- [ ] **Step 2: Validate the regex against a real template**

```bash
# Install yq and test the regex extracts correctly from cert-manager.yaml
python3 -c "
import re
with open('apps/root/templates/cert-manager.yaml') as f:
    content = f.read()
pattern = r'repoURL: (?P<registryUrl>https://[^\n]+)\n      chart: (?P<depName>[^\n]+)\n      targetRevision: \"(?P<currentValue>[^\"]+)\"'
m = re.search(pattern, content)
if m:
    print('Match found:', m.groupdict())
else:
    print('NO MATCH — check indentation in regex')
"
```

Expected output: `Match found: {'registryUrl': 'https://charts.jetstack.io', 'depName': 'cert-manager', 'currentValue': '1.17.1'}`

If no match, inspect the actual indentation with:
```bash
cat -A apps/root/templates/cert-manager.yaml | head -20
```

- [ ] **Step 3: Commit**

```bash
git add renovate.json
git commit -m "feat(repo): add Renovate config for automated chart version PRs"
```

---

### Task 7: GitHub Branch Protection (Manual Operation)

```yaml
# manual-operation
id: github-branch-protection-smoke-test
layer: repo
app: renovate
plan: docs/superpowers/plans/2026-03-25--repo--safe-update-automation.md
when: "After smoke-test.yaml workflow exists on main branch and has run at least once successfully"
why_manual: "Branch protection rules must be configured via GitHub UI or API. The smoke-test/readiness check must be a required status check so Renovate's automerge only fires after tests pass."
commands:
  - |
    # Via GitHub CLI — sets branch protection on main requiring smoke-test/readiness
    gh api repos/:owner/:repo/branches/main/protection \
      --method PUT \
      --field required_status_checks='{"strict":false,"checks":[{"context":"smoke-test/readiness"}]}' \
      --field enforce_admins=false \
      --field required_pull_request_reviews=null \
      --field restrictions=null
verify:
  - gh api repos/:owner/:repo/branches/main/protection --jq '.required_status_checks.checks'
  # Expected: [{"context":"smoke-test/readiness","app_id":null}]
status: pending
```

- [ ] **Step 1: Apply branch protection after smoke-test workflow is live**

Run the `gh api` command above (after Task 8 is complete and the workflow has run). Replace `:owner/:repo` with your actual values.

---

## Chunk 4: Smoke Test Workflow

### Task 8: Smoke Test GitHub Actions Workflow

This is the pre-merge gate. It triggers on PRs that change Application CR templates, skips CRD-heavy apps, installs the chart into an ephemeral namespace, and reports readiness.

**Files:**
- Create: `.github/workflows/smoke-test.yaml`

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/smoke-test.yaml`:

```yaml
name: Smoke Test

on:
  pull_request:
    branches: [main]
    paths:
      - "apps/root/templates/*.yaml"

permissions:
  contents: read
  pull-requests: write
  statuses: write

concurrency:
  group: smoke-test-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  smoke-test:
    runs-on: [self-hosted, frank-cluster]
    steps:
      - name: Checkout PR branch
        uses: actions/checkout@v4

      - name: Skip if no-smoke-test label
        id: check_label
        run: |
          LABELS='${{ toJson(github.event.pull_request.labels.*.name) }}'
          if echo "$LABELS" | grep -q "no-smoke-test"; then
            echo "skip=true" >> $GITHUB_OUTPUT
            echo "Skipping smoke test — no-smoke-test label present"
          else
            echo "skip=false" >> $GITHUB_OUTPUT
          fi

      - name: Install yq
        if: steps.check_label.outputs.skip == 'false'
        run: |
          if ! command -v yq &>/dev/null; then
            wget -qO /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64
            chmod +x /usr/local/bin/yq
          fi

      - name: Get changed template files
        if: steps.check_label.outputs.skip == 'false'
        id: changed
        run: |
          # Find .yaml files in apps/root/templates/ changed in this PR
          FILES=$(git diff --name-only origin/main...HEAD -- 'apps/root/templates/*.yaml' | tr '\n' ' ')
          echo "files=$FILES" >> $GITHUB_OUTPUT
          echo "Changed template files: $FILES"

      - name: Extract chart info from changed files
        if: steps.check_label.outputs.skip == 'false'
        id: charts
        run: |
          # Use yq to extract from the helm source entry (the one with chart: set).
          # repoURL comes BEFORE chart: in the template, so grep-based approaches
          # that search after chart: fail. yq handles this correctly.
          CHARTS_JSON="[]"
          for FILE in ${{ steps.changed.outputs.files }}; do
            # Skip files with no helm chart source (raw manifests, Git-sourced charts, ref-only)
            if ! yq '.spec.sources[] | select(.chart != null)' "$FILE" 2>/dev/null | grep -q "chart:"; then
              echo "Skipping $FILE — no helm chart source"
              continue
            fi
            APP=$(basename "$FILE" .yaml)
            REGISTRY=$(yq '.spec.sources[] | select(.chart != null) | .repoURL' "$FILE" | head -1)
            CHART=$(yq '.spec.sources[] | select(.chart != null) | .chart' "$FILE" | head -1)
            VERSION=$(yq '.spec.sources[] | select(.chart != null) | .targetRevision' "$FILE" | head -1)
            CHARTS_JSON=$(echo "$CHARTS_JSON" | jq --arg app "$APP" --arg reg "$REGISTRY" --arg chart "$CHART" --arg ver "$VERSION" \
              '. += [{"app": $app, "registry": $reg, "chart": $chart, "version": $ver}]')
          done
          echo "charts=$CHARTS_JSON" >> $GITHUB_OUTPUT

      - name: Run smoke tests
        if: steps.check_label.outputs.skip == 'false'
        id: smoke
        run: |
          # Label selector lookup table — maps app name to pod label selector
          declare -A SELECTORS
          SELECTORS[grafana]="app.kubernetes.io/name=grafana"
          SELECTORS[victoria-metrics]="app.kubernetes.io/name=victoria-metrics-k8s-stack"
          SELECTORS[longhorn]="app=longhorn-manager"
          SELECTORS[cert-manager]="app=cert-manager"
          SELECTORS[cilium]="k8s-app=cilium"
          SELECTORS[fluent-bit]="app.kubernetes.io/name=fluent-bit"
          SELECTORS[ollama]="app.kubernetes.io/name=ollama"
          SELECTORS[litellm]="app.kubernetes.io/name=litellm"

          PR_NUM="${{ github.event.pull_request.number }}"
          FAILED=false
          RESULTS=""

          for CHART_JSON in $(echo '${{ steps.charts.outputs.charts }}' | jq -c '.[]'); do
            APP=$(echo "$CHART_JSON" | jq -r '.app')
            REGISTRY=$(echo "$CHART_JSON" | jq -r '.registry')
            CHART=$(echo "$CHART_JSON" | jq -r '.chart')
            VERSION=$(echo "$CHART_JSON" | jq -r '.version')
            NS="smoke-test-${PR_NUM}-${APP}"

            echo "=== Smoke testing $APP $VERSION ==="

            # Get label selector (fall back to app=<name>)
            SELECTOR="${SELECTORS[$APP]:-app=$APP}"

            # Add helm repo
            helm repo add "${APP}-repo" "$REGISTRY" 2>/dev/null || true
            helm repo update "${APP}-repo" 2>/dev/null || true

            # Create namespace
            kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

            # Build helm install args
            HELM_ARGS="-f apps/${APP}/values.yaml"
            if [ -f "apps/${APP}/smoke-test-values.yaml" ]; then
              HELM_ARGS="$HELM_ARGS -f apps/${APP}/smoke-test-values.yaml"
            fi

            # Install chart
            if helm install "$APP" "${APP}-repo/$CHART" \
                --version "$VERSION" \
                --namespace "$NS" \
                $HELM_ARGS \
                --timeout 30s \
                --wait=false 2>&1; then

              # Wait for pod readiness
              if kubectl wait --for=condition=Ready pod \
                  -l "$SELECTOR" \
                  -n "$NS" \
                  --timeout=120s 2>&1; then
                echo "✅ $APP $VERSION — PASSED"
                RESULTS+="✅ **$APP** \`$VERSION\` — pod ready\n"
              else
                echo "❌ $APP $VERSION — pod not ready"
                RESULTS+="❌ **$APP** \`$VERSION\` — pod readiness timeout\n"
                # Capture diagnostics
                kubectl describe pods -l "$SELECTOR" -n "$NS" >> /tmp/diag-${APP}.txt 2>&1 || true
                kubectl get events -n "$NS" --sort-by='.lastTimestamp' >> /tmp/diag-${APP}.txt 2>&1 || true
                FAILED=true
              fi
            else
              echo "❌ $APP $VERSION — helm install failed"
              RESULTS+="❌ **$APP** \`$VERSION\` — helm install failed\n"
              FAILED=true
            fi

            # Cleanup namespace
            kubectl delete namespace "$NS" --ignore-not-found --wait=false || true
          done

          echo "results=$RESULTS" >> $GITHUB_OUTPUT
          if [ "$FAILED" = "true" ]; then
            exit 1
          fi

      - name: Post results comment
        if: always() && steps.check_label.outputs.skip == 'false'
        uses: actions/github-script@v7
        with:
          script: |
            const results = `${{ steps.smoke.outputs.results }}`;
            const status = '${{ steps.smoke.outcome }}' === 'success' ? '✅ Smoke test passed' : '❌ Smoke test failed';
            const body = `## ${status}\n\n${results || 'No charts to test.'}\n\n<details><summary>Diagnostics</summary>\n\nCheck the workflow run for full logs.\n</details>`;
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body
            });

      - name: Set commit status
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const state = '${{ steps.check_label.outputs.skip }}' === 'true' ? 'success' :
                          '${{ steps.smoke.outcome }}' === 'success' ? 'success' : 'failure';
            const description = '${{ steps.check_label.outputs.skip }}' === 'true' ? 'Skipped (no-smoke-test)' :
                                 state === 'success' ? 'All pods ready' : 'Pod readiness check failed';
            github.rest.repos.createCommitStatus({
              owner: context.repo.owner,
              repo: context.repo.repo,
              sha: context.payload.pull_request.head.sha,
              state,
              context: 'smoke-test/readiness',
              description
            });
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/smoke-test.yaml
git commit -m "feat(repo): add Helm smoke test workflow for Renovate PRs"
```

- [ ] **Step 3: Push and trigger a test run**

```bash
git push
```

Create a test PR that bumps a chart version manually (e.g., increment `cert-manager` version by one patch in `apps/root/templates/cert-manager.yaml`) to verify the smoke test workflow fires. Since cert-manager is in the `no-smoke-test` list, the workflow should report "Skipped" rather than attempting a Helm install.

Then test with a stateless app: create a PR bumping a grafana version to confirm full pipeline runs.

- [ ] **Step 4: Apply branch protection (Task 7)**

Once the workflow has run at least once successfully and `smoke-test/readiness` appears in GitHub's known status check list, run the branch protection command from Task 7.

---

## Chunk 5: Wire Up and Verify End-to-End

### Task 9: Verify Renovate Onboarding

- [ ] **Step 1: Confirm Renovate GitHub App is installed**

Go to your GitHub repo → Settings → GitHub Apps. Confirm Renovate is installed with access to this repo.

- [ ] **Step 2: Trigger Renovate onboarding**

Renovate will open an onboarding PR called "Configure Renovate" on first run if it detects no `renovate.json`. Since you already committed `renovate.json`, it will skip onboarding and go straight to dependency scanning. Trigger a run from [Renovate's dashboard](https://developer.mend.io) or wait for the scheduled weekend run.

- [ ] **Step 3: Verify Renovate finds chart versions**

After first run, check if Renovate opens PRs for any outdated chart versions. Confirm the regex manager is matching correctly — if no PRs appear but charts are outdated, the regex likely has an indentation mismatch (re-run the python3 test from Task 6 Step 2).

- [ ] **Step 4: Verify auto-merge fires on green for stateless app**

Wait for a Renovate PR on a stateless app (or create one manually). Confirm: smoke test runs → passes → Renovate auto-merges. If auto-merge doesn't fire, check that branch protection requires `smoke-test/readiness` and that the check status is `success` not just `skipped`.

---

## Deployment Deviations

_Record any deviations from the plan here as they occur._

---

## Notes

- **ARC ServiceAccount name:** ARC v2 names the runner ServiceAccount `<release-name>-gha-rs-no-permission`. If the release name in `values.yaml` differs from `frank-cluster`, update the RBAC manifest subject name accordingly.
- **OCI chart registry auth:** `oci://ghcr.io/actions/...` is public — no Helm registry credentials needed.
- **Renovate packageNames:** The `matchPackageNames` in `renovate.json` must match the `chart:` field values exactly as they appear in the Application CRs. Verify these match after Renovate's first scan.
- **yq version:** The runner image may not have `yq` pre-installed. The version-check workflow installs it on first run; the smoke-test workflow uses only `grep`/`awk`/`jq` which are typically pre-installed in the ARC runner image.
