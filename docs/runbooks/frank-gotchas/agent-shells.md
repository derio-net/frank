# Frank Gotchas — Agent shells (paperclip-shell, ruflo-shell, secure-agent-kali)

Long-form companion to the **Agent shells** section in `agents/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

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

## vk-local 4 Gi limit is load-bearing when the bridge over-feeds the executor cap

`VK_MAX_CONCURRENT_EXECUTIONS=4` bounds *active* executor spawns inside vibe-kanban; it does NOT bound the bridge's own slot count (separate config in `agent-images`). When the bridge dispatches more cards than the executor cap, the surplus queues inside vk-local and the queued sessions retain non-zero memory (claude/npm/node child trees survive across the semaphore wait). The design memo for PR #264 assumed queued sessions held ~0 MiB; the 2026-05-18 incident invalidated that assumption.

**Incident — 2026-05-18 07:10:57 UTC**: `vk-local` OOMKilled (exit 137) on `secure-agent-pod-f88d4cfb6-8ds89` / gpu-1, ~9.5h after the May 17 23:40 CEST image bump to `agent-images@be41440`. Bridge log immediately pre-kill: `active workspaces: 8, max: 8, slots available: 0` with 10 existing VK cards. MCP timeouts (`No response from MCP server within 30.0s`) preceded SIGKILL — classic cgroup pressure → GC stall → unresponsiveness chain. Phase 5 soak (2026-05-03 → 16) had peaked at p99 2.95 GiB with queue depth 3; the 4 Gi limit chosen on commit `390f64a` left only 1 Gi headroom and a 2× bump in upstream load consumed it.

**Mitigation**: vk-local `limits.memory` restored to 8 Gi (the pre-dial-back value). Do not re-dial-back without:
1. Capping the bridge's own slot count at or below `VK_MAX_CONCURRENT_EXECUTIONS` (so queue depth in vk-local stays bounded), OR
2. Re-running the soak under realistic busy load (≥8 in-flight cards for 14 days) and seeing p99 RSS stay below 3 GiB.

**Diagnostics**: kubectl describe pod's `lastState.terminated.reason: OOMKilled` is the canonical signal — Kubernetes events age out within ~1h on Frank, so the pod-level field is more durable. The metrics-server may also be down in this cluster (kubectl top fails with "Metrics API not available"), so prefer cadvisor → VictoriaMetrics for memory time-series.

## vk-issue-bridge 30 s MCP timeout cascades to zombie execution_processes

The bridge's MCP client (`/opt/scripts/vk_mcp_client.py:76`) defaults `_recv(timeout=30.0)`. Heavy operations — notably `start_workspace`, which provisions a git worktree + imports CLAUDE.md/AGENTS.md + runs setupscript — routinely exceed 30 s under bridge load (≥4 active sibling workspaces hammering the longhorn-backed `/home/claude` PV). On timeout:

1. Bridge raises `TimeoutError` and `sys.exit`s (no `try/except` around the `sync_issue()` call in `vk-issue-bridge.py:1066`).
2. Server-side, vk-local's request-handler future is dropped, which **cancels the `Child::wait().await`** for the in-flight setupscript / codingagent / cleanupscript.
3. The child shell process runs to completion (`|| true` ensures exit 0) but **vibe-kanban never calls `waitpid()`** because the wait future was cancelled. Child → zombie. DB row stays `status='running'` forever.
4. UI shows the workspace stuck "active" with no output. New bridge cycles add more.

**Detection signals** (any one is sufficient):

- `ps -eo pid,etime,comm,args` inside vk-local shows multiple `[sh] <defunct>` children of `vibe-kanban` PID 7.
- `python3 -c "import sqlite3; ..."` against `/home/claude/.local/share/vibe-kanban/db.v2.sqlite`:
  `SELECT status, COUNT(*) FROM execution_processes GROUP BY status` shows multiple `running` rows whose `created_at` is >5 min ago and `completed_at IS NULL`.
- Bridge log on supercronic in the kali container: traceback at `vk_mcp_client.py:81 TimeoutError: No response from MCP server within 30.0s`, then `[bridge] starting — dry_run=False` on next cycle (proves the crash-restart loop).

**Recovery** (canonical, non-destructive — used on 2026-05-18):

```bash
POD=$(kubectl get pod -n secure-agent-pod -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n secure-agent-pod $POD -c vk-local -- kill -TERM 1
# tini propagates SIGTERM → vibe-kanban shuts down → k8s restarts vk-local only.
# At startup, vk-local logs `Found orphaned execution process X / Marked X as failed` for every stuck row.
# Worktrees on the PVC survive — check /var/tmp/vibe-kanban/worktrees/ before re-running cards whose coding agent had already completed (some `running` rows are the trailing cleanupscript only).
```

**Important — check whether the codingagent actually finished before retrying**: not all `failed` cards need to be re-run. Some have a `completed` codingagent and only a stuck cleanupscript. Inspect the worktree diff first:

```bash
ls -la /var/tmp/vibe-kanban/worktrees/<hash>-<name>/frank/
cd /var/tmp/vibe-kanban/worktrees/<hash>-<name>/frank && git status && git log --oneline -5
```

**Durable fix** lives upstream of frank — in the bridge code, migrated from `derio-net/agent-images` to `derio-net/super-fr` (the `fr_vk.bridge` module). Two changes are needed there:
1. Bump the MCP client's `_recv` default timeout from `30.0` to `180.0`.
2. Wrap the `sync_issue()` invocation in the bridge `main()` with `try/except TimeoutError: continue` so a single slow call doesn't kill the whole cycle.

There's also an upstream `vibe-kanban` server-side bug — the request-handler future should not own the `Child::wait()` lifetime; child processes should be tracked in a global registry with a background reaper. That's a forked-fork change in `derio-net/vibe-kanban`, lower priority once the timeout is bumped.

## sshd scrubs container env on SSH login — env-dependent commands silently no-op

sshd runs with the OpenSSH default `PermitUserEnvironment no` posture and does not preserve the K8s `envFrom` env injected at PID 1, so anything launched via `ssh agent@<host> -- some-command` runs with the bare login env — `FRANK_C2_TELEGRAM_BOT_TOKEN`, `FRANK_C2_TELEGRAM_CHAT_ID`, `INFISICAL_*`, etc. are absent from the SSH session.

Concrete bite (paperclip-shell, ruflo-shell, any future shell sidecar): `ssh agent@<host> -- paperclip-shell-reconcile` runs reconcile fine and the MOTD updates, but `notify-telegram.sh` exits 0 silently on failure because the token isn't there. The boot-time path (`cont-init.d`) and `kubectl exec` both inherit PID-1 env and DO see the secrets.

Workarounds, in order of cleanliness:
- (a) source from `/proc/1/environ` inside the script — see MEMORY.md `pod_env_secrets.md` for the `_env_from_pid1 NAME` helper
- (b) use `kubectl exec` instead of `ssh` for env-dependent reconcile invocations
- (c) accept the silence and rely on MOTD as the SSH-path failure surface (the MOTD line is unaffected — it's written from `last-reconcile.motd` regardless of env)

## secure-agent-kali build: pin `kali.download`, never the `http.kali.org` redirector

The `agent-images` kali Dockerfile builds on `debian:bookworm-slim` → `agent-base` → `agent-shell-base`, then adds the kali-rolling repo and `apt-get dist-upgrade`s onto it. The repo URL **must** be the official Cloudflare-backed CDN `https://kali.download/kali`, not `https://http.kali.org/kali`.

`http.kali.org` is a redirector that round-robins to community mirrors of varying freshness. During a fast rolling transition (the GCC-16 toolchain churn of 2026-05), a mirror's `Packages` index can advertise a version whose `.deb` has not propagated to (or was already GC'd from) that mirror's `pool/`. `dist-upgrade` then fails with a hard 404:

