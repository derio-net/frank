# Journal: 2026-08-03--obs--etcd-scrape-control-plane

<!-- fr:journal kind=discovery scope=plan id=p1-mutation-check-drift-guards created=2026-08-03T11:42:37 -->
### p1-mutation-check-drift-guards · discovery · Both cross-file drift guards mutation-checked; they name the mismatch, not just the diff

P1.T3.S1. The two derivations in scripts/tests/test_etcd_scrape.py were mutation-checked against deliberate corruption of each half, and both fail with a message that identifies WHICH file disagrees with which.

MUTATION 1 — ConfigPatch listen-metrics-urls 2381 -> 2382.
Two tests failed. test_configpatch_opens_the_metrics_listener (the literal check) and, importantly, the derivation:

  AssertionError: PORT MISMATCH between the two halves of the etcd scrape:
    patches/phase08-obs/omni-configpatch-etcd-metrics.yaml opens etcd metrics listener on port 2382 (listen-metrics-urls: http://0.0.0.0:2382)
    apps/victoria-metrics/values.yaml dials kubeEtcd.service.targetPort = 2381
  These files are applied by different tools and nothing else connects them, so a mismatch does not fail a deploy - it produces a scrape target that is down forever while both files look correct in isolation.
  assert 2382 == 2381

MUTATION 2 — values.yaml kubeEtcd.endpoints mini-2 192.168.55.22 -> .24.
Two tests failed. test_kube_etcd_values_target_the_control_planes and the derivation:

  AssertionError: ENDPOINT MISMATCH between the etcd scrape and the repo machine table:
    apps/victoria-metrics/values.yaml kubeEtcd.endpoints = [192.168.55.21, 192.168.55.24, 192.168.55.23]
    agents/rules/frank-infrastructure.md control-plane rows = [192.168.55.21, 192.168.55.22, 192.168.55.23]
  etcd runs on the control plane and nowhere else. An address in one list and not the other is either a node that is scraped but runs no etcd, or an etcd member that is not scraped at all - and neither shows up as an error, only as missing series.
  At index 1 diff: 192.168.55.24 != 192.168.55.22

Both mutations reverted; suite back to 4 passed.

NOTE FOR LATER PHASES: the control-plane IPs are derived ONCE at module import into CONTROL_PLANE_IPS, by parsing the machine table in agents/rules/frank-infrastructure.md with a regex over markdown table rows (host | ip | role, filtered role == control-plane). That derivation asserts it parsed exactly 3 rows, so a change to the table shape fails loudly rather than silently yielding an empty set and making every downstream assertion vacuous. test_kube_etcd_values_target_the_control_planes also consumes CONTROL_PLANE_IPS rather than restating the addresses - deliberately, so the test file never becomes the third place Frank node IPs live.

<!-- fr:journal kind=discovery scope=plan id=p1-rendered-job-label-kube-etcd created=2026-08-03T11:44:54 -->
### p1-rendered-job-label-kube-etcd · discovery · Rendered job label is kube-etcd — phase 2 alert selectors confirmed against chart 0.72.4

P1.T3.S2. Rendered victoria-metrics-k8s-stack 0.72.4 (the pinned targetRevision in apps/root/templates/victoria-metrics.yaml) with the new kubeEtcd block, release name victoria-metrics to match production.

RENDERED JOB LABEL: kube-etcd

That is the string phase 2 must select on. It arrives by two hops, so record both — a rename of either breaks the alerts silently:
  - the Service carries metadata.labels.jobLabel = kube-etcd
  - the VMServiceScrape carries spec.jobLabel = jobLabel, i.e. "take the job name from the Service label NAMED jobLabel"
So series land as up{job="kube-etcd"}, one per node. Phase 2 rules and the absent() watchdog should use job="kube-etcd" exactly.

ALL THREE RENDER ASSERTIONS CONFIRMED:
  - Service victoria-metrics-victoria-metrics-k8s-stack-kube-etcd, ns kube-system, clusterIP: None (headless), ports: [name http-metrics, port 2381, targetPort 2381]
  - Endpoints, same name/ns, subsets[0].addresses = 192.168.55.21/.22/.23, ports [name http-metrics, port 2381]
  - VMServiceScrape endpoints: [{port: http-metrics, scheme: http}] — no bearerTokenFile, no tlsConfig

DIFFERENTIAL RENDER (default values vs ours) independently reproduces the spec diagnosis:
  DEFAULT: Service on port/targetPort 2379 WITH selector {component: etcd}, and NO Endpoints object rendered at all. That selector is what produces the permanently-empty Endpoints on the live cluster, because Talos runs etcd as a host system service and no pod carries component=etcd.
  OURS: Service on 2381, selector ABSENT (supplying endpoints: makes the chart drop the selector entirely), plus a static Endpoints object. So "supplying endpoints switches the chart to a static Endpoints object" is literally true in the template, not just in effect.

THE DEFAULT vmScrape THE OVERRIDE REPLACES (verbatim, chart 0.72.4) — this is what the negative assertions in test_etcd_scrape.py guard against inheriting:
  endpoints:
  - bearerTokenFile: /var/run/secrets/kubernetes.io/serviceaccount/token
    port: http-metrics
    scheme: https
    tlsConfig:
      caFile: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
All three (https, ServiceAccount bearer token, tlsConfig) are wrong for the plain-HTTP metrics listener; our override replaces the endpoints list wholesale, confirmed in the render.

TWO PRE-EXISTING OBJECTS PHASE 2 SHOULD KNOW ABOUT (both render identically with AND without our block, so this change neither adds nor removes them — they follow from kubeEtcd.enabled, which was already true by chart default):
  1. VMRule victoria-metrics-victoria-metrics-k8s-stack-etcd — 15 UPSTREAM etcd alerts (etcdMembersDown, etcdInsufficientMembers, etcdNoLeader, etcdHighNumberOfLeaderChanges, etcdHighFsyncDurations x2, etcdDatabaseQuotaLowSpace, etcdExcessiveDatabaseGrowth, etcdDatabaseHighFragmentationRatio, etcdMemberCommunicationSlow, etcdHighNumberOfFailedProposals, etcdGRPCRequestsSlow, etcdHighNumberOfFailedGRPCRequests x2, etcdHighCommitDurations). Every one selects job=~".*etcd.*", which MATCHES kube-etcd — so they would all start matching real data once the listener opens. They overlap phase 2 rules 1/4/5/6 substantially (etcdNoLeader is etcd_server_has_leader == 0; etcdHighFsyncDurations is the same WAL fsync histogram at 0.5s/1s vs our 0.05s; etcdDatabaseQuotaLowSpace is the same quota ratio at 95% vs our 80%). They are NOT expected to fire on Frank because apps/victoria-metrics/values.yaml sets vmalert.enabled: false and alertmanager.enabled: false — a VMRule is evaluated by vmalert, and Frank has none; alerting is Grafana-managed. Worth a sentence in phase 2 so nobody later "discovers" duplicate etcd alerting and deletes the wrong half.
  2. ConfigMap victoria-metrics-victoria-metrics-k8s-stack-etcd, labelled grafana_dashboard: "1" — the chart defaultDashboards etcd board that the spec explicitly REJECTED in favour of a curated ConfigMap (decision d3-dashboard). It is rendered regardless of our change. Phase 2 building the curated board does not need to suppress it, but should not be surprised to find it.

Command used (rtk proxy, because rtk summarises helm output and truncates the render):
  rtk proxy helm template victoria-metrics vm/victoria-metrics-k8s-stack --version 0.72.4 -f <(kubeEtcd block extracted with python) --set victoria-metrics-operator.enabled=false

<!-- fr:journal kind=discovery scope=plan id=p3-upstream-etcd-dashboard-is-already-live created=2026-08-03T12:11:39 -->
### p3-upstream-etcd-dashboard-is-already-live · discovery · The chart's etcd dashboard is ALREADY live in Grafana and cannot be disabled independently

Measured live 2026-08-03, and it changes the premise of spec decision d3-dashboard.

d3 was answered as a choice between hand-writing panels and 'enabling' the chart's defaultDashboards etcd board. The board is not something to enable — it is already there:

  kubectl -n monitoring get cm -l grafana_dashboard=1
    -> 15 ConfigMaps, INCLUDING victoria-metrics-victoria-metrics-k8s-stack-etcd

and the Grafana Deployment runs three containers — grafana, grafana-sc-datasources and grafana-sc-dashboard — so the sidecar that consumes grafana_dashboard-labelled ConfigMaps is active. An upstream etcd dashboard has therefore been sitting in Frank's Grafana for 148 days rendering nothing, for the same reason the alerts could not exist: no series.

It cannot be turned off on its own. defaultDashboards.dashboards exposes exactly three toggles (victoriametrics-vmalert, victoriametrics-operator, node-exporter-full); the etcd board follows kubeEtcd.enabled. The only levers are defaultDashboards.enabled: false, which would remove all 15 boards including node-exporter-full and the kubernetes views, and kubeEtcd.enabled: false, which removes the scrape this whole plan exists to add. Neither is acceptable. Note also that with the victoria-metrics Application at prune: false, even a values-level disable would leave the live ConfigMap orphaned on the cluster.

CONSEQUENCE FOR PHASE 3: Frank will have two etcd dashboards, and once the ConfigPatch lands the upstream one will start populating too. Ship the curated board anyway — d3's intent (a curated board where the acceptance evidence lives) survives the corrected fact — but (1) give it a distinct title and uid so the two are never confused, (2) do NOT attempt to disable the upstream board, and (3) say all of this in the dashboard ConfigMap's header comment and in the gotchas entry, so the next person who finds duplicate etcd dashboards does not delete Frank's curated one believing it to be the redundant copy.

<!-- fr:journal kind=discovery scope=plan id=p2-fifteen-minute-window-guard-collision created=2026-08-03T12:29:55 -->
### p2-fifteen-minute-window-guard-collision · discovery · Three of the six rules trip the folder's 15m-window policy guard — the exemption allowlist is the intended answer

P2.T1.S3. The spec's for: values collide with an existing folder-wide policy guard that nothing in the plan or spec mentions. Writing the six rules made scripts/tests/test_feature_health_workload_metrics.py go red:

  AssertionError: feature-health rule(s) sit at `for: 15m` without querying kube_daemonset_status_number_unavailable. That window exists to absorb node drains; using it for anything else needs its own rationale, not this one's. Either pick a window this rule can justify on its own, or add it to FIFTEEN_MINUTE_EXEMPTIONS with a written reason: ['layer-2-etcd-db-quota', 'layer-2-etcd-scrape-absent', 'layer-2-etcd-wal-fsync-slow']

The guard (test_the_fifteen_minute_window_is_reserved_for_daemonset_rules, landed 2026-08-02 with the workload-metrics migration) says 15m exists in the feature-health folder for exactly ONE reason — absorbing a node drain — and any other rule adopting it is a sensitivity decision wearing that one's clothes. The spec's three 15m rules genuinely are not drain-tolerance cases, so the guard is RIGHT and the rules are also right; the resolution the guard itself prescribes is FIFTEEN_MINUTE_EXEMPTIONS, whose VALUE is the justification prose (a sibling test asserts each entry is >=80 chars and that its rule is still actually at 15m, so a stale exemption fails).

Three entries added, each arguing the window on its own terms rather than borrowing the drain argument:
  - layer-2-etcd-scrape-absent: absent() has no `for`-like tolerance of its own, so the window IS the tolerance for the two legitimate pauses (vmagent restart; the rolling etcd restart the ConfigPatch causes). Binary condition, so 15m waits rather than blunts.
  - layer-2-etcd-wal-fsync-slow: a p99 disk quantile is spiky (compaction, Longhorn replica rebuild, backup window); 15m demands the elevation persist across three evaluations. The THRESHOLD carries the sensitivity here and is documented provisional; the window only rejects spikes.
  - layer-2-etcd-db-quota: the backend grows over hours/days, so detection latency is irrelevant — at 80% of quota there is a long runway before the NOSPACE alarm. The window rejects the transient ratio moves around compaction/defrag.

FOR PHASES 3-5: any further rule added to the feature-health folder at for: 15m must either query kube_daemonset_status_number_unavailable or land in that allowlist with its own written reason. Do not reach for 15m as a generic 'less noisy' default — that is precisely the behaviour the guard exists to convert into a written decision.

<!-- fr:journal kind=discovery scope=plan id=p2-watchdog-job-derivation-renders-the-chart created=2026-08-03T12:30:34 -->
### p2-watchdog-job-derivation-renders-the-chart · discovery · The watchdog job assertion renders the pinned chart in-test; mutation-checked, and it names both hops

P2.T2.S1. test_absent_watchdog_selects_the_job_the_chart_renders does NOT compare the rule against a constant — a constant and a rule that agree are the same paste twice. It shells out to `helm template` against the chart pin PARSED OUT OF apps/root/templates/victoria-metrics.yaml (regex, not yaml.safe_load: the Application is a Helm template and its sibling sources carry {{ .Values.repoURL }}, so it does not parse), renders with the real apps/victoria-metrics/values.yaml and release name `victoria-metrics`, and derives the job name in the two hops the P1 journal recorded:

  VMServiceScrape.spec.jobLabel  -> names a Service LABEL KEY  ("jobLabel")
  Service.metadata.labels[key]   -> the job VALUE              ("kube-etcd")

Precedent for shelling out is scripts/tests/test_cnc_staging_host_secrets.py (`helm template --repo <url> --version`), and CI already installs helm for test_argocd_vcluster_pod_exclusion (.github/workflows/repo-tripwires.yml). Fail-closed like that precedent: a non-zero helm exit, a missing kube-etcd Service or a missing jobLabel is an AssertionError, never a skip. Cost is real — the render is ~30-50s, and it is the reason test_etcd_scrape.py went from 7s to 52s.

The test checks EVERY up{job=...} selector in the six rules, not only the watchdog. layer-2-etcd-member-down fails the same way and more quietly: a wrong job yields no series, which under noDataState: OK reads as a healthy quorum forever.

MUTATION CHECK (absent expression job kube-etcd -> kube-etcd-x): 1 failed, 11 passed. The message names both the derived value and the offending rule, so it says WHICH file disagrees rather than merely that something does:

  AssertionError: etcd alert rule(s) select a job the chart does not render.
      chart renders: job='kube-etcd'
      rules select:  {'layer-2-etcd-scrape-absent': ['kube-etcd-x']}
    The name arrives by two hops - the Service carries a `jobLabel` label, and the VMServiceScrape's `spec.jobLabel` says to take the job name from it - so a rename at either end moves it. A selector naming a job that does not exist yields no series, which for the watchdog means `absent() == 1` permanently (fires against a healthy scrape, then gets muted) and for every other rule means NoData, which noDataState: OK reads as health. Both are the guard being silently wrong, which is the exact defect this layer exists to stop recurring.

Reverted; back to 12 passed. NOTE FOR PHASE 3: _rendered_kube_etcd_objects() caches the render at module scope, so a dashboard test that also needs chart facts should reuse it rather than paying a second 30s render.

<!-- fr:journal kind=discovery scope=plan id=p2-inert-upstream-vmrule-documented-in-place created=2026-08-03T12:31:08 -->
### p2-inert-upstream-vmrule-documented-in-place · discovery · The 15 inert upstream etcd alerts are now named in the ConfigMap itself, with which half is live

P2.T1.S3. Acting on the P1 discovery p1-rendered-job-label-kube-etcd. The chart renders VMRule victoria-metrics-victoria-metrics-k8s-stack-etcd carrying 15 upstream etcd alerts, all selecting job=~".*etcd.*" (which MATCHES kube-etcd), overlapping four of the six new rules at looser thresholds — etcdNoLeader vs layer-2-etcd-no-leader, etcdHighFsyncDurations at 0.5s/1s vs our 0.05s, etcdDatabaseQuotaLowSpace at 95% vs our 80%, etcdMembersDown/etcdInsufficientMembers vs layer-2-etcd-member-down.

They are inert: a VMRule is evaluated by vmalert, and apps/victoria-metrics/values.yaml sets vmalert.enabled: false (alerting on Frank is Grafana-managed). They render whether or not our kubeEtcd block exists, since they follow kubeEtcd.enabled which was already true by chart default.

The risk is not that they fire — it is that a future reader discovers 'duplicate etcd alerting' and resolves it by deleting the LIVE half, because the upstream rules look canonical and ours look like a local addition. So the comment block above the new group states outright which half is live and why the other cannot fire, and ends with 'do not delete them in favour of the inert ones'. Same shape as the mitigation phase 3 owes the curated-vs-upstream DASHBOARD pair (see r6-upstream-dashboard-already-live) — worth keeping the two notes consistent in wording so the pattern is recognisable.

Also recorded in that comment block: the metric allowlist (etcd_server_/disk_/mvcc_/network_ and up{job="kube-etcd"}) and the explicit NEVER for etcd_request_*/etcd_requests_*/etcd_lease_*/etcd_bookmark_*, so the rule against measuring the apiserver's storage client exists both as a CI assertion and as prose next to the rules it governs.

<!-- fr:journal kind=finding scope=plan id=p2-endpoints-label-is-k8s-app-not-joblabel created=2026-08-03T12:35:48 state=fixed -->
### p2-endpoints-label-is-k8s-app-not-joblabel · finding [fixed] · The kube-etcd Endpoints object is labelled k8s-app, not jobLabel — a runbook selecting jobLabel returns empty and reads as a missing object

P2.T1.S3, caught before commit by checking the render rather than trusting the shape.

The scrape-absent runbook first said:
  kubectl -n kube-system get endpoints -l jobLabel=kube-etcd -o yaml

That selector matches NOTHING. The chart labels the three objects differently, and the difference is invisible unless you look:
  Service   metadata.labels: {..., jobLabel: kube-etcd}      <- jobLabel lives HERE
  Endpoints metadata.labels: {..., k8s-app:  kube-etcd}      <- and NOT here
  VMServiceScrape spec.jobLabel: jobLabel                    <- names the Service label key

So the command an operator runs at the moment the watchdog fires would have returned no resources — which, for a rule whose entire meaning is 'the scrape produced no series', reads as CONFIRMATION that the Endpoints object is gone. It would have sent triage straight past the actual cause (an empty subsets list, or a closed 2381 listener) toward re-creating an object that was there all along.

Fixed to `-l k8s-app=kube-etcd`, with the distinction stated inline in the runbook so the next person does not re-derive it wrongly. Verified against the 0.72.4 render.

GENERAL SHAPE, worth carrying into phases 3-5: a runbook command is not documentation, it is code that runs during an incident, and a selector that returns empty is indistinguishable from the thing it selects being absent. Any kubectl selector written into an annotation should be checked against a render or the live cluster before shipping — same family as the negative-control lesson in the MagicDNS wildcard gotcha (a check that passes vacuously proves nothing).

<!-- fr:journal kind=discovery scope=plan id=p3-curated-dashboard-shipped created=2026-08-03T13:07:42 -->
### p3-curated-dashboard-shipped · discovery · Curated etcd dashboard shipped alongside the already-live upstream board

P3.T1. Acting on p3-upstream-etcd-dashboard-is-already-live: the curated ConfigMap apps/grafana-alerting/manifests/etcd-dashboard-cm.yaml carries uid frank-l2-etcd, title "Frank Layer 2 — etcd (curated)" — deliberately not "etcd" (the upstream chart-rendered board's title) and not a chart-shaped uid. The upstream board is ConfigMap victoria-metrics-victoria-metrics-k8s-stack-etcd, dashboard uid c2f4e12cdf69feb95caa41a5a1b423d9 (verified by rendering the pinned chart 0.72.4 locally), title "etcd" — confirmed still present in the render alongside our kubeEtcd block, so nothing here removed or touched it, per the journal's instruction not to attempt disabling it.

Five panels per the spec: etcd_server_has_leader per node (stat, background colour red/green), leader changes/1h (timeseries), WAL fsync p99 (timeseries, histogram_quantile 0.99 over etcd_disk_wal_fsync_duration_seconds_bucket), DB size vs quota (gauge, etcd_mvcc_db_total_size_in_bytes / etcd_server_quota_backend_bytes, 0-1 percentunit), peer round-trip p99 (timeseries, histogram_quantile 0.99 over etcd_network_peer_round_trip_time_seconds_bucket). All queries stay inside etcd_(server|disk|mvcc|network)_ — none touch etcd_request_*/etcd_lease_* (the apiserver storage-client trap named in the P1/P2 journal entries).

Mounted via TWO apps/victoria-metrics/values.yaml grafana.extraConfigmapMounts entries (etcd-dashboard-provider -> /etc/grafana/provisioning/dashboards/etcd-provider.yaml, etcd-dashboard-json -> /var/lib/grafana/dashboards/etcd/etcd-dashboard.json), following the existing provider/json pair pattern exactly (mirrors sap-dashboard-provider/sap-dashboard-json). The header comment on the ConfigMap and a comment above the mount block both point back at each other and at the spec's Half 2c correction paragraph, so a future reader who finds two etcd dashboards has the explanation in both places they might look first.

New test test_etcd_dashboard_is_provisioned_and_mounted (scripts/tests/test_etcd_scrape.py, now 13 tests) asserts: the ConfigMap exists and carries both data keys; the dashboard json has exactly 5 titled panels; no panel expr references an apiserver storage-client metric or anything outside the four etcd_* families; the title does not collide with the upstream board's literal title "etcd"; and grafana.extraConfigmapMounts carries exactly 2 mounts (by subPath) referencing this ConfigMap's name. Confirmed RED (missing file) before writing the ConfigMap, GREEN after (13 passed, ~39s, reusing the module-cached chart render from phase 2 — no second helm template call added).

FOR PHASE 4 (docs/gotchas): the gotcha must name both boards by title+uid (curated: frank-l2-etcd / "Frank Layer 2 — etcd (curated)"; upstream: c2f4e12cdf69feb95caa41a5a1b423d9 / "etcd") and say the curated one is NOT the redundant copy — same shape as the inert-upstream-VMRule note phase 2 already wrote for the alert rules, and the two should read consistently.

<!-- fr:journal kind=discovery scope=plan id=p3-complete-phase-acceptance-warning-expected created=2026-08-03T13:08:05 -->
### p3-complete-phase-acceptance-warning-expected · discovery · fr plan edit --complete-phase 3 warns on not-implemented acceptance rows — expected, not a phase 3 gap

P3 completion. fr plan edit --complete-phase 3 emitted: "warning: phase 3 completed but its acceptance rows are still not-implemented: obs-etcd-server-metrics-scraped — flip them (edit status + cite the test refs) or record why in notes." This is expected, not a defect in phase 3's work — per the spec's Test Plan section (d4-testplan), obs-etcd-server-metrics-scraped only flips to skipped once an operator has applied the ConfigPatch (Test Plan step 1, the plan's back-loaded manual phase — Phase 5 per the pickup) and run Test Plan step 3 (confirm the scrape in VMSingle) against the live cluster. No unit test can produce that evidence; it requires the operator's own hands on omnictl. Recording here so phase 4/5 does not mistake this pre-existing warning for a regression introduced by the dashboard work, and so whoever runs the operator steps knows the acceptance-row flip (hand-edit + fr acceptance report --deterministic) is still outstanding after phase 3.

<!-- fr:journal kind=finding scope=plan id=p4-manual-op-block-invisible-to-sync-runbook created=2026-08-03T13:44:45 state=fixed -->
### p4-manual-op-block-invisible-to-sync-runbook · finding [fixed] · A manual-operation block in patches/ is invisible to /sync-runbook — the phase-4 step as written would never reach the runbook

P4.T1.S2 instructs the `# manual-operation` block to go in `patches/phase08-obs/README.md`. `/sync-runbook` (agents/skills/sync-runbook/SKILL.md, step 1) scans ONLY `docs/superpowers/plans/` — both the v1 `*.md` glob and the v2 `<slug>/NN.yaml` phase files. A block written only under `patches/` is therefore never seen, and the failure is silent in the worst way: the sync runs, reports 'N updated, N total', and reports nothing missing, because it never encountered the block. Phase 5's close-out step P5.T3.S4 ("run /sync-runbook now that the manual op has actually been performed") would have produced no runbook entry for `obs-etcd-metrics-listener-apply` at all.

RESOLUTION, deliberately not a silent workaround. The block now exists in BOTH places, verbatim:
  - patches/phase08-obs/README.md  — what an operator about to run omnictl actually reads, next to the patch
  - docs/superpowers/plans/2026-08-03--obs--etcd-scrape-control-plane/05.yaml, inside step P5.T1.S1's text — what /sync-runbook reads
Collapsing to one copy was rejected in both directions: README-only breaks the sync (above), plan-only leaves the operator reading prose in one file and the procedure in another at the moment they are restarting the quorum.

Duplication is exactly the drift risk this plan's own tripwire file exists to catch, so it is guarded rather than trusted: `test_the_two_copies_of_the_manual_operation_agree` in scripts/tests/test_etcd_scrape.py reads the README block raw and the plan block THROUGH yaml.safe_load (so it compares content, not the step-text indentation) and asserts byte equality. Mutation-checked: flipping `status: pending` -> `done` in the README alone fails with a message naming both paths and which one /sync-runbook reads. A sibling test asserts the nine fields repo-manual-ops.md requires, plus that `verify:` mentions 2381 and the kube-etcd job — i.e. that it asserts an OUTCOME, since `omnictl` exiting 0 proves the patch was accepted, not that etcd restarted with it.

FOR PHASE 5: edit both copies or neither. Run /sync-runbook only after the apply has actually been performed, and flip `status: pending` -> `done` in BOTH files (the tripwire will fail the PR if you flip one). Note /sync-runbook itself preserves human-set status on an existing id and only sets `pending` on a new one, so the first sync will land it as pending regardless — the status edit belongs in these two source files, not in manual-operations.yaml.

<!-- fr:journal kind=discovery scope=plan id=p4-kube-scheduler-has-the-same-empty-endpoints-shape created=2026-08-03T13:45:19 -->
### p4-kube-scheduler-has-the-same-empty-endpoints-shape · discovery · kube-scheduler renders the SAME pod-selector shape — the gotcha generalises, and its live state is unverified

P4.T1.S1. Before writing the gotcha as a reusable shape rather than an incident report, the claim was checked against the pinned chart rather than asserted.

Rendered victoria-metrics-k8s-stack 0.72.4 with the real apps/victoria-metrics/values.yaml, release name victoria-metrics:

  Service …-kube-etcd       selector: None (dropped, because we supply endpoints:)  ports: 2381
  Endpoints …-kube-etcd     subsets: [.21, .22, .23] on http-metrics/2381
  Service …-kube-scheduler  selector: {component: kube-scheduler}  ports: 10259   <- NO Endpoints object rendered
  VMServiceScrape …-kube-scheduler  endpoints: [{scheme: https, bearerTokenFile: …/token, tlsConfig: {caFile: …}}]

So kube-scheduler is in EXACTLY the pre-fix shape kube-etcd was in: a Service selecting pods by a kubeadm-convention label, no static Endpoints object, and a scrape config that looks entirely correct. kubeControllerManager renders nothing at all because values.yaml disables it (the 65-char Service name), so it is not exposed.

WHAT IS AND IS NOT ESTABLISHED. The render proves the CHART shape. It does NOT prove kube-scheduler is currently unscraped on Frank — that needs `kubectl -n kube-system get endpoints` against the live cluster, which this phase had no access to. The two components also differ in kind: Talos runs etcd as a host system service (no pod exists at all, so the selector can NEVER match), whereas kube-scheduler IS a static pod — it may or may not carry `component: kube-scheduler`, since Talos and kubeadm do not use identical labels. Both possibilities end in an empty Endpoints object if the label differs, which is why the gotcha is written as 'check its ENDPOINTS before assuming it is scraped' and NOT as 'kube-scheduler is also blind'.

Both gotcha entries (the one-liner in agents/rules/frank-gotchas.md and the prose in docs/runbooks/frank-gotchas/grafana.md) and the building blog post state it at exactly that strength, with the render date. If someone with cluster access runs `kubectl -n kube-system get endpoints | grep scheduler` and finds it empty, that is a second instance of this layer's bug and worth its own fix — the shape of that fix is already written down here (static endpoints + whatever listener kube-scheduler needs), but it is deliberately NOT claimed as done.

<!-- fr:journal kind=discovery scope=plan id=p4-what-phase-5-must-still-write created=2026-08-03T13:45:44 -->
### p4-what-phase-5-must-still-write · discovery · What phase 5 still owes the two blog posts, and the one frontmatter field left deliberately stale

P4.T2. The blog edits shipped with NO measured numbers, per the phase brief — the soak comparison does not exist until the operator runs Test Plan steps 5-6, and a placeholder results paragraph would have been forgotten and shipped. Both posts describe what WILL be measured, or say nothing.

WHAT PHASE 5 MUST ADD (P5.T3.S4 already says 'add the measured numbers to the operating post's new section' — this is the specific list):

1. blog/content/docs/building/07-observability/index.md, Gotcha 4, the paragraph that currently reads: 'There is no results paragraph here yet, on purpose. The soak re-run that this unblocks … has not been performed at the time of writing.' Replace it with the before/under-load numbers, or with an honest statement of why the comparison still cannot be made. Do not leave that sentence in place once it is false.

2. blog/content/docs/operating/05-observability/index.md, section 'Checking the etcd Scrape'. It documents the five queries and the six alerts but carries no baseline. Once the idle baseline and the under-load figures exist, a short 'what normal looks like on Frank' line under the query block is the natural home — WAL fsync p99 and steady-state leader changes especially, because the WAL threshold (50ms) is documented as provisional in three places (the alert annotation, the runbook table, and this post) and the baseline is what makes tightening it defensible.

3. blog/content/docs/operating/05-observability/index.md frontmatter: `last_updated` was bumped to 2026-08-03, but `last_updated_commit` was deliberately LEFT at a77bf484 (a July commit). Phase 4 could not know its own merge sha, and the branch sha would be wrong after a squash-merge anyway. Set it to the actual merge commit when phase 5 touches the post. The building post has no such field — nothing to do there.

The two posts are the only blog files touched. blog/data/roadmap.yaml was NOT touched (correct — this is a fix/extension of Layer 8, not a new layer), no new post was created, and no series index needed editing (they are page-derived).

BUILD VERIFICATION, since past blog edits on this repo have silently rewritten repo state: `hugo --minify` from blog/ exited 0 and `git status --porcelain` was byte-identical before and after — no blog/go.mod, no blog/go.sum, no lockfile. Both pages rendered with the new sections present in blog/public and zero REF_NOT_FOUND. validate_glossary.py passes on both files (13 markers, one new: the WAL marker in the building post). validate_mermaid.py reports the syntax gate is DISABLED repo-wide (quality.mermaid_syntax: false), so it proves nothing — no mermaid was added either way.

<!-- fr:journal kind=finding scope=plan id=f1-kube-scheduler-generalisation-was-wrong created=2026-08-03T13:53:46 state=fixed -->
### f1-kube-scheduler-generalisation-was-wrong · finding [fixed] · The gotcha generalised the empty-Endpoints trap to kube-scheduler, which is live-healthy

Caught in orchestrator verification of phase 4, fixed before review. Phase 4 wrote (in the hot gotchas file, the per-topic file and the building post) that kubeScheduler has the same empty-Endpoints shape, citing a helm template render showing a pod selector and no Endpoints object. The agent said plainly that this proved the chart and not the cluster, and it had no cluster access — honest, but the generalisation still shipped. It is wrong live: endpoints/kube-etcd is <none> while endpoints/kube-scheduler carries 192.168.55.21/22/23:10259, and kube-scheduler is in the up job list (measured 2026-08-03). Talos runs kube-apiserver, kube-controller-manager and kube-scheduler as STATIC PODS carrying the component: labels the chart expects, so the selector works for them; etcd alone is a host system service, which is exactly why it is the only one that broke. The underlying reasoning error is worth more than the correction: a helm template render CANNOT show Endpoints, because the API server creates and populates them at runtime from matching pods — so every selector-based component looks endpoint-less in a render, healthy ones included. Inferring absence from an artifact that structurally cannot contain the thing being looked for is a second silent-absence trap sitting on top of the first. Fixed in all three files; the near-miss is kept on the record rather than quietly corrected, because the mistake teaches the lesson better than the fact does. 15 tests pass, hugo builds, no go.mod or lockfile drift.

<!-- fr:journal kind=finding scope=plan id=c1-ordering-claim-was-false-configpatch-is-a-pre-merge-gate created=2026-08-03T14:36:09 state=fixed -->
### c1-ordering-claim-was-false-configpatch-is-a-pre-merge-gate · finding [fixed] · BLOCKING: 'ordering is safe in either direction' was false — up is synthesised at 0, not absent, so merging first pages Telegram every 3 minutes

Code review, pre-PR. The branch asserted in SEVEN places that the GitOps half could merge before the operator applied the Talos ConfigPatch, on the reasoning: "the target is simply down and the rules sit at NoData with noDataState: OK — nothing fires."

THAT IS WRONG, and one word carried the whole argument: absent.

`up` is NOT a series etcd exports. The SCRAPER synthesises it, once per CONFIGURED target, every interval — 1 on a successful scrape and 0 on a failed one. It is never absent while the target is configured. And supplying `kubeEtcd.endpoints` is precisely what configures targets: the chart drops its pod selector and renders a static Endpoints object with three addresses. So the instant ArgoCD syncs the values block, vmagent has three targets dialling a connection-refused port, and they sit at up=0, NOT NoData.

`layer-2-etcd-member-down` is `up{job="kube-etcd"} lt 1`, for: 10m, severity: critical, with NO health_bridge_only label. It therefore fires ten minutes after the merge, and the notification policy's ROOT repeat_interval (3m, verified in apps/grafana-alerting/manifests/notification-policy-cm.yaml) pages Telegram every three minutes, three instances at a time, against a perfectly healthy quorum — until an operator applies a patch the plan had deliberately deferred.

An absent series and a series reading 0 are different states, and only the first is NoData. The other five rules DO go NoData and DO read OK (they query etcd_server_/disk_/mvcc_, of which a failed scrape produces nothing). `up` is the asymmetric case, and it is the case the two paging rules are built on.

LIVE PROOF, measured on Frank 2026-08-03 (VMSingle, read-only) — not a theoretical reading of the scrape protocol:
  count(up==0) by (job)                        -> {job="kube-scheduler"} 3
  max_over_time(up{job="kube-scheduler"}[90d]) -> 0, 0, 0
kube-scheduler has three POPULATED Endpoints (Talos runs it as a static pod, so the chart's selector works) and a scrape that then fails on 10259 TLS/auth. It has read up=0, not NoData, for the entire retention window. kube-etcd enters exactly that state on merge.

RESOLUTION — the ordering INVERTS: the ConfigPatch is now a PRE-MERGE GATE. That is the right fix rather than de-fanging the rule, because the ConfigPatch is harmless standalone: it opens a read-only, key-material-free metrics port that nothing is yet scraping, and changes no other behaviour. Applying it first costs nothing, makes every claim in the branch true at the moment of merge, and lets the scrape come up healthy on the first sync instead of alarming. Relaxing `for:`, adding health_bridge_only to the paging rules, or shipping the values block disabled would each buy the same quiet by discarding the signal the layer exists to add. test_only_quorum_loss_pages is unchanged; no health_bridge_only was added.

Corrected in all seven places, each carrying the MECHANISM rather than a bare assertion:
  1. docs/superpowers/specs/...-design.md — the Half 2 paragraph is now a section, "Ordering is NOT safe in either direction — the ConfigPatch is a pre-merge gate" (fullest explanation; this is the design authority)
  2. same spec, Half 1 — "back-loaded manual phase" -> pre-merge gate
  3. same spec, Test Plan — steps 1-2 are the PRE-MERGE GATE, steps 3-6 post-merge, stated at the top and per-step
  4. patches/phase08-obs/README.md — new "Ordering: this patch is a PRE-MERGE gate" section, the manual-op `when:` field, and the rollback section
  5. patches/phase08-obs/omni-configpatch-etcd-metrics.yaml — new ORDERING header block + corrected ROLLBACK block
  6. docs/superpowers/plans/.../05.yaml — task 1 retitled '[PRE-MERGE GATE]', both its steps carry the reasoning; tasks 2 and 3 retitled '[post-merge]'; manual-op `when:` kept byte-identical to the README copy
  7. docs/superpowers/plans/.../_prose.md — the ordering section rewritten
  8. scripts/tests/test_etcd_scrape.py — the docstring of test_etcd_rules_declare_nodata_ok_and_execerr_error stated the falsehood as fact; corrected, and it now states the asymmetry plainly (the up{job=...} rules are the one case that is NOT NoData before the patch)
Also added to docs/runbooks/frank-gotchas/grafana.md and the building blog post, which had not made an ordering claim but are where the next reader will look.

DEVIATION FROM THE REVIEW INSTRUCTION, stated: the review said "step 1 is pre-merge; steps 2 onward stay post-merge". I put Test Plan steps 1 AND 2 in the gate, because step 2 (confirm the listener with wget from the vmagent pod) needs nothing from the merge and is what turns "omnictl exited 0" into evidence that etcd actually restarted with the new argument — and because the plan's phase 5 task 1, which the same instruction says to mark as the gate, contains both. Splitting them would have made the spec and the plan disagree about where the gate ends.

<!-- fr:journal kind=finding scope=plan id=c1b-ordering-regression-tripwire created=2026-08-03T14:36:45 state=fixed -->
### c1b-ordering-regression-tripwire · finding [fixed] · Regression tripwire for the ordering claim — anchored to the rule that makes ordering load-bearing, not free-floating prose policing

The C1 defect was a DOCUMENTATION claim. Nothing in the manifests was wrong; seven prose statements were, and they were what the implementation trusted. So the guard against reverting it has to be on the prose — but a bare phrase-ban would be brittle in both directions (it would fail on the corrected documents, which necessarily QUOTE the old sentence in order to explain why it was false, and it would pass on a paraphrase).

test_the_ordering_claim_is_not_reverted, in scripts/tests/test_etcd_scrape.py, is built in two layers:

1. IT DERIVES ITS OWN PREMISE FROM THE MANIFESTS. `_paging_rules_built_on_up()` finds the etcd rules that (a) are in ETCD_PAGING_UIDS, (b) query up{job=...}, and (c) are not absent()-wrapped — i.e. exactly the rules that can fire on a synthesised up=0 AND reach Telegram when they do. If that set is EMPTY the test FAILS, loudly, saying the guard's premise is gone and the ordering docs must be revisited in the same change. It does not pass vacuously: a tripwire that stays green after the thing it guards has been deleted is decoration.

2. GIVEN that premise, it requires five documents (design spec, patches README, the ConfigPatch itself, the plan's _prose.md, the plan's 05.yaml) each to (a) not carry the affirmative claim "Ordering is safe in either direction" / "Ordering is safe either way" — matched case-SENSITIVELY on the capitalised form, so the corrected text can still quote the lower-case original inside quotation marks — (b) contain a pre-merge marker, and (c) contain the MECHANISM (a /synthesis/i match, i.e. "synthesised" / "synthesises" / "SYNTHESISES"). Requiring the mechanism as well as the conclusion is deliberate: an unexplained ordering constraint is one a future reader has no way to evaluate and therefore no reason to keep — and this constraint has already been reasoned away once.

The paths are resolved through the same _PLAN_ROOTS / _SPEC_ROOTS fallback the manual-op guard uses, so the archival commit that moves the plan into implemented/ does not turn the test red for nothing.

MUTATION-CHECKED. Reverting the README heading to "**Ordering is safe in either direction.**" fails with the offending file, its role, and the full mechanism in the message. Removing the "pre-merge" phrase from the ConfigPatch header (the state it was in mid-fix) fails naming that file alone.

<!-- fr:journal kind=finding scope=plan id=i2-kube-scheduler-is-a-second-blind-spot created=2026-08-03T14:37:14 state=fixed -->
### i2-kube-scheduler-is-a-second-blind-spot · finding [fixed] · kube-scheduler is a SECOND control-plane blind spot — populated Endpoints, failing scrape, up=0 and zero scheduler_* series for 148 days

The branch said, correctly, that Talos runs kube-scheduler as a static pod so the chart's pod selector works, and cited its three populated Endpoints. True. But the sentence it built on that — "kube-scheduler has three healthy endpoints on this cluster and reports into `up` like any other job" — is literally true and maximally misleading. It reports up=0.

Measured live 2026-08-03 (VMSingle, read-only):
  count(up==0) by (job)                        -> {job="kube-scheduler"} 3
  max_over_time(up{job="kube-scheduler"}[90d]) -> 0, 0, 0  (all three targets)
  {__name__=~"scheduler_.*"}                   -> []       (zero series)
  endpoints/...-kube-scheduler                 -> 192.168.55.21:10259,.22,.23  (populated, 148d)

The scrape RESOLVES its targets and then FAILS: Talos binds 10259 with TLS/auth that the chart's default endpoint (scheme https + the ServiceAccount bearer token + the in-cluster CA) does not satisfy. Zero scheduler metrics on Frank for exactly as long as there were zero etcd ones.

WHY THIS MATTERS BEYOND ONE MORE GAP: it is a DIFFERENT SPECIES of the same silent absence, and the two diagnostics do not overlap.

  |            | kube-etcd (fixed here)          | kube-scheduler (not fixed)              |
  | Endpoints  | EMPTY - selector matches nothing| populated, 3 addresses                  |
  | Targets    | zero                            | three                                   |
  | up         | series ABSENT entirely          | 0                                       |
  | Cause      | Talos runs etcd as a host svc   | Talos binds 10259 with TLS/auth         |
  | Found by   | kubectl get endpoints           | up lt 1  <- THIS BRANCH'S OWN IDIOM     |

Reading ENDPOINTS finds a scrape with no targets. `count(up==0) by (job)` finds a scrape whose targets never answer. The branch had built the first check and would have shipped believing the control plane was now covered. And the query that finds the second one is the exact idiom the branch's own alert rules are written in — which is also the observation that produced the C1 finding (up=0 vs absent).

FIXED IN ALL THREE PLACES the review named, framed as a discovery rather than an apology:
  - blog/content/docs/building/07-observability/index.md — corrected the "reports into up like any other job" sentence, plus a new subsection "And then the cluster handed me a second one" with the numbers, the two-column comparison table, and an explicit statement that it is NOT fixed here because it needs a decision about authenticating against Talos's static-pod control plane
  - agents/rules/frank-gotchas.md — the (now compressed, see i6) bullet leads with "fails TWO ways on Talos" and names both checks
  - docs/runbooks/frank-gotchas/grafana.md — the "#### etcd is the only one of the three that breaks" heading became "#### etcd is the only ENDPOINTS failure — but kube-scheduler is a second blind spot of a different species", with the table and the measurement; the diagnosis section became TWO checks with a note that neither finds the other's failure
  - blog/content/docs/operating/05-observability/index.md — the diagnosis block gained the up{job="kube-scheduler"} half, and the Quick Reference gained `count(up == 0) by (job)` and `up{job="kube-scheduler"}` rows

DELIBERATELY NOT FIXED. Scraping kube-scheduler needs either a client cert or a metrics-bind-address change on the Talos static pod — a separate decision, not a values typo, and out of scope for this layer. It is now a documented gap rather than an undiscovered one. Worth its own small plan.

<!-- fr:journal kind=finding scope=plan id=i3-stale-paragraph-contradicted-its-own-correction created=2026-08-03T14:37:35 state=fixed -->
### i3-stale-paragraph-contradicted-its-own-correction · finding [fixed] · A pre-correction paragraph survived three paragraphs below its own correction in grafana.md

docs/runbooks/frank-gotchas/grafana.md carried, at the end of the diagnosis section, a paragraph claiming kubeScheduler "still emits selector: {component: kube-scheduler} with no Endpoints object of its own — so it is exposed to exactly this shape. Check its ENDPOINTS before assuming it is scraped; that check has not been run against the live cluster here."

Three paragraphs ABOVE it, the same section printed the live scheduler Endpoints (populated, three addresses) AND named render-based inference as an invalid trap — "a template render can never show Endpoints". So the file simultaneously said the check had not been run and printed its result, and simultaneously warned against the inference it was making. It is a survivor of the pre-correction draft: the correction was written above it and the original was never deleted.

Deleted. Its only unique content was the kubeControllerManager 63-character-Service-name note, which was already stated a few lines earlier; that statement absorbed the "65 characters, Kubernetes allows 63" detail and gained a clause noting kubeControllerManager is exposed to NEITHER failure because it is not scraped at all.

The diagnosis section was rewritten in the same pass (see i2) into two checks rather than one, which is what the deleted paragraph had been gesturing at without being able to say — it was written before anyone had looked.

GENERAL SHAPE: a correction appended above a stale claim leaves a document that contradicts itself, and the stale half reads as the more specific and therefore more authoritative one (it names a chart version and a selector). When correcting prose in place, delete the thing being corrected; do not stack.

<!-- fr:journal kind=finding scope=plan id=i4-manual-op-never-reached-the-central-runbook created=2026-08-03T14:38:06 state=fixed -->
### i4-manual-op-never-reached-the-central-runbook · finding [fixed] · The manual operation was duplicated and byte-guarded so /sync-runbook would pick it up — and then never synced

`obs-etcd-metrics-listener-apply` was absent from docs/runbooks/manual-operations.yaml.

The ENTIRE justification for duplicating the block out of patches/phase08-obs/README.md into the plan phase file 05.yaml, and for guarding the duplication with a byte-equality test, is that /sync-runbook scans only docs/superpowers/plans/ — so a block written only in the patches README would never reach the central registry. That reasoning is in the phase-4 journal entry, in the README, in the plan and in the test docstring. It was duplicated, it was guarded, and the sync never ran.

Two copies that agree perfectly with each other and not with the registry they exist to feed is the same shape as the empty Endpoints object this whole layer is about: every artefact present and internally consistent, the one thing that had to happen never happened, and nothing reports it.

WHAT I DID. Performed the /sync-runbook merge, scoped. Extracted the block from 05.yaml through yaml.safe_load + dedent (the v2 nested-in-step-text path), confirmed the id was new, and appended the entry to docs/runbooks/manual-operations.yaml with the documented field order (id, layer, app, plan, when, why_manual, commands, verify, status: pending).

DELIBERATELY SCOPED, and this is a judgement call worth recording. A faithful full run of the skill would also have REWRITTEN FIVE UNRELATED ENTRIES (gpu-gpu1-usb-25g-nic-firmware, gpu-gpu1-usb-25g-nic-install, net-frank-domain-dual-issuer-rollout, net-frank-domain-final-retirement, obs-crowdsec-canary-telegram-secret), because their plan blocks have drifted from the runbook — and at least one of those rewrites would be a REGRESSION (obs-crowdsec-canary-telegram-secret's plan block carries `plan: 2026-06-21--obs--crowdsec-ban-canary`, a bare slug, which would overwrite the runbook's full path). The skill also specifies a global sort by (layer, id) that the file has not obeyed for a long time; applying it would re-order 142 entries. Neither belongs in a review-fix PR about etcd — both would bury the actual change. FOLLOW-UP: a standalone /sync-runbook reconciliation pass, which should also decide whether the drifted plan blocks or the runbook entries are the correct half.

CLOSED THE LOOP with a test rather than a habit: test_the_manual_operation_reached_the_central_runbook asserts the id is present EXACTLY once in manual-operations.yaml, and that every field except `status` matches the plan block. Field-level rather than id-level because /sync-runbook refreshes all fields but preserves human-set `status`, so a runbook entry whose `when:` or `verify:` disagrees with the plan means the block was edited and never re-synced — and the operator is then reading a stale procedure from the place they were told was authoritative. (This mattered immediately: C1 rewrote the `when:` field, so the entry had to be synced AFTER that correction, not before.) Mutation-checked by deleting the entry: fails naming both copies, the registry, and the fix ("Run /sync-runbook").

<!-- fr:journal kind=finding scope=plan id=i5-two-hardcoded-copies-in-the-derivation-file created=2026-08-03T14:38:26 state=fixed -->
### i5-two-hardcoded-copies-in-the-derivation-file · finding [fixed] · Two hardcoded copies in the file whose thesis is derivation — one of them a chart-template literal whose drift is invisible and silent

scripts/tests/test_etcd_scrape.py opens by saying its cross-file assertions are written as DERIVATIONS "rather than as a third hardcoded copy of the same values". It then contained two hardcoded copies.

(1) METRICS_PORT_NAME = "http-metrics" — and this one is the dangerous one, because it is NOT a values key. It is a CHART-TEMPLATE literal: the chart composes the Service port name as `{{ list "http-metrics" | append $portName | join "-" }}`. So it is not a string this repo sets, and not a string a diff of this repo would ever show moving. A chart bump that renames or suffixes it makes the VMServiceScrape reference a port the Service does not have; the operator then generates NO SCRAPE CONFIG AT ALL, producing zero targets and no error — the exact silent failure this file exists to prevent, surviving all 15 green tests, with the constant and the values file happily agreeing with each other about a name the cluster no longer uses.

FIXED by deriving it: _rendered_metrics_port_name() reads the port name off the rendered Service (_rendered_kube_etcd_objects()["Service"], already in hand and module-cached from the phase-2 helm render, so no second render). It asserts the Service renders exactly one port and that the port is named — a chart that renders several would force a choice, and that choice belongs stated in the test rather than implied by [0].

(2) `service.port == 2381 and service.targetPort == 2381` — a literal 2381 in a file whose whole thesis is that the port lives in the ConfigPatch and everything else agrees with it. FIXED by deriving from urlparse(_listen_metrics_urls()).port, the same derivation test_listener_port_matches_the_scrape_target_port already uses. The failure message now names the ConfigPatch as the source of the expected value.

MUTATION-CHECKED. Changing kubeEtcd.vmScrape.spec.endpoints[0].port to "metrics" fails with "must name port `http-metrics` — the port name the chart actually gives the Service it renders (derived from helm template, not from a literal in this file)". Importantly this ALSO proves the derivation is genuinely independent of the values file: the expected value stayed http-metrics while the values said metrics, i.e. the Service port name is chart-derived and the two really are different sources.

<!-- fr:journal kind=finding scope=plan id=i6-hot-file-bullet-was-3345-chars created=2026-08-03T14:38:50 state=fixed -->
### i6-hot-file-bullet-was-3345-chars · finding [fixed] · The hot-file gotcha bullet was 3,345 chars in a file whose first line says 'one-line reminders only'

agents/rules/frank-gotchas.md is an ALWAYS-LOADED agent context file, and its first line reads "One-line reminders only. Each section header points at a per-topic file under docs/runbooks/frank-gotchas/ for full prose". The etcd bullet came in at 3,345 characters — the longest of 61 bullets in the file (median 237) — and restated most of the 250-line grafana.md entry it points at.

That is a real cost, not a style complaint: every agent session in this repo pays for it in context, and a hot file that duplicates its own runbook stops being a index and becomes a second copy to keep in sync.

Cut to 1,147 characters (no longer the longest bullet in the file), keeping exactly what a reader needs to recognise the shape and know where to go:
  - the shape, now stated as TWO failure modes rather than one (per i2): empty Endpoints on Talos because etcd is a host system service, AND kube-scheduler's populated-Endpoints/failing-scrape at up=0
  - the diagnosis, both halves: `kubectl -n kube-system get endpoints | grep -E 'etcd|scheduler'` and `count(up==0) by (job)`
  - the etcd_request_*/requests_*/lease_*/bookmark_* = APISERVER STORAGE CLIENT warning, with the allowed families
  - the fix in one clause, including that the ConfigPatch is a PRE-MERGE gate and why
  - a pointer to grafana.md

Dropped (all already in grafana.md): the render-vs-runtime near-miss, the k8s-app-vs-jobLabel label trap, the two-dashboards/two-VMRule de-duplication warning with uids, the chart-default provenance narrative, and the 148-day framing repeated three times.

<!-- fr:journal kind=finding scope=plan id=minor-sse-shape-test-claimed-more-than-it-asserted created=2026-08-03T14:39:09 state=fixed -->
### minor-sse-shape-test-claimed-more-than-it-asserted · finding [fixed] · The SSE-shape test's docstring covered three provisioning failures it never checked; conditions:[{}] passed

test_etcd_rules_use_the_three_step_sse_shape claims to guard the A -> B -> C shape that Grafana 12.x requires, on the grounds that a malformed rule fails provisioning with sse.parseError and is then absent from the evaluator while still present in the file — "the most deceptive failure available". Three of the checks that claim covers were missing, and each is a SILENT no-op rather than a loud rejection:

  1. datasourceUid on refIds B and C was never asserted. B and C are expression nodes, not datasource queries; `__expr__` is the sentinel routing them to the server-side expression engine. Point either at the VictoriaMetrics uid and Grafana asks VictoriaMetrics to execute `type: reduce`. Now asserted against a named constant EXPRESSION_DATASOURCE_UID.

  2. B's `reducer` was never checked. A reduce node with no reducer has nothing to reduce with. All 48 reduce nodes in alert-rules-cm.yaml use `last` (counted, not assumed), which is the right reducer for rules that alert on the current value. Now asserted.

  3. C's threshold conditions were only COUNTED to 1 — so `conditions: [{}]` passed. That is a threshold node with no threshold: structurally complete, and a rule that can never fire. Now asserts conditions[0].evaluator.type is present (gt/lt/within_range) and evaluator.params is a non-empty list, i.e. that there is both a comparison and a value to compare against.

MUTATION-CHECKED: flipping layer-2-etcd-member-down's reducer last -> mean fails naming the rule, the observed value, the expected value and why.

The general shape is the one this whole plan is about, applied to a test: a docstring that describes a guard is not the guard. It reads as coverage — which is what "grep etcd in VMUI and conclude etcd is monitored" also did.

<!-- fr:journal kind=finding scope=plan id=minor-status-and-endpoints-selector-caveat created=2026-08-03T14:39:59 state=fixed -->
### minor-status-and-endpoints-selector-caveat · finding [fixed] · Plan status was 'Not Started' with four of five phases landed; and the -l k8s-app selector is correct only AFTER this merges

Two small corrections, the second more interesting than it looks.

1. docs/superpowers/plans/.../ _prose.md said "**Status:** Not Started" with phases 1-4 complete. Set to "In Progress — phases 1-4 complete; phase 5 pending operator apply (task 1 is a PRE-MERGE gate, tasks 2-3 are post-merge evidence)". Kept on one line, matching the convention every other _prose.md in the repo uses.

2. The runbook and the operating post both gave `kubectl -n kube-system get endpoints -l k8s-app=kube-etcd`, from the phase-2 finding that the Endpoints object is labelled k8s-app while jobLabel sits on the Service. That finding is correct — about the CHART-RENDERED STATIC Endpoints object this layer introduces. It is not correct about the object on the cluster today.

Verified live 2026-08-03, before the merge:
  endpoints/...-kube-etcd  labels: {..., jobLabel: kube-etcd,
                                    endpoints.kubernetes.io/managed-by: endpoint-controller}
No k8s-app at all. Today the Endpoints object is created by the ENDPOINT CONTROLLER, which copies the Service's labels onto it — and the Service carries jobLabel. Once the chart renders a static Endpoints object, the labels come from the chart instead, and k8s-app is what appears.

So each selector works in exactly one era and returns an empty set in the other — and an empty set is precisely the answer that reads as "the Endpoints object is gone" at the moment you are asking whether it is empty. Same trap as the original finding, one layer up: the fix for a misleading selector was another selector that is misleading at a different time.

Caveated in both places (grafana.md's Trap section now shows the live pre-merge labels and says which era each selector belongs to; the operating post's code comment does the same), and both now say: when unsure, list without a selector. The bare listing is correct in both eras, which is why it is the first command in the diagnosis block.

<!-- fr:journal kind=finding scope=plan id=followup-html-metacharacters-in-ten-preexisting-rules created=2026-08-03T14:40:00 state=open -->
### followup-html-metacharacters-in-ten-preexisting-rules · finding [open] · FOLLOW-UP: ten pre-existing alert rules carry HTML metacharacters in annotations; the etcd guard is deliberately scoped to the six new rules

test_no_etcd_annotation_contains_html_metacharacters checks only the six layer-2-etcd-* rules. The reviewer noted that widening it to the whole feature-health folder would surface roughly TEN pre-existing violations in other rules — annotations containing a bare <, > or & — each of which is a live instance of the Telegram HTML-400 trap (the alert fires, the contact point is configured, Telegram rejects the message with 400, and nothing arrives; the only trace is an ngalert.notifier line in the Grafana log, which is indistinguishable from the alert not having fired).

DELIBERATELY NOT WIDENED IN THIS PR. Fixing ten unrelated rules' annotations would triple the diff of a branch about etcd and bury the change under edits to rules nobody is reviewing here. Left OPEN rather than silently scoped: the guard's narrowness is a decision, and the reason it is narrow is a known defect elsewhere, not an absence of one.

WORTH DOING SEPARATELY, and it is a small piece of work: widen the assertion to every rule in apps/grafana-alerting/manifests/alert-rules-cm.yaml, fix the ten annotations (spell comparisons out in words, write NODE_IP rather than a bracketed placeholder — the convention layer-1-nic-link-flap adopted after it was bitten on 2026-06-08), and the class is closed repo-wide instead of for six rules. Note the same widening would need to tolerate whatever the pre-existing rules legitimately need; the etcd six were written to the constraint from the start, so they cost nothing.

Also unrelated but adjacent, from the same review: the three FIFTEEN_MINUTE_EXEMPTIONS added by phase 2 were judged legitimate and are untouched.
