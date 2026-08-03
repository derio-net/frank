# Journal: 2026-08-02--obs--feature-health-workload-metrics

<!-- fr:journal kind=discovery scope=plan id=5a58c35a2371 created=2026-08-02T22:53:37 phase=1 -->
### 5a58c35a2371 · discovery · ConfigMap shape: data key is alert-rules.yaml, double YAML load, 35 groups / 37 feature-health rules (phase 1)

apps/grafana-alerting/manifests/alert-rules-cm.yaml is a v1 ConfigMap (metadata.name=grafana-alerting-rules, ns=monitoring) with EXACTLY ONE data key: 'alert-rules.yaml'. Its value is a literal block scalar holding a Grafana provisioning document (apiVersion: 1, top-level keys ['apiVersion','groups']).

Reading a rule therefore needs two loads:
  cm = yaml.safe_load(path.read_text())
  doc = yaml.safe_load(cm['data']['alert-rules.yaml'])

Structure: doc['groups'] is a list of 35 groups; each group carries orgId, name, folder, interval and rules[]. The 'folder' field lives on the GROUP, not the rule — so a flat list of rules loses the routing key. Helper _all_rules() re-attaches it as _folder/_group.

Folder census: feature-health = 37 rules across 33 groups; blog-edge = 3 rules. No other folders.

Global uid uniqueness across the whole document holds today (0 duplicates). Every feature-health rule has noDataState + execErrState present, and severity in {warning(19), critical(18)}.

<!-- fr:journal kind=finding scope=plan id=5cfd15c9efbd created=2026-08-02T22:53:59 phase=1 state=fixed -->
### 5cfd15c9efbd · finding [fixed] · The migration set is TWELVE rules, not eleven — layer-8-observability-down also uses kube_pod_status_ready (phase 1)

> **Closed in phase 3**, which took this entry's own recommended option (a) and
> migrated `layer-8-observability-down` — see `970bfaa0947a` (the `probe_success`
> polarity fix that migration required) and `7cdf97b484a2` (which records the
> strict xfail flipping to `FAILED [XPASS(strict)]` at 12-of-12, forcing its
> retirement — exactly the outcome this entry predicted). State flipped by hand
> in phase 5: `fr journal add --id <existing>` is a no-op rather than an update
> (probed in phase 4, see `7d088477925d`), so there is no CLI path to close a
> finding in place. Body below is phase 1's original analysis, unedited.

RED evidence, verbatim from the tripwire's assertion message:

  AssertionError: feature-health rules still alert on per-pod readiness (kube_pod_status_ready), which fires forever on terminal pods left behind by a node reboot. Migrate them to workload availability - see layer-25-cicd-down for the in-repo precedent. Offending rule uid(s): ['layer-8-observability-down', 'layer-3-networking-down', 'layer-4-storage-down', 'layer-5-gpu-down', 'layer-6-gitops-down', 'layer-10-secrets-down', 'layer-12-agents-down', 'layer-13-auth-down', 'layer-14-vcluster-down', 'layer-15-workflows-down', 'layer-19-rollouts-down', 'layer-24-ingress-down']

