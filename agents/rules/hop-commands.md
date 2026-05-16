## Hop Cluster Commands

```bash
# Environment — Hop cluster (CAUTION: never source .env first — it overrides KUBECONFIG to Frank)
source .env_hop      # Hop (KUBECONFIG → clusters/hop/talosconfig/kubeconfig)

# Hop cluster operations
export TALOSCONFIG=$(pwd)/clusters/hop/talosconfig/talosconfig
talosctl -n $HOP_IP health  # HOP_IP exported from .env_hop
kubectl -n argocd get applications
```
