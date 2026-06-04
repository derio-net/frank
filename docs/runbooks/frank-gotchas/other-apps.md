# Frank Gotchas — Other in-cluster apps

Long-form companion to the **Other in-cluster apps** section in `agents/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

Apps with only one or two gotchas live here together (Sympozium, Zot, Gitea, n8n, VK, curlimages, Homepage). Apps with larger gotcha clusters get their own file (Authentik, Grafana, Tekton, Argo Rollouts, Paperclip/Ruflo).

## Sympozium

- Helm chart is Git-sourced (not OCI) — chart isn't published to any registry.
- Service template doesn't support type/annotations — use a separate LB Service in `extras`.
- `image.tag` must be overridden (chart appVersion lags behind latest fix releases).

### PersonaPack `model` only applies at SympoziumInstance creation

The PersonaPack controller stamps each persona's `model` into its SympoziumInstance **when the instance is created** — editing the PersonaPack afterwards does NOT reconcile existing instances. Two traps stack on top of each other:

1. **Live edits get healed away.** Patching the PersonaPack on the cluster looks like it worked, but ArgoCD self-heal reverts it to git within the sync window. Merge the manifest change to `main` first.
2. **Even a synced PersonaPack changes nothing.** After the merge, existing SympoziumInstances still carry the old model. Delete them and let the controller recreate:

```bash
kubectl delete sympoziuminstances -n sympozium-system --all
# controller recreates from PersonaPacks within ~30s; verify:
kubectl get sympoziuminstances -n sympozium-system -o custom-columns=NAME:.metadata.name,MODEL:.spec.model
```

**Incident (2026-06-04, PR #448):** the LiteLLM alias `qwen3.5` was removed from `apps/litellm/values.yaml`; every scheduled AgentRun failed for ~2 weeks (350 failures) because all SympoziumInstances were created with the dead alias. Fix: `sed` the three PersonaPack manifests to `qwen36-a3b-nothin` (the no-think variant — right choice for agent orchestration), merge, sync, then delete all 8 instances. Validated with a manual AgentRun (`Succeeded` in 273s) and the next hourly scheduled run.

### AgentRun quirks

- `spec.sessionKey` is **required** by schema validation even when unused — set `sessionKey: ""` or creation is rejected.
- Terminal success phase is **`Succeeded`**, not `Completed` — a poll loop matching `Completed` never exits.
- The web UI's Runs page defaults to the `default` namespace (empty) — real runs live in `sympozium-system`; the namespace switcher is a custom dropdown, not a `<select>`.
- UI login is token-only (`#token` input); token lives in the `sympozium-ui-token` secret in `sympozium-system`.

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

## AWX (Ansible automation controller)

