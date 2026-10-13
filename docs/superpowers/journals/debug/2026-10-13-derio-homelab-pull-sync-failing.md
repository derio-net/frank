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
