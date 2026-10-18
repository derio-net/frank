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

<!-- fr:journal kind=finding scope=plan id=p3-r1 created=2026-10-18T15:57:31+00:00 phase=3 state=open review_scope=in -->
### p3-r1 · finding [open] (reviewer: in scope) · Backstop matched 'spending limit' in any annotation (spoofable month-long flip) (phase 3)

Raised in phase-3 review.

<!-- fr:journal kind=finding scope=plan id=p3-r2 created=2026-10-18T15:57:31+00:00 phase=3 state=open review_scope=in -->
### p3-r2 · finding [open] (reviewer: in scope) · Heartbeat rule counted any tekton-pipelines pod and verdict=error lines (phase 3)

Raised in phase-3 review.

<!-- fr:journal kind=finding scope=plan id=p3-r3 created=2026-10-18T15:57:31+00:00 phase=3 state=open review_scope=in -->
### p3-r3 · finding [open] (reviewer: in scope) · billing repositoryName may be owner/name; public exclusion and pinned_share assumed bare names (phase 3)

Raised in phase-3 review.

<!-- fr:journal kind=finding scope=plan id=p3-r4 created=2026-10-18T15:57:31+00:00 phase=3 state=open review_scope=in -->
### p3-r4 · finding [open] (reviewer: in scope) · Backstop rerun branch created and run marked handled after a failed apply; notice overstated (phase 3)

Raised in phase-3 review.

<!-- fr:journal kind=finding scope=plan id=p3-r5 created=2026-10-18T15:57:31+00:00 phase=3 state=open review_scope=in -->
### p3-r5 · finding [open] (reviewer: in scope) · Coverage refusal also blocked the safe move back to github (phase 3)

Raised in phase-3 review.

<!-- fr:journal kind=finding scope=plan id=p3-r6 created=2026-10-18T15:57:31+00:00 phase=3 state=open review_scope=in -->
### p3-r6 · finding [open] (reviewer: in scope) · Rerun-branch cleanup aged branches by commit time after state loss (phase 3)

Raised in phase-3 review.

<!-- fr:journal kind=finding scope=plan id=p3-r7 created=2026-10-18T15:57:31+00:00 phase=3 state=open review_scope=in -->
### p3-r7 · finding [open] (reviewer: in scope) · Missing month-sequence, spoof and owner/name tests; heartbeat-line test was a source grep (phase 3)

Raised in phase-3 review.

<!-- fr:journal kind=finding scope=plan id=p3-sec1 created=2026-10-18T15:57:31+00:00 phase=3 state=open review_scope=in -->
### p3-sec1 · finding [open] (reviewer: in scope) · Automated security review: backstop annotation spoofing (same as p3-r1) (phase 3)

Raised in phase-3 review.

<!-- fr:journal kind=finding scope=plan id=p3-sec2 created=2026-10-18T15:57:31+00:00 phase=3 state=open review_scope=in -->
### p3-sec2 · finding [open] (reviewer: in scope) · Automated security review: heartbeat fail-open/spoofing (same as p3-r2) (phase 3)

Raised in phase-3 review.

<!-- fr:journal kind=review scope=plan id=review-p3 created=2026-10-18T15:57:31+00:00 phase=3 -->
### review-p3 · review · Phase 3 code review: 7 findings + 2 security items, all fixed (phase 3)

Independent code-reviewer subagent reviewed the six phase-3 commits against spec §4 and plan 03.yaml, ran 126 tests and gave explicit verdicts on the two security items (both confirmed). Fixes landed TDD in e93c5e5f: strict backstop matching, a scoped heartbeat that excludes errors plus a ci-budget-watcher-erroring rule, repositoryName normalisation, outcome-based rerun and retry, a gitea-only coverage gate (spec R11 updated), first-seen branch ageing, and a three-tick month test. The orchestrator re-ran the suites: 141 passed.

<!-- fr:journal kind=finding scope=plan id=p3-r1-resolved created=2026-10-18T15:57:31+00:00 phase=3 state=fixed resolves=p3-r1 -->
### p3-r1-resolved · finding [fixed] · resolves p3-r1: Backstop matched 'spending limit' in any annotation (spoofable month-long flip) (phase 3)

Fixed in e93c5e5f (p3-r5 also in spec R11/§4 step 5; p3-r3 shape confirmation added to the PRE-MERGE billing op).

