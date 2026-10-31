<!-- fr:journal-schema=3 -->
# Journal: 2026-10-31--life--update-security-lifecycle

<!-- fr:journal kind=decision scope=plan id=plan-repo-split created=2026-10-31T18:53:33+00:00 -->
### plan-repo-split · decision · One plan per repo (operator chose option A)

frank (this plan), derio-net/cluster-update-fr (console), derio-net/agent-images (session image); sibling plans run by cross-repo agents in their own workspaces.

<!-- fr:journal kind=decision scope=plan id=manual-back-loaded created=2026-10-31T18:53:33+00:00 -->
### manual-back-loaded · decision · Bootstrap/manual work back-loaded to phase 7

No agentic phase needs live secrets; apps tolerate missing Secrets (optional: true) until the trailing manual phase.
