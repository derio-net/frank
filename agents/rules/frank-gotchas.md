## Frank Cluster Gotchas (compact)

One-line reminders only. Each section header points at a per-topic file under `docs/runbooks/frank-gotchas/` for full prose, recovery commands, and dated incident notes — agents read those on demand. When adding a new gotcha: one-liner here, full body in the corresponding section file.

### ArgoCD — `docs/runbooks/frank-gotchas/argocd.md`
- Notifications: subscribe via `subscribe.<trigger>.<service-name>: ""` (the third dotted segment is the service name, not the type).
- Notifications: native `service.telegram` mis-routes positive chat IDs — use `service.webhook.telegram`.
- Notifications-cm is owned by the ArgoCD chart — put service/triggers/templates under `notifications.notifiers/.triggers/.templates` in `apps/argocd/values.yaml`; `notifications.secret.create: false`.
- Manual `kubectl patch application … --type=merge -p '{"operation":{"sync":...}}'` does NOT inherit `spec.syncPolicy.syncOptions` — pass `["ServerSideApply=true","RespectIgnoreDifferences=true"]` explicitly or large CMs blow the 256KB last-applied-config annotation.
- Out-of-bounds symlinks anywhere in the repo lock the entire GitOps loop into `ComparisonError` — check after symlink commits: `find . -type l -lname '*../../..*'`.
- Root App-of-Apps re-templates leaf Application specs every sync, so live spec patches (selfHeal off, branch override) revert within the sync window — durable scale-to-0 needs suspending **root** selfHeal first, not just the leaf. Full recipe: `argocd.md`.
- The UI LoadBalancer (192.168.55.200) is plain HTTP — the Service maps 443→8080 *plaintext*, so `https://` gets a TLS reset. Use `http://192.168.55.200`.
- App-level health can stick at `Degraded` after a source-path change even when all resources are Synced/healthy (stale live-state cache) — cosmetic, but masks real health; needs a controller restart/resync to clear. Full prose: `argocd.md`.
- Switching a live Deployment `RollingUpdate`→`Recreate` via git fails the sync (orphan `rollingUpdate:` block on the live object) — needs a one-time `kubectl patch` to clear it first (same fix as the Helm variant in `storage-secrets-ssa.md`).
- Registering a **vCluster as an ArgoCD cluster target** panics the application-controller **cluster-wide** on cold cache build (`panic: assignment to entry in nil map` in kubectl v0.34.0 `PodRequestsAndLimits`→`populatePodInfo` on a Pod with LimitRange-defaulted resources; vClusters ship a default LimitRange) — argo-cd#26529 / k8s#136533, fixed only in ArgoCD 3.5 (client-go 1.36.1). Latent: fine while the cache builds incrementally, crashes on every controller **restart** (cold rebuild). Fix = a **cluster-scoped** `resource.exclusions` skipping Pod on the vCluster URL ONLY (NEVER global — a global Pod exclusion strips pod tree/health from all ~60 apps). Load the exclusion (restart controller) BEFORE re-registering. Recovery from a live crash: `kubectl delete secret cluster-<name> -n argocd` + delete the controller pod. Full recipe + re-registration sequence: `argocd.md`.

