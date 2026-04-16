# RESUMING — Phase 2 Task A

Plan: `docs/superpowers/plans/2026-04-15--agents--agent-images-and-vk-local-sidecar.md`

## Bounce trigger

Merging frank PR [#86](https://github.com/derio-net/frank/pull/86) — "feat(agents): add vk-local sidecar to secure-agent-pod".
ArgoCD syncs `secure-agent-pod` → pod re-creates (strategy: `Recreate`) → this VK session dies.

## Expected state after bounce

- `kubectl -n secure-agent-pod get pod -l app=secure-agent-pod` shows `Ready: 2/2`.
- `vk-local` sidecar serves on 8081 (winning the port race because it starts faster than kali's in-process VK).
- Kali's npm-installed VK still spawns but fails to bind 8081 — logs show bind error; not fatal.
- `/home/claude` is shared between both containers via `agent-home` PVC.

## Next step

Phase 2 Task A **Step 6** (verification — run from another host after reconnect):

```bash
kubectl -n secure-agent-pod get pod -l app=secure-agent-pod
kubectl -n secure-agent-pod logs deploy/secure-agent-pod -c vk-local --tail=30
kubectl -n secure-agent-pod exec deploy/secure-agent-pod -c vk-local -- ls /home/claude/repos
kubectl -n secure-agent-pod exec deploy/secure-agent-pod -c kali     -- ls /home/claude/repos
# Expected: same directory listing in both containers
```

Then **Step 7**:

```bash
curl -sSf -o /dev/null -w "%{http_code}\n" http://192.168.55.218:8081/api/health
# Expected: 200 (note: /api/health, not /v1/health — see Phase 1 Deviation)
```

After verification, proceed with Phase 2 **Task B** (strip VK from kali image + second bounce).

## Verification artifacts (current pre-bounce state)

- Plan deviation for health endpoint: recorded in "Phase 1 Deviation: Health endpoint path" (`/api/health` not `/v1/health`).
- VK footprint measured pre-bounce: PID 52, RSS 521232 KB (~509 MiB), 0.0% CPU idle.
- Sidecar image: `ghcr.io/derio-net/vk-local:325b23e1ede5d9fc4d626c7f27e7dd2e8c76bb6b`.
