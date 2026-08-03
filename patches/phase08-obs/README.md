# Phase 08 — Observability: etcd metrics listener

Opens etcd's dedicated metrics listener on the control-plane machine set, so
Frank can scrape its own etcd. Applied to the three minis via Omni.

Design spec:
`docs/superpowers/specs/2026-08-03--obs--etcd-scrape-control-plane-design.md`

## Files

- `omni-configpatch-etcd-metrics.yaml` — the authoritative Omni ConfigPatch. Sets
  `cluster.etcd.extraArgs.listen-metrics-urls: http://0.0.0.0:2381`, scoped to
  `omni.sidero.dev/machine-set: frank-control-planes`.

## Why this exists

Frank did not scrape its own etcd for 148 days, and the reason was not a missing
config — it was a config that had been present and inert since day one.
`kubeEtcd.enabled` is `true` by chart default in `victoria-metrics-k8s-stack`,
so a headless Service, a `VMServiceScrape` and an `Endpoints` object all existed
from the day the cluster was built. The `Endpoints` object was **empty** that
entire time: the chart's Service selects pods labelled `component: etcd` (the
kubeadm layout) and **Talos runs etcd as a host system service, not a pod**.
Zero endpoints, zero targets, zero series, and no error anywhere.

An etcd problem on this cluster was therefore invisible until it became an
apiserver problem. Full write-up, including why the `etcd_*` series that *do*
exist in VMSingle are the apiserver's storage client and not etcd:
`docs/runbooks/frank-gotchas/grafana.md`.

## Why `0.0.0.0` and why plain HTTP

etcd serves `/metrics` on its client port (2379) behind **mutual TLS**. Scraping
there means handing a scraper an etcd client certificate — a credential that also
grants full read/write to all cluster state, and whose rotation becomes a new
silent-failure surface. The blast radius of that credential dwarfs the value of a
latency histogram.

`listen-metrics-urls` is etcd's supported alternative: a dedicated listener that
serves `/metrics` and `/health` **only**, read-only, carrying no key material.

Binding `0.0.0.0` rather than three per-node LAN IPs is a deliberate trade
(spec decision `d1-exposure`). The LAN is already Frank's trust boundary — the
ArgoCD UI serves plain HTTP on `192.168.55.200` — and the LAN NIC is the exposed
interface either way, so the per-node variant costs 3x the config surface for no
real gain. A loopback-plus-proxy DaemonSet would be genuinely tighter, but it
interposes a new workload and a new failure mode directly in front of the
control-plane signal this layer exists to trust.

## The other half of the change

This patch is one of two files that must agree, and **nothing but the port number
connects them**:

| File | Applied by | What it does |
|---|---|---|
| `patches/phase08-obs/omni-configpatch-etcd-metrics.yaml` | `omnictl`, by an operator, out of band | opens `0.0.0.0:2381` on the control planes |
| `apps/victoria-metrics/values.yaml` (`kubeEtcd`) | ArgoCD, from `main` | points a **static** `Endpoints` object at the three minis on 2381 |

A port typo in either reproduces exactly the silent empty-target failure above,
so `scripts/tests/test_etcd_scrape.py` derives the port out of this file's URL
and asserts it against `kubeEtcd.service.targetPort` — and derives the three
control-plane addresses out of `agents/rules/frank-infrastructure.md` rather
than restating them.

## Ordering: this patch is a PRE-MERGE gate

**Apply this patch BEFORE the PR carrying the `kubeEtcd` values block merges.**

An earlier draft of this file said the opposite — "ordering is safe in either
direction; before the patch the target is simply down and every rule sits at
`NoData` with `noDataState: OK`". That is wrong, and the mechanism matters:

**`up` is not a series etcd exports. The scraper synthesises it for every
configured target — `1` on a successful scrape, `0` on a failed one — and it is
never *absent* while the target is configured.** Supplying `kubeEtcd.endpoints`
is exactly what creates targets: the chart drops its pod selector and renders a
static `Endpoints` object with three addresses. So the moment ArgoCD syncs the
values block, vmagent has three targets dialling a port that is
connection-refused, and they sit at **`up=0`, not NoData**.

`layer-2-etcd-member-down` is `up{job="kube-etcd"} < 1`, `for: 10m`,
`severity: critical`, with no `health_bridge_only` label. It therefore fires ten
minutes after the sync, and the notification policy's root `repeat_interval: 3m`
pages Telegram every three minutes, three instances at a time, against a
perfectly healthy quorum — until this patch is applied.

Frank already contains a live instance of this shape. `kube-scheduler` has three
*populated* Endpoints (Talos runs it as a static pod, so the chart's selector
works) and a scrape that then fails on TLS/auth against 10259:

```text
count(up==0) by (job)                         ->  {job="kube-scheduler"}  3
max_over_time(up{job="kube-scheduler"}[90d])  ->  0, 0, 0
```

Not NoData. `up=0`, for the whole retention window.

Applying this patch first costs nothing — it opens a read-only metrics port that
nothing is yet scraping, and changes no other behaviour — and it makes the scrape
come up healthy on the very first sync instead of alarming.

## Application

See the manual-operation block below. It runs **before** the GitOps half merges
(see "Ordering" above). In short:

```bash
source .env && source .env_devops
omnictl apply -f patches/phase08-obs/omni-configpatch-etcd-metrics.yaml
```

It triggers a rolling **etcd restart** on each control-plane node in turn. Watch
the roll one node at a time and assert quorum *between* nodes, not after all
three.

