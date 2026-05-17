# Safe Update Automation Implementation Plan

**Spec:** `docs/superpowers/specs/2026-03-25--repo--safe-update-automation-design.md`
**Status:** Not Started

## Phase 0: GitHub App Prerequisites

### Task 1: Install ARC GitHub App

- P0.T1.S1: Create and install the ARC GitHub App

### Task 2: Install Renovate GitHub App

- P0.T2.S1: Install Renovate and grant repo access

## Phase 1: ARC Self-Hosted Runner

### Task 1: ARC Controller ArgoCD App

- P1.T1.S1: Create controller values

- P1.T1.S2: Look up the current stable chart version

- P1.T1.S3: Create controller Application CR

- P1.T1.S4: Commit

### Task 2: ARC Runner Set ArgoCD App + RBAC

- P1.T2.S1: Create runner set values

- P1.T2.S2: Create RBAC manifest

- P1.T2.S3: Create runner set Application CR

- P1.T2.S4: Add raw manifests Application CR for RBAC

- P1.T2.S5: Commit

## Phase 2: ARC Bootstrap Secret

### Task 3: Bootstrap Secret (Manual Operation)

- P2.T3.S1: Create secrets directory

- P2.T3.S2: Apply and encrypt the secret

- P2.T3.S3: Commit the encrypted secret

- P2.T3.S4: Push and verify runner registers

## Phase 3: Version Tracking

### Task 4: Create versions.yaml

- P3.T4.S1: Check current cluster versions

- P3.T4.S2: Create versions.yaml

- P3.T4.S3: Commit

### Task 5: Omni/Talos Version Check Workflow

- P3.T5.S1: Create the workflow

- P3.T5.S2: Test by triggering manually

- P3.T5.S3: Commit

## Phase 4: Renovate & Smoke Testing

### Task 6: Renovate Configuration

- P4.T6.S1: Create renovate.json

- P4.T6.S2: Validate the regex against a real template

- P4.T6.S3: Commit

### Task 7: Smoke Test GitHub Actions Workflow

- P4.T7.S1: Create the workflow

- P4.T7.S2: Commit

- P4.T7.S3: Push and trigger a test run

## Phase 5: Branch Protection & End-to-End Verification

### Task 8: GitHub Branch Protection (Manual Operation)

- P5.T8.S1: Apply branch protection after smoke-test workflow is live

### Task 9: Verify Renovate Onboarding

- P5.T9.S1: Confirm Renovate GitHub App is installed

- P5.T9.S2: Trigger Renovate onboarding

- P5.T9.S3: Verify Renovate finds chart versions

- P5.T9.S4: Verify auto-merge fires on green for stateless app