<!-- fr:journal kind=finding scope=plan id=p3-r2-resolved created=2026-10-18T15:57:31+00:00 phase=3 state=fixed resolves=p3-r2 -->
### p3-r2-resolved · finding [fixed] · resolves p3-r2: Heartbeat rule counted any tekton-pipelines pod and verdict=error lines (phase 3)

Fixed in e93c5e5f (p3-r5 also in spec R11/§4 step 5; p3-r3 shape confirmation added to the PRE-MERGE billing op).

<!-- fr:journal kind=finding scope=plan id=p3-r3-resolved created=2026-10-18T15:57:31+00:00 phase=3 state=fixed resolves=p3-r3 -->
### p3-r3-resolved · finding [fixed] · resolves p3-r3: billing repositoryName may be owner/name; public exclusion and pinned_share assumed bare names (phase 3)

Fixed in e93c5e5f (p3-r5 also in spec R11/§4 step 5; p3-r3 shape confirmation added to the PRE-MERGE billing op).

<!-- fr:journal kind=finding scope=plan id=p3-r4-resolved created=2026-10-18T15:57:31+00:00 phase=3 state=fixed resolves=p3-r4 -->
### p3-r4-resolved · finding [fixed] · resolves p3-r4: Backstop rerun branch created and run marked handled after a failed apply; notice overstated (phase 3)

Fixed in e93c5e5f (p3-r5 also in spec R11/§4 step 5; p3-r3 shape confirmation added to the PRE-MERGE billing op).

<!-- fr:journal kind=finding scope=plan id=p3-r5-resolved created=2026-10-18T15:57:31+00:00 phase=3 state=fixed resolves=p3-r5 -->
### p3-r5-resolved · finding [fixed] · resolves p3-r5: Coverage refusal also blocked the safe move back to github (phase 3)

Fixed in e93c5e5f (p3-r5 also in spec R11/§4 step 5; p3-r3 shape confirmation added to the PRE-MERGE billing op).

<!-- fr:journal kind=finding scope=plan id=p3-r6-resolved created=2026-10-18T15:57:31+00:00 phase=3 state=fixed resolves=p3-r6 -->
### p3-r6-resolved · finding [fixed] · resolves p3-r6: Rerun-branch cleanup aged branches by commit time after state loss (phase 3)

Fixed in e93c5e5f (p3-r5 also in spec R11/§4 step 5; p3-r3 shape confirmation added to the PRE-MERGE billing op).

<!-- fr:journal kind=finding scope=plan id=p3-r7-resolved created=2026-10-18T15:57:31+00:00 phase=3 state=fixed resolves=p3-r7 -->
### p3-r7-resolved · finding [fixed] · resolves p3-r7: Missing month-sequence, spoof and owner/name tests; heartbeat-line test was a source grep (phase 3)

Fixed in e93c5e5f (p3-r5 also in spec R11/§4 step 5; p3-r3 shape confirmation added to the PRE-MERGE billing op).

<!-- fr:journal kind=finding scope=plan id=p3-sec1-resolved created=2026-10-18T15:57:31+00:00 phase=3 state=fixed resolves=p3-sec1 -->
### p3-sec1-resolved · finding [fixed] · resolves p3-sec1: Automated security review: backstop annotation spoofing (same as p3-r1) (phase 3)

Fixed in e93c5e5f (p3-r5 also in spec R11/§4 step 5; p3-r3 shape confirmation added to the PRE-MERGE billing op).

<!-- fr:journal kind=finding scope=plan id=p3-sec2-resolved created=2026-10-18T15:57:31+00:00 phase=3 state=fixed resolves=p3-sec2 -->
### p3-sec2-resolved · finding [fixed] · resolves p3-sec2: Automated security review: heartbeat fail-open/spoofing (same as p3-r2) (phase 3)

Fixed in e93c5e5f (p3-r5 also in spec R11/§4 step 5; p3-r3 shape confirmation added to the PRE-MERGE billing op).

<!-- fr:journal kind=decision scope=plan id=p4-report-reads-visibility-via-billing-token created=2026-10-18T16:07:45+00:00 phase=4 -->
### p4-report-reads-visibility-via-billing-token · decision · Report reads public repos with the billing token's repo listing (phase 4) (phase 4)

Same public_repos call the watcher uses (metadata read), so public-repo exclusion and the 'now public, remove' proposal agree with the flip logic; spec said authority token where visible, but billing token is the one that can list the whole org.

<!-- fr:journal kind=decision scope=plan id=p4-issue-upsert-matches-any-state created=2026-10-18T16:07:45+00:00 phase=4 -->
### p4-issue-upsert-matches-any-state · decision · Issue upsert matches by exact title across open and closed issues, ignoring PRs (phase 4) (phase 4)

