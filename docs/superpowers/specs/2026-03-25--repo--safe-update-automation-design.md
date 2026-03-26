# Safe Update Automation — Design

**Date:** 2026-03-25
**Layer:** `repo` (CI/CD tooling — touches `gitops`, `os`, `tenant`)
**Scope:** Automate version update detection and pre-merge smoke testing across all three update planes: ArgoCD Helm charts, Talos OS, and Kubernetes (via Omni).

---

## Problem Statement

The cluster has no systematic process for staying current with upstream versions. Updates happen ad-hoc — manually noticed, manually tested, manually applied. This creates two risks:

1. **Drift accumulation** — charts and OS versions fall behind, making eventual updates larger and riskier.
2. **No pre-merge validation** — a chart version bump that breaks a pod only surfaces after ArgoCD syncs to production.

---

## Goals

- Detect new upstream versions automatically across all three planes.
- Open PRs with version bumps so updates are reviewed and tracked in git.
- Run a lightweight smoke test (pod readiness) against a staging namespace before any ArgoCD chart update is merged.
- Keep Omni/Talos upgrades human-approved but automated in detection and PR creation.
- Remain compatible with a planned future Argo Rollouts deployment (canary analysis will complement, not replace, this pre-merge gate).

---

## Architecture

Three pipelines, scoped to their update frequency and risk level:

```text
ArgoCD layer (weekly+)
  Renovate ──► PR (targetRevision bump)
            ──► GitHub Actions: namespace smoke test (self-hosted runner, pc-1)
            ──► auto-merge on green (stateless only) or manual review (stateful/core)

Omni/Talos layer (monthly)
  GH Actions cron (weekly) ──► omnictl + GitHub releases API
                            ──► PR updating versions.yaml (if new stable exists)
                            ──► Omni applies upgrade (human-triggered or scheduled)
```

---

## Component Design

### 1. Self-Hosted GitHub Actions Runner (ARC)

A lightweight `actions-runner-controller` (ARC) Deployment pinned to `pc-1` via `nodeSelector: kubernetes.io/hostname: pc-1`. This gives GitHub Actions direct in-cluster `kubectl` access without any network tunneling. Headscale and the subnet router are not in the CI critical path.

- **Location:** `apps/arc/` — new ArgoCD app. Uses the current ARC v2 architecture: two charts installed in sequence — `gha-runner-scale-set-controller` (controller) and `gha-runner-scale-set` (runner set). Do NOT use the legacy `actions-runner-controller` chart (v1, unmaintained).
- **Node binding:** `nodeSelector: kubernetes.io/hostname: pc-1` (label is automatically set by Kubernetes; no Talos patch required)
- **Runner group:** `self-hosted`, labelled `frank-cluster`

**ServiceAccount RBAC** — the runner's ServiceAccount grants:

| Scope                               | Resource                                              | Verbs                             |
|-------------------------------------|-------------------------------------------------------|-----------------------------------|
| Cluster-scoped                      | `namespaces` matching `smoke-test-*`                  | `create`, `delete`, `get`, `list` |
| Namespaced (within `smoke-test-*`)  | all (`apiGroups: ["*"]`, `resources: ["*"]`)          | `*`                               |

Cluster-scoped resources outside namespace management (ClusterRoles, ClusterRoleBindings, CRDs, nodes, PVs) are not granted. The runner cannot access or modify production namespaces.

**ArgoCD Application CR:** The ARC Application CR must include `ignoreDifferences` on the runner registration Secrets that ARC writes ephemerally (runner tokens are rotated continuously and ArgoCD will otherwise show the app as perpetually OutOfSync). Apply `ignoreDifferences` with `jsonPointers: ["/data"]` on Secrets in the `arc-system` namespace — consistent with the repo-wide pattern for Secret data diffs.

**Bootstrap secret:** ARC requires a GitHub App credentials Secret (`arc-github-app-secret`) before the runner pod can register with GitHub. This cannot be declarative — it must be applied out-of-band as a SOPS-encrypted secret. See manual operation below.

```yaml
# manual-operation
id: arc-github-app-secret
layer: repo
app: arc
plan: docs/superpowers/plans/2026-03-25--repo--safe-update-automation.md
when: "After ARC app is synced by ArgoCD, before runner pod starts"
why_manual: "GitHub App credentials are a bootstrap secret — ARC must exist to manage itself, and the secret must exist before the runner can register. SOPS-encrypted per repo convention."
commands:
  - sops --decrypt secrets/arc/github-app-secret.yaml | kubectl apply -f -
verify:
  - kubectl get secret arc-github-app-secret -n arc-system
  - kubectl get pods -n arc-system  # runner pod should reach Running state
status: pending
```

