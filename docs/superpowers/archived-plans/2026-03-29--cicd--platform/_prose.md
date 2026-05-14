# CI/CD Platform Implementation Plan

## Phase 0: Infrastructure Prerequisites

### Task 1: StorageClass and Node Labels

- P0.T1.S1: Create the StorageClass manifest

- P0.T1.S2: Commit

- P0.T1.S3: Push and verify StorageClass syncs

- P0.T1.S4: Add role=cicd label to pc-1 via Omni

## Phase 1: Gitea Deployment

### Task 2: Gitea Deployment

- P1.T2.S1: Create Infisical secrets and Authentik OIDC provider

- P1.T2.S2: Research Gitea Helm chart

- P1.T2.S3: Create ExternalSecret

- P1.T2.S4: Create Helm values

- P1.T2.S5: Create ArgoCD Application CR for Helm chart

- P1.T2.S6: Create ArgoCD Application CR for extras (manifests)

- P1.T2.S7: Commit

- P1.T2.S8: Push and verify

- P1.T2.S9: Verify Authentik OIDC login

## Phase 2: Gitea Post-Deploy Configuration

### Task 3: Create tekton-bot service account

- P2.T3.S1: Retrieve admin token from Infisical

- P2.T3.S2: Create tekton-bot user via API

- P2.T3.S3: Generate API token for tekton-bot

- P2.T3.S4: Store tekton-bot token in Infisical

- P2.T3.S5: Verify tekton-bot can authenticate

### Task 4: Mirror test repo from GitHub

- P2.T4.S6: Create mirror via Gitea migration API

- P2.T4.S7: Verify mirror synced

### Task 5: Verify SSH clone

- P2.T5.S8: Clone via SSH and confirm

## Phase 3: Tekton Core & Triggers

### Task 4: Tekton Core Deployment

- P3.T4.S1: Download and vendor Tekton Pipelines release YAML

- P3.T4.S2: Download and vendor Tekton Dashboard release YAML

- P3.T4.S3: Create Dashboard LoadBalancer Service

- P3.T4.S4: Create ArgoCD Application for Tekton Pipelines

- P3.T4.S5: Create ArgoCD Application for Tekton Dashboard

- P3.T4.S6: Create ArgoCD Application for Tekton extras (manifests)

- P3.T4.S7: Commit

- P3.T4.S8: Push and verify

- P3.T4.S9: Run a manual hello-world PipelineRun

### Task 5: Tekton Triggers Deployment

- P3.T5.S1: Create Infisical webhook secret

- P3.T5.S2: Download and vendor Tekton Triggers release YAML

- P3.T5.S3: Create ExternalSecret for webhook secret

- P3.T5.S4: Create ExternalSecret for Gitea API token

- P3.T5.S5: Create TriggerBinding

- P3.T5.S6: Create TriggerTemplate

- P3.T5.S7: Create EventListener

- P3.T5.S8: Create RBAC for Tekton Triggers

- P3.T5.S9: Create ArgoCD Application for Tekton Triggers

- P3.T5.S10: Commit

- P3.T5.S11: Push and verify

- P3.T5.S12: Configure Gitea webhook

- P3.T5.S13: Test webhook triggers a PipelineRun

## Phase 4: Zot Registry

### Task 6: Zot Registry Deployment

- P4.T6.S1: Create Infisical secrets and Authentik OIDC provider

- P4.T6.S2: Research Zot Helm chart

- P4.T6.S3: Create self-signed ClusterIssuer (if not exists)

- P4.T6.S4: Create Certificate for Zot TLS

- P4.T6.S5: Create ExternalSecret

- P4.T6.S6: Create Helm values

- P4.T6.S7: Create ArgoCD Application CRs

- P4.T6.S8: Commit

- P4.T6.S9: Push and verify

- P4.T6.S10: Test image push/pull

- P4.T6.S11: Apply containerd mirror Talos patch

## Phase 5: CI Pipeline

### Task 7: Pipeline Stage A — Clone, Test, Report Status

- P5.T7.S1: Vendor git-clone Task from Tekton catalog

- P5.T7.S2: Create run-tests Task

- P5.T7.S3: Create gitea-status Task

- P5.T7.S4: Create the gitea-ci Pipeline

- P5.T7.S5: Commit

- P5.T7.S6: Push and verify end-to-end

- P5.T7.S7: Test the full webhook → pipeline → status flow

### Task 8: Pipeline Stage B — Build Image and Push to Zot

- P5.T8.S1: Create ExternalSecret for Zot push credentials

- P5.T8.S2: Create build-push Task

- P5.T8.S3: Extend the gitea-ci Pipeline with build-push

- P5.T8.S4: Commit

- P5.T8.S5: Push and verify

### Task 9: Pipeline Stage C — Cosign Image Signing

- P5.T9.S1: Generate cosign key pair and store in Infisical

- P5.T9.S2: Create ExternalSecret for cosign key

- P5.T9.S3: Create cosign-sign Task

- P5.T9.S4: Extend gitea-ci Pipeline with cosign-sign

- P5.T9.S5: Commit

- P5.T9.S6: Push and verify

## Phase 6: Post-Deploy Checklist

## Deployment Deviations

### 2026-05-14 — PipelineRun TTL CronJob added (`apps/tekton/manifests/pipelinerun-ttl-gc.yaml`)

Tekton doesn't TTL PipelineRuns natively. Their task pods stay around for log inspection (good for the first hour) but accumulate over weeks. Aside from being clutter, they triggered a false-positive Layer 25 alert on 2026-05-13 (see the corresponding deviation note in `2026-04-16--platform--derio-ops-pass3-grafana-wiring/_prose.md` of the same date for context).

New CronJob `pipelinerun-ttl-gc` in the `tekton-pipelines` namespace, daily at 04:30 UTC, deletes PipelineRuns whose `status.completionTime` is older than 7 days. ServiceAccount + Role limit blast radius to local-namespace `tekton.dev/pipelineruns: get/list/delete` only. Bash + kubectl image (`bitnami/kubectl:1.35.3`), no jq/python deps, lexical ISO-8601 comparison. Ad-hoc invocation:

```bash
kubectl create job -n tekton-pipelines --from=cronjob/pipelinerun-ttl-gc pipelinerun-ttl-gc-manual-$(date +%s)
```

Operating post `operating/22-cicd-platform`'s "Clean Up Old PipelineRuns" section updated to point at this CronJob as the canonical mechanism (the manual recipe stays as a backup).

### Task 10: Post-Deploy Checklist

- P6.T10.S1: Write building blog post — Use `/blog-post` skill. Cover the full CI/CD layer: Gitea, Tekton, Zot, cosign. Update series index in `blog/content/building/00-overview/index.md` and cluster roadmap in `blog/layouts/shortcodes/cluster-roadmap.html`

- P6.T10.S2: Write operating blog post — Use `/blog-post` skill for the companion operating guide (health checks, pipeline debugging, registry maintenance, cosign verification). Update operating series index in `blog/content/building/00-overview/index.md`

- P6.T10.S3: Update README — Run `/update-readme` to sync Technology Stack, Repository Structure, Service Access, and Current Status

- P6.T10.S4: Sync runbook — Run `/sync-runbook` (this plan has 11 manual-operation blocks)

- P6.T10.S5: Update plan status — Set `**Status:**` to `Deployed`
