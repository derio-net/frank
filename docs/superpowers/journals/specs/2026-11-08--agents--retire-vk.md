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

<!-- fr:journal kind=review scope=spec id=spec-review-phase2 created=2026-11-12T12:34:59+00:00 -->
### spec-review-phase2 · review · independent spec review (Phase 2, R9-R15): 11 findings, 10 in scope, 1 out

Reviewed only Phase 2 of the retire-vk spec on branch feat/retire-vk-phase2, read-only.
Raised sr2-f1..sr2-f11. The heaviest are sr2-f1 (ClusterRoleBinding explicit delete and
`auth can-i` absent), sr2-f3 (alerts can page on the way down, and check 10 cannot see it),
sr2-f4 (`## Test Plan` still holds Phase 1 rows) and sr2-f7 (an existing tripwire breaks and
is not named). No operator decision is contradicted; three were omitted (sr2-f1, sr2-f5,
sr2-f6, sr2-f4).

Not verifiable from the tree: the `root` Application is not in git (its `prune: true` rests
on docs/runbooks/frank-gotchas/argocd.md:362-366); agent-images contents, live cluster
state; scripts/tests/fixtures/life/pin-exceptions.yaml is NOT on this branch.

Verified with file:line: the Application finalizer and syncPolicy
(apps/root/templates/secure-agent-pod.yaml:16-17, 27-33); the Namespace is a raw manifest in
root's chart (ns-secure-agent-pod.yaml:1-8); the ClusterRoleBinding
(apps/secure-agent-pod/manifests/serviceaccount.yaml:7-18); the PVC, three Services and
vmpodscrape; the five R11 rule uids (alert-rules-cm.yaml:31, 87, 143, 254, 657) and the
`deleteRules` convention (:9-16); the dashboard ConfigMap and its two mounts
(apps/victoria-metrics/values.yaml:177-181, 200-202); dashboard panels (dashboard-cm.yaml:54,
104, 199); the frozen exclusion (.github/workflows/agent-images-bump.yml:136-138) and its
local twin (test_agent_images_bump_coverage.py:22-25, 56-60); the three named tests; the
existing tripwire scripts/tests/test_vk_retired.py; the secrets files; the tekton-owned
generator; no IngressRoute, Authentik provider or homepage tile for the pod; all 15 R14
bundles and building/33-hermes-shell; the `> **Update 2026-10.**` precedent; roadmap entries
(blog/data/roadmap.yaml:148, 218, 242, 280).

<!-- fr:journal kind=finding scope=spec id=sr2-f1 created=2026-11-12T12:34:59+00:00 state=open review_scope=in -->
### sr2-f1 · finding [open] (reviewer: in scope) · The ClusterRoleBinding is left to the cascade; no explicit delete, no auth can-i assertion

Evidence: journal `phase2-operator-brief`; spec "Removal (R10)" and check 9;
apps/secure-agent-pod/manifests/serviceaccount.yaml:7-18; apps/root/templates/secure-agent-pod.yaml:16-17, 27-29.
The CRB is cluster-scoped, so only the Application finalizer removes it. A stripped finalizer
leaves it with a dangling subject. Fix: explicit delete after the Application is NotFound
(selfHeal recreates it before), keep check 9, add the `auth can-i` check, state the
destructive steps are a [manual] phase and the operator performs the merge.

<!-- fr:journal kind=finding scope=spec id=sr2-f2 created=2026-11-12T12:34:59+00:00 state=open review_scope=in -->
### sr2-f2 · finding [open] (reviewer: in scope) · No pre-removal gate that github-app-derio has left the secure-agent-pod Application

Evidence: spec trap 1; Phase 1 row 4; apps/tekton/manifests/clustergenerator-github-app-derio.yaml:3-6.
Git has the generator under tekton, but live ownership was proven only by Phase 1 row 4, whose
manual phase is still open. If the live object still carries the secure-agent-pod tracking id,
the finalizer deletes it. Fix: a pre-merge manual check of tracking id and `.status.resources`.

<!-- fr:journal kind=finding scope=spec id=sr2-f3 created=2026-11-12T12:34:59+00:00 state=open review_scope=in -->
### sr2-f3 · finding [open] (reviewer: in scope) · 'Same PR' does not stop pages on the way down, and check 10 cannot detect a failed tombstone

