---
paper: 08-backup-dr
status: ready
---

## Vendors in scope (≥3, typically 4–6)
- name: Velero
  positioning: "VMware/CNCF — Kubernetes-native API-object backup with CSI/restic plugins for PVC data; the default answer when people say 'Kubernetes backup'."
  primary_url: "https://velero.io/docs/main/"
- name: Longhorn (native backup target)
  positioning: "Rancher/CNCF — distributed block-storage with built-in BackupTarget + RecurringJob; volume-level snapshots shipped to S3 or NFS with no extra control plane."
  primary_url: "https://longhorn.io/docs/latest/snapshots-and-backups/"
- name: Kasten K10 (by Veeam)
  positioning: "Commercial application-aware backup — policy engine, RBAC, audit trail, blueprint hooks for app-consistent snapshots. Veeam acquisition in 2020."
  primary_url: "https://docs.kasten.io/latest/"
- name: TrilioVault for Kubernetes
  positioning: "Commercial application-centric backup — Trilio's K8s product; ITSM/SIEM integrations, multi-cloud DR orchestration."
  primary_url: "https://docs.trilio.io/kubernetes/"
- name: restic
  positioning: "Filesystem-level content-addressed backup with deduplication; what Velero's File-System Backup mode uses under the hood for PVC content."
  primary_url: "https://restic.readthedocs.io/en/stable/"
- name: rclone + cron (homemade)
  positioning: "The anti-pattern baseline — periodic file sync to S3, no API-object capture, no consistency guarantee, no restore tooling. Cheap until you need it."
  primary_url: "https://rclone.org/docs/"

## Primary sources (≥5, ≥3 distinct type values)
- title: "Velero — How Velero Works"
  type: vendor-docs
  url: "https://velero.io/docs/main/how-velero-works/"
  quoted_passages:
    - "Each Velero operation – on-demand backup, scheduled backup, restore – is a custom resource, defined with a Kubernetes Custom Resource Definition (CRD) and stored in etcd."
    - "Velero also includes controllers that process the custom resources to perform backups, restores, and all related operations."
  relevance: "Vendor's authoritative description of Velero's architecture as a controller-driven backup system that captures Kubernetes API objects via CRDs and stores them alongside volume snapshots. Grounds the §3 architecture diagram for Velero and the §5 'why Frank skips Velero' framing — every operation Velero captures is also captured by ArgoCD + git, leaving only PVC data to handle."

- title: "Longhorn — Concepts: Backups and Secondary Storage"
  type: vendor-docs
  url: "https://longhorn.io/docs/latest/concepts/"
  quoted_passages:
    - "A backup is a snapshot copy that is stored in a secondary storage (NFS or S3-compatible object store) outside of the Longhorn cluster. Backups are designed for the disaster recovery purpose."
    - "Longhorn uses a unique mechanism to construct each backup at the block level. Each backup consists of a metadata file and the data blocks. If a data block is already saved in the secondary storage, this data block will not be transferred again."
  relevance: "Definitive statement that Longhorn's backup model is block-level, deduplicated against the BackupStore, and lives outside the Longhorn cluster on S3 or NFS. This is the architectural fork that distinguishes Longhorn-native from Velero+restic — the dedup is at the volume-block layer, owned by the storage driver, not bolted on by a separate backup controller. Underwrites the §2 capability matrix, the §3 Longhorn diagram, and the §5 'no extra control plane' claim."

- title: "Kubernetes blog — Kubernetes 1.20: Volume Snapshot Moves to GA"
  type: paper
  url: "https://kubernetes.io/blog/2020/12/10/kubernetes-1.20-volume-snapshot-moves-to-ga/"
  quoted_passages:
    - "The Kubernetes Volume Snapshot feature is now GA in Kubernetes v1.20. It was introduced as alpha in Kubernetes v1.12, followed by a second alpha with breaking changes in Kubernetes v1.13, and promotion to beta in Kubernetes v1.17."
    - "Volume snapshots provide Kubernetes users with a standardized way to copy a volume's contents at a particular point in time without creating an entirely new volume. This functionality enables, for example, database administrators to backup databases before performing edit or delete modifications."
  relevance: "Canonical announcement that the CSI VolumeSnapshot API graduated to GA — the cross-vendor primitive every modern backup tool now consumes. Anchors the §2 axis 'volume-only ↔ application-aware' and the §7 roadmap claim that CSI VolumeSnapshot is becoming the lingua franca and that the divide between storage-native backup (Longhorn) and storage-agnostic backup (Velero, Kasten) is narrowing."

