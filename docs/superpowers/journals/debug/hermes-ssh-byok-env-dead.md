# Journal: hermes-ssh-byok-env-dead

<!-- fr:journal kind=repro scope=debug id=28342281fdea created=2026-07-24T22:28:03 -->
### 28342281fdea · repro · BYOK env dead in hermes ssh sidecar login shells

frank#688: OPENAI_BASE_URL/OPENAI_API_KEY absent in SSH/Mosh login shells on the ssh sidecar, so hermes has no LiteLLM auth. Repro (live, 2026-07-24): `kubectl exec -c ssh -- tr '\0' '\n' < /proc/1/environ | grep -c '^OPENAI'` -> 0; `kubectl exec -c ssh -- env -i HOME=/opt/data/home bash -lc 'echo ${OPENAI_BASE_URL:-MISSING}'` -> MISSING.

<!-- fr:journal kind=root-cause scope=debug id=43fcce766457 created=2026-07-24T22:28:03 -->
### 43fcce766457 · root-cause · sshd is PID 1 in the sidecar; OpenSSH clobbers /proc/1/environ with proctitle

The ssh sidecar (hermes-agent-shell-ssh) has no s6/init: its entrypoint exec's /usr/sbin/sshd, so sshd is PID 1. OpenSSH overwrites its argv/environ with the process title ('sshd: … [listener] …'), so /proc/1/environ returns proctitle bytes, not the env. The 35-…-byok-env.sh shim re-exports from /proc/1/environ -> reads junk -> exports nothing. Sibling fix #689/#690 gave the STATIC FR_ISOLATION_TARGET a literal fallback, but the DYNAMIC BYOK secrets cannot be hardcoded, so they stay dead. Latent since the official-image migration split the pod into hermes (main, s6 /init) + ssh (sidecar, foreground sshd PID 1).

<!-- fr:journal kind=hypothesis scope=debug id=5cc743f7d4f9 created=2026-07-24T22:29:28 -->
### 5cc743f7d4f9 · hypothesis · Capture the container env at sidecar start, before sshd clobbers it

Frank-side fix (issue candidate 1, no image rebuild): override the ssh container command to snapshot the dynamic BYOK secrets (OPENAI_BASE_URL/OPENAI_API_KEY) from the container env to a memory-tmpfs file, THEN exec the image entrypoint (not raw sshd — keep its host-key + authorized_keys prep). The byok-env shim reads that file for the dynamic vars (fallback after /proc/1/environ, which still works on s6 hosts like kali). Consistent with the sibling #689/#690 frank-side shim precedent; deployable via ArgoCD with no agent-images build+bump. Guard test locks command+volume+shim invariants.

<!-- fr:journal kind=finding scope=debug id=d882e9e70e53 created=2026-07-24T22:33:23 state=fixed -->
### d882e9e70e53 · finding [fixed] · command-wrapper env snapshot to memory tmpfs + shim read

Fix: ssh container command override snapshots OPENAI_BASE_URL/OPENAI_API_KEY from the container env to /run/hermes-env/byok (emptyDir medium: Memory, 0600 via umask 077) then exec's the image entrypoint; the 35-…-byok-env.sh shim reads that file as a fallback after /proc/1/environ. Failing test pinning it: scripts/tests/test_hermes_ssh_byok_env_snapshot.py (3 invariants: command snapshots+exec's entrypoint, memory emptyDir mount, shim reads snapshot). Functionally simulated end-to-end: scrubbed login shell recovers both secrets + FR_ISOLATION_TARGET. Files: apps/hermes-agent-shell/manifests/deployment.yaml, configmap-byok-env.yaml.
