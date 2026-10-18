<!-- fr:journal-schema=2 -->
# Journal: 2026-10-18--cicd--github-preferred-gitea-fallback

<!-- fr:journal kind=decision scope=plan id=plan-shape created=2026-10-18T14:47:33+00:00 -->
### plan-shape · decision · Five agentic phases (one per ask) plus a trailing manual phase

Skeleton = tier config + gate-coverage checker (the cross-repo PRs validate against it). Cross-repo PRs (R17) are dispatched by the orchestrator after phase 1 lands and tracked in the manual phase; PRE-MERGE gates are manual ops that hold the PR in draft.

<!-- fr:journal kind=discovery scope=plan id=gate-coverage-baseline created=2026-10-18T14:51:17+00:00 phase=1 -->
### gate-coverage-baseline · discovery · Gate-coverage baseline across the eleven cross-repo targets (work list) (phase 1)

Checker run read-only on 2026-10-18 against the local clones (all workflows; the cnc repos are gitea-only here, so their numbers are wider than the release.yml-only scope of R17).
willikins 6 ungated; herdr-vertical-tabs 2 ungated; presentation-craft 3 ungated; vibe-kanban 28 ungated (VK_PRIVATE_DEPLOY_KEY passed as gitea_secret); runs-fr 7 ungated;
proxmox-cluster 3 ungated; omada-controller 2 ungated; homelab 2 ungated; ansible-pihole 1 missing-rerun-triggers (gates already present);
cnc-frd 1 ungated + 1 fallback-github-token-to-github + 1 fallback-secret-not-mirrored + 2 missing-rerun-triggers; cnc-fru 1 ungated + 1 fallback-github-token-to-github + 2 fallback-secret-not-mirrored + 2 missing-rerun-triggers.
Only release.yml in cnc-frd/cnc-fru gets the GitHub pin (spec section 6); the other cnc findings are context, not work.

<!-- fr:journal kind=discovery scope=plan id=worktree-has-no-venv created=2026-10-18T14:51:17+00:00 phase=1 -->
### worktree-has-no-venv · discovery · Worktree has no .venv; use the base clone's venv python/pytest by absolute path (phase 1)

The checker needs PyYAML, so the baseline was run with the base clone's .venv python.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t2 created=2026-10-18T14:51:17+00:00 phase=1 -->
### no-refactor-p1-t2 · discovery · no-refactor-because P1.T2 (phase 1)

tiers.yaml and its test are data plus plain assertions; nothing to clean.

<!-- fr:journal kind=discovery scope=plan id=gate-coverage-baseline-2 created=2026-10-18T14:58:15+00:00 phase=1 -->
### gate-coverage-baseline-2 · discovery · Gate-coverage baseline re-run with the hardened checker (supersedes gate-coverage-baseline) (phase 1)

Re-run 2026-10-18 after review fixes, same clones, read-only. Counts: willikins 6 ungated; herdr-vertical-tabs 2 ungated; presentation-craft 3 ungated; vibe-kanban 28 ungated; runs-fr 7 ungated; proxmox-cluster 3 ungated; omada-controller 2 ungated; homelab 2 ungated; ansible-pihole 1 missing-rerun-triggers; cnc-frd 1 ungated + 1 token-to-github + 1 secret-not-mirrored + 2 missing-rerun-triggers; cnc-fru 1 ungated + 2 token-to-github + 2 secret-not-mirrored + 2 missing-rerun-triggers (cnc-fru gains one token hit from the broader token detection). No malformed-gate findings anywhere. Also: gitea/runner-images:ubuntu-24.04 exists on Docker Hub, so the ubuntu-24.04 label now maps to it.

<!-- fr:journal kind=finding scope=plan id=p1-r1 created=2026-10-18T14:59:21+00:00 phase=1 state=open review_scope=in -->
### p1-r1 · finding [open] (reviewer: in scope) · pin detected by substring; near-miss gates passed as pinned (phase 1)

