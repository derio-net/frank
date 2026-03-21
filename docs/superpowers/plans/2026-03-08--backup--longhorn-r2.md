# Backup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Configure Longhorn backup targets (NFS NAS + Cloudflare R2) and recurring job schedules via CRs committed to git and applied by the existing `longhorn-extras` ArgoCD app.

**Architecture:** Four manifests added to `apps/longhorn/manifests/` are picked up automatically by the existing `longhorn-extras` ArgoCD Application (path-based sync). The R2 credentials secret is SOPS-encrypted before commit; if ArgoCD SOPS decryption is not configured, the secret is applied manually via kubectl and ArgoCD is told to ignore Secret data diffs. The existing `longhorn-extras` Application CR needs one edit to add `ignoreDifferences` for the R2 Secret.

**Tech Stack:** Longhorn 1.11 CRDs (`longhorn.io/v1beta2`), Kubernetes Secrets, SOPS/age encryption, ArgoCD, Cloudflare R2 (S3-compatible), NFS
**Status:** Deployed

---

## Prerequisites (gather before starting)

You need four pieces of information before writing any manifests. Collect them now and keep them in a local scratch file (do not commit plaintext secrets).

| Item | Where to find it | Placeholder used in plan |
|------|-----------------|--------------------------|
| NAS IP address | Your NAS admin UI or `nmap -sn 192.168.55.0/24` | `<NAS-IP>` |
| NAS NFS export path for backup share | NAS admin UI → File Services → NFS exports | `<NAS-BACKUP-SHARE>` |
| Cloudflare R2 account ID | Cloudflare dashboard → R2 → overview page URL (`/r2/overview` shows account ID) | `<CF-ACCOUNT-ID>` |
| R2 bucket name | Create a new bucket in R2 called e.g. `frank-longhorn-backups` | `<R2-BUCKET>` |
| R2 access key ID | R2 → Manage R2 API Tokens → Create API Token (Object Read & Write on specific bucket) | `<R2-ACCESS-KEY>` |
| R2 secret access key | Same token creation page — copy immediately, shown once | `<R2-SECRET-KEY>` |

**Verify NFS is reachable from the cluster before committing anything:**

```bash
# Run from any cluster node (or from a debug pod)
kubectl run nfs-test --rm -it --image=alpine --restart=Never -- \
  sh -c "apk add nfs-utils && showmount -e <NAS-IP>"
```

Expected: the `<NAS-BACKUP-SHARE>` export is listed.

---

## Task 1: Create the NAS (NFS) BackupTarget manifest

**Files:**
- Create: `apps/longhorn/manifests/backup-target-nas.yaml`

**Step 1: Write the manifest**

```yaml
# apps/longhorn/manifests/backup-target-nas.yaml
apiVersion: longhorn.io/v1beta2
kind: BackupTarget
metadata:
  name: nas
  namespace: longhorn-system
spec:
  backupTargetURL: "nfs://<NAS-IP>/<NAS-BACKUP-SHARE>"
  credentialSecret: ""
  pollInterval: "5m"
```

Replace `<NAS-IP>` and `<NAS-BACKUP-SHARE>` with the values collected in Prerequisites. Example: `nfs://192.168.55.10/volume1/longhorn-backup`.

**Step 2: Verify the file was written correctly**

```bash
cat apps/longhorn/manifests/backup-target-nas.yaml
```

Expected: the NFS URL is filled in with real values (no `<...>` placeholders).

---

## Task 2: Create the R2 credentials Secret (plaintext then SOPS-encrypt)

**Files:**
- Create: `apps/longhorn/manifests/r2-secret.yaml`

**Step 1: Write the plaintext secret**

```yaml
# apps/longhorn/manifests/r2-secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: longhorn-r2-secret
  namespace: longhorn-system
type: Opaque
stringData:
  AWS_ACCESS_KEY_ID: "<R2-ACCESS-KEY>"
  AWS_SECRET_ACCESS_KEY: "<R2-SECRET-KEY>"
  AWS_ENDPOINTS: "https://<CF-ACCOUNT-ID>.r2.cloudflarestorage.com"
```

Replace all three `<...>` placeholders with your actual R2 credentials.

**Step 2: Encrypt with SOPS**

```bash
sops --encrypt --in-place apps/longhorn/manifests/r2-secret.yaml
```

Expected: the file now shows SOPS ciphertext in the `stringData` block. The `.sops.yaml` config (`encrypted_regex: ^(data|stringData)$`) ensures only the secret data is encrypted, not the metadata.

