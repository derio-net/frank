# Ruflo Image-Upload Fix + Upstream Bump — Design

**Status:** Draft
**Layer:** `orch` (AI Agent Orchestrator — fix/extension of the existing ruflo deployment)
**Spec date:** 2026-05-27

## Goal

Make file uploads work in the Ruflo ChatUI (ruvocal). Today, attaching an image
— or having a tool fetch a file by URL — returns HTTP 500 with
`TypeError: upload.once is not a function`. Plain chat, MCP tools, and inline
text-URL fetch all work; only the **file-storage path** is broken.

Secondary: bump ruvocal to the latest upstream commit (carrying our local
patches), and give the ruflo container more guaranteed CPU/memory.

## Root cause (confirmed)

ruvocal is a fork of HuggingFace chat-ui. Its server-side storage layer
(`src/lib/server/database.ts`) is **hardcoded to the RVF file backend** —
`new RvfCollection(...)` for every collection and `const bucket = new
RvfGridFSBucket()`. There is no MongoDB backend wired in at this revision
(the `database/` dir contains only `rvf.ts` and `postgres.ts`; `postgres.ts`
is not even connected to `collections`, consistent with the documented
"DATABASE_URL silently ignored → RVF" gotcha). Live boot log confirms:
`[RuVocal] Database: /app/db/ruvocal.rvf.json`.

`RvfGridFSBucket` is a **shim** that mimics MongoDB's `GridFSBucket` API so the
Mongo-era chat-ui code keeps compiling — but the mimicry is incomplete.
`uploadFile.ts` (leftover chat-ui code) treats the return of
`bucket.openUploadStream(...)` as a Node `Writable` stream:

```ts
const upload = collections.bucket.openUploadStream(`${conv._id}-${sha}`, { ... });
upload.once("finish", () => resolve({ type: "hash", value: sha, ... }));
upload.once("error", reject);
```

But the RVF shim returns a plain object with only `{ id, write(), end() }` — no
`.once()`, not an EventEmitter — so `upload.once(...)` throws. The same broken
contract is used by `conversation.ts` and `routes/conversation/[id]/share/+server.ts`,
so those upload paths are latent failures too.

This explains both reported symptoms with one cause:
- **Image attach** → stored via `uploadFile()` → `.once` crash → 500 (dies
  before the model is consulted).
- **Tool URL fetch** → `/api/fetch-url` returns 200, but storing the fetched
  content as an attachment hits the same `uploadFile()` → 500. (Inline
  text-URL fetch injects text into context and never touches storage, so it
  works — verified live.)

## Upstream changelog check (decided the approach)

| Item | Our pin `ca0a6fa` | Latest HEAD `a6dd4ab` (+154 commits) |
|---|---|---|
| `files/uploadFile.ts` | uses `.once` | **unchanged** — bug still present |
| `database/rvf.ts` (`openUploadStream`) | non-stream shim | **unchanged** — bug still present |
| `lib/server/urlSafety.ts` (wasm guard) | upstream rejects `wasm://` | **unchanged** — our sed still applies; still needed |

Upstream has **not** fixed the upload bug. Therefore: bump to latest, re-carry
the `wasm://` patch (applies cleanly since `urlSafety.ts` is untouched), and add
the shim fix.

## Decisions (locked during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Storage backend | Keep **RVF** | No Mongo backend exists at this revision; switching is not an option without a different upstream |
| Fix shape | **Fix the RVF shim** (make `openUploadStream` return a real `Writable`) | Root-cause fix; repairs `uploadFile` + the latent `conversation.ts`/`share` call sites at once; upstream-PR-worthy |
| Upstream version | **Bump `ca0a6fa` → `a6dd4ab`** | Ride 154 commits of upstream improvement forward; carry our patches |
| `wasm://` patch | **Keep** (existing Dockerfile sed) | `urlSafety.ts` unchanged upstream; guard line still present |
| ChatUI slowness | **Bump container resources now**; defer root-cause investigation | User decision. Likely gemma inference, not the Node frontend, but a request bump is cheap and removes one variable |

## Changes

### 1. agent-images — `ruflo-server/Dockerfile`

- Bump `ARG RUFLO_GIT_REF=ca0a6fa5cb1678b5c57c9289bc09a036f7308c61` →
  `a6dd4ab3d527fbba3e7202741c9479315cc56a0b`.
