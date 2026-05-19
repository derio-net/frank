# The Frank Papers — Paper 02: Immutable OS & Declarative Machines

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Complete (2026-05-19) — Paper 02 published; series Phase 1 continues.

**Prerequisite:** Phase 0 (`2026-05-16--repo--frank-papers-phase-0`) complete (scripts, shortcodes, dossier gate, `agents/skills/papers/SKILL.md`). Paper 00 (prologue), Paper 10 (inference), Paper 04 (storage), and Paper 11 (identity) already published — series Phase 1 is open, and this is the eighth Paper to publish in decision-weight order (`00 → 10 → 04 → 11 → 14 → 06 → 07 → 02 → ...`).

Paper 02 sits at the foundation of the cluster's stack: the operating system that runs on every node, and the machine-config story for getting it there. The capability question is: *if you're going to run Kubernetes on hardware you own, what OS keeps the nodes from drifting — and how do you re-deploy a node from zero without ever logging into it?*

The vendor space splits along two axes: how the OS handles upgrades (transactional/atomic versus traditional in-place package install), and how the OS is configured (API-driven declarative versus image-baked Ignition versus config-management overlay). Six candidates make the landscape, with **Talos Linux** as Frank's case study — every node, control-plane and worker alike, runs Talos under Sidero Omni, with machine config rendered from YAML patches in `patches/`.

The scars are the point. `talosctl apply-config --config-patch` rebuilds the base file, not the running config. The Hop single-node cluster's `allowSchedulingOnControlPlanes: true` requirement. The GPU layer needed an entire separate plan (`gpu--operator-talos-fix`) because Talos's immutable kernel-module model refused to play along with NVIDIA's stock validator. These aren't decorations on the §5 narrative — they're why §6's decision tree has the leaves it does.

## Phase 1: Dossier construction

Six vendors, ≥5 primary sources across ≥3 type values, ≥3 Frank artefacts across ≥2 kinds, the named gap on day-2 ops cost at homelab scale, and the counter-argument that "Ubuntu Server + Ansible is still the safest default for most teams." Parallel research per vendor is appropriate — one each for Talos, Fedora CoreOS, Flatcar, Bottlerocket, Ubuntu Core, and the mutable-distro-plus-Ansible baseline — with a merger pass to consolidate the dossier.

## Phase 2: Gate validation

Run `validate-dossier.py`. Author reviews the named gap and the counter-argument. The counter to nail: *"mutable distros + good Ansible is the path 90% of teams should take — why doesn't that win for Frank?"* Same shape as Paper 00's framing (Frank is a learning platform — the scars are the asset), applied to the OS capability specifically.

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. TL;DR (≤150 words) written last. §1 capability + stack-position diagram. §2 landscape (quadrantChart on "mutable↔immutable" × "config-mgmt↔API-driven") + capability matrix from `data/vendors.yaml`. §3 architecture comparison per vendor (≥4 diagrams in shared visual language). §4 scale (what changes at 1 node, 10 nodes, 100 nodes). §5 Frank's choice + scar callouts (--config-patch surprise, Hop single-node taint, GPU validation fix). §6 decision tree, ≤4 leaves. §7 roadmap (image-based Linux trends, Talos's API-first model going mainstream, the Bottlerocket/EKS-AMI signal).

## Phase 4: Media fill

Per-paper cover: Frank examining a row of identical immutable-OS server nodes, each carrying the same machine-config rendered as a glowing manifest beside it. Up-close subtle hardware differences (one GPU node, one ARM node, one small board). Approving expression — this is where the abstraction holds. Add `paper-02-cover` to `blog/prompt_for_images.yaml` under the Papers Series Covers block. Render Mermaid diagrams; optional Omni UI screenshot from cluster (placeholder if cluster unavailable from worktree).

## Phase 5: Review + publish

Voice pass: Frank speaks as the cluster, first-person plural ("we learned") or third-person cluster ("Frank chose Talos") — not academic. TL;DR ≤150 words written last. Verify no double-render of the dossier-link shortcode. Set `draft: false`, `status: published`.

## Phase 6: Post-deploy checklist

Standard checklist: update `_index.md` (Paper 02 link in the publish-order list), verify auto-rendered backlink chips appear on Building 02-foundation and Operating 01-cluster-nodes, README is unchanged (Papers series already referenced from Paper 00), no `# manual-operation` blocks → skip `/sync-runbook`, flip plan status to Complete in `_prose.md` and the spec's Implementation Plans table.

## Phase summary

| # | Phase | Depends on |
|---|-------|-----------|
| 1 | Dossier construction | — |
| 2 | Gate validation | 1 |
| 3 | Scaffold + draft | 2 |
| 4 | Media fill | 3 |
| 5 | Review + publish | 4 |
| 6 | Post-deploy checklist | 5 |
