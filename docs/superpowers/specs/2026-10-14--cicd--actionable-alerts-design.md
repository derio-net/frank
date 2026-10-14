# Actionable CI delivery alerts

## Goal

CI notifications should indicate failed expectations, not a quiet repository.
Replace both Layer 25 idle rules and implement the missing delivery checks in
this change. No delivery-detection follow-up issue is required.

## Requirements

R1. Neither stoa-status-bridge nor github-pull-sync inactivity alone produces a notification; existing fault alerts remain available.
R2. A GitHub main or open-PR head that should be mirrored but remains absent or different in Gitea beyond a grace period produces a delivery warning, and matching refs clear it.
R3. An eligible Gitea status on a currently monitored commit that is absent or differs on GitHub beyond a grace period produces a delivery warning, and matching forwarded statuses clear it.
R4. Checker failures, unreadable forge data, missing results, and stale results are observable and cannot silently claim healthy delivery.
R5. The checker is deployed declaratively, reads existing credentials without exposing them, and performs no forge writes or synthetic CI work.
R6. Behavioural tests prove quiet, delayed, missed, recovered, pagination, and failed-read cases before merge; live verification belongs to this run's gated close-out.

## Design

### Alternatives considered

1. Increase idle windows: still assumes human activity has a required frequency.
2. Synthetic forge events: continuously exercise the path, but need a dedicated
   repository and forge writes, and add CI work solely to monitor CI.
3. Compare real work with delivered outcomes (chosen by the operator): verify
   GitHub-to-Gitea refs and Gitea-to-GitHub statuses. With no outstanding work,
   delivery is healthy regardless of how long pipelines have been idle.

### Read-only delivery checker

Add `apps/tekton/manifests/ci-delivery-check.yaml`: a ConfigMap with a standard-
library Python script and a CronJob every five minutes. Follow mirror-reconcile's
non-root, bounded-resource, emptyDir-only shape, without Tekton/PVC dependencies.
The existing `stoa-github-mirror`, `derio-homelab-github-mirror`, and
`gitea-api-token` Secrets supply credentials. Read tokens from mounted files on
each invocation; do not bake a rotating token into a long-running process.

Derive repo coverage from the same MAIN_REPOS/PR_REPOS contracts as
`apps/tekton/manifests/mirror-reconcile.yaml`, and guard parity with tests against
the EventListener triggers. Include kid-laptops mirror refs, but only
agentic-stoa statuses: `gitea-status-bridge` explicitly excludes other orgs.
Check main and `sync-pr-N` refs for the PR triggers that actually mirror them.
Paginate open PRs and commit statuses on both forges, de-duplicate commit heads,
and impose bounded request timeouts and a Job deadline. Partial or malformed
responses and pagination exhaustion are checker errors, not empty data.

For each expected ref, compare GitHub's head SHA to Gitea's branch SHA. Apply a
30-minute grace based on the source commit's committer timestamp, matching the
existing reconciler's time model. This gives the 15-minute reconciler a normal
opportunity to repair before warning; old commits pushed late may be checked
immediately, but a healthy mirror remains quiet. A missing Gitea branch is drift;
unreadable repositories or authentication failures are checker errors. Ensure a
branch 404 is only treated as missing after successfully reading that repo.

On each agentic-stoa source head, select the newest Gitea status per context and
the newest GitHub status per context; order explicitly by timestamps/IDs rather
than trusting API order. Match the EventListener filter `!context.startsWith('tekton')`.
An empty eligible Gitea status set is healthy: path-filtered CI may legitimately
produce none. For each eligible status older than ten minutes, expect context
`gitea-actions/<context>` with normalized state (`skipped`/`warning` become
`success`), target URL, and the bridge's description mapping. No same-SHA
assumption across different branches: compare statuses on the exact source SHA.
A status missing at GitHub or differing after grace is a missed delivery.
Do not infer status loss while that commit is still absent from Gitea; report
ref drift and check statuses once the mirror commit can be read.

### Metrics and alerts