### 2. Renovate

Runs as a GitHub App (cloud-hosted, free tier). Configured via `renovate.json` at repo root. Scans weekly; opens PRs bumping `targetRevision` in Application CR templates.

**Regex manager** — the Application CRs use a multi-source pattern where `chart:` and `targetRevision:` appear at the same indentation level within a `sources` entry (verified against existing templates, e.g. `apps/root/templates/cert-manager.yaml`):

```yaml
sources:
  - repoURL: https://charts.jetstack.io
    chart: cert-manager
    targetRevision: "1.17.1"
```

The Renovate custom regex manager:

```json
{
  "customManagers": [{
    "customType": "regex",
    "fileMatch": ["apps/root/templates/.+\\.yaml"],
    "matchStrings": [
      "repoURL: (?<registryUrl>https://[^\\n]+)\\n      chart: (?<depName>[^\\n]+)\\n      targetRevision: \"(?<currentValue>[^\"]+)\""
    ],
    "datasourceTemplate": "helm"
  }]
}
```

Note: indentation in `matchStrings` is 6 spaces before both `chart:` and `targetRevision:` — they sit at the same level as `repoURL:` within the list item (verified against `apps/root/templates/cert-manager.yaml`). Git-sourced charts (e.g. Sympozium, which uses `path:` instead of `chart:`) produce no `chart:` field and are implicitly excluded — Renovate will not open PRs for them, and they are also excluded from the smoke test for the same reason.

**Auto-merge policy** (configured via `packageRules`):

| Tier | Examples | Policy | Smoke test |
|------|----------|--------|------------|
| Stateless | Grafana, Hubble UI, GPU Switcher | `automerge: true` | Required — blocks merge |
| Stateful (DB) | Authentik, Infisical, Paperclip | `automerge: false` | Runs — informational only |
| Core infra | Cilium, ArgoCD, cert-manager, GPU operator | `automerge: false` + label `no-smoke-test` | Skipped |

Core infra apps are excluded from the smoke test because they install CRDs and require cluster-scoped resources that cannot be satisfied in an isolated namespace. The `no-smoke-test` label is set by Renovate's `packageRules` for these apps; the smoke test workflow skips if the label is present.

**Branch protection requirement:** The `smoke-test/readiness` GitHub status check must be registered as a required status check in branch protection rules. This ensures Renovate's auto-merge for stateless apps only fires after the smoke test passes — not before it runs. For apps with `no-smoke-test`, Renovate auto-merge is `false` so the required check is irrelevant.

**Merge method:** squash merge (configured in `renovate.json` as `"automergeType": "pr"`, `"automergeStrategy": "squash"`).

**Future evolution:** Once Argo Rollouts is deployed with canary analysis, stateful apps can be promoted to `automerge: true` — the namespace smoke test becomes the pre-merge filter and Rollouts provides the post-merge safety net on production traffic.

### 3. Smoke Test (GitHub Actions Workflow)

Triggered on every Renovate PR via `pull_request` event (filter: `paths: ["apps/root/templates/*.yaml"]`). Runs on the self-hosted runner (`runs-on: [self-hosted, frank-cluster]`). Skips if the PR has the `no-smoke-test` label.

**Mechanism:** Direct Helm install into an ephemeral namespace `smoke-test-<pr-number>`. No vCluster — namespace isolation is sufficient for pod readiness checks, and vCluster overhead is unnecessary for this use case.

**Workflow steps:**

1. Checkout the PR branch
2. Skip if `no-smoke-test` label is present (exit 0, report skipped status)
3. Extract app name, chart repo URL, and new `targetRevision` from the changed template file using `yq`. The chart source entry in Application CR templates is a static YAML block (Go template variables only appear in the `ref: values` source, not the helm source) — `yq` can parse it directly: `yq '.spec.sources[] | select(.chart != null) | {name: .chart, repo: .repoURL, version: .targetRevision}' <file>`. If multiple template files changed in one PR (Renovate batch), the workflow runs a smoke test for each changed file sequentially.
4. Create namespace: `kubectl create namespace smoke-test-<pr-number>`
5. `helm install <app> <chart-repo>/<chart-name> --version <new-version> -n smoke-test-<pr-number> -f apps/<app>/values.yaml`. If `apps/<app>/smoke-test-values.yaml` exists, append it as an additional `-f` override (used to stub cluster-internal endpoints such as OIDC issuer URLs or LoadBalancer IPs that prevent pod startup in an isolated namespace).
6. `kubectl wait --for=condition=Ready pod -l <app-label-selector> -n smoke-test-<pr-number> --timeout=120s`
7. On timeout/failure: capture `kubectl describe pod` and `kubectl events` output; post as PR comment
8. `kubectl delete namespace smoke-test-<pr-number>` (always runs — in `finally` block)
9. Report pass/fail as GitHub status check `smoke-test/readiness`

