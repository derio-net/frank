# Phase-to-Layer Naming Convention Rename

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace the "Phase" numbering system with "Layer" domain codes across all plans, specs, docs, skills, and blog posts.

**Architecture:** Layers are architectural/operational domains (gpu, edge, auth, etc.) with short codes. Plans/specs are named `<date>--<layer>--<details>.md`. Blog posts keep sequential reading-order numbers. Roadmap shortcode already uses layers. patches/ directories keep legacy names.

**Tech Stack:** git mv, sed, manual edits
**Status:** Complete

---

## File Structure

| Action | Path | Purpose |
|--------|------|---------|
| Create | `docs/layers.yaml` | Central layer registry |
| Rename | 23 files in `docs/superpowers/plans/` | Plan file renames |
| Rename | 22 files in `docs/superpowers/specs/` | Spec file renames |
| Modify | `CLAUDE.md` | Update naming convention, workflows, commit format |
| Modify | `docs/runbooks/manual-operations.yaml` | Rename `phase` → `layer`, update IDs + plan paths |
| Modify | `.claude/skills/blog-post/SKILL.md` | Update terminology |
| Modify | `.claude/skills/update-readme/SKILL.md` | Update terminology |
| Modify | `.claude/skills/sync-runbook.md` | Update terminology + schema |
| Modify | `README.md` | Update architecture tree comments |
| Modify | ~10 blog posts in `blog/content/building/` | "Phase N" → "Layer N" in narrative |
| Modify | ~2 blog posts in `blog/content/operating/` | Same |

---

## Chunk 1: Create Layer Registry + Rename All Plans/Specs

### Task 1: Create `docs/layers.yaml`

**Files:**
- Create: `docs/layers.yaml`

- [x] **Step 1: Write the layer registry**

```yaml
# Layer Registry — Architectural/operational domains for the Frank cluster
#
# Each layer represents a capability domain. Plans and specs are named:
#   <date>--<layer>--<details>[-design].md
#
# Commit messages use the layer code: fix(gpu): ..., feat(edge): ...
#
# Layer numbers reflect order of introduction (matches roadmap shortcode).
# New layers always get the next number.

layers:
  - code: hw
    number: 1
    name: Hardware & Nodes
    description: Physical hardware, node provisioning, zone topology

  - code: os
    number: 2
    name: OS & Bootstrap
    description: Talos Linux, Sidero Omni, machine config lifecycle

  - code: net
    number: 3
    name: Networking
    description: Cilium CNI, eBPF, L2 LoadBalancer, Hubble

  - code: stor
    number: 4
    name: Storage
    description: Longhorn distributed block storage, StorageClasses

  - code: gpu
    number: 5
    name: GPU Compute
    description: NVIDIA GPU Operator, Intel DRA driver, CDI

  - code: gitops
    number: 6
    name: GitOps
    description: ArgoCD App-of-Apps, drift detection, self-healing

  - code: fun
    number: 7
    name: Fun Stuff
    description: OpenRGB LED control, cosmetic/fun workloads

  - code: obs
    number: 8
    name: Observability
    description: VictoriaMetrics, Grafana, Fluent Bit, alerting

  - code: backup
    number: 9
    name: Backup & DR
    description: Longhorn backups to Cloudflare R2, disaster recovery

  - code: secrets
    number: 10
    name: Secrets Management
    description: Infisical vault, External Secrets Operator

  - code: infer
    number: 11
    name: Local Inference
    description: Ollama, LiteLLM gateway, OpenRouter

  - code: agents
    number: 12
    name: Agentic Control Plane
    description: Sympozium, autonomous coding agents

  - code: auth
    number: 13
    name: Unified Auth
    description: Authentik IdP, OIDC, forward-auth proxy

  - code: tenant
    number: 14
    name: Multi-tenancy
    description: vCluster, disposable experiment clusters

  - code: orch
    number: 15
    name: AI Agent Orchestrator
    description: Paperclip org-chart agents, delegation chains

  - code: media
    number: 16
    name: Media Generation
    description: ComfyUI, GPU Switcher, diffusion models

  - code: edge
    number: 17
    name: Public Edge
    description: Hop cluster, Headscale mesh, Caddy, public blog

  - code: repo
    name: Repository & Tooling
    description: Blog infrastructure, CI, repo restructuring, meta-tasks
```

- [x] **Step 2: Commit**

```bash
git add docs/layers.yaml
git commit -m "feat(repo): add layer registry (docs/layers.yaml)"
```

### Task 2: Rename all plan files

**Files:**
- Rename: 23 files in `docs/superpowers/plans/`

The complete rename mapping:

