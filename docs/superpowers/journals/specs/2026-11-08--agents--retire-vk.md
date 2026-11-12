<!-- fr:journal-schema=3 -->
# Journal: 2026-11-08--agents--retire-vk

<!-- fr:journal kind=discovery scope=spec id=operator-brief created=2026-11-08T19:31:46+00:00 input=true -->
### operator-brief · discovery · Operator brief (verbatim)

I decided to retire VK completely, in two phases. First remove all dependencies, alarms, images. Second: take the secure-agent-pod down if it's not otherwise used (it is not but it's temporary), mark the blog post(s) superceded and clean up

<!-- fr:journal kind=decision scope=spec id=d-pod-end-state created=2026-11-08T21:39:16+00:00 decided_by=operator -->
### d-pod-end-state · decision · Archive then delete the pod

The operator's interactive triage run is the only temporary use. Archive the files worth keeping, then delete the Application, namespace, PVC, LoadBalancers and cluster-admin binding.

<!-- fr:journal kind=decision scope=spec id=d-chorebot created=2026-11-08T21:39:16+00:00 decided_by=operator -->
### d-chorebot · decision · Let chorebot stop

No migration. Its data in Notion and code in willikins allow later revival.

<!-- fr:journal kind=decision scope=spec id=d-images created=2026-11-08T21:39:16+00:00 decided_by=operator -->
### d-images · decision · Stop builds, archive the fork, keep GHCR packages

The agent-images legs are removed, derio-net/vibe-kanban is archived, and published packages are retained so old commits still resolve.

<!-- fr:journal kind=decision scope=spec id=d-shipping created=2026-11-08T21:39:16+00:00 decided_by=operator -->
### d-shipping · decision · Two PRs with live checks

vk-local stays until Phase 2 so Phase 1 never rolls the pod. Phase 2 is held until the triage run ends and the archive verifies.

<!-- fr:journal kind=finding scope=spec id=s1 created=2026-11-08T21:48:23+00:00 state=open review_scope=in -->
### s1 · finding [open] (reviewer: in scope) · layer-18-persistent-agent-degraded also watches vk_issue_bridge, so R1 does not stop the alarm

alert-rules-cm.yaml:840. The rule keeps firing after the three named rules go, and Test Plan 2 would not notice.

<!-- fr:journal kind=finding scope=spec id=s2 created=2026-11-08T21:48:23+00:00 state=open review_scope=in -->
### s2 · finding [open] (reviewer: in scope) · test_agent_images_bump_coverage.py fails once the two pod images leave AGENT_IMAGES

The local twin of the workflow coverage check also needs an explicit exclusion until Phase 2.

<!-- fr:journal kind=finding scope=spec id=s3 created=2026-11-08T21:48:23+00:00 state=open review_scope=in -->
### s3 · finding [open] (reviewer: in scope) · R7 needs a merge order, Frank PR first with no open bump PRs

An agent-images merge first dispatches the old workflow, which rewrites the kali pin and rolls the Recreate pod.

<!-- fr:journal kind=finding scope=spec id=s4 created=2026-11-08T21:48:23+00:00 state=open review_scope=in -->
### s4 · finding [open] (reviewer: in scope) · OLD_AI_SHA is read from the kali pin that R5 freezes

agent-images-bump.yml:42-43. Later bump bodies relist shipped PRs, and Phase 2 silently loses the baseline.

<!-- fr:journal kind=finding scope=spec id=s5 created=2026-11-08T21:48:23+00:00 state=open review_scope=in -->
### s5 · finding [open] (reviewer: in scope) · VKR_SHA runs through three steps, the branch name, commit message and PR title

There is no vk-remote step to delete, and test_render_bump_body.py asserts the vk-remote line.

<!-- fr:journal kind=finding scope=spec id=s6 created=2026-11-08T21:48:23+00:00 state=open review_scope=in -->
### s6 · finding [open] (reviewer: in scope) · R7 has no pre-merge baseline, and the generator move makes secure-agent-pod sync

An auto-sync on a stale Application could apply drift and roll the pod. Nothing records the before values.

