# Scraping Frank's Own etcd — Control-Plane Observability

**Date:** 2026-08-03
**Layer:** `obs` (8) — Observability
**Status:** Designed — not deployed.
**Issue:** [frank#755](https://github.com/derio-net/frank/issues/755)
**Prompted by:** closing out the iGPU retrieval spike (#748 / #751 / #754). The
acceptance row `infer-igpu-workload-preserves-quorum` was recorded **PARTIAL**
because its strongest signal — etcd leader changes under load — could not be
measured at all.

## The problem, stated precisely

Frank's control plane is three mini PCs that are also the etcd quorum. Since
#748 those same machines run workloads: the retrieval tier pins to mini-1 and
claims its iGPU. So the question "does a warm inference workload disturb the
quorum?" is now a real operational question, and Frank cannot answer it.

More generally: **an etcd problem on this cluster is invisible until it becomes
an apiserver problem.**

## Verified state — measured 2026-08-03, not assumed

The issue's claims were re-verified from scratch before designing anything. Two
of them turned out to understate the problem.

| Fact | Result | How |
|---|---|---|
| Is there an etcd scrape job? | **No.** The `job` label carries 22 values; none is `kube-etcd`. | `GET /api/v1/label/job/values` on vmsingle |
| Do `etcd_server_*` series exist? | **No.** | `GET /api/v1/label/__name__/values?match[]={__name__=~"etcd_.*"}` |
| What `etcd_*` series *do* exist? | `etcd_request_duration_seconds`, `etcd_request_errors_total`, `etcd_requests_total`, `etcd_lease_object_counts`, `etcd_bookmark_counts` — **all apiserver storage-client metrics** | as above |
| Is `:2381` listening on the minis? | **No — connection refused on all three** | `wget http://192.168.55.2{1,2,3}:2381/metrics` from the vmagent pod |
| Does the chart already try to scrape etcd? | **Yes — and has for 148 days** | see below |
| Talos / Kubernetes | v1.12.6 / v1.35.3 | `kubectl get nodes -o wide` |

### The finding the issue did not have

`kubeEtcd.enabled` is **`true` by default** in `victoria-metrics-k8s-stack`, and
Frank's `values.yaml` never disables it. The objects are live right now:

```
service/…-kube-etcd     ClusterIP   None   2379/TCP   148d
endpoints/…-kube-etcd   <none>                        148d
vmservicescrape.operator.victoriametrics.com/…-kube-etcd
```

A headless Service on port 2379, a `VMServiceScrape` aimed at it, and an
`Endpoints` object that has been **empty since the cluster was built**. The
chart's Service selects pods labelled `component: etcd` — the kubeadm layout.
**Talos runs etcd as a host system service, not a pod**, so the selector can
never match. Zero endpoints, zero targets, zero series, and no error anywhere.

This matters for how the gap is described. It is not "we forgot to configure an
etcd scrape". It is "the scrape has been configured and inert since day one, and
nothing reports an empty Endpoints object as a fault". Same family as the
kube-state-metrics `maxScrapeSize` incident already written up in
`apps/victoria-metrics/values.yaml`: a limit or a selector silently yields
nothing, and the only symptom is an absence.

The `etcd_*` series that *do* exist are what made this survive 148 days. A
reasonable person greps for `etcd` in VMUI, finds `etcd_request_duration_seconds`,
and concludes etcd is monitored. Those are the **apiserver's client** to etcd,
not etcd. They tell you the apiserver's calls are slow; they cannot tell you
whether the quorum has a leader.

## Design

Two halves, in two different worlds.

### Half 1 — open the metrics listener (Talos ConfigPatch, operator-applied)

etcd serves `/metrics` on its client port (2379) behind mutual TLS, which would
require handing an etcd client certificate to a scraper — a certificate that also
grants full read/write to cluster state. That is rejected: the blast radius of
the credential dwarfs the value of the metric.

The supported alternative is etcd's dedicated metrics listener:

```yaml
cluster:
  etcd:
    extraArgs:
      listen-metrics-urls: http://0.0.0.0:2381
```

Plain HTTP, no auth, read-only, serves `/metrics` and `/health` only.

Delivered as a single Omni `ConfigPatch` scoped to the control-plane machine set,
mirroring the working example at `patches/phase13-auth/omni-configpatch.yaml`:

```yaml
metadata:
  namespace: default
  type: ConfigPatches.omni.sidero.dev
  id: 160-etcd-metrics-listener
  labels:
    omni.sidero.dev/cluster: frank
    omni.sidero.dev/machine-set: frank-control-planes
```

**Exposure decision (`d1-exposure`).** Binding `0.0.0.0` was chosen over per-node
LAN-IP patches and over a loopback-plus-proxy design. The LAN is already Frank's
trust boundary — the ArgoCD UI serves plain HTTP on `192.168.55.200` — the
listener carries no key material, and the alternatives cost either 3× the config
surface for a marginal gain, or a new DaemonSet standing between us and the very
signal we are adding in order to trust the control plane.

**This is operator work.** Applying it needs `omnictl` with the Omni service
account, and it restarts etcd on each control-plane node in turn. It is the plan's
**back-loaded manual phase** — the PR ships it unimplemented.

Rollback is deleting the ConfigPatch; etcd returns to serving metrics on 2379 only.

### Half 2 — point the scrape at it (GitOps, ArgoCD)

In `apps/victoria-metrics/values.yaml`:

```yaml
kubeEtcd:
  enabled: true
  endpoints:
    - 192.168.55.21   # mini-1
    - 192.168.55.22   # mini-2
    - 192.168.55.23   # mini-3
  service:
    port: 2381
    targetPort: 2381
  vmScrape:
    spec:
      endpoints:
        - port: http-metrics
          scheme: http
```

Supplying `endpoints:` switches the chart from selector-based discovery to a
**static `Endpoints` object**, which is what a host system service requires. The
`vmScrape.spec.endpoints` override fully replaces the chart default (which uses
`scheme: https` plus a ServiceAccount bearer token — both wrong for 2381).

Verified by rendering the chart locally at the pinned version 0.72.4: it emits a
headless Service on 2381, an `Endpoints` with the three mini IPs, and a
`VMServiceScrape` with `jobLabel: kube-etcd` — so the job appears as
`up{job="kube-etcd"}` with one series per node.

The three IPs are static and already the documented control-plane addresses
(`agents/rules/frank-infrastructure.md`, `patches/README.md`). Node IPs on Frank
are fixed by Talos machine config, so a static list is not a drift risk — but it
*is* a duplication, and the tripwire below asserts it against the repo's own
machine table.

**Ordering is safe in either direction.** If the values merge before the
ConfigPatch is applied, the target is simply down and the rules sit at `NoData`
with `noDataState: OK` — nothing fires. There is no generic "target down" pager
on Frank.

### Half 2b — the signals

Six rules in `apps/grafana-alerting/manifests/alert-rules-cm.yaml`, folder
`feature-health`, group prefix `layer-2-etcd-*` (Layer 2 is where Frank's
control-plane rules already live), in the established 3-step A→B→C SSE form (a
bare classic-condition fails with `sse.parseError` on Grafana 12.x).

| Rule | Query | Threshold | `for:` | Severity | Route |
|---|---|---|---|---|---|
| etcd quorum has no leader | `etcd_server_has_leader` | `lt 1` | 10m | critical | Telegram + health-bridge |
| etcd member down | `up{job="kube-etcd"}` | `lt 1` | 10m | critical | Telegram + health-bridge |
| **etcd scrape absent** | `absent(up{job="kube-etcd"})` | `gt 0` | 15m | critical | health-bridge only |
| etcd leader-change churn | `increase(etcd_server_leader_changes_seen_total[1h])` | `gt 3` | 0m | warning | health-bridge only |
| etcd WAL fsync slow | `histogram_quantile(0.99, sum by (le, instance) (rate(etcd_disk_wal_fsync_duration_seconds_bucket[5m])))` | `gt 0.05` | 15m | warning | health-bridge only |
| etcd DB size vs quota | `etcd_mvcc_db_total_size_in_bytes / etcd_server_quota_backend_bytes` | `gt 0.8` | 15m | warning | health-bridge only |

**Routing decision (`d2-routing`).** Only quorum loss pages. Everything else
carries `health_bridge_only: "true"`, which the notification policy routes to the
Health Bridge Webhook and keeps off Telegram — an existing, deliberate escape
hatch (first user: `vk-executor-pool-wedged`).

**The scrape-absent rule exists because this spec would otherwise recreate the
bug it is fixing.** Every rule here uses `noDataState: OK`, so if the Endpoints
object ever empties again — a chart bump changing the selector, a values merge
dropping `endpoints:`, a node IP change — the `up{job="kube-etcd"}` series simply
vanish, every rule goes NoData, every rule reads OK, and Frank is blind to etcd
again with a green dashboard. The CI tripwire guards the repo's config; nothing
guards the live cluster against the same silent absence. `absent()` is the only
expression that fires *on the disappearance of a series*, and it is already the
idiom Frank uses for its canary watchdogs.

It is `severity: critical` **plus** `health_bridge_only: "true"` deliberately:
health-bridge's dead→bug-issue lifecycle requires critical, and the notification
policy's generic escape-hatch route keeps critical-for-the-bridge alerts off
Telegram. So a blind scrape becomes a tracked bug that auto-closes on heal,
without paging — consistent with Frank's standing "blindness is not death"
posture. `for: 15m` so a vmagent restart or a rolling etcd apply cannot trip it.

The `for: 10m` on the two critical rules is the load-bearing part. A planned
Talos rolling reboot takes one etcd member down and elects a new leader, entirely
legitimately; the 2026-08-02 control-plane roll produced **48 alerts against a
completely healthy cluster** and is the precedent this design is built to avoid
repeating. The roll itself took roughly 7 minutes, so 10m clears it with margin.

Two constraints inherited from existing gotchas:

- **No `<`, `>` or `&` in annotations.** Grafana's Telegram contact point sends
  HTML `parse_mode`; a bare angle bracket makes Telegram reject the message with
  400 and the alert fires but silently never delivers.
- `noDataState: OK`, `execErrState: Error` — matching every neighbouring rule, so
  a blind scrape reads as blindness (health-bridge caps synthetic
  `DatasourceError`/`NoData` at `degraded`) rather than as death.

Thresholds are deliberately loose first-pass values: 50 ms WAL fsync p99 is the
widely-cited etcd health boundary, and Frank's minis are NVMe-backed, so this
should sit far below it. They are documented as provisional in the runbook, to be
tightened once the dashboard has baseline.

### Half 2c — the dashboard (`d3-dashboard`)

A provisioned ConfigMap `apps/grafana-alerting/manifests/etcd-dashboard-cm.yaml`
with five panels: `etcd_server_has_leader` per node, leader changes/1h, WAL fsync
p99, DB size against quota, and peer round-trip p99. Mounted via
`extraConfigmapMounts` exactly like the existing feature-health / blog-edge /
secure-agent-pod boards.

The chart's `defaultDashboards` etcd board was rejected: it is upstream-shaped,
and every other dashboard on Frank is a curated ConfigMap.

The panels are not decoration — they are where the acceptance re-run's
before/under-load evidence lives. Without them the promoted row has no durable
home beyond a paragraph of prose.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|-----------|
| 2026-08-03--obs--etcd-scrape-control-plane | `derio-net/frank` | `2026-08-03--obs--etcd-scrape-control-plane` | — |

## Rejected alternatives

| Alternative | Why not |
|---|---|
| Scrape 2379 with an etcd client certificate | The cert grants full etcd read/write. Hand-managing it in SOPS to obtain a latency histogram inverts the risk/benefit, and rotation becomes a new silent-failure surface. |
| Per-node LAN-IP `listen-metrics-urls` | 3× the ConfigPatches for a marginal gain — the LAN NIC is the exposed interface either way. |
| Loopback + hostNetwork proxy DaemonSet | Genuinely tighter, but interposes a new workload and a new failure mode in front of the control-plane signal. |
| Talos ingress firewall to restrict 2381 | `NetworkRuleConfig` is only meaningful with `NetworkDefaultActionConfig: block`, which then demands explicit rules for kubelet, apid, trustd, etcd peer, Cilium health and more. Far too large a blast radius for this scope. |
| Enable the chart's `defaultDashboards` etcd board | Upstream-shaped; inconsistent with Frank's hand-curated dashboards. |

## Tripwire (CI, `scripts/tests/test_etcd_scrape.py`)

`scripts/tests/` runs on every PR via `.github/workflows/repo-tripwires.yml`. The
guard asserts the two halves cannot drift apart, because they live in different
files and nothing else connects them:

1. The ConfigPatch's `listen-metrics-urls` port equals `kubeEtcd.service.targetPort`.
   *A port mismatch is exactly the silent-empty-Endpoints failure again.*
2. `kubeEtcd.endpoints` equals the control-plane IPs in `agents/rules/frank-infrastructure.md`.
3. `kubeEtcd.vmScrape` uses `scheme: http` and carries **no** bearer token —
   the chart default would produce a permanently failing target.
4. The ConfigPatch is scoped to `omni.sidero.dev/machine-set: frank-control-planes`
   (a fleet-wide etcd patch would be applied to workers, which run no etcd).
5. Every new alert rule exists, is in folder `feature-health`, uses the 3-step
   A→B→C shape, and references an `etcd_server_*` / `etcd_disk_*` / `etcd_mvcc_*`
   metric — **not** an `etcd_request_*` metric. *That last one is the whole point:
   it fails if someone "fixes" a rule by pointing it at the apiserver-client
   series that already exist.*
6. No `<`, `>` or `&` in any new annotation (Telegram HTML-400 guard).
7. The two paging rules carry `for:` ≥ 10m; every non-paging rule carries
   `health_bridge_only: "true"`.
8. The `absent(up{job="kube-etcd"})` watchdog exists and its selector's `job`
   value matches the one the chart actually renders (`kube-etcd`, from the
   Service's `jobLabel`). *A watchdog watching the wrong job name is a watchdog
   that can never fire — the same class of defect as the empty Endpoints object.*

## Test Plan

Post-merge, operator-driven. Steps 1–2 are the manual phase; 3–6 produce the
acceptance evidence (`d4-testplan`).

1. **Apply the ConfigPatch.** `omnictl apply -f patches/phase08-obs/omni-configpatch-etcd-metrics.yaml`
   (needs `source .env_devops` for the Omni service account, and `source .env`
   from the repo root for the relative `TALOSCONFIG`). Watch the rolling etcd
   restart **one node at a time**, asserting quorum between nodes:
   `talosctl -n <ip> etcd status` — 3 members, one leader, before moving on.

   *Not exercised during design:* `talosctl` against Frank goes through Omni and
   requires operator credentials this session did not hold — the command timed
   out at the auth step. The `omnictl` binary is present and the machine-set
   scoping is copied from a patch that demonstrably landed (phase13-auth,
   PR #742), but the apply itself is unverified here by construction. It is the
   manual phase for exactly that reason.
2. **Confirm the listener.** From the vmagent pod:
   `wget -qO- http://192.168.55.2{1,2,3}:2381/metrics | head` returns etcd metrics
   on all three.
3. **Confirm the scrape.** `up{job="kube-etcd"}` returns **3 series, all 1**, and
   `etcd_server_has_leader` / `etcd_disk_wal_fsync_duration_seconds_bucket` /
   `etcd_mvcc_db_total_size_in_bytes` exist in VMSingle.
4. **Confirm the rules evaluate.** All five rules are `Normal`, not `NoData` and
   not `Error`, in Grafana's rule list; the etcd dashboard renders data in all
   five panels.
5. **Baseline (60 s idle):** record `etcd_server_leader_changes_seen_total`,
   `etcd_server_has_leader`, WAL fsync p99, and apiserver p99
   (**excluding `verb=~"WATCH|CONNECT"`** — unfiltered it reads a flat 60 s,
   the apiserver's long-poll timeout, and swamps the quantile).
6. **Re-run the soak:** 7500 rerank requests over 240 s from mini-1, matching the
   2026-08-03 measurement. Capture the same four signals under load, then rewrite
   `infer-igpu-workload-preserves-quorum`'s notes with the before/under-load
   numbers — or record honestly why it still cannot be met.

   **On what "promote" means here.** `fr acceptance` accepts only
   `ci | scheduled | skipped | not-implemented | failing`; there is no `manual`
   status. The repo's established convention for a row proved by live operator
   measurement is `status: skipped` with the evidence in `notes:` — see
   `gpu1-usb-25g-node-ip-stable` ("Live manual proof 2026-07-11 …"). So the row's
   *status* does not change. What changes is that its notes stop saying
   **"NOT VERIFIABLE: etcd leader changes and WAL fsync — Frank does not scrape
   etcd"** and start carrying numbers. That sentence being deletable is the whole
   deliverable; treating a status flip as the goal would be measuring the wrong
   thing. Status flips are hand-edits followed by `fr acceptance report
   --deterministic` (`add` is append-only, and there is no `set`).

## Acceptance rows

Presented for approval with the spec review — see §"Acceptance rows presented"
in the review section of the journal.

| Row | Claim | Status at merge |
|---|---|---|
| `obs-etcd-server-metrics-scraped` | Frank scrapes its own etcd, so an etcd fault is visible before it becomes an apiserver fault. | `not-implemented` → `skipped` with live evidence after Test Plan step 3; unit guard in CI |
| `obs-etcd-quorum-loss-pages` | Loss of etcd quorum reaches the operator, while routine control-plane maintenance does not. | `not-implemented`; unit guard covers the routing wiring, the live half needs a quorum event |
| `obs-etcd-blindness-is-tracked` | If the etcd scrape ever goes silent again, that silence is itself detected rather than reading as health. | `not-implemented` → evidenced by the `absent()` watchdog firing on a deliberate scrape pause |
| `infer-igpu-workload-preserves-quorum` | *(existing row)* A warm inference workload pinned to a control-plane mini leaves etcd quorum and API-server latency unchanged. | stays `skipped`; notes rewritten from "NOT VERIFIABLE" to measured numbers by the Test Plan |

## What this does not do

- It does not add etcd **backup** verification — that is Layer 9's territory.
- It does not alert on etcd peer-network partition beyond round-trip latency on
  the dashboard; a partition shows up as leader churn or quorum loss, which are
  covered.
- It does not tighten `apiserver_request_duration_seconds` alerting. Worth noting
  for whoever does: p99 reads a flat 60 s unless `verb=~"WATCH|CONNECT"` is
  excluded. Do not build an alert on the unfiltered version.
