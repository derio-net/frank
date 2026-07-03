> **Note:** vk-plan auto-appends a Post-Deploy Checklist phase from
> `docs/superpowers/plan-config.yaml` (`post_deploy` section). This rule
> documents the checklist content for reference and for manual plan creation.

## Post-Deploy Checklist for Plans

When creating a plan for a **standard layer** (new deployment, not a fix/extension/meta task), include a final task:

### Task N: Post-Deploy Checklist

- [ ] **Step 1: Expose externally (if user-facing)** — For any new service reachable by humans from outside the cluster (e.g. `vk.cluster.derio.net`):
  - Add a Traefik IngressRoute in `apps/traefik/manifests/ingressroutes.yaml` (with `authentik-forwardauth` middleware if SSO is required — see `frank-argocd.md` for the full forward-auth wiring, including the manual outpost-provider assignment)
  - Add a tile to the homepage dashboard at `master.cluster.derio.net` via `apps/homepage/manifests/files/services.yaml` (icon, category, description, URL)
  - Document the exposure (domain, auth mode, any manual steps) in the plan's deployment section and in the building blog post
- [ ] **Step 2: Write building blog post** — Use the `/blog-craft:blog-post` skill. The building overview lists the post automatically via `{{< series-index >}}` (page-derived — no index edit). Add the new layer to the cluster-roadmap **data file** `blog/data/roadmap.yaml` (append a `layers:` entry — `{num, key, title, sub_items, tags}`; the roadmap renders data-driven now, not from an inline shortcode), and if the post introduces a new technology, update the hand-curated Technology → Capability Map on `building/00-overview` by hand
- [ ] **Step 3: Write operating blog post** — Use the `/blog-craft:blog-post` skill for the companion operating guide. The operating overview (`operating/00-overview`) lists the post automatically via `{{< series-index >}}` — no index edit
- [ ] **Step 4: Update README** — Run `/update-readme` to sync Technology Stack, Repository Structure, Service Access, and Current Status
- [ ] **Step 5: Sync runbook** — Run `/sync-runbook` if the plan contains any `# manual-operation` blocks
- [ ] **Step 6: Update plan status** — Set `**Status:**` to `Deployed` (cluster workload) or `Complete` (repo/meta work)

**When to skip steps:**
- Fix/extension plans: skip blog posts (update the existing layer's posts instead). New gotchas: one-liner in `agents/rules/frank-gotchas.md` (or `hop-gotchas.md`), full prose in the matching per-topic file under `docs/runbooks/frank-gotchas/<topic>.md`.
- Internal-only services (no public/mesh domain, no homepage tile): skip Step 1.
- Meta/repo plans (`repo` layer): skip blog posts and README unless the change is user-visible.
- Investigation/audit plans: skip all — these are diagnostic, not deployments.

**How to decide if a layer needs an operating post:**
A layer needs an operating post if it has day-to-day operational commands (health checks, restarts, promotions, troubleshooting). Most deployed workloads do. Novelty/fun layers (e.g., OpenRGB LED control) generally don't.
