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
