# RESUMING — Phase 2 Task B

Plan: `docs/superpowers/plans/2026-04-15--agents--agent-images-and-vk-local-sidecar.md`

## Bounce trigger

Merging frank PR [#104](https://github.com/derio-net/frank/pull/104) — "chore(agents): kali cutover (VK stripped)".
ArgoCD syncs `secure-agent-pod` → pod re-creates (strategy: `Recreate`) → this VK session dies.

## Expected state after bounce

- `kubectl -n secure-agent-pod get pod -l app=secure-agent-pod` shows `Ready: 2/2`.
- Kali container now runs image `ghcr.io/derio-net/secure-agent-kali:325b23e1ede5d9fc4d626c7f27e7dd2e8c76bb6b` (VK stripped).
- No `vibe-kanban` binary in kali; no process bound to 18081 on loopback.
- `vk-local` sidecar unchanged — continues to own port 8081.
- The `PORT=18081`/`HOST=127.0.0.1` env vars on kali are now dead config (nothing reads them).

## Next step

Phase 2 Task B **Step 6** (verification — run from another host after reconnect):

```bash
kubectl -n secure-agent-pod exec deploy/secure-agent-pod -c kali -- sh -c 'command -v vibe-kanban; pgrep -a vibe-kanban || echo NO_PROCESS'
# Expected: (empty output for command -v) + NO_PROCESS

curl -sSf -o /dev/null -w "%{http_code}\n" http://192.168.55.218:8081/api/health
# Expected: 200 (sidecar still serving — note /api/health per Phase 1 Deviation)
```

After verification, Phase 2 is complete. Proceed with:

- **Phase 3** — the bumper workflow is already written on branch `vk/49aa-ffe-39-gh-82` (Phase 3 Task 1 Step 2). That branch needs a PR opened, merged, then Task 2/3 can run workflow_dispatch from main to dry-run and verify the dispatch chain.
- **Phase 4** — Post-Deploy Checklist: blog post, README update, `/sync-runbook`, set plan status to Deployed.

## Pre-bounce state (verified 2026-04-17)

- `frank`: branch `chore/kali-cutover`, HEAD `e29154d`, clean, HEAD == `@{u}`.
- `agent-images`: HEAD `325b23e`, clean, HEAD == `@{u}`.
- `vibe-kanban`: HEAD `5bd749c`, clean, HEAD == `@{u}`.
- Plan checkboxes for Task A Steps 5-7 and Task B Steps 1-3 updated + committed.
- Port-collision deviation (commit 79cf7d0) documented in "Deployment Deviations".
