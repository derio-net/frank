# Retire VibeKanban and secure-agent-pod

**Date:** 2026-11-08
**Layer:** agents
**Status:** Draft

## Context

VibeKanban (VK) is being retired from Frank, along with the pod that hosts its
local half. The dispatch bridge cron on the pod was already commented out on
2026-11-08, so `VK Issue Bridge Stale` has been firing since 17:23 UTC that day.

VK spans two workloads and two other repos:

| Where | What |
|---|---|
| `apps/vk-remote` (namespace `agents`) | `vk-remote` with relay sidecar, `electric`, `postgres-vk` (1Gi PVC, 31 MB database) |
| `apps/secure-agent-pod` (namespace `secure-agent-pod`) | `kali` and `vk-local` containers, 50Gi `agent-home` PVC, LoadBalancers .215, .218, .219, cluster-admin `agent-sa` |
| `derio-net/agent-images` | Builds `vk-local` and `secure-agent-kali`. Nothing builds FROM either |
| `derio-net/vibe-kanban` | Builds `vk-remote` and `vibe-kanban-build`. No open PRs. Frank mirrors it into Gitea |

### What is on the pod (measured 2026-11-08)

The pod is not idle, but nothing on it needs to survive:

- **Operator's triage run:** an interactive `claude` under `herdr` in
  `orgs/derio-net/triage-state`. This is the temporary use that Phase 2 waits for.
- **`claude remote-control --name willikins`:** logs report `Connected`, but the
  operator does not see it in the app and does not use it. The cause was not
  investigated, because it is being retired.
- **Crons:** `session-manager` (keeps that session alive), `audit-digest` (audits
  only this pod; nearly every daily archive since mid-June is empty), `rotate-logs`,
  `claude update`, a `willikins` pull (checkout is 117 commits behind).
- **chorebot:** sends paused since 2026-08-06, still polling Telegram every 10 s
  and running `materialize-week` and `mark-missed`. Data is in Notion and code is
  in `derio-net/willikins`.

Of the 37G home, about 33G is regenerable cache. About 150M may be the only copy:
`interviews/` (19 files, newest 2026-11-02) and `orgs/`. The clones also hold
local-only branches (99 commits in `willikins`, 28 in `frank`, 1 in `super-fr`).
Those sampled were mostly old `vk/*` branches, but not all of them were checked.

### Traps found during the inventory

1. **The `github-app-derio` ClusterGenerator is owned by the `secure-agent-pod`
   Application but consumed elsewhere.** `tekton-pipelines/frank-gitops-push` uses
   it, and `cnc-promotion` and staging-gate depend on that Secret. Removing the
   Application would cascade to the generator. The ExternalSecret has
   `deletionPolicy: Retain`, so the old Secret stays in place while its token
   expires about an hour later, with everything still reporting green.
2. **`vk-local` cannot leave the pod without rolling it.** The Deployment is
   `Recreate`, so editing it ends the operator's running session.
3. **An agent-images bump would roll the pod too,** because `agent-images-bump.yml`
   rewrites both pins.
4. **The bump workflow's coverage check rejects un-bumped pins.** It fails on any
   40-hex `ghcr.io/derio-net/*` pin in `apps/` that is not at the new SHA and is
   not in `SKIPPED`, so dropping the images from `AGENT_IMAGES` alone breaks it.
5. **Deleting an IngressRoute from git removes nothing.** `traefik-extras` runs
   `prune: false`, so the live route needs a manual delete.
6. **Removing a file-provisioned Grafana rule does not remove the stored rule.**
   It needs a `deleteRules` tombstone.

## Requirements

Phase 1: remove the dependencies, alarms and images, without touching the pod.

R1. The VK alert rules `vk-bridge-stale`, `vk-bridge-failures` and `vk-executor-pool-wedged` no longer exist in Grafana, `layer-18-persistent-agent-degraded` no longer watches `vk_issue_bridge`, and none of them can fire because of VK.
R2. The `vk-remote` stack (workloads, Application, `agents` namespace, 1Gi PVC) is gone from the cluster, and a dump of its database was verified before removal.
R3. Nothing still advertises VK: `vk.cluster.derio.net` has no route, Authentik no provider or application, and the homepage no tile.
R4. Frank no longer mirrors or budgets `derio-net/vibe-kanban`, and that repo is archived on GitHub.
R5. `agent-images` no longer builds `vk-local`, Frank's bump workflow no longer touches `vk-remote`, `vk-local` or `secure-agent-kali`, and the bump keeps succeeding for every remaining image.
R6. `github-app-derio` belongs to a Tekton-owned Application, and `frank-gitops-push` keeps minting tokens throughout.
R7. Phase 1 does not replace the secure-agent-pod or restart its `kali` container, so a session running there survives. A restart of the `vk-local` container alone does not break this requirement, because it does not touch the session.
R8. VK-only tooling, tests and docs that do not reference the live pod are removed or marked historical.

