<!-- fr:journal-schema=2 -->
# Journal: 2026-10-19-ci-delivery-overdue-status

<!-- fr:journal kind=repro scope=debug id=65c358b96785 created=2026-10-19T19:39:34+00:00 -->
### 65c358b96785 · repro · L25 delivery-overdue (status) fires for 5 repos: Gitea statuses from 04:20-05:56Z never reached GitHub

Alert layer-25-delivery-overdue kind=status for derio-homelab/kid-laptops (4), derio-net/herdr-vertical-tabs (1), presentation-craft (2), runs-fr (5), vibe-kanban (12). Reproduced by running the live check.py API class locally with the job's own tokens and printing per-context expected vs actual: every mismatch is a Gitea status created ~04:20-05:56Z 2026-10-19 on the CURRENT default-branch head with NO gitea-actions/<ctx> status on GitHub at all (got=None), not a wrong state. Includes a permanent 'pending / Waiting to run' for herdr 'ci / test-macos (push)'.

<!-- fr:journal kind=ruled-out scope=debug id=24cbd250fe6c created=2026-10-19T19:41:23+00:00 -->
### 24cbd250fe6c · ruled-out · Not a live forwarding break: bridge forwards derio-* statuses now

132 stoa-status-bridge PipelineRuns for derio-* repos since 11:45:30Z, all post-dating every mismatch; the 19:2x herdr probe PR also forwarded. ci-delivery-check's comparison is correct: GitHub genuinely has no gitea-actions/<ctx> status for these commits.

<!-- fr:journal kind=ruled-out scope=debug id=684851cd10b3 created=2026-10-19T19:41:26+00:00 -->
### 684851cd10b3 · ruled-out · Not a checker false positive (description/URL mapping)

Every mismatch has got=None on GitHub (no status at all), so matches()/forwarded() mapping and the GITEA_WEB_URL rewrite are not involved.

<!-- fr:journal kind=root-cause scope=debug id=8b25faf88089 created=2026-10-19T19:41:29+00:00 -->
### 8b25faf88089 · root-cause · Rollout-ordering gap stranded 24 statuses on still-current heads; fire-and-forget means nothing re-delivers them

The derio-net/derio-homelab org status hooks were created 05:13:25Z (manual op, pre-merge); kid-laptops' 04:23Z molecule statuses predate any hook. The gitea-status-bridge CEL allowlist only gained the derio-* repos in #878 (merged 11:24Z; first derio bridge run 11:45:30Z), so every status event 05:13Z->11:45Z reached gitea-listener and was FILTERED. Gitea webhooks are not retried and nothing reconciles commit statuses, so the 24 statuses (04:23-05:56Z) on the five repos' default-branch heads stay undelivered. The heads have not moved since, so ci-delivery-check re-reads the same stranded statuses every 5 min and the alert cannot self-clear until each repo gets a new commit. 17 of 24 are 'Gitea: skipped' (CI_AUTHORITY was github then); the rest are kid-laptops molecule/acceptance failures and one permanent-pending herdr test-macos.