Raised by the phase-1 code reviewer; details in its return.

<!-- fr:journal kind=finding scope=plan id=p1-r2 created=2026-10-18T14:59:21+00:00 phase=1 state=open review_scope=in -->
### p1-r2 · finding [open] (reviewer: in scope) · gate accepted inside || or under !() (phase 1)

Raised by the phase-1 code reviewer; details in its return.

<!-- fr:journal kind=finding scope=plan id=p1-r3 created=2026-10-18T14:59:21+00:00 phase=1 state=open review_scope=in -->
### p1-r3 · finding [open] (reviewer: in scope) · unfiltered push flagged missing-rerun-triggers (phase 1)

Raised by the phase-1 code reviewer; details in its return.

<!-- fr:journal kind=finding scope=plan id=p1-r4 created=2026-10-18T14:59:21+00:00 phase=1 state=open review_scope=in -->
### p1-r4 · finding [open] (reviewer: in scope) · tags-only push / branches-ignore treated as covering sync branches (phase 1)

Raised by the phase-1 code reviewer; details in its return.

<!-- fr:journal kind=finding scope=plan id=p1-r5 created=2026-10-18T14:59:21+00:00 phase=1 state=open review_scope=in -->
### p1-r5 · finding [open] (reviewer: in scope) · workflow-level env ignored by secret/token checks (phase 1)

Raised by the phase-1 code reviewer; details in its return.

<!-- fr:journal kind=finding scope=plan id=p1-r6 created=2026-10-18T14:59:21+00:00 phase=1 state=open review_scope=in -->
### p1-r6 · finding [open] (reviewer: in scope) · token detection missed backticks, with: inputs, bracket secrets (phase 1)

Raised by the phase-1 code reviewer; details in its return.

<!-- fr:journal kind=finding scope=plan id=p1-r7 created=2026-10-18T14:59:21+00:00 phase=1 state=open review_scope=in -->
### p1-r7 · finding [open] (reviewer: in scope) · secrets: inherit on reusable workflows not inspected (phase 1)

Raised by the phase-1 code reviewer; details in its return.

<!-- fr:journal kind=finding scope=plan id=p1-r8 created=2026-10-18T14:59:21+00:00 phase=1 state=open review_scope=in -->
### p1-r8 · finding [open] (reviewer: in scope) · .gitea/workflows not read (phase 1)

Raised by the phase-1 code reviewer; details in its return.

<!-- fr:journal kind=finding scope=plan id=p1-r9 created=2026-10-18T14:59:21+00:00 phase=1 state=open review_scope=in -->
### p1-r9 · finding [open] (reviewer: in scope) · tier tests lacked read-only-secret rule and unknown-key rejection (phase 1)

Raised by the phase-1 code reviewer; details in its return.

<!-- fr:journal kind=finding scope=plan id=p1-r10 created=2026-10-18T14:59:21+00:00 phase=1 state=open review_scope=in -->
### p1-r10 · finding [open] (reviewer: in scope) · MAIN_REPOS cross-check one-directional (phase 1)

Raised by the phase-1 code reviewer; details in its return.

<!-- fr:journal kind=finding scope=plan id=p1-r11 created=2026-10-18T14:59:21+00:00 phase=1 state=open review_scope=in -->
### p1-r11 · finding [open] (reviewer: in scope) · ubuntu-24.04 label mapped to floating ubuntu-latest image (phase 1)

Raised by the phase-1 code reviewer; details in its return.

<!-- fr:journal kind=finding scope=plan id=p1-r12 created=2026-10-18T14:59:21+00:00 phase=1 state=open review_scope=in -->
### p1-r12 · finding [open] (reviewer: in scope) · checker tests used `in` and lacked edge fixtures (phase 1)

Raised by the phase-1 code reviewer; details in its return.

