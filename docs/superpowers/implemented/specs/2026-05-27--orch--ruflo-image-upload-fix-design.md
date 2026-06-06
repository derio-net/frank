# Ruflo File-Upload Fix + Upstream Bump — Design

**Status:** Deployed
**Layer:** `orch` (AI Agent Orchestrator — fix/extension of the existing ruflo deployment)
**Spec date:** 2026-05-27

## Goal

Make file attachments (images, tool-fetched files) work end-to-end in the Ruflo
ChatUI (ruvocal). Today, attaching an image returns HTTP 500
(`TypeError: upload.once is not a function`). Plain chat, MCP tools, and inline
text-URL fetch work; only the **file storage/retrieval path** is broken — and it
is broken in more than one place.

Secondary: bump ruvocal to the latest upstream commit (carrying our local
patches), and give the ruflo container more guaranteed CPU/memory.

## Root cause (confirmed against source at `a6dd4ab`)

ruvocal is a fork of HuggingFace chat-ui. Its storage layer
(`src/lib/server/database.ts:102`) is **hardcoded to the RVF file backend**:
`const bucket = new RvfGridFSBucket()`. There is no MongoDB backend at this
revision (`database/` contains only `rvf.ts` + `postgres.ts`; `postgres.ts` is
not wired into `collections`). Live boot log confirms RVF:
`[RuVocal] Database: /app/db/ruvocal.rvf.json`.

`RvfGridFSBucket` (rvf.ts:1015) is a **shim** that mimics MongoDB's
`GridFSBucket` API so the Mongo-era chat-ui callers keep compiling — but the
mimicry is incomplete in **three** ways. The chat-ui callers were all written
against the real Mongo stream/cursor contract:

1. **`openUploadStream` is not a `Writable`.** It returns a plain
   `{ id, write(), end() }` object with no `.once()`. `uploadFile.ts:23-26` does
   `upload.once("finish"/"error", …)` → `TypeError: upload.once is not a
   function` → 500. *(This is the originally-reported crash.)*

2. **`uploadFile.ts:18` passes an `ArrayBuffer`** —
   `upload.write((await file.arrayBuffer()) as unknown as Buffer)`. The cast is a
   TS lie; at runtime it is an `ArrayBuffer`. The current shim's `write()` does
   `chunk.toString("base64")` on it, producing the literal string
   `"[object ArrayBuffer]"` — i.e. uploads were **also silently corrupting data**
   even before the `.once` crash. (And a *naïve* `Writable` fix would throw
   `ERR_INVALID_ARG_TYPE` here, since a default-mode `Writable.write()` rejects
   `ArrayBuffer`.)

3. **`openDownloadStream` is not a `Readable`, and `find()` is mis-shaped.**
   `openDownloadStream` (rvf.ts:1050) returns `{ async toArray() }` — no `.on()`,
   no `.pipe()`. `find()` (rvf.ts:1059) is declared `async` and returns
   `{ toArray }` with **no `.next()`**. The readers call these as real
   streams/cursors *without awaiting `find`*:
   - `downloadFile.ts`: `bucket.find(...).next()` then
     `openDownloadStream(...).on("data"/"end"/"error", …)`.
   - `conversation.ts:55,63-71` (copy-on-fork-from-shared):
     `await bucket.find(...).toArray()` and
     `openDownloadStream(...).on("error").pipe(uploadStream).on("finish", …)`.

   So even once uploads succeed, **reading an uploaded image back, and copying
   files when forking a shared conversation, both 500 independently.** The
   earlier spec's claim that the download path was "unchanged / round-trip
   consistent" was wrong.

These paths only execute when files exist; since uploads never succeeded, bugs
(2) and (3) were latent until (1) is fixed — which is why fixing only
`openUploadStream` would surface the next crash rather than working.

## Upstream changelog check (decided the approach)

Latest `main` HEAD is `a6dd4ab` (+154 / -0 commits vs our pin `ca0a6fa`).
`files/uploadFile.ts`, `files/downloadFile.ts`, `database/rvf.ts`,
`conversation.ts`, and `lib/server/urlSafety.ts` are **all unchanged** in that
range (verified via the compare API — none appear in the changed-files list).
So the upload/download bugs are **not fixed upstream**, the `wasm://` sed still
targets a present line, and any patch we write applies cleanly at `a6dd4ab`.

