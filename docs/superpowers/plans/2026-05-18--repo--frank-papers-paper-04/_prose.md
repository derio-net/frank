# The Frank Papers — Paper 04: Distributed Storage on Bare Metal

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Not Started

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete (scripts,
shortcodes, dossier gate, `agents/skills/papers/SKILL.md`). Paper 00 published
— series Phase 1 is open, and this is the second Paper to publish (publish
order: `00 → 10 → 04 → ...`).

Paper 04 is the first full-shape capability Paper to land in the series: 2400–4200
words, the standard skeleton (§1 capability → §2 landscape → §3 architecture
per vendor → §4 scale → §5 Frank's choice → §6 generalization → §7 roadmap),
and the first Paper that exercises every shortcode and diagram type at production
size.

The capability question is: *if you want PVCs on bare metal that survive a node
loss, who do you trust to keep your bytes alive?* The vendor space splits along
two axes: centralized (Ceph-style object/block/file unified) vs distributed-
replicated (Longhorn-style per-volume mirror), and OSS vs commercial. Six
candidates make the landscape, with **Longhorn** as Frank's case study —
three replicas across three control-plane nodes, default StorageClass, and a
handful of scars that turned out to be load-bearing for the series voice.

The scars are the point. RWO PVC + RollingUpdate deadlock. The orphan
`rollingUpdate:` block that Helm wouldn't clear. SOPS-encrypted Secrets that
must NOT be ArgoCD-managed. ESO's empty-`data: []` admission rejection.
These aren't decorations on the §5 narrative — they're why the §6 decision
tree has the leaves it does.

## Phase 1: Dossier construction

Six vendors, ≥5 primary sources across ≥3 type values, ≥3 Frank artefacts
across ≥2 kinds, the named gap on TCO methodology at homelab scale, and the
counter-argument that managed cloud storage erases the operational tax.
Parallel subagents per vendor are appropriate — one each for Longhorn,
Rook-Ceph, OpenEBS Mayastor, Piraeus/LINSTOR, Portworx, and local-path-
provisioner — with a merger pass to consolidate.

## Phase 2: Gate validation

Run `validate-dossier.py`. Human gate: author reviews the named gap and the
counter-argument. The counter to nail: *"managed cloud storage at small scale
is cheaper per-GB and erases the operational tax — why doesn't that win for
Frank?"* Same shape as Paper 00's answer (Frank is a learning platform), but
applied to the storage capability specifically.

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. Section order is fixed:

- TL;DR (≤150 words) — write last
- §1 The capability (200–350 words) + `flowchart LR` stack-position diagram
- §2 The landscape (400–600 words) + `{{< papers/landscape >}}` + `{{< papers/capability-matrix >}}` reading from `data/vendors.yaml`
- §3 How each option handles the hard part (800–1400 words) + one `flowchart TD` per vendor with shared visual language
- §4 What scale changes (300–600 words) + benchmark callouts (NVMe latency, replica count vs throughput, the "5-node minimum for healthy Ceph" rule)
- §5 Frank's choice, and what happened (300–600 words) + 1–3 `{{< papers/scar >}}` callouts (RWO deadlock, SSA discipline, ESO empty-data)
- §6 When Frank's answer doesn't generalize (200–400 words) + decision flowchart, ≤4 leaves
- §7 Roadmap & where this space is going (200–400 words)
- §8 References — auto-rendered from frontmatter

## Phase 4: Media fill

Per-paper cover: Frank examining a column of spinning replica disks with a
skeptical / weighing expression, thin black tie, round reading glasses.
Mermaid diagrams: §1 stack position, §2 landscape (quadrantChart) +
capability matrix, §3 four-to-six architecture flowcharts, §6 decision tree.
At least one Longhorn UI screenshot from `192.168.55.201` showing 3-replica
healthy state.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster — first-person plural or third-person
cluster, not academic). TL;DR ≤150 words written last. Dossier-link rendering
check (use either inline shortcode OR rely on automatic injection — not both).
Set `draft: false`, `status: published`. CI deploys via the existing blog
pipeline.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: update `_index.md`, verify the
auto-rendered cross-link chips appear on Building 03-storage and Operating
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
