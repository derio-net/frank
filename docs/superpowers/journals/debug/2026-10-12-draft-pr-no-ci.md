# Journal: 2026-10-12-draft-pr-no-ci

<!-- fr:journal kind=repro scope=debug id=30e3259e6116 created=2026-10-11T23:57:38+00:00 -->
### 30e3259e6116 · repro · PR #797: zero pull_request runs for ~11h while draft; first runs 08:53:50Z, 9 min after a 'Merge origin/main' push

Source: frank#800. Three pull_request events while draft (opened 22:15Z, two synchronize) created no run. workflow_dispatch on the branch ran green. Runs appeared 08:53:50Z after merge commit 38b49d6e (08:44Z), 9s before ready_for_review.
