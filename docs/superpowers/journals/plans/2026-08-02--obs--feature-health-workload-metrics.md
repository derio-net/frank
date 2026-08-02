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

<!-- fr:journal kind=finding scope=plan id=5cfd15c9efbd created=2026-08-02T22:53:59 phase=1 state=open -->
### 5cfd15c9efbd · finding [open] · The migration set is TWELVE rules, not eleven — layer-8-observability-down also uses kube_pod_status_ready (phase 1)

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