**Step 3: Verify encryption worked**

```bash
head -30 apps/longhorn/manifests/r2-secret.yaml
```

Expected: `stringData` values are encrypted ciphertext strings, not plaintext. The `metadata.name`, `kind`, and `apiVersion` are still readable.

**Step 4: Check if ArgoCD SOPS decryption is configured**

```bash
kubectl get cm -n argocd argocd-cm -o yaml | grep -i sops
kubectl get cm -n argocd argocd-cm -o yaml | grep -i ksops
```

- **If SOPS/KSOPS plugin entries appear:** ArgoCD can decrypt automatically. Continue to Task 3.
- **If nothing appears:** ArgoCD cannot decrypt SOPS secrets from raw manifest paths. Use the manual fallback instead:

  ```bash
  # Decrypt locally and apply directly (ArgoCD will track the resource but ignore data diffs)
  sops --decrypt apps/longhorn/manifests/r2-secret.yaml | kubectl apply -f -
  ```

  Then continue to Task 3 — the `ignoreDifferences` you add in Task 6 will prevent ArgoCD from fighting over the Secret data.

---

## Task 3: Create the R2 BackupTarget manifest

**Files:**
- Create: `apps/longhorn/manifests/backup-target-r2.yaml`

**Step 1: Write the manifest**

```yaml
# apps/longhorn/manifests/backup-target-r2.yaml
apiVersion: longhorn.io/v1beta2
kind: BackupTarget
metadata:
  name: r2
  namespace: longhorn-system
spec:
  backupTargetURL: "s3://<R2-BUCKET>@auto/"
  credentialSecret: "longhorn-r2-secret"
  pollInterval: "5m"
```

Replace `<R2-BUCKET>` with your actual bucket name (e.g. `frank-longhorn-backups`). The `@auto` region is correct for Cloudflare R2 — R2 does not use AWS regions.

**Step 2: Verify the file**

```bash
cat apps/longhorn/manifests/backup-target-r2.yaml
```

Expected: real bucket name, no placeholders.

---

## Task 4: Create the daily recurring job (NAS)

**Files:**
- Create: `apps/longhorn/manifests/recurring-job-daily.yaml`

**Step 1: Write the manifest**

```yaml
# apps/longhorn/manifests/recurring-job-daily.yaml
apiVersion: longhorn.io/v1beta2
kind: RecurringJob
metadata:
  name: daily-nas
  namespace: longhorn-system
spec:
  cron: "0 2 * * *"
  task: "backup"
  groups:
    - default
  retain: 7
  concurrency: 2
  backupTargetName: nas
```

- `cron: "0 2 * * *"` — daily at 02:00
- `retain: 7` — keep 7 backup points (one week of dailies)
- `groups: [default]` — applies to all volumes in the `default` recurring job group
- `backupTargetName: nas` — uses the NAS BackupTarget (Longhorn 1.7+ field)

**Step 2: Verify the file**

```bash
cat apps/longhorn/manifests/recurring-job-daily.yaml
```

**Step 3: Verify the `backupTargetName` field is supported**

```bash
source .env
kubectl get crd recurringjobs.longhorn.io -o jsonpath='{.spec.versions[?(@.name=="v1beta2")].schema.openAPIV3Schema.properties.spec.properties.backupTargetName}' | head -c 200
```

Expected: non-empty output describing the `backupTargetName` field. If this field is not in the CRD schema, check the Longhorn 1.11 release notes — you may need to omit `backupTargetName` and rely on the `default` backup target being set to NAS in the Longhorn settings instead.

---

## Task 5: Create the weekly recurring job (R2)

**Files:**
- Create: `apps/longhorn/manifests/recurring-job-weekly.yaml`

**Step 1: Write the manifest**

```yaml
# apps/longhorn/manifests/recurring-job-weekly.yaml
apiVersion: longhorn.io/v1beta2
kind: RecurringJob
metadata:
  name: weekly-r2
  namespace: longhorn-system
spec:
  cron: "0 3 * * 0"
  task: "backup"
  groups:
    - default
  retain: 4
  concurrency: 1
  backupTargetName: r2
```

- `cron: "0 3 * * 0"` — every Sunday at 03:00
- `retain: 4` — keep 4 weekly backups (one month)
- `concurrency: 1` — serialise R2 uploads to avoid rate-limit issues on the free tier

**Step 2: Verify the file**

