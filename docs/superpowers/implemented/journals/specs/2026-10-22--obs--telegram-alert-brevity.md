<!-- fr:journal-schema=2 -->
# Journal: 2026-10-22--obs--telegram-alert-brevity

<!-- fr:journal kind=discovery scope=spec id=operator-brief created=2026-10-22T04:59:47+00:00 input=true -->
### operator-brief · discovery · Operator brief (verbatim)

(probably the "light" variation). The Grafana notifications in Frank C&C Telegram bot are
unnecessarily verbose. Let's tighten them up. They need to be undesrtandable and actionable.
Example: **Resolved**

Value: A=0, B=0, C=0
Labels:
 - alertname = Layer 15 Agentic Workflows Degraded
 - container = kube-state-metrics
 - deployment = n8n-01
 - endpoint = http
 - github_issue = frank-ops#15
 - grafana_folder = feature-health
 - instance = 10.244.12.53:8080
 - job = kube-state-metrics
 - kind = deployment
 - namespace = n8n-01
 - pod = victoria-metrics-kube-state-metrics-855b9df945-zxn26
 - prometheus = monitoring/victoria-metrics-victoria-metrics-k8s-stack
 - service = victoria-metrics-kube-state-metrics
 - severity = warning
 - workload = n8n-01
Annotations:
 - runbook = kubectl -n n8n-01 rollout status deployment/n8n-01; kubectl -n n8n-01 describe deployment/n8n-01
 - summary = L15 Workflows: n8n-01/deployment/n8n-01 has 0 replica(s) unavailable
Source: https://grafana.cluster.derio.net/alerting/grafana/layer-15-workflows-down/view?orgId=1
Silence: https://grafana.cluster.derio.net/alerting/silence/new?alertmanager=grafana&matcher=__alert_rule_uid__%3Dlayer-15-workflows-down&matcher=container%3Dkube-state-metrics&... (all 15 labels as matchers)&orgId=1

<!-- fr:journal kind=decision scope=spec id=firing-body created=2026-10-22T04:59:47+00:00 decided_by=operator -->
### firing-body · decision · Firing body = compact + identity labels

Operator chose 'Compact + identity labels' over compact-only and minimal: header, summary, Where: (identity labels only), Fix: runbook, Rule and Silence links. decider: operator. Spec R1-R3.

<!-- fr:journal kind=decision scope=spec id=resolved-oneline created=2026-10-22T04:59:47+00:00 decided_by=operator -->
### resolved-oneline · decision · Resolved = one line

Operator chose a one-line resolved message over reusing the firing layout or disabling resolved messages. decider: operator. Spec R4.

<!-- fr:journal kind=decision scope=spec id=silence-rule-scoped created=2026-10-22T04:59:47+00:00 decided_by=operator -->
### silence-rule-scoped · decision · Silence link scoped to the rule UID only

Operator chose a short rule-scoped silence link over instance-scoped or none. decider: operator. Spec R5.

<!-- fr:journal kind=decision scope=spec id=group-cap-5 created=2026-10-22T04:59:47+00:00 decided_by=operator -->
### group-cap-5 · decision · Grouped notifications capped at 5 blocks

Operator chose 'cap at 5 + overflow line'. The overflow line prints the total firing count instead of '+N more' because Grafana's template function set has no arithmetic (spec Design, Template shape). decider: operator. Spec R6.

<!-- fr:journal kind=decision scope=spec id=verification created=2026-10-22T04:59:47+00:00 decided_by=operator -->
### verification · decision · Verification: templates/test preview pre-merge, live post-merge (gate: tester)

Operator chose 'Template preview API + live': pre-merge render via Grafana's templates/test preview (nothing sent) plus offline pytest guards; post-merge, observe a real firing/resolved pair. No .fr/candidate-install, so candidate is unavailable. decider: operator.

<!-- fr:journal kind=finding scope=spec id=spr-1 created=2026-10-22T05:08:05+00:00 state=open review_scope=in -->
### spr-1 · finding [open] (reviewer: in scope) · "No arithmetic, so no +N more" is a false premise — Go text/template builtin `slice` yields the remainder

target: spec. Spec Template-shape overflow bullet, decision group-cap-5 gloss, plan P1.T4.S1 runbook text all claimed no arithmetic was possible; text/template's builtin `slice` (Go 1.13+) gives `len (slice .Alerts.Firing 5)`.

<!-- fr:journal kind=finding scope=spec id=spr-2 created=2026-10-22T05:08:05+00:00 state=open review_scope=in -->
### spr-2 · finding [open] (reviewer: in scope) · R6 contradicts itself on overflow-line placement and leaves resolved overflow undefined

target: spec. R6 'ends with' vs 'resolved follow firing'; matrix row obs-telegram-group-cap echoed 'ends with'; plan T3 set (3) followed the other reading.

<!-- fr:journal kind=finding scope=spec id=spr-3 created=2026-10-22T05:08:05+00:00 state=open review_scope=in -->
### spr-3 · finding [open] (reviewer: in scope) · Pre-merge render bypasses provisioning, so `$` env interpolation and load errors go unchecked

