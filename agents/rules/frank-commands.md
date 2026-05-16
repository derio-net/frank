## Frank Cluster Commands

```bash
# Environment — Frank cluster
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