Surfaced during the `auto` layer deploy (building post #32 / operating post #27). The
CrashLoop gotchas (`extra_settings` Python quoting, `postgres_data_volume_init`) are
one-liners in `frank-gotchas.md`. The two that bite at *OIDC + job* time:

### OIDC secret — right category, or a silent no-op

AWX groups settings into categories, and a PATCH to a category **silently discards keys
that don't belong to it** — `HTTP 200`, body echoes the category, your key is just gone.
The generic-OIDC settings live in their own category, slug **`oidc`**
(`/api/v2/settings/oidc/`), NOT `authentication`. `SOCIAL_AUTH_OIDC_KEY` / `_ENDPOINT`
appear in the aggregate `/settings/all/` view — that's the trap; they belong to `oidc`,
not whatever `all/` lists them beside.

AWX only registers the OIDC backend (and renders the SSO button) once KEY + SECRET +
ENDPOINT are all set, so a secret PATCHed to the wrong category = no backend,
`/api/v2/auth/` stays `{}`, no button — and no error telling you why.

The provider's `client_secret` is **auto-generated by Authentik** for a confidential
provider — don't mint a new one; read Authentik's and copy it in:

```bash
ADMIN_PW=$(kubectl -n awx get secret awx-admin-password -o jsonpath='{.data.password}' | base64 -d)
SECRET=$(kubectl exec -n authentik deploy/authentik-worker -- python -c '
import os; os.environ.setdefault("DJANGO_SETTINGS_MODULE","authentik.root.settings")
import django; django.setup()
from authentik.providers.oauth2.models import OAuth2Provider
print(OAuth2Provider.objects.get(client_id="awx").client_secret)')
kubectl -n awx exec deploy/awx-web -c awx-web -- curl -s -u "admin:$ADMIN_PW" \
  -X PATCH http://localhost:8052/api/v2/settings/oidc/ \
  -H 'Content-Type: application/json' -d "{\"SOCIAL_AUTH_OIDC_SECRET\": \"$SECRET\"}"
# verify: a successful write reads back as $encrypted$; /api/v2/auth/ then lists "oidc"
```

### Ad-hoc commands can't carry `ansible_ssh_common_args`

It's on AWX's **ad-hoc `extra_vars` denylist** — a launch with it in `extra_vars` returns
`400` ("...are prohibited from use in ad hoc commands"). Put first-contact host-key
handling on the **inventory** as a variable instead:

```yaml
ansible_ssh_common_args: "-o StrictHostKeyChecking=accept-new"
```

Job Templates inherit inventory vars, so this covers ad-hoc and JT runs alike. The full
host-onboarding flow (dedicated key → `ssh-copy-id` → org/credential/inventory → ping
proof → Gitea Project + Job Template) is the **`awx-onboard-hosts`** skill.

### Reaching cross-VLAN / non-Talos hosts

AWX runs jobs in execution-environment pods on the cluster network, so a target's
reachability == a *pod's* reachability, not your laptop's. Preflight before wiring an
inventory (e.g. cluster `192.168.55.x` → host `192.168.10.x`):

```bash
kubectl -n awx exec deploy/awx-task -c awx-task -- \
  python3 -c "import socket;s=socket.socket();s.settimeout(4);s.connect(('<ip>',22));print('OPEN')"
```

## LiteLLM `ollama/` vs `ollama_chat/` — streaming + tools leaks scaffold JSON into content

**Symptom (2026-06-04, hermes-agent-shell):** every conversational reply from a
local model rendered as a fake tool call in the client —
`{"name": "text_to_speech", "arguments": {...}}`, `{"name": "todo", ...}` —
instead of plain text. Plain chat without tools was fine; the same request
non-streamed returned a *correct* native `tool_calls` response.

**Root cause:** LiteLLM's `ollama/` provider implements function calling by
prompt injection — it renders the `tools` array into the prompt, instructs the
model to answer with `{"name", "arguments"}` JSON, and re-parses that JSON into
`tool_calls` on the way back. The re-parse needs the complete response, so it
only happens non-streamed. Any streaming client that sends `tools`
(hermes does — `chat_completion_stream_request`) receives the raw scaffold
JSON as `content` with zero `tool_calls` deltas. Models then also imitate the
pattern for ordinary replies, wrapping greetings in whatever tool looks
plausible (tts, todo, image_generate — disabling individual tools is
whack-a-mole, the envelope just moves).

**Probes (run from any pod with the LiteLLM key):**

- non-stream + tools → `content: None`, proper `tool_calls` — looks healthy
- `stream: true` + tools → `content: '{"name": "get_weather", ...}'`, `tool_call deltas: 0` — the bug
- Ollama native `/api/chat` direct with `stream: true` + tools → empty content,
  proper `message.tool_calls` — proving the fix

**Fix:** use the `ollama_chat/` prefix in `apps/litellm/values.yaml`
`model_list` (LiteLLM's own recommendation for chat models). It targets
Ollama's native `/api/chat` tool-calling, which is stream-safe.
`extra_body: {think: false}` (qwen36-a3b-nothin) is a native `/api/chat`
parameter and passes through unchanged. Flipped for all 7 local aliases on
2026-06-04 (hermes-agent-shell deviation follow-up).

**Beware in tests:** a `curl` verification without `"stream": true` CANNOT
catch this class of bug — always probe the streaming path when validating
tool-calling through LiteLLM.

## LiteLLM cannot set Ollama num_ctx per request (2026-06-05)

Verified live against litellm 1.81.13 + ollama_chat: `{"options":
{"num_ctx": N}}`, top-level `"num_ctx"`, and `"extra_body"` variants are ALL
silently dropped — the runner stays at its default window and truncates long
prompts with only a runner-side log line (`truncating input prompt`).
Upstream: BerriAI/litellm#12930, closed not-planned.

The only effective, declarative control is server-side:
`OLLAMA_CONTEXT_LENGTH` env on the ollama Deployment
(`apps/ollama/values.yaml`, currently 16384). It is the default for EVERY
model load on gpu-1 — KV-cache VRAM scales with it, so check `ollama ps`
CPU/GPU split after changing (mistral-small-24b: 16 GB @4096 → 18 GB @16384).
Clients that budget their prompts (ai-alert-helper `ANALYST_NUM_CTX`) must
keep their budget equal to the server value, because past it the truncation
is silent.
