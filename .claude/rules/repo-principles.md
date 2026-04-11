## Declarative-Only Principle

**Every resource on the cluster must be reproducible from code in this repo.** No `helm install`, no ad-hoc `kubectl apply` for workloads or configuration.

- Frank workloads: ArgoCD App-of-Apps (`apps/`)
- Hop workloads: ArgoCD App-of-Apps (`clusters/hop/apps/`)
- All machine config: Talos patches (`patches/`)
- Hop machine config: `talosctl` with combined patch file (not Omni)
- The **only** accepted exception: bootstrap secrets that must exist before the secret store is running. Apply them manually and document as a `# manual-operation` block in the plan.
  - Frank: SOPS-encrypted secrets applied via `sops --decrypt <file> | kubectl apply -f -`
  - Hop: Plain Kubernetes Secrets applied via `kubectl create secret` (Caddy Cloudflare token, Tailscale auth key)

`helm repo add` and `helm show values` are fine as **local research tools** to discover chart schemas — they don't touch the cluster.

## Maintenance

### Skills

Skills are installed at user level via the `superpowers` and `superpowers-for-vk` plugins. They are NOT vendored in this repo. Frank-specific skills remain repo-local in `.claude/skills/` (gitnexus, blog-post, deploy-app, media, sync-runbook, update-readme).

Plan behavior is driven by the profile at `docs/superpowers/plan-config.yaml`.