| Old | New |
|-----|-----|
| `2026-03-02-phase05-argocd-infrastructure.md` | `2026-03-02--gitops--argocd-infrastructure.md` |
| `2026-03-03-phase06-openrgb-led-control.md` | `2026-03-03--fun--openrgb-led-control.md` |
| `2026-03-04-phase04-intel-igpu-stack-mini.md` | `2026-03-04--gpu--intel-igpu-stack-mini.md` |
| `2026-03-06-blog-series.md` | `2026-03-06--repo--blog-series.md` |
| `2026-03-07-phase07-observability.md` | `2026-03-07--obs--observability.md` |
| `2026-03-08-declarative-drift-remediation.md` | `2026-03-08--repo--declarative-drift-remediation.md` |
| `2026-03-08-phase08-backup-impl.md` | `2026-03-08--backup--longhorn-r2.md` |
| `2026-03-08-phase09-secrets-management.md` | `2026-03-08--secrets--infisical-eso.md` |
| `2026-03-09-openrgb-it5701-investigation.md` | `2026-03-09--fun--openrgb-it5701-investigation.md` |
| `2026-03-09-phase04-gpu1-pcie-link-speed-fix.md` | `2026-03-09--gpu--pcie-link-speed-fix.md` |
| `2026-03-09-phase06-openrgb-server-regression-fix.md` | `2026-03-09--fun--openrgb-server-regression-fix.md` |
| `2026-03-09-phase10-local-inference.md` | `2026-03-09--infer--ollama-litellm.md` |
| `2026-03-09-phase11-sympozium.md` | `2026-03-09--agents--sympozium.md` |
| `2026-03-10-phase04-gpu-operator-talos-fix.md` | `2026-03-10--gpu--operator-talos-fix.md` |
| `2026-03-10-phaseXX-coding-agent-infrastructure.md` | `2026-03-10--agents--coding-agent-infrastructure.md` |
| `2026-03-11-phase12-multi-tenancy.md` | `2026-03-11--tenant--vcluster.md` |
| `2026-03-11-phase13-unified-auth.md` | `2026-03-11--auth--authentik.md` |
| `2026-03-13-operating-on-frank-blog-series.md` | `2026-03-13--repo--operating-blog-series.md` |
| `2026-03-14-phase14-paperclip.md` | `2026-03-14--orch--paperclip.md` |
| `2026-03-14-phase15-media-generation.md` | `2026-03-14--media--comfyui-gpu-switcher.md` |
| `2026-03-16-phase15-comfyui-custom-image.md` | `2026-03-16--media--comfyui-custom-image.md` |
| `2026-03-16-phaseXX-hop-public-edge.md` | `2026-03-16--edge--hop-public.md` |
| `2026-03-20-phaseXX-multi-cluster-restructure.md` | `2026-03-20--repo--multi-cluster-restructure.md` |

- [x] **Step 1: Execute all git mv commands for plans**

```bash
cd docs/superpowers/plans
git mv 2026-03-02-phase05-argocd-infrastructure.md 2026-03-02--gitops--argocd-infrastructure.md
git mv 2026-03-03-phase06-openrgb-led-control.md 2026-03-03--fun--openrgb-led-control.md
# ... (all 23 renames)
```

### Task 3: Rename all spec files

**Files:**
- Rename: 22 files in `docs/superpowers/specs/`

| Old | New |
|-----|-----|
| `2026-03-02-phase05-argocd-infrastructure-design.md` | `2026-03-02--gitops--argocd-infrastructure-design.md` |
| `2026-03-03-phase06-openrgb-led-control-design.md` | `2026-03-03--fun--openrgb-led-control-design.md` |
| `2026-03-06-blog-series-design.md` | `2026-03-06--repo--blog-series-design.md` |
| `2026-03-07-phase07-observability-design.md` | `2026-03-07--obs--observability-design.md` |
| `2026-03-07-phase08-backup-design.md` | `2026-03-07--backup--longhorn-r2-design.md` |
| `2026-03-07-phase09-secrets-management-design.md` | `2026-03-07--secrets--infisical-eso-design.md` |
| `2026-03-07-phase12-multi-tenancy-design.md` | `2026-03-07--tenant--vcluster-design.md` |
| `2026-03-07-phaseXX-vms-design.md` | `2026-03-07--hw--vms-design.md` |
| `2026-03-08-declarative-drift-remediation-design.md` | `2026-03-08--repo--declarative-drift-remediation-design.md` |
| `2026-03-09-phase04-gpu1-pcie-link-speed-fix-design.md` | `2026-03-09--gpu--pcie-link-speed-fix-design.md` |
| `2026-03-09-phase06-openrgb-server-regression-fix-design.md` | `2026-03-09--fun--openrgb-server-regression-fix-design.md` |
| `2026-03-09-phase10-local-inference-design.md` | `2026-03-09--infer--ollama-litellm-design.md` |
| `2026-03-09-phase11-sympozium-design.md` | `2026-03-09--agents--sympozium-design.md` |
| `2026-03-10-phase04-gpu-operator-talos-fix-design.md` | `2026-03-10--gpu--operator-talos-fix-design.md` |
| `2026-03-10-phase11-sympozium-agents-fix-design.md` | `2026-03-10--agents--sympozium-agents-fix-design.md` |
| `2026-03-10-phaseXX-coding-agent-infrastructure-design.md` | `2026-03-10--agents--coding-agent-infrastructure-design.md` |
| `2026-03-11-unified-auth-design.md` | `2026-03-11--auth--authentik-design.md` |
| `2026-03-13-operating-on-frank-blog-series-design.md` | `2026-03-13--repo--operating-blog-series-design.md` |
| `2026-03-14-phase14-paperclip-design.md` | `2026-03-14--orch--paperclip-design.md` |
| `2026-03-16-phase15-comfyui-custom-image-design.md` | `2026-03-16--media--comfyui-custom-image-design.md` |
| `2026-03-16-phaseXX-hop-public-edge-design.md` | `2026-03-16--edge--hop-public-design.md` |
| `2026-03-20-phaseXX-multi-cluster-restructure-design.md` | `2026-03-20--repo--multi-cluster-restructure-design.md` |

