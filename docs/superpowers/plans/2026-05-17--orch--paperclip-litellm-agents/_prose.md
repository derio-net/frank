# Paperclip via LiteLLM (opencode + hermes adapters) — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-05-17--orch--paperclip-litellm-agents-design.md`
**Status:** In Progress
**Layer:** `orch` (fix/extension of existing Paperclip deployment)

## Narrative

The spec laid out the design; this plan implements it in five working phases plus the auto-appended post-deploy checklist. The shape mirrors the spec's structure but front-loads all the plan-time-only verifications into a single Phase 1 so risks surface before any manifest change lands. The two adapter wirings (opencode in Phase 2, hermes in Phase 3) are independent — they can execute in parallel after Phase 1 — and the MOTD / runbook / stale-comment cleanup waits for both before documenting them in Phase 4. Phase 5 is the only manual phase: hiring agents through Paperclip's UI to satisfy the cluster rule that a layer isn't "Deployed" until its workflow has run end-to-end.

### Why Phase 1 exists as a standalone phase

Three open assumptions from the spec must be resolved before manifest commits:

1. **opencode `model` field shape.** Whether opencode wants `litellm/qwen-coder-14b` or bare `qwen-coder-14b` once `provider.litellm` is declared. Different opencode versions disagree.
2. **Hermes `--model <name>` argument shape.** Whether Hermes accepts a backend `name` from the inference chain (the most ergonomic choice), or whether it always expects `provider/model` or a bare model ID.
3. **Hermes session-DB write path.** `$HERMES_HOME` will be a read-only ConfigMap mount in Phase 3, so Hermes must NOT default its session DB to that location. The override key in `config.yml` must be identified at plan time, otherwise hermes will fail on first write.

Each of these is a CLI-behavior observation, not a Paperclip-side change — they're cheaper to discover by running the CLIs against LiteLLM from the shell sidecar than by guessing in YAML and bouncing the pod three times.

### Phase 1 doubles as the bootstrap install

Verifying CLI behavior requires installing the CLIs first. Phase 1's installs land on the shared `/paperclip` PVC in the same locations Phases 2 and 3 will rely on (`/paperclip/agent-bin/node_modules/.bin/opencode`, `/paperclip/agent-bin/bin/hermes`). The wiring phases then add the declarative inventory entry so the install survives PVC wipes — but the wiring phases never have to re-install, which keeps them fast and PR-shaped.

### Phase 2 and 3 are independent verticals

Each phase delivers one fully-wired adapter end-to-end: ConfigMap → mount → env → smoke test against LiteLLM. If hermes turns out harder than opencode (likely — Python on a Node-only container is the non-trivial part), opencode still lands on its own merits and provides a working LiteLLM-backed adapter for Phase 5's hire.

### Phase 4 is docs-first

External docs (MOTD, runbook, stale comment) are batched because they document things readers compare in one place — if a reader needs to know "how do I hire a LiteLLM-backed agent," they want both adapters covered in one location, not two PRs of context they have to merge in their head.

### Phase 5 is the real success criterion

Per `agents/rules/frank-gotchas.md`:

> A layer is not "Deployed" until its workflow has been triggered + observed end-to-end. ArgoCD Synced/Healthy proves artifacts exist; not that they work.

So Phase 5 is non-skippable: hire one agent of each adapter type, assign each a trivial issue, watch the transcripts complete, and confirm in LiteLLM's logs that the calls were routed to Ollama. Only then does Phase 6 (post-deploy) run.

## Plan-time verification log

Each entry: timestamp (UTC), finding, evidence.

### opencode

- **2026-05-17T12:19Z — Install** (P1.T1.S1): `npm install --prefix /paperclip/agent-bin opencode-ai` succeeded. Installed version: **1.15.3** (`opencode-ai` npm package). Symlink: `/paperclip/agent-bin/node_modules/.bin/opencode → ../opencode-ai/bin/opencode.exe`.
- **2026-05-17T12:19Z — Image-baked wins** (P1.T1.S2 deviation): `which opencode` in the paperclip container resolves to `/usr/local/bin/opencode` (version **1.14.48**, image-baked), NOT the PVC-installed 1.15.3. The PATH is `…:/usr/local/bin:…:/paperclip/agent-bin/node_modules/.bin` — image dirs precede PVC by design (see deployment.yaml comment: "Suffix (not prefix) so image-baked binaries still win"). The PVC install is reachable via absolute path `/paperclip/agent-bin/node_modules/.bin/opencode --version` → 1.15.3. Phase 2 wires `XDG_CONFIG_HOME` for the image-baked binary (1.14.48).
- **2026-05-17T12:21Z — Working model shape** (P1.T1.S3): **Shape A succeeds — `litellm/qwen-coder-14b`** (provider-prefixed). Output: `> build · qwen-coder-14b` + `{"content":"ping"}`. Shape B (`qwen-coder-14b` bare) fails: `Error: Model not found: qwen-coder-14b/.`. The slash-prefixed `provider/model` form is required.
- **2026-05-17T12:21Z — Env interpolation** (P1.T1.S3): `{env:LITELLM_API_KEY}` in `opencode.json` is resolved correctly — verified by 200 OK from LiteLLM (a wrong literal string would produce 401). No syntax change needed.
- **2026-05-17T12:21Z — LiteLLM route confirmed** (P1.T1.S4): `kubectl -n litellm logs … | grep POST` shows 2× `POST /v1/chat/completions HTTP/1.1" 200 OK` from `10.244.10.177` (paperclip pod IP) within the probe window. Both shapes were attempted; only Shape A reached LiteLLM successfully.
- **2026-05-17T12:22Z — Adapter copy verified** (P1.T3.S1): `runtime-config.ts` in the running image (`sha-c445e59`, v2026.512.0) at `/app/packages/adapters/opencode-local/src/server/runtime-config.ts` confirms: line 68 `await fs.cp(sourceConfigDir, runtimeConfigDir, {`, line 69 `recursive: true,`, line 91 `await fs.writeFile(runtimeConfigPath, \`${JSON.stringify(nextConfig, null, 2)}\n\`)` writes only after merging `{...existingConfig, permission: {...existingPermission, external_directory: "allow"}}`. Our `provider.litellm` block is **preserved** on every run.

