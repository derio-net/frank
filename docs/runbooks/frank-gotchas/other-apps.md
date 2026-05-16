# Frank Gotchas — Other in-cluster apps

Long-form companion to the **Other in-cluster apps** section in `agents/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

Apps with only one or two gotchas live here together (Sympozium, Zot, Gitea, n8n, VK, curlimages). Apps with larger gotcha clusters get their own file (Authentik, Grafana, Tekton, Argo Rollouts, Paperclip/Ruflo).

## Sympozium

- Helm chart is Git-sourced (not OCI) — chart isn't published to any registry.
- Service template doesn't support type/annotations — use a separate LB Service in `extras`.
- `image.tag` must be overridden (chart appVersion lags behind latest fix releases).

## Zot

- Helm chart v0.1.0 is too minimal — no support for `mountConfig`, `mountSecret`, `persistence`, or `externalSecrets`. Use v0.1.60+ for TLS, htpasswd auth, and persistent storage.
- htpasswd hash in `values.yaml` must be regenerated if `ZOT_PUSH_PASSWORD` changes in Infisical — the bcrypt hash and plaintext password are not kept in sync automatically.

## Gitea

- Default `webhook.ALLOWED_HOST_LIST` blocks outgoing webhooks to in-cluster services — add `*.svc.cluster.local` to allow delivery to Tekton EventListeners and other cluster-local endpoints.

## n8n

- Community Edition has no `user:create` CLI command — owner account must be created via the first-time setup wizard in the browser.
- Community Edition OIDC/SSO is enterprise-only — use Authentik forward-auth proxy for SSO.
- Requires `N8N_SECURE_COOKIE=false` when accessed over plain HTTP (without TLS termination); remove once TLS is in place.

## VK / VibeKanban

- Local mode binds to a random port by default — set `PORT=8081` and `HOST=0.0.0.0` env vars to fix the port and allow external access (default host is `127.0.0.1`).
- Tries to reach `api.vibekanban.com` for remote features — add to Cilium egress allowlist if needed, or leave blocked (local mode works without it).
- VK relay sidecar image tag must match a build that includes `/usr/local/bin/relay-server` — the binary was added to the Dockerfile after the initial vk-remote image. Using a pre-relay image tag causes CrashLoopBackOff (`no such file or directory`). Always verify the image contains the expected binary before deploying a sidecar with a different entrypoint.
- VK local server relay tunnel uses exponential backoff (1s → 30s max). If the relay-server sidecar is unavailable when the local server boots, the tunnel may not reconnect for up to 30s. If the sidecar was crash-looping for minutes, restart the secure-agent-pod to force immediate tunnel reconnection rather than waiting for backoff to cycle.
- VK SPAKE2 enrollment codes are one-time-use — the code is consumed on the first `/api/relay-auth/server/spake2/start` call, even if the full exchange fails (e.g., relay tunnel not connected). The error message `"Unauthorized. Please sign in again."` is misleading — it means the enrollment code was invalid/consumed, not a session expiry. Generate a fresh code via Settings → Relay Settings before each pairing attempt.

## curlimages/curl

- Image uses non-numeric user (`curl_user`) — Kubernetes `runAsNonRoot` can't verify non-numeric users are non-root. Add explicit `runAsUser: 100` (curl_user's UID).
