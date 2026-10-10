# Journal: 2026-10-10--obs--frank-alert-gaps

<!-- fr:journal kind=discovery scope=spec id=operator-brief created=2026-10-10T18:52:13+00:00 input=true -->
### operator-brief · discovery · Operator brief — batch frank-alert-gaps (#722, #746, #799)

/fr-goal Frank alerting gaps: PVC capacity, Telegram parse_mode, cred-expiry window

Batch `frank-alert-gaps` of derio-net/frank: 3 issues, delivered as ONE pull request.

## frank#722: obs: no alerting on PVC capacity — a volume can fill to 100% silently
Zero `kubelet_volume_stats` rules in `apps/grafana-alerting/` on main. A PVC filled to 100% once already with no page (#715).
Note: Batch with frank#761, #798, #746 (alerting blind spots).

## frank#746: alert-agent cred-expiry dead-man false-pages on a single missed run (24h cadence vs 30h window)
Rule `alert-agent-cred-expiry-heartbeat-stale` at `apps/grafana-alerting/manifests/alert-rules-cm.yaml:2656` still uses the 30h window against a 24h cadence; one missed run pages critical.

## frank#799: obs: the repo contradicts itself on Telegram parse_mode — seven Telegram-routed rules carry bare angle brackets
`apps/grafana-alerting/manifests/contact-points-cm.yaml:19` still says parse_mode unset; seven Telegram-routed rules carry bare angle brackets. Which claim is true decides whether those alerts deliver.

## Why these belong together
Same alert-rules file; silent PVC fills and possibly undelivered Telegram alerts.

## Delivery rules
- Work on branch `feat/batch-frank-alert-gaps`.
- Open a draft PR as soon as the spec is committed. Its body contains these lines, one per member, so every member closes when it merges:
  Closes derio-net/frank#722
  Closes derio-net/frank#746
  Closes derio-net/frank#799
- Do not name any member issue as a phase `tracking_issue` in the plan: the bridge would then own that issue's `fr:` labels.

<!-- fr:journal kind=discovery scope=spec id=telegram-unset-parse-mode-is-html created=2026-10-10T18:52:13+00:00 -->
### telegram-unset-parse-mode-is-html · discovery · Grafana 12.3.3 sends HTML when parse_mode is unset

grafana/alerting receivers/telegram/v1/config.go:84-86 falls back to DefaultTelegramParseMode = "HTML" when parse_mode is missing; "None" maps to "" and telegram.go:131 then omits parse_mode. Live pod image grafana/grafana:12.3.3. The contact-point comment (claim A) is false; the rule comment and gotcha (B/C) are right.

<!-- fr:journal kind=discovery scope=spec id=cred-expiry-crontab-is-frank-configmap created=2026-10-10T18:52:13+00:00 -->
### cred-expiry-crontab-is-frank-configmap · discovery · The cred-expiry crontab is a frank ConfigMap, not baked in agent-images

apps/alert-agent/manifests/files/.crontab via configMapGenerator (kustomization.yaml:41-43), mounted at /home/agent/.crontab. #746 Option B is therefore frank-only.

<!-- fr:journal kind=decision scope=spec id=q1-parse-mode-none created=2026-10-10T18:52:13+00:00 -->
### q1-parse-mode-none · decision · parse_mode: None, no annotation scrub

Operator chose None (plain text), leaving the seven bracket-bearing rules unchanged; fix the contradicting comments and gotcha; tripwire pins the value.

<!-- fr:journal kind=decision scope=spec id=q2-cred-6h-13h created=2026-10-10T18:52:13+00:00 -->
### q2-cred-6h-13h · decision · Cred-expiry: 6h cadence, once-per-UTC-day-per-tier warning de-dup, 13h window

Operator chose 0 */6 * * *, a PVC state-file de-dup of Telegram warnings, and window 30h→13h (for: 2h kept).

<!-- fr:journal kind=decision scope=spec id=q3-pvc-85-95-both-page created=2026-10-10T18:52:13+00:00 -->
### q3-pvc-85-95-both-page · decision · PVC bytes: warning >85% 30m, critical >95% 5m, both page via severity routes

Operator chose both tiers reaching Telegram then Health Bridge (feature-health, frank-ops#4).

<!-- fr:journal kind=decision scope=spec id=q4-pvc-inodes created=2026-10-10T18:52:13+00:00 -->
### q4-pvc-inodes · decision · Add an inode-exhaustion rule (>90% 30m warning); no predict_linear

Operator selected the inode companion rule only.

<!-- fr:journal kind=decision scope=spec id=q5-verification created=2026-10-10T18:52:13+00:00 -->
### q5-verification · decision · Verification: tripwires + a pre-merge live receivers/test probe; live post-merge rows for PVC and cred-expiry

Operator chose guards plus a live Grafana receivers/test probe (unset vs None with a bare <) before merge.
