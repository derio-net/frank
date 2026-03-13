# Operating on Frank — Blog Series Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second blog series ("Operating on Frank") with 9 operational runbook posts, restructuring the Hugo site into `building/` and `operating/` subsections with section-aware banners.

**Architecture:** Move existing posts from `blog/content/posts/` to `blog/content/building/`, create `blog/content/operating/` for new posts. Update Hugo config for two sections, override `header.html` for section-aware thin banner, override `post_nav_links.html` for section-scoped navigation. Generate banner images via the existing pipeline.

**Tech Stack:** Hugo, PaperMod theme, Go templates, YAML frontmatter, image generation pipeline (`scripts/generate-all-images.py`)

**Spec:** `docs/superpowers/specs/2026-03-13-operating-on-frank-blog-series-design.md`

---

## Chunk 1: Hugo Restructuring (config, templates, content move)

### Task 1: Move existing posts to `building/` subsection

**Files:**
- Create: `blog/content/building/_index.md`
- Move: `blog/content/posts/*` → `blog/content/building/`
- Delete: `blog/content/posts/` (empty after move)

- [ ] **Step 1: Create the `building/` directory and `_index.md`**

```bash
mkdir -p blog/content/building
```

Write `blog/content/building/_index.md`:

```yaml
---
title: "Building Frank"
description: "A tutorial series on building an AI-hybrid Kubernetes homelab from scratch."
---
```

- [ ] **Step 2: Move all post directories into `building/`**

```bash
mv blog/content/posts/* blog/content/building/
rmdir blog/content/posts
```

- [ ] **Step 3: Update all relref links across all moved posts**

Multiple posts contain `relref "/posts/..."` cross-references that now need to point to `/building/...`. Run a global find-and-replace across all markdown files:

```bash
find blog/content/building -name '*.md' -exec sed -i '' 's|relref "/posts/|relref "/building/|g' {} +
```

Verify no stale references remain:

```bash
grep -r 'relref "/posts/' blog/content/building/
```

Expected: no output (all references updated).

- [ ] **Step 3b: Update `prompt_for_images.yaml` output paths**

The existing cover image entries in `blog/prompt_for_images.yaml` reference `blog/content/posts/` paths. Update them to `blog/content/building/`:

```bash
sed -i '' 's|blog/content/posts/|blog/content/building/|g' blog/prompt_for_images.yaml
```

Also update the file's header comment (line 1):

```
Before: # Image Generation Prompts for "Building Frank" Blog
After:  # Image Generation Prompts for "Frank, the Talos Cluster" Blog
```

Verify:

```bash
grep 'blog/content/posts/' blog/prompt_for_images.yaml
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add blog/content/building/ blog/content/posts/ blog/prompt_for_images.yaml
git commit -m "blog: move posts to building/ subsection

Restructure Hugo content from flat posts/ to building/ subsection
as preparation for the new 'Operating on Frank' series. Update all
relref cross-references and prompt_for_images.yaml output paths."
```

---

### Task 2: Create `operating/` subsection scaffolding

**Files:**
- Create: `blog/content/operating/_index.md`

- [ ] **Step 1: Create the `operating/` directory and `_index.md`**

```bash
mkdir -p blog/content/operating
```

Write `blog/content/operating/_index.md`:

```yaml
---
title: "Operating on Frank"
description: "Day-to-day commands, health checks, and debugging guides for every component on the cluster."
---
```

- [ ] **Step 2: Commit**

```bash
git add blog/content/operating/
git commit -m "blog: add operating/ subsection scaffolding"
```

---

### Task 3: Update Hugo config (`hugo.toml`)

**Files:**
- Modify: `blog/hugo.toml`

- [ ] **Step 1: Update site title and label**

In `blog/hugo.toml`, change line 3:
```
Before: title = "Building Frank, the Talos Cluster"
After:  title = "Frank, the Talos Cluster"
```

Change `params.label.text` (line 23):
```
Before: text = "Building Frank, the Talos Cluster"
After:  text = "Frank, the Talos Cluster"
```

- [ ] **Step 2: Update description and add mainSections + operatingThinBanner**

Change `params.description` (line 8):
```
Before: description = "Building an AI-hybrid Kubernetes homelab with Talos Linux"
After:  description = "Tutorial series on building and operating an AI-hybrid Kubernetes homelab"
```

Add after line 20 (`thinBanner = "images/banner-thin.png"`):
```toml
  operatingThinBanner = "images/banner-operating-thin.png"
  mainSections = ["building", "operating"]
```

- [ ] **Step 3: Update homeInfoParams content**

Change `params.homeInfoParams.Content` (line 27):
```
Before: Content = "A tutorial series on building an AI-hybrid Kubernetes homelab from scratch with Talos Linux, Cilium, Longhorn, ArgoCD, and GPU compute."
After:  Content = "Tutorial series on building and operating an AI-hybrid Kubernetes homelab with Talos Linux, Cilium, Longhorn, ArgoCD, and GPU compute."
```

- [ ] **Step 4: Replace menu entries**

Replace the menu section (lines 33-43):

```toml
[menu]
  [[menu.main]]
    identifier = "building"
    name = "Building"
    url = "/building/"
    weight = 10
  [[menu.main]]
    identifier = "operating"
    name = "Operating"
    url = "/operating/"
    weight = 15
  [[menu.main]]
    identifier = "tags"
    name = "Tags"
    url = "/tags/"
    weight = 20
```

- [ ] **Step 5: Commit**

```bash
git add blog/hugo.toml
git commit -m "blog: update hugo.toml for two-section layout

- Neutralize site title to 'Frank, the Talos Cluster'
- Add mainSections for building + operating
- Add operatingThinBanner param
- Replace posts menu with building + operating entries"
```

---

### Task 4: Section-aware thin banner in `header.html`

**Files:**
- Modify: `blog/layouts/partials/header.html:1-5`

- [ ] **Step 1: Replace the banner block**