Phase 2: take the pod down, once the triage run has ended.

R9. Phase 2 is not merged until the operator confirms the triage run has ended and an archive of the files worth keeping has been verified on the operator's Mac.
R10. The `secure-agent-pod` Application, namespace, 50Gi PVC, three LoadBalancers and `agent-sa` cluster-admin binding are gone from the cluster.
R11. No alert, dashboard or scrape depends on the pod, and the pod's removal raises no alert.
R12. `agent-images` no longer builds `secure-agent-kali`.
R13. No manifest, secret, test or client config in Frank still expects the pod, and the operator's leftover manual steps are recorded.
R14. Blog posts about VK and the pod are marked superseded and stay published, and the roadmap reflects the retirement.
R15. chorebot and the other pod crons stop with the pod and are not migrated. The spec records how to revive chorebot.

## Design

### Shipping shape

Two Frank PRs, plus one `agent-images` PR per phase. Phase 1 merges when ready.
Frank's Phase 1 PR merges BEFORE the `agent-images` PR, and any open
`bump/agent-images-*` PR is closed first. Otherwise a dispatch runs the old workflow
from Frank `main`, which still rewrites the `secure-agent-kali` pin, and merging that
bump rolls the `Recreate` pod. Merging `agent-images` afterwards also supplies the
bump run Test Plan row 5 waits for. Phase 2 stays a draft until R9 is met, and its branch is cut from `main` after
Phase 1 merges. Requirements R9-R15 are implemented in that second Frank PR, except
the image build half of R12, which is the Phase 2 `agent-images` PR. Phase 2 has its
own plan folder, `2026-11-12--agents--retire-secure-agent-pod`. Everything that changes
the live cluster in Phase 2 is a `[manual]` phase: the operator performs the merge
that triggers the cascade and runs the sweep. No agentic phase touches the pod.

### Phase 1

**Alarms first (R1).** Delete the three rules and add `deleteRules` tombstones.
Remove the `vk_issue_bridge` clause from `layer-18-persistent-agent-degraded`, which
aggregates the same heartbeat and would otherwise keep firing. Delete the retained
`vk_issue_bridge` pushgateway series if it persists. Remove the dashboard selector
for that job, and `scripts/tests/test_vk_wedge_alert.py`, which guards a rule that no
longer exists. Grafana reads provisioning at boot, so a manual operation runs
`kubectl -n monitoring rollout restart deploy/victoria-metrics-grafana` once the
ConfigMap sync is confirmed, and verification is against the running Grafana, not
ArgoCD.

Two Grafana silences, created 2026-11-08 with the operator's approval, cover the gap
until merge and expire 2026-11-22: one for the three VK rules, one for the
`job=vk_issue_bridge` instance of the Layer 18 rule only. If the PR has not merged by
then, the alerts return.

**vk-remote (R2, R3).** As a pre-merge manual operation, `pg_dump` `postgres-vk`
to the operator's Mac and confirm the dump restores or lists cleanly. Then remove
`apps/root/templates/vk-remote.yaml` and `apps/vk-remote/`. Root's prune plus the
child finalizer cascades, and since the `agents` namespace and PVC are tracked by
that Application they go too. Remove `VK_REMOTE_*` from Infisical afterwards, once
the ExternalSecret is gone. For the public surface: remove the IngressRoute from
git and delete it by hand (trap 5), mark the Authentik provider and application
`state: absent`, and remove the homepage tile.

**Mirror and fork (R4).** Remove `vibe-kanban` from the mirror generator's
repository list, ci-budget generators and tiers, `ci-delivery-check`,
`mirror-reconcile`, both EventListener filters and `apps/tekton/webhooks.yaml`,
and update the `scripts/tests/` fixtures that name it. After merge, delete the
GitHub webhook and archive `derio-net/vibe-kanban`. The Gitea mirror repo stays
as read-only history. Archiving comes last, so nothing depending on the repo ever
sees it read-only while Frank is still configured for it.

