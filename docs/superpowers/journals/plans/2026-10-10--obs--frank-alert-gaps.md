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