In `blog/layouts/partials/header.html`, replace lines 1-5:

```go-html-template
{{- if site.Params.thinBanner }}
<div class="site-banner-strip">
    <img src="{{ site.Params.thinBanner | relURL }}" alt="Frank the Talos Cluster Monster">
</div>
{{- end }}
```

With:

```go-html-template
{{- $banner := site.Params.thinBanner -}}
{{- if eq .Section "operating" -}}
  {{- $banner = site.Params.operatingThinBanner -}}
{{- end -}}
{{- if $banner }}
<div class="site-banner-strip">
    <img src="{{ $banner | relURL }}" alt="Frank the Talos Cluster Monster">
</div>
{{- end }}
```

- [ ] **Step 2: Commit**

```bash
git add blog/layouts/partials/header.html
git commit -m "blog: section-aware thin banner in header partial

Show 'Operating on Frank' banner for operating section pages,
default 'Building Frank' banner for everything else."
```

---

### Task 5: Section-scoped post navigation

**Files:**
- Create: `blog/layouts/partials/post_nav_links.html`
- Reference: `blog/themes/PaperMod/layouts/partials/post_nav_links.html`

- [ ] **Step 1: Create override partial**

The theme's `post_nav_links.html` at `blog/themes/PaperMod/layouts/partials/post_nav_links.html` contains:

```go-html-template
{{- $pages := where site.RegularPages "Type" "in" site.Params.mainSections }}
{{- if and (gt (len $pages) 1) (in $pages . ) }}
<nav class="paginav">
  {{- with $pages.Next . }}
  <a class="prev" href="{{ .Permalink }}">
    <span class="title">« {{ i18n "prev_page" }}</span>
    <br>
    <span>{{- .Name -}}</span>
  </a>
  {{- end }}
  {{- with $pages.Prev . }}
  <a class="next" href="{{ .Permalink }}">
    <span class="title">{{ i18n "next_page" }} »</span>
    <br>
    <span>{{- .Name -}}</span>
  </a>
  {{- end }}
</nav>
{{- end }}
```

Create `blog/layouts/partials/post_nav_links.html` with line 1 changed to scope within the current section:

```go-html-template
{{- $pages := where .CurrentSection.Pages "Kind" "page" }}
{{- if and (gt (len $pages) 1) (in $pages . ) }}
<nav class="paginav">
  {{- with $pages.Next . }}
  <a class="prev" href="{{ .Permalink }}">
    <span class="title">« {{ i18n "prev_page" }}</span>
    <br>
    <span>{{- .Name -}}</span>
  </a>
  {{- end }}
  {{- with $pages.Prev . }}
  <a class="next" href="{{ .Permalink }}">
    <span class="title">{{ i18n "next_page" }} »</span>
    <br>
    <span>{{- .Name -}}</span>
  </a>
  {{- end }}
</nav>
{{- end }}
```

- [ ] **Step 2: Commit**

```bash
git add blog/layouts/partials/post_nav_links.html
git commit -m "blog: scope post nav links within current section

Override PaperMod partial to prevent prev/next links from crossing
between building and operating series."
```

---

### Task 6: Verify Hugo build and site structure

- [ ] **Step 1: Run Hugo build**

```bash
cd blog && hugo --minify 2>&1
```

Expected: Build succeeds with no errors. Check output for:
- Pages in `building/` section
- Pages in `operating/` section (just `_index.md` for now)
- No references to old `posts/` path

- [ ] **Step 2: Spot-check generated output**

```bash
ls blog/public/building/
ls blog/public/operating/
# Verify old posts/ path doesn't exist:
ls blog/public/posts/ 2>&1 || echo "posts/ correctly removed"
```

- [ ] **Step 3: Start dev server and visually verify**

```bash
cd blog && hugo server --buildDrafts &
```

Check:
- Home page shows building posts
- `/building/` list page shows all 15 posts with "Building Frank" thin banner
- `/operating/` list page shows empty with "Building Frank" thin banner (operating banner not yet generated — will be verified again after Task 7)
- `/tags/` page shows "Building Frank" thin banner (not operating)
- Navigation menu shows "Building | Operating | Tags"
- Breadcrumbs show "Home > Building > Post Title"
- Prev/next links on building posts stay within building series

Stop the server after verification.

- [ ] **Step 4: Commit any fixes if needed**

---

### Task 7: Add banner image prompts to `prompt_for_images.yaml`

**Files:**
- Modify: `blog/prompt_for_images.yaml`

- [ ] **Step 1: Add operating thin banner prompt**

Add after the existing `banner-thin` entry (after approximately line 77, before the `favicon` entry) in `blog/prompt_for_images.yaml`:

```yaml
  - key: banner-operating-thin
    output: blog/static/images/banner-operating-thin.png
    description: Operating series header strip banner (1200x200, 6:1 ratio)
    prompt: >-
      An ultra-wide horizontal strip banner, extremely wide and short — exactly
      1200 pixels wide by 200 pixels tall (6:1 aspect ratio). Frank the
      server-hardware Frankenstein monster lies on his back on a surgical
      operating table on the left third of the image, about 60% the strip
      height. His chest cavity is open, revealing circuit boards, drives, and
      glowing cables inside. Multiple robotic arms (mounted to the ceiling or
      the table frame) reach into his chest — one arm solders a circuit trace,
      another swaps a miniature SSD, a third reconnects a glowing cable. Frank
      is conscious and focused, guiding the arms with a small handheld
      controller. Green skin, messy black hair, black eyes, RJ45 neck bolts
      sparking blue electricity. Center-right: the title "Operating on Frank"
      in bold chunky retro-tech lettering, glowing electric blue with subtle
      circuit-trace underlines (matching the "Building Frank" thin banner
      style). Background: dark circuit-board surface with faint green PCB
      traces and sparse blue lightning arcs. Bottom edge: tiny decorative icons
      — a wrench, a stethoscope, a terminal prompt, a heartbeat monitor.
      Composition fades at both edges into darkness. The image MUST be
      extremely wide and short, like a letterbox strip — 1200x200 pixels,
      6:1 ratio.
```