**Images (R5).** In `agent-images-bump.yml`, `VKR_SHA` is not a separate step: it runs
through Resolve SHAs, Update manifests and Open PR, the branch name, the commit
message and the hard-coded PR title. Remove it from all of them, and keep the branch
name unique per agent-images SHA once its `-vkr-` suffix is gone; the existing guard skips a SHA whose PR is already open. Remove the two pod images from
`AGENT_IMAGES`, and add an explicit exclusion for `secure-agent-kali` and `vk-local`
to the coverage check (trap 4), with a comment saying Phase 2 removes it. The local
twin, `scripts/tests/test_agent_images_bump_coverage.py`, gets the same explicit
exclusion; no workflow comment may contain the literal image reference, which would
satisfy its regex by accident.

`OLD_AI_SHA` is read from the `secure-agent-kali` pin, which R5 freezes. Read it from
a pin that keeps moving, `multi-agent-shell` in
`apps/alert-agent/manifests/deployment.yaml`, or later bump PR bodies relist shipped
PRs and Phase 2 silently loses the baseline. Drop the `vk-remote` handling from
`scripts/render_bump_body.py` and `scripts/tests/test_render_bump_body.py`, and
refresh the stale coverage comment. In `agent-images`, remove the `vk-local` matrix
leg and directory. The `kali` image remains until Phase 2.

**Generator move (R6).** Move `clustergenerator-github-app.yaml` to
`apps/tekton/manifests/`, so `tekton-extras` owns it. ArgoCD then tracks it under
the new Application. The secure-agent-pod Application has no `prune`, so its copy
is not deleted when the file leaves its path. The object name is unchanged, so
`agent-github-token` in the pod's namespace keeps working until Phase 2.

**Pod untouched (R7).** Phase 1 does not edit
`apps/secure-agent-pod/manifests/deployment.yaml`. `vk-local` keeps running, idle,
until Phase 2. Its behaviour once the relay is gone is unmeasured; its liveness probe
is local `/api/health`, and a `vk-local`-only restart is tolerated by R7.

Leaving the file untouched does not prove no roll. The generator move is the one
Phase 1 change inside this Application's path, so it can trigger an auto-sync, and a
stale Application would then apply any existing drift. A pre-merge manual operation
therefore records the pod UID and container restart counts, and confirms
`argocd app diff secure-agent-pod` shows no Deployment change, with the Application's
Deployment resource reporting `Synced` as the scripted check.

**Tooling and docs (R8).** Remove `scripts/phase5-soak-daily.sh`. Update
`agents/skills/bump-image/SKILL.md`, `README.md`,
`agents/rules/plan-post-deploy-checklist.md` (its `vk.cluster.derio.net` example),
`agents/rules/repo-workflows.md` (its VK dispatch path), `docs/runbooks/ci-forge-tiers.md`,
and the now-stale comments and `agents` regex in
`apps/grafana-alerting/manifests/notification-policy-cm.yaml` and
`alert-rules-cm.yaml`. Mark retired VK manual operations, such as
`vibe-kanban-dispatch-pat`, in their plan blocks as well as the runbook, because the
runbook is generated from them. `agents/rules/frank-infrastructure.md` lists only the
live pod, so it waits for Phase 2. VK gotchas stay where they are with a
`HISTORICAL (retired 2026-11)` marker, following the Paperclip precedent.

### Phase 2

**Archive and gate (R9).** A script, run by the operator, confirms no interactive
session remains and writes a tarball to `~/Archives/secure-agent-pod-2026-11` on the
Mac (operator decision, 2026-11-12). The script creates that directory `0700` and
refuses a destination inside a git repository or with a looser mode. Phase 1's dump
and baseline stay where Phase 1 wrote them, `$HOME/frank-retire-vk-archive/`. The tarball contains `interviews/`,
`orgs/`, `.hermes`, the audit archive, the VK `db.v2.sqlite`,
`repos/willikins/scripts/chorebot/config.yaml`, `~/.claude/` (session transcripts under
`projects/`, `CLAUDE.md`, settings and memory; credentials and pure caches excluded,
operator decision 2026-11-12), and one self-contained `git bundle` per clone
covering every ref (no prerequisites, so a deleted or force-pushed upstream cannot break a restore). Credential files
(`credentials.json`, `server_ed25519_signing_key`, `.ssh`, `.gnupg`,
`.config/gh`, `.claude.json`) are excluded. chorebot's `config.yaml` is kept on
purpose despite possibly holding tokens, because it is not in git. The script prints a file count and
verifies the tarball and bundles. Regenerable caches are not archived.

