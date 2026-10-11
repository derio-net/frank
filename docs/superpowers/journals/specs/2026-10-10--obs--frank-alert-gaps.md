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

<!-- fr:journal kind=review scope=spec id=spec-review-r1 created=2026-10-10T19:09:42+00:00 -->
### spec-review-r1 · review · independent spec review: 9 findings

fr-spec-reviewer checked the spec against q1-q5, the codebase (file:line per named artefact), and itself. Routing, folder-wide guards, window arithmetic, PVC-resident state path and parse_mode None provisioning verified; 9 in-scope findings sr-1..sr-9 raised.

<!-- fr:journal kind=finding scope=spec id=sr-1 created=2026-10-10T19:09:42+00:00 state=open review_scope=in -->
### sr-1 · finding [open] (reviewer: in scope) · R2 claims every parse-mode description is fixed, but four more places still say HTML

layer-2-etcd-health NOTE (alert-rules-cm.yaml:1126-1130), test_etcd_scrape.py:1038,1062-1063, operating posts 05-observability and 15-health-monitoring.

<!-- fr:journal kind=finding scope=spec id=sr-2 created=2026-10-10T19:09:42+00:00 state=open review_scope=in -->
### sr-2 · finding [open] (reviewer: in scope) · "After a successful send" is undefined; tg_send returns an error dict instead of raising

tg_bridge/bridge.py:59-84 returns {ok: False}; key must be written only on ok:True from both sends.

<!-- fr:journal kind=finding scope=spec id=sr-3 created=2026-10-10T19:09:42+00:00 state=open review_scope=in -->
### sr-3 · finding [open] (reviewer: in scope) · Unit tests need STATE_PATH isolated, or the de-dup leaks state between tests

autouse fixture monkeypatching STATE_PATH, read at call time.

<!-- fr:journal kind=finding scope=spec id=sr-4 created=2026-10-10T19:09:42+00:00 state=open review_scope=in -->
### sr-4 · finding [open] (reviewer: in scope) · The UTC-day de-dup key moves the daily warning to the 00:00 UTC run

0 */6 + utc_date key makes 00:00 UTC the first warning of the day.

<!-- fr:journal kind=finding scope=spec id=sr-5 created=2026-10-10T19:09:42+00:00 state=open review_scope=in -->
### sr-5 · finding [open] (reviewer: in scope) · Test Plan step 3 does not skip a run: deleting the pod 5 minutes early just reschedules it

Recreate + cached image restarts within minutes; supercronic runs the slot.

<!-- fr:journal kind=finding scope=spec id=sr-6 created=2026-10-10T19:09:42+00:00 state=open review_scope=in -->
### sr-6 · finding [open] (reviewer: in scope) · Nothing checks after merge that the provisioned contact point carries parse_mode None

Add a post-merge GET /api/v1/provisioning/contact-points check.

<!-- fr:journal kind=finding scope=spec id=sr-7 created=2026-10-10T19:09:42+00:00 state=open review_scope=in -->
### sr-7 · finding [open] (reviewer: in scope) · A persistent PVC warning re-pages Telegram every 3 minutes under the inherited repeat_interval

notification-policy-cm.yaml:22-25 root repeat_interval 3m.

<!-- fr:journal kind=finding scope=spec id=sr-8 created=2026-10-10T19:09:42+00:00 state=open review_scope=in -->
### sr-8 · finding [open] (reviewer: in scope) · The ratio expressions do not guard a zero denominator; +Inf would fire forever

Add (denominator > 0).

<!-- fr:journal kind=finding scope=spec id=sr-9 created=2026-10-10T19:09:42+00:00 state=open review_scope=in -->
### sr-9 · finding [open] (reviewer: in scope) · Leftover "daily" wording in the rule summary, and the stated latency and test bound are loose

summary 'daily check is dead', .crontab:2,5; latency 15-16h; guard window > 2x cadence parsed from crontab.

<!-- fr:journal kind=discovery scope=spec id=parse-mode-live-probe created=2026-10-10T19:09:42+00:00 -->
### parse-mode-live-probe · discovery · Live receivers/test probe: parse_mode unset → Telegram 400; None → ok

2026-10-10T18:54:50Z, run in the grafana pod (secrets never left it) via POST /api/alertmanager/grafana/config/api/v1/receivers/test with the real bot token and chat id, summary containing bare < > &. Case parse_mode unset: status failed, 'failed to send telegram message: webhook response status 400 Bad Request'. Case parse_mode None: status ok (delivered). Confirms #799 claims B/C and the upstream HTML default; the seven bracket-bearing Telegram rules were genuinely undeliverable.

<!-- fr:journal kind=decision scope=spec id=cred-slots-09-anchor created=2026-10-10T19:09:42+00:00 -->
### cred-slots-09-anchor · decision · Cred-expiry slots 03/09/15/21 UTC with the warning-day anchored at 09:00 UTC

Resolving sr-4 within the operator's 6h-cadence decision (q2): keep today's 09:00 UTC warning time by shifting the slots instead of using 0 */6, and key the de-dup on date(now - 9h).