PUT one complete snapshot to the existing
`http://pushgateway.monitoring.svc:9091/metrics/job/ci-delivery-check` grouping
key. This replaces old repo/PR findings instead of leaving stale series after
a PR closes or scope changes. Export bounded labels (repo and kind, never SHA,
PR number, status context, or URLs): overdue item counts for `mirror` and
`status`, per-repo read-error indicators, and the last completed check timestamp.
Count gauges start at zero on each successful read. Publish partial results
with explicit error gauges, then fail the Job when a read fails. Never stamp a
successful check before the snapshot is built; push failure fails the Job.
Logs give the bounded diagnostic repo/ref/context details without credentials.

Add Grafana A→B→C rules in the Layer 25 outcome group: positive overdue counts
held for ten minutes warn per repo/kind; read errors held for ten minutes warn;
absent or older-than-15-minute snapshot timestamp held for ten minutes warns.
The checker watchdog must cover never-started Jobs and Pushgateway data loss,
not just a CronJob's optional last-success series. Keep rule UIDs at most 40
characters, `severity: warning`, and `github_issue: frank-ops#25`.
Healthy predicate filters return NoData, so `noDataState: OK` is intentional;
the watchdog explicitly uses `absent()` to detect missing telemetry.

Remove both idle rule definitions and add Grafana provisioning `deleteRules`
tombstones for their UIDs. Removing file definitions alone does not prove the
existing stored rules were deleted. Keep all other CI failure/platform/PVC/
timeout/reconciler alerts intact. Update obsolete idle-rule tests and relevant
CI operating/building documentation and gotchas to explain concrete expectations.

## Verification

strategy: live
gate: devops
- ci-quiet-no-idle-alert: live — Grafana reads file-provisioned rules at startup; verify actual deletion and retained fault rules after the merged configuration is loaded. Offline tests verify the candidate's provisioning document before merge.
- ci-real-work-delivery: live — Production credentials and both private forges are required to verify the scheduled deployment and scrape. Before merge, behavioural tests inject forge responses and read-only live probes check API contracts where access permits.
- ci-delivery-checker-visible: live — Scheduled execution, metrics scraping, and Grafana evaluation are cluster behaviours; offline tests cover errors, absent telemetry predicates, pagination and recovery first.

The dev isolation profile has no cluster/forge credentials; unauthenticated
Gitea access returned 404. The cluster-admin profile is operator-selected only.
Do not claim private-forge live-read success without authenticated evidence.

Pre-merge evidence: the operator selected a separate cluster-admin isolation
workspace for read-only probes. Existing Secrets authenticated successfully to
both forges, verifying repo, branch, commit, status, PR and per-org token
contracts. Gitea's response uses `status`, unlike GitHub's `state`; the adapter
normalizes it with a regression test based on the observed schema. Candidate
deployment and Grafana provisioning remain post-merge obligations.

## Test Plan

Post-merge — operator-driven within this run's DevOps close-out:

1. Ensure tekton-extras and grafana-alerting actually applied the merge revision;
   assert the live CronJob/script content, not merely ArgoCD Synced status.
2. Load the Grafana provisioning changes using the documented restart/reload
   procedure. Assert both idle UIDs are absent through Grafana's API and all
   existing CI fault rules plus the three new delivery rules exist.
3. Observe a scheduled checker run using existing Secret mounts, verify no
   credential-bearing logs, and query the scraped timestamp/count/error gauges.
   Inspect any positive findings against the source/destination APIs.
4. Confirm healthy quiet refs/statuses yield zero overdue counts. Use the
   offline failure fixtures for deliberate missing/read-error/recovery cases;
   do not break live webhooks for verification. Record evidence on the linked
   acceptance rows and clear the DevOps gate only when deployment is verified.

## Acceptance scope

- `ci-quiet-no-idle-alert` (R1): inactivity cannot page; live verifies the user-visible notification policy.
- `ci-real-work-delivery` (R2,R3,R5): overdue real delivery warns and recovery clears it without synthetic work; live verifies the deployed outcome checker.
- `ci-delivery-checker-visible` (R4,R6): unreadable or stale observations cannot masquerade as healthy CI; live verifies the monitoring path, with offline fault scenarios before merge.

## Implementation Plans

| Plan | Repo | File | Depends on |
| --- | --- | --- | --- |
| 2026-10-14--cicd--actionable-alerts | `derio-net/frank` | `2026-10-14--cicd--actionable-alerts` | — |