- Keep the existing `wasm://` `sed` + `grep -q` guard (no change).
- **Add fix A** — apply a patch to
  `ruflo/src/ruvocal/src/lib/server/database/rvf.ts` so
  `RvfGridFSBucket.openUploadStream()` returns a real `Writable`:

```ts
import { Writable } from "node:stream";

openUploadStream(filename, options) {
  const id = randomUUID();
  const chunks: Buffer[] = [];
  const self = this;
  const s = new Writable({
    write(chunk, _enc, cb) {
      chunks.push(typeof chunk === "string" ? Buffer.from(chunk) : chunk);
      cb();
    },
    final(cb) {
      try {
        const data = Buffer.concat(chunks).toString("base64");
        self.files.set(id, {
          _id: id, filename,
          contentType: options?.contentType ?? "application/octet-stream",
          length: data.length, data,
          metadata: options?.metadata ?? {}, createdAt: new Date(),
        });
        scheduleSave();
        cb();
      } catch (e) { cb(e as Error); }
    },
  });
  (s as any).id = new ObjectId(id);
  return s;
}
```

The returned `Writable` emits `finish` on `.end()` and `error` on failure,
satisfying `uploadFile.ts`'s `.once("finish"/"error")`, while `.write()`/`.end()`
still work for the other callers. Storage format stays base64, so the
download/read path is unchanged. Apply as a `.patch` via `git apply` (multi-line;
not sed). The patch targets a file unchanged between `ca0a6fa` and `a6dd4ab`, so
it applies cleanly at the new ref.

### 2. frank — `apps/ruflo/manifests/deployment.yaml`

- Bump `ruflo` and `ruflo-shell` image SHAs to the new agent-images build
  (both tags track the same agent-images commit; the agent-images-bump workflow
  normally drives this).
- Resource bump on the `ruflo` container:
  - requests: `cpu 500m → 1`, `memory 1Gi → 2Gi`
  - limits: unchanged (`cpu 4`, `memory 8Gi`)

  Rationale: a request bump guarantees scheduling headroom and reduces CPU-throttle
  contention. Raising limits is not expected to help if the real latency is gemma
  inference on gpu-1, so limits are left as-is pending the deferred investigation.

## Verification (end-to-end — Synced/Healthy is not sufficient)

A layer is not done until the workflow is observed working:

1. **Image round-trip:** attach an image in the ChatUI with a multimodal model
   selected (`gemma-12b` or `qwen-vl-7b`); expect a normal response, **no 500**,
   no `upload.once` in `kubectl -n ruflo-system logs deploy/ruflo -c ruflo`.
2. **Tool URL file-fetch:** a fetch that stores a file no longer 500s.
3. **Regression — chat:** plain chat against a local model still responds.
4. **Regression — MCP/wasm:** with the per-model tools toggle on, RVAgent Local
   tools still load; no `rejected.*wasm` / `all selected MCP servers rejected`
   warnings (the `wasm://` patch survived the bump).
5. **Broad smoke (154-commit bump):** model list loads, settings/feature-flags
   endpoints 200, no new boot errors.

## Risks

- **Wide bump (154 commits):** build-dep drift, the `.env` vendoring fallback
  (`RUFLO_ENV_FALLBACK_SHA` curl), and possible behavior/default changes.
  Mitigation: the broad smoke test above; the build's `grep -q` guard catches a
  missed wasm patch at build time.
- **Patch application:** the `rvf.ts` `.patch` must apply at `a6dd4ab`. Confirmed
  the file is unchanged in the compare range; verify at build time regardless.
- **base64 length field:** `length` stays the base64-string length (matching the
  original shim) to avoid breaking any size checks in the read path.

## Out of scope

- Migrating to MongoDB or Postgres (no first-class backend exists at this
  revision; would require a different upstream).
- Root-cause investigation of ChatUI slowness (deferred; only the resource bump
  is in scope here). Frank has no metrics-server, so that investigation will read
  from Grafana.

## Docs / follow-up

- Update `docs/runbooks/frank-gotchas/paperclip-ruflo.md` (+ one-liner in
  `agents/rules/frank-gotchas.md`): the `RvfGridFSBucket` upload shim fix, and a
  clarification that ruvocal at this revision is **RVF-only** (no Mongo backend
  to switch to).
- File the `rvf.ts` `openUploadStream` Writable fix as an upstream PR to
  ruvnet/ruflo (alongside the still-pending `wasm://` urlSafety PR).
- Per the layer fix/extension workflow: update the ruflo layer's existing
  building/operating posts if the change is narrative-worthy; no new post.