- [ ] **Step 2: Commit**

```bash
git add blog/prompt_for_images.yaml
git commit -m "blog: add operating series banner image prompt"
```

- [ ] **Step 3: Generate the banner image**

```bash
.venv/bin/python scripts/generate-all-images.py -r blog/static/images/reference.png --only banner-operating-thin
```

Expected: Image generated at `blog/static/images/banner-operating-thin.png`.

Visually inspect the image — it should show Frank on a surgical table with robotic arms and "Operating on Frank" text.

- [ ] **Step 4: Quick visual check of operating banner**

Start the dev server briefly and verify `/operating/` now shows the new "Operating on Frank" thin banner instead of the building banner:

```bash
cd blog && hugo server --buildDrafts &
```

Check `/operating/` — should show the new banner. Stop the server.

- [ ] **Step 5: Commit generated image**

```bash
git add blog/static/images/banner-operating-thin.png
git commit -m "blog: add 'Operating on Frank' thin banner image"
```

---

### Task 8: Update CLAUDE.md stale path references

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update Standard Phase Workflow path**

In `CLAUDE.md` line 11, change:
```
Before: update `blog/content/posts/00-overview/index.md`
After:  update `blog/content/building/00-overview/index.md`
```

- [ ] **Step 2: Update Blog Post Pattern section**

Replace the Blog Post Pattern path block (lines 83-88) to show both series:

```
Before:
  blog/content/posts/NN-slug/
    index.md       # Post content
    cover.png      # Cover image
    *.png          # Inline images

After:
  blog/content/building/NN-slug/   # "Building Frank" posts
  blog/content/operating/NN-slug/  # "Operating on Frank" posts
    index.md       # Post content
    cover.png      # Cover image
    *.png          # Inline images
```

- [ ] **Step 3: Update Architecture section**

In `CLAUDE.md` line 124, change:
```
Before: blog/                  # Hugo static site (PaperMod theme)
After:  blog/                  # Hugo static site (PaperMod theme, building/ + operating/ series)
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md paths for building/operating subsections"
```

---

### Task 9: Update overview page to reference operating series

**Files:**
- Modify: `blog/content/building/00-overview/index.md`

- [ ] **Step 1: Add operating series section**

After the Series Index (after line 70 in the original, which lists the last building post), add:

```markdown

## Operating on Frank — Series Index

Companion series with day-to-day commands, health checks, and debugging guides.

1. [Operating on Cluster & Nodes]({{< relref "/operating/01-cluster-nodes" >}}) _(coming soon)_
2. [Operating on Storage & Backups]({{< relref "/operating/02-storage-backups" >}}) _(coming soon)_
3. [Operating on GitOps]({{< relref "/operating/03-gitops" >}}) _(coming soon)_
4. [Operating on GPU Compute]({{< relref "/operating/04-gpu-compute" >}}) _(coming soon)_
5. [Operating on Observability]({{< relref "/operating/05-observability" >}}) _(coming soon)_
6. [Operating on Secrets]({{< relref "/operating/06-secrets" >}}) _(coming soon)_
7. [Operating on Local Inference]({{< relref "/operating/07-inference" >}}) _(coming soon)_
8. [Operating on Authentication]({{< relref "/operating/08-auth" >}}) _(coming soon)_
9. [Operating on Multi-tenancy]({{< relref "/operating/09-multi-tenancy" >}}) _(coming soon)_
```

Note: Use plain markdown links instead of `relref` for "coming soon" entries since the target pages don't exist yet. Replace with:

```markdown

## Operating on Frank — Series Index

Companion series with day-to-day commands, health checks, and debugging guides.

1. Operating on Cluster & Nodes _(coming soon)_
2. Operating on Storage & Backups _(coming soon)_
3. Operating on GitOps _(coming soon)_
4. Operating on GPU Compute _(coming soon)_
5. Operating on Observability _(coming soon)_
6. Operating on Secrets _(coming soon)_
7. Operating on Local Inference _(coming soon)_
8. Operating on Authentication _(coming soon)_
9. Operating on Multi-tenancy _(coming soon)_
```

Convert each to a `relref` link once the corresponding operating post is created.

- [ ] **Step 2: Commit**

```bash
git add blog/content/building/00-overview/index.md
git commit -m "blog: add 'Operating on Frank' series index to overview page"
```

---

## Chunk 2: Operating Posts (01–05)

Each operating post follows the template from the spec. The implementer must:
1. Read the corresponding building post(s) to understand the technology
2. Research upstream documentation for commands and links
3. Write the post content following the hybrid template (Overview, Observing State, Routine Operations, Debugging, Quick Reference, References)
4. Add a cover image prompt to `prompt_for_images.yaml`
5. Generate the cover image

### Task 10: Write operating post 01 — Cluster & Nodes

**Files:**
- Create: `blog/content/operating/01-cluster-nodes/index.md`
- Modify: `blog/prompt_for_images.yaml` (add cover image prompt)
- Reference: `blog/content/building/02-foundation/index.md`

**Key technologies to cover:** Talos Linux (`talosctl`), Cilium (`cilium` CLI, Hubble), node management, Omni (`omnictl`).

- [ ] **Step 1: Read the building post for context**

Read `blog/content/building/02-foundation/index.md` thoroughly to understand what was deployed and how.

- [ ] **Step 2: Research upstream docs for operational commands**

Key sources to reference in the post:
- Talos docs: `https://www.talos.dev/v1.9/reference/cli/` — `talosctl` commands
- Cilium docs: `https://docs.cilium.io/en/stable/operations/` — operations guide
- Hubble docs: `https://docs.cilium.io/en/stable/observability/hubble/` — flow observability
- Omni docs: `https://omni.siderolabs.com/docs/` — machine management

- [ ] **Step 3: Write the post**