## Rollback — revert BOTH halves, or the rollback is a pager

**A rollback is two changes, in this order:**

1. revert the `kubeEtcd` block in `apps/victoria-metrics/values.yaml` (git, via
   ArgoCD) — this removes the static `Endpoints` object and therefore the targets;
2. then delete the ConfigPatch:

```bash
source .env_devops
omnictl delete configpatch 160-etcd-metrics-listener
```

**Deleting the ConfigPatch alone is NOT quiet, despite what an earlier draft of
this file claimed.** The `Endpoints` object survives, so the three targets survive
— they just stop answering. `up` goes to **`0`**, not absent:

- `layer-2-etcd-member-down` (`up < 1`, `for: 10m`, critical, pages) **fires**,
  and repeats to Telegram every 3 minutes;
- `absent(up{job="kube-etcd"})` stays **empty**, because the series is still
  there at value 0 — so `layer-2-etcd-scrape-absent`, the watchdog whose whole
  job is to notice blindness, never fires;
- the five `etcd_server_*` / `etcd_disk_*` / `etcd_mvcc_*` rules do go NoData and
  do read OK.

So the half of the alerting that should stay quiet pages, and the half that
should speak up stays silent. Reverting the values block first removes the
targets, at which point `up` genuinely disappears, `absent()` fires, and the
blindness is recorded as blindness — which is the intended behaviour for a
deliberate rollback.

## Manual operation

The `omnictl` apply cannot be GitOps: Omni is outside the cluster, the apply
needs the Omni service-account credential, and it restarts etcd on the machines
that hold the quorum.

The block below is the **runbook source of truth for the apply as executed**, and
an identical copy lives in the plan phase file
`docs/superpowers/plans/2026-08-03--obs--etcd-scrape-control-plane/05.yaml` —
`/sync-runbook` scans only `docs/superpowers/plans/`, so a block written *only*
here would never reach `docs/runbooks/manual-operations.yaml`. The two copies are
asserted identical by `scripts/tests/test_etcd_scrape.py`; edit both or neither.

```yaml
# manual-operation
id: obs-etcd-metrics-listener-apply
layer: obs
app: victoria-metrics
plan: docs/superpowers/plans/2026-08-03--obs--etcd-scrape-control-plane
when: "BEFORE the PR carrying the kubeEtcd block in apps/victoria-metrics/values.yaml is merged. This is a pre-merge gate, not a post-merge follow-up. `up` is synthesised by the scraper for every configured target and reads 0 on a failed scrape, never absent — so merging first hands vmagent three targets dialling a refused port, and layer-2-etcd-member-down (up lt 1, for 10m, critical, no health_bridge_only) pages Telegram every 3 minutes against a perfectly healthy quorum. Rollback reverts BOTH halves for the same reason."
why_manual: "Omni lives outside the cluster and the apply needs the Omni service-account credential, so it cannot be driven by ArgoCD. It also restarts etcd on each control-plane node in turn, which must be watched one node at a time with quorum asserted between nodes — a rolling restart of the quorum is not something to fire and forget."
commands:
  - source .env && source .env_devops
  - omnictl apply -f patches/phase08-obs/omni-configpatch-etcd-metrics.yaml
  - "# Watch the roll ONE NODE AT A TIME. Do not proceed to the next node until"
  - "# the previous one is back in the member list with a leader elected."
  - talosctl -n 192.168.55.21 etcd status
  - talosctl -n 192.168.55.22 etcd status
  - talosctl -n 192.168.55.23 etcd status
  - "# If nothing changes on the first node within a few minutes, Omni may have"
  - "# wedged on a cold-boot clock jump: it keeps serving cached reads while its"
  - "# reconcile runtime is stopped. Recovery is `docker restart omni` on the Omni"
  - "# host, then refresh the stored talosconfig."
verify:
  - "# 1. The listener responds on ALL THREE minis. Ask from inside the cluster."
  - "VMAGENT=$(kubectl -n monitoring get pod -l app.kubernetes.io/name=vmagent -o name | head -1)"
  - "for ip in 192.168.55.21 192.168.55.22 192.168.55.23; do kubectl -n monitoring exec \"$VMAGENT\" -c vmagent -- wget -qO- \"http://$ip:2381/metrics\" | head -1; done"
  - "# Expect etcd metrics from each. Before the patch all three returned Connection refused."
  - "# 2. The scrape target came UP: up{job=\"kube-etcd\"} returns 3 series, all 1."
  - "kubectl -n monitoring port-forward svc/vmsingle-victoria-metrics-victoria-metrics-k8s-stack 8428:8428 &"
  - "curl -s 'http://localhost:8428/api/v1/query?query=up%7Bjob%3D%22kube-etcd%22%7D' | jq '.data.result[] | {instance: .metric.instance, up: .value[1]}'"
  - "# 3. The etcd-side metric families exist — NOT just the apiserver storage client."
  - "#    Required: etcd_server_has_leader, etcd_disk_wal_fsync_duration_seconds_bucket, etcd_mvcc_db_total_size_in_bytes"
  - "#    NOT evidence: etcd_request_*, etcd_requests_*, etcd_lease_*, etcd_bookmark_* — those existed throughout the 148 blind days."
  - "# omnictl exiting 0 proves the patch was ACCEPTED, not that etcd restarted with it. Assert on the series, not the exit status."
  - "# 4. All six layer-2-etcd-* rules read Normal in Grafana — not NoData, not Error."
status: pending
```
