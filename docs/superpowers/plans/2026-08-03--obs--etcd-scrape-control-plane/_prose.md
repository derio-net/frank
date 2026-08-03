# Scraping Frank's Own etcd

**Spec:** `docs/superpowers/specs/2026-08-03--obs--etcd-scrape-control-plane-design.md`
**Issue:** frank#755
**Layer:** `obs` (8) — Observability
**Status:** In Progress — phases 1-4 complete; phase 5 pending operator apply (task 1 is a PRE-MERGE gate, tasks 2-3 are post-merge evidence)

## What this fixes

Frank's control plane is three mini PCs that are also the etcd quorum, and since
the iGPU retrieval work those machines run workloads. The acceptance row
`infer-igpu-workload-preserves-quorum` asks whether a warm inference workload
disturbs the quorum, and its strongest signal — etcd leader changes — cannot be
measured, because Frank does not scrape etcd.

The interesting part is *why* it doesn't. `kubeEtcd.enabled` is `true` by chart
default and was never disabled. A headless Service, a `VMServiceScrape` and an
`Endpoints` object have all existed since the cluster was built — the Endpoints
object empty the entire time, because the chart selects pods labelled
`component: etcd` and Talos runs etcd as a host system service. 148 days of
configuration that looked complete, produced no error, and yielded no data.

This is the same failure family as the kube-state-metrics `maxScrapeSize` drop
already written up in `apps/victoria-metrics/values.yaml`: something silently
yields nothing, and the only symptom is an absence.

## Shape of the work

Two halves that live in different worlds, plus the guard that keeps them
together.

**Half one** is a Talos ConfigPatch opening etcd's dedicated metrics listener on
`0.0.0.0:2381` — plain HTTP, read-only, no key material. Applied through Omni to
the control-plane machine set. This is operator work: it needs the Omni service
account and it restarts etcd on each control-plane node in turn.

**Half two** is chart values pointing a static `Endpoints` object at the three
mini IPs, six Grafana alert rules, and a five-panel dashboard. All GitOps, all
agentic.

They are connected by nothing except a port number in two files applied by two
different tools. The tripwire in phase 1 task 3 is the only thing that will ever
notice if they drift, which is why it is written as a derivation (parse the port
out of the ConfigPatch URL, parse the IPs out of the machine table) rather than
as a third hardcoded copy.

## Ordering: the manual phase is a PRE-MERGE gate, not a back-loaded one

This plan was written believing the opposite — that the GitOps half was "inert
but harmless before the ConfigPatch lands: the target is simply down, and every
rule sits at `NoData` with `noDataState: OK`, so nothing fires". **That is
false**, and code review caught it before the PR opened.

`up` is not a series etcd exports. The scraper synthesises one **per configured
target**, `1` on a successful scrape and `0` on a failed one; it is never
*absent* while the target is configured. And supplying `kubeEtcd.endpoints` is
precisely what creates targets — the chart drops its pod selector and renders a
static `Endpoints` object with three addresses. So the instant ArgoCD syncs the
values block, vmagent has three targets dialling a port that is
connection-refused, and they sit at **`up=0`, not NoData**.
`layer-2-etcd-member-down` is `up < 1` at `for: 10m`, critical, with no
`health_bridge_only` — so it fires ten minutes after the merge and, on the
notification policy's root `repeat_interval: 3m`, pages Telegram every three
minutes, three instances at a time, against a perfectly healthy quorum.

Frank already contains a live instance of the shape: `count(up==0) by (job)`
returns `{job="kube-scheduler"} 3`, and `max_over_time(up{job="kube-scheduler"}[90d])`
is 0 on all three. Populated Endpoints, a scrape that then fails on TLS/auth
against 10259, and `up=0` — not NoData — for the entire retention window.

So phase 5 task 1 (apply the patch, confirm the listener) runs **before** the PR
merges; tasks 2 and 3 stay post-merge. The fix is the ordering rather than a
looser rule, because the ConfigPatch is harmless standalone: it opens a
read-only metrics port that nothing is yet scraping. De-fanging the paging rules
instead would buy the same quiet by discarding the signal this plan exists to
add.

The same asymmetry governs rollback — deleting the ConfigPatch alone leaves the
`Endpoints` object in place, so `up` reads 0 rather than disappearing, the
member-down rule pages, and the `absent()` watchdog stays silent. A real
rollback reverts both halves.

## The rule that exists because of code review

Five rules were designed; six are being built. Every rule uses
`noDataState: OK`, matching its neighbours and correct in isolation — but that
means if the Endpoints object ever empties *again* (a chart bump changing the
selector, a values merge dropping `endpoints:`, a node IP change) the
`up{job="kube-etcd"}` series vanish, every rule goes NoData, every rule reads OK,
and Frank is blind to etcd behind a green dashboard.

The fix would have reproduced its own bug one layer up. `absent()` is the only
expression that fires on a series *disappearing*, so rule six is
`absent(up{job="kube-etcd"})` at `severity: critical` plus
`health_bridge_only: "true"` — a tracked bug that auto-closes on heal, without
paging.

Phase 2 task 2 then asserts the watchdog selects the job name the chart actually
renders. A watchdog watching the wrong name is a watchdog that can never do its
job, which would be the same defect a third time.

## What only pages

Only quorum loss. `etcd_server_has_leader == 0` and `up{job="kube-etcd"} < 1`
reach Telegram, both with `for: 10m`. Leader-change churn, WAL fsync p99, DB size
against quota and the absent-watchdog all carry `health_bridge_only: "true"`.

The 10m window is the load-bearing number. A planned Talos rolling reboot
legitimately takes an etcd member down and elects a new leader; the 2026-08-02
control-plane roll produced 48 alerts against a completely healthy cluster and
took roughly 7 minutes. An etcd alert that fires on every planned roll would be
muted within a month, and a muted alert is worse than no alert because it looks
like coverage.

## Thresholds are provisional

50ms WAL fsync p99 is the widely-cited etcd boundary and Frank's minis are
NVMe-backed, so the real values should sit far below it. 3 leader changes/hour
and 80% of backend quota are similarly conventional. They are documented as
first-pass values to be tightened once the dashboard has a baseline — stated
plainly rather than presented as tuned.
