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
