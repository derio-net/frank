# ArgoCD Infrastructure — Implementation Plan

## Phase 1: ArgoCD Infrastructure — Implementation Plan

### Task 1: Remove Flux CD

- P1.T1.S1: Delete Flux custom resources

- P1.T1.S2: Delete Flux controllers

- P1.T1.S3: Delete Flux namespace

- P1.T1.S4: Delete Flux CRDs

- P1.T1.S5: Verify Flux is completely gone

- P1.T1.S6: Commit

### Task 2: Remove Pulumi Artifacts and Deprecate Old Docs

- P1.T2.S1: Delete the Pulumi directory

- P1.T2.S2: Add deprecation header to old design doc

- P1.T2.S3: Add deprecation header to old plan doc

- P1.T2.S4: Clean up .gitignore — remove Pulumi-specific entries

- P1.T2.S5: Verify

- P1.T2.S6: Commit

### Task 3: Create apps/ Directory Structure and Move Helm Values

- P1.T3.S1: Create directory structure

- P1.T3.S2: Create Cilium values

- P1.T3.S3: Create Longhorn values

- P1.T3.S4: Create Longhorn GPU-local StorageClass manifest

- P1.T3.S5: Create GPU Operator values

- P1.T3.S6: Verify files exist

- P1.T3.S7: Commit

### Task 4: Create ArgoCD Helm Values

- P1.T4.S1: Create ArgoCD values

- P1.T4.S2: Commit

### Task 5: Create Root App-of-Apps Chart

- P1.T5.S1: Create Chart.yaml

- P1.T5.S2: Create values.yaml

- P1.T5.S3: Create AppProject template

- P1.T5.S4: Create Longhorn namespace template (with PSS labels)

- P1.T5.S5: Create GPU Operator namespace template (with PSS labels)

- P1.T5.S6: Verify chart renders

- P1.T5.S7: Commit

### Task 6: Create Cilium Application Template

- P1.T6.S1: Create Cilium Application template

- P1.T6.S2: Verify renders

- P1.T6.S3: Commit

### Task 7: Create Longhorn Application Templates

- P1.T7.S1: Create Longhorn Helm Application template

- P1.T7.S2: Create Longhorn extras Application template

- P1.T7.S3: Verify renders

- P1.T7.S4: Commit

### Task 8: Create GPU Operator Application Template

- P1.T8.S1: Create GPU Operator Application template

- P1.T8.S2: Verify renders

- P1.T8.S3: Commit

### Task 9: Install ArgoCD via Helm

- P1.T9.S1: Create ArgoCD namespace

- P1.T9.S2: Add Argo Helm repo

- P1.T9.S3: Check latest ArgoCD chart version

- P1.T9.S4: Install ArgoCD

- P1.T9.S5: Wait for ArgoCD to be ready

- P1.T9.S6: Verify all ArgoCD pods are running

- P1.T9.S7: Get initial admin password

- P1.T9.S8: Test ArgoCD CLI login

- P1.T9.S9: Commit (no file changes — just noting state)

### Task 10: Configure ArgoCD Repository Access

- P1.T10.S1: Add the git repository to ArgoCD

- P1.T10.S2: Verify repo is connected

### Task 11: Push Config to Remote and Apply Root Application

- P1.T11.S1: Push all commits to remote

- P1.T11.S2: Apply the root Application

- P1.T11.S3: Wait for root app to sync

- P1.T11.S4: Verify all applications exist

### Task 12: Sync and Verify Cilium Adoption

- P1.T12.S1: Check the diff before syncing

- P1.T12.S2: Sync Cilium

- P1.T12.S3: Verify Cilium is still healthy

- P1.T12.S4: Verify ArgoCD shows Cilium as Synced + Healthy

### Task 13: Sync and Verify Longhorn Adoption

- P1.T13.S1: Check the diff before syncing

- P1.T13.S2: Sync Longhorn

- P1.T13.S3: Sync Longhorn extras (GPU-local StorageClass)

- P1.T13.S4: Verify Longhorn is still healthy

- P1.T13.S5: Verify with a test PVC

- P1.T13.S6: Verify ArgoCD shows Longhorn as Synced + Healthy

### Task 14: GPU Operator (Deferred — Manual Sync When Ready)

- P1.T14.S1: Verify GPU is on PCIe bus

- P1.T14.S2: Sync GPU Operator

- P1.T14.S3: Wait for GPU Operator pods

- P1.T14.S4: Verify GPU is allocatable

- P1.T14.S5: Run nvidia-smi test

- P1.T14.S6: Enable automated sync

### Task 15: Full Cluster Verification

- P1.T15.S1: ArgoCD dashboard — all apps healthy

- P1.T15.S2: All nodes Ready

- P1.T15.S3: Cilium healthy

- P1.T15.S4: Storage healthy

- P1.T15.S5: No Flux remnants

- P1.T15.S6: No Pulumi remnants

- P1.T15.S7: Update patches/README.md with ArgoCD status

- P1.T15.S8: Final commit
