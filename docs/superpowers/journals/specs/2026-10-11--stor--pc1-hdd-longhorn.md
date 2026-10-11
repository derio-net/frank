# Journal: 2026-10-11--stor--pc1-hdd-longhorn

<!-- fr:journal kind=discovery scope=spec id=operator-brief created=2026-10-11T17:03:00+00:00 input=true -->
### operator-brief · discovery · Operator brief — batch pc1-hdd-longhorn (frank#824)

/fr-goal Brainstorm and spec: pc-1's three idle HDDs into Longhorn

Batch `pc1-hdd-longhorn` of derio-net/frank: 1 issues, delivered as ONE pull request.

## frank#824: stor: wire pc-1's three idle HDDs (2×1 TB + 500 GB) into Longhorn
2.5 TB of pc-1 HDDs never wired into Longhorn. Confirmed on main: no pc-1 disk patch exists; `patches/phase03-longhorn/401-gpu1-extra-disks.yaml` is the pattern to mirror; no node's Longhorn disk config is declared in git (`patches/phase03-longhorn/README.md` only). Five decisions are open in the operator's 2026-10-11 comment.
Note: BRAINSTORM FIRST (operator, 2026-10-11): brainstorm and write the spec settling the five decisions in https://github.com/derio-net/frank/issues/824#issuecomment-6106885345, then STOP for the operator's rulings before planning or implementing anything. This PR is spec-only, so write `Refs derio-net/frank#824`, not `Closes`: merging the spec must not close the issue. The PR stays a draft until the operator readies it.

## Why these belong together
BRAINSTORM FIRST, do not implement. Brainstorm and write the spec that settles the five decisions in https://github.com/derio-net/frank/issues/824#issuecomment-6106885345 (SMART health gate on the 2008-09 drives, sdd's old xfs data, HDD pool placement: hdd tag + dedicated StorageClass vs the default pool, binding by stable disk ID, codify the Longhorn node disks or keep them manual). Stop for the operator's rulings on those before any implementation. The PR stays a draft until the operator readies it.

## Delivery rules
- Work on branch `feat/batch-pc1-hdd-longhorn`.
- Open a draft PR as soon as the spec is committed. Its body contains these lines, one per member, so every member closes when it merges:
  Closes derio-net/frank#824
- Do not name any member issue as a phase `tracking_issue` in the plan: the bridge would then own that issue's `fr:` labels.

<!-- fr:journal kind=decision scope=spec id=smart-gate-strict created=2026-10-11T17:03:00+00:00 -->
### smart-gate-strict · decision · SMART gate is strict

Operator (round 1 q1): exclude a drive on overall FAIL, failed long self-test, or any non-zero raw 5/197/198; record 9/193/199 only. decider: operator. → R1

<!-- fr:journal kind=decision scope=spec id=sdd-stop-and-ask created=2026-10-11T17:03:00+00:00 -->
### sdd-stop-and-ask · decision · sdd with any content pauses for an operator ruling

Operator (round 1 q2): list sdd1 read-only; any content → summary on #824, sdd alone paused; never copied or wiped unilaterally. decider: operator. → R2

<!-- fr:journal kind=decision scope=spec id=pool-dedicated-plus-flip created=2026-10-11T17:03:00+00:00 -->
### pool-dedicated-plus-flip · decision · Dedicated hdd tier and allow-empty-disk-selector-volume=false

Operator (round 1 q3): tag HDDs `hdd`, own StorageClass, flip the global setting so empty-selector volumes stop landing on tagged disks (gpu-local too). decider: operator. → R5, R6

<!-- fr:journal kind=decision scope=spec id=hdd-consumers-ci-scratch created=2026-10-11T17:03:00+00:00 -->
### hdd-consumers-ci-scratch · decision · New longhorn-hdd class for CI scratch; Gitea/Zot/act-runner stay

