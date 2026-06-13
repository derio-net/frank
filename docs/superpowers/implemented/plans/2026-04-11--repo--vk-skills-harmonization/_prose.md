# VK Skills Harmonization — Frank Implementation Plan

## Phase 0: Infrastructure Harmonization

### Task 1: Create plan-config.yaml

- P0.T1.S1: Write the Frank profile

- P0.T1.S2: Verify YAML

- P0.T1.S3: Commit *(completed out-of-band in commit b8d2bdd)*

### Task 2: Delete vendored superpowers skills

- P0.T2.S1: Delete superpowers skill directories

- P0.T2.S2: Verify Frank-specific skills remain

- P0.T2.S3: Commit

### Task 3: Delete sync-superpowers.sh

- P0.T3.S1: Delete the script

- P0.T3.S2: Commit

### Task 4: Replace validate-plans.sh with thin wrapper

- P0.T4.S1: Replace with thin wrapper

- P0.T4.S2: Verify syntax

- P0.T4.S3: Commit

### Task 5: Update plan-status.sh for Phase headers

- P0.T5.S1: Update the --open loop to recognize Phase headers

- P0.T5.S2: Test against a phased plan

- P0.T5.S3: Commit

### Task 6: Update rules for vk-plan canonical skill

- P0.T6.S1: Update repo-workflows.md

- P0.T6.S2: Update repo-principles.md

- P0.T6.S3: Update plan-post-deploy-checklist.md

- P0.T6.S4: Verify changes

- P0.T6.S5: Commit

### Task 7: Update plan-checklist-check hook for Phase format

- P0.T7.S1: Extend the detection for Phase-based plans

- P0.T7.S2: Verify syntax

- P0.T7.S3: Commit

## Phase 1: Active Plan Conversion

### Task 1: Convert multi-cluster-restructure plan

- P1.T1.S1: Read the current plan

- P1.T1.S2: Update the banner

- P1.T1.S3: Insert Phase headers

- P1.T1.S4: Validate

- P1.T1.S5: Commit

### Task 2: Convert safe-update-automation plan

- P1.T2.S1: Read the current plan

- P1.T2.S2: Apply the conversion procedure

- P1.T2.S3: Validate

- P1.T2.S4: Commit

### Task 3: Convert cicd-platform plan

- P1.T3.S1: Read the current plan

- P1.T3.S2: Apply the conversion procedure

- P1.T3.S3: Validate

- P1.T3.S4: Commit

### Task 4: Convert blog-media-infrastructure plan

- P1.T4.S1: Read the current plan

- P1.T4.S2: Apply the conversion procedure

- P1.T4.S3: Validate

- P1.T4.S4: Commit
