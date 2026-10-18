# GitHub-preferred CI with automatic Gitea fallback — design

**Issue:** derio-net/frank#875
**Layer:** cicd (Layer 21 CI/CD)
**Date:** 2026-10-18
**Status:** Draft

## Context

GitHub Actions on the three GitHub orgs (derio-net, derio-homelab,
agentic-stoa) runs on the free plan: 2,000 included private-repo minutes per
org per calendar month, macOS billed ×10, public repos free. On 2026-10-18
derio-net exhausted its minutes and jobs stopped starting ("job was not started
because … spending limit"). derio-homelab stands at 1,801 / 2,000 for October.
agentic-stoa moved to Gitea Actions on Frank on 2026-07-22 by a manual,
two-sided flip of the `CI_AUTHORITY` variable (manual op
`cicd-stoa-ci-authority-cutover`). Nothing watches GitHub minutes.

The machinery for running a GitHub repo's CI on Frank already exists for
agentic-stoa and for `derio-homelab/kid-laptops`:

- GitHub → Gitea **push-sync** triggers on `github-listener`
  (`apps/tekton/triggers/eventlistener-github.yaml:197` agentic-stoa main,
  `:240` kid-laptops main), PR heads pushed as `sync-pr-<N>`
  (`eventlistener-github.yaml:37`).
- Per-org GitHub App installation tokens minted by ESO ClusterGenerators
  (`apps/tekton/manifests/clustergenerator-stoa-github-app.yaml`,
  `clustergenerator-derio-homelab-github-app.yaml`; the derio-net App
  `github-app-derio` is declared in
  `apps/secure-agent-pod/manifests/clustergenerator-github-app.yaml:24` and
  already consumed in `tekton-pipelines` by
  `apps/tekton/manifests/externalsecret-frank-gitops-push.yaml`).
- `mirror-reconcile` repairs missed syncs from `MAIN_REPOS` / `PR_REPOS`
  (`apps/tekton/manifests/mirror-reconcile.yaml:360-372`, `:389-400`), kept
  equal to the trigger filters by
  `scripts/tests/test_ci_mirror_resilience.py:183`.
- `ci-delivery-check` reads the same lists
  (`apps/tekton/manifests/ci-delivery-check.yaml:308-314`).
- Declared webhook delivery paths in `apps/tekton/webhooks.yaml`, enforced by
  `scripts/tests/test_webhook_delivery_paths.py`.
- The Gitea → GitHub **status bridge** (`gitea-status-bridge` trigger,
  `apps/tekton/triggers/eventlistener.yaml:66-77`) → `stoa-status-bridge`
  pipeline → `github-status` task.
- One act_runner on pc-1, capacity 2, single label `ubuntu-latest`
  (`apps/gitea-runner/manifests/files/config.yaml:13-20`), privileged DinD with
  a 40Gi emptyDir (`apps/gitea-runner/manifests/deployment.yaml:86-90`).

Gaps this design closes, each found in the code:

1. The status bridge filters `full_name.startsWith('agentic-stoa/')`
   (`eventlistener.yaml:75`) and `github-status` authenticates with the
   agentic-stoa token only (`apps/tekton/tasks/github-status.yaml:5,53`), so
   no derio-homelab or derio-net Gitea result reaches GitHub.
2. The generic `gitea-push` trigger excludes only `agentic-stoa/` and
   `derio-homelab/` (`eventlistener.yaml:28-30`); a `derio-net/*` Gitea repo
   would also fire the generic `gitea-ci` pipeline and fail (the double-run
   gotcha in `docs/runbooks/frank-gotchas/tekton.md`).
3. None of the nine `github-preferred` repos below gates a single job on
   `CI_AUTHORITY` except `derio-homelab/ansible-pihole` (5 gates); none
   triggers on `sync-pr-**`. Measured 2026-10-18 via the contents API. A
   flip of the GitHub variable therefore stops nothing on GitHub today.
4. `agentic-stoa/cnc-frd` and `cnc-fru` `release.yml` carry no gate (known
   gap recorded in `cicd-stoa-ci-authority-cutover`).
5. Nothing alerts on the runner being offline, on queued jobs, or on pc-1
   `/var` (19% free; the DinD emptyDir can grow to 40Gi). No rule in
   `apps/grafana-alerting/manifests/alert-rules-cm.yaml` reads
   `node_filesystem_*`; `layer-25-cicd-down` (`:2420`) watches Deployment
   availability in `gitea|tekton-pipelines|zot`, not the runner's Gitea-side
   registration.

### GitHub API facts this design relies on (verified 2026-10-18)

- `GET /organizations/{org}/settings/billing/usage` (enhanced billing
  platform) returns usage items for the org; query `year`, `month`, `day`.
  GitHub App permission: **organization `Administration`: read**
  (docs.github.com "Permissions required for GitHub Apps", billing rows).
- `POST/PATCH /repos/{owner}/{repo}/actions/variables[/{name}]`: GitHub App
  permission **repository `Variables`: write**.
- Organization Actions variables are **not** visible to private repos on the
  free plan (observed on agentic-stoa 2026-07-22), so the GitHub side of the
  authority is per-repo.
- ESO's `GithubAccessToken` generator (chart 2.1.0) takes optional
  `repositories` and `permissions`, so a token can be minted narrower than
  the App's grant — but the scope is a property of the **ClusterGenerator**,
  not of the consuming ExternalSecret.

## Requirements

R1. A tier config in git declares, per GitHub org: the included minutes (2,000), the flip threshold (85%), the Gitea org, and per private repo a tier — `github-only`, `gitea-only` or `github-preferred`. A repo absent from the config is `github-only`; public repos are always `github-only`.
R2. In a `github-preferred` repo only check jobs (tests, lint, build-verify) fall back to Gitea. Mutating jobs (release, publish, deploy, auto-tag, image push, acceptance-report issue upsert) and every `macos-*` job stay on GitHub regardless of authority.
R3. A check job may fall back while using a secret only if that secret is read-only (a deploy key, a read token). Such secrets are listed per repo in the tier config and provisioned as Gitea org secrets; a job needing a write-capable secret stays on GitHub.
R4. derio-net's five `github-preferred` repos (willikins, herdr-vertical-tabs, presentation-craft, vibe-kanban, runs-fr) are mirrored into a `derio-net` Gitea org: main and PR heads (`sync-pr-<N>`) are push-synced on every GitHub push, repaired by `mirror-reconcile`, checked by `ci-delivery-check`, and declared in `apps/tekton/webhooks.yaml`.
R5. derio-homelab's four `github-preferred` repos (proxmox-cluster, omada-controller, homelab, ansible-pihole) are mirrored the same way into the existing `derio-homelab` Gitea org, alongside kid-laptops.
R6. Gitea Actions commit statuses from all three orgs' mirrors reach the same sha on GitHub as `gitea-actions/<context>` statuses, each org written with its own org's token; a missing token for one org blinds only that org.
R7. A budget watcher on Frank reads each org's billing usage at least hourly and computes included-minute consumption for the current calendar month over private repos (Linux ×1, Windows ×2, macOS ×10).
R8. When an org reaches ≥85% of its included minutes, the watcher moves that org's `github-preferred` repos to `CI_AUTHORITY=gitea`; the authority stays `gitea` for the rest of that calendar month and returns to `github` once the month changes.
R9. Flips are ordered so that no window exists where neither forge runs: toward Gitea, the Gitea side is set first, then GitHub; toward GitHub, GitHub first, then Gitea. The GitHub side is a per-repo Actions variable; the Gitea side is the Gitea org variable.
R10. The watcher is idempotent (a run that finds both forges already at the desired authority writes nothing) and has a dry-run mode that computes and notifies without writing. It ships in dry-run; going live is a one-line git change.
R11. The watcher refuses to flip a repo whose workflows fail the gate-coverage check (R16), and says so in its notification.
R12. Backstop: within 10 minutes of a GitHub job in a `github-preferred` repo failing with the "spending limit" annotation, the watcher flips that org (R8, R9) and re-runs the affected PR heads on Gitea; affected default-branch runs are listed in the notification rather than re-run.
R13. Every flip, would-flip (dry-run), refusal and backstop trigger is sent to Telegram; every watcher run emits a heartbeat log line, and a Grafana rule pages when the heartbeat stops.
R14. The current authority of every `github-preferred` repo is readable from GitHub alone: the watcher sets the repo variable `CI_AUTHORITY` explicitly to `github` or `gitea` (never leaves it unset), so a consumer such as willikins' `doc-pr` can read it with `gh variable get CI_AUTHORITY`. A follow-up issue for the doc-pr side is filed in derio-net/willikins.
R15. On the 1st of each month a report is opened as an issue in derio-net/frank: per org and per repo, the previous month's billed minutes (each job rounded up to a whole minute by GitHub's billing, macOS ×10), the current tier, a proposed tier change with its reason, private repos with usage that the tier config does not list, and the gate-coverage gaps. Re-running it for the same month updates the same issue.
R16. A gate-coverage checker reports, for every workflow in a `github-preferred` or `gitea-only` repo, each job that lacks the authority gate (fallback-eligible jobs) or the GitHub pin (GitHub-only jobs), and each fallback-eligible job whose `runs-on` no Gitea runner label serves. It runs offline against a checkout and is reused by the watcher (R11) and the report (R15).
R17. The nine `github-preferred` repos and `agentic-stoa/cnc-frd` / `cnc-fru` `release.yml` are brought to full gate coverage, one PR per repo.
R18. The act_runner stays on pc-1 only, capacity 2; its `runner` container memory limit rises from 1Gi to 2Gi.
R19. Alerts fire when the Gitea runner is offline, when a Gitea Actions job has waited too long for a runner, and when pc-1 `/var` free space runs low.

