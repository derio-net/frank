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
