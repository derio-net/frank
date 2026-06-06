# GPU Operator Talos Validation Fix — Implementation Plan

## Phase 1: GPU Operator Talos Validation Fix — Implementation Plan

### Task 1: Create the validation markers DaemonSet manifest

- P1.T1.S1: Create the manifest directory

- P1.T1.S2: Write the DaemonSet manifest

- P1.T1.S3: Commit

### Task 2: Create the gpu-operator-extras ArgoCD Application

- P1.T2.S1: Write the Application CR

- P1.T2.S2: Commit

### Task 3: Push and verify GPU Operator pods unblock

- P1.T3.S1: Push to remote

- P1.T3.S2: Sync the root app

- P1.T3.S3: Sync gpu-operator-extras

- P1.T3.S4: Verify the validation markers pod is running

- P1.T3.S5: Verify the marker files exist on the host

- P1.T3.S6: Wait for GPU Operator pods to unblock

- P1.T3.S7: Verify GPU is registered as allocatable

- P1.T3.S8: Commit nothing — this is a verification task

### Task 4: Verify Ollama schedules and serves models

- P1.T4.S1: Check Ollama pod status

- P1.T4.S2: Wait for model pull (may take several minutes)

- P1.T4.S3: Test inference via LiteLLM

- P1.T4.S4: Commit nothing — this is a verification task

### Task 5: Update CLAUDE.md and documentation

- P1.T5.S1: Update the gpu-operator app notes in README.md

- P1.T5.S2: Commit

### Task 6: Final push and verification

- P1.T6.S1: Push all remaining commits

- P1.T6.S2: Verify all three GPU-related ArgoCD apps are healthy

- P1.T6.S3: Run a Sympozium test agent to verify end-to-end

- P1.T6.S4: Clean up test run

- P1.T6.S5: Final push
