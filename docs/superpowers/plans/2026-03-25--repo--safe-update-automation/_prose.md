# Safe Update Automation Implementation Plan

**Spec:** `docs/superpowers/specs/2026-03-25--repo--safe-update-automation-design.md`
**Status:** Not Started

## Phase 1: GitHub App Prerequisites

### Task 1: Install ARC GitHub App

- P1.T1.S1: Create and install the ARC GitHub App

### Task 2: Install Renovate GitHub App

- P1.T2.S1: Install Renovate and grant repo access

## Phase 2: ARC Self-Hosted Runner

### Task 1: ARC Controller ArgoCD App

- P2.T1.S1: Create controller values

- P2.T1.S2: Look up the current stable chart version

- P2.T1.S3: Create controller Application CR

- P2.T1.S4: Commit

### Task 2: ARC Runner Set ArgoCD App + RBAC

- P2.T2.S1: Create runner set values

- P2.T2.S2: Create RBAC manifest

- P2.T2.S3: Create runner set Application CR

- P2.T2.S4: Add raw manifests Application CR for RBAC

- P2.T2.S5: Commit

## Phase 3: ARC Bootstrap Secret

### Task 3: Bootstrap Secret (Manual Operation)

- P3.T3.S1: Create secrets directory

- P3.T3.S2: Apply and encrypt the secret

- P3.T3.S3: Commit the encrypted secret

- P3.T3.S4: Push and verify runner registers

## Phase 4: Version Tracking

### Task 4: Create versions.yaml

- P4.T4.S1: Check current cluster versions

- P4.T4.S2: Create versions.yaml

- P4.T4.S3: Commit

### Task 5: Omni/Talos Version Check Workflow

- P4.T5.S1: Create the workflow

- P4.T5.S2: Test by triggering manually

- P4.T5.S3: Commit

## Phase 5: Renovate & Smoke Testing

### Task 6: Renovate Configuration

- P5.T6.S1: Create renovate.json

- P5.T6.S2: Validate the regex against a real template

- P5.T6.S3: Commit

### Task 7: Smoke Test GitHub Actions Workflow

- P5.T7.S1: Create the workflow

- P5.T7.S2: Commit

- P5.T7.S3: Push and trigger a test run

## Phase 6: Branch Protection & End-to-End Verification

### Task 8: GitHub Branch Protection (Manual Operation)

- P6.T8.S1: Apply branch protection after smoke-test workflow is live

### Task 9: Verify Renovate Onboarding

- P6.T9.S1: Confirm Renovate GitHub App is installed

- P6.T9.S2: Trigger Renovate onboarding

- P6.T9.S3: Verify Renovate finds chart versions

- P6.T9.S4: Verify auto-merge fires on green for stateless app
