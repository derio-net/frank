# Frank Gotchas — Agent shells (paperclip-shell, ruflo-shell, secure-agent-kali)

Long-form companion to the **Agent shells** section in `.claude/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

These all share the `agent-shell-base` image (s6-overlay v3 init, sshd, supercronic, tmux) and inherit the same gotchas.

## PVC mounts at `/home/claude` hide image-baked files

Entrypoints, configs, and templates must live outside (e.g., `/opt/`, `/entrypoint.sh`) and seed PVC contents on first boot.

## secure-agent-kali claude install pattern (intentional duplicate)

secure-agent-kali bootstraps `claude` via `npm i -g` (root-owned, at `/usr/bin/claude`) and updates via the native installer into `~/.local/bin/claude` on the PV. The `⚠ Leftover npm global installation at /usr/bin/claude` warning from `claude doctor` is **expected and intentional** — do not try to remove it. Baking the native installer into the image would be wiped by the PV mount on first boot.

## Supercronic auto-reloads on `~/.crontab` change

No restart needed after updating crontab content.

## Sidecar `runAsUser` overriding image default needs explicit `HOME`

Sidecar containers with `runAsUser` overriding the image's default UID need explicit `HOME` env var — the binary resolves HOME from `/etc/passwd` which points to the image-baked user's home dir (not writable under the overridden UID).

## s6-overlay v3 in non-root mode requires specific env

s6-overlay v3 in non-root mode requires `S6_KEEP_ENV=1` and `S6_VERBOSITY=2` — without these, services don't inherit the container env. The `with-contenv` wrapper around `cont-init.d` / `services.d` scripts is also required for them to see `$AGENT_HOME`.

## s6-overlay v3 in non-root mode also needs `/run` chown'd to AGENT_UID at image build time

Preinit writes `/run/s6-linux-init-container-results` and `/run/s6/container_environment` *directly under `/run`*, not just into pre-existing subdirs. Chowning only `/run/service`, `/run/s6`, `/run/s6-rc`, `/run/sshd` (etc.) leaves `/run` itself root-owned, and a pod with `allowPrivilegeEscalation: false` + `capabilities.drop=["ALL"]` cannot let `s6-overlay-suexec` chown it at runtime. Symptom: `fatal: /run belongs to uid 0 instead of 1000 and we're lacking the privileges to fix it`.

Fix: `chown -R ${AGENT_UID}:${AGENT_GID} /run /var/run` in the image. CI smoke tests must run `/init` under matching `--cap-drop=ALL --security-opt=no-new-privileges` to catch this — `--user 1000` alone is not strict enough.

## s6-overlay v3 ships `with-contenv` at `/command/`, NOT `/usr/bin/`

The canonical shebang for cont-init.d / cont-finish.d / services.d scripts is `#!/command/with-contenv bash`. Using `#!/usr/bin/with-contenv bash` (a common copy-paste error from older s6 v2 docs) makes every supervised script exit 127 ("not found" on the interpreter), which s6 reports as `cont-init: warning: some scripts exited nonzero` → `legacy-cont-init: command exited 1` → `rc.init: fatal: stopping the container`.

Same applies to anything you call from outside the supervisor (e.g. `kubectl exec ... s6-svstat ...`): `/command/` isn't on the agent-base PATH, so always use full paths like `/command/s6-svstat /run/service/sshd`. Suppressing stderr around such probes (`2>/dev/null`) silently converts an ENOENT into a "wait longer" — don't do that in smoke tests.

## `agent-shell-base` parameterizes user via `AGENT_USER` / `AGENT_HOME`

Defaults `agent` / `/home/agent`. `secure-agent-kali` overrides to `claude` / `/home/claude` to preserve PV-resident state. New shell-driven children inherit the defaults — don't hardcode `/home/claude` in any new `cont-init.d` / `services.d` script.

## `cont-init.d/30-authorized-keys` only fires at pod boot

