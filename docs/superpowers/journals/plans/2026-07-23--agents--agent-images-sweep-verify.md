# Journal: 2026-07-23--agents--agent-images-sweep-verify

<!-- fr:journal kind=finding scope=plan id=f1-pretest-failures created=2026-07-23T19:06:40 phase=1 state=refuted -->
### f1-pretest-failures · finding [refuted] · 16 test failures in isolation were 7 pre-existing + 9 environment, not regressions (phase 1)

First run inside 'fr isolation exec' showed 16 failures (cert-expiry-canary, cnc-staging-host-secrets, cnc-staging-vcluster-api-netpol, sync-dossier-to-data). Two variables had changed at once - branch AND environment - so it was isolated properly: origin/main on the HOST = 7 failed / 169 passed; this branch on the HOST = 7 failed / 169 passed, identical. The extra 9 are a devcontainer artifact (missing cluster tooling those tests shell out to), not code. This branch's changes are docs-only and introduce zero regressions.