GET issues?labels=ci-tiers&state=all paginated; a re-run edits the existing body (never duplicates, never reopens). Pull requests that carry the label are skipped.

<!-- fr:journal kind=decision scope=plan id=p4-stoa-workflow-files-via-mirror-token created=2026-10-18T16:07:45+00:00 phase=4 -->
### p4-stoa-workflow-files-via-mirror-token · decision · agentic-stoa workflow files are read with the stoa-github-mirror token (phase 4) (phase 4)

The report CronJob maps GH_AUTHORITY_TOKEN_AGENTIC_STOA to the stoa-github-mirror Secret (optional), since stoa has no ci-authority generator. It mounts no service-account token and no Gitea/Telegram credentials.

<!-- fr:journal kind=discovery scope=plan id=p4-fake-http-page-substring-trap created=2026-10-18T16:07:45+00:00 phase=4 -->
### p4-fake-http-page-substring-trap · discovery · A fake pager matching 'page=1' in the URL also matches per_page=100 (phase 4) (phase 4)

Looped forever on page 2; the fake now matches url.endswith('&page=1').

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p4-t2 created=2026-10-18T16:07:45+00:00 phase=4 -->
### no-refactor-p4-t2 · discovery · no-refactor-because P4.T2 (phase 4) (phase 4)

manifests are declarative, derived from the watcher CronJob; nothing to clean

<!-- fr:journal kind=finding scope=plan id=p4-r1 created=2026-10-18T18:56:10+00:00 phase=4 state=open review_scope=in -->
### p4-r1 · finding [open] (reviewer: in scope) · Report named billed repos absent from tiers.yaml in the public issue (phase 4)

Raised in phase-4 review.

<!-- fr:journal kind=finding scope=plan id=p4-r2 created=2026-10-18T18:56:10+00:00 phase=4 state=open review_scope=in -->
### p4-r2 · finding [open] (reviewer: in scope) · agentic-stoa (third party) rendered per repo (phase 4)

Raised in phase-4 review.

<!-- fr:journal kind=finding scope=plan id=p4-r3 created=2026-10-18T18:56:10+00:00 phase=4 state=open review_scope=in -->
### p4-r3 · finding [open] (reviewer: in scope) · Raw exception text and response bodies rendered into the issue (phase 4)

Raised in phase-4 review.

<!-- fr:journal kind=finding scope=plan id=p4-r4 created=2026-10-18T18:56:10+00:00 phase=4 state=open review_scope=in -->
### p4-r4 · finding [open] (reviewer: in scope) · Tests asserted the leak; redaction test missing (phase 4)

Raised in phase-4 review.

<!-- fr:journal kind=finding scope=plan id=p4-r5 created=2026-10-18T18:56:10+00:00 phase=4 state=open review_scope=in -->
### p4-r5 · finding [open] (reviewer: in scope) · Per-repo minutes and tier rendered only for over-threshold orgs (phase 4)

Raised in phase-4 review.

<!-- fr:journal kind=finding scope=plan id=p4-r6 created=2026-10-18T18:56:10+00:00 phase=4 state=open review_scope=in -->
### p4-r6 · finding [open] (reviewer: in scope) · Upsert found the issue only through its label (phase 4)

Raised in phase-4 review.

<!-- fr:journal kind=finding scope=plan id=p4-sec1 created=2026-10-18T18:56:10+00:00 phase=4 state=open review_scope=in -->
### p4-sec1 · finding [open] (reviewer: in scope) · Automated security review: private data in the public issue (same as p4-r1..r3) (phase 4)

Raised in phase-4 review.

<!-- fr:journal kind=finding scope=plan id=p4-sec2 created=2026-10-18T18:56:10+00:00 phase=4 state=open review_scope=in -->
### p4-sec2 · finding [open] (reviewer: in scope) · Automated security review: report reused stoa-github-mirror (statuses:write) to read workflow files (phase 4)

Raised in phase-4 review.

<!-- fr:journal kind=finding scope=plan id=p4-sec3 created=2026-10-18T18:56:10+00:00 phase=4 state=open review_scope=in -->
### p4-sec3 · finding [open] (reviewer: in scope) · Automated security review: title-search upsert could adopt a human-authored issue (phase 4)

Raised in phase-4 review.

