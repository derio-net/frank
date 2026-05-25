## Hop Cluster Gotchas

- Never `source .env` when working on Hop — it overrides KUBECONFIG to Frank. Use `source .env_hop` instead
- Talos control-plane taint must be removed for single-node cluster (`allowSchedulingOnControlPlanes: true` in Talos config)
- PodSecurity namespaces (`caddy-system`, `headscale-system`) must be labeled `pod-security.kubernetes.io/enforce: privileged` for hostPort/privileged pods
- Deployments using `hostPort` (e.g., Caddy on 80/443, Headscale STUN on 3478/UDP) must use `strategy: Recreate` — `RollingUpdate` deadlocks on a single-node cluster because the new pod can't bind ports while the old pod still holds them
- Headplane v0.5+ requires a `config.yaml` ConfigMap — env vars alone are insufficient
- Headscale `extra_records` in DNS config provides split-DNS for mesh-only services — add entries for any new mesh-only service
- `talosctl apply-config --config-patch` patches the base file, not the running config — all patches must be combined in one invocation
- Tailscale DaemonSet must run in kernel mode (`TS_USERSPACE=false`, `privileged: true`) for Caddy to see mesh source IPs
- Headplane v0.5.5 serves at `/admin/` base path (`basename="/admin/"`) — Caddy redirects all non-`/admin*` paths to `/admin/`
- Headplane requires `config_path` pointing to mounted Headscale config with `config_strict: true` — non-strict mode works but logs scary warnings and forfeits upstream support
- Headplane binds IPv4 only — `wget localhost:3000` fails (resolves to `::1`), use `wget 127.0.0.1:3000` to test
- Headplane API key must be injected via `HEADPLANE_HEADSCALE_API_KEY` env var from a Secret
- Blog deployment uses SHA-pinned image tags (`ghcr.io/derio-net/blog:<sha>`) — CI commits the tag update to `deployment.yaml`, ArgoCD syncs automatically. No manual `rollout restart` needed
- Falco: installing a binary at container runtime (`apk add` / `pip install` / `npm i -g`, etc.) writes it to the container's writable upper layer and trips the **Critical** rule "Drop and execute new binary in container" (`EXE_UPPER_LAYER`, MITRE TA0003) — which pages via Telegram. This is a *benign-true-positive*, not a Falco bug: bake the tool into a digest-pinned image (read-only base layer) rather than muting the rule. First hit: headscale-backup CronJob's `apk add sqlite` at 03:00 → switched to `alpine/sqlite` pinned by digest.
- Falco priority routing on Hop: floor is `notice`; only `Critical` reaches Telegram, everything `≥ notice` goes to VictoriaLogs (`192.168.55.225:9428`) via the Loki push protocol. To audit what's actually firing without paging: `priority:<level> | stats by (rule) count()` in LogsQL. "Contact K8S API Server From Container" (Notice, mostly ArgoCD reconcile) is the expected high-volume benign baseline.
