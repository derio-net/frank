# VK Relay Deployment Implementation Plan

## Phase 0: Manifests

### Task 1: Add relay sidecar to vk-remote deployment

- P0.T1.S1: Add relay-server container

- P0.T1.S2: Commit

### Task 2: Create service with relay port

- P0.T2.S1: Add relay port to the existing Service

- P0.T2.S2: Commit

### Task 3: Split IngressRoute for relay paths

- P0.T3.S1: Replace the existing vk-remote IngressRoute with two rules

- P0.T3.S2: Commit

### Task 4: Add VK_SHARED_RELAY_API_BASE to secure-agent-pod

- P0.T4.S1: Add the env var

- P0.T4.S2: Commit

### Task 5: Commit all and push

- P0.T5.S1: Push to trigger ArgoCD sync

## Phase 1: Deploy & Verify

### Task 1: Verify ArgoCD sync

- P1.T1.S1: Check vk-remote pod has two containers

- P1.T1.S2: Check relay-server container is running

- P1.T1.S3: Verify relay endpoint is reachable through Traefik

### Task 2: Verify local server connects to relay

- P1.T2.S1: Check secure-agent-pod logs for relay registration

- P1.T2.S2: Verify host appears in VK remote UI

### Task 3: Pair browser with local server (one-time)

- P1.T3.S1: Port-forward to the local VK server

- P1.T3.S2: Generate pairing code

- P1.T3.S3: Enter code in remote UI

- P1.T3.S4: Verify workspace repos are visible

- P1.T3.S5: Stop the port-forward

## Phase 2: Post-Deploy Checklist