<!-- fr:journal kind=review scope=plan id=review-p4 created=2026-10-18T18:56:10+00:00 phase=4 -->
### review-p4 · review · Phase 4 code review: 6 findings + 3 security items, all fixed (phase 4)

Independent code-reviewer subagent reviewed 8e9be73d, 27d89429 and 2b9a04dd against spec §5 (incl. the Redaction paragraph) and plan 04.yaml. It found the redaction unimplemented and the tests locking in the leak. Fixes landed TDD in d1bfe190 and eae880d4: unlisted repos collapsed to a count, a third_party org rendered as totals only, errors reported by class and status, a redaction test via main, a per-repo table every month, a title-search fallback that adopts only issues by derio-fr-automation[bot], and a dedicated read-only stoa token. The orchestrator re-ran the suites: 131 passed.

<!-- fr:journal kind=finding scope=plan id=p4-r1-resolved created=2026-10-18T18:56:10+00:00 phase=4 state=fixed resolves=p4-r1 -->
### p4-r1-resolved · finding [fixed] · resolves p4-r1: Report named billed repos absent from tiers.yaml in the public issue (phase 4)

Fixed in d1bfe190 / eae880d4 (p4-sec2 also in spec §4/§5).

<!-- fr:journal kind=finding scope=plan id=p4-r2-resolved created=2026-10-18T18:56:10+00:00 phase=4 state=fixed resolves=p4-r2 -->
### p4-r2-resolved · finding [fixed] · resolves p4-r2: agentic-stoa (third party) rendered per repo (phase 4)

Fixed in d1bfe190 / eae880d4 (p4-sec2 also in spec §4/§5).

<!-- fr:journal kind=finding scope=plan id=p4-r3-resolved created=2026-10-18T18:56:10+00:00 phase=4 state=fixed resolves=p4-r3 -->
### p4-r3-resolved · finding [fixed] · resolves p4-r3: Raw exception text and response bodies rendered into the issue (phase 4)

Fixed in d1bfe190 / eae880d4 (p4-sec2 also in spec §4/§5).

<!-- fr:journal kind=finding scope=plan id=p4-r4-resolved created=2026-10-18T18:56:10+00:00 phase=4 state=fixed resolves=p4-r4 -->
### p4-r4-resolved · finding [fixed] · resolves p4-r4: Tests asserted the leak; redaction test missing (phase 4)

Fixed in d1bfe190 / eae880d4 (p4-sec2 also in spec §4/§5).

<!-- fr:journal kind=finding scope=plan id=p4-r5-resolved created=2026-10-18T18:56:10+00:00 phase=4 state=fixed resolves=p4-r5 -->
### p4-r5-resolved · finding [fixed] · resolves p4-r5: Per-repo minutes and tier rendered only for over-threshold orgs (phase 4)

Fixed in d1bfe190 / eae880d4 (p4-sec2 also in spec §4/§5).

<!-- fr:journal kind=finding scope=plan id=p4-r6-resolved created=2026-10-18T18:56:10+00:00 phase=4 state=fixed resolves=p4-r6 -->
### p4-r6-resolved · finding [fixed] · resolves p4-r6: Upsert found the issue only through its label (phase 4)

Fixed in d1bfe190 / eae880d4 (p4-sec2 also in spec §4/§5).

<!-- fr:journal kind=finding scope=plan id=p4-sec1-resolved created=2026-10-18T18:56:10+00:00 phase=4 state=fixed resolves=p4-sec1 -->
### p4-sec1-resolved · finding [fixed] · resolves p4-sec1: Automated security review: private data in the public issue (same as p4-r1..r3) (phase 4)

Fixed in d1bfe190 / eae880d4 (p4-sec2 also in spec §4/§5).

<!-- fr:journal kind=finding scope=plan id=p4-sec2-resolved created=2026-10-18T18:56:10+00:00 phase=4 state=fixed resolves=p4-sec2 -->
### p4-sec2-resolved · finding [fixed] · resolves p4-sec2: Automated security review: report reused stoa-github-mirror (statuses:write) to read workflow files (phase 4)

Fixed in d1bfe190 / eae880d4 (p4-sec2 also in spec §4/§5).

<!-- fr:journal kind=finding scope=plan id=p4-sec3-resolved created=2026-10-18T18:56:10+00:00 phase=4 state=fixed resolves=p4-sec3 -->
### p4-sec3-resolved · finding [fixed] · resolves p4-sec3: Automated security review: title-search upsert could adopt a human-authored issue (phase 4)

Fixed in d1bfe190 / eae880d4 (p4-sec2 also in spec §4/§5).

