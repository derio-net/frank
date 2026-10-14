<!-- fr:journal-schema=2 -->
# Journal: 2026-10-14--cicd--actionable-alerts

<!-- fr:journal kind=discovery scope=plan id=delivery-t1-tdd created=2026-10-14T17:57:45+00:00 phase=1 -->
### delivery-t1-tdd · discovery · Real-work comparison red-green and API boundaries (phase 1)

Task 1 red: 1 failure/14 errors because checker did not exist; green: 15 passed.
Separate API, latest-status selection, forwarding comparison and per-repo checks.
GitHub read-only gh probe confirmed branch commit.sha and committer.date; current
public-repo status list was empty, not evidence about private Gitea status shapes.
Private Gitea authenticated probes remain inaccessible in dev profile and must
be performed by operator-selected cluster-admin close-out; no live success claimed.
github-status passes the mapped description verbatim (no local truncation).
Checker accepts that exact mapping or a legitimate 140-character capped
representation, including skipped/warning mapping; state and URL must match.
The forwarding task remains unchanged; no new shell byte/Unicode truncation.

<!-- fr:journal kind=discovery scope=plan id=delivery-t2-tdd created=2026-10-14T17:57:45+00:00 phase=1 -->
### delivery-t2-tdd · discovery · Complete snapshots and failed reads are explicit (phase 1)

Task 2 red: 7 failed/24 passed; green: 31 passed. Pagination continues until
an empty page even when a server caps page size, bounded to 20 pages per list.
All successful API reads are memoized per repo/path within one invocation;
status comparisons deduplicate exact mirrored SHA heads, never infer missing
statuses on unmirrored heads. Read budget 210s, per-call 10s, publish 10s,
Job hard limit 270s. Budget exhaustion marks unread repos in a partial PUT
snapshot and fails the Job. Worst-case page exhaustion intentionally fails
rather than certifying large/rate-limited repos healthy. Normal quiet cost
is repo/main/branch + PR lists and 1 empty Gitea status page per mirrored SHA.
Per-repo diagnostics contain no exception bodies or arbitrary forge text;
metrics have only configured repo and mirror/status labels.

<!-- fr:journal kind=discovery scope=plan id=delivery-t3-tdd created=2026-10-14T17:57:45+00:00 phase=1 -->
### delivery-t3-tdd · discovery · Idle deletion and delivery alert predicates (phase 1)

Task 3 red: 3 failed/9 passed on retained idle definitions and missing delivery
rules. Green affected suites: 110 passed; initial full suite: 1221 passed,
9 skipped, 1 xfailed. New A-B-C rules retain NoData OK, warning/frank-ops#25,
and ten-minute holds; absent() explicitly catches missing timestamp.
Outcome/platform/PVC/timeout/reconciler rules unchanged. Retired obsolete
idle-window tests and documentation; retained controller scrape and failure
ratio guards. Added descriptions and operational diagnostics to CI posts and
compact/full Grafana/Tekton gotchas. Agent-config validator passed; plans
validator used its minimal fallback because super-fr validator was unavailable
in the dev container. Live private-forge and post-merge provisioning/scrape
evidence remains owed within this run's DevOps close-out, not a new issue.

<!-- fr:journal kind=discovery scope=plan id=delivery-final-evidence created=2026-10-14T17:57:45+00:00 phase=1 -->
### delivery-final-evidence · discovery · Full clean-tree suite covers the committed implementation (phase 1)

Final affected suites 116 passed. Final full uv run pytest -q scripts/tests/
after code commit 71ba9057 and clean git status: 1227 passed, 9 skipped,
1 xfailed in 114.98s, exit=0. Host-visible ignored raw log includes the exit
sentinel; only this record changed after the suite. No background processes,
forge writes, synthetic CI, pushes or PRs. All nine steps performed; cursor
remains unresolved for the orchestrator. Authenticated Gitea live probes
require operator-selected cluster-admin access and remain unclaimed.

<!-- fr:journal kind=finding scope=plan id=p1-r1 created=2026-10-14T18:42:22+00:00 phase=1 state=open review_scope=in -->
### p1-r1 · finding [open] (reviewer: in scope) · GitHub context identity is case-insensitive (phase 1)

Independent reviewer reproduced selection of an older success over a newer differently-cased failure, and false mismatch for an uppercase equivalent context. Fixed in 11a6b4fc with normalized destination identities and source collision handling; independent re-review confirmed regression cases pass.

<!-- fr:journal kind=finding scope=plan id=p1-r2 created=2026-10-14T18:42:22+00:00 phase=1 state=open review_scope=in -->
### p1-r2 · finding [open] (reviewer: in scope) · Readable commits need status checks despite branch drift (phase 1)

