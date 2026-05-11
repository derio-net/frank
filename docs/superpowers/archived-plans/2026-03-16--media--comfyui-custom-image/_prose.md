# Custom ComfyUI Docker Image Implementation Plan

## Phase 1: Custom ComfyUI Docker Image Implementation Plan

### Task 1: Create the entrypoint script

- P1.T1.S1: Write the entrypoint script

- P1.T1.S2: Set executable bit and commit

### Task 2: Create the Dockerfile

- P1.T2.S1: Write the Dockerfile

- P1.T2.S2: Commit

### Task 3: Create the GitHub Actions workflow

- P1.T3.S1: Write the workflow

- P1.T3.S2: Commit

### Task 4: Create the custom-nodes PVC

- P1.T4.S1: Write the PVC manifest

- P1.T4.S2: Commit

### Task 5: Update the Deployment manifest

- P1.T5.S1: Update the deployment

- P1.T5.S2: Verify services don't need changes

- P1.T5.S3: Commit

### Task 6: Verify NVIDIA driver prerequisite

- P1.T6.S1: Check host NVIDIA driver version

- P1.T6.S2: Confirm sm_120 capability

### Task 7: Trigger the image build

- P1.T7.S1: Push to trigger CI

- P1.T7.S2: Monitor the build

- P1.T7.S3: Verify image exists in registry

### Task 8: Verify ArgoCD sync and deployment health

- P1.T8.S1: Check ArgoCD sync status

- P1.T8.S2: Verify PVC was created

- P1.T8.S3: Activate ComfyUI via GPU Switcher

- P1.T8.S4: Watch pod startup

- P1.T8.S5: Verify GPU/CUDA inside the container

- P1.T8.S6: Access ComfyUI Web UI

- P1.T8.S7: Deactivate ComfyUI

- P1.T8.S8: Final commit (if any adjustments were needed)