<!-- fr:journal kind=discovery scope=plan id=gitea-runner-admin-api created=2026-10-18T19:21:48+00:00 phase=5 -->
### gitea-runner-admin-api · discovery · Gitea 1.25.4 has admin Actions runner and job listings (GET, read:admin) (phase 5)

Live Gitea is 1.25.4. GET /api/v1/admin/actions/runners returns {"runners":[{id,name,status("online"|"offline"),busy,ephemeral,labels:[{id,name,type}]}],"total_count":N}; there is NO last_seen field, so liveness is `status`. GET /api/v1/admin/actions/jobs?status=waiting returns {"jobs":[{id,run_id,name,labels,status,conclusion,runner_id,runner_name,created_at,started_at,completed_at,...}],"total_count":N} (empty at capture). GET /admin/actions/runs also exists; /admin/runners is 404. Queue age = now - created_at of waiting jobs. The spec's kube_deployment fallback was therefore not needed. Fixtures captured to scripts/tests/fixtures/ci_budget/gitea_admin_*.json (the waiting queue was empty, so waiting-job tests re-status the one captured job object).

<!-- fr:journal kind=discovery scope=plan id=pc1-var-series-labels created=2026-10-18T19:21:48+00:00 phase=5 -->
### pc1-var-series-labels · discovery · pc-1 /var series has no node label; identity is instance 192.168.55.71:9100 (phase 5)

node_filesystem_avail_bytes{mountpoint="/var"} on pc-1 carries job=node-exporter, instance=192.168.55.71:9100, device=/dev/sda4, fstype=xfs, namespace=monitoring, pod=victoria-metrics-prometheus-node-exporter-88p8q. Observed 2026-10-18: avail 22.4 GB of 61.6 GB (36%). The rule selects instance+mountpoint. VMSingle is reachable only on its pod IP :8428 via kubectl exec wget (localhost does not listen).

<!-- fr:journal kind=discovery scope=plan id=p5-fifteen-minute-exemption created=2026-10-18T19:21:48+00:00 phase=5 -->
### p5-fifteen-minute-exemption · discovery · layer-25-pc1-var-low needed a written FIFTEEN_MINUTE_EXEMPTIONS entry (phase 5)

The feature-health guard reserves 15m for DaemonSet rules; the spec mandates 15m for pc-1 /var, so a reasoned exemption was added rather than changing the window.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p5-t1 created=2026-10-18T19:21:48+00:00 phase=5 -->
### no-refactor-p5-t1 · discovery · no-refactor-because P5.T1 (phase 5)

one-line limit change plus a guard; nothing to clean

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p5-t2 created=2026-10-18T19:21:48+00:00 phase=5 -->
### no-refactor-p5-t2 · discovery · no-refactor-because P5.T2 (phase 5)

probe functions written once against the captured shapes; no duplication

<!-- fr:journal kind=discovery scope=plan id=runner-rule-logsql-verified created=2026-10-18T19:33:55+00:00 phase=5 -->
### runner-rule-logsql-verified · discovery · Runner LogsQL shapes verified live against VictoriaLogs (phase 5) (phase 5)

Read-only stats_query on Frank VictoriaLogs (pod IP :9428). No ci-runner-probe lines exist yet (watcher not deployed): the exact scoped query parses and returns an empty value (NoData -> OK). On an existing Frank stream with the same key=<number> shape (pipelinerun-ttl-gc result ... deleted=N remaining=N cutoff=...), '| extract "deleted=<n> remaining=" | stats max(n)' returned 419 and min(n) 0, '| extract "remaining=<n> cutoff=" | stats max(n)' returned 989: extract + stats max/min are numeric. Needs an explicit _time window in ad-hoc queries; Grafana supplies it from relativeTimeRange. Hop streams carry the message in 'log', Frank in '_msg'. The pc-1 join node_filesystem_avail_bytes/size * on(instance) group_left() node_uname_info{nodename="pc-1"} returns the pc-1 /var series (0.363).

<!-- fr:journal kind=discovery scope=plan id=gitea-rerun-keeps-created created=2026-10-18T19:34:05+00:00 phase=5 -->
### gitea-rerun-keeps-created · discovery · Gitea 1.25.4 rerun keeps the job's original created_at (phase 5) (phase 5)