- title: "restic — Design and References"
  type: vendor-docs
  url: "https://restic.readthedocs.io/en/stable/100_references.html"
  quoted_passages:
    - "restic uses content-defined chunking and deduplication. Each file is split into variable-sized chunks and the SHA-256 hash of each chunk is used to identify it; identical chunks are stored only once."
    - "The repository's data is stored encrypted using AES-256 in counter mode. The encryption keys are derived from a user-provided password using scrypt."
  relevance: "Vendor description of restic's content-addressed, deduplicated, encrypted-at-rest data model — the design that Velero's File-System Backup mode inherits and that determines why §4 calls out deduplication ratios as a load-bearing scale axis. Underwrites the §3 restic diagram and the §6 'offline-resilient / paranoid' decision-tree leaf."

- title: "Frank — Longhorn backup gotchas (NFS mount-string bug, RecurringJob schema, SOPS-secrets-out-of-band)"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/agents/rules/frank-gotchas.md"
  quoted_passages:
    - "SOPS-encrypted secrets must NOT be ArgoCD-managed; apply out-of-band from `secrets/`."
    - "RWO PVC + RollingUpdate deadlocks; use `strategy: Recreate`."
    - "ESO: empty `data: []` is rejected; delete the ExternalSecret if all keys are removed."
  relevance: "Frank's own running postmortem registry — concrete operational scars accumulated while running Longhorn-native backup to Cloudflare R2 in production for this learning platform. Provides source-of-truth dates and recovery commands for the §5 scar callouts on the SOPS-out-of-band requirement, the RWO restore-order constraint, and the dependency-ordering load-bearing for any DR runbook."

- title: "Longhorn issue #11412 — NFS BackupTarget generates host/path instead of host:/path"
  type: postmortem
  url: "https://github.com/longhorn/longhorn/issues/11412"
  quoted_passages:
    - "remote share not in 'host:dir' format"
    - "Fix targeted for Longhorn v1.13.0."
  relevance: "Upstream bug report and triage thread for the Longhorn 1.11 NFS mount-string defect that disabled Frank's local-first restore path. Provides the canonical incident reference for §5 Scar 2 and the §7 roadmap claim that the NAS-target axis is gated on Longhorn v1.13.0 shipping. Type: postmortem, since it documents a confirmed defect, its triage, and its fix-version commitment."

- title: "Longhorn issue #11392 — RecurringJob has no spec.backupTargetName field"
  type: postmortem
  url: "https://github.com/longhorn/longhorn/issues/11392"
  quoted_passages:
    - ".spec.backupTargetName: field not declared in schema"
  relevance: "Upstream issue documenting the Longhorn 1.11 CRD schema gap that prevents per-RecurringJob target selection. All RecurringJobs in 1.11 target the `default` BackupTarget; there is no per-job routing. Anchors the §5 Scar 3 callout and the §7 roadmap note that Frank's manifests keep the original two-target names (`daily-nas` / `weekly-r2`) as documentation of intent."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "apps/longhorn/manifests/backup-target-default.yaml"
  date: 2026-03-08
  demonstrates: "Frank's live S3-to-R2 BackupTarget: spec.backupTargetURL s3://frank-longhorn-backups@auto/ with credentialSecret longhorn-r2-secret referencing the out-of-band SOPS-applied Secret. The @auto region placeholder is what makes this work with Cloudflare R2's custom endpoint — the actual endpoint is supplied via the Secret's AWS_ENDPOINTS field. This is the file ArgoCD reconciles; it is also the file that fails the entire backup pipeline if the Secret is missing, which is why the SOPS-out-of-band scar is load-bearing for DR."

- kind: yaml
  path_or_url: "apps/longhorn/manifests/recurring-job-weekly.yaml"
  date: 2026-03-08
  demonstrates: "Live RecurringJob for the weekly schedule (Sunday 03:00 UTC, retain 4) targeting the default BackupTarget (which currently means R2 — see the §5 RecurringJob-schema scar). Names daily-nas and weekly-r2 are kept as documentation of intent — when Longhorn v1.13.0 ships and the NFS target re-enables and backupTargetName lands as a per-job field, the routing snaps into shape with no manifest churn beyond uncommenting the NAS target."

