# Frank Gotchas — Paperclip / Ruflo

Long-form companion to the **Paperclip / Ruflo** section in `agents/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

## `paperclip-data` PVC fills up

Currently 10Gi (bumped from 2Gi on 2026-05-12 after hitting 100% / ENOSPC). The main space consumers are `/paperclip/instances` (run histories) and `/paperclip/.npm` (can grow to 500MB+).

If ENOSPC returns, clear the cache inside the `paperclip` container:

```bash
rm -rf /paperclip/.npm/_cacache
```

## Paperclip's "Test environment" runs in the app container, NOT the shell sidecar

And so does every other agent-CLI invocation paperclip spawns at runtime. Both containers live in the same pod, but they don't share a rootfs and they don't share a PID namespace (the latter forced by the `shareProcessNamespace` gotcha — see `agent-shells.md`). So `gemini`/`codex`/etc. installed via the `paperclip-shell-inventory` ConfigMap — which targets `/home/agent` on the shell's PV — are reachable over SSH but invisible to paperclip's `child_process.spawn()`.

The Node spawn inherits paperclip's container PATH (`/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`), which has no overlap with the shell sidecar's mise/npm-global tree. The deployment's only cross-container seam is the `paperclip-data` PVC, mounted as `/paperclip` in both containers.

Wire an agent CLI through that seam:
- (a) `npm install --prefix /paperclip/agent-bin <pkg>` from the shell — node is on PATH there via mise
- (b) PATH-suffix `/paperclip/agent-bin/node_modules/.bin` on the paperclip container in `apps/paperclip/manifests/deployment.yaml`

Suffix not prefix: image-baked binaries at `/usr/local/bin` should still win (paperclip pins its own codex version that way; the PVC fills gaps like `@google/gemini-cli` only). The adapter `command` field is read-only in Paperclip's UI, so an absolute-path override there isn't an option. Per-session install reminder is mounted at `/etc/profile.d/60-paperclip-shell-tips.sh` from `apps/paperclip/manifests/configmap-shell-motd-tips.yaml` so the recipe surfaces on every SSH login.

Same trap shape applies to ruflo and any future hybrid pod where the app container spawns subprocesses the operator wants to provision from the sidecar — the sidecar exists for *humans*, not for app code to reach into.

## ruvocal liveness path

`/api/v2/feature-flags` is the right readiness/liveness path for ruvocal (ruflo-server), NOT `/`. ruvocal SSR-renders the model list at request time, so a probe against `/` reaches into LiteLLM, the configured DB, and any other upstream the SSR loader touches. Net: any flake in the gateway flips the readiness probe and ArgoCD sees the Deployment go `Degraded` for reasons unrelated to the ruvocal process being alive. `/api/v2/feature-flags` is served by the same Express stack with no LLM dependency — use it (or any equivalent static-content endpoint) for true process-liveness.

## LiteLLM-fronted apps need a LiteLLM virtual key, not the upstream provider key

Pointing `OPENAI_BASE_URL` at `http://litellm.litellm.svc:4000` while injecting `OPENAI_API_KEY=<OPENROUTER_API_KEY>` produces `401 Unauthorized` on every model-list call (LiteLLM authenticates against its own key store, not the upstream provider).

Provision a LiteLLM virtual key per consumer (e.g. `RUFLO_LITELLM_KEY`, `PAPERCLIP_LITELLM_KEY`) in Infisical, have ESO project it as `OPENAI_API_KEY`. Symptom for SSR apps that load the model list at render time (ruvocal): the page returns 500, not 401.

## ruvocal stores state in RVF JSON, NOT Postgres

ruvocal at the current pinned SHA stores state in an RVF JSON file at `/app/db/ruvocal.rvf.json`. `DATABASE_URL` is silently ignored at this revision; the Phase 1 plan note that called the destination "PostgreSQL" was based on the env-var inventory, not on a runtime trace. Surface during boot: log line `[RuVocal] Database: /app/db/ruvocal.rvf.json` followed by `[RVF] No existing database … starting fresh`.

Mount a PVC at `/app/db` (or hives/runs/conversations vanish on every pod restart). The `ruflo-db` Bitnami postgresql sub-app is parked in case a future re-vendor switches back to Postgres.

## chat-ui's URL-safety guard rejects `wasm://` — silently soft-bricks autopilot