<!-- fr:journal kind=finding scope=plan id=p1-r13 created=2026-10-18T14:59:21+00:00 phase=1 state=open review_scope=in -->
### p1-r13 · finding [open] (reviewer: in scope) · baseline produced by the buggy checker (phase 1)

Raised by the phase-1 code reviewer; details in its return.

<!-- fr:journal kind=finding scope=plan id=p1-sec1 created=2026-10-18T14:59:21+00:00 phase=1 state=open review_scope=in -->
### p1-sec1 · finding [open] (reviewer: in scope) · gitea_secrets as Gitea org secrets would expose a repo's deploy key to every mirror in the org (phase 1)

Automated security review on tiers.yaml (VK_PRIVATE_DEPLOY_KEY). Spec R3/§1/§8 and the manual op now use repository-level Gitea secrets; tiers.yaml header updated.

<!-- fr:journal kind=review scope=plan id=review-p1 created=2026-10-18T14:59:21+00:00 phase=1 -->
### review-p1 · review · Phase 1 code review: 13 findings, all in scope, all fixed (phase 1)

Independent code-reviewer subagent reviewed commit 3992c166 against spec §1/§6 and plan 01.yaml, ran the tests and an edge-case probe. Raised p1-r1..p1-r13 (gate parsing, rerun-trigger semantics, env/inherit/token coverage, .gitea workflows, tier-config guards, runner label pin, test gaps, stale baseline). All fixed TDD in 95a3e02f with 36 fixtures and exact-set assertions; baseline re-run as gate-coverage-baseline-2. Separate automated security finding p1-sec1 fixed in the same commit. Orchestrator re-ran the tests: 58 passed.

<!-- fr:journal kind=finding scope=plan id=p1-r1-resolved created=2026-10-18T14:59:21+00:00 phase=1 state=fixed resolves=p1-r1 -->
### p1-r1-resolved · finding [fixed] · resolves p1-r1: pin detected by substring; near-miss gates passed as pinned (phase 1)

Fixed in 95a3e02f with a failing fixture/test first.

<!-- fr:journal kind=finding scope=plan id=p1-r2-resolved created=2026-10-18T14:59:21+00:00 phase=1 state=fixed resolves=p1-r2 -->
### p1-r2-resolved · finding [fixed] · resolves p1-r2: gate accepted inside || or under !() (phase 1)

Fixed in 95a3e02f with a failing fixture/test first.

<!-- fr:journal kind=finding scope=plan id=p1-r3-resolved created=2026-10-18T14:59:21+00:00 phase=1 state=fixed resolves=p1-r3 -->
### p1-r3-resolved · finding [fixed] · resolves p1-r3: unfiltered push flagged missing-rerun-triggers (phase 1)

Fixed in 95a3e02f with a failing fixture/test first.

<!-- fr:journal kind=finding scope=plan id=p1-r4-resolved created=2026-10-18T14:59:21+00:00 phase=1 state=fixed resolves=p1-r4 -->
### p1-r4-resolved · finding [fixed] · resolves p1-r4: tags-only push / branches-ignore treated as covering sync branches (phase 1)

Fixed in 95a3e02f with a failing fixture/test first.

<!-- fr:journal kind=finding scope=plan id=p1-r5-resolved created=2026-10-18T14:59:21+00:00 phase=1 state=fixed resolves=p1-r5 -->
### p1-r5-resolved · finding [fixed] · resolves p1-r5: workflow-level env ignored by secret/token checks (phase 1)

Fixed in 95a3e02f with a failing fixture/test first.

<!-- fr:journal kind=finding scope=plan id=p1-r6-resolved created=2026-10-18T14:59:21+00:00 phase=1 state=fixed resolves=p1-r6 -->
### p1-r6-resolved · finding [fixed] · resolves p1-r6: token detection missed backticks, with: inputs, bracket secrets (phase 1)

Fixed in 95a3e02f with a failing fixture/test first.

