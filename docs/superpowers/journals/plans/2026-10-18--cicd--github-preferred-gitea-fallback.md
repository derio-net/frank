<!-- fr:journal-schema=2 -->
# Journal: 2026-10-18--cicd--github-preferred-gitea-fallback

<!-- fr:journal kind=decision scope=plan id=plan-shape created=2026-10-18T14:47:33+00:00 -->
### plan-shape · decision · Five agentic phases (one per ask) plus a trailing manual phase

Skeleton = tier config + gate-coverage checker (the cross-repo PRs validate against it). Cross-repo PRs (R17) are dispatched by the orchestrator after phase 1 lands and tracked in the manual phase; PRE-MERGE gates are manual ops that hold the PR in draft.
