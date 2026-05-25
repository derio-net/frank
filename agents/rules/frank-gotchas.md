## Frank Cluster Gotchas (compact)

One-line reminders only. Each section header points at a per-topic file under `docs/runbooks/frank-gotchas/` for full prose, recovery commands, and dated incident notes — agents read those on demand. When adding a new gotcha: one-liner here, full body in the corresponding section file.

### ArgoCD — `docs/runbooks/frank-gotchas/argocd.md`
- Notifications: subscribe via `subscribe.<trigger>.<service-name>: ""` (the third dotted segment is the service name, not the type).
- Notifications: native `service.telegram` mis-routes positive chat IDs — use `service.webhook.telegram`.
- Notifications-cm is owned by the ArgoCD chart — put service/triggers/templates under `notifications.notifiers/.triggers/.templates` in `apps/argocd/values.yaml`; `notifications.secret.create: false`.
- Manual `kubectl patch application … --type=merge -p '{"operation":{"sync":...}}'` does NOT inherit `spec.syncPolicy.syncOptions` — pass `["ServerSideApply=true","RespectIgnoreDifferences=true"]` explicitly or large CMs blow the 256KB last-applied-config annotation.
- Out-of-bounds symlinks anywhere in the repo lock the entire GitOps loop into `ComparisonError` — check after symlink commits: `find . -type l -lname '*../../..*'`.
- Root App-of-Apps re-templates leaf Application specs on every sync; live spec patches (selfHeal off, branch override) are reverted within the sync window.

### Storage / Secrets / SSA — `docs/runbooks/frank-gotchas/storage-secrets-ssa.md`
- SOPS-encrypted secrets must NOT be ArgoCD-managed; apply out-of-band from `secrets/`.
- RWO PVC + RollingUpdate deadlocks; use `strategy: Recreate`. Switching strategy via Helm needs a one-time `kubectl patch` to clear the orphan `rollingUpdate:` block.
- ESO: empty `data: []` is rejected; delete the ExternalSecret if all keys are removed.
- `envFrom.secretRef` without `optional: true` blocks rolling updates when the Secret is missing.
- Always `ServerSideApply=true`; always `prune: false`; always `ignoreDifferences` on Secret `/data`.

### Tekton — `docs/runbooks/frank-gotchas/tekton.md`
- v1 Task uses `computeResources` not `resources` — schema validation silently fails the whole app.
- `$(tasks.status)` returns `"Completed"` (not `"Succeeded"`) when tasks are skipped via `when` — accept both.
- PVC workspaces mount as root — set `fsGroup` on `taskRunTemplate.podTemplate.securityContext`.
- `runAsUser: 65534` (nobody) → `HOME=/` (read-only); set `HOME=/tekton/home` env explicitly.
- Gitea sends `X-Gitea-Event` (not `X-GitHub-Event`) — use `cel` interceptor, not `github`.

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

### Grafana — `docs/runbooks/frank-gotchas/grafana.md`
- File-provisioned alerts/dashboards in `apps/grafana-alerting/manifests/` are read-only in UI; edit ConfigMap, push, restart pod (provisioning files are read at boot, not watched).
- 12.x SSE alert rules need 3-step A→B→C; classic-condition format fails with `sse.parseError`.
- VictoriaLogs alert rules must set `model.queryType: stats` (hits `/select/logsql/stats_query`, returns wide). Default `instant` hits `/select/logsql/query` which returns a long series of log lines, and SSE `reduce` rejects it with `input data must be a wide series but got type long`.
- `kube_pod_status_ready{condition="true"}` false-positives in batch namespaces (Tekton, Jobs); use `kube_deployment_status_replicas_unavailable` instead.
- Provisioning env-var coercion turns numbers into ints — use YAML block scalars to force string.
- "Cannot change provenance from 'api' to 'file'" → delete the API rows from sqlite first (scale down → DELETE → scale up).
- Helm chart regenerates admin password Secret on re-render — recover with `grafana cli admin reset-admin-password` inside the pod.
- Alertmanager dedup window is 4h after re-provisioning a contact point — restart pod to reset.
- Table panels with Prometheus instant queries need `"format": "table"` on targets; use `filterFieldsByName` transform.
- OIDC: secret key must be `GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET` for `envFromSecret`.
- VictoriaMetrics chart `genCA` regenerates webhook caBundle — `ignoreDifferences` on the validating webhook caBundle.
- `ALERTS{}` does NOT exist in VM for Grafana-managed alerts — use `alertlist` panel type.

