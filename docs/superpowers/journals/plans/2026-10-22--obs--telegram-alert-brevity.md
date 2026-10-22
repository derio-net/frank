<!-- fr:journal-schema=2 -->
# Journal: 2026-10-22--obs--telegram-alert-brevity

<!-- fr:journal kind=decision scope=plan id=template-in-contact-points-file created=2026-10-22T05:01:40+00:00 -->
### template-in-contact-points-file · decision · Template provisioned in the existing contact-points file

Chosen over a separate mounted templates file (needs a chart-values mount) and an inline message (unreadable, not previewable). One agentic phase; post-merge rollout is Test Plan only.

<!-- fr:journal kind=discovery scope=plan id=telegram-template-preview-renders created=2026-10-22T05:22:32+00:00 phase=1 -->
### telegram-template-preview-renders · discovery · frank-telegram template rendered by Grafana's templates/test endpoint (sets 1-4, verbatim) (phase 1)

Rendered by Grafana 12.3.3's own engine via `POST /api/alertmanager/grafana/config/api/v1/templates/test`
(render only, nothing sent), reached with `kubectl -n monitoring exec deploy/victoria-metrics-grafana -c grafana -- curl ... http://localhost:3000/...`
(curl and wget both exist in the image; no port-forward, no Go fallback). Builtin `slice` and `reReplaceAll` both
work: Grafana's FuncMap does not shadow `slice`. Checked mechanically against R1-R6 (no trailing spaces, no stray blank
lines, no Value/label dump, KSM pod/job/instance/service/container/prometheus absent, exactly one silence matcher,
no `//alerting`, set 3 order 5 blocks -> `+2 more firing` -> 2 resolved, set 4 5 lines -> `+2 more resolved`).
Lengths: set1 490, set2 119, set3 2781, set4 608 chars (all under 4096). Output byte-identical before and after the T4 refactor.

