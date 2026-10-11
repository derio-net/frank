# Frank alerting gaps — implementation plan

Three asks from one spec (`2026-10-10--obs--frank-alert-gaps-design.md`), one PR (#832), one agentic phase each:

1. **#799 (skeleton):** pin the Telegram contact point to `parse_mode: None`. The live probe already proved that unset gives 400 and None gives ok. The phase also removes every place that still claims "unset means plain".
2. **#746:** run `cred-expiry-check` 6-hourly at 03/09/15/21 UTC, de-dup the warning to once per warning-day per tier (the day anchored at 09:00 UTC), and narrow the dead-man window to 13h.
3. **#722:** add PVC byte (85/95) and inode (90) rules with a zero-denominator guard, plus a dedicated route that re-notifies every 4h instead of every 3m.

Testing: per operator instruction the full suite never runs locally. Each phase runs its targeted tests locally and uses PR CI (`tripwires`, declared in `.fr/ci.yaml`) as suite evidence. No CI job runs `apps/alert-agent/handlers/tests`, so phase 2's targeted local run is the evidence for those tests.

Post-merge verification lives in the spec's Test Plan (Grafana restart, provisioned contact point check, PVC rules Normal, a missed cred slot). There is no `[manual]` phase.
