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
