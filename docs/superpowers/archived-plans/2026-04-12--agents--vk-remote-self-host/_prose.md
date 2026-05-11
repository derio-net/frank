# VK Remote Self-Host Implementation Plan

## Phase 0: Fork & CI

### Task 1: Fork the VK repository

### Task 2: Create GitHub Actions workflow for vk-remote image

### Task 3: Verify the Dockerfile and trigger first build

### Task 4: Create Infisical secrets

## Phase 1: ArgoCD Manifests

### Task 1: Create namespace manifest

- P1.T1.S1: Write the namespace manifest

### Task 2: Create ExternalSecret for VK Remote secrets

- P1.T2.S1: Write the ExternalSecret

### Task 3: Create PostgreSQL StatefulSet

- P1.T3.S1: Write the PVC

- P1.T3.S2: Write the PostgreSQL Deployment

- P1.T3.S3: Write the PostgreSQL Service

### Task 4: Create PostgreSQL init Job for ElectricSQL role

- P1.T4.S1: Write the init Job

### Task 5: Create ElectricSQL Deployment

- P1.T5.S1: Write the ElectricSQL Deployment and Service

### Task 6: Create vk-remote Deployment

- P1.T6.S1: Write the vk-remote Deployment

### Task 7: Create ArgoCD Application CR

- P1.T7.S1: Write the Application template

### Task 8: Add IngressRoute for vk-remote

- P1.T8.S1: Append the VK Remote IngressRoute

### Task 9: Add Authentik proxy provider for VK Remote

- P1.T9.S1: Append VK Remote proxy provider and application entries

### Task 10: Add secure-agent-pod VK_SHARED_API_BASE

- P1.T10.S1: Add VK_SHARED_API_BASE env var

### Task 11: Add homepage entry

- P1.T11.S1: Add VK Remote to the Development section

### Task 12: Commit all manifests

- P1.T12.S1: Stage and commit

## Phase 2: Deploy & Configure

### Task 1: Verify ArgoCD sync

### Task 2: Verify health endpoint

### Task 3: Login and create org/project

### Task 4: Update bridge env vars

### Task 5: Assign Authentik outpost provider

### Task 6: Verify browser access

### Task 7: End-to-end bridge test

## Phase 3: Post-Deploy Checklist
