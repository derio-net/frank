# Journal: 2026-06-15--cicd--staging-vcluster-gate

<!-- fr:journal kind=decision scope=spec id=d-promote-last-green created=2026-09-14T22:09:45 -->
### d-promote-last-green · decision · Promote records last-green, not a prod bump

runs-fr has no Frank prod app. Operator chose: promote commits the blessed sha-<commit> to apps/staging-gate/runs-fr/promoted.yaml (audit record, future prod-app input). Prod wiring stays a follow-up.

<!-- fr:journal kind=decision scope=spec id=d-dedicated-vcluster created=2026-09-14T22:10:27 -->
### d-dedicated-vcluster · decision · Keep the dedicated staging vCluster

Operator chose dedicated staging over reusing cnc-staging. Requires the argo-cd#26529 scoped Pod exclusion to cover https://staging.vcluster-staging.svc:443 before registration.

<!-- fr:journal kind=decision scope=spec id=d-dispatch-webhook created=2026-09-14T22:11:24 -->
### d-dispatch-webhook · decision · Trigger via fixed repository_dispatch + per-repo webhook

runs-fr trigger-gate 403s (GITHUB_TOKEN contents:read). Operator chose: cross-repo runs-fr PR grants contents:write; a runs-fr GitHub webhook (repository_dispatch) with its own derio-net HMAC, declared in apps/tekton/webhooks.yaml, created by manual op.

<!-- fr:journal kind=decision scope=spec id=d-test-plan created=2026-09-14T22:12:18 -->
### d-test-plan · decision · Test Plan: green + red, agent-driven post-merge

After the operator applies manual-op secrets, the agent drives green (real merge -> last-green commit) and red (broken smoke blocks promote, notification fires) and records evidence on the PR.
