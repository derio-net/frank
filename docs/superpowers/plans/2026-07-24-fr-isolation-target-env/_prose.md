# FR_ISOLATION_TARGET=worktree on agent pods

**Spec:** docs/superpowers/specs/2026-07-24-fr-isolation-target-worktree-design.md
**Status:** In Progress
**Origin:** frank#686 (super-fr v3.15.0 isolation host modes, derio-net/super-fr#397)

## What and why

super-fr v3.15.0's host-worktree isolation mode activates on
`FR_ISOLATION_TARGET=worktree` in the process env: `fr isolation` runs as a
plain git worktree with zero docker/devcontainer calls, which is exactly what
frank's two unprivileged agent pods (no docker socket) need to run fr-goal /
fr-brainstorming / fr-debugging in-pod. This plan declares the variable on
all four agent-bearing containers and — per the operator's "full SSH
coverage" decision — re-exports it into SSH/Mosh login shells via the
established profile.d shim pattern, because sshd scrubs container env from
login shells (the documented agent-shells gotcha).

Containers: `kali` + `vk-local` (secure-agent-pod), `hermes` + `ssh`
(hermes-agent-shell). `hindsight` is excluded (no agent processes). The
hermes pod's existing `35-hermes-agent-shell-byok-env.sh` shim gains the var;
secure-agent-pod gets a new equivalent shim ConfigMap mounted into the kali
container.

## Shape

Phase 1 is one TDD cycle: a repo-local guard test
(`scripts/tests/test_fr_isolation_target_env.py`, the crowdsec/tekton guard
pattern) written failing-first pins all of it — env values, shim contents,
mount — then the manifest edits turn it green, then the gotcha docs. Phase 2
is the back-loaded manual phase: operator merges (Recreate roll drops live
sessions briefly — operator picks timing), agent smoke-tests the live env +
login shells + one minimal in-pod fr walk, operator drives the super-fr
`hermes-agent-compat` Phase 8 hermes walk separately.

## Post-deploy checklist applicability

Fix/extension of the agent-shells layer: no new service, nothing to expose,
no blog posts (gotcha one-liner + runbook prose instead, done in P1.T3), no
README change, no manual-operation runbook blocks (the change is fully
declarative; the manual phase is one-time verification, not reproducible
cluster state).