<!-- fr:journal kind=finding scope=plan id=p1-r7-resolved created=2026-10-18T14:59:21+00:00 phase=1 state=fixed resolves=p1-r7 -->
### p1-r7-resolved · finding [fixed] · resolves p1-r7: secrets: inherit on reusable workflows not inspected (phase 1)

Fixed in 95a3e02f with a failing fixture/test first.

<!-- fr:journal kind=finding scope=plan id=p1-r8-resolved created=2026-10-18T14:59:21+00:00 phase=1 state=fixed resolves=p1-r8 -->
### p1-r8-resolved · finding [fixed] · resolves p1-r8: .gitea/workflows not read (phase 1)

Fixed in 95a3e02f with a failing fixture/test first.

<!-- fr:journal kind=finding scope=plan id=p1-r9-resolved created=2026-10-18T14:59:21+00:00 phase=1 state=fixed resolves=p1-r9 -->
### p1-r9-resolved · finding [fixed] · resolves p1-r9: tier tests lacked read-only-secret rule and unknown-key rejection (phase 1)

Fixed in 95a3e02f with a failing fixture/test first.

<!-- fr:journal kind=finding scope=plan id=p1-r10-resolved created=2026-10-18T14:59:21+00:00 phase=1 state=fixed resolves=p1-r10 -->
### p1-r10-resolved · finding [fixed] · resolves p1-r10: MAIN_REPOS cross-check one-directional (phase 1)

Fixed in 95a3e02f with a failing fixture/test first.

<!-- fr:journal kind=finding scope=plan id=p1-r11-resolved created=2026-10-18T14:59:21+00:00 phase=1 state=fixed resolves=p1-r11 -->
### p1-r11-resolved · finding [fixed] · resolves p1-r11: ubuntu-24.04 label mapped to floating ubuntu-latest image (phase 1)

Fixed in 95a3e02f with a failing fixture/test first.

<!-- fr:journal kind=finding scope=plan id=p1-r12-resolved created=2026-10-18T14:59:21+00:00 phase=1 state=fixed resolves=p1-r12 -->
### p1-r12-resolved · finding [fixed] · resolves p1-r12: checker tests used `in` and lacked edge fixtures (phase 1)

Fixed in 95a3e02f with a failing fixture/test first.

<!-- fr:journal kind=finding scope=plan id=p1-r13-resolved created=2026-10-18T14:59:21+00:00 phase=1 state=fixed resolves=p1-r13 -->
### p1-r13-resolved · finding [fixed] · resolves p1-r13: baseline produced by the buggy checker (phase 1)

Fixed in 95a3e02f with a failing fixture/test first.

<!-- fr:journal kind=finding scope=plan id=p1-sec1-resolved created=2026-10-18T14:59:21+00:00 phase=1 state=fixed resolves=p1-sec1 -->
### p1-sec1-resolved · finding [fixed] · resolves p1-sec1: gitea_secrets as Gitea org secrets would expose a repo's deploy key to every mirror in the org (phase 1)

Repo-level Gitea secrets in spec, manual op and tiers.yaml header (95a3e02f).

<!-- fr:journal kind=discovery scope=plan id=p2-kid-laptops-now-status-checked created=2026-10-18T15:13:40+00:00 phase=2 -->
### p2-kid-laptops-now-status-checked · discovery · ci-delivery-check now compares forwarded statuses for kid-laptops too (phase 2)

Spec R6 widens the comparison to every org in the token map, which includes derio-homelab/kid-laptops (previously skipped). Its Tekton statuses are excluded by the tekton* filter, but any non-tekton Gitea status there is now verified and can raise ci_delivery_overdue kind=status. Watch on go-live.

<!-- fr:journal kind=discovery scope=plan id=p2-staging-gate-guards-coupled created=2026-10-18T15:13:40+00:00 phase=2 -->
### p2-staging-gate-guards-coupled · discovery · test_staging_gate_manifests pins the ClusterGenerator set and takes the first runs-fr webhook entry (phase 2)