```bash
cat apps/longhorn/manifests/recurring-job-weekly.yaml
```

---

## Task 6: Add `ignoreDifferences` to the longhorn-extras Application

This prevents ArgoCD from flagging the SOPS-encrypted Secret as OutOfSync (its on-disk representation in git differs from the decrypted on-cluster representation).

**Files:**
- Modify: `apps/root/templates/longhorn-extras.yaml`

**Step 1: Read the current file**

Current content of `apps/root/templates/longhorn-extras.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: longhorn-extras
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/longhorn/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: longhorn-system
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
```

**Step 2: Add sync options and ignoreDifferences**

The updated file should be:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: longhorn-extras
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/longhorn/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: longhorn-system
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      name: longhorn-r2-secret
      namespace: longhorn-system
      jsonPointers:
        - /data
```

**Step 3: Verify the edit**

```bash
cat apps/root/templates/longhorn-extras.yaml
```

Expected: `ignoreDifferences` and `syncOptions` blocks are present.

---

## Task 7: Commit and push

**Step 1: Stage all new/modified files**

```bash
git add apps/longhorn/manifests/backup-target-nas.yaml \
        apps/longhorn/manifests/backup-target-r2.yaml \
        apps/longhorn/manifests/r2-secret.yaml \
        apps/longhorn/manifests/recurring-job-daily.yaml \
        apps/longhorn/manifests/recurring-job-weekly.yaml \
        apps/root/templates/longhorn-extras.yaml
```

**Step 2: Verify the secret is encrypted before committing**

```bash
git diff --cached apps/longhorn/manifests/r2-secret.yaml | grep "AWS_" | head -5
```

Expected: the values shown are SOPS ciphertext, NOT plaintext credentials. If you see plaintext, stop and re-encrypt with `sops --encrypt --in-place apps/longhorn/manifests/r2-secret.yaml` before continuing.

**Step 3: Commit**

```bash
git commit -m "feat(backup): add Longhorn backup targets (NAS + R2) and recurring jobs"
```

**Step 4: Push**

```bash
git push
```

**Step 5: Watch ArgoCD sync**

```bash
source .env
argocd app wait longhorn-extras --health --sync --port-forward --port-forward-namespace argocd --timeout 120
```

Expected: `Application 'longhorn-extras' is health and synced`.

Also check the root app re-renders with the updated longhorn-extras template:

```bash
argocd app wait root --health --sync --port-forward --port-forward-namespace argocd --timeout 120
```

---

## Task 8: Verify backup targets in Longhorn UI

**Step 1: Open Longhorn UI**

Navigate to `http://192.168.55.201` → **Backup** in the top nav.

**Step 2: Check backup targets appear**

You should see two entries:
- `nas` — Status: `Available`
- `r2` — Status: `Available`

If either shows `Error`, click it to see the error message. Common issues:
- NAS: NFS mount fails → check NAS IP, share path, and that NFS is exported without IP restrictions
- R2: credentials wrong → check `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINTS` in the secret

**Step 3: Verify recurring jobs**

In the Longhorn UI → **Recurring Job** → confirm `daily-nas` and `weekly-r2` appear with correct schedules.

**Step 4: Trigger a manual backup to test the NAS target**

```bash
source .env
# Pick any existing PVC — e.g. the VictoriaMetrics PVC
kubectl get pvc -n monitoring
```

In the Longhorn UI → **Volumes** → select a volume → **Create Backup** → choose target `nas`. Wait for status to change to `Completed`.

Expected: backup appears in Longhorn UI → **Backup** → `nas` target with size and timestamp.

**Step 5: Test restore (optional but recommended)**

In Longhorn UI → **Backup** → select the backup → **Restore** → restore to a new volume named `test-restore-YYYYMMDD`. After restore completes, delete the test volume. This confirms the backup is not corrupt.

---

## Task 9: Write the blog post

**Files:**
- Create: `blog/content/posts/08-backup/index.md`
- Create: `blog/content/posts/08-backup/cover.png` (placeholder — image generated separately)

**Step 1: Create the post directory**

```bash
mkdir -p blog/content/posts/08-backup
```

**Step 2: Write the post**

