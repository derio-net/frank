# ArgoCD Drift Cleanup Implementation Plan

## Phase 0: Baseline & tooling

### Task 1: Capture baseline

- P0.T1.S1: Snapshot OutOfSync state

- P0.T1.S2: Confirm argocd CLI access

## Phase 1: Zero-risk quick wins

### Task 1: Remove duplicate namespace ownership (class E)

- P1.T1.S1: Locate the duplicate Namespace manifest

- P1.T1.S2: Remove the Namespace doc from sympozium-extras

- P1.T1.S3: Apply the pod-security labels out-of-band (manual-op)

- P1.T1.S4: Commit and verify

### Task 2: Delete terminal Job and PipelineRun (class F)

- P1.T2.S1: Re-verify terminal state

- P1.T2.S2: Dump for rollback

- P1.T2.S3: Delete

- P1.T2.S4: Verify ad-hoc entries are gone from app status

### Task 3: Remove `prune: false` from Application templates (class B)

- P1.T3.S1: Confirm no explicit `prune: true` overrides

- P1.T3.S2: Bulk edit

- P1.T3.S3: Sanity-check one render

- P1.T3.S4: Commit and verify

## Phase 2: ExternalSecret default injection (class A)

### Task 1: Add schema-default fields to all 16 ES manifests

- P2.T1.S1: Apply transformation to each manifest

- P2.T1.S2: Spot-check with kubectl diff

- P2.T1.S3: Commit and verify

## Phase 3: CRD adoption (class C)

### Task 1: Adopt argo-rollouts CRDs

- P3.T1.S1: Verify helm resource-policy is present (keeps CRDs safe on app deletion)

- P3.T1.S2: Annotate

- P3.T1.S3: Sync + verify

### Task 2: Adopt Tekton pipelines CRDs

- P3.T2.S1: Annotate + sync

### Task 3: Adopt Tekton Dashboard CRD

- P3.T3.S1: Annotate + sync

## Phase 4: Subchart orphan cleanup (class D)

### Task 1: Gitea redis-cluster orphans

- P4.T1.S1: Dump orphans for rollback

- P4.T1.S2: Confirm services have no endpoints

- P4.T1.S3: Delete with gitea pod health monitoring

- P4.T1.S4: Verify

### Task 2: Infisical orphans (nginx + mongodb + redis configs)

- P4.T2.S1: Verify only expected pods run

- P4.T2.S2: Critical check — no Ingress uses the `nginx` ingressclass

- P4.T2.S3: Dump all for rollback

- P4.T2.S4: Delete in dependency-safe order

- P4.T2.S5: Verify

## Phase 5: Controller/render drift investigation (class G)

### Task 1: victoria-metrics (grafana Deploy + CM + VMRule + VMServiceScrape)

- P5.T1.S1: Capture per-resource diff

- P5.T1.S2: Apply narrowest fix

- P5.T1.S3: Sync + verify

### Task 2: gpu-operator ClusterPolicy

- P5.T2.S1: Diff and classify

- P5.T2.S2: Apply fix and verify

### Task 3: vcluster-experiments StatefulSet

- P5.T3.S1: Diff

- P5.T3.S2: Apply fix and verify `Synced/Healthy`.

### Task 4: infisical-postgresql PDB

- P5.T4.S1: Diff

- P5.T4.S2: Apply fix and verify `Synced/Healthy`.

## Phase 6: Verification & post-mortem

### Task 1: Compare final state to baseline

- P6.T1.S1: Capture final snapshot

- P6.T1.S2: Check residuals

- P6.T1.S3: Verify Progressing apps reached Healthy

### Task 2: Document residuals

- P6.T2.S1: Capture remaining issues inline

## Phase 7: Operating blog post

### Task 1: Write operating post

- P7.T1.S1: Use /blog-post skill

- P7.T1.S2: Generate cover image

- P7.T1.S3: Update operating series index

- P7.T1.S1: Expose externally *(skipped — no new service, internal audit work)*

- P7.T1.S2: Building blog post *(skipped — fix/extension on gitops layer)*

- P7.T1.S3: Operating blog post — covered in Phase 7

- P7.T1.S4: Update README *(skipped — no service inventory changes)*

- P7.T1.S5: Sync runbook *(skipped — no manual-operation blocks in this plan)*

- P7.T1.S6: Update plan status — set `**Status:**` to `Complete`
