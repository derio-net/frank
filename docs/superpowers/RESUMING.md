# RESUMING — vk-local frontend-embed cutover (post-Phase-3)

Plan: `docs/superpowers/plans/2026-04-15--agents--agent-images-and-vk-local-sidecar.md`

## Bounce trigger

Merging frank PR [#107](https://github.com/derio-net/frank/pull/107) — "chore(agents): bump agent-images + vk-remote".
ArgoCD syncs `secure-agent-pod` + `vk-remote` → pods roll → this in-cluster Claude session (running inside `secure-agent-pod`) dies when its containers are replaced.

## Why we're bouncing (new deviation, discovered 2026-04-18)

`vk-local:325b23e1...` shipped a placeholder UI (`"Please build @vibe/local-web first"`) because the fork's artifact Dockerfile (`crates/server/Dockerfile`) skipped the pnpm frontend build. Fixed in vibe-kanban PR [#6](https://github.com/derio-net/vibe-kanban/pull/6) (merged into feature branch, not yet to main). Full dispatch chain already rebuilt images; PR #107 points frank at the new SHAs:
- `secure-agent-kali:95e364f` (no functional change — same base)
- `vk-local:95e364f` (now embeds the real UI)
- `vk-remote:91f09db` (fork feature-branch build — same bits as what PR #6 will produce on main)

## Expected state after bounce

- `kubectl -n secure-agent-pod get pod -l app=secure-agent-pod` shows `Ready: 2/2`.
- `kubectl -n vk-remote get pod` shows the new vk-remote pod Ready.
- `curl -sS http://192.168.55.218:8081/` returns real HTML (React app `index.html`), NOT "Please build @vibe/local-web first".
- `curl -sS http://192.168.55.218:8081/api/health` returns `{"success":true,"data":"OK",...}`.
- `https://vk.cluster.derio.net/` loads the VibeKanban UI through Traefik + Authentik.

## Next steps (after reconnect, from another host)

```bash
# 1. Verify pod rolled and images are correct
kubectl -n secure-agent-pod get pod -l app=secure-agent-pod -o jsonpath='{range .items[0].spec.containers[*]}{.name}={.image}{"\n"}{end}'
# Expect: kali=ghcr.io/derio-net/secure-agent-kali:95e364f..., vk-local=ghcr.io/derio-net/vk-local:95e364f...

# 2. Verify UI is served (not placeholder)
curl -sS http://192.168.55.218:8081/ | head -5
# Expect: <!doctype html> ... (Vite-built React index), NOT "Please build @vibe/local-web first"

# 3. Verify vk-remote rolled
kubectl -n vk-remote get pods -o wide
```

Then:

- **Merge vibe-kanban PR #6** — the frontend-embed fix is currently only on the feature branch `fix/server-embed-local-web-dist`. Merging to main keeps the fix permanent and prevents the next fork push from reverting.
- **Phase 4 Post-Deploy Checklist**:
  - Step 2: Write building blog post (`/blog-post` skill) covering split into sidecar + multi-image repo, including this frontend-embed gotcha.
  - Step 4: `/update-readme`.
  - Step 5: `/sync-runbook` — already run on 2026-04-18 (commit `80eabbf`), re-run if more manual-ops added.
  - Step 6: Flip `**Status:**` to `Deployed`.

## Pre-bounce state (verified 2026-04-18)

- `frank`: branch `main`, clean, HEAD == `@{u}` (plan + deviation notes pushed as `80eabbf`).
- `agent-images`: HEAD `95e364f`, clean, HEAD == `@{u}`.
- `vibe-kanban`: branch `fix/server-embed-local-web-dist` pushed; `main` still at `5bd749c`.
- Open PRs: frank [#107](https://github.com/derio-net/frank/pull/107) ready to merge; vibe-kanban [#6](https://github.com/derio-net/vibe-kanban/pull/6) ready to merge.
- PR #106 closed (superseded by #107).
- Phase 3 deviations all resolved: Actions-create-PR permission enabled at org + repo level (2026-04-18); DISPATCH_PAT was already configured in both repos (2026-04-15 bootstrap); full dispatch chain verified end-to-end.