```markdown
---
title: "Backup — Longhorn to NAS and Cloudflare R2"
date: 2026-03-08
draft: false
tags: ["backup", "longhorn", "nfs", "cloudflare-r2", "disaster-recovery"]
summary: "Why Velero isn't needed when you're GitOps-first — configuring Longhorn's dual backup targets with a NAS for fast local restores and Cloudflare R2 for offsite durability."
weight: 9
cover:
  image: cover.png
  alt: "Frank the cluster monster carefully placing backup tapes into a vault labeled NAS and cloud"
  relative: true
---

A Kubernetes cluster without backups is a disaster waiting to happen. Pods crash gracefully. Nodes can be rebuilt. But PVC data — that is the one thing that does not come back from a cluster rebuild unless you explicitly stored it somewhere safe.

Layer 8 addresses this with Longhorn's built-in backup functionality: two targets, two schedules, zero new ArgoCD applications.

## Why Not Velero?

The reflexive answer to "Kubernetes backup" is Velero. It is a fine tool, but it is solving a different problem than what Frank needs.

Velero backs up Kubernetes API objects — Deployments, Services, ConfigMaps, Secrets, PersistentVolumeClaims — and uses volume snapshots or Restic to capture PVC data. This is essential in environments where the cluster configuration is not in source control.

Frank's cluster is GitOps-first. Every Kubernetes resource is committed to git and managed by ArgoCD. If the cluster evaporates, ArgoCD re-applies everything from the repo within minutes. The only data that is genuinely at risk is the _contents_ of PVCs: the VictoriaMetrics time series, Grafana dashboards, and any application data.

Longhorn handles PVC backup natively, with a richer snapshot model than Velero's volume integration, a first-class UI for browsing and restoring individual backups, and no extra control-plane components to maintain. Velero would add complexity without adding value here.

## The Backup Architecture

Longhorn supports multiple backup targets via `BackupTarget` custom resources, with recurring schedules defined via `RecurringJob` CRs. Both are applied through the existing `longhorn-extras` ArgoCD Application, which syncs everything in `apps/longhorn/manifests/`.

No new ArgoCD apps. No new namespaces. Four new manifest files.

### Backup Targets

**NAS (NFS)** — fast local restores, daily schedule:

```yaml
apiVersion: longhorn.io/v1beta2
kind: BackupTarget
metadata:
  name: nas
  namespace: longhorn-system
spec:
  backupTargetURL: "nfs://<NAS-IP>/<backup-share>"
  credentialSecret: ""
  pollInterval: "5m"
```

NFS requires no credentials — access control is handled at the NFS export level on the NAS. Longhorn mounts the NFS share directly and writes backup data as chunked files.

**Cloudflare R2 (S3-compatible)** — offsite durability, weekly schedule:

```yaml
apiVersion: longhorn.io/v1beta2
kind: BackupTarget
metadata:
  name: r2
  namespace: longhorn-system
spec:
  backupTargetURL: "s3://<bucket-name>@auto/"
  credentialSecret: "longhorn-r2-secret"
  pollInterval: "5m"
```

The `@auto` region is the correct value for Cloudflare R2. R2 does not use AWS-style regions — `auto` routes to the geographically closest R2 endpoint. The `credentialSecret` points to a Kubernetes Secret holding the R2 API token, stored SOPS-encrypted in git.

### Why Cloudflare R2?

R2's free tier includes 10 GB storage and 1 million Class A operations per month. For a homelab with a handful of PVCs totalling a few gigabytes of actual data, the monthly bill is zero. The tradeoff: R2 is Cloudflare-hosted, so it is only truly offsite if your NAS and Cloudflare have independent failure modes (they do).

### Recurring Jobs

Two schedules:

| Job | Cron | Target | Retain |
|-----|------|--------|--------|
| `daily-nas` | `0 2 * * *` | NAS | 7 (one week) |
| `weekly-r2` | `0 3 * * 0` | R2 | 4 (one month) |

The daily NAS backup runs at 02:00 (local time) when the cluster is unlikely to be under load. Seven retained snapshots gives a one-week recovery window for the fast-restore path.

The weekly R2 backup runs Sunday at 03:00, an hour after the Saturday nightly NAS backup. Four retained snapshots = four weeks of offsite recovery points.

## Credentials and SOPS

The R2 API token cannot be committed in plaintext. The repo already uses SOPS/age for secret encryption — the `.sops.yaml` config encrypts the `stringData` section of any YAML file matching `*.yaml`.

The workflow:

```bash
# Write plaintext secret, fill in real values
cat > apps/longhorn/manifests/r2-secret.yaml <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: longhorn-r2-secret
  namespace: longhorn-system
type: Opaque
stringData:
  AWS_ACCESS_KEY_ID: "<real-value>"
  AWS_SECRET_ACCESS_KEY: "<real-value>"
  AWS_ENDPOINTS: "https://<account-id>.r2.cloudflarestorage.com"
