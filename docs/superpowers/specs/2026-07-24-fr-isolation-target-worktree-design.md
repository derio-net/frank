# FR_ISOLATION_TARGET=worktree on agent pods — design

Status: design
Origin: frank#686 (filed from the super-fr v3.15.0 isolation-host-modes work,
derio-net/super-fr#397). Operator Q&A 2026-07-24: full SSH coverage chosen
over issue-as-written env-only; post-merge smoke test agent-driven, the live
hermes fr-goal walk (super-fr `hermes-agent-compat` Phase 8) operator-owned.
Target repo: derio-net/frank (`apps/hermes-agent-shell/`,
`apps/secure-agent-pod/`, `scripts/tests/`).

## Problem

super-fr v3.15.0 shipped docker-less isolation host modes. **Host-worktree
mode** activates when the process env carries `FR_ISOLATION_TARGET=worktree`:
`fr isolation up/exec/down` runs as a plain git worktree in the host env —
zero docker/devcontainer calls — making fr-goal / fr-brainstorming /
fr-debugging runnable inside unprivileged containers. Unknown values fail
closed; hosts without the variable are unchanged. Contract: super-fr spec §B
(`derio-net/super-fr:docs/superpowers/implemented/specs/2026-07-24-isolation-host-modes-design.md`)
— the host env IS the env: pods keep their ESO-injected creds, fr provisions
no secrets.

Frank's two agent pods are exactly the "Type 2 docker-less worktree host"
class that spec names, and neither declares the variable yet:

- **hermes-agent-shell** — blocks super-fr `hermes-agent-compat` Phase 8
  (the live in-pod fr-goal walk) and that spec's Test Plan step 2.
- **secure-agent-pod** (VK-attached) — blocks the fr-isolating flows for
  agents in VK workspaces (Test Plan step 4 spot-check).

A plain env var is not quite sufficient on its own: both pods serve
interactive agents over SSH/Mosh, and sshd (`UsePAM no`, no
`PermitUserEnvironment`) scrubs the container env from login shells — the
documented "sshd scrubs container env on login" gotcha
(`docs/runbooks/frank-gotchas/agent-shells.md`). Env-only would cover VK
executors (children of vk-local) and `kubectl exec` sessions, but an agent
SSHing in would silently fall back to devcontainer mode and fail.

## Design

Declare `FR_ISOLATION_TARGET=worktree` in every agent-bearing container, and
re-export it into SSH login shells via the established profile.d-shim
pattern.

### 1. Container env (4 containers, 2 Deployments)

Add to `env:` with a one-line comment referencing frank#686 / super-fr §B:

| Deployment | Container | Why |
|---|---|---|
| `secure-agent-pod` | `kali` | interactive agent shell (SSH + `kubectl exec`) |
| `secure-agent-pod` | `vk-local` | spawns VK executor processes — they inherit this env |
| `hermes-agent-shell` | `hermes` | gateway runs the agent's terminal commands |
| `hermes-agent-shell` | `ssh` | interactive sidecar (SSH/Mosh + `kubectl exec`) |

Excluded: `hindsight` (Postgres/embedder sidecar, no agent processes).

### 2. hermes SSH login shells — extend the existing shim

`apps/hermes-agent-shell/manifests/configmap-byok-env.yaml` already
re-exports a named list of vars from `/proc/1/environ` into login shells
(`35-hermes-agent-shell-byok-env.sh`). Add `FR_ISOLATION_TARGET` to the loop
list (`OPENAI_BASE_URL OPENAI_API_KEY FR_ISOLATION_TARGET`). No new mounts.
Note: the shim file is a subPath mount — kubelet never live-updates it — but
the value is static, so a normal pod roll (which this PR causes anyway)
suffices.

### 3. secure-agent-pod SSH login shells — new shim, same pattern

The kali image has no in-repo shim. Add one following the hermes pattern
exactly:

- New `apps/secure-agent-pod/manifests/configmap-fr-env.yaml`: ConfigMap
  `secure-agent-pod-env` (ns `secure-agent-pod`), key
  `35-secure-agent-pod-fr-env.sh` — same `/proc/1/environ` re-export loop,
  list containing only `FR_ISOLATION_TARGET`. Readable because the kali
  container runs entirely as UID 1000 (PID 1 same UID). Numbered 35- to run
  before the image's `50-…-motd.sh`.
- `kali` container: volume `fr-env` (configMap) + single-file subPath mount
  at `/etc/profile.d/35-secure-agent-pod-fr-env.sh`, readOnly.
- `vk-local` needs no shim (no sshd; executors inherit process env).

### 4. Guard test (the TDD vehicle)

`scripts/tests/test_fr_isolation_target_env.py` — repo-local guard in the
existing `scripts/tests/` pattern (crowdsec, tekton guards). Asserts, by
parsing the two deployment YAMLs and the two ConfigMaps:

1. all four containers above carry `FR_ISOLATION_TARGET=worktree`;
2. the hermes shim's re-export list contains `FR_ISOLATION_TARGET`;
3. the secure-agent-pod shim ConfigMap exists and the `kali` container
   mounts it at `/etc/profile.d/35-secure-agent-pod-fr-env.sh` via subPath.

Written failing-first; implementation makes it green.

## Non-goals

- No fr CLI installation changes — whether `fr` is present in the pod images
  is agent-images/PVC territory, not this change.
- No external-mode (`.fr-isolation` marker) plumbing — frank's pods are
  long-lived host-worktree hosts, not per-run prepared containers.
- No change to `hindsight` or any non-agent container.

## Rollout note

Both Deployments use `strategy: Recreate`; ArgoCD auto-sync on merge rolls
both pods, briefly dropping live SSH/tmux/VK sessions. The operator controls
timing by choosing when to merge.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-07-24-fr-isolation-target-env | `derio-net/frank` | `2026-07-24-fr-isolation-target-env` | — |

## Test Plan

Post-merge — split ownership per the Q&A:

**Agent-driven smoke (this session, after the operator reports the merge and
ArgoCD syncs):**

1. `kubectl exec` into each of the four containers → `env | grep
   FR_ISOLATION_TARGET` shows `worktree`
   (`fr-isolation-env-in-pods`).
2. Login-shell check on both pods: `bash -lc 'echo $FR_ISOLATION_TARGET'`
   via SSH (or `kubectl exec … bash -lc` as fallback proof of the profile.d
   sourcing) shows `worktree` (`fr-isolation-env-ssh-login`).
3. One minimal in-pod walk in secure-agent-pod (if the `fr` CLI is present
   on the PVC): `fr isolation up --branch feat/smoke → exec → down`,
   verifying no docker/devcontainer invocation. If `fr` is absent, record
   that as the pod's separate gap — the env contract is still proven by 1–2.

**Operator-driven:** the live hermes fr-goal walk = super-fr
`hermes-agent-compat` Phase 8, flipping super-fr's
`isolation-host-worktree-e2e` acceptance row; VK workspace spot-check
(super-fr Test Plan step 4).