<!-- fr:journal kind=finding scope=spec id=s7 created=2026-11-08T21:48:23+00:00 state=open review_scope=in -->
### s7 · finding [open] (reviewer: in scope) · Test Plan row 3 passes even if the manual IngressRoute delete was skipped

Authentik, homepage and dump evidence were also untested.

<!-- fr:journal kind=finding scope=spec id=s8 created=2026-11-08T21:48:23+00:00 state=open review_scope=in -->
### s8 · finding [open] (reviewer: in scope) · R1 leaves the Grafana restart unowned

Provisioning is read at boot, so the restart must be a step.

<!-- fr:journal kind=finding scope=spec id=s9 created=2026-11-08T21:48:23+00:00 state=open review_scope=in -->
### s9 · finding [open] (reviewer: in scope) · R8's named files are incomplete, and frank-infrastructure.md does not fit its criterion

Checklist, repo-workflows, ci-forge-tiers, stale comments and retired manual ops were missing.

<!-- fr:journal kind=finding scope=spec id=s10 created=2026-11-08T21:48:23+00:00 state=open review_scope=in -->
### s10 · finding [open] (reviewer: in scope) · Two acceptance rows span both phases, so Phase 1 cannot close them

vk-images-retired and no-vk-references-remain each mix Phase 1 and Phase 2 requirements.

<!-- fr:journal kind=finding scope=spec id=s11 created=2026-11-08T21:48:23+00:00 state=open review_scope=in -->
### s11 · finding [open] (reviewer: in scope) · R11 omits layer-18-persistent-agent-degraded, so removing the pod would raise an alert

Phase 2. The rule aggregates the same pod heartbeats.

<!-- fr:journal kind=finding scope=spec id=s12 created=2026-11-08T21:48:23+00:00 state=open review_scope=in -->
### s12 · finding [open] (reviewer: in scope) · chorebot's config.yaml is promised to the archive but missing from the archive list

Phase 2. The only copy would be lost with the PVC.

<!-- fr:journal kind=finding scope=spec id=s13 created=2026-11-08T21:48:23+00:00 state=open review_scope=in -->
### s13 · finding [open] (reviewer: in scope) · The SOPS copy of github-app-derio-key for secure-agent-pod is not in the cleanup list

Phase 2. secrets/github-app/github-app-derio-key.yaml targets the removed namespace.

<!-- fr:journal kind=review scope=spec id=spec-review-1 created=2026-11-08T21:48:23+00:00 -->
### spec-review-1 · review · independent spec review: 13 findings, all in scope

fr-spec-reviewer checked the spec against the operator decisions and the codebase. All named Frank paths exist, the generator move and cascades hold, and no operator decision is contradicted. agent-images and vibe-kanban contents and live measurements could not be verified from the workspace.

<!-- fr:journal kind=finding scope=spec id=s1-resolved created=2026-11-08T21:48:23+00:00 state=fixed resolves=s1 -->
### s1-resolved · finding [fixed] · resolves s1: layer-18-persistent-agent-degraded also watches vk_issue_bridge, so R1 does not stop the alarm

R1, Alarms first and Test Plan 2 now cover the Layer 18 clause and its retained series.

<!-- fr:journal kind=finding scope=spec id=s2-resolved created=2026-11-08T21:48:23+00:00 state=fixed resolves=s2 -->
### s2-resolved · finding [fixed] · resolves s2: test_agent_images_bump_coverage.py fails once the two pod images leave AGENT_IMAGES

Images (R5) names the test and its explicit exclusion.

<!-- fr:journal kind=finding scope=spec id=s3-resolved created=2026-11-08T21:48:23+00:00 state=fixed resolves=s3 -->
### s3-resolved · finding [fixed] · resolves s3: R7 needs a merge order, Frank PR first with no open bump PRs

Shipping shape sets the merge order, and Test Plan 0 checks no bump PR is open.

<!-- fr:journal kind=finding scope=spec id=s4-resolved created=2026-11-08T21:48:23+00:00 state=fixed resolves=s4 -->
### s4-resolved · finding [fixed] · resolves s4: OLD_AI_SHA is read from the kali pin that R5 freezes

