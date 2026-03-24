## Repository Structure

```
apps/                  # ArgoCD App-of-Apps for Frank (Helm chart + per-app values)
  root/                # Entry point — templates all Application CRs
  <app>/values.yaml    # Per-app Helm values
  <app>/manifests/     # Raw K8s manifests (when no upstream chart)
  vclusters/           # Per-vCluster Helm values (multi-tenancy)
    template/          # Base values template
    <name>/values.yaml # Per-instance overrides
clusters/
  hop/                 # Hop edge cluster (see hop-infrastructure.md)
patches/               # Talos machine config patches (legacy phaseNN- naming)
  phase01-node-config/ # Node labels, scheduling
  phase02-cilium/      # CNI, eBPF kube-proxy
  phase03-longhorn/    # Distributed storage
  phase04-gpu/         # NVIDIA GPU operator
  phase05-mini-config/ # Intel iGPU DRA
blog/                  # Hugo static site (PaperMod theme, building/ + operating/ series)
omni/                  # Sidero Omni self-hosted config
docs/superpowers/plans/ # Implementation plans
docs/superpowers/specs/ # Design specs
docs/runbooks/         # Manual operations registry (manual-operations.yaml)
secrets/               # SOPS-encrypted bootstrap secrets (applied out-of-band)
  hop/                 # Hop cluster secrets
scripts/               # Utility scripts
```

## Plan Naming Convention

Plan and spec files follow: `YYYY-MM-DD--<layer>--<details>[-design].md`

- `<layer>` is the short code from `docs/layers.yaml` (e.g., `gpu`, `edge`, `auth`, `repo`)
- Multiple plans on the same layer share the code with different detail suffixes (e.g., `--gpu--intel-igpu-stack-mini` and `--gpu--operator-talos-fix`)
- The `repo` layer is for meta-tasks (blog infra, CI, restructuring)
- Bugfixes and extensions of existing layers use the same layer code. The relevant blog posts ('building' and 'operating' if appropriate) must be retroactively updated.
