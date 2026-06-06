# Blog Media Infrastructure Implementation Plan

## Phase 0: Media Infrastructure

### Task 1: Create `screenshot` shortcode

- P0.T1.S1: Create the shortcode

- P0.T1.S2: Commit *(combined into single infrastructure commit)*

### Task 2: Create `asciinema` shortcode

- P0.T2.S1: Create the shortcode *(already created in prior session)*

- P0.T2.S2: Commit *(combined into single infrastructure commit)*

### Task 3: Add CSS and conditional asset loading to extend_head.html

- P0.T3.S1: Append conditional asciinema assets + media CSS after the closing `</style>` tag

- P0.T3.S2: Verify Hugo builds without errors

- P0.T3.S3: Commit *(combined into single infrastructure commit)*

### Task 4: Create MEDIA-GUIDE.md

- P0.T4.S1: Write the guide

- P0.T4.S2: Commit *(combined into single infrastructure commit)*

### Task 5: Insert media placeholders into high-priority building posts

- P0.T5.S1: Insert placeholders into all 9 high-priority posts

- P0.T5.S2: Verify Hugo builds clean

- P0.T5.S3: Commit *(combined into single placeholders commit)*

### Task 6: Insert media placeholders into medium-priority and operating posts

- P0.T6.S1: Insert placeholders into all 14 medium/operating posts (1-2 per post)

- P0.T6.S2: Verify Hugo builds clean

- P0.T6.S3: Commit *(combined into single placeholders commit)*

### Task 7: Create `/media` skill

- P0.T7.S1: Create the skill file

- P0.T7.S2: Commit *(combined into single infrastructure commit)*

## Phase 1: Verification

### Task 8: Verify and push

- P1.T8.S1: Run Hugo build to verify no regressions

- P1.T8.S2: Verify placeholders are invisible in output

- P1.T8.S3: Push all commits