Images (R5) moves the baseline to the multi-agent-shell pin.

<!-- fr:journal kind=finding scope=spec id=s5-resolved created=2026-11-08T21:48:23+00:00 state=fixed resolves=s5 -->
### s5-resolved · finding [fixed] · resolves s5: VKR_SHA runs through three steps, the branch name, commit message and PR title

Images (R5) lists every VKR_SHA site and the test.

<!-- fr:journal kind=finding scope=spec id=s6-resolved created=2026-11-08T21:48:23+00:00 state=fixed resolves=s6 -->
### s6-resolved · finding [fixed] · resolves s6: R7 has no pre-merge baseline, and the generator move makes secure-agent-pod sync

Pod untouched (R7) adds a baseline and argocd app diff; R7 states a vk-local-only restart is tolerated.

<!-- fr:journal kind=finding scope=spec id=s7-resolved created=2026-11-08T21:48:23+00:00 state=fixed resolves=s7 -->
### s7-resolved · finding [fixed] · resolves s7: Test Plan row 3 passes even if the manual IngressRoute delete was skipped

Test Plan 0 and 3 assert the objects directly.

<!-- fr:journal kind=finding scope=spec id=s8-resolved created=2026-11-08T21:48:23+00:00 state=fixed resolves=s8 -->
### s8-resolved · finding [fixed] · resolves s8: R1 leaves the Grafana restart unowned

Alarms first owns the restart as a manual operation.

<!-- fr:journal kind=finding scope=spec id=s9-resolved created=2026-11-08T21:48:23+00:00 state=fixed resolves=s9 -->
### s9-resolved · finding [fixed] · resolves s9: R8's named files are incomplete, and frank-infrastructure.md does not fit its criterion

Tooling and docs (R8) names the files and moves frank-infrastructure.md to Phase 2.

<!-- fr:journal kind=finding scope=spec id=s10-resolved created=2026-11-08T21:48:23+00:00 state=fixed resolves=s10 -->
### s10-resolved · finding [fixed] · resolves s10: Two acceptance rows span both phases, so Phase 1 cannot close them

Rows split into kali-image-retired (R12) and vk-tooling-retired (R8).

<!-- fr:journal kind=finding scope=spec id=s11-resolved created=2026-11-08T21:48:23+00:00 state=fixed resolves=s11 -->
### s11-resolved · finding [fixed] · resolves s11: R11 omits layer-18-persistent-agent-degraded, so removing the pod would raise an alert

Observability (R11) tombstones the Layer 18 rule and deletes retained series.

<!-- fr:journal kind=finding scope=spec id=s12-resolved created=2026-11-08T21:48:23+00:00 state=fixed resolves=s12 -->
### s12-resolved · finding [fixed] · resolves s12: chorebot's config.yaml is promised to the archive but missing from the archive list

Archive and gate (R9) lists config.yaml, and Test Plan 7 confirms it.

<!-- fr:journal kind=finding scope=spec id=s13-resolved created=2026-11-08T21:48:23+00:00 state=fixed resolves=s13 -->
### s13-resolved · finding [fixed] · resolves s13: The SOPS copy of github-app-derio-key for secure-agent-pod is not in the cleanup list

Images and leftovers (R13) deletes the file after confirming the Tekton copy.

<!-- fr:journal kind=decision scope=spec id=exit-baseline created=2026-11-08T21:48:24+00:00 -->
### exit-baseline · decision · exit when spec-review resolved

The exit when spec-review resolved; `fr verification set` and `deliver` compare against it.

```yaml
row_gates:
  gitops-push-token-continuity: devops
  kali-image-retired: devops
  no-vk-references-remain: none
  pod-removal-silent: devops
  pod-removed-after-archive: devops
  pod-undisturbed-phase-1: devops
  vk-alerts-retired: devops
  vk-images-retired: devops
  vk-mirror-retired: devops
  vk-posts-superseded: none
  vk-remote-removed: devops
  vk-surface-removed: devops
  vk-tooling-retired: none
row_kinds:
  gitops-push-token-continuity: live
  kali-image-retired: live
  no-vk-references-remain: none
  pod-removal-silent: live
  pod-removed-after-archive: live
  pod-undisturbed-phase-1: live
  vk-alerts-retired: live
  vk-images-retired: live
  vk-mirror-retired: live
  vk-posts-superseded: none
  vk-remote-removed: live
  vk-surface-removed: live
  vk-tooling-retired: none
run_gate: devops
run_kind: live
```