Evidence: alert-rules-cm.yaml:98 with :670-672 (thresholds 600s / 10800s / 93600s);
apps/root/values.yaml:9-13. Grafana reads provisioning at boot, so stored rules keep
evaluating the retained series; session_manager goes stale ~15 min after the pod dies. Check
10's one-hour window misses the 3h and 26h rules. grafana-alerting does not prune, so the
live dashboard ConfigMap survives. Fix: order the manual phase (silence, merge, restart,
delete series), assert through the Grafana API, assert series gone, delete and assert the
dashboard ConfigMap, close frank-ops#18.

<!-- fr:journal kind=finding scope=spec id=sr2-f4 created=2026-11-12T12:34:59+00:00 state=open review_scope=in -->
### sr2-f4 · finding [open] (reviewer: in scope) · `## Test Plan` holds Phase 1 rows; the Phase 2 checks sit under a heading fr does not read

Evidence: spec Test Plan ("Phase 1 only"), `## Phase 2 checks (later PR)`, Implementation
Plans table; journal `phase2-own-plan-folder`. Fix: make the Phase 2 checks the Test Plan,
keep Phase 1 rows as a record, add the Phase 2 plan row, and say the agent-images PR carries
R12's build half.

<!-- fr:journal kind=finding scope=spec id=sr2-f5 created=2026-11-12T12:34:59+00:00 state=open review_scope=in -->
### sr2-f5 · finding [open] (reviewer: in scope) · The pin-exceptions coordination with PR #913 is not in the spec

Evidence: journal `phase2-operator-brief`; `scripts/tests/fixtures/life/` has no files on
this branch. Fix: a conditional step in "Images and leftovers" and a tripwire assertion once
the file exists.

<!-- fr:journal kind=finding scope=spec id=sr2-f6 created=2026-11-12T12:34:59+00:00 state=open review_scope=in -->
### sr2-f6 · finding [open] (reviewer: in scope) · The archive destination decision is not reflected

Evidence: journal `phase2-archive-destination`; spec R9 design text and check 7. Fix: name
`~/Archives/secure-agent-pod-2026-11`, 0700, and say where Phase 1's dump stays
(docs/runbooks/manual-operations.yaml:2728).

<!-- fr:journal kind=finding scope=spec id=sr2-f7 created=2026-11-12T12:34:59+00:00 state=open review_scope=in -->
### sr2-f7 · finding [open] (reviewer: in scope) · The existing tripwire test_vk_retired.py is not named; it breaks on removal, and the tripwire is narrower than R13

Evidence: scripts/tests/test_vk_retired.py:24-26, 188-195;
scripts/tests/test_agent_images_bump_coverage.py:22-25, 56-60.
`test_pod_deployment_still_pins_both_containers` raises once the directory is deleted. The
local twin of the exclusion is unnamed. R13 covers more than `apps/`. Fix: extend the
existing file, drop the pod exemptions, assert absence, widen the scan.

<!-- fr:journal kind=finding scope=spec id=sr2-f8 created=2026-11-12T12:34:59+00:00 state=open review_scope=in -->
### sr2-f8 · finding [open] (reviewer: in scope) · R12, part of R10 and the SOPS-key precondition have no check in rows 7-10

Evidence: row `kali-image-retired`; checks 7-10; R10. Fix: add a bump-run check, an
Application NotFound check, and a fingerprint comparison of the tekton key before the delete.

<!-- fr:journal kind=finding scope=spec id=sr2-f9 created=2026-11-12T12:34:59+00:00 state=open review_scope=in -->
### sr2-f9 · finding [open] (reviewer: in scope) · Consumers and pointers the spec does not name, including runbook ops that source the file being deleted

Functional: docs/runbooks/manual-operations.yaml:2104 builds the tekton key from the file
being deleted; :1894-1903, :93-152, :1882-1908 are pod ops generated from plan blocks.
Stale pointers: scripts/hooks/session-start.sh:4;
apps/argocd-extras/manifests/externalsecret-repo-runs-fr.yaml:10;
apps/tekton/manifests/clustergenerator-github-app-derio.yaml:20, :27;
clustergenerator-stoa-github-app.yaml:9; apps/paperclip/manifests/deployment.yaml:30;
apps/hermes-agent-shell/manifests/deployment.yaml:24, service.yaml:2-5,
configmap-byok-env.yaml:29; apps/root/templates/hermes-agent-shell.yaml:10,
ns-hermes-agent-shell.yaml:6; secrets/hermes-agent-shell/README.md:10, :17;
secrets/ruflo/README.md:7, :11; patches/phase04-gpu/403-gpu1-pcie-aspm.yaml:27;
scripts/tests/test_staging_gate_manifests.py:218; test_etcd_scrape.py:1210;
test_hermes_ssh_byok_env_snapshot.py:24; docs/runbooks/frank-gotchas/networking.md:64.
Fix: name the runbook ops and plan blocks; state one rule for comment-level mentions.

