# Backup — Design

**Date:** 2026-03-07

## Overview

Configure persistent volume backups for the Frank cluster using Longhorn's built-in backup functionality. Two backup targets: a local NAS (NFS) for fast restores, and Cloudflare R2 (S3-compatible) for offsite durability.

No Velero — K8s resource manifests are already in git and re-applied by ArgoCD on cluster rebuild. The real data at risk is PVC contents.

## Stack

| Component | Tool | Notes |
|-----------|------|-------|
| Backup engine | Longhorn built-in | Already deployed at 192.168.55.201 |
| Local target | NAS via NFS | Fast restore, on-network |
| Remote target | Cloudflare R2 | S3-compatible, generous free tier, offsite |

No new ArgoCD apps — backup targets and schedules are configured via Longhorn CRs added to `apps/longhorn/manifests/`.

## Architecture

Longhorn supports multiple backup targets via `BackupTarget` CRs. Each volume can have a recurring backup schedule (daily/weekly) defined via `RecurringJob` CRs.

### Backup Targets

**NAS (NFS)**
- Target URL: `nfs://<NAS-IP>/<backup-share-path>`
- Used for: daily backups, fast local restores
- Credential: none required for NFS (mount-based)

**Cloudflare R2 (S3-compatible)**
- Target URL: `s3://<bucket-name>@auto/` (R2 uses `auto` as region)
- Endpoint override: `https://<account-id>.r2.cloudflarestorage.com`
- Used for: weekly backups, offsite disaster recovery
- Credential: R2 API token stored as a K8s Secret (SOPS-encrypted in git, or via Infisical after secrets layer)

### Recurring Jobs

| Job | Schedule | Target | Retain |
|-----|----------|--------|--------|
| `daily-nas` | Daily 02:00 | NAS | 7 snapshots |
| `weekly-r2` | Weekly Sunday 03:00 | R2 | 4 snapshots |

Jobs are applied as `RecurringJob` CRs and assigned to volume groups via `RecurringJobSelector` labels.

## Manifests

Added to `apps/longhorn/manifests/`:
- `backup-target-nas.yaml` — NFS BackupTarget CR
- `backup-target-r2.yaml` — R2 BackupTarget CR + Secret
- `recurring-job-daily.yaml` — Daily NAS RecurringJob
- `recurring-job-weekly.yaml` — Weekly R2 RecurringJob

## Exposure

No new UI — Longhorn UI already at `192.168.55.201`. Backup status, snapshots, and restore operations are all managed from there.

## Blog Post

**Title:** "Backup: Longhorn to NAS and Cloudflare R2"

**Angle:** Why Velero isn't needed when you're GitOps-first. Walk through Longhorn's backup architecture (snapshots vs backups), configure dual targets, show a backup running in the Longhorn UI, demonstrate a volume restore. Highlight Cloudflare R2 free tier as an accessible offsite option.
