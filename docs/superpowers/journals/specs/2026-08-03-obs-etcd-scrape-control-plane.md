# Journal: 2026-08-03-obs-etcd-scrape-control-plane

<!-- fr:journal kind=decision scope=spec id=d1-exposure created=2026-08-03T11:15:42 -->
### d1-exposure · decision · etcd metrics listener binds 0.0.0.0:2381 via one machine-set-scoped ConfigPatch

Operator choice (batched Q&A). Alternatives considered: per-node LAN-IP binding (3x config surface, marginal gain — the LAN NIC is the exposed interface either way) and loopback + a hostNetwork proxy DaemonSet (genuinely locked down, but adds a workload and a failure mode in front of the very signal we are adding in order to trust the control plane). The LAN is already Frank's trust boundary: the ArgoCD UI serves plain HTTP on 192.168.55.200. The metrics listener exposes no key material. One file, scoped to omni.sidero.dev/machine-set: frank-control-planes, mirroring patches/phase13-auth/omni-configpatch.yaml.

<!-- fr:journal kind=decision scope=spec id=d2-routing created=2026-08-03T11:15:54 -->
### d2-routing · decision · Quorum loss pages Telegram; latency/size/churn signals are health-bridge only

Operator choice (batched Q&A). etcd_server_has_leader==0 and quorum-member-down are severity=critical with a for: window long enough to ride out a rolling control-plane reboot. Leader-change churn, WAL fsync p99 and DB-size-vs-quota carry severity=warning + health_bridge_only="true", so they drive the feature-health tile and the bug lifecycle without paging. Rationale: a planned Talos roll legitimately changes leaders and removes one etcd for minutes — the 2026-08-02 control-plane roll produced 48 alerts against a healthy cluster and is the cautionary precedent.

<!-- fr:journal kind=decision scope=spec id=d3-dashboard created=2026-08-03T11:16:07 -->
### d3-dashboard · decision · Ship a hand-provisioned etcd dashboard row, not the chart's default board

Operator choice (batched Q&A). Five panels (has_leader per node, leader changes/1h, WAL fsync p99, DB size vs quota, peer round-trip p99) as a provisioned ConfigMap, matching how feature-health / blog-edge / secure-agent-pod dashboards are already shipped. The chart's defaultDashboards etcd board was rejected as upstream-shaped and outside Frank's curation. The panels are where the acceptance re-run's before/under-load evidence lives — without them the promoted row has no durable home.

<!-- fr:journal kind=decision scope=spec id=d4-testplan created=2026-08-03T11:16:18 -->
### d4-testplan · decision · Acceptance re-run repeats the original 7500-rerank/240s soak with etcd evidence

Operator choice (batched Q&A). Post-merge the Test Plan re-runs the same load recorded on 2026-08-03 (7500 rerank requests over 240s from mini-1) and captures leader changes, has_leader and WAL fsync p99 before and under load, alongside the apiserver p99 already measured. Like-for-like comparability is the point: it lets infer-igpu-workload-preserves-quorum be promoted on the claim it originally made, rather than a narrower substitute.

<!-- fr:journal kind=review scope=spec id=r1-absent-watchdog created=2026-08-03T11:24:32 -->
### r1-absent-watchdog · review · Spec would have recreated the very bug it fixes — added an absent() scrape watchdog