The plan and the spec both enumerate ELEVEN rules. The parse finds TWELVE. The extra one is layer-8-observability-down (group layer-8-observability-down, folder feature-health, severity critical, github_issue frank-ops#8, for: 5m, line ~478-540 of the ConfigMap).

Why it was missed: layer-8 is the only rule that already carries a PARTIAL mitigation for this exact defect - its expr wraps kube_pod_status_ready{namespace="monitoring"} in

  ... unless on(namespace,pod) kube_pod_status_phase{namespace="monitoring",phase=~"Succeeded|Failed"} == 1

which is the 'filter tombstones inside the existing query' approach the spec explicitly lists under Rejected alternatives ('Keeps the wrong question and doubles the series joined per evaluation'). It is also structurally different from the other 11: it label_replaces pod -> component and ORs in a probe_success clause for the health-bridge /healthz self-probe, so a mechanical rewrite of the other 11 will not fit it.

CONSEQUENCE FOR PHASE 3 (load-bearing): the tripwire is written folder-wide, exactly as the phase-1 spec dictates, with no per-uid exclusions. So xfail(strict=True) will NOT xpass until layer-8 is migrated too. If phase 3 migrates only 11, the suite stays green with the guard permanently disabled - which is precisely the failure mode strict=True exists to prevent.

Phase 2/3 must pick one, deliberately, and say which:
  (a) migrate layer-8 as well - its monitoring-namespace pod clause becomes kube_deployment_status_replicas_unavailable{namespace="monitoring"} (plus DS/STS clauses as the namespace requires), keeping the probe_success OR-clause and the component label_replace intact; the 'unless' join then becomes dead weight and should go; or
  (b) narrow the tripwire to the 11 named uids - weaker, and it leaves a live instance of the defect class inside the folder the guard claims to cover (the repo has been bitten by exactly this before: the array-item ignoreDifferences tripwire that guarded one file while claiming to guard a class).

(a) is recommended. layer-8 is severity CRITICAL, so a monitoring-namespace tombstone pages harder than the others.

<!-- fr:journal kind=discovery scope=plan id=ce01b07717dd created=2026-08-02T23:05:53 phase=1 -->
### ce01b07717dd · discovery · Baseline correction: the suite is 535 passed / 0 FAILED — the '10 pre-existing test_cnc_staging_* failures' are NOT reproducible (phase 1)

Measured in the isolation worktree, which is at EXACTLY origin/main (git rev-list --count HEAD..origin/main = 0, and origin/main..HEAD = 0), so this IS the clean baseline - no archive-to-/tmp needed.

CLEAN BASELINE (suite minus the new file):
  uv run --frozen pytest scripts/tests/ -q --ignore=scripts/tests/test_feature_health_workload_metrics.py
  -> 535 passed, 1 xfailed in 125.50s     (ZERO failures)

WITH PHASE 1's NEW FILE:
  uv run --frozen pytest scripts/tests/ -q
  -> 542 passed, 2 xfailed in 214.04s     (ZERO failures)

Delta is exactly this phase's contribution: +7 passed, +1 xfailed.

The phase-1 briefing stated 10 pre-existing failures in test_cnc_staging_*. That does not reproduce: test_cnc_staging_host_secrets.py + test_cnc_staging_vcluster_api_netpol.py = 13 passed in 24.34s. The 24s runtime for 13 tests suggests those tests reach live state, so the earlier baseline was probably taken while the cnc-staging vCluster was in a different condition. Phase 2 should use 535/0/1 as the reference, not 10-failures.

The pre-existing xfail (there before this phase) is:
  test_series_index_adoption.py::test_papers_uses_same_layer_name_tag - ASPIRATIONAL, never passed; papers renders via the self-contained {{< papers-roadmap >}} shortcode.
So after phase 1 there are TWO xfails in the suite and only ONE of them is ours.

CI: .github/workflows/repo-tripwires.yml runs "pytest scripts/tests/ -q -rfEx" on every pull_request with NO paths filter, so the new file is a blocking PR gate automatically. The -rx flag means our xfail is PRINTED in the CI log tail rather than hidden - deliberate policy in that workflow ('so a declared-but-unfixed guard stays visible rather than silently green').

<!-- fr:journal kind=discovery scope=plan id=5f622120197e created=2026-08-02T23:06:49 phase=1 -->
### 5f622120197e · discovery · Invariants shipped, and the one the phase spec asked for that is NOT true folder-wide (github_issue) (phase 1)

scripts/tests/test_feature_health_workload_metrics.py ships 8 tests: 1 strict-xfail regression tripwire + 7 invariants that pass today.

Invariants (all mutation-proven, see below):
  test_feature_health_folder_is_populated                          - guards the guards; >=30 rules must parse, else every other assertion is vacuous
  test_migrated_rules_keep_folder_uid_severity_and_tracker         - MIGRATED_RULES expected-dict, 11 uids x {folder, severity, github_issue}
  test_every_feature_health_rule_lives_in_the_feature_health_folder
  test_every_rule_has_a_non_empty_uid_and_uids_are_globally_unique - uniqueness is document-wide, not folder-scoped (Grafana keys uids org-wide)
  test_every_feature_health_rule_has_a_known_severity              - {warning, critical}
  test_layer_tracker_rules_carry_a_well_formed_github_issue_label
  test_every_feature_health_rule_declares_nodata_and_execerr_states

DIVERGENCE FROM THE PHASE SPEC, deliberate. Step P1.T2.S1 says to assert, for EVERY rule in the feature-health folder, a github_issue matching the frank-ops#N pattern - and says these properties are ones the current file already satisfies. It does not. Measured: 11 of the 37 feature-health rules fail that pattern, and none of them is a bug:
  - willikins-owned rules carry a DIFFERENT tracker namespace: exercise-reminder-stale (willikins#11), session-manager-stale (willikins#13), audit-digest-stale (willikins#12)
  - rules with NO github_issue label at all, by design: vk-bridge-stale, vk-bridge-failures, endpoint-down, tls-cert-expiring-14d, tls-cert-expiring-7d, alert-agent-cred-expiry-heartbeat-stale, headscale-api-key-expiry-warning, headscale-api-key-expiry-heartbeat-stale (the last three are telegram_direct dead-man switches - they page the operator, they do not file bugs)

So the assertion is scoped to LAYER-TRACKER rules (uid starting layer-), where it IS universally true: all 21 layer-* rules carry a well-formed frank-ops#N. Writing it folder-wide would have meant either a red test on day one or, worse, 'fixing' eight rules into a tracker they should not have.

Exact severity/tracker snapshot captured into MIGRATED_RULES (this is the before-side of the before/after contract; phase 2/3 must not change any of it):
  layer-3 warning frank-ops#3   | layer-4 warning frank-ops#4   | layer-5 warning frank-ops#5
  layer-6 CRITICAL frank-ops#6  | layer-10 warning frank-ops#10 | layer-12 warning frank-ops#12
  layer-13 CRITICAL frank-ops#13| layer-14 warning frank-ops#14 | layer-15 warning frank-ops#15
  layer-19 warning frank-ops#19 | layer-24 CRITICAL frank-ops#24

MUTATION PROOF (the RED half for properties that already hold). A throwaway harness loaded the module, repointed ALERT_RULES_CM at doctored copies of the ConfigMap, and confirmed each invariant fails on its own violation - 11/11 detected: severity downgrade, folder typo (feature-heath), tracker label deleted, uid renamed, duplicate uid, blank uid, unknown severity value, malformed tracker (frank-ops-9), noDataState deleted, and the whole folder renamed. None of these is a test that merely describes the file.

strict=True was also proven to bite rather than assumed: a scratch test with xfail(strict=True) over a passing assertion reports FAILED [XPASS(strict)], so no repo-level ini setting is neutralising it.

<!-- fr:journal kind=discovery scope=plan id=55a557a79c1d created=2026-08-02T23:34:05 phase=2 -->
### 55a557a79c1d · discovery · RED/GREEN evidence for the 8-rule migration, and the two threshold traps the tests actually caught (phase 2)

RED (5 new tests, all failing against the unmodified ConfigMap, each for the intended reason):

  uv run --frozen pytest scripts/tests/test_feature_health_workload_metrics.py -q
  -> 5 failed, 7 passed, 1 xfailed in 4.23s

Verbatim assertion headlines:
  1. query_only_workload_availability_metrics -> all 8 uids offend with ['kube_pod_status_ready']
  2. fire_when_replicas_are_unavailable_not_when_they_are_ready -> all 8 at {'type': 'lt', 'params': [1]}
  3. wait_five_minutes_before_firing -> {'layer-14-vcluster-down': '10m', 'layer-19-rollouts-down': '10m', 'layer-6-gitops-down': '10m'}
  4. summaries_name_the_workload_not_the_pod -> all 8 summaries interpolate $labels.pod
  5. normalise_kind_in_lowercase -> all 8 'expr never label_replaces a `kind` label'

Failure 3 is the one worth noting: the phase title says "for: 5m", and the spec's
per-rule table says 5m for all eight — but THREE of them were on 10m, not 5m
(layer-6, layer-14, layer-19). So this was not a no-op assertion restating the
file; it forced three real changes. Anyone assuming "5m rules stay 5m" would have
shipped an inconsistent batch.

GREEN, same file: 12 passed, 1 xfailed in 4.48s.
FULL SUITE: 547 passed, 2 xfailed, 0 failed in 131.83s.
  Phase-1 baseline was 542 passed / 2 xfailed, so the delta is exactly +5 = this
  phase's new tests. Zero failures, matching the corrected baseline (the "10
  pre-existing test_cnc_staging_* failures" still does not reproduce).

The strict xfail on test_no_feature_health_rule_uses_pod_readiness is UNTOUCHED and
still XFAILs, correctly: layer-3/4/5 and layer-8 remain on kube_pod_status_ready.
Phase 3 retires it, and only after layer-8.

TEST DESIGN NOTE for phase 3: the new assertions are scoped to an explicit
PHASE_2_UIDS frozenset, not folder-wide, so phase 3's un-migrated rules do not go
red here. Phase 3 should EXTEND that set (or add its own) rather than widening to
the folder while rules are still in flight — the folder-wide statement of intent
is the strict xfail, which is the thing designed to flip exactly once.

Two helpers were added and are reusable: _query_expr(rule) pulls the refId=A
PromQL, _threshold_evaluator(rule) resolves the node named by rule['condition']
(not a hardcoded 'C') and asserts it carries exactly one condition.

<!-- fr:journal kind=discovery scope=plan id=e1d4fa9f157e created=2026-08-02T23:34:29 phase=2 -->
### e1d4fa9f157e · discovery · Live verification: all 8 exprs return series, every series carries workload+kind, all values 0 — and the StatefulSet subtraction joins 13/13 (phase 2)

Verified by extracting each rule's refId=A expr STRAIGHT FROM THE CONFIGMAP (double
YAML load) and POSTing it through Grafana's datasource proxy, rather than retyping
the query — so "what was verified" and "what ships" cannot diverge.

  uid                       series  kinds                         values  for
  layer-6-gitops-down            6  deployment, statefulset       [0]     5m
  layer-10-secrets-down          6  deployment, statefulset       [0]     5m
  layer-12-agents-down           5  deployment                    [0]     5m
  layer-13-auth-down             2  deployment                    [0]     5m
  layer-14-vcluster-down         1  statefulset                   [0]     5m
  layer-15-workflows-down        7  deployment, statefulset       [0]     5m
  layer-19-rollouts-down         1  deployment                    [0]     5m
  layer-24-ingress-down          1  deployment                    [0]     5m

Zero series carry a missing `workload` or `kind` label (checked explicitly, not
inferred) — so the summary/runbook templates cannot render an empty resource path.
Every value is 0 on a healthy cluster, which is the correct quiet state for `gt 0`;
the same reading under the OLD `lt 1` threshold would have fired all 8 rules
permanently. That is the polarity check, and it is the reason the values column is
recorded rather than just the counts.

THE SUBTRACTION JOINS CLEANLY. `kube_statefulset_status_replicas -
kube_statefulset_status_replicas_ready` is a default (all-labels) vector match, so a
single divergent label between the two metrics would silently DROP the series and
produce a rule that can never fire. Measured cluster-wide:
  count(kube_statefulset_status_replicas - kube_statefulset_status_replicas_ready) = 13
which equals the total StatefulSet count — 13 in, 13 out, nothing dropped. Both
metrics come from the same kube-state-metrics target, so their label sets are
identical; `on(namespace,statefulset)` is unnecessary here. Phase 3 gets the same
guarantee for free, but should re-run that count if it ever queries across targets.

Also measured, as a movement check: cluster-wide there is currently NOTHING with
`kube_deployment_status_replicas_unavailable > 0` or a positive StatefulSet
difference. So the 0s above are the cluster's true state, not a dead metric — the
counters exist for all 13 STS / all queried Deployments, they are simply at 0.

Grafana access details for anyone repeating this: plain HTTP on 192.168.55.203
(https gets a TLS reset), basic auth admin / secret victoria-metrics-grafana
.data.admin-password in ns monitoring, datasource proxy uid P4169E866C3094E38.

<!-- fr:journal kind=discovery scope=plan id=9381c4ebfc6d created=2026-08-02T23:34:57 phase=2 -->
### 9381c4ebfc6d · discovery · Four judgement calls phase 3 should copy or contradict deliberately: dropped pod-shape filters, authentik scope, $values.B.Value, and the workload census (phase 2)

1. TWO pod-shape filters were dropped, not just layer-14's.
   The brief named layer-14's `pod=~".*-[0-9]+$"` as disappearing. layer-15 had the
   same class of filter — `pod!~".*-init-.*"`, excluding postgres-vk-init-electric-*
   Job pods — and it is dropped for the identical reason the spec gives for
   layer-14: a Job pod is not owned by a Deployment or a StatefulSet, so querying
   kube_deployment_*/kube_statefulset_* excludes it BY CONSTRUCTION. Carrying it
   over would have been an inert filter implying Jobs could still appear.
   Same reasoning retires layer-12's rationale for its regex (Sympozium's
   developer-team-* Job pods) — but layer-12's regex is KEPT, because it also
   scopes to named control-plane workloads, which is still meaningful.
   Both drops are stated in the in-file comments, not silent.

2. layer-13-auth-down stays DEPLOYMENT-ONLY, despite the spec table saying
   "Deploy + STS".
   The spec's "Kinds present" column is a namespace census feeding the `for:`
   decision, not a mandate to query every kind — and the spec separately names
   `authentik-(server|worker).*` among the regexes that carry over. The
   authentik-postgresql StatefulSet was OUTSIDE this rule before the migration, so
   including it would be new coverage smuggled in under a rewrite. Left out, with a
   comment saying so. Worth a follow-up on its own merits: Authentik's Postgres
   being down absolutely breaks SSO, and nothing currently watches it as a Layer 13
   signal.

3. Annotations use `{{ $values.B.Value | printf "%.0f" }}`, not the spec's
   `{{ $value }}`.
   In Grafana unified alerting `$value` renders the verbose multi-ref form
   (`[ var='B' labels={...} value=1 ]`), which is unreadable in a Telegram/tile
   summary. The in-repo precedent at the vk-bridge-failures rule already uses
   `$values.B.Value | printf "%.0f"` over an identical A->B->C structure, and B is
   the reduce node in every rule here. Phase 3 should match this, not the spec text.

4. Live workload census per namespace (kubectl, 2026-08-02) — phase 3 will want
   this shape of check before writing its own clauses:
     argocd            5 Deploy + 1 STS (argocd-application-controller IS a STS)
     infisical         1 Deploy + 2 STS (postgresql, redis-master)
     external-secrets  3 Deploy
     sympozium-system  5 Deploy — `nats` is a DEPLOYMENT on Frank, not a StatefulSet
     authentik         2 Deploy + 1 STS
     n8n-01            1 Deploy + 1 STS ; agents 3 Deploy ; paperclip-system 1 Deploy + 1 STS
     argo-rollouts     1 Deploy ; traefik-system 1 Deploy
   No DaemonSet in any of the eight — which is what justifies `for: 5m` for this
   batch and is the whole basis of the phase split.

5. PRE-EXISTING COVERAGE GAP, carried over unchanged and flagged in-file:
   layer-14's namespace regex `vcluster-.*` does NOT match `cnc-staging-vcluster`
   (the namespace is suffixed, not prefixed). So that vCluster has never been
   covered by the Layer 14 alert — before or after this migration. Live check:
   kube_statefulset_status_replicas{namespace=~".*vcluster.*"} returns
   cnc-staging-vcluster/cnc-staging AND vcluster-experiments/experiments, but the
   rule only ever sees the second. Deliberately NOT widened mid-migration (that is a
   coverage change, not a query rewrite); it deserves its own change.

