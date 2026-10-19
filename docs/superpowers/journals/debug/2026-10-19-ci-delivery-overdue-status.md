<!-- fr:journal-schema=2 -->
# Journal: 2026-10-19-ci-delivery-overdue-status

<!-- fr:journal kind=repro scope=debug id=65c358b96785 created=2026-10-19T19:39:34+00:00 -->
### 65c358b96785 · repro · L25 delivery-overdue (status) fires for 5 repos: Gitea statuses from 04:20-05:56Z never reached GitHub

Alert layer-25-delivery-overdue kind=status for derio-homelab/kid-laptops (4), derio-net/herdr-vertical-tabs (1), presentation-craft (2), runs-fr (5), vibe-kanban (12). Reproduced by running the live check.py API class locally with the job's own tokens and printing per-context expected vs actual: every mismatch is a Gitea status created ~04:20-05:56Z 2026-10-19 on the CURRENT default-branch head with NO gitea-actions/<ctx> status on GitHub at all (got=None), not a wrong state. Includes a permanent 'pending / Waiting to run' for herdr 'ci / test-macos (push)'.