Bundles hold committed work only, so the script also captures uncommitted state from
every clone and linked worktree: the `git status`, a binary patch of tracked changes
against `HEAD`, a tarball of untracked (not ignored) files under the same credential
excludes, and one patch per stash entry. Dirty clones are listed in `DIRTY.txt`, and
`verify` names them. The script writes nothing to the pod's home.

**Removal (R10).** Remove `apps/root/templates/secure-agent-pod.yaml`,
`ns-secure-agent-pod.yaml` and `apps/secure-agent-pod/`. The PVC, Services, RBAC
and SOPS-applied Secrets go through the cascade or the namespace. Evidence is on
the artifacts: the namespace and PV are gone, .215, .218 and .219 are free, and
the ClusterRoleBinding is gone. The namespace's `github-app-derio-key` copy goes
with it; `tekton-pipelines` has its own.

Three gates run before the merge, as manual steps. First, Phase 1's Test Plan row 4
has passed: the live `github-app-derio` ClusterGenerator carries a `tekton-extras`
tracking id and is absent from `application secure-agent-pod` `.status.resources`.
Otherwise the finalizer cascade deletes it (trap 1). Second, the live
`tekton-pipelines/github-app-derio-key` matches both
`secrets/github-app/github-app-derio-key-tekton.yaml` and the file being deleted,
compared by SHA-256 fingerprint and never printed. Third,
`kubectl -n argocd get application root -o jsonpath='{.spec.syncPolicy.automated}'`
shows `prune: true`, since the root Application is not defined in git.

