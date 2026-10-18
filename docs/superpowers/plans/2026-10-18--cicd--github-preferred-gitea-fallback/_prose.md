# GitHub-preferred CI with automatic Gitea fallback — plan

**Spec:** `docs/superpowers/specs/2026-10-18--cicd--github-preferred-gitea-fallback-design.md`
**Issue:** derio-net/frank#875
**Status:** In Progress

## Shape

Five agentic phases, one per independently reviewable ask, plus one trailing
`[manual]` phase.

1. **Skeleton** — the `ci-budget` Application, `tiers.yaml` and the
   gate-coverage checker (R1–R3, R16), with the `ubuntu-24.04` runner label.
   The checker lands first because the cross-repo workflow PRs (phase 6)
   validate against it, and the watcher reuses it.
2. **Mirrors + status bridge** (R4–R6) — Tekton triggers, the derio-net pull
   pipeline and token, reconciler and delivery-check extension, webhook
   declarations, and three-org status forwarding.
3. **Watcher** (R7–R14) — billing, monotonic authority, ordered two-forge
   writes, backstop re-run, state, Telegram, heartbeat and dead-man rule.
4. **Monthly report** (R15).
5. **Runner** (R18, R19) — 2Gi limit, runner probe, three alert rules.
6. **[manual]** — the two PRE-MERGE gates, the eleven cross-repo PRs (R17),
   provisioning, and per-org go-live.

Phases 2 and 3 depend only on 1; 4 and 5 build on the watcher's code.

## Test command

`.venv/bin/pytest scripts/tests/<files> -q` — call the venv directly. Do not
use `uv run`: across sessions it blocks on its lock. Exclude the hugo blog
tests, which can wedge `hugo --minify`. CI (`repo-tripwires.yml`) runs the
full suite.

## Manual operations

```yaml
# manual-operation
id: cicd-ci-budget-app-permissions
layer: cicd
app: ci-budget
plan: docs/superpowers/plans/2026-10-18--cicd--github-preferred-gitea-fallback/06.yaml
when: PRE-MERGE — before the frank PR leaves draft.
why_manual: GitHub App permission changes and installation re-approval are org-owner UI actions; App private keys are SOPS bootstrap secrets.
commands:
  - '# derio-fr-automation (derio-net), homelab-fr-automation (derio-homelab), stoa-fr-automation (agentic-stoa): App settings → Permissions'
  - '# all three: Organization permissions → Administration: Read-only'
  - '# derio-fr-automation + homelab-fr-automation: Repository → Variables: Read and write; Checks: Read-only; Actions: Read-only; Pull requests: Read-only'
  - '# derio-fr-automation: Repository → Issues: Read and write; Commit statuses: Read and write (if absent)'
  - '# each org: Settings → GitHub Apps → the App → Review request → Accept new permissions'
  - '# homelab-fr-automation installation: Repository access → add proxmox-cluster, omada-controller, homelab, ansible-pihole (keep kid-laptops)'
  - '# derio-fr-automation installation: confirm willikins, herdr-vertical-tabs, presentation-craft, vibe-kanban, runs-fr, frank are included'
  - '# live proof per org: mint an installation token from the PEM (RS256 JWT → POST /app/installations/<id>/access_tokens with {"permissions":{"organization_administration":"read"}}), then GET /organizations/<org>/settings/billing/usage?year=YYYY&month=M'
verify:
  - Each of the three orgs returns HTTP 200 with usageItems for the installation token. Any 403/404 → stop, return to the operator before merge.
status: pending
```

```yaml
# manual-operation
id: cicd-gitea-variable-semantics
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-10-18--cicd--github-preferred-gitea-fallback/06.yaml
when: PRE-MERGE — before the frank PR leaves draft.
why_manual: Proves two Gitea behaviours the watcher depends on, using admin credentials against the live instance.
commands:
  - '# in Gitea org derio-homelab (org var CI_AUTHORITY already set) create scratch repo ci-var-probe with has_actions=true'
  - '# set org variable PROBE=org and repo variable PROBE=repo; push .github/workflows/p.yml: on push, a job running `echo "${{ vars.PROBE }}"`'
  - '# POST /api/v1/repos/derio-homelab/ci-var-probe/branches {"new_branch_name":"sync-rerun-test","old_ref_name":"main"} with the workflow also listening on push branches sync-rerun-**'
  - '# delete org variable PROBE and the scratch repo afterwards'
verify:
  - The main push run prints `repo` (repo variable overrides org).
  - The API-created branch starts a push-triggered run.
status: pending
```