Create `blog/content/operating/01-cluster-nodes/index.md` with:

Frontmatter:
```yaml
---
title: "Operating on Cluster & Nodes"
date: 2026-03-13
draft: false
tags: ["operations", "talos", "cilium", "hubble", "networking"]
summary: "Day-to-day commands for checking cluster health, managing Talos nodes, and debugging Cilium networking on Frank."
weight: 101
cover:
  image: cover.png
  alt: "Frank checking his own vital signs on monitoring screens"
  relative: true
---
```

Sections to include:
- **Overview:** Frank runs Talos Linux (immutable, API-driven) with Cilium eBPF CNI. Link back to building post 02. Healthy = all 7 nodes Ready, Cilium pods running, Hubble collecting flows.
- **Observing State:** `talosctl health`, `kubectl get nodes -o wide`, `talosctl version --nodes <IP>`, `cilium status`, `hubble observe`, `talosctl dmesg --nodes <IP>`, `talosctl logs <service> --nodes <IP>`
- **Routine Operations:** Upgrading Talos (`talosctl upgrade`), applying config patches (`omnictl apply`), rebooting nodes (`talosctl reboot`), checking Omni machine status (`omnictl get machines`)
- **Debugging:** Node NotReady (check `talosctl health`, `dmesg`, `etcd` status), Pod networking issues (`cilium connectivity test`, `hubble observe --pod`), Cilium agent crash (check `cilium-agent` logs)
- **Quick Reference:** Table with ~15 most useful commands and source links
- **References:** Links to Talos, Cilium, Hubble, Omni docs

- [ ] **Step 4: Add cover image prompt**

Add to `blog/prompt_for_images.yaml`:
```yaml
  - key: ops-01-cluster-nodes
    output: blog/content/operating/01-cluster-nodes/cover.png
    description: "Operating on Cluster & Nodes — Frank checking vital signs"
    prompt: >-
      Frank the server-hardware Frankenstein monster lying on a surgical table
      on his back, surrounded by monitoring screens showing node health status
      dashboards — green checkmarks for 7 nodes, heartbeat lines, network
      flow diagrams. One robotic arm holds a stethoscope to his chest (the
      server rack torso), another arm types on a floating terminal showing
      'talosctl health' output. A Cilium hexagonal bee icon floats nearby
      with green status lights. Frank looks relaxed and confident — routine
      checkup, everything is healthy. Dark server room background with blue
      and green accent lighting.
```

- [ ] **Step 5: Generate cover image**

```bash
.venv/bin/python scripts/generate-all-images.py -r blog/static/images/reference.png --only ops-01-cluster-nodes
```

- [ ] **Step 6: Commit**

```bash
git add blog/content/operating/01-cluster-nodes/ blog/prompt_for_images.yaml
git commit -m "blog(operating): add post 01 — Operating on Cluster & Nodes

Covers talosctl, cilium CLI, hubble, omnictl commands for health checks,
routine operations, and debugging."
```

---

### Task 11: Write operating post 02 — Storage & Backups

**Files:**
- Create: `blog/content/operating/02-storage-backups/index.md`
- Modify: `blog/prompt_for_images.yaml`
- Reference: `blog/content/building/03-storage/index.md`, `blog/content/building/08-backup/index.md`

**Key technologies:** Longhorn (`longhornctl`, UI), Cloudflare R2 backups, SOPS/age secrets.

- [ ] **Step 1: Read the building posts**

Read `blog/content/building/03-storage/index.md` and `blog/content/building/08-backup/index.md`.

- [ ] **Step 2: Research upstream docs**

Key sources:
- Longhorn docs: `https://longhorn.io/docs/1.8.1/` — operations, troubleshooting
- Longhorn CLI: `https://longhorn.io/docs/1.8.1/advanced-resources/longhornctl/` — `longhornctl`
- Cloudflare R2 docs: `https://developers.cloudflare.com/r2/` — S3-compatible backup target

- [ ] **Step 3: Write the post**

Create `blog/content/operating/02-storage-backups/index.md` with frontmatter:
```yaml
---
title: "Operating on Storage & Backups"
date: 2026-03-13
draft: false
tags: ["operations", "longhorn", "storage", "backup", "r2"]
summary: "Day-to-day commands for managing Longhorn volumes, checking backup health, and restoring from Cloudflare R2."
weight: 102
cover:
  image: cover.png
  alt: "Frank performing surgery on his own storage drives with robotic arms"
  relative: true
---
```

Sections to include:
- **Overview:** Longhorn provides distributed block storage (3 replicas on control planes, gpu-local class). Backups go to Cloudflare R2 daily/weekly. Link back to building posts 03 and 08.
- **Observing State:** `kubectl get volumes.longhorn.io -n longhorn-system`, Longhorn UI at `192.168.55.201`, `kubectl get recurringjobs.longhorn.io`, check backup status, volume health
- **Routine Operations:** Expand a volume, trigger manual backup, restore from backup, check/manage snapshots, verify R2 backup credentials
- **Debugging:** Volume degraded (replica count, node offline), backup failed (check S3 credentials, network), volume stuck attaching (`kubectl describe pv`, check iSCSI)
- **Quick Reference:** Table of key commands
- **References:** Longhorn docs, R2 docs, building posts

- [ ] **Step 4: Add cover image prompt and generate**

```yaml
  - key: ops-02-storage-backups
    output: blog/content/operating/02-storage-backups/cover.png
    description: "Operating on Storage & Backups — Frank maintaining his storage drives"
    prompt: >-
      Frank the server-hardware Frankenstein monster lying on a surgical table.
      A robotic arm carefully removes a glowing SSD from his torso while
      another arm inserts a fresh replacement drive. A third arm holds a
      magnifying glass over the drive bay, inspecting data integrity. Nearby,
      a conveyor belt carries backup cubes into an orange R2-branded cloud
      portal. Three replica indicators glow green above his chest. A Longhorn
      bull silhouette is visible on a monitor in the background. Dark server
      room with blue and orange lighting.
```

