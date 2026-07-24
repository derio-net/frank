---
name: post-deploy
description: >
  Close out a deployed change with one verb. Walk the Post-Deploy Checklist
  (new layer) or the Layer Fix/Extension Workflow (fix/extension to an existing
  layer), chaining /blog-craft:blog-post -> update-readme -> sync-runbook and
  updating the plan status. Use right after deploying a new layer or a
  fix/extension — when you'd otherwise have to remember the checklist
  bullet-by-bullet.
user-invocable: true
disable-model-invocation: false
---

# Post-Deploy Close-Out

One discoverable verb for "I deployed something." Instead of remembering the
Post-Deploy Checklist and reaching for `/blog-craft:blog-post` / `update-readme` /
`sync-runbook` one at a time, invoke `/post-deploy` and it drives the whole
close-out — the standard-layer checklist or the fix/extension workflow, whichever
fits — delegating to the existing skills at each step.

> **Blog authoring is the `blog-craft` plugin, not a repo-local skill.** Use
> `/blog-craft:blog-post` and `/blog-craft:media` (driven by the repo's
> `.blog-craft.yaml`). Series indexes are page-derived — a post with the right
> `series:` + `layer:` frontmatter is listed automatically, so there is **no
> manual index-edit step**.

This skill **orchestrates**; it does not duplicate the sub-skills. The
authoritative sources of truth are:

- `agents/rules/plan-post-deploy-checklist.md` — the standard-layer checklist and
  the skip matrix.
- `agents/rules/repo-workflows.md` — the Standard Layer Workflow and the Layer
  Fix/Extension Workflow.

## When to use

Invoke immediately after a change is live/merged and you're closing it out:

- A **new layer** was deployed (new ArgoCD app, new service, new capability).
- A **fix or extension** to an existing deployed layer landed.

## When to skip (per `plan-post-deploy-checklist.md`)

- **Internal-only services** (no public/mesh domain, no homepage tile) → skip the
  expose step, keep the rest.
- **Meta/repo layer** work (blog infra, CI, restructuring) → skip blog posts and
  README unless the change is user-visible.
- **Investigation/audit** plans → skip the entire close-out (diagnostic, not a
  deployment).

If a skip applies, say which and why, then run only the remaining steps.

## Step 0 — classify the change

Decide which branch to run, and announce it:

| Change | Branch |
|--------|--------|
| New layer / new deployed capability | **A — Standard Layer close-out** |
| Bugfix or unplanned extension of an existing layer | **B — Fix/Extension close-out** |
| Meta/repo or investigation | Skip per matrix above |

Create a TodoWrite item per step of the chosen branch so the close-out can't be
half-finished silently.

## Branch A — Standard Layer close-out

Follow the six-step Post-Deploy Checklist. Run each step, then verify its
artifact before ticking it.

1. **Expose externally (if user-facing)** — invoke `expose-service` to add the
   Traefik IngressRoute (+ `authentik-forwardauth` and the manual outpost step
   if SSO is required — see `frank-argocd.md`) and the homepage tile. Skip for
   internal-only services.
2. **Building blog post** — invoke `/blog-craft:blog-post` for the "Building
   Frank" post. Give it `series: ["building"]` + `layer: <code>` (a
   `docs/layers.yaml` code) in frontmatter so the `docs/building/` section index
   lists and colours it **automatically** (`{{< series-index "building" >}}` —
   no manual index edit). Add the new layer to the roadmap **data file**
   `blog/data/roadmap.yaml`; if the post introduces a new technology, update the
   hand-curated Technology → Capability Map on `building/00-overview` by hand.
   A brand-new layer code also needs a colour in `blog/data/layer_palette.yaml`.
3. **Operating blog post** — invoke `/blog-craft:blog-post` for the companion
   operating guide, if the layer has day-to-day operational commands (most
   deployed workloads do; pure novelty layers may not). Give it
   `series: ["operating"]` + `layer:` frontmatter — the `docs/operating/` index
   lists it automatically, no index edit.
4. **Update README** — invoke `update-readme` to sync Technology Stack,
   Repository Structure, Service Access, and Current Status.
5. **Sync runbook** — invoke `sync-runbook` if the plan contains any
   `# manual-operation` blocks.
6. **Update plan status** — set the plan's `**Status:**` to `Deployed` (cluster
   workload) or `Complete` (repo/meta work).

## Branch B — Fix/Extension close-out

This is the **close-out** for the Layer Fix/Extension Workflow in
`repo-workflows.md` — it assumes the Diagnose and Fix steps are already done, and
its key difference from Branch A is that you update the **existing** layer's
artifacts rather than creating new ones. Steps 1–3 are the workflow's own
close-out steps (Update-plan / Update-blog / Update-gotchas); Steps 4–5 are the
close-out additions this skill layers on (they are not separate steps in
`repo-workflows.md`, but the same README/runbook hygiene the standard checklist
requires).

1. **Update plan** — add a Deviation entry to the existing layer plan (inline at
   the affected task + appended to the Deployment Deviations section).
2. **Update blog retroactively** — directly edit the layer's *existing* building
   post (add the gotcha/correction) and operating post (add new operational
   commands). Extending an existing post is a normal markdown edit, **not** a
   `/blog-craft:blog-post` run; if you add new `<!-- MEDIA: … -->` markers, run
   `/blog-craft:media` to fill them. Do **not** create a new post unless the fix
   is substantial enough to warrant its own narrative (e.g. the GPU Talos
   validation fix).
3. **Update gotchas** — if the fix revealed a non-obvious pattern, add a
   one-liner to `agents/rules/frank-gotchas.md` (or `hop-gotchas.md`) and the
   full prose / recovery commands to the matching per-topic file under
   `docs/runbooks/frank-gotchas/<topic>.md`.
4. **Update README** *(close-out addition)* — invoke `update-readme` only if the
   fix changed user-visible state (new service, new access URL, status change).
5. **Sync runbook** *(close-out addition)* — invoke `sync-runbook` if the fix
   added or changed any `# manual-operation` block.

Use the layer code in commit messages: `fix(<layer>): …` or `feat(<layer>): …`.

## Verify & finish

Before declaring the close-out done:

- Confirm each invoked sub-skill actually produced its artifact (the blog post
  exists and renders, README rows landed, the runbook entry synced).
- Confirm the plan `**Status:**` is set.
- Report which steps ran and which were skipped (with the reason), so the record
  shows the close-out was complete, not silently truncated.
