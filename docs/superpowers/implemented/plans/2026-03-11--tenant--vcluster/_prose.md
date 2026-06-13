# Multi-tenancy — vCluster Implementation Plan

## Phase 1: Multi-tenancy — vCluster Implementation Plan

### Task 1: Create the vCluster template values file

- P1.T1.S1: Create directory structure

- P1.T1.S2: Write the template values file

- P1.T1.S3: Commit

### Task 2: Create the "experiments" vCluster namespace

- P1.T2.S1: Write namespace manifest

- P1.T2.S2: Commit

### Task 3: Create the "experiments" vCluster values (overrides only)

- P1.T3.S1: Create directory

- P1.T3.S2: Write values file (overrides only)

- P1.T3.S3: Commit

### Task 4: Create the ArgoCD Application CR for "experiments"

- P1.T4.S1: Write the Application CR

- P1.T4.S2: Commit

### Task 5: Push and verify ArgoCD sync

- P1.T5.S1: Push all commits

- P1.T5.S2: Wait for ArgoCD to pick up changes

- P1.T5.S3: Sync if not auto-synced

- P1.T5.S4: Wait for vCluster to become healthy

- P1.T5.S5: Verify ArgoCD app health

- P1.T5.S6: Commit nothing — this is a verification step only

### Task 6: Connect to vCluster and validate

- P1.T6.S1: Install vcluster CLI (if not present)

- P1.T6.S2: Connect to the experiments vCluster

- P1.T6.S3: Verify the virtual cluster is functional

- P1.T6.S4: Verify host-side isolation

- P1.T6.S5: Clean up test workload

- P1.T6.S6: Commit nothing — verification only

### Task 7: Rename design file (COMPLETED — already renamed to layer-based naming)

### Task 8: Update CLAUDE.md services table

- P1.T8.S1: Update Architecture directory tree in CLAUDE.md

- P1.T8.S2: Commit

### Task 9: Follow standard layer workflow — Blog, README, Runbook

- P1.T9.S1: Blog post — Run `/blog-post` skill. Title: "Multi-tenancy: Disposable Kubernetes Clusters with vCluster". Update the series index (`blog/content/posts/00-overview/index.md`) and roadmap shortcode (`blog/layouts/shortcodes/cluster-roadmap.html`).

- P1.T9.S2: Update README — Run `/update-readme` to sync Technology Stack, Repository Structure, Service Access, and Current Status.

- P1.T9.S3: Sync runbook — Run `/sync-runbook` if any `# manual-operation` blocks exist in this plan. (This plan has none — vCluster CLI install is a developer tool, not a cluster operation.)

- P1.T9.S4: Review — Verify deployment health and blog accuracy.