### Storage / Secrets / SSA — `docs/runbooks/frank-gotchas/storage-secrets-ssa.md`
- SOPS-encrypted secrets must NOT be ArgoCD-managed; apply out-of-band from `secrets/`.
- RWO PVC + RollingUpdate deadlocks; use `strategy: Recreate`. Switching strategy via Helm needs a one-time `kubectl patch` to clear the orphan `rollingUpdate:` block.
- ESO: empty `data: []` is rejected; delete the ExternalSecret if all keys are removed.
- ESO `GithubAccessToken` generator resolves its `auth.privateKey.secretRef` in the **consuming ExternalSecret's namespace** and IGNORES `secretRef.namespace` (even on a `ClusterGenerator`) — the key MUST live in the consumer's ns. A moved/fixed key needs a forced resync (`force-sync=$(date +%s)` annotation) to clear a cached `SecretSyncedError`. Full prose: `storage-secrets-ssa.md`.
- `envFrom.secretRef` without `optional: true` blocks rolling updates when the Secret is missing.
- AWX operator-managed Postgres on Longhorn CrashLoops on a fresh PVC (`mkdir …: Permission denied`) — set `postgres_data_volume_init: true` in the AWX CR (root init container chowns the volume) rather than relying on `fsGroup`.
- Always `ServerSideApply=true`; always `prune: false`; always `ignoreDifferences` on Secret `/data`.
- Charts that render CONFIG into a Secret (gitea → `gitea-inline-config`): a values-driven config change syncs the Secret but the pod does NOT auto-roll (live `checksum/config` annotation stays stale under SSA; app stays Synced/Healthy while serving OLD config) — `kubectl rollout restart deploy/<app>` after any config-only values change, then verify inside the pod. Seen: gitea `actions.ENABLED` (2026-07-20). Full prose: `storage-secrets-ssa.md`.
- Longhorn v1.11.0 instance-manager leaked anon Go heap (~0.9 GiB/day), silently wedging nodes (kubelet/CRI hang, no OOM-kill — recovery was a physical power-cycle, not `talosctl reboot`) — **RESOLVED** by chart bump to 1.11.2 (#467). Full incident: `storage-secrets-ssa.md`.
- Longhorn engine live-upgrade only moves REPLICAS to the new instance-manager — reattaching engines re-JOINS the old IM. Retire old IMs by scaling workloads to 0 and waiting for natural detach; **never force-delete a `VolumeAttachment`** (yanks a mounted ext4 mid-write). Full recipe: `storage-secrets-ssa.md`.
- `talosctl memory` rows: AVAILABLE=`$8`, CACHE=`$7`. Pi replica scheduling is disabled (manual-op); `layer-1-node-memory-headroom` (absolute <1GiB, not a ratio) is the early warning. Incident: `docs/investigations/2026-06-04--stor--raspi-1-memory-wedge-incident.md`.
- **Pods stuck `0/1 Error` (phase `Failed`) with IP `<none>` that never restart are graceful-node-shutdown TOMBSTONES, not a live failure** — check `status.reason=Terminated` / `message="Pod was terminated in response to imminent node shutdown"` and `finishedAt` (= the node's reboot time). The Deployment is fine (its ReplicaSet already spun a healthy replacement); k8s does NOT auto-GC shutdown-Failed pods (PodGC `terminated-pod-gc-threshold` default 12500). The pod's AGE is when the *Deployment* was created, not when it failed — so an old age is NOT evidence it predates a recent reboot. Cleanup: `kubectl delete pod <name>` (harmless). Seen as Longhorn `csi-attacher`/`csi-provisioner` after mini-1's 2026-07-11 reboot, but it's generic to any Deployment. Full prose: `storage-secrets-ssa.md`.

### Tekton — `docs/runbooks/frank-gotchas/tekton.md`
- v1 Task uses `computeResources` not `resources` — schema validation silently fails the whole app.
- `$(tasks.status)` returns `"Completed"` (not `"Succeeded"`) when tasks are skipped via `when` — accept both.
- PVC workspaces mount as root — set `fsGroup` on `taskRunTemplate.podTemplate.securityContext`.
- `runAsUser: 65534` (nobody) → `HOME=/` (read-only); set `HOME=/tekton/home` env explicitly.
- Gitea sends `X-Gitea-Event` (not `X-GitHub-Event`) — use `cel` interceptor, not `github`.
- Gitea Actions runner DinD needs `DOCKER_TLS_CERTDIR=""` + explicit `--host=tcp://0.0.0.0:2375` — unset, dind serves TLS on 2376 and every job hangs "Running" against 2375.
- act_runner registration is one-shot PVC state (`/data/.runner`) — rotating `STOA_GITEA_RUNNER_TOKEN` does NOT re-register; scale to 0, delete `/data/.runner`, scale up.

### Argo Rollouts — `docs/runbooks/frank-gotchas/argo-rollouts.md`
- Only `canary` / `blueGreen` strategies — stateful + RWO PVC apps stay as plain Deployments.
- `workloadRef.scaleDown` defaults to `never` — set `onsuccess` explicitly or both Rollout + chart Deployment serve traffic.
- `workloadRef` scales chart Deployment to 0 — add `ignoreDifferences` on `spec.replicas` (`group: apps`, `kind: Deployment`).
- `workloadRef` "leaks" to a healthy-looking Helm Deployment when reconcile aborts pre-workload-phase (missing AnalysisTemplate, missing traffic-router plugin, etc.) — the ONLY signal is the controller pod log; `kubectl get rollout` looks identical to a steady-state run.
- Prometheus provider panics on empty result vector → metric `phase: Error` → 10s-cadence retry → canary aborts in ~50s. Verify metric exists + has samples first.
- AnalysisTemplate error queries must catch 4xx not just 5xx (`status!~"2..|3.."`).
- `interval: 1m` only governs Successful/Failed measurements; `Error` retries at 10s (consecutiveErrorLimit default 4 → ~40-50s to abort).
- `successCondition`/`failureCondition` use `result[0]` syntax for scalar queries.
- `AnalysisTemplate` has no `inconclusiveCondition` field — NaN auto-treats as inconclusive; cap with `inconclusiveLimit`.
- LiteLLM Prometheus is Enterprise-only — OSS image emits no `litellm_*` metrics.

### Authentik — `docs/runbooks/frank-gotchas/authentik.md`
- Blueprints mount in WORKER pod via `blueprints.configMaps` — register new ConfigMaps there.
- Blueprints don't assign providers to embedded outpost — manual Django ORM step (see `frank-argocd.md`).
- Embedded outpost needs `AUTHENTIK_HOST` env or forward-auth redirects use `0.0.0.0:9000`.
- API uses Bearer token (not basic auth); 2026.x requires `invalidation_flow` + object-shaped `redirect_uris` + `signing_key` UUID.
- `global.env` applies to both server + worker (avoids duplication).
- Forward-auth (`authentik-forwardauth`) matches the request Host against each provider's `external_host` — an unregistered Host (e.g. a `.frank.derio.net` re-front) **404s with `x-powered-by: authentik`**, not a Traefik/backend 404. Fix = add the Host to the blueprint + outpost-assignment step, or drop the middleware for self-authing apps. Full prose: `authentik.md`.

### Grafana — `docs/runbooks/frank-gotchas/grafana.md`
- File-provisioned alerts/dashboards in `apps/grafana-alerting/manifests/` are read-only in UI; edit ConfigMap, push, restart pod (provisioning files are read at boot, not watched).
- 12.x SSE alert rules need 3-step A→B→C; classic-condition format fails with `sse.parseError`.
- VictoriaLogs alert rules must set `model.queryType: stats` (hits `/select/logsql/stats_query`, returns wide) — default `instant` returns long series and SSE `reduce` rejects it.
- `kube_pod_status_ready{condition="true"}` false-positives in batch namespaces (Tekton, Jobs); use `kube_deployment_status_replicas_unavailable` instead.
- Provisioning env-var coercion turns numbers into ints — use YAML block scalars to force string.
- "Cannot change provenance from 'api' to 'file'" → delete the API rows from sqlite first (scale down → DELETE → scale up).
- Helm chart regenerates admin password Secret on re-render — recover with `grafana cli admin reset-admin-password` inside the pod.
- Alertmanager dedup window is 4h after re-provisioning a contact point — restart pod to reset.
- Table panels with Prometheus instant queries need `"format": "table"` on targets; use `filterFieldsByName` transform.
- OIDC: secret key must be `GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET` for `envFromSecret`.
- VictoriaMetrics chart `genCA` regenerates webhook caBundle — `ignoreDifferences` on the validating webhook caBundle.
- `ALERTS{}` does NOT exist in VM for Grafana-managed alerts — use `alertlist` panel type.
- A `mute_time_intervals` mute leaves the alert `state: active` and the v2 `/alerts` API has no `mutedBy` field — verify a mute by the metric gap (dispatcher count rises, notification-latency count stays 0), not alert state. Full recipe: `grafana.md`.
- The Telegram contact point uses HTML `parse_mode` — a bare `<`/`>`/`&` in alert annotations makes Telegram reject with 400, and the rule fires+dispatches but **silently never delivers** (other receivers on the same alert are unaffected). Keep `<>&` out of `summary`/`runbook`. Full prose: `grafana.md`.
- GPU-time-shared feature-health rules (Layer 11/16) must probe end-to-end (blackbox `litellm_chat`/`comfyui_object_info`), not pod existence — `kube_pod_status_ready`/`replicas_unavailable` are both blind to scale-to-0. Per-layer rules route to Health Bridge only (no Telegram); the only pager is `gpu-node-both-down`. Full prose: `grafana.md`.

### Observability digest — `docs/runbooks/frank-gotchas/obs-digest.md`
- **RETIRED → `alert-agent`** (2026-06-16): the FastAPI `ai-alert-helper` is replaced by an autonomous `claude` agent on multi-agent-shell (no LiteLLM/Ollama circular dependency). Same Telegram bot + GoatCounter; deterministic logic survives as the `frank-facts` CLI. Old FastAPI-endpoint gotchas below are historical. Full prose: `obs-digest.md`.
- Falco events reach VictoriaLogs via falcosidekick→Loki-push with fields `source`/`priority`/`rule`/`k8s_ns_name` — NOT `kubernetes.namespace_name`. Query Falco with `source:syscall`.
- The daily digest uses a split window: traffic = prior calendar day, security = yesterday 00:00 → digest run time, so overnight Critical events aren't reported ~24h late.
- Surge detection counts Hop-edge Caddy requests (bots/scanners included), NOT GoatCounter pageviews — an edge surge with a flat GoatCounter means automated traffic, not a contradiction.
- Surge baseline is `median(7 hour-of-day samples) or 1` — on a quiet blog it's forced to 1, so any trickle reads as a huge ratio. `SURGE_ABS_FLOOR` (50) is the floor; `SURGE_VISITOR_FLOOR` (10) gates URGENT on real GoatCounter pageviews. Full prose: `obs-digest.md`.
- Frank's own blackbox uptime probe (~360/hr) is tagged `Frank-Blackbox-Probe` and excluded by `facts.edge_filter`/`facts.PROBE_UA_TOKEN` — keep those two in sync. Full prose: `obs-digest.md`.
- ai-alert-helper image builds via CI (`gh workflow run build-ai-alert-helper.yml`) — NOT manual docker; the workflow tag is hardcoded and must be bumped with the version.
- Surge notifications de-dup in-memory (safe: single replica/worker, `concurrencyPolicy: Forbid`) — edge-triggered + `SURGE_COOLDOWN_HOURS` (6h) floor. Narrative is evidence-only. Full prose: `obs-digest.md`.
- The Telegram analyst long-polls `getUpdates` — ONE consumer per bot token, so the helper Deployment must stay `replicas: 1` + `Recreate`. Verify the LLM loop without Telegram via `POST /ask?dry_run=true`. Full prose: `obs-digest.md`.
- **health-bridge: blindness ≠ death** (v0.4.0+) — synthetic `DatasourceError`/`NoData` cap at `degraded` with no bug filed. Heal closes bugs by feature-ref alone so a tracker recovering under a different alertname still closes. Stranding still possible if a fresh Grafana pod eats the `resolved`. Full prose: `obs-digest.md`.

### Networking — `docs/runbooks/frank-gotchas/networking.md`
- Cilium: `lbipam.cilium.io/ips` alone is NOT a sharing directive — separate Services need matching `lbipam.cilium.io/sharing-key`. Check `kubectl get svc -A | grep pending` after any chart split.
- Cilium 1.17 FQDN policies need DNS-proxy initialization on the node first; restart the agent if the LRU isn't ready.
- MixedProtocolLBService (TCP + UDP on one Service) works on Cilium 1.17 + K8s 1.35 — no feature gate needed.
- mosh: flags only in `--ssh="ssh ..."`; `user@host` positional; pin `--server="mosh-server new -p 60000:60015"` to match the Service's port range. Use the per-shell wrappers in `apps/*/client-setup/laptop/`.
- Caddy JSON access logs store the vhost in field `request.host`, NOT in `_msg` — filter `request.host:"blog.derio.net"`, scope edge queries with `kubernetes.host:hop-1`.
- A flapping physical NIC strips the node's IP off Cilium's direct-routing device → ALL pod traffic on that node dies at once (SSH-via-LB drops, `kubectl exec` still works). Diagnose via `talosctl dmesg | grep 'Link is'`; recovery is physical (reseat) — do NOT drain a hard-pinned GPU node. Covered by `layer-1-nic-link-flap` (carrier-change counter). Full incident: `networking.md`.
- **External-edge death → re-front `*.frank` on in-cluster Traefik**: when the edge fronting a domain dies, `*.frank.derio.net` resolves but serves Traefik's default cert (`ERR_CERT_AUTHORITY_INVALID`, HSTS-hard-blocked). Fix = per-name IngressRoute + wildcard cert via the existing DNS-01 resolver — but don't copy `authentik-forwardauth` (404s on the unregistered `.frank` host). Full playbook: `networking.md`.
- A static Talos interface with no `nameservers` falls back to Talos's built-in public DNS, which the homelab blocks → NTP never syncs → Talos gates `apid`/`kubelet` on time-sync → node pings but is dead. Fixed fleet-wide by the cluster-wide `102-cluster-nameservers` patch; a test guard fails any static-NIC patch shipped without it. Full prose: `networking.md`.

### gpu-1 specifics — `docs/runbooks/frank-gotchas/gpu-1.md`
- `kubectl port-forward` flakes with CNI-netns errors on gpu-1 pods only — use `kubectl get application -o wide` / `kubectl exec ... wget -qO-` as replacements.
- **enp3s0/r8169 link-flap is SUPPRESSED, not cured, by `pcie_aspm=off`** (frank#582) — flap rate dropped ~every 1–2min → ~1/6h, but the onboard Realtek NIC isn't trusted long-term. Durable path is the USB 2.5G adapter (`patches/phase04-gpu/404-…`), keeping `192.168.55.31`. Full prose: `gpu-1.md`.
- USB 2.5G adapter (r8152/RTL8156B) logs `Direct firmware load for rtl_nic/rtl8156b-2.fw failed` — link works on on-board fw, warning fixed by adding `siderolabs/realtek-firmware` to gpu-1's **existing** `402-gpu1-nvidia-extensions.yaml` (per-machine `ExtensionsConfiguration` OVERRIDES not merges — a second file drops nvidia+iscsi). Firmware = schematic change (not ConfigPatch/kernel-arg); `omnictl apply` rebuilds+reboots gpu-1 (operator-only). Manual op `gpu-gpu1-usb-25g-nic-firmware`. Full prose: `gpu-1.md`.
- Pin GPU workloads with `nodeSelector: kubernetes.io/hostname: gpu-1` + defensive `nvidia.com/gpu:NoSchedule` toleration.
- Ollama "system memory" errors mean container cgroup RAM (not VRAM) — `OLLAMA_KEEP_ALIVE` page cache pins the cgroup near `resources.limits.memory`.
- ComfyUI custom nodes on the `comfyui-custom-nodes` PVC seed **if-absent** — a Dockerfile node patch never reaches an already-seeded PVC, so pods stay Ready while a node `IMPORT FAILED`s. Probe `/object_info`, not pod existence. Fixed by version-gating the seed. Full prose: `gpu-1.md`.

### Agent shells — `docs/runbooks/frank-gotchas/agent-shells.md`
- `agent-shell-base` parameterizes user via `AGENT_USER`/`AGENT_HOME` (defaults `agent`/`/home/agent`); kali overrides to `claude`/`/home/claude` to preserve PV state. Don't hardcode `/home/claude` in new init scripts.
- s6-overlay v3 in non-root mode needs `S6_KEEP_ENV=1`, `S6_VERBOSITY=2`, `with-contenv` shebangs (`#!/command/with-contenv bash` — `/command/`, NOT `/usr/bin/`), and `/run` chown'd to AGENT_UID at image build time.
- `cont-init.d/30-authorized-keys` only fires at pod boot and COPIES (not symlinks) `/etc/ssh-keys/authorized_keys` — re-run by hand or restart pod after adding/rotating SOPS-managed keys.
- sshd scrubs container env on login — env-dependent commands launched via `ssh agent@host -- cmd` see no `FRANK_C2_*`/`INFISICAL_*`. Use `kubectl exec` or source from `/proc/1/environ`.
- BYOK shells (env-keyed CLIs like hermes) need a numbered `/etc/profile.d/` shim re-exporting keys from `/proc/1/environ` into login shells — number it BELOW the image's `50-…-motd.sh`. Verify with `ssh host 'bash -lc …'`, never `ssh host -- cmd` (skips profile.d).
- hermes ≥0.15 ignores `OPENAI_*` env for chat (provider `auto` → openrouter 401) — pin via config.yaml `model:` MAPPING; model-string prefixes do NOT pin the provider. config.yaml is PVC state (manual-op `orch-hermes-config-provider`).
- `gemma4:12b-64k`/`qwen3.6:35b-a3b-64k` are the per-model 64k escape hatch from litellm#12930 (server default stays 16384) — keep hermes config.yaml `context_length` overrides equal to live reality. Web pages go through `fetch-text <url>` via the terminal, not a function call. `tool_loop_guardrails.hard_stop_enabled: true` kills degenerate tool loops at ~5 iterations. Full prose: `agent-shells.md`.
- `shareProcessNamespace: true` is incompatible with s6-overlay v3 (suexec must be PID 1) — use shared workspace volume + `kubectl exec -c <other>` for cross-container debugging.
- s6 crashloop bail (5 deaths in 60s) leaves service down silently — `s6-svc -u /run/service/<name>` after fixing the root cause.
- tmux-continuum auto-restore only fires when the tmux server starts fresh, not on `tmux source-file ~/.tmux.conf`.
- `/etc/skel/.tmux.conf` only seeds on first boot of a fresh PV — existing PVs need a manual `source-file /etc/agent/tmux-resurrect.conf` appended once.
- PVC mounts at `/home/claude` hide all image-baked files under that path — entrypoints/configs/templates live outside (e.g., `/opt/`) and seed PVC on first boot.
- secure-agent-kali's `⚠ Leftover npm global installation at /usr/bin/claude` warning is intentional — both the npm-i-g bootstrap binary and the PV-resident native installer coexist by design.
- Sidecars with `runAsUser` overriding the image default need explicit `HOME` env — the binary resolves HOME from `/etc/passwd` of the image-baked user.
- Supercronic auto-reloads on `~/.crontab` change — no restart needed.
- `claude install` (and the native build's background auto-updater) buffers its ~245MB download ~17× in anon memory — peak ~4.2GiB group-OOMs any shell pod with a 4Gi limit, killing sshd and dropping ALL SSH sessions at once. Memory-safe install: curl the binary to a versioned path + symlink into `~/.local/bin` (full recipe in `agent-shells.md`).
- vk-local `limits.memory: 4Gi` is too tight in practice — `VK_MAX_CONCURRENT_EXECUTIONS=4` does NOT bound the cgroup once the bridge feeds 8+ cards. Keep at 8 Gi.
- The issue-bridge's 30 s MCP timeout cascades to zombie execution_processes (DB rows stuck `status='running'` forever). Recovery: `kubectl exec -c vk-local -- kill -TERM 1` (vk-local-only restart, orphan-cleanup marks rows failed). Durable fix lives in the bridge code (`fr_vk.bridge` in `super-fr`).
- secure-agent-kali Dockerfile pins the kali repo to `https://kali.download/kali`, NOT the `http.kali.org` redirector — the redirector's mirrors lag their `Packages` index during fast rolling transitions, 404ing `dist-upgrade`.
- The `fr_vk.bridge` daemon emits its banner + `dry-run complete` to **stderr**, not stdout — any smoke test capturing `$(fr-bridge --dry-run)` must use `2>&1` or it asserts on an empty string.
- hermes-agent-shell's Hindsight sidecar Postgres PGDATA gets re-loosened by pod-level `fsGroup` on every remount (first boot hides it, second boot breaks it) — fixed image-side with a boot-time `chmod 700 $PGDATA`. Full prose: `agent-shells.md`.
- hermes-agent-shell's Hermes venv is **PVC-resident**, seeded on first boot from a relocatable image seed (frank#496) — uid-1000-writable, so in-pod patches / `hermes update` PERSIST across restarts, version-gated by a `.seed-version` marker. Full prose: `agent-shells.md`.
- Agent GitHub auth = a rotating GitHub **App installation token** (ESO-minted), NOT a PAT — git uses the `~/.gitconfig` credential helper, gh uses the `/usr/local/bin/gh` wrapper. **Always verify auth against a PRIVATE repo** — public repos read with no token and mask auth failures.
- The git credential helper MUST read the token with `$(cat "$f")`, not the bash-only `$(< file)` — git runs helpers under `/bin/sh`=dash, where `$(< )` yields an EMPTY password.
- `gh` needs the wrapper: App tokens rotate (gh falls back to stale/revoked stores → "Bad credentials") and lack user-context. A leftover `gh auth setup-git` host-helper silently overrides the generic helper — `02-credential-migrate` strips it.
- App install is **per-repo + per-org** — the token 404s on repos not added to the install. Full prose + the live-patch stopgap: `agent-shells.md`.
- The agent-images bump PR body (`scripts/render_bump_body.py`) is best-effort enrichment (falls back to a legacy two-line body on any `gh api` failure) and links `(#NN)` refs as `.../issues/NN` (a squash-commit subject number may be an issue, not a PR). Full prose: `agent-shells.md`.
- The bump workflow's image coverage moved from a hardcoded per-file `sed` list (which silently skipped alert-agent/n8n-01/hermes-agent-shell) to an `AGENT_IMAGES` allowlist over all of `apps/`, with a post-bump coverage-verify step. Full prose: `agent-shells.md`.
- The shell-inventory reconciler's npm-global guard checked `npm ls -g "<pkg>"` with the full dist-tagged spec, which never resolves locally — reinstalling every boot and eventually deadlocking on a stale retired dir (`ENOTEMPTY`). Fixed by checking the bare package name. Full prose + recovery: `agent-shells.md`.
- **Agent instructions must be a file the harness auto-loads — `CLAUDE.md`/`AGENTS.md`, NOT `SKILL.md`** (loaded by nothing). Also: the non-login s6 driver's PATH must track `$AGENT_HOME`; native install is memory-safe curl, never `claude install`; `claude --session-id <uuid>` rejects a HARD-killed session (`--resume` recovers it); interactive DM turns need `DM_TIMEOUT_S=600`. Full prose + the alert-agent saga: `agent-shells.md`.

### Paperclip / Ruflo — `docs/runbooks/frank-gotchas/paperclip-ruflo.md`
- Image bumps (monthly upstream-watcher PR) auto-run Drizzle migrations on boot — verify before merging (diff migrations across the SHA range, flag unguarded `DROP`/`ALTER`) and snapshot the **Postgres** PVC, not `paperclip-data`. Full recipe in `paperclip-ruflo.md`.
- Paperclip's "Test environment" runs in the `paperclip` app container, NOT the `paperclip-shell` sidecar — wire tools through the shared `/paperclip` PVC.
- `paperclip-data` PVC fills up from agent run histories + npm cache — clear via `rm -rf /paperclip/.npm/_cacache`.
- ruvocal stores state in `/app/db/ruvocal.rvf.json` (RVF), NOT Postgres — `DATABASE_URL` is silently ignored at the pinned SHA. Mount a PVC at `/app/db`.
- ruvocal's `RvfGridFSBucket` is an **incomplete GridFS shim** — file upload/download/copy-on-fork all 500. Fixed by a real objectMode `Writable`/`Readable.from` shim, zero caller patches (frank #464, upstreamed ruvnet/ruflo#2293).
- ruvocal liveness should probe `/api/v2/feature-flags`, not `/` (SSR `/` reaches into LiteLLM/DB).
- LiteLLM-fronted apps need a LiteLLM virtual key for `OPENAI_API_KEY` — not the upstream provider key.
- LiteLLM-backed agents (`opencode_local`/`hermes_local`): opencode needs `litellm/<alias>`, hermes uses a bare `<alias>` pinned via config.yaml's default provider; `HERMES_HOME` must be a writable PVC path; `hermes_local` 2nd-heartbeat-onward fails by default (upstream session-ID truncation) — hire with `persistSession: false` for multi-wake. See `paperclip-ruflo.md#litellm-backed-agents`.
- claude-flow v3 (`ruflo v3.10.x`) has NO `orchestrate`/`hive.yaml` — `swarm`/`hive-mind` build coordination state only; workers are Claude Code processes needing an authenticated `claude` on the shell PVC. Full prose: `paperclip-ruflo.md`.
- ruvocal's server-side `isValidUrl` rejects `wasm://` URLs but the in-browser "RVAgent Local (WASM)" MCP advertises one — with autopilot ON the chat POST silently never reaches the server. Local fork adds a `wasm:` allow-line.
- ruvocal MCP tools only load for a model declaring per-model `supportsTools`/`forceTools` — else `runMcpFlow` skips before the `wasm://` guard even runs. No Frank model sets it, so a clean `rejected.*wasm` grep is vacuous.
- Company-import's GitHub fetch is unauthenticated upstream — private repos fail. Use **Local zip** mode: `git archive --format=zip --prefix=<name>/ HEAD:<subdir> > <name>.zip`.
- Archive does NOT free `issue_prefix` (plain UNIQUE index) — only hard DELETE frees a prefix.
- `DELETE /api/companies/:id` cascades incompletely on active companies (wrong table order, missing newer tables). Workaround: `scripts/paperclip-purge-fs.sh` + the retry-loop SQL pattern in `paperclip-ruflo.md`.
- `createCompanyWithUniquePrefix` retry-on-collision is broken (`isIssuePrefixConflict()` doesn't unwrap the Drizzle error) — first attempt's derived prefix must be unique or you get a 500. Fix believed shipped upstream (v2026.525.0 / #6423), NOT yet live-verified.
- Operator API calls from CLI need `Origin: $PAPERCLIP_PUBLIC_URL` (CSRF guard) and `%3D`-encoded trailing `=` in the better-auth session cookie (curl `-b` passes the raw `=` through, failing signature verification).

### Omni — `docs/runbooks/frank-gotchas/omni.md`
- TLS cert is NOT renewed by the snap-installed certbot timer (config lives at `/opt/manual_install/certbot/config/`) — use the dedicated systemd unit in `omni/certbot/certbot.md`. Renewal hook MUST `docker restart omni` (no SIGHUP path on v1.5.0).
- The `omni-cert-renew` unit is the ONLY thing renewing the cert, and a broken renewer **does NOT page** — it silently ages to expiry. Check `systemctl is-failed omni-cert-renew.service` periodically; restore from canonical + `certbot renew --dry-run`. Full prose: `omni.md`.
- **Wedges SILENTLY on a cold-boot clock-jump** — the `omni` container keeps serving CACHED reads (UI/omnictl look green) but its reconcile runtime STOPS; a just-applied KernelArgs/extension never reboots its node. **Recovery: `docker restart omni`** (rotates Talos API certs — refresh the stored talosconfig after). Full prose: `omni.md`.
- **DIED (hardware) ≠ wedged** — the Pi was a 3-role SPOF (Omni + the Docker-Traefik `.frank` edge + its cert-minter). On death the cluster keeps running but kubectl/talosctl access is lost (no non-Omni credential) — ArgoCD git→sync is the only apply path. Omni death does NOT page (no alert rule). Full prose: `omni.md`.
- The `fr-isolation` `cluster-admin` devcontainer authenticates with an **Omni service-account kubeconfig** (1-yr TTL) — a minted token that **expires SILENTLY**; re-minting is the only renewal. Verify a suspect token OFFLINE (decode the JWT `exp`). The `~/.config/fr/secrets/` host store MUST be `0600`/`0700`. Full recipe: `omni.md`.

### Other in-cluster apps — `docs/runbooks/frank-gotchas/other-apps.md`
- LiteLLM `ollama/` prefix = PROMPT-based function calling — with `stream: true` + `tools` the scaffolding JSON leaks into `content` and `tool_calls` is never populated. Use `ollama_chat/` (native tool calling, stream-safe).
- LiteLLM CANNOT pass per-request `num_ctx` to `ollama_chat` (litellm#12930, closed not-planned) — set `OLLAMA_CONTEXT_LENGTH` server-wide and keep client-side trim budgets equal.
- `gemma-12b` = `gemma4:12b` since 2026-06-05 — Gemma 4 is a THINKING model: reasoning tokens consume `max_tokens` before `content`. Fix: `"think": false` fully disables it through ollama_chat.
- hermes resolves a custom LiteLLM alias's context window to a **256K default fallback** when every probe fails — set `context_length` in config.yaml or the compressor engages 8× past the real 16384 boundary, poisoning the whole session ("session amnesia"). Full prose: `other-apps.md`.
- hermes hard-requires a **≥64k context window** (its preamble alone is ~15k tokens) — a derived-tag `num_ctx` silently clamps to the model's trained ceiling. `qwen36-a3b-64k` passed the hermes agentic gate (2026-06-06, 4/4 probes); `gemma4-12B` failed it (degenerate tool loops, confabulation). Full prose: `agent-shells.md`.
- Sympozium chart is Git-sourced (no OCI), service template doesn't take type/annotations (use extras LB), `image.tag` must be overridden.
- Sympozium PersonaPack per-persona `model` applies only at SympoziumInstance CREATION — edits never propagate to existing instances; merge to git first, then delete the SympoziumInstances to recreate.
- Sympozium AgentRun: `spec.sessionKey` is required (use `""`); terminal success phase is `Succeeded`, NOT `Completed`.
- Zot Helm chart v0.1.0 too minimal — use v0.1.60+ for TLS/auth/persistence. htpasswd hash regenerates if `ZOT_PUSH_PASSWORD` rotates.
- Gitea `webhook.ALLOWED_HOST_LIST` blocks in-cluster delivery — add `*.svc.cluster.local`.
- n8n CE has no `user:create` CLI (browser wizard only), no SSO (use Authentik forward-auth), needs `N8N_SECURE_COOKIE=false` over plain HTTP.
- VK relay sidecar image must contain `/usr/local/bin/relay-server`. Local-mode binds random port — set `PORT=8081` and `HOST=0.0.0.0`.
- VK SPAKE2 enrollment codes are one-time-use; "Unauthorized. Please sign in again." actually means the code was consumed.
- VK relay tunnel exponential backoff (1s → 30s) — restart secure-agent-pod to force immediate reconnect after extended sidecar crashloops.
- `curlimages/curl` uses non-numeric user (`curl_user`) — set `runAsUser: 100` explicitly or `runAsNonRoot` rejects.
- ComfyUI model folders are node-specific `folder_paths` registrations — a file in the wrong folder (e.g. `latent_upscale_models/` vs `upscale_models/`) leaves the node enum empty with no error; new model files usually need a `kubectl rollout restart deploy/comfyui`. Full prose: `other-apps.md`.
- Homepage mounts its `{services,settings,bookmarks}.yaml` via `subPath` — kubelet NEVER live-updates subPath ConfigMap mounts. Manifests use Kustomize `configMapGenerator` (hash-suffixed) so an edit rolls the pod automatically; needs `prune: true`. Manual fallback: `kubectl rollout restart deployment/homepage`.
- AWX CR `extra_settings.value` is injected verbatim as the RHS of a Python assignment — string values MUST carry inner Python quotes (`value: "'https://...'"`) or a bare URL is a SyntaxError that CrashLoops `awx-web` and stalls migrations forever.
- AWX settings PATCH **silently drops keys outside the addressed category** — `SOCIAL_AUTH_OIDC_*` live in category `oidc`, NOT `authentication`; a wrong-category write looks like success but OIDC never registers.
- `ansible_ssh_common_args` is prohibited in AWX ad-hoc `extra_vars` (security denylist → 400) — set host-key opts as an inventory variable instead. Host onboarding is codified in the `awx-onboard-hosts` skill.

### Process / practice
- **A layer is not "Deployed" until its workflow has been triggered + observed end-to-end.** ArgoCD Synced/Healthy proves artifacts exist; not that they work. Especially load-bearing for canaries, cron, webhook handlers, gated promotions.
- **Tag-driven releases: verify the tag tree contains the new code BEFORE pushing** (`git grep <new-symbol> <tag>` non-empty) — health-bridge v0.3.0 was tagged from a stale local main (pre-merge SHA), so GHCR built the OLD code under the new version; nothing in the tag→build→bump chain catches it (workflow green, ArgoCD Synced, pod Running). Caught only at deploy verification; superseded by v0.3.1 at the merge commit (re-pointing a tag is worse: `IfNotPresent` keeps the stale cached image).
- **Never `fr apply` a path under `archived-plans/`.** It reopens the plan's already-closed phase-issues: fr projects an agentic phase as CLOSED only when it observes a *live merged PR* on the issue, so inline-executed / hand-closed phases can't satisfy the rule retroactively and apply flips their CLOSED issues back to OPEN. `fr apply --all` is safe — it walks only `plans/`, never `archived-plans/`. To close a lingering archived-plan issue, hand-close it (`gh issue close`); do NOT reconcile via fr. Durable fix tracked in `super-fr#246`.
- **A just-merged agentic phase's Issue can be *transiently* reopened by `fr apply` — even for an active `plans/` entry.** `fr.render._phase_complete` reads the merged-PR signal LIVE via `gh.list_linked_prs` and *ignores* the cached `completion.observed_prs` field; GitHub's cross-reference index lags a merge by a few minutes. An apply firing inside that window sees "no merged PR yet → agentic phase incomplete → OPEN" and reverts the close (re-adds `fr:ready`, reopens). Trigger is a close (manual `gh issue close`, or a PR `Closes #N` auto-close) colliding with the post-merge propagation window. **This is a race, not the deterministic archived-plan projection bug above** — the YAML is fine. **Recovery: re-run `fr apply --yes` once the merge has indexed (a few min later) — idempotent, heals the close; a follow-up dry-run apply is then a clean no-op.** Durable mitigation (super-fr#246): have apply trust cached `completion.observed_prs` as a fallback when the live query returns empty (the cache field already exists — apply just doesn't read it). Incident: #424 (Phase 3, awx-deployment) reopened 2026-06-01 ~2 min after PR #429 merged; re-applied closed.

### Operational reference
- Telegram alerting bot `@agent_zero_cc_bot`; Infisical keys `FRANK_C2_TELEGRAM_BOT_TOKEN` + `FRANK_C2_TELEGRAM_CHAT_ID`. Grafana contact uid: `efi04e0201jb4f`.
- Longhorn default replicaCount: 3 (matches 3 control-plane nodes).
- Intel GPU Resource Driver uses a vendored chart with K8s 1.35 DRA patches.