Operator (round 1 q4): new 1-replica longhorn-hdd class for per-run CI workspaces; longhorn-cicd's long-lived consumers are not moved onto 2008 drives. decider: operator. → R7

<!-- fr:journal kind=decision scope=spec id=binding-uservolumeconfig-wwid created=2026-10-11T17:03:00+00:00 -->
### binding-uservolumeconfig-wwid · decision · Bind via Talos UserVolumeConfig with WWID CEL selector

Operator (round 1 q5): UserVolumeConfig + `disk.wwid ==` match, mounts at /var/mnt/<name>; not legacy machine.disks. decider: operator. → R3

<!-- fr:journal kind=decision scope=spec id=longhorn-disks-manual-op-patch-in-git created=2026-10-11T17:03:00+00:00 -->
### longhorn-disks-manual-op-patch-in-git · decision · Longhorn node disks stay a manual op, exact patch held in git, gpu-1 backfilled

Operator (round 1 q6): patch files under patches/phase03-longhorn/ applied by a # manual-operation; ArgoCD never owns nodes.longhorn.io. decider: operator. → R4

<!-- fr:journal kind=decision scope=spec id=verification-live created=2026-10-11T17:03:00+00:00 -->
### verification-live · decision · Verification is live post-merge; offline guards in CI

Operator (round 1 q7): every acceptance row verify: live; a guard test pins the declarative half pre-merge. decider: operator. → R9, ## Verification

<!-- fr:journal kind=decision scope=spec id=ci-scope-all-workspaces created=2026-10-11T17:03:00+00:00 -->
### ci-scope-all-workspaces · decision · All CI workspaces move to longhorn-hdd, incl. non-pinned templates

Operator (round 2 q1): move eventlistener-github (11 sites) AND kid-laptops-ci + generic triggertemplate, accepting that those two now depend on pc-1 being up. decider: operator. → R7, Risks

<!-- fr:journal kind=discovery scope=spec id=empty-selector-leaks-to-tagged-disks created=2026-10-11T17:03:00+00:00 -->
### empty-selector-leaks-to-tagged-disks · discovery · allow-empty-disk-selector-volume=true — tags do not isolate; gpu-local SSDs hold ~1.1 TiB of default-pool replicas

Live 2026-10-11: gpu-1's gpu-local disks carry default-class and longhorn-cicd replicas while gpu-1's NVMe default disk has 0 Gi scheduled (Longhorn prefers most free space). An hdd tag alone would make the HDDs the default pool's favourite target.

<!-- fr:journal kind=discovery scope=spec id=longhorn-cicd-not-pinned created=2026-10-11T17:03:00+00:00 -->
### longhorn-cicd-not-pinned · discovery · longhorn-cicd has no selector despite its "for pc-1" comment

155 replicas on gpu-1, 8 on pc-1. Its consumers include Gitea repos, Zot blobs, act-runner data and ~150 per-run Tekton workspaces.

<!-- fr:journal kind=discovery scope=spec id=hdd-class-single-replica created=2026-10-11T17:03:00+00:00 -->
### hdd-class-single-replica · discovery · An hdd-only class is single-replica by construction

replica-soft-anti-affinity=false (hard node anti-affinity) and only pc-1 carries hdd disks, so longhorn-hdd volumes have exactly one replica and no redundancy.

<!-- fr:journal kind=decision scope=spec id=gate-question-rounds-brainstorm created=2026-10-11T17:03:01+00:00 -->
### gate-question-rounds-brainstorm · decision · Operator gate `brainstorm` took two question rounds

Trigger: design-risk. Round 1 chose "all CI scratch to a new longhorn-hdd class"; the code check then showed only eventlistener-github's pipelines are pinned to pc-1 (kid-laptops-ci and the generic triggertemplate are not), so the scope choice carried an availability trade-off round 1 had not surfaced.

<!-- fr:journal kind=review scope=spec id=spec-review-r1 created=2026-10-11T17:08:17+00:00 -->
### spec-review-r1 · review · independent spec review: 8 findings (7 in scope, 1 out)

