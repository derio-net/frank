# Secure Agent Pod Implementation Plan

## Phase 1: Secure Agent Pod Implementation Plan

### Task 1: Namespace Template

- P1.T1.S1: Create namespace template

- P1.T1.S2: Commit (cfbbf95)

### Task 2: ServiceAccount and RBAC

- P1.T2.S1: Create ServiceAccount + ClusterRoleBinding

- P1.T2.S2: Commit (54a244a)

### Task 3: PVCs

- P1.T3.S1: Create agent-home PVC

- P1.T3.S3: Commit (54a244a — batched with Task 2)

### Task 4: Core Deployment

- P1.T4.S1: Create the deployment manifest (simplified from 4 containers to 1 in fd2039e)

- P1.T4.S2: Commit (c568c65, fix in d78581f)

### Task 5: Services

- P1.T5.S1: Create SSH service

- P1.T5.S2: Create VibeKanban UI service

- P1.T5.S3: Commit (ff37d89)

### Task 6: Cilium Egress Network Policy

- P1.T6.S1: Create the CiliumNetworkPolicy

- P1.T6.S2: Commit (a3aa519 — batched with Task 7)

### Task 7: ExternalSecret (Infisical)

- P1.T7.S1: Create ExternalSecret

- P1.T7.S2: Commit (a3aa519 — batched with Task 6)

### Task 8: ArgoCD Application CR

- P1.T8.S1: Create Application CR template

- P1.T8.S2: Commit (a0a6c15 — batched with Task 9)

### Task 9: SOPS-Encrypted Bootstrap Secrets

- P1.T9.S1: Create the secrets directory placeholder

- P1.T9.S2: Commit placeholder (a0a6c15 — batched with Task 8)

- P1.T9.S3: Create and encrypt secrets (manual — see manual-operation block above)

- P1.T9.S4: Migrate GITHUB_TOKEN to ESO (62b05c7)

### Task 10: Configure Infisical

- P1.T10.S1: Add ANTHROPIC_API_KEY to Infisical project as ANTHROPIC_API_KEY (already existed)

- P1.T10.S2: Verify ExternalSecret syncs after deployment (confirmed: agent-secrets-tier1 created, ESO status True)

### Task 11: Kali Decommission

- P1.T11.S1: Verify secure-agent-pod is fully operational — 6/9 PASS, 1 SKIP (Cilium), 2 pending manual (SSH + VK UI via Tailscale)

- P1.T11.S2: Scale down Kali

- P1.T11.S3: Remove Kali manifests and ArgoCD templates (d5b6901)

- P1.T11.S4: Update infrastructure docs (d5b6901)

- P1.T11.S5: Commit (d5b6901)

- P1.T11.S6: Clean up Kali namespace (manual) — PVC, deployment, service, secrets, configmap, namespace all deleted

### Task 12: Verification

- P1.T12.S1: Non-root — `uid=1000(claude) gid=1000(claude)`

- P1.T12.S2: No sudo — `sudo not found`

- P1.T12.S3: Egress blocked — SKIP: Cilium FQDN policy temporarily disabled (Cilium 1.17 LRU bug)

- P1.T12.S4: Egress allowed — HTTP 404 from Anthropic (connection succeeds)

- P1.T12.S5: Secrets injected — `ANTHROPIC_API_KEY` set via ESO, no `.env` file

- P1.T12.S6: VibeKanban healthy — process running, HTTP 200 on port 8081 (`PORT=8081`, `HOST=0.0.0.0`)

- P1.T12.S7: PVC persistence — SSH host keys persist across pod restarts

- P1.T12.S8: VibeKanban UI access — confirmed via Tailscale at `http://192.168.55.218:8081`

- P1.T12.S9: SSH access — confirmed: `ssh claude@192.168.55.215`
