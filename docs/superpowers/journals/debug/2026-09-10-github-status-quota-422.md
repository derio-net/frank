# Journal: 2026-09-10-github-status-quota-422

<!-- fr:journal kind=repro scope=debug id=86cd0d16f820 created=2026-09-10T08:08:21 -->
### 86cd0d16f820 · repro · 371 Failed pods: 292 are real stoa-status-bridge failures, 96/day

Cluster shows 371 pods phase=Failed. The discriminator is (reason, has-IP):

- 293 reason=NONE, ip=yes  -> 292 stoa-status-bridge-*-forward-pod = REAL failures
-  68 reason=Terminated, ip=none -> node-shutdown tombstones (benign)
-  10 reason=DeadlineExceeded, ip=none -> stale kid-laptops-ci (GC-uncovered)

Repro (read-only; KUBECONFIG is a RELATIVE path in .env, so run from repo root):
    kubectl get pods -A -o json | jq -r '.items[] | select(.status.phase=="Failed") | "reason=\(.status.reason // "NONE") ip=\(if .status.podIP then "yes" else "none" end)"' | sort | uniq -c

All 292 show step-report exit=1 reason=Error, created at :00:09/:00:16 and
:30:09/:30:16 -> 2 pods per 30 min = 96/day, retained ~3 days by the TTL GC.

<!-- fr:journal kind=ruled-out scope=debug id=213a9d54d4d6 created=2026-09-10T08:08:22 -->
### 213a9d54d4d6 · ruled-out · NOT graceful-node-shutdown tombstones (the standing gotcha)

frank-gotchas.md says a flood of 0/1 Error pods that never restart are
graceful-node-shutdown tombstones. Applied blind here it gives the wrong verdict.

Refuted by two fields the 'kubectl get pods' display column hides:
- tombstones have status.podIP == null and status.reason == Terminated with
  message 'Pod was terminated in response to imminent node shutdown'
- the 292 stoa-status-bridge pods have REAL pod IPs and NO reason -> they were
  scheduled, ran, and exited non-zero.

68 genuine tombstones DO exist in the same listing (mini-1 x37, mini-2 x15,
mini-3 x12, raspi x4), which is exactly what makes the misdiagnosis tempting.

<!-- fr:journal kind=ruled-out scope=debug id=2305ff4e54e0 created=2026-09-10T08:08:24 -->
### 2305ff4e54e0 · ruled-out · NOT a broken PipelineRun TTL GC

The GC OOM incident (#723) made 'garbage accumulating' look like a GC failure.
Refuted: last run reported
    pipelinerun-ttl-gc result deleted=99 remaining=428 cutoff=2026-09-07T04:30:01Z
It deleted 99 against ~96 minted/day. The GC is healthy and merely breaking even.

Separate latent gap noted, NOT this bug: the CronJob is scoped -n tekton-pipelines,
so kid-laptops-ci (13 PipelineRuns) has no GC coverage -> its DeadlineExceeded pods
from 2026-07-27..08-01 persist.

<!-- fr:journal kind=root-cause scope=debug id=72e09b59d101 created=2026-09-10T08:08:41 -->
### 72e09b59d101 · root-cause · github-status Task fails the step on a permanently-unactionable 422 quota error

GitHub caps commit statuses per (SHA, context). agentic-stoa/cnc-fr main has
been frozen at af90148b since 2026-07-23 (49 days), while a Gitea Actions
'pins-update' workflow fires every 30 min against that same static SHA. Each run
forwards a status through stoa-status-bridge, so the pair (af90148b,
'gitea-actions/pins-update / pins (push)') accumulated ~900 statuses -- every other
context on that commit has 16 -- until the cap was reached.

GitHub now answers every write:
  HTTP 422 {"errors": "Validation failed: This SHA and context has reached the
  maximum number of statuses."}

apps/tekton/tasks/github-status.yaml ends its step script with
    [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]
under 'sh -e', so ANY non-2xx fails the step. That is correct for a transient
error and WRONG for this one: the quota is spent permanently, so no retry can
ever succeed. Result: one dead pod every 30 minutes, forever (96/day).

X because Y: the pods fail because the Task cannot distinguish 'retry might work'
from 'this request can never succeed'.

Two consequences:
1. The 'pins' context on cnc-fr main is stranded at 'pending' since
   2026-08-02T06:00:15Z -- the last write that fit under the cap. Commit statuses
   have no lifecycle and nothing reconciles them. Same consequence as the
   skipped/warning vocabulary incident, reached by a different mechanism.
   Blast radius limited: CI_AUTHORITY=gitea, so GitHub statuses are informational.
2. The TTL GC now exists largely to sweep up after this (deleted=99/day).

<!-- fr:journal kind=finding scope=debug id=60b964c2141c created=2026-09-10T08:14:33 state=fixed -->
### 60b964c2141c · finding [fixed] · Tolerate ONLY the quota-exhausted 422 in github-status; pin both directions with an executing tripwire

Source change: apps/tekton/tasks/github-status.yaml

Before the final 2xx assertion, the step now checks for the one 422 that can
never be retried and exits 0 with a WARN, leaving every other non-2xx fatal:

    if [ "$HTTP_CODE" -eq 422 ] && grep -q 'maximum number of statuses' /tmp/resp; then
      echo "WARN: status quota exhausted for ${REVISION} / ${CONTEXT}"
      ...
      exit 0
    fi
    [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]

(grep returning 1 inside an if-condition is exempt from 'sh -e', so the guard is
safe under the step's existing flags.)

Test pinning it: scripts/tests/test_github_status_quota_422.py -- 9 cases. It
EXTRACTS the real step script from the Task YAML and EXECUTES it under /bin/sh
against a stubbed curl, rather than grepping the manifest for a string, because
a textual assertion passes on an implementation that mentions the message and
still exits 1.

Both directions are guarded, and the second matters more:
  - test_quota_exhausted_422_is_not_fatal  -> the fix
  - test_other_422_still_fails             -> the skipped/warning vocabulary 422
                                              must STAY fatal
  - test_other_errors_still_fail (401/404/500/502), test_success_still_passes

Test-authoring defect caught in the red phase and worth recording: the first
draft of test_quota_exhausted_422_is_loud accepted the substring 'maximum number
of statuses', which the script already cat's from the response body -- so it went
GREEN while the bug was present and could not distinguish a loud implementation
from a silent one. A passing assertion inside a red suite is a bug in the
assertion. Narrowed to a step-authored marker ('quota').

NOT fixed here (deliberately, operator-chosen scope):
  - The upstream cause: agentic-stoa/cnc-fr's 'pins-update' workflow firing every
    30 min against a static HEAD. That is a third-party repo; this fix stops the
    dead pods but not the ~48 pipeline runs/day.
  - The stranded 'pending' on cnc-fr main -- unrecoverable by retry; the context's
    status budget is permanently spent.
  - pipelinerun-ttl-gc is scoped -n tekton-pipelines, so kid-laptops-ci has no GC
    coverage (10 DeadlineExceeded pods from 2026-07-27..08-01 persist).
  - 68 node-shutdown tombstones: cosmetic, 'kubectl delete pod' whenever.