target: plan. contact-points-cm.yaml:16-18 is env-interpolated ($FRANK_C2_TELEGRAM_*); planned template used $i and a $1 backreference; templates/test sees raw text only; no post-restart readback planned.

<!-- fr:journal kind=finding scope=spec id=spr-4 created=2026-10-22T05:08:05+00:00 state=open review_scope=in -->
### spr-4 · finding [open] (reviewer: in scope) · `{{ .ExternalURL }}/alerting/list` may render a double slash

target: plan. Grafana may normalise AppURL with a trailing slash; nothing checked for `//alerting`.

<!-- fr:journal kind=review scope=spec id=spec-plan-review-1 created=2026-10-22T05:08:05+00:00 -->
### spec-plan-review-1 · review · independent spec+plan review: 4 findings (spr-1..spr-4)

Dispatched fr-spec-reviewer checked all 5 operator decisions against R1-R8, R1-R8 coverage in plan 01.yaml (red→green→render→refactor, no placeholders, three rows linked), and file:line reality for contact-points-cm.yaml:3-49, victoria-metrics values.yaml:156-159/227, test_telegram_parse_mode_explicit.py:13-37, grafana.md:29-31/485-504, alert-rules-cm.yaml (65 summary/58 runbook), matrix.yaml:1579-1609. Findings spr-1..spr-4, all in scope.

<!-- fr:journal kind=finding scope=spec id=spr-1-resolved created=2026-10-22T05:08:05+00:00 state=fixed resolves=spr-1 -->
### spr-1-resolved · finding [fixed] · resolves spr-1: "No arithmetic, so no +N more" is a false premise — Go text/template builtin `slice` yields the remainder

R6 now renders '+N more firing'/'+N more resolved' via builtin `slice` (spec Template shape, plan P1.T2.S1); the no-arithmetic claim removed from spec and P1.T4.S1. This restores the operator's original 'Cap at 5 + +N more' choice exactly; the group-cap-5 decision's 'total instead' gloss is superseded by this resolution.

<!-- fr:journal kind=finding scope=spec id=spr-2-resolved created=2026-10-22T05:08:05+00:00 state=fixed resolves=spr-2 -->
### spr-2-resolved · finding [fixed] · resolves spr-2: R6 contradicts itself on overflow-line placement and leaves resolved overflow undefined

R6 rewritten with explicit order (firing blocks, +N more firing line with alert-list link, resolved one-liners, +N more resolved line); matrix row obs-telegram-group-cap reworded to match; plan P1.T3.S2 asserts the order and adds a 7-resolved set (4).

<!-- fr:journal kind=finding scope=spec id=spr-3-resolved created=2026-10-22T05:08:05+00:00 state=fixed resolves=spr-3 -->
### spr-3-resolved · finding [fixed] · resolves spr-3: Pre-merge render bypasses provisioning, so `$` env interpolation and load errors go unchecked

New R9: the template contains no `$` at all (slice instead of range vars, backreference-free reReplaceAll chains), guarded by plan P1.T1.S1 (g). Spec Test Plan gains a boot-log provisioning-error check and a GET /api/v1/provisioning/templates/frank-telegram byte-for-byte readback; runbook note in P1.T4.S1 records both.

<!-- fr:journal kind=finding scope=spec id=spr-4-resolved created=2026-10-22T05:08:05+00:00 state=fixed resolves=spr-4 -->
### spr-4-resolved · finding [fixed] · resolves spr-4: `{{ .ExternalURL }}/alerting/list` may render a double slash

No link uses .ExternalURL any more: silence and alert-list links derive their origin from .GeneratorURL; P1.T1.S1 asserts no .ExternalURL and P1.T3.S2 checks no `//alerting` in rendered links.

<!-- fr:journal kind=decision scope=spec id=exit-baseline created=2026-10-22T05:08:06+00:00 -->
### exit-baseline · decision · exit when spec-review resolved

The exit when spec-review resolved; `fr verification set` and `deliver` compare against it.

```yaml
row_gates:
  obs-telegram-firing-compact: tester
  obs-telegram-group-cap: none
  obs-telegram-resolved-oneline: tester
row_kinds:
  obs-telegram-firing-compact: live
  obs-telegram-group-cap: none
  obs-telegram-resolved-oneline: live
run_gate: tester
run_kind: live
```

<!-- fr:journal kind=decision scope=spec id=exit-change-1 created=2026-10-22T05:38:19+00:00 -->
### exit-change-1 · decision · exit change: row obs-telegram-group-cap -> gate tester

proven pre-merge by the Grafana templates/test preview render (sets 3 and 4, recorded in the PR); the provisioned template only reaches Telegram after merge plus a Grafana restart

before: kinds ['live', 'none'], gates ['tester']
after: kinds ['live', 'none'], gates ['tester']

```yaml
answered_by: none
lowered: []
```
