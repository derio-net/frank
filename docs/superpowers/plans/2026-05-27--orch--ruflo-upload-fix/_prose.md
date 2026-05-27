# Ruflo File-Upload Fix + Upstream Bump — Plan

Fix/extension of the existing `orch` layer (ruflo deployment). Spec:
`docs/superpowers/specs/2026-05-27--orch--ruflo-image-upload-fix-design.md`.

## Problem

Attaching an image (or having a tool fetch a file by URL) in the Ruflo ChatUI
500s with `TypeError: upload.once is not a function`. Plain chat, MCP tools, and
inline text-URL fetch work — only the file storage/retrieval path is broken.

## Root cause

ruvocal (a chat-ui fork) is hardcoded to the RVF storage backend. Its
`RvfGridFSBucket` is an **incomplete shim** of MongoDB's `GridFSBucket`; three
gaps break the Mongo-era callers:

1. `openUploadStream` returns a plain object, not a `Writable` — `uploadFile.ts`
   calls `.once("finish"/"error")` on it → crash.
2. `uploadFile.ts` passes an `ArrayBuffer`; the shim corrupts it to
   `"[object ArrayBuffer]"`, and a naïve `Writable` would throw
   `ERR_INVALID_ARG_TYPE`.
3. `openDownloadStream` returns `{toArray}` (not a `Readable`) and `find()` is
   `async` with no `.next()` — so even after uploads work, **reading the file
   back** (`downloadFile.ts`) and **copy-on-fork** (`conversation.ts`) 500
   independently.

Verified against source at upstream HEAD `a6dd4ab`; none of the affected files
changed in the +154 commits since our pin `ca0a6fa`.

## Approach

Make `RvfGridFSBucket` faithfully implement the GridFS contract — a real
`Writable` (objectMode, coerces the chunk), a real `Readable` via
`Readable.from`, and a synchronous cursor with `next()`+`toArray()`. This fixes
upload + download + copy-on-share in **one file** with **zero caller patches**.
The design was verified end-to-end in Node (ArrayBuffer write → `finish` →
base64 round-trip → `.pipe()` copy).

Carry the fix forward on a bump from `ca0a6fa` → `a6dd4ab` (re-applying the
existing `wasm://` urlSafety patch, which still targets a present line), and bump
the ruflo container's resource requests.

## Execution notes

Executed **inline / subagent-driven by the operator**, not via parallel VK
dispatch — Phase 3 verification needs live cluster access (`kubectl`, `.env`,
ArgoCD, and a browser against `ruflo.cluster.derio.net`) that a remote agent
lacks. Phase 1 lands in the **agent-images** repo
(`~/Docs/projects/DERIO_NET/agent-images`) and produces a new image via that
repo's CI; Phases 2-4 land in **frank**.

## Risks

- Wide 154-commit bump (build-dep drift, `.env` vendoring fallback, behavior
  changes) — covered by the broad smoke test in Phase 3.
- The parity `.patch` must apply at `a6dd4ab`; the target file is unchanged in
  the compare range, but the build guards (`grep -q`) catch a miss.