## Design

### 1. Tier config (R1, R2, R3)

New ArgoCD Application `ci-budget` (raw manifests, kustomize), deploying into
the existing `tekton-pipelines` namespace — the GitHub App private keys
(`github-app-stoa-key`, `github-app-homelab-key`, `github-app-derio-key`) already
live there, and ESO resolves a generator's key in the consumer's namespace
(storage-secrets-ssa gotcha). The config is `apps/ci-budget/tiers.yaml`,
shipped to the CronJobs by kustomize `configMapGenerator` (hash-suffixed, so a
tier edit changes the CronJob spec; the app therefore needs `prune: true`,
with nothing stateful in it).

```yaml
version: 1
orgs:
  derio-net:
    included_minutes: 2000
    threshold_pct: 85
    gitea_org: derio-net
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
    repos:   # all gitea-only, unchanged authority
      cnc-fr: {tier: gitea-only}
      # … every currently mirrored agentic-stoa repo
```

Which jobs are check jobs is **not** in the tier config: it is expressed in the
workflows themselves by which gate a job carries (§6). The tier config only
says which repos the watcher may flip. `gitea_secrets` is the declared list of
read-only secrets mirrored as Gitea org secrets (R3); a test asserts every
`secrets.X` referenced by an authority-gated job in a repo's workflows (checked
by R16 against a checkout) is either listed there or is `GITHUB_TOKEN`
(which on Gitea is Gitea's own token).

A `github-preferred` repo's GitHub repo variable and its Gitea org's variable
are the authority state. agentic-stoa is `gitea-only` throughout and the
watcher never writes its variables; it is in the config for the billing view
(R7, R15) only.

### 2. Mirroring derio-net and the four derio-homelab repos (R4, R5)

Following the kid-laptops precedent
(`eventlistener-github.yaml:211-221`: "everything underneath differs: a
different webhook HMAC secret, a different App installation token, and
therefore a different pull-sync Pipeline"):

- **Gitea:** a `derio-net` org (manual op), one private repo per mirrored
  repo, history backfilled by `git push --mirror` (manual op, pattern of
  `cicd-stoa-site-gitea-mirror`). The four homelab repos are created in the
  existing `derio-homelab` Gitea org the same way.
- **Tokens:** a new `derio-net-github-mirror` ExternalSecret from a new
  ClusterGenerator `github-app-derio-mirror` scoped
  (`repositories` + `permissions: {contents: read, statuses: write,
  metadata: read}`) to the five repos. The existing `github-app-derio`
  generator in secure-agent-pod is left untouched. The homelab App's
  installation is widened from `kid-laptops` to the five homelab repos (manual
  op); `derio-homelab-github-mirror` keeps its name.
- **Triggers on `github-listener`:**
  - `derio-net-main-sync` and `derio-net-pr-sync` (repo list filter,
    `derio-net-github-webhook-secret`, which already exists —
    `apps/tekton/manifests/externalsecret-derio-net-github-webhook-secret.yaml`);
  - the kid-laptops main-sync trigger generalised to a repo list
    (`derio-homelab-main-sync`) plus a new `derio-homelab-pr-sync`.
  - PR triggers write `refs/heads/sync-pr-<N>` exactly like the stoa ones
    (`eventlistener-github.yaml:37`); PR close deletes the ref as they do.
- **Pipelines:** `derio-net-pull-sync` cloned from
  `apps/tekton/pipelines/derio-homelab-pull-sync.yaml`, reading
  `derio-net-github-mirror`. (Parameterising one shared pipeline was
  considered; the precedent above kept them separate so a token change for one
  org cannot break another's sync, and that reasoning holds.)
- **Gitea push routing:** the generic `gitea-push` filter adds
  `!body.repository.full_name.startsWith('derio-net/')`
  (`eventlistener.yaml:28-30`). The mirrored repos' CI is Gitea Actions only;
  no Tekton CI pipeline is added for them.
- **`webhooks.yaml`:** a repo-scoped GitHub webhook entry (`push`,
  `pull_request`) per mirrored repo — repo scope, not org scope, so public
  derio-net repos (super-fr ran ~41k minutes in October) never reach the
  listener. A Gitea org webhook entry (`status` events) for the `derio-net`
  and `derio-homelab` Gitea orgs feeding the status bridge.
- **`mirror-reconcile` / `ci-delivery-check`:** both lists grow by the nine
  repos; `plan.py` gains `GITHUB_TOKEN_DERIO_NET` (optional secretKeyRef, the
  pattern at `mirror-reconcile.yaml:409-412`) and picks the token by org. The
  existing guards (`test_ci_mirror_resilience.py:183,208,226`) are extended,
  not bypassed.

### 3. Status bridge for three orgs (R6)

- Trigger filter becomes `full_name.startsWith` any of the three orgs, still
  excluding `context` `tekton*` (`eventlistener.yaml:74-76`).
- `github-status` gains three optional token env vars (`stoa-github-mirror`,
  `derio-homelab-github-mirror`, `derio-net-github-mirror`, each
  `optional: true`) and selects by the `repo-full-name` owner; an owner with
  no token fails that one TaskRun loudly. All existing callers pass
  agentic-stoa repos, so their behaviour is unchanged. The `stoa-status-bridge`
  Pipeline name stays (renaming a Pipeline would orphan its PipelineRun
  history and its idle-rule tombstones); its description is updated.
- `gh_state` overlay unchanged.

### 4. Budget watcher (R7–R14)

A CronJob `ci-budget-watcher` (`*/10 * * * *`, `concurrencyPolicy: Forbid`),
digest-pinned stock `python:3-alpine`, script from the configMapGenerator (the
crowdsec-canary shape: no custom image). Modes from env `MODE=dry-run|live`;
git ships `dry-run`.

**Tokens.** Per org a dedicated ClusterGenerator
(`github-app-<org>-ci-budget`) on the org's existing App, permissions scoped
to `administration: read` (org), `variables: write`, `actions: read`,
`metadata: read`; repositories scoped to the org's `github-preferred` repos.
Mirror, status and push tokens never carry these. The Apps gain the
permissions by a re-approval per installation (manual op
`cicd-ci-budget-app-permissions`). The Gitea side writes org variables with a
dedicated Gitea token for a `ci-budget` bot with org-owner rights on
`derio-net` and `derio-homelab` (manual op; not the Gitea admin password).

**Each run:**

1. Load `tiers.yaml`. For each org with at least one `github-preferred` repo:
2. **Usage** (only when the minute is in the first 10 of the hour, or no
   usage sample has been read this hour — the hourly cadence): read the
   current month's billing usage; sum Actions minutes over private repos,
   Linux ×1, Windows ×2, macOS ×10 (SKU names matched case-insensitively;
   an unknown Actions SKU fails the run rather than being guessed). Record
   `pct = used / included`.
3. **Backstop** (every run): list workflow runs of the org's
   `github-preferred` repos created in the last 30 minutes with conclusion
   `failure`; for their jobs, read check-run annotations; a match on
   `spending limit` (case-insensitive) is a backstop hit.
4. **Desired authority:** `gitea` if `pct ≥ threshold` or a backstop hit or
   the org is already at `gitea` with a `CI_BUDGET_MONTH` Gitea org variable
   equal to the current `YYYY-MM`; otherwise `github`. This makes the
   authority monotonic within a billing month (R8) without any watcher-side
   state store: the stamp lives on the Gitea org beside the authority. At a
   month change the stamp no longer matches and the authority returns to
   `github`.
5. **Coverage:** run the R16 checker against each repo's default branch
   (contents API, no clone); a repo with gaps is excluded from the flip and
   named in a refusal notification (R11).
6. **Apply (live mode only), ordered (R9):**
   - toward `gitea`: Gitea org variable `CI_AUTHORITY=gitea` and
     `CI_BUDGET_MONTH=<YYYY-MM>` → read back → each repo's GitHub variable
     `CI_AUTHORITY=gitea` → read back;
   - toward `github`: each repo's GitHub variable `CI_AUTHORITY=github` →
     read back → Gitea org variable `CI_AUTHORITY=github` → read back.
   A failed write or read-back stops the sequence there (leaving at worst
   "both run", never "neither") and fails the Job.
   Each `github-preferred` repo's GitHub variable is always written
   explicitly, including `github` on first sight (R14).
7. **Backstop re-run:** after a backstop flip, for each affected run whose
   head is a PR, delete and recreate the Gitea branch `sync-pr-<N>` at the
   same sha (a branch-create fires Gitea's push event, so Gitea Actions runs
   the authority-gated jobs that the earlier sync skipped). Default-branch
   runs are listed in the notification, not re-run (deleting a default branch
   is not an option).
8. **Notify** (Telegram, `ci-budget-telegram` Secret, optional — absent means
   heartbeat-only, like crowdsec-canary): one message per flip, would-flip,
   refusal or backstop hit, never one per run. Edge-triggered: the message is
   sent when the authority or the refusal set changes, compared against what
   the variables say before the run.
9. **Heartbeat:** one log line per run,
   `ci-budget-watcher verdict=<ok|flipped|would-flip|refused|error> org=… pct=… authority=… mode=…`,
   to stdout → fluent-bit → VictoriaLogs (`_msg` field — the Frank field, not
   Hop's `log`).

Grafana rule `ci-budget-heartbeat-stale` (feature-health folder,
`telegram_direct`, `lt 1` over 40m on the heartbeat count, `noDataState`
handled as in `crowdsec-canary-heartbeat-stale`, uid ≤40 chars).

**willikins doc-pr (R14):** a follow-up issue is filed in derio-net/willikins
describing the hazard (GitHub shows only `skipped` checks while Gitea is
authoritative, so `gh pr checks` can go green before `gitea-actions/*`
statuses arrive) and the interface: `gh variable get CI_AUTHORITY` per repo.

### 5. Monthly report (R15)

CronJob `ci-budget-report` (`0 6 1 * *`), same image and config. For each org,
the previous month's usage by `repositoryName` (GitHub's billed quantities
already round each job up to a whole minute), macOS ×10. Proposal rules,
stated in the issue with their reason:

- a `github-preferred` repo that alone used ≥50% of its org's included
  minutes → propose `gitea-only`;
- an org that crossed its threshold, ranked consumers listed;
- a private repo with usage that `tiers.yaml` does not list → propose
  `github-preferred` (or `github-only` if any of its jobs is `macos-*`-only);
- a repo that is now public → propose removing it (public is always
  `github-only`);
- gate-coverage gaps (R16) per repo.

Output: an issue in derio-net/frank titled `CI tier review <YYYY-MM>`,
label `ci-tiers`, found by title on re-run and edited (R15). The token is a
ClusterGenerator on the derio-net App scoped to `derio-net/frank`
`issues: write` (permission added in the same manual op). The operator acts
by editing `tiers.yaml`.

### 6. Gate convention and coverage checker (R2, R11, R16, R17)

Two job-level gates, combined with any existing `if:` by `&&`:

- **authority gate** (fallback-eligible check jobs):
  `(vars.CI_AUTHORITY || 'github') == (github.server_url == 'https://github.com' && 'github' || 'gitea')`
  — the expression already in use in kid-laptops and ansible-pihole.
- **GitHub pin** (mutating jobs, `macos-*` jobs):
  `github.server_url == 'https://github.com'`. Without it a `macos-*` job
  mirrored to Gitea queues forever (no runner carries that label).

Plus, on every workflow with an authority-gated job that is triggered by
`pull_request`: `push: branches: ['sync-pr-**']` (those branches exist only on
Gitea, so GitHub never fires on them).

The checker, `scripts/ci_gate_coverage.py`, parses workflow YAML (a checkout
directory or a dict of fetched files) and reports per job one of: `ok`,
`ungated`, `fallback-on-unserved-label` (an authority-gated job whose
`runs-on` is not a label in `apps/gitea-runner/manifests/files/config.yaml`),
`missing-sync-pr-trigger`. For a `gitea-only` repo every job must carry the
authority gate or the GitHub pin. The same module is loaded by the watcher and
the report (it is copied into the configMapGenerator; a test asserts the
copy equals the source).

The runner gains the label `ubuntu-24.04` mapped to the same image as
`ubuntu-latest` (which is 24.04 today); other version labels are left
unserved and flagged.

**Cross-repo PRs (R17).** One PR per repo, each in its own fr workspace in
its own repo, applying the convention above:

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

Each repo PR passes the checker against its own branch; its PR body cites
this spec. In `release.yml` of cnc-frd/cnc-fru the jobs get the authority
gate (agentic-stoa is `gitea-only`; under authority `gitea` its release runs
on Gitea with the existing `STOA_CI_GH_TOKEN` fallback pattern).

### 7. Runner (R18, R19)

- `apps/gitea-runner/manifests/deployment.yaml:62`: runner limit 1Gi → 2Gi.
  Node selector and `capacity: 2` unchanged.
- **Runner offline / queue wait:** the watcher's run (§4) also reads the Gitea
  admin Actions API for registered runners (online/offline, last seen) and
  for jobs in `waiting` state with their age, and logs
  `ci-runner-probe runners_online=N oldest_waiting_s=S waiting=W`. The exact
  endpoints are confirmed against the live Gitea version (chart 12.5.0) during
  implementation by a read-only call; if the version exposes no runner-list
  endpoint, runner liveness falls back to `kube_deployment_status_replicas_unavailable{namespace="gitea-runner"}`
  plus the queue-age signal (a queued job with no taker is the user-visible
  symptom of an offline runner either way).
  Grafana rules (LogsQL, `queryType: stats`): `layer-25-runner-offline`
  (`runners_online < 1` for 10m), `layer-25-runner-queue-wait`
  (`oldest_waiting_s > 900` for 10m).
- **pc-1 `/var`:** `layer-25-pc1-var-low` on
  `node_filesystem_avail_bytes{mountpoint="/var"} / node_filesystem_size_bytes`
  for pc-1 `< 0.15` for 15m (warning). The series' presence and labels are
  checked live (read-only) before the rule is written; a `== 0`-series rule
  would be silent under `noDataState: OK`.

### 8. Manual operations

Recorded as `# manual-operation` blocks in the plan, synced to the runbook:

- `cicd-ci-budget-app-permissions` — add `Administration: read` (org) and
  `Variables: write` (repo) to derio-fr-automation, homelab-fr-automation,
  stoa-fr-automation; add `statuses: write` and `issues: write` to
  derio-fr-automation if absent; re-approve each installation; widen
  homelab-fr-automation to the five homelab repos and confirm
  derio-fr-automation covers the five derio-net repos.
- `cicd-derio-net-gitea-org` — create the `derio-net` Gitea org, the
  `ci-budget` Gitea bot + token (SOPS secret), the org `status` webhook, org
  variable `CI_AUTHORITY=github`; same webhook + variable on `derio-homelab`.
- `cicd-github-preferred-gitea-mirrors` — create and backfill the nine Gitea
  repos; add the nine GitHub repo webhooks.
- `cicd-gitea-readonly-secrets` — set each `gitea_secrets` entry as a Gitea
  org secret.
- `cicd-ci-budget-go-live` — after every repo PR has merged and the
  post-merge rows pass, change `MODE` to `live` in git.

### 9. Risks

- **pc-1 is a SPOF** (Gitea, zot, sync pods, the runner). Accepted by the
  operator; the standby load is ~600–1,000 job-minutes a month on top of
  ~1,300. The queue-wait alert is the early warning.
- **DinD trust boundary.** Check jobs only, read-only secrets only (R2, R3)
  keep derio-net's deploy credentials off the shared privileged daemon.
- **Billing lag.** The usage endpoint can trail real consumption; the
  backstop (R12) covers the tail.
- **Mirror lag.** Webhook syncs are fast; a repaired sync can take 15–25
  minutes. During a flip a PR may briefly show only `skipped` GitHub checks
  (R14's doc-pr follow-up).

## Verification

strategy: live
gate: devops
- tier-config-declares-repo-tiers: none — offline tests in CI (`scripts/tests/`) parse `apps/ci-budget/tiers.yaml` and assert its schema and the read-only-secret rule
- gate-coverage-checker-flags-gaps: none — offline tests in CI run the checker on fixture workflows
- runner-memory-and-placement: none — a manifest guard in CI asserts the limit, node selector and capacity
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

Post-merge, operator-driven (devops gate):

1. After the manual ops: push to a PR in one derio-net and one derio-homelab
   repo; the Gitea mirror shows `sync-pr-<N>` at the PR head sha.
2. With the repo's authority set to `gitea` by hand on both sides: the PR
   shows `gitea-actions/*` statuses with real durations on GitHub, and its
   GitHub check jobs show `skipped`; mutating and `macos-*` jobs still run on
   GitHub.
3. Watcher in dry-run against the live billing APIs: the heartbeat line shows
   each org's `pct`, and a would-flip notification arrives for any org over
   threshold.
4. Watcher in live mode on one repo: one flip to `gitea` and back, with the
   variables read back in the order R9 requires.
5. Kill the CronJob (suspend it) for 45 minutes: `ci-budget-heartbeat-stale`
   fires.
6. Run `ci-budget-report` by hand (`kubectl create job --from=cronjob/…`): the
   `CI tier review` issue appears; a second run edits it instead of opening
   another.
