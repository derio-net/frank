# Blog Hextra Migration Implementation Plan

## Phase 1: Theme Swap Foundation

### Task 1: Remove PaperMod submodule

- P1.T1.S1: Deinit the submodule

- P1.T1.S2: Remove leftover themes directory

### Task 2: Initialize Hugo modules and import Hextra

- P1.T2.S1: Initialize Hugo module in blog directory

- P1.T2.S2: Rewrite hugo.toml for Hextra

- P1.T2.S3: Fetch the Hextra module

### Task 3: Create landing page

- P1.T3.S1: Create root _index.md with Hextra landing layout

- P1.T3.S2: Verify Hugo starts (will show empty docs)

## Phase 2: Content Migration

### Task 1: Move content directories

- P2.T1.S1: Create docs parent and move series

- P2.T1.S2: Update Building section index

- P2.T1.S3: Update Operating section index

### Task 2: Migrate frontmatter across all posts

- P2.T2.S1: Write a frontmatter migration script

- P2.T2.S2: Run the migration script

- P2.T2.S3: Verify sidebar renders both series *(skipped — Hugo not available in this environment; requires manual verification)*

## Phase 3: Custom Features

### Task 1: Port shortcodes

- P3.T1.S1: Update asciinema shortcode for Hextra dark mode detection

- P3.T1.S2: Verify cluster-roadmap dark mode selector

### Task 2: Create asciinema head partial for Hextra

- P3.T2.S1: Create custom head partial

### Task 3: Add cover image layout override

- P3.T3.S1: Create docs single page override

### Task 4: Create custom CSS

- P3.T4.S1: Create assets/css/custom.css

- P3.T4.S2: Verify shortcodes and cover images render

## Phase 4: Read Tracking

### Task 1: Implement read tracker JavaScript

- P4.T1.S1: Create read-tracker.js

### Task 2: Wire up the read tracker

- P4.T2.S1: Add JS loading to custom head partial

- P4.T2.S2: Add reset link to custom footer partial

- P4.T2.S3: Verify read tracking works

## Phase 5: CI/CD & Cleanup

### Task 1: Update Dockerfile

- P5.T1.S1: Add Hugo module fetch to Dockerfile

- P5.T1.S2: Update GitHub Actions workflow for Hugo modules

### Task 2: Remove old PaperMod layout overrides

- P5.T2.S1: Delete PaperMod-specific layout files *(completed in Phase 1 — old layouts referenced PaperMod partials and broke the Hextra build)*

### Task 3: Full build verification

- P5.T3.S1: Production build test *(structural verification only — Hugo not available in agent environment; CI will validate)*

- P5.T3.S2: Verify search index *(requires Hugo build — CI will validate)*

- P5.T3.S3: Dev server smoke test *(requires Hugo dev server — manual verification needed post-merge)*

- P5.T3.S4: Clean up migration script
