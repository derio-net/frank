## Standard Layer Workflow

Every layer follows this sequence:

1. **Brainstorm** — `/brainstorming` to explore requirements, refine scope, and design the approach via Socratic dialogue
2. **Plan** — `/fr-plan` to produce a phase-structured implementation plan. The layer code is chosen at this step (see `docs/layers.yaml` for the registry). Plan behavior is driven by `docs/superpowers/plan-config.yaml`
3. **Execute** — fr-plan offers three execution paths: VK dispatch, subagent-driven, or inline execution
4. **Deploy** — Implement the ArgoCD app (values, Application CR, manifests)
5. **Blog** — Use `/blog-craft:blog-post <series> <NN> <slug> "<title>"`. It scaffolds the page bundle, generates the cover, and runs `/blog-craft:media` for any media markers. The series index lists the new post **automatically**: each series' section entrypoint (`content/docs/<series>/_index.md`) renders `{{< series-index "<series>" >}}` — page-derived cards, colour-coded by the post's `layer`, no append/markers, always in sync — so there is **no index edit step**. Give the new post a `series: ["<series>"]` and a `layer: <code>` (a `docs/layers.yaml` code) in its frontmatter so it's listed and coloured; a brand-new layer also needs a colour in `blog/data/layer_palette.yaml` (regenerate via `blog/scripts/gen-layer-palette.py`). Then **add the new layer to `blog/data/roadmap.yaml`** (data-driven roadmap). If the post introduces a new technology, update the hand-curated **Technology → Capability Map** on `building/00-overview` by hand — that table is not page-derived
6. **Update README** — Run `/update-readme` to sync Technology Stack, Repository Structure, Service Access, and Current Status in `README.md`
7. **Sync runbook** — Run `/sync-runbook` if the layer plan contains any `# manual-operation` blocks
8. **Review** — Verify deployment health and blog accuracy. Update the plan's `**Status:**` to `Deployed` (cluster workload) or `Complete` (repo/meta work)

## Layer Fix/Extension Workflow

When a deployed layer needs a bugfix or unplanned extension:

1. **Diagnose** — `/systematic-debugging` to identify root cause. Document findings in the existing layer plan as a new "Deviation" entry
2. **Fix** — Implement the fix in the original layer's ArgoCD app/manifests (not a new app)
3. **Update plan** — Add deviation notes inline at the affected task + append to the Deployment Deviations section
4. **Update blog** — Retroactively edit the layer's building/ post (add gotcha or correction) and operating/ post (add new operational commands) directly — extending an existing post is a normal markdown edit, not a `/blog-craft:blog-post` run. If you add new `<!-- MEDIA: … -->` markers, run `/blog-craft:media` to fill them. Do NOT create a new post unless the fix is substantial enough to warrant its own narrative (e.g., the GPU Talos validation fix)
5. **Update gotchas** — If the fix reveals a non-obvious pattern, add a one-liner to `agents/rules/frank-gotchas.md` (or `hop-gotchas.md`) and the full prose / recovery commands to the matching per-topic file under `docs/runbooks/frank-gotchas/<topic>.md` (see that dir's `README.md` for the topic→file map). Hot file is part of the required agent load order; per-topic files are not (read on demand).

Use the layer code in commit messages: `fix(gpu): <description>` or `feat(edge): <description>`.

## Plan Management Scripts

- `scripts/plan-status.sh` — list all plans with Spec/Archived/Status columns
- `scripts/plan-status.sh --open` — show only in-progress plans with open tasks/steps tree
- `scripts/plan-status.sh --archive` — move Complete/Deployed/Closed plans to `archived-plans/`
- `scripts/validate-plans.sh [files...]` — validate plan headers (delegates to canonical validator from super-fr plugin)

Validation is enforced by `.githooks/pre-commit` and Claude Code PostToolUse hooks (`scripts/hooks/`).