Read from go-gitea v1.25.4 routers/web/repo/actions/view.go: rerun of a job updates only task_id, status, started, stopped (UpdateRunJob columns); the job's xorm-created 'created' is untouched, so the API created_at is the first attempt's. The API job object carries run_attempt, so the watcher counts reruns in waiting but excludes run_attempt>1 from oldest_waiting_s, and counts jobs whose labels the runner does not serve as unservable=K instead.

<!-- fr:journal kind=finding scope=plan id=p5-r1 created=2026-10-18T19:37:55+00:00 phase=5 state=open review_scope=in -->
### p5-r1 · finding [open] (reviewer: in scope) · runner-offline fired on a single runners_online=0 sample (phase 5)

Raised in phase-5 review.

<!-- fr:journal kind=finding scope=plan id=p5-r2 created=2026-10-18T19:37:55+00:00 phase=5 state=open review_scope=in -->
### p5-r2 · finding [open] (reviewer: in scope) · queue-wait fired on one sample and stayed firing after drain (phase 5)

Raised in phase-5 review.

<!-- fr:journal kind=finding scope=plan id=p5-r3 created=2026-10-18T19:37:55+00:00 phase=5 state=open review_scope=in -->
### p5-r3 · finding [open] (reviewer: in scope) · Missing/revoked probe token made both runner rules silently OK (phase 5)

Raised in phase-5 review.

<!-- fr:journal kind=finding scope=plan id=p5-r4 created=2026-10-18T19:37:55+00:00 phase=5 state=open review_scope=in -->
### p5-r4 · finding [open] (reviewer: in scope) · Queue age counted unservable-label jobs and reruns' original created_at (phase 5)

Raised in phase-5 review.

<!-- fr:journal kind=finding scope=plan id=p5-r5 created=2026-10-18T19:37:55+00:00 phase=5 state=open review_scope=in -->
### p5-r5 · finding [open] (reviewer: in scope) · queue-wait LogsQL shape unverified live (phase 5)

Raised in phase-5 review.

<!-- fr:journal kind=finding scope=plan id=p5-r6 created=2026-10-18T19:37:55+00:00 phase=5 state=open review_scope=in -->
### p5-r6 · finding [open] (reviewer: in scope) · One failing admin call discarded both signals (phase 5)

Raised in phase-5 review.

<!-- fr:journal kind=finding scope=plan id=p5-r7 created=2026-10-18T19:37:55+00:00 phase=5 state=open review_scope=in -->
### p5-r7 · finding [open] (reviewer: in scope) · pc-1 /var rule relied on a hard-coded IP; docs claimed device identity (phase 5)

Raised in phase-5 review.

<!-- fr:journal kind=finding scope=plan id=p5-r8 created=2026-10-18T19:37:55+00:00 phase=5 state=open review_scope=in -->
### p5-r8 · finding [open] (reviewer: in scope) · Probe tests lacked pagination, exact-URL, offset and page-2 404 cases (phase 5)

Raised in phase-5 review.

<!-- fr:journal kind=review scope=plan id=review-p5 created=2026-10-18T19:37:55+00:00 phase=5 -->
### review-p5 · review · Phase 5 code review: 8 findings, all fixed (phase 5)

Independent code-reviewer subagent reviewed 581a0b53, 1b7d3628, 6aefbef0 and b43d8c3a against spec §7 and plan 05.yaml and ran 144 tests. Fixes landed TDD in 07707bc2 and 8c27dbdd: sustained-condition rules (max/min over the window), a new layer-25-runner-probe-blind rule, an explicit no-token error line, unservable/rerun-aware queue age (Gitea 1.25.4 rerun keeps created, verified in source), per-call guards, pc-1 selected by node_uname_info nodename (checked live), and new pagination/URL/offset tests. LogsQL shapes were verified live (discovery runner-rule-logsql-verified), and Test Plan row 10 was extended. The orchestrator re-ran the suites: they pass.

<!-- fr:journal kind=finding scope=plan id=p5-r1-resolved created=2026-10-18T19:37:55+00:00 phase=5 state=fixed resolves=p5-r1 -->
### p5-r1-resolved · finding [fixed] · resolves p5-r1: runner-offline fired on a single runners_online=0 sample (phase 5)

Fixed in 07707bc2 / 8c27dbdd (p5-r5 also discovery f4aa6e7d and spec Test Plan row 10).

<!-- fr:journal kind=finding scope=plan id=p5-r2-resolved created=2026-10-18T19:37:55+00:00 phase=5 state=fixed resolves=p5-r2 -->
### p5-r2-resolved · finding [fixed] · resolves p5-r2: queue-wait fired on one sample and stayed firing after drain (phase 5)

