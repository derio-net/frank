# Actionable CI delivery alerts

## Scope

One agentic phase implements the operator's single ask: CI notifications indicate
failed real-work expectations rather than ordinary inactivity. It removes both
idle rules, compares expected mirror refs and forwarded statuses, and monitors
the checker. Existing CI fault rules stay available.

## Architecture

A five-minute read-only CronJob publishes complete bounded-cardinality snapshots
to the existing Pushgateway. It reuses the mirror-reconcile coverage and existing
forge tokens. Grafana warns on overdue work, failed reads, and missing/stale
checker snapshots. No synthetic CI events or forge writes are introduced.

## Verification

Behavioural fixture tests cover quiet, missed, delayed, recovered, unreadable and
paginated responses before merge. Authenticated read-only live probes verify the
API contracts when the cluster-admin access boundary has been settled. Production
deployment and Grafana provisioning are the spec's DevOps-gated post-merge Test
Plan, within this run rather than a deferred implementation issue.

## Acceptance

The phase links ci-quiet-no-idle-alert, ci-real-work-delivery, and
ci-delivery-checker-visible, tracing to R1–R6 in the spec. Live rows remain owed
until deployment is proven; offline tests provide pre-merge implementation evidence.