**Per-app label selectors** are defined in a lookup table in the workflow YAML (e.g., `grafana: "app.kubernetes.io/name=grafana"`). Apps not in the table use `app=<app-name>` as a fallback.

**Timeout:** 120s. Sufficient for lightweight apps. Apps with known-slow init containers (e.g., DB migration jobs) can have an extended timeout configured in the lookup table.

### 4. Version Tracking File

`versions.yaml` at repo root — declarative record of the target Talos and Kubernetes versions for the Frank cluster:

```yaml
# versions.yaml
# Declarative record of target cluster versions.
# Updated by the version-check workflow when new stable patch releases are available.
# K8s minor version is pinned here and updated manually when Omni supports a new minor.
# Omni applies the actual upgrade; this file is the audit trail and PR review trigger.
talos: v1.9.x
kubernetes:
  minor: "1.32"   # pinned minor — only patch bumps are automated
  patch: v1.32.x  # full version, updated by version-check workflow
```

The K8s minor version (`kubernetes.minor`) is pinned and updated manually. The version-check workflow only bumps patch versions within the pinned minor. When Omni begins supporting a new K8s minor, the minor is updated manually in `versions.yaml` as part of that upgrade PR.

### 5. Omni/Talos Version Check (GitHub Actions Workflow)

Scheduled weekly cron (`0 9 * * 1` — Monday 09:00 UTC). Runs on the self-hosted runner.

**Workflow steps:**

1. Read `versions.yaml` — extract current `talos` and `kubernetes.minor` + `kubernetes.patch`
2. Query latest stable Talos patch: GitHub releases API (`siderolabs/talos`), filter `prerelease: false`, select latest matching `v<major>.<minor>.*` within the same minor as current
3. Query latest stable Kubernetes patch: GitHub releases API (`kubernetes/kubernetes`), filter `prerelease: false`, select latest matching `v<pinned-minor>.*`
4. If either is newer than current: open a PR updating `versions.yaml` with the new version(s)
5. PR description includes:
   - GitHub release URL for each updated component
   - `omnictl` command to run after merge to trigger the Omni upgrade
   - Checklist: review release notes, check for breaking changes, verify Omni compatibility

---

## File Layout

```text
apps/arc/
  values.yaml                    # ARC Helm values (nodeSelector, RBAC, runner config)
apps/root/templates/
  arc.yaml                       # ArgoCD Application CR for ARC
secrets/arc/
  github-app-secret.yaml         # SOPS-encrypted GitHub App credentials (applied out-of-band)
renovate.json                    # Renovate config (regex manager, packageRules, schedule)
versions.yaml                    # Declarative Talos + K8s version targets
.github/workflows/
  smoke-test.yaml                # Helm smoke test triggered on Renovate PRs
  version-check.yaml             # Omni/Talos version detection (weekly cron)
```

---

## Security Considerations

- **Runner RBAC:** Scoped to `smoke-test-*` namespace lifecycle and workloads only. Cannot access production namespaces, cluster-wide secrets, or CRD management.
- **No external secrets in CI:** The runner uses its in-cluster ServiceAccount token — no kubeconfig secrets stored in GitHub. Access is by virtue of running inside the cluster.
- **Renovate token:** GitHub App requires read access to repo contents and write access to PRs/branches. No cluster access.
- **Version check workflow:** Read-only — opens PRs only, never touches the cluster.
- **ARC credentials:** SOPS-encrypted per repo convention; applied out-of-band before ArgoCD syncs the runner deployment.

---

## Out of Scope

- Argo Rollouts deployment (separate future layer)
- Functional or integration smoke tests (future evolution once shallow tests are stable)
- Automatic Omni upgrade triggering (Omni handles this; automation stops at PR creation)
- Hop cluster updates (standalone talosctl workflow; separate concern)
- Image tag updates for non-Helm workloads (e.g., blog container)
- Apps using raw manifests only (`source.path` without a Helm chart) — no `chart:` field for Renovate to match; these are excluded by the regex manager automatically

---

## Compatibility Notes

- The smoke test is a **pre-merge gate only**. Once Argo Rollouts is deployed, canary analysis provides a **post-merge gate** for stateful apps. The two layers are complementary and do not conflict.
- `versions.yaml` is git-tracked but not consumed programmatically by Omni. Omni remains the authoritative source of cluster state; this file provides the human-reviewable audit trail.
