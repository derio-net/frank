# Frank Gotchas — Other in-cluster apps

Long-form companion to the **Other in-cluster apps** section in `agents/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

Apps with only one or two gotchas live here together (Sympozium, Zot, Gitea, n8n, VK, curlimages, Homepage). Apps with larger gotcha clusters get their own file (Authentik, Grafana, Tekton, Argo Rollouts, Paperclip/Ruflo).

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

## Homepage

### `subPath` ConfigMap mounts are frozen — config edits never reach the running pod

Homepage needs `services.yaml`, `settings.yaml`, and `bookmarks.yaml` to all land in the same `/app/config` directory, but each comes from a separate ConfigMap. The only way to merge multiple ConfigMaps into one directory is a `subPath` volume mount per file:

```yaml
volumeMounts:
  - name: config-services
    mountPath: /app/config/services.yaml
    subPath: services.yaml
```

**The trap:** the kubelet live-updates a ConfigMap mounted as a *whole directory* (the ~30–60s projection), but a ConfigMap mounted via **`subPath` is resolved once at pod creation and never updated again**. Homepage's own file-watcher hot-reload is therefore watching a file that can never change. A config-only edit (e.g. fixing a tile icon) produces a green pipeline that lies at every layer:

- ArgoCD shows the app `Synced` / `Healthy` ✅
- `kubectl get configmap -o yaml` shows the new value ✅
- …but the rendered tile still serves the old value, because the projected file *inside the pod* is stale.

The only place the staleness is visible is in-pod:

```bash
source .env
POD=$(kubectl get pods -n homepage -o name | head -1)
kubectl exec -n homepage $POD -- cat /app/config/services.yaml | grep -A1 GoatCounter
# confirm subPath is the mount style:
kubectl get pod -n homepage $(basename $POD) \
  -o jsonpath='{range .spec.containers[0].volumeMounts[*]}{.mountPath}{" subPath="}{.subPath}{"\n"}{end}'
```

First hit: **2026-05-26** — GoatCounter tile icon changed from `chart-bar` to a direct logo URL; ArgoCD synced the ConfigMap but the tile kept rendering `chart-bar` until the pod was restarted.

### Why not switch to a directory mount?

Tempting, but unsafe for Homepage. Its entrypoint `cp -n`'s default config files (`docker.yaml`, `kubernetes.yaml`, `custom.css`, `widgets.yaml`, …) into `/app/config` on boot. A read-only whole-directory ConfigMap mount makes those writes fail and can crash the container. `subPath` is the upstream-recommended pattern — keep it.

### The durable fix: Kustomize `configMapGenerator`

`apps/homepage/manifests/` is a Kustomize package (`kustomization.yaml` present → ArgoCD auto-detects Kustomize; the Application source path is unchanged). The three configs live as plain files under `files/` and are turned into ConfigMaps by `configMapGenerator`, which:

1. Appends a **content-hash suffix** to each ConfigMap name (`homepage-services-b49b7f26k6`).
2. **Rewrites the volume references** in `deployment.yaml` to the hashed names automatically (Kustomize's nameReference transformer). `subPath` is untouched — it still selects the `services.yaml` key inside the now-hash-named ConfigMap.

Any edit to `files/*.yaml` changes the hash → changes the ConfigMap name → changes the pod spec → ArgoCD rolls the pod. This is the declarative equivalent of Helm's `checksum/config` annotation, which can't exist in static YAML.

**`prune: true` is mandatory for this app.** Each config edit creates a new hash-named ConfigMap and orphans the previous one. With the repo-default `prune: false`, the orphan stays live but drops out of desired state, so ArgoCD shows the app `OutOfSync` forever. Enabling prune is safe here specifically — the app holds only a Deployment/Service/ConfigMaps, none of the SOPS Secrets or RWO PVCs that the repo-wide `prune: false` rule exists to protect.

To edit Homepage config: change `apps/homepage/manifests/files/<name>.yaml`, commit, push. The pod rolls on its own — no `kubectl` needed.

**Manual fallback** (e.g. if someone reverts to a non-generator ConfigMap, or a pod is otherwise stale):

```bash
source .env
kubectl rollout restart deployment/homepage -n homepage
kubectl rollout status deployment/homepage -n homepage --timeout=90s
```

## AWX `extra_settings` string values need inner Python quotes

**Symptom (2026-05-31, auto layer):** with Postgres healthy, `awx-web` CrashLooped:

```
SOCIAL_AUTH_OIDC_OIDC_ENDPOINT = https://auth.cluster.derio.net/application/o/awx/
                                       ^ SyntaxError: invalid syntax
unable to load app 0 (mountpoint='/') (callable not found or import error)
```

and the operator reconcile failed at `installer : Check for pending migrations`:

```
fatal: [localhost]: FAILED! => Failed to execute on pod awx-web-... :
  ... b'container not found ("awx-web")'
```

**Root cause:** the AWX operator writes each `spec.extra_settings` entry verbatim as the right-hand side of a Python assignment into the rendered settings ConfigMap (`awx-awx-configmap`): `{{ setting }} = {{ value }}`. A bare URL or word is not a valid Python literal, so Django/uwsgi fails to import the settings module → `awx-web` never starts. Confirm the rendered file:

```bash
kubectl -n awx get configmap awx-awx-configmap -o jsonpath='{.data}' | grep -oE 'SOCIAL_AUTH_OIDC[^\\]*'
# BAD:  SOCIAL_AUTH_OIDC_KEY = awx
# GOOD: SOCIAL_AUTH_OIDC_KEY = 'awx'
```

**Cascade:** the operator runs migrations by `kubectl exec`-ing `awx-manage` *inside* `awx-web`. With `awx-web` crashlooping, that exec fails, so the DB is never migrated, and the `wait-for-migrations` init containers in `awx-task`/`awx-web` loop forever (`Init:0/2`). One malformed setting → web crash + no migrations + stuck task. Postgres being healthy is a red herring here.

**Fix (AWX CR `apps/awx/manifests/awx.yaml`):** wrap string values in inner Python quotes — YAML-double-quoted wrapping a Python-single-quoted literal:

```yaml
extra_settings:
  - setting: SOCIAL_AUTH_OIDC_OIDC_ENDPOINT
    value: "'https://auth.cluster.derio.net/application/o/awx/'"
  - setting: SOCIAL_AUTH_OIDC_KEY
    value: "'awx'"
```

Numeric values (`value: "500"`) are fine bare because they are valid Python. After the CR syncs, the operator re-renders the ConfigMap, `awx-web` starts, migrations run, and `awx-task` reaches `4/4`.
