# Journal: 2026-10-12-draft-pr-no-ci

<!-- fr:journal kind=repro scope=debug id=30e3259e6116 created=2026-10-11T23:57:38+00:00 -->
### 30e3259e6116 · repro · PR #797: zero pull_request runs for ~11h while draft; first runs 08:53:50Z, 9 min after a 'Merge origin/main' push

Source: frank#800. Three pull_request events while draft (opened 22:15Z, two synchronize) created no run. workflow_dispatch on the branch ran green. Runs appeared 08:53:50Z after merge commit 38b49d6e (08:44Z), 9s before ready_for_review.

<!-- fr:journal kind=ruled-out scope=debug id=a54f20029f61 created=2026-10-11T23:57:42+00:00 -->
### a54f20029f61 · ruled-out · Draft state does not suppress pull_request workflows in this repo

Open drafts #839 and #840 (2026-10-11) both carry a tripwires check run from pull_request. No ruleset or Actions setting gates drafts (ruleset 16767331 = deletion + non_fast_forward only; branch protection: none).

<!-- fr:journal kind=root-cause scope=debug id=8f8b7fa01f10 created=2026-10-11T23:57:44+00:00 -->
### 8f8b7fa01f10 · root-cause · #797 was CONFLICTING with main from creation, so GitHub created no merge ref and no pull_request run; with no required checks, absence rendered as clean

main gained #787 (21:15Z) and #762 (21:28Z) before #797 opened at 22:15Z. `git merge-tree --write-tree f7ecc790 dcb31fe6` -> CONFLICT in agents/rules/frank-gotchas.md, docs/acceptance/matrix.yaml, docs/runbooks/frank-gotchas/grafana.md. GitHub only fires pull_request workflows against refs/pull/N/merge, which does not exist while conflicting. The 08:44Z merge 38b49d6e resolved them; runs followed. The ready flip 9s later was coincidence. Contributing: main has no required status checks, so a missing check is never shown as Expected.

<!-- fr:journal kind=finding scope=debug id=02a8bb93768a created=2026-10-12T00:01:11+00:00 state=fixed -->
### 02a8bb93768a · finding [fixed] · pr_ci_verdict.py never reads absence as a pass; CONFLICTING is its own verdict; record corrected in gotchas + tripwires header

Failing-test-first: scripts/tests/test_pr_ci_verdict.py (14 cases, red at 0c then green). Live: #797 now PASSED, #839 PASSED, #842 PENDING (draft, tripwires running — third live proof drafts get CI). Not changed: no types: ready_for_review (wrong cause); required-check ruleset left to operator.