```
E: Failed to fetch .../pool/main/g/gcc-16/gcc-16-base_16-20260322-1_amd64.deb  404  Not Found
E: Unable to fetch some archives, maybe run apt-get update or try with --fix-missing?
```

The failure is **non-deterministic and mirror-dependent** — a local build (or a CI retry minutes later) that happens to hit a consistent mirror passes, which makes it look transient. It is not: any community mirror can be index↔pool-skewed at any time. `kali.download` keeps its index and pool consistent. Diagnosis that nails it without a full build: probe the exact 404'd deb on both mirrors —

```bash
for m in http://http.kali.org/kali https://kali.download/kali; do
  curl -s -o /dev/null -w "%{http_code} $m\n" -L "$m/pool/main/g/gcc-16/gcc-16-base_16-20260322-1_amd64.deb"
done
# http.kali.org → 404, kali.download → 200, while both indexes advertise the same version.
```

First hit: `agent-images` build for the VK_BRIDGE_PIN v2.2.13 bump (2026-05-25). Fixed in `kali/Dockerfile` in `derio-net/agent-images`.

## The `fr_vk.bridge` daemon logs its banner to stderr — smoke tests must capture `2>&1`

The PVC-resident bridge (`fr_vk.bridge` module — formerly v2 `vk.bridge` — installed by `cont-init.d/55-install-fr-bridge` from a `super-fr` git tag) emits its per-tick banner and `dry-run complete` line via Python **logging**, which writes to **stderr**, not stdout:

```
$ python -m fr_vk.bridge --dry-run 1>/tmp/out 2>/tmp/err   # exits 0
$ cat /tmp/out      # empty
$ cat /tmp/err
[bridge] - v2.2.13 - 2026-05-25 16:26:48 UTC - tick
fr_vk.bridge: dry-run complete
```