Findings: sr-1 … sr-8 (out of scope: sr-8). All 8 operator decisions reflected in R1–R7, R9, the rulings table and Risks; one wording drift (sr-5). Codebase references verified with file:line (pc-1 UUID patches/README.md:11, chart 1.11.2 apps/root/templates/longhorn.yaml:20, longhorn-extras owns apps/longhorn/manifests, scripts/tests/ runs in CI via .github/workflows/repo-tripwires.yml). No missed per-run consumer (eventlistener.yaml templates have no workspaces; staging-gate uses emptyDir).

<!-- fr:journal kind=finding scope=spec id=sr-1 created=2026-10-11T17:08:17+00:00 state=open review_scope=in -->
### sr-1 · finding [open] (reviewer: in scope) · eventlistener-github.yaml has 9 longhorn-cicd workspace sites, not 11; total 11 not 13

apps/tekton/triggers/eventlistener-github.yaml:473,514,556,584,611,634,671,709,757. Spec Context, R7 and Design §5 overcounted.

<!-- fr:journal kind=finding scope=spec id=sr-2 created=2026-10-11T17:08:17+00:00 state=open review_scope=in -->
### sr-2 · finding [open] (reviewer: in scope) · Workspace sizes are 1/2/5/8 Gi, not 2/8 Gi

triggertemplate.yaml:44 (1Gi); eventlistener-github.yaml:475,515,710 (5Gi).

<!-- fr:journal kind=finding scope=spec id=sr-3 created=2026-10-11T17:08:17+00:00 state=open review_scope=in -->
### sr-3 · finding [open] (reviewer: in scope) · R8 leaves docs still claiming longhorn-cicd is pinned to pc-1 / holds Tekton workspaces

README.md:297; building/27-cicd-platform:62; building/03-storage:386; operating/02-storage-backups:32,54-60; operating/22-cicd-platform:225,285; SC header line 2.

<!-- fr:journal kind=finding scope=spec id=sr-4 created=2026-10-11T17:08:17+00:00 state=open review_scope=in -->
### sr-4 · finding [open] (reviewer: in scope) · Test Plan's R8 row checks an untracked capacity audit and tests none of R8

Capacity-audit tooling lives in gitignored scripts/tmp/; R8 is a documentation requirement whose checks should be reviewable in the PR.

<!-- fr:journal kind=finding scope=spec id=sr-5 created=2026-10-11T17:08:17+00:00 state=open review_scope=in -->
### sr-5 · finding [open] (reviewer: in scope) · R2's "no user data" is softer than the operator's "any content" ruling

Journal decision sdd-stop-and-ask; R2 first sentence invited a judgement call the operator ruled out.

<!-- fr:journal kind=finding scope=spec id=sr-6 created=2026-10-11T17:08:17+00:00 state=open review_scope=in -->
### sr-6 · finding [open] (reviewer: in scope) · R9's disk-path assertion cannot hold for the gpu-1 file; R4 "same convention" ambiguous

gpu-1 paths come from machine.disks in 401-gpu1-extra-disks.yaml:17,20, not a UserVolumeConfig.

<!-- fr:journal kind=finding scope=spec id=sr-7 created=2026-10-11T17:08:17+00:00 state=open review_scope=in -->
### sr-7 · finding [open] (reviewer: in scope) · Merge window mis-described as Pending PVCs; step 5 checks one Application where three change

volumeBindingMode Immediate → PVC likely binds, volume Scheduled=False; longhorn, longhorn-extras and Tekton triggers apps all change.

<!-- fr:journal kind=finding scope=spec id=sr-8 created=2026-10-11T17:08:17+00:00 state=open review_scope=out -->
### sr-8 · finding [open] (reviewer: out of scope) · Default-group recurring backups apply to every longhorn-hdd CI scratch volume