<!-- fr:journal kind=finding scope=plan id=0e085f03cc03 created=2026-08-02T23:41:04 phase=2 state=fixed -->
### 0e085f03cc03 · finding [fixed] · Reverted an unintended sensitivity change: three rules normalised 10m -> 5m (phase 2)

Phase 2 implemented the spec decision "for: 15m on DaemonSet-bearing rules, 5m
elsewhere" faithfully, which silently tightened three rules that had been
deliberately set to 10m:

- `layer-6-gitops-down` (ArgoCD, **critical**)
- `layer-14-vcluster-down`
- `layer-19-rollouts-down`

The spec was wrong, not the implementation. This change swaps the METRIC a rule
watches; it is not licence to re-tune sensitivity. Tightening a critical alert
from 10m to 5m raises the chance of firing during a slow rollout — the exact
false-positive class this work exists to remove.

Corroborating evidence found after the fact: `layer-25-cicd-down` — the in-repo
precedent, migrated to workload metrics in 2026-05 and cited throughout this
spec as the pattern to follow — sits at **10m**. So the repo had already made
this call once, in the same direction, and the spec contradicted it.

**Fixed:** all three restored to 10m. The guard
`test_phase_2_rules_wait_five_minutes_before_firing` was replaced with
`test_phase_2_rules_preserve_their_pre_migration_for_window`, backed by a per-uid
`PHASE_2_EXPECTED_FOR` map instead of a blanket constant — so a future window
change must be written down deliberately rather than falling out of a rewrite.
Red on exactly the three rules before the fix, 12 passed / 1 xfailed after.

Spec decision 2 amended with the correction.

**For phase 3:** do NOT assume the surviving rules should be 5m either.
`layer-4-storage-down` is currently at **10m** and moves to 15m only because it
queries a DaemonSet metric. `layer-8-observability-down` is at 5m and must STAY
at 5m.

<!-- fr:journal kind=finding scope=plan id=970bfaa0947a created=2026-08-03T00:05:37 phase=3 state=fixed -->
### 970bfaa0947a · finding [fixed] · The probe_success clause could NOT be preserved verbatim — the threshold inversion silently inverts it too (phase 3)

THE find of phase 3, and the second time the design spec has been wrong in the
same direction (after phase 2's `for:` normalisation and the `\$value` vs
`\$values.B.Value` correction).

The spec, the plan step and the phase brief all say the same thing about
layer-8-observability-down: keep its `probe_success` clause for
`http://health-bridge.monitoring.svc.cluster.local:8080/healthz` VERBATIM,
because "that is an end-to-end probe ... and entirely unaffected by this
migration".

Its SELECTOR is unaffected. Its POLARITY cannot be.

  probe_success == 1  means the probe SUCCEEDED.

The old rule read it under `lt 1`, so 0 (failure) fired. The migration inverts
the threshold to `gt 0` because the workload branches now count UNAVAILABLE
replicas. A verbatim `probe_success` OR'd into that expression therefore:

  * fires CONTINUOUSLY while health-bridge is healthy (value 1 > 0), and
  * goes SILENT the moment health-bridge dies (value 0, not > 0).

