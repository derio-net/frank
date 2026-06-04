## Frank Cluster Commands

```bash
# Environment — Frank cluster
# CAUTION: .env sets KUBECONFIG to a RELATIVE path (.talos/Frank_Kubeconfig.yaml).
# Always `cd` to the repo root BEFORE sourcing — a shell sourced elsewhere (or a
# backgrounded job with a different cwd) silently falls back to ~/.kube/config,
# whose endpoint is dead (192.168.64.2 i/o timeout).
source .env          # Frank (KUBECONFIG, TALOSCONFIG, OMNICONFIG)
source .env_devops   # DevOps (OMNI_ENDPOINT, service account key)

# Frank cluster operations
kubectl get nodes -o wide
talosctl health --nodes $CONTROL_PLANE_IP_1
omnictl get machines

# ArgoCD (Frank)
argocd app list --port-forward --port-forward-namespace argocd
argocd app sync root --port-forward --port-forward-namespace argocd
```
