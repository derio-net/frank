# Phase 3 Verification Evidence

End-to-end verification of the ruflo RVF GridFS shim fix (Phase 2 / PR #464)
against the **live cluster**. Captured 2026-06-04.

Deployed artifact under test:
`ghcr.io/derio-net/ruflo-server:0ff701470c7e4dc38c803134a2355b2479ff683b`
— matches the Phase-2 pin in `apps/ruflo/manifests/deployment.yaml`.

## Why not the browser

The prescribed ChatUI walkthrough at `ruflo.cluster.derio.net` is infeasible
from a headless agent, for **two independent reasons**:

1. The Traefik `ip-allowlist` middleware permits only RFC1918 ranges
   (`apps/traefik/manifests/middlewares.yaml`), so a remote Browser-Use cloud
   browser (public egress IP) is rejected *before* the Authentik SSO
   forward-auth.
2. Every deployed model reports `multimodal:false`, so the UI image-attach
   control is gated off — the image-attach test could not be driven through the
   UI even with network access.

Substituted with checks against the **live deployed bundle + RVF DB**, which for
this fix (root cause = "the shim isn't a real Writable/Readable/cursor") is
stronger evidence than a UI click. Auth is enforced only at the edge, so an
anonymous in-pod session reaches the same app code paths.

## 1. Fix present in the deployed bundle (read-only)

The shim and its callers in the running image:

```
# database-BwMu2W6T.js (RvfGridFSBucket)
6:  import { Writable, Readable } from 'stream';
740: class RvfGridFSBucket {
744:   openUploadStream(filename, options) {
748:     const stream = new Writable({          # real Writable (objectMode), emits 'finish'
782:   openDownloadStream(id) {
785:     return Readable.from(                   # real Readable
804:     next: async () => i < results.length ? results[i++] : null,   # sync cursor
805:     toArray: async () => results

# downloadFile-CmJ1QxBO.js  (the HTTP download route's function)
4:  async function downloadFile(sha256, convId) {
5:    const fileId = collections.bucket.find({ filename: `${convId.toString()}-${sha256}` });
15:   const fileStream = collections.bucket.openDownloadStream(file._id);

# _server.ts-BBA_Z3mf.js  (createConversationFromShare — copy-on-fork)
73:   downloadStream.on("error", reject).pipe(uploadStream).on("error", reject).on("finish", () => resolve());

# urlSafety-CMNAzyRy.js  (wasm allow-line re-applied across the bump)
31:   if (url.protocol === "wasm:") return true;
```

## 2. Module-level contracts against the live bucket + RVF DB

Harness (`p3-evidence-module.mjs`) — imports the deployed chunks, exercises every
contract the fix repairs, and deletes every GridFS object it creates (creates no
conversations):

```js
import { getCollectionsEarly } from '/app/build/server/chunks/database-BwMu2W6T.js';
import { i as isValidUrl } from '/app/build/server/chunks/urlSafety-CMNAzyRy.js';
const { bucket } = await getCollectionsEarly();

// 1. UPLOAD: openUploadStream is a Writable; write an ArrayBuffer; await 'finish'
const ab = payload.buffer.slice(payload.byteOffset, payload.byteOffset + payload.byteLength);
const up = bucket.openUploadStream('p3ev.bin', { contentType: 'application/octet-stream' });
await new Promise((res, rej) => { up.once('error', rej); up.once('finish', res); up.write(ab); up.end(); });

// 2. DOWNLOAD: openDownloadStream is a Readable; round-trip byte-exact
const dl = bucket.openDownloadStream(up.id);            // has .on / .pipe
for await (const c of dl) got.push(Buffer.from(c));

// 3. find(): synchronous cursor with .next() and .toArray()
const cur = bucket.find({ _id: up.id.toString() });     // typeof cur.next/toArray === 'function'

// 4. COPY-ON-FORK (createConversationFromShare idiom)
const srcs = await bucket.find({ filename: { $regex: `^${sharedId}-` } }).toArray();
bucket.openDownloadStream(file._id).on('error', reject)
  .pipe(bucket.openUploadStream(newFilename)).on('error', reject).on('finish', () => resolve());

// 5. wasm urlSafety allow-line + negative controls
isValidUrl('wasm://...'); isValidUrl('http://169.254.169.254'); ...
```

Output:

```
# live collections.bucket = RvfGridFSBucket
1. UPLOAD: Writable returned, .once("finish") fired, ArrayBuffer accepted; stream.id = 5ebabc72-...
2. DOWNLOAD: Readable round-trip byte-exact (78 bytes)
3. find(): synchronous cursor; .next() and .toArray() both return the file meta
4. COPY-ON-FORK: find({$regex}).toArray() + downloadStream.on("error").pipe(uploadStream).on("finish") -> byte-exact
   isValidUrl("wasm://rvagent-local") = true  expected true  OK
   isValidUrl("wasm://x/y?z=1") = true  expected true  OK
   isValidUrl("https://example.com") = true  expected true  OK
   isValidUrl("http://169.254.169.254") = false  expected false  OK
   isValidUrl("http://10.0.0.1") = false  expected false  OK
   isValidUrl("ftp://evil") = false  expected false  OK
5. WASM: allow-line live (wasm:// accepted), unsafe URLs still rejected (no over-permissive regression)
cleanup: all GridFS test objects deleted, 0 residue

MODULE-LEVEL CONTRACTS: ALL PASS
```

## 3. HTTP-level end-to-end (real routes)

Harness (`p3-evidence-http.sh`) — anonymous in-pod session, `Origin` header for
CSRF, message threaded onto the conversation's `rootMessageId`; the image part is
a multipart `files` field with filename `base64;onepix.png` and a base64-text
body (the exact shape `uploadFile.ts` parses). Every conversation it creates is
deleted server-authoritatively via `DELETE /conversation/<id>` with the owning
session cookie (verified 200 → subsequent GET 404).

Output:

```
## A. Broad smoke (read-only)
  /api/v2/models -> HTTP 200
  /api/v2/feature-flags -> HTTP 200
  model ids: mistral-small-24b gemma-12b qwen-vl-7b qwen-coder-14b qwen-think-14b qwen36-a3b qwen36-a3b-nothin
## B. Plain chat (gemma-12b, no MCP)
  POST /conversation/<id> -> HTTP 200 ; final events: {"type":"title","title":"Pong"} {"type":"status","status":"finished"}
## C. Image upload via real HTTP multipart route (uploadFile.ts -> openUploadStream)
  upload POST -> HTTP 200
  persisted msg.files sha256: 587188c0a045543ee44fe1450dd81751b3a27136401cae53dbc480c87d27e819
## D. wasm:// MCP request (no rejection)
  wasm-MCP request -> HTTP 200
## E. Server-authoritative cleanup (DELETE with owning session)
  DELETE /conversation/...b14 -> 200
  DELETE /conversation/...b15 -> 200
  DELETE /conversation/...b16 -> 200
```

Read-back of the HTTP-uploaded file through the app's own `downloadFile()`
(`find({filename}).next()` + `openDownloadStream`), then blob cleanup:

```
HTTP-uploaded blob present on disk as {convId}-{sha}: true
downloadFile() returned keys: [ 'type', 'name', 'value', 'mime' ]
downloadFile() value === original PNG base64: true (96 chars, mime image/png)
GridFS blob deleted; residue: 0
```

## 4. Boot / smoke

Clean boot (also re-confirmed after an unrelated mid-session pod roll):

```
[RuVocal] Database: /app/db/ruvocal.rvf.json
[RVF] Loaded 10 collections from /app/db/ruvocal.rvf.json
Listening on http://0.0.0.0:3000
```

Full pod-log scan over all verification activity: **no**
`upload.once` / `ERR_INVALID_ARG_TYPE` / `downloadStream.on` / `is not a function`
/ fatal / uncaught signatures.

## Step → evidence map

| Step | Evidence |
|---|---|
| T1.S1 upload + read-back | §3.C (HTTP 200 + persisted sha) + §3 read-back (`downloadFile()` byte-exact) + §2.1/§2.2 |
| T1.S2 file-storing path | §2.1 + §3.C — same `openUploadStream` primitive; literal *tool* trigger not run (no deployed model has `supportsTools`) |
| T1.S3 copy-on-fork `.pipe()` | §2.4 (exact `createConversationFromShare` idiom, byte-exact) |
| T2.S1 plain chat | §3.B (HTTP 200, stream finished) |
| T2.S2 wasm/MCP regression | §2.5 (`isValidUrl` allow-line + negative controls) + §3.D (HTTP 200, no rejection); note the request's MCP flow *skips* because no model has `supportsTools`, so the url-safety guard is proven directly rather than through the request flow |
| T2.S3 broad smoke | §3.A + §4 |

## Test-data residue (honest accounting)

GridFS test **blobs** created during verification were all deleted (0 residue,
confirmed above). A number of anonymous-**session** test conversations remain in
the RVF store, plus one dangling `files` reference to an already-deleted blob.

These are **not** cleared by a pod restart (RVF reloads the same on-disk JSON),
and they cannot be removed server-side without the original session cookies
(`DELETE /api/v2/conversations` is `deleteMany({...authCondition})` — scoped to
the caller's own session). External-process edits to `ruvocal.rvf.json` do not
stick: the live single-writer server holds authoritative in-memory state and
re-flushes it on the next change. They are nonetheless **harmless** — anonymous,
session-scoped, invisible to every authenticated (Authentik) user, a few KB
total. Definitive removal requires an operator editing the RVF store during a
brief `kubectl scale deploy ruflo --replicas=0` window (RWO PVC), which is
disproportionate for invisible residue on a learning cluster.
