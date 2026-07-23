# Journal: 2026-07-23--agents--agent-images-upstream-version-sweep

<!-- fr:journal kind=decision scope=spec id=d1-selection created=2026-07-23T18:18:30 -->
### d1-selection · decision · Selection scope: full sweep incl. ruflo re-vendor + Node 24

Operator chose the most aggressive option from the batched Q&A, with the ruflo (607-commit) and NODE_MAJOR 22->24 risks stated in the option text. All pin classes in scope; plan sequences them into waves so a stuck wave does not hold the others hostage.

<!-- fr:journal kind=decision scope=spec id=d2-talosctl-target created=2026-07-23T18:18:31 -->
### d2-talosctl-target · decision · talosctl targets the CLUSTER version (v1.12.6), not latest (v1.13.7)

Cluster runs Talos v1.12.6 on all 7 nodes; shells ship talosctl v1.9.5 (3 minors of skew, outside Talos's supported +/-1). Chasing latest v1.13.7 would re-break skew in the other direction.

<!-- fr:journal kind=decision scope=spec id=d3-durable-tooling created=2026-07-23T18:18:33 -->
### d3-durable-tooling · decision · Leave behind an on-demand version-audit script; no scheduled watcher

Operator chose a script in agent-images that reads every pin from the Dockerfiles and reports current-vs-latest. Explicitly NOT a scheduled workflow opening drift PRs - avoids CI noise and an auto-merge path.

<!-- fr:journal kind=decision scope=spec id=d4-testplan created=2026-07-23T18:18:34 -->
### d4-testplan · decision · Test Plan: dispatch a branch build, then live per-shell verification

agent-images CI runs on push, not pull_request, so a bump PR gets zero automatic coverage. Plan must explicitly 'gh workflow run build.yaml --ref <branch>' before merge, then live-verify each affected shell after frank's auto-bump lands.

<!-- fr:journal kind=decision scope=spec id=d5-models created=2026-07-23T18:18:35 -->
### d5-models · decision · All fr model tiers bound to claude-opus-4-8

Judgment-heavy work (risk assessment, changelog reading, patch rebasing); tier differentiation buys little. Persisted to ~/.config/fr/models.yaml for harness claude-code.

<!-- fr:journal kind=review scope=spec id=r1-spec-review created=2026-07-23T18:23:18 -->
### r1-spec-review · review · Spec reviewed against Q&A answers and codebase reality

Verified live: frank pins all at a59f499 (= agent-images HEAD); ruflo IngressRoute ruflo.cluster.derio.net + /api/v2/feature-flags probe; alert-agent has exactly 3 containers; gotcha files exist; cred-expiry rule in alert-rules-cm.yaml; all 10 smoke-test-* jobs named correctly; supercronic in base/Dockerfile. TWO CORRECTIONS APPLIED: (1) build.yaml push trigger is branch-restricted to main with paths-ignore docs/**, so pushing the feature branch does NOT build it - workflow_dispatch is the ONLY way to exercise a branch (strengthens the branch-build requirement); (2) smoke-test-infra-shell DOES exist, so infra-shell boots under CI even though it is deployed nowhere - the gap is in-cluster verification only, not all verification.