Adding github-app-derio-mirror and a repo-scoped derio-net/runs-fr mirror entry broke two staging-gate guards; updated the generator baseline and made the runs-fr lookup filter scope=direct-post. github-app-derio stays unscoped.

<!-- fr:journal kind=discovery scope=plan id=p2-pr-repos-sorted created=2026-10-18T15:13:40+00:00 phase=2 -->
### p2-pr-repos-sorted · discovery · PR_REPOS must stay alphabetical, MAIN_REPOS in listener order (phase 2)

test_ci_mirror_resilience derives PR_REPOS sorted and MAIN_REPOS in trigger order, so the env lists in mirror-reconcile and ci-delivery-check follow those orders.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p2-t2 created=2026-10-18T15:13:40+00:00 phase=2 -->
### no-refactor-p2-t2 · discovery · no-refactor-because P2.T2 (phase 2)

New manifests cloned from the homelab precedent and the four TriggerTemplates generated from one shape; nothing duplicated beyond the deliberate per-org isolation.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p2-t3 created=2026-10-18T15:13:40+00:00 phase=2 -->
### no-refactor-p2-t3 · discovery · no-refactor-because P2.T3 (phase 2)

Edits were list widenings plus one TOKEN_FILES constant; the delivery-check org gate already shares that constant with main(), nothing left to clean.

<!-- fr:journal kind=finding scope=plan id=p2-r1 created=2026-10-18T15:31:13+00:00 phase=2 state=open review_scope=in -->
### p2-r1 · finding [open] (reviewer: in scope) · PR-sync triggers mirrored fork PR heads into the privileged shared DinD (phase 2)

Raised in phase-2 review.

<!-- fr:journal kind=finding scope=plan id=p2-r2 created=2026-10-18T15:31:13+00:00 phase=2 state=open review_scope=in -->
### p2-r2 · finding [open] (reviewer: in scope) · mirror-reconcile / ci-delivery-check re-created or expected sync-pr refs for fork PRs (phase 2)

Raised in phase-2 review.

<!-- fr:journal kind=finding scope=plan id=p2-r3 created=2026-10-18T15:31:13+00:00 phase=2 state=open review_scope=in -->
### p2-r3 · finding [open] (reviewer: in scope) · Status bridge admitted whole orgs by prefix (phase 2)

Raised in phase-2 review.

<!-- fr:journal kind=finding scope=plan id=p2-r4 created=2026-10-18T15:31:13+00:00 phase=2 state=open review_scope=out -->
### p2-r4 · finding [open] (reviewer: out of scope) · gitea-listener status webhooks carry no HMAC (phase 2)

Raised in phase-2 review.

<!-- fr:journal kind=finding scope=plan id=p2-r5 created=2026-10-18T15:31:13+00:00 phase=2 state=open review_scope=in -->
### p2-r5 · finding [open] (reviewer: in scope) · Merging would page: lists name nine repos whose Gitea side is created post-merge (phase 2)

Raised in phase-2 review.

<!-- fr:journal kind=finding scope=plan id=p2-r6 created=2026-10-18T15:31:13+00:00 phase=2 state=open review_scope=in -->
### p2-r6 · finding [open] (reviewer: in scope) · Stoa token mandatory everywhere and token_for fell back to the stoa token for other orgs (phase 2)

Raised in phase-2 review.

<!-- fr:journal kind=finding scope=plan id=p2-r7 created=2026-10-18T15:31:13+00:00 phase=2 state=open review_scope=in -->
### p2-r7 · finding [open] (reviewer: in scope) · Renamed TriggerTemplate orphaned live under prune:false (phase 2)

Raised in phase-2 review.

<!-- fr:journal kind=finding scope=plan id=p2-r8 created=2026-10-18T15:31:13+00:00 phase=2 state=open review_scope=in -->
### p2-r8 · finding [open] (reviewer: in scope) · Homelab ClusterGenerator unscoped with stale header (phase 2)