```bash
.venv/bin/python scripts/generate-all-images.py -r blog/static/images/reference.png --only ops-02-storage-backups
```

- [ ] **Step 5: Commit**

```bash
git add blog/content/operating/02-storage-backups/ blog/prompt_for_images.yaml
git commit -m "blog(operating): add post 02 — Operating on Storage & Backups

Covers Longhorn volume management, backup/restore with R2, snapshot
operations, and troubleshooting degraded volumes."
```

---

### Task 12: Write operating post 03 — GitOps

**Files:**
- Create: `blog/content/operating/03-gitops/index.md`
- Modify: `blog/prompt_for_images.yaml`
- Reference: `blog/content/building/05-gitops/index.md`

**Key technologies:** ArgoCD (`argocd` CLI), App-of-Apps, sync operations.

- [ ] **Step 1: Read the building post**

Read `blog/content/building/05-gitops/index.md`.

- [ ] **Step 2: Research upstream docs**

Key sources:
- ArgoCD docs: `https://argo-cd.readthedocs.io/en/stable/` — operations, CLI, troubleshooting
- ArgoCD CLI: `https://argo-cd.readthedocs.io/en/stable/user-guide/commands/argocd/`

- [ ] **Step 3: Write the post**

Frontmatter:
```yaml
---
title: "Operating on GitOps"
date: 2026-03-13
draft: false
tags: ["operations", "argocd", "gitops"]
summary: "Day-to-day commands for managing ArgoCD applications, syncing, debugging drift, and handling degraded apps."
weight: 103
cover:
  image: cover.png
  alt: "Frank conducting robotic arms that manage his application orchestra"
  relative: true
---
```

Sections to include:
- **Overview:** ArgoCD App-of-Apps at `192.168.55.200`, self-managing. All workloads declared in `apps/`. Link to building post 05.
- **Observing State:** `argocd app list --port-forward --port-forward-namespace argocd`, `argocd app get <app>`, check sync status, health status, resource tree
- **Routine Operations:** Force sync (`argocd app sync`), hard refresh, add new app (App-of-Apps pattern), manage ArgoCD itself, check diff before sync
- **Debugging:** App stuck Degraded (check events, resource status), sync failed (check logs, annotation size), OutOfSync but correct (ignoreDifferences), orphaned resources
- **Quick Reference:** Table of key `argocd` CLI commands
- **References:** ArgoCD docs, building post

- [ ] **Step 4: Add cover image prompt and generate**

```yaml
  - key: ops-03-gitops
    output: blog/content/operating/03-gitops/cover.png
    description: "Operating on GitOps — Frank managing his application orchestra"
    prompt: >-
      Frank the server-hardware Frankenstein monster lying on a surgical table
      with his chest open, revealing neatly organized application boxes inside
      (each labeled: cilium, longhorn, gpu-operator, ollama). A robotic arm
      carefully adjusts the position of one box while another arm holds a
      glowing sync arrow icon. An ArgoCD octopus mascot perches on the table
      edge, tentacles helping sort the applications. A git branch diagram
      glows on a floating monitor. Green "Synced" and "Healthy" badges float
      above each app box. Dark server room with blue and orange lighting.
```

```bash
.venv/bin/python scripts/generate-all-images.py -r blog/static/images/reference.png --only ops-03-gitops
```

- [ ] **Step 5: Commit**

```bash
git add blog/content/operating/03-gitops/ blog/prompt_for_images.yaml
git commit -m "blog(operating): add post 03 — Operating on GitOps

Covers ArgoCD CLI operations, sync management, drift detection,
and troubleshooting degraded applications."
```

---

### Task 13: Write operating post 04 — GPU Compute

**Files:**
- Create: `blog/content/operating/04-gpu-compute/index.md`
- Modify: `blog/prompt_for_images.yaml`
- Reference: `blog/content/building/04-gpu-compute/index.md`, `blog/content/building/12-gpu-talos-fix/index.md`

**Key technologies:** NVIDIA GPU Operator, Intel DRA driver, `nvidia-smi`, containerd, `talosctl`.

- [ ] **Step 1: Read the building posts**

Read `blog/content/building/04-gpu-compute/index.md` and `blog/content/building/12-gpu-talos-fix/index.md`.

- [ ] **Step 2: Research upstream docs**

Key sources:
- NVIDIA GPU Operator: `https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/`
- `nvidia-smi`: `https://developer.nvidia.com/nvidia-system-management-interface`
- Intel GPU DRA: `https://github.com/intel/intel-resource-drivers-for-kubernetes`
- Talos NVIDIA extensions: `https://www.talos.dev/v1.9/talos-guides/configuration/nvidia-gpu/`

- [ ] **Step 3: Write the post**

Frontmatter:
```yaml
---
title: "Operating on GPU Compute"
date: 2026-03-13
draft: false
tags: ["operations", "gpu", "nvidia", "intel", "talos"]
summary: "Day-to-day commands for managing NVIDIA and Intel GPUs, checking utilization, and debugging GPU container issues on Talos."
weight: 104
cover:
  image: cover.png
  alt: "Frank performing surgery on his GPU arm with precision robotic tools"
  relative: true
---
```

Sections: Overview (NVIDIA on gpu-1 + Intel iGPU on minis), Observing State (`nvidia-smi`, GPU operator pods, DRA resource claims), Routine Operations (model loading, GPU memory management, checking utilization), Debugging (GPU not allocating, containerd issues, validation markers, Talos reboot loops), Quick Reference, References.

- [ ] **Step 4: Add cover image prompt and generate**

