---
name: update-readme
description: Update README.md to reflect the current state of the Frank cluster after a new phase
user-invocable: true
disable-model-invocation: true
---

# Update README

Keep `README.md` in sync with the cluster after each new phase is deployed.

## Sections to Update

### 1. Technology Stack

Add a row for each new technology introduced in the phase. Columns: `Layer | Technology | Notes`.

- Check `docs/superpowers/plans/` for the phase design file to confirm the stack choices.
- Layer names should be concise (e.g. Metrics, Logs, Dashboards, Backup, Secrets, Multi-tenancy, VMs).

### 2. Repository Structure

Update the annotated tree if new top-level directories or significant `apps/<name>/` entries were added.

- Add new `apps/<name>/` entries with a brief inline comment.
- Update the blog post count in the `content/posts/` comment.
- Add any new top-level directories (e.g. `secrets/`, `docs/runbooks/`).
- Keep the tree concise — list representative entries, not every file.

### 3. Service Access

Add a row for each new LoadBalancer service. Columns: `Service | URL | IP`.

- Source of truth: `CLAUDE.md` Services table (keep both in sync).
- Include the port in the URL if non-standard (e.g. `:8080`).

### 4. Current Status

Add a row for each new ArgoCD application. Columns: `Application | Namespace | Notes`.

- Run `argocd app list --port-forward --port-forward-namespace argocd` to get the current list.
- Omit the `root` app (it's the App-of-Apps entry point, not a workload).
- Notes should be one-line descriptions of what the app does, not sync state (sync state goes stale immediately).

## After Updating

Commit with the phase number in the message:

```bash
git add README.md
git commit -m "docs(readme): update for phase NN — <one-line summary>"
```
