## Standard Layer Workflow

Every layer follows this sequence:

1. **Brainstorm** — `/brainstorming` to explore requirements, refine scope, and design the approach via Socratic dialogue
2. **Plan** — `/writing-plans` to produce a step-by-step implementation plan. The layer code is chosen at this step (see `docs/layers.yaml` for the registry)
3. **Execute** — `/executing-plans` to implement the plan with review checkpoints
4. **Deploy** — Implement the ArgoCD app (values, Application CR, manifests)
5. **Blog** — Use the `/blog-post` skill to write the Hugo post. After creating the post, update `blog/content/building/00-overview/index.md` (Series Index + Capability Map) and `blog/layouts/shortcodes/cluster-roadmap.html` (add new roadmap layer)
6. **Update README** — Run `/update-readme` to sync Technology Stack, Repository Structure, Service Access, and Current Status in `README.md`
7. **Sync runbook** — Run `/sync-runbook` if the layer plan contains any `# manual-operation` blocks
8. **Review** — Verify deployment health and blog accuracy. Update the plan's `**Status:**` to `Deployed` (cluster workload) or `Complete` (repo/meta work)

## Layer Fix/Extension Workflow

When a deployed layer needs a bugfix or unplanned extension:

1. **Diagnose** — `/systematic-debugging` to identify root cause. Document findings in the existing layer plan as a new "Deviation" entry
2. **Fix** — Implement the fix in the original layer's ArgoCD app/manifests (not a new app)
3. **Update plan** — Add deviation notes inline at the affected task + append to the Deployment Deviations section
4. **Update blog** — Retroactively update the layer's building/ post (add gotcha or correction) and operating/ post (add new operational commands). Do NOT create a new post unless the fix is substantial enough to warrant its own narrative (e.g., the GPU Talos validation fix)
5. **Update gotchas** — If the fix reveals a non-obvious pattern, add it to `.claude/rules/frank-gotchas.md` or `.claude/rules/hop-gotchas.md`

Use the layer code in commit messages: `fix(gpu): <description>` or `feat(edge): <description>`.