Raised in phase-2 review.

<!-- fr:journal kind=finding scope=plan id=p2-r9 created=2026-10-18T15:31:13+00:00 phase=2 state=open review_scope=in -->
### p2-r9 · finding [open] (reviewer: in scope) · Unverified claim that kid-laptops statuses are all tekton* (phase 2)

Raised in phase-2 review.

<!-- fr:journal kind=finding scope=plan id=p2-sec1 created=2026-10-18T15:31:13+00:00 phase=2 state=open review_scope=in -->
### p2-sec1 · finding [open] (reviewer: in scope) · Automated security review: status bridge unauthenticated + org-prefix filter; fork PR mirroring in triggers and reconciler (phase 2)

Raised in phase-2 review.

<!-- fr:journal kind=review scope=plan id=review-p2 created=2026-10-18T15:31:13+00:00 phase=2 -->
### review-p2 · review · Phase 2 code review: 9 findings (8 in, 1 out), all handled (phase 2)

Independent code-reviewer subagent reviewed 30d153f5, f2137b70 and 6f07f05b against spec §2/§3 and plan 02.yaml, ran 236 tests, and gave explicit verdicts on three security items (all confirmed). In-scope findings were fixed TDD in 1b481097 and f50965ea, or in spec, prose and 06.yaml. p2-r4 (HMAC) is out of scope as pre-existing. The orchestrator re-ran the suites: 176 passed, 2 skipped.

<!-- fr:journal kind=finding scope=plan id=p2-r1-resolved created=2026-10-18T15:31:13+00:00 phase=2 state=fixed resolves=p2-r1 -->
### p2-r1-resolved · finding [fixed] · resolves p2-r1: PR-sync triggers mirrored fork PR heads into the privileged shared DinD (phase 2)

Same-repo CEL filter on derio-net-pr-sync and derio-homelab-pr-sync (1b481097).

<!-- fr:journal kind=finding scope=plan id=p2-r2-resolved created=2026-10-18T15:31:13+00:00 phase=2 state=fixed resolves=p2-r2 -->
### p2-r2-resolved · finding [fixed] · resolves p2-r2: mirror-reconcile / ci-delivery-check re-created or expected sync-pr refs for fork PRs (phase 2)

plan.py github_open_prs and ci-delivery-check pulls skip forks, with fork fixtures (1b481097).

<!-- fr:journal kind=finding scope=plan id=p2-r3-resolved created=2026-10-18T15:31:13+00:00 phase=2 state=fixed resolves=p2-r3 -->
### p2-r3-resolved · finding [fixed] · resolves p2-r3: Status bridge admitted whole orgs by prefix (phase 2)

Explicit 21-repo allowlist guarded equal to mirror-reconcile MAIN_REPOS (1b481097, f50965ea).

<!-- fr:journal kind=finding scope=plan id=p2-r4-resolved created=2026-10-18T15:31:13+00:00 phase=2 state=open resolves=p2-r4 out_of_scope=true -->
### p2-r4-resolved · finding [out-of-scope] · resolves p2-r4: gitea-listener status webhooks carry no HMAC (phase 2)

Pre-existing for agentic-stoa since 2026-07-19; closing it needs a secret on every Gitea org hook (manual op) and a github-interceptor on the trigger. This change narrows the surface to an explicit repo list (p2-r3) but does not cause the gap. Filed at deliver as a follow-up.

<!-- fr:journal kind=finding scope=plan id=p2-r5-resolved created=2026-10-18T15:31:13+00:00 phase=2 state=fixed resolves=p2-r5 -->
### p2-r5-resolved · finding [fixed] · resolves p2-r5: Merging would page: lists name nine repos whose Gitea side is created post-merge (phase 2)