EOF

# Encrypt before committing
sops --encrypt --in-place apps/longhorn/manifests/r2-secret.yaml
```

The encrypted file is safe to commit — only the `stringData` block is ciphertext; metadata remains readable. ArgoCD is configured to ignore diffs on the Secret's `/data` field, so the on-disk SOPS ciphertext and the decrypted on-cluster Secret coexist without constant OutOfSync alerts.

## Verifying the Setup

After ArgoCD syncs, open the Longhorn UI at `http://192.168.55.201` → **Backup**. Both targets should show status `Available`. The recurring jobs appear under **Recurring Job**.

To confirm the pipeline works end-to-end before relying on it:

1. Select any volume → **Create Backup** → choose target `nas`
2. Wait for status `Completed`
3. From the backup list, select the backup → **Restore** to a new volume
4. Confirm the restored volume mounts and contains expected data
5. Delete the test volume

This takes about five minutes and gives confidence that the backup-to-restore path is not silently broken.

## What Is Protected Now

Every PVC in the `default` recurring job group gets daily NAS backups and weekly R2 backups. The Longhorn default is to assign all volumes to the `default` group unless explicitly overridden. This means:

- VictoriaMetrics 20Gi time-series data — backed up daily
- Grafana 1Gi dashboard persistence — backed up daily
- VictoriaLogs 20Gi log data — backed up daily

Recovery time objective for a full cluster rebuild: ArgoCD re-applies all resources in ~5 minutes. PVC data restore from NAS adds another 10–30 minutes depending on data size. Total RTO from local NAS: under an hour.

Recovery point objective: 24 hours (last daily NAS backup). In the worst case — NAS and cluster lost simultaneously — R2 provides the weekly backup, so RPO degrades to 7 days maximum.

## References

- [Longhorn Backup Documentation](https://longhorn.io/docs/latest/snapshots-and-backups/) — backup target configuration, recurring jobs, restore workflow
- [Cloudflare R2 Documentation](https://developers.cloudflare.com/r2/) — bucket creation, API token scopes, S3 compatibility
- [SOPS Documentation](https://github.com/getsops/sops) — age encryption, `.sops.yaml` config
```

**Step 3: Preview the post locally**

```bash
cd blog && hugo server --buildDrafts --port 1313
```

Open `http://localhost:1313` and confirm the post appears in the list with correct metadata and no rendering errors.

**Step 4: Generate cover image prompt**

Save this prompt to `blog/content/posts/08-backup/cover-prompt.txt` for reference:

```
Frank the cluster monster — a friendly orange creature with antenna and circuit board markings — carefully placing labelled backup tapes/discs into two separate vaults. Left vault is labelled "NAS" with a home network icon. Right vault is labelled "R2" with a cloud and Cloudflare logo. Background is dark server room. Pixel art / retro game style. Warm orange accent lighting.
```

**Step 5: Add a placeholder cover and commit**

If you have a cover image ready:
```bash
cp /path/to/generated-cover.png blog/content/posts/08-backup/cover.png
```

If not, create a placeholder and note it needs to be replaced:
```bash
touch blog/content/posts/08-backup/cover.png  # replace before publishing
```

**Step 6: Commit the blog post**

```bash
git add blog/content/posts/08-backup/
git commit -m "docs(blog): add Phase 8 backup post"
git push
```

---

## Done

At this point:
- Two Longhorn backup targets are active (NAS + R2)
- Daily backups run at 02:00 to NAS, retaining 7 snapshots
- Weekly backups run Sunday 03:00 to R2, retaining 4 snapshots
- R2 credentials are SOPS-encrypted in git
- Blog post documents the architecture and design decisions

---

## Manual Operations

```yaml
# manual-operation
id: backup-r2-sops-secret
layer: backup
app: longhorn
plan: docs/superpowers/plans/2026-03-08--backup--longhorn-r2.md
when: "After Task 2 — after SOPS-encrypting the R2 secret"
why_manual: "SOPS metadata (.sops key) in Secret YAML is rejected by ArgoCD ServerSideApply schema validation; encrypted secrets must live outside ArgoCD-managed paths and be applied out-of-band"
commands:
  - sops --decrypt secrets/longhorn/r2-secret.yaml | kubectl apply -f -
verify:
  - kubectl get secret longhorn-r2-secret -n longhorn-system
status: done
```