Discovered 2026-05-16 against ruflo-server pinned at agent-images `8006389` / ruvnet/ruflo `9b16981`. **Symptom**: user opens `ruflo.cluster.derio.net`, picks any local model, types a message, clicks send — and gets no response. No 4xx/5xx in the network panel, no error toast in the SPA. The request appears to fire but nothing comes back.

### Why it happens

ruvocal ships an in-browser WebAssembly MCP server ("RVAgent Local") advertised to clients as `url: "wasm://local"`. The chat-ui SPA selects it by default when no other MCPs are configured (and our deployment has `MCP_SERVERS=` empty). On every chat submit, the SPA sends `selectedMcpServers: [{name:"RVAgent Local (WASM)", url:"wasm://local"}]` plus `autopilot: true` (chat-ui default, surfaced as the pulsing-emerald AUTO button on the chat input).

Server-side, `runMcpFlow` passes every selected MCP through `isValidUrl()` (`src/lib/server/urlSafety.ts`). The guard only permits http/https against safe hostnames — sensible SSRF prevention for HTTP MCPs, but categorically wrong for a scheme the server never calls. `wasm://local` is rejected; `runMcpFlow` strips it, sees zero valid servers, and returns `"not_applicable"`. With autopilot ON, the client-side state then refuses to actually fire the POST — a non-event in the server log, just two WARNs at the prior SSR step:

```
[mcp] rejected servers by URL safety   rejected: [{"name":"RVAgent Local (WASM)","url":"wasm://local"}]
[mcp] all selected MCP servers rejected by URL safety guard
```

Without server-side or browser-side evidence of a chat POST, "no response" is the only signal the user gets.

### Fix

A one-line allow-line in `isValidUrl()` (browser-local schemes have nothing the server needs to validate). Applied via sed in our `agent-images/ruflo-server/Dockerfile`:

```dockerfile
RUN sed -i \
      -e 's|const hostname = url\.hostname\.toLowerCase();|if (url.protocol === "wasm:") return true;\n\t\tconst hostname = url.hostname.toLowerCase();|' \
      ruflo/src/ruvocal/src/lib/server/urlSafety.ts \
 && grep -q 'protocol === "wasm:"' ruflo/src/ruvocal/src/lib/server/urlSafety.ts
```

Shipped in agent-images PRs [#77](https://github.com/derio-net/agent-images/pull/77) (urlSafety patch + ruvnet/ruflo bump to `ca0a6fa`) and [#78](https://github.com/derio-net/agent-images/pull/78) (vendor `.env` from `0fd61e3e5b20` after upstream untracked it for security). frank PR [#266](https://github.com/derio-net/frank/pull/266) bumped the deployment to agent-images `8af32cb`.

### Verification recipe (if the patch ever regresses)

```bash
# 1. Patch present in built bundle
kubectl -n ruflo-system exec deploy/ruflo -c ruflo -- \
  sh -c 'grep -nH "wasm:" /app/build/server/chunks/urlSafety-*.js'
# expect: ...urlSafety-XXXX.js:NN:        if (url.protocol === "wasm:") return true;

# 2. No rejection warns during a chat-ui page render
kubectl -n ruflo-system logs deploy/ruflo -c ruflo --since=2m | \
  grep 'rejected.*wasm\|all selected MCP servers rejected' && echo FAIL || echo PASS

# 3. wasm:// makes it past the safety guard into the chat handler
#    (triggers a downstream "Ancestor not found" because this curl flow skips
#    the SPA's full conversation-init dance — that's expected; the signal is
#    that locals.mcp.selectedServers contains the wasm:// entry in the 500's
#    log body, proving the URL passed isValidUrl)
```

### Upstreaming

The allow-line is straightforwardly upstreamable to ruvnet/ruflo; file a PR there so we can drop the local sed on the next agent-images bump.

### Related: autopilot's silent-block UX

Upstream commit `9cfba12` ("autopilot AUTO toggle is silent + autopilotMaxSteps setting was dead wiring", ruvnet/ruflo#1742) made the visible AUTO/MANUAL state legible (previously both branches rendered the same "AUTO" label, so users had no UI signal that the toggle did anything). That fix is included in the `ca0a6fa` bump but doesn't address the underlying "autopilot + zero valid MCPs → silent submit block" interaction; the wasm:// allowance does, by ensuring the WASM MCP is no longer the zeroth case.
