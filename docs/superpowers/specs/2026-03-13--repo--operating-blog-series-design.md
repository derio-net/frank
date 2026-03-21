# Operating on Frank — Blog Series Design

> New blog series providing operational runbooks and day-to-day command references
> for every major technology deployed on the Frank cluster.

## Context

The existing "Building Frank" blog series (posts 00–14) documents how each
component was designed, deployed, and integrated. What's missing is an
operational companion: commands for health-checking, routine maintenance, and
debugging each component after it's running.

This work is **not a Layer** — it produces no new infrastructure. The output is:

1. A restructured Hugo site with two subsections ("building", "operating")
2. 9 new "Operating on Frank" blog posts
3. Two new banner images for the operating series
4. Hugo template/config changes for section-aware banners and navigation

## Hugo Site Restructuring

### Subsections

Move from a flat `posts/` section to two subsections:

```
blog/content/
  building/                  # existing posts moved from posts/
    _index.md                # list page: "Building Frank"
    00-overview/index.md
    01-introduction/index.md
    ...
    14-multi-tenancy/index.md
  operating/                 # new series
    _index.md                # list page: "Operating on Frank"
    01-cluster-nodes/index.md
    02-storage-backups/index.md
    ...
    09-multi-tenancy/index.md
```

The old `posts/` directory is removed entirely. All existing post URLs change
from `/posts/NN-slug/` to `/building/NN-slug/`. This URL breakage is accepted.
The RSS feed URL will also change (`/posts/index.xml` → `/building/index.xml`
plus `/operating/index.xml`); the site-wide feed at `/index.xml` is unaffected.

### `_index.md` Files

**`building/_index.md`:**

```yaml
---
title: "Building Frank"
description: "A tutorial series on building an AI-hybrid Kubernetes homelab from scratch."
---
```

**`operating/_index.md`:**

```yaml
---
title: "Operating on Frank"
description: "Day-to-day commands, health checks, and debugging guides for every component on the cluster."
---
```

### Hugo Config (`hugo.toml`)

The following changes are applied to the existing `hugo.toml`. Note that
`mainSections` is a **new** parameter — it is not currently set. When unset,
PaperMod defaults to the section with the most pages (previously `posts`).
Adding it explicitly ensures both series appear on the home page.

```toml
title = "Frank, the Talos Cluster"   # was: "Building Frank, the Talos Cluster"

[params]
  description = "Tutorial series on building and operating an AI-hybrid Kubernetes homelab"
  mainSections = ["building", "operating"]
  operatingThinBanner = "images/banner-operating-thin.png"
  # existing thinBanner and heroBanner remain for building series / home page

  [params.label]
    text = "Frank, the Talos Cluster"   # was: "Building Frank, the Talos Cluster"

  [params.homeInfoParams]
    Title = "Frank, the Talos Cluster"  # was: "Frank, the Talos Cluster" (unchanged)
    Content = "Tutorial series on building and operating an AI-hybrid Kubernetes homelab with Talos Linux, Cilium, Longhorn, ArgoCD, and GPU compute."

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

The existing `posts` menu entry is replaced by `building`.

### Section-Aware Thin Banner (`layouts/partials/header.html`)

The header partial currently shows `site.Params.thinBanner` unconditionally.
Change it to select the banner based on the page's `.Section` property:

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

Hugo's `.Section` returns the top-level content directory name for any page
(`"building"`, `"operating"`, or `""` for home/taxonomy pages). This handles
all page types correctly — home page and tag pages fall through to the default
building banner.

No changes needed to `home_info.html` — the hero banner only appears on the
home page via `homeInfoParams`, not on section list pages.

### Section-Scoped Post Navigation (`layouts/partials/post_nav_links.html`)

PaperMod's default prev/next navigation spans all `mainSections`, which would
link between building and operating posts. Create a new override partial at
`blog/layouts/partials/post_nav_links.html` by copying the theme's version
from `themes/PaperMod/layouts/partials/post_nav_links.html` and modifying the
page collection to scope within the current section:

```go-html-template
{{- $pages := where .CurrentSection.Pages "Kind" "page" -}}
```

This replaces the theme's cross-section page query and ensures "Operating on
Storage" links to other operating posts, not to building posts.

## Banner Images

Two new images added to `prompt_for_images.yaml`, following the existing
generation pipeline (`scripts/generate-all-images.py` with reference image).

### `banner-operating-thin.png` (1200x200)

Surgical/self-operation theme in the ultra-wide 6:1 strip format. Frank lying
on his back on an operating table on the left third, using robotic arms to
work on his own internals. Center-right: the title **"Operating on Frank"** in
bold chunky retro-tech lettering with electric blue glow (matching the
"Building Frank" thin banner style). Dark circuit-board background.

### Operations Post Cover Images

Each operations post gets its own cover image via `prompt_for_images.yaml`,
following the "Operating on Frank" surgical/self-repair visual theme. These
are generated as part of the post creation tasks.

## Operations Post Inventory

| # | Slug | Title | Building Posts Covered | Key Technologies |
|---|------|-------|-----------------------|------------------|
| 01 | `01-cluster-nodes` | Operating on Cluster & Nodes | 02-foundation | Talos, Cilium, Hubble |
| 02 | `02-storage-backups` | Operating on Storage & Backups | 03-storage, 08-backup | Longhorn, Cloudflare R2, SOPS |
| 03 | `03-gitops` | Operating on GitOps | 05-gitops | ArgoCD, App-of-Apps |
| 04 | `04-gpu-compute` | Operating on GPU Compute | 04-gpu-compute, 12-gpu-talos-fix | NVIDIA Operator, Intel DRA, containerd |
| 05 | `05-observability` | Operating on Observability | 07-observability | VictoriaMetrics, Grafana, Fluent Bit |
| 06 | `06-secrets` | Operating on Secrets | 09-secrets | Infisical, ESO, SOPS/age |
| 07 | `07-inference` | Operating on Local Inference | 10-local-inference | Ollama, LiteLLM, OpenRouter |
| 08 | `08-auth` | Operating on Authentication | 13-unified-auth | Authentik, OIDC |
| 09 | `09-multi-tenancy` | Operating on Multi-tenancy | 14-multi-tenancy | vCluster |

### Excluded Building Posts

- **00-overview** — navigation hub, no operational component
- **01-introduction** — motivation/narrative, no deployed technology
- **06-fun-stuff** — RGB LEDs, novelty project, not operationally relevant
- **11-agentic-control-plane** — Sympozium, too niche/early-stage

## Operations Post Template

Each post follows a consistent hybrid structure: narrative introduction and
walkthroughs for context, plus a structured quick-reference table for
day-to-day lookup.

```markdown
---
title: "Operating on <Topic>"
date: 2026-MM-DD
draft: false
tags: ["operations", "<technology>", ...]
summary: "Day-to-day commands for operating and debugging <topic> on Frank."
weight: <N>
cover:
  image: cover.png
  alt: "..."
  relative: true
