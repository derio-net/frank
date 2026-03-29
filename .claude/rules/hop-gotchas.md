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