```yaml
# manual-operation
id: cicd-derio-net-gitea-org
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-10-18--cicd--github-preferred-gitea-fallback/06.yaml
when: After the frank PR merges, before the mirrors are created.
why_manual: Gitea org, bot users and tokens are forge UI/API state; tokens are SOPS bootstrap secrets.
commands:
  - '# create Gitea org derio-net (private); add stoa-bot to a team with write on all repos'
  - '# create user ci-budget; make it owner of derio-net and derio-homelab; mint a token with scopes write:repository,write:organization; sops-encrypt as secrets/ci-budget/ci-budget-gitea.yaml (ns tekton-pipelines, key token) and apply'
  - '# mint a read:admin-only token from an admin account; sops-encrypt as secrets/ci-budget/ci-budget-gitea-probe.yaml and apply'
  - '# org webhook on derio-net and derio-homelab: type gitea, events Status, URL http://el-gitea-listener.tekton-pipelines.svc.cluster.local:8080'
  - '# optional: secrets/ci-budget/ci-budget-telegram.yaml with the FRANK_C2 bot token + chat id'
verify:
  - kubectl -n tekton-pipelines get secret ci-budget-gitea ci-budget-gitea-probe
  - GET /api/v1/orgs/derio-net/hooks lists the status hook
status: pending
```

```yaml
# manual-operation
id: cicd-github-preferred-gitea-mirrors
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-10-18--cicd--github-preferred-gitea-fallback/06.yaml
when: After cicd-derio-net-gitea-org.
why_manual: One-time Gitea repo creation and history backfill with stoa-bot credentials, plus GitHub repo webhooks (pattern of cicd-stoa-site-gitea-mirror).
commands:
  - '# for each of derio-net/{willikins,herdr-vertical-tabs,presentation-craft,vibe-kanban,runs-fr} and derio-homelab/{proxmox-cluster,omada-controller,homelab,ansible-pihole}:'
  - '#   POST /api/v1/orgs/<org>/repos {"name":"<repo>","private":true,"default_branch":"main"}; PATCH /api/v1/repos/<org>/<repo> {"has_actions":true}'
  - '#   POST /api/v1/repos/<org>/<repo>/actions/variables/CI_AUTHORITY {"value":"github"}'
  - '#   git clone --mirror git@github.com:<org>/<repo>.git && git push --mirror ssh://git@192.168.55.209:2222/<org>/<repo>.git'
  - '#   GitHub repo webhook: push + pull_request → the github-listener URL, secret = the org webhook secret (derio-net-github-webhook-secret / derio-homelab-github-webhook-secret)'
verify:
  - A test push to each repo creates a matching ref on Gitea within a minute (github-listener PipelineRun Succeeded).
status: pending
```

```yaml
# manual-operation
id: cicd-gitea-readonly-secrets
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-10-18--cicd--github-preferred-gitea-fallback/06.yaml
when: After cicd-github-preferred-gitea-mirrors.
why_manual: Secret values live only in the source repos' GitHub settings/Infisical; Gitea Actions secrets are forge state.
commands:
  - '# for each gitea_secrets entry in apps/ci-budget/tiers.yaml (today: derio-net VK_PRIVATE_DEPLOY_KEY — confirm it is a read-only deploy key first):'
  - '#   PUT /api/v1/repos/<gitea_org>/<repo>/actions/secrets/<NAME> {"data":"<value>"}   (REPOSITORY secret on that repo only — never an org secret)'
verify:
  - GET /api/v1/repos/<gitea_org>/<repo>/actions/secrets lists each declared name; GET /api/v1/orgs/<gitea_org>/actions/secrets does not.
status: pending
```

```yaml
# manual-operation
id: cicd-ci-budget-go-live
layer: cicd
app: ci-budget
plan: docs/superpowers/plans/2026-10-18--cicd--github-preferred-gitea-fallback/06.yaml
when: After every repo PR for an org has merged and the spec Test Plan rows 1–8 pass.
why_manual: Deliberate operator decision to let the watcher write forge variables.
commands:
  - '# in apps/ci-budget/tiers.yaml set orgs.<org>.mode: live; PR, merge'
verify:
  - The next ci-budget-watcher heartbeat line for the org shows mode=live.
status: pending
```
