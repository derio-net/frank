> **Note:** vk-plan auto-appends a Post-Deploy Checklist phase from
> `docs/superpowers/plan-config.yaml` (`post_deploy` section). This rule
> documents the checklist content for reference and for manual plan creation.

## Post-Deploy Checklist for Plans

When creating a plan for a **standard layer** (new deployment, not a fix/extension/meta task), include a final task:

### Task N: Post-Deploy Checklist

- [ ] **Step 1: Write building blog post** — Use `/blog-post` skill. Update series index in `blog/content/building/00-overview/index.md` and cluster roadmap in `blog/layouts/shortcodes/cluster-roadmap.html`
- [ ] **Step 2: Write operating blog post** — Use `/blog-post` skill for the companion operating guide. Update operating series index in `blog/content/building/00-overview/index.md`
- [ ] **Step 3: Update README** — Run `/update-readme` to sync Technology Stack, Repository Structure, Service Access, and Current Status
- [ ] **Step 4: Sync runbook** — Run `/sync-runbook` if the plan contains any `# manual-operation` blocks
- [ ] **Step 5: Update plan status** — Set `**Status:**` to `Deployed` (cluster workload) or `Complete` (repo/meta work)

**When to skip steps:**
- Fix/extension plans: skip blog posts (update the existing layer's posts instead). Add gotchas to `.claude/rules/frank-gotchas.md` or `hop-gotchas.md` if applicable.
- Meta/repo plans (`repo` layer): skip blog posts and README unless the change is user-visible.
- Investigation/audit plans: skip all — these are diagnostic, not deployments.

**How to decide if a layer needs an operating post:**
A layer needs an operating post if it has day-to-day operational commands (health checks, restarts, promotions, troubleshooting). Most deployed workloads do. Novelty/fun layers (e.g., OpenRGB LED control) generally don't.
