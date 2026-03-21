# Multi-Cluster Monorepo Restructure — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the frank-cluster repo from a single-cluster layout (`apps/`, `patches/` at root) to a multi-cluster monorepo (`clusters/frank/apps/`, `clusters/frank/patches/`), matching the existing `clusters/hop/` structure.

**Architecture:** Move Frank's `apps/` and `patches/` directories under `clusters/frank/`, update all 41+ ArgoCD Application CR template paths, update the root app source path in ArgoCD, and fix all references in CLAUDE.md, blog posts, CI workflows, and runbooks. Must be atomic — disable auto-sync, commit, push, manually sync, verify, re-enable.

**Tech Stack:** Git, ArgoCD, Omni (config patch paths), Hugo (blog post references), GitHub Actions (CI workflow references)

**Status:** Not started.

**Origin:** Extracted from Hop edge plan (`docs/superpowers/plans/2026-03-16--edge--hop-public.md`, former Task 17 / Chunk 7).

**Spec:** `docs/superpowers/specs/2026-03-20--repo--multi-cluster-restructure-design.md`

---

## Risk Assessment

This is a **high-blast-radius refactor** — it touches every ArgoCD Application CR on the Frank cluster. The rollback plan is straightforward (`git revert` + re-sync), but the operation must be atomic and tested carefully.

**Pre-requisites:**
- Frank cluster healthy, all ArgoCD apps Synced/Healthy
- No in-flight deployments or pending PRs touching `apps/` paths
- ArgoCD port-forward access confirmed

---

## Chunk 1: Restructure

### Task 1: Move directories and update all path references

**Files:**
- Move: `apps/` → `clusters/frank/apps/`
- Move: `patches/` → `clusters/frank/patches/`
- Modify: All 41+ Application CR templates in `clusters/frank/apps/root/templates/`

- [ ] **Step 1: Disable Frank ArgoCD auto-sync**

```bash
source .env
argocd app set root --sync-policy none --port-forward --port-forward-namespace argocd
```

- [ ] **Step 2: Move directories**

```bash
mkdir -p clusters/frank
git mv apps clusters/frank/apps
git mv patches clusters/frank/patches
```

- [ ] **Step 3: Update all Application CR template paths**

Every template in `clusters/frank/apps/root/templates/` that references `apps/<app>/values.yaml` or `apps/<app>/manifests` needs the path prefixed with `clusters/frank/`.

For Helm-based apps (using `$values` ref):
```
$values/apps/<app>/values.yaml  →  $values/clusters/frank/apps/<app>/values.yaml
```

For raw manifest apps (using `path`):
```
path: apps/<app>/manifests  →  path: clusters/frank/apps/<app>/manifests
```

Update all templates. Use a script:

```bash
cd clusters/frank/apps/root/templates
# Fix $values/ references
sed -i '' 's|\$values/apps/|\$values/clusters/frank/apps/|g' *.yaml
# Fix path: references
sed -i '' 's|path: apps/|path: clusters/frank/apps/|g' *.yaml
```

Verify with:
```bash
grep -r 'apps/' clusters/frank/apps/root/templates/ | grep -v 'clusters/frank/apps/'
```

Expected: No output (all paths updated).

- [ ] **Step 4: Update Frank root app in ArgoCD**

The root Application's source path changes from `apps/root` to `clusters/frank/apps/root`:

```bash
argocd app set root --source-path clusters/frank/apps/root --port-forward --port-forward-namespace argocd
```

- [ ] **Step 5: Update Omni config patch paths**

```bash
# List current patches
omnictl get configpatches

# For each patch, export, update path references, and re-apply
# Example for one patch:
# omnictl get configpatch <PATCH_ID> -o yaml > /tmp/patch.yaml
# (edit path if needed)
# omnictl apply -f /tmp/patch.yaml
```

- [ ] **Step 6: Commit the restructure as a single atomic commit**

```bash
git add -A
git commit -m "refactor: restructure repo to multi-cluster monorepo (apps/ → clusters/frank/apps/)"
```

- [ ] **Step 7: Push and verify Frank ArgoCD sync**

```bash
git push
# Manually trigger sync
argocd app sync root --port-forward --port-forward-namespace argocd
# Check all apps reconciled
argocd app list --port-forward --port-forward-namespace argocd
```

Expected: All apps `Synced` and `Healthy`.

- [ ] **Step 8: Re-enable auto-sync**

```bash
argocd app set root --sync-policy automated --self-heal --port-forward --port-forward-namespace argocd
```

- [ ] **Step 9: Commit any fixups**

If any paths were missed, fix them and commit:

```bash
git add -A
git commit -m "fix: correct remaining path references after repo restructure"
```

---

## Chunk 2: Update References

### Task 2: Update documentation and CI

**Files:**
- Modify: `CLAUDE.md`
- Modify: `blog/content/building/` (any posts referencing `apps/` or `patches/`)
- Modify: `.github/workflows/` (any workflows referencing `apps/` or `patches/`)
- Modify: `docs/runbooks/manual-operations.yaml` (path references)

- [ ] **Step 1: Update CLAUDE.md**

Update the Architecture section to reflect the new structure. Update all path references throughout the file.

- [ ] **Step 2: Update blog posts with repo structure references**

Search blog posts for references to `apps/` or `patches/` and update them.

```bash
grep -rn 'apps/' blog/content/ | grep -v 'clusters/frank'
grep -rn 'patches/' blog/content/ | grep -v 'clusters/frank'
```

- [ ] **Step 3: Update CI workflows**

Check and update any workflow references:

```bash
grep -rn 'apps/' .github/workflows/
grep -rn 'patches/' .github/workflows/
```

- [ ] **Step 4: Update runbooks**

```bash
grep -rn 'apps/' docs/runbooks/
grep -rn 'patches/' docs/runbooks/
```

- [ ] **Step 5: Commit reference updates**

```bash
git add -A
git commit -m "docs: update all path references after multi-cluster restructure"
```