## Decisions (locked during brainstorming + code review)

| Decision | Choice | Rationale |
|---|---|---|
| Storage backend | Keep **RVF** | No Mongo backend exists at this revision; switching is not an option without a different upstream |
| Fix shape | **Make the `RvfGridFSBucket` shim faithfully implement the GridFS contract** (real `Writable`, real `Readable`, sync cursor with `next()`+`toArray()`) | Fixes upload **and** download **and** copy-on-share in one file; zero caller patches; minimal patch surface across bumps; upstream-PR-worthy |
| `uploadFile.ts` call site | **Do not patch** | An objectMode `Writable` that coerces the chunk (`Buffer.from`) absorbs the `ArrayBuffer` at the shim boundary — verified in Node — so no caller change is needed. Keeps us to one patched file. |
| Upstream version | **Bump `ca0a6fa` → `a6dd4ab`** | Ride 154 upstream commits forward; carry our patches |
| `wasm://` patch | **Keep** (existing Dockerfile sed) | `urlSafety.ts` unchanged upstream; guard line still present |
| ChatUI slowness | **Bump container resources now**; defer root-cause investigation | User decision. Likely gemma inference, not the Node frontend, but a request bump is cheap |

## Changes

### 1. agent-images — `ruflo-server/Dockerfile`

- Bump `ARG RUFLO_GIT_REF=ca0a6fa…` → `a6dd4ab3d527fbba3e7202741c9479315cc56a0b`.
- Keep the existing `wasm://` `sed` + `grep -q` guard (no change).
- **Apply a GridFS-shim parity patch** (`.patch` via `git apply`, multi-line) to
  `ruflo/src/ruvocal/src/lib/server/database/rvf.ts`. Replace the three broken
  methods of `RvfGridFSBucket` and add `import { Readable, Writable } from
  "node:stream";`. The replacement (verified end-to-end in Node — upload of an
  `ArrayBuffer`, `.once("finish")`, base64 round-trip, and `.pipe()` copy all
  pass):

```ts
import { Readable, Writable } from "node:stream";

export class RvfGridFSBucket {
  private get files() { return getCollection("_files"); }

  openUploadStream(filename: string, options?: { metadata?: Record<string, unknown>; contentType?: string }) {
    const id = randomUUID();
    const chunks: Buffer[] = [];
    const files = this.files;
    const s = new Writable({
      objectMode: true,                       // so callers may pass ArrayBuffer/Uint8Array/Buffer/string
      write(chunk, _enc, cb) {
        try { chunks.push(typeof chunk === "string" ? Buffer.from(chunk) : Buffer.from(chunk as ArrayBufferLike)); cb(); }
        catch (e) { cb(e as Error); }
      },
      final(cb) {
        try {
          const data = Buffer.concat(chunks).toString("base64");
          files.set(id, {
            _id: id, filename,
            contentType: options?.contentType ?? "application/octet-stream",
            length: data.length, data,
            metadata: options?.metadata ?? {}, createdAt: new Date(),
          });
          scheduleSave(); cb();
        } catch (e) { cb(e as Error); }
      },
    });
    (s as unknown as { id: ObjectId }).id = new ObjectId(id);
    return s;                                  // emits finish/error → satisfies uploadFile.ts .once(); .write()/.end()/.pipe() all work
  }

  openDownloadStream(id: ObjectId | string) {
    const fileId = typeof id === "string" ? id : id.toString();
    const file = this.files.get(fileId);
    return Readable.from(file ? [Buffer.from(file.data as string, "base64")] : []);
  }

  async delete(id: ObjectId | string) {        // unchanged from upstream
    const fileId = typeof id === "string" ? id : id.toString();
    this.files.delete(fileId); scheduleSave();
  }

  find(filter: Record<string, unknown> = {}) {  // sync cursor: next() + toArray() (callers don't await find)
    const results: Record<string, unknown>[] = [];
    for (const doc of this.files.values()) {
      if (matchesFilter(doc, filter)) { const { data, ...meta } = doc; results.push(meta); }
    }
    let i = 0;
    return { next: async () => (i < results.length ? results[i++] : null), toArray: async () => results };
  }
}
```