<!-- fr:journal kind=decision scope=spec id=pvc-route-4h-repeat created=2026-10-10T19:09:42+00:00 -->
### pvc-route-4h-repeat · decision · Dedicated pvc_capacity route with repeat_interval 4h fanning out to Telegram and Health Bridge

Resolving sr-7 within the operator's q3 routing decision (both tiers page, then Health Bridge) — only the re-notify cadence changes.

<!-- fr:journal kind=decision scope=spec id=tests-ci-evidence created=2026-10-10T19:09:42+00:00 -->
### tests-ci-evidence · decision · Test evidence via CI (tests: ci); no local full suite

Operator instruction relayed mid-run: the host is overloaded; use PR CI as test evidence via .fr/ci.yaml gate_checks, run only targeted tests locally.

<!-- fr:journal kind=finding scope=spec id=sr-1-resolved created=2026-10-10T19:09:42+00:00 state=fixed resolves=sr-1 -->
### sr-1-resolved · finding [fixed] · resolves sr-1: R2 claims every parse-mode description is fixed, but four more places still say HTML

R2 + Design now list the etcd NOTE, test_etcd_scrape.py messages and both operating posts.

<!-- fr:journal kind=finding scope=spec id=sr-2-resolved created=2026-10-10T19:09:42+00:00 state=fixed resolves=sr-2 -->
### sr-2-resolved · finding [fixed] · resolves sr-2: "After a successful send" is undefined; tg_send returns an error dict instead of raising

R5 + Design define success as both tg_send results dicts with ok true; key written only then; ok:False test case added.

<!-- fr:journal kind=finding scope=spec id=sr-3-resolved created=2026-10-10T19:09:42+00:00 state=fixed resolves=sr-3 -->
### sr-3-resolved · finding [fixed] · resolves sr-3: Unit tests need STATE_PATH isolated, or the de-dup leaks state between tests

Design: STATE_PATH read at call time; autouse fixture to tmp_path; wired fixture returns {ok: True}.

<!-- fr:journal kind=finding scope=spec id=sr-4-resolved created=2026-10-10T19:09:42+00:00 state=fixed resolves=sr-4 -->
### sr-4-resolved · finding [fixed] · resolves sr-4: The UTC-day de-dup key moves the daily warning to the 00:00 UTC run

R4/R5: slots 0 3,9,15,21 and key date(now - 9h) keep the warning at 09:00 UTC; test for the 03:00 run.

<!-- fr:journal kind=finding scope=spec id=sr-5-resolved created=2026-10-10T19:09:42+00:00 state=fixed resolves=sr-5 -->
### sr-5-resolved · finding [fixed] · resolves sr-5: Test Plan step 3 does not skip a run: deleting the pod 5 minutes early just reschedules it

Test Plan step 4 scales the Deployment to 0 across a slot and asserts the slot's heartbeat is absent.

<!-- fr:journal kind=finding scope=spec id=sr-6-resolved created=2026-10-10T19:09:42+00:00 state=fixed resolves=sr-6 -->
### sr-6-resolved · finding [fixed] · resolves sr-6: Nothing checks after merge that the provisioned contact point carries parse_mode None

Test Plan step 2 reads the provisioned contact point and asserts parse_mode None.

<!-- fr:journal kind=finding scope=spec id=sr-7-resolved created=2026-10-10T19:09:42+00:00 state=fixed resolves=sr-7 -->
### sr-7-resolved · finding [fixed] · resolves sr-7: A persistent PVC warning re-pages Telegram every 3 minutes under the inherited repeat_interval

R10: pvc_capacity route with repeat_interval 4h, child routes to Telegram (continue) and Health Bridge.

<!-- fr:journal kind=finding scope=spec id=sr-8-resolved created=2026-10-10T19:09:42+00:00 state=fixed resolves=sr-8 -->
### sr-8-resolved · finding [fixed] · resolves sr-8: The ratio expressions do not guard a zero denominator; +Inf would fire forever

R7/R8 + Design: (denominator > 0) filter; live check showed no zero denominators.

<!-- fr:journal kind=finding scope=spec id=sr-9-resolved created=2026-10-10T19:09:42+00:00 state=fixed resolves=sr-9 -->
### sr-9-resolved · finding [fixed] · resolves sr-9: Leftover "daily" wording in the rule summary, and the stated latency and test bound are loose

R6 latency 15-16h; summary 'daily' sentence and .crontab:2,5 listed; R11 guard parses cadence, asserts 2x cadence < window < 30h.

<!-- fr:journal kind=decision scope=spec id=phase-split-2026-10-10--obs--frank-alert-gaps-p2 created=2026-10-10T19:12:19+00:00 -->
### phase-split-2026-10-10--obs--frank-alert-gaps-p2 · decision · ask: frank#746 cred-expiry cadence, de-dup and window is an independently reviewable ask (R4-R6)

<!-- fr:journal kind=decision scope=spec id=phase-split-2026-10-10--obs--frank-alert-gaps-p3 created=2026-10-10T19:12:21+00:00 -->
### phase-split-2026-10-10--obs--frank-alert-gaps-p3 · decision · ask: frank#722 PVC capacity and inode rules plus their route are an independently reviewable ask (R7-R10)