### Networking — `docs/runbooks/frank-gotchas/networking.md`
- Cilium: `lbipam.cilium.io/ips` alone is NOT a sharing directive — separate Services need matching `lbipam.cilium.io/sharing-key`. Always check `kubectl get svc -A | grep pending` after deploying a chart that splits one service into multiple Services on a shared LB IP.
- Cilium 1.17 FQDN policies need DNS-proxy initialization on the node first; restart the agent if the LRU isn't ready (stale BPF rules also persist after CNP deletion — agent restart clears them).
- MixedProtocolLBService (TCP + UDP on one Service) works on Cilium 1.17 + K8s 1.35 — no feature gate needed.
- mosh: flags only in `--ssh="ssh ..."`; `user@host` positional; pin `--server="mosh-server new -p 60000:60015"` to match the Service's port range. Use the per-shell wrappers in `apps/*/client-setup/laptop/`.

### gpu-1 specifics — `docs/runbooks/frank-gotchas/gpu-1.md`
- `kubectl port-forward` flakes regularly with CNI-netns errors on gpu-1 pods only — use `kubectl get application -n argocd -o wide` for argocd-cli replacements; use `kubectl exec ... wget -qO-` for in-pod metrics.
- Pin GPU workloads with `nodeSelector: kubernetes.io/hostname: gpu-1` + defensive `nvidia.com/gpu:NoSchedule` toleration (insurance against driver re-validation re-asserting the taint).
- Ollama "system memory" errors mean container cgroup RAM (not VRAM) — `OLLAMA_KEEP_ALIVE` page cache pins the cgroup near `resources.limits.memory`.

### Agent shells — `docs/runbooks/frank-gotchas/agent-shells.md`
- `agent-shell-base` parameterizes user via `AGENT_USER`/`AGENT_HOME` (defaults `agent`/`/home/agent`); kali overrides to `claude`/`/home/claude` to preserve PV state. Don't hardcode `/home/claude` in new init scripts.
- s6-overlay v3 in non-root mode needs `S6_KEEP_ENV=1`, `S6_VERBOSITY=2`, `with-contenv` shebangs (`#!/command/with-contenv bash` — `/command/`, NOT `/usr/bin/`), and `/run` chown'd to AGENT_UID at image build time.
- `cont-init.d/30-authorized-keys` only fires at pod boot and COPIES (not symlinks) `/etc/ssh-keys/authorized_keys` — re-run by hand or restart pod after adding/rotating SOPS-managed keys.
- sshd scrubs container env on login — env-dependent commands launched via `ssh agent@host -- cmd` see no `FRANK_C2_*`/`INFISICAL_*`. Use `kubectl exec` or source from `/proc/1/environ`.
- `shareProcessNamespace: true` is incompatible with s6-overlay v3 (suexec must be PID 1) — use shared workspace volume + `kubectl exec -c <other>` for cross-container debugging.
- s6 crashloop bail (5 deaths in 60s) leaves service down silently — `s6-svc -u /run/service/<name>` after fixing the root cause.
- tmux-continuum auto-restore only fires when the tmux server starts fresh, not on `tmux source-file ~/.tmux.conf`.
- `/etc/skel/.tmux.conf` only seeds on first boot of a fresh PV — existing PVs need a manual `source-file /etc/agent/tmux-resurrect.conf` appended once.
- PVC mounts at `/home/claude` hide all image-baked files under that path — entrypoints/configs/templates live outside (e.g., `/opt/`) and seed PVC on first boot.
- secure-agent-kali's `⚠ Leftover npm global installation at /usr/bin/claude` warning is intentional — both the npm-i-g bootstrap binary and the PV-resident native installer coexist by design.
- Sidecars with `runAsUser` overriding the image default need explicit `HOME` env — the binary resolves HOME from `/etc/passwd` of the image-baked user.
- Supercronic auto-reloads on `~/.crontab` change — no restart needed.
- vk-local `limits.memory: 4Gi` is too tight in practice — `VK_MAX_CONCURRENT_EXECUTIONS=4` does NOT bound the cgroup once the bridge feeds 8+ cards (queued sessions retain memory; new images drift baseline). Keep at 8 Gi until the bridge slot count is bound below the executor cap AND a soak under busy load proves the floor.
- vk-issue-bridge's 30 s MCP timeout cascades to zombie execution_processes: bridge crash on timeout → vk-local request handler future drops → `Child::wait()` cancelled → setup/cleanup shell scripts exit but never reaped → DB rows stuck `status='running'` forever, UI shows workspaces stuck active with no output. Recovery: `kubectl exec -c vk-local -- kill -TERM 1` triggers vk-local-only restart whose startup orphan-cleanup marks the rows failed. Durable fix lives in the bridge code being migrated to `superpowers-for-vk`.
- secure-agent-kali Dockerfile pins the kali repo to `https://kali.download/kali` (official CDN), NOT the `http.kali.org` redirector — the redirector round-robins to community mirrors whose `pool/` lags their `Packages` index during fast rolling transitions (GCC-16 churn, 2026-05), so `dist-upgrade` 404s on debs the index promises (e.g. `gcc-16-base 16-20260322-1`). The build (`agent-images`) is non-deterministic with the redirector.
- The v2 `vk.bridge` emits its banner + `dry-run complete` to **stderr** (logging), not stdout — any smoke test / health check capturing `$(vk-bridge --dry-run)` must use `2>&1` or it asserts on an empty string. This silently broke the `agent-images` kali smoke test on every build after the 2026-05-19 v2-bridge cutover.

