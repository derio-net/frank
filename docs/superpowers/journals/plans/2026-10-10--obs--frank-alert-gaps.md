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