<!-- fr:journal kind=finding scope=spec id=sr2-f10 created=2026-11-12T12:34:59+00:00 state=open review_scope=in -->
### sr2-f10 · finding [open] (reviewer: in scope) · The R14 table misses posts that mention the pod, including the Layer 18 building post

Evidence: blog/content/docs/building/18-persistent-agent/index.md (5 hits);
building/24-in-cluster-ingress (1); papers/10-self-hosted-inference (1); paper 17
data/vendors.yaml and dossier. Fix: add them to the table, decide on paper 17's data and
dossier, and add a test for the update line.

<!-- fr:journal kind=finding scope=spec id=sr2-f11 created=2026-11-12T12:34:59+00:00 state=open review_scope=out -->
### sr2-f11 · finding [open] (reviewer: out of scope) · The root Application's prune setting is not in git, and two docs disagree about it

Evidence: apps/root/values.yaml:9-13; docs/runbooks/frank-gotchas/argocd.md:362-366.
Pre-existing documentation ambiguity; Phase 1 relied on the same cascade.

<!-- fr:journal kind=finding scope=spec id=sr2-f1-resolved created=2026-11-12T12:34:59+00:00 state=fixed resolves=sr2-f1 -->
### sr2-f1-resolved · finding [fixed] · resolves sr2-f1: The ClusterRoleBinding is left to the cascade; no explicit delete, no auth can-i assertion

Spec gains 'The cluster-admin binding (R10, frank#912)': explicit delete after the Application is NotFound, NotFound assertion, the auth can-i check (Test Plan row 9), and the Shipping shape now says every live change is a [manual] phase with the operator performing the merge.

<!-- fr:journal kind=finding scope=spec id=sr2-f2-resolved created=2026-11-12T12:34:59+00:00 state=fixed resolves=sr2-f2 -->
### sr2-f2-resolved · finding [fixed] · resolves sr2-f2: No pre-removal gate that github-app-derio has left the secure-agent-pod Application

Removal section adds three pre-merge gates; the first is the generator's tekton-extras tracking id and its absence from the Application's status.resources. Test Plan row 7 carries it.

<!-- fr:journal kind=finding scope=spec id=sr2-f3-resolved created=2026-11-12T12:34:59+00:00 state=fixed resolves=sr2-f3 -->
### sr2-f3-resolved · finding [fixed] · resolves sr2-f3: 'Same PR' does not stop pages on the way down, and check 10 cannot detect a failed tombstone

Observability section now orders the manual phase (silence, merge, confirm ConfigMap, restart Grafana, API assertion, delete series, delete silence), deletes and asserts the dashboard ConfigMap, and closes frank-ops#18. Test Plan row 10 asserts on the Grafana API and the series, not on a one-hour window alone.

<!-- fr:journal kind=finding scope=spec id=sr2-f4-resolved created=2026-11-12T12:34:59+00:00 state=fixed resolves=sr2-f4 -->
### sr2-f4-resolved · finding [fixed] · resolves sr2-f4: `## Test Plan` holds Phase 1 rows; the Phase 2 checks sit under a heading fr does not read

Phase 1 rows moved under '## Phase 1 checks (shipped)'; '## Test Plan' now holds rows 7-11; the Phase 2 plan row is in Implementation Plans; Shipping shape names the agent-images PR for R12.

<!-- fr:journal kind=finding scope=spec id=sr2-f5-resolved created=2026-11-12T12:34:59+00:00 state=fixed resolves=sr2-f5 -->
### sr2-f5-resolved · finding [fixed] · resolves sr2-f5: The pin-exceptions coordination with PR #913 is not in the spec

Images and leftovers states the pin-exceptions rule with frank#913 as a conditional step plus tripwire assertion.

<!-- fr:journal kind=finding scope=spec id=sr2-f6-resolved created=2026-11-12T12:34:59+00:00 state=fixed resolves=sr2-f6 -->
### sr2-f6-resolved · finding [fixed] · resolves sr2-f6: The archive destination decision is not reflected

R9 design text and Test Plan row 7 name ~/Archives/secure-agent-pod-2026-11 at 0700, the refusal conditions, and that Phase 1's dump stays in $HOME/frank-retire-vk-archive/.

