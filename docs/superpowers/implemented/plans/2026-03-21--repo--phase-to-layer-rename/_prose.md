# Phase-to-Layer Naming Convention Rename

## Phase 1: Phase-to-Layer Naming Convention Rename

### Task 1: Create `docs/layers.yaml`

- P1.T1.S1: Write the layer registry

- P1.T1.S2: Commit

### Task 2: Rename all plan files

- P1.T2.S1: Execute all git mv commands for plans

### Task 3: Rename all spec files

- P1.T3.S1: Execute all git mv commands for specs

- P1.T3.S2: Commit renames

### Task 4: Update cross-references inside plans and specs

- P1.T4.S1: Find and replace old filenames with new filenames inside all plan/spec files

- P1.T4.S2: Replace `Phase XX`, `Phase 04`, etc. in plan/spec headers with layer references

- P1.T4.S3: Commit

### Task 5: Update CLAUDE.md naming convention and workflows

- P1.T5.S1: Update "Standard Phase Workflow" section

- P1.T5.S2: Update "Phase Fix/Extension Workflow" section

- P1.T5.S3: Update "Plan Naming Convention" section

- P1.T5.S4: Update Architecture tree comments

- P1.T5.S5: Update Gotchas if any reference phases conceptually

- P1.T5.S6: Commit

### Task 6: Update `docs/runbooks/manual-operations.yaml`

- P1.T6.S1: Rename `phase` field to `layer` throughout

- P1.T6.S2: Update operation IDs from `phaseNN-*` to `<layer>-*`

- P1.T6.S3: Update `plan:` path references to new filenames

- P1.T6.S4: Update any comments referencing phases

- P1.T6.S5: Commit

### Task 7: Update skills

- P1.T7.S1: Update blog-post skill

- P1.T7.S2: Update update-readme skill

- P1.T7.S3: Update sync-runbook skill

- P1.T7.S4: Commit

### Task 8: Update README.md

- P1.T8.S1: Update architecture tree comments

- P1.T8.S2: Update any narrative references to "phase" → "layer"

- P1.T8.S3: Commit

### Task 9: Update blog post narrative text

- P1.T9.S1: Find all "phase"/"Phase" occurrences in blog posts

- P1.T9.S2: Update each occurrence contextually

- P1.T9.S3: Update `blog/content/building/00-overview/index.md`

- P1.T9.S4: Commit

### Task 10: Verify no stale phase references remain

- P1.T10.S1: Grep for stale references

- P1.T10.S2: Verify all plan/spec cross-references resolve

- P1.T10.S3: Final commit (if any fixups needed)