- kind: incident
  path_or_url: "apps/longhorn/manifests/backup-target-nas.yaml"
  date: 2026-03-08
  demonstrates: "The Longhorn 1.11 NFS mount-string bug, made architectural: the entire file is commented out, with a header pointing at GH issue #11412 and the targeted Longhorn v1.13.0 fix. The mount command Longhorn generates is mount -t nfs4 ... 192.168.50.42/volume1/frank-backup /var/... — RFC 2224 requires host:/path, with a colon. No backport, no workaround. The NAS target is the local-first restore axis that does not exist on Frank in 2026, and the commented-out file is the documentation of why."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md"
  date: 2026-03-08
  demonstrates: "The SOPS-encrypted-Secrets-cannot-be-ArgoCD-managed gotcha. ArgoCD's ServerSideApply=true rejects the .sops field as schema-invalid. The Secret that lets Longhorn talk to R2 lives at secrets/longhorn/r2-secret.yaml, encrypted in git, and is applied out-of-band with sops --decrypt | kubectl apply -f -. For DR this is load-bearing: the secret that lets the backup tool read its own bucket is itself a thing you must restore first. The disaster-recovery runbook has a 'before you do anything else' header that no other procedure on Frank has — we are not Velero-restoring our way out of this; we are sops-decrypting our way back in."

- kind: yaml
  path_or_url: "blog/content/docs/building/08-backup/index.md"
  date: 2026-03-08
  demonstrates: "The original building-08 post — the narrative version of the Longhorn → R2 deployment, with all three Longhorn 1.11 gotchas (SOPS-out-of-band, RecurringJob schema, NFS mount-string) written up alongside the working-state evidence (BackupTarget AVAILABLE=true, recovery-point retention, the practical RTO table). The post is the structured artefact this Paper compresses into §5; the Paper is the landscape view that this post implicitly assumed."

## Diagrams planned
- landscape:
    x_axis: "Volume-only ↔ Application-aware"
    y_axis: "Adds control plane ↔ No extra control plane"
    vendors_plotted: ["Velero", "Longhorn (native)", "Kasten K10", "TrilioVault", "restic", "rclone + cron"]
- architecture_comparison:
    vendors: ["Velero", "Longhorn (native)", "Kasten K10", "TrilioVault", "restic"]
- decision_tree:
    leaves: 4
    description: "Question: who owns the restore, and against what artefact? Branches on can-you-reinstall-from-git (dev/sandbox: no backup needed) and have-you-got-GitOps-coverage-of-API-objects (yes: Longhorn-native suffices; no: need application-aware capture), terminating in: no backup (GitOps reapply), Longhorn-native + S3 (Frank's pick), Kasten K10 / TrilioVault (production with regulated state), restic to NAS + offsite encrypted copy (offline-resilient / paranoid)."

## Named gaps (≥1)
- "No public benchmark exists on the honest cost of a restore-from-scratch DR drill at small-cluster scale — the hours-per-quarter spent enumerating bootstrap secrets, re-applying them in the correct order, waiting for Longhorn to re-attach replicas, sequencing workload scale-up to respect strategy Recreate, verifying app state matches expectations. Published comparisons measure backup success rate, restore wall-clock for a single volume, or feature matrices (does Vendor X support application-aware hooks?). None measure how long it takes a competent operator who has never restored this cluster before to bring it back up from cold storage, and how many of the steps were re-discovered live during the drill. The single most decision-relevant number for any backup choice — your actual RTO in practice, not in the marketing material — does not exist as published work."

## Counter-arguments considered (≥1)
- "For a production cluster with regulated workloads (PII, PCI, HIPAA) or any team without 100% GitOps coverage of their Kubernetes API objects, Kasten K10 (or TrilioVault) is the correct answer — application-aware blueprints, RBAC on restore operations, audit trail, multi-cluster DR orchestration. Why doesn't that win for Frank? Answer: same shape as Paper 14. Frank is fully GitOps-managed; every Deployment, Service, ConfigMap, and CRD is in git and restored by ArgoCD in under ten minutes. The K8s API-object backup that Velero or Kasten provides duplicates work that ArgoCD already does. What's left to protect is PVC contents and a small set of bootstrap secrets — both of which Longhorn's native backup target plus a documented out-of-band SOPS-apply step handle, at a cost of zero additional control-plane components. For a team without GitOps coverage, that calculus inverts and Kasten wins on the merits; for Frank, paying a Veeam contract to back up YAML that's already in git would be the bug, not the fix."