apps/longhorn/manifests/recurring-job-daily.yaml:8-10, recurring-job-weekly.yaml:8-10 (groups: [default]).

<!-- fr:journal kind=finding scope=spec id=sr-1-resolved created=2026-10-11T17:08:17+00:00 state=fixed resolves=sr-1 -->
### sr-1-resolved · finding [fixed] · resolves sr-1: eventlistener-github.yaml has 9 longhorn-cicd workspace sites, not 11; total 11 not 13

Context, R7 and Design §5 now say 9 + 1 + 1 = 11, with line numbers; Design §5 makes the R9 guard enumerate every volumeClaimTemplate rather than trusting the count.

<!-- fr:journal kind=finding scope=spec id=sr-2-resolved created=2026-10-11T17:08:17+00:00 state=fixed resolves=sr-2 -->
### sr-2-resolved · finding [fixed] · resolves sr-2: Workspace sizes are 1/2/5/8 Gi, not 2/8 Gi

Context now reads 1, 2, 5 or 8 Gi.

<!-- fr:journal kind=finding scope=spec id=sr-3-resolved created=2026-10-11T17:08:17+00:00 state=fixed resolves=sr-3 -->
### sr-3-resolved · finding [fixed] · resolves sr-3: R8 leaves docs still claiming longhorn-cicd is pinned to pc-1 / holds Tekton workspaces

R8 enumerates every doc that claims longhorn-cicd is pc-1-pinned or holds Tekton workspaces; Design §3 corrects both SC header lines.

<!-- fr:journal kind=finding scope=spec id=sr-4-resolved created=2026-10-11T17:08:17+00:00 state=fixed resolves=sr-4 -->
### sr-4-resolved · finding [fixed] · resolves sr-4: Test Plan's R8 row checks an untracked capacity audit and tests none of R8

R8 Test Plan row now checks the R8 clauses in the PR diff (folding testable ones into R9); the capacity audit moved to an R3/R4 corroboration row, named as gitignored operator tooling.

<!-- fr:journal kind=finding scope=spec id=sr-5-resolved created=2026-10-11T17:08:17+00:00 state=fixed resolves=sr-5 -->
### sr-5-resolved · finding [fixed] · resolves sr-5: R2's "no user data" is softer than the operator's "any content" ruling

R2 and live step 2 now condition the wipe on sdd1 being empty (nothing beyond the filesystem root).

<!-- fr:journal kind=finding scope=spec id=sr-6-resolved created=2026-10-11T17:08:17+00:00 state=fixed resolves=sr-6 -->
### sr-6-resolved · finding [fixed] · resolves sr-6: R9's disk-path assertion cannot hold for the gpu-1 file; R4 "same convention" ambiguous

R9 scopes the path assertion per file (pc-1 ↔ 402 UserVolumeConfig, gpu-1 ↔ 401 machine.disks); R4 says patch-in-git manual-op convention, live gpu-1 names/paths unchanged.

<!-- fr:journal kind=finding scope=spec id=sr-7-resolved created=2026-10-11T17:08:17+00:00 state=fixed resolves=sr-7 -->
### sr-7-resolved · finding [fixed] · resolves sr-7: Merge window mis-described as Pending PVCs; step 5 checks one Application where three change

Step 5 names all three Applications and their operationState revision check, describes the likely Scheduled=False/attach symptom under Immediate binding (plan confirms), and asks for a quiet CI window with step 6 straight after.

<!-- fr:journal kind=finding scope=spec id=sr-8-resolved created=2026-10-11T17:08:17+00:00 state=open resolves=sr-8 out_of_scope=true -->
### sr-8-resolved · finding [out-of-scope] · resolves sr-8: Default-group recurring backups apply to every longhorn-hdd CI scratch volume

Default-group recurring jobs already cover every longhorn-cicd workspace; this change only moves where they read from. Recorded as a Risk with a follow-up to opt longhorn-hdd out of the default group.
