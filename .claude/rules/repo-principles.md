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

### Superpowers plugin skills (vendored)

The superpowers skills in `.claude/skills/` and agents in `.claude/agents/` are vendored copies from the user-level plugin cache so they work in cloud/CI environments. They don't auto-update.

After updating the plugin locally (`claude plugin update superpowers@claude-plugins-official`), re-sync and commit:

```bash
./scripts/sync-superpowers.sh
git add .claude/skills/ .claude/agents/
git commit -m "chore: sync superpowers plugin skills"
```

Check for updates periodically (e.g., when starting a new layer).