**The cluster-admin binding (R10, frank#912).** `secure-agent-pod-cluster-admin`
grants `cluster-admin` to `secure-agent-pod:agent-sa`. It is cluster-scoped, so a
namespace delete does not remove it; only the Application finalizer does, and a
finalizer stripped to clear a `DeletionError` would leave it behind for any later
`agent-sa` to inherit. The sweep therefore runs
`kubectl delete clusterrolebinding secure-agent-pod-cluster-admin --ignore-not-found`
after the Application is NotFound (while the Application lives, `selfHeal` recreates
it), then asserts NotFound and that
`kubectl auth can-i get secrets -n upgrade-sessions --as=system:serviceaccount:secure-agent-pod:agent-sa`
answers `no`. frank#913's upgrade sessions must not hold credentials before this
passes. The `root-agents` group's cluster-admin is a separate change.

**Observability (R11).** In the same PR, so nothing pages on the way down, tombstone
`exercise-reminder-stale`, `session-manager-stale`, `audit-digest-stale`,
`agent-pod-not-running` and `layer-18-persistent-agent-degraded`, delete the retained
heartbeat series as a recorded manual step, and remove `secure-agent-pod-dashboard-cm.yaml`, its two
mounts in `apps/victoria-metrics/values.yaml`, the heartbeat and namespace panels
in `dashboard-cm.yaml`, and `vmpodscrape.yaml` (with the app).

One PR does not by itself keep the removal silent: Grafana reads provisioning at
boot, so the stored rules keep evaluating the retained heartbeat series after the pod
is gone, and `session_manager` goes stale within about 15 minutes. The manual phase
is therefore ordered: create one Grafana silence for the five rule uids before the
merge; merge; confirm the rules ConfigMap holds the tombstones; restart Grafana;
assert through the running Grafana API that none of the five uids exists; delete the
retained `exercise_reminder`, `session_manager` and `audit_digest` pushgateway series
and assert they are gone; delete the silence. `grafana-alerting` does not prune, so
the live ConfigMap `grafana-secure-agent-pod-dashboard` in `monitoring` is deleted by
hand and asserted NotFound. Every rule labelled `frank-ops#18` is tombstoned, so that
tracker is closed as a recorded step.

**Images and leftovers (R12, R13).** Remove the `kali` matrix leg and directory
from `agent-images`, and the temporary exclusion from the bump workflow together
with its local twin (`FROZEN_UNTIL_POD_RETIRED` and
`test_frozen_images_are_not_bumped_by_the_workflow` in
`scripts/tests/test_agent_images_bump_coverage.py`). In Frank,
delete `secrets/secure-agent-pod/` and `secrets/github-app/github-app-derio-key.yaml`
(after confirming the Tekton copy holds the same key, and retiring its runbook line),
and update `test_claude_autoupdater_disabled.py`,
`test_fr_isolation_target_env.py` and `test_config_reaches_the_process.py`, plus
stale pointers in `references/access.md`, the browser-harness rules,
`agents/rules/frank-gotchas.md` and `agents/rules/frank-infrastructure.md`.
Update `README.md` with `/update-readme`.

The tripwire already exists: extend `scripts/tests/test_vk_retired.py` instead of
adding a file. Drop `POD_DEPLOYMENT`, `POD_PIN` and the `skip_pod` exemption, whose
test would raise once the directory is deleted. Assert that `apps/secure-agent-pod`,
both root templates and `secrets/secure-agent-pod` are absent, that the five uids
are tombstoned and no longer defined, that the workflow has no frozen exclusion, and
that nothing under `apps/`, `secrets/` or `.github/` names the pod's images
(`secure-agent-kali`, `vk-local`), its namespace as a live target, or its three
addresses. Prose that names the pod must say it is retired; the scan allows a line
only when it carries `retired` or `HISTORICAL`, and tombstones are allowed by uid.

Pointers the pod leaves behind are fixed, not exempted:
`scripts/hooks/session-start.sh`, `apps/argocd-extras/manifests/externalsecret-repo-runs-fr.yaml`,
both `apps/tekton/manifests/clustergenerator-*github-app*.yaml`,
`apps/paperclip/manifests/deployment.yaml`, the `apps/hermes-agent-shell` manifests
and its two root templates, `secrets/hermes-agent-shell/README.md`,
`secrets/ruflo/README.md`, `patches/phase04-gpu/403-gpu1-pcie-aspm.yaml`,
`docs/runbooks/frank-gotchas/networking.md`, and the comments in
`test_staging_gate_manifests.py`, `test_etcd_scrape.py` and
`test_hermes_ssh_byok_env_snapshot.py`. The pod's manual operations are retired in
their plan blocks and then resynced, because the runbook is generated: the pod
bootstrap and key-apply operations, and the operation that builds the Tekton key from
`secrets/github-app/github-app-derio-key.yaml`, which is repointed at
`github-app-derio-key-tekton.yaml` before the source file is deleted.

`scripts/tests/fixtures/life/pin-exceptions.yaml` arrives with frank#913 and lists
the `vk-local` and `secure-agent-kali` pins. Whichever of #913 and this PR merges
second removes both entries. If the file is on `main` when this PR is rebased, this
PR removes them and the tripwire asserts their absence; otherwise the PR body records
that #913 must drop them. Manual operations record:
removing the `agent-secrets-tier2` Infisical keys no other consumer uses, and
removing the user-level `vibe_kanban` MCP entry on the Mac.

**Blog (R14).** Use the existing `> **Update 2026-11.**` blockquote convention.

| Treatment | Posts |
|---|---|
| Superseded notice at top, bump `last_updated` | building `21-secure-agent-pod`, `25-vk-relay`, `26-vk-remote-self-host`; operating `14-secure-agent-pod`, `20-vk-relay`, `21-vk-remote` |
| Short update note where VK or the pod is central | building `18-persistent-agent`, `28-agent-images-sidecar`, operating `19-git-credentials-without-a-shell`, paper `17-agentic-orchestration` |
| Fix or annotate passing mentions | building `00-overview`, `20-workflow-automation`, `22-health-monitoring`; operating `06-secrets`, `15-health-monitoring`; building `24-in-cluster-ingress`; papers `10-self-hosted-inference`, `15-ingress-and-service-catalog` |

Notices point to `33-hermes-shell` as the agent shell that remains. Annotate the
`blog/data/roadmap.yaml` entries rather than deleting them, since the layers
happened. Posts stay published. Paper 17's `data/vendors.yaml` and its dossier are
left as the research record they are. A test asserts that every bundle in the first
two rows carries the `> **Update 2026-11.**` line.

**Revival note (R15).** To revive chorebot: redeploy from `derio-net/willikins`
`scripts/chorebot` as its own workload. Its data remains in Notion. Its
`config.yaml` is not in git, so it joins the archive; it may hold tokens, so the
archive stays off git and off shared storage.

### Out of scope

- `argocd/repo-runs-fr` is already in `SecretSyncedError` because
  `github-app-derio-key` is missing from `argocd`. This predates the retirement and
  gets its own issue.
- Deleting published GHCR packages. They stay so old commits still resolve.
- VK dispatch code inside `super-fr`.
- Why `remote-control` does not appear in the app.

## Verification

strategy: live
gate: devops

- vk-alerts-retired: live — Grafana's stored rule set exists only on the running cluster.
- vk-remote-removed: live — the cascade can only be observed on the live cluster.
- vk-surface-removed: live — requires the deployed route, Authentik and homepage state.
- vk-mirror-retired: live — mirror delivery and repository archive state exist only on the forges.
- vk-images-retired: live — only a real bump workflow run proves coverage still passes.
- kali-image-retired: live — only a real bump workflow run after Phase 2 proves it.
- vk-tooling-retired: none — reviewed in the PR diff, with CI running the updated guards.
- gitops-push-token-continuity: live — token minting only happens through live ESO.
- pod-undisturbed-phase-1: live — only the running pod's UID and restart count prove it.
- pod-removed-after-archive: live — removal and archive contents are live operational facts.
- pod-removal-silent: live — the absence of pages can only be observed after the removal.
- vk-posts-superseded: none — the blog build and its existing tests run in CI on the PR, and the notices are reviewed in the diff.
- no-vk-references-remain: none — the new tripwire test in `scripts/tests/` verifies this in CI.

## Phase 1 checks (shipped)

These were the Test Plan of the Phase 1 PR and are kept as its record.

0. Pre-merge: the `postgres-vk` dump is verified on the Mac; the pod UID and restart counts are recorded; `argocd app diff secure-agent-pod` shows no Deployment change; no `bump/agent-images-*` PR is open.
1. (op: step-2) `kubectl -n secure-agent-pod get pod` shows the same pod UID and `kali` restart count as the row 0 baseline.
2. After the Grafana restart, the Grafana API lists none of the three VK rule UIDs, and `Layer 18 Persistent Agent Heartbeat Stale` has no `job=vk_issue_bridge` instance.
3. (op: step-4) `kubectl get ns agents` is NotFound. `kubectl -n traefik-system get ingressroute vk-remote` is NotFound, because the namespace's removal alone would hide a skipped manual delete. Authentik has no `vk-remote-cluster` application or `VK Remote (cluster)` provider, and the homepage has no VK tile.
4. (op: step-5) `kubectl get clustergenerator github-app-derio` shows a `tekton-extras` tracking id. After a forced resync, `frank-gitops-push` is `SecretSynced` with a refreshed token.
5. The next agent-images bump run completes with its coverage check green.
6. `derio-net/vibe-kanban` reports `archived: true`, and `ci-delivery-check` reports no overdue finding for it.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-11-08--agents--retire-vk | `derio-net/frank` | `2026-11-08--agents--retire-vk` | — |
| 2026-11-12--agents--retire-secure-agent-pod | `derio-net/frank` | `2026-11-12--agents--retire-secure-agent-pod` | 2026-11-08--agents--retire-vk |

## Test Plan

Phase 2, post-merge and operator-driven, except row 7 which gates leaving draft.

7. (op: premerge-archive) The archive lists and verifies in `~/Archives/secure-agent-pod-2026-11` (mode `0700`) before the PR leaves draft, and contains chorebot's `config.yaml`. Before the merge, the three gates under "Removal" pass: generator ownership, key fingerprints, root `prune`.
8. (op: step-8) `kubectl -n argocd get application secure-agent-pod` is NotFound, `kubectl get ns secure-agent-pod` is NotFound, the PV is gone, and no Service holds .215, .218 or .219.
9. (op: step-9) `kubectl get clusterrolebinding secure-agent-pod-cluster-admin` is NotFound after the explicit delete, and `kubectl auth can-i get secrets -n upgrade-sessions --as=system:serviceaccount:secure-agent-pod:agent-sa` answers `no`.
10. (op: step-10) After the Grafana restart, the Grafana API lists none of the five rule uids, the three heartbeat series are gone from the pushgateway, and `monitoring/grafana-secure-agent-pod-dashboard` is NotFound. No alert fires because of the removal during the following hour, and `frank-gitops-push` is still `SecretSynced` after that hour.
11. (op: step-11) The next agent-images bump run after both Phase 2 PRs merge completes with its coverage check green and no frozen exclusion.