It COPIES (not symlinks) `/etc/ssh-keys/authorized_keys` into `${AGENT_HOME}/.ssh/authorized_keys`. sshd runs with the default `AuthorizedKeysFile=~/.ssh/authorized_keys` (no drop-in in `/etc/ssh/sshd_config.d/`), so anything that lands in `/etc/ssh-keys/` after boot or that gets rotated mid-life never reaches sshd unless you re-run the hook by hand or restart the pod.

This bites two cases on every shell sidecar (ruflo-shell, paperclip-shell, secure-agent-kali):
- (1) bootstrapping the SOPS-managed `*-ssh-keys` Secret on a pod that's already running with `optional: true` on its volume — the pod booted with `/etc/ssh-keys/` empty so the `[ -f ]` guard short-circuited
- (2) any operator-key rotation

Recovery without restart:

```bash
kubectl exec -n <ns> deploy/<name> -c <shell> -- bash -c \
  'cp /etc/ssh-keys/authorized_keys "${AGENT_HOME:-/home/agent}/.ssh/authorized_keys" && \
   chmod 600 "${AGENT_HOME:-/home/agent}/.ssh/authorized_keys"'
```

Long-term fix would be a `ln -sf` in the hook so the symlink follows kubelet's atomic-projection rotations, but that's an agent-images change.

## tmux-continuum auto-restore only fires on fresh server start

`tmux source ~/.tmux.conf` in a running server reloads plugins but does NOT trigger restore. Auto-restore = fresh server start (i.e. the first attach after a pod restart).

## `/etc/skel/.tmux.conf` only seeds on first boot of a fresh PV

Existing PVs (like `secure-agent-kali`'s) keep their existing `~/.tmux.conf`. To pick up the resurrect/continuum config, append `source-file /etc/agent/tmux-resurrect.conf` to `~/.tmux.conf` manually once.

## s6 crashloop bail (5 deaths in 60s) leaves the service down silently

`sshd`-down is visible via the K8s readinessProbe (pod removed from LB); `supercronic`-down is only visible in `s6-svstat /run/service/supercronic`. Future enhancement: alert on bail. Recover by fixing the underlying cause then `s6-svc -u /run/service/<name>`.

## `shareProcessNamespace: true` is incompatible with agent-shell-base

Any pod where a sidecar container uses agent-shell-base (or any image where `s6-overlay-suexec` runs as the entrypoint) will fail with `s6-overlay-suexec: fatal: can only run as pid 1` once the pod's PID namespace is shared. The second container's entrypoint inherits a non-pid-1 slot, suexec refuses to start, and that container never reaches sshd / services.d.

If the goal is cross-container debugging via `ps -ef`, use the shared workspace volume instead (every shell sidecar already mounts `/workspace`); reach for `kubectl exec -c <other>` for live process inspection. Affects ruflo, paperclip, and any future hybrid pod that pairs an app container with an agent-shell-base sidecar.

## sshd scrubs container env on SSH login — env-dependent commands silently no-op

sshd runs with the OpenSSH default `PermitUserEnvironment no` posture and does not preserve the K8s `envFrom` env injected at PID 1, so anything launched via `ssh agent@<host> -- some-command` runs with the bare login env — `FRANK_C2_TELEGRAM_BOT_TOKEN`, `FRANK_C2_TELEGRAM_CHAT_ID`, `INFISICAL_*`, etc. are absent from the SSH session.

Concrete bite (paperclip-shell, ruflo-shell, any future shell sidecar): `ssh agent@<host> -- paperclip-shell-reconcile` runs reconcile fine and the MOTD updates, but `notify-telegram.sh` exits 0 silently on failure because the token isn't there. The boot-time path (`cont-init.d`) and `kubectl exec` both inherit PID-1 env and DO see the secrets.

Workarounds, in order of cleanliness:
- (a) source from `/proc/1/environ` inside the script — see MEMORY.md `pod_env_secrets.md` for the `_env_from_pid1 NAME` helper
- (b) use `kubectl exec` instead of `ssh` for env-dependent reconcile invocations
- (c) accept the silence and rely on MOTD as the SSH-path failure surface (the MOTD line is unaffected — it's written from `last-reconcile.motd` regardless of env)
