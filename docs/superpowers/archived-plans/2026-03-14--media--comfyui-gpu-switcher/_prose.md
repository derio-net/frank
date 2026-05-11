# Media Generation Stack Implementation Plan

## Phase 1: Media Generation Stack Implementation Plan

### Task 1: Create ComfyUI namespace

- P1.T1.S1: Create the namespace manifest

- P1.T1.S2: Verify template renders

- P1.T1.S3: Commit

### Task 2: Create ComfyUI PVC for model storage

- P1.T2.S1: Create the PVC manifest

- P1.T2.S2: Validate YAML syntax

- P1.T2.S3: Commit

### Task 3: Create ComfyUI Deployment

- P1.T3.S1: Create the Deployment manifest

- P1.T3.S2: Validate YAML syntax

- P1.T3.S3: Commit

### Task 4: Create ComfyUI Services

- P1.T4.S1: Create ClusterIP Service

- P1.T4.S2: Create LoadBalancer Service

- P1.T4.S3: Validate both

- P1.T4.S4: Commit

### Task 5: Create ComfyUI ArgoCD Application CR

- P1.T5.S1: Create the Application CR

- P1.T5.S2: Verify template renders

- P1.T5.S3: Commit

- P1.T5.S1: Add ignoreDifferences to ollama.yaml

- P1.T5.S2: Verify template renders

- P1.T5.S3: Commit

### Task 6: Initialize Go module

- P1.T6.S1: Create directory and initialize Go module

- P1.T6.S2: Add kubernetes client-go dependency

- P1.T6.S3: Commit

### Task 7: Implement Kubernetes client operations

- P1.T7.S1: Write the failing test first

- P1.T7.S2: Run test to verify it fails

- P1.T7.S3: Implement k8s.go

- P1.T7.S4: Run tests to verify they pass

- P1.T7.S5: Commit

### Task 8: Implement HTTP server and dashboard UI

- P1.T8.S1: Create the dashboard HTML

- P1.T8.S2: Create main.go with HTTP server

- P1.T8.S3: Verify it compiles

- P1.T8.S4: Run all tests

- P1.T8.S5: Commit

### Task 9: Create Dockerfile and build image

- P1.T9.S1: Create multi-stage Dockerfile

- P1.T9.S2: Verify Docker and GHCR access

- P1.T9.S3: Build the image for amd64

- P1.T9.S4: Push to GHCR

- P1.T9.S4: Tag with a version for reproducibility

- P1.T9.S5: Commit

### Task 10: Create GPU Switcher namespace

- P1.T10.S1: Create the namespace manifest

- P1.T10.S2: Commit

### Task 11: Create RBAC resources

- P1.T11.S1: Create ServiceAccount

- P1.T11.S2: Create ClusterRole

- P1.T11.S3: Create ClusterRoleBinding

- P1.T11.S4: Validate all RBAC manifests

- P1.T11.S5: Commit

### Task 12: Create GPU Switcher Deployment and Service

- P1.T12.S1: Create the Deployment

- P1.T12.S2: Create the LoadBalancer Service

- P1.T12.S3: Validate both

- P1.T12.S4: Commit

### Task 13: Create GPU Switcher ArgoCD Application CR

- P1.T13.S1: Create the Application CR

- P1.T13.S2: Verify template renders

- P1.T13.S3: Commit

### Task 14: Push and verify ArgoCD sync

- P1.T14.S1: Push all commits to main

- P1.T14.S2: Wait for ArgoCD to sync the root app

- P1.T14.S3: Verify ComfyUI app is synced and healthy

- P1.T14.S4: Verify GPU Switcher app is synced and running

- P1.T14.S5: Verify ComfyUI PVC is bound

- P1.T14.S6: Verify GPU Switcher is accessible

### Task 15: Test GPU switching end-to-end

- P1.T15.S1: Open GPU Switcher UI in browser

- P1.T15.S2: Switch to ComfyUI via the dashboard

- P1.T15.S3: Verify ComfyUI is running

- P1.T15.S4: Verify ComfyUI Web UI is accessible

- P1.T15.S5: Switch back to Ollama

- P1.T15.S6: Verify Ollama restored

- P1.T15.S7: Test "Stop All"

### Task 16: Download initial models (one-time setup)

### Task 17: Final commit — update CLAUDE.md services table

- P1.T17.S0: Add Traefik routes on raspi-omni

- P1.T17.S1: Add ComfyUI and GPU Switcher to the Services table in CLAUDE.md

- P1.T17.S2: Commit
