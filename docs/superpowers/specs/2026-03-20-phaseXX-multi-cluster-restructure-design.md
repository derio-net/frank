# Multi-Cluster Monorepo Restructure — Design Spec

> Extracted from the Hop phase design spec (`2026-03-16-phaseXX-hop-public-edge-design.md`, "Repo Structure" section).

## Problem

The frank-cluster repo has a single-cluster layout with `apps/` and `patches/` at root. With the addition of the Hop cluster under `clusters/hop/`, the repo now has an inconsistent structure — Hop lives under `clusters/` while Frank's resources are at root.

## Goal

Restructure to a consistent multi-cluster monorepo where each cluster's resources live under `clusters/<name>/`.

## Target Structure

```
clusters/
  frank/
    apps/                      # moved from apps/
      root/                    # Frank's app-of-apps
      argocd/
      cilium/
      longhorn/
      ...
    patches/                   # moved from patches/
      phase01-node-config/
      phase02-cilium/
      ...
  hop/
    apps/
      root/                    # Hop's app-of-apps
      argocd/
      headscale/
      headplane/
      caddy/
      blog/
    packer/                    # Hetzner image build
blog/                          # Hugo source (unchanged)
docs/                          # Specs, plans, runbooks (unchanged)
secrets/                       # SOPS-encrypted secrets (unchanged)
scripts/                       # Utility scripts (unchanged)
omni/                          # Omni self-hosted config (unchanged)
```

## Migration Checklist

- `git mv apps/ clusters/frank/apps/`
- `git mv patches/ clusters/frank/patches/`
- Update every Application CR template: `$values/apps/<app>/` → `$values/clusters/frank/apps/<app>/`
- Update Frank's ArgoCD root app source path
- Script Omni patch path updates via `omnictl` (delete old path references, apply with new paths)
- Update `CLAUDE.md` — all path references
- Update blog posts referencing repo structure
- Update `docs/runbooks/manual-operations.yaml` path references
- Update any CI workflows referencing `apps/` or `patches/`
- Verify: `argocd app sync root` reconciles cleanly after the move

## Rollback Plan

If ArgoCD fails to reconcile after the move, `git revert` the restructure commit and re-sync. Since ArgoCD reads from Git, reverting the commit restores all paths immediately. The Omni patch path updates via `omnictl` would also need to be reverted.

## Atomicity

The git move and Application CR path updates must be in a single commit. ArgoCD will see the new paths atomically on the next sync. Disable auto-sync before the commit, push, then manually trigger sync to verify before re-enabling auto-sync.
