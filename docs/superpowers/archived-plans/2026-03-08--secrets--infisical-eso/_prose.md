# Secrets Management Implementation Plan

## Phase 1: Secrets Management Implementation Plan

### Task 1: Discover Chart Versions

- P1.T1.S1: Add Helm repos

- P1.T1.S2: Check latest stable versions

- P1.T1.S3: Inspect Infisical chart values

### Task 2: Deploy ESO (External Secrets Operator)

- P1.T2.S1: Create namespace manifest

- P1.T2.S2: Create ESO values.yaml

- P1.T2.S3: Create ESO Application CR

- P1.T2.S4: Verify file structure

- P1.T2.S5: Commit

### Task 3: Deploy Infisical

- P1.T3.S1: Create namespace manifest

- P1.T3.S2: Create Infisical values.yaml

- P1.T3.S3: Create Infisical Application CR

- P1.T3.S4: Verify file structure

- P1.T3.S5: Commit

### Task 4: Create Infisical Bootstrap Secret (SOPS)

- P1.T4.S1: Generate credentials

- P1.T4.S2: Create plaintext secret

- P1.T4.S3: Encrypt in-place with SOPS

- P1.T4.S4: Verify encryption

- P1.T4.S5: Apply the secret to the cluster

- P1.T4.S6: Verify the secret is in the cluster

- P1.T4.S7: Commit the encrypted secret

### Task 5: Push and Verify ESO + Infisical Deploy

- P1.T5.S1: Push to git

- P1.T5.S2: Trigger ArgoCD sync (if needed)

- P1.T5.S3: Watch ESO pods come up

- P1.T5.S4: Watch Infisical pods come up

- P1.T5.S5: Check LoadBalancer IP assignment

- P1.T5.S6: Check Infisical health

### Task 6: Infisical UI Setup (Manual)

- P1.T6.S1: Open the Infisical UI

- P1.T6.S2: Create the admin account

- P1.T6.S3: Create the project

- P1.T6.S4: Create the `prod` environment

- P1.T6.S5: Create a Machine Identity for ESO

- P1.T6.S6: Grant the identity access to the project

### Task 7: Create and Apply ESO Credentials Secret (SOPS)

- P1.T7.S1: Create plaintext credentials secret

- P1.T7.S2: Encrypt in-place

- P1.T7.S3: Apply to cluster

- P1.T7.S4: Verify

- P1.T7.S5: Commit

### Task 8: Create ClusterSecretStore and infisical-extras App

- P1.T8.S1: Create ClusterSecretStore manifest

- P1.T8.S2: Create infisical-extras Application CR

- P1.T8.S3: Verify file structure

- P1.T8.S4: Commit

### Task 9: Push and Verify ClusterSecretStore

- P1.T9.S1: Push to git

- P1.T9.S2: Sync root app

- P1.T9.S3: Watch infisical-extras sync

- P1.T9.S4: Verify ClusterSecretStore is Ready

### Task 10: Demo ExternalSecret Smoke Test

- P1.T10.S1: Add a test secret in Infisical UI

- P1.T10.S2: Create a demo ExternalSecret

- P1.T10.S3: Wait for sync (up to 60s)

- P1.T10.S4: Verify the K8s Secret was created

- P1.T10.S5: Clean up the test resources

### Task 11: Write Blog Post

- P1.T11.S1: Create the post directory

- P1.T11.S2: Write the blog post

- P1.T11.S3: Add cover image prompt to post directory

- P1.T11.S4: Commit blog post

- P1.T11.S5: Preview in Hugo dev server

- P1.T11.S6: Final push