Gitea org, repos and status hooks moved to PRE-MERGE in spec §8, plan prose and 06.yaml; GitHub repo webhooks stay post-merge.

<!-- fr:journal kind=finding scope=plan id=p2-r6-resolved created=2026-10-18T15:31:13+00:00 phase=2 state=fixed resolves=p2-r6 -->
### p2-r6-resolved · finding [fixed] · resolves p2-r6: Stoa token mandatory everywhere and token_for fell back to the stoa token for other orgs (phase 2)

Stoa token optional in github-status, mirror-reconcile, ci-delivery-check; no cross-org fallback, per-repo error instead (1b481097).

<!-- fr:journal kind=finding scope=plan id=p2-r7-resolved created=2026-10-18T15:31:13+00:00 phase=2 state=fixed resolves=p2-r7 -->
### p2-r7-resolved · finding [fixed] · resolves p2-r7: Renamed TriggerTemplate orphaned live under prune:false (phase 2)

New manual op cicd-kid-laptops-template-orphan-delete, in phase 6.

<!-- fr:journal kind=finding scope=plan id=p2-r8-resolved created=2026-10-18T15:31:13+00:00 phase=2 state=fixed resolves=p2-r8 -->
### p2-r8-resolved · finding [fixed] · resolves p2-r8: Homelab ClusterGenerator unscoped with stale header (phase 2)

Scoped to 5 repos and 4 permissions, header fixed, test added (1b481097).

<!-- fr:journal kind=finding scope=plan id=p2-r9-resolved created=2026-10-18T15:31:13+00:00 phase=2 state=fixed resolves=p2-r9 -->
### p2-r9-resolved · finding [fixed] · resolves p2-r9: Unverified claim that kid-laptops statuses are all tekton* (phase 2)

webhooks.yaml note now says kid-laptops Gitea Actions statuses are forwarded by design (1b481097).

<!-- fr:journal kind=finding scope=plan id=p2-sec1-resolved created=2026-10-18T15:31:13+00:00 phase=2 state=fixed resolves=p2-sec1 -->
### p2-sec1-resolved · finding [fixed] · resolves p2-sec1: Automated security review: status bridge unauthenticated + org-prefix filter; fork PR mirroring in triggers and reconciler (phase 2)

Same fixes as p2-r1/r2/r3; HMAC part tracked as p2-r4.

<!-- fr:journal kind=owed scope=plan id=willikins-doc-pr-authority created=2026-10-18T15:44:36+00:00 phase=3 -->
### willikins-doc-pr-authority · owed · File follow-up issue in derio-net/willikins: doc-pr must read CI_AUTHORITY (phase 3)

what: File an issue in derio-net/willikins: `doc-pr ship` can merge on GitHub-only `skipped` checks while Gitea is authoritative (GitHub shows only skipped jobs, so `gh pr checks` can go green before the `gitea-actions/*` statuses arrive). Interface: `gh variable get CI_AUTHORITY` per repo (the watcher sets it explicitly to `github` or `gitea` on every github-preferred repo); when it reads `gitea`, wait for the `gitea-actions/*` statuses before merging.
why: spec 2026-10-18--cicd--github-preferred-gitea-fallback R14; the fix belongs in willikins, not in frank.
how: fr journal file --scope plan --slug 2026-10-18--cicd--github-preferred-gitea-fallback --id willikins-doc-pr-authority --repo derio-net/willikins
owed_key: plan:2026-10-18--cicd--github-preferred-gitea-fallback#p3

<!-- fr:journal kind=decision scope=plan id=p3-stamp-flag-only-when-unstamped created=2026-10-18T15:47:26+00:00 phase=3 -->
### p3-stamp-flag-only-when-unstamped · decision · desired_authority returns stamp=True only when CI_BUDGET_MONTH differs from the current month (phase 3)

Re-stamping an already-stamped month would be a write every 10 minutes; the flag is therefore False when the stamp already equals now_month, which keeps apply idempotent (R10).

