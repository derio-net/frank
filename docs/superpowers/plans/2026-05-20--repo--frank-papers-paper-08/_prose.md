# The Frank Papers — Paper 08: Backup & DR Without a Vendor Contract

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Drafting — Paper 08 implementation in progress on branch `paper-08`.

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete (scripts,
shortcodes, dossier gate, `agents/skills/papers/SKILL.md`). Papers 00, 10, 04,
11, 14, 06, 07, 02 published.

Paper 08 is the ninth capability Paper to land in the series: 2400–4200
words, the standard skeleton (§1 capability → §2 landscape → §3 architecture
per vendor → §4 scale → §5 Frank's choice → §6 generalization → §7 roadmap),
and the first Paper to confront the *backup & disaster recovery* capability —
the part of the stack where the marketing material talks about RTO/RPO and
the operational reality is that you only know whether your backups work
when you restore from scratch, and most teams never do.

The capability question is: *if the cluster's persistent state vanishes
tonight — corrupted volume, accidental `kubectl delete ns`, lost node, full
site loss — who owns the restore, and against what artefact? Who owns the
Kubernetes API objects, who owns the volume contents, who owns the secrets
that aren't in git, and who tests the whole stack end-to-end?* The vendor
space splits along two axes: what gets backed up (volumes only, K8s API
only, both, plus secrets/auth/runbook) and how much you trust your declarative
ground truth (does GitOps replace half the problem, or are you assuming
your config lives in tickets and tribal knowledge?).

Six candidates make the landscape, with **Longhorn's native backup target +
Cloudflare R2** as Frank's case study — a configuration that deliberately
*skips Velero*, because ArgoCD + git already restores every API object on
the cluster, leaving only volume contents and a small set of out-of-band
bootstrap secrets to protect. The scars are the point. A region setting that
silently broke the restore but not the backup. A Longhorn NFS mount-string
bug that disabled the local NAS target for an entire minor version. A
RecurringJob schema that doesn't have a `backupTargetName` field and so
quietly ignores it. SOPS-encrypted secrets that are *deliberately* outside
the backup tool's reach, because they belong to a different recovery flow
that has to run *before* any data is restored. These aren't decorations on
the §5 narrative — they're why the §6 decision tree has the leaves it does.

## Phase 1: Dossier construction

Six vendors, ≥5 primary sources across ≥3 type values, ≥3 Frank artefacts
across ≥2 kinds, the named gap on the absence of an honest "what does a
restore-from-scratch drill actually cost in hours per quarter" measurement,
and the counter-argument that for production with regulated workloads, a
commercial application-aware backup product (Kasten K10, TrilioVault) *is*
the rational choice and Frank's just-Longhorn answer is reckless. Parallel
subagents per vendor are appropriate — one each for Velero, Longhorn,
Kasten K10, TrilioVault, restic, and the "rclone + cron" anti-pattern —
with a merger pass.

## Phase 2: Gate validation

Run `validate-dossier.py`. Human gate: author reviews the named gap and the
counter-argument. The counter to nail: *"for any cluster with regulated
workloads or any team without 100% GitOps coverage, Kasten K10 is the
correct answer — why doesn't that win for Frank?"* Same shape as Paper 04's
framing applied to the backup capability.

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. Section order is fixed:

- TL;DR (≤150 words) — write last
- §1 The capability (200–350 words) + `flowchart LR` stack-position diagram
- §2 The landscape (400–600 words) + `{{< papers/landscape >}}` + `{{< papers/capability-matrix >}}` reading from `data/vendors.yaml`
- §3 How each option handles the hard part (800–1400 words) + one `flowchart TD` per vendor with shared visual language
- §4 What scale changes (300–600 words) + benchmark callouts (snapshot consistency, deduplication ratios, restore wall-clock at TB scale)
- §5 Frank's choice, and what happened (300–600 words) + 1–3 `{{< papers/scar >}}` callouts (Longhorn NFS bug, RecurringJob schema, SOPS-secrets out-of-band)
- §6 When Frank's answer doesn't generalize (200–400 words) + decision flowchart, ≤4 leaves
- §7 Roadmap & where this space is going (200–400 words)
- §8 References — auto-rendered from frontmatter

## Phase 4: Media fill

Per-paper cover: Frank examining a glowing data parcel labelled
`snapshot-2026-05-20` floating away from a rack to an off-cluster archive
box, thin black tie, round reading glasses, cautious expression. The visual
metaphor is *shipping a snapshot off-cluster*. Mermaid diagrams: §1 stack
position, §2 landscape (quadrantChart) + capability matrix, §3 four-to-six
architecture flowcharts, §6 decision tree. At least one Longhorn UI / R2
bucket screenshot captured live from the cluster. Cluster-side captures may
be deferred with `-TODO.png` placeholders if access is unavailable.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster — first-person plural or third-
person cluster, not academic). TL;DR ≤150 words written last. Dossier-link
rendering check (use either inline shortcode OR rely on automatic injection
— not both). Set `draft: false`, `status: published`. CI deploys via the
existing blog pipeline.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: verify _index.md (uses the
papers-roadmap shortcode so no manual list update needed), verify the
auto-rendered cross-link chips appear on Building 08-backup and Operating
02-storage-backups, update README if relevant, set plan status to Complete.

## Phase summary

| # | Phase | Depends on |
|---|-------|-----------|
| 1 | Dossier construction | — |
| 2 | Gate validation | 1 |
| 3 | Scaffold + draft | 2 |
| 4 | Media fill | 3 |
| 5 | Review + publish | 4 |
| 6 | Post-deploy checklist | 5 |
