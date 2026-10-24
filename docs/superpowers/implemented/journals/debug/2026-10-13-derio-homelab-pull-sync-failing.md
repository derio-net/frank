<!-- fr:journal-schema=2 -->
# Journal: 2026-10-13-derio-homelab-pull-sync-failing

<!-- fr:journal kind=repro scope=debug id=5b7de4b38b4c created=2026-10-13T19:28:29+00:00 -->
### 5b7de4b38b4c · repro · Layer 25 Pipeline Failing derio-homelab-pull-sync: 8 failures, 0 successes in 24h

Every retained run (kid-laptops-main-sync-*) fails in seconds in step pull-from-github-push-to-gitea. Gitea rejects the push: 'remote: error: object file .../derio-homelab/kid-laptops.git/objects/.. is empty', 'pack has 66 unresolved deltas', '! [remote rejected] main (unpacker error)'. First failure of this shape 2026-10-13 16:50Z (first new push to kid-laptops since the corruption).

<!-- fr:journal kind=root-cause scope=debug id=4146fdceba9b created=2026-10-13T19:28:35+00:00 -->
### 4146fdceba9b · root-cause · 13 zero-byte loose objects in Gitea's kid-laptops bare repo (since 2026-08-01 10:42Z)

Measured in the gitea pod: exactly 13 empty files under objects/, all mtime 2026-08-01 10:42, no other repo affected (scanned every repo). Gitea main = b6da197b, itself one of the 13 empty objects, so the branch tip is unreadable and any push whose pack deltas against them cannot resolve. Unclean-shutdown signature. Matches frank#849, filed by the earlier mirror-resilience session; this alert is that issue escalating.

<!-- fr:journal kind=ruled-out scope=debug id=59c3aad27dba created=2026-10-13T19:28:40+00:00 -->
### 59c3aad27dba · ruled-out · frank#849 proposed fix (delete empties, then re-push) does NOT work

Tested on a scratch copy of the bare repo (5.1MB, copied out read-only). Delete-only: fsck then reports refs/heads/main invalid sha1 pointer, and re-pushing GitHub main is still rejected (unpacker error): the client believes the remote already has those objects so never re-sends them. Reproduced the original error offline first (same 'unresolved deltas').

<!-- fr:journal kind=hypothesis scope=debug id=85d8e197cccc created=2026-10-13T19:28:46+00:00 -->
### 85d8e197cccc · hypothesis · Re-supplying the 13 objects from GitHub repairs the repo

Delete the empties, then pack exactly those objects from a GitHub clone and unpack-objects them into the bare repo. Tested on scratch: fsck output 0 lines, push of 3e3798e fast-forwards main b6da197..3e3798e.

<!-- fr:journal kind=finding scope=debug id=b5ae1fbfa633 created=2026-10-13T19:32:27+00:00 state=fixed -->
### b5ae1fbfa633 · finding [fixed] · scripts/gitea-repair-empty-objects.sh re-supplies the objects; tested on fixture and on real-data copy

New script (dry-run default; refuses unsafe plans before changing anything; verifies cat-file + fsck; idempotent) and scripts/tests/test_gitea_repair_empty_objects.py (7 tests: fixture reproduces the incident, delete-and-repush FAILS, dry-run no-op, apply repairs + unblocks push, idempotent, refuses unsupplyable, --allow-missing). Red first (5 failed, script absent), green after. Real-data check on a scratch copy of the 5.1MB production repo: 13/13 restored, fsck 0 lines, push of 3e3798e fast-forwards main b6da197..3e3798e. Gotcha added (tekton.md + frank-gotchas.md). PRODUCTION REPAIR NOT RUN: it mutates Gitea storage, left for the operator.

<!-- fr:journal kind=review scope=debug id=c21c66bd32bd created=2026-10-13T19:35:37+00:00 -->
### c21c66bd32bd · review · Self-review of the diff (no independent reviewer)

Read the whole diff myself; no subagent reviewer dispatched. Findings raised: none blocking. Checked: (1) the script deletes nothing until the plan is proven safe (missing-object check runs before any rm; test asserts nothing is deleted on refusal); (2) dry-run is the default; (3) verification is cat-file per object plus an empty git fsck, not an assumption; (4) kubectl exec runs as git uid 1000, same owner as the repo, so restored objects have correct ownership; (5) GITEA_EXEC uses ${VAR-default} so an empty string selects local mode for tests while unset selects the pod. Residual risks, stated in the PR: the production repair is NOT run (writes Gitea storage; operator step); a Gitea write concurrent with the repair is possible, mitigated by the 5MB size and idle mirror; the cause of the 2026-08-01 unclean stop is unverified, so recurrence is not prevented; mirror-reconcile still does not cover derio-homelab.