- [x] **Step 1: Execute all git mv commands for specs**

```bash
cd docs/superpowers/specs
git mv 2026-03-02-phase05-argocd-infrastructure-design.md 2026-03-02--gitops--argocd-infrastructure-design.md
# ... (all 22 renames)
```

- [x] **Step 2: Commit renames**

```bash
git add -A docs/superpowers/plans/ docs/superpowers/specs/
git commit -m "refactor(repo): rename plans/specs from phase to layer naming convention"
```

### Task 4: Update cross-references inside plans and specs

Plans reference their spec files (and sometimes other plans) by filename. These internal references must be updated to match the new filenames.

- [x] **Step 1: Find and replace old filenames with new filenames inside all plan/spec files**

Use `grep -r` to find all cross-references, then `sed` to update them. Key patterns:
- `Spec:` lines in plan headers pointing to spec files
- `Origin:` lines referencing other plans
- `plan:` fields in manual-operation YAML blocks inside plans

- [x] **Step 2: Replace `Phase XX`, `Phase 04`, etc. in plan/spec headers with layer references**

In each plan/spec, the header typically has `Phase: XX` or `Phase: 04`. Replace with the layer code, e.g., `Layer: gpu` or `Layer: edge`.

- [x] **Step 3: Commit**

```bash
git add docs/superpowers/plans/ docs/superpowers/specs/
git commit -m "refactor(repo): update cross-references in plans/specs for layer naming"
```

---

## Chunk 2: Update CLAUDE.md

### Task 5: Update CLAUDE.md naming convention and workflows

**Files:**
- Modify: `CLAUDE.md`

- [x] **Step 1: Update "Standard Phase Workflow" section**

Rename to a workflow section that references layers:
- Section title: `## Standard Layer Workflow`
- "Every phase follows" → "Every layer follows"
- Step 2 (Plan): reference layer code instead of phaseXX
- Step 3 (Execute): no phase number assignment needed — layer code is known from brainstorm

- [x] **Step 2: Update "Phase Fix/Extension Workflow" section**

- Section title: `## Layer Fix/Extension Workflow`
- "deployed phase" → "deployed layer"
- Commit template: `fix(phaseNN):` → `fix(<layer>):` e.g., `fix(gpu):`

- [x] **Step 3: Update "Plan Naming Convention" section**

Replace:
```
Plan files follow: `YYYY-MM-DD-phaseNN-<feature-name>[-design].md`
- New phases start as phaseXX...
- Bugfixes use original phase number...
```

With:
```
Plan files follow: `YYYY-MM-DD--<layer>--<details>[-design].md`
- `<layer>` is the short code from `docs/layers.yaml` (e.g., gpu, edge, auth)
- Multiple plans on the same layer share the code with different detail suffixes
- The `repo` layer is for meta-tasks (blog infra, CI, restructuring)
```

- [x] **Step 4: Update Architecture tree comments**

`patches/` directory comments reference phases — update to note these are legacy names:
```
patches/               # Talos machine config patches (legacy phaseNN naming)
```

- [x] **Step 5: Update Gotchas if any reference phases conceptually**