Any health check or CI smoke test that does `out=$(fr-bridge --dry-run)` captures **stdout only** → `$out` is empty → banner/version assertions fail. Under bash `set -eo pipefail` (GitHub Actions default) the step then aborts before any teardown/diagnostics run, so the log shows the banner printed live (uncaptured stderr) followed immediately by an unexplained exit 1. Always `2>&1` the capture.

This silently broke `agent-images`' `smoke-test-secure-agent-kali` job on **every** build after the 2026-05-19 v2-bridge cutover — the kali image had not published a green build from `main` for a week before it was diagnosed (2026-05-25). The pre-cutover v1 bridge printed to stdout, which is why the same test passed on bridge ≤ v2.1.7.

## BYOK shells: hermes ≥0.15 ignores OPENAI_* env for chat — pin the provider in config.yaml

The hermes-agent-shell BYOK contract supplies `OPENAI_BASE_URL` + `OPENAI_API_KEY` (ExternalSecret → container env → `/etc/profile.d/35-…-byok-env.sh` shim into login shells). The hermes CLI does **not** consume those for chat inference by itself: provider `auto` resolves to **openrouter** (→ `HTTP 401 Missing Authentication header` against `https://openrouter.ai/api/v1` on first `hermes` run), and the plain `OPENAI_API_KEY` registers only as the STT/TTS key in `hermes config`.

What does and doesn't pin the default provider (verified on v0.15.2, 2026-06-04):

- **Works** — `model:` as a *mapping* in `~/.hermes/config.yaml` (`hermes_cli/auth.py` reads `model_cfg.get("provider")`):
  ```yaml
  model:
    default: mistral-small-24b
    provider: litellm        # user-defined name from providers:
  providers:
    litellm:
      base_url: http://litellm.litellm.svc:4000/v1
      key_env: OPENAI_API_KEY   # resolved from the login-shell env (BYOK shim)
  ```