Fixed in 07707bc2 / 8c27dbdd (p5-r5 also discovery f4aa6e7d and spec Test Plan row 10).

<!-- fr:journal kind=finding scope=plan id=p5-r3-resolved created=2026-10-18T19:37:55+00:00 phase=5 state=fixed resolves=p5-r3 -->
### p5-r3-resolved · finding [fixed] · resolves p5-r3: Missing/revoked probe token made both runner rules silently OK (phase 5)

Fixed in 07707bc2 / 8c27dbdd (p5-r5 also discovery f4aa6e7d and spec Test Plan row 10).

<!-- fr:journal kind=finding scope=plan id=p5-r4-resolved created=2026-10-18T19:37:55+00:00 phase=5 state=fixed resolves=p5-r4 -->
### p5-r4-resolved · finding [fixed] · resolves p5-r4: Queue age counted unservable-label jobs and reruns' original created_at (phase 5)

Fixed in 07707bc2 / 8c27dbdd (p5-r5 also discovery f4aa6e7d and spec Test Plan row 10).

<!-- fr:journal kind=finding scope=plan id=p5-r5-resolved created=2026-10-18T19:37:55+00:00 phase=5 state=fixed resolves=p5-r5 -->
### p5-r5-resolved · finding [fixed] · resolves p5-r5: queue-wait LogsQL shape unverified live (phase 5)

Fixed in 07707bc2 / 8c27dbdd (p5-r5 also discovery f4aa6e7d and spec Test Plan row 10).

<!-- fr:journal kind=finding scope=plan id=p5-r6-resolved created=2026-10-18T19:37:55+00:00 phase=5 state=fixed resolves=p5-r6 -->
### p5-r6-resolved · finding [fixed] · resolves p5-r6: One failing admin call discarded both signals (phase 5)

Fixed in 07707bc2 / 8c27dbdd (p5-r5 also discovery f4aa6e7d and spec Test Plan row 10).

<!-- fr:journal kind=finding scope=plan id=p5-r7-resolved created=2026-10-18T19:37:55+00:00 phase=5 state=fixed resolves=p5-r7 -->
### p5-r7-resolved · finding [fixed] · resolves p5-r7: pc-1 /var rule relied on a hard-coded IP; docs claimed device identity (phase 5)

Fixed in 07707bc2 / 8c27dbdd (p5-r5 also discovery f4aa6e7d and spec Test Plan row 10).

<!-- fr:journal kind=finding scope=plan id=p5-r8-resolved created=2026-10-18T19:37:55+00:00 phase=5 state=fixed resolves=p5-r8 -->
### p5-r8-resolved · finding [fixed] · resolves p5-r8: Probe tests lacked pagination, exact-URL, offset and page-2 404 cases (phase 5)

Fixed in 07707bc2 / 8c27dbdd (p5-r5 also discovery f4aa6e7d and spec Test Plan row 10).

<!-- fr:journal kind=finding scope=plan id=xr-checker-refinements created=2026-10-18T19:48:16+00:00 state=open review_scope=out -->
### xr-checker-refinements · finding [open] (reviewer: out of scope) · Gate-coverage checker: implicit github.token in actions, and the STOA_CI_GH_TOKEN||GITHUB_TOKEN fallback pattern

