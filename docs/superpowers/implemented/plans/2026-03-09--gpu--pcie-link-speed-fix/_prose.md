# RTX 5070 PCIe Link Speed Fix Implementation Plan

## Phase 1: RTX 5070 PCIe Link Speed Fix Implementation Plan

### Task 1: Prepare the USB Drive

- P1.T1.S1: Download BIOS files

- P1.T1.S2: Verify USB contents

- P1.T1.S3: Commit nothing — this task has no repo changes

### Task 2: Backup F3 Settings & Flash to F6

### Task 3: Force PCIe Gen 4

### Task 4: Verify Cluster Health

- P1.T4.S1: Confirm node is Ready

- P1.T4.S2: Confirm PCIe link speed

- P1.T4.S3: Confirm NVIDIA module loads cleanly

- P1.T4.S4: Confirm DRI devices present

- P1.T4.S5: Confirm GPU detected by operator

- P1.T4.S6: If still Gen 1 after all steps

### Task 5: Sync Runbook

- P1.T5.S1: Run sync-runbook to register the two manual operations

- P1.T5.S2: Update manual operation statuses to `done` in this plan

- P1.T5.S3: Commit
