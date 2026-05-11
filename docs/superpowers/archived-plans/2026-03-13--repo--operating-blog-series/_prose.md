# Operating on Frank — Blog Series Implementation Plan

## Phase 1: Operating on Frank — Blog Series Implementation Plan

### Task 1: Move existing posts to `building/` subsection

- P1.T1.S1: Create the `building/` directory and `_index.md`

- P1.T1.S2: Move all post directories into `building/`

- P1.T1.S3: Update all relref links across all moved posts

- P1.T1.S4: Commit

### Task 2: Create `operating/` subsection scaffolding

- P1.T2.S1: Create the `operating/` directory and `_index.md`

- P1.T2.S2: Commit

### Task 3: Update Hugo config (`hugo.toml`)

- P1.T3.S1: Update site title and label

- P1.T3.S2: Update description and add mainSections + operatingThinBanner

- P1.T3.S3: Update homeInfoParams content

- P1.T3.S4: Replace menu entries

- P1.T3.S5: Commit

### Task 4: Section-aware thin banner in `header.html`

- P1.T4.S1: Replace the banner block

- P1.T4.S2: Commit

### Task 5: Section-scoped post navigation

- P1.T5.S1: Create override partial

- P1.T5.S2: Commit

### Task 6: Verify Hugo build and site structure

- P1.T6.S1: Run Hugo build

- P1.T6.S2: Spot-check generated output

- P1.T6.S3: Start dev server and visually verify

- P1.T6.S4: Commit any fixes if needed

### Task 7: Add banner image prompts to `prompt_for_images.yaml`

- P1.T7.S1: Add operating thin banner prompt

- P1.T7.S2: Commit

- P1.T7.S3: Generate the banner image

- P1.T7.S4: Quick visual check of operating banner

- P1.T7.S5: Commit generated image

### Task 8: Update CLAUDE.md stale path references

- P1.T8.S1: Update Standard Layer Workflow path

- P1.T8.S2: Update Blog Post Pattern section

- P1.T8.S3: Update Architecture section

- P1.T8.S4: Commit

### Task 9: Update overview page to reference operating series

- P1.T9.S1: Add operating series section

- P1.T9.S2: Commit

### Task 10: Write operating post 01 — Cluster & Nodes

- P1.T10.S1: Read the building post for context

- P1.T10.S2: Research upstream docs for operational commands

- P1.T10.S3: Write the post

- P1.T10.S4: Add cover image prompt

- P1.T10.S5: Generate cover image

- P1.T10.S6: Commit

### Task 11: Write operating post 02 — Storage & Backups

- P1.T11.S1: Read the building posts

- P1.T11.S2: Research upstream docs

- P1.T11.S3: Write the post

- P1.T11.S4: Add cover image prompt and generate

- P1.T11.S5: Commit

### Task 12: Write operating post 03 — GitOps

- P1.T12.S1: Read the building post

- P1.T12.S2: Research upstream docs

- P1.T12.S3: Write the post

- P1.T12.S4: Add cover image prompt and generate

- P1.T12.S5: Commit

### Task 13: Write operating post 04 — GPU Compute

- P1.T13.S1: Read the building posts

- P1.T13.S2: Research upstream docs

- P1.T13.S3: Write the post

- P1.T13.S4: Add cover image prompt and generate

- P1.T13.S5: Commit

### Task 14: Write operating post 05 — Observability

- P1.T14.S1: Read the building post

- P1.T14.S2: Research upstream docs

- P1.T14.S3: Write the post

- P1.T14.S4: Add cover image prompt and generate

- P1.T14.S5: Commit

### Task 15: Write operating post 06 — Secrets

- P1.T15.S1: Read the building post

- P1.T15.S2: Research upstream docs

- P1.T15.S3: Write the post

- P1.T15.S4: Add cover image prompt and generate

- P1.T15.S5: Commit

### Task 16: Write operating post 07 — Local Inference

- P1.T16.S1: Read the building post

- P1.T16.S2: Research upstream docs

- P1.T16.S3: Write the post

- P1.T16.S4: Add cover image prompt and generate

- P1.T16.S5: Commit

### Task 17: Write operating post 08 — Authentication

- P1.T17.S1: Read the building post

- P1.T17.S2: Research upstream docs

- P1.T17.S3: Write the post

- P1.T17.S4: Add cover image prompt and generate

- P1.T17.S5: Commit

### Task 18: Write operating post 09 — Multi-tenancy

- P1.T18.S1: Read the building post

- P1.T18.S2: Research upstream docs

- P1.T18.S3: Write the post

- P1.T18.S4: Add cover image prompt and generate

- P1.T18.S5: Commit

### Task 19: Update overview page with live links

- P1.T19.S1: Replace "coming soon" items with relref links

- P1.T19.S2: Commit

### Task 20: Final verification

- P1.T20.S1: Run Hugo build

- P1.T20.S2: Start dev server and verify all pages

- P1.T20.S3: Final commit if any fixes needed
