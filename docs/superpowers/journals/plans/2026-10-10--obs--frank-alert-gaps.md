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