<!-- fr:journal kind=finding scope=spec id=sr2-f7-resolved created=2026-11-12T12:34:59+00:00 state=fixed resolves=sr2-f7 -->
### sr2-f7-resolved · finding [fixed] · resolves sr2-f7: The existing tripwire test_vk_retired.py is not named; it breaks on removal, and the tripwire is narrower than R13

Spec now extends test_vk_retired.py, drops the pod exemptions, names the local twin of the exclusion, asserts absence, and widens the scan to apps/, secrets/ and .github/.

<!-- fr:journal kind=finding scope=spec id=sr2-f8-resolved created=2026-11-12T12:34:59+00:00 state=fixed resolves=sr2-f8 -->
### sr2-f8-resolved · finding [fixed] · resolves sr2-f8: R12, part of R10 and the SOPS-key precondition have no check in rows 7-10

Test Plan row 8 asserts the Application NotFound, row 11 is the bump run, and the fingerprint comparison is the second pre-merge gate.

<!-- fr:journal kind=finding scope=spec id=sr2-f9-resolved created=2026-11-12T12:34:59+00:00 state=fixed resolves=sr2-f9 -->
### sr2-f9-resolved · finding [fixed] · resolves sr2-f9: Consumers and pointers the spec does not name, including runbook ops that source the file being deleted

Spec lists every pointer and sets one rule: fixed, not exempted. Pod manual operations are retired in their plan blocks and resynced; the Tekton-key operation is repointed at github-app-derio-key-tekton.yaml before the source file is deleted.

<!-- fr:journal kind=finding scope=spec id=sr2-f10-resolved created=2026-11-12T12:34:59+00:00 state=fixed resolves=sr2-f10 -->
### sr2-f10-resolved · finding [fixed] · resolves sr2-f10: The R14 table misses posts that mention the pod, including the Layer 18 building post

R14 table adds building 18-persistent-agent, 24-in-cluster-ingress and paper 10; paper 17's vendors.yaml and dossier are declared left as the research record; a test asserts the update line.

<!-- fr:journal kind=finding scope=spec id=sr2-f11-resolved created=2026-11-12T12:34:59+00:00 state=open resolves=sr2-f11 out_of_scope=true -->
### sr2-f11-resolved · finding [out-of-scope] · resolves sr2-f11: The root Application's prune setting is not in git, and two docs disagree about it

The values.yaml comment and argocd.md disagree independently of this change, and Phase 1 relied on the same cascade. This change only reads the live value as a pre-merge gate (added to the spec); correcting the comment is a separate change.

<!-- fr:journal kind=decision scope=spec id=phase2-agent-images-direct-pr created=2026-11-12T12:39:58+00:00 -->
### phase2-agent-images-direct-pr · decision · agent-images kali removal ships as a direct PR, not its own fr plan

decider: agent. R12's build half is one matrix leg and one directory in derio-net/agent-images, mirroring Phase 1's agent-images#176. It is delivered as a plain PR stacked after #176 and merged by the operator after the Frank PR, with Test Plan row 11 as its proof. A second plan, run and review loop in that repo would cost more than the change.

<!-- fr:journal kind=decision scope=spec id=phase2-archive-uncommitted-state created=2026-11-12T13:47:28+00:00 -->
### phase2-archive-uncommitted-state · decision · The archive also preserves uncommitted clone state

decider: orchestrator session (VK retirement workspace), relayed 2026-11-12 — not the operator. Bundles carry committed refs only; dirty worktrees, untracked files and stash entries would be lost with the PVC. Additive and read-only, so adopted without an operator round.

<!-- fr:journal kind=finding scope=spec id=sr2-f11-resolved-2 created=2026-11-12T14:14:11+00:00 state=open resolves=sr2-f11 tracked_by=https://github.com/derio-net/frank/issues/956 -->
### sr2-f11-resolved-2 · finding [deferred → https://github.com/derio-net/frank/issues/956] · resolves sr2-f11: The root Application's prune setting is not in git, and two docs disagree about it

Filed at deliver as https://github.com/derio-net/frank/issues/956.

<!-- fr:journal kind=decision scope=spec id=phase2-archive-claude-home created=2026-11-12T22:15:32+00:00 -->
### phase2-archive-claude-home · decision · The archive includes ~/.claude: transcripts, CLAUDE.md, settings, memory

decider: operator, relayed by the orchestrator session on 2026-11-12 (this session did not hear it directly). /home/claude/.claude goes into the home tarball, excluding credentials (.credentials.json and other token or auth files by name) and pure caches (statsig, shell-snapshots, cache dirs, node_modules). Exclusions are listed in the usage text and EXCLUDED.txt, and verify's credential scan covers it.