```yaml
  - key: ops-04-gpu-compute
    output: blog/content/operating/04-gpu-compute/cover.png
    description: "Operating on GPU Compute — Frank servicing his GPU arms"
    prompt: >-
      Frank the server-hardware Frankenstein monster on a surgical table. His
      right arm (a massive NVIDIA GPU card) is detached and being serviced by
      two robotic arms — one running diagnostics with a glowing probe, another
      tightening a PCIe connector. His left arm (a smaller Intel Arc iGPU)
      glows blue on the table beside him, also being inspected. A floating
      terminal displays 'nvidia-smi' output showing GPU utilization bars.
      Validation checkmark badges float above the repaired components. Dark
      server room with green and blue electric sparks.
```

```bash
.venv/bin/python scripts/generate-all-images.py -r blog/static/images/reference.png --only ops-04-gpu-compute
```

- [ ] **Step 5: Commit**

```bash
git add blog/content/operating/04-gpu-compute/ blog/prompt_for_images.yaml
git commit -m "blog(operating): add post 04 — Operating on GPU Compute

Covers nvidia-smi, GPU operator management, Intel DRA, containerd
debugging, and Talos-specific GPU gotchas."
```

---

### Task 14: Write operating post 05 — Observability

**Files:**
- Create: `blog/content/operating/05-observability/index.md`
- Modify: `blog/prompt_for_images.yaml`
- Reference: `blog/content/building/07-observability/index.md`

**Key technologies:** VictoriaMetrics, Grafana (`192.168.55.203`), Fluent Bit, VictoriaLogs.

- [ ] **Step 1: Read the building post**

Read `blog/content/building/07-observability/index.md`.

- [ ] **Step 2: Research upstream docs**

Key sources:
- VictoriaMetrics: `https://docs.victoriametrics.com/` — operations, querying
- Grafana: `https://grafana.com/docs/grafana/latest/` — dashboards, alerting
- Fluent Bit: `https://docs.fluentbit.io/manual/` — pipeline, troubleshooting
- VictoriaLogs: `https://docs.victoriametrics.com/victorialogs/` — log querying

- [ ] **Step 3: Write the post**

Frontmatter:
```yaml
---
title: "Operating on Observability"
date: 2026-03-13
draft: false
tags: ["operations", "victoriametrics", "grafana", "fluent-bit", "observability"]
summary: "Day-to-day commands for querying metrics and logs, managing Grafana dashboards, and debugging the observability pipeline."
weight: 105
cover:
  image: cover.png
  alt: "Frank monitoring his own vital signs through surgical instruments"
  relative: true
---
```

Sections: Overview (VM + Grafana + Fluent Bit + VictoriaLogs stack), Observing State (Grafana dashboards, MetricsQL queries, log queries), Routine Operations (create/import dashboards, adjust retention, check Fluent Bit pipeline, silence alerts), Debugging (missing metrics, Fluent Bit not shipping, stale webhook alertmanager, high cardinality), Quick Reference, References.

- [ ] **Step 4: Add cover image prompt and generate**

```yaml
  - key: ops-05-observability
    output: blog/content/operating/05-observability/cover.png
    description: "Operating on Observability — Frank monitoring his own vitals"
    prompt: >-
      Frank the server-hardware Frankenstein monster on a surgical table,
      surrounded by medical-style monitoring equipment repurposed with tech.
      A heart rate monitor shows a Grafana time-series graph instead of a
      heartbeat. An IV drip bag is filled with flowing log entries (green
      text). A robotic arm holds a stethoscope connected to a VictoriaMetrics
      database icon on Frank's chest. A tiny Fluent Bit bird perches on
      the stethoscope. Multiple screens around the table show dashboards
      with green status indicators. Dark server room with blue and purple
      monitoring glow.
```

```bash
.venv/bin/python scripts/generate-all-images.py -r blog/static/images/reference.png --only ops-05-observability
```

- [ ] **Step 5: Commit**

```bash
git add blog/content/operating/05-observability/ blog/prompt_for_images.yaml
git commit -m "blog(operating): add post 05 — Operating on Observability

Covers VictoriaMetrics queries, Grafana dashboard management, Fluent Bit
pipeline debugging, and VictoriaLogs log querying."
```

---

## Chunk 3: Operating Posts (06–09) and Final Steps

### Task 15: Write operating post 06 — Secrets

**Files:**
- Create: `blog/content/operating/06-secrets/index.md`
- Modify: `blog/prompt_for_images.yaml`
- Reference: `blog/content/building/09-secrets/index.md`

**Key technologies:** Infisical (`192.168.55.204`), External Secrets Operator (ESO), SOPS/age.

- [ ] **Step 1: Read the building post**

Read `blog/content/building/09-secrets/index.md`.

- [ ] **Step 2: Research upstream docs**

Key sources:
- Infisical docs: `https://infisical.com/docs/documentation/getting-started/introduction`
- ESO docs: `https://external-secrets.io/latest/` — ExternalSecret, SecretStore
- SOPS: `https://github.com/getsops/sops` — encryption/decryption
- age: `https://github.com/FiloSottile/age` — key management

- [ ] **Step 3: Write the post**

Frontmatter:
```yaml
---
title: "Operating on Secrets"
date: 2026-03-13
draft: false
tags: ["operations", "infisical", "external-secrets", "sops", "security"]
summary: "Day-to-day commands for managing secrets in Infisical, checking ESO sync status, and handling SOPS-encrypted bootstrap secrets."
weight: 106
cover:
  image: cover.png
  alt: "Frank carefully handling encrypted data capsules during self-surgery"
  relative: true
---
```

Sections: Overview (Infisical as source of truth, ESO syncs to K8s, SOPS for bootstrap), Observing State (ESO sync status, Infisical UI, `kubectl get externalsecrets`), Routine Operations (add/rotate secrets in Infisical, force ESO refresh, apply SOPS secrets), Debugging (ESO sync failed, secret not updating, SOPS decrypt errors, project slug issues), Quick Reference, References.

- [ ] **Step 4: Add cover image prompt and generate**