---

## Overview

Short intro (2-3 paragraphs): What this component does on Frank, how it's
deployed (cross-link to the relevant building post), what "healthy" looks
like, and what typically goes wrong.

## Observing State

Narrative walkthrough of the key commands for checking health and
understanding current state. Each command in a bash code block with brief
explanation of what to look for in the output.

## Routine Operations

Common day-to-day tasks: scaling, updating, rotating credentials, etc.
Only tasks that actually apply to this component on Frank.

## Debugging

Realistic problem scenarios: "Pods stuck in Pending", "Metrics not
scraping", "Volume won't attach". For each: symptoms, diagnosis commands,
and fix.

## Quick Reference

| Task | Command | Source |
|------|---------|--------|
| Check health | `kubectl ...` | [Docs](url) |
| View logs | `kubectl ...` | [Docs](url) |

Structured table for scannable lookup. Duplicates the most important
commands from the narrative sections above.

## References

Bulleted list of upstream docs, GitHub repos, and links to the
corresponding building post(s).
```

### Weight Strategy

Operating posts use weights starting at **101** (101, 102, ... 109) to avoid
collisions with building post weights (1–15). On the home page where both
series are listed together, posts are sorted by date (default PaperMod
behavior); weights only affect ordering within section list pages.

### Content Conventions

- Every command includes a link to its upstream documentation source
- The Quick Reference table is a self-contained cheat sheet — usable without
  reading the narrative sections
- The Overview always cross-links to the corresponding building post(s)
- All posts tagged with `"operations"` for filtering
- Cover images follow the "Operating on Frank" surgical/self-repair theme

## Overview Page Update

The existing `building/00-overview/index.md` (Series Index + Capability Map)
should be updated to reference the operating series and link to its posts.

## Follow-up: CLAUDE.md Path Updates

After the restructuring, CLAUDE.md contains stale path references that must
be updated:

- **Blog Post Pattern** section: `blog/content/posts/NN-slug/` → references
  both `blog/content/building/` and `blog/content/operating/`
- **Standard Layer Workflow** step 3: `blog/content/posts/00-overview/index.md`
  → `blog/content/building/00-overview/index.md`
- **Architecture** section: `blog/` description should mention the two-series
  structure

## What This Work Does NOT Include

- No new infrastructure or ArgoCD apps
- No changes to existing building post content (only moved to new path)
- No changes to the cluster roadmap shortcode (this is not a layer)
- No README update (no new services or architecture changes)