Independent reviewer reproduced status loss hidden inside mirror grace because branch equality gated status reads. Fixed in 11a6b4fc: deduplicate all source heads and verify commit readability independently, distinguishing true commit 404 from auth/read errors. Re-review confirmed the original case now warns.

<!-- fr:journal kind=finding scope=plan id=p1-r3 created=2026-10-14T18:42:22+00:00 phase=1 state=open review_scope=in -->
### p1-r3 · finding [open] (reviewer: in scope) · Malformed forge SHA responses must fail reads (phase 1)

Independent reviewer reproduced a healthy snapshot for matching truncated identifiers. Fixed in 11a6b4fc with full forty-character hex API SHA validation and malformed-response cases; re-review confirmed read_error=1 for the original repro.

<!-- fr:journal kind=finding scope=plan id=p1-r4 created=2026-10-14T18:42:22+00:00 phase=1 state=open review_scope=in -->
### p1-r4 · finding [open] (reviewer: in scope) · Live Gitea status contract differs from GitHub (phase 1)

Authenticated read-only live probe found Gitea status histories use status, not state. Fixed in 357d4c28 by validating/normalizing Gitea status in the API adapter without changing GitHub or cached records. Fifteen tests reproduced RED; independent re-review confirmed observed-schema cases and all supported states.

<!-- fr:journal kind=discovery scope=plan id=live-forge-contracts created=2026-10-14T18:42:22+00:00 phase=1 -->
### live-forge-contracts · discovery · Authenticated live forge contracts verified (phase 1)

Operator explicitly selected a separate cluster-admin isolation workspace for read-only
probes. Existing gitea-api-token, stoa-github-mirror, and derio-homelab-github-mirror
Secrets were read in memory without printing tokens. Verified Gitea repo/full_name,
branch commit.id, git/commits sha, and status history schema against agentic-stoa/cnc-fr;
two source and two destination statuses, zero open PRs on the sampled repo. Verified
GitHub branch/status/PR reads with the stoa installation and kid-laptops branch read
with the homelab installation. Gitea raw statuses carry status; GitHub carries state.
The corrected authenticated probe passed every assertion. Verified in-cluster service
gitea-http in namespace gitea exposes port 3000. These are contract/access checks,
not claims that the candidate CronJob or alerts have deployed.

<!-- fr:journal kind=review scope=plan id=p1-independent-review created=2026-10-14T18:42:22+00:00 phase=1 -->
### p1-independent-review · review · Independent code review completed; four findings fixed (phase 1)

Reviewer ses_ec46f8ac4ffegfAdTQyIor969B reviewed code/spec/plan in a separate context,
reproduced three initial findings, and re-reviewed commits 11a6b4fc and 357d4c28.
Final verdict: p1-r1 through p1-r4 fixed, no new or out-of-scope findings.
Independent targeted suite: 105 passed. Final implementation full suite after code
commit: 1257 passed, 9 skipped, 1 xfailed, exit=0. Authenticated live probes separately
verified access and response contracts; deployment remains DevOps-gated.

<!-- fr:journal kind=finding scope=plan id=p1-r1-resolved created=2026-10-14T18:42:22+00:00 phase=1 state=fixed resolves=p1-r1 -->
### p1-r1-resolved · finding [fixed] · resolves p1-r1: GitHub context identity is case-insensitive (phase 1)

11a6b4fc; normalized GitHub context identity and collision tests; independent re-review passed.

<!-- fr:journal kind=finding scope=plan id=p1-r2-resolved created=2026-10-14T18:42:22+00:00 phase=1 state=fixed resolves=p1-r2 -->
### p1-r2-resolved · finding [fixed] · resolves p1-r2: Readable commits need status checks despite branch drift (phase 1)

11a6b4fc; independent commit-readability adapter and drift regression; independent re-review passed.

<!-- fr:journal kind=finding scope=plan id=p1-r3-resolved created=2026-10-14T18:42:22+00:00 phase=1 state=fixed resolves=p1-r3 -->
### p1-r3-resolved · finding [fixed] · resolves p1-r3: Malformed forge SHA responses must fail reads (phase 1)

11a6b4fc; full API SHA validation and malformed identifier cases; independent re-review passed.

<!-- fr:journal kind=finding scope=plan id=p1-r4-resolved created=2026-10-14T18:42:22+00:00 phase=1 state=fixed resolves=p1-r4 -->
### p1-r4-resolved · finding [fixed] · resolves p1-r4: Live Gitea status contract differs from GitHub (phase 1)

357d4c28; validated Gitea status normalization and live-shaped fixtures; independent re-review passed.
