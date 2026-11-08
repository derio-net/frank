<!-- fr:journal-schema=3 -->
# Journal: 2026-11-08--agents--retire-vk

<!-- fr:journal kind=decision scope=plan id=p1-pod-dir-exempt-from-reference-scan created=2026-11-08T22:09:07+00:00 phase=1 -->
### p1-pod-dir-exempt-from-reference-scan · decision · Guard test exempts apps/secure-agent-pod from the vk.cluster.derio.net scan (phase 1)

The spec's guard says no apps/ file references vk.cluster.derio.net, but the live pod Deployment (untouched by the HARD INVARIANT) sets two VK URLs on vk-local. test_vk_retired.py therefore skips apps/secure-agent-pod for that scan only; Phase 2 deletes the pod and the exemption together.

<!-- fr:journal kind=decision scope=plan id=p1-fixture-repo-renamed created=2026-11-08T22:09:07+00:00 phase=1 -->
### p1-fixture-repo-renamed · decision · CI budget fixtures renamed vibe-kanban to runs-fr instead of loosened (phase 1)

usage.json and test_ci_budget_watcher.py used vibe-kanban as one of three preferred repos. Renamed it to runs-fr (a surviving github-preferred repo) so all counts and ratios (200/410, 300/410) stay identical. test_ci_status_backfill.py REPO and default_repos assertion moved to runs-fr likewise.

<!-- fr:journal kind=discovery scope=plan id=p1-manual-ops-in-prose created=2026-11-08T22:09:07+00:00 phase=1 -->
### p1-manual-ops-in-prose · discovery · retire-vk manual-operation blocks live in _prose.md, not NN.yaml (phase 1)

The sync-runbook skill greps docs/superpowers/plans/ recursively, so the four blocks in _prose.md were appended to docs/runbooks/manual-operations.yaml (the file is chronological, not sorted, so appended at the end). vibe-kanban-dispatch-pat is status: decommissioned in both the 2026-04-15 plan block and the runbook, following the Paperclip precedent.

<!-- fr:journal kind=discovery scope=plan id=p1-deliberate-leftovers created=2026-11-08T22:09:07+00:00 phase=1 -->
### p1-deliberate-leftovers · discovery · Deliberate Phase 2 / historical leftovers after grep accounting (phase 1)

Remaining hits: everything under apps/secure-agent-pod (Deployment VK env, service-vibekanban.yaml, disabled cilium egress); agents/rules/frank-infrastructure.md pod row (spec: waits for Phase 2); README pod rows; frank-gotchas lines marked HISTORICAL; the PGDATA gotcha and a hermes Deployment comment citing apps/vk-remote as a past precedent; the tombstone slug in the Authentik blueprint; the tekton generator comment; test files naming VK to guard its absence. The deployment.yaml diff against origin/main is empty; the only apps/secure-agent-pod change is the generator file moving out.

<!-- fr:journal kind=discovery scope=plan id=p1-silences-and-deleterules created=2026-11-08T22:09:07+00:00 phase=1 -->
### p1-silences-and-deleterules · discovery · Alerts removed via deleteRules plus dashboard selector edit (phase 1)

Layer 18 keeps three heartbeats (exercise_reminder, session_manager, audit_digest); Phase 2 owns them. The Layer 15 namespace regex dropped the agents namespace, and the notification-policy comment now notes the original health_bridge_only first user was retired.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t1 created=2026-11-08T22:09:07+00:00 phase=1 -->
### no-refactor-p1-t1 · discovery · no-refactor-because P1.T1 (phase 1)

A single new guard test file with no duplicated helpers; nothing to clean.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t2 created=2026-11-08T22:09:07+00:00 phase=1 -->
### no-refactor-p1-t2 · discovery · no-refactor-because P1.T2 (phase 1)

Pure deletions plus tombstones; no logic left to simplify.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t3 created=2026-11-08T22:09:07+00:00 phase=1 -->
### no-refactor-p1-t3 · discovery · no-refactor-because P1.T3 (phase 1)

Pure deletions and tombstones copied from the Ruflo shape; nothing to clean.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t5 created=2026-11-08T22:09:07+00:00 phase=1 -->
### no-refactor-p1-t5 · discovery · no-refactor-because P1.T5 (phase 1)

List edits only; counts in tests changed with the removed repo, and the fixture repo was renamed rather than counts loosened.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t6 created=2026-11-08T22:09:07+00:00 phase=1 -->
### no-refactor-p1-t6 · discovery · no-refactor-because P1.T6 (phase 1)

The vkr parameter was removed end to end (workflow, collect, legacy_body, CLI, tests), leaving no dead plumbing.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t7 created=2026-11-08T22:09:07+00:00 phase=1 -->
### no-refactor-p1-t7 · discovery · no-refactor-because P1.T7 (phase 1)

Doc edits only; nothing duplicated.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t8 created=2026-11-08T22:09:07+00:00 phase=1 -->
### no-refactor-p1-t8 · discovery · no-refactor-because P1.T8 (phase 1)

Refactor task: grep-accounted every remaining VK hit (removed, marked historical, or deliberate Phase 2 leftover) and found no duplication introduced by the edits.
