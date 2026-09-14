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

<!-- fr:journal kind=decision scope=spec id=skeleton-override-2026-06-15-staging-vcluster-gate created=2026-09-14T22:36:38 -->
### skeleton-override-2026-06-15-staging-vcluster-gate · decision · Phase 1 carries no skeleton marker (predates the rule)

Phases 1-6 completed 2026-06-15, before the skeleton-marker lint. CI (repo-tripwires: 776 passed / 1 xfailed on the rebased branch) already smokes every push, and phases 7-10 extend that suite rather than add a new runtime, so re-marking a completed phase adds no smoke.

<!-- fr:journal kind=review scope=spec id=spec-review-2026-09-14 created=2026-09-14T22:37:58 -->
### spec-review-2026-09-14 · review · Spec re-reviewed against Q&A answers and current main

Every revision-table row cites live evidence gathered 2026-09-14 (ArgoCD v3.3.2 image, argocd-cm exclusion list, runs-fr build.yml 403 logs, argocd repository Secrets, GHCR anonymous manifest fetches, #797 rule body). Named files verified present: apps/argocd/values.yaml Pod exclusion, scripts/tests/test_argocd_vcluster_pod_exclusion.py, apps/tekton/webhooks.yaml + test_webhook_delivery_paths.py, externalsecret-frank-gitops-push.yaml, ClusterGenerator github-app-derio, derio-homelab webhook ExternalSecret precedent, vcluster 0.32.1 exportKubeConfig.additionalSecrets. All four operator answers are reflected (d-promote-last-green, d-dedicated-vcluster, d-dispatch-webhook, d-test-plan). Open risk carried into implementation: additionalSecrets behaviour and StepAction availability are verified by helm render / read-only CRD check in the phase, not assumed.
