# Telegram alert brevity — design

**Layer:** obs (Grafana alerting, Layer 8 observability)
**Status:** Draft

## Problem

The `Telegram - Willikins` contact point (`apps/grafana-alerting/manifests/contact-points-cm.yaml`)
sets no `message`, so Grafana uses its built-in default template. On a phone a single page
holds, in order: a `Value: A=0, B=0, C=0` line, every label (15 in the
`layer-15-workflows-down` example, most of them scrape plumbing such as `job`, `instance`,
`prometheus`, `service`, and the kube-state-metrics pod's own `pod`/`container`), both
annotations, the rule source URL and a silence URL roughly 900 characters long, built from
every label. The operator has to dig the two lines that matter (what broke, what to run) out
of about twenty.

Every one of the 65 provisioned rules carries `summary` and 58 carry `runbook` (one also
carries `description`), so a template that leads with those covers the fleet without
touching any rule.

## Requirements

R1. A firing alert renders as a compact block: a header line `🔥 FIRING · <severity> · <alertname>`, the `summary` annotation, a `Where:` line of identity labels when any are present, a `Fix:` line carrying the `runbook` annotation when present, a `Rule:` link, and a `Silence:` link.
R2. The firing block never prints the `Value:` line, the full label set, or Grafana's all-labels silence URL.
R3. The `Where:` line shows only identity labels, in this order when present: `namespace`, the workload (`workload`, else `deployment`, `statefulset`, `daemonset`, `cronjob`), `node`, `persistentvolumeclaim`, and `pod` only when the alert's `job` is not `kube-state-metrics` (on kube-state-metrics series the `pod` label names the exporter, not the subject).
R4. A resolved alert renders as exactly one line: `✅ RESOLVED · <alertname> — <summary>`, with no runbook and no links.
R5. The `Silence:` link pre-fills only the `__alert_rule_uid__` matcher, so it silences every instance of that rule.
R6. A grouped notification renders, in this order: at most 5 firing blocks; when more than 5 are firing, one `… +N more firing — <alert list link>` line; at most 5 resolved one-liners; when more than 5 are resolved, one `… +N more resolved` line.
R7. The Telegram receiver keeps `parse_mode: None`; the template adds no HTML or Markdown markup.
R8. The change is limited to the Telegram receiver. The Health Bridge and alert-agent webhooks keep their JSON payloads unchanged.
R9. The template text contains no `$` character, so Grafana's provisioning env-var interpolation (which expands `$NAME` in the same file, e.g. `$FRANK_C2_TELEGRAM_BOT_TOKEN`) can never rewrite it.

## Design

### Where the template lives

Grafana file provisioning accepts a `templates:` list in any alerting provisioning file, next
to `contactPoints:`. Like the notification-policy file, which already mixes `muteTimes:` and
`policies:`, the template goes into the existing `contact-points.yaml` key of
`grafana-alerting-contact-points`. It is therefore mounted by the existing `subPath` mount in
`apps/victoria-metrics/values.yaml` (`alerting-contact-points`), so no new mount and no chart
change are needed.

```yaml
templates:
  - orgId: 1
    name: frank-telegram
    template: |
      {{ define "frank.telegram.message" }}…{{ end }}
contactPoints:
  - orgId: 1
    name: "Telegram - Willikins"
    receivers:
      - uid: efi04e0201jb4f
        type: telegram
        settings:
          …
          parse_mode: None
          message: '{{ template "frank.telegram.message" . }}'
```

### Template shape

- `frank.telegram.message` caps each list with Go text/template's builtin `slice`, not with an
  index variable (R9 forbids `$i`): when `gt (len .Alerts.Firing) 5` it ranges over
  `slice .Alerts.Firing 0 5`, and the overflow count is `len (slice .Alerts.Firing 5)`. The
  builtin needs no arithmetic function from Grafana's FuncMap. `.Alerts.Resolved` gets the same treatment.
- `frank.telegram.firing` renders one block (R1, R3, R5). The Rule link is the alert's
  `.GeneratorURL`. Grafana strips `__`-prefixed private labels from the template's `.Labels`,
  so the rule UID for the Silence link comes from that URL instead, via two
  backreference-free `reReplaceAll` calls: drop everything through `/alerting/grafana/`, then
  drop `/view` and everything after it. The silence link is the GeneratorURL's origin plus
  `/alerting/silence/new?alertmanager=grafana&matcher=__alert_rule_uid__%3D<uid>&orgId=1`,
  where the origin is the GeneratorURL with `/alerting/grafana/` and everything after it
  dropped. No link uses `.ExternalURL`, which avoids a possible `//` from a trailing slash.
- `frank.telegram.resolved` renders the R4 one-liner.
- The firing overflow link (R6) is the first firing alert's GeneratorURL origin plus
  `/alerting/list`.
- Whitespace is trimmed with `{{-`/`-}}`, so blocks are separated by exactly one blank line
  and no line has trailing spaces.

### What is deliberately unchanged

- Routing (`notification-policy-cm.yaml`): group_wait, intervals, and the `telegram_direct` /
  `pvc_capacity` routes. They decide *when* and *whether* to send; this change only decides *how
  it reads*.
- The alert rules and their annotations. Rules whose `summary` restates the alertname still
  read fine. Tightening individual summaries is out of scope.
- The `parse_mode: None` pin and its guard (R7).

### Rollout

The contact-points file is read at Grafana boot (`grafana.md`: provisioning files are not
watched), so the merged ConfigMap only takes effect after
`kubectl -n monitoring rollout restart deploy/victoria-metrics-grafana`. The post-merge Test
Plan includes that restart and checks the content of the live ConfigMap first (the "Synced to a
stale revision" gotcha).

## Verification

strategy: live
gate: tester
gate: obs-telegram-group-cap=tester
- obs-telegram-firing-compact: live — rendering through the real notifier into Telegram can only be shown after merge; pre-merge evidence is a Grafana `templates/test` preview render (nothing sent) against firing sample alerts, recorded in the PR
- obs-telegram-resolved-oneline: live — same reason; pre-merge preview render of a resolved sample
- obs-telegram-group-cap: none — verified pre-merge by a `templates/test` preview render of a 7-firing + 2-resolved group, because waiting for an organic flood post-merge is not a plan

Offline, pytest guards in `scripts/tests/` assert that the receiver's `message` references a
defined template, that the template never uses `.Labels.SortedPairs`, `.SilenceURL` or
`.ValueString`, that it contains no `$` (R9), and that `parse_mode: None` survives.

## Test Plan (post-merge — operator-driven)

1. Confirm the live ConfigMap carries the template:
   `kubectl -n monitoring get cm grafana-alerting-contact-points -o jsonpath='{.data.contact-points\.yaml}' | grep frank.telegram.message`
2. `kubectl -n monitoring rollout restart deploy/victoria-metrics-grafana`, then wait for Ready
   and check the boot log for provisioning errors:
   `kubectl -n monitoring logs deploy/victoria-metrics-grafana -c grafana | grep -iE 'provisioning.*(error|fail)'` → empty.
3. Read back what Grafana actually loaded and compare it to the ConfigMap text:
   `GET /api/v1/provisioning/templates/frank-telegram` (admin creds) must equal the `template:`
   block byte for byte (a mismatch means provisioning rewrote it).
4. Watch the next real firing and resolved pair arrive in the C&C chat in the compact form (R1–R5).

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-10-22--obs--telegram-alert-brevity | `derio-net/frank` | `2026-10-22--obs--telegram-alert-brevity` | — |