Blocking finding, fixed. Every rule in the first draft used noDataState: OK (correct, matching neighbours). But that means if the kube-etcd Endpoints object ever empties again — a chart bump changing the selector, a values merge dropping endpoints:, a node IP change — the up{job="kube-etcd"} series vanish, all rules go NoData, all read OK, and Frank is blind to etcd again behind a green dashboard. That is precisely the 148-day failure this spec exists to close, reintroduced one layer up. The CI tripwire guards the repo config; nothing guarded the live cluster. Fixed by a sixth rule, absent(up{job="kube-etcd"}), severity critical + health_bridge_only=true (critical drives health-bridge's dead->bug-issue lifecycle; the escape-hatch route keeps it off Telegram), for: 15m so a vmagent restart cannot trip it. Tripwire item 8 additionally asserts the watchdog's job selector matches the value the chart actually renders — a watchdog watching the wrong job name can never fire.

<!-- fr:journal kind=review scope=spec id=r2-no-manual-status created=2026-08-03T11:24:37 -->
### r2-no-manual-status · review · There is no 'manual' acceptance status — promotion means rewriting notes, not flipping status

Finding, fixed. The draft Test Plan said to promote infer-igpu-workload-preserves-quorum to status 'manual'. fr acceptance accepts only ci | scheduled | skipped | not-implemented | failing. The repo's convention for a live-operator-proved row is status: skipped with evidence in notes (see gpu1-usb-25g-node-ip-stable, 'Live manual proof 2026-07-11'). Spec corrected: the row's status does not change; what changes is that its notes stop saying 'NOT VERIFIABLE: … Frank does not scrape etcd' and start carrying numbers. Also recorded that add is append-only with no set, so status edits are hand-edits + fr acceptance report --deterministic.

<!-- fr:journal kind=review scope=spec id=r3-counts created=2026-08-03T11:24:43 -->
### r3-counts · review · Two factual slips in the verified-state table and the rules section

Fixed. (1) The draft said up carries 23 jobs; the actual /api/v1/label/job/values response has 22 values. (2) The rules section said 'Four rules' above a five-row table, and is now six after r1-absent-watchdog. Both are the kind of unchecked number that makes a reader stop trusting the measured claims beside them.

<!-- fr:journal kind=review scope=spec id=r4-talosctl-unexercised created=2026-08-03T11:24:49 -->
### r4-talosctl-unexercised · review · talosctl could not be exercised this session — recorded rather than implied

Finding, fixed by disclosure. Test Plan step 1 tells the operator to assert quorum with talosctl -n <ip> etcd status between node restarts. talosctl against Frank proxies through Omni and needs operator credentials this session did not hold; the command timed out at the auth step after 2 minutes. omnictl is present on PATH and the machine-set scoping is copied verbatim from a ConfigPatch that demonstrably landed (phase13-auth, PR #742), but the apply path is unverified here by construction. The spec now says so in the step itself rather than letting the reader assume it was tried.

<!-- fr:journal kind=review scope=spec id=r5-configpatch-id created=2026-08-03T11:24:54 -->
### r5-configpatch-id · review · ConfigPatch id 160 verified free against all 30 patches in the repo

Verified, no change. Enumerated every metadata.id under patches/: the numbering is semantic rather than phase-derived (1xx cluster-wide, 2xx labels, 3xx node runtime, 4xx/5xx extensions and disks; phase13-auth uses 150). 160-etcd-metrics-listener sits in the cluster-wide band and collides with nothing. Also confirmed phase13-auth/omni-configpatch.yaml is the only existing machine-set-scoped patch, so it is the correct and only precedent for scoping to frank-control-planes.

<!-- fr:journal kind=review scope=spec id=r6-upstream-dashboard-already-live created=2026-08-03T12:12:24 -->
### r6-upstream-dashboard-already-live · review · d3-dashboard's premise was wrong — the chart's etcd board is already live and undisableable

Finding, spec corrected, decision NOT reversed. The batched Q&A offered 'reuse the chart's built-in etcd dashboard' as an alternative to enable; measurement afterwards showed it is already enabled and running. 15 grafana_dashboard-labelled ConfigMaps exist in monitoring, one of them the chart's etcd board, and Grafana runs a grafana-sc-dashboard sidecar. It has rendered nothing for 148 days for the same reason the alerts could not exist.

It cannot be disabled independently (defaultDashboards.dashboards has three toggles, none of them etcd; the board follows kubeEtcd.enabled) and the Application is prune: false, so even a values-level disable would orphan the live ConfigMap.

Judged NOT to warrant re-opening the operator Q&A: d3's intent was a Frank-curated board holding the acceptance evidence, and that intent is unaffected by the upstream board also existing. Proceeding means two etcd dashboards rather than one, which is cheap to reverse if the operator disagrees. Mitigations required of phase 3: distinct title + uid, a header comment naming the upstream board, and a gotchas entry saying which is which — so the duplicate is not resolved later by deleting the curated one.
