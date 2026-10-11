# Journal: 2026-10-10--obs--frank-alert-gaps

<!-- fr:journal kind=discovery scope=plan id=p1-venv-broken created=2026-10-10T19:18:51+00:00 phase=1 -->
### p1-venv-broken · discovery · Worktree .venv is a dangling symlink (phase 1)

The worktree .venv/bin/python points at a non-existent interpreter, so .venv/bin/pytest fails. Targeted tests were run with the base clone's .venv python (read-only use) from the worktree cwd.

<!-- fr:journal kind=discovery scope=plan id=p1-unset-is-html created=2026-10-10T19:18:51+00:00 phase=1 -->
### p1-unset-is-html · discovery · Unset Telegram parse_mode is HTML (phase 1)

grafana/alerting receivers/telegram/v1/config.go:84-86 falls back to HTML; probe 2026-10-10 unset=400, None=ok. Pinned parse_mode None and guarded by test_telegram_parse_mode_explicit.py (frank#799).

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t2 created=2026-10-10T19:18:51+00:00 phase=1 -->
### no-refactor-p1-t2 · discovery · no-refactor-because P1.T2 (phase 1)

new test is a single small helper plus one assertion; nothing to clean

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t4 created=2026-10-10T19:18:51+00:00 phase=1 -->
### no-refactor-p1-t4 · discovery · no-refactor-because P1.T4 (phase 1)

edits were comment/prose rewordings only; no code structure to refactor

<!-- fr:journal kind=review scope=plan id=review-p1-r1 created=2026-10-10T19:22:10+00:00 phase=1 -->
### review-p1-r1 · review · Phase 1 code review: 3 in-scope findings (wording/style), pin and tripwire verified (phase 1)

Independent code-reviewer checked cbc7c12a against spec R1-R3 and plan phase 1: parse_mode None parses as the string and maps to plain upstream; the tripwire fails on removal/HTML/Markdown/null; every R2 location agrees; no leftover 'unset means plain' claim outside docs/superpowers; history consistent (cc239cf9 before the 2026-06-09 400). Raised p1-r1..p1-r3.

<!-- fr:journal kind=finding scope=plan id=p1-r1 created=2026-10-10T19:22:10+00:00 phase=1 state=open review_scope=in -->
### p1-r1 · finding [open] (reviewer: in scope) · 05-observability table row: inserted pin clause makes 'logs as sent' attach to the None pin (phase 1)

blog/content/docs/operating/05-observability/index.md:494 — reorder the sentence.

<!-- fr:journal kind=finding scope=plan id=p1-r2 created=2026-10-10T19:22:10+00:00 phase=1 state=open review_scope=in -->
### p1-r2 · finding [open] (reviewer: in scope) · 05-observability item 1 uses ASCII ' - ' where the post uses em dashes (phase 1)

blog/content/docs/operating/05-observability/index.md:397.

<!-- fr:journal kind=finding scope=plan id=p1-r3 created=2026-10-10T19:22:10+00:00 phase=1 state=open review_scope=in -->
### p1-r3 · finding [open] (reviewer: in scope) · grafana.md Rule and frank-gotchas one-liner still read as a hard <>& ban (phase 1)

docs/runbooks/frank-gotchas/grafana.md:103, agents/rules/frank-gotchas.md:99 — mark as style-only post-#799.

<!-- fr:journal kind=finding scope=plan id=p1-r1-resolved created=2026-10-10T19:22:10+00:00 phase=1 state=fixed resolves=p1-r1 -->
### p1-r1-resolved · finding [fixed] · resolves p1-r1: 05-observability table row: inserted pin clause makes 'logs as sent' attach to the None pin (phase 1)

Sentence reordered; the pin clause now closes the cell (387a9b89).

<!-- fr:journal kind=finding scope=plan id=p1-r2-resolved created=2026-10-10T19:22:10+00:00 phase=1 state=fixed resolves=p1-r2 -->
### p1-r2-resolved · finding [fixed] · resolves p1-r2: 05-observability item 1 uses ASCII ' - ' where the post uses em dashes (phase 1)

Em dash (387a9b89).

<!-- fr:journal kind=finding scope=plan id=p1-r3-resolved created=2026-10-10T19:22:10+00:00 phase=1 state=fixed resolves=p1-r3 -->
### p1-r3-resolved · finding [fixed] · resolves p1-r3: grafana.md Rule and frank-gotchas one-liner still read as a hard <>& ban (phase 1)

Rule marked style-only since frank#799 in both places; the older carrying rules are noted as harmless and deliberately left (387a9b89).

<!-- fr:journal kind=discovery scope=plan id=p2-handler-test-log created=2026-10-10T19:27:37+00:00 phase=2 -->
### p2-handler-test-log · discovery · Handler tests run locally; no CI job covers them (phase 2)

No CI job runs apps/alert-agent/handlers/tests, so the targeted run (89 passed) is logged at /Users/derio/.claude-tmp/claude-501/-Users-derio-Docs-projects-DERIO-NET-frank/4d6fa419-32bc-4dda-9e07-d7a7cca63eaf/scratchpad/p2-handler-tests.log. Scripts guard run with the base clone venv python.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p2-t1 created=2026-10-10T19:27:37+00:00 phase=2 -->
### no-refactor-p2-t1 · discovery · no-refactor-because P2.T1 (phase 2)

tests only; new cases are flat and share small helpers (_at, _creds_at), nothing to clean

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p2-t2 created=2026-10-10T19:27:37+00:00 phase=2 -->
### no-refactor-p2-t2 · discovery · no-refactor-because P2.T2 (phase 2)

implementation already split into small helpers (_warn_key/_read_state/_write_state/_sent_ok); nothing further to clean

<!-- fr:journal kind=review scope=plan id=review-p2-r1 created=2026-10-10T19:30:04+00:00 phase=2 -->
### review-p2-r1 · review · Phase 2 code review: logic correct vs R4-R6/R11; 3 in-scope doc/test findings, 1 out-of-scope (phase 2)

Independent code-reviewer checked 41825dca: heartbeat-first, _warn_key boundaries, write-only-on-both-ok against tg_bridge's real return shape, fail-open paths, call-time STATE_PATH, autouse isolation, cadence parsing guard, rule arithmetic (fires 15-16h after last heartbeat), PVC-resident state, pod roll via hashed ConfigMap. Targeted tests 72 passed. Raised p2-r1..p2-r4.

<!-- fr:journal kind=finding scope=plan id=p2-r1 created=2026-10-10T19:30:04+00:00 phase=2 state=open review_scope=in -->
### p2-r1 · finding [open] (reviewer: in scope) · Comments say the warning-day rolls at 03:00 UTC; date(now-9h) rolls at 09:00 (phase 2)

cred_expiry.py:181 and test_cred_expiry.py:288-289.

<!-- fr:journal kind=finding scope=plan id=p2-r2 created=2026-10-10T19:30:04+00:00 phase=2 state=open review_scope=in -->
### p2-r2 · finding [open] (reviewer: in scope) · _warn_key test pins only whole hours; add an 08:59 UTC case (phase 2)

test_cred_expiry.py:299-306.

<!-- fr:journal kind=finding scope=plan id=p2-r3 created=2026-10-10T19:30:04+00:00 phase=2 state=open review_scope=in -->
### p2-r3 · finding [open] (reviewer: in scope) · Spliced overlong module docstring line and back-to-back parentheticals (phase 2)

cred_expiry.py:12, obs-digest.md:403.

<!-- fr:journal kind=finding scope=plan id=p2-r4 created=2026-10-10T19:30:04+00:00 phase=2 state=open review_scope=out -->
### p2-r4 · finding [open] (reviewer: out of scope) · Acceptance row obs-cred-expiry-deadman-tolerates-one-miss stays not-implemented until live evidence (phase 2)

docs/acceptance/matrix.yaml:1254 — verify: live, flips post-merge.

<!-- fr:journal kind=finding scope=plan id=p2-r1-resolved created=2026-10-10T19:30:04+00:00 phase=2 state=fixed resolves=p2-r1 -->
### p2-r1-resolved · finding [fixed] · resolves p2-r1: Comments say the warning-day rolls at 03:00 UTC; date(now-9h) rolls at 09:00 (phase 2)

Both comments now say the warning-day runs 09:00 to 09:00 UTC and the 03:00 run joins the previous day.

<!-- fr:journal kind=finding scope=plan id=p2-r2-resolved created=2026-10-10T19:30:04+00:00 phase=2 state=fixed resolves=p2-r2 -->
### p2-r2-resolved · finding [fixed] · resolves p2-r2: _warn_key test pins only whole hours; add an 08:59 UTC case (phase 2)

_at takes a minute; added _warn_key(08:59 day 11) == day 10. 65 passed locally.

<!-- fr:journal kind=finding scope=plan id=p2-r3-resolved created=2026-10-10T19:30:04+00:00 phase=2 state=fixed resolves=p2-r3 -->
### p2-r3-resolved · finding [fixed] · resolves p2-r3: Spliced overlong module docstring line and back-to-back parentheticals (phase 2)

Docstring reflowed into its own sentence; obs-digest parentheticals merged.

<!-- fr:journal kind=finding scope=plan id=p2-r4-resolved created=2026-10-10T19:30:04+00:00 phase=2 state=open resolves=p2-r4 out_of_scope=true -->
### p2-r4-resolved · finding [out-of-scope] · resolves p2-r4: Acceptance row obs-cred-expiry-deadman-tolerates-one-miss stays not-implemented until live evidence (phase 2)

Not caused by this change: a verify: live row can only flip on post-merge live evidence (spec Test Plan step 4); listed under post-merge verification owed.

<!-- fr:journal kind=discovery scope=plan id=p3-live-expr created=2026-10-10T19:36:27+00:00 phase=3 -->
### p3-live-expr · discovery · PVC exprs verified live against VictoriaMetrics (phase 3)

2026-10-10: bytes expr returns 36 series, top 78.2% secure-agent-pod/agent-home, then 68.4% paperclip-data, 65.5% hermes-agent-shell-home. Inode expr 36 series, max 34.8% agent-home. No zero denominators.

<!-- fr:journal kind=discovery scope=plan id=p3-route-count-guard created=2026-10-10T19:36:27+00:00 phase=3 -->
### p3-route-count-guard · discovery · test_cert_expiry_canary pins the route count and order (phase 3)

It asserted exactly 9 routes in order; adding the pvc_capacity route needed it bumped to 10 with the new entry before severity=critical.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p3-t1 created=2026-10-10T19:36:27+00:00 phase=3 -->
### no-refactor-p3-t1 · discovery · no-refactor-because P3.T1 (phase 3)

tests only; flat cases sharing two small loaders, nothing to clean

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p3-t2 created=2026-10-10T19:36:27+00:00 phase=3 -->
### no-refactor-p3-t2 · discovery · no-refactor-because P3.T2 (phase 3)

rules and route follow the existing house shape verbatim; nothing to clean

<!-- fr:journal kind=review scope=plan id=review-p3-r1 created=2026-10-10T19:40:04+00:00 phase=3 -->
### review-p3-r1 · review · Phase 3 code review: rules and route match spec; 3 minor in-scope test/runbook findings (phase 3)

Independent code-reviewer checked 7eafe10b..eae35f72: exprs byte-identical to the spec table incl. max by and > 0 guard; A-B-C shape, thresholds, for, severities, labels, states, uid lengths; $values.B.Value templating; route placement and Alertmanager child semantics (both receivers, no parent double-send, 4h inherited, nothing else captured); tests non-vacuous; cert-expiry-canary 9->10 route update legitimate; docs accurate. 58 targeted tests passed. Raised p3-r1..p3-r3.

<!-- fr:journal kind=finding scope=plan id=p3-r1 created=2026-10-10T19:40:04+00:00 phase=3 state=open review_scope=in -->
### p3-r1 · finding [open] (reviewer: in scope) · Route test does not pin child shape (no matchers / no repeat_interval on children) (phase 3)

scripts/tests/test_pvc_capacity_alert.py:91-97.

<!-- fr:journal kind=finding scope=plan id=p3-r2 created=2026-10-10T19:40:04+00:00 phase=3 state=open review_scope=in -->
### p3-r2 · finding [open] (reviewer: in scope) · Annotation <>& check covers summary only, not runbook (phase 3)

scripts/tests/test_pvc_capacity_alert.py:84-86.

<!-- fr:journal kind=finding scope=plan id=p3-r3 created=2026-10-10T19:40:04+00:00 phase=3 state=open review_scope=in -->
### p3-r3 · finding [open] (reviewer: in scope) · Runbook annotation should name storage-secrets-ssa.md where the headroom recipe lives (phase 3)

alert-rules-cm.yaml:1012,1048,1084.

<!-- fr:journal kind=finding scope=plan id=p3-r1-resolved created=2026-10-10T19:40:04+00:00 phase=3 state=fixed resolves=p3-r1 -->
### p3-r1-resolved · finding [fixed] · resolves p3-r1: Route test does not pin child shape (no matchers / no repeat_interval on children) (phase 3)

Each child asserted to carry no matchers/object_matchers and no repeat_interval.

<!-- fr:journal kind=finding scope=plan id=p3-r2-resolved created=2026-10-10T19:40:04+00:00 phase=3 state=fixed resolves=p3-r2 -->
### p3-r2-resolved · finding [fixed] · resolves p3-r2: Annotation <>& check covers summary only, not runbook (phase 3)

<>& check loops over every annotation.

<!-- fr:journal kind=finding scope=plan id=p3-r3-resolved created=2026-10-10T19:40:04+00:00 phase=3 state=fixed resolves=p3-r3 -->
### p3-r3-resolved · finding [fixed] · resolves p3-r3: Runbook annotation should name storage-secrets-ssa.md where the headroom recipe lives (phase 3)

All three runbooks now name docs/runbooks/frank-gotchas/storage-secrets-ssa.md (headroom check). 46 targeted tests passed.

<!-- fr:journal kind=decision scope=plan id=ci-runs-alert-agent-handler-suite created=2026-10-10T19:58:43+00:00 -->
### ci-runs-alert-agent-handler-suite · decision · CI now runs apps/alert-agent/handlers/tests in the tripwires job

Operator-approved 2026-10-10: the tripwires gate ran only scripts/tests/, so the #746 cred-expiry de-dup had no CI coverage. repo-tripwires.yml now runs the handler suite as a second pytest invocation (its conftest sys.path must not leak into scripts/tests/); scripts/tests/test_alert_agent_handlers_run_in_ci.py guards the step. The .fr/ci.yaml gate stays [tripwires], which now covers both suites (CI log: 1071 passed + 89 passed).
