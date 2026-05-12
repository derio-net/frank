# Local Inference Gateway — Implementation Plan

## Phase 1: Local Inference Gateway — Implementation Plan

### Task 1: Create Ollama ArgoCD app

- P1.T1.S1: Create values file

- P1.T1.S2: Create Application CR

- P1.T1.S3: Commit

### Task 2: Create LiteLLM ExternalSecret manifests

- P1.T2.S1: Create ExternalSecret CR

- P1.T2.S2: Commit

### Task 3: Create LiteLLM ArgoCD apps

- P1.T3.S1: Create values file

- P1.T3.S2: Create LiteLLM Application CR (Helm chart)

- P1.T3.S3: Create LiteLLM extras Application CR (ExternalSecret manifests)

- P1.T3.S4: Commit

### Task 4: Add secrets to Infisical

### Task 5: Push and deploy Ollama

- P1.T5.S1: Push all commits

- P1.T5.S2: Sync ArgoCD root app to discover new apps

- P1.T5.S3: Sync Ollama app

- P1.T5.S4: Wait for Ollama pod to be ready

- P1.T5.S5: Verify Ollama is serving

- P1.T5.S6: Verify GPU allocation

### Task 6: Deploy and verify LiteLLM

- P1.T6.S1: Sync litellm-extras first (ExternalSecret)

- P1.T6.S2: Verify ExternalSecret synced

- P1.T6.S3: Sync litellm app

- P1.T6.S4: Wait for LiteLLM to be ready

- P1.T6.S5: Verify LoadBalancer IP

- P1.T6.S6: Verify LiteLLM health

### Task 7: End-to-end smoke test

- P1.T7.S1: Test local model (Ollama via LiteLLM)

- P1.T7.S2: Test cloud model (OpenRouter via LiteLLM)

- P1.T7.S3: Test default model routing

- P1.T7.S4: Test model listing

- P1.T7.S5: Verify ArgoCD shows all apps healthy

### Task 8: Update CLAUDE.md

- P1.T8.S1: Add to Services table

- P1.T8.S2: Commit