```yaml
  - key: ops-06-secrets
    output: blog/content/operating/06-secrets/cover.png
    description: "Operating on Secrets — Frank handling encrypted data capsules"
    prompt: >-
      Frank the server-hardware Frankenstein monster on a surgical table.
      Robotic arms carefully handle glowing encrypted data capsules — each
      capsule has a tiny padlock icon and a label (DATABASE_URL, API_KEY).
      One arm transfers a capsule from an Infisical vault (ornate glowing
      door in the background) into Frank's chest cavity. Another arm uses
      a SOPS key (shaped like an age encryption key) to unlock a sealed
      capsule. A small ESO robot assistant passes capsules between the vault
      and Frank. Blue encryption ripples flow across the scene. Dark server
      room with blue and gold lighting.
```

```bash
.venv/bin/python scripts/generate-all-images.py -r blog/static/images/reference.png --only ops-06-secrets
```

- [ ] **Step 5: Commit**

```bash
git add blog/content/operating/06-secrets/ blog/prompt_for_images.yaml
git commit -m "blog(operating): add post 06 — Operating on Secrets

Covers Infisical management, ESO sync operations, SOPS/age encryption,
and troubleshooting secret sync issues."
```

---

### Task 16: Write operating post 07 — Local Inference

**Files:**
- Create: `blog/content/operating/07-inference/index.md`
- Modify: `blog/prompt_for_images.yaml`
- Reference: `blog/content/building/10-local-inference/index.md`

**Key technologies:** Ollama, LiteLLM (`192.168.55.206`), OpenRouter.

- [ ] **Step 1: Read the building post**

Read `blog/content/building/10-local-inference/index.md`.

- [ ] **Step 2: Research upstream docs**

Key sources:
- Ollama: `https://github.com/ollama/ollama/blob/main/docs/api.md` — API reference
- LiteLLM: `https://docs.litellm.ai/` — proxy, virtual keys, model management
- OpenRouter: `https://openrouter.ai/docs/` — API, free models

- [ ] **Step 3: Write the post**

Frontmatter:
```yaml
---
title: "Operating on Local Inference"
date: 2026-03-13
draft: false
tags: ["operations", "ollama", "litellm", "openrouter", "ai"]
summary: "Day-to-day commands for managing local LLM inference, checking model status, routing through LiteLLM, and debugging GPU memory issues."
weight: 107
cover:
  image: cover.png
  alt: "Frank adjusting his AI brain module with precision robotic instruments"
  relative: true
---
```

Sections: Overview (Ollama on gpu-1, LiteLLM gateway, OpenRouter cloud), Observing State (Ollama model list, LiteLLM health, GPU memory, active models), Routine Operations (pull/remove models, test inference, check LiteLLM routing, update OpenRouter model list), Debugging (OOM on GPU, model loading slow, LiteLLM routing errors, Ollama not responding), Quick Reference, References.

- [ ] **Step 4: Add cover image prompt and generate**

```yaml
  - key: ops-07-inference
    output: blog/content/operating/07-inference/cover.png
    description: "Operating on Local Inference — Frank adjusting his AI brain"
    prompt: >-
      Frank the server-hardware Frankenstein monster on a surgical table. His
      head is opened (the flat-top CPU die head), and robotic arms carefully
      adjust neural network circuitry inside — tiny glowing LLM model blocks
      labeled 'qwen3.5' and 'deepseek-coder'. A switchboard console labeled
      'LiteLLM' sits beside the table, with routing lines flowing from
      Frank's brain to a local GPU rack (Ollama llama icon) and a cloud
      portal (OpenRouter). A tiny robot consumer waits at the end of the
      routing pipe. Frank looks focused on getting the brain tuning just
      right. Dark server room with purple and blue neural network lighting.
```

```bash
.venv/bin/python scripts/generate-all-images.py -r blog/static/images/reference.png --only ops-07-inference
```

- [ ] **Step 5: Commit**

```bash
git add blog/content/operating/07-inference/ blog/prompt_for_images.yaml
git commit -m "blog(operating): add post 07 — Operating on Local Inference

Covers Ollama model management, LiteLLM gateway operations, GPU memory
monitoring, and OpenRouter routing."
```

---

### Task 17: Write operating post 08 — Authentication

**Files:**
- Create: `blog/content/operating/08-auth/index.md`
- Modify: `blog/prompt_for_images.yaml`
- Reference: `blog/content/building/13-unified-auth/index.md`

**Key technologies:** Authentik (`192.168.55.211`), OIDC, forward auth proxy.

- [ ] **Step 1: Read the building post**

Read `blog/content/building/13-unified-auth/index.md`.

- [ ] **Step 2: Research upstream docs**

Key sources:
- Authentik docs: `https://docs.goauthentik.io/docs/` — administration, troubleshooting
- Authentik API: `https://docs.goauthentik.io/developer-docs/api/` — REST API
- OIDC spec: `https://openid.net/specs/openid-connect-core-1_0.html`

- [ ] **Step 3: Write the post**

Frontmatter:
```yaml
---
title: "Operating on Authentication"
date: 2026-03-13
draft: false
tags: ["operations", "authentik", "oidc", "sso", "security"]
summary: "Day-to-day commands for managing Authentik SSO, checking OIDC flows, and debugging authentication issues across the cluster."
weight: 108
cover:
  image: cover.png
  alt: "Frank installing a new security lock system into his own chest"
  relative: true
---
```

Sections: Overview (Authentik SSO for ArgoCD/Grafana/Infisical, forward auth for Longhorn/Hubble/Sympozium), Observing State (Authentik admin UI, check provider status, user/group listing via API), Routine Operations (add users/groups, create new provider, rotate client secrets, manage API tokens), Debugging (OIDC login loop, token validation failures, forward auth 403, Grafana secret key mismatch), Quick Reference, References.

- [ ] **Step 4: Add cover image prompt and generate**

