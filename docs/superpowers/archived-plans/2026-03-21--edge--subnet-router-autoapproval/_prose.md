# Subnet Router Auto-Approval + Split DNS Implementation Plan

## Phase 1: Subnet Router Auto-Approval + Split DNS Implementation Plan

### Task 1: Update Headscale ACL Policy with autoApprovers

- P1.T1.S1: Replace the `acl.yaml` section in the ConfigMap

- P1.T1.S2: Verify the YAML is valid

### Task 2: Add Split DNS Nameservers to Headscale Config

- P1.T2.S1: Add the `split` key under `dns.nameservers`

- P1.T2.S2: Verify the full ConfigMap is valid

- P1.T2.S3: Commit the ConfigMap changes

### Task 3: Update Operating Blog Post

- P1.T3.S1: Rewrite the "Registering an Exit Node" section (line 186)

- P1.T3.S2: Add a "Split DNS" section after the new subnet router section

- P1.T3.S3: Verify the blog builds

- P1.T3.S4: Commit the blog update

### Task 4: Deploy and Verify

- P1.T4.S1: Push and let ArgoCD sync

- P1.T4.S2: Restart Headscale to pick up config changes

- P1.T4.S3: Verify ACL policy loaded

- P1.T4.S4: Tag existing raspi nodes (skip if re-registering in Steps 5-6)

- P1.T4.S5: Configure raspi-vlan10-D (SSH to device)

- P1.T4.S6: Configure raspi-vlan10-E (SSH to device)

- P1.T4.S7: Verify end-to-end from a mesh client (e.g., Mac)

- P1.T4.S8: Update plan status

- P1.T4.S9: Sync Hop blog

- P1.T4.S10: Sync runbook
