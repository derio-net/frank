# Journal: 2026-07-23--agents--agent-images-sweep-verify

<!-- fr:journal kind=finding scope=plan id=f1-pretest-failures created=2026-07-23T19:06:40 phase=1 state=refuted -->
### f1-pretest-failures · finding [refuted] · 16 test failures in isolation were 7 pre-existing + 9 environment, not regressions (phase 1)

First run inside 'fr isolation exec' showed 16 failures (cert-expiry-canary, cnc-staging-host-secrets, cnc-staging-vcluster-api-netpol, sync-dossier-to-data). Two variables had changed at once - branch AND environment - so it was isolated properly: origin/main on the HOST = 7 failed / 169 passed; this branch on the HOST = 7 failed / 169 passed, identical. The extra 9 are a devcontainer artifact (missing cluster tooling those tests shell out to), not code. This branch's changes are docs-only and introduce zero regressions.

<!-- fr:journal kind=finding scope=plan id=f2-hermes-deploy-topology created=2026-07-23T21:22:30 phase=2 state=fixed -->
### f2-hermes-deploy-topology · finding [fixed] · Live check corrected the hermes image->app mapping; P2.T2.S7 config op is moot (phase 2)

The spec assumed the base hermes-agent-shell image (PyPI 0.19.0, with the retired autocontinue patch) is deployed. Live check: it is NOT deployed anywhere (like infra-shell). The frank hermes pod has 3 containers: runtime 'hermes' = docker.io/nousresearch/hermes-agent:v2026.7.7.2 (0.18.2, manifest-pinned upstream, OUT of sweep scope); 'ssh' = hermes-agent-shell-ssh built FROM docker v2026.7.20 (verified 'Hermes Agent v0.19.0' live); 'hindsight' = hermes-agent-shell-hindsight:c7a80f6. Consequence: P2.T2.S7 (set agent.intent_ack_continuation: true) is N/A for the current deployment - the retired patch was in the undeployed base image, and the running agent-loop hermes (0.18.2) never had our patch and predates the config knob. It becomes relevant only if the runtime hermes manifest pin is bumped to >=0.19.0, a separate decision. Recorded a durable gotcha; corrected the acceptance row.