**Set 1 - one firing (layer-15-workflows-down, KSM labels incl. the exporter's pod)**

```text
🔥 FIRING · warning · Layer 15 Agentic Workflows Degraded
L15 Workflows: n8n-01/deployment/n8n-01 has 1 replica(s) unavailable
Where: n8n-01 · n8n-01
Fix: kubectl -n n8n-01 rollout status deployment/n8n-01; kubectl -n n8n-01 describe deployment/n8n-01
Rule: https://grafana.cluster.derio.net/alerting/grafana/layer-15-workflows-down/view?orgId=1
Silence: https://grafana.cluster.derio.net/alerting/silence/new?alertmanager=grafana&matcher=__alert_rule_uid__%3Dlayer-15-workflows-down&orgId=1
```

**Set 2 - one resolved**

```text
✅ RESOLVED · Layer 15 Agentic Workflows Degraded — L15 Workflows: n8n-01/deployment/n8n-01 has 1 replica(s) unavailable
```

**Set 3 - 7 firing (one kubelet-job pod alert) + 2 resolved**

```text
🔥 FIRING · critical · Pod CrashLooping
alert-agent/alert-agent-7c9d4f6b8-qq2lm restarted 6 times in 15m
Where: alert-agent · mini-2 · alert-agent-7c9d4f6b8-qq2lm
Rule: https://grafana.cluster.derio.net/alerting/grafana/pod-crashlooping/view?orgId=1
Silence: https://grafana.cluster.derio.net/alerting/silence/new?alertmanager=grafana&matcher=__alert_rule_uid__%3Dpod-crashlooping&orgId=1

🔥 FIRING · warning · Layer 15 Agentic Workflows Degraded
L15 Workflows: n8n-01/deployment/n8n-01 has 1 replica(s) unavailable
Where: n8n-01 · n8n-01
Fix: kubectl -n n8n-01 rollout status deployment/n8n-01; kubectl -n n8n-01 describe deployment/n8n-01
Rule: https://grafana.cluster.derio.net/alerting/grafana/layer-15-workflows-down/view?orgId=1
Silence: https://grafana.cluster.derio.net/alerting/silence/new?alertmanager=grafana&matcher=__alert_rule_uid__%3Dlayer-15-workflows-down&orgId=1

🔥 FIRING · warning · Layer 15 Agentic Workflows Degraded
L15 Workflows: agents/statefulset/hermes-agent-shell has 1 replica(s) unavailable
Where: agents · hermes-agent-shell
Fix: kubectl -n agents rollout status statefulset/hermes-agent-shell; kubectl -n agents describe statefulset/hermes-agent-shell
Rule: https://grafana.cluster.derio.net/alerting/grafana/layer-15-workflows-down/view?orgId=1
Silence: https://grafana.cluster.derio.net/alerting/silence/new?alertmanager=grafana&matcher=__alert_rule_uid__%3Dlayer-15-workflows-down&orgId=1

🔥 FIRING · warning · Layer 15 Agentic Workflows Degraded
L15 Workflows: paperclip-system/deployment/paperclip has 1 replica(s) unavailable
Where: paperclip-system · paperclip
Fix: kubectl -n paperclip-system rollout status deployment/paperclip; kubectl -n paperclip-system describe deployment/paperclip
Rule: https://grafana.cluster.derio.net/alerting/grafana/layer-15-workflows-down/view?orgId=1
Silence: https://grafana.cluster.derio.net/alerting/silence/new?alertmanager=grafana&matcher=__alert_rule_uid__%3Dlayer-15-workflows-down&orgId=1

🔥 FIRING · warning · Layer 15 Agentic Workflows Degraded
L15 Workflows: agents/deployment/vk-remote has 1 replica(s) unavailable
Where: agents · vk-remote
Fix: kubectl -n agents rollout status deployment/vk-remote; kubectl -n agents describe deployment/vk-remote
Rule: https://grafana.cluster.derio.net/alerting/grafana/layer-15-workflows-down/view?orgId=1
Silence: https://grafana.cluster.derio.net/alerting/silence/new?alertmanager=grafana&matcher=__alert_rule_uid__%3Dlayer-15-workflows-down&orgId=1

… +2 more firing — https://grafana.cluster.derio.net/alerting/list

✅ RESOLVED · Layer 15 Agentic Workflows Degraded — L15 Workflows: agents/deployment/ruvocal has 1 replica(s) unavailable
✅ RESOLVED · Layer 15 Agentic Workflows Degraded — L15 Workflows: agents/statefulset/gbrain has 1 replica(s) unavailable
```

**Set 4 - 7 resolved**

```text
✅ RESOLVED · Layer 15 Agentic Workflows Degraded — L15 Workflows: agents/deployment/wl-1 has 1 replica(s) unavailable
✅ RESOLVED · Layer 15 Agentic Workflows Degraded — L15 Workflows: agents/deployment/wl-2 has 1 replica(s) unavailable
✅ RESOLVED · Layer 15 Agentic Workflows Degraded — L15 Workflows: agents/deployment/wl-3 has 1 replica(s) unavailable
✅ RESOLVED · Layer 15 Agentic Workflows Degraded — L15 Workflows: agents/deployment/wl-4 has 1 replica(s) unavailable
✅ RESOLVED · Layer 15 Agentic Workflows Degraded — L15 Workflows: agents/deployment/wl-5 has 1 replica(s) unavailable
… +2 more resolved
```

<!-- fr:journal kind=decision scope=plan id=separator-by-first-item-split created=2026-10-22T05:22:32+00:00 phase=1 -->
### separator-by-first-item-split · decision · List separators via first-item split, not `slice LIST 0 5` (phase 1)

With no `$` (R9) there is no range index, so a range cannot tell its first item from the rest and
a blank-line separator would either lead or trail. The message therefore renders `index LIST 0`
on its own and ranges over `slice LIST 1 5` (capped) or `slice LIST 1` (uncapped) with a leading
separator. Same cap and count semantics as the plan's `slice LIST 0 5`; the Where line uses the
same idea (each label prints ` ·` only when an earlier label was present).

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t3 created=2026-10-22T05:22:32+00:00 phase=1 -->
### no-refactor-p1-t3 · discovery · no-refactor-because P1.T3 (phase 1)

Render-proof task: it produces evidence (preview renders under scripts/tmp/telegram-preview/), no code of its own to clean; the template's refactor is P1.T4.

<!-- fr:journal kind=finding scope=plan id=p1-r1 created=2026-10-22T05:30:50+00:00 phase=1 state=open review_scope=in -->
### p1-r1 · finding [open] (reviewer: in scope) · missing severity/summary renders Go "<no value>" in header/summary/resolved line (phase 1)

contact-points-cm.yaml:53-54,65 bare {{ .Labels.severity }} / {{ .Annotations.summary }}.

<!-- fr:journal kind=finding scope=plan id=p1-r2 created=2026-10-22T05:30:50+00:00 phase=1 state=open review_scope=in -->
### p1-r2 · finding [open] (reviewer: in scope) · GeneratorURL not matching /alerting/grafana/<uid>/view yields garbage Silence link and empty Rule (phase 1)

contact-points-cm.yaml:22,27,59 unconditional uid/origin surgery.

<!-- fr:journal kind=finding scope=plan id=p1-r3 created=2026-10-22T05:30:50+00:00 phase=1 state=open review_scope=in -->
### p1-r3 · finding [open] (reviewer: in scope) · unlabeled Where: line is ambiguous, e.g. "Where: n8n-01 · n8n-01" (phase 1)

contact-points-cm.yaml:37-49.

<!-- fr:journal kind=finding scope=plan id=p1-r4 created=2026-10-22T05:30:50+00:00 phase=1 state=open review_scope=in -->
### p1-r4 · finding [open] (reviewer: in scope) · 5 verbose firing blocks can exceed Telegram 4096, truncating the overflow line and resolved section (phase 1)

layer-25-mirror-sync-failing ~620 chars of annotations per block.

<!-- fr:journal kind=finding scope=plan id=p1-r5 created=2026-10-22T05:30:50+00:00 phase=1 state=open review_scope=in -->
### p1-r5 · finding [open] (reviewer: in scope) · guard tests do not pin R3 rendered order or the R6 cap value of 5 (phase 1)

test_telegram_alert_template.py:87-118.

<!-- fr:journal kind=review scope=plan id=p1-review created=2026-10-22T05:30:50+00:00 phase=1 -->
### p1-review · review · phase 1 code review: 5 Minor findings (p1-r1..p1-r5); verdict ready to merge (phase 1)

Dispatched code-reviewer read the diff 76520320..1bb4b46a, all four Grafana preview renders (cat -et), rendered 5/6-item boundaries and an empty group with Go text/template, audited all 65 rules, ran the guard tests (10 passed). Findings p1-r1..p1-r5.

<!-- fr:journal kind=discovery scope=plan id=telegram-template-preview-renders-after-review created=2026-10-22T05:30:50+00:00 phase=1 -->
### telegram-template-preview-renders-after-review · discovery · Rendered messages after review fixes (sets 1,2,3,5,6) (phase 1)

Grafana 12.3.3 templates/test renders after the review fixes (nothing sent):

### set 1-one-firing
```
🔥 FIRING · warning · Layer 15 Agentic Workflows Degraded
L15 Workflows: n8n-01/deployment/n8n-01 has 1 replica(s) unavailable
Where: ns n8n-01 · workload n8n-01
Fix: kubectl -n n8n-01 rollout status deployment/n8n-01; kubectl -n n8n-01 describe deployment/n8n-01
Rule: https://grafana.cluster.derio.net/alerting/grafana/layer-15-workflows-down/view?orgId=1
Silence: https://grafana.cluster.derio.net/alerting/silence/new?alertmanager=grafana&matcher=__alert_rule_uid__%3Dlayer-15-workflows-down&orgId=1
```

### set 2-one-resolved
```
✅ RESOLVED · Layer 15 Agentic Workflows Degraded — L15 Workflows: n8n-01/deployment/n8n-01 has 1 replica(s) unavailable
```

### set 3-seven-firing-two-resolved
```
🔥 FIRING · critical · Pod CrashLooping
alert-agent/alert-agent-7c9d4f6b8-qq2lm restarted 6 times in 15m
Where: ns alert-agent · node mini-2 · pod alert-agent-7c9d4f6b8-qq2lm
Rule: https://grafana.cluster.derio.net/alerting/grafana/pod-crashlooping/view?orgId=1
Silence: https://grafana.cluster.derio.net/alerting/silence/new?alertmanager=grafana&matcher=__alert_rule_uid__%3Dpod-crashlooping&orgId=1

🔥 FIRING · warning · Layer 15 Agentic Workflows Degraded
L15 Workflows: n8n-01/deployment/n8n-01 has 1 replica(s) unavailable
Where: ns n8n-01 · workload n8n-01
Fix: kubectl -n n8n-01 rollout status deployment/n8n-01; kubectl -n n8n-01 describe deployment/n8n-01
Rule: https://grafana.cluster.derio.net/alerting/grafana/layer-15-workflows-down/view?orgId=1
Silence: https://grafana.cluster.derio.net/alerting/silence/new?alertmanager=grafana&matcher=__alert_rule_uid__%3Dlayer-15-workflows-down&orgId=1

🔥 FIRING · warning · Layer 15 Agentic Workflows Degraded
L15 Workflows: agents/statefulset/hermes-agent-shell has 1 replica(s) unavailable
Where: ns agents · workload hermes-agent-shell
Fix: kubectl -n agents rollout status statefulset/hermes-agent-shell; kubectl -n agents describe statefulset/hermes-agent-shell
Rule: https://grafana.cluster.derio.net/alerting/grafana/layer-15-workflows-down/view?orgId=1
Silence: https://grafana.cluster.derio.net/alerting/silence/new?alertmanager=grafana&matcher=__alert_rule_uid__%3Dlayer-15-workflows-down&orgId=1

🔥 FIRING · warning · Layer 15 Agentic Workflows Degraded
L15 Workflows: paperclip-system/deployment/paperclip has 1 replica(s) unavailable
Where: ns paperclip-system · workload paperclip
Fix: kubectl -n paperclip-system rollout status deployment/paperclip; kubectl -n paperclip-system describe deployment/paperclip
Rule: https://grafana.cluster.derio.net/alerting/grafana/layer-15-workflows-down/view?orgId=1
Silence: https://grafana.cluster.derio.net/alerting/silence/new?alertmanager=grafana&matcher=__alert_rule_uid__%3Dlayer-15-workflows-down&orgId=1

🔥 FIRING · warning · Layer 15 Agentic Workflows Degraded
L15 Workflows: agents/deployment/vk-remote has 1 replica(s) unavailable
Where: ns agents · workload vk-remote
Fix: kubectl -n agents rollout status deployment/vk-remote; kubectl -n agents describe deployment/vk-remote
Rule: https://grafana.cluster.derio.net/alerting/grafana/layer-15-workflows-down/view?orgId=1
Silence: https://grafana.cluster.derio.net/alerting/silence/new?alertmanager=grafana&matcher=__alert_rule_uid__%3Dlayer-15-workflows-down&orgId=1

… +2 more firing — https://grafana.cluster.derio.net/alerting/list

✅ RESOLVED · Layer 15 Agentic Workflows Degraded — L15 Workflows: agents/deployment/ruvocal has 1 replica(s) unavailable
✅ RESOLVED · Layer 15 Agentic Workflows Degraded — L15 Workflows: agents/statefulset/gbrain has 1 replica(s) unavailable
```

### set 5-edge-test-notification
```
🔥 FIRING · TestAlert

✅ RESOLVED · TestAlert
```

### set 6-edge-non-rule-url
```
🔥 FIRING · warning · External
from elsewhere
Rule: https://example.invalid/some/page?orgId=1
```

<!-- fr:journal kind=finding scope=plan id=p1-r1-resolved created=2026-10-22T05:30:50+00:00 phase=1 state=fixed resolves=p1-r1 -->
### p1-r1-resolved · finding [fixed] · resolves p1-r1: missing severity/summary renders Go "<no value>" in header/summary/resolved line (phase 1)

Severity and summary behind `with`; resolved summary too. Set 5 renders `🔥 FIRING · TestAlert` / `✅ RESOLVED · TestAlert`, zero "<no value>" across all sets. Pinned by test_missing_severity_or_summary_never_prints_no_value. bcb9dc89.

<!-- fr:journal kind=finding scope=plan id=p1-r2-resolved created=2026-10-22T05:30:50+00:00 phase=1 state=fixed resolves=p1-r2 -->
### p1-r2-resolved · finding [fixed] · resolves p1-r2: GeneratorURL not matching /alerting/grafana/<uid>/view yields garbage Silence link and empty Rule (phase 1)

Rule+Silence built only when `match "/alerting/grafana/[^/?]+/view"`; otherwise an absolute URL prints raw as Rule, anything else nothing (Grafana appends ?orgId=1 even to an empty URL — found in set 5). Overflow link guarded the same way. Sets 5/6 render clean. Pinned by test_links_are_built_only_from_a_rule_shaped_generator_url. bcb9dc89.

<!-- fr:journal kind=finding scope=plan id=p1-r3-resolved created=2026-10-22T05:30:50+00:00 phase=1 state=fixed resolves=p1-r3 -->
### p1-r3-resolved · finding [fixed] · resolves p1-r3: unlabeled Where: line is ambiguous, e.g. "Where: n8n-01 · n8n-01" (phase 1)

Where: values tagged in plain text: `ns`, `workload`, `node`, `pvc`, `pod` — set 1 renders `Where: ns n8n-01 · workload n8n-01`. No markup, R7 intact. bcb9dc89.

<!-- fr:journal kind=finding scope=plan id=p1-r4-resolved created=2026-10-22T05:30:50+00:00 phase=1 state=open resolves=p1-r4 out_of_scope=true -->
### p1-r4-resolved · finding [out-of-scope] · resolves p1-r4: 5 verbose firing blocks can exceed Telegram 4096, truncating the overflow line and resolved section (phase 1)

Reclassified out: the 4096 cap exists independently of this change, and the default template it replaces (all labels + ~900-char silence URL per alert) hits it with far fewer alerts — this change strictly lowers the risk. Worst observed render (set 3, 7 firing + 2 resolved) is 2886 chars. Documented in docs/runbooks/frank-gotchas/grafana.md "Telegram message template".

<!-- fr:journal kind=finding scope=plan id=p1-r5-resolved created=2026-10-22T05:30:50+00:00 phase=1 state=fixed resolves=p1-r5 -->
### p1-r5-resolved · finding [fixed] · resolves p1-r5: guard tests do not pin R3 rendered order or the R6 cap value of 5 (phase 1)

test_where_line_renders_tagged_values_in_r3_order checks the rendered tag order after Where:; test_caps_are_five_for_both_lists pins `gt (len L) 5`, `slice L 1 5`, `len (slice L 5)` for both lists. 14 passed. bcb9dc89.

<!-- fr:journal kind=finding scope=plan id=p1-r4-resolved-2 created=2026-10-22T05:38:15+00:00 phase=1 state=open resolves=p1-r4 tracked_by=https://github.com/derio-net/frank/issues/901 -->
### p1-r4-resolved-2 · finding [deferred → https://github.com/derio-net/frank/issues/901] · resolves p1-r4: 5 verbose firing blocks can exceed Telegram 4096, truncating the overflow line and resolved section (phase 1)

Filed at deliver as https://github.com/derio-net/frank/issues/901.
