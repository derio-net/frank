---
name: bump-image
description: Bump a pinned/CI-built image (or *_PIN) for a Frank or Hop app, watch the ArgoCD rollout, and verify (migrations / smoke test)
user-invocable: true
disable-model-invocation: false
arguments:
  - name: app
    description: App to bump (e.g. "paperclip", "ai-alert-helper", "blog", "vk-bridge")
    required: true
  - name: target
    description: New tag / SHA / version to pin to (omit to pick the latest upstream)
    required: false
---

# Bump-and-Roll a Pinned Image

Update a SHA/version-pinned (or CI-built) image for `$ARGUMENTS.app`, drive the
rollout through ArgoCD, and verify it actually came up. This is the recurring
GitOps "image bump" task — distinct from `/deploy-app` (new app).

> Declarative-only (`repo-principles.md`): bump the pin in git; never `kubectl
> set image`. **Environment:** Frank apps → `source .env`; Hop apps (blog,
> headscale, caddy) → `source .env_hop` (never `.env` first — `hop-gotchas.md`).

## Steps

### 1. Locate the pin

Pins live in one of:
- `apps/<app>/manifests/deployment.yaml` or `clusters/hop/apps/<app>/manifests/deployment.yaml` — `image:` with a SHA tag (e.g. `ghcr.io/derio-net/blog:<sha>`)
- `apps/<app>/values.yaml` — `image.tag`
- an env `*_PIN` (e.g. `VK_BRIDGE_PIN`) in a deployment/secret

```bash
grep -rn "image:\|image.tag\|_PIN" apps/$ARGUMENTS.app clusters/hop/apps/$ARGUMENTS.app 2>/dev/null
```

Note how the image is built: **CI-built** (e.g. `ai-alert-helper` via
`gh workflow run build-ai-alert-helper.yml`; `blog` commits its own SHA tag) vs a
straight upstream pin.

### 2. Diff old → new BEFORE bumping (DB apps especially)

For apps that run migrations on boot (e.g. **paperclip**), this is mandatory —
a bad migration crashes the pod on boot:

- Diff the migration files across the `<old>..<new>` SHA range on the upstream
  **public** repo. Flag `CREATE EXTENSION` (must pre-create) and unguarded
  `DROP CONSTRAINT` / `ALTER` (crashes if the object is absent — confirm it
  exists in the live DB first).
- **Snapshot the Postgres PVC first** (paperclip: `data-paperclip-db-postgresql-0`,
  **not** `paperclip-data`). Strategy is `Recreate`, so downtime = image pull, not
  the migration itself.
- Full recipe: `docs/runbooks/frank-gotchas/paperclip-ruflo.md`.

### 3. Bump the pin

- **Upstream pin:** edit the `image:` / `image.tag` / `*_PIN` to `$ARGUMENTS.target`, commit, push. ArgoCD auto-syncs.
- **CI-built image:** trigger the build (it commits the new tag and ArgoCD syncs):
  ```bash
  gh workflow run build-$ARGUMENTS.app.yml [--ref <branch>]
  ```
  Note: some CI workflow tags are hardcoded and must be bumped alongside the
  version (see `obs-digest.md`).

### 4. Watch the rollout

```bash
kubectl -n <ns> rollout status deploy/$ARGUMENTS.app --timeout=300s
# or follow the ArgoCD app:
kubectl -n argocd get application $ARGUMENTS.app -o wide -w
kubectl -n <ns> get pods -l app=$ARGUMENTS.app -w
```

Long-running rolls are well-suited to a background `Monitor` / `Bash
run_in_background` watch.

### 5. Verify (don't trust Synced/Healthy alone)

ArgoCD `Synced`/`Healthy` proves the artifact deployed, not that it works
(`frank-gotchas.md` → Process/practice). So:

- **Smoke test** the app's real entrypoint. Watch for the stderr-banner trap:
  health checks capturing `$(... --dry-run)` must use `2>&1` (the v2 vk.bridge
  banner goes to stderr — `agent-shells` gotcha).
- **DB apps:** confirm the migration's *tables* exist (do **not** trust the
  `__drizzle_migrations` row count — it doesn't map to file index).
- Check pod logs for boot errors / crashloops.

### 6. If it crashloops on boot

Usually a migration hitting a missing object (step 2). Roll the pin back, restore
the PVC snapshot if a migration partially applied, and re-diff. For paperclip
specifics see `paperclip-ruflo.md`.

## Summary

Show: the pin location + old→new value, the migration diff verdict (and snapshot
taken, if DB), rollout status, and the smoke-test / migration-table verification
output. State plainly whether the new image is verified working — not just synced.
