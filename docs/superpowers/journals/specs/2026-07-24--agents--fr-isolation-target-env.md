# Journal: 2026-07-24--agents--fr-isolation-target-env

<!-- fr:journal kind=decision scope=spec id=qa-ssh-coverage created=2026-07-24T16:46:10 -->
### qa-ssh-coverage · decision · Full SSH coverage: env on all 4 agent containers + profile.d shims on both pods

Operator chose full coverage over issue-as-written env-only. Env var FR_ISOLATION_TARGET=worktree goes on kali+vk-local (secure-agent-pod) and hermes+ssh (hermes-agent-shell); the existing hermes byok-env shim gains FR_ISOLATION_TARGET in its re-export list; secure-agent-pod gets a new equivalent profile.d shim ConfigMap (subPath pattern) so SSH/Mosh login shells see the var despite sshd env scrubbing. hindsight container excluded (no agent processes).

<!-- fr:journal kind=decision scope=spec id=qa-test-plan-ownership created=2026-07-24T16:46:12 -->
### qa-test-plan-ownership · decision · Post-merge: agent smoke-tests env + one in-pod fr walk; operator drives super-fr Phase 8

After the operator merges and ArgoCD rolls both Deployments (Recreate), the agent verifies FR_ISOLATION_TARGET in all four target containers via kubectl exec and runs one minimal fr isolation up/exec/down walk in secure-agent-pod. The full hermes live fr-goal walk (super-fr hermes-agent-compat Phase 8, acceptance rows isolation-host-worktree-e2e) remains operator-owned per the super-fr spec Test Plan.

<!-- fr:journal kind=review scope=spec id=spec-self-review created=2026-07-24T16:47:48 -->
### spec-self-review · review · Spec reviewed against Q&A + codebase: all named files/patterns exist

Verified: hermes byok-env shim exists with named-list loop (configmap-byok-env.yaml); kali+vk-local and hermes+ssh containers as described; kali runs fully as UID 1000 so /proc/1/environ is readable; both Application CRs source apps/<app>/manifests raw so a new ConfigMap file deploys with no template change; scripts/tests/ guard pattern (pytest+yaml, REPO_ROOT=parents[2]) matches the planned test. Caveat folded into spec: scripts/tests/ is a local guard (not in CI). No findings requiring redesign.