```yaml
  - key: ops-08-auth
    output: blog/content/operating/08-auth/cover.png
    description: "Operating on Authentication — Frank installing security systems"
    prompt: >-
      Frank the server-hardware Frankenstein monster on a surgical table.
      A robotic arm installs a glowing golden lock mechanism into his chest
      cavity — the lock has an OIDC token ring around it. Another arm tests
      the lock with a golden skeleton key labeled 'SSO'. Service icons
      (ArgoCD octopus, Grafana flame, a vault door) wait in line beside
      the table, each holding a badge to be validated. An Authentik shield
      emblem glows on a monitor. A rejected intruder icon dissolves with a
      red X. Dark server room with blue and gold lighting accents.
```

```bash
.venv/bin/python scripts/generate-all-images.py -r blog/static/images/reference.png --only ops-08-auth
```

- [ ] **Step 5: Commit**

```bash
git add blog/content/operating/08-auth/ blog/prompt_for_images.yaml
git commit -m "blog(operating): add post 08 — Operating on Authentication

Covers Authentik SSO management, OIDC provider operations, user/group
management, and debugging auth flow issues."
```

---

### Task 18: Write operating post 09 — Multi-tenancy

**Files:**
- Create: `blog/content/operating/09-multi-tenancy/index.md`
- Modify: `blog/prompt_for_images.yaml`
- Reference: `blog/content/building/14-multi-tenancy/index.md`

**Key technologies:** vCluster, virtual Kubernetes clusters, resource quotas.

- [ ] **Step 1: Read the building post**

Read `blog/content/building/14-multi-tenancy/index.md`.

- [ ] **Step 2: Research upstream docs**

Key sources:
- vCluster docs: `https://www.vcluster.com/docs` — operations, CLI
- vCluster CLI: `https://www.vcluster.com/docs/vcluster/reference/vcluster-cli`

- [ ] **Step 3: Write the post**

Frontmatter:
```yaml
---
title: "Operating on Multi-tenancy"
date: 2026-03-13
draft: false
tags: ["operations", "vcluster", "multi-tenancy"]
summary: "Day-to-day commands for managing vCluster virtual clusters, checking tenant health, and debugging isolation issues."
weight: 109
cover:
  image: cover.png
  alt: "Frank maintaining miniature cluster snow globes inside his own body"
  relative: true
---
```

Sections: Overview (vCluster creates virtual K8s clusters inside Frank, template pattern), Observing State (`vcluster list`, check virtual cluster pods, connect to virtual cluster), Routine Operations (create new vCluster from template, delete/recreate, access virtual cluster kubectl, manage resource quotas), Debugging (vCluster not syncing, virtual API server unresponsive, resource quota exceeded, network policy issues), Quick Reference, References.

- [ ] **Step 4: Add cover image prompt and generate**

```yaml
  - key: ops-09-multi-tenancy
    output: blog/content/operating/09-multi-tenancy/cover.png
    description: "Operating on Multi-tenancy — Frank maintaining snow globe clusters"
    prompt: >-
      Frank the server-hardware Frankenstein monster on a surgical table.
      His open chest cavity contains several tiny snow globes, each holding
      a miniature Kubernetes cluster. A robotic arm carefully lifts one snow
      globe out for inspection — inside it, tiny servers glow with blue
      network lines. Another arm installs a fresh snow globe into an empty
      slot. A third arm holds a magnifying glass over a snow globe, checking
      its tiny resource quota meter. One shattered snow globe dissolves into
      sparkles on the table — representing disposability. A vCluster logo
      floats on a nearby monitor. Dark server room with blue and teal
      lighting.
```

```bash
.venv/bin/python scripts/generate-all-images.py -r blog/static/images/reference.png --only ops-09-multi-tenancy
```

- [ ] **Step 5: Commit**

```bash
git add blog/content/operating/09-multi-tenancy/ blog/prompt_for_images.yaml
git commit -m "blog(operating): add post 09 — Operating on Multi-tenancy

Covers vCluster management, virtual cluster access, template-based
creation, and debugging isolation issues."
```

---

### Task 19: Update overview page with live links

**Files:**
- Modify: `blog/content/building/00-overview/index.md`

- [ ] **Step 1: Replace "coming soon" items with relref links**

In the "Operating on Frank — Series Index" section added in Task 9, replace each plain text entry with a `relref` link:

```markdown
## Operating on Frank — Series Index

Companion series with day-to-day commands, health checks, and debugging guides.

1. [Operating on Cluster & Nodes]({{< relref "/operating/01-cluster-nodes" >}})
2. [Operating on Storage & Backups]({{< relref "/operating/02-storage-backups" >}})
3. [Operating on GitOps]({{< relref "/operating/03-gitops" >}})
4. [Operating on GPU Compute]({{< relref "/operating/04-gpu-compute" >}})
5. [Operating on Observability]({{< relref "/operating/05-observability" >}})
6. [Operating on Secrets]({{< relref "/operating/06-secrets" >}})
7. [Operating on Local Inference]({{< relref "/operating/07-inference" >}})
8. [Operating on Authentication]({{< relref "/operating/08-auth" >}})
9. [Operating on Multi-tenancy]({{< relref "/operating/09-multi-tenancy" >}})
```

- [ ] **Step 2: Commit**

```bash
git add blog/content/building/00-overview/index.md
git commit -m "blog: update overview page with live operating series links"
```

---

### Task 20: Final verification

- [ ] **Step 1: Run Hugo build**

```bash
cd blog && hugo --minify 2>&1
```

Expected: Build succeeds, no broken `relref` links, no errors.

- [ ] **Step 2: Start dev server and verify all pages**

```bash
cd blog && hugo server --buildDrafts &
```

Check:
- Home page lists both building and operating posts
- `/building/` list page: all 15 building posts, "Building Frank" thin banner
- `/operating/` list page: all 9 operating posts, "Operating on Frank" thin banner
- Each operating post: correct thin banner, breadcrumbs show "Home > Operating > Post Title"
- Prev/next links on operating posts stay within operating series
- Prev/next links on building posts stay within building series
- Overview page has both series indexes with working links
- Navigation menu: "Building | Operating | Tags"

- [ ] **Step 3: Final commit if any fixes needed**
