# Argo Rollouts — Progressive Delivery Platform

## Phase 1: Controller Install

### Task 1: Register layer and create values file

- P1.T1.S1: Add layer 18 to docs/layers.yaml

- P1.T1.S2: Create apps/argo-rollouts/values.yaml

- P1.T1.S3: Commit

### Task 2: ArgoCD Application CRs

- P1.T2.S1: Find the latest chart version

- P1.T2.S2: Create apps/root/templates/argo-rollouts.yaml

- P1.T2.S3: Create apps/root/templates/argo-rollouts-extras.yaml

- P1.T2.S4: Commit

### Task 3: Cilium plugin ConfigMap and RBAC

- P1.T3.S1: Find the latest Cilium plugin release

- P1.T3.S2: Create plugin-config.yaml

- P1.T3.S3: Create cilium-rbac.yaml

- P1.T3.S4: Commit

### Task 4: Verify Cilium Envoy is enabled

- P1.T4.S1: Check if Cilium Envoy DaemonSet is running

- P1.T4.S2: Check current Cilium values

- P1.T4.S3: Enable Envoy if not present

- P1.T4.S4: Verify CiliumEnvoyConfig CRD exists

### Task 5: Deploy Phase 1 and verify

- P1.T5.S1: Push and sync

- P1.T5.S2: Verify controller is running

- P1.T5.S3: Verify Cilium plugin loaded

- P1.T5.S4: Verify CiliumEnvoyConfig RBAC

- P1.T5.S5: Install kubectl-argo-rollouts CLI plugin locally (manual operation)

## Phase 2: LiteLLM Canary

### Task 6: Pin image tag and fix ArgoCD ignoreDifferences

- P2.T6.S1: Find the current LiteLLM stable release

- P2.T6.S2: Pin image tag in apps/litellm/values.yaml

- P2.T6.S3: Add ignoreDifferences for Deployment spec.replicas

- P2.T6.S4: Commit

### Task 7: Discover service names and VictoriaMetrics URL

- P2.T7.S1: Find the LiteLLM stable service name

- P2.T7.S2: Find LiteLLM pod labels

- P2.T7.S3: Find the VictoriaMetrics service URL

- P2.T7.S4: Verify LiteLLM exposes metrics

### Task 8: LiteLLM canary service and analysis template

- P2.T8.S1: Create service-canary.yaml

- P2.T8.S2: Create analysis-template.yaml

- P2.T8.S3: Commit

### Task 9: LiteLLM Rollout with workloadRef

- P2.T9.S1: Create rollout.yaml

- P2.T9.S2: Commit

### Task 10: Deploy and verify Phase 2

- P2.T10.S1: Push and sync

- P2.T10.S2: Verify Deployment is at 0 and Rollout is healthy

- P2.T10.S3: Verify LiteLLM is still accessible

- P2.T10.S4: Trigger a test canary

- P2.T10.S5: Commit any fixes

## Phase 3: Paperclip Rollout (Recreate)

### Task 11: Manual Deployment deletion (prerequisite)

- P3.T11.S1: Scale Deployment to 0 first (avoids traffic gap) *(skipped — Phase 3 reverted, RWO PVC incompatible with Argo Rollouts)*

- P3.T11.S2: Delete the Deployment object *(skipped — Phase 3 reverted)*

### Task 12: Paperclip Rollout (Recreate strategy)

- P3.T12.S1: Create rollout.yaml from deployment.yaml spec *(skipped — Phase 3 reverted)*

- P3.T12.S2: Remove deployment.yaml and commit rollout.yaml *(skipped — Phase 3 reverted)*

### Task 13: Deploy and verify Phase 3

- P3.T13.S1: Push and sync *(skipped — Phase 3 reverted)*

- P3.T13.S2: Verify Rollout is healthy *(skipped — Phase 3 reverted)*

- P3.T13.S3: Verify Paperclip is accessible *(skipped — Phase 3 reverted)*

- P3.T13.S4: Test rollout and rollback *(skipped — Phase 3 reverted)*