Notes: storage stays base64 (download decodes base64 → raw bytes → `downloadFile`
re-encodes for its `{type:"base64"}` return — round-trip preserved). `length`
stays the base64-string length to match the original shim; nothing in ruvocal
reads it, so the value is cosmetic. `scheduleSave` is a module-level function
(rvf.ts:150) and `ObjectId`/`randomUUID`/`matchesFilter` are already imported —
only `node:stream` is new. The patch targets a file unchanged between `ca0a6fa`
and `a6dd4ab`, so it applies cleanly at the new ref.

### 2. frank — `apps/ruflo/manifests/deployment.yaml`

- Bump `ruflo` and `ruflo-shell` image SHAs to the new agent-images build (both
  tags track the same agent-images commit; the agent-images-bump workflow
  normally drives this).
- Resource bump on the `ruflo` container:
  - requests: `cpu 500m → 1`, `memory 1Gi → 2Gi`
  - limits: unchanged (`cpu 4`, `memory 8Gi`) — a request bump removes
    scheduling/throttle contention; raising limits would not help if the real
    latency is gemma inference on gpu-1 (deferred investigation).

## Verification (end-to-end — Synced/Healthy is not sufficient)

1. **Image round-trip (the real test):** with a multimodal model (`gemma-12b` or
   `qwen-vl-7b`), attach an image → normal response, **no 500**, no
   `upload.once` / `ERR_INVALID_ARG_TYPE` in
   `kubectl -n ruflo-system logs deploy/ruflo -c ruflo`. Then **re-open the
   conversation and confirm the image renders** (exercises `downloadFile.ts` —
   the read path that was independently broken).
2. **Tool URL file-fetch:** a fetch that stores a file no longer 500s and is
   readable.
3. **Copy-on-fork:** forking/continuing from a shared conversation that has a
   file attachment succeeds (exercises `conversation.ts` `.pipe()` path).
4. **Regression — chat:** plain chat against a local model still responds.
5. **Regression — MCP/wasm:** with the per-model tools toggle on, RVAgent Local
   tools still load; no `rejected.*wasm` / `all selected MCP servers rejected`
   warnings (the `wasm://` patch survived the bump).
6. **Broad smoke (154-commit bump):** model list loads, settings/feature-flags
   endpoints 200, no new boot errors.

## Risks

- **Wide bump (154 commits):** build-dep drift, the `.env` vendoring fallback
  (`RUFLO_ENV_FALLBACK_SHA` curl), possible behavior/default changes. Mitigation:
  the broad smoke test; the build's `grep -q` guard catches a missed wasm patch
  at build time.
- **Patch application:** the parity `.patch` must apply at `a6dd4ab`. Confirmed
  the file is unchanged in the compare range; verify at build time regardless.
- **objectMode + pipe:** the download `Readable.from(...)` is objectMode and is
  piped into the objectMode upload `Writable`; verified compatible in Node. If a
  future upstream change reshapes these callers, re-verify.

## Out of scope

- Migrating to MongoDB or Postgres (no first-class backend exists at this
  revision).
- Root-cause investigation of ChatUI slowness (deferred; only the resource bump
  is in scope). Frank has no metrics-server, so that investigation reads from
  Grafana.

## Docs / follow-up

- Update `docs/runbooks/frank-gotchas/paperclip-ruflo.md` (+ one-liner in
  `agents/rules/frank-gotchas.md`): the `RvfGridFSBucket` is an **incomplete
  GridFS shim** (upload/download/find all needed parity fixes), ruvocal is
  **RVF-only** at this revision (no Mongo to switch to), and the per-model
  `supportsTools`/`forceTools` toggle requirement for MCP tools to load.
- File the `rvf.ts` parity fix as an upstream PR to ruvnet/ruflo (alongside the
  still-pending `wasm://` urlSafety PR).
- Per the layer fix/extension workflow: update the ruflo layer's existing
  building/operating posts if narrative-worthy; no new post.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-05-27--orch--ruflo-upload-fix | `derio-net/frank` | `docs/superpowers/plans/2026-05-27--orch--ruflo-upload-fix/` | — |
