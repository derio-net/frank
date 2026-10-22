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