Exactly backwards, at severity: critical, on what the spec itself calls the
sharpest signal in the folder — and the diff that produces it is the careful,
obedient one. This is the same class of error as the threshold inversion the
plan already guards ("backwards fires constantly or never and both look
plausible"), except it hides in a clause everyone was told not to touch.

FIX: `probe_success{instance="..."} == bool 0`, which maps success->0 and
failure->1, matching the polarity of the unavailable-replica counts it is
unioned with. Measured live before shipping:

  probe_success{instance="...healthz"}              -> 1 series, value 1
  probe_success{instance="...healthz"} == bool 0    -> 1 series, value 0
  label_replace(... == bool 0, "component", ...)    -> 1 series, value 0,
                                                       component=probe/health-bridge-healthz

`== bool` retains all labels except __name__, so the label_replace and the
`or` union are unaffected.

GUARD: test_layer_8_inverts_the_self_probe_to_match_the_new_threshold asserts
`probe_success{...} == bool 0` by regex, with the whole reasoning in the
docstring. RED before the fix, green after.

The spec text was NOT amended (phase 3 does not own it) — phases 4-5 should
treat the spec's "preserved verbatim" line as corrected by this entry.

<!-- fr:journal kind=finding scope=plan id=680ae632958d created=2026-08-03T00:06:15 phase=3 state=fixed -->
### 680ae632958d · finding [fixed] · Two pod-name regexes were UNSAFE to carry over — cilium-.* drops the cilium DaemonSet, longhorn-manager-.* matches nothing at all (phase 3)

The spec says the existing pod-name regexes "carry over as workload-name
regexes" and that they get *simpler*. True in spirit, but two of the three
phase-3 rules break outright if you carry the regex over LITERALLY, and both
failures are silent.

A pod regex has to tolerate the name suffix kubernetes appends
(`cilium-8x4kt`, `longhorn-manager-p2wjq`); a workload regex matches the
workload NAME. Measured live against VictoriaMetrics before writing anything:

  daemonset=~"cilium-.*"           -> 1 series  [cilium-envoy]        <- TRAP
  daemonset=~"cilium.*"            -> 2 series  [cilium, cilium-envoy]
  deployment=~"cilium.*"           -> 1 series  [cilium-operator]

  daemonset=~"longhorn-manager-.*" -> 0 series                        <- TRAP
  daemonset="longhorn-manager"     -> 1 series  [longhorn-manager]

layer-3: `cilium-.*` silently drops the `cilium` DaemonSet — the cilium AGENT,
the single most important workload in the rule — while still matching
cilium-envoy and cilium-operator. The rule would return series, pass every
structural assertion in the test file, verify "non-empty" against live data,
and simply never watch the agent again. `cilium.*` restores exactly the set the
pod query covered (all three workloads); this is coverage PRESERVATION, not
widening.

layer-4: `longhorn-manager-.*` matches NO workload, so the rule returns zero
series and can never fire. Under noDataState: OK that is perfectly quiet — a
rule that has been deleted in all but name. This is the same shape as the
vector-match hazard the brief warned about (a rule that can never fire looks
identical to a healthy one).

Neither is catchable by a diff review or by any assertion about rule structure;
the only thing that catches them is querying the live series set and reading
the workload names back. Both selectors are documented in-file with the
measured before/after series counts, so the next person does not "tidy" them
back.

GENERALISATION for phases 4-5 and for any future rule: after rewriting a
selector from pod-shaped to workload-shaped, assert the RETURNED WORKLOAD NAMES
against `kubectl get deploy,ds,sts`, not just that the result is non-empty.
Non-empty was true for the broken layer-3.

<!-- fr:journal kind=finding scope=plan id=86ffb32eb446 created=2026-08-03T00:07:58 phase=3 state=fixed -->
### 86ffb32eb446 · finding [fixed] · Excluding the monitoring DaemonSets is a real coverage loss, and the spec's stated compensating control does not exist (phase 3)

> **Closed in phase 4** by `layer-8-observability-collectors-down` — see entry
> `a88e5d462f7b`. Body below is phase 3's original analysis, unedited. State
> flipped by hand: `fr journal add --id <existing>` is a no-op rather than an
> update (probed), so there is no CLI path to close a finding in place.

Flagged, not fixed — per the phase-2 precedent of surfacing pre-existing/created
gaps rather than folding them into a query rewrite.

layer-8-observability-down previously matched EVERY pod in `monitoring`, which
included the pods of both DaemonSets: `fluent-bit` and
`victoria-metrics-prometheus-node-exporter`. The migrated rule queries
Deployments and StatefulSets only, so those two are now unwatched. That
exclusion is deliberate and well-argued (it is what lets this critical rule keep
`for: 5m` instead of moving to the 15m drain-tolerant window), but the spec
justifies it with a claim that does not hold:

  "node-level collectors whose unavailability during a node drain is exactly
   the noise this work removes, and whose real coverage is the Layer 1/2 node
   alerts"

Checked, because it is the kind of reassuring sentence that never gets checked:

  layer-1-hardware-down : kube_node_status_condition{condition="Ready",status="false"}
  layer-2-os-down       : the same, joined to kube_node_role{role="control-plane"}

Both key on a NODE going NotReady. Neither can see fluent-bit crashlooping on a
perfectly Ready node. Grepping the whole ConfigMap for `fluent-bit` and
`node-exporter` finds four hits each and every one is a comment or a
`job="node-exporter"` label selector — there is no rule anywhere that alerts on
either DaemonSet's health.

What DOES partially cover them, indirectly:
  * node-exporter feeds layer-1-node-memory-headroom and layer-1-nic-link-flap,
    so a fleet-wide node-exporter failure eventually shows up as those rules
    losing data;
  * fluent-bit is the transport for the crowdsec-canary and alert-agent
    cred-expiry heartbeats into VictoriaLogs, and both have dead-man rules — so
    a fleet-wide fluent-bit failure pages via those.

Both are fleet-wide-only and arrive late. A single-node collector failure is
invisible either way, before or after this change; the difference is that
before, a fluent-bit pod stuck NotReady on one node did fire layer-8 (along
with, admittedly, every tombstone on that node — which is the defect being
removed).

RECOMMENDATION (its own change, not this one): a small DaemonSet-availability
rule over `kube_daemonset_status_number_unavailable{namespace="monitoring"}` at
`for: 15m`, severity warning, which is drain-tolerant by construction and would
be automatically consistent with the folder-wide policy guard shipped in this
phase. Deliberately NOT added here: widening coverage under cover of a rewrite
is exactly what phase 2 refused to do with layer-13's authentik-postgresql
StatefulSet and layer-14's cnc-staging-vcluster namespace.

The in-file comment on layer-8 and the docstring of
test_layer_8_watches_deployments_and_statefulsets_but_not_daemonsets were both
written to state this honestly rather than repeat the spec's claim.

<!-- fr:journal kind=discovery scope=plan id=7cdf97b484a2 created=2026-08-03T00:08:30 phase=3 -->
### 7cdf97b484a2 · discovery · RED/GREEN + live series counts for all four rules, the xfail retirement, and the two durable policy guards (phase 3)

RED (task 1, the three DaemonSet-bearing rules), verbatim headlines:
  6 failed, 14 passed, 1 xfailed in 6.83s
  1. query_only_workload_availability_metrics -> all 3 offend with ['kube_pod_status_ready']
  2. actually_query_daemonsets                -> all 3 never query kube_daemonset_status_number_unavailable
  3. fire_when_replicas_are_unavailable       -> all 3 at {'type':'lt','params':[1]}
  4. wait_out_a_node_drain                    -> layer-3 5m, layer-4 10m, layer-5 5m
  5. summaries_name_the_workload_not_the_pod  -> all 3 interpolate \$labels.pod
  6. normalise_kind_in_lowercase              -> all 3 'expr never label_replaces a `kind` label'
GREEN: 20 passed, 1 xfailed.

RED (task 3, layer-8): 5 failed, 22 passed, 1 xfailed.
  Two of the seven layer-8 assertions PASSED red — keeps_the_health_bridge_self_probe
  and keeps_its_five_minute_window_and_critical_severity. That is correct and
  deliberate: they are preservation assertions, so passing before the edit is
  what makes them a genuine before/after contract rather than a description of
  the edit's output.
GREEN: the strict xfail flipped to `FAILED [XPASS(strict)]` — 1 failed, 27 passed.
  That is the marker working exactly as phase 1 designed it: 12 of 12 rules
  migrated, so the only way back to green was deleting it. Marker removed,
  docstring rewritten to record what it caught, `import pytest` (now unused)
  dropped. Final: 28 passed, 0 xfailed in that file.

FULL SUITE: 563 passed, 1 xfailed, 0 failed.
  Baseline at phase start was 547 passed / 2 xfailed / 0 failed, identical to
  phase 2's. Delta = +16 passed / -1 xfailed = 15 new tests plus the retired
  xfail becoming a pass. The one remaining xfail is the pre-existing
  test_series_index_adoption.py::test_papers_uses_same_layer_name_tag.

LIVE VERIFICATION (exprs read out of the ConfigMap by double YAML load and
POSTed through the Grafana datasource proxy, never retyped; each top-level `or`
branch queried SEPARATELY):

  uid                       whole  branches                          kinds                   values
  layer-3-networking-down       3  1 deployment + 2 daemonset        deployment, daemonset   [0]
  layer-4-storage-down          1  1 daemonset (single branch)       daemonset               [0]
  layer-5-gpu-down             12  3 deployment + 9 daemonset        deployment, daemonset   [0]
  layer-8-observability-down   10  8 deployment + 1 statefulset + 1 probe                    [0]

  Every series carries workload+kind (layer-3/4/5) or component (layer-8) —
  checked explicitly, so no annotation can render an empty resource path. Every
  value is 0, the correct quiet state under `gt 0`; the same readings under the
  old `lt 1` would have fired all four rules permanently. layer-8's components
  render as deployment/<name>, statefulset/victoria-logs-victoria-logs-single-server
  and probe/health-bridge-healthz, and fluent-bit / node-exporter are absent —
  confirming the DaemonSet exclusion took effect.

  StatefulSet subtraction join, re-measured as the brief required:
    count(kube_statefulset_status_replicas - ..._ready) = 13 = count(..._replicas) = 13
    scoped to monitoring: 1 in, 1 out. Nothing dropped.
  DaemonSet metric coverage: count(kube_daemonset_status_number_unavailable) = 17
    = count(kube_daemonset_status_current_number_scheduled) = 17, i.e. the
    counter exists for every DaemonSet in the cluster, so the 0s are real
    readings and not a missing metric.

TWO DURABLE POLICY GUARDS (folder-wide, they outlive this migration):
  test_rules_that_watch_daemonsets_tolerate_a_node_drain
      DaemonSet metric in expr => for: 15m
  test_the_fifteen_minute_window_is_reserved_for_daemonset_rules
      for: 15m => DaemonSet metric in expr

They key off the METRIC, never the namespace. The plan's P3.T1.S1 asked for the
namespace-selector derivation plus the converse "every other feature-health rule
has for: 5m", and P3.T3.S1 already warned to re-check that converse. It is
decisively FALSE: the folder holds for: values of 0m, 0s, 1m, 2m, 5m, 10m, 30m,
1h, 2h and 3h, with SIX rules at 10m on purpose — including layer-25-cicd-down,
the in-repo precedent this whole spec cites. Asserting it would have forced a
mass re-tune under cover of a query rewrite, i.e. re-committed the exact mistake
phase 2 caught and reverted. A namespace-derived guard was also rejected: it
encodes live cluster state that drifts silently, and it would misfire on layer-8,
which sits in a DaemonSet-bearing namespace and deliberately does not query them.
Both guards were vacuous at RED time and are non-vacuous now (3 rules matched).

<!-- fr:journal kind=discovery scope=plan id=6e02f009b033 created=2026-08-03T00:09:01 phase=3 -->
### 6e02f009b033 · discovery · Three judgement calls, and a baseline warning: the DEVCONTAINER lacks kustomize and hugo, so the suite must be run on the host (phase 3)

1. BASELINE — run the suite on the HOST, not via `fr isolation exec`.
   Phase 1 recorded that "the 10 pre-existing test_cnc_staging_* failures do NOT
   reproduce". It depends entirely on where you run it, and this cost real time:

     fr isolation exec -- uv run --frozen pytest scripts/tests/ -q
       -> 10 failed, 530 passed, 8 skipped, 1 xfailed
     cd <worktree> && uv run --frozen pytest scripts/tests/ -q
       -> 547 passed, 2 xfailed, 0 failed

   Same 549 tests collected both ways, so it is not a collection difference. All
   10 failures are `FileNotFoundError: [Errno 2] No such file or directory:
   'kustomize'` (confirmed: 10 of 10) and all 8 skips are "hugo not installed" —
   the devcontainer has neither binary, the host has both at /usr/local/bin. The
   missing hugo also eats the pre-existing xfail (it lives in
   test_series_index_adoption.py), which is why the container reports 1 xfail
   where the host reports 2 — a discrepancy that reads like our own marker
   misbehaving and is nothing of the kind.

   So the earlier briefs and phase 1 were each right about their own
   environment. Use the host for the suite; use `fr isolation exec` for cluster
   reads (kubectl/curl), which is what it is needed for.

2. layer-4-storage-down ships as a SINGLE-branch expr, not an `or`.
   The plan step and the phase brief both anticipate a Deployment branch ("if
   the deployment branch of its `or` returns nothing that is correct"). There is
   no such branch, deliberately. `longhorn-manager` exists only as a DaemonSet;
   the Deployment selector returns 0 series and structurally always will
   (verified live). Phase 2 set the precedent by stripping layer-14's
   `pod=~".*-[0-9]+\$"` and layer-15's `pod!~".*-init-.*"` as inert clauses that
   imply a shape that cannot occur, and phase 2 shipped single-kind exprs for
   five rules (layer-12/13/19/24 deployment-only, layer-14 statefulset-only). An
   always-empty Deployment clause here would be the same cargo cult. The
   "verify both branches separately" instruction is satisfied by verifying the
   one branch that exists AND separately confirming no longhorn-system
   Deployment matches the name.

3. layer-8 normalises onto `component`, NOT `workload`/`kind`.
   Every other migrated rule uses workload+kind, and the phase-3 kind test is
   scoped to the three DaemonSet rules for that reason. layer-8 cannot follow:
   its third branch is a `probe_success` series that has no workload to name, so
   a summary interpolating \$labels.workload would render EMPTY for the single
   sharpest signal in the folder. `component` is the pre-existing convention on
   this rule (it produced `pod/<name>`) and it carries over as `<kind>/<name>`
   plus the unchanged `probe/health-bridge-healthz` — one readable summary
   across three unlike branches. Guarded by
   test_layer_8_normalises_every_branch_onto_a_component_label, which asserts
   all three component values are present.

   Related: layer-8's RUNBOOK deliberately interpolates nothing. `rollout status
   {{ \$labels.component }}` would render `rollout status
   probe/health-bridge-healthz` on the probe branch — a paste-able command that
   is garbage, at 03:00, on a critical alert. The summary names the failing
   component; the runbook stays valid for all three branches.

FOR PHASES 4-5:
  * The folder is now 12-of-12 migrated and the regression tripwire is LIVE
    (no marker). Any new feature-health rule using kube_pod_status_ready fails
    the suite immediately — including the new `workload-unexpectedly-scaled-to-
    zero` rule phase 4 adds, which must also satisfy the two policy guards: it
    is spec'd at `for: 15m` while querying `kube_deployment_spec_replicas`, and
    that combination will FAIL test_the_fifteen_minute_window_is_reserved_for_
    daemonset_rules. Decide deliberately: either give it a different window, or
    widen that guard with a written rationale. Do not delete the guard.
  * `PHASE_2_EXPECTED_FOR` and the phase-3 uid frozensets are per-batch scaffolding.
    The two policy guards and the tripwire are the parts meant to last.

<!-- fr:journal kind=finding scope=plan id=1c4e89951ebc created=2026-08-03T00:32:30 phase=4 state=fixed -->
### 1c4e89951ebc · finding [fixed] · Applying the folder's `gt 0` convention to the spec'd `== 0` expr yields a rule that can NEVER fire — PromQL `== 0` is a filter, not a comparison (phase 4)

The third time the design spec has been wrong in the same direction, and the
same shape as phase 3's `probe_success` polarity finding: an obedient,
convention-following diff produces a rule that is structurally incapable of
firing, and nothing in the YAML looks wrong.

The spec gives the new rule's expr as:

    kube_deployment_spec_replicas{namespace!~"ollama|comfyui",deployment!~"litellm"} == 0

and states no threshold. The folder convention established in phases 2-3, and
restated in the phase-4 brief, is `evaluator: {type: gt, params: [0]}`. Pairing
the two ships a dead rule.

In PromQL `metric == 0` (without `bool`) is a **filter**, not a comparison. It
returns the matching series carrying their ORIGINAL value — which for this
filter is, necessarily, always 0. So the reduce node hands the threshold a 0 on
exactly the series that should alert, and `gt 0` never fires on any of them.

Measured live before writing the rule, so this is not an argument from the
docs:

    kube_deployment_spec_replicas == 0
      -> 2 series: comfyui/comfyui = 0, litellm/litellm = 0

The values are `0`, not `1`. That reading IS the evidence.

The convention is correct where it came from and does not transfer here.
`kube_deployment_status_replicas_unavailable` and the StatefulSet difference
COUNT something, so `> 0` is the natural condition. `spec_replicas == 0` is
already the whole condition; the presence of a series is the alert, and the
value is a constant.

SHIPPED: `== 0` filter + `evaluator: {type: lt, params: [1]}`, with
`noDataState: OK` keeping the healthy case (no series at all) quiet. This is
the one rule in the folder whose threshold is `lt`, which reads exactly like
the pre-migration readiness threshold the whole change removed — a future
reader "tidying" it to `gt 0` would silently delete the rule. So the guard
`test_the_scale_to_zero_rule_fires_on_the_series_its_filter_returns` asserts
the `== 0` / `lt 1` PAIRING, not either half: moving to `== bool 0` requires
inverting to `gt 0` in the same edit, and vice versa. The reasoning is in the
docstring and in the in-file comment.

`== bool 0` + `gt 0` was the considered alternative and is equally correct. It
was rejected on cost, not on principle: `bool` drops the filter, so every
non-excluded Deployment in the cluster (measured: 73) goes through the reduce
node on every 1m evaluation for a signal that is normally empty.

FOR PHASE 5: if the acceptance criteria or any doc restates "every rule in this
folder thresholds at gt 0", that is now false, deliberately, for exactly one
rule.

<!-- fr:journal kind=finding scope=plan id=a88e5d462f7b created=2026-08-03T00:32:56 phase=4 state=fixed -->
### a88e5d462f7b · finding [fixed] · CLOSES 86ffb32eb446 — the monitoring-DaemonSet coverage phase 3 dropped is restored by layer-8-observability-collectors-down (phase 4)

Closing phase 3's open finding `86ffb32eb446` rather than shipping it.

RESTATEMENT OF THE GAP (re-verified, not taken on trust): the pre-migration
layer-8 query matched every pod in `monitoring`, which included the pods of both
DaemonSets there — `fluent-bit` and
`victoria-metrics-prometheus-node-exporter`. Migrating layer-8 to Deployments +
StatefulSets dropped them, and the spec justified that with "their real coverage
is the Layer 1/2 node alerts". Both `layer-1-hardware-down` and `layer-2-os-down`
query `kube_node_status_condition{condition="Ready",status="false"}`: they fire
when a NODE goes NotReady and are blind to a collector crashlooping on a healthy
one. So this was a regression THIS work introduced, not a pre-existing gap.

FIXED by a new rule, `layer-8-observability-collectors-down`:

    label_replace(
      label_replace(
        kube_daemonset_status_number_unavailable{namespace="monitoring"},
        "workload", "$1", "daemonset", "(.*)"),
      "kind", "daemonset", "", "")

  for: 15m | severity: warning | github_issue: frank-ops#8 | gt 0

LIVE VERIFICATION (expr read out of the ConfigMap by double YAML load and POSTed
through the Grafana datasource proxy, never retyped):

    series: 2
      monitoring/fluent-bit                                kind=daemonset  value=0
      monitoring/victoria-metrics-prometheus-node-exporter kind=daemonset  value=0

Exactly the two DaemonSets that went unwatched, both carrying `workload` and a
lowercase `kind`, both at 0 — the correct quiet state under `gt 0`.

FOUR DESIGN CHOICES, each with a reason rather than a default:

1. SEPARATE rule, not folded back into layer-8. The folder policy is that any
   rule querying a DaemonSet metric waits 15m for a node drain. Folding these
   two in would therefore drag layer-8 from 5m to 15m — slowing detection of the
   ALERTING STACK's own failure, at severity critical, to fix a warning-level
   gap. That is a worse trade than the gap.

2. `for: 15m` needs NO exemption. It queries a DaemonSet metric, so it satisfies
   `test_the_fifteen_minute_window_is_reserved_for_daemonset_rules` on its
   merits. A guard asserts it is absent from `FIFTEEN_MINUTE_EXEMPTIONS`, so
   nobody "helpfully" adds a redundant allowlist entry — an allowlist that
   accumulates unnecessary entries is how it becomes a rubber stamp.

3. `severity: warning`, not critical. Losing fluent-bit stops log shipping and
   losing node-exporter stops node metrics, both real degradations — but
   vmagent / vmsingle / grafana are Deployments still covered at critical/5m by
   layer-8 proper, so the alerting stack itself is not blind.

4. Scoped to `namespace="monitoring"` with NO name selector, deliberately
   unlike the layer trackers (which name specific control-plane workloads).
   Every DaemonSet in `monitoring` is a collector, so a third one added later is
   covered without anyone remembering to extend a regex.

DOCS BROUGHT INTO LINE, as the plan step required: the layer-8 in-file comment
and the docstring of
`test_layer_8_watches_deployments_and_statefulsets_but_not_daemonsets` both
previously stated the gap honestly and pointed at an open finding. They now
point at this rule, and reframe layer-8's DaemonSet exclusion as a ROUTING
decision between two rules rather than a hole.

<!-- fr:journal kind=discovery scope=plan id=469490d31aab created=2026-08-03T00:33:32 phase=4 -->
### 469490d31aab · discovery · How the 15m guard collision was resolved (widened, not gutted), the derived exclusion set, and live verification in both directions (phase 4)

THE GUARD COLLISION, resolved deliberately.

Phase 3 shipped `test_the_fifteen_minute_window_is_reserved_for_daemonset_rules`
("15m => the expr queries a DaemonSet metric"). The new scale-to-0 rule is
spec'd at `for: 15m` while querying `kube_deployment_spec_replicas`, so it fails
that guard by construction — phase 3 flagged this in advance.

RESOLUTION: widened to "15m requires EITHER a DaemonSet metric OR an entry in
`FIFTEEN_MINUTE_EXEMPTIONS` carrying a written reason". The exemption's VALUE is
the justification string, not a bare uid, so an entry cannot be added without
writing down why. The guard's actual purpose survives intact: it was never
"forbid 15m", it was "15m is never adopted silently", and an allowlist of prose
converts "quietly set 15m" into "write down why", which is the behaviour being
protected.

The rationale recorded for the one entry: a Recreate-strategy Deployment passes
through 0 replicas on EVERY ordinary rollout (k8s tears the old pod down before
creating the new one), and several Frank apps are on Recreate precisely because
their PVC is RWO — so a short window would page on routine deploys of exactly
the apps most likely to be deployed by hand. Noted in-file: this is a settle-time
allowance, not a sensitivity dial. The condition is BINARY (replicas are 0 or
they are not), so 15m buys tolerance for a transition rather than blunting a
threshold — which is why it is a different kind of request from the one the
guard exists to refuse.

A second guard, `test_the_fifteen_minute_exemptions_are_live_and_reasoned`,
stops the allowlist rotting: an entry whose rule has moved off 15m or been
deleted FAILS (a stale exemption silently pre-approves whatever next claims the
uid), and a reason under 80 characters FAILS. That test was RED at first run for
the right reason — the exempted rule did not exist yet — which also proves the
stale-entry half bites rather than being decorative.

THE DERIVED EXCLUSION SET. Both parsers were sanity-read against their sources
before being trusted:

  gpu-switcher WORKLOADS env var    -> {(ollama, ollama), (comfyui, comfyui)}
  apps/**/rollout.yaml, scaleDown   -> {(litellm, litellm)}
  rollout files seen                -> apps/litellm/manifests/rollout.yaml
                                       apps/sympozium-extras/manifests/rollout.yaml

The sympozium file IS parsed and correctly excluded (its workloadRef leaves
`scaleDown` at the default `never`), so the derivation is discriminating rather
than accidentally right.

The test asserts three separate things, not one: (a) the negative matchers are
exactly {namespace, deployment} — any other exclusion label is coverage removed
without a declarative source; (b) the namespace literals set-equal the WORKLOADS
namespaces; (c) the deployment literals set-equal the onsuccess-Rollout names.
`_alternation_literals` refuses a non-literal alternative (e.g. `litellm.*`)
with an explicit message, because "covers exactly the derived set, no more and
no less" is only a checkable claim while the alternatives are literal names.

A fourth test asserts the SPLIT is not arbitrary:
`test_the_scale_to_zero_rule_still_watches_the_litellm_namespace` fails if any
namespace holding an onsuccess Rollout is excluded wholesale. The two mechanisms
are not interchangeable — the GPU namespaces exist to be timeshared so excluding
them wholesale is honest, whereas `litellm` is a normal namespace that happens to
contain one Rollout-managed Deployment.

LIVE VERIFICATION, both directions (exprs read out of the ConfigMap, never
retyped):

  shipped expr                                        -> 0 series   (correct: quiet)
  same expr with the exclusions stripped              -> 2 series   comfyui/comfyui=0
                                                                    litellm/litellm=0
  shipped selector WITHOUT the `== 0` filter          -> 73 series  (the population it watches)
  kube_deployment_spec_replicas{namespace="litellm"}  -> 1 series   litellm=0
  kube_deployment_spec_replicas{namespace="ollama"}   -> 1 series   ollama=1

Reading of those five:

* Zero series is the correct quiet state, and the 73-series count is what proves
  it is quiet because nothing is wrong rather than because the selector matches
  nothing. "A rule returning nothing because it matches nothing is
  indistinguishable from a correct one until it matters" — the exclusion-stripped
  query proves the FILTER works; the unfiltered selector proves the SELECTOR
  does.
* litellm's Deployment really is at 0 while its Rollout serves 5/5. A naive rule
  would have paged on a completely healthy LLM gateway on day one.
* `ollama` is currently at 1 (it holds gpu-1 right now), so its exclusion is
  INERT today and load-bearing the moment the timeshare switches. Anyone
  re-measuring at a different moment will see comfyui and ollama swap places;
  neither reading contradicts the other.
* The litellm namespace holds exactly one Deployment today, so excluding by
  deployment name rather than namespace currently costs nothing — the property
  it protects is about what lands there later.

FULL SUITE: 573 passed, 1 xfailed, 0 failed (host, not the devcontainer).
Baseline at phase start re-measured at 563 passed / 1 xfailed / 0 failed, so the
delta is exactly +10 = this phase's tests. RED was 10 failed / 28 passed, each
for its intended reason.

<!-- fr:journal kind=discovery scope=plan id=d16e09b1d11f created=2026-08-03T00:33:53 phase=4 -->
### d16e09b1d11f · discovery · The sympozium-apiserver rollout comment claims its Deployment is scaled to 0; it is not, and believing it would over-broaden the exclusion set (phase 4)

Small, but it is exactly the kind of thing the derivation exists to defeat.

`apps/sympozium-extras/manifests/rollout.yaml` opens with:

    # workloadRef: Rollout reads pod template from the Helm chart's Deployment.
    # The Deployment is scaled to 0 — this is expected and correct.

That is false. The Rollout's `workloadRef` sets no `scaleDown`, so it takes the
Argo Rollouts default of `never` and the Deployment keeps running. Measured
live:

    kube_deployment_spec_replicas{namespace="sympozium-system"}
      nats=1  sympozium-apiserver=1  sympozium-controller-manager=1
      sympozium-otel-collector=1  sympozium-webhook=2

    kube_deployment_spec_replicas == 0   (cluster-wide, no exclusions)
      -> comfyui/comfyui, litellm/litellm    (sympozium-apiserver absent)

Anyone deriving the exclusion set by READING the rollout files' prose — rather
than by parsing `workloadRef.scaleDown` — adds `sympozium-apiserver` to the
exclusions and silently stops watching a Deployment that is supposed to be up.
Same failure mode as the design spec's first draft reading the GPU set out of a
ClusterRole: the comment is the trap, the field is the fact.

The guard is immune by construction (it keys on `scaleDown == "onsuccess"`), and
it does parse that file — verified, so its correctness is discriminating rather
than incidental. The scale-to-0 rule's in-file comment now records the
discrepancy so the next reader is not misled by it either.

NOT FIXED HERE: the comment in `apps/sympozium-extras/manifests/rollout.yaml` is
still wrong. It is outside this plan's scope (a different app's manifest, and
the file is otherwise correct), and it is now contradicted in writing at the
place where believing it would do damage. Worth a one-line follow-up.

<!-- fr:journal kind=discovery scope=plan id=7d088477925d created=2026-08-03T00:44:05 phase=4 -->
### 7d088477925d · discovery · `fr journal add --id <existing>` is a NO-OP, not an update — a finding cannot be closed in place by the CLI, and one from phase 1 is still stale (phase 4)

Mechanical, but it silently strands exactly the state that matters most in a
journal: whether a finding is still open.

`fr journal add --help` documents `--id` as "Stable id; re-adding the same id is
idempotent." Idempotent here means the second add DOES NOTHING — it does not
update the entry's state, title or body. Probed directly (with a deliberately
obvious PROBE title/body, against a backup) and the journal file came back
byte-identical to the backup. So there is no CLI path to flip a finding from
`open` to `fixed`.

The prescribed workaround, which the phase-4 plan step spells out, is to add a
NEW `--state fixed` entry referencing the old id. That records the fix, but the
ORIGINAL entry still renders as `finding [open]` forever, and
`fr journal render` is what a reviewer reads. A plan whose findings are all
resolved can therefore look like it is shipping with open findings.

DONE HERE for `86ffb32eb446`: the `state=` token in its HTML marker was flipped
to `fixed` by hand and a short "Closed in phase 4, see a88e5d462f7b" note
prepended. Phase 3's analysis body is left verbatim — the state field is the
part that is supposed to change when a finding is resolved; the prose is not.

STILL STALE, and deliberately NOT touched here: `5cfd15c9efbd` (phase 1, "The
migration set is TWELVE rules, not eleven") still reads `[open]`. It was in fact
resolved in phase 3, which chose the entry's own recommended option (a) and
migrated `layer-8-observability-down` — that is precisely why the strict xfail
flipped to `FAILED [XPASS(strict)]` and had to be retired, as phase 3's own
discovery `7cdf97b484a2` records. Left for phase 5/6 rather than rewritten here:
closing the finding my brief named is in scope, quietly editing another phase's
ledger beyond that is not. It is a one-token flip on line ~17 of the journal
file when someone wants it.

GENERAL: after any phase that fixes a previously-recorded finding, check
`fr journal render ... | grep 'finding \[open\]'` before declaring the phase
done. The count is the check; the CLI will not maintain it for you.

<!-- fr:journal kind=discovery scope=plan id=4cdbab53758b created=2026-08-03T00:57:37 phase=5 -->
### 4cdbab53758b · discovery · The brief's '13 rules touched' is 14 — and every documented measurement was re-verified live rather than copied from the journal (phase 5)

DOCUMENTATION PHASE, so the only available 'test' is that each claim is true.
Every factual statement written into the gotcha bullet and the runbook section
was re-derived from the ConfigMap, the manifests or the live cluster at phase-5
time. Two claims changed as a result.

1. RULE COUNT. The phase-5 brief says '13 rules touched, not the 11 the plan
   first named'. Measured by diffing the parsed ConfigMap between origin/main
   and HEAD (uid-keyed, YAML-normalised, so a formatting-only change cannot
   register):

     ADDED   2  layer-8-observability-collectors-down,
                workload-unexpectedly-scaled-to-zero
     CHANGED 12 layer-3, -4, -5, -6, -8, -10, -12, -13, -14, -15, -19, -24
     REMOVED 0
     TOTAL  14

   So it is 14, not 13. The docs say 14. `layer-25-cicd-down` is UNCHANGED on
   this branch — it was already migrated in 2026-05 and is the precedent, so
   anyone counting 'rules now on workload metrics' gets 15 and anyone counting
   'rules this change touched' gets 14. Both numbers are right for different
   questions; the docs state which.

2. LIVE RE-MEASUREMENT, re-run through the Grafana datasource proxy at phase-5
   time rather than trusting phase 2-4's numbers:

     kube_deployment_spec_replicas == 0            -> 2 series, BOTH value '0'
                                                      (comfyui/comfyui, litellm/litellm)
     count(shipped selector, filter stripped)      -> 73
     count(kube_statefulset_status_replicas
           - ..._ready)                            -> 13   = count(..._replicas) 13
     daemonset=~'cilium.*'                         -> 2    | 'cilium-.*'  -> 1
     daemonset='longhorn-manager'                  -> 1    | 'longhorn-manager-.*' -> 0

   All identical to phase 2-4. The `== 0` result is the load-bearing one: the
   values are literally '0', which IS the evidence that `== 0` is a filter
   returning original values, not a comparison returning 1. It is quoted in the
   runbook for that reason.

   The GPU timeshare is in the same position as at phase 4 (ollama holds the
   GPU at 1, comfyui at 0), so the exclusion for `ollama` remains inert today
   and load-bearing after the next switch. The runbook says so explicitly,
   because a reader re-measuring at a different moment will see them swapped
   and would otherwise think one of the two readings is wrong.

3. LIVE STATE for the two Rollout cases, since the whole scale-to-0 exclusion
   set rests on them:

     deploy/litellm             spec.replicas=0  available=<none>
     rollout/litellm            desired=5 ready=5 available=5
     deploy/sympozium-apiserver 1/1/1
     rollout/sympozium-apiserver ready=1  spec.workloadRef.scaleDown=<none>

4. Infrastructure claims checked before writing them: the Grafana Deployment is
   `victoria-metrics-grafana` in ns monitoring (the restart command in the
   runbook would otherwise be wrong), and
   .github/workflows/repo-tripwires.yml does run `pytest scripts/tests/` on
   `pull_request` with NO `paths:` filter, so the guard file really is a
   blocking PR gate.

FULL SUITE after all edits: 573 passed, 1 xfailed, 0 failed (host) — identical
to the phase-4 baseline, as a documentation phase should be.

<!-- fr:journal kind=discovery scope=plan id=e0bb00a91cfa created=2026-08-03T00:58:08 phase=5 -->
### e0bb00a91cfa · discovery · Two documentation defects fixed at the source: a stale journal state marker, and a manifest comment that would have caused the exact damage the alert prevents (phase 5)

Both are 'just docs' and both are load-bearing.

1. LEDGER HYGIENE. `5cfd15c9efbd` (phase 1, 'the migration set is TWELVE rules')
   still rendered `finding [open]` although phase 3 resolved it by taking that
   entry's own recommended option (a) and migrating layer-8. Because
   `fr journal add --id <existing>` is a no-op rather than an update (probed in
   phase 4, `7d088477925d`), a resolved plan renders as if it is shipping with
   an open finding — and `fr journal render` is exactly what a reviewer reads
   before approving the PR.

   Flipped both the `state=` token in the HTML marker and the rendered `[open]`
   in the heading, and prepended a pointer to the two entries that close it
   (`970bfaa0947a`, `7cdf97b484a2`). Phase 1's analysis body is left VERBATIM:
   the state field is the part that is supposed to change when a finding is
   resolved; the prose is the historical record and is not.

   `86ffb32eb446` was checked as instructed and needed nothing — phase 4 had
   already flipped it correctly and attached its closing note.

   VERIFIED by the check phase 4 recommended:
     fr journal render ... | grep -c 'finding \[open\]'  -> 1
   and that single hit is at line 839, inside phase 4's own PROSE describing the
   problem, not an entry heading. All SEVEN findings in the ledger now render
   `[fixed]`. Worth noting for anyone repeating the check: the grep is
   self-referential, so a raw count is not the answer — look at where it hits.

2. THE SYMPOZIUM COMMENT (recorded as a follow-up in phase 4's `d16e09b1d11f`,
   fixed here). `apps/sympozium-extras/manifests/rollout.yaml` opened with
   'The Deployment is scaled to 0 — this is expected and correct.' Re-verified
   false against live state before touching it:

     deploy/sympozium-apiserver             1/1/1
     rollout/sympozium-apiserver ready=1  spec.workloadRef.scaleDown=<none>

   No `scaleDown` means the Argo Rollouts default `never`, so the Deployment is
   supposed to be up — the opposite of what the comment said.

   This matters beyond tidiness. The `workload-unexpectedly-scaled-to-zero` rule
   exists precisely to catch a Deployment that is at 0 and should not be, and its
   exclusion set is the list of workloads that are allowed to be at 0. Anyone
   deriving that set by READING the rollout files' prose adds
   `sympozium-apiserver` to it and silently stops watching a live control-plane
   component — the alert's own blind spot, created by a comment. The CI guard is
   immune (it keys on `scaleDown == 'onsuccess'` and does parse this very file,
   so its correctness here is discriminating rather than incidental), but the
   human reading path was not.

   Rewritten to state what the field actually says, contrast it explicitly with
   apps/litellm/manifests/rollout.yaml (which DOES set `scaleDown: onsuccess`),
   record the live verification, and tell the reader that the exclusion set is
   derived by parsing — so the correct response to adding `scaleDown` here is to
   let the guard pick it up, not to hand-edit the alert. COMMENT ONLY: no
   `scaleDown` added, no behaviour change, `git diff` touches nothing but the
   leading comment block.

GENERAL: this is the second instance in this plan of the same shape — the
design spec's first draft derived the GPU scale-to-0 set from a ClusterRole, and
this comment would have derived it from prose. The field is the fact; the
comment is the trap. Both the runbook section and the gotcha one-liner say so in
those terms.

<!-- fr:journal kind=discovery scope=plan id=25fc5818c254 created=2026-08-03T00:58:39 phase=5 -->
### 25fc5818c254 · discovery · What the documentation deliberately does NOT say, and where each trap was placed so the next person hits it (phase 5)

Placement was the actual design work here; the content came from the ledger.

THE ONE SENTENCE THAT MUST NOT BE WRITTEN. The obvious summary of this plan is
'every feature-health rule now thresholds at gt 0'. It is FALSE for exactly one
rule and the brief flagged it. Both documents therefore state the exception in
the same breath as the convention, and the runbook sets it off in a block quote
so a skimmer cannot pick up the convention without the exception. The runbook
also says outright that 'tidying' `== 0` + `lt 1` to `gt 0` silently deletes the
rule, and names the guard that asserts the PAIRING — because the only durable
defence is that the next reader learns the pairing is intentional before they
'fix' it.

PLACEMENT DECISIONS.

* `docs/runbooks/frank-gotchas/grafana.md` gets the prose, as a new `##` section
  ADJOINED to phase 1's 'Node-shutdown tombstones flood the feature-health
  alerts (2026-08-02)' rather than duplicating it. The tombstone section's
  closing 'Standing exposure' subsection ended with 'Neither is done; the triage
  tool now classifies the flood correctly instead' — which this work makes FALSE.
  Rewritten to '### Standing exposure — CLOSED, see the next section', keeping
  the half that is still true (tombstones still accumulate; nothing lowers
  --terminated-pod-gc-threshold) and linking forward. Leaving a stale 'not done'
  next to the section that does it is how a runbook starts lying.

* The 2026-05 section '## kube_pod_status_ready false-positives in batch
  namespaces' (the layer-25 origin story) gained a two-line forward pointer.
  Its fix (a) is now folder-wide policy, and a reader landing there via search
  would otherwise stop at the 2026-05 view and re-derive the traps themselves.

* `agents/rules/frank-gotchas.md` gets ONE new bullet plus a short clause
  appended to the existing tombstone bullet. The index file is one long bullet
  per gotcha, so 'one-liner only' is satisfied by density, not brevity. Two
  bullets rather than one because the tombstone bullet's topic is the TRIAGE
  CLASSIFIER — burying four PromQL traps inside it means nobody searching for
  'probe_success' or 'pod regex' finds them.

WHAT WENT IN THE RUNBOOK BUT NOT THE INDEX (deliberately, to keep the bullet
navigable): the five-metric table; `$values.B.Value` vs `$value` and layer-8's
`component` normalisation; layer-8's runbook annotation interpolating nothing on
purpose; the verification recipe (read the expr OUT of the ConfigMap by double
YAML load, POST it through the datasource proxy, query each `or` branch
SEPARATELY, assert on returned workload NAMES and on the VALUES being 0); and
the three known coverage limits carried forward unwidened (layer-13's
authentik-postgresql, layer-14's cnc-staging-vcluster, layer-8's DaemonSet
routing).

THE ONE PIECE OF ADVICE MOST LIKELY TO SAVE SOMEONE: 'after rewriting a selector
from pod-shaped to workload-shaped, assert the RETURNED WORKLOAD NAMES against
kubectl get deploy,ds,sts — never just non-empty.' It appears in BOTH documents
because non-empty was true for the broken layer-3, which is what makes that trap
survive code review, structural tests and a live smoke check simultaneously.

SPEC STATUS left at `Draft` as instructed; phase 6 sets it to Deployed. Also
left alone: the spec's own body, which is wrong in three places now corrected by
findings (the `for:` normalisation, 'preserve probe_success verbatim', and the
`== 0` threshold). Phase 3 declined to amend it on the grounds that it does not
own the spec, and the runbook now carries the corrected version, so the spec is
the historical design record and the runbook is the operational truth. If phase
6 wants them reconciled, the findings name every divergence.

<!-- fr:journal kind=finding scope=plan id=a89020abe620 created=2026-08-03T01:01:02 phase=5 state=fixed -->
### a89020abe620 · finding [fixed] · Caught in my own draft: 'exactly one feature-health rule thresholds at lt 1' is FALSE — twelve do, and the gt 0 convention belongs to unavailability counters, not the folder (phase 5)

The phase-5 brief's trap #1 says: do NOT write 'every feature-health rule
thresholds at gt 0', because the scale-to-0 rule is deliberately `lt 1`. My
first draft obeyed that instruction and then OVERSHOT it, writing:

  'Exactly one rule thresholds at lt 1, on purpose, and it is documented
   in-file.'

That is a different false claim, arrived at by correcting the first one too
enthusiastically. Measured across the folder before shipping:

  Counter({'gt': 27, 'lt': 12})   over 39 feature-health rules

  lt rules: endpoint-down, agent-pod-not-running,
            workload-unexpectedly-scaled-to-zero,
            layer-1-node-memory-headroom (lt 1073741824),
            layer-11-inference-down, layer-16-media-gen-down,
            gpu-node-both-down, layer-17-edge-down,
            tls-cert-expiring-14d (lt 1209600), tls-cert-expiring-7d (lt 604800),
            alert-agent-cred-expiry-heartbeat-stale,
            headscale-api-key-expiry-heartbeat-stale

`lt` is not exotic in this folder at all — it is the natural threshold for a
probe, a heartbeat dead-man switch, a cert-expiry countdown and the
GPU-timeshare rules, most of which predate this work. `gt 0` is the convention
for UNAVAILABILITY COUNTERS specifically. Stating it as a folder-wide rule (in
either direction) is what created the original spec bug in the first place: the
spec applied 'the folder's gt 0 convention' to a `== 0` filter and produced a
rule that can never fire.

So the accurate claim, now in both documents, is scoped three ways:
  * all 12 MIGRATED rules invert lt 1 -> gt 0  (true, verified)
  * gt 0 is the convention for unavailability COUNTERS, not for the folder
  * among the WORKLOAD-AVAILABILITY rules, workload-unexpectedly-scaled-to-zero
    is the single lt 1, deliberately

FIXED in `docs/runbooks/frank-gotchas/grafana.md` (the block quote now gives the
27/12 census) and in the `agents/rules/frank-gotchas.md` bullet (which also had
'is now FALSE', implying the statement used to be true — it never was; several
of those 12 lt rules are older than this plan).

Also tightened while there: the subsection heading said 'two rules are
exceptions', but the two exceptions are not the same kind of thing — one is a
CLAUSE polarity inside a migrated rule (layer-8's probe_success, whose rule-level
threshold really is gt 0), the other is a whole RULE's threshold (the scale-to-0
rule). Conflating them would send someone looking for a second lt-thresholded
migrated rule that does not exist. Now 'two polarity traps inside that
inversion', with the clause/rule distinction stated.

LESSON, and the reason this is logged as a finding rather than quietly fixed:
the brief warned about exactly one over-broad sentence, and the corrected draft
introduced a second over-broad sentence one line later. A documentation phase
whose whole premise is 'verify every claim' has to apply that to its own
corrections, not just to the material it inherited. The census took one query.

<!-- fr:journal kind=finding scope=plan id=5b55a02a1b89 created=2026-08-03T02:05:44 phase=5 state=fixed -->
### 5b55a02a1b89 · finding [fixed] · This folder is NOT Health-Bridge-only — every rule here pages Telegram (phase 5)

Believed and repeated throughout this work — in the spec, in the acceptance
matrix, and to the operator — that feature-health alerts route to the Health
Bridge only. **False.** Found in code review, confirmed by reading
`apps/grafana-alerting/manifests/notification-policy-cm.yaml` end to end.

Route order (first match wins unless `continue: true`):

    canary_watchdog     -> HB        continue: false
    canary              -> Telegram  perma-muted, continue: false
    telegram_direct     -> Telegram  continue: false
    blog-edge           -> AI Helper continue: false
    gpu_timeshare       -> HB        continue: false
    health_bridge_only  -> HB        continue: false
    severity=critical   -> Telegram  continue: TRUE     <-- both precede
    severity=warning    -> Telegram  continue: TRUE     <-- the folder route
    grafana_folder=feature-health -> HB  continue: false

None of the 14 rules carries an escape-hatch label, so every one delivers to
**Telegram AND Health Bridge** — and did so before this change too. Routing is
genuinely unchanged; only the claim about it was wrong.

The corroboration was in the operator report that started this work: "Grafana is
sending a bunch of alerts." They were noticed. A Health-Bridge-only folder would
have accumulated 25 permanently-firing alerts unseen.

**Why it mattered rather than being a wording slip:**

1. The acceptance row `feature-health-routing-preserved` asserted "Health Bridge
   webhook only, never to Telegram" at `status: ci` — CI appeared to prove a
   false statement, and its notes committed to a phase-6 live verification that
   could only fail. Rewritten to the provable claim (routing INPUTS — folder,
   uid, severity, tracker — are unchanged).
2. The two NEW rules are therefore new pagers. `workload-unexpectedly-scaled-to-zero`
   watches ~73 Deployments cluster-wide on a 15m window, and two procedures this
   repo documents park a Deployment at 0 for far longer: the Longhorn
   instance-manager retirement (`storage-secrets-ssa.md`) and the durable
   scale-to-0 recipe (`frank-argocd.md`). It would have paged on correct
   operator actions — adding noise, in a change whose entire purpose is removing
   it.

**Fixed:** the scale-to-0 rule carries `health_bridge_only: "true"` (the
documented escape hatch, same mechanism `gpu_timeshare` uses), guarded by
`test_scale_to_zero_stays_off_telegram`.
`layer-8-observability-collectors-down` deliberately does NOT carry it — a
collector dying is worth a page — guarded in the opposite direction by
`test_collectors_rule_deliberately_does_page`, so the two cannot drift into each
other. Routing reality documented in `grafana.md`.

<!-- fr:journal kind=finding scope=plan id=73a01ad92e11 created=2026-08-03T02:05:45 phase=5 state=fixed -->
### 73a01ad92e11 · finding [fixed] · layer-8 was the only migrated rule with no folder/tracker guard (phase 5)

Code review mutation-tested the guards and found `layer-8-observability-down`
missing from `MIGRATED_RULES` — the twelfth migrated rule, the folder`s only
`critical` alerting-stack rule, and the one this change repeatedly calls the
sharpest signal in the folder.

Measured before the fix: mutating its group `folder: feature-health` to
`feature-heath`, and its `github_issue` from `frank-ops#8` to `frank-ops#99`,
BOTH passed the entire suite. Its dedicated tests pinned `for:`, severity,
threshold and expr shape — but never folder, never tracker.

A folder typo there drops it off the Health Bridge silently. It would still page
Telegram via the severity route (see the routing finding above), so the loss is
the bug-issue lifecycle — invisible in exactly the way this whole change is
about.

Fixed by adding it to `MIGRATED_RULES`. Re-mutation-checked after the fix: the
tracker mutation now fails `test_migrated_rules_keep_folder_uid_severity_and_tracker`,
the folder mutation fails `test_every_feature_health_rule_lives_in_the_feature_health_folder`.

<!-- fr:journal kind=finding scope=plan id=1a389850aee9 created=2026-08-03T02:05:47 phase=5 state=open -->
### 1a389850aee9 · finding [open] · layer-12 no longer watches the Rollout-managed Sympozium replicas (phase 5)

A genuine coverage narrowing introduced by this migration, found in code review
and recorded rather than fixed — closing it is its own change.

`sympozium-system` runs `sympozium-apiserver` TWICE: once from the Deployment
and once from a blue/green Argo Rollout whose `workloadRef` has no `scaleDown`
(default `never`, so both run). The old pod regex matched both sets of pods.
`kube_deployment_status_replicas_unavailable{deployment="sympozium-apiserver"}`
sees only the Deployment`s.

So the Rollout`s ReplicaSet — which is what the blue/green Service actually
fronts — is now unwatched, and there is no `rollout_*` / `argo_rollouts_*` metric
anywhere in `alert-rules-cm.yaml`. Unlike `litellm`, which is Rollout-managed but
covered end-to-end by the Layer 11 probe, Sympozium has no compensating probe.

Recorded in `grafana.md` under "Known coverage limits". Closing it means either a
Rollouts-aware metric source or an end-to-end Sympozium probe.

<!-- fr:journal kind=discovery scope=plan id=85587b1340bf created=2026-08-03T02:05:48 phase=5 -->
### 85587b1340bf · discovery · A mutation test that does not verify its own mutation proves nothing (phase 5)

While adding `test_scale_to_zero_stays_off_telegram` I mutation-checked it by
deleting the `health_bridge_only` label and re-running. The suite stayed GREEN,
which read as "the new guard is vacuous".

It was not. The mutation had removed the WRONG rule`s label:
`vk-executor-pool-wedged` already carries `health_bridge_only: "true"` earlier in
the same file (it is named in the notification-policy comment as the escape
hatch`s first user), so a `count=1` substitution hit that instead — and nothing
guards that rule`s label, so the suite was correctly green about a mutation that
never touched the rule under test.

Anchoring the substitution on `uid: workload-unexpectedly-scaled-to-zero` before
searching made it fail as intended.

The general shape: a mutation test has TWO assertions, and only one of them is
usually written down. "The guard fails" is worthless without "the mutation
applied where I meant it to". Re-parse the artifact and assert the mutated value
before running the suite — a green result from an unapplied mutation is
indistinguishable from a vacuous guard, and the wrong conclusion is the
comfortable one.

<!-- fr:journal kind=finding scope=plan id=ee382c32c4c3 created=2026-08-03T09:48:55 phase=6 state=fixed -->
### ee382c32c4c3 · finding [fixed] · Post-merge verification: firing set 25 -> 3, the predicted baseline (phase 6)

Phase 6 run 2026-08-03, after PR #756 merged as `b8558529`.

**ArgoCD reconcile lag is real and looks exactly like the stale-revision
gotcha.** Immediately after the merge, `grafana-alerting` reported
`Synced/Healthy` at revision `b3a1a18d` — one commit behind main, and that one
commit was the merge. Asserting on the ARTIFACT rather than the sync status
showed the live ConfigMap still carrying all twelve `kube_pod_status_ready`
rules and neither new rule. It picked up `b8558529` ~2 minutes later on its own,
so this was ordinary lag, not the `argocd.md` stale-revision bug — but the two
are indistinguishable at the moment you look, which is the argument for checking
the artifact every time.

Grafana rolled (`rollout restart deploy/victoria-metrics-grafana`) — provisioning
files are read at boot and never watched, so the merge is inert until this runs.

**Live results:**

| check | result |
|---|---|
| feature-health rules live | 39 |
| still on `kube_pod_status_ready` | **NONE** |
| `workload-unexpectedly-scaled-to-zero` | present, `health_bridge_only: "true"` intact |
| `layer-8-observability-collectors-down` | present |
| firing set | **3** — 2 TLS canaries + 1 gpu_timeshare |
| scale-to-0 expr | 0 series |
| same, exclusions stripped | 2 (`comfyui`, `litellm`) — quiet for the right reason |

25 permanently-firing alerts -> 3. The 3 are exactly the muted/by-design
baseline the spec predicted.

<!-- fr:journal kind=discovery scope=plan id=c9e9bfd7397c created=2026-08-03T09:48:57 phase=6 -->
### c9e9bfd7397c · discovery · Test Plan step 2 is wrong for filter-style rules: NoData IS the healthy state (phase 6)

The Test Plan asserts "zero feature-health rules in `Normal (NoData)`", on the
reasoning that a typo`d metric name yields NoData rather than an error. That
holds for the twelve migrated rules, whose exprs always return series.

It does NOT hold for `workload-unexpectedly-scaled-to-zero`. Its expr is a
PromQL **filter** (`kube_deployment_spec_replicas{...} == 0`), so when nothing
is unexpectedly scaled to zero it returns **no series at all** — and "no series"
is precisely the condition the rule exists to report as healthy. It sits in
`Normal (NoData)` permanently in the good case, with `noDataState: OK` so it
never alerts on that.

Measured: 5 feature-health rules in NoData post-merge; 4 were already there at
session start (the two cert-expiry canary-absent watchdogs, Exercise Reminder
Stale, VK Issue Bridge Failures), so the delta is exactly this rule.

The trap for whoever audits NoData next: this rule looks broken and is not.
Worth a line in `grafana.md` — a filter-style rule inverts the usual reading,
where NoData means "the query is wrong". Same family as the `== 0` / `lt 1`
pairing already documented there, and it follows from the same PromQL fact.