<!-- fr:journal kind=decision scope=spec id=d-phase1-only created=2026-11-08T22:43:17+00:00 gate=owner narrows=derio-net/frank#950 -->
### d-phase1-only · decision · This run ships Phase 1 only; Phase 2 is tracked in #950

Operator's words, in chat rather than an answered question: 'approved. Run it with fr-goal (only Phase 1)'. R9-R15 ship in a later PR, once the triage run on the pod has ended.

<!-- fr:journal kind=decision scope=spec id=d-phase1-only-filed created=2026-11-08T22:51:00+00:00 gate=owner narrows=derio-net/frank#950 remainder_tracked_by=https://github.com/derio-net/frank/issues/951 -->
### d-phase1-only-filed · decision [filed → https://github.com/derio-net/frank/issues/951] · files d-phase1-only: This run ships Phase 1 only; Phase 2 is tracked in #950

Filed the rest of `d-phase1-only` at deliver as https://github.com/derio-net/frank/issues/951.

<!-- fr:journal kind=discovery scope=spec id=phase2-operator-brief created=2026-11-12T12:28:40+00:00 input=true -->
### phase2-operator-brief · discovery · Operator brief for Phase 2 (take secure-agent-pod down)

Run Phase 2 (R9-R15, checks 7-10) of the existing retire-vk spec as its own plan and PR.
Cluster-destructive steps are a MANUAL phase, never agentic. Security driver: frank#912
must land before frank#913's upgrade sessions hold credentials, so the
`secure-agent-pod-cluster-admin` ClusterRoleBinding is deleted explicitly and asserted
NotFound (CRBs survive a namespace delete), plus
`kubectl auth can-i get secrets -n upgrade-sessions --as=system:serviceaccount:secure-agent-pod:agent-sa` = no.
Do not touch PR #913 or its worktree; do not merge Frank PRs. Whichever of #913 / this PR
merges second drops the vk-local and secure-agent-kali entries from
scripts/tests/fixtures/life/pin-exceptions.yaml. Phase 1 leftovers belong to a sibling session.

<!-- fr:journal kind=decision scope=spec id=phase2-r9-gate-prep-only created=2026-11-12T12:28:40+00:00 decided_by=operator -->
### phase2-r9-gate-prep-only · decision · Triage run still running - this run is planning and prep only

decider: operator. Asked 2026-11-12: the triage run on the pod has NOT ended. This run
therefore delivers the plan, a draft removal PR, the agent-images PR and the archive
script, and makes no live change to the pod. Archive and teardown are a back-loaded
manual phase the operator runs after confirming the triage run ended (R9).

<!-- fr:journal kind=decision scope=spec id=phase2-archive-destination created=2026-11-12T12:28:40+00:00 decided_by=operator -->
### phase2-archive-destination · decision · Archive goes to ~/Archives/secure-agent-pod-2026-11 on the operator's Mac

decider: operator. A new local directory, created 0700, outside every git repo and
outside synced storage, because chorebot's config.yaml may hold tokens.

<!-- fr:journal kind=decision scope=spec id=phase2-own-plan-folder created=2026-11-12T12:28:40+00:00 decided_by=operator -->
### phase2-own-plan-folder · decision · Phase 2 gets its own plan folder against the same spec

decider: agent. The spec ships Phase 2 as a second Frank PR cut from main after Phase 1,
and the Phase 1 plan folder's manual phase is still open in another session, so Phase 2
is a new plan (2026-11-12--agents--retire-secure-agent-pod) rather than extra phases on
the Phase 1 plan. The spec's verification (strategy live, gate devops) is unchanged.