- [x] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(repo): update CLAUDE.md for layer naming convention"
```

---

## Chunk 3: Update Runbook, Skills, README

### Task 6: Update `docs/runbooks/manual-operations.yaml`

**Files:**
- Modify: `docs/runbooks/manual-operations.yaml`

- [x] **Step 1: Rename `phase` field to `layer` throughout**

All entries have `phase: NN` — replace with `layer: NN`.

- [x] **Step 2: Update operation IDs from `phaseNN-*` to `<layer>-*`**

e.g., `phaseXX-hop-argocd-bootstrap` → `edge-hop-argocd-bootstrap`

- [x] **Step 3: Update `plan:` path references to new filenames**

e.g., `plan: docs/superpowers/plans/2026-03-16-phaseXX-hop-public-edge.md` → `plan: docs/superpowers/plans/2026-03-16--edge--hop-public.md`

- [x] **Step 4: Update any comments referencing phases**

- [x] **Step 5: Commit**

```bash
git add docs/runbooks/manual-operations.yaml
git commit -m "refactor(repo): update runbook for layer naming convention"
```

### Task 7: Update skills

**Files:**
- Modify: `.claude/skills/blog-post/SKILL.md` (1 line)
- Modify: `.claude/skills/update-readme/SKILL.md` (~6 lines)
- Modify: `.claude/skills/sync-runbook.md` (~5 lines)

- [x] **Step 1: Update blog-post skill**

Line 96: "new phase/capability" → "new layer/capability"

- [x] **Step 2: Update update-readme skill**

- Line 3: "after a new phase" → "after new layer work"
- Line 10: "after each new phase is deployed" → "after each new layer is deployed"
- Line 16: "introduced in the phase" → "introduced in the layer"
- Line 18: "for the phase design file" → "for the layer design file"
- Lines 47, 51: commit message template `phase NN` → `layer <code> — <summary>`

- [x] **Step 3: Update sync-runbook skill**

- Line 18: "Phase 0 / bootstrap" → "Layer 0 / bootstrap"
- Line 28: "by phase ascending" → "by layer ascending"
- Lines 52-53, 74-75: schema example `phaseNN-short-name` / `phase: NN` → `<layer>-short-name` / `layer: NN`

- [x] **Step 4: Commit**

```bash
git add .claude/skills/
git commit -m "docs(repo): update skills for layer naming convention"
```

### Task 8: Update README.md

**Files:**
- Modify: `README.md`

- [x] **Step 1: Update architecture tree comments**

The `patches/` section references phase names — add a note about legacy naming:
```
patches/               # Talos machine config patches (legacy phaseNN- prefixed dirs)
```

- [x] **Step 2: Update any narrative references to "phase" → "layer"**

- [x] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(repo): update README for layer naming convention"
```

---

## Chunk 4: Update Blog Posts

### Task 9: Update blog post narrative text

**Files:**
- Modify: ~10 building posts + ~2 operating posts

Blog posts that reference "Phase N" or "phase" conceptually need updating. This is narrative text — keep it natural (e.g., "Layer 10 gave Ollama its own...").

Key posts to update (found by grep):
- `blog/content/building/02-foundation/index.md`
- `blog/content/building/03-storage/index.md`
- `blog/content/building/04-gpu-compute/index.md`
- `blog/content/building/07-observability/index.md`
- `blog/content/building/10-local-inference/index.md`
- `blog/content/building/12-gpu-talos-fix/index.md`
- `blog/content/building/13-unified-auth/index.md`
- `blog/content/building/15-paperclip/index.md`
- `blog/content/building/16-media-generation/index.md`
- `blog/content/building/17-public-edge/index.md`
- `blog/content/operating/01-cluster-nodes/index.md`

- [x] **Step 1: Find all "phase"/"Phase" occurrences in blog posts**

```bash
grep -rn -i "phase" blog/content/building/*/index.md blog/content/operating/*/index.md
```

- [x] **Step 2: Update each occurrence contextually**

- "Phase N" → "Layer N" (when referring to a capability domain)
- "Twelve phases in" → "Twelve layers deep" or similar natural phrasing
- "a future phase" → "a future layer"
- File path references to `patches/phaseNN-*/` → keep as-is (these are actual directory paths)

- [x] **Step 3: Update `blog/content/building/00-overview/index.md`**

Check the Technology → Capability Map and Series Index for any phase references.

- [x] **Step 4: Commit**

```bash
git add blog/content/
git commit -m "docs(repo): update blog posts for layer naming convention"
```

---

## Chunk 5: Final Verification

### Task 10: Verify no stale phase references remain

- [x] **Step 1: Grep for stale references**

```bash
# Should return only: patches/ directory names (legacy, intentional)
grep -rn "phase[0-9]\|phaseXX\|phaseNN" --include="*.md" --include="*.yaml" --include="*.html" .
```

- [x] **Step 2: Verify all plan/spec cross-references resolve**

```bash
# Check that every Spec: and plan: reference in plans actually points to an existing file
grep -rh "Spec:\|plan:" docs/superpowers/plans/ | grep -oP '[\w/.-]+\.md' | while read f; do
  [ -f "$f" ] || echo "BROKEN: $f"
done
```

- [x] **Step 3: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "refactor(repo): complete phase-to-layer naming migration"
```
