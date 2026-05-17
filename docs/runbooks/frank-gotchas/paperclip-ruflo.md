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

## Company import from GitHub is unauthenticated upstream

Discovered 2026-05-16. The board UI's import flow has two source modes: **GitHub** and **Local zip**. The GitHub path constructs `https://raw.githubusercontent.com/<owner>/<repo>/<ref>/COMPANY.md` and fetches it via `server/src/services/github-fetch.ts:ghFetch`, which is exactly `fetch(url, init?)` — no `Authorization` header is ever set and no env var is read. There is no token slot in the Admin UI because the backing code path has nothing to plumb a token into. So private repos fail at the preview step with "GitHub company package is missing COMPANY.md".

Workarounds, in increasing effort:

1. **Local zip** — clone the package locally (or in `paperclip-shell` using the operator's SSH access), zip the subtree with `git archive` to avoid the macOS resource-fork warning, upload via the UI's **Local zip** tab:

   ```bash
   git archive --format=zip --prefix=<name>/ HEAD:<subdir> > <name>.zip
   # or, if not in a git repo:
   python3 -m zipfile -c <name>.zip <subdir>/
   ```

   `readLocalPackageZip` detects the shared top-level directory and strips it as the package prefix, so zipping the *directory* (not its contents) is correct.

2. **Public scratch repo** — mirror only the company-package markdown to a public repo if the content is non-sensitive.

3. **Fork the image with token injection** — same pattern we used for `ruflo-server`'s wasm: fix (see above). Patch `github-fetch.ts:ghFetch` to inject `Authorization: Bearer ${PAPERCLIP_GITHUB_TOKEN}` when the hostname is in the `github.com` / `*.githubusercontent.com` set, wire an ExternalSecret in `apps/paperclip/manifests/`. Worth an upstream PR — Paperclip already reads `GITHUB_TOKEN` from `process.env` for the unrelated `scripts/paperclip-commit-metrics.ts`, so the env-var convention is established.

## Hard DELETE is the only path to free `issue_prefix`

`companies_issue_prefix_idx` is a plain `UNIQUE INDEX` on `issue_prefix` — there is no partial-where filtering archived rows. Symptom: a fresh import of company "Stoa" returns 500 with `duplicate key value violates unique constraint "companies_issue_prefix_idx"` even though the colliding `STO` row is archived in the UI. The DB doesn't care about the lifecycle column.

The board UI deliberately exposes only Archive — Delete is API-only and gated to `assertBoard(req)` in `server/src/routes/companies.ts:400` precisely because there's no filesystem cleanup safety net (`svc.remove` is a single Drizzle transaction with zero `fs.*` calls; `PAPERCLIP_HOME=/paperclip` state for the company is orphaned on disk).

**To free a prefix:** delete the holding company via API or (when API breaks — see below) via direct DB. Then clean up its filesystem subtrees with `scripts/paperclip-purge-fs.sh`.

## `DELETE /api/companies/:id` cascades incompletely on active companies

Discovered 2026-05-16 against `ghcr.io/paperclipai/paperclip:sha-c445e59` (v2026.512.0). The `companies.ts:remove()` function performs a single Drizzle transaction that explicitly deletes from ~25 named tables in a fixed order, then deletes the `companies` row. Two failure modes on active companies:

1. **FK ordering bug** — `cost_events.heartbeat_run_id` references `heartbeat_runs.id`, but the function deletes `heartbeat_runs` first (line 271) and `cost_events` afterwards (line 276). For archived companies with no run history this is invisible; for active companies it 500s on:

   ```
   update or delete on table "heartbeat_runs" violates foreign key constraint
   "cost_events_heartbeat_run_id_heartbeat_runs_id_fk" on table "cost_events"
   ```

2. **Missing cascades for newer tables** — schema additions since the function was last touched aren't in the cascade. Observed in this incident: `issue_thread_interactions` referencing `issues`. The full list of `company_id`-bearing tables is much larger than what the function enumerates; any of the post-2026-02 additions could trip the cascade.

### Workaround: retry-loop SQL DO block

Iterate over every table with a `company_id` column, attempt the delete, swallow FK violations, and retry until either no errors remain or a pass limit is hit. PostgreSQL's `EXCEPTION WHEN foreign_key_violation` rolls back only the failing statement (implicit savepoint), so the surrounding `DO` block keeps making progress.

```sql
BEGIN;
DO $purge$
DECLARE
  targets uuid[] := ARRAY['<id1>'::uuid, '<id2>'::uuid];
  tbl text;
  pass int := 0;
  fk_errors int;
BEGIN
  LOOP
    pass := pass + 1;
    fk_errors := 0;
    FOR tbl IN
      SELECT table_name FROM information_schema.columns
      WHERE table_schema='public' AND column_name='company_id' AND table_name <> 'companies'
      ORDER BY table_name
    LOOP
      BEGIN
        EXECUTE format('DELETE FROM %I WHERE company_id = ANY($1)', tbl) USING targets;
      EXCEPTION WHEN foreign_key_violation THEN
        fk_errors := fk_errors + 1;
      END;
    END LOOP;
    EXIT WHEN fk_errors = 0;
    EXIT WHEN pass > 20;
  END LOOP;
END $purge$;
DELETE FROM companies WHERE id = ANY(ARRAY['<id1>','<id2>']);
COMMIT;
```

Followed by the filesystem cleanup script — `scripts/paperclip-purge-fs.sh` — which removes the per-company subtrees under `/paperclip/instances/default/{companies,projects,data/storage}/<id>`. The script defaults to dry-run; pass `--apply` to actually delete. It refuses to touch any path outside `INSTANCE_ROOT` and refuses to delete the keeper UUID.

Both bugs are upstream-fixable: explicit `cost_events` reordering, plus either an exhaustive table list or — much better — a schema-introspecting cascade that mirrors what the workaround does.

## `createCompanyWithUniquePrefix` retry-on-collision is broken

`server/src/services/companies.ts:createCompanyWithUniquePrefix` is *supposed* to derive a 3-letter prefix from the company name (`name.toUpperCase().replace(/[^A-Z]/g,'').slice(0,3)`) and, on a unique-constraint conflict, append `A`, `AA`, `AAA`, … via `suffixForAttempt(n)` and retry up to 10000 times. In practice it bails on attempt 1, returning the 500 from above directly to the client.

Root cause: `isIssuePrefixConflict(error)` reads `error.code` and `error.constraint` from the *outer* error, but the actual `postgres.PostgresError` is wrapped in a `DrizzleQueryError` whose top-level shape has neither field. So the classifier returns `false`, the `catch` clause rethrows, and the retry never fires.

**For the operator:** the first attempt's prefix must be unique. If `AGENT_NAME` derives to `XYZ` and `XYZ` is taken (archived OR active), rename the company to something whose first 3 alpha chars are free. The display name can be changed later in the UI; the prefix can't.

Examples:

| Import name | Derived prefix |
|---|---|
| `Stoa` | `STO` |
| `Synthesis Stoa` | `SYN` |
| `Agentic Stoa` | `AGE` |

Upstream fix is one line: unwrap the cause chain in `isIssuePrefixConflict`. Worth a PR.

## Operator API calls from CLI need Origin header + `%3D` cookie encoding

Two independent guards make CLI access to the board-scoped API non-obvious:

**1. `boardMutationGuard` requires a trusted Origin.** Every non-`GET`/`HEAD`/`OPTIONS` request whose actor is `board` (i.e. session-cookie auth, not a board API key) must include `Origin` or `Referer` matching the configured `PAPERCLIP_PUBLIC_URL` (Frank: `http://192.168.55.212:3100`) — or one of `http://localhost:3100` / `http://127.0.0.1:3100` (the built-in dev defaults). Without it the API returns 403 `Board mutation requires trusted browser origin`. Bypass: issue a board API key (token path: `boardAuth.findBoardApiKeyByToken`), pass as `Authorization: Bearer …` — the `board_key` source skips the Origin check entirely.

**2. better-auth's session cookie value contains `=` which curl mishandles.** Cookie name format: `paperclip-<instanceId>.session_token` (instanceId defaults to `default`, derived from `PAPERCLIP_INSTANCE_ID`). The cookie value is `<token>.<base64-signature>` and the signature is `=`-padded. When pasted directly into `curl -b "name=value"` or interpolated through inline shell quoting, the trailing `=` reaches the server unencoded, fails the HMAC check, and the request is silently treated as unauthenticated (`Board access required`).

Working incantation — file-backed to dodge shell quoting:

```bash
# In the browser: DevTools → Network → any /api request → Copy Request Header "Cookie"
# Save the entire line to /tmp/pc_cookie.txt verbatim (it includes the %3D padding the browser sends).

ORIGIN='http://192.168.55.212:3100'
curl -s -H "Cookie: $(tr -d '\n' < /tmp/pc_cookie.txt)" \
     -H "Origin: $ORIGIN" \
     -X DELETE "http://192.168.55.212:3100/api/companies/<id>"
```

Diagnostic shortcut: if you get `Board access required` with a valid-looking cookie, the most likely cause is `=` → not `%3D`. If you get `Board mutation requires trusted browser origin`, the Origin header is missing.
