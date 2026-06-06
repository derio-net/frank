# Backup Implementation Plan

## Phase 1: Backup Implementation Plan

### Task 1: Create the NAS (NFS) BackupTarget manifest

- P1.T1.S1: Write the manifest

- P1.T1.S2: Verify the file was written correctly

### Task 2: Create the R2 credentials Secret (plaintext then SOPS-encrypt)

- P1.T2.S1: Write the plaintext secret

- P1.T2.S2: Encrypt with SOPS

- P1.T2.S3: Verify encryption worked

- P1.T2.S4: Check if ArgoCD SOPS decryption is configured

### Task 3: Create the R2 BackupTarget manifest

- P1.T3.S1: Write the manifest

- P1.T3.S2: Verify the file

### Task 4: Create the daily recurring job (NAS)

- P1.T4.S1: Write the manifest

- P1.T4.S2: Verify the file

- P1.T4.S3: Verify the `backupTargetName` field is supported

### Task 5: Create the weekly recurring job (R2)

- P1.T5.S1: Write the manifest

- P1.T5.S2: Verify the file

### Task 6: Add `ignoreDifferences` to the longhorn-extras Application

- P1.T6.S1: Read the current file

- P1.T6.S2: Add sync options and ignoreDifferences

- P1.T6.S3: Verify the edit

### Task 7: Commit and push

- P1.T7.S1: Stage all new/modified files

- P1.T7.S2: Verify the secret is encrypted before committing

- P1.T7.S3: Commit

- P1.T7.S4: Push

- P1.T7.S5: Watch ArgoCD sync

### Task 8: Verify backup targets in Longhorn UI

- P1.T8.S1: Open Longhorn UI

- P1.T8.S2: Check backup targets appear

- P1.T8.S3: Verify recurring jobs

- P1.T8.S4: Trigger a manual backup to test the NAS target

- P1.T8.S5: Test restore (optional but recommended)

### Task 9: Write the blog post

- P1.T9.S1: Create the post directory

- P1.T9.S2: Write the post

- P1.T9.S3: Preview the post locally

- P1.T9.S4: Generate cover image prompt

- P1.T9.S5: Add a placeholder cover and commit

- P1.T9.S6: Commit the blog post