### Paperclip / Ruflo — `docs/runbooks/frank-gotchas/paperclip-ruflo.md`
- Paperclip's "Test environment" runs in the `paperclip` app container, NOT the `paperclip-shell` sidecar — agent-CLIs installed via the shell PVC are invisible. Wire through the shared `/paperclip` PVC: `npm install --prefix /paperclip/agent-bin <pkg>` from the shell, PATH-suffix on the paperclip container.
- `paperclip-data` PVC fills up from agent run histories + npm cache. Currently 10Gi — clear cache: `rm -rf /paperclip/.npm/_cacache`.
- ruvocal stores state in `/app/db/ruvocal.rvf.json` (RVF), NOT Postgres — `DATABASE_URL` is silently ignored at the pinned SHA. Mount a PVC at `/app/db`.
- ruvocal liveness should probe `/api/v2/feature-flags`, not `/` (SSR `/` reaches into LiteLLM/DB).
- LiteLLM-fronted apps need a LiteLLM virtual key for `OPENAI_API_KEY` — not the upstream provider key.
- LiteLLM-backed agents (`opencode_local` + `hermes_local`): opencode needs `litellm/<alias>` model shape; hermes uses bare `<alias>` (e.g. `qwen-think-14b`) — config.yaml's `model: ollama-cloud/<alias>` pins the default provider so the adapter's bare `-m <alias>` still routes through LiteLLM; `HERMES_HOME` must be a writable PVC path; do NOT set `provider` or `extraArgs` from the UI (whitelist no-op + schema-form split bug); `hermes_local` 2nd-heartbeat-onward fails by default (upstream session-ID truncation, derio-net/paperclip#1) — hire with `persistSession: false` if you need multi-wake. See `paperclip-ruflo.md#litellm-backed-agents`.
- ruvocal's server-side `isValidUrl` rejects `wasm://` URLs but the in-browser "RVAgent Local (WASM)" MCP advertises one; with autopilot ON + WASM-only MCP (chat-ui defaults), the SPA silently refuses to submit and the chat POST never reaches the server. Local fork in agent-images adds a `wasm:` allow-line.
- Company-import's GitHub fetch is unauthenticated upstream (`server/src/services/github-fetch.ts:ghFetch` injects no `Authorization`) — private repos fail at the COMPANY.md fetch. Use **Local zip** mode: `git archive --format=zip --prefix=<name>/ HEAD:<subdir> > <name>.zip`.
- Archive does NOT free `issue_prefix` (`companies_issue_prefix_idx` is plain UNIQUE, no partial-where on status) — only hard DELETE frees a prefix; re-imports under the same name collide.
- `DELETE /api/companies/:id` cascades incompletely on active companies — `companies.ts:remove()` order is wrong (`cost_events` after `heartbeat_runs`) and several newer tables (e.g. `issue_thread_interactions`) aren't in the cascade at all. Workaround: `scripts/paperclip-purge-fs.sh` + the retry-loop SQL DO block pattern in `paperclip-ruflo.md`.
- `createCompanyWithUniquePrefix` retry-on-collision is broken — `isIssuePrefixConflict()` doesn't unwrap `DrizzleQueryError`, so the loop bails on attempt 1. First attempt's derived prefix (first 3 alpha chars of `newCompanyName`) must be unique or you get a 500; rename at import time to dodge.
- Operator API calls from CLI need `Origin: $PAPERCLIP_PUBLIC_URL` header (CSRF guard `boardMutationGuard` rejects board mutations otherwise) and `%3D`-encoded trailing `=` in the better-auth session cookie value (curl `-b` and inline shell quoting both pass the raw `=` through, which fails signature verification).

### Omni — `docs/runbooks/frank-gotchas/omni.md`
- TLS cert is NOT renewed by the snap-installed certbot timer (config lives at `/opt/manual_install/certbot/config/`). Use the dedicated systemd unit in `omni/certbot/certbot.md`. Renewal hook MUST `docker restart omni` (no SIGHUP path on v1.5.0).

### Other in-cluster apps — `docs/runbooks/frank-gotchas/other-apps.md`
- Sympozium chart is Git-sourced (no OCI), service template doesn't take type/annotations (use extras LB), `image.tag` must be overridden.
- Zot Helm chart v0.1.0 too minimal — use v0.1.60+ for TLS/auth/persistence. htpasswd hash regenerates if `ZOT_PUSH_PASSWORD` rotates.
- Gitea `webhook.ALLOWED_HOST_LIST` blocks in-cluster delivery — add `*.svc.cluster.local`.
- n8n CE has no `user:create` CLI (browser wizard only), no SSO (use Authentik forward-auth), needs `N8N_SECURE_COOKIE=false` over plain HTTP.
- VK relay sidecar image must contain `/usr/local/bin/relay-server`. Local-mode binds random port — set `PORT=8081` and `HOST=0.0.0.0`. Egress to `api.vibekanban.com` for remote features.
- VK SPAKE2 enrollment codes are one-time-use; "Unauthorized. Please sign in again." actually means the code was consumed.
- VK relay tunnel exponential backoff (1s → 30s) — restart secure-agent-pod to force immediate reconnect after extended sidecar crashloops.
- `curlimages/curl` uses non-numeric user (`curl_user`) — set `runAsUser: 100` explicitly or `runAsNonRoot` rejects.

### Process / practice
- **A layer is not "Deployed" until its workflow has been triggered + observed end-to-end.** ArgoCD Synced/Healthy proves artifacts exist; not that they work. Especially load-bearing for canaries, cron, webhook handlers, gated promotions.
- **Never `vk apply` a path under `archived-plans/`.** It reopens the plan's already-closed phase-issues: vk projects an agentic phase as CLOSED only when it observes a *live merged PR* on the issue, so inline-executed / hand-closed phases can't satisfy the rule retroactively and apply flips their CLOSED issues back to OPEN. `vk apply --all` is safe — it walks only `plans/`, never `archived-plans/`. To close a lingering archived-plan issue, hand-close it (`gh issue close`); do NOT reconcile via vk. Durable fix tracked in `superpowers-for-vk#246`.

### Operational reference
- Telegram alerting bot `@agent_zero_cc_bot`; Infisical keys `FRANK_C2_TELEGRAM_BOT_TOKEN` + `FRANK_C2_TELEGRAM_CHAT_ID`. Grafana contact uid: `efi04e0201jb4f`.
- Longhorn default replicaCount: 3 (matches 3 control-plane nodes).
- Intel GPU Resource Driver uses a vendored chart with K8s 1.35 DRA patches.
