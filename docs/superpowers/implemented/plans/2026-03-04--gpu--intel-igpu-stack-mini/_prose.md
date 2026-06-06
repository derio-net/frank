# Intel iGPU (Arc) Stack for mini-{1..3} — Implementation Plan

## Phase 1: Intel iGPU (Arc) Stack for mini-{1..3} — Implementation Plan

### Task 1: Fix mini node labels (amd-igpu → intel-igpu)

- P1.T1.S1: Update labels in all three files

- P1.T1.S2: Apply updated labels (no reboot — labels are hot-applied)

- P1.T1.S3: Verify labels

- P1.T1.S4: Commit

### Task 2: Create Omni ExtensionsConfiguration patches for i915

- P1.T2.S1: Delete the draft file (wrong format)

- P1.T2.S2: Create mini-1 extension patch

- P1.T2.S3: Create mini-2 extension patch

- P1.T2.S4: Create mini-3 extension patch

- P1.T2.S5: Commit

### Task 3: Apply extensions (triggers rolling reboot of mini nodes)

- P1.T3.S1: Apply mini-1 and wait for Ready

- P1.T3.S2: Verify mini-1 extensions loaded

- P1.T3.S3: Apply mini-2 and wait for Ready

- P1.T3.S4: Verify mini-2

- P1.T3.S5: Apply mini-3 and wait for Ready

- P1.T3.S6: Verify mini-3

### Task 4: Create and apply CDI containerd patch

- P1.T4.S1: Create the patch file

- P1.T4.S2: Apply the patch

- P1.T4.S3: Verify containerd restarted (wait ~30s)

- P1.T4.S4: Commit

### Task 5: Create phase05 README

- P1.T5.S1: Commit

### Task 6: ArgoCD — Intel GPU Resource Driver (DRA)

### Task 7: Verify end-to-end

- P1.T7.S1: Check driver pods are running on mini nodes

- P1.T7.S2: Check ResourceSlices — driver has discovered GPUs

- P1.T7.S3: Check DeviceClass was created

- P1.T7.S4: Smoke test — create a ResourceClaim and a test pod

- P1.T7.S5: Confirm ResourceClaim allocation shows the bound node

- P1.T7.S6: (Reference) How workloads will request GPUs going forward
