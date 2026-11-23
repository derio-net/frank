<!-- fr:journal-schema=4 -->
# Journal: 2026-11-23-status-bridge-toctou

<!-- fr:journal kind=repro scope=debug id=f097f1018aa9 created=2026-11-23T07:28:30+00:00 -->
### f097f1018aa9 · repro · Stale pending posted to GitHub after its terminal status (runs-fr PR #52)

layer-25-delivery-overdue kind=status, derio-net/runs-fr, sha 5fb5d703, context 'acceptance-report / pages (push)'. Bridge run vwtxc (pending) created 21:41:18, current-state 21:41:18-28, forward POSTed 21:42:41. Run qzshd (success) created 21:41:52, POSTed 21:42:07. GitHub latest = pending forever. Repaired via scripts/ci_status_backfill.py (stoa-status-bridge-nc9nv). frank#1029.

<!-- fr:journal kind=ruled-out scope=debug id=f75fed955127 created=2026-11-23T07:28:33+00:00 -->
### f75fed955127 · ruled-out · Guard logic bug (wrong field / wrong context match)

At 21:41:2x Gitea genuinely held pending for the context: the success event was only created at 21:41:52. The guard answered correctly for the moment it asked.
