# GitHub-preferred CI with automatic Gitea fallback — design

**Issue:** derio-net/frank#875
**Layer:** cicd (Layer 21 CI/CD)
**Date:** 2026-10-18
**Status:** Draft

## Context

GitHub Actions on the three GitHub orgs (derio-net, derio-homelab,
agentic-stoa) runs on the free plan: 2,000 included private-repo minutes per
org per calendar month (UTC), macOS billed ×10, public repos free. On
2026-10-18 derio-net exhausted its minutes and jobs stopped starting ("job
was not started because … spending limit"). derio-homelab stands at 1,801 /
2,000 for October. agentic-stoa moved to Gitea Actions on Frank on 2026-07-22
by a manual, two-sided flip of the `CI_AUTHORITY` variable (manual op
`cicd-stoa-ci-authority-cutover`). Nothing watches GitHub minutes.

The machinery for running a GitHub repo's CI on Frank already exists for
agentic-stoa and for `derio-homelab/kid-laptops`:

- GitHub → Gitea **push-sync** triggers on `github-listener`
  (`apps/tekton/triggers/eventlistener-github.yaml:197` agentic-stoa main,
  `:240` kid-laptops main), PR heads pushed as `sync-pr-<N>`
  (`eventlistener-github.yaml:37`) on `opened|synchronize|reopened`. No
  trigger handles `closed`, so `sync-pr-<N>` refs accumulate on Gitea today;
  that existing behaviour is unchanged by this design.
- Per-org GitHub App installation tokens minted by ESO ClusterGenerators
  (`apps/tekton/manifests/clustergenerator-stoa-github-app.yaml`,
  `clustergenerator-derio-homelab-github-app.yaml` — kid-laptops only,
  contents/metadata read + statuses write; the derio-net App `github-app-derio`
  is declared in `apps/secure-agent-pod/manifests/clustergenerator-github-app.yaml:24`,
  its PEM is in `tekton-pipelines` via
  `secrets/github-app/github-app-derio-key-tekton.yaml`, and it is already
  consumed there by `apps/tekton/manifests/externalsecret-frank-gitops-push.yaml`).
  A scoped generator on the same App already exists:
  `apps/argocd-extras/manifests/clustergenerator-github-app-derio-argocd-read.yaml:30-33`.
- `mirror-reconcile` repairs missed syncs from `MAIN_REPOS` / `PR_REPOS`
  (`apps/tekton/manifests/mirror-reconcile.yaml:360-372`, `:389-400`), its
  `plan` and `push` stages each carrying per-org tokens
  (`:401-408`, `:419-424`); the lists are kept equal to the trigger filters by
  `scripts/tests/test_ci_mirror_resilience.py:183`, whose PR-repo extractor
  hard-codes `agentic-stoa/` (`:114`) and whose org→Secret map is asserted at
  `:208-226`. The kid-laptops trigger name is pinned by
  `scripts/tests/test_kid_laptops_mirror_wiring.py:45`.
- `ci-delivery-check` reads the same lists
  (`apps/tekton/manifests/ci-delivery-check.yaml:308-318`), mounts a
  stoa/homelab/gitea token map (`:265`, `:328-338`), and compares forwarded
  statuses for `agentic-stoa/` repos only (`:85`).
- Declared webhook delivery paths in `apps/tekton/webhooks.yaml`, enforced by
  `scripts/tests/test_webhook_delivery_paths.py`.
- The Gitea → GitHub **status bridge** (`gitea-status-bridge` trigger,
  `apps/tekton/triggers/eventlistener.yaml:66-77`) → `stoa-status-bridge`
  pipeline → `github-status` task.
- One instance-level act_runner on pc-1, capacity 2, single label
  `ubuntu-latest` (`apps/gitea-runner/manifests/files/config.yaml:13-20`),
  privileged DinD with a 40Gi emptyDir
  (`apps/gitea-runner/manifests/deployment.yaml:86-90`).

Gaps this design closes, each found in the code:

1. The status bridge filters `full_name.startsWith('agentic-stoa/')`
   (`eventlistener.yaml:75`) and `github-status` authenticates with the
   agentic-stoa token only (`apps/tekton/tasks/github-status.yaml:5,53`), so
   no derio-homelab or derio-net Gitea result reaches GitHub.
2. The generic `gitea-push` trigger excludes only `agentic-stoa/` and
   `derio-homelab/` (`eventlistener.yaml:28-30`). This is **not** a live bug —
   that trigger's only delivery path is a repo hook on `gitea_admin/test-ci`
   (`apps/tekton/webhooks.yaml:118-130`), and this design adds no push hook
   from the new Gitea org — but `derio-net/` is excluded as well, as defence in
   depth against the double-run gotcha (`docs/runbooks/frank-gotchas/tekton.md`).
3. None of the nine `github-preferred` repos below gates a single job on
   `CI_AUTHORITY` except `derio-homelab/ansible-pihole` (5 gates); none
   triggers on `sync-pr-**`. Measured 2026-10-18 via the contents API. A
   flip of the GitHub variable therefore stops nothing on GitHub today.
4. `agentic-stoa/cnc-frd` and `cnc-fru` `release.yml` carry no gate (known
   gap recorded in `cicd-stoa-ci-authority-cutover`), so both forges run them.
5. Nothing alerts on the runner being offline, on queued jobs, or on pc-1
   `/var` (19% free; the DinD emptyDir can grow to 40Gi). No rule in
   `apps/grafana-alerting/manifests/alert-rules-cm.yaml` reads
   `node_filesystem_*`; `layer-25-cicd-down` (`:2420`) watches Deployment
   availability in `gitea|tekton-pipelines|zot`, not the runner's Gitea-side
   registration.

### Platform facts this design relies on

Verified from documentation on 2026-10-18; items marked **[PRE-MERGE]** are
re-verified live before merge (§8), because documentation permission tables
are not proof that an App installation token is accepted.

- `GET /organizations/{org}/settings/billing/usage` (enhanced billing
  platform) returns usage items with `date`, `product`, `sku`, `quantity`,
  `repositoryName`; query `year`, `month`, `day`. GitHub App permission:
  organization `Administration`: read — in an installation token's
  `permissions` map the key is **`organization_administration`**
  (`administration` is the repository permission). **[PRE-MERGE]**: an
  installation token minted from each org's App reads this endpoint.
- `POST/PATCH /repos/{owner}/{repo}/actions/variables[/{name}]`: repository
  `Variables`: write (key `variables`).
- Workflow runs and jobs: `actions: read`. Check-run annotations
  (`/repos/{o}/{r}/check-runs/{id}/annotations`): `checks: read`. Workflow
  files via the contents API: `contents: read`. Open PRs: `pull_requests: read`.
- Organization Actions variables are **not** visible to private repos on the
  free plan (observed on agentic-stoa 2026-07-22), so the GitHub side of the
  authority is per repo.
- Gitea Actions variables exist at org and repo level, and a repo-level
  variable overrides the org-level one of the same name. **[PRE-MERGE]**:
  proven on a scratch Gitea repo.
- A branch created through Gitea's API fires a `push` event that triggers
  Gitea Actions `on: push` workflows. **[PRE-MERGE]**: proven on a scratch
  Gitea repo.
- ESO's `GithubAccessToken` generator (chart 2.1.0) takes optional
  `repositories` and `permissions`, so a token can be minted narrower than the
  App's grant — but the scope is a property of the **ClusterGenerator**, not
  of the consuming ExternalSecret.

## Requirements

R1. A tier config in git declares, per GitHub org: the included minutes (2,000), the flip threshold (85%), the Gitea org, the watcher mode (`dry-run` or `live`), and per private repo a tier — `github-only`, `gitea-only` or `github-preferred` — plus an optional operator pin of the repo's authority. A repo absent from the config is `github-only`; public repos are always `github-only`.
R2. In a `github-preferred` repo only check jobs (tests, lint, build-verify) fall back to Gitea. Mutating jobs (release, publish, deploy, auto-tag, image push, acceptance-report issue upsert) and every `macos-*` job stay on GitHub regardless of authority.
R3. A check job may fall back while using a secret only if that secret is read-only (a deploy key, a read token). Such secrets are listed per repo in the tier config and provisioned as Gitea repository secrets on that repo only (never org secrets, which every repo's workflows in the Gitea org could read); a job needing a write-capable secret stays on GitHub.
R4. derio-net's five `github-preferred` repos (willikins, herdr-vertical-tabs, presentation-craft, vibe-kanban, runs-fr) are mirrored into a `derio-net` Gitea org: main and PR heads (`sync-pr-<N>`) are push-synced on every GitHub push, repaired by `mirror-reconcile`, checked by `ci-delivery-check`, and declared in `apps/tekton/webhooks.yaml`.
R5. derio-homelab's four `github-preferred` repos (proxmox-cluster, omada-controller, homelab, ansible-pihole) are mirrored the same way into the existing `derio-homelab` Gitea org, alongside kid-laptops.
R6. Gitea Actions commit statuses from all three orgs' mirrors reach the same sha on GitHub as `gitea-actions/<context>` statuses, each org written with its own org's token; a missing token for one org blinds only that org, and `ci-delivery-check` verifies the forwarding for all three.
R7. A budget watcher on Frank reads each org's billing usage at least hourly and computes included-minute consumption for the current UTC calendar month over private repos (Linux ×1, Windows ×2, macOS ×10).
R8. When an org reaches ≥85% of its included minutes, the watcher moves that org's `github-preferred` repos to `CI_AUTHORITY=gitea`; the authority stays `gitea` for the rest of that UTC calendar month and returns to `github` once the month changes.
R9. Flips are ordered so that no window exists where neither forge runs a job: toward Gitea, the Gitea side is set first, then GitHub; toward GitHub, GitHub first, then Gitea. Both sides are per-repo variables, so a flip touches only the repos it flips; `gitea-only` repos in the same Gitea org are never affected.
R10. The watcher is idempotent (a run that finds both forges already at the desired authority writes nothing) and has a dry-run mode, per org, that computes and notifies without writing. Every org ships in dry-run; going live is a one-line git change per org.
R11. The watcher refuses to move a repo TOWARD Gitea while its workflows fail the gate-coverage check (R16) — on both forges — and says so in its notification. A move back to GitHub is never refused (it is the safe direction).
R12. Backstop: within 10 minutes of a GitHub job in a `github-preferred` repo failing with the "spending limit" annotation, the watcher flips that org (R8, R9) and re-runs the affected commit on Gitea — PR heads and default-branch commits alike.
R13. Every flip, would-flip (dry-run), refusal and backstop trigger is sent to Telegram once (not once per run); every watcher run emits a heartbeat log line, and a Grafana rule pages when the heartbeat stops.
R14. The current authority of every `github-preferred` repo is readable from GitHub alone: the watcher sets the repo variable `CI_AUTHORITY` explicitly to `github` or `gitea` (never leaves it unset), so a consumer such as willikins' `doc-pr` can read it with `gh variable get CI_AUTHORITY`. A follow-up issue for the doc-pr side is filed in derio-net/willikins.
R15. On the 1st of each month a report is opened as an issue in derio-net/frank: per org and per repo, the previous month's billed minutes (each job rounded up to a whole minute by GitHub's billing, macOS ×10), the share consumed by GitHub-pinned jobs, the current tier, a proposed tier change with its reason, billed repos that the tier config does not list, and the gate-coverage gaps. Re-running it for the same month updates the same issue.
R16. A gate-coverage checker reports, for every workflow in a `github-preferred` or `gitea-only` repo, each job that lacks a forge gate, each fallback-eligible job that a Gitea runner cannot serve or that cannot work on Gitea, and each fallback workflow missing the Gitea-only re-run triggers. It runs offline against a checkout and is reused by the watcher (R11) and the report (R15).
R17. The nine `github-preferred` repos and `agentic-stoa/cnc-frd` / `cnc-fru` `release.yml` are brought to full gate coverage, one PR per repo.
R18. The act_runner stays on pc-1 only, capacity 2; its `runner` container memory limit rises from 1Gi to 2Gi.
R19. Alerts fire when the Gitea runner is offline, when a Gitea Actions job has waited too long for a runner, and when pc-1 `/var` free space runs low.

## Design

### 1. Tier config (R1, R2, R3)

New ArgoCD Application `ci-budget` (raw manifests, kustomize), deploying into
the existing `tekton-pipelines` namespace — the GitHub App private keys
(`github-app-stoa-key`, `github-app-homelab-key`, `github-app-derio-key`)
already live there, and ESO resolves a generator's key in the consumer's
namespace (storage-secrets-ssa gotcha). The config is
`apps/ci-budget/tiers.yaml`, shipped to the CronJobs by kustomize
`configMapGenerator` (hash-suffixed, so a tier edit changes the CronJob spec).
The app runs `prune: true`; its only stateful object, the `ci-budget-state`
ConfigMap (§4), is created by the watcher and not part of the manifests.

```yaml
version: 1
orgs:
  derio-net:
    included_minutes: 2000
    threshold_pct: 85
    gitea_org: derio-net
    mode: dry-run            # dry-run | live, per org (R10)
    repos:
      willikins:            {tier: github-preferred}
      herdr-vertical-tabs:  {tier: github-preferred}
      presentation-craft:   {tier: github-preferred}
      vibe-kanban:          {tier: github-preferred, gitea_secrets: [VK_PRIVATE_DEPLOY_KEY]}
      runs-fr:              {tier: github-preferred}
  derio-homelab:
    included_minutes: 2000
    threshold_pct: 85
    gitea_org: derio-homelab
    mode: dry-run
    repos:
      kid-laptops:          {tier: gitea-only}
      proxmox-cluster:      {tier: github-preferred}
      omada-controller:     {tier: github-preferred}
      homelab:              {tier: github-preferred}
      ansible-pihole:       {tier: github-preferred}
  agentic-stoa:
    included_minutes: 2000
    threshold_pct: 85
    gitea_org: agentic-stoa
    mode: dry-run            # no github-preferred repos: nothing to write
    repos:                   # every currently mirrored agentic-stoa repo
      cnc-fr: {tier: gitea-only}
      # …
# optional per repo: pin_authority: github|gitea — an operator override that
# wins over the computed authority (used for the live single-repo test and
# for manual holds); a pin never stamps the month (§4 step 4).
```

Which jobs are check jobs is **not** in the tier config: it is expressed in
the workflows themselves by which gate a job carries (§6). The tier config
says which repos the watcher may flip. `gitea_secrets` is the declared list
of read-only secrets mirrored as Gitea **repository** secrets on that repo only (R3) — an org secret would expose, e.g., vibe-kanban's deploy key to every derio-net mirror's workflows. Each name is also listed in a top-level `readonly_secrets:` allowlist (`{name, repo, kind: deploy-key|read-token, note}`), and names matching `PAT|WRITE|ADMIN|PUSH` are rejected by the tier-config test; the checker (§6)
reports every `secrets.X` used by an authority-gated job that is neither
listed there nor `GITHUB_TOKEN` (and flags `GITHUB_TOKEN` itself when it is
used against GitHub, see §6).

### 2. Mirroring derio-net and the four derio-homelab repos (R4, R5)

Following the kid-laptops precedent
(`eventlistener-github.yaml:211-221`: "everything underneath differs: a
different webhook HMAC secret, a different App installation token, and
therefore a different pull-sync Pipeline"):

- **Gitea:** a `derio-net` org; one private repo per mirrored repo with
  Actions enabled (`has_actions: true` — the unit is not retrofitted onto
  repos created after instance-level `actions.ENABLED`, tekton gotcha) and a
  repo-level variable `CI_AUTHORITY=github` set at creation; history
  backfilled by `git push --mirror` (pattern of `cicd-stoa-site-gitea-mirror`);
  `stoa-bot` (the SSH identity the sync pipelines and `mirror-reconcile` push
  with, `mirror-reconcile.yaml:6`) granted write on the new org. The four
  homelab repos are created in the existing `derio-homelab` Gitea org the
  same way. All manual ops (§8).
- **Tokens:** a new `derio-net-github-mirror` ExternalSecret from a new
  ClusterGenerator `github-app-derio-mirror` on the derio-net App, scoped to
  the five repos with `permissions: {contents: read, pull_requests: read,
  statuses: write, metadata: read}`. The existing `github-app-derio`
  generator in secure-agent-pod is untouched. The homelab App's installation
  is widened from kid-laptops to the five homelab repos and gains
  `pull_requests: read` (manual op); `github-app-derio-homelab` keeps its
  name, and `derio-homelab-github-mirror` its consumers.
- **Triggers on `github-listener`:**
  - `derio-net-main-sync` and `derio-net-pr-sync` (repo-list filter,
    `derio-net-github-webhook-secret`, which already exists —
    `apps/tekton/manifests/externalsecret-derio-net-github-webhook-secret.yaml`);
  - the kid-laptops main-sync trigger generalised to a repo list and renamed
    `derio-homelab-main-sync`, with `TRIGGER_NAME` in
    `scripts/tests/test_kid_laptops_mirror_wiring.py:45` updated in the same
    change (the guard's assertions are kept, only the name moves), plus a new
    `derio-homelab-pr-sync`.
  - PR triggers write `refs/heads/sync-pr-<N>` on
    `opened|synchronize|reopened`, exactly like the stoa ones.
- **Pipelines:** `derio-net-pull-sync` cloned from
  `apps/tekton/pipelines/derio-homelab-pull-sync.yaml`, reading
  `derio-net-github-mirror`. (One shared parameterised pipeline was
  considered; the precedent above kept them separate so a token change for
  one org cannot break another's sync, and that reasoning holds.)
- **Gitea push routing:** the generic `gitea-push` filter adds
  `!body.repository.full_name.startsWith('derio-net/')` (defence in depth,
  gap 2). No Tekton CI pipeline is added for the mirrored repos; their CI is
  Gitea Actions.
- **`webhooks.yaml`:** a repo-scoped GitHub webhook entry (`push`,
  `pull_request`) per mirrored repo — repo scope, not org scope, so public
  derio-net repos (super-fr ran ~41k minutes in October) never reach the
  listener; and a Gitea org webhook entry (`status`) for the `derio-net` and
  `derio-homelab` Gitea orgs feeding the status bridge.
- **`mirror-reconcile`:** both lists grow by the nine repos; `GITHUB_TOKEN_DERIO_NET`
  (optional `secretKeyRef` on `derio-net-github-mirror`, the pattern at
  `mirror-reconcile.yaml:404-408`) is added to **both** the `plan` and `push`
  stages; `plan.py` and `push.sh` select the token by owner.
- **`ci-delivery-check`:** lists grow; a `derio-net` token mount and token-map
  entry are added (`:265`, `:328-338`); the `agentic-stoa/`-only status
  comparison (`:85`) becomes "every org in the token map", so forwarded
  statuses are checked for all three orgs (R6).
- **Guards extended, none weakened:**
  `test_ci_mirror_resilience.py:114` (PR-repo extractor generalised from
  `agentic-stoa/` to any mirrored org), `:183`, `:208-226` (org→Secret map now
  three orgs, both stages), `test_kid_laptops_mirror_wiring.py` (renamed
  trigger), `test_webhook_delivery_paths.py` (new entries),
  and the ci-delivery-check test for the widened status comparison.

### 3. Status bridge for three orgs (R6)

- The trigger filter becomes `full_name.startsWith` any of the three orgs,
  still excluding `context` `tekton*` (`eventlistener.yaml:74-76`).
- `github-status` gains two optional token env vars beside its current one
  (`derio-homelab-github-mirror`, `derio-net-github-mirror`, each
  `optional: true`) and selects by the `repo-full-name` owner; an owner with
  no token fails that one TaskRun loudly. Its existing callers
  (`stoa-status-bridge`, `hum-ci`, `content-factory-ci`, `stoa-blog-ci`,
  `cnc-ci`) all pass agentic-stoa repos and get the existing token, so their
  behaviour is unchanged. The `stoa-status-bridge` Pipeline keeps its name
  (renaming would orphan its PipelineRun history and its idle-rule
  tombstones); its description is updated.
- `gh_state` overlay unchanged.

### 4. Budget watcher (R7–R14)

A CronJob `ci-budget-watcher` (`*/10 * * * *`, `concurrencyPolicy: Forbid`),
digest-pinned stock `python:3-alpine`, script from the configMapGenerator
(the crowdsec-canary shape: no custom image). All dates and months are UTC.

**Tokens.** Two ClusterGenerators per org on that org's existing App
(permissions added by manual op `cicd-ci-budget-app-permissions`):

| Generator | Orgs | Permissions | Repositories |
|---|---|---|---|
| `github-app-<org>-ci-billing` | all three | `organization_administration: read`, `metadata: read` | none listed (org endpoint) |
| `github-app-<org>-ci-authority` | derio-net, derio-homelab | `variables: write`, `actions: read`, `checks: read`, `contents: read`, `metadata: read` | every repo of that org in `tiers.yaml` |

For agentic-stoa (no `github-preferred` repo, never written) the report reads
workflow files with the existing `stoa-github-mirror` token, which already
has `contents: read` on the mirrored stoa repos. Mirror, status and push
tokens never carry the billing or variables permissions.

Gitea side: a `ci-budget` Gitea bot with org-owner rights on `derio-net` and
`derio-homelab` and a token scoped to repository/organization write
(`ci-budget-gitea` Secret, SOPS manual op) — not the Gitea admin password.
Runner probes use a separate token with only `read:admin` scope
(`ci-budget-gitea-probe`), because the instance runner and its job queue are
listed only under the admin API (§7).

**State.** `ci-budget-state`, a ConfigMap the watcher creates and updates
(Role: `get/create/update/patch` on that one name). It holds per org: the
last billing read time and `pct`, the set of notification keys already sent,
and the backstop run ids already handled. Losing it costs at most one
repeated notification and one extra billing read. The authority itself and
the month lock live on the forges (below), so they survive a lost ConfigMap.

**Each run, per org:**

1. Load `tiers.yaml` and `ci-budget-state`.
2. **Usage** — read the billing usage when the state's last read is ≥55
   minutes old (hourly cadence, R7) or a backstop hit is pending. Sum Actions
   minutes over private repos, Linux ×1, Windows ×2, macOS ×10 (SKU names
   matched case-insensitively; an unknown Actions SKU fails the run rather
   than being guessed). Record `pct = used / included` and the GitHub-pinned
   share (minutes from repos/jobs that never fall back — §5 uses the same
   split).
3. **Backstop** (every run): list workflow runs of the org's
   `github-preferred` repos with conclusion `failure` created in the last 30
   minutes **and** at or after the start of the current UTC month (a run from
   the previous month never stamps the new one); skip run ids already in the
   state; for their jobs read check-run annotations; a match on
   `spending limit` (case-insensitive) is a backstop hit.
4. **Desired authority, per repo:** `pin_authority` if set; else `gitea` if
   `pct ≥ threshold`, a backstop hit, or the Gitea org variable
   `CI_BUDGET_MONTH` equals the current `YYYY-MM`; else `github`. A computed
   (non-pinned) move to `gitea` sets `CI_BUDGET_MONTH` to the current month,
   so the authority stays `gitea` for the rest of the month (R8) and the next
   month's first run returns it to `github`.
5. **Coverage:** for a move toward `gitea` only, run the R16 checker against
   each repo's default branch (contents API, no clone). A repo with gaps keeps
   its current authority on **both** forges and is named in a refusal
   notification (R11). A move back to `github` is never gated.
6. **Apply** (only when the org's `mode` is `live`), per repo whose desired
   authority differs from what the two variables say, ordered (R9):
   - toward `gitea`: Gitea **repo** variable `CI_AUTHORITY=gitea` → read back
     → GitHub repo variable `CI_AUTHORITY=gitea` → read back;
   - toward `github`: GitHub repo variable `CI_AUTHORITY=github` → read back
     → Gitea repo variable `CI_AUTHORITY=github` → read back.
   A failed write or read-back stops that repo's sequence there (leaving at
   worst "both run", never "neither") and fails the Job. Gitea **org**
   variables are never written for authority, so `gitea-only` repos (kid-laptops,
   which relies on the derio-homelab org default) are never affected. Each
   `github-preferred` repo's GitHub variable is written explicitly on first
   sight, `github` included (R14). Idempotent: when both variables already
   match, nothing is written (R10).
7. **Backstop re-run** (after a backstop flip): for each affected run, create
   the Gitea branch `sync-rerun-<sha12>` at the run's head sha. Gitea fires
   `push` for the created branch; every fallback workflow triggers on
   `push: branches: ['sync-pr-**', 'sync-rerun-**']` (§6), so the gated check
   jobs run on Gitea at that sha — PR heads and default-branch commits alike
   — and the status bridge posts their results to that sha on GitHub. The
   watcher deletes `sync-rerun-*` branches older than 24 hours. Whether
   Gitea fires a `paths:`-filtered push workflow on a freshly created branch
   is proven by the PRE-MERGE op `cicd-gitea-variable-semantics` (§8).
8. **Notify** (Telegram, `ci-budget-telegram` Secret, optional — absent means
   heartbeat-only, like crowdsec-canary). Each event has a key — `flip:<org>/<repo>:<authority>:<YYYY-MM>`,
   `would-flip:<org>/<repo>:<authority>:<YYYY-MM>`, `refuse:<org>/<repo>:<sha of gap list>`,
   `backstop:<run-id>` — and is sent only if its key is not in the state, so
   a dry-run org over threshold gets one would-flip message a month, not one
   every 10 minutes. Flip and would-flip messages include `pct` and the
   GitHub-pinned share.
9. **Heartbeat:** one log line per run,
   `ci-budget-watcher verdict=<ok|flipped|would-flip|refused|error> org=… pct=… mode=…`,
   to stdout → fluent-bit → VictoriaLogs (`_msg` field — the Frank field,
   not Hop's `log`).

Grafana rule `ci-budget-heartbeat-stale` (feature-health folder,
`telegram_direct`, `lt 1` over 40m on the heartbeat count, modelled on
`crowdsec-canary-heartbeat-stale` at `alert-rules-cm.yaml:3273`, uid ≤40 chars).

**willikins doc-pr (R14):** a follow-up issue is filed in derio-net/willikins
describing the hazard (GitHub shows only `skipped` checks while Gitea is
authoritative, so `gh pr checks` can go green before `gitea-actions/*`
statuses arrive) and the interface: `gh variable get CI_AUTHORITY` per repo.

### 5. Monthly report (R15)

CronJob `ci-budget-report` (`0 6 1 * *`), same image and config. Tokens: each
org's `ci-billing` generator (usage), each org's `ci-authority` generator or
`stoa-github-mirror` (workflow files for the checker), and a ClusterGenerator
`github-app-derio-frank-issues` on the derio-net App scoped to
`derio-net/frank` with `issues: write` (permission added in the same manual
op).

For each org, the previous month's usage by `repositoryName` (GitHub's billed
quantities already round each job up to a whole minute), macOS ×10, split
into the fallback-eligible and GitHub-pinned share. Billing line items are
the source of the repo list, so a billed repo the tier config does not know
is found without any repo-listing permission. Proposal rules, each stated in
the issue with its reason:

- a `github-preferred` repo that alone used ≥50% of its org's included
  minutes → propose `gitea-only`;
- an org that crossed its threshold → ranked consumers, and the pinned share
  that kept billing GitHub after the flip (the §9 risk);
- a billed repo absent from `tiers.yaml` → propose `github-preferred`, or
  `github-only` if all its billed minutes are macOS;
- a tiered repo whose visibility is now public (read with the org's
  `ci-authority` token where that token can see it) → propose removing it;
- gate-coverage gaps (R16) for every `github-preferred` and `gitea-only` repo.

Output: an issue in derio-net/frank titled `CI tier review <YYYY-MM>`, label
`ci-tiers`, found by title on re-run and edited (R15). The operator acts by
editing `tiers.yaml`.

### 6. Gate convention and coverage checker (R2, R11, R16, R17)

Two job-level gates, combined with any existing `if:` by `&&`:

- **authority gate** (fallback-eligible check jobs):
  `(vars.CI_AUTHORITY || 'github') == (github.server_url == 'https://github.com' && 'github' || 'gitea')`
  — the expression already in use in kid-laptops and ansible-pihole.
- **GitHub pin** (mutating jobs, `macos-*` jobs):
  `github.server_url == 'https://github.com'`. Without it a `macos-*` job
  mirrored to Gitea queues forever (no runner carries that label), and a
  mutating job runs twice.

A job-level `if:` cannot read `matrix`, so a matrix job whose legs mix
`macos-*` and Linux runners is **split** into a Linux job (authority gate)
and a macOS job (GitHub pin). Every workflow containing an authority-gated job
that is triggered by `pull_request` or `push` also triggers on
`push: branches: ['sync-pr-**', 'sync-rerun-**']` (those branches exist only
on Gitea, so GitHub never fires on them).

The checker, `scripts/ci_gate_coverage.py`, parses workflow YAML (a checkout
directory or a dict of fetched files) and reports per job:

- `ok`;
- `ungated` — neither gate as a top-level `&&` conjunct of the job's `if:`
  (a gate inside `||` or under `!` does not count);
- `malformed-gate` — a conjunct that mentions `CI_AUTHORITY` but is not the
  exact authority gate (typo, other case, missing `|| 'github'` default);
- `fallback-on-unserved-label` — an authority-gated job whose `runs-on` is not
  a label in `apps/gitea-runner/manifests/files/config.yaml`;
- `fallback-runs-on-expression` — an authority-gated job whose `runs-on` is an
  expression (no static label to check, e.g. `${{ matrix.os }}`);
- `fallback-secret-not-mirrored` — an authority-gated job using a secret not
  in the repo's `gitea_secrets` (job, workflow-level `env`/`defaults`, and
  `secrets: inherit` on a reusable-workflow call all count);
- `fallback-github-token-to-github` — an authority-gated job passing
  `secrets.GITHUB_TOKEN`/`github.token` to `gh`, `api.github.com`, a
  `github.com` checkout of another repo, or any action input (`with:`), from
  the job or workflow-level `env` (on Gitea that token is Gitea's);
- `missing-rerun-triggers` — per workflow, pushes to `sync-pr-*`/`sync-rerun-*`
  would not fire it (an unfiltered `push` covers them; a tags-only `push` or a
  `branches-ignore` matching them does not).

Workflows are read from `.github/workflows/` and `.gitea/workflows/`; local
reusable-workflow callees are resolved from the same file set.

For a `gitea-only` repo every job must carry the authority gate or the GitHub
pin. The same module is loaded by the watcher and the report (copied into the
configMapGenerator; a test asserts the copy equals the source).

The runner gains the label `ubuntu-24.04`, mapped to the pinned
`gitea/runner-images:ubuntu-24.04` tag (not the floating `ubuntu-latest`, which
moves to the next LTS); other version labels stay unserved and flagged.

**Cross-repo PRs (R17).** One PR per repo, each in its own fr workspace in its
own repo, applying the convention above and passing the checker against its
own branch; each PR body cites this spec.

| Repo | Clone |
|---|---|
| derio-net/willikins | `~/Docs/projects/DERIO_NET/willikins` |
| derio-net/herdr-vertical-tabs | `~/Docs/projects/DERIO_NET/herdr-vertical-tabs` |
| derio-net/presentation-craft | `~/Docs/projects/DERIO_NET/presentation-craft` |
| derio-net/vibe-kanban | `~/Docs/projects/DERIO_NET/vibe-kanban` |
| derio-net/runs-fr | `~/Docs/projects/DERIO_NET/runs-fr` |
| derio-homelab/proxmox-cluster | `~/Docs/projects/HOMELAB/proxmox-cluster` |
| derio-homelab/omada-controller | `~/Docs/projects/HOMELAB/omada-controller` |
| derio-homelab/homelab | `~/Docs/projects/HOMELAB` (repo root; submodules untouched) |
| derio-homelab/ansible-pihole | `~/Docs/projects/HOMELAB/ansible-pihole` |
| agentic-stoa/cnc-frd | `~/Docs/projects/STOA/cnc-frd` (`release.yml` only) |
| agentic-stoa/cnc-fru | `~/Docs/projects/STOA/cnc-fru` (`release.yml` only) |

In cnc-frd/cnc-fru `release.yml` the jobs get the **GitHub pin**, following
this section's rule for mutating jobs: the release keeps publishing from
GitHub and keeps firing `cnc-image-ready` (which drives
`cnc-image-promotion`, `eventlistener-github.yaml:332-346`) exactly as today,
and stops the duplicate run on Gitea. Moving CNC releases onto the shared
privileged DinD is not part of this change.

### 7. Runner (R18, R19)

- `apps/gitea-runner/manifests/deployment.yaml:62`: runner limit 1Gi → 2Gi.
  Node selector and `capacity: 2` unchanged.
- **Runner offline / queue wait:** each watcher run also reads, with the
  `read:admin` probe token, the instance runners (online, last seen) and the
  jobs in `waiting` state with their age, and logs
  `ci-runner-probe runners_online=N oldest_waiting_s=S waiting=W`. The exact
  admin endpoints are confirmed against the live Gitea version (chart
  12.5.0) by a read-only call during implementation. If that version lists no
  runners, runner liveness falls back to
  `kube_deployment_status_replicas_unavailable{namespace="gitea-runner"}`
  plus the queue-age signal (a queued job with no taker is the user-visible
  symptom of an offline runner either way). Grafana rules (LogsQL,
  `queryType: stats`): `layer-25-runner-offline` (`runners_online < 1` for
  10m) and `layer-25-runner-queue-wait` (`oldest_waiting_s > 900` for 10m).
- **pc-1 `/var`:** `layer-25-pc1-var-low` on
  `node_filesystem_avail_bytes{mountpoint="/var"} / node_filesystem_size_bytes`
  for pc-1 `< 0.15` for 15m (warning). The series' presence and labels are
  checked live (read-only) before the rule is written; a rule on a series
  that does not exist would be silent under `noDataState: OK`.

### 8. Manual operations

Recorded as `# manual-operation` blocks in the plan, synced to the runbook.
**[PRE-MERGE]** ops gate the merge (the #762 shape): the PR does not leave
draft until they pass.

- `cicd-ci-budget-app-permissions` **[PRE-MERGE]** — add organization
  `Administration: read` to derio-fr-automation, homelab-fr-automation and
  stoa-fr-automation; add repository `Variables: write`, `Checks: read`,
  `Actions: read`, `Pull requests: read` to derio-fr-automation and
  homelab-fr-automation; add `Issues: write` (derio-net/frank) and
  `Statuses: write` to derio-fr-automation if absent; re-approve each
  installation; widen homelab-fr-automation to the five homelab repos and
  confirm derio-fr-automation covers the five derio-net repos and
  derio-net/frank. Then mint an installation token from each PEM and call
  `/organizations/<org>/settings/billing/usage` — if any org's App token is
  refused, stop and return to the operator before merging.
- `cicd-gitea-variable-semantics` **[PRE-MERGE]** — on a scratch Gitea repo
  in an org with org variable `CI_AUTHORITY=gitea`: set a repo variable
  `github`, push a workflow echoing `vars.CI_AUTHORITY`, confirm `github`;
  create a branch through the API and confirm the push-triggered run starts.
  Delete the scratch repo.
- `cicd-derio-net-gitea-org` **[PRE-MERGE]** — create the `derio-net` Gitea org; grant
  `stoa-bot` write on it; create the `ci-budget` bot (org owner on derio-net
  and derio-homelab) and its token, and the `read:admin` probe token (SOPS
  secrets `ci-budget-gitea`, `ci-budget-gitea-probe`); add the org `status`
  webhook on derio-net and on derio-homelab.
- `cicd-github-preferred-gitea-mirrors` **[PRE-MERGE]** (except the GitHub
  repo webhooks, added after merge) — the merged reconciler and delivery check
  list the nine repos at once, so they must already exist on Gitea — create the nine Gitea repos with
  `has_actions: true` and repo variable `CI_AUTHORITY=github`; backfill; add
  the nine GitHub repo webhooks.
- `cicd-gitea-readonly-secrets` — set each `gitea_secrets` entry as a Gitea
  repository secret on its own repo.
- `cicd-kid-laptops-template-orphan-delete` — delete the TriggerTemplate the
  kid-laptops trigger rename leaves behind under `prune: false`.
- `cicd-ci-budget-go-live` — after every repo PR has merged and the
  post-merge rows pass, change an org's `mode` to `live` in git.

### 9. Risks

- **pc-1 is a SPOF** (Gitea, zot, sync pods, the runner). Accepted by the
  operator; the standby load is ~600–1,000 job-minutes a month on top of
  ~1,300. The queue-wait alert is the early warning.
- **DinD trust boundary.** Check jobs only, read-only secrets only (R2, R3)
  keep derio-net's deploy credentials off the shared privileged daemon.
- **The 15% after a flip must carry every GitHub-pinned job.** 15% of 2,000
  is 300 minutes; willikins' macOS leg alone was 1,280 equivalent minutes in
  October. If pinned jobs exhaust the remainder, releases and macOS legs stop
  until the reset, and the backstop cannot help (they are pinned). The flip
  notification and the monthly report show the pinned share so the operator
  can lower the threshold or move work; the threshold stays the operator's
  85% here.
- **Billing lag.** The usage endpoint can trail real consumption; the
  backstop (R12) covers the tail.
- **Mirror lag.** Webhook syncs are fast; a repaired sync can take 15–25
  minutes. During a flip a PR may briefly show only `skipped` GitHub checks
  (R14's doc-pr follow-up).
- **`sync-pr-<N>` accumulation** on Gitea is pre-existing (no close trigger)
  and grows with nine more repos; not addressed here.

## Verification

strategy: live
gate: devops
- tier-config-declares-repo-tiers: none — offline tests in CI (`scripts/tests/`) parse `apps/ci-budget/tiers.yaml` and assert its schema and the read-only-secret rule
- gate-coverage-checker-flags-gaps: none — offline tests in CI run the checker on fixture workflows
- runner-memory-and-placement: none — a manifest guard in CI asserts the limit, node selector, capacity and labels
- ci-fallback-mirrors-derio-orgs: live — needs real GitHub webhooks, the App installations and the Gitea orgs, which exist only after the manual ops; CI asserts the trigger/reconcile wiring offline
- ci-fallback-status-reaches-github: live — needs a real Gitea Actions run and a write to GitHub with each org's token
- ci-budget-flips-at-threshold: live — the decision logic is unit-tested in CI, but the ordered writes to both forges' variables can only be shown against the live APIs
- ci-budget-backstop-spending-limit: live — the annotation is produced only by GitHub refusing a job; CI tests the detector on captured payloads
- ci-budget-notifies-and-heartbeat: live — Telegram delivery and the VictoriaLogs → Grafana dead-man exist only on the cluster
- ci-authority-readable-on-github: live — the repo variables are GitHub state written by the deployed watcher
- ci-tier-monthly-report: live — the report reads the live billing API and writes a real issue
- workflows-carry-forge-gates: live — the eleven workflow PRs live in other repos and merge independently of this one
- runner-health-alerts: live — the rules read live VictoriaLogs/VictoriaMetrics series whose presence must be observed on the cluster

## Test Plan

Post-merge, operator-driven (devops gate). Rows marked `none` above are
covered by CI.

1. **Mirrors (R4, R5).** After the manual ops: push to a PR in one derio-net
   and one derio-homelab repo; the Gitea mirror shows `sync-pr-<N>` at the PR
   head sha; `mirror-reconcile` and `ci-delivery-check` logs list the new
   repos with no read errors.
2. **Statuses (R6).** On a repo whose authority is hand-pinned to `gitea`
   (`pin_authority: gitea`, org `mode: live`): the PR shows
   `gitea-actions/*` statuses with real durations on GitHub, its gated GitHub
   check jobs show `skipped`, and mutating and `macos-*` jobs still run on
   GitHub.
3. **Watcher dry-run (R7, R10, R13).** All orgs in dry-run against the live
   billing APIs: the heartbeat shows each org's `pct`; an org over threshold
   produces exactly one would-flip message across at least three runs.
4. **Live flip, one repo (R8, R9, R14).** Set `pin_authority: gitea` on one
   repo in a live org: the watcher writes Gitea then GitHub, read-backs pass,
   `gh variable get CI_AUTHORITY` returns `gitea`. Remove the pin (the org is
   below threshold and the pin did not stamp the month): GitHub then Gitea
   return to `github`, and `gh variable get` returns `github`. The org's other
   repos and kid-laptops are untouched throughout.
5. **Month lock (R8).** Set the Gitea org variable `CI_BUDGET_MONTH` to the
   previous month on an org at `gitea`: the next run returns the org's repos
   to `github`.
6. **Backstop (R12).** Replay a captured spending-limit annotation through the
   watcher's detector against a live repo (fixture injected via the watcher's
   test hook, dry-run off for a single org): the org flips, `sync-rerun-<sha12>`
   appears on Gitea, Gitea Actions runs at that sha, and its status lands on
   the GitHub commit.
7. **Heartbeat (R13).** Suspend the CronJob for 45 minutes:
   `ci-budget-heartbeat-stale` fires; resume it and it resolves.
8. **Report (R15).** `kubectl create job --from=cronjob/ci-budget-report`
   twice: the `CI tier review` issue appears once and is edited the second
   time.
9. **Repo PRs (R17).** After the eleven PRs merge, run the checker against
   each default branch: every job is `ok`.
10. **Runner (R18, R19).** The runner pod runs with a 2Gi limit on pc-1; the
    `ci-runner-probe` line shows `runners_online ≥ 1`; scale the runner to 0
    for 15 minutes and `layer-25-runner-offline` fires (then restore); query
    the pc-1 `/var` series in VMUI and confirm `layer-25-pc1-var-low`
    evaluates against real data.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-10-18--cicd--github-preferred-gitea-fallback | `derio-net/frank` | `2026-10-18--cicd--github-preferred-gitea-fallback` | — |