- **Works** — explicit flag: `hermes chat --provider litellm -m <alias>` (user-defined names are valid `--provider` values; they normalize to the built-in `custom` path with the entry's `base_url`).
- **Does NOT work** — every model-string prefix form: `model: litellm/<alias>`, `model: custom/<alias>`, `model: custom:litellm:<alias>`. The model string is opaque in this build; the whole string is sent as the model name to the *default* provider (openrouter). The paperclip-era `ollama-cloud/<alias>` trick worked because `ollama-cloud` is a built-in provider — it does not generalize to user-defined names.

Provider entry schema (`providers:` keyed dict, v12+ config; `custom_providers:` list is the legacy equivalent): `base_url`, `api_key`/`key_env`/`api_key_env`, `api_mode`, `model`/`default_model`/`models`, `extra_body`, … (see `_KNOWN_KEYS` in `hermes_cli/config.py`). Unknown keys log a warning and are ignored.

`~/.hermes/config.yaml` lives on the home PVC — it survives restarts but is **not** declarative; seeding it is a manual operation (`orch-hermes-config-provider` in the runbook). Model-side note: the "every reply is a fake tool-call JSON" symptom (`{"name": "text_to_speech", …}`) was NOT a model quirk — it was LiteLLM's `ollama/` prefix breaking tools+streaming; fixed cluster-wide by switching the lineup to `ollama_chat/` (see the LiteLLM entry in `other-apps.md`). Residual genuine model quirks: thinking models can return reasoning-only turns (`qwen36-a3b` exhausted retries with content-free reasoning). `mistral-small-24b` is the most coherent local default; switch per-session with `/model`. The `hermes-405b` LiteLLM DB alias routes to OpenRouter (`Model Group=hermes-4`) which rejects tool-use requests (404) — dead since the 2026-06-04 cloud-alias purge.

## hermes shell: fetch-text for web pages + context budgets must mirror the server (2026-06-06)

Hermes v0.15.2 has **no key-free native web-extract backend** (firecrawl /
tavily / exa / parallel / xai need paid keys; ddgs and searxng are
search-only), so "read this URL" degrades to terminal `curl -s` and floods the
context window with raw HTML — the trigger of the 2026-06-06 session-amnesia
incident (full chain in other-apps.md).

- `fetch-text <url>` — ConfigMap-mounted stdlib-only extractor at
  `/usr/local/bin/fetch-text` (`apps/hermes-agent-shell/manifests/
  configmap-fetch-text.yaml`, subPath mount, 0755). Title + body text,
  20k-char default cap (`--max-chars`), `--stdin` mode for tests
  (`scripts/tests/test_fetch_text.py` runs the exact ConfigMap bytes).
  kubelet never live-updates subPath mounts — script edits need a pod
  restart. SOUL.md carries the steering line (manual-op
  `orch-hermes-soul-fetch-text`).
- Context budgets live in the hermes config.yaml on the PVC
  (`providers.litellm.models.<alias>.context_length`) and MUST mirror live
  server reality: 64k pair = 65536, all other aliases =
  `OLLAMA_CONTEXT_LENGTH` = 16384 (manual-op `orch-hermes-context-budgets`).
  When the gateway lineup changes, update both together — a believed window
  larger than the real one re-opens the silent-truncation amnesia hole; the
  resolver's fallback for unknown aliases is 256K.
- `tool_output.max_bytes` is 24000 (was 50000): the largest single tool
  result that still leaves >50% of a 16k window when the operator `/mode`s
  to a non-64k model.
- Default model is `gemma-12b-64k-nothin`; `/mode gemma-12b-64k` re-enables
  thinking when reasoning depth is worth the latency.

### Rework-1 addendum (2026-06-06): the 64k floor, the clamp, and the brain transplant

- **hermes hard-requires ≥64k context** — its preamble alone is ~15k tokens
  (`in≈15,030` per API call on a trivial task). With truthful budgets it
  refuses every 16k model at init: *"below the minimum 64,000 required."*
  Don't "fix" this with a lying `context_length` override — that re-opens the
  silent-truncation amnesia hole.
- **Derived-tag `num_ctx` silently clamps to the trained ceiling** —
  `qwen3:14b` requested at 65536 loads at 40,960; the Modelfile accepts the
  value, `ollama create` succeeds, and only `ollama ps` CONTEXT shows the
  truth. Check it for every new derived tag.
- **gemma4-12B failed the hermes agentic gate** (think off: hallucinated tool
  names + a 90-iteration identical-call loop on `hostname`, confabulated
  answer; think on: skipped tools, confabulated a summary from the URL slug).
  Plain chat/vision is fine — keep `gemma-12b-64k-nothin` for that.
- **`qwen36-a3b-64k` is the hermes default and agent brain** — gate PASSED
  2026-06-06 (4/4): grounded fetch-text summary of the killer blog post,
  exact URL+command recall in a continued session, `hostname` in ONE tool
  call (gemma4 took 90 and confabulated), 0 ollama truncations. Measured: 24 GB total, 39/61 CPU/GPU hybrid (MoE
  3B-active), 61 t/s generation, 1,792 t/s long prefill — hermes's preamble
  costs ~8 s cold, then ollama prefix-caches across session turns.
- Loop insurance: `tool_loop_guardrails.hard_stop_enabled: true` in hermes
  config.yaml (default thresholds stop identical no-progress tool calls at 5).

## `claude install` group-OOMs 4Gi shell pods — Bun HTTP buffering (~17×), all SSH sessions drop at once

**Incident (2026-06-07, hermes-agent-shell):** operator ran `claude install` in an SSH session;
every SSH connection to the pod closed simultaneously and the pod went CrashLoopBackOff-ish
(4 restarts across the incident, including diagnosis re-runs).

**Mechanism.** The container cgroup has `memory.oom.group` set, so the kernel kills *every*
task in the cgroup when one process trips the limit — sshd included. That's the "all sessions
die at the same instant" signature, distinct from a single killed session. The tripping
process: `claude install` downloads the ~245 MB native build **in-process** via Bun's HTTP
client, which buffers the artifact ~17× in anonymous memory (kernel killed it at anon-rss
4,172,660 kB ≈ 4.17 GiB; 17 × 245 MB ≈ 4.16 GiB — near-exact match). Kernel evidence
(`talosctl -n <node> dmesg`): `claude` with thread "HTTP Client", `total-vm` ~73 GB (normal
JSC reservation, ignore it), anon-rss ≈ the pod limit, then `memory.oom.group` kill list.

**What does NOT work:**
- `BUN_JSC_forceRAMSize` — the buffering is in Bun's native HTTP layer, below JSC GC. Tested, OOM'd identically.
- `curl -fsSL https://claude.ai/install.sh | bash` — the script's *download* is plain curl
  (fine), but its last step runs `"$binary" install`, and `claude install` **re-downloads via
  the same Bun path even when the running binary IS the target version**. Tested, OOM'd identically.
- Upstream: claude-code#22536, closed not-planned.

**Memory-safe install (constant-memory, what the installer would have produced):**

```bash
DL=https://downloads.claude.ai/claude-code-releases
version=$(curl -fsSL "$DL/latest")
checksum=$(curl -fsSL "$DL/$version/manifest.json" | jq -r '.platforms["linux-x64"].checksum')
vdir="$HOME/.local/share/claude/versions"
mkdir -p "$vdir" "$HOME/.local/bin"
curl -fsSL -o "$vdir/$version.tmp" "$DL/$version/linux-x64/claude"
echo "$checksum  $vdir/$version.tmp" | sha256sum -c
chmod +x "$vdir/$version.tmp" && mv "$vdir/$version.tmp" "$vdir/$version"
ln -sfn "$vdir/$version" "$HOME/.local/bin/claude"
claude --version   # login shells resolve ~/.local/bin ahead of the baked /usr/bin/claude
```

**Durable fix:** hermes-agent-shell limit raised 4Gi → 8Gi (peak ~4.2–4.5 GiB fits; kali's
32Gi is why the same install always worked there). Residual risk at 4Gi-class pods: the
native build's **background auto-updater** uses the same download path — i.e. a pod can
group-OOM mid-session with no operator action; either give the pod ≥8Gi or set
`DISABLE_AUTOUPDATER=1`.

## hermes-agent-shell: Hermes venv is PVC-resident, seeded from a relocatable image seed (frank#496)

The `agent` user (uid 1000) in `hermes-agent-shell` cannot patch image-baked
files: the pod is `runAsNonRoot` + `allowPrivilegeEscalation: false` +
`capabilities.drop: ["ALL"]`, and `fsGroup: 1000` only re-groups *mounted
volumes*, never image layers. The old image baked the Hermes venv `root:root`
at `/opt/hermes-agent`, so maintaining Hermes in-pod (`hermes update`,
hot-patching `site-packages`) was impossible — the frank#496 incident.

**Design (image `agent-images@83bdab4`+):**

- The image bakes a **relocatable** seed venv at `/opt/hermes-agent`
  (`uv venv --relocatable` — console scripts get a `#!/bin/sh` polyglot
  shebang that re-execs python by *relative* path, so the venv runs from any
  directory after a copy). It is a read-only build artifact, NOT the live
  runtime. The auto-continue patch (below) is `git apply`'d into it at build,
  and `/opt/hermes-agent/.seed-version` is stamped `<HERMES_VERSION>+autocontinueN`.
- On first boot, `cont-init.d/35-hermes-venv-seed` (runs as uid 1000, before
  `40-shell-inventory`) `cp -a`'s the seed onto the `/home/agent` PVC at
  **`/home/agent/.local/opt/hermes-agent`** — the **live** venv, uid-1000-owned
  and writable. The launcher `/usr/local/bin/hermes` points at the PVC venv.
  In-pod patches / `hermes update` now persist across pod restarts.
- **Version-gated re-seed:** the hook compares `$SEED/.seed-version` vs the live
  marker. Mismatch (first boot, or an image/Hermes bump) → replace the live
  venv (superseding any in-pod patches with the new image's). Match → no-op,
  **preserving** in-pod hot-patches. So an image bump cleanly rolls forward;
  a plain restart keeps the operator's edits.
- The venv cannot be baked directly at the PVC path — the PVC mount at
  `/home/agent` **shadows** anything baked under it (see the "PVC mounts hide
  image-baked files" gotcha above).

**Manual re-seed:** the hook's shebang is `#!/command/with-contenv bash` (s6
execline wrapper, only resolves inside supervised cont-init). To re-run it by
hand, invoke via bash — a bare `docker exec`/`kubectl exec
.../35-hermes-venv-seed` hits `execlineb: fatal: unable to exec ifelse` (exit
127) because the execline env isn't set up:

```bash
kubectl exec -n hermes-agent-shell deploy/hermes-agent-shell -- \
  bash /etc/cont-init.d/35-hermes-venv-seed
```

**Auto-continue patch (baked):** `agent-images/hermes-agent-shell/patches/hermes-autocontinue-chat-completions.patch`
widens one gate in Hermes' `agent/conversation_loop.py`. Hermes v0.15.2 ships a
countermeasure for the "announce-only turn" failure (a planning/ack message
with `finish_reason=stop` and no tool call — endemic to `qwen36-a3b` at ~16k
ctx): it injects `[System: Continue now. Execute the required tool calls…]` and
loops. But it was gated on `api_mode == "codex_responses"`, so it never fired
on Frank's OpenAI-compatible LiteLLM path (`api_mode == "chat_completions"`,
the `determine_api_mode` default for a custom provider on
`http://litellm.litellm.svc:4000/v1`). The patch widens the gate to
`in ("codex_responses", "chat_completions")`; the detection heuristic
(`looks_like_codex_intermediate_ack`) is provider-agnostic. Applied at build
with `git apply` (zero fuzz → the build fails if the hunk drifts on a
`HERMES_VERSION` bump; refresh the patch then, and bump the `+autocontinueN`
seed-version suffix so live pods re-seed).

## hermes-agent-shell Hindsight sidecar: pod-level `fsGroup` re-loosens PGDATA on every remount

The Hindsight sidecar runs Postgres on its own Longhorn PVC at `/opt/hindsight/pgdata`. A pod recreate/remount re-applies the pod-level `fsGroup: 1000` across that volume (default `fsGroupChangePolicy: Always`), re-loosening PGDATA to group-rwx — and Postgres refuses to start (`data directory … has group or world access`; it requires `0700`).

**Nasty because first boot hides it**: `fsGroup` runs on the *empty* volume, then `initdb` creates PGDATA at `0700` afterwards — so it looks fine. The **second** boot re-loosens the now-populated dir and breaks.

Fixed image-side: the sidecar runs `chmod 700 $PGDATA` on every boot before Postgres starts (do the same on an old data dir before a migration `pg_dump`). Belt-and-braces on the pod securityContext: `fsGroupChangePolicy: OnRootMismatch` skips the re-walk once the volume root already matches. Supersedes the old single-container `~/.local/pgsql` form (frank#601).

## Agent GitHub auth: rotating App installation token — git helper + gh wrapper, not a PAT (2026-06-08)

The secure-agent-pod authenticates to GitHub with a short-lived **GitHub App
installation token** (App `derio-fr-automation`), not a personal access token.
ESO's `GithubAccessToken` ClusterGenerator mints a ~1 h token; an ExternalSecret
writes it to the `agent-github-token` Secret, mounted as a **live-updated volume**
at `/var/run/github/token` (kubelet refreshes the file as ESO rotates it; the App
private key never reaches the pod). This replaced the `clawdia-ai-assistant`
org-owner PAT, which was then demoted to member + revoked.

Two consumers, two shims — both read the mounted token file:

- **git** — the `~/.gitconfig` credential helper (baked at `/opt/gitconfig`,
  seeded to the PVC on first boot, upgraded in place by `02-credential-migrate`).
  username is `x-access-token` (the App-token convention; also accepted with a
  PAT). It MUST read the token with `$(cat "$t")`: **git runs credential helpers
  via `/bin/sh` = dash**, where the bash-only `$(< file)` read shortcut yields an
  EMPTY string → `password=` → GitHub rejects auth on PRIVATE repos with
  *"Invalid username or token. Password authentication is not supported for Git
  operations."* PUBLIC repos read with no auth and **mask** the bug — so a
  public-repo check is a false pass. **Always verify against a private repo.**

- **gh** — the `/usr/local/bin/gh` wrapper (ahead of the apt `/usr/bin/gh` in
  PATH) injects the current token per call:
  `if [ -r /var/run/github/token ]; then exec env GH_TOKEN="$(cat /var/run/github/token)" /usr/bin/gh "$@"; fi`.
  Needed because App tokens **rotate** (a long-lived process's captured env token
  goes stale) and gh otherwise falls back to a stale value or the revoked
  `~/.config/gh/hosts.yml` PAT → *"Bad credentials"* (the fr-bridge's GraphQL
  plan-discovery surfaced this). App tokens also lack **user-context**:
  `gh auth status` / `gh api user` report "invalid", but repo/issue/PR/GraphQL
  ops (what `fr apply` + the bridge need) work fine.

### Two traps that masked/broke this

1. **`gh auth setup-git` host override.** A past `gh auth setup-git` leaves
   `credential.https://github.com.helper = !/usr/bin/gh auth git-credential` on
   the PVC. Git makes the **host-specific** helper win for github.com (an empty
   `credential.https://github.com.helper=` line first RESETS the list), so the
   generic App-token helper is ignored and git asks gh for the password — getting
   gh's stored (revoked) token → 401. `02-credential-migrate` now re-seeds
   `/opt/gitconfig` (which has no host override) whenever it finds
   `gh auth git-credential` in the PVC gitconfig.
2. **Per-repo + per-org install coverage.** An installation token only covers
   the repos added to the App install, in that org. Repos not in the install 404
   ("Repository not found"); repos in another org aren't covered at all. The
   fr-bridge tracks repos across orgs, so each needs coverage (add to the install)
   or its own App/token — or drop it from the bridge's repo list.

### Recovery — live stopgap before the fixed image rolls

Durable fix is in `agent-images` (gitconfig `$(cat)`, the gh wrapper,
`02-credential-migrate` upgrades). To patch a running pod immediately
(`/usr/local/bin` is root-owned, so write the gh wrapper to `~/.local/bin`, which
is first in PATH):

```bash
kubectl -n secure-agent-pod exec -i deploy/secure-agent-pod -c kali -- bash -s <<'EOF'
git config --global --unset-all 'credential.https://github.com.helper' 2>/dev/null || true
git config --global credential.helper '!f() { for t in /var/run/github/token /run/s6/basedir/env/GITHUB_TOKEN; do [ -r "$t" ] || continue; echo username=x-access-token; printf "password=%s\n" "$(cat "$t")"; return; done; }; f'
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/gh" <<'WRAP'
#!/bin/sh
_tok="${GH_APP_TOKEN_FILE:-/var/run/github/token}"; _real="${GH_REAL_BIN:-/usr/bin/gh}"
if [ -r "$_tok" ]; then exec env GH_TOKEN="$(cat "$_tok")" "$_real" "$@"; fi
exec "$_real" "$@"
WRAP
chmod +x "$HOME/.local/bin/gh"
EOF
```

Verify against a PRIVATE repo (public ones false-pass):
`git ls-remote https://github.com/derio-net/willikins HEAD` and
`gh api graphql -f query='{repository(owner:"derio-net",name:"willikins"){name}}'`.

The same App pattern backs other CI on the cluster via per-app `GithubAccessToken`
generators (e.g. tekton mirror pipelines for a separate org), with the key in the
consuming namespace — see `storage-secrets-ssa.md` for the generator gotcha.

## agent-images bump PR body rendering (best-effort enrichment)

The agent-images bump PR body is rendered by `scripts/render_bump_body.py`, called from `agent-images-bump.yml`. It lists the upstream `agent-images` PR(s) in the `old…new` SHA range with a one-line summary each.

Enrichment is **best-effort** — any `gh api` failure (or a missing pre-bump pin) falls back to the legacy two-line body, so the bump PR always opens even when enrichment can't run. The "what changed" filter mirrors agent-images `build.yaml`'s `paths-ignore: docs/**` (docs-only upstream PRs trigger no rebuild, so they're excluded from the list — showing them would imply a rebuild that didn't happen).

Summary + title come from the **squash commit body** (GitHub copies the PR description there). A subject's `(#NN)` may reference an **issue**, not a PR — e.g. `8606edf` → issue #88, not PR #88 — so refs link to `.../issues/NN` (canonical; GitHub redirects to the PR when it is one) rather than hard-coding `/pull/NN`, which would 404 on an issue-numbered subject.

## `AGENT_IMAGES` allowlist — bump workflow image coverage

The bump workflow originally covered images via a **hardcoded per-file `sed` list**, which silently skipped any app pinning an agent-image not on it. `alert-agent`, `n8n-01`, and `hermes-agent-shell` all went stale this way — never auto-bumped since they were added, because nobody remembered to add them to the list.

Fixed by generalizing to an **`AGENT_IMAGES` allowlist looped over all of `apps/`** — every image rides the same agent-images SHA except `vk-remote` (its own short-tag build). A post-bump **"Verify coverage" step** fails the workflow loudly if any 40-hex `ghcr.io/derio-net/*` pin under `apps/` wasn't bumped to the new SHA (`blog` is frank-built, excepted).

Adding a new agent-image to the build matrix means adding its name to `AGENT_IMAGES` — `scripts/tests/test_agent_images_bump_coverage.py` guards the allowlist locally (frank#570).

## shell-inventory npm-global dist-tag guard → reinstall-every-boot → `ENOTEMPTY` deadlock on the PVC

**Incident 2026-06-06 → 2026-06-15 (ruflo-shell).** Telegram fired
`ruflo-shell: 1 install(s) failed on boot — npm i -g claude-flow@alpha` on
*every* pod restart for ~9 days before it was investigated.

### Two bugs, one symptom

The Layer-2 inventory reconciler (`/usr/local/lib/<shell>/install-inventory.sh`,
run by `cont-init.d/40-shell-inventory`) installs declared npm-global packages
and is meant to **skip ones already present at any version**. The guard was:

```bash
if npm ls -g "$pkg" --depth=0 >/dev/null 2>&1; then   # $pkg = "claude-flow@alpha"
```

**Bug A — the guard never matches a dist-tagged spec.** It passed the *full*
spec, including the `@alpha` dist-tag, to `npm ls`. `npm ls` can't resolve a
dist-tag locally, so it exits non-zero even when the package IS installed:

```
npm ls -g claude-flow@alpha   → exit 1   (guard fails → install attempted)
npm ls -g claude-flow         → exit 0
npm ls -g @openai/codex       → exit 0   (scoped NAME, not a version selector — skipped fine)
```

So `claude-flow` was the only package that re-ran `npm i -g` on every boot
(codex and the scoped `@anthropic-ai/...` entries skip correctly). This alone
silently auto-pulls a new alpha on every bounce — contradicting the inventory
ConfigMap's own comment that "pod bounces don't auto-pull new alphas."

**Bug B — the reinstall deadlocks on a stale npm retired dir.** npm replaces a
global package by renaming the old dir to a hidden *retired* path
`.{name}-{hash}`, installing the new one, then deleting the retired dir. **That
hash is deterministic per install path** — so the retired name is *stable*
across runs. An interrupted reinstall (pod killed mid-install) left
`.claude-flow-ufsFGjVA` behind, non-empty. Every later install then tried to
rename the live `claude-flow` onto that same already-occupied name →
`ENOTEMPTY: directory not empty, rename 'claude-flow' -> '.claude-flow-ufsFGjVA'`
→ abort. Permanent, because the mise node tree lives under
`/home/agent/.local/share/mise/...` = the **home PVC**, so the orphan survives
restarts (an image-baked node tree would reset every boot).

Diagnostic tell: the orphan and the failing rename target share the *same* hash
suffix. `npm ls -g claude-flow` (bare) exits 0 and looks healthy — the breakage
is only visible by listing the `node_modules` dir and seeing the `.claude-flow-*`
sibling, or by running the guard's exact tagged command.

### Recovery (live, wedged PVC)

```bash
# cd to repo root first (relative KUBECONFIG), then source .env
P=$(kubectl get pod -n ruflo-system -l app=ruflo -o name | head -1 | cut -d/ -f2)
D=/home/agent/.local/share/mise/installs/node/20.20.2/lib/node_modules
# Remove ONLY the stale retired dir (explicit name — never a wildcard, never the real `claude-flow`):
kubectl exec "$P" -c ruflo-shell -n ruflo-system -- sh -c "rm -rf $D/.claude-flow-<hash>"
# Re-run the reconcile and confirm failed=0:
kubectl exec "$P" -c ruflo-shell -n ruflo-system -- sh -lc '/usr/local/lib/ruflo-shell/install-inventory.sh' \
  | grep -E 'claude-flow|summary'
# Expect: ✓ npm i -g claude-flow@alpha  /  === summary: ... failed=0 ===  /  MOTD warning clears.
```

### Durable fix (agent-images#124)

Derive the bare package **name** before the presence check — strip a trailing
`@version`/`@tag`, preserving a leading `@scope` — and `npm ls -g "$name"`;
install still uses the full `$pkg`:

```bash
name="$pkg"
[[ "${pkg#@}" == *@* ]] && name="${pkg%@*}"
if npm ls -g "$name" --depth=0 >/dev/null 2>&1; then ...
```

`claude-flow@alpha`→`claude-flow`, `@openai/codex`→`@openai/codex`,
`@scope/pkg@1.2.3`→`@scope/pkg`. Applied to all 5 shell images (ruflo, hermes,
multi-agent, infra, paperclip — identical guard) with a bats regression in
`hermes-agent-shell/tests/test_install_inventory.bats`. Lands in the cluster on
the next ruflo image bump in `frank`.

## Driving claude inside a multi-agent-shell agent (alert-agent saga, 2026-06-18)

The agentic alert-agent's "DMs aren't answered" was **seven stacked root causes**, each
masking the next. The durable, reusable lessons (not the per-incident details):

- **Agent instructions must be a file the harness auto-loads — NOT `SKILL.md`.** claude Code
  auto-loads **`CLAUDE.md` only** (cwd + `~/.claude/CLAUDE.md`); it never reads a file named
  `SKILL.md`. codex/opencode/antigravity/pi read **`AGENTS.md`** (the agents.md standard);
  Copilot reads `.github/copilot-instructions.md`; **not** `GEMINI.md` (antigravity uses
  AGENTS.md). A deployment mounting agent instructions at `~/SKILL.md` loads them into NOTHING —
  on a free-text turn the model has no tools/boundary and fumbles (reaches for `kubectl`,
  times out). Provide a canonical **`AGENTS.md`** + a `CLAUDE.md`; multi-agent-shell's
  `cont-init.d/46-agent-instructions` fans `~/AGENTS.md` out to the per-harness filenames
  (idempotent, fail-open, never clobbers a real mounted file; `AGENT_INSTRUCTION_LINKS`-overridable).
- **The non-login s6 driver's PATH must track `$AGENT_HOME`.** `base/Dockerfile` hardcodes
  `PATH=/home/claude/.local/bin:…`; `agent-shell-base` overrode HOME/AGENT_HOME to `/home/agent`
  but (until #132) NOT PATH — so the agent-session driver (launches `claude` via tmux with the
  baked PATH, not a login shell, so the profile.d `~/.local/bin` shim doesn't apply) resolved the
  npm `/usr/bin/claude`, not the PV-native build → `Auto-update failed: no write permission to npm
  prefix` forever. agent-shell-base now re-sets `PATH=${AGENT_HOME}/.local/bin:…`.
- **Native claude install is memory-safe-curl, never `claude install`** (the latter buffers ~4 GiB
  → `exit 137` on a memory-capped pod). Baked at `cont-init.d/45-native-harnesses`
  (`install-native-harness.sh`, idempotent/fail-open). The native **auto-updater** uses the same
  ~4.2 GiB path → the agent container needs **≥8 Gi** (alert-agent raised 3→8, frank#575).
- **`claude --session-id <uuid>` REJECTS a session left "in use" by a HARD kill** (`Error: Session
  ID … is already in use`, exit 1) — a graceful SIGTERM (normal pod stop) releases it, an **OOM
  SIGKILL does not**. `claude --resume <uuid>` recovers the stuck session. The driver picks by
  transcript existence: glob `~/.claude/projects/*/<uuid>.jsonl` → exists ⇒ `--resume`, else
  `--session-id` (so `--resume`-on-missing never picker-hangs). The "in use" marker lives in the
  jsonl/store, not a lockfile, and survives the process.
- **claude's MOTD auth check / credential path is `~/.claude/.credentials.json`** (leading dot).
  A check for `credentials.json` (no dot) always reads "✗ not logged in" despite valid auth.
- **A thorough chat answer can take ~5 min** (claude sweeping every probe). Don't cap an
  interactive DM at 2 min: with threaded turns (per-session lock) a long turn doesn't block the
  consumer, so the bridge uses `DM_TIMEOUT_S=600`; pair with a SKILL "answer fast/focused, lead
  with the pre-computed facts" nudge so most answers finish in well under a minute.