Raised by the cross-repo PR reviewers (runs-fr#43, cnc-fru#41). (1) The checker cannot see actions that use the default github.token implicitly (e.g. golangci-lint-action), so a gated job can still call GitHub with Gitea's token. Confirm them on the first real Gitea run. (2) The checker flags agentic-stoa's established secrets.STOA_CI_GH_TOKEN || secrets.GITHUB_TOKEN with: pattern as fallback-github-token-to-github, which is likely a false positive. Not caused by this change: agentic-stoa is never flipped, so only the report gets noisier.

<!-- fr:journal kind=finding scope=plan id=xr-acceptance-step-pin created=2026-10-18T19:48:19+00:00 state=open review_scope=out -->
### xr-acceptance-step-pin · finding [open] (reviewer: out of scope) · acceptance-report: pin only the issue-upsert step so the acceptance check also falls back

Raised by the reviewers on homelab#38, omada-controller#53, presentation-craft#6 and proxmox-cluster#109. Each repo's acceptance-report job is GitHub-pinned as a whole, per spec R2. Authority-gating the job and pinning only the weekly upsert step would keep 'fr acceptance check' running on Gitea during fallback. This change does not require it.

<!-- fr:journal kind=finding scope=plan id=xr-vibe-kanban-no-fallback created=2026-10-18T19:48:22+00:00 state=open review_scope=out -->
### xr-vibe-kanban-no-fallback · finding [open] (reviewer: out of scope) · vibe-kanban has no Gitea fallback (Blacksmith runners): review its tier

vibe-kanban#19 pinned all 28 jobs to GitHub. Its test jobs run on blacksmith-16vcpu-ubuntu-2404, and switching them would change GitHub behaviour, so its github-preferred tier moves nothing. Either mark it github-only in tiers.yaml at the next monthly review, or add a separate authority-gated ubuntu-latest check job.

<!-- fr:journal kind=finding scope=plan id=p2-r4-resolved-2 created=2026-10-18T19:49:28+00:00 phase=2 state=open resolves=p2-r4 tracked_by=https://github.com/derio-net/frank/issues/882 -->
### p2-r4-resolved-2 · finding [deferred → https://github.com/derio-net/frank/issues/882] · resolves p2-r4: gitea-listener status webhooks carry no HMAC (phase 2)

Filed at deliver as https://github.com/derio-net/frank/issues/882.

<!-- fr:journal kind=finding scope=plan id=willikins-doc-pr-authority-resolved created=2026-10-18T19:49:36+00:00 phase=3 state=open resolves=willikins-doc-pr-authority filed_as=derio-net/frank#883 -->
### willikins-doc-pr-authority-resolved · finding [filed → derio-net/frank#883] · resolves willikins-doc-pr-authority: File follow-up issue in derio-net/willikins: doc-pr must read CI_AUTHORITY (phase 3)

Filed at deliver as derio-net/frank#883; still owed until discharged.

<!-- fr:journal kind=finding scope=plan id=xr-checker-refinements-resolved created=2026-10-18T19:50:47+00:00 state=open resolves=xr-checker-refinements out_of_scope=true -->
### xr-checker-refinements-resolved · finding [out-of-scope] · resolves xr-checker-refinements: Gate-coverage checker: implicit github.token in actions, and the STOA_CI_GH_TOKEN||GITHUB_TOKEN fallback pattern

Not caused by this change: implicit default-token use is undetectable statically, and the stoa fallback pattern predates it. Follow-up only.

<!-- fr:journal kind=finding scope=plan id=xr-acceptance-step-pin-resolved created=2026-10-18T19:50:50+00:00 state=open resolves=xr-acceptance-step-pin out_of_scope=true -->
### xr-acceptance-step-pin-resolved · finding [out-of-scope] · resolves xr-acceptance-step-pin: acceptance-report: pin only the issue-upsert step so the acceptance check also falls back

Spec R2 pins acceptance-report as mutating; a step-level split is an optional improvement in other repos.

<!-- fr:journal kind=finding scope=plan id=xr-vibe-kanban-no-fallback-resolved created=2026-10-18T19:50:53+00:00 state=open resolves=xr-vibe-kanban-no-fallback out_of_scope=true -->
### xr-vibe-kanban-no-fallback-resolved · finding [out-of-scope] · resolves xr-vibe-kanban-no-fallback: vibe-kanban has no Gitea fallback (Blacksmith runners): review its tier

A consequence of vibe-kanban's third-party runner choice, not of this change; a tier-review item for the monthly report.

<!-- fr:journal kind=finding scope=plan id=xr-checker-refinements-resolved-2 created=2026-10-18T19:51:01+00:00 state=open resolves=xr-checker-refinements tracked_by=https://github.com/derio-net/frank/issues/884 -->
### xr-checker-refinements-resolved-2 · finding [deferred → https://github.com/derio-net/frank/issues/884] · resolves xr-checker-refinements: Gate-coverage checker: implicit github.token in actions, and the STOA_CI_GH_TOKEN||GITHUB_TOKEN fallback pattern

Filed at deliver as https://github.com/derio-net/frank/issues/884.

<!-- fr:journal kind=finding scope=plan id=xr-acceptance-step-pin-resolved-2 created=2026-10-18T19:51:09+00:00 state=open resolves=xr-acceptance-step-pin tracked_by=https://github.com/derio-net/frank/issues/885 -->
### xr-acceptance-step-pin-resolved-2 · finding [deferred → https://github.com/derio-net/frank/issues/885] · resolves xr-acceptance-step-pin: acceptance-report: pin only the issue-upsert step so the acceptance check also falls back

Filed at deliver as https://github.com/derio-net/frank/issues/885.