<!-- fr:journal kind=decision scope=plan id=p3-billing-reread-on-month-rollover created=2026-10-18T15:47:26+00:00 phase=3 -->
### p3-billing-reread-on-month-rollover · decision · A cached pct from a previous UTC month forces a billing re-read (phase 3)

The 55-minute cadence alone would let the first run of a new month reuse last month's pct and re-stamp gitea. need_billing also compares the last-read month.

<!-- fr:journal kind=decision scope=plan id=p3-public-repos-excluded-from-minutes created=2026-10-18T15:47:26+00:00 phase=3 -->
### p3-public-repos-excluded-from-minutes · decision · Public repos are excluded from included-minute consumption via a repo listing (phase 3)

Usage items carry no visibility. The watcher lists the org's public repos with the billing token (metadata read) and passes them as exclude_repos to included_minutes_used and pinned_share, so R7's private-only sum holds.

<!-- fr:journal kind=decision scope=plan id=p3-rerun-branch-age-from-state created=2026-10-18T15:47:26+00:00 phase=3 -->
### p3-rerun-branch-age-from-state · decision · sync-rerun-* branch age comes from the state timestamp, falling back to the head commit time (phase 3)

Gitea's branch listing only exposes the head commit timestamp, which for a rerun of an old sha is old on creation and would be deleted at once. The watcher records the creation time in ci-budget-state and uses the commit time only for branches it has no record of.

<!-- fr:journal kind=discovery scope=plan id=p3-rbac-create-cannot-be-name-scoped created=2026-10-18T15:47:26+00:00 phase=3 -->
### p3-rbac-create-cannot-be-name-scoped · discovery · RBAC resourceNames cannot restrict create, so the Role has one unnamed create rule (phase 3)

Spec says get/create/update/patch on ci-budget-state. A rule with resourceNames never matches create, so get/patch/update are name-scoped and create on configmaps is a separate unnamed rule. The manifest test pins exactly this shape.

<!-- fr:journal kind=discovery scope=plan id=p3-stoa-org-skips-gitea created=2026-10-18T15:47:26+00:00 phase=3 -->
### p3-stoa-org-skips-gitea · discovery · An org with no github-preferred repo makes no Gitea calls (phase 3)

agentic-stoa has no github-preferred repo and the Gitea bot holds no rights there, so run_org skips the CI_BUDGET_MONTH read/write for it; it still reads billing and heartbeats (pct only).

<!-- fr:journal kind=discovery scope=plan id=p3-yaml-colon-arg-trap created=2026-10-18T15:47:26+00:00 phase=3 -->
### p3-yaml-colon-arg-trap · discovery · An unquoted `--only-binary=:all:` list item parses as a mapping (phase 3)

A trailing colon turned the CronJob arg into a dict; caught by the manifest test. Quote it. Hashes in files/requirements.txt were verified with a real pip install --require-hashes for musllinux_1_2_x86_64/cp313.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p3-t1 created=2026-10-18T15:47:26+00:00 phase=3 -->
### no-refactor-p3-t1 · discovery · no-refactor-because P3.T1 (phase 3)

pure functions written minimal; nothing to clean

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p3-t2 created=2026-10-18T15:47:26+00:00 phase=3 -->
### no-refactor-p3-t2 · discovery · no-refactor-because P3.T2 (phase 3)

apply_authority and run_org were written once against the tests; no duplication to extract

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p3-t3 created=2026-10-18T15:47:26+00:00 phase=3 -->
### no-refactor-p3-t3 · discovery · no-refactor-because P3.T3 (phase 3)

state, notifier and main are thin adapters over run_org; nothing to clean

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p3-t4 created=2026-10-18T15:47:26+00:00 phase=3 -->
### no-refactor-p3-t4 · discovery · no-refactor-because P3.T4 (phase 3)

manifests are declarative and generated from one table; nothing to clean