### hermes

- **2026-05-17T12:19Z — uv install** (P1.T2.S1): `curl … astral.sh/uv/install.sh | env UV_INSTALL_DIR=/paperclip/agent-bin/bin sh` installed **uv 0.11.14** (x86_64-unknown-linux-gnu).
- **2026-05-17T12:24Z — venv relocatability fix** (P1.T2.S2 deviation): First venv attempt failed — `venv/bin/python` symlinked to `/home/agent/.local/share/uv/python/…` (shell sidecar's home PVC), inaccessible from the paperclip container which does not mount `paperclip-shell-home`. Fix: `UV_PYTHON_INSTALL_DIR=/paperclip/agent-bin/python uv venv …` — uv downloads CPython 3.12.13 into the shared PVC at `/paperclip/agent-bin/python/cpython-3.12.13-linux-x86_64-gnu/`. Venv python now resolves to `/paperclip/agent-bin/python/…` — visible from both containers.
- **2026-05-17T12:25Z — Hermes version** (P1.T2.S2): `git+https://github.com/NousResearch/hermes-agent.git@v2026.4.16` resolved to commit `1dd6b5d5fb94cac59e93388f9aeee6bc365b8f42`, installed as **hermes-agent 0.10.0**. Shim: `/paperclip/agent-bin/bin/hermes → /paperclip/agent-bin/hermes-agent/venv/bin/hermes`.
- **2026-05-17T12:25Z — Both containers** (P1.T2.S3): `paperclip-shell` sidecar: `/paperclip/agent-bin/bin/hermes --version` → `Hermes Agent v0.10.0 (2026.4.16)`. `paperclip` container: same via absolute path → same version. PATH widening (`/paperclip/agent-bin/bin`) is Phase 3 work.
- **2026-05-17T12:44Z — Working model shape** (P1.T2.S4): The spec's `inference.chain` config format does NOT exist in hermes v0.10.0. Hermes uses `providers:` dict (keyed by slug) + env vars. The working routing approach: set `OLLAMA_BASE_URL=http://litellm.litellm.svc:4000/v1` + `OLLAMA_API_KEY=$LITELLM_API_KEY` and invoke as `hermes chat -Q -q "…" --provider ollama-cloud --model qwen-think-14b`. Hermes auto-normalizes `ollama-cloud/qwen-think-14b` → `qwen-think-14b` when `--provider ollama-cloud` is explicit. **Working CLI shape: `--provider ollama-cloud --model qwen-think-14b`.**
- **2026-05-17T12:47Z — Session-DB default path** (P1.T2.S5): Hermes writes ALL state to `$HERMES_HOME`: `sessions/session_*.json`, `state.db`, `auth.json`, `auth.lock`, `logs/`, `memories/`, `SOUL.md`. There is **no config key to override the session/state path separately from `$HERMES_HOME`** — `get_config_path()` always returns `$HERMES_HOME/config.yaml` and `ensure_hermes_home()` always creates the full subdirectory tree under `$HERMES_HOME`. Implication: **`HERMES_HOME` cannot be a read-only ConfigMap mount.** Phase 3 must set `HERMES_HOME=/paperclip/agent-bin/.hermes/` (writable PVC) and seed `config.yaml` there via the shell-inventory bootstrapper or an initContainer.
- **2026-05-17T12:47Z — LiteLLM route confirmed** (P1.T2.S6): Two `POST /v1/chat/completions HTTP/1.1" 200 OK` entries in LiteLLM logs from the probe (Shapes D + E both hit LiteLLM). Session JSON confirms model response received. Session files written under `$HERMES_HOME/sessions/`.

### Resolutions for Phase 2/3/4

**P1.T4.S1 — deployment.yaml diff:**

```diff
 env:
   - name: PATH
-    value: "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/paperclip/agent-bin/node_modules/.bin"
+    value: "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/paperclip/agent-bin/node_modules/.bin:/paperclip/agent-bin/bin"
+  - name: XDG_CONFIG_HOME
+    value: /etc/paperclip/opencode-base
+  - name: HERMES_HOME
+    value: /paperclip/agent-bin/.hermes
+  - name: OLLAMA_BASE_URL
+    value: "http://litellm.litellm.svc:4000/v1"
+  - name: OLLAMA_API_KEY
+    valueFrom:
+      secretKeyRef:
+        name: paperclip-llm-key
+        key: LITELLM_API_KEY
```

Note: `HERMES_HOME=/etc/paperclip/hermes-base` (from the original spec) is REVISED to `/paperclip/agent-bin/.hermes` because hermes has no config/state split — the directory must be writable. Phase 3 seeds `config.yaml` at startup via an **initContainer** (preferred over the shell-inventory bootstrapper — see HERMES_HOME deviation note below for rationale).

Alternative for `OLLAMA_API_KEY`: instead of a second `secretKeyRef`, Phase 3 can use Kubernetes variable substitution (`value: "$(LITELLM_API_KEY)"`) since `LITELLM_API_KEY` is already in-scope from `envFrom.secretRef`. Either works; the substitution form is simpler and avoids a redundant secret reference.

**P1.T4.S2 — `external-secret-llm.yaml` header comment refresh:**

The old "http-local coming soon" paragraph is removed. Use this draft **verbatim** — the step text in `01.yaml` reflects the pre-investigation `api_key_env:` assumption (the spec's `inference.chain` schema), which P1.T2.S4 found does not exist in hermes v0.10.0. The actual mechanism is the `OLLAMA_API_KEY` env var, as described below.

```yaml
# Syncs the LiteLLM virtual key from Infisical and exposes it as two env vars:
#   LITELLM_API_KEY  — consumed by opencode via {env:LITELLM_API_KEY} interpolation
#                      in the XDG_CONFIG_HOME-mounted opencode.json
#   LITELLM_BASE_URL — injected but not consumed by either adapter; both hardcode
#                      the URL (opencode in opencode.json, hermes via OLLAMA_BASE_URL)
# LITELLM_API_KEY is also available as OLLAMA_API_KEY in deployment.yaml env so
# hermes (--provider ollama-cloud) can pick it up without a separate secret.
```

## Deployment Deviations

- **P1.T1.S2 — opencode image-baked wins over PVC install**: The paperclip image `sha-c445e59` ships opencode 1.14.48 at `/usr/local/bin/opencode`. This takes precedence over the PVC-installed 1.15.3 because PATH puts `/usr/local/bin` before the PVC suffix. Decision: wire `XDG_CONFIG_HOME` for the image-baked binary. PVC install remains as a newer-version fallback accessible by absolute path and as a baseline for future image updates.
- **P1.T2.S2 — uv venv non-relocatable by default**: uv downloads CPython to the invoking user's home dir (`~/.local/share/uv/python/`), which is the shell sidecar's home PVC — invisible to the paperclip container. Fix: `UV_PYTHON_INSTALL_DIR=/paperclip/agent-bin/python` pins CPython to the shared PVC. Phase 3 must document this env var in the shell-inventory bootstrapper command.
- **P1.T2.S4 — hermes v0.10.0 uses different config schema than spec assumed**: The spec assumed `inference.chain` (a custom config format). Actual hermes v0.10.0 uses `providers:` dict + env vars. The `ollama-cloud` built-in provider with `OLLAMA_BASE_URL`/`OLLAMA_API_KEY` is the working path. Phase 3's hermes ConfigMap will use this schema instead.
- **P1.T2.S5 — HERMES_HOME cannot be read-only**: No config/state path override exists in hermes v0.10.0. `HERMES_HOME` must be a writable directory. Spec's assumption (`/etc/paperclip/hermes-base` as ConfigMap mount) is invalid. Phase 3 revised approach: `HERMES_HOME=/paperclip/agent-bin/.hermes/` (writable PVC), `config.yaml` seeded by an **initContainer** at pod boot. Rationale: the shell-inventory bootstrapper runs in the `paperclip-shell` sidecar which may not start before the main container's first hermes invocation; an initContainer runs before all app containers and writes once unconditionally. The initContainer only needs to write `config.yaml` — `ensure_hermes_home()` creates the rest of the directory tree (`sessions/`, `logs/`, `memories/`, `state.db`) on first run.

## References

- Spec: `docs/superpowers/specs/2026-05-17--orch--paperclip-litellm-agents-design.md`
- Frank gotchas process rule: `agents/rules/frank-gotchas.md` (#process / practice)
- Post-deploy checklist rule: `agents/rules/plan-post-deploy-checklist.md`
- Paperclip deployment manifest: `apps/paperclip/manifests/deployment.yaml`
- LiteLLM values + model aliases: `apps/litellm/values.yaml`
