# CI delivery checker closeout: equivalent target URLs warn

Date: 2026-10-14. Feature: PR #869, merge `5ac6e0bd6a4f817440c3693283dce0f16dd2577f`.
Run: `2026-10-14-feat-ci-actionable-alerts`.

## Verdict

Deployment and provisioning are verified, but the DevOps gate remains open.
The deployed checker reports 22 overdue status deliveries across six repositories
whose statuses were delivered correctly. Gitea's status API returns relative
target URLs; GitHub's status API returns equivalent absolute URLs. Literal URL
comparison makes these healthy outcomes warn.

## Deployment evidence

- `fr isolation verify-merge --branch feat/ci-actionable-alerts` confirmed the
  changes on `origin/main` and the merged PR.
- Initially `tekton-extras` reported Synced with an old last-operation revision
  (`63537c701a6329d3b4a2a6dc8ed4effcbb5e2ae6`), and the CronJob was absent.
  An operator-authorized explicit HEAD sync, with `ServerSideApply=true` and
  `RespectIgnoreDifferences=true`, succeeded and created the checker.
- The live CronJob runs every five minutes, mounts the existing three forge
  Secrets, uses non-root execution, and has a 270-second Job deadline.
- Live `check.py` SHA256 equals the merged artifact:
  `6ab62a1e240cd4a1056cb431c339482dbc6b17c441fea19f12a07fc2df7626fc`.
- Live `grafana-alerting-rules` provisioning SHA256 equals the merged artifact:
  `64fa6515ac843b7ccd36909545381380897045e1ab2c7c62556aaf21565d3d3b`.
- Grafana was restarted using the documented deployment rollout procedure;
  rollout completed. Authenticated `/api/v1/provisioning/alert-rules` returned
  60 stored rules. Both retired idle UIDs were absent. All nine expected
  Layer 25 rules, including the three delivery rules and six retained fault
  rules, were present.
- The authenticated Grafana rules evaluation API at 19:43:30Z reported all
  three delivery rules with `health: ok` and no evaluation errors. The overdue
  rule was firing on the false positives; read-error and stale-snapshot rules
  were inactive.

## Scheduled execution and scrape

Scheduled Jobs `ci-delivery-check-29866765` and `ci-delivery-check-29866770`
completed successfully at 19:25:25Z and 19:30:24Z respectively. The latter's
logs contained bounded status-mismatch diagnostics. An in-memory comparison
against all three mounted Secret token values found none in those logs;
credentials were not printed or persisted.

An authenticated query through Grafana's VictoriaMetrics datasource proxy
returned 37 current series: 24 overdue gauges, 12 read-error gauges, and one
completed-check timestamp. The timestamp was 249 seconds old at observation.
All read-error and mirror-overdue gauges were zero. Status overdue counts:

| Repository | Count |
| --- | ---: |
| agentic-stoa/cnc-fr | 1 |
| agentic-stoa/cnc-frd | 9 |
| agentic-stoa/cnc-fru | 5 |
| agentic-stoa/hermes-brain | 1 |
| agentic-stoa/second-brain | 4 |
| agentic-stoa/site | 2 |

The other six monitored repositories had zero status-overdue counts.

## Authenticated source/destination comparison

Read-only probes authenticated to both forge APIs with existing Secrets,
paginated the deployed repository scope, and reproduced the exact counts above
with no read errors. Every one of the 22 findings had a destination status;
state and description matched. Only target URL representation differed.

Example on `agentic-stoa/cnc-fr` main, SHA prefix `501073c23d48`:

- Gitea: `/agentic-stoa/cnc-fr/actions/runs/3939/jobs/0`
- GitHub: `http://192.168.55.209:3000/agentic-stoa/cnc-fr/actions/runs/3939/jobs/0`
- Source status time: 04:17:24Z; destination status time: 04:17:31Z.

The read-only probe repeated comparison against the same cached API responses
with relative Gitea targets resolved against the Gitea origin. All 12
repositories then had zero overdue mirror and status counts and zero read
errors. This was an isolated diagnostic comparison, not a deployed fix; it
performed no forge writes or metric publication.

## Offline evidence and remaining work

The existing checker and outcome-alert fixture suites passed: **79 passed**.
They cover missing delivery, read failures, pagination, grace periods and
recovery, but miss this real relative/absolute URL contract.

Required correction: resolve legitimate relative Gitea target URLs against the
configured Gitea origin before comparison, preserving rejection of genuinely
different targets and preserving empty URLs. Add a regression fixture based
on this observed API pair. Deploy the correction and observe scheduled
snapshots returning zero for these healthy statuses before clearing the gate
and archiving the original plan.

Test Plan steps 1–3 ran. Step 4 remains owed because healthy statuses currently
produce warnings. The original spec and plan remain active.
