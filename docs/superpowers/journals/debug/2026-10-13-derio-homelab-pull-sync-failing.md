# Journal: 2026-10-13-derio-homelab-pull-sync-failing

<!-- fr:journal kind=repro scope=debug id=5b7de4b38b4c created=2026-10-13T19:28:29+00:00 -->
### 5b7de4b38b4c · repro · Layer 25 Pipeline Failing derio-homelab-pull-sync: 8 failures, 0 successes in 24h

Every retained run (kid-laptops-main-sync-*) fails in seconds in step pull-from-github-push-to-gitea. Gitea rejects the push: 'remote: error: object file .../derio-homelab/kid-laptops.git/objects/.. is empty', 'pack has 66 unresolved deltas', '! [remote rejected] main (unpacker error)'. First failure of this shape 2026-10-13 16:50Z (first new push to kid-laptops since the corruption).
